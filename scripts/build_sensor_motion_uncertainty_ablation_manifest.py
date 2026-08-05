#!/usr/bin/env python3
"""Append only V7-R2 uncertainty-mask training rows to the accepted manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agri_seg.manifest import mask_tree_sha256, read_manifest, write_manifest


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(records: list) -> dict[str, object]:
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
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    base_path = Path(args.base).expanduser().resolve()
    sensor_path = Path(args.sensor_pilot).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    if output_path.exists() or receipt_path.exists():
        raise FileExistsError("R2 combined-manifest outputs already exist")
    base = read_manifest(base_path)
    sensor = read_manifest(sensor_path)

    if {record.split for record in base} - {"train", "val"}:
        raise ValueError("Base manifest contains a forbidden role")
    expected_dataset = "cropcraft_sensor_motion_pilot_v7_r2"
    if {record.dataset_id for record in sensor} != {expected_dataset}:
        raise ValueError("Unexpected R2 sensor dataset ID")
    if {record.split for record in sensor} != {"train", "external_calibration"}:
        raise ValueError("R2 sensor pilot must contain train and calibration")
    sensor_train = [record for record in sensor if record.split == "train"]
    sensor_calibration = [
        record for record in sensor if record.split == "external_calibration"
    ]
    if len(sensor) != 200 or len(sensor_train) != 160 or len(sensor_calibration) != 40:
        raise ValueError("Unexpected R2 sample/role counts")
    for records, expected in ((sensor_train, 80), (sensor_calibration, 20)):
        if Counter(record.target_crop_id for record in records) != Counter(
            {4: expected, 12: expected}
        ):
            raise ValueError("Unexpected R2 crop balance")
    train_groups = {record.group_id for record in sensor_train}
    calibration_groups = {record.group_id for record in sensor_calibration}
    overlap = sorted(train_groups & calibration_groups)
    if overlap:
        raise ValueError(f"R2 source-scene leakage: {overlap}")
    if any(record.capture_date != "synthetic" for record in sensor):
        raise ValueError("Non-synthetic capture entered R2")
    if any(record.platform != "synthetic" for record in sensor):
        raise ValueError("Non-synthetic platform entered R2")
    image_prefix = "synthetic/cropcraft/sensor_motion_pilot_v7_r2/images/"
    mask_prefix = "synthetic/cropcraft/sensor_motion_pilot_v7_r2/masks/"
    if any(not record.image_path.startswith(image_prefix) for record in sensor):
        raise ValueError("R2 image escapes its frozen release")
    if any(not record.mask_path.startswith(mask_prefix) for record in sensor):
        raise ValueError("R2 mask escapes its frozen release")
    base_ids = {record.sample_id for record in base}
    sensor_ids = {record.sample_id for record in sensor_train}
    if len(base_ids) != len(base) or len(sensor_ids) != len(sensor_train):
        raise ValueError("Duplicate sample IDs in an input manifest")
    if base_ids & sensor_ids:
        raise ValueError("Base and R2 sample IDs overlap")

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
            "sensor_uncertainty_pilot": {
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
            "sensor_external_calibration": "excluded_from_training_and_selection",
            "real_deblurweedseg_pixels_in_assets_or_training": 0,
            "external_test_present": False,
        },
        "supervision_policy": {
            "rgb": "byte_identical_v7_r1_directional_motion_rgb",
            "mask": "original_class_or_fail_closed_ignore_by_exact_psf_majority",
            "valid_class_relabeling": False,
            "soft_targets": False,
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
