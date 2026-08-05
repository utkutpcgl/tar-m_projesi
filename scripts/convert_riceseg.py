#!/usr/bin/env python3
"""Losslessly extract gated RiceSEG pairs and derive common 0/1/2 masks."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile, ZipInfo

import numpy as np
import yaml
from PIL import Image

from agri_seg.manifest import SampleRecord, manifest_sha256, write_manifest
try:
    from scripts.inspect_riceseg_release import (
        RASTER_SUFFIXES,
        canonical_pair_key,
        infer_subdataset,
        safe_members,
        validate_metadata,
    )
except ModuleNotFoundError:  # Direct ``python scripts/convert_riceseg.py`` execution.
    from inspect_riceseg_release import (  # type: ignore[no-redef]
        RASTER_SUFFIXES,
        canonical_pair_key,
        infer_subdataset,
        safe_members,
        validate_metadata,
    )


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def require_inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must remain below {root}: {resolved}") from exc
    return resolved


def locked_path(root: Path, specification: dict[str, Any], label: str) -> Path:
    path = require_inside(root / str(specification["path"]), root, label)
    if not path.is_file():
        raise FileNotFoundError(path)
    require_equal(f"{label} SHA-256", sha256(path), str(specification["sha256"]))
    return path


def archive_pair_index(
    archive: ZipFile,
    *,
    subdatasets: dict[str, Any],
    rgb_directory: str,
    mask_directory: str,
) -> tuple[dict[str, ZipInfo], dict[str, ZipInfo]]:
    """Return canonical pair-key indexes after rejecting ambiguous members."""

    rgb: dict[str, ZipInfo] = {}
    masks: dict[str, ZipInfo] = {}
    for member in safe_members(archive, "RiceSEG paired archive"):
        if member.is_dir():
            continue
        candidate = PurePosixPath(member.filename)
        if candidate.suffix.lower() not in RASTER_SUFFIXES:
            raise ValueError(f"Unexpected non-raster RiceSEG payload: {member.filename}")
        parent = candidate.parent.name
        if parent not in {rgb_directory, mask_directory}:
            raise ValueError(f"Unexpected RiceSEG modality directory: {member.filename}")
        subdataset = infer_subdataset(member.filename, subdatasets)
        key = canonical_pair_key(member.filename, subdataset)
        destination = rgb if parent == rgb_directory else masks
        if key in destination:
            raise ValueError(f"Duplicate canonical RiceSEG member {key}: {member.filename}")
        destination[key] = member
    require_equal("RiceSEG RGB/mask keys", set(rgb), set(masks))
    return rgb, masks


def common_from_source(source: np.ndarray, mapping: dict[int, int]) -> np.ndarray:
    if source.ndim != 2:
        raise ValueError(f"RiceSEG source mask must be 2-D, got {source.shape}")
    values = {int(value) for value in np.unique(source)}
    unexpected = values - set(mapping)
    if unexpected:
        raise ValueError(f"Unexpected RiceSEG source labels: {sorted(unexpected)}")
    maximum = max(mapping)
    lookup = np.full(maximum + 1, 255, dtype=np.uint8)
    for raw, common in mapping.items():
        lookup[int(raw)] = int(common)
    return lookup[source.astype(np.int64, copy=False)]


def png_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8, copy=False)).save(buffer, format="PNG")
    return buffer.getvalue()


def write_exact(destination: Path, payload: bytes) -> bool:
    """Write once; an existing different payload is a hard provenance failure."""

    if destination.is_file():
        if sha256(destination) != sha256_bytes(payload):
            raise RuntimeError(f"Refusing to overwrite differing RiceSEG output: {destination}")
        return False
    if destination.exists():
        raise RuntimeError(f"RiceSEG output is not a regular file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return True


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized:
        raise ValueError(f"Cannot form metadata slug from {value!r}")
    return normalized


def record_for(
    *,
    key: str,
    subdataset: str,
    image_path: Path,
    common_mask_path: Path,
    specification: dict[str, Any],
    metadata: dict[str, Any],
    data_root: Path,
) -> SampleRecord:
    stem = key.split("/", 1)[1]
    country = str(specification["country"])
    site = str(specification["site"])
    institute = str(specification["institute"])
    year = str(specification["year"])
    return SampleRecord(
        sample_id=f"riceseg:{subdataset}:{stem}",
        image_path=image_path.relative_to(data_root).as_posix(),
        mask_path=common_mask_path.relative_to(data_root).as_posix(),
        split=str(specification["coverage_role"]),
        dataset_id=str(metadata["dataset_id"]),
        field_id="_".join((slug(country), slug(site), slug(institute))),
        session_id="_".join((slug(site), slug(institute), year)),
        capture_date=year,
        platform=str(specification["platform"]),
        sensor=str(specification["sensor"]),
        target_crop_id=int(metadata["target_crop_id"]),
        crop_species=str(metadata["crop_species"]),
        weed_species_optional=str(metadata["weed_species_optional"]),
        growth_stage=";".join(str(stage) for stage in specification["growth_stages"]),
        annotation_exhaustive=bool(metadata["annotation_exhaustive"]),
        license_status=str(metadata["license_status"]),
        commercial_allowed=bool(metadata["commercial_allowed"]),
    )


def tree_sha256(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda candidate: candidate.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            raise FileNotFoundError(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def counter_dict(counter: Counter[int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items())}


def write_manifests(
    records: list[SampleRecord],
    *,
    outputs: dict[str, Any],
    contract: dict[str, Any],
    metadata: dict[str, Any],
    data_root: Path,
) -> dict[str, dict[str, Any]]:
    coverage_path = require_inside(
        data_root / str(outputs["coverage_manifest"]), data_root, "coverage manifest"
    )
    train_path = require_inside(
        data_root / str(outputs["coverage_train_manifest"]),
        data_root,
        "coverage train manifest",
    )
    calibration_path = require_inside(
        data_root / str(outputs["coverage_calibration_manifest"]),
        data_root,
        "coverage calibration manifest",
    )
    transfer_path = require_inside(
        data_root / str(outputs["country_transfer_manifest"]),
        data_root,
        "country-transfer manifest",
    )
    ordered = sorted(records, key=lambda record: record.sample_id)
    train = [record for record in ordered if record.split == "train"]
    calibration = [
        record for record in ordered if record.split == "external_calibration"
    ]
    expected_roles = {
        str(role): int(count) for role, count in contract["coverage_roles"].items()
    }
    require_equal("coverage train records", len(train), expected_roles["train"])
    require_equal(
        "coverage calibration records",
        len(calibration),
        expected_roles["external_calibration"],
    )
    write_manifest(ordered, coverage_path)
    write_manifest(train, train_path)
    write_manifest(calibration, calibration_path)

    transfer = contract["country_transfer"]
    source_countries = {str(country) for country in transfer["source_countries"]}
    target_countries = {str(country) for country in transfer["target_countries"]}
    if source_countries & target_countries:
        raise ValueError("Country-transfer source and target countries overlap")
    country_by_field_prefix = {slug(country): country for country in source_countries | target_countries}
    transfer_records: list[SampleRecord] = []
    transfer_counts: Counter[str] = Counter()
    for record in ordered:
        field_country = record.field_id.split("_", 1)[0]
        if field_country not in country_by_field_prefix:
            raise ValueError(f"Unknown country prefix in {record.field_id}")
        country = country_by_field_prefix[field_country]
        split = "train" if country in source_countries else "external_calibration"
        transfer_counts[split] += 1
        transfer_records.append(
            replace(
                record,
                dataset_id=str(metadata["country_transfer_dataset_id"]),
                sample_id=record.sample_id.replace("riceseg:", "riceseg_country_transfer:", 1),
                split=split,
            )
        )
    require_equal("country-transfer source records", transfer_counts["train"], int(transfer["source_samples"]))
    require_equal(
        "country-transfer target records",
        transfer_counts["external_calibration"],
        int(transfer["target_samples"]),
    )
    write_manifest(transfer_records, transfer_path)

    result: dict[str, dict[str, Any]] = {}
    for name, path, count in (
        ("coverage", coverage_path, len(ordered)),
        ("coverage_train", train_path, len(train)),
        ("coverage_calibration", calibration_path, len(calibration)),
        ("country_transfer", transfer_path, len(transfer_records)),
    ):
        result[name] = {
            "path": str(path),
            "sha256": manifest_sha256(path),
            "samples": count,
        }
    result["coverage"]["role_counts"] = dict(Counter(record.split for record in ordered))
    result["country_transfer"]["role_counts"] = dict(transfer_counts)
    return result


def verify_locked_inputs(
    config_path: Path, config: dict[str, Any]
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    require_equal("conversion schema", config.get("schema_version"), 1)
    freeze = config["freeze"]
    for key in (
        "conversion_before_visual_review",
        "conversion_before_duplicate_audit",
        "conversion_before_model_evaluation",
        "source_masks_must_be_preserved_byte_exact",
    ):
        require_equal(key, freeze.get(key), True)
    require_equal("publisher random split", freeze.get("publisher_random_split_used"), False)
    require_equal("external test created", freeze.get("external_test_created"), False)

    project_root = config_path.parents[2]
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    locked = config["locked_inputs"]
    release_gate_path = locked_path(project_root, locked["release_gate"], "release gate")
    locked_path(project_root, locked["release_inspector"], "release inspector")
    acquisition_path = locked_path(
        data_root, locked["acquisition_receipt"], "acquisition receipt"
    )
    release_path = locked_path(
        data_root, locked["release_inspection_receipt"], "release receipt"
    )
    condition_path = locked_path(
        data_root, locked["condition_strata_receipt"], "condition receipt"
    )
    archive_path = locked_path(data_root, locked["paired_archive"], "paired archive")

    release_gate = load_yaml(release_gate_path)
    metadata_contract = validate_metadata(release_gate)
    acquisition = load_json(acquisition_path)
    release = load_json(release_path)
    conditions = load_json(condition_path)
    require_equal("acquisition status", acquisition.get("status"), "verified")
    require_equal("release status", release.get("status"), "verified")
    require_equal(
        "condition status",
        conditions.get("status"),
        "metadata_strata_verified_against_release_counts",
    )
    require_equal("release paired samples", int(release["paired_samples"]), int(config["contract"]["samples"]))
    require_equal(
        "condition coverage roles",
        {str(key): int(value) for key, value in conditions["coverage_training_roles"].items()},
        {str(key): int(value) for key, value in config["contract"]["coverage_roles"].items()},
    )
    require_equal(
        "release metadata sample count",
        int(metadata_contract["expected_samples"]),
        int(config["contract"]["samples"]),
    )
    require_equal(
        "release/common mapping",
        {int(key): int(value) for key, value in release_gate["ontology"]["common_mapping"].items()},
        {int(key): int(value) for key, value in config["contract"]["common_mapping"].items()},
    )
    return archive_path, release_gate, release, conditions


def convert(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    config = load_yaml(config_path)
    archive_path, release_gate, release_receipt, condition_receipt = verify_locked_inputs(
        config_path, config
    )
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    outputs = config["outputs"]
    contract = config["contract"]
    metadata = config["manifest_metadata"]
    dataset_root = require_inside(
        data_root / str(outputs["dataset_root"]), data_root, "RiceSEG output root"
    )
    image_root = require_inside(
        data_root / str(outputs["images"]), data_root, "RiceSEG image root"
    )
    source_root = require_inside(
        data_root / str(outputs["source_masks"]), data_root, "RiceSEG source-mask root"
    )
    common_root = require_inside(
        data_root / str(outputs["common_masks"]), data_root, "RiceSEG common-mask root"
    )

    free_before = shutil.disk_usage(data_root).free
    minimum_after = int(contract["minimum_free_space_after_conversion_bytes"])
    source_mapping = {
        int(raw): int(common) for raw, common in contract["common_mapping"].items()
    }
    expected_source = Counter(
        {int(raw): int(count) for raw, count in contract["source_class_pixels"].items()}
    )
    expected_common = Counter(
        {int(raw): int(count) for raw, count in contract["common_class_pixels"].items()}
    )
    subdatasets = release_gate["subdatasets"]
    release_contract = release_gate["release_contract"]

    records: list[SampleRecord] = []
    image_paths: list[Path] = []
    source_paths: list[Path] = []
    common_paths: list[Path] = []
    source_pixels: Counter[int] = Counter()
    common_pixels: Counter[int] = Counter()
    source_by_subdataset: dict[str, Counter[int]] = defaultdict(Counter)
    common_by_subdataset: dict[str, Counter[int]] = defaultdict(Counter)
    samples_by_subdataset: Counter[str] = Counter()
    created_files: Counter[str] = Counter()

    with ZipFile(archive_path) as archive:
        rgb_index, mask_index = archive_pair_index(
            archive,
            subdatasets=subdatasets,
            rgb_directory=str(release_contract["rgb_directory"]),
            mask_directory=str(release_contract["mask_directory"]),
        )
        require_equal("RiceSEG pair count", len(rgb_index), int(contract["samples"]))
        projected_bytes = sum(member.file_size for member in rgb_index.values())
        projected_bytes += sum(member.file_size for member in mask_index.values()) * 2
        if free_before - projected_bytes < minimum_after:
            raise OSError(
                "Insufficient space for RiceSEG conversion: "
                f"free={free_before:,}, conservative_output={projected_bytes:,}, "
                f"required_after={minimum_after:,}"
            )

        for key in sorted(rgb_index):
            rgb_member = rgb_index[key]
            mask_member = mask_index[key]
            subdataset = key.split("/", 1)[0]
            specification = subdatasets[subdataset]
            rgb_payload = archive.read(rgb_member)
            source_payload = archive.read(mask_member)
            with Image.open(io.BytesIO(source_payload)) as source_handle:
                source_handle.load()
                source_array = np.asarray(source_handle)
            require_equal(
                f"source mask size {key}",
                (int(source_array.shape[1]), int(source_array.shape[0])),
                (int(contract["width"]), int(contract["height"])),
            )
            common_array = common_from_source(source_array, source_mapping)
            source_counts = np.bincount(
                source_array.astype(np.uint8, copy=False).ravel(), minlength=6
            )
            common_counts = np.bincount(common_array.ravel(), minlength=3)
            source_pixels.update(
                {value: int(count) for value, count in enumerate(source_counts)}
            )
            common_pixels.update(
                {value: int(count) for value, count in enumerate(common_counts)}
            )
            source_by_subdataset[subdataset].update(
                {value: int(count) for value, count in enumerate(source_counts)}
            )
            common_by_subdataset[subdataset].update(
                {value: int(count) for value, count in enumerate(common_counts)}
            )
            samples_by_subdataset[subdataset] += 1

            rgb_name = PurePosixPath(rgb_member.filename).name
            source_name = PurePosixPath(mask_member.filename).name
            image_path = image_root / subdataset / rgb_name
            source_path = source_root / subdataset / source_name
            common_path = common_root / subdataset / f"{PurePosixPath(source_name).stem}.png"
            created_files["images"] += int(write_exact(image_path, rgb_payload))
            created_files["source_masks"] += int(write_exact(source_path, source_payload))
            created_files["common_masks"] += int(
                write_exact(common_path, png_bytes(common_array))
            )
            image_paths.append(image_path)
            source_paths.append(source_path)
            common_paths.append(common_path)
            records.append(
                record_for(
                    key=key,
                    subdataset=subdataset,
                    image_path=image_path,
                    common_mask_path=common_path,
                    specification=specification,
                    metadata=metadata,
                    data_root=data_root,
                )
            )

    require_equal("source class pixels", source_pixels, expected_source)
    require_equal("common class pixels", common_pixels, expected_common)
    require_equal(
        "release receipt source pixels",
        {int(raw): int(count) for raw, count in release_receipt["source_class_pixels"].items()},
        dict(expected_source),
    )
    expected_subdatasets = {
        str(name): int(specification["images"])
        for name, specification in subdatasets.items()
    }
    require_equal("converted subdataset samples", dict(samples_by_subdataset), expected_subdatasets)
    holdouts = {
        name
        for name, specification in subdatasets.items()
        if str(specification["coverage_role"]) == "external_calibration"
    }
    require_equal(
        "coverage holdout subdatasets",
        holdouts,
        set(str(name) for name in contract["coverage_holdout_subdatasets"]),
    )

    manifests = write_manifests(
        records,
        outputs=outputs,
        contract=contract,
        metadata=metadata,
        data_root=data_root,
    )
    free_after = shutil.disk_usage(data_root).free
    if free_after < minimum_after:
        raise OSError(
            f"RiceSEG conversion left insufficient free space: {free_after:,} < {minimum_after:,}"
        )
    receipt_path = require_inside(
        data_root / str(outputs["conversion_receipt"]), data_root, "conversion receipt"
    )
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "dataset_id": metadata["dataset_id"],
        "conversion_config": str(config_path),
        "conversion_config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "locked_inputs": {
            name: {"path": str(specification["path"]), "sha256": str(specification["sha256"])}
            for name, specification in config["locked_inputs"].items()
        },
        "condition_receipt_synthetic_factor_status": condition_receipt[
            "synthetic_factor_selection_status"
        ],
        "samples": len(records),
        "samples_by_subdataset": dict(sorted(samples_by_subdataset.items())),
        "source_class_pixels": counter_dict(source_pixels),
        "common_class_pixels": counter_dict(common_pixels),
        "source_class_pixels_by_subdataset": {
            name: counter_dict(counter)
            for name, counter in sorted(source_by_subdataset.items())
        },
        "common_class_pixels_by_subdataset": {
            name: counter_dict(counter)
            for name, counter in sorted(common_by_subdataset.items())
        },
        "outputs": {
            "dataset_root": str(dataset_root),
            "images": {
                "files": len(image_paths),
                "created_this_run": created_files["images"],
                "tree_sha256": tree_sha256(dataset_root, image_paths),
                "upstream_bytes_preserved": True,
            },
            "source_masks": {
                "files": len(source_paths),
                "created_this_run": created_files["source_masks"],
                "tree_sha256": tree_sha256(dataset_root, source_paths),
                "upstream_bytes_preserved": True,
            },
            "common_masks": {
                "files": len(common_paths),
                "created_this_run": created_files["common_masks"],
                "tree_sha256": tree_sha256(dataset_root, common_paths),
                "derived_only": True,
            },
        },
        "manifests": manifests,
        "protocol_separation": {
            "coverage_and_country_transfer_are_alternative_manifests": True,
            "must_never_be_combined": True,
            "external_test_created": False,
            "model_selection_used": False,
        },
        "source_masks_preserved": True,
        "rgb_reencoded": False,
        "free_space": {
            "before_bytes": free_before,
            "after_bytes": free_after,
            "minimum_after_bytes": minimum_after,
        },
        "passed": True,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(receipt_path)
    return receipt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/riceseg_conversion_gate_v1.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    receipt = convert(arguments.config)
    print(
        json.dumps(
            {"conversion_receipt": str(receipt), "sha256": sha256(receipt)},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
