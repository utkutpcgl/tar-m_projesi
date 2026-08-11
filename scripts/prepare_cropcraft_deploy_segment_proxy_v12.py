#!/usr/bin/env python3
"""Package a gated CropCraft release as YOLO class-region segmentation labels.

CropCraft emits exact crop/weed semantic masks, not botanical instance IDs.
Each 8-connected visible class region is therefore packaged as a region proxy.
This is suitable for union-mask spot-spray experiments but must not be reported
as true instance-label evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_phenobench_detect_segment_fair_v1 import (
    PlantObject,
    _polygon_from_mask,
    _polygon_iou,
    segmentation_label_line,
    sha256,
    tree_sha256,
)


ROLES = ("train", "val", "test")
CLASS_COLOURS = {0: (255, 0, 0), 1: (0, 255, 0)}
CLASS_NAMES = {0: "weed", 1: "crop"}
REFERENCE_SEMANTIC_IDS = {0: 2, 1: 1}


def load_object(path: Path) -> dict[str, Any]:
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".json"
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def percentiles(values: Sequence[float]) -> dict[str, float | None]:
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


def histogram_percentile(histogram: np.ndarray, percentile: float) -> int:
    if histogram.shape != (256,) or int(histogram.sum()) <= 0:
        raise ValueError("Expected a non-empty 256-bin histogram")
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("Percentile must be in [0, 1]")
    cumulative = np.cumsum(histogram, dtype=np.int64)
    return int(np.searchsorted(cumulative, percentile * cumulative[-1]))


def empty_hsv_histograms() -> dict[int, dict[str, np.ndarray]]:
    return {
        class_id: {
            "saturation": np.zeros(256, dtype=np.int64),
            "value": np.zeros(256, dtype=np.int64),
        }
        for class_id in CLASS_COLOURS
    }


def update_hsv_histograms(
    histograms: dict[int, dict[str, np.ndarray]],
    rgb: np.ndarray,
    class_map: np.ndarray,
    *,
    stride: int,
) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or class_map.shape != rgb.shape[:2]:
        raise ValueError("RGB and class map shapes do not match")
    if stride <= 0:
        raise ValueError("Sampling stride must be positive")
    hsv = np.asarray(Image.fromarray(rgb).convert("HSV"), dtype=np.uint8)
    sampled_hsv = hsv[::stride, ::stride]
    sampled_classes = class_map[::stride, ::stride]
    for class_id in CLASS_COLOURS:
        values = sampled_hsv[sampled_classes == class_id]
        if len(values) == 0:
            continue
        histograms[class_id]["saturation"] += np.bincount(
            values[:, 1], minlength=256
        )
        histograms[class_id]["value"] += np.bincount(
            values[:, 2], minlength=256
        )


def histogram_summary(
    histograms: dict[int, dict[str, np.ndarray]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for class_id, name in CLASS_NAMES.items():
        result[name] = {}
        for channel, histogram in histograms[class_id].items():
            result[name][channel] = {
                "pixels": int(histogram.sum()),
                "p05": histogram_percentile(histogram, 0.05),
                "p50": histogram_percentile(histogram, 0.50),
                "p95": histogram_percentile(histogram, 0.95),
            }
    return result


def derive_midpoint_factors(
    synthetic_summary: dict[str, Any],
    reference_summary: dict[str, Any],
    *,
    blend_fraction: float,
) -> dict[str, dict[str, float]]:
    if not 0.0 < blend_fraction <= 1.0:
        raise ValueError("Appearance blend fraction must be in (0, 1]")
    result: dict[str, dict[str, float]] = {}
    for name in CLASS_NAMES.values():
        result[name] = {}
        for channel in ("saturation", "value"):
            source = float(synthetic_summary[name][channel]["p50"])
            reference = float(reference_summary[name][channel]["p50"])
            if source <= 0:
                raise ValueError(f"Synthetic {name} {channel} median is zero")
            target = source + blend_fraction * (reference - source)
            factor = target / source
            if not np.isfinite(factor) or factor <= 0:
                raise ValueError(f"Invalid {name} {channel} factor")
            result[name][channel] = float(factor)
    return result


def apply_hsv_appearance_calibration(
    rgb: np.ndarray,
    class_map: np.ndarray,
    factors: dict[str, dict[str, float]],
    *,
    maximum_saturation: int,
    minimum_value: int,
) -> np.ndarray:
    if not 0 <= maximum_saturation <= 255 or not 0 <= minimum_value <= 255:
        raise ValueError("Invalid HSV calibration limits")
    hsv = np.asarray(Image.fromarray(rgb).convert("HSV"), dtype=np.uint8).copy()
    for class_id, name in CLASS_NAMES.items():
        selected = class_map == class_id
        if not selected.any():
            continue
        saturation = hsv[:, :, 1][selected].astype(np.float64)
        value = hsv[:, :, 2][selected].astype(np.float64)
        hsv[:, :, 1][selected] = np.clip(
            np.rint(saturation * factors[name]["saturation"]),
            0,
            maximum_saturation,
        ).astype(np.uint8)
        hsv[:, :, 2][selected] = np.clip(
            np.rint(value * factors[name]["value"]),
            minimum_value,
            255,
        ).astype(np.uint8)
    height, width = hsv.shape[:2]
    converted = np.asarray(
        Image.frombytes("HSV", (width, height), hsv.tobytes()).convert("RGB"),
        dtype=np.uint8,
    )
    result = rgb.copy()
    plant = class_map >= 0
    result[plant] = converted[plant]
    return result


def synthetic_class_map(semantic_rgb: np.ndarray) -> np.ndarray:
    result = np.full(semantic_rgb.shape[:2], -1, dtype=np.int8)
    for class_id, colour in CLASS_COLOURS.items():
        result[np.all(semantic_rgb == np.asarray(colour, dtype=np.uint8), axis=2)] = (
            class_id
        )
    return result


def reference_hsv_histograms(
    membership_path: Path,
    *,
    reference_split: str,
    expected_images: int,
    stride: int,
) -> tuple[dict[int, dict[str, np.ndarray]], int]:
    histograms = empty_hsv_histograms()
    count = 0
    for line in membership_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("logical_split") != reference_split:
            continue
        image_path = Path(row["image_path"])
        semantics_path = Path(row["semantics_path"])
        with Image.open(image_path) as handle:
            rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
        with Image.open(semantics_path) as handle:
            semantics = np.asarray(handle)
        if semantics.shape != rgb.shape[:2]:
            raise RuntimeError(f"Reference RGB/semantic shape mismatch: {image_path}")
        class_map = np.full(semantics.shape, -1, dtype=np.int8)
        for class_id, semantic_id in REFERENCE_SEMANTIC_IDS.items():
            class_map[semantics == semantic_id] = class_id
        update_hsv_histograms(histograms, rgb, class_map, stride=stride)
        count += 1
    if count != expected_images:
        raise RuntimeError(
            f"Expected {expected_images} reference images, observed {count}"
        )
    return histograms, count


def read_semantic_mask(path: Path) -> np.ndarray:
    with Image.open(path) as handle:
        mask = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    colours = {tuple(value) for value in np.unique(mask.reshape(-1, 3), axis=0)}
    allowed = {(0, 0, 0), *CLASS_COLOURS.values()}
    if not colours <= allowed:
        raise ValueError(f"Unexpected mask colours in {path}: {sorted(colours - allowed)}")
    return mask


def region_objects_and_truth(
    semantic_rgb: np.ndarray,
    *,
    minimum_area_px: int,
    polygon_epsilon_px: float,
) -> tuple[list[PlantObject], dict[str, int], np.ndarray, np.ndarray]:
    if semantic_rgb.ndim != 3 or semantic_rgb.shape[2] != 3:
        raise ValueError("Semantic mask must be HxWx3")
    if minimum_area_px <= 0 or polygon_epsilon_px < 0:
        raise ValueError("Invalid area or polygon approximation setting")
    height, width = semantic_rgb.shape[:2]
    semantic_ids = np.zeros((height, width), dtype=np.uint8)
    instance_ids = np.zeros((height, width), dtype=np.uint16)
    structure = np.ones((3, 3), dtype=np.uint8)
    objects: list[PlantObject] = []
    audit = {
        "regions_below_minimum_area": 0,
        "regions_without_valid_polygon": 0,
        "border_touching_regions": 0,
    }
    next_id = 1
    for class_id, colour in CLASS_COLOURS.items():
        selected = np.all(semantic_rgb == np.asarray(colour, dtype=np.uint8), axis=2)
        labels, count = ndimage.label(selected, structure=structure)
        slices = ndimage.find_objects(labels, max_label=count)
        for label_id, region_slice in enumerate(slices, start=1):
            if region_slice is None:
                continue
            region = labels[region_slice] == label_id
            area = int(region.sum())
            if area < minimum_area_px:
                audit["regions_below_minimum_area"] += 1
                continue
            local_polygon = _polygon_from_mask(region, polygon_epsilon_px)
            if local_polygon is None:
                audit["regions_without_valid_polygon"] += 1
                continue
            row_slice, column_slice = region_slice
            polygon = local_polygon + np.asarray(
                [column_slice.start, row_slice.start], dtype=np.float64
            )
            box = (
                int(column_slice.start),
                int(row_slice.start),
                int(column_slice.stop),
                int(row_slice.stop),
            )
            if box[0] == 0 or box[1] == 0 or box[2] == width or box[3] == height:
                audit["border_touching_regions"] += 1
            objects.append(
                PlantObject(
                    class_id=class_id,
                    instance_id=next_id,
                    area=area,
                    box_xyxy=box,
                    polygon_xy=polygon,
                    polygon_iou=_polygon_iou(region, local_polygon),
                )
            )
            destination_semantic = 2 if class_id == 0 else 1
            semantic_view = semantic_ids[region_slice]
            instance_view = instance_ids[region_slice]
            semantic_view[region] = destination_semantic
            instance_view[region] = next_id
            next_id += 1
    return objects, audit, semantic_ids, instance_ids


def region_objects(
    semantic_rgb: np.ndarray,
    *,
    minimum_area_px: int,
    polygon_epsilon_px: float,
) -> tuple[list[PlantObject], dict[str, int]]:
    """Return training objects while preserving the original public helper."""
    objects, audit, _, _ = region_objects_and_truth(
        semantic_rgb,
        minimum_area_px=minimum_area_px,
        polygon_epsilon_px=polygon_epsilon_px,
    )
    return objects, audit


def _source_inventory(scene_root: Path, expected_receipt_sha256: str) -> dict[str, str]:
    receipt_path = scene_root / "generation_receipt.json"
    if sha256(receipt_path) != expected_receipt_sha256:
        raise RuntimeError(f"Scene receipt changed: {scene_root}")
    receipt = load_object(receipt_path)
    inventory = receipt.get("outputs")
    if not isinstance(inventory, list):
        raise RuntimeError(f"Scene receipt lacks output inventory: {scene_root}")
    return {str(row["path"]): str(row["sha256"]) for row in inventory}


def run(
    config_path: Path,
    *,
    source_release: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_object(config_path)
    release = (
        Path(config["source_release"]) if source_release is None else source_release
    ).expanduser().resolve()
    output = (
        Path(config["output"]) if output_path is None else output_path
    ).expanduser().resolve()
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output if output.exists() else partial)

    top_path = release / "release_receipt.json"
    top = load_object(top_path)
    if top.get("all_quality_gates_passed") is not True:
        raise RuntimeError("CropCraft top-level release gate did not pass")
    if float(top.get("real_model_selection_score_weight", -1)) != 0.0:
        raise RuntimeError("Synthetic real-score weight must be exactly zero")
    deploy_gate = top.get("deploy_visual_gate")
    if not isinstance(deploy_gate, dict) or deploy_gate.get("all_quality_gates_passed") is not True:
        raise RuntimeError("CropCraft deploy visual gate did not pass")
    resolved_study = Path(top["resolved_study"]).resolve()
    if sha256(resolved_study) != top["resolved_study_sha256"]:
        raise RuntimeError("Resolved study changed after generation")
    if top.get("asset_contract", {}).get("passed") is not True:
        raise RuntimeError("Synthetic split asset contract did not pass")

    visual_index = {
        (str(row["role"]), str(row["scene"]), str(row["frame"])): row
        for row in deploy_gate["frame_rows"]
    }
    role_rows = {str(row["role"]): row for row in top["roles"]}
    if set(role_rows) != set(ROLES):
        raise RuntimeError("Expected exactly train/val/test roles")

    appearance_cfg = config.get("appearance_calibration")
    if not isinstance(appearance_cfg, dict) or appearance_cfg.get("enabled") is not True:
        raise RuntimeError("The V12 appearance calibration must be enabled")
    if appearance_cfg.get("method") != "classwise_hsv_median_half_gap_to_real_train":
        raise RuntimeError("Unexpected V12 appearance calibration method")
    reference_membership = Path(
        appearance_cfg["reference_membership"]
    ).expanduser().resolve()
    reference_membership_hash_locked = (
        sha256(reference_membership)
        == str(appearance_cfg["reference_membership_sha256"])
    )
    if not reference_membership_hash_locked:
        raise RuntimeError("Appearance reference membership changed")
    reference_split = str(appearance_cfg["reference_split"])
    if reference_split != "train":
        raise RuntimeError("Appearance calibration may use only real train data")
    expected_reference_images = int(appearance_cfg["expected_reference_images"])
    sampling_stride = int(appearance_cfg["sampling_stride_px"])
    reference_histograms, reference_image_count = reference_hsv_histograms(
        reference_membership,
        reference_split=reference_split,
        expected_images=expected_reference_images,
        stride=sampling_stride,
    )
    synthetic_histograms = empty_hsv_histograms()
    synthetic_calibration_images = 0
    for key, frame in sorted(visual_index.items()):
        if key[0] != "train":
            continue
        with Image.open(frame["rgb"]) as handle:
            rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
        mask = read_semantic_mask(Path(frame["mask"]))
        update_hsv_histograms(
            synthetic_histograms,
            rgb,
            synthetic_class_map(mask),
            stride=sampling_stride,
        )
        synthetic_calibration_images += 1
    reference_appearance = histogram_summary(reference_histograms)
    synthetic_appearance_before = histogram_summary(synthetic_histograms)
    appearance_factors = derive_midpoint_factors(
        synthetic_appearance_before,
        reference_appearance,
        blend_fraction=float(appearance_cfg["blend_fraction"]),
    )
    adapted_histograms = empty_hsv_histograms()
    background_pixels_unchanged = True
    plant_colour_counts = {
        name: {"pixels": 0, "green_dominant_pixels": 0}
        for name in CLASS_NAMES.values()
    }

    label_cfg = config["labels"]
    minimum_area = int(label_cfg["minimum_component_area_px"])
    epsilon = float(label_cfg["polygon_approximation_epsilon_px"])
    minimum_p05 = float(label_cfg["minimum_polygon_reconstruction_iou_p05"])
    partial.mkdir(parents=True, exist_ok=False)
    membership_lines: list[str] = []
    counts = {
        role: {"images": 0, "weed_regions": 0, "crop_regions": 0}
        for role in ROLES
    }
    audit_totals = Counter()
    polygon_ious: list[float] = []
    polygon_points: list[float] = []
    seeds_by_role: dict[str, set[int]] = {role: set() for role in ROLES}
    source_hashes_by_role: dict[str, set[str]] = {role: set() for role in ROLES}

    for role in ROLES:
        role_row = role_rows[role]
        role_root = Path(role_row["output"]).resolve()
        if role_root != (release / "roles" / role).resolve():
            raise RuntimeError(f"Unexpected role output path: {role}")
        role_receipt_path = role_root / "release_receipt.json"
        if sha256(role_receipt_path) != role_row["receipt_sha256"]:
            raise RuntimeError(f"Role receipt changed: {role}")
        role_receipt = load_object(role_receipt_path)
        if role_receipt.get("all_quality_gates_passed") is not True:
            raise RuntimeError(f"Role gate did not pass: {role}")
        source_receipts = {
            str(row["scene"]): (str(row["receipt_sha256"]), int(row["seed"]))
            for row in role_receipt["scenes"]
        }
        for scene, (scene_receipt_hash, seed) in sorted(source_receipts.items()):
            scene_root = role_root / "scenes" / scene
            inventory = _source_inventory(scene_root, scene_receipt_hash)
            seeds_by_role[role].add(seed)
            images = sorted((scene_root / "render/images").glob("*.jpg"))
            masks = {path.stem: path for path in (scene_root / "render/masks").glob("*.png")}
            if {path.stem for path in images} != set(masks):
                raise RuntimeError(f"RGB/mask pairing mismatch: {role}/{scene}")
            for image_path in images:
                stem = image_path.stem
                mask_path = masks[stem]
                lock = visual_index.get((role, scene, stem))
                if lock is None or Path(lock["rgb"]).resolve() != image_path.resolve():
                    raise RuntimeError(f"Deploy visual index mismatch: {role}/{scene}/{stem}")
                if Path(lock["mask"]).resolve() != mask_path.resolve():
                    raise RuntimeError(f"Deploy mask index mismatch: {role}/{scene}/{stem}")
                for source_path in (image_path, mask_path):
                    relative = source_path.relative_to(scene_root).as_posix()
                    observed_hash = sha256(source_path)
                    if inventory.get(relative) != observed_hash:
                        raise RuntimeError(f"Source output hash mismatch: {source_path}")
                    source_hashes_by_role[role].add(observed_hash)
                with Image.open(image_path) as handle:
                    rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
                height, width = rgb.shape[:2]
                if (width, height) != (1024, 1024):
                    raise RuntimeError(f"Expected native 1024 tile: {image_path}")
                mask = read_semantic_mask(mask_path)
                class_map = synthetic_class_map(mask)
                adapted_rgb = apply_hsv_appearance_calibration(
                    rgb,
                    class_map,
                    appearance_factors,
                    maximum_saturation=int(appearance_cfg["maximum_saturation"]),
                    minimum_value=int(appearance_cfg["minimum_value"]),
                )
                background = class_map < 0
                background_pixels_unchanged &= bool(
                    np.array_equal(adapted_rgb[background], rgb[background])
                )
                for class_id, name in CLASS_NAMES.items():
                    selected = class_map == class_id
                    values = adapted_rgb[selected]
                    plant_colour_counts[name]["pixels"] += len(values)
                    plant_colour_counts[name]["green_dominant_pixels"] += int(
                        (
                            (values[:, 1] > values[:, 0])
                            & (values[:, 1] > values[:, 2])
                        ).sum()
                    )
                if role == "train":
                    update_hsv_histograms(
                        adapted_histograms,
                        adapted_rgb,
                        class_map,
                        stride=sampling_stride,
                    )
                objects, audit, semantic_ids, instance_ids = region_objects_and_truth(
                    mask,
                    minimum_area_px=minimum_area,
                    polygon_epsilon_px=epsilon,
                )
                audit_totals.update(audit)
                polygon_ious.extend(obj.polygon_iou for obj in objects)
                polygon_points.extend(float(len(obj.polygon_xy)) for obj in objects)
                counts[role]["images"] += 1
                counts[role]["weed_regions"] += sum(obj.class_id == 0 for obj in objects)
                counts[role]["crop_regions"] += sum(obj.class_id == 1 for obj in objects)
                destination_image = (
                    partial / "images" / role / f"{role}_{scene}_{stem}.png"
                )
                destination_label = partial / "labels" / role / f"{role}_{scene}_{stem}.txt"
                truth_name = f"{role}_{scene}_{stem}.png"
                semantic_output = partial / "ground_truth/semantics" / role / truth_name
                instance_output = partial / "ground_truth/plant_instances" / role / truth_name
                destination_image.parent.mkdir(parents=True, exist_ok=True)
                destination_label.parent.mkdir(parents=True, exist_ok=True)
                semantic_output.parent.mkdir(parents=True, exist_ok=True)
                instance_output.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(adapted_rgb).save(
                    destination_image, compress_level=3
                )
                lines = [segmentation_label_line(obj, width, height) for obj in objects]
                destination_label.write_text(
                    "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
                )
                Image.fromarray(semantic_ids).save(
                    semantic_output, optimize=True
                )
                Image.fromarray(instance_ids).save(
                    instance_output, optimize=True
                )
                membership_lines.append(
                    json.dumps(
                        {
                            "sample_id": f"{config['dataset_id']}:{role}:{scene}:{stem}",
                            "logical_split": role,
                            "role": role,
                            "scene": scene,
                            "seed": seed,
                            "image_path": str(
                                output / destination_image.relative_to(partial)
                            ),
                            "semantics_path": str(
                                output / semantic_output.relative_to(partial)
                            ),
                            "plant_instances_path": str(
                                output / instance_output.relative_to(partial)
                            ),
                            "source_image": str(image_path),
                            "source_mask": str(mask_path),
                            "appearance_calibrated_from_real_train_only": True,
                            "eligible_instances": len(objects),
                            "eligible_weed_instances": sum(
                                obj.class_id == 0 for obj in objects
                            ),
                            "eligible_crop_instances": sum(
                                obj.class_id == 1 for obj in objects
                            ),
                            "weed_regions": sum(obj.class_id == 0 for obj in objects),
                            "crop_regions": sum(obj.class_id == 1 for obj in objects),
                            "region_proxy_not_botanical_instance": True,
                        },
                        sort_keys=True,
                    )
                )

    observed_frames = sum(row["images"] for row in counts.values())
    if len(visual_index) != observed_frames:
        raise RuntimeError("Visual gate contains missing or duplicate frames")
    seed_sets = list(seeds_by_role.values())
    seeds_disjoint = all(
        not seed_sets[left] & seed_sets[right]
        for left in range(len(seed_sets))
        for right in range(left + 1, len(seed_sets))
    )
    source_hash_sets = list(source_hashes_by_role.values())
    source_hashes_disjoint = all(
        not source_hash_sets[left] & source_hash_sets[right]
        for left in range(len(source_hash_sets))
        for right in range(left + 1, len(source_hash_sets))
    )
    polygon_stats = percentiles(polygon_ious)
    synthetic_appearance_after = histogram_summary(adapted_histograms)
    green_dominant_fraction = {
        name: (
            row["green_dominant_pixels"] / row["pixels"]
            if row["pixels"]
            else 0.0
        )
        for name, row in plant_colour_counts.items()
    }
    minimum_green_dominant = float(
        appearance_cfg["minimum_green_dominant_fraction_per_class"]
    )
    appearance_gap_reduced = all(
        abs(
            synthetic_appearance_after[name][channel]["p50"]
            - reference_appearance[name][channel]["p50"]
        )
        < abs(
            synthetic_appearance_before[name][channel]["p50"]
            - reference_appearance[name][channel]["p50"]
        )
        for name in CLASS_NAMES.values()
        for channel in ("saturation", "value")
    )
    gates = {
        "source_release_passed": True,
        "deploy_visual_gate_passed": True,
        "source_outputs_hash_locked": True,
        "expected_role_counts": all(
            counts[role]["images"] == int(role_rows[role]["expected_pairs"])
            for role in ROLES
        ),
        "scene_seeds_disjoint": seeds_disjoint,
        "source_rgb_and_masks_disjoint": source_hashes_disjoint,
        "polygon_reconstruction_iou_p05": (
            polygon_stats["p05"] is not None and polygon_stats["p05"] >= minimum_p05
        ),
        "appearance_reference_membership_hash_locked": reference_membership_hash_locked,
        "appearance_reference_is_real_train_only": reference_split == "train",
        "appearance_reference_image_count": (
            reference_image_count == expected_reference_images
        ),
        "appearance_synthetic_calibration_image_count": (
            synthetic_calibration_images == counts["train"]["images"]
        ),
        "appearance_median_gap_reduced_for_both_classes": appearance_gap_reduced,
        "appearance_background_pixels_unchanged": background_pixels_unchanged,
        "appearance_green_dominant_fraction_per_class": all(
            fraction >= minimum_green_dominant
            for fraction in green_dominant_fraction.values()
        ),
        "synthetic_real_score_weight_zero": True,
    }
    dataset_yaml = partial / "cropcraft_deploy_segment_proxy_v12.yaml"
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(output),
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "names": {0: "weed", 1: "crop"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    membership = partial / "membership.jsonl"
    membership.write_text("\n".join(membership_lines) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "status": "synthetic_region_proxy_ready_for_bounded_ab_not_real_accuracy_evidence",
        "source_release": str(release),
        "source_release_receipt_sha256": sha256(top_path),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "counts": counts,
        "audit": dict(audit_totals),
        "polygon_reconstruction_iou": polygon_stats,
        "polygon_points": percentiles(polygon_points),
        "appearance_calibration": {
            "method": appearance_cfg["method"],
            "derivation_data": "synthetic_train_and_real_train_only",
            "reference_membership": str(reference_membership),
            "reference_membership_sha256": sha256(reference_membership),
            "reference_split": reference_split,
            "reference_images": reference_image_count,
            "synthetic_calibration_images": synthetic_calibration_images,
            "sampling_stride_px": sampling_stride,
            "blend_fraction": float(appearance_cfg["blend_fraction"]),
            "maximum_saturation": int(appearance_cfg["maximum_saturation"]),
            "minimum_value": int(appearance_cfg["minimum_value"]),
            "minimum_green_dominant_fraction_per_class": minimum_green_dominant,
            "reference_real_train": reference_appearance,
            "synthetic_train_before": synthetic_appearance_before,
            "synthetic_train_after": synthetic_appearance_after,
            "multiplicative_factors": appearance_factors,
            "green_dominant_fraction": green_dominant_fraction,
            "background_pixels_unchanged": background_pixels_unchanged,
            "note": (
                "Moves synthetic plant saturation/value medians halfway toward "
                "the locked real-train medians; it does not use real val/test or "
                "claim physical camera calibration."
            ),
        },
        "label_contract": {
            "classes": {"0": "weed", "1": "crop"},
            "minimum_component_area_px": minimum_area,
            "polygon_approximation_epsilon_px": epsilon,
            "interpretation": "8-connected visible semantic class region proxy",
            "botanical_instance_ids_available": False,
            "intended_metric": "class-union mask and safe interior spot-spray action",
        },
        "evaluation_policy": config["policy"],
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "membership": str(output / "membership.jsonl"),
        "membership_sha256": sha256(membership),
        "images_tree_sha256": tree_sha256(partial / "images"),
        "labels_tree_sha256": tree_sha256(partial / "labels"),
        "ground_truth_tree_sha256": tree_sha256(partial / "ground_truth"),
        "limitations": [
            "Connected regions are not botanical instances and may merge touching plants or split occluded plants.",
            "Synthetic val/test are diagnostic stress sets and have zero weight in real model selection.",
            "Illumination is a renderer proxy and is not calibrated to physical radiometry.",
            "Plant HSV calibration is derived from PhenoBench train and is a conservative appearance bridge, not evidence of botanical realism.",
        ],
    }
    receipt_path = partial / "dataset_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not receipt["all_quality_gates_passed"]:
        failed = [name for name, passed in gates.items() if not passed]
        raise RuntimeError(f"CropCraft packaging gates failed: {failed}; see {receipt_path}")
    partial.replace(output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/cropcraft_deploy_segment_proxy_v12.yaml"),
    )
    parser.add_argument("--source-release", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    run(
        arguments.config,
        source_release=arguments.source_release,
        output_path=arguments.output,
    )


if __name__ == "__main__":
    main()
