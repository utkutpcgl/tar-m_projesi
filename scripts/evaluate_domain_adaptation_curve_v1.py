#!/usr/bin/env python3
"""Paired semantic/pixel-safety evaluation for the target-domain curve.

This intentionally omits connected-component and action-point geometry for
every intermediate curve point.  Those native-resolution metrics are expensive
on 24 MP masks and are only decision-relevant for the control and selected
winner.  No external threshold is tuned: each checkpoint's source-selected
policy is frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader

from agri_seg.constants import CLASS_NAMES, CROP, IGNORE, WEED
from agri_seg.data import EvalTransform, ManifestDataset, padded_collate
from agri_seg.engine import load_checkpoint, predict_logits
from agri_seg.manifest import SampleRecord, manifest_sha256, mask_tree_sha256, read_manifest
from agri_seg.safety import apply_safety_policy

try:
    from scripts.evaluate_intervention_metrics import _frozen_policy
except ModuleNotFoundError:
    from evaluate_intervention_metrics import _frozen_policy


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _miou(confusion: np.ndarray) -> float:
    matrix = confusion.astype(np.float64)
    true_positive = np.diag(matrix)
    union = matrix.sum(axis=0) + matrix.sum(axis=1) - true_positive
    iou = np.divide(
        true_positive,
        union,
        out=np.full(3, np.nan, dtype=np.float64),
        where=union > 0,
    )
    return float(np.nanmean(iou))


def _aggregate(per_image: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    confusion = np.sum(
        [np.asarray(row["confusion"], dtype=np.int64) for row in per_image], axis=0
    )
    matrix = confusion.astype(np.float64)
    true_positive = np.diag(matrix)
    union = matrix.sum(axis=0) + matrix.sum(axis=1) - true_positive
    iou = np.divide(
        true_positive,
        union,
        out=np.full(3, np.nan, dtype=np.float64),
        where=union > 0,
    )
    crop_pixels = sum(int(row["crop_pixels"]) for row in per_image)
    weed_pixels = sum(int(row["weed_pixels"]) for row in per_image)
    safe_pixels = sum(int(row["safe_pixels"]) for row in per_image)
    safe_crop = sum(int(row["safe_crop_pixels"]) for row in per_image)
    safe_weed = sum(int(row["safe_weed_pixels"]) for row in per_image)
    return {
        "images": len(per_image),
        "mean_iou": float(np.nanmean(iou)),
        "iou": {name: float(iou[index]) for index, name in enumerate(CLASS_NAMES)},
        "confusion_matrix": confusion.tolist(),
        "crop_spray_risk": safe_crop / crop_pixels if crop_pixels else None,
        "safe_weed_recall": safe_weed / weed_pixels if weed_pixels else None,
        "safe_weed_precision": safe_weed / safe_pixels if safe_pixels else None,
        "crop_pixels": crop_pixels,
        "weed_pixels": weed_pixels,
        "safe_action_pixels": safe_pixels,
    }


def paired_bootstrap_delta(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    resamples: int = 2000,
    seed: int = 1701,
) -> dict[str, float | int]:
    if [row["sample_id"] for row in baseline] != [row["sample_id"] for row in candidate]:
        raise ValueError("Paired bootstrap sample IDs/order do not match")
    baseline_matrices = np.asarray([row["confusion"] for row in baseline], dtype=np.int64)
    candidate_matrices = np.asarray([row["confusion"] for row in candidate], dtype=np.int64)
    rng = np.random.default_rng(seed)
    deltas = np.empty(resamples, dtype=np.float64)
    images = len(baseline)
    for index in range(resamples):
        selected = rng.integers(0, images, size=images)
        deltas[index] = _miou(candidate_matrices[selected].sum(axis=0)) - _miou(
            baseline_matrices[selected].sum(axis=0)
        )
    observed = _miou(candidate_matrices.sum(axis=0)) - _miou(
        baseline_matrices.sum(axis=0)
    )
    return {
        "resamples": resamples,
        "seed": seed,
        "observed_delta_mean_iou": observed,
        "ci95_low": float(np.quantile(deltas, 0.025)),
        "ci95_high": float(np.quantile(deltas, 0.975)),
        "bootstrap_probability_delta_gt_zero": float(np.mean(deltas > 0.0)),
    }


def select_candidate(
    runs: Sequence[Mapping[str, Any]],
    *,
    baseline_candidate: str,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply a predeclared target-weighted, breadth-gated selection rule."""
    by_name = {str(run["candidate"]): run for run in runs}
    if baseline_candidate not in by_name:
        raise ValueError(f"Missing baseline candidate: {baseline_candidate}")
    weights = {
        str(name): float(value)
        for name, value in specification["weights"].items()
    }
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError("Selection weights must sum to one")
    floors = {
        str(name): float(value)
        for name, value in specification["minimum_delta_vs_baseline"].items()
    }
    if set(floors) != set(weights):
        raise ValueError("Selection weights and non-inferiority floors must match")

    def metric(run: Mapping[str, Any], name: str) -> float:
        if name == "source_validation":
            return float(run["source_validation"]["mean_iou"])
        return float(run["development"][name]["mean_iou"])

    baseline = by_name[baseline_candidate]
    diagnostics: list[dict[str, Any]] = []
    for run in runs:
        values = {name: metric(run, name) for name in weights}
        deltas = {
            name: values[name] - metric(baseline, name) for name in weights
        }
        failed = [name for name, floor in floors.items() if deltas[name] < floor]
        diagnostics.append(
            {
                "candidate": str(run["candidate"]),
                "target_train_frames": int(run.get("target_train_frames", 0)),
                "simplicity_rank": int(
                    run.get(
                        "simplicity_rank",
                        run.get("target_train_frames", 0),
                    )
                ),
                "weighted_mean_iou": sum(
                    weights[name] * values[name] for name in weights
                ),
                "metrics": values,
                "delta_vs_baseline": deltas,
                "eligible": not failed,
                "failed_gates": failed,
            }
        )
    eligible = [row for row in diagnostics if row["eligible"]]
    if not eligible:
        raise RuntimeError("No candidate passed the frozen selection gates")
    best_score = max(float(row["weighted_mean_iou"]) for row in eligible)
    tolerance = float(specification.get("simplicity_tolerance", 0.0))
    near_best = [
        row
        for row in eligible
        if float(row["weighted_mean_iou"]) >= best_score - tolerance
    ]
    selected = min(
        near_best,
        key=lambda row: (
            int(row["simplicity_rank"]),
            -float(row["weighted_mean_iou"]),
            str(row["candidate"]),
        ),
    )
    return {
        "frozen_before_evaluation": True,
        "weights": weights,
        "minimum_delta_vs_baseline": floors,
        "simplicity_tolerance": tolerance,
        "best_eligible_weighted_mean_iou": best_score,
        "selected_candidate": selected["candidate"],
        "selected_target_train_frames": selected["target_train_frames"],
        "selected_simplicity_rank": selected["simplicity_rank"],
        "diagnostics": diagnostics,
    }


@torch.inference_mode()
def evaluate_records(
    model: torch.nn.Module,
    checkpoint: Mapping[str, Any],
    records: Sequence[SampleRecord],
    data_root: Path,
    workers: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    device = torch.device("cuda")
    loader = DataLoader(
        ManifestDataset(records, data_root, EvalTransform(), verify_files=True),
        batch_size=1,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        persistent_workers=workers > 0,
        collate_fn=padded_collate,
    )
    training = checkpoint["config"]["training"]
    policy = _frozen_policy(checkpoint)
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, batch in enumerate(loader, start=1):
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
        decisions = apply_safety_policy(probabilities, policy, crop_ids)
        height, width = batch["valid_size"][0]
        target = batch["mask"][0, :height, :width].cpu().numpy()
        semantic = probabilities[0, :, :height, :width].argmax(dim=0).cpu().numpy()
        safe = decisions["safe_weed"][0, :height, :width].cpu().numpy()
        valid = target != IGNORE
        encoded = target[valid].astype(np.int64) * 3 + semantic[valid].astype(np.int64)
        confusion = np.bincount(encoded, minlength=9).reshape(3, 3)
        crop = target == CROP
        weed = target == WEED
        rows.append(
            {
                "sample_id": str(batch["sample_id"][0]),
                "confusion": confusion.tolist(),
                "crop_pixels": int(crop.sum()),
                "weed_pixels": int(weed.sum()),
                "safe_pixels": int(np.count_nonzero(safe & valid)),
                "safe_crop_pixels": int(np.count_nonzero(safe & crop)),
                "safe_weed_pixels": int(np.count_nonzero(safe & weed)),
            }
        )
        if index % 50 == 0 or index == len(records):
            print(f"    {index}/{len(records)}", flush=True)
    result = _aggregate(rows)
    result["runtime_seconds"] = time.monotonic() - started
    result["external_threshold_tuning_performed"] = False
    result["frozen_policy"] = {
        "weed_threshold": policy.weed_threshold,
        "weed_threshold_by_crop_id": dict(policy.weed_threshold_by_crop_id),
        "unknown_crop_weed_threshold": policy.unknown_crop_weed_threshold,
    }
    return result, rows


def _source_metrics(run_dir: Path) -> dict[str, Any]:
    data = _json(run_dir / "metrics.json")
    selected = data["selected_operating_point"]
    return {
        "mean_iou": float(data["mean_iou"]),
        "iou": data["iou"],
        "crop_spray_risk": float(selected["worst_domain_crop_spray_risk"]),
        "safe_weed_recall": float(selected["macro_domain_safe_weed_recall"]),
        "constraint_met": bool(data["safety_constraint"]["met"]),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _valid_cache(
    path: Path,
    *,
    expected: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not path.is_file():
        return None
    try:
        payload = _json(path)
        if payload.get("identity") != dict(expected):
            return None
        result = payload["result"]
        per_image = payload["per_image"]
        if [row["sample_id"] for row in per_image] != expected["sample_ids"]:
            return None
        if int(result["images"]) != len(expected["sample_ids"]):
            return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return result, per_image


def run(config_path: Path) -> Path:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    project_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = _resolve(project_root, config["data_root"])
    output_root = _resolve(project_root, config["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    evaluations: dict[str, tuple[Path, list[SampleRecord], dict[str, Any]]] = {}
    for evaluation in config["evaluations"]:
        manifest = _resolve(project_root, evaluation["manifest"])
        dataset_ids = set(evaluation.get("dataset_ids", []))
        records = [
            record
            for record in read_manifest(manifest)
            if record.split == evaluation["split"]
            and (not dataset_ids or record.dataset_id in dataset_ids)
        ]
        if not records:
            raise ValueError(f"No records for {evaluation['name']}")
        evaluations[evaluation["name"]] = (
            manifest,
            records,
            {
                "manifest_sha256": manifest_sha256(manifest),
                "selected_mask_tree_sha256": mask_tree_sha256(records, data_root),
                "records": len(records),
                "split": evaluation["split"],
            },
        )
    runs: list[dict[str, Any]] = []
    per_image_by_evaluation: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: {} for name in evaluations
    }
    for model_config in config["models"]:
        candidate = str(model_config["candidate"])
        run_dir = _resolve(project_root, model_config["run_dir"])
        checkpoint_path = run_dir / "best.pt"
        checkpoint_digest = _sha256(checkpoint_path)
        print(f"Loading {candidate}", flush=True)
        model, checkpoint = load_checkpoint(checkpoint_path, torch.device("cuda"))
        development: dict[str, Any] = {}
        for name, (_, records, provenance) in evaluations.items():
            print(f"  {name}: {len(records)} images", flush=True)
            cache_path = output_root / "cache" / candidate / f"{name}.json"
            cache_identity = {
                "schema_version": 1,
                "candidate": candidate,
                "checkpoint_sha256": checkpoint_digest,
                "evaluation": name,
                "manifest_sha256": provenance["manifest_sha256"],
                "selected_mask_tree_sha256": provenance[
                    "selected_mask_tree_sha256"
                ],
                "evaluator_sha256": _sha256(Path(__file__).resolve()),
                "sample_ids": [record.sample_id for record in records],
            }
            cached = _valid_cache(cache_path, expected=cache_identity)
            if cached is None:
                result, per_image = evaluate_records(
                    model,
                    checkpoint,
                    records,
                    data_root,
                    int(config.get("workers", 4)),
                )
                result["provenance"] = provenance
                _write_json_atomic(
                    cache_path,
                    {
                        "identity": cache_identity,
                        "result": result,
                        "per_image": per_image,
                    },
                )
            else:
                print(f"    reusing hash-compatible cache", flush=True)
                result, per_image = cached
            development[name] = result
            per_image_by_evaluation[name][candidate] = per_image
        run_payload = {
            "candidate": candidate,
            "run_dir": str(run_dir),
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": checkpoint_digest,
            "source_validation": _source_metrics(run_dir),
            "development": development,
        }
        if "target_train_frames" in model_config:
            run_payload["target_train_frames"] = int(
                model_config["target_train_frames"]
            )
        if "simplicity_rank" in model_config:
            run_payload["simplicity_rank"] = int(model_config["simplicity_rank"])
        runs.append(run_payload)
        del model
        torch.cuda.empty_cache()
    baseline_name = str(config["baseline_candidate"])
    bootstrap: dict[str, dict[str, Any]] = {}
    for evaluation, by_candidate in per_image_by_evaluation.items():
        bootstrap[evaluation] = {}
        baseline = by_candidate[baseline_name]
        for candidate, per_image in by_candidate.items():
            bootstrap[evaluation][candidate] = paired_bootstrap_delta(
                baseline,
                per_image,
                resamples=int(config.get("bootstrap_resamples", 2000)),
                seed=int(config.get("bootstrap_seed", 1701)),
            )
    payload = {
        "schema_version": 1,
        "protocol": str(
            config.get("protocol", "paired_semantic_pixel_safety_v1")
        ),
        "config": str(config_path.resolve()),
        "config_sha256": _sha256(config_path),
        "baseline_candidate": baseline_name,
        "no_external_threshold_tuning": True,
        "component_metric_scope": (
            "omitted for intermediate curve points; full intervention metrics "
            "must be run for control and selected winner only"
        ),
        "runs": runs,
        "paired_bootstrap_delta_vs_baseline": bootstrap,
        "selection": select_candidate(
            runs,
            baseline_candidate=baseline_name,
            specification=config["selection"],
        ),
    }
    destination = output_root / "results.json"
    _write_json_atomic(destination, payload)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/domain_adaptation_semantic_eval_v1.yaml"),
    )
    print(run(parser.parse_args().config.expanduser().resolve()))


if __name__ == "__main__":
    main()
