#!/usr/bin/env python3
"""Acquire one bounded, licensed BoniRob Sugar Beets 2016 sequence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image


URL = (
    "https://www.ipb.uni-bonn.de/datasets_IJRR2017/raw_data/160523/"
    "bonirob_2016-05-23-11-36-43_4.zip"
)
EXPECTED_BYTES = 165_223_274
EXPECTED_ETAG = '"9d91b6a-553b89ddf3e24"'
LICENSE = "CC-BY-SA-4.0"
LICENSE_EVIDENCE_URL = "https://www.ipb.uni-bonn.de/data/sugarbeets2016/index.html"
USER_AGENT = "AgriSegUnseenFieldAudit/1.0"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    unix_mode = (info.external_attr >> 16) & 0o170000
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and unix_mode != 0o120000
    )


def download(output: Path) -> dict[str, Any]:
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    temporary = output.with_suffix(output.suffix + ".part")
    if temporary.exists():
        raise FileExistsError(temporary)
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
        "wb"
    ) as handle:
        etag = response.headers.get("ETag")
        content_length = int(response.headers.get("Content-Length", "-1"))
        if content_length != EXPECTED_BYTES:
            raise RuntimeError(
                f"Content-Length changed: {content_length} != {EXPECTED_BYTES}"
            )
        if etag != EXPECTED_ETAG:
            raise RuntimeError(f"ETag changed: {etag} != {EXPECTED_ETAG}")
        while True:
            block = response.read(4 * 1024 * 1024)
            if not block:
                break
            handle.write(block)
            digest.update(block)
            size += len(block)
    if size != EXPECTED_BYTES:
        raise RuntimeError(f"Download size mismatch: {size} != {EXPECTED_BYTES}")
    temporary.replace(output)
    return {"size_bytes": size, "sha256": digest.hexdigest(), "etag": etag}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = Path(args.output_dir).expanduser().resolve()
    if root.exists():
        raise FileExistsError(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root.parent).free
    required = 3 * EXPECTED_BYTES + 1024**3
    if free < required:
        raise RuntimeError(f"Insufficient disk: need {required}, have {free}")
    root.mkdir()
    archive = root / Path(URL).name
    transfer = download(archive)

    extracted = root / "extracted_images"
    extracted.mkdir()
    member_rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as handle:
        if any(not safe_member(info) for info in handle.infolist()):
            raise RuntimeError("Unsafe ZIP member found")
        bad = handle.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC failure: {bad}")
        for info in handle.infolist():
            member_rows.append(
                {
                    "path": info.filename,
                    "size_bytes": info.file_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )
            suffix = PurePosixPath(info.filename).suffix.lower()
            if info.is_dir() or suffix not in IMAGE_SUFFIXES:
                continue
            target = extracted / PurePosixPath(info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
            with Image.open(target) as image:
                image.verify()
            with Image.open(target) as image:
                dimensions = list(image.size)
                mode = image.mode
            image_rows.append(
                {
                    "member": info.filename,
                    "path": str(target),
                    "relative_path": target.relative_to(root).as_posix(),
                    "size_bytes": target.stat().st_size,
                    "sha256": sha256(target),
                    "dimensions": dimensions,
                    "mode": mode,
                }
            )

    dimension_counts = Counter(tuple(row["dimensions"]) for row in image_rows)
    receipt = {
        "schema_version": 1,
        "dataset": "Sugar Beets 2016",
        "sequence": "bonirob_2016-05-23-11-36-43_4",
        "source_url": URL,
        "official_dataset_page": LICENSE_EVIDENCE_URL,
        "license": LICENSE,
        "license_evidence": (
            "Official StachnissLab dataset page states that the dataset is "
            "released under Creative Commons CC BY-SA 4.0."
        ),
        "intended_role": "unseen_real_video_candidate",
        "selection_metric_role": "unlabeled_temporal_and_qualitative_only",
        "numeric_miou_allowed_without_new_annotations": False,
        "download": transfer,
        "archive": str(archive),
        "archive_sha256": sha256(archive),
        "archive_safe": True,
        "full_crc_passed": True,
        "members": len(member_rows),
        "member_inventory": member_rows,
        "decoded_images": len(image_rows),
        "image_dimensions": {
            f"{width}x{height}": count
            for (width, height), count in sorted(dimension_counts.items())
        },
        "image_inventory": image_rows,
        "capacity_check": {
            "free_bytes_before": free,
            "required_bytes": required,
            "passed": True,
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "quality_gates": {
            "exact_http_size": transfer["size_bytes"] == EXPECTED_BYTES,
            "etag_locked": transfer["etag"] == EXPECTED_ETAG,
            "archive_safe": True,
            "full_crc": True,
            "multiple_decodable_images": len(image_rows) > 1,
            "explicit_reuse_license": True,
        },
    }
    receipt["all_quality_gates_passed"] = all(receipt["quality_gates"].values())
    receipt_path = root / "acquisition_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"Acquisition gates failed; see {receipt_path}")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "archive_sha256": receipt["archive_sha256"],
                "members": receipt["members"],
                "decoded_images": receipt["decoded_images"],
                "image_dimensions": receipt["image_dimensions"],
                "all_quality_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
