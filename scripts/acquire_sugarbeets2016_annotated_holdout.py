#!/usr/bin/env python3
"""Acquire the RGB sequence paired with official Sugar Beets 2016 labels."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image


SEQUENCE = "bonirob_2016-05-23-10-37-10_0"
URL = (
    "https://www.ipb.uni-bonn.de/datasets_IJRR2017/raw_data/160523/"
    f"{SEQUENCE}.zip"
)
EXPECTED_BYTES = 1_689_110_596
EXPECTED_ETAG = '"64adc844-553b7d399d995"'
LICENSE = "CC-BY-SA-4.0"
LICENSE_EVIDENCE_URL = "https://www.ipb.uni-bonn.de/data/sugarbeets2016/index.html"
USER_AGENT = "AgriSegSugarBeetsAnnotatedHoldout/1.0"
MASK_PATTERN = re.compile(
    rf"^{re.escape(SEQUENCE)}_frame(?P<index>\d+)_GroundTruth_color\.png$"
)


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
    next_progress = 128 * 1024 * 1024
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
            if size >= next_progress:
                print(f"download_bytes={size}/{EXPECTED_BYTES}", flush=True)
                next_progress += 128 * 1024 * 1024
    if size != EXPECTED_BYTES:
        raise RuntimeError(f"Download size mismatch: {size} != {EXPECTED_BYTES}")
    temporary.replace(output)
    return {"size_bytes": size, "sha256": digest.hexdigest(), "etag": etag}


def annotation_indices(annotation_dir: Path) -> tuple[list[int], list[Path]]:
    masks = sorted(annotation_dir.glob("*_GroundTruth_color.png"))
    indexed: list[tuple[int, Path]] = []
    for mask in masks:
        match = MASK_PATTERN.fullmatch(mask.name)
        if match is None:
            raise RuntimeError(f"Unexpected annotation name: {mask.name}")
        indexed.append((int(match.group("index")), mask))
    indexed.sort(key=lambda item: item[0])
    indices = [index for index, _ in indexed]
    if indices != list(range(23, 306)):
        raise RuntimeError(
            "Expected exactly the frozen contiguous annotation frames 23..305"
        )
    return indices, [mask for _, mask in indexed]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations-dir", required=True)
    parser.add_argument("--annotation-receipt", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    annotation_dir = Path(args.annotations_dir).expanduser().resolve()
    annotation_receipt = Path(args.annotation_receipt).expanduser().resolve()
    if not annotation_receipt.is_file():
        raise FileNotFoundError(annotation_receipt)
    receipt_data = json.loads(annotation_receipt.read_text(encoding="utf-8"))
    if not receipt_data.get("all_acquisition_gates_passed"):
        raise RuntimeError("Annotation acquisition receipt is not accepted")
    indices, masks = annotation_indices(annotation_dir)

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

    selected_root = root / "extracted_annotated_rgb"
    selected_root.mkdir()
    selected_inventory: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as handle:
        infos = handle.infolist()
        if any(not safe_member(info) for info in infos):
            raise RuntimeError("Unsafe ZIP member found")
        bad = handle.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC failure: {bad}")
        by_name = {info.filename: info for info in infos}
        for index, mask in zip(indices, masks, strict=True):
            member = f"{SEQUENCE}/camera/jai/rgb/rgb_{index:05d}.png"
            info = by_name.get(member)
            if info is None:
                raise RuntimeError(f"Missing annotated RGB member: {member}")
            target = selected_root / f"rgb_{index:05d}.png"
            with handle.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
            with Image.open(target) as image:
                image.verify()
            with Image.open(target) as image:
                dimensions = list(image.size)
                mode = image.mode
            if dimensions != [1296, 966] or mode != "RGB":
                raise RuntimeError(
                    f"Unexpected RGB format for frame {index}: {dimensions} {mode}"
                )
            selected_inventory.append(
                {
                    "frame_index": index,
                    "archive_member": member,
                    "rgb_path": str(target),
                    "rgb_sha256": sha256(target),
                    "rgb_size_bytes": target.stat().st_size,
                    "mask_path": str(mask),
                    "mask_sha256": sha256(mask),
                    "mask_size_bytes": mask.stat().st_size,
                    "dimensions": dimensions,
                    "mode": mode,
                    "archive_crc32": f"{info.CRC:08x}",
                }
            )

    suffix_counts = Counter(
        PurePosixPath(info.filename).suffix.lower() or "<none>" for info in infos
    )
    receipt = {
        "schema_version": 1,
        "dataset": "Sugar Beets 2016",
        "sequence": SEQUENCE,
        "source_url": URL,
        "official_dataset_page": LICENSE_EVIDENCE_URL,
        "license": LICENSE,
        "license_evidence": (
            "Official StachnissLab dataset page states that the dataset is "
            "released under Creative Commons CC BY-SA 4.0."
        ),
        "intended_role": "candidate_field_disjoint_real_holdout",
        "role_status": "locked_pending_label_palette_leakage_and_visual_audit",
        "download": transfer,
        "archive": str(archive),
        "archive_sha256": sha256(archive),
        "archive_safe": True,
        "full_crc_passed": True,
        "archive_members": len(infos),
        "archive_suffix_counts": dict(sorted(suffix_counts.items())),
        "annotation_acquisition_receipt": str(annotation_receipt),
        "annotation_acquisition_receipt_sha256": sha256(annotation_receipt),
        "annotated_frames": len(selected_inventory),
        "selected_inventory": selected_inventory,
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
            "full_archive_crc": True,
            "annotation_receipt_accepted": True,
            "frozen_frame_indices_23_through_305": len(indices) == 283,
            "all_rgb_pairs_present": len(selected_inventory) == len(indices),
            "all_rgb_decodable_1296x966": len(selected_inventory) == 283,
            "explicit_reuse_license": True,
        },
    }
    receipt["all_acquisition_pairing_gates_passed"] = all(
        receipt["quality_gates"].values()
    )
    receipt_path = root / "acquisition_pairing_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_acquisition_pairing_gates_passed"]:
        raise RuntimeError(f"Acquisition gates failed; see {receipt_path}")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "archive_sha256": receipt["archive_sha256"],
                "archive_members": receipt["archive_members"],
                "annotated_frames": receipt["annotated_frames"],
                "all_acquisition_pairing_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
