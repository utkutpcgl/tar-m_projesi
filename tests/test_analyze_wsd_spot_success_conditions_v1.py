from pathlib import Path

import pytest

from scripts.analyze_wsd_spot_success_conditions_v1 import (
    _choose_balanced_or_zero_action_fallback,
    apparent_box_size,
    evaluate_gt_size_conditioned_spot,
)
from scripts.evaluate_wsd_action_poc_v1 import Instance, Prediction, Sample


def test_apparent_box_size_scales_to_model_input() -> None:
    assert apparent_box_size(
        (0, 0, 40, 10),
        image_width=200,
        image_height=200,
        inference_image_size=100,
    ) == pytest.approx(10.0)


def test_balanced_selection_retains_all_missed_positive_regime() -> None:
    curve = [
        {
            "confidence_threshold": 0.1,
            "precision": None,
            "recall": 0.0,
            "f1": None,
        },
        {
            "confidence_threshold": 0.2,
            "precision": None,
            "recall": 0.0,
            "f1": None,
        },
    ]
    selected = _choose_balanced_or_zero_action_fallback(curve)
    assert selected["threshold"] == pytest.approx(0.1)
    assert selected["selection_status"] == "no_defined_f1_all_actions_missed"
    assert selected["effective_f1_for_interpretation"] == 0.0


def test_gt_size_condition_ignores_hits_on_smaller_weeds() -> None:
    sample = Sample(
        image_path=Path("frame.bmp"),
        width=100,
        height=100,
        ground_truth=(
            Instance(0, (0, 0, 10, 10), (5, 5)),
            Instance(0, (20, 20, 60, 60), (40, 40)),
            Instance(1, (70, 70, 90, 90), None),
        ),
        predictions=(
            Prediction(0, 0.9, (0, 0, 10, 10), (5, 5), 0.9),
            Prediction(0, 0.9, (20, 20, 60, 60), (40, 40), 0.9),
            Prediction(0, 0.9, (90, 0, 99, 9), (95, 5), 0.9),
        ),
    )
    metric = evaluate_gt_size_conditioned_spot(
        [sample], 0.5, minimum_gt_size_px=20, inference_image_size=100
    )
    assert metric["true_positive"] == 1
    assert metric["false_positive"] == 1
    assert metric["false_negative"] == 0
    assert metric["ignored_actions_hitting_smaller_weeds"] == 1
    assert metric["f1"] == pytest.approx(2 / 3)
