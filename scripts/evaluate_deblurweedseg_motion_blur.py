#!/usr/bin/env python3
"""Run the frozen paired DeBlurWeedSeg motion-blur diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.engine import evaluate_checkpoint, source_tree_sha256
from agri_seg.manifest import SampleRecord, mask_tree_sha256, read_manifest


METRIC_KEYS = ("mean_iou", "crop_iou", "weed_iou")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def resolve_path(project_root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def compact(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "mean_iou": float(metrics["mean_iou"]),
        "crop_iou": float(metrics["iou"]["target_crop"]),
        "weed_iou": float(metrics["iou"]["other_vegetation"]),
    }


def validate_manifest(
    path: Path, modality: str, expected_samples: int
) -> list[SampleRecord]:
    records = read_manifest(path)
    if len(records) != expected_samples:
        raise ValueError(f"Expected {expected_samples} rows in {path}, got {len(records)}")
    if {record.split for record in records} != {"external_calibration"}:
        raise ValueError(f"Forbidden role in {path}")
    if {record.dataset_id for record in records} != {"deblurweedseg"}:
        raise ValueError(f"Unexpected dataset in {path}")
    if {record.sample_id.split(":")[-1] for record in records} != {modality}:
        raise ValueError(f"Unexpected modality in {path}")
    if len({record.group_id for record in records}) != 1:
        raise ValueError(f"DeBlurWeedSeg must remain declared as one capture group: {path}")
    return records


def pair_ids(records: list[SampleRecord]) -> set[str]:
    result: set[str] = set()
    for record in records:
        parts = record.sample_id.split(":")
        if len(parts) != 3 or parts[1] != Path(record.image_path).stem:
            raise ValueError(f"Unexpected sample identity: {record.sample_id}")
        result.add(parts[1])
    if len(result) != len(records):
        raise ValueError("Duplicate pair identity")
    return result


def validate_existing_metrics(
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
        raise ValueError(f"Existing metrics failed code provenance: {path}")
    return metrics


def ensure_no_training_exposure(
    config: dict[str, Any], data_root: Path, evaluation: list[SampleRecord]
) -> tuple[Path, list[SampleRecord]]:
    if Path(str(config["data_root"])).resolve() != data_root:
        raise ValueError("Training and evaluation data roots differ")
    training_manifest = Path(str(config["manifest"])).resolve()
    training = read_manifest(training_manifest)
    if any(record.dataset_id == "deblurweedseg" for record in training):
        raise ValueError("DeBlurWeedSeg leaked into accepted-control training")
    training_images = {record.image_path for record in training}
    training_masks = {record.mask_path for record in training}
    if training_images & {record.image_path for record in evaluation}:
        raise ValueError("Evaluation image leaked into accepted-control training")
    if training_masks & {record.mask_path for record in evaluation}:
        raise ValueError("Evaluation mask leaked into accepted-control training")
    return training_manifest, training


def mean_metrics(values: list[dict[str, float]]) -> dict[str, float]:
    return {
        key: statistics.fmean(value[key] for value in values) for key in METRIC_KEYS
    }


def image_tree_sha256(records: list[SampleRecord], data_root: Path) -> str:
    """Hash the exact derived RGB files and their recorded relative paths."""
    digest = hashlib.sha256()
    for recorded_path in sorted({record.image_path for record in records}):
        path = Path(recorded_path)
        resolved = path if path.is_absolute() else data_root / path
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        digest.update(recorded_path.encode("utf-8"))
        digest.update(b"\0")
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    arguments = parser.parse_args()

    protocol_path = Path(arguments.protocol).expanduser().resolve()
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise ValueError("Protocol must be a mapping")
    if protocol.get("frozen_before_evaluation") is not True:
        raise ValueError("Protocol was not frozen before evaluation")
    if protocol.get("external_test_used") is not False:
        raise ValueError("External-test data is forbidden in this diagnostic")
    project_root = protocol_path.parents[2]
    data_root = resolve_path(project_root, str(protocol["data_root"]))

    for name, lock in protocol["locked_inputs"].items():
        locked_path = resolve_path(project_root, str(lock["path"]))
        if not locked_path.is_file():
            raise FileNotFoundError(locked_path)
        actual = sha256(locked_path)
        if actual != str(lock["sha256"]):
            raise ValueError(
                f"Locked input changed ({name}): expected {lock['sha256']}, got {actual}"
            )

    expected_source_tree = str(protocol["accepted_control"]["source_tree_sha256"])
    if source_tree_sha256() != expected_source_tree:
        raise ValueError("Runtime agri_seg source tree differs from accepted control")
    expected_samples = int(protocol["dataset"]["samples_per_modality"])
    manifest_specs = protocol["dataset"]["manifests"]
    manifests = {
        modality: resolve_path(project_root, str(spec["path"]))
        for modality, spec in manifest_specs.items()
    }
    if set(manifests) != {"sharp", "motion_blur"}:
        raise ValueError("Exactly sharp and motion_blur manifests are required")
    for modality, manifest in manifests.items():
        if sha256(manifest) != str(manifest_specs[modality]["sha256"]):
            raise ValueError(f"Manifest changed: {manifest}")
    evaluation_records = {
        modality: validate_manifest(manifest, modality, expected_samples)
        for modality, manifest in manifests.items()
    }
    if pair_ids(evaluation_records["sharp"]) != pair_ids(
        evaluation_records["motion_blur"]
    ):
        raise ValueError("Sharp and motion-blur manifests contain different pairs")
    all_evaluation = evaluation_records["sharp"] + evaluation_records["motion_blur"]
    if mask_tree_sha256(all_evaluation, data_root) != str(
        protocol["dataset"]["normalized_mask_tree_sha256"]
    ):
        raise ValueError("Normalized evaluation masks changed after conversion")
    if image_tree_sha256(all_evaluation, data_root) != str(
        protocol["dataset"]["derived_image_tree_sha256"]
    ):
        raise ValueError("Derived evaluation images changed after conversion")

    control = protocol["accepted_control"]
    run_root = resolve_path(project_root, str(control["run_root"]))
    output_root = resolve_path(project_root, str(protocol["outputs"]["run_root"]))
    seeds = [int(value) for value in control["seeds"]]
    if len(seeds) != len(set(seeds)) or len(seeds) < 3:
        raise ValueError("At least three unique confirmation seeds are required")
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        seed_spec = control["seed_locks"][str(seed)]
        run_dir = run_root / f"seed_{seed}"
        checkpoint = (run_dir / str(control["checkpoint"])).resolve()
        summary_path = run_dir / "summary.json"
        config_path = run_dir / "config.resolved.json"
        history_path = run_dir / "history.jsonl"
        for path in (checkpoint, summary_path, config_path, history_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        for name, path in (
            ("checkpoint", checkpoint),
            ("summary", summary_path),
            ("config", config_path),
            ("history", history_path),
        ):
            expected = str(seed_spec[f"{name}_sha256"])
            if sha256(path) != expected:
                raise ValueError(f"Seed {seed} {name} changed")

        summary = load_object(summary_path)
        if summary.get("status") != "complete":
            raise ValueError(f"Accepted control seed {seed} is incomplete")
        if int(summary.get("epochs", -1)) != int(control["fixed_epoch"]):
            raise ValueError(f"Seed {seed} is not at the frozen fixed epoch")
        if summary.get("source_tree_sha256") != expected_source_tree:
            raise ValueError(f"Seed {seed} source-tree provenance changed")
        config = load_object(config_path)
        training_manifest, training_records = ensure_no_training_exposure(
            config, data_root, all_evaluation
        )
        if summary.get("manifest_sha256") != sha256(training_manifest):
            raise ValueError(f"Seed {seed} training manifest changed")

        artifacts: dict[str, Any] = {}
        for modality, manifest in manifests.items():
            output = output_root / f"seed_{seed}" / f"{modality}.json"
            if output.exists():
                if not arguments.reuse_completed:
                    raise FileExistsError(output)
                metrics = validate_existing_metrics(
                    output,
                    checkpoint,
                    manifest,
                    expected_samples,
                    expected_source_tree,
                )
                reused = True
            else:
                metrics = evaluate_checkpoint(
                    checkpoint,
                    manifest,
                    data_root,
                    "external_calibration",
                    output,
                    batch_size=int(protocol["evaluation"]["batch_size"]),
                    workers=arguments.workers,
                )
                validate_existing_metrics(
                    output,
                    checkpoint,
                    manifest,
                    expected_samples,
                    expected_source_tree,
                )
                reused = False
            artifacts[modality] = {
                "path": str(output),
                "sha256": sha256(output),
                "manifest": str(manifest),
                "manifest_sha256": sha256(manifest),
                "evaluation_mask_tree_sha256": metrics["provenance"][
                    "evaluation_mask_tree_sha256"
                ],
                "samples": expected_samples,
                "reused": reused,
                **compact(metrics),
            }
        delta = {
            key: artifacts["motion_blur"][key] - artifacts["sharp"][key]
            for key in METRIC_KEYS
        }
        runs.append(
            {
                "seed": seed,
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": sha256(checkpoint),
                "training_manifest": str(training_manifest),
                "training_manifest_sha256": sha256(training_manifest),
                "training_samples": len(training_records),
                "deblurweedseg_training_exposure": False,
                "artifacts": artifacts,
                "motion_blur_minus_sharp": delta,
            }
        )

    sharp_mean = mean_metrics([run["artifacts"]["sharp"] for run in runs])
    blur_mean = mean_metrics([run["artifacts"]["motion_blur"] for run in runs])
    delta_mean = mean_metrics([run["motion_blur_minus_sharp"] for run in runs])
    rules = protocol["diagnostic_gate"]
    seed_threshold = float(rules["minimum_per_seed_mean_iou_delta"])
    seed_noninferior = sum(
        run["motion_blur_minus_sharp"]["mean_iou"] >= seed_threshold
        for run in runs
    )
    checks = {
        "mean_iou_noninferiority": delta_mean["mean_iou"]
        >= float(rules["minimum_mean_iou_delta"]),
        "crop_iou_noninferiority": delta_mean["crop_iou"]
        >= float(rules["minimum_crop_iou_delta"]),
        "weed_iou_noninferiority": delta_mean["weed_iou"]
        >= float(rules["minimum_weed_iou_delta"]),
        "seed_consistency": seed_noninferior
        >= int(rules["minimum_passing_seeds"]),
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "single_field_paired_motion_blur_development_diagnostic",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "external_test_used": False,
        "publisher_train_or_val_used": False,
        "publisher_model_used": False,
        "model_selection_or_promotion_allowed": False,
        "accepted_control_changed": False,
        "seeds": seeds,
        "runs": runs,
        "aggregate": {
            "sharp_mean": sharp_mean,
            "motion_blur_mean": blur_mean,
            "motion_blur_minus_sharp_mean": delta_mean,
            "worst_seed_motion_blur_mean_iou": min(
                run["artifacts"]["motion_blur"]["mean_iou"] for run in runs
            ),
            "passing_seeds": seed_noninferior,
            "total_seeds": len(runs),
        },
        "diagnostic_gate": {
            "rules": rules,
            "checks": checks,
            "passed": all(checks.values()),
        },
        "causal_limit": protocol["causal_limit"],
        "field_limit": protocol["field_limit"],
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
        "runtime_source_tree_sha256": source_tree_sha256(),
    }
    receipt_path = resolve_path(project_root, str(protocol["outputs"]["receipt"]))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
