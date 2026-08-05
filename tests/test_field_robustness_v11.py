from pathlib import Path

import pytest

from scripts.generate_cropcraft_profiled_pilot import (
    profile_contract,
    profiled_scene_config,
)
from scripts.generate_cropcraft_profiled_pilot_v2 import stratified_index
from scripts.convert_cropcraft_field_robustness_quarantined_release import (
    violation_reasons,
)


def minimal_study(asset_pack: Path) -> dict:
    return {
        "base_seed": 700,
        "frames_per_scene": 1,
        "crop_bed_name": "sorghum_rows",
        "crop_plant_type": "sorghum_seedling_v2",
        "cycle_crop_asset_heights": True,
        "asset_profile": {
            "ground_material_ids": ["soil"],
            "environment_files": ["sun.hdr", "cloud.hdr"],
            "surface_profile": "field_robustness_v10",
            "surface_parameter_ranges": {
                "environment_strength": "environment_strength",
                "sun_energy": "sun_energy",
            },
        },
        "weed_density_ranges": {"broadleaf": "broadleaf_density"},
        "ranges": {
            "environment_rotation_deg": [0, 360],
            "camera_height_m": [0.5, 0.5],
            "camera_fov_deg": [60, 60],
            "camera_roll_deg": [0, 0],
            "camera_pitch_deg": [0, 0],
            "camera_yaw_deg": [0, 0],
            "camera_y_jitter_m": [0.04, 0.04],
            "crop_asset_heights_m": [0.13],
            "crop_height_scale": [1, 1],
            "crop_height_tolerance": [0.1, 0.1],
            "within_row_spacing_m": [0.25, 0.25],
            "between_row_spacing_m": [0.7, 0.7],
            "position_noise_m": [0.02, 0.02],
            "tilt_noise_rad": [0.05, 0.05],
            "scale_noise": [0.1, 0.1],
            "missing_crop_probability": [0, 0],
            "broadleaf_density": [10, 10],
            "stone_density": [10, 10],
            "environment_strength": [0, 2],
            "sun_energy": [0, 2],
        },
        "correlated_scene_profiles": [
            {
                "name": "sunny",
                "environment_files": ["sun.hdr"],
                "surface_parameter_ranges": {
                    "environment_strength": [0.6, 0.8],
                    "sun_energy": [0.9, 1.1],
                },
            },
            {
                "name": "overcast",
                "environment_files": ["cloud.hdr"],
                "surface_parameter_ranges": {
                    "environment_strength": [0.8, 1.0],
                    "sun_energy": [0.0, 0.2],
                },
            },
        ],
    }


def minimal_base() -> dict:
    return {
        "output_enabled": [],
        "render": {
            "frames": 1,
            "env_rotation_deg": 0,
            "camera": {
                "height": 0.5,
                "fov_deg": 60,
                "roll_deg": 0,
                "pitch_deg": 0,
                "yaw_deg": 0,
                "y_jitter": 0.04,
            },
        },
        "field": {
            "random_seed": 1,
            "beds": {
                "sorghum_rows": {
                    "plant_type": "sorghum_seedling_v2",
                    "plant_height": 0.13,
                    "height_tolerance_coeff": 0.1,
                    "plant_distance": 0.25,
                    "row_distance": 0.7,
                }
            },
            "noise": {"position": 0, "tilt": 0, "scale": 0, "missing": 0},
            "weeds": {"broadleaf": {"density": 10, "max_height": 0.08}},
            "stones": {"density": 10},
        },
    }


def test_profiles_override_coupled_light_and_environment(tmp_path: Path) -> None:
    asset_pack = tmp_path / "pack"
    (asset_pack / "environments").mkdir(parents=True)
    for name in ("sun.hdr", "cloud.hdr"):
        (asset_pack / "environments" / name).write_bytes(b"hdr")
    study = minimal_study(asset_pack)
    sunny = profiled_scene_config(minimal_base(), study, 0, asset_pack)
    overcast = profiled_scene_config(minimal_base(), study, 1, asset_pack)
    assert sunny["agri_asset_profile"]["correlated_scene_profile"] == "sunny"
    assert overcast["agri_asset_profile"]["correlated_scene_profile"] == "overcast"
    assert sunny["agri_asset_profile"]["environment_file"] == "sun.hdr"
    assert overcast["agri_asset_profile"]["environment_file"] == "cloud.hdr"
    assert sunny["agri_asset_profile"]["surface_parameters"]["sun_energy"] >= 0.9
    assert overcast["agri_asset_profile"]["surface_parameters"]["sun_energy"] <= 0.2


def test_profile_contract_rejects_duplicate_names(tmp_path: Path) -> None:
    study = minimal_study(tmp_path)
    study["correlated_scene_profiles"][1]["name"] = "sunny"
    with pytest.raises(ValueError, match="must be unique"):
        profile_contract(study)


def test_stratified_index_is_a_full_deterministic_permutation() -> None:
    first = [stratified_index(rank, 10, "profile|sun") for rank in range(10)]
    second = [stratified_index(rank, 10, "profile|sun") for rank in range(10)]
    assert first == second
    assert sorted(first) == list(range(10))
    assert min(first) == 0
    assert max(first) == 9


def test_radiometry_quarantine_uses_strict_frozen_boundaries() -> None:
    thresholds = {
        "minimum_frame_mean_brightness": 40.0,
        "maximum_frame_mean_brightness": 240.0,
        "maximum_fully_clipped_white_fraction_per_frame": 0.002,
        "maximum_fully_clipped_black_fraction_per_frame": 0.001,
    }
    boundary = {
        "mean_all_channels": 40.0,
        "all_channels_ge_250_fraction": 0.002,
        "all_channels_le_5_fraction": 0.001,
    }
    assert violation_reasons(boundary, thresholds) == []
    boundary["mean_all_channels"] = 39.999
    boundary["all_channels_ge_250_fraction"] = 0.0021
    assert violation_reasons(boundary, thresholds) == [
        "mean_brightness_below_minimum",
        "fully_clipped_white_above_limit",
    ]
