#!/usr/bin/env python3
"""Append only the train role of the frozen synthetic sensor-motion pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agri_seg.manifest import (
    SampleRecord,
    mask_tree_sha256,
    read_manifest,
    write_manifest,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(records: list[SampleRecord]) -> dict[str, object]:
    return {
        "samples": len(records),
        "splits": dict(sorted(Counter(record.split for record in records).items())),
        "datasets": dict(
            sorted(Counter(record.dataset_id for record in records).items())
        ),
        "target_crop_ids": {
            str(key): value
            for key, value in sorted(
                Counter(record.target_crop_id for record in records).items()
            )
        },
        "groups": len({record.group_id for record in records}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--sensor-pilot", required=True)
    parser.add_argument("--expected-sensor-dataset", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    base_path = Path(args.base).expanduser().resolve()
    sensor_path = Path(args.sensor_pilot).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    base = read_manifest(base_path)
    sensor = read_manifest(sensor_path)

    forbidden_base = sorted({record.split for record in base} - {"train", "val"})
    if forbidden_base:
        raise ValueError(f"Base manifest contains forbidden roles: {forbidden_base}")
    if {record.dataset_id for record in sensor} != {args.expected_sensor_dataset}:
        raise ValueError(
            "Unexpected sensor dataset IDs: "
            f"{sorted({record.dataset_id for record in sensor})}"
        )
    if {record.split for record in sensor} != {"train", "external_calibration"}:
        raise ValueError("Sensor pilot must contain train and external_calibration")
    if len(sensor) != 200:
        raise ValueError(f"Expected 200 sensor rows, got {len(sensor)}")

    sensor_train = [record for record in sensor if record.split == "train"]
    sensor_calibration = [
        record for record in sensor if record.split == "external_calibration"
    ]
    if len(sensor_train) != 160 or len(sensor_calibration) != 40:
        raise ValueError(
            "Expected 160 sensor train and 40 external-calibration rows"
        )
    for role, records, expected_per_crop in (
        ("train", sensor_train, 80),
        ("external_calibration", sensor_calibration, 20),
    ):
        crop_counts = Counter(record.target_crop_id for record in records)
        if crop_counts != Counter({4: expected_per_crop, 12: expected_per_crop}):
            raise ValueError(f"Unexpected sensor crop balance in {role}: {crop_counts}")

    train_groups = {record.group_id for record in sensor_train}
    calibration_groups = {record.group_id for record in sensor_calibration}
    overlap = sorted(train_groups & calibration_groups)
    if overlap:
        raise ValueError(f"Sensor source-scene leakage: {overlap[:10]}")
    if any(record.capture_date != "synthetic" for record in sensor):
        raise ValueError("Sensor pilot contains a non-synthetic capture date")
    if any(record.platform != "synthetic" for record in sensor):
        raise ValueError("Sensor pilot contains a non-synthetic platform")
    expected_image_prefix = "synthetic/cropcraft/sensor_motion_pilot_v7_r1/images/"
    if any(not record.image_path.startswith(expected_image_prefix) for record in sensor):
        raise ValueError("Sensor pilot image path escapes the frozen release")
    allowed_mask_prefixes = (
        "processed/cropcraft_agri_robust_pilot_v3/common_masks/",
        "processed/cropcraft_paddy_pilot_v4_r5/common_masks/",
    )
    if any(
        not record.mask_path.startswith(allowed_mask_prefixes) for record in sensor
    ):
        raise ValueError("Sensor pilot mask does not reuse an accepted source mask")

    base_ids = {record.sample_id for record in base}
    sensor_ids = {record.sample_id for record in sensor_train}
    if len(base_ids) != len(base) or len(sensor_ids) != len(sensor_train):
        raise ValueError("A source manifest contains duplicate sample IDs")
    if base_ids & sensor_ids:
        raise ValueError("Base and sensor sample IDs overlap")

    combined = base + sensor_train
    write_manifest(combined, output_path)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "base": {
                "path": str(base_path),
                "sha256": sha256(base_path),
                "mask_tree_sha256": mask_tree_sha256(base, data_root),
                **counts(base),
            },
            "sensor_pilot": {
                "path": str(sensor_path),
                "sha256": sha256(sensor_path),
                "mask_tree_sha256": mask_tree_sha256(sensor, data_root),
                **counts(sensor),
            },
        },
        "source_scene_audit": {
            "passed": not overlap,
            "train_groups": len(train_groups),
            "external_calibration_groups": len(calibration_groups),
            "overlap": overlap,
        },
        "role_policy": {
            "base": "train_and_val_only",
            "sensor_train": "included_in_challenger_training",
            "sensor_external_calibration": "excluded_from_training",
            "real_deblurweedseg_pixels_in_assets_or_training": 0,
            "external_test_present": False,
        },
        "paired_supervision_policy": {
            "rgb": "directionally_blurred_copy_of_accepted_synthetic_rgb",
            "mask": "byte_reused_latent_pre_exposure_source_mask",
            "soft_boundary_targets_used": False,
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256(output_path),
            "mask_tree_sha256": mask_tree_sha256(combined, data_root),
            **counts(combined),
        },
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
