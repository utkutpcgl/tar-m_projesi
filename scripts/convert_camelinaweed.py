#!/usr/bin/env python3
"""Validate CamelinaWeed and build conservative positive-only masks/manifests."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZipFile

import yaml
from PIL import Image, ImageDraw

from agri_seg.constants import IGNORE, WEED
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    write_manifest,
)

Polygon = list[tuple[float, float]]

try:
    from scripts.fetch_camelinaweed_sparse_ranges import selected_members
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repo root.
    from fetch_camelinaweed_sparse_ranges import selected_members


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve_project(project_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def relative_to_data(path: Path, data_root: Path) -> str:
    return path.resolve().relative_to(data_root.resolve()).as_posix()


def write_exact(path: Path, payload: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise ValueError(f"Existing derived file differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    if partial.exists():
        raise FileExistsError(f"Stale partial output requires inspection: {partial}")
    partial.write_bytes(payload)
    partial.replace(path)


def locked_inputs(gate: dict[str, Any], project_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, specification in gate["locked_inputs"].items():
        if isinstance(specification, str):
            path = resolve_project(project_root, specification)
            expected_hash = None
        elif isinstance(specification, dict):
            path = resolve_project(project_root, str(specification["path"]))
            expected_hash = specification.get("sha256")
        else:
            raise ValueError(f"Invalid locked input: {name}")
        if not path.is_file():
            raise FileNotFoundError(path)
        if expected_hash is not None:
            require_equal(f"locked input SHA {name}", sha256(path), str(expected_hash))
        paths[name] = path
    return paths


def polygon_points(
    polygon: object, width: int, height: int
) -> tuple[list[tuple[float, float]], int]:
    """Validate one COCO polygon in the continuous image domain.

    COCO coordinates may lie on the right/bottom continuous boundary, hence
    ``x == width`` and ``y == height`` are valid and clipped by rasterization.
    """
    if not isinstance(polygon, list):
        raise ValueError("COCO polygon must be a list")
    if len(polygon) < 6:
        raise ValueError("COCO polygon must contain at least three points")
    if len(polygon) % 2:
        raise ValueError("COCO polygon coordinate count must be even")
    values: list[float] = []
    for value in polygon:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Non-numeric COCO polygon coordinate: {value!r}")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"Non-finite COCO polygon coordinate: {value!r}")
        values.append(numeric)
    points = list(zip(values[::2], values[1::2]))
    if any(x < 0 or x > width or y < 0 or y > height for x, y in points):
        raise ValueError("COCO polygon falls outside the image domain")
    boundary_coordinates = sum(
        x == 0 or x == width or y == 0 or y == height for x, y in points
    )
    return points, boundary_coordinates


def normalized_partial_mask_png(
    width: int, height: int, polygons: Iterable[Polygon]
) -> tuple[bytes, int]:
    mask = Image.new("L", (width, height), IGNORE)
    draw = ImageDraw.Draw(mask)
    count = 0
    for points in polygons:
        draw.polygon(points, fill=WEED)
        count += 1
    if count == 0:
        raise ValueError("A manifest mask must contain an accepted polygon")
    histogram = mask.histogram()
    positive_pixels = int(histogram[WEED])
    if positive_pixels <= 0:
        raise ValueError("Accepted polygons rasterized to zero positive pixels")
    if sum(histogram[index] for index in range(256) if index not in {WEED, IGNORE}):
        raise ValueError("Derived partial mask has an invalid palette")
    payload = io.BytesIO()
    mask.save(payload, format="PNG", optimize=False, compress_level=9)
    return payload.getvalue(), positive_pixels


def verify_release_tree(
    sparse_archive: Path, release_root: Path, receipt: dict[str, Any]
) -> tuple[dict[str, str], int]:
    """Reproduce the range fetcher's selected-member tree digest."""
    digest = hashlib.sha256()
    file_hashes: dict[str, str] = {}
    total_bytes = 0
    with ZipFile(sparse_archive) as archive:
        members = selected_members(archive, "annotated")
        for info in members:
            source = release_root.joinpath(*Path(info.filename).parts)
            if not source.is_file():
                raise FileNotFoundError(source)
            require_equal(f"extracted size {info.filename}", source.stat().st_size, info.file_size)
            file_hash = sha256(source)
            file_hashes[info.filename] = file_hash
            digest.update(info.filename.encode("utf-8"))
            digest.update(bytes.fromhex(file_hash))
            total_bytes += info.file_size
    extraction = receipt["extraction"]
    require_equal("annotated selected files", len(file_hashes), int(extraction["files"]))
    require_equal("annotated extracted bytes", total_bytes, int(extraction["bytes"]))
    require_equal("annotated selected tree SHA", digest.hexdigest(), extraction["tree_sha256"])
    return file_hashes, total_bytes


def source_image_tree_sha256(
    records: list[SampleRecord], data_root: Path, file_hashes: dict[str, str], release_root: Path
) -> str:
    digest = hashlib.sha256()
    release_prefix = release_root.resolve()
    for record in sorted(records, key=lambda item: item.image_path):
        source = (data_root / record.image_path).resolve()
        member = source.relative_to(release_prefix).as_posix()
        member = f"CamelinaWeed/{member.split('CamelinaWeed/', 1)[-1]}" if not member.startswith("CamelinaWeed/") else member
        file_hash = file_hashes.get(member)
        if file_hash is None:
            raise ValueError(f"Image absent from verified release tree: {member}")
        digest.update(record.image_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash))
        digest.update(b"\0")
    return digest.hexdigest()


def distribution(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("Cannot summarize an empty distribution")
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def convert(gate_path: Path) -> tuple[Path, Path]:
    gate_path = gate_path.expanduser().resolve()
    project_root = gate_path.parents[2]
    gate = load_yaml(gate_path)
    require_equal("schema version", gate.get("schema_version"), 1)
    gate_hash = sha256(gate_path)
    data_root = resolve_project(project_root, str(gate["data_root"]))
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    locked = locked_inputs(gate, project_root)
    acquisition_receipt = load_json(locked["annotated_range_receipt"])
    require_equal("range receipt status", acquisition_receipt.get("status"), "verified")
    require_equal("range receipt mode", acquisition_receipt.get("mode"), "annotated")
    require_equal("range ZIP CRC", acquisition_receipt.get("zip_crc_verified_by_read"), True)
    require_equal("range external test use", acquisition_receipt.get("external_test_used"), False)
    require_equal("range model-selection use", acquisition_receipt.get("model_selection_used"), False)
    require_equal("range common-model permission", acquisition_receipt.get("common_model_training_allowed"), False)
    require_equal(
        "acquisition config SHA in receipt",
        acquisition_receipt["config"]["sha256"],
        gate["locked_inputs"]["acquisition_config"]["sha256"],
    )

    outputs = gate["outputs"]
    release_root = resolve_project(project_root, str(outputs["annotated_release"]))
    require_equal("range output directory", resolve_project(project_root, acquisition_receipt["output_dir"]), release_root)
    file_hashes, source_bytes = verify_release_tree(
        locked["sparse_archive"], release_root, acquisition_receipt
    )

    expected = gate["expected_release"]
    all_files = [path for path in release_root.rglob("*") if path.is_file()]
    all_jpg = [path for path in all_files if path.suffix.lower() == ".jpg"]
    all_json = [path for path in all_files if path.suffix.lower() == ".json"]
    require_equal("annotated release file count", len(all_files), int(expected["annotated_jpg"]) + int(expected["all_coco_json"]))
    require_equal("annotated JPEG count", len(all_jpg), int(expected["annotated_jpg"]))
    require_equal("all COCO JSON count", len(all_json), int(expected["all_coco_json"]))
    if len(all_files) != len(all_jpg) + len(all_json):
        raise ValueError("Unexpected non-JPEG/non-JSON file in selected release")

    normalized_root = resolve_project(project_root, str(outputs["normalized_partial_masks"]))
    records: list[SampleRecord] = []
    group_reports: list[dict[str, Any]] = []
    accepted_category_counts: Counter[str] = Counter()
    ignored_category_counts: Counter[str] = Counter()
    all_coverages: list[float] = []
    all_source_paths: set[Path] = set()
    total_annotations = 0
    total_accepted_annotations = 0
    total_empty = 0
    total_k = 0
    total_excluded_images = 0
    total_boundary_coordinates = 0
    decoded_format_counts: Counter[str] = Counter()

    canonical_groups = gate["canonical_groups"]
    require_equal("canonical COCO count", len(canonical_groups), int(expected["canonical_coco_json"]))
    for group in canonical_groups:
        group_id = str(group["id"])
        coco_path = release_root / str(group["coco"])
        if not coco_path.is_file():
            raise FileNotFoundError(coco_path)
        coco = load_json(coco_path)
        images = coco.get("images")
        annotations = coco.get("annotations")
        categories = coco.get("categories")
        if not isinstance(images, list) or not isinstance(annotations, list) or not isinstance(categories, list):
            raise ValueError(f"Invalid COCO arrays: {coco_path}")
        require_equal(f"{group_id} image count", len(images), int(group["images"]))
        require_equal(f"{group_id} annotation count", len(annotations), int(group["annotations"]))
        total_annotations += len(annotations)

        image_by_id: dict[object, dict[str, Any]] = {}
        for image in images:
            if not isinstance(image, dict) or image.get("id") in image_by_id:
                raise ValueError(f"Invalid or duplicate COCO image ID in {group_id}")
            image_by_id[image["id"]] = image
        category_by_id: dict[object, str] = {}
        for category in categories:
            if not isinstance(category, dict) or category.get("id") in category_by_id:
                raise ValueError(f"Invalid or duplicate category ID in {group_id}")
            category_by_id[category["id"]] = str(category["name"]).strip()

        image_names = [str(image.get("file_name", "")) for image in images]
        if any(not name or Path(name).name != name for name in image_names):
            raise ValueError(f"Unsafe or missing COCO image filename in {group_id}")
        if len(set(image_names)) != len(image_names):
            raise ValueError(f"Duplicate COCO image filename in {group_id}")
        folder_jpg = {
            path.name for path in coco_path.parent.iterdir()
            if path.is_file() and path.suffix.lower() == ".jpg"
        }
        require_equal(f"{group_id} exact COCO/JPEG match", set(image_names), folder_jpg)

        annotations_by_image: dict[object, list[tuple[str, list[Polygon]]]] = defaultdict(list)
        seen_annotation_ids: set[object] = set()
        group_empty = 0
        group_k = 0
        group_accepted_annotations = 0
        group_boundary_coordinates = 0
        for annotation in annotations:
            if not isinstance(annotation, dict):
                raise ValueError(f"Invalid COCO annotation in {group_id}")
            annotation_id = annotation.get("id")
            if annotation_id in seen_annotation_ids:
                raise ValueError(f"Duplicate annotation ID in {group_id}: {annotation_id}")
            seen_annotation_ids.add(annotation_id)
            image_id = annotation.get("image_id")
            category_id = annotation.get("category_id")
            if image_id not in image_by_id or category_id not in category_by_id:
                raise ValueError(f"Dangling annotation reference in {group_id}: {annotation_id}")
            if int(annotation.get("iscrowd", 0)) != 0:
                raise ValueError(f"Unsupported crowd annotation in {group_id}: {annotation_id}")
            category_name = category_by_id[category_id]
            segmentation = annotation.get("segmentation")
            if category_name.lower() == "k":
                group_k += 1
                ignored_category_counts[category_name] += 1
                continue
            if not segmentation:
                group_empty += 1
                ignored_category_counts[category_name] += 1
                continue
            if not isinstance(segmentation, list):
                raise ValueError(f"Non-polygon segmentation in {group_id}: {annotation_id}")
            image = image_by_id[image_id]
            width, height = int(image["width"]), int(image["height"])
            annotation_polygons: list[Polygon] = []
            for polygon in segmentation:
                points, boundary_coordinates = polygon_points(polygon, width, height)
                annotation_polygons.append(points)
                group_boundary_coordinates += boundary_coordinates
            if not annotation_polygons:
                raise ValueError(f"Empty polygon list in {group_id}: {annotation_id}")
            annotations_by_image[image_id].append((category_name, annotation_polygons))
            accepted_category_counts[category_name] += 1
            group_accepted_annotations += 1

        expected_shape = tuple(int(value) for value in expected["image_shapes"][str(group["platform"])])
        group_coverages: list[float] = []
        group_positive_pixels = 0
        group_excluded: list[str] = []
        group_decoded_formats: Counter[str] = Counter()
        for image in images:
            image_id = image["id"]
            filename = str(image["file_name"])
            width, height = int(image["width"]), int(image["height"])
            require_equal(f"{group_id} metadata shape {filename}", (width, height), expected_shape)
            source = coco_path.parent / filename
            all_source_paths.add(source.resolve())
            with Image.open(source) as handle:
                source_format = str(handle.format)
                if source_format not in {"JPEG", "MPO"}:
                    raise ValueError(
                        f"{group_id} is not JPEG-compatible: {filename} ({source_format})"
                    )
                require_equal(f"{group_id} decoded shape {filename}", handle.size, (width, height))
                handle.seek(0)
                decoded = handle.convert("RGB")
                decoded.load()
                require_equal(f"{group_id} RGB decoded shape {filename}", decoded.size, (width, height))
                group_decoded_formats[source_format] += 1
                decoded_format_counts[source_format] += 1
            accepted = annotations_by_image.get(image_id, [])
            if not accepted:
                group_excluded.append(filename)
                continue
            polygons = [polygon for _, polygon_list in accepted for polygon in polygon_list]
            payload, positive_pixels = normalized_partial_mask_png(width, height, polygons)
            mask_path = normalized_root / group_id / f"{Path(filename).stem}.png"
            write_exact(mask_path, payload)
            coverage = positive_pixels / (width * height)
            group_coverages.append(coverage)
            all_coverages.append(coverage)
            group_positive_pixels += positive_pixels
            species = sorted({category for category, _ in accepted})
            records.append(
                SampleRecord(
                    sample_id=f"camelinaweed:{group_id}:{Path(filename).stem}",
                    image_path=relative_to_data(source, data_root),
                    mask_path=relative_to_data(mask_path, data_root),
                    split=str(group["role"]),
                    dataset_id=str(gate["dataset_id"]),
                    field_id=f"greece_{str(group['location']).lower()}",
                    session_id=group_id,
                    capture_date="",
                    platform=str(group["platform"]),
                    sensor="RGB",
                    target_crop_id=int(gate["target_crop_id"]),
                    crop_species=str(gate["crop_species"]),
                    weed_species_optional=" | ".join(species),
                    growth_stage="unknown_within_reported_season",
                    annotation_exhaustive=False,
                    license_status=str(gate["license"]),
                    commercial_allowed=bool(gate["commercial_allowed"]),
                )
            )

        require_equal(f"{group_id} accepted images", len(group_coverages), int(group["accepted_images"]))
        group_reports.append(
            {
                "id": group_id,
                "location": group["location"],
                "season": group["season"],
                "platform": group["platform"],
                "altitude_m": group["altitude_m"],
                "role": group["role"],
                "source_images": len(images),
                "accepted_images": len(group_coverages),
                "excluded_images": len(group_excluded),
                "excluded_filenames": sorted(group_excluded),
                "annotations": len(annotations),
                "accepted_positive_annotations": group_accepted_annotations,
                "ignored_empty_annotations": group_empty,
                "ignored_ambiguous_k_annotations": group_k,
                "polygon_boundary_coordinates": group_boundary_coordinates,
                "positive_pixels": group_positive_pixels,
                "decoded_format_counts": dict(sorted(group_decoded_formats.items())),
                "positive_coverage_fraction": distribution(group_coverages),
            }
        )
        total_accepted_annotations += group_accepted_annotations
        total_empty += group_empty
        total_k += group_k
        total_excluded_images += len(group_excluded)
        total_boundary_coordinates += group_boundary_coordinates

    require_equal("canonical source image count", len(all_source_paths), int(expected["canonical_images"]))
    require_equal("canonical annotations", total_annotations, int(expected["canonical_annotations"]))
    require_equal("accepted positive annotations", total_accepted_annotations, int(expected["accepted_positive_annotations"]))
    require_equal("ignored empty annotations", total_empty, int(expected["empty_segmentation_annotations_to_ignore"]))
    require_equal("ignored ambiguous k annotations", total_k, int(expected["ambiguous_category_k_annotations_to_ignore"]))
    require_equal("excluded images", total_excluded_images, int(expected["images_without_accepted_positive_to_exclude"]))
    require_equal("accepted images", len(records), int(expected["accepted_images"]))

    records.sort(key=lambda item: item.sample_id)
    train_records = [record for record in records if record.split == "train"]
    calibration_records = [record for record in records if record.split == "external_calibration"]
    require_equal("train images", len(train_records), int(expected["train_images"]))
    require_equal("calibration images", len(calibration_records), int(expected["external_calibration_images"]))
    require_equal(
        "train/calibration field overlap",
        len({record.field_id for record in train_records} & {record.field_id for record in calibration_records}),
        int(expected["train_calibration_location_overlap"]),
    )
    if any(record.annotation_exhaustive for record in records):
        raise ValueError("CamelinaWeed partial labels must never be marked exhaustive")

    manifest_path = resolve_project(project_root, str(outputs["manifest"]))
    train_path = resolve_project(project_root, str(outputs["train_manifest"]))
    calibration_path = resolve_project(project_root, str(outputs["calibration_manifest"]))
    write_manifest(records, manifest_path)
    write_manifest(train_records, train_path)
    write_manifest(calibration_records, calibration_path)
    manifest_payload = {
        "all": {"path": str(manifest_path), "samples": len(records), "sha256": manifest_sha256(manifest_path)},
        "train_candidate": {"path": str(train_path), "samples": len(train_records), "sha256": manifest_sha256(train_path)},
        "external_calibration": {"path": str(calibration_path), "samples": len(calibration_records), "sha256": manifest_sha256(calibration_path)},
    }
    mask_hash = mask_tree_sha256(records, data_root)
    image_hash = source_image_tree_sha256(records, data_root, file_hashes, release_root)
    split_counts = Counter(record.split for record in records)

    content_path = resolve_project(project_root, str(outputs["content_audit"]))
    content = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": gate["dataset_id"],
        "automated_content_gate_passed": True,
        "gate_config": str(gate_path),
        "gate_config_sha256": gate_hash,
        "source": {
            "annotated_release": str(release_root),
            "selected_files": len(all_files),
            "selected_bytes": source_bytes,
            "selected_tree_sha256": acquisition_receipt["extraction"]["tree_sha256"],
            "jpeg_images": len(all_jpg),
            "coco_json_files": len(all_json),
            "canonical_coco_json_files": len(canonical_groups),
            "all_jpeg_decoded": True,
            "decoded_format_counts": dict(sorted(decoded_format_counts.items())),
            "mpo_note": "Pillow reports some DJI .JPG files as MPO because they carry MPF metadata; frame 0 is fully RGB-decoded and shape-checked.",
            "all_canonical_coco_jpeg_sets_exact": True,
        },
        "counts": {
            "canonical_images": len(all_source_paths),
            "canonical_annotations": total_annotations,
            "accepted_positive_annotations": total_accepted_annotations,
            "ignored_empty_annotations": total_empty,
            "ignored_ambiguous_k_annotations": total_k,
            "excluded_images_without_accepted_positive": total_excluded_images,
            "manifest_images": len(records),
        },
        "split_counts": dict(sorted(split_counts.items())),
        "field_counts": dict(sorted(Counter(record.field_id for record in records).items())),
        "group_reports": group_reports,
        "accepted_category_annotation_counts": dict(sorted(accepted_category_counts.items())),
        "ignored_category_annotation_counts": dict(sorted(ignored_category_counts.items())),
        "polygon_validation": {
            "all_numeric": True,
            "all_even_coordinate_count": True,
            "all_minimum_three_points": True,
            "all_inside_closed_image_domain": True,
            "boundary_coordinates": total_boundary_coordinates,
            "continuous_domain_note": "COCO coordinates at x=width or y=height are valid boundary coordinates and rasterize clipped to the last pixel.",
        },
        "partial_mask": {
            "palette": [WEED, IGNORE],
            "weed_value": WEED,
            "non_polygon_value": IGNORE,
            "positive_coverage_fraction": distribution(all_coverages),
            "mask_tree_sha256": mask_hash,
        },
        "source_manifest_image_tree_sha256": image_hash,
        "manifests": manifest_payload,
        "ontology": {
            "accepted_weed_polygon_to_common": WEED,
            "ambiguous_category_k_to_common": IGNORE,
            "invalid_or_empty_polygon_to_common": IGNORE,
            "all_non_polygon_pixels_to_common": IGNORE,
            "crop_pixels_supervised": False,
            "background_pixels_supervised": False,
            "annotation_exhaustive": False,
        },
        "metadata_warning": "COCO date_captured values reflect export metadata and conflict with the reported 2025/2025-2026 seasons; capture_date is intentionally blank.",
        "common_three_class_training_allowed": False,
        "positive_only_partial_label_training_allowed": False,
        "external_test_used": False,
        "model_selection_used": False,
        "pending_gates": ["exact_and_near_duplicate_audit", "manual_group_by_coverage_review"],
        "converter": str(Path(__file__).resolve()),
        "converter_sha256": sha256(Path(__file__).resolve()),
    }
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    conversion_path = resolve_project(project_root, str(outputs["conversion_receipt"]))
    conversion = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": gate["dataset_id"],
        "status": "verified",
        "gate_config": str(gate_path),
        "gate_config_sha256": gate_hash,
        "acquisition_receipt": str(locked["annotated_range_receipt"]),
        "acquisition_receipt_sha256": sha256(locked["annotated_range_receipt"]),
        "content_audit": str(content_path),
        "content_audit_sha256": sha256(content_path),
        "derived": {
            "manifests": manifest_payload,
            "normalized_partial_masks": str(normalized_root),
            "normalized_partial_mask_files": len(records),
            "normalized_partial_mask_tree_sha256": mask_hash,
            "source_manifest_image_tree_sha256": image_hash,
        },
        "usage_policy": {
            "common_three_class_training_allowed": False,
            "positive_only_partial_label_training_allowed": False,
            "external_calibration_is_not_external_test": True,
            "unlock_requires": "A separately frozen, implemented, and validated partial-label objective.",
        },
        "external_test_used": False,
        "model_selection_used": False,
        "converter": str(Path(__file__).resolve()),
        "converter_sha256": sha256(Path(__file__).resolve()),
    }
    conversion_path.parent.mkdir(parents=True, exist_ok=True)
    conversion_path.write_text(json.dumps(conversion, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return conversion_path, content_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config",
        type=Path,
        default=Path("configs/data/camelinaweed_partial_label_gate_v1.yaml"),
    )
    arguments = parser.parse_args()
    conversion, content = convert(arguments.gate_config)
    print(
        json.dumps(
            {
                "conversion_receipt": str(conversion),
                "conversion_receipt_sha256": sha256(conversion),
                "content_audit": str(content),
                "content_audit_sha256": sha256(content),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
