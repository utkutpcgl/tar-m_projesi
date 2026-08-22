#!/usr/bin/env python3
"""Checkpoint-bound matched-pair synthetic video inference benchmark.

This evaluator is intentionally fail closed.  It verifies the selected model
checkpoint before importing/loading Ultralytics, verifies every consumed RGB
and ground-truth file against a provenance manifest, calibrates one shared
threshold on declared calibration scenes, and evaluates the locked test split
exactly once.  Its outputs are synthetic diagnostics and can never authorize
field or chemical actuation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import cv2
import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "configs/benchmark/spot_spray_simulation_video_inference_v1.yaml"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_CONTRACT = "spot_spray_simulation_video_sequence_v1"
EVALUATION_CONTRACT = "spot_spray_simulation_video_inference_v1"
CLASS_NAMES = {0: "weed", 1: "crop"}
CLASS_IDS = {value: key for key, value in CLASS_NAMES.items()}


class ContractError(RuntimeError):
    """Raised whenever a frozen input or evaluation invariant is violated."""


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
class FrameRecord:
    frame_id: str
    frame_index: int
    image_path: Path
    image_sha256: str
    semantic_mask_path: Path
    semantic_mask_sha256: str
    track_mask_path: Path
    track_mask_sha256: str
    tracks: tuple[TrackLabel, ...]


@dataclass(frozen=True)
class SequenceRecord:
    sequence_id: str
    pair_id: str
    scene_id: str
    split: str
    condition: str
    frames: tuple[FrameRecord, ...]


@dataclass
class Detection:
    detection_id: int
    class_name: str
    confidence: float
    mask: np.ndarray
    bbox_xyxy: tuple[int, int, int, int]
    centroid_xy: tuple[float, float]
    action_point_xy: tuple[int, int]
    predicted_track_id: str | None = None


@dataclass
class PredictionFrame:
    frame: FrameRecord
    detections: list[Detection]
    inference_wall_ms: float
    model_speed_ms: dict[str, float]


@dataclass
class PredictionSequence:
    sequence: SequenceRecord
    frames: list[PredictionFrame]


@dataclass(frozen=True)
class ActionEvent:
    sequence_id: str
    pair_id: str
    condition: str
    frame_id: str
    frame_index: int
    predicted_track_id: str
    confidence: float
    action_point_xy: tuple[int, int]
    confirmations_in_window: int
    disposition: str = "unscored"
    matched_gt_track_id: str | None = None


@dataclass
class AccessLedger:
    calibration_split: str
    test_split: str
    phase: str = "calibration_inference"
    threshold_selected: bool = False
    selected_threshold: float | None = None
    test_inference_started: bool = False
    locked_test_metric_evaluations: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def record_inference(self, split: str, sequence_id: str) -> None:
        if split == self.test_split and not self.threshold_selected:
            raise ContractError("Locked test inference attempted before calibration froze threshold")
        if split not in {self.calibration_split, self.test_split}:
            raise ContractError(f"Undeclared split accessed: {split}")
        if split == self.test_split:
            self.test_inference_started = True
            self.phase = "locked_test_inference"
        self.events.append(
            {
                "operation": "inference",
                "split": split,
                "sequence_id": sequence_id,
                "threshold_selected_before_access": self.threshold_selected,
            }
        )

    def freeze_threshold(self, threshold: float) -> None:
        if self.test_inference_started:
            raise ContractError("Threshold cannot be selected after locked test access")
        if self.threshold_selected:
            raise ContractError("Threshold was already selected")
        self.threshold_selected = True
        self.selected_threshold = float(threshold)
        self.phase = "threshold_frozen"
        self.events.append(
            {
                "operation": "freeze_shared_threshold",
                "source_split": self.calibration_split,
                "test_accessed": False,
                "threshold": float(threshold),
            }
        )

    def begin_locked_test_evaluation(self) -> None:
        if not self.threshold_selected:
            raise ContractError("Locked test evaluation requires a frozen threshold")
        if self.locked_test_metric_evaluations != 0:
            raise ContractError("Locked test metrics may be evaluated exactly once")
        self.locked_test_metric_evaluations = 1
        self.phase = "locked_test_evaluation"
        self.events.append(
            {
                "operation": "evaluate_locked_test_metrics",
                "split": self.test_split,
                "evaluation_number": 1,
                "threshold": self.selected_threshold,
            }
        )

    def finish(self) -> None:
        if not self.threshold_selected or self.locked_test_metric_evaluations != 1:
            raise ContractError("Evaluation access ledger is incomplete")
        self.phase = "complete"

    def receipt(self) -> dict[str, Any]:
        return {
            "calibration_split": self.calibration_split,
            "locked_test_split": self.test_split,
            "threshold_selected": self.threshold_selected,
            "selected_threshold": self.selected_threshold,
            "test_accessed_during_threshold_selection": False,
            "locked_test_metric_evaluations": self.locked_test_metric_evaluations,
            "final_phase": self.phase,
            "events": self.events,
        }


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(payload), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def resolve_path(value: str | Path, *, base: Path = PROJECT_ROOT) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ContractError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    return value


def require_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    return value


def verify_file(path: Path, expected_sha256: str, label: str) -> str:
    expected = require_sha256(expected_sha256, f"{label}.sha256")
    if not path.is_file():
        raise ContractError(f"{label} is missing: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise ContractError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return observed


def load_config(path: Path) -> dict[str, Any]:
    config_path = path.expanduser().resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = dict(require_mapping(payload, "config"))
    if config.get("schema_version") != 1 or config.get("contract") != EVALUATION_CONTRACT:
        raise ContractError("Evaluation config schema or contract mismatch")
    policy = require_mapping(config.get("evidence_policy"), "evidence_policy")
    if policy.get("scope") != "synthetic_diagnostic_only":
        raise ContractError("Only synthetic_diagnostic_only evidence is allowed")
    forbidden_true = (
        bool(policy.get("field_or_deployment_claim_allowed"))
        or bool(policy.get("chemical_fire_go_allowed"))
    )
    if forbidden_true or float(policy.get("synthetic_score_weight_in_real_go_decision", -1)) != 0.0:
        raise ContractError("Synthetic evidence policy must remain fail closed")
    if policy.get("outcome_target_tuning_forbidden") is not True:
        raise ContractError("Outcome-target tuning prohibition must remain enabled")

    checkpoint = require_mapping(config.get("checkpoint"), "checkpoint")
    require_sha256(checkpoint.get("sha256"), "checkpoint.sha256")
    if checkpoint.get("task") != "segment":
        raise ContractError("Checkpoint task must be segment")
    observed_names = {int(key): str(value) for key, value in require_mapping(
        checkpoint.get("class_names"), "checkpoint.class_names"
    ).items()}
    if observed_names != CLASS_NAMES:
        raise ContractError(f"Checkpoint class contract must equal {CLASS_NAMES}")

    source = require_mapping(config.get("source"), "source")
    calibration_split = str(source.get("calibration_split"))
    test_split = str(source.get("locked_test_split"))
    if calibration_split == test_split or calibration_split != "calibration" or test_split != "test":
        raise ContractError("Frozen split names must be calibration and test")
    calibration = require_mapping(config.get("calibration"), "calibration")
    if calibration.get("source_split") != calibration_split:
        raise ContractError("Calibration split declaration mismatch")
    if calibration.get("test_access_forbidden") is not True:
        raise ContractError("Calibration must forbid test access")
    if calibration.get("shared_threshold_across_conditions") is not True:
        raise ContractError("A shared threshold across matched conditions is required")

    conditions = require_mapping(config.get("conditions"), "conditions")
    ordered = [str(item) for item in require_sequence(conditions.get("ordered"), "conditions.ordered")]
    if ordered != ["ideal", "degraded"]:
        raise ContractError("Matched-pair conditions must be ordered [ideal, degraded]")
    degradation = require_mapping(conditions.get("degraded"), "conditions.degraded")
    if degradation.get("calibrated_to_physical_camera") is not False:
        raise ContractError("Synthetic degradation must not claim physical calibration")

    inference = require_mapping(config.get("inference"), "inference")
    floor = float(inference.get("confidence_floor", -1))
    grid = require_mapping(calibration.get("threshold_grid"), "calibration.threshold_grid")
    start, stop, step = float(grid["start"]), float(grid["stop"]), float(grid["step"])
    if not (0.0 <= floor <= start <= stop <= 1.0 and step > 0.0):
        raise ContractError("Invalid inference floor or calibration threshold grid")
    temporal = require_mapping(config.get("temporal_action"), "temporal_action")
    confirmations = int(temporal.get("minimum_confirmations", 0))
    window = int(temporal.get("preferred_window_frames", 0))
    if not (1 <= confirmations <= window):
        raise ContractError("Temporal action requires 1 <= confirmations <= window")
    if temporal.get("fire_once_per_predicted_track") is not True:
        raise ContractError("Fire-once policy must remain enabled")
    targets = require_mapping(config.get("descriptive_targets"), "descriptive_targets")
    if targets.get("metric") != "eligible_weed_mask_track_spatiotemporal_iou_f1":
        raise ContractError("Descriptive target metric changed")
    if float(targets.get("ideal_minimum", -1.0)) != 0.97:
        raise ContractError("Ideal descriptive target must remain 0.97")
    if float(targets.get("degraded_reference", -1.0)) != 0.75:
        raise ContractError("Degraded descriptive reference must remain 0.75")
    tolerance = float(targets.get("degraded_near_absolute_tolerance", -1.0))
    if tolerance != 0.05:
        raise ContractError("Degraded descriptive tolerance must remain 0.05")
    if bool(targets.get("use_in_threshold_selection")) or bool(
        targets.get("use_in_model_or_degradation_tuning")
    ):
        raise ContractError("Descriptive targets must never tune benchmark outcomes")
    return config


def threshold_grid(config: Mapping[str, Any]) -> list[float]:
    grid = config["calibration"]["threshold_grid"]
    start, stop, step = float(grid["start"]), float(grid["stop"]), float(grid["step"])
    count = int(math.floor((stop - start) / step + 1e-9))
    values = [round(start + index * step, 10) for index in range(count + 1)]
    if not values or values[-1] < stop - 1e-9:
        values.append(round(stop, 10))
    return values


def size_stratum(canopy_span_mm: float, config: Mapping[str, Any]) -> str:
    minimum = float(config["ground_truth"]["eligible_weed_minimum_canopy_span_mm"])
    if canopy_span_mm < minimum:
        return "below_eligible_size"
    for name, bounds in config["ground_truth"]["size_strata_mm"].items():
        lower = float(bounds[0])
        upper = None if bounds[1] is None else float(bounds[1])
        if canopy_span_mm >= lower and (upper is None or canopy_span_mm < upper):
            return str(name)
    raise ContractError(f"No size stratum covers canopy span {canopy_span_mm}")


def _track_labels_from_masks(
    semantic: np.ndarray,
    instances: np.ndarray,
    *,
    pair_id: str,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    semantic_ids = config["source"]["v12_smoke"]["semantic_ids"]
    class_by_semantic = {
        int(semantic_ids["crop"]): "crop",
        int(semantic_ids["weed"]): "weed",
    }
    gsd = float(config["source"]["v12_smoke"]["gsd_mm_per_px"])
    height, width = instances.shape
    tracks: list[dict[str, Any]] = []
    for mask_id in sorted(int(value) for value in np.unique(instances) if int(value) != 0):
        selected = instances == mask_id
        semantic_values, counts = np.unique(semantic[selected], return_counts=True)
        plant_counts = [
            (int(count), int(value))
            for value, count in zip(semantic_values, counts)
            if int(value) in class_by_semantic
        ]
        if not plant_counts:
            raise ContractError(f"Track mask ID {mask_id} contains no declared plant class")
        count, semantic_id = max(plant_counts)
        if count != int(selected.sum()):
            raise ContractError(f"Track mask ID {mask_id} crosses semantic classes")
        ys, xs = np.where(selected)
        span_px = max(int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
        canopy_span_mm = float(span_px * gsd)
        partial = bool(
            xs.min() == 0 or ys.min() == 0 or xs.max() == width - 1 or ys.max() == height - 1
        )
        tracks.append(
            {
                "mask_id": mask_id,
                "track_id": f"{pair_id}:gt:{mask_id:04d}",
                "class_name": class_by_semantic[semantic_id],
                "canopy_span_mm": canopy_span_mm,
                "visible_fraction": 1.0,
                "partial": partial,
                "size_stratum": size_stratum(canopy_span_mm, config),
            }
        )
    return tracks


def deterministic_degradation(
    image_bgr: np.ndarray,
    degradation: Mapping[str, Any],
    *,
    seed: int,
) -> np.ndarray:
    kernel = int(degradation["gaussian_blur_kernel_px"])
    if kernel < 1 or kernel % 2 == 0:
        raise ContractError("Gaussian blur kernel must be a positive odd integer")
    output = cv2.GaussianBlur(
        image_bgr,
        (kernel, kernel),
        sigmaX=float(degradation["gaussian_blur_sigma_px"]),
        sigmaY=float(degradation["gaussian_blur_sigma_px"]),
    )
    motion_length = int(degradation["motion_blur_length_px"])
    if motion_length < 1 or motion_length % 2 == 0:
        raise ContractError("Motion blur length must be a positive odd integer")
    motion_kernel = np.zeros((motion_length, motion_length), dtype=np.float32)
    motion_kernel[motion_length // 2, :] = 1.0 / motion_length
    output = cv2.filter2D(output, -1, motion_kernel, borderType=cv2.BORDER_REFLECT101)
    work = output.astype(np.float32)
    work = (work - 127.5) * float(degradation["contrast_scale"]) + 127.5
    work *= float(degradation["exposure_scale"])
    rng = np.random.default_rng(seed)
    work += rng.normal(0.0, float(degradation["gaussian_noise_sigma_dn"]), work.shape)
    work = np.clip(np.rint(work), 0, 255).astype(np.uint8)
    quality = int(degradation["jpeg_quality"])
    ok, encoded = cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ContractError("OpenCV failed to encode degraded smoke frame")
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if decoded is None or decoded.shape != image_bgr.shape:
        raise ContractError("OpenCV failed to decode degraded smoke frame")
    return decoded


def build_v12_smoke_manifest(
    config: Mapping[str, Any],
    output_dir: Path,
) -> Path:
    source = config["source"]["v12_smoke"]
    membership_path = resolve_path(source["membership"])
    receipt_path = resolve_path(source["dataset_receipt"])
    verify_file(membership_path, source["membership_sha256"], "V12 membership")
    verify_file(receipt_path, source["dataset_receipt_sha256"], "V12 dataset receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != 1 or receipt.get("dataset_id") != source["dataset_id"]:
        raise ContractError("V12 receipt schema or dataset ID mismatch")
    if receipt.get("all_quality_gates_passed") is not True:
        raise ContractError("V12 source quality gates are not all passed")
    if receipt.get("ground_truth_tree_sha256") != source["expected_ground_truth_tree_sha256"]:
        raise ContractError("V12 ground-truth tree receipt changed")
    if receipt.get("images_tree_sha256") != source["expected_images_tree_sha256"]:
        raise ContractError("V12 image tree receipt changed")
    if float(receipt["evaluation_policy"]["real_model_selection_score_weight"]) != 0.0:
        raise ContractError("V12 synthetic evidence weight changed from zero")
    if receipt["label_contract"].get("botanical_instance_ids_available") is not False:
        raise ContractError("Smoke derivation expects region proxies, not botanical IDs")

    rows = [
        json.loads(line)
        for line in membership_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    suffix = str(source["source_frame_suffix"])
    selected: list[tuple[str, str, Mapping[str, Any]]] = []
    declarations = (
        ("val", config["source"]["calibration_split"], source["calibration_scenes"]),
        ("test", config["source"]["locked_test_split"], source["test_scenes"]),
    )
    for role, split, scenes in declarations:
        for scene in scenes:
            matches = [
                row
                for row in rows
                if row.get("role") == role
                and row.get("scene") == scene
                and Path(str(row.get("image_path", ""))).stem.endswith(suffix)
            ]
            if len(matches) != 1:
                raise ContractError(
                    f"Expected exactly one V12 source row for {role}/{scene}/{suffix}, got {len(matches)}"
                )
            selected.append((str(split), str(scene), matches[0]))

    manifest_dir = output_dir / "manifest"
    derived_dir = manifest_dir / "derived_rgb"
    derived_dir.mkdir(parents=True, exist_ok=False)
    repeated = int(source["repeated_frames_per_sequence"])
    minimum_confirmations = int(config["temporal_action"]["minimum_confirmations"])
    if repeated < minimum_confirmations:
        raise ContractError("Smoke sequences must cover the frozen confirmation count")

    sequences: list[dict[str, Any]] = []
    consumed_source_files: dict[str, str] = {}
    for split, scene, row in selected:
        pair_id = f"{split}:{scene}"
        image_path = resolve_path(str(row["image_path"]))
        semantic_path = resolve_path(str(row["semantics_path"]))
        track_path = resolve_path(str(row["plant_instances_path"]))
        for source_path in (image_path, semantic_path, track_path):
            if not source_path.is_file():
                raise ContractError(f"Selected V12 source file is missing: {source_path}")
            consumed_source_files[str(source_path)] = sha256_file(source_path)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        semantic = cv2.imread(str(semantic_path), cv2.IMREAD_UNCHANGED)
        track_mask = cv2.imread(str(track_path), cv2.IMREAD_UNCHANGED)
        if image is None or semantic is None or track_mask is None:
            raise ContractError(f"Failed to decode selected V12 row: {pair_id}")
        if image.shape[:2] != semantic.shape[:2] or semantic.shape != track_mask.shape:
            raise ContractError(f"RGB/semantic/track geometry mismatch: {pair_id}")
        labels = _track_labels_from_masks(
            semantic,
            track_mask,
            pair_id=pair_id,
            config=config,
        )
        for condition_index, condition in enumerate(config["conditions"]["ordered"]):
            sequence_id = f"{condition}:{pair_id}"
            frames: list[dict[str, Any]] = []
            for frame_index in range(repeated):
                if condition == "ideal":
                    rendered_path = image_path
                else:
                    condition_dir = derived_dir / condition / split / scene
                    condition_dir.mkdir(parents=True, exist_ok=True)
                    rendered_path = condition_dir / f"frame_{frame_index:04d}.jpg"
                    seed_payload = f"{config['inference']['seed']}:{pair_id}:{frame_index}:{condition_index}"
                    seed = int(hashlib.sha256(seed_payload.encode()).hexdigest()[:8], 16)
                    degraded = deterministic_degradation(
                        image,
                        config["conditions"]["degraded"],
                        seed=seed,
                    )
                    if not cv2.imwrite(
                        str(rendered_path),
                        degraded,
                        [cv2.IMWRITE_JPEG_QUALITY, int(config["conditions"]["degraded"]["jpeg_quality"])],
                    ):
                        raise ContractError(f"Failed to write degraded frame: {rendered_path}")
                manifest_image_path = (
                    str(rendered_path.resolve())
                    if rendered_path.is_absolute() and not rendered_path.is_relative_to(manifest_dir)
                    else rendered_path.relative_to(manifest_dir).as_posix()
                )
                frames.append(
                    {
                        "frame_id": f"{sequence_id}:frame_{frame_index:04d}",
                        "frame_index": frame_index,
                        "image_path": manifest_image_path,
                        "image_sha256": sha256_file(rendered_path),
                        "semantic_mask_path": str(semantic_path),
                        "semantic_mask_sha256": consumed_source_files[str(semantic_path)],
                        "track_mask_path": str(track_path),
                        "track_mask_sha256": consumed_source_files[str(track_path)],
                        "tracks": labels,
                    }
                )
            sequences.append(
                {
                    "sequence_id": sequence_id,
                    "pair_id": pair_id,
                    "scene_id": scene,
                    "split": split,
                    "condition": condition,
                    "frames": frames,
                }
            )

    manifest = {
        "schema_version": 1,
        "contract": MANIFEST_CONTRACT,
        "dataset_id": f"{source['dataset_id']}:repeated_region_proxy_smoke_v1",
        "evidence_scope": "synthetic_diagnostic_only",
        "declared_splits": {
            "calibration": config["source"]["calibration_split"],
            "locked_test": config["source"]["locked_test_split"],
        },
        "conditions": list(config["conditions"]["ordered"]),
        "provenance": {
            "source_dataset_id": source["dataset_id"],
            "membership": str(membership_path),
            "membership_sha256": source["membership_sha256"],
            "dataset_receipt": str(receipt_path),
            "dataset_receipt_sha256": source["dataset_receipt_sha256"],
            "consumed_source_files": consumed_source_files,
        },
        "derivation": {
            "type": "v12_static_frame_repetition_smoke",
            "frames_per_sequence": repeated,
            "region_proxy_not_botanical_track": True,
            "degradation_frozen_before_inference": True,
            "degradation": config["conditions"]["degraded"],
            "limitation": source["limitation"],
        },
        "sequences": sequences,
    }
    manifest_path = manifest_dir / "sequence_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def _manifest_path(value: Any, *, manifest_dir: Path, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty path")
    return resolve_path(value, base=manifest_dir)


def _parse_track_label(value: Any, label: str) -> TrackLabel:
    row = require_mapping(value, label)
    mask_id = int(row.get("mask_id", 0))
    track_id = str(row.get("track_id", ""))
    class_name = str(row.get("class_name", ""))
    canopy_span_mm = float(row.get("canopy_span_mm", -1.0))
    visible_fraction = float(row.get("visible_fraction", -1.0))
    partial = row.get("partial")
    size_name = str(row.get("size_stratum", ""))
    if mask_id < 1 or not track_id:
        raise ContractError(f"{label} has invalid mask_id or track_id")
    if class_name not in CLASS_IDS:
        raise ContractError(f"{label} has unknown class {class_name}")
    if canopy_span_mm <= 0.0 or not 0.0 <= visible_fraction <= 1.0:
        raise ContractError(f"{label} has invalid physical/visibility metadata")
    if not isinstance(partial, bool) or not size_name:
        raise ContractError(f"{label} has invalid partial or size stratum")
    return TrackLabel(
        mask_id=mask_id,
        track_id=track_id,
        class_name=class_name,
        canopy_span_mm=canopy_span_mm,
        visible_fraction=visible_fraction,
        partial=partial,
        size_stratum=size_name,
    )


def load_sequence_manifest(
    manifest_path: Path,
    config: Mapping[str, Any],
) -> tuple[list[SequenceRecord], dict[str, Any]]:
    path = manifest_path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = dict(require_mapping(payload, "sequence manifest"))
    if manifest.get("schema_version") != 1 or manifest.get("contract") != MANIFEST_CONTRACT:
        raise ContractError("Sequence manifest schema or contract mismatch")
    if manifest.get("evidence_scope") != "synthetic_diagnostic_only":
        raise ContractError("Sequence manifest may only contain synthetic diagnostic evidence")
    expected_conditions = list(config["conditions"]["ordered"])
    if manifest.get("conditions") != expected_conditions:
        raise ContractError("Sequence manifest condition order changed")
    declared = require_mapping(manifest.get("declared_splits"), "declared_splits")
    calibration_split = config["source"]["calibration_split"]
    test_split = config["source"]["locked_test_split"]
    if declared.get("calibration") != calibration_split or declared.get("locked_test") != test_split:
        raise ContractError("Sequence manifest split declarations mismatch config")

    manifest_dir = path.parent
    hash_cache: dict[Path, str] = {}

    def cached_verify(file_path: Path, expected: str, label: str) -> None:
        expected = require_sha256(expected, f"{label}.sha256")
        if file_path not in hash_cache:
            if not file_path.is_file():
                raise ContractError(f"{label} is missing: {file_path}")
            hash_cache[file_path] = sha256_file(file_path)
        if hash_cache[file_path] != expected:
            raise ContractError(
                f"{label} SHA-256 mismatch: expected {expected}, observed {hash_cache[file_path]}"
            )

    sequences: list[SequenceRecord] = []
    seen_sequence_ids: set[str] = set()
    seen_frame_ids: set[str] = set()
    for sequence_index, raw_sequence in enumerate(
        require_sequence(manifest.get("sequences"), "sequences")
    ):
        row = require_mapping(raw_sequence, f"sequences[{sequence_index}]")
        sequence_id = str(row.get("sequence_id", ""))
        pair_id = str(row.get("pair_id", ""))
        scene_id = str(row.get("scene_id", ""))
        split = str(row.get("split", ""))
        condition = str(row.get("condition", ""))
        if not sequence_id or sequence_id in seen_sequence_ids:
            raise ContractError(f"Duplicate or empty sequence_id: {sequence_id}")
        seen_sequence_ids.add(sequence_id)
        if not pair_id or not scene_id or split not in {calibration_split, test_split}:
            raise ContractError(f"Sequence {sequence_id} has invalid pair/scene/split")
        if condition not in expected_conditions:
            raise ContractError(f"Sequence {sequence_id} has undeclared condition")
        frames: list[FrameRecord] = []
        prior_index = -1
        for frame_offset, raw_frame in enumerate(
            require_sequence(row.get("frames"), f"{sequence_id}.frames")
        ):
            frame_row = require_mapping(raw_frame, f"{sequence_id}.frames[{frame_offset}]")
            frame_id = str(frame_row.get("frame_id", ""))
            frame_index = int(frame_row.get("frame_index", -1))
            if not frame_id or frame_id in seen_frame_ids:
                raise ContractError(f"Duplicate or empty frame_id: {frame_id}")
            seen_frame_ids.add(frame_id)
            if frame_index <= prior_index:
                raise ContractError(f"Frame indices must strictly increase in {sequence_id}")
            prior_index = frame_index
            image_path = _manifest_path(
                frame_row.get("image_path"), manifest_dir=manifest_dir, label=f"{frame_id}.image_path"
            )
            semantic_path = _manifest_path(
                frame_row.get("semantic_mask_path"),
                manifest_dir=manifest_dir,
                label=f"{frame_id}.semantic_mask_path",
            )
            track_path = _manifest_path(
                frame_row.get("track_mask_path"),
                manifest_dir=manifest_dir,
                label=f"{frame_id}.track_mask_path",
            )
            image_sha = require_sha256(frame_row.get("image_sha256"), f"{frame_id}.image_sha256")
            semantic_sha = require_sha256(
                frame_row.get("semantic_mask_sha256"), f"{frame_id}.semantic_mask_sha256"
            )
            track_sha = require_sha256(
                frame_row.get("track_mask_sha256"), f"{frame_id}.track_mask_sha256"
            )
            cached_verify(image_path, image_sha, f"{frame_id}.image")
            cached_verify(semantic_path, semantic_sha, f"{frame_id}.semantic_mask")
            cached_verify(track_path, track_sha, f"{frame_id}.track_mask")
            labels = tuple(
                _parse_track_label(value, f"{frame_id}.tracks[{index}]")
                for index, value in enumerate(
                    require_sequence(frame_row.get("tracks"), f"{frame_id}.tracks")
                )
            )
            mask_ids = [item.mask_id for item in labels]
            track_ids = [item.track_id for item in labels]
            if len(mask_ids) != len(set(mask_ids)) or len(track_ids) != len(set(track_ids)):
                raise ContractError(f"Duplicate mask or track identity in {frame_id}")
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            semantic = cv2.imread(str(semantic_path), cv2.IMREAD_UNCHANGED)
            track_mask = cv2.imread(str(track_path), cv2.IMREAD_UNCHANGED)
            if image is None or semantic is None or track_mask is None:
                raise ContractError(f"Unable to decode RGB/ground truth for {frame_id}")
            if image.shape[:2] != semantic.shape[:2] or semantic.shape != track_mask.shape:
                raise ContractError(f"RGB/ground-truth geometry mismatch for {frame_id}")
            observed_ids = {int(value) for value in np.unique(track_mask) if int(value) != 0}
            if observed_ids != set(mask_ids):
                raise ContractError(f"Track label IDs do not exactly cover mask IDs for {frame_id}")
            semantic_ids = config["source"]["v12_smoke"]["semantic_ids"]
            expected_semantic = {"crop": int(semantic_ids["crop"]), "weed": int(semantic_ids["weed"])}
            for item in labels:
                values = set(int(value) for value in np.unique(semantic[track_mask == item.mask_id]))
                if values != {expected_semantic[item.class_name]}:
                    raise ContractError(
                        f"Track {item.track_id} semantic class disagrees with its mask in {frame_id}"
                    )
                expected_size = size_stratum(item.canopy_span_mm, config)
                if item.size_stratum != expected_size:
                    raise ContractError(f"Track {item.track_id} size stratum mismatch")
            frames.append(
                FrameRecord(
                    frame_id=frame_id,
                    frame_index=frame_index,
                    image_path=image_path,
                    image_sha256=image_sha,
                    semantic_mask_path=semantic_path,
                    semantic_mask_sha256=semantic_sha,
                    track_mask_path=track_path,
                    track_mask_sha256=track_sha,
                    tracks=labels,
                )
            )
        if not frames:
            raise ContractError(f"Sequence {sequence_id} is empty")
        sequences.append(
            SequenceRecord(
                sequence_id=sequence_id,
                pair_id=pair_id,
                scene_id=scene_id,
                split=split,
                condition=condition,
                frames=tuple(frames),
            )
        )

    grouped: dict[tuple[str, str], dict[str, SequenceRecord]] = defaultdict(dict)
    for sequence in sequences:
        key = (sequence.split, sequence.pair_id)
        if sequence.condition in grouped[key]:
            raise ContractError(f"Duplicate condition for matched pair {key}")
        grouped[key][sequence.condition] = sequence
    if not grouped:
        raise ContractError("Sequence manifest contains no matched pairs")
    for key, conditions in sorted(grouped.items()):
        if set(conditions) != set(expected_conditions):
            raise ContractError(f"Matched pair {key} does not contain exactly both conditions")
        reference = conditions[expected_conditions[0]]
        for condition in expected_conditions[1:]:
            candidate = conditions[condition]
            if len(reference.frames) != len(candidate.frames):
                raise ContractError(f"Matched pair {key} frame count differs by condition")
            for left, right in zip(reference.frames, candidate.frames):
                left_truth = (
                    left.frame_index,
                    left.semantic_mask_sha256,
                    left.track_mask_sha256,
                    tuple(asdict(item) for item in left.tracks),
                )
                right_truth = (
                    right.frame_index,
                    right.semantic_mask_sha256,
                    right.track_mask_sha256,
                    tuple(asdict(item) for item in right.tracks),
                )
                if left_truth != right_truth:
                    raise ContractError(f"Matched pair {key} ground truth differs by condition")
    calibration_pairs = {pair for split, pair in grouped if split == calibration_split}
    test_pairs = {pair for split, pair in grouped if split == test_split}
    if not calibration_pairs or not test_pairs or calibration_pairs & test_pairs:
        raise ContractError("Calibration/test pair identities must be non-empty and disjoint")
    track_splits: dict[str, set[str]] = defaultdict(set)
    for sequence in sequences:
        for frame in sequence.frames:
            for track in frame.tracks:
                track_splits[track.track_id].add(sequence.split)
    if any(len(splits) != 1 for splits in track_splits.values()):
        raise ContractError("Ground-truth track identity crosses calibration/test split")

    metadata = {
        "path": str(path),
        "sha256": sha256_file(path),
        "dataset_id": manifest.get("dataset_id"),
        "evidence_scope": manifest.get("evidence_scope"),
        "provenance": manifest.get("provenance"),
        "derivation": manifest.get("derivation"),
        "matched_pair_count": len(grouped),
        "calibration_pair_count": len(calibration_pairs),
        "test_pair_count": len(test_pairs),
        "sequence_count": len(sequences),
        "frame_count": sum(len(item.frames) for item in sequences),
        "all_consumed_files_sha256_verified": True,
        "ground_truth_identical_within_pairs": True,
        "calibration_test_pair_ids_disjoint": True,
    }
    return sorted(sequences, key=lambda item: (item.split, item.pair_id, item.condition)), metadata


def load_verified_model(
    checkpoint_path: Path,
    expected_sha256: str,
    *,
    task: str = "segment",
    yolo_factory: Callable[..., Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Verify the complete checkpoint before any model loader is invoked."""

    path = checkpoint_path.expanduser().resolve()
    observed_sha = verify_file(path, expected_sha256, "selected checkpoint")
    if yolo_factory is None:
        from ultralytics import YOLO  # Imported only after the hash gate passes.

        yolo_factory = YOLO
    model = yolo_factory(str(path), task=task)
    names = {int(key): str(value) for key, value in dict(model.names).items()}
    if names != CLASS_NAMES:
        raise ContractError(f"Loaded checkpoint classes {names} do not match {CLASS_NAMES}")
    return model, {
        "path": str(path),
        "sha256": observed_sha,
        "bytes": path.stat().st_size,
        "task": task,
        "class_names": names,
        "hash_verified_before_model_loader_invocation": True,
    }


def configure_determinism(seed: int) -> dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except TypeError:
        torch.use_deterministic_algorithms(True)
    return {
        "seed": seed,
        "python_random_seeded": True,
        "numpy_seeded": True,
        "torch_seeded": True,
        "torch_deterministic_algorithms_warn_only": True,
        "cuda_available": bool(torch.cuda.is_available()),
        "torch_version": torch.__version__,
    }


def _as_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    intersection = int(np.logical_and(left, right).sum())
    union = int(np.logical_or(left, right).sum())
    return intersection / union if union else 0.0


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise ContractError("Predicted mask is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def mask_centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise ContractError("Predicted mask is empty")
    return float(xs.mean()), float(ys.mean())


def maximum_interior_point(mask: np.ndarray) -> tuple[int, int]:
    if not np.any(mask):
        raise ContractError("Cannot choose an action point from an empty mask")
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    _, _, _, maximum_location = cv2.minMaxLoc(distance)
    return int(maximum_location[0]), int(maximum_location[1])


def _resize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if mask.shape == shape:
        return mask.astype(bool)
    resized = cv2.resize(
        mask.astype(np.uint8),
        (shape[1], shape[0]),
        interpolation=cv2.INTER_NEAREST,
    )
    return resized.astype(bool)


def detections_from_result(result: Any, frame_shape: tuple[int, int]) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    masks_object = getattr(result, "masks", None)
    if boxes is None or masks_object is None or getattr(masks_object, "data", None) is None:
        return []
    classes = _as_numpy(boxes.cls).astype(np.int64).reshape(-1)
    confidences = _as_numpy(boxes.conf).astype(np.float64).reshape(-1)
    raw_masks = _as_numpy(masks_object.data)
    if raw_masks.ndim != 3 or len(classes) != len(confidences) or len(classes) != raw_masks.shape[0]:
        raise ContractError("Ultralytics result boxes/masks have inconsistent lengths")
    detections: list[Detection] = []
    for source_index, (class_id, confidence, raw_mask) in enumerate(
        zip(classes.tolist(), confidences.tolist(), raw_masks)
    ):
        if int(class_id) not in CLASS_NAMES:
            raise ContractError(f"Model emitted undeclared class ID {class_id}")
        mask = _resize_mask(raw_mask > 0.5, frame_shape)
        if not np.any(mask):
            continue
        detections.append(
            Detection(
                detection_id=source_index,
                class_name=CLASS_NAMES[int(class_id)],
                confidence=float(confidence),
                mask=mask,
                bbox_xyxy=mask_bbox(mask),
                centroid_xy=mask_centroid(mask),
                action_point_xy=maximum_interior_point(mask),
            )
        )
    detections.sort(
        key=lambda item: (
            -item.confidence,
            item.class_name,
            item.bbox_xyxy,
            item.detection_id,
        )
    )
    for index, item in enumerate(detections):
        item.detection_id = index
    return detections


def assign_predicted_tracks(
    prediction_frames: Sequence[PredictionFrame],
    tracking: Mapping[str, Any],
) -> None:
    minimum_iou = float(tracking["association_min_mask_iou"])
    maximum_distance = float(tracking["association_max_centroid_distance_px"])
    maximum_gap = int(tracking["maximum_frame_gap"])
    active: dict[int, tuple[str, int, np.ndarray, tuple[float, float]]] = {}
    next_track = 1
    for prediction in sorted(prediction_frames, key=lambda item: item.frame.frame_index):
        frame_index = prediction.frame.frame_index
        active = {
            track_number: state
            for track_number, state in active.items()
            if frame_index - state[1] <= maximum_gap
        }
        candidates: list[tuple[float, float, int, int]] = []
        for detection_index, detection in enumerate(prediction.detections):
            for track_number, (class_name, last_frame, last_mask, centroid) in active.items():
                if class_name != detection.class_name or last_frame == frame_index:
                    continue
                overlap = mask_iou(last_mask, detection.mask)
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
            detection = prediction.detections[detection_index]
            detection.predicted_track_id = f"p{track_number:04d}"
            active[track_number] = (
                detection.class_name,
                frame_index,
                detection.mask,
                detection.centroid_xy,
            )
            used_detections.add(detection_index)
            used_tracks.add(track_number)
        for detection_index, detection in enumerate(prediction.detections):
            if detection_index in used_detections:
                continue
            track_number = next_track
            next_track += 1
            detection.predicted_track_id = f"p{track_number:04d}"
            active[track_number] = (
                detection.class_name,
                frame_index,
                detection.mask,
                detection.centroid_xy,
            )


def _predict_one(model: Any, image: np.ndarray, config: Mapping[str, Any]) -> tuple[Any, float]:
    inference = config["inference"]
    import torch

    if torch.cuda.is_available() and str(inference["device"]) != "cpu":
        torch.cuda.synchronize()
    started = time.perf_counter()
    outputs = model.predict(
        source=image,
        imgsz=int(inference["image_size_px"]),
        conf=float(inference["confidence_floor"]),
        iou=float(inference["nms_iou"]),
        device=inference["device"],
        half=bool(inference["half"]),
        deterministic=bool(inference["deterministic"]),
        verbose=False,
    )
    if torch.cuda.is_available() and str(inference["device"]) != "cpu":
        torch.cuda.synchronize()
    wall_ms = (time.perf_counter() - started) * 1000.0
    if len(outputs) != 1:
        raise ContractError("Model must return exactly one result per frame")
    return outputs[0], wall_ms


def persist_prediction_sequence(
    prediction: PredictionSequence,
    artifact_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sequence_root = artifact_root / prediction.sequence.condition / prediction.sequence.sequence_id.replace(":", "_")
    sequence_root.mkdir(parents=True, exist_ok=True)
    for frame_prediction in prediction.frames:
        frame = frame_prediction.frame
        masks = np.stack(
            [item.mask.astype(np.uint8) for item in frame_prediction.detections],
            axis=0,
        ) if frame_prediction.detections else np.zeros((0, 1, 1), dtype=np.uint8)
        class_ids = np.asarray(
            [CLASS_IDS[item.class_name] for item in frame_prediction.detections], dtype=np.int16
        )
        confidences = np.asarray(
            [item.confidence for item in frame_prediction.detections], dtype=np.float32
        )
        track_numbers = np.asarray(
            [int(str(item.predicted_track_id)[1:]) for item in frame_prediction.detections],
            dtype=np.int32,
        )
        npz_path = sequence_root / f"frame_{frame.frame_index:04d}.npz"
        np.savez_compressed(
            npz_path,
            masks=masks,
            class_ids=class_ids,
            confidences=confidences,
            track_numbers=track_numbers,
        )
        rows.append(
            {
                "record_type": "frame_prediction",
                "sequence_id": prediction.sequence.sequence_id,
                "pair_id": prediction.sequence.pair_id,
                "split": prediction.sequence.split,
                "condition": prediction.sequence.condition,
                "frame_id": frame.frame_id,
                "frame_index": frame.frame_index,
                "source_image_sha256": frame.image_sha256,
                "prediction_masks_npz": npz_path.relative_to(artifact_root.parent).as_posix(),
                "prediction_masks_npz_sha256": sha256_file(npz_path),
                "inference_wall_ms": frame_prediction.inference_wall_ms,
                "model_speed_ms": frame_prediction.model_speed_ms,
                "detections": [
                    {
                        "detection_id": item.detection_id,
                        "class_name": item.class_name,
                        "confidence": item.confidence,
                        "predicted_track_id": item.predicted_track_id,
                        "bbox_xyxy": list(item.bbox_xyxy),
                        "centroid_xy": list(item.centroid_xy),
                        "action_point_xy": list(item.action_point_xy),
                        "mask_pixels": int(item.mask.sum()),
                        "mask_sha256": sha256_bytes(item.mask.astype(np.uint8).tobytes()),
                    }
                    for item in frame_prediction.detections
                ],
            }
        )
    return rows


def predict_sequences(
    model: Any,
    sequences: Sequence[SequenceRecord],
    config: Mapping[str, Any],
    ledger: AccessLedger,
    artifact_root: Path,
) -> tuple[dict[str, PredictionSequence], list[dict[str, Any]]]:
    output: dict[str, PredictionSequence] = {}
    rows: list[dict[str, Any]] = []
    for sequence in sorted(sequences, key=lambda item: (item.pair_id, item.condition)):
        ledger.record_inference(sequence.split, sequence.sequence_id)
        prediction_frames: list[PredictionFrame] = []
        for frame in sequence.frames:
            image = cv2.imread(str(frame.image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ContractError(f"Failed to decode inference RGB: {frame.image_path}")
            result, wall_ms = _predict_one(model, image, config)
            speed = {
                str(key): float(value)
                for key, value in dict(getattr(result, "speed", {}) or {}).items()
            }
            prediction_frames.append(
                PredictionFrame(
                    frame=frame,
                    detections=detections_from_result(result, image.shape[:2]),
                    inference_wall_ms=wall_ms,
                    model_speed_ms=speed,
                )
            )
        assign_predicted_tracks(prediction_frames, config["tracking"])
        prediction = PredictionSequence(sequence=sequence, frames=prediction_frames)
        output[sequence.sequence_id] = prediction
        rows.extend(persist_prediction_sequence(prediction, artifact_root))
    return output, rows


def is_eligible_weed(track: TrackLabel, config: Mapping[str, Any]) -> bool:
    ground_truth = config["ground_truth"]
    return bool(
        track.class_name == "weed"
        and track.canopy_span_mm
        >= float(ground_truth["eligible_weed_minimum_canopy_span_mm"])
        and track.visible_fraction
        >= float(ground_truth["eligible_weed_minimum_visible_fraction"])
        and (
            not bool(ground_truth["require_non_partial_observation"])
            or not track.partial
        )
    )


def _truth_for_frame(frame: FrameRecord) -> tuple[np.ndarray, np.ndarray, dict[int, TrackLabel]]:
    semantic = cv2.imread(str(frame.semantic_mask_path), cv2.IMREAD_UNCHANGED)
    track_mask = cv2.imread(str(frame.track_mask_path), cv2.IMREAD_UNCHANGED)
    if semantic is None or track_mask is None:
        raise ContractError(f"Ground truth disappeared after manifest validation: {frame.frame_id}")
    return semantic, track_mask, {track.mask_id: track for track in frame.tracks}


def greedy_mask_matches(
    predicted: Sequence[np.ndarray],
    truth: Sequence[np.ndarray],
    minimum_iou: float,
) -> list[tuple[int, int, float]]:
    candidates = [
        (-mask_iou(predicted_mask, truth_mask), prediction_index, truth_index)
        for prediction_index, predicted_mask in enumerate(predicted)
        for truth_index, truth_mask in enumerate(truth)
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


def _empty_counts() -> dict[str, Any]:
    return {
        "pixel": {name: {"tp": 0, "fp": 0, "fn": 0} for name in CLASS_IDS},
        "instance": {name: {"tp": 0, "fp": 0, "fn": 0} for name in CLASS_IDS},
        "eligible_weed_track": {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "ignored_ineligible_predictions": 0,
        },
        "action": {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "attempted_fire_events": 0,
            "crop_hits": 0,
            "duplicate_fire_events": 0,
            "ignored_ineligible_weed_hits": 0,
            "crop_vetoed_observations": 0,
            "qualifying_weed_observations": 0,
        },
        "size_strata": {
            name: {"eligible_gt_tracks": 0, "matched_tracks": 0, "action_hits": 0}
            for name in ("small", "medium", "large")
        },
    }


def _add_pr_counts(target: dict[str, int], *, tp: int, fp: int, fn: int) -> None:
    target["tp"] += int(tp)
    target["fp"] += int(fp)
    target["fn"] += int(fn)


def _track_mask_by_id(
    sequence: SequenceRecord,
) -> tuple[dict[str, dict[int, np.ndarray]], dict[str, TrackLabel]]:
    masks: dict[str, dict[int, np.ndarray]] = defaultdict(dict)
    catalog: dict[str, TrackLabel] = {}
    for frame in sequence.frames:
        _, track_mask, labels = _truth_for_frame(frame)
        for mask_id, label in labels.items():
            masks[label.track_id][frame.frame_index] = track_mask == mask_id
            prior = catalog.get(label.track_id)
            if prior is None or label.visible_fraction > prior.visible_fraction:
                catalog[label.track_id] = label
    return masks, catalog


def _predicted_track_masks(
    prediction: PredictionSequence,
    threshold: float,
) -> tuple[dict[str, dict[int, np.ndarray]], dict[str, list[Detection]]]:
    masks: dict[str, dict[int, np.ndarray]] = defaultdict(dict)
    observations: dict[str, list[Detection]] = defaultdict(list)
    for frame_prediction in prediction.frames:
        for detection in frame_prediction.detections:
            if detection.class_name != "weed" or detection.confidence < threshold:
                continue
            assert detection.predicted_track_id is not None
            masks[detection.predicted_track_id][frame_prediction.frame.frame_index] = detection.mask
            observations[detection.predicted_track_id].append(detection)
    return masks, observations


def spatiotemporal_iou(
    predicted: Mapping[int, np.ndarray],
    truth: Mapping[int, np.ndarray],
) -> float:
    intersection = 0
    union = 0
    for frame_index in sorted(set(predicted) | set(truth)):
        if frame_index in predicted and frame_index in truth:
            intersection += int(np.logical_and(predicted[frame_index], truth[frame_index]).sum())
            union += int(np.logical_or(predicted[frame_index], truth[frame_index]).sum())
        elif frame_index in predicted:
            union += int(predicted[frame_index].sum())
        else:
            union += int(truth[frame_index].sum())
    return intersection / union if union else 0.0


def evaluate_prediction_sequence(
    prediction: PredictionSequence,
    config: Mapping[str, Any],
    threshold: float,
) -> tuple[dict[str, Any], list[ActionEvent], dict[str, Any]]:
    counts = _empty_counts()
    instance_threshold = float(config["ground_truth"]["instance_match_iou"])
    crop_threshold = float(config["temporal_action"]["predicted_crop_veto_confidence"])
    semantic_ids = config["source"]["v12_smoke"]["semantic_ids"]
    semantic_by_class = {"weed": int(semantic_ids["weed"]), "crop": int(semantic_ids["crop"])}

    for frame_prediction in prediction.frames:
        semantic, track_mask, labels = _truth_for_frame(frame_prediction.frame)
        shape = semantic.shape
        for class_name in CLASS_IDS:
            confidence_threshold = threshold if class_name == "weed" else crop_threshold
            detections = [
                item
                for item in frame_prediction.detections
                if item.class_name == class_name and item.confidence >= confidence_threshold
            ]
            predicted_union = np.zeros(shape, dtype=bool)
            for detection in detections:
                predicted_union |= detection.mask
            truth_union = semantic == semantic_by_class[class_name]
            pixel = counts["pixel"][class_name]
            pixel["tp"] += int(np.logical_and(predicted_union, truth_union).sum())
            pixel["fp"] += int(np.logical_and(predicted_union, ~truth_union).sum())
            pixel["fn"] += int(np.logical_and(~predicted_union, truth_union).sum())
            truth_masks = [
                track_mask == mask_id
                for mask_id, label in sorted(labels.items())
                if label.class_name == class_name
            ]
            matches = greedy_mask_matches(
                [item.mask for item in detections], truth_masks, instance_threshold
            )
            _add_pr_counts(
                counts["instance"][class_name],
                tp=len(matches),
                fp=len(detections) - len(matches),
                fn=len(truth_masks) - len(matches),
            )

    gt_masks, gt_catalog = _track_mask_by_id(prediction.sequence)
    all_predicted_masks, all_predicted_observations = _predicted_track_masks(
        prediction, threshold
    )
    minimum_observations = int(config["tracking"]["minimum_track_observations"])
    short_predicted_ids = sorted(
        track_id
        for track_id, masks in all_predicted_masks.items()
        if len(masks) < minimum_observations
    )
    predicted_masks = {
        track_id: masks
        for track_id, masks in all_predicted_masks.items()
        if len(masks) >= minimum_observations
    }
    predicted_observations = {
        track_id: items
        for track_id, items in all_predicted_observations.items()
        if track_id in predicted_masks
    }
    eligible_ids = sorted(
        track_id for track_id, label in gt_catalog.items() if is_eligible_weed(label, config)
    )
    ineligible_ids = sorted(
        track_id
        for track_id, label in gt_catalog.items()
        if label.class_name == "weed" and track_id not in eligible_ids
    )
    predicted_ids = sorted(predicted_masks)
    match_threshold = float(config["tracking"]["eligible_track_match_iou"])
    eligible_iou_by_predicted = {
        predicted_id: {
            gt_id: spatiotemporal_iou(predicted_masks[predicted_id], gt_masks[gt_id])
            for gt_id in eligible_ids
        }
        for predicted_id in predicted_ids
    }
    ineligible_iou_by_predicted = {
        predicted_id: {
            gt_id: spatiotemporal_iou(predicted_masks[predicted_id], gt_masks[gt_id])
            for gt_id in ineligible_ids
        }
        for predicted_id in predicted_ids
    }
    candidates = [
        (
            -eligible_iou_by_predicted[predicted_id][gt_id],
            predicted_id,
            gt_id,
        )
        for predicted_id in predicted_ids
        for gt_id in eligible_ids
    ]
    candidates.sort()
    matched_predicted: set[str] = set()
    matched_gt: set[str] = set()
    track_matches: list[dict[str, Any]] = []
    for negative_iou, predicted_id, gt_id in candidates:
        overlap = -negative_iou
        if overlap < match_threshold:
            break
        if predicted_id in matched_predicted or gt_id in matched_gt:
            continue
        matched_predicted.add(predicted_id)
        matched_gt.add(gt_id)
        track_matches.append(
            {"predicted_track_id": predicted_id, "gt_track_id": gt_id, "iou": overlap}
        )
    ignored_predictions = {
        predicted_id
        for predicted_id in predicted_ids
        if predicted_id not in matched_predicted
        and any(
            ineligible_iou_by_predicted[predicted_id][gt_id] >= match_threshold
            for gt_id in ineligible_ids
        )
    }
    track_counts = counts["eligible_weed_track"]
    track_counts["tp"] = len(matched_gt)
    track_counts["fp"] = len(predicted_ids) - len(matched_predicted) - len(ignored_predictions)
    track_counts["fn"] = len(eligible_ids) - len(matched_gt)
    track_counts["ignored_ineligible_predictions"] = len(ignored_predictions)
    for gt_id in eligible_ids:
        stratum = gt_catalog[gt_id].size_stratum
        if stratum in counts["size_strata"]:
            counts["size_strata"][stratum]["eligible_gt_tracks"] += 1
            if gt_id in matched_gt:
                counts["size_strata"][stratum]["matched_tracks"] += 1

    matched_gt_by_predicted = {
        row["predicted_track_id"]: row["gt_track_id"] for row in track_matches
    }
    matched_predicted_by_gt = {
        row["gt_track_id"]: row["predicted_track_id"] for row in track_matches
    }

    def ranked_candidates(scores: Mapping[str, float]) -> list[dict[str, Any]]:
        return [
            {"track_id": track_id, "spatiotemporal_mask_iou": float(score)}
            for track_id, score in sorted(
                scores.items(), key=lambda item: (-float(item[1]), item[0])
            )[:5]
        ]

    predicted_track_diagnostics: list[dict[str, Any]] = []
    for predicted_id in predicted_ids:
        eligible_candidates = ranked_candidates(
            eligible_iou_by_predicted[predicted_id]
        )
        ineligible_candidates = ranked_candidates(
            ineligible_iou_by_predicted[predicted_id]
        )
        if predicted_id in matched_predicted:
            disposition = "matched_eligible_gt_track"
            rejection_reason = None
        elif predicted_id in ignored_predictions:
            disposition = "ignored_ineligible_gt_overlap"
            rejection_reason = "best_ineligible_gt_iou_meets_match_threshold"
        elif not eligible_ids:
            disposition = "false_positive_track"
            rejection_reason = "no_eligible_gt_tracks_in_sequence"
        elif not eligible_candidates or float(
            eligible_candidates[0]["spatiotemporal_mask_iou"]
        ) < match_threshold:
            disposition = "false_positive_track"
            rejection_reason = "best_eligible_gt_iou_below_frozen_threshold"
        else:
            disposition = "false_positive_track"
            rejection_reason = "one_to_one_match_conflict"
        observations = predicted_observations[predicted_id]
        predicted_track_diagnostics.append(
            {
                "predicted_track_id": predicted_id,
                "observation_count": len(predicted_masks[predicted_id]),
                "frame_indices": sorted(predicted_masks[predicted_id]),
                "confidence_min": min(item.confidence for item in observations),
                "confidence_mean": statistics.fmean(
                    item.confidence for item in observations
                ),
                "confidence_max": max(item.confidence for item in observations),
                "disposition": disposition,
                "rejection_reason": rejection_reason,
                "matched_gt_track_id": matched_gt_by_predicted.get(predicted_id),
                "top_eligible_candidates": eligible_candidates,
                "top_ineligible_candidates": ineligible_candidates,
            }
        )
    for predicted_id in short_predicted_ids:
        observations = all_predicted_observations[predicted_id]
        eligible_candidates = ranked_candidates(
            {
                gt_id: spatiotemporal_iou(
                    all_predicted_masks[predicted_id], gt_masks[gt_id]
                )
                for gt_id in eligible_ids
            }
        )
        predicted_track_diagnostics.append(
            {
                "predicted_track_id": predicted_id,
                "observation_count": len(all_predicted_masks[predicted_id]),
                "frame_indices": sorted(all_predicted_masks[predicted_id]),
                "confidence_min": min(item.confidence for item in observations),
                "confidence_mean": statistics.fmean(
                    item.confidence for item in observations
                ),
                "confidence_max": max(item.confidence for item in observations),
                "disposition": "excluded_before_track_scoring",
                "rejection_reason": "insufficient_observations",
                "minimum_observations_required": minimum_observations,
                "matched_gt_track_id": None,
                "top_eligible_candidates": eligible_candidates,
                "top_ineligible_candidates": [],
            }
        )
    predicted_track_diagnostics.sort(key=lambda row: row["predicted_track_id"])

    eligible_gt_track_diagnostics: list[dict[str, Any]] = []
    for gt_id in eligible_ids:
        candidates_for_gt = ranked_candidates(
            {
                predicted_id: eligible_iou_by_predicted[predicted_id][gt_id]
                for predicted_id in predicted_ids
            }
        )
        if gt_id in matched_gt:
            disposition = "matched"
            rejection_reason = None
        elif not candidates_for_gt:
            disposition = "false_negative_track"
            rejection_reason = "no_qualifying_predicted_track"
        elif float(candidates_for_gt[0]["spatiotemporal_mask_iou"]) < match_threshold:
            disposition = "false_negative_track"
            rejection_reason = "best_predicted_iou_below_frozen_threshold"
        else:
            disposition = "false_negative_track"
            rejection_reason = "one_to_one_match_conflict"
        label = gt_catalog[gt_id]
        eligible_gt_track_diagnostics.append(
            {
                "gt_track_id": gt_id,
                "canopy_span_mm": label.canopy_span_mm,
                "visible_fraction": label.visible_fraction,
                "partial": label.partial,
                "size_stratum": label.size_stratum,
                "disposition": disposition,
                "rejection_reason": rejection_reason,
                "matched_predicted_track_id": matched_predicted_by_gt.get(gt_id),
                "top_predicted_candidates": candidates_for_gt,
            }
        )

    action_config = config["temporal_action"]
    minimum_confirmations = int(action_config["minimum_confirmations"])
    window_frames = int(action_config["preferred_window_frames"])
    histories: dict[str, list[tuple[int, Detection]]] = defaultdict(list)
    fired: set[str] = set()
    raw_events: list[tuple[PredictionFrame, Detection, int]] = []
    for frame_prediction in sorted(
        prediction.frames, key=lambda item: item.frame.frame_index
    ):
        frame_index = frame_prediction.frame.frame_index
        crop_masks = [
            item.mask
            for item in frame_prediction.detections
            if item.class_name == "crop" and item.confidence >= crop_threshold
        ]
        for detection in frame_prediction.detections:
            if detection.class_name != "weed" or detection.confidence < threshold:
                continue
            x, y = detection.action_point_xy
            if any(bool(mask[y, x]) for mask in crop_masks):
                counts["action"]["crop_vetoed_observations"] += 1
                continue
            counts["action"]["qualifying_weed_observations"] += 1
            assert detection.predicted_track_id is not None
            history = histories[detection.predicted_track_id]
            history.append((frame_index, detection))
            window_start = frame_index - window_frames + 1
            history[:] = [item for item in history if item[0] >= window_start]
            if detection.predicted_track_id not in fired and len(history) >= minimum_confirmations:
                fired.add(detection.predicted_track_id)
                raw_events.append((frame_prediction, detection, len(history)))

    matched_action_gt: set[str] = set()
    events: list[ActionEvent] = []
    for frame_prediction, detection, confirmations in raw_events:
        semantic, track_mask, labels = _truth_for_frame(frame_prediction.frame)
        x, y = detection.action_point_xy
        mask_id = int(track_mask[y, x])
        label = labels.get(mask_id)
        matched_id: str | None = None
        if int(semantic[y, x]) == semantic_by_class["crop"]:
            disposition = "crop_hit_false_positive"
            counts["action"]["crop_hits"] += 1
            counts["action"]["fp"] += 1
        elif label is not None and label.class_name == "weed" and is_eligible_weed(label, config):
            matched_id = label.track_id
            if label.track_id in matched_action_gt:
                disposition = "duplicate_fire_false_positive"
                counts["action"]["duplicate_fire_events"] += 1
                counts["action"]["fp"] += 1
            else:
                disposition = "eligible_weed_true_positive"
                matched_action_gt.add(label.track_id)
                counts["action"]["tp"] += 1
        elif label is not None and label.class_name == "weed" and not label.partial:
            disposition = "ignored_ineligible_weed_hit"
            counts["action"]["ignored_ineligible_weed_hits"] += 1
        else:
            disposition = "background_or_partial_false_positive"
            counts["action"]["fp"] += 1
        counts["action"]["attempted_fire_events"] += 1
        events.append(
            ActionEvent(
                sequence_id=prediction.sequence.sequence_id,
                pair_id=prediction.sequence.pair_id,
                condition=prediction.sequence.condition,
                frame_id=frame_prediction.frame.frame_id,
                frame_index=frame_prediction.frame.frame_index,
                predicted_track_id=str(detection.predicted_track_id),
                confidence=detection.confidence,
                action_point_xy=detection.action_point_xy,
                confirmations_in_window=confirmations,
                disposition=disposition,
                matched_gt_track_id=matched_id,
            )
        )
    counts["action"]["fn"] = len(eligible_ids) - len(matched_action_gt)
    for gt_id in matched_action_gt:
        stratum = gt_catalog[gt_id].size_stratum
        if stratum in counts["size_strata"]:
            counts["size_strata"][stratum]["action_hits"] += 1
    audit = {
        "sequence_id": prediction.sequence.sequence_id,
        "pair_id": prediction.sequence.pair_id,
        "condition": prediction.sequence.condition,
        "threshold": threshold,
        "eligible_track_metric_definition": {
            "prediction_requirement": (
                f"at least {minimum_observations} above-threshold observations "
                "on one associated predicted weed track"
            ),
            "matching": "one_to_one_spatiotemporal_mask_iou",
            "minimum_iou": match_threshold,
            "ineligible_gt_overlap_policy": "ignored_when_iou_meets_same_threshold",
        },
        "eligible_gt_track_ids": eligible_ids,
        "ineligible_gt_weed_track_ids": ineligible_ids,
        "track_matches": track_matches,
        "ignored_predicted_track_ids": sorted(ignored_predictions),
        "predicted_track_diagnostics": predicted_track_diagnostics,
        "eligible_gt_track_diagnostics": eligible_gt_track_diagnostics,
        "action_events": [
            {**asdict(item), "action_point_xy": list(item.action_point_xy)} for item in events
        ],
    }
    return counts, events, audit


def add_counts(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for family in ("pixel", "instance"):
        for class_name in CLASS_IDS:
            for key in ("tp", "fp", "fn"):
                target[family][class_name][key] += int(source[family][class_name][key])
    for key in ("tp", "fp", "fn", "ignored_ineligible_predictions"):
        target["eligible_weed_track"][key] += int(source["eligible_weed_track"][key])
    for key in target["action"]:
        target["action"][key] += int(source["action"][key])
    for stratum in target["size_strata"]:
        for key in target["size_strata"][stratum]:
            target["size_strata"][stratum][key] += int(
                source["size_strata"][stratum][key]
            )


def aggregate_counts(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    output = _empty_counts()
    for item in items:
        add_counts(output, item)
    return output


def safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson_interval(
    successes: int,
    trials: int,
    confidence_level: float = 0.95,
) -> dict[str, Any] | None:
    if trials == 0:
        return None
    if successes < 0 or successes > trials:
        raise ContractError("Wilson interval successes must lie inside [0, trials]")
    z = statistics.NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (proportion + z2 / (2.0 * trials)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / trials + z2 / (4.0 * trials * trials)
        )
        / denominator
    )
    return {
        "method": "wilson",
        "confidence_level": confidence_level,
        "lower": max(0.0, center - radius),
        "upper": min(1.0, center + radius),
    }


def prf_metrics(
    counts: Mapping[str, Any],
    *,
    confidence_level: float,
) -> dict[str, Any]:
    tp, fp, fn = int(counts["tp"]), int(counts["fp"]), int(counts["fn"])
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "precision_ci": wilson_interval(tp, tp + fp, confidence_level),
        "recall": recall,
        "recall_ci": wilson_interval(tp, tp + fn, confidence_level),
        "f1": f1,
    }


def summary_from_counts(
    counts: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    confidence = float(config["uncertainty"]["confidence_level"])
    pixel = {
        class_name: prf_metrics(counts["pixel"][class_name], confidence_level=confidence)
        for class_name in CLASS_IDS
    }
    instance = {
        class_name: prf_metrics(
            counts["instance"][class_name], confidence_level=confidence
        )
        for class_name in CLASS_IDS
    }
    track = prf_metrics(counts["eligible_weed_track"], confidence_level=confidence)
    track["definition"] = (
        "Predicted weed tracks with the frozen minimum observation count, matched "
        "one-to-one to eligible GT weed tracks by frozen spatiotemporal mask IoU."
    )
    track["ignored_ineligible_predictions"] = int(
        counts["eligible_weed_track"]["ignored_ineligible_predictions"]
    )
    action = prf_metrics(counts["action"], confidence_level=confidence)
    action["definition"] = (
        "Confirmed fire events scored by action-point hit against one unmatched "
        "eligible GT weed track, with crop precedence and duplicate-fire exposure."
    )
    attempted = int(counts["action"]["attempted_fire_events"])
    crop_hits = int(counts["action"]["crop_hits"])
    duplicates = int(counts["action"]["duplicate_fire_events"])
    action.update(
        {
            "attempted_fire_events": attempted,
            "crop_hits": crop_hits,
            "crop_hit_rate": safe_rate(crop_hits, attempted),
            "crop_hit_rate_ci": wilson_interval(crop_hits, attempted, confidence),
            "duplicate_fire_events": duplicates,
            "duplicate_fire_rate": safe_rate(duplicates, attempted),
            "duplicate_fire_rate_ci": wilson_interval(duplicates, attempted, confidence),
            "ignored_ineligible_weed_hits": int(
                counts["action"]["ignored_ineligible_weed_hits"]
            ),
            "crop_vetoed_observations": int(
                counts["action"]["crop_vetoed_observations"]
            ),
            "qualifying_weed_observations": int(
                counts["action"]["qualifying_weed_observations"]
            ),
        }
    )
    size_output: dict[str, Any] = {}
    for stratum, item in counts["size_strata"].items():
        eligible = int(item["eligible_gt_tracks"])
        matched = int(item["matched_tracks"])
        action_hits = int(item["action_hits"])
        size_output[stratum] = {
            "metric_scope": "gt_conditioned_recall_only",
            "eligible_gt_tracks": eligible,
            "matched_tracks": matched,
            "track_recall": safe_rate(matched, eligible),
            "track_recall_ci": wilson_interval(matched, eligible, confidence),
            "action_hits": action_hits,
            "action_recall": safe_rate(action_hits, eligible),
            "action_recall_ci": wilson_interval(action_hits, eligible, confidence),
        }
    return {
        "pixel": pixel,
        "instance": instance,
        "eligible_weed_track": track,
        "action": action,
        "size_strata": size_output,
    }


def _metric_value(counts: Mapping[str, Any], metric_key: str) -> float | None:
    if metric_key.startswith("pixel_"):
        _, class_name, key = metric_key.split("_", 2)
        metric = prf_metrics(counts["pixel"][class_name], confidence_level=0.95)
        return metric[key]
    if metric_key.startswith("instance_"):
        _, class_name, key = metric_key.split("_", 2)
        metric = prf_metrics(counts["instance"][class_name], confidence_level=0.95)
        return metric[key]
    if metric_key.startswith("track_"):
        key = metric_key.removeprefix("track_")
        metric = prf_metrics(counts["eligible_weed_track"], confidence_level=0.95)
        return metric[key]
    if metric_key.startswith("action_"):
        key = metric_key.removeprefix("action_")
        metric = prf_metrics(counts["action"], confidence_level=0.95)
        return metric[key]
    raise ContractError(f"Unknown bootstrap metric key: {metric_key}")


def bootstrap_metric_interval(
    counts_by_unit: Mapping[str, Mapping[str, Any]],
    metric_key: str,
    *,
    resamples: int,
    seed: int,
    confidence_level: float,
) -> dict[str, Any] | None:
    unit_ids = sorted(counts_by_unit)
    if not unit_ids:
        return None
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(resamples):
        sampled = rng.choice(unit_ids, size=len(unit_ids), replace=True)
        combined = aggregate_counts(counts_by_unit[str(unit_id)] for unit_id in sampled)
        value = _metric_value(combined, metric_key)
        if value is not None and math.isfinite(float(value)):
            values.append(float(value))
    if not values:
        return None
    alpha = (1.0 - confidence_level) / 2.0
    return {
        "method": "matched_scene_pair_cluster_percentile_bootstrap",
        "confidence_level": confidence_level,
        "resamples_requested": resamples,
        "resamples_defined": len(values),
        "unit_count": len(unit_ids),
        "seed": seed,
        "lower": float(np.quantile(values, alpha)),
        "upper": float(np.quantile(values, 1.0 - alpha)),
    }


def add_bootstrap_intervals(
    summary: dict[str, Any],
    counts_by_pair: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    seed_offset: int,
) -> None:
    uncertainty = config["uncertainty"]
    resamples = int(uncertainty["bootstrap_resamples"])
    confidence = float(uncertainty["confidence_level"])
    seed = int(uncertainty["seed"]) + seed_offset
    targets = (
        ("pixel_weed_f1", summary["pixel"]["weed"]),
        ("pixel_crop_f1", summary["pixel"]["crop"]),
        ("instance_weed_f1", summary["instance"]["weed"]),
        ("instance_crop_f1", summary["instance"]["crop"]),
        ("track_f1", summary["eligible_weed_track"]),
        ("action_f1", summary["action"]),
    )
    for index, (key, destination) in enumerate(targets):
        destination["f1_cluster_bootstrap_ci"] = bootstrap_metric_interval(
            counts_by_pair,
            key,
            resamples=resamples,
            seed=seed + index,
            confidence_level=confidence,
        )


def evaluate_prediction_set(
    predictions: Mapping[str, PredictionSequence],
    config: Mapping[str, Any],
    threshold: float,
    *,
    include_uncertainty: bool,
) -> dict[str, Any]:
    counts_by_sequence: dict[str, dict[str, Any]] = {}
    audits: dict[str, dict[str, Any]] = {}
    events: list[ActionEvent] = []
    for sequence_id, prediction in sorted(predictions.items()):
        counts, sequence_events, audit = evaluate_prediction_sequence(
            prediction, config, threshold
        )
        counts_by_sequence[sequence_id] = counts
        audits[sequence_id] = audit
        events.extend(sequence_events)
    pooled_counts = aggregate_counts(counts_by_sequence.values())
    summary = summary_from_counts(pooled_counts, config)
    if include_uncertainty:
        counts_by_pair: dict[str, dict[str, Any]] = {}
        for sequence_id, counts in counts_by_sequence.items():
            pair_id = predictions[sequence_id].sequence.pair_id
            if pair_id in counts_by_pair:
                raise ContractError("Uncertainty unit contains duplicate sequence for a condition")
            counts_by_pair[pair_id] = counts
        condition_index = list(config["conditions"]["ordered"]).index(
            next(iter(predictions.values())).sequence.condition
        ) if predictions else 0
        add_bootstrap_intervals(
            summary,
            counts_by_pair,
            config,
            seed_offset=condition_index * 100,
        )
    return {
        "threshold": threshold,
        "sequence_count": len(predictions),
        "frame_count": sum(len(item.frames) for item in predictions.values()),
        "counts": pooled_counts,
        "metrics": summary,
        "per_sequence_counts": counts_by_sequence,
        "sequence_audit": audits,
        "action_events": [
            {**asdict(item), "action_point_xy": list(item.action_point_xy)} for item in events
        ],
    }


def _defined(value: Any, fallback: float = -1.0) -> float:
    return fallback if value is None else float(value)


def select_calibration_threshold(
    curve: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    calibration = config["calibration"]

    def feasible(row: Mapping[str, Any]) -> bool:
        track = row["metrics"]["eligible_weed_track"]
        action = row["metrics"]["action"]
        return bool(
            track["precision"] is not None
            and float(track["precision"])
            >= float(calibration["minimum_eligible_track_precision"])
            and action["crop_hit_rate"] is not None
            and float(action["crop_hit_rate"])
            <= float(calibration["maximum_crop_hit_rate"])
            and action["duplicate_fire_rate"] is not None
            and float(action["duplicate_fire_rate"])
            <= float(calibration["maximum_duplicate_fire_rate"])
        )

    feasible_rows = [row for row in curve if feasible(row)]
    if feasible_rows:
        selected = max(
            feasible_rows,
            key=lambda row: (
                _defined(row["metrics"]["eligible_weed_track"]["recall"]),
                _defined(row["metrics"]["eligible_weed_track"]["f1"]),
                _defined(row["metrics"]["eligible_weed_track"]["precision"]),
                float(row["threshold"]),
            ),
        )
        status = "calibration_safety_feasible"
        constraints_passed = True
    else:
        selected = max(
            curve,
            key=lambda row: (
                _defined(row["metrics"]["eligible_weed_track"]["f1"]),
                _defined(row["metrics"]["eligible_weed_track"]["precision"]),
                _defined(row["metrics"]["eligible_weed_track"]["recall"]),
                float(row["threshold"]),
            ),
        )
        status = "no_calibration_safety_feasible_threshold_diagnostic_fallback"
        constraints_passed = False
    return {
        "status": status,
        "constraints_passed": constraints_passed,
        "threshold": float(selected["threshold"]),
        "source_split": config["source"]["calibration_split"],
        "source_conditions": list(config["conditions"]["ordered"]),
        "shared_across_conditions": True,
        "test_accessed": False,
        "selection_rule": calibration["selection"],
        "fallback_rule": calibration["fallback"],
        "selected_metrics": selected["metrics"],
    }


def calibration_curve(
    predictions: Mapping[str, PredictionSequence],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if any(
        item.sequence.split != config["source"]["calibration_split"]
        for item in predictions.values()
    ):
        raise ContractError("Calibration curve received a non-calibration sequence")
    curve: list[dict[str, Any]] = []
    for threshold in threshold_grid(config):
        evaluation = evaluate_prediction_set(
            predictions,
            config,
            threshold,
            include_uncertainty=False,
        )
        curve.append(
            {
                "threshold": threshold,
                "metrics": evaluation["metrics"],
                "pooled_counts": evaluation["counts"],
            }
        )
    return curve, select_calibration_threshold(curve, config)


def paired_delta_interval(
    ideal_by_pair: Mapping[str, Mapping[str, Any]],
    degraded_by_pair: Mapping[str, Mapping[str, Any]],
    metric_key: str,
    config: Mapping[str, Any],
    *,
    seed_offset: int,
) -> dict[str, Any]:
    pair_ids = sorted(set(ideal_by_pair) & set(degraded_by_pair))
    if set(ideal_by_pair) != set(degraded_by_pair) or not pair_ids:
        raise ContractError("Paired delta requires exactly matched ideal/degraded pair IDs")
    uncertainty = config["uncertainty"]
    resamples = int(uncertainty["bootstrap_resamples"])
    confidence = float(uncertainty["confidence_level"])
    rng = np.random.default_rng(int(uncertainty["seed"]) + seed_offset)
    deltas: list[float] = []
    for _ in range(resamples):
        sampled = rng.choice(pair_ids, size=len(pair_ids), replace=True)
        ideal = aggregate_counts(ideal_by_pair[str(pair_id)] for pair_id in sampled)
        degraded = aggregate_counts(degraded_by_pair[str(pair_id)] for pair_id in sampled)
        ideal_value = _metric_value(ideal, metric_key)
        degraded_value = _metric_value(degraded, metric_key)
        if ideal_value is not None and degraded_value is not None:
            deltas.append(float(ideal_value) - float(degraded_value))
    alpha = (1.0 - confidence) / 2.0
    ideal_all = aggregate_counts(ideal_by_pair.values())
    degraded_all = aggregate_counts(degraded_by_pair.values())
    ideal_value = _metric_value(ideal_all, metric_key)
    degraded_value = _metric_value(degraded_all, metric_key)
    return {
        "definition": "ideal_minus_degraded",
        "ideal": ideal_value,
        "degraded": degraded_value,
        "delta": None
        if ideal_value is None or degraded_value is None
        else float(ideal_value) - float(degraded_value),
        "ci": None
        if not deltas
        else {
            "method": "matched_scene_pair_cluster_percentile_bootstrap",
            "confidence_level": confidence,
            "resamples_requested": resamples,
            "resamples_defined": len(deltas),
            "unit_count": len(pair_ids),
            "seed": int(uncertainty["seed"]) + seed_offset,
            "lower": float(np.quantile(deltas, alpha)),
            "upper": float(np.quantile(deltas, 1.0 - alpha)),
        },
    }


def paired_condition_deltas(
    condition_results: Mapping[str, Mapping[str, Any]],
    predictions_by_condition: Mapping[str, Mapping[str, PredictionSequence]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    ideal_counts = {
        predictions_by_condition["ideal"][sequence_id].sequence.pair_id: counts
        for sequence_id, counts in condition_results["ideal"]["per_sequence_counts"].items()
    }
    degraded_counts = {
        predictions_by_condition["degraded"][sequence_id].sequence.pair_id: counts
        for sequence_id, counts in condition_results["degraded"]["per_sequence_counts"].items()
    }
    metrics = (
        "pixel_weed_f1",
        "instance_weed_f1",
        "track_f1",
        "action_f1",
    )
    return {
        metric: paired_delta_interval(
            ideal_counts,
            degraded_counts,
            metric,
            config,
            seed_offset=500 + index,
        )
        for index, metric in enumerate(metrics)
    }


def assess_descriptive_targets(
    condition_results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    targets = config["descriptive_targets"]
    ideal_target = float(targets["ideal_minimum"])
    degraded_reference = float(targets["degraded_reference"])
    tolerance = float(targets["degraded_near_absolute_tolerance"])
    degraded_lower = degraded_reference - tolerance
    degraded_upper = degraded_reference + tolerance
    ideal_metric = condition_results["ideal"]["metrics"]["eligible_weed_track"]
    degraded_metric = condition_results["degraded"]["metrics"][
        "eligible_weed_track"
    ]
    ideal_value = ideal_metric["f1"]
    degraded_value = degraded_metric["f1"]
    ideal_met = ideal_value is not None and float(ideal_value) >= ideal_target
    degraded_near = (
        degraded_value is not None
        and degraded_lower <= float(degraded_value) <= degraded_upper
    )

    def interval_supports(
        interval: Mapping[str, Any] | None,
        lower: float,
        upper: float,
    ) -> bool | None:
        if interval is None:
            return None
        return bool(
            float(interval["upper"]) >= lower
            and float(interval["lower"]) <= upper
        )

    if ideal_met and degraded_near:
        conclusion = "both_descriptive_targets_met"
    elif ideal_met:
        conclusion = "ideal_met_degraded_reference_not_met"
    elif degraded_near:
        conclusion = "ideal_not_met_degraded_reference_met"
    else:
        conclusion = "neither_descriptive_target_met"
    return {
        "metric": str(targets["metric"]),
        "metric_definition": ideal_metric["definition"],
        "reporting_only": True,
        "used_in_threshold_selection": False,
        "used_in_model_or_degradation_tuning": False,
        "ideal": {
            "minimum": ideal_target,
            "observed": ideal_value,
            "reaches_minimum": ideal_met,
            "shortfall": None
            if ideal_value is None
            else max(0.0, ideal_target - float(ideal_value)),
            "f1_cluster_bootstrap_ci": ideal_metric.get(
                "f1_cluster_bootstrap_ci"
            ),
            "ci_intersects_passing_region": interval_supports(
                ideal_metric.get("f1_cluster_bootstrap_ci"), ideal_target, 1.0
            ),
        },
        "degraded": {
            "reference": degraded_reference,
            "near_absolute_tolerance": tolerance,
            "near_range_inclusive": [degraded_lower, degraded_upper],
            "observed": degraded_value,
            "within_near_range": degraded_near,
            "absolute_distance_from_reference": None
            if degraded_value is None
            else abs(float(degraded_value) - degraded_reference),
            "f1_cluster_bootstrap_ci": degraded_metric.get(
                "f1_cluster_bootstrap_ci"
            ),
            "ci_intersects_near_range": interval_supports(
                degraded_metric.get("f1_cluster_bootstrap_ci"),
                degraded_lower,
                degraded_upper,
            ),
        },
        "supplemental_confirmed_action_track_f1": {
            condition: condition_results[condition]["metrics"]["action"]["f1"]
            for condition in ("ideal", "degraded")
        },
        "conclusion": conclusion,
        "synthetic_field_claim_allowed": False,
    }


def _blend_mask(image: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int], alpha: float) -> None:
    if not np.any(mask):
        return
    colour_array = np.asarray(colour, dtype=np.float32)
    image[mask] = np.clip(
        image[mask].astype(np.float32) * (1.0 - alpha) + colour_array * alpha,
        0,
        255,
    ).astype(np.uint8)


def render_overlay_frame(
    prediction: PredictionFrame,
    *,
    condition: str,
    threshold: float,
    events: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> np.ndarray:
    image = cv2.imread(str(prediction.frame.image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ContractError(f"Cannot render overlay for {prediction.frame.frame_id}")
    overlay = image.copy()
    alpha = float(config["video"]["overlay_alpha"])
    semantic, _, _ = _truth_for_frame(prediction.frame)
    semantic_ids = config["source"]["v12_smoke"]["semantic_ids"]
    if bool(config["video"]["show_ground_truth"]):
        for class_name, colour in (("weed", (60, 210, 60)), ("crop", (255, 210, 40))):
            mask = (semantic == int(semantic_ids[class_name])).astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(overlay, contours, -1, colour, 2, lineType=cv2.LINE_AA)
    if bool(config["video"]["show_predictions"]):
        crop_threshold = float(config["temporal_action"]["predicted_crop_veto_confidence"])
        for detection in prediction.detections:
            minimum = threshold if detection.class_name == "weed" else crop_threshold
            if detection.confidence < minimum:
                continue
            colour = (210, 60, 210) if detection.class_name == "weed" else (40, 140, 255)
            _blend_mask(overlay, detection.mask, colour, alpha)
            x1, y1, x2, y2 = detection.bbox_xyxy
            cv2.rectangle(overlay, (x1, y1), (x2, y2), colour, 2, cv2.LINE_AA)
            label = f"P {detection.class_name} {detection.confidence:.2f} {detection.predicted_track_id}"
            cv2.putText(
                overlay,
                label,
                (x1, max(18, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                colour,
                1,
                cv2.LINE_AA,
            )
    if bool(config["video"]["show_action_events"]):
        for event in events:
            x, y = (int(value) for value in event["action_point_xy"])
            disposition = str(event["disposition"])
            colour = (0, 255, 0) if disposition == "eligible_weed_true_positive" else (0, 0, 255)
            cv2.drawMarker(
                overlay,
                (x, y),
                colour,
                markerType=cv2.MARKER_CROSS,
                markerSize=32,
                thickness=4,
                line_type=cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                f"FIRE {disposition}",
                (min(x + 12, overlay.shape[1] - 320), max(25, y - 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                colour,
                2,
                cv2.LINE_AA,
            )
    header_height = 104
    canvas = np.zeros((overlay.shape[0] + header_height, overlay.shape[1], 3), dtype=np.uint8)
    canvas[header_height:] = overlay
    cv2.putText(
        canvas,
        f"SYNTHETIC DIAGNOSTIC | {condition.upper()} | shared weed threshold {threshold:.2f}",
        (18, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.70,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        f"pair={prediction.frame.frame_id.rsplit(':frame_', 1)[0]} frame={prediction.frame.frame_index}",
        (18, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (210, 210, 210),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "GT outline: weed green / crop cyan | Prediction: weed magenta / crop orange",
        (18, 88),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (180, 180, 180),
        1,
        cv2.LINE_AA,
    )
    return canvas


def render_overlay_videos(
    predictions_by_condition: Mapping[str, Mapping[str, PredictionSequence]],
    condition_results: Mapping[str, Mapping[str, Any]],
    threshold: float,
    config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    if not bool(config["video"]["enabled"]):
        return {"enabled": False, "reason": "disabled_by_runtime_override"}
    output_dir.mkdir(parents=True, exist_ok=True)
    receipts: dict[str, Any] = {"enabled": True, "conditions": {}}
    codec = str(config["video"]["codec"])
    if len(codec) != 4:
        raise ContractError("Video codec must be a four-character code")
    fps = float(config["video"]["fps"])
    for condition in config["conditions"]["ordered"]:
        predictions = predictions_by_condition[condition]
        event_rows = condition_results[condition]["action_events"]
        events_by_frame: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for event in event_rows:
            events_by_frame[str(event["frame_id"])].append(event)
        rendered_frames: list[np.ndarray] = []
        for prediction_sequence in sorted(
            predictions.values(), key=lambda item: item.sequence.pair_id
        ):
            for frame_prediction in prediction_sequence.frames:
                rendered_frames.append(
                    render_overlay_frame(
                        frame_prediction,
                        condition=condition,
                        threshold=threshold,
                        events=events_by_frame.get(frame_prediction.frame.frame_id, []),
                        config=config,
                    )
                )
        if not rendered_frames:
            raise ContractError(f"No test frames available for {condition} overlay")
        height, width = rendered_frames[0].shape[:2]
        video_path = output_dir / f"{condition}_locked_test_overlay.mp4"
        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*codec),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise ContractError(f"OpenCV could not open video writer for {video_path}")
        for frame in rendered_frames:
            if frame.shape[:2] != (height, width):
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
        writer.release()
        capture = cv2.VideoCapture(str(video_path))
        decoded_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        decoded_fps = float(capture.get(cv2.CAP_PROP_FPS))
        capture.release()
        if decoded_frames != len(rendered_frames) or video_path.stat().st_size == 0:
            raise ContractError(
                f"Overlay verification failed for {condition}: expected {len(rendered_frames)} frames, decoded {decoded_frames}"
            )
        receipts["conditions"][condition] = {
            "path": video_path.relative_to(output_dir.parent).as_posix(),
            "sha256": sha256_file(video_path),
            "bytes": video_path.stat().st_size,
            "frames_written": len(rendered_frames),
            "frames_decoded": decoded_frames,
            "fps_requested": fps,
            "fps_decoded": decoded_fps,
            "width_px": width,
            "height_px": height,
            "codec": codec,
            "readback_verified": True,
        }
    return receipts


def percentile(values: Sequence[float], quantile: float) -> float | None:
    return None if not values else float(np.quantile(np.asarray(values), quantile))


def runtime_summary(
    prediction_sets: Sequence[Mapping[str, PredictionSequence]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[PredictionFrame]] = defaultdict(list)
    for predictions in prediction_sets:
        for prediction in predictions.values():
            grouped[(prediction.sequence.split, prediction.sequence.condition)].extend(
                prediction.frames
            )
    output: dict[str, Any] = {}
    all_frames: list[PredictionFrame] = []
    for (split, condition), frames in sorted(grouped.items()):
        all_frames.extend(frames)
        wall = [item.inference_wall_ms for item in frames]
        output[f"{split}:{condition}"] = {
            "frames": len(frames),
            "wall_ms_total": float(sum(wall)),
            "wall_ms_mean": float(statistics.fmean(wall)),
            "wall_ms_median": float(statistics.median(wall)),
            "wall_ms_p95": percentile(wall, 0.95),
            "fps_from_mean_wall": 1000.0 / statistics.fmean(wall),
            "ultralytics_speed_ms_mean": {
                key: float(
                    statistics.fmean(
                        frame.model_speed_ms[key]
                        for frame in frames
                        if key in frame.model_speed_ms
                    )
                )
                for key in sorted(
                    {key for frame in frames for key in frame.model_speed_ms}
                )
            },
        }
    wall_all = [item.inference_wall_ms for item in all_frames]
    return {
        "scope": "Python/Ultralytics end-to-end predict call with CUDA synchronization when available",
        "warmup_included": True,
        "groups": output,
        "all_frames": {
            "frames": len(all_frames),
            "wall_ms_total": float(sum(wall_all)),
            "wall_ms_mean": float(statistics.fmean(wall_all)) if wall_all else None,
            "wall_ms_p95": percentile(wall_all, 0.95),
            "fps_from_mean_wall": 1000.0 / statistics.fmean(wall_all) if wall_all else None,
        },
    }


def artifact_inventory(root: Path, *, excluded: Iterable[str] = ()) -> list[dict[str, Any]]:
    excluded_set = set(excluded)
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded_set:
            continue
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def environment_receipt() -> dict[str, Any]:
    import torch
    import ultralytics

    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "ultralytics_version": ultralytics.__version__,
        "opencv_version": cv2.__version__,
        "numpy_version": np.__version__,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_name": (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        ),
    }


def _format_metric(value: Any) -> str:
    return "undefined" if value is None else f"{float(value):.4f}"


def write_documentation_summary(
    docs_dir: Path,
    run_dir: Path,
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    if docs_dir.exists():
        raise ContractError(f"Documentation output already exists: {docs_dir}")
    docs_dir.mkdir(parents=True, exist_ok=False)
    test = metrics["locked_test"]
    compact = {
        "schema_version": 1,
        "status": metrics["status"],
        "run_directory": str(run_dir),
        "run_receipt": str(run_dir / "run_receipt.json"),
        "checkpoint_sha256": metrics["checkpoint"]["sha256"],
        "selected_shared_threshold": metrics["calibration"]["selection"]["threshold"],
        "conditions": {
            condition: {
                "pixel": result["metrics"]["pixel"],
                "instance": result["metrics"]["instance"],
                "eligible_weed_track": result["metrics"]["eligible_weed_track"],
                "action": result["metrics"]["action"],
                "size_strata": result["metrics"]["size_strata"],
            }
            for condition, result in test["conditions"].items()
        },
        "paired_deltas": test["paired_deltas"],
        "descriptive_target_assessment": test["descriptive_target_assessment"],
        "runtime": metrics["runtime"],
        "videos": metrics["videos"],
        "decision": metrics["decision"],
        "limitations": metrics["limitations"],
    }
    summary_path = docs_dir / "benchmark_summary.json"
    write_json(summary_path, compact)
    lines = [
        "# Spot-spray simulation video inference smoke benchmark",
        "",
        "This is a checkpoint-bound **synthetic diagnostic**, not field or deployment evidence.",
        "",
        f"- Checkpoint SHA-256: `{metrics['checkpoint']['sha256']}`",
        f"- Shared calibration-only threshold: `{metrics['calibration']['selection']['threshold']:.2f}`",
        f"- Locked-test evaluation count: `{metrics['access_ledger']['locked_test_metric_evaluations']}`",
        f"- Descriptive target outcome: `{test['descriptive_target_assessment']['conclusion']}`",
        "",
        "| condition | weed pixel F1 | weed instance F1 | eligible-track F1 | action F1 | crop-hit | duplicate-fire |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in metrics["conditions_ordered"]:
        result = test["conditions"][condition]["metrics"]
        lines.append(
            "| "
            + " | ".join(
                (
                    condition,
                    _format_metric(result["pixel"]["weed"]["f1"]),
                    _format_metric(result["instance"]["weed"]["f1"]),
                    _format_metric(result["eligible_weed_track"]["f1"]),
                    _format_metric(result["action"]["f1"]),
                    _format_metric(result["action"]["crop_hit_rate"]),
                    _format_metric(result["action"]["duplicate_fire_rate"]),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "The ideal and degraded rows use the same held-out scene pairs and identical ground truth. "
            "The degraded transform was frozen in configuration before inference; no score was tuned toward a target.",
            "",
            "The reporting-only target assessment checks ideal eligible mask-track F1 >= 0.97 and "
            "whether degraded F1 lies in [0.70, 0.80]. These values do not enter threshold selection.",
            "",
            "V12 smoke sequences repeat one static frame three times. Their region IDs are connected-component proxies, "
            "not botanical tracks, and the result has zero weight in any real GO decision.",
            "",
        ]
    )
    readme_path = docs_dir / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "contract": "spot_spray_simulation_video_inference_docs_receipt_v1",
        "run_receipt": str(run_dir / "run_receipt.json"),
        "run_receipt_sha256": sha256_file(run_dir / "run_receipt.json"),
        "artifacts": artifact_inventory(docs_dir, excluded={"release_receipt.json"}),
    }
    receipt_path = docs_dir / "release_receipt.json"
    write_json(receipt_path, receipt)
    return {
        "path": str(docs_dir),
        "summary_sha256": sha256_file(summary_path),
        "readme_sha256": sha256_file(readme_path),
        "receipt_sha256": sha256_file(receipt_path),
    }


def _condition_split(
    predictions: Mapping[str, PredictionSequence],
) -> dict[str, dict[str, PredictionSequence]]:
    output: dict[str, dict[str, PredictionSequence]] = defaultdict(dict)
    for sequence_id, prediction in predictions.items():
        output[prediction.sequence.condition][sequence_id] = prediction
    return dict(output)


def run_benchmark(
    config_path: Path,
    *,
    sequence_manifest: Path | None = None,
    run_name: str | None = None,
    output_root: Path | None = None,
    docs_root: Path | None = None,
    device_override: str | int | None = None,
    video_enabled_override: bool | None = None,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    runtime_overrides: dict[str, Any] = {}
    if device_override is not None:
        config["inference"]["device"] = device_override
        runtime_overrides["device"] = device_override
    if video_enabled_override is not None:
        config["video"]["enabled"] = video_enabled_override
        runtime_overrides["video_enabled"] = video_enabled_override
    name = run_name or str(config["outputs"]["default_run_name"])
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name) is None:
        raise ContractError("run_name contains unsafe characters")
    run_root = (
        output_root.expanduser().resolve()
        if output_root is not None
        else resolve_path(config["outputs"]["run_root"])
    )
    documentation_root = (
        docs_root.expanduser().resolve()
        if docs_root is not None
        else resolve_path(config["outputs"]["docs_root"])
    )
    final_dir = run_root / name
    final_docs_dir = documentation_root / name
    if final_dir.exists():
        raise ContractError(f"Run output already exists: {final_dir}")
    if final_docs_dir.exists():
        raise ContractError(f"Documentation output already exists: {final_docs_dir}")
    run_root.mkdir(parents=True, exist_ok=True)
    partial = run_root / f".{name}.partial-{uuid.uuid4().hex}"
    partial.mkdir(parents=False, exist_ok=False)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    wall_started = time.perf_counter()
    try:
        if sequence_manifest is None:
            if config["source"].get("mode") != "v12_smoke":
                raise ContractError("A sequence manifest is required outside v12_smoke mode")
            manifest_path = build_v12_smoke_manifest(config, partial)
            manifest_origin = "derived_v12_smoke"
        else:
            manifest_path = sequence_manifest.expanduser().resolve()
            manifest_origin = "external_provenance_bound_manifest"
        sequences, manifest_metadata = load_sequence_manifest(manifest_path, config)
        try:
            manifest_metadata["path"] = manifest_path.relative_to(partial).as_posix()
        except ValueError:
            manifest_metadata["path"] = str(manifest_path)
        manifest_metadata["origin"] = manifest_origin

        deterministic = configure_determinism(int(config["inference"]["seed"]))
        checkpoint_path = resolve_path(config["checkpoint"]["path"])
        model, checkpoint_metadata = load_verified_model(
            checkpoint_path,
            config["checkpoint"]["sha256"],
            task=str(config["checkpoint"]["task"]),
        )
        calibration_split_name = str(config["source"]["calibration_split"])
        test_split_name = str(config["source"]["locked_test_split"])
        calibration_sequences = [
            item for item in sequences if item.split == calibration_split_name
        ]
        test_sequences = [item for item in sequences if item.split == test_split_name]
        ledger = AccessLedger(calibration_split_name, test_split_name)
        prediction_artifacts = partial / "prediction_masks"
        calibration_predictions, calibration_rows = predict_sequences(
            model,
            calibration_sequences,
            config,
            ledger,
            prediction_artifacts,
        )
        curve, selection = calibration_curve(calibration_predictions, config)
        selected_threshold = float(selection["threshold"])
        ledger.freeze_threshold(selected_threshold)
        test_predictions, test_rows = predict_sequences(
            model,
            test_sequences,
            config,
            ledger,
            prediction_artifacts,
        )

        calibration_by_condition = _condition_split(calibration_predictions)
        test_by_condition = _condition_split(test_predictions)
        expected_conditions = list(config["conditions"]["ordered"])
        if set(calibration_by_condition) != set(expected_conditions) or set(test_by_condition) != set(expected_conditions):
            raise ContractError("Both splits must contain both matched conditions")
        calibration_selected: dict[str, Any] = {}
        for condition in expected_conditions:
            calibration_selected[condition] = evaluate_prediction_set(
                calibration_by_condition[condition],
                config,
                selected_threshold,
                include_uncertainty=True,
            )
        ledger.begin_locked_test_evaluation()
        test_results: dict[str, Any] = {}
        for condition in expected_conditions:
            test_results[condition] = evaluate_prediction_set(
                test_by_condition[condition],
                config,
                selected_threshold,
                include_uncertainty=True,
            )
        deltas = paired_condition_deltas(test_results, test_by_condition, config)
        target_assessment = assess_descriptive_targets(test_results, config)
        ledger.finish()

        predictions_path = partial / "predictions.jsonl"
        prediction_metadata = {
            "record_type": "prediction_metadata",
            "schema_version": 1,
            "contract": "spot_spray_simulation_video_predictions_v1",
            "checkpoint_sha256": checkpoint_metadata["sha256"],
            "sequence_manifest_sha256": manifest_metadata["sha256"],
            "config_sha256": sha256_file(config_path),
            "confidence_floor": float(config["inference"]["confidence_floor"]),
            "selected_shared_threshold": selected_threshold,
            "calibration_split": calibration_split_name,
            "locked_test_split": test_split_name,
            "test_evaluation_count": ledger.locked_test_metric_evaluations,
        }
        write_jsonl(predictions_path, [prediction_metadata, *calibration_rows, *test_rows])
        videos = render_overlay_videos(
            test_by_condition,
            test_results,
            selected_threshold,
            config,
            partial / "videos",
        )
        runtime = runtime_summary([calibration_predictions, test_predictions])
        metrics = {
            "schema_version": 1,
            "contract": EVALUATION_CONTRACT,
            "status": "SYNTHETIC_DIAGNOSTIC_COMPLETE",
            "run_name": name,
            "started_utc": started_utc,
            "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config": {
                "path": str(config_path),
                "sha256": sha256_file(config_path),
                "runtime_overrides": runtime_overrides,
            },
            "checkpoint": checkpoint_metadata,
            "manifest": manifest_metadata,
            "determinism": deterministic,
            "environment": environment_receipt(),
            "conditions_ordered": expected_conditions,
            "calibration": {
                "curve": curve,
                "selection": selection,
                "selected_condition_metrics": calibration_selected,
                "test_accessed_during_selection": False,
            },
            "locked_test": {
                "threshold_source": "declared_calibration_scenes_only",
                "evaluation_count": ledger.locked_test_metric_evaluations,
                "conditions": test_results,
                "paired_deltas": deltas,
                "descriptive_target_assessment": target_assessment,
            },
            "runtime": runtime,
            "videos": videos,
            "access_ledger": ledger.receipt(),
            "decision": {
                "synthetic_diagnostic_complete": True,
                "descriptive_target_conclusion": target_assessment["conclusion"],
                "ideal_track_f1_reaches_0_97": target_assessment["ideal"][
                    "reaches_minimum"
                ],
                "degraded_track_f1_within_0_70_to_0_80": target_assessment[
                    "degraded"
                ]["within_near_range"],
                "descriptive_targets_used_for_tuning": False,
                "offline_real_model_go": False,
                "field_fire_go": False,
                "chemical_fire_go": False,
                "synthetic_score_weight_in_real_go_decision": 0.0,
                "fail_closed": True,
            },
            "limitations": [
                str(config["source"]["v12_smoke"]["limitation"]),
                "The degraded capture transform is plausible but not calibrated to a physical camera.",
                "Image-plane mask/centroid association is a smoke tracker, not field-proven motion compensation or ReID.",
                "Synthetic region-proxy scores cannot support a deployment or field-performance claim.",
            ],
            "claims": list(config["claims"]),
        }
        metrics_path = partial / "metrics.json"
        write_json(metrics_path, metrics)
        receipt = {
            "schema_version": 1,
            "contract": "spot_spray_simulation_video_inference_run_receipt_v1",
            "status": metrics["status"],
            "run_name": name,
            "final_run_directory": str(final_dir),
            "config_sha256": sha256_file(config_path),
            "checkpoint": checkpoint_metadata,
            "sequence_manifest": manifest_metadata,
            "predictions_jsonl": {
                "path": "predictions.jsonl",
                "sha256": sha256_file(predictions_path),
            },
            "metrics_json": {"path": "metrics.json", "sha256": sha256_file(metrics_path)},
            "access_ledger": ledger.receipt(),
            "output_artifacts": artifact_inventory(partial, excluded={"run_receipt.json"}),
            "decision": metrics["decision"],
            "elapsed_wall_seconds": time.perf_counter() - wall_started,
        }
        receipt_path = partial / "run_receipt.json"
        write_json(receipt_path, receipt)
        partial.replace(final_dir)
    except Exception:
        if partial.exists():
            shutil.rmtree(partial)
        raise

    documentation = write_documentation_summary(
        final_docs_dir,
        final_dir,
        metrics,
    )
    return {
        "status": metrics["status"],
        "run_directory": str(final_dir),
        "metrics": str(final_dir / "metrics.json"),
        "run_receipt": str(final_dir / "run_receipt.json"),
        "documentation": documentation,
        "checkpoint_sha256": checkpoint_metadata["sha256"],
        "selected_shared_threshold": selected_threshold,
        "locked_test_evaluation_count": ledger.locked_test_metric_evaluations,
        "ideal_track_f1": test_results["ideal"]["metrics"]["eligible_weed_track"]["f1"],
        "degraded_track_f1": test_results["degraded"]["metrics"]["eligible_weed_track"]["f1"],
        "descriptive_target_conclusion": target_assessment["conclusion"],
        "ideal_reaches_0_97": target_assessment["ideal"]["reaches_minimum"],
        "degraded_within_0_70_to_0_80": target_assessment["degraded"][
            "within_near_range"
        ],
        "synthetic_only": True,
        "field_or_chemical_go": False,
    }


def parse_device(value: str) -> str | int:
    return int(value) if re.fullmatch(r"\d+", value) else value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--sequence-manifest", type=Path)
    parser.add_argument("--run-name")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--device", type=parse_device)
    parser.add_argument("--no-video", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        result = run_benchmark(
            arguments.config,
            sequence_manifest=arguments.sequence_manifest,
            run_name=arguments.run_name,
            output_root=arguments.output_root,
            docs_root=arguments.docs_root,
            device_override=arguments.device,
            video_enabled_override=False if arguments.no_video else None,
        )
    except ContractError as error:
        print(
            stable_json(
                {
                    "status": "CONTRACT_ERROR",
                    "error": str(error),
                    "fail_closed": True,
                    "field_or_chemical_go": False,
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
