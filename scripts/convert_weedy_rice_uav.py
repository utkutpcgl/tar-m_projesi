#!/usr/bin/env python3
"""Validate and convert the pinned Weedy Rice UAV RGB/mask release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile, ZipInfo

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import IGNORE, WEED
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    write_manifest,
)
try:
    from scripts.audit_weedy_rice_uav_archive import archive_summary
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repo root.
    from audit_weedy_rice_uav_archive import archive_summary


SOURCE_ROOT = PurePosixPath("WeedyRice-RGBMS-DB")
RGB_PATTERN = re.compile(
    r"^DJI_DateTime_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_"
    r"(\d+)_lat_(-?\d+(?:\.\d+)?)_lon_(-?\d+(?:\.\d+)?)_"
    r"alt_(-?\d+(?:\.\d+)?)m\.JPG$"
)
COVERAGE_BINS = (
    (0.05, "gt_0_le_5_percent"),
    (0.10, "gt_5_le_10_percent"),
    (0.20, "gt_10_le_20_percent"),
    (0.30, "gt_20_le_30_percent"),
    (0.40, "gt_30_le_40_percent"),
    (0.60, "gt_40_le_60_percent"),
    (0.75, "gt_60_le_75_percent"),
    (0.90, "gt_75_lt_90_percent"),
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve_project(project_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def require_inside(path: Path, root: Path, name: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{name} must remain below data_root: {resolved}") from exc
    return resolved


def relative(path: Path, data_root: Path) -> str:
    return path.resolve().relative_to(data_root.resolve()).as_posix()


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


def csv_member(archive: ZipFile, name: str) -> tuple[list[str], list[dict[str, str]]]:
    text = archive.read(name).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError(f"CSV has no header: {name}")
    return list(reader.fieldnames), list(reader)


def unique_index(rows: list[dict[str, str]], key: str, name: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row[key]
        if not value or value in result:
            raise ValueError(f"Missing or duplicate {key} in {name}: {value!r}")
        result[value] = row
    return result


def write_exact(path: Path, payload: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise ValueError(f"Existing derived file differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    if temporary.exists():
        raise FileExistsError(f"Stale partial output requires inspection: {temporary}")
    temporary.write_bytes(payload)
    temporary.replace(path)


def tree_sha256(paths: set[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        recorded = path.resolve().relative_to(root.resolve()).as_posix()
        digest.update(recorded.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def image_tree_sha256(records: list[SampleRecord], data_root: Path) -> str:
    paths = {
        (Path(record.image_path) if Path(record.image_path).is_absolute() else data_root / record.image_path).resolve()
        for record in records
    }
    return tree_sha256(paths, data_root)


def coverage_bin(fraction: float) -> str:
    if fraction <= 0:
        raise ValueError(f"Empty weedy-rice mask: {fraction}")
    for upper, name in COVERAGE_BINS:
        if fraction <= upper + 1e-12:
            return name
    raise ValueError(f"Forbidden weedy-rice coverage: {fraction}")


def parse_rgb_filename(name: str) -> dict[str, str | float]:
    match = RGB_PATTERN.fullmatch(name)
    if match is None:
        raise ValueError(f"Unexpected standardized RGB filename: {name}")
    year, month, day, hour, minute, index, latitude, longitude, altitude = match.groups()
    return {
        "date": f"{year}-{month}-{day}",
        "hour_minute": f"{hour}:{minute}",
        "index": index,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "altitude": float(altitude),
    }


def normalized_mask_png(source: np.ndarray) -> bytes:
    normalized = np.full(source.shape, IGNORE, dtype=np.uint8)
    normalized[source == 255] = WEED
    output = io.BytesIO()
    Image.fromarray(normalized).save(
        output, format="PNG", optimize=False, compress_level=9
    )
    return output.getvalue()


def validate_locked_inputs(gate: dict[str, Any], project_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, specification in gate["locked_inputs"].items():
        if isinstance(specification, str):
            path = resolve_project(project_root, specification)
            expected = None
        elif isinstance(specification, dict):
            path = resolve_project(project_root, str(specification["path"]))
            expected = specification.get("sha256")
        else:
            raise ValueError(f"Invalid locked-input specification: {name}")
        if not path.is_file():
            raise FileNotFoundError(path)
        if expected is not None and sha256(path) != str(expected):
            raise ValueError(f"Locked input changed: {name}")
        paths[name] = path
    return paths


def expected_member_groups(
    archive: ZipFile, expected: dict[str, Any]
) -> dict[str, list[ZipInfo]]:
    summary = archive_summary(archive)
    require_equal("nested release files", summary["files"], int(expected["total_files"]))
    groups: dict[str, list[ZipInfo]] = {
        "RGB": [],
        "Masks": [],
        "Multispectral": [],
        "Overlay": [],
        "Metadata": [],
        "root": [],
    }
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename)
        if not path.parts or path.parts[0] != SOURCE_ROOT.name:
            raise ValueError(f"File outside canonical release root: {info.filename}")
        if len(path.parts) == 2:
            groups["root"].append(info)
        elif len(path.parts) == 3 and path.parts[1] in groups:
            groups[path.parts[1]].append(info)
        else:
            raise ValueError(f"Unexpected nested release layout: {info.filename}")
    for name, key in (
        ("RGB", "rgb_images"),
        ("Masks", "masks"),
        ("Multispectral", "multispectral_images"),
        ("Overlay", "overlays"),
    ):
        require_equal(f"{name} file count", len(groups[name]), int(expected[key]))
    require_equal("Metadata file count", len(groups["Metadata"]), 3)
    require_equal(
        "Metadata member names",
        {PurePosixPath(info.filename).name for info in groups["Metadata"]},
        {"filename_mapping.csv", "image_metadata.csv", "readme.txt"},
    )
    require_equal(
        "root member names",
        {PurePosixPath(info.filename).name for info in groups["root"]},
        {"readme.md", *expected["publisher_split_lists"].keys()},
    )
    require_equal(
        "RGB suffixes",
        {PurePosixPath(info.filename).suffix for info in groups["RGB"]},
        {".JPG"},
    )
    require_equal(
        "mask suffixes",
        {PurePosixPath(info.filename).suffix for info in groups["Masks"]},
        {".png"},
    )
    require_equal(
        "MS suffixes",
        {PurePosixPath(info.filename).suffix for info in groups["Multispectral"]},
        {".TIF"},
    )
    return groups


def convert(gate_path: Path) -> tuple[Path, Path]:
    gate_path = gate_path.expanduser().resolve()
    project_root = gate_path.parents[2]
    gate = load_yaml(gate_path)
    require_equal("schema_version", gate.get("schema_version"), 1)
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    locked = validate_locked_inputs(gate, project_root)
    acquisition = load_json(locked["acquisition_receipt"])
    require_equal("acquisition status", acquisition.get("status"), "verified")
    require_equal("acquisition config SHA", acquisition.get("config_sha256"), gate["locked_inputs"]["acquisition_config"]["sha256"])
    require_equal("acquisition auditor SHA", acquisition.get("script_sha256"), gate["locked_inputs"]["archive_auditor"]["sha256"])
    require_equal("nested CRC", acquisition["nested_archive"]["full_crc_passed"], True)
    nested_path = locked["nested_archive"]
    require_equal("nested archive path", Path(acquisition["nested_archive"]["path"]).resolve(), nested_path)
    require_equal("nested archive SHA", sha256(nested_path), acquisition["nested_archive"]["sha256"])

    split = load_yaml(locked["split_protocol"])
    require_equal("split dataset", split["dataset_id"], gate["dataset_id"])
    events = {
        (str(event["date"]), str(event["location"])): event
        for event in split["expected_capture_events"]
    }
    require_equal("split event uniqueness", len(events), len(split["expected_capture_events"]))
    date_events = {date: (location, event) for (date, location), event in events.items()}
    require_equal("unique event dates", len(date_events), len(events))

    expected = gate["expected_release"]
    outputs = gate["outputs"]
    repository = require_inside(data_root / str(outputs["repository_subset"]), data_root, "repository subset")
    normalized_root = require_inside(data_root / str(outputs["normalized_partial_masks"]), data_root, "normalized masks")
    reserve = int(load_yaml(locked["acquisition_config"])["quality_gate"]["minimum_free_space_after_archive_and_nested_bytes"])

    with ZipFile(nested_path) as archive:
        groups = expected_member_groups(archive, expected)
        mapping_name = f"{SOURCE_ROOT}/Metadata/filename_mapping.csv"
        metadata_name = f"{SOURCE_ROOT}/Metadata/image_metadata.csv"
        mapping_columns, mapping_rows = csv_member(archive, mapping_name)
        metadata_columns, metadata_rows = csv_member(archive, metadata_name)
        require_equal("filename mapping columns", mapping_columns, list(expected["filename_mapping_columns"]))
        require_equal("image metadata columns", metadata_columns, list(expected["image_metadata_columns"]))
        require_equal("filename mapping rows", len(mapping_rows), int(expected["metadata_rows"]))
        require_equal("image metadata rows", len(metadata_rows), int(expected["metadata_rows"]))
        mapping_by_original = unique_index(mapping_rows, "original_filename", "filename_mapping.csv")
        metadata_by_original = unique_index(metadata_rows, "original_filename", "image_metadata.csv")
        require_equal("metadata primary-key set", set(metadata_by_original), set(mapping_by_original))
        standardized = [row["standardized_filename"] for row in mapping_rows]
        require_equal("standardized filename uniqueness", len(set(standardized)), len(standardized))
        release_modal_names = {
            PurePosixPath(info.filename).name
            for key in ("RGB", "Multispectral")
            for info in groups[key]
        }
        require_equal("mapping to released RGB/MS files", set(standardized), release_modal_names)
        standard_to_original = {
            row["standardized_filename"]: row["original_filename"] for row in mapping_rows
        }
        require_equal(
            "sensor counts",
            dict(Counter(row["sensor_type"] for row in metadata_rows)),
            dict(expected["sensor_counts"]),
        )
        require_equal(
            "camera counts",
            dict(Counter(row["camera_model"] for row in metadata_rows)),
            dict(expected["camera_counts"]),
        )
        require_equal(
            "MS band counts",
            dict(Counter(row["band"] for row in metadata_rows if row["sensor_type"] == "MS")),
            dict(expected["multispectral_band_counts"]),
        )

        rgb_by_stem = {PurePosixPath(info.filename).stem: info for info in groups["RGB"]}
        mask_by_stem = {PurePosixPath(info.filename).stem: info for info in groups["Masks"]}
        overlay_stems = {PurePosixPath(info.filename).stem for info in groups["Overlay"]}
        require_equal("RGB/mask stem pairing", set(rgb_by_stem), set(mask_by_stem))
        require_equal("RGB/overlay stem pairing", set(rgb_by_stem), overlay_stems)
        ms_counts: Counter[str] = Counter()
        ms_parent_stems: Counter[str] = Counter()
        for info in groups["Multispectral"]:
            stem = PurePosixPath(info.filename).stem
            for band in ("NIR", "RE", "G", "R"):
                suffix = "_" + band
                if stem.endswith(suffix):
                    ms_counts[band] += 1
                    ms_parent_stems[stem[: -len(suffix)]] += 1
                    break
            else:
                raise ValueError(f"Unexpected multispectral band name: {info.filename}")
        require_equal("MS files per RGB", set(ms_parent_stems), set(rgb_by_stem))
        require_equal("four MS files per RGB", set(ms_parent_stems.values()), {4})
        require_equal("MS band suffix counts", dict(ms_counts), {"G": 734, "NIR": 734, "R": 734, "RE": 734})

        publisher_sets: dict[str, set[str]] = {}
        publisher_event_counts: dict[str, dict[str, int]] = {}
        for filename, count in expected["publisher_split_lists"].items():
            rows = [
                line.strip()
                for line in archive.read(f"{SOURCE_ROOT}/{filename}").decode("utf-8-sig").splitlines()
                if line.strip()
            ]
            require_equal(f"{filename} rows", len(rows), int(count))
            require_equal(f"{filename} uniqueness", len(set(rows)), len(rows))
            publisher_sets[filename] = set(rows)
            publisher_event_counts[filename] = dict(
                sorted(Counter(str(parse_rgb_filename(name)["date"]) for name in rows).items())
            )
        require_equal("publisher split union", set().union(*publisher_sets.values()), {PurePosixPath(info.filename).name for info in groups["RGB"]})
        for left, left_values in publisher_sets.items():
            for right, right_values in publisher_sets.items():
                if left < right:
                    require_equal(f"publisher split overlap {left}/{right}", len(left_values & right_values), 0)
        require_equal(
            "publisher split capture events",
            publisher_event_counts,
            {name: dict(values) for name, values in expected["publisher_split_capture_event_counts"].items()},
        )
        if any(len(counts) != len(events) for counts in publisher_event_counts.values()):
            raise ValueError("Publisher split leakage evidence changed")

        selected_infos = {
            info.filename: info
            for key in ("RGB", "Masks", "Metadata", "root")
            for info in groups[key]
        }
        estimated_output = sum(info.file_size for info in selected_infos.values()) + len(groups["Masks"]) * 1280 * 960
        free_before = shutil.disk_usage(data_root).free
        if free_before - estimated_output < reserve:
            raise OSError(f"Insufficient data-disk reserve: free={free_before}, estimate={estimated_output}, reserve={reserve}")

        expected_repository_files: set[Path] = set()
        for name, info in sorted(selected_infos.items()):
            member_path = PurePosixPath(name)
            destination = require_inside(repository / Path(*member_path.parts[1:]), data_root, "repository member")
            write_exact(destination, archive.read(info))
            expected_repository_files.add(destination.resolve())
        actual_repository_files = {path.resolve() for path in repository.rglob("*") if path.is_file()}
        require_equal("repository subset exact file set", actual_repository_files, expected_repository_files)

        records: list[SampleRecord] = []
        coverages: list[float] = []
        coverage_counts: Counter[str] = Counter()
        event_counts: Counter[str] = Counter()
        mask_palettes: Counter[tuple[int, ...]] = Counter()
        rgb_modes: Counter[str] = Counter()
        mask_modes: Counter[str] = Counter()
        normalized_paths: set[Path] = set()
        altitude_values: list[float] = []
        latitude_values: list[float] = []
        longitude_values: list[float] = []
        time_values: list[str] = []
        positive_pixels = 0
        negative_pixels = 0

        for stem, rgb_info in sorted(rgb_by_stem.items()):
            rgb_name = PurePosixPath(rgb_info.filename).name
            parsed = parse_rgb_filename(rgb_name)
            original = standard_to_original[rgb_name]
            metadata = metadata_by_original[original]
            require_equal(f"RGB sensor {rgb_name}", metadata["sensor_type"], "RGB")
            require_equal(f"RGB camera {rgb_name}", metadata["camera_model"], "FC6520")
            require_equal(f"RGB band {rgb_name}", metadata["band"], "")
            require_equal(f"RGB date {rgb_name}", metadata["acquisition_date"], parsed["date"])
            require_equal(f"RGB minute {rgb_name}", metadata["time"][:5], parsed["hour_minute"])
            for field in ("latitude", "longitude"):
                if abs(float(metadata[field]) - float(parsed[field])) > 1e-7:
                    raise ValueError(f"Filename/metadata {field} mismatch: {rgb_name}")
            metadata_altitude = float(metadata["altitude"].removesuffix("m"))
            if abs(metadata_altitude - float(parsed["altitude"])) > 1e-6:
                raise ValueError(f"Filename/metadata altitude mismatch: {rgb_name}")
            date = str(parsed["date"])
            if date not in date_events:
                raise ValueError(f"Unknown capture event date: {date}")
            location, event = date_events[date]
            event_key = f"{date}|{location}"
            event_counts[event_key] += 1
            role = str(event["role"])
            if role not in {"train_candidate", "external_calibration"}:
                raise ValueError(f"Forbidden capture role: {role}")
            manifest_split = "train" if role == "train_candidate" else role

            rgb_payload = archive.read(rgb_info)
            with Image.open(io.BytesIO(rgb_payload)) as image:
                require_equal(f"RGB format {rgb_name}", image.format, expected["rgb_format"])
                require_equal(f"RGB size {rgb_name}", list(image.size), list(expected["rgb_size"]))
                rgb_modes[image.mode] += 1
                image.verify()
            mask_info = mask_by_stem[stem]
            mask_payload = archive.read(mask_info)
            with Image.open(io.BytesIO(mask_payload)) as image:
                require_equal(f"mask format {stem}", image.format, expected["mask_format"])
                require_equal(f"mask size {stem}", list(image.size), list(expected["mask_size"]))
                mask_modes[image.mode] += 1
                source_mask = np.asarray(image, dtype=np.uint8)
            values = tuple(int(value) for value in np.unique(source_mask))
            mask_palettes[values] += 1
            require_equal(f"mask palette {stem}", set(values), set(expected["mask_values"]))
            fraction = float(np.count_nonzero(source_mask == 255) / source_mask.size)
            if not 0 < fraction < float(gate["quality_gate"]["require_mask_coverage_below"]):
                raise ValueError(f"Forbidden source mask coverage {fraction}: {stem}")
            coverages.append(fraction)
            coverage_counts[coverage_bin(fraction)] += 1
            positive_pixels += int(np.count_nonzero(source_mask == 255))
            negative_pixels += int(np.count_nonzero(source_mask == 0))

            session_id = f"{location.lower()}_{date.replace('-', '_')}_uav_flight"
            normalized_path = normalized_root / manifest_split / session_id / f"{stem}.png"
            write_exact(normalized_path, normalized_mask_png(source_mask))
            normalized_paths.add(normalized_path.resolve())
            source_image_path = repository / "RGB" / rgb_name
            record = SampleRecord(
                sample_id=f"weedy_rice_uav:{stem}",
                image_path=relative(source_image_path, data_root),
                mask_path=relative(normalized_path, data_root),
                split=manifest_split,
                dataset_id=str(gate["manifest_dataset_id"]),
                field_id=f"an_giang_{location.lower()}",
                session_id=session_id,
                capture_date=date,
                platform=str(gate["capture"]["platform"]),
                sensor=str(gate["capture"]["sensor"]),
                target_crop_id=int(gate["capture"]["target_crop_id"]),
                crop_species=str(gate["capture"]["crop_species"]).replace("_", " "),
                weed_species_optional=str(gate["capture"]["weed_species"]).replace("_", " "),
                growth_stage=str(gate["capture"]["growth_stage"]),
                annotation_exhaustive=False,
                license_status=str(gate["license"]["status"]),
                commercial_allowed=bool(gate["license"]["commercial_allowed"]),
            )
            records.append(record)
            altitude_values.append(metadata_altitude)
            latitude_values.append(float(metadata["latitude"]))
            longitude_values.append(float(metadata["longitude"]))
            time_values.append(metadata["time"])

    require_equal("sample count", len(records), int(expected["rgb_images"]))
    require_equal("capture event counts", dict(sorted(event_counts.items())), {str(key): int(value) for key, value in gate["expected_capture_events"].items()})
    expected_bins = {
        key: int(value)
        for key, value in gate["expected_mask_coverage_bins"].items()
        if key not in {"mean_percent_reference", "mean_percent_absolute_tolerance"}
    }
    require_equal("coverage bins", dict(coverage_counts), expected_bins)
    mean_percent = statistics.fmean(coverages) * 100
    if abs(mean_percent - float(gate["expected_mask_coverage_bins"]["mean_percent_reference"])) > float(gate["expected_mask_coverage_bins"]["mean_percent_absolute_tolerance"]):
        raise ValueError(f"Mean coverage differs from publication: {mean_percent}")
    require_equal("normalized mask file set", {path.resolve() for path in normalized_root.rglob("*.png")}, normalized_paths)

    train = [record for record in records if record.split == "train"]
    calibration = [record for record in records if record.split == "external_calibration"]
    require_equal("train-candidate rows", len(train), int(split["expected_totals"]["train_candidate"]))
    require_equal("calibration rows", len(calibration), int(split["expected_totals"]["external_calibration"]))
    require_equal("capture groups", len({record.group_id for record in records}), 4)
    require_equal("train/calibration group overlap", len({record.group_id for record in train} & {record.group_id for record in calibration}), 0)

    output_paths = {
        "binary_manifest": data_root / str(outputs["binary_manifest"]),
        "train_candidate_manifest": data_root / str(outputs["train_candidate_manifest"]),
        "external_calibration_manifest": data_root / str(outputs["external_calibration_manifest"]),
    }
    write_manifest(records, output_paths["binary_manifest"])
    write_manifest(train, output_paths["train_candidate_manifest"])
    write_manifest(calibration, output_paths["external_calibration_manifest"])
    derived = {
        name: {"path": str(path.resolve()), "sha256": manifest_sha256(path)}
        for name, path in output_paths.items()
    }
    derived.update(
        {
            "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
            "calibration_mask_tree_sha256": mask_tree_sha256(calibration, data_root),
            "image_tree_sha256": image_tree_sha256(records, data_root),
            "calibration_image_tree_sha256": image_tree_sha256(calibration, data_root),
            "repository_subset_tree_sha256": tree_sha256(expected_repository_files, data_root),
        }
    )
    common = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": str(gate["manifest_dataset_id"]),
        "gate_config": str(gate_path),
        "gate_config_sha256": sha256(gate_path),
        "split_protocol": str(locked["split_protocol"]),
        "split_protocol_sha256": sha256(locked["split_protocol"]),
        "acquisition_receipt": str(locked["acquisition_receipt"]),
        "acquisition_receipt_sha256": sha256(locked["acquisition_receipt"]),
        "nested_archive": str(nested_path),
        "nested_archive_sha256": sha256(nested_path),
        "converter": str(Path(__file__).resolve()),
        "converter_sha256": sha256(Path(__file__).resolve()),
        "samples": len(records),
        "split_counts": dict(Counter(record.split for record in records)),
        "field_count": len({record.field_id for record in records}),
        "capture_group_count": len({record.group_id for record in records}),
        "capture_event_counts": dict(sorted(event_counts.items())),
        "derived": derived,
        "external_test_used": False,
        "model_selection_used": False,
        "common_model_training_allowed": False,
    }
    content_audit = {
        **common,
        "role": "automated_content_quality_audit",
        "automated_content_gate_passed": True,
        "all_quality_gates_passed": False,
        "pending_gates": ["exact_and_near_duplicate_audit", "manual_contact_sheet_review"],
        "release_inventory": {
            "files": int(expected["total_files"]),
            "rgb": len(records),
            "masks": len(records),
            "multispectral": int(expected["multispectral_images"]),
            "overlays": int(expected["overlays"]),
            "metadata_rows": int(expected["metadata_rows"]),
        },
        "publisher_split_rejected": {
            "counts": {name: len(values) for name, values in publisher_sets.items()},
            "capture_event_counts": publisher_event_counts,
            "every_role_contains_every_capture_event": True,
            "used_for_manifest_roles": False,
            "reason": "70_percent_overlapping_adjacent_frames_cross_all_publisher_roles",
        },
        "metadata": {
            "rgb_camera_modes": dict(rgb_modes),
            "mask_modes": dict(mask_modes),
            "altitude_m": {"min": min(altitude_values), "max": max(altitude_values)},
            "latitude": {"min": min(latitude_values), "max": max(latitude_values)},
            "longitude": {"min": min(longitude_values), "max": max(longitude_values)},
            "time_local": {"min": min(time_values), "max": max(time_values)},
            "article_reported_time_local": gate["capture"]["reported_flight_time_local"],
            "article_metadata_time_discrepancy": min(time_values) < str(gate["capture"]["reported_flight_time_local"][0]),
        },
        "source_masks": {
            "palettes": {str(key): value for key, value in mask_palettes.items()},
            "positive_pixels": positive_pixels,
            "negative_pixels": negative_pixels,
            "coverage_fraction": {
                "min": min(coverages),
                "mean": statistics.fmean(coverages),
                "median": statistics.median(coverages),
                "max": max(coverages),
            },
            "coverage_bins": dict(coverage_counts),
        },
        "ontology": {
            "source_255": "common_other_vegetation_2",
            "source_0": "common_ignore_255",
            "annotation_exhaustive": False,
            "source_zero_used_as_common_background_or_crop": False,
            "binary_diagnostic_negative_definition": "source_zero_not_annotated_as_weedy_rice",
        },
        "disk": {
            "free_bytes_before_conversion": free_before,
            "free_bytes_after_conversion": shutil.disk_usage(data_root).free,
            "minimum_reserve_bytes": reserve,
        },
    }
    content_path = require_inside(data_root / str(outputs["content_audit"]), data_root, "content audit")
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(json.dumps(content_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    conversion = {
        **common,
        "role": "source_preserving_partial_label_conversion",
        "repository_subset": str(repository),
        "repository_files": len(expected_repository_files),
        "source_bytes_preserved": True,
        "multispectral_extracted": False,
        "overlay_extracted": False,
        "normalized_partial_masks": str(normalized_root),
        "normalized_partial_mask_files": len(normalized_paths),
        "content_audit": str(content_path),
        "content_audit_sha256": sha256(content_path),
    }
    receipt_path = require_inside(data_root / str(outputs["conversion_receipt"]), data_root, "conversion receipt")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(conversion, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_path, content_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config",
        type=Path,
        default=Path("configs/data/weedy_rice_uav_real_gate_v1.yaml"),
    )
    arguments = parser.parse_args()
    receipt, audit = convert(arguments.gate_config)
    print(
        json.dumps(
            {
                "conversion_receipt": str(receipt),
                "conversion_receipt_sha256": sha256(receipt),
                "content_audit": str(audit),
                "content_audit_sha256": sha256(audit),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
