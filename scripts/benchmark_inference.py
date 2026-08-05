#!/usr/bin/env python3
"""Measure reproducible batch-1 PyTorch CUDA latency and peak memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import torch

from agri_seg.engine import load_checkpoint


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("--output", required=True)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--crop-id", type=int)
    parser.add_argument("--fp32", action="store_true")
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for latency measurement")
    if args.warmup < 1 or args.repeats < 2:
        raise ValueError("Use at least one warm-up and two measured repeats")

    destination = Path(args.output).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    checkpoint_path = Path(args.checkpoint).resolve()
    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    model.eval()
    model_config = checkpoint["config"]["model"]
    known_ids = [int(value) for value in model_config.get("known_crop_ids", [0])]
    crop_id = args.crop_id if args.crop_id is not None else known_ids[0]
    generator = torch.Generator(device=device).manual_seed(20260731)
    image = torch.randn(
        args.batch_size,
        3,
        args.image_size,
        args.image_size,
        generator=generator,
        device=device,
    )
    crop_ids = torch.full(
        (args.batch_size,), crop_id, dtype=torch.long, device=device
    )
    use_amp = not args.fp32

    def forward() -> torch.Tensor:
        with torch.autocast(
            device_type="cuda", dtype=torch.float16, enabled=use_amp
        ):
            return model(image, crop_ids).softmax(dim=1)

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
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    trainable_parameters = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    peak_allocated = torch.cuda.max_memory_allocated(device)
    peak_reserved = torch.cuda.max_memory_reserved(device)
    mean_latency = statistics.fmean(latencies)
    report = {
        "schema_version": 1,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "script_sha256": sha256(__file__),
        "device": torch.cuda.get_device_name(device),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
        "architecture": model_config["architecture"],
        "head": model_config.get("head", "flat"),
        "batch_size": args.batch_size,
        "image_shape": [args.batch_size, 3, args.image_size, args.image_size],
        "target_crop_id": crop_id,
        "precision": "fp32" if args.fp32 else "amp_fp16",
        "warmup_iterations": args.warmup,
        "measured_iterations": args.repeats,
        "latency_ms": {
            "mean": mean_latency,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "min": min(latencies),
            "max": max(latencies),
        },
        "images_per_second": args.batch_size * 1000.0 / mean_latency,
        "cuda_memory_bytes": {
            "baseline_allocated": baseline_allocated,
            "baseline_reserved": baseline_reserved,
            "peak_allocated": peak_allocated,
            "peak_reserved": peak_reserved,
            "incremental_peak_allocated": max(
                0, peak_allocated - baseline_allocated
            ),
        },
        "total_parameters": total_parameters,
        "trainable_parameters": trainable_parameters,
        "includes_preprocessing": False,
        "includes_tiling": False,
        "includes_safety_policy": False,
        "synchronization": "CUDA events with one final device synchronize",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
