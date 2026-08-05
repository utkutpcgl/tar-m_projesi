#!/usr/bin/env python3
"""Fail-closed structural and condition audit for the pinned RiceSEG release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile, ZipInfo

import numpy as np
import yaml
from PIL import Image


RASTER_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
PAIR_SUFFIX = re.compile(
    r"(?:[_\-.](?:mask|masks|label|labels|annotation|annot|rgb|image|img))+$",
    flags=re.IGNORECASE,
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


def safe_members(archive: ZipFile, label: str) -> list[ZipInfo]:
    members = archive.infolist()
    unsafe: list[str] = []
    links: list[str] = []
    duplicate_names: list[str] = []
    seen: set[str] = set()
    for member in members:
        name = member.filename
        candidate = PurePosixPath(name)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in name:
            unsafe.append(name)
        file_type = (member.external_attr >> 16) & 0o170000
        if file_type == 0o120000:
            links.append(name)
        if name in seen:
            duplicate_names.append(name)
        seen.add(name)
    if unsafe or links or duplicate_names:
        raise ValueError(
            f"Unsafe {label}: paths={unsafe[:5]}, symlinks={links[:5]}, "
            f"duplicate_names={duplicate_names[:5]}"
        )
    return members


def validate_metadata(gate: dict[str, Any]) -> dict[str, Any]:
    require_equal("schema_version", gate.get("schema_version"), 1)
    freeze = gate["freeze"]
    for name in (
        "frozen_before_archive_content_inspection",
        "frozen_before_mask_visual_review",
        "frozen_before_model_evaluation",
    ):
        require_equal(name, freeze.get(name), True)
    require_equal("publisher random split", freeze.get("publisher_random_split_used"), False)
    require_equal("external test created", freeze.get("external_test_created"), False)

    expected_samples = int(gate["release_contract"]["expected_samples"])
    subdatasets = gate["subdatasets"]
    if not isinstance(subdatasets, dict) or not subdatasets:
        raise ValueError("subdatasets must be a non-empty mapping")
    expected_by_subdataset = {
        str(name): int(specification["images"])
        for name, specification in subdatasets.items()
    }
    require_equal(
        "subdataset image total", sum(expected_by_subdataset.values()), expected_samples
    )
    require_equal("subdataset count", len(expected_by_subdataset), 19)

    aliases: dict[str, str] = {}
    for name, specification in subdatasets.items():
        recorded_aliases = specification.get("aliases")
        if not isinstance(recorded_aliases, list) or not recorded_aliases:
            raise ValueError(f"Missing aliases for {name}")
        for alias in recorded_aliases:
            normalized = str(alias).upper()
            owner = aliases.setdefault(normalized, str(name))
            if owner != name:
                raise ValueError(f"Alias {alias!r} is shared by {owner} and {name}")

    mapping = {int(raw): int(common) for raw, common in gate["ontology"]["common_mapping"].items()}
    require_equal("common mapping", mapping, {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 2})
    require_equal("target crop id", int(gate["ontology"]["target_crop_id"]), 12)
    require_equal("annotation exhaustive", gate["ontology"]["annotation_exhaustive"], True)

    roles = Counter()
    role_groups: dict[str, set[str]] = {}
    for name, specification in subdatasets.items():
        role = str(specification["coverage_role"])
        if role not in {"train", "external_calibration"}:
            raise ValueError(f"Unsupported coverage role for {name}: {role}")
        roles[role] += int(specification["images"])
        role_groups.setdefault(role, set()).add(str(name))
    expected_roles = {
        str(role): int(count)
        for role, count in gate["split_protocols"]["coverage_training"]["expected_roles"].items()
    }
    require_equal("coverage role counts", dict(roles), expected_roles)
    require_equal(
        "coverage holdout groups",
        role_groups.get("external_calibration", set()),
        set(gate["split_protocols"]["coverage_training"]["holdout_subdatasets"]),
    )

    transfer = gate["split_protocols"]["country_transfer_diagnostic"]
    source_countries = {str(value) for value in transfer["source_countries"]}
    target_countries = {str(value) for value in transfer["target_countries"]}
    require_equal("country-transfer country overlap", source_countries & target_countries, set())
    source_images = sum(
        int(specification["images"])
        for specification in subdatasets.values()
        if str(specification["country"]) in source_countries
    )
    target_images = sum(
        int(specification["images"])
        for specification in subdatasets.values()
        if str(specification["country"]) in target_countries
    )
    require_equal("country-transfer source images", source_images, int(transfer["expected_source_images"]))
    require_equal("country-transfer target images", target_images, int(transfer["expected_target_images"]))
    require_equal("country-transfer total", source_images + target_images, expected_samples)

    return {
        "expected_samples": expected_samples,
        "subdatasets": len(expected_by_subdataset),
        "expected_by_subdataset": expected_by_subdataset,
        "coverage_roles": dict(roles),
        "country_transfer": {"source": source_images, "target": target_images},
    }


def infer_subdataset(member_name: str, subdatasets: dict[str, Any]) -> str:
    normalized = member_name.upper().replace("\\", "/")
    matches: list[tuple[int, str, str]] = []
    for name, specification in subdatasets.items():
        for alias in specification["aliases"]:
            candidate = str(alias).upper()
            pattern = rf"(?<![A-Z0-9]){re.escape(candidate)}(?![A-Z0-9])"
            if re.search(pattern, normalized):
                matches.append((len(candidate), str(name), candidate))
    owners = {name for _, name, _ in matches}
    if not matches:
        raise ValueError(f"Cannot infer RiceSEG subdataset from member: {member_name}")
    if len(owners) != 1:
        raise ValueError(f"Ambiguous RiceSEG subdataset for {member_name}: {sorted(owners)}")
    return max(matches)[1]


def canonical_pair_key(member_name: str, subdataset: str) -> str:
    path = PurePosixPath(member_name)
    stem = PAIR_SUFFIX.sub("", path.stem).strip("_.-").lower()
    if not stem:
        raise ValueError(f"Empty pair key for archive member: {member_name}")
    return f"{subdataset}/{stem}"


def raster_members(archive: ZipFile, label: str) -> list[ZipInfo]:
    members = safe_members(archive, label)
    return [
        member
        for member in members
        if not member.is_dir()
        and PurePosixPath(member.filename).suffix.lower() in RASTER_SUFFIXES
    ]


def inspect_raster_archive(
    path: Path,
    *,
    kind: str,
    subdatasets: dict[str, Any],
    expected_count: int,
    expected_size: tuple[int, int],
    parent_directory: str | None = None,
    allowed_mask_values: set[int] | None = None,
    verify_crc: bool = True,
) -> dict[str, Any]:
    if kind not in {"rgb", "mask"}:
        raise ValueError(f"Unsupported raster archive kind: {kind}")
    if not path.is_file():
        raise FileNotFoundError(path)
    subgroup_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    class_pixels: Counter[int] = Counter()
    pair_members: dict[str, str] = {}
    with ZipFile(path) as archive:
        rasters = raster_members(archive, str(path))
        if parent_directory is not None:
            rasters = [
                member
                for member in rasters
                if PurePosixPath(member.filename).parent.name == parent_directory
            ]
        require_equal(f"{kind} raster count", len(rasters), expected_count)
        for member in rasters:
            subdataset = infer_subdataset(member.filename, subdatasets)
            subgroup_counts[subdataset] += 1
            suffix_counts[PurePosixPath(member.filename).suffix.lower()] += 1
            key = canonical_pair_key(member.filename, subdataset)
            if key in pair_members:
                raise ValueError(
                    f"Duplicate canonical {kind} pair key {key}: "
                    f"{pair_members[key]!r}, {member.filename!r}"
                )
            pair_members[key] = member.filename
            with archive.open(member) as handle, Image.open(handle) as image:
                image.load()
                require_equal(f"{kind} size {member.filename}", image.size, expected_size)
                mode_counts[image.mode] += 1
                format_counts[str(image.format)] += 1
                if kind == "rgb":
                    if image.mode not in {"RGB", "RGBA"}:
                        raise ValueError(
                            f"Unexpected RiceSEG RGB mode {image.mode}: {member.filename}"
                        )
                    if image.mode == "RGBA":
                        alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
                        if not np.all(alpha == 255):
                            raise ValueError(f"Non-opaque RiceSEG RGB: {member.filename}")
                else:
                    array = np.asarray(image)
                    if array.ndim != 2:
                        raise ValueError(
                            f"RiceSEG mask is not single-channel: {member.filename}, "
                            f"shape={array.shape}, mode={image.mode}"
                        )
                    values, counts = np.unique(array, return_counts=True)
                    integer_values = {int(value) for value in values.tolist()}
                    if allowed_mask_values is None:
                        raise ValueError("allowed_mask_values is required for mask inspection")
                    unexpected = integer_values - allowed_mask_values
                    if unexpected:
                        raise ValueError(
                            f"Unexpected RiceSEG mask values {sorted(unexpected)}: {member.filename}"
                        )
                    class_pixels.update(
                        {int(value): int(count) for value, count in zip(values, counts, strict=True)}
                    )
        if verify_crc:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f"Archive CRC failure in {path}: {bad_member}")

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rasters": len(pair_members),
        "pair_members": pair_members,
        "subdataset_counts": dict(sorted(subgroup_counts.items())),
        "modes": dict(sorted(mode_counts.items())),
        "formats": dict(sorted(format_counts.items())),
        "suffixes": dict(sorted(suffix_counts.items())),
        "class_pixels": {str(key): value for key, value in sorted(class_pixels.items())},
    }


def inspect_paired_archive_layout(
    path: Path,
    *,
    expected_root: str,
    rgb_directory: str,
    mask_directory: str,
    expected_files: int,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    parent_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    with ZipFile(path) as archive:
        files = [
            member
            for member in safe_members(archive, str(path))
            if not member.is_dir()
        ]
        require_equal("paired archive file count", len(files), expected_files)
        for member in files:
            candidate = PurePosixPath(member.filename)
            if not candidate.parts or candidate.parts[0] != expected_root:
                raise ValueError(f"File outside paired release root: {member.filename}")
            if candidate.parent.name not in {rgb_directory, mask_directory}:
                raise ValueError(f"Unexpected paired release directory: {member.filename}")
            if candidate.suffix.lower() not in RASTER_SUFFIXES:
                raise ValueError(f"Unexpected paired release payload: {member.filename}")
            parent_counts[candidate.parent.name] += 1
            suffix_counts[candidate.suffix.lower()] += 1
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Archive CRC failure in {path}: {bad_member}")
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "files": expected_files,
        "parent_counts": dict(sorted(parent_counts.items())),
        "suffixes": dict(sorted(suffix_counts.items())),
        "safe_paths": True,
        "symlinks": 0,
        "duplicate_names": 0,
        "full_crc_passed": True,
    }


def inspect_original_archive(
    path: Path,
    *,
    expected_count: int,
    expected_directory_counts: dict[str, int],
    expected_modes: dict[str, int],
    expected_formats: dict[str, int],
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    directories: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    basenames: set[str] = set()
    with ZipFile(path) as archive:
        rasters = raster_members(archive, str(path))
        require_equal("original raster count", len(rasters), expected_count)
        for member in rasters:
            candidate = PurePosixPath(member.filename)
            directories[candidate.parent.name] += 1
            normalized_basename = candidate.name.lower()
            if normalized_basename in basenames:
                raise ValueError(f"Duplicate original basename: {candidate.name}")
            basenames.add(normalized_basename)
            with archive.open(member) as handle, Image.open(handle) as image:
                image.load()
                modes[image.mode] += 1
                formats[str(image.format)] += 1
                sizes[f"{image.width}x{image.height}"] += 1
                if image.mode != "RGB":
                    raise ValueError(
                        f"Unexpected original RiceSEG mode {image.mode}: {member.filename}"
                    )
        # Every archive file is a decoded raster, so ZipExtFile has verified
        # each payload CRC while the acquisition receipt independently locks
        # the archive-wide testzip result.
    require_equal("original directory counts", dict(directories), expected_directory_counts)
    require_equal("original mode counts", dict(modes), expected_modes)
    require_equal("original format counts", dict(formats), expected_formats)
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rasters": expected_count,
        "directories": dict(sorted(directories.items())),
        "modes": dict(sorted(modes.items())),
        "formats": dict(sorted(formats.items())),
        "sizes": dict(sorted(sizes.items())),
        "basenames": basenames,
        "all_payloads_decoded": True,
        "payload_crc_verified_during_decode": True,
    }


def xlsx_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    workbook_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_relationship_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    with ZipFile(path) as archive:
        names = {member.filename for member in safe_members(archive, str(path)) if not member.is_dir()}
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        missing = required - names
        if missing:
            raise ValueError(f"Invalid XLSX {path}; missing {sorted(missing)}")
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            element.attrib["Id"]: element.attrib["Target"]
            for element in relationships.findall(f"{{{package_relationship_namespace}}}Relationship")
        }
        sheets: list[dict[str, Any]] = []
        for sheet in workbook.findall(f".//{{{workbook_namespace}}}sheet"):
            relationship_id = sheet.attrib[f"{{{relationship_namespace}}}id"]
            target = targets[relationship_id].lstrip("/")
            worksheet_path = target if target.startswith("xl/") else f"xl/{target}"
            if worksheet_path not in names:
                raise ValueError(f"Missing XLSX worksheet {worksheet_path} in {path}")
            root = ElementTree.fromstring(archive.read(worksheet_path))
            rows = root.findall(f".//{{{workbook_namespace}}}row")
            cells = root.findall(f".//{{{workbook_namespace}}}c")
            sheets.append(
                {
                    "name": sheet.attrib["name"],
                    "worksheet": worksheet_path,
                    "rows": len(rows),
                    "cells": len(cells),
                }
            )
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"XLSX CRC failure in {path}: {bad_member}")
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "sheets": sheets,
    }


def xlsx_column_index(cell_reference: str) -> int:
    match = re.match(r"[A-Z]+", cell_reference.upper())
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {cell_reference}")
    result = 0
    for character in match.group(0):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def first_worksheet_rows(path: Path) -> list[list[str]]:
    workbook_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    namespace = f"{{{workbook_namespace}}}"
    with ZipFile(path) as archive:
        names = {member.filename for member in safe_members(archive, str(path))}
        worksheet_path = "xl/worksheets/sheet1.xml"
        if worksheet_path not in names:
            raise ValueError(f"Missing first worksheet in {path}")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{namespace}t"))
                for item in root.findall(f"{namespace}si")
            ]
        worksheet = ElementTree.fromstring(archive.read(worksheet_path))
        rows: list[list[str]] = []
        for row in worksheet.findall(f".//{namespace}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{namespace}c"):
                index = xlsx_column_index(cell.attrib["r"])
                cell_type = cell.attrib.get("t")
                raw = cell.find(f"{namespace}v")
                if cell_type == "inlineStr":
                    inline = cell.find(f"{namespace}is")
                    value = (
                        "".join(
                            node.text or "" for node in inline.iter(f"{namespace}t")
                        )
                        if inline is not None
                        else ""
                    )
                elif raw is None or raw.text is None:
                    value = ""
                elif cell_type == "s":
                    value = shared[int(raw.text)]
                elif cell_type == "b":
                    value = "true" if int(raw.text) else "false"
                else:
                    value = raw.text
                values[index] = value
            width = max(values, default=-1) + 1
            recorded = [values.get(index, "") for index in range(width)]
            while recorded and recorded[-1] == "":
                recorded.pop()
            rows.append(recorded)
    return rows


def validate_class_pixel_workbook(
    path: Path,
    *,
    expected_rows: int,
    expected_mask_stems: set[str],
    expected_class_pixels: dict[int, int],
    expected_pixels_per_mask: int,
) -> dict[str, Any]:
    summary = xlsx_summary(path)
    rows = first_worksheet_rows(path)
    require_equal("class workbook rows", len(rows), expected_rows)
    expected_header = [
        "country",
        "province",
        "image",
        "class_0",
        "class_1",
        "class_2",
        "class_3",
        "class_4",
        "class_5",
    ]
    require_equal("class workbook header", rows[0], expected_header)
    stems: set[str] = set()
    aggregate: Counter[int] = Counter()
    for row_number, recorded in enumerate(rows[1:], start=2):
        row = recorded + [""] * (len(expected_header) - len(recorded))
        require_equal(f"class workbook width row {row_number}", len(row), len(expected_header))
        if not row[2]:
            raise ValueError(f"Missing mask path in class workbook row {row_number}")
        stem = PurePosixPath(row[2].replace("\\", "/")).stem.lower()
        if stem in stems:
            raise ValueError(f"Duplicate mask stem in class workbook: {stem}")
        stems.add(stem)
        try:
            counts = [int(value) for value in row[3:9]]
        except ValueError as exc:
            raise ValueError(f"Invalid class count in workbook row {row_number}") from exc
        require_equal(
            f"class workbook pixel total row {row_number}",
            sum(counts),
            expected_pixels_per_mask,
        )
        aggregate.update({raw: count for raw, count in enumerate(counts)})
    require_equal("class workbook mask stems", stems, expected_mask_stems)
    require_equal("class workbook aggregate pixels", dict(aggregate), expected_class_pixels)
    summary.update(
        {
            "validated_data_rows": len(rows) - 1,
            "unique_mask_stems": len(stems),
            "aggregate_class_pixels": {
                str(raw): count for raw, count in sorted(aggregate.items())
            },
            "matches_decoded_masks": True,
        }
    )
    return summary


def validate_crop_mapping_workbook(
    path: Path,
    *,
    expected_rows: int,
    expected_rows_with_crop: int,
    expected_rows_without_crop: int,
    expected_rgb_stems: set[str],
) -> dict[str, Any]:
    summary = xlsx_summary(path)
    rows = first_worksheet_rows(path)
    require_equal("crop mapping rows", len(rows), expected_rows)
    expected_header = ["country", "province", "original_name", "crop_name", "x0", "y0"]
    header = rows[0] + [""] * (len(expected_header) - len(rows[0]))
    require_equal("crop mapping header", header, expected_header)
    crop_stems: set[str] = set()
    original_names: set[str] = set()
    rows_without_crop = 0
    current_original = ""
    for row_number, recorded in enumerate(rows[1:], start=2):
        row = recorded + [""] * (len(expected_header) - len(recorded))
        if len(row) != len(expected_header):
            raise ValueError(f"Unexpected crop mapping width in row {row_number}: {len(row)}")
        if row[2]:
            current_original = row[2]
        if not row[3]:
            rows_without_crop += 1
            continue
        if not current_original:
            raise ValueError(f"Crop row has no original image in row {row_number}")
        stem = PurePosixPath(row[3]).stem.lower()
        if stem in crop_stems:
            raise ValueError(f"Duplicate crop stem in mapping workbook: {stem}")
        crop_stems.add(stem)
        original_names.add(PurePosixPath(current_original).name.lower())
        try:
            x0 = int(row[4])
            y0 = int(row[5])
        except ValueError as exc:
            raise ValueError(f"Invalid crop coordinates in workbook row {row_number}") from exc
        if x0 < 0 or y0 < 0:
            raise ValueError(f"Negative crop coordinates in workbook row {row_number}")
    require_equal("crop mapping rows with crop", len(crop_stems), expected_rows_with_crop)
    require_equal("crop mapping rows without crop", rows_without_crop, expected_rows_without_crop)
    require_equal("crop mapping RGB stems", crop_stems, expected_rgb_stems)
    summary.update(
        {
            "validated_rows_with_crop": len(crop_stems),
            "rows_without_crop": rows_without_crop,
            "unique_crop_stems": len(crop_stems),
            "unique_referenced_original_basenames": len(original_names),
            "referenced_original_basenames": original_names,
            "matches_paired_rgb": True,
        }
    )
    return summary


def condition_summary(gate: dict[str, Any]) -> dict[str, Any]:
    subdatasets = gate["subdatasets"]
    countries: Counter[str] = Counter()
    institutes: Counter[str] = Counter()
    sites: Counter[str] = Counter()
    years: Counter[str] = Counter()
    platforms: Counter[str] = Counter()
    sensors: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    for specification in subdatasets.values():
        images = int(specification["images"])
        countries[str(specification["country"])] += images
        institutes[str(specification["institute"])] += images
        sites[str(specification["site"])] += images
        years[str(specification["year"])] += images
        platforms[str(specification["platform"])] += images
        sensors[str(specification["sensor"])] += images
        for stage in specification["growth_stages"]:
            stages[str(stage)] += images
    return {
        "countries": dict(sorted(countries.items())),
        "institutes": dict(sorted(institutes.items())),
        "sites": dict(sorted(sites.items())),
        "years": dict(sorted(years.items())),
        "platforms": dict(sorted(platforms.items())),
        "sensors": dict(sorted(sensors.items())),
        "declared_growth_stage_memberships_nonexclusive": dict(sorted(stages.items())),
        "growth_stage_memberships_are_nonexclusive": True,
    }


def verify_locked_acquisition(
    gate: dict[str, Any], gate_path: Path
) -> tuple[Path, dict[str, Any]]:
    project_root = gate_path.parents[2]
    source = gate["source"]
    acquisition_config = resolve_project(project_root, str(source["acquisition_config"]["path"]))
    acquisition_script = resolve_project(project_root, str(source["acquisition_script"]["path"]))
    require_equal(
        "acquisition config SHA-256",
        sha256(acquisition_config),
        str(source["acquisition_config"]["sha256"]),
    )
    require_equal(
        "acquisition script SHA-256",
        sha256(acquisition_script),
        str(source["acquisition_script"]["sha256"]),
    )
    acquisition_gate = load_yaml(acquisition_config)
    data_root = Path(str(acquisition_gate["data_root"])).expanduser().resolve()
    receipt_path = require_inside(
        data_root / str(source["acquisition_receipt"]), data_root, "acquisition receipt"
    )
    receipt = load_json(receipt_path)
    require_equal("acquisition status", receipt.get("status"), "verified")
    require_equal("acquisition revision", receipt["source"]["revision"], source["revision"])
    require_equal(
        "receipt acquisition config SHA-256",
        receipt["config_sha256"],
        source["acquisition_config"]["sha256"],
    )
    require_equal(
        "receipt acquisition script SHA-256",
        receipt["script_sha256"],
        source["acquisition_script"]["sha256"],
    )
    require_equal("acquisition archive CRC", receipt["full_archive_crc_passed"], True)
    repository_dir = require_inside(
        data_root / str(source["repository_dir"]), data_root, "RiceSEG repository"
    )
    return repository_dir, receipt


def inspect_release(gate_path: Path) -> tuple[Path, Path]:
    gate_path = gate_path.expanduser().resolve()
    gate = load_yaml(gate_path)
    metadata = validate_metadata(gate)
    repository_dir, acquisition = verify_locked_acquisition(gate, gate_path)
    source = gate["source"]
    contract = gate["release_contract"]
    expected_count = int(contract["expected_samples"])
    expected_size = (int(contract["expected_width"]), int(contract["expected_height"]))
    subdatasets = gate["subdatasets"]
    paired_path = repository_dir / str(source["paired_archive"])
    paired_layout = inspect_paired_archive_layout(
        paired_path,
        expected_root=str(contract["paired_archive_root"]),
        rgb_directory=str(contract["rgb_directory"]),
        mask_directory=str(contract["mask_directory"]),
        expected_files=int(contract["expected_paired_archive_files"]),
    )
    rgb = inspect_raster_archive(
        paired_path,
        kind="rgb",
        subdatasets=subdatasets,
        expected_count=int(contract["expected_rgb_images"]),
        expected_size=expected_size,
        parent_directory=str(contract["rgb_directory"]),
        verify_crc=False,
    )
    masks = inspect_raster_archive(
        paired_path,
        kind="mask",
        subdatasets=subdatasets,
        expected_count=int(contract["expected_masks"]),
        expected_size=expected_size,
        parent_directory=str(contract["mask_directory"]),
        allowed_mask_values={int(value) for value in contract["require_source_mask_values_subset"]},
        verify_crc=False,
    )
    original = inspect_original_archive(
        repository_dir / str(source["original_archive"]),
        expected_count=int(contract["expected_original_images"]),
        expected_directory_counts={
            str(name): int(count)
            for name, count in contract["expected_original_directory_counts"].items()
        },
        expected_modes={
            str(name): int(count) for name, count in contract["expected_original_modes"].items()
        },
        expected_formats={
            str(name): int(count)
            for name, count in contract["expected_original_formats"].items()
        },
    )
    expected_by_subdataset = metadata["expected_by_subdataset"]
    require_equal("RGB subdataset counts", rgb["subdataset_counts"], expected_by_subdataset)
    require_equal("mask subdataset counts", masks["subdataset_counts"], expected_by_subdataset)
    rgb_members = rgb.pop("pair_members")
    mask_members = masks.pop("pair_members")
    rgb_keys = set(rgb_members)
    mask_keys = set(mask_members)
    require_equal("RGB/mask canonical pair keys", rgb_keys, mask_keys)
    require_equal("RGB/mask pair count", len(rgb_keys), expected_count)

    class_pixels = {int(key): int(value) for key, value in masks["class_pixels"].items()}
    require_equal(
        "global source mask values",
        set(class_pixels),
        {int(value) for value in contract["require_all_source_mask_values_globally"]},
    )
    total_pixels = sum(class_pixels.values())
    expected_total_pixels = expected_count * expected_size[0] * expected_size[1]
    require_equal("RiceSEG mask pixel total", total_pixels, expected_total_pixels)
    actual_percent = {
        value: count * 100.0 / total_pixels for value, count in sorted(class_pixels.items())
    }
    tolerance = float(contract["published_percent_absolute_tolerance"])
    for raw, published in contract["published_global_class_percent"].items():
        raw_value = int(raw)
        delta = abs(actual_percent[raw_value] - float(published))
        if delta > tolerance:
            raise ValueError(
                f"RiceSEG class {raw_value} published proportion mismatch: "
                f"actual={actual_percent[raw_value]:.6f}, published={float(published):.6f}, "
                f"tolerance={tolerance:.6f}"
            )

    rgb_stems = {
        PurePosixPath(member).stem.lower() for member in rgb_members.values()
    }
    mask_stems = {
        PurePosixPath(member).stem.lower() for member in mask_members.values()
    }
    require_equal("global RGB/mask stems", rgb_stems, mask_stems)
    class_workbook = validate_class_pixel_workbook(
        repository_dir / str(source["class_pixel_workbook"]),
        expected_rows=int(contract["expected_class_pixel_workbook_rows_including_header"]),
        expected_mask_stems=mask_stems,
        expected_class_pixels=class_pixels,
        expected_pixels_per_mask=expected_size[0] * expected_size[1],
    )
    crop_workbook = validate_crop_mapping_workbook(
        repository_dir / str(source["crop_mapping_workbook"]),
        expected_rows=int(contract["expected_crop_mapping_workbook_rows_including_header"]),
        expected_rows_with_crop=int(contract["expected_crop_mapping_rows_with_crop"]),
        expected_rows_without_crop=int(contract["expected_crop_mapping_rows_without_crop"]),
        expected_rgb_stems=rgb_stems,
    )
    original_basenames = original.pop("basenames")
    referenced_originals = crop_workbook.pop("referenced_original_basenames")
    original_mapping_overlap = original_basenames & referenced_originals
    workbooks = {
        "class_pixel_counts": class_workbook,
        "crop_mapping": crop_workbook,
        "original_mapping_relation": {
            "archive_unique_basenames": len(original_basenames),
            "mapping_unique_referenced_basenames": len(referenced_originals),
            "basename_overlap": len(original_mapping_overlap),
            "interpretation": (
                "original.zip is a partial parent-image provenance archive; "
                "the paired 512x512 RGB tree is the training release"
            ),
        },
    }
    conditions = condition_summary(gate)
    outputs = gate["outputs"]
    acquisition_config = load_yaml(
        resolve_project(gate_path.parents[2], str(source["acquisition_config"]["path"]))
    )
    data_root = Path(str(acquisition_config["data_root"])).expanduser().resolve()
    release_path = require_inside(
        data_root / str(outputs["release_inspection_receipt"]), data_root, "release receipt"
    )
    condition_path = require_inside(
        data_root / str(outputs["condition_strata_receipt"]), data_root, "condition receipt"
    )
    created = datetime.now(timezone.utc).isoformat()
    release_receipt = {
        "schema_version": 1,
        "created_utc": created,
        "status": "verified",
        "gate_config": str(gate_path),
        "gate_config_sha256": sha256(gate_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "source_revision": source["revision"],
        "acquisition_receipt": str(data_root / str(source["acquisition_receipt"])),
        "acquisition_receipt_sha256": sha256(data_root / str(source["acquisition_receipt"])),
        "acquisition_total_file_bytes": acquisition["total_file_bytes"],
        "paired_archive": paired_layout,
        "paired_rgb_inventory": rgb,
        "paired_mask_inventory": masks,
        "partial_original_archive": original,
        "paired_samples": expected_count,
        "source_class_pixels": {str(key): value for key, value in sorted(class_pixels.items())},
        "source_class_percent": {str(key): value for key, value in actual_percent.items()},
        "workbooks": workbooks,
        "archive_crc_passed": True,
        "source_masks_preserved": True,
        "common_masks_written": False,
        "external_test_used": False,
        "model_selection_used": False,
    }
    condition_receipt = {
        "schema_version": 1,
        "created_utc": created,
        "status": "metadata_strata_verified_against_release_counts",
        "gate_config": str(gate_path),
        "gate_config_sha256": sha256(gate_path),
        "release_inspection_receipt": str(release_path),
        "release_inspection_receipt_sha256_pending_until_write": True,
        "subdataset_counts": expected_by_subdataset,
        "strata": conditions,
        "coverage_training_roles": metadata["coverage_roles"],
        "country_transfer": metadata["country_transfer"],
        "synthetic_factor_selection_status": "pending_rgb_condition_and_domain_gap_audit",
        "external_test_created": False,
        "model_selection_used": False,
    }
    release_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_release = release_path.with_suffix(release_path.suffix + ".tmp")
    temporary_release.write_text(
        json.dumps(release_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_release.replace(release_path)
    condition_receipt["release_inspection_receipt_sha256"] = sha256(release_path)
    condition_receipt.pop("release_inspection_receipt_sha256_pending_until_write")
    temporary_condition = condition_path.with_suffix(condition_path.suffix + ".tmp")
    temporary_condition.write_text(
        json.dumps(condition_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_condition.replace(condition_path)
    return release_path, condition_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/riceseg_release_gate_v1.yaml"),
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate frozen metadata/splits without requiring gated dataset bytes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gate_path = args.config.expanduser().resolve()
    if args.validate_config:
        result = validate_metadata(load_yaml(gate_path))
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    release_path, condition_path = inspect_release(gate_path)
    print(
        json.dumps(
            {
                "release_inspection_receipt": str(release_path),
                "release_inspection_sha256": sha256(release_path),
                "condition_strata_receipt": str(condition_path),
                "condition_strata_sha256": sha256(condition_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
