#!/usr/bin/env python3
"""Build and validate the pinned spot-spray product architecture V1 contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "configs/deploy/spot_spray_product_architecture_v1.yaml"
)
ALLOWED_RESULT_ROOT = (
    PROJECT_ROOT / "docs/results/spot_spray_product_architecture_v1"
)
DEFAULT_RESULT = ALLOWED_RESULT_ROOT / "architecture.json"
DEFAULT_BOM_CSV = ALLOWED_RESULT_ROOT / "bom.csv"
DEFAULT_VISUAL_MANIFEST = ALLOWED_RESULT_ROOT / "visual_manifest.json"
DEFAULT_PACKAGE_MANIFEST = ALLOWED_RESULT_ROOT / "package_manifest.json"
DEFAULT_DOCUMENT = PROJECT_ROOT / "docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ABS_TOL = 1e-9
SOURCE_LOCK_GROUPS = ("terminal_plans", "terminal_surveys", "upstream_authorities")
TERMINAL_SOURCE_IDS = {
    "terminal_plans": {
        "sensor_optics_plan",
        "light_enclosure_plan",
        "platform_product_plan",
    },
    "terminal_surveys": {
        "sensor_optics_survey",
        "light_enclosure_survey",
        "platform_product_survey",
    },
}


class SourceDriftError(ValueError):
    """A pinned input is missing or no longer has its admitted identity."""


class CrossLaneConflictError(ValueError):
    """Two admitted contracts disagree at an integration boundary."""


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


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
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return payload


def load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
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


def render_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            _json_value(payload),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _repo_file(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Source path escapes repository: {relative_path}") from exc
    if not path.is_file():
        raise SourceDriftError(f"Pinned source is missing: {relative_path}")
    return path


def _source_rows(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source_lock = config.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise ValueError("source_lock must be a mapping")
    rows: list[Mapping[str, Any]] = []
    for group in SOURCE_LOCK_GROUPS:
        value = source_lock.get(group)
        if not isinstance(value, list) or not value:
            raise ValueError(f"source_lock.{group} must be a non-empty list")
        for row in value:
            if not isinstance(row, Mapping):
                raise ValueError(f"source_lock.{group} rows must be mappings")
            rows.append(row)
    return rows


def _git_command(
    root: Path,
    *args: str,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root.resolve()), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SourceDriftError(
            "INTEGRATION_INVALID_SOURCE_DRIFT: git executable unavailable"
        ) from exc
    if result.returncode not in accepted_returncodes:
        raise SourceDriftError(
            "INTEGRATION_INVALID_SOURCE_DRIFT: "
            f"git {args[0] if args else 'command'} verification failed"
        )
    return result


def verify_source_lock(
    config: Mapping[str, Any], root: Path = PROJECT_ROOT
) -> dict[str, dict[str, Any]]:
    """Verify exact bytes before parsing or calculating from upstream sources."""

    source_lock = config.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise ValueError("source_lock must be a mapping")
    rows = _source_rows(config)
    implementation_base_commit = str(
        source_lock.get("implementation_base_commit", "")
    )
    if not GIT_COMMIT_RE.fullmatch(implementation_base_commit):
        raise ValueError(
            "source_lock.implementation_base_commit must be an exact Git commit"
        )
    for group, expected_ids in TERMINAL_SOURCE_IDS.items():
        group_rows = source_lock[group]
        observed_ids = {str(row.get("source_id")) for row in group_rows}
        if observed_ids != expected_ids:
            raise ValueError(
                f"source_lock.{group} must contain exactly {sorted(expected_ids)}"
            )

    resolved_commit = _git_command(
        root,
        "rev-parse",
        "--verify",
        f"{implementation_base_commit}^{{commit}}",
    ).stdout.decode("ascii").strip()
    if resolved_commit != implementation_base_commit:
        raise SourceDriftError(
            "INTEGRATION_INVALID_SOURCE_DRIFT: implementation base commit identity "
            "does not resolve exactly"
        )
    ancestor = _git_command(
        root,
        "merge-base",
        "--is-ancestor",
        implementation_base_commit,
        "HEAD",
        accepted_returncodes=(0, 1),
    )
    if ancestor.returncode != 0:
        raise SourceDriftError(
            "INTEGRATION_INVALID_SOURCE_DRIFT: implementation base commit is not "
            "reachable from HEAD"
        )

    terminal_source_ids = set().union(*TERMINAL_SOURCE_IDS.values())
    terminal_paths: list[str] = []
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    verified: dict[str, dict[str, Any]] = {}
    for row in rows:
        required = {"source_id", "path", "sha256", "owner", "role"}
        missing = required - set(row)
        if missing:
            raise ValueError(f"Source row missing fields: {sorted(missing)}")
        source_id = str(row["source_id"])
        relative_path = str(row["path"])
        expected = str(row["sha256"])
        if source_id in source_ids:
            raise ValueError(f"Duplicate source_id: {source_id}")
        if relative_path in source_paths:
            raise ValueError(f"Duplicate source path: {relative_path}")
        if not SHA256_RE.fullmatch(expected):
            raise ValueError(f"Invalid SHA-256 pin for {source_id}: {expected}")
        source_ids.add(source_id)
        source_paths.add(relative_path)

        path = _repo_file(root, relative_path)
        actual = sha256_file(path)
        if actual != expected:
            raise SourceDriftError(
                "INTEGRATION_INVALID_SOURCE_DRIFT: "
                f"{source_id} expected {expected}, observed {actual}"
            )

        containing_commit: str | None = None
        if source_id in terminal_source_ids:
            containing_commit = str(row.get("containing_commit", ""))
            if containing_commit != implementation_base_commit:
                raise SourceDriftError(
                    "INTEGRATION_INVALID_SOURCE_DRIFT: "
                    f"{source_id} containing commit must equal the implementation "
                    "base commit"
                )
            committed_payload = _git_command(
                root,
                "show",
                f"{containing_commit}:{relative_path}",
            ).stdout
            committed_sha256 = hashlib.sha256(committed_payload).hexdigest()
            if committed_sha256 != expected:
                raise SourceDriftError(
                    "INTEGRATION_INVALID_SOURCE_DRIFT: "
                    f"{source_id} is not present with its pinned bytes at "
                    f"{containing_commit}"
                )
            terminal_paths.append(relative_path)

        receipt: dict[str, Any] = {
            "path": relative_path,
            "sha256": actual,
            "owner": row["owner"],
            "role": row["role"],
            "exact_bytes_verified": True,
        }
        if containing_commit is not None:
            receipt["containing_commit"] = containing_commit
            receipt["committed_bytes_verified"] = True
        canonical_expected = row.get("canonical_sha256")
        if canonical_expected is not None:
            canonical_expected = str(canonical_expected)
            if not SHA256_RE.fullmatch(canonical_expected):
                raise ValueError(f"Invalid canonical SHA-256 pin for {source_id}")
            canonical_actual = canonical_mapping_sha256(load_yaml_mapping(path))
            if canonical_actual != canonical_expected:
                raise SourceDriftError(
                    "INTEGRATION_INVALID_SOURCE_DRIFT: "
                    f"{source_id} canonical policy expected {canonical_expected}, "
                    f"observed {canonical_actual}"
                )
            receipt.update(
                {
                    "canonical_sha256": canonical_actual,
                    "canonical_policy_verified": True,
                }
            )
        verified[source_id] = receipt

    terminal_diff = _git_command(
        root,
        "diff",
        "--quiet",
        "--no-ext-diff",
        implementation_base_commit,
        "--",
        *terminal_paths,
        accepted_returncodes=(0, 1),
    )
    if terminal_diff.returncode != 0:
        raise SourceDriftError(
            "INTEGRATION_INVALID_SOURCE_DRIFT: terminal source worktree differs "
            "from the pinned implementation base commit"
        )
    return verified


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _as_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _expect_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise CrossLaneConflictError(
            "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: "
            f"{label} expected {expected!r}, observed {actual!r}"
        )


def _expect_close(actual: Any, expected: Any, label: str) -> None:
    actual_number = _as_number(actual, label)
    expected_number = _as_number(expected, label)
    if not math.isclose(actual_number, expected_number, rel_tol=0.0, abs_tol=ABS_TOL):
        raise CrossLaneConflictError(
            "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: "
            f"{label} expected {expected_number}, observed {actual_number}"
        )


def _verify_upstream_consistency(
    config: Mapping[str, Any],
    verified_sources: Mapping[str, Mapping[str, Any]],
    root: Path,
) -> None:
    """Check decisive fields against their owning machine-readable authorities."""

    def source_path(source_id: str) -> Path:
        return _repo_file(root, str(verified_sources[source_id]["path"]))

    capture = load_yaml_mapping(source_path("capture_optimization_contract"))
    imaging = load_yaml_mapping(source_path("product_imaging_contract"))
    acceptance = load_yaml_mapping(source_path("rig_acceptance_contract"))
    halo = load_json_mapping(source_path("halo_compute_summary"))
    action = load_yaml_mapping(source_path("track_action_contract"))

    baseline = _as_mapping(config["baseline"], "baseline")
    sensor = _as_mapping(baseline["sensor_optics"], "baseline.sensor_optics")
    light = _as_mapping(
        baseline["light_enclosure"], "baseline.light_enclosure"
    )
    platform = _as_mapping(
        baseline["platform_carrier"], "baseline.platform_carrier"
    )
    compute = _as_mapping(
        baseline["compute_capture"], "baseline.compute_capture"
    )
    power = _as_mapping(baseline["power_thermal"], "baseline.power_thermal")
    safety = _as_mapping(baseline["safety"], "baseline.safety")

    image_baseline = imaging["baseline_proof_module"]
    _expect_equal(sensor["camera_count"], imaging["camera_count_and_swath"]["frozen_proof_camera_count"], "camera count")
    _expect_equal(sensor["model"], image_baseline["camera"]["model"], "camera model")
    _expect_equal(sensor["order_number"], image_baseline["camera"]["order_number"], "camera order")
    _expect_equal(sensor["lens_model"], image_baseline["lens"]["model"], "lens model")
    _expect_equal(sensor["active_roi_px"], image_baseline["capture"]["native_roi_px"], "active ROI")
    _expect_equal(sensor["active_roi_offset_px"], image_baseline["capture"]["native_roi_offset_px"], "ROI offset")
    _expect_equal(sensor["ground_fov_mm"], [474.0, image_baseline["capture"]["nominal_ground_FOV_mm"], 484.0], "FOV samples")
    _expect_equal(sensor["working_distance_adjustment_mm"], image_baseline["capture"]["working_distance_adjustment_mm"], "working distance")
    _expect_close(sensor["aperture_f_number"], image_baseline["lens"]["selected_aperture_f_number"], "aperture")
    _expect_close(sensor["exposure_us"], image_baseline["capture"]["exposure_us"], "exposure")
    _expect_close(sensor["acquisition_rate_hz"], image_baseline["capture"]["acquisition_rate_hz"], "baseline rate")
    _expect_equal(sensor["outer_abstain_ring_px"], image_baseline["tiling"]["halo_px"], "outer abstain ring")

    _expect_equal(light["hood_internal_plan_minimum_mm"], imaging["hood_light_and_functional_ruggedization"]["hood"]["minimum_internal_plan_mm"], "hood internal plan")
    _expect_equal(light["spectrum_cct_k"], imaging["hood_light_and_functional_ruggedization"]["illumination"]["correlated_color_temperature_k"], "light CCT")
    _expect_equal(light["polarization_state"], "OFF", "polarization baseline")
    _expect_equal(platform["proof_topology"], "manual_tractor_rear_three_point_rigid_toolbar", "proof topology")
    _expect_equal(platform["exact_host"], None, "exact host state")

    _expect_equal(compute["stage_e_proxy_checkpoint_sha256"], halo["checkpoint_sha256"], "Stage-E proxy checkpoint")
    _expect_close(compute["halo_batch4_p95_ms"], halo["timing_by_batch_size"]["4"]["latency_ms"]["p95"], "halo batch-4 p95")
    _expect_equal(compute["selected_foundation_checkpoint_sha256"], action["model"]["foundation"]["checkpoint_sha256"], "selected foundation checkpoint")
    _expect_equal(action["model"]["evaluated_checkpoint"]["checkpoint_sha256"], None, "evaluated checkpoint readiness")

    gates = acceptance["thresholds"]
    _expect_close(power["light_branch_average_maximum_w"], gates["D_light_hood_and_polarization"]["light_branch_average_power_maximum_w"], "light average power")
    _expect_close(power["capture_module_average_maximum_w_excluding_compute"], gates["D_light_hood_and_polarization"]["capture_module_average_power_maximum_w_excluding_compute"], "capture module average power")
    _expect_close(power["thermal_duration_minimum_minutes"], gates["B_transport_trigger_and_thermal"]["thermal_duration_minimum_minutes"], "thermal duration")
    _expect_close(
        safety["encoder_stale_no_fire_after_ms"],
        gates["F_registration_and_safe_actuation"]["time_and_encoder"][
            "encoder_stale_no_fire_maximum_ms"
        ],
        "encoder stale threshold",
    )
    _expect_equal(acceptance["decision_policy"]["chemical_fire_allowed"], False, "chemical fire policy")

    capture_optics = capture["baseline_optics"]
    _expect_equal(sensor["model"], capture_optics["camera_model"], "capture camera model")
    _expect_equal(sensor["lens_model"], capture_optics["lens"]["model"], "capture lens model")
    _expect_close(sensor["pixel_pitch_um"], capture_optics["lens"]["rated_pixel_pitch_um"], "pixel pitch")
    _expect_equal(sensor["native_sensor_px"], capture_optics["roi"]["raw_sensor_px"], "raw sensor raster")

    source_bom = capture["bom_usd_excluding_tax_shipping_existing_rtx3090"]
    normalized_rows = {
        row["bom_item_id"]: row for row in config["bom_contract"]["items"]
    }
    for source_row in source_bom["items"]:
        item_id = source_row["item"]
        if item_id not in normalized_rows:
            raise CrossLaneConflictError(
                "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: "
                f"source BOM item missing from normalized BOM: {item_id}"
            )
        normalized = normalized_rows[item_id]
        _expect_close(
            normalized["minimum_cost"],
            source_row["minimum"],
            f"BOM minimum {item_id}",
        )
        _expect_close(
            normalized["maximum_cost"],
            source_row["maximum"],
            f"BOM maximum {item_id}",
        )
    _expect_close(
        config["bom_contract"]["contingency_fraction"],
        source_bom["contingency_fraction"],
        "BOM contingency fraction",
    )


DECISION_REQUIRED_FIELDS = {
    "item_id",
    "owner",
    "category",
    "decision_state",
    "value",
    "unit",
    "evidence_class",
    "source_id",
    "source_locator",
    "rationale",
    "dependency_ids",
    "resolution_trigger",
    "resolution_rule",
    "invalidation_scope",
    "claim_limit",
}


def _reject_unauthorized_true_promotions(value: Any, path: str = "contract") -> None:
    prohibited_true_keys = {
        "physical_ready",
        "physical_acceptance_pass",
        "ready",
        "field_ready",
        "field_go",
        "product_go",
        "chemical_go",
        "chemical_fire_allowed",
        "controlled_capture_authorized",
        "dry_marker_ready",
        "purchase_authorized",
        "fabrication_authorized",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in prohibited_true_keys and child is not False:
                raise ValueError(
                    f"Unauthorized readiness/status promotion at {child_path}"
                )
            _reject_unauthorized_true_promotions(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_unauthorized_true_promotions(child, f"{path}[{index}]")


def validate_schema_and_decisions(
    config: Mapping[str, Any], verified_sources: Mapping[str, Mapping[str, Any]]
) -> None:
    _reject_unauthorized_true_promotions(config)
    schema = _as_mapping(config.get("schema_contract"), "schema_contract")
    owners = set(schema["owners"])
    states = set(schema["decision_states"])
    evidence_classes = set(schema["evidence_classes"])
    expected_results = {
        "INTEGRATION_CONSISTENT_PRE_REAL",
        "INTEGRATION_INVALID_SOURCE_DRIFT",
        "INTEGRATION_INVALID_CROSS_LANE_CONFLICT",
        "REPLAN_REQUIRED",
    }
    if set(schema["integration_results"]) != expected_results:
        raise ValueError("integration_results must contain only the bounded result enum")

    items = config.get("decision_items")
    if not isinstance(items, list) or not items:
        raise ValueError("decision_items must be a non-empty list")
    item_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"decision_items[{index}] must be a mapping")
        missing = DECISION_REQUIRED_FIELDS - set(item)
        if missing:
            raise ValueError(
                f"decision item {item.get('item_id', index)!r} missing {sorted(missing)}"
            )
        item_id = str(item["item_id"])
        if item_id in item_ids:
            raise ValueError(f"Duplicate decision item_id: {item_id}")
        item_ids.add(item_id)
        if item["owner"] not in owners:
            raise ValueError(f"Unknown owner for {item_id}: {item['owner']}")
        if item["decision_state"] not in states:
            raise ValueError(
                f"Unknown decision state for {item_id}: {item['decision_state']}"
            )
        if item["evidence_class"] not in evidence_classes:
            raise ValueError(
                f"Unknown evidence class for {item_id}: {item['evidence_class']}"
            )
        if item["source_id"] not in verified_sources:
            raise ValueError(f"Unknown source_id for {item_id}: {item['source_id']}")
        if item["decision_state"] == "FROZEN_BASELINE" and item["value"] is None:
            raise ValueError(f"Frozen decision {item_id} cannot be null")
        if item["decision_state"] in {"OPEN_BENCH_VARIABLE", "HOST_UNRESOLVED"}:
            if not item["resolution_trigger"] or not item["resolution_rule"]:
                raise ValueError(
                    f"Open decision {item_id} needs a bounded trigger and rule"
                )
        if item["owner"] == "integration_only" and item["evidence_class"] not in {
            "DETERMINISTIC_CALCULATION",
            "ENGINEERING_INTEGRATION_INFERENCE",
        }:
            raise ValueError(
                f"integration_only item {item_id} cannot own a lane decision"
            )
        dependencies = item["dependency_ids"]
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)):
            raise ValueError(f"Invalid dependency list for {item_id}")

    for item in items:
        unknown = set(item["dependency_ids"]) - item_ids
        if unknown:
            raise ValueError(
                f"Decision {item['item_id']} has unknown dependencies: {sorted(unknown)}"
            )

    by_id = {str(item["item_id"]): item for item in items}
    chemical = by_id.get("chemical_enable")
    if chemical is None or chemical["decision_state"] != "UNSUPPORTED" or chemical["value"] is not False:
        raise ValueError("chemical_enable must remain UNSUPPORTED and false")
    for item_id in ("controlled_capture_authority", "dry_marker_authority"):
        item = by_id.get(item_id)
        if item is None or item["value"] is not False:
            raise ValueError(f"{item_id} must remain explicitly false")

    axes = _as_mapping(config.get("status_axes"), "status_axes")
    expected_axis_keys = {
        "architecture_selection",
        "source_integrity",
        "host_qualification",
        "physical_acceptance",
        "controlled_capture_authorized",
        "dry_marker_ready",
        "field_go",
        "product_go",
        "chemical_fire_allowed",
        "purchase_authorized",
    }
    if set(axes) != expected_axis_keys:
        raise ValueError(
            "status_axes must contain exactly the bounded independent axes; "
            f"missing={sorted(expected_axis_keys - set(axes))}, "
            f"extra={sorted(set(axes) - expected_axis_keys)}"
        )
    for flag in (
        "controlled_capture_authorized",
        "dry_marker_ready",
        "field_go",
        "product_go",
        "chemical_fire_allowed",
        "purchase_authorized",
    ):
        if axes.get(flag) is not False:
            raise ValueError(f"status_axes.{flag} must remain false")
    if axes.get("physical_acceptance") != "PRE_REAL_NOT_READY":
        raise ValueError("physical_acceptance must remain PRE_REAL_NOT_READY")

    evidence_ledger = _as_mapping(
        config.get("evidence_ledger"), "evidence_ledger"
    )
    expected_evidence_categories = {
        "sourced_facts",
        "deterministic_calculations",
        "integration_hypotheses",
        "physically_unmeasured",
        "physical_measurements",
    }
    if set(evidence_ledger) != expected_evidence_categories:
        raise ValueError(
            "evidence_ledger must distinguish sourced facts, calculations, "
            "integration hypotheses, unmeasured values, and measurements"
        )
    sourced_row = _as_mapping(
        evidence_ledger["sourced_facts"], "evidence_ledger.sourced_facts"
    )
    sourced_classes = sourced_row.get("evidence_classes")
    if sourced_classes != [
        "FROZEN_REPOSITORY_CONTRACT",
        "TERMINAL_LANE_DECISION",
    ]:
        raise ValueError("sourced_facts evidence classes changed")
    if (
        not isinstance(sourced_row.get("result_paths"), list)
        or not sourced_row["result_paths"]
        or not all(
            isinstance(path, str) and path for path in sourced_row["result_paths"]
        )
        or not sourced_row.get("claim_limit")
    ):
        raise ValueError("sourced_facts requires bounded result paths and claim limit")
    expected_class_by_category = {
        "deterministic_calculations": "DETERMINISTIC_CALCULATION",
        "integration_hypotheses": "ENGINEERING_INTEGRATION_INFERENCE",
        "physically_unmeasured": "NO_EVIDENCE_NULL",
        "physical_measurements": "PHYSICAL_MEASUREMENT",
    }
    for category, expected_class in expected_class_by_category.items():
        row = _as_mapping(evidence_ledger[category], f"evidence_ledger.{category}")
        if row.get("evidence_class") != expected_class:
            raise ValueError(f"{category} evidence class changed")
        paths = row.get("result_paths")
        if not isinstance(paths, list) or not paths or not all(
            isinstance(path, str) and path for path in paths
        ):
            raise ValueError(f"{category} requires bounded result_paths")
        if not row.get("claim_limit"):
            raise ValueError(f"{category} requires a claim_limit")
    if evidence_ledger["physical_measurements"].get(
        "current_product_receipt_count"
    ) != 0:
        raise ValueError("physical product receipt count must remain zero")


def validate_acceptance_and_fail_safe_interfaces(
    config: Mapping[str, Any],
    verified_sources: Mapping[str, Mapping[str, Any]],
) -> None:
    binding = _as_mapping(config.get("acceptance_binding"), "acceptance_binding")
    contract = verified_sources[str(binding["contract_source_id"])]
    evaluator = verified_sources[str(binding["evaluator_source_id"])]
    runbook = verified_sources[str(binding["runbook_source_id"])]
    _expect_equal(
        binding["exact_contract_sha256"],
        contract["sha256"],
        "acceptance exact-byte identity",
    )
    _expect_equal(
        binding["canonical_policy_sha256"],
        contract["canonical_sha256"],
        "acceptance canonical identity",
    )
    _expect_equal(
        binding["evaluator_sha256"],
        evaluator["sha256"],
        "acceptance evaluator identity",
    )
    if runbook["role"] != "physical_A_to_F_runbook":
        raise CrossLaneConflictError(
            "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: acceptance runbook role"
        )

    capture_target = _as_mapping(
        binding["controlled_capture_target"],
        "acceptance_binding.controlled_capture_target",
    )
    dry_target = _as_mapping(
        binding["dry_marker_target"], "acceptance_binding.dry_marker_target"
    )
    chemical_target = _as_mapping(
        binding["chemical_target"], "acceptance_binding.chemical_target"
    )
    if capture_target["current_authorized"] is not False:
        raise ValueError("controlled capture authority must remain false")
    if dry_target["current_ready"] is not False:
        raise ValueError("dry-marker readiness must remain false")
    if chemical_target["allowed"] is not False:
        raise ValueError("chemical target must remain prohibited")
    if binding["integration_evaluates_physical_receipts"] is not False:
        raise ValueError("integration cannot evaluate physical receipts")
    if binding["integration_can_override_rig_evaluator"] is not False:
        raise ValueError("integration cannot override the rig evaluator")

    rows = config.get("fail_safe_interfaces")
    if not isinstance(rows, list) or not rows:
        raise ValueError("fail_safe_interfaces must be a non-empty list")
    required_faults = set(config["baseline"]["safety"]["no_fire_on"])
    observed_faults: set[str] = set()
    valid_owners = set(config["schema_contract"]["owners"])
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("fail_safe interface rows must be mappings")
        required = {
            "fault_id",
            "owner",
            "scope",
            "immediate_action",
            "pending_command_action",
            "recovery",
        }
        missing = required - set(row)
        if missing:
            raise ValueError(f"Fail-safe row missing fields: {sorted(missing)}")
        fault_id = str(row["fault_id"])
        if fault_id in observed_faults:
            raise ValueError(f"Duplicate fail-safe fault_id: {fault_id}")
        observed_faults.add(fault_id)
        if row["owner"] not in valid_owners:
            raise ValueError(f"Unknown fail-safe owner for {fault_id}")
        action = str(row["immediate_action"])
        if "no_fire" not in action and "hard_cut" not in action:
            raise ValueError(f"Fail-safe action for {fault_id} is not fail closed")
        if not row["pending_command_action"] or not row["recovery"]:
            raise ValueError(f"Fail-safe row {fault_id} lacks cancellation/recovery")
    if observed_faults != required_faults:
        raise ValueError(
            "Fail-safe rows must exactly cover baseline no_fire_on states; "
            f"missing={sorted(required_faults - observed_faults)}, "
            f"extra={sorted(observed_faults - required_faults)}"
        )


def validate_drawing_contract(config: Mapping[str, Any]) -> None:
    spatial = _as_mapping(config.get("spatial_contract"), "spatial_contract")
    active = _as_mapping(spatial["active_geometry"], "spatial active geometry")
    baseline = _as_mapping(config["baseline"], "baseline")
    sensor = _as_mapping(baseline["sensor_optics"], "baseline.sensor_optics")
    light = _as_mapping(baseline["light_enclosure"], "baseline.light_enclosure")
    platform = _as_mapping(
        baseline["platform_carrier"], "baseline.platform_carrier"
    )
    _expect_equal(active["active_bay_count"], 1, "spatial active bay count")
    _expect_equal(
        active["hood_internal_plan_minimum_mm"],
        light["hood_internal_plan_minimum_mm"],
        "spatial hood plan",
    )
    _expect_equal(
        active["calibrated_ground_fov_range_mm"],
        [min(sensor["ground_fov_mm"]), max(sensor["ground_fov_mm"])],
        "spatial FOV range",
    )
    _expect_close(
        active["action_safe_lateral_width_minimum_mm"],
        config["golden_calculations"]["safe_width_mm"]["474"],
        "spatial safe width",
    )
    _expect_equal(
        active["outer_abstain_ring_px"],
        sensor["outer_abstain_ring_px"],
        "spatial abstain ring",
    )
    for field in (
        "intervention_footprint_mm",
        "exact_installed_optical_clearance_mm",
    ):
        _expect_equal(active[field], None, f"spatial unresolved {field}")

    envelopes = spatial.get("no_intrusion_envelopes")
    if not isinstance(envelopes, list):
        raise ValueError("no_intrusion_envelopes must be a list")
    by_envelope = {str(row["envelope_id"]): row for row in envelopes}
    if len(by_envelope) != len(envelopes):
        raise ValueError("Duplicate no-intrusion envelope ID")
    expected_envelopes = {
        "installed_calibrated_ray_cone",
        "conservative_action_safe_ground_region",
        "central_no_emitter_packaging_zone",
    }
    if set(by_envelope) != expected_envelopes:
        raise ValueError("No-intrusion envelopes must exactly match the proof set")
    ray = by_envelope["installed_calibrated_ray_cone"]
    _expect_equal(ray["exact_installed_shape_mm"], None, "installed ray cone")
    if not ray["prohibited_intruders"]:
        raise ValueError("Installed ray cone needs prohibited intruders")
    safe = by_envelope["conservative_action_safe_ground_region"]
    _expect_equal(
        safe["plan_mm"], active["conservative_action_safe_plan_mm"], "safe plan"
    )
    no_emitter = by_envelope["central_no_emitter_packaging_zone"]
    _expect_close(
        no_emitter["minimum_diameter_mm"],
        light["central_no_emitter_minimum_diameter_mm"],
        "no-emitter zone",
    )

    interfaces = config.get("interface_contract")
    if not isinstance(interfaces, list):
        raise ValueError("interface_contract must be a list")
    expected_interfaces = {
        "host_structure_to_carrier",
        "host_power_to_regulated_distribution",
        "carrier_to_removable_cassette",
        "trigger_to_camera_and_encoder_latch",
        "camera_exposureactive_to_strobe",
        "camera_to_compute_data",
        "camera_to_intervention_mount",
        "safety_to_strobe_and_intervention_enable",
    }
    by_interface: dict[str, Mapping[str, Any]] = {}
    owners = set(config["schema_contract"]["owners"])
    states = set(config["schema_contract"]["decision_states"])
    for row in interfaces:
        if not isinstance(row, Mapping):
            raise ValueError("Interface rows must be mappings")
        required = {
            "interface_id",
            "owner",
            "counterparty",
            "state",
            "value",
            "no_fire_on_invalid",
            "claim_limit",
        }
        missing = required - set(row)
        if missing:
            raise ValueError(f"Interface row missing fields: {sorted(missing)}")
        interface_id = str(row["interface_id"])
        if interface_id in by_interface:
            raise ValueError(f"Duplicate interface_id: {interface_id}")
        by_interface[interface_id] = row
        if row["owner"] not in owners or row["counterparty"] not in owners:
            raise ValueError(f"Unknown interface owner for {interface_id}")
        if row["state"] not in states:
            raise ValueError(f"Unknown interface state for {interface_id}")
        if row["no_fire_on_invalid"] is not True:
            raise ValueError(f"Interface must fail closed: {interface_id}")
        if not row["claim_limit"]:
            raise ValueError(f"Interface claim limit missing: {interface_id}")
    if set(by_interface) != expected_interfaces:
        raise ValueError("Interface IDs must exactly match the one-bay contract")
    for interface_id in (
        "host_structure_to_carrier",
        "host_power_to_regulated_distribution",
        "camera_to_intervention_mount",
    ):
        _expect_equal(
            by_interface[interface_id]["value"],
            None,
            f"unresolved interface {interface_id}",
        )
    _expect_equal(platform["exact_host"], None, "drawing exact host")
    _expect_equal(
        platform["camera_to_intervention_offset_mm"],
        None,
        "drawing intervention offset",
    )

    visual = _as_mapping(config.get("visual_contract"), "visual_contract")
    _expect_equal(visual["fixed_viewbox"], [0, 0, 1400, 900], "visual viewBox")
    _expect_equal(visual["notice"], "NOT A FABRICATION DRAWING", "visual notice")
    views = visual.get("views")
    if not isinstance(views, list):
        raise ValueError("visual_contract.views must be a list")
    expected_views = {
        "exterior": "exterior.svg",
        "underside": "underside.svg",
        "optical_cross_section": "optical_cross_section.svg",
    }
    observed_views: dict[str, str] = {}
    annotation_ids: set[str] = set()
    for row in views:
        view_id = str(row["view_id"])
        if view_id in observed_views:
            raise ValueError(f"Duplicate visual view_id: {view_id}")
        observed_views[view_id] = str(row["filename"])
        annotations = row["required_annotation_ids"]
        if (
            not isinstance(annotations, list)
            or not annotations
            or len(annotations) != len(set(annotations))
        ):
            raise ValueError(f"Invalid annotation IDs for view {view_id}")
        overlap = annotation_ids.intersection(annotations)
        if overlap:
            raise ValueError(f"Annotation IDs reused across views: {sorted(overlap)}")
        annotation_ids.update(str(item) for item in annotations)
    if observed_views != expected_views:
        raise ValueError("Visual views must exactly match the three-view package")
    deterministic = _as_mapping(
        visual["deterministic_contract"], "visual deterministic contract"
    )
    if any(value is not True for value in deterministic.values()):
        raise ValueError("Every deterministic visual guard must remain true")


def _validate_baseline_invariants(config: Mapping[str, Any]) -> None:
    baseline = _as_mapping(config["baseline"], "baseline")
    sensor = _as_mapping(baseline["sensor_optics"], "baseline.sensor_optics")
    light = _as_mapping(baseline["light_enclosure"], "baseline.light_enclosure")
    platform = _as_mapping(baseline["platform_carrier"], "baseline.platform_carrier")
    compute = _as_mapping(baseline["compute_capture"], "baseline.compute_capture")
    power = _as_mapping(baseline["power_thermal"], "baseline.power_thermal")
    safety = _as_mapping(baseline["safety"], "baseline.safety")

    _expect_equal(sensor["camera_count"], 1, "proof camera count")
    _expect_equal(sensor["model"], "a2A2464-77ucPRO", "proof camera")
    _expect_equal(sensor["lens_model"], "C23-0824-5M-P", "proof lens")
    _expect_equal(sensor["active_roi_px"], [2048, 2048], "native ROI")
    _expect_equal(sensor["acquisition_rate_hz"], 15.0, "proof acquisition rate")
    _expect_equal(sensor["outer_abstain_ring_px"], 64, "outer abstain ring")
    _expect_close(sensor["focus_plane_above_ground_mm"], 55.0, "focus plane")
    _expect_equal(
        sensor["test_planes_above_ground_mm"],
        [0.0, 55.0, 110.0],
        "optical test planes",
    )
    _expect_equal(light["hood_internal_plan_minimum_mm"], [600.0, 600.0], "proof hood plan")
    _expect_equal(light["polarization_state"], "OFF", "polarization")
    _expect_close(
        light["inner_skirt_rail_nominal_inset_mm"], 50.0, "inner skirt inset"
    )
    _expect_close(
        light["central_no_emitter_minimum_diameter_mm"],
        120.0,
        "central no-emitter diameter",
    )
    _expect_equal(
        light["quadrant_center_radius_adjustment_mm"],
        [140.0, 210.0],
        "quadrant radius adjustment",
    )
    _expect_equal(platform["proof_topology"], "manual_tractor_rear_three_point_rigid_toolbar", "proof carrier")
    multi = _as_mapping(
        platform["multi_bay_compatibility"], "multi-bay compatibility"
    )
    _expect_equal(multi["active_bay_count"], 1, "active bay count")
    _expect_equal(
        multi["multi_bay_currently_active"], False, "multi-bay active state"
    )
    _expect_equal(
        multi["second_camera_currently_active"], False, "second-camera active state"
    )
    _expect_close(multi["center_pitch_maximum_mm"], 430.0, "multi-bay pitch")
    _expect_close(multi["overlap_minimum_mm"], 10.0, "multi-bay overlap")
    _expect_equal(compute["supported_camera_count"], 1, "compute camera count")
    _expect_equal(compute["supported_rate_hz"], 15.0, "compute supported rate")
    _expect_equal(compute["stage_e_proxy_applies_to_selected_foundation"], False, "checkpoint evidence separation")
    _expect_equal(safety["chemical_enable_hardware_line"], "verified_disabled", "chemical enable line")
    for field in (
        "whole_compute_system_measured_w",
        "capture_module_transient_measured_w",
        "whole_compute_system_transient_measured_w",
        "conversion_distribution_continuous_loss_w",
        "conversion_distribution_transient_loss_w",
        "integrated_host_continuous_power_w",
        "integrated_host_transient_power_w",
    ):
        _expect_equal(power[field], None, f"pre-real power null {field}")

    frames = _as_mapping(config["coordinate_frames"], "coordinate_frames")
    required_frames = {
        "world": "F_world",
        "carrier": "F_carrier",
        "cassette": "F_cassette",
        "camera": "F_camera",
        "ground_calibration": "F_ground_calibration",
        "light_fixture": "F_light_fixture",
        "encoder": "F_encoder",
        "intervention_mount": "F_intervention_mount",
    }
    for key, frame_id in required_frames.items():
        frame = _as_mapping(frames[key], f"coordinate_frames.{key}")
        _expect_equal(frame["frame_id"], frame_id, f"frame identity {key}")
        _expect_equal(frame["z_axis"], "up_from_local_ground", f"frame +Z {key}")
    for key in (
        "world",
        "carrier",
        "cassette",
        "camera",
        "ground_calibration",
        "intervention_mount",
    ):
        frame = frames[key]
        _expect_equal(frame["x_axis"], "forward_travel", f"frame +X {key}")
        _expect_equal(frame["y_axis"], "vehicle_right", f"frame +Y {key}")
    cassette = _as_mapping(frames["cassette"], "coordinate_frames.cassette")
    fixture = _as_mapping(frames["light_fixture"], "coordinate_frames.light_fixture")
    transform = _as_mapping(
        frames["light_fixture_to_cassette"],
        "coordinate_frames.light_fixture_to_cassette",
    )
    _expect_equal(cassette["x_axis"], "forward_travel", "cassette +X")
    _expect_equal(cassette["y_axis"], "vehicle_right", "cassette +Y")
    _expect_equal(fixture["x_axis"], "vehicle_right", "light fixture +X")
    _expect_equal(fixture["y_axis"], "vehicle_front", "light fixture +Y")
    _expect_equal(transform["cassette_x_from"], "light_fixture_y", "frame X mapping")
    _expect_equal(transform["cassette_y_from"], "light_fixture_x", "frame Y mapping")
    _expect_equal(transform["cassette_z_from"], "light_fixture_z", "frame Z mapping")
    _expect_equal(
        frames["intervention_mount"]["measured_along_track_offset_mm"],
        None,
        "intervention physical offset",
    )


def safe_fraction(roi_width_px: int, outer_ring_px: int) -> float:
    if roi_width_px <= 0 or outer_ring_px < 0:
        raise ValueError("ROI width must be positive and outer ring non-negative")
    usable = roi_width_px - 2 * outer_ring_px
    if usable <= 0:
        raise ValueError("Outer abstain ring consumes the full ROI")
    return usable / roi_width_px


def raw_payload_mbit_s(
    width_px: int, height_px: int, bit_depth: int, rate_hz: float
) -> float:
    if min(width_px, height_px, bit_depth) <= 0 or rate_hz <= 0:
        raise ValueError("Transport dimensions, bit depth, and rate must be positive")
    return width_px * height_px * bit_depth * rate_hz / 1_000_000.0


def _nullable_sum(values: Iterable[Any], label: str) -> float | None:
    normalized: list[float] = []
    for index, value in enumerate(values):
        if value is None:
            return None
        normalized.append(_as_number(value, f"{label}[{index}]"))
    return sum(normalized)


def derive_mechanical_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    inputs = _as_mapping(config["calculation_inputs"], "calculation_inputs")
    model = _as_mapping(
        inputs["mechanical_payload_model"],
        "calculation_inputs.mechanical_payload_model",
    )
    gravity = _as_number(model["gravity_m_s2"], "mechanical gravity")
    if gravity <= 0:
        raise ValueError("Mechanical gravity must be positive")
    rows = model.get("components")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Mechanical payload components must be a non-empty list")
    valid_owners = set(config["schema_contract"]["owners"])
    valid_sources = {str(row["source_id"]) for row in _source_rows(config)}
    component_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Mechanical payload rows must be mappings")
        required = {
            "component_id",
            "owner",
            "source_id",
            "evidence_class",
            "required_for_payload",
            "mass_kg",
            "signed_distance_from_carrier_datum_mm",
        }
        missing = required - set(row)
        if missing:
            raise ValueError(f"Mechanical payload row missing fields: {sorted(missing)}")
        component_id = str(row["component_id"])
        if component_id in component_ids:
            raise ValueError(f"Duplicate mechanical component: {component_id}")
        component_ids.add(component_id)
        if row["owner"] not in valid_owners:
            raise ValueError(f"Unknown mechanical owner for {component_id}")
        if row["source_id"] not in valid_sources:
            raise ValueError(f"Unknown mechanical source for {component_id}")
        if not isinstance(row["required_for_payload"], bool):
            raise ValueError(
                f"required_for_payload must be boolean for {component_id}"
            )
        mass = row["mass_kg"]
        distance = row["signed_distance_from_carrier_datum_mm"]
        if mass is not None:
            mass = _as_number(mass, f"mechanical mass {component_id}")
            if mass <= 0:
                raise ValueError(
                    f"Known required mechanical mass must be positive: {component_id}"
                )
        if distance is not None:
            distance = _as_number(
                distance, f"mechanical signed distance {component_id}"
            )
        if mass is None and row["evidence_class"] != "NO_EVIDENCE_NULL":
            raise ValueError(
                f"Null mechanical mass must retain NO_EVIDENCE_NULL: {component_id}"
            )
        normalized.append(
            {
                **_json_value(row),
                "mass_kg": mass,
                "signed_distance_from_carrier_datum_mm": distance,
            }
        )

    required_rows = [row for row in normalized if row["required_for_payload"]]
    missing_mass = [
        row["component_id"] for row in required_rows if row["mass_kg"] is None
    ]
    missing_distance = [
        row["component_id"]
        for row in required_rows
        if row["signed_distance_from_carrier_datum_mm"] is None
    ]
    payload_total = _nullable_sum(
        (row["mass_kg"] for row in required_rows), "mechanical mass"
    )
    moment_terms = [
        None
        if row["mass_kg"] is None
        or row["signed_distance_from_carrier_datum_mm"] is None
        else float(row["mass_kg"])
        * gravity
        * float(row["signed_distance_from_carrier_datum_mm"])
        / 1000.0
        for row in required_rows
    ]
    moment = _nullable_sum(moment_terms, "mechanical moment")
    center_of_gravity = None
    if payload_total is not None and moment is not None:
        center_of_gravity = moment / (payload_total * gravity) * 1000.0
    by_id = {row["component_id"]: row for row in normalized}
    cassette = by_id["cassette_frame"]
    return {
        "datum": model["datum"],
        "gravity_m_s2": gravity,
        "components": normalized,
        "cassette_mass_kg": cassette["mass_kg"],
        "cassette_center_of_gravity_mm": cassette[
            "signed_distance_from_carrier_datum_mm"
        ],
        "payload_total_kg": payload_total,
        "moment_about_carrier_datum_Nm": moment,
        "center_of_gravity_from_carrier_datum_mm": center_of_gravity,
        "missing_mass_component_ids": missing_mass,
        "missing_distance_component_ids": missing_distance,
        "null_rule": (
            "any_missing_required_mass_propagates_payload_null; any_missing_"
            "required_mass_or_distance_propagates_moment_and_CG_null"
        ),
    }


def derive_power_status(config: Mapping[str, Any]) -> dict[str, Any]:
    power = dict(_json_value(config["baseline"]["power_thermal"]))
    inputs = _as_mapping(config["calculation_inputs"], "calculation_inputs")
    model = _as_mapping(
        inputs["power_aggregation_model"],
        "calculation_inputs.power_aggregation_model",
    )

    def aggregate(field_list_name: str) -> tuple[float | None, list[str]]:
        fields = model[field_list_name]
        if not isinstance(fields, list) or not fields or len(fields) != len(set(fields)):
            raise ValueError(f"{field_list_name} must be a unique non-empty list")
        unknown: list[str] = []
        values: list[Any] = []
        for field in fields:
            if field not in power:
                raise ValueError(f"Unknown power aggregation field: {field}")
            value = power[field]
            if value is None:
                unknown.append(str(field))
            else:
                value = _as_number(value, f"power input {field}")
                if value < 0:
                    raise ValueError(f"Power input cannot be negative: {field}")
            values.append(value)
        return _nullable_sum(values, field_list_name), unknown

    continuous, continuous_unknown = aggregate("continuous_required_fields")
    transient, transient_unknown = aggregate("transient_required_fields")
    evidence = _as_mapping(
        model["field_evidence_class"], "power_aggregation_model.field_evidence_class"
    )
    missing_evidence = set(power) - {
        "camera_external_supply_vdc",
        "light_bus_vdc",
        "strobe_peak_current_envelope_a",
        "thermal_duration_minimum_minutes",
        "exterior_ambient_test_c",
        "camera_housing_maximum_c",
        "led_plate_maximum_c",
        "integrated_host_continuous_power_w",
        "integrated_host_transient_power_w",
    } - set(evidence)
    if missing_evidence:
        raise ValueError(
            f"Power evidence classes missing for: {sorted(missing_evidence)}"
        )
    power["integrated_host_continuous_power_w"] = continuous
    power["integrated_host_transient_power_w"] = transient
    power["aggregation_model"] = {
        "continuous_required_fields": list(model["continuous_required_fields"]),
        "transient_required_fields": list(model["transient_required_fields"]),
        "field_evidence_class": dict(evidence),
        "continuous_missing_fields": continuous_unknown,
        "transient_missing_fields": transient_unknown,
        "null_rule": model["null_rule"],
        "claim_limit": model["claim_limit"],
    }
    return power


def derive_calculations(config: Mapping[str, Any]) -> dict[str, Any]:
    inputs = _as_mapping(config["calculation_inputs"], "calculation_inputs")
    width = int(inputs["roi_width_px"])
    height = int(inputs["roi_height_px"])
    pitch_um = _as_number(inputs["pixel_pitch_um"], "pixel_pitch_um")
    exposure_us = _as_number(inputs["exposure_us"], "exposure_us")
    ring = int(inputs["outer_abstain_ring_px"])
    fovs = [_as_number(value, "fov_samples_mm") for value in inputs["fov_samples_mm"]]
    targets = [_as_number(value, "target_sizes_mm") for value in inputs["target_sizes_mm"]]
    speeds = [_as_number(value, "speeds_m_s") for value in inputs["speeds_m_s"]]
    bit_depths = [int(value) for value in inputs["transport_bit_depths"]]
    rates = [_as_number(value, "transport_rates_hz") for value in inputs["transport_rates_hz"]]
    headroom = _as_number(inputs["transport_headroom_fraction"], "transport_headroom_fraction")
    if not 0.0 <= headroom < 1.0:
        raise ValueError("transport_headroom_fraction must be in [0, 1)")

    active_span = width * pitch_um / 1000.0
    gsd = {str(int(fov)): fov / width for fov in fovs}
    target_pixels = {
        str(int(fov)): {
            str(int(target)): target / (fov / width) for target in targets
        }
        for fov in fovs
    }
    fraction = safe_fraction(width, ring)
    safe_widths = {str(int(fov)): fov * fraction for fov in fovs}
    smear = {
        str(speed): speed * 1000.0 * exposure_us / 1_000_000.0
        for speed in speeds
    }
    blur = {
        str(speed): {
            str(int(fov)): smear[str(speed)] / gsd[str(int(fov))]
            for fov in fovs
        }
        for speed in speeds
    }

    raw_payload: dict[str, float] = {}
    payload_headroom: dict[str, float] = {}
    for bit_depth in bit_depths:
        for rate in rates:
            key = f"bayer{bit_depth}_{int(rate)}hz"
            value = raw_payload_mbit_s(width, height, bit_depth, rate)
            raw_payload[key] = value
            payload_headroom[key] = value * (1.0 + headroom)

    conservative_safe_m = min(safe_widths.values()) / 1000.0
    throughput = {
        str(speed): conservative_safe_m * speed * 0.36 for speed in speeds
    }
    compute = _as_mapping(config["baseline"]["compute_capture"], "compute")
    light = _as_mapping(config["baseline"]["light_enclosure"], "light")
    platform = _as_mapping(config["baseline"]["platform_carrier"], "platform")
    deadline = _as_number(compute["stage_e_deadline_ms"], "stage_e_deadline_ms")
    proxy_p95 = _as_number(compute["halo_batch4_p95_ms"], "halo_batch4_p95_ms")
    frame_period_ms = 1000.0 / _as_number(
        config["baseline"]["sensor_optics"]["acquisition_rate_hz"],
        "acquisition_rate_hz",
    )
    skirt_lengths = [
        _as_number(value, "skirt_length_mm") for value in light["skirt_length_mm"]
    ]
    clearances = [
        _as_number(value, "operating_clearance_mm")
        for value in light["operating_clearance_mm"]
    ]
    skirt_rail_height = [
        min(skirt_lengths) + min(clearances),
        max(skirt_lengths) + max(clearances),
    ]
    multi = _as_mapping(
        platform["multi_bay_compatibility"],
        "platform_carrier.multi_bay_compatibility",
    )
    pitch_maximum = _as_number(
        multi["center_pitch_maximum_mm"], "multi-bay pitch maximum"
    )
    one_bay_minimum = min(safe_widths.values())
    two_bay_safe = one_bay_minimum + pitch_maximum
    two_bay_hood = float(light["hood_internal_plan_minimum_mm"][0]) + pitch_maximum

    return {
        "active_sensor_span_mm": active_span,
        "gsd_mm_px": gsd,
        "target_pixels": target_pixels,
        "safe_fraction": fraction,
        "safe_width_mm": safe_widths,
        "smear_mm": smear,
        "blur_px": blur,
        "raw_payload_mbit_s": raw_payload,
        "payload_with_headroom_mbit_s": payload_headroom,
        "gross_geometric_throughput_ha_h": throughput,
        "frame_period_ms": frame_period_ms,
        "skirt_rail_height_range_mm": skirt_rail_height,
        "multi_bay_compatibility": {
            "current_active_bay_count": multi["active_bay_count"],
            "multi_bay_currently_active": multi["multi_bay_currently_active"],
            "second_camera_currently_active": multi[
                "second_camera_currently_active"
            ],
            "center_pitch_maximum_mm": pitch_maximum,
            "overlap_minimum_mm": multi["overlap_minimum_mm"],
            "one_bay_conservative_safe_swath_mm": one_bay_minimum,
            "inactive_two_bay_safe_swath_at_max_pitch_mm": two_bay_safe,
            "inactive_two_bay_continuous_hood_width_at_max_pitch_mm": two_bay_hood,
            "safe_swath_formula": multi["safe_swath_formula"],
            "continuous_hood_formula": multi["continuous_hood_formula"],
            "per_bay_independent_acceptance_required": multi[
                "per_bay_independent_acceptance_required"
            ],
            "claim_limit": multi["claim_limit"],
        },
        "compute_proxy": {
            "halo_batch4_p95_ms": proxy_p95,
            "stage_e_deadline_ms": deadline,
            "remaining_deadline_margin_ms": deadline - proxy_p95,
            "scope": "compute_proxy_not_end_to_end_physical_PASS",
        },
        "mechanical_payload": derive_mechanical_payload(config),
        "power_status": derive_power_status(config),
    }


def _verify_golden_calculations(
    config: Mapping[str, Any], calculations: Mapping[str, Any]
) -> None:
    golden = _as_mapping(config["golden_calculations"], "golden_calculations")
    tolerance = _as_number(
        golden["numeric_tolerance_absolute"], "numeric_tolerance_absolute"
    )
    if tolerance > ABS_TOL:
        raise ValueError(f"Golden tolerance {tolerance} is looser than {ABS_TOL}")

    def close(actual: Any, expected: Any, label: str) -> None:
        if not math.isclose(
            _as_number(actual, label),
            _as_number(expected, label),
            rel_tol=0.0,
            abs_tol=tolerance,
        ):
            raise CrossLaneConflictError(
                "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: "
                f"golden {label} expected {expected}, observed {actual}"
            )

    close(calculations["active_sensor_span_mm"], golden["active_sensor_span_mm"], "active sensor span")
    for key, expected in golden["gsd_mm_px"].items():
        close(calculations["gsd_mm_px"][str(key)], expected, f"GSD {key}")
    nominal = calculations["target_pixels"]["480"]
    for key, expected in golden["target_pixels_nominal_480mm"].items():
        close(nominal[str(key)], expected, f"target pixels {key} mm")
    close(calculations["safe_fraction"], golden["safe_fraction"], "safe fraction")
    for key, expected in golden["safe_width_mm"].items():
        close(calculations["safe_width_mm"][str(key)], expected, f"safe width {key}")
    for key, expected in golden["smear_mm"].items():
        close(calculations["smear_mm"][str(key)], expected, f"smear {key}")
    for key, expected in golden["blur_px_at_1m_s"].items():
        close(calculations["blur_px"]["1.0"][str(key)], expected, f"blur {key}")
    for key, expected in golden["raw_payload_mbit_s"].items():
        close(calculations["raw_payload_mbit_s"][str(key)], expected, f"payload {key}")
    for key, expected in golden["payload_with_20pct_headroom_mbit_s"].items():
        close(calculations["payload_with_headroom_mbit_s"][str(key)], expected, f"payload headroom {key}")
    for key, expected in golden["gross_geometric_throughput_ha_h"].items():
        close(calculations["gross_geometric_throughput_ha_h"][str(key)], expected, f"throughput {key}")
    for index, expected in enumerate(golden["skirt_rail_height_range_mm"]):
        close(
            calculations["skirt_rail_height_range_mm"][index],
            expected,
            f"skirt rail height {index}",
        )
    close(
        calculations["frame_period_ms"],
        golden["frame_period_ms_at_15hz"],
        "15 Hz frame period",
    )
    multi = calculations["multi_bay_compatibility"]
    close(
        multi["inactive_two_bay_safe_swath_at_max_pitch_mm"],
        golden["inactive_two_bay_safe_swath_at_max_pitch_mm"],
        "inactive two-bay safe swath",
    )
    close(
        multi["inactive_two_bay_continuous_hood_width_at_max_pitch_mm"],
        golden["inactive_two_bay_continuous_hood_width_at_max_pitch_mm"],
        "inactive two-bay hood width",
    )

    maximum_blur = max(
        value for row in calculations["blur_px"].values() for value in row.values()
    )
    maximum_allowed = _as_number(
        config["baseline"]["sensor_optics"]["maximum_blur_px"],
        "maximum_blur_px",
    )
    if maximum_blur > maximum_allowed + tolerance:
        raise CrossLaneConflictError(
            "INTEGRATION_INVALID_CROSS_LANE_CONFLICT: blur exceeds frozen gate"
        )


BOM_REQUIRED_FIELDS = {
    "bom_item_id",
    "owner",
    "cost_scope",
    "description",
    "quantity",
    "unit",
    "minimum_cost",
    "maximum_cost",
    "evidence_class",
    "source_id",
    "price_checked_on",
    "included_in_module_total",
    "included_in_integrated_total",
    "unknown_reason",
    "double_count_group",
}


def derive_bom(
    config: Mapping[str, Any],
    verified_sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    contract = _as_mapping(config.get("bom_contract"), "bom_contract")
    rows = contract.get("items")
    if not isinstance(rows, list) or not rows:
        raise ValueError("bom_contract.items must be a non-empty list")
    owners = set(config["schema_contract"]["owners"])
    evidence_classes = set(contract["cost_evidence_classes"])
    currency = str(contract["currency"])
    item_ids: set[str] = set()
    included_double_count_groups: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("BOM rows must be mappings")
        missing = BOM_REQUIRED_FIELDS - set(row)
        if missing:
            raise ValueError(f"BOM row missing fields: {sorted(missing)}")
        item_id = str(row["bom_item_id"])
        if item_id in item_ids:
            raise ValueError(f"Duplicate BOM item: {item_id}")
        item_ids.add(item_id)
        if row["owner"] not in owners:
            raise ValueError(f"Unknown BOM owner for {item_id}: {row['owner']}")
        if row["evidence_class"] not in evidence_classes:
            raise ValueError(
                f"Unknown BOM evidence class for {item_id}: {row['evidence_class']}"
            )
        if row["source_id"] not in verified_sources:
            raise ValueError(f"Unknown BOM source for {item_id}: {row['source_id']}")
        quantity = _as_number(row["quantity"], f"BOM quantity {item_id}")
        if quantity <= 0:
            raise ValueError(f"BOM quantity must be positive for {item_id}")
        minimum = row["minimum_cost"]
        maximum = row["maximum_cost"]
        if (minimum is None) != (maximum is None):
            raise ValueError(f"BOM cost range must be entirely known or null: {item_id}")
        unresolved = row["evidence_class"] == "UNRESOLVED_REQUIRED_COST"
        if unresolved:
            if minimum is not None or maximum is not None or not row["unknown_reason"]:
                raise ValueError(
                    f"Unresolved BOM item {item_id} must preserve null costs and a reason"
                )
            if row["price_checked_on"] is not None:
                raise ValueError(f"Unresolved BOM item {item_id} cannot have a price date")
        else:
            minimum = _as_number(minimum, f"BOM minimum {item_id}")
            maximum = _as_number(maximum, f"BOM maximum {item_id}")
            if minimum < 0 or maximum < minimum:
                raise ValueError(f"Invalid BOM cost range for {item_id}")
            if row["unknown_reason"] is not None:
                raise ValueError(f"Known BOM item {item_id} cannot have unknown_reason")
            if row["price_checked_on"] is None:
                raise ValueError(f"Known BOM item {item_id} needs an evidence date")
            if minimum == 0.0 and maximum == 0.0 and row["evidence_class"] != (
                "EXISTING_ASSET_INCREMENTAL_ACQUISITION_ONLY"
            ):
                raise ValueError(
                    f"Zero BOM cost is allowed only for explicit existing-asset acquisition: {item_id}"
                )

        included_module = row["included_in_module_total"]
        included_integrated = row["included_in_integrated_total"]
        if not isinstance(included_module, bool) or not isinstance(
            included_integrated, bool
        ):
            raise ValueError(f"BOM inclusion flags must be booleans: {item_id}")
        group = str(row["double_count_group"])
        if included_integrated:
            if group in included_double_count_groups:
                raise ValueError(
                    f"BOM double-count group included twice: {group}"
                )
            included_double_count_groups.add(group)

        source = verified_sources[str(row["source_id"])]
        normalized.append(
            {
                **_json_value(row),
                "currency": currency,
                "source_path": source["path"],
                "source_sha256": source["sha256"],
            }
        )

    normalized.sort(
        key=lambda row: (str(row["cost_scope"]), str(row["owner"]), row["bom_item_id"])
    )
    by_id = {row["bom_item_id"]: row for row in normalized}
    required_ids = list(contract["integrated_total_required_item_ids"])
    missing_required = set(required_ids) - set(by_id)
    if missing_required:
        raise ValueError(
            f"Integrated-total BOM items missing: {sorted(missing_required)}"
        )
    for item_id in required_ids:
        if by_id[item_id]["included_in_integrated_total"] is not True:
            raise ValueError(f"Required integrated BOM item is excluded: {item_id}")

    module_rows = [row for row in normalized if row["included_in_module_total"]]
    module_minimum_decimal = sum(
        (Decimal(str(row["minimum_cost"])) for row in module_rows), Decimal("0")
    )
    module_maximum_decimal = sum(
        (Decimal(str(row["maximum_cost"])) for row in module_rows), Decimal("0")
    )
    module_minimum = float(module_minimum_decimal)
    module_maximum = float(module_maximum_decimal)
    contingency = _as_number(
        contract["contingency_fraction"], "BOM contingency fraction"
    )
    contingency_decimal = Decimal(str(contract["contingency_fraction"]))
    module_with_contingency = [
        float(module_minimum_decimal * (Decimal("1") + contingency_decimal)),
        float(module_maximum_decimal * (Decimal("1") + contingency_decimal)),
    ]

    golden_subtotal = contract["module_subtotal_golden_usd"]
    golden_contingency = contract["module_with_contingency_golden_usd"]
    _expect_close(module_minimum, golden_subtotal[0], "module BOM minimum")
    _expect_close(module_maximum, golden_subtotal[1], "module BOM maximum")
    _expect_close(
        module_with_contingency[0],
        golden_contingency[0],
        "module BOM contingency minimum",
    )
    _expect_close(
        module_with_contingency[1],
        golden_contingency[1],
        "module BOM contingency maximum",
    )

    carrier_screen = by_id["rear_carrier_structure_engineering_screen"]
    screen_golden = contract["rear_carrier_engineering_screen_usd"]
    _expect_close(
        carrier_screen["minimum_cost"], screen_golden[0], "carrier screen minimum"
    )
    _expect_close(
        carrier_screen["maximum_cost"], screen_golden[1], "carrier screen maximum"
    )
    bounded_screen = [
        float(
            Decimal(str(module_with_contingency[0]))
            + Decimal(str(carrier_screen["minimum_cost"]))
        ),
        float(
            Decimal(str(module_with_contingency[1]))
            + Decimal(str(carrier_screen["maximum_cost"]))
        ),
    ]
    for observed, expected, label in zip(
        bounded_screen,
        contract["bounded_proof_plus_carrier_screen_golden_usd"],
        ("bounded proof screen minimum", "bounded proof screen maximum"),
    ):
        _expect_close(observed, expected, label)

    blockers = [
        {
            "bom_item_id": item_id,
            "reason": by_id[item_id]["unknown_reason"],
        }
        for item_id in required_ids
        if by_id[item_id]["minimum_cost"] is None
        or by_id[item_id]["maximum_cost"] is None
    ]
    for group in contract["pending_double_count_reconciliation_groups"]:
        blockers.append(
            {
                "double_count_group": group,
                "reason": "source_allowance_overlap_requires_line_by_line_quote_reconciliation",
            }
        )
    integrated_total = None
    if not blockers:
        additions = [by_id[item_id] for item_id in required_ids]
        integrated_total = [
            float(
                Decimal(str(module_with_contingency[0]))
                + sum(
                    (Decimal(str(row["minimum_cost"])) for row in additions),
                    Decimal("0"),
                )
            ),
            float(
                Decimal(str(module_with_contingency[1]))
                + sum(
                    (Decimal(str(row["maximum_cost"])) for row in additions),
                    Decimal("0"),
                )
            ),
        ]

    return {
        "currency": currency,
        "price_evidence_date": str(contract["price_evidence_date"]),
        "items": normalized,
        "totals": {
            "proof_module_before_contingency": [module_minimum, module_maximum],
            "contingency_fraction": contingency,
            "proof_module_with_contingency": module_with_contingency,
            "rear_carrier_engineering_screen_not_quote": [
                float(carrier_screen["minimum_cost"]),
                float(carrier_screen["maximum_cost"]),
            ],
            "bounded_proof_plus_carrier_screen_not_integrated_total": bounded_screen,
            "integrated_one_bay_total": integrated_total,
            "integrated_total_complete": integrated_total is not None,
            "integrated_total_blockers": blockers,
        },
        "forbidden_benefit_credits": list(contract["benefit_credits_forbidden"]),
        "claim_limit": (
            "module values are dated budgetary evidence; carrier screen is not a "
            "quote; integrated total remains null until every required cost and "
            "overlap reconciliation is complete"
        ),
    }


BOM_CSV_FIELDS = [
    "bom_item_id",
    "owner",
    "cost_scope",
    "description",
    "quantity",
    "unit",
    "minimum_cost",
    "maximum_cost",
    "currency",
    "evidence_class",
    "source_id",
    "source_path",
    "source_sha256",
    "price_checked_on",
    "included_in_module_total",
    "included_in_integrated_total",
    "unknown_reason",
    "double_count_group",
]


def _csv_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    return value


def render_bom_csv(bom: Mapping[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=BOM_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in bom["items"]:
        writer.writerow({field: _csv_scalar(row.get(field)) for field in BOM_CSV_FIELDS})
    return buffer.getvalue()


SVG_STYLE = """
    .bg { fill: #f7fafc; }
    .grid { stroke: #d9e3ec; stroke-width: 1; }
    .panel { fill: #ffffff; stroke: #9fb2c4; stroke-width: 1.5; }
    .ink { fill: none; stroke: #17324d; stroke-width: 3; }
    .thin { fill: none; stroke: #48657e; stroke-width: 1.5; }
    .muted { fill: none; stroke: #8498aa; stroke-width: 2; }
    .dashed { stroke-dasharray: 9 7; }
    .unresolved { fill: #fff8e6; stroke: #d28a00; stroke-width: 2.5; stroke-dasharray: 8 6; }
    .selected { fill: #e8f5f2; stroke: #087f6d; stroke-width: 3; }
    .safe { fill: #36b59b; fill-opacity: 0.18; stroke: #087f6d; stroke-width: 3; }
    .optical { fill: #58a6ff; fill-opacity: 0.10; stroke: #1673bd; stroke-width: 2.5; }
    .light { fill: #fff1a8; stroke: #c98b00; stroke-width: 2; }
    .fault { fill: #fff0f0; stroke: #bd2d2d; stroke-width: 2; }
    .disabled { fill: #f4f5f7; stroke: #6f7782; stroke-width: 2; }
    .dimension { fill: none; stroke: #8b3fd1; stroke-width: 1.8; marker-start: url(#dim-arrow); marker-end: url(#dim-arrow); }
    .flow { fill: none; stroke: #087f6d; stroke-width: 2.2; marker-end: url(#flow-arrow); }
    .fault-flow { fill: none; stroke: #bd2d2d; stroke-width: 2.2; marker-end: url(#flow-arrow-red); }
    text { font-family: Inter, 'DejaVu Sans', Arial, sans-serif; fill: #17324d; }
    .title { font-size: 27px; font-weight: 700; letter-spacing: 0.2px; }
    .subtitle { font-size: 13px; font-weight: 600; fill: #48657e; letter-spacing: 0.8px; }
    .section { font-size: 18px; font-weight: 700; }
    .label { font-size: 14px; font-weight: 600; }
    .small { font-size: 12px; fill: #48657e; }
    .tiny { font-size: 10.5px; fill: #48657e; }
    .mono { font-family: 'DejaVu Sans Mono', monospace; font-size: 10px; fill: #48657e; }
    .chip { font-size: 11px; font-weight: 700; letter-spacing: 0.45px; }
    .warning { fill: #a36300; font-weight: 700; }
    .danger { fill: #a11e1e; font-weight: 700; }
""".strip()


def _format_dimension(value: Any, maximum_decimals: int = 3) -> str:
    number = _as_number(value, "visual dimension")
    if math.isclose(number, round(number), rel_tol=0.0, abs_tol=1e-12):
        return str(int(round(number)))
    return f"{number:.{maximum_decimals}f}".rstrip("0").rstrip(".")


def _svg_annotation(annotation_id: str, content: str) -> str:
    escaped = html.escape(annotation_id, quote=True)
    return (
        f'<g id="annotation-{escaped}" data-annotation-id="{escaped}">'
        f"{content}</g>"
    )


def _visual_row(result: Mapping[str, Any], view_id: str) -> Mapping[str, Any]:
    rows = result["visual_contract"]["views"]
    matches = [row for row in rows if row["view_id"] == view_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one visual contract row for {view_id}")
    return matches[0]


def _svg_shell(
    result: Mapping[str, Any],
    architecture_sha256: str,
    view_id: str,
    body: str,
) -> str:
    if not SHA256_RE.fullmatch(architecture_sha256):
        raise ValueError("Architecture result SHA-256 is invalid")
    row = _visual_row(result, view_id)
    title = str(row["title"])
    config_sha256 = str(result["config_identity"]["sha256"])
    if not SHA256_RE.fullmatch(config_sha256):
        raise ValueError("Config SHA-256 is invalid for visual generation")
    viewbox = " ".join(str(value) for value in result["visual_contract"]["fixed_viewbox"])
    status = result["status_axes"]
    metadata = html.escape(
        json.dumps(
            {
                "architecture_sha256": architecture_sha256,
                "config_sha256": config_sha256,
                "contract_id": result["contract_id"],
                "source_integrity": result["source_integrity"]["status"],
                "view_id": view_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    escaped_title = html.escape(title)
    notice = html.escape(str(result["visual_contract"]["notice"]))
    payload = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" aria-labelledby="title-{view_id} desc-{view_id}" data-view-id="{view_id}" data-config-sha256="{config_sha256}" data-architecture-sha256="{architecture_sha256}">
  <title id="title-{view_id}">{escaped_title}</title>
  <desc id="desc-{view_id}">Source-bound schematic of the frozen one-bay proof architecture. It is pre-real, not physically accepted, and not a fabrication drawing.</desc>
  <metadata>{metadata}</metadata>
  <defs>
    <pattern id="minor-grid" width="25" height="25" patternUnits="userSpaceOnUse"><path d="M 25 0 L 0 0 0 25" class="grid" fill="none"/></pattern>
    <marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#087f6d"/></marker>
    <marker id="flow-arrow-red" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#bd2d2d"/></marker>
    <marker id="dim-arrow" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0,3.5 L7,0 L7,7 Z" fill="#8b3fd1"/></marker>
    <style>{SVG_STYLE}</style>
  </defs>
  <rect width="1400" height="900" class="bg"/>
  <rect x="0" y="96" width="1400" height="714" fill="url(#minor-grid)" opacity="0.58"/>
  <g id="header">
    <text x="38" y="43" class="title">{escaped_title}</text>
    <text x="40" y="70" class="subtitle">ONE-BAY PROOF · ARCHITECTURE FROZEN · SOURCE INTEGRITY {html.escape(str(result['source_integrity']['status']))}</text>
    <rect x="1008" y="24" width="112" height="28" rx="14" class="selected"/><text x="1064" y="43" text-anchor="middle" class="chip">ONE BAY</text>
    <rect x="1132" y="24" width="116" height="28" rx="14" class="unresolved"/><text x="1190" y="43" text-anchor="middle" class="chip">HOST OPEN</text>
    <rect x="1260" y="24" width="106" height="28" rx="14" class="fault"/><text x="1313" y="43" text-anchor="middle" class="chip">NO FIRE</text>
    <text x="1365" y="70" text-anchor="end" class="small">physical: {html.escape(str(status['physical_acceptance']))}</text>
  </g>
  {body}
  <g id="footer">
    <rect x="0" y="810" width="1400" height="90" fill="#17324d"/>
    <text x="38" y="839" fill="#ffffff" style="font-size:14px;font-weight:700">{notice} · NOT TO SCALE · SCHEMATIC ENVELOPES ONLY</text>
    <text x="38" y="862" class="mono" style="fill:#dbe8f2">config sha256: {config_sha256}</text>
    <text x="38" y="881" class="mono" style="fill:#dbe8f2">architecture sha256: {architecture_sha256}</text>
    <text x="1362" y="862" text-anchor="end" fill="#ffffff" style="font-size:12px">controlled capture: false · dry marker: false</text>
    <text x="1362" y="881" text-anchor="end" fill="#ffffff" style="font-size:12px">field GO: false · chemical fire: false</text>
  </g>
</svg>
"""
    return "\n".join(line.rstrip() for line in payload.splitlines()) + "\n"


def _render_exterior_svg(
    result: Mapping[str, Any], architecture_sha256: str
) -> str:
    baseline = result["baseline"]
    sensor = baseline["sensor_optics"]
    light = baseline["light_enclosure"]
    platform = baseline["platform_carrier"]
    power = result["calculations"]["power_status"]
    speed = "–".join(_format_dimension(value, 1) for value in platform["trial_speeds_m_s"])
    hood = "×".join(_format_dimension(value) for value in light["hood_internal_plan_minimum_mm"])
    wd = "–".join(_format_dimension(value) for value in sensor["working_distance_adjustment_mm"])
    skirt = "–".join(_format_dimension(value) for value in light["skirt_length_mm"])
    clearance = "–".join(
        _format_dimension(value) for value in light["operating_clearance_mm"]
    )
    body = f"""
  <g id="exterior-main">
    <rect x="35" y="118" width="925" height="664" rx="12" class="panel"/>
    <text x="60" y="151" class="section">SIDE / EXTERIOR SCHEMATIC</text>
    <text x="60" y="174" class="small">+X forward travel · host-specific structure deliberately unresolved</text>
    <line x1="70" y1="724" x2="930" y2="724" class="ink"/>
    <text x="76" y="748" class="small">local ground / F_world</text>
    <line x1="160" y1="206" x2="310" y2="206" class="flow"/><text x="165" y="196" class="label">+X forward · {speed} m/s proof</text>

    {_svg_annotation('host_unresolved', '''
      <path d="M92 475 L132 360 L318 336 L383 423 L374 580 L116 580 Z" class="unresolved"/>
      <circle cx="163" cy="592" r="75" class="unresolved"/><circle cx="330" cy="602" r="48" class="unresolved"/>
      <text x="232" y="401" text-anchor="middle" class="label warning">EXACT REAR HOST</text>
      <text x="232" y="423" text-anchor="middle" class="label warning">UNRESOLVED</text>
      <text x="232" y="450" text-anchor="middle" class="small">hitch · ballast · axle · visibility</text>
      <text x="232" y="469" text-anchor="middle" class="small">power · cable · speed evidence = null</text>
    ''')}
    {_svg_annotation('rear_three_point', '''
      <path d="M375 448 L461 388 L465 547 L377 524" class="ink"/>
      <circle cx="462" cy="389" r="7" class="selected"/><circle cx="465" cy="547" r="7" class="selected"/>
      <text x="411" y="370" class="label">rear three-point</text>
      <text x="411" y="390" class="small">proof topology selected</text>
    ''')}
    <g id="carrier-frame">
      <rect x="453" y="315" width="417" height="34" rx="6" class="ink"/>
      <text x="661" y="388" text-anchor="middle" class="label">carrier toolbar · rating unresolved</text>
    </g>
    {_svg_annotation('compute_tray', f'''
      <rect x="493" y="250" width="212" height="54" rx="8" class="unresolved"/>
      <text x="599" y="273" text-anchor="middle" class="label">compute / power tray</text>
      <text x="599" y="292" text-anchor="middle" class="small">whole-system input: UNRESOLVED</text>
      <path d="M705 277 L775 277 L775 398" class="thin dashed"/>
    ''')}
    {_svg_annotation('ground_follow', '''
      <path d="M648 349 L608 430 L608 568 M705 349 L745 430 L745 568" class="ink"/>
      <rect x="583" y="422" width="188" height="28" rx="7" class="selected"/>
      <text x="676" y="414" text-anchor="middle" class="label">passive ground following</text>
      <text x="676" y="471" text-anchor="middle" class="small">carrier owns coarse height and guide</text>
    ''')}
    {_svg_annotation('removable_cassette', f'''
      <rect x="545" y="488" width="265" height="178" rx="8" class="selected"/>
      <rect x="574" y="512" width="207" height="110" class="ink"/>
      <path d="M585 622 L585 690 M615 622 L615 690 M741 622 L741 690 M771 622 L771 690" class="muted"/>
      <circle cx="677" cy="540" r="18" class="optical"/>
      <text x="677" y="572" text-anchor="middle" class="label">REMOVABLE ONE-BAY CASSETTE</text>
      <text x="677" y="594" text-anchor="middle" class="small">hood internal plan ≥ {hood} mm</text>
      <text x="677" y="646" text-anchor="middle" class="small">dual skirts {skirt} mm · clearance {clearance} mm</text>
    ''')}
    <line x1="825" y1="540" x2="825" y2="724" class="dimension"/>
    <text x="925" y="617" text-anchor="end" class="label">WD {wd} mm</text>
    <text x="925" y="638" text-anchor="end" class="small">unit-adjusted and locked</text>
    {_svg_annotation('gauge_wheel', '''
      <path d="M812 420 L888 477 L888 627" class="ink"/>
      <circle cx="888" cy="674" r="48" class="ink"/>
      <text x="925" y="404" text-anchor="end" class="label">gauge wheel</text>
      <text x="925" y="425" text-anchor="end" class="small">outside optical/action envelope</text>
    ''')}
    {_svg_annotation('encoder', '''
      <circle cx="888" cy="674" r="14" class="selected"/>
      <path d="M903 650 L930 626" class="thin"/>
      <text x="930" y="704" text-anchor="end" class="label">F_encoder · signed ground travel</text>
    ''')}
    {_svg_annotation('intervention_offset_unresolved', '''
      <path d="M704 690 L704 730 M684 710 L724 710" class="fault-flow"/>
      <text x="496" y="748" class="label warning">F_intervention_mount: rigid datum only</text>
      <text x="496" y="770" class="small">signed camera offset = UNRESOLVED · hardware / footprint = null</text>
    ''')}
    {_svg_annotation('deployed_state', '''
      <rect x="458" y="571" width="82" height="48" rx="7" class="fault"/>
      <text x="499" y="590" text-anchor="middle" class="label danger">STATE</text>
      <text x="499" y="608" text-anchor="middle" class="small">lift/lock/deploy</text>
      <path d="M540 595 L577 595" class="fault-flow"/>
    ''')}
  </g>
  <g id="exterior-contract-panel">
    <rect x="985" y="118" width="380" height="664" rx="12" class="panel"/>
    <text x="1012" y="151" class="section">BUILD / CONTROL BOUNDARY</text>
    <text x="1012" y="184" class="label">Frozen cassette</text>
    <text x="1028" y="208" class="small">• {html.escape(sensor['model'])} + {html.escape(sensor['lens_model'])}</text>
    <text x="1028" y="230" class="small">• native 2048×2048 ROI · {sensor['acquisition_rate_hz']:.0f} Hz</text>
    <text x="1028" y="252" class="small">• four diffuse white quadrants · polarization OFF</text>
    <text x="1028" y="274" class="small">• local camera-to-intervention rigid frame</text>
    <line x1="1012" y1="294" x2="1338" y2="294" class="grid"/>
    <text x="1012" y="326" class="label">Carrier owns</text>
    <text x="1028" y="350" class="small">• hitch, toolbar, ground following, gauge wheel</text>
    <text x="1028" y="372" class="small">• signed encoder, lift/transport and deployed state</text>
    <text x="1028" y="394" class="small">• host power conversion and E-stop route</text>
    <line x1="1012" y1="414" x2="1338" y2="414" class="grid"/>
    <text x="1012" y="446" class="label">Known electrical boundaries</text>
    <text x="1028" y="470" class="small">capture module ≤ {power['capture_module_average_maximum_w_excluding_compute']:.0f} W average (no compute)</text>
    <text x="1028" y="492" class="small">light branch ≤ {power['light_branch_average_maximum_w']:.0f} W average</text>
    <text x="1028" y="514" class="small">GPU {power['gpu_reference_board_power_w_not_vehicle_draw']:.0f} W = reference only</text>
    <text x="1028" y="536" class="small">host continuous / transient input = UNRESOLVED</text>
    <line x1="1012" y1="556" x2="1338" y2="556" class="grid"/>
    <rect x="1012" y="578" width="326" height="86" rx="8" class="fault"/>
    <text x="1175" y="605" text-anchor="middle" class="label danger">DEFAULT = NO FIRE</text>
    <text x="1175" y="629" text-anchor="middle" class="small">invalid host / lift / reverse / encoder / power</text>
    <text x="1175" y="648" text-anchor="middle" class="small">cancels pending commands; clean witness required</text>
    <rect x="1012" y="686" width="326" height="69" rx="8" class="unresolved"/>
    <text x="1175" y="713" text-anchor="middle" class="label warning">NO BUILD OR PROCUREMENT AUTHORITY</text>
    <text x="1175" y="737" text-anchor="middle" class="small">mass · CG · rating · exact cost remain null</text>
  </g>"""
    return _svg_shell(result, architecture_sha256, "exterior", body)


def _render_underside_svg(
    result: Mapping[str, Any], architecture_sha256: str
) -> str:
    baseline = result["baseline"]
    sensor = baseline["sensor_optics"]
    light = baseline["light_enclosure"]
    calc = result["calculations"]
    hood_width = float(light["hood_internal_plan_minimum_mm"][0])
    drawing_scale = 0.86
    center_x, center_y = 390.0, 475.0
    hood_draw = hood_width * drawing_scale
    hood_x, hood_y = center_x - hood_draw / 2.0, center_y - hood_draw / 2.0
    fov_min = min(float(value) for value in sensor["ground_fov_mm"])
    fov_max = max(float(value) for value in sensor["ground_fov_mm"])
    safe_min = min(float(value) for value in calc["safe_width_mm"].values())
    inner_inset = float(light["inner_skirt_rail_nominal_inset_mm"])
    no_emitter = float(light["central_no_emitter_minimum_diameter_mm"])
    def square(size: float) -> tuple[float, float]:
        drawn = size * drawing_scale
        return center_x - drawn / 2.0, center_y - drawn / 2.0
    fov_max_draw = fov_max * drawing_scale
    fov_min_draw = fov_min * drawing_scale
    safe_draw = safe_min * drawing_scale
    inner_inset_draw = inner_inset * drawing_scale
    no_emitter_draw = no_emitter * drawing_scale
    fov_max_x, fov_max_y = square(fov_max)
    fov_min_x, fov_min_y = square(fov_min)
    safe_x, safe_y = square(safe_min)
    body = f"""
  <g id="underside-main">
    <rect x="35" y="118" width="735" height="664" rx="12" class="panel"/>
    <text x="60" y="151" class="section">UNDERSIDE / GROUND-PLANE PROJECTION</text>
    <text x="60" y="174" class="small">cassette frame: +X forward (up) · +Y vehicle right</text>
    {_svg_annotation('hood_600', f'''
      <rect x="{hood_x:.3f}" y="{hood_y:.3f}" width="{hood_draw:.3f}" height="{hood_draw:.3f}" class="ink"/>
      <text x="{center_x:.3f}" y="{hood_y - 16:.3f}" text-anchor="middle" class="label">minimum clear hood: {hood_width:.0f}×{hood_width:.0f} mm</text>
      <rect x="{hood_x + inner_inset_draw:.3f}" y="{hood_y + inner_inset_draw:.3f}" width="{hood_draw - 2 * inner_inset_draw:.3f}" height="{hood_draw - 2 * inner_inset_draw:.3f}" class="muted dashed"/>
      <text x="{hood_x + 8:.3f}" y="{hood_y + hood_draw + 18:.3f}" class="tiny">outer skirt rail</text>
      <text x="{hood_x + inner_inset_draw + 8:.3f}" y="{hood_y + hood_draw - 19:.3f}" class="tiny">inner rail nominal inset {inner_inset:.0f} mm</text>
    ''')}
    {_svg_annotation('four_quadrants', f'''
      <g class="light"><rect x="335" y="285" width="110" height="74" rx="12"/><rect x="335" y="590" width="110" height="74" rx="12"/><rect x="166" y="438" width="110" height="74" rx="12"/><rect x="504" y="438" width="110" height="74" rx="12"/></g>
      <text x="390" y="315" text-anchor="middle" class="label">Q_FRONT</text><text x="390" y="339" text-anchor="middle" class="small">diffuse white</text>
      <text x="390" y="620" text-anchor="middle" class="label">Q_REAR</text><text x="390" y="644" text-anchor="middle" class="small">diffuse white</text>
      <text x="221" y="470" text-anchor="middle" class="label">Q_LEFT</text><text x="221" y="494" text-anchor="middle" class="small">diffuse white</text>
      <text x="559" y="470" text-anchor="middle" class="label">Q_RIGHT</text><text x="559" y="494" text-anchor="middle" class="small">diffuse white</text>
    ''')}
    {_svg_annotation('no_emitter_zone', f'''
      <circle cx="{center_x:.3f}" cy="{center_y:.3f}" r="{no_emitter_draw / 2.0:.3f}" class="disabled"/>
      <circle cx="{center_x:.3f}" cy="{center_y:.3f}" r="18" class="optical"/>
      <line x1="{center_x - 27:.3f}" y1="{center_y:.3f}" x2="{center_x + 27:.3f}" y2="{center_y:.3f}" class="thin"/><line x1="{center_x:.3f}" y1="{center_y - 27:.3f}" x2="{center_x:.3f}" y2="{center_y + 27:.3f}" class="thin"/>
      <text x="{center_x:.3f}" y="{center_y + 73:.3f}" text-anchor="middle" class="small">central no-emitter zone ≥ Ø{no_emitter:.0f} mm</text>
      <text x="{center_x:.3f}" y="{center_y + 91:.3f}" text-anchor="middle" class="tiny">camera optical axis / isolated window bay</text>
    ''')}
    {_svg_annotation('fov_range', f'''
      <rect x="{fov_max_x:.3f}" y="{fov_max_y:.3f}" width="{fov_max_draw:.3f}" height="{fov_max_draw:.3f}" class="optical"/>
      <rect x="{fov_min_x:.3f}" y="{fov_min_y:.3f}" width="{fov_min_draw:.3f}" height="{fov_min_draw:.3f}" class="thin dashed"/>
    ''')}
    {_svg_annotation('safe_region_444_375', f'''
      <rect x="{safe_x:.3f}" y="{safe_y:.3f}" width="{safe_draw:.3f}" height="{safe_draw:.3f}" class="safe"/>
      <text x="{center_x:.3f}" y="{center_y - 82:.3f}" text-anchor="middle" class="label">ACTION-SAFE REGION</text>
      <text x="{center_x:.3f}" y="{center_y - 60:.3f}" text-anchor="middle" class="label">minimum {safe_min:.3f} × {safe_min:.3f} mm</text>
      <text x="{center_x:.3f}" y="{center_y - 38:.3f}" text-anchor="middle" class="small">not hood width · not nozzle footprint</text>
    ''')}
    {_svg_annotation('abstain_ring', f'''
      <path d="M {fov_min_x:.3f} {fov_min_y:.3f} H {fov_min_x + fov_min_draw:.3f} V {fov_min_y + fov_min_draw:.3f} H {fov_min_x:.3f} Z M {safe_x:.3f} {safe_y:.3f} H {safe_x + safe_draw:.3f} V {safe_y + safe_draw:.3f} H {safe_x:.3f} Z" fill="#8b3fd1" fill-opacity="0.10" fill-rule="evenodd" stroke="none"/>
      <path d="M {fov_max_x:.3f} {fov_max_y - 8:.3f} H {fov_max_x + fov_max_draw:.3f}" class="dimension"/>
      <text x="{center_x:.3f}" y="{fov_max_y - 18:.3f}" text-anchor="middle" class="label">measured FOV {fov_min:.0f}–{fov_max:.0f} mm</text>
      <text x="{center_x:.3f}" y="{safe_y + safe_draw + 22:.3f}" text-anchor="middle" class="label">64 px abstain ring per ROI edge</text>
    ''')}
    {_svg_annotation('no_intrusion', f'''
      <path d="M {safe_x:.3f} {safe_y + 40:.3f} L 110 {safe_y + 40:.3f} L 110 {safe_y + 86:.3f}" class="fault-flow"/>
      <rect x="52" y="330" width="206" height="72" rx="7" fill="#ffffff" stroke="#bd2d2d" stroke-width="1.5"/>
      <text x="66" y="353" class="label danger">NO INTRUSION</text>
      <text x="66" y="375" class="tiny">wall · skirt · baffle · cable · carrier · wheel</text>
      <text x="66" y="392" class="tiny">ray clearance = UNMEASURED</text>
    ''')}
    <g id="underside-axes">
      <line x1="704" y1="700" x2="704" y2="618" class="flow"/><text x="704" y="603" text-anchor="middle" class="label">+X forward</text>
      <line x1="704" y1="700" x2="752" y2="700" class="flow"/><text x="739" y="722" text-anchor="middle" class="label">+Y right</text>
    </g>
  </g>
  <g id="underside-contract-panel">
    <rect x="795" y="118" width="570" height="664" rx="12" class="panel"/>
    <text x="824" y="151" class="section">GEOMETRY LEDGER</text>
    <rect x="824" y="178" width="512" height="115" rx="9" class="selected"/>
    <text x="848" y="208" class="label">Three different boundaries</text>
    <text x="848" y="234" class="small">hood internal plan: {hood_width:.0f}×{hood_width:.0f} mm · enclosure only</text>
    <text x="848" y="257" class="small">calibrated FOV: {fov_min:.0f}–{fov_max:.0f} mm · physically measured range</text>
    <text x="848" y="280" class="small">safe action width: ≥{safe_min:.3f} mm · throughput basis</text>
    <text x="824" y="329" class="label">ROI derivation</text>
    <text x="844" y="355" class="small">native ROI: {sensor['active_roi_px'][0]}×{sensor['active_roi_px'][1]} px</text>
    <text x="844" y="379" class="small">usable: {sensor['active_roi_px'][0] - 2 * sensor['outer_abstain_ring_px']} px / axis</text>
    <text x="844" y="403" class="small">safe fraction: {calc['safe_fraction']:.4f}</text>
    <text x="844" y="427" class="small">minimum GSD: {calc['gsd_mm_px']['474']:.6f} mm/px</text>
    <line x1="824" y1="449" x2="1336" y2="449" class="grid"/>
    {_svg_annotation('axis_permutation', '''
      <text x="824" y="482" class="label">Explicit source-frame reconciliation</text>
      <text x="844" y="508" class="small">cassette +X forward ← light-fixture +Y front</text>
      <text x="844" y="532" class="small">cassette +Y right ← light-fixture +X right</text>
      <text x="844" y="556" class="small">+Z unchanged · no scale · no reflection</text>
    ''')}
    <line x1="824" y1="578" x2="1336" y2="578" class="grid"/>
    <text x="824" y="611" class="label">Inactive multi-bay compatibility</text>
    <text x="844" y="637" class="small">active bays = 1 · second camera = false</text>
    <text x="844" y="661" class="small">pitch ≤{calc['multi_bay_compatibility']['center_pitch_maximum_mm']:.0f} mm · overlap ≥{calc['multi_bay_compatibility']['overlap_minimum_mm']:.0f} mm</text>
    <text x="844" y="685" class="small">two-bay formula screen: {calc['multi_bay_compatibility']['inactive_two_bay_safe_swath_at_max_pitch_mm']:.3f} mm</text>
    <text x="844" y="709" class="small">not current capability · each bay and overlap must pass</text>
    <rect x="824" y="731" width="512" height="34" rx="7" class="fault"/>
    <text x="1080" y="753" text-anchor="middle" class="label danger">Stage C alone owns physical non-occlusion</text>
  </g>"""
    return _svg_shell(result, architecture_sha256, "underside", body)


def _render_optical_cross_section_svg(
    result: Mapping[str, Any], architecture_sha256: str
) -> str:
    baseline = result["baseline"]
    sensor = baseline["sensor_optics"]
    light = baseline["light_enclosure"]
    compute = baseline["compute_capture"]
    calc = result["calculations"]
    wd = "–".join(_format_dimension(value) for value in sensor["working_distance_adjustment_mm"])
    window_thickness = "–".join(_format_dimension(value) for value in light["window_thickness_mm"])
    window_tilt = "–".join(_format_dimension(value) for value in light["window_tilt_deg"])
    skirt = "–".join(_format_dimension(value) for value in light["skirt_length_mm"])
    rail = "–".join(_format_dimension(value) for value in calc["skirt_rail_height_range_mm"])
    clearance = "–".join(
        _format_dimension(value) for value in light["operating_clearance_mm"]
    )
    planes = [
        _format_dimension(value) for value in sensor["test_planes_above_ground_mm"]
    ]
    fov_range = (
        f"{_format_dimension(min(sensor['ground_fov_mm']))}–"
        f"{_format_dimension(max(sensor['ground_fov_mm']))}"
    )
    safe_width = _format_dimension(min(calc["safe_width_mm"].values()))
    body = f"""
  <g id="cross-section-main">
    <rect x="35" y="118" width="790" height="664" rx="12" class="panel"/>
    <text x="60" y="151" class="section">OPTICAL CROSS-SECTION · NOMINAL POSE</text>
    <text x="60" y="174" class="small">vertical layout uses a nominal schematic pose inside the bounded WD; labels carry the contract</text>
    <line x1="70" y1="720" x2="790" y2="720" class="ink"/>
    {_svg_annotation('test_planes', f'''
      <line x1="92" y1="665" x2="730" y2="665" class="muted dashed"/>
      <line x1="92" y1="610" x2="730" y2="610" class="muted dashed"/>
      <text x="82" y="724" text-anchor="end" class="label">{planes[0]} mm</text>
      <text x="82" y="669" text-anchor="end" class="label">{planes[1]} mm</text>
      <text x="82" y="614" text-anchor="end" class="label">{planes[2]} mm</text>
      <text x="112" y="702" class="small">local ground</text>
      <text x="112" y="647" class="small">focus plane</text>
      <text x="112" y="592" class="small">upper test plane</text>
    ''')}
    <g id="hood-section">
      <path d="M130 278 L130 570 L690 570 L690 278" class="ink"/>
      <path d="M130 278 L300 278 M520 278 L690 278" class="ink"/>
      <rect x="132" y="286" width="556" height="24" class="disabled"/>
      <text x="410" y="268" text-anchor="middle" class="label">rigid matte hood · passive sealed thermal path</text>
      <path d="M190 278 L190 230 L260 230" class="thin"/><path d="M630 278 L630 230 L560 230" class="thin"/>
      <text x="225" y="252" text-anchor="middle" class="small">external heatsink</text>
      <text x="595" y="252" text-anchor="middle" class="small">sealed path · no optical airflow</text>
    </g>
    <g id="camera-section">
      <rect x="354" y="184" width="112" height="64" rx="9" class="selected"/>
      <path d="M382 248 L382 275 L438 275 L438 248" class="ink"/>
      <circle cx="410" cy="278" r="9" class="optical"/>
      <text x="410" y="207" text-anchor="middle" class="label">{html.escape(sensor['model'])}</text>
      <text x="410" y="227" text-anchor="middle" class="small">{html.escape(sensor['lens_model'])} · f/{sensor['aperture_f_number']}</text>
      <text x="410" y="246" text-anchor="middle" class="small">F_camera · optical axis −Z</text>
    </g>
    {_svg_annotation('window', f'''
      <path d="M319 334 L501 318" stroke="#1673bd" stroke-width="8" opacity="0.48"/>
      <text x="516" y="322" class="label">AR window {window_thickness} mm</text>
      <text x="516" y="342" class="small">installed tilt {window_tilt}° · exact part/profile open</text>
    ''')}
    <g id="light-section">
      <path d="M174 366 L290 334 L310 388 L194 420 Z" class="light"/>
      <path d="M646 366 L530 334 L510 388 L626 420 Z" class="light"/>
      <text x="236" y="383" text-anchor="middle" class="small">diffuse quadrant</text>
      <text x="584" y="383" text-anchor="middle" class="small">diffuse quadrant</text>
      <path d="M290 368 L399 472 M530 368 L421 472" class="thin dashed"/>
    </g>
    {_svg_annotation('ray_cone', f'''
      <path d="M410 282 L168 720 L652 720 Z" class="optical"/>
      <line x1="410" y1="282" x2="410" y2="720" class="thin dashed"/>
      <line x1="188" y1="706" x2="632" y2="706" class="safe"/>
      <text x="410" y="524" text-anchor="middle" class="label">calibrated optical cone</text>
      <text x="410" y="546" text-anchor="middle" class="small">FOV {fov_range} mm at ground</text>
      <text x="410" y="697" text-anchor="middle" class="label">safe ≥{safe_width} mm</text>
    ''')}
    {_svg_annotation('skirts', f'''
      <path d="M130 570 L130 702 M158 570 L158 702 M690 570 L690 702 M662 570 L662 702" class="muted"/>
      <path d="M130 652 L102 652 M690 652 L718 652" class="thin"/>
      <text x="480" y="588" class="small">dual skirts {skirt} mm</text>
      <text x="480" y="608" class="small">rail height {rail} mm · clearance {clearance} mm</text>
    ''')}
    {_svg_annotation('working_distance', f'''
      <line x1="748" y1="278" x2="748" y2="720" class="dimension"/>
      <text x="730" y="470" text-anchor="end" class="label">WD {wd} mm</text>
      <text x="730" y="491" text-anchor="end" class="small">measured and locked</text>
    ''')}
    {_svg_annotation('physical_stage_C_unmeasured', '''
      <rect x="254" y="734" width="312" height="34" rx="8" class="unresolved"/>
      <text x="410" y="756" text-anchor="middle" class="label warning">exact ray clearance = UNMEASURED · Stage C required</text>
    ''')}
  </g>
  <g id="capture-interface-panel">
    <rect x="850" y="118" width="515" height="664" rx="12" class="panel"/>
    <text x="878" y="151" class="section">CAPTURE / SAFETY INTERFACES</text>
    {_svg_annotation('exposure_strobe', f'''
      <rect x="884" y="182" width="180" height="58" rx="8" class="selected"/>
      <text x="974" y="207" text-anchor="middle" class="label">real-time controller</text>
      <text x="974" y="227" text-anchor="middle" class="small">trigger + encoder latch</text>
      <path d="M1064 211 L1131 211" class="flow"/>
      <rect x="1136" y="182" width="195" height="58" rx="8" class="selected"/>
      <text x="1233" y="207" text-anchor="middle" class="label">global exposure</text>
      <text x="1233" y="227" text-anchor="middle" class="small">{sensor['exposure_us']:.0f} µs · {sensor['acquisition_rate_hz']:.0f} Hz</text>
      <path d="M1233 240 L1233 284" class="flow"/>
      <rect x="1136" y="289" width="195" height="58" rx="8" class="light"/>
      <text x="1233" y="314" text-anchor="middle" class="label">ExposureActive → strobe</text>
      <text x="1233" y="334" text-anchor="middle" class="small">{light['strobe_pulse_us'][0]:.0f}–{light['strobe_pulse_us'][1]:.0f} µs · four channels</text>
      <text x="884" y="269" class="small">same hardware event · stale host/GPS time forbidden</text>
    ''')}
    {_svg_annotation('usb_compute', f'''
      <rect x="884" y="379" width="180" height="66" rx="8" class="selected"/>
      <text x="974" y="404" text-anchor="middle" class="label">Basler camera</text>
      <text x="974" y="425" text-anchor="middle" class="small">native {sensor['active_roi_px'][0]}×{sensor['active_roi_px'][1]}</text>
      <path d="M1064 412 L1131 412" class="flow"/>
      <text x="1097" y="400" text-anchor="middle" class="tiny">USB3 ≤{compute['locking_cable_maximum_m']:.0f} m</text>
      <rect x="1136" y="379" width="195" height="66" rx="8" class="selected"/>
      <text x="1233" y="404" text-anchor="middle" class="label">RTX 3090 lane</text>
      <text x="1233" y="425" text-anchor="middle" class="small">{sensor['camera_count']} camera / {sensor['acquisition_rate_hz']:.0f} Hz only</text>
      <path d="M1233 445 L1233 485" class="flow"/>
      <rect x="1105" y="490" width="226" height="50" rx="8" class="disabled"/>
      <text x="1218" y="512" text-anchor="middle" class="label">scheduler / intervention interface</text>
      <text x="1218" y="530" text-anchor="middle" class="tiny">physical offset and hardware unresolved</text>
    ''')}
    {_svg_annotation('fail_closed', '''
      <rect x="884" y="574" width="447" height="122" rx="9" class="fault"/>
      <text x="1107" y="601" text-anchor="middle" class="label danger">FAULT OR INVALID IDENTITY → NO FIRE</text>
      <text x="906" y="627" class="small">E-stop · watchdog · hood open · overtemperature</text>
      <text x="906" y="650" class="small">timestamp · encoder · frame · deadline · calibration</text>
      <text x="906" y="673" class="small">profile · strobe · light channel · deploy · reverse · brownout</text>
      <path d="M1107 696 L1107 733" class="fault-flow"/>
      <rect x="952" y="733" width="310" height="33" rx="7" class="disabled"/>
      <text x="1107" y="755" text-anchor="middle" class="label danger">chemical-enable line: VERIFIED DISABLED</text>
    ''')}
  </g>"""
    return _svg_shell(result, architecture_sha256, "optical_cross_section", body)


def _validate_svg_payload(
    payload: str,
    result: Mapping[str, Any],
    architecture_sha256: str,
    view_id: str,
) -> None:
    if not payload.endswith("\n") or "\r" in payload:
        raise ValueError(f"SVG newline contract failed: {view_id}")
    if str(PROJECT_ROOT) in payload:
        raise ValueError(f"Absolute repository path leaked into SVG: {view_id}")
    if result["visual_contract"]["notice"] not in payload:
        raise ValueError(f"Fabrication disclaimer missing from SVG: {view_id}")
    if result["config_identity"]["sha256"] not in payload:
        raise ValueError(f"Config hash missing from SVG: {view_id}")
    if architecture_sha256 not in payload:
        raise ValueError(f"Architecture hash missing from SVG: {view_id}")
    required = set(_visual_row(result, view_id)["required_annotation_ids"])
    for annotation_id in required:
        marker = f'data-annotation-id="{html.escape(str(annotation_id), quote=True)}"'
        if marker not in payload:
            raise ValueError(
                f"Required visual annotation {annotation_id} missing from {view_id}"
            )
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid SVG XML for {view_id}: {exc}") from exc
    if root.attrib.get("data-view-id") != view_id:
        raise ValueError(f"SVG view identity mismatch: {view_id}")
    if root.attrib.get("data-architecture-sha256") != architecture_sha256:
        raise ValueError(f"SVG architecture identity mismatch: {view_id}")


def render_engineering_svgs(
    result: Mapping[str, Any], architecture_sha256: str
) -> dict[str, str]:
    renderers = {
        "exterior": _render_exterior_svg,
        "underside": _render_underside_svg,
        "optical_cross_section": _render_optical_cross_section_svg,
    }
    payloads: dict[str, str] = {}
    for row in result["visual_contract"]["views"]:
        view_id = str(row["view_id"])
        payload = renderers[view_id](result, architecture_sha256)
        _validate_svg_payload(payload, result, architecture_sha256, view_id)
        payloads[str(row["filename"])] = payload
    return payloads


def render_visual_manifest(
    result: Mapping[str, Any],
    architecture_sha256: str,
    visual_payloads: Mapping[str, str],
) -> str:
    rows = []
    for row in result["visual_contract"]["views"]:
        filename = str(row["filename"])
        payload = visual_payloads[filename]
        rows.append(
            {
                "view_id": row["view_id"],
                "filename": filename,
                "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "required_annotation_ids": list(row["required_annotation_ids"]),
            }
        )
    return render_json(
        {
            "schema_version": 1,
            "contract_id": result["contract_id"],
            "architecture_sha256": architecture_sha256,
            "config_sha256": result["config_identity"]["sha256"],
            "notice": result["visual_contract"]["notice"],
            "views": rows,
        }
    )


def _markdown_inline(value: Any) -> str:
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, list):
        return ", ".join(_markdown_inline(item) for item in value)
    if isinstance(value, float):
        return f"`{_format_dimension(value, 9)}`"
    return f"`{str(value)}`"


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| " + " | ".join(cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(cell(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def _docs_relative_link(repo_path: str) -> str:
    if repo_path.startswith("docs/"):
        return repo_path[len("docs/") :]
    return f"../{repo_path}"


def render_architecture_markdown(
    result: Mapping[str, Any],
    architecture_sha256: str,
    bom_sha256: str,
    visual_manifest_sha256: str,
    visual_payloads: Mapping[str, str],
) -> str:
    """Render the concise human-readable architecture from validated result data."""

    baseline = result["baseline"]
    sensor = baseline["sensor_optics"]
    light = baseline["light_enclosure"]
    platform = baseline["platform_carrier"]
    compute = baseline["compute_capture"]
    power = result["calculations"]["power_status"]
    calc = result["calculations"]
    bom = result["bom"]
    axes = result["status_axes"]
    source_integrity = result["source_integrity"]
    sources = source_integrity["sources"]
    decisions = {row["item_id"]: row for row in result["decision_items"]}
    visual_rows = result["visual_contract"]["views"]
    visual_hashes = {
        filename: hashlib.sha256(payload.encode("utf-8")).hexdigest()
        for filename, payload in visual_payloads.items()
    }

    status_table = _markdown_table(
        ["Axis", "Current state", "Meaning"],
        [
            ["Architecture", _markdown_inline(axes["architecture_selection"]), "One-bay selection is frozen for proof."],
            ["Source integration", _markdown_inline(result["integration_result"]), f"{source_integrity['verified_source_count']} exact-byte inputs verified; six terminal files are commit-bound."],
            ["Exact host", _markdown_inline(axes["host_qualification"]), "No tractor-specific build authority."],
            ["Physical acceptance", _markdown_inline(axes["physical_acceptance"]), "No physical A–E receipt exists."],
            ["Controlled capture", _markdown_inline(axes["controlled_capture_authorized"]), "Only the existing rig evaluator may grant it."],
            ["Dry marker", _markdown_inline(axes["dry_marker_ready"]), "Requires physical A–F evidence."],
            ["Field / product GO", f"{_markdown_inline(axes['field_go'])} / {_markdown_inline(axes['product_go'])}", "Not granted."],
            ["Purchase", _markdown_inline(axes["purchase_authorized"]), "No procurement or fabrication authorization."],
            ["Chemical fire", _markdown_inline(axes["chemical_fire_allowed"]), "Verified-disabled enable line; agronomic safety evidence absent."],
        ],
    )

    evidence_labels = {
        "sourced_facts": "Sourced facts",
        "deterministic_calculations": "Deterministic calculations",
        "integration_hypotheses": "Integration hypotheses",
        "physically_unmeasured": "Physically unmeasured",
        "physical_measurements": "Physical measurements",
    }
    evidence_table = _markdown_table(
        ["Evidence kind", "Machine class", "Result locations", "Claim limit"],
        [
            [
                evidence_labels[category],
                _markdown_inline(
                    row["evidence_classes"]
                    if "evidence_classes" in row
                    else row["evidence_class"]
                ),
                _markdown_inline(row["result_paths"]),
                (
                    f"{row['claim_limit']}; current product receipts = "
                    f"{row['current_product_receipt_count']}"
                    if "current_product_receipt_count" in row
                    else row["claim_limit"]
                ),
            ]
            for category in evidence_labels
            for row in [result["evidence_ledger"][category]]
        ],
    )

    source_release_table = _markdown_table(
        ["Release control", "Verified value", "Fail-closed meaning"],
        [
            [
                "Implementation base",
                f"`{source_integrity['implementation_base_commit']}`",
                "reachable from HEAD and contains the exact six terminal source files",
            ],
            [
                "Terminal source admission",
                f"{source_integrity['terminal_source_count']}/{source_integrity['terminal_source_count']} committed bytes verified",
                "current plan/survey bytes must equal both SHA-256 pins and the containing commit tree",
            ],
            [
                "Drift response",
                "`INTEGRATION_INVALID_SOURCE_DRIFT`",
                "missing, modified, uncommitted or commit-mismatched terminal input stops before calculation",
            ],
        ],
    )

    baseline_table = _markdown_table(
        ["Subsystem", "Frozen proof baseline", "Owner / boundary"],
        [
            ["Camera", f"1× {_markdown_inline(sensor['model'])}, order {_markdown_inline(sensor['order_number'])}, global-shutter visible RGB with factory IR-cut", "sensor_optics"],
            ["Lens", f"{_markdown_inline(sensor['lens_model'])}, f/{_format_dimension(sensor['aperture_f_number'])}", "sensor_optics"],
            ["Raster", f"native {sensor['active_roi_px'][0]}×{sensor['active_roi_px'][1]} ROI at offset ({sensor['active_roi_offset_px'][0]}, {sensor['active_roi_offset_px'][1]}); resize forbidden", "sensor_optics"],
            ["Optical geometry", f"FOV {_format_dimension(min(sensor['ground_fov_mm']))}–{_format_dimension(max(sensor['ground_fov_mm']))} mm; WD {_format_dimension(sensor['working_distance_adjustment_mm'][0])}–{_format_dimension(sensor['working_distance_adjustment_mm'][1])} mm; planes 0/55/110 mm", "sensor_optics; physical Stage C still required"],
            ["Capture", f"{_format_dimension(sensor['exposure_us'])} µs at {_format_dimension(sensor['acquisition_rate_hz'])} Hz", "compute_capture"],
            ["Light", f"four diffuse visible-white quadrants, {light['spectrum_cct_k'][0]}–{light['spectrum_cct_k'][1]} K, CRI ≥{light['color_rendering_index_minimum']}, simultaneous all-on, polarization {light['polarization_state']}", "light_enclosure; exact installed profile remains open"],
            ["Enclosure", f"minimum {light['hood_internal_plan_minimum_mm'][0]:.0f}×{light['hood_internal_plan_minimum_mm'][1]:.0f} mm internal hood; dual {light['skirt_length_mm'][0]:.0f}–{light['skirt_length_mm'][1]:.0f} mm skirts; {light['operating_clearance_mm'][0]:.0f}–{light['operating_clearance_mm'][1]:.0f} mm clearance; tilted window", "light_enclosure; functional proof enclosure, not certified ingress"],
            ["Carrier", _markdown_inline(platform["proof_topology"]), "platform_carrier; exact rear host unresolved"],
            ["Reusable unit", _markdown_inline(platform["reusable_unit"]), "cassette is local rigid calibration frame; carrier stays host-specific"],
            ["Travel", f"ground-contact signed quadrature encoder; proof speeds {platform['trial_speeds_m_s'][0]} and {platform['trial_speeds_m_s'][1]} m/s", "platform_carrier"],
            ["Compute", f"existing {compute['accelerator']}; one camera at {compute['supported_rate_hz']:.0f} Hz only; dedicated USB3 root", "compute_capture; measured Stage-E proxy is not an end-to-end physical PASS"],
            ["Intervention", "rigid local mounting datum only; hardware, footprint, signed offset, deposition and chemistry are null/external", "intervention_external"],
        ],
    )

    gsd_values = list(calc["gsd_mm_px"].values())
    blur_values = [
        value for speed_row in calc["blur_px"].values() for value in speed_row.values()
    ]
    calculation_table = _markdown_table(
        ["Derived quantity", "Exact result", "Claim boundary"],
        [
            ["Active sensor span", f"{calc['active_sensor_span_mm']:.4f} mm", "deterministic from 2048 px × 3.45 µm"],
            ["GSD over measured FOV", f"{min(gsd_values):.12f}–{max(gsd_values):.12f} mm/px", "nominal geometry, not installed Stage-C evidence"],
            ["Nominal target support at 480 mm", f"10 mm = {calc['target_pixels']['480']['10']:.6f} px; 20 mm = {calc['target_pixels']['480']['20']:.6f} px", "10 mm is an optical witness; 20 mm is the first action service class"],
            ["Smear at 0.5 / 1.0 m/s", f"{calc['smear_mm']['0.5']:.3f} / {calc['smear_mm']['1.0']:.3f} mm", "170 µs exposure"],
            ["Worst calculated blur", f"{max(blur_values):.12f} px", "must remain ≤0.75 px"],
            ["Action-safe widths", f"{calc['safe_width_mm']['474']:.3f} / {calc['safe_width_mm']['480']:.3f} / {calc['safe_width_mm']['484']:.3f} mm", "474/480/484 mm FOV after 64 px per-edge abstention"],
            ["Bayer10 at 15 Hz", f"{calc['raw_payload_mbit_s']['bayer10_15hz']:.4f} Mbit/s raw; {calc['payload_with_headroom_mbit_s']['bayer10_15hz']:.5f} Mbit/s with 20% headroom", "data payload, not mechanical payload"],
            ["Gross geometric throughput", f"{calc['gross_geometric_throughput_ha_h']['0.5']:.7f} ha/h at 0.5 m/s; {calc['gross_geometric_throughput_ha_h']['1.0']:.6f} ha/h at 1.0 m/s", "uses conservative safe width; excludes turns, misses and duty losses"],
            ["Compute proxy", f"batch-4 p95 {calc['compute_proxy']['halo_batch4_p95_ms']:.12f} ms; margin {calc['compute_proxy']['remaining_deadline_margin_ms']:.12f} ms", "proxy checkpoint differs from selected foundation; no end-to-end readiness claim"],
            ["Inactive two-bay formula screen", f"{calc['multi_bay_compatibility']['inactive_two_bay_safe_swath_at_max_pitch_mm']:.3f} mm safe swath at max pitch; hood ≥{calc['multi_bay_compatibility']['inactive_two_bay_continuous_hood_width_at_max_pitch_mm']:.0f} mm", "compatibility-only; second camera is false and every bay/overlap requires new evidence"],
        ],
    )

    ownership_table = _markdown_table(
        ["Boundary", "Owns", "Does not silently acquire"],
        [
            ["Cassette", ", ".join(result["ownership_boundary"]["cassette_owns"]), "host hitch, gross structure or carrier qualification"],
            ["Carrier", ", ".join(result["ownership_boundary"]["carrier_owns"]), "camera, lens, light internals or intervention agronomy"],
            ["Sensor / optics", ", ".join(result["ownership_boundary"]["external_owners"]["sensor_optics"]), "light, carrier or chemical decisions"],
            ["Light / enclosure", ", ".join(result["ownership_boundary"]["external_owners"]["light_enclosure"]), "sensor modality, platform or chemistry"],
            ["Intervention", ", ".join(result["ownership_boundary"]["external_owners"]["intervention_external"]), "camera/light/platform acceptance"],
        ],
    )

    interface_table = _markdown_table(
        ["Interface", "Owner → counterparty", "State", "Value / limit"],
        [
            [row["interface_id"], f"{row['owner']} → {row['counterparty']}", row["state"], f"{_markdown_inline(row['value'])}; {row['claim_limit']}"]
            for row in result["interface_contract"]
        ],
    )

    cost_totals = bom["totals"]
    blocker_text = "; ".join(
        f"{row.get('bom_item_id', row.get('double_count_group'))}: {row['reason']}"
        for row in cost_totals["integrated_total_blockers"]
    )
    cost_table = _markdown_table(
        ["Cost boundary", "USD", "Meaning"],
        [
            ["Proof module before contingency", f"{cost_totals['proof_module_before_contingency'][0]:.2f}–{cost_totals['proof_module_before_contingency'][1]:.2f}", "source-bound dated module evidence"],
            ["Proof module with 15% contingency", f"{cost_totals['proof_module_with_contingency'][0]:.2f}–{cost_totals['proof_module_with_contingency'][1]:.2f}", "budget screen, not landed quote"],
            ["Rear carrier engineering screen", f"{cost_totals['rear_carrier_engineering_screen_not_quote'][0]:.2f}–{cost_totals['rear_carrier_engineering_screen_not_quote'][1]:.2f}", "engineering screen, explicitly not a quote"],
            ["Bounded module + carrier screen", f"{cost_totals['bounded_proof_plus_carrier_screen_not_integrated_total'][0]:.2f}–{cost_totals['bounded_proof_plus_carrier_screen_not_integrated_total'][1]:.2f}", "not an integrated product total"],
            ["Integrated one-bay total", _markdown_inline(cost_totals["integrated_one_bay_total"]), "remains null until every required cost and overlap reconciliation is complete"],
        ],
    )

    challenger_ids = [
        "alternative_modalities",
        "cross_polarization",
        "external_heatsink_fan",
        "front_three_point_challenger",
        "rate_20hz",
        "second_camera",
        "scale_carrier",
    ]
    challenger_table = _markdown_table(
        ["Alternative", "Current state", "Only opening trigger", "Decision rule / owner"],
        [
            [item_id, decisions[item_id]["decision_state"], decisions[item_id]["resolution_trigger"], f"{decisions[item_id]['resolution_rule']} / {decisions[item_id]['owner']}"]
            for item_id in challenger_ids
        ],
    )

    open_ids = [
        "installed_light_profile",
        "exact_rear_host",
        "whole_compute_system_power",
        "cassette_mass",
        "cassette_center_of_gravity",
        "camera_to_intervention_offset",
        "controlled_capture_authority",
        "dry_marker_authority",
        "chemical_enable",
    ]
    open_table = _markdown_table(
        ["Unresolved item", "Value", "Evidence trigger", "Who may resolve it"],
        [
            [item_id, _markdown_inline(decisions[item_id]["value"]), decisions[item_id]["resolution_trigger"], decisions[item_id]["resolution_rule"]]
            for item_id in open_ids
        ],
    )

    source_table = _markdown_table(
        ["Source ID", "Pinned file", "Owner / role", "SHA-256", "Containing commit"],
        [
            [
                source_id,
                f"[`{receipt['path']}`]({_docs_relative_link(receipt['path'])})",
                f"{receipt['owner']} / {receipt['role']}",
                f"`{receipt['sha256']}`",
                (
                    f"`{receipt['containing_commit']}`"
                    if "containing_commit" in receipt
                    else "—"
                ),
            ]
            for source_id, receipt in sorted(sources.items())
        ],
    )

    artifact_rows = [
        ["Canonical config", "[`configs/deploy/spot_spray_product_architecture_v1.yaml`](../configs/deploy/spot_spray_product_architecture_v1.yaml)", f"`{result['config_identity']['sha256']}`"],
        ["Architecture JSON", "[`architecture.json`](results/spot_spray_product_architecture_v1/architecture.json)", f"`{architecture_sha256}`"],
        ["Normalized BOM", "[`bom.csv`](results/spot_spray_product_architecture_v1/bom.csv)", f"`{bom_sha256}`"],
        ["Visual manifest", "[`visual_manifest.json`](results/spot_spray_product_architecture_v1/visual_manifest.json)", f"`{visual_manifest_sha256}`"],
    ]
    artifact_rows.extend(
        [
            row["view_id"],
            f"[`{row['filename']}`](results/spot_spray_product_architecture_v1/{row['filename']})",
            f"`{visual_hashes[row['filename']]}`",
        ]
        for row in visual_rows
    )
    artifact_table = _markdown_table(["Artifact", "Path", "SHA-256"], artifact_rows)

    fail_safe_ids = ", ".join(row["fault_id"] for row in result["fail_safe_interfaces"])
    replan_list = "\n".join(f"- `{trigger}`" for trigger in result["replan_triggers"])

    document = f"""# Spot-Spray Product Architecture V1

> **Canonical outcome:** one controlled, removable spot-spray proof bay is selected at desk-integration level. The result is `{result['integration_result']}` with exact source integrity `PASS`; it is **not** physical acceptance, procurement authority, controlled-capture authority, field GO, product GO, dry-marker readiness, certified ingress, or chemical-fire authority.

This document is generated deterministically from the pinned architecture result, normalized BOM and visual manifest. It reconciles the terminal sensor/optics, light/enclosure and platform plans and surveys without transferring their ownership.

## 1. Independent status axes

{status_table}

“Frozen” below means a build-and-test baseline only. It never means physically READY.

### Evidence reading key

{evidence_table}

Sourced facts retain their owning lane; deterministic calculations are arithmetic, not observations. Integration hypotheses connect interfaces without creating a physical fact. Every physically unmeasured value remains `null`, and the current product-level physical receipt count is zero.

### Source release closure

{source_release_table}

The six terminal lane plans and surveys are admitted only when their current bytes match both their SHA-256 pins and implementation-base commit `{source_integrity['implementation_base_commit']}`. This commit binding proves repository provenance for those decision-owning inputs; it does not promote any physical, host, procurement, field or chemical state.

## 2. Selected price-performance proof product

{baseline_table}

The selected carrier architecture is a manually driven rear-three-point one-bay proof toolbar with a removable ground-following cassette. A front-three-point carrier is trigger-only; multi-bay/qualified-boom and dedicated-trailed carriers remain later scale routes. No autonomous platform is part of this proof.

## 3. Engineering views

Each SVG is generated from the same architecture result, contains the full config and result hashes, names unresolved values explicitly, and carries **NOT A FABRICATION DRAWING**.

[![Exterior carrier and proof bay](results/spot_spray_product_architecture_v1/exterior.svg)](results/spot_spray_product_architecture_v1/exterior.svg)

[![Underside optical and action geometry](results/spot_spray_product_architecture_v1/underside.svg)](results/spot_spray_product_architecture_v1/underside.svg)

[![Optical cross-section and capture interfaces](results/spot_spray_product_architecture_v1/optical_cross_section.svg)](results/spot_spray_product_architecture_v1/optical_cross_section.svg)

## 4. Geometry, pixels, blur, payload and throughput

{calculation_table}

### Why 600 mm is not 444.375 mm

- **600×600 mm** is the minimum clear internal hood plan used to package optics, four lights, diffusers, baffles, the window, skirts, cable routes and thermal paths.
- **474–484 mm** is the measured ground FOV range.
- **444.375 mm** is the conservative action-safe width after the 64 px outer ring is abstained: `474 × (2048 − 2×64) / 2048`.
- Only the action-safe width enters the throughput calculation. Hood width, unmasked FOV and an unknown intervention footprint do not.
- Installed optical-cone clearance remains `null`; the existing physical Stage-C authority must prove non-occlusion.

## 5. Ownership and coordinate reconciliation

{ownership_table}

All general product frames use right-handed `+X` forward travel, `+Y` vehicle right and `+Z` up. The light survey’s fixture frame used `+X` vehicle right and `+Y` vehicle front, so the contract records an exact axis permutation: cassette `+X ← light +Y`, cassette `+Y ← light +X`, `+Z` unchanged. It does not silently reinterpret either source.

The required frames are `F_world`, `F_carrier`, `F_cassette`, `F_camera`, `F_ground_calibration`, `F_light_fixture`, `F_encoder` and `F_intervention_mount`. Host, installed-camera, ground-calibration, encoder and intervention transforms remain physically unresolved where their owning evidence is absent.

## 6. Data, timing, tracking and safety flow

`signed ground encoder → same-event trigger + encoder latch → global-shutter camera → ExposureActive → isolated four-channel strobe → dedicated USB3 root → one-camera RTX 3090 tracking/result lane → scheduler/intervention interface`

The scheduler may consume only identity-bound frame, timestamp, encoder, calibration, bay, profile and result records. Host-arrival time, GPS-only speed, display speed, CAD-assumed intervention offset and stale metadata are not control authority.

{interface_table}

All {len(result['fail_safe_interfaces'])} material fault states are fail-closed: {fail_safe_ids}. Every affected pending command is discarded within its defined scope and recovery requires a fresh valid witness. The chemical-enable hardware line remains verified disabled.

## 7. Illumination, enclosure and agronomic variability

- The baseline is broad visible-white illumination with four cardinal diffuse quadrants, simultaneous all-on firing, factory IR-cut retained and polarization physically OFF.
- Exact LED/bin, diffuser, current vector, optical energy, aim, window installation, thermal interface, skirt material and installed profile remain bench variables. Catalogue values do not populate them.
- Agronomic/optical variability is confronted through the existing installed-rig program: 0/55/110 mm planes, full-field regions, external-light/skirt states, wet-leaf/soil glare attribution and thermal/fault arms.
- Cross-polarization opens only after the paired wet-leaf/soil glare trigger and must reduce glare by at least 50% while every other absolute gate still passes.
- Visible mono, RGB+NIR, multispectral, RGB+thermal and RGB+depth remain closed challengers. Only the sensor lane may open a bounded A/B after an attributable terminal failure.
- The 10 mm target is an optical witness, not an action promise. The first action service class is 20 mm, and no weed-control effectiveness, deposition, dose, crop-injury or yield claim exists.

## 8. Mechanical, power and thermal status

- Required mechanical components are reported separately, but all assembled masses and signed CG distances are physically unmeasured. Therefore payload, moment and combined CG are `null` by rule.
- The light branch ceiling is {power['light_branch_average_maximum_w']:.0f} W average; the capture module ceiling is {power['capture_module_average_maximum_w_excluding_compute']:.0f} W average excluding compute; {power['light_peak_electrical_ceiling_w_not_setpoint']:.0f} W is a peak electrical ceiling, not a setpoint.
- The RTX 3090 {power['gpu_reference_board_power_w_not_vehicle_draw']:.0f} W board figure and {power['reference_system_psu_w_not_vehicle_draw']:.0f} W reference PSU are reference-only, not vehicle input measurements.
- Whole-compute draw, conversion/distribution losses, integrated continuous draw and integrated transient draw remain `null`. Exact host power qualification therefore remains open.
- The inherited thermal campaign is at least {power['thermal_duration_minimum_minutes']} minutes over {power['exterior_ambient_test_c'][0]:.0f}–{power['exterior_ambient_test_c'][1]:.0f} °C, with camera housing ≤{power['camera_housing_maximum_c']:.0f} °C and LED plate ≤{power['led_plate_maximum_c']:.0f} °C. No physical receipt exists yet.

## 9. BOM and cost boundary

{cost_table}

The normalized line-level BOM is [`bom.csv`](results/spot_spray_product_architecture_v1/bom.csv). Existing RTX 3090 incremental acquisition is allowed to be USD 0 only because it is explicitly an existing asset; its power, opportunity cost and integration cost are not zero. Unknown required costs serialize empty/`null`, never zero. Chemical savings, yield, acreage, labor and autonomy benefits are forbidden credits.

Integrated-total blockers: {blocker_text}.

## 10. Alternatives and opening triggers

{challenger_table}

Cost or preference cannot compensate for a failed provenance, geometry, safety, compute, host or acceptance gate. One trigger opens at most the bounded challenger owned by that lane.

## 11. Physically unmeasured values and next evidence

{open_table}

The next highest-value physical step is **one exact-host-qualified, hash-bound one-bay A–E bench campaign**, after exact host intake and installed BOM identities—not another market survey. Physical A–F may authorize a non-chemical dry marker only through the existing evaluator. Chemical operation requires a separate authorized safety/agronomy scope and full re-plan.

## 12. Re-plan triggers

{replan_list}

Any terminal lane plan or survey byte drift invalidates this generated package. Capture or acceptance authority drift requires explicit source re-freeze or full integration re-plan before any consistent result can be emitted.

## 13. Source lock

{source_table}

The acceptance contract’s exact bytes and canonical policy are separately checked. This integration layer references the existing evaluator; it does not imitate it or evaluate physical receipts.

## 14. Artifact identities

{artifact_table}

The package-wide artifact ledger is [`package_manifest.json`](results/spot_spray_product_architecture_v1/package_manifest.json). It intentionally excludes its own digest to avoid a recursive hash; the builder reports that final digest externally. Generated-artifact hashes contain no timestamp, hostname or absolute path.

## 15. Terminal claim boundary

This package proves only that the six commit-bound terminal inputs, other exact pinned desk evidence, explicit ownership boundaries and deterministic calculations are mutually consistent for the selected one-bay proof architecture. It makes **no procurement, fabrication, physical READY, controlled-capture, dry-marker READY, field GO, product GO, autonomous-operation, certified-ingress, chemical-fire, deposition, crop-injury, weed-kill, yield, acreage or commercial-return claim**.
"""
    return document.rstrip() + "\n"


def render_package_manifest(
    result: Mapping[str, Any],
    architecture_sha256: str,
    bom_sha256: str,
    document_sha256: str,
    visual_manifest_sha256: str,
    visual_payloads: Mapping[str, str],
) -> str:
    artifacts = [
        {
            "artifact_id": "canonical_config",
            "path": result["config_identity"]["path"],
            "sha256": result["config_identity"]["sha256"],
        },
        {
            "artifact_id": "architecture_json",
            "path": "docs/results/spot_spray_product_architecture_v1/architecture.json",
            "sha256": architecture_sha256,
        },
        {
            "artifact_id": "normalized_bom_csv",
            "path": "docs/results/spot_spray_product_architecture_v1/bom.csv",
            "sha256": bom_sha256,
        },
        {
            "artifact_id": "human_readable_architecture",
            "path": "docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md",
            "sha256": document_sha256,
        },
        {
            "artifact_id": "visual_manifest",
            "path": "docs/results/spot_spray_product_architecture_v1/visual_manifest.json",
            "sha256": visual_manifest_sha256,
        },
    ]
    for row in result["visual_contract"]["views"]:
        filename = str(row["filename"])
        artifacts.append(
            {
                "artifact_id": f"visual_{row['view_id']}",
                "path": f"docs/results/spot_spray_product_architecture_v1/{filename}",
                "sha256": hashlib.sha256(
                    visual_payloads[filename].encode("utf-8")
                ).hexdigest(),
            }
        )
    return render_json(
        {
            "schema_version": 1,
            "contract_id": result["contract_id"],
            "integration_result": result["integration_result"],
            "source_integrity": result["source_integrity"]["status"],
            "verified_source_count": result["source_integrity"][
                "verified_source_count"
            ],
            "source_release": {
                "admission_policy": result["source_integrity"][
                    "admission_policy"
                ],
                "implementation_base_commit": result["source_integrity"][
                    "implementation_base_commit"
                ],
                "terminal_source_count": result["source_integrity"][
                    "terminal_source_count"
                ],
                "terminal_sources_clean_against_commit": result[
                    "source_integrity"
                ]["terminal_sources_clean_against_commit"],
            },
            "status_axes": result["status_axes"],
            "claim_boundary": result["claim_boundary"],
            "evidence_ledger": result["evidence_ledger"],
            "source_inputs": [
                {
                    "source_id": source_id,
                    "path": receipt["path"],
                    "sha256": receipt["sha256"],
                    "containing_commit": receipt.get("containing_commit"),
                    "committed_bytes_verified": receipt.get(
                        "committed_bytes_verified", False
                    ),
                    "owner": receipt["owner"],
                    "role": receipt["role"],
                }
                for source_id, receipt in sorted(
                    result["source_integrity"]["sources"].items()
                )
            ],
            "artifacts": artifacts,
            "manifest_self_identity": {
                "path": (
                    "docs/results/spot_spray_product_architecture_v1/"
                    "package_manifest.json"
                ),
                "sha256": None,
                "reason": "self_digest_excluded_to_avoid_recursive_hash",
            },
            "package_claim": (
                "desk_evidence_and_deterministic_integration_only; no procurement, "
                "physical READY, controlled capture, dry-marker READY, field GO, "
                "product GO or chemical fire"
            ),
        }
    )


def derive_contract(
    config: Mapping[str, Any], root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    """Validate all pins and return the deterministic pre-real integration result."""

    verified_sources = verify_source_lock(config, root)
    validate_schema_and_decisions(config, verified_sources)
    validate_acceptance_and_fail_safe_interfaces(config, verified_sources)
    _validate_baseline_invariants(config)
    validate_drawing_contract(config)
    _verify_upstream_consistency(config, verified_sources, root)
    calculations = derive_calculations(config)
    _verify_golden_calculations(config, calculations)
    bom = derive_bom(config, verified_sources)

    return {
        "schema_version": 1,
        "contract_id": config["contract_id"],
        "integration_result": "INTEGRATION_CONSISTENT_PRE_REAL",
        "source_integrity": {
            "status": "PASS",
            "algorithm": config["source_lock"]["algorithm"],
            "admission_policy": config["source_lock"]["admission_policy"],
            "implementation_base_commit": config["source_lock"][
                "implementation_base_commit"
            ],
            "terminal_source_count": sum(
                len(config["source_lock"][group])
                for group in TERMINAL_SOURCE_IDS
            ),
            "terminal_sources_clean_against_commit": True,
            "verified_source_count": len(verified_sources),
            "sources": verified_sources,
        },
        "status_axes": _json_value(config["status_axes"]),
        "claim_boundary": _json_value(config["claim_boundary"]),
        "evidence_ledger": _json_value(config["evidence_ledger"]),
        "baseline": _json_value(config["baseline"]),
        "coordinate_frames": _json_value(config["coordinate_frames"]),
        "ownership_boundary": _json_value(config["ownership_boundary"]),
        "spatial_contract": _json_value(config["spatial_contract"]),
        "interface_contract": _json_value(config["interface_contract"]),
        "visual_contract": _json_value(config["visual_contract"]),
        "acceptance_binding": _json_value(config["acceptance_binding"]),
        "fail_safe_interfaces": _json_value(config["fail_safe_interfaces"]),
        "decision_items": _json_value(config["decision_items"]),
        "calculations": calculations,
        "bom": bom,
        "replan_triggers": list(config["replan_triggers"]),
    }


def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
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


def _allowed_result_path(path: Path, root: Path) -> Path:
    path = path.resolve()
    allowed = (root / "docs/results/spot_spray_product_architecture_v1").resolve()
    try:
        path.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Result path must remain under {allowed}: {path}") from exc
    return path


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--result",
        type=Path,
        default=DEFAULT_RESULT,
        help="Architecture JSON path under the lane's allowed result directory.",
    )
    parser.add_argument(
        "--bom-csv",
        type=Path,
        default=DEFAULT_BOM_CSV,
        help="Normalized BOM CSV path under the lane's allowed result directory.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and calculate without writing either result artifact.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    config_path = args.config.resolve()
    config = load_yaml_mapping(config_path)
    result = derive_contract(config, root)
    result["config_identity"] = {
        "path": str(config_path.relative_to(root)),
        "sha256": sha256_file(config_path),
    }
    architecture_payload = render_json(result)
    bom_payload = render_bom_csv(result["bom"])
    architecture_sha256 = hashlib.sha256(
        architecture_payload.encode("utf-8")
    ).hexdigest()
    bom_sha256 = hashlib.sha256(bom_payload.encode("utf-8")).hexdigest()
    visual_payloads = render_engineering_svgs(result, architecture_sha256)
    visual_manifest_payload = render_visual_manifest(
        result, architecture_sha256, visual_payloads
    )
    visual_sha256 = {
        filename: hashlib.sha256(payload.encode("utf-8")).hexdigest()
        for filename, payload in visual_payloads.items()
    }
    visual_manifest_sha256 = hashlib.sha256(
        visual_manifest_payload.encode("utf-8")
    ).hexdigest()
    document_payload = render_architecture_markdown(
        result,
        architecture_sha256,
        bom_sha256,
        visual_manifest_sha256,
        visual_payloads,
    )
    document_sha256 = hashlib.sha256(document_payload.encode("utf-8")).hexdigest()
    package_manifest_payload = render_package_manifest(
        result,
        architecture_sha256,
        bom_sha256,
        document_sha256,
        visual_manifest_sha256,
        visual_payloads,
    )
    package_manifest_sha256 = hashlib.sha256(
        package_manifest_payload.encode("utf-8")
    ).hexdigest()
    if not args.check_only:
        architecture_output = _allowed_result_path(args.result, root)
        bom_output = _allowed_result_path(args.bom_csv, root)
        view_outputs = {
            filename: _allowed_result_path(
                root / "docs/results/spot_spray_product_architecture_v1" / filename,
                root,
            )
            for filename in visual_payloads
        }
        manifest_output = _allowed_result_path(
            root
            / "docs/results/spot_spray_product_architecture_v1"
            / DEFAULT_VISUAL_MANIFEST.name,
            root,
        )
        package_manifest_output = _allowed_result_path(
            root
            / "docs/results/spot_spray_product_architecture_v1"
            / DEFAULT_PACKAGE_MANIFEST.name,
            root,
        )
        document_output = (
            root / "docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md"
        ).resolve()
        expected_document_output = DEFAULT_DOCUMENT.resolve()
        if document_output != expected_document_output:
            raise ValueError(
                "Human-readable architecture output must remain at "
                f"{expected_document_output}: {document_output}"
            )
        all_outputs = [
            architecture_output,
            bom_output,
            manifest_output,
            package_manifest_output,
            document_output,
            *view_outputs.values(),
        ]
        if len(all_outputs) != len(set(all_outputs)):
            raise ValueError("Generated architecture artifact paths must differ")
        _atomic_write_text(architecture_output, architecture_payload)
        _atomic_write_text(bom_output, bom_payload)
        for filename, output in view_outputs.items():
            _atomic_write_text(output, visual_payloads[filename])
        _atomic_write_text(manifest_output, visual_manifest_payload)
        _atomic_write_text(document_output, document_payload)
        _atomic_write_text(package_manifest_output, package_manifest_payload)
    summary = {
        "integration_result": result["integration_result"],
        "source_integrity": result["source_integrity"]["status"],
        "verified_source_count": result["source_integrity"]["verified_source_count"],
        "safe_width_minimum_mm": min(result["calculations"]["safe_width_mm"].values()),
        "proof_module_with_contingency_usd": result["bom"]["totals"][
            "proof_module_with_contingency"
        ],
        "integrated_one_bay_total_usd": result["bom"]["totals"][
            "integrated_one_bay_total"
        ],
        "physical_acceptance": result["status_axes"]["physical_acceptance"],
        "chemical_fire_allowed": result["status_axes"]["chemical_fire_allowed"],
        "architecture_sha256": architecture_sha256,
        "bom_csv_sha256": bom_sha256,
        "visual_sha256": visual_sha256,
        "visual_manifest_sha256": visual_manifest_sha256,
        "document_sha256": document_sha256,
        "package_manifest_sha256": package_manifest_sha256,
        "artifacts_written": not args.check_only,
    }
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
