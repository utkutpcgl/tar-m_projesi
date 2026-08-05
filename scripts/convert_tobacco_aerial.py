#!/usr/bin/env python3
"""Convert Tobacco Aerial Dataset with archive, label, and field gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from zipfile import ZipFile

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import BACKGROUND, CROP, WEED
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    write_manifest,
)


CLASS_NAMES = {BACKGROUND: "background", CROP: "crop", WEED: "weed"}
KINDS = ("data", "mask", "maskref")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stream_sha256(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def archive_summary(archive: ZipFile) -> dict[str, int]:
    bad_paths: list[str] = []
    links: list[str] = []
    members = archive.infolist()
    for member in members:
        candidate = PurePosixPath(member.filename)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in member.filename:
            bad_paths.append(member.filename)
        file_type = (member.external_attr >> 16) & 0o170000
        if file_type == 0o120000:
            links.append(member.filename)
    if bad_paths or links:
        raise ValueError(
            f"Unsafe archive: bad_paths={bad_paths[:5]}, symlinks={links[:5]}"
        )
    return {
        "members": len(members),
        "files": sum(not member.is_dir() for member in members),
        "compressed_bytes": sum(member.compress_size for member in members),
        "uncompressed_bytes": sum(member.file_size for member in members),
        "unsafe_paths": len(bad_paths),
        "symlinks": len(links),
    }


def verify_archive(
    path: Path, specification: dict[str, Any], *, verify_crc: bool
) -> tuple[ZipFile, dict[str, int]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    require_equal(f"archive size {path}", path.stat().st_size, int(specification["size_bytes"]))
    require_equal(f"archive SHA-256 {path}", sha256(path), str(specification["sha256"]))
    archive = ZipFile(path)
    summary = archive_summary(archive)
    for field in ("members", "files", "compressed_bytes", "uncompressed_bytes"):
        require_equal(f"archive {field} {path}", summary[field], int(specification[field]))
    if verify_crc:
        bad_member = archive.testzip()
        if bad_member is not None:
            archive.close()
            raise ValueError(f"Archive CRC failure in {path}: {bad_member}")
    return archive, summary


def decoded_png(payload: bytes, source: str) -> tuple[Image.Image, str]:
    with Image.open(BytesIO(payload)) as handle:
        if handle.format != "PNG":
            raise ValueError(f"Expected PNG payload: {source}")
        mode = handle.mode
        handle.load()
        return handle.copy(), mode


def canonical_member(campaign: str, directory: str, kind: str, index: int) -> str:
    return (
        f"Tobacco Aerial Dataset/Campaign no. {campaign}/"
        f"{directory}/{kind}/{index}.png"
    )


def redundant_member(campaign: str, group: str, kind: str, index: int) -> str:
    root = f"Ready for traintest tobacco data 352x480/{group}"
    if campaign in {"1", "2"}:
        return f"{root}/{kind}/{index}.png"
    return f"{root}/test/RGB/{kind}/{index}.png"


def expected_member_set(
    campaign: str, specification: dict[str, Any], *, canonical: bool
) -> set[str]:
    count = int(specification["patches"])
    if canonical:
        directory = str(specification["v2_patch_directory"])
        return {
            canonical_member(campaign, directory, kind, index)
            for kind in KINDS
            for index in range(1, count + 1)
        }
    group = str(specification["v1_group"])
    return {
        redundant_member(campaign, group, kind, index)
        for kind in KINDS
        for index in range(1, count + 1)
    }


def validate_exact_directory_members(
    names: set[str], expected: set[str], prefixes: tuple[str, ...], label: str
) -> None:
    actual = {
        name
        for name in names
        if name.startswith(prefixes) and not name.endswith("/")
    }
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(
            f"Unexpected {label} member set: missing={missing[:5]}, extra={extra[:5]}"
        )


def reconstruct_parent(patches: list[np.ndarray]) -> np.ndarray:
    require_equal("patches per parent", len(patches), 12)
    return np.concatenate(
        [
            np.concatenate([patches[column * 3 + row] for column in range(4)], axis=1)
            for row in range(3)
        ],
        axis=0,
    )


def seam_internal_ratio(parent: np.ndarray) -> tuple[float, float, float]:
    value = parent.astype(np.int16, copy=False)
    seams = [
        float(np.abs(value[:, x] - value[:, x - 1]).mean())
        for x in (480, 960, 1440)
    ] + [
        float(np.abs(value[y] - value[y - 1]).mean())
        for y in (352, 704)
    ]
    internal = [
        float(np.abs(value[:, x] - value[:, x - 1]).mean())
        for x in (240, 720, 1200, 1680)
    ] + [
        float(np.abs(value[y] - value[y - 1]).mean())
        for y in (176, 528, 880)
    ]
    seam = statistics.fmean(seams)
    baseline = statistics.fmean(internal)
    return seam, baseline, seam / max(baseline, 1e-12)


def uniformly_spaced_parent_blocks(parent_count: int, selected: int) -> list[int]:
    if selected < 2 or parent_count < selected:
        raise ValueError("Invalid balanced parent selection")
    zero_based = [
        math.floor(index * (parent_count - 1) / (selected - 1) + 0.5)
        for index in range(selected)
    ]
    require_equal("unique selected parent blocks", len(set(zero_based)), selected)
    require_equal("first selected parent block", zero_based[0], 0)
    require_equal("last selected parent block", zero_based[-1], parent_count - 1)
    return [value + 1 for value in zero_based]


def recorded_tree_sha256(
    records: list[SampleRecord], data_root: Path, attribute: str
) -> str:
    digest = hashlib.sha256()
    for recorded_path in sorted({str(getattr(record, attribute)) for record in records}):
        path = Path(recorded_path)
        resolved = path if path.is_absolute() else data_root / path
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        digest.update(recorded_path.encode("utf-8"))
        digest.update(b"\0")
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def verify_outer_members(
    outer: ZipFile, nested_paths: dict[str, Path], specifications: dict[str, Any]
) -> dict[str, dict[str, object]]:
    expected = {str(value["outer_member"]) for value in specifications.values()}
    actual = {member.filename for member in outer.infolist() if not member.is_dir()}
    require_equal("outer archive member names", actual, expected)
    result: dict[str, dict[str, object]] = {}
    for name, specification in specifications.items():
        member = str(specification["outer_member"])
        info = outer.getinfo(member)
        require_equal(f"outer member size {name}", info.file_size, int(specification["size_bytes"]))
        with outer.open(info) as handle:
            payload_hash = stream_sha256(handle)
        require_equal(f"outer member SHA-256 {name}", payload_hash, str(specification["sha256"]))
        require_equal(f"extracted nested SHA-256 {name}", sha256(nested_paths[name]), payload_hash)
        result[name] = {
            "outer_member": member,
            "size_bytes": info.file_size,
            "sha256": payload_hash,
            "matches_extracted_nested_archive": True,
        }
    return result


def convert(gate_path: Path) -> Path:
    gate_path = gate_path.expanduser().resolve()
    gate = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError("Gate config must be a mapping")
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    source = gate["source"]
    nested_specs = gate["nested_archives"]
    quality = gate["quality_gate"]
    outputs = gate["outputs"]
    campaigns = {str(key): value for key, value in gate["campaigns"].items()}
    require_equal("campaign identifiers", set(campaigns), set("12345678"))
    require_equal(
        "common ontology mapping",
        {int(raw): int(common) for raw, common in gate["capture"]["raw_class_to_common"].items()},
        {BACKGROUND: BACKGROUND, CROP: CROP, WEED: WEED},
    )

    split_path = Path(str(gate["split_protocol"]["path"])).expanduser().resolve()
    require_equal("split protocol SHA-256", sha256(split_path), str(gate["split_protocol"]["sha256"]))
    split = yaml.safe_load(split_path.read_text(encoding="utf-8"))
    if split.get("frozen_before_archive_visual_review") is not True:
        raise ValueError("Split was not frozen before archive visual review")
    if split.get("frozen_before_model_evaluation") is not True:
        raise ValueError("Split was not frozen before model evaluation")
    train_campaigns = {str(value) for value in split["role_policy"]["train_campaigns"]}
    calibration_campaigns = {
        str(value) for value in split["role_policy"]["external_calibration_campaigns"]
    }
    require_equal("train campaign lock", train_campaigns, set(gate["split_protocol"]["train_campaigns"]))
    require_equal(
        "calibration campaign lock",
        calibration_campaigns,
        set(gate["split_protocol"]["external_calibration_campaigns"]),
    )
    require_equal("campaign role coverage", train_campaigns | calibration_campaigns, set(campaigns))
    require_equal("campaign role overlap", train_campaigns & calibration_campaigns, set())
    for campaign, specification in campaigns.items():
        expected_role = "train" if campaign in train_campaigns else "external_calibration"
        require_equal(f"campaign role {campaign}", str(specification["role"]), expected_role)

    outer_path = data_root / str(source["archive_path"])
    outer_spec = {
        "size_bytes": source["archive_size_bytes"],
        "sha256": source["archive_sha256"],
        "members": source["archive_members"],
        "files": source["archive_files"],
        "compressed_bytes": source["archive_compressed_bytes"],
        "uncompressed_bytes": source["archive_uncompressed_bytes"],
    }
    outer, outer_summary = verify_archive(
        outer_path, outer_spec, verify_crc=bool(source["require_full_crc_test"])
    )
    nested_paths = {
        name: data_root / str(specification["path"])
        for name, specification in nested_specs.items()
    }
    nested_archives: dict[str, ZipFile] = {}
    nested_summaries: dict[str, dict[str, int]] = {}
    try:
        for name, specification in nested_specs.items():
            archive, summary = verify_archive(
                nested_paths[name],
                specification,
                verify_crc=bool(specification["require_full_crc_test"]),
            )
            nested_archives[name] = archive
            nested_summaries[name] = summary
        outer_members = verify_outer_members(outer, nested_paths, nested_specs)
        redundant = nested_archives["release_v1"]
        canonical = nested_archives["release_v2"]
        redundant_names = set(redundant.namelist())
        canonical_names = set(canonical.namelist())

        canonical_output_bytes = 0
        for campaign, specification in campaigns.items():
            expected_canonical = expected_member_set(campaign, specification, canonical=True)
            expected_redundant = expected_member_set(campaign, specification, canonical=False)
            directory = str(specification["v2_patch_directory"])
            canonical_prefixes = tuple(
                f"Tobacco Aerial Dataset/Campaign no. {campaign}/{directory}/{kind}/"
                for kind in KINDS
            )
            group = str(specification["v1_group"])
            redundant_base = f"Ready for traintest tobacco data 352x480/{group}"
            redundant_prefixes = tuple(
                (
                    f"{redundant_base}/{kind}/"
                    if campaign in {"1", "2"}
                    else f"{redundant_base}/test/RGB/{kind}/"
                )
                for kind in KINDS
            )
            validate_exact_directory_members(
                canonical_names, expected_canonical, canonical_prefixes, f"canonical campaign {campaign}"
            )
            validate_exact_directory_members(
                redundant_names, expected_redundant, redundant_prefixes, f"redundant campaign {campaign}"
            )
            for index in range(1, int(specification["patches"]) + 1):
                for kind in ("data", "mask"):
                    canonical_output_bytes += canonical.getinfo(
                        canonical_member(campaign, directory, kind, index)
                    ).file_size

        available = shutil.disk_usage(data_root).free
        reserve = int(quality["minimum_free_space_after_output_bytes"])
        if available - canonical_output_bytes < reserve:
            raise OSError(
                f"Insufficient data-disk space: output={canonical_output_bytes:,}, "
                f"available={available:,}, required reserve={reserve:,}"
            )

        images_root = data_root / str(outputs["images_root"])
        masks_root = data_root / str(outputs["masks_root"])
        records: list[SampleRecord] = []
        balanced_records: list[SampleRecord] = []
        expected_images: set[Path] = set()
        expected_masks: set[Path] = set()
        campaign_audits: dict[str, dict[str, Any]] = {}
        total_pixels: Counter[int] = Counter()
        total_mask_presence: Counter[int] = Counter()
        exact_release_matches = 0
        parent_blocks_total = 0
        exact_source_reconstructions_total = 0

        for campaign in sorted(campaigns, key=int):
            specification = campaigns[campaign]
            patch_count = int(specification["patches"])
            parent_count = int(specification["parent_blocks"])
            require_equal(f"parent arithmetic {campaign}", patch_count, parent_count * 12)
            directory = str(specification["v2_patch_directory"])
            group = str(specification["v1_group"])
            selected_blocks = uniformly_spaced_parent_blocks(
                parent_count,
                int(gate["balanced_selection"]["selected_parent_blocks_per_campaign"]),
            )
            selected_set = set(selected_blocks)
            tree_digest = hashlib.sha256()
            image_modes: Counter[str] = Counter()
            mask_modes: Counter[str] = Counter()
            maskref_modes: Counter[str] = Counter()
            class_pixels: Counter[int] = Counter()
            masks_containing: Counter[int] = Counter()
            parent_patches: list[np.ndarray] = []
            reconstructed_parents: list[np.ndarray] = []

            for kind in KINDS:
                for index in range(1, patch_count + 1):
                    canonical_name = canonical_member(campaign, directory, kind, index)
                    redundant_name = redundant_member(campaign, group, kind, index)
                    payload = canonical.read(canonical_name)
                    duplicate = redundant.read(redundant_name)
                    if payload != duplicate:
                        raise ValueError(
                            f"Nested release mismatch: {canonical_name} != {redundant_name}"
                        )
                    exact_release_matches += 1
                    tree_digest.update(kind.encode("utf-8"))
                    tree_digest.update(b"\0")
                    tree_digest.update(str(index).encode("utf-8"))
                    tree_digest.update(b"\0")
                    tree_digest.update(hashlib.sha256(payload).digest())

                    if kind == "data":
                        image, mode = decoded_png(payload, canonical_name)
                        require_equal(f"image mode {canonical_name}", mode, str(quality["require_rgb_png_mode"]))
                        require_equal(
                            f"image size {canonical_name}",
                            image.size,
                            (int(gate["capture"]["patch_width"]), int(gate["capture"]["patch_height"])),
                        )
                        image_modes[mode] += 1
                        parent_patches.append(np.asarray(image, dtype=np.uint8))
                        if len(parent_patches) == 12:
                            reconstructed_parents.append(reconstruct_parent(parent_patches))
                            parent_patches = []
                    elif kind == "mask":
                        mask_image, mode = decoded_png(payload, canonical_name)
                        require_equal(f"mask mode {canonical_name}", mode, str(quality["require_mask_png_mode"]))
                        require_equal(
                            f"mask size {canonical_name}",
                            mask_image.size,
                            (int(gate["capture"]["patch_width"]), int(gate["capture"]["patch_height"])),
                        )
                        mask = np.asarray(mask_image)
                        values, counts = np.unique(mask, return_counts=True)
                        allowed = {int(value) for value in quality["require_exact_mask_values"]}
                        unexpected = {int(value) for value in values} - allowed
                        if unexpected:
                            raise ValueError(f"Unexpected mask values {unexpected}: {canonical_name}")
                        class_pixels.update(
                            {int(value): int(count) for value, count in zip(values, counts, strict=True)}
                        )
                        total_pixels.update(
                            {int(value): int(count) for value, count in zip(values, counts, strict=True)}
                        )
                        for value in values:
                            masks_containing[int(value)] += 1
                            total_mask_presence[int(value)] += 1
                        mask_modes[mode] += 1
                    else:
                        maskref_image, mode = decoded_png(payload, canonical_name)
                        require_equal(
                            f"maskref mode {canonical_name}",
                            mode,
                            str(quality["require_mask_png_mode"]),
                        )
                        require_equal(
                            f"maskref size {canonical_name}",
                            maskref_image.size,
                            (
                                int(gate["capture"]["patch_width"]),
                                int(gate["capture"]["patch_height"]),
                            ),
                        )
                        maskref_modes[mode] += 1
                        mask_name = canonical_member(campaign, directory, "mask", index)
                        mask = np.asarray(decoded_png(canonical.read(mask_name), mask_name)[0])
                        mapping = {
                            int(raw): int(value)
                            for raw, value in gate["capture"]["maskref_visualization_mapping"].items()
                        }
                        expected_ref = np.zeros(mask.shape, dtype=np.uint8)
                        for raw, value in mapping.items():
                            expected_ref[mask == raw] = value
                        if not np.array_equal(np.asarray(maskref_image), expected_ref):
                            raise ValueError(f"Visualization-mask mismatch: {canonical_name}")

            require_equal(f"completed parent patch buffer {campaign}", len(parent_patches), 0)
            require_equal(
                f"reconstructed parent count {campaign}", len(reconstructed_parents), parent_count
            )
            require_equal(
                f"patch tree digest {campaign}",
                tree_digest.hexdigest(),
                str(specification["canonical_patch_tree_sha256"]),
            )
            observed_class = {
                CLASS_NAMES[class_id]: class_pixels[class_id]
                for class_id in (BACKGROUND, CROP, WEED)
            }
            observed_presence = {
                CLASS_NAMES[class_id]: masks_containing[class_id]
                for class_id in (BACKGROUND, CROP, WEED)
            }
            require_equal(
                f"class pixels {campaign}", observed_class, dict(specification["common_class_pixels"])
            )
            require_equal(
                f"mask class presence {campaign}",
                observed_presence,
                dict(specification["masks_containing_class"]),
            )
            if class_pixels[CROP] <= 0 or class_pixels[WEED] <= 0:
                raise ValueError(f"Campaign {campaign} must contain crop and weed pixels")

            original_prefix = (
                f"Tobacco Aerial Dataset/Campaign no. {campaign}/Original 1080P images/"
            )
            original_names = sorted(
                name
                for name in canonical_names
                if name.startswith(original_prefix)
                and name.lower().endswith((".jpg", ".jpeg", ".png"))
            )
            require_equal(f"original parent count {campaign}", len(original_names), parent_count)
            exact_source_reconstructions = 0
            source_grid_patch_matches = 0
            seam_rows: list[dict[str, float | int]] = []
            if campaign == "1":
                source_patch_hashes: set[bytes] = set()
                for original_name in original_names:
                    with Image.open(BytesIO(canonical.read(original_name))) as handle:
                        original = np.asarray(handle.convert("RGB"), dtype=np.uint8)
                    require_equal(f"original size {original_name}", original.shape[:2], (1080, 1920))
                    for column in range(4):
                        for row in range(3):
                            crop = original[
                                row * 352 : (row + 1) * 352,
                                column * 480 : (column + 1) * 480,
                            ]
                            source_patch_hashes.add(hashlib.sha256(crop.tobytes()).digest())
                for block_index, parent in enumerate(reconstructed_parents, start=1):
                    for column in range(4):
                        for row in range(3):
                            crop = parent[
                                row * 352 : (row + 1) * 352,
                                column * 480 : (column + 1) * 480,
                            ]
                            source_grid_patch_matches += int(
                                hashlib.sha256(crop.tobytes()).digest() in source_patch_hashes
                            )
                    seam, internal, ratio = seam_internal_ratio(parent)
                    seam_rows.append(
                        {
                            "parent_block": block_index,
                            "seam_mad": seam,
                            "internal_mad": internal,
                            "ratio": ratio,
                        }
                    )
                require_equal("Campaign 1 mismatched 1080P grid matches", source_grid_patch_matches, 0)
                maximum_ratio = max(float(row["ratio"]) for row in seam_rows)
                if maximum_ratio > float(
                    gate["parent_frame_policy"]["campaign_1_maximum_seam_internal_mad_ratio"]
                ):
                    raise ValueError(f"Campaign 1 parent-block seam gate failed: {maximum_ratio}")
            else:
                for parent, original_name in zip(
                    reconstructed_parents, original_names, strict=True
                ):
                    with Image.open(BytesIO(canonical.read(original_name))) as handle:
                        original = np.asarray(handle.convert("RGB"), dtype=np.uint8)
                    require_equal(f"original size {original_name}", original.shape[:2], (1080, 1920))
                    exact_source_reconstructions += int(
                        np.array_equal(parent, original[:1056, :1920])
                    )
                require_equal(
                    f"exact source reconstructions {campaign}",
                    exact_source_reconstructions,
                    parent_count,
                )
                exact_source_reconstructions_total += exact_source_reconstructions

            role = str(specification["role"])
            capture_date = str(specification["capture_date"])
            capture_time = str(specification["capture_time"])
            soil = str(specification["soil_condition"])
            campaign_records: list[SampleRecord] = []
            for index in range(1, patch_count + 1):
                parent_block = (index - 1) // 12 + 1
                offset = (index - 1) % 12 + 1
                source_image = canonical_member(campaign, directory, "data", index)
                source_mask = canonical_member(campaign, directory, "mask", index)
                image_path = images_root / f"campaign_{int(campaign):02d}" / f"patch_{index:04d}.png"
                mask_path = masks_root / f"campaign_{int(campaign):02d}" / f"patch_{index:04d}.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(canonical.read(source_image))
                mask_path.write_bytes(canonical.read(source_mask))
                expected_images.add(image_path.resolve())
                expected_masks.add(mask_path.resolve())
                record = SampleRecord(
                    sample_id=(
                        f"tobacco_aerial:c{int(campaign):02d}:"
                        f"parent{parent_block:03d}:patch{offset:02d}"
                    ),
                    image_path=relative(image_path, data_root),
                    mask_path=relative(mask_path, data_root),
                    split=role,
                    dataset_id="tobacco_aerial",
                    field_id=f"mardan_pakistan_tobacco_field_campaign_{int(campaign):02d}",
                    session_id=(
                        f"campaign_{int(campaign):02d}_{capture_date.replace('-', '_')}_"
                        f"{capture_time.replace(':', '')}_{soil}"
                    ),
                    capture_date=capture_date,
                    platform=str(gate["capture"]["platform"]),
                    sensor=str(gate["capture"]["sensor"]),
                    target_crop_id=int(gate["capture"]["target_crop_id"]),
                    crop_species=str(gate["capture"]["crop_species"]),
                    weed_species_optional=str(gate["capture"]["weed_species"]),
                    growth_stage=str(gate["capture"]["growth_stage"]),
                    annotation_exhaustive=bool(gate["capture"]["annotation_exhaustive"]),
                    license_status=str(gate["license"]["status"]),
                    commercial_allowed=bool(gate["license"]["commercial_allowed"]),
                )
                campaign_records.append(record)
                records.append(record)
                if parent_block in selected_set:
                    balanced_records.append(record)
            require_equal(
                f"balanced campaign rows {campaign}",
                sum(record in balanced_records for record in campaign_records),
                int(gate["balanced_selection"]["campaign_patch_cap"]),
            )
            parent_blocks_total += parent_count
            campaign_audits[campaign] = {
                "role": role,
                "field_id": campaign_records[0].field_id,
                "source_patches": patch_count,
                "parent_blocks": parent_count,
                "selected_balanced_parent_blocks": selected_blocks,
                "selected_balanced_patches": len(selected_blocks) * 12,
                "source_modes": {
                    "image": dict(sorted(image_modes.items())),
                    "mask": dict(sorted(mask_modes.items())),
                    "maskref": dict(sorted(maskref_modes.items())),
                },
                "common_class_pixels": observed_class,
                "masks_containing_class": observed_presence,
                "canonical_patch_tree_sha256": tree_digest.hexdigest(),
                "nested_release_patch_members_byte_identical": patch_count * 3,
                "parent_evidence": (
                    {
                        "exact_reconstructions_against_1080p": exact_source_reconstructions,
                        "expected": parent_count,
                    }
                    if campaign != "1"
                    else {
                        "publisher_1080p_grid_patch_matches": source_grid_patch_matches,
                        "spatially_coherent_blocks": len(seam_rows),
                        "seam_internal_mad_ratio": {
                            "min": min(float(row["ratio"]) for row in seam_rows),
                            "median": statistics.median(
                                float(row["ratio"]) for row in seam_rows
                            ),
                            "max": max(float(row["ratio"]) for row in seam_rows),
                        },
                    }
                ),
            }

        require_equal("all released mask values", set(total_pixels), {BACKGROUND, CROP, WEED})
        require_equal("full sample count", len(records), int(quality["expected_samples"]))
        require_equal("parent block count", parent_blocks_total, int(quality["expected_parent_blocks"]))
        require_equal("balanced sample count", len(balanced_records), int(quality["expected_balanced_samples"]))
        require_equal("exact source parent reconstructions", exact_source_reconstructions_total, 138)
        require_equal("nested release exact patch members", exact_release_matches, 2520 * 3)

        actual_images = {path.resolve() for path in images_root.rglob("*.png")}
        actual_masks = {path.resolve() for path in masks_root.rglob("*.png")}
        require_equal("derived image file set", actual_images, expected_images)
        require_equal("derived mask file set", actual_masks, expected_masks)

        train_records = [record for record in records if record.split == "train"]
        calibration_records = [
            record for record in records if record.split == "external_calibration"
        ]
        balanced_train = [record for record in balanced_records if record.split == "train"]
        balanced_calibration = [
            record
            for record in balanced_records
            if record.split == "external_calibration"
        ]
        require_equal("train rows", len(train_records), int(quality["expected_train"]))
        require_equal(
            "calibration rows",
            len(calibration_records),
            int(quality["expected_external_calibration"]),
        )
        require_equal(
            "balanced train rows", len(balanced_train), int(quality["expected_balanced_train"])
        )
        require_equal(
            "balanced calibration rows",
            len(balanced_calibration),
            int(quality["expected_balanced_external_calibration"]),
        )

        manifest_output_names = (
            "manifest",
            "train_manifest",
            "calibration_manifest",
            "balanced_manifest",
            "balanced_train_manifest",
            "balanced_calibration_manifest",
        )
        output_paths = {
            name: data_root / str(outputs[name]) for name in manifest_output_names
        }
        write_manifest(records, output_paths["manifest"])
        write_manifest(train_records, output_paths["train_manifest"])
        write_manifest(calibration_records, output_paths["calibration_manifest"])
        write_manifest(balanced_records, output_paths["balanced_manifest"])
        write_manifest(balanced_train, output_paths["balanced_train_manifest"])
        write_manifest(balanced_calibration, output_paths["balanced_calibration_manifest"])

        split_counts = Counter(record.split for record in records)
        balanced_split_counts = Counter(record.split for record in balanced_records)
        report = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_id": "tobacco_aerial",
            "all_quality_gates_passed": True,
            "provenance": {
                "official_doi": str(source["official_doi"]),
                "official_landing_page": str(source["official_landing_page"]),
                "official_download_url": str(source["official_download_url"]),
                "archive": str(outer_path),
                "archive_size_bytes": outer_path.stat().st_size,
                "archive_sha256": sha256(outer_path),
                "archive_checksum_status": str(source["archive_checksum_status"]),
                "archive_safety": outer_summary,
                "full_crc_test_passed": True,
                "outer_members": outer_members,
                "nested_archives": {
                    name: {
                        "path": str(nested_paths[name]),
                        "size_bytes": nested_paths[name].stat().st_size,
                        "sha256": sha256(nested_paths[name]),
                        "archive_safety": nested_summaries[name],
                        "full_crc_test_passed": True,
                    }
                    for name in sorted(nested_paths)
                },
                "gate_config": str(gate_path),
                "gate_config_sha256": sha256(gate_path),
                "split_protocol": str(split_path),
                "split_protocol_sha256": sha256(split_path),
                "converter": str(Path(__file__).resolve()),
                "converter_sha256": sha256(__file__),
            },
            "policy": {
                "canonical_source": "release_v2 Patch images/data and mask only",
                "maskref_used_as_ground_truth": False,
                "detected_vegetation_used_as_rgb": False,
                "external_test_claim": False,
                "commercial_allowed": True,
                "balanced_selection_independent_of_content_and_model": True,
                "minimum_free_space_after_output_bytes": reserve,
                "free_space_before_output_bytes": available,
                "expected_output_bytes": canonical_output_bytes,
            },
            "resolved_release_anomalies": gate["resolved_release_anomalies"],
            "samples": len(records),
            "field_count": len({record.field_id for record in records}),
            "capture_group_count": len({record.group_id for record in records}),
            "parent_block_count": parent_blocks_total,
            "split_counts": dict(sorted(split_counts.items())),
            "balanced_samples": len(balanced_records),
            "balanced_split_counts": dict(sorted(balanced_split_counts.items())),
            "nested_release_patch_members_byte_identical": exact_release_matches,
            "common_class_pixels": {
                CLASS_NAMES[class_id]: total_pixels[class_id]
                for class_id in (BACKGROUND, CROP, WEED)
            },
            "masks_containing_class": {
                CLASS_NAMES[class_id]: total_mask_presence[class_id]
                for class_id in (BACKGROUND, CROP, WEED)
            },
            "campaign_audits": campaign_audits,
            "derived": {
                **{
                    name: {
                        "path": str(path),
                        "sha256": manifest_sha256(path),
                    }
                    for name, path in output_paths.items()
                },
                "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
                "derived_image_tree_sha256": recorded_tree_sha256(
                    records, data_root, "image_path"
                ),
                "balanced_normalized_mask_tree_sha256": mask_tree_sha256(
                    balanced_records, data_root
                ),
                "balanced_image_tree_sha256": recorded_tree_sha256(
                    balanced_records, data_root, "image_path"
                ),
            },
        }
        require_equal("field count", report["field_count"], int(quality["expected_fields"]))
        report_path = data_root / str(outputs["report"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report_path
    finally:
        outer.close()
        for archive in nested_archives.values():
            archive.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config", default="configs/data/tobacco_aerial_real_gate_v1.yaml"
    )
    arguments = parser.parse_args()
    report = convert(Path(arguments.gate_config))
    print(json.dumps({"report": str(report), "sha256": sha256(report)}, indent=2))


if __name__ == "__main__":
    main()
