from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.generate_cropcraft_deploy_constrained_pilot_v12 import (
    _frame_quality,
    _weed_component_bboxes,
)
from scripts.generate_cropcraft_deploy_profiled_pilot_v12 import (
    deploy_scene_config,
    ground_fov_deg,
)
from scripts.generate_cropcraft_field_robustness_pilot import load_study
from scripts.generate_cropcraft_field_robustness_pilot import role_study


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_tile_fov_preserves_quarter_module_ground_coverage() -> None:
    for height in (0.55, 0.60, 0.65):
        fov = ground_fov_deg(0.25, height)
        assert 21.0 < fov < 26.0


def test_v12_resolves_to_disjoint_roles_and_244_micrometre_gsd() -> None:
    path = Path("configs/simulation/cropcraft_deploy_constrained_pilot_v12.yaml")
    study, _ = load_study(path)
    assert set(study["splits"]) == {"train", "val", "test"}
    contract = study["deploy_imaging_contract"]
    gsd = contract["tile_ground_width_m"] * 1000 / contract["tile_resolution_px"]
    assert gsd == pytest.approx(0.244140625)
    assert study["splits"]["train"]["scenes"] == 40
    assert study["splits"]["val"]["scenes"] == 8
    assert study["splits"]["test"]["scenes"] == 8


def test_deploy_adapter_overrides_inherited_wide_camera_attitude() -> None:
    path = Path("configs/simulation/cropcraft_deploy_constrained_pilot_v12.yaml")
    study, _ = load_study(path)
    resolved = role_study(study, "train", Path("/tmp/not-rendered"))
    base = yaml.safe_load(
        (PROJECT_ROOT / resolved["base_config"]).read_text(encoding="utf-8")
    )
    asset_pack = Path(resolved["asset_pack"]).expanduser().resolve()
    config = deploy_scene_config(base, resolved, 0, asset_pack)
    camera = config["render"]["camera"]
    contract = resolved["deploy_imaging_contract"]
    for key, contract_key in (
        ("roll_deg", "camera_roll_deg"),
        ("pitch_deg", "camera_pitch_deg"),
        ("yaw_deg", "camera_yaw_deg"),
        ("y_jitter", "camera_y_jitter_m"),
    ):
        assert contract[contract_key][0] <= camera[key] <= contract[contract_key][1]
    assert config["render"]["resolution_x"] == 1024
    assert config["render"]["resolution_y"] == 1024


def test_deploy_scene_rejects_missing_contract() -> None:
    with pytest.raises(ValueError, match="deploy_imaging_contract"):
        deploy_scene_config({}, {"base_seed": 1}, 0, None)


def test_smoke_plan_inherits_full_capture_contract() -> None:
    path = Path("configs/simulation/cropcraft_deploy_constrained_smoke_v12.yaml")
    study, _ = load_study(path)
    assert study["deploy_imaging_contract"]["tile_resolution_px"] == 1024
    assert study["splits"]["train"]["scenes"] == 4
    assert study["splits"]["val"]["scenes"] == 2
    assert study["splits"]["test"]["scenes"] == 2
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["base_study"].endswith(
        "cropcraft_deploy_constrained_pilot_v12.yaml"
    )


def test_component_gate_uses_maximum_bbox_dimension() -> None:
    import numpy as np

    mask = np.zeros((64, 64), dtype=bool)
    mask[5:10, 7:50] = True
    mask[30:50, 30:50] = True
    assert sorted(_weed_component_bboxes(mask)) == [20, 43]


def test_frame_quality_reads_palette_and_actionable_component(
    tmp_path: Path,
) -> None:
    import numpy as np
    from PIL import Image

    rgb = np.full((1024, 1024, 3), 100, dtype=np.uint8)
    mask = np.zeros_like(rgb)
    mask[100:150, 200:230] = (255, 0, 0)
    rgb_path = tmp_path / "frame.jpg"
    mask_path = tmp_path / "frame.png"
    Image.fromarray(rgb).save(rgb_path)
    Image.fromarray(mask).save(mask_path)
    row = _frame_quality(rgb_path, mask_path, 41)
    assert row["weed_component_count"] == 1
    assert row["actionable_weed_component_count"] == 1
    assert row["mean_all_channels"] == pytest.approx(100.0)
