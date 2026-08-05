#!/usr/bin/env python3
"""Select a replay-preserving CropAndWeed follow-up against two controls."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from select_real_data_cropandweed import (
    aggregate,
    challenger_points,
    control_points,
    load_json,
    sha256,
)


def subtract(
    left: dict[str, float], right: dict[str, float]
) -> dict[str, float]:
    return {key: left[key] - right[key] for key in left}


def means(rows: list[dict[str, float]]) -> dict[str, float]:
    return {
        key: statistics.fmean(row[key] for row in rows) for key in rows[0]
    }


def common_screen_checks(
    delta: dict[str, float], rules: dict[str, Any]
) -> dict[str, bool]:
    return {
        "primary_delta_vs_original": delta["robust_mean_iou"]
        > float(rules["primary_delta_must_be_greater_than"]),
        "source_regression_vs_original": delta["source_mean_iou"]
        >= -float(rules["maximum_source_validation_mean_iou_regression"]),
        "cwfid_regression_vs_original": delta["cwfid_mean_iou"]
        >= -float(rules["maximum_cwfid_mean_iou_regression"]),
        "sorghum_regression_vs_original": delta["sorghum_weed_mean_iou"]
        >= -float(rules["maximum_sorghum_validation_mean_iou_regression"]),
    }


def common_confirmation_checks(
    deltas: list[dict[str, float]], rules: dict[str, Any]
) -> tuple[dict[str, bool], dict[str, float], int]:
    mean_delta = means(deltas)
    wins = sum(delta["robust_mean_iou"] > 0 for delta in deltas)
    checks = {
        "mean_primary_delta_vs_original": mean_delta["robust_mean_iou"]
        > float(rules["mean_paired_primary_delta_must_be_greater_than"]),
        "primary_wins_vs_original": wins
        >= int(rules["minimum_primary_wins_out_of_3"]),
        "mean_source_regression_vs_original": mean_delta["source_mean_iou"]
        >= -float(
            rules["maximum_mean_source_validation_mean_iou_regression"]
        ),
        "mean_cwfid_regression_vs_original": mean_delta["cwfid_mean_iou"]
        >= -float(rules["maximum_mean_cwfid_mean_iou_regression"]),
        "mean_sorghum_regression_vs_original": mean_delta[
            "sorghum_weed_mean_iou"
        ]
        >= -float(
            rules["maximum_mean_sorghum_validation_mean_iou_regression"]
        ),
    }
    return checks, mean_delta, wins


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--control-benchmark", required=True)
    parser.add_argument("--control-development", required=True)
    parser.add_argument("--control-cropandweed-pattern", required=True)
    parser.add_argument("--challenger-benchmark", required=True)
    parser.add_argument("--stage", choices=("screen", "confirmation"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("frozen_before_training") is not True:
        raise ValueError("Selection protocol was not frozen before training")

    original = str(protocol["original_control"])
    matched = str(protocol["matched_compute_control"])
    additive = str(protocol["additive_candidate"])
    seeds = (
        [int(protocol["screen_seed"])]
        if args.stage == "screen"
        else [int(value) for value in protocol["confirmation_seeds"]]
    )

    control_benchmark = load_json(args.control_benchmark)
    control_development = load_json(args.control_development)
    challenger_benchmark = load_json(args.challenger_benchmark)
    original_points = control_points(
        control_benchmark,
        control_development,
        args.control_cropandweed_pattern,
        original,
        seeds,
    )
    candidate_points = challenger_points(challenger_benchmark, seeds)
    if set(candidate_points) != {matched, additive}:
        raise ValueError(
            "Expected exactly matched compute control and additive candidate; "
            f"found {sorted(candidate_points)}"
        )

    aggregates: dict[str, dict[int, dict[str, float]]] = {
        original: {seed: aggregate(original_points[seed]) for seed in seeds},
        matched: {
            seed: aggregate(candidate_points[matched][seed]) for seed in seeds
        },
        additive: {
            seed: aggregate(candidate_points[additive][seed]) for seed in seeds
        },
    }
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        original_aggregate = aggregates[original][seed]
        matched_aggregate = aggregates[matched][seed]
        for candidate in (original, matched, additive):
            points = (
                original_points[seed]
                if candidate == original
                else candidate_points[candidate][seed]
            )
            item: dict[str, Any] = {
                "candidate": candidate,
                "seed": seed,
                "points": points,
                "aggregate": aggregates[candidate][seed],
                "paired_deltas_vs_original": subtract(
                    aggregates[candidate][seed], original_aggregate
                ),
            }
            if candidate == additive:
                item["paired_deltas_vs_matched_control"] = subtract(
                    aggregates[candidate][seed], matched_aggregate
                )
            runs.append(item)

    acceptance: dict[str, dict[str, Any]] = {}
    if args.stage == "screen":
        common_rules = protocol["screen_acceptance_against_original"]
        additive_rules = protocol["screen_additive_requirements"]
        seed = seeds[0]
        matched_delta = subtract(
            aggregates[matched][seed], aggregates[original][seed]
        )
        matched_checks = common_screen_checks(matched_delta, common_rules)
        acceptance[matched] = {
            "accepted": all(matched_checks.values()),
            "checks": matched_checks,
        }

        original_delta = subtract(
            aggregates[additive][seed], aggregates[original][seed]
        )
        compute_delta = subtract(
            aggregates[additive][seed], aggregates[matched][seed]
        )
        additive_checks = {
            **common_screen_checks(original_delta, common_rules),
            "cropandweed_gain_vs_original": original_delta[
                "cropandweed_mean_iou"
            ]
            >= float(
                additive_rules[
                    "cropandweed_mean_iou_delta_vs_original_must_be_at_least"
                ]
            ),
            "primary_delta_vs_matched_control": compute_delta[
                "robust_mean_iou"
            ]
            > float(
                additive_rules[
                    "primary_delta_vs_matched_control_must_be_greater_than"
                ]
            ),
            "cropandweed_gain_vs_matched_control": compute_delta[
                "cropandweed_mean_iou"
            ]
            >= float(
                additive_rules[
                    "cropandweed_mean_iou_delta_vs_matched_control_must_be_at_least"
                ]
            ),
            "source_regression_vs_matched_control": compute_delta[
                "source_mean_iou"
            ]
            >= -float(
                additive_rules[
                    "maximum_source_validation_regression_vs_matched_control"
                ]
            ),
            "cwfid_regression_vs_matched_control": compute_delta["cwfid_mean_iou"]
            >= -float(
                additive_rules["maximum_cwfid_regression_vs_matched_control"]
            ),
            "sorghum_regression_vs_matched_control": compute_delta[
                "sorghum_weed_mean_iou"
            ]
            >= -float(
                additive_rules["maximum_sorghum_regression_vs_matched_control"]
            ),
        }
        acceptance[additive] = {
            "accepted": all(additive_checks.values()),
            "checks": additive_checks,
        }
    else:
        common_rules = protocol["confirmation_acceptance_against_original"]
        additive_rules = protocol["confirmation_additive_requirements"]
        for candidate in (matched, additive):
            original_deltas = [
                subtract(aggregates[candidate][seed], aggregates[original][seed])
                for seed in seeds
            ]
            checks, mean_delta, wins = common_confirmation_checks(
                original_deltas, common_rules
            )
            record: dict[str, Any] = {
                "checks": checks,
                "mean_paired_deltas_vs_original": mean_delta,
                "primary_wins_vs_original": wins,
            }
            if candidate == additive:
                compute_deltas = [
                    subtract(aggregates[additive][seed], aggregates[matched][seed])
                    for seed in seeds
                ]
                mean_compute_delta = means(compute_deltas)
                compute_wins = sum(
                    delta["robust_mean_iou"] > 0 for delta in compute_deltas
                )
                checks.update(
                    {
                        "mean_cropandweed_gain_vs_original": mean_delta[
                            "cropandweed_mean_iou"
                        ]
                        >= float(
                            additive_rules[
                                "mean_cropandweed_delta_vs_original_must_be_at_least"
                            ]
                        ),
                        "mean_primary_delta_vs_matched_control": mean_compute_delta[
                            "robust_mean_iou"
                        ]
                        > float(
                            additive_rules[
                                "mean_primary_delta_vs_matched_control_must_be_greater_than"
                            ]
                        ),
                        "primary_wins_vs_matched_control": compute_wins
                        >= int(
                            additive_rules[
                                "minimum_primary_wins_vs_matched_control_out_of_3"
                            ]
                        ),
                        "mean_cropandweed_gain_vs_matched_control": mean_compute_delta[
                            "cropandweed_mean_iou"
                        ]
                        >= float(
                            additive_rules[
                                "mean_cropandweed_delta_vs_matched_control_must_be_at_least"
                            ]
                        ),
                        "mean_source_regression_vs_matched_control": mean_compute_delta[
                            "source_mean_iou"
                        ]
                        >= -float(
                            additive_rules[
                                "maximum_mean_source_regression_vs_matched_control"
                            ]
                        ),
                        "mean_cwfid_regression_vs_matched_control": mean_compute_delta[
                            "cwfid_mean_iou"
                        ]
                        >= -float(
                            additive_rules[
                                "maximum_mean_cwfid_regression_vs_matched_control"
                            ]
                        ),
                        "mean_sorghum_regression_vs_matched_control": mean_compute_delta[
                            "sorghum_weed_mean_iou"
                        ]
                        >= -float(
                            additive_rules[
                                "maximum_mean_sorghum_regression_vs_matched_control"
                            ]
                        ),
                    }
                )
                record["mean_paired_deltas_vs_matched_control"] = (
                    mean_compute_delta
                )
                record["primary_wins_vs_matched_control"] = compute_wins
            record["accepted"] = all(checks.values())
            acceptance[candidate] = record

    eligible = [name for name in (matched, additive) if acceptance[name]["accepted"]]
    if args.stage == "screen":
        selected = (
            max(
                eligible,
                key=lambda name: (
                    aggregates[name][seeds[0]]["robust_mean_iou"],
                    aggregates[name][seeds[0]]["macro_mean_iou"],
                    aggregates[name][seeds[0]]["cropandweed_mean_iou"],
                ),
            )
            if eligible
            else original
        )
    else:
        selected = (
            max(
                eligible,
                key=lambda name: (
                    statistics.fmean(
                        aggregates[name][seed]["robust_mean_iou"] for seed in seeds
                    ),
                    min(aggregates[name][seed]["robust_mean_iou"] for seed in seeds),
                    statistics.fmean(
                        aggregates[name][seed]["macro_mean_iou"] for seed in seeds
                    ),
                ),
            )
            if eligible
            else original
        )

    selected_order = sorted(
        seeds,
        key=lambda seed: (aggregates[selected][seed]["robust_mean_iou"], seed),
    )
    representative_seed = selected_order[len(selected_order) // 2]
    if selected == original:
        run_dir = Path(
            next(
                run["run_dir"]
                for run in control_benchmark["runs"]
                if run["candidate"] == original
                and int(run["seed"]) == representative_seed
            )
        )
    else:
        run_dir = Path(
            next(
                run["run_dir"]
                for run in challenger_benchmark["runs"]
                if run["candidate"] == selected
                and int(run["seed"]) == representative_seed
            )
        )
    checkpoint = run_dir / str(protocol["checkpoint"])

    input_paths = {
        "protocol": Path(args.protocol).resolve(),
        "control_benchmark": Path(args.control_benchmark).resolve(),
        "control_development": Path(args.control_development).resolve(),
        "challenger_benchmark": Path(args.challenger_benchmark).resolve(),
    }
    control_cropandweed = {
        str(seed): {
            "path": str(Path(args.control_cropandweed_pattern.format(seed=seed)).resolve()),
            "sha256": sha256(args.control_cropandweed_pattern.format(seed=seed)),
        }
        for seed in seeds
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "frozen_protocol": str(protocol_path),
        "frozen_protocol_sha256": sha256(protocol_path),
        "inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in input_paths.items()
        },
        "control_cropandweed_inputs": control_cropandweed,
        "seeds": seeds,
        "runs": runs,
        "acceptance": acceptance,
        "selected_candidate": selected,
        "representative_seed": representative_seed,
        "representative_checkpoint": str(checkpoint.resolve()),
        "representative_checkpoint_sha256": sha256(checkpoint),
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
