#!/usr/bin/env python3
"""Measure controlled CUDA latency for one native-size tiled prediction."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import torch
from PIL import Image

from agri_seg.engine import load_checkpoint, predict_logits


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def tile_starts(length: int, tile_size: int, overlap: int) -> list[int]:
    if length <= tile_size:
        return [0]
    stride = tile_size - overlap
    starts = list(range(0, length - tile_size + 1, stride))
    if starts[-1] != length - tile_size:
        starts.append(length - tile_size)
    return starts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference-image", required=True)
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument("--tile-overlap", type=int, default=128)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--crop-id", type=int)
    parser.add_argument("--fp32", action="store_true")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for latency measurement")
    if args.warmup < 1 or args.repeats < 2:
        raise ValueError("Use at least one warm-up and two measured repeats")
    if (
        args.tile_size <= 0
        or args.tile_overlap < 0
        or args.tile_overlap >= args.tile_size
    ):
        raise ValueError("Invalid tile size/overlap")

    destination = Path(args.output).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    checkpoint_path = Path(args.checkpoint).resolve()
    reference_path = Path(args.reference_image).resolve()
    with Image.open(reference_path) as reference:
        width, height = reference.size
        reference_mode = reference.mode

    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    model.eval()
    model_config = checkpoint["config"]["model"]
    known_ids = [int(value) for value in model_config.get("known_crop_ids", [0])]
    crop_id = args.crop_id if args.crop_id is not None else known_ids[0]
    generator = torch.Generator(device=device).manual_seed(20260801)
    image = torch.randn(
        1, 3, height, width, generator=generator, device=device
    )
    crop_ids = torch.tensor([crop_id], dtype=torch.long, device=device)
    use_amp = not args.fp32

    def forward() -> torch.Tensor:
        logits = predict_logits(
            model,
            image,
            crop_ids,
            use_amp=use_amp,
            tile_size=args.tile_size,
            tile_overlap=args.tile_overlap,
            tile_trigger_pixels=0,
        )
        return logits.softmax(dim=1)

    with torch.inference_mode():
        for _ in range(args.warmup):
            forward()
        torch.cuda.synchronize()
        baseline_allocated = torch.cuda.memory_allocated(device)
        baseline_reserved = torch.cuda.memory_reserved(device)
        torch.cuda.reset_peak_memory_stats(device)
        event_pairs: list[tuple[torch.cuda.Event, torch.cuda.Event]] = []
        for _ in range(args.repeats):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            forward()
            end.record()
            event_pairs.append((start, end))
        torch.cuda.synchronize()

    latencies = [float(start.elapsed_time(end)) for start, end in event_pairs]
    mean_latency = statistics.fmean(latencies)
    peak_allocated = torch.cuda.max_memory_allocated(device)
    peak_reserved = torch.cuda.max_memory_reserved(device)
    y_starts = tile_starts(height, args.tile_size, args.tile_overlap)
    x_starts = tile_starts(width, args.tile_size, args.tile_overlap)
    report = {
        "schema_version": 1,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "script_sha256": sha256(__file__),
        "reference_image": str(reference_path),
        "reference_image_sha256": sha256(reference_path),
        "reference_image_mode": reference_mode,
        "device": torch.cuda.get_device_name(device),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
        "architecture": model_config["architecture"],
        "head": model_config.get("head", "flat"),
        "batch_size": 1,
        "image_shape": [1, 3, height, width],
        "target_crop_id": crop_id,
        "precision": "fp32" if args.fp32 else "amp_fp16",
        "tiling": {
            "tile_size": args.tile_size,
            "overlap": args.tile_overlap,
            "stride": args.tile_size - args.tile_overlap,
            "rows": len(y_starts),
            "columns": len(x_starts),
            "tile_count": len(y_starts) * len(x_starts),
            "y_starts": y_starts,
            "x_starts": x_starts,
        },
        "warmup_iterations": args.warmup,
        "measured_iterations": args.repeats,
        "latency_ms": {
            "mean": mean_latency,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "min": min(latencies),
            "max": max(latencies),
        },
        "images_per_second": 1000.0 / mean_latency,
        "cuda_memory_bytes": {
            "baseline_allocated": baseline_allocated,
            "baseline_reserved": baseline_reserved,
            "peak_allocated": peak_allocated,
            "peak_reserved": peak_reserved,
            "incremental_peak_allocated": max(
                0, peak_allocated - baseline_allocated
            ),
        },
        "total_parameters": sum(
            parameter.numel() for parameter in model.parameters()
        ),
        "trainable_parameters": sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        ),
        "includes_preprocessing": False,
        "includes_tiling": True,
        "includes_softmax": True,
        "includes_safety_policy": False,
        "input_content": "seeded synthetic tensor at reference native shape",
        "synchronization": "CUDA events with one final device synchronize",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
