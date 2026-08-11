#!/usr/bin/env python3
"""Measure action and tissue diagnostics on split-disjoint synthetic holdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_phenobench_cropcraft_deploy_action_ab_v1 import (
    METHODS,
    eligibility_view,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    classify_point,
    evaluate_actions,
    evaluate_segment_tissue,
    infer_actions,
    load_ground_truth,
    maximum_excess_green_point,
    release_cuda,
    select_threshold,
    sha256,
    threshold_curve,
)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def evaluate_resolution(
    model: Any,
    validation: Sequence[GroundTruth],
    test: Sequence[GroundTruth],
    inference: Mapping[str, Any],
    thresholds: np.ndarray,
    size_views: Sequence[float],
    primary_method: str,
    primary_size: float,
) -> dict[str, Any]:
    validation_actions, validation_timing = infer_actions(
        model, "segment", validation, inference
    )
    test_actions, test_timing = infer_actions(model, "segment", test, inference)
    output: dict[str, Any] = {
        "timing": {"validation": validation_timing, "test": test_timing},
        "methods": {},
    }
    primary_threshold: float | None = None
    primary_test_view: list[GroundTruth] | None = None
    for method in METHODS:
        views: dict[str, Any] = {}
        for minimum in size_views:
            val_view, val_actions = eligibility_view(
                validation, validation_actions[method], minimum
            )
            test_view, test_action_view = eligibility_view(
                test, test_actions[method], minimum
            )
            selection = select_threshold(
                threshold_curve(val_actions, val_view, thresholds)
            )
            selected = float(selection["balanced_max_f1"]["threshold"])
            test_metric = evaluate_actions(
                test_action_view, test_view, selected, include_per_sample=True
            )
            views[str(int(minimum))] = {
                "minimum_sqrt_gt_box_area_px": float(minimum),
                "validation_calibration": selection,
                "test": test_metric,
            }
            if method == primary_method and float(minimum) == primary_size:
                primary_threshold = selected
                primary_test_view = test_view
        output["methods"][method] = {"eligible_size_views": views}
    if primary_threshold is None or primary_test_view is None:
        raise ValueError("Primary method/size is absent from diagnostic grid")
    output["primary_service"] = {
        "method": primary_method,
        "minimum_sqrt_gt_box_area_px": primary_size,
        "threshold": primary_threshold,
        "tissue": evaluate_segment_tissue(
            model, primary_test_view, primary_threshold, inference
        ),
    }
    release_cuda(model)
    return output


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(
        str(Path("/usr/share/fonts/truetype/dejavu") / filename), size=size
    )


def _blend(image: Image.Image, mask: np.ndarray, colour: tuple[int, int, int]) -> None:
    overlay = Image.new("RGB", image.size, colour)
    image.paste(overlay, (0, 0), Image.fromarray(mask.astype(np.uint8) * 100))


def _resize_mask(raw: Any, shape: tuple[int, int]) -> np.ndarray:
    array = raw.ge(0.5).to(torch.uint8).cpu().numpy()
    if array.shape != shape:
        array = cv2.resize(
            array, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST
        )
    return array.astype(bool, copy=False)


def render_example(
    model: Any,
    truth: GroundTruth,
    *,
    threshold: float,
    inference: Mapping[str, Any],
    output: Path,
    title: str = "Unseen sentetik holdout — noktasal ilaçlama tanısı",
) -> None:
    rgb = Image.open(truth.image_path).convert("RGB")
    semantics = np.asarray(Image.open(truth.semantics_path), dtype=np.uint16)
    instances = np.asarray(Image.open(truth.instances_path), dtype=np.uint16)
    gt_panel, prediction_panel = rgb.copy(), rgb.copy()
    _blend(gt_panel, semantics == 1, (38, 196, 91))
    _blend(gt_panel, semantics == 2, (239, 68, 68))
    result = model.predict(
        source=str(truth.image_path),
        imgsz=int(inference["image_size"]),
        conf=float(threshold),
        iou=float(inference["nms_iou"]),
        max_det=int(inference["max_detections"]),
        device=int(inference["device"]),
        retina_masks=True,
        verbose=False,
    )[0]
    points: list[tuple[tuple[int, int], str]] = []
    if result.boxes is not None and result.masks is not None:
        classes = result.boxes.cls.detach().cpu().numpy().astype(np.int64)
        masks = [_resize_mask(raw, semantics.shape) for raw in result.masks.data]
        crop_union = np.zeros(semantics.shape, dtype=bool)
        for class_id, mask in zip(classes, masks, strict=True):
            if int(class_id) == 1:
                crop_union |= mask
                _blend(prediction_panel, mask, (38, 196, 91))
        for class_id, mask in zip(classes, masks, strict=True):
            if int(class_id) != 0:
                continue
            _blend(prediction_panel, mask, (168, 85, 247))
            safe = np.logical_and(mask, ~crop_union)
            point = maximum_excess_green_point(
                safe, np.asarray(rgb, dtype=np.uint8)
            )
            if point is None:
                continue
            kind, _ = classify_point(*point, semantics, instances, truth)
            points.append((point, kind))
    draw_prediction = ImageDraw.Draw(prediction_panel)
    for (x, y), kind in points:
        colour = (0, 210, 255) if kind == "weed" else (255, 210, 0)
        radius = 12
        draw_prediction.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=colour,
            outline="white",
            width=3,
        )
        if kind != "weed":
            draw_prediction.line(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(180, 0, 0),
                width=4,
            )
            draw_prediction.line(
                (x - radius, y + radius, x + radius, y - radius),
                fill=(180, 0, 0),
                width=4,
            )
    panels = [rgb, gt_panel, prediction_panel]
    panel_size = 480
    canvas = Image.new("RGB", (panel_size * 3, 650), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (22, 14),
        title,
        fill="#111827",
        font=_font(25, bold=True),
    )
    titles = ("Kamera RGB", "Gerçek maske", "Model + atış noktası")
    for index, (panel, title) in enumerate(zip(panels, titles, strict=True)):
        left = index * panel_size
        draw.text((left + 12, 58), title, fill="#111827", font=_font(20, bold=True))
        canvas.paste(
            panel.resize((panel_size, panel_size), Image.Resampling.LANCZOS),
            (left, 90),
        )
    draw.text(
        (22, 586),
        "Etiket: yeşil=mahsul, kırmızı=yabani ot | Tahmin: yeşil=mahsul, mor=ot",
        fill="#111827",
        font=_font(18),
    )
    draw.text(
        (22, 615),
        "Nokta: mavi=ot dokusuna güvenli temas, sarı/çarpı=hatalı müdahale",
        fill="#111827",
        font=_font(18),
    )
    canvas.save(output, quality=94, subsampling=0)


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {name: False for name in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb")}
    )
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(PROJECT_ROOT, config["data_root"])
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    receipt_path = resolve(data_root, config["dataset_receipt"])
    dataset_yaml = resolve(data_root, config["dataset_yaml"])
    for path, expected in (
        (receipt_path, str(config["dataset_receipt_sha256"])),
        (dataset_yaml, str(config["dataset_yaml_sha256"])),
    ):
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Locked dataset input mismatch: {path}")
    dataset_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if dataset_receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Synthetic dataset gate did not pass")
    if float(dataset_receipt["evaluation_policy"]["real_model_selection_score_weight"]) != 0.0:
        raise RuntimeError("Synthetic score weight must remain zero")
    membership = Path(dataset_receipt["membership"])
    if sha256(membership) != dataset_receipt["membership_sha256"]:
        raise ValueError("Synthetic membership hash mismatch")
    minimum_area = int(dataset_receipt["label_contract"]["minimum_component_area_px"])
    validation = load_ground_truth(membership, "val", minimum_area)
    test = load_ground_truth(membership, "test", minimum_area)
    threshold_cfg = config["thresholds"]
    thresholds = np.arange(
        float(threshold_cfg["start"]),
        float(threshold_cfg["stop"]) + 1e-9,
        float(threshold_cfg["step"]),
    )
    size_views = [float(value) for value in config["eligible_minimum_sqrt_box_px"]]
    primary_method = str(config["primary_method"])
    primary_size = float(config["primary_service_minimum_sqrt_box_px"])
    inference_base = dict(config["inference"])
    image_sizes = [int(value) for value in inference_base.pop("image_sizes")]
    native_size = int(inference_base.pop("native_tile_size"))
    locked_models: dict[str, Any] = {}
    results: dict[str, Any] = {}
    loaded: dict[str, Any] = {}
    for model_name, model_cfg in config["models"].items():
        checkpoint = resolve(data_root, model_cfg["checkpoint"])
        if not checkpoint.is_file() or sha256(checkpoint) != str(model_cfg["checkpoint_sha256"]):
            raise ValueError(f"Locked model mismatch: {model_name}")
        model = YOLO(str(checkpoint))
        if model.task != "segment":
            raise ValueError(f"Model is not segmentation: {model_name}")
        loaded[model_name] = model
        locked_models[model_name] = {"checkpoint": str(checkpoint), "sha256": sha256(checkpoint)}
        model_results: dict[str, Any] = {}
        for image_size in image_sizes:
            inference = {**inference_base, "image_size": image_size}
            model_results[str(image_size)] = evaluate_resolution(
                model,
                validation,
                test,
                inference,
                thresholds,
                size_views,
                primary_method,
                primary_size,
            )
            model_results[str(image_size)]["software_resampling_only"] = image_size != native_size
        results[model_name] = model_results
    output = resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    gallery_cfg = config["gallery"]
    gallery_model = str(gallery_cfg["model"])
    if gallery_model not in loaded:
        raise ValueError("Gallery model must be selected from evaluated real A/B arms")
    gallery_size = int(gallery_cfg["image_size"])
    primary_row = results[gallery_model][str(gallery_size)]["methods"][primary_method]["eligible_size_views"][str(int(primary_size))]
    gallery_threshold = float(primary_row["validation_calibration"]["balanced_max_f1"]["threshold"])
    gallery_root = output / "gallery"
    gallery_root.mkdir()
    gallery_rows = []
    for index in [int(value) for value in gallery_cfg["test_indices"]]:
        truth = test[index]
        path = gallery_root / f"synthetic_test_{index:02d}.jpg"
        render_example(
            loaded[gallery_model],
            truth,
            threshold=gallery_threshold,
            inference={**inference_base, "image_size": gallery_size},
            output=path,
        )
        gallery_rows.append({"sample_id": truth.sample_id, "path": str(path), "sha256": sha256(path)})
    for model in loaded.values():
        release_cuda(model)
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "synthetic_diagnostic_complete_zero_real_selection_weight",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_receipt": str(receipt_path),
        "dataset_receipt_sha256": sha256(receipt_path),
        "locked_models": locked_models,
        "native_tile_size": native_size,
        "image_sizes": image_sizes,
        "results": results,
        "gallery": {"model": gallery_model, "image_size": gallery_size, "threshold": gallery_threshold, "frames": gallery_rows},
        "real_model_selection_score_weight": 0.0,
        "claims": config["claims"],
        "limitations": [
            "Synthetic connected regions are not botanical plant instances.",
            "Renderer appearance and illumination are not a physical camera calibration.",
            "Only sixteen synthetic validation and sixteen synthetic test tiles are available.",
        ],
    }
    metrics = output / "synthetic_diagnostic_metrics.json"
    metrics.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Sentetik unseen holdout\n\nYeşil mahsul, kırmızı gerçek yabani ot, mor model ot tahmini; mavi nokta doğru ve sarı çarpı hatalı müdahaledir. Bu set gerçek model seçiminde ağırlık taşımaz.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": receipt["status"], "metrics": str(metrics), "gallery": gallery_rows}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/cropcraft_deploy_synthetic_diagnostic_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
