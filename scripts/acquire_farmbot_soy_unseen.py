#!/usr/bin/env python3
"""Download and fail-closed audit the CC-BY FarmBot soybean unseen set.

The publisher's download is a single-member wrapper ZIP containing the actual
dataset ZIP.  Schema-v2 configs declare that structure explicitly; neither ZIP
is extracted until its paths, member types, sizes and CRCs pass inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from zipfile import ZipFile

import yaml
from PIL import Image

from agri_seg.prepare import download_with_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/data/farmbot_soy_unseen_v4.yaml"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 4:
        raise ValueError("FarmBot unseen config must be a schema-v4 mapping")
    return value


def inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Output escapes data_root: {candidate}")
    return candidate


def safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError(f"Unsafe ZIP member: {name!r}")
    return path


def is_symlink(external_attr: int) -> bool:
    return stat.S_ISLNK((external_attr >> 16) & 0xFFFF)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def inspect_archive(
    archive_path: Path,
    extracted_root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    gates = config["gates"]
    maximum_members = int(gates["maximum_members"])
    maximum_uncompressed = int(gates["maximum_uncompressed_bytes"])
    allowed = {str(value).lower() for value in gates["allowed_file_suffixes"]}
    quarantine = config["metadata_quarantine"]
    prefixes = tuple(str(value) for value in quarantine["path_prefixes"])
    basenames = {str(value) for value in quarantine["basenames"]}
    with ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members or len(members) > maximum_members:
            raise ValueError(f"Unexpected member count: {len(members)}")
        names: set[str] = set()
        suffixes: Counter[str] = Counter()
        uncompressed = 0
        regular_files = 0
        quarantined_members = 0
        quarantined_bytes = 0
        quarantine_reasons: Counter[str] = Counter()
        for member in members:
            normalized = safe_name(member.filename).as_posix()
            if normalized in names:
                raise ValueError(f"Duplicate ZIP member: {normalized}")
            names.add(normalized)
            if is_symlink(member.external_attr):
                raise ValueError(f"ZIP symlink is forbidden: {normalized}")
            basename = PurePosixPath(normalized.rstrip("/")).name
            quarantine_reason = None
            if normalized.startswith(prefixes):
                quarantine_reason = "publisher_macos_resource_fork"
            elif basename in basenames:
                quarantine_reason = "publisher_desktop_metadata"
            if quarantine_reason is not None:
                quarantined_members += 1
                quarantined_bytes += int(member.file_size)
                quarantine_reasons[quarantine_reason] += 1
                continue
            if member.is_dir():
                continue
            regular_files += 1
            suffix = PurePosixPath(normalized).suffix.lower()
            if suffix not in allowed:
                raise ValueError(f"Unexpected member suffix {suffix}: {normalized}")
            suffixes[suffix] += 1
            uncompressed += int(member.file_size)
        if quarantined_members > int(quarantine["maximum_members"]):
            raise ValueError(
                f"Metadata quarantine member cap exceeded: {quarantined_members}"
            )
        if quarantined_bytes > int(quarantine["maximum_uncompressed_bytes"]):
            raise ValueError(
                f"Metadata quarantine byte cap exceeded: {quarantined_bytes}"
            )
        if uncompressed > maximum_uncompressed:
            raise ValueError(
                f"Uncompressed archive exceeds gate: {uncompressed:,}"
            )
        free = shutil.disk_usage(extracted_root.parent).free
        reserve = int(gates["minimum_free_bytes_after_extraction"])
        if free - uncompressed < reserve:
            raise OSError(
                f"Insufficient extraction reserve: free={free:,}, "
                f"uncompressed={uncompressed:,}, reserve={reserve:,}"
            )
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"ZIP CRC failure: {bad_member}")
        return {
            "member_count": len(members),
            "regular_file_count": regular_files,
            "suffix_counts": dict(sorted(suffixes.items())),
            "uncompressed_bytes": uncompressed,
            "quarantined_member_count": quarantined_members,
            "quarantined_uncompressed_bytes": quarantined_bytes,
            "quarantine_reason_counts": dict(sorted(quarantine_reasons.items())),
            "metadata_quarantine_gate_passed": True,
            "safe_paths_passed": True,
            "no_symlinks_passed": True,
            "unique_members_passed": True,
            "allowed_suffixes_passed": True,
            "capacity_gate_passed": True,
            "full_crc_passed": True,
        }


def inspect_outer_archive(archive_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    nested = config["nested_archive"]
    expected_member = str(nested["outer_member"])
    expected_bytes = int(nested["expected_uncompressed_bytes"])
    with ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) != 1:
            raise ValueError(f"Outer ZIP must have one member, found {len(members)}")
        member = members[0]
        normalized = safe_name(member.filename).as_posix()
        if normalized != expected_member:
            raise ValueError(
                f"Unexpected nested member: {normalized!r}; expected {expected_member!r}"
            )
        if member.is_dir() or is_symlink(member.external_attr):
            raise ValueError("Nested archive member must be a regular file")
        if PurePosixPath(normalized).suffix.lower() != ".zip":
            raise ValueError("Declared nested archive is not a ZIP")
        if int(member.file_size) != expected_bytes:
            raise ValueError(
                f"Unexpected nested archive size: {member.file_size:,}; "
                f"expected {expected_bytes:,}"
            )
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Outer ZIP CRC failure: {bad_member}")
        return {
            "member_count": 1,
            "nested_member": normalized,
            "nested_uncompressed_bytes": int(member.file_size),
            "safe_path_passed": True,
            "regular_file_passed": True,
            "expected_size_passed": True,
            "full_crc_passed": True,
        }


def extract_nested_archive(
    outer_path: Path, nested_path: Path, member_name: str
) -> None:
    nested_path.parent.mkdir(parents=True, exist_ok=True)
    if nested_path.exists():
        raise FileExistsError(f"Refusing existing nested archive: {nested_path}")
    temporary = nested_path.with_suffix(nested_path.suffix + ".partial")
    if temporary.exists():
        raise FileExistsError(f"Refusing stale partial nested archive: {temporary}")
    with ZipFile(outer_path) as archive, archive.open(member_name) as source:
        with temporary.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
    temporary.replace(nested_path)


def extract_archive(
    archive_path: Path, destination: Path, config: Mapping[str, Any]
) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing non-empty extraction target: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    quarantine = config["metadata_quarantine"]
    prefixes = tuple(str(value) for value in quarantine["path_prefixes"])
    basenames = {str(value) for value in quarantine["basenames"]}
    with ZipFile(archive_path) as archive:
        for member in archive.infolist():
            relative = safe_name(member.filename)
            normalized = relative.as_posix()
            basename = PurePosixPath(normalized.rstrip("/")).name
            if normalized.startswith(prefixes) or basename in basenames:
                continue
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=4 * 1024 * 1024)


def verify_existing_extraction(
    root: Path, config: Mapping[str, Any], archive_report: Mapping[str, Any]
) -> dict[str, Any]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    allowed = {str(value).lower() for value in config["gates"]["allowed_file_suffixes"]}
    quarantine = config["metadata_quarantine"]
    prefixes = tuple(str(value) for value in quarantine["path_prefixes"])
    basenames = {str(value) for value in quarantine["basenames"]}
    regular_files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Extracted symlink is forbidden: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(prefixes) or path.name in basenames:
            raise ValueError(f"Quarantined metadata was extracted: {relative}")
        if path.suffix.lower() not in allowed:
            raise ValueError(f"Unexpected extracted suffix: {relative}")
        regular_files += 1
        total_bytes += path.stat().st_size
    expected_files = int(archive_report["regular_file_count"])
    expected_bytes = int(archive_report["uncompressed_bytes"])
    if regular_files != expected_files or total_bytes != expected_bytes:
        raise RuntimeError(
            "Existing extraction differs from accepted archive members: "
            f"files={regular_files}/{expected_files}, bytes={total_bytes}/{expected_bytes}"
        )
    return {
        "regular_file_count": regular_files,
        "total_bytes": total_bytes,
        "matches_accepted_archive_members": True,
        "no_symlinks": True,
        "no_quarantined_metadata": True,
        "allowed_suffixes_only": True,
    }


def decode_inventory(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    image_paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not image_paths:
        raise ValueError("Extracted FarmBot release has no images")
    modes: Counter[str] = Counter()
    dimensions: Counter[str] = Counter()
    corrupt: list[str] = []
    rgb_photos: list[dict[str, Any]] = []
    photo_gate = config["photo_gate"]
    required_marker = str(photo_gate["required_relative_path_marker"])
    minimum_width = int(photo_gate["minimum_width"])
    minimum_height = int(photo_gate["minimum_height"])
    for path in image_paths:
        try:
            with Image.open(path) as image:
                image.load()
                mode = str(image.mode)
                width, height = image.size
        except Exception:
            corrupt.append(str(path))
            continue
        modes[mode] += 1
        dimensions[f"{width}x{height}"] += 1
        relative = path.relative_to(root).as_posix()
        if (
            mode in {"RGB", "RGBA"}
            and width >= minimum_width
            and height >= minimum_height
            and required_marker in relative
        ):
            rgb_photos.append(
                {
                    "path": str(path.resolve()),
                    "relative_path": relative,
                    "bytes": path.stat().st_size,
                    "width": width,
                    "height": height,
                    "mode": mode,
                    "sha256": sha256(path),
                }
            )
    if corrupt:
        raise ValueError(f"Image decode failures: {corrupt[:5]}")
    if not rgb_photos:
        raise ValueError("No FarmBot photographs satisfy the declared photo gate")
    return {
        "decoded_image_count": len(image_paths),
        "decode_failures": corrupt,
        "mode_counts": dict(sorted(modes.items())),
        "dimension_counts": dict(sorted(dimensions.items())),
        "high_resolution_rgb_photo_count": len(rgb_photos),
        "high_resolution_rgb_photos": rgb_photos,
        "photo_gate": dict(photo_gate),
        "all_images_decoded": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    archive_path = inside(data_root, str(config["outputs"]["archive"]))
    nested_archive_path = inside(
        data_root, str(config["outputs"]["nested_archive"])
    )
    extracted_root = inside(data_root, str(config["outputs"]["extracted"]))
    audit_path = inside(data_root, str(config["outputs"]["audit"]))
    expected = int(config["source"]["expected_archive_bytes"])
    reserve = int(config["gates"]["minimum_free_bytes_after_download"])
    free_before = shutil.disk_usage(data_root).free
    if free_before - expected < reserve:
        raise OSError(
            f"Insufficient download reserve: free={free_before:,}, "
            f"expected={expected:,}, reserve={reserve:,}"
        )
    if audit_path.exists():
        if not args.reuse:
            raise FileExistsError(audit_path)
        existing = json.loads(audit_path.read_text(encoding="utf-8"))
        if sha256(archive_path) != existing["archive_sha256"]:
            raise RuntimeError("Existing FarmBot archive changed")
        print(json.dumps(existing, indent=2, sort_keys=True))
        return

    download_with_resume(
        str(config["source"]["download_url"]), archive_path, expected_size=expected
    )
    archive_hash = sha256(archive_path)
    outer_report = inspect_outer_archive(archive_path, config)
    if nested_archive_path.exists():
        if not bool(config["nested_archive"].get("reuse_if_hash_matches", False)):
            raise FileExistsError(f"Refusing existing nested archive: {nested_archive_path}")
        if sha256(nested_archive_path) != str(
            config["nested_archive"]["expected_sha256"]
        ):
            raise RuntimeError("Existing nested archive hash changed")
    else:
        extract_nested_archive(
            archive_path,
            nested_archive_path,
            str(config["nested_archive"]["outer_member"]),
        )
    if nested_archive_path.stat().st_size != int(
        config["nested_archive"]["expected_uncompressed_bytes"]
    ):
        raise RuntimeError("Extracted nested archive changed size")
    nested_archive_hash = sha256(nested_archive_path)
    archive_report = inspect_archive(nested_archive_path, extracted_root, config)
    if extracted_root.exists() and any(extracted_root.iterdir()):
        if not bool(config["outputs"].get("reuse_existing_extraction", False)):
            raise FileExistsError(f"Refusing non-empty extraction target: {extracted_root}")
        extraction_report = verify_existing_extraction(
            extracted_root, config, archive_report
        )
    else:
        extract_archive(nested_archive_path, extracted_root, config)
        extraction_report = verify_existing_extraction(
            extracted_root, config, archive_report
        )
    decoded = decode_inventory(extracted_root, config)
    policy = dict(config["policy"])
    quality_gates = {
        "archive_expected_size": archive_path.stat().st_size == expected,
        "outer_archive_safe_and_crc_verified": all(
            outer_report[key]
            for key in (
                "safe_path_passed",
                "regular_file_passed",
                "expected_size_passed",
                "full_crc_passed",
            )
        ),
        "nested_archive_safe_and_crc_verified": all(
            archive_report[key]
            for key in (
                "safe_paths_passed",
                "no_symlinks_passed",
                "unique_members_passed",
                "allowed_suffixes_passed",
                "capacity_gate_passed",
                "full_crc_passed",
                "metadata_quarantine_gate_passed",
            )
        ),
        "all_images_decoded": decoded["all_images_decoded"],
        "high_resolution_rgb_photos_present": decoded[
            "high_resolution_rgb_photo_count"
        ]
        > 0,
        "minimum_declared_photo_count_met": decoded[
            "high_resolution_rgb_photo_count"
        ]
        >= int(config["photo_gate"]["minimum_photo_count"]),
        "existing_or_new_extraction_matches_archive": extraction_report[
            "matches_accepted_archive_members"
        ],
        "training_disabled": policy["training_authorized"] is False,
        "numeric_accuracy_disabled": policy[
            "numeric_segmentation_accuracy_authorized"
        ]
        is False,
        "selection_weight_zero": float(policy["model_selection_score_weight"])
        == 0.0,
    }
    receipt = {
        "schema_version": 4,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": config["source"],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "archive": str(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "archive_sha256": archive_hash,
        "outer_archive_report": outer_report,
        "nested_archive": str(nested_archive_path),
        "nested_archive_bytes": nested_archive_path.stat().st_size,
        "nested_archive_sha256": nested_archive_hash,
        "extracted_root": str(extracted_root),
        "disk_free_before_download_bytes": free_before,
        "archive_report": archive_report,
        "extraction_report": extraction_report,
        "decoded_inventory": decoded,
        "policy": policy,
        "quality_gates": quality_gates,
        "all_quality_gates_passed": all(quality_gates.values()),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    write_json(audit_path, receipt)
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"FarmBot unseen gates failed; see {audit_path}")
    print(
        json.dumps(
            {
                "audit": str(audit_path),
                "archive_sha256": archive_hash,
                "nested_archive_sha256": nested_archive_hash,
                "outer_archive_report": outer_report,
                "archive_report": archive_report,
                "decoded_image_count": decoded["decoded_image_count"],
                "high_resolution_rgb_photo_count": decoded[
                    "high_resolution_rgb_photo_count"
                ],
                "all_quality_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
