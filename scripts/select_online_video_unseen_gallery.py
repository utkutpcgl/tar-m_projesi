#!/usr/bin/env python3
"""Materialize and audit a model-uninformed online-video frame selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont

from agri_seg.data import load_rgb_image, to_display_pil
from agri_seg.manifest import manifest_sha256, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/data/online_unseen_video_visual_v1.yaml"


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
            value = (value << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return value


def render_sheet(frames: list[dict[str, Any]], output: Path) -> None:
    columns, cell_width, cell_height, header = 4, 480, 310, 56
    rows = (len(frames) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, header + rows * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((10, 10), "Naio Oz online-video unseen selection", fill="black", font=font)
    draw.text((10, 30), "Local qualitative OOD analysis only; no redistribution or numeric accuracy", fill=(100, 0, 0), font=font)
    for index, row in enumerate(frames):
        x, y = (index % columns) * cell_width, header + (index // columns) * cell_height
        with Image.open(row["path"]) as handle:
            image = handle.convert("RGB")
            image.thumbnail((cell_width - 8, cell_height - 28), Image.Resampling.LANCZOS)
        canvas.paste(image, (x + (cell_width - image.width) // 2, y))
        draw.text((x + 8, y + cell_height - 22), row["label"], fill="black", font=font)
    canvas.save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Online-video config must be schema-v1")
    source_cfg = config["accepted_candidate"]
    source = Path(str(source_cfg["source"])).resolve()
    metadata = Path(str(source_cfg["metadata"])).resolve()
    checkpoint_path = Path(str(config["checkpoint_training_exposure_reference"]["path"])).resolve()
    output = Path(str(config["output"]["directory"])).resolve()
    if output.exists():
        raise FileExistsError(output)
    for path, expected in (
        (source, source_cfg["source_sha256"]),
        (metadata, source_cfg["metadata_sha256"]),
        (checkpoint_path, config["checkpoint_training_exposure_reference"]["sha256"]),
    ):
        if sha256(path) != str(expected):
            raise RuntimeError(f"Locked input changed: {path}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    probe_value = json.loads(probe.stdout)
    video_streams = [row for row in probe_value["streams"] if row.get("codec_type") == "video"]
    if len(video_streams) != 1:
        raise ValueError("Expected exactly one video stream")
    stream = video_streams[0]
    expected_width, expected_height = source_cfg["expected_resolution"]
    if [int(stream["width"]), int(stream["height"])] != [expected_width, expected_height]:
        raise RuntimeError("Online-video resolution changed")
    if abs(float(probe_value["format"]["duration"]) - float(source_cfg["expected_duration_seconds"])) > 0.1:
        raise RuntimeError("Online-video duration changed")

    output.mkdir(parents=True, exist_ok=False)
    frames_root = output / "frames"
    frames_root.mkdir()
    selected: list[dict[str, Any]] = []
    for index, timestamp in enumerate(source_cfg["selected_timestamps_seconds"]):
        path = frames_root / f"frame_{index:03d}_{int(timestamp):04d}s.jpg"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(timestamp), "-i", str(source),
            "-frames:v", "1", "-q:v", "2", "-n", str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Frame extraction failed at {timestamp}s: {result.stderr[-1000:]}")
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            array = np.asarray(image.convert("L"), dtype=np.float32)
        if (width, height) != (expected_width, expected_height):
            raise RuntimeError(f"Extracted frame dimensions changed: {path}")
        selected.append(
            {
                "index": index,
                "timestamp_seconds": float(timestamp),
                "label": f"t={int(timestamp)//60:02d}:{int(timestamp)%60:02d}",
                "path": str(path),
                "sha256": sha256(path),
                "width": width,
                "height": height,
                "grayscale_mean": float(array.mean()),
                "grayscale_std": float(array.std()),
                "dhash64": f"{dhash(path):016x}",
            }
        )

    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    checkpoint_config = payload["config"]
    training_manifest = Path(str(checkpoint_config["manifest"])).resolve()
    data_root = Path(str(checkpoint_config["data_root"])).resolve()
    records = [row for row in read_manifest(training_manifest) if row.split == "train"]
    training_paths = sorted({
        (Path(row.image_path) if Path(row.image_path).is_absolute() else data_root / row.image_path).resolve()
        for row in records
    })
    training_hashes = {sha256(path) for path in training_paths}
    training_dhashes = [dhash(path) for path in training_paths]
    for row in selected:
        if row["sha256"] in training_hashes:
            raise RuntimeError("Online-video frame exactly duplicates a training image")
        perceptual = int(row["dhash64"], 16)
        minimum = min((perceptual ^ value).bit_count() for value in training_dhashes)
        row["minimum_training_dhash_distance"] = minimum
        if minimum <= 2:
            raise RuntimeError("Online-video frame failed the training near-duplicate gate")
    internal_distances = [
        (int(selected[left]["dhash64"], 16) ^ int(selected[right]["dhash64"], 16)).bit_count()
        for left in range(len(selected)) for right in range(left + 1, len(selected))
    ]
    contact = output / "source_contact_sheet.jpg"
    render_sheet(selected, contact)
    conditioning = config["conditioning"]
    policy = config["policy"]
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "source": source_cfg,
        "source_probe": probe_value,
        "selected_count": len(selected),
        "selected_frames": selected,
        "source_contact_sheets": [{"path": str(contact), "sha256": sha256(contact)}],
        "training_manifest": str(training_manifest),
        "training_manifest_sha256": manifest_sha256(training_manifest),
        "training_unique_image_count_audited": len(training_paths),
        "minimum_selected_pair_dhash_distance": min(internal_distances),
        "training_exposure": False,
        "target_crop_id": int(conditioning["target_crop_id"]),
        "crop_species": conditioning["crop_species"],
        "class_interpretation": conditioning["class_interpretation"],
        "numeric_segmentation_accuracy_authorized": policy["numeric_segmentation_accuracy_authorized"],
        "model_selection_score_weight": float(policy["model_selection_score_weight"]),
        "redistribution_authorized": policy["redistribution_authorized"],
        "quality_gates": {
            "locked_inputs_match": True,
            "resolution_and_duration_match": True,
            "all_frames_decode": True,
            "training_exact_and_dhash_duplicate_gate": True,
            "numeric_accuracy_disabled": policy["numeric_segmentation_accuracy_authorized"] is False,
            "selection_weight_zero": float(policy["model_selection_score_weight"]) == 0.0,
            "local_only_policy": policy["redistribution_authorized"] is False,
        },
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt["all_quality_gates_passed"] = all(receipt["quality_gates"].values())
    destination = output / "selection_receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "receipt": str(destination), "selected_count": len(selected),
        "minimum_training_dhash_distance": min(row["minimum_training_dhash_distance"] for row in selected),
        "source_contact_sheet": str(contact), "all_quality_gates_passed": receipt["all_quality_gates_passed"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
