#!/usr/bin/env python3
"""Confirm the frozen crop-routed rice specialist across three paired seeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from scripts.select_riceseg_specialist_dose import TARGET_DOMAINS, target_summary


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
            raise ValueError(f"Locked input changed ({name}): {actual}")


def index_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_seeds: list[int],
    expected_source: str,
    evaluator_hash: str,
    expected_exposure: float,
) -> dict[int, dict[str, Any]]:
    if receipt.get("script_sha256") != evaluator_hash:
        raise ValueError("Target evaluator hash mismatch")
    if receipt.get("external_test_used") is not False:
        raise ValueError("External test use declared")
    routing = receipt.get("routing_contract", {})
    if int(routing.get("specialist_target_crop_id", -1)) != 12:
        raise ValueError("Rice routing ID changed")
    if routing.get("pixel_inferred_routing_allowed") is not False:
        raise ValueError("Pixel-inferred routing was enabled")
    runs: dict[int, dict[str, Any]] = {}
    for run in receipt.get("runs", []):
        seed = int(run["seed"])
        if seed in runs:
            raise ValueError(f"Duplicate seed: {seed}")
        if run.get("source_tree_sha256") != expected_source:
            raise ValueError(f"Source tree mismatch: {seed}")
        if run.get("external_test_used") is not False:
            raise ValueError(f"External test flag changed: {seed}")
        if abs(float(run["riceseg_training_exposure"]) - expected_exposure) > 1e-12:
            raise ValueError(f"RiceSEG exposure mismatch: {seed}")
        runs[seed] = run
    if sorted(runs) != expected_seeds:
        raise ValueError(f"Wrong receipt seeds: {sorted(runs)}")
    return runs


def paired_confirmation(
    specialist_runs: Mapping[int, Mapping[str, Any]],
    fallback_runs: Mapping[int, Mapping[str, Any]],
    rules: Mapping[str, Any],
) -> dict[str, Any]:
    seeds = sorted(specialist_runs)
    paired: list[dict[str, Any]] = []
    for seed in seeds:
        specialist = target_summary(specialist_runs[seed])
        fallback = target_summary(fallback_runs[seed])
        deltas = {
            domain: float(specialist["domains"][domain])
            - float(fallback["domains"][domain])
            for domain in TARGET_DOMAINS
        }
        deltas["target_robust_mean_iou"] = float(
            specialist["target_robust_mean_iou"]
        ) - float(fallback["target_robust_mean_iou"])
        paired.append(
            {
                "seed": seed,
                "specialist": specialist,
                "fallback": fallback,
                "deltas": deltas,
                "target_robust_win": deltas["target_robust_mean_iou"] > 0,
            }
        )

    mean_deltas = {
        domain: statistics.fmean(item["deltas"][domain] for item in paired)
        for domain in (*TARGET_DOMAINS, "target_robust_mean_iou")
    }
    wins = sum(bool(item["target_robust_win"]) for item in paired)
    checks = {
        "early_rice_mean_gain": mean_deltas["early_rice"]
        >= float(rules["minimum_mean_early_rice_gain"]),
        "riceseg_mean_gain": mean_deltas["riceseg"]
        >= float(rules["minimum_mean_riceseg_gain"]),
        "riceseg_reproductive_mean_gain": mean_deltas["riceseg_reproductive"]
        >= float(rules["minimum_mean_riceseg_reproductive_gain"]),
        "target_robust_mean_gain": mean_deltas["target_robust_mean_iou"]
        >= float(rules["minimum_mean_target_robust_gain"]),
        "target_robust_seed_wins": wins
        >= int(rules["minimum_target_robust_wins_out_of_3"]),
    }
    return {
        "paired": paired,
        "mean_deltas": mean_deltas,
        "target_robust_wins": wins,
        "checks": checks,
        "accepted": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--specialist-receipt", required=True)
    parser.add_argument("--fallback-receipt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_object(protocol_path)
    if protocol.get("stage") != "confirmation":
        raise ValueError("Only a confirmation protocol is supported")
    if protocol.get("frozen_before_confirmation_training") is not True:
        raise ValueError("Protocol was not frozen before confirmation training")
    validate_locks(protocol)

    screen = load_object(protocol["locked_inputs"]["screen_selection"]["path"])
    if screen.get("confirmation_eligible") is not True:
        raise ValueError("Screen did not unlock confirmation")
    selected_name = str(protocol["selected_specialist"])
    if screen.get("selected_specialist") != selected_name:
        raise ValueError("Confirmation candidate differs from screen selection")

    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_object(benchmark_path)
    matrix_lock = protocol["locked_inputs"]["confirmation_matrix"]
    if Path(str(benchmark["matrix"])).resolve() != Path(
        str(matrix_lock["path"])
    ).resolve():
        raise ValueError("Benchmark used another confirmation matrix")
    benchmark_seeds = sorted(
        int(run["seed"])
        for run in benchmark.get("runs", [])
        if run.get("candidate") == selected_name
    )
    if benchmark_seeds != [29, 43]:
        raise ValueError(f"Wrong newly trained seeds: {benchmark_seeds}")

    seeds = [int(value) for value in protocol["confirmation_seeds"]]
    evaluator_hash = str(protocol["locked_inputs"]["target_evaluator"]["sha256"])
    expected_source = str(protocol["source_tree_sha256"])
    specialist_receipt_path = Path(args.specialist_receipt).resolve()
    fallback_receipt_path = Path(args.fallback_receipt).resolve()
    specialist_runs = index_receipt(
        load_object(specialist_receipt_path),
        expected_seeds=seeds,
        expected_source=expected_source,
        evaluator_hash=evaluator_hash,
        expected_exposure=float(protocol["selected_riceseg_exposure"]),
    )
    fallback_runs = index_receipt(
        load_object(fallback_receipt_path),
        expected_seeds=seeds,
        expected_source=expected_source,
        evaluator_hash=evaluator_hash,
        expected_exposure=0.0,
    )
    confirmation = paired_confirmation(
        specialist_runs, fallback_runs, protocol["confirmation_acceptance"]
    )

    representative: dict[str, Any] | None = None
    if confirmation["accepted"]:
        ordered = sorted(
            specialist_runs.values(),
            key=lambda run: target_summary(run)["target_robust_mean_iou"],
        )
        representative_run = ordered[len(ordered) // 2]
        representative = {
            "seed": int(representative_run["seed"]),
            "checkpoint": representative_run["checkpoint"],
            "checkpoint_sha256": representative_run["checkpoint_sha256"],
            **target_summary(representative_run),
            "rule": "median_target_robust_mean_iou_seed",
        }

    output = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "riceseg_crop_routed_specialist_three_seed_confirmation",
        "stage": "confirmation",
        "external_test_used": False,
        "spray_deployment_eligible": False,
        "accepted": confirmation["accepted"],
        "selected_specialist": selected_name if confirmation["accepted"] else None,
        "accepted_global_fallback": protocol["accepted_global_fallback"],
        "accepted_global_fallback_unchanged": True,
        "routing_contract": protocol["routing_contract"],
        "confirmation": confirmation,
        "representative_specialist": representative,
        "representative_global_fallback": protocol[
            "representative_global_fallback"
        ],
        "specialist_receipt": {
            "path": str(specialist_receipt_path),
            "sha256": sha256(specialist_receipt_path),
        },
        "fallback_receipt": {
            "path": str(fallback_receipt_path),
            "sha256": sha256(fallback_receipt_path),
        },
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "selector": str(Path(__file__).resolve()),
        "selector_sha256": sha256(Path(__file__).resolve()),
        "source_tree_sha256": expected_source,
    }
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(output_path), "accepted": output["accepted"]}, indent=2))


if __name__ == "__main__":
    main()
