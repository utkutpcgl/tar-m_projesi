#!/usr/bin/env python3
"""Apply the frozen reproductive-rice synthetic screen/confirmation rules."""

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


DEVELOPMENT_DOMAINS = {
    "cwfid",
    "sorghum_weed",
    "cropandweed",
    "early_rice",
    "riceseg",
    "riceseg_reproductive",
}


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


def validate_locked_inputs(protocol: dict[str, Any]) -> None:
    for name, specification in protocol["locked_inputs"].items():
        path = Path(str(specification["path"])).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != specification["sha256"]:
            raise ValueError(
                f"Locked input changed ({name}): {actual} != {specification['sha256']}"
            )


def points(run: dict[str, Any]) -> dict[str, float]:
    artifacts = run["artifacts"]
    if set(artifacts) != DEVELOPMENT_DOMAINS:
        raise ValueError(f"Unexpected development domains: {sorted(artifacts)}")
    return {
        "source": float(run["source_validation"]["mean_iou"]),
        **{
            name: float(artifacts[name]["mean_iou"])
            for name in sorted(DEVELOPMENT_DOMAINS)
        },
    }


def aggregate(values: dict[str, float]) -> dict[str, float]:
    return {
        "robust_mean_iou": min(values.values()),
        "macro_mean_iou": statistics.fmean(values.values()),
        **{f"{name}_mean_iou": value for name, value in values.items()},
    }


def subtract(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    return {key: left[key] - right[key] for key in left}


def screen_checks(delta: dict[str, float], rules: dict[str, Any]) -> dict[str, bool]:
    checks = {
        "robust_gain": delta["robust_mean_iou"]
        >= float(rules["robust_mean_iou_delta_must_be_at_least"]),
        "riceseg_gain": delta["riceseg_mean_iou"]
        >= float(rules["riceseg_mean_iou_delta_must_be_at_least"]),
        "riceseg_reproductive_gain": delta["riceseg_reproductive_mean_iou"]
        >= float(rules["riceseg_reproductive_mean_iou_delta_must_be_at_least"]),
        "macro_nonregression": delta["macro_mean_iou"]
        >= float(rules["macro_mean_iou_delta_must_be_at_least"]),
    }
    for domain, maximum in rules["maximum_existing_domain_mean_iou_regression"].items():
        checks[f"{domain}_noninferiority"] = delta[f"{domain}_mean_iou"] >= -float(maximum)
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--stage", choices=("screen", "confirmation"), required=True)
    parser.add_argument("--screen-receipt")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    protocol_path = Path(arguments.protocol).expanduser().resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Protocol was not frozen before challenger training")
    validate_locked_inputs(protocol)
    benchmark_path = Path(arguments.benchmark).expanduser().resolve()
    benchmark = load_json(benchmark_path)
    matrix_path = Path(benchmark["matrix"]).resolve()

    control = str(protocol["control"])
    challenger = str(protocol["challenger"])
    if arguments.stage == "screen":
        matrix_lock = protocol["locked_inputs"]["screen_matrix"]
        if matrix_path != Path(matrix_lock["path"]).resolve():
            raise ValueError("Benchmark does not use the frozen screen matrix")
        if sha256(matrix_path) != matrix_lock["sha256"]:
            raise ValueError("Screen matrix changed after protocol freeze")
        seeds = [int(protocol["screen_seed"])]
    else:
        if not arguments.screen_receipt:
            raise ValueError("Confirmation requires --screen-receipt")
        screen_path = Path(arguments.screen_receipt).expanduser().resolve()
        screen = load_json(screen_path)
        if screen.get("stage") != "screen":
            raise ValueError("Supplied receipt is not a screen receipt")
        if screen.get("frozen_protocol_sha256") != sha256(protocol_path):
            raise ValueError("Screen receipt used another protocol")
        if screen.get("selected_candidate") != challenger:
            raise ValueError("No accepted challenger is available for confirmation")
        seeds = [int(seed) for seed in protocol["confirmation_seeds"]]

    benchmark_runs: dict[tuple[str, int], dict[str, Any]] = {}
    for run in benchmark["runs"]:
        key = (str(run["candidate"]), int(run["seed"]))
        if key[0] in {control, challenger} and key[1] in seeds:
            if key in benchmark_runs:
                raise ValueError(f"Duplicate benchmark run: {key}")
            benchmark_runs[key] = run
    expected_keys = {(name, seed) for name in (control, challenger) for seed in seeds}
    missing = sorted(expected_keys - set(benchmark_runs))
    if missing:
        raise ValueError(f"Missing paired benchmark runs: {missing}")

    evaluator_hash = protocol["locked_inputs"]["evaluator_script"]["sha256"]
    seed_label = "-".join(str(seed) for seed in sorted(seeds))
    evaluations: dict[tuple[str, int], dict[str, Any]] = {}
    evaluation_locks: dict[str, dict[str, str]] = {}
    source_hashes: set[str] = set()
    for name in (control, challenger):
        candidate_dir = Path(benchmark_runs[(name, seeds[0])]["run_dir"]).parent
        receipt_path = candidate_dir / (
            f"reproductive_development_fixed_epoch{protocol['fixed_epoch']}_seeds_{seed_label}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluator hash mismatch: {receipt_path}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {receipt_path}")
        if receipt.get("real_rice_training_exposure") is not False:
            raise ValueError(f"Real Rice training exposure declared: {receipt_path}")
        if receipt.get("checkpoint") != protocol["checkpoint"]:
            raise ValueError(f"Wrong checkpoint policy: {receipt_path}")
        if int(receipt.get("fixed_epoch", -1)) != int(protocol["fixed_epoch"]):
            raise ValueError(f"Wrong fixed epoch: {receipt_path}")
        evaluation_locks[name] = {"path": str(receipt_path), "sha256": sha256(receipt_path)}
        for run in receipt["runs"]:
            seed = int(run["seed"])
            if seed not in seeds:
                continue
            key = (name, seed)
            if key in evaluations:
                raise ValueError(f"Duplicate evaluation: {key}")
            if Path(run["run_dir"]).resolve() != Path(benchmark_runs[key]["run_dir"]).resolve():
                raise ValueError(f"Run directory mismatch: {key}")
            if run.get("checkpoint_name") != protocol["checkpoint"]:
                raise ValueError(f"Wrong checkpoint: {key}")
            if run.get("real_rice_training_exposure") is not False:
                raise ValueError(f"Real Rice exposure: {key}")
            source_hashes.add(str(run["source_tree_sha256"]))
            benchmark_source = float(benchmark_runs[key]["source_validation"]["mean_iou"])
            fixed_source = float(run["source_validation"]["mean_iou"])
            if not math.isclose(benchmark_source, fixed_source, abs_tol=1e-12):
                raise ValueError(f"Source metric mismatch: {key}")
            evaluations[key] = run
    if source_hashes != {str(protocol["source_tree_sha256"])}:
        raise ValueError(f"Source-tree hashes are not frozen: {source_hashes}")
    if set(evaluations) != expected_keys:
        raise ValueError(f"Evaluation matrix mismatch: {sorted(set(evaluations))}")

    runs: list[dict[str, Any]] = []
    deltas: list[dict[str, float]] = []
    for seed in seeds:
        control_aggregate = aggregate(points(evaluations[(control, seed)]))
        challenger_aggregate = aggregate(points(evaluations[(challenger, seed)]))
        delta = subtract(challenger_aggregate, control_aggregate)
        deltas.append(delta)
        runs.extend(
            [
                {
                    "candidate": control,
                    "seed": seed,
                    "aggregate": control_aggregate,
                    "paired_deltas_vs_control": {key: 0.0 for key in control_aggregate},
                },
                {
                    "candidate": challenger,
                    "seed": seed,
                    "aggregate": challenger_aggregate,
                    "paired_deltas_vs_control": delta,
                },
            ]
        )

    if arguments.stage == "screen":
        checks = screen_checks(deltas[0], protocol["screen_acceptance_against_control"])
        accepted = all(checks.values())
        acceptance = {challenger: {"accepted": accepted, "checks": checks}}
        selected = challenger if accepted else control
    else:
        rules = protocol["confirmation_acceptance_against_control"]
        means = {
            key: statistics.fmean(delta[key] for delta in deltas)
            for key in deltas[0]
        }
        wins = sum(delta["robust_mean_iou"] > 0.0 for delta in deltas)
        checks = {
            "positive_mean_robust_gain": means["robust_mean_iou"]
            > float(rules["mean_robust_delta_must_be_greater_than"]),
            "minimum_robust_wins": wins >= int(rules["minimum_robust_wins_out_of_3"]),
            "mean_riceseg_gain": means["riceseg_mean_iou"]
            >= float(rules["mean_riceseg_delta_must_be_at_least"]),
            "mean_riceseg_reproductive_gain": means["riceseg_reproductive_mean_iou"]
            >= float(rules["mean_riceseg_reproductive_delta_must_be_at_least"]),
        }
        for domain, maximum in rules["maximum_mean_existing_domain_mean_iou_regression"].items():
            checks[f"{domain}_mean_noninferiority"] = means[f"{domain}_mean_iou"] >= -float(maximum)
        accepted = all(checks.values())
        acceptance = {
            challenger: {
                "accepted": accepted,
                "checks": checks,
                "mean_paired_deltas": means,
                "robust_wins": wins,
            }
        }
        selected = challenger if accepted else control

    representative = Path(evaluations[(selected, int(protocol["screen_seed"]))]["checkpoint"])
    output = Path(arguments.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": arguments.stage,
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "seeds": seeds,
        "runs": runs,
        "acceptance": acceptance,
        "selected_candidate": selected,
        "fallback_applied": selected == control,
        "evaluation_receipts": evaluation_locks,
        "representative_checkpoint": str(representative),
        "representative_checkpoint_sha256": sha256(representative),
        "source_tree_sha256": protocol["source_tree_sha256"],
        "external_test_used": False,
        "real_rice_training_exposure": False,
        "model_benefit_established": selected == challenger,
        "spray_deployment_eligible": False,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(Path(__file__).resolve()),
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
