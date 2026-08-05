#!/usr/bin/env python3
"""Build a paired sharp/blur RGB-mask-overlay sheet for manual QC."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(path: str, root: Path) -> Path:
    candidate = Path(path)
    result = candidate if candidate.is_absolute() else root / candidate
    if not result.is_file():
        raise FileNotFoundError(result)
    return result.resolve()


def colour_mask(mask: np.ndarray) -> Image.Image:
    values = set(np.unique(mask).tolist())
    if not values <= {BACKGROUND, CROP, WEED, IGNORE}:
        raise ValueError(f"Invalid common mask palette: {values}")
    rgb = np.zeros((*mask.shape, 3), dtype=np.uint8)
    rgb[mask == BACKGROUND] = (80, 80, 80)
    rgb[mask == CROP] = (0, 255, 0)
    rgb[mask == WEED] = (255, 0, 0)
    rgb[mask == IGNORE] = (255, 0, 255)
    return Image.fromarray(rgb)


def overlay(image: Image.Image, mask: np.ndarray) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32).copy()
    for value, colour in ((CROP, (0, 255, 0)), (WEED, (255, 0, 0)), (IGNORE, (255, 0, 255))):
        selected = mask == value
        rgb[selected] = 0.58 * rgb[selected] + 0.42 * np.asarray(colour)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def modality(record: SampleRecord) -> str:
    suffix = record.sample_id.rsplit(":", 1)[-1]
    if suffix not in {"sharp", "motion_blur"}:
        raise ValueError(f"Unexpected modality in {record.sample_id}")
    return suffix


def pair_id(record: SampleRecord) -> str:
    parts = record.sample_id.split(":")
    if len(parts) != 3 or parts[0] != "deblurweedseg":
        raise ValueError(f"Unexpected sample id: {record.sample_id}")
    return parts[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--pair-ids", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tile-size", type=int, default=128)
    arguments = parser.parse_args()

    manifest = Path(arguments.manifest).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    report_path = output.with_suffix(".json")
    if output.exists() or report_path.exists():
        raise FileExistsError(output)
    if len(arguments.pair_ids) != len(set(arguments.pair_ids)):
        raise ValueError("pair ids must be unique")
    if arguments.tile_size < 96:
        raise ValueError("tile-size must be at least 96")

    records = read_manifest(manifest)
    index: dict[tuple[str, str], SampleRecord] = {}
    for record in records:
        key = (pair_id(record), modality(record))
        if key in index:
            raise ValueError(f"Duplicate manifest pair modality: {key}")
        index[key] = record

    tile = int(arguments.tile_size)
    pairs_per_row = 2
    tiles_per_pair = 6
    header = 24
    rows_count = (len(arguments.pair_ids) + pairs_per_row - 1) // pairs_per_row
    canvas = Image.new(
        "RGB",
        (tile * tiles_per_pair * pairs_per_row, rows_count * (tile + header)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    report_rows: list[dict[str, object]] = []

    for pair_index, stem in enumerate(arguments.pair_ids):
        row = pair_index // pairs_per_row
        pair_column = pair_index % pairs_per_row
        x0 = pair_column * tiles_per_pair * tile
        y0 = row * (tile + header)
        draw.text(
            (x0 + 4, y0 + 5),
            f"{stem}: sharp RGB/mask/overlay | motion-blur RGB/mask/overlay",
            fill="black",
        )
        pair_records: dict[str, dict[str, object]] = {}
        for modality_index, name in enumerate(("sharp", "motion_blur")):
            record = index.get((stem, name))
            if record is None:
                raise ValueError(f"Missing pair modality: {stem}/{name}")
            image_path = resolve(record.image_path, data_root)
            mask_path = resolve(record.mask_path, data_root)
            with Image.open(image_path) as image_handle, Image.open(mask_path) as mask_handle:
                image = image_handle.convert("RGB")
                mask = np.asarray(mask_handle, dtype=np.uint8)
                if image.size != (mask.shape[1], mask.shape[0]):
                    raise ValueError(f"Image/mask mismatch: {record.sample_id}")
                panels = (image, colour_mask(mask), overlay(image, mask))
                for subcolumn, panel in enumerate(panels):
                    column = modality_index * 3 + subcolumn
                    canvas.paste(
                        panel.resize((tile, tile), Image.Resampling.NEAREST),
                        (x0 + column * tile, y0 + header),
                    )
            pair_records[name] = {
                "sample_id": record.sample_id,
                "image": str(image_path),
                "image_sha256": sha256(image_path),
                "mask": str(mask_path),
                "mask_sha256": sha256(mask_path),
            }
        report_rows.append({"pair_id": stem, "modalities": pair_records})

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    report = {
        "schema_version": 1,
        "manifest": str(manifest),
        "manifest_sha256": manifest_sha256(manifest),
        "columns_per_pair": [
            "sharp_rgb",
            "sharp_mask",
            "sharp_overlay",
            "motion_blur_rgb",
            "motion_blur_mask",
            "motion_blur_overlay",
        ],
        "pairs_per_row": pairs_per_row,
        "tile_size": tile,
        "pairs": report_rows,
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
