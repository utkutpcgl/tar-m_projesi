#!/usr/bin/env python3
"""Build a deterministic per-orthomosaic WeedMap RGB/mask review sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


COLOURS = {
    BACKGROUND: (45, 45, 45),
    CROP: (35, 205, 70),
    WEED: (235, 70, 70),
    IGNORE: (230, 50, 230),
}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(recorded: str, data_root: Path) -> Path:
    path = Path(recorded)
    return path if path.is_absolute() else data_root / path


def mask_fractions(record: SampleRecord, data_root: Path) -> dict[str, float]:
    with Image.open(resolve(record.mask_path, data_root)) as handle:
        mask = np.asarray(handle.convert("L"), dtype=np.uint8)
    valid = mask != IGNORE
    denominator = max(1, int(valid.sum()))
    return {
        "valid_fraction": float(valid.mean()),
        "crop_fraction_of_valid": float(np.count_nonzero(mask == CROP) / denominator),
        "weed_fraction_of_valid": float(np.count_nonzero(mask == WEED) / denominator),
    }


def selected_records(
    records: list[SampleRecord], data_root: Path
) -> list[tuple[SampleRecord, dict[str, float], str]]:
    grouped: dict[str, list[tuple[SampleRecord, dict[str, float]]]] = defaultdict(list)
    for record in records:
        map_id = record.sample_id.split(":")[1]
        grouped[map_id].append((record, mask_fractions(record, data_root)))
    selected: list[tuple[SampleRecord, dict[str, float], str]] = []
    for map_id in sorted(grouped):
        values = sorted(
            grouped[map_id],
            key=lambda item: (
                item[1]["weed_fraction_of_valid"],
                item[1]["crop_fraction_of_valid"],
                item[0].sample_id,
            ),
        )
        positions = {
            "low_weed": 0,
            "median_weed": (len(values) - 1) // 2,
            "high_weed": len(values) - 1,
        }
        seen: set[str] = set()
        for stratum, position in positions.items():
            record, fractions = values[position]
            if record.sample_id in seen:
                raise ValueError(f"Non-unique QC selection for map {map_id}")
            seen.add(record.sample_id)
            selected.append((record, fractions, stratum))
    return selected


def colour_mask(mask: np.ndarray) -> Image.Image:
    output = np.zeros((*mask.shape, 3), dtype=np.uint8)
    unexpected = set(int(value) for value in np.unique(mask)) - set(COLOURS)
    if unexpected:
        raise ValueError(f"Unexpected common mask values: {unexpected}")
    for value, colour in COLOURS.items():
        output[mask == value] = colour
    return Image.fromarray(output, mode="RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    arguments = parser.parse_args()

    manifest = Path(arguments.manifest).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    receipt_path = Path(arguments.receipt).expanduser().resolve()
    records = read_manifest(manifest)
    if {record.dataset_id for record in records} != {"weedmap"}:
        raise ValueError("Expected only WeedMap records")
    if len({record.field_id for record in records}) != 1:
        raise ValueError("WeedMap RGB subset must retain its single-site declaration")
    selected = selected_records(records, data_root)
    if len(selected) != 15:
        raise ValueError(f"Expected 15 stratified review samples, got {len(selected)}")

    panel_size = (320, 240)
    header_height = 32
    row_height = panel_size[1] + header_height
    sheet = Image.new("RGB", (panel_size[0] * 3, row_height * len(selected)), "white")
    draw = ImageDraw.Draw(sheet)
    receipt_rows: list[dict[str, object]] = []
    for row_index, (record, fractions, stratum) in enumerate(selected):
        image_path = resolve(record.image_path, data_root).resolve()
        mask_path = resolve(record.mask_path, data_root).resolve()
        with Image.open(image_path) as handle:
            rgb = handle.convert("RGB")
        with Image.open(mask_path) as handle:
            mask = np.asarray(handle.convert("L"), dtype=np.uint8)
        if rgb.size != (mask.shape[1], mask.shape[0]):
            raise ValueError(f"RGB/mask shape mismatch: {record.sample_id}")
        mask_rgb = colour_mask(mask)
        overlay = Image.blend(rgb, mask_rgb, 0.45)
        panels = [rgb, mask_rgb, overlay]
        y = row_index * row_height
        label = (
            f"{record.sample_id} | {record.split} | {stratum} | "
            f"valid={fractions['valid_fraction']:.3f} "
            f"crop={fractions['crop_fraction_of_valid']:.3f} "
            f"weed={fractions['weed_fraction_of_valid']:.3f}"
        )
        draw.text((5, y + 8), label, fill=(0, 0, 0))
        for column, panel in enumerate(panels):
            resized = panel.resize(panel_size, Image.Resampling.NEAREST)
            sheet.paste(resized, (column * panel_size[0], y + header_height))
        receipt_rows.append(
            {
                "sample_id": record.sample_id,
                "split": record.split,
                "stratum": stratum,
                "fractions": fractions,
                "image": str(image_path),
                "image_sha256": sha256(image_path),
                "mask": str(mask_path),
                "mask_sha256": sha256(mask_path),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, optimize=False)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "weedmap",
        "selection": "per map low/median/high weed fraction among effective tiles",
        "columns": ["rgb", "common_mask", "overlay"],
        "legend": {
            "background": list(COLOURS[BACKGROUND]),
            "crop": list(COLOURS[CROP]),
            "weed": list(COLOURS[WEED]),
            "ignore": list(COLOURS[IGNORE]),
        },
        "manifest": str(manifest),
        "manifest_sha256": manifest_sha256(manifest),
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "samples": receipt_rows,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
