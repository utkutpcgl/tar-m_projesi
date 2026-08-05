#!/usr/bin/env python3
"""Acquire and verify the pinned gated RiceSEG repository on the data disk."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

import yaml
from huggingface_hub import HfApi, get_token, snapshot_download


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


def load_gate(path: Path) -> dict[str, Any]:
    gate = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(gate, dict):
        raise ValueError("Acquisition config must be a mapping")
    require_equal("schema_version", gate.get("schema_version"), 1)
    return gate


def expected_files(gate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = gate["expected_repository"]["exact_files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("expected_repository.exact_files must be a non-empty mapping")
    normalized = {str(name): dict(specification) for name, specification in files.items()}
    for name in normalized:
        candidate = PurePosixPath(name)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in name:
            raise ValueError(f"Unsafe expected repository path: {name}")
    expected_total = sum(int(specification["size_bytes"]) for specification in normalized.values())
    require_equal(
        "expected repository total bytes",
        expected_total,
        int(gate["expected_repository"]["total_file_bytes"]),
    )
    return normalized


def remote_preflight(gate: dict[str, Any], token: str | None) -> dict[str, Any]:
    source = gate["source"]
    expected = expected_files(gate)
    api = HfApi(token=token)
    information = api.dataset_info(
        str(source["repository_id"]),
        revision=str(source["revision"]),
        files_metadata=True,
    )
    if gate["quality_gate"]["require_pinned_remote_revision"]:
        require_equal("remote repository revision", information.sha, str(source["revision"]))
    remote = {
        str(sibling.rfilename): int(sibling.size)
        for sibling in information.siblings
        if sibling.size is not None
    }
    if gate["quality_gate"]["require_exact_repository_file_set"]:
        require_equal("remote repository file set", set(remote), set(expected))
    for name, specification in expected.items():
        require_equal(
            f"remote size {name}",
            remote.get(name),
            int(specification["size_bytes"]),
        )

    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    free_bytes = shutil.disk_usage(data_root).free
    download_bytes = int(gate["expected_repository"]["total_file_bytes"])
    reserve_bytes = int(gate["quality_gate"]["minimum_free_space_after_download_bytes"])
    if free_bytes - download_bytes < reserve_bytes:
        raise OSError(
            "Insufficient data-disk space: "
            f"free={free_bytes:,}, download={download_bytes:,}, reserve={reserve_bytes:,}"
        )
    return {
        "repository_id": str(source["repository_id"]),
        "pinned_revision": str(source["revision"]),
        "remote_revision": information.sha,
        "gated": information.gated,
        "remote_files": remote,
        "remote_total_file_bytes": sum(remote.values()),
        "data_root": str(data_root),
        "free_bytes": free_bytes,
        "minimum_free_space_after_download_bytes": reserve_bytes,
        "token_available": bool(token),
        "download_ready": bool(token),
    }


def archive_summary(path: Path, *, full_crc: bool) -> dict[str, int | bool]:
    unsafe: list[str] = []
    links: list[str] = []
    with ZipFile(path) as archive:
        members = archive.infolist()
        for member in members:
            candidate = PurePosixPath(member.filename)
            if candidate.is_absolute() or ".." in candidate.parts or "\\" in member.filename:
                unsafe.append(member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                links.append(member.filename)
        if unsafe:
            raise ValueError(f"Unsafe archive paths in {path}: {unsafe[:5]}")
        if links:
            raise ValueError(f"Archive symlinks in {path}: {links[:5]}")
        bad_member = archive.testzip() if full_crc else None
        if bad_member is not None:
            raise ValueError(f"Archive CRC failure in {path}: {bad_member}")
        return {
            "members": len(members),
            "files": sum(not member.is_dir() for member in members),
            "compressed_bytes": sum(member.compress_size for member in members),
            "uncompressed_bytes": sum(member.file_size for member in members),
            "unsafe_paths": len(unsafe),
            "symlinks": len(links),
            "full_crc_passed": bool(full_crc),
        }


def local_repository_files(repository_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in repository_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repository_dir)
        if relative.parts and relative.parts[0] == ".cache":
            continue
        files[relative.as_posix()] = path
    return files


def verify_local(gate: dict[str, Any], config_path: Path) -> Path:
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    outputs = gate["outputs"]
    repository_dir = require_inside(
        data_root / str(outputs["repository_dir"]), data_root, "repository_dir"
    )
    if not repository_dir.is_dir():
        raise FileNotFoundError(repository_dir)
    expected = expected_files(gate)
    local = local_repository_files(repository_dir)
    if gate["quality_gate"]["require_exact_repository_file_set"]:
        require_equal("local repository file set", set(local), set(expected))

    file_receipts: dict[str, dict[str, Any]] = {}
    archive_receipts: dict[str, dict[str, int | bool]] = {}
    for name, specification in expected.items():
        path = local.get(name)
        if path is None:
            raise FileNotFoundError(repository_dir / name)
        size = path.stat().st_size
        require_equal(f"local size {name}", size, int(specification["size_bytes"]))
        digest = sha256(path)
        if "sha256" in specification:
            require_equal(f"local SHA-256 {name}", digest, str(specification["sha256"]))
        file_receipts[name] = {"size_bytes": size, "sha256": digest}
        if path.suffix.lower() == ".zip":
            archive_receipts[name] = archive_summary(
                path,
                full_crc=bool(gate["quality_gate"]["require_full_archive_crc"]),
            )

    receipt_path = require_inside(
        data_root / str(outputs["acquisition_receipt"]), data_root, "acquisition_receipt"
    )
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "source": {
            "repository_id": str(gate["source"]["repository_id"]),
            "repository_type": str(gate["source"]["repository_type"]),
            "revision": str(gate["source"]["revision"]),
            "gated": str(gate["source"]["gated"]),
            "user_access_conditions_accepted": bool(
                gate["source"]["user_access_conditions_accepted"]
            ),
            "official_dataset_page": str(gate["source"]["official_dataset_page"]),
            "official_repository_page": str(gate["source"]["official_repository_page"]),
            "license_presentation": str(gate["source"]["license_presentation"]),
            "license_note": str(gate["source"]["license_note"]),
        },
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "repository_dir": str(repository_dir),
        "files": file_receipts,
        "total_file_bytes": sum(item["size_bytes"] for item in file_receipts.values()),
        "archives": archive_receipts,
        "archive_safe_paths_passed": True,
        "archive_symlink_gate_passed": True,
        "full_archive_crc_passed": all(
            bool(summary["full_crc_passed"]) for summary in archive_receipts.values()
        ),
        "external_test_used": False,
        "model_selection_used": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(receipt_path)
    return receipt_path


def acquire(gate: dict[str, Any], config_path: Path, workers: int) -> Path:
    if gate["source"]["user_access_conditions_accepted"] is not True:
        raise PermissionError("RiceSEG access conditions are not recorded as accepted")
    token = get_token()
    if gate["quality_gate"]["require_local_huggingface_token"] and not token:
        raise PermissionError(
            "No local Hugging Face token. Run `.venv/bin/python -m "
            "huggingface_hub.commands.huggingface_cli login` from the project "
            "directory; never paste the token into project files."
        )
    remote_preflight(gate, token)
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    repository_dir = require_inside(
        data_root / str(gate["outputs"]["repository_dir"]), data_root, "repository_dir"
    )
    repository_dir.mkdir(parents=True, exist_ok=True)
    source = gate["source"]
    snapshot_download(
        repo_id=str(source["repository_id"]),
        repo_type=str(source["repository_type"]),
        revision=str(source["revision"]),
        local_dir=repository_dir,
        token=token,
        max_workers=workers,
    )
    return verify_local(gate, config_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify the pinned gated RiceSEG repository."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/riceseg_acquisition_v1.yaml"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="Check metadata/disk only")
    mode.add_argument(
        "--verify-existing",
        action="store_true",
        help="Verify an already downloaded repository without network download",
    )
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    config_path = args.config.expanduser().resolve()
    gate = load_gate(config_path)
    if args.preflight:
        result = remote_preflight(gate, get_token())
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    receipt = (
        verify_local(gate, config_path)
        if args.verify_existing
        else acquire(gate, config_path, args.workers)
    )
    print(json.dumps({"acquisition_receipt": str(receipt), "sha256": sha256(receipt)}, indent=2))


if __name__ == "__main__":
    main()
