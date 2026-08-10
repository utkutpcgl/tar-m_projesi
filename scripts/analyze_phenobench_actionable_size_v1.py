#!/usr/bin/env python3
"""Diagnose a deployable predicted-size gate for the locked PhenoBench segmenter."""

from __future__ import annotations

import argparse
import gc
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
from PIL import Image

from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    _mask_interior_from_box_crop,
    classify_point,
    load_ground_truth,
    release_cuda,
    sha256,
)


@dataclass(frozen=True)
class SizedAction:
    sample_id: str
    confidence: float
    x: int
    y: int
    target_kind: str
    target_instance_id: int | None
    predicted_box_size_px: float
    predicted_mask_size_px: float


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _mask_bbox_size(
    mask: torch.Tensor,
    box: Sequence[float],
    target_shape: tuple[int, int],
) -> float:
    """Return sqrt(mask bounding-box area) at the target raster."""
    height, width = target_shape
    mask_height, mask_width = (int(value) for value in mask.shape)
    if (mask_height, mask_width) == target_shape:
        x0 = max(0, int(math.floor(float(box[0]))) - 1)
        y0 = max(0, int(math.floor(float(box[1]))) - 1)
        x1 = min(width, int(math.ceil(float(box[2]))) + 1)
        y1 = min(height, int(math.ceil(float(box[3]))) + 1)
        binary = mask[y0:y1, x0:x1].ge(0.5).to(torch.uint8).cpu().numpy()
        offset_x, offset_y = x0, y0
    else:
        full = mask.ge(0.5).to(torch.uint8).cpu().numpy()
        binary = cv2.resize(full, (width, height), interpolation=cv2.INTER_NEAREST)
        offset_x = offset_y = 0
    rows, columns = np.nonzero(binary)
    if not len(rows):
        box_width = max(0.0, float(box[2]) - float(box[0]))
        box_height = max(0.0, float(box[3]) - float(box[1]))
        return math.sqrt(box_width * box_height)
    x_min = int(columns.min()) + offset_x
    x_max = int(columns.max()) + offset_x
    y_min = int(rows.min()) + offset_y
    y_max = int(rows.max()) + offset_y
    return math.sqrt((x_max - x_min + 1) * (y_max - y_min + 1))


def _rates(counts: Mapping[str, int], images: int) -> dict[str, float | int]:
    tp, fp, fn = (int(counts[key]) for key in ("tp", "fp", "fn"))
    attempted = tp + fp
    precision = tp / attempted if attempted else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        **{key: int(value) for key, value in counts.items()},
        "attempted_actions": attempted,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "crop_collision_rate_per_attempt": (
            int(counts["crop_collision"]) / attempted if attempted else 0.0
        ),
        "false_actions_per_image": fp / images if images else 0.0,
    }


def evaluate_policy(
    actions_by_sample: Mapping[str, Sequence[SizedAction]],
    records: Sequence[GroundTruth],
    *,
    confidence_threshold: float,
    minimum_gt_size_px: float,
    minimum_prediction_size_px: float,
) -> dict[str, Any]:
    counts = {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "crop_collision": 0,
        "soil_action": 0,
        "duplicate_action": 0,
        "ignored_small_gt_action": 0,
        "ignored_other_action": 0,
        "suppressed_by_prediction_size": 0,
        "eligible_gt_weeds": 0,
    }
    for truth in records:
        eligible = {
            instance_id
            for instance_id, size in truth.weed_sizes.items()
            if float(size) >= minimum_gt_size_px
        }
        excluded = set(truth.weed_sizes) - eligible
        counts["eligible_gt_weeds"] += len(eligible)
        matched: set[int] = set()
        actions = sorted(
            actions_by_sample.get(truth.sample_id, ()),
            key=lambda item: item.confidence,
            reverse=True,
        )
        for action in actions:
            if action.confidence < confidence_threshold:
                continue
            if action.predicted_mask_size_px < minimum_prediction_size_px:
                counts["suppressed_by_prediction_size"] += 1
                continue
            if action.target_kind == "ignore":
                counts["ignored_other_action"] += 1
                continue
            if action.target_kind == "weed":
                instance_id = int(action.target_instance_id)
                if instance_id in excluded:
                    counts["ignored_small_gt_action"] += 1
                elif instance_id in eligible and instance_id not in matched:
                    matched.add(instance_id)
                    counts["tp"] += 1
                elif instance_id in eligible:
                    counts["fp"] += 1
                    counts["duplicate_action"] += 1
                else:
                    counts["ignored_other_action"] += 1
                continue
            counts["fp"] += 1
            if action.target_kind == "crop":
                counts["crop_collision"] += 1
            else:
                counts["soil_action"] += 1
        counts["fn"] += len(eligible) - len(matched)
    return {
        "policy": {
            "confidence_threshold": float(confidence_threshold),
            "minimum_gt_size_px": float(minimum_gt_size_px),
            "minimum_prediction_size_px": float(minimum_prediction_size_px),
        },
        **_rates(counts, len(records)),
    }


def select_validation_policy(
    actions_by_sample: Mapping[str, Sequence[SizedAction]],
    records: Sequence[GroundTruth],
    *,
    minimum_gt_size_px: float,
    confidence_thresholds: Iterable[float],
    prediction_size_thresholds: Iterable[float],
) -> dict[str, Any]:
    candidates = [
        evaluate_policy(
            actions_by_sample,
            records,
            confidence_threshold=float(confidence),
            minimum_gt_size_px=minimum_gt_size_px,
            minimum_prediction_size_px=float(prediction_size),
        )
        for confidence in confidence_thresholds
        for prediction_size in prediction_size_thresholds
    ]
    return max(
        candidates,
        key=lambda item: (
            float(item["f1"]),
            -float(item["crop_collision_rate_per_attempt"]),
            float(item["precision"]),
            float(item["recall"]),
            float(item["policy"]["confidence_threshold"]),
            -float(item["policy"]["minimum_prediction_size_px"]),
        ),
    )


def infer_sized_actions(
    model: Any,
    records: Sequence[GroundTruth],
    inference: Mapping[str, Any],
) -> tuple[dict[str, list[SizedAction]], dict[str, Any]]:
    output: dict[str, list[SizedAction]] = {}
    elapsed: list[float] = []
    prediction_count = 0
    chunk_size = int(inference["chunk_size"])
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        started = time.perf_counter()
        results = model.predict(
            source=[str(record.image_path) for record in chunk],
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
        for truth, result in zip(chunk, results, strict=True):
            semantics = np.asarray(Image.open(truth.semantics_path), dtype=np.uint16)
            instances = np.asarray(Image.open(truth.instances_path), dtype=np.uint16)
            output[truth.sample_id] = []
            if result.boxes is None or result.masks is None:
                continue
            boxes = result.boxes.xyxy.detach().cpu().numpy()
            confidences = result.boxes.conf.detach().cpu().numpy()
            classes = result.boxes.cls.detach().cpu().numpy().astype(np.int64)
            masks = result.masks.data
            for index, (box, confidence, class_id) in enumerate(
                zip(boxes, confidences, classes, strict=True)
            ):
                if int(class_id) != 0 or index >= len(masks):
                    continue
                prediction_count += 1
                interior = _mask_interior_from_box_crop(
                    masks[index], box, semantics.shape
                )
                if interior is None:
                    interior = (
                        int(round((float(box[0]) + float(box[2])) / 2)),
                        int(round((float(box[1]) + float(box[3])) / 2)),
                    )
                target_kind, target_id = classify_point(
                    interior[0], interior[1], semantics, instances, truth
                )
                box_width = max(0.0, float(box[2]) - float(box[0]))
                box_height = max(0.0, float(box[3]) - float(box[1]))
                output[truth.sample_id].append(
                    SizedAction(
                        sample_id=truth.sample_id,
                        confidence=float(confidence),
                        x=int(interior[0]),
                        y=int(interior[1]),
                        target_kind=target_kind,
                        target_instance_id=target_id,
                        predicted_box_size_px=math.sqrt(box_width * box_height),
                        predicted_mask_size_px=_mask_bbox_size(
                            masks[index], box, semantics.shape
                        ),
                    )
                )
        elapsed.append((time.perf_counter() - started) * 1000.0)
        result = None
        masks = None
        results = None
        gc.collect()
        release_cuda(model)
    return output, {
        "images": len(records),
        "weed_predictions_at_confidence_floor": prediction_count,
        "wall_ms_per_image": sum(elapsed) / len(records),
        "batch": int(inference["batch"]),
        "chunk_size": chunk_size,
    }


def _write_actions(path: Path, actions: Mapping[str, Sequence[SizedAction]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for sample_id in sorted(actions):
            for action in actions[sample_id]:
                handle.write(json.dumps(asdict(action), sort_keys=True) + "\n")


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, settings

    settings.update({"wandb": False, "mlflow": False, "clearml": False})
    project_root = Path(__file__).resolve().parents[1]
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = _resolve(project_root, config["data_root"])
    source_metrics_path = _resolve(data_root, config["source_metrics"])
    if sha256(source_metrics_path) != config["source_metrics_sha256"]:
        raise ValueError("Source metrics SHA-256 drift")
    source_metrics = json.loads(source_metrics_path.read_text(encoding="utf-8"))
    dataset_receipt_path = Path(source_metrics["dataset_receipt"])
    dataset_receipt = json.loads(dataset_receipt_path.read_text(encoding="utf-8"))
    membership = Path(dataset_receipt["provenance"]["membership"])
    if sha256(membership) != dataset_receipt["provenance"]["membership_sha256"]:
        raise ValueError("Membership SHA-256 drift")
    minimum_area = int(dataset_receipt["label_contract"]["minimum_full_instance_area_px"])
    records = {
        split: load_ground_truth(membership, split, minimum_area)
        for split in ("val", "test")
    }
    arm = source_metrics["locked_arms"]["segment"]
    checkpoint = Path(arm["fixed_final_checkpoint"])
    if sha256(checkpoint) != arm["fixed_final_checkpoint_sha256"]:
        raise ValueError("Segment checkpoint SHA-256 drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for sized-action inference")
    model = YOLO(str(checkpoint))
    actions: dict[str, dict[str, list[SizedAction]]] = {}
    timing: dict[str, Any] = {}
    for split in ("val", "test"):
        actions[split], timing[split] = infer_sized_actions(
            model, records[split], config["inference"]
        )
    confidence = np.arange(
        float(config["confidence_threshold"]["start"]),
        float(config["confidence_threshold"]["stop"]) + 1e-9,
        float(config["confidence_threshold"]["step"]),
    )
    prediction_sizes = [float(value) for value in config["predicted_mask_minimum_size_px"]]
    original = config["original_policy"]
    diagnostics: dict[str, Any] = {}
    for raw_minimum in config["ground_truth_minimum_size_px"]:
        minimum = float(raw_minimum)
        selected = select_validation_policy(
            actions["val"],
            records["val"],
            minimum_gt_size_px=minimum,
            confidence_thresholds=confidence,
            prediction_size_thresholds=prediction_sizes,
        )
        policy = selected["policy"]
        diagnostics[str(raw_minimum)] = {
            "original_policy_test": evaluate_policy(
                actions["test"],
                records["test"],
                confidence_threshold=float(original["confidence_threshold"]),
                minimum_gt_size_px=minimum,
                minimum_prediction_size_px=float(
                    original["predicted_mask_minimum_size_px"]
                ),
            ),
            "validation_selected_policy": policy,
            "validation_selected_metrics": selected,
            "validation_selected_policy_test": evaluate_policy(
                actions["test"],
                records["test"],
                confidence_threshold=float(policy["confidence_threshold"]),
                minimum_gt_size_px=minimum,
                minimum_prediction_size_px=float(
                    policy["minimum_prediction_size_px"]
                ),
            ),
        }
    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    for split in ("val", "test"):
        _write_actions(output / f"{split}_sized_actions.jsonl", actions[split])
    payload = {
        "schema_version": 1,
        "status": "posthoc_size_diagnostic_not_untouched_not_deployment_proof",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "source_metrics": str(source_metrics_path),
        "source_metrics_sha256": sha256(source_metrics_path),
        "segment_checkpoint_sha256": sha256(checkpoint),
        "size_definition": "sqrt of exact or predicted mask bounding-box area at native/model 1024",
        "diagnostics": diagnostics,
        "timing": timing,
        "limitations": config["claims"],
    }
    metrics_path = output / "actionable_size_metrics.json"
    metrics_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    payload["metrics_path"] = str(metrics_path)
    payload["metrics_sha256"] = sha256(metrics_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_actionable_size_diagnostic_v1.yaml"),
    )
    args = parser.parse_args()
    result = run(args.config)
    print(
        json.dumps(
            {
                "status": result["status"],
                "metrics": result["metrics_path"],
                "metrics_sha256": result["metrics_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
