#!/usr/bin/env python3
"""Gate a bounded CropCraft release against frozen RiceSEG RGB statistics."""

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


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def aggregate(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Cannot aggregate an empty release")
    metrics: dict[str, Any] = {}
    for name in sorted(rows[0]):
        values = np.asarray([row[name] for row in rows], dtype=np.float64)
        metrics[name] = {
            "mean": float(values.mean()),
            "q05": float(np.quantile(values, 0.05)),
            "q50": float(np.quantile(values, 0.50)),
            "q95": float(np.quantile(values, 0.95)),
        }
    return {"samples": len(rows), "metrics": metrics}


def frame_stats(image_path: Path, mask_path: Path) -> dict[str, float]:
    with Image.open(image_path) as handle:
        rgb = np.asarray(
            handle.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR),
            dtype=np.float32,
        ) / 255.0
    with Image.open(mask_path) as handle:
        mask = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    colors = {tuple(int(value) for value in color) for color in mask.reshape(-1, 3)}
    allowed = {(0, 0, 0), (0, 255, 0), (255, 0, 0)}
    if not colors <= allowed:
        raise ValueError(f"Unexpected semantic palette in {mask_path}: {colors - allowed}")
    crop = np.all(mask == np.array([0, 255, 0], dtype=np.uint8), axis=2)
    weed = np.all(mask == np.array([255, 0, 0], dtype=np.uint8), axis=2)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    saturation = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )
    gray = rgb.mean(axis=2)
    texture = (
        np.abs(np.diff(gray, axis=0)).mean()
        + np.abs(np.diff(gray, axis=1)).mean()
    ) / 2.0
    laplacian = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return {
        "brightness_mean": float(rgb.mean()),
        "brightness_std": float(rgb.std()),
        "saturation_mean": float(saturation.mean()),
        "green_dominance": float(
            (rgb[:, :, 1] - (rgb[:, :, 0] + rgb[:, :, 2]) / 2.0).mean()
        ),
        "texture_abs_gradient": float(texture),
        "laplacian_variance": float(laplacian.var()),
        "shadow_fraction": float(np.count_nonzero(maximum < 0.08) / maximum.size),
        "highlight_fraction": float(np.count_nonzero(minimum > 0.92) / minimum.size),
        "crop_fraction": float(crop.mean()),
        "weed_fraction": float(weed.mean()),
    }


def analyze(
    release: Path, reference_report: Path, gate_path: Path, phase: str
) -> dict[str, Any]:
    release = release.expanduser().resolve()
    reference_report = reference_report.expanduser().resolve()
    gate_path = gate_path.expanduser().resolve()
    reference = load_object(reference_report)
    gate = load_object(gate_path)
    receipt_path = release / "release_receipt.json"
    receipt = load_object(receipt_path)
    if receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError(f"Release quality receipt has not passed: {receipt_path}")
    locked_reference = gate["selection_evidence_lock"]
    if sha256(reference_report) != locked_reference["sha256"]:
        raise RuntimeError("RiceSEG condition report differs from the frozen gate")
    if phase not in {"smoke", "pilot"}:
        raise ValueError(f"Unknown phase: {phase}")
    phase_gate = gate["bounded_render_gate"][phase]
    expected_pairs = int(phase_gate["expected_pairs"])
    image_paths = sorted(release.glob("scenes/*/render/images/*.jpg"))
    mask_paths = sorted(release.glob("scenes/*/render/masks/*.png"))
    image_by_key = {
        (path.parents[2].name, path.stem): path for path in image_paths
    }
    mask_by_key = {(path.parents[2].name, path.stem): path for path in mask_paths}
    if set(image_by_key) != set(mask_by_key):
        raise RuntimeError("RGB/mask key sets differ")
    rows = [
        frame_stats(image_by_key[key], mask_by_key[key])
        for key in sorted(image_by_key)
    ]
    synthetic = aggregate(rows)
    real = reference["riceseg"]["rgb_common_statistics"]
    required_metrics = gate["bounded_render_gate"]["rice_seg_distribution_lock"][
        "required_synthetic_median_within_real_q05_q95"
    ]
    metric_checks: dict[str, bool] = {}
    comparison: dict[str, Any] = {}
    for metric in required_metrics:
        synthetic_median = float(synthetic["metrics"][metric]["q50"])
        real_q05 = float(real["metrics"][metric]["q05"])
        real_q95 = float(real["metrics"][metric]["q95"])
        passed = real_q05 <= synthetic_median <= real_q95
        metric_checks[str(metric)] = passed
        comparison[str(metric)] = {
            "synthetic_q50": synthetic_median,
            "riceseg_q05": real_q05,
            "riceseg_q95": real_q95,
            "passed": passed,
        }
    checks = {
        "expected_pairs": len(rows) == expected_pairs,
        "receipt_frame_count": int(receipt["frames"]) == expected_pairs,
        "receipt_quality_passed": receipt["all_quality_gates_passed"] is True,
        **{f"median_{name}": value for name, value in metric_checks.items()},
    }
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "release": str(release),
        "release_receipt": str(receipt_path),
        "release_receipt_sha256": sha256(receipt_path),
        "gate": str(gate_path),
        "gate_sha256": sha256(gate_path),
        "riceseg_reference_report": str(reference_report),
        "riceseg_reference_report_sha256": sha256(reference_report),
        "synthetic": synthetic,
        "riceseg": real,
        "required_metric_comparison": comparison,
        "quality_gate_checks": checks,
        "all_quality_gates_passed": all(checks.values()),
        "interpretation": (
            "This rejects gross low-order RGB/coverage mismatch only. Manual "
            "morphology review and equal-budget model A/B remain mandatory."
        ),
        "large_synthetic_batch_generated": phase == "pilot" and len(rows) > 100,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--reference-report", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--phase", required=True, choices=("smoke", "pilot"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = analyze(
        Path(args.release), Path(args.reference_report), Path(args.gate), args.phase
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["all_quality_gates_passed"]:
        raise RuntimeError(f"RiceSEG distribution gate failed; see {output}")


if __name__ == "__main__":
    main()
