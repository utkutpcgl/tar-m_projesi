#!/usr/bin/env python3
"""Fail-closed GrowingSoy conversion with a longitudinally disjoint split.

The publisher's random split contains adjacent frames from every source video
in train, validation, and test.  This converter deliberately ignores those
roles, reconstructs the 1,000 original (non-augmented) frames, and applies the
trajectory split frozen in ``configs/data/growingsoy_real_gate_v1.yaml``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from PIL import Image, ImageDraw

from agri_seg.constants import BACKGROUND, CROP, IGNORE, WEED
from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    write_manifest,
)


PUBLISHER_SPLITS = ("train", "valid", "test")
FILENAME_PATTERN = re.compile(
    r"(?P<date>\d{8})-(?P<video>GX\d+)_frame(?P<frame>\d+)"
    r"_jpg\.rf\.(?P<roboflow_hash>[0-9a-f]+)\.jpg"
)
EXPECTED_CATEGORIES = [
    {"id": 0, "name": "soy, weeds", "supercategory": "none"},
    {"id": 1, "name": "caruru_weed", "supercategory": "soy, weeds"},
    {"id": 2, "name": "grassy_weed", "supercategory": "soy, weeds"},
    {"id": 3, "name": "soy_plant", "supercategory": "soy, weeds"},
]
CATEGORY_NAMES = {1: "caruru_weed", 2: "grassy_weed", 3: "soy_plant"}
WEED_SCIENTIFIC_NAMES = {
    1: "Amaranthus viridis",
    2: "Cynodon dactylon",
}


@dataclass(frozen=True)
class SourceFrame:
    publisher_split: str
    image_id: int
    image_path: Path
    file_name: str
    capture_date_compact: str
    video_id: str
    frame_index: int
    width: int
    height: int
    annotations: tuple[dict[str, Any], ...]

    @property
    def video_session(self) -> str:
        return f"{self.capture_date_compact}-{self.video_id}"

    @property
    def canonical_stem(self) -> str:
        return (
            f"{self.capture_date_compact}-{self.video_id}-"
            f"frame{self.frame_index:06d}"
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return payload


def git_output(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def hash_path_tree(paths: Iterable[Path], root: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    total_bytes = 0
    ordered = sorted(paths, key=lambda path: relative(path, root))
    for path in ordered:
        recorded_path = relative(path, root)
        digest.update(recorded_path.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                total_bytes += len(block)
        digest.update(b"\0")
    return digest.hexdigest(), total_bytes, len(ordered)


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"Unexpected GrowingSoy {name}: {actual!r} != {expected!r}")


def _validate_annotation(
    annotation: dict[str, Any], width: int, height: int, source: Path
) -> None:
    category_id = int(annotation.get("category_id", -1))
    if category_id not in CATEGORY_NAMES:
        raise ValueError(f"Unsupported category {category_id} in {source}")
    if int(annotation.get("iscrowd", -1)) != 0:
        raise ValueError(f"Crowd/RLE annotations are not accepted in {source}")
    if float(annotation.get("area", 0)) <= 0:
        raise ValueError(f"Non-positive annotation area in {source}")
    bbox = annotation.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"Malformed COCO bbox in {source}")
    if not all(math.isfinite(float(value)) for value in bbox):
        raise ValueError(f"Non-finite COCO bbox in {source}")
    if float(bbox[2]) <= 0 or float(bbox[3]) <= 0:
        raise ValueError(f"Non-positive COCO bbox in {source}")

    segmentation = annotation.get("segmentation")
    if not isinstance(segmentation, list) or not segmentation:
        raise ValueError(f"Missing polygon segmentation in {source}")
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2:
            raise ValueError(f"Malformed polygon segmentation in {source}")
        coordinates = [float(value) for value in polygon]
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError(f"Non-finite polygon coordinate in {source}")
        x_values = coordinates[::2]
        y_values = coordinates[1::2]
        if min(x_values) < 0 or max(x_values) > width:
            raise ValueError(f"Polygon x coordinate outside image in {source}")
        if min(y_values) < 0 or max(y_values) > height:
            raise ValueError(f"Polygon y coordinate outside image in {source}")
        signed_twice_area = sum(
            x_values[index] * y_values[(index + 1) % len(y_values)]
            - x_values[(index + 1) % len(x_values)] * y_values[index]
            for index in range(len(x_values))
        )
        if abs(signed_twice_area) <= 0:
            raise ValueError(f"Degenerate polygon in {source}")


def load_source_frames(
    repository: Path, gate: dict[str, Any]
) -> tuple[list[SourceFrame], dict[str, str], Counter[str]]:
    source_root = repository / "labeled"
    expected = gate["expected"]
    expected_publisher = expected["publisher_splits"]
    expected_annotation_hashes = gate["source_annotation_sha256"]
    width = int(expected["image_width"])
    height = int(expected["image_height"])
    frames: list[SourceFrame] = []
    annotation_hashes: dict[str, str] = {}
    category_counts: Counter[str] = Counter()
    canonical_keys: set[tuple[str, str, int]] = set()
    file_names: set[str] = set()

    for publisher_split in PUBLISHER_SPLITS:
        split_root = source_root / publisher_split
        annotation_path = split_root / "_annotations.coco.json"
        annotation_hashes[publisher_split] = sha256(annotation_path)
        require_equal(
            f"{publisher_split} annotation SHA-256",
            annotation_hashes[publisher_split],
            str(expected_annotation_hashes[publisher_split]),
        )
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        require_equal(
            f"{publisher_split} categories", payload.get("categories"), EXPECTED_CATEGORIES
        )
        licenses = payload.get("licenses")
        if not isinstance(licenses, list) or not any(
            str(item.get("name", "")).upper() == "MIT"
            for item in licenses
            if isinstance(item, dict)
        ):
            raise ValueError(f"GrowingSoy {publisher_split} lacks its MIT licence tag")

        images = payload.get("images")
        annotations = payload.get("annotations")
        if not isinstance(images, list) or not isinstance(annotations, list):
            raise ValueError(f"Malformed COCO document: {annotation_path}")
        require_equal(
            f"{publisher_split} image count",
            len(images),
            int(expected_publisher[publisher_split]["images"]),
        )
        require_equal(
            f"{publisher_split} annotation count",
            len(annotations),
            int(expected_publisher[publisher_split]["annotations"]),
        )
        image_by_id: dict[int, dict[str, Any]] = {}
        for image in images:
            image_id = int(image["id"])
            if image_id in image_by_id:
                raise ValueError(f"Duplicate image id in {annotation_path}: {image_id}")
            image_by_id[image_id] = image
        annotation_ids: set[int] = set()
        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in annotations:
            annotation_id = int(annotation["id"])
            if annotation_id in annotation_ids:
                raise ValueError(
                    f"Duplicate annotation id in {annotation_path}: {annotation_id}"
                )
            annotation_ids.add(annotation_id)
            image_id = int(annotation["image_id"])
            if image_id not in image_by_id:
                raise ValueError(f"Orphan annotation in {annotation_path}: {image_id}")
            _validate_annotation(annotation, width, height, annotation_path)
            category_id = int(annotation["category_id"])
            category_counts[CATEGORY_NAMES[category_id]] += 1
            annotations_by_image[image_id].append(annotation)

        for image_id, image in image_by_id.items():
            file_name = str(image["file_name"])
            match = FILENAME_PATTERN.fullmatch(file_name)
            if match is None:
                raise ValueError(f"Unexpected GrowingSoy filename: {file_name}")
            capture_date = match.group("date")
            video_id = match.group("video")
            frame_index = int(match.group("frame"))
            canonical_key = (capture_date, video_id, frame_index)
            if canonical_key in canonical_keys or file_name in file_names:
                raise ValueError(f"Duplicate GrowingSoy source frame: {canonical_key}")
            canonical_keys.add(canonical_key)
            file_names.add(file_name)
            image_width = int(image["width"])
            image_height = int(image["height"])
            require_equal(f"image width for {file_name}", image_width, width)
            require_equal(f"image height for {file_name}", image_height, height)
            image_path = split_root / file_name
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            with Image.open(image_path) as image_handle:
                image_handle.load()
                require_equal(f"decoded size for {file_name}", image_handle.size, (width, height))
                require_equal(f"decoded mode for {file_name}", image_handle.mode, "RGB")
            frames.append(
                SourceFrame(
                    publisher_split=publisher_split,
                    image_id=image_id,
                    image_path=image_path,
                    file_name=file_name,
                    capture_date_compact=capture_date,
                    video_id=video_id,
                    frame_index=frame_index,
                    width=width,
                    height=height,
                    annotations=tuple(annotations_by_image[image_id]),
                )
            )

    frames.sort(
        key=lambda frame: (
            frame.capture_date_compact,
            frame.video_id,
            frame.frame_index,
        )
    )
    require_equal("source image count", len(frames), int(expected["source_images"]))
    require_equal(
        "source annotation count",
        sum(len(frame.annotations) for frame in frames),
        int(expected["source_annotations"]),
    )
    expected_categories = {
        str(name): int(count)
        for name, count in expected["annotation_categories"].items()
    }
    require_equal("annotation category counts", dict(category_counts), expected_categories)
    background_only = sum(not frame.annotations for frame in frames)
    require_equal(
        "background-only image count",
        background_only,
        int(expected["background_only_images"]),
    )
    return frames, annotation_hashes, category_counts


def trajectory_policy(
    gate: dict[str, Any], frames: list[SourceFrame]
) -> tuple[dict[str, tuple[str, str]], dict[str, int]]:
    policy: dict[str, tuple[str, str]] = {}
    allowed_roles = {"train", "external_calibration"}
    for trajectory_name, specification in gate["longitudinal_trajectories"].items():
        role = str(specification["role"])
        if role not in allowed_roles:
            raise ValueError(f"Unsupported GrowingSoy split role: {role}")
        for video_session in specification["videos"]:
            video_session = str(video_session)
            if video_session in policy:
                raise ValueError(f"Video occurs in two trajectories: {video_session}")
            policy[video_session] = (str(trajectory_name), role)

    actual_counts = Counter(frame.video_session for frame in frames)
    expected_counts = {
        str(video): int(count)
        for video, count in gate["expected"]["source_images_by_video"].items()
    }
    require_equal("source video counts", dict(actual_counts), expected_counts)
    require_equal("trajectory video coverage", set(policy), set(actual_counts))
    return policy, dict(actual_counts)


def rasterize(frame: SourceFrame) -> tuple[np.ndarray, dict[str, int], set[int]]:
    crop_layer = Image.new("1", (frame.width, frame.height), 0)
    weed_layer = Image.new("1", (frame.width, frame.height), 0)
    crop_draw = ImageDraw.Draw(crop_layer)
    weed_draw = ImageDraw.Draw(weed_layer)
    weed_categories: set[int] = set()
    instance_counts = Counter[str]()
    for annotation in frame.annotations:
        category_id = int(annotation["category_id"])
        target = crop_draw if category_id == 3 else weed_draw
        if category_id in WEED_SCIENTIFIC_NAMES:
            weed_categories.add(category_id)
        instance_counts[CATEGORY_NAMES[category_id]] += 1
        for polygon in annotation["segmentation"]:
            coordinates = [float(value) for value in polygon]
            points = list(zip(coordinates[::2], coordinates[1::2], strict=True))
            target.polygon(points, fill=1)

    crop = np.asarray(crop_layer, dtype=bool)
    weed = np.asarray(weed_layer, dtype=bool)
    overlap = crop & weed
    common = np.full((frame.height, frame.width), BACKGROUND, dtype=np.uint8)
    common[crop & ~weed] = CROP
    common[weed & ~crop] = WEED
    common[overlap] = IGNORE
    pixel_counts = {
        "background": int((common == BACKGROUND).sum()),
        "crop": int((common == CROP).sum()),
        "weed": int((common == WEED).sum()),
        "ignore_overlap": int((common == IGNORE).sum()),
        **{f"instances_{name}": int(count) for name, count in instance_counts.items()},
    }
    return common, pixel_counts, weed_categories


def convert(
    registry_path: Path,
    gate_path: Path,
    output_manifest: Path | None = None,
) -> tuple[Path, Path]:
    registry = load_mapping(registry_path)
    gate = load_mapping(gate_path)
    if str(gate.get("dataset_id")) != "growingsoy":
        raise ValueError("GrowingSoy gate has the wrong dataset_id")
    data_root = Path(str(registry["data_root"])).expanduser().resolve()
    dataset_spec = registry["datasets"]["growingsoy"]
    repository = data_root / str(dataset_spec["extracted"])
    if not repository.is_dir():
        raise FileNotFoundError(repository)
    actual_revision = git_output(repository, "rev-parse", "HEAD")
    expected_revision = str(gate["source_revision"])
    require_equal("repository revision", actual_revision, expected_revision)
    require_equal("registry revision", str(dataset_spec["revision"]), expected_revision)
    dirty = git_output(repository, "status", "--porcelain")
    if dirty:
        raise RuntimeError("GrowingSoy raw repository is not immutable/clean")
    labeled_git_tree = git_output(repository, "rev-parse", "HEAD:labeled")
    require_equal("labeled Git tree", labeled_git_tree, str(gate["labeled_git_tree"]))
    if bool(gate["quality_gate"]["reject_augmented_labeled_tree"]) and not (
        repository / "augmented-labeled"
    ).is_dir():
        raise ValueError("Expected augmented tree is absent; upstream layout changed")

    frames, annotation_hashes, category_counts = load_source_frames(repository, gate)
    source_image_hash, source_image_bytes, source_image_count = hash_path_tree(
        (frame.image_path for frame in frames), repository
    )
    require_equal(
        "source image tree SHA-256",
        source_image_hash,
        str(gate["source_image_tree_sha256"]),
    )
    require_equal(
        "source image bytes",
        source_image_bytes,
        int(gate["expected"]["source_image_bytes"]),
    )
    require_equal(
        "source image tree count",
        source_image_count,
        int(gate["expected"]["source_images"]),
    )
    policy, source_video_counts = trajectory_policy(gate, frames)

    normalized_root = data_root / "processed/growingsoy/common_masks"
    destination = output_manifest or data_root / "processed/manifests/growingsoy.csv"
    destination = destination.expanduser().resolve()
    records: list[SampleRecord] = []
    condition_rows: list[dict[str, object]] = []
    class_pixels: dict[str, Counter[str]] = defaultdict(Counter)
    overlap_images: list[str] = []
    weed_positive_images: Counter[str] = Counter()
    first_capture = date(2022, 12, 16)

    for frame in frames:
        trajectory_name, split = policy[frame.video_session]
        common, counts, weed_categories = rasterize(frame)
        values = set(np.unique(common).tolist())
        if not values <= {BACKGROUND, CROP, WEED, IGNORE}:
            raise RuntimeError(f"Invalid normalized labels for {frame.file_name}: {values}")
        if counts["ignore_overlap"]:
            overlap_images.append(frame.canonical_stem)
        if counts["weed"]:
            weed_positive_images[split] += 1
        class_pixels[split].update(
            {
                name: counts[name]
                for name in ("background", "crop", "weed", "ignore_overlap")
            }
        )
        common_path = normalized_root / split / f"{frame.canonical_stem}.png"
        common_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(common).save(common_path)

        capture = datetime.strptime(frame.capture_date_compact, "%Y%m%d").date()
        day_index = (capture - first_capture).days
        weed_species = ";".join(
            WEED_SCIENTIFIC_NAMES[category_id]
            for category_id in sorted(weed_categories)
        )
        record = SampleRecord(
            sample_id=f"growingsoy:{frame.canonical_stem}",
            image_path=relative(frame.image_path, data_root),
            mask_path=relative(common_path, data_root),
            split=split,
            dataset_id="growingsoy",
            field_id="ufsm_santa_maria_soy_research_field",
            session_id=f"longitudinal_{trajectory_name}_full_cycle",
            capture_date=capture.isoformat(),
            platform="ATV-mounted GoPro video frame",
            sensor="GoPro HERO12 RGB 4K120 source; publisher-resized 640x640",
            target_crop_id=int(gate["quality_gate"]["exact_target_crop_id"]),
            crop_species=str(gate["quality_gate"]["exact_crop_species"]),
            weed_species_optional=weed_species,
            growth_stage=f"chronological_day_{day_index}_publisher_stage_unresolved",
            annotation_exhaustive=counts["ignore_overlap"] == 0,
            license_status=str(gate["quality_gate"]["license"]),
            commercial_allowed=bool(gate["quality_gate"]["commercial_allowed"]),
        )
        records.append(record)
        condition_rows.append(
            {
                "sample_id": record.sample_id,
                "split": split,
                "trajectory": trajectory_name,
                "capture_date": record.capture_date,
                "source_video_session": frame.video_session,
                "source_video_id": frame.video_id,
                "source_frame_index": frame.frame_index,
                "publisher_split_ignored": frame.publisher_split,
                "source_file_name": frame.file_name,
                "instances_soy": counts.get("instances_soy_plant", 0),
                "instances_caruru": counts.get("instances_caruru_weed", 0),
                "instances_grassy": counts.get("instances_grassy_weed", 0),
                "pixels_background": counts["background"],
                "pixels_crop": counts["crop"],
                "pixels_weed": counts["weed"],
                "pixels_ignore_overlap": counts["ignore_overlap"],
            }
        )

    split_counts = Counter(record.split for record in records)
    expected_final_splits = {
        str(split): int(count)
        for split, count in gate["expected"]["final_splits"].items()
    }
    require_equal("final split counts", dict(split_counts), expected_final_splits)
    total_pixels = sum(sum(counter.values()) for counter in class_pixels.values())
    expected_pixels = len(records) * int(gate["expected"]["image_width"]) * int(
        gate["expected"]["image_height"]
    )
    require_equal("normalized pixel count", total_pixels, expected_pixels)
    overlap_pixels = sum(counter["ignore_overlap"] for counter in class_pixels.values())
    overlap_fraction = overlap_pixels / expected_pixels
    max_overlap = float(gate["quality_gate"]["max_crop_weed_overlap_fraction"])
    if overlap_fraction > max_overlap:
        raise ValueError(
            f"GrowingSoy crop/weed overlap {overlap_fraction:.6f} exceeds {max_overlap}"
        )
    if bool(gate["quality_gate"]["require_train_weed_pixels"]) and not class_pixels[
        "train"
    ]["weed"]:
        raise ValueError("GrowingSoy train split contains no weed pixels")
    if bool(
        gate["quality_gate"]["require_external_calibration_weed_pixels"]
    ) and not class_pixels["external_calibration"]["weed"]:
        raise ValueError("GrowingSoy calibration split contains no weed pixels")

    expected_masks = {
        (data_root / record.mask_path).resolve() for record in records
    }
    actual_masks = {
        path.resolve() for path in normalized_root.rglob("*.png") if path.is_file()
    }
    extras = sorted(actual_masks - expected_masks)
    missing = sorted(expected_masks - actual_masks)
    if extras or missing:
        raise RuntimeError(
            "GrowingSoy normalized mask tree is not exact: "
            f"extras={extras[:5]}, missing={missing[:5]}"
        )

    write_manifest(records, destination)
    conditions_path = data_root / "processed/growingsoy/conditions.csv"
    conditions_path.parent.mkdir(parents=True, exist_ok=True)
    with conditions_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(condition_rows[0]))
        writer.writeheader()
        writer.writerows(condition_rows)

    converter_path = Path(__file__).resolve()
    report = {
        "schema_version": 1,
        "dataset_id": "growingsoy",
        "samples": len(records),
        "split_counts": dict(split_counts),
        "group_counts": {
            split: len({record.group_id for record in records if record.split == split})
            for split in expected_final_splits
        },
        "capture_date_counts": dict(Counter(record.capture_date for record in records)),
        "source_video_counts": source_video_counts,
        "source_annotation_counts": dict(category_counts),
        "class_pixels": {
            split: dict(counter) for split, counter in class_pixels.items()
        },
        "weed_positive_images": dict(weed_positive_images),
        "overlap": {
            "pixels_mapped_to_ignore": overlap_pixels,
            "fraction": overlap_fraction,
            "maximum_allowed_fraction": max_overlap,
            "affected_images": len(overlap_images),
            "affected_canonical_stems": overlap_images,
        },
        "ontology": {
            "background": BACKGROUND,
            "target_crop_Glycine_max": CROP,
            "caruru_and_grassy_weeds": WEED,
            "crop_weed_polygon_overlap": IGNORE,
        },
        "policy": {
            "publisher_split": str(
                gate["quality_gate"]["publisher_split_policy"]
            ),
            "source_tree": "labeled only; augmented-labeled excluded",
            "split_unit": "inferred longitudinal treatment/trajectory across all dates",
            "training_trajectory": "trajectory_b (weed-richer)",
            "external_calibration_trajectory": "trajectory_a (never trained)",
            "growth_stage": "date order retained; exact phenological stage unresolved",
            "polygon_overlap": "ignore_255",
        },
        "provenance": {
            "repository": str(repository),
            "revision": actual_revision,
            "labeled_git_tree": labeled_git_tree,
            "source_image_tree_sha256": source_image_hash,
            "source_image_bytes": source_image_bytes,
            "source_annotation_sha256": annotation_hashes,
            "license_sha256": sha256(repository / "LICENSE"),
            "readme_sha256": sha256(repository / "README.md"),
            "registry": str(registry_path.resolve()),
            "registry_sha256": sha256(registry_path.resolve()),
            "gate_config": str(gate_path.resolve()),
            "gate_config_sha256": sha256(gate_path.resolve()),
            "converter": str(converter_path),
            "converter_sha256": sha256(converter_path),
        },
        "derived": {
            "manifest": str(destination),
            "manifest_sha256": manifest_sha256(destination),
            "normalized_mask_tree_sha256": mask_tree_sha256(records, data_root),
            "conditions": str(conditions_path),
            "conditions_sha256": sha256(conditions_path),
        },
        "all_quality_gates_passed": True,
    }
    report_path = data_root / "processed/manifests/growingsoy_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="configs/datasets.yaml")
    parser.add_argument(
        "--gate-config", default="configs/data/growingsoy_real_gate_v1.yaml"
    )
    parser.add_argument("--output-manifest")
    arguments = parser.parse_args()
    manifest, report = convert(
        Path(arguments.registry),
        Path(arguments.gate_config),
        Path(arguments.output_manifest) if arguments.output_manifest else None,
    )
    print(
        json.dumps(
            {"dataset": "growingsoy", "manifest": str(manifest), "report": str(report)},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
