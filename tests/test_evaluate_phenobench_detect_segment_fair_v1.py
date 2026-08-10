from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    Action,
    GroundTruth,
    _mask_interior_from_box_crop,
    classify_point,
    deepest_interior_point,
    evaluate_actions,
    paired_bootstrap_f1_difference,
    select_threshold,
)


def _truth() -> GroundTruth:
    return GroundTruth(
        sample_id="sample",
        image_path=Path("image.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={11: 10.0, 12: 30.0},
        crop_ids=frozenset({21}),
    )


def test_deepest_interior_point_is_inside_and_central() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[2:7, 1:8] = True
    point = deepest_interior_point(mask)
    assert point is not None
    assert mask[point[1], point[0]]
    assert point[1] == 4


def test_point_classification_respects_eligible_and_ignore_contract() -> None:
    semantics = np.asarray([[2, 2, 1, 4, 0]], dtype=np.uint16)
    instances = np.asarray([[11, 99, 21, 77, 0]], dtype=np.uint16)
    truth = _truth()
    assert classify_point(0, 0, semantics, instances, truth) == ("weed", 11)
    assert classify_point(1, 0, semantics, instances, truth) == ("ignore", 99)
    assert classify_point(2, 0, semantics, instances, truth) == ("crop", 21)
    assert classify_point(3, 0, semantics, instances, truth) == ("ignore", 77)
    assert classify_point(4, 0, semantics, instances, truth) == ("soil", None)


def test_box_cropped_mask_interior_matches_full_mask() -> None:
    mask = np.zeros((50, 60), dtype=np.uint8)
    mask[10:22, 7:31] = 1
    expected = deepest_interior_point(mask)
    actual = _mask_interior_from_box_crop(
        torch.from_numpy(mask.astype(np.float32)),
        (7.0, 10.0, 31.0, 22.0),
        mask.shape,
    )
    assert actual == expected


def test_action_metric_counts_duplicate_crop_soil_and_ignore() -> None:
    actions = {
        "sample": [
            Action("sample", 0.9, 1, 1, "weed", 11),
            Action("sample", 0.8, 2, 2, "weed", 11),
            Action("sample", 0.7, 3, 3, "crop", 21),
            Action("sample", 0.6, 4, 4, "soil", None),
            Action("sample", 0.5, 5, 5, "ignore", 99),
        ]
    }
    metric = evaluate_actions(actions, [_truth()], 0.5)
    assert metric["tp"] == 1
    assert metric["fp"] == 3
    assert metric["fn"] == 1
    assert metric["duplicate_action"] == 1
    assert metric["crop_collision"] == 1
    assert metric["soil_action"] == 1
    assert metric["ignored_action"] == 1
    assert metric["recall_by_sqrt_gt_box_area_px"]["lt14"]["recall"] == 1.0
    assert metric["recall_by_sqrt_gt_box_area_px"]["28_to_lt56"]["recall"] == 0.0


def test_threshold_selection_and_bootstrap_are_deterministic() -> None:
    curve = [
        {"threshold": 0.1, "f1": 0.6, "precision": 0.5, "recall": 0.75, "crop_collision_rate_per_attempt": 0.1},
        {"threshold": 0.2, "f1": 0.7, "precision": 0.7, "recall": 0.7, "crop_collision_rate_per_attempt": 0.05},
    ]
    selection = select_threshold(curve)
    assert selection["balanced_max_f1"]["threshold"] == 0.2
    assert selection["recall_95"]["attainable_on_validation"] is False

    detect = {"a": {"tp": 1, "fp": 1, "fn": 1}, "b": {"tp": 1, "fp": 0, "fn": 0}}
    segment = {"a": {"tp": 2, "fp": 0, "fn": 0}, "b": {"tp": 1, "fp": 0, "fn": 0}}
    left = paired_bootstrap_f1_difference(detect, segment, iterations=100, seed=4)
    right = paired_bootstrap_f1_difference(detect, segment, iterations=100, seed=4)
    assert left == right
    assert left["median_difference"] > 0
