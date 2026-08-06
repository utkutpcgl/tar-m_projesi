#!/usr/bin/env python3
"""Build model-independent qualitative comparisons for selected A/B winners."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader

from agri_seg.constants import CROP, WEED
from agri_seg.data import (
    EvalTransform,
    ManifestDataset,
    load_rgb_image,
    padded_collate,
    to_display_pil,
)
from agri_seg.engine import load_checkpoint, predict_logits
from agri_seg.manifest import SampleRecord, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
DOMAIN_RESULT = DATA_ROOT / "processed/audits/domain_adaptation_curve_v1/results.json"
SMALL_RESULT = DATA_ROOT / "processed/audits/small_object_training_ablation_v1/results.json"
OUTPUT = DATA_ROOT / "processed/audits/camera_domain_report_v1/gallery"

GREEN = np.asarray([25, 210, 70], dtype=np.float32)
RED = np.asarray([235, 45, 55], dtype=np.float32)
INK = (27, 37, 44)
MUTED = (87, 101, 112)
BG = (244, 247, 244)
WHITE = (255, 255, 255)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(path), size=size)


def quantile_indices(length: int, count: int) -> list[int]:
    if length <= 0 or count <= 0:
        return []
    count = min(length, count)
    if count == 1:
        return [(length - 1) // 2]
    return [round(index * (length - 1) / (count - 1)) for index in range(count)]


def _resolve(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _short_candidate(name: str) -> str:
    return (
        name.replace("domainadapt_sorghum_", "")
        .replace("smallobj_", "")
        .replace("_512_e8_v1", "")
        .replace("_e8_v1", "")
    )


def _evaluation_records(result: Mapping[str, Any], name: str) -> list[SampleRecord]:
    config = yaml.safe_load(_resolve(result["config"]).read_text(encoding="utf-8"))
    evaluation = next(item for item in config["evaluations"] if item["name"] == name)
    manifest = _resolve(evaluation["manifest"])
    dataset_ids = set(evaluation.get("dataset_ids", []))
    return [
        record
        for record in read_manifest(manifest)
        if record.split == evaluation["split"]
        and (not dataset_ids or record.dataset_id in dataset_ids)
    ]


def _representative_records(
    records: Sequence[SampleRecord], count: int = 2
) -> list[SampleRecord]:
    """Select weed-fraction quantiles using GT only, never model outputs."""
    scored: list[tuple[float, str, SampleRecord]] = []
    for record in records:
        with Image.open(DATA_ROOT / record.mask_path) as handle:
            histogram = handle.convert("L").histogram()
        valid = sum(histogram[:3])
        weed = histogram[WEED]
        if weed and valid:
            scored.append((weed / valid, record.sample_id, record))
    if not scored:
        raise RuntimeError("No positive weed records for qualitative gallery")
    scored.sort(key=lambda item: (item[0], item[1]))
    # Avoid only showing extreme tails when two examples are requested.
    if count == 2 and len(scored) >= 4:
        indices = [round(0.33 * (len(scored) - 1)), round(0.67 * (len(scored) - 1))]
    else:
        indices = quantile_indices(len(scored), count)
    return [scored[index][2] for index in indices]


@torch.inference_mode()
def _predictions(
    checkpoint_path: Path, records: Sequence[SampleRecord]
) -> dict[str, np.ndarray]:
    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    training = checkpoint["config"]["training"]
    loader = DataLoader(
        ManifestDataset(records, DATA_ROOT, EvalTransform(), verify_files=True),
        batch_size=1,
        shuffle=False,
        num_workers=0,
        collate_fn=padded_collate,
    )
    output: dict[str, np.ndarray] = {}
    for batch in loader:
        images = batch["image"].to(device)
        crop_ids = batch["target_crop_id"].to(device)
        logits = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=bool(training.get("amp", True)),
            tile_size=training.get("eval_tile_size"),
            tile_overlap=int(training.get("eval_tile_overlap", 128)),
            tile_trigger_pixels=int(training.get("eval_tile_trigger_pixels", 4_000_000)),
        )
        height, width = batch["valid_size"][0]
        output[str(batch["sample_id"][0])] = (
            logits[0, :, :height, :width].argmax(dim=0).cpu().numpy().astype(np.uint8)
        )
    del model
    torch.cuda.empty_cache()
    return output


def _fit_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    scale = min(max_width / width, max_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _overlay(image: Image.Image, label: np.ndarray, size: tuple[int, int]) -> Image.Image:
    rgb = image.resize(size, Image.Resampling.LANCZOS)
    mask = Image.fromarray(label.astype(np.uint8)).resize(size, Image.Resampling.NEAREST)
    array = np.asarray(rgb, dtype=np.float32).copy()
    values = np.asarray(mask, dtype=np.uint8)
    for class_id, color in ((CROP, GREEN), (WEED, RED)):
        selection = values == class_id
        array[selection] = 0.42 * array[selection] + 0.58 * color
    return Image.fromarray(np.clip(np.rint(array), 0, 255).astype(np.uint8))


def _render_gallery(
    records: Sequence[SampleRecord],
    baseline: Mapping[str, np.ndarray],
    selected: Mapping[str, np.ndarray],
    *,
    title: str,
    baseline_label: str,
    selected_label: str,
    destination: Path,
) -> None:
    width = 1900
    header = 135
    row_height = 440
    margin = 25
    gap = 18
    cell_width = (width - margin * 2 - gap * 3) // 4
    image_height = 340
    canvas = Image.new("RGB", (width, header + len(records) * row_height + 20), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((35, 22), title, font=_font(30, bold=True), fill=INK)
    draw.text(
        (35, 68),
        "Yeşil = crop (mahsul) | Kırmızı = weed (istenmeyen ot) | Örnekler GT weed oranı kuantillerinden seçildi",
        font=_font(20),
        fill=MUTED,
    )
    headers = ("RGB girdi", "Gerçek etiket", baseline_label, selected_label)
    for column, label in enumerate(headers):
        left = margin + column * (cell_width + gap)
        draw.text((left, 105), label, font=_font(19, bold=True), fill=INK)
    for row_index, record in enumerate(records):
        row_top = header + row_index * row_height
        image = to_display_pil(load_rgb_image(DATA_ROOT / record.image_path)).convert("RGB")
        with Image.open(DATA_ROOT / record.mask_path) as handle:
            target = np.asarray(handle.convert("L"), dtype=np.uint8)
        size = _fit_size(image.width, image.height, cell_width, image_height)
        panels = (
            image.resize(size, Image.Resampling.LANCZOS),
            _overlay(image, target, size),
            _overlay(image, baseline[record.sample_id], size),
            _overlay(image, selected[record.sample_id], size),
        )
        for column, panel in enumerate(panels):
            left = margin + column * (cell_width + gap)
            box_top = row_top + 18
            cell = Image.new("RGB", (cell_width, image_height), WHITE)
            cell.paste(
                panel,
                ((cell_width - panel.width) // 2, (image_height - panel.height) // 2),
            )
            canvas.paste(cell, (left, box_top))
            draw.rectangle(
                (left, box_top, left + cell_width, box_top + image_height),
                outline=(205, 212, 207),
                width=2,
            )
        sample_text = record.sample_id
        if len(sample_text) > 150:
            sample_text = sample_text[:147] + "..."
        draw.text(
            (margin, row_top + image_height + 26),
            sample_text,
            font=_font(16),
            fill=MUTED,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=94, subsampling=0, optimize=True)


def _run_pair(
    result_path: Path,
    evaluation: str,
    destination_name: str,
    title: str,
    *,
    selected_candidate: str | None = None,
) -> dict[str, Any]:
    result = _json(result_path)
    baseline_name = str(result["baseline_candidate"])
    selected_name = selected_candidate or str(
        result["selection"]["selected_candidate"]
    )
    by_name = {str(run["candidate"]): run for run in result["runs"]}
    records = _representative_records(_evaluation_records(result, evaluation), count=2)
    baseline_path = Path(by_name[baseline_name]["checkpoint"])
    selected_path = Path(by_name[selected_name]["checkpoint"])
    baseline = _predictions(baseline_path, records)
    selected = baseline if selected_path == baseline_path else _predictions(selected_path, records)
    destination = OUTPUT / destination_name
    _render_gallery(
        records,
        baseline,
        selected,
        title=title,
        baseline_label="Kontrol",
        selected_label=f"Seçilen ({_short_candidate(selected_name)})",
        destination=destination,
    )
    return {
        "evaluation": evaluation,
        "result": str(result_path),
        "result_sha256": _sha256(result_path),
        "baseline_candidate": baseline_name,
        "baseline_checkpoint": str(baseline_path),
        "baseline_checkpoint_sha256": _sha256(baseline_path),
        "selected_candidate": selected_name,
        "selected_checkpoint": str(selected_path),
        "selected_checkpoint_sha256": _sha256(selected_path),
        "sample_selection": "GT weed-fraction 33rd/67th percentiles; no model-output selection",
        "sample_ids": [record.sample_id for record in records],
        "gallery": str(destination),
        "gallery_sha256": _sha256(destination),
    }


def build() -> Path:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    galleries = [
        _run_pair(
            DOMAIN_RESULT,
            "sorghum_external_calibration",
            "domain_sorghum_control_vs_selected.jpg",
            "Domain adaptation — Sorghum calibration (final test değil)",
        ),
        _run_pair(
            SMALL_RESULT,
            "sugarbeets_robot_holdout",
            "small_sugarbeets_control_vs_selected.jpg",
            "768 hedef-kamera adayı — unseen SugarBeets robot holdout",
            selected_candidate="smallobj_canvas768_e8_v1",
        ),
        _run_pair(
            SMALL_RESULT,
            "weedmap_uav_holdout",
            "small_weedmap_control_vs_selected.jpg",
            "768 hedef-kamera adayı — unseen WeedMap UAV holdout",
            selected_candidate="smallobj_canvas768_e8_v1",
        ),
    ]
    receipt = {
        "schema_version": 1,
        "role": "model_independent_qualitative_control_vs_selected",
        "color_legend": {"crop": "green", "weed": "red"},
        "galleries": galleries,
        "builder": str(Path(__file__).resolve()),
        "builder_sha256": _sha256(Path(__file__).resolve()),
    }
    destination = OUTPUT / "build_receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(build())
