#!/usr/bin/env python3
"""Select a day-balanced, training-unseen FarmBot qualitative gallery."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from PIL import Image, ImageDraw, ImageFont

from agri_seg.data import load_rgb_image, to_display_pil
from agri_seg.manifest import manifest_sha256, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = PROJECT_ROOT / "data/processed/audits/farmbot_soy_unseen_v4/acquisition_and_archive_audit.json"
DEFAULT_CHECKPOINT = PROJECT_ROOT / "data/runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt"
DAY_PATTERN = re.compile(r"(?:^|/)Unannotated Dataset/Day (\d+)/")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dhash(path: str | Path) -> int:
    image = to_display_pil(load_rgb_image(path))
    pixels = list(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(
                pixels[row * 9 + column] > pixels[row * 9 + column + 1]
            )
    return value


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def image_natural_key(item: dict[str, Any]) -> tuple[int, str]:
    stem = Path(str(item["relative_path"])).stem
    match = re.search(r"-(\d+)$", stem)
    return (int(match.group(1)) if match else 10**9, stem)


def render_sheet(rows: list[dict[str, Any]], output: Path, title: str) -> None:
    columns, cell_width, cell_height = 4, 420, 285
    header = 58
    rows_count = (len(rows) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, header + rows_count * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((12, 10), title, fill="black", font=font)
    draw.text(
        (12, 30),
        "Distributed source release: 1600x1200; qualitative only; 2 frames/day",
        fill=(70, 70, 70),
        font=font,
    )
    for index, row in enumerate(rows):
        x = (index % columns) * cell_width
        y = header + (index // columns) * cell_height
        with Image.open(row["path"]) as image:
            rgb = image.convert("RGB")
            rgb.thumbnail((cell_width - 12, cell_height - 34), Image.Resampling.LANCZOS)
            px = x + (cell_width - rgb.width) // 2
            py = y + 2
            canvas.paste(rgb, (px, py))
        label = f"Day {row['day']:02d} | {Path(row['path']).name}"
        draw.text((x + 8, y + cell_height - 25), label, fill="black", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data/processed/audits/farmbot_soy_unseen_v4/gallery_selection_v1"))
    parser.add_argument("--per-day", type=int, default=2)
    args = parser.parse_args()
    audit_path = Path(args.audit).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    output = Path(args.output_dir).resolve()
    receipt_path = output / "selection_receipt.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("all_quality_gates_passed") is not True:
        raise RuntimeError("FarmBot acquisition audit is not accepted")
    policy = audit["policy"]
    if (
        policy.get("training_authorized") is not False
        or policy.get("numeric_segmentation_accuracy_authorized") is not False
        or float(policy.get("model_selection_score_weight", -1)) != 0.0
    ):
        raise RuntimeError("FarmBot qualitative-only policy changed")

    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = payload["config"]
    training_manifest = Path(str(config["manifest"])).resolve()
    data_root = Path(str(config["data_root"])).resolve()
    training_records = [row for row in read_manifest(training_manifest) if row.split == "train"]
    training_paths = sorted(
        {
            (Path(row.image_path) if Path(row.image_path).is_absolute() else data_root / row.image_path).resolve()
            for row in training_records
        }
    )
    training_sha: set[str] = set()
    training_dhash: list[int] = []
    for path in training_paths:
        training_sha.add(sha256(path))
        training_dhash.append(dhash(path))

    by_day: dict[int, list[dict[str, Any]]] = {}
    for item in audit["decoded_inventory"]["high_resolution_rgb_photos"]:
        relative = str(item["relative_path"])
        match = DAY_PATTERN.search(relative)
        if match:
            by_day.setdefault(int(match.group(1)), []).append(dict(item))
    if sorted(by_day) != list(range(1, 21)):
        raise ValueError(f"Expected FarmBot days 1..20, found {sorted(by_day)}")

    selected: list[dict[str, Any]] = []
    selected_hashes: set[str] = set()
    selected_dhashes: list[int] = []
    rejected = Counter()
    for day, items in sorted(by_day.items()):
        candidates = sorted(items, key=image_natural_key)
        targets = [(slot + 0.5) * len(candidates) / args.per_day for slot in range(args.per_day)]
        day_selected: list[dict[str, Any]] = []
        for target in targets:
            ranked = sorted(
                enumerate(candidates), key=lambda pair: (abs(pair[0] - target), pair[0])
            )
            chosen = None
            for _, item in ranked:
                digest = str(item["sha256"])
                if digest in training_sha:
                    rejected["exact_training_duplicate"] += 1
                    continue
                if digest in selected_hashes:
                    rejected["duplicate_selected_sha256"] += 1
                    continue
                perceptual = dhash(item["path"])
                minimum_training_distance = min(
                    hamming(perceptual, value) for value in training_dhash
                )
                if minimum_training_distance <= 2:
                    rejected["training_dhash_distance_le_2"] += 1
                    continue
                if selected_dhashes and min(
                    hamming(perceptual, value) for value in selected_dhashes
                ) <= 2:
                    rejected["selected_dhash_distance_le_2"] += 1
                    continue
                chosen = {
                    "day": day,
                    "path": str(Path(item["path"]).resolve()),
                    "relative_path": item["relative_path"],
                    "sha256": digest,
                    "dhash64": f"{perceptual:016x}",
                    "minimum_training_dhash_distance": minimum_training_distance,
                    "width": int(item["width"]),
                    "height": int(item["height"]),
                }
                selected_hashes.add(digest)
                selected_dhashes.append(perceptual)
                day_selected.append(chosen)
                selected.append(chosen)
                break
            if chosen is None:
                raise RuntimeError(f"Could not select {args.per_day} unseen frames for day {day}")
        if len(day_selected) != args.per_day:
            raise RuntimeError(f"Day {day} selection count changed")

    if len(selected) != len(by_day) * args.per_day:
        raise RuntimeError("FarmBot selection cardinality changed")
    output.mkdir(parents=True, exist_ok=True)
    sheets: list[dict[str, Any]] = []
    for page, start in enumerate(range(0, len(selected), 20), start=1):
        path = output / f"source_contact_sheet_{page:02d}.jpg"
        render_sheet(selected[start : start + 20], path, f"FarmBot Soy unseen source | page {page}")
        sheets.append({"path": str(path), "sha256": sha256(path)})

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_audit": str(audit_path),
        "source_audit_sha256": sha256(audit_path),
        "checkpoint_training_exposure_reference": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "checkpoint_experiment": config.get("experiment"),
        "checkpoint_seed": config.get("seed"),
        "training_manifest": str(training_manifest),
        "training_manifest_sha256": manifest_sha256(training_manifest),
        "training_unique_image_count_audited": len(training_paths),
        "selection_policy": {
            "source_subset": "publisher_unannotated_high_resolution_RGB_only",
            "days": sorted(by_day),
            "frames_per_day": args.per_day,
            "within_day_policy": "nearest valid candidates to equal-width bin centers",
            "exact_training_duplicate_forbidden": True,
            "minimum_dhash64_hamming_distance_from_training": 3,
            "minimum_dhash64_hamming_distance_within_selection": 3,
        },
        "candidate_counts_by_day": {str(day): len(rows) for day, rows in sorted(by_day.items())},
        "rejection_counts": dict(sorted(rejected.items())),
        "selected_count": len(selected),
        "selected_frames": selected,
        "source_contact_sheets": sheets,
        "training_exposure": False,
        "numeric_segmentation_accuracy_authorized": False,
        "model_selection_score_weight": 0.0,
        "target_crop_id": int(audit["source"]["target_crop_id"]),
        "crop_species": audit["source"]["crop_species"],
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    temporary = receipt_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    temporary.replace(receipt_path)
    print(json.dumps({
        "receipt": str(receipt_path),
        "selected_count": len(selected),
        "days": len(by_day),
        "training_images_audited": len(training_paths),
        "source_contact_sheets": sheets,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
