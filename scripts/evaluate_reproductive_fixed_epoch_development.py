#!/usr/bin/env python3
"""Evaluate the reproductive-rice A/B on frozen real development domains."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint

from scripts import evaluate_paddy_fixed_epoch_development as base


FORBIDDEN_REAL_RICE_DATASETS = {"rice_seedling_weed", "riceseg"}


def validate_training_inputs(config: dict[str, Any], data_root: Path) -> Path:
    training_manifest = base.validate_training_inputs(config, data_root)
    rows = base.manifest_rows(training_manifest)
    dataset_ids = {str(row.get("dataset_id")) for row in rows}
    forbidden = dataset_ids & FORBIDDEN_REAL_RICE_DATASETS
    if forbidden:
        raise ValueError(f"Training manifest contains real Rice datasets: {sorted(forbidden)}")
    weights = {
        str(name): float(weight)
        for name, weight in config["training"]["dataset_weights"].items()
    }
    forbidden_weights = set(weights) & FORBIDDEN_REAL_RICE_DATASETS
    if forbidden_weights:
        raise ValueError(f"Training weights contain real Rice datasets: {sorted(forbidden_weights)}")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Dataset weights do not sum to one: {sum(weights.values())}")
    return training_manifest


def reusable_metrics(
    output: Path,
    legacy: Path | None,
    checkpoint: Path,
    manifest: Path,
    reuse_completed: bool,
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    candidates = [(output, "same_protocol")]
    if legacy is not None:
        candidates.append((legacy, "compatible_paddy_protocol"))
    for path, source in candidates:
        if not path.is_file():
            continue
        if not reuse_completed:
            raise FileExistsError(path)
        metrics = base.existing_metrics(path, checkpoint)
        provenance = metrics.get("provenance", {})
        if provenance.get("evaluation_manifest_sha256") != base.sha256(manifest):
            raise ValueError(f"Reusable metrics use another manifest: {path}")
        return metrics, path, source
    return None, None, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_dir")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--fixed-epoch", type=int, required=True)
    parser.add_argument("--expected-source-tree-sha256", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--cwfid-manifest", required=True)
    parser.add_argument("--sorghum-manifest", required=True)
    parser.add_argument("--cropandweed-manifest", required=True)
    parser.add_argument("--early-rice-manifest", required=True)
    parser.add_argument("--riceseg-manifest", required=True)
    parser.add_argument("--riceseg-reproductive-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    manifests = {
        "cwfid": (
            Path(args.cwfid_manifest).expanduser().resolve(),
            "external_calibration",
            "cwfid",
            "cwfid.json",
        ),
        "sorghum_weed": (
            Path(args.sorghum_manifest).expanduser().resolve(),
            "external_calibration",
            "sorghum_weed",
            "sorghum_weed.json",
        ),
        "cropandweed": (
            Path(args.cropandweed_manifest).expanduser().resolve(),
            "external_calibration",
            "cropandweed",
            "cropandweed.json",
        ),
        "early_rice": (
            Path(args.early_rice_manifest).expanduser().resolve(),
            "train",
            "rice_seedling_weed",
            "rice.json",
        ),
        "riceseg": (
            Path(args.riceseg_manifest).expanduser().resolve(),
            "external_calibration",
            "riceseg",
            None,
        ),
        "riceseg_reproductive": (
            Path(args.riceseg_reproductive_manifest).expanduser().resolve(),
            "external_calibration",
            "riceseg",
            None,
        ),
    }
    for manifest, split, dataset_id, _ in manifests.values():
        base.validate_evaluation_manifest(manifest, split, dataset_id)

    seeds = sorted(set(args.seeds))
    if len(seeds) != len(args.seeds):
        raise ValueError("Seeds must be unique")
    records: list[dict[str, Any]] = []
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
        if summary.get("status") != "complete":
            raise ValueError(f"Run is not complete: {run_dir}")
        if int(summary.get("epochs", -1)) != args.fixed_epoch:
            raise ValueError(f"Run is not at fixed epoch {args.fixed_epoch}: {run_dir}")
        if summary.get("source_tree_sha256") != args.expected_source_tree_sha256:
            raise ValueError(f"Run source-tree hash is not frozen: {run_dir}")
        config = base.load_object(config_path)
        training_manifest = validate_training_inputs(config, data_root)
        if summary.get("manifest_sha256") != base.sha256(training_manifest):
            raise ValueError(f"Training manifest hash mismatch: {run_dir}")
        source_validation = base.fixed_epoch_validation(history_path, args.fixed_epoch)

        output_dir = run_dir / f"development_fixed_epoch{args.fixed_epoch}_reproductive"
        artifacts: dict[str, Any] = {}
        for name, (manifest, split, _, legacy_filename) in manifests.items():
            output = output_dir / f"{name}.json"
            legacy = (
                run_dir
                / f"development_fixed_epoch{args.fixed_epoch}_paddy"
                / str(legacy_filename)
                if legacy_filename is not None
                else None
            )
            metrics, metrics_path, reuse_source = reusable_metrics(
                output, legacy, checkpoint, manifest, args.reuse_completed
            )
            if metrics is None:
                metrics = evaluate_checkpoint(
                    checkpoint,
                    manifest,
                    data_root,
                    split,
                    output,
                    batch_size=1,
                    workers=args.workers,
                )
                metrics_path = output
                reuse_source = None
            assert metrics_path is not None
            artifacts[name] = {
                "path": str(metrics_path),
                "sha256": base.sha256(metrics_path),
                "manifest": str(manifest),
                "manifest_sha256": base.sha256(manifest),
                "split": split,
                "reused": reuse_source is not None,
                "reuse_source": reuse_source,
                **base.compact(metrics),
            }
        records.append(
            {
                "seed": seed,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint),
                "checkpoint_name": checkpoint.name,
                "checkpoint_sha256": base.sha256(checkpoint),
                "training_manifest": str(training_manifest),
                "training_manifest_sha256": base.sha256(training_manifest),
                "real_rice_training_exposure": False,
                "source_validation": source_validation,
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
        "role": "reproductive_synthetic_asset_gate_real_development_only",
        "external_test_used": False,
        "real_rice_training_exposure": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": args.fixed_epoch,
        "checkpoint": "last.pt",
        "expected_source_tree_sha256": args.expected_source_tree_sha256,
        "seeds": seeds,
        "runs": records,
        "script": str(Path(__file__).resolve()),
        "script_sha256": base.sha256(Path(__file__).resolve()),
    }
    receipt_path = candidate_dir / (
        f"reproductive_development_fixed_epoch{args.fixed_epoch}_seeds_{seed_label}.json"
    )
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
