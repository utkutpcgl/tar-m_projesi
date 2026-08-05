#!/usr/bin/env python3
"""Run a frozen checkpoint on the unlabeled BoniRob JAI RGB sequence.

The output is deliberately qualitative/diagnostic.  It never fabricates an
accuracy score from unlabeled frames and never tunes the source-frozen safety
policy on this sequence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageDraw

from agri_seg.data import EvalTransform
from agri_seg.engine import load_checkpoint, predict_logits, source_tree_sha256
from agri_seg.gallery import source_calibrated_policy
from agri_seg.manifest import read_manifest
from agri_seg.safety import apply_safety_policy


EXPECTED_CHECKPOINT_SHA256 = (
    "b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f"
)
RGB_MARKER = "/camera/jai/rgb/"
TARGET_CROP_ID = 0
TARGET_CROP_SPECIES = "Beta vulgaris"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
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


def render_contact_sheet(
    rows: list[dict[str, Any]], sampled_indices: list[int], output: Path
) -> None:
    tile_width, tile_height = 324, 242
    label_height = 30
    canvas = Image.new(
        "RGB",
        (3 * tile_width, len(sampled_indices) * (tile_height + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    for row_index, frame_index in enumerate(sampled_indices):
        row = rows[frame_index]
        y = row_index * (tile_height + label_height)
        draw.text(
            (5, y + 8),
            (
                f"{row['frame']} | RGB / semantic / policy | "
                f"crop={row['semantic_fraction']['target_crop']:.3f}, "
                f"other={row['semantic_fraction']['other_vegetation']:.3f}"
            ),
            fill=(0, 0, 0),
        )
        for column, key in enumerate(
            ("source_path", "semantic_overlay", "policy_overlay")
        ):
            with Image.open(row[key]) as handle:
                tile = handle.convert("RGB")
                tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
                background = Image.new("RGB", (tile_width, tile_height), (238, 238, 238))
                background.paste(
                    tile,
                    ((tile_width - tile.width) // 2, (tile_height - tile.height) // 2),
                )
            canvas.paste(background, (column * tile_width, y + label_height))
    canvas.save(output, optimize=True)


def exact_training_duplicate_audit(
    frames: list[Path], checkpoint_config: dict[str, Any]
) -> dict[str, Any]:
    manifest = Path(str(checkpoint_config["manifest"])).resolve()
    data_root = Path(str(checkpoint_config["data_root"])).resolve()
    records = read_manifest(manifest)
    source_paths = {frame.resolve() for frame in frames}
    frame_hashes = {sha256(frame): frame for frame in frames}
    source_sizes = {frame.stat().st_size for frame in frames}
    candidates: list[Path] = []
    path_overlap: list[str] = []
    for recorded in sorted({record.image_path for record in records}):
        path = Path(recorded)
        resolved = path.resolve() if path.is_absolute() else (data_root / path).resolve()
        if resolved in source_paths:
            path_overlap.append(str(resolved))
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        if resolved.stat().st_size in source_sizes:
            candidates.append(resolved)
    byte_duplicates = []
    for candidate in candidates:
        digest = sha256(candidate)
        if digest in frame_hashes:
            byte_duplicates.append(
                {
                    "source_frame": str(frame_hashes[digest]),
                    "training_image": str(candidate),
                    "sha256": digest,
                }
            )
    dataset_ids = sorted({record.dataset_id for record in records})
    return {
        "training_manifest": str(manifest),
        "training_manifest_sha256": sha256(manifest),
        "training_rows": len(records),
        "training_dataset_ids": dataset_ids,
        "source_path_overlap": path_overlap,
        "same_size_training_candidates_hashed": len(candidates),
        "exact_byte_duplicates": byte_duplicates,
        "passed": not path_overlap
        and not byte_duplicates
        and "sugarbeets2016" not in {value.lower() for value in dataset_ids},
        "scope": (
            "exact bytes/path and declared dataset ID only; this is not a "
            "perceptual near-duplicate guarantee"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-receipt", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    video_receipt_path = Path(arguments.video_receipt).expanduser().resolve()
    checkpoint_path = Path(arguments.checkpoint).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the accepted-model audit")
    checkpoint_sha = sha256(checkpoint_path)
    if checkpoint_sha != EXPECTED_CHECKPOINT_SHA256:
        raise RuntimeError(
            f"Accepted checkpoint SHA mismatch: {checkpoint_sha} != "
            f"{EXPECTED_CHECKPOINT_SHA256}"
        )
    video_receipt = json.loads(video_receipt_path.read_text(encoding="utf-8"))
    if video_receipt.get("all_automated_quality_gates_passed") is not True:
        raise RuntimeError("Video receipt did not pass automated gates")
    acquisition_path = Path(video_receipt["acquisition_receipt"]).resolve()
    if sha256(acquisition_path) != video_receipt["acquisition_receipt_sha256"]:
        raise RuntimeError("Acquisition receipt changed after video materialization")
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    frame_rows = sorted(
        (
            row
            for row in acquisition["image_inventory"]
            if RGB_MARKER in row["member"]
        ),
        key=lambda row: row["member"],
    )
    frames = [Path(row["path"]).resolve() for row in frame_rows]
    if len(frames) != int(video_receipt["frame_count"]):
        raise RuntimeError("Acquisition/video frame counts differ")
    for frame, row in zip(frames, frame_rows):
        if sha256(frame) != row["sha256"]:
            raise RuntimeError(f"Source frame SHA changed: {frame}")

    output.mkdir(parents=True, exist_ok=False)
    masks_root = output / "semantic_masks"
    semantic_root = output / "semantic_overlays"
    policy_root = output / "policy_overlays"
    for directory in (masks_root, semantic_root, policy_root):
        directory.mkdir()

    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    model.eval()
    config = checkpoint["config"]
    policy, _ = source_calibrated_policy(checkpoint)
    training = config["training"]
    transform = EvalTransform()
    crop_ids = torch.tensor([TARGET_CROP_ID], dtype=torch.long, device=device)
    evaluated: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, frame in enumerate(frames):
        frame_started = time.monotonic()
        with Image.open(frame) as handle:
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
                tile_trigger_pixels=int(
                    training.get("eval_tile_trigger_pixels", 4_000_000)
                ),
            )
            probabilities = logits.float().softmax(dim=1)
            decisions = apply_safety_policy(probabilities, policy, crop_ids)
        probability_array = probabilities[0].cpu().numpy()
        semantic = probability_array.argmax(axis=0).astype(np.uint8)
        unknown = decisions["unknown"][0].cpu().numpy()
        safe_weed = decisions["safe_weed"][0].cpu().numpy()
        weed_candidate = decisions["weed_candidate"][0].cpu().numpy()
        confidence = decisions["confidence"][0].cpu().numpy()
        entropy = decisions["entropy"][0].cpu().numpy()

        mask_path = masks_root / f"prediction_{index:05d}.png"
        Image.fromarray(semantic, mode="L").save(mask_path, optimize=True)
        semantic_overlay = tint(
            source_rgb,
            [
                (semantic == 1, (0, 255, 0)),
                (semantic == 2, (255, 35, 35)),
            ],
        )
        semantic_path = semantic_root / f"prediction_{index:05d}.jpg"
        semantic_overlay.save(semantic_path, quality=94, subsampling=0)
        policy_overlay = tint(
            source_rgb,
            [
                (semantic == 1, (0, 220, 0)),
                (weed_candidate & ~safe_weed, (255, 150, 0)),
                (safe_weed, (255, 0, 40)),
                (unknown, (170, 60, 255)),
            ],
        )
        policy_path = policy_root / f"prediction_{index:05d}.jpg"
        policy_overlay.save(policy_path, quality=94, subsampling=0)
        pixels = semantic.size
        evaluated.append(
            {
                "index": index,
                "frame": frame.name,
                "source_path": str(frame),
                "source_sha256": sha256(frame),
                "semantic_mask": str(mask_path),
                "semantic_mask_sha256": sha256(mask_path),
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
                "confidence": {
                    "mean": float(confidence.mean()),
                    "p05": float(np.percentile(confidence, 5)),
                    "median": float(np.median(confidence)),
                },
                "entropy": {
                    "mean": float(entropy.mean()),
                    "p95": float(np.percentile(entropy, 95)),
                },
                "inference_seconds": time.monotonic() - frame_started,
            }
        )
        del logits, probabilities, decisions, images

    sampled_indices = [
        int(row["index"])
        for row in video_receipt["contact_sheet"]["sampled_frames"]
    ]
    contact_path = output / "accepted_model_contact_sheet.jpg"
    render_contact_sheet(evaluated, sampled_indices, contact_path)
    overlay_video_path = output / "accepted_model_semantic_overlay_1fps.mp4"
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
        str(semantic_root / "prediction_%05d.jpg"),
        "-frames:v",
        str(len(evaluated)),
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
        str(overlay_video_path),
    ]
    encoded = subprocess.run(command, capture_output=True, text=True)
    if encoded.returncode != 0:
        raise RuntimeError(f"Overlay video encoding failed:\n{encoded.stderr[-4000:]}")

    duplicate_audit = exact_training_duplicate_audit(frames, config)
    summaries = {
        "semantic_target_crop_fraction": distribution(
            [row["semantic_fraction"]["target_crop"] for row in evaluated]
        ),
        "semantic_other_vegetation_fraction": distribution(
            [row["semantic_fraction"]["other_vegetation"] for row in evaluated]
        ),
        "safe_weed_fraction": distribution(
            [row["safe_weed_fraction"] for row in evaluated]
        ),
        "unknown_fraction": distribution(
            [row["unknown_fraction"] for row in evaluated]
        ),
        "mean_confidence": distribution(
            [row["confidence"]["mean"] for row in evaluated]
        ),
        "mean_entropy": distribution(
            [row["entropy"]["mean"] for row in evaluated]
        ),
        "inference_seconds": distribution(
            [row["inference_seconds"] for row in evaluated]
        ),
    }
    gates = {
        "accepted_checkpoint_sha256_locked": checkpoint_sha
        == EXPECTED_CHECKPOINT_SHA256,
        "source_tree_sha256_matches_checkpoint": checkpoint["metadata"][
            "source_tree_sha256"
        ]
        == source_tree_sha256(),
        "video_receipt_passed": True,
        "all_frames_evaluated": len(evaluated) == 31,
        "target_crop_identity_explicit": TARGET_CROP_ID == 0,
        "source_calibrated_policy_reused_without_tuning": True,
        "exact_training_duplicate_audit": duplicate_audit["passed"],
        "numeric_accuracy_not_reported": True,
        "selection_score_weight_zero": True,
        "no_motion_unregistered_temporal_iou_reported": True,
    }
    receipt = {
        "schema_version": 1,
        "purpose": "unseen_real_robot_sequence_qualitative_audit",
        "sequence": video_receipt["sequence"],
        "sensor_stream": video_receipt["sensor_stream"],
        "license": video_receipt["license"],
        "video_receipt": str(video_receipt_path),
        "video_receipt_sha256": sha256(video_receipt_path),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint_experiment": config["experiment"],
        "checkpoint_seed": int(config["seed"]),
        "checkpoint_source_tree_sha256": checkpoint["metadata"][
            "source_tree_sha256"
        ],
        "runtime_source_tree_sha256": source_tree_sha256(),
        "conditioning": {
            "target_crop_id": TARGET_CROP_ID,
            "crop_species": TARGET_CROP_SPECIES,
            "basis": "project ontology maps Beta vulgaris to target_crop_id=0",
        },
        "source_frozen_safety_policy": asdict(policy),
        "exact_training_duplicate_audit": duplicate_audit,
        "frames": evaluated,
        "sequence_summaries": summaries,
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "semantic_overlay_video": str(overlay_video_path),
        "semantic_overlay_video_sha256": sha256(overlay_video_path),
        "evaluation_policy": {
            "annotations_present": False,
            "numeric_accuracy_reported": False,
            "miou": None,
            "model_selection_score_weight": 0.0,
            "allowed_interpretation": (
                "qualitative failure discovery and prediction/confidence area traces"
            ),
            "forbidden_interpretation": (
                "accuracy, field-generalization proof, or temporal stability proof"
            ),
            "area_trace_caveat": (
                "Robot motion changes scene content, so adjacent area changes combine "
                "model variation with real scene variation."
            ),
        },
        "manual_prediction_review": "pending",
        "quality_gates": gates,
        "all_automated_quality_gates_passed": all(gates.values()),
        "wall_seconds": time.monotonic() - started,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not math.isclose(
        sum(
            receipt["sequence_summaries"][name]["mean"]
            for name in (
                "semantic_target_crop_fraction",
                "semantic_other_vegetation_fraction",
            )
        )
        + statistics.fmean(
            row["semantic_fraction"]["background"] for row in evaluated
        ),
        1.0,
        abs_tol=1e-6,
    ):
        raise RuntimeError("Mean semantic fractions do not sum to one")
    receipt_path = output / "unseen_sequence_evaluation.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_automated_quality_gates_passed"]:
        raise RuntimeError(f"Unseen-sequence gates failed; see {receipt_path}")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "contact_sheet": str(contact_path),
                "semantic_overlay_video": str(overlay_video_path),
                "frame_count": len(evaluated),
                "sequence_summaries": summaries,
                "all_automated_quality_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
