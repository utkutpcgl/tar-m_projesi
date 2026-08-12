#!/usr/bin/env python3
"""Evaluate target-rig predictions as frozen track-level spot-spray actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"

EXIT_EVALUATED_OFFLINE_MODEL_GO = 0
EXIT_NOT_READY = 2
EXIT_EVALUATED_NO_GO = 3
EXIT_FIXTURE_ONLY = 4
EXIT_CONTRACT_ERROR = 5


class ContractError(ValueError):
    """A fail-closed input or protocol violation."""


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


@dataclass(frozen=True)
class Instance:
    instance_id: str
    track_id: str
    class_name: str
    polygon: tuple[tuple[float, float], ...]
    visible_fraction: float
    canopy_span_mm: float | None
    partial: bool
    occluded: bool


@dataclass(frozen=True)
class WhiteBalance:
    mode: str
    red_gain: float
    green_gain: float
    blue_gain: float


@dataclass(frozen=True)
class StrobeSettings:
    profile_id: str
    pulse_width_us: float
    peak_current_a: float


@dataclass(frozen=True)
class RigAcceptanceReference:
    result_path: str
    result_sha256: str


@dataclass(frozen=True)
class Frame:
    frame_id: str
    image_path: str
    image_sha256: str | None
    field_id: str
    session_id: str
    video_id: str
    frame_index: int
    timestamp_ns: int
    camera_frame_counter: int | None
    camera_timestamp_ns: int | None
    encoder_mm: float
    exposure_us: float
    gain_db: float
    white_balance: WhiteBalance | None
    working_distance_mm: float
    native_width_px: int | None
    native_height_px: int | None
    pixel_format: str | None
    camera_id: str | None
    rig_id: str | None
    capture_profile_id: str | None
    strobe_profile_id: str
    strobe_settings: StrobeSettings | None
    split: str
    instances: tuple[Instance, ...]

    @property
    def video_key(self) -> tuple[str, str, str]:
        return self.field_id, self.session_id, self.video_id


@dataclass(frozen=True)
class Candidate:
    predicted_track_id: str
    class_name: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    action_point: tuple[float, float] | None


@dataclass(frozen=True)
class PredictionFrame:
    frame_id: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class FireEvent:
    field_id: str
    session_id: str
    video_id: str
    frame_id: str
    frame_index: int
    predicted_track_id: str
    confidence: float
    action_point: tuple[float, float]
    confirmations_in_window: int


@dataclass(frozen=True)
class CaptureManifest:
    manifest_id: str
    evidence_scope: str
    rig_acceptance: RigAcceptanceReference | None
    frames: tuple[Frame, ...]


@dataclass(frozen=True)
class CaptureAudit:
    path: str
    sha256: str
    data_root: str
    status: str
    evidence_scope: str
    synthetic_fixture: bool
    real_proof_checks: Mapping[str, bool]

    @property
    def real_proof_accepted(self) -> bool:
        return bool(self.real_proof_checks) and all(self.real_proof_checks.values())


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _identifier(value: Any, label: str) -> str:
    result = _nonempty_string(value, label)
    if not IDENTIFIER.fullmatch(result):
        raise ContractError(f"{label} is not a canonical identifier")
    return result


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{label} must be an integer >= {minimum}")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ContractError(f"{label} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ContractError(f"{label} must be <= {maximum}")
    return result


def _positive_number(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ContractError(f"{label} must be > 0")
    return result


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{label} must be boolean")
    return value


def _sha256_hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError(f"{label} must be lowercase SHA-256")
    return value


def polygon_area(polygon: Sequence[tuple[float, float]]) -> float:
    return abs(
        sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1])
        )
    ) / 2.0


def _polygon(
    value: Any, label: str, *, minimum_area: float = 1e-12
) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 3:
        raise ContractError(f"{label} must contain at least three points")
    points: list[tuple[float, float]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, list) or len(raw) != 2:
            raise ContractError(f"{label}[{index}] must be [x, y]")
        points.append(
            (
                _number(raw[0], f"{label}[{index}].x", minimum=0.0, maximum=1.0),
                _number(raw[1], f"{label}[{index}].y", minimum=0.0, maximum=1.0),
            )
        )
    result = tuple(points)
    if polygon_area(result) < minimum_area:
        raise ContractError(f"{label} area is below {minimum_area}")
    return result


def _point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ContractError(f"{label} must be [x, y]")
    return (
        _number(value[0], f"{label}.x", minimum=0.0, maximum=1.0),
        _number(value[1], f"{label}.y", minimum=0.0, maximum=1.0),
    )


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance: float = 1e-12,
) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= px <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= py <= max(y1, y2) + tolerance
    )


def point_in_polygon(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> bool:
    """Return True on polygon interiors or boundaries."""
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        if _point_on_segment(point, start, end):
            return True
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
        previous = current
    return inside


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ContractError(f"JSONL input does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError(f"Invalid JSON at {path}:{line_number}: {error}") from error
        if not isinstance(row, dict):
            raise ContractError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ContractError(f"JSONL input is empty: {path}")
    return rows


def _require_fields(row: Mapping[str, Any], fields: Iterable[str], label: str) -> None:
    missing = sorted(set(fields) - set(row))
    if missing:
        raise ContractError(f"{label} is missing fields: {missing}")


def _reject_unknown_fields(
    row: Mapping[str, Any], fields: Iterable[str], label: str
) -> None:
    unknown = sorted(set(row) - set(fields))
    if unknown:
        raise ContractError(f"{label} has unknown fields: {unknown}")


def load_manifest(path: Path, config: Mapping[str, Any]) -> CaptureManifest:
    if not path.is_file():
        raise ContractError(f"Capture manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"Invalid capture manifest JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ContractError("Capture manifest must be one JSON object")
    manifest_cfg = config["capture_manifest"]
    top_fields = manifest_cfg["top_level_fields"]
    _require_fields(
        payload, manifest_cfg["required_top_level_fields"], "capture manifest"
    )
    _reject_unknown_fields(payload, top_fields, "capture manifest")
    if payload["schema_version"] != manifest_cfg["contract"]:
        raise ContractError("Capture manifest schema_version mismatch")
    manifest_id = _identifier(payload["manifest_id"], "capture manifest.manifest_id")
    evidence_scope = _nonempty_string(
        payload["evidence_scope"], "capture manifest.evidence_scope"
    )
    if evidence_scope not in set(manifest_cfg["evidence_scopes"]):
        raise ContractError(f"Unknown capture evidence_scope: {evidence_scope}")
    if evidence_scope == "real_target_rig":
        _require_fields(
            payload,
            manifest_cfg["real_required_top_level_fields"],
            "real capture manifest",
        )
    rig_acceptance: RigAcceptanceReference | None = None
    if "rig_acceptance" in payload:
        raw_acceptance = payload["rig_acceptance"]
        if not isinstance(raw_acceptance, dict):
            raise ContractError("capture manifest.rig_acceptance must be an object")
        acceptance_fields = manifest_cfg["rig_acceptance_fields"]
        _require_fields(raw_acceptance, acceptance_fields, "capture manifest.rig_acceptance")
        _reject_unknown_fields(
            raw_acceptance, acceptance_fields, "capture manifest.rig_acceptance"
        )
        rig_acceptance = RigAcceptanceReference(
            result_path=_nonempty_string(
                raw_acceptance["result_path"],
                "capture manifest.rig_acceptance.result_path",
            ),
            result_sha256=_sha256_hex(
                raw_acceptance["result_sha256"],
                "capture manifest.rig_acceptance.result_sha256",
            ),
        )
    rows = payload["frames"]
    if not isinstance(rows, list) or not rows:
        raise ContractError("Capture manifest.frames must be a non-empty list")
    allowed_splits = set(manifest_cfg["splits"])
    allowed_classes = set(manifest_cfg["classes"])
    required_frame = manifest_cfg["required_frame_fields"]
    real_required_frame = manifest_cfg["real_required_frame_fields"]
    allowed_frame = [*required_frame, *real_required_frame]
    required_instance = manifest_cfg["required_instance_fields"]
    frames: list[Frame] = []
    seen_frame_ids: set[str] = set()
    seen_frame_keys: set[tuple[str, str, str, int]] = set()
    known_track_classes: dict[tuple[str, str, str, str], str] = {}
    for row_index, row in enumerate(rows):
        label = f"manifest row {row_index}"
        if not isinstance(row, dict):
            raise ContractError(f"{label} must be an object")
        _require_fields(row, required_frame, label)
        if evidence_scope == "real_target_rig":
            _require_fields(row, real_required_frame, f"real {label}")
        _reject_unknown_fields(row, allowed_frame, label)
        frame_id = _identifier(row["frame_id"], f"{label}.frame_id")
        if frame_id in seen_frame_ids:
            raise ContractError(f"Duplicate frame_id: {frame_id}")
        seen_frame_ids.add(frame_id)
        field_id = _identifier(row["field_id"], f"{label}.field_id")
        session_id = _identifier(row["session_id"], f"{label}.session_id")
        video_id = _identifier(row["video_id"], f"{label}.video_id")
        frame_index = _integer(row["frame_index"], f"{label}.frame_index")
        frame_key = field_id, session_id, video_id, frame_index
        if frame_key in seen_frame_keys:
            raise ContractError(f"Duplicate field/session/video/frame_index: {frame_key}")
        seen_frame_keys.add(frame_key)
        split = _nonempty_string(row["split"], f"{label}.split")
        if split not in allowed_splits:
            raise ContractError(f"Unknown split {split!r} in {label}")
        image_hash = (
            _sha256_hex(row["image_sha256"], f"{label}.image_sha256")
            if "image_sha256" in row
            else None
        )
        camera_frame_counter = (
            _integer(row["camera_frame_counter"], f"{label}.camera_frame_counter")
            if "camera_frame_counter" in row
            else None
        )
        camera_timestamp_ns = (
            _integer(row["camera_timestamp_ns"], f"{label}.camera_timestamp_ns")
            if "camera_timestamp_ns" in row
            else None
        )
        white_balance: WhiteBalance | None = None
        if "white_balance" in row:
            raw_white_balance = row["white_balance"]
            if not isinstance(raw_white_balance, dict):
                raise ContractError(f"{label}.white_balance must be an object")
            white_balance_fields = manifest_cfg["white_balance_fields"]
            _require_fields(
                raw_white_balance, white_balance_fields, f"{label}.white_balance"
            )
            _reject_unknown_fields(
                raw_white_balance, white_balance_fields, f"{label}.white_balance"
            )
            mode = _nonempty_string(
                raw_white_balance["mode"], f"{label}.white_balance.mode"
            )
            if mode != "manual":
                raise ContractError(f"{label}.white_balance.mode must be manual")
            white_balance = WhiteBalance(
                mode=mode,
                red_gain=_positive_number(
                    raw_white_balance["red_gain"],
                    f"{label}.white_balance.red_gain",
                ),
                green_gain=_positive_number(
                    raw_white_balance["green_gain"],
                    f"{label}.white_balance.green_gain",
                ),
                blue_gain=_positive_number(
                    raw_white_balance["blue_gain"],
                    f"{label}.white_balance.blue_gain",
                ),
            )
        native_width_px = (
            _integer(row["native_width_px"], f"{label}.native_width_px", minimum=1)
            if "native_width_px" in row
            else None
        )
        native_height_px = (
            _integer(row["native_height_px"], f"{label}.native_height_px", minimum=1)
            if "native_height_px" in row
            else None
        )
        pixel_format = (
            _identifier(row["pixel_format"], f"{label}.pixel_format")
            if "pixel_format" in row
            else None
        )
        camera_id = (
            _identifier(row["camera_id"], f"{label}.camera_id")
            if "camera_id" in row
            else None
        )
        rig_id = (
            _identifier(row["rig_id"], f"{label}.rig_id")
            if "rig_id" in row
            else None
        )
        capture_profile_id = (
            _identifier(row["capture_profile_id"], f"{label}.capture_profile_id")
            if "capture_profile_id" in row
            else None
        )
        strobe_settings: StrobeSettings | None = None
        if "strobe_settings" in row:
            raw_strobe = row["strobe_settings"]
            if not isinstance(raw_strobe, dict):
                raise ContractError(f"{label}.strobe_settings must be an object")
            strobe_fields = manifest_cfg["strobe_settings_fields"]
            _require_fields(raw_strobe, strobe_fields, f"{label}.strobe_settings")
            _reject_unknown_fields(
                raw_strobe, strobe_fields, f"{label}.strobe_settings"
            )
            profile_id = _identifier(
                raw_strobe["profile_id"], f"{label}.strobe_settings.profile_id"
            )
            if profile_id != row["strobe_profile_id"]:
                raise ContractError(
                    f"{label}.strobe_settings.profile_id must match strobe_profile_id"
                )
            strobe_settings = StrobeSettings(
                profile_id=profile_id,
                pulse_width_us=_positive_number(
                    raw_strobe["pulse_width_us"],
                    f"{label}.strobe_settings.pulse_width_us",
                ),
                peak_current_a=_number(
                    raw_strobe["peak_current_a"],
                    f"{label}.strobe_settings.peak_current_a",
                    minimum=0.0,
                ),
            )
        raw_instances = row["instances"]
        if not isinstance(raw_instances, list):
            raise ContractError(f"{label}.instances must be a list")
        instances: list[Instance] = []
        frame_instance_ids: set[str] = set()
        frame_track_ids: set[str] = set()
        for instance_index, raw in enumerate(raw_instances):
            item_label = f"{label}.instances[{instance_index}]"
            if not isinstance(raw, dict):
                raise ContractError(f"{item_label} must be an object")
            _require_fields(raw, required_instance, item_label)
            _reject_unknown_fields(raw, required_instance, item_label)
            instance_id = _identifier(raw["instance_id"], f"{item_label}.instance_id")
            track_id = _identifier(raw["track_id"], f"{item_label}.track_id")
            if instance_id in frame_instance_ids:
                raise ContractError(f"Duplicate instance_id {instance_id!r} in frame {frame_id}")
            if track_id in frame_track_ids:
                raise ContractError(f"Duplicate track_id {track_id!r} in frame {frame_id}")
            frame_instance_ids.add(instance_id)
            frame_track_ids.add(track_id)
            class_name = _nonempty_string(raw["class_name"], f"{item_label}.class_name")
            if class_name not in allowed_classes:
                raise ContractError(f"Unknown class {class_name!r} in {item_label}")
            track_key = field_id, session_id, video_id, track_id
            if class_name != "partial_unknown":
                previous_class = known_track_classes.setdefault(track_key, class_name)
                if previous_class != class_name:
                    raise ContractError(f"GT track conflicts between known classes: {track_key}")
            visible_fraction = _number(
                raw["visible_fraction"],
                f"{item_label}.visible_fraction",
                minimum=0.0,
                maximum=1.0,
            )
            if visible_fraction <= 0.0:
                raise ContractError(f"{item_label}.visible_fraction must be > 0")
            partial = _boolean(raw["partial"], f"{item_label}.partial")
            if class_name == "partial_unknown":
                if raw["canopy_span_mm"] is not None:
                    raise ContractError(
                        f"{item_label}.canopy_span_mm must be null for partial_unknown"
                    )
                if not partial:
                    raise ContractError(f"{item_label} partial_unknown must be partial")
                canopy_span_mm = None
            else:
                canopy_span_mm = _number(
                    raw["canopy_span_mm"],
                    f"{item_label}.canopy_span_mm",
                    minimum=0.0,
                )
                if canopy_span_mm <= 0.0:
                    raise ContractError(f"{item_label}.canopy_span_mm must be > 0")
            instances.append(
                Instance(
                    instance_id=instance_id,
                    track_id=track_id,
                    class_name=class_name,
                    polygon=_polygon(
                        raw["polygon"],
                        f"{item_label}.polygon",
                        minimum_area=float(manifest_cfg["minimum_normalized_polygon_area"]),
                    ),
                    visible_fraction=visible_fraction,
                    canopy_span_mm=canopy_span_mm,
                    partial=partial,
                    occluded=_boolean(raw["occluded"], f"{item_label}.occluded"),
                )
            )
        frames.append(
            Frame(
                frame_id=frame_id,
                image_path=_nonempty_string(row["image_path"], f"{label}.image_path"),
                image_sha256=image_hash,
                field_id=field_id,
                session_id=session_id,
                video_id=video_id,
                frame_index=frame_index,
                timestamp_ns=_integer(row["timestamp_ns"], f"{label}.timestamp_ns"),
                camera_frame_counter=camera_frame_counter,
                camera_timestamp_ns=camera_timestamp_ns,
                encoder_mm=_number(row["encoder_mm"], f"{label}.encoder_mm"),
                exposure_us=_positive_number(row["exposure_us"], f"{label}.exposure_us"),
                gain_db=_number(row["gain_db"], f"{label}.gain_db"),
                white_balance=white_balance,
                working_distance_mm=_positive_number(
                    row["working_distance_mm"], f"{label}.working_distance_mm"
                ),
                native_width_px=native_width_px,
                native_height_px=native_height_px,
                pixel_format=pixel_format,
                camera_id=camera_id,
                rig_id=rig_id,
                capture_profile_id=capture_profile_id,
                strobe_profile_id=_identifier(
                    row["strobe_profile_id"], f"{label}.strobe_profile_id"
                ),
                strobe_settings=strobe_settings,
                split=split,
                instances=tuple(instances),
            )
        )
    groups: dict[tuple[str, str, str], list[Frame]] = defaultdict(list)
    for frame in frames:
        groups[frame.video_key].append(frame)
    for video_key, group in groups.items():
        splits = {frame.split for frame in group}
        if len(splits) != 1:
            raise ContractError(f"Adjacent video frames cross splits: {video_key} -> {splits}")
        ordered = sorted(group, key=lambda item: item.frame_index)
        for previous, current in zip(ordered, ordered[1:]):
            if current.timestamp_ns <= previous.timestamp_ns:
                raise ContractError(f"Non-increasing timestamp in video {video_key}")
    for level, key_fn in (
        ("field", lambda frame: (frame.field_id,)),
        ("session", lambda frame: (frame.field_id, frame.session_id)),
    ):
        split_by_key: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for frame in frames:
            split_by_key[key_fn(frame)].add(frame.split)
        leaking = {key: splits for key, splits in split_by_key.items() if len(splits) > 1}
        if leaking:
            raise ContractError(f"{level} crosses splits: {leaking}")
    ordered_frames = sorted(
        frames,
        key=lambda item: (item.field_id, item.session_id, item.video_id, item.frame_index),
    )
    return CaptureManifest(
        manifest_id=manifest_id,
        evidence_scope=evidence_scope,
        rig_acceptance=rig_acceptance,
        frames=tuple(ordered_frames),
    )


def _report_path(value: Any, label: str) -> Path:
    raw = _nonempty_string(value, label)
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _source_binding_matches(
    report: Mapping[str, Any],
    *,
    path_key: str,
    hash_key: str,
    trusted_path: Path,
) -> bool:
    if not trusted_path.is_file():
        return False
    try:
        reported_path = _report_path(report.get(path_key), f"capture audit.{path_key}")
    except ContractError:
        return False
    return (
        reported_path == trusted_path
        and report.get(hash_key) == sha256(trusted_path)
    )


def load_capture_audit(
    path: Path,
    manifest_path: Path,
    config: Mapping[str, Any],
) -> CaptureAudit:
    """Load the capture lane's audit artifact and verify its manifest binding.

    The artifact hash is subsequently required in prediction metadata.  READY is
    accepted as real proof only when every frozen capture-audit provenance field
    matches the exact local schema, policy, implementation, and manifest.
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ContractError(f"Capture audit result does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"Invalid capture audit result JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ContractError("Capture audit result must be one JSON object")
    _require_fields(
        payload,
        [
            "audit_contract",
            "manifest_contract",
            "status",
            "valid",
            "ready",
            "evidence",
            "errors",
            "readiness_reasons",
            "inputs",
            "audit_scope",
        ],
        "capture audit result",
    )
    audit_cfg = config["capture_audit"]
    if payload["audit_contract"] != audit_cfg["contract"]:
        raise ContractError("Capture audit contract mismatch")
    if payload["manifest_contract"] != audit_cfg["manifest_contract"]:
        raise ContractError("Capture audit manifest contract mismatch")
    status = _nonempty_string(payload["status"], "capture audit.status")
    if status not in {"READY", "NOT_READY", "INVALID"}:
        raise ContractError(f"Unknown capture audit status: {status}")
    valid = _boolean(payload["valid"], "capture audit.valid")
    ready = _boolean(payload["ready"], "capture audit.ready")
    if not isinstance(payload["errors"], list):
        raise ContractError("capture audit.errors must be a list")
    if not isinstance(payload["readiness_reasons"], list):
        raise ContractError("capture audit.readiness_reasons must be a list")

    evidence = payload["evidence"]
    if not isinstance(evidence, dict):
        raise ContractError("capture audit.evidence must be an object")
    _require_fields(
        evidence,
        [
            "scope",
            "synthetic_fixture",
            "counts_as_real_target_rig_evidence",
            "fixture_can_unlock_ready",
        ],
        "capture audit.evidence",
    )
    evidence_scope = _nonempty_string(
        evidence["scope"], "capture audit.evidence.scope"
    )
    synthetic_fixture = _boolean(
        evidence["synthetic_fixture"],
        "capture audit.evidence.synthetic_fixture",
    )
    counts_as_real = _boolean(
        evidence["counts_as_real_target_rig_evidence"],
        "capture audit.evidence.counts_as_real_target_rig_evidence",
    )
    fixture_can_unlock = _boolean(
        evidence["fixture_can_unlock_ready"],
        "capture audit.evidence.fixture_can_unlock_ready",
    )
    if synthetic_fixture != (evidence_scope == "synthetic_fixture"):
        raise ContractError("Capture audit synthetic evidence flags conflict")

    inputs = payload["inputs"]
    if not isinstance(inputs, dict):
        raise ContractError("capture audit.inputs must be an object")
    _require_fields(
        inputs,
        ["manifest", "manifest_sha256", "data_root"],
        "capture audit.inputs",
    )
    exact_manifest = manifest_path.expanduser().resolve()
    if _report_path(inputs["manifest"], "capture audit.inputs.manifest") != exact_manifest:
        raise ContractError("Capture audit manifest path does not match the evaluated manifest")
    if inputs["manifest_sha256"] != sha256(exact_manifest):
        raise ContractError("Capture audit manifest hash does not match the evaluated manifest")

    audit_scope = payload["audit_scope"]
    if not isinstance(audit_scope, dict):
        raise ContractError("capture audit.audit_scope must be an object")
    inferred_from_fixtures = _boolean(
        audit_scope.get("real_field_evidence_inferred_from_fixtures"),
        "capture audit.audit_scope.real_field_evidence_inferred_from_fixtures",
    )
    image_metadata_checked = _boolean(
        audit_scope.get("image_file_metadata_checked"),
        "capture audit.audit_scope.image_file_metadata_checked",
    )
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        integrity = {}
    rig_acceptance = integrity.get("rig_acceptance")
    if not isinstance(rig_acceptance, dict):
        rig_acceptance = {}

    trusted = audit_cfg["trusted_sources"]
    schema_path = (PROJECT_ROOT / str(trusted["schema"])).resolve()
    policy_path = (PROJECT_ROOT / str(trusted["policy"])).resolve()
    implementation_path = (PROJECT_ROOT / str(trusted["implementation"])).resolve()
    implementation = payload.get("implementation")
    if not isinstance(implementation, dict):
        implementation = {}
    checks = {
        "status_ready": status == audit_cfg["real_ready_status"],
        "valid": valid is True,
        "ready": ready is True,
        "errors_empty": payload["errors"] == [],
        "readiness_reasons_empty": payload["readiness_reasons"] == [],
        "real_target_rig_scope": evidence_scope == audit_cfg["real_evidence_scope"],
        "not_synthetic_fixture": synthetic_fixture is False,
        "counts_as_real_target_rig_evidence": counts_as_real is True,
        "fixture_cannot_unlock_ready": fixture_can_unlock is False,
        "real_evidence_not_inferred_from_fixtures": inferred_from_fixtures is False,
        "image_file_metadata_checked": image_metadata_checked is True,
        "real_capture_metadata_complete": (
            integrity.get("real_capture_metadata_complete") is True
        ),
        "all_real_image_sha256_verified": (
            integrity.get("all_real_image_sha256_verified") is True
        ),
        "all_real_image_content_verified": (
            integrity.get("all_real_image_content_verified") is True
        ),
        "rig_acceptance_passed": (
            rig_acceptance.get("status") == "PASS"
            and rig_acceptance.get("physical_collection_allowed") is True
        ),
        "schema_source_current": _source_binding_matches(
            inputs,
            path_key="schema",
            hash_key="schema_sha256",
            trusted_path=schema_path,
        ),
        "policy_source_current": _source_binding_matches(
            inputs,
            path_key="policy",
            hash_key="policy_sha256",
            trusted_path=policy_path,
        ),
        "implementation_source_current": _source_binding_matches(
            implementation,
            path_key="script",
            hash_key="script_sha256",
            trusted_path=implementation_path,
        ),
    }
    return CaptureAudit(
        path=str(path),
        sha256=sha256(path),
        data_root=str(_report_path(inputs["data_root"], "capture audit.inputs.data_root")),
        status=status,
        evidence_scope=evidence_scope,
        synthetic_fixture=synthetic_fixture,
        real_proof_checks=checks,
    )


def _parse_candidate(
    raw: Mapping[str, Any], label: str, config: Mapping[str, Any]
) -> Candidate:
    prediction_cfg = config["prediction_jsonl"]
    _require_fields(raw, prediction_cfg["required_candidate_fields"], label)
    track_id = _identifier(raw["predicted_track_id"], f"{label}.predicted_track_id")
    class_name = _nonempty_string(raw["class_name"], f"{label}.class_name")
    if class_name not in set(prediction_cfg["classes"]):
        raise ContractError(f"Unknown prediction class {class_name!r} in {label}")
    polygon = _polygon(
        raw["polygon"],
        f"{label}.polygon",
        minimum_area=float(config["capture_manifest"]["minimum_normalized_polygon_area"]),
    )
    action_point: tuple[float, float] | None = None
    if class_name == "weed":
        _require_fields(raw, prediction_cfg["weed_only_required_candidate_fields"], label)
        _reject_unknown_fields(
            raw,
            [
                *prediction_cfg["required_candidate_fields"],
                *prediction_cfg["weed_only_required_candidate_fields"],
            ],
            label,
        )
        action_point = _point(raw["action_point"], f"{label}.action_point")
        if not point_in_polygon(action_point, polygon):
            raise ContractError(f"{label}.action_point must lie inside its predicted mask")
    else:
        _reject_unknown_fields(raw, prediction_cfg["required_candidate_fields"], label)
    return Candidate(
        predicted_track_id=track_id,
        class_name=class_name,
        confidence=_number(raw["confidence"], f"{label}.confidence", minimum=0.0, maximum=1.0),
        polygon=polygon,
        action_point=action_point,
    )


def load_predictions(
    path: Path,
    manifest_path: Path,
    capture_audit: CaptureAudit,
    frames: Sequence[Frame],
    config: Mapping[str, Any],
) -> tuple[dict[str, PredictionFrame], dict[str, Any]]:
    rows = _load_jsonl(path)
    prediction_cfg = config["prediction_jsonl"]
    metadata = rows[0]
    _require_fields(metadata, prediction_cfg["required_metadata_fields"], "prediction metadata")
    _reject_unknown_fields(
        metadata, prediction_cfg["required_metadata_fields"], "prediction metadata"
    )
    if metadata["record_type"] != prediction_cfg["first_record"]:
        raise ContractError("Prediction JSONL must begin with prediction_metadata")
    if metadata["schema_version"] != prediction_cfg["schema_version"]:
        raise ContractError("Prediction schema_version mismatch")
    observed_checkpoint = metadata["model_checkpoint_sha256"]
    if not isinstance(observed_checkpoint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", observed_checkpoint
    ):
        raise ContractError("Prediction model_checkpoint_sha256 is not lowercase SHA-256")
    expected_checkpoint = config["model"]["evaluated_checkpoint"]["checkpoint_sha256"]
    if expected_checkpoint is not None and observed_checkpoint != expected_checkpoint:
        raise ContractError("Prediction checkpoint hash does not match the frozen model")
    manifest_hash = sha256(manifest_path)
    if metadata["capture_manifest_sha256"] != manifest_hash:
        raise ContractError("Prediction manifest hash does not match the evaluated manifest")
    if metadata["capture_audit_result_sha256"] != capture_audit.sha256:
        raise ContractError("Prediction capture-audit hash does not match the supplied audit result")
    expected_frame_ids = {
        frame.frame_id
        for frame in frames
        if frame.split
        in {
            config["capture_manifest"]["calibration_split"],
            config["capture_manifest"]["locked_test_split"],
        }
    }
    frame_by_id = {frame.frame_id: frame for frame in frames}
    output: dict[str, PredictionFrame] = {}
    track_classes: dict[tuple[str, str, str, str], str] = {}
    for row_index, row in enumerate(rows[1:], 1):
        label = f"prediction row {row_index}"
        _require_fields(row, prediction_cfg["required_frame_fields"], label)
        _reject_unknown_fields(row, prediction_cfg["required_frame_fields"], label)
        if row["record_type"] != prediction_cfg["frame_record"]:
            raise ContractError(f"Unexpected prediction record_type in {label}")
        frame_id = _identifier(row["frame_id"], f"{label}.frame_id")
        if frame_id not in expected_frame_ids:
            raise ContractError(f"Prediction row targets a non-evaluation frame: {frame_id}")
        if frame_id in output:
            raise ContractError(f"Duplicate prediction frame_id: {frame_id}")
        raw_candidates = row["candidates"]
        if not isinstance(raw_candidates, list):
            raise ContractError(f"{label}.candidates must be a list")
        candidates: list[Candidate] = []
        ids_this_frame: set[str] = set()
        frame = frame_by_id[frame_id]
        for candidate_index, raw_candidate in enumerate(raw_candidates):
            candidate_label = f"{label}.candidates[{candidate_index}]"
            if not isinstance(raw_candidate, dict):
                raise ContractError(f"{candidate_label} must be an object")
            candidate = _parse_candidate(raw_candidate, candidate_label, config)
            if candidate.predicted_track_id in ids_this_frame:
                raise ContractError(
                    f"Duplicate predicted_track_id in frame {frame_id}: {candidate.predicted_track_id}"
                )
            ids_this_frame.add(candidate.predicted_track_id)
            track_key = (*frame.video_key, candidate.predicted_track_id)
            previous_class = track_classes.setdefault(track_key, candidate.class_name)
            if previous_class != candidate.class_name:
                raise ContractError(f"Predicted track changes class: {track_key}")
            candidates.append(candidate)
        output[frame_id] = PredictionFrame(frame_id, tuple(candidates))
    missing = sorted(expected_frame_ids - set(output))
    if missing:
        raise ContractError(f"Predictions do not cover evaluation frames: {missing[:5]}")
    return output, {
        "schema_version": metadata["schema_version"],
        "model_checkpoint_sha256": observed_checkpoint,
        "capture_manifest_sha256": metadata["capture_manifest_sha256"],
        "capture_audit_result_sha256": metadata["capture_audit_result_sha256"],
        "prediction_jsonl_sha256": sha256(path),
    }


def threshold_grid(config: Mapping[str, Any]) -> list[float]:
    calibration = config["threshold_calibration"]
    start = float(calibration["start"])
    stop = float(calibration["stop"])
    step = float(calibration["step"])
    if not 0.0 <= start <= stop <= 1.0 or step <= 0.0:
        raise ContractError("Invalid threshold grid")
    count = int(math.floor((stop - start) / step + 1e-9))
    values = [round(start + index * step, 10) for index in range(count + 1)]
    if not values or values[-1] < stop - 1e-9:
        values.append(round(stop, 10))
    return values


def simulate_fire_events(
    frames: Sequence[Frame],
    predictions: Mapping[str, PredictionFrame],
    *,
    split: str,
    weed_threshold: float,
    minimum_confirmations: int,
    window_frames: int,
    crop_mask_threshold: float,
) -> tuple[list[FireEvent], dict[str, int]]:
    if minimum_confirmations < 1 or window_frames < minimum_confirmations:
        raise ContractError("Temporal confirmation requires 1 <= confirmations <= window")
    groups: dict[tuple[str, str, str], list[Frame]] = defaultdict(list)
    for frame in frames:
        if frame.split == split:
            groups[frame.video_key].append(frame)
    events: list[FireEvent] = []
    counters = {
        "weed_observations_above_threshold": 0,
        "weed_observations_crop_vetoed": 0,
        "qualifying_weed_observations": 0,
        "fire_events": 0,
    }
    for video_key, group in sorted(groups.items()):
        history: dict[str, list[tuple[int, Candidate]]] = defaultdict(list)
        fired: set[str] = set()
        for frame in sorted(group, key=lambda item: item.frame_index):
            prediction = predictions[frame.frame_id]
            crop_polygons = [
                candidate.polygon
                for candidate in prediction.candidates
                if candidate.class_name == "crop"
                and candidate.confidence >= crop_mask_threshold
            ]
            for candidate in prediction.candidates:
                if candidate.class_name != "weed" or candidate.confidence < weed_threshold:
                    continue
                counters["weed_observations_above_threshold"] += 1
                assert candidate.action_point is not None
                if any(
                    point_in_polygon(candidate.action_point, polygon)
                    for polygon in crop_polygons
                ):
                    counters["weed_observations_crop_vetoed"] += 1
                    continue
                counters["qualifying_weed_observations"] += 1
                observations = history[candidate.predicted_track_id]
                observations.append((frame.frame_index, candidate))
                window_start = frame.frame_index - window_frames + 1
                observations[:] = [item for item in observations if item[0] >= window_start]
                if (
                    candidate.predicted_track_id not in fired
                    and len(observations) >= minimum_confirmations
                ):
                    fired.add(candidate.predicted_track_id)
                    events.append(
                        FireEvent(
                            field_id=frame.field_id,
                            session_id=frame.session_id,
                            video_id=frame.video_id,
                            frame_id=frame.frame_id,
                            frame_index=frame.frame_index,
                            predicted_track_id=candidate.predicted_track_id,
                            confidence=candidate.confidence,
                            action_point=candidate.action_point,
                            confirmations_in_window=len(observations),
                        )
                    )
    counters["fire_events"] = len(events)
    return sorted(
        events,
        key=lambda item: (item.field_id, item.session_id, item.video_id, item.frame_index, item.predicted_track_id),
    ), counters


def gt_track_key(frame: Frame, instance: Instance) -> tuple[str, str, str, str]:
    return frame.field_id, frame.session_id, frame.video_id, instance.track_id


def eligible_track_sets(
    frames: Sequence[Frame], split: str, config: Mapping[str, Any]
) -> tuple[set[tuple[str, str, str, str]], set[tuple[str, str, str, str]]]:
    eligibility = config["eligible_weed_track"]
    all_weeds: set[tuple[str, str, str, str]] = set()
    eligible: set[tuple[str, str, str, str]] = set()
    for frame in frames:
        if frame.split != split:
            continue
        for instance in frame.instances:
            if instance.class_name != eligibility["class_name"]:
                continue
            key = gt_track_key(frame, instance)
            all_weeds.add(key)
            if (
                instance.canopy_span_mm is not None
                and instance.canopy_span_mm >= float(eligibility["minimum_canopy_span_mm"])
                and instance.visible_fraction >= float(eligibility["minimum_visible_fraction"])
                and (
                    not bool(eligibility["require_non_partial_observation"])
                    or not instance.partial
                )
            ):
                eligible.add(key)
    return eligible, all_weeds


def wilson_upper(successes: int, trials: int, z: float = 1.959963984540054) -> float | None:
    if trials == 0:
        return None
    if successes < 0 or successes > trials:
        raise ContractError("Invalid Wilson interval counts")
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = proportion + z2 / (2.0 * trials)
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z2 / (4.0 * trials * trials)
    )
    return (center + radius) / denominator


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_fire_events(
    frames: Sequence[Frame],
    events: Sequence[FireEvent],
    eligible_tracks: set[tuple[str, str, str, str]],
    all_weed_tracks: set[tuple[str, str, str, str]],
    *,
    field_id: str | None = None,
    include_event_audit: bool = False,
) -> dict[str, Any]:
    frame_by_id = {frame.frame_id: frame for frame in frames}
    selected_eligible = {
        key for key in eligible_tracks if field_id is None or key[0] == field_id
    }
    selected_all_weeds = {
        key for key in all_weed_tracks if field_id is None or key[0] == field_id
    }
    selected_events = [
        event for event in events if field_id is None or event.field_id == field_id
    ]
    matched: set[tuple[str, str, str, str]] = set()
    true_positive = false_positive = 0
    crop_collision = duplicate_shot = ignored_ineligible = partial_unknown_shot = 0
    audit: list[dict[str, Any]] = []
    for event in selected_events:
        frame = frame_by_id[event.frame_id]
        point = event.action_point
        crop_hit = any(
            instance.class_name == "crop" and point_in_polygon(point, instance.polygon)
            for instance in frame.instances
        )
        partial_hit = any(
            (
                instance.class_name == "partial_unknown"
                or (instance.class_name == "weed" and instance.partial)
            )
            and point_in_polygon(point, instance.polygon)
            for instance in frame.instances
        )
        eligible_hits = sorted(
            gt_track_key(frame, instance)
            for instance in frame.instances
            if instance.class_name == "weed"
            and not instance.partial
            and gt_track_key(frame, instance) in selected_eligible
            and point_in_polygon(point, instance.polygon)
        )
        ineligible_hit = any(
            instance.class_name == "weed"
            and not instance.partial
            and gt_track_key(frame, instance) in selected_all_weeds - selected_eligible
            and point_in_polygon(point, instance.polygon)
            for instance in frame.instances
        )
        matched_key: tuple[str, str, str, str] | None = None
        if crop_hit:
            disposition = "crop_collision_false_positive"
            crop_collision += 1
            false_positive += 1
        elif partial_hit:
            disposition = "partial_or_unknown_false_positive"
            partial_unknown_shot += 1
            false_positive += 1
        elif eligible_hits:
            unmatched = [key for key in eligible_hits if key not in matched]
            if unmatched:
                matched_key = unmatched[0]
                matched.add(matched_key)
                true_positive += 1
                disposition = "true_positive_first_track_hit"
            else:
                matched_key = eligible_hits[0]
                duplicate_shot += 1
                false_positive += 1
                disposition = "duplicate_track_hit_false_positive"
        elif ineligible_hit:
            ignored_ineligible += 1
            disposition = "ignored_noneligible_nonpartial_weed_hit"
        else:
            false_positive += 1
            disposition = "background_false_positive"
        if include_event_audit:
            audit.append(
                {
                    **asdict(event),
                    "action_point": list(event.action_point),
                    "disposition": disposition,
                    "matched_gt_track": list(matched_key) if matched_key else None,
                }
            )
    false_negative = len(selected_eligible) - len(matched)
    precision = _safe_rate(true_positive, true_positive + false_positive)
    recall = _safe_rate(true_positive, len(selected_eligible))
    if precision is None or recall is None or precision + recall == 0.0:
        f1 = None if precision is None or recall is None else 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    attempted = len(selected_events)
    metric: dict[str, Any] = {
        "eligible_weed_tracks": len(selected_eligible),
        "all_gt_weed_tracks": len(selected_all_weeds),
        "excluded_noneligible_weed_tracks": len(selected_all_weeds - selected_eligible),
        "matched_eligible_weed_tracks": len(matched),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "attempted_fire_events": attempted,
        "scored_fire_events": true_positive + false_positive,
        "ignored_noneligible_weed_hits": ignored_ineligible,
        "partial_or_unknown_shots": partial_unknown_shot,
        "crop_collision": crop_collision,
        "crop_hit_rate": _safe_rate(crop_collision, attempted),
        "crop_hit_wilson_upper_95": wilson_upper(crop_collision, attempted),
        "duplicate_shot": duplicate_shot,
        "duplicate_shot_rate": _safe_rate(duplicate_shot, attempted),
    }
    if include_event_audit:
        metric["event_audit"] = audit
    return metric


def metric_gates(metric: Mapping[str, Any], gates: Mapping[str, Any]) -> dict[str, bool]:
    def at_least(key: str, minimum: float) -> bool:
        value = metric.get(key)
        return value is not None and float(value) >= minimum

    def at_most(key: str, maximum: float) -> bool:
        value = metric.get(key)
        return value is not None and float(value) <= maximum

    checks = {
        "precision": at_least("precision", float(gates["precision_minimum"])),
        "recall": at_least("recall", float(gates["recall_minimum"])),
        "f1": at_least("f1", float(gates["f1_minimum"])),
        "crop_hit_rate": at_most(
            "crop_hit_rate", float(gates["crop_hit_rate_maximum"])
        ),
        "crop_hit_wilson_upper_95": (
            not bool(gates["crop_hit_upper_confidence_bound_required"])
            or at_most(
                "crop_hit_wilson_upper_95",
                float(gates["crop_hit_rate_maximum"]),
            )
        ),
        "duplicate_shot_rate": at_most(
            "duplicate_shot_rate", float(gates["duplicate_shot_rate_maximum"])
        ),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def _split_evaluation(
    frames: Sequence[Frame],
    predictions: Mapping[str, PredictionFrame],
    config: Mapping[str, Any],
    *,
    split: str,
    threshold: float,
    include_event_audit: bool,
) -> dict[str, Any]:
    temporal = config["temporal_action"]
    events, temporal_counts = simulate_fire_events(
        frames,
        predictions,
        split=split,
        weed_threshold=threshold,
        minimum_confirmations=int(temporal["minimum_confirmations"]),
        window_frames=int(temporal["preferred_window_frames"]),
        crop_mask_threshold=float(temporal["crop_mask_confidence_threshold"]),
    )
    eligible, all_weeds = eligible_track_sets(frames, split, config)
    pooled = score_fire_events(
        frames,
        events,
        eligible,
        all_weeds,
        include_event_audit=include_event_audit,
    )
    fields = sorted({frame.field_id for frame in frames if frame.split == split})
    per_field = {
        field: score_fire_events(
            frames,
            events,
            eligible,
            all_weeds,
            field_id=field,
            include_event_audit=False,
        )
        for field in fields
    }
    return {
        "split": split,
        "fixed_weed_confidence_threshold": threshold,
        "temporal_counts": temporal_counts,
        "pooled": pooled,
        "per_field": per_field,
    }


def _selection_metric(metric: Mapping[str, Any], key: str) -> float:
    value = metric.get(key)
    return float(value) if value is not None else -1.0


def choose_validation_threshold(
    curve: Sequence[Mapping[str, Any]], calibration: Mapping[str, Any]
) -> dict[str, Any]:
    def feasible(row: Mapping[str, Any]) -> bool:
        metric = row["metrics"]
        upper_bound_feasible = (
            not bool(calibration["crop_hit_upper_confidence_bound_required"])
            or (
                metric["crop_hit_wilson_upper_95"] is not None
                and float(metric["crop_hit_wilson_upper_95"])
                <= float(calibration["maximum_crop_hit_rate"])
            )
        )
        return (
            metric["precision"] is not None
            and float(metric["precision"]) >= float(calibration["minimum_precision"])
            and metric["crop_hit_rate"] is not None
            and float(metric["crop_hit_rate"])
            <= float(calibration["maximum_crop_hit_rate"])
            and metric["duplicate_shot_rate"] is not None
            and float(metric["duplicate_shot_rate"])
            <= float(calibration["maximum_duplicate_shot_rate"])
            and upper_bound_feasible
        )

    feasible_rows = [row for row in curve if feasible(row)]
    if feasible_rows:
        selected = max(
            feasible_rows,
            key=lambda row: (
                _selection_metric(row["metrics"], "recall"),
                _selection_metric(row["metrics"], "f1"),
                _selection_metric(row["metrics"], "precision"),
                float(row["threshold"]),
            ),
        )
        status = "validation_safety_feasible"
        constraints_passed = True
    else:
        selected = max(
            curve,
            key=lambda row: (
                _selection_metric(row["metrics"], "f1"),
                _selection_metric(row["metrics"], "precision"),
                _selection_metric(row["metrics"], "recall"),
                float(row["threshold"]),
            ),
        )
        status = "no_validation_safety_feasible_threshold_fallback_for_diagnostics"
        constraints_passed = False
    return {
        "status": status,
        "constraints_passed": constraints_passed,
        "threshold": float(selected["threshold"]),
        "validation_metrics": selected["metrics"],
    }


def _worst_field(per_field: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, direction in (
        ("precision", "minimum"),
        ("recall", "minimum"),
        ("f1", "minimum"),
        ("crop_hit_rate", "maximum"),
        ("crop_hit_wilson_upper_95", "maximum"),
        ("duplicate_shot_rate", "maximum"),
    ):
        undefined = sorted(field for field, metric in per_field.items() if metric[key] is None)
        if undefined:
            output[key] = {"field_id": undefined[0], "value": None, "direction": direction}
            continue
        chooser = min if direction == "minimum" else max
        field_id, metric = chooser(
            per_field.items(), key=lambda item: (float(item[1][key]), item[0])
        )
        output[key] = {"field_id": field_id, "value": metric[key], "direction": direction}
    return output


def readiness_checks(
    frames: Sequence[Frame], config: Mapping[str, Any]
) -> dict[str, bool]:
    readiness = config["readiness"]
    calibration_split = config["capture_manifest"]["calibration_split"]
    test_split = config["capture_manifest"]["locked_test_split"]
    all_fields = {frame.field_id for frame in frames}
    all_field_sessions = {(frame.field_id, frame.session_id) for frame in frames}
    train_frames = [frame for frame in frames if frame.split == "train"]
    train_fields = {frame.field_id for frame in train_frames}
    validation_fields = {frame.field_id for frame in frames if frame.split == calibration_split}
    test_fields = {frame.field_id for frame in frames if frame.split == test_split}
    validation_eligible, _ = eligible_track_sets(frames, calibration_split, config)
    test_eligible, _ = eligible_track_sets(frames, test_split, config)
    test_eligible_fields = {key[0] for key in test_eligible}
    checks = {
        "minimum_total_fields": len(all_fields) >= int(readiness["minimum_total_fields"]),
        "minimum_total_field_sessions": len(all_field_sessions)
        >= int(readiness["minimum_total_field_sessions"]),
        "minimum_train_frames": len(train_frames) >= int(readiness["minimum_train_frames"]),
        "minimum_train_fields": len(train_fields) >= int(readiness["minimum_train_fields"]),
        "minimum_validation_fields": len(validation_fields)
        >= int(readiness["minimum_validation_fields"]),
        "minimum_test_fields": len(test_fields) >= int(readiness["minimum_test_fields"]),
        "minimum_validation_eligible_weed_tracks": len(validation_eligible)
        >= int(readiness["minimum_validation_eligible_weed_tracks"]),
        "minimum_test_eligible_weed_tracks": len(test_eligible)
        >= int(readiness["minimum_test_eligible_weed_tracks"]),
        "each_test_field_has_eligible_weed": (
            not bool(readiness["require_each_test_field_has_eligible_weed"])
            or test_fields == test_eligible_fields
        ),
        "validation_and_test_are_distinct": calibration_split != test_split,
        "all_frames_have_frozen_split": all(frame.split != "unassigned" for frame in frames),
        "adjacent_frames_do_not_cross_splits": True,
        "prediction_coverage_exact": True,
        "manifest_and_prediction_contracts_valid": True,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def _resolve_input(
    cli_value: Path | None, configured: Any, *, base: Path
) -> Path | None:
    if cli_value is not None:
        return cli_value.expanduser().resolve()
    if configured in (None, ""):
        return None
    path = Path(str(configured)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def validate_locked_sources(config: Mapping[str, Any]) -> None:
    for name, source in config["locked_sources"].items():
        path = (PROJECT_ROOT / str(source["path"])).resolve()
        if not path.is_file() or sha256(path) != str(source["sha256"]):
            raise ContractError(f"Locked source drift: {name} -> {path}")


def validate_frozen_protocol(config: Mapping[str, Any]) -> None:
    audit = config["capture_audit"]
    expected_audit = {
        "contract": "spot_spray_capture_audit_v1",
        "manifest_contract": "capture_manifest_v1",
        "real_ready_status": "READY",
        "real_evidence_scope": "real_target_rig",
    }
    for key, expected in expected_audit.items():
        if audit.get(key) != expected:
            raise ContractError(f"Frozen capture-audit protocol drift: {key}")
    expected_sources = {
        "schema": "configs/data/spot_spray_capture_manifest_v1.schema.json",
        "policy": "configs/data/spot_spray_capture_audit_v1.yaml",
        "implementation": "scripts/audit_spot_spray_capture_v1.py",
    }
    if audit.get("trusted_sources") != expected_sources:
        raise ContractError("Frozen capture-audit trusted-source paths drift")
    if "capture_audit_result_sha256" not in set(
        config["prediction_jsonl"]["required_metadata_fields"]
    ):
        raise ContractError("Prediction provenance must bind the capture-audit SHA-256")

    deploy_source = config["locked_sources"]["deploy_contract"]
    deploy_path = (PROJECT_ROOT / str(deploy_source["path"])).resolve()
    deploy = yaml.safe_load(deploy_path.read_text(encoding="utf-8"))
    deploy_gates = deploy["offline_go_gates"]
    gates = config["offline_go_gates"]
    frozen_gate_pairs = {
        "precision_minimum": "primary_track_precision_minimum",
        "recall_minimum": "primary_track_recall_minimum",
        "f1_minimum": "primary_track_f1_minimum",
        "crop_hit_rate_maximum": "crop_hit_rate_maximum",
        "duplicate_shot_rate_maximum": "duplicate_shot_rate_maximum",
        "synthetic_score_weight_in_real_go_decision": (
            "synthetic_score_weight_in_real_go_decision"
        ),
    }
    for local_key, deploy_key in frozen_gate_pairs.items():
        if float(gates[local_key]) != float(deploy_gates[deploy_key]):
            raise ContractError(f"Frozen offline GO gate drift: {local_key}")
    upper_required = deploy_gates["crop_hit_upper_confidence_bound_required"]
    if upper_required is not True:
        raise ContractError("Locked deploy contract no longer requires crop-hit upper bound")
    if gates.get("crop_hit_upper_confidence_bound_required") is not True:
        raise ContractError("Offline crop-hit upper-confidence gate cannot be disabled")
    calibration = config["threshold_calibration"]
    if calibration.get("crop_hit_upper_confidence_bound_required") is not True:
        raise ContractError("Validation crop-hit upper-confidence gate cannot be disabled")
    for local_key, gate_key in (
        ("minimum_precision", "precision_minimum"),
        ("maximum_crop_hit_rate", "crop_hit_rate_maximum"),
        ("maximum_duplicate_shot_rate", "duplicate_shot_rate_maximum"),
    ):
        if float(calibration[local_key]) != float(gates[gate_key]):
            raise ContractError(f"Validation safety gate drift: {local_key}")


def _write_json(path: Path, payload: Mapping[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ContractError(f"Output already exists: {path}; pass --overwrite explicitly")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def not_ready_payload(
    config_path: Path,
    reason: str,
    *,
    manifest_path: Path | None,
    audit_path: Path | None,
    prediction_path: Path | None,
    status: str = "NOT_READY",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": "spot_spray_target_rig_track_action_eval_v1",
        "status": status,
        "reason": reason,
        "config": str(config_path),
        "config_sha256": sha256(config_path) if config_path.is_file() else None,
        "inputs": {
            "capture_manifest_json": str(manifest_path) if manifest_path else None,
            "capture_audit_result_json": str(audit_path) if audit_path else None,
            "prediction_jsonl": str(prediction_path) if prediction_path else None,
        },
        "decision": {
            "offline_model_go": False,
            "field_fire_go": False,
            "chemical_fire_go": False,
            "synthetic_score_weight_in_real_go_decision": 0.0,
            "fail_closed": True,
        },
    }


def evaluate(
    config_path: Path,
    manifest_path: Path,
    audit_path: Path,
    prediction_path: Path,
    *,
    fixture_mode: bool = False,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ContractError("Evaluation config schema mismatch")
    validate_locked_sources(config)
    validate_frozen_protocol(config)
    if float(
        config["offline_go_gates"]["synthetic_score_weight_in_real_go_decision"]
    ) != 0.0:
        raise ContractError("Synthetic real-GO score weight must remain zero")
    manifest = load_manifest(manifest_path, config)
    frames = manifest.frames
    capture_audit = load_capture_audit(audit_path, manifest_path, config)
    predictions, prediction_metadata = load_predictions(
        prediction_path, manifest_path, capture_audit, frames, config
    )
    calibration_split = str(config["capture_manifest"]["calibration_split"])
    test_split = str(config["capture_manifest"]["locked_test_split"])
    curve: list[dict[str, Any]] = []
    for threshold in threshold_grid(config):
        validation = _split_evaluation(
            frames,
            predictions,
            config,
            split=calibration_split,
            threshold=threshold,
            include_event_audit=False,
        )
        curve.append({"threshold": threshold, "metrics": validation["pooled"]})
    selection = choose_validation_threshold(curve, config["threshold_calibration"])
    selected_threshold = float(selection["threshold"])
    validation_selected = _split_evaluation(
        frames,
        predictions,
        config,
        split=calibration_split,
        threshold=selected_threshold,
        include_event_audit=True,
    )
    test = _split_evaluation(
        frames,
        predictions,
        config,
        split=test_split,
        threshold=selected_threshold,
        include_event_audit=True,
    )
    gates = config["offline_go_gates"]
    pooled_gates = metric_gates(test["pooled"], gates)
    per_field_gates = {
        field: metric_gates(metric, gates) for field, metric in test["per_field"].items()
    }
    readiness = readiness_checks(frames, config)
    evaluated_checkpoint = config["model"]["evaluated_checkpoint"]
    checkpoint_path = evaluated_checkpoint["checkpoint"]
    checkpoint_sha = evaluated_checkpoint["checkpoint_sha256"]
    resolved_checkpoint: Path | None = None
    if isinstance(checkpoint_path, str) and checkpoint_path:
        candidate_checkpoint = Path(checkpoint_path).expanduser()
        resolved_checkpoint = (
            candidate_checkpoint.resolve()
            if candidate_checkpoint.is_absolute()
            else (PROJECT_ROOT / candidate_checkpoint).resolve()
        )
    checkpoint_frozen = (
        resolved_checkpoint is not None
        and resolved_checkpoint.is_file()
        and isinstance(checkpoint_sha, str)
        and re.fullmatch(r"[0-9a-f]{64}", checkpoint_sha) is not None
        and sha256(resolved_checkpoint) == checkpoint_sha
        and prediction_metadata["model_checkpoint_sha256"] == checkpoint_sha
    )
    readiness["evaluated_checkpoint_path_and_hash_frozen"] = checkpoint_frozen
    readiness["capture_audit_real_proof_accepted"] = (
        capture_audit.real_proof_accepted
    )
    readiness["all_pass"] = all(
        value for key, value in readiness.items() if key != "all_pass"
    )
    every_field_pass = bool(per_field_gates) and all(
        item["all_pass"] for item in per_field_gates.values()
    )
    effective_fixture_mode = (
        fixture_mode
        or manifest.evidence_scope == "synthetic_fixture"
        or capture_audit.synthetic_fixture
    )
    real_data_ready = (
        readiness["all_pass"]
        and manifest.evidence_scope == "real_target_rig"
        and capture_audit.evidence_scope == "real_target_rig"
        and capture_audit.real_proof_accepted
        and not fixture_mode
    )
    offline_model_go = bool(
        real_data_ready
        and selection["constraints_passed"]
        and pooled_gates["all_pass"]
        and every_field_pass
    )
    if effective_fixture_mode:
        status = "FIXTURE_ONLY"
    elif not real_data_ready:
        status = "NOT_READY"
    elif offline_model_go:
        status = "EVALUATED_OFFLINE_MODEL_GO"
    else:
        status = "EVALUATED_NO_GO"
    result = {
        "schema_version": 1,
        "contract": config["contract"],
        "status": status,
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "inputs": {
            "capture_manifest_json": str(manifest_path),
            "capture_manifest_sha256": sha256(manifest_path),
            "capture_manifest_id": manifest.manifest_id,
            "capture_evidence_scope": manifest.evidence_scope,
            "capture_audit_result_json": capture_audit.path,
            "capture_audit_result_sha256": capture_audit.sha256,
            "capture_audit_data_root": capture_audit.data_root,
            "prediction_jsonl": str(prediction_path),
            **prediction_metadata,
        },
        "model": config["model"],
        "eligible_weed_track_contract": config["eligible_weed_track"],
        "temporal_action_contract": config["temporal_action"],
        "calibration": {
            "source_split": calibration_split,
            "test_accessed_during_selection": False,
            "selection": selection,
            "curve": curve,
            "selected_split_metrics": validation_selected,
        },
        "test": {
            **test,
            "threshold_source": "validation_only",
            "pooled_gates": pooled_gates,
            "per_field_gates": per_field_gates,
            "worst_field": _worst_field(test["per_field"]),
            "every_field_pass": every_field_pass,
        },
        "readiness": {
            "fixture_mode_requested": fixture_mode,
            "capture_evidence_scope": manifest.evidence_scope,
            "capture_audit_evidence_scope": capture_audit.evidence_scope,
            "capture_audit_status": capture_audit.status,
            "capture_audit_real_proof_checks": dict(
                capture_audit.real_proof_checks
            ),
            "capture_audit_real_proof_accepted": capture_audit.real_proof_accepted,
            "checks": readiness,
            "real_data_ready": real_data_ready,
        },
        "decision": {
            "offline_model_go": offline_model_go,
            "field_fire_go": False,
            "chemical_fire_go": False,
            "chemical_fire_blocker": "Independent registration, deposition, crop-injury, and physical safety gates are outside this model evaluator.",
            "synthetic_score_weight_in_real_go_decision": 0.0,
            "pooled_and_every_field_required": True,
            "fail_closed": True,
        },
        "claims": config["claims"],
    }
    return result


def exit_code_for_status(status: str) -> int:
    try:
        return {
            "EVALUATED_OFFLINE_MODEL_GO": EXIT_EVALUATED_OFFLINE_MODEL_GO,
            "NOT_READY": EXIT_NOT_READY,
            "EVALUATED_NO_GO": EXIT_EVALUATED_NO_GO,
            "FIXTURE_ONLY": EXIT_FIXTURE_ONLY,
            "CONTRACT_ERROR": EXIT_CONTRACT_ERROR,
        }[status]
    except KeyError as error:
        raise ContractError(f"Unknown evaluator status: {status}") from error


def run_cli(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config_path = arguments.config.expanduser().resolve()
    manifest_path = (
        arguments.manifest.expanduser().resolve() if arguments.manifest else None
    )
    audit_path = (
        arguments.capture_audit.expanduser().resolve()
        if arguments.capture_audit
        else None
    )
    prediction_path = (
        arguments.predictions.expanduser().resolve() if arguments.predictions else None
    )
    output_path = arguments.output.expanduser().resolve() if arguments.output else None
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        base = PROJECT_ROOT
        manifest_path = _resolve_input(
            arguments.manifest, config["inputs"]["capture_manifest_json"], base=base
        )
        audit_path = _resolve_input(
            arguments.capture_audit,
            config["inputs"]["capture_audit_result_json"],
            base=base,
        )
        prediction_path = _resolve_input(
            arguments.predictions, config["inputs"]["prediction_jsonl"], base=base
        )
        output_path = _resolve_input(
            arguments.output, config["inputs"]["output_json"], base=base
        )
        if manifest_path is None or audit_path is None or prediction_path is None:
            missing = []
            if manifest_path is None:
                missing.append("capture_manifest_json")
            if audit_path is None:
                missing.append("capture_audit_result_json")
            if prediction_path is None:
                missing.append("prediction_jsonl")
            result = not_ready_payload(
                config_path,
                f"Missing required real-data inputs: {', '.join(missing)}",
                manifest_path=manifest_path,
                audit_path=audit_path,
                prediction_path=prediction_path,
            )
            exit_code = exit_code_for_status(result["status"])
        else:
            result = evaluate(
                config_path,
                manifest_path,
                audit_path,
                prediction_path,
                fixture_mode=arguments.fixture_mode,
            )
            exit_code = exit_code_for_status(result["status"])
        if output_path is not None:
            _write_json(output_path, result, overwrite=arguments.overwrite)
    except (ContractError, KeyError, TypeError, OSError, yaml.YAMLError) as error:
        result = not_ready_payload(
            config_path,
            f"Fail-closed contract error: {error}",
            manifest_path=manifest_path,
            audit_path=audit_path,
            prediction_path=prediction_path,
            status="CONTRACT_ERROR",
        )
        exit_code = exit_code_for_status(result["status"])
    return result, exit_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--capture-audit",
        type=Path,
        help="Capture audit JSON whose exact SHA-256 is bound in prediction metadata.",
    )
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--fixture-mode",
        action="store_true",
        help="Evaluate synthetic contract fixtures while permanently forcing real GO false.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    result, exit_code = run_cli(parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
