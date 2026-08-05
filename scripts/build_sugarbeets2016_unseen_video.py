#!/usr/bin/env python3
"""Materialize the licensed BoniRob JAI RGB stream as an auditable video."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


TIMESTAMP_SUFFIX = "/camera/jai/timestamp/timestamps.txt"
RGB_MARKER = "/camera/jai/rgb/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr[-4000:]}"
        )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object from command")
    return value


def fit_inside(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", size, (238, 238, 238))
    rendered = image.convert("RGB")
    rendered.thumbnail(size, Image.Resampling.LANCZOS)
    x = (size[0] - rendered.width) // 2
    y = (size[1] - rendered.height) // 2
    tile.paste(rendered, (x, y))
    return tile


def build_contact_sheet(
    frames: list[Path], timestamps: list[float], output: Path
) -> list[dict[str, Any]]:
    columns = 4
    sample_count = min(8, len(frames))
    if sample_count == 1:
        indices = [0]
    else:
        indices = [
            round(position * (len(frames) - 1) / (sample_count - 1))
            for position in range(sample_count)
        ]
    tile_size = (324, 242)
    label_height = 30
    rows = (len(indices) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (columns * tile_size[0], rows * (tile_size[1] + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    sampled: list[dict[str, Any]] = []
    for position, index in enumerate(indices):
        frame = frames[index]
        with Image.open(frame) as handle:
            tile = fit_inside(handle, tile_size)
        column = position % columns
        row = position // columns
        x = column * tile_size[0]
        y = row * (tile_size[1] + label_height)
        canvas.paste(tile, (x, y + label_height))
        offset = timestamps[index] - timestamps[0]
        draw.text(
            (x + 5, y + 8),
            f"{frame.stem} | source t={offset:.3f}s",
            fill=(0, 0, 0),
        )
        sampled.append(
            {
                "index": index,
                "path": str(frame),
                "sha256": sha256(frame),
                "timestamp": timestamps[index],
                "offset_seconds": offset,
            }
        )
    canvas.save(output, optimize=True)
    return sampled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acquisition_root")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    root = Path(arguments.acquisition_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)
    acquisition_path = root / "acquisition_receipt.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    if acquisition.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Acquisition receipt did not pass all gates")
    archive = Path(acquisition["archive"]).resolve()
    if sha256(archive) != acquisition["archive_sha256"]:
        raise RuntimeError("Archive SHA-256 changed after acquisition")

    inventory = {
        Path(row["path"]).resolve(): row
        for row in acquisition["image_inventory"]
        if RGB_MARKER in row["member"]
    }
    frames = sorted(inventory)
    if len(frames) != 31:
        raise RuntimeError(f"Expected exactly 31 JAI RGB frames, found {len(frames)}")
    expected_names = [f"rgb_{index:05d}.png" for index in range(len(frames))]
    if [frame.name for frame in frames] != expected_names:
        raise RuntimeError("JAI RGB frame sequence is not contiguous")
    for frame in frames:
        row = inventory[frame]
        if sha256(frame) != row["sha256"]:
            raise RuntimeError(f"Frame changed after acquisition: {frame}")
        with Image.open(frame) as handle:
            if handle.size != (1296, 966) or handle.mode != "RGB":
                raise RuntimeError(
                    f"Unexpected JAI RGB format for {frame}: {handle.size}/{handle.mode}"
                )

    with zipfile.ZipFile(archive) as handle:
        matches = [
            name for name in handle.namelist() if name.endswith(TIMESTAMP_SUFFIX)
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one JAI timestamp member, found {matches}")
        timestamp_bytes = handle.read(matches[0])
    timestamps = [
        float(line) for line in timestamp_bytes.decode("ascii").splitlines() if line
    ]
    if len(timestamps) != len(frames):
        raise RuntimeError("Timestamp and frame counts differ")
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise RuntimeError("JAI timestamps are not strictly increasing")
    intervals = [right - left for left, right in zip(timestamps, timestamps[1:])]
    median_interval = statistics.median(intervals)
    max_interval_error = max(abs(value - median_interval) for value in intervals)
    if not 0.95 <= median_interval <= 1.05 or max_interval_error > 0.02:
        raise RuntimeError("JAI stream does not satisfy the locked near-1-Hz gate")

    output.mkdir(parents=True, exist_ok=False)
    timestamp_path = output / "jai_rgb_timestamps.txt"
    timestamp_path.write_bytes(timestamp_bytes)
    contact_path = output / "jai_rgb_contact_sheet.png"
    sampled = build_contact_sheet(frames, timestamps, contact_path)
    video_path = output / "bonirob_jai_rgb_1fps.mp4"
    pattern = str(frames[0].parent / "rgb_%05d.png")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        "1",
        "-start_number",
        "0",
        "-i",
        pattern,
        "-frames:v",
        str(len(frames)),
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-4000:]}")
    probe = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_frames",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(video_path),
        ]
    )
    stream = probe["streams"][0]
    gates = {
        "acquisition_receipt_passed": True,
        "archive_sha256_locked": True,
        "explicit_cc_by_sa_4_license": acquisition.get("license") == "CC-BY-SA-4.0",
        "jai_rgb_only": True,
        "contiguous_31_frames": len(frames) == 31,
        "source_dimensions_and_mode_locked": True,
        "timestamp_count_matches": len(timestamps) == len(frames),
        "timestamps_strictly_increasing": True,
        "near_one_hz_source": 0.95 <= median_interval <= 1.05
        and max_interval_error <= 0.02,
        "video_frame_count_matches": int(stream["nb_read_frames"]) == len(frames),
        "video_dimensions_match": [int(stream["width"]), int(stream["height"])]
        == [1296, 966],
        "numeric_accuracy_disabled_without_labels": True,
    }
    receipt = {
        "schema_version": 1,
        "dataset": acquisition["dataset"],
        "sequence": acquisition["sequence"],
        "sensor_stream": "camera/jai/rgb",
        "capture_platform": "BoniRob field robot",
        "license": acquisition["license"],
        "official_dataset_page": acquisition["official_dataset_page"],
        "acquisition_receipt": str(acquisition_path),
        "acquisition_receipt_sha256": sha256(acquisition_path),
        "source_archive": str(archive),
        "source_archive_sha256": sha256(archive),
        "frame_count": len(frames),
        "source_dimensions": [1296, 966],
        "timestamps": {
            "path": str(timestamp_path),
            "sha256": sha256(timestamp_path),
            "first": timestamps[0],
            "last": timestamps[-1],
            "elapsed_seconds": timestamps[-1] - timestamps[0],
            "median_interval_seconds": median_interval,
            "source_median_fps": 1.0 / median_interval,
            "min_interval_seconds": min(intervals),
            "max_interval_seconds": max(intervals),
            "max_abs_error_from_median_seconds": max_interval_error,
        },
        "video": {
            "path": str(video_path),
            "sha256": sha256(video_path),
            "materialized_playback_fps": 1.0,
            "probe": probe,
        },
        "contact_sheet": {
            "path": str(contact_path),
            "sha256": sha256(contact_path),
            "sampled_frames": sampled,
        },
        "evaluation_policy": {
            "model_selection_score_weight": 0.0,
            "numeric_miou_allowed": False,
            "allowed_before_annotation": [
                "qualitative_overlay_review",
                "prediction_area_trace",
                "confidence_and_entropy_trace",
            ],
            "temporal_iou_caveat": (
                "Adjacent masks are not pixel-aligned because the robot moves; "
                "raw mask IoU is not a valid flicker metric without registration."
            ),
        },
        "manual_visual_review": "pending",
        "quality_gates": gates,
        "all_automated_quality_gates_passed": all(gates.values()),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = output / "video_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_automated_quality_gates_passed"]:
        raise RuntimeError(f"Video materialization gates failed; see {receipt_path}")
    print(
        json.dumps(
            {
                "video": str(video_path),
                "video_sha256": receipt["video"]["sha256"],
                "contact_sheet": str(contact_path),
                "receipt": str(receipt_path),
                "frames": len(frames),
                "source_median_fps": 1.0 / median_interval,
                "all_automated_quality_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
