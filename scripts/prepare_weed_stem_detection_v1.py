#!/usr/bin/env python3
"""Audit and prepare the published Weed Stem Detection labelled archive.

The source archive stores standard YOLO boxes and a separate point file in the
same row order.  Only weeds have a meaningful stem point; crop rows use (0, 0).
The prepared representation uses one YOLO-pose keypoint with visibility zero
when no stem annotation exists.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile

import yaml
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class SourceSample:
    stem: str
    image_member: str
    box_member: str
    point_member: str
    capture_date: str
    split: str


@dataclass(frozen=True)
class PoseRow:
    class_id: int
    x: float
    y: float
    width: float
    height: float
    point_x: float
    point_y: float
    visibility: int
    source_field_count: int


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and not path.parts[0].endswith(":")
    )


def _members_by_stem(
    names: Iterable[str], prefix: str, suffixes: tuple[str, ...]
) -> dict[str, str]:
    normalized_prefix = prefix.rstrip("/") + "/"
    result: dict[str, str] = {}
    for name in names:
        path = PurePosixPath(name)
        if not name.startswith(normalized_prefix) or path.suffix.lower() not in suffixes:
            continue
        if path.stem in result:
            raise ValueError(f"Duplicate stem under {prefix}: {path.stem}")
        result[path.stem] = name
    return result


def _capture_date(stem: str) -> str:
    if not stem.startswith("Image_") or len(stem) < 14:
        raise ValueError(f"Unexpected WSD image stem: {stem}")
    date = stem[6:14]
    if len(date) != 8 or not date.isdigit():
        raise ValueError(f"Unexpected WSD capture date: {stem}")
    return date


def _split_for_date(date: str, policy: dict[str, Any]) -> str:
    matches = [
        split
        for split in ("train", "val", "test")
        if date in {str(item) for item in policy[f"{split}_dates"]}
    ]
    if len(matches) != 1:
        raise ValueError(f"Capture date {date} maps to {matches}, expected one split")
    return matches[0]


def _float_tokens(line: str, expected: set[int], member: str, row: int) -> list[float]:
    tokens = line.split()
    if len(tokens) not in expected:
        raise ValueError(
            f"{member}:{row}: expected field count {sorted(expected)}, got {len(tokens)}"
        )
    try:
        values = [float(token) for token in tokens]
    except ValueError as error:
        raise ValueError(f"{member}:{row}: non-numeric annotation") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{member}:{row}: non-finite annotation")
    return values


def parse_pose_rows(
    archive: ZipFile,
    sample: SourceSample,
    config: dict[str, Any],
) -> tuple[list[PoseRow], dict[str, int]]:
    policy = config["normalization_policy"]
    classes = {int(key) for key in config["archive_layout"]["class_names"]}
    accepted_counts = {int(value) for value in policy["accepted_box_field_counts"]}
    box_lines = [
        line
        for line in archive.read(sample.box_member).decode("utf-8").splitlines()
        if line.strip()
    ]
    point_lines = [
        line
        for line in archive.read(sample.point_member).decode("utf-8").splitlines()
        if line.strip()
    ]
    if len(box_lines) != len(point_lines):
        raise ValueError(
            f"{sample.stem}: {len(box_lines)} boxes but {len(point_lines)} points"
        )
    missing = tuple(float(value) for value in policy["missing_point"])
    keypoint_class = int(policy["stem_keypoint_class"])
    visible_value = int(policy["visible_keypoint_value"])
    missing_value = int(policy["missing_keypoint_value"])
    rows: list[PoseRow] = []
    stats = Counter()
    for index, (box_line, point_line) in enumerate(
        zip(box_lines, point_lines, strict=True), start=1
    ):
        box = _float_tokens(
            box_line, accepted_counts, sample.box_member, index
        )
        point = _float_tokens(point_line, {2}, sample.point_member, index)
        class_id = int(box[0])
        if box[0] != class_id or class_id not in classes:
            raise ValueError(f"{sample.box_member}:{index}: invalid class {box[0]}")
        x, y, width, height = box[1:5]
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"{sample.box_member}:{index}: center outside [0,1]")
        if not (0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            raise ValueError(f"{sample.box_member}:{index}: invalid box extent")
        point_x, point_y = point
        if not (0.0 <= point_x <= 1.0 and 0.0 <= point_y <= 1.0):
            raise ValueError(f"{sample.point_member}:{index}: point outside [0,1]")
        has_point = not (
            math.isclose(point_x, missing[0], abs_tol=0.0)
            and math.isclose(point_y, missing[1], abs_tol=0.0)
        )
        if class_id != keypoint_class and has_point:
            raise ValueError(
                f"{sample.point_member}:{index}: crop class has a non-placeholder point"
            )
        if class_id == keypoint_class and has_point:
            if abs(point_x - x) > width / 2 + 1e-12 or abs(point_y - y) > height / 2 + 1e-12:
                raise ValueError(
                    f"{sample.point_member}:{index}: weed point is outside its box"
                )
            visibility = visible_value
            stats["visible_weed_points"] += 1
        else:
            visibility = missing_value
            point_x = 0.0
            point_y = 0.0
            if class_id == keypoint_class:
                stats["missing_weed_points"] += 1
            else:
                stats["crop_point_placeholders"] += 1
        stats[f"class_{class_id}_instances"] += 1
        stats["instances"] += 1
        if len(box) != 5:
            stats["box_rows_with_extra_fields"] += 1
        rows.append(
            PoseRow(
                class_id=class_id,
                x=x,
                y=y,
                width=width,
                height=height,
                point_x=point_x,
                point_y=point_y,
                visibility=visibility,
                source_field_count=len(box),
            )
        )
    return rows, dict(stats)


def _pose_line(row: PoseRow) -> str:
    values: tuple[int | float, ...] = (
        row.class_id,
        row.x,
        row.y,
        row.width,
        row.height,
        row.point_x,
        row.point_y,
        row.visibility,
    )
    return " ".join(
        str(value) if isinstance(value, int) else f"{value:.16g}" for value in values
    )


def _image_dimensions(archive: ZipFile, member: str) -> tuple[int, int, str]:
    with Image.open(io.BytesIO(archive.read(member))) as image:
        image.load()
        return image.width, image.height, image.mode


def _write_contact_sheet(
    archive: ZipFile,
    selected: list[tuple[SourceSample, list[PoseRow]]],
    output: Path,
) -> None:
    tile_size = 360
    title_height = 34
    columns = 2
    rows_count = math.ceil(len(selected) / columns)
    sheet = Image.new(
        "RGB", (columns * tile_size, rows_count * (tile_size + title_height)), "white"
    )
    draw = ImageDraw.Draw(sheet)
    class_colours = {0: "#ff3030", 1: "#39d353", 2: "#3b82f6"}
    for position, (sample, annotations) in enumerate(selected):
        with Image.open(io.BytesIO(archive.read(sample.image_member))) as source:
            image = source.convert("RGB")
        width, height = image.size
        image.thumbnail((tile_size, tile_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (tile_size, tile_size), "black")
        offset_x = (tile_size - image.width) // 2
        offset_y = (tile_size - image.height) // 2
        canvas.paste(image, (offset_x, offset_y))
        overlay = ImageDraw.Draw(canvas)
        scale_x = image.width / width
        scale_y = image.height / height
        for annotation in annotations:
            cx = offset_x + annotation.x * width * scale_x
            cy = offset_y + annotation.y * height * scale_y
            box_width = annotation.width * width * scale_x
            box_height = annotation.height * height * scale_y
            colour = class_colours[annotation.class_id]
            overlay.rectangle(
                (
                    cx - box_width / 2,
                    cy - box_height / 2,
                    cx + box_width / 2,
                    cy + box_height / 2,
                ),
                outline=colour,
                width=2,
            )
            if annotation.visibility > 0:
                px = offset_x + annotation.point_x * width * scale_x
                py = offset_y + annotation.point_y * height * scale_y
                radius = 3
                overlay.ellipse(
                    (px - radius, py - radius, px + radius, py + radius),
                    fill="#fff200",
                    outline="black",
                )
        column = position % columns
        row = position // columns
        x = column * tile_size
        y = row * (tile_size + title_height)
        draw.text(
            (x + 5, y + 4),
            f"{sample.split}: {sample.stem} | red=weed, green=maize, blue=soy, yellow=stem",
            fill="black",
        )
        sheet.paste(canvas, (x, y + title_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=92, subsampling=0)


def prepare(config_path: Path, *, audit_only: bool = False) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, config["data_root"])
    source = config["source"]
    outputs = config["outputs"]
    archive_path = _resolve(data_root, source["archive"])
    if archive_path.stat().st_size != int(source["archive_bytes"]):
        raise ValueError("WSD archive byte count mismatch")
    archive_digest = sha256(archive_path)
    if archive_digest != str(source["archive_sha256"]):
        raise ValueError("WSD archive SHA-256 mismatch")

    output_root = _resolve(data_root, outputs["root"])
    receipt_path = _resolve(data_root, outputs["receipt"])
    manifest_path = _resolve(data_root, outputs["manifest"])
    contact_path = _resolve(data_root, outputs["contact_sheet"])
    dataset_yaml_path = _resolve(data_root, outputs["ultralytics_yaml"])
    layout = config["archive_layout"]
    suffixes = tuple(str(value).lower() for value in layout["image_suffixes"])

    try:
        archive = ZipFile(archive_path)
    except BadZipFile as error:
        raise ValueError("WSD archive is not a valid ZIP") from error
    with archive:
        names = archive.namelist()
        unsafe = sorted(name for name in names if not _safe_member(name))
        if unsafe:
            raise ValueError(f"Unsafe ZIP members: {unsafe[:3]}")
        duplicate_names = sorted(
            name for name, count in Counter(names).items() if count > 1
        )
        if duplicate_names:
            raise ValueError(f"Duplicate ZIP members: {duplicate_names[:3]}")
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise ValueError(f"Corrupt ZIP member: {corrupt_member}")
        images = _members_by_stem(names, layout["image_prefix"], suffixes)
        boxes = _members_by_stem(names, layout["box_label_prefix"], (".txt",))
        points = _members_by_stem(names, layout["point_label_prefix"], (".txt",))
        common = sorted(set(images) & set(boxes) & set(points))
        orphan_images = sorted(set(images) - set(boxes) - set(points))
        orphan_boxes = sorted(set(boxes) - set(images))
        orphan_points = sorted(set(points) - set(images))
        samples = [
            SourceSample(
                stem=stem,
                image_member=images[stem],
                box_member=boxes[stem],
                point_member=points[stem],
                capture_date=_capture_date(stem),
                split=_split_for_date(_capture_date(stem), config["split_policy"]),
            )
            for stem in common
        ]
        parsed: dict[str, list[PoseRow]] = {}
        aggregate = Counter()
        split_stats: dict[str, Counter[str]] = {
            split: Counter() for split in ("train", "val", "test")
        }
        dimensions = Counter()
        for sample in samples:
            annotations, stats = parse_pose_rows(archive, sample, config)
            parsed[sample.stem] = annotations
            width, height, mode = _image_dimensions(archive, sample.image_member)
            dimensions[f"{width}x{height}:{mode}"] += 1
            aggregate.update(stats)
            split_stats[sample.split].update(stats)
            split_stats[sample.split]["images"] += 1

        if not audit_only:
            if output_root.exists() or manifest_path.exists():
                raise FileExistsError(
                    f"Prepared WSD output already exists: {output_root} or {manifest_path}"
                )
            for split in ("train", "val", "test"):
                (output_root / "images" / split).mkdir(parents=True, exist_ok=False)
                (output_root / "labels" / split).mkdir(parents=True, exist_ok=False)
            manifest_rows: list[dict[str, object]] = []
            label_hash_rows: list[str] = []
            for sample in samples:
                image_destination = (
                    output_root / "images" / sample.split / f"{sample.stem}.bmp"
                )
                with archive.open(sample.image_member) as source_handle, image_destination.open(
                    "wb"
                ) as destination_handle:
                    shutil.copyfileobj(source_handle, destination_handle, length=4 * 1024 * 1024)
                label_destination = (
                    output_root / "labels" / sample.split / f"{sample.stem}.txt"
                )
                label_payload = "\n".join(
                    _pose_line(row) for row in parsed[sample.stem]
                ) + "\n"
                label_destination.write_text(label_payload, encoding="utf-8")
                label_digest = hashlib.sha256(label_payload.encode("utf-8")).hexdigest()
                label_hash_rows.append(
                    f"{sample.split}/{sample.stem}.txt\0{label_digest}"
                )
                sample_stats = Counter()
                for row in parsed[sample.stem]:
                    sample_stats[f"class_{row.class_id}"] += 1
                    if row.class_id == int(config["normalization_policy"]["stem_keypoint_class"]):
                        sample_stats[
                            "visible_weed_points" if row.visibility > 0 else "missing_weed_points"
                        ] += 1
                manifest_rows.append(
                    {
                        "sample_id": sample.stem,
                        "capture_date": sample.capture_date,
                        "split": sample.split,
                        "image_path": image_destination.relative_to(data_root).as_posix(),
                        "pose_label_path": label_destination.relative_to(data_root).as_posix(),
                        "weed_instances": sample_stats["class_0"],
                        "maize_instances": sample_stats["class_1"],
                        "soybean_instances": sample_stats["class_2"],
                        "visible_weed_points": sample_stats["visible_weed_points"],
                        "missing_weed_points": sample_stats["missing_weed_points"],
                    }
                )
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with manifest_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
                writer.writeheader()
                writer.writerows(manifest_rows)
            dataset_yaml = {
                "path": str(output_root),
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "kpt_shape": [1, 3],
                "flip_idx": [0],
                "names": {
                    int(key): str(value)
                    for key, value in layout["class_names"].items()
                },
            }
            dataset_yaml_path.write_text(
                yaml.safe_dump(dataset_yaml, sort_keys=False), encoding="utf-8"
            )
            by_split = {
                split: [sample for sample in samples if sample.split == split]
                for split in ("train", "val", "test")
            }
            selected: list[tuple[SourceSample, list[PoseRow]]] = []
            for split in ("train", "val", "test"):
                candidates = by_split[split]
                for index in (len(candidates) // 3, 2 * len(candidates) // 3):
                    sample = candidates[index]
                    selected.append((sample, parsed[sample.stem]))
            _write_contact_sheet(archive, selected, contact_path)
            derived = {
                "output_root": str(output_root),
                "manifest": str(manifest_path),
                "manifest_sha256": sha256(manifest_path),
                "ultralytics_yaml": str(dataset_yaml_path),
                "ultralytics_yaml_sha256": sha256(dataset_yaml_path),
                "pose_label_tree_sha256": hashlib.sha256(
                    ("\n".join(sorted(label_hash_rows)) + "\n").encode("utf-8")
                ).hexdigest(),
                "contact_sheet": str(contact_path),
                "contact_sheet_sha256": sha256(contact_path),
            }
        else:
            derived = {"audit_only": True}

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "status": (
            "research_pilot_prepared_with_source_anomalies_disclosed"
            if not audit_only
            else "audit_only"
        ),
        "source": {
            "archive": str(archive_path),
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": archive_digest,
            "dataset_page": source["dataset_page"],
            "dataset_revision": source["dataset_revision"],
            "dataset_license": source["dataset_license"],
            "paper": source["paper"],
            "reference_code": source["reference_code"],
            "reference_code_revision": source["reference_code_revision"],
        },
        "archive_inventory": {
            "entries": len(names),
            "unique_entries": len(set(names)),
            "image_files": len(images),
            "box_label_files": len(boxes),
            "point_label_files": len(points),
            "paired_samples": len(samples),
            "orphan_images": orphan_images,
            "orphan_box_labels": orphan_boxes,
            "orphan_point_labels": orphan_points,
            "decoded_image_dimensions": dict(sorted(dimensions.items())),
        },
        "annotations": dict(sorted(aggregate.items())),
        "split_statistics": {
            split: dict(sorted(values.items()))
            for split, values in split_stats.items()
        },
        "normalization": {
            "date_disjoint": True,
            "box_fields_used": "first five fields",
            "point_authority": "separate points_labels row in matching order",
            "missing_weed_points_have_visibility_zero": True,
            "crop_placeholder_points_have_visibility_zero": True,
        },
        "disclosed_source_mismatches": {
            "paper_annotated_images": 1556,
            "downloadable_paired_images": len(samples),
            "paper_weed_instances": 11151,
            "downloadable_weed_boxes": int(aggregate["class_0_instances"]),
            "paper_reports_mungbean": True,
            "downloadable_archive_has_mungbean_class": False,
            "box_rows_with_extra_fields": int(
                aggregate["box_rows_with_extra_fields"]
            ),
            "orphan_box_label_files": len(orphan_boxes),
            "missing_weed_stem_points": int(aggregate["missing_weed_points"]),
            "reference_code_imports_missing_utils_package": True,
        },
        "quality_gates": {
            "archive_sha256_passed": True,
            "archive_byte_count_passed": True,
            "zip_integrity_passed": True,
            "archive_paths_safe": True,
            "unique_archive_member_names": True,
            "all_paired_images_decode": sum(dimensions.values()) == len(samples),
            "paired_box_point_row_counts_match": True,
            "all_visible_weed_points_inside_box": True,
            "capture_date_disjoint_splits": True,
            "publisher_archive_matches_paper_inventory": False,
            "reference_baseline_reproducible_from_published_repository": False,
            "production_release_approved": False,
            "research_pilot_approved": True,
        },
        "derived": derived,
        "provenance": {
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "preparer": str(Path(__file__).resolve()),
            "preparer_sha256": sha256(Path(__file__).resolve()),
        },
    }
    receipt["canonical_content_sha256"] = canonical_sha256(receipt)
    if not audit_only:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/data/weed_stem_detection_v1.yaml"
    )
    parser.add_argument("--audit-only", action="store_true")
    arguments = parser.parse_args()
    receipt = prepare(Path(arguments.config), audit_only=arguments.audit_only)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
