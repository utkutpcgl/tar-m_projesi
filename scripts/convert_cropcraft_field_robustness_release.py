#!/usr/bin/env python3
"""Convert split-aware CropCraft roles to one common-ontology manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import BACKGROUND, CROP, WEED
from agri_seg.manifest import SampleRecord, validate_records, write_manifest
from agri_seg.prepare import _save_common_mask


ROLES = ("train", "val", "test")
COLOUR_MAPPING = {
    (0, 0, 0): BACKGROUND,
    (0, 255, 0): CROP,
    (255, 0, 0): WEED,
}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".json"
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def common_mask(path: Path) -> np.ndarray:
    with Image.open(path) as handle:
        raw = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    common = np.full(raw.shape[:2], 255, dtype=np.uint8)
    known = np.zeros(raw.shape[:2], dtype=bool)
    for colour, label in COLOUR_MAPPING.items():
        selected = np.all(raw == np.asarray(colour, dtype=np.uint8), axis=2)
        common[selected] = label
        known |= selected
    if not np.all(known):
        unexpected = np.unique(raw[~known].reshape(-1, 3), axis=0)
        raise ValueError(f"Unexpected mask colours in {path}: {unexpected[:10].tolist()}")
    return common


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--dataset-id", default="cropcraft_field_robustness_pilot_v10_r1"
    )
    arguments = parser.parse_args()
    release = Path(arguments.release).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    report_path = output.with_name(f"{output.stem}_conversion.json")
    if output.exists() or report_path.exists():
        raise FileExistsError(output if output.exists() else report_path)

    top_path = release / "release_receipt.json"
    top = load_object(top_path)
    if top.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Top-level release did not pass")
    if float(top.get("real_model_selection_score_weight", -1)) != 0.0:
        raise RuntimeError("Synthetic model-selection weight must be exactly zero")
    visual_path = release / "visual_review_receipt.json"
    visual = load_object(visual_path)
    if visual.get("passed") is not True:
        raise RuntimeError("Visual/radiometric gate did not pass")
    if visual["release_receipt_sha256"] != sha256(top_path):
        raise RuntimeError("Visual receipt locks a different top-level release")
    resolved_study_path = Path(top["resolved_study"]).resolve()
    if sha256(resolved_study_path) != top["resolved_study_sha256"]:
        raise RuntimeError("Resolved study changed after generation")
    study = load_object(resolved_study_path)
    metadata = study.get("manifest_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Resolved study has no manifest_metadata mapping")
    dataset_id = str(arguments.dataset_id)
    normalized_root = data_root / "processed" / dataset_id / "common_masks"
    temporary_root = normalized_root.with_name(normalized_root.name + ".partial")
    if normalized_root.exists() or temporary_root.exists():
        raise FileExistsError(normalized_root if normalized_root.exists() else temporary_root)

    visual_index = {
        (row["role"], row["scene"], row["frame"]): row
        for row in visual["frame_radiometry"]
    }
    top_roles = {row["role"]: row for row in top["roles"]}
    if set(top_roles) != set(ROLES):
        raise RuntimeError("Expected exactly train/val/test top-level roles")
    records: list[SampleRecord] = []
    class_pixels_by_split: dict[str, Counter[str]] = {
        role: Counter() for role in ROLES
    }
    role_sources: dict[str, Any] = {}
    observed_seeds: dict[str, list[int]] = {}
    for role in ROLES:
        role_row = top_roles[role]
        role_root = Path(role_row["output"]).resolve()
        if role_root != (release / "roles" / role).resolve():
            raise RuntimeError(f"Unexpected {role} output path in receipt")
        role_receipt_path = role_root / "release_receipt.json"
        role_receipt = load_object(role_receipt_path)
        if sha256(role_receipt_path) != role_row["receipt_sha256"]:
            raise RuntimeError(f"{role} receipt hash changed")
        role_study_path = Path(role_row["study"]).resolve()
        role_study = load_object(role_study_path)
        if sha256(role_study_path) != role_row["study_sha256"]:
            raise RuntimeError(f"{role} study hash changed")
        if role_study.get("synthetic_role") != role:
            raise RuntimeError(f"{role} role marker mismatch")
        if role_receipt["copied_study_sha256"] != sha256(
            role_root / "study.input.yaml"
        ):
            raise RuntimeError(f"{role} immutable study copy mismatch")
        scene_count = int(role_study["scene_count"])
        frames_per_scene = int(role_study["frames_per_scene"])
        expected_pairs = int(role_row["expected_pairs"])
        if scene_count * frames_per_scene != expected_pairs:
            raise RuntimeError(f"{role} expected pair arithmetic mismatch")
        seeds: list[int] = []
        for scene_index in range(scene_count):
            scene = f"scene_{scene_index:04d}"
            scene_root = role_root / "scenes" / scene
            config_path = role_root / "scene_configs" / f"{scene}.yaml"
            config = load_object(config_path)
            receipt_path = scene_root / "generation_receipt.json"
            scene_receipt = load_object(receipt_path)
            if sha256(config_path) != scene_receipt["config_sha256"]:
                raise RuntimeError(f"Scene config mismatch: {role}/{scene}")
            seed = int(config["field"]["random_seed"])
            seeds.append(seed)
            crop_bed_name = str(role_study["crop_bed_name"])
            bed = config["field"]["beds"][crop_bed_name]
            if str(bed["plant_type"]) != str(role_study["crop_plant_type"]):
                raise RuntimeError(f"Crop plant type mismatch: {role}/{scene}")
            crop_height = float(bed["plant_height"])
            images = {
                path.stem: path
                for path in sorted((scene_root / "render/images").glob("*.jpg"))
            }
            masks = {
                path.stem: path
                for path in sorted((scene_root / "render/masks").glob("*.png"))
            }
            if set(images) != set(masks) or len(images) != frames_per_scene:
                raise RuntimeError(f"RGB/mask pairing mismatch: {role}/{scene}")
            for stem in sorted(images):
                lock = visual_index.get((role, scene, stem))
                if lock is None:
                    raise RuntimeError(f"Visual receipt lacks frame: {role}/{scene}/{stem}")
                if sha256(images[stem]) != lock["rgb_sha256"]:
                    raise RuntimeError(f"RGB changed after visual gate: {role}/{scene}/{stem}")
                if sha256(masks[stem]) != lock["mask_sha256"]:
                    raise RuntimeError(f"Mask changed after visual gate: {role}/{scene}/{stem}")
                mask = common_mask(masks[stem])
                for name, label in (
                    ("background", BACKGROUND),
                    ("target_crop", CROP),
                    ("other_vegetation", WEED),
                ):
                    class_pixels_by_split[role][name] += int((mask == label).sum())
                final_mask = normalized_root / role / scene / f"{stem}.png"
                partial_mask = temporary_root / role / scene / f"{stem}.png"
                _save_common_mask(mask, partial_mask)
                records.append(
                    SampleRecord(
                        sample_id=f"{dataset_id}:{role}:{scene}:{stem}",
                        image_path=relative(images[stem], data_root),
                        mask_path=relative(final_mask, data_root),
                        split=role,
                        dataset_id=dataset_id,
                        field_id=f"synthetic_{role}_{scene}",
                        session_id=f"seed_{seed}",
                        capture_date="synthetic",
                        platform=str(metadata["platform"]),
                        sensor=str(metadata["sensor"]),
                        target_crop_id=int(metadata["target_crop_id"]),
                        crop_species=str(metadata["crop_species"]),
                        weed_species_optional=str(metadata["weed_species_optional"]),
                        growth_stage=(
                            f"{metadata['growth_stage_prefix']}_{crop_height:.3f}m_{role}"
                        ),
                        annotation_exhaustive=bool(metadata["annotation_exhaustive"]),
                        license_status=str(metadata["license_status"]),
                        commercial_allowed=bool(metadata["commercial_allowed"]),
                    )
                )
        if seeds != [int(value) for value in role_row["seeds"]]:
            raise RuntimeError(f"{role} seed list differs from top receipt")
        observed_seeds[role] = seeds
        role_sources[role] = {
            "release_receipt": str(role_receipt_path),
            "release_receipt_sha256": sha256(role_receipt_path),
            "role_study": str(role_study_path),
            "role_study_sha256": sha256(role_study_path),
            "scenes": scene_count,
            "frames": expected_pairs,
        }

    if len({seed for values in observed_seeds.values() for seed in values}) != sum(
        len(values) for values in observed_seeds.values()
    ):
        raise RuntimeError("Scene seed leakage across synthetic roles")
    if len(visual_index) != len(records):
        raise RuntimeError("Visual receipt contains unconverted or duplicate frames")
    validate_records(records)
    temporary_root.replace(normalized_root)
    write_manifest(records, output)
    split_counts = Counter(record.split for record in records)
    expected_counts = {
        role: int(top_roles[role]["expected_pairs"]) for role in ROLES
    }
    gates = {
        "top_generation_gate_passed": True,
        "visual_and_radiometric_gate_passed": True,
        "all_source_frames_hash_locked": True,
        "common_ontology_exact": True,
        "role_counts_match": dict(split_counts) == expected_counts,
        "scene_seeds_disjoint": True,
        "asset_families_disjoint": top["asset_contract"]["passed"] is True,
        "manifest_group_leakage_check": True,
        "synthetic_val_test_are_diagnostic_only": True,
        "real_model_selection_score_weight_zero": True,
    }
    report = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "release": str(release),
        "release_receipt_sha256": sha256(top_path),
        "visual_review_receipt_sha256": sha256(visual_path),
        "resolved_study_sha256": sha256(resolved_study_path),
        "manifest": str(output),
        "manifest_sha256": sha256(output),
        "normalized_masks": str(normalized_root),
        "samples": len(records),
        "split_counts": dict(split_counts),
        "class_pixels_by_split": {
            role: dict(values) for role, values in class_pixels_by_split.items()
        },
        "ontology": {
            "background": 0,
            "target_crop": 1,
            "other_vegetation": 2,
            "ignore": 255,
        },
        "role_sources": role_sources,
        "role_seeds": observed_seeds,
        "asset_contract": top["asset_contract"],
        "evaluation_policy": {
            "train_role_allowed_for_challenger_training": True,
            "synthetic_val_role": "diagnostic_stress_only",
            "synthetic_test_role": "diagnostic_stress_only",
            "real_model_selection_score_weight": 0.0,
            "may_replace_real_validation_or_test": False,
        },
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not report["all_quality_gates_passed"]:
        raise RuntimeError(f"Conversion gates failed; see {report_path}")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
