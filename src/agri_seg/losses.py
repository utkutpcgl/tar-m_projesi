"""Losses that prioritize crop safety without ignoring weed recall."""

from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F

from .constants import CROP, IGNORE, NUM_CLASSES, WEED


def soft_dice_loss(
    probabilities: torch.Tensor, target: torch.Tensor, ignore_index: int = IGNORE
) -> torch.Tensor:
    valid = target != ignore_index
    safe_target = target.masked_fill(~valid, 0)
    one_hot = F.one_hot(safe_target, NUM_CLASSES).permute(0, 3, 1, 2).float()
    valid_float = valid.unsqueeze(1).float()
    probabilities = probabilities * valid_float
    one_hot = one_hot * valid_float
    losses: list[torch.Tensor] = []
    for class_id in (CROP, WEED):
        intersection = (probabilities[:, class_id] * one_hot[:, class_id]).sum()
        denominator = (
            probabilities[:, class_id].sum() + one_hot[:, class_id].sum()
        )
        losses.append(1.0 - (2.0 * intersection + 1.0) / (denominator + 1.0))
    return torch.stack(losses).mean()


class SafetyAwareLoss(nn.Module):
    def __init__(
        self,
        class_weights: tuple[float, float, float] = (0.25, 1.5, 1.0),
        dice_weight: float = 0.5,
        crop_safety_weight: float = 1.0,
        crop_safety_tail_fraction: float = 1.0,
    ) -> None:
        super().__init__()
        if not 0.0 < crop_safety_tail_fraction <= 1.0:
            raise ValueError("crop_safety_tail_fraction must be in (0, 1]")
        self.register_buffer("class_weights", torch.tensor(class_weights))
        self.dice_weight = dice_weight
        self.crop_safety_weight = crop_safety_weight
        self.crop_safety_tail_fraction = crop_safety_tail_fraction

    def forward(
        self, logits: torch.Tensor, target: torch.Tensor
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # The CUDA NCHW nll_loss2d kernel has no strict deterministic
        # implementation. Flattening pixels selects the mathematically
        # equivalent 2D cross-entropy kernel, which supports deterministic
        # forward/backward on the target deployment stack.
        flat_logits = logits.permute(0, 2, 3, 1).reshape(
            -1, logits.shape[1]
        )
        ce = F.cross_entropy(
            flat_logits,
            target.reshape(-1),
            weight=self.class_weights,
            ignore_index=IGNORE,
        )
        probabilities = logits.float().softmax(dim=1)
        dice = soft_dice_loss(probabilities, target)
        crop_pixels = target == CROP
        if crop_pixels.any():
            crop_as_weed_mean = probabilities[:, WEED][crop_pixels].mean()
            per_image_tail: list[torch.Tensor] = []
            for batch_index in range(target.shape[0]):
                values = probabilities[batch_index, WEED][
                    crop_pixels[batch_index]
                ]
                if values.numel():
                    count = max(
                        1,
                        math.ceil(
                            values.numel() * self.crop_safety_tail_fraction
                        ),
                    )
                    per_image_tail.append(values.topk(count).values.mean())
            crop_as_weed_tail = torch.stack(per_image_tail).mean()
        else:
            crop_as_weed_mean = probabilities.sum() * 0.0
            crop_as_weed_tail = crop_as_weed_mean
        total = (
            ce
            + self.dice_weight * dice
            + self.crop_safety_weight * crop_as_weed_tail
        )
        return total, {
            "loss": total.detach(),
            "cross_entropy": ce.detach(),
            "dice": dice.detach(),
            "crop_as_weed_soft": crop_as_weed_mean.detach(),
            "crop_as_weed_tail": crop_as_weed_tail.detach(),
        }
