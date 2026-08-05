#!/usr/bin/env python3
"""Build deterministic class-aware RiceSEG RGB/source/common review sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


SOURCE_COLORS = np.array(
    [
        (35, 30, 25),
        (35, 190, 65),
        (215, 175, 45),
        (245, 90, 30),
        (215, 45, 205),
        (35, 190, 220),
    ],
    dtype=np.uint8,
)
COMMON_COLORS = np.array(
    [(35, 30, 25), (35, 190, 65), (215, 45, 205)], dtype=np.uint8
)
COMMON_LOOKUP = np.array([0, 1, 1, 1, 2, 2], dtype=np.uint8)
SELECTION_NAMES = (
    "low_vegetation_q10",
    "median_vegetation_q50",
    "high_vegetation_q90",
    "weed_rich",
    "rice_organ_rich",
)


@dataclass(frozen=True)
class SampleStats:
    record: SampleRecord
    source_mask: Path
    common_mask: Path
    vegetation_fraction: float
    weed_fraction: float
    rice_organ_fraction: float


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(recorded: str, data_root: Path) -> Path:
    path = Path(recorded)
    return (path if path.is_absolute() else data_root / path).resolve()


def source_path_for(record: SampleRecord, data_root: Path) -> Path:
    common = resolve(record.mask_path, data_root)
    try:
        relative = common.relative_to(data_root / "processed/riceseg/common_masks")
    except ValueError as exc:
        raise ValueError(f"Unexpected RiceSEG common-mask path: {common}") from exc
    source = data_root / "processed/riceseg/source_masks" / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    return source


def subgroup(record: SampleRecord) -> str:
    parts = record.sample_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "riceseg" or not parts[1]:
        raise ValueError(f"Unexpected RiceSEG sample_id: {record.sample_id}")
    return parts[1]


def collect_stats(records: list[SampleRecord], data_root: Path) -> list[SampleStats]:
    result: list[SampleStats] = []
    for record in records:
        common_path = resolve(record.mask_path, data_root)
        source_path = source_path_for(record, data_root)
        image_path = resolve(record.image_path, data_root)
        with Image.open(source_path) as handle:
            source = np.asarray(handle.convert("L"), dtype=np.uint8)
        with Image.open(common_path) as handle:
            common = np.asarray(handle.convert("L"), dtype=np.uint8)
        with Image.open(image_path) as handle:
            image_size = handle.size
        if source.shape != common.shape or image_size != (source.shape[1], source.shape[0]):
            raise ValueError(f"RiceSEG RGB/source/common shape mismatch: {record.sample_id}")
        values = {int(value) for value in np.unique(source)}
        if not values <= set(range(6)):
            raise ValueError(f"Unexpected source values {values}: {record.sample_id}")
        expected_common = COMMON_LOOKUP[source]
        if not np.array_equal(common, expected_common):
            raise ValueError(f"Common mask differs from source mapping: {record.sample_id}")
        pixels = source.size
        result.append(
            SampleStats(
                record=record,
                source_mask=source_path,
                common_mask=common_path,
                vegetation_fraction=float(np.count_nonzero(source) / pixels),
                weed_fraction=float(np.count_nonzero((source == 4) | (source == 5)) / pixels),
                rice_organ_fraction=float(
                    np.count_nonzero((source == 2) | (source == 3)) / pixels
                ),
            )
        )
    return result


def _quantile_pick(
    values: list[SampleStats], attribute: str, quantile: float, excluded: set[str]
) -> SampleStats:
    ordered = sorted(values, key=lambda item: (getattr(item, attribute), item.record.sample_id))
    target = round((len(ordered) - 1) * quantile)
    indices = sorted(range(len(ordered)), key=lambda index: (abs(index - target), index))
    for index in indices:
        candidate = ordered[index]
        if candidate.record.sample_id not in excluded:
            return candidate
    raise ValueError("No unselected RiceSEG quantile candidate remains")


def _maximum_pick(
    values: list[SampleStats], attribute: str, excluded: set[str]
) -> SampleStats:
    ordered = sorted(
        values,
        key=lambda item: (-getattr(item, attribute), item.record.sample_id),
    )
    for candidate in ordered:
        if candidate.record.sample_id not in excluded:
            return candidate
    raise ValueError("No unselected RiceSEG maximum candidate remains")


def select_subdataset(values: list[SampleStats]) -> dict[str, SampleStats]:
    if len(values) < len(SELECTION_NAMES):
        raise ValueError("RiceSEG subgroup is too small for distinct visual selections")
    selected: dict[str, SampleStats] = {}
    used: set[str] = set()
    for name, quantile in (
        ("low_vegetation_q10", 0.10),
        ("median_vegetation_q50", 0.50),
        ("high_vegetation_q90", 0.90),
    ):
        candidate = _quantile_pick(values, "vegetation_fraction", quantile, used)
        selected[name] = candidate
        used.add(candidate.record.sample_id)
    for name, attribute in (
        ("weed_rich", "weed_fraction"),
        ("rice_organ_rich", "rice_organ_fraction"),
    ):
        candidate = _maximum_pick(values, attribute, used)
        selected[name] = candidate
        used.add(candidate.record.sample_id)
    return selected


def colorize(mask: np.ndarray, colors: np.ndarray) -> Image.Image:
    values = {int(value) for value in np.unique(mask)}
    if values and max(values) >= len(colors):
        raise ValueError(f"Mask palette index outside color table: {values}")
    return Image.fromarray(colors[mask])


def render_panels(stats: SampleStats, data_root: Path) -> tuple[Image.Image, ...]:
    image_path = resolve(stats.record.image_path, data_root)
    with Image.open(image_path) as handle:
        rgb = handle.convert("RGB")
    with Image.open(stats.source_mask) as handle:
        source = np.asarray(handle.convert("L"), dtype=np.uint8)
    with Image.open(stats.common_mask) as handle:
        common = np.asarray(handle.convert("L"), dtype=np.uint8)
    source_color = colorize(source, SOURCE_COLORS)
    common_color = colorize(common, COMMON_COLORS)
    overlay = Image.blend(rgb, common_color, 0.38)
    return rgb, source_color, common_color, overlay


def safe_name(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")


def build_sheets(
    *,
    selected: dict[str, dict[str, SampleStats]],
    data_root: Path,
    output: Path,
) -> list[dict[str, str]]:
    subdatasets = sorted(selected)
    overview_panel = (96, 96)
    row_label_width = 130
    label_height = 30
    table_header = 50
    cell_width = overview_panel[0] * 4
    row_height = label_height + overview_panel[1]
    sheet = Image.new(
        "RGB",
        (row_label_width + cell_width * len(SELECTION_NAMES), table_header + row_height * len(subdatasets)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), "RiceSEG | RGB / source-6 / common-3 / overlay", fill=(0, 0, 0))
    for column, selection_name in enumerate(SELECTION_NAMES):
        draw.text(
            (row_label_width + column * cell_width + 5, 30),
            selection_name,
            fill=(0, 0, 0),
        )
    receipt_pages: list[dict[str, str]] = []
    detail_panel = (256, 256)
    detail_label_height = 40
    for row, name in enumerate(subdatasets):
        y = table_header + row * row_height
        draw.rectangle((0, y, sheet.width - 1, y + row_height - 1), outline=(175, 175, 175))
        role = next(iter(selected[name].values())).record.split
        draw.text((6, y + 8), f"{name} | {role}", fill=(0, 0, 0))
        detail = Image.new(
            "RGB",
            (
                detail_panel[0] * 4,
                detail_label_height * len(SELECTION_NAMES)
                + detail_panel[1] * len(SELECTION_NAMES),
            ),
            "white",
        )
        detail_draw = ImageDraw.Draw(detail)
        for column, selection_name in enumerate(SELECTION_NAMES):
            stats = selected[name][selection_name]
            panels = render_panels(stats, data_root)
            x = row_label_width + column * cell_width
            label = (
                f"veg={stats.vegetation_fraction * 100:.1f}% "
                f"weed={stats.weed_fraction * 100:.1f}% "
                f"organ={stats.rice_organ_fraction * 100:.1f}%"
            )
            draw.text((x + 5, y + 8), label, fill=(0, 0, 0))
            for panel_index, panel in enumerate(panels):
                resized = panel.resize(
                    overview_panel,
                    Image.Resampling.NEAREST if panel_index in {1, 2} else Image.Resampling.LANCZOS,
                )
                sheet.paste(
                    resized,
                    (x + panel_index * overview_panel[0], y + label_height),
                )

            detail_y = column * (detail_label_height + detail_panel[1])
            detail_draw.text(
                (5, detail_y + 5),
                f"{name} | {selection_name} | {label} | {stats.record.sample_id}",
                fill=(0, 0, 0),
            )
            for panel_index, panel in enumerate(panels):
                resized = panel.resize(
                    detail_panel,
                    Image.Resampling.NEAREST if panel_index in {1, 2} else Image.Resampling.LANCZOS,
                )
                detail.paste(
                    resized,
                    (
                        panel_index * detail_panel[0],
                        detail_y + detail_label_height,
                    ),
                )
        detail_path = output.with_name(f"{output.stem}_{safe_name(name)}{output.suffix}")
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail.save(detail_path, format="PNG", optimize=True)
        receipt_pages.append(
            {"subdataset": name, "path": str(detail_path), "sha256": sha256(detail_path)}
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)
    return receipt_pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--conversion-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--manual-verdict", choices=("pending", "pass", "fail"), default="pending"
    )
    parser.add_argument("--review-note", default="")
    arguments = parser.parse_args()

    manifest = Path(arguments.manifest).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    conversion_path = Path(arguments.conversion_receipt).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    receipt_path = Path(arguments.receipt).expanduser().resolve()
    conversion = json.loads(conversion_path.read_text(encoding="utf-8"))
    if conversion.get("status") != "verified" or conversion.get("passed") is not True:
        raise RuntimeError("RiceSEG conversion receipt has not passed")
    records = read_manifest(manifest)
    if len(records) != 3078 or {record.dataset_id for record in records} != {"riceseg"}:
        raise ValueError("Expected the complete 3,078-sample RiceSEG coverage manifest")
    if conversion["manifests"]["coverage"]["sha256"] != manifest_sha256(manifest):
        raise RuntimeError("RiceSEG manifest is not locked by the conversion receipt")

    stats = collect_stats(records, data_root)
    grouped: dict[str, list[SampleStats]] = defaultdict(list)
    for item in stats:
        grouped[subgroup(item.record)].append(item)
    expected_counts = {
        str(name): int(count)
        for name, count in conversion["samples_by_subdataset"].items()
    }
    actual_counts = {name: len(values) for name, values in grouped.items()}
    if actual_counts != expected_counts or len(grouped) != 19:
        raise ValueError(
            f"RiceSEG visual strata differ from conversion: {actual_counts} != {expected_counts}"
        )
    selected = {name: select_subdataset(values) for name, values in grouped.items()}
    pages = build_sheets(selected=selected, data_root=data_root, output=output)

    rows: list[dict[str, object]] = []
    for name in sorted(selected):
        for selection_name in SELECTION_NAMES:
            item = selected[name][selection_name]
            rows.append(
                {
                    "subdataset": name,
                    "selection": selection_name,
                    "sample_id": item.record.sample_id,
                    "split": item.record.split,
                    "vegetation_fraction": item.vegetation_fraction,
                    "weed_fraction": item.weed_fraction,
                    "rice_organ_fraction": item.rice_organ_fraction,
                    "image": str(resolve(item.record.image_path, data_root)),
                    "source_mask": str(item.source_mask),
                    "common_mask": str(item.common_mask),
                }
            )
    split_counts = Counter(record.split for record in records)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "riceseg",
        "manifest": str(manifest),
        "manifest_sha256": manifest_sha256(manifest),
        "conversion_receipt": str(conversion_path),
        "conversion_receipt_sha256": sha256(conversion_path),
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "detail_pages": pages,
        "subdatasets": len(grouped),
        "split_counts": dict(split_counts),
        "reviewed_cells": len(rows),
        "selection": list(SELECTION_NAMES),
        "selection_note": (
            "Five distinct deterministic samples per subdataset: vegetation q10/q50/q90, "
            "maximum remaining weed fraction, and maximum remaining senescent-rice-plus-panicle fraction."
        ),
        "panels": ["rgb", "source_6_class", "common_3_class", "common_overlay"],
        "source_palette": {
            "0": "background",
            "1": "green_rice",
            "2": "senescent_rice",
            "3": "rice_panicle",
            "4": "weed",
            "5": "duckweed",
        },
        "rows": rows,
        "full_manifest_mapping_reverified": True,
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
    print(
        json.dumps(
            {
                "contact_sheet": str(output),
                "contact_sheet_sha256": receipt["contact_sheet_sha256"],
                "receipt": str(receipt_path),
                "receipt_sha256": sha256(receipt_path),
                "manual_verdict": arguments.manual_verdict,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
