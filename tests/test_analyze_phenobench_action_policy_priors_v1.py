from pathlib import Path

from scripts.analyze_phenobench_action_policy_priors_v1 import (
    confidence_grid,
    select_action_policies,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import Action, GroundTruth


def _truth() -> GroundTruth:
    return GroundTruth(
        sample_id="sample",
        image_path=Path("image.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={1: 50.0, 2: 60.0},
        crop_ids=frozenset({3}),
    )


def test_confidence_grid_is_inclusive() -> None:
    assert confidence_grid({"start": 0.1, "stop": 0.3, "step": 0.1}) == [
        0.1,
        0.2,
        0.3,
    ]


def test_safety_policy_can_differ_from_max_f1() -> None:
    actions = {
        "sample": [
            Action("sample", 0.9, 0, 0, "weed", 1),
            Action("sample", 0.6, 0, 0, "weed", 2),
            Action("sample", 0.7, 0, 0, "crop", 3),
        ]
    }
    selected = select_action_policies(
        actions,
        [_truth()],
        thresholds=[0.5, 0.75],
        minimum_gt_size_px=42,
        maximum_crop_collision_rate=0.0,
    )
    assert selected["max_f1"]["policy"]["confidence_threshold"] == 0.5
    assert selected["crop_safe_max_f1"]["policy"]["confidence_threshold"] == 0.75
    assert selected["crop_safe_max_f1"]["crop_collision"] == 0
