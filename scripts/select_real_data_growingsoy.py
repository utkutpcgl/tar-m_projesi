#!/usr/bin/env python3
"""Apply the frozen GrowingSoy real-data screen/confirmation protocol."""

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
    "rice",
    "growingsoy",
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


def load_yaml(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def validate_locked_inputs(document: dict[str, Any]) -> None:
    for name, lock in document["locked_inputs"].items():
        path = Path(lock["path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != lock["sha256"]:
            raise ValueError(
                f"Locked input changed ({name}): {actual} != {lock['sha256']}"
            )


def locked_json(document: dict[str, Any], name: str) -> dict[str, Any]:
    return load_json(Path(document["locked_inputs"][name]["path"]).resolve())


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    conversion = locked_json(protocol, "growingsoy_conversion_report")
    if conversion.get("all_quality_gates_passed") is not True:
        raise ValueError("GrowingSoy conversion quality gate did not pass")
    if conversion.get("split_counts") != {"train": 541, "external_calibration": 459}:
        raise ValueError("Unexpected GrowingSoy role counts")
    provenance = conversion.get("provenance", {})
    if provenance.get("revision") != protocol["growingsoy_source_revision"]:
        raise ValueError("GrowingSoy source revision mismatch")

    for name, samples in (
        ("growingsoy_manifest_audit", 1000),
        ("challenger_manifest_audit", 6444),
    ):
        audit = locked_json(protocol, name)
        if int(audit.get("samples", -1)) != samples:
            raise ValueError(f"Unexpected sample count in {name}")
        for field in ("missing_files", "invalid_masks", "shape_mismatches"):
            if int(audit.get(field, -1)) != 0:
                raise ValueError(f"{name} failed: {field}={audit.get(field)}")

    cross_split = locked_json(protocol, "growingsoy_cross_split_duplicate_audit")
    if int(cross_split.get("match_count", -1)) != 0:
        raise ValueError("GrowingSoy train/calibration near-duplicate leakage")

    cross_source = locked_json(protocol, "growingsoy_cross_source_duplicate_audit")
    if cross_source.get("passed") is not True:
        raise ValueError("GrowingSoy cross-source duplicate gate did not pass")
    for field in (
        "candidate_to_reference_match_count",
        "within_candidate_cross_split_match_count",
    ):
        if int(cross_source.get(field, -1)) != 0:
            raise ValueError(f"Cross-source audit failed: {field}")

    visual = locked_json(protocol, "growingsoy_manual_visual_review")
    if visual.get("passed") is not True:
        raise ValueError("GrowingSoy manual visual review did not pass")

    challenger = locked_json(protocol, "challenger_manifest_receipt")
    if challenger.get("session_audit", {}).get("passed") is not True:
        raise ValueError("Challenger trajectory-disjointness gate did not pass")
    if challenger.get("role_policy", {}).get("external_test_present") is not False:
        raise ValueError("Challenger manifest contains an external test role")


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


def validate_confirmation_freeze(
    freeze_path: Path,
    protocol_path: Path,
    screen_path: Path,
    matrix_path: Path,
    control: str,
    winner: str,
    seeds: list[int],
) -> dict[str, Any]:
    freeze = load_yaml(freeze_path)
    if freeze.get("frozen_before_seed_29_or_43_training") is not True:
        raise ValueError("Confirmation was not frozen before new-seed training")
    validate_locked_inputs(freeze)
    locks = freeze["locked_inputs"]
    expected = {
        "parent_protocol": protocol_path,
        "screen_selection_receipt": screen_path,
        "confirmation_matrix": matrix_path,
    }
    for name, path in expected.items():
        if Path(locks[name]["path"]).resolve() != path:
            raise ValueError(f"Confirmation freeze points to another {name}")
        if locks[name]["sha256"] != sha256(path):
            raise ValueError(f"Confirmation freeze hash mismatch: {name}")
    if str(freeze.get("control")) != control:
        raise ValueError("Confirmation freeze control mismatch")
    if str(freeze.get("selected_screen_winner")) != winner:
        raise ValueError("Confirmation freeze winner mismatch")
    if [int(value) for value in freeze.get("seeds", [])] != seeds:
        raise ValueError("Confirmation freeze seeds mismatch")
    return freeze


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--stage", choices=("screen", "confirmation"), required=True)
    parser.add_argument("--screen-receipt")
    parser.add_argument("--confirmation-freeze")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_yaml(protocol_path)
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Protocol was not frozen before challenger training")
    validate_locked_inputs(protocol)
    validate_data_evidence(protocol)

    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_json(benchmark_path)
    matrix_path = Path(benchmark["matrix"]).resolve()
    control = str(protocol["control"])
    confirmation_freeze_path: Path | None = None
    confirmation_freeze: dict[str, Any] | None = None
    screen_path: Path | None = None

    if args.stage == "screen":
        matrix_lock = protocol["locked_inputs"]["screen_matrix"]
        if matrix_path != Path(matrix_lock["path"]).resolve():
            raise ValueError("Benchmark does not use the frozen screen matrix")
        if sha256(matrix_path) != matrix_lock["sha256"]:
            raise ValueError("Screen matrix changed after protocol freeze")
        seeds = [int(protocol["screen_seed"])]
        candidate_names = [str(value) for value in protocol["screen_candidates"]]
    else:
        if not args.screen_receipt or not args.confirmation_freeze:
            raise ValueError(
                "Confirmation requires --screen-receipt and --confirmation-freeze"
            )
        screen_path = Path(args.screen_receipt).resolve()
        screen = load_json(screen_path)
        if screen.get("stage") != "screen":
            raise ValueError("The supplied receipt is not a screen receipt")
        if screen.get("frozen_protocol_sha256") != sha256(protocol_path):
            raise ValueError("Screen receipt used another frozen protocol")
        winner = str(screen["selected_candidate"])
        if winner == control:
            raise ValueError("There is no accepted challenger to confirm")
        if winner not in protocol["screen_candidates"]:
            raise ValueError("Screen selected an undeclared challenger")
        seeds = [int(value) for value in protocol["confirmation_seeds"]]
        candidate_names = [winner]
        confirmation_freeze_path = Path(args.confirmation_freeze).resolve()
        confirmation_freeze = validate_confirmation_freeze(
            confirmation_freeze_path,
            protocol_path,
            screen_path,
            matrix_path,
            control,
            winner,
            seeds,
        )

    expected_names = {control, *candidate_names}
    indexed_benchmark: dict[tuple[str, int], dict[str, Any]] = {}
    for run in benchmark["runs"]:
        key = (str(run["candidate"]), int(run["seed"]))
        if key[0] in expected_names and key[1] in seeds:
            if key in indexed_benchmark:
                raise ValueError(f"Duplicate benchmark run: {key}")
            indexed_benchmark[key] = run
    missing = [
        (name, seed)
        for name in sorted(expected_names)
        for seed in seeds
        if (name, seed) not in indexed_benchmark
    ]
    if missing:
        raise ValueError(f"Missing paired benchmark runs: {missing}")

    seed_label = "-".join(str(seed) for seed in sorted(seeds))
    indexed_evaluations: dict[tuple[str, int], dict[str, Any]] = {}
    evaluation_receipt_locks: dict[str, dict[str, str]] = {}
    source_hashes: set[str] = set()
    evaluator_hash = protocol["locked_inputs"]["evaluator_script"]["sha256"]
    expected_exposures = {
        str(name): float(value)
        for name, value in protocol["candidate_growingsoy_exposure"].items()
    }
    if not expected_names.issubset(expected_exposures):
        raise ValueError("Protocol exposure map is missing a compared candidate")

    for name in sorted(expected_names):
        run_dir = Path(indexed_benchmark[(name, seeds[0])]["run_dir"])
        candidate_dir = run_dir.parent
        receipt_path = candidate_dir / (
            f"growingsoy_development_fixed_epoch{protocol['fixed_epoch']}_"
            f"seeds_{seed_label}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {receipt_path}")
        if receipt.get("external_test_used") is not False:
            raise ValueError(f"External test use declared: {receipt_path}")
        if receipt.get("real_rice_training_exposure") is not False:
            raise ValueError(f"Real Rice exposure declared: {receipt_path}")
        if receipt.get("growingsoy_external_calibration_exposure") is not False:
            raise ValueError(f"GrowingSoy calibration exposure declared: {receipt_path}")
        if receipt.get("checkpoint") != protocol["checkpoint"]:
            raise ValueError(f"Wrong checkpoint policy: {receipt_path}")
        if int(receipt.get("fixed_epoch", -1)) != int(protocol["fixed_epoch"]):
            raise ValueError(f"Wrong fixed epoch: {receipt_path}")
        evaluation_receipt_locks[name] = {
            "path": str(receipt_path),
            "sha256": sha256(receipt_path),
        }
        receipt_seeds = sorted(int(run["seed"]) for run in receipt["runs"])
        if receipt_seeds != sorted(seeds):
            raise ValueError(f"Evaluation receipt has wrong seeds: {receipt_path}")
        for run in receipt["runs"]:
            seed = int(run["seed"])
            key = (name, seed)
            if key in indexed_evaluations:
                raise ValueError(f"Duplicate fixed-epoch evaluation: {key}")
            if Path(run["run_dir"]).resolve() != Path(
                indexed_benchmark[key]["run_dir"]
            ).resolve():
                raise ValueError(f"Run directory mismatch: {key}")
            if run.get("checkpoint_name") != protocol["checkpoint"]:
                raise ValueError(f"Run used wrong checkpoint: {key}")
            if run.get("real_rice_training_exposure") is not False:
                raise ValueError(f"Run trained on real Rice: {key}")
            if run.get("growingsoy_external_calibration_exposure") is not False:
                raise ValueError(f"Calibration leakage declared: {key}")
            exposure = float(run["growingsoy_training_exposure"])
            if not math.isclose(exposure, expected_exposures[name], abs_tol=1e-12):
                raise ValueError(f"GrowingSoy exposure mismatch: {key}")
            source_hashes.add(str(run["source_tree_sha256"]))
            benchmark_source = float(
                indexed_benchmark[key]["source_validation"]["mean_iou"]
            )
            fixed_source = float(run["source_validation"]["mean_iou"])
            if not math.isclose(benchmark_source, fixed_source, abs_tol=1e-12):
                raise ValueError(f"Source metric mismatch: {key}")
            indexed_evaluations[key] = run
    if source_hashes != {str(protocol["source_tree_sha256"])}:
        raise ValueError(f"Source-tree hashes are not frozen: {source_hashes}")

    runs: list[dict[str, Any]] = []
    for seed in seeds:
        control_values = points(indexed_evaluations[(control, seed)])
        control_aggregate = aggregate(control_values)
        runs.append(
            {
                "candidate": control,
                "seed": seed,
                "domains": control_values,
                "aggregate": control_aggregate,
                "paired_deltas_vs_control": {
                    key: 0.0 for key in control_aggregate
                },
            }
        )
        for candidate in candidate_names:
            candidate_values = points(indexed_evaluations[(candidate, seed)])
            candidate_aggregate = aggregate(candidate_values)
            runs.append(
                {
                    "candidate": candidate,
                    "seed": seed,
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
        limits = rules["maximum_existing_domain_mean_iou_regression"]
        for candidate in candidate_names:
            run = next(value for value in runs if value["candidate"] == candidate)
            delta = run["paired_deltas_vs_control"]
            checks = {
                "robust_gain": delta["robust_mean_iou"]
                >= float(rules["robust_mean_iou_delta_must_be_at_least"]),
                "growingsoy_gain": delta["growingsoy_mean_iou"]
                >= float(rules["growingsoy_mean_iou_delta_must_be_at_least"]),
                "macro_nonregression": delta["macro_mean_iou"]
                >= float(rules["macro_mean_iou_delta_must_be_at_least"]),
                **{
                    f"{domain}_noninferiority": delta[f"{domain}_mean_iou"]
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
        limits = rules["maximum_mean_existing_domain_mean_iou_regression"]
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
                "positive_mean_robust_gain": means["robust_mean_iou"]
                > float(rules["mean_robust_delta_must_be_greater_than"]),
                "minimum_robust_wins": wins
                >= int(rules["minimum_robust_wins_out_of_3"]),
                "mean_growingsoy_gain": means["growingsoy_mean_iou"]
                >= float(rules["mean_growingsoy_delta_must_be_at_least"]),
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
                "robust_wins": wins,
            }

    eligible = [name for name in candidate_names if acceptance[name]["accepted"]]

    def rank_key(name: str) -> tuple[float, float, float]:
        selected_runs = [value for value in runs if value["candidate"] == name]
        return (
            statistics.fmean(
                value["aggregate"]["robust_mean_iou"] for value in selected_runs
            ),
            statistics.fmean(
                value["aggregate"]["growingsoy_mean_iou"] for value in selected_runs
            ),
            statistics.fmean(
                value["aggregate"]["macro_mean_iou"] for value in selected_runs
            ),
        )

    selected = max(eligible, key=rank_key) if eligible else control
    selected_runs = [value for value in runs if value["candidate"] == selected]
    representative = sorted(
        selected_runs,
        key=lambda value: (value["aggregate"]["robust_mean_iou"], value["seed"]),
    )[len(selected_runs) // 2]
    representative_seed = int(representative["seed"])
    representative_run = indexed_evaluations[(selected, representative_seed)]
    checkpoint = Path(representative_run["checkpoint"]).resolve()

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
        "evaluation_receipts": evaluation_receipt_locks,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(__file__),
        "source_tree_sha256": next(iter(source_hashes)),
        "seeds": seeds,
        "runs": runs,
        "acceptance": acceptance,
        "selected_candidate": selected,
        "representative_seed": representative_seed,
        "representative_checkpoint": str(checkpoint),
        "representative_checkpoint_sha256": sha256(checkpoint),
        "growingsoy_external_calibration_exposure": False,
        "real_rice_training_exposure": False,
        "external_test_used": False,
        "safety_policy_used_for_selection": False,
        "spray_deployment_eligible": False,
    }
    if confirmation_freeze_path is not None and confirmation_freeze is not None:
        receipt["confirmation_freeze"] = str(confirmation_freeze_path)
        receipt["confirmation_freeze_sha256"] = sha256(confirmation_freeze_path)

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
