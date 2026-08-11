from pathlib import Path

import pytest
import yaml

from scripts.render_pre_real_data_ceiling_gallery_v1 import (
    locked_inputs,
    selected_threshold,
)


CONFIG = Path("configs/benchmark/pre_real_data_ceiling_gallery_v1.yaml")


def test_locked_gallery_inputs_bind_selected_model_and_threshold() -> None:
    locked = locked_inputs(CONFIG)
    config = locked["config"]
    threshold = selected_threshold(
        locked["diagnostics"],
        config["model_name"],
        config["primary_method"],
        config["primary_service_minimum_sqrt_box_px"],
    )
    assert threshold == pytest.approx(0.76)
    assert locked["indices"] == [0, 150]
    assert locked["diagnostics"]["decision"]["field_fire_go"] is False


def test_gallery_config_preserves_fixed_bonirob_boundary() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["primary_service_minimum_sqrt_box_px"] == 82
    assert config["minimum_component_area_px"] == 16
    assert "BoniRob" in " ".join(config["claims"])
