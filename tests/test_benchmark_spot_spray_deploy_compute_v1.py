from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.benchmark_spot_spray_deploy_compute_v1 import (
    derive_imaging_metrics,
    feature_pixels,
    gsd_mm_per_px,
    max_exposure_us,
    percentile,
    required_frame_rate_hz,
)


def test_deploy_geometry_makes_ten_mm_weed_about_41_pixels() -> None:
    gsd = gsd_mm_per_px(500.0, 2048)
    assert gsd == pytest.approx(0.244140625)
    assert feature_pixels(10.0, gsd) == pytest.approx(40.96)
    assert feature_pixels(20.0, gsd) == pytest.approx(81.92)


def test_motion_and_tracking_requirements_are_dimensionally_correct() -> None:
    gsd = 500.0 / 2048
    assert max_exposure_us(gsd, 1.0, 0.75) == pytest.approx(183.10546875)
    assert max_exposure_us(gsd, 0.5, 0.75) == pytest.approx(366.2109375)
    assert required_frame_rate_hz(1.0, 500.0, 3) == pytest.approx(6.0)
    assert required_frame_rate_hz(0.5, 500.0, 3) == pytest.approx(3.0)


def test_config_tile_grid_exactly_covers_raw_sensor() -> None:
    config = yaml.safe_load(
        Path("configs/benchmark/spot_spray_deploy_compute_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    metrics = derive_imaging_metrics(config["imaging_contract"])
    assert metrics["tiles_per_module_frame"] == 4
    assert metrics["model_input_size_px"] == 1024
    assert metrics["tile_world_width_mm"] == pytest.approx(250.0)
    assert metrics["weed_diameter_px"]["minimum_actionable"] == pytest.approx(40.96)


def test_percentile_interpolates_and_validation_rejects_invalid_values() -> None:
    assert percentile([1.0, 2.0, 3.0], 0.5) == pytest.approx(2.0)
    assert percentile([1.0, 2.0], 0.95) == pytest.approx(1.95)
    with pytest.raises(ValueError):
        percentile([], 0.5)
    with pytest.raises(ValueError):
        gsd_mm_per_px(0.0, 2048)


def test_halo_keeps_world_gsd_but_expands_model_input() -> None:
    config = yaml.safe_load(
        Path("configs/benchmark/spot_spray_deploy_compute_halo_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    metrics = derive_imaging_metrics(config["imaging_contract"])
    assert metrics["gsd_mm_per_px"] == pytest.approx(0.244140625)
    assert metrics["tile_core_size_px"] == 1024
    assert metrics["tile_halo_px"] == 64
    assert metrics["model_input_size_px"] == 1152
