#!/usr/bin/env python3
"""Derive the controlled spot-spray capture V2 quantitative contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/deploy/spot_spray_capture_optimization_v2.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/results/controlled_capture_optimization_v2.json"


def positive(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def normalized_public_price(price: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Normalize a scalar listing or a conservative supplier-listing range."""
    currency = price["currency"]
    kind = price["kind"]
    if "amount" in price:
        if any(
            key in price
            for key in ("minimum_amount", "maximum_amount", "comparison_amount")
        ):
            raise ValueError("public price cannot mix scalar and range amounts")
        amount = positive(price["amount"], "public_price.amount")
        return (
            {
                "amount": amount,
                "comparison_amount": amount,
                "comparison_basis": "single_listed_amount",
                "currency": currency,
                "kind": kind,
                "source_key": price["source_key"],
            },
            amount,
        )

    minimum = positive(price["minimum_amount"], "public_price.minimum_amount")
    maximum = positive(price["maximum_amount"], "public_price.maximum_amount")
    comparison = positive(
        price["comparison_amount"], "public_price.comparison_amount"
    )
    if maximum < minimum:
        raise ValueError("public price maximum must be at least its minimum")
    if not math.isclose(comparison, minimum, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("range comparison amount must equal its lower bound")
    if price["comparison_basis"] != "lower_bound_to_favor_challenger":
        raise ValueError("supplier range must explicitly favor the challenger")
    source_keys = list(price["source_keys"])
    if len(source_keys) < 2:
        raise ValueError("supplier range requires at least two price sources")
    return (
        {
            "minimum_amount": minimum,
            "maximum_amount": maximum,
            "comparison_amount": comparison,
            "comparison_basis": price["comparison_basis"],
            "currency": currency,
            "kind": kind,
            "source_keys": source_keys,
        },
        comparison,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def thin_lens_fov_mm(
    sensor_span_mm: float, focal_length_mm: float, object_distance_mm: float
) -> float:
    """Return object-plane FOV using a thin-lens principal-plane prescreen."""
    sensor_span_mm = positive(sensor_span_mm, "sensor_span_mm")
    focal_length_mm = positive(focal_length_mm, "focal_length_mm")
    object_distance_mm = positive(object_distance_mm, "object_distance_mm")
    if object_distance_mm <= focal_length_mm:
        raise ValueError("object_distance_mm must exceed focal_length_mm")
    return sensor_span_mm * (object_distance_mm - focal_length_mm) / focal_length_mm


def working_distance_for_fov_mm(
    sensor_span_mm: float, focal_length_mm: float, fov_mm: float
) -> float:
    """Invert the thin-lens FOV prescreen to obtain object distance."""
    sensor_span_mm = positive(sensor_span_mm, "sensor_span_mm")
    focal_length_mm = positive(focal_length_mm, "focal_length_mm")
    fov_mm = positive(fov_mm, "fov_mm")
    return focal_length_mm + fov_mm * focal_length_mm / sensor_span_mm


def depth_of_field_mm(
    focal_length_mm: float,
    aperture_f_number: float,
    circle_of_confusion_mm: float,
    focus_distance_mm: float,
) -> dict[str, float]:
    """Return thin-lens hyperfocal, near, far, and total DOF distances."""
    focal_length_mm = positive(focal_length_mm, "focal_length_mm")
    aperture_f_number = positive(aperture_f_number, "aperture_f_number")
    circle_of_confusion_mm = positive(
        circle_of_confusion_mm, "circle_of_confusion_mm"
    )
    focus_distance_mm = positive(focus_distance_mm, "focus_distance_mm")
    if focus_distance_mm <= focal_length_mm:
        raise ValueError("focus_distance_mm must exceed focal_length_mm")
    hyperfocal = (
        focal_length_mm**2 / (aperture_f_number * circle_of_confusion_mm)
        + focal_length_mm
    )
    near = hyperfocal * focus_distance_mm / (
        hyperfocal + focus_distance_mm - focal_length_mm
    )
    far_denominator = hyperfocal - focus_distance_mm + focal_length_mm
    far = math.inf
    if far_denominator > 0:
        far = hyperfocal * focus_distance_mm / far_denominator
    return {
        "hyperfocal_mm": hyperfocal,
        "near_mm": near,
        "far_mm": far,
        "total_mm": far - near,
    }


def max_exposure_us(
    gsd_mm_px: float, speed_m_s: float, maximum_blur_px: float
) -> float:
    gsd_mm_px = positive(gsd_mm_px, "gsd_mm_px")
    speed_m_s = positive(speed_m_s, "speed_m_s")
    maximum_blur_px = positive(maximum_blur_px, "maximum_blur_px")
    return maximum_blur_px * gsd_mm_px * 1000.0 / speed_m_s


def blur_px(gsd_mm_px: float, speed_m_s: float, exposure_us: float) -> float:
    gsd_mm_px = positive(gsd_mm_px, "gsd_mm_px")
    speed_m_s = positive(speed_m_s, "speed_m_s")
    exposure_us = positive(exposure_us, "exposure_us")
    travel_mm = speed_m_s * 1000.0 * exposure_us / 1_000_000.0
    return travel_mm / gsd_mm_px


def minimum_periodic_observations(
    valid_length_mm: float, speed_m_s: float, frame_rate_hz: float
) -> int:
    """Worst-phase count of periodic triggers while a point crosses a region."""
    valid_length_mm = positive(valid_length_mm, "valid_length_mm")
    speed_m_s = positive(speed_m_s, "speed_m_s")
    frame_rate_hz = positive(frame_rate_hz, "frame_rate_hz")
    dwell_s = valid_length_mm / (speed_m_s * 1000.0)
    return math.floor(dwell_s * frame_rate_hz + 1e-12)


def transport_rate_mbps(
    width_px: int, height_px: int, bit_depth: int, frame_rate_hz: float
) -> float:
    if min(width_px, height_px, bit_depth) <= 0:
        raise ValueError("transport dimensions and bit depth must be positive")
    frame_rate_hz = positive(frame_rate_hz, "frame_rate_hz")
    return width_px * height_px * bit_depth * frame_rate_hz / 1_000_000.0


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping in {path}")
    return raw


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected object in {path}")
    return raw


def _resolved(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Input escapes repository: {relative}") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def derive(config: dict[str, Any], root: Path = PROJECT_ROOT) -> dict[str, Any]:
    inputs = config["source_inputs"]
    input_paths = {name: _resolved(root, path) for name, path in inputs.items()}
    core = _load_json(input_paths["v1_compute"])
    halo = _load_json(input_paths["v1_halo_compute"])
    if core["checkpoint_sha256"] != halo["checkpoint_sha256"]:
        raise ValueError("Core and halo evidence use different checkpoints")

    optics = config["baseline_optics"]
    roi_px = int(optics["roi"]["centered_native_px"][0])
    if optics["roi"]["centered_native_px"] != [roi_px, roi_px]:
        raise ValueError("The baseline active ROI must be square")
    sensor_span_mm = float(optics["roi"]["active_sensor_span_mm"])
    focal_mm = float(optics["lens"]["nominal_design_focal_length_mm"])
    focal_tolerance = float(
        optics["lens"]["catalog_focal_length_tolerance_fraction"]
    )
    if not 0.0 <= focal_tolerance < 1.0:
        raise ValueError("Catalog focal length tolerance must be in [0, 1)")
    focal_range_mm = [
        focal_mm * (1.0 - focal_tolerance),
        focal_mm * (1.0 + focal_tolerance),
    ]
    minimum_fov, maximum_fov = map(
        float, optics["geometry"]["target_ground_FOV_mm"]
    )
    nominal_fov = float(optics["geometry"]["nominal_ground_FOV_mm"])
    if not minimum_fov <= nominal_fov <= maximum_fov:
        raise ValueError("Nominal FOV must be inside the target range")
    ground_points: list[dict[str, float]] = []
    for fov_mm in (minimum_fov, nominal_fov, maximum_fov):
        distance_mm = working_distance_for_fov_mm(
            sensor_span_mm, focal_mm, fov_mm
        )
        gsd = fov_mm / roi_px
        ground_points.append(
            {
                "nominal_focal_length_mm": focal_mm,
                "object_distance_mm": distance_mm,
                "fov_mm": fov_mm,
                "gsd_mm_px": gsd,
                "span_10_mm_px": 10.0 / gsd,
                "span_20_mm_px": 20.0 / gsd,
            }
        )
    worst_gsd = maximum_fov / roi_px

    halo_px = int(config["tiling_and_swath"]["halo_px"])
    action_safe_px = roi_px - 2 * halo_px
    if action_safe_px <= 0:
        raise ValueError("Outer action mask consumes the full image")
    safe_width_min_mm = minimum_fov * action_safe_px / roi_px
    safe_width_max_mm = maximum_fov * action_safe_px / roi_px
    pitch_mm = float(
        config["tiling_and_swath"]["multi_module_center_pitch_maximum_mm"]
    )
    minimum_overlap_mm = float(
        config["tiling_and_swath"]["minimum_calibrated_safe_swath_overlap_mm"]
    )
    standalone_hood_width_mm = float(
        config["tiling_and_swath"]["standalone_proof_hood_internal_plan_mm"][0]
    )

    aperture = float(optics["lens"]["selected_aperture_f_number"])
    circle_of_confusion_mm = (
        float(optics["geometry"]["circle_of_confusion_um"]) / 1000.0
    )
    focus_offset_mm = float(
        optics["geometry"]["focus_plane_offset_above_ground_mm"]
    )
    relief_min_mm, relief_max_mm = map(
        float, optics["geometry"]["canopy_relief_above_ground_mm"]
    )
    catalog_samples: list[dict[str, Any]] = []
    for sampled_focal_mm in (focal_range_mm[0], focal_mm, focal_range_mm[1]):
        for sampled_fov_mm in (minimum_fov, nominal_fov, maximum_fov):
            distance_mm = working_distance_for_fov_mm(
                sensor_span_mm, sampled_focal_mm, sampled_fov_mm
            )
            focus_distance_mm = distance_mm - focus_offset_mm
            if focus_distance_mm <= sampled_focal_mm:
                raise ValueError("Focus plane must remain beyond the lens")
            sample_dof = depth_of_field_mm(
                sampled_focal_mm,
                aperture,
                circle_of_confusion_mm,
                focus_distance_mm,
            )
            near_object_mm = distance_mm - relief_max_mm
            far_object_mm = distance_mm - relief_min_mm
            catalog_samples.append(
                {
                    "focal_length_mm": sampled_focal_mm,
                    "ground_FOV_mm": sampled_fov_mm,
                    "working_distance_mm": distance_mm,
                    "focus_distance_mm": focus_distance_mm,
                    "operating_object_distance_mm": [
                        near_object_mm,
                        far_object_mm,
                    ],
                    "DOF": sample_dof,
                    "near_DOF_margin_mm": near_object_mm - sample_dof["near_mm"],
                    "far_DOF_margin_mm": sample_dof["far_mm"] - far_object_mm,
                }
            )
    required_working_distance_mm = [
        min(sample["working_distance_mm"] for sample in catalog_samples),
        max(sample["working_distance_mm"] for sample in catalog_samples),
    ]
    mount_working_distance_mm = list(
        map(float, optics["geometry"]["working_distance_adjustment_mm"])
    )
    nominal_sample = next(
        sample
        for sample in catalog_samples
        if sample["focal_length_mm"] == focal_mm
        and sample["ground_FOV_mm"] == nominal_fov
    )
    dof = nominal_sample["DOF"]
    wavelength_mm = float(optics["geometry"]["design_wavelength_nm"]) / 1_000_000.0
    airy_disk_mm = (
        2.44
        * wavelength_mm
        * aperture
    )
    pixel_pitch_mm = float(config["camera_shortlist"][0]["pixel_pitch_um"]) / 1000.0
    if not math.isclose(
        sensor_span_mm, roi_px * pixel_pitch_mm, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("Active sensor span must equal ROI pixels times pixel pitch")

    motion = config["motion_and_observation"]
    frozen_exposure_us = float(motion["frozen_exposure_us"])
    frame_rates = [
        float(motion["acquisition_rate_hz"][key])
        for key in ("hard_minimum", "baseline", "target_after_end_to_end_gate")
    ]
    motion_rows: list[dict[str, Any]] = []
    for speed in map(float, motion["speeds_m_s"]):
        rate_rows = []
        for fps in frame_rates:
            rate_rows.append(
                {
                    "frame_rate_hz": fps,
                    "trigger_pitch_mm": speed * 1000.0 / fps,
                    "minimum_action_safe_observations": minimum_periodic_observations(
                        safe_width_min_mm, speed, fps
                    ),
                    "maximum_speed_m_s_for_five_observations": (
                        safe_width_min_mm / 1000.0 * fps / 5.0
                    ),
                }
            )
        motion_rows.append(
            {
                "speed_m_s": speed,
                "maximum_exposure_us_at_blur_limit": max_exposure_us(
                    worst_gsd, speed, float(motion["maximum_motion_blur_px"])
                ),
                "blur_px_at_frozen_exposure": blur_px(
                    worst_gsd, speed, frozen_exposure_us
                ),
                "observation_envelope": rate_rows,
            }
        )

    halo_batch = halo["timing_by_batch_size"]["4"]
    mean_ms = float(halo_batch["latency_ms"]["mean"])
    p95_ms = float(halo_batch["latency_ms"]["p95"])
    compute_rows: list[dict[str, Any]] = []
    for camera_count in (1, 2, 3):
        for fps in frame_rates:
            mean_util = camera_count * fps * mean_ms / 1000.0
            p95_util = camera_count * fps * p95_ms / 1000.0
            compute_rows.append(
                {
                    "camera_count": camera_count,
                    "frame_rate_hz_each": fps,
                    "tile_demand_per_s": camera_count * fps * 4,
                    "mean_service_utilization_fraction": mean_util,
                    "p95_service_utilization_fraction": p95_util,
                    "p95_compute_only_supported": p95_util < 1.0,
                    "p95_remaining_budget_ms_per_cycle": 1000.0 / fps
                    - camera_count * p95_ms,
                }
            )

    shortlist = []
    _, baseline_price = normalized_public_price(
        config["camera_shortlist"][0]["public_price"]
    )
    for candidate in config["camera_shortlist"]:
        width, height = map(int, candidate["resolution_px"])
        price = candidate["public_price"]
        price_evidence, comparison_amount = normalized_public_price(price)
        row = {
            "rank": int(candidate["rank"]),
            "role": candidate["role"],
            "manufacturer": candidate["manufacturer"],
            "model": candidate["model"],
            "resolution_px": [width, height],
            "megapixels": width * height / 1_000_000.0,
            "maximum_frame_rate_hz": float(candidate["maximum_frame_rate_hz"]),
            "maximum_frame_rate_condition": candidate[
                "maximum_frame_rate_condition"
            ],
            "shutter": candidate["shutter"],
            "color": candidate["color"],
            "sensor": candidate["sensor"],
            "sensor_format": candidate["sensor_format"],
            "pixel_pitch_um": float(candidate["pixel_pitch_um"]),
            "bit_depths": list(map(int, candidate["bit_depths"])),
            "interface": candidate["interface"],
            "lens_mount": candidate["lens_mount"],
            "matched_lens_model": candidate["matched_lens_model"],
            "active_roi_px": list(map(int, candidate["active_roi_px"])),
            "active_roi_offset_px": list(
                map(int, candidate["active_roi_offset_px"])
            ),
            "trigger": candidate["trigger"],
            "public_availability": candidate["public_availability"],
            "price": price_evidence,
            "price_per_max_fps_using_comparison_amount": comparison_amount
            / float(candidate["maximum_frame_rate_hz"]),
        }
        if price["currency"] == "USD":
            row[
                "price_ratio_vs_selected_baseline_using_comparison_amount"
            ] = comparison_amount / baseline_price
        if "power" in candidate:
            row["power"] = candidate["power"]
        if "typical_camera_power_w" in candidate:
            row["typical_camera_power_w"] = float(
                candidate["typical_camera_power_w"]
            )
        if "typical_camera_power_w_by_supply" in candidate:
            row["typical_camera_power_w_by_supply"] = {
                key: float(value)
                for key, value in candidate[
                    "typical_camera_power_w_by_supply"
                ].items()
            }
        if "full_frame_rate_hz_by_raw_format" in candidate:
            row["full_frame_rate_hz_by_raw_format"] = {
                key: float(value)
                for key, value in candidate[
                    "full_frame_rate_hz_by_raw_format"
                ].items()
            }
        shortlist.append(row)

    transport = []
    for fps in frame_rates:
        transport.append(
            {
                "frame_rate_hz": fps,
                "Bayer10_packed_payload_mbps": transport_rate_mbps(
                    roi_px, roi_px, 10, fps
                ),
                "Bayer12_packed_payload_mbps": transport_rate_mbps(
                    roi_px, roi_px, 12, fps
                ),
            }
        )

    light = config["illumination"]
    electrical = light["electrical_design_envelope"]
    bus_voltage_v = float(electrical["bus_voltage_v"])
    peak_current_a = float(electrical["programmable_peak_current_a"][1])
    peak_ceiling_w = float(electrical["peak_electrical_ceiling_w"])
    nominal_pulse_us = float(light["nominal_pulse_us"])
    maximum_pulse_us = float(light["maximum_pulse_us"])
    maximum_droop_v = bus_voltage_v * float(
        electrical["maximum_bus_droop_fraction_during_pulse"]
    )
    local_storage_prescreen_uF = (
        peak_current_a * nominal_pulse_us / maximum_droop_v
    )
    duty_rows = []
    for fps in frame_rates:
        duty_rows.append(
            {
                "frame_rate_hz": fps,
                "nominal_pulse_duty_fraction": nominal_pulse_us
                * fps
                / 1_000_000.0,
                "maximum_pulse_duty_fraction": maximum_pulse_us
                * fps
                / 1_000_000.0,
                "average_w_at_peak_ceiling_and_nominal_pulse": peak_ceiling_w
                * nominal_pulse_us
                * fps
                / 1_000_000.0,
            }
        )

    bom = config["bom_usd_excluding_tax_shipping_existing_rtx3090"]
    bom_min = sum(float(item["minimum"]) for item in bom["items"])
    bom_max = sum(float(item["maximum"]) for item in bom["items"])
    contingency = float(bom["contingency_fraction"])
    fallback_price = float(
        config["camera_shortlist"][1]["public_price"]["amount"]
    )
    fallback_bom_min = bom_min - baseline_price + fallback_price
    fallback_bom_max = bom_max - baseline_price + fallback_price

    gsd_gate = float(optics["nine_region_gate"]["local_gsd_maximum_mm_px"])
    region_centers = optics["nine_region_gate"]["normalized_centers"]
    one_15 = next(
        row
        for row in compute_rows
        if row["camera_count"] == 1 and row["frame_rate_hz_each"] == 15.0
    )
    one_20 = next(
        row
        for row in compute_rows
        if row["camera_count"] == 1 and row["frame_rate_hz_each"] == 20.0
    )
    two_12 = next(
        row
        for row in compute_rows
        if row["camera_count"] == 2 and row["frame_rate_hz_each"] == 12.0
    )
    fastest_row = next(row for row in motion_rows if row["speed_m_s"] == 1.0)
    fastest_min_rate = next(
        row
        for row in fastest_row["observation_envelope"]
        if row["frame_rate_hz"] == 12.0
    )
    checks = {
        "thin_lens_FOV_below_500_mm": maximum_fov < 500.0,
        "thin_lens_GSD_below_nine_region_gate": worst_gsd <= gsd_gate,
        "ten_mm_span_at_least_41_px": 10.0 / worst_gsd >= 41.0,
        "twenty_mm_span_at_least_82_px": 20.0 / worst_gsd >= 82.0,
        "working_distance_mount_covers_catalog_focal_tolerance": mount_working_distance_mm[
            0
        ]
        <= required_working_distance_mm[0]
        and mount_working_distance_mm[1] >= required_working_distance_mm[1],
        "analytic_DOF_covers_operating_object_range": all(
            sample["near_DOF_margin_mm"] >= 0.0
            and sample["far_DOF_margin_mm"] >= 0.0
            for sample in catalog_samples
        ),
        "frozen_exposure_blur_at_1_m_s_at_most_0_75_px": fastest_row[
            "blur_px_at_frozen_exposure"
        ]
        <= 0.75,
        "five_observations_at_1_m_s_and_12_Hz": fastest_min_rate[
            "minimum_action_safe_observations"
        ]
        >= 5,
        "one_camera_15_Hz_compute_p95_below_capacity": one_15[
            "p95_compute_only_supported"
        ],
        "one_camera_20_Hz_not_yet_proven_at_p95": not one_20[
            "p95_compute_only_supported"
        ],
        "two_camera_12_Hz_rejected_by_measured_p95": not two_12[
            "p95_compute_only_supported"
        ],
        "nine_unique_image_regions_are_gated": len(region_centers) == 9
        and len({tuple(center) for center in region_centers}) == 9,
        "nine_region_GSD_gate_implies_10_and_20_mm_spans": 10.0 / gsd_gate
        >= float(optics["nine_region_gate"]["minimum_10_mm_span_px"])
        and 20.0 / gsd_gate
        >= float(optics["nine_region_gate"]["minimum_20_mm_span_px"]),
        "replicated_module_pitch_has_no_worst_case_gap": pitch_mm
        <= safe_width_min_mm,
        "replicated_bays_keep_minimum_safe_swath_overlap": pitch_mm
        + minimum_overlap_mm
        <= safe_width_min_mm,
        "continuous_hood_geometry_matches_swath_contract": float(
            config["hood_and_window"]["scaling"]["camera_center_pitch_maximum_mm"]
        )
        == pitch_mm
        and list(
            map(float, config["hood_and_window"]["shell"]["minimum_internal_plan_mm"])
        )
        == list(
            map(
                float,
                config["tiling_and_swath"][
                    "standalone_proof_hood_internal_plan_mm"
                ],
            )
        ),
        "local_strobe_storage_prescreen_is_consistent": math.isclose(
            local_storage_prescreen_uF,
            float(electrical["conservative_local_storage_prescreen_at_10A_150us_uF"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Baseline analytic checks failed: {failed}")

    return {
        "schema_version": 2,
        "contract": config["contract"],
        "status": config["status"],
        "evidence_date": str(config["evidence_date"]),
        "decision": {
            "proof_camera_count": 1,
            "baseline_camera": config["camera_shortlist"][0]["model"],
            "lower_cost_fallback": config["camera_shortlist"][1]["model"],
            "lens": optics["lens"]["model"],
            "working_distance_adjustment_mm": mount_working_distance_mm,
            "working_distance_required_catalog_envelope_mm": required_working_distance_mm,
            "nominal_working_distance_ground_mm": nominal_sample[
                "working_distance_mm"
            ],
            "working_distance_selection_rule": optics["geometry"][
                "working_distance_rule"
            ],
            "frozen_exposure_us": frozen_exposure_us,
            "baseline_frame_rate_hz": float(
                motion["acquisition_rate_hz"]["baseline"]
            ),
            "scale_rule": config["tiling_and_swath"]["scale_rule"],
        },
        "source_integrity": {
            name: {
                "path": str(path.relative_to(root)),
                "sha256": sha256_file(path),
            }
            for name, path in sorted(input_paths.items())
        },
        "camera_price_performance": {
            "price_date": str(config["price_policy"]["price_date"]),
            "disclaimer": config["price_policy"]["disclaimer"],
            "range_comparison_rule": config["price_policy"][
                "range_comparison_rule"
            ],
            "shortlist": shortlist,
            "matched_lens": {
                "manufacturer": optics["lens"]["manufacturer"],
                "model": optics["lens"]["model"],
                "order_number": int(optics["lens"]["order_number"]),
                "nominal_design_focal_length_mm": focal_mm,
                "catalog_focal_length_range_mm": focal_range_mm,
                "aperture_range_f_number": list(
                    map(float, optics["lens"]["aperture_range_f_number"])
                ),
                "selected_aperture_f_number": aperture,
                "sensor_coverage": optics["lens"]["sensor_coverage"],
                "rated_pixel_pitch_um": float(
                    optics["lens"]["rated_pixel_pitch_um"]
                ),
                "lens_mount": optics["lens"]["mount"],
                "price": {
                    "amount": float(
                        optics["lens"]["public_price"]["amount"]
                    ),
                    "currency": optics["lens"]["public_price"]["currency"],
                    "kind": optics["lens"]["public_price"]["kind"],
                    "source_key": optics["lens"]["public_price"]["source_key"],
                },
            },
        },
        "optical_proof": {
            "active_sensor_span_mm": sensor_span_mm,
            "nominal_design_focal_length_mm": focal_mm,
            "catalog_focal_length_range_mm": focal_range_mm,
            "aperture_f_number": aperture,
            "nominal_focus_distance_mm": nominal_sample["focus_distance_mm"],
            "focus_plane_offset_above_ground_mm": focus_offset_mm,
            "canopy_relief_above_ground_mm": [relief_min_mm, relief_max_mm],
            "ground_distance_samples": ground_points,
            "FOV_range_mm": [minimum_fov, maximum_fov],
            "GSD_range_mm_px": [
                min(point["gsd_mm_px"] for point in ground_points),
                worst_gsd,
            ],
            "worst_case_10_mm_span_px": 10.0 / worst_gsd,
            "worst_case_20_mm_span_px": 20.0 / worst_gsd,
            "action_safe_inner_px": action_safe_px,
            "action_safe_width_range_mm": [safe_width_min_mm, safe_width_max_mm],
            "analytic_DOF": dof,
            "catalog_focal_FOV_DOF_samples": catalog_samples,
            "required_working_distance_range_mm": required_working_distance_mm,
            "working_distance_mount_adjustment_mm": mount_working_distance_mm,
            "minimum_near_DOF_margin_mm": min(
                sample["near_DOF_margin_mm"] for sample in catalog_samples
            ),
            "minimum_far_DOF_margin_mm": min(
                sample["far_DOF_margin_mm"] for sample in catalog_samples
            ),
            "airy_disk_at_design_wavelength_um": airy_disk_mm * 1000.0,
            "airy_disk_at_design_wavelength_px": airy_disk_mm / pixel_pitch_mm,
            "nine_region_count": len(
                optics["nine_region_gate"]["normalized_centers"]
            ),
            "catalog_math_is_not_acceptance_evidence": True,
        },
        "tiling_and_scalable_swath": {
            "tile_grid": config["tiling_and_swath"]["tile_grid"],
            "tile_core_px": int(config["tiling_and_swath"]["tile_core_px"]),
            "halo_px": halo_px,
            "model_input_px": int(config["tiling_and_swath"]["model_input_px"]),
            "outer_edge_abstain_px": halo_px,
            "maximum_module_center_pitch_mm": pitch_mm,
            "minimum_calibrated_safe_swath_overlap_mm": minimum_overlap_mm,
            "worst_case_safe_swath_overlap_at_maximum_pitch_mm": safe_width_min_mm
            - pitch_mm,
            "minimum_valid_union_width_mm_by_camera_count": {
                str(count): safe_width_min_mm + (count - 1) * pitch_mm
                for count in (1, 2, 3)
            },
            "continuous_hood_internal_width_mm_by_camera_count": {
                str(count): standalone_hood_width_mm + (count - 1) * pitch_mm
                for count in (1, 2, 3)
            },
            "compute_consequence": compute_rows,
            "measured_halo_batch4_mean_ms": mean_ms,
            "measured_halo_batch4_p95_ms": p95_ms,
            "measured_mean_module_capacity_hz": 1000.0 / mean_ms,
            "measured_p95_module_capacity_hz": 1000.0 / p95_ms,
            "multi_camera_extrapolation_rule": config["tiling_and_swath"][
                "compute_extrapolation_rule"
            ],
        },
        "motion_and_track_observation": motion_rows,
        "camera_transport_payload": transport,
        "strobe_duty_and_power_envelope": {
            "rows": duty_rows,
            "peak_electrical_ceiling_w": peak_ceiling_w,
            "nominal_peak_energy_ceiling_j_per_pulse": peak_ceiling_w
            * nominal_pulse_us
            / 1_000_000.0,
            "maximum_peak_energy_ceiling_j_per_pulse": peak_ceiling_w
            * maximum_pulse_us
            / 1_000_000.0,
            "conservative_local_storage_prescreen_uF": local_storage_prescreen_uF,
            "bench_variable_rule": light["bench_variable_rule"],
            "unmeasured_lux_or_energy_is_frozen": False,
        },
        "bom_budget": {
            "currency": "USD",
            "subtotal_range": [bom_min, bom_max],
            "with_contingency_range": [
                round(bom_min * (1.0 + contingency), 2),
                round(bom_max * (1.0 + contingency), 2),
            ],
            "contingency_fraction": contingency,
            "existing_RTX3090_incremental_cost": float(
                bom["existing_rtx3090_incremental_cost_usd"]
            ),
            "lower_cost_fallback_savings": baseline_price - fallback_price,
            "lower_cost_fallback_subtotal_range": [
                fallback_bom_min,
                fallback_bom_max,
            ],
            "lower_cost_fallback_with_contingency_range": [
                round(fallback_bom_min * (1.0 + contingency), 2),
                round(fallback_bom_max * (1.0 + contingency), 2),
            ],
            "quote_status": "budgetary_not_landed_quote",
        },
        "synthetic_envelope": {
            **config["synthetic_envelope"],
            "derived_optical_match": {
                "catalog_focal_length_range_mm": focal_range_mm,
                "ground_FOV_range_mm": [minimum_fov, maximum_fov],
                "ground_GSD_range_mm_px": [
                    min(point["gsd_mm_px"] for point in ground_points),
                    worst_gsd,
                ],
                "action_safe_width_range_mm": [
                    safe_width_min_mm,
                    safe_width_max_mm,
                ],
                "required_working_distance_range_mm": required_working_distance_mm,
                "focus_plane_offset_above_ground_mm": focus_offset_mm,
                "analytic_DOF_mm": dof,
            },
        },
        "baseline_analytic_checks": checks,
        "baseline_analytic_checks_pass": all(checks.values()),
        "manager_validation_required": True,
    }


def render(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed output differs; do not write.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    config = _load_yaml(config_path)
    result = derive(config, PROJECT_ROOT)
    result["source_integrity"]["derivation_config"] = {
        "path": str(config_path.relative_to(PROJECT_ROOT)),
        "sha256": sha256_file(config_path),
    }
    expected = render(result)
    if args.check:
        if not output_path.is_file():
            raise SystemExit(f"Missing derived output: {output_path}")
        actual = output_path.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit(f"Derived output is stale: {output_path}")
        print(f"OK: {output_path.relative_to(PROJECT_ROOT)} is reproducible")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(expected, encoding="utf-8")
    print(f"Wrote {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
