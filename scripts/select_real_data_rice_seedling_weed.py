#!/usr/bin/env python3
"""Apply the frozen train-only Rice contribution protocol to a benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
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


def load_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def points(run: dict[str, Any], expected_development: set[str]) -> dict[str, float]:
    development = run["development"]
    if set(development) != expected_development:
        raise ValueError(
            f"Unexpected development domains for {run['candidate']}: "
            f"{sorted(development)}"
        )
    return {
        "source": float(run["source_validation"]["mean_iou"]),
        **{
            name: float(development[name]["mean_iou"])
            for name in sorted(expected_development)
        },
    }


def aggregate(values: dict[str, float]) -> dict[str, float]:
    return {
        "robust_mean_iou": min(values.values()),
        "macro_mean_iou": statistics.fmean(values.values()),
        **{f"{name}_mean_iou": value for name, value in values.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--stage", choices=("screen", "confirmation"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("frozen_before_training") is not True:
        raise ValueError("Selection protocol was not frozen before training")
    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_object(benchmark_path)
    matrix_path = Path(benchmark["matrix"]).resolve()
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))

    control = str(protocol["control"])
    candidate_dataset = str(protocol["candidate_dataset"])
    seeds = (
        [int(protocol["screen_seed"])]
        if args.stage == "screen"
        else [int(value) for value in protocol["confirmation_seeds"]]
    )
    expected_development = set(protocol["evaluation_domains"]) - {"source"}
    exposures: dict[str, float] = {}
    for candidate in matrix["candidates"]:
        name = str(candidate["name"])
        weights = candidate.get("training", {}).get("dataset_weights", {})
        exposures[name] = float(weights.get(candidate_dataset, 0.0))

    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    source_hashes: set[str] = set()
    runs: list[dict[str, Any]] = []
    for run in benchmark["runs"]:
        name, seed = str(run["candidate"]), int(run["seed"])
        if seed not in seeds:
            continue
        key = (name, seed)
        if key in indexed:
            raise ValueError(f"Duplicate benchmark run: {key}")
        indexed[key] = run
        summary_path = Path(run["run_dir"]) / "summary.json"
        summary = load_object(summary_path)
        source_hashes.add(str(summary["source_tree_sha256"]))
    if len(source_hashes) != 1:
        raise ValueError("All paired runs must use one source-tree hash")

    candidate_names = sorted(
        name for name in exposures if name != control and exposures[name] > 0
    )
    for seed in seeds:
        if (control, seed) not in indexed:
            raise ValueError(f"Missing control seed {seed}")
        control_values = points(indexed[(control, seed)], expected_development)
        control_aggregate = aggregate(control_values)
        runs.append(
            {
                "candidate": control,
                "seed": seed,
                "candidate_exposure": exposures[control],
                "domains": control_values,
                "aggregate": control_aggregate,
                "paired_deltas_vs_control": {
                    key: 0.0 for key in control_aggregate
                },
            }
        )
        for candidate in candidate_names:
            if (candidate, seed) not in indexed:
                raise ValueError(f"Missing challenger {candidate} seed {seed}")
            candidate_values = points(
                indexed[(candidate, seed)], expected_development
            )
            candidate_aggregate = aggregate(candidate_values)
            runs.append(
                {
                    "candidate": candidate,
                    "seed": seed,
                    "candidate_exposure": exposures[candidate],
                    "domains": candidate_values,
                    "aggregate": candidate_aggregate,
                    "paired_deltas_vs_control": {
                        key: candidate_aggregate[key] - control_aggregate[key]
                        for key in control_aggregate
                    },
                }
            )

    acceptance: dict[str, dict[str, Any]] = {}
    if args.stage == "screen":
        rules = protocol["screen_acceptance_against_control"]
        limits = rules["maximum_mean_iou_regression"]
        for candidate in candidate_names:
            run = next(value for value in runs if value["candidate"] == candidate)
            deltas = run["paired_deltas_vs_control"]
            checks = {
                "positive_primary_delta": deltas["robust_mean_iou"]
                > float(rules["primary_delta_must_be_greater_than"]),
                **{
                    f"{domain}_noninferiority": deltas[f"{domain}_mean_iou"]
                    >= -float(limit)
                    for domain, limit in limits.items()
                },
            }
            acceptance[candidate] = {
                "accepted": all(checks.values()),
                "checks": checks,
            }
    else:
        rules = protocol["confirmation_acceptance_against_control"]
        limits = rules["maximum_mean_mean_iou_regression"]
        for candidate in candidate_names:
            candidate_runs = [
                value for value in runs if value["candidate"] == candidate
            ]
            deltas = [value["paired_deltas_vs_control"] for value in candidate_runs]
            means = {
                key: statistics.fmean(delta[key] for delta in deltas)
                for key in deltas[0]
            }
            wins = sum(delta["robust_mean_iou"] > 0.0 for delta in deltas)
            checks = {
                "positive_mean_primary_delta": means["robust_mean_iou"]
                > float(rules["mean_paired_primary_delta_must_be_greater_than"]),
                "minimum_primary_wins": wins
                >= int(rules["minimum_primary_wins_out_of_3"]),
                **{
                    f"{domain}_mean_noninferiority": means[f"{domain}_mean_iou"]
                    >= -float(limit)
                    for domain, limit in limits.items()
                },
            }
            acceptance[candidate] = {
                "accepted": all(checks.values()),
                "checks": checks,
                "mean_paired_deltas": means,
                "primary_wins": wins,
            }

    eligible = [name for name in candidate_names if acceptance[name]["accepted"]]

    def candidate_key(name: str) -> tuple[float, float, float, float, float]:
        selected_runs = [value for value in runs if value["candidate"] == name]
        robust = [value["aggregate"]["robust_mean_iou"] for value in selected_runs]
        macro = [value["aggregate"]["macro_mean_iou"] for value in selected_runs]
        cropandweed = [
            value["aggregate"]["cropandweed_mean_iou"] for value in selected_runs
        ]
        return (
            statistics.fmean(robust),
            min(robust),
            statistics.fmean(macro),
            statistics.fmean(cropandweed),
            -exposures[name],
        )

    selected = max(eligible, key=candidate_key) if eligible else control
    selected_runs = [value for value in runs if value["candidate"] == selected]
    representative = sorted(
        selected_runs,
        key=lambda value: (value["aggregate"]["robust_mean_iou"], value["seed"]),
    )[len(selected_runs) // 2]
    representative_seed = int(representative["seed"])
    checkpoint = (
        Path(indexed[(selected, representative_seed)]["run_dir"])
        / str(protocol["checkpoint"])
    )

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(Path(__file__).resolve()),
        "source_tree_sha256": next(iter(source_hashes)),
        "seeds": seeds,
        "runs": runs,
        "acceptance": acceptance,
        "selected_candidate": selected,
        "selected_exposure": exposures[selected],
        "representative_seed": representative_seed,
        "representative_checkpoint": str(checkpoint.resolve()),
        "representative_checkpoint_sha256": sha256(checkpoint),
        "candidate_train_tiles_used_as_post_training_evaluation": False,
        "external_test_used": False,
        "spray_deployment_eligible": False,
    }
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
