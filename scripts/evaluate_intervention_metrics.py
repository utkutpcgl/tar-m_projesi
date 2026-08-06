#!/usr/bin/env python3
"""Evaluate segmentation checkpoints with intervention-oriented proxy metrics.

The available datasets contain semantic crop/weed masks rather than plant
instances, roots, stems, or apical-meristem keypoints.  Connected components
are therefore reported explicitly as *semantic component proxies*.  These
metrics are useful for model comparison, but they are not a substitute for a
calibrated actuator test in millimetres.

This script intentionally lives outside ``src/agri_seg``.  Adding a reporting
utility must not change the source-tree hash embedded in accepted checkpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
import yaml
from scipy import ndimage
from torch.nn import functional as torch_functional
from torch.utils.data import DataLoader

from agri_seg.constants import BACKGROUND, CLASS_NAMES, CROP, IGNORE, WEED
from agri_seg.data import EvalTransform, ManifestDataset, padded_collate
from agri_seg.engine import load_checkpoint, predict_logits
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    read_manifest,
)
from agri_seg.safety import SafetyPolicy, apply_safety_policy


PATCH_SIZE_PX = 14.0
COVERAGE_THRESHOLDS = (0.10, 0.50, 0.90)
CENTER_PIXEL_THRESHOLDS = (5.0, 10.0, 20.0)
CENTER_RADIUS_THRESHOLDS = (0.5, 1.0)
FOOTPRINT_RADII_PX = (0, 5, 10, 20)
DIAMETER_BINS: tuple[tuple[str, float, float], ...] = (
    ("sub_patch_lt14px", 0.0, 14.0),
    ("one_to_two_patches_14_28px", 14.0, 28.0),
    ("two_to_four_patches_28_56px", 28.0, 56.0),
    ("four_plus_patches_ge56px", 56.0, math.inf),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p90": None, "p95": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "p50": float(np.quantile(array, 0.50)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _component_geometry(
    mask: np.ndarray,
) -> tuple[np.ndarray, int, np.ndarray, np.ndarray, np.ndarray]:
    labels, count = ndimage.label(
        mask.astype(bool, copy=False),
        structure=np.ones((3, 3), dtype=np.uint8),
    )
    count = int(count)
    if count == 0:
        return (
            labels,
            0,
            np.empty(0, dtype=np.int64),
            np.empty((0, 2), dtype=np.float64),
            np.empty(0, dtype=np.float64),
        )
    # center_of_mass materializes full-resolution float coordinate grids.  On
    # 6000x4000 field frames that dominates runtime and memory even when plant
    # pixels are sparse.  Accumulate only foreground coordinates; this is the
    # same area-weighted centroid for a binary semantic component.
    rows, columns = np.nonzero(mask)
    component_labels = labels[rows, columns]
    areas = np.bincount(
        component_labels, minlength=count + 1
    )[1:].astype(np.int64, copy=False)
    row_sums = np.bincount(
        component_labels,
        weights=rows,
        minlength=count + 1,
    )[1:]
    column_sums = np.bincount(
        component_labels,
        weights=columns,
        minlength=count + 1,
    )[1:]
    centers = np.column_stack(
        (row_sums / areas, column_sums / areas)
    ).astype(np.float64, copy=False)
    equivalent_diameters = 2.0 * np.sqrt(areas.astype(np.float64) / math.pi)
    return labels, count, areas, centers, equivalent_diameters


def _deepest_interior_points(
    mask: np.ndarray, labels: np.ndarray, count: int
) -> np.ndarray:
    """Return one valid mask point per predicted connected component."""
    if count == 0:
        return np.empty((0, 2), dtype=np.int64)
    distance = ndimage.distance_transform_edt(mask)
    positions = ndimage.maximum_position(
        distance,
        labels=labels,
        index=np.arange(1, count + 1),
    )
    return np.asarray(positions, dtype=np.int64).reshape(count, 2)


def _best_overlap_center_errors(
    gt_labels: np.ndarray,
    gt_count: int,
    gt_centers: np.ndarray,
    gt_areas: np.ndarray,
    predicted_labels: np.ndarray,
    predicted_count: int,
    predicted_centers: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Match each GT proxy to its greatest-overlap prediction (recall view).

    This is deliberately not called instance AP: semantic masks may merge
    touching plants or split disconnected leaves, and matching is not one-to-one.
    """
    errors_px = np.full(gt_count, np.nan, dtype=np.float64)
    errors_radius = np.full(gt_count, np.nan, dtype=np.float64)
    if gt_count == 0 or predicted_count == 0:
        return errors_px, errors_radius
    selection = (gt_labels > 0) & (predicted_labels > 0)
    if not np.any(selection):
        return errors_px, errors_radius
    gt_values = gt_labels[selection].astype(np.int64, copy=False)
    predicted_values = predicted_labels[selection].astype(np.int64, copy=False)
    encoded = gt_values * (predicted_count + 1) + predicted_values
    pairs, intersections = np.unique(encoded, return_counts=True)
    pair_gt = pairs // (predicted_count + 1)
    pair_predicted = pairs % (predicted_count + 1)
    best_label = np.zeros(gt_count + 1, dtype=np.int64)
    # Select maximum overlap per GT entirely in NumPy.  The previous Python
    # loop became pathological on 24 MP masks with many overlap pairs.
    # np.unique returns labels in ascending order, so ties previously kept the
    # smallest predicted label; lexsort preserves that exact rule.
    order = np.lexsort((pair_predicted, -intersections, pair_gt))
    ordered_gt = pair_gt[order]
    first_for_gt = np.empty(ordered_gt.shape, dtype=bool)
    first_for_gt[0] = True
    first_for_gt[1:] = ordered_gt[1:] != ordered_gt[:-1]
    chosen = order[first_for_gt]
    best_label[pair_gt[chosen]] = pair_predicted[chosen]
    matched = best_label[1:] > 0
    if not np.any(matched):
        return errors_px, errors_radius
    predicted = predicted_centers[best_label[1:][matched] - 1]
    errors = np.linalg.norm(predicted - gt_centers[matched], axis=1)
    equivalent_radii = np.sqrt(gt_areas[matched].astype(np.float64) / math.pi)
    errors_px[matched] = errors
    errors_radius[matched] = errors / np.maximum(equivalent_radii, 1.0)
    return errors_px, errors_radius


def _bin_selections(diameters: np.ndarray) -> dict[str, np.ndarray]:
    selections = {"all": np.ones(diameters.shape, dtype=bool)}
    for name, lower, upper in DIAMETER_BINS:
        selections[name] = (diameters >= lower) & (diameters < upper)
    return selections


@dataclass
class ComponentCounts:
    components: int = 0
    gt_pixels: int = 0
    covered_pixels: int = 0
    hit_any: int = 0
    coverage_hits: dict[float, int] = field(
        default_factory=lambda: {value: 0 for value in COVERAGE_THRESHOLDS}
    )
    matched_centers: int = 0
    center_px_hits: dict[float, int] = field(
        default_factory=lambda: {value: 0 for value in CENTER_PIXEL_THRESHOLDS}
    )
    center_radius_hits: dict[float, int] = field(
        default_factory=lambda: {value: 0 for value in CENTER_RADIUS_THRESHOLDS}
    )
    center_errors_px: list[float] = field(default_factory=list)
    center_errors_radius: list[float] = field(default_factory=list)

    def update(
        self,
        areas: np.ndarray,
        hits: np.ndarray,
        center_errors_px: np.ndarray,
        center_errors_radius: np.ndarray,
    ) -> None:
        if not areas.size:
            return
        coverages = hits.astype(np.float64) / areas
        matched = np.isfinite(center_errors_px)
        self.components += int(areas.size)
        self.gt_pixels += int(areas.sum())
        self.covered_pixels += int(hits.sum())
        self.hit_any += int(np.count_nonzero(hits > 0))
        for threshold in COVERAGE_THRESHOLDS:
            self.coverage_hits[threshold] += int(
                np.count_nonzero(coverages >= threshold)
            )
        self.matched_centers += int(np.count_nonzero(matched))
        for threshold in CENTER_PIXEL_THRESHOLDS:
            self.center_px_hits[threshold] += int(
                np.count_nonzero(matched & (center_errors_px <= threshold))
            )
        for threshold in CENTER_RADIUS_THRESHOLDS:
            self.center_radius_hits[threshold] += int(
                np.count_nonzero(
                    matched & (center_errors_radius <= threshold)
                )
            )
        self.center_errors_px.extend(center_errors_px[matched].tolist())
        self.center_errors_radius.extend(center_errors_radius[matched].tolist())

    def compute(self) -> dict[str, object]:
        return {
            "semantic_component_proxies": self.components,
            "gt_pixels": self.gt_pixels,
            "pixel_recall_within_components": _ratio(
                self.covered_pixels, self.gt_pixels
            ),
            "component_hit_recall_any_overlap": _ratio(
                self.hit_any, self.components
            ),
            "component_coverage_recall": {
                f"at_least_{int(threshold * 100)}pct": _ratio(
                    self.coverage_hits[threshold], self.components
                )
                for threshold in COVERAGE_THRESHOLDS
            },
            "center_proxy": {
                "definition": (
                    "centroid error of the greatest-overlap predicted semantic "
                    "component versus GT semantic-component centroid"
                ),
                "matched_components": self.matched_centers,
                "match_recall": _ratio(self.matched_centers, self.components),
                "recall_within_pixels": {
                    str(int(threshold)): _ratio(
                        self.center_px_hits[threshold], self.components
                    )
                    for threshold in CENTER_PIXEL_THRESHOLDS
                },
                "recall_within_equivalent_radius": {
                    str(threshold): _ratio(
                        self.center_radius_hits[threshold], self.components
                    )
                    for threshold in CENTER_RADIUS_THRESHOLDS
                },
                "matched_error_px": _distribution(self.center_errors_px),
                "matched_error_over_equivalent_radius": _distribution(
                    self.center_errors_radius
                ),
            },
        }

    def merge(self, other: "ComponentCounts") -> None:
        self.components += other.components
        self.gt_pixels += other.gt_pixels
        self.covered_pixels += other.covered_pixels
        self.hit_any += other.hit_any
        for threshold in COVERAGE_THRESHOLDS:
            self.coverage_hits[threshold] += other.coverage_hits[threshold]
        self.matched_centers += other.matched_centers
        for threshold in CENTER_PIXEL_THRESHOLDS:
            self.center_px_hits[threshold] += other.center_px_hits[threshold]
        for threshold in CENTER_RADIUS_THRESHOLDS:
            self.center_radius_hits[threshold] += other.center_radius_hits[
                threshold
            ]
        self.center_errors_px.extend(other.center_errors_px)
        self.center_errors_radius.extend(other.center_errors_radius)


@dataclass
class ActionCounts:
    total: int = 0
    valid: int = 0
    ignored: int = 0
    weed: int = 0
    crop: int = 0
    background: int = 0
    crop_footprint_hits: dict[int, int] = field(
        default_factory=lambda: {radius: 0 for radius in FOOTPRINT_RADII_PX}
    )
    image_actions: list[float] = field(default_factory=list)

    def update(
        self,
        target: np.ndarray,
        points: np.ndarray,
        crop_distance: np.ndarray | None,
    ) -> None:
        self.image_actions.append(float(len(points)))
        if not len(points):
            return
        values = target[points[:, 0], points[:, 1]]
        valid = values != IGNORE
        self.total += int(len(points))
        self.valid += int(np.count_nonzero(valid))
        self.ignored += int(np.count_nonzero(~valid))
        self.weed += int(np.count_nonzero(values == WEED))
        self.crop += int(np.count_nonzero(values == CROP))
        self.background += int(np.count_nonzero(values == BACKGROUND))
        if crop_distance is not None:
            distances = crop_distance[points[:, 0], points[:, 1]]
            for radius in FOOTPRINT_RADII_PX:
                self.crop_footprint_hits[radius] += int(
                    np.count_nonzero(valid & (distances <= radius))
                )

    def compute(self) -> dict[str, object]:
        return {
            "action_points": self.total,
            "valid_action_points": self.valid,
            "ignored_action_points": self.ignored,
            "point_precision_on_weed": _ratio(self.weed, self.valid),
            "point_crop_hit_rate": _ratio(self.crop, self.valid),
            "point_background_rate": _ratio(self.background, self.valid),
            "point_counts": {
                "weed": self.weed,
                "crop": self.crop,
                "background": self.background,
            },
            "crop_collision_rate_by_circular_footprint_radius_px": {
                str(radius): _ratio(
                    self.crop_footprint_hits[radius], self.valid
                )
                for radius in FOOTPRINT_RADII_PX
            },
            "actions_per_image": _distribution(self.image_actions),
        }

    def merge(self, other: "ActionCounts") -> None:
        self.total += other.total
        self.valid += other.valid
        self.ignored += other.ignored
        self.weed += other.weed
        self.crop += other.crop
        self.background += other.background
        for radius in FOOTPRINT_RADII_PX:
            self.crop_footprint_hits[radius] += other.crop_footprint_hits[
                radius
            ]
        self.image_actions.extend(other.image_actions)


class DatasetAccumulator:
    def __init__(self) -> None:
        bin_names = ("all",) + tuple(name for name, _, _ in DIAMETER_BINS)
        self.components = {
            mode: {name: ComponentCounts() for name in bin_names}
            for mode in ("semantic_argmax", "frozen_safe_action")
        }
        self.actions = {
            mode: ActionCounts()
            for mode in ("semantic_argmax", "frozen_safe_action")
        }
        self.images = 0
        self.image_megapixels: list[float] = []
        self.weed_diameters_px: list[float] = []
        self.confusion = np.zeros((3, 3), dtype=np.int64)
        self.crop_pixels = 0
        self.weed_pixels = 0
        self.safe_pixels = 0
        self.safe_on_crop = 0
        self.safe_on_weed = 0

    def update(
        self,
        target: np.ndarray,
        semantic_prediction: np.ndarray,
        safe_weed: np.ndarray,
    ) -> None:
        if semantic_prediction.dtype == bool:
            semantic_weed = semantic_prediction
            semantic_classes = np.where(
                semantic_weed, WEED, BACKGROUND
            ).astype(np.uint8)
        else:
            semantic_classes = semantic_prediction
            semantic_weed = semantic_classes == WEED
        if target.shape != semantic_classes.shape or target.shape != safe_weed.shape:
            raise ValueError("target and predictions must have identical HxW shapes")
        self.images += 1
        self.image_megapixels.append(float(target.size / 1_000_000.0))
        valid = target != IGNORE
        encoded = (
            target[valid].astype(np.int64) * 3
            + semantic_classes[valid].astype(np.int64)
        )
        self.confusion += np.bincount(encoded, minlength=9).reshape(3, 3)
        crop = target == CROP
        weed = target == WEED
        self.crop_pixels += int(np.count_nonzero(crop))
        self.weed_pixels += int(np.count_nonzero(weed))
        self.safe_pixels += int(np.count_nonzero(safe_weed & valid))
        self.safe_on_crop += int(np.count_nonzero(safe_weed & crop))
        self.safe_on_weed += int(np.count_nonzero(safe_weed & weed))
        gt_mask = target == WEED
        gt_labels, gt_count, gt_areas, gt_centers, gt_diameters = (
            _component_geometry(gt_mask)
        )
        self.weed_diameters_px.extend(gt_diameters.tolist())
        selections = _bin_selections(gt_diameters)

        prepared: dict[
            str, tuple[np.ndarray, int, np.ndarray, np.ndarray]
        ] = {}
        for mode, prediction in (
            ("semantic_argmax", semantic_weed),
            ("frozen_safe_action", safe_weed),
        ):
            labels, count, _, centers, _ = _component_geometry(prediction)
            points = _deepest_interior_points(prediction, labels, count)
            prepared[mode] = (labels, count, centers, points)

        needs_crop_distance = any(
            len(values[3]) for values in prepared.values()
        )
        crop_mask = target == CROP
        crop_distance = (
            ndimage.distance_transform_edt(~crop_mask)
            if needs_crop_distance and np.any(crop_mask)
            else None
        )

        for mode, prediction in (
            ("semantic_argmax", semantic_weed),
            ("frozen_safe_action", safe_weed),
        ):
            labels, count, centers, points = prepared[mode]
            hits = (
                np.bincount(
                    gt_labels.reshape(-1),
                    weights=prediction.reshape(-1).astype(np.uint8),
                    minlength=gt_count + 1,
                )[1:].astype(np.int64, copy=False)
                if gt_count
                else np.empty(0, dtype=np.int64)
            )
            errors_px, errors_radius = _best_overlap_center_errors(
                gt_labels,
                gt_count,
                gt_centers,
                gt_areas,
                labels,
                count,
                centers,
            )
            for bin_name, selection in selections.items():
                self.components[mode][bin_name].update(
                    gt_areas[selection],
                    hits[selection],
                    errors_px[selection],
                    errors_radius[selection],
                )
            self.actions[mode].update(target, points, crop_distance)

    def compute(self) -> dict[str, object]:
        diameter_distribution = _distribution(self.weed_diameters_px)
        diameter_distribution["sub_patch_fraction"] = (
            float(
                np.mean(np.asarray(self.weed_diameters_px) < PATCH_SIZE_PX)
            )
            if self.weed_diameters_px
            else None
        )
        confusion = self.confusion.astype(np.float64)
        true_positive = np.diag(confusion)
        ground_truth = confusion.sum(axis=1)
        predicted = confusion.sum(axis=0)
        union = ground_truth + predicted - true_positive
        iou = np.divide(
            true_positive,
            union,
            out=np.full(3, np.nan, dtype=np.float64),
            where=union > 0,
        )
        recall = np.divide(
            true_positive,
            ground_truth,
            out=np.full(3, np.nan, dtype=np.float64),
            where=ground_truth > 0,
        )
        precision = np.divide(
            true_positive,
            predicted,
            out=np.full(3, np.nan, dtype=np.float64),
            where=predicted > 0,
        )
        return {
            "images": self.images,
            "image_megapixels": _distribution(self.image_megapixels),
            "gt_weed_semantic_component_diameter_px": diameter_distribution,
            "semantic_segmentation": {
                "confusion_matrix": self.confusion.tolist(),
                "mean_iou": float(np.nanmean(iou)),
                "iou": {
                    name: float(iou[index])
                    for index, name in enumerate(CLASS_NAMES)
                },
                "recall": {
                    name: float(recall[index])
                    for index, name in enumerate(CLASS_NAMES)
                },
                "precision": {
                    name: float(precision[index])
                    for index, name in enumerate(CLASS_NAMES)
                },
            },
            "frozen_safe_pixel_metrics": {
                "crop_pixels": self.crop_pixels,
                "weed_pixels": self.weed_pixels,
                "safe_action_pixels": self.safe_pixels,
                "safe_action_on_crop_pixels": self.safe_on_crop,
                "safe_action_on_weed_pixels": self.safe_on_weed,
                "crop_spray_risk_per_crop_pixel": _ratio(
                    self.safe_on_crop, self.crop_pixels
                ),
                "safe_weed_pixel_recall": _ratio(
                    self.safe_on_weed, self.weed_pixels
                ),
                "safe_weed_pixel_precision": _ratio(
                    self.safe_on_weed, self.safe_pixels
                ),
            },
            "modes": {
                mode: {
                    "component_metrics": {
                        name: counts.compute()
                        for name, counts in bins.items()
                    },
                    "action_point_metrics": self.actions[mode].compute(),
                }
                for mode, bins in self.components.items()
            },
        }

    def merge(self, other: "DatasetAccumulator") -> None:
        self.images += other.images
        self.image_megapixels.extend(other.image_megapixels)
        self.weed_diameters_px.extend(other.weed_diameters_px)
        self.confusion += other.confusion
        self.crop_pixels += other.crop_pixels
        self.weed_pixels += other.weed_pixels
        self.safe_pixels += other.safe_pixels
        self.safe_on_crop += other.safe_on_crop
        self.safe_on_weed += other.safe_on_weed
        for mode in self.components:
            for name in self.components[mode]:
                self.components[mode][name].merge(other.components[mode][name])
            self.actions[mode].merge(other.actions[mode])


class InterventionAccumulator:
    def __init__(self) -> None:
        self.by_dataset: dict[str, DatasetAccumulator] = defaultdict(
            DatasetAccumulator
        )

    def update(
        self,
        target: np.ndarray,
        semantic_prediction: np.ndarray,
        safe_weed: np.ndarray,
        dataset_id: str,
    ) -> None:
        self.by_dataset[dataset_id].update(
            target, semantic_prediction, safe_weed
        )

    def compute(self) -> dict[str, object]:
        overall = DatasetAccumulator()
        for accumulator in self.by_dataset.values():
            overall.merge(accumulator)
        return {
            "overall": overall.compute(),
            "by_dataset": {
                name: accumulator.compute()
                for name, accumulator in sorted(self.by_dataset.items())
            },
        }


def _frozen_policy(checkpoint: Mapping[str, Any]) -> SafetyPolicy:
    config = checkpoint["config"]
    validation = checkpoint.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("Checkpoint has no source-validation result")
    selected = validation.get("selected_operating_point")
    if not isinstance(selected, Mapping) or "weed_threshold" not in selected:
        raise ValueError("Checkpoint has no source-selected operating point")
    selected_by_crop_id = selected.get("weed_threshold_by_crop_id", {})
    if not isinstance(selected_by_crop_id, Mapping):
        raise ValueError("weed_threshold_by_crop_id must be a mapping")
    unknown_threshold = float(
        selected.get("unknown_crop_weed_threshold", selected["weed_threshold"])
    )
    return replace(
        SafetyPolicy(**dict(config.get("safety", {}))),
        weed_threshold=unknown_threshold,
        weed_threshold_by_crop_id={
            int(crop_id): float(threshold)
            for crop_id, threshold in selected_by_crop_id.items()
        },
        unknown_crop_weed_threshold=unknown_threshold,
    )


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _select_records(
    manifest: Path,
    split: str,
    dataset_ids: Sequence[str] | None,
    limit: int | None,
) -> list[SampleRecord]:
    allowed = set(dataset_ids or ())
    records = [
        record
        for record in read_manifest(manifest)
        if record.split == split and (not allowed or record.dataset_id in allowed)
    ]
    if limit is not None:
        records = records[:limit]
    if not records:
        raise ValueError(
            f"No records for split={split!r}, dataset_ids={sorted(allowed)!r}"
        )
    return records


@torch.inference_mode()
def evaluate_records(
    model: torch.nn.Module,
    checkpoint: Mapping[str, Any],
    records: Sequence[SampleRecord],
    data_root: Path,
    workers: int,
    inference_scale: float = 1.0,
) -> dict[str, object]:
    if inference_scale < 1.0:
        raise ValueError("inference_scale must be >= 1.0 for this protocol")
    device = torch.device("cuda")
    dataset = ManifestDataset(records, data_root, EvalTransform(), verify_files=True)
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        persistent_workers=workers > 0,
        collate_fn=padded_collate,
    )
    model.eval()
    config = checkpoint["config"]
    training = config["training"]
    policy = _frozen_policy(checkpoint)
    accumulator = InterventionAccumulator()
    started = time.monotonic()
    inference_seconds = 0.0
    for image_index, batch in enumerate(loader, start=1):
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        torch.cuda.synchronize(device)
        inference_started = time.monotonic()
        native_height, native_width = images.shape[-2:]
        model_images = images
        if not math.isclose(inference_scale, 1.0):
            model_images = torch_functional.interpolate(
                images,
                scale_factor=inference_scale,
                mode="bilinear",
                align_corners=False,
                antialias=True,
            )
        logits = predict_logits(
            model,
            model_images,
            crop_ids,
            use_amp=bool(training.get("amp", True)),
            tile_size=training.get("eval_tile_size"),
            tile_overlap=int(training.get("eval_tile_overlap", 128)),
            tile_trigger_pixels=int(
                training.get("eval_tile_trigger_pixels", 4_000_000)
            ),
        )
        if logits.shape[-2:] != (native_height, native_width):
            logits = torch_functional.interpolate(
                logits,
                size=(native_height, native_width),
                mode="bilinear",
                align_corners=False,
            )
        probabilities = logits.float().softmax(dim=1)
        decisions = apply_safety_policy(probabilities, policy, crop_ids)
        torch.cuda.synchronize(device)
        inference_seconds += time.monotonic() - inference_started
        height, width = batch["valid_size"][0]
        target = (
            batch["mask"][0, :height, :width].detach().cpu().numpy()
        )
        semantic = (
            probabilities[0, :, :height, :width]
            .argmax(dim=0)
            .detach()
            .cpu()
            .numpy()
        )
        safe = (
            decisions["safe_weed"][0, :height, :width]
            .detach()
            .cpu()
            .numpy()
        )
        accumulator.update(
            target,
            semantic,
            safe,
            str(batch["dataset_id"][0]),
        )
        if image_index % 50 == 0 or image_index == len(dataset):
            elapsed = time.monotonic() - started
            print(
                f"  {image_index}/{len(dataset)} images "
                f"({image_index / max(elapsed, 1e-9):.2f} img/s)",
                flush=True,
            )
    elapsed = time.monotonic() - started
    result = accumulator.compute()
    result["runtime"] = {
        "images": len(dataset),
        "seconds": elapsed,
        "images_per_second": len(dataset) / max(elapsed, 1e-9),
        "device": str(device),
        "inference_scale": inference_scale,
        "perception_seconds": inference_seconds,
        "perception_ms_per_image": 1000.0 * inference_seconds / len(dataset),
        "perception_images_per_second": len(dataset)
        / max(inference_seconds, 1e-9),
        "runtime_note": (
            "perception includes interpolation, model/tiled inference, output "
            "resize, softmax, and frozen safety policy; total runtime also "
            "includes CPU intervention metrics and data loading"
        ),
    }
    result["frozen_safety_policy"] = {
        "weed_threshold": policy.weed_threshold,
        "weed_threshold_by_crop_id": dict(policy.weed_threshold_by_crop_id),
        "unknown_crop_weed_threshold": policy.unknown_crop_weed_threshold,
        "crop_threshold": policy.crop_threshold,
        "min_confidence": policy.min_confidence,
        "min_margin": policy.min_margin,
        "max_entropy": policy.max_entropy,
        "crop_dilation_px": policy.crop_dilation_px,
        "external_threshold_tuning_performed": False,
    }
    return result


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(payload: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(dict(payload)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _completed_result_matches(
    destination: Path,
    *,
    model_name: str,
    evaluation_name: str,
    split: str,
    records: int,
    inference_scale: float,
    checkpoint_sha256: str,
    manifest_sha256_value: str,
) -> dict[str, object] | None:
    """Return a completed compatible payload, otherwise fail closed."""
    if not destination.is_file():
        return None
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
        identity = payload["identity"]
        provenance = payload["provenance"]
        if (
            identity["model"] != model_name
            or identity["evaluation"] != evaluation_name
            or identity["split"] != split
            or int(identity["records"]) != records
            or int(payload["overall"]["images"]) != records
            or not math.isclose(
                float(identity.get("inference_scale", 1.0)),
                inference_scale,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or provenance["checkpoint_sha256"] != checkpoint_sha256
            or provenance["evaluation_manifest_sha256"]
            != manifest_sha256_value
            or provenance.get("no_external_threshold_tuning") is not True
        ):
            return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload


def run_config(
    config_path: Path,
    *,
    only_model: str | None = None,
    only_evaluation: str | None = None,
    limit: int | None = None,
    resume: bool = False,
) -> dict[str, object]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for accepted-checkpoint evaluation")
    project_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = _resolve(project_root, config["data_root"])
    output_root = _resolve(project_root, config["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    workers = int(config.get("workers", 4))
    results: dict[str, object] = {}
    for model_name, model_config in config["models"].items():
        if only_model and model_name != only_model:
            continue
        checkpoint_path = _resolve(project_root, model_config["checkpoint"])
        checkpoint_digest = _sha256(checkpoint_path)
        print(f"Loading {model_name}: {checkpoint_path}", flush=True)
        model, checkpoint = load_checkpoint(checkpoint_path, torch.device("cuda"))
        model_results: dict[str, object] = {}
        for evaluation in model_config["evaluations"]:
            evaluation_name = str(evaluation["name"])
            if only_evaluation and evaluation_name != only_evaluation:
                continue
            manifest = _resolve(project_root, evaluation["manifest"])
            split = str(evaluation["split"])
            records = _select_records(
                manifest,
                split,
                evaluation.get("dataset_ids"),
                limit,
            )
            inference_scale = float(evaluation.get("inference_scale", 1.0))
            destination = output_root / model_name / f"{evaluation_name}.json"
            manifest_digest = manifest_sha256(manifest)
            if resume:
                completed = _completed_result_matches(
                    destination,
                    model_name=model_name,
                    evaluation_name=evaluation_name,
                    split=split,
                    records=len(records),
                    inference_scale=inference_scale,
                    checkpoint_sha256=checkpoint_digest,
                    manifest_sha256_value=manifest_digest,
                )
                if completed is not None:
                    print(
                        f"Reusing completed {model_name}/{evaluation_name}: "
                        f"{len(records)} images",
                        flush=True,
                    )
                    model_results[evaluation_name] = {
                        "path": str(destination),
                        "checkpoint_sha256": checkpoint_digest,
                        "manifest_sha256": manifest_digest,
                        "records": len(records),
                    }
                    continue
            print(
                f"Evaluating {model_name}/{evaluation_name}: "
                f"{len(records)} images",
                flush=True,
            )
            payload = evaluate_records(
                model,
                checkpoint,
                records,
                data_root,
                workers,
                inference_scale=inference_scale,
            )
            payload["identity"] = {
                "model": model_name,
                "evaluation": evaluation_name,
                "role": str(evaluation["role"]),
                "manifest": str(manifest),
                "split": split,
                "dataset_filter": list(evaluation.get("dataset_ids", [])),
                "records": len(records),
                "inference_scale": inference_scale,
            }
            payload["provenance"] = {
                "checkpoint": str(checkpoint_path),
                "checkpoint_sha256": checkpoint_digest,
                "checkpoint_runtime_provenance": checkpoint[
                    "runtime_provenance"
                ],
                "evaluation_manifest_sha256": manifest_digest,
                "selected_mask_tree_sha256": mask_tree_sha256(
                    records, data_root
                ),
                "metric_protocol": "intervention_semantic_component_proxy_v1",
                "no_external_threshold_tuning": True,
            }
            _write_json(payload, destination)
            model_results[evaluation_name] = {
                "path": str(destination),
                "checkpoint_sha256": checkpoint_digest,
                "manifest_sha256": manifest_digest,
                "records": len(records),
            }
        del model
        torch.cuda.empty_cache()
        results[model_name] = model_results
    index = {
        "protocol": "intervention_semantic_component_proxy_v1",
        "config": str(config_path.resolve()),
        "config_sha256": _sha256(config_path),
        "definitions": {
            "ground_truth_unit": (
                "8-connected component of a semantic weed mask; not a true "
                "botanical plant instance"
            ),
            "semantic_argmax": "weed pixels from three-class argmax",
            "frozen_safe_action": (
                "source-validation-selected threshold plus uncertainty and "
                "predicted-crop guard; no target-set retuning"
            ),
            "action_point": (
                "maximum Euclidean-distance-transform point inside each "
                "predicted connected component"
            ),
            "center_proxy": (
                "centroid of greatest-overlap predicted component compared "
                "with semantic GT-component centroid; not root/stem/meristem"
            ),
            "diameter_bins_px": {
                name: [lower, None if math.isinf(upper) else upper]
                for name, lower, upper in DIAMETER_BINS
            },
            "backbone_patch_size_px": PATCH_SIZE_PX,
            "coverage_thresholds": list(COVERAGE_THRESHOLDS),
            "footprint_radii_px": list(FOOTPRINT_RADII_PX),
        },
        "results": results,
    }
    _write_json(index, output_root / "index.json")
    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/intervention_metrics_v1.yaml"),
    )
    parser.add_argument("--model", help="Run only one configured model")
    parser.add_argument(
        "--evaluation", help="Run only one configured evaluation name"
    )
    parser.add_argument(
        "--limit", type=int, help="Deterministic smoke-test limit per evaluation"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse only completed identity/hash-compatible result JSONs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_config(
        args.config.expanduser().resolve(),
        only_model=args.model,
        only_evaluation=args.evaluation,
        limit=args.limit,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
