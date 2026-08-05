"""Small, bounded qualitative artifacts for label and prediction review."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw

from .constants import CROP, IGNORE, WEED
from .data import load_rgb_image, to_display_pil
from .manifest import SampleRecord, iter_resolved, read_manifest


def overlay_mask(
    image: Image.Image, mask: Image.Image, alpha: float = 0.45
) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    labels = np.asarray(mask.convert("L"))
    colors = np.zeros_like(rgb)
    colors[labels == CROP] = (40, 220, 70)
    colors[labels == WEED] = (230, 45, 45)
    colors[labels == IGNORE] = (180, 60, 210)
    marked = labels != 0
    output = rgb.copy()
    output[marked] = (
        (1.0 - alpha) * rgb[marked] + alpha * colors[marked]
    )
    return Image.fromarray(output.clip(0, 255).astype(np.uint8))


def create_contact_sheet(
    manifest_path: str | Path,
    data_root: str | Path,
    destination: str | Path,
    count: int = 30,
    seed: int = 17,
    columns: int = 5,
    tile_size: tuple[int, int] = (320, 240),
) -> Path:
    records = read_manifest(manifest_path)
    rng = random.Random(seed)
    by_split: dict[str, list[SampleRecord]] = {}
    for record in records:
        by_split.setdefault(record.split, []).append(record)
    selected: list[SampleRecord] = []
    splits = sorted(by_split)
    while len(selected) < min(count, len(records)):
        made_progress = False
        for split in splits:
            available = [
                record
                for record in by_split[split]
                if record not in selected
            ]
            if available and len(selected) < count:
                selected.append(rng.choice(available))
                made_progress = True
        if not made_progress:
            break

    resolved = {
        record.sample_id: (image, mask)
        for record, image, mask in iter_resolved(records, data_root)
    }
    tile_width, tile_height = tile_size
    label_height = 24
    rows = (len(selected) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * tile_width, rows * (tile_height + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, record in enumerate(selected):
        image_path, mask_path = resolved[record.sample_id]
        image = to_display_pil(load_rgb_image(image_path))
        with Image.open(mask_path) as mask:
            overlay = overlay_mask(image, mask)
            overlay.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + label_height)
        canvas = Image.new("RGB", (tile_width, tile_height), (32, 32, 32))
        canvas.paste(
            overlay,
            ((tile_width - overlay.width) // 2, (tile_height - overlay.height) // 2),
        )
        sheet.paste(canvas, (x, y))
        draw.text(
            (x + 4, y + tile_height + 4),
            f"{record.sample_id} [{record.split}]",
            fill="black",
        )
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    return output
