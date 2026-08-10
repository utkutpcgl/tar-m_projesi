#!/usr/bin/env python3
"""Measure whether apparent-size gating creates a high-success spray regime."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence

from scripts.evaluate_wsd_action_poc_v1 import (
    Instance,
    Prediction,
    Sample,
    choose_threshold,
    deduplicate_action_points,
    point_footprint_hits_box,
    prf,
)
from scripts.evaluate_wsd_detection_spot_spray_v1 import (
    _weed_box_proxy_matches,
    _weed_gt,
    _weed_predictions,
    choose_recall_target,
    metric_curve,
)


DEFAULT_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/"
    "wsd_detection_poc_v1/yolo26s_detect_1024_seed17/"
    "spot_spray_ab_1024_final_v1"
)
DEFAULT_OUTPUT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "wsd_spot_success_conditions_v1/detection_gt_size_conditioned.json"
)


def load_samples(path: Path) -> list[Sample]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples: list[Sample] = []
    for row in payload:
        samples.append(
            Sample(
                image_path=Path(row["image_path"]),
                width=int(row["width"]),
                height=int(row["height"]),
                ground_truth=tuple(
                    Instance(
                        class_id=int(item["class_id"]),
                        box=tuple(float(value) for value in item["box"]),
                        point=(
                            None
                            if item["point"] is None
                            else tuple(float(value) for value in item["point"])
                        ),
                    )
                    for item in row["ground_truth"]
                ),
                predictions=tuple(
                    Prediction(
                        class_id=int(item["class_id"]),
                        confidence=float(item["confidence"]),
                        box=tuple(float(value) for value in item["box"]),
                        point=tuple(float(value) for value in item["point"]),
                        keypoint_confidence=float(item["keypoint_confidence"]),
                    )
                    for item in row["predictions"]
                ),
            )
        )
    return samples


def apparent_box_size(
    box: tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
    inference_image_size: int,
) -> float:
    scale = min(inference_image_size / image_width, inference_image_size / image_height)
    width = max(0.0, box[2] - box[0]) * scale
    height = max(0.0, box[3] - box[1]) * scale
    return math.sqrt(width * height)


def _count_target_weeds(samples: Sequence[Sample]) -> int:
    return sum(
        item.class_id == 0 for sample in samples for item in sample.ground_truth
    )


def evaluate_gt_size_conditioned_spot(
    samples: Sequence[Sample],
    threshold: float,
    *,
    minimum_gt_size_px: float,
    inference_image_size: int,
) -> dict[str, Any]:
    """Score eligible GT weeds while ignoring valid hits on smaller weeds.

    This answers the conditional question "how well are targets that appear at
    least N pixels handled?"  Background/duplicate/crop actions remain false
    positives.  A one-to-one action matched to a real but smaller weed is
    ignored instead of being mislabeled as a false action.
    """
    true_positive = false_positive = false_negative = actions = 0
    ignored_small_target_actions = crop_collisions = 0
    eligible_targets = excluded_targets = 0
    for sample in samples:
        predictions = _weed_predictions(sample, threshold, action=True)
        ground_truth = _weed_gt(sample)
        eligible = [
            apparent_box_size(
                item.box,
                image_width=sample.width,
                image_height=sample.height,
                inference_image_size=inference_image_size,
            )
            >= minimum_gt_size_px
            for item in ground_truth
        ]
        matches = _weed_box_proxy_matches(predictions, ground_truth, 0.0)
        matched_prediction_indices = {pair[0] for pair in matches}
        matched_eligible = sum(eligible[gt_index] for _, gt_index in matches)
        ignored = sum(not eligible[gt_index] for _, gt_index in matches)
        considered_prediction_indices = [
            index
            for index in range(len(predictions))
            if index not in matched_prediction_indices
        ]
        considered_prediction_indices.extend(
            prediction_index
            for prediction_index, gt_index in matches
            if eligible[gt_index]
        )
        crop_boxes = [
            item.box for item in sample.ground_truth if item.class_id != 0
        ]
        crop_collisions += sum(
            any(
                point_footprint_hits_box(predictions[index].point, box, 0.0)
                for box in crop_boxes
            )
            for index in considered_prediction_indices
        )
        eligible_count = sum(eligible)
        true_positive += matched_eligible
        false_negative += eligible_count - matched_eligible
        false_positive += len(predictions) - len(matches)
        actions += len(considered_prediction_indices)
        ignored_small_target_actions += ignored
        eligible_targets += eligible_count
        excluded_targets += len(eligible) - eligible_count
    result = prf(true_positive, false_positive, false_negative)
    result.update(
        {
            "confidence_threshold": threshold,
            "minimum_gt_apparent_size_px": minimum_gt_size_px,
            "inference_image_size": inference_image_size,
            "size_definition": "sqrt(GT weed box area) after full-frame model-input scale",
            "definition": "one-to-one action intersection with an eligible GT weed box; matched smaller weeds ignored",
            "actions_scored": actions,
            "eligible_gt_weed_boxes": eligible_targets,
            "excluded_smaller_gt_weed_boxes": excluded_targets,
            "ignored_actions_hitting_smaller_weeds": ignored_small_target_actions,
            "crop_as_weed_false_fire": {
                "actions": crop_collisions,
                "rate_per_action": crop_collisions / actions if actions else None,
            },
        }
    )
    return result


def _choose_balanced_or_zero_action_fallback(
    curve: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Select balanced F1, while preserving an honest all-missed regime.

    The shared metric helper represents precision/F1 as undefined when a
    detector emits no actions.  For a positive validation set that is still a
    meaningful (failed) result, so retain the maximum-recall operating point
    instead of aborting the complete size analysis.
    """
    try:
        selected = choose_threshold(curve)
        selected["selection_status"] = "defined_f1"
        return selected
    except ValueError as error:
        if "No defined F1" not in str(error):
            raise
    usable = [item for item in curve if item["recall"] is not None]
    if not usable:
        raise ValueError("No defined recall values in threshold curve")
    selected_metric = max(
        usable,
        key=lambda item: (
            float(item["recall"]),
            float(item["precision"] or 0.0),
            -float(item["confidence_threshold"]),
        ),
    )
    return {
        "threshold": selected_metric["confidence_threshold"],
        "validation_metrics": selected_metric,
        "crop_false_fire_gate_passed": None,
        "maximum_crop_false_fire_rate": None,
        "selection_status": "no_defined_f1_all_actions_missed",
        "effective_f1_for_interpretation": 0.0,
    }


def _evaluate_regime(
    train: Sequence[Sample],
    validation: Sequence[Sample],
    test: Sequence[Sample],
    thresholds: Sequence[float],
    *,
    minimum_gt_size_px: float,
    inference_image_size: int,
) -> dict[str, Any]:
    evaluator = lambda samples, threshold: evaluate_gt_size_conditioned_spot(
        samples,
        threshold,
        minimum_gt_size_px=minimum_gt_size_px,
        inference_image_size=inference_image_size,
    )
    spot_curve = metric_curve(validation, thresholds, evaluator)
    spot_selection = _choose_balanced_or_zero_action_fallback(spot_curve)
    recall_selection = choose_recall_target(spot_curve, 0.95)
    spot_threshold = float(spot_selection["threshold"])
    return {
        "target_weed_counts": {
            "train_all": _count_target_weeds(train),
            "val_all": _count_target_weeds(validation),
            "test_all": _count_target_weeds(test),
            "train_eligible": evaluator(train, 0.0)["eligible_gt_weed_boxes"],
            "val_eligible": evaluator(validation, 0.0)["eligible_gt_weed_boxes"],
            "test_eligible": evaluator(test, 0.0)["eligible_gt_weed_boxes"],
        },
        "validation": {
            "spot_balanced_selection": spot_selection,
            "spot_recall_95_selection": recall_selection,
        },
        "test": {
            "spot_balanced": evaluator(test, spot_threshold),
            "spot_recall_95_policy": evaluator(
                test, float(recall_selection["threshold"])
            ),
        },
        "seen_train_diagnostic": {
            "role": "training-date diagnostic with validation-frozen thresholds; not generalization evidence",
            "spot_balanced": evaluator(train, spot_threshold),
        },
    }


def run(root: Path, output: Path, *, inference_image_size: int = 1024) -> dict[str, Any]:
    metrics_path = root / "spot_spray_ab_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    fraction = float(
        metrics["strategies"]["detection_only_box_center"]["validation"]
        ["spot_spray_calibration"]["selected_deduplication_fraction"]
    )
    raw = {
        split: load_samples(root / f"predictions_detection_{split}.json")
        for split in ("train", "val", "test")
    }
    deduplicated = {
        split: deduplicate_action_points(samples, fraction)
        for split, samples in raw.items()
    }
    thresholds = [round(value / 100.0, 2) for value in range(1, 100)]
    regimes: dict[str, Any] = {}
    for minimum_size in (0, 14, 28, 42, 56):
        regimes[str(minimum_size)] = _evaluate_regime(
            deduplicated["train"],
            deduplicated["val"],
            deduplicated["test"],
            thresholds,
            minimum_gt_size_px=float(minimum_size),
            inference_image_size=inference_image_size,
        )
    result = {
        "schema_version": 1,
        "protocol": "wsd_detection_gt_size_conditioned_spot_spray_v1",
        "status": "offline_development_diagnostic_not_field_validated",
        "source_metrics": str(metrics_path),
        "inference_image_size": inference_image_size,
        "deduplication_fraction_frozen_from_all_size_validation": fraction,
        "size_definition": "sqrt(GT weed box area) after full-frame model-input scale",
        "regimes": regimes,
        "limitations": [
            "Each regime retunes confidence on validation and is a development diagnostic.",
            "This conditions on annotated GT size; it is analysis, not a deployable predicted-size gate.",
            "Actions correctly matched to smaller weeds are ignored; background, duplicate, and crop actions remain false positives.",
            "A box-proxy hit is not weed-tissue deposition or kill.",
            "The >=28px test subset has 163 weeds and supports a directional estimate, not a field guarantee.",
            "The >=56px test regime has only one GT weed and cannot support a conclusion.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--image-size", type=int, default=1024)
    arguments = parser.parse_args()
    result = run(
        arguments.root.expanduser().resolve(),
        arguments.output.expanduser().resolve(),
        inference_image_size=arguments.image_size,
    )
    summary = {
        minimum: {
            "target_test_weeds": regime["target_weed_counts"]["test_eligible"],
            "test_spot": regime["test"]["spot_balanced"],
            "seen_train_spot": regime["seen_train_diagnostic"]["spot_balanced"],
        }
        for minimum, regime in result["regimes"].items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
