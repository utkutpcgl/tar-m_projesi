#!/usr/bin/env python3
"""Apply an auditable deterministic CCTV output curve to Unreal RGB frames.

The Unreal LDR export is retained byte-for-byte under
``raw/images_pre_sensor``.  Only ``raw/images`` is transformed; instance masks,
depth and geometry therefore remain untouched.  Running the command again is
idempotent because it always regenerates from the preserved input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Unreal dataset output root")
    parser.add_argument("--config", type=Path, required=True, help="Sensor response JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported sensor response schema")

    image_dir = root / "raw" / "images"
    source_dir = root / "raw" / "images_pre_sensor"
    image_paths = sorted(image_dir.glob("*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No Unreal RGB PNG files under {image_dir}")
    source_dir.mkdir(parents=True, exist_ok=True)

    black = int(config["black_level_8bit"])
    white = int(config["white_level_8bit"])
    gamma = float(config["gamma"])
    if not (0 <= black < white <= 255 and gamma > 0.0):
        raise ValueError("Expected 0 <= black < white <= 255 and gamma > 0")
    lut = [
        max(0, min(255, round(black + (white - black) * ((value / 255.0) ** gamma))))
        for value in range(256)
    ]
    lens_cfg = config.get("lens_dust", {})
    lens_enabled = bool(lens_cfg.get("enabled", False))
    if lens_enabled:
        count_range = list(map(int, lens_cfg.get("spot_count_range", [])))
        radius_range = list(
            map(float, lens_cfg.get("radius_fraction_range", []))
        )
        opacity_range = list(map(int, lens_cfg.get("opacity_8bit_range", [])))
        blur_range = list(
            map(float, lens_cfg.get("blur_radius_fraction_range", []))
        )
        probability = float(lens_cfg.get("occurrence_probability", -1.0))
        if (
            len(count_range) != 2
            or not 0 <= count_range[0] <= count_range[1] <= 8
            or len(radius_range) != 2
            or not 0.002 <= radius_range[0] <= radius_range[1] <= 0.035
            or len(opacity_range) != 2
            or not 1 <= opacity_range[0] <= opacity_range[1] <= 18
            or len(blur_range) != 2
            or not 0.001 <= blur_range[0] <= blur_range[1] <= 0.02
            or not 0.0 <= probability <= 0.6
        ):
            raise ValueError("lens_dust is outside the subtle RGB-only contract")
    metadata_by_stem = {
        path.stem: (
            path,
            json.loads(path.read_text(encoding="utf-8")),
        )
        for path in sorted((root / "raw" / "metadata").glob("*.json"))
    }

    entries = []
    lens_dust_frame_count = 0
    lens_dust_spot_total = 0
    for destination in image_paths:
        source = source_dir / destination.name
        if not source.exists():
            shutil.copy2(destination, source)
        with Image.open(source) as image:
            rgb = image.convert("RGB").point(lut * 3)
            lens_dust_spots = []
            metadata_record = metadata_by_stem.get(destination.stem)
            if lens_enabled and metadata_record is not None:
                metadata = metadata_record[1]
                lens_rng = random.Random(
                    f"{metadata['seed']}:{metadata['camera']}:lens-dust-v1"
                )
                if lens_rng.random() < probability:
                    spot_count = lens_rng.randint(*count_range)
                    overlay = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
                    draw = ImageDraw.Draw(overlay)
                    for _index in range(spot_count):
                        radius_fraction = lens_rng.uniform(*radius_range)
                        radius_px = radius_fraction * min(rgb.size)
                        aspect = lens_rng.uniform(0.72, 1.38)
                        center_x = lens_rng.uniform(0.04, 0.96) * rgb.width
                        center_y = lens_rng.uniform(0.04, 0.96) * rgb.height
                        opacity = lens_rng.randint(*opacity_range)
                        bounds = (
                            center_x - radius_px * aspect,
                            center_y - radius_px,
                            center_x + radius_px * aspect,
                            center_y + radius_px,
                        )
                        draw.ellipse(bounds, fill=(58, 51, 42, opacity))
                        lens_dust_spots.append(
                            {
                                "x_fraction": center_x / rgb.width,
                                "y_fraction": center_y / rgb.height,
                                "radius_fraction": radius_fraction,
                                "aspect": aspect,
                                "opacity_8bit": opacity,
                            }
                        )
                    blur_px = lens_rng.uniform(*blur_range) * min(rgb.size)
                    overlay = overlay.filter(
                        ImageFilter.GaussianBlur(radius=blur_px)
                    )
                    rgb = Image.alpha_composite(
                        rgb.convert("RGBA"), overlay
                    ).convert("RGB")
                    lens_dust_frame_count += 1
                    lens_dust_spot_total += spot_count
            temporary = destination.with_name(destination.name + ".tmp")
            rgb.save(temporary, format="PNG", compress_level=6)
        temporary.replace(destination)
        if metadata_record is not None:
            metadata_path, metadata = metadata_record
            metadata["sensor_response"] = {
                "profile": config["name"],
                "lens_dust_profile": (
                    "subtle_rgb_only_blurred_ellipses_v1"
                    if lens_enabled
                    else "disabled"
                ),
                "lens_dust_spots": lens_dust_spots,
                "masks_changed": False,
                "depth_changed": False,
            }
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        entries.append(
            {
                "name": destination.name,
                "pre_sensor_sha256": sha256(source),
                "sensor_rgb_sha256": sha256(destination),
                "lens_dust_spots": lens_dust_spots,
            }
        )

    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "config": config_path.name,
        "config_sha256": sha256(config_path),
        "script_sha256": sha256(Path(__file__).resolve()),
        "frame_count": len(entries),
        "geometry_changed": False,
        "masks_changed": False,
        "depth_changed": False,
        "lens_dust_frame_count": lens_dust_frame_count,
        "lens_dust_spot_total": lens_dust_spot_total,
        "entries": entries,
    }
    manifest_path = root / "raw" / "sensor_response_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SENSOR_RESPONSE_OK frames={len(entries)} root={root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
