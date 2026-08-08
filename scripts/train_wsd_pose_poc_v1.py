#!/usr/bin/env python3
"""Train and test a date-disjoint weed detection + stem-keypoint PoC."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
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


def _locked_input(config: dict[str, Any], data_root: Path) -> tuple[Path, Path, Path]:
    dataset_yaml = _resolve(data_root, config["dataset_yaml"])
    receipt = _resolve(data_root, config["dataset_receipt"])
    pretrained = _resolve(data_root, config["model"]["pretrained_checkpoint"])
    if sha256(receipt) != str(config["dataset_receipt_sha256"]):
        raise ValueError("WSD dataset receipt SHA-256 mismatch")
    if sha256(pretrained) != str(config["model"]["pretrained_checkpoint_sha256"]):
        raise ValueError("Pretrained checkpoint SHA-256 mismatch")
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    gates = receipt_payload["quality_gates"]
    if gates.get("research_pilot_approved") is not True:
        raise ValueError("WSD dataset is not approved for the research pilot")
    if gates.get("production_release_approved") is not False:
        raise ValueError("WSD receipt must explicitly remain non-production")
    return dataset_yaml, receipt, pretrained


def run(
    config_path: Path,
    *,
    epochs_override: int | None = None,
    fraction: float = 1.0,
    name_suffix: str = "",
) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    # Keep research runs local and reproducible.  Ultralytics enables several
    # third-party integrations by default when their packages are installed.
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
    enabled_integrations = [
        key for key in disabled_integrations if bool(settings.get(key))
    ]
    if enabled_integrations:
        raise RuntimeError(
            "Could not disable external integrations: "
            + ", ".join(enabled_integrations)
        )

    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    dataset_yaml, dataset_receipt, pretrained = _locked_input(config, data_root)
    expected_version = str(config["model"]["package_version"])
    if ultralytics_version != expected_version:
        raise ValueError(
            f"Expected ultralytics {expected_version}, got {ultralytics_version}"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the WSD pose pilot")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0,1]")

    training = dict(config["training"])
    output = config["output"]
    run_name = str(output["name"]) + name_suffix
    output_project = _resolve(data_root, output["project"])
    run_directory = output_project / run_name
    if run_directory.exists():
        raise FileExistsError(run_directory)
    epochs = int(epochs_override or training["epochs"])
    model = YOLO(str(pretrained))
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
        lr0=float(training.get("lr0", 0.01)),
        lrf=float(training.get("lrf", 0.01)),
        momentum=float(training.get("momentum", 0.937)),
        weight_decay=float(training.get("weight_decay", 0.0005)),
        cos_lr=bool(training["cos_lr"]),
        cache=bool(training["cache"]),
        degrees=float(training["degrees"]),
        translate=float(training["translate"]),
        scale=float(training["scale"]),
        fliplr=float(training["fliplr"]),
        flipud=float(training["flipud"]),
        mosaic=float(training["mosaic"]),
        close_mosaic=int(training["close_mosaic"]),
        fraction=float(fraction),
        pretrained=True,
        val=True,
        plots=True,
        verbose=True,
    )
    best = run_directory / "weights/best.pt"
    last = run_directory / "weights/last.pt"
    if not best.is_file() or not last.is_file():
        raise RuntimeError("Ultralytics training did not create best.pt and last.pt")

    evaluation = config["evaluation"]
    test_model = YOLO(str(best))
    test_metrics = test_model.val(
        data=str(dataset_yaml),
        split=str(evaluation["split"]),
        conf=float(evaluation["confidence"]),
        iou=float(evaluation["iou"]),
        imgsz=int(evaluation["image_size"]),
        batch=int(evaluation["batch"]),
        workers=int(training["workers"]),
        device=int(training["device"]),
        project=str(run_directory),
        name="test_builtin_metrics",
        plots=True,
        verbose=True,
    )
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "research_poc_complete_not_field_or_laser_validated",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_yaml": str(dataset_yaml),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "dataset_receipt": str(dataset_receipt),
        "dataset_receipt_sha256": sha256(dataset_receipt),
        "pretrained_checkpoint": str(pretrained),
        "pretrained_checkpoint_sha256": sha256(pretrained),
        "ultralytics_version": ultralytics_version,
        "ultralytics_license_scope": config["model"]["license_scope"],
        "external_integrations": {
            key: bool(settings.get(key)) for key in disabled_integrations
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(int(training["device"])),
        },
        "training": {
            "epochs_requested": epochs,
            "fraction": fraction,
            "results": _plain(getattr(results, "results_dict", {})),
        },
        "test_builtin_metrics": _plain(
            getattr(test_metrics, "results_dict", {})
        ),
        "artifacts": {
            "run_directory": str(run_directory),
            "best_checkpoint": str(best),
            "best_checkpoint_sha256": sha256(best),
            "last_checkpoint": str(last),
            "last_checkpoint_sha256": sha256(last),
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
    parser.add_argument(
        "--config", default="configs/benchmark/wsd_pose_poc_v1.yaml"
    )
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--name-suffix", default="")
    arguments = parser.parse_args()
    receipt = run(
        Path(arguments.config),
        epochs_override=arguments.epochs,
        fraction=arguments.fraction,
        name_suffix=arguments.name_suffix,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
