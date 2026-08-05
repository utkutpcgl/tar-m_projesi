#!/usr/bin/env python3
"""Fetch only selected records from the split CamelinaWeed ZIP release."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import urllib.request
import zipfile

import yaml


CHUNK_BYTES = 8 * 1024 * 1024


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive member: {name}")
    return path


def selected_members(
    archive: zipfile.ZipFile, mode: str
) -> list[zipfile.ZipInfo]:
    allowed = {".json"} if mode == "metadata" else {".jpg", ".json"}
    selected = []
    for info in archive.infolist():
        path = safe_member_path(info.filename)
        if info.is_dir() or "Annotated" not in path.parts:
            continue
        if path.suffix.lower() in allowed:
            selected.append(info)
    return sorted(selected, key=lambda item: item.header_offset)


def member_record_intervals(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    *,
    merge_gap_bytes: int = 4096,
) -> list[tuple[int, int]]:
    ordered = sorted(archive.infolist(), key=lambda item: item.header_offset)
    next_offset = {
        info.header_offset: (
            ordered[index + 1].header_offset
            if index + 1 < len(ordered)
            else archive.start_dir
        )
        for index, info in enumerate(ordered)
    }
    intervals: list[list[int]] = []
    for info in members:
        start = info.header_offset
        end = next_offset[start]
        if end <= start:
            raise ValueError(f"Invalid ZIP record interval: {info.filename}")
        if intervals and start - intervals[-1][1] <= merge_gap_bytes:
            intervals[-1][1] = end
        else:
            intervals.append([start, end])
    return [(start, end) for start, end in intervals]


def split_intervals_by_parts(
    intervals: list[tuple[int, int]],
    part_sizes: list[int],
    *,
    max_chunk_bytes: int | None = None,
) -> list[dict[str, int]]:
    boundaries = [0]
    for size in part_sizes:
        boundaries.append(boundaries[-1] + size)
    chunks: list[dict[str, int]] = []
    for start, end in intervals:
        if start < 0 or end > boundaries[-1] or end <= start:
            raise ValueError(f"Interval outside combined archive: {start}:{end}")
        cursor = start
        while cursor < end:
            part_index = next(
                index
                for index in range(len(part_sizes))
                if boundaries[index] <= cursor < boundaries[index + 1]
            )
            chunk_end = min(end, boundaries[part_index + 1])
            if max_chunk_bytes is not None:
                chunk_end = min(chunk_end, cursor + max_chunk_bytes)
            chunks.append(
                {
                    "part_index": part_index,
                    "global_start": cursor,
                    "global_end": chunk_end,
                    "part_start": cursor - boundaries[part_index],
                    "part_end": chunk_end - boundaries[part_index],
                }
            )
            cursor = chunk_end
    return chunks


def ensure_sparse_index(
    sparse_path: Path,
    combined_size: int,
    last_part_path: Path,
    last_part_offset: int,
) -> None:
    sparse_path.parent.mkdir(parents=True, exist_ok=True)
    if not sparse_path.exists() or sparse_path.stat().st_size != combined_size:
        with sparse_path.open("wb") as stream:
            stream.truncate(combined_size)
    with last_part_path.open("rb") as source, sparse_path.open("r+b", buffering=0) as target:
        target.seek(last_part_offset)
        while chunk := source.read(CHUNK_BYTES):
            target.write(chunk)


def copy_local_range(
    source_path: Path,
    source_start: int,
    source_end: int,
    target_path: Path,
    target_start: int,
) -> None:
    remaining = source_end - source_start
    with source_path.open("rb") as source, target_path.open("r+b", buffering=0) as target:
        source.seek(source_start)
        target.seek(target_start)
        while remaining:
            chunk = source.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                raise EOFError(f"Short local range read from {source_path}")
            target.write(chunk)
            remaining -= len(chunk)


def fetch_http_range(
    url: str,
    start: int,
    end: int,
    target_path: Path,
    target_start: int,
) -> None:
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes={start}-{end - 1}", "User-Agent": "agri-seg/1"},
    )
    expected = end - start
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        if response.status != 206:
            raise RuntimeError(f"Server ignored Range request: HTTP {response.status}")
        content_range = response.headers.get("Content-Range", "")
        if not content_range.startswith(f"bytes {start}-{end - 1}/"):
            raise RuntimeError(f"Unexpected Content-Range: {content_range}")
        with target_path.open("r+b", buffering=0) as target:
            target.seek(target_start)
            remaining = expected
            while remaining:
                chunk = response.read(min(CHUNK_BYTES, remaining))
                if not chunk:
                    raise EOFError(f"Short HTTP range read from {url}")
                target.write(chunk)
                remaining -= len(chunk)
            if response.read(1):
                raise RuntimeError("Range response exceeded requested length")


def extract_and_verify(
    sparse_path: Path,
    members: list[zipfile.ZipInfo],
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tree_digest = hashlib.sha256()
    total_bytes = 0
    with zipfile.ZipFile(sparse_path) as archive:
        by_name = {item.filename: item for item in archive.infolist()}
        for frozen in members:
            info = by_name[frozen.filename]
            relative = safe_member_path(info.filename)
            payload = archive.read(info)
            destination = output_dir.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            tree_digest.update(info.filename.encode("utf-8"))
            tree_digest.update(hashlib.sha256(payload).digest())
            total_bytes += len(payload)
    return {
        "files": len(members),
        "bytes": total_bytes,
        "tree_sha256": tree_digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Range-fetch CamelinaWeed metadata or annotated RGB records."
    )
    parser.add_argument(
        "--config",
        default="configs/data/camelinaweed_acquisition_screen_v1.yaml",
    )
    parser.add_argument("--mode", choices=("metadata", "annotated"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / arguments.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    parts = config["parts"]
    part_sizes = [int(item["size_bytes"]) for item in parts]
    combined_size = int(config["combined_archive"]["size_bytes"])
    if sum(part_sizes) != combined_size:
        raise ValueError("Configured part sizes do not equal combined archive size")

    last_part_path = (project_root / config["local"]["last_part"]).resolve()
    if last_part_path.stat().st_size != part_sizes[-1]:
        raise ValueError("Last part size mismatch")
    if file_digest(last_part_path, "md5") != str(parts[-1]["md5"]):
        raise ValueError("Last part MD5 mismatch")

    sparse_path = (project_root / config["local"]["sparse_index_view"]).resolve()
    ensure_sparse_index(
        sparse_path,
        combined_size,
        last_part_path,
        combined_size - part_sizes[-1],
    )
    with zipfile.ZipFile(sparse_path) as archive:
        members = selected_members(archive, arguments.mode)
        intervals = member_record_intervals(archive, members)
        central_directory_offset = archive.start_dir
        archive_entries = len(archive.infolist())
    chunks = split_intervals_by_parts(
        intervals, part_sizes, max_chunk_bytes=256 * 1024 * 1024
    )

    expected_extract_bytes = sum(item.file_size for item in members)
    remote_bytes = sum(
        item["global_end"] - item["global_start"]
        for item in chunks
        if item["part_index"] != len(parts) - 1
    )
    reserve = int(config["screen_protocol"]["minimum_free_bytes_after_planned_download"])
    free = shutil.disk_usage(sparse_path.parent).free
    if free - remote_bytes - expected_extract_bytes < reserve:
        raise RuntimeError("CamelinaWeed selective acquisition would violate disk reserve")

    def transfer(chunk: dict[str, int]) -> int:
        part_index = chunk["part_index"]
        if part_index == len(parts) - 1:
            copy_local_range(
                last_part_path,
                chunk["part_start"],
                chunk["part_end"],
                sparse_path,
                chunk["global_start"],
            )
        else:
            fetch_http_range(
                str(parts[part_index]["url"]),
                chunk["part_start"],
                chunk["part_end"],
                sparse_path,
                chunk["global_start"],
            )
        return chunk["global_end"] - chunk["global_start"]

    workers = max(1, int(arguments.workers))
    completed_bytes = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(transfer, chunk): chunk for chunk in chunks}
        for future in as_completed(futures):
            completed_bytes += future.result()
            print(
                f"range_bytes_complete={completed_bytes}/{sum(item['global_end'] - item['global_start'] for item in chunks)}",
                flush=True,
            )

    output_dir = project_root / arguments.output_dir
    extraction = extract_and_verify(sparse_path, members, output_dir)
    receipt_path = (project_root / arguments.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "status": "verified",
        "mode": arguments.mode,
        "config": {
            "path": str(config_path.relative_to(project_root)),
            "sha256": file_digest(config_path, "sha256"),
        },
        "archive": {
            "combined_size_bytes": combined_size,
            "central_directory_offset": central_directory_offset,
            "entries": archive_entries,
            "last_part_sha256": file_digest(last_part_path, "sha256"),
        },
        "selection": {
            "members": len(members),
            "uncompressed_bytes": expected_extract_bytes,
            "intervals": [
                {"start": start, "end": end, "bytes": end - start}
                for start, end in intervals
            ],
            "range_chunks": chunks,
            "remote_bytes": remote_bytes,
        },
        "extraction": extraction,
        "output_dir": str(Path(arguments.output_dir)),
        "zip_crc_verified_by_read": True,
        "common_model_training_allowed": False,
        "external_test_used": False,
        "model_selection_used": False,
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
