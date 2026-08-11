from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.derive_spot_spray_capture_optimization_v2 import (
    PROJECT_ROOT,
    blur_px,
    depth_of_field_mm,
    derive,
    max_exposure_us,
    minimum_periodic_observations,
    render,
    sha256_file,
    thin_lens_fov_mm,
    transport_rate_mbps,
    working_distance_for_fov_mm,
)


CONFIG_PATH = PROJECT_ROOT / "configs/deploy/spot_spray_capture_optimization_v2.yaml"
RESULT_PATH = PROJECT_ROOT / "docs/results/controlled_capture_optimization_v2.json"
DOCUMENT_PATH = PROJECT_ROOT / "docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md"


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result(config: dict) -> dict:
    return derive(config, PROJECT_ROOT)


def _compute_row(result: dict, camera_count: int, frame_rate_hz: float) -> dict:
    return next(
        row
        for row in result["tiling_and_scalable_swath"]["compute_consequence"]
        if row["camera_count"] == camera_count
        and row["frame_rate_hz_each"] == frame_rate_hz
    )


def test_optical_motion_and_transport_formulae() -> None:
    fov = thin_lens_fov_mm(7.0656, 8.0, 550.0)
    assert fov == pytest.approx(478.6944)
    assert working_distance_for_fov_mm(7.0656, 8.06, 480.0) == pytest.approx(
        555.6143478260869
    )
    gsd = fov / 2048
    assert max_exposure_us(gsd, 1.0, 0.75) == pytest.approx(175.303125)
    assert blur_px(gsd, 1.0, 170.0) == pytest.approx(0.7273116504)
    assert minimum_periodic_observations(444.636, 1.0, 12.0) == 5
    assert transport_rate_mbps(2048, 2048, 10, 15.0) == pytest.approx(
        629.1456
    )

    dof = depth_of_field_mm(8.0, 5.6, 0.00345, 500.0)
    assert dof["near_mm"] == pytest.approx(435.4775998)
    assert dof["far_mm"] == pytest.approx(586.9679146)


def test_baseline_optics_and_nine_region_guarantee(config: dict, result: dict) -> None:
    decision = result["decision"]
    optics = result["optical_proof"]
    assert decision["proof_camera_count"] == 1
    assert decision["baseline_camera"] == "a2A2464-77ucPRO"
    assert decision["lower_cost_fallback"] == "a2A2464-77ucBAS"
    assert decision["working_distance_adjustment_mm"] == [520.0, 590.0]
    assert decision["nominal_working_distance_ground_mm"] == pytest.approx(
        555.6143478260869
    )
    assert optics["catalog_focal_length_range_mm"] == pytest.approx(
        [7.657, 8.463]
    )
    assert optics["FOV_range_mm"] == pytest.approx([474.0, 484.0])
    assert optics["GSD_range_mm_px"] == pytest.approx(
        [0.2314453125, 0.236328125]
    )
    assert optics["worst_case_10_mm_span_px"] >= 41.0
    assert optics["worst_case_20_mm_span_px"] >= 82.0
    assert optics["analytic_DOF"]["near_mm"] <= 445.0
    assert optics["analytic_DOF"]["far_mm"] >= 555.0
    assert optics["minimum_near_DOF_margin_mm"] >= 6.0
    assert optics["minimum_far_DOF_margin_mm"] >= 27.0

    gate = config["baseline_optics"]["nine_region_gate"]
    assert len({tuple(center) for center in gate["normalized_centers"]}) == 9
    assert gate["pass_rule"] == (
        "every_region_at_every_test_plane_must_pass_without_averaging"
    )
    assert 10.0 / gate["local_gsd_maximum_mm_px"] >= 41.0
    assert 20.0 / gate["local_gsd_maximum_mm_px"] >= 82.0


def test_measured_halo_compute_supports_only_one_camera_baseline(result: dict) -> None:
    swath = result["tiling_and_scalable_swath"]
    assert swath["measured_halo_batch4_mean_ms"] == pytest.approx(
        46.06308924655119
    )
    assert swath["measured_halo_batch4_p95_ms"] == pytest.approx(
        52.67959251068532
    )
    one_15 = _compute_row(result, 1, 15.0)
    one_20 = _compute_row(result, 1, 20.0)
    two_12 = _compute_row(result, 2, 12.0)
    two_15 = _compute_row(result, 2, 15.0)
    assert one_15["p95_service_utilization_fraction"] == pytest.approx(
        0.7901938876602798
    )
    assert one_15["p95_compute_only_supported"] is True
    assert one_20["p95_service_utilization_fraction"] == pytest.approx(
        1.0535918502137063
    )
    assert one_20["p95_compute_only_supported"] is False
    assert two_12["p95_service_utilization_fraction"] == pytest.approx(
        1.2643102202564476
    )
    assert two_12["p95_compute_only_supported"] is False
    assert two_15["tile_demand_per_s"] == pytest.approx(120.0)
    assert "not a batch-8" in swath["multi_camera_extrapolation_rule"]
    assert swath["maximum_module_center_pitch_mm"] == 430.0
    assert swath[
        "worst_case_safe_swath_overlap_at_maximum_pitch_mm"
    ] == pytest.approx(14.375)
    assert swath["minimum_valid_union_width_mm_by_camera_count"]["2"] == pytest.approx(
        874.375
    )
    assert swath["continuous_hood_internal_width_mm_by_camera_count"] == {
        "1": 600.0,
        "2": 1030.0,
        "3": 1460.0,
    }


def test_price_performance_bom_and_supply_decision(result: dict) -> None:
    camera = result["camera_price_performance"]
    assert camera["price_date"] == "2026-08-11"
    assert "lower bound to favor the challenger" in camera[
        "range_comparison_rule"
    ]
    shortlist = camera["shortlist"]
    assert [item["model"] for item in shortlist] == [
        "a2A2464-77ucPRO",
        "a2A2464-77ucBAS",
        "BFS-U3-51S5C-C",
    ]
    assert [item["price"]["amount"] for item in shortlist[:2]] == [709.0, 619.0]
    assert all(item["shutter"] == "global" for item in shortlist)
    assert all(item["matched_lens_model"] == "C23-0824-5M-P" for item in shortlist)
    assert shortlist[0]["power"] == "USB3_or_12_to_24_VDC"
    assert shortlist[1]["power"] == "USB3_only"
    challenger = shortlist[2]
    assert challenger["full_frame_rate_hz_by_raw_format"]["BayerRG10p"] == 49.0
    assert challenger["public_availability"] == (
        "varies_DigiKey_available_to_order_Edmund_US_in_stock"
    )
    assert challenger["price"] == {
        "minimum_amount": 1304.0,
        "maximum_amount": 1557.78,
        "comparison_amount": 1304.0,
        "comparison_basis": "lower_bound_to_favor_challenger",
        "currency": "USD",
        "kind": "current_supplier_listing_range",
        "source_keys": ["flir_camera_price_digikey", "flir_camera_price_edmund"],
    }
    assert challenger[
        "price_per_max_fps_using_comparison_amount"
    ] == pytest.approx(1304.0 / 73.0)
    assert challenger[
        "price_ratio_vs_selected_baseline_using_comparison_amount"
    ] == pytest.approx(1304.0 / 709.0)
    assert challenger[
        "price_per_max_fps_using_comparison_amount"
    ] < 1557.78 / 73.0
    lens = camera["matched_lens"]
    assert lens["model"] == "C23-0824-5M-P"
    assert lens["order_number"] == 2200000568
    assert lens["catalog_focal_length_range_mm"] == pytest.approx(
        [7.657, 8.463]
    )
    assert lens["price"]["amount"] == 136.0

    bom = result["bom_budget"]
    assert bom["subtotal_range"] == pytest.approx([3115.0, 6545.0])
    assert bom["with_contingency_range"] == pytest.approx(
        [3582.25, 7526.75]
    )
    assert bom["lower_cost_fallback_savings"] == pytest.approx(90.0)


def test_speed_exposure_observations_strobe_and_synthetic_match(result: dict) -> None:
    fastest = next(
        row
        for row in result["motion_and_track_observation"]
        if row["speed_m_s"] == 1.0
    )
    assert fastest["maximum_exposure_us_at_blur_limit"] == pytest.approx(
        177.24609375
    )
    assert fastest["blur_px_at_frozen_exposure"] == pytest.approx(
        0.7193388430
    )
    observations = [
        row["minimum_action_safe_observations"]
        for row in fastest["observation_envelope"]
    ]
    assert observations == [
        5,
        6,
        8,
    ]

    transport = result["camera_transport_payload"]
    assert transport[1]["Bayer10_packed_payload_mbps"] == pytest.approx(
        629.1456
    )
    strobe = result["strobe_duty_and_power_envelope"]
    assert strobe["nominal_peak_energy_ceiling_j_per_pulse"] == pytest.approx(
        0.036
    )
    assert strobe["conservative_local_storage_prescreen_uF"] == pytest.approx(
        1250.0
    )
    assert strobe["unmeasured_lux_or_energy_is_frozen"] is False

    synthetic = result["synthetic_envelope"]
    match = synthetic["derived_optical_match"]
    optics = result["optical_proof"]
    assert match["ground_FOV_range_mm"] == optics["FOV_range_mm"]
    assert match["ground_GSD_range_mm_px"] == optics["GSD_range_mm_px"]
    assert synthetic["real_GO_score_weight"] == 0.0
    assert synthetic["geometry"]["active_centered_ROI_offset_px"] == [200, 0]


def test_physical_module_calibration_and_safety_interfaces_are_explicit(
    config: dict,
) -> None:
    light = config["illumination"]
    assert light["camera_exposure_us"] == 170.0
    assert light["nominal_pulse_us"] == 150.0
    assert light["trigger_to_light_jitter_p95_maximum_us"] == 5.0
    assert "no frozen physical value" in light["bench_variable_rule"]
    assert light["thermal_gates"]["soak_duration_minutes"] == 120

    hood = config["hood_and_window"]
    assert hood["shell"]["minimum_internal_plan_mm"] == [600.0, 600.0]
    assert hood["skirt"]["layers"] == 2
    assert hood["labyrinth"]["stages"] == 2
    assert "unmeasured ambient challenge cannot pass" in hood["ambient_acceptance"]

    interfaces = config["interfaces"]
    assert interfaces["camera_transport"]["dedicated_USB3_root_controller_per_camera"]
    assert interfaces["time_and_encoder"]["host_arrival_timestamp_for_control_forbidden"]
    assert "measured_camera_to_nozzle_offset_mm" in interfaces["calibration"][
        "command_encoder_position_formula"
    ]
    assert interfaces["safety"]["watchdog_default"] == "no_fire"
    assert interfaces["safety"]["emergency_stop_hard_cuts_strobe_and_valve_enable"]


def test_sources_stages_and_human_contract_cover_every_requested_decision(
    config: dict,
) -> None:
    assert all(
        str(source["checked_on"]) == "2026-08-11"
        for source in config["authoritative_sources"].values()
    )
    assert [stage["stage"] for stage in config["bench_acceptance_stages"]] == [
        "A_procurement_and_identity",
        "B_transport_trigger_and_thermal",
        "C_optics_and_window",
        "D_light_hood_and_polarization",
        "E_motion_tracking_and_compute",
        "F_registration_and_safe_actuation",
    ]
    document = DOCUMENT_PATH.read_text(encoding="utf-8")
    assert config["authoritative_sources"]["flir_camera_price_digikey"][
        "url"
    ].startswith("https://www.digikey.com/")
    assert config["authoritative_sources"]["flir_camera_price_edmund"][
        "url"
    ].startswith("https://www.edmundoptics.com/")
    assert "1.304–1.557,78 USD" in document
    assert "1.304 USD / 73 fps" in document
    removed_duplicate_claim = "üretici dokümanıyla " + "uyumludur"
    assert removed_duplicate_claim not in document
    for required_heading in (
        "Satın alınabilir kamera ve lens kısa listesi",
        "Optik, FOV, GSD, fokus ve DOF kontratı",
        "Karo, kamera adedi ve ölçeklenebilir swath",
        "RTX 3090 hesap kanıtı",
        "Hız, pozlama, motion blur, FPS ve track gözlemi",
        "Diffuse strobe, güç ve termal kontrat",
        "Hood, skirt, labyrinth ve pencere",
        "Encoder, zaman, kalibrasyon, nozzle ve safety arayüzleri",
        "Baseline BOM ve bütçe",
        "Eşleşen sentetik kamera, ışık ve domain-randomization zarfı",
    ):
        assert f"## {required_heading}" in document


def test_all_analytic_gates_pass_and_committed_result_is_reproducible(
    config: dict, result: dict
) -> None:
    assert result["baseline_analytic_checks_pass"] is True
    assert all(result["baseline_analytic_checks"].values())
    expected = deepcopy(result)
    expected["source_integrity"]["derivation_config"] = {
        "path": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
        "sha256": sha256_file(CONFIG_PATH),
    }
    assert RESULT_PATH.read_text(encoding="utf-8") == render(expected)
    committed = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert committed["manager_validation_required"] is True
    assert committed["status"] == "READY_FOR_MANAGER_VALIDATION"


def test_invalid_active_sensor_span_fails_closed(config: dict) -> None:
    invalid = deepcopy(config)
    invalid["baseline_optics"]["roi"]["active_sensor_span_mm"] = 7.0
    with pytest.raises(ValueError, match="sensor span"):
        derive(invalid, PROJECT_ROOT)


def test_supplier_range_comparison_must_use_challenger_favoring_lower_bound(
    config: dict,
) -> None:
    invalid = deepcopy(config)
    invalid["camera_shortlist"][2]["public_price"]["comparison_amount"] = 1400.0
    with pytest.raises(ValueError, match="lower bound"):
        derive(invalid, PROJECT_ROOT)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: thin_lens_fov_mm(7.0, 8.0, 8.0), "exceed"),
        (lambda: max_exposure_us(0.2, 0.0, 0.75), "positive"),
        (lambda: transport_rate_mbps(0, 2048, 10, 15.0), "positive"),
    ],
)
def test_formulae_fail_closed(call, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()
