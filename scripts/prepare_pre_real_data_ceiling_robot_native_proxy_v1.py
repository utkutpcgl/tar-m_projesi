#!/usr/bin/env python3
"""Build the matched PhenoBench plus native-detail ROSE robot proxy dataset."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_cropcraft_deploy_segment_proxy_v12 import (
    percentiles,
    region_objects_and_truth,
)
from scripts.prepare_phenobench_cropcraft_deploy_ab_v1 import (
    hardlink_pair,
    sha256,
    tree_sha256,
)
from scripts.prepare_phenobench_detect_segment_fair_v1 import (
    segmentation_label_line,
)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def candidate_origins(width: int, height: int, tile_size: int) -> list[tuple[int, int]]:
    if tile_size <= 0 or tile_size > width or tile_size > height:
        raise ValueError("Tile size must fit inside the source raster")
    xs = sorted({0, (width - tile_size) // 2, width - tile_size})
    ys = sorted({0, (height - tile_size) // 2, height - tile_size})
    return [(x, y) for y in ys for x in xs]


def choose_native_window(
    semantics: np.ndarray,
    *,
    tile_size: int,
    minimum_crop_pixels: int,
    minimum_weed_pixels: int,
) -> dict[str, int] | None:
    if semantics.ndim != 2 or not set(np.unique(semantics).tolist()) <= {0, 1, 2}:
        raise ValueError("Expected common semantics with background=0,crop=1,weed=2")
    height, width = semantics.shape
    rows: list[dict[str, int]] = []
    for x, y in candidate_origins(width, height, tile_size):
        view = semantics[y : y + tile_size, x : x + tile_size]
        crop_pixels = int((view == 1).sum())
        weed_pixels = int((view == 2).sum())
        rows.append(
            {
                "x": x,
                "y": y,
                "crop_pixels": crop_pixels,
                "weed_pixels": weed_pixels,
            }
        )
    eligible = [
        row
        for row in rows
        if row["crop_pixels"] >= minimum_crop_pixels
        and row["weed_pixels"] >= minimum_weed_pixels
    ]
    if not eligible:
        return None
    # Training-only hard-example crop: maximize weed evidence, then crop safety
    # evidence. Coordinate tie-breaks make the choice stable.
    return max(
        eligible,
        key=lambda row: (
            row["weed_pixels"],
            row["crop_pixels"],
            -row["y"],
            -row["x"],
        ),
    )


def stratified_sample(
    eligible: Mapping[str, Sequence[dict[str, Any]]],
    quotas: Mapping[str, int],
    *,
    seed: int,
) -> list[dict[str, Any]]:
    if set(eligible) != set(quotas):
        raise ValueError("Eligible session groups and quota groups differ")
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for session in sorted(quotas):
        rows = sorted(eligible[session], key=lambda row: str(row["sample_id"]))
        quota = int(quotas[session])
        if quota <= 0 or len(rows) < quota:
            raise ValueError(f"Insufficient eligible rows for {session}: {len(rows)} < {quota}")
        selected.extend(rng.sample(rows, quota))
    return sorted(selected, key=lambda row: str(row["sample_id"]))


def _lock(path: Path, expected: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Locked input mismatch: {path}")


def _semantic_rgb(semantics: np.ndarray) -> np.ndarray:
    rgb = np.zeros((*semantics.shape, 3), dtype=np.uint8)
    rgb[semantics == 1] = (0, 255, 0)
    rgb[semantics == 2] = (255, 0, 0)
    return rgb


def run(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(PROJECT_ROOT, config["data_root"])
    pheno = config["phenobench"]
    robot = config["robot_proxy"]
    pheno_root = resolve(data_root, pheno["dataset_root"])
    pheno_receipt_path = resolve(data_root, pheno["dataset_receipt"])
    pheno_yaml = resolve(data_root, pheno["dataset_yaml"])
    robot_manifest = resolve(data_root, robot["manifest"])
    robot_receipt = resolve(data_root, robot["conversion_receipt"])
    leakage_audit = resolve(data_root, config["bonirob_leakage_lock"]["audit"])
    reference_checkpoint = resolve(data_root, config["matched_reference"]["checkpoint"])
    synthetic_receipt = resolve(data_root, config["matched_reference"]["synthetic_receipt"])
    for path, expected in (
        (pheno_receipt_path, str(pheno["dataset_receipt_sha256"])),
        (pheno_yaml, str(pheno["dataset_yaml_sha256"])),
        (robot_manifest, str(robot["manifest_sha256"])),
        (robot_receipt, str(robot["conversion_receipt_sha256"])),
        (leakage_audit, str(config["bonirob_leakage_lock"]["audit_sha256"])),
        (reference_checkpoint, str(config["matched_reference"]["checkpoint_sha256"])),
        (synthetic_receipt, str(config["matched_reference"]["synthetic_receipt_sha256"])),
    ):
        _lock(path, expected)
    leakage = json.loads(leakage_audit.read_text(encoding="utf-8"))
    if leakage.get("passed") is not True or int(leakage["candidate_to_reference_match_count"]) != 0:
        raise RuntimeError("BoniRob-to-prior-real duplicate lock did not pass")
    if int(config["matched_reference"]["extra_train_images"]) != sum(
        int(value) for value in robot["session_quotas"].values()
    ):
        raise RuntimeError("Robot proxy count does not match the current winner's supplement count")

    real_images = sorted(path for path in (pheno_root / "images/train").glob("*") if path.is_file())
    if len(real_images) != int(pheno["expected_train_images"]):
        raise RuntimeError("PhenoBench train count drift")

    with robot_manifest.open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))
    quotas = {str(key): int(value) for key, value in robot["session_quotas"].items()}
    eligible: dict[str, list[dict[str, Any]]] = defaultdict(list)
    audited_candidates = 0
    for row in manifest_rows:
        if (
            row["split"] != str(robot["required_split"])
            or row["crop_species"] != str(robot["required_crop_species"])
            or not row["platform"].startswith(str(robot["required_platform_prefix"]))
            or row["session_id"] not in quotas
        ):
            continue
        image_path = resolve(data_root, row["image_path"])
        mask_path = resolve(data_root, row["mask_path"])
        if not image_path.is_file() or not mask_path.is_file():
            raise FileNotFoundError(f"Incomplete ROSE pair: {image_path}")
        with Image.open(image_path) as handle:
            width, height = handle.size
        expected_raster = tuple(
            int(value)
            for value in robot["source_raster_px_by_session"][row["session_id"]]
        )
        if (width, height) != expected_raster:
            raise RuntimeError(f"ROSE source raster drift: {image_path}: {(width, height)}")
        with Image.open(mask_path) as handle:
            semantics = np.asarray(handle, dtype=np.uint8)
        window = choose_native_window(
            semantics,
            tile_size=int(robot["tile_size_px"]),
            minimum_crop_pixels=int(robot["minimum_crop_pixels_per_tile"]),
            minimum_weed_pixels=int(robot["minimum_weed_pixels_per_tile"]),
        )
        audited_candidates += 1
        if window is not None:
            eligible[row["session_id"]].append(
                {
                    **row,
                    "source_image_path": str(image_path),
                    "source_mask_path": str(mask_path),
                    "window": window,
                }
            )
    selected = stratified_sample(eligible, quotas, seed=int(robot["selection_seed"]))

    output = resolve(data_root, config["output"])
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output if output.exists() else partial)
    partial.mkdir(parents=True, exist_ok=False)
    membership: list[dict[str, Any]] = []
    for image in real_images:
        destination = partial / "images/train" / f"phenobench_{image.name}"
        hardlink_pair(image, destination)
        membership.append(
            {
                "kind": "phenobench_unique_train",
                "source_image": str(image),
                "output_image": str(output / destination.relative_to(partial)),
            }
        )

    tile_size = int(robot["tile_size_px"])
    minimum_area = int(robot["minimum_component_area_px"])
    epsilon = float(robot["polygon_approximation_epsilon_px"])
    polygon_ious: list[float] = []
    audit_totals: Counter[str] = Counter()
    class_region_counts = {"weed": 0, "crop": 0}
    selected_rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        source_image = Path(row["source_image_path"])
        source_mask = Path(row["source_mask_path"])
        window = row["window"]
        x, y = int(window["x"]), int(window["y"])
        with Image.open(source_image) as handle:
            rgb = handle.convert("RGB").crop((x, y, x + tile_size, y + tile_size))
        with Image.open(source_mask) as handle:
            semantics = np.asarray(handle, dtype=np.uint8)[y : y + tile_size, x : x + tile_size]
        objects, audit, semantic_ids, instance_ids = region_objects_and_truth(
            _semantic_rgb(semantics),
            minimum_area_px=minimum_area,
            polygon_epsilon_px=epsilon,
        )
        audit_totals.update(audit)
        polygon_ious.extend(float(obj.polygon_iou) for obj in objects)
        class_region_counts["weed"] += sum(obj.class_id == 0 for obj in objects)
        class_region_counts["crop"] += sum(obj.class_id == 1 for obj in objects)
        stem = f"rose_native_{index:04d}"
        image_output = partial / "images/train" / f"{stem}.png"
        label_output = partial / "labels/train" / f"{stem}.txt"
        semantic_output = partial / "ground_truth/semantics" / f"{stem}.png"
        instance_output = partial / "ground_truth/plant_instances" / f"{stem}.png"
        for path in (image_output, label_output, semantic_output, instance_output):
            path.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(image_output, compress_level=3)
        label_output.write_text(
            "\n".join(segmentation_label_line(obj, tile_size, tile_size) for obj in objects)
            + ("\n" if objects else ""),
            encoding="utf-8",
        )
        Image.fromarray(semantic_ids).save(semantic_output, optimize=True)
        Image.fromarray(instance_ids).save(instance_output, optimize=True)
        selection_row = {
            "sample_id": row["sample_id"],
            "session_id": row["session_id"],
            "platform": row["platform"],
            "crop_species": row["crop_species"],
            "source_split": row["split"],
            "source_image": str(source_image),
            "source_image_sha256": sha256(source_image),
            "source_mask": str(source_mask),
            "source_mask_sha256": sha256(source_mask),
            "native_window_xywh": [x, y, tile_size, tile_size],
            "crop_pixels": int(window["crop_pixels"]),
            "weed_pixels": int(window["weed_pixels"]),
            "eligible_crop_regions": sum(obj.class_id == 1 for obj in objects),
            "eligible_weed_regions": sum(obj.class_id == 0 for obj in objects),
            "output_image": str(output / image_output.relative_to(partial)),
            "output_label": str(output / label_output.relative_to(partial)),
            "region_proxy_not_botanical_instance": True,
        }
        selected_rows.append(selection_row)
        membership.append({"kind": "rose_native_robot_proxy_train", **selection_row})

    dataset_yaml = partial / "pre_real_data_ceiling_robot_native_proxy_v1.yaml"
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(output),
                "train": "images/train",
                "val": str((pheno_root / "images/val").resolve()),
                "test": str((pheno_root / "images/test").resolve()),
                "names": {0: "weed", 1: "crop"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    membership_path = partial / "membership.jsonl"
    membership_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in membership) + "\n",
        encoding="utf-8",
    )
    polygon_stats = percentiles(polygon_ious)
    session_counts = Counter(str(row["session_id"]) for row in selected_rows)
    train_images = sorted((partial / "images/train").glob("*"))
    train_labels = sorted((partial / "labels/train").glob("*.txt"))
    gates = {
        "rose_train_only": all(row["source_split"] == "train" for row in selected_rows),
        "rose_val_test_never_selected": not any(row["split"] != "train" for row in selected),
        "session_quotas_exact": dict(sorted(session_counts.items())) == dict(sorted(quotas.items())),
        "unique_robot_source_frames": len({row["sample_id"] for row in selected_rows}) == len(selected_rows),
        "native_pixels_no_resize": all(row["native_window_xywh"][2:] == [tile_size, tile_size] for row in selected_rows),
        "every_tile_has_crop_and_weed": all(
            row["crop_pixels"] >= int(robot["minimum_crop_pixels_per_tile"])
            and row["weed_pixels"] >= int(robot["minimum_weed_pixels_per_tile"])
            for row in selected_rows
        ),
        "matched_extra_exposure_count": len(selected_rows) == int(config["matched_reference"]["extra_train_images"]),
        "all_phenobench_train_retained": len(real_images) == int(pheno["expected_train_images"]),
        "matched_total_train_exposure": len(train_images) == len(real_images) + len(selected_rows) == 1487,
        "image_label_pairs_complete": len(train_images) == len(train_labels),
        "both_proxy_classes_present": all(value > 0 for value in class_region_counts.values()),
        "polygon_reconstruction_iou_p05": float(polygon_stats["p05"] or 0.0)
        >= float(robot["minimum_polygon_reconstruction_iou_p05"]),
        "bonirob_duplicate_audit_locked_and_clear": leakage.get("passed") is True
        and int(leakage["candidate_to_reference_match_count"]) == 0,
    }
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "matched_real_robot_native_proxy_dataset_ready",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "inputs": {
            "phenobench_receipt": {"path": str(pheno_receipt_path), "sha256": sha256(pheno_receipt_path)},
            "phenobench_yaml": {"path": str(pheno_yaml), "sha256": sha256(pheno_yaml)},
            "rose_manifest": {"path": str(robot_manifest), "sha256": sha256(robot_manifest)},
            "rose_conversion_receipt": {"path": str(robot_receipt), "sha256": sha256(robot_receipt)},
            "bonirob_leakage_audit": {"path": str(leakage_audit), "sha256": sha256(leakage_audit)},
            "matched_reference_checkpoint": {"path": str(reference_checkpoint), "sha256": sha256(reference_checkpoint)},
            "matched_reference_synthetic_receipt": {"path": str(synthetic_receipt), "sha256": sha256(synthetic_receipt)},
        },
        "selection": {
            "audited_train_candidates": audited_candidates,
            "eligible_by_session": {key: len(value) for key, value in sorted(eligible.items())},
            "seed": int(robot["selection_seed"]),
            "session_quotas": quotas,
            "selected": selected_rows,
        },
        "counts": {
            "phenobench_unique_train": len(real_images),
            "rose_native_robot_proxy_train": len(selected_rows),
            "train_images_per_epoch": len(train_images),
            "proxy_regions": class_region_counts,
            "audit": dict(audit_totals),
        },
        "native_detail_contract": {
            "source_raster_px_by_session": robot["source_raster_px_by_session"],
            "tile_raster_px": [tile_size, tile_size],
            "resized": False,
            "label_informed_train_crop": True,
        },
        "polygon_reconstruction_iou": polygon_stats,
        "dataset_yaml": str(output / dataset_yaml.relative_to(partial)),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "membership": str(output / membership_path.relative_to(partial)),
        "membership_sha256": sha256(membership_path),
        "train_label_tree_sha256": tree_sha256(partial / "labels/train"),
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "claims": config["claims"],
        "limitations": [
            "ROSE crops contain Phaseolus rather than the target sugar beet crop.",
            "Connected semantic regions can merge touching plants or split occluded plants.",
            "Training-only mask-informed crops enrich visible weed/crop evidence and do not isolate viewpoint from content enrichment.",
            "ROSE is research-only for this project and cannot define a commercial deployment checkpoint.",
        ],
    }
    receipt_path = partial / "dataset_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not receipt["all_quality_gates_passed"]:
        failed = [name for name, passed in gates.items() if not passed]
        raise RuntimeError(f"Dataset gates failed: {failed}; see {receipt_path}")
    partial.replace(output)
    print(json.dumps({"status": receipt["status"], "output": str(output), "counts": receipt["counts"], "gates": gates}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/pre_real_data_ceiling_robot_native_proxy_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
