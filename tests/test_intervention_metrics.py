from __future__ import annotations

import numpy as np

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from scripts.evaluate_intervention_metrics import (
    InterventionAccumulator,
    _best_overlap_center_errors,
    _component_geometry,
)


def test_component_coverage_center_and_action_point_metrics() -> None:
    target = np.full((32, 32), BACKGROUND, dtype=np.uint8)
    target[4:12, 4:12] = WEED
    target[20:28, 20:28] = CROP
    semantic = np.full_like(target, BACKGROUND)
    semantic[4:12, 4:12] = WEED
    semantic[20:28, 20:28] = CROP
    safe = semantic == WEED

    accumulator = InterventionAccumulator()
    accumulator.update(target, semantic, safe, "toy")
    result = accumulator.compute()["overall"]
    mode = result["modes"]["frozen_safe_action"]
    components = mode["component_metrics"]["all"]
    actions = mode["action_point_metrics"]

    assert components["semantic_component_proxies"] == 1
    assert components["component_hit_recall_any_overlap"] == 1.0
    assert components["component_coverage_recall"]["at_least_90pct"] == 1.0
    assert components["center_proxy"]["recall_within_pixels"]["5"] == 1.0
    assert actions["action_points"] == 1
    assert actions["point_precision_on_weed"] == 1.0
    assert actions["point_crop_hit_rate"] == 0.0


def test_any_hit_differs_from_fifty_percent_coverage() -> None:
    target = np.full((40, 40), BACKGROUND, dtype=np.uint8)
    target[10:20, 10:20] = WEED
    semantic = np.full_like(target, BACKGROUND)
    semantic[10, 10] = WEED

    accumulator = InterventionAccumulator()
    accumulator.update(target, semantic, semantic == WEED, "toy")
    components = accumulator.compute()["overall"]["modes"]
    proxy = components["frozen_safe_action"]["component_metrics"]["all"]

    assert proxy["component_hit_recall_any_overlap"] == 1.0
    assert proxy["component_coverage_recall"]["at_least_10pct"] == 0.0
    assert proxy["component_coverage_recall"]["at_least_50pct"] == 0.0


def test_action_point_crop_hit_and_ignored_denominator() -> None:
    target = np.full((32, 32), BACKGROUND, dtype=np.uint8)
    target[2:8, 2:8] = WEED
    target[12:18, 12:18] = CROP
    target[24:30, 24:30] = IGNORE
    semantic = np.full_like(target, BACKGROUND)
    semantic[2:8, 2:8] = WEED
    semantic[12:18, 12:18] = WEED
    semantic[24:30, 24:30] = WEED

    accumulator = InterventionAccumulator()
    accumulator.update(target, semantic, semantic == WEED, "toy")
    actions = accumulator.compute()["overall"]["modes"]["semantic_argmax"]
    points = actions["action_point_metrics"]

    assert points["action_points"] == 3
    assert points["valid_action_points"] == 2
    assert points["ignored_action_points"] == 1
    assert points["point_precision_on_weed"] == 0.5
    assert points["point_crop_hit_rate"] == 0.5


def test_sub_patch_apparent_size_bin() -> None:
    target = np.full((64, 64), BACKGROUND, dtype=np.uint8)
    target[2:6, 2:6] = WEED  # equivalent diameter ~= 4.5 px
    target[20:40, 20:40] = WEED  # equivalent diameter ~= 22.6 px
    prediction = np.where(target == WEED, WEED, BACKGROUND).astype(np.uint8)

    accumulator = InterventionAccumulator()
    accumulator.update(target, prediction, prediction == WEED, "toy")
    result = accumulator.compute()["overall"]
    bins = result["modes"]["semantic_argmax"]["component_metrics"]

    assert bins["all"]["semantic_component_proxies"] == 2
    assert bins["sub_patch_lt14px"]["semantic_component_proxies"] == 1
    assert bins["one_to_two_patches_14_28px"]["semantic_component_proxies"] == 1
    assert result["gt_weed_semantic_component_diameter_px"]["sub_patch_fraction"] == 0.5


def test_overall_is_exact_merge_of_dataset_accumulators() -> None:
    first = np.full((24, 24), BACKGROUND, dtype=np.uint8)
    second = np.full((24, 24), BACKGROUND, dtype=np.uint8)
    first[2:8, 2:8] = WEED
    second[10:18, 10:18] = WEED
    first_prediction = np.where(first == WEED, WEED, BACKGROUND).astype(np.uint8)
    second_prediction = np.where(second == WEED, WEED, BACKGROUND).astype(np.uint8)

    accumulator = InterventionAccumulator()
    accumulator.update(first, first_prediction, first_prediction == WEED, "a")
    accumulator.update(second, second_prediction, second_prediction == WEED, "b")
    result = accumulator.compute()

    assert result["overall"]["images"] == 2
    assert result["by_dataset"]["a"]["images"] == 1
    assert result["by_dataset"]["b"]["images"] == 1
    assert (
        result["overall"]["modes"]["semantic_argmax"]["component_metrics"]["all"]
        ["semantic_component_proxies"]
        == 2
    )


def test_vectorized_overlap_match_preserves_smallest_label_tie_break() -> None:
    gt_labels = np.array([[1, 1, 1, 1]], dtype=np.int32)
    predicted_labels = np.array([[1, 1, 2, 2]], dtype=np.int32)
    errors_px, errors_radius = _best_overlap_center_errors(
        gt_labels=gt_labels,
        gt_count=1,
        gt_centers=np.array([[0.0, 0.0]]),
        gt_areas=np.array([4]),
        predicted_labels=predicted_labels,
        predicted_count=2,
        predicted_centers=np.array([[0.0, 1.0], [0.0, 10.0]]),
    )

    assert errors_px.tolist() == [1.0]
    assert np.isclose(errors_radius[0], np.sqrt(np.pi) / 2.0)


def test_sparse_component_geometry_has_exact_area_and_centroid() -> None:
    mask = np.zeros((20, 30), dtype=bool)
    mask[2:5, 3:7] = True
    mask[10, 20] = True

    labels, count, areas, centers, diameters = _component_geometry(mask)

    assert labels.shape == mask.shape
    assert count == 2
    assert areas.tolist() == [12, 1]
    assert np.allclose(centers, [[3.0, 4.5], [10.0, 20.0]])
    assert np.allclose(diameters, 2.0 * np.sqrt(areas / np.pi))
