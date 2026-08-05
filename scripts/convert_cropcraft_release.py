#!/usr/bin/env python3
"""Convert a validated CropCraft release to the common 0/1/2/255 ontology."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import BACKGROUND, CROP, WEED
from agri_seg.manifest import SampleRecord, write_manifest
from agri_seg.prepare import _save_common_mask


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_object(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset-id", default="cropcraft_stock_pilot_v1")
    parser.add_argument(
        "--metadata-config",
        help=(
            "Optional study config supplying manifest_metadata. Generation "
            "fields must match the immutable study copy in the release."
        ),
    )
    args = parser.parse_args()

    release_root = Path(args.release).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    receipt_path = release_root / "release_receipt.json"
    release_receipt = load_object(receipt_path)
    if not release_receipt.get("all_quality_gates_passed"):
        raise RuntimeError("CropCraft release quality gates did not pass")
    study_path = release_root / "study.input.yaml"
    study = load_object(study_path)
    if release_receipt.get("copied_study_sha256") != sha256(study_path):
        raise RuntimeError("Immutable release study hash does not match receipt")
    train_scenes = int(study["train_scenes"])
    validation_scenes = int(study["validation_scenes"])
    scene_count = int(study["scene_count"])
    if train_scenes + validation_scenes != scene_count:
        raise ValueError("Study scene split does not cover the release")
    metadata_config_path: Path | None = None
    metadata = study.get("manifest_metadata", {})
    if args.metadata_config:
        metadata_config_path = Path(args.metadata_config).expanduser().resolve()
        metadata_config = load_object(metadata_config_path)
        locked_fields = (
            "release",
            "asset_pack_id",
            "crop_bed_name",
            "crop_plant_type",
            "scene_count",
            "frames_per_scene",
            "train_scenes",
            "validation_scenes",
        )
        mismatches = [
            field
            for field in locked_fields
            if metadata_config.get(field) != study.get(field)
        ]
        if mismatches:
            raise ValueError(
                "Metadata config changes immutable generation fields: "
                + ", ".join(mismatches)
            )
        metadata = metadata_config.get("manifest_metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("manifest_metadata must be a mapping")
    crop_bed_name = str(study.get("crop_bed_name", "maize_rows"))
    expected_crop_type = str(study.get("crop_plant_type", "maize"))
    target_crop_id = int(metadata.get("target_crop_id", 3))
    crop_species = str(metadata.get("crop_species", "Zea mays stock asset"))
    weed_species = str(
        metadata.get(
            "weed_species_optional",
            "Portulaca;Polygonum;Taraxacum stock assets",
        )
    )
    growth_stage_prefix = str(
        metadata.get("growth_stage_prefix", "stock_asset_scaled_height")
    )
    platform = str(metadata.get("platform", "blender_4_5_cycles"))
    sensor = str(metadata.get("sensor", "synthetic_pinhole_rgb"))
    annotation_exhaustive = bool(metadata.get("annotation_exhaustive", True))
    license_status = str(
        metadata.get(
            "license_status",
            "Apache-2.0-repository;bundled-assets-not-itemized",
        )
    )
    commercial_allowed = bool(metadata.get("commercial_allowed", False))
    expected_asset_pack_id = study.get("asset_pack_id")
    if expected_asset_pack_id is not None:
        receipt_asset_pack = release_receipt.get("asset_pack", {})
        if not isinstance(receipt_asset_pack, dict) or receipt_asset_pack.get(
            "pack_id"
        ) != expected_asset_pack_id:
            raise RuntimeError("Release asset-pack receipt does not match study")
        visual_receipt_path = release_root / "visual_review_receipt.json"
        visual_receipt = load_object(visual_receipt_path)
        if visual_receipt.get("passed") is not True:
            raise RuntimeError("Custom-asset release lacks a passed visual review")
        if visual_receipt.get("release_receipt_sha256") != sha256(receipt_path):
            raise RuntimeError("Visual-review receipt does not lock this release")

    normalized_root = (
        data_root / f"processed/{args.dataset_id}/common_masks"
    )
    records: list[SampleRecord] = []
    class_pixels = {"background": 0, "crop": 0, "weed": 0}
    scene_receipt_hashes: dict[str, str] = {}
    for scene_index in range(scene_count):
        scene_name = f"scene_{scene_index:04d}"
        scene_root = release_root / "scenes" / scene_name
        scene_receipt_path = scene_root / "generation_receipt.json"
        scene_receipt = load_object(scene_receipt_path)
        if int(scene_receipt["validation"]["validated_pairs"]) != int(
            study["frames_per_scene"]
        ):
            raise RuntimeError(f"Incomplete scene receipt: {scene_name}")
        scene_receipt_hashes[scene_name] = sha256(scene_receipt_path)
        config_path = release_root / "scene_configs" / f"{scene_name}.yaml"
        config = load_object(config_path)
        if sha256(config_path) != scene_receipt["config_sha256"]:
            raise RuntimeError(f"Scene config hash mismatch: {scene_name}")
        beds = config["field"]["beds"]
        if crop_bed_name not in beds:
            raise ValueError(
                f"Configured crop bed {crop_bed_name!r} is missing: {scene_name}"
            )
        crop_type = str(beds[crop_bed_name]["plant_type"])
        if crop_type != expected_crop_type:
            raise ValueError(f"Unsupported pilot crop type: {crop_type}")
        crop_height = float(beds[crop_bed_name]["plant_height"])
        split = "train" if scene_index < train_scenes else "val"
        image_root = scene_root / "render/images"
        mask_root = scene_root / "render/masks"
        images = {path.stem: path for path in sorted(image_root.glob("*.jpg"))}
        masks = {path.stem: path for path in sorted(mask_root.glob("*.png"))}
        if set(images) != set(masks) or len(images) != int(
            study["frames_per_scene"]
        ):
            raise RuntimeError(f"RGB/mask pairing mismatch: {scene_name}")
        for stem in sorted(images):
            with Image.open(masks[stem]) as mask_handle:
                raw = np.asarray(mask_handle.convert("RGB"), dtype=np.uint8)
            common = np.full(raw.shape[:2], 255, dtype=np.uint8)
            color_mapping = {
                (0, 0, 0): BACKGROUND,
                (0, 255, 0): CROP,
                (255, 0, 0): WEED,
            }
            known = np.zeros(raw.shape[:2], dtype=bool)
            for color, label in color_mapping.items():
                selected = np.all(raw == color, axis=-1)
                common[selected] = label
                known |= selected
            if not np.all(known):
                unexpected = np.unique(raw[~known].reshape(-1, 3), axis=0)
                raise ValueError(
                    f"Unexpected mask colors in {masks[stem]}: "
                    f"{unexpected[:10].tolist()}"
                )
            for name, label in (
                ("background", BACKGROUND),
                ("crop", CROP),
                ("weed", WEED),
            ):
                class_pixels[name] += int((common == label).sum())
            common_path = normalized_root / split / scene_name / f"{stem}.png"
            _save_common_mask(common, common_path)
            records.append(
                SampleRecord(
                    sample_id=f"{args.dataset_id}:{scene_name}:{stem}",
                    image_path=relative(images[stem], data_root),
                    mask_path=relative(common_path, data_root),
                    split=split,
                    dataset_id=args.dataset_id,
                    field_id=scene_name,
                    session_id=f"seed_{int(config['field']['random_seed'])}",
                    capture_date="synthetic",
                    platform=platform,
                    sensor=sensor,
                    target_crop_id=target_crop_id,
                    crop_species=crop_species,
                    weed_species_optional=weed_species,
                    growth_stage=f"{growth_stage_prefix}_{crop_height:.3f}m",
                    annotation_exhaustive=annotation_exhaustive,
                    license_status=license_status,
                    commercial_allowed=commercial_allowed,
                )
            )

    write_manifest(records, output)
    report = {
        "schema_version": 1,
        "dataset_id": args.dataset_id,
        "release": str(release_root),
        "release_receipt_sha256": sha256(receipt_path),
        "study_sha256": sha256(release_root / "study.input.yaml"),
        "metadata_config": (
            {
                "path": str(metadata_config_path),
                "sha256": sha256(metadata_config_path),
            }
            if metadata_config_path is not None
            else None
        ),
        "scene_receipt_sha256": scene_receipt_hashes,
        "samples": len(records),
        "split_counts": {
            split: sum(record.split == split for record in records)
            for split in ("train", "val")
        },
        "class_pixels": class_pixels,
        "ontology": {"background": 0, "target_crop": 1, "weed": 2},
        "manifest_metadata": {
            "target_crop_id": target_crop_id,
            "crop_species": crop_species,
            "weed_species_optional": weed_species,
            "platform": platform,
            "sensor": sensor,
            "license_status": license_status,
            "commercial_allowed": commercial_allowed,
        },
        "scene_disjoint_split": {
            "passed": True,
            "train_scenes": train_scenes,
            "validation_scenes": validation_scenes,
            "overlap": [],
        },
        "asset_pack": release_receipt.get("asset_pack"),
    }
    report_path = output.with_name(f"{output.stem}_conversion.json")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
