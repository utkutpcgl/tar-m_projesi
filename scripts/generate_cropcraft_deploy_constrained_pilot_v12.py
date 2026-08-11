#!/usr/bin/env python3
"""Generate the split-disjoint V12 controlled-deployment CropCraft release."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.generate_cropcraft_field_robustness_pilot as split_generator


ROLE_GENERATOR = (
    Path(__file__).resolve().parent
    / "generate_cropcraft_deploy_profiled_pilot_v12.py"
)


def output_argument(argv: list[str]) -> Path:
    try:
        index = argv.index("--output")
        return Path(argv[index + 1]).expanduser().resolve()
    except (ValueError, IndexError) as error:
        raise ValueError("Expected --output PATH") from error


def _weed_component_bboxes(mask: np.ndarray) -> list[int]:
    labels, count = ndimage.label(mask)
    boxes: list[int] = []
    for label_id in range(1, count + 1):
        ys, xs = np.nonzero(labels == label_id)
        if len(xs) == 0:
            continue
        boxes.append(int(max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)))
    return boxes


def _frame_quality(
    rgb_path: Path, mask_path: Path, actionable_px: int
) -> dict[str, Any]:
    rgb = np.asarray(Image.open(rgb_path).convert("RGB"), dtype=np.uint8)
    mask = np.asarray(Image.open(mask_path).convert("RGB"), dtype=np.uint8)
    if rgb.shape != mask.shape or rgb.shape[:2] != (1024, 1024):
        raise ValueError(f"Unexpected deploy RGB/mask shape: {rgb_path}")
    colors = {tuple(value) for value in np.unique(mask.reshape(-1, 3), axis=0)}
    allowed = {(0, 0, 0), (0, 255, 0), (255, 0, 0)}
    if not colors <= allowed:
        raise ValueError(f"Unexpected mask palette: {mask_path}: {colors - allowed}")
    weed = (mask[:, :, 0] == 255) & (mask[:, :, 1] == 0)
    component_bboxes = _weed_component_bboxes(weed)
    return {
        "rgb": str(rgb_path),
        "mask": str(mask_path),
        "mean_all_channels": float(rgb.mean()),
        "all_channels_ge_250_fraction": float((rgb >= 250).all(axis=2).mean()),
        "all_channels_le_5_fraction": float((rgb <= 5).all(axis=2).mean()),
        "weed_pixels": int(weed.sum()),
        "weed_component_count": len(component_bboxes),
        "actionable_weed_component_count": sum(
            value >= actionable_px for value in component_bboxes
        ),
        "weed_component_bbox_px": component_bboxes,
    }


def finalize_deploy_visual_gate(destination: Path) -> dict[str, Any]:
    receipt_path = destination / "release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    study = yaml.safe_load(
        Path(receipt["resolved_study"]).read_text(encoding="utf-8")
    )
    contract = study["deploy_visual_gates"]
    actionable_px = int(contract["minimum_actionable_weed_component_bbox_px"])
    role_rows: dict[str, Any] = {}
    all_frames: list[dict[str, Any]] = []
    global_gates: dict[str, bool] = {}
    for role in ("train", "val", "test"):
        frames: list[dict[str, Any]] = []
        role_root = destination / "roles" / role / "scenes"
        for rgb_path in sorted(role_root.glob("*/render/images/*.jpg")):
            mask_path = Path(
                str(rgb_path).replace("/images/", "/masks/")
            ).with_suffix(".png")
            row = _frame_quality(rgb_path, mask_path, actionable_px)
            row["role"] = role
            row["scene"] = rgb_path.parents[2].name
            row["frame"] = rgb_path.stem
            frames.append(row)
            all_frames.append(row)
        if not frames:
            raise RuntimeError(f"No rendered frames for deploy role: {role}")
        role_contract = contract["roles"][role]
        any_weed_fraction = sum(row["weed_pixels"] > 0 for row in frames) / len(
            frames
        )
        actionable_fraction = sum(
            row["actionable_weed_component_count"] > 0 for row in frames
        ) / len(frames)
        actionable_count = sum(
            row["actionable_weed_component_count"] for row in frames
        )
        role_gates = {
            "frames_with_any_weed_fraction": any_weed_fraction
            >= float(role_contract["minimum_frames_with_any_weed_fraction"]),
            "frames_with_actionable_weed_fraction": actionable_fraction
            >= float(role_contract["minimum_frames_with_actionable_weed_fraction"]),
            "actionable_weed_component_count": actionable_count
            >= int(role_contract["minimum_actionable_weed_components"]),
        }
        role_rows[role] = {
            "frames": len(frames),
            "frames_with_any_weed_fraction": any_weed_fraction,
            "frames_with_actionable_weed_fraction": actionable_fraction,
            "actionable_weed_component_count": actionable_count,
            "quality_gates": role_gates,
        }
        global_gates.update(
            {f"{role}_{name}": passed for name, passed in role_gates.items()}
        )

    brightness = [row["mean_all_channels"] for row in all_frames]
    whites = [row["all_channels_ge_250_fraction"] for row in all_frames]
    blacks = [row["all_channels_le_5_fraction"] for row in all_frames]
    radiometry_gates = {
        "minimum_frame_mean_brightness": min(brightness)
        >= float(contract["minimum_frame_mean_brightness"]),
        "maximum_frame_mean_brightness": max(brightness)
        <= float(contract["maximum_frame_mean_brightness"]),
        "fully_clipped_white_fraction": max(whites)
        <= float(contract["maximum_fully_clipped_white_fraction_per_frame"]),
        "fully_clipped_black_fraction": max(blacks)
        <= float(contract["maximum_fully_clipped_black_fraction_per_frame"]),
    }
    global_gates.update(radiometry_gates)
    receipt["deploy_visual_gate"] = {
        "contract": contract,
        "radiometry": {
            "minimum_frame_mean_brightness": min(brightness),
            "maximum_frame_mean_brightness": max(brightness),
            "maximum_fully_clipped_white_fraction": max(whites),
            "maximum_fully_clipped_black_fraction": max(blacks),
        },
        "roles": role_rows,
        "quality_gates": global_gates,
        "all_quality_gates_passed": all(global_gates.values()),
        "frame_rows": all_frames,
        "component_note": (
            "semantic connected components are visibility proxies, not true plant instances"
        ),
    }
    receipt["quality_gates"].update(
        {f"deploy_{name}": passed for name, passed in global_gates.items()}
    )
    receipt["all_quality_gates_passed"] = all(
        receipt["quality_gates"].values()
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_quality_gates_passed"]:
        failed = [name for name, passed in global_gates.items() if not passed]
        raise RuntimeError(f"Deploy visual gate failed: {failed}; see {receipt_path}")
    return receipt


def main() -> None:
    destination = output_argument(sys.argv[1:])
    split_generator.LEGACY_GENERATOR = ROLE_GENERATOR
    split_generator.main()
    plan_only = "--plan-only" in sys.argv
    receipt_name = (
        "plan_receipt.json" if plan_only else "release_receipt.json"
    )
    receipt_path = destination / receipt_name
    if not plan_only:
        finalize_deploy_visual_gate(destination)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_split_generator"] = receipt["generator"]
    receipt["base_split_generator_sha256"] = receipt["generator_sha256"]
    receipt["generator"] = str(Path(__file__).resolve())
    receipt["generator_sha256"] = split_generator.sha256(Path(__file__).resolve())
    receipt["deploy_role_generator"] = str(ROLE_GENERATOR)
    receipt["deploy_role_generator_sha256"] = split_generator.sha256(
        ROLE_GENERATOR
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "receipt_sha256": split_generator.sha256(receipt_path),
                "all_quality_gates_passed": receipt[
                    "all_quality_gates_passed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
