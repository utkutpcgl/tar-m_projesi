#!/usr/bin/env python3
"""Compare two same-seed Unreal-EBIS outputs and write machine-readable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decoded_mask_sha256(path: Path) -> str:
    with Image.open(path) as opened:
        image = opened.convert("L")
    digest = hashlib.sha256()
    digest.update(f"{image.width}x{image.height}:L\n".encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def singleton(directory: Path, suffix: str) -> Path:
    values = sorted(directory.glob(f"*{suffix}"))
    if len(values) != 1:
        raise RuntimeError(f"expected one {suffix} below {directory}; got {len(values)}")
    return values[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", type=Path, required=True)
    parser.add_argument("--run-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = (args.run_a.resolve(), args.run_b.resolve())

    rgb = [singleton(root / "raw" / "images", ".png") for root in roots]
    with Image.open(rgb[0]) as opened_a, Image.open(rgb[1]) as opened_b:
        image_a, image_b = opened_a.convert("RGB"), opened_b.convert("RGB")
    if image_a.size != image_b.size:
        raise RuntimeError(f"RGB dimensions differ: {image_a.size} vs {image_b.size}")
    difference = ImageChops.difference(image_a, image_b)
    histogram = difference.histogram()
    changed_channels = sum(histogram[index] for channel in range(3) for index in range(channel * 256 + 1, channel * 256 + 256))
    total_channels = image_a.width * image_a.height * 3
    extrema = difference.getextrema()

    mask_records = []
    masks_equal = True
    for kind in ("masks_visible", "masks_amodal"):
        files_a = {path.name: path for path in (roots[0] / "raw" / kind).glob("*.png")}
        files_b = {path.name: path for path in (roots[1] / "raw" / kind).glob("*.png")}
        if files_a.keys() != files_b.keys():
            raise RuntimeError(f"{kind} filenames differ")
        for name in sorted(files_a):
            file_digest_a, file_digest_b = sha256(files_a[name]), sha256(files_b[name])
            digest_a, digest_b = decoded_mask_sha256(files_a[name]), decoded_mask_sha256(files_b[name])
            equal = digest_a == digest_b
            masks_equal &= equal
            mask_records.append({
                "kind": kind,
                "name": name,
                "decoded_pixels_equal": equal,
                "decoded_pixel_sha256_a": digest_a,
                "decoded_pixel_sha256_b": digest_b,
                "png_container_bit_exact": file_digest_a == file_digest_b,
                "file_sha256_a": file_digest_a,
                "file_sha256_b": file_digest_b,
            })

    labels_a = sorted((roots[0] / "partitions").glob("*/labels/*.txt"))
    labels_b = sorted((roots[1] / "partitions").glob("*/labels/*.txt"))
    labels_equal = len(labels_a) == len(labels_b) == 1 and labels_a[0].read_bytes() == labels_b[0].read_bytes()
    metadata = [json.loads(singleton(root / "metadata", ".json").read_text(encoding="utf-8")) for root in roots]
    stable_keys = ("engine_version", "config_sha256", "seed", "camera", "sample", "rfid_instances", "lighting", "machine")
    stable_equal = all(metadata[0].get(key) == metadata[1].get(key) for key in stable_keys)
    depth = [singleton(root / "raw" / "depth", ".exr") for root in roots]

    result = {
        "schema_version": 1,
        "same_seed": metadata[0].get("seed") == metadata[1].get("seed"),
        "stable_scenario_fields_equal": stable_equal,
        "visible_and_amodal_masks_bit_exact": masks_equal,
        "published_yolo_label_bit_exact": labels_equal,
        "depth_exr_bit_exact": sha256(depth[0]) == sha256(depth[1]),
        "rgb": {
            "bit_exact": sha256(rgb[0]) == sha256(rgb[1]),
            "sha256_a": sha256(rgb[0]),
            "sha256_b": sha256(rgb[1]),
            "changed_channels": changed_channels,
            "total_channels": total_channels,
            "changed_channel_fraction": changed_channels / total_channels,
            "max_absolute_channel_delta": max(value for pair in extrema for value in pair),
            "mean_absolute_delta_rgb": [round(value, 8) for value in ImageStat.Stat(difference).mean],
        },
        "mask_records": mask_records,
        "claim_boundary": "Same build/GPU only; no bit-determinism claim across engine, driver or GPU versions.",
    }
    result["ok"] = bool(result["same_seed"] and stable_equal and masks_equal and labels_equal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "stable_scenario_fields_equal", "visible_and_amodal_masks_bit_exact", "published_yolo_label_bit_exact", "depth_exr_bit_exact", "rgb")}, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
