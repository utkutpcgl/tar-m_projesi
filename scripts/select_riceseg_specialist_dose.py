#!/usr/bin/env python3
"""Select a crop-routed RiceSEG specialist from the frozen seed-17 dose screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml


TARGET_DOMAINS = ("early_rice", "riceseg", "riceseg_reproductive")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        value = json.loads(source.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a mapping: {source}")
    return value


def validate_locks(protocol: Mapping[str, Any]) -> None:
    for name, lock in protocol["locked_inputs"].items():
        path = Path(str(lock["path"])).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != str(lock["sha256"]):
            raise ValueError(
                f"Locked input changed ({name}): {actual} != {lock['sha256']}"
            )


def target_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Evaluation run has no artifacts")
    values = {
        name: float(artifacts[name]["mean_iou"]) for name in TARGET_DOMAINS
    }
    return {
        "domains": values,
        "target_robust_mean_iou": min(values.values()),
        "target_macro_mean_iou": statistics.fmean(values.values()),
    }


def selection_key(summary: Mapping[str, Any], exposure: float) -> tuple[float, ...]:
    domains = summary["domains"]
    return (
        float(summary["target_robust_mean_iou"]),
        float(summary["target_macro_mean_iou"]),
        float(domains["riceseg"]),
        -float(exposure),
    )


def screen_checks(
    specialist: Mapping[str, Any],
    fallback: Mapping[str, Any],
    rules: Mapping[str, Any],
) -> tuple[dict[str, float], dict[str, bool]]:
    deltas = {
        name: float(specialist["domains"][name])
        - float(fallback["domains"][name])
        for name in TARGET_DOMAINS
    }
    deltas["target_robust_mean_iou"] = float(
        specialist["target_robust_mean_iou"]
    ) - float(fallback["target_robust_mean_iou"])
    deltas["target_macro_mean_iou"] = float(
        specialist["target_macro_mean_iou"]
    ) - float(fallback["target_macro_mean_iou"])
    checks = {
        "early_rice_gain": deltas["early_rice"]
        >= float(rules["minimum_early_rice_gain"]),
        "riceseg_gain": deltas["riceseg"]
        >= float(rules["minimum_riceseg_gain"]),
        "riceseg_reproductive_gain": deltas["riceseg_reproductive"]
        >= float(rules["minimum_riceseg_reproductive_gain"]),
        "target_robust_gain": deltas["target_robust_mean_iou"]
        >= float(rules["minimum_target_robust_gain"]),
    }
    return deltas, checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_object(protocol_path)
    if protocol.get("stage") != "screen":
        raise ValueError("Only a screen protocol is supported")
    if protocol.get("frozen_before_screen_training") is not True:
        raise ValueError("Protocol was not frozen before screen training")
    validate_locks(protocol)

    quality = load_object(protocol["locked_inputs"]["riceseg_quality_gate"]["path"])
    if quality.get("passed") is not True or quality.get("status") != "passed":
        raise ValueError("RiceSEG quality gate did not pass")
    if quality.get("external_test_created") is not False:
        raise ValueError("RiceSEG gate created an external test")

    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_object(benchmark_path)
    matrix_lock = protocol["locked_inputs"]["screen_matrix"]
    if Path(str(benchmark["matrix"])).resolve() != Path(
        str(matrix_lock["path"])
    ).resolve():
        raise ValueError("Benchmark used another matrix")

    seed = int(protocol["screen_seed"])
    fallback_name = str(protocol["accepted_global_fallback"])
    specialist_names = [str(value) for value in protocol["specialist_candidates"]]
    expected = {fallback_name, *specialist_names}
    benchmark_runs: dict[str, dict[str, Any]] = {}
    for run in benchmark.get("runs", []):
        name = str(run.get("candidate"))
        if name in expected and int(run.get("seed", -1)) == seed:
            if name in benchmark_runs:
                raise ValueError(f"Duplicate benchmark run: {name}/{seed}")
            benchmark_runs[name] = run
    missing = sorted(expected - set(benchmark_runs))
    if missing:
        raise ValueError(f"Missing benchmark runs: {missing}")

    expected_exposure = {
        str(name): float(value)
        for name, value in protocol["candidate_riceseg_exposure"].items()
    }
    evaluator_hash = str(protocol["locked_inputs"]["target_evaluator"]["sha256"])
    summaries: dict[str, dict[str, Any]] = {}
    receipts: dict[str, dict[str, str]] = {}
    for name in sorted(expected):
        run_dir = Path(str(benchmark_runs[name]["run_dir"])).resolve()
        family_dir = run_dir.parent
        receipt_path = family_dir / (
            f"riceseg_specialist_targets_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed}.json"
        )
        receipt = load_object(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluator hash mismatch: {name}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test was used: {name}")
        routing = receipt.get("routing_contract", {})
        if int(routing.get("specialist_target_crop_id", -1)) != 12:
            raise ValueError(f"Routing contract changed: {name}")
        if routing.get("pixel_inferred_routing_allowed") is not False:
            raise ValueError(f"Pixel-inferred routing was enabled: {name}")
        runs = receipt.get("runs", [])
        if len(runs) != 1 or int(runs[0].get("seed", -1)) != seed:
            raise ValueError(f"Evaluation receipt has wrong seed: {name}")
        evaluated = runs[0]
        if Path(str(evaluated["run_dir"])).resolve() != run_dir:
            raise ValueError(f"Run directory mismatch: {name}")
        if evaluated.get("source_tree_sha256") != protocol["source_tree_sha256"]:
            raise ValueError(f"Source tree mismatch: {name}")
        if evaluated.get("external_test_used") is not False:
            raise ValueError(f"External test flag changed: {name}")
        exposure = float(evaluated["riceseg_training_exposure"])
        if not math.isclose(exposure, expected_exposure[name], abs_tol=1e-12):
            raise ValueError(f"RiceSEG exposure mismatch: {name}")
        summaries[name] = {
            **target_summary(evaluated),
            "riceseg_training_exposure": exposure,
            "checkpoint": evaluated["checkpoint"],
            "checkpoint_sha256": evaluated["checkpoint_sha256"],
        }
        receipts[name] = {"path": str(receipt_path), "sha256": sha256(receipt_path)}

    selected_name = max(
        specialist_names,
        key=lambda name: selection_key(
            summaries[name], summaries[name]["riceseg_training_exposure"]
        ),
    )
    fallback = summaries[fallback_name]
    selected = summaries[selected_name]
    deltas, checks = screen_checks(selected, fallback, protocol["screen_acceptance"])
    confirmation_eligible = all(checks.values())

    output = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "riceseg_crop_routed_specialist_dose_screen_selection",
        "stage": "screen",
        "external_test_used": False,
        "spray_deployment_eligible": False,
        "routing_contract": protocol["routing_contract"],
        "accepted_global_fallback": fallback_name,
        "accepted_global_fallback_unchanged": True,
        "selected_specialist": selected_name if confirmation_eligible else None,
        "selected_screen_checkpoint": (
            selected["checkpoint"] if confirmation_eligible else None
        ),
        "selected_screen_checkpoint_sha256": (
            selected["checkpoint_sha256"] if confirmation_eligible else None
        ),
        "confirmation_eligible": confirmation_eligible,
        "screen_checks": checks,
        "selected_deltas_vs_global_fallback": deltas,
        "candidate_summaries": summaries,
        "evaluation_receipts": receipts,
        "screen_seed": seed,
        "fixed_epoch": int(protocol["fixed_epoch"]),
        "source_tree_sha256": protocol["source_tree_sha256"],
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "selector": str(Path(__file__).resolve()),
        "selector_sha256": sha256(Path(__file__).resolve()),
    }
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(output_path), "selected": output["selected_specialist"]}, indent=2))


if __name__ == "__main__":
    main()
