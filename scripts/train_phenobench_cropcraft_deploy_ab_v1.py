#!/usr/bin/env python3
"""Train one arm of the equal-exposure deploy-synthetic segmentation A/B."""

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


ARMS = ("control_real_replay", "challenger_real_synthetic")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def locked_inputs(config_path: Path, arm_name: str) -> tuple[dict[str, Any], Path, Path, Path, dict[str, Any]]:
    if arm_name not in ARMS:
        raise ValueError(f"Unknown arm: {arm_name}")
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = resolve(project_root, config["data_root"])
    receipt_path = resolve(data_root, config["ab_dataset_receipt"])
    checkpoint = resolve(data_root, config["initial_checkpoint"])
    arm = config["arms"][arm_name]
    dataset_yaml = resolve(data_root, arm["dataset_yaml"])
    for path, expected in (
        (receipt_path, str(config["ab_dataset_receipt_sha256"])),
        (checkpoint, str(config["initial_checkpoint_sha256"])),
        (dataset_yaml, str(arm["dataset_yaml_sha256"])),
    ):
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Locked input mismatch: {path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError("A/B dataset receipt did not pass")
    counts = receipt["arm_train_counts"]
    if set(counts) != set(ARMS) or len(set(int(value) for value in counts.values())) != 1:
        raise RuntimeError("A/B arm exposure differs")
    if sha256(dataset_yaml) != receipt["dataset_yamls"][arm_name]["sha256"]:
        raise RuntimeError("Config and dataset receipt YAML hashes differ")
    return config, data_root, receipt_path, checkpoint, {**arm, "dataset_yaml_path": dataset_yaml, "train_images": int(counts[arm_name])}


def run(config_path: Path, arm_name: str) -> dict[str, Any]:
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
    config, data_root, receipt_path, checkpoint, arm = locked_inputs(config_path, arm_name)
    if ultralytics_version != str(config["model_family"]["package_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    training = config["training"]
    output_project = resolve(data_root, config["output"]["project"])
    run_name = str(arm["run_name"])
    run_directory = output_project / run_name
    if run_directory.exists():
        raise FileExistsError(run_directory)
    model = YOLO(str(checkpoint))
    if model.task != "segment":
        raise ValueError("Initial checkpoint is not a segmentation model")
    started = time.monotonic()
    results = model.train(
        data=str(arm["dataset_yaml_path"]),
        project=str(output_project),
        name=run_name,
        exist_ok=False,
        epochs=int(training["epochs"]),
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
        pretrained=True,
        val=bool(training["val"]),
        plots=bool(training["plots"]),
        verbose=True,
    )
    elapsed = time.monotonic() - started
    last = run_directory / "weights/last.pt"
    results_csv = run_directory / "results.csv"
    if not last.is_file() or not results_csv.is_file():
        raise RuntimeError("Training artifacts are incomplete")
    completed_epochs = max(0, len(results_csv.read_text(encoding="utf-8").splitlines()) - 1)
    if completed_epochs != int(training["epochs"]):
        raise RuntimeError("Fixed epoch exposure was violated")
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "equal_exposure_training_arm_complete_real_val_test_not_touched",
        "arm": arm_name,
        "config": str(config_path.expanduser().resolve()),
        "config_sha256": sha256(config_path.expanduser().resolve()),
        "dataset_receipt": str(receipt_path),
        "dataset_receipt_sha256": sha256(receipt_path),
        "dataset_yaml": str(arm["dataset_yaml_path"]),
        "dataset_yaml_sha256": sha256(arm["dataset_yaml_path"]),
        "initial_checkpoint": str(checkpoint),
        "initial_checkpoint_sha256": sha256(checkpoint),
        "train_images_per_epoch": arm["train_images"],
        "training": {
            "epochs_requested": int(training["epochs"]),
            "epochs_completed": completed_epochs,
            "batch": int(training["batch"]),
            "seed": int(training["seed"]),
            "image_size": int(training["image_size"]),
            "results": plain(getattr(results, "results_dict", {})),
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(int(training["device"])),
            "elapsed_seconds": elapsed,
            "ultralytics": ultralytics_version,
        },
        "selection": config["selection"],
        "artifacts": {
            "run_directory": str(run_directory),
            "fixed_final_checkpoint": str(last),
            "fixed_final_checkpoint_sha256": sha256(last),
            "results_csv": str(results_csv),
            "results_csv_sha256": sha256(results_csv),
        },
        "claims": config["claims"],
    }
    receipt_path_out = run_directory / "run_receipt.json"
    receipt_path_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "artifacts": receipt["artifacts"]}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=ARMS)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_cropcraft_deploy_training_ab_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config, arguments.arm)


if __name__ == "__main__":
    main()
