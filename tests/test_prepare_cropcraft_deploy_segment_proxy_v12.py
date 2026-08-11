from __future__ import annotations

import numpy as np
import pytest

from scripts.prepare_cropcraft_deploy_segment_proxy_v12 import (
    apply_hsv_appearance_calibration,
    derive_midpoint_factors,
    region_objects,
    region_objects_and_truth,
)


def test_region_objects_maps_red_to_weed_and_green_to_crop() -> None:
    mask = np.zeros((64, 64, 3), dtype=np.uint8)
    mask[5:20, 5:25] = (255, 0, 0)
    mask[30:55, 35:60] = (0, 255, 0)
    objects, audit = region_objects(
        mask, minimum_area_px=16, polygon_epsilon_px=0.25
    )
    assert [obj.class_id for obj in objects] == [0, 1]
    assert all(obj.polygon_iou > 0.95 for obj in objects)
    assert audit["border_touching_regions"] == 0


def test_region_objects_uses_eight_connectivity_and_audits_border() -> None:
    mask = np.zeros((16, 16, 3), dtype=np.uint8)
    mask[0:5, 0:5] = (255, 0, 0)
    mask[5:10, 5:10] = (255, 0, 0)
    objects, audit = region_objects(
        mask, minimum_area_px=1, polygon_epsilon_px=0.0
    )
    assert len(objects) == 1
    assert audit["border_touching_regions"] == 1


def test_region_objects_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="HxWx3"):
        region_objects(
            np.zeros((8, 8), dtype=np.uint8),
            minimum_area_px=1,
            polygon_epsilon_px=0.0,
        )


def test_region_truth_arrays_match_action_evaluator_semantics() -> None:
    mask = np.zeros((32, 32, 3), dtype=np.uint8)
    mask[2:12, 3:15] = (255, 0, 0)
    mask[18:30, 20:31] = (0, 255, 0)
    objects, _, semantics, instances = region_objects_and_truth(
        mask, minimum_area_px=16, polygon_epsilon_px=0.25
    )
    assert [obj.class_id for obj in objects] == [0, 1]
    assert set(np.unique(semantics)) == {0, 1, 2}
    assert set(np.unique(instances)) == {0, 1, 2}
    assert np.all(semantics[instances == 1] == 2)
    assert np.all(semantics[instances == 2] == 1)


def test_midpoint_factors_move_each_class_halfway_to_reference() -> None:
    synthetic = {
        "weed": {"saturation": {"p50": 40}, "value": {"p50": 200}},
        "crop": {"saturation": {"p50": 80}, "value": {"p50": 220}},
    }
    reference = {
        "weed": {"saturation": {"p50": 120}, "value": {"p50": 120}},
        "crop": {"saturation": {"p50": 160}, "value": {"p50": 140}},
    }
    factors = derive_midpoint_factors(
        synthetic, reference, blend_fraction=0.5
    )
    assert factors["weed"]["saturation"] == pytest.approx(2.0)
    assert factors["weed"]["value"] == pytest.approx(0.8)
    assert factors["crop"]["saturation"] == pytest.approx(1.5)
    assert factors["crop"]["value"] == pytest.approx(180 / 220)


def test_hsv_calibration_preserves_background_exactly() -> None:
    rgb = np.full((12, 12, 3), (170, 130, 90), dtype=np.uint8)
    rgb[2:6, 2:6] = (125, 220, 120)
    rgb[7:11, 7:11] = (145, 225, 135)
    class_map = np.full((12, 12), -1, dtype=np.int8)
    class_map[2:6, 2:6] = 0
    class_map[7:11, 7:11] = 1
    result = apply_hsv_appearance_calibration(
        rgb,
        class_map,
        {
            "weed": {"saturation": 1.8, "value": 0.8},
            "crop": {"saturation": 1.5, "value": 0.75},
        },
        maximum_saturation=240,
        minimum_value=24,
    )
    assert np.array_equal(result[class_map < 0], rgb[class_map < 0])
    assert not np.array_equal(result[class_map == 0], rgb[class_map == 0])
    assert not np.array_equal(result[class_map == 1], rgb[class_map == 1])
    assert np.all(result[class_map >= 0, 1] > result[class_map >= 0, 0])
    assert np.all(result[class_map >= 0, 1] > result[class_map >= 0, 2])
