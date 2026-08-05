#!/usr/bin/env python3
"""Convert the frozen Sugar Beets 2016 multiclass sequence to common masks."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
import yaml

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
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def palette_counts(array: np.ndarray) -> Counter[tuple[int, int, int]]:
    colours, counts = np.unique(array.reshape(-1, 3), axis=0, return_counts=True)
    return Counter(
        {
            tuple(int(value) for value in colour): int(count)
            for colour, count in zip(colours, counts, strict=True)
        }
    )


def common_mask(
    raw: np.ndarray,
    expected_palette: set[tuple[int, int, int]],
    background: tuple[int, int, int],
    crop: tuple[int, int, int],
) -> tuple[np.ndarray, Counter[tuple[int, int, int]]]:
    counts = palette_counts(raw)
    unexpected = set(counts) - expected_palette
    if unexpected:
        raise ValueError(f"Unexpected source colours: {sorted(unexpected)}")
    result = np.full(raw.shape[:2], WEED, dtype=np.uint8)
    result[np.all(raw == np.asarray(background, dtype=np.uint8), axis=2)] = BACKGROUND
    result[np.all(raw == np.asarray(crop, dtype=np.uint8), axis=2)] = CROP
    return result, counts


def contact_sheet(
    rows: list[dict[str, Any]], output: Path, selected_indices: list[int]
) -> None:
    by_index = {int(row["frame_index"]): row for row in rows}
    tile_width, image_height, title_height = 648, 242, 22
    columns = 2
    sheet_rows = math.ceil(len(selected_indices) / columns)
    sheet = Image.new(
        "RGB", (columns * tile_width, sheet_rows * (image_height + title_height)), "white"
    )
    draw = ImageDraw.Draw(sheet)
    colours = {
        CROP: np.asarray([40, 230, 40], dtype=np.float32),
        WEED: np.asarray([255, 30, 180], dtype=np.float32),
    }
    for position, index in enumerate(selected_indices):
        row = by_index[index]
        rgb = Image.open(row["rgb_path"]).convert("RGB")
        mask = np.asarray(Image.open(row["common_mask_path"]), dtype=np.uint8)
        thumbnail = rgb.resize((324, image_height), Image.Resampling.LANCZOS)
        resized_mask = np.asarray(
            Image.fromarray(mask).resize((324, image_height), Image.Resampling.NEAREST),
            dtype=np.uint8,
        )
        overlay = np.asarray(thumbnail, dtype=np.float32).copy()
        for value, colour in colours.items():
            pixels = resized_mask == value
            overlay[pixels] = 0.45 * overlay[pixels] + 0.55 * colour
        pair = Image.new("RGB", (tile_width, image_height))
        pair.paste(thumbnail, (0, 0))
        pair.paste(Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8)), (324, 0))
        x = (position % columns) * tile_width
        y = (position // columns) * (image_height + title_height)
        draw.text(
            (x + 5, y + 4),
            f"frame {index:05d} | RGB / crop=green, weed=magenta overlay",
            fill="black",
        )
        sheet.paste(pair, (x, y + title_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=92, subsampling=0)


def convert(config_path: Path) -> tuple[Path, Path]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config must be a mapping")
    if config.get("frozen_before_any_model_evaluation") is not True:
        raise ValueError("Holdout config is not frozen")
    project_root = Path(__file__).resolve().parents[1]
    data_root = (project_root / "data").resolve()
    source = config["source"]
    contract = config["publisher_contract"]
    ontology = config["ontology"]
    capture = config["capture"]
    policy = config["role_policy"]
    outputs = config["outputs"]

    annotation_receipt_path = data_root / source["annotation_receipt"]
    rgb_receipt_path = data_root / source["rgb_receipt"]
    require_equal(
        "annotation receipt SHA-256",
        sha256(annotation_receipt_path),
        source["annotation_receipt_sha256"],
    )
    require_equal(
        "RGB receipt SHA-256", sha256(rgb_receipt_path), source["rgb_receipt_sha256"]
    )
    annotation_receipt = load_json(annotation_receipt_path)
    rgb_receipt = load_json(rgb_receipt_path)
    require_equal(
        "annotation acquisition gate",
        annotation_receipt.get("all_acquisition_gates_passed"),
        True,
    )
    require_equal(
        "RGB acquisition gate",
        rgb_receipt.get("all_acquisition_pairing_gates_passed"),
        True,
    )
    require_equal(
        "annotation archive SHA-256",
        annotation_receipt.get("archive_sha256"),
        source["annotation_archive_sha256"],
    )
    require_equal(
        "RGB archive SHA-256",
        rgb_receipt.get("archive_sha256"),
        source["rgb_archive_sha256"],
    )

    annotation_inventory = {
        Path(str(row["member"])).name: row
        for row in annotation_receipt["member_inventory"]
    }
    rgb_inventory = {
        int(row["frame_index"]): row for row in rgb_receipt["selected_inventory"]
    }
    first = int(contract["first_frame_index"])
    last = int(contract["last_frame_index"])
    indices = list(range(first, last + 1))
    require_equal("frozen frame count", len(indices), int(contract["expected_frames"]))
    require_equal("RGB receipt frame ids", sorted(rgb_inventory), indices)

    annotations_dir = data_root / source["annotations_dir"]
    rgb_dir = data_root / source["rgb_dir"]
    mask_pattern = re.compile(
        rf"^{re.escape(str(source['sequence']))}_frame(\d+)_GroundTruth_color\.png$"
    )
    actual_annotation_names = {
        path.name for path in annotations_dir.glob("*_GroundTruth_color.png")
    }
    expected_annotation_names = {
        f"{source['sequence']}_frame{index}_GroundTruth_color.png" for index in indices
    }
    require_equal(
        "exact annotation file set", actual_annotation_names, expected_annotation_names
    )
    if any(mask_pattern.fullmatch(name) is None for name in actual_annotation_names):
        raise ValueError("Unexpected annotation filename")
    actual_rgb_names = {path.name for path in rgb_dir.glob("rgb_*.png")}
    expected_rgb_names = {f"rgb_{index:05d}.png" for index in indices}
    require_equal("exact RGB file set", actual_rgb_names, expected_rgb_names)

    expected_palette = {
        tuple(int(value) for value in colour)
        for colour in contract["expected_palette_rgb"]
    }
    background_rgb = tuple(int(value) for value in ontology["source_black_rgb"])
    crop_rgb = tuple(int(value) for value in ontology["source_sugar_beet_rgb"])
    common_ids = ontology["common_ids"]
    require_equal("crop id", int(common_ids["target_crop"]), CROP)
    require_equal("weed id", int(common_ids["other_vegetation"]), WEED)
    require_equal("background id", int(common_ids["background"]), BACKGROUND)
    require_equal("ignore id", int(common_ids["ignore"]), IGNORE)

    masks_root = data_root / outputs["common_masks"]
    manifest_path = data_root / outputs["manifest"]
    report_path = data_root / outputs["conversion_report"]
    contact_path = data_root / outputs["contact_sheet"]
    for path in (masks_root, manifest_path, report_path, contact_path):
        if path.exists():
            raise FileExistsError(path)
    masks_root.mkdir(parents=True)

    source_palette_pixels: Counter[tuple[int, int, int]] = Counter()
    common_pixels: Counter[int] = Counter()
    records: list[SampleRecord] = []
    frame_rows: list[dict[str, Any]] = []
    expected_size = tuple(int(value) for value in contract["expected_dimensions"])
    for index in indices:
        rgb_path = rgb_dir / f"rgb_{index:05d}.png"
        annotation_name = (
            f"{source['sequence']}_frame{index}_GroundTruth_color.png"
        )
        raw_mask_path = annotations_dir / annotation_name
        rgb_receipt_row = rgb_inventory[index]
        annotation_receipt_row = annotation_inventory[annotation_name]
        require_equal(
            f"RGB SHA frame {index}", sha256(rgb_path), rgb_receipt_row["rgb_sha256"]
        )
        require_equal(
            f"mask SHA frame {index}",
            sha256(raw_mask_path),
            annotation_receipt_row["sha256"],
        )
        with Image.open(rgb_path) as image:
            require_equal(f"RGB size frame {index}", image.size, expected_size)
            require_equal(
                f"RGB mode frame {index}", image.mode, contract["expected_rgb_mode"]
            )
            image.verify()
        with Image.open(raw_mask_path) as image:
            require_equal(f"mask size frame {index}", image.size, expected_size)
            raw = np.asarray(image.convert("RGB"), dtype=np.uint8)
        normalized, counts = common_mask(
            raw, expected_palette, background_rgb, crop_rgb
        )
        source_palette_pixels.update(counts)
        frame_common = Counter(
            {
                value: int(np.count_nonzero(normalized == value))
                for value in (CROP, WEED, BACKGROUND, IGNORE)
            }
        )
        common_pixels.update(frame_common)
        mask_path = masks_root / f"frame_{index:05d}.png"
        Image.fromarray(normalized, mode="L").save(mask_path, format="PNG", optimize=False)
        sample_id = f"sugarbeets2016_multiclass:{source['sequence']}:frame{index:05d}"
        records.append(
            SampleRecord(
                sample_id=sample_id,
                image_path=relative(rgb_path, data_root),
                mask_path=relative(mask_path, data_root),
                split=str(policy["output_split"]),
                dataset_id=str(config["dataset_id"]),
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
        total = normalized.size
        frame_rows.append(
            {
                "frame_index": index,
                "rgb_path": str(rgb_path),
                "raw_mask_path": str(raw_mask_path),
                "common_mask_path": str(mask_path),
                "common_pixels": {
                    "crop": frame_common[CROP],
                    "weed": frame_common[WEED],
                    "background": frame_common[BACKGROUND],
                    "ignore": frame_common[IGNORE],
                },
                "fractions": {
                    "crop": frame_common[CROP] / total,
                    "weed": frame_common[WEED] / total,
                    "background": frame_common[BACKGROUND] / total,
                },
            }
        )

    require_equal("observed exact palette", set(source_palette_pixels), expected_palette)
    if any(common_pixels[value] <= 0 for value in (CROP, WEED, BACKGROUND)):
        raise ValueError("One or more common classes is absent")
    require_equal("ignore pixels", common_pixels[IGNORE], 0)
    write_manifest(records, manifest_path)
    selected_contact_indices = [23, 48, 73, 98, 123, 148, 173, 198, 223, 248, 273, 305]
    contact_sheet(frame_rows, contact_path, selected_contact_indices)

    total_pixels = sum(common_pixels.values())
    report = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "status": "automated_pass_pending_duplicate_and_manual_visual_gates",
        "frozen_before_any_model_evaluation": True,
        "frames": len(records),
        "field_session_units": 1,
        "split_counts": dict(Counter(record.split for record in records)),
        "source_palette_pixel_counts": {
            ",".join(str(value) for value in colour): count
            for colour, count in sorted(source_palette_pixels.items())
        },
        "common_pixel_counts": {
            "target_crop": common_pixels[CROP],
            "other_vegetation": common_pixels[WEED],
            "background": common_pixels[BACKGROUND],
            "ignore": common_pixels[IGNORE],
        },
        "common_pixel_fractions": {
            "target_crop": common_pixels[CROP] / total_pixels,
            "other_vegetation": common_pixels[WEED] / total_pixels,
            "background": common_pixels[BACKGROUND] / total_pixels,
            "ignore": common_pixels[IGNORE] / total_pixels,
        },
        "frame_inventory": frame_rows,
        "manual_contact_indices": selected_contact_indices,
        "policy": {
            "training_allowed": False,
            "single_correlated_sequence": True,
            "one_sequence_one_field_session_vote": True,
            "dataset_image_or_pixel_weighting_forbidden": True,
            "real_panel": policy["real_panel"],
            "final_test_claim": False,
        },
        "provenance": {
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "annotation_receipt": str(annotation_receipt_path),
            "annotation_receipt_sha256": sha256(annotation_receipt_path),
            "rgb_receipt": str(rgb_receipt_path),
            "rgb_receipt_sha256": sha256(rgb_receipt_path),
            "converter": str(Path(__file__).resolve()),
            "converter_sha256": sha256(Path(__file__).resolve()),
            "license": source["license"],
            "official_dataset_page": source["official_dataset_page"],
            "primary_article": source["primary_article"],
        },
        "derived": {
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha256(manifest_path),
            "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
            "contact_sheet": str(contact_path),
            "contact_sheet_sha256": sha256(contact_path),
        },
        "automated_quality_gates": {
            "receipts_and_archive_hashes_locked": True,
            "exact_rgb_mask_pairing": len(records) == int(contract["expected_frames"]),
            "all_images_and_masks_decode_1296x966": True,
            "source_palette_exact": set(source_palette_pixels) == expected_palette,
            "three_common_classes_present": all(
                common_pixels[value] > 0 for value in (CROP, WEED, BACKGROUND)
            ),
            "common_masks_have_no_unexpected_ignore": common_pixels[IGNORE] == 0,
            "one_field_session_group": len({record.group_id for record in records}) == 1,
        },
        "all_automated_conversion_gates_passed": True,
        "duplicate_gate_passed": False,
        "manual_visual_gate_passed": False,
        "holdout_release_accepted": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/data/sugarbeets2016_multiclass_holdout_v1.yaml"
    )
    args = parser.parse_args()
    manifest, report = convert(Path(args.config))
    print(json.dumps({"manifest": str(manifest), "report": str(report)}, indent=2))


if __name__ == "__main__":
    main()
