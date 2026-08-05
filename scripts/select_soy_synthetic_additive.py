#!/usr/bin/env python3
"""Apply the frozen replay-preserving soybean synthetic additive gate."""

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
EXISTING_DOMAINS = {"source", "cwfid", "sorghum_weed", "cropandweed", "rice"}
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
    visual = locked_json(protocol, "pilot_visual_receipt")
    if visual.get("passed") is not True:
        raise ValueError("Soy pilot manual gate did not pass")
    release_path = Path(
        protocol["locked_inputs"]["pilot_release_receipt"]["path"]
    ).resolve()
    if visual.get("release_receipt_sha256") != sha256(release_path):
        raise ValueError("Visual receipt does not lock the pilot release")
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
        raise ValueError("Unexpected additive manifest size")
    for field in ("missing_files", "invalid_masks", "shape_mismatches"):
        if int(combined.get(field, -1)) != 0:
            raise ValueError(f"Additive manifest failed: {field}")
    previous = locked_json(protocol, "replacement_screen_receipt")
    if previous.get("stage") != "screen":
        raise ValueError("The replacement-screen evidence has an invalid role")
    if previous.get("selected_candidate") != protocol["original_control"]:
        raise ValueError("Replacement screen did not retain the original control")
    if any(value.get("accepted") for value in previous["acceptance"].values()):
        raise ValueError("Additive follow-up is unjustified: replacement passed")


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

    samples = int(config["training"]["samples_per_epoch"])
    if samples != int(protocol["candidate_samples_per_epoch"][candidate]):
        raise ValueError(f"Sample budget changed: {candidate}")
    expected_draws = {
        str(name): float(value)
        for name, value in protocol["expected_draws_per_epoch"][candidate].items()
    }
    observed_draws = {name: weight * samples for name, weight in observed_weights.items()}
    if set(expected_draws) != set(observed_draws):
        raise ValueError(f"Expected-draw keys changed: {candidate}")
    for name, expected in expected_draws.items():
        if not math.isclose(observed_draws[name], expected, abs_tol=1e-9):
            raise ValueError(f"Absolute draw budget changed: {candidate}/{name}")
    if int(config["training"]["epochs"]) != int(protocol["fixed_epoch"]):
        raise ValueError(f"Epoch budget changed: {candidate}")
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
    allowed_roles = {
        str(config["training"]["train_split"]),
        str(config["training"]["val_split"]),
    }
    forbidden_roles = sorted({record.split for record in records} - allowed_roles)
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
    synthetic_ids = {str(value) for value in protocol["synthetic_dataset_ids"]}
    synthetic_exposure = sum(observed_weights.get(name, 0.0) for name in synthetic_ids)
    return {
        "config": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "manifest": str(manifest),
        "manifest_sha256": sha256(manifest),
        "dataset_weights": observed_weights,
        "samples_per_epoch": samples,
        "expected_draws_per_epoch": observed_draws,
        "synthetic_exposure": synthetic_exposure,
        "soy_synthetic_exposure": soy_weight,
        "soy_synthetic_draws_per_epoch": soy_weight * samples,
        "real_growingsoy_training_rows": False,
        "real_rice_training_rows": False,
    }


def validate_confirmation_freeze(
    freeze_path: Path,
    protocol_path: Path,
    screen_path: Path,
    matrix_path: Path,
    protocol: dict[str, Any],
) -> None:
    freeze = load_yaml(freeze_path)
    if freeze.get("frozen_before_seed_29_or_43_training") is not True:
        raise ValueError("Confirmation was not frozen before new-seed training")
    validate_locked_inputs(freeze)
    for name, path in {
        "parent_protocol": protocol_path,
        "screen_selection_receipt": screen_path,
        "confirmation_matrix": matrix_path,
    }.items():
        lock = freeze["locked_inputs"][name]
        if Path(lock["path"]).resolve() != path or lock["sha256"] != sha256(path):
            raise ValueError(f"Confirmation freeze mismatch: {name}")
    for key in ("original_control", "matched_compute_control", "additive_candidate"):
        if str(freeze.get(key)) != str(protocol[key]):
            raise ValueError(f"Confirmation candidate mismatch: {key}")
    if [int(value) for value in freeze.get("seeds", [])] != [
        int(value) for value in protocol["confirmation_seeds"]
    ]:
        raise ValueError("Confirmation seed mismatch")


def mean_deltas(
    runs: list[dict[str, Any]], candidate: str, reference: str
) -> tuple[dict[str, float], int]:
    candidate_runs = {value["seed"]: value for value in runs if value["candidate"] == candidate}
    reference_runs = {value["seed"]: value for value in runs if value["candidate"] == reference}
    if set(candidate_runs) != set(reference_runs):
        raise ValueError(f"Unpaired runs: {candidate}/{reference}")
    deltas = []
    for seed in sorted(candidate_runs):
        current = candidate_runs[seed]["aggregate"]
        control = reference_runs[seed]["aggregate"]
        deltas.append({key: current[key] - control[key] for key in current})
    means = {
        key: statistics.fmean(delta[key] for delta in deltas)
        for key in deltas[0]
    }
    wins = sum(delta["robust_mean_iou"] > 0.0 for delta in deltas)
    return means, wins


def acceptance_checks(
    delta: dict[str, float], rules: dict[str, Any]
) -> dict[str, bool]:
    limit = float(rules["maximum_each_existing_domain_regression"])
    return {
        "robust_nonregression": delta["robust_mean_iou"]
        >= float(rules["robust_delta_must_be_at_least"]),
        "growingsoy_gain": delta["growingsoy_mean_iou"]
        >= float(rules["growingsoy_delta_must_be_at_least"]),
        "macro_nonregression": delta["macro_mean_iou"]
        >= float(rules["macro_delta_must_be_at_least"]),
        **{
            f"{domain}_noninferiority": delta[f"{domain}_mean_iou"] >= -limit
            for domain in sorted(EXISTING_DOMAINS)
        },
    }


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
    if protocol.get("frozen_before_additive_training") is not True:
        raise ValueError("Protocol was not frozen before additive training")
    validate_locked_inputs(protocol)
    validate_data_evidence(protocol)

    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_json(benchmark_path)
    matrix_path = Path(benchmark["matrix"]).resolve()
    original = str(protocol["original_control"])
    compute = str(protocol["matched_compute_control"])
    additive = str(protocol["additive_candidate"])
    screen_path: Path | None = None
    freeze_path: Path | None = None
    if args.stage == "screen":
        lock = protocol["locked_inputs"]["screen_matrix"]
        if matrix_path != Path(lock["path"]).resolve() or sha256(matrix_path) != lock["sha256"]:
            raise ValueError("Benchmark does not use the frozen screen matrix")
        seeds = [int(protocol["screen_seed"])]
    else:
        if not args.screen_receipt or not args.confirmation_freeze:
            raise ValueError("Confirmation requires screen receipt and freeze")
        screen_path = Path(args.screen_receipt).resolve()
        screen = load_json(screen_path)
        if screen.get("stage") != "screen" or screen.get("selected_candidate") != additive:
            raise ValueError("There is no accepted additive candidate to confirm")
        if screen.get("frozen_protocol_sha256") != sha256(protocol_path):
            raise ValueError("Screen receipt used another protocol")
        freeze_path = Path(args.confirmation_freeze).resolve()
        validate_confirmation_freeze(
            freeze_path, protocol_path, screen_path, matrix_path, protocol
        )
        seeds = [int(value) for value in protocol["confirmation_seeds"]]

    names = {original, compute, additive}
    indexed_benchmark: dict[tuple[str, int], dict[str, Any]] = {}
    for run in benchmark["runs"]:
        key = (str(run["candidate"]), int(run["seed"]))
        if key[0] in names and key[1] in seeds:
            if key in indexed_benchmark:
                raise ValueError(f"Duplicate benchmark run: {key}")
            indexed_benchmark[key] = run
    missing = [
        (name, seed)
        for name in sorted(names)
        for seed in seeds
        if (name, seed) not in indexed_benchmark
    ]
    if missing:
        raise ValueError(f"Missing paired benchmark runs: {missing}")

    seed_label = "-".join(str(seed) for seed in sorted(seeds))
    evaluations: dict[tuple[str, int], dict[str, Any]] = {}
    evaluation_locks: dict[str, dict[str, str]] = {}
    recipes: dict[str, dict[str, Any]] = {}
    source_hashes: set[str] = set()
    evaluator_hash = protocol["locked_inputs"]["evaluator_script"]["sha256"]
    for name in sorted(names):
        first_dir = Path(indexed_benchmark[(name, seeds[0])]["run_dir"])
        receipt_path = first_dir.parent / (
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
                raise ValueError(f"Forbidden exposure: {receipt_path}/{field}")
        if receipt.get("checkpoint") != protocol["checkpoint"]:
            raise ValueError(f"Wrong checkpoint policy: {receipt_path}")
        evaluation_locks[name] = {
            "path": str(receipt_path.resolve()),
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
            if not math.isclose(float(run.get("growingsoy_training_exposure", -1.0)), 0.0, abs_tol=1e-12):
                raise ValueError(f"Real GrowingSoy training exposure: {key}")
            if run.get("growingsoy_training_rows_present") is not False:
                raise ValueError(f"GrowingSoy rows present: {key}")
            recipe = validate_recipe(protocol, name, run_dir)
            if run.get("training_manifest_sha256") != recipe["manifest_sha256"]:
                raise ValueError(f"Evaluator manifest mismatch: {key}")
            recipes[f"{name}/seed_{seed}"] = recipe
            source_hashes.add(str(run["source_tree_sha256"]))
            if not math.isclose(
                float(indexed_benchmark[key]["source_validation"]["mean_iou"]),
                float(run["source_validation"]["mean_iou"]),
                abs_tol=1e-12,
            ):
                raise ValueError(f"Source metric mismatch: {key}")
            evaluations[key] = run
    if source_hashes != {str(protocol["source_tree_sha256"])}:
        raise ValueError(f"Source-tree hashes are not frozen: {source_hashes}")

    runs: list[dict[str, Any]] = []
    for seed in seeds:
        for name in (original, compute, additive):
            values = points(evaluations[(name, seed)])
            runs.append(
                {
                    "candidate": name,
                    "seed": seed,
                    "domains": values,
                    "aggregate": aggregate(values),
                }
            )

    delta_original, wins_original = mean_deltas(runs, additive, original)
    delta_compute, wins_compute = mean_deltas(runs, additive, compute)
    if args.stage == "screen":
        original_checks = acceptance_checks(
            delta_original, protocol["screen_acceptance_against_original"]
        )
        compute_checks = acceptance_checks(
            delta_compute, protocol["screen_acceptance_against_matched_compute"]
        )
    else:
        original_checks = acceptance_checks(
            delta_original, protocol["confirmation_acceptance_against_original"]
        )
        compute_checks = acceptance_checks(
            delta_compute, protocol["confirmation_acceptance_against_matched_compute"]
        )
        minimum_wins = int(protocol["confirmation_minimum_robust_wins_out_of_3"])
        original_checks["minimum_robust_wins"] = wins_original >= minimum_wins
        compute_checks["minimum_robust_wins"] = wins_compute >= minimum_wins
    accepted = all(original_checks.values()) and all(compute_checks.values())
    selected = additive if accepted else original
    selected_runs = [value for value in runs if value["candidate"] == selected]
    representative = sorted(
        selected_runs,
        key=lambda value: (value["aggregate"]["robust_mean_iou"], value["seed"]),
    )[len(selected_runs) // 2]
    representative_seed = int(representative["seed"])
    checkpoint = Path(evaluations[(selected, representative_seed)]["checkpoint"]).resolve()

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
        "confirmation_freeze": None if freeze_path is None else {
            "path": str(freeze_path), "sha256": sha256(freeze_path)
        },
        "evaluation_receipts": evaluation_locks,
        "recipe_checks": recipes,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(__file__),
        "source_tree_sha256": next(iter(source_hashes)),
        "seeds": seeds,
        "runs": runs,
        "acceptance": {
            "accepted": accepted,
            "against_original": {
                "checks": original_checks,
                "mean_paired_deltas": delta_original,
                "robust_wins": wins_original,
            },
            "against_matched_compute": {
                "checks": compute_checks,
                "mean_paired_deltas": delta_compute,
                "robust_wins": wins_compute,
            },
        },
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
