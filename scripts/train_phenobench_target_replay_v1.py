#!/usr/bin/env python3
"""Train a simple target-data plus source-replay segmentation challenger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import yaml

from scripts.train_phenobench_detect_segment_fair_v1 import run as train_arm
from scripts.train_phenobench_detect_segment_fair_v1 import sha256


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def interleave_equal(left: Sequence[str], right: Sequence[str]) -> list[str]:
    if len(left) != len(right):
        raise ValueError("Replay inputs must have equal length")
    if len(set(left)) != len(left) or len(set(right)) != len(right):
        raise ValueError("Replay inputs contain duplicates")
    if set(left) & set(right):
        raise ValueError("Source and target replay overlap")
    return [item for pair in zip(left, right, strict=True) for item in pair]


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    locked = [
        (
            _resolve(data_root, config["dataset_receipt"]),
            config["dataset_receipt_sha256"],
        ),
        (
            _resolve(data_root, config["source_segment_yaml"]),
            config["source_segment_yaml_sha256"],
        ),
        (
            _resolve(data_root, config["initial_checkpoint"]),
            config["initial_checkpoint_sha256"],
        ),
    ]
    input_paths: dict[str, Path] = {}
    for name, item in config["input_lists"].items():
        path = _resolve(data_root, item["path"])
        locked.append((path, item["sha256"]))
        input_paths[str(name)] = path
    for path, expected in locked:
        if not path.is_file() or sha256(path) != str(expected):
            raise ValueError(f"Locked input mismatch: {path}")

    source = input_paths["source126"].read_text(encoding="utf-8").splitlines()
    target = input_paths["target126"].read_text(encoding="utf-8").splitlines()
    combined = interleave_equal(source, target)
    output_project = _resolve(data_root, config["output"]["project"])
    if output_project.exists():
        raise FileExistsError(output_project)
    protocol = output_project / "protocol"
    protocol.mkdir(parents=True)
    combined_list = protocol / "replay_images.txt"
    combined_list.write_text(
        "".join(f"{path}\n" for path in combined), encoding="utf-8"
    )
    source_yaml = yaml.safe_load(
        _resolve(data_root, config["source_segment_yaml"]).read_text(encoding="utf-8")
    )
    dataset_yaml = protocol / "replay_dataset.yaml"
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(source_yaml["path"]),
                "train": str(combined_list),
                "val": str(combined_list),
                "names": {0: "weed", 1: "crop"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    runtime = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "data_root": str(data_root),
        "dataset_receipt": config["dataset_receipt"],
        "dataset_receipt_sha256": config["dataset_receipt_sha256"],
        "arms": {
            "segment": {
                "task": "segment",
                "dataset_yaml": str(dataset_yaml),
                "dataset_yaml_sha256": sha256(dataset_yaml),
                "pretrained_checkpoint": str(
                    _resolve(data_root, config["initial_checkpoint"])
                ),
                "pretrained_checkpoint_sha256": config[
                    "initial_checkpoint_sha256"
                ],
                "run_name": config["output"]["run_name"],
            }
        },
        "model_family": config["model_family"],
        "training": config["training"],
        "selection": {
            "checkpoint": "last.pt",
            "reason": "fixed final epoch; common external calibration follows",
            "validation_role": "not used during training",
            "test_role": "not used during training",
        },
        "output": {"project": str(output_project)},
        "claims": config["claims"],
    }
    runtime_config = protocol / "runtime_training_config.yaml"
    runtime_config.write_text(
        yaml.safe_dump(runtime, sort_keys=False), encoding="utf-8"
    )
    training_receipt = train_arm(runtime_config, "segment")
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "target_source_replay_training_complete_test_not_touched",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "inputs": {
            "source_images": len(source),
            "target_images": len(target),
            "combined_images": len(combined),
            "combined_list": str(combined_list),
            "combined_list_sha256": sha256(combined_list),
        },
        "training": training_receipt,
        "claims": config["claims"],
    }
    receipt_path = output_project / "target_replay_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_target_replay_finetune_v1.yaml"),
    )
    arguments = parser.parse_args()
    receipt = run(arguments.config)
    print(json.dumps({
        "status": receipt["status"],
        "artifacts": receipt["training"]["artifacts"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
