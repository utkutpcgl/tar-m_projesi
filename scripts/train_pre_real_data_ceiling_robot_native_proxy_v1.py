#!/usr/bin/env python3
"""Train the one matched native-detail real-robot proxy challenger."""

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


def locked_inputs(config_path: Path) -> tuple[dict[str, Any], Path, Path, Path, Path]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = resolve(project_root, config["data_root"])
    receipt_path = resolve(data_root, config["dataset_receipt"])
    dataset_yaml = resolve(data_root, config["dataset_yaml"])
    checkpoint = resolve(data_root, config["initial_checkpoint"])
    reference = resolve(data_root, config["matched_reference"]["checkpoint"])
    for path, expected in (
        (receipt_path, str(config["dataset_receipt_sha256"])),
        (dataset_yaml, str(config["dataset_yaml_sha256"])),
        (checkpoint, str(config["initial_checkpoint_sha256"])),
        (reference, str(config["matched_reference"]["checkpoint_sha256"])),
    ):
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Locked input mismatch: {path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Robot-native dataset receipt did not pass")
    train_images = int(receipt["counts"]["train_images_per_epoch"])
    if train_images != int(config["matched_reference"]["train_images_per_epoch"]):
        raise RuntimeError("Current winner and challenger exposure counts differ")
    if int(receipt["counts"]["rose_native_robot_proxy_train"]) != 80:
        raise RuntimeError("Expected exactly 80 ROSE robot proxy crops")
    if sha256(dataset_yaml) != receipt["dataset_yaml_sha256"]:
        raise RuntimeError("Dataset YAML hash does not match its receipt")
    return config, data_root, receipt_path, dataset_yaml, checkpoint


def completed_epochs(results_csv: Path) -> int:
    if not results_csv.is_file():
        return 0
    return max(0, len(results_csv.read_text(encoding="utf-8").splitlines()) - 1)


def run(config_path: Path, *, resume_incomplete: bool = False) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {name: False for name in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb")}
    )
    config, data_root, receipt_path, dataset_yaml, checkpoint = locked_inputs(config_path)
    if ultralytics_version != str(config["model_family"]["package_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    training = config["training"]
    output_project = resolve(data_root, config["output"]["project"])
    run_name = str(config["output"]["run_name"])
    run_directory = output_project / run_name
    results_csv = run_directory / "results.csv"
    last = run_directory / "weights/last.pt"
    requested_epochs = int(training["epochs"])
    resume_context: dict[str, Any] | None = None
    if run_directory.exists() and not resume_incomplete:
        raise FileExistsError(run_directory)
    if resume_incomplete:
        observed_epochs = completed_epochs(results_csv)
        if not run_directory.is_dir() or not last.is_file():
            raise FileNotFoundError("Incomplete run has no resumable last.pt")
        if not 0 < observed_epochs < requested_epochs:
            raise RuntimeError(
                f"Resume requires 1..{requested_epochs - 1} completed epochs, found {observed_epochs}"
            )
        resume_context = {
            "reason": "external GPU-memory contention interrupted epoch five",
            "completed_epochs_before_resume": observed_epochs,
            "resume_checkpoint": str(last),
            "resume_checkpoint_sha256": sha256(last),
            "optimizer_state_source": "same run last.pt",
            "completed_epoch_repeated": False,
        }
        incident_path = run_directory / "resume_incident.json"
        incident_payload = json.dumps(resume_context, indent=2, sort_keys=True) + "\n"
        if incident_path.exists():
            if incident_path.read_text(encoding="utf-8") != incident_payload:
                raise ValueError("Existing resume incident provenance changed")
        else:
            incident_path.write_text(incident_payload, encoding="utf-8")
        model = YOLO(str(last))
    else:
        model = YOLO(str(checkpoint))
    if model.task != "segment":
        raise ValueError("Initial checkpoint is not a segmentation model")
    started = time.monotonic()
    if resume_incomplete:
        results = model.train(resume=True, device=int(training["device"]), verbose=True)
    else:
        results = model.train(
            data=str(dataset_yaml),
            project=str(output_project),
            name=run_name,
            exist_ok=False,
            epochs=requested_epochs,
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
    if not last.is_file() or not results_csv.is_file():
        raise RuntimeError("Training artifacts are incomplete")
    final_completed_epochs = completed_epochs(results_csv)
    if final_completed_epochs != requested_epochs:
        raise RuntimeError("Fixed epoch exposure was violated")
    dataset_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "matched_robot_native_training_complete_test_not_touched",
        "config": str(config_path.expanduser().resolve()),
        "config_sha256": sha256(config_path.expanduser().resolve()),
        "dataset_receipt": str(receipt_path),
        "dataset_receipt_sha256": sha256(receipt_path),
        "dataset_yaml": str(dataset_yaml),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "initial_checkpoint": str(checkpoint),
        "initial_checkpoint_sha256": sha256(checkpoint),
        "train_images_per_epoch": int(dataset_receipt["counts"]["train_images_per_epoch"]),
        "training": {
            "epochs_requested": requested_epochs,
            "epochs_completed": final_completed_epochs,
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
        "matched_reference": config["matched_reference"],
        "resume_context": resume_context,
        "claims": config["claims"],
    }
    output_receipt = run_directory / "run_receipt.json"
    output_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "artifacts": receipt["artifacts"]}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/pre_real_data_ceiling_robot_native_train_v1.yaml"),
    )
    parser.add_argument(
        "--resume-incomplete",
        action="store_true",
        help="Resume this exact run from its saved last.pt after an external interruption.",
    )
    arguments = parser.parse_args()
    run(arguments.config, resume_incomplete=arguments.resume_incomplete)


if __name__ == "__main__":
    main()
