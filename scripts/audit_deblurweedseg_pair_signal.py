#!/usr/bin/env python3
"""Audit that DeBlurWeedSeg's paired holdout contains measurable blur stress."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from agri_seg.manifest import SampleRecord, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolved(path: str, data_root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else data_root / candidate


def pair_id(record: SampleRecord) -> str:
    image_stem = Path(record.image_path).stem
    parts = record.sample_id.split(":")
    if len(parts) != 3 or parts[0] != "deblurweedseg" or parts[1] != image_stem:
        raise ValueError(f"Unexpected paired sample identity: {record.sample_id}")
    return image_stem


def indexed(path: Path, expected_modality: str) -> dict[str, SampleRecord]:
    records = read_manifest(path)
    index: dict[str, SampleRecord] = {}
    for record in records:
        key = pair_id(record)
        if record.sample_id.split(":")[-1] != expected_modality:
            raise ValueError(f"Unexpected modality in {path}: {record.sample_id}")
        if record.split != "external_calibration":
            raise ValueError(f"Forbidden role in {path}: {record.split}")
        if record.dataset_id != "deblurweedseg":
            raise ValueError(f"Unexpected dataset in {path}: {record.dataset_id}")
        if key in index:
            raise ValueError(f"Duplicate pair id in {path}: {key}")
        index[key] = record
    return index


def grayscale_metrics(path: Path) -> tuple[float, float]:
    with Image.open(path) as image:
        gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    if gray.shape != (128, 128):
        raise ValueError(f"Unexpected image shape {gray.shape}: {path}")
    horizontal = float(np.abs(np.diff(gray, axis=1)).mean())
    vertical = float(np.abs(np.diff(gray, axis=0)).mean())
    return (horizontal + vertical) / 2.0, float(gray.mean())


def distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "p25": float(np.percentile(array, 25)),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "p75": float(np.percentile(array, 75)),
        "max": float(array.max()),
    }


def comparable_metadata(record: SampleRecord) -> dict[str, Any]:
    value = asdict(record)
    for key in ("sample_id", "image_path", "mask_path"):
        value.pop(key)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sharp-manifest", required=True)
    parser.add_argument("--blur-manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-pairs", type=int, default=100)
    parser.add_argument("--minimum-lower-gradient-fraction", type=float, default=0.95)
    parser.add_argument("--maximum-median-gradient-ratio", type=float, default=0.75)
    parser.add_argument("--maximum-mean-brightness-delta", type=float, default=0.10)
    arguments = parser.parse_args()

    sharp_manifest = Path(arguments.sharp_manifest).expanduser().resolve()
    blur_manifest = Path(arguments.blur_manifest).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    sharp = indexed(sharp_manifest, "sharp")
    blur = indexed(blur_manifest, "motion_blur")
    if set(sharp) != set(blur):
        raise ValueError("Sharp and motion-blur manifests contain different pair IDs")
    if len(sharp) != arguments.expected_pairs:
        raise ValueError(f"Expected {arguments.expected_pairs} pairs, got {len(sharp)}")

    sharp_gradient: list[float] = []
    blur_gradient: list[float] = []
    ratios: list[float] = []
    brightness_deltas: list[float] = []
    lower_count = 0
    metadata_mismatches: list[str] = []
    for key in sorted(sharp):
        sharp_record = sharp[key]
        blur_record = blur[key]
        if comparable_metadata(sharp_record) != comparable_metadata(blur_record):
            metadata_mismatches.append(key)
        sharp_value, sharp_brightness = grayscale_metrics(
            resolved(sharp_record.image_path, data_root)
        )
        blur_value, blur_brightness = grayscale_metrics(
            resolved(blur_record.image_path, data_root)
        )
        if sharp_value <= 0.0:
            raise ValueError(f"Non-positive sharp gradient for pair {key}")
        sharp_gradient.append(sharp_value)
        blur_gradient.append(blur_value)
        ratios.append(blur_value / sharp_value)
        brightness_deltas.append(abs(blur_brightness - sharp_brightness))
        lower_count += int(blur_value < sharp_value)

    lower_fraction = lower_count / len(sharp)
    checks = {
        "pair_count": len(sharp) == arguments.expected_pairs,
        "pair_ids_match": set(sharp) == set(blur),
        "paired_metadata_match": not metadata_mismatches,
        "lower_gradient_fraction": (
            lower_fraction >= arguments.minimum_lower_gradient_fraction
        ),
        "median_gradient_ratio": (
            statistics.median(ratios)
            <= arguments.maximum_median_gradient_ratio
        ),
        "mean_brightness_delta": (
            statistics.fmean(brightness_deltas)
            <= arguments.maximum_mean_brightness_delta
        ),
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "deblurweedseg",
        "role": "paired_condition_qc_development_only",
        "metric_definition": (
            "Mean of horizontal and vertical mean absolute first differences "
            "on PIL-L grayscale values scaled to [0,1]."
        ),
        "pair_count": len(sharp),
        "sharp_manifest": str(sharp_manifest),
        "sharp_manifest_sha256": sha256(sharp_manifest),
        "motion_blur_manifest": str(blur_manifest),
        "motion_blur_manifest_sha256": sha256(blur_manifest),
        "sharp_gradient": distribution(sharp_gradient),
        "motion_blur_gradient": distribution(blur_gradient),
        "motion_blur_to_sharp_gradient_ratio": distribution(ratios),
        "absolute_mean_brightness_delta": distribution(brightness_deltas),
        "motion_blur_lower_gradient_pairs": lower_count,
        "motion_blur_lower_gradient_fraction": lower_fraction,
        "metadata_mismatch_pair_ids": metadata_mismatches,
        "thresholds": {
            "minimum_lower_gradient_fraction": (
                arguments.minimum_lower_gradient_fraction
            ),
            "maximum_median_gradient_ratio": (
                arguments.maximum_median_gradient_ratio
            ),
            "maximum_mean_brightness_delta": (
                arguments.maximum_mean_brightness_delta
            ),
        },
        "checks": checks,
        "all_quality_gates_passed": all(checks.values()),
        "causal_limit": (
            "The matched panels are separately captured/annotated rather than "
            "pixel-identical counterfactuals; downstream sharp-to-blur performance "
            "deltas are diagnostic, not a pure causal blur estimate."
        ),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    if not receipt["all_quality_gates_passed"]:
        raise ValueError(json.dumps(receipt, indent=2, sort_keys=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
