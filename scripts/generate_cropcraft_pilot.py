#!/usr/bin/env python3
"""Generate independent, pinned CropCraft scenes for a bounded pilot."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts/run_cropcraft.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return payload


def sampled(rng: random.Random, ranges: dict[str, Any], name: str) -> float:
    bounds = ranges.get(name)
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or float(bounds[0]) > float(bounds[1])
    ):
        raise ValueError(f"Invalid range {name!r}: {bounds!r}")
    return round(rng.uniform(float(bounds[0]), float(bounds[1])), 6)


def scene_config(
    base: dict[str, Any],
    study: dict[str, Any],
    scene_index: int,
    asset_pack: Path | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(base)
    ranges = study["ranges"]
    if not isinstance(ranges, dict):
        raise ValueError("Study ranges must be an object")
    seed = int(study["base_seed"]) + scene_index
    rng = random.Random(seed)
    result["output_enabled"] = ["description"]
    result["render"]["frames"] = int(study["frames_per_scene"])
    result["render"]["env_rotation_deg"] = sampled(
        rng, ranges, "environment_rotation_deg"
    )
    camera = result["render"]["camera"]
    for output_name, range_name in (
        ("height", "camera_height_m"),
        ("fov_deg", "camera_fov_deg"),
        ("roll_deg", "camera_roll_deg"),
        ("pitch_deg", "camera_pitch_deg"),
        ("yaw_deg", "camera_yaw_deg"),
        ("y_jitter", "camera_y_jitter_m"),
    ):
        camera[output_name] = sampled(rng, ranges, range_name)

    field = result["field"]
    field["random_seed"] = seed
    crop_bed_name = str(study.get("crop_bed_name", "maize_rows"))
    bed = field["beds"][crop_bed_name]
    expected_plant_type = study.get("crop_plant_type")
    if expected_plant_type is not None and bed.get("plant_type") != expected_plant_type:
        raise ValueError(
            f"Base crop plant type does not match study: "
            f"{bed.get('plant_type')} != {expected_plant_type}"
        )
    asset_heights = ranges.get("crop_asset_heights_m")
    if not isinstance(asset_heights, list) or not asset_heights:
        raise ValueError("crop_asset_heights_m must be a non-empty array")
    asset_height = float(
        asset_heights[scene_index % len(asset_heights)]
        if study.get("cycle_crop_asset_heights", False)
        else rng.choice(asset_heights)
    )
    bed["plant_height"] = round(
        asset_height * sampled(rng, ranges, "crop_height_scale"), 6
    )
    if "camera_height_crop_ratio" in ranges:
        height_bounds = ranges["camera_height_m"]
        ratio = sampled(rng, ranges, "camera_height_crop_ratio")
        camera["height"] = round(
            min(
                float(height_bounds[1]),
                max(float(height_bounds[0]), asset_height * ratio),
            ),
            6,
        )
    for output_name, range_name in (
        ("height_tolerance_coeff", "crop_height_tolerance"),
        ("plant_distance", "within_row_spacing_m"),
        ("row_distance", "between_row_spacing_m"),
    ):
        bed[output_name] = sampled(rng, ranges, range_name)
    noise = field["noise"]
    for output_name, range_name in (
        ("position", "position_noise_m"),
        ("tilt", "tilt_noise_rad"),
        ("scale", "scale_noise"),
        ("missing", "missing_crop_probability"),
    ):
        noise[output_name] = sampled(rng, ranges, range_name)
    weed_density_ranges = study.get(
        "weed_density_ranges",
        {
            "broadleaf_low": "portulaca_density",
            "broadleaf_tall": "polygonum_density",
            "rosette": "taraxacum_density",
        },
    )
    if not isinstance(weed_density_ranges, dict):
        raise ValueError("weed_density_ranges must be a mapping")
    for weed_name, range_name in weed_density_ranges.items():
        field["weeds"][weed_name]["density"] = sampled(rng, ranges, range_name)
    weed_height_ratio_ranges = study.get("weed_max_height_crop_ratios", {})
    if not isinstance(weed_height_ratio_ranges, dict):
        raise ValueError("weed_max_height_crop_ratios must be a mapping")
    weed_height_floors = study.get("weed_max_height_floors_m", {})
    weed_height_caps = study.get("weed_max_height_caps_m", {})
    if not isinstance(weed_height_floors, dict) or not isinstance(
        weed_height_caps, dict
    ):
        raise ValueError("weed max-height floors and caps must be mappings")
    for weed_name, range_name in weed_height_ratio_ranges.items():
        if weed_name not in field["weeds"]:
            raise ValueError(f"Unknown staged weed family: {weed_name}")
        ratio = sampled(rng, ranges, str(range_name))
        value = float(bed["plant_height"]) * ratio
        if weed_name in weed_height_floors:
            value = max(value, float(weed_height_floors[weed_name]))
        if weed_name in weed_height_caps:
            value = min(value, float(weed_height_caps[weed_name]))
        field["weeds"][weed_name]["max_height"] = round(value, 6)
    field["stones"]["density"] = sampled(rng, ranges, "stone_density")
    if asset_pack is not None:
        profile = study.get("asset_profile")
        if not isinstance(profile, dict):
            raise ValueError("Asset-pack studies require asset_profile")
        ground_ids = profile.get("ground_material_ids")
        environment_files = profile.get("environment_files")
        if not isinstance(ground_ids, list) or not ground_ids:
            raise ValueError("asset_profile.ground_material_ids must be non-empty")
        if not isinstance(environment_files, list) or not environment_files:
            raise ValueError("asset_profile.environment_files must be non-empty")
        ground_id = str(ground_ids[scene_index % len(ground_ids)])
        environment_file = str(
            environment_files[(scene_index * 2 + 1) % len(environment_files)]
        )
        environment_path = (asset_pack / "environments" / environment_file).resolve()
        if not environment_path.is_file():
            raise FileNotFoundError(environment_path)
        result["render"]["env_path"] = str(environment_path)
        result["agri_asset_profile"] = {
            "pack": str(asset_pack),
            "ground_material_id": ground_id,
            "environment_file": environment_file,
        }
        surface_profile = profile.get("surface_profile")
        if surface_profile is not None:
            result["agri_asset_profile"]["surface_profile"] = str(surface_profile)
        parameter_ranges = profile.get("surface_parameter_ranges", {})
        if not isinstance(parameter_ranges, dict):
            raise ValueError(
                "asset_profile.surface_parameter_ranges must be a mapping"
            )
        surface_parameters: dict[str, float] = {}
        for parameter_name, range_name in sorted(parameter_ranges.items()):
            surface_parameters[str(parameter_name)] = sampled(
                rng, ranges, str(range_name)
            )
        if surface_parameters:
            result["agri_asset_profile"]["surface_parameters"] = surface_parameters
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("study")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    study_path = Path(args.study).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    study = load_yaml(study_path)
    base_path = PROJECT_ROOT / str(study["base_config"])
    base = load_yaml(base_path)
    asset_pack: Path | None = None
    if study.get("asset_pack") is not None:
        candidate = Path(str(study["asset_pack"])).expanduser()
        asset_pack = (
            candidate.resolve()
            if candidate.is_absolute()
            else (PROJECT_ROOT / candidate).resolve()
        )
        pack_manifest = asset_pack / "PACK.json"
        if not pack_manifest.is_file():
            raise FileNotFoundError(pack_manifest)
        pack_payload = json.loads(pack_manifest.read_text(encoding="utf-8"))
        expected_pack_id = study.get("asset_pack_id")
        if expected_pack_id and pack_payload.get("pack_id") != expected_pack_id:
            raise ValueError(
                f"Asset pack ID mismatch: {pack_payload.get('pack_id')} "
                f"!= {expected_pack_id}"
            )
    scene_count = int(study["scene_count"])
    if scene_count <= 0 or int(study["frames_per_scene"]) <= 0:
        raise ValueError("scene_count and frames_per_scene must be positive")
    if int(study["train_scenes"]) + int(study["validation_scenes"]) != scene_count:
        raise ValueError("Train and validation scene counts must cover the pilot")

    configs_root = destination / "scene_configs"
    scenes_root = destination / "scenes"
    logs_root = destination / "launcher_logs"
    configs_root.mkdir(parents=True, exist_ok=False)
    scenes_root.mkdir()
    logs_root.mkdir()
    copied_study = destination / "study.input.yaml"
    copied_study.write_bytes(study_path.read_bytes())
    started_at = datetime.now(timezone.utc)
    scene_receipts: list[dict[str, Any]] = []
    class_pixels = {"background": 0, "crop": 0, "weed": 0}
    crop_free_frames = 0
    weed_free_frames = 0
    total_frames = 0
    crop_model_filenames: set[str] = set()
    used_ground_materials: set[str] = set()
    used_environments: set[str] = set()
    used_surface_profiles: set[str] = set()
    surface_parameter_values: dict[str, list[float]] = {}
    weed_max_height_values: dict[str, list[float]] = {}
    rgb_hash_frames: dict[str, list[str]] = {}
    mask_hash_scenes: dict[str, set[str]] = {}

    for scene_index in range(scene_count):
        scene_name = f"scene_{scene_index:04d}"
        config_path = configs_root / f"{scene_name}.yaml"
        config = scene_config(base, study, scene_index, asset_pack)
        for weed_name, weed in config["field"].get("weeds", {}).items():
            weed_max_height_values.setdefault(str(weed_name), []).append(
                float(weed["max_height"])
            )
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        scene_output = scenes_root / scene_name
        command = [
            sys.executable,
            str(RUNNER),
            str(config_path),
            "--output",
            str(scene_output),
        ]
        if asset_pack is not None:
            profile = config["agri_asset_profile"]
            command.extend(
                [
                    "--asset-pack",
                    str(asset_pack),
                    "--ground-material-id",
                    str(profile["ground_material_id"]),
                ]
            )
            scene_patch = study.get("scene_patch")
            if scene_patch is not None:
                patch_candidate = Path(str(scene_patch)).expanduser()
                patch_path = (
                    patch_candidate.resolve()
                    if patch_candidate.is_absolute()
                    else (PROJECT_ROOT / patch_candidate).resolve()
                )
                if not patch_path.is_file():
                    raise FileNotFoundError(patch_path)
                command.extend(["--scene-patch", str(patch_path)])
            used_ground_materials.add(str(profile["ground_material_id"]))
            used_environments.add(str(profile["environment_file"]))
            if profile.get("surface_profile") is not None:
                used_surface_profiles.add(str(profile["surface_profile"]))
            for name, value in profile.get("surface_parameters", {}).items():
                surface_parameter_values.setdefault(str(name), []).append(float(value))
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        (logs_root / f"{scene_name}.stdout.log").write_text(
            result.stdout, encoding="utf-8"
        )
        (logs_root / f"{scene_name}.stderr.log").write_text(
            result.stderr, encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{scene_name} failed with {result.returncode}:\n"
                + "\n".join(result.stderr.splitlines()[-30:])
            )
        receipt_path = scene_output / "generation_receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        validation = receipt["validation"]
        for name, count in validation["class_pixels"].items():
            class_pixels[name] += int(count)
        for frame in validation["per_frame"]:
            total_frames += 1
            crop_free_frames += int(frame["class_pixels"]["crop"] == 0)
            weed_free_frames += int(frame["class_pixels"]["weed"] == 0)
        description_path = scene_output / "field_description.json"
        description = json.loads(description_path.read_text(encoding="utf-8"))
        for bed_state in description.get("field", {}).get("beds", []):
            for row_state in bed_state.get("rows", []):
                for crop in row_state.get("crops", []):
                    filename = crop.get("filename")
                    if filename:
                        crop_model_filenames.add(str(filename))
        rgb_paths = sorted(scene_output.glob("render/images/*.jpg"))
        mask_paths = sorted(scene_output.glob("render/masks/*.png"))
        if len(rgb_paths) != int(study["frames_per_scene"]):
            raise RuntimeError(f"Incomplete rgb set: {scene_name}")
        if len(mask_paths) != int(study["frames_per_scene"]):
            raise RuntimeError(f"Incomplete mask set: {scene_name}")
        for path in rgb_paths:
            rgb_hash_frames.setdefault(sha256(path), []).append(
                f"{scene_name}/{path.name}"
            )
        for path in mask_paths:
            mask_hash_scenes.setdefault(sha256(path), set()).add(scene_name)
        scene_receipts.append(
            {
                "scene": scene_name,
                "seed": int(config["field"]["random_seed"]),
                "config_sha256": sha256(config_path),
                "receipt_sha256": sha256(receipt_path),
                "validated_pairs": int(validation["validated_pairs"]),
            }
        )
        print(
            f"{scene_name}: {validation['validated_pairs']} pairs validated",
            flush=True,
        )

    gates = study["quality_gates"]
    expected_pairs = int(gates["expected_pairs"])
    crop_free_fraction = crop_free_frames / total_frames
    weed_free_fraction = weed_free_frames / total_frames
    total_pixels = sum(class_pixels.values())
    mean_crop_fraction = class_pixels["crop"] / total_pixels
    mean_weed_fraction = class_pixels["weed"] / total_pixels
    exact_rgb_duplicates = sum(
        max(0, len(frames) - 1) for frames in rgb_hash_frames.values()
    )
    exact_mask_duplicates_across_scenes = sum(
        max(0, len(scenes) - 1) for scenes in mask_hash_scenes.values()
    )
    gate_results = {
        "expected_pairs": total_frames == expected_pairs,
        "unique_seeds": len({item["seed"] for item in scene_receipts}) == scene_count,
        "crop_free_frame_fraction": (
            crop_free_fraction
            <= float(gates["max_crop_free_frame_fraction"])
        ),
        "weed_free_frame_fraction": (
            weed_free_fraction
            <= float(gates["max_weed_free_frame_fraction"])
        ),
    }
    optional_checks = {
        "exact_rgb_duplicates": exact_rgb_duplicates
        <= int(gates.get("max_exact_rgb_duplicates", exact_rgb_duplicates)),
        "exact_mask_duplicates_across_scenes": exact_mask_duplicates_across_scenes
        <= int(
            gates.get(
                "max_exact_mask_duplicates_across_scenes",
                exact_mask_duplicates_across_scenes,
            )
        ),
        "mean_crop_fraction_min": mean_crop_fraction
        >= float(gates.get("minimum_mean_crop_fraction", mean_crop_fraction)),
        "mean_crop_fraction_max": mean_crop_fraction
        <= float(gates.get("maximum_mean_crop_fraction", mean_crop_fraction)),
        "mean_weed_fraction_min": mean_weed_fraction
        >= float(gates.get("minimum_mean_weed_fraction", mean_weed_fraction)),
        "mean_weed_fraction_max": mean_weed_fraction
        <= float(gates.get("maximum_mean_weed_fraction", mean_weed_fraction)),
        "used_crop_model_variants": len(crop_model_filenames)
        >= int(gates.get("minimum_used_crop_model_variants", 0)),
        "used_ground_families": len(used_ground_materials)
        >= int(gates.get("minimum_used_ground_families", 0)),
        "used_environment_families": len(used_environments)
        >= int(gates.get("minimum_used_environment_families", 0)),
        "used_surface_profiles": len(used_surface_profiles)
        >= int(gates.get("minimum_used_surface_profiles", 0)),
        "scene_disjoint_split": (
            set(range(int(study["train_scenes"])))
            .isdisjoint(set(range(int(study["train_scenes"]), scene_count)))
        ),
    }
    required_parameter_spans = gates.get("minimum_surface_parameter_spans", {})
    if not isinstance(required_parameter_spans, dict):
        raise ValueError("minimum_surface_parameter_spans must be a mapping")
    for name, minimum_span in sorted(required_parameter_spans.items()):
        values = surface_parameter_values.get(str(name), [])
        observed_span = max(values) - min(values) if values else 0.0
        optional_checks[f"surface_parameter_span_{name}"] = (
            observed_span >= float(minimum_span)
        )
    gate_results.update(optional_checks)
    receipt = {
        "schema_version": 1,
        "release": study["release"],
        "purpose": study["purpose"],
        "pilot_generator": str(Path(__file__).resolve()),
        "pilot_generator_sha256": sha256(Path(__file__).resolve()),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "study": str(study_path),
        "study_sha256": sha256(study_path),
        "copied_study_sha256": sha256(copied_study),
        "base_config": str(base_path),
        "base_config_sha256": sha256(base_path),
        "scenes": scene_receipts,
        "scene_count": scene_count,
        "frames": total_frames,
        "class_pixels": class_pixels,
        "crop_free_frames": crop_free_frames,
        "weed_free_frames": weed_free_frames,
        "crop_free_frame_fraction": crop_free_fraction,
        "weed_free_frame_fraction": weed_free_fraction,
        "mean_crop_fraction": mean_crop_fraction,
        "mean_weed_fraction": mean_weed_fraction,
        "crop_model_filenames": sorted(crop_model_filenames),
        "used_ground_materials": sorted(used_ground_materials),
        "used_environments": sorted(used_environments),
        "used_surface_profiles": sorted(used_surface_profiles),
        "surface_parameter_values": {
            name: values for name, values in sorted(surface_parameter_values.items())
        },
        "weed_max_height_values": {
            name: values for name, values in sorted(weed_max_height_values.items())
        },
        "exact_rgb_duplicates": exact_rgb_duplicates,
        "exact_mask_duplicates_across_scenes": exact_mask_duplicates_across_scenes,
        "asset_pack": (
            None
            if asset_pack is None
            else {
                "path": str(asset_pack),
                "pack_id": pack_payload.get("pack_id"),
                "manifest_sha256": sha256(asset_pack / "PACK.json"),
                "inventory_sha256": pack_payload.get("inventory_sha256"),
            }
        ),
        "quality_gates": gate_results,
        "all_quality_gates_passed": all(gate_results.values()),
        "limitations": (
            [
                "stock low-poly maize morphology",
                "small stock weed asset library",
                "one bundled soil material and one environment family",
                "bundled asset licenses are not itemized separately upstream",
            ]
            if asset_pack is None
            else [
                "procedural morphology is an approximation, not a botanical scan",
                "CropCraft uses a simple pinhole camera without measured sensor response",
                "wind, wet leaves, disease, and motion blur are not modeled",
                "downstream benefit must pass the frozen real-development A/B gate",
            ]
        ),
    }
    receipt_path = destination / "release_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"Pilot quality gates failed; see {receipt_path}")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
