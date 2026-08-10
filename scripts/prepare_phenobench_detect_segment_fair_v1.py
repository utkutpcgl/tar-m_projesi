#!/usr/bin/env python3
"""Build matched YOLO detection and instance-segmentation PhenoBench data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import yaml
from PIL import Image
from ultralytics.data.converter import merge_multi_segment


@dataclass(frozen=True)
class PlantObject:
    class_id: int
    instance_id: int
    area: int
    box_xyxy: tuple[int, int, int, int]
    polygon_xy: np.ndarray
    polygon_iou: float


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path, pattern: str = "*") -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob(pattern) if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def plot_group(stem: str) -> str:
    match = re.search(r"(P\d+)$", stem)
    if match is None:
        raise ValueError(f"Could not parse PhenoBench plot group from {stem!r}")
    return match.group(1)


def logical_split(
    source_split: str,
    group: str,
    calibration_groups: set[str],
    test_groups: set[str],
) -> str:
    if source_split == "train":
        return "train"
    if source_split != "val":
        raise ValueError(f"Unexpected labelled PhenoBench split: {source_split}")
    if group in calibration_groups:
        return "val"
    if group in test_groups:
        return "test"
    raise ValueError(f"Unassigned official-val plot group: {group}")


def _polygon_from_mask(mask: np.ndarray, epsilon_px: float) -> np.ndarray | None:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    simplified: list[np.ndarray] = []
    for contour in contours:
        candidate = cv2.approxPolyDP(contour, epsilon_px, closed=True).reshape(-1, 2)
        if len(candidate) >= 3 and abs(cv2.contourArea(candidate.astype(np.float32))) > 0:
            simplified.append(candidate.astype(np.float64))
    if not simplified:
        return None
    simplified.sort(
        key=lambda item: abs(cv2.contourArea(item.astype(np.float32))),
        reverse=True,
    )
    if len(simplified) == 1:
        return simplified[0]
    merged = merge_multi_segment([item.reshape(-1).tolist() for item in simplified])
    return np.concatenate(merged, axis=0).astype(np.float64)


def _polygon_iou(mask: np.ndarray, polygon: np.ndarray) -> float:
    reconstructed = np.zeros(mask.shape, dtype=np.uint8)
    points = np.rint(polygon).astype(np.int32)
    cv2.fillPoly(reconstructed, [points], 1)
    truth = mask.astype(bool)
    prediction = reconstructed.astype(bool)
    intersection = int(np.logical_and(truth, prediction).sum())
    union = int(np.logical_or(truth, prediction).sum())
    return intersection / union if union else 1.0


def objects_from_arrays(
    semantics: np.ndarray,
    instances: np.ndarray,
    *,
    minimum_area_px: int,
    polygon_epsilon_px: float,
    semantic_to_yolo: Mapping[int, int] = {1: 1, 2: 0},
) -> tuple[list[PlantObject], dict[str, int]]:
    if semantics.shape != instances.shape or semantics.ndim != 2:
        raise ValueError("Semantics and plant instances must be same-shape 2D arrays")
    if minimum_area_px <= 0 or polygon_epsilon_px < 0:
        raise ValueError("Invalid minimum area or polygon epsilon")
    output: list[PlantObject] = []
    audit = {
        "full_pixels_without_instance_id": 0,
        "instances_below_minimum_area": 0,
        "instances_without_valid_polygon": 0,
    }
    full = np.isin(semantics, tuple(semantic_to_yolo))
    audit["full_pixels_without_instance_id"] = int(np.logical_and(full, instances == 0).sum())
    seen_ids_by_semantic: dict[int, set[int]] = {}
    for semantic_id, class_id in semantic_to_yolo.items():
        ids = set(int(value) for value in np.unique(instances[semantics == semantic_id]) if value)
        seen_ids_by_semantic[semantic_id] = ids
        for instance_id in sorted(ids):
            mask = np.logical_and(instances == instance_id, semantics == semantic_id)
            area = int(mask.sum())
            if area < minimum_area_px:
                audit["instances_below_minimum_area"] += 1
                continue
            polygon = _polygon_from_mask(mask, polygon_epsilon_px)
            if polygon is None:
                audit["instances_without_valid_polygon"] += 1
                continue
            rows, columns = np.nonzero(mask)
            output.append(
                PlantObject(
                    class_id=int(class_id),
                    instance_id=instance_id,
                    area=area,
                    box_xyxy=(
                        int(columns.min()),
                        int(rows.min()),
                        int(columns.max()) + 1,
                        int(rows.max()) + 1,
                    ),
                    polygon_xy=polygon,
                    polygon_iou=_polygon_iou(mask, polygon),
                )
            )
    overlap = set.intersection(*seen_ids_by_semantic.values()) if seen_ids_by_semantic else set()
    if overlap:
        raise ValueError(f"Instance IDs mix full crop and weed semantics: {sorted(overlap)[:10]}")
    return output, audit


def detection_label_line(obj: PlantObject, width: int, height: int) -> str:
    x1, y1, x2, y2 = obj.box_xyxy
    values = (
        obj.class_id,
        (x1 + x2) / (2.0 * width),
        (y1 + y2) / (2.0 * height),
        (x2 - x1) / width,
        (y2 - y1) / height,
    )
    return f"{values[0]} " + " ".join(f"{value:.8f}" for value in values[1:])


def segmentation_label_line(obj: PlantObject, width: int, height: int) -> str:
    normalized = obj.polygon_xy / np.asarray([width, height], dtype=np.float64)
    if np.any(normalized < 0.0) or np.any(normalized > 1.0):
        raise ValueError("Polygon coordinate outside normalized image")
    return f"{obj.class_id} " + " ".join(
        f"{value:.8f}" for value in normalized.reshape(-1)
    )


def _percentiles(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p05": None, "p50": None, "p95": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "p05": float(np.percentile(array, 5)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
    }


def _write_dataset_yaml(path: Path, root: Path) -> None:
    payload = {
        "path": str(root),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {0: "weed", 1: "crop"},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _membership_rows(manifest: Path) -> list[dict[str, str]]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    source_manifest = _resolve(data_root, config["source_manifest"])
    source_root = _resolve(data_root, config["source_root"])
    output = _resolve(data_root, config["output"])
    if output.exists():
        raise FileExistsError(output)
    calibration_groups = set(str(value) for value in config["calibration_groups"])
    test_groups = set(str(value) for value in config["test_groups"])
    if calibration_groups & test_groups:
        raise ValueError("Calibration/test plot groups overlap")
    label_config = config["labels"]
    minimum_area = int(label_config["minimum_full_instance_area_px"])
    epsilon = float(label_config["polygon_approximation_epsilon_px"])
    rows = _membership_rows(source_manifest)
    if len(rows) != 2179:
        raise ValueError(f"Expected 2179 labelled PhenoBench rows, got {len(rows)}")

    output.mkdir(parents=True)
    membership_path = output / "membership.jsonl"
    membership_lines: list[str] = []
    counts: dict[str, dict[str, int]] = {
        split: {"images": 0, "weed_instances": 0, "crop_instances": 0}
        for split in ("train", "val", "test")
    }
    audit_totals = {
        "full_pixels_without_instance_id": 0,
        "instances_below_minimum_area": 0,
        "instances_without_valid_polygon": 0,
    }
    polygon_ious: list[float] = []
    polygon_points: list[float] = []
    source_paths_by_logical_split: dict[str, set[str]] = {
        split: set() for split in ("train", "val", "test")
    }
    groups_by_logical_split: dict[str, set[str]] = {
        split: set() for split in ("train", "val", "test")
    }
    for row in rows:
        image_path = _resolve(data_root, row["image_path"])
        source_split = str(row["split"])
        stem = image_path.stem
        group = plot_group(stem)
        split = logical_split(
            source_split, group, calibration_groups, test_groups
        )
        semantics_path = source_root / source_split / "semantics" / image_path.name
        instances_path = source_root / source_split / "plant_instances" / image_path.name
        if not image_path.is_file() or not semantics_path.is_file() or not instances_path.is_file():
            raise FileNotFoundError(f"Incomplete source triplet for {image_path}")
        with Image.open(image_path) as handle:
            width, height = handle.size
        semantics = np.asarray(Image.open(semantics_path), dtype=np.uint16)
        instances = np.asarray(Image.open(instances_path), dtype=np.uint16)
        if semantics.shape != (height, width) or instances.shape != (height, width):
            raise ValueError(f"Shape mismatch for {image_path}")
        objects, object_audit = objects_from_arrays(
            semantics,
            instances,
            minimum_area_px=minimum_area,
            polygon_epsilon_px=epsilon,
        )
        for key, value in object_audit.items():
            audit_totals[key] += value
        for obj in objects:
            class_name = "weed_instances" if obj.class_id == 0 else "crop_instances"
            counts[split][class_name] += 1
            polygon_ious.append(obj.polygon_iou)
            polygon_points.append(float(len(obj.polygon_xy)))
        counts[split]["images"] += 1
        source_paths_by_logical_split[split].add(str(image_path.resolve()))
        groups_by_logical_split[split].add(group)
        for arm in ("detect", "segment"):
            image_output = output / arm / "images" / split / image_path.name
            label_output = output / arm / "labels" / split / f"{stem}.txt"
            image_output.parent.mkdir(parents=True, exist_ok=True)
            label_output.parent.mkdir(parents=True, exist_ok=True)
            os.link(image_path, image_output)
            lines = (
                [detection_label_line(obj, width, height) for obj in objects]
                if arm == "detect"
                else [segmentation_label_line(obj, width, height) for obj in objects]
            )
            label_output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        membership_lines.append(
            json.dumps(
                {
                    "sample_id": row["sample_id"],
                    "logical_split": split,
                    "source_split": source_split,
                    "plot_group": group,
                    "capture_date": row["capture_date"],
                    "image_path": str(image_path),
                    "semantics_path": str(semantics_path),
                    "plant_instances_path": str(instances_path),
                    "eligible_instances": len(objects),
                    "eligible_weed_instances": sum(obj.class_id == 0 for obj in objects),
                    "eligible_crop_instances": sum(obj.class_id == 1 for obj in objects),
                },
                sort_keys=True,
            )
        )
    membership_path.write_text("\n".join(membership_lines) + "\n", encoding="utf-8")
    detect_yaml = output / "phenobench_detect_fair_v1.yaml"
    segment_yaml = output / "phenobench_segment_fair_v1.yaml"
    _write_dataset_yaml(detect_yaml, output / "detect")
    _write_dataset_yaml(segment_yaml, output / "segment")

    split_path_overlaps: dict[str, int] = {}
    split_names = ("train", "val", "test")
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            split_path_overlaps[f"{left}_vs_{right}"] = len(
                source_paths_by_logical_split[left] & source_paths_by_logical_split[right]
            )
    if any(split_path_overlaps.values()):
        raise ValueError(f"Source image leakage across logical splits: {split_path_overlaps}")
    if groups_by_logical_split["val"] & groups_by_logical_split["test"]:
        raise ValueError("Official-val plot group leakage between calibration/test")

    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "research_fair_ab_dataset_complete_not_deployment_evidence",
        "provenance": {
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "source_manifest": str(source_manifest),
            "source_manifest_sha256": sha256(source_manifest),
            "source_readme": str(source_root / "README.MD"),
            "source_readme_sha256": sha256(source_root / "README.MD"),
            "membership": str(membership_path),
            "membership_sha256": sha256(membership_path),
            "detect_labels_tree_sha256": tree_sha256(output / "detect/labels"),
            "segment_labels_tree_sha256": tree_sha256(output / "segment/labels"),
        },
        "split_contract": {
            "official_train_role": "train",
            "official_val_calibration_groups": sorted(calibration_groups),
            "official_val_test_groups": sorted(test_groups),
            "groups_by_logical_split": {
                key: sorted(value) for key, value in groups_by_logical_split.items()
            },
            "source_path_overlap": split_path_overlaps,
        },
        "counts": counts,
        "label_contract": {
            "minimum_full_instance_area_px": minimum_area,
            "polygon_approximation_epsilon_px": epsilon,
            "yolo_classes": {"0": "weed", "1": "crop"},
            "full_semantics": {"1": "crop", "2": "weed"},
            "ignored_semantics": {"3": "partial_crop", "4": "partial_weed"},
        },
        "quality": {
            **audit_totals,
            "polygon_reconstruction_iou": _percentiles(polygon_ious),
            "polygon_points": _percentiles(polygon_points),
            "detect_segment_image_membership_equal": True,
            "detect_segment_eligible_instance_membership_equal": True,
            "hardlinked_images": sum(item["images"] for item in counts.values()) * 2,
        },
        "dataset_yamls": {
            "detect": str(detect_yaml),
            "detect_sha256": sha256(detect_yaml),
            "segment": str(segment_yaml),
            "segment_sha256": sha256(segment_yaml),
        },
        "claims": list(config["claims"]),
        "limitations": [
            "The official test split has no public labels and is not used.",
            "Train and held-out spatial regions share the three capture dates; this isolates task/model behavior more than temporal deployment shift.",
            "Partial plants are ignored because publisher visibility is below 50 percent.",
            "YOLO polygons cannot encode holes exactly; reconstruction IoU is audited.",
            "PhenoBench is UAV sugar-beet imagery, not the final robot-camera distribution.",
        ],
    }
    receipt_path = output / "dataset_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_detect_segment_fair_v1.yaml"),
    )
    arguments = parser.parse_args()
    receipt = run(arguments.config)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
