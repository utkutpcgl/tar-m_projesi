#!/usr/bin/env python3
"""Apply the frozen soybean synthetic-asset screen/confirmation protocol."""

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

from agri_seg.manifest import read_manifest


DEVELOPMENT_DOMAINS = {
    "cwfid",
    "sorghum_weed",
    "cropandweed",
    "rice",
    "growingsoy",
}
REQUIRED_KNOWN_CROP_IDS = {0, 2, 3, 4, 5, 6, 7, 8, 9, 12}


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


def locked_json(protocol: dict[str, Any], name: str) -> dict[str, Any]:
    return load_json(Path(protocol["locked_inputs"][name]["path"]).resolve())


def validate_data_evidence(protocol: dict[str, Any]) -> None:
    static = locked_json(protocol, "asset_static_audit")
    if static.get("custom", {}).get("all_quality_gates_passed") is not True:
        raise ValueError("Soy asset static-quality gate did not pass")

    release = locked_json(protocol, "pilot_release_receipt")
    if release.get("all_quality_gates_passed") is not True:
        raise ValueError("Soy pilot automatic gate did not pass")
    if int(release.get("frames", -1)) != 100 or int(
        release.get("scene_count", -1)
    ) != 25:
        raise ValueError("Unexpected soy pilot size")

    visual = locked_json(protocol, "pilot_visual_receipt")
    if visual.get("passed") is not True:
        raise ValueError("Soy pilot manual visual gate did not pass")
    release_path = Path(
        protocol["locked_inputs"]["pilot_release_receipt"]["path"]
    ).resolve()
    if visual.get("release_receipt_sha256") != sha256(release_path):
        raise ValueError("Visual review does not lock the pilot receipt")

    manifest_audit = locked_json(protocol, "soy_manifest_audit")
    if int(manifest_audit.get("samples", -1)) != 100:
        raise ValueError("Unexpected soy manifest sample count")
    for field in ("missing_files", "invalid_masks", "shape_mismatches"):
        if int(manifest_audit.get(field, -1)) != 0:
            raise ValueError(f"Soy manifest failed: {field}")

    duplicates = locked_json(protocol, "soy_real_duplicate_audit")
    if duplicates.get("passed") is not True:
        raise ValueError("Soy duplicate/leakage gate did not pass")
    for field in (
        "candidate_to_reference_match_count",
        "within_candidate_cross_split_match_count",
    ):
        if int(duplicates.get(field, -1)) != 0:
            raise ValueError(f"Soy duplicate audit failed: {field}")

    combined = locked_json(protocol, "challenger_manifest_audit")
    if int(combined.get("samples", -1)) != int(
        protocol["challenger_manifest_samples"]
    ):
        raise ValueError("Unexpected combined challenger manifest size")
    for field in ("missing_files", "invalid_masks", "shape_mismatches"):
        if int(combined.get(field, -1)) != 0:
            raise ValueError(f"Combined challenger manifest failed: {field}")

    existing_gap = locked_json(protocol, "existing_real_domain_gap")
    if any(existing_gap["synthetic_median_outside_real_pooled_q05_q95"].values()):
        raise ValueError("Soy pilot has a gross pooled existing-real domain gap")
    growingsoy_gap = locked_json(protocol, "growingsoy_domain_gap")
    if growingsoy_gap.get("real_splits") != ["external_calibration"]:
        raise ValueError("GrowingSoy gap audit used an unexpected role")


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


def validate_recipe(
    protocol: dict[str, Any], candidate: str, run_dir: Path
) -> dict[str, Any]:
    config_path = run_dir / "config.resolved.json"
    config = load_json(config_path)
    expected_weights = {
        str(name): float(value)
        for name, value in protocol["candidate_dataset_weights"][candidate].items()
    }
    observed_weights = {
        str(name): float(value)
        for name, value in config["training"]["dataset_weights"].items()
    }
    if set(expected_weights) != set(observed_weights):
        raise ValueError(f"Dataset-weight keys changed: {candidate}")
    for name, expected in expected_weights.items():
        if not math.isclose(observed_weights[name], expected, abs_tol=1e-12):
            raise ValueError(f"Dataset weight changed: {candidate}/{name}")
    if not math.isclose(sum(observed_weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError(f"Dataset weights do not sum to one: {candidate}")

    synthetic_ids = {str(value) for value in protocol["synthetic_dataset_ids"]}
    synthetic_exposure = sum(observed_weights.get(name, 0.0) for name in synthetic_ids)
    if not math.isclose(
        synthetic_exposure,
        float(protocol["compute_budget"]["synthetic_exposure"]),
        abs_tol=1e-12,
    ):
        raise ValueError(f"Synthetic exposure changed: {candidate}")
    real_exposure = 1.0 - synthetic_exposure
    if not math.isclose(
        real_exposure,
        float(protocol["compute_budget"]["real_exposure"]),
        abs_tol=1e-12,
    ):
        raise ValueError(f"Real exposure changed: {candidate}")

    if int(config["training"]["epochs"]) != int(protocol["fixed_epoch"]):
        raise ValueError(f"Epoch budget changed: {candidate}")
    if int(config["training"]["samples_per_epoch"]) != int(
        protocol["compute_budget"]["samples_per_epoch"]
    ):
        raise ValueError(f"Sample budget changed: {candidate}")
    if {int(value) for value in config["model"]["known_crop_ids"]} != (
        REQUIRED_KNOWN_CROP_IDS
    ):
        raise ValueError(f"Known crop IDs changed: {candidate}")

    manifest_lock = protocol["candidate_training_manifests"][candidate]
    manifest = Path(config["manifest"]).resolve()
    if manifest != Path(manifest_lock["path"]).resolve():
        raise ValueError(f"Training manifest path changed: {candidate}")
    if sha256(manifest) != manifest_lock["sha256"]:
        raise ValueError(f"Training manifest hash changed: {candidate}")
    records = read_manifest(manifest)
    forbidden_roles = sorted(
        {record.split for record in records}
        - {
            str(config["training"]["train_split"]),
            str(config["training"]["val_split"]),
        }
    )
    if forbidden_roles:
        raise ValueError(f"Forbidden training roles: {candidate}/{forbidden_roles}")
    dataset_ids = {record.dataset_id for record in records}
    if "growingsoy" in dataset_ids or "rice_seedling_weed" in dataset_ids:
        raise ValueError(f"Real evaluation data leaked into training: {candidate}")
    if not set(observed_weights) <= dataset_ids:
        raise ValueError(f"Weighted dataset absent from manifest: {candidate}")
    soy_id = str(protocol["soy_synthetic_dataset_id"])
    soy_weight = observed_weights.get(soy_id, 0.0)
    if (soy_id in dataset_ids) != (soy_weight > 0.0):
        raise ValueError(f"Soy manifest/weight exposure mismatch: {candidate}")
    return {
        "config": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "manifest": str(manifest),
        "manifest_sha256": sha256(manifest),
        "dataset_weights": observed_weights,
        "synthetic_exposure": synthetic_exposure,
        "soy_synthetic_exposure": soy_weight,
        "real_growingsoy_training_rows": False,
        "real_rice_training_rows": False,
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
    expected = {
        "parent_protocol": protocol_path,
        "screen_selection_receipt": screen_path,
        "confirmation_matrix": matrix_path,
    }
    for name, path in expected.items():
        lock = freeze["locked_inputs"][name]
        if Path(lock["path"]).resolve() != path or lock["sha256"] != sha256(path):
            raise ValueError(f"Confirmation freeze mismatch: {name}")
    if str(freeze.get("control")) != control:
        raise ValueError("Confirmation control mismatch")
    if str(freeze.get("selected_screen_winner")) != winner:
        raise ValueError("Confirmation winner mismatch")
    if [int(value) for value in freeze.get("seeds", [])] != seeds:
        raise ValueError("Confirmation seed mismatch")
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
            raise ValueError("Confirmation requires screen receipt and freeze")
        screen_path = Path(args.screen_receipt).resolve()
        screen = load_json(screen_path)
        if screen.get("stage") != "screen":
            raise ValueError("The supplied receipt is not a screen receipt")
        if screen.get("frozen_protocol_sha256") != sha256(protocol_path):
            raise ValueError("Screen receipt used another frozen protocol")
        winner = str(screen["selected_candidate"])
        if winner == control or winner not in protocol["screen_candidates"]:
            raise ValueError("There is no accepted challenger to confirm")
        seeds = [int(value) for value in protocol["confirmation_seeds"]]
        candidate_names = [winner]
        confirmation_freeze_path = Path(args.confirmation_freeze).resolve()
        validate_confirmation_freeze(
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
    recipe_checks: dict[str, dict[str, Any]] = {}
    source_hashes: set[str] = set()
    evaluator_hash = protocol["locked_inputs"]["evaluator_script"]["sha256"]
    for name in sorted(expected_names):
        first_run_dir = Path(indexed_benchmark[(name, seeds[0])]["run_dir"])
        receipt_path = first_run_dir.parent / (
            f"growingsoy_development_fixed_epoch{protocol['fixed_epoch']}_"
            f"seeds_{seed_label}.json"
        )
        receipt = load_json(receipt_path)
        if receipt.get("script_sha256") != evaluator_hash:
            raise ValueError(f"Evaluation script mismatch: {receipt_path}")
        for field in (
            "external_test_used",
            "real_rice_training_exposure",
            "growingsoy_external_calibration_exposure",
        ):
            if receipt.get(field) is not False:
                raise ValueError(f"Forbidden exposure in {receipt_path}: {field}")
        if receipt.get("checkpoint") != protocol["checkpoint"]:
            raise ValueError(f"Wrong checkpoint policy: {receipt_path}")
        evaluation_receipt_locks[name] = {
            "path": str(receipt_path),
            "sha256": sha256(receipt_path),
        }
        for run in receipt["runs"]:
            seed = int(run["seed"])
            if seed not in seeds:
                continue
            key = (name, seed)
            run_dir = Path(run["run_dir"]).resolve()
            if run_dir != Path(indexed_benchmark[key]["run_dir"]).resolve():
                raise ValueError(f"Run directory mismatch: {key}")
            if run.get("checkpoint_name") != protocol["checkpoint"]:
                raise ValueError(f"Wrong checkpoint: {key}")
            if run.get("real_rice_training_exposure") is not False:
                raise ValueError(f"Real Rice training exposure: {key}")
            if not math.isclose(
                float(run.get("growingsoy_training_exposure", -1.0)),
                0.0,
                abs_tol=1e-12,
            ) or run.get("growingsoy_training_rows_present") is not False:
                raise ValueError(f"Real GrowingSoy training exposure: {key}")
            recipe = validate_recipe(protocol, name, run_dir)
            if run.get("training_manifest_sha256") != recipe["manifest_sha256"]:
                raise ValueError(f"Evaluator manifest mismatch: {key}")
            recipe_checks[f"{name}/seed_{seed}"] = recipe
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
                "robust_nonregression": delta["robust_mean_iou"]
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
                value["aggregate"]["growingsoy_mean_iou"]
                for value in selected_runs
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
        "confirmation_freeze": (
            None
            if confirmation_freeze_path is None
            else {
                "path": str(confirmation_freeze_path),
                "sha256": sha256(confirmation_freeze_path),
            }
        ),
        "evaluation_receipts": evaluation_receipt_locks,
        "recipe_checks": recipe_checks,
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
        "real_growingsoy_training_exposure": False,
        "real_rice_training_exposure": False,
        "external_test_used": False,
        "safety_policy_used_for_selection": False,
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
