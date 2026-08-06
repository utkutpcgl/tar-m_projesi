#!/usr/bin/env python3
"""Measure a parallel crop-row prior with practical and oracle geometry.

The practical mode estimates row geometry only from high-confidence model crop
probabilities.  The oracle mode estimates the same geometry from the ground
truth crop mask and is label-leaking by design: it is an upper-bound diagnostic
for a future calibrated planter/RTK row map, never a deployable model result.

Both modes preserve the predicted vegetation-vs-background probability and
only redistribute crop-vs-weed probability.  They therefore cannot create a
plant merely because a pixel is close to a row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from torch.utils.data import DataLoader

from agri_seg.constants import CLASS_NAMES, CROP, IGNORE, WEED
from agri_seg.data import EvalTransform, ManifestDataset, padded_collate
from agri_seg.engine import load_checkpoint, predict_logits
from agri_seg.manifest import SampleRecord, manifest_sha256, mask_tree_sha256, read_manifest
from agri_seg.safety import apply_safety_policy

try:  # Import works both as ``python scripts/...`` and in the test package.
    from scripts.evaluate_intervention_metrics import (
        _bin_selections,
        _component_geometry,
        _frozen_policy,
        _json_safe,
        _select_records,
    )
except ModuleNotFoundError:
    from evaluate_intervention_metrics import (
        _bin_selections,
        _component_geometry,
        _frozen_policy,
        _json_safe,
        _select_records,
    )


@dataclass(frozen=True)
class RowFit:
    angle_deg: float
    normal_x: float
    normal_y: float
    peaks: tuple[float, ...]
    half_width_px: float
    sampled_seed_pixels: int
    seed_coverage_within_1p5_corridors: float
    orientation_score: float


class RowPriorAccumulator:
    """Shared-GT subset of intervention metrics needed for this prior test."""

    def __init__(self) -> None:
        self.images = 0
        self.confusion = np.zeros((3, 3), dtype=np.int64)
        self.crop_pixels = 0
        self.weed_pixels = 0
        self.safe_pixels = 0
        self.safe_on_crop = 0
        self.safe_on_weed = 0
        self.component_total: dict[str, int] = {}
        self.component_hit: dict[str, int] = {}

    def update(
        self,
        target: np.ndarray,
        semantic: np.ndarray,
        safe: np.ndarray,
        prepared_gt: tuple[np.ndarray, np.ndarray, Mapping[str, np.ndarray]],
    ) -> None:
        gt_labels, gt_areas, selections = prepared_gt
        valid = target != IGNORE
        encoded = target[valid].astype(np.int64) * 3 + semantic[valid].astype(np.int64)
        self.confusion += np.bincount(encoded, minlength=9).reshape(3, 3)
        crop = target == CROP
        weed = target == WEED
        self.images += 1
        self.crop_pixels += int(crop.sum())
        self.weed_pixels += int(weed.sum())
        self.safe_pixels += int(np.count_nonzero(safe & valid))
        self.safe_on_crop += int(np.count_nonzero(safe & crop))
        self.safe_on_weed += int(np.count_nonzero(safe & weed))
        hits = (
            np.bincount(
                gt_labels.reshape(-1),
                weights=safe.reshape(-1).astype(np.uint8),
                minlength=len(gt_areas) + 1,
            )[1:]
            if len(gt_areas)
            else np.empty(0, dtype=np.int64)
        )
        for name, selection in selections.items():
            self.component_total[name] = self.component_total.get(name, 0) + int(
                selection.sum()
            )
            self.component_hit[name] = self.component_hit.get(name, 0) + int(
                np.count_nonzero(hits[selection] > 0)
            )

    def compute(self) -> dict[str, Any]:
        confusion = self.confusion.astype(np.float64)
        true_positive = np.diag(confusion)
        ground_truth = confusion.sum(axis=1)
        predicted = confusion.sum(axis=0)
        union = ground_truth + predicted - true_positive
        iou = np.divide(
            true_positive,
            union,
            out=np.full(3, np.nan, dtype=np.float64),
            where=union > 0,
        )
        recall = np.divide(
            true_positive,
            ground_truth,
            out=np.full(3, np.nan, dtype=np.float64),
            where=ground_truth > 0,
        )
        return {
            "images": self.images,
            "semantic_segmentation": {
                "confusion_matrix": self.confusion.tolist(),
                "mean_iou": float(np.nanmean(iou)),
                "iou": {
                    name: float(iou[index])
                    for index, name in enumerate(CLASS_NAMES)
                },
                "recall": {
                    name: float(recall[index])
                    for index, name in enumerate(CLASS_NAMES)
                },
            },
            "frozen_safe_pixel_metrics": {
                "crop_pixels": self.crop_pixels,
                "weed_pixels": self.weed_pixels,
                "safe_action_pixels": self.safe_pixels,
                "crop_spray_risk_per_crop_pixel": (
                    self.safe_on_crop / self.crop_pixels if self.crop_pixels else None
                ),
                "safe_weed_pixel_recall": (
                    self.safe_on_weed / self.weed_pixels if self.weed_pixels else None
                ),
                "safe_weed_pixel_precision": (
                    self.safe_on_weed / self.safe_pixels if self.safe_pixels else None
                ),
            },
            "safe_component_hit_recall": {
                name: self.component_hit.get(name, 0) / total if total else None
                for name, total in self.component_total.items()
            },
            "metric_scope_note": (
                "GT weed-component geometry is computed once per image and shared "
                "across prior modes; action-point/footprint metrics remain in the "
                "main intervention report"
            ),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _weighted_histogram(
    transverse: np.ndarray,
    weights: np.ndarray,
    bin_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    lower = math.floor(float(transverse.min()) / bin_width) * bin_width - bin_width
    upper = math.ceil(float(transverse.max()) / bin_width) * bin_width + bin_width
    bins = max(8, int(math.ceil((upper - lower) / bin_width)))
    histogram, edges = np.histogram(
        transverse,
        bins=bins,
        range=(lower, upper),
        weights=weights,
    )
    centers = (edges[:-1] + edges[1:]) * 0.5
    return histogram.astype(np.float64, copy=False), centers


def _greedy_peaks(
    profile: np.ndarray,
    centers: np.ndarray,
    min_distance_px: float,
    max_rows: int = 16,
) -> tuple[float, ...]:
    if not profile.size or float(profile.max()) <= 0.0:
        return ()
    padded = np.pad(profile, (1, 1), mode="constant")
    local = (profile >= padded[:-2]) & (profile >= padded[2:])
    threshold = max(float(profile.max()) * 0.10, float(profile.mean()) * 1.35)
    candidates = np.flatnonzero(local & (profile >= threshold))
    if not candidates.size:
        candidates = np.asarray([int(profile.argmax())])
    ordered = candidates[np.argsort(profile[candidates])[::-1]]
    chosen: list[int] = []
    for index in ordered:
        if all(abs(float(centers[index] - centers[prior])) >= min_distance_px for prior in chosen):
            chosen.append(int(index))
        if len(chosen) >= max_rows:
            break
    return tuple(sorted(float(centers[index]) for index in chosen))


def fit_parallel_rows(
    seed_score: np.ndarray,
    seed_mask: np.ndarray,
    *,
    angle_step_deg: int = 3,
    corridor_fraction_of_short_side: float = 0.03,
    minimum_seed_pixels: int = 96,
    maximum_sample_pixels: int = 100_000,
) -> RowFit | None:
    """Fit parallel row centerlines by projection-profile concentration."""
    if seed_score.shape != seed_mask.shape or seed_score.ndim != 2:
        raise ValueError("seed score/mask must be equal HxW arrays")
    rows, columns = np.nonzero(seed_mask)
    if len(rows) < minimum_seed_pixels:
        return None
    scores = seed_score[rows, columns].astype(np.float64, copy=False)
    if len(rows) > maximum_sample_pixels:
        # Deterministic, spatial-order-independent-enough sampling for a fit.
        selected = np.linspace(0, len(rows) - 1, maximum_sample_pixels, dtype=np.int64)
        rows, columns, scores = rows[selected], columns[selected], scores[selected]
    x = columns.astype(np.float64, copy=False)
    y = rows.astype(np.float64, copy=False)
    half_width = float(
        np.clip(
            min(seed_mask.shape) * corridor_fraction_of_short_side,
            8.0,
            220.0,
        )
    )
    bin_width = max(2.0, half_width / 4.0)
    best: tuple[float, float, float, np.ndarray, np.ndarray] | None = None
    for angle_deg in range(0, 180, angle_step_deg):
        angle = math.radians(float(angle_deg))
        normal_x = -math.sin(angle)
        normal_y = math.cos(angle)
        transverse = x * normal_x + y * normal_y
        histogram, centers = _weighted_histogram(transverse, scores, bin_width)
        smoothed = ndimage.gaussian_filter1d(
            histogram,
            sigma=max(0.8, half_width / bin_width / 2.0),
            mode="nearest",
        )
        mean = float(smoothed.mean())
        if mean <= 0.0:
            continue
        # Dimensionless concentration; correct row angle gives narrow peaks.
        concentration = float(np.mean(np.square(smoothed / mean)))
        candidate = (concentration, normal_x, normal_y, transverse, centers)
        if best is None or concentration > best[0]:
            best = candidate
    if best is None:
        return None
    score, normal_x, normal_y, transverse, _ = best
    histogram, centers = _weighted_histogram(transverse, scores, bin_width)
    smoothed = ndimage.gaussian_filter1d(
        histogram,
        sigma=max(0.8, half_width / bin_width / 2.0),
        mode="nearest",
    )
    peaks = _greedy_peaks(smoothed, centers, min_distance_px=2.4 * half_width)
    if not peaks:
        return None
    peak_array = np.asarray(peaks, dtype=np.float64)
    distances = np.min(np.abs(transverse[:, None] - peak_array[None, :]), axis=1)
    coverage = float(np.average(distances <= 1.5 * half_width, weights=scores))
    if coverage < 0.50:
        return None
    angle_deg = math.degrees(math.atan2(-normal_x, normal_y)) % 180.0
    return RowFit(
        angle_deg=angle_deg,
        normal_x=normal_x,
        normal_y=normal_y,
        peaks=peaks,
        half_width_px=half_width,
        sampled_seed_pixels=len(rows),
        seed_coverage_within_1p5_corridors=coverage,
        orientation_score=score,
    )


def row_probability(shape: tuple[int, int], fit: RowFit) -> np.ndarray:
    """Build a soft crop-row probability without a full coordinate meshgrid."""
    height, width = shape
    x_term = np.arange(width, dtype=np.float32) * np.float32(fit.normal_x)
    distances = np.full((height, width), np.inf, dtype=np.float32)
    for top in range(0, height, 512):
        bottom = min(top + 512, height)
        y_term = (
            np.arange(top, bottom, dtype=np.float32)[:, None]
            * np.float32(fit.normal_y)
        )
        transverse = y_term + x_term[None, :]
        chunk = distances[top:bottom]
        for peak in fit.peaks:
            np.minimum(chunk, np.abs(transverse - np.float32(peak)), out=chunk)
    gaussian = np.exp(-0.5 * np.square(distances / fit.half_width_px))
    return (0.10 + 0.80 * gaussian).astype(np.float32, copy=False)


def adjust_crop_weed_probabilities(
    probabilities: torch.Tensor,
    row_crop_probability: torch.Tensor,
    strength: float,
) -> torch.Tensor:
    """Apply the prior conditional on model-predicted vegetation."""
    if probabilities.ndim != 4 or probabilities.shape[0] != 1:
        raise ValueError("Expected one Bx3xHxW probability tensor")
    if row_crop_probability.shape != probabilities.shape[-2:]:
        raise ValueError("Row probability shape mismatch")
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength must be in [0,1]")
    adjusted = probabilities.clone()
    vegetation = probabilities[:, CROP] + probabilities[:, WEED]
    conditional_crop = probabilities[:, CROP] / vegetation.clamp_min(1e-7)
    blended = (
        (1.0 - strength) * conditional_crop
        + strength * row_crop_probability.unsqueeze(0)
    )
    adjusted[:, CROP] = vegetation * blended
    adjusted[:, WEED] = vegetation * (1.0 - blended)
    return adjusted


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(path), size=size) if path.is_file() else ImageFont.load_default()


def _overlay(image: Image.Image, classes: np.ndarray, alpha: float = 0.48) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    colors = np.zeros_like(rgb)
    colored = (classes == CROP) | (classes == WEED)
    colors[classes == CROP] = (35, 220, 55)
    colors[classes == WEED] = (235, 45, 40)
    rgb[colored] = (1.0 - alpha) * rgb[colored] + alpha * colors[colored]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def _gallery(
    source_path: Path,
    target: np.ndarray,
    predictions: Mapping[str, np.ndarray],
    destination: Path,
    subtitle: str,
) -> None:
    with Image.open(source_path) as handle:
        source = handle.convert("RGB")
    panel_width = 390
    panel_height = max(1, round(source.height * panel_width / source.width))
    source = source.resize((panel_width, panel_height), Image.Resampling.LANCZOS)
    panels: list[tuple[str, Image.Image]] = [("RGB input", source.copy())]
    labels = (
        ("Ground truth", target),
        ("Baseline", predictions["baseline"]),
        ("Practical row prior", predictions["practical_0p65"]),
        ("Oracle geometry ceiling", predictions["oracle_0p65"]),
    )
    for label, classes in labels:
        resized_classes = np.asarray(
            Image.fromarray(classes.astype(np.uint8)).resize(
                (panel_width, panel_height), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        )
        panels.append((label, _overlay(source, resized_classes)))
    header = 105
    canvas = Image.new("RGB", (panel_width * len(panels), panel_height + header), "white")
    draw = ImageDraw.Draw(canvas)
    title_font, label_font = _font(25), _font(18)
    draw.text((18, 10), subtitle, fill="black", font=title_font)
    draw.text(
        (18, 48),
        "Green = crop | Red = weed | Oracle uses GT only to estimate row geometry",
        fill=(35, 35, 35),
        font=label_font,
    )
    for index, (label, panel) in enumerate(panels):
        resized = panel.resize((panel_width, panel_height), Image.Resampling.LANCZOS)
        left = index * panel_width
        canvas.paste(resized, (left, header))
        draw.rectangle((left, 78, left + panel_width, 105), fill=(245, 245, 245))
        draw.text((left + 8, 81), label, fill="black", font=label_font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=92, optimize=True)


def _summary_row(evaluation: str, mode: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    overall = payload
    semantic = overall["semantic_segmentation"]
    safe = overall["frozen_safe_pixel_metrics"]
    components = overall["safe_component_hit_recall"]
    return {
        "evaluation": evaluation,
        "mode": mode,
        "images": overall["images"],
        "mean_iou": semantic["mean_iou"],
        "crop_iou": semantic["iou"]["target_crop"],
        "weed_iou": semantic["iou"]["other_vegetation"],
        "crop_spray_risk": safe["crop_spray_risk_per_crop_pixel"],
        "safe_weed_pixel_recall": safe["safe_weed_pixel_recall"],
        "safe_component_hit_recall": components["all"],
        "small_lt14px_safe_component_hit_recall": components["sub_patch_lt14px"],
    }


@torch.inference_mode()
def evaluate(
    model: torch.nn.Module,
    checkpoint: Mapping[str, Any],
    records: Sequence[SampleRecord],
    data_root: Path,
    workers: int,
    strengths: Sequence[float],
    practical_threshold: float,
    action_guard_threshold: float,
    row_fit_config: Mapping[str, Any],
    gallery_root: Path,
    evaluation_name: str,
    gallery_examples: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    device = torch.device("cuda")
    dataset = ManifestDataset(records, data_root, EvalTransform(), verify_files=True)
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        persistent_workers=workers > 0,
        collate_fn=padded_collate,
    )
    policy = _frozen_policy(checkpoint)
    training = checkpoint["config"]["training"]
    mode_names = ["baseline", "practical_guard", "oracle_guard"] + [
        f"{source}_{str(strength).replace('.', 'p')}"
        for source in ("practical", "oracle")
        for strength in strengths
    ]
    accumulators = {name: RowPriorAccumulator() for name in mode_names}
    fit_rows: list[dict[str, Any]] = []
    started = time.monotonic()
    for image_index, batch in enumerate(loader):
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        logits = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=bool(training.get("amp", True)),
            tile_size=training.get("eval_tile_size"),
            tile_overlap=int(training.get("eval_tile_overlap", 128)),
            tile_trigger_pixels=int(training.get("eval_tile_trigger_pixels", 4_000_000)),
        )
        probabilities = logits.float().softmax(dim=1)
        height, width = batch["valid_size"][0]
        probabilities = probabilities[:, :, :height, :width]
        target = batch["mask"][0, :height, :width].cpu().numpy()
        gt_labels, _, gt_areas, _, gt_diameters = _component_geometry(target == WEED)
        prepared_gt = (gt_labels, gt_areas, _bin_selections(gt_diameters))

        baseline_decisions = apply_safety_policy(probabilities, policy, crop_ids)
        baseline_semantic = probabilities[0].argmax(dim=0).cpu().numpy()
        baseline_safe = baseline_decisions["safe_weed"][0].cpu().numpy()
        accumulators["baseline"].update(
            target, baseline_semantic, baseline_safe, prepared_gt
        )

        practical_score = probabilities[0, CROP].detach().cpu().numpy()
        practical_mask = (
            (practical_score >= practical_threshold)
            & (practical_score > probabilities[0, WEED].detach().cpu().numpy())
        )
        fits = {
            "practical": fit_parallel_rows(
                practical_score,
                practical_mask,
                **dict(row_fit_config),
            ),
            "oracle": fit_parallel_rows(
                (target == CROP).astype(np.float32),
                target == CROP,
                **dict(row_fit_config),
            ),
        }
        image_predictions: dict[str, np.ndarray] = {"baseline": baseline_semantic}
        for source, fit in fits.items():
            fit_rows.append(
                {
                    "evaluation": evaluation_name,
                    "sample_id": str(batch["sample_id"][0]),
                    "source": source,
                    "fit_available": fit is not None,
                    "fit": None if fit is None else asdict(fit),
                }
            )
            prior = (
                None
                if fit is None
                else torch.from_numpy(row_probability((height, width), fit)).to(
                    device, non_blocking=True
                )
            )
            guarded_safe = (
                baseline_safe
                if prior is None
                else (
                    baseline_decisions["safe_weed"][0]
                    & (prior < action_guard_threshold)
                )
                .cpu()
                .numpy()
            )
            accumulators[f"{source}_guard"].update(
                target, baseline_semantic, guarded_safe, prepared_gt
            )
            for strength in strengths:
                mode = f"{source}_{str(strength).replace('.', 'p')}"
                adjusted = (
                    probabilities
                    if prior is None
                    else adjust_crop_weed_probabilities(probabilities, prior, strength)
                )
                decisions = apply_safety_policy(adjusted, policy, crop_ids)
                semantic = adjusted[0].argmax(dim=0).cpu().numpy()
                safe = decisions["safe_weed"][0].cpu().numpy()
                accumulators[mode].update(target, semantic, safe, prepared_gt)
                if math.isclose(strength, max(strengths)):
                    image_predictions[mode] = semantic
            del prior

        if image_index < gallery_examples:
            # Gallery expects these stable aliases for the strongest declared prior.
            strongest = str(max(strengths)).replace(".", "p")
            image_predictions["practical_0p65"] = image_predictions[
                f"practical_{strongest}"
            ]
            image_predictions["oracle_0p65"] = image_predictions[f"oracle_{strongest}"]
            source_path = data_root / records[image_index].image_path
            _gallery(
                source_path,
                target,
                image_predictions,
                gallery_root / evaluation_name / f"{image_index + 1:02d}.jpg",
                f"{evaluation_name} — {records[image_index].sample_id}",
            )
        if (image_index + 1) % 25 == 0 or image_index + 1 == len(dataset):
            print(
                f"  {evaluation_name}: {image_index + 1}/{len(dataset)} "
                f"({(image_index + 1) / max(time.monotonic() - started, 1e-9):.2f} img/s)",
                flush=True,
            )
    return {name: accumulator.compute() for name, accumulator in accumulators.items()}, fit_rows


def run(config_path: Path) -> Path:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    project_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = _resolve(project_root, config["data_root"])
    output_root = _resolve(project_root, config["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = _resolve(project_root, config["checkpoint"])
    model, checkpoint = load_checkpoint(checkpoint_path, torch.device("cuda"))
    strengths = tuple(float(value) for value in config["prior_strengths"])
    if not strengths:
        raise ValueError("At least one prior strength is required")
    summaries: list[dict[str, Any]] = []
    index: dict[str, Any] = {
        "schema_version": 1,
        "protocol": "parallel_crop_row_prior_diagnostic_v1",
        "config": str(config_path.resolve()),
        "config_sha256": _sha256(config_path),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "checkpoint_runtime_provenance": checkpoint["runtime_provenance"],
        "prior_strengths": strengths,
        "practical_definition": (
            "parallel rows estimated only from model crop probability; vegetation/background "
            "posterior is preserved and only crop/weed conditional probability changes"
        ),
        "action_guard_definition": (
            "the frozen baseline safe-weed action is retained only outside the "
            "estimated crop-row corridor; the guard never creates a new action "
            "and needs no probability-threshold recalibration"
        ),
        "oracle_definition": (
            "same row estimator seeded by GT crop mask; label-leaking geometry ceiling only, "
            "not a deployable score"
        ),
        "evaluations": {},
    }
    all_fits: list[dict[str, Any]] = []
    for evaluation in config["evaluations"]:
        name = str(evaluation["name"])
        manifest = _resolve(project_root, evaluation["manifest"])
        records = _select_records(
            manifest,
            str(evaluation["split"]),
            evaluation.get("dataset_ids"),
            evaluation.get("limit"),
        )
        print(f"Evaluating {name}: {len(records)} images", flush=True)
        metrics, fits = evaluate(
            model,
            checkpoint,
            records,
            data_root,
            int(config.get("workers", 4)),
            strengths,
            float(config.get("practical_crop_probability_threshold", 0.60)),
            float(config.get("action_guard_row_probability_threshold", 0.50)),
            config.get("row_fit", {}),
            output_root / "gallery",
            name,
            int(evaluation.get("gallery_examples", 2)),
        )
        payload = {
            "identity": {
                "name": name,
                "role": evaluation["role"],
                "manifest": str(manifest),
                "split": evaluation["split"],
                "dataset_ids": evaluation.get("dataset_ids", []),
                "records": len(records),
            },
            "provenance": {
                "manifest_sha256": manifest_sha256(manifest),
                "selected_mask_tree_sha256": mask_tree_sha256(records, data_root),
                "external_threshold_tuning_performed": False,
            },
            "modes": metrics,
        }
        destination = output_root / f"{name}.json"
        destination.write_text(
            json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index["evaluations"][name] = str(destination)
        all_fits.extend(fits)
        summaries.extend(_summary_row(name, mode, result) for mode, result in metrics.items())
    fit_path = output_root / "row_fit_diagnostics.json"
    fit_path.write_text(json.dumps(_json_safe(all_fits), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = output_root / "summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    index["summary_csv"] = str(summary_path)
    index["row_fit_diagnostics"] = str(fit_path)
    index_path = output_root / "index.json"
    index_path.write_text(json.dumps(_json_safe(index), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/crop_row_prior_v1.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    print(run(parse_args().config.expanduser().resolve()))


if __name__ == "__main__":
    main()
