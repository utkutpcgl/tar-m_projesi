"""Pixel, domain, safety, and threshold-calibration metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Iterable, Sequence

import torch

from .constants import CLASS_NAMES, CROP, IGNORE, NUM_CLASSES, WEED
from .safety import SafetyPolicy, apply_safety_policy


def confusion_matrix(
    prediction: torch.Tensor, target: torch.Tensor
) -> torch.Tensor:
    prediction = prediction.detach().to(torch.int64).reshape(-1)
    target = target.detach().to(torch.int64).reshape(-1)
    valid = (target != IGNORE) & (target >= 0) & (target < NUM_CLASSES)
    encoded = target[valid] * NUM_CLASSES + prediction[valid]
    return torch.bincount(
        encoded.cpu(), minlength=NUM_CLASSES * NUM_CLASSES
    ).reshape(NUM_CLASSES, NUM_CLASSES)


def metrics_from_confusion(matrix: torch.Tensor) -> dict[str, object]:
    values = matrix.double()
    true_positive = values.diag()
    ground_truth = values.sum(dim=1)
    predicted = values.sum(dim=0)
    union = ground_truth + predicted - true_positive
    iou = torch.where(union > 0, true_positive / union, torch.nan)
    recall = torch.where(ground_truth > 0, true_positive / ground_truth, torch.nan)
    precision = torch.where(predicted > 0, true_positive / predicted, torch.nan)
    return {
        "confusion_matrix": matrix.tolist(),
        "iou": {name: float(iou[i]) for i, name in enumerate(CLASS_NAMES)},
        "recall": {
            name: float(recall[i]) for i, name in enumerate(CLASS_NAMES)
        },
        "precision": {
            name: float(precision[i]) for i, name in enumerate(CLASS_NAMES)
        },
        "mean_iou": float(torch.nanmean(iou)),
    }


@dataclass
class SafetyCounts:
    crop_pixels: int = 0
    weed_pixels: int = 0
    vegetation_pixels: int = 0
    valid_pixels: int = 0
    crop_as_raw_weed: int = 0
    weed_as_raw_weed: int = 0
    crop_as_safe_weed: int = 0
    weed_as_safe_weed: int = 0
    safe_weed_pixels: int = 0
    unknown_pixels: int = 0
    unknown_vegetation_pixels: int = 0

    def update(
        self,
        probabilities: torch.Tensor,
        target: torch.Tensor,
        policy: SafetyPolicy,
    ) -> None:
        decisions = apply_safety_policy(probabilities, policy)
        self.update_decisions(target, decisions)

    def update_decisions(
        self, target: torch.Tensor, decisions: dict[str, torch.Tensor]
    ) -> None:
        valid = target != IGNORE
        crop = target == CROP
        weed = target == WEED
        raw_weed = decisions["weed_candidate"] & ~decisions["unknown"]
        safe = decisions["safe_weed"]
        unknown = decisions["unknown"]
        self.crop_pixels += int(crop.sum())
        self.weed_pixels += int(weed.sum())
        self.vegetation_pixels += int((crop | weed).sum())
        self.valid_pixels += int(valid.sum())
        self.crop_as_raw_weed += int((raw_weed & crop).sum())
        self.weed_as_raw_weed += int((raw_weed & weed).sum())
        self.crop_as_safe_weed += int((safe & crop).sum())
        self.weed_as_safe_weed += int((safe & weed).sum())
        self.safe_weed_pixels += int((safe & valid).sum())
        self.unknown_pixels += int((unknown & valid).sum())
        self.unknown_vegetation_pixels += int(
            (unknown & (crop | weed)).sum()
        )

    def compute(self) -> dict[str, float | int]:
        return {
            **asdict(self),
            "crop_as_weed_rate_raw": self.crop_as_raw_weed
            / max(1, self.crop_pixels),
            "weed_recall_raw": self.weed_as_raw_weed / max(1, self.weed_pixels),
            "crop_spray_risk": self.crop_as_safe_weed / max(1, self.crop_pixels),
            "safe_weed_recall": self.weed_as_safe_weed
            / max(1, self.weed_pixels),
            "safe_weed_precision": self.weed_as_safe_weed
            / max(1, self.safe_weed_pixels),
            "unknown_rate": self.unknown_pixels / max(1, self.valid_pixels),
            "unknown_vegetation_rate": self.unknown_vegetation_pixels
            / max(1, self.vegetation_pixels),
        }


@dataclass(frozen=True)
class ThresholdPoint:
    weed_threshold: float
    crop_as_weed_rate_raw: float
    crop_spray_risk: float
    safe_weed_recall: float
    unknown_rate: float


def sweep_weed_threshold(
    batches: Iterable[tuple[torch.Tensor, torch.Tensor]],
    base_policy: SafetyPolicy,
    thresholds: Sequence[float],
) -> list[ThresholdPoint]:
    materialized = [
        (probabilities.detach().cpu(), target.detach().cpu())
        for probabilities, target in batches
    ]
    curve: list[ThresholdPoint] = []
    for threshold in thresholds:
        counts = SafetyCounts()
        policy = replace(base_policy, weed_threshold=float(threshold))
        for probabilities, target in materialized:
            counts.update(probabilities, target, policy)
        result = counts.compute()
        curve.append(
            ThresholdPoint(
                weed_threshold=float(threshold),
                crop_as_weed_rate_raw=float(result["crop_as_weed_rate_raw"]),
                crop_spray_risk=float(result["crop_spray_risk"]),
                safe_weed_recall=float(result["safe_weed_recall"]),
                unknown_rate=float(result["unknown_rate"]),
            )
        )
    return curve


def select_operating_point(
    curve: Sequence[ThresholdPoint], max_crop_spray_risk: float
) -> ThresholdPoint:
    feasible = [
        point
        for point in curve
        if point.crop_spray_risk <= max_crop_spray_risk
    ]
    if not feasible:
        return min(curve, key=lambda point: point.crop_spray_risk)
    return max(
        feasible,
        key=lambda point: (
            point.safe_weed_recall,
            -point.unknown_rate,
            point.weed_threshold,
        ),
    )
