#!/usr/bin/env python3
"""Fail-closed audit and deterministic split tool for capture_manifest_v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

import yaml
from PIL import Image, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/data/spot_spray_capture_audit_v1.yaml"
EXIT_READY = 0
EXIT_INVALID = 2
EXIT_NOT_READY = 3
FROZEN_POLICY_FILE_SHA256 = "cbebfea95f8b39dcd2d3189c874e7910f9fdb6d6e58b4e905eaabadc36e667f4"
FROZEN_POLICY_SEMANTIC_SHA256 = "c31ab07951b3a1919fca885917f405c9084cd42bc85740599750db3460e6c46d"
FROZEN_SCHEMA_FILE_SHA256 = "d6a3a8c31a3fc762a9f71262074e724864fc265643c9a945f4d2ee742d125745"
FROZEN_SCHEMA_SEMANTIC_SHA256 = "8928bbcca4dbd48c602a9e262893d4a8d0239374c5f88e848886d35c328900cb"
RIG_ACCEPTANCE_STAGES_A_E = (
    "A_procurement_and_identity",
    "B_transport_trigger_and_thermal",
    "C_optics_and_window",
    "D_light_hood_and_polarization",
    "E_motion_tracking_and_compute",
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json(token: str) -> None:
    raise ValueError(f"Non-finite JSON number is forbidden: {token}")


def _canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
    rendered = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that forbids duplicate keys at every mapping depth."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ValueError("YAML mapping keys must be hashable scalars") from error
        if duplicate:
            raise ValueError(f"Duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(
        source.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_json,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Expected one JSON object: {source}")
    return payload


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = yaml.load(
        source.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Expected one YAML mapping: {source}")
    return payload


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    raise ValueError(f"Unsupported JSON Schema type in frozen schema: {expected!r}")


def validate_json_schema(
    value: Any, schema: Mapping[str, Any], path: str = "$"
) -> list[dict[str, str]]:
    """Validate the frozen schema subset without an undeclared runtime dependency."""

    findings: list[dict[str, str]] = []
    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not isinstance(expected_types, list) or not all(
            isinstance(item, str) for item in expected_types
        ):
            raise ValueError(f"Invalid type declaration in schema at {path}")
        if not any(_json_type_matches(value, item) for item in expected_types):
            findings.append(
                issue(
                    "schema.type",
                    path,
                    f"Expected {' or '.join(expected_types)}, got {type(value).__name__}",
                )
            )
            return findings

    if "const" in schema and value != schema["const"]:
        findings.append(
            issue("schema.const", path, f"Expected frozen value {schema['const']!r}")
        )
    if "enum" in schema and value not in schema["enum"]:
        findings.append(
            issue("schema.enum", path, f"Expected one of {schema['enum']!r}")
        )

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError(f"Invalid object declaration in schema at {path}")
        for name in required:
            if name not in value:
                findings.append(
                    issue(
                        "schema.required",
                        f"{path}.{name}",
                        f"Required property {name!r} is missing",
                    )
                )
        if schema.get("additionalProperties") is False:
            for name in sorted(set(value) - set(properties)):
                findings.append(
                    issue(
                        "schema.additional_property",
                        f"{path}.{name}",
                        f"Unexpected property {name!r}",
                    )
                )
        for name in sorted(set(value) & set(properties)):
            child = properties[name]
            if not isinstance(child, dict):
                raise ValueError(f"Invalid property schema at {path}.{name}")
            findings.extend(validate_json_schema(value[name], child, f"{path}.{name}"))

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if minimum_items is not None and len(value) < int(minimum_items):
            findings.append(
                issue(
                    "schema.min_items",
                    path,
                    f"Expected at least {minimum_items} items, got {len(value)}",
                )
            )
        if maximum_items is not None and len(value) > int(maximum_items):
            findings.append(
                issue(
                    "schema.max_items",
                    path,
                    f"Expected at most {maximum_items} items, got {len(value)}",
                )
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            if not isinstance(item_schema, dict):
                raise ValueError(f"Invalid items schema at {path}")
            for index, item in enumerate(value):
                findings.extend(validate_json_schema(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            findings.append(issue("schema.min_length", path, "String is too short"))
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            findings.append(
                issue("schema.pattern", path, f"String does not match {schema['pattern']!r}")
            )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if "minimum" in schema and numeric < float(schema["minimum"]):
            findings.append(
                issue("schema.minimum", path, f"Value is below {schema['minimum']}")
            )
        if "maximum" in schema and numeric > float(schema["maximum"]):
            findings.append(
                issue("schema.maximum", path, f"Value is above {schema['maximum']}")
            )
        if "exclusiveMinimum" in schema and numeric <= float(schema["exclusiveMinimum"]):
            findings.append(
                issue(
                    "schema.exclusive_minimum",
                    path,
                    f"Value must be greater than {schema['exclusiveMinimum']}",
                )
            )
        if "exclusiveMaximum" in schema and numeric >= float(schema["exclusiveMaximum"]):
            findings.append(
                issue(
                    "schema.exclusive_maximum",
                    path,
                    f"Value must be less than {schema['exclusiveMaximum']}",
                )
            )
    return findings


def resolve_repo_path(repo_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else repo_root / path).resolve()


def validate_schema_contract(schema: Mapping[str, Any]) -> None:
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("Capture schema must remain JSON Schema Draft 2020-12")
    if (
        schema.get("$id")
        != "https://tarim-projesi.local/schema/spot_spray_capture_manifest_v1.schema.json"
    ):
        raise ValueError("Capture schema $id drifted from the frozen v1 identity")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Capture schema properties must be a mapping")
    schema_version = properties.get("schema_version")
    if not isinstance(schema_version, dict) or schema_version.get("const") != "capture_manifest_v1":
        raise ValueError("Capture schema must freeze capture_manifest_v1")
    observed = _canonical_mapping_sha256(schema)
    if observed != FROZEN_SCHEMA_SEMANTIC_SHA256:
        raise ValueError(
            "Capture schema semantics drifted from the frozen v1 contract: "
            f"expected {FROZEN_SCHEMA_SEMANTIC_SHA256}, observed {observed}"
        )


def validate_policy(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != 1:
        raise ValueError("Audit policy schema_version must equal 1")
    if config.get("manifest_contract") != "capture_manifest_v1":
        raise ValueError("Audit policy manifest_contract must equal capture_manifest_v1")
    if config.get("manifest_schema") != "configs/data/spot_spray_capture_manifest_v1.schema.json":
        raise ValueError("Audit policy manifest_schema path must remain frozen")
    scope = config.get("evidence_scope")
    if not isinstance(scope, dict) or scope.get("real") != "real_target_rig":
        raise ValueError("Audit policy must freeze real_target_rig evidence scope")
    if scope.get("synthetic_fixture") != "synthetic_fixture":
        raise ValueError("Audit policy must freeze synthetic_fixture evidence scope")
    if scope.get("synthetic_fixture_can_be_ready") is not False:
        raise ValueError("Synthetic fixtures must be permanently barred from READY")
    image_files = config.get("image_files")
    if not isinstance(image_files, dict) or image_files.get("read_pixels") is not False:
        raise ValueError("The v1 audit may verify image containers but may not inspect scene pixels")
    if (
        image_files.get("require_exists") is not True
        or image_files.get("require_nonempty") is not True
    ):
        raise ValueError("The v1 audit must require existing, non-empty image files")
    for flag in (
        "require_sha256_for_real",
        "verify_declared_sha256",
        "require_decodable_content_for_real",
        "verify_native_dimensions_for_real",
    ):
        if image_files.get(flag) is not True:
            raise ValueError(f"Image integrity policy {flag} must remain true")
    rig_acceptance = config.get("rig_acceptance")
    if not isinstance(rig_acceptance, dict):
        raise ValueError("Audit policy rig_acceptance must be a mapping")
    if rig_acceptance.get("result_path_base") != "data_root":
        raise ValueError("Rig-acceptance results must be data-root-relative")
    if rig_acceptance.get("contract_id") != "controlled_spot_spray_rig_acceptance_v1":
        raise ValueError("Unexpected rig-acceptance contract")
    frozen_rig_source_identity = {
        "contract_path": "configs/deploy/spot_spray_rig_acceptance_v1.yaml",
        "contract_identity_id": "controlled_spot_spray_rig_acceptance_v1_exact_default",
        "contract_identity_algorithm": "sha256_exact_bytes_plus_canonical_json_v1",
        "contract_exact_byte_sha256": "a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c",
        "contract_canonical_policy_sha256": "c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21",
        "evaluator_path": "scripts/evaluate_spot_spray_rig_acceptance_v1.py",
        "evaluator_sha256": "596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2",
    }
    for name, expected in frozen_rig_source_identity.items():
        if rig_acceptance.get(name) != expected:
            raise ValueError(f"Rig-acceptance source identity {name} drifted")
    if rig_acceptance.get("accepted_evidence_kind") != "physical_bench":
        raise ValueError("Only physical_bench rig acceptance may unlock real capture")
    if rig_acceptance.get("required_collection_outcome") != "PASS":
        raise ValueError("Rig-acceptance A-E collection outcome must remain PASS")
    if rig_acceptance.get("required_validation_status") != "PASS":
        raise ValueError("Rig-acceptance validation status must remain PASS")
    if rig_acceptance.get("controlled_data_collection_allowed") is not True:
        raise ValueError("Physical acceptance must explicitly allow controlled collection")
    if rig_acceptance.get("deployment_evidence_eligible") is not True:
        raise ValueError("Physical acceptance must be eligible deployment evidence")
    if rig_acceptance.get("required_stages_A_E") != list(RIG_ACCEPTANCE_STAGES_A_E):
        raise ValueError("Rig-acceptance stages A-E must remain frozen")
    provenance = config.get("real_capture_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Audit policy real_capture_provenance must be a mapping")
    expected_real_fields = [
        "image_sha256",
        "camera_frame_counter",
        "camera_timestamp_ns",
        "white_balance",
        "native_width_px",
        "native_height_px",
        "pixel_format",
        "camera_id",
        "rig_id",
        "capture_profile_id",
        "strobe_settings",
    ]
    if provenance.get("required_frame_fields") != expected_real_fields:
        raise ValueError("Real capture metadata fields must remain frozen")
    for flag in (
        "require_manual_white_balance",
        "require_strobe_profile_binding",
        "require_strict_camera_counter_order",
        "require_strict_camera_timestamp_order",
        "require_contiguous_video_frames",
        "require_frame_index_counter_delta_match",
        "freeze_profile_bindings",
        "freeze_video_camera_and_rig_identity",
    ):
        if provenance.get(flag) is not True:
            raise ValueError(f"Real provenance policy {flag} must remain true")
    split = config.get("split")
    if not isinstance(split, dict):
        raise ValueError("Audit policy split must be a mapping")
    roles = split.get("roles")
    if roles != ["train", "validation", "test"]:
        raise ValueError("Split roles must be frozen as train/validation/test")
    fractions = split.get("target_fractions")
    frozen_fractions = {"train": 0.60, "validation": 0.20, "test": 0.20}
    if fractions != frozen_fractions:
        raise ValueError("Split fractions must remain exactly 0.60/0.20/0.20")
    if split.get("deterministic_seed") != "spot_spray_capture_manifest_v1":
        raise ValueError("Deterministic split seed must remain spot_spray_capture_manifest_v1")
    if split.get("role_exclusive_levels") != ["field", "session", "video_track"]:
        raise ValueError("Role exclusivity must remain field/session/video_track")
    if split.get("unassigned_role") != "unassigned":
        raise ValueError("The unfrozen split role must remain unassigned")
    if split.get("require_every_role_for_ready") is not True:
        raise ValueError("READY must require every train/validation/test role")
    if split.get("adjacent_frame_max_gap") != 1:
        raise ValueError("Adjacent-frame gap must remain exactly 1")
    readiness = config.get("readiness")
    if not isinstance(readiness, dict):
        raise ValueError("Audit policy readiness must be a mapping")
    if readiness.get("minimum_fields") != 3:
        raise ValueError("Readiness minimum_fields must remain exactly 3")
    if readiness.get("minimum_sessions") != 4:
        raise ValueError("Readiness minimum_sessions must remain exactly 4")
    if readiness.get("ready_status") != "READY" or readiness.get("not_ready_status") != "NOT_READY":
        raise ValueError("Readiness status strings must remain READY/NOT_READY")
    annotation = config.get("annotation")
    if not isinstance(annotation, dict):
        raise ValueError("Audit policy annotation must be a mapping")
    if annotation.get("classes") != ["crop", "weed", "partial_unknown"]:
        raise ValueError("Annotation classes must remain crop/weed/partial_unknown")
    if annotation.get("minimum_normalized_polygon_area") != 1.0e-8:
        raise ValueError("Minimum normalized polygon area must remain exactly 1e-8")
    if annotation.get("complete_visibility_threshold") != 0.999999:
        raise ValueError("Complete visibility threshold must remain exactly 0.999999")
    if annotation.get("stem_or_keypoint_labels_allowed") is not False:
        raise ValueError("Stem/keypoint labels are deferred in v1")
    for flag in (
        "partial_unknown_requires_partial",
        "partial_unknown_canopy_span_must_be_null",
        "complete_crop_or_weed_requires_canopy_span",
    ):
        if annotation.get(flag) is not True:
            raise ValueError(f"Annotation policy {flag} must remain true")
    if readiness.get("require_frozen_splits") is not True:
        raise ValueError("Readiness must require frozen splits")
    observed = _canonical_mapping_sha256(config)
    if observed != FROZEN_POLICY_SEMANTIC_SHA256:
        raise ValueError(
            "Capture audit policy semantics drifted from the frozen v1 contract: "
            f"expected {FROZEN_POLICY_SEMANTIC_SHA256}, observed {observed}"
        )


def validate_rig_source_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the exact local producer sources trusted by the capture consumer."""

    policy = config["rig_acceptance"]
    contract_path = resolve_repo_path(PROJECT_ROOT, str(policy["contract_path"]))
    evaluator_path = resolve_repo_path(PROJECT_ROOT, str(policy["evaluator_path"]))
    for label, path in (("contract", contract_path), ("evaluator", evaluator_path)):
        if not path.is_file():
            raise ValueError(f"Trusted rig-acceptance {label} is missing: {path}")
    contract_sha256 = sha256(contract_path)
    evaluator_sha256 = sha256(evaluator_path)
    if contract_sha256 != policy["contract_exact_byte_sha256"]:
        raise ValueError(
            "Trusted rig-acceptance contract exact-byte identity drifted: "
            f"expected {policy['contract_exact_byte_sha256']}, observed {contract_sha256}"
        )
    if evaluator_sha256 != policy["evaluator_sha256"]:
        raise ValueError(
            "Trusted rig-acceptance evaluator identity drifted: "
            f"expected {policy['evaluator_sha256']}, observed {evaluator_sha256}"
        )
    return {
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "evaluator_path": evaluator_path,
        "evaluator_sha256": evaluator_sha256,
    }


def deterministic_field_splits(
    field_ids: Iterable[str], split_policy: Mapping[str, Any]
) -> dict[str, str]:
    fields = sorted(set(field_ids))
    roles = [str(role) for role in split_policy["roles"]]
    fractions = {role: float(split_policy["target_fractions"][role]) for role in roles}
    seed = str(split_policy["deterministic_seed"])
    count = len(fields)
    allocations = {role: 0 for role in roles}
    remaining = count
    if count >= len(roles):
        allocations = {role: 1 for role in roles}
        remaining -= len(roles)
    raw = {role: fractions[role] * remaining for role in roles}
    for role in roles:
        base = math.floor(raw[role])
        allocations[role] += base
        remaining -= base
    remainder_order = sorted(
        roles,
        key=lambda role: (-(raw[role] - math.floor(raw[role])), roles.index(role)),
    )
    for role in remainder_order[:remaining]:
        allocations[role] += 1
    ordered_fields = sorted(
        fields,
        key=lambda field_id: (
            hashlib.sha256(f"{seed}\0{field_id}".encode("utf-8")).hexdigest(),
            field_id,
        ),
    )
    result: dict[str, str] = {}
    cursor = 0
    for role in roles:
        for field_id in ordered_fields[cursor : cursor + allocations[role]]:
            result[field_id] = role
        cursor += allocations[role]
    if cursor != count:
        raise AssertionError("Deterministic split allocation did not consume every field")
    return dict(sorted(result.items()))


def assign_deterministic_splits(
    manifest: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("A non-empty, schema-valid frames list is required")
    assigned = [frame.get("split") for frame in frames if isinstance(frame, dict)]
    if any(role != config["split"]["unassigned_role"] for role in assigned):
        raise ValueError("Deterministic assignment only accepts an entirely unassigned manifest")
    mapping = deterministic_field_splits(
        (str(frame["field_id"]) for frame in frames), config["split"]
    )
    output = copy.deepcopy(dict(manifest))
    for frame in output["frames"]:
        frame["split"] = mapping[str(frame["field_id"])]
    return output


def _polygon_area(points: Sequence[Sequence[float]]) -> float:
    return abs(
        sum(
            float(points[index][0]) * float(points[(index + 1) % len(points)][1])
            - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
            for index in range(len(points))
        )
    ) / 2.0


def _orientation(
    first: Sequence[float], second: Sequence[float], third: Sequence[float]
) -> float:
    return (float(second[0]) - float(first[0])) * (
        float(third[1]) - float(first[1])
    ) - (float(second[1]) - float(first[1])) * (
        float(third[0]) - float(first[0])
    )


def _on_segment(
    first: Sequence[float], point: Sequence[float], second: Sequence[float]
) -> bool:
    epsilon = 1.0e-12
    return (
        min(float(first[0]), float(second[0])) - epsilon
        <= float(point[0])
        <= max(float(first[0]), float(second[0])) + epsilon
        and min(float(first[1]), float(second[1])) - epsilon
        <= float(point[1])
        <= max(float(first[1]), float(second[1])) + epsilon
    )


def _segments_intersect(
    a: Sequence[float],
    b: Sequence[float],
    c: Sequence[float],
    d: Sequence[float],
) -> bool:
    epsilon = 1.0e-12
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > epsilon and o2 < -epsilon) or (o1 < -epsilon and o2 > epsilon)) and (
        (o3 > epsilon and o4 < -epsilon) or (o3 < -epsilon and o4 > epsilon)
    ):
        return True
    return any(
        abs(orientation) <= epsilon and _on_segment(start, point, end)
        for orientation, start, point, end in (
            (o1, a, c, b),
            (o2, a, d, b),
            (o3, c, a, d),
            (o4, c, b, d),
        )
    )


def _polygon_self_intersects(points: Sequence[Sequence[float]]) -> bool:
    edge_count = len(points)
    for first in range(edge_count):
        first_next = (first + 1) % edge_count
        for second in range(first + 1, edge_count):
            second_next = (second + 1) % edge_count
            if first == second or first_next == second or second_next == first:
                continue
            if first == 0 and second_next == 0:
                continue
            if _segments_intersect(
                points[first], points[first_next], points[second], points[second_next]
            ):
                return True
    return False


def _role_sets(
    frames: Sequence[Mapping[str, Any]],
    key,
    unassigned: str,
) -> dict[Any, set[str]]:
    roles: dict[Any, set[str]] = defaultdict(set)
    for frame in frames:
        role = str(frame["split"])
        if role != unassigned:
            roles[key(frame)].add(role)
    return roles


def _resolve_data_root_file(
    data_root: Path,
    recorded_path: str,
    json_path: str,
    code_prefix: str,
) -> tuple[Path | None, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    pure_path = PurePosixPath(recorded_path)
    if "\\" in recorded_path:
        findings.append(
            issue(
                f"{code_prefix}.non_posix_path",
                json_path,
                "Path must use data-root-relative POSIX syntax",
            )
        )
    elif pure_path.is_absolute():
        findings.append(
            issue(f"{code_prefix}.absolute_path", json_path, "Absolute paths are forbidden")
        )
    elif any(part in {"", ".", ".."} for part in recorded_path.split("/")):
        findings.append(
            issue(
                f"{code_prefix}.path_traversal",
                json_path,
                "Path may not contain empty, dot, or parent components",
            )
        )
    else:
        resolved = (data_root / Path(*pure_path.parts)).resolve()
        try:
            resolved.relative_to(data_root)
        except ValueError:
            findings.append(
                issue(
                    f"{code_prefix}.outside_data_root",
                    json_path,
                    "Resolved path escapes data_root",
                )
            )
        else:
            return resolved, findings
    return None, findings


def _acceptance_content_error(path: str, message: str) -> dict[str, str]:
    return issue("rig_acceptance.content_invalid", path, message)


def validate_rig_acceptance(
    manifest: Mapping[str, Any], data_root: Path, config: Mapping[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """Validate a portable, hash-pinned output from the frozen A-E evaluator."""

    errors: list[dict[str, str]] = []
    reasons: list[dict[str, str]] = []
    policy = config["rig_acceptance"]
    trusted_sources = validate_rig_source_contract(config)
    real_scope = manifest.get("evidence_scope") == config["evidence_scope"]["real"]
    summary: dict[str, Any] = {
        "present": False,
        "result_path": None,
        "resolved_result_path": None,
        "result_sha256_declared": None,
        "result_sha256_observed": None,
        "receipt_id": None,
        "receipt_sha256": None,
        "accepted_rig_id": None,
        "accepted_camera_id": None,
        "contract_identity_bound": False,
        "implementation_identity_bound": False,
        "trusted_contract_path": str(trusted_sources["contract_path"]),
        "trusted_contract_sha256": trusted_sources["contract_sha256"],
        "trusted_evaluator_path": str(trusted_sources["evaluator_path"]),
        "trusted_evaluator_sha256": trusted_sources["evaluator_sha256"],
        "collection_identity_bound": False,
        "evidence_kind": None,
        "collection_gate_outcome_A_E": None,
        "collection_acceptance_outcome_A_E": None,
        "controlled_data_collection_allowed": False,
        "deployment_evidence_eligible": False,
        "physical_collection_allowed": False,
        "status": "MISSING",
    }
    reference = manifest.get("rig_acceptance")
    if reference is None:
        if real_scope:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_missing",
                    "$.rig_acceptance",
                    "Real target-rig evidence requires a hash-pinned physical A-E evaluator result",
                )
            )
        return errors, reasons, summary

    summary["present"] = True
    result_path = str(reference["result_path"])
    declared_sha = str(reference["result_sha256"])
    summary["result_path"] = result_path
    summary["result_sha256_declared"] = declared_sha
    resolved, path_errors = _resolve_data_root_file(
        data_root,
        result_path,
        "$.rig_acceptance.result_path",
        "rig_acceptance",
    )
    errors.extend(path_errors)
    if resolved is None:
        summary["status"] = "INVALID"
        return errors, reasons, summary
    summary["resolved_result_path"] = str(resolved)
    if not resolved.is_file():
        summary["status"] = "NOT_READY"
        if real_scope:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_result_missing",
                    "$.rig_acceptance.result_path",
                    f"Rig-acceptance result is not present under data_root: {result_path}",
                )
            )
        return errors, reasons, summary

    observed_sha = sha256(resolved)
    summary["result_sha256_observed"] = observed_sha
    if observed_sha != declared_sha:
        errors.append(
            issue(
                "rig_acceptance.sha256_mismatch",
                "$.rig_acceptance.result_sha256",
                f"Declared {declared_sha}, observed {observed_sha}",
            )
        )
        summary["status"] = "INVALID"
        return errors, reasons, summary
    try:
        result = load_json_object(resolved)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(
            _acceptance_content_error(
                "$.rig_acceptance.result_path",
                f"Hash-matched evaluator result is not valid JSON: {error}",
            )
        )
        summary["status"] = "INVALID"
        return errors, reasons, summary

    def required_mapping(parent: Mapping[str, Any], name: str, path: str) -> Mapping[str, Any] | None:
        value = parent.get(name)
        if not isinstance(value, dict):
            errors.append(_acceptance_content_error(f"{path}.{name}", "Expected an object"))
            return None
        return value

    if result.get("schema_version") != 1:
        errors.append(
            _acceptance_content_error("$.rig_acceptance.result.schema_version", "Expected 1")
        )
    if result.get("contract_id") != policy["contract_id"]:
        errors.append(
            _acceptance_content_error(
                "$.rig_acceptance.result.contract_id",
                f"Expected {policy['contract_id']!r}",
            )
        )
    receipt_id = result.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        errors.append(
            _acceptance_content_error(
                "$.rig_acceptance.result.receipt_id", "Expected a non-empty receipt_id"
            )
        )
    receipt_sha = result.get("receipt_sha256")
    if not isinstance(receipt_sha, str) or re.fullmatch(r"[0-9a-f]{64}", receipt_sha) is None:
        errors.append(
            _acceptance_content_error(
                "$.rig_acceptance.result.receipt_sha256",
                "Expected the evaluated receipt SHA-256",
            )
        )
    evidence_kind = result.get("evidence_kind")
    if evidence_kind not in {"physical_bench", "synthetic_fixture"}:
        errors.append(
            _acceptance_content_error(
                "$.rig_acceptance.result.evidence_kind",
                "Expected physical_bench or synthetic_fixture",
            )
        )

    receipt_validation = required_mapping(
        result, "receipt_validation", "$.rig_acceptance.result"
    )
    source_integrity = required_mapping(
        result, "frozen_v2_source_integrity", "$.rig_acceptance.result"
    )
    contract_identity = required_mapping(
        result, "contract_identity", "$.rig_acceptance.result"
    )
    implementation = required_mapping(
        result, "implementation", "$.rig_acceptance.result"
    )
    decision = required_mapping(result, "decision", "$.rig_acceptance.result")
    stage_results = required_mapping(result, "stage_results", "$.rig_acceptance.result")
    valid_statuses = {"PASS", "FAIL", "NOT_MEASURED"}

    def identity_matches(
        container: Mapping[str, Any] | None,
        expected: Mapping[str, Any],
        path: str,
    ) -> bool:
        if container is None:
            return False
        matched = True
        for name, expected_value in expected.items():
            observed_value = container.get(name)
            exact = observed_value == expected_value
            if isinstance(expected_value, bool):
                exact = type(observed_value) is bool and observed_value is expected_value
            if not exact:
                matched = False
                errors.append(
                    issue(
                        "rig_acceptance.provenance_mismatch",
                        f"{path}.{name}",
                        f"Expected frozen provenance value {expected_value!r}, "
                        f"observed {observed_value!r}",
                    )
                )
        return matched

    contract_identity_bound = identity_matches(
        contract_identity,
        {
            "identity_id": policy["contract_identity_id"],
            "algorithm": policy["contract_identity_algorithm"],
            "default_contract_path": policy["contract_path"],
            "expected_exact_byte_sha256": policy["contract_exact_byte_sha256"],
            "observed_exact_byte_sha256": policy["contract_exact_byte_sha256"],
            "exact_bytes_verified": True,
            "expected_canonical_policy_sha256": policy[
                "contract_canonical_policy_sha256"
            ],
            "observed_canonical_policy_sha256": policy[
                "contract_canonical_policy_sha256"
            ],
            "canonical_policy_verified": True,
        },
        "$.rig_acceptance.result.contract_identity",
    )
    implementation_identity_bound = identity_matches(
        implementation,
        {
            "script": policy["evaluator_path"],
            "script_sha256": policy["evaluator_sha256"],
        },
        "$.rig_acceptance.result.implementation",
    )
    summary["contract_identity_bound"] = contract_identity_bound
    summary["implementation_identity_bound"] = implementation_identity_bound

    def checked_status(container: Mapping[str, Any] | None, path: str) -> str | None:
        if container is None:
            return None
        status = container.get("status")
        if status not in valid_statuses:
            errors.append(
                _acceptance_content_error(path, f"Expected one of {sorted(valid_statuses)!r}")
            )
            return None
        return str(status)

    receipt_status = checked_status(
        receipt_validation, "$.rig_acceptance.result.receipt_validation.status"
    )
    source_status = checked_status(
        source_integrity, "$.rig_acceptance.result.frozen_v2_source_integrity.status"
    )
    stage_statuses: dict[str, str | None] = {}
    stage_measurements: dict[str, str | None] = {}
    if stage_results is not None:
        for stage in policy["required_stages_A_E"]:
            stage_result = stage_results.get(stage)
            if not isinstance(stage_result, dict):
                errors.append(
                    _acceptance_content_error(
                        f"$.rig_acceptance.result.stage_results.{stage}",
                        "Required A-E stage result is missing",
                    )
                )
                stage_statuses[stage] = None
                stage_measurements[stage] = None
                continue
            measurement_status = stage_result.get("measurement_status")
            if measurement_status not in {None, "measured", "not_measured"}:
                errors.append(
                    _acceptance_content_error(
                        f"$.rig_acceptance.result.stage_results.{stage}.measurement_status",
                        "Expected measured, not_measured, or null",
                    )
                )
                stage_measurements[stage] = None
            elif measurement_status is None:
                stage_measurements[stage] = "not_measured"
            else:
                stage_measurements[stage] = str(measurement_status)
            stage_statuses[stage] = checked_status(
                stage_result,
                f"$.rig_acceptance.result.stage_results.{stage}.status",
            )

    def passed_check_actual(checks: Any, check_id: str) -> str | None:
        if not isinstance(checks, list):
            return None
        matches = [
            entry.get("actual")
            for entry in checks
            if isinstance(entry, dict)
            and entry.get("check_id") == check_id
            and entry.get("status") == "PASS"
        ]
        if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
            return None
        return matches[0]

    accepted_rig_id = passed_check_actual(
        None if receipt_validation is None else receipt_validation.get("checks"),
        "root.rig_unit_id",
    )
    accepted_camera_id: str | None = None
    stage_a = None if stage_results is None else stage_results.get(
        "A_procurement_and_identity"
    )
    if isinstance(stage_a, dict) and isinstance(stage_a.get("gates"), list):
        camera_matches: list[str] = []
        for stage_gate in stage_a["gates"]:
            if not isinstance(stage_gate, dict):
                continue
            candidate = passed_check_actual(stage_gate.get("checks"), "camera.serial_number")
            if candidate is not None:
                camera_matches.append(candidate)
        if len(camera_matches) == 1:
            accepted_camera_id = camera_matches[0]

    required_outcome = str(policy["required_collection_outcome"])
    gate_outcome = result.get("collection_gate_outcome_A_E")
    acceptance_outcome = result.get("collection_acceptance_outcome_A_E")
    for name, value in (
        ("collection_gate_outcome_A_E", gate_outcome),
        ("collection_acceptance_outcome_A_E", acceptance_outcome),
    ):
        if value not in valid_statuses:
            errors.append(
                _acceptance_content_error(
                    f"$.rig_acceptance.result.{name}",
                    f"Expected one of {sorted(valid_statuses)!r}",
                )
            )
    for alias, expected in (
        ("gate_outcome", gate_outcome),
        ("acceptance_outcome", acceptance_outcome),
    ):
        if alias in result and result[alias] != expected:
            errors.append(
                issue(
                    "rig_acceptance.content_inconsistent",
                    f"$.rig_acceptance.result.{alias}",
                    f"Alias {alias} contradicts its A-E collection outcome",
                )
            )
    collection_allowed = None if decision is None else decision.get(
        "controlled_data_collection_allowed"
    )
    deployment_eligible = None if decision is None else decision.get(
        "deployment_evidence_eligible"
    )
    for name, value in (
        ("controlled_data_collection_allowed", collection_allowed),
        ("deployment_evidence_eligible", deployment_eligible),
    ):
        if not isinstance(value, bool):
            errors.append(
                _acceptance_content_error(
                    f"$.rig_acceptance.result.decision.{name}", "Expected a boolean"
                )
            )
    if isinstance(collection_allowed, bool) and isinstance(deployment_eligible, bool):
        if collection_allowed != deployment_eligible:
            errors.append(
                issue(
                    "rig_acceptance.content_inconsistent",
                    "$.rig_acceptance.result.decision",
                    "Collection permission and deployment-evidence eligibility must agree",
                )
            )
        if collection_allowed and decision.get("code") != "GO_CONTROLLED_DATA_COLLECTION":
            errors.append(
                issue(
                    "rig_acceptance.content_inconsistent",
                    "$.rig_acceptance.result.decision.code",
                    "Positive collection permission requires GO_CONTROLLED_DATA_COLLECTION",
                )
            )

    summary.update(
        {
            "receipt_id": receipt_id,
            "receipt_sha256": receipt_sha,
            "accepted_rig_id": accepted_rig_id,
            "accepted_camera_id": accepted_camera_id,
            "evidence_kind": evidence_kind,
            "collection_gate_outcome_A_E": gate_outcome,
            "collection_acceptance_outcome_A_E": acceptance_outcome,
            "controlled_data_collection_allowed": collection_allowed is True,
            "deployment_evidence_eligible": deployment_eligible is True,
        }
    )
    if errors:
        summary["status"] = "INVALID"
        return errors, reasons, summary

    prerequisites_pass = all(
        (
            evidence_kind == policy["accepted_evidence_kind"],
            receipt_status == policy["required_validation_status"],
            source_status == policy["required_validation_status"],
            gate_outcome == required_outcome,
            acceptance_outcome == required_outcome,
            all(status == required_outcome for status in stage_statuses.values()),
            all(status == "measured" for status in stage_measurements.values()),
        )
    )
    if (collection_allowed is True or deployment_eligible is True) and not prerequisites_pass:
        errors.append(
            issue(
                "rig_acceptance.content_inconsistent",
                "$.rig_acceptance.result.decision",
                "Positive collection/deployment decision contradicts evidence class or A-E validation",
            )
        )
        summary["status"] = "INVALID"
        return errors, reasons, summary

    evaluator_allows_physical_collection = bool(
        prerequisites_pass
        and collection_allowed == policy["controlled_data_collection_allowed"]
        and deployment_eligible == policy["deployment_evidence_eligible"]
    )
    frame_rig_ids = {
        str(frame["rig_id"]) for frame in manifest["frames"] if "rig_id" in frame
    }
    frame_camera_ids = {
        str(frame["camera_id"]) for frame in manifest["frames"] if "camera_id" in frame
    }
    collection_identity_bound = False
    if evaluator_allows_physical_collection:
        if accepted_rig_id is None or accepted_camera_id is None:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_identity_binding_missing",
                    "$.rig_acceptance.result",
                    "Physical evaluator result must expose passing rig_unit_id and camera.serial_number checks",
                )
            )
        else:
            if frame_rig_ids and frame_rig_ids != {accepted_rig_id}:
                errors.append(
                    issue(
                        "rig_acceptance.rig_identity_mismatch",
                        "$.frames",
                        f"Frame rig IDs {sorted(frame_rig_ids)!r} do not match accepted rig "
                        f"{accepted_rig_id!r}",
                    )
                )
            if frame_camera_ids and frame_camera_ids != {accepted_camera_id}:
                errors.append(
                    issue(
                        "rig_acceptance.camera_identity_mismatch",
                        "$.frames",
                        f"Frame camera IDs {sorted(frame_camera_ids)!r} do not match accepted camera "
                        f"{accepted_camera_id!r}",
                    )
                )
            collection_identity_bound = not errors and bool(frame_rig_ids and frame_camera_ids)
    physical_collection_allowed = bool(
        evaluator_allows_physical_collection and collection_identity_bound
    )
    summary["collection_identity_bound"] = collection_identity_bound
    summary["physical_collection_allowed"] = physical_collection_allowed
    summary["status"] = (
        "INVALID" if errors else "PASS" if physical_collection_allowed else "NOT_READY"
    )
    if errors:
        return errors, reasons, summary
    if real_scope and not physical_collection_allowed:
        if evidence_kind != policy["accepted_evidence_kind"]:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_not_physical",
                    "$.rig_acceptance.result.evidence_kind",
                    "Only a physical_bench evaluator result may authorize real collection",
                )
            )
        if receipt_status != policy["required_validation_status"]:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_receipt_not_pass",
                    "$.rig_acceptance.result.receipt_validation.status",
                    "Physical receipt validation is missing, unmeasured, or not PASS",
                )
            )
        if source_status != policy["required_validation_status"]:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_source_not_pass",
                    "$.rig_acceptance.result.frozen_v2_source_integrity.status",
                    "Frozen V2 source integrity is missing, unmeasured, or not PASS",
                )
            )
        if gate_outcome != required_outcome or acceptance_outcome != required_outcome:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_collection_not_pass",
                    "$.rig_acceptance.result",
                    "Both A-E collection gate and acceptance outcomes must be PASS",
                )
            )
        failed_stages = sorted(
            stage
            for stage in policy["required_stages_A_E"]
            if stage_statuses.get(stage) != required_outcome
            or stage_measurements.get(stage) != "measured"
        )
        if failed_stages:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_stages_not_pass",
                    "$.rig_acceptance.result.stage_results",
                    f"A-E stages missing or not PASS: {failed_stages!r}",
                )
            )
        if collection_allowed != policy["controlled_data_collection_allowed"]:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_collection_not_allowed",
                    "$.rig_acceptance.result.decision.controlled_data_collection_allowed",
                    "Evaluator did not authorize controlled data collection",
                )
            )
        if deployment_eligible != policy["deployment_evidence_eligible"]:
            reasons.append(
                issue(
                    "readiness.rig_acceptance_not_deployment_evidence",
                    "$.rig_acceptance.result.decision.deployment_evidence_eligible",
                    "Evaluator result is not eligible physical evidence",
                )
            )
    return errors, reasons, summary


def validate_semantics(
    manifest: Mapping[str, Any], data_root: Path, config: Mapping[str, Any]
) -> tuple[
    list[dict[str, str]],
    dict[str, Any],
    list[dict[str, str]],
    dict[str, Any],
]:
    findings: list[dict[str, str]] = []
    frames: list[dict[str, Any]] = list(manifest["frames"])
    data_root = data_root.expanduser().resolve()
    metadata_bounds = config["metadata_bounds"]
    annotation = config["annotation"]
    split_policy = config["split"]
    unassigned = str(split_policy["unassigned_role"])
    real_scope = manifest["evidence_scope"] == config["evidence_scope"]["real"]
    required_real_fields = list(config["real_capture_provenance"]["required_frame_fields"])
    readiness_findings: list[dict[str, str]] = []
    missing_real_metadata: list[tuple[int, str]] = []
    image_hashes_checked = 0
    image_hashes_verified = 0
    image_contents_checked = 0
    image_contents_verified = 0

    frame_ids: dict[str, int] = {}
    image_paths: dict[Path, int] = {}
    session_fields: dict[str, set[str]] = defaultdict(set)
    video_scopes: dict[str, set[tuple[str, str]]] = defaultdict(set)
    videos: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    track_keys: set[tuple[str, str, str, str]] = set()
    known_track_classes: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    profile_bindings: dict[str, tuple[Any, ...]] = {}
    profile_binding_frames: dict[str, int] = {}
    video_identities: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)

    for frame_number, frame in enumerate(frames):
        frame_path = f"$.frames[{frame_number}]"
        frame_id = str(frame["frame_id"])
        if frame_id in frame_ids:
            findings.append(
                issue(
                    "frame.duplicate_id",
                    f"{frame_path}.frame_id",
                    f"frame_id duplicates frame {frame_ids[frame_id]}",
                )
            )
        else:
            frame_ids[frame_id] = frame_number

        recorded_path = str(frame["image_path"])
        pure_path = PurePosixPath(recorded_path)
        resolved_image: Path | None = None
        if "\\" in recorded_path:
            findings.append(
                issue(
                    "image.non_posix_path",
                    f"{frame_path}.image_path",
                    "image_path must use repository/data-root-relative POSIX syntax",
                )
            )
        elif pure_path.is_absolute():
            findings.append(
                issue(
                    "image.absolute_path",
                    f"{frame_path}.image_path",
                    "Absolute image paths are forbidden",
                )
            )
        elif any(part in {"", ".", ".."} for part in recorded_path.split("/")):
            findings.append(
                issue(
                    "image.path_traversal",
                    f"{frame_path}.image_path",
                    "image_path may not contain empty, dot, or parent components",
                )
            )
        else:
            resolved_image = (data_root / Path(*pure_path.parts)).resolve()
            try:
                resolved_image.relative_to(data_root)
            except ValueError:
                findings.append(
                    issue(
                        "image.outside_data_root",
                        f"{frame_path}.image_path",
                        "Resolved image escapes data_root",
                    )
                )
                resolved_image = None
        if resolved_image is not None:
            if resolved_image in image_paths:
                findings.append(
                    issue(
                        "image.duplicate",
                        f"{frame_path}.image_path",
                        f"Image path duplicates frame {image_paths[resolved_image]}",
                    )
                )
            else:
                image_paths[resolved_image] = frame_number
            if config["image_files"]["require_exists"] and not resolved_image.is_file():
                findings.append(
                    issue(
                        "image.missing",
                        f"{frame_path}.image_path",
                        f"Image file does not exist under data_root: {recorded_path}",
                    )
                )
            elif (
                config["image_files"]["require_nonempty"]
                and resolved_image.is_file()
                and resolved_image.stat().st_size == 0
            ):
                findings.append(
                    issue(
                        "image.empty",
                        f"{frame_path}.image_path",
                        "Image file is empty",
                    )
                )
            if resolved_image.is_file() and "image_sha256" in frame:
                image_hashes_checked += 1
                observed_image_sha = sha256(resolved_image)
                if observed_image_sha != str(frame["image_sha256"]):
                    findings.append(
                        issue(
                            "image.sha256_mismatch",
                            f"{frame_path}.image_sha256",
                            f"Declared {frame['image_sha256']}, observed {observed_image_sha}",
                        )
                    )
                else:
                    image_hashes_verified += 1
            if real_scope and resolved_image.is_file() and resolved_image.stat().st_size > 0:
                image_contents_checked += 1
                try:
                    with Image.open(resolved_image) as image:
                        observed_width, observed_height = image.size
                        image.verify()
                except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
                    findings.append(
                        issue(
                            "image.content_invalid",
                            f"{frame_path}.image_path",
                            f"File is not a decodable image container: {error}",
                        )
                    )
                else:
                    if "native_width_px" in frame and "native_height_px" in frame:
                        declared_size = (
                            int(frame["native_width_px"]),
                            int(frame["native_height_px"]),
                        )
                        if declared_size != (observed_width, observed_height):
                            findings.append(
                                issue(
                                    "image.native_dimensions_mismatch",
                                    f"{frame_path}.native_width_px",
                                    "Declared native dimensions "
                                    f"{declared_size!r}, decoded {(observed_width, observed_height)!r}",
                                )
                            )
                        else:
                            image_contents_verified += 1

        if real_scope:
            for name in required_real_fields:
                if name not in frame:
                    missing_real_metadata.append((frame_number, name))

        for name in ("exposure_us", "gain_db", "working_distance_mm"):
            value = float(frame[name])
            bounds = metadata_bounds[name]
            if value < float(bounds["minimum"]) or value > float(bounds["maximum"]):
                findings.append(
                    issue(
                        "metadata.out_of_bounds",
                        f"{frame_path}.{name}",
                        f"{value} is outside [{bounds['minimum']}, {bounds['maximum']}]",
                    )
                )
        if "white_balance" in frame:
            white_balance = frame["white_balance"]
            for channel in ("red_gain", "green_gain", "blue_gain"):
                value = float(white_balance[channel])
                bounds = metadata_bounds["white_balance_gain"]
                if value < float(bounds["minimum"]) or value > float(bounds["maximum"]):
                    findings.append(
                        issue(
                            "metadata.white_balance_out_of_bounds",
                            f"{frame_path}.white_balance.{channel}",
                            f"{value} is outside [{bounds['minimum']}, {bounds['maximum']}]",
                        )
                    )
        if "strobe_settings" in frame:
            strobe_settings = frame["strobe_settings"]
            if str(strobe_settings["profile_id"]) != str(frame["strobe_profile_id"]):
                findings.append(
                    issue(
                        "metadata.strobe_profile_mismatch",
                        f"{frame_path}.strobe_settings.profile_id",
                        "strobe_settings.profile_id must equal strobe_profile_id",
                    )
                )
            for name, bound_name in (
                ("pulse_width_us", "strobe_pulse_width_us"),
                ("peak_current_a", "strobe_peak_current_a"),
            ):
                value = float(strobe_settings[name])
                bounds = metadata_bounds[bound_name]
                if value < float(bounds["minimum"]) or value > float(bounds["maximum"]):
                    findings.append(
                        issue(
                            "metadata.strobe_setting_out_of_bounds",
                            f"{frame_path}.strobe_settings.{name}",
                            f"{value} is outside [{bounds['minimum']}, {bounds['maximum']}]",
                        )
                    )

        field_id = str(frame["field_id"])
        session_id = str(frame["session_id"])
        video_id = str(frame["video_id"])
        session_fields[session_id].add(field_id)
        video_scopes[video_id].add((field_id, session_id))
        video_key = (field_id, session_id, video_id)
        videos[video_key].append((frame_number, frame))
        if real_scope and all(name in frame for name in required_real_fields):
            video_identities[video_key].add((str(frame["camera_id"]), str(frame["rig_id"])))
            profile_id = str(frame["capture_profile_id"])
            profile_signature = (
                str(frame["camera_id"]),
                str(frame["rig_id"]),
                int(frame["native_width_px"]),
                int(frame["native_height_px"]),
                str(frame["pixel_format"]),
                frame["exposure_us"],
                frame["gain_db"],
                json.dumps(frame["white_balance"], sort_keys=True, separators=(",", ":")),
                frame["working_distance_mm"],
                str(frame["strobe_profile_id"]),
                json.dumps(frame["strobe_settings"], sort_keys=True, separators=(",", ":")),
            )
            previous_signature = profile_bindings.get(profile_id)
            if previous_signature is not None and previous_signature != profile_signature:
                findings.append(
                    issue(
                        "metadata.capture_profile_drift",
                        f"{frame_path}.capture_profile_id",
                        f"Profile {profile_id!r} differs from frame "
                        f"{profile_binding_frames[profile_id]}",
                    )
                )
            else:
                profile_bindings[profile_id] = profile_signature
                profile_binding_frames[profile_id] = frame_number

        seen_instance_ids: set[str] = set()
        seen_track_ids: set[str] = set()
        for instance_number, instance in enumerate(frame["instances"]):
            instance_path = f"{frame_path}.instances[{instance_number}]"
            instance_id = str(instance["instance_id"])
            track_id = str(instance["track_id"])
            if instance_id in seen_instance_ids:
                findings.append(
                    issue(
                        "instance.duplicate_in_frame",
                        f"{instance_path}.instance_id",
                        f"instance_id {instance_id!r} occurs twice in one frame",
                    )
                )
            seen_instance_ids.add(instance_id)
            if track_id in seen_track_ids:
                findings.append(
                    issue(
                        "track.duplicate_in_frame",
                        f"{instance_path}.track_id",
                        f"track_id {track_id!r} occurs twice in one frame",
                    )
                )
            seen_track_ids.add(track_id)

            track_key = (*video_key, track_id)
            track_keys.add(track_key)
            class_name = str(instance["class_name"])
            if class_name != "partial_unknown":
                known_track_classes[track_key].add(class_name)

            polygon = instance["polygon"]
            vertices = [tuple(float(coordinate) for coordinate in point) for point in polygon]
            if len(set(vertices)) != len(vertices):
                findings.append(
                    issue(
                        "polygon.duplicate_vertex",
                        f"{instance_path}.polygon",
                        "Polygon vertices must be unique and the first vertex must not be repeated",
                    )
                )
            if _polygon_area(polygon) < float(annotation["minimum_normalized_polygon_area"]):
                findings.append(
                    issue(
                        "polygon.area_too_small",
                        f"{instance_path}.polygon",
                        "Polygon has zero or sub-threshold normalized area",
                    )
                )
            if _polygon_self_intersects(polygon):
                findings.append(
                    issue(
                        "polygon.self_intersection",
                        f"{instance_path}.polygon",
                        "Polygon edges self-intersect",
                    )
                )

            if class_name == "partial_unknown" and not bool(instance["partial"]):
                findings.append(
                    issue(
                        "annotation.partial_unknown_requires_partial",
                        f"{instance_path}.partial",
                        "partial_unknown is reserved for border-truncated, unresolved plants",
                    )
                )
            canopy_span = instance["canopy_span_mm"]
            if class_name == "partial_unknown" and canopy_span is not None:
                findings.append(
                    issue(
                        "annotation.partial_unknown_canopy_span",
                        f"{instance_path}.canopy_span_mm",
                        "partial_unknown canopy_span_mm must be null",
                    )
                )
            eligible = (
                class_name in {"crop", "weed"}
                and not bool(instance["partial"])
                and not bool(instance["occluded"])
                and float(instance["visible_fraction"])
                >= float(annotation["complete_visibility_threshold"])
            )
            if eligible and canopy_span is None:
                findings.append(
                    issue(
                        "annotation.eligible_canopy_span_missing",
                        f"{instance_path}.canopy_span_mm",
                        "Fully visible crop/weed requires measured canopy_span_mm",
                    )
                )
            if canopy_span is not None:
                bounds = metadata_bounds["canopy_span_mm"]
                value = float(canopy_span)
                if value < float(bounds["minimum"]) or value > float(bounds["maximum"]):
                    findings.append(
                        issue(
                            "annotation.canopy_span_out_of_bounds",
                            f"{instance_path}.canopy_span_mm",
                            f"{value} is outside [{bounds['minimum']}, {bounds['maximum']}]",
                        )
                    )

    for session_id, field_ids in sorted(session_fields.items()):
        if len(field_ids) > 1:
            findings.append(
                issue(
                    "session.multiple_fields",
                    "$.frames",
                    f"session_id {session_id!r} appears in fields {sorted(field_ids)!r}",
                )
            )
    for video_id, scopes in sorted(video_scopes.items()):
        if len(scopes) > 1:
            findings.append(
                issue(
                    "video.multiple_sessions",
                    "$.frames",
                    f"video_id {video_id!r} appears in field/session scopes {sorted(scopes)!r}",
                )
            )
    for video_key, identities in sorted(video_identities.items()):
        if len(identities) > 1:
            findings.append(
                issue(
                    "metadata.video_identity_drift",
                    "$.frames",
                    f"Video {video_key!r} changes camera/rig identity: {sorted(identities)!r}",
                )
            )
    for track_key, classes in sorted(known_track_classes.items()):
        if len(classes) > 1:
            findings.append(
                issue(
                    "track.class_conflict",
                    "$.frames",
                    f"Track {track_key!r} has conflicting known classes {sorted(classes)!r}",
                )
            )

    adjacent_gap = int(split_policy["adjacent_frame_max_gap"])
    for video_key, entries in sorted(videos.items()):
        ordered = sorted(entries, key=lambda pair: int(pair[1]["frame_index"]))
        indices: dict[int, int] = {}
        previous_timestamp: int | None = None
        previous_camera_record: tuple[int, int, int] | None = None
        for frame_number, frame in ordered:
            index = int(frame["frame_index"])
            if index in indices:
                findings.append(
                    issue(
                        "video.duplicate_frame_index",
                        f"$.frames[{frame_number}].frame_index",
                        f"frame_index duplicates frame {indices[index]} in video {video_key!r}",
                    )
                )
            indices[index] = frame_number
            timestamp = int(frame["timestamp_ns"])
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                findings.append(
                    issue(
                        "video.timestamp_not_increasing",
                        f"$.frames[{frame_number}].timestamp_ns",
                        f"timestamp_ns is not strictly increasing by frame_index in {video_key!r}",
                    )
                )
            previous_timestamp = timestamp
            if real_scope and all(
                name in frame for name in ("camera_frame_counter", "camera_timestamp_ns")
            ):
                camera_counter = int(frame["camera_frame_counter"])
                camera_timestamp = int(frame["camera_timestamp_ns"])
                if previous_camera_record is not None:
                    prior_index, prior_counter, prior_camera_timestamp = previous_camera_record
                    if camera_counter <= prior_counter:
                        findings.append(
                            issue(
                                "video.camera_counter_not_increasing",
                                f"$.frames[{frame_number}].camera_frame_counter",
                                f"Camera counter is not strictly increasing in {video_key!r}",
                            )
                        )
                    if camera_timestamp <= prior_camera_timestamp:
                        findings.append(
                            issue(
                                "video.camera_timestamp_not_increasing",
                                f"$.frames[{frame_number}].camera_timestamp_ns",
                                f"Camera timestamp is not strictly increasing in {video_key!r}",
                            )
                        )
                    frame_delta = index - prior_index
                    counter_delta = camera_counter - prior_counter
                    if frame_delta != 1 or counter_delta != 1:
                        findings.append(
                            issue(
                                "video.frame_sequence_gap",
                                f"$.frames[{frame_number}].frame_index",
                                f"Real video frames/counters must be contiguous; observed "
                                f"frame delta {frame_delta}, counter delta {counter_delta} "
                                f"in {video_key!r}",
                            )
                        )
                    if counter_delta != frame_delta:
                        findings.append(
                            issue(
                                "video.frame_counter_delta_mismatch",
                                f"$.frames[{frame_number}].camera_frame_counter",
                                f"frame_index delta {frame_delta} differs from camera counter "
                                f"delta {counter_delta} in {video_key!r}",
                            )
                        )
                previous_camera_record = (index, camera_counter, camera_timestamp)
        for (left_number, left), (right_number, right) in zip(ordered, ordered[1:]):
            gap = int(right["frame_index"]) - int(left["frame_index"])
            if gap <= adjacent_gap and str(left["split"]) != str(right["split"]):
                findings.append(
                    issue(
                        "split.adjacent_frame_leakage",
                        f"$.frames[{right_number}].split",
                        f"Adjacent frames {left['frame_id']!r}/{right['frame_id']!r} cross roles",
                    )
                )

    group_specs = (
        ("field", lambda frame: str(frame["field_id"])),
        ("session", lambda frame: (str(frame["field_id"]), str(frame["session_id"]))),
    )
    for label, key in group_specs:
        roles = _role_sets(frames, key, unassigned)
        for group, observed in sorted(roles.items(), key=lambda item: str(item[0])):
            if len(observed) > 1:
                findings.append(
                    issue(
                        f"split.{label}_leakage",
                        "$.frames",
                        f"{label} group {group!r} crosses roles {sorted(observed)!r}",
                    )
                )

    track_roles: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for frame in frames:
        role = str(frame["split"])
        if role == unassigned:
            continue
        for instance in frame["instances"]:
            key = (
                str(frame["field_id"]),
                str(frame["session_id"]),
                str(frame["video_id"]),
                str(instance["track_id"]),
            )
            track_roles[key].add(role)
    for group, observed in sorted(track_roles.items()):
        if len(observed) > 1:
            findings.append(
                issue(
                    "split.video_track_leakage",
                    "$.frames",
                    f"video-track group {group!r} crosses roles {sorted(observed)!r}",
                )
            )

    field_roles: dict[str, set[str]] = defaultdict(set)
    for frame in frames:
        field_roles[str(frame["field_id"])].add(str(frame["split"]))
    for field_id, roles in sorted(field_roles.items()):
        if unassigned in roles and len(roles) > 1:
            findings.append(
                issue(
                    "split.partial_assignment",
                    "$.frames",
                    f"Field {field_id!r} mixes unassigned and frozen roles",
                )
            )
    deterministic = deterministic_field_splits(field_roles, split_policy)
    if all(unassigned not in roles for roles in field_roles.values()):
        for field_id, roles in sorted(field_roles.items()):
            if len(roles) == 1 and next(iter(roles)) != deterministic[field_id]:
                findings.append(
                    issue(
                        "split.non_deterministic_assignment",
                        "$.frames",
                        f"Field {field_id!r} has {next(iter(roles))!r}; frozen plan requires {deterministic[field_id]!r}",
                    )
                )

    if real_scope and missing_real_metadata:
        missing_names = sorted({name for _, name in missing_real_metadata})
        readiness_findings.append(
            issue(
                "readiness.real_capture_metadata_missing",
                "$.frames",
                f"{len(missing_real_metadata)} required frame values are missing; "
                f"fields={missing_names!r}",
            )
        )
    acceptance_errors, acceptance_reasons, acceptance_summary = validate_rig_acceptance(
        manifest, data_root, config
    )
    findings.extend(acceptance_errors)
    readiness_findings.extend(acceptance_reasons)

    stats = {
        "frames": len(frames),
        "images": len(image_paths),
        "instances": sum(len(frame["instances"]) for frame in frames),
        "tracks": len(track_keys),
        "fields": len({str(frame["field_id"]) for frame in frames}),
        "sessions": len(
            {(str(frame["field_id"]), str(frame["session_id"])) for frame in frames}
        ),
        "videos": len(videos),
        "split_counts": dict(sorted(Counter(str(frame["split"]) for frame in frames).items())),
        "class_counts": dict(
            sorted(
                Counter(
                    str(instance["class_name"])
                    for frame in frames
                    for instance in frame["instances"]
                ).items()
            )
        ),
        "deterministic_field_assignment": deterministic,
    }
    integrity = {
        "real_capture_metadata_complete": bool(real_scope and not missing_real_metadata),
        "resolved_image_paths": sorted(str(path) for path in image_paths),
        "image_sha256_checked": image_hashes_checked,
        "image_sha256_verified": image_hashes_verified,
        "image_content_checked": image_contents_checked,
        "image_content_verified": image_contents_verified,
        "all_real_image_sha256_verified": bool(
            real_scope and image_hashes_verified == len(frames)
        ),
        "all_real_image_content_verified": bool(
            real_scope and image_contents_verified == len(frames)
        ),
        "rig_acceptance": acceptance_summary,
    }
    return (
        sorted(findings, key=lambda item: (item["code"], item["path"], item["message"])),
        stats,
        sorted(
            readiness_findings,
            key=lambda item: (item["code"], item["path"], item["message"]),
        ),
        integrity,
    )


def _capture_input_path_roles(
    manifest_path: Path,
    config_path: Path,
    schema_path: Path,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    data_root: Path,
) -> dict[Path, list[str]]:
    roles: dict[Path, list[str]] = defaultdict(list)
    for role, path in (
        ("manifest", manifest_path),
        ("config", config_path),
        ("schema", schema_path),
        ("audit_implementation", Path(__file__).resolve()),
        (
            "rig_acceptance_contract",
            resolve_repo_path(PROJECT_ROOT, str(config["rig_acceptance"]["contract_path"])),
        ),
        (
            "rig_acceptance_evaluator",
            resolve_repo_path(PROJECT_ROOT, str(config["rig_acceptance"]["evaluator_path"])),
        ),
    ):
        roles[path.resolve()].append(role)
    frames = manifest.get("frames")
    if isinstance(frames, list):
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict) or not isinstance(frame.get("image_path"), str):
                continue
            recorded = str(frame["image_path"])
            pure_path = PurePosixPath(recorded)
            candidate = (
                Path(recorded).resolve()
                if pure_path.is_absolute()
                else (data_root / Path(*pure_path.parts)).resolve()
            )
            roles[candidate].append(f"image[{index}]")
    rig_reference = manifest.get("rig_acceptance")
    if isinstance(rig_reference, dict) and isinstance(
        rig_reference.get("result_path"), str
    ):
        recorded = str(rig_reference["result_path"])
        pure_path = PurePosixPath(recorded)
        candidate = (
            Path(recorded).resolve()
            if pure_path.is_absolute()
            else (data_root / Path(*pure_path.parts)).resolve()
        )
        roles[candidate].append("rig_acceptance_result")
    return dict(roles)


def _input_path_collision_findings(
    path_roles: Mapping[Path, Sequence[str]],
) -> list[dict[str, str]]:
    return [
        issue(
            "path.input_role_collision",
            "$",
            f"Resolved path {path} has multiple source roles {list(roles)!r}",
        )
        for path, roles in sorted(path_roles.items(), key=lambda item: str(item[0]))
        if len(roles) > 1
    ]


def evaluate_readiness(
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    stats: Mapping[str, Any],
    errors: Sequence[Mapping[str, str]],
    semantic_reasons: Sequence[Mapping[str, str]] = (),
) -> tuple[str, list[dict[str, str]]]:
    if errors:
        return "INVALID", []
    reasons: list[dict[str, str]] = [dict(reason) for reason in semantic_reasons]
    readiness = config["readiness"]
    scope = str(manifest["evidence_scope"])
    if scope == config["evidence_scope"]["synthetic_fixture"]:
        reasons.append(
            issue(
                "readiness.synthetic_fixture_only",
                "$.evidence_scope",
                "Synthetic fixtures test the contract but never count as real target-rig field evidence",
            )
        )
    if int(stats["fields"]) < int(readiness["minimum_fields"]):
        reasons.append(
            issue(
                "readiness.minimum_fields_not_met",
                "$.frames",
                f"Need at least {readiness['minimum_fields']} fields; found {stats['fields']}",
            )
        )
    if int(stats["sessions"]) < int(readiness["minimum_sessions"]):
        reasons.append(
            issue(
                "readiness.minimum_sessions_not_met",
                "$.frames",
                f"Need at least {readiness['minimum_sessions']} field/session groups; found {stats['sessions']}",
            )
        )
    split_counts = stats["split_counts"]
    unassigned = str(config["split"]["unassigned_role"])
    if int(split_counts.get(unassigned, 0)) > 0:
        reasons.append(
            issue(
                "readiness.splits_not_frozen",
                "$.frames",
                f"{split_counts[unassigned]} frames remain unassigned",
            )
        )
    if bool(config["split"]["require_every_role_for_ready"]):
        missing_roles = [
            role for role in config["split"]["roles"] if int(split_counts.get(role, 0)) == 0
        ]
        if missing_roles:
            reasons.append(
                issue(
                    "readiness.split_roles_missing",
                    "$.frames",
                    f"Frozen split is missing roles {missing_roles!r}",
                )
            )
    reasons.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return (readiness["ready_status"] if not reasons else readiness["not_ready_status"]), reasons


def audit_capture(
    manifest_path: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
    data_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()
    inferred_repo = config_path.parents[2]
    repo = Path(repo_root).expanduser().resolve() if repo_root is not None else inferred_repo
    root = (
        Path(data_root).expanduser().resolve()
        if data_root is not None
        else manifest_path.parent.resolve()
    )
    config = load_yaml_mapping(config_path)
    validate_policy(config)
    policy_file_sha256 = sha256(config_path)
    if policy_file_sha256 != FROZEN_POLICY_FILE_SHA256:
        raise ValueError(
            "Capture audit policy file identity drifted: "
            f"expected {FROZEN_POLICY_FILE_SHA256}, observed {policy_file_sha256}"
        )
    schema_path = resolve_repo_path(repo, str(config["manifest_schema"]))
    schema = load_json_object(schema_path)
    validate_schema_contract(schema)
    schema_file_sha256 = sha256(schema_path)
    if schema_file_sha256 != FROZEN_SCHEMA_FILE_SHA256:
        raise ValueError(
            "Capture manifest schema file identity drifted: "
            f"expected {FROZEN_SCHEMA_FILE_SHA256}, observed {schema_file_sha256}"
        )
    manifest = load_json_object(manifest_path)
    errors = validate_json_schema(manifest, schema)
    stats: dict[str, Any] = {
        "frames": 0,
        "images": 0,
        "instances": 0,
        "tracks": 0,
        "fields": 0,
        "sessions": 0,
        "videos": 0,
        "split_counts": {},
        "class_counts": {},
        "deterministic_field_assignment": {},
    }
    semantic_reasons: list[dict[str, str]] = []
    integrity: dict[str, Any] = {
        "real_capture_metadata_complete": False,
        "resolved_image_paths": [],
        "image_sha256_checked": 0,
        "image_sha256_verified": 0,
        "image_content_checked": 0,
        "image_content_verified": 0,
        "all_real_image_sha256_verified": False,
        "all_real_image_content_verified": False,
        "rig_acceptance": {
            "present": False,
            "physical_collection_allowed": False,
            "status": "NOT_EVALUATED",
        },
    }
    if not errors:
        semantic_errors, stats, semantic_reasons, integrity = validate_semantics(
            manifest, root, config
        )
        errors.extend(semantic_errors)
    input_path_roles = _capture_input_path_roles(
        manifest_path, config_path, schema_path, config, manifest, root
    )
    errors.extend(_input_path_collision_findings(input_path_roles))
    errors.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    status, readiness_reasons = evaluate_readiness(
        manifest, config, stats, errors, semantic_reasons
    )
    synthetic = manifest.get("evidence_scope") == config["evidence_scope"]["synthetic_fixture"]
    provenance_bound_real_scope = (
        not errors and manifest.get("evidence_scope") == config["evidence_scope"]["real"]
        and integrity["real_capture_metadata_complete"]
        and integrity["all_real_image_sha256_verified"]
        and integrity["all_real_image_content_verified"]
        and integrity["rig_acceptance"]["physical_collection_allowed"]
    )
    return {
        "audit_contract": "spot_spray_capture_audit_v1",
        "manifest_contract": "capture_manifest_v1",
        "status": status,
        "valid": not errors,
        "ready": status == config["readiness"]["ready_status"],
        "evidence": {
            "scope": manifest.get("evidence_scope"),
            "synthetic_fixture": synthetic,
            "counts_as_real_target_rig_evidence": provenance_bound_real_scope,
            "fixture_can_unlock_ready": False,
        },
        "integrity": integrity,
        "statistics": stats,
        "errors": errors,
        "readiness_reasons": readiness_reasons,
        "inputs": {
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "schema": str(schema_path),
            "schema_sha256": schema_file_sha256,
            "schema_semantic_sha256": _canonical_mapping_sha256(schema),
            "policy": str(config_path),
            "policy_sha256": policy_file_sha256,
            "policy_semantic_sha256": _canonical_mapping_sha256(config),
            "data_root": str(root),
            "image_files": list(integrity["resolved_image_paths"]),
            "rig_acceptance_result": integrity["rig_acceptance"].get(
                "resolved_result_path"
            ),
            "rig_acceptance_contract": integrity["rig_acceptance"].get(
                "trusted_contract_path"
            ),
            "rig_acceptance_contract_sha256": integrity["rig_acceptance"].get(
                "trusted_contract_sha256"
            ),
            "rig_acceptance_evaluator": integrity["rig_acceptance"].get(
                "trusted_evaluator_path"
            ),
            "rig_acceptance_evaluator_sha256": integrity["rig_acceptance"].get(
                "trusted_evaluator_sha256"
            ),
            "protected_paths": sorted(str(path) for path in input_path_roles),
        },
        "implementation": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256(Path(__file__).resolve()),
        },
        "audit_scope": {
            "image_files_read": bool(
                integrity["image_sha256_checked"] or integrity["image_content_checked"]
            ),
            "image_file_metadata_checked": True,
            "image_file_bytes_hashed": integrity["image_sha256_checked"],
            "image_hashes_verified": integrity["image_sha256_verified"],
            "image_containers_checked": integrity["image_content_checked"],
            "image_containers_and_dimensions_verified": integrity[
                "image_content_verified"
            ],
            "scene_quality_metrics_evaluated": False,
            "model_outputs_read": False,
            "real_field_evidence_inferred_from_fixtures": False,
        },
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _atomic_write_text(path: Path, content: str, overwrite: bool) -> None:
    path = _absolute_lexical_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and (path.exists() or path.is_symlink()):
        raise ValueError(
            f"Refusing existing output target without explicit --overwrite: {path}"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise ValueError(
                    f"Output target appeared without explicit --overwrite: {path}"
                ) from error
            temporary.unlink()
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(
    path: Path, payload: Mapping[str, Any], overwrite: bool
) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        overwrite=overwrite,
    )


def _validate_publish_targets(
    audit: Mapping[str, Any],
    output: Path | None,
    derived_manifest: Path | None,
    overwrite: bool,
) -> tuple[Path | None, Path | None]:
    resolved_output = None if output is None else _absolute_lexical_path(output)
    resolved_derived = (
        None if derived_manifest is None else _absolute_lexical_path(derived_manifest)
    )
    targets = [
        (role, path)
        for role, path in (
            ("output", resolved_output),
            ("derived_manifest", resolved_derived),
        )
        if path is not None
    ]
    if overwrite and not targets:
        raise ValueError("--overwrite requires --output or --assign-splits")
    if len({path.resolve() for _, path in targets}) != len(targets):
        raise ValueError("Audit output and derived manifest targets must be distinct")

    inputs = audit.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("protected_paths"), list):
        raise ValueError("Audit report is missing its protected input-path receipt")
    protected = {Path(str(path)).resolve() for path in inputs["protected_paths"]}
    for role, target in targets:
        if target.resolve() in protected:
            raise ValueError(
                f"Refusing {role} collision with a protected capture input: {target}"
            )
        if not overwrite and (target.exists() or target.is_symlink()):
            raise ValueError(
                f"Refusing existing {role} target without explicit --overwrite: {target}"
            )
    return resolved_output, resolved_derived


def _exit_code(status: str) -> int:
    return {
        "READY": EXIT_READY,
        "INVALID": EXIT_INVALID,
        "NOT_READY": EXIT_NOT_READY,
    }[status]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--assign-splits",
        type=Path,
        help="Write a derived manifest after deterministic field-level assignment; input must be entirely unassigned.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly replace existing non-source --output/--assign-splits targets; protected inputs are never writable.",
    )
    arguments = parser.parse_args(argv)
    try:
        manifest_path = arguments.manifest.expanduser().resolve()
        audit = audit_capture(
            manifest_path,
            arguments.config,
            arguments.data_root,
            arguments.repo_root,
        )
        output, target = _validate_publish_targets(
            audit,
            arguments.output,
            arguments.assign_splits,
            arguments.overwrite,
        )
        if target is not None:
            if audit["status"] == "INVALID":
                raise ValueError("Refusing split assignment because the input manifest is INVALID")
            config = load_yaml_mapping(arguments.config)
            validate_policy(config)
            assigned = assign_deterministic_splits(load_json_object(manifest_path), config)
            _atomic_write_json(target, assigned, overwrite=arguments.overwrite)
            audit = audit_capture(
                target,
                arguments.config,
                arguments.data_root,
                arguments.repo_root,
            )
            audit["derived_manifest"] = {
                "path": str(target),
                "sha256": sha256(target),
                "source_manifest": str(manifest_path),
            }
        rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
        if output is not None:
            _atomic_write_text(output, rendered, overwrite=arguments.overwrite)
        sys.stdout.write(rendered)
        return _exit_code(str(audit["status"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.stderr.write(
            json.dumps(
                {
                    "audit_contract": "spot_spray_capture_audit_v1",
                    "status": "INVALID",
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
