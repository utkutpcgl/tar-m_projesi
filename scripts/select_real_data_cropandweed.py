#!/usr/bin/env python3
"""Apply the frozen CropAndWeed screen/confirmation acceptance protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
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


def compact(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "mean_iou": float(metrics["mean_iou"]),
        "crop_iou": float(metrics["iou"]["target_crop"]),
        "weed_iou": float(metrics["iou"]["other_vegetation"]),
    }


def control_points(
    benchmark: dict[str, Any],
    development: dict[str, Any],
    cropandweed_pattern: str,
    candidate: str,
    seeds: list[int],
) -> dict[int, dict[str, dict[str, float]]]:
    sources = {
        int(run["seed"]): run["source_validation"]
        for run in benchmark["runs"]
        if run["candidate"] == candidate
    }
    dev_runs = {int(run["seed"]): run for run in development["runs"]}
    output: dict[int, dict[str, dict[str, float]]] = {}
    for seed in seeds:
        if seed not in sources or seed not in dev_runs:
            raise ValueError(f"Missing control development metrics for seed {seed}")
        run_dir = Path(dev_runs[seed]["run_dir"])
        best = torch.load(run_dir / "best.pt", map_location="cpu", weights_only=False)
        last = torch.load(run_dir / "last.pt", map_location="cpu", weights_only=False)
        if best["model"].keys() != last["model"].keys() or not all(
            torch.equal(best["model"][key], last["model"][key])
            for key in best["model"]
        ):
            raise ValueError(f"Control best.pt and last.pt differ for seed {seed}")
        cropandweed_path = Path(cropandweed_pattern.format(seed=seed))
        cropandweed = load_json(cropandweed_path)
        output[seed] = {
            "source": {
                key: float(sources[seed][key])
                for key in ("mean_iou", "crop_iou", "weed_iou")
            },
            "cwfid": {
                key: float(dev_runs[seed]["artifacts"]["cwfid"][key])
                for key in ("mean_iou", "crop_iou", "weed_iou")
            },
            "sorghum_weed": {
                key: float(dev_runs[seed]["artifacts"]["sorghum_weed"][key])
                for key in ("mean_iou", "crop_iou", "weed_iou")
            },
            "cropandweed": compact(cropandweed),
        }
    return output


def challenger_points(
    benchmark: dict[str, Any], seeds: list[int]
) -> dict[str, dict[int, dict[str, dict[str, float]]]]:
    output: dict[str, dict[int, dict[str, dict[str, float]]]] = {}
    for run in benchmark["runs"]:
        seed = int(run["seed"])
        if seed not in seeds:
            continue
        development = run["development"]
        required = {"cwfid", "sorghum_weed", "cropandweed"}
        if set(development) != required:
            raise ValueError(
                f"Unexpected challenger development inputs: {sorted(development)}"
            )
        output.setdefault(str(run["candidate"]), {})[seed] = {
            "source": {
                key: float(run["source_validation"][key])
                for key in ("mean_iou", "crop_iou", "weed_iou")
            },
            **{
                name: {
                    key: float(development[name][key])
                    for key in ("mean_iou", "crop_iou", "weed_iou")
                }
                for name in required
            },
        }
    return output


def aggregate(points: dict[str, dict[str, float]]) -> dict[str, float]:
    values = [point["mean_iou"] for point in points.values()]
    return {
        "robust_mean_iou": min(values),
        "macro_mean_iou": statistics.fmean(values),
        "source_mean_iou": points["source"]["mean_iou"],
        "cwfid_mean_iou": points["cwfid"]["mean_iou"],
        "sorghum_weed_mean_iou": points["sorghum_weed"]["mean_iou"],
        "cropandweed_mean_iou": points["cropandweed"]["mean_iou"],
        "cropandweed_crop_iou": points["cropandweed"]["crop_iou"],
        "cropandweed_weed_iou": points["cropandweed"]["weed_iou"],
    }


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
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Selection protocol was not frozen before training")
    control_name = str(protocol["control"])
    seeds = (
        [int(protocol["screen_seed"])]
        if args.stage == "screen"
        else [int(value) for value in protocol["confirmation_seeds"]]
    )
    control_benchmark = load_json(args.control_benchmark)
    control_development = load_json(args.control_development)
    challenger_benchmark = load_json(args.challenger_benchmark)
    controls = control_points(
        control_benchmark,
        control_development,
        args.control_cropandweed_pattern,
        control_name,
        seeds,
    )
    challengers = challenger_points(challenger_benchmark, seeds)
    exposures = {control_name: 0.0}
    matrix_path = Path(challenger_benchmark["matrix"])
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    for candidate in matrix["candidates"]:
        name = str(candidate["name"])
        weights = candidate.get("training", {}).get("dataset_weights", {})
        exposures[name] = float(weights.get("cropandweed", 0.0))
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        control_aggregate = aggregate(controls[seed])
        runs.append(
            {
                "candidate": control_name,
                "seed": seed,
                "cropandweed_exposure": exposures[control_name],
                "points": controls[seed],
                "aggregate": control_aggregate,
                "paired_deltas_vs_control": {key: 0.0 for key in control_aggregate},
            }
        )
        for candidate, candidate_seeds in challengers.items():
            if seed not in candidate_seeds:
                raise ValueError(f"Missing challenger {candidate} seed {seed}")
            candidate_aggregate = aggregate(candidate_seeds[seed])
            runs.append(
                {
                    "candidate": candidate,
                    "seed": seed,
                    "cropandweed_exposure": exposures[candidate],
                    "points": candidate_seeds[seed],
                    "aggregate": candidate_aggregate,
                    "paired_deltas_vs_control": {
                        key: candidate_aggregate[key] - control_aggregate[key]
                        for key in control_aggregate
                    },
                }
            )

    candidate_names = sorted(challengers)
    acceptance: dict[str, dict[str, Any]] = {}
    if args.stage == "screen":
        rules = protocol["screen_acceptance_against_control"]
        seed = seeds[0]
        for candidate in candidate_names:
            run = next(
                value
                for value in runs
                if value["candidate"] == candidate and value["seed"] == seed
            )
            delta = run["paired_deltas_vs_control"]
            checks = {
                "primary_delta": delta["robust_mean_iou"]
                > float(rules["primary_delta_must_be_greater_than"]),
                "cropandweed_gain": delta["cropandweed_mean_iou"]
                >= float(rules["cropandweed_mean_iou_delta_must_be_at_least"]),
                "source_regression": delta["source_mean_iou"]
                >= -float(rules["maximum_source_validation_mean_iou_regression"]),
                "cwfid_regression": delta["cwfid_mean_iou"]
                >= -float(rules["maximum_cwfid_mean_iou_regression"]),
                "sorghum_regression": delta["sorghum_weed_mean_iou"]
                >= -float(rules["maximum_sorghum_validation_mean_iou_regression"]),
            }
            acceptance[candidate] = {"accepted": all(checks.values()), "checks": checks}
    else:
        rules = protocol["confirmation_acceptance_against_control"]
        for candidate in candidate_names:
            candidate_runs = [
                value for value in runs if value["candidate"] == candidate
            ]
            deltas = [value["paired_deltas_vs_control"] for value in candidate_runs]
            means = {
                key: statistics.fmean(value[key] for value in deltas)
                for key in deltas[0]
            }
            wins = sum(value["robust_mean_iou"] > 0 for value in deltas)
            checks = {
                "mean_primary_delta": means["robust_mean_iou"]
                > float(rules["mean_paired_primary_delta_must_be_greater_than"]),
                "primary_wins": wins
                >= int(rules["minimum_primary_wins_out_of_3"]),
                "mean_source_regression": means["source_mean_iou"]
                >= -float(
                    rules["maximum_mean_source_validation_mean_iou_regression"]
                ),
                "mean_cwfid_regression": means["cwfid_mean_iou"]
                >= -float(rules["maximum_mean_cwfid_mean_iou_regression"]),
                "mean_sorghum_regression": means["sorghum_weed_mean_iou"]
                >= -float(
                    rules["maximum_mean_sorghum_validation_mean_iou_regression"]
                ),
            }
            acceptance[candidate] = {
                "accepted": all(checks.values()),
                "checks": checks,
                "mean_paired_deltas": means,
                "primary_wins": wins,
            }

    eligible = [name for name in candidate_names if acceptance[name]["accepted"]]
    if args.stage == "screen":
        def screen_key(name: str) -> tuple[float, float, float, float]:
            run = next(value for value in runs if value["candidate"] == name)
            aggregate_values = run["aggregate"]
            return (
                aggregate_values["robust_mean_iou"],
                aggregate_values["macro_mean_iou"],
                aggregate_values["cropandweed_mean_iou"],
                -exposures[name],
            )

        selected = max(eligible, key=screen_key) if eligible else control_name
    else:
        def confirmation_key(name: str) -> tuple[float, float, float]:
            candidate_runs = [
                value for value in runs if value["candidate"] == name
            ]
            robust = [value["aggregate"]["robust_mean_iou"] for value in candidate_runs]
            macro = [value["aggregate"]["macro_mean_iou"] for value in candidate_runs]
            return (statistics.fmean(robust), min(robust), statistics.fmean(macro))

        selected = max(eligible, key=confirmation_key) if eligible else control_name

    selected_runs = [value for value in runs if value["candidate"] == selected]
    representative_seed = min(seeds)
    if args.stage == "confirmation" and selected != control_name:
        ordered = sorted(
            selected_runs,
            key=lambda value: (
                value["aggregate"]["robust_mean_iou"],
                value["seed"],
            ),
        )
        representative_seed = int(ordered[len(ordered) // 2]["seed"])
    challenger_run = next(
        (
            run
            for run in challenger_benchmark["runs"]
            if run["candidate"] == selected and int(run["seed"]) == representative_seed
        ),
        None,
    )
    if selected == control_name:
        checkpoint = Path(
            next(
                run["run_dir"]
                for run in control_benchmark["runs"]
                if run["candidate"] == control_name
                and int(run["seed"]) == representative_seed
            )
        ) / str(protocol["checkpoint"])
    else:
        if challenger_run is None:
            raise ValueError("Selected challenger run is absent")
        checkpoint = Path(challenger_run["run_dir"]) / str(protocol["checkpoint"])

    input_paths = {
        "protocol": Path(args.protocol).resolve(),
        "control_benchmark": Path(args.control_benchmark).resolve(),
        "control_development": Path(args.control_development).resolve(),
        "challenger_benchmark": Path(args.challenger_benchmark).resolve(),
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
        "seeds": seeds,
        "runs": runs,
        "acceptance": acceptance,
        "selected_candidate": selected,
        "selected_exposure": exposures[selected],
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
