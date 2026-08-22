#!/usr/bin/env python3
"""GT-blind, encoder-compensated geometry tracker for the spot-spray proof bay.

This module deliberately contains no model, ground-truth, arm, pair, renderer,
or action-metric integration.  It buffers a complete video and publishes only
after every homography, telemetry, ordering, and association check succeeds.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import json
import math
import re
import struct
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml"
CONTRACT_ID = "spot_spray_ego_motion_tracker_v1"
HOMOGRAPHY_DIRECTION = "image_pixel_to_camera_local_ground_mm"
STATE_UNINITIALIZED = "UNINITIALIZED"
STATE_ACTIVE = "ACTIVE"
STATE_INVALID = "INVALID_SEQUENCE"
STATE_FINALIZED = "FINALIZED"
TRACK_ID_RE = re.compile(r"^trk_[0-9]{6}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LANE_RUN_ROOT = PROJECT_ROOT / "data/runs/spot_spray_ego_motion_tracker_v1"
LANE_RESULTS_ROOT = PROJECT_ROOT / "docs/results/spot_spray_ego_motion_tracker_v1"
TRACKER_TEST_PATH = PROJECT_ROOT / "tests/test_evaluate_spot_spray_ego_motion_tracker_v1.py"
NEUTRAL_FIXTURE_ID = "neutral_planar_encoder_calibration_mechanics_v1"
NEUTRAL_FIXTURE_SCOPE = "neutral_synthetic_calibration_mechanics_only"
NEUTRAL_SPEEDS_UM_S = (500_000, 1_000_000)
NEUTRAL_FRAMES_PER_SPEED = 30
NEUTRAL_GROUND_FOV_MM = 480.0


class TrackerContractError(RuntimeError):
    """A canonical fail-closed tracker contract violation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise TrackerContractError(code, message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
        + b"\n"
        for row in rows
    )


def _read_bytes(path: Path, code: str, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        _fail(code, f"cannot read {label}: {exc}")


def _require_expected_sha256(path: Path, expected: str, code: str, label: str) -> bytes:
    expected_hash = _exact_sha256(expected, f"{label} expected SHA-256")
    payload = _read_bytes(path, code, label)
    observed = hashlib.sha256(payload).hexdigest()
    if observed != expected_hash:
        _fail(code, f"{label} SHA-256 mismatch: expected {expected_hash}, observed {observed}")
    return payload


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _require_lane_write_path(path: Path, *, result_only: bool = False) -> Path:
    resolved = path.resolve()
    roots = (LANE_RESULTS_ROOT,) if result_only else (LANE_RESULTS_ROOT, LANE_RUN_ROOT)
    if not any(_path_within(resolved, root) for root in roots):
        _fail(
            "TRACKER_INVALID_SCOPE_VIOLATION",
            f"output path is outside tracker-lane roots: {resolved}",
        )
    return resolved


def _write_immutable_bytes(path: Path, payload: bytes, *, result_only: bool = False) -> None:
    resolved = _require_lane_write_path(path, result_only=result_only)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        observed = resolved.read_bytes()
        if observed != payload:
            _fail(
                "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
                f"immutable artifact differs from requested bytes: {resolved}",
            )
        return
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    if temporary.exists():
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            f"stale temporary artifact blocks atomic write: {temporary}",
        )
    temporary.write_bytes(payload)
    temporary.replace(resolved)


def _repo_relative(path: Path, repo_root: Path = PROJECT_ROOT) -> str:
    resolved = path.resolve()
    for physical_root, logical_root in (
        (LANE_RUN_ROOT.resolve(), Path("data/runs/spot_spray_ego_motion_tracker_v1")),
        (
            LANE_RESULTS_ROOT.resolve(),
            Path("docs/results/spot_spray_ego_motion_tracker_v1"),
        ),
    ):
        try:
            suffix = resolved.relative_to(physical_root)
        except ValueError:
            continue
        return (logical_root / suffix).as_posix()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        _fail("TRACKER_INVALID_SCOPE_VIOLATION", f"path is outside repository: {resolved}")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be a mapping")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be a sequence")
    return value


def _exact_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be lowercase SHA-256")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be finite")
    return result


def _exact_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"{label} must be an integer")
    return value


def ceil_div(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("ceil_div accepts a non-negative numerator and positive denominator")
    return (numerator + denominator - 1) // denominator


@dataclass(frozen=True)
class SourceLock:
    name: str
    path: str
    sha256: str
    role: str


@dataclass(frozen=True)
class TrackerContract:
    implementation_base_commit: str
    claim_evidence_class: str
    source_locks: tuple[SourceLock, ...]
    pixel_space_id: str
    preprocessing_sha256: str
    width_px: int
    height_px: int
    central_support_xyxy_px: tuple[float, float, float, float]
    quantization_um: int
    projection_denominator_minimum: float
    homography_residual_p95_maximum_mm: float
    homography_residual_maximum_mm: float
    daily_registration_drift_maximum_mm: float
    orientation_witness_maximum_error_mm: float
    orientation_minimum_axis_delta_mm: float
    encoder_resolution_maximum_um_per_count: int
    encoder_scale_error_maximum_um_per_m: int
    trigger_encoder_delta_maximum_us: int
    encoder_stale_no_fire_after_us: int
    maximum_forward_speed_um_s: int
    travel_envelope_endpoint_tolerance_um: int
    maximum_frame_index_delta: int
    hard_gate_ceiling_um: int
    fixed_budget_um: int
    maximum_canopy_relief_mm: int
    minimum_camera_ground_distance_mm: int
    maximum_track_id: int
    allowed_classes: tuple[str, ...]
    allowed_detection_fields: frozenset[str]
    allowed_frame_fields: frozenset[str]
    forbidden_exact_fields: frozenset[str]
    forbidden_prefixes: tuple[str, ...]
    calibration_required_frames_per_speed: int
    calibration_minimum_persistent_fiducials: int
    calibration_raw_pixel_ceiling_witness_px: float

    def dynamic_gate_um(self, travel_um: int) -> int:
        if isinstance(travel_um, bool) or not isinstance(travel_um, int) or travel_um < 0:
            _fail("INVALID_ENCODER_BINDING", "association travel must be non-negative integer um")
        denominator = self.minimum_camera_ground_distance_mm - self.maximum_canopy_relief_mm
        parallax_um = ceil_div(travel_um * self.maximum_canopy_relief_mm, denominator)
        scale_um = ceil_div(travel_um * self.encoder_scale_error_maximum_um_per_m, 1_000_000)
        budget_um = self.fixed_budget_um + parallax_um + scale_um
        gate_um = 1000 * ceil_div(budget_um, 1000)
        if gate_um > self.hard_gate_ceiling_um:
            _fail(
                "TRAVEL_OUTSIDE_PROOF_ENVELOPE",
                f"dynamic gate {gate_um} um exceeds hard ceiling {self.hard_gate_ceiling_um} um",
            )
        return gate_um


def _require_config_value(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        _fail(
            "INVALID_CONFIG_OR_SOURCE_LOCK",
            f"{label} changed: expected {expected!r}, observed {value!r}",
        )


def load_tracker_contract(
    path: str | Path = DEFAULT_CONFIG,
    *,
    verify_source_locks: bool = True,
    repo_root: str | Path = PROJECT_ROOT,
) -> TrackerContract:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"cannot read tracker config: {exc}")
    config = _mapping(raw, "tracker config")
    _require_config_value(config.get("schema_version"), 1, "schema_version")
    _require_config_value(config.get("contract_id"), CONTRACT_ID, "contract_id")
    implementation_base_commit = config.get("implementation_base_commit")
    if not isinstance(implementation_base_commit, str) or re.fullmatch(
        r"[0-9a-f]{40}", implementation_base_commit
    ) is None:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "implementation base commit must be 40 hex")
    claims = _mapping(config.get("claim_boundary"), "claim_boundary")
    for key in (
        "target_performance_claimed",
        "locked_test_access_allowed",
        "model_loading_allowed",
        "field_go",
        "product_go",
        "dry_marker_go",
        "chemical_fire_allowed",
    ):
        _require_config_value(claims.get(key), False, f"claim_boundary.{key}")

    locks_raw = _mapping(config.get("source_locks"), "source_locks")
    locks: list[SourceLock] = []
    root = Path(repo_root).resolve()
    for name in sorted(locks_raw):
        row = _mapping(locks_raw[name], f"source_locks.{name}")
        relative = row.get("path")
        role = row.get("role")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"source_locks.{name}.path is invalid")
        if not isinstance(role, str) or not role:
            _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"source_locks.{name}.role is invalid")
        expected_hash = _exact_sha256(row.get("sha256"), f"source_locks.{name}.sha256")
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"source lock escapes repository: {relative}")
        if verify_source_locks:
            if not resolved.is_file():
                _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"source lock is missing: {relative}")
            observed = sha256_file(resolved)
            if observed != expected_hash:
                _fail(
                    "INVALID_CONFIG_OR_SOURCE_LOCK",
                    f"source lock SHA-256 mismatch for {relative}: {observed}",
                )
        locks.append(SourceLock(name, relative, expected_hash, role))

    pixel = _mapping(config.get("pixel_space"), "pixel_space")
    _require_config_value(pixel.get("implicit_resize_allowed"), False, "implicit resize")
    _require_config_value(pixel.get("implicit_crop_allowed"), False, "implicit crop")
    _require_config_value(pixel.get("runtime_undistortion_allowed"), False, "runtime undistortion")
    support_raw = _sequence(pixel.get("central_support_xyxy_px"), "central support")
    if len(support_raw) != 4:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "central support must have four coordinates")
    support = tuple(_finite_number(value, "central support coordinate") for value in support_raw)

    coordinate = _mapping(config.get("coordinate_contract"), "coordinate_contract")
    _require_config_value(
        coordinate.get("homography_direction"), HOMOGRAPHY_DIRECTION, "homography direction"
    )
    _require_config_value(
        coordinate.get("runtime_matrix_inversion_allowed"), False, "runtime matrix inversion"
    )
    _require_config_value(
        coordinate.get("encoder_positive_axis"),
        "product_ground_positive_x",
        "encoder positive axis",
    )

    homography = _mapping(config.get("homography_acceptance"), "homography_acceptance")
    telemetry = _mapping(config.get("encoder_and_timing"), "encoder_and_timing")
    _require_config_value(
        telemetry.get("same_hardware_event_required"), True, "same hardware event"
    )
    _require_config_value(
        telemetry.get("reverse_or_ambiguous_direction_allowed"),
        False,
        "reverse direction policy",
    )
    association = _mapping(config.get("association"), "association")
    _require_config_value(
        association.get("solver"),
        "deterministic_exact_integer_min_cost_flow",
        "association solver",
    )
    _require_config_value(
        association.get("raw_pixel_fallback_allowed"), False, "raw pixel fallback"
    )
    dynamic = _mapping(association.get("dynamic_gate"), "association.dynamic_gate")
    fixed_terms = _mapping(
        association.get("fixed_budget_terms_um"), "association.fixed_budget_terms_um"
    )
    fixed_budget = _exact_int(association.get("fixed_budget_um"), "fixed_budget_um")
    if sum(_exact_int(value, f"fixed budget term {name}") for name, value in fixed_terms.items()) != fixed_budget:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "fixed gate budget terms do not sum exactly")

    input_policy = _mapping(config.get("association_input_policy"), "association_input_policy")
    classes = _mapping(config.get("class_output"), "class_output")
    _require_config_value(
        classes.get("association_completed_before_class_logic"),
        True,
        "class association ordering",
    )
    _require_config_value(
        classes.get("conflict_emitted_confidence"), 0.0, "conflict confidence"
    )
    state_machine = _mapping(config.get("state_machine"), "state_machine")
    _require_config_value(
        state_machine.get("atomic_video_publication"), True, "atomic publication"
    )
    _require_config_value(
        state_machine.get("partial_prediction_publication_allowed"),
        False,
        "partial publication",
    )
    calibration = _mapping(config.get("calibration_diagnostic"), "calibration_diagnostic")
    _require_config_value(
        calibration.get("target_gt_allowed"), False, "calibration target GT access"
    )
    _require_config_value(
        calibration.get("model_output_allowed"), False, "calibration model output access"
    )
    _require_config_value(
        calibration.get("locked_test_allowed"), False, "calibration locked-test access"
    )

    contract = TrackerContract(
        implementation_base_commit=implementation_base_commit,
        claim_evidence_class=str(claims.get("evidence_class")),
        source_locks=tuple(locks),
        pixel_space_id=str(pixel.get("pixel_space_id")),
        preprocessing_sha256=_exact_sha256(
            pixel.get("preprocessing_sha256"), "pixel_space.preprocessing_sha256"
        ),
        width_px=_exact_int(pixel.get("width_px"), "pixel_space.width_px"),
        height_px=_exact_int(pixel.get("height_px"), "pixel_space.height_px"),
        central_support_xyxy_px=(support[0], support[1], support[2], support[3]),
        quantization_um=_exact_int(coordinate.get("quantization_um"), "quantization_um"),
        projection_denominator_minimum=_finite_number(
            coordinate.get("projection_denominator_absolute_minimum"),
            "projection denominator minimum",
        ),
        homography_residual_p95_maximum_mm=_finite_number(
            homography.get("residual_p95_maximum_mm"), "homography p95 maximum"
        ),
        homography_residual_maximum_mm=_finite_number(
            homography.get("residual_maximum_mm"), "homography maximum residual"
        ),
        daily_registration_drift_maximum_mm=_finite_number(
            homography.get("daily_registration_drift_maximum_mm"), "daily drift maximum"
        ),
        orientation_witness_maximum_error_mm=_finite_number(
            homography.get("orientation_witness_maximum_error_mm"),
            "orientation witness maximum error",
        ),
        orientation_minimum_axis_delta_mm=_finite_number(
            homography.get("orientation_minimum_axis_delta_mm"),
            "orientation minimum axis delta",
        ),
        encoder_resolution_maximum_um_per_count=_exact_int(
            telemetry.get("encoder_resolution_maximum_um_per_count"),
            "encoder resolution maximum",
        ),
        encoder_scale_error_maximum_um_per_m=_exact_int(
            telemetry.get("encoder_scale_error_maximum_um_per_m"),
            "encoder scale error maximum",
        ),
        trigger_encoder_delta_maximum_us=_exact_int(
            telemetry.get("trigger_encoder_delta_maximum_us"),
            "trigger encoder delta maximum",
        ),
        encoder_stale_no_fire_after_us=_exact_int(
            telemetry.get("encoder_stale_no_fire_after_us"), "encoder stale maximum"
        ),
        maximum_forward_speed_um_s=_exact_int(
            telemetry.get("maximum_forward_speed_um_s"), "maximum forward speed"
        ),
        travel_envelope_endpoint_tolerance_um=_exact_int(
            telemetry.get("travel_envelope_endpoint_tolerance_um"),
            "travel endpoint tolerance",
        ),
        maximum_frame_index_delta=_exact_int(
            association.get("maximum_frame_index_delta"), "maximum frame-index delta"
        ),
        hard_gate_ceiling_um=_exact_int(
            association.get("hard_gate_ceiling_um"), "hard gate ceiling"
        ),
        fixed_budget_um=fixed_budget,
        maximum_canopy_relief_mm=_exact_int(
            dynamic.get("maximum_canopy_relief_mm"), "maximum canopy relief"
        ),
        minimum_camera_ground_distance_mm=_exact_int(
            dynamic.get("minimum_camera_ground_distance_mm"),
            "minimum camera-ground distance",
        ),
        maximum_track_id=_exact_int(
            association.get("maximum_track_id"), "maximum track ID"
        ),
        allowed_classes=tuple(
            str(value) for value in _sequence(classes.get("allowed_classes"), "allowed classes")
        ),
        allowed_detection_fields=frozenset(
            str(value)
            for value in _sequence(
                input_policy.get("exact_allowed_detection_fields"), "allowed detection fields"
            )
        ),
        allowed_frame_fields=frozenset(
            str(value)
            for value in _sequence(
                input_policy.get("exact_allowed_frame_fields"), "allowed frame fields"
            )
        ),
        forbidden_exact_fields=frozenset(
            str(value)
            for value in _sequence(
                input_policy.get("forbidden_exact_fields"), "forbidden exact fields"
            )
        ),
        forbidden_prefixes=tuple(
            str(value)
            for value in _sequence(input_policy.get("forbidden_prefixes"), "forbidden prefixes")
        ),
        calibration_required_frames_per_speed=_exact_int(
            calibration.get("required_frames_per_speed"),
            "calibration required frames per speed",
        ),
        calibration_minimum_persistent_fiducials=_exact_int(
            calibration.get("minimum_persistent_fiducials"),
            "calibration minimum persistent fiducials",
        ),
        calibration_raw_pixel_ceiling_witness_px=_finite_number(
            calibration.get("raw_pixel_ceiling_witness_px"),
            "calibration raw-pixel ceiling witness",
        ),
    )
    if contract.width_px != 2048 or contract.height_px != 2048:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 requires native 2048-square masks")
    if contract.quantization_um != 10:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 ground quantization must remain 10 um")
    if contract.maximum_frame_index_delta != 2:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 frame-index delta must remain 2")
    if contract.hard_gate_ceiling_um != 45_000:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 hard gate ceiling must remain 45 mm")
    if contract.claim_evidence_class != NEUTRAL_FIXTURE_SCOPE:
        _fail(
            "INVALID_CONFIG_OR_SOURCE_LOCK",
            "V1 local evidence class must remain neutral calibration mechanics only",
        )
    if contract.calibration_required_frames_per_speed != NEUTRAL_FRAMES_PER_SPEED:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 requires 30 frames per proof speed")
    if contract.calibration_minimum_persistent_fiducials != 9:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 requires at least nine fiducials")
    if contract.calibration_raw_pixel_ceiling_witness_px != 160.0:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", "V1 raw-motion witness ceiling must be 160 px")
    acceptance = _mapping(association.get("acceptance_vectors_um"), "gate acceptance vectors")
    expected_vectors = {
        "speed_0p5_one_frame": contract.dynamic_gate_um(33_334),
        "speed_0p5_two_frames": contract.dynamic_gate_um(66_667),
        "speed_1p0_one_frame": contract.dynamic_gate_um(66_667),
        "speed_1p0_two_frames": contract.dynamic_gate_um(133_334),
    }
    for name, observed in expected_vectors.items():
        _require_config_value(acceptance.get(name), observed, f"gate vector {name}")
    return contract


@dataclass(frozen=True)
class OrientationWitness:
    role: str
    pixel_xy: tuple[float, float]
    ground_xy_mm: tuple[float, float]


@dataclass(frozen=True)
class HomographyBinding:
    receipt_sha256: str
    direction: str
    pixel_space_id: str
    preprocessing_sha256: str
    matrix_i2g: tuple[tuple[float, float, float], ...]
    support_polygon_px: tuple[tuple[float, float], ...]
    residual_p95_mm: float
    residual_max_mm: float
    daily_registration_drift_mm: float
    orientation_witnesses: tuple[OrientationWitness, ...]


@dataclass(frozen=True)
class EncoderBinding:
    receipt_sha256: str
    same_hardware_event: bool
    positive_axis: str
    resolution_um_per_count: int
    scale_error_um_per_m: int
    trigger_encoder_delta_limit_us: int
    stale_after_us: int


@dataclass(frozen=True)
class FrameTelemetry:
    frame_index: int
    timestamp_ns: int
    encoder_position_um: int | None
    trigger_encoder_delta_us: int | None
    encoder_age_us: int | None
    homography_binding_id: str


@dataclass(frozen=True)
class DetectionInput:
    mask: np.ndarray
    class_name: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    action_point: tuple[float, float]


@dataclass(frozen=True)
class PreparedDetection:
    source: DetectionInput
    centroid_px: tuple[float, float]
    anchor_um: tuple[int, int]
    mask_sha256: str
    association_key: tuple[int, int, str]
    trackable: bool


@dataclass
class TrackState:
    numeric_id: int
    track_id: str
    last_frame_index: int
    last_encoder_position_um: int
    anchor_um: tuple[int, int]
    emitted_class_name: str
    raw_label_conflict_count: int = 0


@dataclass(frozen=True)
class CalibrationFileLock:
    name: str
    path: Path
    sha256: str
    payload: bytes


@dataclass(frozen=True)
class CalibrationFixtureLock:
    fixture_id: str
    evidence_scope: str
    implementation_path: Path
    implementation_sha256: str
    files: tuple[CalibrationFileLock, ...]

    def file(self, name: str) -> CalibrationFileLock:
        matches = [item for item in self.files if item.name == name]
        if len(matches) != 1:
            _fail(
                "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
                f"calibration file lock {name!r} is not unique",
            )
        return matches[0]


def _reject_forbidden_or_unknown_fields(
    raw: Mapping[str, Any], allowed: frozenset[str], contract: TrackerContract, label: str
) -> None:
    keys = {str(key) for key in raw}
    forbidden = sorted(
        key
        for key in keys
        if key in contract.forbidden_exact_fields
        or any(key.startswith(prefix) for prefix in contract.forbidden_prefixes)
    )
    if forbidden:
        _fail(
            "FORBIDDEN_ASSOCIATION_INPUT",
            f"{label} contains forbidden association fields: {forbidden}",
        )
    unknown = sorted(keys - allowed)
    if unknown:
        _fail("FORBIDDEN_ASSOCIATION_INPUT", f"{label} contains unknown fields: {unknown}")
    missing = sorted(allowed - keys)
    if missing:
        _fail("INVALID_DETECTION_GEOMETRY", f"{label} is missing required fields: {missing}")


def detection_from_mapping(raw: Mapping[str, Any], contract: TrackerContract) -> DetectionInput:
    row = _mapping(raw, "detection")
    _reject_forbidden_or_unknown_fields(
        row, contract.allowed_detection_fields, contract, "detection"
    )
    class_name = row["class_name"]
    if not isinstance(class_name, str) or class_name not in contract.allowed_classes:
        _fail("INVALID_DETECTION_GEOMETRY", f"unsupported raw class {class_name!r}")
    confidence = _finite_number(row["confidence"], "detection confidence")
    if not 0.0 <= confidence <= 1.0:
        _fail("INVALID_DETECTION_GEOMETRY", "detection confidence must be in [0,1]")
    polygon = _parse_normalized_points(row["polygon"], "detection polygon", minimum=3)
    action_points = _parse_normalized_points(
        [row["action_point"]], "detection action point", minimum=1
    )
    mask = np.asarray(row["mask"])
    return DetectionInput(mask, class_name, confidence, polygon, action_points[0])


def telemetry_and_detections_from_mapping(
    raw: Mapping[str, Any], contract: TrackerContract
) -> tuple[str, FrameTelemetry, tuple[DetectionInput, ...]]:
    row = _mapping(raw, "frame")
    _reject_forbidden_or_unknown_fields(row, contract.allowed_frame_fields, contract, "frame")
    frame_id = row["frame_id"]
    if not isinstance(frame_id, str) or not frame_id:
        _fail("INVALID_FRAME_ORDER", "frame_id must be a non-empty opaque string")
    detections_raw = _sequence(row["detections"], "frame detections")
    detections = tuple(detection_from_mapping(_mapping(item, "detection"), contract) for item in detections_raw)
    telemetry = FrameTelemetry(
        frame_index=row["frame_index"],
        timestamp_ns=row["timestamp_ns"],
        encoder_position_um=row["encoder_position_um"],
        trigger_encoder_delta_us=row["trigger_encoder_delta_us"],
        encoder_age_us=row["encoder_age_us"],
        homography_binding_id=row["homography_binding_id"],
    )
    return frame_id, telemetry, detections


def _parse_normalized_points(
    value: Any, label: str, *, minimum: int
) -> tuple[tuple[float, float], ...]:
    rows = _sequence(value, label)
    if len(rows) < minimum:
        _fail("INVALID_DETECTION_GEOMETRY", f"{label} needs at least {minimum} points")
    output: list[tuple[float, float]] = []
    for index, raw_point in enumerate(rows):
        point = _sequence(raw_point, f"{label}[{index}]")
        if len(point) != 2:
            _fail("INVALID_DETECTION_GEOMETRY", f"{label}[{index}] must have two values")
        x = _finite_number(point[0], f"{label}[{index}].x")
        y = _finite_number(point[1], f"{label}[{index}].y")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            _fail("INVALID_DETECTION_GEOMETRY", f"{label}[{index}] is outside [0,1]")
        output.append((x, y))
    return tuple(output)


def homography_binding_from_mapping(
    raw: Mapping[str, Any], contract: TrackerContract
) -> HomographyBinding:
    row = _mapping(raw, "homography binding")
    allowed = {
        "schema_version",
        "contract_id",
        "evidence_scope",
        "receipt_sha256",
        "direction",
        "pixel_space_id",
        "preprocessing_sha256",
        "matrix_i2g",
        "support_polygon_px",
        "residual_p95_mm",
        "residual_max_mm",
        "daily_registration_drift_mm",
        "orientation_witnesses",
    }
    unknown = sorted(set(row) - allowed)
    if unknown:
        _fail("INVALID_HOMOGRAPHY_BINDING", f"homography binding has unknown fields: {unknown}")
    required = allowed - {"schema_version", "contract_id", "evidence_scope"}
    missing = sorted(required - set(row))
    if missing:
        _fail("INVALID_HOMOGRAPHY_BINDING", f"homography binding is missing: {missing}")
    matrix_rows = _sequence(row["matrix_i2g"], "matrix_i2g")
    if len(matrix_rows) != 3:
        _fail("INVALID_HOMOGRAPHY_BINDING", "matrix_i2g must be 3x3")
    matrix: list[tuple[float, float, float]] = []
    for row_index, matrix_row in enumerate(matrix_rows):
        values = _sequence(matrix_row, f"matrix_i2g[{row_index}]")
        if len(values) != 3:
            _fail("INVALID_HOMOGRAPHY_BINDING", "matrix_i2g must be 3x3")
        matrix.append(tuple(_finite_number(value, "homography coefficient") for value in values))
    support_rows = _sequence(row["support_polygon_px"], "homography support polygon")
    if len(support_rows) < 3:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography support needs at least three points")
    support: list[tuple[float, float]] = []
    for raw_point in support_rows:
        point = _sequence(raw_point, "homography support point")
        if len(point) != 2:
            _fail("INVALID_HOMOGRAPHY_BINDING", "homography support point must be 2D")
        support.append(
            (
                _finite_number(point[0], "homography support x"),
                _finite_number(point[1], "homography support y"),
            )
        )
    witnesses_raw = _sequence(row["orientation_witnesses"], "orientation witnesses")
    witnesses: list[OrientationWitness] = []
    for raw_witness in witnesses_raw:
        witness = _mapping(raw_witness, "orientation witness")
        if set(witness) != {"role", "pixel_xy", "ground_xy_mm"}:
            _fail("INVALID_HOMOGRAPHY_BINDING", "orientation witness fields changed")
        role = witness["role"]
        if not isinstance(role, str):
            _fail("INVALID_HOMOGRAPHY_BINDING", "orientation witness role must be text")
        pixel = _sequence(witness["pixel_xy"], "orientation witness pixel")
        ground = _sequence(witness["ground_xy_mm"], "orientation witness ground")
        if len(pixel) != 2 or len(ground) != 2:
            _fail("INVALID_HOMOGRAPHY_BINDING", "orientation witness coordinates must be 2D")
        witnesses.append(
            OrientationWitness(
                role=role,
                pixel_xy=(
                    _finite_number(pixel[0], "orientation pixel x"),
                    _finite_number(pixel[1], "orientation pixel y"),
                ),
                ground_xy_mm=(
                    _finite_number(ground[0], "orientation ground x"),
                    _finite_number(ground[1], "orientation ground y"),
                ),
            )
        )
    binding = HomographyBinding(
        receipt_sha256=_exact_sha256(row["receipt_sha256"], "homography receipt SHA-256"),
        direction=str(row["direction"]),
        pixel_space_id=str(row["pixel_space_id"]),
        preprocessing_sha256=_exact_sha256(
            row["preprocessing_sha256"], "homography preprocessing SHA-256"
        ),
        matrix_i2g=tuple(matrix),
        support_polygon_px=tuple(support),
        residual_p95_mm=_finite_number(row["residual_p95_mm"], "homography residual p95"),
        residual_max_mm=_finite_number(row["residual_max_mm"], "homography residual maximum"),
        daily_registration_drift_mm=_finite_number(
            row["daily_registration_drift_mm"], "daily registration drift"
        ),
        orientation_witnesses=tuple(witnesses),
    )
    validate_homography_binding(binding, contract)
    return binding


def encoder_binding_from_mapping(raw: Mapping[str, Any], contract: TrackerContract) -> EncoderBinding:
    row = _mapping(raw, "encoder binding")
    allowed = {
        "schema_version",
        "contract_id",
        "evidence_scope",
        "receipt_sha256",
        "same_hardware_event",
        "positive_axis",
        "resolution_um_per_count",
        "scale_error_um_per_m",
        "trigger_encoder_delta_limit_us",
        "stale_after_us",
    }
    unknown = sorted(set(row) - allowed)
    if unknown:
        _fail("INVALID_ENCODER_BINDING", f"encoder binding has unknown fields: {unknown}")
    required = allowed - {"schema_version", "contract_id", "evidence_scope"}
    missing = sorted(required - set(row))
    if missing:
        _fail("INVALID_ENCODER_BINDING", f"encoder binding is missing: {missing}")
    binding = EncoderBinding(
        receipt_sha256=_exact_sha256(row["receipt_sha256"], "encoder receipt SHA-256"),
        same_hardware_event=row["same_hardware_event"] is True,
        positive_axis=str(row["positive_axis"]),
        resolution_um_per_count=_exact_int(
            row["resolution_um_per_count"], "encoder resolution"
        ),
        scale_error_um_per_m=_exact_int(row["scale_error_um_per_m"], "encoder scale error"),
        trigger_encoder_delta_limit_us=_exact_int(
            row["trigger_encoder_delta_limit_us"], "trigger/encoder limit"
        ),
        stale_after_us=_exact_int(row["stale_after_us"], "encoder stale limit"),
    )
    validate_encoder_binding(binding, contract)
    return binding


def project_pixel_to_ground_mm(
    binding: HomographyBinding,
    pixel_xy: tuple[float, float],
    denominator_minimum: float,
) -> tuple[float, float]:
    u, v = pixel_xy
    matrix = binding.matrix_i2g
    qx = matrix[0][0] * u + matrix[0][1] * v + matrix[0][2]
    qy = matrix[1][0] * u + matrix[1][1] * v + matrix[1][2]
    qw = matrix[2][0] * u + matrix[2][1] * v + matrix[2][2]
    if not all(math.isfinite(value) for value in (qx, qy, qw)):
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography projection is non-finite")
    if abs(qw) <= denominator_minimum:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography projection denominator is invalid")
    output = (qx / qw, qy / qw)
    if not all(math.isfinite(value) for value in output):
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography output is non-finite")
    return output


def validate_homography_binding(binding: HomographyBinding, contract: TrackerContract) -> None:
    if binding.direction != HOMOGRAPHY_DIRECTION:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography direction is not image-to-ground")
    if binding.pixel_space_id != contract.pixel_space_id:
        _fail("INVALID_PIXEL_SPACE", "homography pixel-space ID does not match tracker")
    if binding.preprocessing_sha256 != contract.preprocessing_sha256:
        _fail("INVALID_PIXEL_SPACE", "homography preprocessing hash does not match tracker")
    if binding.residual_p95_mm > contract.homography_residual_p95_maximum_mm:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography p95 residual exceeds 1 mm")
    if binding.residual_max_mm > contract.homography_residual_maximum_mm:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography maximum residual exceeds 2 mm")
    if binding.daily_registration_drift_mm > contract.daily_registration_drift_maximum_mm:
        _fail("INVALID_HOMOGRAPHY_BINDING", "daily registration drift exceeds 2 mm")
    matrix = np.asarray(binding.matrix_i2g, dtype=np.float64)
    determinant = float(np.linalg.det(matrix))
    if not math.isfinite(determinant) or abs(determinant) <= 1.0e-15:
        _fail("INVALID_HOMOGRAPHY_BINDING", "homography matrix is singular")
    for point in binding.support_polygon_px:
        project_pixel_to_ground_mm(binding, point, contract.projection_denominator_minimum)
    by_role: dict[str, OrientationWitness] = {}
    for witness in binding.orientation_witnesses:
        if witness.role in by_role:
            _fail("INVALID_HOMOGRAPHY_BINDING", "duplicate homography orientation witness role")
        by_role[witness.role] = witness
        observed = project_pixel_to_ground_mm(
            binding, witness.pixel_xy, contract.projection_denominator_minimum
        )
        error = math.hypot(
            observed[0] - witness.ground_xy_mm[0],
            observed[1] - witness.ground_xy_mm[1],
        )
        if error > contract.orientation_witness_maximum_error_mm:
            _fail("INVALID_HOMOGRAPHY_BINDING", "homography orientation witness residual failed")
    if set(by_role) != {"origin", "forward", "right"}:
        _fail("INVALID_HOMOGRAPHY_BINDING", "origin/forward/right witnesses are required")
    origin = by_role["origin"].ground_xy_mm
    forward = by_role["forward"].ground_xy_mm
    right = by_role["right"].ground_xy_mm
    if forward[0] - origin[0] < contract.orientation_minimum_axis_delta_mm:
        _fail("INVALID_HOMOGRAPHY_BINDING", "forward witness does not increase ground +X")
    if right[1] - origin[1] < contract.orientation_minimum_axis_delta_mm:
        _fail("INVALID_HOMOGRAPHY_BINDING", "right witness does not increase ground +Y")


def validate_encoder_binding(binding: EncoderBinding, contract: TrackerContract) -> None:
    if binding.same_hardware_event is not True:
        _fail("INVALID_ENCODER_BINDING", "camera trigger and encoder are not same-event latched")
    if binding.positive_axis != "product_ground_positive_x":
        _fail("INVALID_ENCODER_BINDING", "encoder positive axis is not product +X")
    if not 0 < binding.resolution_um_per_count <= contract.encoder_resolution_maximum_um_per_count:
        _fail("INVALID_ENCODER_BINDING", "encoder resolution exceeds frozen limit")
    if not 0 <= binding.scale_error_um_per_m <= contract.encoder_scale_error_maximum_um_per_m:
        _fail("INVALID_ENCODER_BINDING", "encoder scale error exceeds frozen limit")
    if not 0 <= binding.trigger_encoder_delta_limit_us <= contract.trigger_encoder_delta_maximum_us:
        _fail("INVALID_ENCODER_BINDING", "trigger/encoder binding limit exceeds frozen limit")
    if not 0 < binding.stale_after_us <= contract.encoder_stale_no_fire_after_us:
        _fail("INVALID_ENCODER_BINDING", "encoder stale cutoff exceeds frozen limit")


def _round_ground_mm_to_um(value_mm: float, quantum_um: int) -> int:
    units = (Decimal(repr(value_mm)) * Decimal(1000)) / Decimal(quantum_um)
    return int(units.to_integral_value(rounding=ROUND_HALF_EVEN)) * quantum_um


def canonical_mask_sha256(mask: np.ndarray) -> str:
    header = struct.pack(">II", int(mask.shape[0]), int(mask.shape[1]))
    packed = np.packbits(mask.reshape(-1).astype(np.uint8), bitorder="big").tobytes()
    return hashlib.sha256(header + packed).hexdigest()


def _point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > 1.0e-9:
        return False
    return min(ax, bx) - 1.0e-9 <= px <= max(ax, bx) + 1.0e-9 and min(
        ay, by
    ) - 1.0e-9 <= py <= max(ay, by) + 1.0e-9


def point_in_polygon_inclusive(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> bool:
    inside = False
    x, y = point
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def prepare_detection(
    detection: DetectionInput,
    homography: HomographyBinding,
    contract: TrackerContract,
    relative_encoder_um: int,
) -> PreparedDetection:
    mask = np.asarray(detection.mask)
    if mask.ndim != 2 or mask.shape != (contract.height_px, contract.width_px):
        _fail(
            "INVALID_DETECTION_GEOMETRY",
            f"mask shape {mask.shape} does not match {(contract.height_px, contract.width_px)}",
        )
    if mask.dtype != np.bool_:
        unique = np.unique(mask)
        if not set(int(value) for value in unique).issubset({0, 1}):
            _fail("INVALID_DETECTION_GEOMETRY", "mask is not canonical binary geometry")
        mask = mask.astype(bool)
    rows, columns = np.nonzero(mask)
    if rows.size == 0:
        _fail("INVALID_DETECTION_GEOMETRY", "mask has no foreground pixels")
    if detection.class_name not in contract.allowed_classes:
        _fail("INVALID_DETECTION_GEOMETRY", "detection class is outside frozen output schema")
    if not math.isfinite(detection.confidence) or not 0.0 <= detection.confidence <= 1.0:
        _fail("INVALID_DETECTION_GEOMETRY", "detection confidence is invalid")
    if len(detection.polygon) < 3:
        _fail("INVALID_DETECTION_GEOMETRY", "detection polygon has fewer than three points")
    for point in (*detection.polygon, detection.action_point):
        if len(point) != 2 or not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in point):
            _fail("INVALID_DETECTION_GEOMETRY", "normalized detection geometry is invalid")
    centroid_px = (float(np.mean(columns + 0.5)), float(np.mean(rows + 0.5)))
    local_mm = project_pixel_to_ground_mm(
        homography, centroid_px, contract.projection_denominator_minimum
    )
    local_x_um = _round_ground_mm_to_um(local_mm[0], contract.quantization_um)
    local_y_um = _round_ground_mm_to_um(local_mm[1], contract.quantization_um)
    anchor_um = (local_x_um + relative_encoder_um, local_y_um)
    mask_hash = canonical_mask_sha256(mask)
    key = (anchor_um[0], anchor_um[1], mask_hash)
    left, top, right, bottom = contract.central_support_xyxy_px
    in_central = left <= centroid_px[0] < right and top <= centroid_px[1] < bottom
    in_calibrated = point_in_polygon_inclusive(centroid_px, homography.support_polygon_px)
    return PreparedDetection(
        source=detection,
        centroid_px=centroid_px,
        anchor_um=anchor_um,
        mask_sha256=mask_hash,
        association_key=key,
        trackable=in_central and in_calibrated,
    )


@dataclass
class _FlowEdge:
    to: int
    reverse: int
    capacity: int
    cost: int


def _add_flow_edge(graph: list[list[_FlowEdge]], source: int, target: int, cost: int) -> _FlowEdge:
    forward = _FlowEdge(target, len(graph[target]), 1, cost)
    reverse = _FlowEdge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[target].append(reverse)
    return forward


def deterministic_global_assignment(
    track_count: int,
    detection_count: int,
    valid_squared_residuals: Mapping[tuple[int, int], int],
    hard_gate_um: int,
) -> tuple[tuple[int, int], ...]:
    """Exact cardinality/residual/lexicographic bipartite assignment.

    A full assignment gives every track either one real detection or its own
    dummy.  Mixed-radix integer costs encode, in order: unmatched-track count,
    total squared residual, then the complete canonical assignment vector.
    """

    if track_count < 0 or detection_count < 0 or hard_gate_um <= 0:
        raise ValueError("assignment dimensions and gate must be non-negative")
    if track_count == 0 or detection_count == 0:
        return ()
    for (track_index, detection_index), residual_sq in valid_squared_residuals.items():
        if not 0 <= track_index < track_count or not 0 <= detection_index < detection_count:
            raise ValueError("assignment edge index is outside the matrix")
        if isinstance(residual_sq, bool) or not isinstance(residual_sq, int) or residual_sq < 0:
            raise ValueError("assignment residual must be a non-negative integer")
        if residual_sq > hard_gate_um * hard_gate_um:
            raise ValueError("assignment edge exceeds the declared hard gate")

    base = detection_count + 1
    residual_base = base**track_count
    maximum_residual_sum = track_count * hard_gate_um * hard_gate_um
    unmatched_base = (maximum_residual_sum + 1) * residual_base
    digit_weights = [base ** (track_count - 1 - index) for index in range(track_count)]

    source = 0
    first_track = 1
    first_detection = first_track + track_count
    first_dummy = first_detection + detection_count
    sink = first_dummy + track_count
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink + 1)]
    references: dict[tuple[int, int], _FlowEdge] = {}
    for track_index in range(track_count):
        track_node = first_track + track_index
        _add_flow_edge(graph, source, track_node, 0)
        for detection_index in range(detection_count):
            residual_sq = valid_squared_residuals.get((track_index, detection_index))
            if residual_sq is None:
                continue
            cost = residual_sq * residual_base + detection_index * digit_weights[track_index]
            references[(track_index, detection_index)] = _add_flow_edge(
                graph, track_node, first_detection + detection_index, cost
            )
        dummy_cost = unmatched_base + detection_count * digit_weights[track_index]
        _add_flow_edge(graph, track_node, first_dummy + track_index, dummy_cost)
    for column_node in range(first_detection, sink):
        _add_flow_edge(graph, column_node, sink, 0)

    potentials = [0] * len(graph)
    for _ in range(track_count):
        distances: list[int | None] = [None] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[source] = 0
        queue: list[tuple[int, int]] = [(0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distances[node] != distance:
                continue
            for edge_index, edge in enumerate(graph[node]):
                if edge.capacity == 0:
                    continue
                reduced = edge.cost + potentials[node] - potentials[edge.to]
                if reduced < 0:
                    raise RuntimeError("min-cost-flow reduced cost invariant failed")
                candidate = distance + reduced
                current = distances[edge.to]
                predecessor = (node, edge_index)
                if current is None or candidate < current or (
                    candidate == current
                    and previous[edge.to] is not None
                    and predecessor < previous[edge.to]
                ):
                    distances[edge.to] = candidate
                    previous[edge.to] = predecessor
                    heapq.heappush(queue, (candidate, edge.to))
        if distances[sink] is None:
            raise RuntimeError("dummy-complete tracker assignment became infeasible")
        for node, distance in enumerate(distances):
            if distance is not None:
                potentials[node] += distance
        node = sink
        while node != source:
            predecessor = previous[node]
            if predecessor is None:
                raise RuntimeError("assignment augmenting path is incomplete")
            parent, edge_index = predecessor
            edge = graph[parent][edge_index]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = parent

    matches = tuple(
        sorted(key for key, edge in references.items() if edge.capacity == 0)
    )
    if len({track for track, _ in matches}) != len(matches) or len(
        {detection for _, detection in matches}
    ) != len(matches):
        raise RuntimeError("assignment is not one-to-one")
    return matches


class EgoMotionTracker:
    def __init__(self, contract: TrackerContract):
        self.contract = contract
        self.state = STATE_UNINITIALIZED
        self._homography: HomographyBinding | None = None
        self._encoder_binding: EncoderBinding | None = None
        self._first_frame_index = 0
        self._epoch_encoder_um: int | None = None
        self._last_telemetry: FrameTelemetry | None = None
        self._seen_frame_ids: set[str] = set()
        self._tracks: dict[int, TrackState] = {}
        self._next_track_id = 1
        self._prediction_frames: list[dict[str, Any]] = []
        self._diagnostics: list[dict[str, Any]] = []
        self._failure: dict[str, Any] | None = None

    def start_sequence(
        self,
        homography: HomographyBinding,
        encoder_binding: EncoderBinding,
        *,
        first_frame_index: int = 0,
    ) -> None:
        if self.state != STATE_UNINITIALIZED:
            _fail("INVALID_STATE", "start_sequence requires UNINITIALIZED state")
        try:
            validate_homography_binding(homography, self.contract)
            validate_encoder_binding(encoder_binding, self.contract)
            if isinstance(first_frame_index, bool) or not isinstance(first_frame_index, int):
                _fail("INVALID_FRAME_ORDER", "first frame index must be an integer")
        except TrackerContractError as exc:
            self._invalidate(exc)
            raise
        self._homography = homography
        self._encoder_binding = encoder_binding
        self._first_frame_index = first_frame_index
        self.state = STATE_ACTIVE

    def reset_sequence(self) -> None:
        if self.state == STATE_ACTIVE:
            _fail("INVALID_STATE", "an active valid sequence must finish before reset")
        self.state = STATE_UNINITIALIZED
        self._homography = None
        self._encoder_binding = None
        self._first_frame_index = 0
        self._epoch_encoder_um = None
        self._last_telemetry = None
        self._seen_frame_ids.clear()
        self._tracks.clear()
        self._next_track_id = 1
        self._prediction_frames.clear()
        self._diagnostics.clear()
        self._failure = None

    def process_mapping(self, raw: Mapping[str, Any]) -> None:
        frame_id, telemetry, detections = telemetry_and_detections_from_mapping(
            raw, self.contract
        )
        self.process_frame(frame_id, telemetry, detections)

    def process_frame(
        self,
        frame_id: str,
        telemetry: FrameTelemetry,
        detections: Sequence[DetectionInput],
    ) -> None:
        if self.state != STATE_ACTIVE:
            _fail("INVALID_STATE", "process_frame requires ACTIVE state")
        try:
            assert self._homography is not None and self._encoder_binding is not None
            self._validate_frame_telemetry(frame_id, telemetry)
            assert telemetry.encoder_position_um is not None
            if self._epoch_encoder_um is None:
                self._epoch_encoder_um = telemetry.encoder_position_um
            relative_encoder_um = telemetry.encoder_position_um - self._epoch_encoder_um
            prepared = sorted(
                (
                    prepare_detection(
                        detection,
                        self._homography,
                        self.contract,
                        relative_encoder_um,
                    )
                    for detection in detections
                ),
                key=lambda item: item.association_key,
            )
            keys = [item.association_key for item in prepared]
            if len(keys) != len(set(keys)):
                _fail(
                    "AMBIGUOUS_DUPLICATE_GEOMETRY",
                    "two detections have identical canonical geometry in one frame",
                )
            self._expire_tracks(telemetry.frame_index)
            trackable_indices = [index for index, item in enumerate(prepared) if item.trackable]
            active_tracks = [self._tracks[key] for key in sorted(self._tracks)]
            edges: dict[tuple[int, int], int] = {}
            edge_details: dict[tuple[int, int], tuple[int, int]] = {}
            for track_index, track in enumerate(active_tracks):
                frame_delta = telemetry.frame_index - track.last_frame_index
                if not 1 <= frame_delta <= self.contract.maximum_frame_index_delta:
                    continue
                travel_um = telemetry.encoder_position_um - track.last_encoder_position_um
                gate_um = self.contract.dynamic_gate_um(travel_um)
                for compact_detection_index, prepared_index in enumerate(trackable_indices):
                    detection = prepared[prepared_index]
                    dx = detection.anchor_um[0] - track.anchor_um[0]
                    dy = detection.anchor_um[1] - track.anchor_um[1]
                    residual_sq = dx * dx + dy * dy
                    if residual_sq <= gate_um * gate_um:
                        edges[(track_index, compact_detection_index)] = residual_sq
                        edge_details[(track_index, compact_detection_index)] = (
                            int(math.isqrt(residual_sq)),
                            gate_um,
                        )
            compact_matches = deterministic_global_assignment(
                len(active_tracks),
                len(trackable_indices),
                edges,
                self.contract.hard_gate_ceiling_um,
            )
            matches = [
                (track_index, trackable_indices[compact_detection_index])
                for track_index, compact_detection_index in compact_matches
            ]
            matched_detection_indices: set[int] = set()
            candidate_rows: list[tuple[int, dict[str, Any]]] = []
            for track_index, prepared_index in matches:
                track = active_tracks[track_index]
                detection = prepared[prepared_index]
                compact_index = trackable_indices.index(prepared_index)
                residual_floor_um, gate_um = edge_details[(track_index, compact_index)]
                frame_delta = telemetry.frame_index - track.last_frame_index
                encoder_delta_um = telemetry.encoder_position_um - track.last_encoder_position_um
                conflict = detection.source.class_name != track.emitted_class_name
                if conflict:
                    track.raw_label_conflict_count += 1
                track.last_frame_index = telemetry.frame_index
                track.last_encoder_position_um = telemetry.encoder_position_um
                track.anchor_um = detection.anchor_um
                candidate_rows.append(
                    (track.numeric_id, self._candidate_row(track, detection, conflict))
                )
                self._diagnostics.append(
                    {
                        "frame_index": telemetry.frame_index,
                        "track_id": track.track_id,
                        "association_state": "matched",
                        "residual_floor_um": residual_floor_um,
                        "residual_squared_um2": edges[(track_index, compact_index)],
                        "gate_um": gate_um,
                        "frame_delta": frame_delta,
                        "encoder_delta_um": encoder_delta_um,
                        "raw_label_conflict": conflict,
                    }
                )
                matched_detection_indices.add(prepared_index)
            for prepared_index, detection in enumerate(prepared):
                if prepared_index in matched_detection_indices:
                    continue
                track = self._new_track(detection, telemetry)
                candidate_rows.append((track.numeric_id, self._candidate_row(track, detection, False)))
                if detection.trackable:
                    self._tracks[track.numeric_id] = track
                    association_state = "new_track"
                else:
                    association_state = "singleton_outside_calibrated_support"
                self._diagnostics.append(
                    {
                        "frame_index": telemetry.frame_index,
                        "track_id": track.track_id,
                        "association_state": association_state,
                        "residual_floor_um": None,
                        "residual_squared_um2": None,
                        "gate_um": None,
                        "frame_delta": None,
                        "encoder_delta_um": None,
                        "raw_label_conflict": False,
                    }
                )
            candidate_rows.sort(key=lambda row: row[0])
            self._prediction_frames.append(
                {
                    "record_type": "frame_prediction",
                    "frame_id": frame_id,
                    "candidates": [row for _, row in candidate_rows],
                }
            )
            self._seen_frame_ids.add(frame_id)
            self._last_telemetry = telemetry
        except TrackerContractError as exc:
            self._invalidate(exc)
            raise

    def finish_sequence(self) -> dict[str, Any]:
        if self.state != STATE_ACTIVE:
            _fail("INVALID_STATE", "finish_sequence requires ACTIVE state")
        payload = {
            "contract_id": CONTRACT_ID,
            "status": "TRACKER_SEQUENCE_VALID",
            "prediction_frames": copy.deepcopy(self._prediction_frames),
            "diagnostic_sidecar": copy.deepcopy(self._diagnostics),
        }
        payload["canonical_prediction_sha256"] = hashlib.sha256(
            canonical_json_bytes(payload["prediction_frames"])
        ).hexdigest()
        self.state = STATE_FINALIZED
        self._tracks.clear()
        return payload

    def failure_receipt(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._failure)

    def _validate_frame_telemetry(self, frame_id: str, telemetry: FrameTelemetry) -> None:
        if not isinstance(frame_id, str) or not frame_id:
            _fail("INVALID_FRAME_ORDER", "frame ID must be a non-empty opaque string")
        if frame_id in self._seen_frame_ids:
            _fail("INVALID_FRAME_ORDER", "duplicate opaque frame ID")
        if isinstance(telemetry.frame_index, bool) or not isinstance(telemetry.frame_index, int):
            _fail("INVALID_FRAME_ORDER", "frame index must be integer")
        expected_index = (
            self._first_frame_index
            if self._last_telemetry is None
            else self._last_telemetry.frame_index + 1
        )
        if telemetry.frame_index != expected_index:
            _fail(
                "INVALID_FRAME_ORDER",
                f"expected frame index {expected_index}, observed {telemetry.frame_index}",
            )
        if isinstance(telemetry.timestamp_ns, bool) or not isinstance(telemetry.timestamp_ns, int):
            _fail("INVALID_TIMESTAMP", "timestamp must be integer ns")
        if self._last_telemetry is not None and telemetry.timestamp_ns <= self._last_telemetry.timestamp_ns:
            _fail("INVALID_TIMESTAMP", "timestamps must be strictly increasing")
        if telemetry.encoder_position_um is None:
            _fail("MISSING_ENCODER", "encoder position is missing")
        if isinstance(telemetry.encoder_position_um, bool) or not isinstance(
            telemetry.encoder_position_um, int
        ):
            _fail("MISSING_ENCODER", "encoder position must be integer um")
        if telemetry.trigger_encoder_delta_us is None:
            _fail("MISSING_ENCODER", "trigger/encoder delta is missing")
        if isinstance(telemetry.trigger_encoder_delta_us, bool) or not isinstance(
            telemetry.trigger_encoder_delta_us, int
        ):
            _fail("UNSYNCHRONIZED_ENCODER", "trigger/encoder delta must be integer us")
        if abs(telemetry.trigger_encoder_delta_us) > self.contract.trigger_encoder_delta_maximum_us:
            _fail("UNSYNCHRONIZED_ENCODER", "trigger/encoder delta exceeds 250 us")
        if telemetry.encoder_age_us is None:
            _fail("MISSING_ENCODER", "encoder age is missing")
        if isinstance(telemetry.encoder_age_us, bool) or not isinstance(
            telemetry.encoder_age_us, int
        ):
            _fail("STALE_ENCODER", "encoder age must be integer us")
        if not 0 <= telemetry.encoder_age_us <= self.contract.encoder_stale_no_fire_after_us:
            _fail("STALE_ENCODER", "encoder sample age exceeds 5 ms")
        assert self._homography is not None
        if telemetry.homography_binding_id != self._homography.receipt_sha256:
            _fail("HOMOGRAPHY_BINDING_DRIFT", "homography identity changed within video")
        if self._last_telemetry is not None:
            assert self._last_telemetry.encoder_position_um is not None
            encoder_delta = telemetry.encoder_position_um - self._last_telemetry.encoder_position_um
            if encoder_delta < 0:
                _fail(
                    "REVERSE_OR_AMBIGUOUS_DIRECTION",
                    "encoder position decreased inside forward-only proof",
                )
            elapsed_ns = telemetry.timestamp_ns - self._last_telemetry.timestamp_ns
            maximum_travel = ceil_div(
                elapsed_ns * self.contract.maximum_forward_speed_um_s, 1_000_000_000
            ) + self.contract.travel_envelope_endpoint_tolerance_um
            if encoder_delta > maximum_travel:
                _fail(
                    "TRAVEL_OUTSIDE_PROOF_ENVELOPE",
                    f"encoder delta {encoder_delta} um exceeds {maximum_travel} um envelope",
                )

    def _expire_tracks(self, frame_index: int) -> None:
        expired = [
            numeric_id
            for numeric_id, track in self._tracks.items()
            if frame_index - track.last_frame_index > self.contract.maximum_frame_index_delta
        ]
        for numeric_id in sorted(expired):
            track = self._tracks.pop(numeric_id)
            self._diagnostics.append(
                {
                    "frame_index": frame_index,
                    "track_id": track.track_id,
                    "association_state": "expired_before_association",
                    "residual_floor_um": None,
                    "residual_squared_um2": None,
                    "gate_um": None,
                    "frame_delta": frame_index - track.last_frame_index,
                    "encoder_delta_um": None,
                    "raw_label_conflict": False,
                }
            )

    def _new_track(self, detection: PreparedDetection, telemetry: FrameTelemetry) -> TrackState:
        if self._next_track_id > self.contract.maximum_track_id:
            _fail("TRACK_ID_OVERFLOW", "video-scoped tracker ID counter overflow")
        assert telemetry.encoder_position_um is not None
        numeric_id = self._next_track_id
        self._next_track_id += 1
        track_id = f"trk_{numeric_id:06d}"
        if TRACK_ID_RE.fullmatch(track_id) is None:
            raise RuntimeError("internal tracker ID formatting failed")
        return TrackState(
            numeric_id=numeric_id,
            track_id=track_id,
            last_frame_index=telemetry.frame_index,
            last_encoder_position_um=telemetry.encoder_position_um,
            anchor_um=detection.anchor_um,
            emitted_class_name=detection.source.class_name,
        )

    @staticmethod
    def _candidate_row(
        track: TrackState, detection: PreparedDetection, conflict: bool
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "predicted_track_id": track.track_id,
            "class_name": track.emitted_class_name,
            "confidence": 0.0 if conflict else float(detection.source.confidence),
            "polygon": [list(point) for point in detection.source.polygon],
        }
        if track.emitted_class_name == "weed":
            row["action_point"] = list(detection.source.action_point)
        return row

    def _invalidate(self, error: TrackerContractError) -> None:
        self._tracks.clear()
        self._prediction_frames.clear()
        self._diagnostics.clear()
        self.state = STATE_INVALID
        self._failure = {
            "contract_id": CONTRACT_ID,
            "status": STATE_INVALID,
            "failure_code": error.code,
            "reason": str(error),
            "publishable_prediction": False,
            "partial_prediction_discarded": True,
            "field_go": False,
            "product_go": False,
            "chemical_fire_allowed": False,
        }


def _receipt_id(payload_without_receipt_id: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload_without_receipt_id)).hexdigest()


def build_neutral_calibration_fixture_payloads(
    contract: TrackerContract,
) -> dict[str, bytes]:
    """Build a deterministic, target-free mechanics fixture entirely in memory."""

    origin_u = 1024.5
    origin_v = 1024.5
    gsd_mm_px = NEUTRAL_GROUND_FOV_MM / contract.width_px
    homography_body: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": "neutral_planar_fiducial_homography_v1",
        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
        "direction": HOMOGRAPHY_DIRECTION,
        "pixel_space_id": contract.pixel_space_id,
        "preprocessing_sha256": contract.preprocessing_sha256,
        "matrix_i2g": [
            [gsd_mm_px, 0.0, -gsd_mm_px * origin_u],
            [0.0, gsd_mm_px, -gsd_mm_px * origin_v],
            [0.0, 0.0, 1.0],
        ],
        "support_polygon_px": [
            [64.0, 64.0],
            [1984.0, 64.0],
            [1984.0, 1984.0],
            [64.0, 1984.0],
        ],
        "residual_p95_mm": 0.0,
        "residual_max_mm": 0.0,
        "daily_registration_drift_mm": 0.0,
        "orientation_witnesses": [
            {
                "role": "origin",
                "pixel_xy": [origin_u, origin_v],
                "ground_xy_mm": [0.0, 0.0],
            },
            {
                "role": "forward",
                "pixel_xy": [origin_u + 128.0, origin_v],
                "ground_xy_mm": [30.0, 0.0],
            },
            {
                "role": "right",
                "pixel_xy": [origin_u, origin_v + 128.0],
                "ground_xy_mm": [0.0, 30.0],
            },
        ],
    }
    homography_payload = dict(homography_body)
    homography_payload["receipt_sha256"] = _receipt_id(homography_body)

    encoder_body: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": "neutral_encoder_acceptance_fixture_v1",
        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
        "same_hardware_event": True,
        "positive_axis": "product_ground_positive_x",
        "resolution_um_per_count": contract.encoder_resolution_maximum_um_per_count,
        "scale_error_um_per_m": contract.encoder_scale_error_maximum_um_per_m,
        "trigger_encoder_delta_limit_us": contract.trigger_encoder_delta_maximum_us,
        "stale_after_us": contract.encoder_stale_no_fire_after_us,
    }
    encoder_payload = dict(encoder_body)
    encoder_payload["receipt_sha256"] = _receipt_id(encoder_body)

    timing_rows: list[dict[str, Any]] = []
    witness_rows: list[dict[str, Any]] = []
    left, top, right, bottom = contract.central_support_xyxy_px
    x_positions_mm = tuple(range(-300, 2281, 30))
    y_positions_mm = (-180, 0, 180)
    grid = tuple(
        (x_mm, y_mm)
        for x_mm in x_positions_mm
        for y_mm in y_positions_mm
    )
    for speed_um_s in NEUTRAL_SPEEDS_UM_S:
        sequence_id = f"neutral_linear_{speed_um_s:07d}um_s_v1"
        for frame_index in range(NEUTRAL_FRAMES_PER_SPEED):
            timestamp_ns = round(frame_index * 1_000_000_000 / 15)
            encoder_um = (frame_index * speed_um_s + 7) // 15
            timing_rows.append(
                {
                    "record_type": "calibration_frame_timing",
                    "fixture_id": NEUTRAL_FIXTURE_ID,
                    "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
                    "sequence_id": sequence_id,
                    "speed_um_s": speed_um_s,
                    "frame_index": frame_index,
                    "timestamp_ns": timestamp_ns,
                    "encoder_position_um": encoder_um,
                    "trigger_encoder_delta_us": 0,
                    "encoder_age_us": 0,
                    "homography_binding_id": homography_payload["receipt_sha256"],
                }
            )
            for grid_index, (world_x_mm, world_y_mm) in enumerate(grid, start=1):
                if grid_index % 5 == 0 and frame_index % 2 == 1:
                    continue
                local_x_mm = world_x_mm - encoder_um / 1000.0
                u = origin_u + local_x_mm / gsd_mm_px
                v = origin_v + world_y_mm / gsd_mm_px
                if not (left <= u < right and top <= v < bottom):
                    continue
                witness_rows.append(
                    {
                        "record_type": "calibration_fiducial_observation",
                        "fixture_id": NEUTRAL_FIXTURE_ID,
                        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
                        "sequence_id": sequence_id,
                        "frame_index": frame_index,
                        "witness_id": f"fid_{grid_index:04d}",
                        "pixel_xy": [round(u, 9), round(v, 9)],
                    }
                )

    payloads: dict[str, bytes] = {
        "frame_timing": canonical_jsonl_bytes(timing_rows),
        "homography_receipt": canonical_json_bytes(homography_payload),
        "encoder_receipt": canonical_json_bytes(encoder_payload),
        "calibration_witnesses": canonical_jsonl_bytes(witness_rows),
    }
    generation_receipt = {
        "schema_version": 1,
        "fixture_id": NEUTRAL_FIXTURE_ID,
        "status": "NEUTRAL_CALIBRATION_FIXTURE_GENERATED",
        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
        "basis": {
            "pixel_space_id": contract.pixel_space_id,
            "nominal_ground_fov_mm": NEUTRAL_GROUND_FOV_MM,
            "frame_rate_hz": 15,
            "speed_um_s": list(NEUTRAL_SPEEDS_UM_S),
            "frames_per_speed": NEUTRAL_FRAMES_PER_SPEED,
            "central_support_xyxy_px": list(contract.central_support_xyxy_px),
        },
        "files": {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in sorted(payloads.items())
        },
        "model_loaded": False,
        "target_gt_accessed": False,
        "locked_test_accessed": False,
        "field_go": False,
        "product_go": False,
        "chemical_fire_allowed": False,
    }
    payloads["generation_receipt"] = canonical_json_bytes(generation_receipt)
    return payloads


def write_neutral_calibration_fixture(
    contract: TrackerContract, output_directory: Path
) -> dict[str, Any]:
    directory = _require_lane_write_path(output_directory)
    if not _path_within(directory, LANE_RUN_ROOT):
        _fail(
            "TRACKER_INVALID_SCOPE_VIOLATION",
            "neutral calibration fixture must be written under the lane run root",
        )
    file_names = {
        "frame_timing": "frame_timing.jsonl",
        "homography_receipt": "homography_receipt_v1.json",
        "encoder_receipt": "encoder_receipt_v1.json",
        "calibration_witnesses": "calibration_witnesses_v1.jsonl",
        "generation_receipt": "fixture_generation_receipt_v1.json",
    }
    payloads = build_neutral_calibration_fixture_payloads(contract)
    output: dict[str, dict[str, str]] = {}
    for name in sorted(file_names):
        path = directory / file_names[name]
        payload = payloads[name]
        _write_immutable_bytes(path, payload)
        output[name] = {
            "path": _repo_relative(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    return {
        "fixture_id": NEUTRAL_FIXTURE_ID,
        "status": "NEUTRAL_CALIBRATION_FIXTURE_GENERATED",
        "files": output,
        "model_loaded": False,
        "target_gt_accessed": False,
        "locked_test_accessed": False,
    }


def _parse_canonical_json(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", f"invalid {label}: {exc}")
    row = _mapping(value, label)
    if canonical_json_bytes(row) != payload:
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            f"{label} is not canonical JSON",
        )
    return row


def _parse_canonical_jsonl(payload: bytes, label: str) -> tuple[Mapping[str, Any], ...]:
    if not payload or not payload.endswith(b"\n"):
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", f"{label} is empty or unterminated")
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(
                "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
                f"invalid {label} line {line_number}: {exc}",
            )
        rows.append(_mapping(value, f"{label} line {line_number}"))
    if canonical_jsonl_bytes(rows) != payload:
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            f"{label} is not canonical JSONL",
        )
    return tuple(rows)


CALIBRATION_FORBIDDEN_KEYS = frozenset(
    {
        "arm",
        "pair_id",
        "condition",
        "split",
        "source_object_id",
        "stable_gt_track_id",
        "target_gt",
        "botanical_gt",
        "semantic_gt",
        "locked_test",
        "locked_test_input",
        "model_output",
        "model_prediction",
        "action_outcome",
        "class_name",
        "confidence",
        "action_point",
        "predicted_track_id",
        "renderer_trajectory",
        "latent_trajectory",
    }
)


def reject_forbidden_calibration_scope(value: Any, label: str = "calibration input") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).lower()
            if key in CALIBRATION_FORBIDDEN_KEYS or key.startswith("gt_"):
                _fail(
                    "TRACKER_INVALID_SCOPE_VIOLATION",
                    f"{label} contains forbidden field {raw_key!r}",
                )
            reject_forbidden_calibration_scope(nested, f"{label}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            reject_forbidden_calibration_scope(nested, f"{label}[{index}]")


def _require_exact_fields(row: Mapping[str, Any], expected: set[str], label: str) -> None:
    observed = {str(key) for key in row}
    if observed != expected:
        _fail(
            "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
            f"{label} fields changed: expected {sorted(expected)}, observed {sorted(observed)}",
        )


def load_calibration_fixture_lock(
    config_path: Path,
    *,
    repo_root: Path = PROJECT_ROOT,
) -> CalibrationFixtureLock:
    try:
        config_value = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _fail("INVALID_CONFIG_OR_SOURCE_LOCK", f"cannot load calibration fixture lock: {exc}")
    config = _mapping(config_value, "tracker config")
    raw_lock = _mapping(config.get("calibration_fixture_lock"), "calibration_fixture_lock")
    _require_exact_fields(
        raw_lock,
        {"fixture_id", "evidence_scope", "implementation", "files"},
        "calibration_fixture_lock",
    )
    if raw_lock["fixture_id"] != NEUTRAL_FIXTURE_ID:
        _fail("TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT", "calibration fixture ID changed")
    if raw_lock["evidence_scope"] != NEUTRAL_FIXTURE_SCOPE:
        _fail("TRACKER_INVALID_SCOPE_VIOLATION", "calibration fixture scope changed")
    implementation = _mapping(raw_lock["implementation"], "calibration implementation lock")
    _require_exact_fields(implementation, {"path", "sha256"}, "implementation lock")
    implementation_relative = implementation["path"]
    if not isinstance(implementation_relative, str) or Path(implementation_relative).is_absolute():
        _fail("TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT", "implementation path is invalid")
    root = repo_root.resolve()
    implementation_path = (root / implementation_relative).resolve()
    try:
        implementation_path.relative_to(root)
    except ValueError:
        _fail("TRACKER_INVALID_SCOPE_VIOLATION", "implementation lock escapes repository")
    if implementation_path != Path(__file__).resolve():
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            "calibration implementation lock does not identify this tracker module",
        )
    implementation_sha256 = _exact_sha256(
        implementation["sha256"], "calibration implementation SHA-256"
    )
    _require_expected_sha256(
        implementation_path,
        implementation_sha256,
        "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
        "tracker implementation",
    )

    files_raw = _mapping(raw_lock["files"], "calibration fixture files")
    expected_names = {
        "frame_timing",
        "homography_receipt",
        "encoder_receipt",
        "calibration_witnesses",
        "generation_receipt",
    }
    if set(files_raw) != expected_names:
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            "calibration fixture file-lock set changed",
        )
    files: list[CalibrationFileLock] = []
    for name in sorted(expected_names):
        raw_file = _mapping(files_raw[name], f"calibration file lock {name}")
        _require_exact_fields(raw_file, {"path", "sha256"}, f"calibration file lock {name}")
        relative = raw_file["path"]
        if not isinstance(relative, str) or Path(relative).is_absolute():
            _fail("TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT", f"invalid {name} path")
        if ".." in Path(relative).parts:
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", f"{name} path traverses upward")
        path = (root / relative).resolve()
        if not _path_within(path, LANE_RUN_ROOT):
            _fail(
                "TRACKER_INVALID_SCOPE_VIOLATION",
                f"{name} is outside the isolated calibration run root",
            )
        expected_hash = _exact_sha256(raw_file["sha256"], f"{name} SHA-256")
        payload = _require_expected_sha256(
            path,
            expected_hash,
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            name,
        )
        files.append(CalibrationFileLock(name, path, expected_hash, payload))
    return CalibrationFixtureLock(
        fixture_id=NEUTRAL_FIXTURE_ID,
        evidence_scope=NEUTRAL_FIXTURE_SCOPE,
        implementation_path=implementation_path,
        implementation_sha256=implementation_sha256,
        files=tuple(files),
    )


def _round_scaled(value: float, scale: int) -> int:
    return int(
        (Decimal(repr(value)) * Decimal(scale)).to_integral_value(rounding=ROUND_HALF_EVEN)
    )


def _nearest_rank(values: Sequence[int], percentile_numerator: int = 95) -> int:
    if not values:
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "metric vector is empty")
    ordered = sorted(values)
    index = ceil_div(percentile_numerator * len(ordered), 100) - 1
    return ordered[index]


def _median_rounded(values: Sequence[int]) -> int:
    if not values:
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "metric vector is empty")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return int(
        (Decimal(ordered[middle - 1] + ordered[middle]) / Decimal(2)).to_integral_value(
            rounding=ROUND_HALF_EVEN
        )
    )


def _metric_summary(values: Sequence[int], integer_unit: str, display_unit: str, divisor: int) -> dict[str, Any]:
    median = _median_rounded(values)
    p95 = _nearest_rank(values)
    maximum = max(values)
    return {
        f"median_{integer_unit}": median,
        f"p95_{integer_unit}": p95,
        f"maximum_{integer_unit}": maximum,
        f"median_{display_unit}": round(median / divisor, 6),
        f"p95_{display_unit}": round(p95 / divisor, 6),
        f"maximum_{display_unit}": round(maximum / divisor, 6),
        "p95_definition": "nearest_rank_ceiling_0p95_n",
    }


def audit_calibration_payloads(
    contract: TrackerContract,
    payloads: Mapping[str, bytes],
    *,
    config_path: Path,
    config_sha256: str,
    implementation_path: Path,
    implementation_sha256: str,
    input_locks: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    required_payloads = {
        "frame_timing",
        "homography_receipt",
        "encoder_receipt",
        "calibration_witnesses",
        "generation_receipt",
    }
    if set(payloads) != required_payloads or set(input_locks) != required_payloads:
        _fail(
            "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
            "calibration payload set is incomplete or has unexpected inputs",
        )
    config_sha256 = _exact_sha256(config_sha256, "tracker config SHA-256")
    implementation_sha256 = _exact_sha256(
        implementation_sha256, "tracker implementation SHA-256"
    )

    generation = _parse_canonical_json(payloads["generation_receipt"], "generation receipt")
    _require_exact_fields(
        generation,
        {
            "schema_version",
            "fixture_id",
            "status",
            "evidence_scope",
            "basis",
            "files",
            "model_loaded",
            "target_gt_accessed",
            "locked_test_accessed",
            "field_go",
            "product_go",
            "chemical_fire_allowed",
        },
        "generation receipt",
    )
    if generation["fixture_id"] != NEUTRAL_FIXTURE_ID or generation[
        "evidence_scope"
    ] != NEUTRAL_FIXTURE_SCOPE:
        _fail("TRACKER_INVALID_SCOPE_VIOLATION", "generation receipt scope or ID changed")
    for flag in (
        "model_loaded",
        "target_gt_accessed",
        "locked_test_accessed",
        "field_go",
        "product_go",
        "chemical_fire_allowed",
    ):
        if generation[flag] is not False:
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", f"generation receipt flag {flag} is unsafe")
    generated_hashes = _mapping(generation["files"], "generation receipt file hashes")
    for name in sorted(required_payloads - {"generation_receipt"}):
        expected = _exact_sha256(generated_hashes.get(name), f"generated {name} SHA-256")
        observed = hashlib.sha256(payloads[name]).hexdigest()
        if observed != expected:
            _fail(
                "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
                f"generation receipt hash mismatch for {name}",
            )

    homography_raw = _parse_canonical_json(
        payloads["homography_receipt"], "homography receipt"
    )
    encoder_raw = _parse_canonical_json(payloads["encoder_receipt"], "encoder receipt")
    timing_rows = _parse_canonical_jsonl(payloads["frame_timing"], "frame timing")
    witness_rows = _parse_canonical_jsonl(
        payloads["calibration_witnesses"], "calibration witnesses"
    )
    for label, value in (
        ("homography receipt", homography_raw),
        ("encoder receipt", encoder_raw),
        ("frame timing", timing_rows),
        ("calibration witnesses", witness_rows),
    ):
        reject_forbidden_calibration_scope(value, label)
    homography = homography_binding_from_mapping(homography_raw, contract)
    encoder = encoder_binding_from_mapping(encoder_raw, contract)

    timing_fields = {
        "record_type",
        "fixture_id",
        "evidence_scope",
        "sequence_id",
        "speed_um_s",
        "frame_index",
        "timestamp_ns",
        "encoder_position_um",
        "trigger_encoder_delta_us",
        "encoder_age_us",
        "homography_binding_id",
    }
    timing_by_sequence: dict[str, list[Mapping[str, Any]]] = {}
    telemetry_lookup: dict[tuple[str, int], FrameTelemetry] = {}
    speed_by_sequence: dict[str, int] = {}
    for row_index, row in enumerate(timing_rows):
        _require_exact_fields(row, timing_fields, f"frame timing row {row_index}")
        if (
            row["record_type"] != "calibration_frame_timing"
            or row["fixture_id"] != NEUTRAL_FIXTURE_ID
            or row["evidence_scope"] != NEUTRAL_FIXTURE_SCOPE
        ):
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", "frame timing scope marker changed")
        sequence_id = row["sequence_id"]
        if not isinstance(sequence_id, str) or not sequence_id.startswith("neutral_linear_"):
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", "frame timing sequence ID is not neutral")
        speed_um_s = _exact_int(row["speed_um_s"], "fixture speed")
        if speed_um_s not in NEUTRAL_SPEEDS_UM_S:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "unexpected calibration speed")
        prior_speed = speed_by_sequence.setdefault(sequence_id, speed_um_s)
        if prior_speed != speed_um_s:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "speed changes within a sequence")
        timing_by_sequence.setdefault(sequence_id, []).append(row)

    observed_speeds = sorted(speed_by_sequence.values())
    if observed_speeds != list(NEUTRAL_SPEEDS_UM_S) or len(timing_by_sequence) != 2:
        _fail(
            "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
            "exactly one 0.5 and one 1.0 m/s calibration sequence are required",
        )
    maximum_latch_delta_us = 0
    maximum_encoder_age_us = 0
    for sequence_id in sorted(timing_by_sequence):
        rows = sorted(timing_by_sequence[sequence_id], key=lambda item: item["frame_index"])
        speed_um_s = speed_by_sequence[sequence_id]
        if len(rows) != contract.calibration_required_frames_per_speed:
            _fail(
                "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
                f"{sequence_id} does not have exactly 30 timing rows",
            )
        instance = EgoMotionTracker(contract)
        instance.start_sequence(homography, encoder)
        for expected_frame_index, row in enumerate(rows):
            frame_index = _exact_int(row["frame_index"], "calibration frame index")
            timestamp_ns = _exact_int(row["timestamp_ns"], "calibration timestamp")
            encoder_position_um = _exact_int(
                row["encoder_position_um"], "calibration encoder position"
            )
            trigger_encoder_delta_us = _exact_int(
                row["trigger_encoder_delta_us"], "calibration latch delta"
            )
            encoder_age_us = _exact_int(row["encoder_age_us"], "calibration encoder age")
            if frame_index != expected_frame_index:
                _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "calibration frames are incomplete")
            if timestamp_ns != round(frame_index * 1_000_000_000 / 15):
                _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "calibration timing is not 15 Hz")
            if encoder_position_um != (frame_index * speed_um_s + 7) // 15:
                _fail(
                    "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
                    "calibration encoder travel does not match the declared proof speed",
                )
            if row["homography_binding_id"] != homography.receipt_sha256:
                _fail("HOMOGRAPHY_BINDING_DRIFT", "calibration timing homography ID drifted")
            telemetry = FrameTelemetry(
                frame_index=frame_index,
                timestamp_ns=timestamp_ns,
                encoder_position_um=encoder_position_um,
                trigger_encoder_delta_us=trigger_encoder_delta_us,
                encoder_age_us=encoder_age_us,
                homography_binding_id=str(row["homography_binding_id"]),
            )
            telemetry_lookup[(sequence_id, frame_index)] = telemetry
            maximum_latch_delta_us = max(
                maximum_latch_delta_us, abs(trigger_encoder_delta_us)
            )
            maximum_encoder_age_us = max(maximum_encoder_age_us, encoder_age_us)
            instance.process_frame(f"{sequence_id}:{frame_index:02d}", telemetry, ())
        instance.finish_sequence()

    witness_fields = {
        "record_type",
        "fixture_id",
        "evidence_scope",
        "sequence_id",
        "frame_index",
        "witness_id",
        "pixel_xy",
    }
    observations: dict[tuple[str, str], list[dict[str, Any]]] = {}
    observed_pixels: dict[str, list[tuple[float, float]]] = {
        sequence_id: [] for sequence_id in timing_by_sequence
    }
    seen_observations: set[tuple[str, int, str]] = set()
    seen_frame_pixels: set[tuple[str, int, float, float]] = set()
    for row_index, row in enumerate(witness_rows):
        _require_exact_fields(row, witness_fields, f"calibration witness row {row_index}")
        if (
            row["record_type"] != "calibration_fiducial_observation"
            or row["fixture_id"] != NEUTRAL_FIXTURE_ID
            or row["evidence_scope"] != NEUTRAL_FIXTURE_SCOPE
        ):
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", "witness scope marker changed")
        sequence_id = row["sequence_id"]
        frame_index = _exact_int(row["frame_index"], "witness frame index")
        witness_id = row["witness_id"]
        if sequence_id not in timing_by_sequence:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "witness sequence is unknown")
        if not isinstance(witness_id, str) or re.fullmatch(r"fid_[0-9]{4}", witness_id) is None:
            _fail("TRACKER_INVALID_SCOPE_VIOLATION", "witness ID is not a neutral fiducial ID")
        pixel_values = _sequence(row["pixel_xy"], "witness pixel")
        if len(pixel_values) != 2:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "witness pixel must be 2D")
        pixel = (
            _finite_number(pixel_values[0], "witness pixel u"),
            _finite_number(pixel_values[1], "witness pixel v"),
        )
        telemetry = telemetry_lookup.get((sequence_id, frame_index))
        if telemetry is None:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "witness frame has no timing row")
        left, top, right, bottom = contract.central_support_xyxy_px
        if not (left <= pixel[0] < right and top <= pixel[1] < bottom):
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "witness leaves central support")
        if not point_in_polygon_inclusive(pixel, homography.support_polygon_px):
            _fail("INVALID_HOMOGRAPHY_BINDING", "witness leaves homography support")
        identity_key = (str(sequence_id), frame_index, witness_id)
        pixel_key = (str(sequence_id), frame_index, pixel[0], pixel[1])
        if identity_key in seen_observations or pixel_key in seen_frame_pixels:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "duplicate witness observation")
        seen_observations.add(identity_key)
        seen_frame_pixels.add(pixel_key)
        assert telemetry.encoder_position_um is not None
        epoch = telemetry_lookup[(str(sequence_id), 0)].encoder_position_um
        assert epoch is not None
        relative_encoder_um = telemetry.encoder_position_um - epoch
        local_mm = project_pixel_to_ground_mm(
            homography, pixel, contract.projection_denominator_minimum
        )
        local_um = (
            _round_ground_mm_to_um(local_mm[0], contract.quantization_um),
            _round_ground_mm_to_um(local_mm[1], contract.quantization_um),
        )
        observations.setdefault((str(sequence_id), witness_id), []).append(
            {
                "frame_index": frame_index,
                "pixel": pixel,
                "local_um": local_um,
                "positive_um": (local_um[0] + relative_encoder_um, local_um[1]),
                "wrong_sign_um": (local_um[0] - relative_encoder_um, local_um[1]),
                "encoder_position_um": telemetry.encoder_position_um,
            }
        )
        observed_pixels[str(sequence_id)].append(pixel)

    for sequence_id, pixels in observed_pixels.items():
        if not pixels:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "calibration witnesses are absent")
        left, top, right, bottom = contract.central_support_xyxy_px
        width = right - left
        height = bottom - top
        if (
            min(point[0] for point in pixels) > left + 0.25 * width
            or max(point[0] for point in pixels) < right - 0.25 * width
            or min(point[1] for point in pixels) > top + 0.25 * height
            or max(point[1] for point in pixels) < bottom - 0.25 * height
        ):
            _fail(
                "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
                f"{sequence_id} witnesses do not span the central support",
            )

    metric_vectors: dict[int, dict[str, list[int]]] = {
        speed: {
            "raw_micropx": [],
            "local_um": [],
            "positive_um": [],
            "wrong_um": [],
            "gate_um": [],
            "frame_delta": [],
        }
        for speed in NEUTRAL_SPEEDS_UM_S
    }
    persistent_ids: dict[int, set[str]] = {speed: set() for speed in NEUTRAL_SPEEDS_UM_S}
    positive_violations: list[dict[str, Any]] = []
    wrong_sign_violations: dict[int, int] = {speed: 0 for speed in NEUTRAL_SPEEDS_UM_S}
    for (sequence_id, witness_id), rows in sorted(observations.items()):
        ordered = sorted(rows, key=lambda item: item["frame_index"])
        speed = speed_by_sequence[sequence_id]
        for previous, current in zip(ordered, ordered[1:]):
            frame_delta = current["frame_index"] - previous["frame_index"]
            if not 1 <= frame_delta <= contract.maximum_frame_index_delta:
                continue
            persistent_ids[speed].add(witness_id)
            travel_um = current["encoder_position_um"] - previous["encoder_position_um"]
            gate_um = contract.dynamic_gate_um(travel_um)
            raw_dx = current["pixel"][0] - previous["pixel"][0]
            raw_dy = current["pixel"][1] - previous["pixel"][1]
            raw_micropx = _round_scaled(math.hypot(raw_dx, raw_dy), 1_000_000)

            def distance_um(key: str) -> int:
                dx = current[key][0] - previous[key][0]
                dy = current[key][1] - previous[key][1]
                return math.isqrt(dx * dx + dy * dy)

            local_um = distance_um("local_um")
            positive_um = distance_um("positive_um")
            wrong_um = distance_um("wrong_sign_um")
            vectors = metric_vectors[speed]
            vectors["raw_micropx"].append(raw_micropx)
            vectors["local_um"].append(local_um)
            vectors["positive_um"].append(positive_um)
            vectors["wrong_um"].append(wrong_um)
            vectors["gate_um"].append(gate_um)
            vectors["frame_delta"].append(frame_delta)
            if positive_um > gate_um:
                positive_violations.append(
                    {
                        "sequence_id": sequence_id,
                        "witness_id": witness_id,
                        "from_frame": previous["frame_index"],
                        "to_frame": current["frame_index"],
                        "residual_um": positive_um,
                        "gate_um": gate_um,
                    }
                )
            if wrong_um > gate_um:
                wrong_sign_violations[speed] += 1

    speed_summaries: dict[str, Any] = {}
    for speed in NEUTRAL_SPEEDS_UM_S:
        vectors = metric_vectors[speed]
        if len(persistent_ids[speed]) < contract.calibration_minimum_persistent_fiducials:
            _fail(
                "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
                f"speed {speed} has fewer than nine persistent calibration fiducials",
            )
        if not vectors["raw_micropx"]:
            _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "no eligible transitions")
        speed_key = "speed_0p5_m_s" if speed == 500_000 else "speed_1p0_m_s"
        sequence_id = next(
            sequence for sequence, sequence_speed in speed_by_sequence.items() if sequence_speed == speed
        )
        speed_summaries[speed_key] = {
            "speed_um_s": speed,
            "frame_count": len(timing_by_sequence[sequence_id]),
            "observation_count": len(observed_pixels[sequence_id]),
            "persistent_fiducial_count": len(persistent_ids[speed]),
            "eligible_transition_count": len(vectors["raw_micropx"]),
            "frame_delta_counts": {
                "1": vectors["frame_delta"].count(1),
                "2": vectors["frame_delta"].count(2),
            },
            "raw_pixel_displacement": _metric_summary(
                vectors["raw_micropx"], "micropx", "px", 1_000_000
            ),
            "camera_local_ground_displacement": _metric_summary(
                vectors["local_um"], "um", "mm", 1000
            ),
            "positive_sign_compensated_residual": _metric_summary(
                vectors["positive_um"], "um", "mm", 1000
            ),
            "wrong_sign_negative_control_residual": _metric_summary(
                vectors["wrong_um"], "um", "mm", 1000
            ),
            "dynamic_gate": _metric_summary(vectors["gate_um"], "um", "mm", 1000),
            "positive_sign_gate_violation_count": sum(
                1 for residual, gate in zip(vectors["positive_um"], vectors["gate_um"]) if residual > gate
            ),
            "wrong_sign_gate_violation_count": wrong_sign_violations[speed],
        }

    if positive_violations:
        first = positive_violations[0]
        _fail(
            "REPLAN_REQUIRED_HOMOGRAPHY_OR_ENCODER",
            "positive-sign calibration residual exceeds gate: "
            f"witness={first['witness_id']} transition={first['from_frame']}->{first['to_frame']} "
            f"residual_um={first['residual_um']} gate_um={first['gate_um']}",
        )
    one_m = speed_summaries["speed_1p0_m_s"]
    raw_p95_px = one_m["raw_pixel_displacement"]["p95_px"]
    if raw_p95_px <= contract.calibration_raw_pixel_ceiling_witness_px:
        _fail(
            "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
            f"1.0 m/s raw p95 {raw_p95_px} px does not exceed 160 px",
        )
    if (
        one_m["wrong_sign_gate_violation_count"] < 1
        or one_m["wrong_sign_negative_control_residual"]["p95_um"]
        <= one_m["positive_sign_compensated_residual"]["p95_um"]
    ):
        _fail(
            "TRACKER_INVALID_TRANSFORM_DIRECTION_TEST",
            "wrong-sign negative control did not separate from positive compensation",
        )
    maximum_dynamic_gate_um = max(
        max(vectors["gate_um"]) for vectors in metric_vectors.values()
    )
    if maximum_dynamic_gate_um != contract.hard_gate_ceiling_um:
        _fail(
            "TRACKER_NOT_READY_CALIBRATION_EVIDENCE",
            "neutral fixture did not exercise the hard 45 mm two-frame gate",
        )

    metric_core = {
        "speed_summaries": speed_summaries,
        "raw_pixel_p95_1m_s": raw_p95_px,
        "positive_sign_gate_violation_count": 0,
        "wrong_sign_gate_violation_count": sum(wrong_sign_violations.values()),
        "maximum_dynamic_gate_um": maximum_dynamic_gate_um,
        "maximum_latch_delta_us": maximum_latch_delta_us,
        "maximum_encoder_age_us": maximum_encoder_age_us,
    }
    deterministic_digest = hashlib.sha256(canonical_json_bytes(metric_core)).hexdigest()
    source_rows = [
        {
            "name": source.name,
            "path": source.path,
            "sha256": source.sha256,
            "role": source.role,
        }
        for source in contract.source_locks
    ]
    locked_inputs = {
        name: {
            "path": str(input_locks[name]["path"]),
            "sha256": _exact_sha256(input_locks[name]["sha256"], f"{name} lock SHA-256"),
        }
        for name in sorted(input_locks)
    }
    return {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "status": "TRACKER_CALIBRATION_MECHANICS_PASS",
        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
        "claim_boundary": {
            "installed_rig_homography_validated": False,
            "target_performance_claimed": False,
            "ready_for_parent_integration_after_release_seal": True,
            "parent_runtime_homography_binding_required": True,
        },
        "implementation_base_commit": contract.implementation_base_commit,
        "source_locks": source_rows,
        "tracker_config": {
            "path": _repo_relative(config_path),
            "sha256": config_sha256,
        },
        "tracker_implementation": {
            "path": _repo_relative(implementation_path),
            "sha256": implementation_sha256,
        },
        "calibration_inputs": locked_inputs,
        "coordinate_contract": {
            "homography_direction": HOMOGRAPHY_DIRECTION,
            "encoder_positive_axis": "product_ground_positive_x",
            "odometric_anchor_x": "camera_local_ground_x_mm_plus_relative_encoder_travel_mm",
            "odometric_anchor_y": "camera_local_ground_y_mm",
            "quantization_um": contract.quantization_um,
        },
        "gate_contract": {
            "fixed_budget_um": contract.fixed_budget_um,
            "maximum_canopy_relief_mm": contract.maximum_canopy_relief_mm,
            "minimum_camera_ground_distance_mm": contract.minimum_camera_ground_distance_mm,
            "hard_gate_ceiling_um": contract.hard_gate_ceiling_um,
            "formula": "ceil_mm(8500um+ceil(travel_um*110/410)+ceil(travel_um/1000))",
        },
        "homography_diagnostics": {
            "residual_p95_mm": homography.residual_p95_mm,
            "residual_max_mm": homography.residual_max_mm,
            "daily_registration_drift_mm": homography.daily_registration_drift_mm,
            "receipt_sha256": homography.receipt_sha256,
        },
        "encoder_diagnostics": {
            "resolution_um_per_count": encoder.resolution_um_per_count,
            "scale_error_um_per_m": encoder.scale_error_um_per_m,
            "trigger_encoder_delta_limit_us": encoder.trigger_encoder_delta_limit_us,
            "stale_after_us": encoder.stale_after_us,
            "maximum_observed_latch_delta_us": maximum_latch_delta_us,
            "maximum_observed_encoder_age_us": maximum_encoder_age_us,
            "receipt_sha256": encoder.receipt_sha256,
        },
        **metric_core,
        "deterministic_canonical_result_sha256": deterministic_digest,
        "forbidden_access_assertions": {
            "model_loaded": False,
            "model_outputs_present": False,
            "target_gt_accessed": False,
            "locked_test_accessed": False,
            "arm_or_pair_identity_accessed": False,
            "outcome_targets_accessed": False,
        },
        "field_go": False,
        "product_go": False,
        "dry_marker_go": False,
        "chemical_fire_allowed": False,
    }


def audit_calibration_fixture(
    contract: TrackerContract,
    fixture_lock: CalibrationFixtureLock,
    *,
    config_path: Path,
    config_sha256: str,
) -> dict[str, Any]:
    payloads = {item.name: item.payload for item in fixture_lock.files}
    input_locks = {
        item.name: {"path": _repo_relative(item.path), "sha256": item.sha256}
        for item in fixture_lock.files
    }
    return audit_calibration_payloads(
        contract,
        payloads,
        config_path=config_path,
        config_sha256=config_sha256,
        implementation_path=fixture_lock.implementation_path,
        implementation_sha256=fixture_lock.implementation_sha256,
        input_locks=input_locks,
    )


def seal_calibration_release(
    contract: TrackerContract,
    fixture_lock: CalibrationFixtureLock,
    *,
    config_path: Path,
    config_sha256: str,
    candidate_seed_0_path: Path,
    candidate_seed_1_path: Path,
    calibration_receipt_path: Path,
    release_lock_path: Path,
    validation_receipt_path: Path,
) -> dict[str, Any]:
    config_sha256 = _exact_sha256(config_sha256, "tracker config SHA-256")
    actual_config = _require_expected_sha256(
        config_path,
        config_sha256,
        "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
        "tracker config",
    )
    if hashlib.sha256(actual_config).hexdigest() != config_sha256:
        raise RuntimeError("config hash verification invariant failed")
    candidate_paths = (candidate_seed_0_path.resolve(), candidate_seed_1_path.resolve())
    for candidate_path in candidate_paths:
        if not _path_within(candidate_path, LANE_RUN_ROOT):
            _fail(
                "TRACKER_INVALID_SCOPE_VIOLATION",
                "determinism candidates must remain under the lane run root",
            )
    candidate_bytes = tuple(
        _read_bytes(path, "TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "audit candidate")
        for path in candidate_paths
    )
    if candidate_bytes[0] != candidate_bytes[1]:
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            "PYTHONHASHSEED=0 and PYTHONHASHSEED=1 audit candidates are not byte-identical",
        )
    candidate = _parse_canonical_json(candidate_bytes[0], "calibration audit candidate")
    if candidate.get("contract_id") != CONTRACT_ID or candidate.get("status") != (
        "TRACKER_CALIBRATION_MECHANICS_PASS"
    ):
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "audit candidate did not pass")
    tracker_config = _mapping(candidate.get("tracker_config"), "candidate tracker config")
    tracker_implementation = _mapping(
        candidate.get("tracker_implementation"), "candidate tracker implementation"
    )
    if tracker_config.get("sha256") != config_sha256:
        _fail("TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT", "candidate config hash drifted")
    if tracker_implementation.get("sha256") != fixture_lock.implementation_sha256:
        _fail(
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            "candidate implementation hash drifted",
        )
    assertions = _mapping(
        candidate.get("forbidden_access_assertions"), "candidate access assertions"
    )
    if any(value is not False for value in assertions.values()):
        _fail("TRACKER_INVALID_SCOPE_VIOLATION", "candidate contains unsafe access assertion")
    if candidate.get("positive_sign_gate_violation_count") != 0:
        _fail("REPLAN_REQUIRED_HOMOGRAPHY_OR_ENCODER", "positive-sign gate violation")
    if candidate.get("wrong_sign_gate_violation_count", 0) < 1:
        _fail(
            "TRACKER_INVALID_TRANSFORM_DIRECTION_TEST",
            "wrong-sign negative control did not violate the gate",
        )
    if candidate.get("raw_pixel_p95_1m_s", 0.0) <= (
        contract.calibration_raw_pixel_ceiling_witness_px
    ):
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "raw ceiling witness is absent")
    if candidate.get("maximum_dynamic_gate_um") != contract.hard_gate_ceiling_um:
        _fail("TRACKER_NOT_READY_CALIBRATION_EVIDENCE", "hard gate was not exercised")

    candidate_sha256 = hashlib.sha256(candidate_bytes[0]).hexdigest()
    final_receipt = copy.deepcopy(dict(candidate))
    final_receipt["status"] = "TRACKER_FROZEN_CALIBRATION_ONLY"
    final_receipt["determinism_proof"] = {
        "method": "separate_process_canonical_byte_comparison",
        "python_hash_seeds": [0, 1],
        "candidate_seed_0_path": _repo_relative(candidate_paths[0]),
        "candidate_seed_1_path": _repo_relative(candidate_paths[1]),
        "candidate_sha256": candidate_sha256,
        "byte_identical": True,
    }
    final_receipt["claim_boundary"]["release_sealed"] = True
    final_receipt_bytes = canonical_json_bytes(final_receipt)
    _write_immutable_bytes(calibration_receipt_path, final_receipt_bytes, result_only=True)
    calibration_receipt_sha256 = hashlib.sha256(final_receipt_bytes).hexdigest()

    if not TRACKER_TEST_PATH.is_file():
        _fail("TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT", "tracker test file is missing")
    test_sha256 = sha256_file(TRACKER_TEST_PATH)
    source_locks = {
        source.name: {
            "path": source.path,
            "sha256": source.sha256,
            "role": source.role,
        }
        for source in contract.source_locks
    }
    fixture_files = {
        item.name: {"path": _repo_relative(item.path), "sha256": item.sha256}
        for item in fixture_lock.files
    }
    identity_core = {
        "contract_id": CONTRACT_ID,
        "tracker_config_sha256": config_sha256,
        "tracker_implementation_sha256": fixture_lock.implementation_sha256,
        "tracker_test_sha256": test_sha256,
        "calibration_receipt_sha256": calibration_receipt_sha256,
        "deterministic_canonical_result_sha256": candidate[
            "deterministic_canonical_result_sha256"
        ],
        "source_locks": source_locks,
        "calibration_fixture_files": fixture_files,
    }
    release_identity_sha256 = hashlib.sha256(canonical_json_bytes(identity_core)).hexdigest()
    release_lock: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "release_identity_sha256": release_identity_sha256,
        "status": "TRACKER_RELEASE_FROZEN_CALIBRATION_ONLY",
        "implementation_base_commit": contract.implementation_base_commit,
        "tracker_config": {
            "path": _repo_relative(config_path),
            "sha256": config_sha256,
        },
        "tracker_module": {
            "path": _repo_relative(fixture_lock.implementation_path),
            "sha256": fixture_lock.implementation_sha256,
        },
        "calibration_audit": {
            "path": _repo_relative(fixture_lock.implementation_path),
            "sha256": fixture_lock.implementation_sha256,
            "entrypoint": "audit_calibration_fixture",
        },
        "tests": [
            {
                "path": _repo_relative(TRACKER_TEST_PATH),
                "sha256": test_sha256,
            }
        ],
        "source_locks": source_locks,
        "calibration_fixture_files": fixture_files,
        "calibration_receipt": {
            "path": _repo_relative(calibration_receipt_path),
            "sha256": calibration_receipt_sha256,
        },
        "determinism_candidates": {
            "seed_0_path": _repo_relative(candidate_paths[0]),
            "seed_1_path": _repo_relative(candidate_paths[1]),
            "sha256": candidate_sha256,
            "byte_identical": True,
        },
        "coordinate_contract": {
            "homography_direction": HOMOGRAPHY_DIRECTION,
            "encoder_positive_axis": "product_ground_positive_x",
            "odometric_anchor_formula": [
                "x=camera_local_ground_x_mm+relative_encoder_travel_mm",
                "y=camera_local_ground_y_mm",
            ],
        },
        "association_contract": {
            "maximum_frame_index_delta": contract.maximum_frame_index_delta,
            "bridges_intervening_no_detection_frames": 1,
            "hard_gate_ceiling_um": contract.hard_gate_ceiling_um,
            "fixed_budget_um": contract.fixed_budget_um,
            "objective": [
                "maximum_cardinality",
                "minimum_total_integer_squared_residual_um2",
                "lexicographically_smallest_assignment_vector",
            ],
            "class_confidence_arm_pair_gt_blind": True,
            "raw_pixel_fallback_allowed": False,
        },
        "label_output_contract": {
            "track_class": "immutable_birth_observation_class",
            "conflict_emitted_confidence": 0.0,
            "promotion_from_later_observation_allowed": False,
        },
        "output_schema": {
            "identity": "spot_spray_target_rig_action_eval_v1_candidate_schema",
            "frame_fields": ["record_type", "frame_id", "candidates"],
            "candidate_fields": [
                "predicted_track_id",
                "class_name",
                "confidence",
                "polygon",
            ],
            "weed_only_candidate_fields": ["action_point"],
            "diagnostic_sidecar_separate": True,
        },
        "callable_api": {
            "load": "load_tracker_contract(config_path)",
            "construct": "EgoMotionTracker(contract)",
            "start": "start_sequence(homography_binding, encoder_binding, first_frame_index=0)",
            "frame": "process_frame(frame_id, telemetry, detections)",
            "finish": "finish_sequence()",
            "reset": "reset_sequence() after FINALIZED or INVALID_SEQUENCE",
        },
        "deterministic_canonical_result_sha256": candidate[
            "deterministic_canonical_result_sha256"
        ],
        "integration_boundary": {
            "ready_for_parent_integration": True,
            "new_parent_release_identity_required": True,
            "parent_runtime_homography_and_encoder_binding_required": True,
            "fresh_locked_test_inference_authorized_by_this_lane": False,
            "exactly_one_fresh_locked_test_evaluation_remains_parent_owned": True,
        },
        "evidence_scope": NEUTRAL_FIXTURE_SCOPE,
        "installed_rig_homography_validated": False,
        "model_outputs_present": False,
        "model_loaded": False,
        "target_gt_accessed": False,
        "locked_test_accessed": False,
        "field_go": False,
        "product_go": False,
        "dry_marker_go": False,
        "chemical_fire_allowed": False,
    }
    release_lock_bytes = canonical_json_bytes(release_lock)
    _write_immutable_bytes(release_lock_path, release_lock_bytes, result_only=True)
    release_lock_sha256 = hashlib.sha256(release_lock_bytes).hexdigest()
    validation_receipt = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "status": "TRACKER_RELEASE_LOCK_VALIDATED",
        "release_identity_sha256": release_identity_sha256,
        "calibration_receipt": {
            "path": _repo_relative(calibration_receipt_path),
            "sha256": calibration_receipt_sha256,
        },
        "release_lock": {
            "path": _repo_relative(release_lock_path),
            "sha256": release_lock_sha256,
        },
        "determinism_candidate_sha256": candidate_sha256,
        "candidate_bytes_equal": True,
        "model_loaded": False,
        "target_gt_accessed": False,
        "locked_test_accessed": False,
        "active_full_render_written": False,
        "field_go": False,
        "product_go": False,
        "chemical_fire_allowed": False,
    }
    validation_bytes = canonical_json_bytes(validation_receipt)
    _write_immutable_bytes(validation_receipt_path, validation_bytes)
    return {
        "contract_id": CONTRACT_ID,
        "status": "TRACKER_RELEASE_LOCK_VALIDATED",
        "release_identity_sha256": release_identity_sha256,
        "calibration_receipt_sha256": calibration_receipt_sha256,
        "release_lock_sha256": release_lock_sha256,
        "validation_receipt_sha256": hashlib.sha256(validation_bytes).hexdigest(),
        "candidate_bytes_equal": True,
        "model_loaded": False,
        "target_gt_accessed": False,
        "locked_test_accessed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--print-contract",
        action="store_true",
        help="validate frozen source locks and print a non-operational contract summary",
    )
    mode.add_argument(
        "--generate-neutral-calibration-fixture",
        type=Path,
        metavar="DIRECTORY",
        help="write the deterministic target-free 0.5/1.0 m/s mechanics fixture",
    )
    mode.add_argument(
        "--audit-neutral-calibration",
        action="store_true",
        help="audit the exact hash-locked neutral calibration fixture",
    )
    mode.add_argument(
        "--seal-calibration-release",
        action="store_true",
        help="compare two audit candidates and seal the calibration-only release",
    )
    parser.add_argument("--expected-config-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-seed-0", type=Path)
    parser.add_argument("--candidate-seed-1", type=Path)
    parser.add_argument("--release-lock", type=Path)
    parser.add_argument("--validation-receipt", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config_path = args.config.resolve()
        config_sha256: str | None = None
        if args.audit_neutral_calibration or args.seal_calibration_release:
            if args.expected_config_sha256 is None:
                _fail(
                    "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
                    "--expected-config-sha256 is required before calibration parsing",
                )
            config_sha256 = _exact_sha256(
                args.expected_config_sha256, "expected tracker config SHA-256"
            )
            _require_expected_sha256(
                config_path,
                config_sha256,
                "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
                "tracker config",
            )
        contract = load_tracker_contract(config_path)
        if args.generate_neutral_calibration_fixture is not None:
            summary = write_neutral_calibration_fixture(
                contract, args.generate_neutral_calibration_fixture
            )
            print(canonical_json_bytes(summary).decode("utf-8"), end="")
            return 0
        if args.audit_neutral_calibration:
            if args.output is None:
                _fail("TRACKER_INVALID_SCOPE_VIOLATION", "--output is required for audit")
            output = _require_lane_write_path(args.output)
            if not _path_within(output, LANE_RUN_ROOT):
                _fail(
                    "TRACKER_INVALID_SCOPE_VIOLATION",
                    "audit candidate output must be under the lane run root",
                )
            assert config_sha256 is not None
            fixture_lock = load_calibration_fixture_lock(config_path)
            candidate = audit_calibration_fixture(
                contract,
                fixture_lock,
                config_path=config_path,
                config_sha256=config_sha256,
            )
            candidate_bytes = canonical_json_bytes(candidate)
            _write_immutable_bytes(output, candidate_bytes)
            print(
                canonical_json_bytes(
                    {
                        "contract_id": CONTRACT_ID,
                        "status": candidate["status"],
                        "output": _repo_relative(output),
                        "output_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                        "raw_pixel_p95_1m_s": candidate["raw_pixel_p95_1m_s"],
                        "positive_sign_gate_violation_count": candidate[
                            "positive_sign_gate_violation_count"
                        ],
                        "wrong_sign_gate_violation_count": candidate[
                            "wrong_sign_gate_violation_count"
                        ],
                        "model_loaded": False,
                        "target_gt_accessed": False,
                        "locked_test_accessed": False,
                    }
                ).decode("utf-8"),
                end="",
            )
            return 0
        if args.seal_calibration_release:
            required_paths = {
                "--output": args.output,
                "--candidate-seed-0": args.candidate_seed_0,
                "--candidate-seed-1": args.candidate_seed_1,
                "--release-lock": args.release_lock,
                "--validation-receipt": args.validation_receipt,
            }
            missing = [name for name, value in required_paths.items() if value is None]
            if missing:
                _fail(
                    "TRACKER_INVALID_SCOPE_VIOLATION",
                    f"release seal is missing required paths: {missing}",
                )
            assert config_sha256 is not None
            fixture_lock = load_calibration_fixture_lock(config_path)
            summary = seal_calibration_release(
                contract,
                fixture_lock,
                config_path=config_path,
                config_sha256=config_sha256,
                candidate_seed_0_path=args.candidate_seed_0,
                candidate_seed_1_path=args.candidate_seed_1,
                calibration_receipt_path=args.output,
                release_lock_path=args.release_lock,
                validation_receipt_path=args.validation_receipt,
            )
            print(canonical_json_bytes(summary).decode("utf-8"), end="")
            return 0
        if args.print_contract:
            print(
                canonical_json_bytes(
                    {
                        "contract_id": CONTRACT_ID,
                        "status": "TRACKER_CONTRACT_VALIDATED_NO_SEQUENCE_RUN",
                        "coordinate_direction": HOMOGRAPHY_DIRECTION,
                        "hard_gate_ceiling_um": contract.hard_gate_ceiling_um,
                        "maximum_frame_index_delta": contract.maximum_frame_index_delta,
                        "source_lock_count": len(contract.source_locks),
                        "model_loaded": False,
                        "locked_test_accessed": False,
                    }
                ).decode("utf-8"),
                end="",
            )
        return 0
    except TrackerContractError as exc:
        if exc.code == "TRACKER_INVALID_SCOPE_VIOLATION":
            exit_code = 4
        elif exc.code in {
            "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT",
            "INVALID_CONFIG_OR_SOURCE_LOCK",
        }:
            exit_code = 5
        elif exc.code == "TRACKER_NOT_READY_CALIBRATION_EVIDENCE":
            exit_code = 2
        else:
            exit_code = 3
        print(
            canonical_json_bytes(
                {
                    "contract_id": CONTRACT_ID,
                    "status": "TRACKER_CALIBRATION_FAIL_CLOSED",
                    "failure_code": exc.code,
                    "reason": str(exc),
                    "model_loaded": False,
                    "target_gt_accessed": False,
                    "locked_test_accessed": False,
                    "field_go": False,
                    "product_go": False,
                    "chemical_fire_allowed": False,
                }
            ).decode("utf-8"),
            end="",
            file=sys.stderr,
        )
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
