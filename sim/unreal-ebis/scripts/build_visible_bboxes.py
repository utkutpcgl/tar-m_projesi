#!/usr/bin/env python3
"""Convert UE visible/amodal instance masks into safe YOLO partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


MASK_THRESHOLD = 96
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    """Keep release validation byte-identical across local and render mirrors."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def mask_stats(path: Path, include_components: bool = False) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    image = Image.open(path).convert("L")
    width, height = image.size
    threshold_table = [0 if value < MASK_THRESHOLD else 255 for value in range(256)]
    binary = image.point(threshold_table, mode="L")
    bbox = binary.getbbox()
    if bbox is None:
        return None
    min_x, min_y, right, bottom = bbox
    max_x, max_y = right - 1, bottom - 1
    cropped = binary.crop(bbox)
    count = cropped.histogram()[255]
    box_width, box_height = max_x - min_x + 1, max_y - min_y + 1
    component_count = None
    largest_component_fraction = None
    if include_components:
        crop_width, crop_height = cropped.size
        remaining = {index for index, value in enumerate(cropped.tobytes()) if value}
        component_sizes = []
        while remaining:
            queue = [remaining.pop()]
            size = 0
            while queue:
                current = queue.pop()
                size += 1
                cy, cx = divmod(current, crop_width)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < crop_width and 0 <= ny < crop_height:
                            neighbour = ny * crop_width + nx
                            if neighbour in remaining:
                                remaining.remove(neighbour)
                                queue.append(neighbour)
            component_sizes.append(size)
        component_count = len(component_sizes)
        largest_component_fraction = max(component_sizes) / count
    return {
        "threshold": MASK_THRESHOLD,
        "resolution_px": [width, height],
        "pixels": count,
        "xyxy_top_left_px": [min_x, min_y, max_x, max_y],
        "size_px": [box_width, box_height],
        "yolo": [
            (min_x + max_x + 1) / (2.0 * width),
            (min_y + max_y + 1) / (2.0 * height),
            box_width / width,
            box_height / height,
        ],
        "bbox_fill_fraction": count / (box_width * box_height),
        "touching_edges": {
            "left": min_x == 0,
            "right": max_x == width - 1,
            "top": min_y == 0,
            "bottom": max_y == height - 1,
        },
        "component_count": component_count,
        "largest_component_fraction": largest_component_fraction,
        "sha256": sha256(path),
    }


def classify_rfid(
    visible: dict[str, Any] | None,
    amodal: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    if amodal is None:
        return {
            "label_status": "present_but_outside_frame",
            "include_in_yolo": False,
            "visibility_fraction": 0.0,
            "metrics_at_model_input": None,
            "reasons": ["no_amodal_in_frame_pixels"],
        }
    if visible is None:
        return {
            "label_status": "present_but_fully_occluded",
            "include_in_yolo": False,
            "visibility_fraction": 0.0,
            "metrics_at_model_input": None,
            "reasons": ["amodal_present_but_no_visible_pixels"],
        }
    resolution = visible["resolution_px"]
    model_input = float(policy["model_input_px"])
    scale = model_input / max(map(float, resolution))
    width_px, height_px = map(float, visible["size_px"])
    x1, y1, x2, y2 = map(float, visible["xyxy_top_left_px"])
    visibility = min(1.0, visible["pixels"] / max(1.0, float(amodal["pixels"])))
    metrics = {
        "short_side_px": min(width_px, height_px) * scale,
        "long_side_px": max(width_px, height_px) * scale,
        "foreground_pixels": visible["pixels"] * scale * scale,
        "edge_margin_px": min(x1, y1, resolution[0] - 1 - x2, resolution[1] - 1 - y2) * scale,
        "largest_component_fraction": float(visible["largest_component_fraction"] or 0.0),
    }

    def passes(values: dict[str, Any], require_margin: bool):
        failures = []
        checks = [
            (metrics["short_side_px"] >= float(values["min_short_side_px"]), "short_side"),
            (metrics["long_side_px"] >= float(values["min_long_side_px"]), "long_side"),
            (metrics["foreground_pixels"] >= float(values["min_foreground_pixels"]), "foreground"),
            (visibility >= float(values["min_visibility_fraction"]), "visibility"),
            (metrics["largest_component_fraction"] >= float(values["min_largest_component_fraction"]), "largest_component"),
        ]
        failures.extend(name for ok, name in checks if not ok)
        if require_margin and metrics["edge_margin_px"] < float(values.get("min_edge_margin_px", 0)):
            failures.append("edge_margin")
        return not failures, failures

    standard_ok, standard_failures = passes(policy["rfid_tag"]["standard"], True)
    hard_ok, hard_failures = passes(policy["rfid_tag"]["hard"], False)
    if standard_ok:
        label_status, include, reasons = "standard_positive", True, []
    elif hard_ok:
        label_status, include, reasons = "hard_positive", True, standard_failures
    else:
        label_status, include, reasons = "excluded_too_small_or_occluded", False, hard_failures
    return {
        "label_status": label_status,
        "include_in_yolo": include,
        "visibility_fraction": visibility,
        "metrics_at_model_input": metrics,
        "reasons": reasons,
    }


def image_metrics(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    channels = image.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = maximum.histogram()
    pixel_count = image.width * image.height
    clipped = sum(histogram[251:]) / pixel_count
    crushed = sum(histogram[:5]) / pixel_count
    return {
        "resolution_px": list(image.size),
        "mean_rgb": [round(value, 4) for value in stat.mean],
        "clipped_highlight_fraction": clipped,
        "crushed_black_fraction": crushed,
        "sha256": sha256(path),
    }


def process(root: Path, config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_digest = sha256(config_path)
    policy = config["annotation_policy"]
    metadata_paths = sorted((root / "raw" / "metadata").glob("*.json"))
    errors: list[str] = []
    warnings: list[str] = []
    partition_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    camera_counts: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()
    paper_occlusion_counts: Counter[str] = Counter()
    paper_links_checked = 0
    door_angles_checked = 0
    door_profile_counts: Counter[str] = Counter()
    interior_finish_contracts_checked = 0
    fixed_camera_stacks_checked = 0
    lower_contact_faces_checked = 0
    lower_contact_face_profile_counts: Counter[str] = Counter()
    upper_contact_faces_checked = 0
    debris_contracts_checked = 0
    concrete_surface_regimes_checked = 0
    concrete_surface_regime_counts: Counter[str] = Counter()
    concrete_body_profiles_checked = 0
    concrete_body_profile_counts: Counter[str] = Counter()
    concrete_top_load_weathering_checked = 0
    concrete_top_load_weathering_patch_total = 0
    camera_model_contracts_checked = 0
    camera_randomization_contracts_checked = 0
    rfid_contact_models_checked = 0
    rfid_contact_model_counts: Counter[str] = Counter()
    rfid_visible_tip_regime_counts: Counter[str] = Counter()
    manifest_stems: dict[str, list[str]] = {name: [] for name in ("standard", "hard_occlusion", "exclude")}
    concrete_cells: dict[str, list[list[float]]] = {}
    visible_nonempty_hashes: dict[str, list[str]] = {}
    rgb_hashes: dict[str, list[str]] = {}
    depth_hashes: dict[str, list[str]] = {}
    raw_instance_count = 0
    generated_records = []

    run_manifest_path = root / "raw" / "run_manifest.json"
    run_manifest = (
        json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if run_manifest_path.is_file()
        else None
    )
    expect_depth = bool(run_manifest and run_manifest.get("include_depth"))
    camera_model_cfg = config.get("camera_model", {})
    camera_model_manifest_path = root / "raw" / "camera_model_manifest.json"
    camera_model_manifest = (
        json.loads(camera_model_manifest_path.read_text(encoding="utf-8"))
        if camera_model_manifest_path.is_file()
        else None
    )
    if camera_model_cfg.get("enabled"):
        if not camera_model_manifest:
            errors.append("missing_camera_model_manifest")
        else:
            if (
                camera_model_manifest.get("status") != "PASS"
                or camera_model_manifest.get("profile") != camera_model_cfg.get("profile")
                or camera_model_manifest.get("config_sha256") != config_digest
                or not camera_model_manifest.get("rgb_and_instance_masks_warped_together")
                or camera_model_manifest.get("depth_status") != "not_rendered_fail_closed"
            ):
                errors.append(f"camera_model_manifest_contract_mismatch:{camera_model_manifest}")
            if expect_depth:
                errors.append("camera_model_depth_must_fail_closed")

    if not metadata_paths:
        errors.append("no_raw_metadata")

    for metadata_path in metadata_paths:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        stem = raw["stem"]
        if raw.get("config_sha256") != config_digest:
            errors.append(f"config_hash_mismatch:{stem}:{raw.get('config_sha256')}:{config_digest}")
        if not str(raw.get("engine_version", "")).startswith("5.8.1-"):
            errors.append(f"unexpected_engine_version:{stem}:{raw.get('engine_version')}")
        camera, shape = raw["camera"], raw["sample"]["shape"]
        camera_counts[camera] += 1
        shape_counts[shape] += 1
        camera_realization = raw.get("camera_realization", {})
        camera_randomization = config.get("camera_randomization", {})
        fov_jitter_bounds = list(
            map(float, camera_randomization.get("fov_jitter_deg", [0.0, 0.0]))
        )
        if (
            camera_realization.get("randomization_profile")
            != "bounded_camera_jitter_v1"
            or len(camera_realization.get("resolved_location_cm", [])) != 3
            or len(camera_realization.get("resolved_target_cm", [])) != 3
            or len(camera_realization.get("location_jitter_cm", [])) != 3
            or len(camera_realization.get("target_jitter_cm", [])) != 3
            or not math.isclose(
                float(
                    camera_realization.get(
                        "base_horizontal_fov_deg", -1.0
                    )
                ),
                float(config["cameras"][camera]["horizontal_fov_deg"]),
                abs_tol=1e-6,
            )
            or len(fov_jitter_bounds) != 2
            or not fov_jitter_bounds[0]
            <= float(camera_realization.get("fov_jitter_deg", 99.0))
            <= fov_jitter_bounds[1]
        ):
            errors.append(
                f"camera_randomization_contract_mismatch:{stem}:"
                f"{camera_realization}"
            )
        else:
            camera_randomization_contracts_checked += 1
        if camera_model_cfg.get("enabled"):
            observed_camera_model = raw.get("camera_model", {})
            expected_camera_model = camera_model_cfg["cameras"].get(camera, {})
            if (
                observed_camera_model.get("profile") != camera_model_cfg.get("profile")
                or observed_camera_model.get("calibration_status")
                != camera_model_cfg.get("calibration_status")
                or not observed_camera_model.get("rgb_and_instance_masks_warped_together")
                or observed_camera_model.get("depth_status") != "not_rendered"
                or not math.isclose(
                    float(observed_camera_model.get("raw_horizontal_fov_deg", -1.0)),
                    float(camera_realization["horizontal_fov_deg"]),
                    abs_tol=1e-6,
                )
                or not math.isclose(
                    float(observed_camera_model.get("radial_strength", -1.0)),
                    float(expected_camera_model.get("radial_strength", -2.0)),
                    abs_tol=1e-6,
                )
            ):
                errors.append(f"camera_model_metadata_mismatch:{stem}:{observed_camera_model}")
            else:
                camera_model_contracts_checked += 1
        machine_state = raw.get("machine", {})
        machine_cfg = config["machine"]
        door_state = machine_state.get("door")
        door_profiles = machine_cfg.get("door_open_angle_profiles", {})
        if not isinstance(door_state, dict):
            errors.append(f"missing_door_state:{stem}")
        else:
            door_profile = str(door_state.get("profile", ""))
            expected_door_profile = door_profiles.get(door_profile)
            observed_range = door_state.get("angle_range_deg")
            range_valid = (
                isinstance(observed_range, list)
                and len(observed_range) == 2
                and isinstance(expected_door_profile, dict)
                and all(
                    math.isclose(float(actual), float(expected), abs_tol=1e-6)
                    for actual, expected in zip(
                        observed_range, expected_door_profile["range_deg"]
                    )
                )
            )
            door_angle = float(door_state.get("angle_deg", -1.0))
            expected_door_side = str(machine_cfg["door_side"])
            if (
                not range_valid
                or not float(observed_range[0]) <= door_angle <= float(observed_range[1])
                or door_state.get("side") != expected_door_side
                or door_state.get("angle_convention")
                != "0=closed across front aperture, positive=left latch edge rotates outward"
                or door_state.get("distribution_status")
                != machine_cfg["door_angle_status"]
            ):
                errors.append(
                    f"door_angle_contract_mismatch:{stem}:{door_state}"
                )
            else:
                door_angles_checked += 1
                door_profile_counts[door_profile] += 1

        cover_state = door_state.get("service_cover", {}) if isinstance(door_state, dict) else {}
        expected_cover_size = list(map(float, machine_cfg["door_service_cover_size_cm"]))
        cover_valid = (
            isinstance(cover_state, dict)
            and len(cover_state.get("size_cm", [])) == 2
            and math.isclose(
                float(cover_state.get("center_from_hinge_cm", -1.0)),
                float(machine_cfg["door_service_cover_center_from_hinge_cm"]),
                abs_tol=1e-6,
            )
            and math.isclose(
                float(cover_state.get("center_z_cm", -1.0)),
                float(machine_cfg["door_service_cover_center_z_cm"]),
                abs_tol=1e-6,
            )
            and all(
                math.isclose(float(actual), expected, abs_tol=1e-6)
                for actual, expected in zip(cover_state["size_cm"], expected_cover_size)
            )
            and math.isclose(
                float(door_state.get("leaf_width_cm", -1.0)),
                float(machine_cfg["door_leaf_width_cm"]),
                abs_tol=1e-6,
            )
            and math.isclose(
                float(door_state.get("leaf_height_cm", -1.0)),
                float(machine_cfg["door_leaf_height_cm"]),
                abs_tol=1e-6,
            )
            and math.isclose(
                float(door_state.get("leaf_thickness_cm", -1.0)),
                float(machine_cfg["door_leaf_thickness_cm"]),
                abs_tol=1e-6,
            )
        )
        if (
            machine_state.get("interior_finish") != machine_cfg["interior_finish"]
            or machine_state.get("interior_panel_materials")
            != machine_cfg["interior_panel_materials"]
        ):
            errors.append(f"interior_finish_contract_mismatch:{stem}")
        else:
            interior_finish_contracts_checked += 1
        if (
            int(machine_state.get("fixed_camera_stack_count", -1))
            != int(machine_cfg["fixed_camera_stack_count"])
            or machine_state.get("fixed_camera_stack_status")
            != machine_cfg["fixed_camera_stack_status"]
            or machine_state.get("workshop_backdrop_status")
            != machine_cfg["workshop_backdrop_status"]
            or machine_state.get("blue_wall_material_profile")
            != machine_cfg["blue_wall_material_profile"]
            or not cover_valid
        ):
            errors.append(f"fixed_camera_stack_contract_mismatch:{stem}")
        else:
            fixed_camera_stacks_checked += 1
        debris_count_range = list(
            map(int, machine_cfg.get("debris_count_range", [32, 32]))
        )
        debris_count = int(machine_state.get("debris_count", -1))
        debris_shape_counts = machine_state.get("debris_shape_counts", {})
        platen_wear_counts = machine_state.get(
            "platen_wear_line_counts", {}
        )
        if (
            len(debris_count_range) != 2
            or not debris_count_range[0]
            <= debris_count
            <= debris_count_range[1]
            or machine_state.get("debris_morphology")
            != machine_cfg.get("debris_morphology_profile")
            or not isinstance(debris_shape_counts, dict)
            or set(debris_shape_counts)
            != {"angular_cube", "rounded_sphere"}
            or sum(map(int, debris_shape_counts.values())) != debris_count
            or machine_state.get("debris_annotation_policy")
            != "background only, never concrete target class"
            or platen_wear_counts != {"lower": 8, "upper": 6}
            or machine_state.get("platen_wear_profile")
            != "bounded_sparse_scratches_and_dust_streaks_v1"
        ):
            errors.append(f"debris_contract_mismatch:{stem}:{machine_state}")
        else:
            debris_contracts_checked += 1

        sample_record = raw["sample"]
        surface_regime = str(sample_record.get("surface_regime", ""))
        allowed_regimes = config["sample"]["surface_regime_weights_by_shape"].get(
            shape, {}
        )
        relief_range = config["sample"]["edge_relief_count_range_by_regime"].get(
            surface_regime
        )
        observed_size_range = sample_record.get("edge_relief_size_range_cm", [])
        expected_size_range = list(map(float, config["sample"]["edge_relief_size_cm"]))
        size_range_valid = (
            isinstance(observed_size_range, list)
            and len(observed_size_range) == 2
            and all(
                math.isclose(float(actual), expected, abs_tol=1e-9)
                for actual, expected in zip(observed_size_range, expected_size_range)
            )
        )
        edge_relief_count = int(sample_record.get("edge_relief_count", -1))
        weathering_count_range = config["sample"][
            "top_load_weathering_patch_count_range_by_regime"
        ].get(surface_regime)
        weathering_patch_count = int(
            sample_record.get("top_load_weathering_patch_count", -1)
        )
        weathering_material_counts = sample_record.get(
            "top_load_weathering_material_counts", {}
        )
        weathering_contract_valid = (
            weathering_count_range is not None
            and int(weathering_count_range[0])
            <= weathering_patch_count
            <= int(weathering_count_range[1])
            and isinstance(weathering_material_counts, dict)
            and set(weathering_material_counts) == {"ochre", "dark"}
            and sum(map(int, weathering_material_counts.values()))
            == weathering_patch_count
            and sample_record.get("top_load_weathering_profile")
            == "clustered_submillimetre_embedded_ochre_dark_residue_v1"
            and sample_record.get("top_load_weathering_status")
            == config["sample"]["top_load_weathering_status"]
        )
        expected_additional_pores = int(
            config["sample"]["additional_regime_pore_count"].get(
                surface_regime, -1
            )
        )
        observed_additional_pores = int(
            sample_record.get("additional_regime_pore_count", -1)
        )
        body_profile = str(sample_record.get("body_profile", ""))
        notch = sample_record.get("spall_notch_cm")
        notch_side = sample_record.get("spall_notch_side")
        fracture_tooth_count = int(
            sample_record.get("spall_fracture_tooth_count", -1)
        )
        cylinder_spall_size = sample_record.get(
            "cylinder_spall_patch_size_cm"
        )
        cylinder_spall_angle = sample_record.get(
            "cylinder_spall_patch_angle_deg"
        )
        cylinder_spall_aggregate_count = int(
            sample_record.get("cylinder_spall_aggregate_count", -1)
        )
        notch_contract_valid = False
        if shape == "cube" and surface_regime == "spalled":
            notch_ranges = config["sample"]["spalled_cube_notch_fraction_range"]
            tooth_range = list(
                map(
                    int,
                    config["sample"][
                        "spalled_cube_fracture_tooth_count_range"
                    ],
                )
            )
            sample_dims = list(map(float, sample_record["dimensions_cm"]))
            notch_contract_valid = (
                body_profile
                == "notched_upper_front_corner_with_inset_aggregate_v5"
                and isinstance(notch, list)
                and len(notch) == 3
                and notch_side in {"left", "right"}
                and tooth_range[0]
                <= fracture_tooth_count
                <= tooth_range[1]
                and cylinder_spall_size is None
                and cylinder_spall_angle is None
                and cylinder_spall_aggregate_count == 0
                and all(
                    float(notch_ranges[axis][0]) * sample_dims[index]
                    <= float(notch[index])
                    <= float(notch_ranges[axis][1]) * sample_dims[index]
                    for index, axis in enumerate(("x", "y", "z"))
                )
            )
        elif shape == "cylinder" and surface_regime == "spalled":
            patch_bounds = list(
                map(
                    float,
                    config["sample"]["spalled_cylinder_patch_size_cm"],
                )
            )
            notch_contract_valid = (
                body_profile
                == "solid_nominal_with_additive_faceted_spall_proxy_v1"
                and notch is None
                and notch_side is None
                and fracture_tooth_count == 0
                and isinstance(cylinder_spall_size, list)
                and len(cylinder_spall_size) == 2
                and patch_bounds[0]
                <= float(cylinder_spall_size[0])
                <= patch_bounds[1]
                and patch_bounds[0] * 0.72
                <= float(cylinder_spall_size[1])
                <= patch_bounds[1] * 1.08
                and cylinder_spall_angle is not None
                and -58.5 <= float(cylinder_spall_angle) <= 58.5
                and 18 <= cylinder_spall_aggregate_count <= 26
                and sample_record.get("cylinder_spall_status")
                == config["sample"]["spalled_cylinder_patch_status"]
            )
        else:
            notch_contract_valid = (
                body_profile == "solid_nominal_v1"
                and notch is None
                and notch_side is None
                and fracture_tooth_count == 0
                and cylinder_spall_size is None
                and cylinder_spall_angle is None
                and cylinder_spall_aggregate_count == 0
            )
        pore_min, pore_max = map(int, config["sample"]["pore_count_range"])
        expected_pore_count = int(
            pore_min + float(sample_record["damage"]) * (pore_max - pore_min)
        )
        observed_pore_radius_range = sample_record.get(
            "pore_radius_range_cm", []
        )
        pore_contract_valid = (
            int(sample_record.get("pore_count", -1)) == expected_pore_count
            and isinstance(observed_pore_radius_range, list)
            and len(observed_pore_radius_range) == 2
            and all(
                math.isclose(float(actual), float(expected), abs_tol=1e-9)
                for actual, expected in zip(
                    observed_pore_radius_range,
                    config["sample"]["pore_radius_cm"],
                )
            )
            and math.isclose(
                float(sample_record.get("pore_radius_distribution_power", -1.0)),
                float(config["sample"]["pore_radius_distribution_power"]),
                abs_tol=1e-9,
            )
        )
        aggregate_count = int(
            sample_record.get("exposed_aggregate_count", -1)
        )
        aggregate_count_range = config["sample"][
            "exposed_aggregate_count_range_by_regime"
        ].get(surface_regime)
        aggregate_radius_range = sample_record.get(
            "exposed_aggregate_radius_range_cm", []
        )
        aggregate_material_counts = sample_record.get(
            "exposed_aggregate_material_counts", {}
        )
        aggregate_contract_valid = (
            aggregate_count_range is not None
            and int(aggregate_count_range[0])
            <= aggregate_count
            <= int(aggregate_count_range[1])
            and isinstance(aggregate_radius_range, list)
            and len(aggregate_radius_range) == 2
            and all(
                math.isclose(float(actual), float(expected), abs_tol=1e-9)
                for actual, expected in zip(
                    aggregate_radius_range,
                    config["sample"]["exposed_aggregate_radius_cm"],
                )
            )
            and isinstance(aggregate_material_counts, dict)
            and set(aggregate_material_counts)
            == {"light_aggregate", "dark_mortar", "body_tone"}
            and sum(map(int, aggregate_material_counts.values()))
            == aggregate_count
        )
        if (
            surface_regime not in allowed_regimes
            or relief_range is None
            or not int(relief_range[0]) <= edge_relief_count <= int(relief_range[1])
            or not size_range_valid
            or sample_record.get("surface_profile")
            != "fine_cast_tone_with_irregular_flush_pores_exposed_aggregate_spall_and_load_zone_v7"
            or sample_record.get("pore_proxy_profile")
            != "single_layer_low_contrast_variable_aspect_flush_void_v3"
            or not notch_contract_valid
            or not pore_contract_valid
            or not aggregate_contract_valid
            or not weathering_contract_valid
            or sample_record.get("spall_notch_status")
            != config["sample"]["spalled_cube_notch_status"]
            or sample_record.get("cylinder_spall_status")
            != config["sample"]["spalled_cylinder_patch_status"]
            or observed_additional_pores != expected_additional_pores
            or sample_record.get("surface_regime_distribution_status")
            != config["sample"]["surface_regime_status"]
        ):
            errors.append(
                f"concrete_surface_regime_contract_mismatch:{stem}:"
                f"{shape}:{surface_regime}:{edge_relief_count}:{observed_size_range}"
            )
        else:
            concrete_surface_regimes_checked += 1
            concrete_surface_regime_counts[surface_regime] += 1
            concrete_body_profiles_checked += 1
            concrete_body_profile_counts[body_profile] += 1
            concrete_top_load_weathering_checked += 1
            concrete_top_load_weathering_patch_total += weathering_patch_count
        lower_face = raw.get("machine", {}).get("lower_contact_face")
        if not isinstance(lower_face, dict):
            errors.append(f"missing_lower_contact_face:{stem}")
        else:
            expected_lower_diameter = (
                2.0
                * float(machine_cfg["lower_platen_radius_cm"])
                * float(machine_cfg["lower_contact_face_diameter_scale"])
            )
            expected_lower_thickness = float(
                machine_cfg["lower_contact_face_thickness_cm"]
            )
            sample_bottom = float(raw["sample"]["location_cm"][2]) - float(
                raw["sample"]["dimensions_cm"][2]
            ) / 2.0
            specimen_gap = sample_bottom - float(lower_face.get("top_z_cm", -1.0))
            lower_profile = str(lower_face.get("surface_profile", ""))
            if (
                not math.isclose(
                    float(lower_face.get("diameter_cm", -1.0)),
                    expected_lower_diameter,
                    abs_tol=0.002,
                )
                or not math.isclose(
                    float(lower_face.get("thickness_cm", -1.0)),
                    expected_lower_thickness,
                    abs_tol=0.002,
                )
                or not math.isclose(specimen_gap, 0.0, abs_tol=0.002)
                or lower_profile
                not in machine_cfg["lower_contact_face_surface_profile_weights"]
                or lower_face.get("surface_status")
                != machine_cfg["lower_contact_face_surface_status"]
            ):
                errors.append(
                    f"lower_contact_face_contract_mismatch:{stem}:"
                    f"{lower_face}:gap={specimen_gap}"
                )
            else:
                lower_contact_faces_checked += 1
                lower_contact_face_profile_counts[lower_profile] += 1
        face = raw.get("machine", {}).get("upper_contact_face")
        if not isinstance(face, dict):
            errors.append(f"missing_upper_contact_face:{stem}")
        else:
            expected_diameter = 2.0 * float(machine_cfg["upper_platen_radius_cm"]) * float(
                machine_cfg["upper_contact_face_diameter_scale"]
            )
            expected_thickness = float(machine_cfg["upper_contact_face_thickness_cm"])
            sample_top = float(raw["sample"]["location_cm"][2]) + float(
                raw["sample"]["dimensions_cm"][2]
            ) / 2.0
            contact_gap = float(face.get("bottom_z_cm", -1.0)) - sample_top
            # Unreal tag dimensions are [length, physical thickness, height].
            minimum_gap = float(config["rfid_tag"]["size_cm"][1]) * 2.0
            if (
                not math.isclose(
                    float(face.get("diameter_cm", -1.0)),
                    expected_diameter,
                    abs_tol=0.002,
                )
                or not math.isclose(
                    float(face.get("thickness_cm", -1.0)),
                    expected_thickness,
                    abs_tol=0.002,
                )
                or contact_gap < minimum_gap
                or contact_gap > 0.10
                or face.get("material_profile")
                != machine_cfg["upper_contact_face_material_profile"]
            ):
                errors.append(
                    f"upper_contact_face_contract_mismatch:{stem}:{face}:gap={contact_gap}"
                )
            else:
                upper_contact_faces_checked += 1
        rgb_path = root / "raw" / "images" / f"{stem}.png"
        if not rgb_path.exists():
            errors.append(f"missing_rgb:{stem}")
            continue
        rgb = image_metrics(rgb_path)
        rgb_hashes.setdefault(rgb["sha256"], []).append(stem)
        if list(raw.get("resolution_px", [])) != rgb["resolution_px"]:
            errors.append(f"rgb_resolution_metadata_mismatch:{stem}:{raw.get('resolution_px')}:{rgb['resolution_px']}")
        if rgb["clipped_highlight_fraction"] > 0.35:
            errors.append(f"rgb_excessive_clipping:{stem}:{rgb['clipped_highlight_fraction']:.4f}")
        if max(rgb["mean_rgb"]) < 12:
            errors.append(f"rgb_too_dark:{stem}:{rgb['mean_rgb']}")

        concrete_key = raw["sample"]["instance_key"]
        concrete_visible_path = root / "raw" / "masks_visible" / f"{stem}__{concrete_key}.png"
        concrete_amodal_path = root / "raw" / "masks_amodal" / f"{stem}__{concrete_key}.png"
        concrete_visible = mask_stats(concrete_visible_path)
        concrete_amodal = mask_stats(concrete_amodal_path)
        if concrete_visible is None:
            errors.append(f"concrete_not_visible:{stem}")
            continue
        if concrete_amodal is None:
            errors.append(f"concrete_amodal_missing_or_empty:{stem}")
            continue
        for mask_name, mask in (("concrete_visible", concrete_visible), ("concrete_amodal", concrete_amodal)):
            if mask["resolution_px"] != rgb["resolution_px"]:
                errors.append(f"mask_resolution_mismatch:{stem}:{mask_name}:{mask['resolution_px']}:{rgb['resolution_px']}")
        cell = f"{camera}:{shape}"
        concrete_cells.setdefault(cell, []).append(concrete_visible["yolo"])

        instance_records = []
        statuses = []
        label_lines = []
        raw_instance_count += 1 + len(raw["rfid_instances"])
        raw_tag_keys = {item["instance_key"] for item in raw["rfid_instances"]}
        for paper in raw.get("paper_labels", []):
            mode = str(paper.get("occlusion_mode", "unknown"))
            paper_occlusion_counts[mode] += 1
            if (
                paper.get("colour_profile")
                not in config["paper_label"]["colour_profile_weights"]
                or paper.get("target_class") is not None
                or paper.get("orange_decoy_is_rfid") is not False
            ):
                errors.append(
                    f"paper_colour_or_target_contract_mismatch:{stem}:{paper}"
                )
            linked_key = paper.get("linked_rfid_instance_key")
            if linked_key is not None:
                paper_links_checked += 1
                if linked_key not in raw_tag_keys:
                    errors.append(f"paper_link_missing_rfid:{stem}:{linked_key}")
                    continue
                linked_tag = next(
                    item for item in raw["rfid_instances"] if item["instance_key"] == linked_key
                )
                linked_mode = linked_tag.get("paper_occlusion", {}).get("mode")
                if linked_mode != mode:
                    errors.append(
                        f"paper_link_mode_mismatch:{stem}:{linked_key}:{mode}:{linked_mode}"
                    )
        for instance in raw["rfid_instances"]:
            key = instance["instance_key"]
            state = str(instance.get("state", ""))
            contact_model = str(instance.get("contact_model", ""))
            expected_contact_model = (
                "cylinder_conformed_arc"
                if state in {"sample_front", "sample_side"} and shape == "cylinder"
                else "planar_sample_face"
                if state in {"sample_front", "sample_side"}
                else "plate_gap_visible_tip"
                if state in {"plate_gap_top", "plate_gap_bottom"}
                else "loose_platen"
                if state == "loose_front"
                else ""
            )
            contact_error = False
            try:
                normal = list(map(float, instance["surface_normal_world"]))
                length_axis = list(map(float, instance["length_axis_world"]))
                normal_norm = math.sqrt(sum(value * value for value in normal))
                length_norm = math.sqrt(sum(value * value for value in length_axis))
                orthogonality = abs(
                    sum(a * b for a, b in zip(normal, length_axis))
                )
                if (
                    len(normal) != 3
                    or len(length_axis) != 3
                    or not math.isclose(normal_norm, 1.0, abs_tol=1e-5)
                    or not math.isclose(length_norm, 1.0, abs_tol=1e-5)
                    or orthogonality > 1e-5
                ):
                    contact_error = True
            except (KeyError, TypeError, ValueError):
                contact_error = True
            visible_tip = instance.get("visible_tip_target_cm")
            visible_tip_regime = instance.get("visible_tip_regime")
            if state in {"plate_gap_top", "plate_gap_bottom"}:
                modulo = int(config["rfid_tag"]["plate_gap_tip_regime_seed_modulo"])
                expected_tip_regime = config["rfid_tag"][
                    "plate_gap_tip_regime_by_remainder"
                ][str(int(raw["seed"]) % modulo)]
                tip_key = (
                    "plate_gap_top_cm"
                    if state == "plate_gap_top"
                    else "plate_gap_bottom_cm"
                )
                tip_range = list(
                    map(
                        float,
                        config["rfid_tag"]["plate_gap_tip_regimes"][
                            expected_tip_regime
                        ][tip_key],
                    )
                )
                if (
                    visible_tip_regime != expected_tip_regime
                    or visible_tip is None
                    or not tip_range[0] <= float(visible_tip) <= tip_range[1]
                ):
                    contact_error = True
            elif visible_tip is not None or visible_tip_regime is not None:
                contact_error = True
            expected_conform_segments = (
                int(config["rfid_tag"]["cylinder_conform_segments"])
                if expected_contact_model == "cylinder_conformed_arc"
                else 1
            )
            if int(instance.get("conform_segment_count", 0)) != expected_conform_segments:
                contact_error = True
            if (
                instance.get("contact_profile")
                != config["rfid_tag"]["contact_profile"]
                or contact_model != expected_contact_model
                or contact_error
            ):
                errors.append(
                    f"rfid_contact_contract_mismatch:{stem}:{key}:"
                    f"{state}:{contact_model}:{visible_tip}"
                )
            else:
                rfid_contact_models_checked += 1
                rfid_contact_model_counts[contact_model] += 1
                if visible_tip_regime is not None:
                    rfid_visible_tip_regime_counts[str(visible_tip_regime)] += 1
            visible_path = root / "raw" / "masks_visible" / f"{stem}__{key}.png"
            amodal_path = root / "raw" / "masks_amodal" / f"{stem}__{key}.png"
            if not visible_path.exists() or not amodal_path.exists():
                errors.append(f"missing_instance_mask:{stem}:{key}")
                continue
            visible = mask_stats(visible_path, include_components=True)
            amodal = mask_stats(amodal_path)
            for mask_name, mask in (("visible", visible), ("amodal", amodal)):
                if mask and mask["resolution_px"] != rgb["resolution_px"]:
                    errors.append(f"mask_resolution_mismatch:{stem}:{key}:{mask_name}:{mask['resolution_px']}:{rgb['resolution_px']}")
            decision = classify_rfid(visible, amodal, policy)
            statuses.append(decision["label_status"])
            status_counts[decision["label_status"]] += 1
            if visible:
                visible_nonempty_hashes.setdefault(visible["sha256"], []).append(f"{stem}:{key}")
            if visible and amodal and visible["pixels"] > amodal["pixels"] * 1.08 + 8:
                errors.append(f"visible_exceeds_amodal:{stem}:{key}:{visible['pixels']}:{amodal['pixels']}")
            if visible and decision["include_in_yolo"]:
                label_lines.append("0 " + " ".join(f"{value:.8f}" for value in visible["yolo"]))
            instance_records.append({**instance, "visible_mask": visible, "amodal_mask": amodal, "detection_policy": decision})

        label_lines.append("1 " + " ".join(f"{value:.8f}" for value in concrete_visible["yolo"]))
        if "excluded_too_small_or_occluded" in statuses:
            partition = "exclude"
        elif "hard_positive" in statuses:
            partition = "hard_occlusion"
        else:
            partition = "standard"
        partition_counts[partition] += 1
        manifest_stems[partition].append(stem)
        partition_root = root / "partitions" / partition
        (partition_root / "images").mkdir(parents=True, exist_ok=True)
        (partition_root / "labels").mkdir(parents=True, exist_ok=True)
        shutil.copy2(rgb_path, partition_root / "images" / rgb_path.name)
        (partition_root / "labels" / f"{stem}.txt").write_text("\n".join(label_lines) + "\n", encoding="utf-8")

        enriched = {
            **raw,
            "annotation_partition": partition,
            "annotations": {
                "mask_threshold": MASK_THRESHOLD,
                "concrete_sample": {"visible": concrete_visible, "amodal": concrete_amodal},
                "rfid_instances": instance_records,
                "yolo_label_lines": label_lines,
            },
            "rgb_qc": rgb,
        }
        output_metadata = root / "metadata" / f"{stem}.json"
        output_metadata.parent.mkdir(parents=True, exist_ok=True)
        output_metadata.write_text(json.dumps(enriched, indent=2, sort_keys=True), encoding="utf-8")
        generated_records.append(enriched)

        depth_declared = str(raw.get("render_outputs", {}).get("depth", ""))
        if expect_depth or depth_declared:
            depth_path = root / "raw" / "depth" / f"{stem}.exr"
            if not depth_path.is_file() or depth_path.stat().st_size < 1024:
                errors.append(f"missing_or_small_depth:{stem}")
            else:
                with depth_path.open("rb") as handle:
                    magic = handle.read(4)
                if magic != b"\x76\x2f\x31\x01":
                    errors.append(f"invalid_openexr_magic:{stem}:{magic.hex()}")
                depth_hashes.setdefault(sha256(depth_path), []).append(stem)

    for digest, instances in visible_nonempty_hashes.items():
        if len(instances) > 1:
            errors.append(f"duplicate_nonempty_visible_mask:{digest}:{','.join(instances)}")
    for digest, stems in rgb_hashes.items():
        if len(stems) > 1:
            errors.append(f"duplicate_rgb:{digest}:{','.join(stems)}")

    frame_count = len(generated_records)
    raw_rgb_count = len(list((root / "raw" / "images").glob("*.png")))
    raw_depth_count = len(list((root / "raw" / "depth").glob("*.exr")))
    visible_mask_count = len(list((root / "raw" / "masks_visible").glob("*.png")))
    amodal_mask_count = len(list((root / "raw" / "masks_amodal").glob("*.png")))
    if raw_rgb_count != frame_count:
        errors.append(f"raw_rgb_count_mismatch:{raw_rgb_count}:{frame_count}")
    if visible_mask_count != raw_instance_count:
        errors.append(f"visible_mask_count_mismatch:{visible_mask_count}:{raw_instance_count}")
    if amodal_mask_count != raw_instance_count:
        errors.append(f"amodal_mask_count_mismatch:{amodal_mask_count}:{raw_instance_count}")
    if expect_depth and raw_depth_count != frame_count:
        errors.append(f"depth_count_mismatch:{raw_depth_count}:{frame_count}")
    if camera_model_manifest:
        if int(camera_model_manifest.get("frame_count", -1)) != frame_count:
            errors.append(
                f"camera_model_frame_count_mismatch:"
                f"{camera_model_manifest.get('frame_count')}:{frame_count}"
            )
        if int(camera_model_manifest.get("visible_mask_count", -1)) != visible_mask_count:
            errors.append(
                f"camera_model_visible_count_mismatch:"
                f"{camera_model_manifest.get('visible_mask_count')}:{visible_mask_count}"
            )
        if int(camera_model_manifest.get("amodal_mask_count", -1)) != amodal_mask_count:
            errors.append(
                f"camera_model_amodal_count_mismatch:"
                f"{camera_model_manifest.get('amodal_mask_count')}:{amodal_mask_count}"
            )
    if run_manifest and int(run_manifest.get("count", -1)) != frame_count:
        errors.append(f"run_manifest_count_mismatch:{run_manifest.get('count')}:{frame_count}")
    if frame_count >= 4:
        if not partition_counts["standard"] and not partition_counts["hard_occlusion"]:
            errors.append("all_frames_excluded_from_training")
        if partition_counts["exclude"] / frame_count > 0.75:
            warnings.append(
                f"exclude_partition_dominates:"
                f"{partition_counts['exclude']}:{frame_count}"
            )
        for expected_camera in ("camera_angled", "camera_door"):
            if not camera_counts[expected_camera]:
                errors.append(f"missing_camera_coverage:{expected_camera}")
        for expected_shape in ("cube", "cylinder"):
            if not shape_counts[expected_shape]:
                errors.append(f"missing_shape_coverage:{expected_shape}")

    manifests_root = root / "manifests"
    manifests_root.mkdir(parents=True, exist_ok=True)
    for partition, stems in manifest_stems.items():
        (manifests_root / f"{partition}_images.txt").write_text(
            "".join(f"partitions/{partition}/images/{stem}.png\n" for stem in stems), encoding="utf-8"
        )

    concrete_comparison = {}
    for cell, boxes in sorted(concrete_cells.items()):
        medians = [sorted(values)[len(values) // 2] for values in zip(*boxes)]
        target = config["evidence"]["real_concrete_bbox_medians_yolo"].get(cell)
        delta = [abs(a - b) for a, b in zip(medians, target)] if target else None
        within_gate = bool(delta and max(delta) <= 0.06)
        concrete_comparison[cell] = {
            "count": len(boxes),
            "synthetic_median": medians,
            "real_target": target,
            "absolute_delta": delta,
            "within_visual_gate_abs_0_06": within_gate,
        }
        if target and not within_gate:
            warnings.append(f"concrete_bbox_visual_gate:{cell}:{delta}")
    if frame_count >= 4:
        for expected_cell in (
            "camera_angled:cube",
            "camera_angled:cylinder",
            "camera_door:cube",
            "camera_door:cylinder",
        ):
            if expected_cell not in concrete_comparison:
                errors.append(f"missing_camera_shape_cell:{expected_cell}")

    result = {
        "schema_version": 1,
        "ok": not errors,
        "root": portable_path(root),
        "config": portable_path(config_path),
        "config_sha256": config_digest,
        "frame_count": frame_count,
        "artifact_counts": {
            "raw_rgb": raw_rgb_count,
            "raw_depth_exr": raw_depth_count,
            "raw_metadata": len(metadata_paths),
            "expected_physical_instances": raw_instance_count,
            "visible_masks": visible_mask_count,
            "amodal_masks": amodal_mask_count,
            "unique_depth_hashes": len(depth_hashes),
        },
        "partition_counts": dict(sorted(partition_counts.items())),
        "rfid_status_counts": dict(sorted(status_counts.items())),
        "camera_counts": dict(sorted(camera_counts.items())),
        "sample_shape_counts": dict(sorted(shape_counts.items())),
        "paper_occlusion_counts": dict(sorted(paper_occlusion_counts.items())),
        "paper_links_checked": paper_links_checked,
        "door_angles_checked": door_angles_checked,
        "door_profile_counts": dict(sorted(door_profile_counts.items())),
        "interior_finish_contracts_checked": interior_finish_contracts_checked,
        "fixed_camera_stacks_checked": fixed_camera_stacks_checked,
        "camera_model_contracts_checked": camera_model_contracts_checked,
        "camera_randomization_contracts_checked": (
            camera_randomization_contracts_checked
        ),
        "lower_contact_faces_checked": lower_contact_faces_checked,
        "lower_contact_face_profile_counts": dict(
            sorted(lower_contact_face_profile_counts.items())
        ),
        "upper_contact_faces_checked": upper_contact_faces_checked,
        "debris_contracts_checked": debris_contracts_checked,
        "concrete_surface_regimes_checked": concrete_surface_regimes_checked,
        "concrete_surface_regime_counts": dict(
            sorted(concrete_surface_regime_counts.items())
        ),
        "concrete_body_profiles_checked": concrete_body_profiles_checked,
        "concrete_body_profile_counts": dict(
            sorted(concrete_body_profile_counts.items())
        ),
        "concrete_top_load_weathering_checked": concrete_top_load_weathering_checked,
        "concrete_top_load_weathering_patch_total": concrete_top_load_weathering_patch_total,
        "rfid_contact_models_checked": rfid_contact_models_checked,
        "rfid_contact_model_counts": dict(sorted(rfid_contact_model_counts.items())),
        "rfid_visible_tip_regime_counts": dict(
            sorted(rfid_visible_tip_regime_counts.items())
        ),
        "concrete_bbox_comparison": concrete_comparison,
        "errors": errors,
        "warnings": warnings,
    }
    (root / "validation.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = process(args.root.resolve(), args.config.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
