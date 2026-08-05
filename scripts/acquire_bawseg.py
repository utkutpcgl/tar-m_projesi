#!/usr/bin/env python3
"""Preflight, acquire and fail-closed verify the subscription-gated BAWSeg ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Mapping
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from zipfile import ZipFile

import yaml


USER_AGENT = "agri-seg-bawseg-acquisition/1.0"
SHA_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")


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


def load_gate(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Acquisition config must be a mapping")
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported acquisition schema")
    return value


def require_inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must remain under data_root: {resolved}") from exc
    return resolved


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def public_landing(gate: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    url = str(gate["source"]["landing_url"])
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
    text = raw.decode("utf-8", errors="replace")
    missing = [
        snippet
        for snippet in gate["public_page_gate"]["required_snippets"]
        if str(snippet) not in html.unescape(text)
    ]
    if missing:
        raise ValueError(f"BAWSeg landing page contract changed; missing={missing}")
    content_ids = sorted(set(re.findall(r'data-content-id="([0-9]+)"', text)))
    if str(gate["source"]["content_id"]) not in content_ids:
        raise ValueError(f"Expected content id is absent: {content_ids}")
    subscription_required = "Subscription Required" in text
    return text, {
        "landing_url": url,
        "final_url": final_url,
        "content_type": content_type,
        "response_bytes": len(raw),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "content_ids": content_ids,
        "subscription_required": subscription_required,
        "archive_display_name": str(gate["source"]["archive_display_name"]),
        "archive_display_size": str(gate["source"]["archive_display_size"]),
    }


def disk_preflight(gate: Mapping[str, Any]) -> dict[str, Any]:
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    free = shutil.disk_usage(data_root).free
    maximum = int(gate["archive_gate"]["maximum_download_bytes"])
    reserve = int(
        gate["archive_gate"]["minimum_free_space_after_download_bytes"]
    )
    download_space_passed = free - maximum >= reserve
    if not download_space_passed:
        raise OSError(
            "Insufficient space even for bounded archive download: "
            f"free={free:,}, maximum={maximum:,}, reserve={reserve:,}"
        )
    return {
        "data_root": str(data_root),
        "free_bytes": free,
        "maximum_download_bytes": maximum,
        "minimum_free_space_after_download_bytes": reserve,
        "download_space_passed": download_space_passed,
        "extraction_space_status": "unknown_until_zip_central_directory",
    }


def remote_preflight(gate: Mapping[str, Any], config_path: Path) -> Path:
    _, landing = public_landing(gate)
    disk = disk_preflight(gate)
    data_root = Path(str(gate["data_root"])).resolve()
    output = require_inside(
        data_root / str(gate["outputs"]["remote_preflight_receipt"]),
        data_root,
        "remote_preflight_receipt",
    )
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked_authentication",
        "role": "bawseg_public_remote_and_disk_preflight",
        "source": dict(gate["source"]),
        "landing": landing,
        "disk": disk,
        "public_claim_consistency": {
            "archive_display_size": gate["public_page_gate"][
                "reported_archive_display_size"
            ],
            "reported_total_data_volume": gate["public_page_gate"][
                "reported_total_data_volume"
            ],
            "consistent_for_extraction_planning": False,
            "decision": "download_archive_only_then_inspect_central_directory",
        },
        "authentication": {
            "required": True,
            "available_to_this_preflight": False,
            "credential_material_recorded": False,
        },
        "license_review_required": True,
        "training_authorized": False,
        "extraction_authorized": False,
        "external_test_used": False,
        "model_selection_used": False,
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    write_json(output, receipt)
    return output


def safe_member_name(name: str) -> PurePosixPath:
    value = PurePosixPath(name)
    if (
        not name
        or "\x00" in name
        or value.is_absolute()
        or ".." in value.parts
        or "\\" in name
    ):
        raise ValueError(f"Unsafe ZIP member path: {name}")
    return value


def member_is_symlink(external_attr: int) -> bool:
    return ((external_attr >> 16) & 0o170000) == 0o120000


def unique_control_members(
    archive: ZipFile, required: list[str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for basename in required:
        matches = [
            member.filename
            for member in archive.infolist()
            if not member.is_dir() and PurePosixPath(member.filename).name == basename
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one {basename}, found {matches}")
        result[basename] = matches[0]
    return result


def read_control(archive: ZipFile, name: str, maximum: int) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > maximum:
        raise ValueError(f"Control file exceeds bounded size: {name}")
    with archive.open(info) as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError(f"Control file exceeds bounded size: {name}")
    return value


def parse_checksums(raw: bytes) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        raw.decode("utf-8", errors="strict").splitlines(), start=1
    ):
        line = raw_line.strip("\r\n")
        if not line:
            continue
        match = SHA_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"Malformed checksums line {line_number}")
        digest, name = match.groups()
        normalized = safe_member_name(name).as_posix()
        if normalized in checksums:
            raise ValueError(f"Duplicate checksum path: {normalized}")
        checksums[normalized] = digest.lower()
    if not checksums:
        raise ValueError("Internal checksums file is empty")
    return checksums


def strip_common_prefix(name: str, prefix: PurePosixPath) -> str:
    path = PurePosixPath(name)
    if not prefix.parts:
        return path.as_posix()
    try:
        return path.relative_to(prefix).as_posix()
    except ValueError:
        return path.as_posix()


def inspect_archive(
    gate: Mapping[str, Any], config_path: Path, *, full_verify: bool
) -> Path:
    data_root = Path(str(gate["data_root"])).resolve()
    archive_path = require_inside(
        data_root / str(gate["outputs"]["archive"]), data_root, "archive"
    )
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    if archive_path.stat().st_size > int(gate["archive_gate"]["maximum_download_bytes"]):
        raise ValueError("Downloaded archive exceeds frozen maximum size")

    required = [str(value) for value in gate["archive_gate"]["required_control_files"]]
    maximum_control = int(gate["archive_gate"]["max_control_file_bytes"])
    with ZipFile(archive_path) as archive:
        members = archive.infolist()
        for member in members:
            safe_member_name(member.filename)
        symlinks = [
            member.filename
            for member in members
            if member_is_symlink(member.external_attr)
        ]
        if symlinks:
            raise ValueError(f"Archive symlinks are forbidden: {symlinks[:5]}")
        controls = unique_control_members(archive, required)
        control_raw = {
            key: read_control(archive, value, maximum_control)
            for key, value in controls.items()
        }
        manifest_text = control_raw["manifest.csv"].decode("utf-8", errors="strict")
        manifest_reader = csv.DictReader(io.StringIO(manifest_text))
        columns = set(manifest_reader.fieldnames or [])
        expected_columns = set(gate["archive_gate"]["manifest_required_columns"])
        if not expected_columns.issubset(columns):
            raise ValueError(
                f"Manifest columns changed: missing={sorted(expected_columns - columns)}"
            )
        manifest_rows = list(manifest_reader)
        checksums = parse_checksums(control_raw["checksums_sha256.txt"])

        control_path = PurePosixPath(controls["manifest.csv"])
        prefix = control_path.parent
        file_infos = {}
        for member in members:
            if member.is_dir():
                continue
            relative = strip_common_prefix(member.filename, prefix)
            if relative in file_infos:
                raise ValueError(f"Duplicate normalized ZIP member: {relative}")
            file_infos[relative] = member
        missing_checksum_members = sorted(set(checksums) - set(file_infos))
        if missing_checksum_members:
            raise ValueError(
                "Internal checksums reference absent ZIP members: "
                f"{missing_checksum_members[:5]}"
            )
        manifest_paths: set[str] = set()
        for row_number, row in enumerate(manifest_rows, start=2):
            raw_path = str(row.get("relative_path") or "")
            if not raw_path:
                raise ValueError(f"Manifest row {row_number} has no relative_path")
            relative = safe_member_name(raw_path).as_posix()
            if relative in manifest_paths:
                raise ValueError(f"Duplicate manifest path: {relative}")
            manifest_paths.add(relative)
            for field in ("year", "field", "product_type"):
                if not str(row.get(field) or "").strip():
                    raise ValueError(
                        f"Manifest row {row_number} has an empty {field}"
                    )
        missing_manifest_members = sorted(manifest_paths - set(file_infos))
        if missing_manifest_members:
            raise ValueError(
                "Internal manifest references absent ZIP members: "
                f"{missing_manifest_members[:5]}"
            )
        for row_number, row in enumerate(manifest_rows, start=2):
            relative = safe_member_name(str(row["relative_path"])).as_posix()
            try:
                declared_bytes = int(str(row["bytes"]))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Manifest row {row_number} has invalid bytes"
                ) from exc
            actual_bytes = file_infos[relative].file_size
            if declared_bytes != actual_bytes:
                raise ValueError(
                    f"Manifest byte mismatch for {relative}: "
                    f"declared={declared_bytes}, archive={actual_bytes}"
                )
            declared_digest = str(row["sha256"]).lower()
            if re.fullmatch(r"[0-9a-f]{64}", declared_digest) is None:
                raise ValueError(
                    f"Manifest row {row_number} has invalid sha256"
                )
            checksum_digest = checksums.get(relative)
            if checksum_digest is None:
                raise ValueError(f"Manifest path lacks internal checksum: {relative}")
            if declared_digest != checksum_digest:
                raise ValueError(f"Manifest/checksum disagreement: {relative}")

        crc_passed = False
        internal_sha_passed = False
        if full_verify:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"ZIP CRC failure: {bad}")
            crc_passed = True
            for relative, expected_digest in checksums.items():
                with archive.open(file_infos[relative]) as handle:
                    actual = stream_sha256(handle)
                if actual != expected_digest:
                    raise ValueError(f"Internal SHA-256 mismatch: {relative}")
            internal_sha_passed = True

        compressed = sum(member.compress_size for member in members)
        uncompressed = sum(member.file_size for member in members)
        free = shutil.disk_usage(data_root).free
        extraction_reserve = int(
            gate["archive_gate"]["minimum_free_space_after_extraction_bytes"]
        )
        extraction_space_passed = free - uncompressed >= extraction_reserve
        license_bytes = control_raw["LICENSE.txt"]
        license_digest = hashlib.sha256(license_bytes).hexdigest()
        receipt = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "verified" if full_verify else "inspected",
            "role": "bawseg_archive_fail_closed_gate",
            "archive": str(archive_path),
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": sha256(archive_path),
            "members": len(members),
            "files": len(file_infos),
            "compressed_member_bytes": compressed,
            "uncompressed_member_bytes": uncompressed,
            "unsafe_paths": 0,
            "symlinks": 0,
            "control_members": controls,
            "manifest_rows": len(manifest_rows),
            "internal_checksum_entries": len(checksums),
            "full_crc_passed": crc_passed,
            "internal_sha256_passed": internal_sha_passed,
            "free_bytes_at_inspection": free,
            "minimum_free_space_after_extraction_bytes": extraction_reserve,
            "extraction_space_passed": extraction_space_passed,
            "extraction_authorized": bool(full_verify and extraction_space_passed),
            "license": {
                "member": controls["LICENSE.txt"],
                "bytes": len(license_bytes),
                "sha256": license_digest,
                "manual_review_required": True,
                "commercial_allowed": False,
            },
            "training_authorized": False,
            "external_test_used": False,
            "model_selection_used": False,
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256(__file__),
        }
    output_key = "acquisition_receipt" if full_verify else "archive_inspection_receipt"
    output = require_inside(
        data_root / str(gate["outputs"][output_key]), data_root, output_key
    )
    write_json(output, receipt)
    return output


def cookie_opener(cookie_file: Path):
    jar = MozillaCookieJar(str(cookie_file))
    jar.load(ignore_discard=True, ignore_expires=True)
    return build_opener(HTTPCookieProcessor(jar))


def discover_archive_url(page: str, gate: Mapping[str, Any]) -> str | None:
    name = re.escape(str(gate["source"]["archive_display_name"]))
    patterns = (
        rf'<a[^>]+href="([^"]+)"[^>]*>[^<]*{name}',
        rf'<a[^>]+data-download-url="([^"]+)"[^>]*>[^<]*{name}',
    )
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE)
        if match and match.group(1) != "#":
            return html.unescape(match.group(1))
    return None


def download_archive(
    gate: Mapping[str, Any],
    config_path: Path,
    cookie_file: Path,
    explicit_url: str | None,
) -> Path:
    disk_preflight(gate)
    if not cookie_file.is_file():
        raise FileNotFoundError(cookie_file)
    opener = cookie_opener(cookie_file)
    landing_url = str(gate["source"]["landing_url"])
    with opener.open(Request(landing_url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")
    archive_url = explicit_url or discover_archive_url(page, gate)
    if archive_url is None:
        raise PermissionError(
            "Authenticated page did not expose a file URL. Copy the direct BAWSeg "
            "archive URL from the authenticated IEEE DataPort download action and "
            "pass it via --archive-url; do not store it in project files."
        )
    archive_url = urljoin(landing_url, archive_url)
    split = urlsplit(archive_url)
    if split.scheme != "https":
        raise ValueError("BAWSeg archive URL must use HTTPS")

    data_root = Path(str(gate["data_root"])).resolve()
    destination = require_inside(
        data_root / str(gate["outputs"]["archive"]), data_root, "archive"
    )
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    with opener.open(Request(archive_url, headers=headers), timeout=120) as response:
        status = getattr(response, "status", response.getcode())
        if existing and status != 206:
            raise RuntimeError(
                "Server did not honor resume Range; partial file was preserved"
            )
        mode = "ab" if existing else "wb"
        maximum = int(gate["archive_gate"]["maximum_download_bytes"])
        written = existing
        with partial.open(mode) as handle:
            while True:
                block = response.read(8 * 1024 * 1024)
                if not block:
                    break
                written += len(block)
                if written > maximum:
                    raise ValueError("Download exceeded frozen maximum archive size")
                handle.write(block)
    partial.replace(destination)
    return inspect_archive(gate, config_path, full_verify=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/bawseg_acquisition_v1.yaml"),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--download", action="store_true")
    mode.add_argument("--inspect-existing", action="store_true")
    mode.add_argument("--verify-existing", action="store_true")
    parser.add_argument(
        "--cookie-file",
        type=Path,
        help="Netscape-format IEEE cookies stored outside the project",
    )
    parser.add_argument(
        "--archive-url",
        help="Authenticated direct HTTPS URL; never write signed URLs into config",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    gate = load_gate(config_path)
    if args.preflight:
        output = remote_preflight(gate, config_path)
    elif args.download:
        if args.cookie_file is None:
            raise PermissionError("--download requires --cookie-file")
        output = download_archive(
            gate,
            config_path,
            args.cookie_file.expanduser().resolve(),
            args.archive_url,
        )
    elif args.inspect_existing:
        output = inspect_archive(gate, config_path, full_verify=False)
    else:
        output = inspect_archive(gate, config_path, full_verify=True)
    print(json.dumps({"receipt": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
