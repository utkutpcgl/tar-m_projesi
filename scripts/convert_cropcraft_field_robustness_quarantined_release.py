#!/usr/bin/env python3
"""Convert a generated CropCraft release after objective train quarantine.

This path is intentionally narrower than the ordinary converter.  It is only
valid when manual alignment/plausibility passed, the full release failed fixed
radiometry thresholds, every violating frame belongs to train, and no more
than 2.5% of train is removed.  Validation and test are never filtered.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agri_seg.manifest import SampleRecord, validate_records, write_manifest
from agri_seg.prepare import _save_common_mask
from scripts.convert_cropcraft_field_robustness_release import (
    ROLES,
    common_mask,
    load_object,
    relative,
    sha256,
)


MAX_TRAIN_QUARANTINE_FRACTION = 0.025


def violation_reasons(
    row: dict[str, Any], thresholds: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    if float(row["mean_all_channels"]) < float(
        thresholds["minimum_frame_mean_brightness"]
    ):
        reasons.append("mean_brightness_below_minimum")
    if float(row["mean_all_channels"]) > float(
        thresholds["maximum_frame_mean_brightness"]
    ):
        reasons.append("mean_brightness_above_maximum")
    if float(row["all_channels_ge_250_fraction"]) > float(
        thresholds["maximum_fully_clipped_white_fraction_per_frame"]
    ):
        reasons.append("fully_clipped_white_above_limit")
    if float(row["all_channels_le_5_fraction"]) > float(
        thresholds["maximum_fully_clipped_black_fraction_per_frame"]
    ):
        reasons.append("fully_clipped_black_above_limit")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--dataset-id", default="cropcraft_field_robustness_pilot_v11_r2q"
    )
    arguments = parser.parse_args()
    release = Path(arguments.release).expanduser().resolve()
    data_root = Path(arguments.data_root).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    report_path = output.with_name(f"{output.stem}_conversion.json")
    dataset_id = str(arguments.dataset_id)
    normalized_root = data_root / "processed" / dataset_id / "common_masks"
    temporary_root = normalized_root.with_name(normalized_root.name + ".partial")
    for candidate in (output, report_path, normalized_root, temporary_root):
        if candidate.exists():
            raise FileExistsError(candidate)

    top_path = release / "release_receipt.json"
    visual_path = release / "visual_review_receipt.json"
    top = load_object(top_path)
    visual = load_object(visual_path)
    if top.get("all_quality_gates_passed") is not True:
        raise RuntimeError("Generation release did not pass")
    if float(top.get("real_model_selection_score_weight", -1)) != 0.0:
        raise RuntimeError("Synthetic real-score weight must be zero")
    if visual.get("passed") is not False or visual.get("manual_verdict") != "pass":
        raise RuntimeError("Expected automatic radiometry failure after manual pass")
    if visual.get("release_receipt_sha256") != sha256(top_path):
        raise RuntimeError("Visual receipt locks a different generation release")
    permitted_false_gates = {
        "frame_mean_brightness_in_range",
        "fully_clipped_white_below_limit",
        "fully_clipped_black_below_limit",
    }
    false_gates = {
        str(name)
        for name, passed in visual["quality_gates"].items()
        if passed is not True
    }
    if not false_gates or not false_gates <= permitted_false_gates:
        raise RuntimeError(f"Visual failure is not quarantine-eligible: {false_gates}")

    thresholds = visual["radiometry_thresholds"]
    visual_rows = {
        (str(row["role"]), str(row["scene"]), str(row["frame"])): row
        for row in visual["frame_radiometry"]
    }
    violating = {
        key: violation_reasons(row, thresholds)
        for key, row in visual_rows.items()
        if violation_reasons(row, thresholds)
    }
    if not violating or {key[0] for key in violating} != {"train"}:
        raise RuntimeError("Only non-empty train-only quarantine is allowed")
    train_frame_count = sum(key[0] == "train" for key in visual_rows)
    if len(violating) / train_frame_count > MAX_TRAIN_QUARANTINE_FRACTION:
        raise RuntimeError("Train quarantine exceeds the frozen 2.5% cap")

    resolved_study_path = Path(top["resolved_study"]).resolve()
    if sha256(resolved_study_path) != top["resolved_study_sha256"]:
        raise RuntimeError("Resolved study changed after generation")
    study = load_object(resolved_study_path)
    metadata = study.get("manifest_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Resolved study has no manifest metadata")
    top_roles = {str(row["role"]): row for row in top["roles"]}
    if set(top_roles) != set(ROLES):
        raise RuntimeError("Expected exactly train/val/test roles")

    records: list[SampleRecord] = []
    role_counts: Counter[str] = Counter()
    class_pixels: dict[str, Counter[str]] = {
        role: Counter() for role in ROLES
    }
    profile_frame_counts: dict[str, Counter[str]] = {
        role: Counter() for role in ROLES
    }
    observed_keys: set[tuple[str, str, str]] = set()
    quarantined_rows: list[dict[str, Any]] = []
    observed_seeds: dict[str, list[int]] = {}
    role_sources: dict[str, Any] = {}

    for role in ROLES:
        role_row = top_roles[role]
        role_root = Path(role_row["output"]).resolve()
        if role_root != (release / "roles" / role).resolve():
            raise RuntimeError(f"Unexpected role root: {role}")
        role_receipt_path = role_root / "release_receipt.json"
        role_study_path = Path(role_row["study"]).resolve()
        if sha256(role_receipt_path) != role_row["receipt_sha256"]:
            raise RuntimeError(f"Role receipt changed: {role}")
        if sha256(role_study_path) != role_row["study_sha256"]:
            raise RuntimeError(f"Role study changed: {role}")
        role_study = load_object(role_study_path)
        seeds: list[int] = []
        for scene_index in range(int(role_study["scene_count"])):
            scene = f"scene_{scene_index:04d}"
            scene_root = role_root / "scenes" / scene
            config_path = role_root / "scene_configs" / f"{scene}.yaml"
            config = load_object(config_path)
            scene_receipt = load_object(scene_root / "generation_receipt.json")
            if sha256(config_path) != scene_receipt["config_sha256"]:
                raise RuntimeError(f"Scene config changed: {role}/{scene}")
            seed = int(config["field"]["random_seed"])
            seeds.append(seed)
            crop_bed_name = str(role_study["crop_bed_name"])
            bed = config["field"]["beds"][crop_bed_name]
            crop_height = float(bed["plant_height"])
            profile = str(
                config["agri_asset_profile"]["correlated_scene_profile"]
            )
            images = {
                path.stem: path
                for path in sorted((scene_root / "render/images").glob("*.jpg"))
            }
            masks = {
                path.stem: path
                for path in sorted((scene_root / "render/masks").glob("*.png"))
            }
            if set(images) != set(masks):
                raise RuntimeError(f"RGB/mask mismatch: {role}/{scene}")
            for frame in sorted(images):
                key = (role, scene, frame)
                observed_keys.add(key)
                lock = visual_rows.get(key)
                if lock is None:
                    raise RuntimeError(f"Missing visual lock: {key}")
                if sha256(images[frame]) != lock["rgb_sha256"]:
                    raise RuntimeError(f"RGB hash changed: {key}")
                if sha256(masks[frame]) != lock["mask_sha256"]:
                    raise RuntimeError(f"Mask hash changed: {key}")
                if key in violating:
                    quarantined_rows.append(
                        {
                            "role": role,
                            "scene": scene,
                            "frame": frame,
                            "profile": profile,
                            "reasons": violating[key],
                            "rgb": str(images[frame]),
                            "rgb_sha256": lock["rgb_sha256"],
                            "mask": str(masks[frame]),
                            "mask_sha256": lock["mask_sha256"],
                        }
                    )
                    continue
                mask = common_mask(masks[frame])
                for name, label in (
                    ("background", 0),
                    ("target_crop", 1),
                    ("other_vegetation", 2),
                ):
                    class_pixels[role][name] += int((mask == label).sum())
                final_mask = normalized_root / role / scene / f"{frame}.png"
                _save_common_mask(
                    mask, temporary_root / role / scene / f"{frame}.png"
                )
                records.append(
                    SampleRecord(
                        sample_id=f"{dataset_id}:{role}:{scene}:{frame}",
                        image_path=relative(images[frame], data_root),
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
                        weed_species_optional=str(
                            metadata["weed_species_optional"]
                        ),
                        growth_stage=(
                            f"{metadata['growth_stage_prefix']}_{crop_height:.3f}m_{role}"
                        ),
                        annotation_exhaustive=bool(
                            metadata["annotation_exhaustive"]
                        ),
                        license_status=str(metadata["license_status"]),
                        commercial_allowed=bool(metadata["commercial_allowed"]),
                    )
                )
                role_counts[role] += 1
                profile_frame_counts[role][profile] += 1
        if seeds != [int(value) for value in role_row["seeds"]]:
            raise RuntimeError(f"Seed list changed: {role}")
        observed_seeds[role] = seeds
        role_sources[role] = {
            "release_receipt": str(role_receipt_path),
            "release_receipt_sha256": sha256(role_receipt_path),
            "role_study": str(role_study_path),
            "role_study_sha256": sha256(role_study_path),
        }

    if observed_keys != set(visual_rows):
        raise RuntimeError("Visual receipt and generated frame set differ")
    if {tuple(row[key] for key in ("role", "scene", "frame")) for row in quarantined_rows} != set(violating):
        raise RuntimeError("Quarantine differs from objective violation set")
    expected_counts = {"train": 78, "val": 16, "test": 16}
    if dict(role_counts) != expected_counts:
        raise RuntimeError(f"Unexpected retained role counts: {dict(role_counts)}")
    if any(max(values.values()) - min(values.values()) > 1 for values in profile_frame_counts.values()):
        raise RuntimeError("Profile frame balance changed beyond one frame")
    all_seeds = [seed for values in observed_seeds.values() for seed in values]
    if len(all_seeds) != len(set(all_seeds)):
        raise RuntimeError("Scene seeds overlap across roles")

    validate_records(records)
    temporary_root.replace(normalized_root)
    write_manifest(records, output)
    gates = {
        "generation_release_passed": True,
        "manual_rgb_mask_alignment_and_plausibility_passed": True,
        "only_fixed_radiometry_failures_quarantined": True,
        "quarantine_is_train_only": True,
        "train_quarantine_fraction_within_2_5_percent": True,
        "all_val_test_frames_retained": True,
        "retained_profile_frame_counts_balanced": True,
        "all_source_frames_hash_locked": True,
        "common_ontology_exact": True,
        "scene_seeds_disjoint": True,
        "synthetic_val_test_diagnostic_only": True,
        "real_model_selection_score_weight_zero": True,
    }
    report = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "source_release": str(release),
        "source_release_receipt_sha256": sha256(top_path),
        "source_visual_receipt_sha256": sha256(visual_path),
        "source_release_visual_gate_passed": False,
        "derived_quarantined_dataset_accepted": all(gates.values()),
        "manifest": str(output),
        "manifest_sha256": sha256(output),
        "normalized_masks": str(normalized_root),
        "samples": len(records),
        "split_counts": dict(role_counts),
        "profile_frame_counts": {
            role: dict(values) for role, values in profile_frame_counts.items()
        },
        "class_pixels_by_split": {
            role: dict(values) for role, values in class_pixels.items()
        },
        "quarantine_policy": {
            "source": "pre-existing fixed visual/radiometry thresholds",
            "maximum_train_fraction": MAX_TRAIN_QUARANTINE_FRACTION,
            "observed_train_fraction": len(quarantined_rows) / train_frame_count,
            "validation_or_test_filtering_allowed": False,
        },
        "quarantined_frames": quarantined_rows,
        "radiometry_thresholds": thresholds,
        "role_sources": role_sources,
        "role_seeds": observed_seeds,
        "evaluation_policy": {
            "train_role_allowed_for_challenger_training": True,
            "synthetic_val_test_role": "diagnostic_stress_only",
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
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
