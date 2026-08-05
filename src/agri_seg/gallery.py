"""Reproducible best/worst prediction galleries for locked evaluation splits."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch import nn
from torch.utils.data import DataLoader

from .constants import CROP, IGNORE, WEED
from .data import (
    EvalTransform,
    ManifestDataset,
    load_rgb_image,
    padded_collate,
    to_display_pil,
)
from .engine import load_checkpoint, predict_logits
from .manifest import (
    SampleRecord,
    iter_resolved,
    manifest_sha256,
    read_manifest,
)
from .safety import SafetyPolicy, apply_safety_policy
from .visualize import overlay_mask


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_calibrated_policy(
    checkpoint: Mapping[str, Any],
) -> tuple[SafetyPolicy, float]:
    """Recover the frozen source-validation policy; never tune on external data."""
    config = checkpoint.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("Checkpoint has no usable config")
    validation = checkpoint.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError(
            "Checkpoint has no source-validation result; a gallery cannot "
            "silently choose an external-test threshold"
        )
    selected = validation.get("selected_operating_point")
    if not isinstance(selected, Mapping) or "weed_threshold" not in selected:
        raise ValueError(
            "Checkpoint has no source-selected weed threshold; external-test "
            "threshold tuning is intentionally disabled"
        )
    base = SafetyPolicy(**dict(config.get("safety", {})))
    selected_by_crop_id = selected.get("weed_threshold_by_crop_id", {})
    if not isinstance(selected_by_crop_id, Mapping):
        raise ValueError("Source crop-ID threshold policy is not a mapping")
    unknown_threshold = float(
        selected.get(
            "unknown_crop_weed_threshold", selected["weed_threshold"]
        )
    )
    policy = replace(
        base,
        weed_threshold=unknown_threshold,
        weed_threshold_by_crop_id={
            int(crop_id): float(threshold)
            for crop_id, threshold in selected_by_crop_id.items()
        },
        unknown_crop_weed_threshold=unknown_threshold,
    )
    policy.validate()
    training = config.get("training", {})
    if not isinstance(training, Mapping):
        training = {}
    max_crop_spray_risk = float(
        training.get("max_crop_spray_risk", 0.005)
    )
    if not 0.0 <= max_crop_spray_risk <= 1.0:
        raise ValueError(
            "training.max_crop_spray_risk must be between zero and one"
        )
    return policy, max_crop_spray_risk


def image_quality_metrics(
    probabilities: torch.Tensor,
    target: torch.Tensor,
    policy: SafetyPolicy,
    max_crop_spray_risk: float,
    target_crop_id: torch.Tensor | None = None,
) -> dict[str, object]:
    """Compute transparent, per-image semantic and spray-safety metrics."""
    if probabilities.shape[0] != 1 or target.shape[0] != 1:
        raise ValueError("Per-image metrics require a batch size of one")
    probabilities = probabilities.detach().cpu()
    target = target.detach().cpu()
    if probabilities.shape[-2:] != target.shape[-2:]:
        raise ValueError("Prediction and target shapes do not match")

    prediction = probabilities.argmax(dim=1)
    valid = target != IGNORE
    target_crop = target == CROP
    target_weed = target == WEED
    predicted_crop = (prediction == CROP) & valid
    predicted_weed = (prediction == WEED) & valid
    decisions = apply_safety_policy(
        probabilities, policy, target_crop_id
    )

    crop_intersection = int((predicted_crop & target_crop).sum())
    crop_union = int((predicted_crop | target_crop).sum())
    weed_intersection = int((predicted_weed & target_weed).sum())
    weed_union = int((predicted_weed | target_weed).sum())
    crop_pixels = int(target_crop.sum())
    weed_pixels = int(target_weed.sum())
    valid_pixels = int(valid.sum())
    safe_weed = decisions["safe_weed"]
    weed_candidate = decisions["weed_candidate"] & ~decisions["unknown"]
    crop_as_raw_weed = int((weed_candidate & target_crop).sum())
    weed_as_raw_weed = int((weed_candidate & target_weed).sum())
    crop_as_safe_weed = int((safe_weed & target_crop).sum())
    weed_as_safe_weed = int((safe_weed & target_weed).sum())
    safe_weed_pixels = int((safe_weed & valid).sum())
    unknown_pixels = int((decisions["unknown"] & valid).sum())

    crop_spray_risk = (
        crop_as_safe_weed / crop_pixels if crop_pixels else None
    )
    weed_iou = weed_intersection / weed_union if weed_union else None
    crop_iou = crop_intersection / crop_union if crop_union else None
    return {
        "valid_pixels": valid_pixels,
        "crop_pixels": crop_pixels,
        "weed_pixels": weed_pixels,
        "crop_iou": crop_iou,
        "weed_iou": weed_iou,
        "crop_spray_pixels": crop_as_safe_weed,
        "crop_spray_risk": crop_spray_risk,
        "crop_safety_constraint_applicable": crop_pixels > 0,
        "crop_safety_constraint_met": (
            crop_spray_risk <= max_crop_spray_risk
            if crop_spray_risk is not None
            else None
        ),
        "crop_as_weed_pixels_raw": crop_as_raw_weed,
        "crop_as_weed_rate_raw": (
            crop_as_raw_weed / crop_pixels if crop_pixels else None
        ),
        "weed_as_raw_weed_pixels": weed_as_raw_weed,
        "weed_recall_raw": (
            weed_as_raw_weed / weed_pixels if weed_pixels else None
        ),
        "weed_as_safe_weed_pixels": weed_as_safe_weed,
        "safe_weed_recall": (
            weed_as_safe_weed / weed_pixels if weed_pixels else None
        ),
        "safe_weed_precision": (
            weed_as_safe_weed / safe_weed_pixels
            if safe_weed_pixels
            else None
        ),
        "safe_weed_pixels": safe_weed_pixels,
        "unknown_pixels": unknown_pixels,
        "unknown_rate": unknown_pixels / max(1, valid_pixels),
        # Empty-union agreement is useful only as an explicit sorting surrogate;
        # the reported weed_iou remains null because no IoU was measurable.
        "weed_iou_ranking_value": (
            weed_iou if weed_iou is not None else 1.0
        ),
    }


def _quality_key(
    item: Mapping[str, object],
) -> tuple[int, float, float, str]:
    metrics = item["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("Gallery entry has no metric mapping")
    crop_pixels = int(metrics["crop_pixels"])
    risk_value = metrics["crop_spray_risk"]
    constraint_met = metrics["crop_safety_constraint_met"]
    if crop_pixels == 0:
        # No target crop means safety was not measurable. Keep such images
        # between demonstrated-safe and demonstrated-unsafe examples.
        safety_tier = 1
        risk = 0.0
    else:
        safety_tier = 2 if bool(constraint_met) else 0
        risk = float(risk_value)
    weed_iou = float(metrics["weed_iou_ranking_value"])
    return safety_tier, -risk, weed_iou, str(item["sample_id"])


def select_gallery_entries(
    entries: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    """Select disjoint extremes: 10+10, or every image once when fewer."""
    if not entries:
        raise ValueError("Cannot build a gallery without evaluated images")
    ordered = sorted(entries, key=_quality_key)  # worst -> best
    if len(ordered) >= 20:
        worst_count = best_count = 10
    else:
        worst_count = len(ordered) // 2
        best_count = len(ordered) - worst_count

    selected: list[dict[str, object]] = []
    for rank, entry in enumerate(reversed(ordered[-best_count:]), start=1):
        selected.append({**entry, "selection": "best", "selection_rank": rank})
    if worst_count:
        for rank, entry in enumerate(ordered[:worst_count], start=1):
            selected.append(
                {**entry, "selection": "worst", "selection_rank": rank}
            )
    return selected


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:100] or "sample"


def _format_rate(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * float(value):.3f}%"


def render_prediction_overlay(
    image: Image.Image,
    target: torch.Tensor,
    prediction: torch.Tensor,
    decisions: Mapping[str, torch.Tensor],
    metrics: Mapping[str, object],
    sample_id: str,
    destination: str | Path,
    panel_size: tuple[int, int] = (360, 300),
) -> Path:
    """Render original, ground truth, semantic prediction, and safe-spray view."""
    image = image.convert("RGB")
    labels = target.detach().cpu().squeeze(0).numpy().astype(np.uint8)
    predicted = (
        prediction.detach().cpu().squeeze(0).numpy().astype(np.uint8)
    )
    if labels.shape != (image.height, image.width):
        raise ValueError("Original image and target dimensions do not match")

    max_width, max_height = panel_size
    scale = min(max_width / image.width, max_height / image.height)
    display_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    base = image.resize(display_size, Image.Resampling.LANCZOS)
    target_image = Image.fromarray(labels).resize(
        display_size, Image.Resampling.NEAREST
    )
    prediction_image = Image.fromarray(predicted).resize(
        display_size, Image.Resampling.NEAREST
    )
    ground_truth_overlay = overlay_mask(base, target_image)
    prediction_overlay = overlay_mask(base, prediction_image)

    safe_weed = decisions["safe_weed"].detach().cpu().squeeze(0).numpy()
    crop_guard = decisions["crop_guard"].detach().cpu().squeeze(0).numpy()
    unknown = decisions["unknown"].detach().cpu().squeeze(0).numpy()
    crop_spray_error = safe_weed & (labels == CROP)
    safety_rgb = np.asarray(image, dtype=np.float32).copy()
    safety_colors = np.zeros_like(safety_rgb)
    safety_colors[crop_guard] = (40, 220, 70)
    safety_colors[unknown] = (180, 60, 210)
    safety_colors[safe_weed] = (20, 190, 240)
    safety_colors[crop_spray_error] = (255, 180, 0)
    marked = crop_guard | unknown | safe_weed
    safety_rgb[marked] = (
        0.55 * safety_rgb[marked] + 0.45 * safety_colors[marked]
    )
    safety_overlay = Image.fromarray(
        safety_rgb.clip(0, 255).astype(np.uint8)
    ).resize(display_size, Image.Resampling.LANCZOS)

    panels = (base, ground_truth_overlay, prediction_overlay, safety_overlay)
    panel_labels = (
        "RGB",
        "Ground truth\ncrop=green, weed=red, ignore=purple",
        "Semantic prediction\ncrop=green, weed=red",
        "Safety: guard=green, spray=cyan\ncrop hit=yellow, unknown=purple",
    )
    header_height = 48
    label_height = 32
    canvas = Image.new(
        "RGB",
        (display_size[0] * len(panels), display_size[1] + header_height + label_height),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    weed_iou = metrics["weed_iou"]
    weed_iou_text = "n/a" if weed_iou is None else f"{float(weed_iou):.4f}"
    draw.text(
        (6, 5),
        (
            f"{sample_id} | weed IoU={weed_iou_text} | "
            f"crop spray risk={_format_rate(metrics['crop_spray_risk'])} | "
            f"safe weed recall={_format_rate(metrics['safe_weed_recall'])}"
        ),
        fill="black",
    )
    draw.text(
        (6, 24),
        (
            f"crop pixels={metrics['crop_pixels']} | "
            f"weed pixels={metrics['weed_pixels']} | "
            f"unknown={_format_rate(metrics['unknown_rate'])}"
        ),
        fill="black",
    )
    for index, (panel, label) in enumerate(zip(panels, panel_labels)):
        x = index * display_size[0]
        canvas.paste(panel, (x, header_height))
        draw.multiline_text(
            (x + 4, header_height + display_size[1] + 5),
            label,
            fill="black",
            spacing=1,
        )
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=92, subsampling=0)
    return output


def _device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return device


@torch.inference_mode()
def _rank_records(
    model: nn.Module,
    records: Sequence[SampleRecord],
    data_root: str | Path,
    device: torch.device,
    policy: SafetyPolicy,
    max_crop_spray_risk: float,
    workers: int,
    use_amp: bool,
    tile_size: int | None,
    tile_overlap: int,
    tile_trigger_pixels: int,
) -> list[dict[str, object]]:
    dataset = ManifestDataset(
        records, data_root, EvalTransform(), verify_files=True
    )
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        collate_fn=padded_collate,
    )
    entries: list[dict[str, object]] = []
    model.eval()
    by_id = {record.sample_id: record for record in records}
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        probabilities = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=use_amp,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_trigger_pixels=tile_trigger_pixels,
        ).float().softmax(dim=1)
        height, width = batch["valid_size"][0]
        sample_id = str(batch["sample_id"][0])
        record = by_id[sample_id]
        metrics = image_quality_metrics(
            probabilities[:, :, :height, :width],
            batch["mask"][:, :height, :width],
            policy,
            max_crop_spray_risk,
            crop_ids,
        )
        entries.append(
            {
                "sample_id": sample_id,
                "dataset_id": record.dataset_id,
                "group_id": record.group_id,
                "image_path": record.image_path,
                "mask_path": record.mask_path,
                "metrics": metrics,
            }
        )
    return entries


@torch.inference_mode()
def _render_selected(
    model: nn.Module,
    selected: Sequence[dict[str, object]],
    records: Sequence[SampleRecord],
    data_root: str | Path,
    destination: Path,
    device: torch.device,
    policy: SafetyPolicy,
    use_amp: bool,
    tile_size: int | None,
    tile_overlap: int,
    tile_trigger_pixels: int,
) -> list[dict[str, object]]:
    record_by_id = {record.sample_id: record for record in records}
    paths_by_id = {
        record.sample_id: (image_path, mask_path)
        for record, image_path, mask_path in iter_resolved(records, data_root)
    }
    artifacts: list[dict[str, object]] = []
    model.eval()
    for entry in selected:
        sample_id = str(entry["sample_id"])
        record = record_by_id[sample_id]
        dataset = ManifestDataset(
            [record], data_root, EvalTransform(), verify_files=True
        )
        batch = padded_collate([dataset[0]])
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        probabilities = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=use_amp,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_trigger_pixels=tile_trigger_pixels,
        ).float().softmax(dim=1)
        height, width = batch["valid_size"][0]
        probabilities = probabilities[:, :, :height, :width].cpu()
        prediction = probabilities.argmax(dim=1)
        decisions = apply_safety_policy(
            probabilities, policy, crop_ids.cpu()
        )
        image_path, _ = paths_by_id[sample_id]
        image = to_display_pil(load_rgb_image(image_path))

        selection = str(entry["selection"])
        selection_rank = int(entry["selection_rank"])
        relative_path = Path(selection) / (
            f"{selection_rank:02d}_{_safe_filename(sample_id)}.jpg"
        )
        render_prediction_overlay(
            image,
            batch["mask"][:, :height, :width],
            prediction,
            decisions,
            entry["metrics"],  # type: ignore[arg-type]
            sample_id,
            destination / relative_path,
        )
        artifacts.append(
            {
                **entry,
                "artifact": relative_path.as_posix(),
            }
        )
    return artifacts


def _write_json(payload: Mapping[str, object], destination: Path) -> None:
    def json_safe(value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, Mapping):
            return {
                str(key): json_safe(item) for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        return value

    destination.write_text(
        json.dumps(
            json_safe(payload),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def create_error_gallery(
    checkpoint_path: str | Path,
    manifest_path: str | Path,
    data_root: str | Path,
    split: str,
    output_directory: str | Path,
    workers: int = 4,
    device: str = "auto",
    overwrite: bool = False,
) -> Path:
    """Create a locked-policy external-test gallery and return its JSON index."""
    if workers < 0:
        raise ValueError("workers cannot be negative")
    destination = Path(output_directory).expanduser()
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Gallery destination is not a directory: {destination}")
    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Gallery destination is not empty: {destination}; "
            "pass overwrite=True to replace it"
        )

    execution_device = _device(device)
    model, checkpoint = load_checkpoint(checkpoint_path, execution_device)
    policy, max_crop_spray_risk = source_calibrated_policy(checkpoint)
    config = checkpoint["config"]
    training = config.get("training", {})
    use_amp = bool(training.get("amp", True))
    tile_size = training.get("eval_tile_size")
    tile_overlap = int(training.get("eval_tile_overlap", 128))
    tile_trigger_pixels = int(
        training.get("eval_tile_trigger_pixels", 4_000_000)
    )
    records = [
        record
        for record in read_manifest(manifest_path)
        if record.split == split
    ]
    if not records:
        raise ValueError(f"No {split!r} samples in {manifest_path}")

    entries = _rank_records(
        model,
        records,
        data_root,
        execution_device,
        policy,
        max_crop_spray_risk,
        workers,
        use_amp,
        tile_size,
        tile_overlap,
        tile_trigger_pixels,
    )
    selected = select_gallery_entries(entries)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (
        f".{destination.name}.tmp-{uuid.uuid4().hex}"
    )
    staging.mkdir()
    try:
        artifacts = _render_selected(
            model,
            selected,
            records,
            data_root,
            staging,
            execution_device,
            policy,
            use_amp,
            tile_size,
            tile_overlap,
            tile_trigger_pixels,
        )
        index: dict[str, object] = {
            "schema_version": 1,
            "checkpoint": {
                "path": str(Path(checkpoint_path).expanduser().resolve()),
                "sha256": _sha256(checkpoint_path),
                "epoch": checkpoint.get("epoch"),
                "global_step": checkpoint.get("global_step"),
                "architecture": config.get("model", {}).get("architecture"),
                "provenance": checkpoint.get("runtime_provenance"),
            },
            "manifest": {
                "path": str(Path(manifest_path).expanduser().resolve()),
                "sha256": manifest_sha256(manifest_path),
                "split": split,
                "evaluated_images": len(entries),
            },
            "calibration": {
                "source": "checkpoint.source_validation",
                "frozen_policy": asdict(policy),
                "max_crop_spray_risk": max_crop_spray_risk,
                "external_threshold_sweep_performed": False,
            },
            "ranking": {
                "priority": [
                    "per-image crop safety constraint",
                    "lower crop spray risk",
                    "higher semantic weed IoU",
                ],
                "absent_crop_rule": (
                    "not measurable; ranks between constraint-met and "
                    "constraint-violating samples"
                ),
                "empty_weed_union_rule": (
                    "reported weed_iou is null; correct empty-union agreement "
                    "uses 1.0 only for deterministic sorting"
                ),
                "selection_rule": (
                    "disjoint 10 best and 10 worst for >=20 images; otherwise "
                    "every image once, split as ceil(n/2) best and floor(n/2) worst"
                ),
            },
            "selection_counts": {
                "best": sum(
                    item["selection"] == "best" for item in artifacts
                ),
                "worst": sum(
                    item["selection"] == "worst" for item in artifacts
                ),
                "total": len(artifacts),
            },
            "artifacts": artifacts,
        }
        _write_json(index, staging / "index.json")

        if destination.exists():
            if overwrite:
                shutil.rmtree(destination)
            else:
                destination.rmdir()
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / "index.json"
