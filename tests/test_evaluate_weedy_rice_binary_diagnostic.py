import numpy as np
import pytest
import torch

from scripts.evaluate_weedy_rice_binary_diagnostic import (
    coverage_bin,
    empty_counts,
    metrics_from_counts,
    ranking_metrics,
    update_counts,
)


def test_binary_counts_and_metrics() -> None:
    prediction = torch.tensor([[True, True, False, False]])
    target = torch.tensor([[True, False, True, False]])
    counts = empty_counts()

    update_counts(counts, prediction, target)
    metrics = metrics_from_counts(counts)

    assert counts == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert metrics["iou"] == pytest.approx(1 / 3)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["specificity"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.0001, "gt_0_le_5"),
        (0.05, "gt_0_le_5"),
        (0.05001, "gt_5_le_10"),
        (0.10, "gt_5_le_10"),
        (0.20, "gt_10_le_20"),
        (0.30, "gt_20_le_30"),
        (0.40, "gt_30_le_40"),
        (0.60, "gt_40_le_60"),
        (0.75, "gt_60_le_75"),
        (0.899, "gt_75_lt_90"),
    ],
)
def test_coverage_bin_boundaries(fraction: float, expected: str) -> None:
    assert coverage_bin(fraction) == expected


def test_coverage_bin_rejects_forbidden_high_coverage() -> None:
    with pytest.raises(ValueError, match="Forbidden"):
        coverage_bin(0.91)


def test_ranking_metrics_perfect_ordering() -> None:
    positive = np.array([0, 0, 0, 4], dtype=np.int64)
    negative = np.array([4, 0, 0, 0], dtype=np.int64)

    metrics = ranking_metrics(positive, negative)

    assert metrics["approx_average_precision"] == pytest.approx(1.0)
    assert metrics["approx_auroc"] == pytest.approx(1.0)
    assert metrics["positive_pixels"] == 4
    assert metrics["negative_pixels"] == 4


def test_ranking_metrics_reversed_ordering() -> None:
    positive = np.array([4, 0, 0, 0], dtype=np.int64)
    negative = np.array([0, 0, 0, 4], dtype=np.int64)

    metrics = ranking_metrics(positive, negative)

    assert metrics["approx_auroc"] == pytest.approx(0.0)


def test_ranking_metrics_requires_both_classes() -> None:
    with pytest.raises(ValueError, match="both classes"):
        ranking_metrics(
            np.array([0, 1], dtype=np.int64),
            np.array([0, 0], dtype=np.int64),
        )
