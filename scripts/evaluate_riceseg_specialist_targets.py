#!/usr/bin/env python3
"""Evaluate a separately routed rice specialist on frozen real rice targets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint, source_tree_sha256

from scripts import evaluate_paddy_fixed_epoch_development as base
from scripts import evaluate_riceseg_additive_fixed_epoch_development as additive


def compatible_paths(
    run_dir: Path, fixed_epoch: int, domain: str
) -> list[tuple[Path, str]]:
    current = (
        run_dir
        / f"development_fixed_epoch{fixed_epoch}_riceseg_specialist_targets"
        / f"{domain}.json"
    )
    return [(current, "same_protocol"), *additive.prior_paths(run_dir, fixed_epoch, domain)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_dir")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--fixed-epoch", type=int, required=True)
    parser.add_argument("--expected-source-tree-sha256", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--early-rice-manifest", required=True)
    parser.add_argument("--riceseg-manifest", required=True)
    parser.add_argument("--riceseg-reproductive-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    manifests = {
        "early_rice": (
            Path(args.early_rice_manifest).resolve(),
            "train",
            "rice_seedling_weed",
        ),
        "riceseg": (
            Path(args.riceseg_manifest).resolve(),
            "external_calibration",
            additive.RICESEG_DATASET_ID,
        ),
        "riceseg_reproductive": (
            Path(args.riceseg_reproductive_manifest).resolve(),
            "external_calibration",
            additive.RICESEG_DATASET_ID,
        ),
    }
    for manifest, split, dataset_id in manifests.values():
        base.validate_evaluation_manifest(manifest, split, dataset_id)

    expected_source = str(args.expected_source_tree_sha256)
    if source_tree_sha256() != expected_source:
        raise ValueError("Runtime source tree differs from the frozen protocol")
    seeds = sorted(set(args.seeds))
    if len(seeds) != len(args.seeds):
        raise ValueError("Seeds must be unique")

    records: list[dict[str, Any]] = []
    riceseg_calibration = manifests["riceseg"][0]
    for seed in seeds:
        run_dir = candidate_dir / f"seed_{seed}"
        checkpoint = (run_dir / "last.pt").resolve()
        summary_path = run_dir / "summary.json"
        history_path = run_dir / "history.jsonl"
        config_path = run_dir / "config.resolved.json"
        for required in (checkpoint, summary_path, history_path, config_path):
            if not required.is_file():
                raise FileNotFoundError(required)

        summary = base.load_object(summary_path)
        if (
            summary.get("status") != "complete"
            or int(summary.get("epochs", -1)) != args.fixed_epoch
        ):
            raise ValueError(
                f"Run is not complete at epoch {args.fixed_epoch}: {run_dir}"
            )
        if summary.get("source_tree_sha256") != expected_source:
            raise ValueError(f"Run source tree differs: {run_dir}")
        config = base.load_object(config_path)
        training = additive.validate_training_inputs(
            config, data_root, riceseg_calibration
        )
        training_manifest = Path(training["manifest"])
        if summary.get("manifest_sha256") != base.sha256(training_manifest):
            raise ValueError(f"Training manifest hash mismatch: {run_dir}")

        artifacts: dict[str, Any] = {}
        for name, (manifest, split, _) in manifests.items():
            paths = compatible_paths(run_dir, args.fixed_epoch, name)
            metrics, artifact_path, reuse_source = additive.reusable_metrics(
                paths,
                checkpoint,
                manifest,
                expected_source,
                args.reuse_completed,
            )
            if metrics is None:
                artifact_path = paths[0][0]
                metrics = evaluate_checkpoint(
                    checkpoint,
                    manifest,
                    data_root,
                    split,
                    artifact_path,
                    batch_size=1,
                    workers=args.workers,
                )
                reuse_source = "fresh"
            assert artifact_path is not None
            artifacts[name] = {
                "path": str(artifact_path),
                "sha256": base.sha256(artifact_path),
                "manifest": str(manifest),
                "manifest_sha256": base.sha256(manifest),
                "split": split,
                "reuse_source": reuse_source,
                **base.compact(metrics),
            }

        records.append(
            {
                "seed": seed,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": base.sha256(checkpoint),
                "training_manifest": str(training_manifest),
                "training_manifest_sha256": base.sha256(training_manifest),
                "samples_per_epoch": training["samples_per_epoch"],
                "riceseg_training_exposure": training["riceseg_exposure"],
                "riceseg_training_rows": training["riceseg_rows"],
                "riceseg_training_groups": training["riceseg_groups"],
                "riceseg_calibration_exposure": False,
                "early_rice_training_exposure": False,
                "external_test_used": False,
                "source_validation": base.fixed_epoch_validation(
                    history_path, args.fixed_epoch
                ),
                "summary_sha256": base.sha256(summary_path),
                "history_sha256": base.sha256(history_path),
                "config_sha256": base.sha256(config_path),
                "source_tree_sha256": summary["source_tree_sha256"],
                "artifacts": artifacts,
            }
        )

    seed_label = "-".join(str(seed) for seed in seeds)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "riceseg_crop_routed_specialist_target_development_gate",
        "routing_contract": {
            "specialist_target_crop_id": 12,
            "specialist_target_crop_species": "Oryza sativa",
            "unknown_or_other_crop": "accepted_global_fallback",
            "pixel_inferred_routing_allowed": False,
        },
        "external_test_used": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": args.fixed_epoch,
        "checkpoint": "last.pt",
        "expected_source_tree_sha256": expected_source,
        "seeds": seeds,
        "runs": records,
        "script": str(Path(__file__).resolve()),
        "script_sha256": base.sha256(Path(__file__).resolve()),
    }
    receipt_path = candidate_dir / (
        f"riceseg_specialist_targets_fixed_epoch{args.fixed_epoch}_seeds_{seed_label}.json"
    )
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"receipt": str(receipt_path), "runs": len(records)}, indent=2))


if __name__ == "__main__":
    main()
