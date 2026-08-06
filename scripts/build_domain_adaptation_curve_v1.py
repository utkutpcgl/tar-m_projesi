#!/usr/bin/env python3
"""Build nested Sorghum target-domain subsets for an equal-budget curve.

Selection uses only RGB thumbnails from the official training partition.  A
deterministic farthest-point ordering covers visual diversity and makes every
larger subset a strict superset of smaller subsets.  Calibration/test labels
never participate in subset construction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from agri_seg.constants import MANIFEST_COLUMNS
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
MANIFEST_ROOT = DATA_ROOT / "processed/manifests"
REAL_CORE = MANIFEST_ROOT / "real_core_final.csv"
TARGET = MANIFEST_ROOT / "sorghum_weed.csv"
SIZES = (0, 10, 25, 50, 100, 202)
RELEASE = "domain_adaptation_sorghum_curve_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _thumbnail_feature(record: SampleRecord) -> np.ndarray:
    path = DATA_ROOT / record.image_path
    with Image.open(path) as handle:
        image = handle.convert("RGB")
        image.thumbnail((64, 64), Image.Resampling.BILINEAR)
        image = image.resize((16, 16), Image.Resampling.BILINEAR)
        rgb = np.asarray(image, dtype=np.float32) / 255.0
    # Layout, radiometry, and simple vegetation-excess statistics.  No masks.
    excess_green = 2.0 * rgb[:, :, 1] - rgb[:, :, 0] - rgb[:, :, 2]
    summary = np.asarray(
        [
            *rgb.mean(axis=(0, 1)),
            *rgb.std(axis=(0, 1)),
            *np.quantile(excess_green, (0.10, 0.50, 0.90)),
        ],
        dtype=np.float32,
    )
    return np.concatenate((rgb.reshape(-1), summary))


def farthest_point_order(features: np.ndarray, sample_ids: Sequence[str]) -> list[int]:
    if features.ndim != 2 or len(features) != len(sample_ids):
        raise ValueError("Feature/sample shape mismatch")
    scale = features.std(axis=0)
    normalized = (features - features.mean(axis=0)) / np.where(scale > 1e-6, scale, 1.0)
    mean = normalized.mean(axis=0)
    distances_to_mean = np.square(normalized - mean).sum(axis=1)
    first = min(range(len(sample_ids)), key=lambda index: (distances_to_mean[index], sample_ids[index]))
    order = [first]
    selected = np.zeros(len(sample_ids), dtype=bool)
    selected[first] = True
    minimum_distance = np.square(normalized - normalized[first]).sum(axis=1)
    minimum_distance[first] = -1.0
    while len(order) < len(sample_ids):
        maximum = float(minimum_distance.max())
        candidates = np.flatnonzero(np.isclose(minimum_distance, maximum, rtol=0.0, atol=1e-8))
        chosen = min(candidates.tolist(), key=lambda index: sample_ids[index])
        order.append(chosen)
        selected[chosen] = True
        distance = np.square(normalized - normalized[chosen]).sum(axis=1)
        minimum_distance = np.minimum(minimum_distance, distance)
        minimum_distance[selected] = -1.0
    return order


def _write_manifest(records: Sequence[SampleRecord], destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    temporary.replace(destination)


def build() -> Path:
    real_records = [record for record in read_manifest(REAL_CORE) if record.split in {"train", "val"}]
    target_train = sorted(
        (record for record in read_manifest(TARGET) if record.split == "train"),
        key=lambda record: record.sample_id,
    )
    if len(target_train) != max(SIZES):
        raise RuntimeError(f"Expected {max(SIZES)} target training frames, got {len(target_train)}")
    features = np.stack([_thumbnail_feature(record) for record in target_train])
    order = farthest_point_order(features, [record.sample_id for record in target_train])
    ordered_target = [target_train[index] for index in order]
    outputs: dict[str, object] = {}
    previous: set[str] = set()
    for size in SIZES:
        selected = ordered_target[:size]
        selected_ids = {record.sample_id for record in selected}
        if not previous <= selected_ids:
            raise RuntimeError("Target subsets are not nested")
        previous = selected_ids
        destination = MANIFEST_ROOT / f"domain_adaptation_sorghum_n{size}_v1.csv"
        _write_manifest([*real_records, *selected], destination)
        reread = read_manifest(destination)
        outputs[str(size)] = {
            "manifest": str(destination),
            "manifest_sha256": manifest_sha256(destination),
            "records": len(reread),
            "target_train_records": size,
            "selected_sample_ids": [record.sample_id for record in selected],
        }
    receipt = {
        "schema_version": 1,
        "release": RELEASE,
        "real_core_manifest": str(REAL_CORE),
        "real_core_manifest_sha256": manifest_sha256(REAL_CORE),
        "target_manifest": str(TARGET),
        "target_manifest_sha256": manifest_sha256(TARGET),
        "selection": (
            "deterministic farthest-point traversal of standardized 16x16 RGB "
            "thumbnail plus RGB/excess-green summary features"
        ),
        "selection_uses_masks": False,
        "selection_uses_external_calibration_or_test": False,
        "strictly_nested": True,
        "sizes": list(SIZES),
        "ordered_target_sample_ids": [record.sample_id for record in ordered_target],
        "outputs": outputs,
        "builder": str(Path(__file__).resolve()),
        "builder_sha256": _sha256(Path(__file__).resolve()),
    }
    destination = MANIFEST_ROOT / f"{RELEASE}_receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(build())


if __name__ == "__main__":
    main()
