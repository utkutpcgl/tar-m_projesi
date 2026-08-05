#!/usr/bin/env python3
"""Convert the frozen DeBlurWeedSeg publisher holdout into paired stress data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    write_manifest,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def safe_archive_summary(path: Path) -> dict[str, int]:
    bad_paths: list[str] = []
    links: list[str] = []
    with ZipFile(path) as archive:
        members = archive.infolist()
        for member in members:
            candidate = PurePosixPath(member.filename)
            if (
                candidate.is_absolute()
                or ".." in candidate.parts
                or "\\" in member.filename
            ):
                bad_paths.append(member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                links.append(member.filename)
        if bad_paths or links:
            raise ValueError(
                f"Unsafe archive {path}: bad_paths={bad_paths[:5]}, links={links[:5]}"
            )
        return {
            "members": len(members),
            "uncompressed_bytes": sum(member.file_size for member in members),
            "bad_paths": len(bad_paths),
            "symlinks": len(links),
        }


def read_split(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["filename"]:
            raise ValueError(f"Unexpected split columns in {path}: {reader.fieldnames}")
        values = [str(row["filename"]) for row in reader]
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate publisher split id in {path}")
    return values


def sequence_sha256(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode("utf-8")).hexdigest()


def parse_palette(document: dict[str, Any]) -> dict[tuple[int, int, int], int]:
    palette: dict[tuple[int, int, int], int] = {}
    for raw, common in document["publisher_structure"][
        "source_palette_rgb_to_common"
    ].items():
        colour = tuple(int(value) for value in str(raw).split(","))
        if len(colour) != 3:
            raise ValueError(f"Invalid RGB palette key: {raw}")
        palette[colour] = int(common)
    require_equal("common palette", set(palette.values()), {BACKGROUND, CROP, WEED})
    return palette


def decode_mask(
    rgb: np.ndarray, palette: dict[tuple[int, int, int], int], source: str
) -> tuple[np.ndarray, Counter[int]]:
    output = np.full(rgb.shape[:2], IGNORE, dtype=np.uint8)
    for colour, common in palette.items():
        output[np.all(rgb == np.asarray(colour, dtype=np.uint8), axis=2)] = common
    unexpected = np.unique(rgb[output == IGNORE].reshape(-1, 3), axis=0)
    if unexpected.size:
        raise ValueError(f"Unexpected mask colours in {source}: {unexpected[:10].tolist()}")
    counts = Counter({value: int(np.count_nonzero(output == value)) for value in palette.values()})
    return output, counts


def convert(gate_path: Path) -> tuple[Path, Path]:
    gate_path = gate_path.expanduser().resolve()
    gate = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError("Gate config must be a mapping")
    data_root = Path("data").resolve()
    source = gate["source"]
    outputs = gate["outputs"]
    structure = gate["publisher_structure"]

    archive = data_root / str(source["archive_path"])
    inner_archive = data_root / str(source["inner_data_archive_path"])
    repository = data_root / str(source["extracted_root"])
    for path in (archive, inner_archive, repository):
        if not path.exists():
            raise FileNotFoundError(path)
    require_equal("archive size", archive.stat().st_size, int(source["archive_size_bytes"]))
    require_equal("archive SHA-256", sha256(archive), str(source["archive_sha256"]))
    require_equal(
        "inner archive size",
        inner_archive.stat().st_size,
        int(source["inner_data_archive_size_bytes"]),
    )
    require_equal(
        "inner archive SHA-256",
        sha256(inner_archive),
        str(source["inner_data_archive_sha256"]),
    )
    archive_safety = {
        "outer": safe_archive_summary(archive),
        "inner": safe_archive_summary(inner_archive),
    }

    split_values: dict[str, list[str]] = {}
    for split, expected_count in structure["publisher_split_counts"].items():
        split_path = repository / "splits" / f"{split}.csv"
        require_equal(
            f"{split} split SHA-256",
            sha256(split_path),
            str(structure["split_csv_sha256"][split]),
        )
        values = read_split(split_path)
        require_equal(f"{split} split count", len(values), int(expected_count))
        require_equal(
            f"{split} id sequence SHA-256",
            sequence_sha256(values),
            str(structure["split_id_sequence_sha256"][split]),
        )
        split_values[split] = values
    all_ids = [value for values in split_values.values() for value in values]
    require_equal("publisher split union count", len(all_ids), int(structure["composite_pairs"]))
    require_equal("publisher split union uniqueness", len(set(all_ids)), len(all_ids))

    source_panels = sorted((repository / "gt").glob("*.png"))
    require_equal("source panel count", len(source_panels), int(structure["composite_pairs"]))
    require_equal("source panel ids", {path.stem for path in source_panels}, set(all_ids))
    palette = parse_palette(gate)
    boxes = {
        name: tuple(int(value) for value in box)
        for name, box in structure["crop_boxes_xyxy"].items()
    }
    expected_size = (
        int(structure["composite_width"]),
        int(structure["composite_height"]),
    )
    expected_panel_shape = (
        int(structure["panel_height"]),
        int(structure["panel_width"]),
        3,
    )
    source_palette_counts: dict[str, Counter[str]] = {
        "sharp": Counter(),
        "motion_blur": Counter(),
    }
    rgba_panels = 0
    for path in source_panels:
        with Image.open(path) as image:
            require_equal(f"composite dimensions {path.name}", image.size, expected_size)
            if image.mode == "RGBA":
                rgba_panels += 1
                alpha = np.asarray(image.getchannel("A"))
                if not np.all(alpha == 255):
                    raise ValueError(f"Non-opaque alpha in {path}")
            rgb_image = image.convert("RGB")
            for modality, panel_name in (
                ("sharp", "sharp_mask"),
                ("motion_blur", "blur_mask"),
            ):
                panel = np.asarray(rgb_image.crop(boxes[panel_name]), dtype=np.uint8)
                require_equal(f"panel shape {path.name}/{panel_name}", panel.shape, expected_panel_shape)
                _, counts = decode_mask(panel, palette, f"{path.name}/{panel_name}")
                source_palette_counts[modality].update(
                    {str(common): count for common, count in counts.items()}
                )

    included_split = str(gate["role_policy"]["included_publisher_split"])
    included_ids = split_values[included_split]
    require_equal(
        "included pair count",
        len(included_ids),
        int(gate["quality_gate"]["require_paired_output_count"]),
    )
    images_root = data_root / str(outputs["images_root"])
    masks_root = data_root / str(outputs["masks_root"])
    records: list[SampleRecord] = []
    class_pixels: dict[str, Counter[int]] = {
        "sharp": Counter(),
        "motion_blur": Counter(),
    }
    expected_images: set[Path] = set()
    expected_masks: set[Path] = set()
    capture = gate["capture"]
    ontology = gate["ontology"]
    output_role = str(gate["role_policy"]["output_role"])
    modality_panels = {
        "sharp": ("sharp_rgb", "sharp_mask"),
        "motion_blur": ("blur_rgb", "blur_mask"),
    }

    for stem in included_ids:
        source_panel = repository / "gt" / f"{stem}.png"
        with Image.open(source_panel) as image:
            rgb_image = image.convert("RGB")
            for modality, (rgb_name, mask_name) in modality_panels.items():
                rgb = rgb_image.crop(boxes[rgb_name])
                raw_mask = np.asarray(rgb_image.crop(boxes[mask_name]), dtype=np.uint8)
                common_mask, counts = decode_mask(
                    raw_mask, palette, f"{source_panel.name}/{mask_name}"
                )
                class_pixels[modality].update(counts)
                image_path = images_root / modality / f"{stem}.png"
                mask_path = masks_root / modality / f"{stem}.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                rgb.save(image_path, format="PNG", optimize=False)
                Image.fromarray(common_mask).save(mask_path, format="PNG", optimize=False)
                expected_images.add(image_path.resolve())
                expected_masks.add(mask_path.resolve())
                records.append(
                    SampleRecord(
                        sample_id=f"deblurweedseg:{stem}:{modality}",
                        image_path=relative(image_path, data_root),
                        mask_path=relative(mask_path, data_root),
                        split=output_role,
                        dataset_id=str(gate["dataset_id"]),
                        field_id=str(capture["field_id"]),
                        session_id=str(capture["session_id"]),
                        capture_date=str(capture["capture_date"]),
                        platform=str(capture["platform"]),
                        sensor=str(capture["sensor"]),
                        target_crop_id=int(ontology["target_crop_id"]),
                        crop_species=str(ontology["crop_species"]),
                        weed_species_optional=str(ontology["weed_species"]),
                        growth_stage=str(capture["growth_stage"]),
                        annotation_exhaustive=bool(ontology["annotation_exhaustive"]),
                        license_status=str(source["license"]),
                        commercial_allowed=bool(source["commercial_allowed"]),
                    )
                )

    actual_images = {path.resolve() for path in images_root.rglob("*.png")}
    actual_masks = {path.resolve() for path in masks_root.rglob("*.png")}
    if actual_images != expected_images or actual_masks != expected_masks:
        raise ValueError(
            "Derived output tree is not exact: "
            f"image_extra={sorted(actual_images - expected_images)[:5]}, "
            f"image_missing={sorted(expected_images - actual_images)[:5]}, "
            f"mask_extra={sorted(actual_masks - expected_masks)[:5]}, "
            f"mask_missing={sorted(expected_masks - actual_masks)[:5]}"
        )
    for modality, counts in class_pixels.items():
        missing = {BACKGROUND, CROP, WEED} - set(counts)
        if missing:
            raise ValueError(f"Missing common classes in {modality}: {missing}")

    manifest = data_root / str(outputs["manifest"])
    sharp_manifest = data_root / str(outputs["sharp_manifest"])
    blur_manifest = data_root / str(outputs["blur_manifest"])
    write_manifest(records, manifest)
    write_manifest([record for record in records if record.sample_id.endswith(":sharp")], sharp_manifest)
    write_manifest(
        [record for record in records if record.sample_id.endswith(":motion_blur")],
        blur_manifest,
    )

    converter_path = Path(__file__).resolve()
    report = {
        "schema_version": 1,
        "dataset_id": str(gate["dataset_id"]),
        "source_pairs_audited": len(source_panels),
        "publisher_split_counts": {key: len(value) for key, value in split_values.items()},
        "included_publisher_split": included_split,
        "included_pairs": len(included_ids),
        "samples": len(records),
        "modality_counts": dict(Counter(record.sample_id.rsplit(":", 1)[1] for record in records)),
        "split_counts": dict(Counter(record.split for record in records)),
        "group_count": len({record.group_id for record in records}),
        "rgba_composites_fully_opaque": rgba_panels,
        "source_palette_pixel_counts": {
            modality: dict(counts) for modality, counts in source_palette_counts.items()
        },
        "included_common_class_pixels": {
            modality: {
                "background": counts[BACKGROUND],
                "crop": counts[CROP],
                "weed": counts[WEED],
                "ignore": counts[IGNORE],
            }
            for modality, counts in class_pixels.items()
        },
        "ontology": {
            "background": BACKGROUND,
            "target_crop": CROP,
            "other_vegetation": WEED,
            "ignore": IGNORE,
        },
        "policy": {
            "role": output_role,
            "publisher_train_and_val_used": False,
            "publisher_pretrained_model_used": False,
            "external_test_claim": False,
            "paired_modalities_share_one_capture_group": True,
            "single_field_limit": str(gate["role_policy"]["independence_limit"]),
        },
        "provenance": {
            "landing_page": str(source["landing_page"]),
            "doi": str(source["doi"]),
            "archive": str(archive),
            "archive_sha256": sha256(archive),
            "inner_data_archive": str(inner_archive),
            "inner_data_archive_sha256": sha256(inner_archive),
            "source_composite_tree_sha256": tree_sha256(source_panels, repository),
            "archive_safety": archive_safety,
            "gate_config": str(gate_path),
            "gate_config_sha256": sha256(gate_path),
            "converter": str(converter_path),
            "converter_sha256": sha256(converter_path),
            "license": str(source["license"]),
        },
        "derived": {
            "manifest": str(manifest),
            "manifest_sha256": manifest_sha256(manifest),
            "sharp_manifest": str(sharp_manifest),
            "sharp_manifest_sha256": manifest_sha256(sharp_manifest),
            "blur_manifest": str(blur_manifest),
            "blur_manifest_sha256": manifest_sha256(blur_manifest),
            "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
        },
        "all_quality_gates_passed": True,
    }
    report_path = data_root / str(outputs["conversion_report"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config", default="configs/data/deblurweedseg_real_gate_v1.yaml"
    )
    arguments = parser.parse_args()
    manifest, report = convert(Path(arguments.gate_config))
    print(json.dumps({"manifest": str(manifest), "report": str(report)}, indent=2))


if __name__ == "__main__":
    main()
