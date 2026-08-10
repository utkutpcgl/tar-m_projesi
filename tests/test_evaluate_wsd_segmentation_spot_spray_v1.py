import numpy as np
import pytest

from scripts.evaluate_wsd_action_poc_v1 import Instance
from scripts.evaluate_wsd_segmentation_spot_spray_v1 import (
    GeneratorConfig,
    _distance_peaks,
    _component_features,
    crop_id_for_sample,
    predictions_from_probabilities,
)


def probabilities_with_weed(mask: np.ndarray, confidence: float = 0.8) -> np.ndarray:
    probabilities = np.full((3, *mask.shape), 0.1, dtype=np.float32)
    probabilities[0] = 0.8
    probabilities[0, mask] = 0.1
    probabilities[2, mask] = confidence
    return probabilities


def test_component_action_uses_deepest_interior_and_scales_to_original() -> None:
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:6, 2:6] = True
    predictions = predictions_from_probabilities(
        probabilities_with_weed(mask),
        GeneratorConfig("component", 4, "mean"),
        original_width=16,
        original_height=16,
    )
    assert len(predictions) == 1
    assert predictions[0].box == pytest.approx((4.0, 4.0, 12.0, 12.0))
    assert 4.0 < predictions[0].point[0] < 12.0
    assert 4.0 < predictions[0].point[1] < 12.0
    assert predictions[0].confidence == pytest.approx(0.8)


def test_minimum_area_filters_small_semantic_noise() -> None:
    mask = np.zeros((8, 8), dtype=bool)
    mask[1, 1] = True
    predictions = predictions_from_probabilities(
        probabilities_with_weed(mask),
        GeneratorConfig("component", 4, "max"),
        original_width=8,
        original_height=8,
    )
    assert predictions == ()


def test_distance_peaks_split_two_lobes_in_one_component() -> None:
    mask = np.zeros((15, 25), dtype=bool)
    mask[3:12, 2:10] = True
    mask[3:12, 15:23] = True
    mask[7, 9:16] = True
    feature = _component_features(probabilities_with_weed(mask))[0]
    peaks = _distance_peaks(feature, 5)
    assert len(peaks) == 2


def test_crop_id_routing_uses_known_field_crop_and_explicit_fallback() -> None:
    maize = [Instance(0, (0, 0, 1, 1), (0.5, 0.5)), Instance(1, (1, 1, 2, 2), None)]
    assert crop_id_for_sample(maize, {1: 3, 2: 8}, 99) == (3, "wsd_class_1")
    assert crop_id_for_sample([], {1: 3, 2: 8}, 99) == (
        99,
        "session_fallback_no_visible_crop_box",
    )


def test_crop_id_routing_rejects_mixed_crop_frame() -> None:
    mixed = [Instance(1, (0, 0, 1, 1), None), Instance(2, (1, 1, 2, 2), None)]
    with pytest.raises(ValueError, match="mixes crop classes"):
        crop_id_for_sample(mixed, {1: 3, 2: 8}, 99)
