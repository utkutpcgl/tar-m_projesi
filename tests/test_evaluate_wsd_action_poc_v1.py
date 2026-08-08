from pathlib import Path

import numpy as np
import pytest

from scripts.evaluate_wsd_action_poc_v1 import (
    Instance,
    Prediction,
    Sample,
    choose_threshold,
    deduplicate_action_points,
    evaluate_actions,
    evaluate_detection,
    maximum_valid_pairs,
    point_footprint_hits_box,
    run,
    with_box_center_actions,
)


def prediction(
    point: tuple[float, float],
    *,
    confidence: float = 0.9,
    keypoint_confidence: float = 0.8,
) -> Prediction:
    return Prediction(
        class_id=0,
        confidence=confidence,
        box=(0.0, 0.0, 20.0, 20.0),
        point=point,
        keypoint_confidence=keypoint_confidence,
    )


def sample(predictions: tuple[Prediction, ...]) -> Sample:
    return Sample(
        image_path=Path("image.jpg"),
        width=100,
        height=100,
        ground_truth=(
            Instance(0, (0.0, 0.0, 20.0, 20.0), (10.0, 10.0)),
            Instance(0, (40.0, 40.0, 60.0, 60.0), (50.0, 50.0)),
            Instance(1, (70.0, 70.0, 90.0, 90.0), None),
        ),
        predictions=predictions,
    )


def test_maximum_valid_pairs_maximizes_cardinality() -> None:
    values = np.asarray([[1.0, 2.0], [1.1, 99.0]])
    valid = np.asarray([[True, True], [True, False]])
    pairs = maximum_valid_pairs(values, valid, prefer_larger=False)
    assert sorted(pairs) == [(0, 1), (1, 0)]


def test_action_metric_is_one_to_one_and_counts_false_fires() -> None:
    result = evaluate_actions(
        [sample((prediction((10.0, 10.0)), prediction((11.0, 10.0)), prediction((80.0, 80.0))))],
        0.5,
        tolerance_kind="pixels",
        tolerance=3.0,
    )
    assert result["true_positive"] == 1
    assert result["false_positive"] == 2
    assert result["false_negative"] == 1
    assert result["precision"] == pytest.approx(1 / 3)
    assert result["recall"] == pytest.approx(1 / 2)
    assert result["crop_box_collision"]["0"]["actions_colliding"] == 1
    assert result["false_positive_breakdown"][
        "duplicate_action_near_already_hit_stem"
    ] == 1
    assert result["false_positive_breakdown"]["sum"] == 2


def test_unmatched_weed_box_on_crop_counts_crop_false_fire() -> None:
    crop_prediction = Prediction(
        class_id=0,
        confidence=0.9,
        box=(70.0, 70.0, 90.0, 90.0),
        point=(80.0, 80.0),
        keypoint_confidence=0.9,
    )
    result = evaluate_actions(
        [sample((crop_prediction,))],
        0.5,
        tolerance_kind="pixels",
        tolerance=3.0,
    )
    assert result["crop_as_weed_false_fire"]["actions"] == 1
    assert result["crop_as_weed_false_fire"]["rate_per_action"] == 1.0


def test_action_score_requires_box_and_keypoint_confidence() -> None:
    weak_keypoint = prediction((10.0, 10.0), confidence=0.95, keypoint_confidence=0.2)
    result = evaluate_actions([sample((weak_keypoint,))], 0.5)
    assert result["actions"] == 0
    assert result["false_negative"] == 2


def test_detection_uses_iou_not_keypoint() -> None:
    result = evaluate_detection([sample((prediction((90.0, 90.0), keypoint_confidence=0.0),))], 0.5)
    assert result["true_positive"] == 1
    assert result["false_negative"] == 1


def test_crop_footprint_circle_rectangle_intersection() -> None:
    box = (10.0, 10.0, 20.0, 20.0)
    assert point_footprint_hits_box((5.0, 15.0), box, 5.0)
    assert not point_footprint_hits_box((4.9, 15.0), box, 5.0)


def test_threshold_choice_reports_failed_safety_gate() -> None:
    curve = [
        {
            "confidence_threshold": 0.2,
            "f1": 0.8,
            "recall": 0.9,
            "crop_box_collision": {"0": {"rate_per_action": 0.02}},
            "crop_as_weed_false_fire": {"rate_per_action": 0.02},
        },
        {
            "confidence_threshold": 0.8,
            "f1": 0.4,
            "recall": 0.3,
            "crop_box_collision": {"0": {"rate_per_action": 0.01}},
            "crop_as_weed_false_fire": {"rate_per_action": 0.01},
        },
    ]
    selected = choose_threshold(curve, maximum_crop_false_fire_rate=0.005)
    assert selected["crop_false_fire_gate_passed"] is False
    assert selected["threshold"] == 0.8


def test_output_name_must_be_one_path_component(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe path component"):
        run(tmp_path / "missing.yaml", output_name="../escape")


def test_box_center_control_ignores_keypoint_prediction() -> None:
    original = sample((prediction((99.0, 99.0), keypoint_confidence=0.1),))
    converted = with_box_center_actions([original])[0]
    assert converted.predictions[0].point == (10.0, 10.0)
    assert converted.predictions[0].keypoint_confidence == pytest.approx(0.9)


def test_action_point_deduplication_keeps_highest_score() -> None:
    low = prediction((10.0, 10.0), confidence=0.7, keypoint_confidence=0.7)
    high = prediction((11.0, 10.0), confidence=0.9, keypoint_confidence=0.9)
    far = prediction((50.0, 50.0), confidence=0.8, keypoint_confidence=0.8)
    converted = deduplicate_action_points([sample((low, high, far))], 0.10)[0]
    weed = [item for item in converted.predictions if item.class_id == 0]
    assert len(weed) == 2
    assert high in weed
    assert low not in weed
    assert far in weed
