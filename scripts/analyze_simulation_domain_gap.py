#!/usr/bin/env python3
"""Compare bounded RGB/mask statistics for real and stock synthetic data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from agri_seg.constants import CROP, IGNORE, WEED
from agri_seg.data import load_rgb_image, to_display_pil
from agri_seg.manifest import SampleRecord, iter_resolved, read_manifest


def stable_key(record: SampleRecord) -> str:
    return hashlib.sha256(record.sample_id.encode("utf-8")).hexdigest()


def selected_records(
    manifest: Path, per_dataset: int, splits: set[str]
) -> list[SampleRecord]:
    grouped: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in read_manifest(manifest):
        if record.split in splits:
            grouped[record.dataset_id].append(record)
    selected: list[SampleRecord] = []
    for dataset in sorted(grouped):
        selected.extend(sorted(grouped[dataset], key=stable_key)[:per_dataset])
    return selected


def sample_stats(image_path: Path, mask_path: Path) -> dict[str, float]:
    display = to_display_pil(load_rgb_image(image_path)).resize(
        (128, 128), Image.Resampling.BILINEAR
    )
    rgb = np.asarray(display, dtype=np.float32) / 255.0
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    saturation = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )
    gray = rgb.mean(axis=2)
    texture = (
        np.abs(np.diff(gray, axis=0)).mean()
        + np.abs(np.diff(gray, axis=1)).mean()
    ) / 2.0
    with Image.open(mask_path) as mask_handle:
        mask = np.asarray(mask_handle.convert("L"), dtype=np.uint8)
    valid = mask != IGNORE
    valid_pixels = max(1, int(valid.sum()))
    return {
        "brightness_mean": float(rgb.mean()),
        "brightness_std": float(rgb.std()),
        "saturation_mean": float(saturation.mean()),
        "green_dominance": float(
            (rgb[:, :, 1] - (rgb[:, :, 0] + rgb[:, :, 2]) / 2.0).mean()
        ),
        "texture_abs_gradient": float(texture),
        "crop_fraction": float(((mask == CROP) & valid).sum() / valid_pixels),
        "weed_fraction": float(((mask == WEED) & valid).sum() / valid_pixels),
        "ignore_fraction": float((mask == IGNORE).mean()),
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, object]:
    if not rows:
        raise ValueError("Cannot aggregate an empty sample")
    result: dict[str, object] = {"samples": len(rows), "metrics": {}}
    metrics = result["metrics"]
    for name in sorted(rows[0]):
        values = np.asarray([row[name] for row in rows], dtype=np.float64)
        metrics[name] = {
            "mean": float(values.mean()),
            "q05": float(np.quantile(values, 0.05)),
            "q50": float(np.quantile(values, 0.50)),
            "q95": float(np.quantile(values, 0.95)),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", required=True)
    parser.add_argument("--synthetic", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-dataset", type=int, default=30)
    parser.add_argument("--real-splits", nargs="+", default=["train"])
    parser.add_argument("--synthetic-splits", nargs="+", default=["train"])
    args = parser.parse_args()

    root = Path(args.data_root).expanduser().resolve()
    real_splits = {str(value) for value in args.real_splits}
    synthetic_splits = {str(value) for value in args.synthetic_splits}
    real_records = selected_records(Path(args.real), args.per_dataset, real_splits)
    synthetic_records = selected_records(
        Path(args.synthetic), args.per_dataset, synthetic_splits
    )

    def evaluate(records: list[SampleRecord]) -> tuple[dict[str, object], dict[str, object]]:
        by_dataset: dict[str, list[dict[str, float]]] = defaultdict(list)
        pooled: list[dict[str, float]] = []
        for record, image_path, mask_path in iter_resolved(records, root):
            row = sample_stats(image_path, mask_path)
            by_dataset[record.dataset_id].append(row)
            pooled.append(row)
        return (
            aggregate(pooled),
            {dataset: aggregate(rows) for dataset, rows in sorted(by_dataset.items())},
        )

    real_pooled, real_by_dataset = evaluate(real_records)
    synthetic_pooled, synthetic_by_dataset = evaluate(synthetic_records)
    outside_real_90_percent_interval = {}
    for name, synthetic_metric in synthetic_pooled["metrics"].items():
        real_metric = real_pooled["metrics"][name]
        outside_real_90_percent_interval[name] = not (
            real_metric["q05"]
            <= synthetic_metric["q50"]
            <= real_metric["q95"]
        )
    report = {
        "schema_version": 1,
        "sampling": (
            "deterministic SHA256(sample_id), bounded per training dataset"
        ),
        "per_dataset_limit": args.per_dataset,
        "real_splits": sorted(real_splits),
        "synthetic_splits": sorted(synthetic_splits),
        "real": {"pooled": real_pooled, "by_dataset": real_by_dataset},
        "synthetic": {
            "pooled": synthetic_pooled,
            "by_dataset": synthetic_by_dataset,
        },
        "synthetic_median_outside_real_pooled_q05_q95": (
            outside_real_90_percent_interval
        ),
        "interpretation": (
            "These low-order statistics expose gross mismatch only; model A/B on "
            "untouched real development data is the acceptance criterion."
        ),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
