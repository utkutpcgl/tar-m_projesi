#!/usr/bin/env python3
"""Evaluate WeedMap real-data screens at one frozen fixed epoch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint, source_tree_sha256
from agri_seg.manifest import SampleRecord, read_manifest


WEEDMAP_DATASET_ID = "weedmap"
FORBIDDEN_TRAIN_DATASETS = {
    "cwfid",
    "cropandweed",
    "rice_seedling_weed",
    "growingsoy",
    "deblurweedseg",
}
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


def selected_records(
    manifest: Path,
    split: str,
    expected_dataset_id: str,
    expected_modality: str | None = None,
) -> list[SampleRecord]:
    if "external_test" in split or "final_test" in split:
        raise ValueError(f"Forbidden evaluation split: {split}")
    selected = [record for record in read_manifest(manifest) if record.split == split]
    if not selected:
        raise ValueError(f"No rows for split {split}: {manifest}")
    if {record.dataset_id for record in selected} != {expected_dataset_id}:
        raise ValueError(f"Unexpected dataset in {manifest}/{split}")
    if expected_modality is not None:
        modalities = {record.sample_id.split(":")[-1] for record in selected}
        if modalities != {expected_modality}:
            raise ValueError(f"Unexpected modality in {manifest}: {modalities}")
    return selected


def validate_training_inputs(
    config: dict[str, Any],
    data_root: Path,
    weedmap_calibration: list[SampleRecord],
) -> tuple[Path, float, int, int]:
    if Path(str(config["data_root"])).resolve() != data_root:
        raise ValueError("Run data_root differs from evaluation data_root")
    known_ids = {int(value) for value in config["model"]["known_crop_ids"]}
    if known_ids != REQUIRED_KNOWN_CROP_IDS:
        raise ValueError(f"Unexpected known_crop_ids: {sorted(known_ids)}")
    weights = {
        str(key): float(value)
        for key, value in config["training"]["dataset_weights"].items()
    }
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Dataset weights do not sum to one: {sum(weights.values())}")
    forbidden_weights = sorted(FORBIDDEN_TRAIN_DATASETS & set(weights))
    if forbidden_weights:
        raise ValueError(f"Evaluation-only datasets have training weight: {forbidden_weights}")

    training_manifest = Path(str(config["manifest"])).resolve()
    training = read_manifest(training_manifest)
    expected_roles = {
        str(config["training"]["train_split"]),
        str(config["training"]["val_split"]),
    }
    unexpected_roles = sorted({record.split for record in training} - expected_roles)
    if unexpected_roles:
        raise ValueError(f"Training manifest has forbidden roles: {unexpected_roles}")
    leaked_datasets = sorted(
        {record.dataset_id for record in training} & FORBIDDEN_TRAIN_DATASETS
    )
    if leaked_datasets:
        raise ValueError(f"Evaluation-only datasets leaked into training: {leaked_datasets}")
    weedmap_train = [
        record for record in training if record.dataset_id == WEEDMAP_DATASET_ID
    ]
    if any(record.split != "train" for record in weedmap_train):
        raise ValueError("Only WeedMap publisher-train maps may enter training")
    exposure = weights.get(WEEDMAP_DATASET_ID, 0.0)
    if bool(weedmap_train) != (exposure > 0.0):
        raise ValueError("WeedMap manifest presence and sampling exposure disagree")
    overlap = {record.group_id for record in weedmap_train} & {
        record.group_id for record in weedmap_calibration
    }
    if overlap:
        raise ValueError(f"WeedMap calibration group leaked into training: {overlap}")
    train_paths = {
        value
        for record in weedmap_train
        for value in (record.image_path, record.mask_path)
    }
    calibration_paths = {
        value
        for record in weedmap_calibration
        for value in (record.image_path, record.mask_path)
    }
    if train_paths & calibration_paths:
        raise ValueError("WeedMap calibration files leaked into training")
    return (
        training_manifest,
        exposure,
        len(weedmap_train),
        len({record.group_id for record in weedmap_train}),
    )


def existing_metrics(
    path: Path,
    checkpoint: Path,
    manifest: Path,
    expected_samples: int,
    expected_source_tree: str,
) -> dict[str, Any]:
    metrics = load_object(path)
    calibration = metrics.get("calibration_source", {})
    if Path(str(calibration.get("checkpoint", ""))).resolve() != checkpoint:
        raise ValueError(f"Existing metrics use another checkpoint: {path}")
    if calibration.get("external_threshold_sweep_performed") is not False:
        raise ValueError(f"Existing metrics swept external thresholds: {path}")
    if int(metrics.get("runtime", {}).get("images", -1)) != expected_samples:
        raise ValueError(f"Existing metrics contain another sample count: {path}")
    provenance = metrics.get("provenance", {})
    if provenance.get("evaluation_manifest_sha256") != sha256(manifest):
        raise ValueError(f"Existing metrics contain another manifest: {path}")
    if provenance.get("checkpoint_source_tree_sha256") != expected_source_tree:
        raise ValueError(f"Existing metrics contain another source tree: {path}")
    if provenance.get("source_tree_match") is not True:
        raise ValueError(f"Existing metrics failed source provenance: {path}")
    return metrics


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
    parser.add_argument("--weedmap-manifest", required=True)
    parser.add_argument("--deblur-sharp-manifest", required=True)
    parser.add_argument("--deblur-motion-blur-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    arguments = parser.parse_args()

    candidate_dir = Path(arguments.candidate_dir).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    manifests = {
        "cwfid": (
            Path(arguments.cwfid_manifest).resolve(),
            "external_calibration",
            "cwfid",
            None,
        ),
        "sorghum_weed": (
            Path(arguments.sorghum_manifest).resolve(),
            "external_calibration",
            "sorghum_weed",
            None,
        ),
        "cropandweed": (
            Path(arguments.cropandweed_manifest).resolve(),
            "external_calibration",
            "cropandweed",
            None,
        ),
        "rice": (
            Path(arguments.rice_manifest).resolve(),
            "train",
            "rice_seedling_weed",
            None,
        ),
        "growingsoy": (
            Path(arguments.growingsoy_manifest).resolve(),
            "external_calibration",
            "growingsoy",
            None,
        ),
        "weedmap": (
            Path(arguments.weedmap_manifest).resolve(),
            "external_calibration",
            WEEDMAP_DATASET_ID,
            None,
        ),
        "deblur_sharp": (
            Path(arguments.deblur_sharp_manifest).resolve(),
            "external_calibration",
            "deblurweedseg",
            "sharp",
        ),
        "deblur_motion_blur": (
            Path(arguments.deblur_motion_blur_manifest).resolve(),
            "external_calibration",
            "deblurweedseg",
            "motion_blur",
        ),
    }
    evaluation_records = {
        name: selected_records(manifest, split, dataset_id, modality)
        for name, (manifest, split, dataset_id, modality) in manifests.items()
    }
    weedmap_calibration = evaluation_records["weedmap"]
    expected_source_tree = str(arguments.expected_source_tree_sha256)
    if source_tree_sha256() != expected_source_tree:
        raise ValueError("Runtime source tree differs from the frozen protocol")

    seeds = sorted(set(arguments.seeds))
    if len(seeds) != len(arguments.seeds):
        raise ValueError("Seeds must be unique")
    runs: list[dict[str, Any]] = []
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
            raise ValueError(f"Run is incomplete: {run_dir}")
        if int(summary.get("epochs", -1)) != arguments.fixed_epoch:
            raise ValueError(f"Run is not at epoch {arguments.fixed_epoch}: {run_dir}")
        if summary.get("source_tree_sha256") != expected_source_tree:
            raise ValueError(f"Run source tree differs: {run_dir}")
        config = load_object(config_path)
        (
            training_manifest,
            weedmap_exposure,
            weedmap_rows,
            weedmap_groups,
        ) = validate_training_inputs(config, data_root, weedmap_calibration)
        if summary.get("manifest_sha256") != sha256(training_manifest):
            raise ValueError(f"Training manifest hash mismatch: {run_dir}")
        source_validation = fixed_epoch_validation(history_path, arguments.fixed_epoch)

        output_dir = run_dir / f"development_fixed_epoch{arguments.fixed_epoch}_weedmap"
        artifacts: dict[str, Any] = {}
        for name, (manifest, split, _, _) in manifests.items():
            output = output_dir / f"{name}.json"
            if output.exists():
                if not arguments.reuse_completed:
                    raise FileExistsError(output)
                metrics = existing_metrics(
                    output,
                    checkpoint,
                    manifest,
                    len(evaluation_records[name]),
                    expected_source_tree,
                )
                reused = True
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
                existing_metrics(
                    output,
                    checkpoint,
                    manifest,
                    len(evaluation_records[name]),
                    expected_source_tree,
                )
                reused = False
            artifacts[name] = {
                "path": str(output),
                "sha256": sha256(output),
                "manifest": str(manifest),
                "manifest_sha256": sha256(manifest),
                "split": split,
                "samples": len(evaluation_records[name]),
                "reused": reused,
                **compact(metrics),
            }
        runs.append(
            {
                "seed": seed,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint),
                "checkpoint_name": checkpoint.name,
                "checkpoint_sha256": sha256(checkpoint),
                "training_manifest": str(training_manifest),
                "training_manifest_sha256": sha256(training_manifest),
                "weedmap_training_exposure": weedmap_exposure,
                "weedmap_training_rows": weedmap_rows,
                "weedmap_training_groups": weedmap_groups,
                "weedmap_external_calibration_exposure": False,
                "deblurweedseg_training_exposure": False,
                "real_rice_training_exposure": False,
                "growingsoy_training_exposure": False,
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
        "role": "weedmap_real_data_gate_development_only",
        "external_test_used": False,
        "publisher_model_used": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": arguments.fixed_epoch,
        "checkpoint": "last.pt",
        "expected_source_tree_sha256": expected_source_tree,
        "seeds": seeds,
        "runs": runs,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path = candidate_dir / (
        f"weedmap_development_fixed_epoch{arguments.fixed_epoch}_"
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
