#!/usr/bin/env python3
"""Audit the real LED labels and compare a generated EBIS detection set.

The script is intentionally dependency-free. It reads PNG headers and YOLO
text files with the standard library so the same gate can run locally or on
the 3090 without modifying the training environment.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


CLASS_NAMES = {0: "tag", 1: "concrete", 2: "apriltag", 3: "person"}
SHAPE_BY_TASK = {"task_9": "cylinder", "task_12": "cylinder", "task_11": "cube", "task_13": "cube"}
REAL_TARGETS = {
    ("camera_angled", "cylinder"): [0.502, 0.594, 0.255, 0.809],
    ("camera_angled", "cube"): [0.500, 0.574, 0.496, 0.852],
    ("camera_door", "cylinder"): [0.511, 0.573, 0.267, 0.854],
    ("camera_door", "cube"): [0.511, 0.575, 0.487, 0.849],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-root", required=True, type=Path)
    parser.add_argument("--synthetic-root", type=Path)
    parser.add_argument("--json", required=True, type=Path, dest="json_path")
    parser.add_argument("--markdown", type=Path)
    return parser.parse_args()


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "p01": quantile(values, 0.01),
        "p05": quantile(values, 0.05),
        "median": quantile(values, 0.5),
        "p95": quantile(values, 0.95),
        "maximum": max(values) if values else None,
    }


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Unsupported or invalid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def label_for_image(image: Path) -> Path:
    parts = list(image.parts)
    index = parts.index("images")
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def parse_camera(name: str) -> str:
    if "cam-10" in name:
        return "camera_angled"
    if "cam-11" in name:
        return "camera_door"
    return "unknown_legacy_camera"


def parse_task(name: str) -> str:
    match = re.search(r"(task_\d+)", name)
    return match.group(1) if match else "legacy"


def parse_batch(name: str) -> str:
    match = re.search(r"batch-(\d+)", name)
    return f"batch-{match.group(1)}" if match else "legacy"


def split_for_image(image: Path) -> str:
    parts = list(image.parts)
    index = parts.index("images")
    return parts[index + 1] if index + 1 < len(parts) else "unknown"


def read_yolo(path: Path) -> list[tuple[int, list[float]]]:
    boxes = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid YOLO row {path}:{line_number}")
        class_id = int(fields[0])
        values = [float(value) for value in fields[1:]]
        if any(not math.isfinite(value) for value in values):
            raise ValueError(f"Non-finite YOLO row {path}:{line_number}")
        if not all(0.0 <= value <= 1.0 for value in values) or values[2] <= 0 or values[3] <= 0:
            raise ValueError(f"Out-of-range YOLO row {path}:{line_number}")
        boxes.append((class_id, values))
    return boxes


def audit_real(root: Path) -> dict:
    image_paths = sorted(path for path in root.rglob("*.png") if "images" in path.parts)
    if not image_paths:
        raise ValueError(f"No real PNG images found under {root}")
    class_counts = Counter()
    class_image_counts = Counter()
    camera_counts = Counter()
    split_counts = Counter()
    per_image_tag_counts = []
    sizes: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    concrete_groups: dict[tuple[str, str], list[list[float]]] = defaultdict(list)
    split_groups: dict[str, set[str]] = defaultdict(set)
    empty_labels = 0
    resolutions = Counter()

    for image in image_paths:
        label = label_for_image(image)
        if not label.is_file():
            raise ValueError(f"Missing label for {image}: {label}")
        width, height = png_size(image)
        resolutions[f"{width}x{height}"] += 1
        boxes = read_yolo(label)
        if not boxes:
            empty_labels += 1
        for class_id in {class_id for class_id, _box in boxes}:
            class_image_counts[class_id] += 1
        camera = parse_camera(image.name)
        task = parse_task(image.name)
        batch = parse_batch(image.name)
        split = split_for_image(image)
        camera_counts[camera] += 1
        split_counts[split] += 1
        split_groups[split].add(f"{task}:{camera}:{batch}")
        tag_count = 0
        for class_id, (cx, cy, bw, bh) in boxes:
            class_counts[class_id] += 1
            if class_id == 0:
                tag_count += 1
            pixel_w, pixel_h = bw * width, bh * height
            sizes[class_id]["short_px"].append(min(pixel_w, pixel_h))
            sizes[class_id]["long_px"].append(max(pixel_w, pixel_h))
            sizes[class_id]["area_fraction"].append(bw * bh)
            touches = (
                cx - bw / 2 <= 1e-6
                or cy - bh / 2 <= 1e-6
                or cx + bw / 2 >= 1 - 1e-6
                or cy + bh / 2 >= 1 - 1e-6
            )
            sizes[class_id]["touches_edge"].append(float(touches))
            shape = SHAPE_BY_TASK.get(task)
            if class_id == 1 and shape and camera != "unknown_legacy_camera":
                concrete_groups[(camera, shape)].append([cx, cy, bw, bh])
        per_image_tag_counts.append(tag_count)

    class_stats = {}
    for class_id, metrics in sorted(sizes.items()):
        class_stats[CLASS_NAMES.get(class_id, str(class_id))] = {
            "instances": class_counts[class_id],
            "images": class_image_counts[class_id],
            "image_fraction": class_image_counts[class_id] / len(image_paths),
            "short_side_px": summary(metrics["short_px"]),
            "long_side_px": summary(metrics["long_px"]),
            "bbox_area_fraction": summary(metrics["area_fraction"]),
            "touches_image_edge_fraction": sum(metrics["touches_edge"]) / len(metrics["touches_edge"]),
        }

    concrete_medians = {}
    for key, boxes in sorted(concrete_groups.items()):
        concrete_medians[f"{key[0]}:{key[1]}"] = {
            "count": len(boxes),
            "median_yolo": [median([box[index] for box in boxes]) for index in range(4)],
        }
    train_val_overlap = sorted(split_groups.get("train", set()) & split_groups.get("val", set()))
    return {
        "root": str(root.resolve()),
        "image_count": len(image_paths),
        "resolutions": dict(sorted(resolutions.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "camera_counts": dict(sorted(camera_counts.items())),
        "empty_label_files": empty_labels,
        "class_stats": class_stats,
        "rfid_instances_per_image": summary([float(value) for value in per_image_tag_counts]),
        "concrete_bbox_medians": concrete_medians,
        "train_val_capture_group_overlap": train_val_overlap,
        "leakage_warning": bool(train_val_overlap),
    }


def audit_synthetic(root: Path) -> dict:
    metadata_paths = sorted((root / "metadata").glob("ebis_*.json"))
    if not metadata_paths:
        raise ValueError(f"No synthetic metadata found under {root}")
    partitions = Counter()
    cameras = Counter()
    shapes = Counter()
    statuses = Counter()
    instance_counts = []
    grouped_boxes: dict[tuple[str, str], list[list[float]]] = defaultdict(list)
    for path in metadata_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        camera = data["camera"]
        shape = data["sample"]["shape"]
        partition = data.get("detection_annotations", {}).get("image_partition", "legacy")
        cameras[camera] += 1
        shapes[shape] += 1
        partitions[partition] += 1
        records = data.get("rfid_tags") or []
        instance_counts.append(float(len(records)))
        for record in records:
            statuses[record.get("detection_policy", {}).get("label_status", "unknown")] += 1
        concrete = data.get("visible_annotations", {}).get("concrete_sample")
        if concrete:
            grouped_boxes[(camera, shape)].append(list(map(float, concrete["yolo"])))

    bbox_comparison = {}
    for key, real_target in REAL_TARGETS.items():
        boxes = grouped_boxes.get(key, [])
        synthetic_median = [median([box[index] for box in boxes]) for index in range(4)] if boxes else None
        bbox_comparison[f"{key[0]}:{key[1]}"] = {
            "count": len(boxes),
            "real_target": real_target,
            "synthetic_median": synthetic_median,
            "absolute_delta": (
                [abs(a - b) for a, b in zip(synthetic_median, real_target)]
                if synthetic_median
                else None
            ),
            "within_visual_gate_abs_0_03": (
                all(abs(a - b) <= 0.03 for a, b in zip(synthetic_median, real_target))
                if synthetic_median
                else False
            ),
        }
    return {
        "root": str(root.resolve()),
        "image_count": len(metadata_paths),
        "camera_counts": dict(sorted(cameras.items())),
        "sample_shape_counts": dict(sorted(shapes.items())),
        "annotation_partition_counts": dict(sorted(partitions.items())),
        "rfid_label_status_counts": dict(sorted(statuses.items())),
        "rfid_instances_per_image": summary(instance_counts),
        "concrete_bbox_comparison": bbox_comparison,
    }


def markdown_report(report: dict) -> str:
    real = report["real"]
    lines = [
        "# EBIS detection-domain audit",
        "",
        f"- Real images: {real['image_count']}",
        f"- Real split leakage warning: {'YES' if real['leakage_warning'] else 'no'}",
        f"- Overlapping capture groups: {len(real['train_val_capture_group_overlap'])}",
        "",
        "## Real class counts",
        "",
        "| Class | Instances | Images | Image fraction | Median short px | Median long px | Edge-touch |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, stats in real["class_stats"].items():
        lines.append(
            f"| {name} | {stats['instances']} | {stats['images']} | {stats['image_fraction']:.3f} | "
            f"{stats['short_side_px']['median']:.2f} | "
            f"{stats['long_side_px']['median']:.2f} | {stats['touches_image_edge_fraction']:.3f} |"
        )
    synthetic = report.get("synthetic")
    if synthetic:
        lines.extend(
            [
                "",
                "## Synthetic concrete framing gate",
                "",
                "| Camera/shape | N | Synthetic median | Real target | max |delta| | Gate |",
                "| --- | ---: | --- | --- | ---: | --- |",
            ]
        )
        for key, item in synthetic["concrete_bbox_comparison"].items():
            synth = item["synthetic_median"]
            delta = item["absolute_delta"]
            lines.append(
                f"| {key} | {item['count']} | {synth or '-'} | {item['real_target']} | "
                f"{max(delta) if delta else '-'} | {'PASS' if item['within_visual_gate_abs_0_03'] else 'TUNE'} |"
            )
        lines.extend(
            [
                "",
                f"Partitions: `{synthetic['annotation_partition_counts']}`",
                "",
                "The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    report = {"schema_version": 1, "real": audit_real(args.real_root)}
    if args.synthetic_root:
        report["synthetic"] = audit_synthetic(args.synthetic_root)
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report), encoding="utf-8")
    print(f"EBIS_DOMAIN_AUDIT_OK {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
