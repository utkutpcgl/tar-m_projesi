#!/usr/bin/env python3
"""Evaluate accepted checkpoints on frozen binary weedy-rice calibration data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader

from agri_seg.constants import IGNORE, WEED
from agri_seg.data import EvalTransform, ManifestDataset, padded_collate
from agri_seg.engine import (
    _safety_policy,
    load_checkpoint,
    predict_logits,
    source_tree_sha256,
)
from agri_seg.manifest import SampleRecord, mask_tree_sha256, read_manifest
from agri_seg.safety import apply_safety_policy


PREDICTION_MODES = ("semantic_argmax", "weed_candidate", "safe_weed")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "min": float(array.min()),
        "p05": float(np.percentile(array, 5)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
        "mean": float(array.mean()),
    }


def image_tree_sha256(records: list[SampleRecord], data_root: Path) -> str:
    digest = hashlib.sha256()
    for recorded in sorted({record.image_path for record in records}):
        path = Path(recorded)
        resolved = path if path.is_absolute() else data_root / path
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        digest.update(recorded.encode("utf-8"))
        digest.update(b"\0")
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_manifest(path: Path, expected: dict[str, Any]) -> list[SampleRecord]:
    records = read_manifest(path)
    if len(records) != int(expected["samples"]):
        raise ValueError(f"Expected {expected['samples']} rows, got {len(records)}")
    if {record.split for record in records} != {"external_calibration"}:
        raise ValueError("Weedy-rice diagnostic manifest must be calibration-only")
    if {record.dataset_id for record in records} != {str(expected["dataset_id"])}:
        raise ValueError("Unexpected diagnostic dataset_id")
    if {record.target_crop_id for record in records} != {int(expected["target_crop_id"])}:
        raise ValueError("Unexpected target crop ID")
    if any(record.annotation_exhaustive for record in records):
        raise ValueError("Binary partial masks must be marked non-exhaustive")
    if len({record.group_id for record in records}) != int(expected["capture_groups"]):
        raise ValueError("Unexpected calibration capture-group count")
    return records


def ensure_no_training_exposure(
    config: dict[str, Any], data_root: Path, records: list[SampleRecord]
) -> tuple[Path, str]:
    if Path(str(config["data_root"])).resolve() != data_root:
        raise ValueError("Training and diagnostic data roots differ")
    manifest = Path(str(config["manifest"])).resolve()
    training = read_manifest(manifest)
    candidate_ids = {record.dataset_id for record in records}
    if candidate_ids & {record.dataset_id for record in training}:
        raise ValueError("Weedy-rice data leaked into accepted-control training")
    candidate_images = {record.image_path for record in records}
    if candidate_images & {record.image_path for record in training}:
        raise ValueError("Diagnostic image path leaked into accepted-control training")
    return manifest, sha256(manifest)


def empty_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0, "tn": 0}


def update_counts(counts: dict[str, int], prediction: torch.Tensor, target: torch.Tensor) -> None:
    counts["tp"] += int((prediction & target).sum())
    counts["fp"] += int((prediction & ~target).sum())
    counts["fn"] += int((~prediction & target).sum())
    counts["tn"] += int((~prediction & ~target).sum())


def metrics_from_counts(counts: dict[str, int]) -> dict[str, float | int]:
    tp, fp, fn, tn = (counts[name] for name in ("tp", "fp", "fn", "tn"))
    total = tp + fp + fn + tn
    return {
        **counts,
        "pixels": total,
        "target_positive_fraction": (tp + fn) / max(1, total),
        "predicted_positive_fraction": (tp + fp) / max(1, total),
        "iou": tp / max(1, tp + fp + fn),
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "specificity": tn / max(1, tn + fp),
    }


def coverage_bin(fraction: float) -> str:
    boundaries = (
        (0.05, "gt_0_le_5"),
        (0.10, "gt_5_le_10"),
        (0.20, "gt_10_le_20"),
        (0.30, "gt_20_le_30"),
        (0.40, "gt_30_le_40"),
        (0.60, "gt_40_le_60"),
        (0.75, "gt_60_le_75"),
        (0.90, "gt_75_lt_90"),
    )
    for upper, name in boundaries:
        if fraction <= upper + 1e-12:
            return name
    raise ValueError(f"Forbidden weedy-rice coverage: {fraction}")


def ranking_metrics(positive: np.ndarray, negative: np.ndarray) -> dict[str, float | int]:
    positive_desc = np.cumsum(positive[::-1], dtype=np.float64)
    negative_desc = np.cumsum(negative[::-1], dtype=np.float64)
    positives = float(positive.sum())
    negatives = float(negative.sum())
    if positives <= 0 or negatives <= 0:
        raise ValueError("Binary ranking metrics require both classes")
    recall = positive_desc / positives
    precision = positive_desc / np.maximum(positive_desc + negative_desc, 1.0)
    previous = np.concatenate(([0.0], recall[:-1]))
    average_precision = float(np.sum((recall - previous) * precision))
    false_positive_rate = negative_desc / negatives
    auroc = float(
        np.trapz(
            np.concatenate(([0.0], recall)),
            np.concatenate(([0.0], false_positive_rate)),
        )
    )
    return {
        "histogram_bins": int(len(positive)),
        "positive_pixels": int(positives),
        "negative_pixels": int(negatives),
        "approx_average_precision": average_precision,
        "approx_auroc": auroc,
    }


def fixed_policy(checkpoint: dict[str, Any]):
    config = checkpoint["config"]
    selected = checkpoint.get("validation", {}).get("selected_operating_point")
    if not isinstance(selected, dict) or "weed_threshold" not in selected:
        raise ValueError("Checkpoint lacks source-frozen operating point")
    configured = selected.get("weed_threshold_by_crop_id", {})
    if not isinstance(configured, dict):
        raise ValueError("Invalid source crop-specific threshold policy")
    unknown = float(
        selected.get("unknown_crop_weed_threshold", selected["weed_threshold"])
    )
    return replace(
        _safety_policy(config),
        weed_threshold=unknown,
        weed_threshold_by_crop_id={int(key): float(value) for key, value in configured.items()},
        unknown_crop_weed_threshold=unknown,
    )


@torch.inference_mode()
def evaluate_run(
    checkpoint_path: Path,
    records: list[SampleRecord],
    manifest_path: Path,
    data_root: Path,
    workers: int,
    histogram_bins: int,
) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the diagnostic")
    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    model.eval()
    policy = fixed_policy(checkpoint)
    config = checkpoint["config"]
    training_manifest, training_manifest_sha = ensure_no_training_exposure(
        config, data_root, records
    )
    dataset = ManifestDataset(records, data_root, EvalTransform(), verify_files=True)
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        collate_fn=padded_collate,
    )
    aggregate = {mode: empty_counts() for mode in PREDICTION_MODES}
    by_coverage: dict[str, dict[str, dict[str, int]]] = {}
    image_iou: dict[str, list[float]] = {mode: [] for mode in PREDICTION_MODES}
    target_fractions: list[float] = []
    positive_hist = np.zeros(histogram_bins, dtype=np.int64)
    negative_hist = np.zeros(histogram_bins, dtype=np.int64)
    started = time.monotonic()

    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        logits = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=bool(config["training"].get("amp", True)),
            tile_size=config["training"].get("eval_tile_size"),
            tile_overlap=int(config["training"].get("eval_tile_overlap", 128)),
            tile_trigger_pixels=int(config["training"].get("eval_tile_trigger_pixels", 4_000_000)),
        )
        probabilities = logits.float().softmax(dim=1)
        safety = apply_safety_policy(probabilities, policy, crop_ids)
        height, width = batch["valid_size"][0]
        partial = batch["mask"][0, :height, :width].to(device, non_blocking=True)
        values = set(torch.unique(partial).cpu().tolist())
        if not values <= {WEED, IGNORE} or WEED not in values:
            raise ValueError(f"Invalid partial-mask palette: {values}")
        target = partial == WEED
        fraction = float(target.float().mean())
        name = coverage_bin(fraction)
        target_fractions.append(fraction)
        modes = {
            "semantic_argmax": probabilities[0, :, :height, :width].argmax(dim=0) == WEED,
            "weed_candidate": safety["weed_candidate"][0, :height, :width],
            "safe_weed": safety["safe_weed"][0, :height, :width],
        }
        by_coverage.setdefault(name, {mode: empty_counts() for mode in PREDICTION_MODES})
        for mode, prediction in modes.items():
            update_counts(aggregate[mode], prediction, target)
            update_counts(by_coverage[name][mode], prediction, target)
            one = empty_counts()
            update_counts(one, prediction, target)
            image_iou[mode].append(float(metrics_from_counts(one)["iou"]))

        weed_probability = probabilities[0, WEED, :height, :width]
        positive_hist += torch.histc(
            weed_probability[target], bins=histogram_bins, min=0.0, max=1.0
        ).to(torch.int64).cpu().numpy()
        negative_hist += torch.histc(
            weed_probability[~target], bins=histogram_bins, min=0.0, max=1.0
        ).to(torch.int64).cpu().numpy()

    return {
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "training_manifest": str(training_manifest),
        "training_manifest_sha256": training_manifest_sha,
        "weedy_rice_training_exposure": False,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "source_frozen_policy": {
            "weed_threshold": policy.weed_threshold,
            "weed_threshold_by_crop_id": dict(policy.weed_threshold_by_crop_id),
            "unknown_crop_weed_threshold": policy.unknown_crop_weed_threshold,
            "crop_threshold": policy.crop_threshold,
            "min_confidence": policy.min_confidence,
            "min_margin": policy.min_margin,
            "max_entropy": policy.max_entropy,
            "crop_dilation_px": policy.crop_dilation_px,
        },
        "metrics": {mode: metrics_from_counts(counts) for mode, counts in aggregate.items()},
        "by_target_coverage": {
            name: {mode: metrics_from_counts(counts) for mode, counts in modes.items()}
            for name, modes in sorted(by_coverage.items())
        },
        "per_image_iou": {mode: distribution(values) for mode, values in image_iou.items()},
        "target_positive_fraction": distribution(target_fractions),
        "weed_probability_ranking": ranking_metrics(positive_hist, negative_hist),
        "runtime": {"images": len(records), "seconds": time.monotonic() - started},
        "external_threshold_sweep_performed": False,
        "model_evaluation_mode": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    if arguments.workers < 0:
        raise ValueError("--workers cannot be negative")
    protocol_path = arguments.protocol.expanduser().resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise ValueError("Protocol must be a mapping")
    if protocol.get("frozen_before_evaluation") is not True:
        raise ValueError("Protocol was not frozen before evaluation")
    if protocol.get("external_test_used") is not False:
        raise ValueError("External test is forbidden")
    if protocol.get("model_selection_allowed") is not False:
        raise ValueError("This diagnostic cannot select a model")
    project_root = protocol_path.parents[2]
    data_root = resolve(project_root, str(protocol["data_root"]))
    for name, specification in protocol["locked_inputs"].items():
        path = resolve(project_root, str(specification["path"]))
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != str(specification["sha256"]):
            raise ValueError(f"Locked input changed: {name}")
    expected_source = str(protocol["accepted_control"]["source_tree_sha256"])
    if source_tree_sha256() != expected_source:
        raise ValueError("Runtime source tree changed")

    manifest_path = resolve(project_root, str(protocol["dataset"]["manifest"]["path"]))
    if sha256(manifest_path) != str(protocol["dataset"]["manifest"]["sha256"]):
        raise ValueError("Diagnostic manifest changed")
    records = validate_manifest(manifest_path, protocol["dataset"])
    if mask_tree_sha256(records, data_root) != str(protocol["dataset"]["mask_tree_sha256"]):
        raise ValueError("Partial-mask tree changed")
    if image_tree_sha256(records, data_root) != str(protocol["dataset"]["image_tree_sha256"]):
        raise ValueError("Diagnostic image tree changed")

    control = protocol["accepted_control"]
    run_root = resolve(project_root, str(control["run_root"]))
    seeds = [int(seed) for seed in control["seeds"]]
    if len(seeds) < 3 or len(seeds) != len(set(seeds)):
        raise ValueError("At least three unique accepted-control seeds are required")
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        run_dir = run_root / f"seed_{seed}"
        locks = control["seed_locks"][str(seed)]
        artifacts = {
            "checkpoint": run_dir / str(control["checkpoint"]),
            "summary": run_dir / "summary.json",
            "config": run_dir / "config.resolved.json",
            "history": run_dir / "history.jsonl",
        }
        for name, path in artifacts.items():
            if sha256(path) != str(locks[f"{name}_sha256"]):
                raise ValueError(f"Accepted seed {seed} {name} changed")
        summary = load_json(artifacts["summary"])
        if summary.get("source_tree_sha256") != expected_source:
            raise ValueError(f"Accepted seed {seed} source provenance changed")
        result = evaluate_run(
            artifacts["checkpoint"],
            records,
            manifest_path,
            data_root,
            arguments.workers,
            int(protocol["dataset"].get("probability_histogram_bins", 1024)),
        )
        result["seed"] = seed
        runs.append(result)

    aggregate: dict[str, Any] = {}
    for mode in PREDICTION_MODES:
        aggregate[mode] = {
            metric: {
                "mean": statistics.fmean(float(run["metrics"][mode][metric]) for run in runs),
                "std": statistics.pstdev(float(run["metrics"][mode][metric]) for run in runs),
                "min": min(float(run["metrics"][mode][metric]) for run in runs),
                "max": max(float(run["metrics"][mode][metric]) for run in runs),
            }
            for metric in ("iou", "precision", "recall", "f1", "specificity")
        }
    ranking = {
        metric: {
            "mean": statistics.fmean(float(run["weed_probability_ranking"][metric]) for run in runs),
            "std": statistics.pstdev(float(run["weed_probability_ranking"][metric]) for run in runs),
        }
        for metric in ("approx_average_precision", "approx_auroc")
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "real_weedy_rice_binary_external_diagnostic",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "source_tree_sha256": expected_source,
        "seeds": seeds,
        "runs": runs,
        "aggregate": aggregate,
        "weed_probability_ranking": ranking,
        "external_test_used": False,
        "model_selection_used": False,
        "training_exposure": False,
        "claim_scope": "two-location-four-flight-binary-weedy-rice-development-only",
    }
    output = resolve(project_root, str(protocol["outputs"]["receipt"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
