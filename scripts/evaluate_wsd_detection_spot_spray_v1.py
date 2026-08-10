#!/usr/bin/env python3
"""Compare detection-only box centres with pose keypoints for spot spraying.

Validation alone chooses confidence and within-frame point-deduplication.  The
date-disjoint test capture is then evaluated with frozen settings.  Two action
definitions are deliberately kept separate:

* ``weed_box_proxy``: the action point/footprint intersects a GT weed box.  It
  is an optimistic spraying proxy because a box includes background.
* ``stem_strict``: the action point is within 10% of the GT weed-box diagonal
  from the annotated stem.  This is the stricter point-intervention proxy.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

from scripts.evaluate_wsd_action_poc_v1 import (
    CROP_CLASSES,
    Prediction,
    Sample,
    _dataset_split,
    _distribution,
    _point_pairs,
    _read_ground_truth,
    _sample_payload,
    _weed_gt,
    _weed_predictions,
    choose_threshold,
    deduplicate_action_points,
    evaluate_actions,
    evaluate_detection,
    infer_split,
    maximum_valid_pairs,
    point_footprint_hits_box,
    prf,
    sha256,
    with_box_center_actions,
)


def infer_detection_split(
    model: Any,
    pose_dataset_yaml: Path,
    split: str,
    *,
    image_size: int,
    batch: int,
    device: int,
) -> list[Sample]:
    """Infer a detect model while retaining pose GT for strict scoring."""
    root, image_paths = _dataset_split(pose_dataset_yaml, split)
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
        predictions = tuple(
            Prediction(
                class_id=int(class_id),
                confidence=float(confidence),
                box=tuple(float(value) for value in box),
                point=(float((box[0] + box[2]) / 2.0), float((box[1] + box[3]) / 2.0)),
                keypoint_confidence=float(confidence),
            )
            for box, confidence, class_id in zip(
                boxes, confidences, classes, strict=True
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


def evaluate_weed_box_proxy(
    samples: Sequence[Sample],
    threshold: float,
    *,
    footprint_radius_px: float = 0.0,
) -> dict[str, Any]:
    """Score one-to-one action/GT-weed-box intersection.

    This intentionally does not claim tissue contact.  A GT rectangle can
    include substantial soil, particularly for sparse or irregular plants.
    """
    if footprint_radius_px < 0.0:
        raise ValueError("footprint radius cannot be negative")
    true_positive = false_positive = false_negative = actions = 0
    crop_collisions = 0
    for sample in samples:
        predictions = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample)
        matches = _weed_box_proxy_matches(
            predictions, ground_truth, footprint_radius_px
        )
        true_positive += len(matches)
        false_positive += len(predictions) - len(matches)
        false_negative += len(ground_truth) - len(matches)
        actions += len(predictions)
        crop_boxes = [
            item.box for item in sample.ground_truth if item.class_id in CROP_CLASSES
        ]
        crop_collisions += sum(
            any(
                point_footprint_hits_box(
                    prediction.point, crop_box, footprint_radius_px
                )
                for crop_box in crop_boxes
            )
            for prediction in predictions
        )
    result = prf(true_positive, false_positive, false_negative)
    collision_rate = crop_collisions / actions if actions else None
    result.update(
        {
            "confidence_threshold": threshold,
            "definition": "one-to-one action footprint intersection with a GT weed bounding box",
            "interpretation": "optimistic spot-spray proxy; not verified weed-tissue contact or kill",
            "footprint_radius_px_at_original_2048_frame": footprint_radius_px,
            "actions": actions,
            "ground_truth_weed_boxes": true_positive + false_negative,
            "crop_box_collision": {
                "actions": crop_collisions,
                "rate_per_action": collision_rate,
            },
            # Keep the common selector interface explicit.  This is a point vs
            # crop-rectangle collision, not an IoU-based class-confusion count.
            "crop_as_weed_false_fire": {
                "actions": crop_collisions,
                "rate_per_action": collision_rate,
                "definition": "action footprint intersects any GT crop rectangle",
            },
        }
    )
    return result


def _weed_box_proxy_matches(
    predictions: Sequence[Prediction],
    ground_truth: Sequence[Any],
    footprint_radius_px: float,
) -> list[tuple[int, int]]:
    centres = np.asarray(
        [
            ((item.box[0] + item.box[2]) / 2.0, (item.box[1] + item.box[3]) / 2.0)
            for item in ground_truth
        ],
        dtype=np.float64,
    )
    points = np.asarray([item.point for item in predictions], dtype=np.float64)
    if predictions and ground_truth:
        distances = np.linalg.norm(points[:, None, :] - centres[None, :, :], axis=2)
        valid = np.asarray(
            [
                [
                    point_footprint_hits_box(
                        prediction.point, instance.box, footprint_radius_px
                    )
                    for instance in ground_truth
                ]
                for prediction in predictions
            ],
            dtype=bool,
        )
    else:
        distances = np.zeros((len(predictions), len(ground_truth)), dtype=np.float64)
        valid = np.zeros_like(distances, dtype=bool)
    return maximum_valid_pairs(distances, valid, prefer_larger=False)


def weed_box_proxy_recall_by_apparent_size(
    samples: Sequence[Sample],
    threshold: float,
    *,
    inference_image_size: int,
    footprint_radius_px: float = 0.0,
) -> dict[str, Any]:
    """Break proxy recall down by GT box-equivalent diameter at model input."""
    totals = {"lt14": 0, "14_to_lt28": 0, "28_to_lt56": 0, "ge56": 0}
    hits = {key: 0 for key in totals}
    for sample in samples:
        predictions = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample)
        matched_gt = {
            gt_index
            for _, gt_index in _weed_box_proxy_matches(
                predictions, ground_truth, footprint_radius_px
            )
        }
        scale = min(
            inference_image_size / sample.width,
            inference_image_size / sample.height,
        )
        for index, instance in enumerate(ground_truth):
            width = max(0.0, instance.box[2] - instance.box[0]) * scale
            height = max(0.0, instance.box[3] - instance.box[1]) * scale
            size = math.sqrt(width * height)
            if size < 14.0:
                key = "lt14"
            elif size < 28.0:
                key = "14_to_lt28"
            elif size < 56.0:
                key = "28_to_lt56"
            else:
                key = "ge56"
            totals[key] += 1
            hits[key] += int(index in matched_gt)
    return {
        "size_definition": "sqrt(GT weed box area) after scale to model input",
        "footprint_radius_px_at_original_2048_frame": footprint_radius_px,
        "bins": {
            key: {
                "ground_truth": totals[key],
                "hits": hits[key],
                "recall": hits[key] / totals[key] if totals[key] else None,
            }
            for key in totals
        },
    }


def metric_curve(
    samples: Sequence[Sample],
    thresholds: Iterable[float],
    evaluator: Callable[[Sequence[Sample], float], dict[str, Any]],
) -> list[dict[str, Any]]:
    return [evaluator(samples, float(threshold)) for threshold in thresholds]


def choose_recall_target(
    curve: Sequence[dict[str, Any]], target: float = 0.95
) -> dict[str, Any]:
    usable = [item for item in curve if item["recall"] is not None]
    if not usable:
        raise ValueError("No defined recall values")
    feasible = [item for item in usable if float(item["recall"]) >= target]
    target_reached = bool(feasible)
    candidates = feasible if feasible else usable
    selected = max(
        candidates,
        key=lambda item: (
            float(item["precision"] or 0.0) if target_reached else float(item["recall"]),
            float(item["f1"] or 0.0),
            float(item["recall"]),
            float(item["confidence_threshold"]),
        ),
    )
    return {
        "target_recall": target,
        "target_reached_on_validation": target_reached,
        "threshold": selected["confidence_threshold"],
        "validation_metrics": selected,
    }


def calibrate_spot_strategy(
    validation_samples: Sequence[Sample], thresholds: Sequence[float]
) -> dict[str, Any]:
    screen: list[dict[str, Any]] = []
    curves: dict[float, list[dict[str, Any]]] = {}
    for fraction in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
        converted = deduplicate_action_points(validation_samples, fraction)
        curve = metric_curve(converted, thresholds, evaluate_weed_box_proxy)
        selection = choose_threshold(curve)
        curves[fraction] = curve
        screen.append(
            {
                "radius_fraction_of_smaller_predicted_box_diagonal": fraction,
                "balanced_selection": selection,
            }
        )
    selected = max(
        screen,
        key=lambda item: (
            float(item["balanced_selection"]["validation_metrics"]["f1"]),
            float(item["balanced_selection"]["validation_metrics"]["recall"]),
            -float(item["radius_fraction_of_smaller_predicted_box_diagonal"]),
        ),
    )
    fraction = float(selected["radius_fraction_of_smaller_predicted_box_diagonal"])
    return {
        "deduplication_screen": screen,
        "selected_deduplication_fraction": fraction,
        "balanced_selection": selected["balanced_selection"],
        "recall_95_selection": choose_recall_target(curves[fraction], 0.95),
    }


def apparent_weed_box_sizes(
    samples: Sequence[Sample], inference_image_size: int
) -> dict[str, Any]:
    sizes: list[float] = []
    for sample in samples:
        scale = min(inference_image_size / sample.width, inference_image_size / sample.height)
        for instance in _weed_gt(sample):
            width = max(0.0, instance.box[2] - instance.box[0]) * scale
            height = max(0.0, instance.box[3] - instance.box[1]) * scale
            sizes.append(math.sqrt(width * height))
    bins = {
        "lt14": sum(value < 14.0 for value in sizes),
        "14_to_lt28": sum(14.0 <= value < 28.0 for value in sizes),
        "28_to_lt56": sum(28.0 <= value < 56.0 for value in sizes),
        "ge56": sum(value >= 56.0 for value in sizes),
    }
    return {
        "definition": "sqrt(GT weed box area) after letterbox scale to model input; box proxy, not mask diameter",
        "count": len(sizes),
        "distribution_px": _distribution(sizes),
        "bins": {
            key: {"count": count, "fraction": count / len(sizes) if sizes else None}
            for key, count in bins.items()
        },
    }


def _evaluate_strategy(
    raw_samples: dict[str, list[Sample]],
    thresholds: Sequence[float],
    inference_image_size: int,
) -> tuple[dict[str, Any], dict[str, list[Sample]]]:
    detection_curve = metric_curve(raw_samples["val"], thresholds, evaluate_detection)
    detection_selection = choose_threshold(detection_curve)
    spot_calibration = calibrate_spot_strategy(raw_samples["val"], thresholds)
    fraction = float(spot_calibration["selected_deduplication_fraction"])
    samples = {
        split: deduplicate_action_points(items, fraction)
        for split, items in raw_samples.items()
    }
    strict_curve = metric_curve(
        samples["val"], thresholds, lambda items, threshold: evaluate_actions(
            items,
            threshold,
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        )
    )
    strict_balanced = choose_threshold(strict_curve)
    strict_recall_95 = choose_recall_target(strict_curve, 0.95)

    spot_test: dict[str, Any] = {}
    for policy_name, selection in (
        ("balanced_max_f1", spot_calibration["balanced_selection"]),
        ("validation_recall_95", spot_calibration["recall_95_selection"]),
    ):
        threshold = float(selection["threshold"])
        spot_test[policy_name] = {
            "selection": selection,
            "test_by_footprint_radius": {
                str(radius): evaluate_weed_box_proxy(
                    samples["test"], threshold, footprint_radius_px=float(radius)
                )
                for radius in (0, 5, 10, 20)
            },
            "test_radius_0_recall_by_apparent_weed_box_size": (
                weed_box_proxy_recall_by_apparent_size(
                    samples["test"],
                    threshold,
                    inference_image_size=inference_image_size,
                    footprint_radius_px=0.0,
                )
            ),
        }
    strict_test: dict[str, Any] = {}
    for policy_name, selection in (
        ("balanced_max_f1", strict_balanced),
        ("validation_recall_95", strict_recall_95),
    ):
        threshold = float(selection["threshold"])
        strict_test[policy_name] = {
            "selection": selection,
            "test_by_tolerance": {
                f"box_diagonal_fraction_{fraction:.2f}": evaluate_actions(
                    samples["test"],
                    threshold,
                    tolerance_kind="box_diagonal_fraction",
                    tolerance=fraction,
                )
                for fraction in (0.05, 0.10, 0.20)
            },
        }
    return (
        {
            "validation": {
                "detection_selection": detection_selection,
                "spot_spray_calibration": spot_calibration,
                "strict_stem_balanced_selection": strict_balanced,
                "strict_stem_recall_95_selection": strict_recall_95,
            },
            "test": {
                "weed_detection_iou_0.50": evaluate_detection(
                    raw_samples["test"], float(detection_selection["threshold"])
                ),
                "weed_box_proxy": spot_test,
                "stem_strict": strict_test,
            },
        },
        samples,
    )


def _per_image_strict_f1(sample: Sample, threshold: float) -> float:
    result = evaluate_actions(
        [sample], threshold, tolerance_kind="box_diagonal_fraction", tolerance=0.10
    )
    return float(result["f1"] or 0.0)


def _draw_panel(
    sample: Sample,
    *,
    title: str,
    threshold: float | None,
    predictions: bool,
) -> Image.Image:
    image = Image.open(sample.image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for instance in sample.ground_truth:
        colour = "#ff3434" if instance.class_id == 0 else "#35d04f"
        draw.rectangle(instance.box, outline=colour, width=4)
        if instance.class_id == 0 and instance.point is not None:
            x, y = instance.point
            draw.line((x - 8, y, x + 8, y), fill="#00e5ff", width=4)
            draw.line((x, y - 8, x, y + 8), fill="#00e5ff", width=4)
    if predictions and threshold is not None:
        selected = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample, visible_only=True)
        matches, _ = _point_pairs(
            selected,
            ground_truth,
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        )
        hit = {index for index, _ in matches}
        for index, prediction in enumerate(selected):
            colour = "#ffe100" if index in hit else "#ff00ff"
            draw.rectangle(prediction.box, outline=colour, width=3)
            x, y = prediction.point
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=colour, width=4)
    banner = 82
    resized_width = 760
    resized_height = round(image.height * resized_width / image.width)
    image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (resized_width, resized_height + banner), "#101820")
    canvas.paste(image, (0, banner))
    text = ImageDraw.Draw(canvas)
    text.text((12, 8), title, fill="white", font=font)
    text.text(
        (12, 29),
        "GT weed=RED | crop=GREEN | GT stem=CYAN +",
        fill="white",
        font=font,
    )
    text.text(
        (12, 50),
        "prediction/action: YELLOW=strict hit | MAGENTA=miss/false fire",
        fill="white",
        font=font,
    )
    return canvas


def _write_comparison_gallery(
    strategies: dict[str, dict[str, list[Sample]]],
    selections: dict[str, dict[str, Any]],
    output: Path,
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    anchor_name = "detection_only_box_center"
    anchor = strategies[anchor_name]["test"]
    anchor_threshold = float(
        selections[anchor_name]["validation"]["strict_stem_balanced_selection"]["threshold"]
    )
    ranked = sorted(
        anchor,
        key=lambda sample: (_per_image_strict_f1(sample, anchor_threshold), sample.image_path.name),
    )
    indices = np.linspace(0, len(ranked) - 1, min(6, len(ranked)), dtype=int)
    sample_maps = {
        name: {sample.image_path.name: sample for sample in split_samples["test"]}
        for name, split_samples in strategies.items()
    }
    paths: list[str] = []
    for rank, index in enumerate(indices, 1):
        anchor_sample = ranked[int(index)]
        panels = [
            _draw_panel(
                anchor_sample, title="Ground truth only", threshold=None, predictions=False
            )
        ]
        for name, label in (
            ("detection_only_box_center", "Detection-only -> box centre"),
            ("pose_box_center", "Pose model -> box centre control"),
            ("pose_keypoint", "Pose model -> predicted stem keypoint"),
        ):
            threshold = float(
                selections[name]["validation"]["strict_stem_balanced_selection"]["threshold"]
            )
            panels.append(
                _draw_panel(
                    sample_maps[name][anchor_sample.image_path.name],
                    title=label,
                    threshold=threshold,
                    predictions=True,
                )
            )
        width = panels[0].width * 2
        height = panels[0].height * 2
        sheet = Image.new("RGB", (width, height), "white")
        for position, panel in enumerate(panels):
            sheet.paste(
                panel,
                ((position % 2) * panel.width, (position // 2) * panel.height),
            )
        path = output / f"{rank:02d}_{anchor_sample.image_path.stem}.jpg"
        sheet.save(path, quality=90)
        paths.append(str(path))
    return paths


def run(
    detection_config_path: Path,
    pose_config_path: Path,
    *,
    output_name: str = "spot_spray_ab_v1",
    image_size_override: int | None = None,
) -> dict[str, Any]:
    if not output_name or Path(output_name).name != output_name:
        raise ValueError("output_name must be one safe path component")
    from ultralytics import YOLO, settings

    for key in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb"):
        settings.update({key: False})
    detection_config_path = detection_config_path.expanduser().resolve()
    pose_config_path = pose_config_path.expanduser().resolve()
    detection_config = yaml.safe_load(detection_config_path.read_text(encoding="utf-8"))
    pose_config = yaml.safe_load(pose_config_path.read_text(encoding="utf-8"))
    data_root = Path(detection_config["data_root"]).expanduser().resolve()
    pose_data_root = Path(pose_config["data_root"]).expanduser().resolve()
    if data_root != pose_data_root:
        raise ValueError("Detection and pose configs must use the same data root")
    detection_checkpoint = (
        data_root
        / detection_config["output"]["project"]
        / detection_config["output"]["name"]
        / "weights/best.pt"
    ).resolve()
    pose_checkpoint = (
        data_root
        / pose_config["output"]["project"]
        / pose_config["output"]["name"]
        / "weights/best.pt"
    ).resolve()
    pose_dataset_yaml = (data_root / pose_config["dataset_yaml"]).resolve()
    for path in (detection_checkpoint, pose_checkpoint, pose_dataset_yaml):
        if not path.is_file():
            raise FileNotFoundError(path)
    configured_detection_size = int(detection_config["evaluation"]["image_size"])
    configured_pose_size = int(pose_config["evaluation"]["image_size"])
    if configured_detection_size != configured_pose_size:
        raise ValueError("A/B models must use the same evaluation image size")
    detection_training_size = int(detection_config["training"]["image_size"])
    pose_training_size = int(pose_config["training"]["image_size"])
    if detection_training_size != pose_training_size:
        raise ValueError("A/B models must use the same training image size")
    image_size = int(image_size_override or configured_detection_size)
    if image_size <= 0 or image_size % 32:
        raise ValueError("image size must be a positive multiple of 32")
    batch = min(
        int(detection_config["evaluation"]["batch"]),
        int(pose_config["evaluation"]["batch"]),
    )
    device = int(detection_config["training"]["device"])
    output = detection_checkpoint.parents[1] / output_name
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)

    detection_model = YOLO(str(detection_checkpoint))
    pose_model = YOLO(str(pose_checkpoint))
    detection_samples: dict[str, list[Sample]] = {}
    pose_samples: dict[str, list[Sample]] = {}
    for split in ("train", "val", "test"):
        detection_samples[split] = infer_detection_split(
            detection_model,
            pose_dataset_yaml,
            split,
            image_size=image_size,
            batch=batch,
            device=device,
        )
        pose_samples[split] = infer_split(
            pose_model,
            pose_dataset_yaml,
            split,
            image_size=image_size,
            batch=batch,
            device=device,
        )
        for model_name, samples in (
            ("detection", detection_samples[split]),
            ("pose", pose_samples[split]),
        ):
            (output / f"predictions_{model_name}_{split}.json").write_text(
                json.dumps([_sample_payload(sample) for sample in samples]) + "\n",
                encoding="utf-8",
            )

    raw_strategies = {
        "detection_only_box_center": detection_samples,
        "pose_box_center": {
            split: with_box_center_actions(samples)
            for split, samples in pose_samples.items()
        },
        "pose_keypoint": pose_samples,
    }
    thresholds = [round(value / 100.0, 2) for value in range(1, 100)]
    results: dict[str, Any] = {}
    calibrated_samples: dict[str, dict[str, list[Sample]]] = {}
    for name, strategy_samples in raw_strategies.items():
        results[name], calibrated_samples[name] = _evaluate_strategy(
            strategy_samples, thresholds, image_size
        )
    gallery = _write_comparison_gallery(
        calibrated_samples, results, output / "comparison_gallery"
    )
    size_distribution = {
        split: apparent_weed_box_sizes(detection_samples[split], image_size)
        for split in ("train", "val", "test")
    }
    size_counterfactuals = {
        str(candidate): apparent_weed_box_sizes(
            detection_samples["test"], candidate
        )
        for candidate in (1024, 1536, 2048)
    }
    receipt = {
        "schema_version": 1,
        "protocol": "wsd_detection_only_vs_pose_spot_spray_date_holdout_v1",
        "status": "offline_research_proxy_not_field_validated",
        "fairness_controls": {
            "same_source_images_and_classes": True,
            "same_capture_date_disjoint_splits": True,
            "same_training_image_size": detection_training_size,
            "same_inference_image_size": image_size,
            "same_seed": int(detection_config["training"]["seed"]),
            "same_requested_epochs": int(detection_config["training"]["epochs"]),
            "validation_only_selects_thresholds_and_deduplication": True,
            "test_capture_date_used_for_selection": False,
        },
        "checkpoints": {
            "detection_only": {
                "path": str(detection_checkpoint),
                "sha256": sha256(detection_checkpoint),
            },
            "pose": {"path": str(pose_checkpoint), "sha256": sha256(pose_checkpoint)},
        },
        "data": {
            "pose_ground_truth_yaml": str(pose_dataset_yaml),
            "pose_ground_truth_yaml_sha256": sha256(pose_dataset_yaml),
            "apparent_weed_box_size_at_model_input": size_distribution,
            "test_size_counterfactuals_without_model_inference": size_counterfactuals,
        },
        "strategies": results,
        "decision_gate": {
            "target": "test balanced F1 >= 0.95",
            "spot_proxy_passed": bool(
                results["detection_only_box_center"]["test"]["weed_box_proxy"]
                ["balanced_max_f1"]["test_by_footprint_radius"]["0"]["f1"]
                is not None
                and results["detection_only_box_center"]["test"]["weed_box_proxy"]
                ["balanced_max_f1"]["test_by_footprint_radius"]["0"]["f1"]
                >= 0.95
            ),
            "strict_stem_passed": bool(
                results["detection_only_box_center"]["test"]["stem_strict"]
                ["balanced_max_f1"]["test_by_tolerance"]
                ["box_diagonal_fraction_0.10"]["f1"]
                is not None
                and results["detection_only_box_center"]["test"]["stem_strict"]
                ["balanced_max_f1"]["test_by_tolerance"]
                ["box_diagonal_fraction_0.10"]["f1"]
                >= 0.95
            ),
            "field_deployment_gate": "not evaluated",
        },
        "artifacts": {
            "output_directory": str(output),
            "comparison_gallery": gallery,
        },
        "limitations": [
            "A weed GT bounding rectangle includes soil; box-proxy hits overestimate tissue hits.",
            "Crop-rectangle intersection overestimates physical crop contact; canopy masks are unavailable.",
            "No nozzle footprint, GSD, latency, tracking, wind, pressure, or physical kill outcome is measured.",
            "The downloadable WSD subset has 511 paired frames, not the paper's full annotated inventory.",
            "The held-out WSD date has already been inspected in earlier development and is not a pristine final field test.",
        ],
    }
    receipt_path = output / "spot_spray_ab_metrics.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detection-config",
        type=Path,
        default=Path("configs/benchmark/wsd_detection_poc_v1.yaml"),
    )
    parser.add_argument(
        "--pose-config",
        type=Path,
        default=Path("configs/benchmark/wsd_pose_poc_v1.yaml"),
    )
    parser.add_argument("--output-name", default="spot_spray_ab_v1")
    parser.add_argument("--image-size", type=int)
    arguments = parser.parse_args()
    result = run(
        arguments.detection_config,
        arguments.pose_config,
        output_name=arguments.output_name,
        image_size_override=arguments.image_size,
    )
    summary = {}
    for name, strategy in result["strategies"].items():
        summary[name] = {
            "weed_detection": strategy["test"]["weed_detection_iou_0.50"],
            "spot_proxy_radius_0": strategy["test"]["weed_box_proxy"]
            ["balanced_max_f1"]["test_by_footprint_radius"]["0"],
            "stem_strict_10pct": strategy["test"]["stem_strict"]
            ["balanced_max_f1"]["test_by_tolerance"]
            ["box_diagonal_fraction_0.10"],
        }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
