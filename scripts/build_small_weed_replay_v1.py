#!/usr/bin/env python3
"""Materialize training-only crops centered on small weed-mask components.

This creates a sampler-compatible replay domain without changing the accepted
training code.  Components are semantic connected-component proxies, not
botanical instances.  Only ``train`` records are scanned; validation and test
frames are excluded before any mask is opened.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from torchvision.transforms import functional as vision_functional

from agri_seg.constants import MANIFEST_COLUMNS, WEED
from agri_seg.data import load_rgb_image
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
SOURCE_MANIFEST = (
    DATA_ROOT
    / "processed/manifests/real_sorghum_cropcraft_robust_v3_paddy_trainval_v4_r5.csv"
)
RELEASE = "small_weed_replay_v1"
OUTPUT_ROOT = DATA_ROOT / "processed" / RELEASE
REPLAY_MANIFEST = DATA_ROOT / "processed/manifests" / f"{RELEASE}.csv"
COMBINED_MANIFEST = (
    DATA_ROOT / "processed/manifests/real_sorghum_cropcraft_paddy_small_replay_v1.csv"
)
PATCH_SIZE = 512
MIN_DIAMETER = 4.0
MAX_DIAMETER = 28.0
QUOTAS = {
    "phenobench": 80,
    "acre": 80,
    "weedsgalore": 70,
    "we3ds": 80,
    "rose": 80,
    "sorghum_weed": 80,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rank(record: SampleRecord) -> str:
    return hashlib.sha256(record.sample_id.encode("utf-8")).hexdigest()


def _small_component(mask_path: Path) -> dict[str, float] | None:
    with Image.open(mask_path) as handle:
        mask = np.asarray(handle.convert("L"), dtype=np.uint8)
    weed = mask == WEED
    labels, count = ndimage.label(weed, structure=np.ones((3, 3), dtype=np.uint8))
    if not count:
        return None
    rows, columns = np.nonzero(weed)
    component_labels = labels[rows, columns]
    areas = np.bincount(component_labels, minlength=count + 1)[1:]
    diameters = 2.0 * np.sqrt(areas.astype(np.float64) / math.pi)
    eligible = np.flatnonzero((diameters >= MIN_DIAMETER) & (diameters < MAX_DIAMETER))
    if not eligible.size:
        return None
    # Prefer a true sub-patch component near 10 px, then a 14--28 px component.
    chosen = min(
        eligible.tolist(),
        key=lambda index: (diameters[index] >= 14.0, abs(float(diameters[index]) - 10.0), index),
    )
    label = chosen + 1
    selection = component_labels == label
    return {
        "row": float(rows[selection].mean()),
        "column": float(columns[selection].mean()),
        "area_px": int(areas[chosen]),
        "equivalent_diameter_px": float(diameters[chosen]),
        "image_height": int(mask.shape[0]),
        "image_width": int(mask.shape[1]),
    }


def _window(center: float, length: int) -> tuple[int, int, int, int]:
    start = int(round(center)) - PATCH_SIZE // 2
    source_start = max(0, start)
    source_end = min(length, start + PATCH_SIZE)
    pad_before = source_start - start
    pad_after = PATCH_SIZE - pad_before - (source_end - source_start)
    return source_start, source_end, pad_before, pad_after


def _materialize_image(
    source_path: Path,
    destination_stem: Path,
    y_window: tuple[int, int, int, int],
    x_window: tuple[int, int, int, int],
) -> Path:
    image = load_rgb_image(source_path)
    top, bottom, pad_top, pad_bottom = y_window
    left, right, pad_left, pad_right = x_window
    if isinstance(image, Image.Image):
        crop = image.crop((left, top, right, bottom))
        crop = ImageOps.expand(
            crop,
            border=(pad_left, pad_top, pad_right, pad_bottom),
            fill=(0, 0, 0),
        )
        destination = destination_stem.with_suffix(".png")
        destination.parent.mkdir(parents=True, exist_ok=True)
        crop.save(destination, optimize=True)
    else:
        crop = image[:, top:bottom, left:right]
        crop = vision_functional.pad(
            crop,
            [pad_left, pad_top, pad_right, pad_bottom],
            fill=0.0,
        )
        destination = destination_stem.with_suffix(".npy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        np.save(
            destination,
            crop.permute(1, 2, 0).cpu().numpy().astype(np.float16),
            allow_pickle=False,
        )
    return destination


def _materialize_mask(
    source_path: Path,
    destination: Path,
    y_window: tuple[int, int, int, int],
    x_window: tuple[int, int, int, int],
) -> None:
    top, bottom, pad_top, pad_bottom = y_window
    left, right, pad_left, pad_right = x_window
    with Image.open(source_path) as handle:
        crop = handle.convert("L").crop((left, top, right, bottom))
    crop = ImageOps.expand(
        crop,
        border=(pad_left, pad_top, pad_right, pad_bottom),
        fill=255,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    crop.save(destination, optimize=True)


def _write_manifest(records: Sequence[SampleRecord], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    temporary.replace(destination)


def build() -> Path:
    source_records = read_manifest(SOURCE_MANIFEST)
    train_by_dataset: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in source_records:
        if record.split == "train" and record.dataset_id in QUOTAS:
            train_by_dataset[record.dataset_id].append(record)
    selected: list[tuple[SampleRecord, dict[str, float]]] = []
    scanned: dict[str, int] = {}
    for dataset_id, quota in QUOTAS.items():
        candidates: list[tuple[SampleRecord, dict[str, float]]] = []
        records = sorted(train_by_dataset[dataset_id], key=_rank)
        scan_cap = min(len(records), max(quota * 5, quota + 40))
        processed = 0
        for record in records[:scan_cap]:
            processed += 1
            component = _small_component(DATA_ROOT / record.mask_path)
            if component is not None:
                candidates.append((record, component))
            if len(candidates) >= quota:
                break
        scanned[dataset_id] = processed
        selected.extend(candidates[:quota])

    replay_records: list[SampleRecord] = []
    inventory: list[dict[str, Any]] = []
    for index, (source, component) in enumerate(selected):
        y_window = _window(component["row"], int(component["image_height"]))
        x_window = _window(component["column"], int(component["image_width"]))
        safe_id = f"{index:04d}_{hashlib.sha256(source.sample_id.encode()).hexdigest()[:12]}"
        image_path = _materialize_image(
            DATA_ROOT / source.image_path,
            OUTPUT_ROOT / "images" / safe_id,
            y_window,
            x_window,
        )
        mask_path = OUTPUT_ROOT / "masks" / f"{safe_id}.png"
        _materialize_mask(DATA_ROOT / source.mask_path, mask_path, y_window, x_window)
        replay = SampleRecord(
            sample_id=f"{RELEASE}:{safe_id}",
            image_path=image_path.relative_to(DATA_ROOT).as_posix(),
            mask_path=mask_path.relative_to(DATA_ROOT).as_posix(),
            split="train",
            dataset_id=RELEASE,
            field_id=f"{source.dataset_id}:{source.field_id}",
            session_id=source.session_id,
            capture_date=source.capture_date,
            platform=source.platform,
            sensor=source.sensor,
            target_crop_id=source.target_crop_id,
            crop_species=source.crop_species,
            weed_species_optional=source.weed_species_optional,
            growth_stage=source.growth_stage,
            annotation_exhaustive=source.annotation_exhaustive,
            license_status=source.license_status,
            commercial_allowed=source.commercial_allowed,
        )
        replay_records.append(replay)
        inventory.append(
            {
                "replay_sample_id": replay.sample_id,
                "source_sample_id": source.sample_id,
                "source_dataset_id": source.dataset_id,
                "component": component,
                "image_path": replay.image_path,
                "image_sha256": _sha256(image_path),
                "mask_path": replay.mask_path,
                "mask_sha256": _sha256(mask_path),
            }
        )
    if len(replay_records) < 200:
        raise RuntimeError(f"Insufficient replay diversity: {len(replay_records)}")
    _write_manifest(replay_records, REPLAY_MANIFEST)
    _write_manifest([*source_records, *replay_records], COMBINED_MANIFEST)
    by_source = defaultdict(int)
    for row in inventory:
        by_source[row["source_dataset_id"]] += 1
    receipt = {
        "schema_version": 1,
        "release": RELEASE,
        "source_manifest": str(SOURCE_MANIFEST),
        "source_manifest_sha256": manifest_sha256(SOURCE_MANIFEST),
        "replay_manifest": str(REPLAY_MANIFEST),
        "replay_manifest_sha256": manifest_sha256(REPLAY_MANIFEST),
        "combined_manifest": str(COMBINED_MANIFEST),
        "combined_manifest_sha256": manifest_sha256(COMBINED_MANIFEST),
        "selection_scope": "training split only; validation/test excluded before mask scan",
        "component_unit": "8-connected semantic weed component proxy, not plant instance",
        "diameter_range_px": [MIN_DIAMETER, MAX_DIAMETER],
        "patch_size_px": PATCH_SIZE,
        "quotas": QUOTAS,
        "scanned_records": scanned,
        "selected_by_source_dataset": dict(sorted(by_source.items())),
        "records": len(replay_records),
        "inventory": inventory,
        "builder": str(Path(__file__).resolve()),
        "builder_sha256": _sha256(Path(__file__).resolve()),
    }
    receipt_path = OUTPUT_ROOT / "build_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(build())


if __name__ == "__main__":
    main()
