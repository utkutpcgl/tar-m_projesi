from pathlib import Path

from scripts.analyze_phenobench_actionable_size_v1 import (
    SizedAction,
    evaluate_policy,
    select_validation_policy,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import GroundTruth


def _truth() -> GroundTruth:
    return GroundTruth(
        sample_id="sample",
        image_path=Path("image.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={1: 10.0, 2: 40.0},
        crop_ids=frozenset({3}),
    )


def _action(
    confidence: float,
    target_kind: str,
    target_id: int | None,
    predicted_size: float,
) -> SizedAction:
    return SizedAction(
        sample_id="sample",
        confidence=confidence,
        x=0,
        y=0,
        target_kind=target_kind,
        target_instance_id=target_id,
        predicted_box_size_px=predicted_size,
        predicted_mask_size_px=predicted_size,
    )


def test_actionable_denominator_ignores_predeclared_small_weed() -> None:
    actions = {
        "sample": [
            _action(0.9, "weed", 1, 10),
            _action(0.8, "weed", 2, 35),
            _action(0.7, "soil", None, 8),
        ]
    }
    metric = evaluate_policy(
        actions,
        [_truth()],
        confidence_threshold=0.5,
        minimum_gt_size_px=28,
        minimum_prediction_size_px=0,
    )
    assert metric["eligible_gt_weeds"] == 1
    assert metric["tp"] == 1
    assert metric["fp"] == 1
    assert metric["ignored_small_gt_action"] == 1


def test_predicted_size_gate_is_deployable_and_selected_on_validation() -> None:
    actions = {
        "sample": [
            _action(0.9, "weed", 2, 35),
            _action(0.8, "soil", None, 8),
        ]
    }
    selected = select_validation_policy(
        actions,
        [_truth()],
        minimum_gt_size_px=28,
        confidence_thresholds=[0.5],
        prediction_size_thresholds=[0, 14],
    )
    assert selected["policy"]["minimum_prediction_size_px"] == 14
    assert selected["precision"] == 1.0
    assert selected["recall"] == 1.0
