#!/usr/bin/env python3
"""Apply the frozen seed-17 WeedMap real-data screen protocol."""

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


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    expected = protocol["expected_data_evidence"]
    conversion = locked_json(protocol, "weedmap_conversion_report")
    if conversion.get("all_quality_gates_passed") is not True:
        raise ValueError("WeedMap conversion quality gate did not pass")
    if int(conversion.get("samples", -1)) != int(expected["samples"]):
        raise ValueError("Unexpected WeedMap sample count")
    if conversion.get("split_counts") != {
        "external_calibration": int(expected["external_calibration"]),
        "train": int(expected["train"]),
    }:
        raise ValueError("Unexpected WeedMap role counts")
    if int(conversion.get("field_count", -1)) != int(expected["fields"]):
        raise ValueError("Unexpected WeedMap field count")
    if int(conversion.get("capture_group_count", -1)) != int(expected["groups"]):
        raise ValueError("Unexpected WeedMap group count")
    if conversion.get("policy", {}).get("sequoia_cir_excluded") is not True:
        raise ValueError("The CIR-only Sequoia subset was not excluded")

    manifest_audit = locked_json(protocol, "weedmap_manifest_audit")
    if int(manifest_audit.get("samples", -1)) != int(expected["samples"]):
        raise ValueError("WeedMap manifest audit has another sample count")
    for field in ("missing_files", "invalid_masks", "shape_mismatches"):
        if int(manifest_audit.get(field, -1)) != 0:
            raise ValueError(f"WeedMap manifest audit failed: {field}")

    duplicate = locked_json(protocol, "weedmap_duplicate_audit")
    if duplicate.get("passed") is not True:
        raise ValueError("WeedMap duplicate gate did not pass")
    for field in (
        "candidate_to_reference_match_count",
        "within_candidate_cross_split_match_count",
    ):
        if int(duplicate.get(field, -1)) != 0:
            raise ValueError(f"WeedMap duplicate audit failed: {field}")

    visual = locked_json(protocol, "weedmap_manual_visual_review")
    if visual.get("passed") is not True:
        raise ValueError("WeedMap manual visual review did not pass")

    combined = locked_json(protocol, "challenger_manifest_receipt")
    if combined.get("session_audit", {}).get("passed") is not True:
        raise ValueError("WeedMap challenger group-disjointness failed")
    if combined.get("role_policy", {}).get("external_test_present") is not False:
        raise ValueError("WeedMap challenger manifest contains an external test")
    if int(combined.get("output", {}).get("samples", -1)) != int(
        expected["combined_training_manifest_samples"]
    ):
        raise ValueError("Unexpected challenger training-manifest size")


def domain_points(run: dict[str, Any], domains: list[str]) -> dict[str, float]:
    artifacts = run["artifacts"]
    expected_artifacts = {
        "cwfid",
        "sorghum_weed",
        "cropandweed",
        "rice",
        "growingsoy",
        "weedmap",
        "deblur_sharp",
        "deblur_motion_blur",
    }
    if set(artifacts) != expected_artifacts:
        raise ValueError(f"Unexpected evaluation artifacts: {sorted(artifacts)}")
    values = {"source": float(run["source_validation"]["mean_iou"])}
    values.update({name: float(artifacts[name]["mean_iou"]) for name in domains})
    return values


def aggregate(
    values: dict[str, float], existing_domains: list[str]
) -> dict[str, float]:
    existing = {name: values[name] for name in existing_domains}
    expanded = {**existing, "weedmap": values["weedmap"]}
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
    control = str(protocol["control"])
    challengers = [str(value) for value in protocol["screen_candidates"]]
    expected_names = {control, *challengers}
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
        for name, value in protocol["candidate_weedmap_exposure"].items()
    }
    evaluator_hash = str(
        protocol["locked_inputs"]["evaluator_script"]["sha256"]
    )
    indexed_evaluations: dict[str, dict[str, Any]] = {}
    receipt_locks: dict[str, dict[str, str]] = {}
    for name in sorted(expected_names):
        run_dir = Path(str(indexed_benchmark[name]["run_dir"])).resolve()
        candidate_dir = run_dir.parent
        receipt_path = candidate_dir / (
            f"weedmap_development_fixed_epoch{protocol['fixed_epoch']}_"
            f"seeds_{seed}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {receipt_path}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {receipt_path}")
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
        if run.get("real_rice_training_exposure") is not False:
            raise ValueError(f"Real Rice training leakage declared: {name}")
        if run.get("growingsoy_training_exposure") is not False:
            raise ValueError(f"GrowingSoy training leakage declared: {name}")
        if run.get("deblurweedseg_training_exposure") is not False:
            raise ValueError(f"DeBlurWeedSeg training leakage declared: {name}")
        exposure = float(run["weedmap_training_exposure"])
        if not math.isclose(exposure, expected_exposure[name], abs_tol=1e-12):
            raise ValueError(f"WeedMap exposure mismatch: {name}")
        benchmark_source = float(indexed_benchmark[name]["source_validation"]["mean_iou"])
        fixed_source = float(run["source_validation"]["mean_iou"])
        if not math.isclose(benchmark_source, fixed_source, abs_tol=1e-12):
            raise ValueError(f"Source validation mismatch: {name}")
        indexed_evaluations[name] = run
        receipt_locks[name] = {
            "path": str(receipt_path),
            "sha256": sha256(receipt_path),
        }

    existing_domains = [str(value) for value in protocol["existing_domains"]]
    if "weedmap" in existing_domains or "source" not in existing_domains:
        raise ValueError("Invalid existing-domain definition")
    metric_domains = [
        name for name in existing_domains if name != "source"
    ] + ["weedmap"]
    control_values = domain_points(indexed_evaluations[control], metric_domains)
    control_aggregate = aggregate(control_values, existing_domains)
    rows: list[dict[str, Any]] = [
        {
            "candidate": control,
            "seed": seed,
            "domains": control_values,
            "aggregate": control_aggregate,
            "paired_deltas_vs_control": {
                key: 0.0 for key in control_aggregate
            },
        }
    ]
    for name in challengers:
        values = domain_points(indexed_evaluations[name], metric_domains)
        totals = aggregate(values, existing_domains)
        rows.append(
            {
                "candidate": name,
                "seed": seed,
                "domains": values,
                "aggregate": totals,
                "paired_deltas_vs_control": {
                    key: totals[key] - control_aggregate[key]
                    for key in control_aggregate
                },
            }
        )

    rules = protocol["screen_acceptance_against_control"]
    regressions = {
        str(name): float(value)
        for name, value in rules[
            "maximum_existing_domain_mean_iou_regression"
        ].items()
    }
    acceptance: dict[str, dict[str, Any]] = {}
    for name in challengers:
        row = next(value for value in rows if value["candidate"] == name)
        delta = row["paired_deltas_vs_control"]
        checks = {
            "weedmap_gain": delta["weedmap_mean_iou"]
            >= float(rules["weedmap_mean_iou_delta_must_be_at_least"]),
            "existing_robust_nonregression": delta["existing_robust_mean_iou"]
            >= float(rules["existing_robust_delta_must_be_at_least"]),
            "expanded_robust_nonregression": delta["expanded_robust_mean_iou"]
            >= float(rules["expanded_robust_delta_must_be_at_least"]),
            "existing_macro_nonregression": delta["existing_macro_mean_iou"]
            >= float(rules["existing_macro_delta_must_be_at_least"]),
            "expanded_macro_nonregression": delta["expanded_macro_mean_iou"]
            >= float(rules["expanded_macro_delta_must_be_at_least"]),
            **{
                f"{domain}_noninferiority": delta[f"{domain}_mean_iou"]
                >= -limit
                for domain, limit in regressions.items()
            },
        }
        acceptance[name] = {"accepted": all(checks.values()), "checks": checks}

    eligible = [name for name in challengers if acceptance[name]["accepted"]]

    def rank_key(name: str) -> tuple[float, float, float]:
        row = next(value for value in rows if value["candidate"] == name)
        totals = row["aggregate"]
        return (
            totals["expanded_robust_mean_iou"],
            totals["weedmap_mean_iou"],
            totals["expanded_macro_mean_iou"],
        )

    selected = max(eligible, key=rank_key) if eligible else control
    selected_run = indexed_evaluations[selected]
    checkpoint = Path(str(selected_run["checkpoint"])).resolve()
    blur_diagnostics = {
        name: {
            "sharp_mean_iou": float(
                indexed_evaluations[name]["artifacts"]["deblur_sharp"]["mean_iou"]
            ),
            "motion_blur_mean_iou": float(
                indexed_evaluations[name]["artifacts"]["deblur_motion_blur"][
                    "mean_iou"
                ]
            ),
        }
        for name in sorted(expected_names)
    }
    for values in blur_diagnostics.values():
        values["motion_blur_minus_sharp_mean_iou"] = (
            values["motion_blur_mean_iou"] - values["sharp_mean_iou"]
        )

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
        "acceptance": acceptance,
        "selected_candidate": selected,
        "accepted_control_changed": selected != control,
        "confirmation_required": selected != control,
        "representative_seed": seed,
        "representative_checkpoint": str(checkpoint),
        "representative_checkpoint_sha256": sha256(checkpoint),
        "deblurweedseg_diagnostics": blur_diagnostics,
        "deblurweedseg_used_for_selection": False,
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
