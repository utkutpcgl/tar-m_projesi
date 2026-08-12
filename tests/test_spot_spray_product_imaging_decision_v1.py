from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.evaluate_spot_spray_rig_acceptance_v1 import (
    DEFAULT_CONTRACT_CANONICAL_SHA256,
    DEFAULT_CONTRACT_SHA256,
    canonical_mapping_sha256,
    load_yaml_mapping,
    sha256_file,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = (
    PROJECT_ROOT / "configs/deploy/spot_spray_product_imaging_decision_v1.yaml"
)
DOCUMENT_PATH = PROJECT_ROOT / "docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md"
V2_PATH = PROJECT_ROOT / "configs/deploy/spot_spray_capture_optimization_v2.yaml"
RIG_PATH = PROJECT_ROOT / "configs/deploy/spot_spray_rig_acceptance_v1.yaml"
METRICS_PATH = (
    PROJECT_ROOT
    / "docs/results/kontrollu_spot_spray_poc_v1/metrics_summary.json"
)


@pytest.fixture(scope="module")
def decision() -> dict:
    return load_yaml_mapping(DECISION_PATH)


@pytest.fixture(scope="module")
def v2() -> dict:
    loaded = yaml.safe_load(V2_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_decision_pins_exact_planner_and_frozen_contract_sources(
    decision: dict,
) -> None:
    sources = decision["source_identity"]
    for key in (
        "planner",
        "frozen_capture_contract",
        "frozen_capture_decision_document",
        "rig_acceptance_evaluator",
        "market_and_ceiling_review",
    ):
        source = sources[key]
        assert sha256_file(PROJECT_ROOT / source["path"]) == source["sha256"]

    assert sources["planner"]["commit"] == (
        "f1865879815de6ee4516a700fbc7722c5bf30ae0"
    )
    rig_source = sources["rig_acceptance_contract"]
    assert sha256_file(RIG_PATH) == rig_source["exact_byte_sha256"]
    assert rig_source["exact_byte_sha256"] == DEFAULT_CONTRACT_SHA256
    rig = load_yaml_mapping(RIG_PATH)
    assert canonical_mapping_sha256(rig) == rig_source[
        "canonical_policy_sha256"
    ]
    assert rig_source["canonical_policy_sha256"] == (
        DEFAULT_CONTRACT_CANONICAL_SHA256
    )


def test_baseline_is_a_consistent_projection_of_frozen_v2(
    decision: dict, v2: dict
) -> None:
    baseline = decision["baseline_proof_module"]
    v2_camera = v2["camera_shortlist"][0]
    v2_optics = v2["baseline_optics"]
    v2_capture = v2_optics["roi"]
    v2_geometry = v2_optics["geometry"]
    v2_gate = v2_optics["nine_region_gate"]

    assert baseline["purchase_quantity"] == 1
    assert baseline["camera"]["model"] == v2_camera["model"]
    assert baseline["camera"]["order_number"] == v2_camera["order_number"]
    assert baseline["camera"]["shutter"] == "global"
    assert baseline["camera"]["power"] == "external_12_to_24_VDC"
    assert baseline["lens"]["model"] == v2_optics["lens"]["model"]
    assert baseline["lens"]["order_number"] == v2_optics["lens"][
        "order_number"
    ]
    assert baseline["capture"]["native_roi_px"] == v2_capture[
        "centered_native_px"
    ]
    assert baseline["capture"]["native_roi_offset_px"] == v2_capture[
        "centered_native_offset_px"
    ]
    assert baseline["capture"]["ground_FOV_range_mm"] == v2_geometry[
        "target_ground_FOV_mm"
    ]
    assert baseline["capture"]["working_distance_adjustment_mm"] == (
        v2_geometry["working_distance_adjustment_mm"]
    )
    assert baseline["capture"]["exposure_us"] == v2[
        "motion_and_observation"
    ]["frozen_exposure_us"]
    assert baseline["capture"]["acquisition_rate_hz"] == v2[
        "motion_and_observation"
    ]["acquisition_rate_hz"]["baseline"]

    optical = baseline["optical_acceptance"]
    assert optical["region_count"] * optical["plane_count"] == 27
    assert optical["local_GSD_maximum_mm_px"] == v2_gate[
        "local_gsd_maximum_mm_px"
    ]
    assert optical["span_10mm_minimum_px"] == v2_gate[
        "minimum_10_mm_span_px"
    ]
    assert optical["span_20mm_minimum_px"] == v2_gate[
        "minimum_20_mm_span_px"
    ]
    assert optical["all_27_cells_must_pass"] is True


def test_20mm_service_class_is_conservative_and_prediction_independent(
    decision: dict,
) -> None:
    service = decision["first_service_class"]
    eligibility = service["eligibility"]
    assert eligibility == {
        "canopy_span_mm_minimum": 20.0,
        "visible_fraction_minimum_in_at_least_one_observation": 0.70,
        "partial_must_be_false_in_that_observation": True,
        "denominator_frozen_before_predictions": True,
        "once_eligible_track_remains_in_denominator": True,
    }
    gsd = decision["baseline_proof_module"]["optical_acceptance"][
        "local_GSD_maximum_mm_px"
    ]
    assert 20.0 / gsd >= 82.0
    assert 10.0 / gsd >= 41.0
    assert 5.0 / gsd < 21.0
    assert "abstain" in service["size_bands"]["10_to_below_20_mm"]
    assert service["status"].startswith("PROVISIONAL")


def test_one_camera_price_performance_and_environmental_boundaries_are_explicit(
    decision: dict,
) -> None:
    scale = decision["camera_count_and_swath"]
    assert scale["frozen_proof_camera_count"] == 1
    assert scale["minimum_action_safe_swath_mm"] == pytest.approx(444.375)
    assert len(scale["multi_camera_conditions_all_required"]) == 4
    assert scale["current_two_camera_decision"] == "BLOCKED_NOT_PURCHASED"

    economics = decision["price_performance"]
    assert economics["BAS_camera_saving_usd"] == 90.0
    assert economics["BAS_saving_fraction_of_low_module_subtotal"] == (
        pytest.approx(90.0 / 3115.0)
    )
    assert economics[
        "FLIR_camera_price_ratio_vs_PRO_using_challenger_favoring_lower_bound"
    ] == pytest.approx(1304.0 / 709.0)
    assert economics["prices_are_landed_quotes"] is False

    environment = decision["hood_light_and_functional_ruggedization"][
        "environmental_claim"
    ]
    assert decision["baseline_proof_module"]["camera"][
        "bare_camera_ingress_rating"
    ] == "IP30"
    assert environment["current_level"] == "functional_proof_enclosure_only"
    assert environment["certified_IP_claim"] is False
    assert environment[
        "rain_washdown_heavy_dust_shock_vibration_certified"
    ] is False


def test_procurement_and_physical_status_fail_closed(decision: dict) -> None:
    procurement = decision["procurement_boundary"]
    assert procurement["owner_approval_required"] is True
    assert procurement["current_supplier_quote_available"] is False
    assert procurement["currently_authorized_for_purchase"] is False
    assert procurement[
        "maximum_initial_proof_sets_after_quote_and_owner_approval"
    ] == 1
    assert "second_camera" in procurement["blocked_initial_items"]
    assert "FLIR_challenger" in procurement["blocked_initial_items"]

    physical = decision["physical_stage_state"]
    for stage in (
        "A_procurement_and_identity",
        "B_transport_trigger_and_thermal",
        "C_optics_and_window",
        "D_light_hood_and_polarization",
        "E_motion_tracking_and_compute",
    ):
        assert physical[stage] == "NOT_MEASURED"
    assert physical["current_result"] == "PRE_REAL_NOT_READY"
    assert physical["A_E_PASS_result_label"] == (
        "FROZEN_FOR_CONTROLLED_CAPTURE"
    )
    assert "CHEMICAL_FIRE_GO" in physical["prohibited_result_labels"]

    evidence = decision["evidence_policy"]
    assert evidence["physical_A_E_available"] is False
    assert evidence["controlled_capture_ready"] is False
    assert evidence["physical_field_go"] is False
    assert evidence["chemical_fire_go"] is False
    assert evidence["synthetic_and_external_OOD_real_decision_weight"] == 0.0


def test_selected_foundation_and_current_report_status_remain_consistent(
    decision: dict,
) -> None:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    compute = decision["baseline_proof_module"]["compute"]
    assert compute["selected_pre_real_foundation_checkpoint_sha256"] == (
        metrics["target_rig_contracts"]["selected_foundation"][
            "checkpoint_sha256"
        ]
    )
    assert compute["measured_compute_proxy_checkpoint_sha256"] != (
        compute["selected_pre_real_foundation_checkpoint_sha256"]
    )
    assert "Re-run Stage E" in compute["checkpoint_change_rule"]
    assert metrics["target_rig_contracts"]["overall_status"] == (
        "PRE_REAL_NOT_READY"
    )
    assert metrics["target_rig_contracts"]["field_fire_status"] == "NO-GO"
    assert metrics["target_rig_contracts"]["chemical_fire_status"] == (
        "NO-GO_UNSUPPORTED"
    )


def test_human_document_is_self_contained_and_does_not_overclaim() -> None:
    document = DOCUMENT_PATH.read_text(encoding="utf-8")
    for heading in (
        "Yönetici özeti",
        "Neyi gerçekten araştırdık?",
        "Neden bu kamera ve neden yalnız bir tane?",
        "Hood ve aydınlatma kararı",
        "Rugged ve IP konusunda dürüst sınır",
        "Frozen, provisional ve kapalı kararlar",
        "Satın alma sınırı",
        "En az maliyetle kanıt sırası",
        "Bugünün net sonucu",
    ):
        assert f"## {heading}" in document
    for evidence_phrase in (
        "2048×1536",
        "1,3 MP",
        "120×180 mm",
        "36` yüksek çözünürlük kamera",
        "altı RGB+3D vision modülü",
        "IP30",
        "PRE_REAL",
        "FROZEN_FOR_CONTROLLED_CAPTURE",
    ):
        assert evidence_phrase in document
    assert "satın alma yapılmış veya yetkilendirilmiş değildir" in document
    assert "nihai saha ürününün ideal olduğu iddiası değildir" in document
