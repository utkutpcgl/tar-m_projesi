#!/usr/bin/env python3
"""Evaluate measured spot-spray rig receipts against frozen V2 A-E gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    PROJECT_ROOT / "configs/deploy/spot_spray_rig_acceptance_v1.yaml"
)
DEFAULT_CONTRACT_SHA256 = (
    "a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c"
)
DEFAULT_CONTRACT_CANONICAL_SHA256 = (
    "c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21"
)
CONTRACT_IDENTITY_ALGORITHM = "sha256_exact_bytes_plus_canonical_json_v1"
MISSING = object()
PASS = "PASS"
FAIL = "FAIL"
NOT_MEASURED = "NOT_MEASURED"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate mapping key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.load(
        path.read_text(encoding="utf-8"),
        Loader=UniqueKeySafeLoader,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return payload


def render(result: Mapping[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _json_value(value: Any) -> Any:
    if value is MISSING:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_mapping_sha256(mapping: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _json_value(mapping),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_contract_identity(
    contract: Mapping[str, Any],
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Reject policy drift before any receipt or stage gate is evaluated."""

    canonical_sha256 = canonical_mapping_sha256(contract)
    if canonical_sha256 != DEFAULT_CONTRACT_CANONICAL_SHA256:
        raise ValueError(
            "Contract canonical-policy identity mismatch; refusing gate "
            f"evaluation (expected {DEFAULT_CONTRACT_CANONICAL_SHA256}, "
            f"observed {canonical_sha256})."
        )

    exact_sha256 = None
    exact_bytes_verified = False
    if contract_path is not None:
        exact_sha256 = sha256_file(contract_path)
        if exact_sha256 != DEFAULT_CONTRACT_SHA256:
            raise ValueError(
                "Contract exact-byte identity mismatch; refusing gate "
                f"evaluation (expected {DEFAULT_CONTRACT_SHA256}, "
                f"observed {exact_sha256})."
            )
        exact_bytes_verified = True

    return {
        "identity_id": contract["default_contract_identity"]["identity_id"],
        "algorithm": CONTRACT_IDENTITY_ALGORITHM,
        "default_contract_path": str(DEFAULT_CONTRACT.relative_to(PROJECT_ROOT)),
        "expected_exact_byte_sha256": DEFAULT_CONTRACT_SHA256,
        "observed_exact_byte_sha256": exact_sha256,
        "exact_bytes_verified": exact_bytes_verified,
        "expected_canonical_policy_sha256": DEFAULT_CONTRACT_CANONICAL_SHA256,
        "observed_canonical_policy_sha256": canonical_sha256,
        "canonical_policy_verified": True,
    }


def _paths_collide(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    if left == right:
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def validate_output_path(
    output_path: Path,
    protected_paths: Mapping[str, Path],
) -> Path:
    output_path = output_path.resolve()
    for label, protected_path in protected_paths.items():
        if _paths_collide(output_path, protected_path):
            raise ValueError(
                f"Output path collides with protected {label}: {protected_path.resolve()}"
            )
    return output_path


def atomic_write_text(path: Path, payload: str) -> None:
    """Replace one result file atomically without exposing partial JSON."""

    path = path.resolve()
    if not path.parent.is_dir():
        raise ValueError(f"Output directory does not exist: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _get(mapping: Any, path: str) -> Any:
    value = mapping
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return MISSING
        value = value[key]
    return value


def _unmeasured(value: Any) -> bool:
    return value is MISSING or value is None or value == "not_measured"


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value is not numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("value is not finite")
    return value


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(
            _number(actual), _number(expected), rel_tol=0.0, abs_tol=1e-9
        )
    return actual == expected


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_aware_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp lacks a UTC offset")
    return parsed


def check(
    check_id: str,
    actual: Any,
    operator: str,
    expected: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "check_id": check_id,
        "operator": operator,
        "actual": _json_value(actual),
        "expected": _json_value(expected),
    }
    if _unmeasured(actual):
        result.update(
            status=NOT_MEASURED,
            reason="required value is missing, null, or explicitly not_measured",
        )
        return result
    try:
        if operator == "eq":
            passed = _equal(actual, expected)
        elif operator == "ge":
            passed = _number(actual) >= _number(expected)
        elif operator == "gt":
            passed = _number(actual) > _number(expected)
        elif operator == "le":
            passed = _number(actual) <= _number(expected)
        elif operator == "between":
            lower, upper = expected
            passed = _number(lower) <= _number(actual) <= _number(upper)
        elif operator == "finite_number":
            _number(actual)
            passed = True
        elif operator == "nonempty":
            passed = isinstance(actual, str) and bool(actual.strip())
        elif operator == "date_gt":
            passed = _as_date(actual) > _as_date(expected)
        elif operator == "aware_datetime":
            _as_aware_datetime(actual)
            passed = True
        elif operator == "sha256":
            passed = isinstance(actual, str) and SHA256_RE.fullmatch(actual) is not None
        elif operator == "commit":
            passed = isinstance(actual, str) and COMMIT_RE.fullmatch(actual) is not None
        elif operator == "set_eq":
            if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
                raise TypeError("value is not a sequence")
            passed = set(actual) == set(expected) and len(actual) == len(expected)
        elif operator == "in":
            passed = actual in expected
        else:
            raise ValueError(f"unsupported operator: {operator}")
    except (TypeError, ValueError) as exc:
        result.update(status=FAIL, reason=f"invalid measured value: {exc}")
        return result
    result.update(
        status=PASS if passed else FAIL,
        reason="gate satisfied" if passed else "measured value violates gate",
    )
    return result


def combine_status(statuses: Sequence[str]) -> str:
    if any(status == FAIL for status in statuses):
        return FAIL
    if any(status == NOT_MEASURED for status in statuses):
        return NOT_MEASURED
    return PASS


def gate(gate_id: str, checks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    checks = list(checks)
    return {
        "gate_id": gate_id,
        "status": combine_status([item["status"] for item in checks]),
        "checks": checks,
    }


def _receipt_validation(
    contract: Mapping[str, Any], receipt: Mapping[str, Any]
) -> dict[str, Any]:
    policy = contract["receipt_contract"]
    checks = []
    for field in policy["required_root_fields"]:
        value = _get(receipt, field)
        checks.append(
            check(f"root.{field}.present", not _unmeasured(value), "eq", True)
        )
    checks.extend(
        [
            check(
                "root.receipt_schema_version",
                _get(receipt, "receipt_schema_version"),
                "eq",
                policy["receipt_schema_version"],
            ),
            check(
                "root.contract_id",
                _get(receipt, "contract_id"),
                "eq",
                contract["contract_id"],
            ),
            check("root.receipt_id", _get(receipt, "receipt_id"), "nonempty"),
            check(
                "root.created_at_utc",
                _get(receipt, "created_at_utc"),
                "aware_datetime",
            ),
            check("root.rig_unit_id", _get(receipt, "rig_unit_id"), "nonempty"),
            check(
                "root.hardware_revision",
                _get(receipt, "hardware_revision"),
                "nonempty",
            ),
            check(
                "root.software_commit",
                _get(receipt, "software_commit"),
                "commit",
            ),
        ]
    )
    evidence_kind = _get(receipt, "evidence_kind")
    checks.append(
        check(
            "root.evidence_kind",
            evidence_kind,
            "in",
            policy["evidence_kinds"],
        )
    )
    if evidence_kind == "synthetic_fixture":
        checks.extend(
            [
                check(
                    "root.synthetic_fixture",
                    _get(receipt, "synthetic_fixture"),
                    "eq",
                    True,
                ),
                check(
                    "root.deployment_evidence",
                    _get(receipt, "deployment_evidence"),
                    "eq",
                    False,
                ),
            ]
        )
    elif evidence_kind == "physical_bench":
        checks.extend(
            [
                check(
                    "root.synthetic_fixture",
                    _get(receipt, "synthetic_fixture"),
                    "eq",
                    False,
                ),
                check(
                    "root.deployment_evidence",
                    _get(receipt, "deployment_evidence"),
                    "eq",
                    True,
                ),
            ]
        )
    return gate("receipt_schema_and_evidence_class", checks)


def _source_integrity(
    contract: Mapping[str, Any], receipt: Mapping[str, Any], root: Path
) -> dict[str, Any]:
    receipt_hashes = _get(receipt, "frozen_v2_source_sha256")
    checks: list[dict[str, Any]] = []
    for source_name in ("capture_contract", "decision_document"):
        frozen = contract["frozen_v2_sources"][source_name]
        path = (root / frozen["path"]).resolve()
        actual_hash = sha256_file(path) if path.is_file() else MISSING
        checks.append(
            check(
                f"source.{source_name}.workspace_sha256",
                actual_hash,
                "eq",
                frozen["sha256"],
            )
        )
        declared = (
            _get(receipt_hashes, source_name)
            if isinstance(receipt_hashes, Mapping)
            else MISSING
        )
        checks.append(
            check(
                f"source.{source_name}.receipt_sha256",
                declared,
                "eq",
                frozen["sha256"],
            )
        )
    return gate("frozen_v2_source_integrity", checks)


def _artifact_check(
    artifact_id: str,
    artifact: Any,
    evidence_kind: Any,
    receipt_dir: Path,
) -> list[dict[str, Any]]:
    if not isinstance(artifact, Mapping):
        return [check(f"artifact.{artifact_id}.present", artifact, "nonempty")]
    if evidence_kind == "synthetic_fixture":
        uri = _get(artifact, "uri")
        return [
            check(
                f"artifact.{artifact_id}.kind",
                _get(artifact, "kind"),
                "eq",
                "synthetic_placeholder",
            ),
            check(
                f"artifact.{artifact_id}.deployment_evidence",
                _get(artifact, "deployment_evidence"),
                "eq",
                False,
            ),
            check(
                f"artifact.{artifact_id}.synthetic_uri",
                isinstance(uri, str) and uri.startswith("synthetic://"),
                "eq",
                True,
            ),
        ]
    if evidence_kind != "physical_bench":
        return [check(f"artifact.{artifact_id}.evidence_kind", evidence_kind, "eq", "physical_bench")]
    declared_path = _get(artifact, "path")
    declared_hash = _get(artifact, "sha256")
    checks = [
        check(f"artifact.{artifact_id}.kind", _get(artifact, "kind"), "nonempty"),
        check(
            f"artifact.{artifact_id}.captured_at_utc",
            _get(artifact, "captured_at_utc"),
            "aware_datetime",
        ),
        check(f"artifact.{artifact_id}.path", declared_path, "nonempty"),
        check(f"artifact.{artifact_id}.sha256_format", declared_hash, "sha256"),
    ]
    if not _unmeasured(declared_path):
        path = Path(str(declared_path)).expanduser()
        path = path.resolve() if path.is_absolute() else (receipt_dir / path).resolve()
        actual_hash = sha256_file(path) if path.is_file() else MISSING
        checks.append(
            check(
                f"artifact.{artifact_id}.file_sha256",
                actual_hash,
                "eq",
                declared_hash,
            )
        )
    return checks


def _stage_evidence_gate(
    stage_name: str,
    stage: Mapping[str, Any],
    receipt: Mapping[str, Any],
    receipt_dir: Path,
) -> dict[str, Any]:
    artifact_ids = _get(stage, "evidence_artifact_ids")
    if _unmeasured(artifact_ids):
        return gate(
            f"{stage_name}.evidence",
            [check("evidence_artifact_ids", artifact_ids, "nonempty")],
        )
    if not isinstance(artifact_ids, list) or not artifact_ids:
        return gate(
            f"{stage_name}.evidence",
            [check("evidence_artifact_ids", artifact_ids, "nonempty")],
        )
    artifacts = _get(receipt, "artifacts")
    checks: list[dict[str, Any]] = []
    for artifact_id in artifact_ids:
        artifact = (
            artifacts.get(artifact_id, MISSING)
            if isinstance(artifacts, Mapping)
            else MISSING
        )
        checks.extend(
            _artifact_check(
                str(artifact_id),
                artifact,
                _get(receipt, "evidence_kind"),
                receipt_dir,
            )
        )
    return gate(f"{stage_name}.evidence", checks)


def _stage_A(stage: Mapping[str, Any], thresholds: Mapping[str, Any]) -> list[dict[str, Any]]:
    camera = thresholds["camera"]
    lens = thresholds["lens"]
    cable = thresholds["cable"]
    return [
        gate(
            "A.exact_hardware_identity",
            [
                check("camera.manufacturer", _get(stage, "camera.manufacturer"), "eq", camera["manufacturer"]),
                check("camera.model", _get(stage, "camera.model"), "eq", camera["model"]),
                check("camera.order_number", _get(stage, "camera.order_number"), "eq", camera["order_number"]),
                check("camera.serial_number", _get(stage, "camera.serial_number"), "nonempty"),
                check("camera.color_sensor", _get(stage, "camera.color_sensor"), "eq", camera["color_sensor_required"]),
                check("camera.factory_ir_cut", _get(stage, "camera.factory_ir_cut"), "eq", camera["factory_ir_cut_required"]),
                check("lens.manufacturer", _get(stage, "lens.manufacturer"), "eq", lens["manufacturer"]),
                check("lens.model", _get(stage, "lens.model"), "eq", lens["model"]),
                check("lens.order_number", _get(stage, "lens.order_number"), "eq", lens["order_number"]),
                check("lens.serial_number", _get(stage, "lens.serial_number"), "nonempty"),
            ],
        ),
        gate(
            "A.interface_and_power_variant",
            [
                check("installed_power_source", _get(stage, "installed_power_source"), "eq", camera["installed_power_source"]),
                check("locking_cable", _get(stage, "locking_cable"), "eq", cable["locking_required"]),
                check("cable_length_m", _get(stage, "cable_length_m"), "le", cable["maximum_length_m"]),
                check("dedicated_USB3_root", _get(stage, "dedicated_USB3_root"), "eq", thresholds["dedicated_USB3_root_required"]),
            ],
        ),
        gate(
            "A.refreshed_quote_and_lead_time",
            [
                check("supplier_quote_id", _get(stage, "supplier_quote_id"), "nonempty"),
                check("supplier_quote_date", _get(stage, "supplier_quote_date"), "date_gt", thresholds["supplier_quote_strictly_after"]),
                check("supplier_lead_time_days", _get(stage, "supplier_lead_time_days"), "ge", 0),
            ],
        ),
    ]


def _stage_B(stage: Mapping[str, Any], t: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        gate(
            "B.transport_and_frame_integrity",
            [
                check("hardware_trigger", _get(stage, "trigger_test.hardware_trigger"), "eq", t["hardware_trigger_required"]),
                check("trigger_count", _get(stage, "trigger_test.trigger_count"), "ge", t["trigger_count_minimum"]),
                check("trigger_rate_hz", _get(stage, "trigger_test.trigger_rate_hz"), "eq", t["trigger_rate_hz"]),
                check("missing_frame_counters", _get(stage, "trigger_test.missing_frame_counters"), "le", t["missing_frame_counter_maximum"]),
                check("duplicate_frame_counters", _get(stage, "trigger_test.duplicate_frame_counters"), "le", t["duplicate_frame_counter_maximum"]),
                check("invalid_camera_timestamps", _get(stage, "trigger_test.invalid_camera_timestamps"), "le", t["invalid_camera_timestamp_maximum"]),
            ],
        ),
        gate(
            "B.trigger_encoder_strobe_timing",
            [
                check("stale_encoder_events", _get(stage, "timing.stale_encoder_events"), "le", t["stale_encoder_event_maximum"]),
                check("trigger_encoder_delta_p95_us", _get(stage, "timing.trigger_encoder_delta_p95_us"), "le", t["trigger_encoder_delta_p95_maximum_us"]),
                check("trigger_encoder_delta_max_us", _get(stage, "timing.trigger_encoder_delta_max_us"), "le", t["trigger_encoder_delta_maximum_us"]),
                check("strobe_jitter_p95_us", _get(stage, "timing.strobe_jitter_p95_us"), "le", t["strobe_jitter_p95_maximum_us"]),
                check("pulse_width_error_fraction", _get(stage, "timing.pulse_width_error_fraction"), "le", t["pulse_width_error_maximum_fraction"]),
                check("bus_droop_fraction", _get(stage, "timing.bus_droop_fraction"), "le", t["bus_droop_maximum_fraction"]),
            ],
        ),
        gate(
            "B.two_hour_thermal_envelope",
            [
                check("duration_minutes", _get(stage, "thermal.duration_minutes"), "ge", t["thermal_duration_minimum_minutes"]),
                check("ambient_min_c", _get(stage, "thermal.ambient_min_c"), "le", t["thermal_ambient_coverage_c"][0]),
                check("ambient_max_c", _get(stage, "thermal.ambient_max_c"), "ge", t["thermal_ambient_coverage_c"][1]),
                check("camera_housing_max_c", _get(stage, "thermal.camera_housing_max_c"), "le", t["camera_housing_maximum_c"]),
                check("LED_plate_max_c", _get(stage, "thermal.LED_plate_max_c"), "le", t["LED_plate_maximum_c"]),
                check("frame_drops", _get(stage, "thermal.frame_drops"), "le", t["frame_drop_maximum"]),
                check("thermal_throttle_events", _get(stage, "thermal.thermal_throttle_events"), "le", t["thermal_throttle_event_maximum"]),
            ],
        ),
        gate(
            "B.frozen_PRO_power_path",
            [
                check("powered_USB_fallback_in_use", _get(stage, "powered_USB_fallback_in_use"), "eq", t["powered_USB_fallback_in_use"]),
            ],
        ),
    ]


def _collection_gate(
    gate_id: str,
    rows: Any,
    expected_keys: Sequence[Any],
    key_function: Any,
    row_checks: Any,
) -> dict[str, Any]:
    if _unmeasured(rows):
        return {
            "gate_id": gate_id,
            "status": NOT_MEASURED,
            "coverage": {"expected": len(expected_keys), "observed": 0},
            "missing_keys": [_json_value(key) for key in expected_keys],
            "unexpected_keys": [],
            "duplicate_keys": [],
            "records": [],
        }
    if not isinstance(rows, list):
        return {
            "gate_id": gate_id,
            "status": FAIL,
            "reason": "measurement collection is not a list",
            "coverage": {"expected": len(expected_keys), "observed": 0},
            "records": [],
        }
    expected = set(expected_keys)
    by_key: dict[Any, Mapping[str, Any]] = {}
    duplicates: list[Any] = []
    invalid_rows = False
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows = True
            continue
        key = key_function(row)
        if key in by_key:
            duplicates.append(key)
        else:
            by_key[key] = row
    observed = set(by_key)
    missing = sorted(expected - observed, key=str)
    unexpected = sorted(observed - expected, key=str)
    records: list[dict[str, Any]] = []
    for key in sorted(expected & observed, key=str):
        checks = row_checks(by_key[key])
        records.append(
            {
                "key": _json_value(list(key) if isinstance(key, tuple) else key),
                "status": combine_status([item["status"] for item in checks]),
                "checks": checks,
            }
        )
    statuses = [record["status"] for record in records]
    if invalid_rows or duplicates or unexpected:
        statuses.append(FAIL)
    if missing:
        statuses.append(NOT_MEASURED)
    return {
        "gate_id": gate_id,
        "status": combine_status(statuses),
        "coverage": {"expected": len(expected), "observed": len(observed)},
        "missing_keys": [_json_value(list(key) if isinstance(key, tuple) else key) for key in missing],
        "unexpected_keys": [_json_value(list(key) if isinstance(key, tuple) else key) for key in unexpected],
        "duplicate_keys": [_json_value(list(key) if isinstance(key, tuple) else key) for key in duplicates],
        "records": records,
    }


def _stage_C(stage: Mapping[str, Any], t: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_keys = [
        (float(plane), region)
        for plane in t["plane_offsets_above_ground_mm"]
        for region in t["region_ids"]
    ]

    def key_function(row: Mapping[str, Any]) -> tuple[Any, Any]:
        plane = _get(row, "plane_offset_above_ground_mm")
        if isinstance(plane, (int, float)) and not isinstance(plane, bool):
            plane = float(plane)
        return plane, _get(row, "region_id")

    def row_checks(row: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            check("local_GSD_mm_px", _get(row, "local_GSD_mm_px"), "le", t["local_GSD_maximum_mm_px"]),
            check("span_10mm_px", _get(row, "span_10mm_px"), "ge", t["span_10mm_minimum_px"]),
            check("span_20mm_px", _get(row, "span_20mm_px"), "ge", t["span_20mm_minimum_px"]),
            check("MTF50_cycles_px", _get(row, "MTF50_cycles_px"), "ge", t["MTF50_minimum_cycles_px"]),
            check("reprojection_RMS_px", _get(row, "reprojection_RMS_px"), "le", t["reprojection_RMS_maximum_px"]),
            check("reprojection_p95_px", _get(row, "reprojection_p95_px"), "le", t["reprojection_p95_maximum_px"]),
            check("distortion_model_valid", _get(row, "distortion_model_valid"), "eq", t["distortion_model_valid_required"]),
        ]

    return [
        gate(
            "C.installed_locked_optical_state",
            [
                check("installed_window", _get(stage, "installed_window"), "eq", t["installed_window_required"]),
                check("focus_locked", _get(stage, "focus_locked"), "eq", t["focus_and_iris_locked_required"]),
                check("iris_locked", _get(stage, "iris_locked"), "eq", t["focus_and_iris_locked_required"]),
            ],
        ),
        gate(
            "C.measured_geometry",
            [
                check("working_distance_mm", _get(stage, "working_distance_mm"), "between", t["working_distance_range_mm"]),
                check("ground_FOV_mm", _get(stage, "ground_FOV_mm"), "between", t["ground_FOV_range_mm"]),
                check("action_safe_length_mm", _get(stage, "action_safe_length_mm"), "ge", t["action_safe_length_minimum_mm"]),
            ],
        ),
        _collection_gate(
            "C.twenty_seven_cell_optical_matrix",
            _get(stage, "cells"),
            expected_keys,
            key_function,
            row_checks,
        ),
    ]


def _stage_D(stage: Mapping[str, Any], t: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_regions = list(t["region_ids"])

    def row_checks(row: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            check("ambient_off_on_ratio", _get(row, "ambient_off_on_ratio"), "le", t["ambient_off_on_ratio_maximum"]),
            check("mean_luma_8bit", _get(row, "mean_luma_8bit"), "between", t["frame_mean_luma_range_8bit"]),
            check("clipped_white_fraction", _get(row, "clipped_white_fraction"), "le", t["clipped_white_fraction_maximum"]),
            check("clipped_black_fraction", _get(row, "clipped_black_fraction"), "le", t["clipped_black_fraction_maximum"]),
            check("temporal_SNR_18pct_gray_db", _get(row, "temporal_SNR_18pct_gray_db"), "ge", t["temporal_SNR_18pct_gray_minimum_db"]),
        ]

    regions = _get(stage, "regions")
    image_gate = _collection_gate(
        "D.nine_region_image_and_ambient_metrics",
        regions,
        expected_regions,
        lambda row: _get(row, "region_id"),
        row_checks,
    )
    luma_values: list[float] = []
    if isinstance(regions, list):
        for row in regions:
            value = _get(row, "mean_luma_8bit")
            if not _unmeasured(value):
                try:
                    luma_values.append(_number(value))
                except (TypeError, ValueError):
                    pass
    derived_ratio: Any = MISSING
    if len(luma_values) == len(expected_regions) and max(luma_values) > 0:
        derived_ratio = min(luma_values) / max(luma_values)
    uniformity_gate = gate(
        "D.derived_nine_region_uniformity",
        [
            check(
                "derived_luma_min_to_max_ratio",
                derived_ratio,
                "ge",
                t["nine_region_luma_min_to_max_ratio_minimum"],
            )
        ],
    )
    polarization_enabled = _get(stage, "polarization.enabled")
    polarization_checks = [
        check(
            "paired_wet_glare_test_completed",
            _get(stage, "polarization.paired_wet_glare_test_completed"),
            "eq",
            t["paired_wet_glare_test_required"],
        ),
        check("polarization.enabled", polarization_enabled, "eq", polarization_enabled),
    ]
    if polarization_enabled is True:
        polarization_checks.append(
            check(
                "saturated_glare_reduction_fraction",
                _get(stage, "polarization.saturated_glare_reduction_fraction"),
                "ge",
                t["polarization_enable_glare_reduction_minimum_fraction"],
            )
        )
    elif polarization_enabled is not False and not _unmeasured(polarization_enabled):
        polarization_checks.append(
            check("polarization.enabled_boolean", False, "eq", True)
        )
    return [
        gate(
            "D.fixed_installed_light_setting",
            [
                check("bench_setting_id", _get(stage, "bench_setting_id"), "nonempty"),
                check("camera_controls_frozen", _get(stage, "camera_controls_frozen"), "eq", True),
                check("worst_ambient_condition_documented", _get(stage, "worst_ambient_condition_documented"), "eq", t["worst_ambient_condition_must_be_documented"]),
                check("worst_ambient_condition_id", _get(stage, "worst_ambient_condition_id"), "nonempty"),
                check("exterior_lux", _get(stage, "exterior_lux"), "ge", 0.0),
                check("camera_exposure_us", _get(stage, "camera_exposure_us"), "eq", t["camera_exposure_us"]),
                check("strobe_pulse_us", _get(stage, "strobe_pulse_us"), "between", t["strobe_pulse_range_us"]),
                check("strobe_peak_current_a", _get(stage, "strobe_peak_current_a"), "between", t["strobe_peak_current_range_a"]),
                check("correlated_color_temperature_k", _get(stage, "correlated_color_temperature_k"), "between", t["correlated_color_temperature_range_k"]),
                check("color_rendering_index", _get(stage, "color_rendering_index"), "ge", t["color_rendering_index_minimum"]),
            ],
        ),
        gate(
            "D.electrical_and_timing",
            [
                check("pulse_width_error_fraction", _get(stage, "pulse_width_error_fraction"), "le", t["pulse_width_error_maximum_fraction"]),
                check("strobe_jitter_p95_us", _get(stage, "strobe_jitter_p95_us"), "le", t["strobe_jitter_p95_maximum_us"]),
                check("bus_droop_fraction", _get(stage, "bus_droop_fraction"), "le", t["bus_droop_maximum_fraction"]),
                check("light_branch_average_power_w", _get(stage, "light_branch_average_power_w"), "le", t["light_branch_average_power_maximum_w"]),
                check("capture_module_average_power_w_excluding_compute", _get(stage, "capture_module_average_power_w_excluding_compute"), "le", t["capture_module_average_power_maximum_w_excluding_compute"]),
            ],
        ),
        gate(
            "D.thermal_at_passing_light_setting",
            [
                check("duration_minutes", _get(stage, "thermal.duration_minutes"), "ge", t["thermal_duration_minimum_minutes"]),
                check("camera_housing_max_c", _get(stage, "thermal.camera_housing_max_c"), "le", t["camera_housing_maximum_c"]),
                check("LED_plate_max_c", _get(stage, "thermal.LED_plate_max_c"), "le", t["LED_plate_maximum_c"]),
                check("frame_drops", _get(stage, "thermal.frame_drops"), "le", t["frame_drop_maximum"]),
                check("thermal_throttle_events", _get(stage, "thermal.thermal_throttle_events"), "le", t["thermal_throttle_event_maximum"]),
            ],
        ),
        image_gate,
        uniformity_gate,
        gate("D.paired_wet_glare_and_polarization", polarization_checks),
    ]


def _stage_E(stage: Mapping[str, Any], t: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_speeds = [float(value) for value in t["motion_speeds_m_s"]]

    def key_function(row: Mapping[str, Any]) -> Any:
        value = _get(row, "speed_m_s")
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value

    def row_checks(row: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            check("motion_blur_px", _get(row, "motion_blur_px"), "le", t["motion_blur_maximum_px"]),
            check("exposure_us", _get(row, "exposure_us"), "le", t["motion_exposure_maximum_us"]),
        ]

    return [
        _collection_gate(
            "E.motion_blur_at_both_speeds",
            _get(stage, "motion_trials"),
            expected_speeds,
            key_function,
            row_checks,
        ),
        gate(
            "E.minimum_valid_region_observations",
            [
                check("speed_m_s", _get(stage, "observation_test.speed_m_s"), "eq", t["observation_speed_m_s"]),
                check("rate_hz", _get(stage, "observation_test.rate_hz"), "eq", t["observation_rate_hz"]),
                check("minimum_valid_region_observations", _get(stage, "observation_test.minimum_valid_region_observations"), "ge", t["valid_region_observations_minimum"]),
            ],
        ),
        gate(
            "E.one_module_15Hz_end_to_end",
            [
                check("camera_count", _get(stage, "end_to_end.camera_count"), "eq", t["camera_count"]),
                check("rate_hz", _get(stage, "end_to_end.rate_hz"), "eq", t["end_to_end_rate_hz"]),
                check("evaluated_frame_count", _get(stage, "end_to_end.evaluated_frame_count"), "gt", 0),
                check("latency_p95_ms", _get(stage, "end_to_end.latency_p95_ms"), "le", t["end_to_end_p95_deadline_ms"]),
                check("deadline_misses", _get(stage, "end_to_end.deadline_misses"), "le", t["deadline_miss_maximum"]),
                check("frame_drops", _get(stage, "end_to_end.frame_drops"), "le", t["frame_drop_maximum"]),
                check("accelerator", _get(stage, "end_to_end.accelerator"), "eq", t["accelerator"]),
                check("model_checkpoint_sha256", _get(stage, "end_to_end.model_checkpoint_sha256"), "eq", t["model_checkpoint_sha256"]),
                check("pipeline_components", _get(stage, "end_to_end.pipeline_components"), "set_eq", t["required_pipeline_components"]),
            ],
        ),
    ]


def _stage_F(stage: Mapping[str, Any], t: Mapping[str, Any]) -> list[dict[str, Any]]:
    timing = t["time_and_encoder"]
    calibration = t["calibration"]
    nozzle = t["nozzle_registration"]
    deadline = t["actuation_deadline"]
    marker = t["dry_marker"]
    safety = t["safety"]
    chemical = t["chemical"]
    evidence_roles = _get(stage, "evidence_roles")
    evidence_artifact_ids = _get(stage, "evidence_artifact_ids")
    if isinstance(evidence_roles, Mapping):
        unexpected_roles = sorted(
            set(evidence_roles) - set(t["required_evidence_roles"])
        )
        evidence_role_checks = [
            check("evidence_roles.unexpected", unexpected_roles, "set_eq", [])
        ]
    else:
        evidence_role_checks = [
            check("evidence_roles.mapping", evidence_roles, "nonempty")
        ]
    for role in t["required_evidence_roles"]:
        artifact_id = (
            evidence_roles.get(role, MISSING)
            if isinstance(evidence_roles, Mapping)
            else MISSING
        )
        evidence_role_checks.extend(
            [
                check(f"evidence_roles.{role}.artifact_id", artifact_id, "nonempty"),
                check(
                    f"evidence_roles.{role}.referenced",
                    artifact_id,
                    "in",
                    evidence_artifact_ids
                    if isinstance(evidence_artifact_ids, list)
                    else [],
                ),
            ]
        )

    camera_offset = _get(stage, "nozzle_registration.measured_camera_to_nozzle_offset_mm")
    valve_latency_ms = _get(stage, "nozzle_registration.measured_valve_onset_latency_ms")
    speed_mm_s = _get(stage, "nozzle_registration.formula_verification.speed_mm_s")
    capture_encoder_mm = _get(stage, "nozzle_registration.formula_verification.capture_encoder_mm")
    declared_command_mm = _get(stage, "nozzle_registration.formula_verification.command_encoder_mm")
    expected_command_mm: Any = MISSING
    if not any(
        _unmeasured(value)
        for value in (camera_offset, valve_latency_ms, speed_mm_s, capture_encoder_mm)
    ):
        try:
            expected_command_mm = (
                _number(capture_encoder_mm)
                + _number(camera_offset)
                - _number(speed_mm_s) * _number(valve_latency_ms) / 1000.0
            )
        except (TypeError, ValueError):
            expected_command_mm = MISSING

    footprint_radius = _get(stage, "nozzle_registration.measured_footprint_radius_mm")
    registration_p95 = _get(stage, "nozzle_registration.p95_total_registration_error_mm")
    declared_no_fire_distance = _get(stage, "nozzle_registration.frozen_no_fire_distance_mm")
    expected_no_fire_distance: Any = MISSING
    if not any(_unmeasured(value) for value in (footprint_radius, registration_p95)):
        try:
            expected_no_fire_distance = _number(footprint_radius) + _number(
                registration_p95
            )
        except (TypeError, ValueError):
            expected_no_fire_distance = MISSING

    fault_rows = _get(stage, "safety.fault_injection_results")
    expected_faults = list(safety["forced_no_fire_faults"])

    def fault_checks(row: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            check("injected", _get(row, "injected"), "eq", safety["each_fault_injected"]),
            check("no_fire_observed", _get(row, "no_fire_observed"), "eq", safety["each_fault_no_fire_observed"]),
            check("valve_enable", _get(row, "valve_enable"), "eq", safety["each_fault_valve_enable"]),
        ]

    def deadline_case_checks(
        case_name: str, expected_feasible: bool
    ) -> list[dict[str, Any]]:
        prefix = f"actuation_deadline.{case_name}"
        case = _get(stage, prefix)
        speed = _get(case, "speed_mm_s")
        distance = _get(case, "remaining_encoder_distance_mm")
        inference = _get(case, "worst_case_inference_latency_ms")
        transfer = _get(case, "worst_case_result_transfer_latency_ms")
        controller = _get(case, "worst_case_controller_latency_ms")
        case_valve = _get(case, "measured_valve_onset_latency_ms")
        required: Any = MISSING
        available: Any = MISSING
        inputs = (speed, distance, inference, transfer, controller, case_valve)
        if not any(_unmeasured(value) for value in inputs):
            try:
                required = (
                    _number(inference)
                    + _number(transfer)
                    + _number(controller)
                    + _number(case_valve)
                )
                available = _number(distance) / _number(speed) * 1000.0
            except (TypeError, ValueError, ZeroDivisionError):
                required = MISSING
                available = MISSING
        computed_feasible: Any = MISSING
        if not _unmeasured(required) and not _unmeasured(available):
            computed_feasible = _number(required) <= _number(available)
        return [
            check(f"{case_name}.speed_mm_s", speed, "gt", 0.0),
            check(
                f"{case_name}.remaining_encoder_distance_mm",
                distance,
                "ge",
                0.0,
            ),
            check(
                f"{case_name}.worst_case_inference_latency_ms",
                inference,
                "ge",
                0.0,
            ),
            check(
                f"{case_name}.worst_case_result_transfer_latency_ms",
                transfer,
                "ge",
                0.0,
            ),
            check(
                f"{case_name}.worst_case_controller_latency_ms",
                controller,
                "ge",
                0.0,
            ),
            check(
                f"{case_name}.measured_valve_onset_latency_ms",
                case_valve,
                "eq",
                valve_latency_ms,
            ),
            check(
                f"{case_name}.calculated_required_latency_ms",
                _get(case, "calculated_required_latency_ms"),
                "eq",
                required,
            ),
            check(
                f"{case_name}.calculated_available_time_ms",
                _get(case, "calculated_available_time_ms"),
                "eq",
                available,
            ),
            check(
                f"{case_name}.computed_deadline_feasible",
                computed_feasible,
                "eq",
                expected_feasible,
            ),
            check(
                f"{case_name}.declared_deadline_feasible",
                _get(case, "deadline_feasible"),
                "eq",
                computed_feasible,
            ),
        ]

    return [
        gate("F.explicit_measurement_evidence_roles", evidence_role_checks),
        gate(
            "F.shared_clock_encoder_and_time_alignment",
            [
                check("shared_real_time_controller_clock", _get(stage, "time_and_encoder.shared_real_time_controller_clock"), "eq", timing["shared_real_time_controller_clock_required"]),
                check("trigger_encoder_same_hardware_event", _get(stage, "time_and_encoder.trigger_encoder_same_hardware_event"), "eq", timing["trigger_encoder_same_hardware_event_required"]),
                check("host_arrival_timestamp_used_for_control", _get(stage, "time_and_encoder.host_arrival_timestamp_used_for_control"), "eq", timing["host_arrival_timestamp_for_control"]),
                check("encoder_resolution_mm_per_count", _get(stage, "time_and_encoder.encoder_resolution_mm_per_count"), "le", timing["encoder_resolution_maximum_mm_per_count"]),
                check("encoder_scale_error_mm_per_m", _get(stage, "time_and_encoder.encoder_scale_error_mm_per_m"), "le", timing["encoder_scale_error_maximum_mm_per_m"]),
                check("trigger_encoder_delta_p95_us", _get(stage, "time_and_encoder.trigger_encoder_delta_p95_us"), "le", timing["trigger_encoder_delta_p95_maximum_us"]),
                check("trigger_encoder_delta_max_us", _get(stage, "time_and_encoder.trigger_encoder_delta_max_us"), "le", timing["trigger_encoder_delta_maximum_us"]),
                check("encoder_stale_no_fire_after_ms", _get(stage, "time_and_encoder.encoder_stale_no_fire_after_ms"), "le", timing["encoder_stale_no_fire_maximum_ms"]),
            ],
        ),
        gate(
            "F.homography_and_daily_registration",
            [
                check("installed_optical_state_frozen", _get(stage, "calibration.installed_optical_state_frozen"), "eq", calibration["installed_optical_state_frozen_required"]),
                check("daily_fiducial_check_id", _get(stage, "calibration.daily_fiducial_check_id"), "nonempty"),
                check("ground_homography_residual_p95_mm", _get(stage, "calibration.ground_homography_residual_p95_mm"), "le", calibration["ground_homography_residual_p95_maximum_mm"]),
                check("ground_homography_residual_max_mm", _get(stage, "calibration.ground_homography_residual_max_mm"), "le", calibration["ground_homography_residual_maximum_mm"]),
                check("daily_registration_drift_mm", _get(stage, "calibration.daily_registration_drift_mm"), "le", calibration["daily_registration_drift_maximum_mm"]),
            ],
        ),
        gate(
            "F.measured_nozzle_latency_footprint_and_formulae",
            [
                check("offset_measurement_method", _get(stage, "nozzle_registration.offset_measurement_method"), "nonempty"),
                check("offset_physically_measured", _get(stage, "nozzle_registration.offset_physically_measured"), "eq", nozzle["camera_to_nozzle_offset_must_be_physically_measured"]),
                check("offset_CAD_assumed", _get(stage, "nozzle_registration.offset_CAD_assumed"), "eq", nozzle["camera_to_nozzle_offset_CAD_assumed"]),
                check("offset_coordinate_convention", _get(stage, "nozzle_registration.offset_coordinate_convention"), "eq", nozzle["offset_coordinate_convention"]),
                check("measured_camera_to_nozzle_offset_mm", camera_offset, "finite_number"),
                check("latency_footprint_measurement_method", _get(stage, "nozzle_registration.latency_footprint_measurement_method"), "in", nozzle["allowed_latency_footprint_methods"]),
                check("measured_valve_onset_latency_ms", valve_latency_ms, "gt", nozzle["valve_onset_latency_minimum_ms_exclusive"]),
                check("measured_footprint_radius_mm", footprint_radius, "gt", nozzle["footprint_radius_minimum_mm_exclusive"]),
                check("p95_total_registration_error_mm", registration_p95, "ge", 0.0),
                check("command_encoder_mm_formula", declared_command_mm, "eq", expected_command_mm),
                check("frozen_no_fire_distance_mm_formula", declared_no_fire_distance, "eq", expected_no_fire_distance),
            ],
        ),
        gate(
            "F.actuation_deadline_and_forced_abort",
            [
                check("actuation_medium", _get(stage, "actuation_deadline.actuation_medium"), "eq", deadline["dry_marker_medium"]),
                *deadline_case_checks("feasible_case", True),
                check("feasible_case.dry_marker_command_emitted", _get(stage, "actuation_deadline.feasible_case.dry_marker_command_emitted"), "eq", deadline["feasible_case_must_emit_dry_marker_command"]),
                *deadline_case_checks("forced_missed_deadline", False),
                check("forced_missed_deadline.abort_observed", _get(stage, "actuation_deadline.forced_missed_deadline.abort_observed"), "eq", deadline["forced_missed_deadline_must_abort"]),
                check("forced_missed_deadline.valve_enable", _get(stage, "actuation_deadline.forced_missed_deadline.valve_enable"), "eq", deadline["forced_missed_deadline_valve_enable"]),
                check("forced_missed_deadline.fire_command", _get(stage, "actuation_deadline.forced_missed_deadline.fire_command"), "eq", deadline["forced_missed_deadline_fire_command"]),
            ],
        ),
        gate(
            "F.dry_marker_end_to_end_error",
            [
                check("evaluated_marks", _get(stage, "dry_marker.evaluated_marks"), "gt", marker["evaluated_marks_minimum_exclusive"]),
                check("end_to_end_error_p95_mm", _get(stage, "dry_marker.end_to_end_error_p95_mm"), "le", marker["end_to_end_error_p95_maximum_mm"]),
                check("end_to_end_error_max_mm", _get(stage, "dry_marker.end_to_end_error_max_mm"), "le", marker["end_to_end_error_maximum_mm"]),
            ],
        ),
        gate(
            "F.hardware_estop_watchdog_and_power_safety",
            [
                check("SELV_LPS_power_verified", _get(stage, "safety.SELV_LPS_power_verified"), "eq", safety["SELV_LPS_power_verified"]),
                check("fused_camera_light_controller_branches_verified", _get(stage, "safety.fused_camera_light_controller_branches_verified"), "eq", safety["fused_camera_light_controller_branches_verified"]),
                check("emergency_stop.tested", _get(stage, "safety.emergency_stop.tested"), "eq", safety["emergency_stop_tested"]),
                check("emergency_stop.strobe_enable", _get(stage, "safety.emergency_stop.strobe_enable"), "eq", safety["emergency_stop_strobe_enable"]),
                check("emergency_stop.valve_enable", _get(stage, "safety.emergency_stop.valve_enable"), "eq", safety["emergency_stop_valve_enable"]),
                check("watchdog.tested", _get(stage, "safety.watchdog.tested"), "eq", safety["watchdog_tested"]),
                check("watchdog.default_no_fire", _get(stage, "safety.watchdog.default_no_fire"), "eq", safety["watchdog_default_no_fire"]),
                check("watchdog.valve_enable", _get(stage, "safety.watchdog.valve_enable"), "eq", safety["watchdog_valve_enable"]),
            ],
        ),
        _collection_gate(
            "F.each_frozen_fault_forces_no_fire",
            fault_rows,
            expected_faults,
            lambda row: _get(row, "fault"),
            fault_checks,
        ),
        gate(
            "F.chemical_enable_remains_unsupported_and_disabled",
            [
                check("chemical_enable", _get(stage, "chemical.chemical_enable"), "eq", chemical["chemical_enable"]),
                check("chemical_enable_hardware_line_verified_disabled", _get(stage, "chemical.chemical_enable_hardware_line_verified_disabled"), "eq", chemical["chemical_enable_hardware_line_verified_disabled"]),
                check("deposition_acceptance_status", _get(stage, "chemical.deposition_acceptance_status"), "eq", chemical["deposition_acceptance_status"]),
                check("crop_injury_acceptance_status", _get(stage, "chemical.crop_injury_acceptance_status"), "eq", chemical["crop_injury_acceptance_status"]),
            ],
        ),
    ]


STAGE_EVALUATORS = {
    "A_procurement_and_identity": _stage_A,
    "B_transport_trigger_and_thermal": _stage_B,
    "C_optics_and_window": _stage_C,
    "D_light_hood_and_polarization": _stage_D,
    "E_motion_tracking_and_compute": _stage_E,
    "F_registration_and_safe_actuation": _stage_F,
}


def evaluate(
    contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
    root: Path = PROJECT_ROOT,
    receipt_path: Path | None = None,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    contract_identity = validate_contract_identity(contract, contract_path)
    receipt_dir = receipt_path.resolve().parent if receipt_path else root.resolve()
    receipt_validation = _receipt_validation(contract, receipt)
    source_integrity = _source_integrity(contract, receipt, root.resolve())
    stages = _get(receipt, "stages")
    stage_results: dict[str, Any] = {}
    for stage_name in contract["decision_policy"]["evaluated_stages"]:
        stage = stages.get(stage_name, MISSING) if isinstance(stages, Mapping) else MISSING
        measurement_status = _get(stage, "measurement_status")
        if measurement_status == "not_measured" or _unmeasured(measurement_status):
            status_check = check(
                f"{stage_name}.measurement_status",
                measurement_status,
                "eq",
                "measured",
            )
            stage_results[stage_name] = {
                "status": NOT_MEASURED,
                "measurement_status": _json_value(measurement_status),
                "gates": [gate(f"{stage_name}.measurement_presence", [status_check])],
            }
            continue
        if measurement_status != "measured" or not isinstance(stage, Mapping):
            status_check = check(
                f"{stage_name}.measurement_status",
                measurement_status,
                "eq",
                "measured",
            )
            stage_results[stage_name] = {
                "status": FAIL,
                "measurement_status": _json_value(measurement_status),
                "gates": [gate(f"{stage_name}.measurement_presence", [status_check])],
            }
            continue
        gates = [
            gate(
                f"{stage_name}.measurement_presence",
                [check(f"{stage_name}.measurement_status", measurement_status, "eq", "measured")],
            ),
            _stage_evidence_gate(stage_name, stage, receipt, receipt_dir),
            *STAGE_EVALUATORS[stage_name](
                stage, contract["thresholds"][stage_name]
            ),
        ]
        stage_results[stage_name] = {
            "status": combine_status([item["status"] for item in gates]),
            "measurement_status": measurement_status,
            "gates": gates,
        }

    collection_stage_names = contract["decision_policy"][
        "controlled_data_collection_stages"
    ]
    dry_marker_stage_names = contract["decision_policy"][
        "dry_marker_readiness_stages"
    ]
    collection_gate_outcome = combine_status(
        [stage_results[name]["status"] for name in collection_stage_names]
    )
    dry_marker_gate_outcome = combine_status(
        [stage_results[name]["status"] for name in dry_marker_stage_names]
    )
    collection_acceptance_outcome = combine_status(
        [
            receipt_validation["status"],
            source_integrity["status"],
            collection_gate_outcome,
        ]
    )
    dry_marker_acceptance_outcome = combine_status(
        [
            receipt_validation["status"],
            source_integrity["status"],
            dry_marker_gate_outcome,
        ]
    )
    evidence_kind = _get(receipt, "evidence_kind")
    data_collection_allowed = (
        collection_acceptance_outcome == PASS
        and evidence_kind == "physical_bench"
        and _get(receipt, "deployment_evidence") is True
        and _get(receipt, "synthetic_fixture") is False
    )
    dry_marker_ready = (
        dry_marker_acceptance_outcome == PASS
        and evidence_kind == "physical_bench"
        and _get(receipt, "deployment_evidence") is True
        and _get(receipt, "synthetic_fixture") is False
    )
    if evidence_kind == "synthetic_fixture":
        collection_code = "SYNTHETIC_NOT_DEPLOYMENT_EVIDENCE"
        collection_reason = (
            "Synthetic fixture can prove evaluator logic only; controlled data "
            "collection remains blocked."
        )
    elif data_collection_allowed:
        collection_code = "GO_CONTROLLED_DATA_COLLECTION"
        collection_reason = "Physical receipt and every frozen A-E gate passed."
    elif collection_acceptance_outcome == NOT_MEASURED:
        collection_code = "NO_GO_NOT_MEASURED"
        collection_reason = "At least one required receipt, source, artifact, or A-E value is unmeasured."
    else:
        collection_code = "NO_GO_FAILED"
        collection_reason = "At least one receipt, integrity, artifact, or A-E gate failed."

    if evidence_kind == "synthetic_fixture":
        dry_marker_code = "SYNTHETIC_NOT_DRY_MARKER_EVIDENCE"
        dry_marker_reason = (
            "Synthetic fixture can prove Stage F logic only; dry-marker "
            "actuation remains blocked."
        )
    elif dry_marker_ready:
        dry_marker_code = "READY_SAFE_DRY_MARKER"
        dry_marker_reason = "Physical receipt and every frozen A-F gate passed."
    elif dry_marker_acceptance_outcome == NOT_MEASURED:
        dry_marker_code = "NOT_READY_DRY_MARKER_NOT_MEASURED"
        dry_marker_reason = (
            "At least one required receipt, source, artifact, or A-F value is "
            "unmeasured."
        )
    else:
        dry_marker_code = "NOT_READY_DRY_MARKER_FAILED"
        dry_marker_reason = (
            "At least one receipt, integrity, artifact, or A-F gate failed."
        )

    receipt_digest = None
    if receipt_path is not None and receipt_path.is_file():
        receipt_digest = sha256_file(receipt_path)
    return {
        "schema_version": 1,
        "contract_id": contract["contract_id"],
        "contract_identity": contract_identity,
        "implementation": {
            "script": str(Path(__file__).resolve().relative_to(PROJECT_ROOT)),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "receipt_id": _json_value(_get(receipt, "receipt_id")),
        "receipt_sha256": receipt_digest,
        "evidence_kind": _json_value(evidence_kind),
        "receipt_validation": receipt_validation,
        "frozen_v2_source_integrity": source_integrity,
        "stage_results": stage_results,
        "gate_outcome": collection_gate_outcome,
        "acceptance_outcome": collection_acceptance_outcome,
        "collection_gate_outcome_A_E": collection_gate_outcome,
        "collection_acceptance_outcome_A_E": collection_acceptance_outcome,
        "dry_marker_gate_outcome_A_F": dry_marker_gate_outcome,
        "dry_marker_acceptance_outcome_A_F": dry_marker_acceptance_outcome,
        "decision": {
            "code": collection_code,
            "reason": collection_reason,
            "controlled_data_collection_allowed": data_collection_allowed,
            "deployment_evidence_eligible": data_collection_allowed,
            "stage_F_evaluated": True,
            "dry_marker_readiness": {
                "code": dry_marker_code,
                "reason": dry_marker_reason,
                "ready": dry_marker_ready,
                "deployment_evidence_eligible": dry_marker_ready,
            },
            "chemical_fire_allowed": False,
            "chemical_fire_blocker": contract["decision_policy"][
                "chemical_fire_blocker"
            ],
        },
        "warning": (
            "Physical A-E govern controlled RGB data collection; physical A-F "
            "separately govern safe dry-marker readiness. Frozen V2 has no "
            "quantitative deposition or crop-injury acceptance thresholds, so "
            "chemical fire remains unsupported and disabled."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--decision-target",
        choices=("controlled-data-collection", "dry-marker"),
        default="controlled-data-collection",
        help="Select which independent readiness decision controls the exit code.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    contract_path = args.contract.resolve()
    receipt_path = args.receipt.resolve()
    output_path = None
    try:
        if args.output:
            output_path = validate_output_path(
                args.output,
                {
                    "receipt": receipt_path,
                    "selected contract": contract_path,
                    "default contract": DEFAULT_CONTRACT,
                },
            )
        contract = load_yaml_mapping(contract_path)
        receipt = load_yaml_mapping(receipt_path)
        result = evaluate(
            contract,
            receipt,
            PROJECT_ROOT,
            receipt_path,
            contract_path,
        )
        output = render(result)
        if output_path:
            atomic_write_text(output_path, output)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(output, end="")
    ready = result["decision"]["controlled_data_collection_allowed"]
    if args.decision_target == "dry-marker":
        ready = result["decision"]["dry_marker_readiness"]["ready"]
    raise SystemExit(0 if ready else 2)


if __name__ == "__main__":
    main()
