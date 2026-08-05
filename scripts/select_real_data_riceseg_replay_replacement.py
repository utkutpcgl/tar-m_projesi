#!/usr/bin/env python3
"""Select the frozen fixed-compute exact-index RiceSEG replacement screen."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.select_real_data_riceseg_additive import (
    aggregate,
    load_json,
    load_yaml,
    screen_checks,
    sha256,
    validate_data_evidence,
    validate_locked_inputs,
)


def validate_replay_receipt(
    protocol: dict[str, Any], candidate_run: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    contract = protocol["exact_replay_replacement"]
    path = Path(str(contract["receipt_path"])).resolve()
    receipt = load_json(path)
    if receipt.get("status") != "complete":
        raise ValueError("Exact replay receipt is not complete")
    if receipt.get("role") != "exact_index_replay_fixed_compute_riceseg_replacement":
        raise ValueError("Unexpected exact replay receipt role")
    trainer_hash = str(protocol["locked_inputs"]["replay_trainer_script"]["sha256"])
    if receipt.get("script_sha256") != trainer_hash:
        raise ValueError("Exact replay trainer script mismatch")
    if receipt.get("matrix_sha256") != str(
        protocol["locked_inputs"]["screen_matrix"]["sha256"]
    ):
        raise ValueError("Exact replay receipt matrix mismatch")
    if receipt.get("source_tree_sha256") != str(protocol["source_tree_sha256"]):
        raise ValueError("Exact replay receipt source-tree mismatch")
    run_dir = Path(str(candidate_run["run_dir"])).resolve()
    if Path(str(receipt.get("run_dir"))).resolve() != run_dir:
        raise ValueError("Exact replay receipt run directory mismatch")
    checkpoint = run_dir / str(protocol["checkpoint"])
    if receipt.get("checkpoint_sha256") != sha256(checkpoint):
        raise ValueError("Exact replay receipt checkpoint mismatch")

    resolved_yaml = load_yaml(receipt["resolved_config"])
    resolved_json = load_json(run_dir / "config.resolved.json")
    if resolved_yaml != resolved_json:
        raise ValueError("Exact replay preflight and trained configs differ")
    evidence = receipt.get("evidence", {})
    if evidence.get("passed") is not True:
        raise ValueError("Exact replay evidence did not pass")
    expected_draws = int(contract["draws_per_epoch"])
    expected_replacements = int(contract["replacements_per_epoch"])
    expected_exposure = float(contract["target_exposure"])
    if int(evidence.get("draws_per_epoch", -1)) != expected_draws:
        raise ValueError("Exact replay draw budget mismatch")
    if int(evidence.get("replacements_per_epoch", -1)) != expected_replacements:
        raise ValueError("Exact replay replacement count mismatch")
    if not math.isclose(
        float(evidence.get("target_exposure", -1.0)),
        expected_exposure,
        abs_tol=1e-12,
    ):
        raise ValueError("Exact replay target exposure mismatch")
    epochs = evidence.get("per_epoch", [])
    if len(epochs) != int(protocol["fixed_epoch"]):
        raise ValueError("Exact replay epoch evidence is incomplete")
    expected_kept = expected_draws - expected_replacements
    for item in epochs:
        if item.get("all_non_replaced_positions_match") is not True:
            raise ValueError("A non-replaced baseline position changed")
        if item.get("target_position_contract_passed") is not True:
            raise ValueError("Target replacement positions changed")
        if int(item.get("exact_kept_position_matches", -1)) != expected_kept:
            raise ValueError("Wrong number of exact baseline position matches")
        if int(item.get("target_draws", -1)) != expected_replacements:
            raise ValueError("Wrong number of target draws in an epoch")
    if int(evidence.get("target_group_draw_min", 0)) <= 0:
        raise ValueError("At least one RiceSEG training group was never sampled")
    return receipt, {"path": str(path), "sha256": sha256(path)}


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
    challenger = str(protocol["screen_candidate"])
    expected_names = {accepted_control, challenger}
    indexed_benchmark: dict[str, dict[str, Any]] = {}
    for run in benchmark["runs"]:
        name = str(run["candidate"])
        if name in expected_names and int(run["seed"]) == seed:
            if name in indexed_benchmark:
                raise ValueError(f"Duplicate benchmark run: {name}/{seed}")
            indexed_benchmark[name] = run
    if set(indexed_benchmark) != expected_names:
        raise ValueError(
            f"Missing benchmark runs: {sorted(expected_names - set(indexed_benchmark))}"
        )

    expected_source = str(protocol["source_tree_sha256"])
    evaluator_hash = str(protocol["locked_inputs"]["evaluator_script"]["sha256"])
    expected_exposure = {
        str(name): float(value)
        for name, value in protocol["candidate_riceseg_exposure"].items()
    }
    expected_rows = {
        str(name): int(value)
        for name, value in protocol["expected_riceseg_training_rows"].items()
    }
    expected_samples = {
        str(name): int(value)
        for name, value in protocol["candidate_samples_per_epoch"].items()
    }
    indexed_evaluations: dict[str, dict[str, Any]] = {}
    evaluation_locks: dict[str, dict[str, str]] = {}
    for name in sorted(expected_names):
        run_dir = Path(str(indexed_benchmark[name]["run_dir"])).resolve()
        receipt_path = run_dir.parent / (
            f"riceseg_additive_development_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {name}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {name}")
        runs = receipt.get("runs", [])
        if len(runs) != 1 or int(runs[0].get("seed", -1)) != seed:
            raise ValueError(f"Evaluation receipt has wrong seed: {name}")
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
        if not math.isclose(
            float(run["riceseg_training_exposure"]),
            expected_exposure[name],
            abs_tol=1e-12,
        ):
            raise ValueError(f"RiceSEG exposure mismatch: {name}")
        if int(run["riceseg_training_rows"]) != expected_rows[name]:
            raise ValueError(f"RiceSEG training-row mismatch: {name}")
        if int(run["samples_per_epoch"]) != expected_samples[name]:
            raise ValueError(f"Samples-per-epoch mismatch: {name}")
        source_metric = float(indexed_benchmark[name]["source_validation"]["mean_iou"])
        if not math.isclose(
            source_metric, float(run["source_validation"]["mean_iou"]), abs_tol=1e-12
        ):
            raise ValueError(f"Source validation mismatch: {name}")
        indexed_evaluations[name] = run
        evaluation_locks[name] = {
            "path": str(receipt_path),
            "sha256": sha256(receipt_path),
        }

    replay_receipt, replay_lock = validate_replay_receipt(
        protocol, indexed_evaluations[challenger]
    )

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
    for name in (accepted_control, challenger):
        run = indexed_evaluations[name]
        artifacts = run["artifacts"]
        if set(artifacts) != expected_artifacts:
            raise ValueError(f"Unexpected evaluation artifacts for {name}")
        values = {"source": float(run["source_validation"]["mean_iou"])}
        values.update(
            {
                domain: float(artifacts[domain]["mean_iou"])
                for domain in sorted(
                    expected_artifacts - {"deblur_sharp", "deblur_motion_blur"}
                )
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
                    "deblur_sharp_mean_iou": float(
                        artifacts["deblur_sharp"]["mean_iou"]
                    ),
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
    delta = {
        key: aggregates[challenger][key] - aggregates[accepted_control][key]
        for key in aggregates[challenger]
    }
    checks = screen_checks(delta, protocol["screen_acceptance"])
    accepted = all(checks.values())

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "screen",
        "role": "riceseg_exact_index_fixed_compute_replacement_selection",
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "source_tree_sha256": expected_source,
        "seeds": [seed],
        "runs": rows,
        "comparison": {
            "comparator": accepted_control,
            "accepted": accepted,
            "checks": checks,
            "deltas": delta,
        },
        "screen_candidate_accepted": accepted,
        "confirmation_eligible": accepted,
        "selected_candidate": challenger if accepted else accepted_control,
        "fallback_applied": not accepted,
        "model_benefit_established": False,
        "evaluation_receipts": evaluation_locks,
        "exact_replay_receipt": replay_lock,
        "exact_replay_summary": replay_receipt["evidence"],
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
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
