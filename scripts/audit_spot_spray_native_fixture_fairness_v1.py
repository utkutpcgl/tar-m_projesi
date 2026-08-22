#!/usr/bin/env python3
"""Audit the frozen native spot-spray fixture from persisted predictions only.

The audit is deliberately post-hoc and non-selective: it verifies immutable
inputs, recomputes locked metrics, and runs labelled descriptive sweeps.  It
never invokes model inference, changes the locked threshold, or writes into the
active full-benchmark lane.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "configs/benchmark/spot_spray_native_fixture_fairness_audit_v1.yaml"
)
AUDIT_CONTRACT = "spot_spray_native_fixture_fairness_audit_v1"
MANIFEST_CONTRACT = "spot_spray_simulation_video_sequence_v1"
PREDICTION_CONTRACT = "spot_spray_simulation_video_predictions_v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(RuntimeError):
    """Raised when a frozen input or non-tuning invariant fails closed."""


@dataclass(frozen=True)
class BinaryMask:
    """A compact bounding-box crop of one native-resolution binary mask."""

    shape: tuple[int, int]
    bbox_xyxy: tuple[int, int, int, int]
    crop: np.ndarray
    area: int

    @classmethod
    def from_full(cls, value: np.ndarray) -> "BinaryMask":
        mask = np.asarray(value, dtype=bool)
        if mask.ndim != 2:
            raise ContractError(f"Binary mask must be two-dimensional, got {mask.shape}")
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return cls(mask.shape, (0, 0, 0, 0), np.zeros((0, 0), dtype=bool), 0)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        crop = np.ascontiguousarray(mask[y0:y1, x0:x1])
        return cls(mask.shape, (x0, y0, x1, y1), crop, int(crop.sum()))

    @property
    def centroid_xy(self) -> tuple[float, float]:
        if self.area == 0:
            raise ContractError("Empty masks do not have a centroid")
        ys, xs = np.where(self.crop)
        x0, y0, _, _ = self.bbox_xyxy
        return float(xs.mean() + x0), float(ys.mean() + y0)

    def intersection_area(self, other: "BinaryMask") -> int:
        if self.shape != other.shape:
            raise ContractError(f"Mask shape mismatch: {self.shape} versus {other.shape}")
        ax0, ay0, ax1, ay1 = self.bbox_xyxy
        bx0, by0, bx1, by1 = other.bbox_xyxy
        x0, y0 = max(ax0, bx0), max(ay0, by0)
        x1, y1 = min(ax1, bx1), min(ay1, by1)
        if x0 >= x1 or y0 >= y1:
            return 0
        left = self.crop[y0 - ay0 : y1 - ay0, x0 - ax0 : x1 - ax0]
        right = other.crop[y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0]
        return int(np.logical_and(left, right).sum())

    def iou(self, other: "BinaryMask") -> float:
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        return intersection / union if union else 0.0

    def semantic_overlap(self, semantic: np.ndarray, semantic_id: int) -> int:
        if tuple(semantic.shape) != self.shape or self.area == 0:
            return 0
        x0, y0, x1, y1 = self.bbox_xyxy
        return int(np.logical_and(self.crop, semantic[y0:y1, x0:x1] == semantic_id).sum())


@dataclass(frozen=True)
class TrackLabel:
    mask_id: int
    track_id: str
    class_name: str
    canopy_span_mm: float
    visible_fraction: float
    partial: bool
    size_stratum: str


@dataclass(frozen=True)
class TruthFrame:
    semantic_path: Path
    semantic_sha256: str
    track_path: Path
    track_sha256: str
    shape: tuple[int, int]
    semantic_counts: Mapping[int, int]
    labels: tuple[TrackLabel, ...]
    masks_by_id: Mapping[int, BinaryMask]


@dataclass(frozen=True)
class Detection:
    frame_index: int
    detection_id: int
    class_id: int
    class_name: str
    confidence: float
    stored_track_id: str
    mask: BinaryMask
    centroid_xy: tuple[float, float]


@dataclass(frozen=True)
class PredictionFrame:
    frame_id: str
    frame_index: int
    image_path: Path
    image_sha256: str
    truth: TruthFrame
    detections: tuple[Detection, ...]


@dataclass(frozen=True)
class PredictionSequence:
    sequence_id: str
    pair_id: str
    split: str
    condition: str
    frames: tuple[PredictionFrame, ...]


def stable_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(payload), encoding="utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be a mapping")
    return value


def require_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be a sequence")
    return value


def verify_file(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(str(expected_sha256)):
        raise ContractError(f"{label} has an invalid expected SHA-256")
    if not path.is_file():
        raise ContractError(f"{label} is missing: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ContractError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = dict(require_mapping(payload, "audit config"))
    if config.get("contract") != AUDIT_CONTRACT or config.get("schema_version") != 1:
        raise ContractError("Audit config contract or schema version is invalid")
    policy = require_mapping(config.get("evidence_policy"), "evidence_policy")
    required_false = (
        "field_or_deployment_claim_allowed",
        "chemical_fire_go_allowed",
        "product_go_allowed",
        "locked_test_retuning_allowed",
        "descriptive_sweeps_are_selection_inputs",
    )
    if any(policy.get(key) is not False for key in required_false):
        raise ContractError("Audit evidence policy must fail closed")
    if policy.get("outcome_target_tuning_forbidden") is not True:
        raise ContractError("Outcome-target tuning must be forbidden")
    return config


def verify_anchor_sources(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Path]]:
    sources = require_mapping(config.get("sources"), "sources")
    anchor_names = (
        "metrics",
        "threshold_lock",
        "sequence_manifest",
        "inference_config",
        "run_receipt",
        "checkpoint",
    )
    anchors: dict[str, Any] = {}
    paths: dict[str, Path] = {
        "fixture_root": resolve_path(require_mapping(sources["fixture_root"], "fixture_root")["path"]),
        "prediction_root": resolve_path(
            require_mapping(sources["prediction_root"], "prediction_root")["path"]
        ),
    }
    for name in anchor_names:
        item = require_mapping(sources.get(name), f"sources.{name}")
        path = resolve_path(item["path"])
        anchors[name] = verify_file(path, str(item["sha256"]), f"source {name}")
        paths[name] = path
    prediction_items = require_mapping(sources.get("predictions"), "sources.predictions")
    anchors["predictions"] = {}
    for name, value in sorted(prediction_items.items()):
        item = require_mapping(value, f"sources.predictions.{name}")
        path = resolve_path(item["path"])
        anchors["predictions"][name] = {
            **verify_file(path, str(item["sha256"]), f"prediction {name}"),
            "condition": str(item["condition"]),
            "split": str(item["split"]),
        }
        paths[f"prediction:{name}"] = path
    fingerprint_payload = {
        name: value["sha256"]
        for name, value in anchors.items()
        if name != "predictions"
    }
    fingerprint_payload["predictions"] = {
        name: value["sha256"] for name, value in anchors["predictions"].items()
    }
    anchors["source_fingerprint_sha256"] = sha256_bytes(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    return anchors, paths


def normalize_class_names(value: Any) -> dict[int, str]:
    if isinstance(value, Mapping):
        return {int(key): str(name) for key, name in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {index: str(name) for index, name in enumerate(value)}
    raise ContractError(f"Unsupported checkpoint class-name payload: {type(value).__name__}")


def verify_checkpoint_class_mapping(
    checkpoint_path: Path,
    expected_names: Mapping[int, str],
) -> dict[str, Any]:
    """Read names only after the caller has verified checkpoint bytes."""

    import torch

    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(payload, Mapping):
        raise ContractError("Checkpoint payload is not a mapping")
    model = payload.get("model") or payload.get("ema")
    if model is None:
        raise ContractError("Checkpoint has neither model nor ema payload")
    actual = normalize_class_names(getattr(model, "names", None))
    expected = {int(key): str(value) for key, value in expected_names.items()}
    if actual != expected:
        raise ContractError(f"Checkpoint class mapping mismatch: {actual} != {expected}")
    receipt = {
        "hash_verified_before_deserialization": True,
        "payload_keys": sorted(str(key) for key in payload),
        "model_type": f"{type(model).__module__}.{type(model).__name__}",
        "class_names": {str(key): value for key, value in sorted(actual.items())},
        "class_count": len(actual),
    }
    del model, payload
    gc.collect()
    return receipt


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return dict(require_mapping(json.loads(path.read_text(encoding="utf-8")), label))
    except json.JSONDecodeError as error:
        raise ContractError(f"{label} is not valid JSON: {error}") from error


def parse_track_label(value: Any, label: str) -> TrackLabel:
    row = require_mapping(value, label)
    class_name = str(row["class_name"])
    if class_name not in {"weed", "crop"}:
        raise ContractError(f"{label} has undeclared class {class_name}")
    return TrackLabel(
        mask_id=int(row["mask_id"]),
        track_id=str(row["track_id"]),
        class_name=class_name,
        canopy_span_mm=float(row["canopy_span_mm"]),
        visible_fraction=float(row["visible_fraction"]),
        partial=bool(row["partial"]),
        size_stratum=str(row["size_stratum"]),
    )


def load_and_verify_manifest(
    manifest_path: Path,
    fixture_root: Path,
    semantic_ids: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    manifest = load_json(manifest_path, "sequence manifest")
    if manifest.get("contract") != MANIFEST_CONTRACT or manifest.get("schema_version") != 1:
        raise ContractError("Sequence manifest contract or schema version is invalid")
    if set(manifest.get("conditions", [])) != {"ideal", "degraded"}:
        raise ContractError("Sequence manifest must contain ideal and degraded conditions")
    truth_cache: dict[tuple[str, str], TruthFrame] = {}
    decoded_sequences: dict[str, list[dict[str, Any]]] = {}
    verified_images: set[Path] = set()
    image_bytes = 0
    raw_mask_bytes = 0
    semantic_values: set[int] = set()
    label_pixels_checked = 0
    sequence_rows = require_sequence(manifest.get("sequences"), "manifest.sequences")
    for sequence_index, raw_sequence in enumerate(sequence_rows):
        sequence = require_mapping(raw_sequence, f"manifest.sequences[{sequence_index}]")
        sequence_id = str(sequence["sequence_id"])
        frames: list[dict[str, Any]] = []
        for frame_index, raw_frame in enumerate(
            require_sequence(sequence.get("frames"), f"{sequence_id}.frames")
        ):
            frame = require_mapping(raw_frame, f"{sequence_id}.frames[{frame_index}]")
            if int(frame["frame_index"]) != frame_index:
                raise ContractError(f"{sequence_id} frame indices are not contiguous")
            image_path = resolve_path(fixture_root / str(frame["image_path"]))
            if image_path not in verified_images:
                receipt = verify_file(
                    image_path, str(frame["image_sha256"]), f"RGB {sequence_id}:{frame_index}"
                )
                image_bytes += int(receipt["bytes"])
                verified_images.add(image_path)
            semantic_path = resolve_path(fixture_root / str(frame["semantic_mask_path"]))
            track_path = resolve_path(fixture_root / str(frame["track_mask_path"]))
            cache_key = (str(semantic_path), str(track_path))
            labels = tuple(
                parse_track_label(value, f"{sequence_id}:{frame_index}.tracks")
                for value in require_sequence(frame.get("tracks"), "frame.tracks")
            )
            if cache_key not in truth_cache:
                semantic_receipt = verify_file(
                    semantic_path,
                    str(frame["semantic_mask_sha256"]),
                    f"semantic GT {sequence_id}:{frame_index}",
                )
                track_receipt = verify_file(
                    track_path,
                    str(frame["track_mask_sha256"]),
                    f"track GT {sequence_id}:{frame_index}",
                )
                raw_mask_bytes += int(semantic_receipt["bytes"]) + int(track_receipt["bytes"])
                semantic = cv2.imread(str(semantic_path), cv2.IMREAD_UNCHANGED)
                track_mask = cv2.imread(str(track_path), cv2.IMREAD_UNCHANGED)
                if semantic is None or track_mask is None or semantic.shape != track_mask.shape:
                    raise ContractError(f"GT decode or shape mismatch at {sequence_id}:{frame_index}")
                allowed = {int(value) for value in semantic_ids.values()}
                observed = {int(value) for value in np.unique(semantic)}
                if not observed <= allowed:
                    raise ContractError(f"Unexpected semantic IDs {observed - allowed}")
                semantic_values.update(observed)
                label_by_id = {item.mask_id: item for item in labels}
                if len(label_by_id) != len(labels):
                    raise ContractError(f"Duplicate track mask ID at {sequence_id}:{frame_index}")
                observed_track_ids = {int(value) for value in np.unique(track_mask)} - {0}
                if observed_track_ids != set(label_by_id):
                    raise ContractError(
                        f"GT track label/mask IDs disagree at {sequence_id}:{frame_index}"
                    )
                masks_by_id: dict[int, BinaryMask] = {}
                for mask_id, item in sorted(label_by_id.items()):
                    full_mask = track_mask == mask_id
                    expected_semantic = int(semantic_ids[item.class_name])
                    if not np.all(semantic[full_mask] == expected_semantic):
                        raise ContractError(
                            f"GT class/semantic mismatch for {item.track_id} at frame {frame_index}"
                        )
                    masks_by_id[mask_id] = BinaryMask.from_full(full_mask)
                    label_pixels_checked += int(full_mask.sum())
                counts = {
                    int(value): int((semantic == int(value)).sum()) for value in observed
                }
                truth_cache[cache_key] = TruthFrame(
                    semantic_path=semantic_path,
                    semantic_sha256=str(frame["semantic_mask_sha256"]),
                    track_path=track_path,
                    track_sha256=str(frame["track_mask_sha256"]),
                    shape=tuple(int(value) for value in semantic.shape),
                    semantic_counts=counts,
                    labels=labels,
                    masks_by_id=masks_by_id,
                )
            truth = truth_cache[cache_key]
            if truth.labels != labels:
                raise ContractError(f"Matched arms disagree on GT labels at {sequence_id}:{frame_index}")
            frames.append(
                {
                    "frame_id": str(frame["frame_id"]),
                    "frame_index": frame_index,
                    "image_path": image_path,
                    "image_sha256": str(frame["image_sha256"]),
                    "truth": truth,
                }
            )
        decoded_sequences[sequence_id] = frames
    pair_groups: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for raw_sequence in sequence_rows:
        sequence = require_mapping(raw_sequence, "manifest sequence")
        pair_groups[(str(sequence["split"]), str(sequence["pair_id"]))][
            str(sequence["condition"])
        ] = decoded_sequences[str(sequence["sequence_id"])]
    for key, conditions in pair_groups.items():
        if set(conditions) != {"ideal", "degraded"}:
            raise ContractError(f"Matched pair {key} is missing an arm")
        for ideal, degraded in zip(conditions["ideal"], conditions["degraded"]):
            if ideal["truth"] is not degraded["truth"]:
                raise ContractError(f"Matched arms do not share exact GT at {key}")
    validation = {
        "sequence_count": len(decoded_sequences),
        "frame_reference_count": sum(len(value) for value in decoded_sequences.values()),
        "unique_rgb_file_count": len(verified_images),
        "unique_gt_frame_count": len(truth_cache),
        "verified_rgb_bytes": image_bytes,
        "verified_gt_mask_bytes": raw_mask_bytes,
        "semantic_ids_observed": sorted(semantic_values),
        "track_label_pixels_class_checked": label_pixels_checked,
        "matched_arm_ground_truth_object_identity": True,
        "all_declared_hashes_verified": True,
    }
    return manifest, decoded_sequences, validation


def load_prediction_sequence(
    path: Path,
    expected_condition: str,
    expected_split: str,
    manifest_sequences: Mapping[str, list[dict[str, Any]]],
    prediction_root: Path,
    receipt_artifacts: Mapping[str, str],
    expected_checkpoint_sha256: str,
    expected_manifest_sha256: str,
    expected_config_sha256: str,
    class_names: Mapping[int, str],
) -> tuple[PredictionSequence, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or rows[0].get("record_type") != "prediction_metadata":
        raise ContractError(f"Prediction file lacks metadata row: {path}")
    metadata = require_mapping(rows[0], "prediction metadata")
    expected_metadata = {
        "contract": PREDICTION_CONTRACT,
        "condition": expected_condition,
        "split": expected_split,
        "checkpoint_sha256": expected_checkpoint_sha256,
        "sequence_manifest_sha256": expected_manifest_sha256,
        "config_sha256": expected_config_sha256,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise ContractError(f"Prediction metadata {key} mismatch in {path}")
    frame_rows = [row for row in rows[1:] if row.get("record_type") == "frame_prediction"]
    if len(frame_rows) != len(rows) - 1 or not frame_rows:
        raise ContractError(f"Prediction rows are missing or have unknown record types: {path}")
    sequence_ids = {str(row["sequence_id"]) for row in frame_rows}
    if len(sequence_ids) != 1:
        raise ContractError(f"Prediction file must contain exactly one sequence: {path}")
    sequence_id = next(iter(sequence_ids))
    if sequence_id not in manifest_sequences:
        raise ContractError(f"Prediction references undeclared sequence {sequence_id}")
    manifest_frames = manifest_sequences[sequence_id]
    frame_rows.sort(key=lambda row: int(row["frame_index"]))
    if len(frame_rows) != len(manifest_frames):
        raise ContractError(f"Prediction/manifest frame count mismatch for {sequence_id}")
    frames: list[PredictionFrame] = []
    mask_hashes_verified = 0
    masks_verified = 0
    mask_pixels_verified = 0
    native_shape: tuple[int, int] | None = None
    for expected_index, (row, manifest_frame) in enumerate(zip(frame_rows, manifest_frames)):
        if int(row["frame_index"]) != expected_index:
            raise ContractError(f"Prediction frames are not contiguous for {sequence_id}")
        if row["frame_id"] != manifest_frame["frame_id"]:
            raise ContractError(f"Prediction frame ID mismatch for {sequence_id}:{expected_index}")
        if row["source_image_sha256"] != manifest_frame["image_sha256"]:
            raise ContractError(f"Prediction source hash mismatch for {sequence_id}:{expected_index}")
        relative_npz = str(row["prediction_masks_npz"])
        npz_path = (prediction_root / relative_npz).resolve()
        if not npz_path.is_relative_to(prediction_root.resolve()):
            raise ContractError(f"Prediction mask path escapes source root: {relative_npz}")
        npz_hash = str(row["prediction_masks_npz_sha256"])
        verify_file(npz_path, npz_hash, f"prediction NPZ {sequence_id}:{expected_index}")
        if receipt_artifacts.get(relative_npz) != npz_hash:
            raise ContractError(f"Run receipt does not bind prediction NPZ {relative_npz}")
        mask_hashes_verified += 1
        with np.load(npz_path, allow_pickle=False) as archive:
            if set(archive.files) != {"masks", "class_ids", "confidences", "track_numbers"}:
                raise ContractError(f"Unexpected NPZ fields in {relative_npz}")
            masks = np.asarray(archive["masks"], dtype=np.uint8)
            class_ids = np.asarray(archive["class_ids"], dtype=np.int64)
            confidences = np.asarray(archive["confidences"], dtype=np.float64)
            track_numbers = np.asarray(archive["track_numbers"], dtype=np.int64)
        detections_json = require_sequence(row.get("detections"), "frame detections")
        length = len(detections_json)
        if not (len(class_ids) == len(confidences) == len(track_numbers) == length):
            raise ContractError(f"Prediction array length mismatch in {relative_npz}")
        if length:
            if masks.ndim != 3 or masks.shape[0] != length:
                raise ContractError(f"Prediction mask shape mismatch in {relative_npz}")
            frame_shape = tuple(int(value) for value in masks.shape[1:])
            if frame_shape != manifest_frame["truth"].shape:
                raise ContractError(f"Prediction masks are not native GT shape in {relative_npz}")
            native_shape = native_shape or frame_shape
            if native_shape != frame_shape:
                raise ContractError("Prediction mask native shape changed across frames")
        detections: list[Detection] = []
        for index, raw_detection in enumerate(detections_json):
            item = require_mapping(raw_detection, "detection")
            if int(item["detection_id"]) != index:
                raise ContractError(f"Detection IDs are not contiguous in {relative_npz}")
            class_id = int(class_ids[index])
            if class_id not in class_names or item["class_name"] != class_names[class_id]:
                raise ContractError(f"Prediction class mapping mismatch in {relative_npz}")
            confidence = float(confidences[index])
            if not math.isclose(confidence, float(item["confidence"]), abs_tol=1e-6):
                raise ContractError(f"Prediction confidence mismatch in {relative_npz}")
            full_mask = masks[index].astype(bool)
            compact = BinaryMask.from_full(full_mask)
            if compact.area != int(item["mask_pixels"]):
                raise ContractError(f"Prediction mask area mismatch in {relative_npz}")
            if compact.bbox_xyxy != tuple(int(value) for value in item["bbox_xyxy"]):
                raise ContractError(f"Prediction bbox mismatch in {relative_npz}")
            if sha256_bytes(masks[index].tobytes()) != item["mask_sha256"]:
                raise ContractError(f"Prediction raw mask hash mismatch in {relative_npz}")
            track_id = f"p{int(track_numbers[index]):04d}"
            if track_id != item["predicted_track_id"]:
                raise ContractError(f"Prediction track-number mismatch in {relative_npz}")
            centroid = compact.centroid_xy
            declared_centroid = tuple(float(value) for value in item["centroid_xy"])
            if not all(
                math.isclose(left, right, abs_tol=1e-6)
                for left, right in zip(centroid, declared_centroid)
            ):
                raise ContractError(f"Prediction centroid mismatch in {relative_npz}")
            detections.append(
                Detection(
                    frame_index=expected_index,
                    detection_id=index,
                    class_id=class_id,
                    class_name=class_names[class_id],
                    confidence=confidence,
                    stored_track_id=track_id,
                    mask=compact,
                    centroid_xy=centroid,
                )
            )
            masks_verified += 1
            mask_pixels_verified += compact.area
        frames.append(
            PredictionFrame(
                frame_id=str(row["frame_id"]),
                frame_index=expected_index,
                image_path=manifest_frame["image_path"],
                image_sha256=manifest_frame["image_sha256"],
                truth=manifest_frame["truth"],
                detections=tuple(detections),
            )
        )
    pair_ids = {str(row["pair_id"]) for row in frame_rows}
    if len(pair_ids) != 1:
        raise ContractError(f"Prediction sequence has multiple pair IDs: {sequence_id}")
    sequence = PredictionSequence(
        sequence_id=sequence_id,
        pair_id=next(iter(pair_ids)),
        split=expected_split,
        condition=expected_condition,
        frames=tuple(frames),
    )
    validation = {
        "sequence_id": sequence_id,
        "frame_count": len(frames),
        "detection_count": masks_verified,
        "prediction_npz_hashes_verified": mask_hashes_verified,
        "raw_detection_mask_hashes_verified": masks_verified,
        "raw_detection_mask_pixels_verified": mask_pixels_verified,
        "native_mask_shape": list(native_shape) if native_shape else None,
        "metadata_contract_verified": True,
    }
    return sequence, validation


def mask_union(masks: Sequence[BinaryMask], shape: tuple[int, int]) -> BinaryMask:
    nonempty = [mask for mask in masks if mask.area]
    if not nonempty:
        return BinaryMask(shape, (0, 0, 0, 0), np.zeros((0, 0), dtype=bool), 0)
    if any(mask.shape != shape for mask in nonempty):
        raise ContractError("Cannot union masks with different native shapes")
    x0 = min(mask.bbox_xyxy[0] for mask in nonempty)
    y0 = min(mask.bbox_xyxy[1] for mask in nonempty)
    x1 = max(mask.bbox_xyxy[2] for mask in nonempty)
    y1 = max(mask.bbox_xyxy[3] for mask in nonempty)
    merged = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    for mask in nonempty:
        mx0, my0, mx1, my1 = mask.bbox_xyxy
        merged[my0 - y0 : my1 - y0, mx0 - x0 : mx1 - x0] |= mask.crop
    return BinaryMask(shape, (x0, y0, x1, y1), merged, int(merged.sum()))


def greedy_mask_matches(
    predicted: Sequence[BinaryMask],
    truth: Sequence[BinaryMask],
    minimum_iou: float,
) -> list[tuple[int, int, float]]:
    candidates = [
        (-prediction.iou(target), prediction_index, truth_index)
        for prediction_index, prediction in enumerate(predicted)
        for truth_index, target in enumerate(truth)
    ]
    candidates.sort()
    matched_prediction: set[int] = set()
    matched_truth: set[int] = set()
    output: list[tuple[int, int, float]] = []
    for negative_iou, prediction_index, truth_index in candidates:
        overlap = -negative_iou
        if overlap < minimum_iou:
            break
        if prediction_index in matched_prediction or truth_index in matched_truth:
            continue
        matched_prediction.add(prediction_index)
        matched_truth.add(truth_index)
        output.append((prediction_index, truth_index, overlap))
    return output


def safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def prf_metrics(counts: Mapping[str, int]) -> dict[str, Any]:
    tp, fp, fn = int(counts["tp"]), int(counts["fp"]), int(counts["fn"])
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
        state = "undefined_missing_precision_or_recall_denominator"
    elif precision + recall == 0.0:
        f1 = 0.0
        state = "defined_numeric_zero"
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
        state = "defined_nonzero"
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f1_state": state,
        "precision_denominator": tp + fp,
        "recall_denominator": tp + fn,
    }


def empty_evaluation_counts() -> dict[str, Any]:
    return {
        "pixel": {name: {"tp": 0, "fp": 0, "fn": 0} for name in ("weed", "crop")},
        "instance": {
            name: {"tp": 0, "fp": 0, "fn": 0} for name in ("weed", "crop")
        },
        "eligible_weed_track": {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "ignored_ineligible_predictions": 0,
        },
        "size_strata": {
            name: {"eligible_gt_tracks": 0, "matched_tracks": 0}
            for name in ("small", "medium", "large")
        },
    }


def add_counts(target: dict[str, int], *, tp: int, fp: int, fn: int) -> None:
    target["tp"] += int(tp)
    target["fp"] += int(fp)
    target["fn"] += int(fn)


def is_eligible_weed(label: TrackLabel, ground_truth: Mapping[str, Any]) -> bool:
    return bool(
        label.class_name == "weed"
        and label.canopy_span_mm
        >= float(ground_truth["eligible_weed_minimum_canopy_span_mm"])
        and label.visible_fraction
        >= float(ground_truth["eligible_weed_minimum_visible_fraction"])
        and (
            not bool(ground_truth["require_non_partial_observation"])
            or not label.partial
        )
    )


def track_truth_catalog(
    sequence: PredictionSequence,
) -> tuple[dict[str, dict[int, BinaryMask]], dict[str, TrackLabel]]:
    masks: dict[str, dict[int, BinaryMask]] = defaultdict(dict)
    catalog: dict[str, TrackLabel] = {}
    for frame in sequence.frames:
        for label in frame.truth.labels:
            masks[label.track_id][frame.frame_index] = frame.truth.masks_by_id[label.mask_id]
            prior = catalog.get(label.track_id)
            if prior is None or label.visible_fraction > prior.visible_fraction:
                catalog[label.track_id] = label
    return dict(masks), catalog


def spatiotemporal_iou(
    predicted: Mapping[int, BinaryMask],
    truth: Mapping[int, BinaryMask],
) -> float:
    intersection = 0
    union = 0
    for frame_index in sorted(set(predicted) | set(truth)):
        if frame_index in predicted and frame_index in truth:
            overlap = predicted[frame_index].intersection_area(truth[frame_index])
            intersection += overlap
            union += predicted[frame_index].area + truth[frame_index].area - overlap
        elif frame_index in predicted:
            union += predicted[frame_index].area
        else:
            union += truth[frame_index].area
    return intersection / union if union else 0.0


def stored_assignments(sequence: PredictionSequence) -> dict[tuple[int, int], str]:
    return {
        (frame.frame_index, detection.detection_id): detection.stored_track_id
        for frame in sequence.frames
        for detection in frame.detections
    }


def assign_tracks(
    sequence: PredictionSequence,
    *,
    minimum_iou: float,
    maximum_distance: float,
    maximum_gap: int,
) -> dict[tuple[int, int], str]:
    active: dict[int, tuple[str, int, BinaryMask, tuple[float, float]]] = {}
    assignments: dict[tuple[int, int], str] = {}
    next_track = 1
    for frame in sorted(sequence.frames, key=lambda item: item.frame_index):
        active = {
            track_number: state
            for track_number, state in active.items()
            if frame.frame_index - state[1] <= maximum_gap
        }
        candidates: list[tuple[float, float, int, int]] = []
        for detection_index, detection in enumerate(frame.detections):
            for track_number, (class_name, last_frame, mask, centroid) in active.items():
                if class_name != detection.class_name or last_frame == frame.frame_index:
                    continue
                overlap = mask.iou(detection.mask)
                distance = math.hypot(
                    centroid[0] - detection.centroid_xy[0],
                    centroid[1] - detection.centroid_xy[1],
                )
                if overlap >= minimum_iou or distance <= maximum_distance:
                    candidates.append((-overlap, distance, detection_index, track_number))
        candidates.sort()
        used_detections: set[int] = set()
        used_tracks: set[int] = set()
        for _, _, detection_index, track_number in candidates:
            if detection_index in used_detections or track_number in used_tracks:
                continue
            detection = frame.detections[detection_index]
            track_id = f"p{track_number:04d}"
            assignments[(frame.frame_index, detection.detection_id)] = track_id
            active[track_number] = (
                detection.class_name,
                frame.frame_index,
                detection.mask,
                detection.centroid_xy,
            )
            used_detections.add(detection_index)
            used_tracks.add(track_number)
        for detection_index, detection in enumerate(frame.detections):
            if detection_index in used_detections:
                continue
            track_number = next_track
            next_track += 1
            track_id = f"p{track_number:04d}"
            assignments[(frame.frame_index, detection.detection_id)] = track_id
            active[track_number] = (
                detection.class_name,
                frame.frame_index,
                detection.mask,
                detection.centroid_xy,
            )
    return assignments


def evaluate_tracks(
    sequence: PredictionSequence,
    threshold: float,
    inference_config: Mapping[str, Any],
    assignments: Mapping[tuple[int, int], str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    tracking = require_mapping(inference_config["tracking"], "tracking")
    ground_truth = require_mapping(inference_config["ground_truth"], "ground_truth")
    all_predicted: dict[str, dict[int, BinaryMask]] = defaultdict(dict)
    for frame in sequence.frames:
        for detection in frame.detections:
            if detection.class_name != "weed" or detection.confidence < threshold:
                continue
            track_id = assignments[(frame.frame_index, detection.detection_id)]
            all_predicted[track_id][frame.frame_index] = detection.mask
    minimum_observations = int(tracking["minimum_track_observations"])
    qualifying = {
        track_id: masks
        for track_id, masks in all_predicted.items()
        if len(masks) >= minimum_observations
    }
    short = {
        track_id: masks
        for track_id, masks in all_predicted.items()
        if len(masks) < minimum_observations
    }
    truth_masks, catalog = track_truth_catalog(sequence)
    eligible_ids = sorted(
        track_id
        for track_id, label in catalog.items()
        if is_eligible_weed(label, ground_truth)
    )
    ineligible_ids = sorted(
        track_id
        for track_id, label in catalog.items()
        if label.class_name == "weed" and track_id not in eligible_ids
    )
    match_iou = float(tracking["eligible_track_match_iou"])
    eligible_scores = {
        predicted_id: {
            truth_id: spatiotemporal_iou(masks, truth_masks[truth_id])
            for truth_id in eligible_ids
        }
        for predicted_id, masks in qualifying.items()
    }
    candidates = sorted(
        (
            -score,
            predicted_id,
            truth_id,
        )
        for predicted_id, scores in eligible_scores.items()
        for truth_id, score in scores.items()
    )
    matched_predictions: set[str] = set()
    matched_truth: set[str] = set()
    matches: list[dict[str, Any]] = []
    for negative_iou, predicted_id, truth_id in candidates:
        score = -negative_iou
        if score < match_iou:
            break
        if predicted_id in matched_predictions or truth_id in matched_truth:
            continue
        matched_predictions.add(predicted_id)
        matched_truth.add(truth_id)
        matches.append(
            {
                "predicted_track_id": predicted_id,
                "gt_track_id": truth_id,
                "spatiotemporal_iou": score,
            }
        )
    ignored: set[str] = set()
    for predicted_id, masks in qualifying.items():
        if predicted_id in matched_predictions:
            continue
        if any(
            spatiotemporal_iou(masks, truth_masks[truth_id]) >= match_iou
            for truth_id in ineligible_ids
        ):
            ignored.add(predicted_id)
    counts = {
        "tp": len(matched_truth),
        "fp": len(qualifying) - len(matched_predictions) - len(ignored),
        "fn": len(eligible_ids) - len(matched_truth),
        "ignored_ineligible_predictions": len(ignored),
    }
    diagnostics = {
        "eligible_gt_track_ids": eligible_ids,
        "ineligible_gt_track_ids": ineligible_ids,
        "above_threshold_detection_count": sum(len(value) for value in all_predicted.values()),
        "above_threshold_predicted_track_count": len(all_predicted),
        "qualifying_predicted_track_count": len(qualifying),
        "short_predicted_track_count": len(short),
        "short_track_observation_counts": sorted(len(value) for value in short.values()),
        "qualifying_track_observation_counts": sorted(len(value) for value in qualifying.values()),
        "matches": matches,
        "ignored_predicted_track_ids": sorted(ignored),
        "minimum_track_observations": minimum_observations,
        "eligible_track_match_iou": match_iou,
    }
    return counts, diagnostics


def evaluate_sequence(
    sequence: PredictionSequence,
    threshold: float,
    inference_config: Mapping[str, Any],
    semantic_ids: Mapping[str, int],
    *,
    assignments: Mapping[tuple[int, int], str] | None = None,
) -> dict[str, Any]:
    counts = empty_evaluation_counts()
    instance_iou = float(inference_config["ground_truth"]["instance_match_iou"])
    crop_threshold = float(
        inference_config["temporal_action"]["predicted_crop_veto_confidence"]
    )
    for frame in sequence.frames:
        semantic = cv2.imread(str(frame.truth.semantic_path), cv2.IMREAD_UNCHANGED)
        if semantic is None:
            raise ContractError(f"GT disappeared during recomputation: {frame.truth.semantic_path}")
        for class_name in ("weed", "crop"):
            confidence_threshold = threshold if class_name == "weed" else crop_threshold
            detections = [
                item
                for item in frame.detections
                if item.class_name == class_name and item.confidence >= confidence_threshold
            ]
            union = mask_union([item.mask for item in detections], frame.truth.shape)
            truth_pixels = int(
                frame.truth.semantic_counts.get(int(semantic_ids[class_name]), 0)
            )
            tp = union.semantic_overlap(semantic, int(semantic_ids[class_name]))
            add_counts(
                counts["pixel"][class_name],
                tp=tp,
                fp=union.area - tp,
                fn=truth_pixels - tp,
            )
            truth_masks = [
                frame.truth.masks_by_id[label.mask_id]
                for label in frame.truth.labels
                if label.class_name == class_name
            ]
            matches = greedy_mask_matches(
                [item.mask for item in detections], truth_masks, instance_iou
            )
            add_counts(
                counts["instance"][class_name],
                tp=len(matches),
                fp=len(detections) - len(matches),
                fn=len(truth_masks) - len(matches),
            )
    assignments = assignments or stored_assignments(sequence)
    track_counts, track_diagnostics = evaluate_tracks(
        sequence, threshold, inference_config, assignments
    )
    counts["eligible_weed_track"].update(track_counts)
    _, catalog = track_truth_catalog(sequence)
    matched_truth = {
        row["gt_track_id"] for row in track_diagnostics["matches"]
    }
    for track_id in track_diagnostics["eligible_gt_track_ids"]:
        stratum = catalog[track_id].size_stratum
        counts["size_strata"][stratum]["eligible_gt_tracks"] += 1
        if track_id in matched_truth:
            counts["size_strata"][stratum]["matched_tracks"] += 1
    return {
        "sequence_id": sequence.sequence_id,
        "pair_id": sequence.pair_id,
        "split": sequence.split,
        "condition": sequence.condition,
        "threshold": threshold,
        "counts": counts,
        "metrics": {
            "pixel": {
                name: prf_metrics(counts["pixel"][name]) for name in ("weed", "crop")
            },
            "instance": {
                name: prf_metrics(counts["instance"][name])
                for name in ("weed", "crop")
            },
            "eligible_weed_track": prf_metrics(counts["eligible_weed_track"]),
        },
        "track_diagnostics": track_diagnostics,
    }


def flatten_sweep_row(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    metrics = evaluation["metrics"]
    counts = evaluation["counts"]
    track = metrics["eligible_weed_track"]
    diagnostics = evaluation["track_diagnostics"]
    return {
        "sequence_id": evaluation["sequence_id"],
        "pair_id": evaluation["pair_id"],
        "split": evaluation["split"],
        "condition": evaluation["condition"],
        "threshold": evaluation["threshold"],
        "weed_detection_count": diagnostics["above_threshold_detection_count"],
        "weed_predicted_track_count": diagnostics["above_threshold_predicted_track_count"],
        "weed_qualifying_track_count": diagnostics["qualifying_predicted_track_count"],
        "eligible_gt_track_count": track["recall_denominator"],
        "track_tp": track["tp"],
        "track_fp": track["fp"],
        "track_fn": track["fn"],
        "track_precision": track["precision"],
        "track_recall": track["recall"],
        "track_f1": track["f1"],
        "track_f1_state": track["f1_state"],
        "weed_pixel_tp": counts["pixel"]["weed"]["tp"],
        "weed_pixel_fp": counts["pixel"]["weed"]["fp"],
        "weed_pixel_fn": counts["pixel"]["weed"]["fn"],
        "weed_pixel_precision": metrics["pixel"]["weed"]["precision"],
        "weed_pixel_recall": metrics["pixel"]["weed"]["recall"],
        "weed_pixel_f1": metrics["pixel"]["weed"]["f1"],
        "crop_pixel_precision": metrics["pixel"]["crop"]["precision"],
        "crop_pixel_recall": metrics["pixel"]["crop"]["recall"],
        "crop_pixel_f1": metrics["pixel"]["crop"]["f1"],
        "weed_instance_precision": metrics["instance"]["weed"]["precision"],
        "weed_instance_recall": metrics["instance"]["weed"]["recall"],
        "weed_instance_f1": metrics["instance"]["weed"]["f1"],
        "crop_instance_f1": metrics["instance"]["crop"]["f1"],
    }


def threshold_sweep(
    sequences: Sequence[PredictionSequence],
    thresholds: Sequence[float],
    inference_config: Mapping[str, Any],
    semantic_ids: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[tuple[str, float], dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    evaluations: dict[tuple[str, float], dict[str, Any]] = {}
    for sequence in sorted(sequences, key=lambda item: (item.split, item.condition)):
        for threshold in thresholds:
            value = round(float(threshold), 8)
            evaluation = evaluate_sequence(
                sequence, value, inference_config, semantic_ids
            )
            evaluations[(sequence.sequence_id, value)] = evaluation
            rows.append(flatten_sweep_row(evaluation))
    return rows, evaluations


def compare_locked_recomputation(
    sequences: Sequence[PredictionSequence],
    evaluations: Mapping[tuple[str, float], Mapping[str, Any]],
    metrics: Mapping[str, Any],
    locked_threshold: float,
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    all_exact = True
    for sequence in sequences:
        if sequence.split != "test":
            continue
        recomputed = evaluations[(sequence.sequence_id, locked_threshold)]["counts"]
        frozen = metrics["locked_test"]["conditions"][sequence.condition]["counts"]
        fields: dict[str, Any] = {}
        for family in ("pixel", "instance"):
            for class_name in ("weed", "crop"):
                for key in ("tp", "fp", "fn"):
                    name = f"{family}.{class_name}.{key}"
                    actual = int(recomputed[family][class_name][key])
                    expected = int(frozen[family][class_name][key])
                    fields[name] = {"recomputed": actual, "frozen": expected, "exact": actual == expected}
                    all_exact &= actual == expected
        for key in ("tp", "fp", "fn", "ignored_ineligible_predictions"):
            name = f"eligible_weed_track.{key}"
            actual = int(recomputed["eligible_weed_track"][key])
            expected = int(frozen["eligible_weed_track"][key])
            fields[name] = {"recomputed": actual, "frozen": expected, "exact": actual == expected}
            all_exact &= actual == expected
        comparisons[sequence.condition] = {
            "sequence_id": sequence.sequence_id,
            "threshold": locked_threshold,
            "fields": fields,
            "all_recomputed_fields_exact": all(item["exact"] for item in fields.values()),
        }
    if not all_exact:
        raise ContractError("Independent locked recomputation disagrees with frozen metrics")
    return {
        "all_recomputed_fields_exact": True,
        "conditions": comparisons,
        "action_metrics_not_recomputed": True,
        "reason_action_excluded": "audit scope isolates masks, classes, thresholds, and tracking",
    }


def class_confusion_diagnostics(
    sequences: Sequence[PredictionSequence],
    confidence_floor: float,
    locked_threshold: float,
    semantic_ids: Mapping[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output: dict[str, Any] = {}
    instance_rows: list[dict[str, Any]] = []
    for sequence in sorted(sequences, key=lambda item: (item.split, item.condition)):
        counts = {
            class_name: {
                "gt_pixels": 0,
                "raw_same_class_overlap_pixels": 0,
                "raw_other_class_overlap_pixels": 0,
                "raw_both_class_overlap_pixels": 0,
                "locked_weed_overlap_pixels": 0,
            }
            for class_name in ("weed", "crop")
        }
        raw_detection_counts = {"weed": 0, "crop": 0}
        locked_weed_detection_count = 0
        for frame in sequence.frames:
            semantic = cv2.imread(str(frame.truth.semantic_path), cv2.IMREAD_UNCHANGED)
            if semantic is None:
                raise ContractError(f"Failed to decode semantic GT {frame.truth.semantic_path}")
            raw_by_class = {
                class_name: [
                    item
                    for item in frame.detections
                    if item.class_name == class_name and item.confidence >= confidence_floor
                ]
                for class_name in ("weed", "crop")
            }
            for class_name in raw_detection_counts:
                raw_detection_counts[class_name] += len(raw_by_class[class_name])
            locked_weed = [
                item
                for item in frame.detections
                if item.class_name == "weed" and item.confidence >= locked_threshold
            ]
            locked_weed_detection_count += len(locked_weed)
            unions = {
                class_name: mask_union(
                    [item.mask for item in raw_by_class[class_name]], frame.truth.shape
                )
                for class_name in ("weed", "crop")
            }
            locked_union = mask_union(
                [item.mask for item in locked_weed], frame.truth.shape
            )
            for class_name, other_name in (("weed", "crop"), ("crop", "weed")):
                semantic_id = int(semantic_ids[class_name])
                gt_pixels = int(frame.truth.semantic_counts.get(semantic_id, 0))
                counts[class_name]["gt_pixels"] += gt_pixels
                counts[class_name]["raw_same_class_overlap_pixels"] += unions[
                    class_name
                ].semantic_overlap(semantic, semantic_id)
                counts[class_name]["raw_other_class_overlap_pixels"] += unions[
                    other_name
                ].semantic_overlap(semantic, semantic_id)
                same = unions[class_name]
                other = unions[other_name]
                if same.area and other.area:
                    intersection = same.intersection_area(other)
                    if intersection:
                        ax0, ay0, ax1, ay1 = same.bbox_xyxy
                        bx0, by0, bx1, by1 = other.bbox_xyxy
                        x0, y0 = max(ax0, bx0), max(ay0, by0)
                        x1, y1 = min(ax1, bx1), min(ay1, by1)
                        left = same.crop[y0 - ay0 : y1 - ay0, x0 - ax0 : x1 - ax0]
                        right = other.crop[y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0]
                        counts[class_name]["raw_both_class_overlap_pixels"] += int(
                            np.logical_and(
                                np.logical_and(left, right),
                                semantic[y0:y1, x0:x1] == semantic_id,
                            ).sum()
                        )
                if class_name == "weed":
                    counts[class_name]["locked_weed_overlap_pixels"] += (
                        locked_union.semantic_overlap(semantic, semantic_id)
                    )
            for label in frame.truth.labels:
                truth_mask = frame.truth.masks_by_id[label.mask_id]
                same = raw_by_class[label.class_name]
                other_class = "crop" if label.class_name == "weed" else "weed"
                other = raw_by_class[other_class]
                same_score = max((item.mask.iou(truth_mask) for item in same), default=0.0)
                other_score = max((item.mask.iou(truth_mask) for item in other), default=0.0)
                instance_rows.append(
                    {
                        "sequence_id": sequence.sequence_id,
                        "split": sequence.split,
                        "condition": sequence.condition,
                        "frame_index": frame.frame_index,
                        "gt_track_id": label.track_id,
                        "gt_class": label.class_name,
                        "best_same_class_raw_iou": same_score,
                        "best_other_class_raw_iou": other_score,
                        "other_class_better": other_score > same_score,
                        "no_raw_overlap": max(same_score, other_score) == 0.0,
                    }
                )
        summaries: dict[str, Any] = {}
        for class_name, values in counts.items():
            denominator = values["gt_pixels"]
            summaries[class_name] = {
                **values,
                "raw_same_class_gt_pixel_coverage": safe_rate(
                    values["raw_same_class_overlap_pixels"], denominator
                ),
                "raw_other_class_gt_pixel_coverage": safe_rate(
                    values["raw_other_class_overlap_pixels"], denominator
                ),
                "raw_both_class_gt_pixel_coverage": safe_rate(
                    values["raw_both_class_overlap_pixels"], denominator
                ),
                "locked_weed_gt_pixel_coverage": (
                    safe_rate(values["locked_weed_overlap_pixels"], denominator)
                    if class_name == "weed"
                    else None
                ),
            }
        relevant_instances = [
            row for row in instance_rows if row["sequence_id"] == sequence.sequence_id
        ]
        output[sequence.sequence_id] = {
            "split": sequence.split,
            "condition": sequence.condition,
            "confidence_floor": confidence_floor,
            "locked_weed_threshold": locked_threshold,
            "raw_detection_counts": raw_detection_counts,
            "locked_weed_detection_count": locked_weed_detection_count,
            "pixel_overlap": summaries,
            "instance_overlap_summary": {
                class_name: {
                    "gt_observation_count": len(
                        [row for row in relevant_instances if row["gt_class"] == class_name]
                    ),
                    "other_class_better_count": len(
                        [
                            row
                            for row in relevant_instances
                            if row["gt_class"] == class_name and row["other_class_better"]
                        ]
                    ),
                    "same_class_iou_at_least_0p10_count": len(
                        [
                            row
                            for row in relevant_instances
                            if row["gt_class"] == class_name
                            and row["best_same_class_raw_iou"] >= 0.10
                        ]
                    ),
                    "same_class_iou_at_least_0p50_count": len(
                        [
                            row
                            for row in relevant_instances
                            if row["gt_class"] == class_name
                            and row["best_same_class_raw_iou"] >= 0.50
                        ]
                    ),
                }
                for class_name in ("weed", "crop")
            },
        }
    return output, instance_rows


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), quantile))


def motion_diagnostics(
    sequences: Sequence[PredictionSequence],
    locked_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    # GT is byte-identical between arms, so use ideal once per matched pair.
    for sequence in sequences:
        if sequence.condition != "ideal":
            continue
        truth_masks, catalog = track_truth_catalog(sequence)
        for track_id, observations in sorted(truth_masks.items()):
            ordered = sorted(observations.items())
            for (left_frame, left), (right_frame, right) in zip(ordered, ordered[1:]):
                gap = right_frame - left_frame
                left_centroid = left.centroid_xy
                right_centroid = right.centroid_xy
                distance = math.hypot(
                    left_centroid[0] - right_centroid[0],
                    left_centroid[1] - right_centroid[1],
                )
                overlap = left.iou(right)
                passes = bool(
                    gap <= int(locked_policy["maximum_frame_gap"])
                    and (
                        overlap >= float(locked_policy["association_min_mask_iou"])
                        or distance
                        <= float(locked_policy["association_max_centroid_distance_px"])
                    )
                )
                rows.append(
                    {
                        "sequence_id": sequence.sequence_id,
                        "pair_id": sequence.pair_id,
                        "split": sequence.split,
                        "class_name": catalog[track_id].class_name,
                        "gt_track_id": track_id,
                        "left_frame": left_frame,
                        "right_frame": right_frame,
                        "frame_gap": gap,
                        "centroid_distance_px": distance,
                        "mask_iou": overlap,
                        "passes_frozen_association_geometry": passes,
                    }
                )
    summary: dict[str, Any] = {}
    for split in sorted({row["split"] for row in rows}):
        summary[split] = {}
        for class_name in ("weed", "crop"):
            selected = [
                row
                for row in rows
                if row["split"] == split and row["class_name"] == class_name
            ]
            distances = [float(row["centroid_distance_px"]) for row in selected]
            overlaps = [float(row["mask_iou"]) for row in selected]
            failures = [
                row for row in selected if not row["passes_frozen_association_geometry"]
            ]
            summary[split][class_name] = {
                "transition_count": len(selected),
                "centroid_distance_px": {
                    "median": percentile(distances, 50),
                    "p95": percentile(distances, 95),
                    "maximum": max(distances) if distances else None,
                },
                "mask_iou": {
                    "median": percentile(overlaps, 50),
                    "p05": percentile(overlaps, 5),
                    "minimum": min(overlaps) if overlaps else None,
                },
                "frozen_geometry_gate_failure_count": len(failures),
                "frozen_geometry_gate_failure_fraction": safe_rate(
                    len(failures), len(selected)
                ),
                "interpretation": (
                    "apparent GT inter-frame motion; static plants make camera translation "
                    "the dominant source, but this is not a calibrated camera-motion estimate"
                ),
            }
    return summary, rows


def track_length_stats(
    sequence: PredictionSequence,
    assignments: Mapping[tuple[int, int], str],
    *,
    class_name: str,
    confidence: float,
) -> dict[str, Any]:
    tracks: dict[str, list[int]] = defaultdict(list)
    for frame in sequence.frames:
        for detection in frame.detections:
            if detection.class_name == class_name and detection.confidence >= confidence:
                track_id = assignments[(frame.frame_index, detection.detection_id)]
                tracks[track_id].append(frame.frame_index)
    lengths = sorted(len(values) for values in tracks.values())
    return {
        "detection_count": sum(lengths),
        "track_count": len(lengths),
        "singleton_track_count": sum(value == 1 for value in lengths),
        "qualifying_three_observation_track_count": sum(value >= 3 for value in lengths),
        "median_observations": statistics.median(lengths) if lengths else None,
        "maximum_observations": max(lengths) if lengths else None,
    }


def association_sweep(
    sequences: Sequence[PredictionSequence],
    diagnostics: Mapping[str, Any],
    inference_config: Mapping[str, Any],
    locked_threshold: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    minimum_ious = [float(value) for value in diagnostics["association_min_mask_iou_values"]]
    maximum_distances = [
        float(value) for value in diagnostics["association_max_centroid_distance_px_values"]
    ]
    maximum_gaps = [int(value) for value in diagnostics["maximum_frame_gap_values"]]
    confidence_floor = float(inference_config["inference"]["confidence_floor"])
    frozen = inference_config["tracking"]
    validation: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for sequence in sorted(sequences, key=lambda item: (item.split, item.condition)):
        recomputed_frozen = assign_tracks(
            sequence,
            minimum_iou=float(frozen["association_min_mask_iou"]),
            maximum_distance=float(frozen["association_max_centroid_distance_px"]),
            maximum_gap=int(frozen["maximum_frame_gap"]),
        )
        declared = stored_assignments(sequence)
        mismatches = [
            {"key": list(key), "stored": declared[key], "recomputed": recomputed_frozen[key]}
            for key in sorted(declared)
            if recomputed_frozen.get(key) != declared[key]
        ]
        if mismatches:
            raise ContractError(f"Stored tracker IDs do not reproduce for {sequence.sequence_id}")
        validation[sequence.sequence_id] = {
            "detection_assignment_count": len(declared),
            "exact_assignment_match": True,
            "frozen_parameters": {
                "association_min_mask_iou": float(frozen["association_min_mask_iou"]),
                "association_max_centroid_distance_px": float(
                    frozen["association_max_centroid_distance_px"]
                ),
                "maximum_frame_gap": int(frozen["maximum_frame_gap"]),
            },
        }
        for minimum_iou in minimum_ious:
            for maximum_distance in maximum_distances:
                for maximum_gap in maximum_gaps:
                    assignments = assign_tracks(
                        sequence,
                        minimum_iou=minimum_iou,
                        maximum_distance=maximum_distance,
                        maximum_gap=maximum_gap,
                    )
                    track_counts, track_diagnostics = evaluate_tracks(
                        sequence, locked_threshold, inference_config, assignments
                    )
                    track_metrics = prf_metrics(track_counts)
                    raw_stats = track_length_stats(
                        sequence,
                        assignments,
                        class_name="weed",
                        confidence=confidence_floor,
                    )
                    locked_stats = track_length_stats(
                        sequence,
                        assignments,
                        class_name="weed",
                        confidence=locked_threshold,
                    )
                    rows.append(
                        {
                            "sequence_id": sequence.sequence_id,
                            "pair_id": sequence.pair_id,
                            "split": sequence.split,
                            "condition": sequence.condition,
                            "association_min_mask_iou": minimum_iou,
                            "association_max_centroid_distance_px": maximum_distance,
                            "maximum_frame_gap": maximum_gap,
                            "is_frozen_setting": bool(
                                math.isclose(
                                    minimum_iou,
                                    float(frozen["association_min_mask_iou"]),
                                )
                                and math.isclose(
                                    maximum_distance,
                                    float(frozen["association_max_centroid_distance_px"]),
                                )
                                and maximum_gap == int(frozen["maximum_frame_gap"])
                            ),
                            "raw_weed_detection_count": raw_stats["detection_count"],
                            "raw_weed_track_count": raw_stats["track_count"],
                            "raw_weed_singleton_track_count": raw_stats[
                                "singleton_track_count"
                            ],
                            "raw_weed_maximum_observations": raw_stats[
                                "maximum_observations"
                            ],
                            "locked_weed_detection_count": locked_stats["detection_count"],
                            "locked_weed_track_count": locked_stats["track_count"],
                            "locked_weed_singleton_track_count": locked_stats[
                                "singleton_track_count"
                            ],
                            "locked_weed_qualifying_track_count": track_diagnostics[
                                "qualifying_predicted_track_count"
                            ],
                            "track_tp": track_metrics["tp"],
                            "track_fp": track_metrics["fp"],
                            "track_fn": track_metrics["fn"],
                            "track_precision": track_metrics["precision"],
                            "track_recall": track_metrics["recall"],
                            "track_f1": track_metrics["f1"],
                            "track_f1_state": track_metrics["f1_state"],
                        }
                    )
    return rows, validation


def summarize_association_sweep(
    rows: Sequence[Mapping[str, Any]],
    inference_config: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = inference_config["tracking"]
    summary: dict[str, Any] = {}
    for condition in ("ideal", "degraded"):
        selected = [
            row
            for row in rows
            if row["split"] == "test" and row["condition"] == condition
        ]
        if not selected:
            raise ContractError(f"Association sweep lacks test rows for {condition}")
        frozen_rows = [row for row in selected if row["is_frozen_setting"]]
        if len(frozen_rows) != 1:
            raise ContractError(f"Association sweep lacks one frozen row for {condition}")
        frozen_row = frozen_rows[0]
        qualifying = [
            row
            for row in selected
            if int(row["locked_weed_qualifying_track_count"]) > 0
        ]
        qualifying.sort(
            key=lambda row: (
                float(row["association_max_centroid_distance_px"]),
                float(row["association_min_mask_iou"]),
                int(row["maximum_frame_gap"]),
            )
        )
        defined = [row for row in selected if row["track_f1"] is not None]
        true_positive = [row for row in selected if int(row["track_tp"]) > 0]
        if not qualifying:
            diagnostic_result = (
                "no_swept_geometry_setting_forms_a_three_observation_locked_weed_track"
            )
        elif not true_positive:
            diagnostic_result = (
                "geometry_relaxation_forms_qualifying_tracks_but_none_match_eligible_gt"
            )
        else:
            diagnostic_result = (
                "some_post_hoc_geometry_settings_form_tracks_matching_eligible_gt"
            )
        examples = [
            {
                "association_min_mask_iou": float(row["association_min_mask_iou"]),
                "association_max_centroid_distance_px": float(
                    row["association_max_centroid_distance_px"]
                ),
                "maximum_frame_gap": int(row["maximum_frame_gap"]),
                "locked_weed_qualifying_track_count": int(
                    row["locked_weed_qualifying_track_count"]
                ),
                "track_tp": int(row["track_tp"]),
                "track_fp": int(row["track_fp"]),
                "track_fn": int(row["track_fn"]),
                "track_f1": row["track_f1"],
                "track_f1_state": row["track_f1_state"],
            }
            for row in qualifying[:12]
        ]
        summary[condition] = {
            "grid_setting_count": len(selected),
            "distance_range_px": [
                min(float(row["association_max_centroid_distance_px"]) for row in selected),
                max(float(row["association_max_centroid_distance_px"]) for row in selected),
            ],
            "frozen_setting": {
                "association_min_mask_iou": float(frozen["association_min_mask_iou"]),
                "association_max_centroid_distance_px": float(
                    frozen["association_max_centroid_distance_px"]
                ),
                "maximum_frame_gap": int(frozen["maximum_frame_gap"]),
                "locked_weed_detection_count": int(
                    frozen_row["locked_weed_detection_count"]
                ),
                "locked_weed_track_count": int(frozen_row["locked_weed_track_count"]),
                "locked_weed_singleton_track_count": int(
                    frozen_row["locked_weed_singleton_track_count"]
                ),
                "locked_weed_qualifying_track_count": int(
                    frozen_row["locked_weed_qualifying_track_count"]
                ),
                "track_f1": frozen_row["track_f1"],
                "track_f1_state": frozen_row["track_f1_state"],
            },
            "maximum_raw_weed_track_observations_any_setting": max(
                int(row["raw_weed_maximum_observations"]) for row in selected
            ),
            "maximum_locked_qualifying_track_count_any_setting": max(
                int(row["locked_weed_qualifying_track_count"]) for row in selected
            ),
            "settings_with_locked_qualifying_tracks": len(qualifying),
            "settings_with_defined_track_f1": len(defined),
            "settings_with_track_true_positive": len(true_positive),
            "qualifying_setting_examples": examples,
            "diagnostic_result": diagnostic_result,
            "selection_status": "post_hoc_failure_decomposition_only_not_a_recommendation",
        }
    return summary


def blend_mask(
    image: np.ndarray,
    mask: BinaryMask,
    colour_rgb: tuple[int, int, int],
    alpha: float,
) -> None:
    if mask.area == 0:
        return
    x0, y0, x1, y1 = mask.bbox_xyxy
    region = image[y0:y1, x0:x1]
    pixels = mask.crop
    colour = np.asarray(colour_rgb, dtype=np.float32)
    region[pixels] = np.clip(
        region[pixels].astype(np.float32) * (1.0 - alpha) + colour * alpha,
        0,
        255,
    ).astype(np.uint8)


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def render_panel(
    frame: PredictionFrame,
    *,
    mode: str,
    panel_px: int,
    confidence_floor: float,
    locked_threshold: float,
    semantic_ids: Mapping[str, int],
) -> Image.Image:
    source = cv2.imread(str(frame.image_path), cv2.IMREAD_COLOR)
    if source is None:
        raise ContractError(f"Failed to decode contact-sheet RGB: {frame.image_path}")
    image = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
    semantic = cv2.imread(str(frame.truth.semantic_path), cv2.IMREAD_UNCHANGED)
    if semantic is None:
        raise ContractError(f"Failed to decode contact-sheet GT: {frame.truth.semantic_path}")
    if mode == "gt":
        for class_name, colour in (("crop", (30, 210, 80)), ("weed", (235, 45, 185))):
            blend_mask(
                image,
                BinaryMask.from_full(semantic == int(semantic_ids[class_name])),
                colour,
                0.45,
            )
        weed_count = sum(label.class_name == "weed" for label in frame.truth.labels)
        crop_count = sum(label.class_name == "crop" for label in frame.truth.labels)
        footer = f"GT instances  weed {weed_count} | crop {crop_count}"
    else:
        threshold = confidence_floor if mode == "raw" else locked_threshold
        selected = [
            detection
            for detection in frame.detections
            if detection.confidence >= threshold
        ]
        for detection in sorted(selected, key=lambda item: item.class_name):
            colour = (250, 75, 45) if detection.class_name == "weed" else (35, 155, 245)
            blend_mask(image, detection.mask, colour, 0.42)
        weed_outline = (semantic == int(semantic_ids["weed"])).astype(np.uint8)
        contours, _ = cv2.findContours(weed_outline, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image, contours, -1, (255, 235, 40), 5)
        weed_count = sum(item.class_name == "weed" for item in selected)
        crop_count = sum(item.class_name == "crop" for item in selected)
        footer = (
            f"pred @ {threshold:.2f}  weed {weed_count} | crop {crop_count}"
            "  (yellow=GT weed edge)"
        )
    panel = Image.fromarray(image).resize((panel_px, panel_px), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (panel_px, panel_px + 42), "white")
    canvas.paste(panel, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, panel_px + 11), footer, fill=(20, 24, 28), font=font(13))
    return canvas


def build_contact_sheet(
    sequences: Sequence[PredictionSequence],
    frame_indices: Sequence[int],
    panel_px: int,
    confidence_floor: float,
    locked_threshold: float,
    semantic_ids: Mapping[str, int],
    output_path: Path,
) -> dict[str, Any]:
    test = {
        sequence.condition: sequence for sequence in sequences if sequence.split == "test"
    }
    if set(test) != {"ideal", "degraded"}:
        raise ContractError("Contact sheet requires one ideal and one degraded test sequence")
    columns = [
        ("ideal", "gt", "IDEAL · GT"),
        ("ideal", "raw", "IDEAL · raw predictions"),
        ("ideal", "locked", "IDEAL · locked policy"),
        ("degraded", "gt", "DEGRADED · GT"),
        ("degraded", "raw", "DEGRADED · raw predictions"),
        ("degraded", "locked", "DEGRADED · locked policy"),
    ]
    margin = 16
    title_height = 126
    column_header_height = 42
    row_height = panel_px + 42
    width = margin * (len(columns) + 1) + panel_px * len(columns)
    height = title_height + column_header_height + margin + len(frame_indices) * (
        row_height + margin
    )
    sheet = Image.new("RGB", (width, height), (245, 247, 249))
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (margin, 14),
        "Native fixture fairness audit · failure decomposition",
        fill=(16, 24, 32),
        font=font(28, bold=True),
    )
    draw.text(
        (margin, 52),
        (
            f"Raw={confidence_floor:.2f}; locked weed={locked_threshold:.2f}. "
            "GT: crop green, weed magenta. Predictions: crop blue, weed orange."
        ),
        fill=(48, 58, 68),
        font=font(17),
    )
    draw.text(
        (margin, 80),
        "The sweep is descriptive post-hoc evidence; it is not a replacement threshold selection.",
        fill=(130, 42, 34),
        font=font(16, bold=True),
    )
    for column_index, (_, _, title) in enumerate(columns):
        x = margin + column_index * (panel_px + margin)
        draw.text((x + 4, title_height), title, fill=(24, 34, 44), font=font(16, bold=True))
    for row_index, frame_index in enumerate(frame_indices):
        y = title_height + column_header_height + margin + row_index * (
            row_height + margin
        )
        for column_index, (condition, mode, _) in enumerate(columns):
            sequence = test[condition]
            if frame_index < 0 or frame_index >= len(sequence.frames):
                raise ContractError(f"Contact-sheet frame {frame_index} is out of bounds")
            panel = render_panel(
                sequence.frames[frame_index],
                mode=mode,
                panel_px=panel_px,
                confidence_floor=confidence_floor,
                locked_threshold=locked_threshold,
                semantic_ids=semantic_ids,
            )
            x = margin + column_index * (panel_px + margin)
            sheet.paste(panel, (x, y))
        draw.text(
            (2, y + 6),
            f"{frame_index:02d}",
            fill=(10, 10, 10),
            font=font(11, bold=True),
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG", optimize=True)
    with Image.open(output_path) as decoded:
        decoded.verify()
    return {
        "path": output_path.name,
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "width": width,
        "height": height,
        "frame_indices": list(frame_indices),
        "column_count": len(columns),
        "readable_decode_verified": True,
    }


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ContractError(f"Refusing to write empty CSV: {path}")
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def artifact_inventory(root: Path, *, excluded: Iterable[str] = ()) -> list[dict[str, Any]]:
    excluded_set = set(excluded)
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded_set
    ]


def root_cause_summary(
    sequences: Sequence[PredictionSequence],
    sweep_rows: Sequence[Mapping[str, Any]],
    confusion: Mapping[str, Any],
    motion: Mapping[str, Any],
    association_summary: Mapping[str, Any],
    locked_threshold: float,
    confidence_floor: float,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for sequence in sequences:
        if sequence.split != "test":
            continue
        raw = next(
            row
            for row in sweep_rows
            if row["sequence_id"] == sequence.sequence_id
            and math.isclose(float(row["threshold"]), confidence_floor)
        )
        locked = next(
            row
            for row in sweep_rows
            if row["sequence_id"] == sequence.sequence_id
            and math.isclose(float(row["threshold"]), locked_threshold)
        )
        class_row = confusion[sequence.sequence_id]
        weed_overlap = class_row["pixel_overlap"]["weed"]
        summary[sequence.condition] = {
            "segmentation_localization": {
                "raw_weed_pixel_recall": raw["weed_pixel_recall"],
                "raw_weed_instance_recall": raw["weed_instance_recall"],
                "interpretation": (
                    "same-class raw mask overlap is measurable but far below complete GT coverage"
                ),
            },
            "classification": {
                "gt_weed_pixel_coverage_by_raw_weed": weed_overlap[
                    "raw_same_class_gt_pixel_coverage"
                ],
                "gt_weed_pixel_coverage_by_raw_crop": weed_overlap[
                    "raw_other_class_gt_pixel_coverage"
                ],
                "gt_weed_instances_where_crop_overlap_beats_weed_overlap": class_row[
                    "instance_overlap_summary"
                ]["weed"]["other_class_better_count"],
                "interpretation": (
                    "actual class IDs are correct; crop-over-weed overlap is therefore model "
                    "class confusion, not an index swap"
                ),
            },
            "thresholding": {
                "raw_weed_detection_count": raw["weed_detection_count"],
                "locked_weed_detection_count": locked["weed_detection_count"],
                "raw_qualifying_track_count": raw["weed_qualifying_track_count"],
                "locked_qualifying_track_count": locked[
                    "weed_qualifying_track_count"
                ],
                "locked_weed_pixel_recall": locked["weed_pixel_recall"],
                "interpretation": (
                    "the locked threshold removes low-confidence detections but is not the sole "
                    "cause because raw same-class recall and overlap are already weak"
                ),
            },
            "tracking": {
                "locked_predicted_track_count": locked["weed_predicted_track_count"],
                "locked_qualifying_track_count": locked[
                    "weed_qualifying_track_count"
                ],
                "eligible_gt_track_count": locked["eligible_gt_track_count"],
                "track_f1": locked["track_f1"],
                "track_f1_state": locked["track_f1_state"],
                "ideal_gt_motion_proxy": motion.get("test", {}).get("weed", {}),
                "association_counterfactual": association_summary[sequence.condition],
                "interpretation": (
                    "association fragmentation is real, but class/localization failures also "
                    "prevent eligible spatiotemporal matches"
                ),
            },
            "causal_boundary": (
                "These are decomposed observational diagnostics from one synthetic fixture pair; "
                "they do not identify a field-general causal effect or justify retuning test outcomes."
            ),
        }
    return summary


def build_readme(audit: Mapping[str, Any]) -> str:
    locked = audit["locked_recomputation"]
    lines = [
        "# Native fixture fairness audit v1",
        "",
        "**Status:** PASS — hash-bound post-hoc diagnostic recomputation.",
        "",
        "This package reads the frozen native fixture and persisted predictions only. It did not "
        "run inference, change the locked threshold, tune the tracker, or write into the active "
        "full-benchmark lane. The evidence is synthetic-only and authorizes no field, product, or "
        "chemical action.",
        "",
        "## What was independently verified",
        "",
        "- All configured anchor SHA-256 values matched, including the checkpoint, manifest, "
        "  threshold lock, four prediction JSONL files, metrics, and run receipt.",
        "- The deserialized checkpoint declares `0=weed, 1=crop`; each prediction NPZ agrees. "
        "  GT declares `0=background, 1=crop, 2=weed`, and every labelled track pixel agrees.",
        "- Every RGB, GT semantic mask, GT track mask, prediction NPZ, and raw detection mask "
        "  consumed by the audit passed its declared hash/content checks.",
        "- Frozen tracker IDs reproduced exactly from the persisted detections and frozen native "
        "  association parameters.",
        "- Independent weed/crop pixel, instance, and eligible-track counts exactly match the "
        "  stored locked-test metrics.",
        "",
        "## Why eligible-track F1 is null, not zero",
        "",
    ]
    for condition in ("ideal", "degraded"):
        comparison = locked["conditions"][condition]
        fields = comparison["fields"]
        tp = fields["eligible_weed_track.tp"]["recomputed"]
        fp = fields["eligible_weed_track.fp"]["recomputed"]
        fn = fields["eligible_weed_track.fn"]["recomputed"]
        lines.append(
            f"- **{condition.title()}:** `TP={tp}, FP={fp}, FN={fn}`. Precision has denominator "
            f"`TP+FP={tp + fp}`, so precision is undefined. Recall is numerically zero because "
            f"`TP+FN={tp + fn}` is non-zero. This metric contract defines F1 only when both "
            "precision and recall are defined, so F1 is `null`; coercing it to `0.0` would "
            "misreport the evaluator semantics."
        )
    lines.extend(
        [
            "",
            "A numeric zero F1 is a different case: it requires both denominators to exist, for "
            "example at least one qualifying predicted track (`TP+FP>0`) and at least one eligible "
            "GT track (`TP+FN>0`), with no true positives.",
            "",
            "## Valid interpretation",
            "",
            "The fixture demonstrates low weed-mask coverage, crop/weed class confusion, threshold "
            "attrition, and track fragmentation. It does **not** demonstrate a class-index swap: "
            "checkpoint, prediction arrays, and GT semantic IDs are mutually consistent. Because "
            "eligible-track F1 is undefined in both arms, neither the ideal `>=0.97` reference nor "
            "the degraded `[0.70, 0.80]` reference is reached or meaningfully estimated here. "
            "Non-zero pixel/instance scores remain valid narrow diagnostics, not whole-model accuracy.",
            "",
            "## Motion versus association limit",
            "",
        ]
    )
    association = audit["motion_vs_tracker"]["association_counterfactual_summary"]
    motion = audit["motion_vs_tracker"]["gt_apparent_motion_summary"]["test"]["weed"]
    lines.append(
        "Test-weed apparent inter-frame motion has median "
        f"`{motion['centroid_distance_px']['median']:.1f}px`, p95 "
        f"`{motion['centroid_distance_px']['p95']:.1f}px`, and "
        f"`{motion['frozen_geometry_gate_failure_fraction']:.1%}` of transitions fail the "
        "frozen geometry gate. The descriptive grid extends beyond that p95; it remains a "
        "counterfactual diagnostic, not a tracker recommendation."
    )
    lines.append("")
    for condition in ("ideal", "degraded"):
        item = association[condition]
        lines.append(
            f"- **{condition.title()}:** `{item['settings_with_locked_qualifying_tracks']}` of "
            f"`{item['grid_setting_count']}` swept settings form a qualifying locked weed track; "
            f"`{item['settings_with_track_true_positive']}` produce an eligible-track TP. "
            f"Result: `{item['diagnostic_result']}`."
        )
    lines.extend(
        [
            "",
            "See `diagnostic_contact_sheet.png` for five matched frames. `threshold_sweep.csv` and "
            "`association_sweep.csv` are explicitly post-hoc descriptive sweeps and must never be "
            "used to replace the locked test configuration.",
            "",
            "## Corrective full-benchmark acceptance rule",
            "",
            "A correction must be selected using fixture/calibration evidence only, assigned a new "
            "hash-bound release identity, and evaluated exactly once on a fresh untouched full locked "
            "test. The checkpoint/class/semantic mapping, full manifest, inference/tracker config, "
            "and degraded-calibration-only threshold lock must all verify before test access. Both "
            "arms must have non-empty eligible GT denominators and a defined primary F1; undefined "
            "F1 automatically fails target assessment. Only then may the frozen point estimates be "
            "compared with ideal `>=0.97` and degraded `[0.70, 0.80]`, without tuning to those values. "
            "Synthetic scores still authorize no field or chemical action.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_terminal_audit(audit: Mapping[str, Any]) -> dict[str, bool]:
    checks = {
        "status_pass": audit.get("status")
        == "PASS_HASH_BOUND_DIAGNOSTIC_SYNTHETIC_ONLY",
        "class_mapping_verified_no_shift": bool(
            audit["fixture_validation"][
                "all_checkpoint_gt_prediction_class_bindings_verified"
            ]
            and audit["class_contract"]["id_shift_detected"] is False
        ),
        "locked_counts_exact": audit["locked_recomputation"][
            "all_recomputed_fields_exact"
        ]
        is True,
        "primary_target_not_claimed": bool(
            audit["valid_interpretation"]["fixture_primary_target_assessment"]
            == "not_estimated_because_f1_undefined"
            and audit["valid_interpretation"]["ideal_reaches_0p97"] is False
            and audit["valid_interpretation"]["degraded_plausibly_near_0p75"]
            is False
        ),
        "acceptance_rule_fails_undefined_f1": audit[
            "corrective_full_benchmark_acceptance_rule"
        ]["undefined_f1_fails_target_gate"]
        is True,
        "fresh_locked_test_required_after_correction": audit[
            "corrective_full_benchmark_acceptance_rule"
        ]["require_fresh_untouched_full_locked_test_after_any_correction"]
        is True,
        "contact_sheet_readable": audit["diagnostic_contact_sheet"][
            "readable_decode_verified"
        ]
        is True,
        "active_full_lane_not_written": audit["write_scope"][
            "active_full_render_lane_written"
        ]
        is False,
    }
    for condition in ("ideal", "degraded"):
        metric = audit["eligible_track_f1_semantics"][condition]
        checks[f"{condition}_f1_undefined_not_zero"] = bool(
            metric["f1"] is None
            and metric["f1_state"]
            == "undefined_missing_precision_or_recall_denominator"
            and metric["precision_denominator"] == 0
            and metric["recall_denominator"] > 0
        )
    motion_p95 = float(
        audit["motion_vs_tracker"]["gt_apparent_motion_summary"]["test"]["weed"][
            "centroid_distance_px"
        ]["p95"]
    )
    for condition in ("ideal", "degraded"):
        counterfactual = audit["motion_vs_tracker"][
            "association_counterfactual_summary"
        ][condition]
        checks[f"{condition}_association_sweep_exceeds_motion_p95"] = bool(
            float(counterfactual["distance_range_px"][1]) > motion_p95
            and counterfactual["selection_status"]
            == "post_hoc_failure_decomposition_only_not_a_recommendation"
        )
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ContractError(f"Terminal audit validation failed: {failed}")
    return checks


def verify_internal_contracts(
    config: Mapping[str, Any],
    anchors: Mapping[str, Any],
    inference_config: Mapping[str, Any],
    threshold_lock: Mapping[str, Any],
    metrics: Mapping[str, Any],
    run_receipt: Mapping[str, Any],
) -> tuple[dict[int, str], dict[str, int], float]:
    class_contract = require_mapping(config["class_contract"], "class_contract")
    expected_names = {
        int(key): str(value)
        for key, value in require_mapping(
            class_contract["checkpoint_and_prediction_names"],
            "checkpoint_and_prediction_names",
        ).items()
    }
    semantic_ids = {
        str(key): int(value)
        for key, value in require_mapping(
            class_contract["ground_truth_semantic_ids"],
            "ground_truth_semantic_ids",
        ).items()
    }
    if expected_names != {0: "weed", 1: "crop"}:
        raise ContractError("Expected checkpoint class mapping must be 0=weed, 1=crop")
    if semantic_ids != {"background": 0, "crop": 1, "weed": 2}:
        raise ContractError("Expected GT semantic mapping must be background=0,crop=1,weed=2")
    inferred_names = normalize_class_names(inference_config["checkpoint"]["class_names"])
    inferred_semantic = {
        str(key): int(value)
        for key, value in inference_config["source"]["v12_smoke"]["semantic_ids"].items()
    }
    if inferred_names != expected_names or inferred_semantic != semantic_ids:
        raise ContractError("Frozen inference class contract disagrees with audit class contract")
    checkpoint_hash = anchors["checkpoint"]["sha256"]
    manifest_hash = anchors["sequence_manifest"]["sha256"]
    inference_hash = anchors["inference_config"]["sha256"]
    if threshold_lock.get("checkpoint_sha256") != checkpoint_hash:
        raise ContractError("Threshold lock checkpoint hash mismatch")
    if threshold_lock.get("inference_and_tracker_config_sha256") != inference_hash:
        raise ContractError("Threshold lock inference config hash mismatch")
    if metrics["checkpoint"]["sha256"] != checkpoint_hash:
        raise ContractError("Frozen metrics checkpoint hash mismatch")
    if metrics["sequence_manifest"]["sha256"] != manifest_hash:
        raise ContractError("Frozen metrics manifest hash mismatch")
    if metrics.get("threshold_lock_sha256") != anchors["threshold_lock"]["sha256"]:
        raise ContractError("Frozen metrics threshold-lock hash mismatch")
    if run_receipt.get("metrics_sha256") != anchors["metrics"]["sha256"]:
        raise ContractError("Run receipt metrics hash mismatch")
    if run_receipt.get("threshold_lock_sha256") != anchors["threshold_lock"]["sha256"]:
        raise ContractError("Run receipt threshold-lock hash mismatch")
    locked_threshold = float(
        threshold_lock["selected_threshold_and_feasibility"]["threshold"]
    )
    if not math.isclose(locked_threshold, float(metrics["locked_test"]["shared_threshold"])):
        raise ContractError("Threshold lock and frozen metrics disagree")
    locked_policy = require_mapping(config["locked_policy"], "locked_policy")
    if not math.isclose(locked_threshold, float(locked_policy["weed_confidence_threshold"])):
        raise ContractError("Audit locked threshold differs from threshold-lock artifact")
    tracker = inference_config["tracking"]
    policy_pairs = (
        ("association_min_mask_iou", "association_min_mask_iou"),
        ("association_max_centroid_distance_px", "association_max_centroid_distance_px"),
        ("maximum_frame_gap", "maximum_frame_gap"),
        ("eligible_track_match_iou", "eligible_track_match_iou"),
        ("minimum_track_observations", "minimum_track_observations"),
    )
    for policy_key, inference_key in policy_pairs:
        if not math.isclose(float(locked_policy[policy_key]), float(tracker[inference_key])):
            raise ContractError(f"Locked tracker policy mismatch for {policy_key}")
    crop_threshold = float(
        inference_config["temporal_action"]["predicted_crop_veto_confidence"]
    )
    if not math.isclose(crop_threshold, float(locked_policy["crop_confidence_threshold"])):
        raise ContractError("Locked crop threshold differs from inference config")
    return expected_names, semantic_ids, locked_threshold


def validate_output_scope(config: Mapping[str, Any]) -> tuple[Path, Path]:
    outputs = require_mapping(config["outputs"], "outputs")
    run_root = resolve_path(outputs["run_root"])
    docs_root = resolve_path(outputs["docs_root"])
    if run_root.name != "spot_spray_native_fixture_fairness_audit_v1":
        raise ContractError("Run output name is outside the allowed lane")
    if docs_root.name != "spot_spray_native_fixture_fairness_audit_v1":
        raise ContractError("Docs output name is outside the allowed lane")
    forbidden = [
        resolve_path(
            "data/runs/spot_spray_simulation_video_ab_execution_v1/full_benchmark_v1"
        ),
        resolve_path(
            "docs/results/spot_spray_simulation_video_ab_execution_v1/full_benchmark_v1"
        ),
    ]
    for output in (run_root, docs_root):
        if any(output == path or output.is_relative_to(path) for path in forbidden):
            raise ContractError("Audit output overlaps the active full-render lane")
    return run_root, docs_root


def prepare_staging(target: Path, *, replace: bool) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not replace:
            raise ContractError(f"Output already exists; pass --replace for this audit lane: {target}")
        if target.name != "spot_spray_native_fixture_fairness_audit_v1":
            raise ContractError(f"Refusing to replace unexpected output directory: {target}")
        shutil.rmtree(target)
    staging = target.parent / f".{target.name}.partial-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    return staging


def run_audit(config_path: Path, *, replace: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    run_root, docs_root = validate_output_scope(config)
    anchors, paths = verify_anchor_sources(config)
    inference_config = dict(
        require_mapping(
            yaml.safe_load(paths["inference_config"].read_text(encoding="utf-8")),
            "inference config",
        )
    )
    threshold_lock = load_json(paths["threshold_lock"], "threshold lock")
    metrics = load_json(paths["metrics"], "frozen metrics")
    run_receipt = load_json(paths["run_receipt"], "frozen run receipt")
    class_names, semantic_ids, locked_threshold = verify_internal_contracts(
        config,
        anchors,
        inference_config,
        threshold_lock,
        metrics,
        run_receipt,
    )
    checkpoint_mapping = verify_checkpoint_class_mapping(paths["checkpoint"], class_names)
    manifest, manifest_sequences, gt_validation = load_and_verify_manifest(
        paths["sequence_manifest"], paths["fixture_root"], semantic_ids
    )
    artifact_hashes = {
        str(item["path"]): str(item["sha256"])
        for item in require_sequence(run_receipt.get("artifacts"), "run_receipt.artifacts")
    }
    configured_predictions = require_mapping(
        config["sources"]["predictions"], "sources.predictions"
    )
    sequences: list[PredictionSequence] = []
    prediction_validation: dict[str, Any] = {}
    for name, raw_item in sorted(configured_predictions.items()):
        item = require_mapping(raw_item, f"prediction {name}")
        prediction_path = paths[f"prediction:{name}"]
        if artifact_hashes.get(prediction_path.name) != anchors["predictions"][name]["sha256"]:
            raise ContractError(f"Run receipt does not bind prediction JSONL {name}")
        sequence, validation = load_prediction_sequence(
            prediction_path,
            str(item["condition"]),
            str(item["split"]),
            manifest_sequences,
            paths["prediction_root"],
            artifact_hashes,
            anchors["checkpoint"]["sha256"],
            anchors["sequence_manifest"]["sha256"],
            anchors["inference_config"]["sha256"],
            class_names,
        )
        sequences.append(sequence)
        prediction_validation[name] = validation
    expected_sequence_ids = set(manifest_sequences)
    actual_sequence_ids = {sequence.sequence_id for sequence in sequences}
    if actual_sequence_ids != expected_sequence_ids:
        raise ContractError("Persisted prediction files do not cover the exact fixture manifest")

    diagnostic_config = require_mapping(
        config["descriptive_diagnostics"], "descriptive_diagnostics"
    )
    thresholds = [float(value) for value in diagnostic_config["threshold_values"]]
    confidence_floor = float(inference_config["inference"]["confidence_floor"])
    if confidence_floor not in thresholds or locked_threshold not in thresholds:
        raise ContractError("Descriptive threshold sweep must include floor and locked threshold")
    sweep_rows, evaluations = threshold_sweep(
        sequences, thresholds, inference_config, semantic_ids
    )
    locked_recomputation = compare_locked_recomputation(
        sequences, evaluations, metrics, locked_threshold
    )
    confusion, instance_overlap_rows = class_confusion_diagnostics(
        sequences, confidence_floor, locked_threshold, semantic_ids
    )
    motion, motion_rows = motion_diagnostics(sequences, config["locked_policy"])
    association_rows, tracker_validation = association_sweep(
        sequences,
        diagnostic_config,
        inference_config,
        locked_threshold,
    )
    association_summary = summarize_association_sweep(
        association_rows, inference_config
    )
    root_causes = root_cause_summary(
        sequences,
        sweep_rows,
        confusion,
        motion,
        association_summary,
        locked_threshold,
        confidence_floor,
    )
    null_semantics: dict[str, Any] = {}
    for sequence in sequences:
        if sequence.split != "test":
            continue
        metric = evaluations[(sequence.sequence_id, locked_threshold)]["metrics"][
            "eligible_weed_track"
        ]
        null_semantics[sequence.condition] = {
            **metric,
            "valid_interpretation": (
                "F1 is undefined because precision has no qualifying-prediction denominator; "
                "recall is defined as zero because eligible GT tracks exist. This is not a "
                "numeric-zero F1 and is not evidence of zero model accuracy."
            ),
        }
        if metric["f1"] is not None or metric["f1_state"] != (
            "undefined_missing_precision_or_recall_denominator"
        ):
            raise ContractError("Expected locked eligible-track F1 to remain undefined")

    acceptance = require_mapping(config["acceptance_rule"], "acceptance_rule")
    audit: dict[str, Any] = {
        "schema_version": 1,
        "contract": AUDIT_CONTRACT,
        "status": "PASS_HASH_BOUND_DIAGNOSTIC_SYNTHETIC_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_anchors": anchors,
        "checkpoint_class_mapping": checkpoint_mapping,
        "class_contract": {
            "checkpoint_and_predictions": {
                str(key): value for key, value in sorted(class_names.items())
            },
            "ground_truth_semantic_ids": semantic_ids,
            "id_shift_detected": False,
            "interpretation": (
                "prediction class 0=weed/1=crop and GT semantic 1=crop/2=weed are different "
                "namespaces and were decoded explicitly; all masks agree with those namespaces"
            ),
        },
        "fixture_validation": {
            "manifest": {
                "contract": manifest["contract"],
                "dataset_id": manifest["dataset_id"],
                "declared_splits": manifest["declared_splits"],
                "derivation": manifest["derivation"],
            },
            "ground_truth": gt_validation,
            "predictions": prediction_validation,
            "all_checkpoint_gt_prediction_class_bindings_verified": True,
        },
        "locked_policy": {
            **dict(config["locked_policy"]),
            "threshold_source": "frozen degraded-calibration threshold_lock_v1.json",
            "test_retuned": False,
        },
        "locked_recomputation": locked_recomputation,
        "eligible_track_f1_semantics": null_semantics,
        "class_confusion": confusion,
        "motion_vs_tracker": {
            "gt_apparent_motion_summary": motion,
            "frozen_stored_track_ids_exactly_recomputed": tracker_validation,
            "association_counterfactual_summary": association_summary,
        },
        "descriptive_sweeps": {
            "selection_or_acceptance_input": False,
            "post_hoc_locked_test_diagnostic": True,
            "outcome_target_retuning_performed": False,
            "threshold_row_count": len(sweep_rows),
            "association_row_count": len(association_rows),
            "threshold_values": thresholds,
            "association_parameter_grid": {
                "association_min_mask_iou_values": diagnostic_config[
                    "association_min_mask_iou_values"
                ],
                "association_max_centroid_distance_px_values": diagnostic_config[
                    "association_max_centroid_distance_px_values"
                ],
                "maximum_frame_gap_values": diagnostic_config[
                    "maximum_frame_gap_values"
                ],
            },
        },
        "failure_decomposition": root_causes,
        "valid_interpretation": {
            "fixture_primary_target_assessment": "not_estimated_because_f1_undefined",
            "ideal_reaches_0p97": False,
            "degraded_plausibly_near_0p75": False,
            "model_accuracy_claim_allowed": False,
            "pixel_and_instance_metrics": (
                "valid synthetic fixture diagnostics only; they neither equal track F1 nor "
                "establish field/generalization accuracy"
            ),
            "field_product_or_chemical_go": False,
        },
        "corrective_full_benchmark_acceptance_rule": {
            "rule": (
                "Any correction is chosen on fixture/calibration evidence only, frozen under a "
                "new release hash, and evaluated once on a fresh untouched full locked test. "
                "Checkpoint/class/semantic mappings, full manifest, tracker config, and the "
                "degraded-calibration-only threshold lock must verify before test access. Both "
                "arms require non-empty eligible GT denominators and defined primary F1; null F1 "
                "fails the target gate. Only then compare frozen outcomes to ideal >=0.97 and "
                "degraded [0.70,0.80], without target-driven tuning."
            ),
            **dict(acceptance),
            "current_fixture_passes_target_gate": False,
            "current_fixture_reason": "primary eligible-track F1 undefined in both arms",
        },
        "write_scope": {
            "run_root": str(run_root),
            "docs_root": str(docs_root),
            "active_full_render_lane_written": False,
            "source_fixture_or_predictions_modified": False,
            "model_inference_invoked": False,
            "gpu_training_invoked": False,
        },
    }

    run_stage = prepare_staging(run_root, replace=replace)
    docs_stage: Path | None = None
    try:
        docs_stage = prepare_staging(docs_root, replace=replace)
        write_json(run_stage / "audit.json", audit)
        write_json(run_stage / "source_hashes.json", anchors)
        write_csv(run_stage / "threshold_sweep.csv", sweep_rows)
        write_csv(run_stage / "association_sweep.csv", association_rows)
        write_csv(run_stage / "gt_motion_transitions.csv", motion_rows)
        write_csv(run_stage / "instance_overlap.csv", instance_overlap_rows)
        contact_receipt = build_contact_sheet(
            sequences,
            [int(value) for value in diagnostic_config["contact_sheet_frame_indices"]],
            int(diagnostic_config["contact_sheet_panel_px"]),
            confidence_floor,
            locked_threshold,
            semantic_ids,
            docs_stage / "diagnostic_contact_sheet.png",
        )
        audit["diagnostic_contact_sheet"] = contact_receipt
        audit["terminal_validation"] = validate_terminal_audit(audit)
        write_json(run_stage / "audit.json", audit)
        (docs_stage / "README.md").write_text(build_readme(audit), encoding="utf-8")
        shutil.copy2(run_stage / "audit.json", docs_stage / "audit_summary.json")
        for name in (
            "threshold_sweep.csv",
            "association_sweep.csv",
            "gt_motion_transitions.csv",
            "instance_overlap.csv",
        ):
            shutil.copy2(run_stage / name, docs_stage / name)
        run_inventory = artifact_inventory(
            run_stage, excluded=("package_manifest.json", "run_receipt.json")
        )
        write_json(
            run_stage / "package_manifest.json",
            {
                "schema_version": 1,
                "contract": f"{AUDIT_CONTRACT}_package_manifest",
                "source_fingerprint_sha256": anchors["source_fingerprint_sha256"],
                "artifacts": run_inventory,
            },
        )
        write_json(
            run_stage / "run_receipt.json",
            {
                "schema_version": 1,
                "contract": f"{AUDIT_CONTRACT}_run_receipt",
                "status": audit["status"],
                "source_fingerprint_sha256": anchors["source_fingerprint_sha256"],
                "locked_counts_exact": True,
                "checkpoint_class_mapping_verified": True,
                "gt_prediction_masks_verified": True,
                "tracker_assignments_exact": True,
                "eligible_track_f1_undefined_not_zero": True,
                "test_retuned": False,
                "active_full_render_lane_written": False,
                "artifacts": run_inventory,
            },
        )
        docs_inventory = artifact_inventory(
            docs_stage, excluded=("package_manifest.json",)
        )
        write_json(
            docs_stage / "package_manifest.json",
            {
                "schema_version": 1,
                "contract": f"{AUDIT_CONTRACT}_docs_manifest",
                "source_fingerprint_sha256": anchors["source_fingerprint_sha256"],
                "artifacts": docs_inventory,
            },
        )
        os.replace(run_stage, run_root)
        run_stage = Path()
        os.replace(docs_stage, docs_root)
        docs_stage = None
    finally:
        if run_stage != Path() and run_stage.exists():
            shutil.rmtree(run_stage)
        if docs_stage is not None and docs_stage.exists():
            shutil.rmtree(docs_stage)
    return {
        "status": audit["status"],
        "run_root": str(run_root),
        "docs_root": str(docs_root),
        "audit_sha256": sha256_file(run_root / "audit.json"),
        "contact_sheet_sha256": sha256_file(docs_root / "diagnostic_contact_sheet.png"),
        "source_fingerprint_sha256": anchors["source_fingerprint_sha256"],
        "locked_counts_exact": True,
        "eligible_track_f1_undefined_not_zero": True,
        "active_full_render_lane_written": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only this audit lane's two exact output directories.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        result = run_audit(arguments.config, replace=arguments.replace)
    except ContractError as error:
        print(
            stable_json(
                {
                    "status": "CONTRACT_ERROR",
                    "error": str(error),
                    "fail_closed": True,
                    "field_product_or_chemical_go": False,
                }
            ),
            file=sys.stderr,
            end="",
        )
        return 2
    print(stable_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
