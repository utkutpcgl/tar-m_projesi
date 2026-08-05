#!/usr/bin/env python3
"""Evaluate GrowingSoy real-data ablations at the frozen fixed epoch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint
from agri_seg.manifest import SampleRecord, read_manifest


GROWINGSOY_DATASET_ID = "growingsoy"
RICE_DATASET_ID = "rice_seedling_weed"
REQUIRED_KNOWN_CROP_IDS = {0, 2, 3, 4, 5, 6, 7, 8, 9, 12}


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


def compact(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "mean_iou": float(metrics["mean_iou"]),
        "crop_iou": float(metrics["iou"]["target_crop"]),
        "weed_iou": float(metrics["iou"]["other_vegetation"]),
    }


def fixed_epoch_validation(history_path: Path, epoch: int) -> dict[str, float]:
    matches: list[dict[str, Any]] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if int(record.get("epoch", -1)) == epoch:
                validation = record.get("val")
                if not isinstance(validation, dict):
                    raise ValueError(f"Epoch {epoch} has no validation: {history_path}")
                matches.append(validation)
    if len(matches) != 1:
        raise ValueError(f"Expected one validated epoch {epoch}: {history_path}")
    return compact(matches[0])


def existing_metrics(path: Path, checkpoint: Path) -> dict[str, Any]:
    metrics = load_object(path)
    calibration = metrics.get("calibration_source", {})
    if Path(calibration.get("checkpoint", "")).resolve() != checkpoint:
        raise ValueError(f"Existing metrics use another checkpoint: {path}")
    if calibration.get("external_threshold_sweep_performed") is not False:
        raise ValueError(f"Existing metrics swept external thresholds: {path}")
    return metrics


def selected_records(
    manifest: Path, split: str, expected_dataset_id: str
) -> list[SampleRecord]:
    if "external_test" in split or "final_test" in split:
        raise ValueError(f"Forbidden evaluation split: {split}")
    selected = [record for record in read_manifest(manifest) if record.split == split]
    if not selected:
        raise ValueError(f"No rows for split {split}: {manifest}")
    dataset_ids = {record.dataset_id for record in selected}
    if dataset_ids != {expected_dataset_id}:
        raise ValueError(
            f"Unexpected dataset IDs in {manifest}/{split}: {sorted(dataset_ids)}"
        )
    return selected


def validate_training_inputs(
    config: dict[str, Any], data_root: Path, growingsoy_calibration: list[SampleRecord]
) -> tuple[Path, float, bool]:
    if Path(config["data_root"]).resolve() != data_root:
        raise ValueError("Run data_root differs from the declared evaluation root")
    known_ids = {int(value) for value in config["model"]["known_crop_ids"]}
    if known_ids != REQUIRED_KNOWN_CROP_IDS:
        raise ValueError(f"Unexpected known_crop_ids: {sorted(known_ids)}")
    weights = {
        str(key): float(value)
        for key, value in config["training"]["dataset_weights"].items()
    }
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Dataset weights do not sum to one: {sum(weights.values())}")
    if RICE_DATASET_ID in weights:
        raise ValueError("Real Rice tiles are evaluation-only in this gate")

    training_manifest = Path(config["manifest"]).resolve()
    training = read_manifest(training_manifest)
    forbidden_roles = sorted(
        {record.split for record in training}
        - {str(config["training"]["train_split"]), str(config["training"]["val_split"])}
    )
    if forbidden_roles:
        raise ValueError(f"Training manifest contains forbidden roles: {forbidden_roles}")
    if any(record.dataset_id == RICE_DATASET_ID for record in training):
        raise ValueError("Training manifest contains evaluation-only real Rice tiles")
    growingsoy_train = [
        record for record in training if record.dataset_id == GROWINGSOY_DATASET_ID
    ]
    growingsoy_exposure = weights.get(GROWINGSOY_DATASET_ID, 0.0)
    if bool(growingsoy_train) != (growingsoy_exposure > 0.0):
        raise ValueError(
            "GrowingSoy manifest presence and dataset sampling exposure disagree"
        )
    if any(record.split != "train" for record in growingsoy_train):
        raise ValueError("GrowingSoy challenger contains a non-train source role")
    train_groups = {record.group_id for record in growingsoy_train}
    calibration_groups = {record.group_id for record in growingsoy_calibration}
    overlap = sorted(train_groups & calibration_groups)
    if overlap:
        raise ValueError(f"GrowingSoy calibration leakage into training: {overlap}")
    return training_manifest, growingsoy_exposure, bool(growingsoy_train)


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
    parser.add_argument("--rice-manifest", required=True)
    parser.add_argument("--growingsoy-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    arguments = parser.parse_args()

    candidate_dir = Path(arguments.candidate_dir).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    manifests = {
        "cwfid": (
            Path(arguments.cwfid_manifest).expanduser().resolve(),
            "external_calibration",
            "cwfid",
        ),
        "sorghum_weed": (
            Path(arguments.sorghum_manifest).expanduser().resolve(),
            "external_calibration",
            "sorghum_weed",
        ),
        "cropandweed": (
            Path(arguments.cropandweed_manifest).expanduser().resolve(),
            "external_calibration",
            "cropandweed",
        ),
        "rice": (
            Path(arguments.rice_manifest).expanduser().resolve(),
            "train",
            RICE_DATASET_ID,
        ),
        "growingsoy": (
            Path(arguments.growingsoy_manifest).expanduser().resolve(),
            "external_calibration",
            GROWINGSOY_DATASET_ID,
        ),
    }
    evaluation_records = {
        name: selected_records(manifest, split, dataset_id)
        for name, (manifest, split, dataset_id) in manifests.items()
    }
    growingsoy_calibration = evaluation_records["growingsoy"]

    seeds = sorted(set(arguments.seeds))
    if len(seeds) != len(arguments.seeds):
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

        summary = load_object(summary_path)
        if summary.get("status") != "complete":
            raise ValueError(f"Run is not complete: {run_dir}")
        if int(summary.get("epochs", -1)) != arguments.fixed_epoch:
            raise ValueError(f"Run is not at epoch {arguments.fixed_epoch}: {run_dir}")
        if summary.get("source_tree_sha256") != arguments.expected_source_tree_sha256:
            raise ValueError(f"Run source-tree hash is not frozen: {run_dir}")
        config = load_object(config_path)
        training_manifest, growingsoy_exposure, growingsoy_used = (
            validate_training_inputs(config, data_root, growingsoy_calibration)
        )
        if summary.get("manifest_sha256") != sha256(training_manifest):
            raise ValueError(f"Training manifest hash mismatch: {run_dir}")
        source_validation = fixed_epoch_validation(history_path, arguments.fixed_epoch)

        output_dir = run_dir / f"development_fixed_epoch{arguments.fixed_epoch}_growingsoy"
        artifacts: dict[str, Any] = {}
        for name, (manifest, split, _) in manifests.items():
            output = output_dir / f"{name}.json"
            legacy = (
                run_dir
                / f"development_fixed_epoch{arguments.fixed_epoch}_paddy"
                / f"{name}.json"
            )
            if output.exists():
                if not arguments.reuse_completed:
                    raise FileExistsError(output)
                metrics = existing_metrics(output, checkpoint)
                artifact_path = output
                reused = True
                reuse_source = "growingsoy_gate"
            elif name != "growingsoy" and legacy.exists():
                metrics = existing_metrics(legacy, checkpoint)
                artifact_path = legacy
                reused = True
                reuse_source = "locked_paddy_gate"
            else:
                metrics = evaluate_checkpoint(
                    checkpoint,
                    manifest,
                    data_root,
                    split,
                    output,
                    batch_size=1,
                    workers=arguments.workers,
                )
                artifact_path = output
                reused = False
                reuse_source = "new_evaluation"
            artifacts[name] = {
                "path": str(artifact_path),
                "sha256": sha256(artifact_path),
                "manifest": str(manifest),
                "manifest_sha256": sha256(manifest),
                "split": split,
                "samples": len(evaluation_records[name]),
                "reused": reused,
                "reuse_source": reuse_source,
                **compact(metrics),
            }
        records.append(
            {
                "seed": seed,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint),
                "checkpoint_name": checkpoint.name,
                "checkpoint_sha256": sha256(checkpoint),
                "training_manifest": str(training_manifest),
                "training_manifest_sha256": sha256(training_manifest),
                "growingsoy_training_exposure": growingsoy_exposure,
                "growingsoy_training_rows_present": growingsoy_used,
                "growingsoy_external_calibration_exposure": False,
                "real_rice_training_exposure": False,
                "source_validation": source_validation,
                "summary_sha256": sha256(summary_path),
                "history_sha256": sha256(history_path),
                "config_sha256": sha256(config_path),
                "source_tree_sha256": summary["source_tree_sha256"],
                "artifacts": artifacts,
            }
        )

    seed_label = "-".join(str(seed) for seed in seeds)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "growingsoy_real_data_gate_development_only",
        "external_test_used": False,
        "real_rice_training_exposure": False,
        "growingsoy_external_calibration_exposure": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": arguments.fixed_epoch,
        "checkpoint": "last.pt",
        "expected_source_tree_sha256": arguments.expected_source_tree_sha256,
        "seeds": seeds,
        "runs": records,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path = candidate_dir / (
        f"growingsoy_development_fixed_epoch{arguments.fixed_epoch}_"
        f"seeds_{seed_label}.json"
    )
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
