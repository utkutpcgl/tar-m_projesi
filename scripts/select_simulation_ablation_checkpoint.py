#!/usr/bin/env python3
"""Select and lock the real/synthetic ablation winner without reading final data."""

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


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def fixed_epoch_validation(history_path: Path, epoch: int) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if int(record.get("epoch", -1)) == epoch:
                matches.append(record)
    if len(matches) != 1 or not isinstance(matches[0].get("val"), dict):
        raise ValueError(
            f"Expected one validated fixed epoch {epoch}: {history_path}"
        )
    return matches[0]["val"]


def semantic_metrics(metrics: dict[str, Any]) -> dict[str, float | bool]:
    calibration = metrics.get("calibration_source", {})
    if calibration.get("external_threshold_sweep_performed") is not False:
        raise ValueError("Development evaluation performed an external sweep")
    selected = metrics["selected_operating_point"]
    risk_distribution = selected["per_image_crop_spray_risk"]
    return {
        "mean_iou": float(metrics["mean_iou"]),
        "crop_iou": float(metrics["iou"]["target_crop"]),
        "weed_iou": float(metrics["iou"]["other_vegetation"]),
        "safety_constraint_met": bool(metrics["safety_constraint"]["met"]),
        "crop_spray_risk": float(selected["global"]["crop_spray_risk"]),
        "crop_spray_risk_p99": float(risk_distribution["p99"]),
        "crop_spray_risk_violation_rate": float(
            risk_distribution["violation_rate"]
        ),
    }


def run_record(
    runs_root: Path,
    candidate: str,
    seed: int,
    fixed_epoch: int,
    expected_development_hashes: dict[str, str],
) -> dict[str, Any]:
    run_dir = (runs_root / candidate / f"seed_{seed}").resolve()
    summary_path = run_dir / "summary.json"
    config_path = run_dir / "config.resolved.json"
    history_path = run_dir / "history.jsonl"
    checkpoint_path = run_dir / "last.pt"
    development_dir = run_dir / f"development_fixed_epoch{fixed_epoch}"
    paths = {
        "cwfid": development_dir / "cwfid.json",
        "sorghum_weed": development_dir / "sorghum_weed.json",
    }
    required = [
        summary_path,
        config_path,
        history_path,
        checkpoint_path,
        *paths.values(),
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing fixed-epoch artifacts: {missing}")

    summary = load_json(summary_path)
    config = load_json(config_path)
    source = fixed_epoch_validation(history_path, fixed_epoch)
    development = {name: load_json(path) for name, path in paths.items()}
    if summary.get("status") != "complete" or int(summary.get("epochs", -1)) != fixed_epoch:
        raise ValueError(f"Incomplete fixed-epoch run: {run_dir}")
    if config.get("experiment") != candidate or int(config.get("seed", -1)) != seed:
        raise ValueError(f"Candidate/seed mismatch: {config_path}")

    for name, metrics in development.items():
        evaluated_checkpoint = Path(
            metrics["calibration_source"]["checkpoint"]
        ).resolve()
        if evaluated_checkpoint != checkpoint_path:
            raise ValueError(
                f"{name} did not evaluate fixed-epoch last.pt: {paths[name]}"
            )
        provenance = metrics["provenance"]
        if provenance.get("source_tree_match") is not True:
            raise ValueError(f"Source provenance mismatch: {paths[name]}")
        if provenance.get("checkpoint_source_tree_sha256") != summary.get(
            "source_tree_sha256"
        ):
            raise ValueError(f"Mixed source tree: {paths[name]}")
        if provenance.get("evaluation_manifest_sha256") != expected_development_hashes[
            name
        ]:
            raise ValueError(f"Unexpected development manifest: {paths[name]}")

    source_semantic = {
        "mean_iou": float(source["mean_iou"]),
        "crop_iou": float(source["iou"]["target_crop"]),
        "weed_iou": float(source["iou"]["other_vegetation"]),
    }
    development_semantic = {
        name: semantic_metrics(metrics) for name, metrics in development.items()
    }
    primary = min(
        source_semantic["mean_iou"],
        float(development_semantic["cwfid"]["mean_iou"]),
        float(development_semantic["sorghum_weed"]["mean_iou"]),
    )
    return {
        "candidate": candidate,
        "seed": seed,
        "fixed_epoch": fixed_epoch,
        "primary_robust_semantic_mean_iou": primary,
        "source_validation": source_semantic,
        "development": development_semantic,
        "run_dir": str(run_dir),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "summary": str(summary_path),
        "summary_sha256": sha256(summary_path),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "history": str(history_path),
        "history_sha256": sha256(history_path),
        "development_artifacts": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in paths.items()
        },
        "manifest_sha256": summary["manifest_sha256"],
        "normalized_mask_tree_sha256": summary[
            "normalized_mask_tree_sha256"
        ],
        "source_tree_sha256": summary["source_tree_sha256"],
    }


def distribution(runs: list[dict[str, Any]], getter: Any) -> dict[str, float]:
    values = [float(getter(run)) for run in runs]
    return {
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def candidate_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "seeds": [run["seed"] for run in runs],
        "primary_robust_semantic_mean_iou": distribution(
            runs, lambda run: run["primary_robust_semantic_mean_iou"]
        ),
        "source_mean_iou": distribution(
            runs, lambda run: run["source_validation"]["mean_iou"]
        ),
        "cwfid_mean_iou": distribution(
            runs, lambda run: run["development"]["cwfid"]["mean_iou"]
        ),
        "cwfid_crop_iou": distribution(
            runs, lambda run: run["development"]["cwfid"]["crop_iou"]
        ),
        "cwfid_weed_iou": distribution(
            runs, lambda run: run["development"]["cwfid"]["weed_iou"]
        ),
        "sorghum_mean_iou": distribution(
            runs,
            lambda run: run["development"]["sorghum_weed"]["mean_iou"],
        ),
        "sorghum_crop_iou": distribution(
            runs,
            lambda run: run["development"]["sorghum_weed"]["crop_iou"],
        ),
        "sorghum_weed_iou": distribution(
            runs,
            lambda run: run["development"]["sorghum_weed"]["weed_iou"],
        ),
        "development_safety_pass_rate": statistics.fmean(
            float(
                run["development"][name]["safety_constraint_met"]
            )
            for run in runs
            for name in ("cwfid", "sorghum_weed")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--cwfid-manifest", required=True)
    parser.add_argument("--sorghum-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol_path = Path(args.protocol).expanduser().resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise ValueError(f"Expected protocol mapping: {protocol_path}")
    if protocol.get("external_test_used_for_selection") is not False:
        raise ValueError("Protocol does not keep external test locked")
    runs_root = Path(args.runs_root).expanduser().resolve()
    seeds = [int(seed) for seed in protocol["seeds"]]
    if len(seeds) != len(set(seeds)):
        raise ValueError("Protocol seeds must be unique")

    development_manifests = {
        "cwfid": Path(args.cwfid_manifest).expanduser().resolve(),
        "sorghum_weed": Path(args.sorghum_manifest).expanduser().resolve(),
    }
    expected_development_hashes = {
        name: sha256(path) for name, path in development_manifests.items()
    }
    candidate_entries = protocol["paired_candidates"]

    def candidate_spec(role: str) -> dict[str, Any]:
        entry = candidate_entries[role]
        if isinstance(entry, str):
            return {"name": entry, "fixed_epoch": int(protocol["fixed_epoch"])}
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid {role} candidate specification")
        return {
            "name": str(entry["name"]),
            "fixed_epoch": int(entry["fixed_epoch"]),
        }

    control_spec = candidate_spec("control")
    challenger_spec = candidate_spec("challenger")
    control_name = control_spec["name"]
    challenger_name = challenger_spec["name"]
    specs = {control_name: control_spec, challenger_name: challenger_spec}
    runs = {
        candidate: [
            run_record(
                runs_root,
                candidate,
                seed,
                int(specs[candidate]["fixed_epoch"]),
                expected_development_hashes,
            )
            for seed in seeds
        ]
        for candidate in (control_name, challenger_name)
    }
    if len({run["source_tree_sha256"] for values in runs.values() for run in values}) != 1:
        raise ValueError("Mixed source trees across paired confirmation runs")
    for candidate, values in runs.items():
        if len({run["manifest_sha256"] for run in values}) != 1:
            raise ValueError(f"Mixed manifests across seeds for {candidate}")
        if len({run["normalized_mask_tree_sha256"] for run in values}) != 1:
            raise ValueError(f"Mixed mask trees across seeds for {candidate}")

    summaries = {
        candidate: candidate_summary(values) for candidate, values in runs.items()
    }
    paired = []
    for index, seed in enumerate(seeds):
        control = runs[control_name][index]
        challenger = runs[challenger_name][index]
        paired.append(
            {
                "seed": seed,
                "control_primary": control[
                    "primary_robust_semantic_mean_iou"
                ],
                "challenger_primary": challenger[
                    "primary_robust_semantic_mean_iou"
                ],
                "primary_delta": challenger[
                    "primary_robust_semantic_mean_iou"
                ]
                - control["primary_robust_semantic_mean_iou"],
            }
        )
    acceptance = protocol["challenger_acceptance"]
    mean_delta = statistics.fmean(row["primary_delta"] for row in paired)
    wins = sum(row["primary_delta"] > 0.0 for row in paired)
    source_regression = (
        summaries[control_name]["source_mean_iou"]["mean"]
        - summaries[challenger_name]["source_mean_iou"]["mean"]
    )
    sorghum_regression = (
        summaries[control_name]["sorghum_mean_iou"]["mean"]
        - summaries[challenger_name]["sorghum_mean_iou"]["mean"]
    )
    checks = {
        "positive_mean_paired_primary_delta": mean_delta
        > float(acceptance["mean_paired_primary_delta_must_be_greater_than"]),
        "minimum_primary_seed_wins": wins
        >= int(acceptance["minimum_primary_wins_out_of_3"]),
        "source_validation_noninferiority": source_regression
        <= float(
            acceptance[
                "maximum_allowed_mean_source_validation_miou_regression"
            ]
        ),
        "sorghum_validation_noninferiority": sorghum_regression
        <= float(
            acceptance[
                "maximum_allowed_mean_sorghum_validation_miou_regression"
            ]
        ),
    }
    challenger_accepted = all(checks.values())
    selected_name = challenger_name if challenger_accepted else control_name
    ordered = sorted(
        runs[selected_name],
        key=lambda run: (
            run["primary_robust_semantic_mean_iou"],
            run["seed"],
        ),
    )
    representative = ordered[len(ordered) // 2]
    safety_pass_rate = summaries[selected_name]["development_safety_pass_rate"]

    output = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection_scope": "research semantic crop segmentation",
        "selection_status": protocol.get(
            "receipt_selection_status",
            "synthetic_ratio_selected_for_training_budget_confirmation; "
            "external_test_remains_locked",
        ),
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "development_manifests": {
            name: {"path": str(path), "sha256": expected_development_hashes[name]}
            for name, path in development_manifests.items()
        },
        "external_test_used_for_selection": False,
        "locked_external_test": protocol["locked_external_test"],
        "fixed_epoch_by_candidate": {
            name: int(spec["fixed_epoch"]) for name, spec in specs.items()
        },
        "paired_seeds": seeds,
        "candidate_summaries": summaries,
        "paired_primary_deltas": paired,
        "challenger_acceptance": {
            "challenger": challenger_name,
            "control": control_name,
            "mean_paired_primary_delta": mean_delta,
            "primary_seed_wins": wins,
            "source_mean_iou_regression": source_regression,
            "sorghum_mean_iou_regression": sorghum_regression,
            "checks": checks,
            "accepted": challenger_accepted,
        },
        "selected_candidate": selected_name,
        "selected_fixed_epoch": int(specs[selected_name]["fixed_epoch"]),
        "representative_rule": protocol["representative_checkpoint_rule"],
        "selected_seed": representative["seed"],
        "selected_checkpoint": representative["checkpoint"],
        "selected_checkpoint_sha256": representative["checkpoint_sha256"],
        "spray_deployment_status": (
            "not_eligible_semantic_only_and_development_safety_gates_not_all_met"
            if safety_pass_rate < 1.0
            else "not_eligible_semantic_protocol_requires_independent_field_validation"
        ),
        "runs": runs,
        "selector_script": str(Path(__file__).resolve()),
        "selector_script_sha256": sha256(__file__),
    }
    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
