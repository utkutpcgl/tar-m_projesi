#!/usr/bin/env python3
"""Apply the frozen two-control RiceSEG replay-preserving seed-17 screen."""

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
            raise ValueError(f"Locked input changed ({name}): {actual} != {lock['sha256']}")


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    expected = protocol["expected_data_evidence"]
    locked = protocol["locked_inputs"]
    quality = load_json(locked["riceseg_quality_gate"]["path"])
    if quality.get("passed") is not True or quality.get("status") != "passed":
        raise ValueError("RiceSEG quality gate did not pass")
    if int(quality.get("eligible_samples", -1)) != int(expected["eligible_samples"]):
        raise ValueError("Unexpected RiceSEG eligible sample count")
    train = quality.get("manifests", {}).get("train", {})
    calibration = quality.get("manifests", {}).get("calibration", {})
    if int(train.get("samples", -1)) != int(expected["train"]):
        raise ValueError("Unexpected RiceSEG train count")
    if int(calibration.get("samples", -1)) != int(expected["external_calibration"]):
        raise ValueError("Unexpected RiceSEG calibration count")
    if quality.get("external_test_created") is not False:
        raise ValueError("RiceSEG quality gate created an external test")
    if quality.get("model_results_used") is not False:
        raise ValueError("RiceSEG quality gate used model results")

    combined = load_json(locked["challenger_manifest_receipt"]["path"])
    if combined.get("session_audit", {}).get("passed") is not True:
        raise ValueError("RiceSEG train/calibration group separation failed")
    if combined.get("session_audit", {}).get("overlap"):
        raise ValueError("RiceSEG train/calibration group overlap is non-empty")
    if combined.get("role_policy", {}).get("external_test_present") is not False:
        raise ValueError("Challenger manifest contains an external test")
    output = combined.get("output", {})
    if int(output.get("samples", -1)) != int(expected["combined_training_samples"]):
        raise ValueError("Unexpected challenger manifest sample count")
    if int(output.get("datasets", {}).get("riceseg", -1)) != int(expected["train"]):
        raise ValueError("Challenger manifest has wrong RiceSEG row count")

    audit = load_json(locked["challenger_manifest_audit"]["path"])
    if int(audit.get("samples", -1)) != int(expected["combined_training_samples"]):
        raise ValueError("Challenger manifest audit has wrong sample count")
    for field in ("missing_files", "invalid_masks", "shape_mismatches"):
        if int(audit.get(field, -1)) != 0:
            raise ValueError(f"Challenger manifest audit failed: {field}")


def aggregate(values: dict[str, float], existing_domains: list[str]) -> dict[str, float]:
    existing = {name: values[name] for name in existing_domains}
    expanded = {
        **existing,
        "riceseg": values["riceseg"],
        "riceseg_reproductive": values["riceseg_reproductive"],
    }
    return {
        "existing_robust_mean_iou": min(existing.values()),
        "existing_macro_mean_iou": statistics.fmean(existing.values()),
        "expanded_robust_mean_iou": min(expanded.values()),
        "expanded_macro_mean_iou": statistics.fmean(expanded.values()),
        **{f"{name}_mean_iou": value for name, value in values.items()},
    }


def screen_checks(
    delta: dict[str, float], rules: dict[str, Any]
) -> dict[str, bool]:
    limits = {
        str(name): float(value)
        for name, value in rules["maximum_existing_domain_mean_iou_regression"].items()
    }
    return {
        "riceseg_gain": delta["riceseg_mean_iou"]
        >= float(rules["riceseg_mean_iou_delta_must_be_at_least"]),
        "riceseg_reproductive_gain": delta["riceseg_reproductive_mean_iou"]
        >= float(rules["riceseg_reproductive_mean_iou_delta_must_be_at_least"]),
        "existing_robust_nonregression": delta["existing_robust_mean_iou"]
        >= float(rules["existing_robust_delta_must_be_at_least"]),
        "existing_macro_nonregression": delta["existing_macro_mean_iou"]
        >= float(rules["existing_macro_delta_must_be_at_least"]),
        "expanded_robust_gain": delta["expanded_robust_mean_iou"]
        >= float(rules["expanded_robust_delta_must_be_at_least"]),
        "expanded_macro_nonregression": delta["expanded_macro_mean_iou"]
        >= float(rules["expanded_macro_delta_must_be_at_least"]),
        **{
            f"{domain}_noninferiority": delta[f"{domain}_mean_iou"] >= -limit
            for domain, limit in limits.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_yaml(protocol_path)
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Protocol was not frozen before challenger training")
    if protocol.get("stage") != "screen":
        raise ValueError("This selector accepts only the seed-17 screen")
    validate_locked_inputs(protocol)
    validate_data_evidence(protocol)

    benchmark_path = Path(args.benchmark).resolve()
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
        if name in expected_names and int(run["seed"]) == seed:
            if name in indexed_benchmark:
                raise ValueError(f"Duplicate benchmark run: {name}/{seed}")
            indexed_benchmark[name] = run
    missing = sorted(expected_names - set(indexed_benchmark))
    if missing:
        raise ValueError(f"Missing benchmark runs: {missing}")

    expected_source = str(protocol["source_tree_sha256"])
    expected_exposure = {
        str(name): float(value)
        for name, value in protocol["candidate_riceseg_exposure"].items()
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
        receipt_path = run_dir.parent / (
            f"riceseg_additive_development_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {receipt_path}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {receipt_path}")
        runs = receipt.get("runs", [])
        if len(runs) != 1 or int(runs[0].get("seed", -1)) != seed:
            raise ValueError(f"Evaluation receipt has wrong seed: {receipt_path}")
        run = runs[0]
        if Path(str(run["run_dir"])).resolve() != run_dir:
            raise ValueError(f"Run directory mismatch: {name}")
        if run.get("source_tree_sha256") != expected_source:
            raise ValueError(f"Source-tree mismatch: {name}")
        for flag in (
            "riceseg_calibration_exposure",
            "early_rice_training_exposure",
            "growingsoy_training_exposure",
            "weedmap_training_exposure",
            "tobacco_training_exposure",
            "deblurweedseg_training_exposure",
        ):
            if run.get(flag) is not False:
                raise ValueError(f"Forbidden training exposure ({flag}): {name}")
        exposure = float(run["riceseg_training_exposure"])
        if not math.isclose(exposure, expected_exposure[name], abs_tol=1e-12):
            raise ValueError(f"RiceSEG exposure mismatch: {name}")
        expected_rows = int(protocol["expected_riceseg_training_rows"][name])
        if int(run["riceseg_training_rows"]) != expected_rows:
            raise ValueError(f"RiceSEG training-row mismatch: {name}")
        if int(run["samples_per_epoch"]) != expected_samples[name]:
            raise ValueError(f"Samples-per-epoch mismatch: {name}")
        benchmark_source = float(indexed_benchmark[name]["source_validation"]["mean_iou"])
        if not math.isclose(
            benchmark_source,
            float(run["source_validation"]["mean_iou"]),
            abs_tol=1e-12,
        ):
            raise ValueError(f"Source validation mismatch: {name}")
        indexed_evaluations[name] = run
        receipt_locks[name] = {"path": str(receipt_path), "sha256": sha256(receipt_path)}

    existing_domains = [str(value) for value in protocol["existing_domains"]]
    expected_artifacts = set(existing_domains) - {"source"}
    expected_artifacts |= {
        "riceseg",
        "riceseg_reproductive",
        "deblur_sharp",
        "deblur_motion_blur",
    }
    aggregates: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []
    for name in (accepted_control, compute_control, challenger):
        run = indexed_evaluations[name]
        artifacts = run["artifacts"]
        if set(artifacts) != expected_artifacts:
            raise ValueError(f"Unexpected evaluation artifacts for {name}")
        values = {"source": float(run["source_validation"]["mean_iou"])}
        values.update(
            {
                domain: float(artifacts[domain]["mean_iou"])
                for domain in sorted(expected_artifacts - {"deblur_sharp", "deblur_motion_blur"})
            }
        )
        totals = aggregate(values, existing_domains)
        aggregates[name] = totals
        rows.append(
            {
                "candidate": name,
                "seed": seed,
                "domains": values,
                "diagnostics": {
                    "deblur_sharp_mean_iou": float(artifacts["deblur_sharp"]["mean_iou"]),
                    "deblur_motion_blur_mean_iou": float(
                        artifacts["deblur_motion_blur"]["mean_iou"]
                    ),
                },
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
    comparisons: dict[str, dict[str, Any]] = {}
    for comparator in (accepted_control, compute_control):
        delta = {
            key: aggregates[challenger][key] - aggregates[comparator][key]
            for key in aggregates[challenger]
        }
        checks = screen_checks(delta, rules)
        comparisons[comparator] = {
            "accepted": all(checks.values()),
            "checks": checks,
            "deltas": delta,
        }
    accepted = all(item["accepted"] for item in comparisons.values())

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "screen",
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "source_tree_sha256": expected_source,
        "seeds": [seed],
        "runs": rows,
        "comparisons": comparisons,
        "screen_candidate_accepted": accepted,
        "confirmation_eligible": accepted,
        "selected_candidate": challenger if accepted else accepted_control,
        "fallback_applied": not accepted,
        "model_benefit_established": False,
        "evaluation_receipts": receipt_locks,
        "external_test_used": False,
        "deblurweedseg_used_for_selection": False,
        "spray_deployment_eligible": False,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(Path(__file__).resolve()),
    }
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
