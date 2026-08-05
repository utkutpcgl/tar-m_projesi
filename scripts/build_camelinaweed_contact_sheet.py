#!/usr/bin/env python3
"""Build the frozen group-by-coverage visual review for CamelinaWeed."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

from agri_seg.constants import IGNORE, WEED
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(recorded: str, root: Path) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def quantile_index(size: int, quantile: float) -> int:
    if size <= 0:
        raise ValueError("Quantile inventory cannot be empty")
    if not 0 <= quantile <= 1:
        raise ValueError(f"Invalid quantile: {quantile}")
    return int(round(quantile * (size - 1)))


def mask_fraction(path: Path) -> float:
    with Image.open(path) as handle:
        mask = np.asarray(handle.convert("L"), dtype=np.uint8)
    values = set(int(value) for value in np.unique(mask))
    if values != {WEED, IGNORE}:
        raise ValueError(f"Invalid CamelinaWeed partial-mask palette {values}: {path}")
    fraction = float((mask == WEED).sum() / mask.size)
    if fraction <= 0:
        raise ValueError(f"Empty CamelinaWeed positive mask: {path}")
    return fraction


def visual_panels(image_path: Path, mask_path: Path) -> tuple[Image.Image, Image.Image, Image.Image]:
    with Image.open(image_path) as handle:
        handle.seek(0)
        rgb = handle.convert("RGB")
        rgb.load()
    with Image.open(mask_path) as handle:
        mask = handle.convert("L")
        mask.load()
    if rgb.size != mask.size:
        raise ValueError(f"RGB/mask shape mismatch: {image_path}")
    palette = set(int(value) for value in np.unique(np.asarray(mask, dtype=np.uint8)))
    if palette != {WEED, IGNORE}:
        raise ValueError(f"Invalid CamelinaWeed mask palette {palette}: {mask_path}")
    weed_binary = mask.point(lambda value: 255 if value == WEED else 0)
    mask_rgb = Image.new("RGB", rgb.size, (35, 35, 35))
    mask_rgb.paste((240, 55, 55), mask=weed_binary)
    alpha = mask.point(lambda value: 125 if value == WEED else 0)
    overlay = rgb.copy()
    overlay.paste((255, 30, 30), mask=alpha)
    return rgb, mask_rgb, overlay


def paste_triplet(
    canvas: Image.Image,
    panels: tuple[Image.Image, Image.Image, Image.Image],
    x: int,
    y: int,
    panel_size: tuple[int, int],
) -> None:
    for index, (panel, resampling) in enumerate(
        (
            (panels[0], Image.Resampling.LANCZOS),
            (panels[1], Image.Resampling.NEAREST),
            (panels[2], Image.Resampling.LANCZOS),
        )
    ):
        canvas.paste(
            panel.resize(panel_size, resampling),
            (x + index * panel_size[0], y),
        )


def build(
    gate_path: Path,
    manifest_path: Path,
    output: Path,
    receipt_path: Path,
    manual_verdict: str,
    review_note: str,
) -> tuple[Path, Path]:
    gate_path = gate_path.expanduser().resolve()
    project_root = gate_path.parents[2]
    gate = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError(f"Expected YAML mapping: {gate_path}")
    data_root = resolve(str(gate["data_root"]), project_root)
    manifest_path = manifest_path.expanduser().resolve()
    output = output.expanduser().resolve()
    receipt_path = receipt_path.expanduser().resolve()
    records = read_manifest(manifest_path)
    expected = int(gate["expected_release"]["accepted_images"])
    if len(records) != expected:
        raise ValueError(f"Expected {expected} CamelinaWeed samples, got {len(records)}")
    if {record.dataset_id for record in records} != {gate["dataset_id"]}:
        raise ValueError("Contact-sheet manifest contains another dataset")
    if {record.annotation_exhaustive for record in records} != {False}:
        raise ValueError("CamelinaWeed contact sheet requires partial labels")

    group_order = [str(group["id"]) for group in gate["canonical_groups"]]
    by_group: dict[str, list[tuple[SampleRecord, float]]] = defaultdict(list)
    for record in records:
        mask_path = resolve(record.mask_path, data_root)
        by_group[record.session_id].append((record, mask_fraction(mask_path)))
    if set(by_group) != set(group_order):
        raise ValueError(f"Unexpected session inventory: {sorted(by_group)}")
    quantiles = [float(value) for value in gate["quality_gate"]["manual_sample_quantiles"]]
    selections: dict[tuple[str, float], tuple[SampleRecord, float]] = {}
    for group_id in group_order:
        ordered = sorted(by_group[group_id], key=lambda item: (item[1], item[0].sample_id))
        for quantile in quantiles:
            selections[(group_id, quantile)] = ordered[quantile_index(len(ordered), quantile)]

    overview_panel = (240, 135)
    cell_width = overview_panel[0] * 3
    cell_header = 30
    cell_height = cell_header + overview_panel[1]
    left_header = 310
    top_header = 52
    overview = Image.new(
        "RGB",
        (left_header + cell_width * len(quantiles), top_header + cell_height * len(group_order)),
        "white",
    )
    draw = ImageDraw.Draw(overview)
    draw.text((8, 8), "CamelinaWeed | RGB / partial weed mask / positive overlay", fill=(0, 0, 0))
    for column, quantile in enumerate(quantiles):
        draw.text((left_header + column * cell_width + 8, 31), f"coverage q={quantile:.2f}", fill=(0, 0, 0))

    rows: list[dict[str, object]] = []
    details: list[dict[str, str]] = []
    detail_panel = (640, 360)
    for row_index, group_id in enumerate(group_order):
        group_records = by_group[group_id]
        role = group_records[0][0].split
        row_y = top_header + row_index * cell_height
        draw.text((8, row_y + 8), group_id, fill=(0, 0, 0))
        draw.text((8, row_y + 24), f"{role} | n={len(group_records)}", fill=(0, 0, 0))

        detail = Image.new(
            "RGB",
            (detail_panel[0] * 3, 48 + len(quantiles) * (detail_panel[1] + 32)),
            "white",
        )
        detail_draw = ImageDraw.Draw(detail)
        detail_draw.text((8, 8), f"{group_id} | {role} | RGB / mask / overlay", fill=(0, 0, 0))
        for column, quantile in enumerate(quantiles):
            record, fraction = selections[(group_id, quantile)]
            image_path = resolve(record.image_path, data_root)
            mask_path = resolve(record.mask_path, data_root)
            panels = visual_panels(image_path, mask_path)
            x = left_header + column * cell_width
            draw.text((x + 5, row_y + 8), f"q={quantile:.2f} | {fraction * 100:.3f}%", fill=(0, 0, 0))
            paste_triplet(overview, panels, x, row_y + cell_header, overview_panel)

            detail_y = 48 + column * (detail_panel[1] + 32)
            detail_draw.text(
                (8, detail_y + 7),
                f"q={quantile:.2f} | {fraction * 100:.4f}% | {record.sample_id}",
                fill=(0, 0, 0),
            )
            paste_triplet(detail, panels, 0, detail_y + 32, detail_panel)
            rows.append(
                {
                    "group_id": group_id,
                    "role": role,
                    "quantile": quantile,
                    "sample_id": record.sample_id,
                    "positive_fraction": fraction,
                    "image": str(image_path),
                    "mask": str(mask_path),
                }
            )
        detail_path = output.with_name(f"{output.stem}_{row_index + 1:02d}_{group_id}{output.suffix}")
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail.save(detail_path, format="PNG", optimize=True)
        details.append({"group_id": group_id, "path": str(detail_path), "sha256": sha256(detail_path)})

    output.parent.mkdir(parents=True, exist_ok=True)
    overview.save(output, format="PNG", optimize=True)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": gate["dataset_id"],
        "gate_config": str(gate_path),
        "gate_config_sha256": sha256(gate_path),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha256(manifest_path),
        "samples": len(records),
        "split_counts": dict(sorted(Counter(record.split for record in records).items())),
        "group_counts": {group_id: len(by_group[group_id]) for group_id in group_order},
        "selection": "nearest deterministic order statistic at each frozen within-group positive-coverage quantile",
        "quantiles": quantiles,
        "selected_samples": len(rows),
        "panels": ["rgb", "partial_positive_mask", "positive_only_overlay"],
        "ignore_visualization": "dark gray only in the mask panel; untouched in the RGB overlay",
        "contact_sheet": str(output),
        "contact_sheet_sha256": sha256(output),
        "detail_pages": details,
        "rows": rows,
        "manual_review": {"verdict": manual_verdict, "note": review_note},
        "external_test_used": False,
        "model_selection_used": False,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output, receipt_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-config", type=Path, default=Path("configs/data/camelinaweed_partial_label_gate_v1.yaml"))
    parser.add_argument("--manifest", type=Path, default=Path("data/processed/manifests/camelinaweed_partial_v1.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/audits/qc/camelinaweed_review_v1.png"))
    parser.add_argument("--receipt", type=Path, default=Path("data/processed/audits/camelinaweed_contact_sheet_v1.json"))
    parser.add_argument("--manual-verdict", choices=("pending", "pass", "fail"), default="pending")
    parser.add_argument("--review-note", default="")
    arguments = parser.parse_args()
    output, receipt = build(
        arguments.gate_config,
        arguments.manifest,
        arguments.output,
        arguments.receipt,
        arguments.manual_verdict,
        arguments.review_note,
    )
    print(json.dumps({"contact_sheet": str(output), "receipt": str(receipt)}, indent=2))


if __name__ == "__main__":
    main()
