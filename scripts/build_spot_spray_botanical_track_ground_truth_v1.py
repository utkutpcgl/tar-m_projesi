#!/usr/bin/env python3
"""Build and validate source-bound CropCraft botanical track ground truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "configs/simulation/spot_spray_botanical_track_ground_truth_v1.yaml"
)
RUNNER = PROJECT_ROOT / "scripts/run_cropcraft.py"
IDENTITY_FORBIDDEN_INPUTS = {
    "semantic_connected_components",
    "model_predictions",
    "rendered_pixel_topology",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def assert_sha256(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise RuntimeError(
            f"{label} SHA256 mismatch: {observed} != {expected}: {path}"
        )


def git_output(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_source_locks(config: dict[str, Any]) -> dict[str, Any]:
    lock = config["source_lock"]
    protocol_path = resolve_path(lock["protocol"]["path"])
    pair_receipt_path = resolve_path(lock["paired_render_receipt"]["path"])
    assert_sha256(protocol_path, lock["protocol"]["sha256"], "protocol")
    assert_sha256(
        pair_receipt_path,
        lock["paired_render_receipt"]["sha256"],
        "paired-render receipt",
    )

    cropcraft = lock["cropcraft"]
    repository = resolve_path(cropcraft["repository"])
    if git_output(repository, "rev-parse", "HEAD") != cropcraft["revision"]:
        raise RuntimeError("Pinned CropCraft revision drift")
    dirty = git_output(repository, "status", "--porcelain", "--untracked-files=no")
    if cropcraft["require_clean_tracked_checkout"] and dirty:
        raise RuntimeError("Pinned CropCraft checkout has tracked modifications")
    for relative, expected in cropcraft["critical_sources"].items():
        assert_sha256(repository / relative, expected, f"CropCraft {relative}")

    for key in ("compatibility_patch", "botanical_gt_patch"):
        row = lock[key]
        assert_sha256(resolve_path(row["path"]), row["sha256"], key)

    v12 = lock["cropcraft_v12_release"]
    v12_receipt_path = resolve_path(v12["receipt"])
    assert_sha256(v12_receipt_path, v12["sha256"], "CropCraft V12 receipt")
    v12_receipt = load_json(v12_receipt_path)
    if (
        v12["require_all_quality_gates_passed"]
        and not v12_receipt.get("all_quality_gates_passed")
    ):
        raise RuntimeError("Pinned CropCraft V12 release did not pass its gates")

    pack = lock["v12_asset_pack"]
    pack_root = resolve_path(pack["root"])
    pack_manifest_path = resolve_path(pack["manifest"])
    assert_sha256(
        pack_manifest_path, pack["manifest_sha256"], "V12 asset pack manifest"
    )
    pack_manifest = load_json(pack_manifest_path)
    if pack["ground_material_id"] not in pack_manifest.get("grounds", []):
        raise RuntimeError("Configured pilot ground is absent from the V12 pack")
    environment = pack_root / pack["environment_relative_path"]
    if not environment.is_file():
        raise FileNotFoundError(f"Missing V12 environment: {environment}")

    runtime = config["runtime"]
    blender = resolve_path(runtime["blender"])
    if not blender.is_file():
        raise FileNotFoundError(f"Missing Blender: {blender}")
    blender_version = subprocess.run(
        [str(blender), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    if not blender_version.startswith(runtime["required_blender_version_prefix"]):
        raise RuntimeError(f"Unexpected Blender version: {blender_version}")

    return {
        "protocol": {"path": str(protocol_path), "sha256": sha256_file(protocol_path)},
        "paired_render_receipt": {
            "path": str(pair_receipt_path),
            "sha256": sha256_file(pair_receipt_path),
        },
        "cropcraft": {
            "repository": str(repository),
            "revision": cropcraft["revision"],
            "tracked_checkout_clean": not bool(dirty),
            "critical_sources": cropcraft["critical_sources"],
        },
        "compatibility_patch": {
            "path": str(resolve_path(lock["compatibility_patch"]["path"])),
            "sha256": lock["compatibility_patch"]["sha256"],
        },
        "botanical_gt_patch": {
            "path": str(resolve_path(lock["botanical_gt_patch"]["path"])),
            "sha256": lock["botanical_gt_patch"]["sha256"],
        },
        "cropcraft_v12_receipt": {
            "path": str(v12_receipt_path),
            "sha256": sha256_file(v12_receipt_path),
            "all_quality_gates_passed": True,
        },
        "v12_asset_pack": {
            "root": str(pack_root),
            "manifest": str(pack_manifest_path),
            "manifest_sha256": sha256_file(pack_manifest_path),
            "inventory_sha256": pack_manifest.get("inventory_sha256"),
        },
        "blender": {"path": str(blender), "version": blender_version},
    }


def build_cropcraft_scene_config(config: dict[str, Any]) -> dict[str, Any]:
    pilot = config["pilot"]
    field = pilot["field"]
    camera = pilot["camera"]
    pack = config["source_lock"]["v12_asset_pack"]
    environment = resolve_path(pack["root"]) / pack["environment_relative_path"]
    return {
        "output_enabled": ["description"],
        "output": {
            "description": {
                "type": "field_description",
                "format": "json",
                "filename": "field_description.json",
            }
        },
        "render": {
            "directory": "render",
            "frames": int(pilot["frame_count"]),
            "samples": int(pilot["render_samples"]),
            "cycles_device": pilot["cycles_device"],
            "resolution_x": int(pilot["resolution_px"][0]),
            "resolution_y": int(pilot["resolution_px"][1]),
            "env_rotation_deg": 0.0,
            "camera": {
                "height": float(camera["height_m"]),
                "fov_deg": float(camera["fov_deg"]),
                "roll_deg": float(camera["roll_deg"]),
                "pitch_deg": float(camera["pitch_deg"]),
                "yaw_deg": float(camera["yaw_deg"]),
                "y_jitter": float(camera["y_jitter_m"]),
            },
            "label_colors": {
                "crop": [0, 255, 0],
                "weed": [255, 0, 0],
                "background": [0, 0, 0],
            },
            "env_path": str(environment),
        },
        "field": {
            "random_seed": int(pilot["seed"]),
            "headland_width": float(field["headland_width_m"]),
            "scattering_extra_width": float(field["scattering_extra_width_m"]),
            "beds": {
                field["bed_name"]: {
                    "plant_type": field["crop_plant_type"],
                    "plant_height": float(field["crop_height_m"]),
                    "height_tolerance_coeff": float(
                        field["crop_height_tolerance_coeff"]
                    ),
                    "plant_distance": float(field["crop_distance_m"]),
                    "bed_width": float(field["bed_width_m"]),
                    "row_distance": float(field["bed_width_m"]),
                    "rows_count": 1,
                    "plants_count": int(field["crop_count"]),
                    "beds_count": 1,
                    "orientation": field["crop_orientation"],
                }
            },
            "noise": {
                "position": float(field["position_noise_m"]),
                "tilt": float(field["tilt_noise_rad"]),
                "scale": float(field["scale_noise"]),
                "missing": 0.0,
            },
            "weeds": {
                field["weed_group_name"]: {
                    "plant_type": field["weed_plant_type"],
                    "max_height": float(field["weed_max_height_m"]),
                    "density": float(field["weed_density"]),
                    "distance_min": float(field["weed_distance_min_m"]),
                    "noise_scale": float(field["weed_noise_scale"]),
                    "noise_offset": float(field["weed_noise_offset"]),
                }
            },
        },
        "botanical_gt_contract": {
            "identity_authority": "pre_render_source_point_attribute",
            "arm_neutral": True,
            "pilot_only": True,
        },
    }


def run_cropcraft_scene(
    config: dict[str, Any], scene_config_path: Path, destination: Path
) -> dict[str, Any]:
    runtime = config["runtime"]
    source = config["source_lock"]
    cropcraft = source["cropcraft"]
    pack = source["v12_asset_pack"]
    command = [
        sys.executable,
        str(RUNNER),
        str(scene_config_path),
        "--output",
        str(destination),
        "--repository",
        str(resolve_path(cropcraft["repository"])),
        "--blender",
        str(resolve_path(runtime["blender"])),
        "--python-environment",
        str(resolve_path(runtime["python_environment"])),
        "--expected-revision",
        cropcraft["revision"],
        "--compatibility-patch",
        str(resolve_path(source["compatibility_patch"]["path"])),
        "--scene-patch",
        str(resolve_path(source["botanical_gt_patch"]["path"])),
        "--asset-pack",
        str(resolve_path(pack["root"])),
        "--ground-material-id",
        pack["ground_material_id"],
    ]
    environment = os.environ.copy()
    environment["CROPCRAFT_BOTANICAL_GT"] = "1"
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-80:])
        raise RuntimeError(f"CropCraft botanical pilot failed:\n{tail}")
    (destination / "runner.stdout.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    receipt = load_json(destination / "generation_receipt.json")
    expected_patch = source["botanical_gt_patch"]["sha256"]
    if receipt.get("scene_patch_sha256") != expected_patch:
        raise RuntimeError("CropCraft receipt did not bind the botanical GT patch")
    return receipt


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}:{line_number}")
        rows.append(value)
    return rows


def _mask(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8) >= 127


def _rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def validate_scene(scene_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    gates = config["quality_gates"]
    gt_root = scene_root / "botanical_ground_truth"
    source_path = gt_root / "source_objects.json"
    registry_path = gt_root / "track_registry.json"
    rows_path = gt_root / "tracks.jsonl"
    source = load_json(source_path)
    registry = load_json(registry_path)
    rows = read_jsonl(rows_path)
    tracks = source.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise RuntimeError("Botanical source registry has no tracks")
    if set(source.get("forbidden_identity_inputs", [])) != IDENTITY_FORBIDDEN_INPUTS:
        raise RuntimeError("Botanical registry did not fail closed on identity inputs")
    if source.get("identity_authority") != "pre-render Geometry Nodes dependency-graph instances":
        raise RuntimeError("Botanical identity was not assigned before rendering")
    observed_identity = canonical_sha256(tracks)
    if source.get("source_scene_graph_identity_sha256") != observed_identity:
        raise RuntimeError("Botanical source scene identity digest mismatch")

    track_ids = [str(row["track_id"]) for row in tracks]
    render_ids = [int(row["render_id"]) for row in tracks]
    if len(set(track_ids)) != len(track_ids) or len(set(render_ids)) != len(render_ids):
        raise RuntimeError("Botanical source IDs or render IDs are not unique")
    if any(float(row.get("canopy_span_mm", 0.0)) <= 0.0 for row in tracks):
        raise RuntimeError("Every botanical track must have positive canopy span")
    field_state_asset_mismatch_count = 0
    for track in tracks:
        if track.get("source_asset_binding_authority") != "depsgraph_instance_object":
            raise RuntimeError("Rendered source geometry authority is ambiguous")
        source = track.get("source", {})
        candidates = source.get("source_asset_candidates")
        if not isinstance(candidates, list) or track.get("source_instance_object") not in candidates:
            raise RuntimeError("Resolved source instance is absent from its source collection")
        if track.get("class_name") == "crop":
            declared = source.get("field_state_declared_asset_filename")
            if not isinstance(declared, str):
                raise RuntimeError("Crop field-state asset declaration is missing")
            observed_match = Path(declared).stem == track["source_instance_object"]
            if source.get("field_state_asset_matches_instance_object") is not observed_match:
                raise RuntimeError("Crop field-state/dependency-graph binding flag is wrong")
            field_state_asset_mismatch_count += int(not observed_match)
    crop_count = sum(row.get("class_name") == "crop" for row in tracks)
    weed_count = sum(row.get("class_name") == "weed" for row in tracks)
    if crop_count < int(gates["minimum_crop_tracks"]):
        raise RuntimeError(f"Too few source crop tracks: {crop_count}")
    if weed_count < int(gates["minimum_weed_tracks"]):
        raise RuntimeError(f"Too few source weed tracks: {weed_count}")

    instance_paths = sorted((gt_root / "instance_masks").glob("frame_*.png"))
    expected_frames = int(gates["exact_frame_count"])
    if len(instance_paths) != expected_frames:
        raise RuntimeError(
            f"Unexpected botanical frame count: {len(instance_paths)} != {expected_frames}"
        )
    frame_ids = [path.stem for path in instance_paths]
    expected_pairs = {(frame, track) for frame in frame_ids for track in track_ids}
    observed_pairs = {(str(row["frame_id"]), str(row["track_id"])) for row in rows}
    if observed_pairs != expected_pairs or len(rows) != len(expected_pairs):
        raise RuntimeError("Track table is not a full frame-by-source-track grid")

    track_by_id = {str(row["track_id"]): row for row in tracks}
    semantic_colors = {
        "crop": np.asarray([0, 255, 0], dtype=np.uint8),
        "weed": np.asarray([255, 0, 0], dtype=np.uint8),
    }
    row_by_pair = {
        (str(row["frame_id"]), str(row["track_id"])): row for row in rows
    }
    visible_subset_passed = True
    class_binding_passed = True
    accounting_passed = True
    palette_passed = True
    allowed_palette = {(0, 0, 0)} | {
        tuple(int(value) for value in track["render_color_rgb"]) for track in tracks
    }
    for instance_path in instance_paths:
        frame = instance_path.stem
        instance = _rgb(instance_path)
        semantic_path = scene_root / "render" / "masks" / f"{frame}.png"
        semantic = _rgb(semantic_path)
        observed_colors = {
            tuple(int(value) for value in color)
            for color in np.unique(instance.reshape(-1, 3), axis=0)
        }
        palette_passed = palette_passed and observed_colors <= allowed_palette
        for track_id in track_ids:
            track = track_by_id[track_id]
            table_row = row_by_pair[(frame, track_id)]
            visible_path = gt_root / str(table_row["visible_mask"])
            isolated_path = gt_root / str(table_row["isolated_mask"])
            visible = _mask(visible_path)
            isolated = _mask(isolated_path)
            if visible.shape != instance.shape[:2] or isolated.shape != visible.shape:
                raise RuntimeError("Botanical mask shape mismatch")
            visible_subset_passed = visible_subset_passed and not bool(
                np.logical_and(visible, ~isolated).any()
            )
            expected_visible = np.all(
                instance
                == np.asarray(track["render_color_rgb"], dtype=np.uint8),
                axis=2,
            )
            accounting_passed = accounting_passed and bool(
                np.array_equal(visible, expected_visible)
                and int(visible.sum()) == int(table_row["visible_pixels"])
                and int(isolated.sum()) == int(table_row["isolated_pixels"])
            )
            class_pixels = np.all(
                semantic == semantic_colors[str(track["class_name"])], axis=2
            )
            class_binding_passed = class_binding_passed and not bool(
                np.logical_and(visible, ~class_pixels).any()
            )

    registry_tracks = registry.get("tracks", [])
    if [row["track_id"] for row in registry_tracks] != track_ids:
        raise RuntimeError("Track registry/source registry ordering drift")
    if int(registry.get("frames_with_source_silhouette_overlap", 0)) < int(
        gates["minimum_frames_with_source_silhouette_overlap"]
    ):
        raise RuntimeError("Pilot has no admitted source silhouette overlap")
    if int(registry.get("occluded_track_frame_rows", 0)) < int(
        gates["minimum_occluded_track_frame_rows"]
    ):
        raise RuntimeError("Pilot has no admitted occlusion row")
    if not visible_subset_passed:
        raise RuntimeError("Visible instance mask escapes its isolated source silhouette")
    if not class_binding_passed:
        raise RuntimeError("Visible source instance mask conflicts with semantic class")
    if not accounting_passed or not palette_passed:
        raise RuntimeError("Visible instance map/table accounting mismatch")

    return {
        "scene_root": str(scene_root),
        "source_scene_graph_identity_sha256": observed_identity,
        "track_count": len(track_ids),
        "crop_track_count": crop_count,
        "weed_track_count": weed_count,
        "field_state_asset_mismatch_count": field_state_asset_mismatch_count,
        "frame_count": len(frame_ids),
        "track_frame_rows": len(rows),
        "frames_with_source_silhouette_overlap": int(
            registry["frames_with_source_silhouette_overlap"]
        ),
        "occluded_track_frame_rows": int(registry["occluded_track_frame_rows"]),
        "fully_occluded_track_frame_rows": int(
            registry["fully_occluded_track_frame_rows"]
        ),
        "quality_gates": {
            "source_identity_digest": True,
            "source_ids_unique": True,
            "render_ids_unique": True,
            "crop_track_minimum": True,
            "weed_track_minimum": True,
            "full_track_frame_grid": True,
            "visible_subset_of_isolated": visible_subset_passed,
            "semantic_class_binding": class_binding_passed,
            "visible_instance_accounting": accounting_passed,
            "instance_palette_closed": palette_passed,
            "source_silhouette_overlap": True,
            "occlusion_exercised": True,
            "positive_canopy_span": True,
            "depsgraph_source_asset_binding": True,
            "field_state_asset_disagreement_explicit": True,
        },
    }


def inventory(root: Path, *, include_logs: bool = False) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (not include_logs and path.suffix == ".log"):
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def ground_truth_inventory(scene_root: Path) -> list[dict[str, Any]]:
    rows = inventory(scene_root / "botanical_ground_truth")
    semantic_root = scene_root / "render" / "masks"
    rows.extend(
        {
            "path": f"semantic_masks/{path.name}",
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(semantic_root.glob("frame_*.png"))
    )
    return sorted(rows, key=lambda row: row["path"])


def compare_replay(primary: Path, replay: Path) -> dict[str, Any]:
    primary_inventory = ground_truth_inventory(primary)
    replay_inventory = ground_truth_inventory(replay)
    if primary_inventory != replay_inventory:
        primary_map = {row["path"]: row["sha256"] for row in primary_inventory}
        replay_map = {row["path"]: row["sha256"] for row in replay_inventory}
        mismatches = sorted(
            path
            for path in set(primary_map) | set(replay_map)
            if primary_map.get(path) != replay_map.get(path)
        )
        raise RuntimeError(f"Determinism replay mismatch: {mismatches[:20]}")
    return {
        "byte_identical": True,
        "file_count": len(primary_inventory),
        "inventory_sha256": canonical_sha256(primary_inventory),
        "files": primary_inventory,
    }


def copy_ground_truth_package(primary: Path, destination: Path) -> None:
    shutil.copytree(primary / "botanical_ground_truth", destination)
    semantic_destination = destination / "semantic_masks"
    semantic_destination.mkdir()
    for path in sorted((primary / "render" / "masks").glob("frame_*.png")):
        shutil.copy2(path, semantic_destination / path.name)


def create_arm_packages(
    primary: Path, release_root: Path, config: dict[str, Any]
) -> dict[str, Any]:
    canonical_root = release_root / "canonical_gt"
    copy_ground_truth_package(primary, canonical_root)
    base_inventory = inventory(canonical_root)
    trajectory_identity = canonical_sha256(
        {
            "frame_count": config["pilot"]["frame_count"],
            "resolution_px": config["pilot"]["resolution_px"],
            "camera": config["pilot"]["camera"],
            "field_end_x_m": (
                (config["pilot"]["field"]["crop_count"] - 1)
                * config["pilot"]["field"]["crop_distance_m"]
            ),
        }
    )
    source = load_json(canonical_root / "source_objects.json")
    manifest = {
        "schema_version": 1,
        "arm_neutral": True,
        "identity_authority": "pre_render_geometry_nodes_dependency_graph_instance",
        "source_scene_graph_identity_sha256": source[
            "source_scene_graph_identity_sha256"
        ],
        "trajectory_identity_sha256": trajectory_identity,
        "ground_truth_inventory_sha256": canonical_sha256(base_inventory),
        "ground_truth_files": base_inventory,
    }
    write_json(canonical_root / "ground_truth_manifest.json", manifest)

    arm_roots = {}
    for arm in ("ideal", "degraded"):
        arm_root = release_root / "arms" / arm / "gt"
        shutil.copytree(canonical_root, arm_root)
        arm_roots[arm] = arm_root
    ideal_inventory = inventory(arm_roots["ideal"])
    degraded_inventory = inventory(arm_roots["degraded"])
    if ideal_inventory != degraded_inventory:
        raise RuntimeError("Ideal/degraded botanical GT packages are not byte-identical")
    return {
        "byte_identical": True,
        "trajectory_identity_sha256": trajectory_identity,
        "source_scene_graph_identity_sha256": source[
            "source_scene_graph_identity_sha256"
        ],
        "file_count_per_arm": len(ideal_inventory),
        "inventory_sha256": canonical_sha256(ideal_inventory),
        "ideal_root": str(arm_roots["ideal"]),
        "degraded_root": str(arm_roots["degraded"]),
    }


def ensure_safe_replace_target(path: Path, expected_relative: str) -> None:
    expected = resolve_path(expected_relative)
    allowed = {
        "data/synthetic/cropcraft/spot_spray_botanical_track_ground_truth_v1",
        "docs/results/spot_spray_botanical_track_ground_truth_v1",
    }
    normalized = Path(expected_relative).as_posix().rstrip("/")
    if path.resolve() != expected or normalized not in allowed:
        raise RuntimeError(f"Refusing unsafe output replacement: {path}")


def write_readme(
    path: Path,
    receipt: dict[str, Any],
) -> None:
    primary = receipt["primary_validation"]
    content = f"""# CropCraft botanical track ground truth V1

Status: **{receipt['status']}**

This is a deterministic, synthetic-only protocol-admission pilot. It proves
source-bound botanical identity and occlusion accounting; it is not the native
2048 px benchmark release, physical capture evidence, or field/product approval.

- Source tracks: {primary['track_count']} ({primary['crop_track_count']} crop, {primary['weed_track_count']} weed)
- Frames: {primary['frame_count']}
- Track-frame rows: {primary['track_frame_rows']}
- Frames with overlapping isolated silhouettes: {primary['frames_with_source_silhouette_overlap']}
- Occluded track-frame rows: {primary['occluded_track_frame_rows']}
- Field-state/actual source-object disagreements recorded: {primary['field_state_asset_mismatch_count']}
- Determinism replay byte-identical: {str(receipt['determinism_replay']['byte_identical']).lower()}
- Ideal/degraded GT byte-identical: {str(receipt['paired_arm_ground_truth']['byte_identical']).lower()}

Identity is assigned from CropCraft bed points and Geometry Nodes dependency-
graph instances before rendering. Semantic connected components, model
predictions, and rendered pixel topology are explicitly forbidden as identity
inputs.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build(config_path: Path, replace: bool) -> dict[str, Any]:
    config = load_yaml(config_path)
    source_evidence = validate_source_locks(config)
    release_root = resolve_path(config["outputs"]["release_root"])
    results_root = resolve_path(config["outputs"]["results_root"])
    ensure_safe_replace_target(release_root, config["outputs"]["release_root"])
    ensure_safe_replace_target(results_root, config["outputs"]["results_root"])
    existing = [path for path in (release_root, results_root) if path.exists()]
    if existing and not replace:
        raise FileExistsError(
            "Outputs already exist; pass --replace for these exact lane paths: "
            + ", ".join(str(path) for path in existing)
        )
    if replace:
        for path in existing:
            shutil.rmtree(path)
    release_root.mkdir(parents=True)
    results_root.mkdir(parents=True)

    scene_config = build_cropcraft_scene_config(config)
    scene_config_path = release_root / "pilot_scene_config.yaml"
    scene_config_path.write_text(
        yaml.safe_dump(scene_config, sort_keys=False), encoding="utf-8"
    )
    primary = release_root / config["outputs"]["primary_scene"]
    replay = release_root / config["outputs"]["replay_scene"]
    primary_generation = run_cropcraft_scene(config, scene_config_path, primary)
    replay_generation = run_cropcraft_scene(config, scene_config_path, replay)
    primary_validation = validate_scene(primary, config)
    replay_validation = validate_scene(replay, config)
    determinism = compare_replay(primary, replay)
    paired = create_arm_packages(primary, release_root, config)

    config_hash = sha256_file(config_path)
    scene_config_hash = sha256_file(scene_config_path)
    protocol_capabilities = {
        "persistent_source_object_ids": True,
        "stable_per_frame_gt_tracks": True,
        "visible_polygons_or_masks": True,
        "canopy_span_mm": True,
        "visibility_and_occlusion": True,
        "native_2048_square_rgb": {
            "pilot_executed": False,
            "renderer_path_parameterized": True,
            "required_for_full_benchmark_release": True,
        },
    }
    all_gates = {
        **{f"primary_{key}": value for key, value in primary_validation["quality_gates"].items()},
        **{f"replay_{key}": value for key, value in replay_validation["quality_gates"].items()},
        "source_locks": True,
        "determinism_replay_byte_identical": determinism["byte_identical"],
        "ideal_degraded_gt_byte_identical": paired["byte_identical"],
        "source_identity_matches_replay": (
            primary_validation["source_scene_graph_identity_sha256"]
            == replay_validation["source_scene_graph_identity_sha256"]
        ),
        "native_benchmark_resolution_not_claimed": not config["claim_boundary"][
            "pilot_resolution_is_native_benchmark_resolution"
        ],
    }
    if not all(all_gates.values()):
        failed = [name for name, passed in all_gates.items() if not passed]
        raise RuntimeError(f"Botanical GT admission failed: {failed}")
    receipt = {
        "schema_version": 1,
        "study_id": config["study_id"],
        "status": "PASS_PROTOCOL_ADMISSION_PILOT_SYNTHETIC_ONLY",
        "config": str(config_path),
        "config_sha256": config_hash,
        "scene_config": str(scene_config_path),
        "scene_config_sha256": scene_config_hash,
        "source_evidence": source_evidence,
        "primary_generation_receipt": {
            "path": str(primary / "generation_receipt.json"),
            "sha256": sha256_file(primary / "generation_receipt.json"),
            "scene_patch_sha256": primary_generation["scene_patch_sha256"],
        },
        "replay_generation_receipt": {
            "path": str(replay / "generation_receipt.json"),
            "sha256": sha256_file(replay / "generation_receipt.json"),
            "scene_patch_sha256": replay_generation["scene_patch_sha256"],
        },
        "primary_validation": primary_validation,
        "replay_validation": replay_validation,
        "determinism_replay": determinism,
        "paired_arm_ground_truth": paired,
        "protocol_admission_capabilities": protocol_capabilities,
        "quality_gates": all_gates,
        "all_quality_gates_passed": True,
        "claim_boundary": config["claim_boundary"],
    }
    receipt_path = results_root / "validation_receipt.json"
    write_json(receipt_path, receipt)
    package = {
        "schema_version": 1,
        "study_id": config["study_id"],
        "validation_receipt": str(receipt_path),
        "validation_receipt_sha256": sha256_file(receipt_path),
        "release_inventory": inventory(release_root),
    }
    package["release_inventory_sha256"] = canonical_sha256(
        package["release_inventory"]
    )
    write_json(results_root / "package_manifest.json", package)
    write_readme(results_root / "README.md", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--validate-only",
        help="Validate an existing CropCraft pilot scene directory and print JSON",
    )
    args = parser.parse_args()
    config_path = resolve_path(args.config)
    config = load_yaml(config_path)
    if args.validate_only:
        result = validate_scene(resolve_path(args.validate_only), config)
    else:
        result = build(config_path, args.replace)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
