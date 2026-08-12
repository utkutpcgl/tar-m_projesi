#!/usr/bin/env python3
"""Prepare and optionally train the provenance-bound target-rig segmenter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_spot_spray_target_rig_action_v1 import (
    CaptureAudit,
    CaptureManifest,
    ContractError,
    Frame,
    load_capture_audit,
    load_manifest,
)


DEFAULT_CONFIG = PROJECT_ROOT / "configs/benchmark/spot_spray_target_rig_finetune_v1.yaml"
ACTION_CONFIG = PROJECT_ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"

EXIT_READY = 0
EXIT_NOT_READY = 2
EXIT_FIXTURE_ONLY = 4
EXIT_CONTRACT_ERROR = 5
SELECTED_FOUNDATION_SHA256 = (
    "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
)


class NotReadyError(RuntimeError):
    """An expected external prerequisite has not been satisfied."""


@dataclass(frozen=True)
class PreparedFrame:
    frame_id: str
    split: str
    source_image: Path
    source_image_sha256: str
    image_name: str
    label_text: str
    label_sha256: str
    class_counts: Mapping[str, int]


@dataclass(frozen=True)
class Preparation:
    output_directory: Path
    dataset_yaml: Path
    dataset_index: Path
    dataset_receipt: Path
    real_training_ready: bool
    fixture_only: bool
    payload: Mapping[str, Any]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ContractError(f"Cannot load YAML {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ContractError(f"YAML root must be an object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def capture_manager_accepted(config: Mapping[str, Any]) -> bool:
    acceptance = config["capture_interface"]["manager_acceptance"]
    accepted = acceptance["status"] == acceptance["accepted_status"]
    if accepted:
        acceptance_id = acceptance.get("acceptance_id")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            raise ContractError(
                "Accepted capture interface requires a non-empty manager acceptance_id"
            )
    return accepted


def validate_config(config_path: Path) -> tuple[dict[str, Any], Path]:
    config_path = config_path.expanduser().resolve()
    config = load_yaml(config_path)
    if config.get("schema_version") != 1:
        raise ContractError("Fine-tune config schema_version must equal 1")
    if config.get("contract") != "spot_spray_target_rig_segmentation_finetune_v1":
        raise ContractError("Fine-tune config contract mismatch")
    foundation = config["foundation"]
    if foundation.get("checkpoint_sha256") != SELECTED_FOUNDATION_SHA256:
        raise ContractError("Selected ROSE-native foundation SHA-256 drift")
    if foundation.get("task") != "segment":
        raise ContractError("Foundation task must remain segment")
    checkpoint = resolve(PROJECT_ROOT, foundation["checkpoint"])
    if not checkpoint.is_file() or sha256(checkpoint) != SELECTED_FOUNDATION_SHA256:
        raise ContractError("Selected foundation checkpoint is missing or hash-drifted")

    expected_sources = {
        "schema": "configs/data/spot_spray_capture_manifest_v1.schema.json",
        "policy": "configs/data/spot_spray_capture_audit_v1.yaml",
        "audit_implementation": "scripts/audit_spot_spray_capture_v1.py",
    }
    sources = config["capture_interface"]["sources"]
    if set(sources) != set(expected_sources):
        raise ContractError("Capture source set drift")
    for name, relative in expected_sources.items():
        source = sources[name]
        if source.get("path") != relative:
            raise ContractError(f"Capture {name} path drift")
        path = (PROJECT_ROOT / relative).resolve()
        if not path.is_file() or source.get("sha256") != sha256(path):
            raise ContractError(f"Capture {name} SHA-256 drift")

    interface = config["capture_interface"]
    expected_interface = {
        "manifest_contract": "capture_manifest_v1",
        "audit_contract": "spot_spray_capture_audit_v1",
        "real_evidence_scope": "real_target_rig",
        "ready_status": "READY",
    }
    for key, expected in expected_interface.items():
        if interface.get(key) != expected:
            raise ContractError(f"Capture interface drift: {key}")
    for key in (
        "require_valid",
        "require_ready",
        "require_no_errors_or_readiness_reasons",
        "require_complete_real_capture_metadata",
        "require_all_real_image_sha256_verified",
        "require_all_real_image_content_verified",
        "require_physical_rig_acceptance_pass",
    ):
        if interface.get(key) is not True:
            raise ContractError(f"Capture proof requirement cannot be disabled: {key}")
    acceptance = interface["manager_acceptance"]
    if acceptance.get("required_for_real_training") is not True:
        raise ContractError("Capture manager acceptance cannot be disabled")
    if acceptance.get("accepted_status") != "accepted":
        raise ContractError("Capture manager accepted status drift")
    if acceptance.get("status") not in {"pending_manager_acceptance", "accepted"}:
        raise ContractError("Unknown capture manager acceptance status")
    capture_manager_accepted(config)

    dataset = config["dataset"]
    if dataset.get("class_names") != {0: "crop", 1: "weed"}:
        raise ContractError("Fine-tune classes must remain crop=0 and weed=1")
    if dataset.get("train_split") != "train" or dataset.get("validation_split") != "validation":
        raise ContractError("Training split roles drift")
    if set(dataset.get("forbidden_training_splits", [])) != {"test", "unassigned"}:
        raise ContractError("Test and unassigned must remain forbidden")
    if dataset.get("image_link_mode") != "symlink":
        raise ContractError("Dataset materialization must remain symlink-based")
    partial = dataset["partial_unknown"]
    if (
        partial.get("policy") != "quarantine_entire_frame"
        or partial.get("materialize_image") is not False
        or partial.get("materialize_label") is not False
    ):
        raise ContractError("partial_unknown quarantine policy drift")
    if dataset.get("test_images_materialized") is not False:
        raise ContractError("Test images must never be materialized")
    if dataset.get("test_labels_materialized") is not False:
        raise ContractError("Test labels must never be materialized")

    training = config["training"]
    frozen_training = {
        "epochs": 30,
        "patience": 0,
        "image_size": 1024,
        "batch": 3,
        "seed": 41,
        "deterministic": True,
        "optimizer": "AdamW",
        "mosaic": 0.0,
        "mixup": 0.0,
        "copy_paste": 0.0,
        "val": True,
        "plots": False,
        "pretrained": True,
    }
    for key, expected in frozen_training.items():
        if training.get(key) != expected:
            raise ContractError(f"Frozen training protocol drift: {key}")
    selection = config["selection"]
    if (
        selection.get("final_checkpoint") != "last.pt"
        or selection.get("rule") != "fixed_epoch_30_last_checkpoint_only"
        or selection.get("best_checkpoint_used_for_final") is not False
        or "forbidden" not in str(selection.get("test_role", ""))
    ):
        raise ContractError("Fixed final checkpoint or test-isolation policy drift")
    if config["model_family"].get("package_version") != "8.4.60":
        raise ContractError("Ultralytics version must remain frozen at 8.4.60")
    expected_outputs = {
        "run_name": "target_rig_seg_finetune_seed41_e30",
        "dataset_yaml": "dataset.yaml",
        "dataset_index": "dataset_index.json",
        "dataset_receipt": "dataset_receipt.json",
        "training_receipt": "training_receipt.json",
        "final_checkpoint_receipt": "final_checkpoint_receipt.json",
    }
    if config.get("output") != expected_outputs:
        raise ContractError("Derived-output names or run identity drift")
    return config, checkpoint


def load_capture_inputs(
    manifest_path: Path,
    audit_path: Path,
    data_root: Path,
) -> tuple[CaptureManifest, CaptureAudit]:
    action_config = load_yaml(ACTION_CONFIG)
    manifest_path = manifest_path.expanduser().resolve()
    audit_path = audit_path.expanduser().resolve()
    data_root = data_root.expanduser().resolve()
    manifest = load_manifest(manifest_path, action_config)
    audit = load_capture_audit(audit_path, manifest_path, action_config)
    if Path(audit.data_root).resolve() != data_root:
        raise ContractError("CLI data root does not match the capture-audit data root")
    return manifest, audit


def _safe_source_image(data_root: Path, frame: Frame, config: Mapping[str, Any]) -> Path:
    recorded = frame.image_path
    if "\\" in recorded:
        raise ContractError(f"Non-POSIX image path for frame {frame.frame_id}")
    pure = PurePosixPath(recorded)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in recorded.split("/")):
        raise ContractError(f"Unsafe image path for frame {frame.frame_id}")
    path = (data_root / Path(*pure.parts)).resolve()
    try:
        path.relative_to(data_root)
    except ValueError as error:
        raise ContractError(f"Image escapes data root for frame {frame.frame_id}") from error
    if not path.is_file() or path.stat().st_size <= 0:
        raise ContractError(f"Source image is missing or empty for frame {frame.frame_id}")
    suffixes = {str(value).lower() for value in config["dataset"]["supported_image_suffixes"]}
    if path.suffix.lower() not in suffixes:
        raise ContractError(f"Unsupported image suffix for frame {frame.frame_id}: {path.suffix}")
    observed = sha256(path)
    if frame.image_sha256 is not None and observed != frame.image_sha256:
        raise ContractError(f"Source image SHA-256 mismatch for frame {frame.frame_id}")
    if (
        frame.image_sha256 is None
        and frame.split in {"train", "validation"}
        and config["dataset"]["require_declared_image_sha256_for_real"]
    ):
        # The caller separately exempts explicit synthetic fixtures.
        return path
    return path


def _number_text(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _label_text(frame: Frame, config: Mapping[str, Any]) -> tuple[str, Counter[str]]:
    name_to_index = {
        name: int(index) for index, name in config["dataset"]["class_names"].items()
    }
    lines: list[str] = []
    counts: Counter[str] = Counter()
    for instance in sorted(frame.instances, key=lambda item: item.instance_id):
        if instance.class_name == "partial_unknown":
            raise AssertionError("partial_unknown frame reached label conversion")
        class_index = name_to_index[instance.class_name]
        coordinates = " ".join(
            _number_text(coordinate)
            for point in instance.polygon
            for coordinate in point
        )
        lines.append(f"{class_index} {coordinates}")
        counts[instance.class_name] += 1
    text = "\n".join(lines)
    if text:
        text += "\n"
    return text, counts


def _collect_prepared_frames(
    manifest: CaptureManifest,
    data_root: Path,
    config: Mapping[str, Any],
    *,
    fixture_only: bool,
) -> tuple[list[PreparedFrame], list[dict[str, str]], dict[str, int]]:
    train_split = config["dataset"]["train_split"]
    validation_split = config["dataset"]["validation_split"]
    allowed = {train_split, validation_split}
    split_counts = Counter(frame.split for frame in manifest.frames)
    prepared: list[PreparedFrame] = []
    quarantine: list[dict[str, str]] = []
    for frame in manifest.frames:
        if frame.split not in allowed:
            continue
        if any(instance.class_name == "partial_unknown" for instance in frame.instances):
            quarantine.append(
                {
                    "frame_id": frame.frame_id,
                    "split": frame.split,
                    "reason": "contains_partial_unknown_entire_frame_quarantined",
                }
            )
            continue
        source = _safe_source_image(data_root, frame, config)
        source_hash = sha256(source)
        if not fixture_only and frame.image_sha256 is None:
            raise ContractError(
                f"Real training frame lacks declared image SHA-256: {frame.frame_id}"
            )
        label_text, class_counts = _label_text(frame, config)
        prepared.append(
            PreparedFrame(
                frame_id=frame.frame_id,
                split=frame.split,
                source_image=source,
                source_image_sha256=source_hash,
                image_name=f"{frame.frame_id}{source.suffix.lower()}",
                label_text=label_text,
                label_sha256=sha256_text(label_text),
                class_counts=dict(sorted(class_counts.items())),
            )
        )
    materialized_counts = Counter(frame.split for frame in prepared)
    if (
        config["dataset"]["require_nonempty_train_after_quarantine"]
        and materialized_counts[train_split] == 0
    ):
        raise ContractError("No train frames remain after partial_unknown quarantine")
    if (
        config["dataset"]["require_nonempty_validation_after_quarantine"]
        and materialized_counts[validation_split] == 0
    ):
        raise ContractError("No validation frames remain after partial_unknown quarantine")
    return prepared, quarantine, dict(sorted(split_counts.items()))


def _training_arguments(config: Mapping[str, Any]) -> dict[str, Any]:
    training = config["training"]
    return {
        "epochs": int(training["epochs"]),
        "patience": int(training["patience"]),
        "imgsz": int(training["image_size"]),
        "batch": int(training["batch"]),
        "workers": int(training["workers"]),
        "device": int(training["device"]),
        "seed": int(training["seed"]),
        "deterministic": bool(training["deterministic"]),
        "amp": bool(training["amp"]),
        "optimizer": str(training["optimizer"]),
        "lr0": float(training["lr0"]),
        "lrf": float(training["lrf"]),
        "momentum": float(training["momentum"]),
        "weight_decay": float(training["weight_decay"]),
        "warmup_epochs": float(training["warmup_epochs"]),
        "warmup_momentum": float(training["warmup_momentum"]),
        "warmup_bias_lr": float(training["warmup_bias_lr"]),
        "cos_lr": bool(training["cos_lr"]),
        "cache": bool(training["cache"]),
        "hsv_h": float(training["hsv_h"]),
        "hsv_s": float(training["hsv_s"]),
        "hsv_v": float(training["hsv_v"]),
        "degrees": float(training["degrees"]),
        "translate": float(training["translate"]),
        "scale": float(training["scale"]),
        "shear": float(training["shear"]),
        "perspective": float(training["perspective"]),
        "fliplr": float(training["fliplr"]),
        "flipud": float(training["flipud"]),
        "mosaic": float(training["mosaic"]),
        "mixup": float(training["mixup"]),
        "copy_paste": float(training["copy_paste"]),
        "close_mosaic": int(training["close_mosaic"]),
        "mask_ratio": int(training["mask_ratio"]),
        "overlap_mask": bool(training["overlap_mask"]),
        "pretrained": bool(training["pretrained"]),
        "val": bool(training["val"]),
        "plots": bool(training["plots"]),
    }


def _derived_path(output_directory: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ContractError(f"Unsafe {label}")
    output_directory = output_directory.resolve()
    path = output_directory / Path(*pure.parts)
    try:
        path.relative_to(output_directory)
    except ValueError as error:
        raise ContractError(f"{label} escapes the derived output") from error
    return path


def verify_prepared_dataset(preparation: Preparation) -> None:
    """Recheck the exact receipt-bound bytes immediately around real training."""

    try:
        index = json.loads(preparation.dataset_index.read_text(encoding="utf-8"))
        receipt = json.loads(preparation.dataset_receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Cannot reload prepared dataset receipts: {error}") from error
    if index.get("contract") != "spot_spray_target_rig_segmentation_dataset_index_v1":
        raise ContractError("Prepared dataset index contract drift")
    if index.get("test_entries") != []:
        raise ContractError("Prepared dataset index exposes test entries")
    if receipt != plain(preparation.payload):
        raise ContractError("Prepared dataset receipt changed after creation")
    artifacts = receipt.get("artifacts", {})
    if artifacts.get("dataset_yaml_sha256") != sha256(preparation.dataset_yaml):
        raise ContractError("Prepared dataset YAML hash drift")
    if artifacts.get("dataset_index_sha256") != sha256(preparation.dataset_index):
        raise ContractError("Prepared dataset index hash drift")
    for path_key, hash_key in (
        ("config", "config_sha256"),
        ("manifest", "manifest_sha256"),
        ("capture_audit", "capture_audit_sha256"),
        ("foundation_checkpoint", "foundation_checkpoint_sha256"),
    ):
        input_path = Path(receipt["inputs"][path_key]).expanduser().resolve()
        if not input_path.is_file() or sha256(input_path) != receipt["inputs"][hash_key]:
            raise ContractError(f"Prepared input hash drift: {path_key}")

    entries = index.get("entries")
    if not isinstance(entries, list):
        raise ContractError("Prepared dataset index entries must be a list")
    for row_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ContractError(f"Prepared dataset index entry {row_index} is invalid")
        if entry.get("split") not in {"train", "validation"}:
            raise ContractError("Prepared dataset contains a forbidden split")
        source = Path(entry.get("source_image", "")).expanduser().resolve()
        image = _derived_path(
            preparation.output_directory,
            entry.get("derived_image"),
            f"dataset index entry {row_index} image",
        )
        label = _derived_path(
            preparation.output_directory,
            entry.get("derived_label"),
            f"dataset index entry {row_index} label",
        )
        if not image.is_symlink() or image.resolve() != source:
            raise ContractError(f"Prepared image symlink drift: {entry.get('frame_id')}")
        if not source.is_file() or sha256(source) != entry.get("source_image_sha256"):
            raise ContractError(f"Prepared source image hash drift: {entry.get('frame_id')}")
        if not label.is_file() or label.is_symlink():
            raise ContractError(f"Prepared label file drift: {entry.get('frame_id')}")
        if sha256(label) != entry.get("derived_label_sha256"):
            raise ContractError(f"Prepared label hash drift: {entry.get('frame_id')}")


def prepare_dataset(
    config_path: Path,
    manifest_path: Path,
    audit_path: Path,
    data_root: Path,
    output_directory: Path,
    *,
    fixture_mode: bool = False,
    execute_requested: bool = False,
) -> tuple[Preparation, dict[str, Any], Path]:
    config, foundation = validate_config(config_path)
    manifest_path = manifest_path.expanduser().resolve()
    audit_path = audit_path.expanduser().resolve()
    data_root = data_root.expanduser().resolve()
    output_directory = output_directory.expanduser().resolve()
    manifest, audit = load_capture_inputs(manifest_path, audit_path, data_root)

    if manifest.evidence_scope != audit.evidence_scope:
        raise ContractError(
            "Capture manifest and audit evidence scopes must match exactly"
        )
    automatic_fixture = (
        manifest.evidence_scope == "synthetic_fixture" and audit.synthetic_fixture
    )
    if fixture_mode and not automatic_fixture:
        raise ContractError(
            "--fixture-mode is permitted only for explicitly synthetic manifest and audit evidence"
        )
    fixture_only = automatic_fixture
    if execute_requested and fixture_only:
        raise ContractError("Synthetic or fixture evidence can never execute training")
    manager_accepted = capture_manager_accepted(config)
    real_training_ready = bool(
        not fixture_only
        and manifest.evidence_scope == "real_target_rig"
        and audit.evidence_scope == "real_target_rig"
        and audit.real_proof_accepted
        and manager_accepted
    )
    if not fixture_only and not real_training_ready:
        blockers = []
        if not manager_accepted:
            blockers.append("capture_lane_manager_acceptance")
        if manifest.evidence_scope != "real_target_rig":
            blockers.append("real_target_rig_manifest")
        if not audit.real_proof_accepted:
            blockers.append("physical_READY_capture_audit")
        raise NotReadyError(
            "Real fine-tuning preparation is blocked: " + ", ".join(blockers)
        )
    if output_directory.exists():
        raise ContractError(f"Derived output already exists: {output_directory}")

    prepared, quarantine, source_split_counts = _collect_prepared_frames(
        manifest,
        data_root,
        config,
        fixture_only=fixture_only,
    )
    output_directory.mkdir(parents=True)
    for split in (config["dataset"]["train_split"], config["dataset"]["validation_split"]):
        (output_directory / "images" / split).mkdir(parents=True)
        (output_directory / "labels" / split).mkdir(parents=True)

    index_entries: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    for frame in prepared:
        image_path = output_directory / "images" / frame.split / frame.image_name
        label_path = output_directory / "labels" / frame.split / f"{frame.frame_id}.txt"
        os.symlink(frame.source_image, image_path)
        label_path.write_text(frame.label_text, encoding="utf-8")
        for name, count in frame.class_counts.items():
            class_counts[name] += int(count)
        index_entries.append(
            {
                "frame_id": frame.frame_id,
                "split": frame.split,
                "source_image": str(frame.source_image),
                "source_image_sha256": frame.source_image_sha256,
                "derived_image": str(image_path.relative_to(output_directory)),
                "derived_label": str(label_path.relative_to(output_directory)),
                "derived_label_sha256": sha256(label_path),
                "class_counts": frame.class_counts,
            }
        )

    output_names = config["output"]
    dataset_yaml = output_directory / output_names["dataset_yaml"]
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(output_directory),
                "train": f"images/{config['dataset']['train_split']}",
                "val": f"images/{config['dataset']['validation_split']}",
                "names": config["dataset"]["class_names"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    dataset_index = output_directory / output_names["dataset_index"]
    index_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_segmentation_dataset_index_v1",
        "entries": index_entries,
        "quarantined_partial_unknown_frames": quarantine,
        "test_entries": [],
    }
    write_json(dataset_index, index_payload)

    materialized_counts = Counter(frame.split for frame in prepared)
    dataset_receipt = output_directory / output_names["dataset_receipt"]
    receipt_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_segmentation_dataset_receipt_v1",
        "status": "FIXTURE_ONLY" if fixture_only else "READY_FOR_REAL_TRAINING",
        "real_training_ready": real_training_ready,
        "fixture_only": fixture_only,
        "inputs": {
            "config": str(config_path.expanduser().resolve()),
            "config_sha256": sha256(config_path.expanduser().resolve()),
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "capture_audit": str(audit_path),
            "capture_audit_sha256": sha256(audit_path),
            "data_root": str(data_root),
            "foundation_checkpoint": str(foundation),
            "foundation_checkpoint_sha256": sha256(foundation),
        },
        "capture_release": {
            "manager_accepted": manager_accepted,
            "manager_acceptance": config["capture_interface"]["manager_acceptance"],
            "audit_status": audit.status,
            "audit_real_proof_accepted": audit.real_proof_accepted,
            "audit_real_proof_checks": dict(audit.real_proof_checks),
            "source_hashes": config["capture_interface"]["sources"],
        },
        "dataset_contract": config["dataset"],
        "counts": {
            "source_frames_by_split": source_split_counts,
            "materialized_train_frames": materialized_counts[
                config["dataset"]["train_split"]
            ],
            "materialized_validation_frames": materialized_counts[
                config["dataset"]["validation_split"]
            ],
            "quarantined_partial_unknown_frames": len(quarantine),
            "excluded_test_frames": source_split_counts.get("test", 0),
            "materialized_instances_by_class": dict(sorted(class_counts.items())),
        },
        "quarantined_partial_unknown_frames": quarantine,
        "test_isolation": {
            "test_manifest_metadata_used_only_to_count_exclusion": True,
            "test_image_bytes_read": False,
            "test_images_materialized": False,
            "test_labels_materialized": False,
            "test_used_for_training": False,
            "test_used_for_checkpoint_selection": False,
        },
        "artifacts": {
            "dataset_yaml": str(dataset_yaml),
            "dataset_yaml_sha256": sha256(dataset_yaml),
            "dataset_index": str(dataset_index),
            "dataset_index_sha256": sha256(dataset_index),
        },
        "claims": config["claims"],
    }
    write_json(dataset_receipt, receipt_payload)
    preparation = Preparation(
        output_directory=output_directory,
        dataset_yaml=dataset_yaml,
        dataset_index=dataset_index,
        dataset_receipt=dataset_receipt,
        real_training_ready=real_training_ready,
        fixture_only=fixture_only,
        payload=receipt_payload,
    )
    return preparation, config, foundation


def _dry_run_receipts(
    preparation: Preparation,
    config_path: Path,
    config: Mapping[str, Any],
    foundation: Path,
) -> tuple[Path, Path]:
    output_names = config["output"]
    training_receipt = preparation.output_directory / output_names["training_receipt"]
    training_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_segmentation_training_receipt_v1",
        "status": (
            "FIXTURE_ONLY_DRY_RUN"
            if preparation.fixture_only
            else "REAL_TRAINING_READY_DRY_RUN"
        ),
        "training_executed": False,
        "config": str(config_path.expanduser().resolve()),
        "config_sha256": sha256(config_path.expanduser().resolve()),
        "dataset_receipt": str(preparation.dataset_receipt),
        "dataset_receipt_sha256": sha256(preparation.dataset_receipt),
        "dataset_yaml": str(preparation.dataset_yaml),
        "dataset_yaml_sha256": sha256(preparation.dataset_yaml),
        "foundation_checkpoint": str(foundation),
        "foundation_checkpoint_sha256": sha256(foundation),
        "training_arguments": _training_arguments(config),
        "selection": config["selection"],
        "test_access": {
            "training": False,
            "checkpoint_selection": False,
            "threshold_calibration": False,
        },
    }
    write_json(training_receipt, training_payload)
    final_receipt = preparation.output_directory / output_names["final_checkpoint_receipt"]
    final_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_final_checkpoint_receipt_v1",
        "status": "NOT_PRODUCED_DRY_RUN",
        "training_executed": False,
        "checkpoint": None,
        "checkpoint_sha256": None,
        "deployment_or_field_go": False,
        "reason": "Dry-run/fixture preparation cannot produce a final checkpoint.",
    }
    write_json(final_receipt, final_payload)
    return training_receipt, final_receipt


def _completed_epoch_sequence(results_csv: Path) -> list[int]:
    if not results_csv.is_file():
        return []
    try:
        with results_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "epoch" not in reader.fieldnames:
                raise ContractError("Training results CSV lacks the epoch column")
            return [int(row["epoch"]) for row in reader]
    except (OSError, TypeError, ValueError) as error:
        raise ContractError(f"Training results CSV epoch sequence is invalid: {error}") from error


def execute_training(
    preparation: Preparation,
    config_path: Path,
    config: Mapping[str, Any],
    foundation: Path,
) -> tuple[Path, Path]:
    if preparation.fixture_only or not preparation.real_training_ready:
        raise ContractError("Fixture or unready capture evidence cannot execute training")
    verify_prepared_dataset(preparation)
    from ultralytics import YOLO, __version__ as ultralytics_version, settings
    import torch

    if ultralytics_version != str(config["model_family"]["package_version"]):
        raise ContractError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise NotReadyError("CUDA is required for the real fine-tune execution")
    settings.update(
        {
            name: False
            for name in (
                "clearml",
                "comet",
                "dvc",
                "hub",
                "mlflow",
                "neptune",
                "wandb",
            )
        }
    )
    dataset_payload = load_yaml(preparation.dataset_yaml)
    if set(dataset_payload) != {"path", "train", "val", "names"}:
        raise ContractError("Prepared dataset YAML exposes an unexpected split or field")
    if "test" in dataset_payload:
        raise ContractError("Prepared training dataset must not expose test")

    project = preparation.output_directory / "runs"
    run_name = str(config["output"]["run_name"])
    run_directory = project / run_name
    if run_directory.exists():
        raise ContractError(f"Training run already exists: {run_directory}")
    model = YOLO(str(foundation))
    if model.task != "segment":
        raise ContractError("Selected foundation checkpoint is not a segmentation model")
    arguments = _training_arguments(config)
    started = time.monotonic()
    results = model.train(
        data=str(preparation.dataset_yaml),
        project=str(project),
        name=run_name,
        exist_ok=False,
        verbose=True,
        **arguments,
    )
    elapsed = time.monotonic() - started
    last = run_directory / "weights/last.pt"
    results_csv = run_directory / "results.csv"
    if not last.is_file() or not results_csv.is_file():
        raise ContractError("Training artifacts are incomplete")
    expected_epochs = list(range(1, int(config["training"]["epochs"]) + 1))
    epoch_sequence = _completed_epoch_sequence(results_csv)
    if epoch_sequence != expected_epochs:
        raise ContractError("Fixed epoch sequence was violated")
    completed = len(epoch_sequence)
    verify_prepared_dataset(preparation)
    post_config, post_foundation = validate_config(config_path)
    if post_config != config or post_foundation != foundation:
        raise ContractError("Fine-tune config or foundation changed during training")

    training_receipt = preparation.output_directory / config["output"]["training_receipt"]
    training_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_segmentation_training_receipt_v1",
        "status": "TRAINING_COMPLETE_TEST_UNTOUCHED_NOT_EVALUATED",
        "training_executed": True,
        "config": str(config_path.expanduser().resolve()),
        "config_sha256": sha256(config_path.expanduser().resolve()),
        "dataset_receipt": str(preparation.dataset_receipt),
        "dataset_receipt_sha256": sha256(preparation.dataset_receipt),
        "dataset_yaml": str(preparation.dataset_yaml),
        "dataset_yaml_sha256": sha256(preparation.dataset_yaml),
        "foundation_checkpoint": str(foundation),
        "foundation_checkpoint_sha256": sha256(foundation),
        "training_arguments": arguments,
        "epochs_completed": completed,
        "selection": config["selection"],
        "test_access": {
            "training": False,
            "checkpoint_selection": False,
            "threshold_calibration": False,
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(int(config["training"]["device"])),
            "ultralytics": ultralytics_version,
            "elapsed_seconds": elapsed,
        },
        "results": plain(getattr(results, "results_dict", {})),
        "artifacts": {
            "run_directory": str(run_directory),
            "results_csv": str(results_csv),
            "results_csv_sha256": sha256(results_csv),
            "fixed_final_checkpoint": str(last),
            "fixed_final_checkpoint_sha256": sha256(last),
        },
    }
    write_json(training_receipt, training_payload)

    final_receipt = preparation.output_directory / config["output"][
        "final_checkpoint_receipt"
    ]
    final_payload = {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_final_checkpoint_receipt_v1",
        "status": "FINAL_CHECKPOINT_FROZEN_NOT_EVALUATED",
        "training_executed": True,
        "selection_rule": config["selection"]["rule"],
        "checkpoint": str(last),
        "checkpoint_sha256": sha256(last),
        "results_csv": str(results_csv),
        "results_csv_sha256": sha256(results_csv),
        "dataset_receipt": str(preparation.dataset_receipt),
        "dataset_receipt_sha256": sha256(preparation.dataset_receipt),
        "foundation_checkpoint_sha256": sha256(foundation),
        "test_accessed": False,
        "offline_model_go": False,
        "field_fire_go": False,
        "chemical_fire_go": False,
        "next_required_step": "Generate validation/test predictions and run the frozen track-action evaluator.",
    }
    write_json(final_receipt, final_payload)
    return training_receipt, final_receipt


def fail_closed_payload(status: str, reason: str, config_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_segmentation_finetune_v1",
        "status": status,
        "reason": reason,
        "config": str(config_path),
        "config_sha256": sha256(config_path) if config_path.is_file() else None,
        "training_executed": False,
        "real_training_ready": False,
        "offline_model_go": False,
        "field_fire_go": False,
        "chemical_fire_go": False,
    }


def run_cli(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config_path = arguments.config.expanduser().resolve()
    required = {
        "manifest": arguments.manifest,
        "capture_audit": arguments.capture_audit,
        "data_root": arguments.data_root,
        "output_directory": arguments.output_directory,
    }
    missing = sorted(name for name, value in required.items() if value is None)
    if missing:
        result = fail_closed_payload(
            "NOT_READY",
            "Missing required inputs: " + ", ".join(missing),
            config_path,
        )
        return result, EXIT_NOT_READY
    if arguments.execute_training and arguments.fixture_mode:
        result = fail_closed_payload(
            "CONTRACT_ERROR",
            "Fixture mode can never execute training.",
            config_path,
        )
        return result, EXIT_CONTRACT_ERROR
    try:
        preparation, config, foundation = prepare_dataset(
            config_path,
            arguments.manifest,
            arguments.capture_audit,
            arguments.data_root,
            arguments.output_directory,
            fixture_mode=arguments.fixture_mode,
            execute_requested=arguments.execute_training,
        )
        if arguments.execute_training:
            training_receipt, final_receipt = execute_training(
                preparation,
                config_path,
                config,
                foundation,
            )
            status = "TRAINING_COMPLETE_TEST_UNTOUCHED_NOT_EVALUATED"
            exit_code = EXIT_READY
        else:
            training_receipt, final_receipt = _dry_run_receipts(
                preparation,
                config_path,
                config,
                foundation,
            )
            status = (
                "FIXTURE_ONLY" if preparation.fixture_only else "REAL_DRY_RUN_READY"
            )
            exit_code = EXIT_FIXTURE_ONLY if preparation.fixture_only else EXIT_READY
        result = {
            "schema_version": 1,
            "contract": config["contract"],
            "status": status,
            "training_executed": bool(arguments.execute_training),
            "real_training_ready": preparation.real_training_ready,
            "fixture_only": preparation.fixture_only,
            "artifacts": {
                "dataset_receipt": str(preparation.dataset_receipt),
                "dataset_receipt_sha256": sha256(preparation.dataset_receipt),
                "training_receipt": str(training_receipt),
                "training_receipt_sha256": sha256(training_receipt),
                "final_checkpoint_receipt": str(final_receipt),
                "final_checkpoint_receipt_sha256": sha256(final_receipt),
            },
            "offline_model_go": False,
            "field_fire_go": False,
            "chemical_fire_go": False,
        }
        return result, exit_code
    except NotReadyError as error:
        return fail_closed_payload("NOT_READY", str(error), config_path), EXIT_NOT_READY
    except (ContractError, KeyError, TypeError, ValueError, OSError) as error:
        return (
            fail_closed_payload(
                "CONTRACT_ERROR",
                f"Fail-closed contract error: {error}",
                config_path,
            ),
            EXIT_CONTRACT_ERROR,
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--capture-audit", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument(
        "--fixture-mode",
        action="store_true",
        help="Materialize synthetic contract artifacts while permanently blocking training.",
    )
    parser.add_argument(
        "--execute-training",
        action="store_true",
        help="Explicitly execute GPU training after every real provenance gate passes.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    result, exit_code = run_cli(parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
