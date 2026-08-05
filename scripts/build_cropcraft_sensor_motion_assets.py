#!/usr/bin/env python3
"""Build a scene-disjoint camera-shake PSF asset bank and synthetic pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from agri_seg.manifest import SampleRecord, read_manifest, write_manifest


DATASET_ID = "cropcraft_sensor_motion_pilot_v7_r1"
SENSOR_ID = "procedural_subpixel_camera_shake_psf_v7_r1"
PALETTE = {
    BACKGROUND: (45, 45, 45),
    CROP: (35, 205, 70),
    WEED: (235, 70, 70),
    IGNORE: (230, 50, 230),
}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "q05": float(np.quantile(array, 0.05)),
        "median": float(np.median(array)),
        "q95": float(np.quantile(array, 0.95)),
        "max": float(array.max()),
        "mean": float(array.mean()),
    }


def deposit_bilinear(kernel: np.ndarray, x: float, y: float) -> None:
    x0 = math.floor(x)
    y0 = math.floor(y)
    dx = x - x0
    dy = y - y0
    for oy, wy in ((0, 1.0 - dy), (1, dy)):
        for ox, wx in ((0, 1.0 - dx), (1, dx)):
            xx = x0 + ox
            yy = y0 + oy
            if 0 <= xx < kernel.shape[1] and 0 <= yy < kernel.shape[0]:
                kernel[yy, xx] += float(wx * wy)


def camera_shake_kernel(
    size: int,
    length: float,
    angle_deg: float,
    curvature: float,
    phase: float,
) -> np.ndarray:
    """Rasterize a centered, sub-pixel exposure trajectory into a PSF."""
    if size % 2 != 1:
        raise ValueError("Kernel size must be odd")
    center = (size - 1) / 2.0
    angle = math.radians(angle_deg)
    tangent = np.asarray([math.cos(angle), math.sin(angle)], dtype=np.float64)
    normal = np.asarray([-math.sin(angle), math.cos(angle)], dtype=np.float64)
    kernel = np.zeros((size, size), dtype=np.float64)
    samples = max(257, int(math.ceil(length * 32)))
    for t in np.linspace(-0.5, 0.5, samples, dtype=np.float64):
        # The sine term is zero at both shutter endpoints. Linear kernels use
        # curvature=0; curved kernels approximate smooth hand/vehicle shake.
        offset = tangent * (length * t)
        offset += normal * (curvature * math.sin(2.0 * math.pi * (t + phase)))
        deposit_bilinear(kernel, center + offset[0], center + offset[1])
    kernel = cv2.GaussianBlur(kernel.astype(np.float32), (3, 3), 0.35)
    total = float(kernel.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Invalid camera-shake kernel")
    kernel /= total
    return kernel.astype(np.float32)


def kernel_centroid(kernel: np.ndarray) -> tuple[float, float]:
    ys, xs = np.indices(kernel.shape, dtype=np.float64)
    total = float(kernel.sum())
    return float((xs * kernel).sum() / total), float((ys * kernel).sum() / total)


def image_gradient_mean(rgb: np.ndarray) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.sqrt(gx * gx + gy * gy).mean())


def apply_psf(rgb: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    working = rgb.astype(np.float32) / 255.0
    blurred = cv2.filter2D(
        working, -1, kernel, borderType=cv2.BORDER_REFLECT_101
    )
    return np.clip(np.rint(blurred * 255.0), 0, 255).astype(np.uint8)


def scene_index(record: SampleRecord) -> int:
    if not record.field_id.startswith("scene_"):
        raise ValueError(f"Unexpected CropCraft scene: {record.field_id}")
    return int(record.field_id.split("_")[-1])


def relative_to_root(path: Path, data_root: Path) -> str:
    return str(path.resolve().relative_to(data_root.resolve()))


def mask_rgb(mask: np.ndarray) -> Image.Image:
    unexpected = set(int(value) for value in np.unique(mask)) - set(PALETTE)
    if unexpected:
        raise ValueError(f"Unexpected common mask values: {unexpected}")
    output = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for value, colour in PALETTE.items():
        output[mask == value] = colour
    return Image.fromarray(output, mode="RGB")


def tree_inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected YAML mapping")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    arguments = parser.parse_args()

    config_path = Path(arguments.config).expanduser().resolve()
    config = load_config(config_path)
    if config.get("frozen_before_asset_build") is not True:
        raise ValueError("Sensor asset protocol was not frozen before build")
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    pack_dir = Path(str(config["outputs"]["asset_pack"])).expanduser().resolve()
    release_dir = Path(str(config["outputs"]["release"])).expanduser().resolve()
    manifest_path = Path(str(config["outputs"]["manifest"])).expanduser().resolve()
    audit_path = Path(str(config["outputs"]["audit"])).expanduser().resolve()
    contact_path = Path(str(config["outputs"]["contact_sheet"])).expanduser().resolve()
    contact_receipt_path = Path(
        str(config["outputs"]["contact_sheet_receipt"])
    ).expanduser().resolve()
    for path in (
        pack_dir,
        release_dir,
        manifest_path,
        audit_path,
        contact_path,
        contact_receipt_path,
    ):
        if path.exists():
            raise FileExistsError(path)

    expected_bytes = int(config["capacity"]["expected_output_bytes"])
    minimum_after = int(config["capacity"]["minimum_free_bytes_after"])
    free_before = shutil.disk_usage(data_root).free
    if free_before - expected_bytes < minimum_after:
        raise OSError("Insufficient data-root capacity for sensor pilot")

    sources: list[tuple[str, Path, list[SampleRecord]]] = []
    for domain, specification in sorted(config["sources"].items()):
        manifest = Path(str(specification["manifest"])).expanduser().resolve()
        if sha256(manifest) != str(specification["sha256"]):
            raise ValueError(f"Source manifest changed: {domain}")
        receipt = Path(str(specification["release_receipt"])).expanduser().resolve()
        if sha256(receipt) != str(specification["release_receipt_sha256"]):
            raise ValueError(f"Source release receipt changed: {domain}")
        records = sorted(read_manifest(manifest), key=lambda item: item.sample_id)
        if len(records) != 100 or len({item.field_id for item in records}) != 25:
            raise ValueError(f"Expected 100 rows / 25 scenes: {domain}")
        if {item.split for item in records} != {"train", "val"}:
            raise ValueError(f"Expected source pilot train/val roles: {domain}")
        for item in records:
            expected_split = "train" if scene_index(item) < 20 else "val"
            if item.split != expected_split:
                raise ValueError(
                    f"Source scene split mismatch ({domain}): "
                    f"{item.sample_id}/{item.split} != {expected_split}"
                )
        sources.append((domain, manifest, records))

    kernel_spec = config["kernel_bank"]
    count = int(kernel_spec["count"])
    size = int(kernel_spec["size"])
    lengths = [float(value) for value in kernel_spec["lengths_px"]]
    if count != 32 or len(lengths) != count:
        raise ValueError("The frozen v7_r1 bank requires 32 declared lengths")
    rng = np.random.default_rng(int(kernel_spec["seed"]))
    kernel_dir = pack_dir / "kernels"
    preview_dir = pack_dir / "previews"
    kernel_dir.mkdir(parents=True)
    preview_dir.mkdir(parents=True)
    kernel_rows: list[dict[str, object]] = []
    kernels: list[np.ndarray] = []
    for index, length in enumerate(lengths):
        angle = (index * 180.0 / count + float(rng.uniform(-2.0, 2.0))) % 180.0
        curved = index >= count // 2
        curvature = 0.0
        if curved:
            sign = -1.0 if index % 2 else 1.0
            curvature = sign * length * float(rng.uniform(0.08, 0.20))
        phase = float(rng.uniform(-0.125, 0.125)) if curved else 0.0
        kernel = camera_shake_kernel(size, length, angle, curvature, phase)
        kernels.append(kernel)
        npy_path = kernel_dir / f"psf_{index:02d}.npy"
        np.save(npy_path, kernel, allow_pickle=False)
        preview = np.clip(kernel / max(float(kernel.max()), 1e-12) * 255.0, 0, 255)
        preview_path = preview_dir / f"psf_{index:02d}.png"
        Image.fromarray(preview.astype(np.uint8), mode="L").resize(
            (size * 6, size * 6), Image.Resampling.NEAREST
        ).save(preview_path, optimize=False)
        centroid = kernel_centroid(kernel)
        center = (size - 1) / 2.0
        kernel_rows.append(
            {
                "kernel_id": f"psf_{index:02d}",
                "trajectory": "curved" if curved else "linear",
                "declared_length_px": length,
                "angle_deg": angle,
                "curvature_px": curvature,
                "phase": phase,
                "shape": list(kernel.shape),
                "sum": float(kernel.sum()),
                "minimum": float(kernel.min()),
                "maximum": float(kernel.max()),
                "centroid": list(centroid),
                "centroid_error_px": float(
                    math.hypot(centroid[0] - center, centroid[1] - center)
                ),
                "npy": str(npy_path.relative_to(pack_dir)),
                "npy_sha256": sha256(npy_path),
                "preview": str(preview_path.relative_to(pack_dir)),
                "preview_sha256": sha256(preview_path),
            }
        )

    license_path = pack_dir / "LICENSES.txt"
    license_path.write_text(
        "Camera-shake PSF geometry and metadata: CC0-1.0.\n"
        "Source CropCraft images retain their recorded generated/Poly Haven "
        "CC0 provenance; no real-image pixels enter this pack.\n",
        encoding="utf-8",
    )
    kernel_inventory = tree_inventory(pack_dir)
    pack = {
        "schema_version": 1,
        "pack_id": "cropcraft_sensor_motion_v7_r1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "license": "CC0-1.0",
        "isolated_change": "rgb_camera_shake_psf_only_masks_unchanged",
        "real_training_or_asset_pixels": 0,
        "kernel_bank": kernel_rows,
        "kernel_inventory": kernel_inventory,
        "kernel_inventory_sha256": canonical_sha256(kernel_inventory),
        "frozen_config": str(config_path),
        "frozen_config_sha256": sha256(config_path),
    }
    pack_path = pack_dir / "PACK.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    image_metrics: list[dict[str, object]] = []
    output_records: list[SampleRecord] = []
    generated_hashes: set[str] = set()
    source_image_hashes: set[str] = set()
    kernel_usage: Counter[str] = Counter()
    mapping_index = 0
    for domain, _, records in sources:
        for source in records:
            source_image = data_root / source.image_path
            source_mask = data_root / source.mask_path
            if not source_image.is_file() or not source_mask.is_file():
                raise FileNotFoundError(source_image if not source_image.is_file() else source_mask)
            with Image.open(source_image) as handle:
                rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
            with Image.open(source_mask) as handle:
                mask = np.asarray(handle.convert("L"), dtype=np.uint8)
            if rgb.shape[:2] != mask.shape:
                raise ValueError(f"Source image/mask mismatch: {source.sample_id}")
            if set(int(value) for value in np.unique(mask)) - set(PALETTE):
                raise ValueError(f"Invalid source mask: {source.sample_id}")
            kernel_index = (mapping_index * 13 + 7) % count
            kernel = kernels[kernel_index]
            kernel_id = str(kernel_rows[kernel_index]["kernel_id"])
            blurred = apply_psf(rgb, kernel)
            scene = source.field_id
            frame = source.sample_id.split(":")[-1]
            destination = release_dir / "images" / domain / scene / f"{frame}.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(blurred, mode="RGB").save(destination, optimize=False)
            source_hash = sha256(source_image)
            generated_hash = sha256(destination)
            if generated_hash == source_hash:
                raise ValueError(f"Motion transform made no change: {source.sample_id}")
            if generated_hash in generated_hashes:
                raise ValueError(f"Duplicate generated RGB: {source.sample_id}")
            generated_hashes.add(generated_hash)
            source_image_hashes.add(source_hash)
            kernel_usage[kernel_id] += 1

            difference = np.abs(blurred.astype(np.float32) - rgb.astype(np.float32)) / 255.0
            source_gradient = image_gradient_mean(rgb)
            blurred_gradient = image_gradient_mean(blurred)
            metric = {
                "sample_id": source.sample_id,
                "domain": domain,
                "scene": scene,
                "kernel_id": kernel_id,
                "source_image": str(source_image.resolve()),
                "source_image_sha256": source_hash,
                "generated_image": str(destination.resolve()),
                "generated_image_sha256": generated_hash,
                "mask": str(source_mask.resolve()),
                "mask_sha256": sha256(source_mask),
                "mean_absolute_change": float(difference.mean()),
                "p95_absolute_change": float(np.quantile(difference, 0.95)),
                "maximum_channel_mean_shift": float(
                    np.abs(
                        blurred.astype(np.float64).mean(axis=(0, 1))
                        - rgb.astype(np.float64).mean(axis=(0, 1))
                    ).max()
                    / 255.0
                ),
                "source_gradient_mean": source_gradient,
                "blurred_gradient_mean": blurred_gradient,
                "gradient_ratio": blurred_gradient / max(source_gradient, 1e-12),
            }
            image_metrics.append(metric)
            split = "train" if scene_index(source) < 20 else "external_calibration"
            output_records.append(
                SampleRecord(
                    sample_id=f"{DATASET_ID}:{domain}:{scene}:{frame}",
                    image_path=relative_to_root(destination, data_root),
                    mask_path=source.mask_path,
                    split=split,
                    dataset_id=DATASET_ID,
                    field_id=f"{domain}_{scene}",
                    session_id=f"{source.dataset_id}:{source.session_id}",
                    capture_date=source.capture_date,
                    platform="synthetic",
                    sensor=SENSOR_ID,
                    target_crop_id=source.target_crop_id,
                    crop_species=source.crop_species,
                    weed_species_optional=source.weed_species_optional,
                    growth_stage=source.growth_stage,
                    annotation_exhaustive=True,
                    license_status=(
                        f"{source.license_status};procedural-camera-shake-PSF-CC0-1.0"
                    ),
                    commercial_allowed=True,
                )
            )
            mapping_index += 1

    write_manifest(output_records, manifest_path)
    train = [record for record in output_records if record.split == "train"]
    calibration = [
        record for record in output_records if record.split == "external_calibration"
    ]
    train_groups = {record.group_id for record in train}
    calibration_groups = {record.group_id for record in calibration}
    group_overlap = sorted(train_groups & calibration_groups)
    mean_changes = [float(row["mean_absolute_change"]) for row in image_metrics]
    channel_shifts = [float(row["maximum_channel_mean_shift"]) for row in image_metrics]
    gradient_ratios = [float(row["gradient_ratio"]) for row in image_metrics]
    gate = config["quality_gate"]
    center_limit = float(gate["maximum_kernel_centroid_error_px"])
    checks = {
        "expected_samples": len(output_records) == int(gate["expected_samples"]),
        "expected_train_samples": len(train) == int(gate["expected_train_samples"]),
        "expected_calibration_samples": len(calibration)
        == int(gate["expected_calibration_samples"]),
        "expected_source_domains": Counter(row["domain"] for row in image_metrics)
        == {"dryland": 100, "paddy": 100},
        "expected_kernel_count": len(kernels) == int(gate["expected_kernels"]),
        "all_kernels_used": set(kernel_usage) == {row["kernel_id"] for row in kernel_rows},
        "linear_and_curved_balance": Counter(row["trajectory"] for row in kernel_rows)
        == {"linear": 16, "curved": 16},
        "minimum_length_families": len({row["declared_length_px"] for row in kernel_rows})
        >= int(gate["minimum_length_families"]),
        "minimum_angle_bins": len({int(float(row["angle_deg"]) // 22.5) for row in kernel_rows})
        >= int(gate["minimum_angle_bins"]),
        "kernel_nonnegative_and_normalized": all(
            float(row["minimum"]) >= 0.0 and abs(float(row["sum"]) - 1.0) <= 1e-6
            for row in kernel_rows
        ),
        "kernel_centroids": max(float(row["centroid_error_px"]) for row in kernel_rows)
        <= center_limit,
        "all_rgb_changed": len(generated_hashes & source_image_hashes) == 0,
        "no_generated_exact_duplicates": len(generated_hashes) == len(output_records),
        "group_disjoint": not group_overlap,
        "mean_change_band": float(gate["minimum_median_absolute_change"])
        <= float(np.median(mean_changes))
        <= float(gate["maximum_median_absolute_change"]),
        "brightness_preservation": float(np.quantile(channel_shifts, 0.95))
        <= float(gate["maximum_p95_channel_mean_shift"]),
        "gradient_attenuation_band": float(gate["minimum_median_gradient_ratio"])
        <= float(np.median(gradient_ratios))
        <= float(gate["maximum_median_gradient_ratio"]),
        "no_real_pixels_in_assets_or_training": int(pack["real_training_or_asset_pixels"])
        == 0,
    }

    # Contact sheet selection is deterministic and independent of model output:
    # six length strata per source domain, including train/calibration scenes.
    selected_indices: list[int] = []
    for domain in ("dryland", "paddy"):
        indices = [i for i, row in enumerate(image_metrics) if row["domain"] == domain]
        ordered = sorted(
            indices,
            key=lambda i: (
                float(kernel_rows[int(image_metrics[i]["kernel_id"].split("_")[-1])]["declared_length_px"]),
                str(image_metrics[i]["scene"]),
                str(image_metrics[i]["sample_id"]),
            ),
        )
        positions = [0, len(ordered) // 5, 2 * len(ordered) // 5, 3 * len(ordered) // 5, 4 * len(ordered) // 5, len(ordered) - 1]
        selected_indices.extend(ordered[position] for position in positions)
    panel = (256, 256)
    header = 38
    sheet = Image.new("RGB", (panel[0] * 4, (panel[1] + header) * len(selected_indices)), "white")
    draw = ImageDraw.Draw(sheet)
    contact_rows: list[dict[str, object]] = []
    for row_number, metric_index in enumerate(selected_indices):
        metric = image_metrics[metric_index]
        with Image.open(str(metric["source_image"])) as handle:
            sharp = handle.convert("RGB")
        with Image.open(str(metric["generated_image"])) as handle:
            blurred = handle.convert("RGB")
        with Image.open(str(metric["mask"])) as handle:
            mask = np.asarray(handle.convert("L"), dtype=np.uint8)
        coloured = mask_rgb(mask)
        overlay = Image.blend(blurred, coloured, 0.42)
        y = row_number * (panel[1] + header)
        kernel_id = str(metric["kernel_id"])
        kernel_row = kernel_rows[int(kernel_id.split("_")[-1])]
        label = (
            f"{metric['domain']} {metric['scene']} {kernel_id} "
            f"L={float(kernel_row['declared_length_px']):.0f}px "
            f"grad={float(metric['gradient_ratio']):.3f}"
        )
        draw.text((5, y + 11), label, fill=(0, 0, 0))
        for column, image in enumerate((sharp, blurred, coloured, overlay)):
            sheet.paste(
                image.resize(panel, Image.Resampling.BILINEAR if column < 2 else Image.Resampling.NEAREST),
                (column * panel[0], y + header),
            )
        contact_rows.append(
            {
                "source_sample_id": metric["sample_id"],
                "domain": metric["domain"],
                "scene": metric["scene"],
                "kernel_id": kernel_id,
                "declared_length_px": kernel_row["declared_length_px"],
                "trajectory": kernel_row["trajectory"],
                "gradient_ratio": metric["gradient_ratio"],
                "source_image_sha256": metric["source_image_sha256"],
                "generated_image_sha256": metric["generated_image_sha256"],
                "mask_sha256": metric["mask_sha256"],
            }
        )
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(contact_path, optimize=False)
    contact_receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "columns": ["source_sharp", "generated_motion_blur", "common_mask", "blur_mask_overlay"],
        "selection": "six deterministic kernel-length strata per dryland/paddy source",
        "rows": contact_rows,
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    contact_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    contact_receipt_path.write_text(
        json.dumps(contact_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    release_inventory = tree_inventory(release_dir)
    audit = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": DATASET_ID,
        "frozen_config": str(config_path),
        "frozen_config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
        "asset_pack": str(pack_dir),
        "asset_pack_manifest": str(pack_path),
        "asset_pack_manifest_sha256": sha256(pack_path),
        "kernel_inventory_sha256": pack["kernel_inventory_sha256"],
        "release": str(release_dir),
        "release_inventory": release_inventory,
        "release_inventory_sha256": canonical_sha256(release_inventory),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "counts": {
            "samples": len(output_records),
            "train": len(train),
            "external_calibration": len(calibration),
            "source_domains": dict(Counter(str(row["domain"]) for row in image_metrics)),
            "target_crop_ids": dict(Counter(str(row.target_crop_id) for row in output_records)),
            "train_groups": len(train_groups),
            "calibration_groups": len(calibration_groups),
            "group_overlap": group_overlap,
            "kernel_usage": dict(sorted(kernel_usage.items())),
        },
        "kernel_metrics": {
            "rows": kernel_rows,
            "maximum_centroid_error_px": max(float(row["centroid_error_px"]) for row in kernel_rows),
        },
        "image_metrics": {
            "mean_absolute_change": quantiles(mean_changes),
            "maximum_channel_mean_shift": quantiles(channel_shifts),
            "gradient_ratio": quantiles(gradient_ratios),
            "rows": image_metrics,
        },
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "contact_sheet_receipt": str(contact_receipt_path),
        "contact_sheet_receipt_sha256": sha256(contact_receipt_path),
        "capacity": {
            "free_bytes_before": free_before,
            "expected_output_bytes": expected_bytes,
            "minimum_free_bytes_after": minimum_after,
            "free_bytes_after": shutil.disk_usage(data_root).free,
        },
        "quality_gate_checks": checks,
        "all_automatic_quality_gates_passed": all(checks.values()),
        "manual_visual_review_required": True,
        "manual_visual_review_passed": None,
        "real_deblurweedseg_training_or_asset_exposure": 0,
        "external_test_used": False,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "audit": str(audit_path),
        "all_automatic_quality_gates_passed": audit["all_automatic_quality_gates_passed"],
        "checks": checks,
        "manifest": str(manifest_path),
        "manifest_sha256": audit["manifest_sha256"],
        "contact_sheet": str(contact_path),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
