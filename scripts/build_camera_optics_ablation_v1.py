#!/usr/bin/env python3
"""Build a paired CropCraft camera/optics diagnostic set.

The study reuses the eight untouched V11 test geometries.  Each rendered
condition changes one acquisition variable while preserving the ``field``
subtree byte-for-byte.  Defocus and motion variants are deterministic sensor
degradations of the 512 px reference frame.  This is a diagnostic camera
study, not training data and not a replacement for a real camera bench.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import yaml
from PIL import Image, ImageFilter
from scipy import ndimage

from agri_seg.constants import MANIFEST_COLUMNS
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
SOURCE_ROOT = (
    DATA_ROOT
    / "synthetic/cropcraft/field_robustness_pilot_v11_r2/roles/test"
)
SOURCE_MANIFEST = (
    DATA_ROOT
    / "processed/manifests/cropcraft_field_robustness_pilot_v11_r2q.csv"
)
RELEASE = "camera_optics_ablation_v1"
RAW_ROOT = DATA_ROOT / "synthetic/cropcraft" / RELEASE
PROCESSED_ROOT = DATA_ROOT / "processed" / RELEASE
MANIFEST = DATA_ROOT / "processed/manifests" / f"{RELEASE}.csv"
ASSET_PACK = (
    DATA_ROOT
    / "raw/synthetic_assets/cropcraft_field_robustness_v10_r1"
)
SCENE_PATCH = PROJECT_ROOT / "patches/cropcraft/0006-field-robustness-surface-lighting.patch"

RENDER_VARIANTS: tuple[tuple[str, Mapping[str, Any]], ...] = (
    ("resolution_256", {"resolution": 256}),
    ("resolution_384", {"resolution": 384}),
    ("resolution_768", {"resolution": 768}),
    ("resolution_1024", {"resolution": 1024}),
    ("zoom_1p33", {"optical_zoom": 1.33, "resolution": 512}),
    ("zoom_1p67", {"optical_zoom": 1.67, "resolution": 512}),
    (
        "dim_no_led",
        {
            "resolution": 512,
            "environment_strength": 0.30,
            "sun_energy": 0.08,
            "artificial_light_energy": 0.0,
        },
    ),
    (
        "dim_led_energy30",
        {
            "resolution": 512,
            "environment_strength": 0.30,
            "sun_energy": 0.08,
            "artificial_light_energy": 30.0,
        },
    ),
    (
        "dim_led_energy60",
        {
            "resolution": 512,
            "environment_strength": 0.30,
            "sun_energy": 0.08,
            "artificial_light_energy": 60.0,
        },
    ),
    (
        "dim_led_energy120",
        {
            "resolution": 512,
            "environment_strength": 0.30,
            "sun_energy": 0.08,
            "artificial_light_energy": 120.0,
        },
    ),
)

DERIVED_VARIANTS: tuple[tuple[str, Mapping[str, Any]], ...] = (
    ("defocus_sigma1p5", {"gaussian_sigma_px": 1.5}),
    ("defocus_sigma3p0", {"gaussian_sigma_px": 3.0}),
    ("motion_blur_7px", {"motion_blur_px": 7}),
    # These three variants separate captured detail from network raster size.
    # No new scene information is introduced by either upscale condition.
    ("digital_input_256", {"resize_to": 256}),
    ("detail_loss_256_up512", {"downsample_to": 256, "resize_to": 512}),
    ("digital_upscale_1024", {"resize_to": 1024}),
)

ALL_VARIANTS = (
    "reference_512",
    *(name for name, _ in RENDER_VARIANTS),
    *(name for name, _ in DERIVED_VARIANTS),
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def zoomed_fov_deg(fov_deg: float, optical_zoom: float) -> float:
    """Return a narrower FOV with image-plane scale multiplied by zoom."""
    if not 0.0 < fov_deg < 180.0 or optical_zoom < 1.0:
        raise ValueError("Invalid FOV or optical zoom")
    half = math.radians(fov_deg) / 2.0
    return math.degrees(2.0 * math.atan(math.tan(half) / optical_zoom))


def _scene_configs() -> list[Path]:
    configs = sorted((SOURCE_ROOT / "scene_configs").glob("scene_*.yaml"))
    if len(configs) != 8:
        raise RuntimeError(f"Expected eight frozen test scenes, got {len(configs)}")
    return configs


def _variant_config(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    config = deepcopy(dict(base))
    render = config["render"]
    resolution = int(patch.get("resolution", 512))
    render["resolution_x"] = resolution
    render["resolution_y"] = resolution
    if "optical_zoom" in patch:
        render["camera"]["fov_deg"] = round(
            zoomed_fov_deg(
                float(render["camera"]["fov_deg"]),
                float(patch["optical_zoom"]),
            ),
            6,
        )
    surface = config["agri_asset_profile"]["surface_parameters"]
    for key in (
        "environment_strength",
        "sun_energy",
        "artificial_light_energy",
    ):
        if key in patch:
            surface[key] = float(patch[key])
    return config


def prepare_configs() -> list[dict[str, str]]:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    jobs: list[dict[str, str]] = []
    field_hashes: set[str] = set()
    for source_path in _scene_configs():
        base = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        field_hash = _canonical_hash(base["field"])
        field_hashes.add(field_hash)
        for variant, patch in RENDER_VARIANTS:
            config = _variant_config(base, patch)
            if _canonical_hash(config["field"]) != field_hash:
                raise RuntimeError(f"Field geometry changed for {variant}/{source_path.name}")
            config_dir = RAW_ROOT / "scene_configs" / variant
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / source_path.name
            serialized = yaml.safe_dump(config, sort_keys=False)
            if config_path.exists() and config_path.read_text(encoding="utf-8") != serialized:
                raise RuntimeError(f"Refusing to overwrite incompatible {config_path}")
            if not config_path.exists():
                config_path.write_text(serialized, encoding="utf-8")
            scene = source_path.stem
            output = RAW_ROOT / "scenes" / variant / scene
            jobs.append(
                {
                    "variant": variant,
                    "scene": scene,
                    "config": str(config_path),
                    "output": str(output),
                    "field_hash": field_hash,
                }
            )
    if len(field_hashes) != 8:
        raise RuntimeError("Frozen scene geometries are unexpectedly duplicated")
    return jobs


def _render_job(job: Mapping[str, str]) -> str:
    output = Path(job["output"])
    receipt = output / "generation_receipt.json"
    if receipt.is_file():
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        expected_config = _sha256(Path(job["config"]))
        if (
            payload.get("config_sha256") != expected_config
            or payload.get("scene_patch_sha256") != _sha256(SCENE_PATCH)
        ):
            raise RuntimeError(f"Incompatible existing render: {output}")
        return f"reuse {job['variant']}/{job['scene']}"
    if output.exists():
        raise RuntimeError(f"Incomplete output exists; refusing overwrite: {output}")
    log_dir = RAW_ROOT / "launcher_logs" / job["variant"]
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(PROJECT_ROOT / ".venv/bin/python"),
        str(PROJECT_ROOT / "scripts/run_cropcraft.py"),
        job["config"],
        "--output",
        str(output),
        "--asset-pack",
        str(ASSET_PACK),
        "--ground-material-id",
        str(
            yaml.safe_load(Path(job["config"]).read_text(encoding="utf-8"))[
                "agri_asset_profile"
            ]["ground_material_id"]
        ),
        "--scene-patch",
        str(SCENE_PATCH),
    ]
    with (log_dir / f"{job['scene']}.stdout.log").open("wb") as stdout, (
        log_dir / f"{job['scene']}.stderr.log"
    ).open("wb") as stderr:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"CropCraft failed ({completed.returncode}) for "
            f"{job['variant']}/{job['scene']}; see {log_dir}"
        )
    return f"render {job['variant']}/{job['scene']}"


def render(jobs: Iterable[Mapping[str, str]], workers: int) -> None:
    selected = list(jobs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(_render_job, job): job for job in selected}
        for index, future in enumerate(as_completed(futures), start=1):
            print(f"[{index}/{len(selected)}] {future.result()}", flush=True)


def _source_records() -> dict[tuple[str, str], SampleRecord]:
    records: dict[tuple[str, str], SampleRecord] = {}
    for record in read_manifest(SOURCE_MANIFEST):
        if record.split != "test":
            continue
        # sample IDs end in scene/frame, while paths are stable and explicit.
        parts = Path(record.image_path).parts
        scene = next(part for part in parts if part.startswith("scene_"))
        frame = Path(record.image_path).stem
        records[(scene, frame)] = record
    if len(records) != 16:
        raise RuntimeError(f"Expected 16 source test records, got {len(records)}")
    return records


def _common_mask(rgb_mask_path: Path, destination: Path) -> dict[str, int]:
    with Image.open(rgb_mask_path) as handle:
        rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    common = np.full(rgb.shape[:2], 255, dtype=np.uint8)
    colors = {
        0: np.array([0, 0, 0], dtype=np.uint8),
        1: np.array([0, 255, 0], dtype=np.uint8),
        2: np.array([255, 0, 0], dtype=np.uint8),
    }
    counts: dict[str, int] = {}
    for label, color in colors.items():
        selection = np.all(rgb == color, axis=2)
        common[selection] = label
        counts[str(label)] = int(selection.sum())
    if np.any(common == 255):
        raise RuntimeError(f"Unexpected palette in {rgb_mask_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(common).save(destination, optimize=True)
    return counts


def _motion_blur(image: Image.Image, pixels: int) -> Image.Image:
    if pixels < 3 or pixels % 2 == 0:
        raise ValueError("Motion kernel must be odd and >=3")
    array = np.asarray(image.convert("RGB"), dtype=np.float32)
    blurred = ndimage.uniform_filter1d(array, size=pixels, axis=1, mode="reflect")
    return Image.fromarray(np.clip(np.rint(blurred), 0, 255).astype(np.uint8))


def _derive_image(source: Path, destination: Path, patch: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as handle:
        image = handle.convert("RGB")
        if "gaussian_sigma_px" in patch:
            result = image.filter(
                ImageFilter.GaussianBlur(radius=float(patch["gaussian_sigma_px"]))
            )
        elif "motion_blur_px" in patch:
            result = _motion_blur(image, int(patch["motion_blur_px"]))
        elif "resize_to" in patch:
            downsample_to = patch.get("downsample_to")
            if downsample_to is not None:
                size = int(downsample_to)
                image = image.resize((size, size), resample=Image.Resampling.LANCZOS)
            size = int(patch["resize_to"])
            resample = (
                Image.Resampling.LANCZOS
                if size < max(image.size)
                else Image.Resampling.BILINEAR
            )
            result = image.resize((size, size), resample=resample)
        else:
            raise ValueError(f"Unknown derived patch: {patch}")
        result.save(destination, quality=95, subsampling=0, optimize=True)


def _derive_rgb_mask(source: Path, destination: Path, size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as handle:
        mask = handle.convert("RGB").resize(
            (size, size), resample=Image.Resampling.NEAREST
        )
    mask.save(destination, optimize=True)


def _relative(path: Path) -> str:
    return path.resolve().relative_to(DATA_ROOT.resolve()).as_posix()


def build_manifest(jobs: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    records = _source_records()
    rows: list[SampleRecord] = []
    inventory: list[dict[str, Any]] = []
    variant_class_counts = {
        variant: {"0": 0, "1": 0, "2": 0} for variant in ALL_VARIANTS
    }
    job_lookup = {(job["variant"], job["scene"]): job for job in jobs}
    variant_metadata = {
        "reference_512": {"source": "frozen_v11_r2_test_render", "resolution": 512},
        **{name: dict(patch) for name, patch in RENDER_VARIANTS},
        **{name: dict(patch) for name, patch in DERIVED_VARIANTS},
    }

    for (scene, frame), source_record in sorted(records.items()):
        source_image = DATA_ROOT / source_record.image_path
        source_rgb_mask = SOURCE_ROOT / "scenes" / scene / "render/masks" / f"{frame}.png"
        for variant in ALL_VARIANTS:
            dataset_id = f"{RELEASE}_{variant}"
            if variant == "reference_512":
                image_path = source_image
                rgb_mask_path = source_rgb_mask
            elif variant in dict(DERIVED_VARIANTS):
                patch = dict(DERIVED_VARIANTS)[variant]
                image_path = PROCESSED_ROOT / "images" / variant / scene / f"{frame}.jpg"
                if not image_path.is_file():
                    _derive_image(source_image, image_path, patch)
                final_size = int(patch.get("resize_to", 512))
                if final_size == 512:
                    rgb_mask_path = source_rgb_mask
                else:
                    rgb_mask_path = (
                        PROCESSED_ROOT
                        / "rgb_masks"
                        / variant
                        / scene
                        / f"{frame}.png"
                    )
                    if not rgb_mask_path.is_file():
                        _derive_rgb_mask(source_rgb_mask, rgb_mask_path, final_size)
            else:
                output = Path(job_lookup[(variant, scene)]["output"])
                image_path = output / "render/images" / f"{frame}.jpg"
                rgb_mask_path = output / "render/masks" / f"{frame}.png"
            if not image_path.is_file() or not rgb_mask_path.is_file():
                raise FileNotFoundError(f"Missing pair: {image_path}, {rgb_mask_path}")
            mask_path = PROCESSED_ROOT / "common_masks" / variant / scene / f"{frame}.png"
            counts = _common_mask(rgb_mask_path, mask_path)
            for label, count in counts.items():
                variant_class_counts[variant][label] += count
            rows.append(
                SampleRecord(
                    sample_id=f"{dataset_id}:{scene}:{frame}",
                    image_path=_relative(image_path),
                    mask_path=_relative(mask_path),
                    split="test",
                    dataset_id=dataset_id,
                    field_id=f"paired_{scene}",
                    session_id=source_record.session_id,
                    capture_date="synthetic_paired_diagnostic",
                    platform="synthetic_robot_camera_bench",
                    sensor=f"cropcraft_cycles_{variant}",
                    target_crop_id=source_record.target_crop_id,
                    crop_species=source_record.crop_species,
                    weed_species_optional=source_record.weed_species_optional,
                    growth_stage=source_record.growth_stage,
                    annotation_exhaustive=True,
                    license_status=source_record.license_status,
                    commercial_allowed=source_record.commercial_allowed,
                )
            )
            inventory.append(
                {
                    "variant": variant,
                    "scene": scene,
                    "frame": frame,
                    "image": _relative(image_path),
                    "image_sha256": _sha256(image_path),
                    "mask": _relative(mask_path),
                    "mask_sha256": _sha256(mask_path),
                    "class_pixels": counts,
                }
            )

    empty_variants = [
        variant
        for variant, counts in variant_class_counts.items()
        if counts["1"] == 0 or counts["2"] == 0
    ]
    if empty_variants:
        raise RuntimeError(f"Crop/weed-free diagnostic variants: {empty_variants}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for record in rows:
            writer.writerow(asdict(record))
    temporary.replace(MANIFEST)
    reread = read_manifest(MANIFEST)
    expected = 16 * len(ALL_VARIANTS)
    if len(reread) != expected:
        raise RuntimeError(f"Manifest count mismatch: {len(reread)} != {expected}")

    field_hashes_by_scene: dict[str, set[str]] = {}
    for job in jobs:
        field_hashes_by_scene.setdefault(job["scene"], set()).add(job["field_hash"])
    if any(len(values) != 1 for values in field_hashes_by_scene.values()):
        raise RuntimeError("Paired field hashes are inconsistent")
    receipt = {
        "schema_version": 1,
        "release": RELEASE,
        "role": "paired_synthetic_camera_diagnostic_only",
        "not_training_data": True,
        "real_camera_validation_required": True,
        "source_manifest": str(SOURCE_MANIFEST),
        "source_manifest_sha256": manifest_sha256(SOURCE_MANIFEST),
        "scene_patch": str(SCENE_PATCH),
        "scene_patch_sha256": _sha256(SCENE_PATCH),
        "manifest": str(MANIFEST),
        "manifest_sha256": manifest_sha256(MANIFEST),
        "variants": variant_metadata,
        "paired_scenes": 8,
        "frames_per_variant": 16,
        "class_pixels_by_variant": variant_class_counts,
        "records": len(rows),
        "field_geometry_hashes": {
            scene: next(iter(values))
            for scene, values in sorted(field_hashes_by_scene.items())
        },
        "pairing_claim": (
            "Every rendered condition preserves the complete CropCraft field subtree. "
            "Zoom changes framing/FOV; resolution and lighting preserve framing. "
            "Digital-raster variants are deterministic transforms of reference_512."
        ),
        "illumination_units_note": (
            "artificial_light_energy is the simulator/Blender control value, not "
            "a calibrated electrical wattage or measured field lux"
        ),
        "inventory": inventory,
    }
    receipt_path = PROCESSED_ROOT / "build_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("all", "prepare", "render", "manifest"),
        default="all",
    )
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    jobs = prepare_configs()
    if args.stage in {"all", "render"}:
        render(jobs, args.workers)
    if args.stage in {"all", "manifest"}:
        receipt = build_manifest(jobs)
        print(json.dumps({key: receipt[key] for key in ("manifest", "records", "variants")}, indent=2))
    elif args.stage == "prepare":
        print(json.dumps({"jobs": len(jobs), "root": str(RAW_ROOT)}, indent=2))


if __name__ == "__main__":
    main()
