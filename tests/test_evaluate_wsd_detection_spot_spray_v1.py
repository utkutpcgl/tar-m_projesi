from pathlib import Path

import pytest

from scripts.evaluate_wsd_action_poc_v1 import Instance, Prediction, Sample
from scripts.evaluate_wsd_detection_spot_spray_v1 import (
    apparent_weed_box_sizes,
    choose_recall_target,
    evaluate_weed_box_proxy,
    weed_box_proxy_recall_by_apparent_size,
)


def _prediction(point: tuple[float, float], confidence: float = 0.9) -> Prediction:
    return Prediction(
        class_id=0,
        confidence=confidence,
        box=(point[0] - 2, point[1] - 2, point[0] + 2, point[1] + 2),
        point=point,
        keypoint_confidence=confidence,
    )


def _sample(predictions: tuple[Prediction, ...]) -> Sample:
    return Sample(
        image_path=Path("frame.bmp"),
        width=100,
        height=100,
        ground_truth=(
            Instance(0, (10, 10, 30, 30), (18, 18)),
            Instance(0, (50, 50, 70, 70), (60, 60)),
            Instance(1, (75, 75, 95, 95), None),
        ),
        predictions=predictions,
    )


def test_box_proxy_is_one_to_one_and_marks_crop_rectangle_collision() -> None:
    result = evaluate_weed_box_proxy(
        [_sample((_prediction((20, 20)), _prediction((21, 20)), _prediction((80, 80))))],
        0.5,
    )
    assert result["true_positive"] == 1
    assert result["false_positive"] == 2
    assert result["false_negative"] == 1
    assert result["crop_box_collision"]["actions"] == 1
    assert result["precision"] == pytest.approx(1 / 3)


def test_box_proxy_footprint_can_reach_nearby_box() -> None:
    miss = evaluate_weed_box_proxy([_sample((_prediction((5, 20)),))], 0.5)
    hit = evaluate_weed_box_proxy(
        [_sample((_prediction((5, 20)),))], 0.5, footprint_radius_px=5
    )
    assert miss["true_positive"] == 0
    assert hit["true_positive"] == 1


def test_recall_target_reports_when_validation_cannot_reach_target() -> None:
    curve = [
        {"confidence_threshold": 0.1, "precision": 0.4, "recall": 0.9, "f1": 0.55},
        {"confidence_threshold": 0.5, "precision": 0.8, "recall": 0.7, "f1": 0.75},
    ]
    selected = choose_recall_target(curve, 0.95)
    assert selected["target_reached_on_validation"] is False
    assert selected["threshold"] == 0.1


def test_apparent_size_uses_model_input_scale() -> None:
    result = apparent_weed_box_sizes([_sample(())], 50)
    assert result["count"] == 2
    assert result["distribution_px"]["p50"] == pytest.approx(10.0)
    assert result["bins"]["lt14"]["count"] == 2


def test_box_proxy_recall_is_split_by_apparent_size() -> None:
    result = weed_box_proxy_recall_by_apparent_size(
        [_sample((_prediction((20, 20)),))],
        0.5,
        inference_image_size=50,
    )
    assert result["bins"]["lt14"]["ground_truth"] == 2
    assert result["bins"]["lt14"]["hits"] == 1
    assert result["bins"]["lt14"]["recall"] == pytest.approx(0.5)
