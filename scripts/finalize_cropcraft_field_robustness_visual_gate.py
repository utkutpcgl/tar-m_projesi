#!/usr/bin/env python3
"""Finalize visual/radiometric review for a split-aware CropCraft release."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROLES = ("train", "val", "test")
MASK_COLOURS = {(0, 0, 0), (0, 255, 0), (255, 0, 0)}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--verdict", choices=("pass", "fail"), required=True)
    parser.add_argument("--notes", required=True)
    arguments = parser.parse_args()
    release = Path(arguments.release).expanduser().resolve()
    output = release / "visual_review_receipt.json"
    if output.exists():
        raise FileExistsError(output)
    top_receipt_path = release / "release_receipt.json"
    top = load_json(top_receipt_path)
    if top.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Top-level synthetic release gates did not pass")
    if float(top.get("real_model_selection_score_weight", -1)) != 0.0:
        raise RuntimeError("Synthetic real-selection weight is not zero")
    top_roles = {row["role"]: row for row in top["roles"]}
    if set(top_roles) != set(ROLES):
        raise RuntimeError("Top receipt does not contain exactly three roles")

    role_reports: dict[str, Any] = {}
    all_frame_rows: list[dict[str, Any]] = []
    for role in ROLES:
        role_root = release / "roles" / role
        role_receipt_path = role_root / "release_receipt.json"
        role_receipt = load_json(role_receipt_path)
        if role_receipt.get("all_quality_gates_passed") is not True:
            raise RuntimeError(f"{role} release did not pass generation gates")
        if sha256(role_receipt_path) != top_roles[role]["receipt_sha256"]:
            raise RuntimeError(f"{role} receipt changed after top-level gate")
        contact_path = release / f"{role}_contact_sheet.png"
        contact_report_path = contact_path.with_suffix(".json")
        contact = load_json(contact_report_path)
        if sha256(contact_path) != contact["contact_sheet_sha256"]:
            raise RuntimeError(f"{role} contact sheet hash mismatch")
        if contact["release_receipt_sha256"] != sha256(role_receipt_path):
            raise RuntimeError(f"{role} contact sheet locks a different release")

        images = sorted(role_root.glob("scenes/*/render/images/*.jpg"))
        masks = sorted(role_root.glob("scenes/*/render/masks/*.png"))
        image_by_key = {
            (path.parents[2].name, path.stem): path for path in images
        }
        mask_by_key = {(path.parents[2].name, path.stem): path for path in masks}
        if set(image_by_key) != set(mask_by_key):
            raise RuntimeError(f"{role} RGB/mask pairing mismatch")
        if len(images) != int(top_roles[role]["expected_pairs"]):
            raise RuntimeError(f"{role} pair count differs from top receipt")
        frame_rows: list[dict[str, Any]] = []
        for key in sorted(image_by_key):
            image_path = image_by_key[key]
            mask_path = mask_by_key[key]
            with Image.open(image_path) as handle:
                rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
            with Image.open(mask_path) as handle:
                mask = np.asarray(handle.convert("RGB"), dtype=np.uint8)
            if rgb.shape != mask.shape or rgb.shape[:2] != (512, 512):
                raise RuntimeError(f"Unexpected shape for {role}/{key}: {rgb.shape}")
            colours = {
                tuple(int(channel) for channel in colour)
                for colour in np.unique(mask.reshape(-1, 3), axis=0)
            }
            if not colours <= MASK_COLOURS:
                raise RuntimeError(f"Unexpected mask colours for {role}/{key}: {colours}")
            row = {
                "role": role,
                "scene": key[0],
                "frame": key[1],
                "rgb": str(image_path),
                "rgb_sha256": sha256(image_path),
                "mask": str(mask_path),
                "mask_sha256": sha256(mask_path),
                "mean_rgb": [float(value) for value in rgb.mean(axis=(0, 1))],
                "mean_all_channels": float(rgb.mean()),
                "any_channel_ge_250_fraction": float((rgb >= 250).any(axis=2).mean()),
                "all_channels_ge_250_fraction": float((rgb >= 250).all(axis=2).mean()),
                "all_channels_le_5_fraction": float((rgb <= 5).all(axis=2).mean()),
                "mask_colours": [list(value) for value in sorted(colours)],
            }
            frame_rows.append(row)
            all_frame_rows.append(row)
        role_reports[role] = {
            "frames": len(frame_rows),
            "contact_sheet": str(contact_path),
            "contact_sheet_sha256": sha256(contact_path),
            "contact_report": str(contact_report_path),
            "contact_report_sha256": sha256(contact_report_path),
            "mean_brightness_range": [
                min(row["mean_all_channels"] for row in frame_rows),
                max(row["mean_all_channels"] for row in frame_rows),
            ],
            "maximum_any_channel_ge_250_fraction": max(
                row["any_channel_ge_250_fraction"] for row in frame_rows
            ),
            "maximum_all_channels_ge_250_fraction": max(
                row["all_channels_ge_250_fraction"] for row in frame_rows
            ),
            "maximum_all_channels_le_5_fraction": max(
                row["all_channels_le_5_fraction"] for row in frame_rows
            ),
        }

    thresholds = {
        "minimum_frame_mean_brightness": 40.0,
        "maximum_frame_mean_brightness": 240.0,
        "maximum_fully_clipped_white_fraction_per_frame": 0.002,
        "maximum_fully_clipped_black_fraction_per_frame": 0.001,
    }
    gates = {
        "top_release_gates_passed": True,
        "all_role_receipts_hash_locked": True,
        "all_contact_sheets_hash_locked": True,
        "all_rgb_mask_pairs_512_square": True,
        "all_masks_use_exact_known_colours": True,
        "frame_mean_brightness_in_range": all(
            thresholds["minimum_frame_mean_brightness"]
            <= row["mean_all_channels"]
            <= thresholds["maximum_frame_mean_brightness"]
            for row in all_frame_rows
        ),
        "fully_clipped_white_below_limit": all(
            row["all_channels_ge_250_fraction"]
            <= thresholds["maximum_fully_clipped_white_fraction_per_frame"]
            for row in all_frame_rows
        ),
        "fully_clipped_black_below_limit": all(
            row["all_channels_le_5_fraction"]
            <= thresholds["maximum_fully_clipped_black_fraction_per_frame"]
            for row in all_frame_rows
        ),
        "manual_rgb_mask_alignment_and_plausibility": arguments.verdict == "pass",
        "synthetic_real_selection_weight_zero": True,
    }
    receipt = {
        "schema_version": 1,
        "release": str(release),
        "release_receipt": str(top_receipt_path),
        "release_receipt_sha256": sha256(top_receipt_path),
        "reviewer": arguments.reviewer,
        "manual_verdict": arguments.verdict,
        "manual_notes": arguments.notes,
        "manual_review_scope": (
            "sampled RGB/mask/overlay contact sheets for all three roles; "
            "all frames were checked automatically for shape, colours and radiometry"
        ),
        "role_reports": role_reports,
        "frame_radiometry": all_frame_rows,
        "radiometry_thresholds": thresholds,
        "quality_gates": gates,
        "passed": all(gates.values()),
        "real_model_selection_score_weight": 0.0,
        "limitations": [
            "manual review is sampled rather than pixel-by-pixel over every frame",
            "visual plausibility does not prove downstream real-field benefit",
            "shader-normal tillage detail is not physical displaced soil geometry",
        ],
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["passed"]:
        raise RuntimeError(f"Visual/radiometric gate failed; see {output}")
    print(
        json.dumps(
            {
                "receipt": str(output),
                "release_receipt_sha256": receipt["release_receipt_sha256"],
                "frames": len(all_frame_rows),
                "role_reports": role_reports,
                "passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
