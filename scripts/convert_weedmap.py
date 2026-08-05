#!/usr/bin/env python3
"""Convert the frozen RGB subset of WeedMap with fail-closed provenance gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
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


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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
        "bad_paths": len(bad_paths),
        "symlinks": len(links),
    }


def decoded_png(payload: bytes, source: str) -> tuple[Image.Image, str]:
    with Image.open(BytesIO(payload)) as handle:
        if handle.format != "PNG":
            raise ValueError(f"Expected PNG payload: {source}")
        mode = handle.mode
        handle.load()
        return handle.copy(), mode


def single_channel(image: Image.Image, source: str) -> np.ndarray:
    value = np.asarray(image)
    if value.ndim == 3:
        if value.shape[2] not in {3, 4}:
            raise ValueError(f"Unexpected channel count in {source}: {value.shape}")
        rgb = value[:, :, :3]
        if not np.all(rgb == rgb[:, :, :1]):
            raise ValueError(f"Expected equal mask channels in {source}")
        value = rgb[:, :, 0]
    if value.ndim != 2:
        raise ValueError(f"Expected a single-channel mask in {source}: {value.shape}")
    return value


def recorded_tree_sha256(
    records: list[SampleRecord], data_root: Path, attribute: str
) -> str:
    digest = hashlib.sha256()
    recorded_paths = sorted({str(getattr(record, attribute)) for record in records})
    for recorded_path in recorded_paths:
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


def source_members(map_id: str, frame: int) -> dict[str, str]:
    stem = f"frame{frame:04d}"
    root = f"Tiles/RedEdge/{map_id}"
    return {
        "image": f"{root}/tile/RGB/{stem}.png",
        "validity": f"{root}/mask/{stem}.png",
        "label": (
            f"{root}/groundtruth/{map_id}_{stem}_GroundTruth_iMap.png"
        ),
        "label_color": (
            f"{root}/groundtruth/{map_id}_{stem}_GroundTruth_color.png"
        ),
    }


def convert(gate_path: Path) -> Path:
    gate_path = gate_path.expanduser().resolve()
    gate = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError("Gate config must be a mapping")
    data_root = Path(str(gate.get("data_root", "data"))).expanduser().resolve()
    source = gate["source"]
    structure = gate["publisher_structure"]
    outputs = gate["outputs"]
    archive_path = data_root / str(source["archive_path"])
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    require_equal(
        "archive size", archive_path.stat().st_size, int(source["archive_size_bytes"])
    )
    require_equal("archive SHA-256", sha256(archive_path), str(source["archive_sha256"]))

    map_specs = {str(key): value for key, value in structure["rededge_maps"].items()}
    require_equal("RedEdge map ids", set(map_specs), {"000", "001", "002", "003", "004"})
    raw_to_common = {
        int(raw): int(common)
        for raw, common in structure["raw_class_to_common"].items()
    }
    require_equal(
        "common ontology", set(raw_to_common.values()), {BACKGROUND, CROP, WEED}
    )
    allowed_validity = {int(value) for value in structure["validity_mask_values"]}
    valid_mask_value = int(structure["observed_valid_mask_value"])
    invalid_mask_value = int(structure["observed_invalid_mask_value"])
    require_equal(
        "validity polarity values",
        {valid_mask_value, invalid_mask_value},
        allowed_validity,
    )
    minimum_valid_fraction = float(structure["minimum_valid_fraction"])
    if not 0.0 < minimum_valid_fraction <= 1.0:
        raise ValueError("minimum_valid_fraction must be in (0, 1]")
    raw_to_color = {
        int(raw): tuple(int(channel) for channel in colour)
        for raw, colour in structure["observed_raw_class_to_color"].items()
    }
    require_equal("raw/color keys", set(raw_to_color), set(raw_to_common))
    expected_size = (
        int(structure["tile_width"]),
        int(structure["tile_height"]),
    )

    images_root = data_root / str(outputs["images_root"])
    masks_root = data_root / str(outputs["masks_root"])
    records: list[SampleRecord] = []
    expected_images: set[Path] = set()
    expected_masks: set[Path] = set()
    source_modes: dict[str, Counter[str]] = {
        "image": Counter(),
        "validity": Counter(),
        "label": Counter(),
        "label_color": Counter(),
    }
    source_raw_pixels: Counter[int] = Counter()
    source_valid_raw_pixels: Counter[int] = Counter()
    included_common_pixels: Counter[int] = Counter()
    map_audits: dict[str, dict[str, Any]] = {}

    with ZipFile(archive_path) as archive:
        summary = archive_summary(archive)
        require_equal("archive members", summary["members"], int(source["archive_members"]))
        require_equal(
            "archive compressed bytes",
            summary["compressed_bytes"],
            int(source["archive_compressed_bytes"]),
        )
        require_equal(
            "archive uncompressed bytes",
            summary["uncompressed_bytes"],
            int(source["archive_uncompressed_bytes"]),
        )
        if bool(source.get("require_full_crc_test", True)):
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f"Archive CRC failure: {bad_member}")
        names = set(archive.namelist())

        for map_id in sorted(map_specs):
            spec = map_specs[map_id]
            total_tiles = int(spec["total_tiles"])
            effective = 0
            excluded_all_invalid = 0
            excluded_below_minimum_valid_fraction = 0
            map_common: Counter[int] = Counter()
            included_valid_fractions: list[float] = []
            for frame in range(total_tiles):
                members = source_members(map_id, frame)
                missing = sorted(set(members.values()) - names)
                if missing:
                    raise FileNotFoundError(missing[0])
                payloads = {name: archive.read(member) for name, member in members.items()}
                decoded = {
                    name: decoded_png(payload, members[name])
                    for name, payload in payloads.items()
                }
                for name, (_, mode) in decoded.items():
                    source_modes[name][mode] += 1
                rgb = decoded["image"][0]
                require_equal(f"RGB size {map_id}/{frame}", rgb.size, expected_size)
                if rgb.mode not in {"RGB", "RGBA"}:
                    raise ValueError(
                        f"Unexpected RGB mode {rgb.mode}: {members['image']}"
                    )
                validity_image = decoded["validity"][0]
                label_image = decoded["label"][0]
                label_color_image = decoded["label_color"][0]
                require_equal(
                    f"validity size {map_id}/{frame}", validity_image.size, expected_size
                )
                require_equal(
                    f"label size {map_id}/{frame}", label_image.size, expected_size
                )
                require_equal(
                    f"color label size {map_id}/{frame}",
                    label_color_image.size,
                    expected_size,
                )
                validity = single_channel(validity_image, members["validity"])
                raw_label = single_channel(label_image, members["label"]).astype(
                    np.int64, copy=False
                )
                label_color = np.asarray(label_color_image.convert("RGB"))
                rgb_array = np.asarray(rgb.convert("RGB"))
                validity_values = {int(value) for value in np.unique(validity)}
                if not validity_values <= allowed_validity:
                    raise ValueError(
                        f"Unexpected validity values {validity_values}: {members['validity']}"
                    )
                source_raw_pixels.update(
                    {
                        int(value): int(count)
                        for value, count in zip(
                            *np.unique(raw_label, return_counts=True), strict=True
                        )
                    }
                )
                raw_values = {int(value) for value in np.unique(raw_label)}
                unexpected_raw = raw_values - set(raw_to_common)
                if unexpected_raw:
                    raise ValueError(
                        f"Unexpected released labels {unexpected_raw}: {members['label']}"
                    )
                for raw, expected_colour in raw_to_color.items():
                    selected = raw_label == raw
                    mismatch = selected & np.any(
                        label_color != np.asarray(expected_colour, dtype=np.uint8),
                        axis=2,
                    )
                    if np.any(mismatch):
                        raise ValueError(
                            "Indexed/color ground-truth mismatch for "
                            f"raw {raw}: {members['label_color']}"
                        )
                valid = validity == valid_mask_value
                rgb_non_black = np.any(rgb_array != 0, axis=2)
                if not np.array_equal(valid, rgb_non_black):
                    raise ValueError(
                        "Released mask polarity does not match RGB footprint: "
                        f"{members['validity']}"
                    )
                if not np.any(valid):
                    excluded_all_invalid += 1
                    continue
                valid_fraction = float(valid.mean())
                if valid_fraction < minimum_valid_fraction:
                    excluded_below_minimum_valid_fraction += 1
                    continue
                effective += 1
                included_valid_fractions.append(valid_fraction)
                valid_values, valid_counts = np.unique(
                    raw_label[valid], return_counts=True
                )
                unexpected = {int(value) for value in valid_values} - set(raw_to_common)
                if unexpected:
                    raise ValueError(
                        f"Unexpected valid labels {unexpected}: {members['label']}"
                    )
                source_valid_raw_pixels.update(
                    {
                        int(value): int(count)
                        for value, count in zip(valid_values, valid_counts, strict=True)
                    }
                )
                common = np.full(raw_label.shape, IGNORE, dtype=np.uint8)
                for raw, common_id in raw_to_common.items():
                    common[valid & (raw_label == raw)] = common_id
                for common_id in (BACKGROUND, CROP, WEED, IGNORE):
                    count = int(np.count_nonzero(common == common_id))
                    map_common[common_id] += count
                    included_common_pixels[common_id] += count

                stem = f"{map_id}_frame{frame:04d}"
                image_path = images_root / map_id / f"{stem}.png"
                mask_path = masks_root / map_id / f"{stem}.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(payloads["image"])
                Image.fromarray(common, mode="L").save(mask_path, optimize=False)
                expected_images.add(image_path.resolve())
                expected_masks.add(mask_path.resolve())

                metadata = gate["capture"]
                records.append(
                    SampleRecord(
                        sample_id=f"weedmap:{map_id}:frame{frame:04d}",
                        image_path=relative(image_path, data_root),
                        mask_path=relative(mask_path, data_root),
                        split=str(spec["role"]),
                        dataset_id="weedmap",
                        field_id=str(metadata["field_id"]),
                        session_id=f"rededge_orthomosaic_{map_id}_2017_09_18",
                        capture_date=str(metadata["capture_date"]),
                        platform=str(metadata["platform"]),
                        sensor=str(metadata["sensor"]),
                        target_crop_id=int(metadata["target_crop_id"]),
                        crop_species=str(metadata["crop_species"]),
                        weed_species_optional=str(metadata["weed_species"]),
                        growth_stage=str(metadata["growth_stage"]),
                        annotation_exhaustive=True,
                        license_status=str(gate["license"]["status"]),
                        commercial_allowed=bool(gate["license"]["commercial_allowed"]),
                    )
                )
            require_equal(
                f"effective tiles {map_id}", effective, int(spec["effective_tiles"])
            )
            require_equal(
                f"all-invalid tiles {map_id}",
                excluded_all_invalid,
                int(spec["all_invalid_tiles"]),
            )
            require_equal(
                f"below-minimum-valid-fraction tiles {map_id}",
                excluded_below_minimum_valid_fraction,
                int(spec["below_minimum_valid_fraction_tiles"]),
            )
            map_audits[map_id] = {
                "role": str(spec["role"]),
                "source_tiles": total_tiles,
                "included_effective_tiles": effective,
                "excluded_all_invalid_tiles": excluded_all_invalid,
                "excluded_below_minimum_valid_fraction_tiles": (
                    excluded_below_minimum_valid_fraction
                ),
                "minimum_valid_fraction_gate": minimum_valid_fraction,
                "included_valid_fraction": {
                    "min": min(included_valid_fractions),
                    "max": max(included_valid_fractions),
                    "mean": sum(included_valid_fractions)
                    / len(included_valid_fractions),
                },
                "publisher_reported_effective_tiles": int(
                    spec["publisher_reported_effective_tiles"]
                ),
                "released_archive_count_delta_vs_publisher": effective
                - int(spec["publisher_reported_effective_tiles"]),
                "common_class_pixels": {
                    "background": map_common[BACKGROUND],
                    "crop": map_common[CROP],
                    "weed": map_common[WEED],
                    "ignore": map_common[IGNORE],
                },
            }

    actual_images = {path.resolve() for path in images_root.glob("*/*.png")}
    actual_masks = {path.resolve() for path in masks_root.glob("*/*.png")}
    require_equal("derived RGB file set", actual_images, expected_images)
    require_equal("derived mask file set", actual_masks, expected_masks)
    require_equal(
        "included samples", len(records), int(gate["quality_gate"]["expected_samples"])
    )
    if included_common_pixels[CROP] <= 0 or included_common_pixels[WEED] <= 0:
        raise ValueError("Included WeedMap subset must contain crop and weed pixels")
    require_equal(
        "released raw label values", set(source_raw_pixels), set(raw_to_common)
    )

    manifest = data_root / str(outputs["manifest"])
    train_manifest = data_root / str(outputs["train_manifest"])
    calibration_manifest = data_root / str(outputs["calibration_manifest"])
    write_manifest(records, manifest)
    write_manifest([record for record in records if record.split == "train"], train_manifest)
    write_manifest(
        [record for record in records if record.split == "external_calibration"],
        calibration_manifest,
    )
    split_counts = Counter(record.split for record in records)
    require_equal(
        "train samples", split_counts["train"], int(gate["quality_gate"]["expected_train"])
    )
    require_equal(
        "calibration samples",
        split_counts["external_calibration"],
        int(gate["quality_gate"]["expected_external_calibration"]),
    )

    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": "weedmap",
        "all_quality_gates_passed": True,
        "provenance": {
            "official_doi": str(source["official_doi"]),
            "official_landing_page": str(source["official_landing_page"]),
            "mirror_landing_page": str(source["mirror_landing_page"]),
            "mirror_download_url": str(source["mirror_download_url"]),
            "archive": str(archive_path),
            "archive_size_bytes": archive_path.stat().st_size,
            "archive_sha256": sha256(archive_path),
            "archive_checksum_status": str(source["archive_checksum_status"]),
            "archive_safety": summary,
            "full_crc_test_passed": bool(source.get("require_full_crc_test", True)),
            "gate_config": str(gate_path),
            "gate_config_sha256": sha256(gate_path),
            "converter": str(Path(__file__).resolve()),
            "converter_sha256": sha256(__file__),
        },
        "policy": {
            "research_only": True,
            "commercial_allowed": False,
            "rgb_only": True,
            "sequoia_cir_excluded": True,
            "single_site_campaign_limit": str(gate["role_policy"]["single_site_limit"]),
            "external_test_claim": False,
            "minimum_valid_fraction": minimum_valid_fraction,
        },
        "resolved_release_anomalies": gate["resolved_release_anomalies"],
        "source_rededge_tiles_audited": sum(
            int(spec["total_tiles"]) for spec in map_specs.values()
        ),
        "source_modes": {
            name: dict(sorted(values.items())) for name, values in source_modes.items()
        },
        "source_raw_class_pixels": {
            str(key): value for key, value in sorted(source_raw_pixels.items())
        },
        "source_valid_raw_class_pixels": {
            str(key): value for key, value in sorted(source_valid_raw_pixels.items())
        },
        "included_common_class_pixels": {
            "background": included_common_pixels[BACKGROUND],
            "crop": included_common_pixels[CROP],
            "weed": included_common_pixels[WEED],
            "ignore": included_common_pixels[IGNORE],
        },
        "map_audits": map_audits,
        "samples": len(records),
        "field_count": len({record.field_id for record in records}),
        "capture_group_count": len({record.group_id for record in records}),
        "split_counts": dict(sorted(split_counts.items())),
        "derived": {
            "manifest": str(manifest),
            "manifest_sha256": manifest_sha256(manifest),
            "train_manifest": str(train_manifest),
            "train_manifest_sha256": manifest_sha256(train_manifest),
            "calibration_manifest": str(calibration_manifest),
            "calibration_manifest_sha256": manifest_sha256(calibration_manifest),
            "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
            "derived_image_tree_sha256": recorded_tree_sha256(
                records, data_root, "image_path"
            ),
        },
    }
    report_path = data_root / str(outputs["report"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config", default="configs/data/weedmap_real_gate_v1.yaml"
    )
    arguments = parser.parse_args()
    report = convert(Path(arguments.gate_config))
    print(json.dumps({"report": str(report), "sha256": sha256(report)}, indent=2))


if __name__ == "__main__":
    main()
