#!/usr/bin/env python3
"""Run frozen real action evaluation and fixed-threshold external diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_phenobench_cropcraft_deploy_action_ab_v1 import (
    METHODS,
    eligibility_view,
    evaluate_model as evaluate_phenobench_model,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    evaluate_actions,
    evaluate_segment_tissue,
    infer_actions,
    load_ground_truth,
    release_cuda,
    sha256,
)
from scripts.evaluate_sugarbeets2016_yolo_segment_external_v1 import (
    evaluate_model as evaluate_external_model,
)


MODEL_NAMES = ("current_best_real_synthetic", "challenger_real_robot_native")


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _lock(path: Path, expected: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Locked input mismatch: {path}")


def wilson_upper(successes: int, trials: int, z: float = 1.959963984540054) -> float | None:
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError("Invalid binomial counts")
    if trials == 0:
        return None
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = proportion + z2 / (2.0 * trials)
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z2 / (4.0 * trials * trials)
    )
    return (centre + radius) / denominator


def with_crop_safety(metric: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(metric)
    result["crop_collision_wilson_upper_95"] = wilson_upper(
        int(metric["crop_collision"]), int(metric["attempted_actions"])
    )
    return result


def paired_bootstrap_difference(
    current: Mapping[str, Mapping[str, Any]],
    challenger: Mapping[str, Mapping[str, Any]],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    sample_ids = sorted(set(current) & set(challenger))
    if not sample_ids:
        raise ValueError("No paired samples")
    keys = ("tp", "fp", "fn")
    left = np.asarray(
        [[current[sample][key] for key in keys] for sample in sample_ids],
        dtype=np.float64,
    )
    right = np.asarray(
        [[challenger[sample][key] for key in keys] for sample in sample_ids],
        dtype=np.float64,
    )

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
        "definition": "challenger_real_robot_native F1 minus current_best_real_synthetic F1",
        "paired_samples": len(sample_ids),
        "iterations": iterations,
        "seed": seed,
        "median_difference": float(np.median(differences)),
        "ci95": [
            float(np.percentile(differences, 2.5)),
            float(np.percentile(differences, 97.5)),
        ],
        "probability_challenger_higher": float(np.mean(differences > 0.0)),
    }


def fixed_threshold(
    phenobench: Mapping[str, Any], model_name: str, method: str, minimum_size: float
) -> float:
    return float(
        phenobench["results"][model_name]["methods"][method]["eligible_size_views"]
        [str(int(minimum_size))]["validation_calibration"]["balanced_max_f1"]
        ["threshold"]
    )


def normalize_threshold_size_map(
    size_views: Sequence[float],
    source_views: Sequence[float],
    raw_map: Mapping[str, Any],
) -> dict[str, float]:
    expected = {str(int(size)) for size in size_views}
    if set(raw_map) != expected:
        raise ValueError("Threshold size map does not exactly cover the target size views")
    normalized = {key: float(raw_map[key]) for key in expected}
    if any(source not in source_views for source in normalized.values()):
        raise ValueError("Threshold size map references a missing PhenoBench calibration view")
    return normalized


def evaluate_fixed_panel(
    model: Any,
    records: Sequence[GroundTruth],
    inference: Mapping[str, Any],
    phenobench: Mapping[str, Any],
    model_name: str,
    size_views: Sequence[float],
    threshold_size_map: Mapping[str, float],
    primary_method: str,
    primary_size: float,
) -> dict[str, Any]:
    actions, timing = infer_actions(model, "segment", records, inference)
    output: dict[str, Any] = {"timing": timing, "methods": {}}
    primary_records: list[GroundTruth] | None = None
    primary_threshold: float | None = None
    for method in METHODS:
        views: dict[str, Any] = {}
        for minimum in size_views:
            record_view, action_view = eligibility_view(records, actions[method], minimum)
            threshold_source_size = threshold_size_map[str(int(minimum))]
            threshold = fixed_threshold(
                phenobench, model_name, method, threshold_source_size
            )
            metric = evaluate_actions(
                action_view, record_view, threshold, include_per_sample=True
            )
            metric = with_crop_safety(metric)
            views[str(int(minimum))] = {
                "minimum_sqrt_gt_box_area_px": float(minimum),
                "fixed_threshold": threshold,
                "threshold_source": "same model's frozen PhenoBench validation action calibration",
                "threshold_source_minimum_sqrt_gt_box_area_px": threshold_source_size,
                "test": metric,
            }
            if method == primary_method and float(minimum) == primary_size:
                primary_records = record_view
                primary_threshold = threshold
        output["methods"][method] = {"eligible_size_views": views}
    if primary_records is None or primary_threshold is None:
        raise ValueError("Primary service view is absent")
    output["primary_service"] = {
        "method": primary_method,
        "minimum_sqrt_gt_box_area_px": primary_size,
        "fixed_threshold": primary_threshold,
        "tissue": evaluate_segment_tissue(
            model, primary_records, primary_threshold, inference
        ),
    }
    release_cuda(model)
    return output


def primary_metric(
    panel: Mapping[str, Any], model_name: str, method: str, size: float
) -> dict[str, Any]:
    return dict(
        panel["results"][model_name]["methods"][method]["eligible_size_views"]
        [str(int(size))]["test"]
    )


def pre_real_decision(
    current_pheno: Mapping[str, Any],
    candidate_pheno: Mapping[str, Any],
    current_bonirob: Mapping[str, Any],
    candidate_bonirob: Mapping[str, Any],
    rules: Mapping[str, Any],
    field_gate: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "phenobench_f1_noninferior": float(candidate_pheno["f1"])
        >= float(current_pheno["f1"])
        - float(rules["phenobench_f1_maximum_regression"]),
        "phenobench_crop_hit_not_materially_worse": float(
            candidate_pheno["crop_collision_rate_per_attempt"]
        )
        <= float(current_pheno["crop_collision_rate_per_attempt"])
        + float(rules["phenobench_crop_hit_maximum_absolute_increase"]),
        "bonirob_f1_material_gain": float(candidate_bonirob["f1"])
        >= float(current_bonirob["f1"])
        + float(rules["bonirob_f1_minimum_absolute_gain"]),
        "bonirob_crop_hit_not_worse": float(
            candidate_bonirob["crop_collision_rate_per_attempt"]
        )
        <= float(current_bonirob["crop_collision_rate_per_attempt"])
        + float(rules["bonirob_crop_hit_maximum_absolute_increase"]),
    }
    upper = candidate_bonirob.get("crop_collision_wilson_upper_95")
    go_checks = {
        "bonirob_precision": float(candidate_bonirob["precision"])
        >= float(field_gate["precision_minimum"]),
        "bonirob_recall": float(candidate_bonirob["recall"])
        >= float(field_gate["recall_minimum"]),
        "bonirob_f1": float(candidate_bonirob["f1"])
        >= float(field_gate["f1_minimum"]),
        "bonirob_crop_hit_rate": float(candidate_bonirob["crop_collision_rate_per_attempt"])
        <= float(field_gate["crop_hit_rate_maximum"]),
        "bonirob_crop_hit_upper_95": upper is not None
        and float(upper) <= float(field_gate["crop_hit_upper_95_maximum"]),
    }
    displaced = all(checks.values())
    numeric_field_gate_passed = all(go_checks.values())
    return {
        "synthetic_score_used": False,
        "candidate_displaces_current_pre_real_best": displaced,
        "selected_pre_real_model": (
            "challenger_real_robot_native" if displaced else "current_best_real_synthetic"
        ),
        "selection_checks": checks,
        "numeric_public_panel_gate_passed": numeric_field_gate_passed,
        "field_fire_go": False,
        "field_gate_checks": {
            **go_checks,
            "independent_own_rig_field_test": False,
        },
        "field_fire_blocker": "No independent own-rig field/session test exists; public development panels cannot authorize spraying.",
    }


def _metrics_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    keys = (
        "tp",
        "fp",
        "fn",
        "precision",
        "recall",
        "f1",
        "attempted_actions",
        "crop_collision",
        "crop_collision_rate_per_attempt",
    )
    for key in keys:
        a, b = left[key], right[key]
        if isinstance(a, float) or isinstance(b, float):
            if not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12):
                return False
        elif a != b:
            return False
    return True


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {name: False for name in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb")}
    )
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(PROJECT_ROOT, config["data_root"])
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")

    pheno_cfg = config["phenobench"]
    pheno_receipt_path = resolve(data_root, pheno_cfg["dataset_receipt"])
    pheno_yaml = resolve(data_root, pheno_cfg["dataset_yaml"])
    bonirob_receipt_path = resolve(data_root, config["bonirob"]["frozen_panel_receipt"])
    synthetic_receipt_path = resolve(data_root, config["synthetic"]["dataset_receipt"])
    legacy_synthetic_path = resolve(data_root, config["synthetic"]["legacy_diagnostic"])
    baseline_pheno_path = resolve(data_root, config["baseline_evidence"]["phenobench_action"])
    baseline_bonirob_path = resolve(data_root, config["baseline_evidence"]["bonirob_action"])
    for path, expected in (
        (pheno_receipt_path, str(pheno_cfg["dataset_receipt_sha256"])),
        (pheno_yaml, str(pheno_cfg["dataset_yaml_sha256"])),
        (bonirob_receipt_path, str(config["bonirob"]["frozen_panel_receipt_sha256"])),
        (synthetic_receipt_path, str(config["synthetic"]["dataset_receipt_sha256"])),
        (legacy_synthetic_path, str(config["synthetic"]["legacy_diagnostic_sha256"])),
        (baseline_pheno_path, str(config["baseline_evidence"]["phenobench_action_sha256"])),
        (baseline_bonirob_path, str(config["baseline_evidence"]["bonirob_action_sha256"])),
    ):
        _lock(path, expected)

    pheno_receipt = json.loads(pheno_receipt_path.read_text(encoding="utf-8"))
    pheno_membership = Path(pheno_receipt["provenance"]["membership"])
    _lock(pheno_membership, str(pheno_receipt["provenance"]["membership_sha256"]))
    pheno_minimum_area = int(pheno_receipt["label_contract"]["minimum_full_instance_area_px"])
    pheno_val = load_ground_truth(pheno_membership, "val", pheno_minimum_area)
    pheno_test = load_ground_truth(pheno_membership, "test", pheno_minimum_area)

    bonirob_receipt = json.loads(bonirob_receipt_path.read_text(encoding="utf-8"))
    if int(bonirob_receipt["frames"]) != int(config["bonirob"]["expected_frames"]):
        raise RuntimeError("BoniRob frame count drift")
    bonirob_membership = Path(bonirob_receipt["membership"])
    _lock(bonirob_membership, str(bonirob_receipt["membership_sha256"]))
    bonirob_records = load_ground_truth(
        bonirob_membership, "test", int(config["bonirob"]["minimum_component_area_px"])
    )

    synthetic_receipt = json.loads(synthetic_receipt_path.read_text(encoding="utf-8"))
    if synthetic_receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError("V12 synthetic release gate did not pass")
    if float(synthetic_receipt["evaluation_policy"]["real_model_selection_score_weight"]) != 0.0:
        raise RuntimeError("Synthetic real model-selection weight changed")
    synthetic_membership = Path(synthetic_receipt["membership"])
    _lock(synthetic_membership, str(synthetic_receipt["membership_sha256"]))
    synthetic_records = load_ground_truth(
        synthetic_membership,
        "test",
        int(synthetic_receipt["label_contract"]["minimum_component_area_px"]),
    )

    threshold_cfg = config["thresholds"]
    thresholds = np.arange(
        float(threshold_cfg["start"]),
        float(threshold_cfg["stop"]) + 1e-9,
        float(threshold_cfg["step"]),
    )
    primary_method = str(config["primary_method"])
    primary_size = float(config["primary_service_minimum_sqrt_box_px"])
    pheno_sizes = [float(value) for value in pheno_cfg["size_views_px"]]
    bonirob_sizes = [float(value) for value in config["bonirob"]["size_views_px"]]
    synthetic_sizes = [float(value) for value in config["synthetic"]["size_views_px"]]
    if primary_method not in METHODS or not all(
        primary_size in sizes for sizes in (pheno_sizes, bonirob_sizes, synthetic_sizes)
    ):
        raise ValueError("Primary method/size is absent from one or more panels")
    synthetic_threshold_size_map = normalize_threshold_size_map(
        synthetic_sizes,
        pheno_sizes,
        config["synthetic"]["phenobench_threshold_size_map"],
    )
    if synthetic_threshold_size_map[str(int(primary_size))] != primary_size:
        raise ValueError("Primary synthetic diagnostic must use the matching PhenoBench view")

    models: dict[str, Any] = {}
    locked_models: dict[str, Any] = {}
    for name in MODEL_NAMES:
        model_cfg = config["models"][name]
        checkpoint = resolve(data_root, model_cfg["checkpoint"])
        _lock(checkpoint, str(model_cfg["checkpoint_sha256"]))
        model = YOLO(str(checkpoint))
        if model.task != "segment":
            raise ValueError(f"Checkpoint is not segmentation: {name}")
        models[name] = model
        locked_models[name] = {"checkpoint": str(checkpoint), "sha256": sha256(checkpoint)}

    pheno_results: dict[str, Any] = {}
    pheno_primary_per_sample: dict[str, Any] = {}
    for name in MODEL_NAMES:
        pheno_results[name], pheno_primary_per_sample[name] = evaluate_phenobench_model(
            models[name],
            pheno_val,
            pheno_test,
            config["inference"],
            thresholds,
            pheno_sizes,
            primary_method,
            primary_size,
        )
        for method in METHODS:
            for minimum in pheno_sizes:
                row = pheno_results[name]["methods"][method]["eligible_size_views"][str(int(minimum))]
                row["test"] = with_crop_safety(row["test"])
    pheno_panel: dict[str, Any] = {"results": pheno_results}

    bonirob_results: dict[str, Any] = {}
    synthetic_results: dict[str, Any] = {}
    for name in MODEL_NAMES:
        bonirob_results[name] = evaluate_external_model(
            models[name],
            bonirob_records,
            config["inference"],
            pheno_panel,
            name,
            bonirob_sizes,
            primary_method,
            primary_size,
        )
        for method in METHODS:
            for minimum in bonirob_sizes:
                row = bonirob_results[name]["methods"][method]["eligible_size_views"][str(int(minimum))]
                row["test"] = with_crop_safety(row["test"])
        synthetic_results[name] = evaluate_fixed_panel(
            models[name],
            synthetic_records,
            config["inference"],
            pheno_panel,
            name,
            synthetic_sizes,
            synthetic_threshold_size_map,
            primary_method,
            primary_size,
        )
        release_cuda(models[name])

    pheno_panel.update(
        {
            "role": "frozen PhenoBench action development test; already opened",
            "size_views_px": pheno_sizes,
            "threshold_calibration": "same-model PhenoBench validation only",
        }
    )
    bonirob_panel: dict[str, Any] = {
        "role": "fixed-threshold external development panel; one field/session",
        "frames": len(bonirob_records),
        "size_views_px": bonirob_sizes,
        "results": bonirob_results,
    }
    synthetic_panel: dict[str, Any] = {
        "role": "fixed-PhenoBench-threshold diagnostic only",
        "frames": len(synthetic_records),
        "size_views_px": synthetic_sizes,
        "real_model_selection_score_weight": 0.0,
        "results": synthetic_results,
    }

    current_pheno = primary_metric(pheno_panel, MODEL_NAMES[0], primary_method, primary_size)
    candidate_pheno = primary_metric(pheno_panel, MODEL_NAMES[1], primary_method, primary_size)
    current_bonirob = primary_metric(bonirob_panel, MODEL_NAMES[0], primary_method, primary_size)
    candidate_bonirob = primary_metric(bonirob_panel, MODEL_NAMES[1], primary_method, primary_size)
    decision = pre_real_decision(
        current_pheno,
        candidate_pheno,
        current_bonirob,
        candidate_bonirob,
        config["pre_real_selection"],
        config["field_gate"],
    )
    bootstrap_cfg = config["bootstrap"]
    bootstrap = paired_bootstrap_difference(
        pheno_primary_per_sample[MODEL_NAMES[0]],
        pheno_primary_per_sample[MODEL_NAMES[1]],
        iterations=int(bootstrap_cfg["iterations"]),
        seed=int(bootstrap_cfg["seed"]),
    )
    bootstrap.update(
        {"primary_method": primary_method, "minimum_sqrt_gt_box_area_px": primary_size}
    )

    baseline_pheno = json.loads(baseline_pheno_path.read_text(encoding="utf-8"))
    baseline_bonirob = json.loads(baseline_bonirob_path.read_text(encoding="utf-8"))
    legacy_synthetic = json.loads(legacy_synthetic_path.read_text(encoding="utf-8"))
    old_pheno_metric = baseline_pheno["results"]["challenger_real_synthetic"]["methods"][primary_method]["eligible_size_views"][str(int(primary_size))]["test"]
    old_bonirob_metric = baseline_bonirob["results"]["challenger_real_synthetic"]["methods"][primary_method]["eligible_size_views"][str(int(primary_size))]["test"]
    reproduction = {
        "current_best_phenobench_matches_locked_baseline": _metrics_match(current_pheno, old_pheno_metric),
        "current_best_bonirob_matches_locked_baseline": _metrics_match(current_bonirob, old_bonirob_metric),
    }
    if not all(reproduction.values()):
        raise RuntimeError(f"Frozen baseline reproduction drift: {reproduction}")

    legacy_synthetic_row = legacy_synthetic["results"]["challenger_real_synthetic"]["1024"]["methods"][primary_method]["eligible_size_views"][str(int(primary_size))]
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "pre_real_data_ceiling_diagnostic_complete_no_field_go",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "locked_models": locked_models,
        "primary_service": {
            "method": primary_method,
            "minimum_sqrt_gt_box_area_px": primary_size,
            "physical_mm_equivalence_on_real_public_panels": False,
        },
        "phenobench": pheno_panel,
        "bonirob": bonirob_panel,
        "synthetic": synthetic_panel,
        "paired_bootstrap_phenobench_primary": bootstrap,
        "decision": decision,
        "baseline_reproduction": reproduction,
        "legacy_synthetic_context": {
            "threshold_source": "synthetic validation; not comparable to the stricter fixed-PhenoBench-threshold diagnostic",
            "test": legacy_synthetic_row["test"],
            "real_model_selection_score_weight": 0.0,
        },
        "claims": config["claims"],
        "limitations": [
            "PhenoBench test and BoniRob were consumed by earlier development and are not fresh final holdouts.",
            "BoniRob connected semantic regions are not publisher botanical instances and 283 adjacent frames are one correlated field/session.",
            "ROSE uses bean rather than sugar beet crop morphology; any gain combines viewpoint, appearance, content enrichment and native-detail cropping.",
            "The experiment is one seed and cannot quantify training variance.",
            "V12 synthetic scores have zero weight in both the pre-real winner and field GO decisions.",
        ],
    }
    output = resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    metrics_path = output / "diagnostics.json"
    metrics_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {
        "status": receipt["status"],
        "primary_service": receipt["primary_service"],
        "metrics": {
            "phenobench": {name: primary_metric(pheno_panel, name, primary_method, primary_size) for name in MODEL_NAMES},
            "bonirob": {name: primary_metric(bonirob_panel, name, primary_method, primary_size) for name in MODEL_NAMES},
            "synthetic_fixed_pheno_threshold": {name: primary_metric(synthetic_panel, name, primary_method, primary_size) for name in MODEL_NAMES},
        },
        "paired_bootstrap_phenobench_primary": bootstrap,
        "decision": decision,
        "baseline_reproduction": reproduction,
        "synthetic_score_used_in_real_decision": False,
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "summary": str(summary_path), "decision": decision}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/pre_real_data_ceiling_action_diagnostics_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
