#!/usr/bin/env python3
"""Train one locked arm of the fair PhenoBench detection/segmentation A/B."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path
from typing import Any

import torch
import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def locked_inputs(
    config: dict[str, Any], project_root: Path, arm_name: str
) -> tuple[Path, Path, Path, dict[str, Any]]:
    if arm_name not in {"detect", "segment"}:
        raise ValueError(f"Unknown arm: {arm_name}")
    data_root = _resolve(project_root, config["data_root"])
    receipt_path = _resolve(data_root, config["dataset_receipt"])
    if sha256(receipt_path) != str(config["dataset_receipt_sha256"]):
        raise ValueError("Dataset receipt SHA-256 mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    quality = receipt["quality"]
    required_quality = {
        "detect_segment_image_membership_equal": True,
        "detect_segment_eligible_instance_membership_equal": True,
        "full_pixels_without_instance_id": 0,
        "instances_without_valid_polygon": 0,
    }
    for key, expected in required_quality.items():
        if quality.get(key) != expected:
            raise ValueError(f"Dataset quality contract failed: {key}")

    arm = dict(config["arms"][arm_name])
    dataset_yaml = _resolve(data_root, arm["dataset_yaml"])
    checkpoint = _resolve(data_root, arm["pretrained_checkpoint"])
    if sha256(dataset_yaml) != str(arm["dataset_yaml_sha256"]):
        raise ValueError(f"{arm_name} dataset YAML SHA-256 mismatch")
    if sha256(checkpoint) != str(arm["pretrained_checkpoint_sha256"]):
        raise ValueError(f"{arm_name} pretrained checkpoint SHA-256 mismatch")
    return data_root, dataset_yaml, checkpoint, arm


def run(
    config_path: Path,
    arm_name: str,
    *,
    epochs_override: int | None = None,
    fraction: float = 1.0,
    name_suffix: str = "",
) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    disabled_integrations = {
        "clearml": False,
        "comet": False,
        "dvc": False,
        "hub": False,
        "mlflow": False,
        "neptune": False,
        "wandb": False,
    }
    settings.update(disabled_integrations)
    if any(bool(settings.get(key)) for key in disabled_integrations):
        raise RuntimeError("Could not disable every external integration")

    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root, dataset_yaml, checkpoint, arm = locked_inputs(
        config, project_root, arm_name
    )
    expected_version = str(config["model_family"]["package_version"])
    if ultralytics_version != expected_version:
        raise ValueError(
            f"Expected ultralytics {expected_version}, got {ultralytics_version}"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this benchmark")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")

    training = dict(config["training"])
    epochs = int(epochs_override or training["epochs"])
    if epochs <= 0:
        raise ValueError("epochs must be positive")
    output_project = _resolve(data_root, config["output"]["project"])
    run_name = str(arm["run_name"]) + name_suffix
    run_directory = output_project / run_name
    if run_directory.exists():
        raise FileExistsError(run_directory)

    model = YOLO(str(checkpoint))
    if str(model.task) != str(arm["task"]):
        raise ValueError(f"Expected task {arm['task']}, checkpoint is {model.task}")
    pretrained_parameter_count = sum(
        parameter.numel() for parameter in model.model.parameters()
    )
    started = time.monotonic()
    results = model.train(
        data=str(dataset_yaml),
        project=str(output_project),
        name=run_name,
        exist_ok=False,
        epochs=epochs,
        patience=int(training["patience"]),
        imgsz=int(training["image_size"]),
        batch=int(training["batch"]),
        workers=int(training["workers"]),
        device=int(training["device"]),
        seed=int(training["seed"]),
        deterministic=bool(training["deterministic"]),
        amp=bool(training["amp"]),
        optimizer=str(training["optimizer"]),
        lr0=float(training["lr0"]),
        lrf=float(training["lrf"]),
        momentum=float(training["momentum"]),
        weight_decay=float(training["weight_decay"]),
        warmup_epochs=float(training["warmup_epochs"]),
        warmup_momentum=float(training["warmup_momentum"]),
        warmup_bias_lr=float(training["warmup_bias_lr"]),
        cos_lr=bool(training["cos_lr"]),
        cache=str(training["cache"]),
        hsv_h=float(training["hsv_h"]),
        hsv_s=float(training["hsv_s"]),
        hsv_v=float(training["hsv_v"]),
        degrees=float(training["degrees"]),
        translate=float(training["translate"]),
        scale=float(training["scale"]),
        shear=float(training["shear"]),
        perspective=float(training["perspective"]),
        fliplr=float(training["fliplr"]),
        flipud=float(training["flipud"]),
        mosaic=float(training["mosaic"]),
        mixup=float(training["mixup"]),
        copy_paste=float(training["copy_paste"]),
        close_mosaic=int(training["close_mosaic"]),
        mask_ratio=int(training["mask_ratio"]),
        overlap_mask=bool(training["overlap_mask"]),
        fraction=float(fraction),
        pretrained=True,
        val=True,
        plots=True,
        verbose=True,
    )
    elapsed = time.monotonic() - started
    best = run_directory / "weights/best.pt"
    last = run_directory / "weights/last.pt"
    results_csv = run_directory / "results.csv"
    if not best.is_file() or not last.is_file() or not results_csv.is_file():
        raise RuntimeError("Training did not create the expected artifacts")
    completed_epochs = max(0, len(results_csv.read_text(encoding="utf-8").splitlines()) - 1)
    if completed_epochs != epochs:
        raise RuntimeError(
            f"Fixed exposure violated: requested {epochs}, completed {completed_epochs}"
        )
    trained_model = YOLO(str(last))
    trained_parameter_count = sum(
        parameter.numel() for parameter in trained_model.model.parameters()
    )

    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "fair_training_arm_complete_test_not_touched",
        "arm": arm_name,
        "task": arm["task"],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_yaml": str(dataset_yaml),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "dataset_receipt": str(_resolve(data_root, config["dataset_receipt"])),
        "dataset_receipt_sha256": config["dataset_receipt_sha256"],
        "pretrained_checkpoint": str(checkpoint),
        "pretrained_checkpoint_sha256": sha256(checkpoint),
        "ultralytics_version": ultralytics_version,
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(int(training["device"])),
            "elapsed_seconds": elapsed,
        },
        "training": {
            "epochs_requested": epochs,
            "epochs_completed": completed_epochs,
            "fraction": fraction,
            "parameter_count": trained_parameter_count,
            "pretrained_parameter_count": pretrained_parameter_count,
            "results": _plain(getattr(results, "results_dict", {})),
        },
        "selection": dict(config["selection"]),
        "artifacts": {
            "run_directory": str(run_directory),
            "best_checkpoint": str(best),
            "best_checkpoint_sha256": sha256(best),
            "fixed_final_checkpoint": str(last),
            "fixed_final_checkpoint_sha256": sha256(last),
            "results_csv": str(results_csv),
            "results_csv_sha256": sha256(results_csv),
        },
        "claims": list(config["claims"]),
    }
    receipt_path = run_directory / "run_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("detect", "segment"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "configs/benchmark/phenobench_detect_segment_training_fair_v1.yaml"
        ),
    )
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--name-suffix", default="")
    arguments = parser.parse_args()
    receipt = run(
        arguments.config,
        arguments.arm,
        epochs_override=arguments.epochs,
        fraction=arguments.fraction,
        name_suffix=arguments.name_suffix,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
