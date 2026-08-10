from pathlib import Path

import numpy as np
import pytest

from scripts.prepare_phenobench_detect_segment_fair_v1 import (
    detection_label_line,
    logical_split,
    objects_from_arrays,
    plot_group,
    segmentation_label_line,
)


def test_plot_group_and_locked_split() -> None:
    assert plot_group("05-15_00028_P0030852") == "P0030852"
    assert logical_split("train", "P1", {"P2"}, {"P3"}) == "train"
    assert logical_split("val", "P2", {"P2"}, {"P3"}) == "val"
    assert logical_split("val", "P3", {"P2"}, {"P3"}) == "test"
    with pytest.raises(ValueError, match="Unassigned"):
        logical_split("val", "P4", {"P2"}, {"P3"})


def test_objects_share_exact_crop_weed_membership_for_both_arms() -> None:
    semantics = np.zeros((20, 20), dtype=np.uint16)
    instances = np.zeros_like(semantics)
    semantics[2:8, 2:8] = 2
    instances[2:8, 2:8] = 101
    semantics[10:18, 11:19] = 1
    instances[10:18, 11:19] = 7
    semantics[0:2, 10:15] = 4
    instances[0:2, 10:15] = 202
    objects, audit = objects_from_arrays(
        semantics,
        instances,
        minimum_area_px=16,
        polygon_epsilon_px=0.0,
    )
    assert [(item.class_id, item.instance_id, item.area) for item in objects] == [
        (1, 7, 64),
        (0, 101, 36),
    ]
    assert audit["instances_below_minimum_area"] == 0
    for item in objects:
        assert item.polygon_iou == pytest.approx(1.0)
        assert len(detection_label_line(item, 20, 20).split()) == 5
        assert len(segmentation_label_line(item, 20, 20).split()) >= 7


def test_tiny_full_instance_is_excluded_from_both_labels() -> None:
    semantics = np.zeros((8, 8), dtype=np.uint16)
    instances = np.zeros_like(semantics)
    semantics[1:3, 1:3] = 2
    instances[1:3, 1:3] = 9
    objects, audit = objects_from_arrays(
        semantics,
        instances,
        minimum_area_px=5,
        polygon_epsilon_px=0.0,
    )
    assert objects == []
    assert audit["instances_below_minimum_area"] == 1
