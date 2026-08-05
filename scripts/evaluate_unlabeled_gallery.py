#!/usr/bin/env python3
"""Render source/semantic/policy panels for a locked unlabeled selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from agri_seg.data import EvalTransform
from agri_seg.engine import load_checkpoint, predict_logits, source_tree_sha256
from agri_seg.gallery import source_calibrated_policy
from agri_seg.safety import apply_safety_policy


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "min": float(array.min()),
        "p05": float(np.percentile(array, 5)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
        "mean": float(array.mean()),
        "std": float(array.std()),
    }


def tint(
    rgb: np.ndarray, masks_and_colours: list[tuple[np.ndarray, tuple[int, int, int]]]
) -> Image.Image:
    rendered = rgb.astype(np.float32).copy()
    for mask, colour in masks_and_colours:
        rendered[mask] = 0.56 * rendered[mask] + 0.44 * np.asarray(colour)
    return Image.fromarray(np.clip(rendered, 0, 255).astype(np.uint8))


def render_sheet(
    rows: list[dict[str, Any]], output: Path, title: str, page: int, display_mode: str
) -> None:
    tile_width, tile_height, label_height = 420, 236, 42
    header = 72
    canvas = Image.new(
        "RGB", (3 * tile_width, header + len(rows) * (tile_height + label_height)), "white"
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((10, 10), f"{title} | page {page}", fill="black", font=font)
    semantic_legend = (
        "semantic: vegetation union=green"
        if display_mode == "vegetation_union_only"
        else "semantic: crop=green, other vegetation=red"
    )
    policy_legend = (
        "diagnostic: vegetation=green, unknown=purple"
        if display_mode == "vegetation_union_only"
        else "policy: safe=red, candidate=orange, unknown=purple"
    )
    draw.text(
        (10, 31),
        f"RGB | {semantic_legend} | {policy_legend}",
        fill=(50, 50, 50),
        font=font,
    )
    draw.text(
        (10, 50), "Qualitative unlabeled diagnostic; no mIoU and zero selection weight", fill=(90, 0, 0), font=font
    )
    for row_index, row in enumerate(rows):
        y = header + row_index * (tile_height + label_height)
        prefix = str(row.get("source_label") or f"Day {int(row.get('day', -1)):02d}")
        label = (
            f"{prefix} | {row['frame']} | "
            f"crop={row['semantic_fraction']['target_crop']:.3f}, "
            f"other={row['semantic_fraction']['other_vegetation']:.3f}, "
            f"unknown={row['unknown_fraction']:.3f}"
        )
        draw.text((7, y + 5), label, fill="black", font=font)
        for column, key in enumerate(("source_path", "semantic_overlay", "policy_overlay")):
            with Image.open(row[key]) as handle:
                image = handle.convert("RGB")
                image.thumbnail((tile_width - 8, tile_height - 8), Image.Resampling.LANCZOS)
            background = Image.new("RGB", (tile_width, tile_height), (235, 235, 235))
            background.paste(image, ((tile_width - image.width) // 2, (tile_height - image.height) // 2))
            canvas.paste(background, (column * tile_width, y + label_height))
    canvas.save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="Unseen unlabeled gallery")
    parser.add_argument("--frames-per-page", type=int, default=10)
    parser.add_argument("--minimum-free-gpu-bytes", type=int, default=7516192768)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    selection_path = Path(args.selection).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (
        selection.get("training_exposure") is not False
        or selection.get("numeric_segmentation_accuracy_authorized") is not False
        or float(selection.get("model_selection_score_weight", -1)) != 0.0
    ):
        raise RuntimeError("Selection is not locked as unseen qualitative-only data")
    frames = selection.get("selected_frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Selection has no selected_frames")
    for row in frames:
        path = Path(str(row["path"])).resolve()
        if sha256(path) != str(row["sha256"]):
            raise RuntimeError(f"Selected source frame changed: {path}")
    requested_device = str(args.device)
    device = torch.device(
        "cuda"
        if requested_device == "auto" and torch.cuda.is_available()
        else "cpu" if requested_device == "auto" else requested_device
    )
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    gpu_capacity_gate: dict[str, Any] = {
        "required_for_runtime": device.type == "cuda",
        "minimum_free_bytes": int(args.minimum_free_gpu_bytes),
    }
    if device.type == "cuda":
        free, total = torch.cuda.mem_get_info()
        gpu_capacity_gate.update(
            {"observed_free_bytes": int(free), "total_bytes": int(total)}
        )
        if free < args.minimum_free_gpu_bytes:
            raise RuntimeError(
                f"GPU capacity gate failed: free={free:,}, required={args.minimum_free_gpu_bytes:,}; "
                "no external process was modified"
            )
        gpu_capacity_gate["passed"] = True
    else:
        gpu_capacity_gate.update(
            {"observed_free_bytes": None, "total_bytes": None, "passed": True}
        )

    output.mkdir(parents=True, exist_ok=False)
    mask_root = output / "semantic_masks"
    semantic_root = output / "semantic_overlays"
    policy_root = output / "policy_overlays"
    for directory in (mask_root, semantic_root, policy_root):
        directory.mkdir()
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    model.eval()
    config = checkpoint["config"]
    policy, max_crop_spray_risk = source_calibrated_policy(checkpoint)
    training = config["training"]
    crop_id = int(selection["target_crop_id"])
    display_mode = str(selection.get("class_interpretation", "three_class"))
    if display_mode not in {"three_class", "vegetation_union_only"}:
        raise ValueError(f"Unsupported class_interpretation: {display_mode}")
    crop_ids = torch.tensor([crop_id], dtype=torch.long, device=device)
    transform = EvalTransform()
    evaluated: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, source_row in enumerate(frames):
        frame_started = time.monotonic()
        source = Path(str(source_row["path"])).resolve()
        with Image.open(source) as handle:
            source_image = handle.convert("RGB")
            source_rgb = np.asarray(source_image, dtype=np.uint8).copy()
        dummy = Image.new("L", source_image.size, 255)
        tensor, _ = transform(source_image, dummy)
        images = tensor.unsqueeze(0).to(device, non_blocking=True)
        with torch.inference_mode():
            logits = predict_logits(
                model,
                images,
                crop_ids,
                use_amp=bool(training.get("amp", True)),
                tile_size=int(training.get("eval_tile_size", 1024)),
                tile_overlap=int(training.get("eval_tile_overlap", 128)),
                tile_trigger_pixels=int(training.get("eval_tile_trigger_pixels", 4_000_000)),
            )
            probabilities = logits.float().softmax(dim=1)
            decisions = apply_safety_policy(probabilities, policy, crop_ids)
        probabilities_np = probabilities[0].cpu().numpy()
        semantic = probabilities_np.argmax(axis=0).astype(np.uint8)
        unknown = decisions["unknown"][0].cpu().numpy()
        safe_weed = decisions["safe_weed"][0].cpu().numpy()
        weed_candidate = decisions["weed_candidate"][0].cpu().numpy()
        confidence = decisions["confidence"][0].cpu().numpy()
        entropy = decisions["entropy"][0].cpu().numpy()
        stem = f"prediction_{index:04d}_day_{int(source_row.get('day', 0)):02d}"
        mask = mask_root / f"{stem}.png"
        semantic_path = semantic_root / f"{stem}.jpg"
        policy_path = policy_root / f"{stem}.jpg"
        Image.fromarray(semantic, mode="L").save(mask, optimize=True)
        semantic_colours = (
            [(semantic > 0, (0, 230, 110))]
            if display_mode == "vegetation_union_only"
            else [(semantic == 1, (0, 255, 0)), (semantic == 2, (255, 35, 35))]
        )
        tint(source_rgb, semantic_colours).save(semantic_path, quality=94, subsampling=0)
        policy_colours = (
            [(semantic > 0, (0, 220, 100)), (unknown, (170, 60, 255))]
            if display_mode == "vegetation_union_only"
            else [
                (semantic == 1, (0, 220, 0)),
                (weed_candidate & ~safe_weed, (255, 150, 0)),
                (safe_weed, (255, 0, 40)),
                (unknown, (170, 60, 255)),
            ]
        )
        tint(source_rgb, policy_colours).save(policy_path, quality=94, subsampling=0)
        pixels = semantic.size
        evaluated.append(
            {
                "index": index,
                "day": int(source_row.get("day", -1)),
                "source_label": source_row.get("label"),
                "frame": source.name,
                "source_path": str(source),
                "source_sha256": source_row["sha256"],
                "semantic_mask": str(mask),
                "semantic_mask_sha256": sha256(mask),
                "semantic_overlay": str(semantic_path),
                "semantic_overlay_sha256": sha256(semantic_path),
                "policy_overlay": str(policy_path),
                "policy_overlay_sha256": sha256(policy_path),
                "semantic_fraction": {
                    "background": float((semantic == 0).sum() / pixels),
                    "target_crop": float((semantic == 1).sum() / pixels),
                    "other_vegetation": float((semantic == 2).sum() / pixels),
                },
                "safe_weed_fraction": float(safe_weed.sum() / pixels),
                "weed_candidate_fraction": float(weed_candidate.sum() / pixels),
                "unknown_fraction": float(unknown.sum() / pixels),
                "mean_confidence": float(confidence.mean()),
                "mean_entropy": float(entropy.mean()),
                "inference_seconds": time.monotonic() - frame_started,
            }
        )
        del logits, probabilities, decisions, images, probabilities_np

    contact_sheets: list[dict[str, Any]] = []
    for page, start in enumerate(range(0, len(evaluated), args.frames_per_page), start=1):
        path = output / f"prediction_contact_sheet_{page:02d}.jpg"
        render_sheet(
            evaluated[start : start + args.frames_per_page],
            path,
            args.title,
            page,
            display_mode,
        )
        contact_sheets.append({"path": str(path), "sha256": sha256(path)})
    summaries = {
        "target_crop_fraction": distribution([row["semantic_fraction"]["target_crop"] for row in evaluated]),
        "other_vegetation_fraction": distribution([row["semantic_fraction"]["other_vegetation"] for row in evaluated]),
        "safe_weed_fraction": distribution([row["safe_weed_fraction"] for row in evaluated]),
        "unknown_fraction": distribution([row["unknown_fraction"] for row in evaluated]),
        "mean_confidence": distribution([row["mean_confidence"] for row in evaluated]),
        "mean_entropy": distribution([row["mean_entropy"] for row in evaluated]),
        "inference_seconds": distribution([row["inference_seconds"] for row in evaluated]),
    }
    receipt = {
        "schema_version": 1,
        "purpose": "unseen_real_unlabeled_qualitative_failure_discovery",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection": str(selection_path),
        "selection_sha256": sha256(selection_path),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "checkpoint_experiment": config["experiment"],
        "checkpoint_seed": int(config["seed"]),
        "checkpoint_source_tree_sha256": checkpoint["metadata"]["source_tree_sha256"],
        "runtime_source_tree_sha256": source_tree_sha256(),
        "runtime_device": str(device),
        "gpu_capacity_gate": gpu_capacity_gate,
        "conditioning": {"target_crop_id": crop_id, "crop_species": selection.get("crop_species")},
        "class_interpretation": display_mode,
        "source_frozen_safety_policy": asdict(policy),
        "source_calibration": {
            "source": "checkpoint.source_validation",
            "max_crop_spray_risk": max_crop_spray_risk,
            "external_threshold_tuning_performed": False,
        },
        "frames": evaluated,
        "summaries": summaries,
        "contact_sheets": contact_sheets,
        "evaluation_policy": {
            "annotations_present": False,
            "numeric_accuracy_reported": False,
            "miou": None,
            "model_selection_score_weight": 0.0,
            "allowed_interpretation": (
                "qualitative vegetation-vs-background failure discovery only"
                if display_mode == "vegetation_union_only"
                else "qualitative failure discovery and area/confidence traces"
            ),
            "forbidden_interpretation": "accuracy or field-generalization proof",
        },
        "quality_gates": {
            "source_tree_matches_checkpoint": checkpoint["metadata"]["source_tree_sha256"] == source_tree_sha256(),
            "all_selected_frames_evaluated": len(evaluated) == len(frames),
            "source_calibrated_policy_reused_without_tuning": True,
            "selection_training_exposure_false": True,
            "numeric_accuracy_not_reported": True,
            "selection_score_weight_zero": True,
        },
        "manual_prediction_review": "pending",
        "wall_seconds": time.monotonic() - started,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt["all_automated_quality_gates_passed"] = all(receipt["quality_gates"].values())
    receipt_path = output / "unlabeled_gallery_evaluation.json"
    temporary = receipt_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    temporary.replace(receipt_path)
    print(json.dumps({
        "receipt": str(receipt_path),
        "frames": len(evaluated),
        "contact_sheets": contact_sheets,
        "summaries": summaries,
        "all_automated_quality_gates_passed": receipt["all_automated_quality_gates_passed"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
