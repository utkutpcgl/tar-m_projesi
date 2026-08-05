#!/usr/bin/env python3
"""Apply the frozen low-exposure V7-R2 uncertainty-mask screen."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from select_sensor_motion_additive import (
    aggregate,
    domain_points,
    load_json,
    load_yaml,
    sha256,
)


def validate_locked_inputs(protocol: dict[str, Any]) -> None:
    for name, lock in protocol["locked_inputs"].items():
        path = Path(str(lock["path"])).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != str(lock["sha256"]):
            raise ValueError(f"Locked input changed ({name}): {actual}")


def locked_json(protocol: dict[str, Any], name: str) -> dict[str, Any]:
    return load_json(Path(protocol["locked_inputs"][name]["path"]).resolve())


def clean_manifest_audit(audit: dict[str, Any], expected: int) -> bool:
    return int(audit.get("samples", -1)) == expected and all(
        int(audit.get(field, -1)) == 0
        for field in ("missing_files", "invalid_masks", "shape_mismatches")
    )


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    expected = protocol["expected_data_evidence"]
    asset = locked_json(protocol, "r2_asset_quality_audit")
    if asset.get("all_automatic_quality_gates_passed") is not True:
        raise ValueError("R2 automatic asset gate did not pass")
    if not asset.get("quality_gate_checks") or not all(
        bool(value) for value in asset["quality_gate_checks"].values()
    ):
        raise ValueError("R2 contains a failed automatic asset check")
    if asset.get("r2_rgb_byte_identical_to_r1") is not True:
        raise ValueError("R2 RGBs are not byte-identical to the leakage-audited R1")
    if asset.get("inherited_r1_real_duplicate_gate_passed") is not True:
        raise ValueError("R2 did not inherit a valid R1 real-duplicate gate")
    if int(asset.get("real_deblurweedseg_training_or_asset_exposure", -1)) != 0:
        raise ValueError("Real DeBlurWeedSeg data entered R2")
    aggregate_evidence = asset.get("aggregate", {})
    if int(aggregate_evidence.get("samples", -1)) != int(expected["samples"]):
        raise ValueError("Unexpected R2 asset sample count")
    if aggregate_evidence.get("split_counts") != {
        "external_calibration": int(expected["external_calibration"]),
        "train": int(expected["train"]),
    }:
        raise ValueError("Unexpected R2 role counts")
    if not math.isclose(
        float(aggregate_evidence.get("new_ignore_fraction", -1)),
        float(expected["new_ignore_fraction"]),
        abs_tol=1e-15,
    ):
        raise ValueError("Unexpected R2 uncertainty fraction")

    visual = locked_json(protocol, "r2_manual_visual_review")
    if visual.get("passed") is not True:
        raise ValueError("R2 manual visual review did not pass")
    manifest_audit = locked_json(protocol, "r2_manifest_audit")
    if not clean_manifest_audit(manifest_audit, int(expected["samples"])):
        raise ValueError("R2 manifest audit failed")
    inherited_duplicate = locked_json(protocol, "r1_vs_all_real_duplicate_audit")
    if inherited_duplicate.get("passed") is not True:
        raise ValueError("Inherited R1 duplicate gate failed")

    combined = locked_json(protocol, "challenger_manifest_receipt")
    if combined.get("source_scene_audit", {}).get("passed") is not True:
        raise ValueError("R2 challenger group-disjointness failed")
    role = combined.get("role_policy", {})
    if role.get("external_test_present") is not False:
        raise ValueError("R2 challenger contains an external test")
    if int(role.get("real_deblurweedseg_pixels_in_assets_or_training", -1)) != 0:
        raise ValueError("Real blur pixels entered R2 training")
    if int(combined.get("output", {}).get("samples", -1)) != int(
        expected["combined_training_manifest_samples"]
    ):
        raise ValueError("Unexpected R2 combined-manifest size")
    combined_audit = locked_json(protocol, "challenger_manifest_audit")
    if not clean_manifest_audit(
        combined_audit, int(expected["combined_training_manifest_samples"])
    ):
        raise ValueError("R2 combined-manifest audit failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_yaml(protocol_path)
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("R2 protocol was not frozen before training")
    if protocol.get("stage") != "screen":
        raise ValueError("This selector accepts only the R2 screen")
    validate_locked_inputs(protocol)
    validate_data_evidence(protocol)

    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_json(benchmark_path)
    matrix_path = Path(str(benchmark["matrix"])).resolve()
    matrix_lock = protocol["locked_inputs"]["screen_matrix"]
    if matrix_path != Path(str(matrix_lock["path"])).resolve():
        raise ValueError("Benchmark does not use the frozen R2 matrix")
    if sha256(matrix_path) != str(matrix_lock["sha256"]):
        raise ValueError("R2 matrix changed after freeze")

    seed = int(protocol["screen_seed"])
    control = str(protocol["accepted_control"])
    challenger = str(protocol["screen_candidate"])
    expected_names = {control, challenger}
    indexed_benchmark = {
        str(run["candidate"]): run
        for run in benchmark["runs"]
        if str(run["candidate"]) in expected_names and int(run["seed"]) == seed
    }
    if set(indexed_benchmark) != expected_names:
        raise ValueError("R2 benchmark is missing an expected arm")

    expected_source = str(protocol["source_tree_sha256"])
    expected_exposures = {
        str(key): float(value)
        for key, value in protocol["candidate_sensor_motion_exposure"].items()
    }
    expected_samples = {
        str(key): int(value)
        for key, value in protocol["candidate_samples_per_epoch"].items()
    }
    expected_evaluator_hashes = {
        str(key): str(value)
        for key, value in protocol["evaluation_receipt_script_sha256"].items()
    }
    evaluations: dict[str, dict[str, Any]] = {}
    receipt_locks: dict[str, dict[str, str]] = {}
    for name in (control, challenger):
        run_dir = Path(str(indexed_benchmark[name]["run_dir"])).resolve()
        receipt_path = run_dir.parent / (
            f"sensor_motion_development_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != expected_evaluator_hashes[name]:
            raise ValueError(f"Wrong evaluator policy for {name}")
        if receipt.get("external_test_used") is not False:
            raise ValueError("External test use declared")
        if receipt.get("sensor_external_calibration_used_for_model_selection") is not False:
            raise ValueError("Synthetic calibration was used for model selection")
        runs = receipt.get("runs", [])
        if len(runs) != 1 or int(runs[0].get("seed", -1)) != seed:
            raise ValueError("Evaluation receipt has an unexpected seed")
        run = runs[0]
        if Path(str(run["run_dir"])).resolve() != run_dir:
            raise ValueError("Evaluation run directory mismatch")
        if run.get("source_tree_sha256") != expected_source:
            raise ValueError("Evaluation source-tree mismatch")
        for flag in (
            "real_rice_training_exposure",
            "growingsoy_training_exposure",
            "deblurweedseg_training_exposure",
            "weedmap_training_exposure",
            "tobacco_training_exposure",
            "sensor_motion_external_calibration_exposure",
        ):
            if run.get(flag) is not False:
                raise ValueError(f"Forbidden exposure: {flag}/{name}")
        if not math.isclose(
            float(run["sensor_motion_training_exposure"]),
            expected_exposures[name],
            abs_tol=1e-12,
        ):
            raise ValueError("R2 sampling exposure mismatch")
        if int(run["samples_per_epoch"]) != expected_samples[name]:
            raise ValueError("R2 samples-per-epoch mismatch")
        if not math.isclose(
            float(indexed_benchmark[name]["source_validation"]["mean_iou"]),
            float(run["source_validation"]["mean_iou"]),
            abs_tol=1e-12,
        ):
            raise ValueError("Benchmark/evaluator source mismatch")
        evaluations[name] = run
        receipt_locks[name] = {"path": str(receipt_path), "sha256": sha256(receipt_path)}

    for domain, artifact in evaluations[control]["artifacts"].items():
        if artifact.get("reuse_source") != "compatible_prior_tobacco_evaluator":
            raise ValueError(f"Accepted artifact was not byte-reused: {domain}")
    if any(
        artifact.get("reuse_source") not in {"fresh", "current_sensor_motion_evaluator"}
        for artifact in evaluations[challenger]["artifacts"].values()
    ):
        raise ValueError("R2 challenger contains an unexpected reused artifact")

    existing_domains = [str(value) for value in protocol["existing_domains"]]
    totals: dict[str, dict[str, float]] = {}
    rows = []
    for name in (control, challenger):
        values = domain_points(evaluations[name], existing_domains)
        candidate_totals = aggregate(values, existing_domains)
        totals[name] = candidate_totals
        rows.append(
            {
                "candidate": name,
                "seed": seed,
                "domains": values,
                "aggregate": candidate_totals,
                "paired_deltas_vs_accepted_control": {
                    key: candidate_totals[key] - totals[control][key]
                    for key in candidate_totals
                },
            }
        )

    delta = {
        key: totals[challenger][key] - totals[control][key]
        for key in totals[challenger]
    }
    rules = protocol["screen_acceptance_against_accepted_control"]
    regression_limits = {
        str(key): float(value)
        for key, value in rules["maximum_existing_domain_mean_iou_regression"].items()
    }
    checks = {
        "motion_blur_gain": delta["deblur_motion_blur_mean_iou"]
        >= float(rules["motion_blur_mean_iou_delta_must_be_at_least"]),
        "matched_sharp_noninferiority": delta["deblur_sharp_mean_iou"]
        >= -float(rules["maximum_deblur_sharp_mean_iou_regression"]),
        "existing_robust_nonregression": delta["existing_robust_mean_iou"]
        >= float(rules["existing_robust_delta_must_be_at_least"]),
        "expanded_robust_nonregression": delta["expanded_robust_mean_iou"]
        >= float(rules["expanded_robust_delta_must_be_at_least"]),
        "existing_macro_nonregression": delta["existing_macro_mean_iou"]
        >= float(rules["existing_macro_delta_must_be_at_least"]),
        "expanded_macro_nonregression": delta["expanded_macro_mean_iou"]
        >= float(rules["expanded_macro_delta_must_be_at_least"]),
        **{
            f"{domain}_noninferiority": delta[f"{domain}_mean_iou"] >= -limit
            for domain, limit in regression_limits.items()
        },
    }
    accepted = all(checks.values())
    selected = challenger if accepted else control
    selected_checkpoint = Path(str(evaluations[selected]["checkpoint"])).resolve()
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "screen",
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "evaluation_receipts": receipt_locks,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(__file__),
        "source_tree_sha256": expected_source,
        "seeds": [seed],
        "runs": rows,
        "acceptance_against_accepted_control": {
            "accepted": accepted,
            "checks": checks,
            "deltas": delta,
        },
        "challenger_accepted": accepted,
        "selected_candidate": selected,
        "accepted_control_changed": selected != control,
        "confirmation_required": selected != control,
        "representative_seed": seed,
        "representative_checkpoint": str(selected_checkpoint),
        "representative_checkpoint_sha256": sha256(selected_checkpoint),
        "deblurweedseg_used_for_selection": True,
        "deblurweedseg_claim_scope": "single_field_matched_development_screen_only",
        "synthetic_sensor_calibration_used_for_selection": False,
        "external_test_used": False,
        "safety_policy_used_for_selection": False,
        "spray_deployment_eligible": False,
    }
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
