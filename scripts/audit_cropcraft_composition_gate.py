#!/usr/bin/env python3
"""Audit a CropCraft release against a frozen frame-composition gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image


SEMANTIC_COLORS = {
    "background": (0, 0, 0),
    "crop": (0, 255, 0),
    "weed": (255, 0, 0),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object: {path}")
    return payload


def fraction_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("min", "p10", "median", "mean", "p90", "max")}
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "p10": float(np.quantile(array, 0.10)),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "p90": float(np.quantile(array, 0.90)),
        "max": float(array.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument("--gate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    release = Path(args.release).expanduser().resolve()
    gate_path = Path(args.gate).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)

    receipt_path = release / "release_receipt.json"
    receipt = load_object(receipt_path)
    gate_document = load_object(gate_path)
    gate = gate_document.get("release_gate")
    if not isinstance(gate, dict):
        raise ValueError("Gate document has no release_gate mapping")

    expected_frames = int(gate["expected_rgb_mask_pairs"])
    expected_scenes = int(gate["expected_independent_scenes"])
    frame_rows: list[dict[str, Any]] = []
    observed_colors: set[tuple[int, int, int]] = set()
    image_shapes: set[tuple[int, int]] = set()

    scene_roots = sorted((release / "scenes").glob("scene_*"))
    for scene_root in scene_roots:
        mask_root = scene_root / "render" / "masks"
        image_root = scene_root / "render" / "images"
        masks = {path.stem: path for path in sorted(mask_root.glob("*.png"))}
        images = {path.stem: path for path in sorted(image_root.glob("*.jpg"))}
        if set(masks) != set(images):
            raise ValueError(f"RGB/mask pairing mismatch: {scene_root.name}")
        for stem, mask_path in masks.items():
            image_path = images[stem]
            with Image.open(mask_path) as mask_handle:
                raw = np.asarray(mask_handle.convert("RGB"), dtype=np.uint8)
            with Image.open(image_path) as image_handle:
                if image_handle.size != (raw.shape[1], raw.shape[0]):
                    raise ValueError(f"RGB/mask shape mismatch: {mask_path}")
            pixels = int(raw.shape[0] * raw.shape[1])
            image_shapes.add((int(raw.shape[1]), int(raw.shape[0])))
            unique = np.unique(raw.reshape(-1, 3), axis=0)
            observed_colors.update(tuple(int(channel) for channel in row) for row in unique)
            crop_pixels = int(
                np.all(raw == np.asarray(SEMANTIC_COLORS["crop"]), axis=2).sum()
            )
            weed_pixels = int(
                np.all(raw == np.asarray(SEMANTIC_COLORS["weed"]), axis=2).sum()
            )
            crop_fraction = crop_pixels / pixels
            weed_fraction = weed_pixels / pixels
            frame_rows.append(
                {
                    "scene": scene_root.name,
                    "frame": mask_path.stem,
                    "crop_fraction": crop_fraction,
                    "weed_fraction": weed_fraction,
                    "weed_to_crop_ratio": (
                        weed_fraction / crop_fraction
                        if crop_fraction > 0.0
                        else None
                    ),
                    "mask_sha256": sha256(mask_path),
                }
            )

    if not frame_rows:
        raise RuntimeError(f"No masks found in {release}")
    crop = [float(row["crop_fraction"]) for row in frame_rows]
    weed = [float(row["weed_fraction"]) for row in frame_rows]
    finite_ratio = [
        float(row["weed_to_crop_ratio"])
        for row in frame_rows
        if row["weed_to_crop_ratio"] is not None
    ]
    crop_free = sum(value == 0.0 for value in crop)
    weed_free = sum(value == 0.0 for value in weed)
    weed_003_count = sum(value >= 0.03 for value in weed)
    crop_band_count = sum(0.005 <= value <= 0.12 for value in crop)
    ratio_075_count = sum(
        row["weed_to_crop_ratio"] is None
        or float(row["weed_to_crop_ratio"]) >= 0.75
        for row in frame_rows
    )

    allowed_colors = set(SEMANTIC_COLORS.values())
    palette_exact = observed_colors.issubset(allowed_colors)
    release_quality_gates = receipt.get("quality_gates", {})
    evidence = gate_document.get("evidence", {})
    receipt_asset_pack = receipt.get("asset_pack", {})
    study_path = release / "study.input.yaml"
    checks = {
        "generator_quality_gates": receipt.get("all_quality_gates_passed") is True,
        "receipt_frame_count": int(receipt.get("frames", -1)) == expected_frames,
        "receipt_scene_count": int(receipt.get("scene_count", -1)) == expected_scenes,
        "immutable_study_copy": study_path.is_file()
        and receipt.get("copied_study_sha256") == sha256(study_path),
        "asset_pack_id": isinstance(receipt_asset_pack, dict)
        and receipt_asset_pack.get("pack_id") == evidence.get("asset_pack_id"),
        "asset_pack_manifest_sha256": isinstance(receipt_asset_pack, dict)
        and receipt_asset_pack.get("manifest_sha256")
        == evidence.get("asset_pack_manifest_sha256"),
        "expected_rgb_mask_pairs": len(frame_rows) == expected_frames,
        "expected_independent_scenes": len(scene_roots) == expected_scenes,
        "maximum_crop_free_frame_fraction": crop_free / len(crop)
        <= float(gate["maximum_crop_free_frame_fraction"]),
        "maximum_weed_free_frame_fraction": weed_free / len(weed)
        <= float(gate["maximum_weed_free_frame_fraction"]),
        "minimum_mean_crop_fraction": np.mean(crop)
        >= float(gate["minimum_mean_crop_fraction"]),
        "maximum_mean_crop_fraction": np.mean(crop)
        <= float(gate["maximum_mean_crop_fraction"]),
        "minimum_mean_weed_fraction": np.mean(weed)
        >= float(gate["minimum_mean_weed_fraction"]),
        "maximum_mean_weed_fraction": np.mean(weed)
        <= float(gate["maximum_mean_weed_fraction"]),
        "minimum_frames_with_weed_fraction_at_least_0_03": weed_003_count
        >= int(gate["minimum_frames_with_weed_fraction_at_least_0_03"]),
        "minimum_frames_with_crop_fraction_between_0_005_and_0_12": crop_band_count
        >= int(gate["minimum_frames_with_crop_fraction_between_0_005_and_0_12"]),
        "minimum_frames_with_weed_to_crop_ratio_at_least_0_75": ratio_075_count
        >= int(gate["minimum_frames_with_weed_to_crop_ratio_at_least_0_75"]),
        "maximum_exact_rgb_duplicates": int(receipt.get("exact_rgb_duplicates", -1))
        <= int(gate["maximum_exact_rgb_duplicates"]),
        "maximum_exact_mask_duplicates_across_scenes": int(
            receipt.get("exact_mask_duplicates_across_scenes", -1)
        )
        <= int(gate["maximum_exact_mask_duplicates_across_scenes"]),
        "minimum_used_crop_model_variants": len(receipt.get("crop_model_filenames", []))
        >= int(gate["minimum_used_crop_model_variants"]),
        "minimum_used_ground_families": len(receipt.get("used_ground_materials", []))
        >= int(gate["minimum_used_ground_families"]),
        "minimum_used_environment_families": len(receipt.get("used_environments", []))
        >= int(gate["minimum_used_environment_families"]),
        "require_exact_semantic_palette": (
            palette_exact if bool(gate["require_exact_semantic_palette"]) else True
        ),
        "require_scene_disjoint_split": (
            release_quality_gates.get("scene_disjoint_split") is True
            if bool(gate["require_scene_disjoint_split"])
            else True
        ),
    }
    checks = {name: bool(value) for name, value in checks.items()}
    report = {
        "schema_version": 1,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "release": str(release),
        "release_receipt_sha256": sha256(receipt_path),
        "study_sha256": sha256(study_path),
        "gate": str(gate_path),
        "gate_sha256": sha256(gate_path),
        "script_sha256": sha256(Path(__file__).resolve()),
        "frames": len(frame_rows),
        "scenes": len(scene_roots),
        "image_shapes": [list(shape) for shape in sorted(image_shapes)],
        "observed_semantic_colors": [list(color) for color in sorted(observed_colors)],
        "crop_fraction": fraction_summary(crop),
        "weed_fraction": fraction_summary(weed),
        "weed_to_crop_ratio_for_crop_positive_frames": fraction_summary(finite_ratio),
        "counts": {
            "crop_free_frames": crop_free,
            "weed_free_frames": weed_free,
            "frames_with_weed_fraction_at_least_0_03": weed_003_count,
            "frames_with_crop_fraction_between_0_005_and_0_12": crop_band_count,
            "frames_with_weed_to_crop_ratio_at_least_0_75": ratio_075_count,
        },
        "checks": checks,
        "passed": all(checks.values()),
        "frame_metrics": frame_rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("passed", "counts", "checks")}, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
