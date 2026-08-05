#!/usr/bin/env python3
"""Build a deterministic flight-by-coverage Weedy Rice RGB/mask review sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from agri_seg.constants import IGNORE, WEED
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


BINS = (
    (0.05, "gt_0_le_5"),
    (0.10, "gt_5_le_10"),
    (0.20, "gt_10_le_20"),
    (0.30, "gt_20_le_30"),
    (0.40, "gt_30_le_40"),
    (0.60, "gt_40_le_60"),
    (0.75, "gt_60_le_75"),
    (0.90, "gt_75_lt_90"),
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(recorded: str, data_root: Path) -> Path:
    path = Path(recorded)
    return path if path.is_absolute() else data_root / path


def coverage_bin(fraction: float) -> str:
    if fraction <= 0:
        raise ValueError(f"Empty weedy-rice mask: {fraction}")
    for upper, name in BINS:
        if fraction <= upper + 1e-12:
            return name
    raise ValueError(f"Forbidden weedy-rice coverage: {fraction}")


def mask_fraction(record: SampleRecord, data_root: Path) -> float:
    with Image.open(resolve(record.mask_path, data_root)) as handle:
        mask = np.asarray(handle.convert("L"), dtype=np.uint8)
    values = set(int(value) for value in np.unique(mask))
    if not values <= {WEED, IGNORE} or WEED not in values:
        raise ValueError(f"Invalid partial-mask palette for {record.sample_id}: {values}")
    return float(np.count_nonzero(mask == WEED) / mask.size)


def select_records(
    records: list[SampleRecord], data_root: Path
) -> tuple[
    list[str],
    dict[tuple[str, str], tuple[SampleRecord, float]],
    dict[str, int],
]:
    grouped: dict[tuple[str, str], list[tuple[SampleRecord, float]]] = defaultdict(list)
    bin_counts: dict[str, int] = defaultdict(int)
    sessions = sorted(
        {record.session_id for record in records},
        key=lambda session: min(
            (record.capture_date, record.field_id)
            for record in records
            if record.session_id == session
        ),
    )
    for record in records:
        fraction = mask_fraction(record, data_root)
        name = coverage_bin(fraction)
        grouped[(record.session_id, name)].append((record, fraction))
        bin_counts[name] += 1
    selected: dict[tuple[str, str], tuple[SampleRecord, float]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda item: (item[1], item[0].sample_id))
        selected[key] = ordered[(len(ordered) - 1) // 2]
    return sessions, selected, dict(bin_counts)


def binary_mask(mask: np.ndarray) -> Image.Image:
    canvas = np.full((*mask.shape, 3), 28, dtype=np.uint8)
    canvas[mask == WEED] = (235, 65, 65)
    return Image.fromarray(canvas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--manual-verdict", choices=("pending", "pass", "fail"), default="pending"
    )
    parser.add_argument("--review-note", default="")
    arguments = parser.parse_args()

    manifest = Path(arguments.manifest).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    receipt_path = Path(arguments.receipt).expanduser().resolve()
    records = read_manifest(manifest)
    if len(records) != 734:
        raise ValueError(f"Expected 734 Weedy Rice records, got {len(records)}")
    if {record.dataset_id for record in records} != {"weedy_rice_uav"}:
        raise ValueError("Expected only weedy_rice_uav records")
    sessions, selected, bin_counts = select_records(records, data_root)
    if len(sessions) != 4:
        raise ValueError(f"Expected four capture sessions, got {len(sessions)}")
    expected_bins = {name for _, name in BINS}
    if set(bin_counts) != expected_bins:
        raise ValueError(f"Missing global coverage bins: {expected_bins - set(bin_counts)}")

    panel_size = (320, 240)
    cell_width = panel_size[0] * 3
    header_height = 36
    cell_height = header_height + panel_size[1]
    table_header = 42
    sheet = Image.new(
        "RGB", (cell_width * len(sessions), table_header + cell_height * len(BINS)), "white"
    )
    draw = ImageDraw.Draw(sheet)
    for column, session in enumerate(sessions):
        example = next(record for record in records if record.session_id == session)
        title = f"{example.capture_date} | {example.field_id} | {example.split}"
        draw.text((column * cell_width + 5, 14), title, fill=(0, 0, 0))

    receipt_rows: list[dict[str, object]] = []
    for row, (_, bin_name) in enumerate(BINS):
        for column, session in enumerate(sessions):
            x = column * cell_width
            y = table_header + row * cell_height
            selection = selected.get((session, bin_name))
            if selection is None:
                draw.rectangle((x, y, x + cell_width - 1, y + cell_height - 1), fill=(220, 220, 220))
                draw.text((x + 5, y + 10), f"{bin_name} | no sample", fill=(60, 60, 60))
                continue
            record, fraction = selection
            image_path = resolve(record.image_path, data_root).resolve()
            mask_path = resolve(record.mask_path, data_root).resolve()
            with Image.open(image_path) as handle:
                rgb = handle.convert("RGB")
            with Image.open(mask_path) as handle:
                mask = np.asarray(handle.convert("L"), dtype=np.uint8)
            if rgb.size != (mask.shape[1], mask.shape[0]):
                raise ValueError(f"RGB/mask shape mismatch: {record.sample_id}")
            mask_rgb = binary_mask(mask)
            overlay = Image.blend(rgb, mask_rgb, 0.45)
            label = f"{bin_name} | {fraction * 100:.2f}% | {record.sample_id.rsplit(':', 1)[-1]}"
            draw.text((x + 5, y + 10), label, fill=(0, 0, 0))
            for panel_index, (panel, resampling) in enumerate(
                (
                    (rgb, Image.Resampling.LANCZOS),
                    (mask_rgb, Image.Resampling.NEAREST),
                    (overlay, Image.Resampling.LANCZOS),
                )
            ):
                resized = panel.resize(panel_size, resampling)
                sheet.paste(resized, (x + panel_index * panel_size[0], y + header_height))
            receipt_rows.append(
                {
                    "sample_id": record.sample_id,
                    "capture_date": record.capture_date,
                    "field_id": record.field_id,
                    "session_id": record.session_id,
                    "split": record.split,
                    "coverage_bin": bin_name,
                    "weedy_rice_fraction": fraction,
                    "image": str(image_path),
                    "mask": str(mask_path),
                }
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)
    detail_pages: list[dict[str, str]] = []
    for column, session in enumerate(sessions, start=1):
        left = (column - 1) * cell_width
        page = sheet.crop((left, 0, left + cell_width, sheet.height))
        page_path = output.with_name(
            f"{output.stem}_event_{column:02d}{output.suffix}"
        )
        page.save(page_path, format="PNG", optimize=True)
        detail_pages.append(
            {
                "session_id": session,
                "path": str(page_path),
                "sha256": sha256(page_path),
            }
        )
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "weedy_rice_uav",
        "manifest": str(manifest),
        "manifest_sha256": manifest_sha256(manifest),
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "detail_pages": detail_pages,
        "capture_sessions": len(sessions),
        "coverage_bins": bin_counts,
        "selected_cells": len(receipt_rows),
        "cells_without_samples": len(sessions) * len(BINS) - len(receipt_rows),
        "selection": "median coverage per capture-session x coverage-bin cell",
        "panels": ["rgb", "binary_positive_mask", "rgb_mask_overlay"],
        "rows": receipt_rows,
        "manual_review": {
            "verdict": arguments.manual_verdict,
            "note": arguments.review_note,
        },
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"contact_sheet": str(output), "receipt": str(receipt_path)}, indent=2))


if __name__ == "__main__":
    main()
