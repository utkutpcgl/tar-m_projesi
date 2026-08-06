from __future__ import annotations

import numpy as np
import torch

from scripts.evaluate_crop_row_prior_v1 import (
    adjust_crop_weed_probabilities,
    fit_parallel_rows,
    row_probability,
)


def _striped_seed() -> tuple[np.ndarray, np.ndarray]:
    score = np.zeros((256, 320), dtype=np.float32)
    mask = np.zeros_like(score, dtype=bool)
    for column in (55, 155, 255):
        mask[15:245, column - 3 : column + 4] = True
        score[mask] = 0.9
    return score, mask


def test_row_fit_recovers_vertical_parallel_rows() -> None:
    score, mask = _striped_seed()
    fit = fit_parallel_rows(score, mask, angle_step_deg=3)
    assert fit is not None
    assert min(abs(fit.angle_deg - 90.0), abs(fit.angle_deg - 0.0)) < 5.0
    assert len(fit.peaks) == 3
    assert fit.seed_coverage_within_1p5_corridors > 0.95
    prior = row_probability(mask.shape, fit)
    assert prior[:, 55].mean() > prior[:, 105].mean()


def test_row_prior_preserves_background_and_vegetation_mass() -> None:
    probabilities = torch.tensor(
        [[[[0.8, 0.1]], [[0.1, 0.6]], [[0.1, 0.3]]]], dtype=torch.float32
    )
    row = torch.tensor([[0.9, 0.1]], dtype=torch.float32)
    adjusted = adjust_crop_weed_probabilities(probabilities, row, 0.65)
    assert torch.allclose(adjusted[:, 0], probabilities[:, 0])
    assert torch.allclose(adjusted[:, 1:].sum(dim=1), probabilities[:, 1:].sum(dim=1))
    assert torch.allclose(adjusted.sum(dim=1), torch.ones((1, 1, 2)))


def test_row_fit_falls_back_when_seed_is_insufficient() -> None:
    score = np.zeros((64, 64), dtype=np.float32)
    mask = np.zeros_like(score, dtype=bool)
    mask[2:4, 2:4] = True
    assert fit_parallel_rows(score, mask) is None
