#!/usr/bin/env python3
"""Apply the frozen seed-17 synthetic sensor-motion additive screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_yaml(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def validate_locked_inputs(protocol: dict[str, Any]) -> None:
    for name, lock in protocol["locked_inputs"].items():
        path = Path(str(lock["path"])).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != str(lock["sha256"]):
            raise ValueError(
                f"Locked input changed ({name}): {actual} != {lock['sha256']}"
            )


def locked_json(protocol: dict[str, Any], name: str) -> dict[str, Any]:
    return load_json(Path(protocol["locked_inputs"][name]["path"]).resolve())


def clean_manifest_audit(audit: dict[str, Any], expected_samples: int) -> bool:
    return int(audit.get("samples", -1)) == expected_samples and all(
        int(audit.get(field, -1)) == 0
        for field in ("missing_files", "invalid_masks", "shape_mismatches")
    )


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    expected = protocol["expected_data_evidence"]
    asset = locked_json(protocol, "asset_quality_audit")
    if asset.get("all_automatic_quality_gates_passed") is not True:
        raise ValueError("Sensor asset automatic quality gate did not pass")
    if not asset.get("quality_gate_checks") or not all(
        bool(value) for value in asset["quality_gate_checks"].values()
    ):
        raise ValueError("At least one sensor asset check failed")
    if int(asset.get("real_deblurweedseg_training_or_asset_exposure", -1)) != 0:
        raise ValueError("Real DeBlurWeedSeg pixels entered the synthetic asset")
    counts = asset.get("counts", {})
    for key in ("samples", "train", "external_calibration"):
        if int(counts.get(key, -1)) != int(expected[key]):
            raise ValueError(f"Unexpected sensor asset count: {key}")
    if counts.get("group_overlap") != []:
        raise ValueError("Sensor asset train/calibration source scenes overlap")

    visual = locked_json(protocol, "manual_visual_review")
    if visual.get("passed") is not True:
        raise ValueError("Sensor manual visual review did not pass")
    manifest_audit = locked_json(protocol, "sensor_manifest_audit")
    if not clean_manifest_audit(manifest_audit, int(expected["samples"])):
        raise ValueError("Sensor manifest audit failed")
    duplicate = locked_json(protocol, "sensor_vs_all_real_duplicate_audit")
    if duplicate.get("passed") is not True:
        raise ValueError("Sensor cross-real duplicate gate did not pass")
    for field in (
        "candidate_to_reference_match_count",
        "within_candidate_cross_split_match_count",
    ):
        if int(duplicate.get(field, -1)) != 0:
            raise ValueError(f"Sensor duplicate audit failed: {field}")

    combined = locked_json(protocol, "challenger_manifest_receipt")
    if combined.get("source_scene_audit", {}).get("passed") is not True:
        raise ValueError("Challenger sensor source-scene gate failed")
    policy = combined.get("role_policy", {})
    if policy.get("external_test_present") is not False:
        raise ValueError("Challenger manifest contains an external test")
    if int(policy.get("real_deblurweedseg_pixels_in_assets_or_training", -1)) != 0:
        raise ValueError("Real blur diagnostic pixels entered training")
    if int(combined.get("output", {}).get("samples", -1)) != int(
        expected["combined_training_manifest_samples"]
    ):
        raise ValueError("Unexpected challenger training-manifest size")
    combined_audit = locked_json(protocol, "challenger_manifest_audit")
    if not clean_manifest_audit(
        combined_audit, int(expected["combined_training_manifest_samples"])
    ):
        raise ValueError("Challenger training-manifest audit failed")


def domain_points(run: dict[str, Any], existing_domains: list[str]) -> dict[str, float]:
    artifacts = run["artifacts"]
    expected_artifacts = {
        "cwfid",
        "sorghum_weed",
        "cropandweed",
        "rice",
        "growingsoy",
        "weedmap",
        "tobacco",
        "deblur_sharp",
        "deblur_motion_blur",
    }
    if set(artifacts) != expected_artifacts:
        raise ValueError(f"Unexpected evaluation artifacts: {sorted(artifacts)}")
    values = {"source": float(run["source_validation"]["mean_iou"])}
    values.update(
        {
            name: float(artifacts[name]["mean_iou"])
            for name in existing_domains
            if name != "source"
        }
    )
    values["deblur_sharp"] = float(artifacts["deblur_sharp"]["mean_iou"])
    values["deblur_motion_blur"] = float(
        artifacts["deblur_motion_blur"]["mean_iou"]
    )
    return values


def aggregate(values: dict[str, float], existing_domains: list[str]) -> dict[str, float]:
    existing = {name: values[name] for name in existing_domains}
    expanded = {**existing, "deblur_motion_blur": values["deblur_motion_blur"]}
    return {
        "existing_robust_mean_iou": min(existing.values()),
        "existing_macro_mean_iou": statistics.fmean(existing.values()),
        "expanded_robust_mean_iou": min(expanded.values()),
        "expanded_macro_mean_iou": statistics.fmean(expanded.values()),
        **{f"{name}_mean_iou": value for name, value in values.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    protocol_path = Path(arguments.protocol).resolve()
    protocol = load_yaml(protocol_path)
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Protocol was not frozen before challenger training")
    if protocol.get("stage") != "screen":
        raise ValueError("This selector accepts only the seed-17 screen")
    validate_locked_inputs(protocol)
    validate_data_evidence(protocol)

    benchmark_path = Path(arguments.benchmark).resolve()
    benchmark = load_json(benchmark_path)
    matrix_path = Path(str(benchmark["matrix"])).resolve()
    matrix_lock = protocol["locked_inputs"]["screen_matrix"]
    if matrix_path != Path(str(matrix_lock["path"])).resolve():
        raise ValueError("Benchmark does not use the frozen screen matrix")
    if sha256(matrix_path) != str(matrix_lock["sha256"]):
        raise ValueError("Screen matrix changed after protocol freeze")

    seed = int(protocol["screen_seed"])
    accepted_control = str(protocol["accepted_control"])
    compute_control = str(protocol["matched_compute_control"])
    challenger = str(protocol["screen_candidate"])
    expected_names = {accepted_control, compute_control, challenger}
    indexed_benchmark: dict[str, dict[str, Any]] = {}
    for run in benchmark["runs"]:
        name = str(run["candidate"])
        run_seed = int(run["seed"])
        if name in expected_names and run_seed == seed:
            if name in indexed_benchmark:
                raise ValueError(f"Duplicate benchmark run: {name}/{seed}")
            indexed_benchmark[name] = run
    missing = sorted(expected_names - set(indexed_benchmark))
    if missing:
        raise ValueError(f"Missing benchmark runs: {missing}")

    expected_source = str(protocol["source_tree_sha256"])
    expected_exposure = {
        str(name): float(value)
        for name, value in protocol["candidate_sensor_motion_exposure"].items()
    }
    expected_samples = {
        str(name): int(value)
        for name, value in protocol["candidate_samples_per_epoch"].items()
    }
    evaluator_hash = str(protocol["locked_inputs"]["evaluator_script"]["sha256"])
    indexed_evaluations: dict[str, dict[str, Any]] = {}
    receipt_locks: dict[str, dict[str, str]] = {}
    for name in sorted(expected_names):
        run_dir = Path(str(indexed_benchmark[name]["run_dir"])).resolve()
        candidate_dir = run_dir.parent
        receipt_path = candidate_dir / (
            f"sensor_motion_development_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {receipt_path}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {receipt_path}")
        if receipt.get("sensor_external_calibration_used_for_model_selection") is not False:
            raise ValueError("Synthetic sensor calibration was used for selection")
        if receipt.get("checkpoint") != protocol["checkpoint"]:
            raise ValueError(f"Wrong checkpoint policy: {receipt_path}")
        if int(receipt.get("fixed_epoch", -1)) != int(protocol["fixed_epoch"]):
            raise ValueError(f"Wrong fixed epoch: {receipt_path}")
        runs = receipt.get("runs", [])
        if len(runs) != 1 or int(runs[0].get("seed", -1)) != seed:
            raise ValueError(f"Evaluation receipt has wrong seed: {receipt_path}")
        run = runs[0]
        if Path(str(run["run_dir"])).resolve() != run_dir:
            raise ValueError(f"Run directory mismatch: {name}")
        if run.get("source_tree_sha256") != expected_source:
            raise ValueError(f"Source-tree mismatch: {name}")
        for flag in (
            "real_rice_training_exposure",
            "growingsoy_training_exposure",
            "deblurweedseg_training_exposure",
            "weedmap_training_exposure",
            "tobacco_training_exposure",
            "sensor_motion_external_calibration_exposure",
        ):
            if run.get(flag) is not False:
                raise ValueError(f"Forbidden training exposure ({flag}): {name}")
        exposure = float(run["sensor_motion_training_exposure"])
        if not math.isclose(exposure, expected_exposure[name], abs_tol=1e-12):
            raise ValueError(f"Sensor exposure mismatch: {name}")
        if int(run["samples_per_epoch"]) != expected_samples[name]:
            raise ValueError(f"Samples-per-epoch mismatch: {name}")
        benchmark_source = float(indexed_benchmark[name]["source_validation"]["mean_iou"])
        fixed_source = float(run["source_validation"]["mean_iou"])
        if not math.isclose(benchmark_source, fixed_source, abs_tol=1e-12):
            raise ValueError(f"Source validation mismatch: {name}")
        indexed_evaluations[name] = run
        receipt_locks[name] = {"path": str(receipt_path), "sha256": sha256(receipt_path)}

    accepted_artifacts = indexed_evaluations[accepted_control]["artifacts"]
    for name, artifact in accepted_artifacts.items():
        if artifact.get("reuse_source") != "compatible_prior_tobacco_evaluator":
            raise ValueError(f"Accepted control artifact was not byte-reused: {name}")

    existing_domains = [str(value) for value in protocol["existing_domains"]]
    if "source" not in existing_domains or "deblur_motion_blur" in existing_domains:
        raise ValueError("Invalid existing-domain definition")
    rows: list[dict[str, Any]] = []
    aggregates: dict[str, dict[str, float]] = {}
    for name in (accepted_control, compute_control, challenger):
        values = domain_points(indexed_evaluations[name], existing_domains)
        totals = aggregate(values, existing_domains)
        aggregates[name] = totals
        rows.append(
            {
                "candidate": name,
                "seed": seed,
                "domains": values,
                "aggregate": totals,
                "paired_deltas_vs_accepted_control": {
                    key: totals[key] - aggregates[accepted_control][key]
                    for key in totals
                },
            }
        )
    challenger_row = next(row for row in rows if row["candidate"] == challenger)
    challenger_row["paired_deltas_vs_matched_compute_control"] = {
        key: aggregates[challenger][key] - aggregates[compute_control][key]
        for key in aggregates[challenger]
    }

    rules = protocol["screen_acceptance_against_each_control"]
    regression_limits = {
        str(name): float(value)
        for name, value in rules["maximum_existing_domain_mean_iou_regression"].items()
    }
    comparisons: dict[str, dict[str, Any]] = {}
    for comparator in (accepted_control, compute_control):
        delta = {
            key: aggregates[challenger][key] - aggregates[comparator][key]
            for key in aggregates[challenger]
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
        comparisons[comparator] = {
            "accepted": all(checks.values()),
            "checks": checks,
            "deltas": delta,
        }
    challenger_accepted = all(value["accepted"] for value in comparisons.values())
    selected = challenger if challenger_accepted else accepted_control
    selected_run = indexed_evaluations[selected]
    checkpoint = Path(str(selected_run["checkpoint"])).resolve()

    blur_diagnostics = {
        name: {
            "sharp_mean_iou": aggregates[name]["deblur_sharp_mean_iou"],
            "motion_blur_mean_iou": aggregates[name]["deblur_motion_blur_mean_iou"],
            "motion_blur_minus_sharp_mean_iou": (
                aggregates[name]["deblur_motion_blur_mean_iou"]
                - aggregates[name]["deblur_sharp_mean_iou"]
            ),
        }
        for name in sorted(expected_names)
    }
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
        "acceptance_against_each_control": comparisons,
        "challenger_accepted": challenger_accepted,
        "selected_candidate": selected,
        "accepted_control_changed": selected != accepted_control,
        "matched_compute_control_used_for_causal_comparison": True,
        "matched_compute_control_eligible_for_selection": False,
        "confirmation_required": selected != accepted_control,
        "representative_seed": seed,
        "representative_checkpoint": str(checkpoint),
        "representative_checkpoint_sha256": sha256(checkpoint),
        "deblurweedseg_diagnostics": blur_diagnostics,
        "deblurweedseg_used_for_selection": True,
        "deblurweedseg_claim_scope": "single_field_matched_development_screen_only",
        "synthetic_sensor_calibration_used_for_selection": False,
        "external_test_used": False,
        "safety_policy_used_for_selection": False,
        "spray_deployment_eligible": False,
    }
    output = Path(arguments.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
