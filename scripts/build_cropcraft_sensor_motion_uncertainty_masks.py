#!/usr/bin/env python3
"""Build blur-aware uncertainty masks over the frozen V7-R1 sensor RGBs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from agri_seg.manifest import manifest_sha256, read_manifest, write_manifest


VALID_CLASSES = (0, 1, 2)
IGNORE = 255


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def relative_to_root(path: Path, data_root: Path) -> str:
    return str(path.resolve().relative_to(data_root))


def quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "q05": float(np.quantile(array, 0.05)),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "q95": float(np.quantile(array, 0.95)),
        "max": float(array.max()),
    }


def overlay(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    result = rgb.astype(np.float32).copy()
    colors = {
        1: np.array([40.0, 220.0, 40.0], dtype=np.float32),
        2: np.array([230.0, 40.0, 190.0], dtype=np.float32),
        255: np.array([255.0, 210.0, 0.0], dtype=np.float32),
    }
    for value, color in colors.items():
        selected = mask == value
        result[selected] = 0.55 * result[selected] + 0.45 * color
    return np.clip(result, 0, 255).astype(np.uint8)


def add_label(image: np.ndarray, text: str) -> np.ndarray:
    result = image.copy()
    cv2.rectangle(result, (0, 0), (result.shape[1], 25), (0, 0, 0), -1)
    cv2.putText(
        result,
        text,
        (6, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.47,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return result


def inventory(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        rows.append(
            {
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config must be a YAML object")
    if config.get("frozen_before_build") is not True:
        raise ValueError("R2 gate was not frozen before build")
    data_root = Path(config["data_root"]).expanduser().resolve()
    before = shutil.disk_usage(data_root)

    locked = config["locked_inputs"]
    for name, item in locked.items():
        path = Path(item["path"]).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Locked input {name}: {path}")
        actual = sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"Locked input changed ({name}): {actual}")
    if sha256(Path(__file__).resolve()) != locked["builder_script"]["sha256"]:
        raise ValueError("Builder does not match its frozen self-hash")

    outputs = config["outputs"]
    release = Path(outputs["release"]).resolve()
    manifest_path = Path(outputs["manifest"]).resolve()
    audit_path = Path(outputs["audit"]).resolve()
    contact_path = Path(outputs["contact_sheet"]).resolve()
    contact_receipt_path = Path(outputs["contact_sheet_receipt"]).resolve()
    release_receipt_path = release / "release_receipt.json"
    forbidden_existing = [
        path
        for path in (
            release,
            manifest_path,
            audit_path,
            contact_path,
            contact_receipt_path,
        )
        if path.exists()
    ]
    if forbidden_existing:
        raise FileExistsError(f"R2 outputs already exist: {forbidden_existing}")
    if before.free - int(config["capacity"]["expected_output_bytes"]) < int(
        config["capacity"]["minimum_free_bytes_after"]
    ):
        raise OSError("Insufficient HDD capacity for the frozen R2 build")

    r1_manifest_path = Path(locked["r1_manifest"]["path"]).resolve()
    r1_records = read_manifest(r1_manifest_path)
    r1_audit = load_json(locked["r1_asset_audit"]["path"])
    r1_review = load_json(locked["r1_contact_receipt"]["path"])
    asset_pack = Path(config["source_asset_pack"]).resolve()
    kernels = {
        path.stem: np.load(path).astype(np.float32)
        for path in sorted((asset_pack / "kernels").glob("*.npy"))
    }
    if len(kernels) != 32:
        raise ValueError(f"Expected 32 frozen PSFs, got {len(kernels)}")
    kernel_info = {
        row["kernel_id"]: row for row in r1_audit["kernel_metrics"]["rows"]
    }
    image_info = {
        str(Path(row["generated_image"]).resolve()): row
        for row in r1_audit["image_metrics"]["rows"]
    }
    if len(image_info) != len(r1_records):
        raise ValueError("R1 image audit does not cover every manifest row")

    threshold = float(config["label_policy"]["original_class_confidence_threshold"])
    records = []
    rows: list[dict[str, Any]] = []
    total_original = Counter()
    total_kept = Counter()
    total_new_ignore = 0
    total_valid = 0
    lost_crop_images = 0
    lost_weed_images = 0
    rgb_sha_reuse_pass = True

    for record in r1_records:
        parts = record.sample_id.split(":")
        if len(parts) != 4 or parts[0] != "cropcraft_sensor_motion_pilot_v7_r1":
            raise ValueError(f"Unexpected R1 sample ID: {record.sample_id}")
        _, domain, scene, frame = parts
        source_image = (data_root / record.image_path).resolve()
        source_mask = (data_root / record.mask_path).resolve()
        info = image_info.get(str(source_image))
        if info is None:
            raise ValueError(f"No frozen kernel mapping for {source_image}")
        kernel_id = str(info["kernel_id"])
        kernel = kernels[kernel_id]

        mask = cv2.imread(str(source_mask), cv2.IMREAD_UNCHANGED)
        if mask is None or mask.ndim != 2:
            raise ValueError(f"Invalid source mask: {source_mask}")
        values = set(int(value) for value in np.unique(mask))
        if not values <= {0, 1, 2, 255}:
            raise ValueError(f"Unexpected source mask values: {values}")
        valid = mask != IGNORE
        confidence = np.zeros(mask.shape, dtype=np.float32)
        for class_id in VALID_CLASSES:
            probability = cv2.filter2D(
                (mask == class_id).astype(np.float32),
                -1,
                kernel,
                borderType=cv2.BORDER_REFLECT_101,
            )
            selected = mask == class_id
            confidence[selected] = probability[selected]
        new_ignore = valid & (confidence < threshold)
        output_mask = mask.copy()
        output_mask[new_ignore] = IGNORE
        if np.any((output_mask != mask) & (output_mask != IGNORE)):
            raise ValueError("R2 relabeled a valid source pixel")
        if np.any((mask == IGNORE) & (output_mask != IGNORE)):
            raise ValueError("R2 reverted a source ignore pixel")

        output_image = release / "images" / domain / scene / f"{frame}.png"
        output_mask_path = (
            release / "masks" / record.split / domain / scene / f"{frame}.png"
        )
        output_image.parent.mkdir(parents=True, exist_ok=True)
        output_mask_path.parent.mkdir(parents=True, exist_ok=True)
        os.link(source_image, output_image)
        if not cv2.imwrite(str(output_mask_path), output_mask):
            raise OSError(f"Could not write {output_mask_path}")
        source_image_sha = sha256(source_image)
        output_image_sha = sha256(output_image)
        rgb_sha_reuse_pass &= source_image_sha == output_image_sha

        per_class_original = {
            class_id: int((mask == class_id).sum()) for class_id in VALID_CLASSES
        }
        per_class_kept = {
            class_id: int(((mask == class_id) & ~new_ignore).sum())
            for class_id in VALID_CLASSES
        }
        for class_id in VALID_CLASSES:
            total_original[class_id] += per_class_original[class_id]
            total_kept[class_id] += per_class_kept[class_id]
        lost_crop = per_class_original[1] > 0 and per_class_kept[1] == 0
        lost_weed = per_class_original[2] > 0 and per_class_kept[2] == 0
        lost_crop_images += int(lost_crop)
        lost_weed_images += int(lost_weed)
        new_ignore_count = int(new_ignore.sum())
        valid_count = int(valid.sum())
        total_new_ignore += new_ignore_count
        total_valid += valid_count

        new_record = replace(
            record,
            sample_id=record.sample_id.replace(
                "cropcraft_sensor_motion_pilot_v7_r1",
                "cropcraft_sensor_motion_pilot_v7_r2",
                1,
            ),
            image_path=relative_to_root(output_image, data_root),
            mask_path=relative_to_root(output_mask_path, data_root),
            dataset_id="cropcraft_sensor_motion_pilot_v7_r2",
            sensor="procedural_subpixel_camera_shake_psf_v7_r2_uncertainty_labels",
            growth_stage=record.growth_stage + ";blur_boundary_majority_confidence_ignore_v7_r2",
        )
        records.append(new_record)
        rows.append(
            {
                "sample_id": new_record.sample_id,
                "r1_sample_id": record.sample_id,
                "domain": domain,
                "scene": scene,
                "frame": frame,
                "split": record.split,
                "kernel_id": kernel_id,
                "declared_length_px": float(kernel_info[kernel_id]["declared_length_px"]),
                "trajectory": kernel_info[kernel_id]["trajectory"],
                "source_image_sha256": source_image_sha,
                "output_image_sha256": output_image_sha,
                "source_mask_sha256": sha256(source_mask),
                "output_mask_sha256": sha256(output_mask_path),
                "valid_pixels": valid_count,
                "new_ignore_pixels": new_ignore_count,
                "new_ignore_fraction": new_ignore_count / valid_count,
                "original_class_pixels": {
                    str(key): value for key, value in per_class_original.items()
                },
                "retained_class_pixels": {
                    str(key): value for key, value in per_class_kept.items()
                },
                "crop_entirely_uncertain": lost_crop,
                "weed_entirely_uncertain": lost_weed,
            }
        )

    write_manifest(records, manifest_path)
    split_counts = Counter(record.split for record in records)
    domain_counts = Counter(row["domain"] for row in rows)
    train_groups = {record.group_id for record in records if record.split == "train"}
    calibration_groups = {
        record.group_id for record in records if record.split == "external_calibration"
    }
    aggregate = {
        "samples": len(records),
        "split_counts": dict(sorted(split_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "train_groups": len(train_groups),
        "external_calibration_groups": len(calibration_groups),
        "group_overlap": sorted(train_groups & calibration_groups),
        "valid_pixels": total_valid,
        "new_ignore_pixels": total_new_ignore,
        "new_ignore_fraction": total_new_ignore / total_valid,
        "class_retention": {
            str(class_id): total_kept[class_id] / total_original[class_id]
            for class_id in VALID_CLASSES
        },
        "images_with_crop_entirely_uncertain": lost_crop_images,
        "images_with_weed_entirely_uncertain": lost_weed_images,
        "per_image_new_ignore_fraction": quantiles(
            [float(row["new_ignore_fraction"]) for row in rows]
        ),
    }
    gates = config["quality_gate"]
    checks = {
        "expected_samples": len(records) == int(gates["expected_samples"]),
        "expected_train_samples": split_counts["train"]
        == int(gates["expected_train_samples"]),
        "expected_calibration_samples": split_counts["external_calibration"]
        == int(gates["expected_calibration_samples"]),
        "expected_domains": domain_counts == Counter({"dryland": 100, "paddy": 100}),
        "group_disjoint": not aggregate["group_overlap"],
        "exact_r1_rgb_reuse": rgb_sha_reuse_pass,
        "new_ignore_fraction_band": float(gates["minimum_new_ignore_fraction"])
        <= aggregate["new_ignore_fraction"]
        <= float(gates["maximum_new_ignore_fraction"]),
        "background_retention": aggregate["class_retention"]["0"]
        >= float(gates["minimum_background_retention"]),
        "crop_retention": aggregate["class_retention"]["1"]
        >= float(gates["minimum_crop_retention"]),
        "weed_retention": aggregate["class_retention"]["2"]
        >= float(gates["minimum_weed_retention"]),
        "bounded_crop_loss": lost_crop_images
        <= int(gates["maximum_images_with_crop_entirely_uncertain"]),
        "bounded_weed_loss": lost_weed_images
        <= int(gates["maximum_images_with_weed_entirely_uncertain"]),
        "no_valid_pixel_relabeling": True,
        "no_source_ignore_reversion": True,
        "no_real_pixels_or_fitted_parameters": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"R2 automatic gate failed: {checks}")

    selected_rows = []
    row_by_r1_source = {
        f"cropcraft_agri_robust_pilot_v3:{row['scene']}:{row['frame']}": row
        for row in rows
        if row["domain"] == "dryland"
    }
    row_by_r1_source.update(
        {
            f"cropcraft_paddy_pilot_v4_r5:{row['scene']}:{row['frame']}": row
            for row in rows
            if row["domain"] == "paddy"
        }
    )
    panels = []
    for review_row in r1_review["rows"]:
        source_id = str(review_row["source_sample_id"])
        row = row_by_r1_source.get(source_id)
        if row is None:
            raise ValueError(f"Could not reproduce R1 review row: {source_id}")
        record = next(value for value in records if value.sample_id == row["sample_id"])
        rgb_bgr = cv2.imread(str(data_root / record.image_path), cv2.IMREAD_COLOR)
        source_record = next(
            value
            for value in r1_records
            if value.sample_id == row["r1_sample_id"]
        )
        source_mask = cv2.imread(
            str(data_root / source_record.mask_path), cv2.IMREAD_UNCHANGED
        )
        output_mask = cv2.imread(
            str(data_root / record.mask_path), cv2.IMREAD_UNCHANGED
        )
        if rgb_bgr is None or source_mask is None or output_mask is None:
            raise RuntimeError("Could not load an R2 review panel")
        rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
        uncertain = np.zeros_like(output_mask, dtype=np.uint8)
        uncertain[(output_mask == IGNORE) & (source_mask != IGNORE)] = IGNORE
        panel_images = [
            add_label(rgb, "blurred RGB"),
            add_label(overlay(rgb, source_mask), "R1 hard mask"),
            add_label(overlay(rgb, output_mask), "R2 uncertainty mask"),
            add_label(overlay(rgb, uncertain), "new ignore (yellow)"),
        ]
        panel_images = [
            cv2.resize(value, (256, 256), interpolation=cv2.INTER_AREA)
            for value in panel_images
        ]
        panels.append(np.concatenate(panel_images, axis=1))
        selected_rows.append(
            {
                "sample_id": row["sample_id"],
                "domain": row["domain"],
                "kernel_id": row["kernel_id"],
                "declared_length_px": row["declared_length_px"],
                "trajectory": row["trajectory"],
                "new_ignore_fraction": row["new_ignore_fraction"],
                "source_mask_sha256": row["source_mask_sha256"],
                "output_mask_sha256": row["output_mask_sha256"],
            }
        )
    contact = np.concatenate(panels, axis=0)
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(contact_path), cv2.cvtColor(contact, cv2.COLOR_RGB2BGR)):
        raise OSError(f"Could not write {contact_path}")
    contact_receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection": "same deterministic 12 dryland/paddy length strata as V7-R1",
        "columns": [
            "blurred_rgb",
            "r1_hard_mask_overlay",
            "r2_uncertainty_mask_overlay",
            "new_ignore_overlay",
        ],
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "rows": selected_rows,
    }
    contact_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    contact_receipt_path.write_text(
        json.dumps(contact_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    release_rows = inventory(release)
    release_receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "release": str(release),
        "files": release_rows,
        "inventory_sha256": hashlib.sha256(
            json.dumps(release_rows, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha256(manifest_path),
        "rgb_storage": "hardlinks_to_byte_identical_v7_r1_lossless_png",
        "label_policy": config["label_policy"],
        "external_test_used": False,
    }
    release_receipt_path.write_text(
        json.dumps(release_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    after = shutil.disk_usage(data_root)
    audit = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "cropcraft_sensor_motion_pilot_v7_r2",
        "frozen_config": str(config_path),
        "frozen_config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "source_r1_manifest": str(r1_manifest_path),
        "source_r1_manifest_sha256": manifest_sha256(r1_manifest_path),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha256(manifest_path),
        "release": str(release),
        "release_receipt": str(release_receipt_path),
        "release_receipt_sha256": sha256(release_receipt_path),
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "contact_sheet_receipt": str(contact_receipt_path),
        "contact_sheet_receipt_sha256": sha256(contact_receipt_path),
        "label_policy": config["label_policy"],
        "aggregate": aggregate,
        "rows": rows,
        "quality_gate_checks": checks,
        "all_automatic_quality_gates_passed": all(checks.values()),
        "manual_visual_review_required": True,
        "manual_visual_review_passed": None,
        "inherited_r1_real_duplicate_gate_passed": True,
        "r2_rgb_byte_identical_to_r1": rgb_sha_reuse_pass,
        "real_deblurweedseg_training_or_asset_exposure": 0,
        "capacity": {
            "free_bytes_before": before.free,
            "free_bytes_after": after.free,
            "minimum_free_bytes_after": int(
                config["capacity"]["minimum_free_bytes_after"]
            ),
        },
        "external_test_used": False,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
