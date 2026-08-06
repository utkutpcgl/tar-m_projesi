#!/usr/bin/env python3
"""Create self-contained paired camera-condition segmentation comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from agri_seg.constants import CLASS_NAMES, CROP, IGNORE, WEED
from agri_seg.data import EvalTransform
from agri_seg.engine import load_checkpoint, predict_logits
from agri_seg.manifest import SampleRecord, read_manifest


DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
MANIFEST = DATA_ROOT / "processed/manifests/camera_optics_ablation_v1.csv"
CHECKPOINT = (
    DATA_ROOT
    / "runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt"
)
OUTPUT = DATA_ROOT / "processed/audits/camera_optics_intervention_v1/gallery"
PREFIX = "camera_optics_ablation_v1_"
GROUPS: dict[str, tuple[str, ...]] = {
    "01_resolution_same_scene": (
        "resolution_256",
        "reference_512",
        "resolution_768",
        "resolution_1024",
    ),
    "02_optical_zoom_same_scene": ("reference_512", "zoom_1p33", "zoom_1p67"),
    "03_focus_motion_same_scene": (
        "reference_512",
        "defocus_sigma1p5",
        "defocus_sigma3p0",
        "motion_blur_7px",
    ),
    "04_low_light_camera_light_same_scene": (
        "dim_no_led",
        "dim_led_energy30",
        "dim_led_energy60",
        "dim_led_energy120",
    ),
    "05_model_raster_same_capture": (
        "digital_input_256",
        "detail_loss_256_up512",
        "reference_512",
        "digital_upscale_1024",
    ),
}
GROUP_TITLES = {
    "01_resolution_same_scene": "Aynı saha: native görüntü çözünürlüğü",
    "02_optical_zoom_same_scene": "Aynı saha: optik zoom / daha dar görüş alanı",
    "03_focus_motion_same_scene": "Aynı capture: focus ve hareket bulanıklığı",
    "04_low_light_camera_light_same_scene": "Aynı düşük-ışık sahnesi: kamera ışığı sweep'i",
    "05_model_raster_same_capture": "Aynı capture: model giriş rasterı",
}
CONDITION_LABELS = {
    "resolution_256": "Native 256",
    "reference_512": "Referans 512",
    "resolution_768": "Native 768",
    "resolution_1024": "Native 1024",
    "zoom_1p33": "Optik zoom 1,33×",
    "zoom_1p67": "Optik zoom 1,67×",
    "defocus_sigma1p5": "Defocus σ=1,5 px",
    "defocus_sigma3p0": "Defocus σ=3,0 px",
    "motion_blur_7px": "Hareket blur 7 px",
    "dim_no_led": "Düşük ışık • lamba kapalı",
    "dim_led_energy30": "Kamera ışığı E30",
    "dim_led_energy60": "Kamera ışığı E60",
    "dim_led_energy120": "Kamera ışığı E120",
    "digital_input_256": "Dijital girdi 256",
    "detail_loss_256_up512": "256'ya indir → 512",
    "digital_upscale_1024": "512'den dijital 1024",
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size=size)


def _overlay(image: Image.Image, classes: np.ndarray, alpha: float = 0.50) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    color = np.zeros_like(rgb)
    selected = (classes == CROP) | (classes == WEED)
    color[classes == CROP] = (35, 220, 55)
    color[classes == WEED] = (235, 45, 40)
    rgb[selected] = (1.0 - alpha) * rgb[selected] + alpha * color[selected]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def _metrics(target: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    valid = target != IGNORE
    encoded = target[valid].astype(np.int64) * 3 + predicted[valid].astype(np.int64)
    confusion = np.bincount(encoded, minlength=9).reshape(3, 3)
    true_positive = np.diag(confusion).astype(np.float64)
    union = confusion.sum(axis=0) + confusion.sum(axis=1) - true_positive
    iou = np.divide(
        true_positive,
        union,
        out=np.full(3, np.nan, dtype=np.float64),
        where=union > 0,
    )
    return {
        "mean_iou": float(np.nanmean(iou)),
        "iou": {name: float(iou[index]) for index, name in enumerate(CLASS_NAMES)},
        "confusion": confusion.tolist(),
    }


@torch.inference_mode()
def _predict(
    model: torch.nn.Module,
    checkpoint: dict[str, Any],
    record: SampleRecord,
) -> tuple[Image.Image, np.ndarray, np.ndarray, dict[str, Any]]:
    image_path, mask_path = DATA_ROOT / record.image_path, DATA_ROOT / record.mask_path
    with Image.open(image_path) as handle:
        image = handle.convert("RGB")
    with Image.open(mask_path) as handle:
        mask = handle.convert("L")
    image_tensor, target_tensor = EvalTransform()(image, mask)
    height, width = target_tensor.shape
    pad_height = (-height) % 32
    pad_width = (-width) % 32
    model_input = torch.nn.functional.pad(
        image_tensor.unsqueeze(0), (0, pad_width, 0, pad_height)
    ).cuda()
    crop_ids = torch.tensor([record.target_crop_id], device="cuda")
    training = checkpoint["config"]["training"]
    logits = predict_logits(
        model,
        model_input,
        crop_ids,
        use_amp=bool(training.get("amp", True)),
        tile_size=training.get("eval_tile_size"),
        tile_overlap=int(training.get("eval_tile_overlap", 128)),
        tile_trigger_pixels=int(training.get("eval_tile_trigger_pixels", 4_000_000)),
    )
    predicted = logits[0, :, :height, :width].argmax(dim=0).cpu().numpy()
    target = target_tensor.numpy()
    return image, target, predicted, _metrics(target, predicted)


def _comparison(
    title: str,
    conditions: Sequence[str],
    outputs: dict[str, tuple[Image.Image, np.ndarray, np.ndarray, dict[str, Any]]],
    destination: Path,
) -> None:
    panel_width = 480
    view = 380
    header = 120
    caption = 96
    canvas = Image.new(
        "RGB",
        (panel_width * len(conditions), header + 2 * view + caption),
        (247, 248, 244),
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 12), title, fill=(25, 38, 33), font=_font(30, True))
    draw.text(
        (20, 57),
        "Üst: model çıktısı | Alt: ground truth | Yeşil: crop | Kırmızı: weed",
        fill=(75, 87, 82),
        font=_font(21),
    )
    for index, condition in enumerate(conditions):
        image, target, predicted, metrics = outputs[condition]
        display = image.resize((view, view), Image.Resampling.LANCZOS)
        target_small = np.asarray(
            Image.fromarray(target.astype(np.uint8)).resize((view, view), Image.Resampling.NEAREST)
        )
        predicted_small = np.asarray(
            Image.fromarray(predicted.astype(np.uint8)).resize((view, view), Image.Resampling.NEAREST)
        )
        model_overlay = _overlay(display, predicted_small)
        gt_overlay = _overlay(display, target_small)
        left = index * panel_width + (panel_width - view) // 2
        canvas.paste(model_overlay, (left, header))
        canvas.paste(gt_overlay, (left, header + view))
        caption_left = index * panel_width + (panel_width - view) // 2
        label = CONDITION_LABELS.get(condition, condition.replace("_", " "))
        draw.text((caption_left, header + 2 * view + 6), label, fill=(25, 38, 33), font=_font(18, True))
        draw.text(
            (caption_left, header + 2 * view + 36),
            f"mIoU {metrics['mean_iou'] * 100:.1f}%  |  crop IoU {metrics['iou']['target_crop'] * 100:.1f}%",
            fill=(70, 80, 76),
            font=_font(15),
        )
        draw.text(
            (caption_left, header + 2 * view + 61),
            f"weed IoU {metrics['iou']['other_vegetation'] * 100:.1f}%",
            fill=(70, 80, 76),
            font=_font(15),
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=92, optimize=True)


def build(scene: str, frame: str) -> Path:
    wanted = {
        condition for conditions in GROUPS.values() for condition in conditions
    }
    records: dict[str, SampleRecord] = {}
    for record in read_manifest(MANIFEST):
        if f":{scene}:{frame}" not in record.sample_id:
            continue
        condition = record.dataset_id.removeprefix(PREFIX)
        if condition in wanted:
            records[condition] = record
    missing = wanted - set(records)
    if missing:
        raise RuntimeError(f"Missing paired conditions: {sorted(missing)}")
    model, checkpoint = load_checkpoint(CHECKPOINT, torch.device("cuda"))
    model.eval()
    outputs = {
        condition: _predict(model, checkpoint, records[condition])
        for condition in sorted(wanted)
    }
    for name, conditions in GROUPS.items():
        _comparison(
            GROUP_TITLES[name],
            conditions,
            outputs,
            OUTPUT / f"{name}.jpg",
        )
    summary = {
        "scene": scene,
        "frame": frame,
        "legend": {"crop": "green", "weed": "red"},
        "conditions": {condition: outputs[condition][3] for condition in sorted(outputs)},
        "files": [str(OUTPUT / f"{name}.jpg") for name in GROUPS],
    }
    destination = OUTPUT / "summary.json"
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", default="scene_0004")
    parser.add_argument("--frame", default="frame_0001")
    args = parser.parse_args()
    print(build(args.scene, args.frame))


if __name__ == "__main__":
    main()
