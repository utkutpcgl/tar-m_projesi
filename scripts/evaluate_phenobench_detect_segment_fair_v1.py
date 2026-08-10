#!/usr/bin/env python3
"""Evaluate a target-trained detection/instance-segmentation A/B for spot spray."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class GroundTruth:
    sample_id: str
    image_path: Path
    semantics_path: Path
    instances_path: Path
    weed_sizes: Mapping[int, float]
    crop_ids: frozenset[int]


@dataclass(frozen=True)
class Action:
    sample_id: str
    confidence: float
    x: int
    y: int
    target_kind: str
    target_instance_id: int | None


SIZE_BINS = (
    ("lt14", 0.0, 14.0),
    ("14_to_lt28", 14.0, 28.0),
    ("28_to_lt56", 28.0, 56.0),
    ("ge56", 56.0, math.inf),
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def release_cuda(model: Any) -> None:
    predictor = getattr(model, "predictor", None)
    backend = getattr(predictor, "model", None)
    if backend is not None and hasattr(backend, "to"):
        backend.to("cpu")
    model.to("cpu")
    model.predictor = None
    model.validator = None
    del backend, predictor
    gc.collect()
    torch.cuda.empty_cache()


def deepest_interior_point(mask: np.ndarray) -> tuple[int, int] | None:
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2 or not binary.any():
        return None
    rows, columns = np.nonzero(binary)
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    x0, x1 = int(columns.min()), int(columns.max()) + 1
    crop = binary[y0:y1, x0:x1]
    padded = np.pad(crop.astype(np.uint8), 1, mode="constant")
    distance = cv2.distanceTransform(padded, cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(distance)), distance.shape)
    return int(x) + x0 - 1, int(y) + y0 - 1


def maximum_excess_green_point(
    mask: np.ndarray, rgb: np.ndarray
) -> tuple[int, int] | None:
    """Choose the greenest pixel inside a predicted mask without using labels."""
    binary = np.asarray(mask, dtype=bool)
    image = np.asarray(rgb)
    if binary.ndim != 2 or image.shape[:2] != binary.shape or not binary.any():
        return None
    red = image[..., 0].astype(np.int16)
    green = image[..., 1].astype(np.int16)
    blue = image[..., 2].astype(np.int16)
    excess_green = 2 * green - red - blue
    scores = np.where(binary, excess_green, np.iinfo(np.int16).min)
    y, x = np.unravel_index(int(np.argmax(scores)), scores.shape)
    return int(x), int(y)


def cluster_vertical_crop_rows(
    x_centers: Sequence[float], maximum_within_row_gap_px: float
) -> tuple[float, ...]:
    """Cluster predicted crop centres into camera-aligned vertical rows."""
    if maximum_within_row_gap_px < 0:
        raise ValueError("maximum_within_row_gap_px must be non-negative")
    ordered = sorted(float(value) for value in x_centers)
    if not ordered:
        return ()
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][-1] <= maximum_within_row_gap_px:
            groups[-1].append(value)
        else:
            groups.append([value])
    return tuple(float(np.median(group)) for group in groups)


def _eligible_ids(
    semantics: np.ndarray,
    instances: np.ndarray,
    semantic_id: int,
    minimum_area_px: int,
) -> dict[int, float]:
    output: dict[int, float] = {}
    ids = np.unique(instances[semantics == semantic_id])
    for raw_id in ids:
        instance_id = int(raw_id)
        if instance_id == 0:
            continue
        mask = np.logical_and(semantics == semantic_id, instances == instance_id)
        if int(mask.sum()) < minimum_area_px:
            continue
        rows, columns = np.nonzero(mask)
        width = int(columns.max()) - int(columns.min()) + 1
        height = int(rows.max()) - int(rows.min()) + 1
        output[instance_id] = math.sqrt(width * height)
    return output


def load_ground_truth(
    membership_path: Path,
    split: str,
    minimum_area_px: int,
) -> list[GroundTruth]:
    output: list[GroundTruth] = []
    for line in membership_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["logical_split"] != split:
            continue
        semantics_path = Path(row["semantics_path"])
        instances_path = Path(row["plant_instances_path"])
        semantics = np.asarray(Image.open(semantics_path), dtype=np.uint16)
        instances = np.asarray(Image.open(instances_path), dtype=np.uint16)
        weed_sizes = _eligible_ids(semantics, instances, 2, minimum_area_px)
        crop_sizes = _eligible_ids(semantics, instances, 1, minimum_area_px)
        if len(weed_sizes) != int(row["eligible_weed_instances"]):
            raise ValueError(f"Weed membership drift for {row['sample_id']}")
        if len(crop_sizes) != int(row["eligible_crop_instances"]):
            raise ValueError(f"Crop membership drift for {row['sample_id']}")
        output.append(
            GroundTruth(
                sample_id=str(row["sample_id"]),
                image_path=Path(row["image_path"]),
                semantics_path=semantics_path,
                instances_path=instances_path,
                weed_sizes=weed_sizes,
                crop_ids=frozenset(crop_sizes),
            )
        )
    if not output:
        raise ValueError(f"No ground truth records for split={split}")
    return output


def classify_point(
    x: int,
    y: int,
    semantics: np.ndarray,
    instances: np.ndarray,
    truth: GroundTruth,
) -> tuple[str, int | None]:
    height, width = semantics.shape
    x = min(max(int(x), 0), width - 1)
    y = min(max(int(y), 0), height - 1)
    semantic_id = int(semantics[y, x])
    instance_id = int(instances[y, x])
    if semantic_id == 2 and instance_id in truth.weed_sizes:
        return "weed", instance_id
    if semantic_id == 1 and instance_id in truth.crop_ids:
        return "crop", instance_id
    if semantic_id in {3, 4}:
        return "ignore", instance_id or None
    if semantic_id in {1, 2}:
        return "ignore", instance_id or None
    return "soil", None


def _box_center(box: Sequence[float], shape: tuple[int, int]) -> tuple[int, int]:
    height, width = shape
    x = int(round((float(box[0]) + float(box[2])) / 2.0))
    y = int(round((float(box[1]) + float(box[3])) / 2.0))
    return min(max(x, 0), width - 1), min(max(y, 0), height - 1)


def _mask_interior_from_box_crop(
    mask: torch.Tensor,
    box: Sequence[float],
    target_shape: tuple[int, int],
) -> tuple[int, int] | None:
    height, width = target_shape
    mask_height, mask_width = (int(value) for value in mask.shape)
    if (mask_height, mask_width) != target_shape:
        full = mask.ge(0.5).to(torch.uint8).cpu().numpy()
        resized = cv2.resize(
            full,
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        return deepest_interior_point(resized)
    x0 = max(0, int(math.floor(float(box[0]))) - 1)
    y0 = max(0, int(math.floor(float(box[1]))) - 1)
    x1 = min(width, int(math.ceil(float(box[2]))) + 1)
    y1 = min(height, int(math.ceil(float(box[3]))) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = mask[y0:y1, x0:x1].ge(0.5).to(torch.uint8).cpu().numpy()
    local = deepest_interior_point(crop)
    return None if local is None else (local[0] + x0, local[1] + y0)


def _mask_excess_green_from_box_crop(
    mask: torch.Tensor,
    box: Sequence[float],
    target_shape: tuple[int, int],
    rgb: np.ndarray,
) -> tuple[int, int] | None:
    height, width = target_shape
    mask_height, mask_width = (int(value) for value in mask.shape)
    if (mask_height, mask_width) != target_shape:
        full = mask.ge(0.5).to(torch.uint8).cpu().numpy()
        resized = cv2.resize(full, (width, height), interpolation=cv2.INTER_NEAREST)
        return maximum_excess_green_point(resized, rgb)
    x0 = max(0, int(math.floor(float(box[0]))) - 1)
    y0 = max(0, int(math.floor(float(box[1]))) - 1)
    x1 = min(width, int(math.ceil(float(box[2]))) + 1)
    y1 = min(height, int(math.ceil(float(box[3]))) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    binary = mask[y0:y1, x0:x1].ge(0.5).to(torch.uint8).cpu().numpy()
    local = maximum_excess_green_point(binary, rgb[y0:y1, x0:x1])
    return None if local is None else (local[0] + x0, local[1] + y0)


def _mask_at_target(
    mask: torch.Tensor, target_shape: tuple[int, int]
) -> np.ndarray:
    height, width = target_shape
    binary = mask.ge(0.5).to(torch.uint8).cpu().numpy()
    if binary.shape != target_shape:
        binary = cv2.resize(binary, (width, height), interpolation=cv2.INTER_NEAREST)
    return binary.astype(bool, copy=False)


def _action(
    truth: GroundTruth,
    confidence: float,
    point: tuple[int, int],
    semantics: np.ndarray,
    instances: np.ndarray,
) -> Action:
    target_kind, target_id = classify_point(
        point[0], point[1], semantics, instances, truth
    )
    return Action(
        sample_id=truth.sample_id,
        confidence=float(confidence),
        x=int(point[0]),
        y=int(point[1]),
        target_kind=target_kind,
        target_instance_id=target_id,
    )


def infer_actions(
    model: Any,
    arm_name: str,
    records: Sequence[GroundTruth],
    inference: Mapping[str, Any],
) -> tuple[dict[str, dict[str, list[Action]]], dict[str, Any]]:
    row_half_widths = tuple(
        int(value) for value in inference.get("crop_row_half_widths_px", ())
    )
    if any(value < 0 for value in row_half_widths):
        raise ValueError("crop_row_half_widths_px cannot be negative")
    methods = (
        ("detect_box_center",)
        if arm_name == "detect"
        else (
            "segment_deepest_interior",
            "segment_max_excess_green",
            "segment_crop_safe_excess_green",
            "segment_box_center",
        )
        + tuple(
            f"segment_row_safe_excess_green_w{width}" for width in row_half_widths
        )
    )
    output = {method: {} for method in methods}
    inference_ms: list[float] = []
    preprocess_ms: list[float] = []
    framework_postprocess_ms: list[float] = []
    postprocess_ms: list[float] = []
    prediction_count = 0
    seen: set[str] = set()

    def consume(truth: GroundTruth, result: Any) -> None:
        nonlocal prediction_count
        seen.add(truth.sample_id)
        rgb = np.asarray(Image.open(truth.image_path).convert("RGB"), dtype=np.uint8)
        semantics = np.asarray(Image.open(truth.semantics_path), dtype=np.uint16)
        instances = np.asarray(Image.open(truth.instances_path), dtype=np.uint16)
        for method in methods:
            output[method][truth.sample_id] = []
        started = time.perf_counter()
        boxes = result.boxes
        if boxes is None:
            postprocess_ms.append((time.perf_counter() - started) * 1000.0)
            preprocess_ms.append(float(result.speed.get("preprocess", math.nan)))
            inference_ms.append(float(result.speed.get("inference", math.nan)))
            framework_postprocess_ms.append(
                float(result.speed.get("postprocess", math.nan))
            )
            return
        xyxy = boxes.xyxy.detach().cpu().numpy()
        confidences = boxes.conf.detach().cpu().numpy()
        classes = boxes.cls.detach().cpu().numpy().astype(np.int64)
        mask_tensor = (
            result.masks.data
            if arm_name == "segment" and result.masks is not None
            else None
        )
        crop_safety_mask = np.zeros(semantics.shape, dtype=bool)
        crop_row_x_centers: list[float] = []
        if mask_tensor is not None:
            crop_safety_confidence = float(inference.get("crop_safety_confidence", 0.25))
            for crop_index, (crop_confidence, crop_class_id) in enumerate(
                zip(confidences, classes, strict=True)
            ):
                if (
                    int(crop_class_id) == 1
                    and float(crop_confidence) >= crop_safety_confidence
                    and crop_index < len(mask_tensor)
                ):
                    crop_safety_mask |= _mask_at_target(
                        mask_tensor[crop_index], semantics.shape
                    )
                    crop_box = xyxy[crop_index]
                    crop_row_x_centers.append(
                        (float(crop_box[0]) + float(crop_box[2])) / 2.0
                    )
            crop_safety_dilation = int(inference.get("crop_safety_dilation_px", 0))
            if crop_safety_dilation > 0 and crop_safety_mask.any():
                diameter = 2 * crop_safety_dilation + 1
                kernel = cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (diameter, diameter)
                )
                crop_safety_mask = cv2.dilate(
                    crop_safety_mask.astype(np.uint8), kernel
                ).astype(bool)
        crop_row_centers = cluster_vertical_crop_rows(
            crop_row_x_centers,
            float(inference.get("crop_row_cluster_gap_px", 96)),
        )
        for index, (box, confidence, class_id) in enumerate(
            zip(xyxy, confidences, classes, strict=True)
        ):
            if int(class_id) != 0:
                continue
            prediction_count += 1
            center = _box_center(box, semantics.shape)
            if arm_name == "detect":
                output["detect_box_center"][truth.sample_id].append(
                    _action(truth, float(confidence), center, semantics, instances)
                )
                continue
            output["segment_box_center"][truth.sample_id].append(
                _action(truth, float(confidence), center, semantics, instances)
            )
            interior = (
                _mask_interior_from_box_crop(mask_tensor[index], box, semantics.shape)
                if mask_tensor is not None and index < len(mask_tensor)
                else None
            )
            output["segment_deepest_interior"][truth.sample_id].append(
                _action(
                    truth,
                    float(confidence),
                    interior if interior is not None else center,
                    semantics,
                    instances,
                )
            )
            greenest = (
                _mask_excess_green_from_box_crop(
                    mask_tensor[index], box, semantics.shape, rgb
                )
                if mask_tensor is not None and index < len(mask_tensor)
                else None
            )
            output["segment_max_excess_green"][truth.sample_id].append(
                _action(
                    truth,
                    float(confidence),
                    greenest if greenest is not None else center,
                    semantics,
                    instances,
                )
            )
            safe_mask = (
                np.logical_and(
                    _mask_at_target(mask_tensor[index], semantics.shape),
                    ~crop_safety_mask,
                )
                if mask_tensor is not None and index < len(mask_tensor)
                else None
            )
            safe_greenest = (
                maximum_excess_green_point(safe_mask, rgb)
                if safe_mask is not None
                else None
            )
            if safe_greenest is not None:
                output["segment_crop_safe_excess_green"][truth.sample_id].append(
                    _action(
                        truth,
                        float(confidence),
                        safe_greenest,
                        semantics,
                        instances,
                    )
                )
                for row_half_width in row_half_widths:
                    if all(
                        abs(float(safe_greenest[0]) - row_center) > row_half_width
                        for row_center in crop_row_centers
                    ):
                        output[
                            f"segment_row_safe_excess_green_w{row_half_width}"
                        ][truth.sample_id].append(
                            _action(
                                truth,
                                float(confidence),
                                safe_greenest,
                                semantics,
                                instances,
                            )
                        )
        postprocess_ms.append((time.perf_counter() - started) * 1000.0)
        preprocess_ms.append(float(result.speed.get("preprocess", math.nan)))
        inference_ms.append(float(result.speed.get("inference", math.nan)))
        framework_postprocess_ms.append(
            float(result.speed.get("postprocess", math.nan))
        )

    chunk_size = int(inference["chunk_size"])
    if chunk_size <= 0:
        raise ValueError("inference.chunk_size must be positive")
    for start in range(0, len(records), chunk_size):
        chunk_records = records[start : start + chunk_size]
        results = model.predict(
            source=[str(record.image_path) for record in chunk_records],
            stream=True,
            conf=float(inference["confidence_floor"]),
            iou=float(inference["nms_iou"]),
            imgsz=int(inference["image_size"]),
            batch=int(inference["batch"]),
            max_det=int(inference["max_detections"]),
            device=int(inference["device"]),
            retina_masks=True,
            verbose=False,
        )
        for truth, result in zip(chunk_records, results, strict=True):
            consume(truth, result)
        del result, results, truth
        release_cuda(model)
    if seen != {record.sample_id for record in records}:
        raise ValueError("Inference did not return every requested image")
    timing = {
        "images": len(records),
        "weed_predictions_at_confidence_floor": prediction_count,
        "model_preprocess_ms_per_image_mean": float(np.nanmean(preprocess_ms)),
        "model_inference_ms_per_image_mean": float(np.nanmean(inference_ms)),
        "framework_postprocess_ms_per_image_mean": float(
            np.nanmean(framework_postprocess_ms)
        ),
        "action_postprocess_ms_per_image_mean": float(np.mean(postprocess_ms)),
        "batch": int(inference["batch"]),
        "chunk_size": chunk_size,
    }
    return output, timing


def _size_bin(size: float) -> str:
    for name, lower, upper in SIZE_BINS:
        if lower <= size < upper:
            return name
    raise AssertionError(size)


def _rates(counts: Mapping[str, int]) -> dict[str, float | int]:
    tp = int(counts["tp"])
    fp = int(counts["fp"])
    fn = int(counts["fn"])
    attempts = tp + fp
    precision = tp / attempts if attempts else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        **{key: int(value) for key, value in counts.items()},
        "attempted_actions": attempts,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "crop_collision_rate_per_attempt": (
            int(counts["crop_collision"]) / attempts if attempts else 0.0
        ),
        "soil_action_rate_per_attempt": (
            int(counts["soil_action"]) / attempts if attempts else 0.0
        ),
    }


def evaluate_actions(
    actions_by_sample: Mapping[str, Sequence[Action]],
    records: Sequence[GroundTruth],
    threshold: float,
    *,
    include_per_sample: bool = False,
) -> dict[str, Any]:
    totals = {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "crop_collision": 0,
        "soil_action": 0,
        "duplicate_action": 0,
        "ignored_action": 0,
    }
    size_totals = {name: {"matched": 0, "total": 0} for name, _, _ in SIZE_BINS}
    per_sample: dict[str, dict[str, Any]] = {}
    for truth in records:
        counts = {key: 0 for key in totals}
        matched: set[int] = set()
        for instance_id, size in truth.weed_sizes.items():
            size_totals[_size_bin(size)]["total"] += 1
        actions = sorted(
            actions_by_sample.get(truth.sample_id, ()),
            key=lambda action: action.confidence,
            reverse=True,
        )
        for action in actions:
            if action.confidence < threshold:
                continue
            if action.target_kind == "ignore":
                counts["ignored_action"] += 1
                continue
            if action.target_kind == "weed":
                instance_id = int(action.target_instance_id)
                if instance_id not in matched:
                    matched.add(instance_id)
                    counts["tp"] += 1
                else:
                    counts["fp"] += 1
                    counts["duplicate_action"] += 1
            else:
                counts["fp"] += 1
                if action.target_kind == "crop":
                    counts["crop_collision"] += 1
                else:
                    counts["soil_action"] += 1
        counts["fn"] = len(truth.weed_sizes) - len(matched)
        for instance_id in matched:
            size_totals[_size_bin(float(truth.weed_sizes[instance_id]))]["matched"] += 1
        for key in totals:
            totals[key] += counts[key]
        if include_per_sample:
            per_sample[truth.sample_id] = {
                **_rates(counts),
                "gt_weeds": len(truth.weed_sizes),
                "small_gt_weeds_lt28": sum(
                    size < 28.0 for size in truth.weed_sizes.values()
                ),
            }
    size_recall = {
        name: {
            **values,
            "recall": values["matched"] / values["total"] if values["total"] else None,
        }
        for name, values in size_totals.items()
    }
    result: dict[str, Any] = {
        "threshold": float(threshold),
        **_rates(totals),
        "recall_by_sqrt_gt_box_area_px": size_recall,
    }
    if include_per_sample:
        result["per_sample"] = per_sample
    return result


def threshold_curve(
    actions_by_sample: Mapping[str, Sequence[Action]],
    records: Sequence[GroundTruth],
    thresholds: Iterable[float],
) -> list[dict[str, Any]]:
    return [
        evaluate_actions(actions_by_sample, records, float(threshold))
        for threshold in thresholds
    ]


def select_threshold(curve: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = max(
        curve,
        key=lambda item: (
            float(item["f1"]),
            -float(item["crop_collision_rate_per_attempt"]),
            float(item["precision"]),
            float(item["recall"]),
            float(item["threshold"]),
        ),
    )
    recall_candidates = [item for item in curve if float(item["recall"]) >= 0.95]
    recall_95 = (
        max(
            recall_candidates,
            key=lambda item: (
                float(item["precision"]),
                -float(item["crop_collision_rate_per_attempt"]),
                float(item["f1"]),
                float(item["threshold"]),
            ),
        )
        if recall_candidates
        else max(
            curve,
            key=lambda item: (
                float(item["recall"]),
                float(item["precision"]),
                -float(item["crop_collision_rate_per_attempt"]),
            ),
        )
    )
    return {
        "balanced_max_f1": dict(selected),
        "recall_95": {
            "attainable_on_validation": bool(recall_candidates),
            "selection": dict(recall_95),
        },
    }


def paired_bootstrap_f1_difference(
    detection_per_sample: Mapping[str, Mapping[str, Any]],
    segmentation_per_sample: Mapping[str, Mapping[str, Any]],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    sample_ids = sorted(set(detection_per_sample) & set(segmentation_per_sample))
    if not sample_ids:
        raise ValueError("No paired samples for bootstrap")
    keys = ("tp", "fp", "fn")
    detection = np.asarray(
        [[detection_per_sample[sample][key] for key in keys] for sample in sample_ids],
        dtype=np.float64,
    )
    segmentation = np.asarray(
        [[segmentation_per_sample[sample][key] for key in keys] for sample in sample_ids],
        dtype=np.float64,
    )

    def f1(rows: np.ndarray) -> float:
        tp, fp, fn = rows.sum(axis=0)
        denominator = 2.0 * tp + fp + fn
        return float(2.0 * tp / denominator) if denominator else 0.0

    rng = np.random.default_rng(seed)
    differences = np.empty(iterations, dtype=np.float64)
    for index in range(iterations):
        draw = rng.integers(0, len(sample_ids), size=len(sample_ids))
        differences[index] = f1(segmentation[draw]) - f1(detection[draw])
    return {
        "definition": "segment_deepest_interior F1 minus detect_box_center F1; paired image bootstrap",
        "iterations": int(iterations),
        "seed": int(seed),
        "median_difference": float(np.median(differences)),
        "ci95": [
            float(np.percentile(differences, 2.5)),
            float(np.percentile(differences, 97.5)),
        ],
        "probability_segment_higher": float(np.mean(differences > 0.0)),
    }


def _binary_metric(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
    dice = 2.0 * tp / (2.0 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {
        "tp_pixels": int(tp),
        "fp_pixels": int(fp),
        "fn_pixels": int(fn),
        "precision": precision,
        "recall": recall,
        "iou": iou,
        "dice": dice,
    }


def evaluate_segment_tissue(
    model: Any,
    records: Sequence[GroundTruth],
    threshold: float,
    inference: Mapping[str, Any],
) -> dict[str, Any]:
    totals = {"weed": [0, 0, 0], "crop": [0, 0, 0]}

    def consume(truth: GroundTruth, result: Any) -> None:
        semantics = np.asarray(Image.open(truth.semantics_path), dtype=np.uint16)
        instances = np.asarray(Image.open(truth.instances_path), dtype=np.uint16)
        valid = np.logical_not(np.isin(semantics, [3, 4]))
        eligible_weed = np.isin(instances, list(truth.weed_sizes))
        eligible_crop = np.isin(instances, list(truth.crop_ids))
        valid &= np.logical_not(np.logical_and(semantics == 2, ~eligible_weed))
        valid &= np.logical_not(np.logical_and(semantics == 1, ~eligible_crop))
        predicted = {
            "weed": np.zeros(semantics.shape, dtype=bool),
            "crop": np.zeros(semantics.shape, dtype=bool),
        }
        if result.boxes is not None and result.masks is not None:
            classes = result.boxes.cls.detach().cpu().numpy().astype(np.int64)
            masks = result.masks.data.ge(0.5).to(torch.uint8).cpu().numpy()
            for class_id, raw_mask in zip(classes, masks, strict=True):
                mask = raw_mask
                if mask.shape != semantics.shape:
                    mask = cv2.resize(
                        mask.astype(np.float32),
                        (semantics.shape[1], semantics.shape[0]),
                        interpolation=cv2.INTER_NEAREST,
                    )
                predicted["weed" if int(class_id) == 0 else "crop"] |= mask >= 0.5
        targets = {
            "weed": np.logical_and(semantics == 2, eligible_weed),
            "crop": np.logical_and(semantics == 1, eligible_crop),
        }
        for name in ("weed", "crop"):
            pred = np.logical_and(predicted[name], valid)
            target = np.logical_and(targets[name], valid)
            totals[name][0] += int(np.logical_and(pred, target).sum())
            totals[name][1] += int(np.logical_and(pred, ~target & valid).sum())
            totals[name][2] += int(np.logical_and(~pred & valid, target).sum())

    chunk_size = int(inference["chunk_size"])
    for start in range(0, len(records), chunk_size):
        chunk_records = records[start : start + chunk_size]
        results = model.predict(
            source=[str(record.image_path) for record in chunk_records],
            stream=True,
            conf=float(threshold),
            iou=float(inference["nms_iou"]),
            imgsz=int(inference["image_size"]),
            batch=int(inference["batch"]),
            max_det=int(inference["max_detections"]),
            device=int(inference["device"]),
            retina_masks=True,
            verbose=False,
        )
        for truth, result in zip(chunk_records, results, strict=True):
            consume(truth, result)
        del result, results, truth
        release_cuda(model)
    metrics = {
        name: _binary_metric(*values) for name, values in totals.items()
    }
    metrics["macro_iou"] = float(
        np.mean([metrics["weed"]["iou"], metrics["crop"]["iou"]])
    )
    metrics["threshold"] = float(threshold)
    return metrics


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(path), size=size)


def _blend_mask(image: Image.Image, mask: np.ndarray, color: tuple[int, int, int]) -> None:
    overlay = Image.new("RGB", image.size, color)
    alpha = Image.fromarray(mask.astype(np.uint8) * 92)
    image.paste(overlay, (0, 0), alpha)


def _draw_point(draw: ImageDraw.ImageDraw, point: tuple[int, int], correct: bool) -> None:
    color = (34, 197, 94) if correct else (239, 68, 68)
    x, y = point
    radius = 14
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="white", width=3)


def render_example(
    detection_model: Any,
    segment_model: Any,
    truth: GroundTruth,
    detection_threshold: float,
    segment_threshold: float,
    inference: Mapping[str, Any],
    output_path: Path,
) -> None:
    rgb = Image.open(truth.image_path).convert("RGB")
    semantics = np.asarray(Image.open(truth.semantics_path), dtype=np.uint16)
    instances = np.asarray(Image.open(truth.instances_path), dtype=np.uint16)
    panels = [rgb.copy(), rgb.copy(), rgb.copy()]
    gt_weed = np.logical_and(semantics == 2, np.isin(instances, list(truth.weed_sizes)))
    gt_crop = np.logical_and(semantics == 1, np.isin(instances, list(truth.crop_ids)))
    _blend_mask(panels[0], gt_crop, (34, 197, 94))
    _blend_mask(panels[0], gt_weed, (168, 85, 247))

    common = {
        "source": str(truth.image_path),
        "imgsz": int(inference["image_size"]),
        "device": int(inference["device"]),
        "iou": float(inference["nms_iou"]),
        "max_det": int(inference["max_detections"]),
        "retina_masks": True,
        "verbose": False,
    }
    detection = detection_model.predict(conf=detection_threshold, **common)[0]
    segment = segment_model.predict(conf=segment_threshold, **common)[0]
    detection_draw = ImageDraw.Draw(panels[1])
    if detection.boxes is not None:
        for box, confidence, class_id in zip(
            detection.boxes.xyxy.detach().cpu().numpy(),
            detection.boxes.conf.detach().cpu().numpy(),
            detection.boxes.cls.detach().cpu().numpy().astype(np.int64),
            strict=True,
        ):
            color = (249, 115, 22) if int(class_id) == 0 else (34, 197, 94)
            detection_draw.rectangle(tuple(float(value) for value in box), outline=color, width=4)
            if int(class_id) == 0:
                point = _box_center(box, semantics.shape)
                kind, _ = classify_point(*point, semantics, instances, truth)
                _draw_point(detection_draw, point, kind == "weed")
    if segment.boxes is not None and segment.masks is not None:
        classes = segment.boxes.cls.detach().cpu().numpy().astype(np.int64)
        masks = segment.masks.data.detach().cpu().numpy()
        for class_id, raw_mask in zip(classes, masks, strict=True):
            mask = raw_mask
            if mask.shape != semantics.shape:
                mask = cv2.resize(
                    mask.astype(np.float32),
                    (semantics.shape[1], semantics.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )
            binary = mask >= 0.5
            _blend_mask(
                panels[2], binary, (249, 115, 22) if int(class_id) == 0 else (34, 197, 94)
            )
        segment_draw = ImageDraw.Draw(panels[2])
        for class_id, raw_mask in zip(classes, masks, strict=True):
            if int(class_id) != 0:
                continue
            mask = raw_mask
            if mask.shape != semantics.shape:
                mask = cv2.resize(
                    mask.astype(np.float32),
                    (semantics.shape[1], semantics.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )
            point = deepest_interior_point(mask >= 0.5)
            if point is not None:
                kind, _ = classify_point(*point, semantics, instances, truth)
                _draw_point(segment_draw, point, kind == "weed")

    panel_size = 512
    resized = [panel.resize((panel_size, panel_size), Image.Resampling.LANCZOS) for panel in panels]
    canvas = Image.new("RGB", (panel_size * 3, 650), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 12), f"{truth.sample_id} | gercek PhenoBench test parcasi", fill="#111827", font=_font(24, True))
    titles = ("Gercek etiket", "Detection: kutu merkezi", "Segmentation: guvenli maske ici")
    for index, (panel, title) in enumerate(zip(resized, titles, strict=True)):
        left = index * panel_size
        draw.text((left + 12, 52), title, fill="#111827", font=_font(20, True))
        canvas.paste(panel, (left, 82))
    draw.text(
        (24, 607),
        "Renk: yesil=mahsul, mor=GT ot, turuncu=tahmin ot | Nokta: yesil=dogru ot temasi, kirmizi=hatali",
        fill="#111827",
        font=_font(18),
    )
    canvas.save(output_path, quality=94)


def choose_gallery_samples(
    records: Sequence[GroundTruth],
    detection_per_sample: Mapping[str, Mapping[str, Any]],
    segment_per_sample: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    candidates = [record.sample_id for record in records if record.weed_sizes]
    if not candidates:
        return []
    average = {
        sample: (
            float(detection_per_sample[sample]["f1"])
            + float(segment_per_sample[sample]["f1"])
        )
        / 2.0
        for sample in candidates
    }
    median_value = float(np.median(list(average.values())))
    output: list[str] = []

    def add_first(ranked: Sequence[str]) -> None:
        for sample in ranked:
            if sample not in output:
                output.append(sample)
                return

    add_first(
        sorted(
            candidates,
            key=lambda sample: (
                average[sample], detection_per_sample[sample]["gt_weeds"]
            ),
            reverse=True,
        )
    )
    add_first(
        sorted(
            candidates,
            key=lambda sample: (
                average[sample], -detection_per_sample[sample]["gt_weeds"]
            ),
        )
    )
    add_first(
        sorted(
            candidates,
            key=lambda sample: float(segment_per_sample[sample]["f1"])
            - float(detection_per_sample[sample]["f1"]),
            reverse=True,
        )
    )
    add_first(
        sorted(
            candidates,
            key=lambda sample: float(detection_per_sample[sample]["f1"])
            - float(segment_per_sample[sample]["f1"]),
            reverse=True,
        )
    )
    add_first(
        sorted(
            candidates,
            key=lambda sample: detection_per_sample[sample]["small_gt_weeds_lt28"],
            reverse=True,
        )
    )
    add_first(
        sorted(candidates, key=lambda sample: abs(average[sample] - median_value))
    )
    return output


def _write_actions(path: Path, actions: Mapping[str, Sequence[Action]]) -> None:
    lines = []
    for sample_id in sorted(actions):
        for action in sorted(actions[sample_id], key=lambda item: item.confidence, reverse=True):
            lines.append(json.dumps(asdict(action), sort_keys=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _locked_arm(
    data_root: Path, arm_name: str, arm: Mapping[str, Any]
) -> tuple[Path, Path, Path, dict[str, Any]]:
    receipt_path = _resolve(data_root, arm["training_receipt"])
    if sha256(receipt_path) != str(arm["training_receipt_sha256"]):
        raise ValueError(f"{arm_name} training receipt SHA-256 mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("arm") != arm_name or receipt.get("status") != "fair_training_arm_complete_test_not_touched":
        raise ValueError(f"{arm_name} training receipt contract failed")
    checkpoint = _resolve(data_root, arm["fixed_final_checkpoint"])
    dataset_yaml = _resolve(data_root, arm["dataset_yaml"])
    if sha256(checkpoint) != str(arm["fixed_final_checkpoint_sha256"]):
        raise ValueError(f"{arm_name} final checkpoint SHA-256 mismatch")
    if sha256(dataset_yaml) != str(arm["dataset_yaml_sha256"]):
        raise ValueError(f"{arm_name} dataset YAML SHA-256 mismatch")
    if receipt["artifacts"]["fixed_final_checkpoint_sha256"] != sha256(checkpoint):
        raise ValueError(f"{arm_name} receipt/checkpoint mismatch")
    return receipt_path, checkpoint, dataset_yaml, receipt


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {
            "clearml": False,
            "comet": False,
            "dvc": False,
            "hub": False,
            "mlflow": False,
            "neptune": False,
            "wandb": False,
        }
    )
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the locked evaluation")
    dataset_receipt_path = _resolve(data_root, config["dataset_receipt"])
    if sha256(dataset_receipt_path) != str(config["dataset_receipt_sha256"]):
        raise ValueError("Dataset receipt SHA-256 mismatch")
    dataset_receipt = json.loads(dataset_receipt_path.read_text(encoding="utf-8"))
    membership_path = Path(dataset_receipt["provenance"]["membership"])
    if sha256(membership_path) != dataset_receipt["provenance"]["membership_sha256"]:
        raise ValueError("Membership SHA-256 mismatch")
    minimum_area = int(dataset_receipt["label_contract"]["minimum_full_instance_area_px"])
    val_records = load_ground_truth(membership_path, "val", minimum_area)
    test_records = load_ground_truth(membership_path, "test", minimum_area)
    if len(val_records) != int(dataset_receipt["counts"]["val"]["images"]):
        raise ValueError("Validation image count drift")
    if len(test_records) != int(dataset_receipt["counts"]["test"]["images"]):
        raise ValueError("Test image count drift")

    locked: dict[str, dict[str, Any]] = {}
    models: dict[str, Any] = {}
    for arm_name in ("detect", "segment"):
        receipt_path, checkpoint, dataset_yaml, receipt = _locked_arm(
            data_root, arm_name, config["arms"][arm_name]
        )
        model = YOLO(str(checkpoint))
        trained_parameter_count = sum(
            parameter.numel() for parameter in model.model.parameters()
        )
        receipt_training = receipt["training"]
        if "pretrained_parameter_count" in receipt_training:
            if int(receipt_training["parameter_count"]) != trained_parameter_count:
                raise ValueError(f"{arm_name} trained parameter-count mismatch")
            pretrained_parameter_count = int(
                receipt_training["pretrained_parameter_count"]
            )
        else:
            # v1 receipts produced by the already-running benchmark recorded
            # the COCO-head count before nc=2 override.  The locked final
            # count above is recomputed from checkpoint bytes.
            pretrained_parameter_count = int(receipt_training["parameter_count"])
        locked[arm_name] = {
            "training_receipt": str(receipt_path),
            "training_receipt_sha256": sha256(receipt_path),
            "fixed_final_checkpoint": str(checkpoint),
            "fixed_final_checkpoint_sha256": sha256(checkpoint),
            "dataset_yaml": str(dataset_yaml),
            "dataset_yaml_sha256": sha256(dataset_yaml),
            "trained_parameter_count": trained_parameter_count,
            "pretrained_parameter_count": pretrained_parameter_count,
            "training_elapsed_seconds": receipt["runtime"]["elapsed_seconds"],
        }
        models[arm_name] = model

    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    inference = config["inference"]
    thresholds = np.arange(
        float(config["thresholds"]["start"]),
        float(config["thresholds"]["stop"]) + 1e-9,
        float(config["thresholds"]["step"]),
    )

    validation_actions: dict[str, dict[str, list[Action]]] = {}
    timing: dict[str, dict[str, Any]] = {"validation": {}, "test": {}}
    for arm_name in ("detect", "segment"):
        actions, arm_timing = infer_actions(
            models[arm_name], arm_name, val_records, inference
        )
        validation_actions.update(actions)
        timing["validation"][arm_name] = arm_timing
        release_cuda(models[arm_name])
    calibration = {
        method: {
            "selection": select_threshold(
                threshold_curve(actions, val_records, thresholds)
            )
        }
        for method, actions in validation_actions.items()
    }
    for method, payload in calibration.items():
        payload["threshold_grid"] = {
            "start": float(thresholds[0]),
            "stop": float(thresholds[-1]),
            "step": float(config["thresholds"]["step"]),
        }
    calibration_payload = {
        "status": "locked_before_test_inference",
        "config_sha256": sha256(config_path),
        "calibration": calibration,
    }
    calibration_path = output / "locked_validation_calibration.json"
    calibration_path.write_text(
        json.dumps(calibration_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    test_actions: dict[str, dict[str, list[Action]]] = {}
    for arm_name in ("detect", "segment"):
        actions, arm_timing = infer_actions(
            models[arm_name], arm_name, test_records, inference
        )
        test_actions.update(actions)
        timing["test"][arm_name] = arm_timing
        release_cuda(models[arm_name])

    validation_metrics: dict[str, Any] = {}
    test_metrics: dict[str, Any] = {}
    test_recall_95_policy: dict[str, Any] = {}
    for method in validation_actions:
        threshold = float(
            calibration[method]["selection"]["balanced_max_f1"]["threshold"]
        )
        validation_metrics[method] = evaluate_actions(
            validation_actions[method], val_records, threshold, include_per_sample=True
        )
        test_metrics[method] = evaluate_actions(
            test_actions[method], test_records, threshold, include_per_sample=True
        )
        recall_threshold = float(
            calibration[method]["selection"]["recall_95"]["selection"]["threshold"]
        )
        test_recall_95_policy[method] = {
            "validation_target_attainable": bool(
                calibration[method]["selection"]["recall_95"][
                    "attainable_on_validation"
                ]
            ),
            "metrics": evaluate_actions(
                test_actions[method], test_records, recall_threshold
            ),
        }

    action_dir = output / "raw_actions"
    action_dir.mkdir()
    action_hashes: dict[str, str] = {}
    for split_name, methods in (
        ("validation", validation_actions),
        ("test", test_actions),
    ):
        for method, actions in methods.items():
            path = action_dir / f"{split_name}_{method}.jsonl"
            _write_actions(path, actions)
            action_hashes[path.name] = sha256(path)

    builtin: dict[str, Any] = {}
    for arm_name in ("detect", "segment"):
        metrics = models[arm_name].val(
            data=locked[arm_name]["dataset_yaml"],
            split="test",
            conf=0.001,
            iou=float(inference["nms_iou"]),
            imgsz=int(inference["image_size"]),
            batch=int(inference["batch"]),
            workers=int(inference["workers"]),
            device=int(inference["device"]),
            max_det=int(inference["max_detections"]),
            project=str(output),
            name=f"{arm_name}_builtin_test",
            exist_ok=False,
            plots=True,
            verbose=False,
        )
        builtin[arm_name] = {
            "results": _plain(getattr(metrics, "results_dict", {})),
            "speed_ms_per_image": _plain(getattr(metrics, "speed", {})),
        }
        release_cuda(models[arm_name])

    segment_threshold = float(
        calibration["segment_deepest_interior"]["selection"]["balanced_max_f1"]["threshold"]
    )
    tissue = evaluate_segment_tissue(
        models["segment"], test_records, segment_threshold, inference
    )
    release_cuda(models["segment"])
    bootstrap = paired_bootstrap_f1_difference(
        test_metrics["detect_box_center"]["per_sample"],
        test_metrics["segment_deepest_interior"]["per_sample"],
        iterations=int(config["bootstrap"]["iterations"]),
        seed=int(config["bootstrap"]["seed"]),
    )

    detector = test_metrics["detect_box_center"]
    segmenter = test_metrics["segment_deepest_interior"]
    gate_config = config["segmentation_preference_gate"]
    latency_ratio = (
        float(timing["test"]["segment"]["model_preprocess_ms_per_image_mean"])
        + float(timing["test"]["segment"]["model_inference_ms_per_image_mean"])
        + float(
            timing["test"]["segment"]["framework_postprocess_ms_per_image_mean"]
        )
        + float(timing["test"]["segment"]["action_postprocess_ms_per_image_mean"])
    ) / max(
        1e-9,
        float(timing["test"]["detect"]["model_preprocess_ms_per_image_mean"])
        + float(timing["test"]["detect"]["model_inference_ms_per_image_mean"])
        + float(
            timing["test"]["detect"]["framework_postprocess_ms_per_image_mean"]
        )
        + float(timing["test"]["detect"]["action_postprocess_ms_per_image_mean"]),
    )
    gate_checks = {
        "f1_within_allowed_drop": float(segmenter["f1"])
        >= float(detector["f1"]) - float(gate_config["maximum_f1_drop"]),
        "recall_within_allowed_drop": float(segmenter["recall"])
        >= float(detector["recall"]) - float(gate_config["maximum_recall_drop"]),
        "crop_collision_within_allowed_increase": float(
            segmenter["crop_collision_rate_per_attempt"]
        )
        <= float(detector["crop_collision_rate_per_attempt"])
        + float(gate_config["maximum_crop_collision_rate_increase"]),
        "latency_ratio_allowed": latency_ratio <= float(gate_config["maximum_latency_ratio"]),
    }
    gate = {
        "checks": gate_checks,
        "passed": all(gate_checks.values()),
        "latency_ratio_segment_over_detect": latency_ratio,
        "decision_if_passed": "prefer segmentation as extensible foundation",
        "decision_if_failed": "prefer detection for current spot-spray PoC; retain segmentation as future-intervention branch",
    }

    gallery_dir = output / "gallery"
    gallery_dir.mkdir()
    record_by_id = {record.sample_id: record for record in test_records}
    gallery_samples = choose_gallery_samples(
        test_records,
        test_metrics["detect_box_center"]["per_sample"],
        test_metrics["segment_deepest_interior"]["per_sample"],
    )
    gallery_files: list[str] = []
    detection_threshold = float(
        calibration["detect_box_center"]["selection"]["balanced_max_f1"]["threshold"]
    )
    for index, sample_id in enumerate(gallery_samples, start=1):
        path = gallery_dir / f"{index:02d}_{sample_id}.jpg"
        render_example(
            models["detect"],
            models["segment"],
            record_by_id[sample_id],
            detection_threshold,
            segment_threshold,
            inference,
            path,
        )
        gallery_files.append(str(path))
    (gallery_dir / "README.md").write_text(
        "# Fair detection vs segmentation gallery\n\n"
        "Each image uses a publisher-labelled PhenoBench test plot. Green is crop, purple is ground-truth weed, orange is predicted weed. "
        "A green action point touches the exact ground-truth weed tissue; a red point does not. Detection acts at the weed box centre; "
        "segmentation acts at the deepest interior point of its predicted weed mask. Confidence thresholds were locked on validation before test inference.\n",
        encoding="utf-8",
    )

    # Per-image rows remain in raw files and the gallery selector, while the
    # summary stays readable.
    summarized_validation = {
        method: {key: value for key, value in metric.items() if key != "per_sample"}
        for method, metric in validation_metrics.items()
    }
    summarized_test = {
        method: {key: value for key, value in metric.items() if key != "per_sample"}
        for method, metric in test_metrics.items()
    }
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "fair_target_trained_ab_complete_not_deployment_proof",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_receipt": str(dataset_receipt_path),
        "dataset_receipt_sha256": sha256(dataset_receipt_path),
        "locked_arms": locked,
        "calibration": calibration,
        "locked_calibration": {
            "path": str(calibration_path),
            "sha256": sha256(calibration_path),
            "written_before_test_inference": True,
        },
        "validation": summarized_validation,
        "test": summarized_test,
        "test_recall_95_policy": test_recall_95_policy,
        "standard_test_metrics": builtin,
        "segment_test_tissue_metrics": tissue,
        "paired_bootstrap": bootstrap,
        "timing": timing,
        "segmentation_preference_gate": gate,
        "raw_action_hashes": action_hashes,
        "gallery": gallery_files,
        "metric_contract": {
            "detection_action": "centre of a predicted weed bounding box",
            "segmentation_action": "deepest interior pixel of a predicted weed instance mask",
            "true_positive": "first action point landing on exact eligible publisher full-weed tissue",
            "false_positive": "duplicate weed action or action on crop/background",
            "crop_collision": "predicted weed action point landing on exact eligible publisher crop tissue",
            "ignored": "action landing on publisher partial plant or an ineligible less-than-16-pixel full plant",
            "size": "sqrt of the exact ground-truth instance bounding-box area at native/model 1024 raster",
        },
        "limitations": [
            "PhenoBench is UAV sugar-beet imagery rather than the final robot camera distribution.",
            "The split controls spatial plot groups but train and test share three capture dates.",
            "One training seed estimates direction, not full training variance.",
            "The same source instances are used, but mask supervision is richer and more expensive to annotate than boxes; this is a task-pipeline A/B, not an equal annotation-minutes study.",
            "Tissue contact is a software proxy; nozzle footprint, calibration, motion, tracking, and kill rate are not measured.",
            "PhenoBench is CC BY-NC-SA 4.0 and the Ultralytics baseline is AGPL-3.0-or-enterprise; these research weights are not a commercial deployment artifact.",
        ],
    }
    metrics_path = output / "fair_ab_metrics.json"
    metrics_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_detect_segment_evaluation_fair_v1.yaml"),
    )
    arguments = parser.parse_args()
    receipt = run(arguments.config)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
