"""Conservative no-spray and safe-weed decision logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import torch
from torch.nn import functional as F

from .constants import CROP, WEED


@dataclass(frozen=True)
class SafetyPolicy:
    weed_threshold: float = 0.70
    # Source-validation-calibrated operating points for crop IDs seen during
    # training. Crops absent from this mapping use the conservative unknown
    # fallback. The scalar remains the legacy/default operating point.
    weed_threshold_by_crop_id: Mapping[int, float] = field(
        default_factory=dict
    )
    unknown_crop_weed_threshold: float | None = None
    crop_threshold: float = 0.40
    min_confidence: float = 0.55
    min_margin: float = 0.15
    max_entropy: float = 0.85
    crop_dilation_px: int = 5

    def validate(self) -> None:
        for name in (
            "weed_threshold",
            "crop_threshold",
            "min_confidence",
            "min_margin",
            "max_entropy",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        if self.unknown_crop_weed_threshold is not None and not (
            0.0 <= self.unknown_crop_weed_threshold <= 1.0
        ):
            raise ValueError(
                "unknown_crop_weed_threshold must be in [0, 1], got "
                f"{self.unknown_crop_weed_threshold}"
            )
        for crop_id, threshold in self.weed_threshold_by_crop_id.items():
            if int(crop_id) < 0:
                raise ValueError(f"crop ID must be non-negative, got {crop_id}")
            if not 0.0 <= float(threshold) <= 1.0:
                raise ValueError(
                    "crop-specific weed threshold must be in [0, 1], got "
                    f"{threshold} for crop ID {crop_id}"
                )
        if self.crop_dilation_px < 0:
            raise ValueError("crop_dilation_px cannot be negative")


def normalized_entropy(probabilities: torch.Tensor) -> torch.Tensor:
    working = probabilities.float()
    classes = working.shape[1]
    safe = working.clamp_min(torch.finfo(torch.float32).tiny)
    entropy = -(safe.log() * working).sum(dim=1)
    return entropy / torch.log(
        torch.tensor(float(classes), device=probabilities.device)
    )


def dilate(binary_mask: torch.Tensor, radius: int) -> torch.Tensor:
    if radius <= 0:
        return binary_mask.bool()
    kernel = 2 * radius + 1
    # A square structuring element is separable. Two 1-D pools are exactly
    # equivalent to a k×k pool and are much cheaper on native 20 MP UAV frames.
    values = F.max_pool2d(
        binary_mask.float().unsqueeze(1),
        kernel_size=(1, kernel),
        stride=1,
        padding=(0, radius),
    )
    values = F.max_pool2d(
        values,
        kernel_size=(kernel, 1),
        stride=1,
        padding=(radius, 0),
    )
    return values[:, 0] > 0


def apply_safety_policy(
    probabilities: torch.Tensor,
    policy: SafetyPolicy,
    target_crop_id: torch.Tensor | None = None,
) -> dict[str, torch.Tensor]:
    policy.validate()
    if probabilities.ndim != 4 or probabilities.shape[1] != 3:
        raise ValueError("Expected probabilities shaped [B, 3, H, W]")
    working = probabilities.float()
    if not torch.isfinite(working).all():
        raise ValueError("Safety probabilities contain non-finite values")
    top2 = working.topk(k=2, dim=1).values
    confidence = top2[:, 0]
    margin = top2[:, 0] - top2[:, 1]
    entropy = normalized_entropy(working)
    uncertain = (
        (confidence < policy.min_confidence)
        | (margin < policy.min_margin)
        | (entropy > policy.max_entropy)
    )

    crop_candidate = working[:, CROP] >= policy.crop_threshold
    crop_guard = dilate(crop_candidate, policy.crop_dilation_px)
    fallback = (
        policy.unknown_crop_weed_threshold
        if policy.unknown_crop_weed_threshold is not None
        else policy.weed_threshold
    )
    if target_crop_id is None or not policy.weed_threshold_by_crop_id:
        weed_threshold = torch.full(
            (working.shape[0], 1, 1),
            float(policy.weed_threshold),
            dtype=working.dtype,
            device=working.device,
        )
    else:
        crop_ids = target_crop_id.detach().reshape(-1)
        if crop_ids.numel() != working.shape[0]:
            raise ValueError(
                "target_crop_id must contain one value per probability batch item"
            )
        configured = {
            int(crop_id): float(threshold)
            for crop_id, threshold in policy.weed_threshold_by_crop_id.items()
        }
        weed_threshold = torch.tensor(
            [configured.get(int(crop_id), float(fallback)) for crop_id in crop_ids],
            dtype=working.dtype,
            device=working.device,
        )[:, None, None]
    weed_candidate = (
        (working[:, WEED] >= weed_threshold)
        & (working[:, WEED] > working[:, CROP])
    )
    safe_weed = weed_candidate & ~crop_guard & ~uncertain
    return {
        "weed_candidate": weed_candidate,
        "safe_weed": safe_weed,
        "crop_guard": crop_guard,
        "unknown": uncertain,
        "confidence": confidence,
        "margin": margin,
        "entropy": entropy,
    }
