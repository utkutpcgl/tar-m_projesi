#!/usr/bin/env python3
"""Compare base, source-extra, and target-plot adaptation on common plots."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from scripts.analyze_phenobench_action_policy_priors_v1 import (
    _apply_selected,
    confidence_grid,
    select_action_policies,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    infer_actions,
    load_ground_truth,
    release_cuda,
    sha256,
)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_plot_groups(membership: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for line in membership.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        output[str(row["sample_id"])] = str(row["plot_group"])
    return output


def filter_plot_groups(
    records: Sequence[GroundTruth],
    group_by_sample: Mapping[str, str],
    allowed_groups: Sequence[str],
) -> list[GroundTruth]:
    allowed = {str(group) for group in allowed_groups}
    selected = [
        record
        for record in records
        if group_by_sample.get(record.sample_id) in allowed
    ]
    observed = {group_by_sample[record.sample_id] for record in selected}
    if observed != allowed:
        raise ValueError(f"Missing plot groups: {sorted(allowed - observed)}")
    return selected


def _metric_brief(metric: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: metric[key]
        for key in (
            "precision",
            "recall",
            "f1",
            "crop_collision_rate_per_attempt",
            "tp",
            "fp",
            "fn",
            "crop_collision",
        )
    }


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO

    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    receipt_path = _resolve(data_root, config["dataset_receipt"])
    if (
        not receipt_path.is_file()
        or sha256(receipt_path) != str(config["dataset_receipt_sha256"])
    ):
        raise ValueError("Dataset receipt mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    membership = Path(receipt["provenance"]["membership"])
    if sha256(membership) != str(receipt["provenance"]["membership_sha256"]):
        raise ValueError("Membership mismatch")
    minimum_area = int(receipt["label_contract"]["minimum_full_instance_area_px"])
    group_by_sample = load_plot_groups(membership)
    calibration = filter_plot_groups(
        load_ground_truth(membership, "val", minimum_area),
        group_by_sample,
        config["calibration_plot_groups"],
    )
    test = filter_plot_groups(
        load_ground_truth(membership, "test", minimum_area),
        group_by_sample,
        config["test_plot_groups"],
    )
    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    methods = [str(method) for method in config["methods"]]
    minimum_size = float(config["minimum_actionable_gt_size_px"])
    thresholds = confidence_grid(config["confidence_threshold"])
    maximum_crop = float(
        config["safety_policy"]["maximum_crop_collision_rate_per_attempt"]
    )

    checkpoints: dict[str, Path] = {}
    selection: dict[str, Any] = {}
    timing: dict[str, Any] = {"calibration": {}, "test": {}}
    for model_name, model_config in config["models"].items():
        checkpoint = _resolve(data_root, model_config["checkpoint"])
        if (
            not checkpoint.is_file()
            or sha256(checkpoint) != str(model_config["checkpoint_sha256"])
        ):
            raise ValueError(f"Checkpoint mismatch: {model_name}")
        checkpoints[str(model_name)] = checkpoint
        model = YOLO(str(checkpoint))
        actions, model_timing = infer_actions(
            model, "segment", calibration, config["inference"]
        )
        timing["calibration"][str(model_name)] = model_timing
        selection[str(model_name)] = {
            method: select_action_policies(
                actions[method],
                calibration,
                thresholds=thresholds,
                minimum_gt_size_px=minimum_size,
                maximum_crop_collision_rate=maximum_crop,
            )
            for method in methods
        }
        release_cuda(model)
        del model, actions
        gc.collect()
    selection_path = output / "common_calibration_selected_policies.json"
    selection_path.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    test_results: dict[str, Any] = {}
    for model_name, checkpoint in checkpoints.items():
        model = YOLO(str(checkpoint))
        actions, model_timing = infer_actions(
            model, "segment", test, config["inference"]
        )
        timing["test"][model_name] = model_timing
        test_results[model_name] = {
            method: {
                policy_name: _apply_selected(
                    selected_policy,
                    actions[method],
                    test,
                    minimum_size,
                )
                for policy_name, selected_policy in selection[model_name][method].items()
            }
            for method in methods
        }
        release_cuda(model)
        del model, actions
        gc.collect()

    primary_method = str(config["primary_method"])
    primary = {
        model_name: results[primary_method]["max_f1"]
        for model_name, results in test_results.items()
    }
    base = primary["base"]
    comparisons = {
        model_name: {
            "metric": _metric_brief(metric),
            "f1_delta_vs_base": float(metric["f1"]) - float(base["f1"]),
            "precision_delta_vs_base": float(metric["precision"])
            - float(base["precision"]),
            "recall_delta_vs_base": float(metric["recall"])
            - float(base["recall"]),
        }
        for model_name, metric in primary.items()
    }
    metrics = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "posthoc_common_plot_domain_adaptation_comparison_complete",
        "interpretation": "directional target-adaptation diagnostic; not a perfectly controlled or untouched deployment claim",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "records": {
            "calibration_images": len(calibration),
            "test_images": len(test),
            "minimum_actionable_gt_size_px": minimum_size,
        },
        "models": config["models"],
        "common_calibration_selection": selection,
        "common_calibration_selection_sha256_before_test": sha256(selection_path),
        "test_results": test_results,
        "primary_method": primary_method,
        "primary_max_f1_comparison": comparisons,
        "timing": timing,
        "claims": config["claims"],
    }
    metrics_path = output / "domain_adaptation_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_domain_adaptation_comparison_v1.yaml"),
    )
    arguments = parser.parse_args()
    metrics = run(arguments.config)
    print(json.dumps(metrics["primary_max_f1_comparison"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
