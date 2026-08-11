#!/usr/bin/env python3
"""Build equal-exposure real-replay and real-plus-synthetic YOLO datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any, Sequence

import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def deterministic_replay(paths: Sequence[Path], count: int, seed: int) -> list[Path]:
    ordered = sorted(Path(path) for path in paths)
    if count <= 0 or count > len(ordered):
        raise ValueError("Replay count must be in [1, number of unique paths]")
    if len(set(ordered)) != len(ordered):
        raise ValueError("Replay source contains duplicate paths")
    return sorted(random.Random(seed).sample(ordered, count))


def label_for(image: Path) -> Path:
    parts = list(image.parts)
    try:
        index = len(parts) - 1 - parts[::-1].index("images")
    except ValueError as error:
        raise ValueError(f"Image path has no images component: {image}") from error
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def hardlink_pair(image: Path, image_output: Path) -> tuple[Path, Path]:
    label = label_for(image)
    if not image.is_file() or not label.is_file():
        raise FileNotFoundError(f"Incomplete image/label pair: {image}")
    label_output = label_for(image_output)
    image_output.parent.mkdir(parents=True, exist_ok=True)
    label_output.parent.mkdir(parents=True, exist_ok=True)
    os.link(image, image_output)
    os.link(label, label_output)
    return image_output, label_output


def _lock(path: Path, expected: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Locked input mismatch: {path}")


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(Path(__file__).resolve().parents[1], config["data_root"])
    real_cfg = config["real"]
    synthetic_cfg = config["synthetic"]
    real_root = resolve(data_root, real_cfg["dataset_root"])
    synthetic_root = resolve(data_root, synthetic_cfg["dataset_root"])
    real_receipt_path = resolve(data_root, real_cfg["dataset_receipt"])
    synthetic_receipt_path = resolve(data_root, synthetic_cfg["dataset_receipt"])
    real_yaml = resolve(data_root, real_cfg["dataset_yaml"])
    synthetic_yaml = resolve(data_root, synthetic_cfg["dataset_yaml"])
    for path, expected in (
        (real_receipt_path, str(real_cfg["dataset_receipt_sha256"])),
        (real_yaml, str(real_cfg["dataset_yaml_sha256"])),
        (synthetic_receipt_path, str(synthetic_cfg["dataset_receipt_sha256"])),
        (synthetic_yaml, str(synthetic_cfg["dataset_yaml_sha256"])),
    ):
        _lock(path, expected)
    real_receipt = json.loads(real_receipt_path.read_text(encoding="utf-8"))
    synthetic_receipt = json.loads(synthetic_receipt_path.read_text(encoding="utf-8"))
    if synthetic_receipt.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Synthetic packaging receipt did not pass")
    if synthetic_receipt.get("label_contract", {}).get("botanical_instance_ids_available") is not False:
        raise RuntimeError("Synthetic region-proxy limitation is not explicit")
    if float(synthetic_receipt["evaluation_policy"]["real_model_selection_score_weight"]) != 0.0:
        raise RuntimeError("Synthetic real-score weight must remain zero")

    real_images = sorted((real_root / "images/train").glob("*"))
    synthetic_images = sorted((synthetic_root / "images/train").glob("*"))
    real_images = [path for path in real_images if path.is_file()]
    synthetic_images = [path for path in synthetic_images if path.is_file()]
    if len(real_images) != int(real_cfg["expected_train_images"]):
        raise RuntimeError("Real train image count drift")
    if len(synthetic_images) != int(synthetic_cfg["expected_train_images"]):
        raise RuntimeError("Synthetic train image count drift")
    replay_count = int(config["replay_control"]["replay_images"])
    if replay_count != len(synthetic_images):
        raise RuntimeError("Control replay and synthetic supplement counts differ")
    replay = deterministic_replay(
        real_images, replay_count, int(config["replay_control"]["seed"])
    )

    output = resolve(data_root, config["output"])
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output if output.exists() else partial)
    partial.mkdir(parents=True, exist_ok=False)
    membership: list[dict[str, Any]] = []
    for arm in ("control_real_replay", "challenger_real_synthetic"):
        for image in real_images:
            destination = partial / arm / "images/train" / f"real_{image.name}"
            hardlink_pair(image, destination)
            membership.append(
                {"arm": arm, "kind": "real_unique", "source": str(image), "output": str(destination)}
            )
    for index, image in enumerate(replay):
        destination = (
            partial
            / "control_real_replay/images/train"
            / f"replay_{index:04d}_{image.name}"
        )
        hardlink_pair(image, destination)
        membership.append(
            {"arm": "control_real_replay", "kind": "real_replay", "source": str(image), "output": str(destination)}
        )
    for image in synthetic_images:
        destination = (
            partial
            / "challenger_real_synthetic/images/train"
            / f"synthetic_{image.name}"
        )
        hardlink_pair(image, destination)
        membership.append(
            {"arm": "challenger_real_synthetic", "kind": "synthetic_train", "source": str(image), "output": str(destination)}
        )

    val_images = (real_root / "images/val").resolve()
    test_images = (real_root / "images/test").resolve()
    yaml_paths: dict[str, Path] = {}
    for arm in ("control_real_replay", "challenger_real_synthetic"):
        arm_root = partial / arm
        yaml_path = partial / f"{arm}.yaml"
        yaml_path.write_text(
            yaml.safe_dump(
                {
                    "path": str(output / arm),
                    "train": "images/train",
                    "val": str(val_images),
                    "test": str(test_images),
                    "names": {0: "weed", 1: "crop"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        yaml_paths[arm] = yaml_path

    membership_path = partial / "membership.jsonl"
    membership_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in membership) + "\n",
        encoding="utf-8",
    )
    arm_counts = {
        arm: len(list((partial / arm / "images/train").glob("*")))
        for arm in ("control_real_replay", "challenger_real_synthetic")
    }
    real_source_sets = {
        arm: {
            row["source"]
            for row in membership
            if row["arm"] == arm and row["kind"] == "real_unique"
        }
        for arm in arm_counts
    }
    gates = {
        "equal_train_samples_per_epoch": len(set(arm_counts.values())) == 1,
        "all_unique_real_train_frames_in_both_arms": (
            real_source_sets["control_real_replay"]
            == real_source_sets["challenger_real_synthetic"]
            == {str(path) for path in real_images}
        ),
        "control_replay_matches_synthetic_count": replay_count == len(synthetic_images),
        "synthetic_train_only": all("/images/train/" in str(path) for path in synthetic_images),
        "real_val_test_identical_between_arms": True,
        "synthetic_val_test_selection_weight_zero": True,
        "hardlinked_pairs_complete": all(
            len(list((partial / arm / "images/train").glob("*")))
            == len(list((partial / arm / "labels/train").glob("*.txt")))
            for arm in arm_counts
        ),
    }
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "equal_exposure_ab_datasets_ready",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "inputs": {
            "real_receipt": str(real_receipt_path),
            "real_receipt_sha256": sha256(real_receipt_path),
            "synthetic_receipt": str(synthetic_receipt_path),
            "synthetic_receipt_sha256": sha256(synthetic_receipt_path),
            "real_unique_train_images": len(real_images),
            "synthetic_train_images": len(synthetic_images),
            "control_real_replay_images": len(replay),
            "real_val_images": int(real_receipt["counts"]["val"]["images"]),
            "real_test_images": int(real_receipt["counts"]["test"]["images"]),
        },
        "arm_train_counts": arm_counts,
        "replay_selection": {
            "seed": int(config["replay_control"]["seed"]),
            "paths": [str(path) for path in replay],
        },
        "dataset_yamls": {
            arm: {
                "path": str(output / yaml_path.relative_to(partial)),
                "sha256": sha256(yaml_path),
            }
            for arm, yaml_path in yaml_paths.items()
        },
        "membership": str(output / "membership.jsonl"),
        "membership_sha256": sha256(membership_path),
        "train_label_trees": {
            arm: tree_sha256(partial / arm / "labels/train") for arm in arm_counts
        },
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "claims": config["claims"],
        "limitations": [
            "The control repeats 80 deterministic real frames; the challenger replaces only those extra exposures with 80 synthetic region proxies.",
            "This is one-seed directional evidence; a positive result still requires real deploy-distribution validation.",
        ],
    }
    receipt_path = partial / "dataset_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not receipt["all_quality_gates_passed"]:
        failed = [name for name, passed in gates.items() if not passed]
        raise RuntimeError(f"A/B dataset gates failed: {failed}; see {receipt_path}")
    partial.replace(output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_cropcraft_deploy_ab_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
