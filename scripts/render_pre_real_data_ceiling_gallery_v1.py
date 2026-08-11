#!/usr/bin/env python3
"""Render two locked BoniRob examples for the selected pre-real checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import torch
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_cropcraft_deploy_synthetic_diagnostic_v1 import render_example
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    load_ground_truth,
    release_cuda,
    sha256,
)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def selected_threshold(
    diagnostics: Mapping[str, Any], model_name: str, method: str, size: float
) -> float:
    return float(
        diagnostics["phenobench"]["results"][model_name]["methods"][method]
        ["eligible_size_views"][str(int(size))]["validation_calibration"]
        ["balanced_max_f1"]["threshold"]
    )


def locked_inputs(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(PROJECT_ROOT, config["data_root"])
    paths = {
        "checkpoint": resolve(data_root, config["checkpoint"]),
        "diagnostics": resolve(data_root, config["diagnostics"]),
        "bonirob_receipt": resolve(data_root, config["bonirob_receipt"]),
    }
    for name, path in paths.items():
        expected = str(config[f"{name}_sha256"])
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Locked input mismatch: {name}: {path}")
    diagnostics = json.loads(paths["diagnostics"].read_text(encoding="utf-8"))
    receipt = json.loads(paths["bonirob_receipt"].read_text(encoding="utf-8"))
    model_name = str(config["model_name"])
    locked_model = diagnostics["locked_models"][model_name]
    if locked_model["sha256"] != str(config["checkpoint_sha256"]):
        raise ValueError("Diagnostics/checkpoint identity mismatch")
    if diagnostics["decision"]["selected_pre_real_model"] != model_name:
        raise ValueError("Gallery model is not the selected pre-real model")
    if diagnostics["decision"]["field_fire_go"] is not False:
        raise ValueError("Gallery must not imply field-fire authorization")
    membership = Path(receipt["membership"]).resolve()
    if not membership.is_file() or sha256(membership) != receipt["membership_sha256"]:
        raise ValueError("BoniRob membership mismatch")
    indices = [int(value) for value in config["frame_indices"]]
    if len(indices) != len(set(indices)) or any(index < 0 for index in indices):
        raise ValueError("Frame indices must be unique and non-negative")
    return {
        "config": config,
        "config_path": config_path,
        "data_root": data_root,
        "paths": paths,
        "diagnostics": diagnostics,
        "receipt": receipt,
        "membership": membership,
        "indices": indices,
    }


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {
            name: False
            for name in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb")
        }
    )
    locked = locked_inputs(config_path)
    config = locked["config"]
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    records = load_ground_truth(
        locked["membership"], "test", int(config["minimum_component_area_px"])
    )
    if any(index >= len(records) for index in locked["indices"]):
        raise IndexError("Gallery frame index is outside the locked panel")
    output = resolve(locked["data_root"], config["output"])
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output if output.exists() else partial)
    partial.mkdir(parents=True)
    model = YOLO(str(locked["paths"]["checkpoint"]))
    if model.task != "segment":
        raise ValueError("Selected checkpoint is not a segmentation model")
    threshold = selected_threshold(
        locked["diagnostics"],
        str(config["model_name"]),
        str(config["primary_method"]),
        float(config["primary_service_minimum_sqrt_box_px"]),
    )
    frames: list[dict[str, Any]] = []
    try:
        for index in locked["indices"]:
            truth = records[index]
            destination = partial / f"bonirob_{index:03d}.jpg"
            render_example(
                model,
                truth,
                threshold=threshold,
                inference=config["inference"],
                output=destination,
                title=(
                    "ROSE native-detail aday — BoniRob dış robot-view "
                    "geliştirme paneli"
                ),
            )
            frames.append(
                {
                    "frame_index": index,
                    "sample_id": truth.sample_id,
                    "path": str(output / destination.name),
                    "sha256": sha256(destination),
                }
            )
    finally:
        release_cuda(model)
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "selected_pre_real_gallery_complete_not_deployment_proof",
        "config": str(locked["config_path"]),
        "config_sha256": sha256(locked["config_path"]),
        "model": {
            "name": config["model_name"],
            "checkpoint": str(locked["paths"]["checkpoint"]),
            "sha256": sha256(locked["paths"]["checkpoint"]),
        },
        "threshold": {
            "value": threshold,
            "source": "same model PhenoBench validation; no BoniRob tuning",
            "minimum_sqrt_gt_box_area_px": float(
                config["primary_service_minimum_sqrt_box_px"]
            ),
        },
        "panel": {
            "receipt": str(locked["paths"]["bonirob_receipt"]),
            "receipt_sha256": sha256(locked["paths"]["bonirob_receipt"]),
            "membership": str(locked["membership"]),
            "membership_sha256": sha256(locked["membership"]),
        },
        "frames": frames,
        "claims": config["claims"],
    }
    (partial / "gallery_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (partial / "README.md").write_text(
        "# Directional pre-real model gallery\n\n"
        "Green ground truth is crop, red ground truth is weed; green prediction is crop, "
        "purple prediction is weed. A blue point is a safe weed contact and a yellow cross "
        "is an incorrect action. The threshold is frozen on PhenoBench validation. BoniRob "
        "is a consumed one-session development panel, not target-rig or deployment proof.\n",
        encoding="utf-8",
    )
    partial.replace(output)
    print(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/pre_real_data_ceiling_gallery_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
