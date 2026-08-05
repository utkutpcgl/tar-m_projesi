#!/usr/bin/env python3
"""Verify and unwrap the pinned Mendeley Weedy Rice UAV release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from zipfile import ZipFile

import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def require_inside(path: Path, root: Path, name: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{name} must remain below data_root: {resolved}") from exc
    return resolved


def archive_summary(archive: ZipFile) -> dict[str, int]:
    members = archive.infolist()
    unsafe: list[str] = []
    links: list[str] = []
    for member in members:
        candidate = PurePosixPath(member.filename)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in member.filename:
            unsafe.append(member.filename)
        file_type = (member.external_attr >> 16) & 0o170000
        if file_type == 0o120000:
            links.append(member.filename)
    if unsafe:
        raise ValueError(f"Unsafe archive paths: {unsafe[:5]}")
    if links:
        raise ValueError(f"Archive symlinks are forbidden: {links[:5]}")
    return {
        "members": len(members),
        "files": sum(not member.is_dir() for member in members),
        "compressed_bytes": sum(member.compress_size for member in members),
        "uncompressed_bytes": sum(member.file_size for member in members),
        "unsafe_paths": len(unsafe),
        "symlinks": len(links),
    }


def copy_and_hash(source: BinaryIO, destination: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    copied = 0
    with destination.open("wb") as output:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            output.write(block)
            digest.update(block)
            copied += len(block)
    return copied, digest.hexdigest()


def stream_hash(source: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    copied = 0
    for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
        digest.update(block)
        copied += len(block)
    return copied, digest.hexdigest()


def load_gate(path: Path) -> dict[str, Any]:
    gate = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError("Acquisition config must be a mapping")
    require_equal("schema_version", gate.get("schema_version"), 1)
    return gate


def audit(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    gate = load_gate(config_path)
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    outer_spec = gate["outer_archive"]
    quality = gate["quality_gate"]
    outputs = gate["outputs"]
    outer_path = require_inside(
        data_root / str(outer_spec["path"]), data_root, "outer archive"
    )
    nested_path = require_inside(
        data_root / str(outputs["nested_archive"]), data_root, "nested archive"
    )
    receipt_path = require_inside(
        data_root / str(outputs["acquisition_receipt"]), data_root, "receipt"
    )
    if not outer_path.is_file():
        raise FileNotFoundError(outer_path)
    require_equal("outer archive size", outer_path.stat().st_size, int(outer_spec["size_bytes"]))

    free_before = shutil.disk_usage(data_root).free
    nested_bytes = int(outer_spec["exact_member_size_bytes"])
    reserve = int(quality["minimum_free_space_after_archive_and_nested_bytes"])
    if not nested_path.exists() and free_before - nested_bytes < reserve:
        raise OSError(
            f"Insufficient data-disk space: free={free_before:,}, "
            f"nested={nested_bytes:,}, reserve={reserve:,}"
        )

    outer_digest = sha256(outer_path)
    nested_digest: str
    outer_crc_passed = False
    with ZipFile(outer_path) as outer:
        summary_outer = archive_summary(outer)
        for field in ("members", "files", "compressed_bytes", "uncompressed_bytes"):
            require_equal(f"outer {field}", summary_outer[field], int(outer_spec[field]))
        names = [member.filename for member in outer.infolist() if not member.is_dir()]
        require_equal("outer exact member set", names, [str(outer_spec["exact_member"])])
        member = outer.getinfo(str(outer_spec["exact_member"]))
        require_equal("nested member size", member.file_size, nested_bytes)

        if nested_path.exists():
            require_equal("existing nested archive size", nested_path.stat().st_size, nested_bytes)
            nested_digest = sha256(nested_path)
            with outer.open(member) as source:
                member_bytes, member_digest = stream_hash(source)
            require_equal("streamed nested member bytes", member_bytes, nested_bytes)
            require_equal(
                "existing nested archive SHA-256",
                nested_digest,
                member_digest,
            )
            outer_crc_passed = True
        else:
            nested_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = nested_path.with_suffix(nested_path.suffix + ".part")
            with outer.open(member) as source:
                copied, nested_digest = copy_and_hash(source, temporary)
            require_equal("extracted nested bytes", copied, nested_bytes)
            temporary.replace(nested_path)
            outer_crc_passed = True

    with ZipFile(nested_path) as nested:
        summary_nested = archive_summary(nested)
        bad_nested = nested.testzip() if bool(quality["require_full_nested_crc"]) else None
        if bad_nested is not None:
            raise ValueError(f"Nested archive CRC failure: {bad_nested}")
    nested_crc_passed = bool(quality["require_full_nested_crc"])

    free_after = shutil.disk_usage(data_root).free
    if free_after < reserve:
        raise OSError(f"Data-disk reserve violated after audit: {free_after:,} < {reserve:,}")
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "source": gate["source"],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "outer_archive": {
            "path": str(outer_path),
            "size_bytes": outer_path.stat().st_size,
            "sha256": outer_digest,
            "etag": str(outer_spec["etag"]),
            "summary": summary_outer,
            "full_crc_passed": outer_crc_passed,
        },
        "nested_archive": {
            "path": str(nested_path),
            "size_bytes": nested_path.stat().st_size,
            "sha256": nested_digest,
            "summary": summary_nested,
            "full_crc_passed": nested_crc_passed,
        },
        "disk": {
            "free_bytes_before_nested": free_before,
            "free_bytes_after_audit": free_after,
            "minimum_required_free_bytes_after": reserve,
        },
        "external_test_used": bool(quality["external_test_used"]),
        "model_selection_used": bool(quality["model_selection_used"]),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_receipt = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary_receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_receipt.replace(receipt_path)
    return receipt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/weedy_rice_uav_acquisition_v1.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    receipt = audit(args.config)
    print(json.dumps({"receipt": str(receipt), "sha256": sha256(receipt)}, indent=2))


if __name__ == "__main__":
    main()
