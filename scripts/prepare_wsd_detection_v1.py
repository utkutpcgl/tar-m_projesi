#!/usr/bin/env python3
"""Derive a detection-only WSD dataset without duplicating the 5 GB images."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _detection_line(line: str, path: Path, line_number: int) -> str:
    tokens = line.split()
    if len(tokens) != 8:
        raise ValueError(f"{path}:{line_number}: expected 8 pose fields")
    values = [float(token) for token in tokens]
    class_id = int(values[0])
    if values[0] != class_id or class_id not in {0, 1, 2}:
        raise ValueError(f"{path}:{line_number}: invalid class")
    if not all(0.0 <= value <= 1.0 for value in values[1:5]):
        raise ValueError(f"{path}:{line_number}: box outside normalized range")
    if values[3] <= 0.0 or values[4] <= 0.0:
        raise ValueError(f"{path}:{line_number}: non-positive box extent")
    return " ".join(tokens[:5])


def prepare(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    source_root = _resolve(data_root, config["source_pose_root"])
    source_receipt = _resolve(data_root, config["source_receipt"])
    output_root = _resolve(data_root, config["outputs"]["root"])
    output_receipt = _resolve(data_root, config["outputs"]["receipt"])
    output_yaml = _resolve(data_root, config["outputs"]["ultralytics_yaml"])

    if sha256(source_receipt) != str(config["source_receipt_sha256"]):
        raise ValueError("Source WSD receipt SHA-256 mismatch")
    source_payload = json.loads(source_receipt.read_text(encoding="utf-8"))
    gates = source_payload["quality_gates"]
    if gates.get("research_pilot_approved") is not True:
        raise ValueError("Source WSD dataset is not approved for research")
    if output_root.exists() or output_receipt.exists():
        raise FileExistsError(output_root if output_root.exists() else output_receipt)

    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_receipt.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {}
    label_inventory: list[dict[str, Any]] = []
    link_modes: Counter[str] = Counter()
    try:
        for split in ("train", "val", "test"):
            source_images = source_root / "images" / split
            source_labels = source_root / "labels" / split
            image_output = output_root / "images" / split
            label_output = output_root / "labels" / split
            image_output.mkdir(parents=True)
            label_output.mkdir(parents=True)
            images = sorted(
                path
                for path in source_images.iterdir()
                if path.suffix.lower() in {".bmp", ".jpg", ".jpeg", ".png"}
            )
            labels = sorted(source_labels.glob("*.txt"))
            if {path.stem for path in images} != {path.stem for path in labels}:
                raise ValueError(f"{split}: source image/label stems differ")
            split_counts: Counter[str] = Counter(images=len(images))
            for image in images:
                destination = image_output / image.name
                try:
                    os.link(image, destination)
                    link_modes["hardlink"] += 1
                except OSError:
                    destination.symlink_to(image)
                    link_modes["symlink"] += 1
            for label in labels:
                converted: list[str] = []
                for line_number, line in enumerate(
                    label.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if not line.strip():
                        continue
                    converted_line = _detection_line(line, label, line_number)
                    converted.append(converted_line)
                    class_id = int(converted_line.split()[0])
                    split_counts["instances"] += 1
                    split_counts[f"class_{class_id}_instances"] += 1
                destination = label_output / label.name
                destination.write_text("\n".join(converted) + "\n", encoding="utf-8")
                label_inventory.append(
                    {
                        "path": str(destination.relative_to(output_root)),
                        "sha256": sha256(destination),
                    }
                )
            counts[split] = dict(split_counts)

        dataset_payload = {
            "path": str(output_root),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {int(key): value for key, value in config["derivation"]["class_names"].items()},
        }
        output_yaml.write_text(
            yaml.safe_dump(dataset_payload, sort_keys=False), encoding="utf-8"
        )
        receipt = {
            "schema_version": 1,
            "dataset_id": config["dataset_id"],
            "status": "research_detection_derivative_prepared",
            "source": {
                "pose_root": str(source_root),
                "receipt": str(source_receipt),
                "receipt_sha256": sha256(source_receipt),
                "pose_label_tree_sha256": source_payload["derived"]["pose_label_tree_sha256"],
            },
            "derivation": {
                "box_fields": "verbatim first five fields from each pose row",
                "image_link_modes": dict(link_modes),
                "detection_label_tree_sha256": canonical_sha256(label_inventory),
                "split_statistics": counts,
            },
            "artifacts": {
                "root": str(output_root),
                "ultralytics_yaml": str(output_yaml),
                "ultralytics_yaml_sha256": sha256(output_yaml),
            },
            "provenance": {
                "config": str(config_path),
                "config_sha256": sha256(config_path),
                "preparer": str(Path(__file__).resolve()),
                "preparer_sha256": sha256(Path(__file__).resolve()),
            },
            "quality_gates": {
                "source_receipt_locked": True,
                "source_split_membership_preserved": True,
                "all_pose_rows_have_detection_rows": True,
                "images_are_zero_copy_links": link_modes["hardlink"] + link_modes["symlink"]
                == sum(item["images"] for item in counts.values()),
                "research_pilot_approved": True,
                "production_release_approved": False,
            },
            "limitations": list(config["release_policy"]["limitations"]),
        }
        output_receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt
    except Exception:
        if output_root.exists():
            shutil.rmtree(output_root)
        if output_receipt.exists():
            output_receipt.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/weed_stem_detection_detect_v1.yaml"),
    )
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
