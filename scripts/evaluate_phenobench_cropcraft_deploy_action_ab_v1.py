#!/usr/bin/env python3
"""Evaluate base/control/synthetic segmenters on exact weed action contact."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    Action,
    GroundTruth,
    evaluate_actions,
    infer_actions,
    load_ground_truth,
    release_cuda,
    select_threshold,
    sha256,
    threshold_curve,
)


METHODS = (
    "segment_deepest_interior",
    "segment_max_excess_green",
    "segment_crop_safe_excess_green",
)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def eligibility_view(
    records: Sequence[GroundTruth],
    actions_by_sample: Mapping[str, Sequence[Action]],
    minimum_size_px: float,
) -> tuple[list[GroundTruth], dict[str, list[Action]]]:
    if minimum_size_px < 0:
        raise ValueError("Minimum eligible size cannot be negative")
    eligible_by_sample: dict[str, set[int]] = {}
    filtered_records: list[GroundTruth] = []
    for record in records:
        weed_sizes = {
            int(instance_id): float(size)
            for instance_id, size in record.weed_sizes.items()
            if float(size) >= minimum_size_px
        }
        eligible_by_sample[record.sample_id] = set(weed_sizes)
        filtered_records.append(replace(record, weed_sizes=weed_sizes))
    filtered_actions: dict[str, list[Action]] = {}
    for sample_id, actions in actions_by_sample.items():
        eligible = eligible_by_sample[sample_id]
        filtered_actions[sample_id] = [
            replace(action, target_kind="ignore")
            if action.target_kind == "weed"
            and int(action.target_instance_id) not in eligible
            else action
            for action in actions
        ]
    return filtered_records, filtered_actions


def paired_bootstrap_difference(
    control: Mapping[str, Mapping[str, Any]],
    challenger: Mapping[str, Mapping[str, Any]],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    sample_ids = sorted(set(control) & set(challenger))
    if not sample_ids:
        raise ValueError("No paired samples")
    keys = ("tp", "fp", "fn")
    left = np.asarray([[control[sample][key] for key in keys] for sample in sample_ids], dtype=np.float64)
    right = np.asarray([[challenger[sample][key] for key in keys] for sample in sample_ids], dtype=np.float64)

    def f1(rows: np.ndarray) -> float:
        tp, fp, fn = rows.sum(axis=0)
        denominator = 2.0 * tp + fp + fn
        return float(2.0 * tp / denominator) if denominator else 0.0

    rng = np.random.default_rng(seed)
    differences = np.empty(iterations, dtype=np.float64)
    for index in range(iterations):
        draw = rng.integers(0, len(sample_ids), len(sample_ids))
        differences[index] = f1(right[draw]) - f1(left[draw])
    return {
        "definition": "challenger_real_synthetic F1 minus control_real_replay F1",
        "iterations": iterations,
        "seed": seed,
        "median_difference": float(np.median(differences)),
        "ci95": [float(np.percentile(differences, 2.5)), float(np.percentile(differences, 97.5))],
        "probability_challenger_higher": float(np.mean(differences > 0.0)),
    }


def evaluate_model(
    model: Any,
    val_records: Sequence[GroundTruth],
    test_records: Sequence[GroundTruth],
    inference: Mapping[str, Any],
    thresholds: np.ndarray,
    size_thresholds: Sequence[float],
    primary_method: str,
    primary_size: float,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    val_actions, val_timing = infer_actions(model, "segment", val_records, inference)
    release_cuda(model)
    test_actions, test_timing = infer_actions(model, "segment", test_records, inference)
    release_cuda(model)
    output: dict[str, Any] = {"timing": {"validation": val_timing, "test": test_timing}, "methods": {}}
    primary_per_sample: dict[str, dict[str, Any]] = {}
    for method in METHODS:
        size_rows: dict[str, Any] = {}
        for minimum in size_thresholds:
            val_view, val_action_view = eligibility_view(val_records, val_actions[method], minimum)
            test_view, test_action_view = eligibility_view(test_records, test_actions[method], minimum)
            selection = select_threshold(threshold_curve(val_action_view, val_view, thresholds))
            threshold = float(selection["balanced_max_f1"]["threshold"])
            val_metric = evaluate_actions(val_action_view, val_view, threshold)
            test_metric = evaluate_actions(
                test_action_view,
                test_view,
                threshold,
                include_per_sample=True,
            )
            size_rows[str(int(minimum))] = {
                "minimum_sqrt_gt_box_area_px": float(minimum),
                "validation_calibration": selection,
                "validation": val_metric,
                "test": {key: value for key, value in test_metric.items() if key != "per_sample"},
            }
            if method == primary_method and float(minimum) == primary_size:
                primary_per_sample = test_metric["per_sample"]
        output["methods"][method] = {"eligible_size_views": size_rows}
    return output, primary_per_sample


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update({"clearml": False, "comet": False, "dvc": False, "hub": False, "mlflow": False, "neptune": False, "wandb": False})
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = resolve(project_root, config["data_root"])
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    receipt_path = resolve(data_root, config["dataset_receipt"])
    dataset_yaml = resolve(data_root, config["dataset_yaml"])
    if sha256(receipt_path) != str(config["dataset_receipt_sha256"]):
        raise ValueError("Dataset receipt hash mismatch")
    if sha256(dataset_yaml) != str(config["dataset_yaml_sha256"]):
        raise ValueError("Dataset YAML hash mismatch")
    dataset_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    membership = Path(dataset_receipt["provenance"]["membership"])
    if sha256(membership) != dataset_receipt["provenance"]["membership_sha256"]:
        raise ValueError("Membership hash mismatch")
    minimum_area = int(dataset_receipt["label_contract"]["minimum_full_instance_area_px"])
    val_records = load_ground_truth(membership, "val", minimum_area)
    test_records = load_ground_truth(membership, "test", minimum_area)
    thresholds = np.arange(
        float(config["thresholds"]["start"]),
        float(config["thresholds"]["stop"]) + 1e-9,
        float(config["thresholds"]["step"]),
    )
    size_thresholds = [float(value) for value in config["eligible_minimum_sqrt_box_px"]]
    primary_method = str(config["primary_method"])
    primary_size = float(config["primary_service_minimum_sqrt_box_px"])
    if primary_method not in METHODS or primary_size not in size_thresholds:
        raise ValueError("Primary method/size is absent from the evaluation grid")
    results: dict[str, Any] = {}
    primary: dict[str, dict[str, Any]] = {}
    locked_models: dict[str, Any] = {}
    for name, model_cfg in config["models"].items():
        checkpoint = resolve(data_root, model_cfg["checkpoint"])
        if not checkpoint.is_file() or sha256(checkpoint) != str(model_cfg["checkpoint_sha256"]):
            raise ValueError(f"Locked checkpoint mismatch: {name}")
        model = YOLO(str(checkpoint))
        if model.task != "segment":
            raise ValueError(f"Checkpoint is not segmentation: {name}")
        results[name], primary[name] = evaluate_model(
            model,
            val_records,
            test_records,
            config["inference"],
            thresholds,
            size_thresholds,
            primary_method,
            primary_size,
        )
        locked_models[name] = {"checkpoint": str(checkpoint), "sha256": sha256(checkpoint)}
    bootstrap_cfg = config["bootstrap"]
    bootstrap = paired_bootstrap_difference(
        primary["control_real_replay"],
        primary["challenger_real_synthetic"],
        iterations=int(bootstrap_cfg["iterations"]),
        seed=int(bootstrap_cfg["seed"]),
    )
    bootstrap["primary_method"] = primary_method
    bootstrap["minimum_sqrt_gt_box_area_px"] = primary_size
    output = resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "paired_real_action_ab_complete_development_evidence_not_deploy_proof",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_receipt": str(receipt_path),
        "dataset_receipt_sha256": sha256(receipt_path),
        "locked_models": locked_models,
        "eligibility_contract": {
            "size_definition": "sqrt of exact GT weed bounding-box area at native 1024 raster",
            "views_px": size_thresholds,
            "smaller_weed_actions": "ignored as optional opportunities, not counted false positive",
            "physical_mm_equivalence": False,
        },
        "results": results,
        "primary_service": {
            "method": primary_method,
            "minimum_sqrt_gt_box_area_px": primary_size,
            "physical_mm_equivalence_on_phenobench": False,
        },
        "paired_bootstrap_at_primary_service": bootstrap,
        "claims": config["claims"],
        "limitations": [
            "PhenoBench is UAV sugar-beet imagery, not the hooded robot-camera deployment distribution.",
            "The test plots were consumed by earlier development and are not a fresh final holdout.",
            "Eligibility uses GT size for analysis; deploy suppression would need predicted size and calibrated GSD.",
            "One seed measures direction, not variance.",
        ],
    }
    metrics_path = output / "action_ab_metrics.json"
    metrics_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "output": str(metrics_path), "bootstrap": bootstrap}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_cropcraft_deploy_action_ab_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
