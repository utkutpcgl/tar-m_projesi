#!/usr/bin/env python3
"""Evaluate simple deployable spray-point priors on unseen PhenoBench plots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from scripts.analyze_phenobench_actionable_size_v1 import evaluate_policy
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    infer_actions,
    load_ground_truth,
    release_cuda,
    sha256,
)
from scripts.run_phenobench_segment_overfit_gate_v1 import _sized_actions


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def confidence_grid(config: Mapping[str, Any]) -> list[float]:
    start, stop, step = (float(config[key]) for key in ("start", "stop", "step"))
    if step <= 0 or stop < start:
        raise ValueError("Invalid confidence grid")
    return [
        round(start + index * step, 10)
        for index in range(int(round((stop - start) / step)) + 1)
    ]


def select_action_policies(
    actions_by_sample: Mapping[str, Sequence[Any]],
    records: Sequence[GroundTruth],
    *,
    thresholds: Sequence[float],
    minimum_gt_size_px: float,
    maximum_crop_collision_rate: float,
) -> dict[str, Any]:
    sized = _sized_actions(actions_by_sample)
    candidates = [
        evaluate_policy(
            sized,
            records,
            confidence_threshold=threshold,
            minimum_gt_size_px=minimum_gt_size_px,
            minimum_prediction_size_px=0,
        )
        for threshold in thresholds
    ]
    max_f1 = max(
        candidates,
        key=lambda item: (
            float(item["f1"]),
            -float(item["crop_collision_rate_per_attempt"]),
            float(item["precision"]),
            float(item["recall"]),
            float(item["policy"]["confidence_threshold"]),
        ),
    )
    safe_candidates = [
        item
        for item in candidates
        if int(item["attempted_actions"]) > 0
        and float(item["crop_collision_rate_per_attempt"])
        <= maximum_crop_collision_rate
    ]
    safety = (
        max(
            safe_candidates,
            key=lambda item: (
                float(item["f1"]),
                float(item["recall"]),
                float(item["precision"]),
                float(item["policy"]["confidence_threshold"]),
            ),
        )
        if safe_candidates
        else None
    )
    return {"max_f1": max_f1, "crop_safe_max_f1": safety}


def _apply_selected(
    selected: Mapping[str, Any] | None,
    actions_by_sample: Mapping[str, Sequence[Any]],
    records: Sequence[GroundTruth],
    minimum_size: float,
) -> dict[str, Any] | None:
    if selected is None:
        return None
    return evaluate_policy(
        _sized_actions(actions_by_sample),
        records,
        confidence_threshold=float(selected["policy"]["confidence_threshold"]),
        minimum_gt_size_px=minimum_size,
        minimum_prediction_size_px=0,
    )


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO

    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    evaluation_config = _resolve(project_root, config["source_evaluation_config"])
    receipt_path = _resolve(data_root, config["dataset_receipt"])
    checkpoint = _resolve(data_root, config["checkpoint"])
    for path, expected in (
        (evaluation_config, config["source_evaluation_config_sha256"]),
        (receipt_path, config["dataset_receipt_sha256"]),
        (checkpoint, config["checkpoint_sha256"]),
    ):
        if not path.is_file() or sha256(path) != str(expected):
            raise ValueError(f"Locked input mismatch: {path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    membership = Path(receipt["provenance"]["membership"])
    if sha256(membership) != str(receipt["provenance"]["membership_sha256"]):
        raise ValueError("Membership hash mismatch")
    minimum_area = int(receipt["label_contract"]["minimum_full_instance_area_px"])
    validation = load_ground_truth(membership, "val", minimum_area)
    test = load_ground_truth(membership, "test", minimum_area)
    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)

    model = YOLO(str(checkpoint))
    validation_actions, validation_timing = infer_actions(
        model, "segment", validation, config["inference"]
    )
    release_cuda(model)
    thresholds = confidence_grid(config["confidence_threshold"])
    minimum_size = float(config["minimum_actionable_gt_size_px"])
    maximum_crop = float(
        config["safety_policy"]["maximum_crop_collision_rate_per_attempt"]
    )
    methods = [str(method) for method in config["methods"]]
    selection: dict[str, Any] = {}
    for method in methods:
        if method not in validation_actions:
            raise ValueError(f"Inference method missing: {method}")
        selection[method] = select_action_policies(
            validation_actions[method],
            validation,
            thresholds=thresholds,
            minimum_gt_size_px=minimum_size,
            maximum_crop_collision_rate=maximum_crop,
        )
    selection_path = output / "validation_selected_policies.json"
    selection_path.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    model = YOLO(str(checkpoint))
    test_actions, test_timing = infer_actions(
        model, "segment", test, config["inference"]
    )
    release_cuda(model)
    test_results: dict[str, Any] = {}
    for method in methods:
        test_results[method] = {
            policy_name: _apply_selected(
                selected_policy,
                test_actions[method],
                test,
                minimum_size,
            )
            for policy_name, selected_policy in selection[method].items()
        }
    baseline = test_results["segment_deepest_interior"]["max_f1"]
    comparisons = {
        method: {
            "f1_delta_vs_deepest": (
                float(results["max_f1"]["f1"]) - float(baseline["f1"])
            ),
            "recall_delta_vs_deepest": (
                float(results["max_f1"]["recall"]) - float(baseline["recall"])
            ),
            "precision_delta_vs_deepest": (
                float(results["max_f1"]["precision"]) - float(baseline["precision"])
            ),
        }
        for method, results in test_results.items()
    }
    metrics = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "posthoc_unseen_plot_action_policy_diagnostic_complete",
        "interpretation": "spatially unseen PhenoBench plots; test was opened before this diagnostic and is not untouched deployment evidence",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "minimum_actionable_gt_size_px": minimum_size,
        "records": {"validation_images": len(validation), "test_images": len(test)},
        "validation_selected_policies": selection,
        "validation_selected_policies_sha256_before_test": sha256(selection_path),
        "test_results": test_results,
        "test_max_f1_comparisons": comparisons,
        "timing": {"validation": validation_timing, "test": test_timing},
        "claims": config["claims"],
    }
    metrics_path = output / "action_policy_prior_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_action_policy_priors_v1.yaml"),
    )
    arguments = parser.parse_args()
    metrics = run(arguments.config)
    print(json.dumps(metrics["test_results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
