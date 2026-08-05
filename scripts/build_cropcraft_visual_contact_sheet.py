#!/usr/bin/env python3
"""Build a deterministic RGB/mask/overlay contact sheet for manual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_pair(value: str) -> tuple[str, str]:
    parts = value.split(":", maxsplit=1)
    if len(parts) != 2 or not parts[0].startswith("scene_") or not parts[1].startswith(
        "frame_"
    ):
        raise argparse.ArgumentTypeError("Expected scene_NNNN:frame_NNNN")
    return parts[0], parts[1]


def overlay(rgb: Image.Image, mask: Image.Image) -> Image.Image:
    rgb_array = np.asarray(rgb.convert("RGB"), dtype=np.float32)
    mask_array = np.asarray(mask.convert("RGB"), dtype=np.uint8)
    result = rgb_array.copy()
    crop = np.all(mask_array == np.array([0, 255, 0], dtype=np.uint8), axis=2)
    weed = np.all(mask_array == np.array([255, 0, 0], dtype=np.uint8), axis=2)
    result[crop] = 0.62 * result[crop] + 0.38 * np.array([0.0, 255.0, 0.0])
    result[weed] = 0.62 * result[weed] + 0.38 * np.array([255.0, 0.0, 0.0])
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument("--pairs", nargs="+", required=True, type=parse_pair)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tile-size", type=int, default=256)
    arguments = parser.parse_args()
    release = Path(arguments.release).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    if output.exists() or output.with_suffix(".json").exists():
        raise FileExistsError(output)
    receipt = release / "release_receipt.json"
    if not receipt.is_file():
        raise FileNotFoundError(receipt)
    size = int(arguments.tile_size)
    if size < 64:
        raise ValueError("tile-size must be at least 64")
    header = 24
    canvas = Image.new("RGB", (size * 3, (size + header) * len(arguments.pairs)), "white")
    draw = ImageDraw.Draw(canvas)
    rows = []
    for index, (scene, frame) in enumerate(arguments.pairs):
        image_path = release / "scenes" / scene / "render/images" / f"{frame}.jpg"
        mask_path = release / "scenes" / scene / "render/masks" / f"{frame}.png"
        if not image_path.is_file() or not mask_path.is_file():
            raise FileNotFoundError(f"Missing pair: {scene}:{frame}")
        with Image.open(image_path) as image_handle, Image.open(mask_path) as mask_handle:
            rgb = image_handle.convert("RGB")
            mask = mask_handle.convert("RGB")
            if rgb.size != mask.size:
                raise ValueError(f"RGB/mask shape mismatch: {scene}:{frame}")
            blend = overlay(rgb, mask)
            tiles = [rgb, mask, blend]
            y = index * (size + header)
            draw.text((4, y + 5), f"{scene}:{frame} | RGB / mask / overlay", fill="black")
            for column, tile in enumerate(tiles):
                canvas.paste(
                    tile.resize((size, size), Image.Resampling.LANCZOS),
                    (column * size, y + header),
                )
        rows.append(
            {
                "scene": scene,
                "frame": frame,
                "rgb": str(image_path),
                "rgb_sha256": sha256(image_path),
                "mask": str(mask_path),
                "mask_sha256": sha256(mask_path),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    report = {
        "schema_version": 1,
        "release": str(release),
        "release_receipt_sha256": sha256(receipt),
        "columns": ["rgb", "semantic_mask", "alpha_overlay"],
        "tile_size": size,
        "pairs": rows,
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    report_path = output.with_suffix(".json")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
