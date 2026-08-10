#!/usr/bin/env python3
"""Compare accepted semantic segmentation with WSD detection for spraying."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from agri_seg.data import EvalTransform
from agri_seg.engine import load_checkpoint, predict_logits
from scripts.evaluate_wsd_action_poc_v1 import (
    Instance,
    Prediction,
    Sample,
    _dataset_split,
    _read_ground_truth,
    choose_threshold,
    evaluate_actions,
    sha256,
)
from scripts.evaluate_wsd_detection_spot_spray_v1 import (
    choose_recall_target,
    evaluate_weed_box_proxy,
    metric_curve,
    weed_box_proxy_recall_by_apparent_size,
)


WEED_CLASS = 0
PROJECT_WEED_CLASS = 2


@dataclass(frozen=True)
class GeneratorConfig:
    mode: str
    min_area_px: int
    score_kind: str
    peak_min_distance_px: int | None = None

    @property
    def name(self) -> str:
        suffix = (
            ""
            if self.peak_min_distance_px is None
            else f"_distance{self.peak_min_distance_px}"
        )
        return f"{self.mode}_area{self.min_area_px}_{self.score_kind}{suffix}"


@dataclass(frozen=True)
class ComponentFeature:
    area: int
    box: tuple[int, int, int, int]
    deepest_point: tuple[int, int]
    mean_confidence: float
    max_confidence: float
    distance: np.ndarray
    component_mask: np.ndarray
    offset: tuple[int, int]


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generator_configs(screen: Mapping[str, Any]) -> list[GeneratorConfig]:
    configs = [
        GeneratorConfig("component", int(area), str(score))
        for area in screen["component_min_areas_px"]
        for score in screen["component_score_kinds"]
    ]
    configs.extend(
        GeneratorConfig("distance_peaks", int(area), "mean", int(distance))
        for area in screen["peak_min_areas_px"]
        for distance in screen["peak_min_distances_px"]
    )
    names = [config.name for config in configs]
    if len(names) != len(set(names)):
        raise ValueError("Generator configuration names must be unique")
    return configs


def confidence_thresholds(screen: Mapping[str, Any]) -> list[float]:
    config = screen["confidence_thresholds"]
    start = float(config["start"])
    stop = float(config["stop"])
    step = float(config["step"])
    if not (0.0 <= start <= stop <= 1.0) or step <= 0.0:
        raise ValueError("Invalid confidence threshold screen")
    values: list[float] = []
    value = start
    while value <= stop + 1e-9:
        values.append(round(value, 4))
        value += step
    if values[-1] != stop:
        values.append(stop)
    return values


def _component_features(probabilities: np.ndarray) -> list[ComponentFeature]:
    if probabilities.ndim != 3 or probabilities.shape[0] != 3:
        raise ValueError("Expected 3xHxW class probabilities")
    semantic = probabilities.argmax(axis=0)
    mask = semantic == PROJECT_WEED_CLASS
    labels, count = ndimage.label(
        mask, structure=np.ones((3, 3), dtype=np.uint8)
    )
    if not count:
        return []
    areas = np.bincount(labels.ravel(), minlength=count + 1)[1:]
    slices = ndimage.find_objects(labels)
    features: list[ComponentFeature] = []
    weed_probability = probabilities[PROJECT_WEED_CLASS]
    for label_index, (area, component_slice) in enumerate(
        zip(areas, slices, strict=True), start=1
    ):
        if component_slice is None or area <= 0:
            continue
        local_labels = labels[component_slice]
        component_mask = local_labels == label_index
        local_probability = weed_probability[component_slice]
        values = local_probability[component_mask]
        distance = ndimage.distance_transform_edt(component_mask)
        flat_index = int(np.argmax(distance))
        row, column = np.unravel_index(flat_index, distance.shape)
        top = int(component_slice[0].start or 0)
        left = int(component_slice[1].start or 0)
        bottom = int(component_slice[0].stop)
        right = int(component_slice[1].stop)
        features.append(
            ComponentFeature(
                area=int(area),
                box=(left, top, right, bottom),
                deepest_point=(left + int(column), top + int(row)),
                mean_confidence=float(values.mean()),
                max_confidence=float(values.max()),
                distance=distance,
                component_mask=component_mask,
                offset=(left, top),
            )
        )
    return features


def _distance_peaks(feature: ComponentFeature, min_distance: int) -> list[tuple[int, int]]:
    if min_distance <= 0:
        raise ValueError("peak minimum distance must be positive")
    distance = feature.distance
    size = 2 * min_distance + 1
    maxima = ndimage.maximum_filter(distance, size=size, mode="constant")
    candidates = feature.component_mask & (distance > 0.0) & (distance == maxima)
    plateau_labels, plateau_count = ndimage.label(
        candidates, structure=np.ones((3, 3), dtype=np.uint8)
    )
    proposed: list[tuple[float, int, int]] = []
    for plateau in range(1, int(plateau_count) + 1):
        rows, columns = np.nonzero(plateau_labels == plateau)
        if not len(rows):
            continue
        values = distance[rows, columns]
        best = int(np.argmax(values))
        proposed.append((float(values[best]), int(rows[best]), int(columns[best])))
    kept: list[tuple[int, int]] = []
    for _, row, column in sorted(proposed, reverse=True):
        if all(
            math.hypot(row - prior_row, column - prior_column) >= min_distance
            for prior_row, prior_column in kept
        ):
            kept.append((row, column))
    left, top = feature.offset
    return [(left + column, top + row) for row, column in kept]


def predictions_from_probabilities(
    probabilities: np.ndarray,
    config: GeneratorConfig,
    *,
    original_width: int,
    original_height: int,
) -> tuple[Prediction, ...]:
    return predictions_from_features(
        _component_features(probabilities),
        config,
        model_width=probabilities.shape[2],
        model_height=probabilities.shape[1],
        original_width=original_width,
        original_height=original_height,
    )


def predictions_from_features(
    features: Sequence[ComponentFeature],
    config: GeneratorConfig,
    *,
    model_width: int,
    model_height: int,
    original_width: int,
    original_height: int,
    peak_cache: dict[tuple[int, int], list[tuple[int, int]]] | None = None,
) -> tuple[Prediction, ...]:
    scale_x = original_width / model_width
    scale_y = original_height / model_height
    output: list[Prediction] = []
    cache = {} if peak_cache is None else peak_cache
    for feature_index, feature in enumerate(features):
        if feature.area < config.min_area_px:
            continue
        confidence = (
            feature.mean_confidence
            if config.score_kind == "mean"
            else feature.max_confidence
        )
        if config.mode == "component":
            points = [feature.deepest_point]
        elif config.mode == "distance_peaks":
            if config.peak_min_distance_px is None:
                raise ValueError("distance-peaks mode requires min distance")
            key = (feature_index, config.peak_min_distance_px)
            if key not in cache:
                cache[key] = _distance_peaks(
                    feature, config.peak_min_distance_px
                )
            points = cache[key]
        else:
            raise ValueError(f"Unknown generator mode: {config.mode}")
        x1, y1, x2, y2 = feature.box
        box = (x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y)
        for point_x, point_y in points:
            point = (
                (point_x + 0.5) * scale_x,
                (point_y + 0.5) * scale_y,
            )
            output.append(
                Prediction(
                    class_id=WEED_CLASS,
                    confidence=confidence,
                    box=box,
                    point=point,
                    keypoint_confidence=confidence,
                )
            )
    return tuple(output)


def crop_id_for_sample(
    ground_truth: Sequence[Instance],
    mapping: Mapping[int, int],
    fallback: int,
) -> tuple[int, str]:
    crop_classes = {item.class_id for item in ground_truth if item.class_id in mapping}
    if len(crop_classes) > 1:
        raise ValueError(f"WSD frame unexpectedly mixes crop classes: {crop_classes}")
    if crop_classes:
        source_class = next(iter(crop_classes))
        return int(mapping[source_class]), f"wsd_class_{source_class}"
    return int(fallback), "session_fallback_no_visible_crop_box"


@torch.inference_mode()
def infer_segmentation_split(
    model: torch.nn.Module,
    checkpoint: Mapping[str, Any],
    dataset_yaml: Path,
    split: str,
    *,
    raster_size: int,
    tile_size: int | None,
    tile_overlap: int,
    crop_mapping: Mapping[int, int],
    no_crop_fallback: int,
    configs: Sequence[GeneratorConfig],
    output: Path,
) -> tuple[dict[str, list[Sample]], dict[str, Any]]:
    root, image_paths = _dataset_split(dataset_yaml, split)
    transform = EvalTransform()
    device = next(model.parameters()).device
    training = checkpoint["config"]["training"]
    samples = {config.name: [] for config in configs}
    mask_output = output / "semantic_masks" / split
    mask_output.mkdir(parents=True, exist_ok=True)
    routing_counts: dict[str, int] = {}
    started = time.monotonic()
    for index, image_path in enumerate(image_paths, 1):
        with Image.open(image_path) as handle:
            source = handle.convert("RGB")
        original_width, original_height = source.size
        label_path = root / "labels" / split / f"{image_path.stem}.txt"
        ground_truth = _read_ground_truth(label_path, original_width, original_height)
        crop_id, routing_basis = crop_id_for_sample(
            ground_truth, crop_mapping, no_crop_fallback
        )
        routing_counts[routing_basis] = routing_counts.get(routing_basis, 0) + 1
        if source.size != (raster_size, raster_size):
            model_image = source.resize(
                (raster_size, raster_size), Image.Resampling.BILINEAR
            )
        else:
            model_image = source
        dummy = Image.new("L", model_image.size, 255)
        tensor, _ = transform(model_image, dummy)
        images = tensor.unsqueeze(0).to(device, non_blocking=True)
        crop_ids = torch.tensor([crop_id], dtype=torch.long, device=device)
        logits = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=bool(training.get("amp", True)),
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_trigger_pixels=0 if tile_size is not None else 2**63 - 1,
        )
        probabilities = logits[0].float().softmax(dim=0).cpu().numpy()
        semantic = probabilities.argmax(axis=0).astype(np.uint8)
        Image.fromarray(semantic, mode="L").save(mask_output / f"{image_path.stem}.png", optimize=True)
        features = _component_features(probabilities)
        peak_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for config in configs:
            samples[config.name].append(
                Sample(
                    image_path=image_path,
                    width=original_width,
                    height=original_height,
                    ground_truth=ground_truth,
                    predictions=predictions_from_features(
                        features,
                        config,
                        model_width=probabilities.shape[2],
                        model_height=probabilities.shape[1],
                        original_width=original_width,
                        original_height=original_height,
                        peak_cache=peak_cache,
                    ),
                )
            )
        if index % 25 == 0 or index == len(image_paths):
            print(
                f"{output.name}/{split}: {index}/{len(image_paths)} images",
                flush=True,
            )
    elapsed = time.monotonic() - started
    return samples, {
        "images": len(image_paths),
        "seconds": elapsed,
        "images_per_second": len(image_paths) / max(elapsed, 1e-9),
        "routing_counts": routing_counts,
    }


def _strategy_payload(config: GeneratorConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "mode": config.mode,
        "minimum_component_area_model_px": config.min_area_px,
        "score_kind": config.score_kind,
        "peak_min_distance_model_px": config.peak_min_distance_px,
    }


def _species_samples(samples: Sequence[Sample], source_class: int) -> list[Sample]:
    return [
        sample
        for sample in samples
        if any(item.class_id == source_class for item in sample.ground_truth)
    ]


def calibrate_and_evaluate(
    validation: Mapping[str, list[Sample]],
    test: Mapping[str, list[Sample]],
    configs: Sequence[GeneratorConfig],
    thresholds: Sequence[float],
    *,
    inference_image_size: int,
) -> dict[str, Any]:
    screen: list[dict[str, Any]] = []
    curves: dict[str, list[dict[str, Any]]] = {}
    config_by_name = {config.name: config for config in configs}
    for config in configs:
        curve = metric_curve(
            validation[config.name], thresholds, evaluate_weed_box_proxy
        )
        selection = choose_threshold(curve)
        curves[config.name] = curve
        screen.append(
            {
                "generator": _strategy_payload(config),
                "balanced_spot_selection": selection,
            }
        )
    selected = max(
        screen,
        key=lambda item: (
            float(item["balanced_spot_selection"]["validation_metrics"]["f1"]),
            float(item["balanced_spot_selection"]["validation_metrics"]["recall"]),
            item["generator"]["mode"] == "component",
            -int(item["generator"]["minimum_component_area_model_px"]),
        ),
    )
    selected_name = str(selected["generator"]["name"])
    selected_config = config_by_name[selected_name]
    selected_validation = validation[selected_name]
    selected_test = test[selected_name]
    spot_selection = selected["balanced_spot_selection"]
    spot_recall_selection = choose_recall_target(curves[selected_name], 0.95)
    strict_curve = metric_curve(
        selected_validation,
        thresholds,
        lambda samples, threshold: evaluate_actions(
            samples,
            threshold,
            tolerance_kind="box_diagonal_fraction",
            tolerance=0.10,
        ),
    )
    strict_selection = choose_threshold(strict_curve)
    spot_threshold = float(spot_selection["threshold"])
    strict_threshold = float(strict_selection["threshold"])
    spot_test = evaluate_weed_box_proxy(selected_test, spot_threshold)
    strict_test = evaluate_actions(
        selected_test,
        strict_threshold,
        tolerance_kind="box_diagonal_fraction",
        tolerance=0.10,
    )
    by_species: dict[str, Any] = {}
    for name, source_class in (("maize", 1), ("soybean", 2)):
        subset = _species_samples(selected_test, source_class)
        by_species[name] = {
            "images": len(subset),
            "weed_box_proxy": evaluate_weed_box_proxy(subset, spot_threshold),
            "stem_strict": evaluate_actions(
                subset,
                strict_threshold,
                tolerance_kind="box_diagonal_fraction",
                tolerance=0.10,
            ),
        }
    return {
        "generator_screen": screen,
        "selected_generator": _strategy_payload(selected_config),
        "validation": {
            "spot_balanced_selection": spot_selection,
            "spot_recall_95_selection": spot_recall_selection,
            "stem_strict_selection": strict_selection,
        },
        "test": {
            "weed_box_proxy": spot_test,
            "stem_strict": strict_test,
            "spot_recall_by_apparent_gt_box_size": weed_box_proxy_recall_by_apparent_size(
                selected_test,
                spot_threshold,
                inference_image_size=inference_image_size,
            ),
            "by_crop_species": by_species,
        },
        "selected_test_samples": selected_test,
    }


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
            }
            for item in sample.predictions
        ],
    }


def _write_gallery(
    samples: Sequence[Sample],
    semantic_mask_root: Path,
    output: Path,
    threshold: float,
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    per_image = [
        (
            float(evaluate_weed_box_proxy([sample], threshold)["f1"] or 0.0),
            sample,
        )
        for sample in samples
    ]
    per_image.sort(key=lambda item: (item[0], item[1].image_path.name))
    positions = np.linspace(0, len(per_image) - 1, min(6, len(per_image)), dtype=int)
    paths: list[str] = []
    font = ImageFont.load_default()
    for rank, position in enumerate(positions, 1):
        sample = per_image[int(position)][1]
        with Image.open(sample.image_path) as handle:
            source = handle.convert("RGB")
        with Image.open(semantic_mask_root / f"{sample.image_path.stem}.png") as handle:
            semantic = handle.resize(source.size, Image.Resampling.NEAREST)
        rgb = np.asarray(source, dtype=np.uint8).copy()
        mask = np.asarray(semantic, dtype=np.uint8) == PROJECT_WEED_CLASS
        overlay = rgb.astype(np.float32)
        overlay[mask] = overlay[mask] * 0.55 + np.asarray((255, 45, 45)) * 0.45
        image = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))
        draw = ImageDraw.Draw(image)
        for item in sample.ground_truth:
            colour = "#ff3030" if item.class_id == 0 else "#39d353"
            draw.rectangle(item.box, outline=colour, width=4)
            if item.class_id == 0 and item.point is not None:
                x, y = item.point
                draw.line((x - 8, y, x + 8, y), fill="#00e5ff", width=4)
                draw.line((x, y - 8, x, y + 8), fill="#00e5ff", width=4)
        for prediction in sample.predictions:
            if prediction.confidence < threshold:
                continue
            x, y = prediction.point
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline="#ffe100", width=4)
        banner = 92
        canvas = Image.new("RGB", (image.width, image.height + banner), "#101820")
        canvas.paste(image, (0, banner))
        text = ImageDraw.Draw(canvas)
        text.text((12, 8), "RED tint=predicted semantic weed | YELLOW=action", fill="white", font=font)
        text.text((12, 31), "GT weed box=RED | GT crop box=GREEN | GT stem=CYAN +", fill="white", font=font)
        metric = evaluate_weed_box_proxy([sample], threshold)
        text.text((12, 54), f"{sample.image_path.name} | spot P/R/F1={metric['precision']}/{metric['recall']}/{metric['f1']}", fill="white", font=font)
        path = output / f"{rank:02d}_{sample.image_path.stem}.jpg"
        canvas.resize((1048, 1094), Image.Resampling.LANCZOS).save(path, quality=90)
        paths.append(str(path))
    return paths


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    dataset_yaml = _resolve(data_root, config["pose_dataset_yaml"])
    dataset_receipt = _resolve(data_root, config["pose_dataset_receipt"])
    checkpoint_path = _resolve(data_root, config["segmentation_checkpoint"])
    detection_metrics_path = _resolve(data_root, config["detection_metrics"])
    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    if sha256(dataset_receipt) != str(config["pose_dataset_receipt_sha256"]):
        raise ValueError("WSD dataset receipt SHA mismatch")
    if sha256(checkpoint_path) != str(config["segmentation_checkpoint_sha256"]):
        raise ValueError("Accepted segmentation checkpoint SHA mismatch")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    output.mkdir(parents=True)
    model, checkpoint = load_checkpoint(checkpoint_path, torch.device("cuda"))
    model.eval()
    configs = generator_configs(config["action_generator_screen"])
    thresholds = confidence_thresholds(config["action_generator_screen"])
    routing = config["crop_routing"]
    crop_mapping = {
        int(source): int(target)
        for source, target in routing["wsd_class_to_project_crop_id"].items()
    }
    fallbacks = {
        str(split): int(value)
        for split, value in routing["no_crop_fallback_by_split"].items()
    }
    modes: dict[str, Any] = {}
    for mode_name, mode_config in config["inference_modes"].items():
        mode_output = output / mode_name
        mode_output.mkdir()
        inferred: dict[str, dict[str, list[Sample]]] = {}
        runtime: dict[str, Any] = {}
        for split in ("val", "test"):
            inferred[split], runtime[split] = infer_segmentation_split(
                model,
                checkpoint,
                dataset_yaml,
                split,
                raster_size=int(mode_config["raster_size"]),
                tile_size=(
                    None
                    if mode_config.get("tile_size") is None
                    else int(mode_config["tile_size"])
                ),
                tile_overlap=int(mode_config.get("tile_overlap", 0)),
                crop_mapping=crop_mapping,
                no_crop_fallback=fallbacks[split],
                configs=configs,
                output=mode_output,
            )
        result = calibrate_and_evaluate(
            inferred["val"],
            inferred["test"],
            configs,
            thresholds,
            inference_image_size=int(mode_config["raster_size"]),
        )
        selected_samples = result.pop("selected_test_samples")
        selected_name = result["selected_generator"]["name"]
        threshold = float(result["validation"]["spot_balanced_selection"]["threshold"])
        cache_path = mode_output / "selected_predictions_test.json"
        cache_path.write_text(
            json.dumps([_sample_payload(sample) for sample in selected_samples]) + "\n",
            encoding="utf-8",
        )
        gallery = _write_gallery(
            selected_samples,
            mode_output / "semantic_masks/test",
            mode_output / "gallery",
            threshold,
        )
        modes[mode_name] = {
            "inference": dict(mode_config),
            "runtime": runtime,
            "calibration_and_test": result,
            "artifacts": {
                "selected_prediction_cache": str(cache_path),
                "semantic_mask_root": str(mode_output / "semantic_masks"),
                "gallery": gallery,
            },
        }
        print(
            f"{mode_name}: selected {selected_name}, test spot F1="
            f"{result['test']['weed_box_proxy']['f1']}",
            flush=True,
        )
    detection_metrics = json.loads(detection_metrics_path.read_text(encoding="utf-8"))
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "offline_research_comparison_not_field_validated",
        "provenance": {
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "dataset_yaml": str(dataset_yaml),
            "dataset_yaml_sha256": sha256(dataset_yaml),
            "dataset_receipt": str(dataset_receipt),
            "dataset_receipt_sha256": sha256(dataset_receipt),
            "segmentation_checkpoint": str(checkpoint_path),
            "segmentation_checkpoint_sha256": sha256(checkpoint_path),
            "evaluation_source_commit": config["evaluation_source_commit"],
            "checkpoint_runtime_provenance": checkpoint["runtime_provenance"],
            "detection_metrics": str(detection_metrics_path),
            "detection_metrics_sha256": sha256(detection_metrics_path),
        },
        "keypoint_annotation_origin": {
            "source": "publisher WSD labelled.zip/labelled/points_labels",
            "generated_by_this_project": False,
            "pairing": "same row order as publisher box labels",
            "visible_points": {"train": 1435, "val": 1549, "test": 1097},
            "missing_weed_points_total": 34,
        },
        "comparison_interpretation": {
            "segmentation_wsd_training_frames": 0,
            "detection_wsd_training_frames": 211,
            "detection_wsd_train_weed_boxes": 1437,
            "pose_wsd_train_visible_stem_points": 1435,
            "causal_limit": "Difference combines target-domain annotation and task/model architecture; WSD has no masks for an equal target-trained segmentation specialist.",
        },
        "segmentation_modes": modes,
        "reference_detection": detection_metrics["strategies"]["detection_only_box_center"],
        "reference_pose_keypoint": detection_metrics["strategies"]["pose_keypoint"],
        "claims": list(config["claims"]),
        "limitations": [
            "WSD has no semantic masks, so segmentation IoU and target-trained segmentation are unavailable.",
            "The action generator is validation-selected on one maize-dominant date and evaluated on the previously inspected development test date.",
            "Known crop identity routing is assumed from the field plan; it is not automatic crop recognition.",
            "Bounding-box hits can land on soil and are not spray deposition or kill.",
            "No tracking, GSD, nozzle footprint, latency compensation, or crop injury outcome is measured.",
        ],
    }
    receipt_path = output / "segmentation_vs_detection_metrics.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/wsd_segmentation_spot_spray_v1.yaml"),
    )
    arguments = parser.parse_args()
    result = run(arguments.config)
    summary: dict[str, Any] = {}
    for mode_name, mode in result["segmentation_modes"].items():
        evaluation = mode["calibration_and_test"]
        summary[mode_name] = {
            "selected_generator": evaluation["selected_generator"],
            "spot": evaluation["test"]["weed_box_proxy"],
            "stem": evaluation["test"]["stem_strict"],
        }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
