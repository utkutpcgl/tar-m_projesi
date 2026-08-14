from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest
from yaml.constructor import ConstructorError

from scripts.build_spot_spray_product_architecture_v1 import (
    PROJECT_ROOT,
    CrossLaneConflictError,
    SourceDriftError,
    derive_calculations,
    derive_contract,
    load_yaml_mapping,
    raw_payload_mbit_s,
    render_architecture_markdown,
    render_bom_csv,
    render_engineering_svgs,
    render_json,
    render_package_manifest,
    render_visual_manifest,
    safe_fraction,
    sha256_file,
    verify_source_lock,
)


CONFIG_PATH = (
    PROJECT_ROOT / "configs/deploy/spot_spray_product_architecture_v1.yaml"
)


@pytest.fixture(scope="module")
def config() -> dict:
    return load_yaml_mapping(CONFIG_PATH)


@pytest.fixture(scope="module")
def result(config: dict) -> dict:
    return derive_contract(config, PROJECT_ROOT)


@pytest.fixture(scope="module")
def result_with_identity(result: dict) -> dict:
    return {
        **result,
        "config_identity": {
            "path": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
            "sha256": sha256_file(CONFIG_PATH),
        },
    }


def _decision(result: dict, item_id: str) -> dict:
    return next(
        item for item in result["decision_items"] if item["item_id"] == item_id
    )


def _bom_item(result: dict, item_id: str) -> dict:
    return next(item for item in result["bom"]["items"] if item["bom_item_id"] == item_id)


def _render_package(result: dict) -> dict[str, object]:
    architecture = render_json(result)
    bom = render_bom_csv(result["bom"])
    architecture_sha256 = hashlib.sha256(architecture.encode("utf-8")).hexdigest()
    bom_sha256 = hashlib.sha256(bom.encode("utf-8")).hexdigest()
    views = render_engineering_svgs(result, architecture_sha256)
    visual_manifest = render_visual_manifest(result, architecture_sha256, views)
    visual_manifest_sha256 = hashlib.sha256(
        visual_manifest.encode("utf-8")
    ).hexdigest()
    document = render_architecture_markdown(
        result,
        architecture_sha256,
        bom_sha256,
        visual_manifest_sha256,
        views,
    )
    document_sha256 = hashlib.sha256(document.encode("utf-8")).hexdigest()
    package_manifest = render_package_manifest(
        result,
        architecture_sha256,
        bom_sha256,
        document_sha256,
        visual_manifest_sha256,
        views,
    )
    return {
        "architecture": architecture,
        "bom": bom,
        "views": views,
        "visual_manifest": visual_manifest,
        "document": document,
        "package_manifest": package_manifest,
    }


def test_exact_source_lock_and_acceptance_identity_are_current(result: dict) -> None:
    integrity = result["source_integrity"]
    assert integrity["status"] == "PASS"
    assert integrity["verified_source_count"] == 19
    assert len(integrity["sources"]) == 19
    assert integrity["implementation_base_commit"] == (
        "a24f7dec956af170436bcb17d679aa53918c9ec8"
    )
    assert integrity["terminal_source_count"] == 6
    assert integrity["terminal_sources_clean_against_commit"] is True
    for receipt in integrity["sources"].values():
        assert receipt["exact_bytes_verified"] is True
        assert sha256_file(PROJECT_ROOT / receipt["path"]) == receipt["sha256"]

    terminal_ids = {
        "sensor_optics_plan",
        "light_enclosure_plan",
        "platform_product_plan",
        "sensor_optics_survey",
        "light_enclosure_survey",
        "platform_product_survey",
    }
    for source_id in terminal_ids:
        receipt = integrity["sources"][source_id]
        assert receipt["containing_commit"] == integrity[
            "implementation_base_commit"
        ]
        assert receipt["committed_bytes_verified"] is True

    acceptance = integrity["sources"]["rig_acceptance_contract"]
    assert acceptance["canonical_policy_verified"] is True
    assert acceptance["canonical_sha256"] == (
        "c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21"
    )


def test_status_axes_are_independent_and_never_promote_readiness(result: dict) -> None:
    assert result["integration_result"] == "INTEGRATION_CONSISTENT_PRE_REAL"
    axes = result["status_axes"]
    assert axes["architecture_selection"] == "FROZEN_BASELINE"
    assert axes["host_qualification"] == "HOST_UNRESOLVED"
    assert axes["physical_acceptance"] == "PRE_REAL_NOT_READY"
    for flag in (
        "controlled_capture_authorized",
        "dry_marker_ready",
        "field_go",
        "product_go",
        "chemical_fire_allowed",
        "purchase_authorized",
    ):
        assert axes[flag] is False
    assert result["claim_boundary"][
        "integration_validation_is_physical_acceptance"
    ] is False


def test_evidence_ledger_separates_fact_calculation_hypothesis_and_null(
    result: dict, config: dict
) -> None:
    ledger = result["evidence_ledger"]
    assert set(ledger) == {
        "sourced_facts",
        "deterministic_calculations",
        "integration_hypotheses",
        "physically_unmeasured",
        "physical_measurements",
    }
    assert ledger["sourced_facts"]["evidence_classes"] == [
        "FROZEN_REPOSITORY_CONTRACT",
        "TERMINAL_LANE_DECISION",
    ]
    assert ledger["deterministic_calculations"]["evidence_class"] == (
        "DETERMINISTIC_CALCULATION"
    )
    assert ledger["integration_hypotheses"]["evidence_class"] == (
        "ENGINEERING_INTEGRATION_INFERENCE"
    )
    assert ledger["physically_unmeasured"]["evidence_class"] == (
        "NO_EVIDENCE_NULL"
    )
    assert ledger["physical_measurements"]["evidence_class"] == (
        "PHYSICAL_MEASUREMENT"
    )
    assert ledger["physical_measurements"]["current_product_receipt_count"] == 0

    forged = deepcopy(config)
    forged["evidence_ledger"]["physical_measurements"][
        "current_product_receipt_count"
    ] = 1
    with pytest.raises(ValueError, match="physical product receipt count"):
        derive_contract(forged, PROJECT_ROOT)


def test_one_bay_baseline_is_source_consistent(result: dict) -> None:
    baseline = result["baseline"]
    sensor = baseline["sensor_optics"]
    assert sensor["camera_count"] == 1
    assert sensor["model"] == "a2A2464-77ucPRO"
    assert sensor["lens_model"] == "C23-0824-5M-P"
    assert sensor["modality"] == "visible_RGB_with_factory_IR_cut"
    assert sensor["active_roi_px"] == [2048, 2048]
    assert sensor["active_roi_offset_px"] == [200, 0]
    assert sensor["ground_fov_mm"] == [474.0, 480.0, 484.0]
    assert sensor["working_distance_adjustment_mm"] == [520.0, 590.0]
    assert sensor["exposure_us"] == 170.0
    assert sensor["acquisition_rate_hz"] == 15.0

    light = baseline["light_enclosure"]
    assert light["hood_internal_plan_minimum_mm"] == [600.0, 600.0]
    assert light["polarization_state"] == "OFF"
    assert light["exact_installed_profile"] is None

    platform = baseline["platform_carrier"]
    assert platform["proof_topology"] == (
        "manual_tractor_rear_three_point_rigid_toolbar"
    )
    assert platform["exact_host"] is None
    assert platform["camera_to_intervention_offset_mm"] is None

    compute = baseline["compute_capture"]
    assert compute["supported_camera_count"] == 1
    assert compute["supported_rate_hz"] == 15.0
    assert compute["stage_e_proxy_applies_to_selected_foundation"] is False


def test_golden_geometry_target_pixels_blur_and_swath(result: dict) -> None:
    calc = result["calculations"]
    assert calc["active_sensor_span_mm"] == pytest.approx(7.0656, abs=1e-12)
    assert calc["gsd_mm_px"] == pytest.approx(
        {
            "474": 0.2314453125,
            "480": 0.234375,
            "484": 0.236328125,
        },
        abs=1e-12,
    )
    assert calc["target_pixels"]["480"]["10"] == pytest.approx(
        42.666666666666664
    )
    assert calc["target_pixels"]["480"]["20"] == pytest.approx(
        85.33333333333333
    )
    assert calc["safe_fraction"] == pytest.approx(0.9375)
    assert calc["safe_width_mm"] == pytest.approx(
        {"474": 444.375, "480": 450.0, "484": 453.75}
    )
    assert calc["smear_mm"] == pytest.approx({"0.5": 0.085, "1.0": 0.17})
    assert calc["blur_px"]["1.0"] == pytest.approx(
        {
            "474": 0.7345147679324894,
            "480": 0.7253333333333334,
            "484": 0.7193388429752067,
        }
    )
    assert max(calc["blur_px"]["1.0"].values()) <= 0.75


def test_payload_throughput_and_compute_boundary(result: dict) -> None:
    calc = result["calculations"]
    assert calc["raw_payload_mbit_s"] == pytest.approx(
        {
            "bayer10_15hz": 629.1456,
            "bayer10_20hz": 838.8608,
            "bayer12_15hz": 754.97472,
            "bayer12_20hz": 1006.63296,
        }
    )
    assert calc["payload_with_headroom_mbit_s"] == pytest.approx(
        {
            "bayer10_15hz": 754.97472,
            "bayer10_20hz": 1006.63296,
            "bayer12_15hz": 905.969664,
            "bayer12_20hz": 1207.959552,
        }
    )
    assert calc["gross_geometric_throughput_ha_h"] == pytest.approx(
        {"0.5": 0.0799875, "1.0": 0.159975}
    )
    compute = calc["compute_proxy"]
    assert compute["halo_batch4_p95_ms"] == pytest.approx(52.67959251068532)
    assert compute["stage_e_deadline_ms"] == pytest.approx(
        66.66666666666667
    )
    assert compute["remaining_deadline_margin_ms"] == pytest.approx(
        13.98707415598135
    )
    assert compute["scope"] == "compute_proxy_not_end_to_end_physical_PASS"


def test_power_and_mechanical_unknowns_propagate_null(result: dict) -> None:
    power = result["calculations"]["power_status"]
    assert power["light_branch_average_maximum_w"] == 20.0
    assert power["capture_module_average_maximum_w_excluding_compute"] == 60.0
    assert power["gpu_reference_board_power_w_not_vehicle_draw"] == 350.0
    assert power["reference_system_psu_w_not_vehicle_draw"] == 750.0
    assert power["whole_compute_system_measured_w"] is None
    assert power["integrated_host_continuous_power_w"] is None
    assert power["integrated_host_transient_power_w"] is None

    mechanical = result["calculations"]["mechanical_payload"]
    assert mechanical["cassette_mass_kg"] is None
    assert mechanical["cassette_center_of_gravity_mm"] is None
    assert mechanical["payload_total_kg"] is None
    assert mechanical["moment_about_carrier_datum_Nm"] is None
    assert mechanical["center_of_gravity_from_carrier_datum_mm"] is None
    assert len(mechanical["missing_mass_component_ids"]) == 8
    assert len(mechanical["missing_distance_component_ids"]) == 8


def test_mechanical_payload_and_moment_formula_when_inputs_exist(config: dict) -> None:
    measured = deepcopy(config)
    components = measured["calculation_inputs"]["mechanical_payload_model"][
        "components"
    ]
    for index, component in enumerate(components, start=1):
        component["mass_kg"] = float(index)
        component["signed_distance_from_carrier_datum_mm"] = 100.0
        component["evidence_class"] = "PHYSICAL_MEASUREMENT"
    mechanical = derive_calculations(measured)["mechanical_payload"]
    assert mechanical["payload_total_kg"] == pytest.approx(36.0)
    assert mechanical["moment_about_carrier_datum_Nm"] == pytest.approx(
        36.0 * 9.80665 * 0.1
    )
    assert mechanical["center_of_gravity_from_carrier_datum_mm"] == pytest.approx(
        100.0
    )

    components[0]["signed_distance_from_carrier_datum_mm"] = None
    mechanical = derive_calculations(measured)["mechanical_payload"]
    assert mechanical["payload_total_kg"] == pytest.approx(36.0)
    assert mechanical["moment_about_carrier_datum_Nm"] is None
    assert mechanical["center_of_gravity_from_carrier_datum_mm"] is None


def test_power_aggregation_separates_ceilings_references_and_nulls(
    config: dict, result: dict
) -> None:
    power = result["calculations"]["power_status"]
    model = power["aggregation_model"]
    assert power["integrated_host_continuous_power_w"] is None
    assert power["integrated_host_transient_power_w"] is None
    assert model["field_evidence_class"][
        "capture_module_average_maximum_w_excluding_compute"
    ] == "ACCEPTANCE_CEILING"
    assert model["field_evidence_class"][
        "gpu_reference_board_power_w_not_vehicle_draw"
    ] == "REFERENCE_ONLY_NOT_VEHICLE_DRAW"
    assert model["field_evidence_class"][
        "whole_compute_system_measured_w"
    ] == "NO_EVIDENCE_NULL"

    measured = deepcopy(config)
    measured_power = measured["baseline"]["power_thermal"]
    measured_power["whole_compute_system_measured_w"] = 500.0
    measured_power["conversion_distribution_continuous_loss_w"] = 20.0
    calculated = derive_calculations(measured)["power_status"]
    assert calculated["integrated_host_continuous_power_w"] == pytest.approx(580.0)
    assert calculated["integrated_host_transient_power_w"] is None


def test_normalized_bom_totals_and_integrated_null_boundary(result: dict) -> None:
    totals = result["bom"]["totals"]
    assert totals["proof_module_before_contingency"] == [3115.0, 6545.0]
    assert totals["proof_module_with_contingency"] == [3582.25, 7526.75]
    assert totals["rear_carrier_engineering_screen_not_quote"] == [
        4300.0,
        14000.0,
    ]
    assert totals["bounded_proof_plus_carrier_screen_not_integrated_total"] == [
        7882.25,
        21526.75,
    ]
    assert totals["integrated_one_bay_total"] is None
    assert totals["integrated_total_complete"] is False
    item_blockers = {
        row["bom_item_id"]
        for row in totals["integrated_total_blockers"]
        if "bom_item_id" in row
    }
    assert item_blockers == {
        "exact_rear_carrier_cost",
        "exact_host_incremental_cost",
        "compute_opportunity_cost",
        "intervention_external_cost",
        "physical_acceptance_execution_cost",
    }
    assert any(
        row.get("double_count_group")
        == "host_integration_shared_pending_reconciliation"
        for row in totals["integrated_total_blockers"]
    )


def test_bom_source_binding_reuse_boundary_and_deterministic_csv(result: dict) -> None:
    rows = result["bom"]["items"]
    assert rows == sorted(
        rows,
        key=lambda row: (row["cost_scope"], row["owner"], row["bom_item_id"]),
    )
    for row in rows:
        receipt = result["source_integrity"]["sources"][row["source_id"]]
        assert row["source_path"] == receipt["path"]
        assert row["source_sha256"] == receipt["sha256"]

    reused = _bom_item(result, "existing_RTX3090_incremental_acquisition")
    opportunity = _bom_item(result, "compute_opportunity_cost")
    assert [reused["minimum_cost"], reused["maximum_cost"]] == [0.0, 0.0]
    assert reused["evidence_class"] == "EXISTING_ASSET_INCREMENTAL_ACQUISITION_ONLY"
    assert opportunity["minimum_cost"] is None
    assert opportunity["maximum_cost"] is None

    first = render_bom_csv(result["bom"])
    second = render_bom_csv(result["bom"])
    assert first == second
    assert first.endswith("\n")
    assert "\r" not in first
    csv_rows = list(csv.DictReader(io.StringIO(first)))
    assert [row["bom_item_id"] for row in csv_rows] == [
        row["bom_item_id"] for row in rows
    ]
    unknown = next(
        row for row in csv_rows if row["bom_item_id"] == "exact_rear_carrier_cost"
    )
    assert unknown["minimum_cost"] == ""
    assert unknown["maximum_cost"] == ""
    module_rows = [row for row in csv_rows if row["included_in_module_total"] == "true"]
    assert sum(float(row["minimum_cost"]) for row in module_rows) == 3115.0
    assert sum(float(row["maximum_cost"]) for row in module_rows) == 6545.0


def test_acceptance_binding_and_fail_safe_coverage(result: dict) -> None:
    binding = result["acceptance_binding"]
    assert binding["exact_contract_sha256"] == result["source_integrity"]["sources"][
        "rig_acceptance_contract"
    ]["sha256"]
    assert binding["evaluator_sha256"] == result["source_integrity"]["sources"][
        "rig_acceptance_evaluator"
    ]["sha256"]
    assert binding["controlled_capture_target"]["current_authorized"] is False
    assert binding["dry_marker_target"]["current_ready"] is False
    assert binding["chemical_target"]["allowed"] is False
    assert binding["integration_evaluates_physical_receipts"] is False
    assert binding["integration_can_override_rig_evaluator"] is False

    rows = result["fail_safe_interfaces"]
    assert {row["fault_id"] for row in rows} == set(
        result["baseline"]["safety"]["no_fire_on"]
    )
    for row in rows:
        assert "no_fire" in row["immediate_action"] or "hard_cut" in row[
            "immediate_action"
        ]
        assert row["pending_command_action"]
        assert row["recovery"]


def test_three_svg_views_are_deterministic_hash_bound_and_complete(
    result_with_identity: dict,
) -> None:
    architecture_payload = render_json(result_with_identity)
    architecture_sha256 = hashlib.sha256(
        architecture_payload.encode("utf-8")
    ).hexdigest()
    first = render_engineering_svgs(result_with_identity, architecture_sha256)
    second = render_engineering_svgs(result_with_identity, architecture_sha256)
    assert first == second
    assert list(first) == ["exterior.svg", "underside.svg", "optical_cross_section.svg"]
    assert len({hashlib.sha256(value.encode("utf-8")).hexdigest() for value in first.values()}) == 3

    view_rows = {
        row["filename"]: row for row in result_with_identity["visual_contract"]["views"]
    }
    for filename, payload in first.items():
        root = ElementTree.fromstring(payload)
        assert root.attrib["viewBox"] == "0 0 1400 900"
        assert root.attrib["data-architecture-sha256"] == architecture_sha256
        assert root.attrib["data-config-sha256"] == result_with_identity[
            "config_identity"
        ]["sha256"]
        assert payload.endswith("\n")
        assert "\r" not in payload
        assert str(PROJECT_ROOT) not in payload
        assert "NOT A FABRICATION DRAWING" in payload
        assert "chemical fire: false" in payload
        for annotation_id in view_rows[filename]["required_annotation_ids"]:
            assert f'data-annotation-id="{annotation_id}"' in payload

    assert "minimum 444.375 × 444.375 mm" in first["underside.svg"]
    assert "minimum clear hood: 600×600 mm" in first["underside.svg"]
    assert "not hood width · not nozzle footprint" in first["underside.svg"]
    assert "two-bay formula screen: 874.375 mm" in first["underside.svg"]
    assert "signed camera offset = UNRESOLVED" in first["exterior.svg"]
    assert "exact ray clearance = UNMEASURED" in first["optical_cross_section.svg"]
    assert "ExposureActive → strobe" in first["optical_cross_section.svg"]
    assert "FOV 474–484 mm at ground" in first["optical_cross_section.svg"]
    assert "safe ≥444.375 mm" in first["optical_cross_section.svg"]
    assert "{fov_range}" not in first["optical_cross_section.svg"]
    assert "{safe_width}" not in first["optical_cross_section.svg"]


def test_visual_manifest_hashes_every_exact_view(result_with_identity: dict) -> None:
    architecture_payload = render_json(result_with_identity)
    architecture_sha256 = hashlib.sha256(
        architecture_payload.encode("utf-8")
    ).hexdigest()
    views = render_engineering_svgs(result_with_identity, architecture_sha256)
    manifest_payload = render_visual_manifest(
        result_with_identity, architecture_sha256, views
    )
    manifest = json.loads(manifest_payload)
    assert manifest["architecture_sha256"] == architecture_sha256
    assert manifest["config_sha256"] == result_with_identity["config_identity"][
        "sha256"
    ]
    assert [row["filename"] for row in manifest["views"]] == list(views)
    for row in manifest["views"]:
        assert row["sha256"] == hashlib.sha256(
            views[row["filename"]].encode("utf-8")
        ).hexdigest()


def test_human_document_is_deterministic_source_bound_and_no_go(
    result_with_identity: dict,
) -> None:
    first = _render_package(result_with_identity)
    second = _render_package(result_with_identity)
    assert first == second
    document = first["document"]
    assert isinstance(document, str)
    assert document.endswith("\n")
    assert "\r" not in document
    assert str(PROJECT_ROOT) not in document
    assert "INTEGRATION_CONSISTENT_PRE_REAL" in document
    assert "PRE_REAL_NOT_READY" in document
    assert "Sourced facts" in document
    assert "Deterministic calculations" in document
    assert "Integration hypotheses" in document
    assert "Physically unmeasured" in document
    assert "current product-level physical receipt count is zero" in document
    assert "444.375 mm" in document
    assert "600×600 mm" in document
    assert "3582.25–7526.75" in document
    assert "Integrated one-bay total | `null`" in document
    assert "not an integrated product total" in document
    assert "no procurement, fabrication, physical READY" in document
    assert "chemical-fire" in document
    assert "NOT A FABRICATION DRAWING" in document
    assert "Source release closure" in document
    assert "a24f7dec956af170436bcb17d679aa53918c9ec8" in document
    assert "six terminal lane plans and surveys" in document
    assert document.count("[![") == 3
    for filename in ("exterior.svg", "underside.svg", "optical_cross_section.svg"):
        assert (
            f"results/spot_spray_product_architecture_v1/{filename}"
            in document
        )

    architecture_sha256 = hashlib.sha256(
        first["architecture"].encode("utf-8")
    ).hexdigest()
    bom_sha256 = hashlib.sha256(first["bom"].encode("utf-8")).hexdigest()
    visual_manifest_sha256 = hashlib.sha256(
        first["visual_manifest"].encode("utf-8")
    ).hexdigest()
    for digest in (architecture_sha256, bom_sha256, visual_manifest_sha256):
        assert digest in document
    for receipt in result_with_identity["source_integrity"]["sources"].values():
        assert receipt["path"] in document
        assert receipt["sha256"] in document

    document_path = PROJECT_ROOT / "docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md"
    local_links = set(re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", document))
    assert local_links
    for target in local_links:
        assert not Path(target).is_absolute()
        assert (document_path.parent / target).resolve().is_file()


def test_package_manifest_hashes_every_artifact_and_source(
    result_with_identity: dict,
) -> None:
    rendered = _render_package(result_with_identity)
    manifest = json.loads(rendered["package_manifest"])
    assert manifest["integration_result"] == "INTEGRATION_CONSISTENT_PRE_REAL"
    assert manifest["source_integrity"] == "PASS"
    assert manifest["verified_source_count"] == 19
    assert manifest["source_release"] == {
        "admission_policy": (
            "six_terminal_files_exact_bytes_at_reachable_commit_fail_closed"
        ),
        "implementation_base_commit": (
            "a24f7dec956af170436bcb17d679aa53918c9ec8"
        ),
        "terminal_source_count": 6,
        "terminal_sources_clean_against_commit": True,
    }
    assert manifest["status_axes"]["physical_acceptance"] == "PRE_REAL_NOT_READY"
    assert manifest["status_axes"]["field_go"] is False
    assert manifest["status_axes"]["product_go"] is False
    assert manifest["status_axes"]["chemical_fire_allowed"] is False
    assert manifest["status_axes"]["purchase_authorized"] is False
    assert manifest["evidence_ledger"] == result_with_identity["evidence_ledger"]
    assert manifest["manifest_self_identity"] == {
        "path": "docs/results/spot_spray_product_architecture_v1/package_manifest.json",
        "sha256": None,
        "reason": "self_digest_excluded_to_avoid_recursive_hash",
    }

    artifacts = {row["artifact_id"]: row for row in manifest["artifacts"]}
    assert len(artifacts) == 8
    payload_by_id = {
        "canonical_config": CONFIG_PATH.read_text(encoding="utf-8"),
        "architecture_json": rendered["architecture"],
        "normalized_bom_csv": rendered["bom"],
        "human_readable_architecture": rendered["document"],
        "visual_manifest": rendered["visual_manifest"],
        **{
            f"visual_{row['view_id']}": rendered["views"][row["filename"]]
            for row in result_with_identity["visual_contract"]["views"]
        },
    }
    assert set(artifacts) == set(payload_by_id)
    for artifact_id, payload in payload_by_id.items():
        assert artifacts[artifact_id]["sha256"] == hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()
        assert not Path(artifacts[artifact_id]["path"]).is_absolute()

    expected_sources = result_with_identity["source_integrity"]["sources"]
    source_rows = {row["source_id"]: row for row in manifest["source_inputs"]}
    assert set(source_rows) == set(expected_sources)
    for source_id, receipt in expected_sources.items():
        assert source_rows[source_id]["path"] == receipt["path"]
        assert source_rows[source_id]["sha256"] == receipt["sha256"]
        assert source_rows[source_id]["containing_commit"] == receipt.get(
            "containing_commit"
        )
        assert source_rows[source_id]["committed_bytes_verified"] is receipt.get(
            "committed_bytes_verified", False
        )


def test_each_material_item_has_one_owner_and_bounded_state(result: dict) -> None:
    items = result["decision_items"]
    item_ids = [item["item_id"] for item in items]
    assert len(item_ids) == len(set(item_ids))
    assert all(isinstance(item["owner"], str) and item["owner"] for item in items)
    assert _decision(result, "action_camera")["owner"] == "sensor_optics"
    assert _decision(result, "light_architecture")["owner"] == "light_enclosure"
    assert _decision(result, "proof_carrier_topology")["owner"] == (
        "platform_carrier"
    )
    assert _decision(result, "exact_rear_host")["decision_state"] == (
        "HOST_UNRESOLVED"
    )
    assert _decision(result, "installed_light_profile")["value"] is None
    assert _decision(result, "second_camera")["decision_state"] == (
        "CHALLENGER_CLOSED_NOT_TRIGGERED"
    )
    assert _decision(result, "chemical_enable") == {
        **_decision(result, "chemical_enable"),
        "decision_state": "UNSUPPORTED",
        "value": False,
    }
    for item in items:
        if item["decision_state"] in {"OPEN_BENCH_VARIABLE", "HOST_UNRESOLVED"}:
            assert item["resolution_trigger"]
            assert item["resolution_rule"]


def test_light_and_platform_frames_use_an_explicit_axis_permutation(
    result: dict,
) -> None:
    frames = result["coordinate_frames"]
    assert frames["cassette"]["x_axis"] == "forward_travel"
    assert frames["cassette"]["y_axis"] == "vehicle_right"
    assert frames["light_fixture"]["x_axis"] == "vehicle_right"
    assert frames["light_fixture"]["y_axis"] == "vehicle_front"
    assert frames["light_fixture_to_cassette"] == {
        "owner": "integration_only",
        "transform_type": "exact_axis_permutation_no_scale_no_reflection",
        "cassette_x_from": "light_fixture_y",
        "cassette_y_from": "light_fixture_x",
        "cassette_z_from": "light_fixture_z",
    }


def test_complete_coordinate_frame_and_interface_contract(result: dict) -> None:
    frames = result["coordinate_frames"]
    assert {
        frames[key]["frame_id"]
        for key in (
            "world",
            "carrier",
            "cassette",
            "camera",
            "ground_calibration",
            "light_fixture",
            "encoder",
            "intervention_mount",
        )
    } == {
        "F_world",
        "F_carrier",
        "F_cassette",
        "F_camera",
        "F_ground_calibration",
        "F_light_fixture",
        "F_encoder",
        "F_intervention_mount",
    }
    assert frames["carrier"]["transform_state"] == "HOST_UNRESOLVED"
    assert frames["camera"]["transform_state"] == (
        "INSTALLED_STAGE_C_MEASUREMENT_REQUIRED"
    )
    assert frames["intervention_mount"]["measured_along_track_offset_mm"] is None
    assert frames["intervention_mount"]["hardware_owner"] == (
        "intervention_external"
    )

    interfaces = {row["interface_id"]: row for row in result["interface_contract"]}
    assert len(interfaces) == 8
    assert all(row["no_fire_on_invalid"] is True for row in interfaces.values())
    assert interfaces["host_structure_to_carrier"]["value"] is None
    assert interfaces["host_power_to_regulated_distribution"]["value"] is None
    assert interfaces["camera_to_intervention_mount"]["value"] is None
    assert interfaces["safety_to_strobe_and_intervention_enable"]["value"] == (
        "default_no_fire_chemical_enable_verified_disabled"
    )


def test_spatial_no_intrusion_and_inactive_multi_bay_contract(result: dict) -> None:
    spatial = result["spatial_contract"]
    active = spatial["active_geometry"]
    assert active["active_bay_count"] == 1
    assert active["hood_internal_plan_minimum_mm"] == [600.0, 600.0]
    assert active["calibrated_ground_fov_range_mm"] == [474.0, 484.0]
    assert active["conservative_action_safe_plan_mm"] == [444.375, 444.375]
    assert active["intervention_footprint_mm"] is None
    assert active["exact_installed_optical_clearance_mm"] is None
    envelopes = {
        row["envelope_id"]: row for row in spatial["no_intrusion_envelopes"]
    }
    assert envelopes["installed_calibrated_ray_cone"][
        "exact_installed_shape_mm"
    ] is None
    assert "gauge_wheel" in envelopes["installed_calibrated_ray_cone"][
        "prohibited_intruders"
    ]
    assert envelopes["conservative_action_safe_ground_region"]["plan_mm"] == [
        444.375,
        444.375,
    ]

    multi = result["calculations"]["multi_bay_compatibility"]
    assert multi["current_active_bay_count"] == 1
    assert multi["multi_bay_currently_active"] is False
    assert multi["second_camera_currently_active"] is False
    assert multi["inactive_two_bay_safe_swath_at_max_pitch_mm"] == pytest.approx(
        874.375
    )
    assert multi[
        "inactive_two_bay_continuous_hood_width_at_max_pitch_mm"
    ] == pytest.approx(1030.0)
    assert multi["claim_limit"] == "compatibility_formula_only_not_current_capability"


def test_geometry_helpers_do_not_use_hood_width() -> None:
    assert safe_fraction(2048, 64) == pytest.approx(0.9375)
    assert 474.0 * safe_fraction(2048, 64) == pytest.approx(444.375)
    assert raw_payload_mbit_s(2048, 2048, 10, 15.0) == pytest.approx(629.1456)
    assert 600.0 not in (444.375, 450.0, 453.75)


def test_result_render_is_deterministic(config: dict) -> None:
    first = render_json(derive_contract(config, PROJECT_ROOT))
    second = render_json(derive_contract(config, PROJECT_ROOT))
    assert first == second
    assert first.endswith("\n")


def test_source_drift_fails_before_integration(
    config: dict, tmp_path: Path
) -> None:
    invalid = deepcopy(config)
    invalid["source_lock"]["terminal_surveys"][0]["sha256"] = "0" * 64
    with pytest.raises(SourceDriftError, match="INTEGRATION_INVALID_SOURCE_DRIFT"):
        derive_contract(invalid, PROJECT_ROOT)

    repository = tmp_path / "source-lock-repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    terminal_specs = {
        "terminal_plans": [
            ("sensor_optics_plan", "plans/sensor.md"),
            ("light_enclosure_plan", "plans/light.md"),
            ("platform_product_plan", "plans/platform.md"),
        ],
        "terminal_surveys": [
            ("sensor_optics_survey", "surveys/sensor.md"),
            ("light_enclosure_survey", "surveys/light.md"),
            ("platform_product_survey", "surveys/platform.md"),
        ],
    }
    for rows in terminal_specs.values():
        for source_id, relative_path in rows:
            path = repository / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{source_id}\n".encode("utf-8"))
    upstream_path = repository / "upstream/authority.txt"
    upstream_path.parent.mkdir(parents=True, exist_ok=True)
    upstream_path.write_bytes(b"authority\n")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Source Lock Test",
            "-c",
            "user.email=source-lock@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Freeze terminal sources",
        ],
        check=True,
    )
    base_commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    source_lock: dict[str, object] = {
        "algorithm": "sha256_exact_bytes",
        "admission_policy": (
            "six_terminal_files_exact_bytes_at_reachable_commit_fail_closed"
        ),
        "implementation_base_commit": base_commit,
        "upstream_authorities": [
            {
                "source_id": "upstream_authority",
                "path": "upstream/authority.txt",
                "sha256": hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
                "owner": "test",
                "role": "test_authority",
            }
        ],
    }
    for group, rows in terminal_specs.items():
        source_lock[group] = [
            {
                "source_id": source_id,
                "path": relative_path,
                "sha256": hashlib.sha256(
                    (repository / relative_path).read_bytes()
                ).hexdigest(),
                "containing_commit": base_commit,
                "owner": "test",
                "role": "test_terminal_source",
            }
            for source_id, relative_path in rows
        ]
    synthetic = {"source_lock": source_lock}
    assert len(verify_source_lock(synthetic, repository)) == 7
    for rows in terminal_specs.values():
        for _, relative_path in rows:
            path = repository / relative_path
            original = path.read_bytes()
            path.write_bytes(original + b"x")
            with pytest.raises(
                SourceDriftError, match="INTEGRATION_INVALID_SOURCE_DRIFT"
            ):
                verify_source_lock(synthetic, repository)
            path.write_bytes(original)


def test_canonical_acceptance_drift_fails_closed(config: dict) -> None:
    invalid = deepcopy(config)
    rig = next(
        row
        for row in invalid["source_lock"]["upstream_authorities"]
        if row["source_id"] == "rig_acceptance_contract"
    )
    rig["canonical_sha256"] = "0" * 64
    with pytest.raises(SourceDriftError, match="canonical policy"):
        derive_contract(invalid, PROJECT_ROOT)


def test_source_path_cannot_escape_repository(config: dict) -> None:
    invalid = deepcopy(config)
    invalid["source_lock"]["terminal_surveys"][0]["path"] = "../outside.md"
    with pytest.raises(ValueError, match="escapes repository"):
        derive_contract(invalid, PROJECT_ROOT)


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("schema_version: 1\nschema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConstructorError, match="duplicate mapping key"):
        load_yaml_mapping(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda cfg: cfg["decision_items"][0].update(
                {"decision_state": "READY"}
            ),
            "Unknown decision state",
        ),
        (
            lambda cfg: cfg["decision_items"][0].update({"value": None}),
            "cannot be null",
        ),
        (
            lambda cfg: next(
                item
                for item in cfg["decision_items"]
                if item["item_id"] == "chemical_enable"
            ).update({"value": True}),
            "chemical_enable",
        ),
    ],
)
def test_status_promotion_and_null_frozen_value_are_rejected(
    config: dict, mutation, message: str
) -> None:
    invalid = deepcopy(config)
    mutation(invalid)
    with pytest.raises(ValueError, match=message):
        derive_contract(invalid, PROJECT_ROOT)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("baseline", "sensor_optics", "camera_count"), 2, "proof camera count"),
        (
            ("baseline", "sensor_optics", "acquisition_rate_hz"),
            20.0,
            "proof acquisition rate",
        ),
        (
            (
                "baseline",
                "light_enclosure",
                "hood_internal_plan_minimum_mm",
            ),
            [444.375, 444.375],
            "proof hood plan",
        ),
        (
            ("calculation_inputs", "outer_abstain_ring_px"),
            0,
            "golden safe fraction",
        ),
    ],
)
def test_baseline_and_golden_mutations_fail_closed(
    config: dict, path: tuple[str, ...], value, message: str
) -> None:
    invalid = deepcopy(config)
    target = invalid
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(CrossLaneConflictError, match=message):
        derive_contract(invalid, PROJECT_ROOT)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda cfg: cfg["status_axes"].update({"physical_ready": True}),
            "Unauthorized readiness/status promotion",
        ),
        (
            lambda cfg: cfg["acceptance_binding"]["controlled_capture_target"].update(
                {"current_authorized": True}
            ),
            "controlled capture authority",
        ),
        (
            lambda cfg: cfg["acceptance_binding"]["dry_marker_target"].update(
                {"current_ready": True}
            ),
            "dry-marker readiness",
        ),
        (
            lambda cfg: cfg["acceptance_binding"]["chemical_target"].update(
                {"allowed": True}
            ),
            "chemical target",
        ),
    ],
)
def test_forged_acceptance_and_readiness_promotions_are_rejected(
    config: dict, mutation, message: str
) -> None:
    invalid = deepcopy(config)
    mutation(invalid)
    with pytest.raises(ValueError, match=message):
        derive_contract(invalid, PROJECT_ROOT)


def test_fail_safe_coverage_and_action_mutations_are_rejected(config: dict) -> None:
    missing = deepcopy(config)
    missing["fail_safe_interfaces"].pop()
    with pytest.raises(ValueError, match="exactly cover"):
        derive_contract(missing, PROJECT_ROOT)

    unsafe = deepcopy(config)
    unsafe["fail_safe_interfaces"][0]["immediate_action"] = "hold_last_command"
    with pytest.raises(ValueError, match="not fail closed"):
        derive_contract(unsafe, PROJECT_ROOT)


def test_bom_double_count_and_unknown_zero_mutations_are_rejected(
    config: dict,
) -> None:
    duplicate = deepcopy(config)
    row = next(
        item
        for item in duplicate["bom_contract"]["items"]
        if item["bom_item_id"]
        == "host_integration_cooling_and_dedicated_USB_controller"
    )
    row["included_in_integrated_total"] = True
    with pytest.raises(ValueError, match="double-count group included twice"):
        derive_contract(duplicate, PROJECT_ROOT)

    false_zero = deepcopy(config)
    row = next(
        item
        for item in false_zero["bom_contract"]["items"]
        if item["bom_item_id"] == "exact_host_incremental_cost"
    )
    row.update(
        {
            "minimum_cost": 0.0,
            "maximum_cost": 0.0,
            "evidence_class": "BUDGETARY_ALLOWANCE",
            "price_checked_on": "2026-08-14",
            "unknown_reason": None,
        }
    )
    with pytest.raises(ValueError, match="Zero BOM cost is allowed only"):
        derive_contract(false_zero, PROJECT_ROOT)


def test_source_bom_cost_drift_is_a_cross_lane_conflict(config: dict) -> None:
    invalid = deepcopy(config)
    row = next(
        item
        for item in invalid["bom_contract"]["items"]
        if item["bom_item_id"] == "camera_a2A2464_77ucPRO"
    )
    row["minimum_cost"] = 710.0
    with pytest.raises(CrossLaneConflictError, match="BOM minimum"):
        derive_contract(invalid, PROJECT_ROOT)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda cfg: cfg["baseline"]["platform_carrier"][
                "multi_bay_compatibility"
            ].update({"multi_bay_currently_active": True}),
            "multi-bay active state",
        ),
        (
            lambda cfg: cfg["spatial_contract"]["active_geometry"].update(
                {"action_safe_lateral_width_minimum_mm": 600.0}
            ),
            "spatial safe width",
        ),
        (
            lambda cfg: next(
                row
                for row in cfg["interface_contract"]
                if row["interface_id"] == "camera_to_intervention_mount"
            ).update({"value": 250.0}),
            "unresolved interface camera_to_intervention_mount",
        ),
        (
            lambda cfg: next(
                row
                for row in cfg["interface_contract"]
                if row["interface_id"] == "camera_to_compute_data"
            ).update({"no_fire_on_invalid": False}),
            "must fail closed",
        ),
        (
            lambda cfg: cfg["coordinate_frames"]["camera"].update(
                {"x_axis": "vehicle_right"}
            ),
            r"frame \+X camera",
        ),
    ],
)
def test_drawing_contract_mutations_fail_closed(
    config: dict, mutation, message: str
) -> None:
    invalid = deepcopy(config)
    mutation(invalid)
    with pytest.raises((ValueError, CrossLaneConflictError), match=message):
        derive_contract(invalid, PROJECT_ROOT)


def test_missing_required_svg_annotation_fails_generation(
    result_with_identity: dict,
) -> None:
    invalid = deepcopy(result_with_identity)
    next(
        row
        for row in invalid["visual_contract"]["views"]
        if row["view_id"] == "exterior"
    )["required_annotation_ids"].append("nonexistent_annotation")
    architecture_sha256 = hashlib.sha256(
        render_json(invalid).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="nonexistent_annotation"):
        render_engineering_svgs(invalid, architecture_sha256)


def test_generated_artifact_set_matches_current_contract(
    result_with_identity: dict,
) -> None:
    architecture_path = (
        PROJECT_ROOT
        / "docs/results/spot_spray_product_architecture_v1/architecture.json"
    )
    bom_path = PROJECT_ROOT / "docs/results/spot_spray_product_architecture_v1/bom.csv"
    rendered = _render_package(result_with_identity)
    assert architecture_path.read_text(encoding="utf-8") == rendered[
        "architecture"
    ]
    assert bom_path.read_text(encoding="utf-8") == rendered["bom"]
    result_root = architecture_path.parent
    for filename, payload in rendered["views"].items():
        assert (result_root / filename).read_text(encoding="utf-8") == payload
    assert (result_root / "visual_manifest.json").read_text(
        encoding="utf-8"
    ) == rendered["visual_manifest"]
    assert (result_root / "package_manifest.json").read_text(
        encoding="utf-8"
    ) == rendered["package_manifest"]
    assert (
        PROJECT_ROOT / "docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md"
    ).read_text(encoding="utf-8") == rendered["document"]
