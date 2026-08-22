from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from scripts.build_spot_spray_botanical_track_ground_truth_v1 import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    build_cropcraft_scene_config,
    canonical_sha256,
    compare_replay,
    inventory,
    load_yaml,
    sha256_file,
    validate_scene,
    validate_source_locks,
)


CONFIG_PATH = DEFAULT_CONFIG


def load_config() -> dict:
    value = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def release_root(config: dict) -> Path:
    return PROJECT_ROOT / config["outputs"]["release_root"]


def results_root(config: dict) -> Path:
    return PROJECT_ROOT / config["outputs"]["results_root"]


def primary_scene(config: dict) -> Path:
    return release_root(config) / config["outputs"]["primary_scene"]


def replay_scene(config: dict) -> Path:
    return release_root(config) / config["outputs"]["replay_scene"]


def test_config_is_source_native_synthetic_only_and_outcome_agnostic() -> None:
    config = load_config()
    boundary = config["claim_boundary"]
    identity = config["identity_contract"]
    assert config["status"] == "PROTOCOL_ADMISSION_PILOT_SYNTHETIC_ONLY"
    assert boundary["benchmark_release"] is False
    assert boundary["pilot_resolution_is_native_benchmark_resolution"] is False
    assert boundary["model_inference_performed"] is False
    assert boundary["outcome_targeting_performed"] is False
    assert boundary["field_go"] is False
    assert boundary["chemical_fire_allowed"] is False
    assert identity["assignment_time"] == "before_first_rgb_or_label_render"
    assert identity["weed_identity_source"] == (
        "geometry_nodes_depsgraph_persistent_instance_id"
    )
    assert set(identity["forbidden_identity_inputs"]) == {
        "semantic_connected_components",
        "model_predictions",
        "rendered_pixel_topology",
    }
    assert config["pilot"]["resolution_px"] != config["pilot"][
        "benchmark_native_resolution_px"
    ]


def test_pinned_sources_validate_and_patch_applies_after_compatibility(
    tmp_path: Path,
) -> None:
    config = load_config()
    state = validate_source_locks(config)
    assert state["cropcraft"]["tracked_checkout_clean"] is True
    assert state["cropcraft"]["revision"] == (
        "7128cd2acade50cc4a5a1761210b55989ab62527"
    )
    assert state["protocol"]["sha256"] == (
        "de12cd76d3f497f1ea3a6ffa1d1c7fc8eea4e70a9af218c2769bae81da0f329f"
    )
    assert state["paired_render_receipt"]["sha256"] == (
        "179410f6f975e1b7b43c369839ea3b58f74e6eb2ccc667dc4e64127b5ce7d5b3"
    )

    repository = Path(state["cropcraft"]["repository"])
    archive = tmp_path / "source.tar"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar",
            f"--output={archive}",
            state["cropcraft"]["revision"],
        ],
        check=True,
    )
    with tarfile.open(archive) as handle:
        handle.extractall(checkout, filter="data")
    for key in ("compatibility_patch", "botanical_gt_patch"):
        subprocess.run(
            [
                "patch",
                "--batch",
                "--forward",
                "-d",
                str(checkout),
                "-p1",
                "-i",
                state[key]["path"],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    module = (checkout / "core/botanical_gt.py").read_text(encoding="utf-8")
    compile(module, "core/botanical_gt.py", "exec")
    assert "depsgraph.object_instances" in module
    assert "persistent_id" in module
    assert "ndimage" not in module
    assert "connected_components(" not in module
    entrypoint = (checkout / "core/blender_entrypoint.py").read_text(
        encoding="utf-8"
    )
    assert entrypoint.index("materialize_source_plants") < entrypoint.index(
        "setup_camera_animation"
    )


def test_scene_config_uses_v12_species_and_a_moving_camera() -> None:
    config = load_config()
    scene = build_cropcraft_scene_config(config)
    field = scene["field"]
    bed = field["beds"][config["pilot"]["field"]["bed_name"]]
    weed = field["weeds"][config["pilot"]["field"]["weed_group_name"]]
    assert bed["plant_type"] == "sorghum_seedling_v2"
    assert weed["plant_type"] == "weed_broadleaf_v2"
    assert bed["plants_count"] == 4
    assert bed["plant_distance"] > 0
    assert scene["render"]["frames"] == 4
    assert scene["botanical_gt_contract"]["arm_neutral"] is True


def test_actual_pilot_has_complete_source_tracks_class_binding_and_occlusion() -> None:
    config = load_config()
    result = validate_scene(primary_scene(config), config)
    assert result["track_count"] == 5
    assert result["crop_track_count"] == 4
    assert result["weed_track_count"] == 1
    assert result["frame_count"] == 4
    assert result["track_frame_rows"] == 20
    assert result["frames_with_source_silhouette_overlap"] == 4
    assert result["occluded_track_frame_rows"] >= 1
    assert result["field_state_asset_mismatch_count"] >= 1
    assert all(result["quality_gates"].values())


def test_replay_and_ideal_degraded_packages_are_byte_identical() -> None:
    config = load_config()
    replay = compare_replay(primary_scene(config), replay_scene(config))
    assert replay["byte_identical"] is True
    assert replay["file_count"] == 51
    ideal = release_root(config) / "arms/ideal/gt"
    degraded = release_root(config) / "arms/degraded/gt"
    assert inventory(ideal) == inventory(degraded)
    assert (ideal / "ground_truth_manifest.json").read_bytes() == (
        degraded / "ground_truth_manifest.json"
    ).read_bytes()
    ideal_manifest = json.loads(
        (ideal / "ground_truth_manifest.json").read_text(encoding="utf-8")
    )
    assert ideal_manifest["arm_neutral"] is True
    assert ideal_manifest["identity_authority"] == (
        "pre_render_geometry_nodes_dependency_graph_instance"
    )


def test_validation_receipt_is_current_and_does_not_claim_native_release() -> None:
    config = load_config()
    root = results_root(config)
    receipt_path = root / "validation_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["config_sha256"] == sha256_file(CONFIG_PATH)
    patch = PROJECT_ROOT / config["source_lock"]["botanical_gt_patch"]["path"]
    assert receipt["source_evidence"]["botanical_gt_patch"]["sha256"] == (
        sha256_file(patch)
    )
    assert receipt["status"] == "PASS_PROTOCOL_ADMISSION_PILOT_SYNTHETIC_ONLY"
    assert receipt["all_quality_gates_passed"] is True
    assert all(receipt["quality_gates"].values())
    native = receipt["protocol_admission_capabilities"]["native_2048_square_rgb"]
    assert native["pilot_executed"] is False
    assert native["required_for_full_benchmark_release"] is True
    package = json.loads((root / "package_manifest.json").read_text(encoding="utf-8"))
    assert package["validation_receipt_sha256"] == sha256_file(receipt_path)


def test_source_lock_drift_fails_closed() -> None:
    config = copy.deepcopy(load_config())
    config["source_lock"]["protocol"]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="protocol SHA256 mismatch"):
        validate_source_locks(config)


def test_forbidden_identity_input_tamper_fails_closed(tmp_path: Path) -> None:
    config = load_config()
    scene = tmp_path / "scene"
    shutil.copytree(primary_scene(config), scene)
    source_path = scene / "botanical_ground_truth/source_objects.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["forbidden_identity_inputs"].remove("model_predictions")
    source_path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(RuntimeError, match="identity inputs"):
        validate_scene(scene, config)


def test_source_asset_binding_tamper_fails_closed(tmp_path: Path) -> None:
    config = load_config()
    scene = tmp_path / "scene"
    shutil.copytree(primary_scene(config), scene)
    source_path = scene / "botanical_ground_truth/source_objects.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["tracks"][0]["source"]["source_asset_candidates"] = []
    source["source_scene_graph_identity_sha256"] = canonical_sha256(
        source["tracks"]
    )
    source_path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(RuntimeError, match="absent from its source collection"):
        validate_scene(scene, config)


def test_visible_mask_occlusion_tamper_fails_closed(tmp_path: Path) -> None:
    config = load_config()
    scene = tmp_path / "scene"
    shutil.copytree(primary_scene(config), scene)
    gt_root = scene / "botanical_ground_truth"
    first = json.loads((gt_root / "tracks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    visible_path = gt_root / first["visible_mask"]
    isolated = np.asarray(
        Image.open(gt_root / first["isolated_mask"]).convert("L"), dtype=np.uint8
    )
    visible = np.asarray(Image.open(visible_path).convert("L"), dtype=np.uint8).copy()
    candidates = np.argwhere(isolated < 127)
    assert len(candidates) > 0
    y, x = (int(value) for value in candidates[0])
    visible[y, x] = 255
    Image.fromarray(visible).save(visible_path)
    with pytest.raises(RuntimeError, match="Visible instance"):
        validate_scene(scene, config)
