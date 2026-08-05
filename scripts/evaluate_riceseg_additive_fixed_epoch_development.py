#!/usr/bin/env python3
"""Evaluate the replay-preserving RiceSEG additive screen on real development data."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint, source_tree_sha256

from scripts import evaluate_paddy_fixed_epoch_development as base


RICESEG_DATASET_ID = "riceseg"
FORBIDDEN_TRAIN_DATASETS = {
    "rice_seedling_weed",
    "growingsoy",
    "weedmap",
    "tobacco_aerial",
    "deblurweedseg",
}


def selected_ids(path: Path, split: str) -> tuple[set[str], set[str]]:
    rows = [row for row in base.manifest_rows(path) if row.get("split") == split]
    return (
        {str(row.get("sample_id")) for row in rows},
        {str(row.get("image_path")) for row in rows},
    )


def validate_training_inputs(
    config: dict[str, Any], data_root: Path, riceseg_calibration: Path
) -> dict[str, Any]:
    if Path(str(config["data_root"])).resolve() != data_root:
        raise ValueError("Run data_root differs from the declared evaluation root")
    known_ids = {int(value) for value in config["model"]["known_crop_ids"]}
    if known_ids != base.REQUIRED_KNOWN_CROP_IDS:
        raise ValueError(f"Unexpected known_crop_ids: {sorted(known_ids)}")

    weights = {
        str(name): float(value)
        for name, value in config["training"]["dataset_weights"].items()
    }
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Dataset weights do not sum to one: {sum(weights.values())}")
    forbidden_weights = set(weights) & FORBIDDEN_TRAIN_DATASETS
    if forbidden_weights:
        raise ValueError(f"Forbidden development dataset weights: {sorted(forbidden_weights)}")

    training_manifest = Path(str(config["manifest"])).resolve()
    rows = base.manifest_rows(training_manifest)
    forbidden_splits = sorted(
        {str(row.get("split")) for row in rows} - {"train", "val"}
    )
    if forbidden_splits:
        raise ValueError(f"Forbidden training-manifest roles: {forbidden_splits}")
    forbidden_datasets = {
        str(row.get("dataset_id")) for row in rows
    } & FORBIDDEN_TRAIN_DATASETS
    if forbidden_datasets:
        raise ValueError(
            f"Training manifest contains development-only datasets: {sorted(forbidden_datasets)}"
        )

    riceseg_rows = [row for row in rows if row.get("dataset_id") == RICESEG_DATASET_ID]
    if any(row.get("split") != "train" for row in riceseg_rows):
        raise ValueError("Only quality-gated RiceSEG train rows may enter training")
    riceseg_weight = float(weights.get(RICESEG_DATASET_ID, 0.0))
    if bool(riceseg_rows) != (riceseg_weight > 0.0):
        raise ValueError("RiceSEG manifest rows and sampling exposure disagree")

    calibration_ids, calibration_images = selected_ids(
        riceseg_calibration, "external_calibration"
    )
    training_ids = {str(row.get("sample_id")) for row in rows}
    training_images = {str(row.get("image_path")) for row in rows}
    if training_ids & calibration_ids or training_images & calibration_images:
        raise ValueError("RiceSEG external calibration leaked into training")

    return {
        "manifest": training_manifest,
        "samples_per_epoch": int(config["training"]["samples_per_epoch"]),
        "riceseg_exposure": riceseg_weight,
        "riceseg_rows": len(riceseg_rows),
        "riceseg_groups": len({str(row.get("session_id")) for row in riceseg_rows}),
    }


def reusable_metrics(
    paths: list[tuple[Path, str]],
    checkpoint: Path,
    manifest: Path,
    expected_source_tree: str,
    reuse_completed: bool,
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    for path, source in paths:
        if not path.is_file():
            continue
        if not reuse_completed:
            raise FileExistsError(path)
        metrics = base.existing_metrics(path, checkpoint)
        provenance = metrics.get("provenance", {})
        if provenance.get("evaluation_manifest_sha256") != base.sha256(manifest):
            raise ValueError(f"Reusable metrics use another manifest: {path}")
        if provenance.get("checkpoint_source_tree_sha256") != expected_source_tree:
            raise ValueError(f"Reusable metrics use another source tree: {path}")
        return metrics, path, source
    return None, None, None


def prior_paths(run_dir: Path, epoch: int, domain: str) -> list[tuple[Path, str]]:
    current = run_dir / f"development_fixed_epoch{epoch}_riceseg_additive" / f"{domain}.json"
    paths: list[tuple[Path, str]] = [(current, "same_protocol")]
    reproductive = run_dir / f"development_fixed_epoch{epoch}_reproductive"
    tobacco = run_dir / f"development_fixed_epoch{epoch}_tobacco"
    paddy = run_dir / f"development_fixed_epoch{epoch}_paddy"
    if domain in {
        "cwfid",
        "sorghum_weed",
        "cropandweed",
        "early_rice",
        "riceseg",
        "riceseg_reproductive",
    }:
        paths.append((reproductive / f"{domain}.json", "compatible_reproductive_protocol"))
    tobacco_name = "rice" if domain == "early_rice" else domain
    if domain in {
        "cwfid",
        "sorghum_weed",
        "cropandweed",
        "early_rice",
        "growingsoy",
        "weedmap",
        "tobacco",
        "deblur_sharp",
        "deblur_motion_blur",
    }:
        paths.append((tobacco / f"{tobacco_name}.json", "compatible_tobacco_protocol"))
    if domain in {"cwfid", "sorghum_weed", "cropandweed", "early_rice"}:
        paths.append((paddy / f"{tobacco_name}.json", "compatible_paddy_protocol"))
    return paths


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
    parser.add_argument("--growingsoy-manifest", required=True)
    parser.add_argument("--weedmap-manifest", required=True)
    parser.add_argument("--tobacco-manifest", required=True)
    parser.add_argument("--riceseg-manifest", required=True)
    parser.add_argument("--riceseg-reproductive-manifest", required=True)
    parser.add_argument("--deblur-sharp-manifest", required=True)
    parser.add_argument("--deblur-motion-blur-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    manifests = {
        "cwfid": (Path(args.cwfid_manifest).resolve(), "external_calibration", "cwfid"),
        "sorghum_weed": (
            Path(args.sorghum_manifest).resolve(),
            "external_calibration",
            "sorghum_weed",
        ),
        "cropandweed": (
            Path(args.cropandweed_manifest).resolve(),
            "external_calibration",
            "cropandweed",
        ),
        "early_rice": (Path(args.early_rice_manifest).resolve(), "train", "rice_seedling_weed"),
        "growingsoy": (
            Path(args.growingsoy_manifest).resolve(),
            "external_calibration",
            "growingsoy",
        ),
        "weedmap": (Path(args.weedmap_manifest).resolve(), "external_calibration", "weedmap"),
        "tobacco": (
            Path(args.tobacco_manifest).resolve(),
            "external_calibration",
            "tobacco_aerial",
        ),
        "riceseg": (
            Path(args.riceseg_manifest).resolve(),
            "external_calibration",
            RICESEG_DATASET_ID,
        ),
        "riceseg_reproductive": (
            Path(args.riceseg_reproductive_manifest).resolve(),
            "external_calibration",
            RICESEG_DATASET_ID,
        ),
        "deblur_sharp": (
            Path(args.deblur_sharp_manifest).resolve(),
            "external_calibration",
            "deblurweedseg",
        ),
        "deblur_motion_blur": (
            Path(args.deblur_motion_blur_manifest).resolve(),
            "external_calibration",
            "deblurweedseg",
        ),
    }
    for manifest, split, dataset_id in manifests.values():
        base.validate_evaluation_manifest(manifest, split, dataset_id)

    expected_source_tree = str(args.expected_source_tree_sha256)
    if source_tree_sha256() != expected_source_tree:
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
        if summary.get("status") != "complete" or int(summary.get("epochs", -1)) != args.fixed_epoch:
            raise ValueError(f"Run is not complete at epoch {args.fixed_epoch}: {run_dir}")
        if summary.get("source_tree_sha256") != expected_source_tree:
            raise ValueError(f"Run source tree differs: {run_dir}")
        config = base.load_object(config_path)
        training = validate_training_inputs(config, data_root, riceseg_calibration)
        training_manifest = Path(training["manifest"])
        if summary.get("manifest_sha256") != base.sha256(training_manifest):
            raise ValueError(f"Training manifest hash mismatch: {run_dir}")

        artifacts: dict[str, Any] = {}
        for name, (manifest, split, _) in manifests.items():
            paths = prior_paths(run_dir, args.fixed_epoch, name)
            metrics, artifact_path, reuse_source = reusable_metrics(
                paths,
                checkpoint,
                manifest,
                expected_source_tree,
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
                "growingsoy_training_exposure": False,
                "weedmap_training_exposure": False,
                "tobacco_training_exposure": False,
                "deblurweedseg_training_exposure": False,
                "source_validation": base.fixed_epoch_validation(history_path, args.fixed_epoch),
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
        "role": "riceseg_replay_preserving_real_data_development_gate",
        "external_test_used": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": args.fixed_epoch,
        "checkpoint": "last.pt",
        "expected_source_tree_sha256": expected_source_tree,
        "seeds": seeds,
        "runs": records,
        "script": str(Path(__file__).resolve()),
        "script_sha256": base.sha256(Path(__file__).resolve()),
    }
    receipt_path = candidate_dir / (
        f"riceseg_additive_development_fixed_epoch{args.fixed_epoch}_seeds_{seed_label}.json"
    )
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
