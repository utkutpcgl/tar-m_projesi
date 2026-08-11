#!/usr/bin/env python3
"""Benchmark the proposed spot-spray raster geometry and YOLO segmentation path."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml
from PIL import Image


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("At least one value is required")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("Quantile must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def gsd_mm_per_px(field_width_mm: float, raster_width_px: int) -> float:
    if field_width_mm <= 0 or raster_width_px <= 0:
        raise ValueError("Field width and raster width must be positive")
    return float(field_width_mm) / int(raster_width_px)


def feature_pixels(feature_size_mm: float, gsd_mm_px: float) -> float:
    if feature_size_mm <= 0 or gsd_mm_px <= 0:
        raise ValueError("Feature size and GSD must be positive")
    return float(feature_size_mm) / float(gsd_mm_px)


def max_exposure_us(
    gsd_mm_px: float, speed_m_s: float, maximum_blur_px: float
) -> float:
    if gsd_mm_px <= 0 or speed_m_s <= 0 or maximum_blur_px <= 0:
        raise ValueError("GSD, speed, and blur limit must be positive")
    speed_mm_s = float(speed_m_s) * 1000.0
    return maximum_blur_px * gsd_mm_px / speed_mm_s * 1_000_000.0


def required_frame_rate_hz(
    speed_m_s: float, longitudinal_fov_mm: float, observations: int
) -> float:
    if speed_m_s <= 0 or longitudinal_fov_mm <= 0 or observations <= 0:
        raise ValueError("Speed, field length, and observations must be positive")
    dwell_seconds = longitudinal_fov_mm / (speed_m_s * 1000.0)
    return observations / dwell_seconds


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def derive_imaging_metrics(contract: Mapping[str, Any]) -> dict[str, Any]:
    raw_width = int(contract["raw_sensor_width_px"])
    raw_height = int(contract["raw_sensor_height_px"])
    rows = int(contract["tile_rows"])
    columns = int(contract["tile_columns"])
    tile_size = int(contract["tile_size_px"])
    halo = int(contract.get("tile_halo_px", 0))
    if halo < 0:
        raise ValueError("Tile halo cannot be negative")
    if raw_width != columns * tile_size or raw_height != rows * tile_size:
        raise ValueError("The tile grid must exactly cover the proposed raw raster")
    gsd_x = gsd_mm_per_px(float(contract["field_width_mm"]), raw_width)
    gsd_y = gsd_mm_per_px(float(contract["field_height_mm"]), raw_height)
    if abs(gsd_x - gsd_y) > 1e-9:
        raise ValueError("This v1 contract requires square pixels in world space")

    weed_sizes = {
        "minimum_actionable": float(contract["minimum_actionable_weed_diameter_mm"]),
        "primary_actionable": float(contract["primary_actionable_weed_diameter_mm"]),
    }
    speeds = [float(speed) for speed in contract["travel_speeds_m_s"]]
    blur = float(contract["maximum_blur_px"])
    observations = int(contract["minimum_track_observations"])
    field_height = float(contract["field_height_mm"])
    return {
        "gsd_mm_per_px": gsd_x,
        "weed_diameter_px": {
            name: feature_pixels(size, gsd_x) for name, size in weed_sizes.items()
        },
        "maximum_exposure_us_by_speed": {
            str(speed): max_exposure_us(gsd_x, speed, blur) for speed in speeds
        },
        "minimum_frame_rate_hz_by_speed_for_track_observations": {
            str(speed): required_frame_rate_hz(speed, field_height, observations)
            for speed in speeds
        },
        "tiles_per_module_frame": rows * columns,
        "tile_core_size_px": tile_size,
        "tile_halo_px": halo,
        "model_input_size_px": tile_size + 2 * halo,
        "tile_world_width_mm": float(contract["field_width_mm"]) / columns,
        "tile_world_height_mm": field_height / rows,
    }


def _load_bgr_images(
    paths: Sequence[Path], native_size: int, halo_px: int
) -> list[np.ndarray]:
    images: list[np.ndarray] = []
    for path in paths:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            if rgb.size != (native_size, native_size):
                raise ValueError(
                    f"Reference image must be native {native_size}x{native_size}: "
                    f"{path} is {rgb.size}"
                )
            bgr = np.asarray(rgb, dtype=np.uint8)[:, :, ::-1].copy()
            if halo_px:
                bgr = np.pad(
                    bgr,
                    ((halo_px, halo_px), (halo_px, halo_px), (0, 0)),
                    mode="reflect",
                )
            images.append(bgr)
    return images


def _prediction_count(results: Sequence[Any]) -> int:
    return sum(0 if result.boxes is None else len(result.boxes) for result in results)


def benchmark_batch(
    model: Any,
    images: Sequence[np.ndarray],
    *,
    batch_size: int,
    warmups: int,
    repeats: int,
    predict_args: Mapping[str, Any],
) -> dict[str, Any]:
    if batch_size <= 0 or warmups < 1 or repeats < 2:
        raise ValueError("Use a positive batch, >=1 warm-up, and >=2 repeats")
    if len(images) < batch_size:
        raise ValueError("Not enough distinct reference frames for requested batch")
    source = list(images[:batch_size])
    with torch.inference_mode():
        for _ in range(warmups):
            model.predict(source=source, **predict_args)
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        latencies_ms: list[float] = []
        prediction_counts: list[int] = []
        for _ in range(repeats):
            torch.cuda.synchronize()
            started = time.perf_counter()
            results = model.predict(source=source, **predict_args)
            torch.cuda.synchronize()
            latencies_ms.append((time.perf_counter() - started) * 1000.0)
            prediction_counts.append(_prediction_count(results))
    mean_ms = statistics.fmean(latencies_ms)
    return {
        "batch_size": batch_size,
        "warmup_iterations": warmups,
        "measured_iterations": repeats,
        "latency_ms": {
            "mean": mean_ms,
            "p50": percentile(latencies_ms, 0.50),
            "p95": percentile(latencies_ms, 0.95),
            "min": min(latencies_ms),
            "max": max(latencies_ms),
        },
        "tiles_per_second": batch_size * 1000.0 / mean_ms,
        "prediction_count_per_batch": {
            "mean": statistics.fmean(prediction_counts),
            "min": min(prediction_counts),
            "max": max(prediction_counts),
        },
        "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(),
    }


def run(config_path: Path, *, overwrite: bool = False) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {
            "clearml": False,
            "comet": False,
            "dvc": False,
            "hub": False,
            "mlflow": False,
            "neptune": False,
            "wandb": False,
        }
    )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the deploy compute gate")
    config_path = config_path.expanduser().resolve()
    project_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = _resolve(project_root, config["data_root"])
    checkpoint = _resolve(data_root, config["checkpoint"])
    if sha256(checkpoint) != str(config["checkpoint_sha256"]):
        raise ValueError("Locked checkpoint SHA-256 mismatch")
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")

    inference = config["inference"]
    image_size = int(inference["image_size"])
    reference_paths = [
        _resolve(data_root, value) for value in config["reference_images"]
    ]
    for path in reference_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    imaging = derive_imaging_metrics(config["imaging_contract"])
    if image_size != int(imaging["model_input_size_px"]):
        raise ValueError("Inference size must equal tile core plus two halos")
    images = _load_bgr_images(
        reference_paths,
        int(imaging["tile_core_size_px"]),
        int(imaging["tile_halo_px"]),
    )
    model = YOLO(str(checkpoint))
    predict_args = {
        "imgsz": image_size,
        "device": int(inference["device"]),
        "half": bool(inference["half"]),
        "conf": float(inference["confidence"]),
        "iou": float(inference["iou"]),
        "max_det": int(inference["max_detections"]),
        "verbose": False,
        "save": False,
    }
    timing = {}
    for batch_size in (int(value) for value in inference["batch_sizes"]):
        result = benchmark_batch(
            model,
            images,
            batch_size=batch_size,
            warmups=int(inference["warmup_iterations"]),
            repeats=int(inference["measured_iterations"]),
            predict_args=predict_args,
        )
        result["estimated_module_frames_per_second"] = (
            result["tiles_per_second"] / imaging["tiles_per_module_frame"]
        )
        timing[str(batch_size)] = result

    report = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script_sha256": sha256(__file__),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "reference_images": [
            {"path": str(path), "sha256": sha256(path)} for path in reference_paths
        ],
        "device": torch.cuda.get_device_name(int(inference["device"])),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "ultralytics_version": ultralytics_version,
        "imaging_contract": config["imaging_contract"],
        "derived_imaging_metrics": imaging,
        "inference_contract": inference,
        "timing_by_batch_size": timing,
        "scope": {
            "included": [
                "preloaded real RGB pixels",
                "preprocessing",
                "GPU model forward",
                "NMS",
                "segmentation mask construction",
                "result transfer to CPU",
            ],
            "excluded": [
                "camera acquisition and transport",
                "filesystem decode",
                "temporal tracking",
                "actuator latency",
                "spray physics",
            ],
        },
        "claims": config["claims"],
    }

    outputs = config["outputs"]
    full_output = _resolve(data_root, outputs["full_report"])
    summary_output = _resolve(project_root, outputs["repository_summary"])
    for output in (full_output, summary_output):
        if output.exists() and not overwrite:
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
    full_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "schema_version": report["schema_version"],
        "protocol": report["protocol"],
        "checkpoint_sha256": report["checkpoint_sha256"],
        "device": report["device"],
        "derived_imaging_metrics": imaging,
        "timing_by_batch_size": timing,
        "full_report": str(full_output),
        "scope": report["scope"],
    }
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/spot_spray_deploy_compute_v1.yaml"),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run(args.config, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
