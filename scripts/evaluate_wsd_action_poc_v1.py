#!/usr/bin/env python3
"""Calibrate and freeze weed-box and stem-action metrics for the WSD PoC.

The validation capture date selects confidence thresholds.  The held-out test
date is evaluated once with those frozen thresholds.  An action is a predicted
weed keypoint; it is a true positive only when it can be assigned one-to-one to
a visible ground-truth weed stem within the declared tolerance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import linear_sum_assignment


WEED_CLASS = 0
CROP_CLASSES = (1, 2)


@dataclass(frozen=True)
class Instance:
    class_id: int
    box: tuple[float, float, float, float]
    point: tuple[float, float] | None


@dataclass(frozen=True)
class Prediction:
    class_id: int
    confidence: float
    box: tuple[float, float, float, float]
    point: tuple[float, float]
    keypoint_confidence: float

    @property
    def action_score(self) -> float:
        # Both weed identity and point visibility must be credible before fire.
        return min(self.confidence, self.keypoint_confidence)


@dataclass(frozen=True)
class Sample:
    image_path: Path
    width: int
    height: int
    ground_truth: tuple[Instance, ...]
    predictions: tuple[Prediction, ...]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prf(true_positive: int, false_positive: int, false_negative: int) -> dict[str, Any]:
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def xywh_to_xyxy(
    x: float, y: float, width: float, height: float
) -> tuple[float, float, float, float]:
    return (
        x - width / 2.0,
        y - height / 2.0,
        x + width / 2.0,
        y + height / 2.0,
    )


def box_iou_matrix(
    predictions: Sequence[tuple[float, float, float, float]],
    ground_truth: Sequence[tuple[float, float, float, float]],
) -> np.ndarray:
    if not predictions or not ground_truth:
        return np.zeros((len(predictions), len(ground_truth)), dtype=np.float64)
    left = np.asarray(predictions, dtype=np.float64)
    right = np.asarray(ground_truth, dtype=np.float64)
    x1 = np.maximum(left[:, None, 0], right[None, :, 0])
    y1 = np.maximum(left[:, None, 1], right[None, :, 1])
    x2 = np.minimum(left[:, None, 2], right[None, :, 2])
    y2 = np.minimum(left[:, None, 3], right[None, :, 3])
    intersection = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    left_area = np.maximum(0.0, left[:, 2] - left[:, 0]) * np.maximum(
        0.0, left[:, 3] - left[:, 1]
    )
    right_area = np.maximum(0.0, right[:, 2] - right[:, 0]) * np.maximum(
        0.0, right[:, 3] - right[:, 1]
    )
    union = left_area[:, None] + right_area[None, :] - intersection
    return np.divide(
        intersection,
        union,
        out=np.zeros_like(intersection),
        where=union > 0.0,
    )


def maximum_valid_pairs(
    values: np.ndarray,
    valid: np.ndarray,
    *,
    prefer_larger: bool,
) -> list[tuple[int, int]]:
    """Maximum-cardinality one-to-one matching, then best total value."""
    if values.shape != valid.shape:
        raise ValueError("values and valid must have equal shapes")
    rows, columns = values.shape
    if not rows or not columns or not bool(np.any(valid)):
        return []
    # Dummy columns permit every prediction to remain unmatched at zero cost.
    cost = np.zeros((rows, columns + rows), dtype=np.float64)
    quality = values if prefer_larger else -values
    finite = quality[np.isfinite(quality)]
    scale = max(1.0, float(np.max(np.abs(finite))) if finite.size else 1.0)
    cost[:, :columns] = np.where(valid, -1.0 - quality / scale * 1e-3, 0.0)
    row_indices, column_indices = linear_sum_assignment(cost)
    return [
        (int(row), int(column))
        for row, column in zip(row_indices, column_indices, strict=True)
        if column < columns and bool(valid[row, column])
    ]


def _point_distance_matrix(
    predictions: Sequence[tuple[float, float]],
    ground_truth: Sequence[tuple[float, float]],
) -> np.ndarray:
    if not predictions or not ground_truth:
        return np.zeros((len(predictions), len(ground_truth)), dtype=np.float64)
    left = np.asarray(predictions, dtype=np.float64)
    right = np.asarray(ground_truth, dtype=np.float64)
    return np.linalg.norm(left[:, None, :] - right[None, :, :], axis=2)


def point_footprint_hits_box(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
    radius: float,
) -> bool:
    x, y = point
    x1, y1, x2, y2 = box
    delta_x = max(x1 - x, 0.0, x - x2)
    delta_y = max(y1 - y, 0.0, y - y2)
    return math.hypot(delta_x, delta_y) <= radius


def _weed_gt(sample: Sample, *, visible_only: bool = False) -> list[Instance]:
    return [
        item
        for item in sample.ground_truth
        if item.class_id == WEED_CLASS and (item.point is not None or not visible_only)
    ]


def _weed_predictions(
    sample: Sample, threshold: float, *, action: bool
) -> list[Prediction]:
    return [
        item
        for item in sample.predictions
        if item.class_id == WEED_CLASS
        and (item.action_score if action else item.confidence) >= threshold
    ]


def evaluate_detection(
    samples: Sequence[Sample], threshold: float, iou_threshold: float = 0.50
) -> dict[str, Any]:
    true_positive = false_positive = false_negative = 0
    for sample in samples:
        predictions = _weed_predictions(sample, threshold, action=False)
        ground_truth = _weed_gt(sample)
        overlaps = box_iou_matrix(
            [item.box for item in predictions], [item.box for item in ground_truth]
        )
        matches = maximum_valid_pairs(
            overlaps, overlaps >= iou_threshold, prefer_larger=True
        )
        true_positive += len(matches)
        false_positive += len(predictions) - len(matches)
        false_negative += len(ground_truth) - len(matches)
    result = prf(true_positive, false_positive, false_negative)
    result.update({"confidence_threshold": threshold, "iou_threshold": iou_threshold})
    return result


def _point_pairs(
    predictions: Sequence[Prediction],
    ground_truth: Sequence[Instance],
    *,
    tolerance_kind: str,
    tolerance: float,
) -> tuple[list[tuple[int, int]], np.ndarray]:
    distances = _point_distance_matrix(
        [item.point for item in predictions],
        [item.point for item in ground_truth if item.point is not None],
    )
    if tolerance_kind == "box_diagonal_fraction":
        diagonals = np.asarray(
            [
                math.hypot(item.box[2] - item.box[0], item.box[3] - item.box[1])
                for item in ground_truth
            ],
            dtype=np.float64,
        )
        limits = diagonals[None, :] * tolerance
    elif tolerance_kind == "pixels":
        limits = np.full_like(distances, tolerance)
    else:
        raise ValueError(f"Unknown tolerance kind: {tolerance_kind}")
    matches = maximum_valid_pairs(
        distances, distances <= limits, prefer_larger=False
    )
    return matches, distances


def evaluate_actions(
    samples: Sequence[Sample],
    threshold: float,
    *,
    tolerance_kind: str = "box_diagonal_fraction",
    tolerance: float = 0.10,
    footprint_radii_px: Sequence[int] = (0, 5, 10, 20),
) -> dict[str, Any]:
    true_positive = false_positive = false_negative = 0
    collisions = {int(radius): 0 for radius in footprint_radii_px}
    crop_as_weed_false_fires = 0
    false_positive_breakdown = {
        "duplicate_action_near_already_hit_stem": 0,
        "crop_as_weed_box_match": 0,
        "stem_localization_near_miss_within_2x_tolerance": 0,
        "other_or_background": 0,
    }
    actions = 0
    distance_errors: list[float] = []
    normalized_errors: list[float] = []
    size_total = {"small_lt5pct_diag": 0, "medium_5to10pct_diag": 0, "large_ge10pct_diag": 0}
    size_hit = {key: 0 for key in size_total}
    for sample in samples:
        predictions = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample, visible_only=True)
        matches, distances = _point_pairs(
            predictions,
            ground_truth,
            tolerance_kind=tolerance_kind,
            tolerance=tolerance,
        )
        matched_gt = {ground_truth_index for _, ground_truth_index in matches}
        matched_predictions = {prediction_index for prediction_index, _ in matches}
        true_positive += len(matches)
        false_positive += len(predictions) - len(matches)
        false_negative += len(ground_truth) - len(matches)
        actions += len(predictions)
        crop_boxes = [
            item.box for item in sample.ground_truth if item.class_id in CROP_CLASSES
        ]
        unmatched_prediction_indices = [
            index
            for index, prediction in enumerate(predictions)
            if index not in matched_predictions
        ]
        unmatched_predictions = [
            predictions[index] for index in unmatched_prediction_indices
        ]
        crop_overlaps = box_iou_matrix(
            [item.box for item in unmatched_predictions], crop_boxes
        )
        crop_pairs = maximum_valid_pairs(
            crop_overlaps, crop_overlaps >= 0.50, prefer_larger=True
        )
        crop_local_indices = {prediction_index for prediction_index, _ in crop_pairs}
        crop_as_weed_false_fires += len(crop_pairs)
        if tolerance_kind == "box_diagonal_fraction":
            point_limits = np.asarray(
                [
                    math.hypot(
                        item.box[2] - item.box[0], item.box[3] - item.box[1]
                    )
                    * tolerance
                    for item in ground_truth
                ],
                dtype=np.float64,
            )
        else:
            point_limits = np.full(len(ground_truth), tolerance, dtype=np.float64)
        for local_index, prediction_index in enumerate(unmatched_prediction_indices):
            row = distances[prediction_index] if distances.shape[1] else np.empty(0)
            if row.size and bool(np.any(row <= point_limits)):
                key = "duplicate_action_near_already_hit_stem"
            elif local_index in crop_local_indices:
                key = "crop_as_weed_box_match"
            elif row.size and bool(np.any(row <= point_limits * 2.0)):
                key = "stem_localization_near_miss_within_2x_tolerance"
            else:
                key = "other_or_background"
            false_positive_breakdown[key] += 1
        for prediction in predictions:
            for radius in collisions:
                if any(
                    point_footprint_hits_box(prediction.point, box, float(radius))
                    for box in crop_boxes
                ):
                    collisions[radius] += 1
        for prediction_index, ground_truth_index in matches:
            error = float(distances[prediction_index, ground_truth_index])
            box = ground_truth[ground_truth_index].box
            diagonal = math.hypot(box[2] - box[0], box[3] - box[1])
            distance_errors.append(error)
            normalized_errors.append(error / diagonal if diagonal else math.inf)
        for index, instance in enumerate(ground_truth):
            diagonal_fraction = math.hypot(
                instance.box[2] - instance.box[0], instance.box[3] - instance.box[1]
            ) / math.hypot(sample.width, sample.height)
            if diagonal_fraction < 0.05:
                key = "small_lt5pct_diag"
            elif diagonal_fraction < 0.10:
                key = "medium_5to10pct_diag"
            else:
                key = "large_ge10pct_diag"
            size_total[key] += 1
            size_hit[key] += int(index in matched_gt)
    result = prf(true_positive, false_positive, false_negative)
    result.update(
        {
            "confidence_threshold": threshold,
            "score_definition": "min(weed_box_confidence,keypoint_confidence)",
            "tolerance_kind": tolerance_kind,
            "tolerance": tolerance,
            "actions": actions,
            "visible_ground_truth_stems": true_positive + false_negative,
            "crop_box_collision": {
                str(radius): {
                    "actions_colliding": collisions[radius],
                    "rate_per_action": collisions[radius] / actions if actions else None,
                }
                for radius in collisions
            },
            "crop_as_weed_false_fire": {
                "definition": "unmatched predicted-weed boxes assigned one-to-one to GT crop boxes at IoU>=0.50",
                "actions": crop_as_weed_false_fires,
                "rate_per_action": crop_as_weed_false_fires / actions
                if actions
                else None,
            },
            "false_positive_breakdown": {
                **false_positive_breakdown,
                "sum": sum(false_positive_breakdown.values()),
            },
            "true_positive_error_px": _distribution(distance_errors),
            "true_positive_error_box_diagonal_fraction": _distribution(
                normalized_errors
            ),
            "recall_by_weed_size": {
                key: {
                    "ground_truth_stems": size_total[key],
                    "hits": size_hit[key],
                    "recall": size_hit[key] / size_total[key]
                    if size_total[key]
                    else None,
                }
                for key in size_total
            },
        }
    )
    return result


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p90": None, "p95": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean": float(array.mean()),
        "p50": float(np.quantile(array, 0.50)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
    }


def threshold_curve(
    samples: Sequence[Sample],
    thresholds: Iterable[float],
    *,
    action: bool,
) -> list[dict[str, Any]]:
    evaluator = evaluate_actions if action else evaluate_detection
    return [evaluator(samples, float(threshold)) for threshold in thresholds]


def with_box_center_actions(samples: Sequence[Sample]) -> list[Sample]:
    """Detection-only control: fire at each predicted weed box center."""
    return [
        Sample(
            image_path=sample.image_path,
            width=sample.width,
            height=sample.height,
            ground_truth=sample.ground_truth,
            predictions=tuple(
                Prediction(
                    class_id=item.class_id,
                    confidence=item.confidence,
                    box=item.box,
                    point=(
                        (item.box[0] + item.box[2]) / 2.0,
                        (item.box[1] + item.box[3]) / 2.0,
                    ),
                    keypoint_confidence=item.confidence,
                )
                for item in sample.predictions
            ),
        )
        for sample in samples
    ]


def deduplicate_action_points(
    samples: Sequence[Sample], radius_fraction_of_smaller_box_diagonal: float
) -> list[Sample]:
    """Keep the highest-score action among nearby within-frame weed points."""
    fraction = radius_fraction_of_smaller_box_diagonal
    if fraction < 0.0:
        raise ValueError("deduplication radius fraction cannot be negative")
    converted: list[Sample] = []
    for sample in samples:
        weed = [item for item in sample.predictions if item.class_id == WEED_CLASS]
        other = [item for item in sample.predictions if item.class_id != WEED_CLASS]
        kept: list[Prediction] = []
        for candidate in sorted(
            weed,
            key=lambda item: (item.action_score, item.confidence),
            reverse=True,
        ):
            candidate_diagonal = math.hypot(
                candidate.box[2] - candidate.box[0],
                candidate.box[3] - candidate.box[1],
            )
            duplicate = False
            for prior in kept:
                prior_diagonal = math.hypot(
                    prior.box[2] - prior.box[0], prior.box[3] - prior.box[1]
                )
                radius = fraction * min(candidate_diagonal, prior_diagonal)
                if math.dist(candidate.point, prior.point) <= radius:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        converted.append(
            Sample(
                image_path=sample.image_path,
                width=sample.width,
                height=sample.height,
                ground_truth=sample.ground_truth,
                predictions=tuple(kept + other),
            )
        )
    return converted


def choose_threshold(
    curve: Sequence[dict[str, Any]],
    *,
    maximum_crop_false_fire_rate: float | None = None,
) -> dict[str, Any]:
    usable = [item for item in curve if item["f1"] is not None]
    if not usable:
        raise ValueError("No defined F1 values in threshold curve")
    feasible = usable
    gate_passed: bool | None = None
    if maximum_crop_false_fire_rate is not None:
        feasible = [
            item
            for item in usable
            if item["crop_as_weed_false_fire"]["rate_per_action"] is not None
            and item["crop_as_weed_false_fire"]["rate_per_action"]
            <= maximum_crop_false_fire_rate
        ]
        gate_passed = bool(feasible)
        if not feasible:
            # Honest fallback: lowest collision rate, then highest F1.  The gate
            # remains failed and the selected setting is not deployment-safe.
            minimum = min(
                item["crop_as_weed_false_fire"]["rate_per_action"]
                for item in usable
                if item["crop_as_weed_false_fire"]["rate_per_action"] is not None
            )
            feasible = [
                item
                for item in usable
                if item["crop_as_weed_false_fire"]["rate_per_action"] == minimum
            ]
    selected = max(
        feasible,
        key=lambda item: (
            float(item["f1"]),
            float(item["recall"]),
            -float(item["confidence_threshold"]),
        ),
    )
    return {
        "threshold": selected["confidence_threshold"],
        "validation_metrics": selected,
        "crop_false_fire_gate_passed": gate_passed,
        "maximum_crop_false_fire_rate": maximum_crop_false_fire_rate,
    }


def _read_ground_truth(label_path: Path, width: int, height: int) -> tuple[Instance, ...]:
    instances: list[Instance] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        values = [float(token) for token in line.split()]
        if len(values) != 8:
            raise ValueError(f"{label_path}:{line_number}: expected 8 fields")
        class_id = int(values[0])
        if class_id != values[0]:
            raise ValueError(f"{label_path}:{line_number}: non-integer class")
        x, y, box_width, box_height, point_x, point_y, visibility = values[1:]
        normalized_box = xywh_to_xyxy(x, y, box_width, box_height)
        box = (
            normalized_box[0] * width,
            normalized_box[1] * height,
            normalized_box[2] * width,
            normalized_box[3] * height,
        )
        point = (
            (point_x * width, point_y * height) if int(visibility) > 0 else None
        )
        instances.append(Instance(class_id=class_id, box=box, point=point))
    return tuple(instances)


def _dataset_split(dataset_yaml: Path, split: str) -> tuple[Path, list[Path]]:
    data = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8"))
    root = Path(data["path"]).expanduser().resolve()
    image_root = (root / data[split]).resolve()
    images = sorted(
        path
        for path in image_root.iterdir()
        if path.suffix.lower() in {".bmp", ".jpg", ".jpeg", ".png"}
    )
    if not images:
        raise ValueError(f"No images in {image_root}")
    return root, images


def infer_split(
    model: Any,
    dataset_yaml: Path,
    split: str,
    *,
    image_size: int,
    batch: int,
    device: int,
) -> list[Sample]:
    root, image_paths = _dataset_split(dataset_yaml, split)
    # A directory source uses Ultralytics' streaming file loader and honours
    # ``batch``.  Passing a Python list eagerly materializes every 2048px BMP
    # and can turn the whole split into one GPU batch.
    results = model.predict(
        source=str(image_paths[0].parent),
        imgsz=image_size,
        conf=0.001,
        iou=0.70,
        max_det=500,
        batch=batch,
        device=device,
        stream=True,
        verbose=False,
        save=False,
    )
    expected = {path.resolve(): path for path in image_paths}
    collected: dict[Path, Sample] = {}
    for result in results:
        result_path = Path(result.path).resolve()
        if result_path not in expected:
            raise ValueError(f"Unexpected prediction path: {result_path}")
        if result_path in collected:
            raise ValueError(f"Duplicate prediction path: {result_path}")
        expected_path = expected[result_path]
        height, width = result.orig_shape
        label_path = root / "labels" / split / f"{expected_path.stem}.txt"
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        confidences = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy().astype(np.int64)
        points = result.keypoints.xy.detach().cpu().numpy()[:, 0, :]
        keypoint_tensor = result.keypoints.conf
        keypoint_confidences = (
            keypoint_tensor.detach().cpu().numpy()[:, 0]
            if keypoint_tensor is not None
            else confidences.copy()
        )
        predictions = tuple(
            Prediction(
                class_id=int(class_id),
                confidence=float(confidence),
                box=tuple(float(value) for value in box),
                point=tuple(float(value) for value in point),
                keypoint_confidence=float(keypoint_confidence),
            )
            for box, confidence, class_id, point, keypoint_confidence in zip(
                boxes,
                confidences,
                classes,
                points,
                keypoint_confidences,
                strict=True,
            )
        )
        collected[result_path] = Sample(
                image_path=expected_path,
                width=int(width),
                height=int(height),
                ground_truth=_read_ground_truth(label_path, int(width), int(height)),
                predictions=predictions,
            )
    missing = [path for path in image_paths if path.resolve() not in collected]
    if missing:
        raise ValueError(f"Missing predictions for {len(missing)} images")
    return [collected[path.resolve()] for path in image_paths]


def _sample_payload(sample: Sample) -> dict[str, Any]:
    return {
        "image_path": str(sample.image_path),
        "width": sample.width,
        "height": sample.height,
        "ground_truth": [
            {"class_id": item.class_id, "box": item.box, "point": item.point}
            for item in sample.ground_truth
        ],
        "predictions": [
            {
                "class_id": item.class_id,
                "confidence": item.confidence,
                "box": item.box,
                "point": item.point,
                "keypoint_confidence": item.keypoint_confidence,
            }
            for item in sample.predictions
        ],
    }


def _write_gallery(
    samples: Sequence[Sample], output: Path, threshold: float, count: int = 6
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[float, Sample]] = []
    for sample in samples:
        metric = evaluate_actions([sample], threshold)
        f1 = float(metric["f1"] or 0.0)
        candidates.append((f1, sample))
    candidates.sort(key=lambda item: (item[0], item[1].image_path.name))
    positions = np.linspace(0, len(candidates) - 1, min(count, len(candidates)), dtype=int)
    paths: list[str] = []
    font = ImageFont.load_default()
    for rank, position in enumerate(positions, 1):
        sample = candidates[int(position)][1]
        image = Image.open(sample.image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        for item in sample.ground_truth:
            colour = "#39d353" if item.class_id in CROP_CLASSES else "#ff4040"
            draw.rectangle(item.box, outline=colour, width=4)
            if item.point is not None:
                x, y = item.point
                draw.line((x - 9, y, x + 9, y), fill="#00e5ff", width=4)
                draw.line((x, y - 9, x, y + 9), fill="#00e5ff", width=4)
        selected = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample, visible_only=True)
        matches, _ = _point_pairs(
            selected,
            ground_truth,
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        )
        hit_predictions = {index for index, _ in matches}
        for index, item in enumerate(selected):
            colour = "#ffe600" if index in hit_predictions else "#ff00ff"
            draw.rectangle(item.box, outline=colour, width=3)
            x, y = item.point
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=colour, width=4)
        metric = evaluate_actions([sample], threshold)
        banner_height = 84
        canvas = Image.new("RGB", (image.width, image.height + banner_height), "#101820")
        canvas.paste(image, (0, banner_height))
        banner = ImageDraw.Draw(canvas)
        banner.text(
            (12, 8),
            "GT crop box=GREEN | GT weed box=RED | GT stem=CYAN +",
            fill="white",
            font=font,
        )
        banner.text(
            (12, 29),
            "Predicted action: YELLOW=hit | MAGENTA=miss/false fire",
            fill="white",
            font=font,
        )
        banner.text(
            (12, 50),
            f"{sample.image_path.name} | P={metric['precision']} R={metric['recall']} F1={metric['f1']}",
            fill="white",
            font=font,
        )
        path = output / f"{rank:02d}_{sample.image_path.stem}.jpg"
        canvas.save(path, quality=92)
        paths.append(str(path))
    return paths


def _write_curve_plot(
    detection_curve: Sequence[dict[str, Any]],
    action_curve: Sequence[dict[str, Any]],
    detection_selection: dict[str, Any],
    action_selection: dict[str, Any],
    action_safety_selection: dict[str, Any],
    box_center_curve: Sequence[dict[str, Any]],
    box_center_selection: dict[str, Any],
    deduplicated_curve: Sequence[dict[str, Any]],
    deduplicated_selection: dict[str, Any],
    output: Path,
) -> None:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for axis, curve, selection, title in (
        (axes[0], detection_curve, detection_selection, "Weed detection (IoU >= 0.50)"),
        (axes[1], action_curve, action_selection, "Stem action (<= 10% weed-box diagonal)"),
    ):
        precision = [item["precision"] or 0.0 for item in curve]
        recall = [item["recall"] or 0.0 for item in curve]
        axis.plot(recall, precision, color="#2563eb", linewidth=2)
        selected = selection["validation_metrics"]
        axis.scatter([selected["recall"]], [selected["precision"]], color="#dc2626", s=60)
        axis.annotate(
            f"thr={selection['threshold']:.2f}\nF1={selected['f1']:.3f}",
            (selected["recall"], selected["precision"]),
            xytext=(8, -34),
            textcoords="offset points",
        )
        axis.set(xlim=(0, 1.01), ylim=(0, 1.01), xlabel="Recall", ylabel="Precision", title=title)
        axis.grid(alpha=0.25)
    safe = action_safety_selection["validation_metrics"]
    axes[1].scatter(
        [safe["recall"]],
        [safe["precision"]],
        color="#16a34a",
        marker="s",
        s=55,
        label="crop-box-safe selection",
    )
    axes[1].plot(
        [item["recall"] or 0.0 for item in box_center_curve],
        [item["precision"] or 0.0 for item in box_center_curve],
        color="#6b7280",
        linestyle="--",
        linewidth=1.5,
        label="box-center control",
    )
    center = box_center_selection["validation_metrics"]
    axes[1].scatter(
        [center["recall"]],
        [center["precision"]],
        color="#111827",
        marker="x",
        s=55,
    )
    axes[1].plot(
        [item["recall"] or 0.0 for item in deduplicated_curve],
        [item["precision"] or 0.0 for item in deduplicated_curve],
        color="#7c3aed",
        linestyle="-.",
        linewidth=1.7,
        label="keypoint + point dedupe",
    )
    deduplicated = deduplicated_selection["validation_metrics"]
    axes[1].scatter(
        [deduplicated["recall"]],
        [deduplicated["precision"]],
        color="#7c3aed",
        marker="D",
        s=48,
    )
    axes[1].legend(loc="lower left")
    figure.suptitle("Validation chooses thresholds; test never tunes them")
    figure.savefig(output, dpi=170)
    plt.close(figure)


def run(
    config_path: Path,
    checkpoint_override: Path | None = None,
    *,
    image_size_override: int | None = None,
    batch_override: int | None = None,
    output_name: str = "action_metrics_v1",
) -> dict[str, Any]:
    if not output_name or Path(output_name).name != output_name:
        raise ValueError("output_name must be one safe path component")
    from ultralytics import YOLO, settings

    for key in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb"):
        settings.update({key: False})
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = Path(config["data_root"]).expanduser().resolve()
    dataset_value = Path(config["dataset_yaml"]).expanduser()
    dataset_yaml = (
        dataset_value.resolve()
        if dataset_value.is_absolute()
        else (data_root / dataset_value).resolve()
    )
    checkpoint = (
        checkpoint_override.expanduser().resolve()
        if checkpoint_override is not None
        else (data_root / config["output"]["project"] / config["output"]["name"] / "weights/best.pt").resolve()
    )
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    output = checkpoint.parents[1] / output_name
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    model = YOLO(str(checkpoint))
    evaluation = config["evaluation"]
    image_size = int(image_size_override or evaluation["image_size"])
    inference_batch = int(batch_override or evaluation["batch"])
    if image_size <= 0 or image_size % 32:
        raise ValueError("image_size must be a positive multiple of 32")
    if inference_batch <= 0:
        raise ValueError("batch must be positive")
    samples: dict[str, list[Sample]] = {}
    for split in ("train", "val", "test"):
        samples[split] = infer_split(
            model,
            dataset_yaml,
            split,
            image_size=image_size,
            batch=inference_batch,
            device=int(config["training"]["device"]),
        )
        cache = output / f"predictions_{split}.json"
        cache.write_text(
            json.dumps([_sample_payload(item) for item in samples[split]]) + "\n",
            encoding="utf-8",
        )
    thresholds = [round(value / 100.0, 2) for value in range(1, 100)]
    detection_curve = threshold_curve(samples["val"], thresholds, action=False)
    action_curve = threshold_curve(samples["val"], thresholds, action=True)
    center_samples = {
        split: with_box_center_actions(split_samples)
        for split, split_samples in samples.items()
    }
    center_action_curve = threshold_curve(
        center_samples["val"], thresholds, action=True
    )
    detection_selection = choose_threshold(detection_curve)
    action_balanced_selection = choose_threshold(action_curve)
    action_safety_selection = choose_threshold(
        action_curve, maximum_crop_false_fire_rate=0.005
    )
    center_balanced_selection = choose_threshold(center_action_curve)
    center_safety_selection = choose_threshold(
        center_action_curve, maximum_crop_false_fire_rate=0.005
    )
    deduplication_screen: list[dict[str, Any]] = []
    deduplicated_candidates: dict[float, tuple[list[Sample], list[dict[str, Any]]]] = {}
    for fraction in (0.05, 0.10, 0.15, 0.20, 0.30):
        candidate_samples = deduplicate_action_points(samples["val"], fraction)
        curve = threshold_curve(candidate_samples, thresholds, action=True)
        selection = choose_threshold(curve)
        deduplicated_candidates[fraction] = (candidate_samples, curve)
        deduplication_screen.append(
            {
                "radius_fraction_of_smaller_predicted_box_diagonal": fraction,
                "selection": selection,
            }
        )
    selected_deduplication = max(
        deduplication_screen,
        key=lambda item: (
            float(item["selection"]["validation_metrics"]["f1"]),
            float(item["selection"]["validation_metrics"]["recall"]),
            -float(item["radius_fraction_of_smaller_predicted_box_diagonal"]),
        ),
    )
    deduplication_fraction = float(
        selected_deduplication[
            "radius_fraction_of_smaller_predicted_box_diagonal"
        ]
    )
    deduplicated_selection = selected_deduplication["selection"]
    deduplicated_curve = deduplicated_candidates[deduplication_fraction][1]
    deduplicated_samples = {
        split: deduplicate_action_points(split_samples, deduplication_fraction)
        for split, split_samples in samples.items()
    }
    detection_threshold = float(detection_selection["threshold"])
    action_modes: dict[str, Any] = {}
    for mode_name, selection, mode_samples in (
        ("keypoint_balanced_max_f1", action_balanced_selection, samples["test"]),
        ("keypoint_crop_class_safe", action_safety_selection, samples["test"]),
        ("box_center_balanced_max_f1", center_balanced_selection, center_samples["test"]),
        ("box_center_crop_class_safe", center_safety_selection, center_samples["test"]),
        ("keypoint_deduplicated_balanced_max_f1", deduplicated_selection, deduplicated_samples["test"]),
    ):
        action_threshold = float(selection["threshold"])
        tolerances: dict[str, Any] = {}
        for fraction in (0.05, 0.10, 0.20):
            tolerances[f"box_diagonal_fraction_{fraction:.2f}"] = evaluate_actions(
                mode_samples,
                action_threshold,
                tolerance_kind="box_diagonal_fraction",
                tolerance=fraction,
            )
        for pixels in (5, 10, 20):
            tolerances[f"pixels_{pixels}"] = evaluate_actions(
                mode_samples,
                action_threshold,
                tolerance_kind="pixels",
                tolerance=float(pixels),
            )
        action_modes[mode_name] = {
            "selection": selection,
            "test_by_tolerance": tolerances,
        }
    train_diagnostic = {
        "role": "seen_capture_date_diagnostic_using_validation_frozen_thresholds",
        "images": len(samples["train"]),
        "weed_detection": evaluate_detection(samples["train"], detection_threshold),
        "stem_action_keypoint_balanced_10pct_box_diagonal": evaluate_actions(
            samples["train"],
            float(action_balanced_selection["threshold"]),
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        ),
        "stem_action_keypoint_crop_class_safe_10pct_box_diagonal": evaluate_actions(
            samples["train"],
            float(action_safety_selection["threshold"]),
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        ),
        "stem_action_box_center_balanced_10pct_box_diagonal": evaluate_actions(
            center_samples["train"],
            float(center_balanced_selection["threshold"]),
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        ),
        "stem_action_keypoint_deduplicated_10pct_box_diagonal": evaluate_actions(
            deduplicated_samples["train"],
            float(deduplicated_selection["threshold"]),
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        ),
    }
    balanced_threshold = float(deduplicated_selection["threshold"])
    gallery = _write_gallery(
        deduplicated_samples["test"], output / "gallery", balanced_threshold
    )
    curve_path = output / "validation_precision_recall.png"
    _write_curve_plot(
        detection_curve,
        action_curve,
        detection_selection,
        action_balanced_selection,
        action_safety_selection,
        center_action_curve,
        center_balanced_selection,
        deduplicated_curve,
        deduplicated_selection,
        curve_path,
    )
    receipt = {
        "schema_version": 1,
        "protocol": "wsd_detection_stem_action_date_holdout_v1",
        "status": "research_poc_not_field_or_laser_validated",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "dataset_yaml": str(dataset_yaml),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "inference_image_size": image_size,
        "inference_batch": inference_batch,
        "split_policy": {
            "threshold_selection": "validation_capture_date_only",
            "final_evaluation": "held_out_test_capture_date_once_with_frozen_thresholds",
        },
        "validation": {
            "images": len(samples["val"]),
            "detection_selection": detection_selection,
            "action_balanced_selection": action_balanced_selection,
            "action_safety_selection": action_safety_selection,
            "box_center_balanced_selection": center_balanced_selection,
            "box_center_safety_selection": center_safety_selection,
            "deduplication_screen": deduplication_screen,
            "deduplication_selected": {
                "radius_fraction_of_smaller_predicted_box_diagonal": deduplication_fraction,
                "selection": deduplicated_selection,
            },
            "detection_curve": detection_curve,
            "action_curve": action_curve,
            "box_center_action_curve": center_action_curve,
        },
        "train_diagnostic": train_diagnostic,
        "test": {
            "images": len(samples["test"]),
            "weed_detection": evaluate_detection(samples["test"], detection_threshold),
            "stem_action_modes": action_modes,
            "offline_poc_gate": {
                "definition": "balanced test F1 >= 0.95 at <=10% weed-box-diagonal and crop-as-weed box false-fire <=0.5%; not a field/laser gate",
                "passed": bool(
                    action_modes["keypoint_deduplicated_balanced_max_f1"]["test_by_tolerance"]
                    ["box_diagonal_fraction_0.10"]["f1"] is not None
                    and action_modes["keypoint_deduplicated_balanced_max_f1"]["test_by_tolerance"]
                    ["box_diagonal_fraction_0.10"]["f1"] >= 0.95
                    and action_modes["keypoint_deduplicated_balanced_max_f1"]["test_by_tolerance"]
                    ["box_diagonal_fraction_0.10"]["crop_as_weed_false_fire"]
                    ["rate_per_action"] is not None
                    and action_modes["keypoint_deduplicated_balanced_max_f1"]["test_by_tolerance"]
                    ["box_diagonal_fraction_0.10"]["crop_as_weed_false_fire"]
                    ["rate_per_action"] <= 0.005
                ),
            },
        },
        "artifacts": {
            "output_directory": str(output),
            "validation_precision_recall_plot": str(curve_path),
            "gallery": gallery,
            "prediction_caches": {
                split: str(output / f"predictions_{split}.json")
                for split in ("train", "val", "test")
            },
        },
        "limitations": [
            "Point/footprint overlap with a crop bounding rectangle is a conservative spatial proxy, not canopy contact.",
            "No ground-sampling distance or camera-tool calibration is available; pixel errors cannot be claimed as millimetres.",
            "The downloadable WSD labelled archive is smaller than the inventory reported by the paper.",
            "Single-frame date transfer is measured; video tracking and physical kill outcome are not measured here.",
        ],
    }
    receipt_path = output / "action_metrics.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/benchmark/wsd_pose_poc_v1.yaml"))
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--image-size", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--output-name", default="action_metrics_v1")
    arguments = parser.parse_args()
    result = run(
        arguments.config,
        arguments.checkpoint,
        image_size_override=arguments.image_size,
        batch_override=arguments.batch,
        output_name=arguments.output_name,
    )
    primary = result["test"]["stem_action_modes"]["keypoint_deduplicated_balanced_max_f1"][
        "test_by_tolerance"
    ]["box_diagonal_fraction_0.10"]
    print(
        json.dumps(
            {
                "output_directory": result["artifacts"]["output_directory"],
                "weed_detection": result["test"]["weed_detection"],
                "balanced_stem_action_10pct_box_diagonal": {
                    key: primary[key]
                    for key in ("precision", "recall", "f1", "confidence_threshold")
                },
                "offline_poc_gate": result["test"]["offline_poc_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
