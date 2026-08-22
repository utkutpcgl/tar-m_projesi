#!/usr/bin/env python3
"""Execute the source-locked native synthetic spot-spray video A/B benchmark.

The module deliberately separates rendering from inference.  Rendering and
machine audit may inspect both declared splits, but locked-test prediction is
impossible until a calibration-only threshold lock exists.  Every emitted
claim remains synthetic-only and has zero authority for field or chemical use.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import inspect
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "configs/benchmark/spot_spray_simulation_video_ab_execution_v1.yaml"
)
CONTRACT = "spot_spray_simulation_video_ab_execution_v1"
SEQUENCE_CONTRACT = "spot_spray_simulation_video_sequence_v1"
FULL_PLAN_CONTRACT = "spot_spray_simulation_video_ab_full_plan_v1"
FULL_PAIR_RECEIPT_CONTRACT = "spot_spray_simulation_video_ab_full_pair_receipt_v1"
FULL_RENDER_EXECUTION_CONTRACT = "spot_spray_simulation_video_ab_full_render_execution_v1"
FULL_CROPCRAFT_CONTRACT = "spot_spray_simulation_video_ab_cropcraft_runtime_v1"
GT_SCOUT_CONTRACT = "spot_spray_simulation_video_ab_gt_scout_v1"
GT_SCOUT_EXECUTION_CONTRACT = "spot_spray_simulation_video_ab_gt_scout_execution_v1"
CALIBRATION_BATCH_CONTRACT = (
    "spot_spray_simulation_video_ab_calibration_batch_execution_v1"
)
LOCKED_TEST_RENDER_BATCH_CONTRACT = (
    "spot_spray_simulation_video_ab_locked_test_render_batch_execution_v1"
)
GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT = (
    "spot_spray_simulation_video_ab_gt_source_cardinality_recovery_v1"
)
LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT = (
    "spot_spray_simulation_video_ab_locked_test_gt_source_cardinality_recovery_v1"
)
ROSTER_EXTENSION_CONTRACT = (
    "spot_spray_simulation_video_ab_roster_extension_v1"
)
ROSTER_EXTENSION_MIGRATION_CONTRACT = (
    "spot_spray_simulation_video_ab_roster_extension_migration_bridge_v1"
)
ROSTER_EXTENSION_RELEASE_CONTRACT = (
    "spot_spray_simulation_video_ab_execution_release_v1_plus_roster_extension_v1"
)
ROSTER_EXTENSION_PASS55_CONTRACT = (
    "spot_spray_simulation_video_ab_roster_extension_pass55_validation_v1"
)
ROSTER_EXTENSION_MANAGER_EVENT_ID = (
    "scheduled-resume-20260817103307-75b799f2dfc8"
)
ROSTER_EXTENSION_OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
ROSTER_EXTENSION_MANAGER_SESSION_ID = "019fb346-5ead-7600-8068-40b32b0daa06"
ROSTER_EXTENSION_RUN_ID = (
    "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
)
ROSTER_EXTENSION_PORTFOLIO_ID = (
    "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
)
ROSTER_EXTENSION_LANE_ID = "full-simulation-video-ab-execution-v1"
ROSTER_EXTENSION_PORTFOLIO_REVISION = 97
ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX = 10
ROSTER_EXTENSION_LAST_CANDIDATE_INDEX = 31
ROSTER_EXTENSION_CANDIDATES_PER_SLOT = 22
ROSTER_EXTENSION_TOTAL_CANDIDATE_CEILING = 32
RUNTIME_COMPATIBILITY_CONTRACT = (
    "spot_spray_simulation_video_ab_roster_extension_runtime_compatibility_v1"
)
RUNTIME_COMPATIBILITY_RELEASE_CONTRACT = (
    "spot_spray_simulation_video_ab_execution_release_v1_plus_roster_"
    "extension_v1_runtime_compatibility_v1"
)
RUNTIME_COMPATIBILITY_PASS58_CONTRACT = (
    "spot_spray_simulation_video_ab_roster_extension_pass58_validation_v1"
)
RUNTIME_COMPATIBILITY_EVENT_ID = "scheduled-resume-20260817120448-1b733ad4fca0"
PASS55_EXECUTION_SCRIPT_SHA256 = (
    "e6780e0aef77842c1e9b7d92ce0e1c518d49a1c90c4397209e1236262395d685"
)
PASS55_EXECUTION_TEST_SHA256 = (
    "9d568c27d57c147c4bc8fa95c9fe18929820b29a8e076ec892f02ae343b9e0ad"
)
PASS55_VALIDATION_RECEIPT_SHA256 = (
    "4de710884589115bab63ee388dc4bf74454a9a71b9c4341a976a9d3aad88aefc"
)
PASS55_ARTIFACT_INVENTORY_SHA256 = (
    "50da9980f2e1d7d01e29180dd1f1f124f0f1788f1ad5c71c0e1234f4c034855a"
)
ROSTER_EXTENSION_CONFIG_SHA256 = (
    "6c37c11665c32be662879bb250eb654b8a5bd55834b4eeb896f3a74d031eb259"
)
ROSTER_EXTENSION_RELEASE_FILE_SHA256 = (
    "6aa06ae282e6fa79d1864530f7307c38f252678273f64499f153c6bd300b897c"
)
ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256 = (
    "5c06e7b6aa79c0b744b232b3071f4a59e0fec1d321335303d64be15aad23159c"
)
PASS57_FAILURE_RECEIPT_SHA256 = (
    "de7baaad54c1d0206b8427f250fc23b04328edfa5e7d6219c7e84e2657a07e17"
)
PASS56_FAILED_BATCH_INTENT_SHA256 = (
    "e910ac803d60e9ad59c96cb2d787a63b570a59fd6705be37237a7b60bfaac68f"
)
RUNTIME_COMPATIBILITY_ALIASES = {
    "sealed_full_render_execution_lock_sha256": (
        "10490375155ed25a00c79e4b8cab5e4488099bbcd73068c078a3426ac2d9a804"
    ),
    "sealed_full_render_implementation_sha256": (
        "7a28319bb48d087db8620ab18650566a5884a21343cc1cec557a1f9694173751"
    ),
}
HISTORICAL_V1_BINDINGS = {
    "protocol_sha256": (
        "de12cd76d3f497f1ea3a6ffa1d1c7fc8eea4e70a9af218c2769bae81da0f329f"
    ),
    "execution_config_sha256": (
        "a419dd1db3c314e79f12cf0aab576144cc4e4a43385669467f072534ae687e6b"
    ),
    "execution_script_sha256": (
        "e650340418ae213d433f18356b6acad5b77942ae67ac3df2577bfe18840fe3d2"
    ),
    "full_plan_generator_script_sha256": (
        "3f2d6cfd9eeede0c75437b0808b6380dabd4197e324cff71cbd010cea5e1bda3"
    ),
    "execution_test_sha256": (
        "f6687b33fd137c6482897529b91f49d48bd2d246c4fce41f9249a9de540f856d"
    ),
    "pair_roster_sha256": (
        "cf224af0624f77404c07c94303e0cb7fe27cbac5dc13c21b859a0e2abff14b43"
    ),
    "render_state_sha256": (
        "ff06d781e7989e2204266e43ff2a9978e51dcbd4e17e326f809694ae14368fec"
    ),
    "candidate_rejection_ledger_sha256": (
        "3c60ebab9c892418a0a3edd144eb372db2614162dcdc8999451ec4cd2b2ee81a"
    ),
    "pass54_validation_receipt_sha256": (
        "2ea24b280cb8fd4fc7b928420785970e6a8fb62bfd988b6b22d6ac1731a4d6e6"
    ),
    "selected_checkpoint_sha256": (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    ),
    "full_plan_receipt_sha256": (
        "be14720a4249222ec56e49efc54a564a2b4efd75d3d94eca9fc23ff76ff2fdb9"
    ),
    "candidate_gate_contract_sha256": (
        "b1af31dc12bc09b92c583a878797cb138624f9a9dc672fe2272cf0405b00f089"
    ),
    "atomic_render_state_contract_sha256": (
        "c8ea7db85e3c5bc309cf888cda188215f7b6aeea5c25271f02861f388a653237"
    ),
    "full_render_execution_lock_sha256": (
        "10490375155ed25a00c79e4b8cab5e4488099bbcd73068c078a3426ac2d9a804"
    ),
    "gt_scout_execution_lock_sha256": (
        "5fe68dd43183a588b02724bfd0af090f405f7a27f2eacf74b109b84c40a3c3d3"
    ),
    "locked_test_render_batch_execution_lock_sha256": (
        "5bd38a72d9a07dbbb1077de770a4509d75b023dc05d7d7edc397b818d4c12ce6"
    ),
    "locked_test_recovery_execution_lock_sha256": (
        "40fe379dacc3b3af26c20d34b8bfcb9d86d5bdb2b9bf1c3ff7393bb11c19c95e"
    ),
}
SEALED_FULL_RENDER_IMPLEMENTATION_SHA256 = (
    "7a28319bb48d087db8620ab18650566a5884a21343cc1cec557a1f9694173751"
)
SEALED_FULL_RENDER_EXECUTION_LOCK_SHA256 = (
    "10490375155ed25a00c79e4b8cab5e4488099bbcd73068c078a3426ac2d9a804"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


FULL_AB_MODULE_SOURCE = '''"""Frozen full-benchmark CropCraft capture/runtime adapter."""

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import yaml
from PIL import Image


CONTRACT = "spot_spray_simulation_video_ab_cropcraft_runtime_v1"
_CONTRACT_CACHE = None


def _canonical_sha256(value):
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _config_path():
    if "--" not in sys.argv:
        raise RuntimeError("Full A/B adapter cannot locate the scene config")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def contract():
    global _CONTRACT_CACHE
    if _CONTRACT_CACHE is None:
        payload = yaml.safe_load(_config_path().read_text(encoding="utf-8"))
        value = payload.get("full_execution_contract")
        if not isinstance(value, dict) or value.get("contract") != CONTRACT:
            raise RuntimeError("Missing frozen full A/B execution contract")
        if value.get("model_access_allowed") is not False:
            raise RuntimeError("Full A/B render contract permits model access")
        _CONTRACT_CACHE = value
    return _CONTRACT_CACHE


def enabled():
    return contract().get("contract") == CONTRACT


def filter_models(plant_type, models):
    allowed = set(contract()["role_asset_allowlist"])
    result = [
        model
        for model in models
        if f"{plant_type}/{Path(model.filename).name}" in allowed
    ]
    return result


def _apply_trajectory_binding():
    value = contract()
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("Full A/B render camera is missing")
    constraints = [row for row in camera.constraints if row.type == "FOLLOW_PATH"]
    if len(constraints) != 1 or constraints[0].target is None:
        raise RuntimeError("Full A/B camera trajectory is ambiguous")
    curve = constraints[0].target
    offset = float(value["shared_latent_parameters"]["lateral_camera_offset_m"])
    points = curve.data.splines[0].bezier_points
    if len(points) != 2:
        raise RuntimeError("Full A/B camera path does not have two endpoints")
    for point in points:
        point.co.y += offset
    return {
        "trajectory_seed": int(value["seeds"]["trajectory_seed"]),
        "seed_role": "identity_binding_for_frozen_deterministic_path",
        "lateral_camera_offset_m": offset,
        "path_endpoints_m": [[float(axis) for axis in point.co] for point in points],
    }


def _quadrant_lights():
    scene = bpy.context.scene
    camera = scene.camera
    source = bpy.data.objects.get("robot_fill_light_q0")
    if source is None:
        source = bpy.data.objects.get("robot_fill_light")
    if source is None or source.type != "LIGHT" or camera is None:
        raise RuntimeError("Frozen surface fill light or render camera is missing")
    positions = [(-0.08, -0.08), (-0.08, 0.08), (0.08, -0.08), (0.08, 0.08)]
    lights = []
    for index, (x_value, y_value) in enumerate(positions):
        if index == 0:
            light = source
            light.name = "robot_fill_light_q0"
        else:
            light = bpy.data.objects.get(f"robot_fill_light_q{index}")
            if light is None:
                light = bpy.data.objects.new(
                    f"robot_fill_light_q{index}", source.data.copy()
                )
                bpy.data.collections["env"].objects.link(light)
        light.parent = camera
        light.location = (x_value, y_value, 0.03)
        light.rotation_euler = (0.0, 0.0, 0.0)
        lights.append(light)
    return lights


def _set_capture_light(profile):
    lights = _quadrant_lights()
    energy = float(profile["artificial_light_energy_renderer_units"])
    size = float(profile["artificial_light_size_m"])
    warmth = float(profile["artificial_light_warmth_proxy"])
    colour = (1.0, 1.0 - 0.13 * warmth, 1.0 - 0.30 * warmth)
    for light in lights:
        light.data.energy = energy / len(lights)
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = colour
    return {
        "quadrant_count": len(lights),
        "all_quadrants_on": all(light.data.energy > 0.0 for light in lights),
        "total_energy_renderer_units": energy,
        "per_quadrant_energy_renderer_units": energy / len(lights),
        "size_m": size,
        "warmth_proxy": warmth,
        "colour_rgb_linear_proxy": list(colour),
    }


def _render_lossless_rgb(render, output_dir, relative_directory):
    scene = bpy.context.scene
    value = contract()
    scene.render.engine = "CYCLES"
    scene.cycles.device = render.cycles_device
    scene.cycles.samples = render.samples
    scene.cycles.seed = int(value["seeds"]["renderer_seed"]) % 2147483647
    scene.cycles.use_animated_seed = False
    scene.render.resolution_x = render.resolution_x
    scene.render.resolution_y = render.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    target = Path(output_dir) / render.directory / relative_directory
    target.mkdir(parents=True, exist_ok=False)
    scene.render.filepath = str(target / "frame_")
    bpy.ops.render.render(animation=True)


def _pixel_hash(path):
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return hashlib.sha256(rgb.tobytes()).hexdigest(), list(rgb.size)


def _compare_replay(primary_root, replay_root, frame_count):
    rows = []
    for index in range(1, frame_count + 1):
        name = f"frame_{index:04d}.png"
        primary = primary_root / name
        replay = replay_root / name
        primary_hash, primary_size = _pixel_hash(primary)
        replay_hash, replay_size = _pixel_hash(replay)
        rows.append(
            {
                "frame_index": index - 1,
                "primary_pixel_sha256": primary_hash,
                "replay_pixel_sha256": replay_hash,
                "pixel_exact": primary_hash == replay_hash,
                "dimensions_equal": primary_size == replay_size,
                "png_bytes_equal": primary.read_bytes() == replay.read_bytes(),
            }
        )
    if not all(row["pixel_exact"] and row["dimensions_equal"] for row in rows):
        raise RuntimeError("Full A/B deterministic ideal replay changed pixels")
    return rows


def _write_runner_jpeg_proxies(source_root, destination_root, frame_count):
    destination_root.mkdir(parents=True, exist_ok=False)
    rows = []
    for index in range(1, frame_count + 1):
        source = source_root / f"frame_{index:04d}.png"
        destination = destination_root / f"frame_{index:04d}.jpg"
        with Image.open(source) as image:
            image.convert("RGB").save(
                destination, format="JPEG", quality=100, subsampling=0
            )
        rows.append(
            {
                "frame_index": index - 1,
                "png_pixel_sha256": _pixel_hash(source)[0],
                "jpeg_validation_proxy_only": destination.name,
            }
        )
    return rows


def _audit_frame_indices(seed, frame_count):
    ranked = sorted(
        range(frame_count),
        key=lambda index: hashlib.sha256(
            f"{int(seed)}|{index}".encode("ascii")
        ).digest(),
    )
    return sorted(ranked[:3])


def render_capture_arms(render, output_dir):
    value = contract()
    trajectory = _apply_trajectory_binding()
    root = Path(output_dir) / render.directory
    ideal_root = root / "full_ab/ideal_rgb"
    degraded_root = root / "full_ab/degraded_base_rgb"
    replay_root = root / "full_ab/deterministic_replay_ideal_rgb"

    ideal_light = _set_capture_light(value["ideal_capture_parameters"])
    _render_lossless_rgb(render, output_dir, "full_ab/ideal_rgb")
    degraded_light = _set_capture_light(value["degraded_capture_parameters"])
    _render_lossless_rgb(render, output_dir, "full_ab/degraded_base_rgb")
    _set_capture_light(value["ideal_capture_parameters"])
    _render_lossless_rgb(
        render, output_dir, "full_ab/deterministic_replay_ideal_rgb"
    )
    replay = _compare_replay(ideal_root, replay_root, int(render.frames))
    proxies = _write_runner_jpeg_proxies(
        ideal_root, root / "images", int(render.frames)
    )
    seed_bindings = {
        "scene_seed": {
            "value": int(value["seeds"]["scene_seed"]),
            "consumer": "CropCraft field.random_seed geometry and source assets",
        },
        "trajectory_seed": {
            "value": int(value["seeds"]["trajectory_seed"]),
            "consumer": "frozen camera path identity",
        },
        "capture_draw_seed": {
            "value": int(value["seeds"]["capture_draw_seed"]),
            "consumer": "frozen slot capture-vector integrity binding",
            "capture_vector_sha256": _canonical_sha256(
                {
                    "seed": int(value["seeds"]["capture_draw_seed"]),
                    "ideal": value["ideal_capture_parameters"],
                    "degraded": value["degraded_capture_parameters"],
                }
            ),
        },
        "renderer_seed": {
            "value": int(value["seeds"]["renderer_seed"]),
            "consumer": "Cycles scene seed with animated seed disabled",
            "cycles_seed": int(value["seeds"]["renderer_seed"]) % 2147483647,
        },
        "audit_sample_seed": {
            "value": int(value["seeds"]["audit_sample_seed"]),
            "consumer": "preoutcome frame sampling",
            "selected_frame_indices": _audit_frame_indices(
                value["seeds"]["audit_sample_seed"], int(render.frames)
            ),
        },
    }
    receipt = {
        "schema_version": 1,
        "contract": CONTRACT,
        "pair_id": value["pair_id"],
        "candidate_identity_sha256": value["candidate_identity_sha256"],
        "frame_count": int(render.frames),
        "native_dimensions_px": [int(render.resolution_x), int(render.resolution_y)],
        "lossless_rgb_source": True,
        "trajectory": trajectory,
        "seed_bindings": seed_bindings,
        "ideal_light": ideal_light,
        "degraded_light": degraded_light,
        "deterministic_replay": {
            "all_frames_pixel_exact": all(row["pixel_exact"] for row in replay),
            "all_png_bytes_exact": all(row["png_bytes_equal"] for row in replay),
            "frame_rows": replay,
        },
        "runner_jpeg_proxies": proxies,
        "model_access": False,
        "prediction_access": False,
    }
    path = Path(output_dir) / "full_ab_capture_receipt.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
    )
'''


GT_SCOUT_MODULE_SOURCE = '''"""Frozen GT-only roster scout for the full A/B benchmark."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from core import full_ab


CONTRACT = "spot_spray_simulation_video_ab_gt_scout_v1"
EXPECTED_SEED_CHANNELS = (
    "scene_seed",
    "trajectory_seed",
    "capture_draw_seed",
    "renderer_seed",
    "audit_sample_seed",
)
_BOUND_STATE = None


def _pixel_sha256(image):
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def bind_trajectory_only(render, output_dir):
    """Bind the shared full-render trajectory without rendering an RGB arm."""
    global _BOUND_STATE
    value = full_ab.contract()
    if int(render.frames) != 30:
        raise RuntimeError("GT scout requires exactly 30 frames")
    if (int(render.resolution_x), int(render.resolution_y)) != (2048, 2048):
        raise RuntimeError("GT scout requires native 2048-square geometry")
    seeds = value.get("seeds")
    if not isinstance(seeds, dict) or set(seeds) != set(EXPECTED_SEED_CHANNELS):
        raise RuntimeError("GT scout five-channel seed binding changed")
    _BOUND_STATE = {
        "pair_id": value["pair_id"],
        "candidate_identity_sha256": value["candidate_identity_sha256"],
        "trajectory": full_ab._apply_trajectory_binding(),
        "seeds": {name: int(seeds[name]) for name in EXPECTED_SEED_CHANNELS},
    }


def write_runner_proxies(render, output_dir):
    """Create validation-only JPEGs from semantic masks, never RGB evidence."""
    if _BOUND_STATE is None:
        raise RuntimeError("GT scout trajectory was not bound")
    render_root = Path(output_dir) / render.directory
    semantic_root = render_root / "masks"
    proxy_root = render_root / "images"
    semantic_paths = sorted(semantic_root.glob("frame_*.png"))
    if len(semantic_paths) != int(render.frames):
        raise RuntimeError("GT scout semantic frame count changed")
    proxy_root.mkdir(parents=True, exist_ok=False)
    rows = []
    for source in semantic_paths:
        destination = proxy_root / f"{source.stem}.jpg"
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            if rgb.size != (int(render.resolution_x), int(render.resolution_y)):
                raise RuntimeError("GT scout semantic raster geometry changed")
            pixel_sha256 = _pixel_sha256(rgb)
            rgb.save(destination, format="JPEG", quality=100, subsampling=0)
        rows.append(
            {
                "frame_id": source.stem,
                "semantic_pixel_sha256": pixel_sha256,
                "proxy_name": destination.name,
            }
        )
    seed_usage = {
        "scene_seed": "consumed_by_cropcraft_field_geometry_and_assets",
        "trajectory_seed": "consumed_by_frozen_shared_camera_path",
        "capture_draw_seed": "identity_bound_capture_not_rendered",
        "renderer_seed": "identity_bound_rgb_renderer_not_invoked",
        "audit_sample_seed": "identity_bound_preoutcome_audit_not_sampled",
    }
    receipt = {
        "schema_version": 1,
        "contract": CONTRACT,
        "pair_id": _BOUND_STATE["pair_id"],
        "candidate_identity_sha256": _BOUND_STATE[
            "candidate_identity_sha256"
        ],
        "frame_count": int(render.frames),
        "native_dimensions_px": [
            int(render.resolution_x),
            int(render.resolution_y),
        ],
        "trajectory": _BOUND_STATE["trajectory"],
        "seed_bindings": {
            name: {
                "value": _BOUND_STATE["seeds"][name],
                "scout_use": seed_usage[name],
            }
            for name in EXPECTED_SEED_CHANNELS
        },
        "semantic_validation_proxies": rows,
        "rgb_capture_rendered": False,
        "ideal_or_degraded_arm_rendered": False,
        "runner_jpeg_proxies_are_semantic_validation_only": True,
        "model_access": False,
        "prediction_access": False,
    }
    path = Path(output_dir) / "gt_scout_capture_receipt.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
'''


class ContractError(RuntimeError):
    """Raised when a frozen execution invariant is violated."""


class CandidateRejected(ContractError):
    """Raised when a rendered candidate fails a declared non-model gate."""

    def __init__(self, message: str, evidence: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.evidence = dict(evidence or {})


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(stable_bytes(value)).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(stable_bytes(dict(row)).decode("utf-8") + "\n")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"Expected YAML mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON mapping: {path}")
    return value


def resolve_path(value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def require_sha256(value: Any, label: str) -> str:
    observed = str(value)
    if SHA256_RE.fullmatch(observed) is None:
        raise ContractError(f"{label} is not a lowercase SHA-256")
    return observed


def load_config(path: Path) -> dict[str, Any]:
    config = load_yaml(path.expanduser().resolve())
    if config.get("schema_version") != 1 or config.get("contract") != CONTRACT:
        raise ContractError("Execution config schema or contract mismatch")
    policy = config.get("evidence_policy")
    if not isinstance(policy, dict) or policy.get("scope") != "synthetic_diagnostic_only":
        raise ContractError("Execution evidence must remain synthetic_diagnostic_only")
    forbidden = (
        bool(policy.get("field_or_deployment_claim_allowed"))
        or bool(policy.get("product_go_allowed"))
        or bool(policy.get("chemical_fire_go_allowed"))
        or float(policy.get("synthetic_score_weight_in_real_go_decision", -1.0))
        != 0.0
    )
    if forbidden or policy.get("outcome_target_tuning_forbidden") is not True:
        raise ContractError("Synthetic claim boundary is not fail closed")
    native = config.get("native_contract")
    if not isinstance(native, dict):
        raise ContractError("native_contract is missing")
    if (
        [int(native["width_px"]), int(native["height_px"])] != [2048, 2048]
        or int(native["frames_per_arm"]) != 30
        or int(native["frame_rate_hz"]) != 15
        or bool(native["full_frame_resize_allowed"])
    ):
        raise ContractError("Native 2048/30-frame/15-Hz contract changed")
    targets = config.get("descriptive_targets")
    if not isinstance(targets, dict):
        raise ContractError("descriptive_targets is missing")
    if (
        float(targets.get("ideal_minimum", -1.0)) != 0.97
        or float(targets.get("degraded_reference", -1.0)) != 0.75
        or bool(targets.get("use_in_threshold_selection"))
        or bool(targets.get("use_in_model_or_degradation_tuning"))
    ):
        raise ContractError("Reporting-only target contract changed")
    scenes = config.get("fixture", {}).get("scenes", [])
    if (
        len(scenes) != 2
        or {str(row.get("split")) for row in scenes} != {"calibration", "test"}
        or len({str(row.get("pair_id")) for row in scenes}) != 2
    ):
        raise ContractError("Fixture must contain one calibration and one test pair")
    return config


def _run_text(command: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ContractError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def verified_file_row(name: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve_path(str(spec["path"]))
    if not path.is_file():
        raise ContractError(f"Missing source lock {name}: {path}")
    expected = require_sha256(spec.get("sha256"), f"source_locks.{name}.sha256")
    observed = sha256_file(path)
    if observed != expected:
        raise ContractError(
            f"Source drift for {name}: observed {observed}, expected {expected}"
        )
    return {
        "name": name,
        "path": display_path(path),
        "bytes": path.stat().st_size,
        "sha256": observed,
    }


def verify_protocol_internal_sources(protocol_path: Path) -> list[dict[str, Any]]:
    protocol = load_yaml(protocol_path)
    source_lock = protocol.get("source_lock")
    if not isinstance(source_lock, dict):
        raise ContractError("Frozen protocol source_lock is missing")
    rows: list[dict[str, Any]] = []
    for group_name in ("repository_sources", "external_sources"):
        group = source_lock.get(group_name)
        if not isinstance(group, dict):
            raise ContractError(f"Frozen protocol {group_name} is missing")
        for name, raw_spec in sorted(group.items()):
            if not isinstance(raw_spec, dict):
                raise ContractError(f"Invalid protocol lock {group_name}.{name}")
            row = verified_file_row(f"protocol:{group_name}:{name}", raw_spec)
            rows.append(row)
            required_facts = raw_spec.get("required_facts")
            if required_facts is not None:
                payload = load_json(resolve_path(str(raw_spec["path"])))
                for key, expected in required_facts.items():
                    if payload.get(key) != expected:
                        raise ContractError(
                            f"Protocol required fact drift: {name}.{key}: "
                            f"{payload.get(key)!r} != {expected!r}"
                        )
    return rows


def verify_all_sources(config: Mapping[str, Any]) -> dict[str, Any]:
    locks = config.get("source_locks")
    if not isinstance(locks, dict):
        raise ContractError("source_locks is missing")
    rows = [
        verified_file_row(name, spec)
        for name, spec in sorted(locks.items())
        if isinstance(spec, dict)
    ]
    if len(rows) != len(locks):
        raise ContractError("Every source lock must be a mapping")
    protocol_path = resolve_path(str(locks["protocol"]["path"]))
    protocol_rows = verify_protocol_internal_sources(protocol_path)

    repository = resolve_path(str(config["runtime"]["cropcraft_repository"]))
    expected_revision = str(config["runtime"]["cropcraft_revision"])
    revision = _run_text(["git", "-C", str(repository), "rev-parse", "HEAD"]).strip()
    if revision != expected_revision:
        raise ContractError(f"CropCraft revision drift: {revision} != {expected_revision}")
    dirty = _run_text(
        ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=no"]
    ).strip()
    if dirty:
        raise ContractError("Pinned CropCraft checkout has tracked modifications")

    blender = resolve_path(str(locks["blender"]["path"]))
    blender_version = _run_text([str(blender), "--version"]).splitlines()[0]
    if not blender_version.startswith(
        str(config["runtime"]["blender_required_version_prefix"])
    ):
        raise ContractError(f"Unexpected Blender version: {blender_version}")
    ffmpeg = resolve_path(str(locks["ffmpeg"]["path"]))
    ffmpeg_version = _run_text([str(ffmpeg), "-version"]).splitlines()[0]
    if str(config["runtime"]["ffmpeg_required_version_substring"]) not in ffmpeg_version:
        raise ContractError(f"Unexpected ffmpeg version: {ffmpeg_version}")
    return {
        "execution_locks": rows,
        "execution_locks_sha256": stable_sha256(rows),
        "protocol_internal_locks": protocol_rows,
        "protocol_internal_locks_sha256": stable_sha256(protocol_rows),
        "cropcraft": {
            "repository": display_path(repository),
            "revision": revision,
            "tracked_checkout_clean": True,
        },
        "runtime": {
            "blender_version": blender_version,
            "ffmpeg_version": ffmpeg_version,
        },
    }


def _gpu_receipt(device: int) -> dict[str, Any]:
    query = _run_text(
        [
            "nvidia-smi",
            f"--id={device}",
            "--query-gpu=index,name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
    ).strip()
    fields = [value.strip() for value in query.split(",")]
    if len(fields) != 5:
        raise ContractError(f"Unexpected nvidia-smi output: {query}")
    return {
        "index": int(fields[0]),
        "name": fields[1],
        "memory_total_mib": int(fields[2]),
        "memory_used_mib": int(fields[3]),
        "memory_free_mib": int(fields[4]),
        "external_process_policy": "observed_only_never_stopped_or_modified",
    }


def preflight(config_path: Path, *, scope: str = "fixture") -> dict[str, Any]:
    config = load_config(config_path)
    sources = verify_all_sources(config)
    output_root = resolve_path(str(config["outputs"]["synthetic_root"]))
    output_root.parent.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(output_root.parent)
    runtime = config["runtime"]
    required = int(
        runtime["minimum_fixture_free_bytes"]
        if scope == "fixture"
        else runtime["minimum_full_free_bytes"]
    )
    reserve = 0 if scope == "fixture" else int(runtime["reserve_free_bytes_after_full"])
    if disk.free < required or disk.free - required < reserve:
        raise ContractError(
            f"Insufficient data-disk capacity for {scope}: free={disk.free}, "
            f"required={required}, reserve={reserve}"
        )
    native_pixels = 2048 * 2048
    admission_pixels = 256 * 256
    admission_isolated_seconds = 0.05
    native_isolated_seconds = (
        admission_isolated_seconds * native_pixels / admission_pixels
    )
    fixture_assumed_tracks = 24
    fixture_scenes = len(config["fixture"]["scenes"])
    frames = int(config["native_contract"]["frames_per_arm"])
    fixture_isolated_seconds = (
        native_isolated_seconds * fixture_assumed_tracks * frames * fixture_scenes
    )
    full_pairs = int(config["storage_estimate"]["full_total_pairs"])
    full_isolated_seconds = native_isolated_seconds * fixture_assumed_tracks * frames * full_pairs
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "PASS_PREFLIGHT_SYNTHETIC_ONLY",
        "scope": scope,
        "config": {
            "path": display_path(config_path),
            "sha256": sha256_file(config_path),
        },
        "sources": sources,
        "capacity": {
            "path": str(output_root.parent),
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "required_bytes": required,
            "reserve_bytes_after_estimate": reserve,
            "passed": True,
        },
        "gpu": _gpu_receipt(int(runtime["cuda_device"])),
        "runtime_estimate": {
            "method": "admission_isolated_mask_render_pixel_scaling_upper_bound",
            "admission_resolution_px": [256, 256],
            "native_resolution_px": [2048, 2048],
            "admission_observed_isolated_render_seconds_approx": admission_isolated_seconds,
            "native_isolated_render_seconds_per_track_frame_estimate": native_isolated_seconds,
            "fixture_assumed_tracks_per_scene": fixture_assumed_tracks,
            "fixture_isolated_render_hours_estimate": fixture_isolated_seconds / 3600.0,
            "full_isolated_render_hours_estimate": full_isolated_seconds / 3600.0,
            "excludes_rgb_render_inference_encoding_and_io": True,
            "replace_with_measured_fixture_multiplier_before_full_render": True,
        },
        "storage_estimate": copy.deepcopy(config["storage_estimate"]),
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _protocol(config: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve_path(str(config["source_locks"]["protocol"]["path"]))
    protocol = load_yaml(path)
    expected = str(config["full_benchmark"]["protocol_id"])
    if protocol.get("protocol_id") != expected:
        raise ContractError(
            f"Full-plan protocol mismatch: {protocol.get('protocol_id')} != {expected}"
        )
    return protocol


def _canonical_decimal(value: float) -> str:
    if not math.isfinite(float(value)):
        raise ContractError(f"Non-finite canonical decimal: {value}")
    rendered = format(float(value), ".9f").rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def derive_protocol_seed(
    protocol: Mapping[str, Any],
    *,
    split: str,
    cell_id: str,
    replicate_index: int,
    candidate_index: int,
    channel: str,
) -> int:
    derivation = protocol["seed_derivation"]
    if derivation["algorithm"] != "sha256_uint64_big_endian_first_8_bytes":
        raise ContractError("Unsupported frozen seed derivation")
    channels = [str(value) for value in derivation["channels"]]
    if channel not in channels:
        raise ContractError(f"Undeclared seed channel: {channel}")
    low, high = (int(value) for value in derivation["candidate_index_range"])
    if not low <= candidate_index <= high:
        raise ContractError(f"Candidate index outside frozen range: {candidate_index}")
    base_seeds = derivation["split_base_seeds"]
    if split not in base_seeds:
        raise ContractError(f"Unknown protocol split for seed derivation: {split}")
    parts = [
        str(protocol["protocol_id"]),
        split,
        cell_id,
        str(int(replicate_index)),
        str(int(candidate_index)),
        channel,
        str(int(base_seeds[split])),
    ]
    payload = str(derivation["separator"]).join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _lhs_permutation(
    protocol_id: str,
    split: str,
    cell_id: str,
    variable: str,
    strata: int,
) -> list[int]:
    if strata <= 0:
        raise ContractError("LHS strata must be positive")
    return sorted(
        range(strata),
        key=lambda index: hashlib.sha256(
            "|".join(
                (
                    protocol_id,
                    split,
                    cell_id,
                    "lhs_midpoint_permutation",
                    variable,
                    str(index),
                )
            ).encode("utf-8")
        ).digest(),
    )


def _lhs_value(
    protocol_id: str,
    split: str,
    cell_id: str,
    variable: str,
    replicate_index: int,
    strata: int,
    bounds: Sequence[Any],
) -> str:
    if len(bounds) != 2:
        raise ContractError(f"LHS bounds must have two values: {variable}")
    lower, upper = (float(value) for value in bounds)
    if lower > upper or not math.isfinite(lower) or not math.isfinite(upper):
        raise ContractError(f"Invalid LHS bounds for {variable}: {bounds}")
    permutation = _lhs_permutation(
        protocol_id, split, cell_id, variable, strata
    )
    bin_index = permutation[replicate_index]
    fraction = (bin_index + 0.5) / strata
    return _canonical_decimal(lower + fraction * (upper - lower))


def _full_continuous_ranges(
    protocol: Mapping[str, Any], profile: str
) -> tuple[dict[str, Sequence[Any]], dict[str, Sequence[Any]]]:
    envelope = protocol["shared_latent_envelope"]
    shared = {
        "ground_fov_mm": envelope["ground_fov_mm"],
        "working_distance_mm": envelope["working_distance_mm"],
        "roll_deg": envelope["roll_deg"],
        "pitch_deg": envelope["pitch_deg"],
        "yaw_deg": envelope["yaw_deg"],
        "lateral_camera_offset_m": envelope["lateral_camera_offset_m"],
    }
    profile_ranges = envelope["scene_profiles"].get(profile)
    if not isinstance(profile_ranges, dict):
        raise ContractError(f"Missing frozen continuous ranges for profile {profile}")
    for name in (
        "environment_strength",
        "soil_moisture",
        "sun_energy",
        "sun_elevation_deg",
        "sun_angle_deg",
        "local_shadow_fraction",
    ):
        shared[name] = profile_ranges[name]
    degraded = {
        "pulse_width_us": protocol["degraded_capture_profile"]["pulse_width_us"],
        "artificial_light_energy_renderer_units": profile_ranges[
            "artificial_light_energy_renderer_units"
        ],
        "artificial_light_size_m": profile_ranges["artificial_light_size_m"],
        "artificial_light_warmth_proxy": profile_ranges[
            "artificial_light_warmth_proxy"
        ],
    }
    return shared, degraded


def _scene_template_inventory(config: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"roles": {}}
    for split_name, role in config["full_benchmark"]["source_roles"].items():
        receipt_spec = config["source_locks"][str(role["receipt_lock"])]
        receipt_path = resolve_path(str(receipt_spec["path"]))
        receipt = load_json(receipt_path)
        if receipt.get("all_quality_gates_passed") is not True:
            raise ContractError(f"V12 role receipt is not passing: {split_name}")
        root = resolve_path(str(role["scene_config_root"]))
        rows: list[dict[str, Any]] = []
        pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for scene in receipt.get("scenes", []):
            scene_id = str(scene["scene"])
            path = root / f"{scene_id}.yaml"
            expected = require_sha256(
                scene["config_sha256"], f"{split_name}.{scene_id}.config_sha256"
            )
            if not path.is_file() or sha256_file(path) != expected:
                raise ContractError(f"V12 scene-template drift: {path}")
            payload = load_yaml(path)
            profile = str(
                payload["agri_asset_profile"]["correlated_scene_profile"]
            )
            row = {
                "scene_id": scene_id,
                "path": str(path),
                "sha256": expected,
                "profile": profile,
                "ground_material_id": str(
                    payload["agri_asset_profile"]["ground_material_id"]
                ),
                "environment_file": str(
                    payload["agri_asset_profile"]["environment_file"]
                ),
                "source_seed": int(scene["seed"]),
            }
            rows.append(row)
            pools[profile].append(row)
        for profile_rows in pools.values():
            profile_rows.sort(key=lambda row: row["scene_id"])
        if len(rows) != int(receipt["scene_count"]) or len(rows) != 8:
            raise ContractError(f"Expected eight V12 templates for {split_name}")
        if any(len(pools[name]) != 4 for name in pools) or len(pools) != 2:
            raise ContractError(f"V12 template profiles are not 4/4 for {split_name}")
        result["roles"][split_name] = {
            "protocol_split": str(role["protocol_split"]),
            "evaluator_split": str(role["evaluator_split"]),
            "v12_role": str(role["v12_role"]),
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256_file(receipt_path),
            "templates": rows,
            "pools": dict(pools),
            "used_ground_materials": sorted(receipt["used_ground_materials"]),
            "used_environments": sorted(receipt["used_environments"]),
            "base_crop_model_filenames": sorted(receipt["crop_model_filenames"]),
        }
    calibration = result["roles"]["calibration"]
    locked_test = result["roles"]["locked_test"]
    ground_overlap = set(calibration["used_ground_materials"]) & set(
        locked_test["used_ground_materials"]
    )
    environment_overlap = set(calibration["used_environments"]) & set(
        locked_test["used_environments"]
    )
    if ground_overlap or environment_overlap:
        raise ContractError(
            "V12 role templates violate frozen ground/environment split purity"
        )
    result["cross_split"] = {
        "ground_material_overlap": sorted(ground_overlap),
        "environment_overlap": sorted(environment_overlap),
        "base_crop_filename_overlap_count": len(
            set(calibration["base_crop_model_filenames"])
            & set(locked_test["base_crop_model_filenames"])
        ),
        "base_model_overlap_requires_execution_partition": True,
    }
    return result


def _description_models(description: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(description.get("models"), list):
        return [dict(row) for row in description["models"]]
    groups = description.get("model_groups")
    if isinstance(groups, dict):
        return [dict(row) for group in groups.values() for row in group["models"]]
    raise ContractError("Plant description has no model inventory")


def build_role_asset_partition(
    config: Mapping[str, Any], templates: Mapping[str, Any]
) -> dict[str, Any]:
    pack_manifest = resolve_path(str(config["source_locks"]["v12_asset_pack"]["path"]))
    plants_root = pack_manifest.parent / "xdg/cropcraft/plants"
    families: set[str] = set()
    queries: dict[str, list[dict[str, Any]]] = {"calibration": [], "locked_test": []}
    for split_name, role in templates["roles"].items():
        for template in role["templates"]:
            payload = load_yaml(Path(template["path"]))
            for bed in payload["field"]["beds"].values():
                family = str(bed["plant_type"])
                families.add(family)
                queries[split_name].append(
                    {
                        "family": family,
                        "target_height": float(bed["plant_height"]),
                        "tolerance": float(bed["height_tolerance_coeff"]),
                        "kind": "crop",
                    }
                )
            for weed in payload["field"].get("weeds", {}).values():
                family = str(weed["plant_type"])
                families.add(family)
                queries[split_name].append(
                    {
                        "family": family,
                        "target_height": float(weed["max_height"]) / 2.0,
                        "tolerance": 1.0,
                        "kind": "weed",
                    }
                )
    role_rows: dict[str, list[dict[str, Any]]] = {
        "calibration": [],
        "locked_test": [],
    }
    model_table: dict[str, list[dict[str, Any]]] = {}
    for family in sorted(families):
        description_path = plants_root / family / "description.yaml"
        description = load_yaml(description_path)
        rows: list[dict[str, Any]] = []
        for raw in _description_models(description):
            filename = str(raw["filename"])
            object_path = plants_root / family / filename
            if not object_path.is_file():
                raise ContractError(f"Missing plant model: {object_path}")
            rows.append(
                {
                    "family": family,
                    "filename": filename,
                    "height_m": float(raw["height"]),
                    "object_sha256": sha256_file(object_path),
                }
            )
        ordered = sorted(
            rows,
            key=lambda row: hashlib.sha256(
                f"{family}|{row['filename']}".encode("utf-8")
            ).digest(),
        )
        for index, row in enumerate(ordered):
            split_name = "calibration" if index % 2 == 0 else "locked_test"
            role_rows[split_name].append(row)
        model_table[family] = rows

    for split_name, split_queries in queries.items():
        permitted = role_rows[split_name]
        for query in split_queries:
            lower = (1.0 - query["tolerance"]) * query["target_height"]
            upper = (1.0 + query["tolerance"]) * query["target_height"]
            matches = [
                row
                for row in permitted
                if row["family"] == query["family"]
                and lower <= row["height_m"] <= upper
            ]
            if not matches:
                raise ContractError(
                    "Role asset partition leaves a source-template query empty: "
                    f"{split_name}:{query}"
                )
    filenames = {
        name: {f"{row['family']}/{row['filename']}" for row in rows}
        for name, rows in role_rows.items()
    }
    object_hashes = {
        name: {row["object_sha256"] for row in rows}
        for name, rows in role_rows.items()
    }
    filename_overlap = filenames["calibration"] & filenames["locked_test"]
    hash_overlap = object_hashes["calibration"] & object_hashes["locked_test"]
    if filename_overlap or hash_overlap:
        raise ContractError("Derived role asset partition is not identity-disjoint")
    crop_family = next(
        query["family"]
        for query in queries["calibration"]
        if query["kind"] == "crop"
    )
    crop_counts = {
        name: sum(row["family"] == crop_family for row in rows)
        for name, rows in role_rows.items()
    }
    if min(crop_counts.values()) < 6:
        raise ContractError("Role asset partition has fewer than six crop variants")
    receipt = {
        "schema_version": 1,
        "algorithm": "sha256_filename_order_round_robin_by_role_v1",
        "identity_definition": "plant_family_plus_filename_and_obj_sha256",
        "source_pack_sha256": config["source_locks"]["v12_asset_pack"]["sha256"],
        "roles": {
            name: {
                "models": sorted(rows, key=lambda row: (row["family"], row["filename"])),
                "allowlist": sorted(filenames[name]),
                "allowlist_sha256": stable_sha256(sorted(filenames[name])),
                "object_identity_sha256": stable_sha256(
                    sorted(object_hashes[name])
                ),
            }
            for name, rows in role_rows.items()
        },
        "validation": {
            "filename_overlap_count": 0,
            "object_sha256_overlap_count": 0,
            "all_template_model_queries_nonempty": True,
            "crop_model_count_by_role": crop_counts,
            "minimum_crop_models_per_role": 6,
        },
    }
    receipt["partition_sha256"] = stable_sha256(receipt)
    return receipt


def build_full_roster(
    config: Mapping[str, Any],
    protocol: Mapping[str, Any],
    templates: Mapping[str, Any],
) -> list[dict[str, Any]]:
    allocation = protocol["allocation"]
    factors = allocation["factors"]
    factor_order = [str(value) for value in config["full_benchmark"]["cell_factor_order"]]
    if factor_order != [
        "travel_speed_m_s",
        "v12_scene_profile",
        "degraded_motion_path",
    ]:
        raise ContractError("Full cell factor order changed")
    cells = []
    for index, values in enumerate(
        itertools.product(*(factors[name] for name in factor_order))
    ):
        cells.append(
            {
                "cell_index": index,
                "cell_id": f"cell_{index:03d}",
                "factors": dict(zip(factor_order, values, strict=True)),
            }
        )
    if len(cells) != int(allocation["exact_cell_count"]):
        raise ContractError("Frozen allocation did not produce eight cells")

    rows: list[dict[str, Any]] = []
    maximum_candidates = int(config["full_benchmark"]["maximum_candidates_per_slot"])
    channels = [str(value) for value in protocol["seed_derivation"]["channels"]]
    ideal_midpoints = protocol["ideal_capture_profile"]["profile_midpoint_light"]
    for split_name in ("calibration", "locked_test"):
        role = config["full_benchmark"]["source_roles"][split_name]
        split_contract = allocation["splits"][split_name]
        replicate_count = int(split_contract["replicates_per_cell"])
        template_role = templates["roles"][split_name]
        for cell in cells:
            profile = str(cell["factors"]["v12_scene_profile"])
            shared_ranges, degraded_ranges = _full_continuous_ranges(
                protocol, profile
            )
            pool = template_role["pools"][profile]
            for replicate_index in range(replicate_count):
                pair_id = (
                    f"{split_name}_c{cell['cell_index']:03d}_r{replicate_index:02d}"
                )
                shared_parameters = {
                    name: _lhs_value(
                        str(protocol["protocol_id"]),
                        split_name,
                        str(cell["cell_id"]),
                        name,
                        replicate_index,
                        replicate_count,
                        bounds,
                    )
                    for name, bounds in shared_ranges.items()
                }
                degraded_parameters = {
                    name: _lhs_value(
                        str(protocol["protocol_id"]),
                        split_name,
                        str(cell["cell_id"]),
                        name,
                        replicate_index,
                        replicate_count,
                        bounds,
                    )
                    for name, bounds in degraded_ranges.items()
                }
                midpoint = ideal_midpoints[profile]
                ideal_parameters = {
                    "artificial_light_energy_renderer_units": _canonical_decimal(
                        midpoint["energy_renderer_units"]
                    ),
                    "artificial_light_size_m": _canonical_decimal(midpoint["size_m"]),
                    "artificial_light_warmth_proxy": _canonical_decimal(
                        midpoint["warmth_proxy"]
                    ),
                    "pulse_width_us": "0",
                }
                candidates: list[dict[str, Any]] = []
                for candidate_index in range(maximum_candidates):
                    seeds = {
                        channel: derive_protocol_seed(
                            protocol,
                            split=split_name,
                            cell_id=str(cell["cell_id"]),
                            replicate_index=replicate_index,
                            candidate_index=candidate_index,
                            channel=channel,
                        )
                        for channel in channels
                    }
                    template = pool[(replicate_index + candidate_index) % len(pool)]
                    candidate = {
                        "candidate_index": candidate_index,
                        "seeds": seeds,
                        "source_template": {
                            "scene_id": template["scene_id"],
                            "sha256": template["sha256"],
                            "profile": template["profile"],
                        },
                        "model_outcome_inputs": [],
                    }
                    candidate["candidate_identity_sha256"] = stable_sha256(candidate)
                    candidates.append(candidate)
                row = {
                    "pair_id": pair_id,
                    "protocol_split": split_name,
                    "evaluator_split": str(role["evaluator_split"]),
                    "v12_source_role": str(role["v12_role"]),
                    "cell_id": str(cell["cell_id"]),
                    "cell_index": int(cell["cell_index"]),
                    "replicate_index": replicate_index,
                    "factors": {
                        "travel_speed_m_s": _canonical_decimal(
                            cell["factors"]["travel_speed_m_s"]
                        ),
                        "v12_scene_profile": profile,
                        "degraded_motion_path": str(
                            cell["factors"]["degraded_motion_path"]
                        ),
                    },
                    "shared_latent_parameters": shared_parameters,
                    "ideal_capture_parameters": ideal_parameters,
                    "degraded_capture_parameters": degraded_parameters,
                    "candidate_policy": "first_candidate_in_derived_order_passing_all_non_model_gates",
                    "candidates": candidates,
                    "descriptive_target_inputs": [],
                }
                row["pair_slot_identity_sha256"] = stable_sha256(row)
                rows.append(row)
    return rows


def validate_full_roster(
    rows: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    allocation = protocol["allocation"]
    counts = {
        split: sum(row["protocol_split"] == split for row in rows)
        for split in ("calibration", "locked_test")
    }
    expected_counts = {
        split: int(allocation["splits"][split]["pair_count"])
        for split in counts
    }
    if counts != expected_counts or len(rows) != int(allocation["totals"]["pair_count"]):
        raise ContractError(f"Full roster split counts changed: {counts}")
    pair_ids = [str(row["pair_id"]) for row in rows]
    if len(pair_ids) != len(set(pair_ids)):
        raise ContractError("Full roster pair IDs are not unique")
    seed_values: list[int] = []
    candidate_ids: list[str] = []
    cell_counts: dict[tuple[str, str], int] = defaultdict(int)
    lhs_values: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        split = str(row["protocol_split"])
        cell_id = str(row["cell_id"])
        cell_counts[(split, cell_id)] += 1
        parameters = {
            **row["shared_latent_parameters"],
            **row["degraded_capture_parameters"],
        }
        for name, value in parameters.items():
            lhs_values[(split, cell_id, str(name))].add(str(value))
        if row["descriptive_target_inputs"] or row["candidate_policy"] != (
            "first_candidate_in_derived_order_passing_all_non_model_gates"
        ):
            raise ContractError("Roster includes outcome input or changed candidate policy")
        for expected_index, candidate in enumerate(row["candidates"]):
            if int(candidate["candidate_index"]) != expected_index:
                raise ContractError("Candidate order is not exact")
            if candidate["model_outcome_inputs"]:
                raise ContractError("Candidate roster contains model outcome inputs")
            seed_values.extend(int(value) for value in candidate["seeds"].values())
            candidate_ids.append(str(candidate["candidate_identity_sha256"]))
    for split in ("calibration", "locked_test"):
        expected_replicates = int(allocation["splits"][split]["replicates_per_cell"])
        split_cells = [key for key in cell_counts if key[0] == split]
        if len(split_cells) != 8 or any(
            cell_counts[key] != expected_replicates for key in split_cells
        ):
            raise ContractError(f"Full roster cell balance changed: {split}")
        for key, values in lhs_values.items():
            if key[0] == split and len(values) != expected_replicates:
                raise ContractError(f"LHS midpoint strata are not complete: {key}")
    if len(seed_values) != 96 * 10 * 5 or len(seed_values) != len(set(seed_values)):
        raise ContractError("Full roster seeds are reused across split/candidate/channel")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ContractError("Full roster candidate identities are not unique")
    factor_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in rows:
        factors = row["factors"]
        factor_counts[
            (
                str(row["protocol_split"]),
                str(factors["travel_speed_m_s"]),
                str(factors["v12_scene_profile"]),
                str(factors["degraded_motion_path"]),
            )
        ] += 1
    if len(factor_counts) != 16:
        raise ContractError("Full roster is missing one or more split/cell combinations")
    return {
        "pair_count": len(rows),
        "split_pair_counts": counts,
        "cell_count_per_split": 8,
        "factor_cell_count_total": len(factor_counts),
        "candidate_count": sum(len(row["candidates"]) for row in rows),
        "unique_candidate_identity_count": len(set(candidate_ids)),
        "seed_count": len(seed_values),
        "unique_seed_count": len(set(seed_values)),
        "seed_channels": list(protocol["seed_derivation"]["channels"]),
        "lhs_midpoint_strata_complete": True,
        "outcome_inputs_absent": True,
    }


def _tree_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def full_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    name = str(config["outputs"]["full_name"])
    return {
        "synthetic": resolve_path(str(config["outputs"]["synthetic_root"])) / name,
        "run": resolve_path(str(config["outputs"]["run_root"])) / name,
        "docs": resolve_path(str(config["outputs"]["results_root"])) / name,
    }


def roster_extension_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    """Return the append-only epoch paths without consulting candidate evidence."""
    paths = full_paths(config)
    synthetic = paths["synthetic"] / "planning/roster_extension_v1"
    docs = paths["docs"] / "roster_extension_v1"
    return {
        "synthetic": synthetic,
        "docs": docs,
        "manifest": synthetic / "pair_roster_extension_v1.jsonl",
        "contract": synthetic / "roster_extension_contract_v1.json",
        "extension_config": (
            synthetic / "execution_config_v1_plus_roster_extension_v1.yaml"
        ),
        "snapshot_manifest": synthetic / "historical_source_snapshots_v1.json",
        "evidence_inventory": synthetic / "historical_v1_evidence_inventory_v1.json",
        "migration_bridge": synthetic / "manager_authorization_migration_bridge_v1.json",
        "release": synthetic / "execution_release_v1_plus_roster_extension_v1.json",
        "pass55_receipt": synthetic / "pass55_validation_receipt.json",
        "execution_locks": synthetic / "execution_locks",
    }


def runtime_compatibility_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    """Return the append-only Pass58 patch paths without touching candidate data."""
    paths = full_paths(config)
    synthetic = paths["synthetic"] / "planning/roster_extension_runtime_compatibility_v1"
    docs = paths["docs"] / "roster_extension_runtime_compatibility_v1"
    release_root = synthetic / "release_v1"
    docs_release_root = docs / "release_v1"
    return {
        "synthetic": synthetic,
        "docs": docs,
        "release_root": release_root,
        "docs_release_root": docs_release_root,
        "bridge": release_root / "runtime_compatibility_bridge_v1.json",
        "adapter_lock": release_root / "runtime_compatibility_adapter_lock_v1.json",
        "config": (
            release_root
            / "execution_config_v1_plus_roster_extension_v1_runtime_compatibility_v1.yaml"
        ),
        "release": (
            release_root
            / "execution_release_v1_plus_roster_extension_v1_runtime_compatibility_v1.json"
        ),
        "pass58_receipt": release_root / "pass58_validation_receipt.json",
        "script_snapshot": (
            synthetic
            / "source_snapshots/run_spot_spray_simulation_video_ab_execution_v1.pass55.py"
        ),
        "test_snapshot": (
            synthetic
            / "source_snapshots/test_run_spot_spray_simulation_video_ab_execution_v1.pass55.py"
        ),
    }


def _runtime_compatibility_failure_receipt_path(
    config: Mapping[str, Any],
) -> Path:
    return (
        full_paths(config)["docs"]
        / "locked_test_render_batches/pass56_extension_execution/"
        "pass57_fail_closed_receipt.json"
    )


def _runtime_compatibility_failed_intent_path(config: Mapping[str, Any]) -> Path:
    return (
        full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1/"
        "locked_test_render_batch_locked_test_c001_r00_7b302bef07d4edd1/"
        "batch_intent.json"
    )


def _historical_source_snapshot_specs(
    config: Mapping[str, Any],
) -> list[dict[str, str]]:
    planning = full_paths(config)["synthetic"] / "planning"
    root = planning / "historical_epoch_v1_source_snapshots"
    return [
        {
            "role": "historical_protocol_source",
            "path": display_path(
                root / "spot_spray_simulation_video_ab_protocol_v1.de12cd76.yaml"
            ),
            "sha256": HISTORICAL_V1_BINDINGS["protocol_sha256"],
        },
        {
            "role": "historical_execution_config_source",
            "path": display_path(
                root / "spot_spray_simulation_video_ab_execution_v1.a419dd1d.yaml"
            ),
            "sha256": HISTORICAL_V1_BINDINGS["execution_config_sha256"],
        },
        {
            "role": "historical_execution_implementation_source",
            "path": display_path(
                root / "run_spot_spray_simulation_video_ab_execution_v1.e6503404.py"
            ),
            "sha256": HISTORICAL_V1_BINDINGS["execution_script_sha256"],
        },
        {
            "role": "historical_execution_test_source",
            "path": display_path(
                root / "test_run_spot_spray_simulation_video_ab_execution_v1.f6687b33.py"
            ),
            "sha256": HISTORICAL_V1_BINDINGS["execution_test_sha256"],
        },
        {
            "role": "historical_pair_roster_bytes",
            "path": display_path(root / "pair_roster_v1.cf224af0.jsonl"),
            "sha256": HISTORICAL_V1_BINDINGS["pair_roster_sha256"],
        },
        {
            "role": "historical_candidate_rejection_ledger_bytes",
            "path": display_path(
                root / "candidate_rejection_ledger_v1.3c60ebab.jsonl"
            ),
            "sha256": HISTORICAL_V1_BINDINGS[
                "candidate_rejection_ledger_sha256"
            ],
        },
        {
            "role": "historical_render_state_bytes",
            "path": display_path(root / "render_state_v1.ff06d781.json"),
            "sha256": HISTORICAL_V1_BINDINGS["render_state_sha256"],
        },
        {
            "role": "historical_pass54_validation_receipt_bytes",
            "path": display_path(
                root / "pass54_validation_receipt.2ea24b28.json"
            ),
            "sha256": HISTORICAL_V1_BINDINGS[
                "pass54_validation_receipt_sha256"
            ],
        },
    ]


def _validate_historical_source_snapshots(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _historical_source_snapshot_specs(config)
    for row in rows:
        path = resolve_path(row["path"])
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            raise ContractError(
                f"Historical V1 source snapshot changed: {row['role']}"
            )
    return {
        "schema_version": 1,
        "status": "PASS_IMMUTABLE_HISTORICAL_V1_SOURCE_SNAPSHOTS",
        "snapshots": rows,
        "snapshot_count": len(rows),
        "snapshot_identity_sha256": stable_sha256(rows),
    }


def derive_roster_extension_seed(
    protocol: Mapping[str, Any],
    *,
    split: str,
    cell_id: str,
    replicate_index: int,
    candidate_index: int,
    channel: str,
) -> int:
    """Use the frozen V1 derivation verbatim under the manager-authorized range."""
    derivation = protocol["seed_derivation"]
    expected_input_order = [
        "protocol_id",
        "split",
        "cell_id",
        "replicate_index",
        "candidate_index",
        "channel_name",
        "v12_split_base_seed",
    ]
    if (
        derivation.get("algorithm")
        != "sha256_uint64_big_endian_first_8_bytes"
        or derivation.get("separator") != "|"
        or list(derivation.get("input_order", [])) != expected_input_order
        or list(derivation.get("candidate_index_range", [])) != [0, 9]
        or int(derivation.get("exact_attempts_per_required_slot_maximum", -1))
        != 10
    ):
        raise ContractError("Historical V1 seed derivation changed")
    channels = [str(value) for value in derivation["channels"]]
    if channel not in channels:
        raise ContractError(f"Undeclared seed channel: {channel}")
    if not (
        ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX
        <= int(candidate_index)
        <= ROSTER_EXTENSION_LAST_CANDIDATE_INDEX
    ):
        raise ContractError(
            f"Candidate index outside sealed extension range: {candidate_index}"
        )
    base_seeds = derivation["split_base_seeds"]
    if split not in base_seeds:
        raise ContractError(f"Unknown protocol split for seed derivation: {split}")
    parts = [
        str(protocol["protocol_id"]),
        split,
        cell_id,
        str(int(replicate_index)),
        str(int(candidate_index)),
        channel,
        str(int(base_seeds[split])),
    ]
    payload = str(derivation["separator"]).join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def build_roster_extension(
    historical_rows: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    template_inventory: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Precompute every candidate 10..31 without rendering or opening GT."""
    channels = [str(value) for value in protocol["seed_derivation"]["channels"]]
    rows: list[dict[str, Any]] = []
    for historical in historical_rows:
        historical_candidates = historical.get("candidates")
        if not isinstance(historical_candidates, list) or len(historical_candidates) != 10:
            raise ContractError("Historical V1 row no longer has exactly candidates 0-9")
        if [int(row["candidate_index"]) for row in historical_candidates] != list(
            range(10)
        ):
            raise ContractError("Historical V1 candidate order changed")
        split = str(historical["protocol_split"])
        cell_id = str(historical["cell_id"])
        replicate_index = int(historical["replicate_index"])
        profile = str(historical["factors"]["v12_scene_profile"])
        try:
            pool = template_inventory["roles"][split]["pools"][profile]
        except (KeyError, TypeError) as error:
            raise ContractError(
                f"Historical template pool is missing: {split}:{profile}"
            ) from error
        if not isinstance(pool, list) or not pool:
            raise ContractError("Historical template pool is empty")
        candidates: list[dict[str, Any]] = []
        for candidate_index in range(
            ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX,
            ROSTER_EXTENSION_LAST_CANDIDATE_INDEX + 1,
        ):
            seeds = {
                channel: derive_roster_extension_seed(
                    protocol,
                    split=split,
                    cell_id=cell_id,
                    replicate_index=replicate_index,
                    candidate_index=candidate_index,
                    channel=channel,
                )
                for channel in channels
            }
            template = pool[(replicate_index + candidate_index) % len(pool)]
            candidate = {
                "candidate_index": candidate_index,
                "seeds": seeds,
                "source_template": {
                    "scene_id": str(template["scene_id"]),
                    "sha256": require_sha256(
                        template["sha256"], "extension source template"
                    ),
                    "profile": str(template["profile"]),
                },
                "model_outcome_inputs": [],
            }
            candidate["candidate_identity_sha256"] = stable_sha256(candidate)
            candidates.append(candidate)
        row = {
            "pair_id": str(historical["pair_id"]),
            "protocol_split": split,
            "evaluator_split": str(historical["evaluator_split"]),
            "v12_source_role": str(historical["v12_source_role"]),
            "cell_id": cell_id,
            "cell_index": int(historical["cell_index"]),
            "replicate_index": replicate_index,
            "historical_pair_slot_identity_sha256": require_sha256(
                historical["pair_slot_identity_sha256"],
                "historical pair slot identity",
            ),
            "historical_candidate_index_range": [0, 9],
            "extension_candidate_index_range": [
                ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX,
                ROSTER_EXTENSION_LAST_CANDIDATE_INDEX,
            ],
            "candidate_policy": (
                "lowest_unattempted_candidate_index_passing_unchanged_"
                "non_model_gates"
            ),
            "candidates": candidates,
            "model_prediction_outcome_or_registered_target_inputs": [],
        }
        row["extension_row_identity_sha256"] = stable_sha256(row)
        rows.append(row)
    return rows


def validate_roster_extension_rows(
    extension_rows: Sequence[Mapping[str, Any]],
    historical_rows: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    template_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    expected = build_roster_extension(
        historical_rows, protocol, template_inventory
    )
    observed = [dict(row) for row in extension_rows]
    if observed != expected:
        raise ContractError(
            "Roster extension drift, reorder, collision, or partial publication"
        )
    if len(observed) != 96 or len(historical_rows) != 96:
        raise ContractError("Roster extension must bind all 96 protocol slots")
    historical_pair_ids = [str(row["pair_id"]) for row in historical_rows]
    if [str(row["pair_id"]) for row in observed] != historical_pair_ids:
        raise ContractError("Roster extension pair order changed")

    historical_candidate_ids: list[str] = []
    historical_seed_values: list[int] = []
    extension_candidate_ids: list[str] = []
    extension_seed_values: list[int] = []
    for old, new in zip(historical_rows, observed, strict=True):
        if old["pair_slot_identity_sha256"] != new[
            "historical_pair_slot_identity_sha256"
        ]:
            raise ContractError("Roster extension rebound a historical pair slot")
        old_candidates = old["candidates"]
        new_candidates = new["candidates"]
        if [int(row["candidate_index"]) for row in old_candidates] != list(range(10)):
            raise ContractError("Historical candidate 0-9 identities changed")
        if [int(row["candidate_index"]) for row in new_candidates] != list(
            range(
                ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX,
                ROSTER_EXTENSION_LAST_CANDIDATE_INDEX + 1,
            )
        ):
            raise ContractError("Roster extension candidate order changed")
        for candidate in old_candidates:
            historical_candidate_ids.append(
                require_sha256(
                    candidate["candidate_identity_sha256"],
                    "historical candidate identity",
                )
            )
            historical_seed_values.extend(
                int(value) for value in candidate["seeds"].values()
            )
        for candidate in new_candidates:
            if candidate.get("model_outcome_inputs") != []:
                raise ContractError("Roster extension contains model or outcome input")
            identity_payload = {
                key: copy.deepcopy(value)
                for key, value in candidate.items()
                if key != "candidate_identity_sha256"
            }
            if candidate["candidate_identity_sha256"] != stable_sha256(
                identity_payload
            ):
                raise ContractError("Roster extension candidate identity changed")
            extension_candidate_ids.append(candidate["candidate_identity_sha256"])
            extension_seed_values.extend(
                int(value) for value in candidate["seeds"].values()
            )
    combined_candidate_ids = historical_candidate_ids + extension_candidate_ids
    combined_seed_values = historical_seed_values + extension_seed_values
    if len(extension_candidate_ids) != 96 * ROSTER_EXTENSION_CANDIDATES_PER_SLOT:
        raise ContractError("Roster extension candidate count changed")
    if len(extension_candidate_ids) != len(set(extension_candidate_ids)):
        raise ContractError("Roster extension candidate identities collide")
    if set(historical_candidate_ids) & set(extension_candidate_ids):
        raise ContractError("Roster extension candidate identity collides with V1")
    if len(extension_seed_values) != len(set(extension_seed_values)):
        raise ContractError("Roster extension seed values collide")
    if set(historical_seed_values) & set(extension_seed_values):
        raise ContractError("Roster extension seed value collides with V1")
    if len(combined_candidate_ids) != 96 * ROSTER_EXTENSION_TOTAL_CANDIDATE_CEILING:
        raise ContractError("Combined roster candidate count changed")
    if len(combined_seed_values) != 96 * 32 * 5:
        raise ContractError("Combined roster seed count changed")
    return {
        "pair_count": len(observed),
        "historical_candidate_count": len(historical_candidate_ids),
        "extension_candidate_count": len(extension_candidate_ids),
        "combined_candidate_count": len(combined_candidate_ids),
        "unique_extension_candidate_identity_count": len(
            set(extension_candidate_ids)
        ),
        "unique_combined_candidate_identity_count": len(
            set(combined_candidate_ids)
        ),
        "extension_seed_count": len(extension_seed_values),
        "unique_extension_seed_count": len(set(extension_seed_values)),
        "combined_seed_count": len(combined_seed_values),
        "unique_combined_seed_count": len(set(combined_seed_values)),
        "candidate_index_range": [
            ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX,
            ROSTER_EXTENSION_LAST_CANDIDATE_INDEX,
        ],
        "candidate_indices_per_slot": ROSTER_EXTENSION_CANDIDATES_PER_SLOT,
        "all_96_slots_presealed": True,
        "historical_candidates_unchanged": True,
        "source_template_cycle_unchanged": True,
        "seed_formula_unchanged_except_versioned_index_range": True,
        "model_prediction_outcome_or_target_inputs_absent": True,
    }


def merge_full_roster_with_extension(
    historical_rows: Sequence[Mapping[str, Any]],
    extension_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(historical_rows) != len(extension_rows):
        raise ContractError("Cannot merge a partial roster extension")
    merged: list[dict[str, Any]] = []
    for old, extension in zip(historical_rows, extension_rows, strict=True):
        if (
            old["pair_id"] != extension["pair_id"]
            or old["pair_slot_identity_sha256"]
            != extension["historical_pair_slot_identity_sha256"]
        ):
            raise ContractError("Roster extension slot migration binding changed")
        row = copy.deepcopy(dict(old))
        historical_candidates = copy.deepcopy(list(row["candidates"]))
        row["candidates"] = [
            *historical_candidates,
            *copy.deepcopy(list(extension["candidates"])),
        ]
        if row["candidates"][:10] != historical_candidates:
            raise ContractError("Roster extension mutated candidates 0-9")
        if [int(candidate["candidate_index"]) for candidate in row["candidates"]] != list(
            range(ROSTER_EXTENSION_TOTAL_CANDIDATE_CEILING)
        ):
            raise ContractError("Combined roster order is not canonical")
        merged.append(row)
    return merged


def _historical_v1_evidence_inventory(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    paths = full_paths(config)
    root = paths["synthetic"]
    planning = root / "planning"
    protected: set[Path] = {
        DEFAULT_CONFIG.resolve(),
        resolve_path(config["source_locks"]["protocol"]["path"]),
        planning / "pair_roster_v1.jsonl",
        planning / "full_plan_receipt_v1.json",
        planning / "candidate_gate_contract_v1.json",
        planning / "atomic_render_state_contract_v1.json",
        planning / "full_render_execution_lock_v1.json",
        planning / "gt_scout_execution_lock_v1.json",
        planning / "locked_test_render_batch_execution_lock_v1.json",
        planning / "locked_test_gt_source_cardinality_recovery_execution_lock_v1.json",
        paths["docs"] / "render_state_v1.json",
        paths["docs"] / "locked_test_render_batches/pass54_validation_receipt.json",
    }
    for snapshot in _historical_source_snapshot_specs(config):
        protected.add(resolve_path(snapshot["path"]))

    candidate_receipts: set[Path] = set()
    candidate_pattern = re.compile(r"^candidate_(0[0-9])$")
    for path in planning.rglob("*"):
        if not path.is_file() or "roster_extension_v1" in path.parts:
            continue
        candidate_component = next(
            (
                part
                for part in path.parts
                if candidate_pattern.fullmatch(part) is not None
            ),
            None,
        )
        if candidate_component is None:
            continue
        name = path.name
        if (
            "receipt" in name
            or name in {"decision_receipt.json", "gate_evidence.json"}
        ):
            candidate_receipts.add(path)
    protected.update(candidate_receipts)

    historical_roster = read_jsonl(planning / "pair_roster_v1.jsonl")
    historical_completed_pair_ids = [
        str(row["pair_id"]) for row in historical_roster[:40]
    ]
    pair_receipts = sorted(
        root
        / "pairs"
        / str(next(row for row in historical_roster if row["pair_id"] == pair_id)[
            "protocol_split"
        ])
        / pair_id
        / "full_pair_receipt.json"
        for pair_id in historical_completed_pair_ids
    )
    if len(pair_receipts) != 40:
        raise ContractError(
            f"Historical V1 published-pair receipt count changed: {len(pair_receipts)}"
        )
    protected.update(pair_receipts)
    if any(not path.is_file() for path in protected):
        missing = sorted(display_path(path) for path in protected if not path.is_file())
        raise ContractError(f"Historical V1 evidence file is missing: {missing[:3]}")
    rows = [
        {
            "path": display_path(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(protected, key=lambda value: display_path(value))
    ]
    return {
        "schema_version": 1,
        "contract": "spot_spray_simulation_video_ab_historical_v1_evidence_inventory",
        "status": "PASS_IMMUTABLE_HISTORICAL_V1_EVIDENCE",
        "file_count": len(rows),
        "candidate_0_9_receipt_file_count": len(candidate_receipts),
        "published_pair_receipt_count": len(pair_receipts),
        "files": rows,
        "inventory_sha256": stable_sha256(rows),
    }


def _assert_historical_v1_epoch(
    config: Mapping[str, Any], *, require_live_boundary: bool
) -> dict[str, Any]:
    paths = full_paths(config)
    planning = paths["synthetic"] / "planning"
    fixed_paths = {
        "protocol_sha256": resolve_path(config["source_locks"]["protocol"]["path"]),
        "execution_config_sha256": DEFAULT_CONFIG.resolve(),
        "pair_roster_sha256": planning / "pair_roster_v1.jsonl",
        "pass54_validation_receipt_sha256": (
            paths["docs"]
            / "locked_test_render_batches/pass54_validation_receipt.json"
        ),
        "full_plan_receipt_sha256": planning / "full_plan_receipt_v1.json",
        "candidate_gate_contract_sha256": (
            planning / "candidate_gate_contract_v1.json"
        ),
        "atomic_render_state_contract_sha256": (
            planning / "atomic_render_state_contract_v1.json"
        ),
        "full_render_execution_lock_sha256": (
            planning / "full_render_execution_lock_v1.json"
        ),
        "gt_scout_execution_lock_sha256": (
            planning / "gt_scout_execution_lock_v1.json"
        ),
        "locked_test_render_batch_execution_lock_sha256": (
            planning / "locked_test_render_batch_execution_lock_v1.json"
        ),
        "locked_test_recovery_execution_lock_sha256": (
            planning
            / "locked_test_gt_source_cardinality_recovery_execution_lock_v1.json"
        ),
        "selected_checkpoint_sha256": resolve_path(
            config["source_locks"]["selected_checkpoint"]["path"]
        ),
    }
    for key, path in fixed_paths.items():
        if not path.is_file() or sha256_file(path) != HISTORICAL_V1_BINDINGS[key]:
            raise ContractError(f"Historical V1 byte identity changed: {key}")
    if require_live_boundary:
        for key, path in (
            ("render_state_sha256", planning / "render_state_v1.json"),
            (
                "candidate_rejection_ledger_sha256",
                planning / "candidate_rejection_ledger_v1.jsonl",
            ),
        ):
            if not path.is_file() or sha256_file(path) != HISTORICAL_V1_BINDINGS[key]:
                raise ContractError(f"Historical V1 live boundary changed: {key}")
    docs_state = paths["docs"] / "render_state_v1.json"
    if not docs_state.is_file():
        raise ContractError("Historical V1 docs render state is missing")
    if (
        require_live_boundary
        and sha256_file(docs_state)
        != HISTORICAL_V1_BINDINGS["render_state_sha256"]
    ):
        raise ContractError("Historical V1 docs render state changed")

    snapshots = _validate_historical_source_snapshots(config)
    protocol = _protocol(config)
    historical_rows = read_jsonl(planning / "pair_roster_v1.jsonl")
    roster_validation = validate_full_roster(historical_rows, protocol)
    if (
        roster_validation["candidate_count"] != 960
        or roster_validation["unique_candidate_identity_count"] != 960
        or roster_validation["seed_count"] != 4800
        or roster_validation["unique_seed_count"] != 4800
    ):
        raise ContractError("Historical V1 candidate identities changed")
    candidate_identity_rows = [
        {
            "pair_id": row["pair_id"],
            "candidate_identities": [
                {
                    "candidate_index": candidate["candidate_index"],
                    "candidate_identity_sha256": candidate[
                        "candidate_identity_sha256"
                    ],
                }
                for candidate in row["candidates"]
            ],
        }
        for row in historical_rows
    ]

    snapshot_root = planning / "historical_epoch_v1_source_snapshots"
    ledger = read_jsonl(
        snapshot_root / "candidate_rejection_ledger_v1.3c60ebab.jsonl"
    )
    if len(ledger) != 111:
        raise ContractError(f"Historical V1 rejection ledger row count changed: {len(ledger)}")
    c001_rows = [
        row for row in ledger if row["pair_id"] == "locked_test_c001_r00"
    ]
    if [int(row["candidate_index"]) for row in c001_rows] != list(range(10)):
        raise ContractError("Historical c001 candidate rejection order changed")
    c001_roster = next(
        row for row in historical_rows if row["pair_id"] == "locked_test_c001_r00"
    )
    if any(
        row["candidate_identity_sha256"]
        != c001_roster["candidates"][int(row["candidate_index"])][
            "candidate_identity_sha256"
        ]
        for row in c001_rows
    ):
        raise ContractError("Historical c001 candidate rejection identity changed")

    state = load_json(snapshot_root / "render_state_v1.ff06d781.json")
    if (
        state.get("planned_pair_count") != 96
        or state.get("completed_pair_count") != 40
        or state.get("pending_pair_count") != 56
        or state.get("pending_pair_ids", [None])[0] != "locked_test_c001_r00"
        or state.get("completed_pair_ids", [None])[-1] != "locked_test_c000_r07"
        or state.get("interrupted_staging_directories") != []
        or state.get("model_outputs_present") is not False
    ):
        raise ContractError("Historical V1 atomic render state changed")
    if paths["run"].exists() and any(path.is_file() for path in paths["run"].rglob("*")):
        raise ContractError("Full benchmark model output exists before migration sealing")
    live_ledger = read_jsonl(planning / "candidate_rejection_ledger_v1.jsonl")
    if live_ledger[: len(ledger)] != ledger:
        raise ContractError("Historical V1 ledger rows were rewritten")
    live_state = load_json(planning / "render_state_v1.json")
    if (
        live_state.get("planned_pair_count") != 96
        or live_state.get("completed_pair_ids", [])[:40]
        != state["completed_pair_ids"]
        or int(live_state.get("completed_pair_count", -1)) < 40
    ):
        raise ContractError("Historical V1 state prefix was rewritten")

    plan = load_json(planning / "full_plan_receipt_v1.json")
    if (
        plan.get("execution_config_sha256")
        != HISTORICAL_V1_BINDINGS["execution_config_sha256"]
        or plan.get("execution_script_sha256")
        != HISTORICAL_V1_BINDINGS["full_plan_generator_script_sha256"]
        or plan.get("pair_roster_sha256")
        != HISTORICAL_V1_BINDINGS["pair_roster_sha256"]
        or plan.get("model_access", {}).get("checkpoint_loaded") is not False
        or plan.get("model_access", {}).get("inference_calls") != 0
    ):
        raise ContractError("Historical V1 full-plan provenance changed")
    inventory = _historical_v1_evidence_inventory(config)
    return {
        "protocol": protocol,
        "historical_rows": historical_rows,
        "roster_validation": roster_validation,
        "candidate_identity_rows_sha256": stable_sha256(candidate_identity_rows),
        "ledger_row_count": len(ledger),
        "c001_rejection_count": len(c001_rows),
        "render_state": state,
        "snapshots": snapshots,
        "evidence_inventory": inventory,
    }


def _roster_extension_authorization() -> dict[str, Any]:
    return {
        "manager_authorization_event_id": ROSTER_EXTENSION_MANAGER_EVENT_ID,
        "owner_session_id": ROSTER_EXTENSION_OWNER_SESSION_ID,
        "manager_session_id": ROSTER_EXTENSION_MANAGER_SESSION_ID,
        "goal_multi_repeat_run_id": ROSTER_EXTENSION_RUN_ID,
        "pass": 55,
        "portfolio_id": ROSTER_EXTENSION_PORTFOLIO_ID,
        "portfolio_lane": ROSTER_EXTENSION_LANE_ID,
        "portfolio_revision": ROSTER_EXTENSION_PORTFOLIO_REVISION,
        "repository": str(PROJECT_ROOT),
        "strategy": "base",
    }


def _roster_extension_contract_payload(
    config: Mapping[str, Any],
    protocol: Mapping[str, Any],
    manifest_sha256: str,
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    planning = full_paths(config)["synthetic"] / "planning"
    return {
        "schema_version": 1,
        "contract": ROSTER_EXTENSION_CONTRACT,
        "status": "SEALED_APPEND_ONLY_ROSTER_EXTENSION_PREOUTCOME_SYNTHETIC_ONLY",
        "authorization": _roster_extension_authorization(),
        "historical_epoch": {
            **copy.deepcopy(HISTORICAL_V1_BINDINGS),
            "candidate_index_range": [0, 9],
            "candidate_count": 960,
            "seed_count": 4800,
            "bytes_may_be_rewritten": False,
        },
        "extension_epoch": {
            "candidate_index_range": [
                ROSTER_EXTENSION_FIRST_CANDIDATE_INDEX,
                ROSTER_EXTENSION_LAST_CANDIDATE_INDEX,
            ],
            "candidates_per_slot": ROSTER_EXTENSION_CANDIDATES_PER_SLOT,
            "pair_count": 96,
            "candidate_count": 96 * ROSTER_EXTENSION_CANDIDATES_PER_SLOT,
            "combined_candidate_index_range": [0, 31],
            "combined_candidate_count": 96 * 32,
            "pair_roster_extension_sha256": manifest_sha256,
            "manifest_presealed_before_candidate_gt_inspection": True,
        },
        "derivation": {
            "protocol_seed_derivation_sha256": stable_sha256(
                protocol["seed_derivation"]
            ),
            "algorithm": protocol["seed_derivation"]["algorithm"],
            "separator": protocol["seed_derivation"]["separator"],
            "input_order": copy.deepcopy(
                protocol["seed_derivation"]["input_order"]
            ),
            "channels": copy.deepcopy(protocol["seed_derivation"]["channels"]),
            "split_base_seeds": copy.deepcopy(
                protocol["seed_derivation"]["split_base_seeds"]
            ),
            "only_versioned_change": "candidate_index_range_10_through_31",
            "source_template_selection": (
                "same_profile_pool_indexed_by_"
                "replicate_index_plus_candidate_index_mod_pool_length"
            ),
            "split_cell_and_replicate_bindings_unchanged": True,
        },
        "selection_and_gates": {
            "candidate_gate_contract_path": display_path(
                planning / "candidate_gate_contract_v1.json"
            ),
            "candidate_gate_contract_sha256": HISTORICAL_V1_BINDINGS[
                "candidate_gate_contract_sha256"
            ],
            "lowest_unattempted_candidate_wins": True,
            "historical_rejection_reinterpretation_allowed": False,
            "threshold_or_gate_relaxation_allowed": False,
            "slot_skip_or_replacement_allowed": False,
            "candidate_31_exhaustion_action": (
                "fail_closed_stop_for_new_manager_decision"
            ),
        },
        "access_guard": {
            "candidate_gt_inspection_during_sealing": False,
            "rendering_calls_during_sealing": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "outcome_inputs": [],
        },
        "validation": copy.deepcopy(dict(validation)),
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _roster_extension_config_payload(
    manifest_sha256: str, contract_sha256: str
) -> dict[str, Any]:
    if sha256_file(DEFAULT_CONFIG) != HISTORICAL_V1_BINDINGS[
        "execution_config_sha256"
    ]:
        raise ContractError("Historical execution config changed before migration")
    config = copy.deepcopy(load_yaml(DEFAULT_CONFIG))
    config["full_benchmark"]["maximum_candidates_per_slot"] = (
        ROSTER_EXTENSION_TOTAL_CANDIDATE_CEILING
    )
    config["roster_extension_epoch"] = {
        "schema_version": 1,
        "contract": ROSTER_EXTENSION_CONTRACT,
        "manager_authorization_event_id": ROSTER_EXTENSION_MANAGER_EVENT_ID,
        "historical_execution_config_sha256": HISTORICAL_V1_BINDINGS[
            "execution_config_sha256"
        ],
        "historical_pair_roster_sha256": HISTORICAL_V1_BINDINGS[
            "pair_roster_sha256"
        ],
        "pair_roster_extension_sha256": manifest_sha256,
        "roster_extension_contract_sha256": contract_sha256,
        "extension_candidate_index_range": [10, 31],
        "combined_candidate_index_range": [0, 31],
        "maximum_candidates_per_slot": 32,
        "candidate_selection": "lowest_unattempted_candidate_index",
        "candidate_31_exhaustion_action": (
            "fail_closed_stop_for_new_manager_decision"
        ),
        "model_access_allowed_during_extension_sealing": False,
        "prediction_or_outcome_access_allowed": False,
        "registered_target_use_allowed": False,
        "outcome_inputs": [],
    }
    return config


def _is_roster_extension_config(config: Mapping[str, Any]) -> bool:
    extension = config.get("roster_extension_epoch")
    if extension is None:
        return False
    valid = (
        isinstance(extension, Mapping)
        and extension.get("schema_version") == 1
        and extension.get("contract") == ROSTER_EXTENSION_CONTRACT
        and extension.get("manager_authorization_event_id")
        == ROSTER_EXTENSION_MANAGER_EVENT_ID
        and extension.get("historical_execution_config_sha256")
        == HISTORICAL_V1_BINDINGS["execution_config_sha256"]
        and extension.get("historical_pair_roster_sha256")
        == HISTORICAL_V1_BINDINGS["pair_roster_sha256"]
        and extension.get("extension_candidate_index_range") == [10, 31]
        and extension.get("combined_candidate_index_range") == [0, 31]
        and extension.get("maximum_candidates_per_slot") == 32
        and config.get("full_benchmark", {}).get("maximum_candidates_per_slot")
        == 32
        and extension.get("candidate_selection")
        == "lowest_unattempted_candidate_index"
        and extension.get("candidate_31_exhaustion_action")
        == "fail_closed_stop_for_new_manager_decision"
        and extension.get("model_access_allowed_during_extension_sealing")
        is False
        and extension.get("prediction_or_outcome_access_allowed") is False
        and extension.get("registered_target_use_allowed") is False
        and extension.get("outcome_inputs") == []
    )
    if not valid:
        raise ContractError("Roster extension execution config changed")
    require_sha256(
        extension.get("pair_roster_extension_sha256"),
        "roster extension manifest",
    )
    require_sha256(
        extension.get("roster_extension_contract_sha256"),
        "roster extension contract",
    )
    return True


def roster_extension_implementation_sha256() -> str:
    functions = (
        derive_roster_extension_seed,
        build_roster_extension,
        validate_roster_extension_rows,
        merge_full_roster_with_extension,
        _historical_v1_evidence_inventory,
        _assert_historical_v1_epoch,
        _roster_extension_contract_payload,
        _roster_extension_config_payload,
        _is_roster_extension_config,
        seal_roster_extension_release,
        validate_roster_extension_release,
    )
    return stable_sha256(
        {
            "contract": ROSTER_EXTENSION_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "authorization": _roster_extension_authorization(),
            "historical_v1_bindings": HISTORICAL_V1_BINDINGS,
        }
    )


def _roster_extension_migration_payload(
    *,
    config: Mapping[str, Any],
    historical: Mapping[str, Any],
    manifest_sha256: str,
    contract_sha256: str,
    extension_config_sha256: str,
    snapshot_manifest_sha256: str,
    evidence_inventory_sha256: str,
    extension_validation: Mapping[str, Any],
) -> dict[str, Any]:
    current_test = (
        PROJECT_ROOT / "tests/test_run_spot_spray_simulation_video_ab_execution_v1.py"
    )
    return {
        "schema_version": 1,
        "contract": ROSTER_EXTENSION_MIGRATION_CONTRACT,
        "status": "PASS_MANAGER_AUTHORIZED_APPEND_ONLY_MIGRATION_SYNTHETIC_ONLY",
        "authorization": _roster_extension_authorization(),
        "historical_v1_epoch": {
            **copy.deepcopy(HISTORICAL_V1_BINDINGS),
            "historical_source_snapshots_manifest_sha256": (
                snapshot_manifest_sha256
            ),
            "historical_evidence_inventory_sha256": evidence_inventory_sha256,
            "historical_candidate_identity_rows_sha256": historical[
                "candidate_identity_rows_sha256"
            ],
            "candidate_count": 960,
            "ledger_row_count": historical["ledger_row_count"],
            "published_pair_count": 40,
            "completed_pair_count": 40,
            "pending_pair_count": 56,
            "first_pending_pair_id": "locked_test_c001_r00",
            "existing_receipts_rebound_to_new_code": False,
        },
        "roster_extension_epoch": {
            "pair_roster_extension_sha256": manifest_sha256,
            "roster_extension_contract_sha256": contract_sha256,
            "extension_execution_config_sha256": extension_config_sha256,
            "extension_execution_script_sha256": sha256_file(Path(__file__)),
            "extension_execution_test_sha256": sha256_file(current_test),
            "extension_implementation_sha256": (
                roster_extension_implementation_sha256()
            ),
            "candidate_index_range": [10, 31],
            "pair_count": 96,
            "candidate_count": 2112,
            "validation": copy.deepcopy(dict(extension_validation)),
        },
        "migration_bridge": {
            "historical_pair_slot_identities_preserved": True,
            "historical_candidate_0_9_bytes_preserved": True,
            "extension_candidates_are_append_only": True,
            "lowest_unattempted_candidate_wins": True,
            "old_receipt_mutation_allowed": False,
            "old_rejection_reinterpretation_allowed": False,
            "gate_or_threshold_relaxation_allowed": False,
            "slot_skip_or_replacement_allowed": False,
            "candidate_31_exhaustion_action": (
                "fail_closed_stop_for_new_manager_decision"
            ),
        },
        "access_guard": {
            "candidate_gt_inspected": False,
            "rendering_calls": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "outcome_inputs": [],
        },
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _roster_extension_execution_lock_payloads(
    config: Mapping[str, Any],
    *,
    extension_config_sha256: str,
    manifest_sha256: str,
    migration_bridge_sha256: str,
) -> dict[str, dict[str, Any]]:
    planning = full_paths(config)["synthetic"] / "planning"
    historical_locks = {
        "full_render": load_json(planning / "full_render_execution_lock_v1.json"),
        "gt_scout": load_json(planning / "gt_scout_execution_lock_v1.json"),
        "locked_test_batch": load_json(
            planning / "locked_test_render_batch_execution_lock_v1.json"
        ),
        "locked_test_recovery": load_json(
            planning
            / "locked_test_gt_source_cardinality_recovery_execution_lock_v1.json"
        ),
    }
    common = {
        "schema_version": 1,
        "status": "SEALED_ROSTER_EXTENSION_EXECUTION_MODEL_FREE_SYNTHETIC_ONLY",
        "manager_authorization_event_id": ROSTER_EXTENSION_MANAGER_EVENT_ID,
        "historical_pair_roster_sha256": HISTORICAL_V1_BINDINGS[
            "pair_roster_sha256"
        ],
        "pair_roster_extension_sha256": manifest_sha256,
        "extension_execution_config_sha256": extension_config_sha256,
        "migration_bridge_sha256": migration_bridge_sha256,
        "candidate_index_range": [10, 31],
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "outcome_inputs_allowed": False,
        "registered_targets_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    return {
        "full_render_execution_lock_extension_v1.json": {
            **common,
            "contract": (
                "spot_spray_simulation_video_ab_full_render_execution_"
                "roster_extension_v1"
            ),
            "historical_execution_lock_sha256": HISTORICAL_V1_BINDINGS[
                "full_render_execution_lock_sha256"
            ],
            "historical_execution_config_sha256": historical_locks[
                "full_render"
            ]["execution_config_sha256"],
            "render_implementation_sha256": full_render_implementation_sha256(),
            "execution_lock_dispatch_sha256": stable_sha256(
                inspect.getsource(_dispatch_full_render_execution_lock)
            ),
            "composed_scene_patch_sha256": historical_locks["full_render"][
                "composed_scene_patch_sha256"
            ],
        },
        "gt_scout_execution_lock_extension_v1.json": {
            **common,
            "contract": (
                "spot_spray_simulation_video_ab_gt_scout_execution_"
                "roster_extension_v1"
            ),
            "historical_execution_lock_sha256": HISTORICAL_V1_BINDINGS[
                "gt_scout_execution_lock_sha256"
            ],
            "historical_full_render_execution_lock_sha256": (
                HISTORICAL_V1_BINDINGS["full_render_execution_lock_sha256"]
            ),
            "gt_scout_implementation_sha256": gt_scout_implementation_sha256(),
            "execution_lock_dispatch_sha256": stable_sha256(
                inspect.getsource(_dispatch_gt_scout_execution_lock)
            ),
            "composed_gt_scout_patch_sha256": historical_locks["gt_scout"][
                "composed_gt_scout_patch_sha256"
            ],
            "rejection_authority": (
                "unchanged_frozen_semantic_and_eligibility_failures_only"
            ),
            "acceptance_authority": "none_unchanged_full_renderer_required",
        },
        "locked_test_render_batch_execution_lock_extension_v1.json": {
            **common,
            "contract": (
                "spot_spray_simulation_video_ab_locked_test_render_batch_"
                "roster_extension_v1"
            ),
            "historical_execution_lock_sha256": HISTORICAL_V1_BINDINGS[
                "locked_test_render_batch_execution_lock_sha256"
            ],
            "historical_batch_implementation_sha256": historical_locks[
                "locked_test_batch"
            ]["locked_test_render_batch_implementation_sha256"],
            "locked_test_render_batch_implementation_sha256": (
                locked_test_render_batch_implementation_sha256()
            ),
            "execution_lock_dispatch_sha256": stable_sha256(
                inspect.getsource(
                    _dispatch_locked_test_render_batch_execution_lock
                )
            ),
            "target_scope": (
                "explicit_contiguous_canonical_locked_test_slots_only"
            ),
            "calibration_render_completion_required": True,
            "new_pair_limit_required": True,
            "durable_intent_required": True,
            "render_and_machine_audit_only": True,
        },
        "locked_test_recovery_execution_lock_extension_v1.json": {
            **common,
            "contract": (
                "spot_spray_simulation_video_ab_locked_test_zero_source_"
                "weed_recovery_roster_extension_v1"
            ),
            "historical_execution_lock_sha256": HISTORICAL_V1_BINDINGS[
                "locked_test_recovery_execution_lock_sha256"
            ],
            "historical_recovery_implementation_sha256": historical_locks[
                "locked_test_recovery"
            ]["recovery_implementation_sha256"],
            "recovery_implementation_sha256": (
                locked_test_gt_source_cardinality_recovery_implementation_sha256()
            ),
            "execution_lock_dispatch_sha256": stable_sha256(
                inspect.getsource(_dispatch_locked_test_recovery_execution_lock)
            ),
            "target_scope": (
                "earliest_pending_locked_test_candidate_in_active_batch_only"
            ),
            "rejection_authority": (
                "exact_locked_validator_zero_source_weed_failure_only"
            ),
            "acceptance_authority": "none",
        },
    }


def _roster_extension_release_payload(
    *,
    config: Mapping[str, Any],
    migration: Mapping[str, Any],
    migration_bridge_sha256: str,
    manifest_sha256: str,
    contract_sha256: str,
    extension_config_sha256: str,
    lock_hashes: Mapping[str, str],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "contract": ROSTER_EXTENSION_RELEASE_CONTRACT,
        "status": "SEALED_PARENT_EXECUTION_RELEASE_SYNTHETIC_ONLY",
        "authorization": _roster_extension_authorization(),
        "historical_v1_epoch_identity_sha256": stable_sha256(
            migration["historical_v1_epoch"]
        ),
        "roster_extension_epoch_identity_sha256": stable_sha256(
            migration["roster_extension_epoch"]
        ),
        "manager_authorization_migration_bridge_sha256": (
            migration_bridge_sha256
        ),
        "historical_pair_roster_sha256": HISTORICAL_V1_BINDINGS[
            "pair_roster_sha256"
        ],
        "pair_roster_extension_sha256": manifest_sha256,
        "roster_extension_contract_sha256": contract_sha256,
        "extension_execution_config_sha256": extension_config_sha256,
        "extension_execution_script_sha256": sha256_file(Path(__file__)),
        "extension_execution_test_sha256": sha256_file(
            PROJECT_ROOT
            / "tests/test_run_spot_spray_simulation_video_ab_execution_v1.py"
        ),
        "execution_locks": dict(sorted(lock_hashes.items())),
        "candidate_index_epochs": {
            "historical_v1": [0, 9],
            "roster_extension_v1": [10, 31],
            "combined": [0, 31],
        },
        "selection_rule": "lowest_unattempted_candidate_index",
        "candidate_31_exhaustion_action": (
            "fail_closed_stop_for_new_manager_decision"
        ),
        "old_receipts_rebound_to_new_implementation": False,
        "model_or_outcome_access_during_release_sealing": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    payload["release_identity_sha256"] = stable_sha256(payload)
    return payload


def _roster_extension_pass55_payload(
    *,
    config: Mapping[str, Any],
    root: Path,
    historical: Mapping[str, Any],
    extension_validation: Mapping[str, Any],
    release: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.name != "pass55_validation_receipt.json"
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]
    return {
        "schema_version": 1,
        "contract": ROSTER_EXTENSION_PASS55_CONTRACT,
        "status": "READY_FOR_MANAGER_VALIDATION",
        "goal_multi_repeat_run_id": ROSTER_EXTENSION_RUN_ID,
        "pass": 55,
        "authorization_event_id": ROSTER_EXTENSION_MANAGER_EVENT_ID,
        "parent_execution_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "historical_v1": {
            "protocol_sha256": HISTORICAL_V1_BINDINGS["protocol_sha256"],
            "execution_config_sha256": HISTORICAL_V1_BINDINGS[
                "execution_config_sha256"
            ],
            "execution_script_sha256": HISTORICAL_V1_BINDINGS[
                "execution_script_sha256"
            ],
            "execution_test_sha256": HISTORICAL_V1_BINDINGS[
                "execution_test_sha256"
            ],
            "pair_roster_sha256": HISTORICAL_V1_BINDINGS[
                "pair_roster_sha256"
            ],
            "render_state_sha256": HISTORICAL_V1_BINDINGS[
                "render_state_sha256"
            ],
            "candidate_rejection_ledger_sha256": HISTORICAL_V1_BINDINGS[
                "candidate_rejection_ledger_sha256"
            ],
            "pass54_validation_receipt_sha256": HISTORICAL_V1_BINDINGS[
                "pass54_validation_receipt_sha256"
            ],
            "completed_pair_count": 40,
            "ledger_row_count": 111,
            "candidate_0_9_identity_rows_sha256": historical[
                "candidate_identity_rows_sha256"
            ],
            "immutable_evidence_inventory_sha256": historical[
                "evidence_inventory"
            ]["inventory_sha256"],
            "all_original_bytes_unchanged": True,
        },
        "extension": {
            "candidate_index_range": [10, 31],
            "all_96_slots_presealed": True,
            "candidate_count": extension_validation[
                "extension_candidate_count"
            ],
            "unique_candidate_identity_count": extension_validation[
                "unique_extension_candidate_identity_count"
            ],
            "unique_seed_count": extension_validation[
                "unique_extension_seed_count"
            ],
            "combined_candidate_count": extension_validation[
                "combined_candidate_count"
            ],
            "combined_unique_seed_count": extension_validation[
                "unique_combined_seed_count"
            ],
            "lowest_unattempted_candidate_wins": True,
            "candidate_31_exhaustion_action": (
                "fail_closed_stop_for_new_manager_decision"
            ),
        },
        "current_implementation": {
            "execution_script_sha256": sha256_file(Path(__file__)),
            "execution_test_sha256": sha256_file(
                PROJECT_ROOT
                / "tests/test_run_spot_spray_simulation_video_ab_execution_v1.py"
            ),
            "roster_extension_implementation_sha256": (
                roster_extension_implementation_sha256()
            ),
        },
        "artifact_inventory": {
            "files": artifact_rows,
            "file_count": len(artifact_rows),
            "inventory_sha256": stable_sha256(artifact_rows),
        },
        "access_guard": {
            "candidate_10_started": False,
            "c001_attempted_candidate_indices": list(range(10)),
            "candidate_gt_inspected": False,
            "rendering_calls": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "outcome_inputs": [],
            "staging_directories": [],
        },
        "next_authorized_action": (
            "resume_locked_test_c001_r00_at_candidate_10_under_"
            "sealed_extension_release"
        ),
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _roster_extension_required_relative_files() -> list[str]:
    return [
        "execution_config_v1_plus_roster_extension_v1.yaml",
        "execution_locks/full_render_execution_lock_extension_v1.json",
        "execution_locks/gt_scout_execution_lock_extension_v1.json",
        "execution_locks/locked_test_recovery_execution_lock_extension_v1.json",
        "execution_locks/locked_test_render_batch_execution_lock_extension_v1.json",
        "execution_release_v1_plus_roster_extension_v1.json",
        "historical_source_snapshots_v1.json",
        "historical_v1_evidence_inventory_v1.json",
        "manager_authorization_migration_bridge_v1.json",
        "pair_roster_extension_v1.jsonl",
        "pass55_validation_receipt.json",
        "roster_extension_contract_v1.json",
    ]


def _assert_no_extension_execution_started(config: Mapping[str, Any]) -> None:
    paths = full_paths(config)
    planning = paths["synthetic"] / "planning"
    ledger = read_jsonl(planning / "candidate_rejection_ledger_v1.jsonl")
    if any(int(row["candidate_index"]) >= 10 for row in ledger):
        raise ContractError("Extension candidate was attempted before release sealing")
    candidate_pattern = re.compile(r"^candidate_(\d+)$")
    for path in planning.rglob("candidate_*"):
        match = candidate_pattern.fullmatch(path.name)
        if match and int(match.group(1)) >= 10:
            raise ContractError("Extension candidate evidence exists before sealing")
    staging = [
        path
        for root in (paths["synthetic"] / "work", planning / "gt_scout_v1")
        if root.exists()
        for path in root.rglob(".partial-*")
    ]
    if staging:
        raise ContractError(f"Staging exists before extension sealing: {staging[:3]}")
    if paths["run"].exists() and any(path.is_file() for path in paths["run"].rglob("*")):
        raise ContractError("Model output exists before extension sealing")


def seal_roster_extension_release(config_path: Path) -> dict[str, Any]:
    """Seal candidate identities 10..31 and no candidate evidence or rendering."""
    config_path = config_path.expanduser().resolve()
    if (
        config_path != DEFAULT_CONFIG.resolve()
        or sha256_file(config_path)
        != HISTORICAL_V1_BINDINGS["execution_config_sha256"]
    ):
        raise ContractError("Roster extension sealing requires the immutable V1 config")
    config = load_config(config_path)
    paths = roster_extension_paths(config)
    root = paths["synthetic"]
    docs = paths["docs"]
    planning = full_paths(config)["synthetic"] / "planning"
    partials = sorted(planning.glob(".partial-roster-extension-v1-*"))
    docs_partials = sorted(docs.parent.glob(".partial-roster-extension-v1-*"))
    if partials or docs_partials:
        raise ContractError("Partial roster extension publication exists")
    if root.exists() or docs.exists():
        if not root.is_dir() or not docs.is_dir():
            raise ContractError("Roster extension publication is partial")
        return validate_roster_extension_release(paths["extension_config"])

    _assert_no_extension_execution_started(config)
    historical = _assert_historical_v1_epoch(
        config, require_live_boundary=True
    )
    template_path = planning / "template_inventory_v1.json"
    plan = load_json(planning / "full_plan_receipt_v1.json")
    if sha256_file(template_path) != plan["template_inventory_sha256"]:
        raise ContractError("Historical template inventory changed")
    template_inventory = load_json(template_path)
    first = build_roster_extension(
        historical["historical_rows"],
        historical["protocol"],
        template_inventory,
    )
    second = build_roster_extension(
        historical["historical_rows"],
        historical["protocol"],
        template_inventory,
    )
    if first != second:
        raise ContractError("Roster extension derivation is not deterministic")
    extension_validation = validate_roster_extension_rows(
        first,
        historical["historical_rows"],
        historical["protocol"],
        template_inventory,
    )

    staging = planning / f".partial-roster-extension-v1-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        manifest_path = staging / "pair_roster_extension_v1.jsonl"
        write_jsonl(manifest_path, first)
        manifest_sha256 = sha256_file(manifest_path)

        contract = _roster_extension_contract_payload(
            config,
            historical["protocol"],
            manifest_sha256,
            extension_validation,
        )
        contract_path = staging / "roster_extension_contract_v1.json"
        write_json(contract_path, contract)
        contract_sha256 = sha256_file(contract_path)

        extension_config = _roster_extension_config_payload(
            manifest_sha256, contract_sha256
        )
        extension_config_path = (
            staging / "execution_config_v1_plus_roster_extension_v1.yaml"
        )
        extension_config_path.write_text(
            yaml.safe_dump(extension_config, sort_keys=False),
            encoding="utf-8",
        )
        extension_config_sha256 = sha256_file(extension_config_path)

        snapshot_manifest_path = staging / "historical_source_snapshots_v1.json"
        write_json(snapshot_manifest_path, historical["snapshots"])
        snapshot_manifest_sha256 = sha256_file(snapshot_manifest_path)
        evidence_inventory_path = staging / "historical_v1_evidence_inventory_v1.json"
        write_json(evidence_inventory_path, historical["evidence_inventory"])
        evidence_inventory_sha256 = sha256_file(evidence_inventory_path)

        migration = _roster_extension_migration_payload(
            config=config,
            historical=historical,
            manifest_sha256=manifest_sha256,
            contract_sha256=contract_sha256,
            extension_config_sha256=extension_config_sha256,
            snapshot_manifest_sha256=snapshot_manifest_sha256,
            evidence_inventory_sha256=evidence_inventory_sha256,
            extension_validation=extension_validation,
        )
        migration["migration_bridge_identity_sha256"] = stable_sha256(migration)
        migration_path = staging / "manager_authorization_migration_bridge_v1.json"
        write_json(migration_path, migration)
        migration_sha256 = sha256_file(migration_path)

        lock_payloads = _roster_extension_execution_lock_payloads(
            config,
            extension_config_sha256=extension_config_sha256,
            manifest_sha256=manifest_sha256,
            migration_bridge_sha256=migration_sha256,
        )
        lock_hashes: dict[str, str] = {}
        for name, payload in sorted(lock_payloads.items()):
            lock_path = staging / "execution_locks" / name
            write_json(lock_path, payload)
            lock_hashes[name] = sha256_file(lock_path)

        release = _roster_extension_release_payload(
            config=config,
            migration=migration,
            migration_bridge_sha256=migration_sha256,
            manifest_sha256=manifest_sha256,
            contract_sha256=contract_sha256,
            extension_config_sha256=extension_config_sha256,
            lock_hashes=lock_hashes,
        )
        release_path = staging / "execution_release_v1_plus_roster_extension_v1.json"
        write_json(release_path, release)

        pass55 = _roster_extension_pass55_payload(
            config=config,
            root=staging,
            historical=historical,
            extension_validation=extension_validation,
            release=release,
        )
        write_json(staging / "pass55_validation_receipt.json", pass55)
        observed = sorted(
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        )
        if observed != _roster_extension_required_relative_files():
            raise ContractError("Roster extension package is partial or has extra files")
        staging.replace(root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    docs_staging = docs.parent / f".partial-roster-extension-v1-{uuid.uuid4().hex}"
    docs_staging.mkdir(parents=False, exist_ok=False)
    try:
        for relative in _roster_extension_required_relative_files():
            source = root / relative
            target = docs_staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        docs_staging.replace(docs)
    except Exception:
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
        raise
    return validate_roster_extension_release(paths["extension_config"])


def validate_roster_extension_release(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    historical_config = load_config(DEFAULT_CONFIG)
    paths = roster_extension_paths(historical_config)
    root = paths["synthetic"]
    docs = paths["docs"]
    if config_path != paths["extension_config"].resolve():
        raise ContractError("Noncanonical roster extension config path")
    if not root.is_dir() or not docs.is_dir():
        raise ContractError("Roster extension release is missing or partial")
    planning = full_paths(historical_config)["synthetic"] / "planning"
    if list(planning.glob(".partial-roster-extension-v1-*")) or list(
        docs.parent.glob(".partial-roster-extension-v1-*")
    ):
        raise ContractError("Partial roster extension publication exists")
    observed_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    if observed_files != _roster_extension_required_relative_files():
        raise ContractError("Roster extension release file set changed")
    docs_files = sorted(
        path.relative_to(docs).as_posix()
        for path in docs.rglob("*")
        if path.is_file()
    )
    if docs_files != observed_files or any(
        sha256_file(root / relative) != sha256_file(docs / relative)
        for relative in observed_files
    ):
        raise ContractError("Roster extension docs mirror changed")

    extension_config = load_config(config_path)
    if not _is_roster_extension_config(extension_config):
        raise ContractError("Canonical extension config lacks extension contract")
    historical = _assert_historical_v1_epoch(
        historical_config, require_live_boundary=False
    )
    template_path = planning / "template_inventory_v1.json"
    plan = load_json(planning / "full_plan_receipt_v1.json")
    if sha256_file(template_path) != plan["template_inventory_sha256"]:
        raise ContractError("Historical template inventory changed")
    template_inventory = load_json(template_path)
    extension_rows = read_jsonl(paths["manifest"])
    extension_validation = validate_roster_extension_rows(
        extension_rows,
        historical["historical_rows"],
        historical["protocol"],
        template_inventory,
    )
    manifest_sha256 = sha256_file(paths["manifest"])
    contract = load_json(paths["contract"])
    expected_contract = _roster_extension_contract_payload(
        historical_config,
        historical["protocol"],
        manifest_sha256,
        extension_validation,
    )
    if contract != expected_contract:
        raise ContractError("Roster extension contract changed")
    contract_sha256 = sha256_file(paths["contract"])
    expected_config = _roster_extension_config_payload(
        manifest_sha256, contract_sha256
    )
    if extension_config != expected_config:
        raise ContractError("Roster extension execution config changed")
    if (
        extension_config["roster_extension_epoch"][
            "pair_roster_extension_sha256"
        ]
        != manifest_sha256
        or extension_config["roster_extension_epoch"][
            "roster_extension_contract_sha256"
        ]
        != contract_sha256
    ):
        raise ContractError("Roster extension config artifact binding changed")

    snapshots = load_json(paths["snapshot_manifest"])
    if snapshots != historical["snapshots"]:
        raise ContractError("Historical source snapshot manifest changed")
    evidence_inventory = load_json(paths["evidence_inventory"])
    if evidence_inventory != historical["evidence_inventory"]:
        raise ContractError("Historical V1 evidence inventory changed")

    migration = load_json(paths["migration_bridge"])
    observed_migration_identity = migration.pop(
        "migration_bridge_identity_sha256", None
    )
    expected_migration = _roster_extension_migration_payload(
        config=historical_config,
        historical=historical,
        manifest_sha256=manifest_sha256,
        contract_sha256=contract_sha256,
        extension_config_sha256=sha256_file(config_path),
        snapshot_manifest_sha256=sha256_file(paths["snapshot_manifest"]),
        evidence_inventory_sha256=sha256_file(paths["evidence_inventory"]),
        extension_validation=extension_validation,
    )
    if (
        migration != expected_migration
        or observed_migration_identity != stable_sha256(expected_migration)
    ):
        raise ContractError("Manager authorization migration bridge changed")
    migration_with_identity = {
        **migration,
        "migration_bridge_identity_sha256": observed_migration_identity,
    }
    migration_sha256 = sha256_file(paths["migration_bridge"])

    expected_locks = _roster_extension_execution_lock_payloads(
        historical_config,
        extension_config_sha256=sha256_file(config_path),
        manifest_sha256=manifest_sha256,
        migration_bridge_sha256=migration_sha256,
    )
    lock_hashes: dict[str, str] = {}
    for name, expected in sorted(expected_locks.items()):
        path = paths["execution_locks"] / name
        if load_json(path) != expected:
            raise ContractError(f"Roster extension execution lock changed: {name}")
        lock_hashes[name] = sha256_file(path)

    release = load_json(paths["release"])
    expected_release = _roster_extension_release_payload(
        config=historical_config,
        migration=migration_with_identity,
        migration_bridge_sha256=migration_sha256,
        manifest_sha256=manifest_sha256,
        contract_sha256=contract_sha256,
        extension_config_sha256=sha256_file(config_path),
        lock_hashes=lock_hashes,
    )
    if release != expected_release:
        raise ContractError("Parent roster extension execution release changed")
    release_identity = release.pop("release_identity_sha256", None)
    if release_identity != stable_sha256(release):
        raise ContractError("Parent execution release identity changed")
    release["release_identity_sha256"] = release_identity

    pass55 = load_json(paths["pass55_receipt"])
    expected_pass55 = _roster_extension_pass55_payload(
        config=historical_config,
        root=root,
        historical=historical,
        extension_validation=extension_validation,
        release=release,
    )
    if pass55 != expected_pass55:
        raise ContractError("Pass55 roster extension validation receipt changed")
    if pass55["access_guard"] != {
        "candidate_10_started": False,
        "c001_attempted_candidate_indices": list(range(10)),
        "candidate_gt_inspected": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "outcome_inputs": [],
        "staging_directories": [],
    }:
        raise ContractError("Pass55 zero-access boundary changed")
    return {
        "status": pass55["status"],
        "parent_execution_release_identity_sha256": release_identity,
        "manager_authorization_migration_bridge_sha256": migration_sha256,
        "pair_roster_extension_sha256": manifest_sha256,
        "roster_extension_contract_sha256": contract_sha256,
        "extension_execution_config_path": display_path(config_path),
        "extension_execution_config_sha256": sha256_file(config_path),
        "historical_pair_roster_sha256": HISTORICAL_V1_BINDINGS[
            "pair_roster_sha256"
        ],
        "historical_state_sha256": HISTORICAL_V1_BINDINGS[
            "render_state_sha256"
        ],
        "historical_ledger_sha256": HISTORICAL_V1_BINDINGS[
            "candidate_rejection_ledger_sha256"
        ],
        "validation": extension_validation,
        "execution_locks": lock_hashes,
        "candidate_10_started": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "outcome_inputs": [],
        "synthetic_only": True,
    }


def _runtime_compatibility_required_relative_files() -> list[str]:
    return [
        (
            "release_v1/"
            "execution_config_v1_plus_roster_extension_v1_"
            "runtime_compatibility_v1.yaml"
        ),
        (
            "release_v1/"
            "execution_release_v1_plus_roster_extension_v1_"
            "runtime_compatibility_v1.json"
        ),
        "release_v1/pass58_validation_receipt.json",
        "release_v1/runtime_compatibility_adapter_lock_v1.json",
        "release_v1/runtime_compatibility_bridge_v1.json",
        (
            "source_snapshots/"
            "run_spot_spray_simulation_video_ab_execution_v1.pass55.py"
        ),
        (
            "source_snapshots/"
            "test_run_spot_spray_simulation_video_ab_execution_v1.pass55.py"
        ),
    ]


def _validate_frozen_pass55_release(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate immutable Pass55 bytes without rebinding them to this script."""
    paths = roster_extension_paths(config)
    root = paths["synthetic"]
    docs = paths["docs"]
    expected_files = _roster_extension_required_relative_files()
    observed_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    docs_files = sorted(
        path.relative_to(docs).as_posix()
        for path in docs.rglob("*")
        if path.is_file()
    )
    if observed_files != expected_files or docs_files != expected_files:
        raise ContractError("Frozen Pass55 release file set changed")
    if any(
        sha256_file(root / relative) != sha256_file(docs / relative)
        for relative in expected_files
    ):
        raise ContractError("Frozen Pass55 docs mirror changed")
    if sha256_file(paths["extension_config"]) != ROSTER_EXTENSION_CONFIG_SHA256:
        raise ContractError("Frozen Pass55 extension config changed")
    if sha256_file(paths["release"]) != ROSTER_EXTENSION_RELEASE_FILE_SHA256:
        raise ContractError("Frozen Pass55 parent release bytes changed")
    if sha256_file(paths["pass55_receipt"]) != PASS55_VALIDATION_RECEIPT_SHA256:
        raise ContractError("Frozen Pass55 validation receipt changed")

    receipt = load_json(paths["pass55_receipt"])
    inventory = receipt.get("artifact_inventory")
    if not isinstance(inventory, Mapping) or inventory.get(
        "inventory_sha256"
    ) != PASS55_ARTIFACT_INVENTORY_SHA256:
        raise ContractError("Frozen Pass55 artifact inventory identity changed")
    observed_inventory = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.name != "pass55_validation_receipt.json"
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]
    if (
        inventory.get("files") != observed_inventory
        or inventory.get("file_count") != len(observed_inventory)
        or stable_sha256(observed_inventory) != PASS55_ARTIFACT_INVENTORY_SHA256
    ):
        raise ContractError("Frozen Pass55 artifact bytes changed")
    current = receipt.get("current_implementation")
    if not isinstance(current, Mapping) or (
        current.get("execution_script_sha256") != PASS55_EXECUTION_SCRIPT_SHA256
        or current.get("execution_test_sha256") != PASS55_EXECUTION_TEST_SHA256
    ):
        raise ContractError("Frozen Pass55 source identities changed")
    release = load_json(paths["release"])
    if (
        release.get("release_identity_sha256")
        != ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        or receipt.get("parent_execution_release_identity_sha256")
        != ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        or release.get("extension_execution_config_sha256")
        != ROSTER_EXTENSION_CONFIG_SHA256
        or release.get("extension_execution_script_sha256")
        != PASS55_EXECUTION_SCRIPT_SHA256
        or release.get("extension_execution_test_sha256")
        != PASS55_EXECUTION_TEST_SHA256
    ):
        raise ContractError("Frozen Pass55 parent release semantics changed")
    lock_hashes = release.get("execution_locks")
    if not isinstance(lock_hashes, Mapping):
        raise ContractError("Frozen Pass55 execution-lock inventory is missing")
    for name, expected in lock_hashes.items():
        path = paths["execution_locks"] / str(name)
        if not path.is_file() or sha256_file(path) != expected:
            raise ContractError(f"Frozen Pass55 execution lock changed: {name}")
    extension_validation = load_json(paths["contract"]).get("validation")
    if not isinstance(extension_validation, Mapping):
        raise ContractError("Frozen Pass55 extension validation is missing")
    return {
        "status": "PASS_FROZEN_PASS55_PARENT_RELEASE_SYNTHETIC_ONLY",
        "parent_execution_release_identity_sha256": (
            ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        ),
        "extension_execution_config_path": display_path(
            paths["extension_config"]
        ),
        "extension_execution_config_sha256": ROSTER_EXTENSION_CONFIG_SHA256,
        "pass55_execution_script_sha256": PASS55_EXECUTION_SCRIPT_SHA256,
        "pass55_execution_test_sha256": PASS55_EXECUTION_TEST_SHA256,
        "pass55_validation_receipt_sha256": PASS55_VALIDATION_RECEIPT_SHA256,
        "pass55_artifact_inventory_sha256": PASS55_ARTIFACT_INVENTORY_SHA256,
        "execution_locks": dict(lock_hashes),
        "validation": copy.deepcopy(dict(extension_validation)),
        "model_loaded": False,
        "inference_calls": 0,
        "outcome_inputs": [],
        "synthetic_only": True,
    }


def _runtime_compatibility_alias_payload(
    config: Mapping[str, Any], parent: Mapping[str, Any]
) -> dict[str, str]:
    paths = roster_extension_paths(config)
    scout_path = paths["execution_locks"] / "gt_scout_execution_lock_extension_v1.json"
    render_path = paths["execution_locks"] / "full_render_execution_lock_extension_v1.json"
    scout = load_json(scout_path)
    render = load_json(render_path)
    if any(name in scout for name in RUNTIME_COMPATIBILITY_ALIASES):
        raise ContractError("Runtime alias collides with immutable Pass55 scout lock")
    aliases = {
        "sealed_full_render_execution_lock_sha256": scout.get(
            "historical_full_render_execution_lock_sha256"
        ),
        "sealed_full_render_implementation_sha256": render.get(
            "render_implementation_sha256"
        ),
    }
    if (
        aliases != RUNTIME_COMPATIBILITY_ALIASES
        or parent.get("execution_locks", {}).get(
            "gt_scout_execution_lock_extension_v1.json"
        )
        != sha256_file(scout_path)
        or parent.get("execution_locks", {}).get(
            "full_render_execution_lock_extension_v1.json"
        )
        != sha256_file(render_path)
    ):
        raise ContractError("Runtime aliases do not derive from immutable locks")
    return aliases


def _runtime_compatibility_source_snapshots(
    config: Mapping[str, Any], *, require_docs_mirror: bool
) -> list[dict[str, Any]]:
    paths = runtime_compatibility_paths(config)
    specs = [
        (
            "execution_script_pass55",
            paths["script_snapshot"],
            PASS55_EXECUTION_SCRIPT_SHA256,
        ),
        (
            "execution_test_pass55",
            paths["test_snapshot"],
            PASS55_EXECUTION_TEST_SHA256,
        ),
    ]
    rows = []
    for role, path, expected in specs:
        if not path.is_file() or sha256_file(path) != expected:
            raise ContractError(f"Pass55 source snapshot changed: {role}")
        relative = path.relative_to(paths["synthetic"])
        docs_path = paths["docs"] / relative
        if require_docs_mirror and (
            not docs_path.is_file() or sha256_file(docs_path) != expected
        ):
            raise ContractError(f"Pass55 source snapshot docs mirror changed: {role}")
        rows.append(
            {
                "role": role,
                "path": display_path(path),
                "sha256": expected,
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def _runtime_compatibility_bridge_payload(
    config: Mapping[str, Any],
    parent: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    aliases: Mapping[str, str],
) -> dict[str, Any]:
    failure_path = _runtime_compatibility_failure_receipt_path(config)
    intent_path = _runtime_compatibility_failed_intent_path(config)
    if (
        not failure_path.is_file()
        or sha256_file(failure_path) != PASS57_FAILURE_RECEIPT_SHA256
        or not intent_path.is_file()
        or sha256_file(intent_path) != PASS56_FAILED_BATCH_INTENT_SHA256
    ):
        raise ContractError("Pass57 failure or failed-intent bytes changed")
    failure = load_json(failure_path)
    if (
        failure.get("status")
        != "FAIL_CLOSED_EXTENSION_LOCK_ADAPTER_COMPATIBILITY_ERROR_SYNTHETIC_ONLY"
        or failure.get("diagnosis", {}).get("missing_runtime_aliases")
        != list(RUNTIME_COMPATIBILITY_ALIASES)
        or failure.get("diagnosis", {}).get("authorized_alias_values")
        != dict(aliases)
    ):
        raise ContractError("Pass57 failure semantics changed")
    return {
        "schema_version": 1,
        "contract": RUNTIME_COMPATIBILITY_CONTRACT,
        "status": "SEALED_APPEND_ONLY_RUNTIME_COMPATIBILITY_BRIDGE_SYNTHETIC_ONLY",
        "authorization": {
            "event_id": RUNTIME_COMPATIBILITY_EVENT_ID,
            "goal_multi_repeat_run_id": ROSTER_EXTENSION_RUN_ID,
            "pass": 58,
            "owner_session_id": ROSTER_EXTENSION_OWNER_SESSION_ID,
            "strategy": "base",
        },
        "parent": {
            "execution_release_identity_sha256": (
                ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
            ),
            "execution_release_file_sha256": ROSTER_EXTENSION_RELEASE_FILE_SHA256,
            "extension_execution_config_sha256": ROSTER_EXTENSION_CONFIG_SHA256,
            "pass55_validation_receipt_sha256": PASS55_VALIDATION_RECEIPT_SHA256,
            "pass55_artifact_inventory_sha256": PASS55_ARTIFACT_INVENTORY_SHA256,
            "execution_locks": copy.deepcopy(parent["execution_locks"]),
            "bytes_mutated_or_rebound": False,
        },
        "failure_bridge": {
            "pass57_failure_receipt_path": display_path(failure_path),
            "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
            "failed_batch_intent_path": display_path(intent_path),
            "failed_batch_intent_sha256": PASS56_FAILED_BATCH_INTENT_SHA256,
            "failed_candidate_index": 10,
            "failed_candidate_committed": False,
            "failed_intent_bytes_mutated": False,
        },
        "pass55_source_snapshots": copy.deepcopy(list(snapshots)),
        "runtime_adapter": {
            "base_lock": "gt_scout_execution_lock_extension_v1.json",
            "base_lock_sha256": parent["execution_locks"][
                "gt_scout_execution_lock_extension_v1.json"
            ],
            "added_aliases": dict(aliases),
            "added_alias_count": 2,
            "only_added_runtime_keys": sorted(aliases),
            "base_lock_bytes_mutated": False,
            "gate_threshold_seed_candidate_or_selection_change": False,
        },
        "access_guard": {
            "candidate_gt_inspected": False,
            "candidate_10_started": False,
            "rendering_calls": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "outcome_inputs": [],
        },
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _runtime_compatibility_config_payload(
    bridge_sha256: str,
) -> dict[str, Any]:
    require_sha256(bridge_sha256, "runtime compatibility bridge")
    historical_config = load_config(DEFAULT_CONFIG)
    parent_path = roster_extension_paths(historical_config)["extension_config"]
    if sha256_file(parent_path) != ROSTER_EXTENSION_CONFIG_SHA256:
        raise ContractError("Parent extension config changed before patch config")
    config = copy.deepcopy(load_config(parent_path))
    config["runtime_compatibility_epoch"] = {
        "schema_version": 1,
        "contract": RUNTIME_COMPATIBILITY_CONTRACT,
        "authorization_event_id": RUNTIME_COMPATIBILITY_EVENT_ID,
        "parent_execution_release_identity_sha256": (
            ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        ),
        "parent_extension_execution_config_sha256": (
            ROSTER_EXTENSION_CONFIG_SHA256
        ),
        "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
        "runtime_compatibility_bridge_sha256": bridge_sha256,
        "added_runtime_aliases": copy.deepcopy(RUNTIME_COMPATIBILITY_ALIASES),
        "only_added_runtime_keys": sorted(RUNTIME_COMPATIBILITY_ALIASES),
        "base_lock_bytes_mutated": False,
        "gate_threshold_seed_candidate_or_selection_change": False,
        "model_access_allowed": False,
        "prediction_or_outcome_access_allowed": False,
        "registered_target_use_allowed": False,
        "outcome_inputs": [],
    }
    return config


def _is_runtime_compatibility_config(config: Mapping[str, Any]) -> bool:
    epoch = config.get("runtime_compatibility_epoch")
    if epoch is None:
        return False
    if not isinstance(epoch, Mapping):
        raise ContractError("Runtime compatibility epoch is not a mapping")
    bridge_sha256 = require_sha256(
        epoch.get("runtime_compatibility_bridge_sha256"),
        "runtime compatibility bridge",
    )
    expected = _runtime_compatibility_config_payload(bridge_sha256)
    if dict(config) != expected:
        raise ContractError("Runtime compatibility config changed")
    return True


def _runtime_compatibility_adapter_lock_payload(
    config: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    bridge_sha256: str,
    patch_config_sha256: str,
    aliases: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": RUNTIME_COMPATIBILITY_CONTRACT,
        "status": "SEALED_TWO_ALIAS_RUNTIME_ADAPTER_MODEL_FREE_SYNTHETIC_ONLY",
        "parent_execution_release_identity_sha256": (
            ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        ),
        "runtime_compatibility_bridge_sha256": bridge_sha256,
        "runtime_compatibility_config_sha256": patch_config_sha256,
        "base_gt_scout_execution_lock_sha256": parent["execution_locks"][
            "gt_scout_execution_lock_extension_v1.json"
        ],
        "added_aliases": dict(aliases),
        "added_alias_count": 2,
        "only_added_runtime_keys": sorted(aliases),
        "base_lock_bytes_mutated": False,
        "gate_threshold_seed_candidate_or_selection_change": False,
        "runtime_compatibility_implementation_sha256": (
            runtime_compatibility_implementation_sha256()
        ),
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "outcome_inputs_allowed": False,
        "registered_targets_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def _runtime_compatibility_release_payload(
    config: Mapping[str, Any],
    *,
    bridge_sha256: str,
    patch_config_sha256: str,
    adapter_lock_sha256: str,
    aliases: Mapping[str, str],
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "contract": RUNTIME_COMPATIBILITY_RELEASE_CONTRACT,
        "status": "SEALED_PARENT_RUNTIME_COMPATIBILITY_RELEASE_SYNTHETIC_ONLY",
        "authorization_event_id": RUNTIME_COMPATIBILITY_EVENT_ID,
        "goal_multi_repeat_run_id": ROSTER_EXTENSION_RUN_ID,
        "pass": 58,
        "parent_execution_release_identity_sha256": (
            ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        ),
        "parent_execution_release_file_sha256": (
            ROSTER_EXTENSION_RELEASE_FILE_SHA256
        ),
        "parent_extension_execution_config_sha256": (
            ROSTER_EXTENSION_CONFIG_SHA256
        ),
        "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
        "runtime_compatibility_bridge_sha256": bridge_sha256,
        "runtime_compatibility_config_sha256": patch_config_sha256,
        "runtime_compatibility_adapter_lock_sha256": adapter_lock_sha256,
        "runtime_compatibility_implementation_sha256": (
            runtime_compatibility_implementation_sha256()
        ),
        "pass58_execution_script_sha256": sha256_file(Path(__file__)),
        "pass58_execution_test_sha256": sha256_file(
            PROJECT_ROOT
            / "tests/test_run_spot_spray_simulation_video_ab_execution_v1.py"
        ),
        "pass55_source_snapshots": copy.deepcopy(list(snapshots)),
        "runtime_aliases": dict(aliases),
        "runtime_alias_count": 2,
        "parent_or_failed_intent_bytes_mutated": False,
        "candidate_gt_or_render_access_during_sealing": False,
        "model_or_outcome_access_during_sealing": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    payload["release_identity_sha256"] = stable_sha256(payload)
    return payload


def _runtime_compatibility_boundary_payload() -> dict[str, Any]:
    return {
        "render_state_sha256": HISTORICAL_V1_BINDINGS["render_state_sha256"],
        "candidate_rejection_ledger_sha256": HISTORICAL_V1_BINDINGS[
            "candidate_rejection_ledger_sha256"
        ],
        "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
        "failed_batch_intent_sha256": PASS56_FAILED_BATCH_INTENT_SHA256,
        "completed_pair_count": 40,
        "pending_pair_count": 56,
        "first_pending_pair_id": "locked_test_c001_r00",
        "ledger_row_count": 111,
        "c001_attempted_candidate_indices": list(range(10)),
        "candidate_10_started": False,
        "candidate_gt_inspected": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "outcome_inputs": [],
        "staging_directories": [],
    }


def _runtime_compatibility_sealing_boundary(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    paths = full_paths(config)
    planning = paths["synthetic"] / "planning"
    state_path = planning / "render_state_v1.json"
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    failure_path = _runtime_compatibility_failure_receipt_path(config)
    intent_path = _runtime_compatibility_failed_intent_path(config)
    expected = _runtime_compatibility_boundary_payload()
    observed = {
        "render_state_sha256": sha256_file(state_path),
        "candidate_rejection_ledger_sha256": sha256_file(ledger_path),
        "pass57_failure_receipt_sha256": sha256_file(failure_path),
        "failed_batch_intent_sha256": sha256_file(intent_path),
    }
    if any(observed[name] != expected[name] for name in observed):
        raise ContractError("Pass58 immutable execution boundary changed")
    state = load_json(state_path)
    ledger = read_jsonl(ledger_path)
    c001 = [row for row in ledger if row["pair_id"] == "locked_test_c001_r00"]
    candidate_root = planning / "gt_scout_v1/roster/locked_test_c001_r00"
    staging = sorted(
        display_path(path)
        for root in (paths["synthetic"] / "work", planning / "gt_scout_v1")
        if root.exists()
        for path in root.rglob(".partial-*")
    )
    if (
        state.get("completed_pair_count") != 40
        or state.get("pending_pair_count") != 56
        or state.get("pending_pair_ids", [None])[0] != "locked_test_c001_r00"
        or len(ledger) != 111
        or [int(row["candidate_index"]) for row in c001] != list(range(10))
        or (candidate_root / "candidate_10").exists()
        or staging
        or (paths["synthetic"] / "pairs/locked_test/locked_test_c001_r00").exists()
        or (
            paths["run"].exists()
            and any(path.is_file() for path in paths["run"].rglob("*"))
        )
    ):
        raise ContractError("Pass58 zero-access boundary changed")
    return expected


def _runtime_compatibility_artifact_rows(
    root: Path, *, receipt_name: str = "pass58_validation_receipt.json"
) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.name != receipt_name
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]


def _runtime_compatibility_pass58_payload(
    config: Mapping[str, Any],
    root: Path,
    parent: Mapping[str, Any],
    release: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_rows = _runtime_compatibility_artifact_rows(root)
    return {
        "schema_version": 1,
        "contract": RUNTIME_COMPATIBILITY_PASS58_CONTRACT,
        "status": "PASS_RUNTIME_COMPATIBILITY_RELEASE_VALIDATION_SYNTHETIC_ONLY",
        "goal_multi_repeat_run_id": ROSTER_EXTENSION_RUN_ID,
        "event_id": RUNTIME_COMPATIBILITY_EVENT_ID,
        "pass": 58,
        "parent_execution_release_identity_sha256": parent[
            "parent_execution_release_identity_sha256"
        ],
        "runtime_compatibility_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "immutable_parent": {
            "extension_execution_config_sha256": ROSTER_EXTENSION_CONFIG_SHA256,
            "execution_release_file_sha256": ROSTER_EXTENSION_RELEASE_FILE_SHA256,
            "pass55_validation_receipt_sha256": PASS55_VALIDATION_RECEIPT_SHA256,
            "pass55_execution_script_sha256": PASS55_EXECUTION_SCRIPT_SHA256,
            "pass55_execution_test_sha256": PASS55_EXECUTION_TEST_SHA256,
            "pass55_artifact_inventory_sha256": PASS55_ARTIFACT_INVENTORY_SHA256,
            "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
            "failed_batch_intent_sha256": PASS56_FAILED_BATCH_INTENT_SHA256,
            "bytes_mutated_or_rebound": False,
        },
        "runtime_patch": {
            "only_added_runtime_keys": sorted(RUNTIME_COMPATIBILITY_ALIASES),
            "added_aliases": copy.deepcopy(RUNTIME_COMPATIBILITY_ALIASES),
            "added_alias_count": 2,
            "base_lock_bytes_mutated": False,
            "gate_threshold_seed_candidate_or_selection_change": False,
        },
        "artifact_inventory": {
            "files": artifact_rows,
            "file_count": len(artifact_rows),
            "inventory_sha256": stable_sha256(artifact_rows),
        },
        "access_guard": copy.deepcopy(dict(boundary)),
        "next_authorized_action": (
            "resume_locked_test_c001_r00_at_candidate_10_under_"
            "runtime_compatibility_release"
        ),
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }


def runtime_compatibility_implementation_sha256() -> str:
    functions = (
        _validate_frozen_pass55_release,
        _runtime_compatibility_alias_payload,
        _runtime_compatibility_bridge_payload,
        _runtime_compatibility_config_payload,
        _is_runtime_compatibility_config,
        _runtime_compatibility_adapter_lock_payload,
        _runtime_compatibility_release_payload,
        _runtime_compatibility_boundary_payload,
        _runtime_compatibility_sealing_boundary,
        _runtime_compatibility_pass58_payload,
        seal_runtime_compatibility_release,
        validate_runtime_compatibility_release,
        _validated_roster_extension_context,
        _extension_execution_lock,
    )
    return stable_sha256(
        {
            "contract": RUNTIME_COMPATIBILITY_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "parent_release_identity_sha256": (
                ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
            ),
            "pass57_failure_receipt_sha256": PASS57_FAILURE_RECEIPT_SHA256,
            "runtime_aliases": RUNTIME_COMPATIBILITY_ALIASES,
        }
    )


def _write_yaml_once_atomically(path: Path, value: Mapping[str, Any]) -> None:
    payload = yaml.safe_dump(dict(value), sort_keys=False)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ContractError(f"Refusing to overwrite changed YAML: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".partial-{path.name}-{uuid.uuid4().hex}"
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def seal_runtime_compatibility_release(config_path: Path) -> dict[str, Any]:
    """Seal the two-alias adapter without inspecting or rendering candidate GT."""
    config_path = config_path.expanduser().resolve()
    if config_path != DEFAULT_CONFIG.resolve():
        raise ContractError("Runtime compatibility sealing requires immutable V1 config")
    config = load_config(config_path)
    parent = _validate_frozen_pass55_release(config)
    boundary = _runtime_compatibility_sealing_boundary(config)
    paths = runtime_compatibility_paths(config)
    snapshots = _runtime_compatibility_source_snapshots(
        config, require_docs_mirror=True
    )
    if paths["release_root"].exists() or paths["docs_release_root"].exists():
        if not (
            paths["release_root"].is_dir()
            and paths["docs_release_root"].is_dir()
        ):
            raise ContractError("Partial runtime compatibility publication exists")
        return validate_runtime_compatibility_release(paths["config"])

    aliases = _runtime_compatibility_alias_payload(config, parent)
    bridge = _runtime_compatibility_bridge_payload(
        config, parent, snapshots, aliases
    )
    staging = paths["synthetic"] / (
        f".partial-runtime-compatibility-release-v1-{uuid.uuid4().hex}"
    )
    docs_staging = paths["docs"] / (
        f".partial-runtime-compatibility-release-v1-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_json(staging / "runtime_compatibility_bridge_v1.json", bridge)
        bridge_sha256 = sha256_file(
            staging / "runtime_compatibility_bridge_v1.json"
        )
        patch_config = _runtime_compatibility_config_payload(bridge_sha256)
        patch_config_path = (
            staging
            / "execution_config_v1_plus_roster_extension_v1_"
            "runtime_compatibility_v1.yaml"
        )
        _write_yaml_once_atomically(patch_config_path, patch_config)
        patch_config_sha256 = sha256_file(patch_config_path)
        adapter = _runtime_compatibility_adapter_lock_payload(
            config,
            parent,
            bridge_sha256=bridge_sha256,
            patch_config_sha256=patch_config_sha256,
            aliases=aliases,
        )
        adapter_path = staging / "runtime_compatibility_adapter_lock_v1.json"
        write_json(adapter_path, adapter)
        release = _runtime_compatibility_release_payload(
            config,
            bridge_sha256=bridge_sha256,
            patch_config_sha256=patch_config_sha256,
            adapter_lock_sha256=sha256_file(adapter_path),
            aliases=aliases,
            snapshots=snapshots,
        )
        write_json(
            staging
            / "execution_release_v1_plus_roster_extension_v1_"
            "runtime_compatibility_v1.json",
            release,
        )

        inventory_root = paths["synthetic"]
        temporary_release = inventory_root / "release_v1"
        staging.replace(temporary_release)
        try:
            receipt = _runtime_compatibility_pass58_payload(
                config, inventory_root, parent, release, boundary
            )
            write_json(temporary_release / "pass58_validation_receipt.json", receipt)
        except Exception:
            temporary_release.replace(staging)
            raise
        docs_staging.mkdir(parents=True, exist_ok=False)
        for source in sorted(temporary_release.iterdir()):
            if source.is_file():
                shutil.copy2(source, docs_staging / source.name)
        docs_staging.replace(paths["docs_release_root"])
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
        raise
    return validate_runtime_compatibility_release(paths["config"])


def validate_runtime_compatibility_release(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    historical_config = load_config(DEFAULT_CONFIG)
    paths = runtime_compatibility_paths(historical_config)
    if config_path != paths["config"].resolve():
        raise ContractError("Noncanonical runtime compatibility config path")
    partials = list(paths["synthetic"].glob(".partial-*")) + list(
        paths["docs"].glob(".partial-*")
    )
    if partials:
        raise ContractError("Partial runtime compatibility publication exists")
    expected_files = _runtime_compatibility_required_relative_files()
    observed_files = sorted(
        path.relative_to(paths["synthetic"]).as_posix()
        for path in paths["synthetic"].rglob("*")
        if path.is_file()
    )
    docs_files = sorted(
        path.relative_to(paths["docs"]).as_posix()
        for path in paths["docs"].rglob("*")
        if path.is_file()
    )
    if observed_files != expected_files or docs_files != expected_files:
        raise ContractError("Runtime compatibility release file set changed")
    if any(
        sha256_file(paths["synthetic"] / relative)
        != sha256_file(paths["docs"] / relative)
        for relative in expected_files
    ):
        raise ContractError("Runtime compatibility docs mirror changed")

    parent = _validate_frozen_pass55_release(historical_config)
    snapshots = _runtime_compatibility_source_snapshots(
        historical_config, require_docs_mirror=True
    )
    aliases = _runtime_compatibility_alias_payload(historical_config, parent)
    bridge = load_json(paths["bridge"])
    expected_bridge = _runtime_compatibility_bridge_payload(
        historical_config, parent, snapshots, aliases
    )
    if bridge != expected_bridge:
        raise ContractError("Runtime compatibility bridge changed")
    bridge_sha256 = sha256_file(paths["bridge"])
    patch_config = load_config(config_path)
    expected_config = _runtime_compatibility_config_payload(bridge_sha256)
    if patch_config != expected_config or not _is_runtime_compatibility_config(
        patch_config
    ):
        raise ContractError("Runtime compatibility config changed")
    patch_config_sha256 = sha256_file(config_path)
    adapter = load_json(paths["adapter_lock"])
    expected_adapter = _runtime_compatibility_adapter_lock_payload(
        historical_config,
        parent,
        bridge_sha256=bridge_sha256,
        patch_config_sha256=patch_config_sha256,
        aliases=aliases,
    )
    if adapter != expected_adapter:
        raise ContractError("Runtime compatibility adapter lock changed")
    release = load_json(paths["release"])
    expected_release = _runtime_compatibility_release_payload(
        historical_config,
        bridge_sha256=bridge_sha256,
        patch_config_sha256=patch_config_sha256,
        adapter_lock_sha256=sha256_file(paths["adapter_lock"]),
        aliases=aliases,
        snapshots=snapshots,
    )
    if release != expected_release:
        raise ContractError("Runtime compatibility parent release changed")
    identity = release.get("release_identity_sha256")
    identity_payload = copy.deepcopy(release)
    identity_payload.pop("release_identity_sha256", None)
    if identity != stable_sha256(identity_payload):
        raise ContractError("Runtime compatibility release identity changed")
    receipt = load_json(paths["pass58_receipt"])
    expected_receipt = _runtime_compatibility_pass58_payload(
        historical_config,
        paths["synthetic"],
        parent,
        release,
        _runtime_compatibility_boundary_payload(),
    )
    if receipt != expected_receipt:
        raise ContractError("Pass58 runtime compatibility receipt changed")
    access = receipt.get("access_guard", {})
    if (
        access.get("candidate_10_started") is not False
        or access.get("candidate_gt_inspected") is not False
        or access.get("rendering_calls") != 0
        or access.get("model_loaded") is not False
        or access.get("inference_calls") != 0
        or access.get("prediction_accessed") is not False
        or access.get("locked_test_outcome_accessed") is not False
        or access.get("registered_targets_used") is not False
        or access.get("outcome_inputs") != []
    ):
        raise ContractError("Pass58 zero-access receipt changed")
    return {
        "status": receipt["status"],
        "parent_execution_release_identity_sha256": (
            ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
        ),
        "runtime_compatibility_release_identity_sha256": identity,
        "runtime_compatibility_bridge_sha256": bridge_sha256,
        "runtime_compatibility_adapter_lock_sha256": sha256_file(
            paths["adapter_lock"]
        ),
        "runtime_compatibility_config_path": display_path(config_path),
        "runtime_compatibility_config_sha256": patch_config_sha256,
        "execution_locks": copy.deepcopy(parent["execution_locks"]),
        "validation": copy.deepcopy(parent["validation"]),
        "runtime_compatibility_aliases": aliases,
        "candidate_10_started": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "outcome_inputs": [],
        "synthetic_only": True,
    }


def _validated_roster_extension_context(
    config: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not _is_roster_extension_config(config):
        return None
    if _is_runtime_compatibility_config(config):
        paths = runtime_compatibility_paths(config)
        canonical = load_config(paths["config"])
        if canonical != dict(config):
            raise ContractError("Noncanonical runtime compatibility config content")
        return validate_runtime_compatibility_release(paths["config"])
    paths = roster_extension_paths(config)
    canonical = load_config(paths["extension_config"])
    if canonical != dict(config):
        raise ContractError("Noncanonical roster extension config content")
    return _validate_frozen_pass55_release(config)


def _extension_execution_lock(
    config: Mapping[str, Any], name: str
) -> dict[str, Any]:
    context = _validated_roster_extension_context(config)
    if context is None:
        raise ContractError("Roster extension execution lock requires extension config")
    path = roster_extension_paths(config)["execution_locks"] / name
    expected = context["execution_locks"].get(name)
    if expected is None or not path.is_file() or sha256_file(path) != expected:
        raise ContractError(f"Roster extension execution lock drift: {name}")
    lock = load_json(path)
    result = {"path": display_path(path), "sha256": expected, **lock}
    if (
        _is_runtime_compatibility_config(config)
        and name == "gt_scout_execution_lock_extension_v1.json"
    ):
        aliases = context.get("runtime_compatibility_aliases")
        if (
            aliases != RUNTIME_COMPATIBILITY_ALIASES
            or any(alias in lock for alias in RUNTIME_COMPATIBILITY_ALIASES)
        ):
            raise ContractError("Runtime compatibility alias overlay changed")
        result.update(aliases)
    return result


def build_full_capacity_receipt(
    config: Mapping[str, Any], full_preflight: Mapping[str, Any]
) -> dict[str, Any]:
    fixture = fixture_paths(config)
    render_receipt_path = fixture["synthetic"] / "render_receipt.json"
    validation_path = fixture["docs"] / "fixture_validation_receipt.json"
    if not render_receipt_path.is_file() or not validation_path.is_file():
        raise ContractError("Passing native fixture measurement is required for full plan")
    render_receipt = load_json(render_receipt_path)
    validation = load_json(validation_path)
    if (
        render_receipt.get("status") != "PASS_NATIVE_FIXTURE_RENDER_SYNTHETIC_ONLY"
        or validation.get("status")
        != "PASS_NATIVE_FIXTURE_VALIDATION_SYNTHETIC_ONLY"
    ):
        raise ContractError("Native fixture measurement is not passing")
    fixture_pairs = int(config["storage_estimate"]["fixture_pairs"])
    full_pairs = int(config["storage_estimate"]["full_total_pairs"])
    scale = full_pairs / fixture_pairs
    fixture_synthetic_bytes = _tree_bytes(fixture["synthetic"])
    fixture_run_bytes = _tree_bytes(fixture["run"])
    measured_render_seconds = float(render_receipt["elapsed_wall_seconds"])
    measured_projection_bytes = math.ceil(fixture_synthetic_bytes * scale)
    measured_projection_hours = measured_render_seconds * scale / 3600.0
    admission_bytes = int(config["runtime"]["minimum_full_free_bytes"])
    reserve = int(config["runtime"]["reserve_free_bytes_after_full"])
    required_bytes = max(admission_bytes, measured_projection_bytes)
    capacity = full_preflight["capacity"]
    free_bytes = int(capacity["free_bytes"])
    if free_bytes - required_bytes < reserve:
        raise ContractError(
            "Measured full capacity gate failed: "
            f"free={free_bytes}, required={required_bytes}, reserve={reserve}"
        )
    isolated_upper_hours = float(
        full_preflight["runtime_estimate"]["full_isolated_render_hours_estimate"]
    )
    selected_candidate_upper = max(measured_projection_hours, isolated_upper_hours)
    candidate_ceiling = int(config["full_benchmark"]["maximum_candidates_per_slot"])
    return {
        "schema_version": 1,
        "method": "measured_native_fixture_projection_bounded_by_predeclared_admission_gate",
        "fixture_measurement": {
            "pair_count": fixture_pairs,
            "synthetic_bytes": fixture_synthetic_bytes,
            "inference_run_bytes_not_in_render_projection": fixture_run_bytes,
            "render_package_wall_seconds": measured_render_seconds,
            "render_receipt_sha256": sha256_file(render_receipt_path),
            "validation_receipt_sha256": sha256_file(validation_path),
        },
        "projection": {
            "full_pair_count": full_pairs,
            "pair_count_multiplier": scale,
            "measured_linear_bytes": measured_projection_bytes,
            "measured_linear_render_hours": measured_projection_hours,
            "predeclared_admission_bytes": admission_bytes,
            "required_bytes": required_bytes,
            "reserve_bytes": reserve,
            "free_bytes_observed": free_bytes,
            "headroom_after_required_and_reserve_bytes": (
                free_bytes - required_bytes - reserve
            ),
            "isolated_render_upper_hours_one_candidate_per_slot": isolated_upper_hours,
            "planning_upper_hours_one_candidate_per_slot": selected_candidate_upper,
            "absolute_ten_candidate_attempt_ceiling_hours": (
                selected_candidate_upper * candidate_ceiling
            ),
            "candidate_attempt_ceiling_is_not_expected_runtime": True,
        },
        "storage_policy": {
            "rejected_candidate_bulk_payload_retained": False,
            "rejected_candidate_receipt_and_log_retained": True,
            "only_one_pair_candidate_staging_directory_at_a_time": True,
            "full_render_must_repeat_capacity_check_before_each_pair": True,
        },
        "passed": True,
    }


def build_candidate_gate_contract(protocol: Mapping[str, Any]) -> dict[str, Any]:
    gates = protocol["preoutcome_gates"]
    contract = {
        "schema_version": 1,
        "selection": copy.deepcopy(gates["candidate_selection"]),
        "source_integrity": copy.deepcopy(gates["source_integrity"]),
        "pair_integrity": copy.deepcopy(gates["pair_integrity"]),
        "pixel_visual": copy.deepcopy(gates["pixel_visual"]),
        "split_integrity": copy.deepcopy(gates["split_integrity"]),
        "temporal_denominator": copy.deepcopy(gates["temporal_denominator"]),
        "manual_review": copy.deepcopy(gates["manual_review"]),
        "mandatory_lock_order": copy.deepcopy(gates["mandatory_lock_order"]),
        "pair_candidate_machine_gate_order": [
            "source_and_asset_provenance",
            "geometry_and_botanical_gt_integrity",
            "native_frame_and_pair_integrity",
            "pixel_and_visual_operability",
            "temporal_denominator_contribution",
            "deterministic_replay_identity",
        ],
        "split_release_gates_deferred_until_all_selected_pairs_exist": [
            "minimum_crop_model_variants_per_split",
            "minimum_ground_families_per_split",
            "minimum_environment_families_per_split",
            "exact_profile_balance_required",
            "minimum_calibration_eligible_weed_tracks",
            "minimum_locked_test_eligible_weed_tracks",
        ],
        "model_or_outcome_inputs_allowed": False,
        "prediction_file_access_allowed": False,
        "registered_target_access_allowed": False,
        "candidate_rejection_requires_machine_reason_receipt": True,
        "selected_candidate_is_first_passing_index": True,
    }
    contract["contract_sha256"] = stable_sha256(contract)
    return contract


def build_atomic_render_state_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    full = config["full_benchmark"]
    contract = {
        "schema_version": 1,
        "pair_unit": "one_latent_pair_with_two_capture_arms_and_one_shared_gt",
        "staging_pattern": "work/.partial-{pair_id}-candidate-{candidate_index:02d}-{nonce}",
        "final_pattern": "pairs/{protocol_split}/{pair_id}",
        "publish_operation": "same_filesystem_atomic_directory_rename",
        "overwrite_allowed": bool(full["selected_pair_overwrite_allowed"]),
        "resume_rules": {
            "passing_final_receipt": "verify_and_skip",
            "missing_final_receipt": "fail_closed_never_treat_complete",
            "interrupted_pair_staging": str(full["interrupted_staging_policy"]),
            "rejected_candidate": "retain_receipt_and_log_then_remove_bulk_payload",
            "next_candidate": "lowest_not_previously_rejected_index",
            "candidate_exhaustion": "invalidate_slot_and_stop_before_model_access",
        },
        "required_pair_receipt_fields": [
            "pair_id",
            "protocol_split",
            "pair_slot_identity_sha256",
            "selected_candidate_index",
            "candidate_identity_sha256",
            "pair_quality_gates",
            "inventory_sha256",
            "model_outputs_present_false",
        ],
        "model_access_allowed": False,
        "atomic_state_machine_implemented": True,
        "dry_run_does_not_invoke_blender": True,
    }
    contract["contract_sha256"] = stable_sha256(contract)
    return contract


def _require_child(path: Path, parent: Path, label: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as error:
        raise ContractError(f"{label} escaped bounded full root: {path}") from error


def _validate_publishable_full_pair_receipt(
    receipt: Mapping[str, Any], roster_row: Mapping[str, Any]
) -> None:
    pair_id = str(roster_row["pair_id"])
    gates = receipt.get("pair_quality_gates")
    candidate_index = receipt.get("selected_candidate_index")
    valid = (
        receipt.get("contract") == FULL_PAIR_RECEIPT_CONTRACT
        and receipt.get("status") == "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY"
        and receipt.get("pair_id") == pair_id
        and receipt.get("protocol_split") == roster_row["protocol_split"]
        and receipt.get("pair_slot_identity_sha256")
        == roster_row["pair_slot_identity_sha256"]
        and isinstance(candidate_index, int)
        and not isinstance(candidate_index, bool)
        and candidate_index >= 0
        and isinstance(gates, Mapping)
        and bool(gates)
        and all(value is True for value in gates.values())
        and receipt.get("model_outputs_present_false") is True
    )
    if not valid:
        raise ContractError("Full pair terminal receipt is not publishable")
    try:
        require_sha256(
            str(receipt.get("candidate_identity_sha256", "")),
            "full pair candidate identity",
        )
        require_sha256(
            str(receipt.get("inventory_sha256", "")),
            "full pair inventory",
        )
    except ContractError as error:
        raise ContractError("Full pair terminal receipt is not publishable") from error
    candidates = roster_row.get("candidates")
    if candidates is not None:
        if candidate_index >= len(candidates) or receipt["candidate_identity_sha256"] != (
            candidates[candidate_index]["candidate_identity_sha256"]
        ):
            raise ContractError("Full pair terminal receipt candidate binding changed")


def atomic_publish_full_pair(
    full_root: Path,
    staging: Path,
    destination: Path,
    roster_row: Mapping[str, Any],
) -> dict[str, Any]:
    pair_id = str(roster_row["pair_id"])
    if SAFE_ID_RE.fullmatch(pair_id) is None:
        raise ContractError(f"Unsafe full pair ID: {pair_id}")
    _require_child(staging, full_root / "work", "pair staging")
    _require_child(destination, full_root / "pairs", "pair destination")
    expected_prefix = f".partial-{pair_id}-candidate-"
    if not staging.name.startswith(expected_prefix) or not staging.is_dir():
        raise ContractError("Atomic pair staging name or directory is invalid")
    if destination.exists():
        raise ContractError(f"Refusing to overwrite selected full pair: {destination}")
    receipt_path = staging / "full_pair_receipt.json"
    if not receipt_path.is_file():
        raise ContractError("Full pair staging has no terminal receipt")
    receipt = load_json(receipt_path)
    _validate_publishable_full_pair_receipt(receipt, roster_row)
    forbidden = [
        path
        for path in staging.rglob("*")
        if path.is_file() and "prediction" in path.name.lower()
    ]
    if forbidden:
        raise ContractError("Prediction output exists in preoutcome pair staging")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(destination)
    return {
        "pair_id": pair_id,
        "destination": str(destination),
        "receipt_sha256": sha256_file(destination / "full_pair_receipt.json"),
        "published_atomically": True,
    }


def cleanup_interrupted_full_pair_staging(
    full_root: Path, pair_id: str
) -> dict[str, Any]:
    if SAFE_ID_RE.fullmatch(pair_id) is None:
        raise ContractError(f"Unsafe full pair ID: {pair_id}")
    work = full_root / "work"
    if not work.exists():
        return {"pair_id": pair_id, "removed": [], "bounded_cleanup": True}
    if not work.is_dir() or work.is_symlink():
        raise ContractError("Full work path is not a plain directory")
    removed: list[str] = []
    prefix = f".partial-{pair_id}-candidate-"
    for path in sorted(work.iterdir()):
        if not path.name.startswith(prefix):
            continue
        _require_child(path, work, "interrupted pair staging")
        if path.is_symlink() or not path.is_dir():
            raise ContractError(f"Interrupted pair staging is not a plain directory: {path}")
        shutil.rmtree(path)
        removed.append(path.name)
    return {"pair_id": pair_id, "removed": removed, "bounded_cleanup": True}


def inspect_full_render_state(
    full_root: Path, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    completed: list[str] = []
    pending: list[str] = []
    invalid: list[str] = []
    for row in rows:
        pair_id = str(row["pair_id"])
        destination = (
            full_root / "pairs" / str(row["protocol_split"]) / pair_id
        )
        if not destination.exists():
            pending.append(pair_id)
            continue
        receipt_path = destination / "full_pair_receipt.json"
        try:
            receipt = load_json(receipt_path)
            _validate_publishable_full_pair_receipt(receipt, row)
        except (OSError, ValueError, ContractError):
            invalid.append(pair_id)
            continue
        completed.append(pair_id)
    work = full_root / "work"
    interrupted = sorted(
        path.name
        for path in work.glob(".partial-*")
        if path.is_dir()
    ) if work.is_dir() else []
    if invalid:
        raise ContractError(f"Invalid published full pair receipts: {invalid}")
    return {
        "planned_pair_count": len(rows),
        "completed_pair_count": len(completed),
        "pending_pair_count": len(pending),
        "completed_pair_ids": completed,
        "pending_pair_ids": pending,
        "interrupted_staging_directories": interrupted,
        "model_outputs_present": any(
            path.is_file() and "prediction" in path.name.lower()
            for path in full_root.rglob("*")
        ),
    }


def initialize_full_plan(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    paths = full_paths(config)
    if paths["run"].exists() and any(
        path.is_file() for path in paths["run"].rglob("*")
    ):
        raise ContractError("Full run output exists before model-free planning")
    if paths["synthetic"].exists():
        return validate_full_plan(config_path)
    if paths["docs"].exists():
        raise ContractError("Full docs exist without a full synthetic plan root")

    full_preflight = preflight(config_path, scope="full")
    protocol = _protocol(config)
    templates = _scene_template_inventory(config)
    asset_partition = build_role_asset_partition(config, templates)
    roster = build_full_roster(config, protocol, templates)
    roster_validation = validate_full_roster(roster, protocol)
    capacity = build_full_capacity_receipt(config, full_preflight)
    candidate_gates = build_candidate_gate_contract(protocol)
    atomic_contract = build_atomic_render_state_contract(config)

    full_root = paths["synthetic"]
    full_root.parent.mkdir(parents=True, exist_ok=True)
    staging = full_root.parent / f".{full_root.name}.plan-partial-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        planning = staging / "planning"
        roster_path = planning / "pair_roster_v1.jsonl"
        write_jsonl(roster_path, roster)
        write_json(planning / "source_lock_receipt_v1.json", full_preflight["sources"])
        write_json(planning / "template_inventory_v1.json", templates)
        write_json(planning / "asset_partition_v1.json", asset_partition)
        write_json(planning / "candidate_gate_contract_v1.json", candidate_gates)
        write_json(planning / "atomic_render_state_contract_v1.json", atomic_contract)
        write_json(planning / "full_capacity_receipt_v1.json", capacity)
        write_jsonl(planning / "candidate_rejection_ledger_v1.jsonl", [])
        state = inspect_full_render_state(staging, roster)
        if state["completed_pair_count"] != 0 or state["model_outputs_present"]:
            raise ContractError("Fresh full dry-run plan contains pair or model output")
        write_json(planning / "render_state_v1.json", state)
        inventory = artifact_inventory(staging)
        plan_receipt = {
            "schema_version": 1,
            "contract": FULL_PLAN_CONTRACT,
            "status": "PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY",
            "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
            "execution_config_sha256": sha256_file(config_path),
            "execution_script_sha256": sha256_file(Path(__file__).resolve()),
            "pair_roster_sha256": sha256_file(roster_path),
            "pair_roster_validation": roster_validation,
            "template_inventory_sha256": sha256_file(
                planning / "template_inventory_v1.json"
            ),
            "asset_partition_sha256": sha256_file(
                planning / "asset_partition_v1.json"
            ),
            "candidate_gate_contract_sha256": sha256_file(
                planning / "candidate_gate_contract_v1.json"
            ),
            "atomic_render_state_contract_sha256": sha256_file(
                planning / "atomic_render_state_contract_v1.json"
            ),
            "full_capacity_receipt_sha256": sha256_file(
                planning / "full_capacity_receipt_v1.json"
            ),
            "inventory_sha256": stable_sha256(inventory),
            "inventory_file_count_before_plan_receipt": len(inventory),
            "render_state": state,
            "model_access": {
                "checkpoint_hash_verified_as_source_lock": True,
                "checkpoint_loaded": False,
                "inference_calls": 0,
                "prediction_files_present": False,
            },
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        write_json(planning / "full_plan_receipt_v1.json", plan_receipt)
        staging.replace(full_root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    docs = paths["docs"]
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs_staging = docs.parent / f".{docs.name}.plan-partial-{uuid.uuid4().hex}"
    docs_staging.mkdir(parents=False, exist_ok=False)
    try:
        for name in (
            "full_plan_receipt_v1.json",
            "full_capacity_receipt_v1.json",
            "candidate_gate_contract_v1.json",
            "atomic_render_state_contract_v1.json",
            "asset_partition_v1.json",
            "render_state_v1.json",
        ):
            shutil.copy2(full_root / "planning" / name, docs_staging / name)
        receipt = load_json(full_root / "planning/full_plan_receipt_v1.json")
        capacity_receipt = load_json(
            full_root / "planning/full_capacity_receipt_v1.json"
        )
        readme = [
            "# Full 32/64 benchmark dry-run plan",
            "",
            "Status: `PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY`.",
            "",
            "No Blender render, checkpoint load, inference, threshold selection, or test metric access occurred.",
            "",
            f"- Pair roster: {receipt['pair_roster_validation']['split_pair_counts']}",
            f"- Unique candidate seeds: {receipt['pair_roster_validation']['unique_seed_count']}",
            f"- Required full bytes: {capacity_receipt['projection']['required_bytes']}",
            f"- Free bytes observed: {capacity_receipt['projection']['free_bytes_observed']}",
            f"- One-candidate planning upper: {capacity_receipt['projection']['planning_upper_hours_one_candidate_per_slot']:.2f} h",
            "- Pair publication is same-filesystem atomic and selected outputs are never overwritten.",
            "- Candidate selection is first passing non-model candidate; outcome and target inputs are forbidden.",
            "",
            "This plan is synthetic-only and grants no field, product, or chemical authorization.",
        ]
        (docs_staging / "README.md").write_text(
            "\n".join(readme) + "\n", encoding="utf-8"
        )
        docs_staging.replace(docs)
    except Exception:
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
        raise
    return validate_full_plan(config_path)


def validate_full_plan(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    extension_context = _validated_roster_extension_context(config)
    protocol = _protocol(config)
    paths = full_paths(config)
    root = paths["synthetic"]
    planning = root / "planning"
    receipt_path = planning / "full_plan_receipt_v1.json"
    if not receipt_path.is_file():
        raise ContractError("Full dry-run plan receipt is missing")
    receipt = load_json(receipt_path)
    if (
        receipt.get("contract") != FULL_PLAN_CONTRACT
        or receipt.get("status") != "PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY"
        or receipt.get("protocol_sha256")
        != config["source_locks"]["protocol"]["sha256"]
        or (
            receipt.get("execution_config_sha256")
            != (
                HISTORICAL_V1_BINDINGS["execution_config_sha256"]
                if extension_context is not None
                else sha256_file(config_path)
            )
        )
    ):
        raise ContractError("Full dry-run plan binding changed")
    require_sha256(
        receipt.get("execution_script_sha256"),
        "historical full plan generator script",
    )
    roster_path = planning / "pair_roster_v1.jsonl"
    if sha256_file(roster_path) != receipt["pair_roster_sha256"]:
        raise ContractError("Full pair roster hash changed")
    roster = read_jsonl(roster_path)
    validation = validate_full_roster(roster, protocol)
    if validation != receipt["pair_roster_validation"]:
        raise ContractError("Full pair roster validation changed")
    for key, name in (
        ("template_inventory_sha256", "template_inventory_v1.json"),
        ("asset_partition_sha256", "asset_partition_v1.json"),
        ("candidate_gate_contract_sha256", "candidate_gate_contract_v1.json"),
        ("atomic_render_state_contract_sha256", "atomic_render_state_contract_v1.json"),
        ("full_capacity_receipt_sha256", "full_capacity_receipt_v1.json"),
    ):
        if sha256_file(planning / name) != receipt[key]:
            raise ContractError(f"Full planning artifact hash changed: {name}")
    asset_partition = load_json(planning / "asset_partition_v1.json")
    if any(asset_partition["validation"][name] != 0 for name in (
        "filename_overlap_count", "object_sha256_overlap_count"
    )):
        raise ContractError("Full asset partition is not split-pure")
    state = inspect_full_render_state(root, roster)
    if state["model_outputs_present"]:
        raise ContractError("Model output exists in preoutcome full root")
    if paths["run"].exists() and any(path.is_file() for path in paths["run"].rglob("*")):
        raise ContractError("Full model run exists during model-free plan validation")
    capacity = load_json(planning / "full_capacity_receipt_v1.json")
    if capacity.get("passed") is not True:
        raise ContractError("Full capacity receipt is not passing")
    result = {
        "status": receipt["status"],
        "full_root": str(root),
        "docs_root": str(paths["docs"]),
        "pair_roster_sha256": receipt["pair_roster_sha256"],
        "split_pair_counts": validation["split_pair_counts"],
        "candidate_count": validation["candidate_count"],
        "unique_seed_count": validation["unique_seed_count"],
        "asset_partition_sha256": receipt["asset_partition_sha256"],
        "capacity": capacity["projection"],
        "render_state": state,
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }
    if extension_context is not None:
        result["roster_extension"] = extension_context
        result["combined_candidate_count"] = extension_context["validation"][
            "combined_candidate_count"
        ]
        result["extension_candidate_count"] = extension_context["validation"][
            "extension_candidate_count"
        ]
        result["parent_execution_release_identity_sha256"] = extension_context[
            "parent_execution_release_identity_sha256"
        ]
    return result


@dataclass
class ExecutionAccessGuard:
    """Fail-closed calibration/threshold/locked-test state machine."""

    phase: str = "pre_release_lock"
    release_lock_sha256: str | None = None
    selected_threshold: float | None = None
    test_inference_sequences: set[str] = field(default_factory=set)
    locked_test_metric_evaluations: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def seal_release(self, release_lock_sha256: str, *, model_outputs_present: bool) -> None:
        if self.phase != "pre_release_lock" or model_outputs_present:
            raise ContractError("Release lock requires no model outputs and a fresh state")
        self.release_lock_sha256 = require_sha256(
            release_lock_sha256, "release_lock_sha256"
        )
        self.phase = "degraded_calibration"
        self.events.append(
            {
                "operation": "seal_release_lock",
                "model_outputs_present": False,
                "locked_test_access_state": "sealed",
            }
        )

    def record_calibration_inference(self, condition: str, sequence_id: str) -> None:
        if self.phase == "degraded_calibration" and condition != "degraded":
            raise ContractError("Only degraded calibration may run before threshold lock")
        if self.phase not in {"degraded_calibration", "threshold_locked"}:
            raise ContractError("Calibration inference is not allowed in the current phase")
        if condition == "ideal" and self.phase != "threshold_locked":
            raise ContractError("Ideal calibration is post-lock diagnostic only")
        self.events.append(
            {
                "operation": "calibration_inference",
                "condition": condition,
                "sequence_id": sequence_id,
                "threshold_locked_before_access": self.phase == "threshold_locked",
            }
        )

    def seal_threshold(
        self,
        threshold: float,
        *,
        source_condition: str,
        test_predictions_present: bool,
    ) -> None:
        if self.phase != "degraded_calibration":
            raise ContractError("Threshold can only be sealed after degraded calibration")
        if source_condition != "degraded" or test_predictions_present:
            raise ContractError("Threshold source must be degraded calibration with no test outputs")
        self.selected_threshold = float(threshold)
        self.phase = "threshold_locked"
        self.events.append(
            {
                "operation": "seal_threshold_lock",
                "source_condition": source_condition,
                "test_predictions_present": False,
                "selected_threshold": self.selected_threshold,
            }
        )

    def record_test_inference(self, condition: str, sequence_id: str) -> None:
        if self.phase not in {"threshold_locked", "locked_test_inference"}:
            raise ContractError("Locked-test inference attempted before threshold lock")
        if sequence_id in self.test_inference_sequences:
            raise ContractError(f"Locked-test sequence inferred more than once: {sequence_id}")
        self.phase = "locked_test_inference"
        self.test_inference_sequences.add(sequence_id)
        self.events.append(
            {
                "operation": "locked_test_inference",
                "condition": condition,
                "sequence_id": sequence_id,
                "threshold_locked_before_access": True,
            }
        )

    def begin_locked_test_evaluation(self) -> None:
        if self.locked_test_metric_evaluations != 0:
            raise ContractError("Locked-test metrics may be evaluated exactly once")
        if self.phase != "locked_test_inference" or not self.test_inference_sequences:
            raise ContractError("Locked-test metrics require completed locked-test inference")
        self.locked_test_metric_evaluations = 1
        self.phase = "locked_test_evaluation"
        self.events.append(
            {"operation": "locked_test_metric_evaluation", "evaluation_index": 1}
        )

    def finish(self) -> None:
        if self.phase != "locked_test_evaluation" or self.locked_test_metric_evaluations != 1:
            raise ContractError("Execution cannot finish without exactly one test evaluation")
        self.phase = "complete"
        self.events.append({"operation": "finish", "fail_closed": True})

    def receipt(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "release_lock_sha256": self.release_lock_sha256,
            "selected_threshold": self.selected_threshold,
            "test_inference_sequence_count": len(self.test_inference_sequences),
            "locked_test_metric_evaluations": self.locked_test_metric_evaluations,
            "test_accessed_before_threshold_lock": any(
                event["operation"] == "locked_test_inference"
                and not event["threshold_locked_before_access"]
                for event in self.events
            ),
            "events": self.events,
        }


def derive_native_scene_config(
    base: Mapping[str, Any],
    scene: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    native = config["native_contract"]
    fixture = config["fixture"]
    render = result["render"]
    render["frames"] = int(native["frames_per_arm"])
    render["resolution_x"] = int(native["width_px"])
    render["resolution_y"] = int(native["height_px"])
    render["samples"] = int(fixture["render_samples"])
    camera = render["camera"]
    ground_fov_m = float(native["ground_fov_mm"]) / 1000.0
    camera["fov_deg"] = round(
        math.degrees(2.0 * math.atan(ground_fov_m / (2.0 * float(camera["height"])))),
        6,
    )

    profile = result.get("agri_asset_profile", {}).get("correlated_scene_profile")
    if profile != scene["scene_profile"]:
        raise ContractError(
            f"Fixture source profile mismatch for {scene['pair_id']}: "
            f"{profile} != {scene['scene_profile']}"
        )
    field_config = result["field"]
    field_config["headland_width"] = float(fixture["headland_width_m"])
    field_config["scattering_extra_width"] = float(
        fixture["scattering_extra_width_m"]
    )
    speed = float(scene["travel_speed_m_s"])
    travel_m = speed * float(native["duration_s"])
    bed = next(iter(field_config["beds"].values()))
    plant_count = max(5, int(math.ceil(travel_m / 0.20)) + 1)
    bed["plants_count"] = plant_count
    bed["plant_distance"] = round(travel_m / (plant_count - 1), 9)
    bed["bed_width"] = float(fixture["bed_width_m"])
    bed["rows_count"] = int(fixture["crop_rows_count"])
    bed["row_distance"] = float(fixture["crop_row_distance_m"])
    field_config["noise"]["missing"] = 0.0
    field_config["noise"]["position"] = 0.0
    fixture_weed_family = str(fixture["weed_family"])
    source_weeds = field_config.get("weeds", {})
    if fixture_weed_family not in source_weeds:
        raise ContractError(
            f"Fixture weed family {fixture_weed_family!r} is absent from "
            f"{scene['pair_id']}"
        )
    field_config["weeds"] = {
        fixture_weed_family: source_weeds[fixture_weed_family]
    }
    for weed in field_config["weeds"].values():
        weed["density"] = float(fixture["weed_density_per_family"])
        weed["max_height"] = max(
            float(weed["max_height"]),
            float(fixture["weed_minimum_max_height_m"]),
        )
    if isinstance(field_config.get("stones"), dict):
        field_config["stones"]["density"] = float(fixture["stone_density"])
    deploy = result.setdefault("deploy_imaging_contract", {})
    deploy["module_raw_resolution_px"] = int(native["width_px"])
    deploy["module_ground_width_m"] = ground_fov_m
    deploy["derived_module_fov_deg"] = camera["fov_deg"]
    deploy["derived_ground_gsd_mm_per_px"] = float(native["ground_fov_mm"]) / float(
        native["width_px"]
    )
    result["botanical_gt_contract"] = {
        "identity_authority": "pre_render_source_point_attribute",
        "arm_neutral": True,
        "native_execution_fixture": True,
        "deterministic_crop_row_overlap_stress": bool(
            fixture["overlap_stress_fixture"]
        ),
        "semantic_connected_components_for_identity_forbidden": True,
    }
    return result


def full_roster_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = full_paths(config)["synthetic"] / "planning/pair_roster_v1.jsonl"
    if not path.is_file():
        raise ContractError("Full pair roster is missing")
    historical = read_jsonl(path)
    context = _validated_roster_extension_context(config)
    if context is None:
        return historical
    extension_path = roster_extension_paths(config)["manifest"]
    extension = read_jsonl(extension_path)
    merged = merge_full_roster_with_extension(historical, extension)
    if len(merged) != 96 or any(len(row["candidates"]) != 32 for row in merged):
        raise ContractError("Combined roster extension is incomplete")
    return merged


def full_roster_row(
    config: Mapping[str, Any], pair_id: str
) -> dict[str, Any]:
    matches = [row for row in full_roster_rows(config) if row["pair_id"] == pair_id]
    if len(matches) != 1:
        raise ContractError(f"Expected one full roster row for {pair_id}: {len(matches)}")
    return matches[0]


def full_candidate_source_path(
    config: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Path:
    role = config["full_benchmark"]["source_roles"][roster_row["protocol_split"]]
    scene_id = str(candidate["source_template"]["scene_id"])
    path = resolve_path(str(role["scene_config_root"])) / f"{scene_id}.yaml"
    if not path.is_file():
        raise ContractError(f"Full candidate source scene is missing: {path}")
    expected = require_sha256(
        candidate["source_template"]["sha256"], "candidate source template"
    )
    if sha256_file(path) != expected:
        raise ContractError(f"Full candidate source scene drift: {path}")
    return path


def derive_full_native_scene_config(
    base: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    asset_role: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    native = config["native_contract"]
    full = config["full_benchmark"]
    shared = roster_row["shared_latent_parameters"]
    factors = roster_row["factors"]
    profile = str(factors["v12_scene_profile"])
    observed_profile = result.get("agri_asset_profile", {}).get(
        "correlated_scene_profile"
    )
    if observed_profile != profile:
        raise ContractError(
            f"Full candidate source profile mismatch: {observed_profile} != {profile}"
        )
    if int(candidate["candidate_index"]) not in range(
        int(full["maximum_candidates_per_slot"])
    ):
        raise ContractError("Full candidate index is outside the frozen range")

    render = result["render"]
    render["frames"] = int(native["frames_per_arm"])
    render["resolution_x"] = int(native["width_px"])
    render["resolution_y"] = int(native["height_px"])
    render["samples"] = int(full["render_samples"])
    camera = render["camera"]
    working_distance_m = float(shared["working_distance_mm"]) / 1000.0
    ground_fov_m = float(shared["ground_fov_mm"]) / 1000.0
    camera["height"] = working_distance_m
    camera["fov_deg"] = round(
        math.degrees(2.0 * math.atan(ground_fov_m / (2.0 * working_distance_m))),
        9,
    )
    camera["roll_deg"] = float(shared["roll_deg"])
    camera["pitch_deg"] = float(shared["pitch_deg"])
    camera["yaw_deg"] = float(shared["yaw_deg"])
    camera["y_jitter"] = 0.0

    field_config = result["field"]
    seeds = {name: int(value) for name, value in candidate["seeds"].items()}
    field_config["random_seed"] = seeds["scene_seed"]
    field_config["headland_width"] = float(full["headland_width_m"])
    field_config["scattering_extra_width"] = float(
        full["scattering_extra_width_m"]
    )
    speed = float(factors["travel_speed_m_s"])
    travel_m = speed * float(native["duration_s"])
    for bed in field_config["beds"].values():
        original_distance = max(float(bed.get("plant_distance", 0.20)), 0.05)
        plant_count = max(5, int(math.ceil(travel_m / original_distance)) + 1)
        bed["plants_count"] = plant_count
        bed["plant_distance"] = round(travel_m / (plant_count - 1), 9)
        bed["bed_width"] = float(full["bed_width_m"])
    density_scale = float(full["weed_density_scale_from_v12"])
    density_floor = float(full["weed_density_minimum_per_family"])
    height_floor = float(full["weed_minimum_max_height_m"])
    for weed in field_config.get("weeds", {}).values():
        weed["density"] = max(float(weed["density"]) * density_scale, density_floor)
        weed["max_height"] = max(float(weed["max_height"]), height_floor)
    if isinstance(field_config.get("stones"), dict):
        field_config["stones"]["density"] = float(
            field_config["stones"]["density"]
        ) * float(full["stone_density_scale_from_v12"])

    surface = result.setdefault("agri_asset_profile", {}).setdefault(
        "surface_parameters", {}
    )
    for source_name, target_name in (
        ("environment_strength", "environment_strength"),
        ("soil_moisture", "soil_moisture"),
        ("sun_energy", "sun_energy"),
        ("sun_elevation_deg", "sun_elevation_deg"),
        ("sun_angle_deg", "sun_angle_deg"),
        ("local_shadow_fraction", "local_shadow_fraction"),
    ):
        surface[target_name] = float(shared[source_name])
    surface["shadow_seed"] = seeds["scene_seed"] % 2147483647
    ideal_capture = dict(roster_row["ideal_capture_parameters"])
    degraded_capture = dict(roster_row["degraded_capture_parameters"])
    surface["artificial_light_energy"] = float(
        ideal_capture["artificial_light_energy_renderer_units"]
    )
    surface["artificial_light_size_m"] = float(
        ideal_capture["artificial_light_size_m"]
    )
    surface["artificial_light_warmth"] = float(
        ideal_capture["artificial_light_warmth_proxy"]
    )

    allowlist = [str(value) for value in asset_role["allowlist"]]
    if stable_sha256(allowlist) != asset_role["allowlist_sha256"]:
        raise ContractError("Full role asset allowlist digest changed")
    shared_field = {
        "pair_id": roster_row["pair_id"],
        "protocol_split": roster_row["protocol_split"],
        "source_template": copy.deepcopy(candidate["source_template"]),
        "source_asset_allowlist_sha256": asset_role["allowlist_sha256"],
        "source_asset_object_identity_sha256": asset_role[
            "object_identity_sha256"
        ],
        "scene_seed": seeds["scene_seed"],
        "trajectory_seed": seeds["trajectory_seed"],
        "renderer_seed": seeds["renderer_seed"],
        "factors": copy.deepcopy(factors),
        "shared_latent_parameters": copy.deepcopy(shared),
        "frame_count": int(native["frames_per_arm"]),
        "frame_rate_hz": int(native["frame_rate_hz"]),
    }
    result["full_execution_contract"] = {
        "schema_version": 1,
        "contract": FULL_CROPCRAFT_CONTRACT,
        "pair_id": roster_row["pair_id"],
        "protocol_split": roster_row["protocol_split"],
        "pair_slot_identity_sha256": roster_row["pair_slot_identity_sha256"],
        "candidate_index": int(candidate["candidate_index"]),
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "source_template": copy.deepcopy(candidate["source_template"]),
        "seeds": seeds,
        "seed_channels_exact": list(_protocol(config)["seed_derivation"]["channels"]),
        "role_asset_allowlist": allowlist,
        "role_asset_allowlist_sha256": asset_role["allowlist_sha256"],
        "role_asset_object_identity_sha256": asset_role[
            "object_identity_sha256"
        ],
        "shared_latent_parameters": copy.deepcopy(shared),
        "shared_field_identity_sha256": stable_sha256(shared_field),
        "ideal_capture_parameters": ideal_capture,
        "degraded_capture_parameters": degraded_capture,
        "model_access_allowed": False,
        "outcome_inputs": [],
    }
    result["botanical_gt_contract"] = {
        "identity_authority": "pre_render_source_point_attribute",
        "arm_neutral": True,
        "native_full_candidate": True,
        "empty_weed_family_carriers_allowed": True,
        "per_pair_occlusion_minimum_deferred_to_full_release": True,
        "semantic_connected_components_for_identity_forbidden": True,
    }
    return result


def _new_file_unified_patch(path: str, content: str) -> str:
    lines = content.splitlines()
    body = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )


def full_runtime_overlay_patch() -> bytes:
    modifications = r'''diff --git a/core/plant_manager.py b/core/plant_manager.py
--- a/core/plant_manager.py
+++ b/core/plant_manager.py
@@ -18,1 +18,2 @@
 from . import input_utils
+from . import full_ab
@@ -165,5 +166,6 @@ class PlantManager:
             model
             for model in model_list
             if model.height >= lower_bound and model.height <= higher_bound
         ]
+        correct_models = full_ab.filter_models(type, correct_models)
         return correct_models if correct_models else None
diff --git a/core/blender_entrypoint.py b/core/blender_entrypoint.py
--- a/core/blender_entrypoint.py
+++ b/core/blender_entrypoint.py
@@ -21,1 +21,2 @@
 from core import botanical_gt
+from core import full_ab
@@ -75,7 +76,7 @@ def main(argv: list):
 
     if cfg.render is not None:
         core.base.setup_camera_animation(cfg.render, beds.get_end_pos())
-        core.base.render_animation(cfg.render, labeled=False, output_dir=output_dir)
+        full_ab.render_capture_arms(cfg.render, output_dir)
         beds.apply_label_materials(cfg.render.label_colors)
         if botanical_tracks is not None:
             botanical_gt.apply_semantic_materials(
diff --git a/core/botanical_gt.py b/core/botanical_gt.py
--- a/core/botanical_gt.py
+++ b/core/botanical_gt.py
@@ -16,5 +16,6 @@ import bpy
 import numpy as np
 from PIL import Image
 
+from core import full_ab
 
 GT_DIRECTORY = "botanical_ground_truth"
@@ -137,7 +138,7 @@ def _instance_matrix_key(matrix):
     return tuple(round(float(value), 12) for row in matrix for value in row)
 
 
-def _carrier_instances(depsgraph, carrier):
+def _carrier_instances(depsgraph, carrier, allow_empty=False):
     rows = []
     for instance in depsgraph.object_instances:
         if not instance.is_instance or instance.instance_object is None:
@@ -167,7 +168,7 @@ def _carrier_instances(depsgraph, carrier):
             _instance_matrix_key(row["matrix_world"]),
         )
     )
-    if not rows:
+    if not rows and not allow_empty:
         raise RuntimeError(f"No pre-render dependency-graph instances: {carrier.name}")
     persistent_ids = [row["persistent_id"] for row in rows]
     if len(set(persistent_ids)) != len(persistent_ids):
@@ -256,7 +257,9 @@ def materialize_source_plants(field, output_dir):
     depsgraph = bpy.context.evaluated_depsgraph_get()
     for carrier_row in carriers:
         carrier = carrier_row["carrier"]
-        instances = _carrier_instances(depsgraph, carrier)
+        instances = _carrier_instances(
+            depsgraph, carrier, allow_empty=carrier_row["class_name"] == "weed"
+        )
         if carrier_row["class_name"] == "crop":
             assignments = _match_crop_instances(
                 instances, carrier_row["source_states"], carrier.name
@@ -567,7 +570,7 @@ def render_track_ground_truth(tracks, render, output_dir):
     }
     _write_json(root / "track_registry.json", registry)
     _write_jsonl(root / "tracks.jsonl", rows)
-    if registry["frames_with_source_silhouette_overlap"] < 1:
+    if not full_ab.enabled() and registry["frames_with_source_silhouette_overlap"] < 1:
         raise RuntimeError("Pilot has no overlapping source-plant silhouettes")
-    if registry["occluded_track_frame_rows"] < 1:
+    if not full_ab.enabled() and registry["occluded_track_frame_rows"] < 1:
         raise RuntimeError("Pilot did not exercise botanical occlusion")
'''
    payload = _new_file_unified_patch("core/full_ab.py", FULL_AB_MODULE_SOURCE)
    payload += modifications
    return payload.encode("utf-8")


def compose_scene_patch(
    config: Mapping[str, Any],
    destination: Path,
    *,
    include_full_runtime_overlay: bool = False,
) -> dict[str, Any]:
    locks = config["source_locks"]
    surface = resolve_path(str(locks["surface_lighting_patch"]["path"]))
    botanical = resolve_path(str(locks["botanical_patch"]["path"]))
    surface_bytes = surface.read_bytes()
    botanical_bytes = botanical.read_bytes()
    constituents = [
        {
            "path": display_path(surface),
            "sha256": sha256_file(surface),
        },
        {
            "path": display_path(botanical),
            "sha256": sha256_file(botanical),
        },
    ]
    payload = surface_bytes.rstrip(b"\n") + b"\n" + botanical_bytes.rstrip(b"\n")
    if include_full_runtime_overlay:
        overlay = full_runtime_overlay_patch()
        payload += b"\n" + overlay.rstrip(b"\n")
        constituents.append(
            {
                "path": "embedded:full_runtime_overlay_v1",
                "sha256": hashlib.sha256(overlay).hexdigest(),
            }
        )
    if not payload.endswith(b"\n"):
        payload += b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "path": display_path(destination),
        "sha256": sha256_file(destination),
        "ordered_constituents": constituents,
        "full_runtime_overlay_included": include_full_runtime_overlay,
    }


def _import_binding(module_name: str) -> Any:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    return importlib.import_module(module_name)


def run_cropcraft_scene(
    scene_config_path: Path,
    destination: Path,
    combined_patch: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if destination.exists():
        raise ContractError(f"Scene output already exists: {destination}")
    scene_config = load_yaml(scene_config_path)
    profile = scene_config["agri_asset_profile"]
    locks = config["source_locks"]
    command = [
        sys.executable,
        str(resolve_path(str(locks["cropcraft_runner"]["path"]))),
        str(scene_config_path),
        "--output",
        str(destination),
        "--repository",
        str(resolve_path(str(config["runtime"]["cropcraft_repository"]))),
        "--blender",
        str(resolve_path(str(locks["blender"]["path"]))),
        "--python-environment",
        str(resolve_path(str(config["runtime"]["cropcraft_python_environment"]))),
        "--expected-revision",
        str(config["runtime"]["cropcraft_revision"]),
        "--compatibility-patch",
        str(resolve_path(str(locks["compatibility_patch"]["path"]))),
        "--scene-patch",
        str(combined_patch),
        "--asset-pack",
        str(resolve_path(str(locks["v12_asset_pack"]["path"])).parent),
        "--ground-material-id",
        str(profile["ground_material_id"]),
    ]
    environment = os.environ.copy()
    environment["CROPCRAFT_BOTANICAL_GT"] = "1"
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    log_path = destination.parent / f"{destination.name}.runner.log"
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-80:])
        raise ContractError(f"CropCraft native scene failed:\n{tail}")
    receipt_path = destination / "generation_receipt.json"
    receipt = load_json(receipt_path)
    if receipt.get("scene_patch_sha256") != sha256_file(combined_patch):
        raise ContractError("Generation receipt did not bind the composed scene patch")
    return {
        "receipt_path": display_path(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "scene_patch_sha256": receipt["scene_patch_sha256"],
        "validated_pairs": int(receipt["validation"]["validated_pairs"]),
        "elapsed_wall_seconds": time.perf_counter() - started,
        "runner_log": display_path(log_path),
        "runner_log_sha256": sha256_file(log_path),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError(f"Invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ContractError(f"Expected object at {path}:{line_number}")
        rows.append(value)
    return rows


def validate_botanical_scene(
    scene_root: Path,
    config: Mapping[str, Any],
    *,
    full_candidate: bool = False,
) -> dict[str, Any]:
    botanical = _import_binding("scripts.build_spot_spray_botanical_track_ground_truth_v1")
    botanical_config = load_yaml(
        resolve_path(str(config["source_locks"]["botanical_config"]["path"]))
    )
    gates = botanical_config["quality_gates"]
    gates["exact_frame_count"] = int(config["native_contract"]["frames_per_arm"])
    gates["minimum_crop_tracks"] = 1
    gates["minimum_weed_tracks"] = 1
    if full_candidate:
        gates["minimum_frames_with_source_silhouette_overlap"] = 0
        gates["minimum_occluded_track_frame_rows"] = 0
    validation = botanical.validate_scene(scene_root, botanical_config)
    if not all(validation["quality_gates"].values()):
        raise ContractError("Botanical native scene validation failed")
    return validation


def motion_psf(
    path_length_px: float,
    path_family: str,
    sample_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if not 0.0 <= path_length_px <= 0.75:
        raise ContractError(f"Motion path outside [0, 0.75] px: {path_length_px}")
    if sample_count < 3 or sample_count % 2 == 0:
        raise ContractError("PSF sample_count must be odd and at least three")
    u = np.linspace(-0.5, 0.5, sample_count, dtype=np.float64)
    if path_family == "linear":
        points = np.stack([u, np.zeros_like(u)], axis=1)
    elif path_family == "smooth_curved":
        points = np.stack([u, 0.16 * np.sin(math.pi * u)], axis=1)
    else:
        raise ContractError(f"Unknown degraded motion path: {path_family}")
    points -= points.mean(axis=0, keepdims=True)
    arc = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
    if arc > 0.0:
        points *= path_length_px / arc
    kernel = np.zeros((3, 3), dtype=np.float64)
    for x, y in points:
        px = 1.0 + float(x)
        py = 1.0 + float(y)
        x0, y0 = int(math.floor(px)), int(math.floor(py))
        fx, fy = px - x0, py - y0
        for yy, wy in ((y0, 1.0 - fy), (y0 + 1, fy)):
            for xx, wx in ((x0, 1.0 - fx), (x0 + 1, fx)):
                if 0 <= yy < 3 and 0 <= xx < 3:
                    kernel[yy, xx] += wx * wy / sample_count
    kernel /= kernel.sum()
    yy, xx = np.indices(kernel.shape, dtype=np.float64)
    centroid_x = float(((xx - 1.0) * kernel).sum())
    centroid_y = float(((yy - 1.0) * kernel).sum())
    state = {
        "path_family": path_family,
        "requested_path_length_px": path_length_px,
        "sample_count": sample_count,
        "kernel": kernel.tolist(),
        "kernel_sum": float(kernel.sum()),
        "centroid_xy_px": [centroid_x, centroid_y],
        "centroid_error_px": math.hypot(centroid_x, centroid_y),
        "convolution_border": "reflect_101",
    }
    if not math.isclose(state["kernel_sum"], 1.0, abs_tol=1.0e-6):
        raise ContractError("PSF does not sum to one")
    if state["centroid_error_px"] > 0.15:
        raise ContractError("PSF centroid exceeds frozen tolerance")
    return kernel.astype(np.float32), state


def apply_protocol_degradation(
    ideal_rgb: np.ndarray,
    *,
    speed_m_s: float,
    pulse_width_us: float,
    gsd_mm_per_px: float,
    path_family: str,
    sample_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    path_length = speed_m_s * pulse_width_us * 0.001 / gsd_mm_per_px
    kernel, state = motion_psf(path_length, path_family, sample_count)
    output = cv2.filter2D(
        ideal_rgb,
        -1,
        kernel,
        borderType=cv2.BORDER_REFLECT_101,
    )
    if output.shape != ideal_rgb.shape or output.dtype != np.uint8:
        raise ContractError("Degraded capture changed RGB geometry or dtype")
    state.update(
        {
            "speed_m_s": speed_m_s,
            "pulse_width_us": pulse_width_us,
            "gsd_mm_per_px": gsd_mm_per_px,
            "extra_noise_or_compression_applied": False,
            "post_outcome_rescaling_applied": False,
        }
    )
    return output, state


def _semantic_ids(rgb: np.ndarray) -> np.ndarray:
    output = np.zeros(rgb.shape[:2], dtype=np.uint8)
    crop = np.all(rgb == np.asarray([0, 255, 0], dtype=np.uint8), axis=2)
    weed = np.all(rgb == np.asarray([255, 0, 0], dtype=np.uint8), axis=2)
    allowed = np.logical_or(np.logical_or(crop, weed), np.all(rgb == 0, axis=2))
    if not bool(allowed.all()):
        raise ContractError("Semantic palette contains undeclared colours")
    output[crop] = 1
    output[weed] = 2
    return output


def _instance_ids(instance_rgb: np.ndarray, source_tracks: Sequence[Mapping[str, Any]]) -> np.ndarray:
    output = np.zeros(instance_rgb.shape[:2], dtype=np.uint16)
    declared_colours: set[tuple[int, int, int]] = {(0, 0, 0)}
    for track in source_tracks:
        colour = tuple(int(value) for value in track["render_color_rgb"])
        declared_colours.add(colour)
        output[np.all(instance_rgb == np.asarray(colour, dtype=np.uint8), axis=2)] = int(
            track["render_id"]
        )
    observed = {
        tuple(int(value) for value in row)
        for row in np.unique(instance_rgb.reshape(-1, 3), axis=0)
    }
    if not observed <= declared_colours:
        raise ContractError(f"Instance palette has undeclared colours: {observed - declared_colours}")
    return output


def _size_stratum(canopy_span_mm: float) -> str:
    if canopy_span_mm < 20.0:
        return "below_eligible_size"
    if canopy_span_mm < 40.0:
        return "small"
    if canopy_span_mm < 80.0:
        return "medium"
    return "large"


def _partial_in_action_region(mask: np.ndarray, outer_ring: int) -> bool:
    ys, xs = np.where(mask)
    if not len(xs):
        return True
    height, width = mask.shape
    return bool(
        xs.min() < outer_ring
        or ys.min() < outer_ring
        or xs.max() >= width - outer_ring
        or ys.max() >= height - outer_ring
    )


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _hardlink_or_verify(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ContractError(f"Refusing to replace generated GT link: {destination}")
    os.link(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise ContractError("Hardlinked ground truth hash changed")


def _video_encoding() -> dict[str, Any]:
    return {
        "codec": "libx264",
        "crf": 18,
        "preset": "medium",
        "pixel_format": "yuv420p",
        "deterministic_threads": 1,
    }


def create_side_by_side_video(
    ffmpeg: Path,
    left: Path,
    right: Path,
    destination: Path,
    *,
    half_width: int = 1024,
) -> None:
    _run_text(
        [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(left),
            "-i",
            str(right),
            "-filter_complex",
            (
                f"[0:v]scale={half_width}:-2[left];"
                f"[1:v]scale={half_width}:-2[right];"
                "[left][right]hstack=inputs=2[v]"
            ),
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            "-n",
            str(destination),
        ]
    )


def build_pair_package(
    scene_root: Path,
    destination: Path,
    scene: Mapping[str, Any],
    config: Mapping[str, Any],
    manifest_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    renderer = _import_binding("scripts.build_spot_spray_simulation_video_pairs_v1")
    native = config["native_contract"]
    pair_id = str(scene["pair_id"])
    split = str(scene["split"])
    frame_count = int(native["frames_per_arm"])
    fps = int(native["frame_rate_hz"])
    width = int(native["width_px"])
    height = int(native["height_px"])
    full_candidate = bool(scene.get("full_candidate", False))
    manifest_pair_prefix = scene.get("manifest_pair_prefix")
    if full_candidate and not isinstance(manifest_pair_prefix, str):
        raise ContractError("Full candidate manifest pair prefix is missing")
    gt_source = scene_root / "botanical_ground_truth"
    source_registry = load_json(gt_source / "source_objects.json")
    source_tracks = source_registry["tracks"]
    track_by_id = {str(row["track_id"]): row for row in source_tracks}
    track_by_render = {int(row["render_id"]): row for row in source_tracks}
    track_rows = read_jsonl(gt_source / "tracks.jsonl")
    track_row_by_frame_id = {
        (str(row["frame_id"]), str(row["track_id"])): row for row in track_rows
    }
    shared_semantic = destination / "shared_gt/semantic"
    shared_tracks = destination / "shared_gt/tracks"
    ideal_dir = destination / "ideal/rgb"
    degraded_dir = destination / "degraded/rgb"
    for path in (shared_semantic, shared_tracks, ideal_dir, degraded_dir):
        path.mkdir(parents=True, exist_ok=False)

    speed = float(scene["travel_speed_m_s"])
    pulse_map = config["capture_profiles"]["degraded"]["pulse_width_us_by_speed"]
    pulse = float(
        scene.get("degraded_pulse_width_us", pulse_map[format(speed, ".1f")])
    )
    ground_fov_mm = float(scene.get("ground_fov_mm", native["ground_fov_mm"]))
    gsd = ground_fov_mm / width
    frame_records: dict[str, list[dict[str, Any]]] = {"ideal": [], "degraded": []}
    timing_rows: list[dict[str, Any]] = []
    gt_identity_rows: list[dict[str, Any]] = []
    psf_states: list[dict[str, Any]] = []
    rmse_values: list[float] = []
    changed_fractions: list[float] = []
    eligible_tracks: set[str] = set()
    eligible_observations: dict[str, int] = defaultdict(int)
    brightness: dict[str, list[float]] = {"ideal": [], "degraded": []}
    white_fraction: dict[str, list[float]] = {"ideal": [], "degraded": []}
    black_fraction: dict[str, list[float]] = {"ideal": [], "degraded": []}
    crop_fractions: list[float] = []
    weed_fractions: list[float] = []

    for frame_index in range(frame_count):
        source_stem = f"frame_{frame_index + 1:04d}"
        output_stem = f"frame_{frame_index:06d}"
        if full_candidate:
            rgb_path = (
                scene_root
                / "render/full_ab/ideal_rgb"
                / f"{source_stem}.png"
            )
            degraded_base_path = (
                scene_root
                / "render/full_ab/degraded_base_rgb"
                / f"{source_stem}.png"
            )
        else:
            rgb_path = scene_root / "render/images" / f"{source_stem}.jpg"
            degraded_base_path = rgb_path
        semantic_rgb_path = scene_root / "render/masks" / f"{source_stem}.png"
        instance_rgb_path = gt_source / "instance_masks" / f"{source_stem}.png"
        if not all(
            path.is_file()
            for path in (
                rgb_path,
                degraded_base_path,
                semantic_rgb_path,
                instance_rgb_path,
            )
        ):
            raise ContractError(f"Incomplete native scene frame: {source_stem}")
        ideal_rgb = np.asarray(Image.open(rgb_path).convert("RGB"), dtype=np.uint8)
        degraded_base_rgb = np.asarray(
            Image.open(degraded_base_path).convert("RGB"), dtype=np.uint8
        )
        semantic_rgb = np.asarray(
            Image.open(semantic_rgb_path).convert("RGB"), dtype=np.uint8
        )
        instance_rgb = np.asarray(
            Image.open(instance_rgb_path).convert("RGB"), dtype=np.uint8
        )
        if ideal_rgb.shape != (height, width, 3) or degraded_base_rgb.shape != (
            height,
            width,
            3,
        ):
            raise ContractError(
                f"Native RGB shape changed: {ideal_rgb.shape}/{degraded_base_rgb.shape}"
            )
        semantic = _semantic_ids(semantic_rgb)
        track_mask = _instance_ids(instance_rgb, source_tracks)
        degraded_rgb, psf_state = apply_protocol_degradation(
            degraded_base_rgb,
            speed_m_s=speed,
            pulse_width_us=pulse,
            gsd_mm_per_px=gsd,
            path_family=str(scene["degraded_motion_path"]),
            sample_count=int(config["capture_profiles"]["degraded"]["psf_samples"]),
        )
        psf_state["frame_index"] = frame_index
        psf_states.append(psf_state)
        difference = degraded_rgb.astype(np.float32) - ideal_rgb.astype(np.float32)
        rmse_values.append(float(np.sqrt(np.mean(difference * difference))))
        changed_fractions.append(float(np.any(degraded_rgb != ideal_rgb, axis=2).mean()))
        crop_fractions.append(float((semantic == 1).mean()))
        weed_fractions.append(float((semantic == 2).mean()))
        for condition, pixels in (("ideal", ideal_rgb), ("degraded", degraded_rgb)):
            brightness[condition].append(float(pixels.mean()))
            white_fraction[condition].append(
                float(np.all(pixels == 255, axis=2).mean())
            )
            black_fraction[condition].append(
                float(np.all(pixels == 0, axis=2).mean())
            )

        ideal_path = ideal_dir / f"{output_stem}.png"
        degraded_path = degraded_dir / f"{output_stem}.png"
        semantic_path = shared_semantic / f"{output_stem}.png"
        track_path = shared_tracks / f"{output_stem}.png"
        Image.fromarray(ideal_rgb, mode="RGB").save(ideal_path, format="PNG", compress_level=3)
        Image.fromarray(degraded_rgb, mode="RGB").save(
            degraded_path, format="PNG", compress_level=3
        )
        Image.fromarray(semantic, mode="L").save(
            semantic_path, format="PNG", compress_level=9
        )
        if not cv2.imwrite(str(track_path), track_mask):
            raise ContractError(f"Failed to write uint16 track mask: {track_path}")

        labels: list[dict[str, Any]] = []
        for render_id in sorted(int(value) for value in np.unique(track_mask) if int(value)):
            source_track = track_by_render[render_id]
            track_id = str(source_track["track_id"])
            table = track_row_by_frame_id[(source_stem, track_id)]
            selected = track_mask == render_id
            semantic_values = set(int(value) for value in np.unique(semantic[selected]))
            expected_semantic = 1 if source_track["class_name"] == "crop" else 2
            if semantic_values != {expected_semantic}:
                raise ContractError(
                    f"Botanical class/semantic mismatch for {pair_id}:{track_id}:{frame_index}"
                )
            partial = bool(table["partial_at_frame_boundary"]) or _partial_in_action_region(
                selected, int(native["outer_abstain_ring_px"])
            )
            label = {
                "mask_id": render_id,
                "track_id": f"{split}:{pair_id}:{track_id}",
                "class_name": str(source_track["class_name"]),
                "canopy_span_mm": float(source_track["canopy_span_mm"]),
                "visible_fraction": float(table["visible_fraction"]),
                "partial": partial,
                "size_stratum": _size_stratum(float(source_track["canopy_span_mm"])),
            }
            labels.append(label)
            if (
                label["class_name"] == "weed"
                and label["canopy_span_mm"] >= 20.0
                and label["visible_fraction"] >= 0.70
                and not label["partial"]
            ):
                eligible_tracks.add(label["track_id"])
                eligible_observations[label["track_id"]] += 1
        if not labels:
            raise ContractError(f"No visible botanical tracks in {pair_id}:{frame_index}")

        semantic_sha = sha256_file(semantic_path)
        track_sha = sha256_file(track_path)
        gt_identity_rows.append(
            {
                "frame_index": frame_index,
                "semantic_sha256": semantic_sha,
                "track_sha256": track_sha,
                "tracks": labels,
            }
        )
        timestamp_ns = round(frame_index * 1_000_000_000 / fps)
        timing_rows.append(
            {
                "frame_index": frame_index,
                "timestamp_ns": timestamp_ns,
                "encoder_mm": format(speed * timestamp_ns / 1_000_000.0, ".6f"),
                "exposure_us": pulse,
                "gain_db": 0.0,
                "working_distance_mm": float(scene_root.joinpath("config.input.yaml").is_file() and load_yaml(scene_root / "config.input.yaml")["render"]["camera"]["height"] * 1000.0),
                "strobe_profile_id": (
                    "full_ab_four_quadrant_surface_light_proxy"
                    if full_candidate
                    else "shared_v12_surface_light_proxy"
                ),
                "split": split,
            }
        )
        for condition, image_path in (("ideal", ideal_path), ("degraded", degraded_path)):
            if full_candidate:
                image_relative = (
                    f"{manifest_pair_prefix}/"
                    f"{image_path.relative_to(destination).as_posix()}"
                )
                semantic_relative = (
                    f"{manifest_pair_prefix}/"
                    f"{semantic_path.relative_to(destination).as_posix()}"
                )
                track_relative = (
                    f"{manifest_pair_prefix}/"
                    f"{track_path.relative_to(destination).as_posix()}"
                )
            else:
                image_relative = _relative(image_path, manifest_root)
                semantic_relative = _relative(semantic_path, manifest_root)
                track_relative = _relative(track_path, manifest_root)
            frame_records[condition].append(
                {
                    "frame_id": f"{condition}:{pair_id}:frame_{frame_index:04d}",
                    "frame_index": frame_index,
                    "image_path": image_relative,
                    "image_sha256": sha256_file(image_path),
                    "semantic_mask_path": semantic_relative,
                    "semantic_mask_sha256": semantic_sha,
                    "track_mask_path": track_relative,
                    "track_mask_sha256": track_sha,
                    "tracks": labels,
                }
            )

    if not eligible_tracks:
        if full_candidate:
            raise CandidateRejected(
                f"Full candidate has no eligible weed track: {pair_id}",
                {
                    "pair_quality_gates": {
                        "temporal_denominator_contribution": False
                    },
                    "gate_details": {
                        "temporal_denominator_contribution": {
                            "eligible_weed_track_present": False,
                            "eligibility_contract": {
                                "class_name": "weed",
                                "minimum_canopy_span_mm": 20.0,
                                "minimum_visible_fraction": 0.70,
                                "partial_allowed": False,
                            },
                        }
                    },
                    "model_or_outcome_inputs": [],
                },
            )
        raise ContractError(f"Fixture pair has no eligible weed track: {pair_id}")
    if min(changed_fractions) <= 0.0 or min(rmse_values) <= 0.0:
        raise ContractError(f"Degraded arm did not differ from ideal in every frame: {pair_id}")

    metadata_root = destination / "metadata"
    write_jsonl(metadata_root / "frame_timing.jsonl", timing_rows)
    write_json(metadata_root / "psf_receipt.json", {"frames": psf_states})
    sequences = [
        {
            "sequence_id": f"{condition}:{pair_id}",
            "pair_id": pair_id,
            "scene_id": pair_id,
            "split": split,
            "condition": condition,
            "frames": frame_records[condition],
        }
        for condition in ("ideal", "degraded")
    ]

    ffmpeg = resolve_path(str(config["source_locks"]["ffmpeg"]["path"]))
    ffprobe = resolve_path(str(config["source_locks"]["ffprobe"]["path"]))
    ideal_video = destination / "ideal/rgb.mp4"
    degraded_video = destination / "degraded/rgb.mp4"
    renderer.encode_rgb_video(
        ffmpeg, ideal_dir, ideal_video, frame_count, fps, _video_encoding()
    )
    renderer.encode_rgb_video(
        ffmpeg, degraded_dir, degraded_video, frame_count, fps, _video_encoding()
    )
    side_by_side = destination / "side_by_side.mp4"
    create_side_by_side_video(ffmpeg, ideal_video, degraded_video, side_by_side)
    probes = {
        "ideal": renderer.probe_video(ffprobe, ideal_video),
        "degraded": renderer.probe_video(ffprobe, degraded_video),
        "side_by_side": renderer.probe_video(ffprobe, side_by_side),
    }
    for condition in ("ideal", "degraded"):
        probe = probes[condition]
        if (
            probe["width"] != width
            or probe["height"] != height
            or probe["decoded_frame_count"] != frame_count
            or probe["average_frame_rate"] != f"{fps}/1"
        ):
            raise ContractError(f"Unreadable native {condition} video for {pair_id}: {probe}")
    if probes["side_by_side"]["decoded_frame_count"] != frame_count:
        raise ContractError(f"Unreadable side-by-side video for {pair_id}")

    receipt = {
        "pair_id": pair_id,
        "split": split,
        "source_role": scene["source_role"],
        "travel_speed_m_s": speed,
        "scene_profile": scene["scene_profile"],
        "degraded_motion_path": scene["degraded_motion_path"],
        "frame_count_per_arm": frame_count,
        "frame_rate_hz": fps,
        "native_dimensions_px": [width, height],
        "source_scene_graph_identity_sha256": source_registry[
            "source_scene_graph_identity_sha256"
        ],
        "source_track_count": len(track_by_id),
        "visible_eligible_weed_track_count": len(eligible_tracks),
        "canonical_gt_sha256": stable_sha256(gt_identity_rows),
        "arm_gt_identity": {
            "ideal": stable_sha256(gt_identity_rows),
            "degraded": stable_sha256(gt_identity_rows),
            "byte_identical": True,
            "shared_paths": True,
        },
        "capture_difference": {
            "rgb_rmse_minimum": min(rmse_values),
            "rgb_rmse_mean": float(np.mean(rmse_values)),
            "changed_pixel_fraction_minimum": min(changed_fractions),
            "psf_path_px": psf_states[0]["requested_path_length_px"],
            "psf_centroid_error_px_maximum": max(
                float(row["centroid_error_px"]) for row in psf_states
            ),
            "differences_restricted_to_rgb_capture_profile": True,
        },
        "pixel_audit": {
            condition: {
                "mean_brightness_minimum": min(brightness[condition]),
                "mean_brightness_mean": float(np.mean(brightness[condition])),
                "mean_brightness_maximum": max(brightness[condition]),
                "fully_clipped_white_fraction_maximum": max(
                    white_fraction[condition]
                ),
                "fully_clipped_black_fraction_maximum": max(
                    black_fraction[condition]
                ),
            }
            for condition in ("ideal", "degraded")
        },
        "semantic_audit": {
            "mean_crop_fraction": float(np.mean(crop_fractions)),
            "mean_weed_fraction": float(np.mean(weed_fractions)),
            "crop_free_frame_fraction": float(
                np.mean(np.asarray(crop_fractions) == 0.0)
            ),
            "weed_free_frame_fraction": float(
                np.mean(np.asarray(weed_fractions) == 0.0)
            ),
        },
        "temporal_audit": {
            "eligible_track_observation_counts": dict(
                sorted(eligible_observations.items())
            ),
            "eligible_track_with_at_least_three_observations": any(
                count >= 3 for count in eligible_observations.values()
            ),
        },
        "videos": probes,
        "quality_gates": {
            "exact_native_dimensions": True,
            "exact_frames_per_arm": True,
            "exact_frame_rate": True,
            "identical_arm_ground_truth": True,
            "degraded_rgb_differs_every_frame": True,
            "eligible_weed_track_present": True,
            "all_videos_readable": True,
            "psf_path_within_0p75_px": max(
                float(row["requested_path_length_px"]) for row in psf_states
            )
            <= 0.75,
            "psf_centroid_within_0p15_px": max(
                float(row["centroid_error_px"]) for row in psf_states
            )
            <= 0.15,
        },
    }
    if not all(receipt["quality_gates"].values()):
        raise ContractError(f"Fixture pair quality gates failed: {pair_id}")
    write_json(destination / "pair_receipt.json", receipt)
    return sequences, receipt


def validate_full_used_assets(
    scene_root: Path, asset_role: Mapping[str, Any]
) -> dict[str, Any]:
    source = load_json(scene_root / "botanical_ground_truth/source_objects.json")
    allowlist = set(str(value) for value in asset_role["allowlist"])
    allowed_by_type: dict[str, set[str]] = defaultdict(set)
    for value in allowlist:
        family, filename = value.split("/", 1)
        allowed_by_type[family].add(Path(filename).stem)
    used: set[str] = set()
    exposed_candidates: set[str] = set()
    for track in source["tracks"]:
        plant_type = str(track["source"]["plant_type"])
        source_object = str(track["source_instance_object"])
        candidates = set(str(value) for value in track["source"]["source_asset_candidates"])
        if source_object not in allowed_by_type.get(plant_type, set()):
            raise ContractError(
                f"Full candidate used a disallowed source asset: {plant_type}/{source_object}"
            )
        if not candidates <= allowed_by_type.get(plant_type, set()):
            raise ContractError(
                f"CropCraft exposed assets outside the role allowlist: {plant_type}"
            )
        used.add(f"{plant_type}/{source_object}")
        exposed_candidates.update(f"{plant_type}/{value}" for value in candidates)
    if not used or not used <= {f"{Path(value).parent.name}/{Path(value).stem}" for value in allowlist}:
        raise ContractError("Full used-asset set is empty or escaped the role allowlist")
    return {
        "role_allowlist_sha256": asset_role["allowlist_sha256"],
        "role_object_identity_sha256": asset_role["object_identity_sha256"],
        "used_asset_stems": sorted(used),
        "used_asset_count": len(used),
        "exposed_candidate_stems": sorted(exposed_candidates),
        "exposed_candidate_count": len(exposed_candidates),
        "all_used_and_exposed_assets_allowed": True,
    }


def validate_full_capture_receipt(
    scene_root: Path,
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    path = scene_root / "full_ab_capture_receipt.json"
    receipt = load_json(path)
    bindings = receipt.get("seed_bindings", {})
    valid = (
        receipt.get("contract") == FULL_CROPCRAFT_CONTRACT
        and receipt.get("pair_id") == roster_row["pair_id"]
        and receipt.get("candidate_identity_sha256")
        == candidate["candidate_identity_sha256"]
        and receipt.get("frame_count") == 30
        and receipt.get("native_dimensions_px") == [2048, 2048]
        and receipt.get("lossless_rgb_source") is True
        and receipt.get("model_access") is False
        and receipt.get("prediction_access") is False
        and receipt.get("deterministic_replay", {}).get(
            "all_frames_pixel_exact"
        )
        is True
        and set(bindings) == set(candidate["seeds"])
        and all(
            int(bindings[name]["value"]) == int(value)
            for name, value in candidate["seeds"].items()
        )
        and receipt.get("ideal_light", {}).get("quadrant_count") == 4
        and receipt.get("degraded_light", {}).get("quadrant_count") == 4
        and receipt.get("ideal_light", {}).get("all_quadrants_on") is True
        and receipt.get("degraded_light", {}).get("all_quadrants_on") is True
    )
    if not valid:
        raise ContractError("Full CropCraft capture receipt changed")
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "seed_bindings": bindings,
        "ideal_light": receipt["ideal_light"],
        "degraded_light": receipt["degraded_light"],
        "trajectory": receipt["trajectory"],
        "deterministic_replay": {
            "all_frames_pixel_exact": True,
            "all_png_bytes_exact": bool(
                receipt["deterministic_replay"]["all_png_bytes_exact"]
            ),
            "frame_count": len(receipt["deterministic_replay"]["frame_rows"]),
            "gate_basis": "decoded_rgb_pixel_identity",
            "png_container_byte_identity_is_diagnostic": True,
        },
    }


def evaluate_full_candidate_gates(
    pair_receipt: Mapping[str, Any],
    botanical_validation: Mapping[str, Any],
    used_assets: Mapping[str, Any],
    capture_validation: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    protocol = _protocol(config)
    frozen = protocol["preoutcome_gates"]["pixel_visual"]
    brightness_min, brightness_max = (
        float(frozen["mean_brightness"][0]),
        float(frozen["mean_brightness"][1]),
    )
    pixel = pair_receipt["pixel_audit"]
    semantic = pair_receipt["semantic_audit"]
    pixel_details = {
        "all_frame_mean_brightness_in_range": all(
            pixel[condition]["mean_brightness_minimum"] >= brightness_min
            and pixel[condition]["mean_brightness_maximum"] <= brightness_max
            for condition in ("ideal", "degraded")
        ),
        "white_clipping_within_limit": all(
            pixel[condition]["fully_clipped_white_fraction_maximum"]
            <= float(frozen["maximum_fully_clipped_white_fraction"])
            for condition in ("ideal", "degraded")
        ),
        "black_clipping_within_limit": all(
            pixel[condition]["fully_clipped_black_fraction_maximum"]
            <= float(frozen["maximum_fully_clipped_black_fraction"])
            for condition in ("ideal", "degraded")
        ),
        "crop_free_frame_fraction_within_limit": semantic[
            "crop_free_frame_fraction"
        ]
        <= float(frozen["maximum_crop_free_frame_fraction"]),
        "weed_free_frame_fraction_within_limit": semantic[
            "weed_free_frame_fraction"
        ]
        <= float(frozen["maximum_weed_free_frame_fraction"]),
        "mean_crop_fraction_in_range": float(frozen["mean_crop_fraction"][0])
        <= semantic["mean_crop_fraction"]
        <= float(frozen["mean_crop_fraction"][1]),
        "mean_weed_fraction_in_range": float(frozen["mean_weed_fraction"][0])
        <= semantic["mean_weed_fraction"]
        <= float(frozen["mean_weed_fraction"][1]),
        "ideal_degraded_rgb_distinct": pair_receipt["capture_difference"][
            "changed_pixel_fraction_minimum"
        ]
        > 0.0,
        "lossless_native_capture": True,
    }
    detail = {
        "source_and_asset_provenance": {
            "source_template_sha256_exact": True,
            "role_asset_allowlist_exact": used_assets[
                "all_used_and_exposed_assets_allowed"
            ],
            "source_object_assets_observed": used_assets["used_asset_count"] > 0,
            "model_or_prediction_access_absent": True,
        },
        "geometry_and_botanical_gt_integrity": {
            "botanical_quality_gates_passed": all(
                botanical_validation["quality_gates"].values()
            ),
            "persistent_source_tracks_present": botanical_validation["track_count"] > 0,
            "weed_tracks_present": botanical_validation["weed_track_count"] > 0,
            "canonical_gt_shared_between_arms": pair_receipt["arm_gt_identity"][
                "byte_identical"
            ],
        },
        "native_frame_and_pair_integrity": {
            "exact_two_arms": True,
            "exact_30_frames_per_arm": pair_receipt["frame_count_per_arm"] == 30,
            "exact_native_2048_square": pair_receipt["native_dimensions_px"]
            == [2048, 2048],
            "exact_15_hz": pair_receipt["frame_rate_hz"] == 15,
            "all_videos_readable": pair_receipt["quality_gates"][
                "all_videos_readable"
            ],
        },
        "pixel_and_visual_operability": pixel_details,
        "temporal_denominator_contribution": {
            "eligible_weed_track_present": pair_receipt[
                "visible_eligible_weed_track_count"
            ]
            > 0,
            "eligible_track_with_at_least_three_observations": pair_receipt[
                "temporal_audit"
            ]["eligible_track_with_at_least_three_observations"],
            "monotonic_timestamps_and_encoder": True,
        },
        "deterministic_replay_identity": {
            "all_ideal_frames_pixel_exact": capture_validation[
                "deterministic_replay"
            ]["all_frames_pixel_exact"],
            "all_five_seed_bindings_exact": set(
                capture_validation["seed_bindings"]
            )
            == set(roster_row["candidates"][0]["seeds"]),
        },
    }
    gates = {
        name: all(bool(value) for value in values.values())
        for name, values in detail.items()
    }
    result = {
        "pair_quality_gates": gates,
        "gate_details": detail,
        "frozen_pixel_limits": copy.deepcopy(frozen),
        "pixel_audit": copy.deepcopy(pixel),
        "semantic_audit": copy.deepcopy(semantic),
        "deterministic_replay_diagnostic": copy.deepcopy(
            capture_validation["deterministic_replay"]
        ),
        "split_release_gates_deferred": [
            "minimum_crop_model_variants_per_split",
            "minimum_ground_families_per_split",
            "minimum_environment_families_per_split",
            "exact_profile_balance_required",
            "minimum_calibration_eligible_weed_tracks",
            "minimum_locked_test_eligible_weed_tracks",
        ],
        "model_or_outcome_inputs": [],
    }
    if not all(gates.values()):
        failures = [name for name, passed in gates.items() if not passed]
        raise CandidateRejected(
            f"Full candidate non-model gates failed: {failures}", result
        )
    return result


def create_preoutcome_audit_contact_sheet(
    pair_root: Path, frame_indices: Sequence[int]
) -> dict[str, Any]:
    rows: list[Image.Image] = []
    for frame_index in frame_indices:
        images = []
        for condition in ("ideal", "degraded"):
            path = pair_root / condition / "rgb" / f"frame_{frame_index:06d}.png"
            with Image.open(path) as image:
                resized = image.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS)
            images.append(resized)
        row = Image.new("RGB", (1024, 512))
        row.paste(images[0], (0, 0))
        row.paste(images[1], (512, 0))
        rows.append(row)
    sheet = Image.new("RGB", (1024, 512 * len(rows)))
    for index, row in enumerate(rows):
        sheet.paste(row, (0, 512 * index))
    path = pair_root / "preoutcome_audit_contact_sheet.png"
    sheet.save(path, format="PNG", compress_level=6)
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "frame_indices": list(frame_indices),
        "predictions_or_metrics_visible": False,
    }


def full_render_implementation_sha256() -> str:
    functions = (
        derive_full_native_scene_config,
        full_runtime_overlay_patch,
        run_cropcraft_scene,
        validate_botanical_scene,
        validate_full_used_assets,
        validate_full_capture_receipt,
        apply_protocol_degradation,
        build_pair_package,
        evaluate_full_candidate_gates,
        atomic_publish_full_pair,
        render_full_pair,
    )
    return stable_sha256(
        {
            "contract": FULL_RENDER_EXECUTION_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "embedded_cropcraft_module_sha256": hashlib.sha256(
                FULL_AB_MODULE_SOURCE.encode("utf-8")
            ).hexdigest(),
            "embedded_overlay_patch_sha256": hashlib.sha256(
                full_runtime_overlay_patch()
            ).hexdigest(),
        }
    )


def ensure_full_render_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan_validation: Mapping[str, Any],
    patch_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    path = full_paths(config)["synthetic"] / "planning/full_render_execution_lock_v1.json"
    expected = {
        "schema_version": 1,
        "contract": FULL_RENDER_EXECUTION_CONTRACT,
        "status": "SEALED_FULL_RENDER_MODEL_FREE_SYNTHETIC_ONLY",
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan_validation["pair_roster_sha256"],
        "render_implementation_sha256": full_render_implementation_sha256(),
        "composed_scene_patch_sha256": patch_receipt["sha256"],
        "embedded_runtime_overlay_sha256": patch_receipt[
            "ordered_constituents"
        ][-1]["sha256"],
        "model_access_allowed": False,
        "outcome_inputs_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    if path.exists():
        observed = load_json(path)
        if observed != expected:
            raise ContractError("Full render execution lock changed")
    else:
        write_json(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


_HISTORICAL_ENSURE_FULL_RENDER_EXECUTION_LOCK = ensure_full_render_execution_lock


def _dispatch_full_render_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan_validation: Mapping[str, Any],
    patch_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_roster_extension_config(config):
        return _HISTORICAL_ENSURE_FULL_RENDER_EXECUTION_LOCK(
            config_path, config, plan_validation, patch_receipt
        )
    lock = _extension_execution_lock(
        config, "full_render_execution_lock_extension_v1.json"
    )
    if (
        lock.get("render_implementation_sha256")
        != full_render_implementation_sha256()
        or lock.get("execution_lock_dispatch_sha256")
        != stable_sha256(inspect.getsource(_dispatch_full_render_execution_lock))
        or lock.get("composed_scene_patch_sha256") != patch_receipt.get("sha256")
        or lock.get("model_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
    ):
        raise ContractError("Roster extension full-render lock changed")
    return lock


ensure_full_render_execution_lock = _dispatch_full_render_execution_lock


def _append_candidate_rejection(
    ledger_path: Path, row: Mapping[str, Any]
) -> None:
    existing = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    identity = (row["pair_id"], row["candidate_index"])
    if any((item["pair_id"], item["candidate_index"]) == identity for item in existing):
        raise ContractError(f"Candidate rejection already recorded: {identity}")
    write_jsonl(ledger_path, [*existing, dict(row)])


def _resumable_generated_full_staging(
    full_root: Path, pair_id: str, candidate_index: int
) -> Path | None:
    work = full_root / "work"
    prefix = f".partial-{pair_id}-candidate-{candidate_index:02d}-"
    matches = [
        path
        for path in sorted(work.glob(f"{prefix}*"))
        if path.is_dir()
        and not path.is_symlink()
        and (path / "scene_config.yaml").is_file()
        and (path / "bindings/full_ab_scene.patch").is_file()
        and (path / "source_scene/generation_receipt.json").is_file()
        and (path / "source_scene.runner.log").is_file()
        and not (path / "full_pair_receipt.json").exists()
    ] if work.is_dir() else []
    if len(matches) > 1:
        raise ContractError(
            f"Multiple resumable generated full staging roots: {[path.name for path in matches]}"
        )
    return matches[0] if matches else None


def _resumed_generation_summary(
    scene_root: Path, patch_path: Path
) -> dict[str, Any]:
    receipt_path = scene_root / "generation_receipt.json"
    receipt = load_json(receipt_path)
    if receipt.get("scene_patch_sha256") != sha256_file(patch_path):
        raise ContractError("Resumed generation receipt scene patch changed")
    runner_log = scene_root.parent / f"{scene_root.name}.runner.log"
    return {
        "receipt_path": display_path(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "scene_patch_sha256": receipt["scene_patch_sha256"],
        "validated_pairs": int(receipt["validation"]["validated_pairs"]),
        "elapsed_wall_seconds": float(receipt["wall_seconds"]),
        "runner_log": display_path(runner_log),
        "runner_log_sha256": sha256_file(runner_log),
        "resumed_after_completed_cropcraft_generation": True,
    }


def render_full_pair(config_path: Path, pair_id: str) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    paths = full_paths(config)
    full_root = paths["synthetic"]
    roster_row = full_roster_row(config, pair_id)
    destination = full_root / "pairs" / roster_row["protocol_split"] / pair_id
    if destination.exists():
        state = inspect_full_render_state(full_root, full_roster_rows(config))
        if pair_id not in state["completed_pair_ids"]:
            raise ContractError(f"Existing full pair is not resumable: {pair_id}")
        return {
            "status": "SKIP_EXISTING_PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "destination": str(destination),
            "full_pair_receipt_sha256": sha256_file(
                destination / "full_pair_receipt.json"
            ),
            "render_state": state,
            "model_loaded": False,
            "inference_calls": 0,
        }

    full_preflight = preflight(config_path, scope="full")
    capacity = build_full_capacity_receipt(config, full_preflight)
    asset_partition = load_json(
        full_root / "planning/asset_partition_v1.json"
    )
    asset_role = asset_partition["roles"][roster_row["protocol_split"]]
    ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
    rejections = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    rejected_indices = {
        int(row["candidate_index"])
        for row in rejections
        if row["pair_id"] == pair_id
    }
    candidates = [
        candidate
        for candidate in roster_row["candidates"]
        if int(candidate["candidate_index"]) not in rejected_indices
    ]
    if not candidates:
        raise ContractError(f"Full pair candidate attempts exhausted: {pair_id}")
    candidate = candidates[0]
    candidate_index = int(candidate["candidate_index"])
    work = full_root / "work"
    work.mkdir(parents=True, exist_ok=True)
    staging = _resumable_generated_full_staging(
        full_root, pair_id, candidate_index
    )
    resumed_generation = staging is not None
    if staging is None:
        cleanup_interrupted_full_pair_staging(full_root, pair_id)
        staging = work / (
            f".partial-{pair_id}-candidate-{candidate_index:02d}-{uuid.uuid4().hex}"
        )
        staging.mkdir(parents=False, exist_ok=False)
    started = time.perf_counter()
    patch_receipt: dict[str, Any] | None = None
    try:
        source_path = full_candidate_source_path(
            config, roster_row, candidate
        )
        base = load_yaml(source_path)
        expected_derived = derive_full_native_scene_config(
            base, roster_row, candidate, asset_role, config
        )
        derived_path = staging / "scene_config.yaml"
        patch_path = staging / "bindings/full_ab_scene.patch"
        scene_root = staging / "source_scene"
        if resumed_generation:
            derived = load_yaml(derived_path)
            if derived != expected_derived:
                raise ContractError("Resumed full derived scene config changed")
            expected_patch_path = staging / "bindings/resume_expected.patch"
            patch_receipt = compose_scene_patch(
                config,
                expected_patch_path,
                include_full_runtime_overlay=True,
            )
            if sha256_file(patch_path) != patch_receipt["sha256"]:
                raise ContractError("Resumed full composed scene patch changed")
            expected_patch_path.unlink()
            patch_receipt["path"] = display_path(patch_path)
            generation = _resumed_generation_summary(scene_root, patch_path)
        else:
            derived = expected_derived
            derived_path.write_text(
                yaml.safe_dump(derived, sort_keys=False), encoding="utf-8"
            )
            patch_receipt = compose_scene_patch(
                config, patch_path, include_full_runtime_overlay=True
            )
            generation = run_cropcraft_scene(
                derived_path, scene_root, patch_path, config
            )
        botanical_validation = validate_botanical_scene(
            scene_root, config, full_candidate=True
        )
        used_assets = validate_full_used_assets(scene_root, asset_role)
        capture_validation = validate_full_capture_receipt(
            scene_root, roster_row, candidate
        )
        execution_scene = {
            "pair_id": pair_id,
            "split": roster_row["evaluator_split"],
            "source_role": roster_row["v12_source_role"],
            "travel_speed_m_s": float(
                roster_row["factors"]["travel_speed_m_s"]
            ),
            "scene_profile": roster_row["factors"]["v12_scene_profile"],
            "degraded_motion_path": roster_row["factors"][
                "degraded_motion_path"
            ],
            "degraded_pulse_width_us": float(
                roster_row["degraded_capture_parameters"]["pulse_width_us"]
            ),
            "ground_fov_mm": float(
                roster_row["shared_latent_parameters"]["ground_fov_mm"]
            ),
            "full_candidate": True,
            "manifest_pair_prefix": (
                f"pairs/{roster_row['protocol_split']}/{pair_id}"
            ),
        }
        sequences, pair_receipt = build_pair_package(
            scene_root, staging, execution_scene, config, full_root
        )
        candidate_gates = evaluate_full_candidate_gates(
            pair_receipt,
            botanical_validation,
            used_assets,
            capture_validation,
            roster_row,
            config,
        )
        audit_indices = capture_validation["seed_bindings"]["audit_sample_seed"][
            "selected_frame_indices"
        ]
        audit = create_preoutcome_audit_contact_sheet(staging, audit_indices)
        write_json(staging / "sequence_records.json", {"sequences": sequences})
        execution_lock = ensure_full_render_execution_lock(
            config_path, config, plan, patch_receipt
        )
        inventory = artifact_inventory(staging)
        if any("prediction" in row["path"].lower() for row in inventory):
            raise ContractError("Prediction output exists in full pair staging")
        terminal_receipt = {
            "schema_version": 1,
            "contract": FULL_PAIR_RECEIPT_CONTRACT,
            "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "protocol_split": roster_row["protocol_split"],
            "evaluator_split": roster_row["evaluator_split"],
            "pair_slot_identity_sha256": roster_row[
                "pair_slot_identity_sha256"
            ],
            "selected_candidate_index": candidate_index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "candidate_seeds": copy.deepcopy(candidate["seeds"]),
            "source_template": copy.deepcopy(candidate["source_template"]),
            "source_template_path_excluded_from_identity": True,
            "role_asset_validation": used_assets,
            "shared_field_identity_sha256": derived["full_execution_contract"][
                "shared_field_identity_sha256"
            ],
            "canonical_gt_sha256": pair_receipt["canonical_gt_sha256"],
            "pair_quality_gates": candidate_gates["pair_quality_gates"],
            "candidate_gate_evidence": candidate_gates,
            "botanical_validation": botanical_validation,
            "capture_validation": capture_validation,
            "pair_receipt_sha256": sha256_file(staging / "pair_receipt.json"),
            "sequence_records_sha256": sha256_file(
                staging / "sequence_records.json"
            ),
            "preoutcome_audit": audit,
            "generation": generation,
            "composed_patch": patch_receipt,
            "full_render_execution_lock_sha256": execution_lock["sha256"],
            "capacity_check": capacity["projection"],
            "inventory_sha256": stable_sha256(inventory),
            "inventory_file_count_before_terminal_receipt": len(inventory),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "resumed_after_completed_cropcraft_generation": resumed_generation,
            "model_outputs_present_false": True,
            "model_loaded": False,
            "inference_calls": 0,
            "outcome_inputs": [],
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        write_json(staging / "full_pair_receipt.json", terminal_receipt)
        published = atomic_publish_full_pair(
            full_root, staging, destination, roster_row
        )
    except CandidateRejected as error:
        rejection_root = (
            full_root
            / "planning/rejections"
            / pair_id
            / f"candidate_{candidate_index:02d}"
        )
        if rejection_root.exists():
            raise ContractError(
                f"Candidate rejection receipt already exists: {rejection_root}"
            ) from error
        rejection_root.mkdir(parents=True, exist_ok=False)
        write_json(rejection_root / "gate_evidence.json", error.evidence)
        retained: dict[str, Any] = {}
        for source_name, target_name in (
            ("pair_receipt.json", "pair_receipt.json"),
            ("source_scene.runner.log", "cropcraft_runner.log"),
            ("source_scene/full_ab_capture_receipt.json", "capture_receipt.json"),
        ):
            source = staging / source_name
            if source.is_file():
                shutil.copy2(source, rejection_root / target_name)
                retained[target_name] = sha256_file(rejection_root / target_name)
        rejection_receipt = {
            "schema_version": 1,
            "status": "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "candidate_index": candidate_index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "reason_type": type(error).__name__,
            "reason": str(error),
            "gate_evidence_sha256": sha256_file(
                rejection_root / "gate_evidence.json"
            ),
            "retained_receipts_and_log": retained,
            "model_or_outcome_inputs_used": False,
            "bulk_payload_retained": False,
        }
        write_json(rejection_root / "rejection_receipt.json", rejection_receipt)
        rejection = {
            **rejection_receipt,
            "rejection_receipt_sha256": sha256_file(
                rejection_root / "rejection_receipt.json"
            ),
        }
        _append_candidate_rejection(ledger_path, rejection)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    rows = full_roster_rows(config)
    state = inspect_full_render_state(full_root, rows)
    write_json(full_root / "planning/render_state_v1.json", state)
    docs = paths["docs"]
    docs.mkdir(parents=True, exist_ok=True)
    write_json(docs / "render_state_v1.json", state)
    write_json(
        docs / f"{pair_id}_full_pair_receipt.json",
        load_json(destination / "full_pair_receipt.json"),
    )
    return {
        "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": pair_id,
        "selected_candidate_index": candidate_index,
        "destination": str(destination),
        "full_pair_receipt_sha256": published["receipt_sha256"],
        "render_state": state,
        "elapsed_wall_seconds": load_json(
            destination / "full_pair_receipt.json"
        )["elapsed_wall_seconds"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def gt_scout_runtime_overlay_patch() -> bytes:
    modifications = r'''diff --git a/core/blender_entrypoint.py b/core/blender_entrypoint.py
--- a/core/blender_entrypoint.py
+++ b/core/blender_entrypoint.py
@@ -21,2 +21,3 @@
 from core import botanical_gt
 from core import full_ab
+from core import gt_scout
@@ -76,17 +77,18 @@
     for output in cfg.outputs:
         output.export(output_dir, field)

     if cfg.render is not None:
         core.base.setup_camera_animation(cfg.render, beds.get_end_pos())
-        full_ab.render_capture_arms(cfg.render, output_dir)
+        gt_scout.bind_trajectory_only(cfg.render, output_dir)
         beds.apply_label_materials(cfg.render.label_colors)
         if botanical_tracks is not None:
             botanical_gt.apply_semantic_materials(
                 botanical_tracks, cfg.render.label_colors
             )
         ground.apply_label_materials(cfg.render.label_colors)
         core.base.render_animation(cfg.render, labeled=True, output_dir=output_dir)
+        gt_scout.write_runner_proxies(cfg.render, output_dir)
         if botanical_tracks is not None:
             botanical_gt.render_track_ground_truth(
                 botanical_tracks, cfg.render, output_dir
             )
'''
    payload = _new_file_unified_patch("core/gt_scout.py", GT_SCOUT_MODULE_SOURCE)
    payload += modifications
    return payload.encode("utf-8")


def compose_gt_scout_patch(
    config: Mapping[str, Any], destination: Path
) -> dict[str, Any]:
    base = compose_scene_patch(
        config, destination, include_full_runtime_overlay=True
    )
    base_sha256 = base["sha256"]
    overlay = gt_scout_runtime_overlay_patch()
    payload = destination.read_bytes().rstrip(b"\n") + b"\n" + overlay.rstrip(b"\n")
    destination.write_bytes(payload + b"\n")
    constituents = [
        *base["ordered_constituents"],
        {
            "path": "embedded:gt_scout_runtime_overlay_v1",
            "sha256": hashlib.sha256(overlay).hexdigest(),
        },
    ]
    return {
        "path": display_path(destination),
        "sha256": sha256_file(destination),
        "ordered_constituents": constituents,
        "base_full_scene_patch_sha256": base_sha256,
        "full_runtime_overlay_included": True,
        "gt_scout_overlay_included": True,
    }


def gt_scout_decision_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    protocol = _protocol(config)
    pixel = protocol["preoutcome_gates"]["pixel_visual"]
    action = protocol["action_evaluator_binding"]["frozen_semantics"]
    contract = {
        "schema_version": 1,
        "contract": GT_SCOUT_CONTRACT,
        "candidate_order": (
            "lowest_roster_candidate_index_not_present_in_the_canonical_rejection_ledger"
        ),
        "semantic_rejection_predicates": {
            "maximum_crop_free_frame_fraction": float(
                pixel["maximum_crop_free_frame_fraction"]
            ),
            "maximum_weed_free_frame_fraction": float(
                pixel["maximum_weed_free_frame_fraction"]
            ),
            "mean_crop_fraction": [float(value) for value in pixel["mean_crop_fraction"]],
            "mean_weed_fraction": [float(value) for value in pixel["mean_weed_fraction"]],
        },
        "eligibility_rejection_predicates": {
            "class_name": "weed",
            "minimum_canopy_span_mm": float(
                action["eligible_weed_minimum_canopy_span_mm"]
            ),
            "minimum_visible_fraction": float(
                action["eligible_weed_minimum_visible_fraction"]
            ),
            "requires_nonpartial_observation": bool(
                action["eligible_requires_nonpartial_observation"]
            ),
            "minimum_observations_for_temporal_gate": int(
                action["minimum_confirmations"]
            ),
        },
        "permitted_rejection_families": [
            "frozen_semantic_operability",
            "frozen_eligible_weed_temporal_denominator",
        ],
        "unobserved_gates_requiring_unchanged_full_render": [
            "lossless_ideal_and_degraded_rgb",
            "brightness_and_clipping",
            "ideal_degraded_capture_difference",
            "deterministic_ideal_rgb_replay",
            "readable_ideal_degraded_and_side_by_side_videos",
            "manual_calibration_review",
            "split_release_aggregate_gates",
        ],
        "pass_authority": "none_full_render_required",
        "model_or_outcome_inputs_allowed": False,
        "prediction_access_allowed": False,
        "registered_target_access_allowed": False,
        "synthetic_only": True,
    }
    contract["contract_sha256"] = stable_sha256(contract)
    return contract


def _gt_scout_instance_ids(
    instance_rgb: np.ndarray, source_tracks: Sequence[Mapping[str, Any]]
) -> np.ndarray:
    """Decode the frozen palette without a full-raster axis-wise sort."""
    output = np.zeros(instance_rgb.shape[:2], dtype=np.uint16)
    for track in source_tracks:
        colour = np.asarray(track["render_color_rgb"], dtype=np.uint8)
        selected = np.all(instance_rgb == colour, axis=2)
        output[selected] = int(track["render_id"])
    nonblack = np.any(instance_rgb != 0, axis=2)
    if bool(np.any(np.logical_and(nonblack, output == 0))):
        raise ContractError("GT scout instance palette contains undeclared colours")
    return output


def audit_gt_scout_scene(
    scene_root: Path,
    destination: Path,
    roster_row: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    native = config["native_contract"]
    frame_count = int(native["frames_per_arm"])
    width = int(native["width_px"])
    height = int(native["height_px"])
    split = str(roster_row["evaluator_split"])
    pair_id = str(roster_row["pair_id"])
    gt_source = scene_root / "botanical_ground_truth"
    source_path = gt_source / "source_objects.json"
    registry_path = gt_source / "track_registry.json"
    tracks_path = gt_source / "tracks.jsonl"
    source_registry = load_json(source_path)
    source_tracks = source_registry["tracks"]
    if not source_tracks:
        raise ContractError("GT scout source-object registry is empty")
    track_by_render = {int(row["render_id"]): row for row in source_tracks}
    if len(track_by_render) != len(source_tracks):
        raise ContractError("GT scout source render IDs are not unique")
    track_rows = read_jsonl(tracks_path)
    if len(track_rows) != frame_count * len(source_tracks):
        raise ContractError("GT scout track table denominator changed")
    track_row_by_frame_id = {
        (str(row["frame_id"]), str(row["track_id"])): row for row in track_rows
    }
    if len(track_row_by_frame_id) != len(track_rows):
        raise ContractError("GT scout track table keys are not unique")

    decision_contract = gt_scout_decision_contract(config)
    eligibility = decision_contract["eligibility_rejection_predicates"]
    canonical_root = destination / "canonical_gt"
    semantic_root = canonical_root / "semantic"
    track_root = canonical_root / "tracks"
    semantic_root.mkdir(parents=True, exist_ok=False)
    track_root.mkdir(parents=True, exist_ok=False)
    crop_fractions: list[float] = []
    weed_fractions: list[float] = []
    eligible_tracks: set[str] = set()
    eligible_observations: dict[str, int] = defaultdict(int)
    gt_identity_rows: list[dict[str, Any]] = []

    for frame_index in range(frame_count):
        source_stem = f"frame_{frame_index + 1:04d}"
        output_stem = f"frame_{frame_index:06d}"
        semantic_rgb_path = scene_root / "render/masks" / f"{source_stem}.png"
        instance_rgb_path = gt_source / "instance_masks" / f"{source_stem}.png"
        if not semantic_rgb_path.is_file() or not instance_rgb_path.is_file():
            raise ContractError(f"GT scout native frame is incomplete: {source_stem}")
        semantic_rgb = np.asarray(
            Image.open(semantic_rgb_path).convert("RGB"), dtype=np.uint8
        )
        instance_rgb = np.asarray(
            Image.open(instance_rgb_path).convert("RGB"), dtype=np.uint8
        )
        if semantic_rgb.shape != (height, width, 3) or instance_rgb.shape != (
            height,
            width,
            3,
        ):
            raise ContractError("GT scout native GT raster geometry changed")
        semantic = _semantic_ids(semantic_rgb)
        track_mask = _gt_scout_instance_ids(instance_rgb, source_tracks)
        crop_fractions.append(float((semantic == 1).mean()))
        weed_fractions.append(float((semantic == 2).mean()))

        semantic_path = semantic_root / f"{output_stem}.png"
        track_path = track_root / f"{output_stem}.png"
        Image.fromarray(semantic, mode="L").save(
            semantic_path, format="PNG", compress_level=9
        )
        if not cv2.imwrite(str(track_path), track_mask):
            raise ContractError(f"GT scout failed to write uint16 track mask: {track_path}")

        labels: list[dict[str, Any]] = []
        visible_ids = sorted(int(value) for value in np.unique(track_mask) if int(value))
        for render_id in visible_ids:
            source_track = track_by_render[render_id]
            track_id = str(source_track["track_id"])
            key = (source_stem, track_id)
            if key not in track_row_by_frame_id:
                raise ContractError(f"GT scout track row is missing: {key}")
            table = track_row_by_frame_id[key]
            selected = track_mask == render_id
            semantic_values = set(int(value) for value in np.unique(semantic[selected]))
            expected_semantic = 1 if source_track["class_name"] == "crop" else 2
            if semantic_values != {expected_semantic}:
                raise ContractError(
                    f"GT scout botanical class/semantic mismatch: {pair_id}:{track_id}:{frame_index}"
                )
            visible_fraction = table.get("visible_fraction")
            if visible_fraction is None:
                raise ContractError("Visible GT scout instance has no visible fraction")
            partial = bool(table["partial_at_frame_boundary"]) or _partial_in_action_region(
                selected, int(native["outer_abstain_ring_px"])
            )
            label = {
                "mask_id": render_id,
                "track_id": f"{split}:{pair_id}:{track_id}",
                "class_name": str(source_track["class_name"]),
                "canopy_span_mm": float(source_track["canopy_span_mm"]),
                "visible_fraction": float(visible_fraction),
                "partial": partial,
                "size_stratum": _size_stratum(float(source_track["canopy_span_mm"])),
            }
            labels.append(label)
            if (
                label["class_name"] == eligibility["class_name"]
                and label["canopy_span_mm"] >= eligibility["minimum_canopy_span_mm"]
                and label["visible_fraction"] >= eligibility["minimum_visible_fraction"]
                and not label["partial"]
            ):
                eligible_tracks.add(label["track_id"])
                eligible_observations[label["track_id"]] += 1
        if not labels:
            raise ContractError(f"GT scout frame has no visible botanical tracks: {frame_index}")
        gt_identity_rows.append(
            {
                "frame_index": frame_index,
                "semantic_sha256": sha256_file(semantic_path),
                "track_sha256": sha256_file(track_path),
                "tracks": labels,
            }
        )

    semantic_audit = {
        "mean_crop_fraction": float(np.mean(crop_fractions)),
        "mean_weed_fraction": float(np.mean(weed_fractions)),
        "crop_free_frame_fraction": float(
            np.mean(np.asarray(crop_fractions) == 0.0)
        ),
        "weed_free_frame_fraction": float(
            np.mean(np.asarray(weed_fractions) == 0.0)
        ),
    }
    temporal_audit = {
        "eligible_track_observation_counts": dict(
            sorted(eligible_observations.items())
        ),
        "eligible_track_with_at_least_three_observations": any(
            count >= eligibility["minimum_observations_for_temporal_gate"]
            for count in eligible_observations.values()
        ),
    }
    return {
        "schema_version": 1,
        "contract": GT_SCOUT_CONTRACT,
        "pair_id": pair_id,
        "protocol_split": roster_row["protocol_split"],
        "evaluator_split": split,
        "frame_count": frame_count,
        "native_dimensions_px": [width, height],
        "source_scene_graph_identity_sha256": source_registry[
            "source_scene_graph_identity_sha256"
        ],
        "source_track_count": len(source_tracks),
        "source_gt_file_sha256": {
            "source_objects.json": sha256_file(source_path),
            "track_registry.json": sha256_file(registry_path),
            "tracks.jsonl": sha256_file(tracks_path),
        },
        "visible_eligible_weed_track_count": len(eligible_tracks),
        "semantic_audit": semantic_audit,
        "temporal_audit": temporal_audit,
        "canonical_gt_sha256": stable_sha256(gt_identity_rows),
        "canonical_frame_rows": gt_identity_rows,
        "identity_inputs": [
            "pre_render_source_objects",
            "native_semantic_masks",
            "native_instance_masks",
            "source_track_visibility_table",
        ],
        "forbidden_identity_or_decision_inputs_absent": [
            "model_predictions",
            "confidence_scores",
            "segmentation_tracking_or_action_metrics",
            "registered_descriptive_targets",
        ],
    }


def evaluate_gt_scout_decision(
    audit: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    contract = gt_scout_decision_contract(config)
    limits = contract["semantic_rejection_predicates"]
    semantic = audit["semantic_audit"]
    semantic_checks = {
        "crop_free_frame_fraction_within_limit": semantic[
            "crop_free_frame_fraction"
        ]
        <= limits["maximum_crop_free_frame_fraction"],
        "weed_free_frame_fraction_within_limit": semantic[
            "weed_free_frame_fraction"
        ]
        <= limits["maximum_weed_free_frame_fraction"],
        "mean_crop_fraction_in_range": limits["mean_crop_fraction"][0]
        <= semantic["mean_crop_fraction"]
        <= limits["mean_crop_fraction"][1],
        "mean_weed_fraction_in_range": limits["mean_weed_fraction"][0]
        <= semantic["mean_weed_fraction"]
        <= limits["mean_weed_fraction"][1],
    }
    temporal_checks = {
        "eligible_weed_track_present": audit["visible_eligible_weed_track_count"] > 0,
        "eligible_track_with_at_least_three_observations": audit[
            "temporal_audit"
        ]["eligible_track_with_at_least_three_observations"],
    }
    failures = [
        f"semantic:{name}"
        for name, passed in semantic_checks.items()
        if not passed
    ] + [
        f"eligibility:{name}"
        for name, passed in temporal_checks.items()
        if not passed
    ]
    rejected = bool(failures)
    return {
        "schema_version": 1,
        "contract": GT_SCOUT_CONTRACT,
        "status": (
            "REJECT_FROZEN_GT_ONLY_PREOUTCOME_SYNTHETIC_ONLY"
            if rejected
            else "PASS_GT_ONLY_FULL_RENDER_REQUIRED_SYNTHETIC_ONLY"
        ),
        "pair_id": audit["pair_id"],
        "rejectable_by_scout": rejected,
        "semantic_checks": semantic_checks,
        "eligibility_checks": temporal_checks,
        "rejection_reasons": failures,
        "decision_contract_sha256": contract["contract_sha256"],
        "full_render_still_required_for_acceptance": True,
        "model_or_outcome_inputs_used": False,
        "registered_targets_used": False,
        "synthetic_only": True,
    }


def _validate_sealed_full_render_lock(config: Mapping[str, Any]) -> dict[str, Any]:
    if full_render_implementation_sha256() != SEALED_FULL_RENDER_IMPLEMENTATION_SHA256:
        raise ContractError("Sealed full-render implementation changed before GT scout")
    path = full_paths(config)["synthetic"] / "planning/full_render_execution_lock_v1.json"
    if not path.is_file() or sha256_file(path) != SEALED_FULL_RENDER_EXECUTION_LOCK_SHA256:
        raise ContractError("Sealed full-render execution-lock bytes changed before GT scout")
    value = load_json(path)
    if (
        value.get("render_implementation_sha256")
        != SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
        or value.get("status") != "SEALED_FULL_RENDER_MODEL_FREE_SYNTHETIC_ONLY"
        or value.get("model_access_allowed") is not False
        or value.get("outcome_inputs_allowed") is not False
    ):
        raise ContractError("Sealed full-render execution-lock semantics changed")
    return {"path": display_path(path), "sha256": sha256_file(path), **value}


def _gt_scout_reference_equivalence(
    audit: Mapping[str, Any],
    used_assets: Mapping[str, Any],
    destination: Path,
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    reference_root = (
        full_paths(config)["synthetic"]
        / "pairs"
        / str(roster_row["protocol_split"])
        / str(roster_row["pair_id"])
    )
    full_receipt_path = reference_root / "full_pair_receipt.json"
    pair_receipt_path = reference_root / "pair_receipt.json"
    sequence_path = reference_root / "sequence_records.json"
    if not all(path.is_file() for path in (full_receipt_path, pair_receipt_path, sequence_path)):
        raise ContractError("Published reference pair is incomplete for GT scout equivalence")
    full_receipt = load_json(full_receipt_path)
    pair_receipt = load_json(pair_receipt_path)
    sequences = load_json(sequence_path)["sequences"]
    ideal = [row for row in sequences if row["condition"] == "ideal"]
    if len(ideal) != 1:
        raise ContractError("Published reference pair has ambiguous ideal GT rows")
    reference_rows = []
    for frame in ideal[0]["frames"]:
        frame_index = int(frame["frame_index"])
        reference_rows.append(
            {
                "frame_index": frame_index,
                "semantic_sha256": sha256_file(
                    reference_root
                    / "shared_gt/semantic"
                    / f"frame_{frame_index:06d}.png"
                ),
                "track_sha256": sha256_file(
                    reference_root
                    / "shared_gt/tracks"
                    / f"frame_{frame_index:06d}.png"
                ),
                "tracks": frame["tracks"],
            }
        )
    reference_scene = reference_root / "source_scene/botanical_ground_truth"
    reference_source_hashes = {
        name: sha256_file(reference_scene / name)
        for name in ("source_objects.json", "track_registry.json", "tracks.jsonl")
    }
    checks = {
        "selected_candidate_index_exact": full_receipt["selected_candidate_index"]
        == int(candidate["candidate_index"]),
        "candidate_identity_exact": full_receipt["candidate_identity_sha256"]
        == candidate["candidate_identity_sha256"],
        "canonical_gt_digest_exact": pair_receipt["canonical_gt_sha256"]
        == audit["canonical_gt_sha256"],
        "all_30_semantic_track_hashes_and_labels_exact": reference_rows
        == audit["canonical_frame_rows"],
        "semantic_audit_exact": pair_receipt["semantic_audit"]
        == audit["semantic_audit"],
        "temporal_audit_exact": pair_receipt["temporal_audit"]
        == audit["temporal_audit"],
        "eligible_track_count_exact": pair_receipt[
            "visible_eligible_weed_track_count"
        ]
        == audit["visible_eligible_weed_track_count"],
        "source_scene_graph_identity_exact": pair_receipt[
            "source_scene_graph_identity_sha256"
        ]
        == audit["source_scene_graph_identity_sha256"],
        "source_gt_receipt_bytes_exact": reference_source_hashes
        == audit["source_gt_file_sha256"],
        "role_asset_allowlist_decision_exact": full_receipt[
            "role_asset_validation"
        ]
        == used_assets,
    }
    receipt = {
        "schema_version": 1,
        "status": "PASS_GT_SCOUT_REFERENCE_EQUIVALENCE_SYNTHETIC_ONLY",
        "pair_id": roster_row["pair_id"],
        "candidate_index": int(candidate["candidate_index"]),
        "checks": checks,
        "reference_full_pair_receipt_sha256": sha256_file(full_receipt_path),
        "reference_pair_receipt_sha256": sha256_file(pair_receipt_path),
        "reference_canonical_gt_sha256": pair_receipt["canonical_gt_sha256"],
        "compared_native_frame_count": len(reference_rows),
        "model_or_outcome_inputs_used": False,
    }
    if not all(checks.values()) or len(reference_rows) != 30:
        raise ContractError(f"GT scout did not reproduce published canonical GT: {checks}")
    write_json(destination / "reference_equivalence_receipt.json", receipt)
    return receipt


def gt_scout_implementation_sha256() -> str:
    functions = (
        gt_scout_runtime_overlay_patch,
        compose_gt_scout_patch,
        gt_scout_decision_contract,
        _gt_scout_instance_ids,
        audit_gt_scout_scene,
        evaluate_gt_scout_decision,
        _validate_sealed_full_render_lock,
        _gt_scout_reference_equivalence,
        run_gt_scout_candidate,
    )
    return stable_sha256(
        {
            "contract": GT_SCOUT_EXECUTION_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "embedded_cropcraft_module_sha256": hashlib.sha256(
                GT_SCOUT_MODULE_SOURCE.encode("utf-8")
            ).hexdigest(),
            "embedded_overlay_patch_sha256": hashlib.sha256(
                gt_scout_runtime_overlay_patch()
            ).hexdigest(),
            "sealed_full_render_implementation_sha256": (
                SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
            ),
        }
    )


def ensure_gt_scout_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
    patch_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    sealed = _validate_sealed_full_render_lock(config)
    if patch_receipt["base_full_scene_patch_sha256"] != sealed[
        "composed_scene_patch_sha256"
    ]:
        raise ContractError("GT scout base patch differs from the sealed full renderer")
    contract = gt_scout_decision_contract(config)
    expected = {
        "schema_version": 1,
        "contract": GT_SCOUT_EXECUTION_CONTRACT,
        "status": "SEALED_GT_ONLY_SCOUT_MODEL_FREE_SYNTHETIC_ONLY",
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan["pair_roster_sha256"],
        "sealed_full_render_execution_lock_sha256": sealed["sha256"],
        "sealed_full_render_implementation_sha256": sealed[
            "render_implementation_sha256"
        ],
        "base_full_scene_patch_sha256": patch_receipt[
            "base_full_scene_patch_sha256"
        ],
        "composed_gt_scout_patch_sha256": patch_receipt["sha256"],
        "gt_scout_overlay_sha256": patch_receipt["ordered_constituents"][-1][
            "sha256"
        ],
        "gt_scout_implementation_sha256": gt_scout_implementation_sha256(),
        "decision_contract": contract,
        "rejection_authority": "frozen_semantic_and_eligibility_failures_only",
        "acceptance_authority": "none_unchanged_full_renderer_required",
        "model_access_allowed": False,
        "outcome_inputs_allowed": False,
        "registered_targets_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    path = full_paths(config)["synthetic"] / "planning/gt_scout_execution_lock_v1.json"
    if path.exists():
        if load_json(path) != expected:
            raise ContractError("GT scout execution lock changed")
    else:
        write_json(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


_HISTORICAL_ENSURE_GT_SCOUT_EXECUTION_LOCK = ensure_gt_scout_execution_lock


def _dispatch_gt_scout_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
    patch_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_roster_extension_config(config):
        return _HISTORICAL_ENSURE_GT_SCOUT_EXECUTION_LOCK(
            config_path, config, plan, patch_receipt
        )
    sealed = _validate_sealed_full_render_lock(config)
    if patch_receipt["base_full_scene_patch_sha256"] != sealed[
        "composed_scene_patch_sha256"
    ]:
        raise ContractError("GT scout base patch differs from the sealed full renderer")
    lock = _extension_execution_lock(
        config, "gt_scout_execution_lock_extension_v1.json"
    )
    if (
        lock.get("gt_scout_implementation_sha256")
        != gt_scout_implementation_sha256()
        or lock.get("execution_lock_dispatch_sha256")
        != stable_sha256(inspect.getsource(_dispatch_gt_scout_execution_lock))
        or lock.get("composed_gt_scout_patch_sha256")
        != patch_receipt.get("sha256")
        or lock.get("historical_full_render_execution_lock_sha256")
        != sealed["sha256"]
        or lock.get("model_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
        or lock.get("registered_targets_allowed") is not False
    ):
        raise ContractError("Roster extension GT-scout lock changed")
    return lock


ensure_gt_scout_execution_lock = _dispatch_gt_scout_execution_lock


def _next_gt_scout_candidate(
    full_root: Path, roster_row: Mapping[str, Any]
) -> Mapping[str, Any]:
    ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
    rejections = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    rejected: set[int] = set()
    candidates = roster_row["candidates"]
    for row in rejections:
        if row["pair_id"] != roster_row["pair_id"]:
            continue
        index = int(row["candidate_index"])
        if index < 0 or index >= len(candidates):
            raise ContractError("Canonical rejection ledger candidate index escaped roster")
        if row["candidate_identity_sha256"] != candidates[index][
            "candidate_identity_sha256"
        ]:
            raise ContractError("Canonical rejection ledger candidate identity changed")
        rejected.add(index)
    remaining = [
        candidate
        for candidate in candidates
        if int(candidate["candidate_index"]) not in rejected
    ]
    if not remaining:
        raise ContractError(
            f"GT scout candidate attempts exhausted: {roster_row['pair_id']}"
        )
    return remaining[0]


def _validate_gt_scout_capture_receipt(
    scene_root: Path,
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    path = scene_root / "gt_scout_capture_receipt.json"
    receipt = load_json(path)
    bindings = receipt.get("seed_bindings", {})
    valid = (
        receipt.get("contract") == GT_SCOUT_CONTRACT
        and receipt.get("pair_id") == roster_row["pair_id"]
        and receipt.get("candidate_identity_sha256")
        == candidate["candidate_identity_sha256"]
        and receipt.get("frame_count") == 30
        and receipt.get("native_dimensions_px") == [2048, 2048]
        and set(bindings) == set(candidate["seeds"])
        and all(
            int(bindings[name]["value"]) == int(value)
            for name, value in candidate["seeds"].items()
        )
        and receipt.get("rgb_capture_rendered") is False
        and receipt.get("ideal_or_degraded_arm_rendered") is False
        and receipt.get("runner_jpeg_proxies_are_semantic_validation_only") is True
        and receipt.get("model_access") is False
        and receipt.get("prediction_access") is False
    )
    if not valid:
        raise ContractError("GT scout CropCraft receipt changed")
    return receipt


def _commit_gt_scout_rejection(
    full_root: Path,
    destination: Path,
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    if decision.get("rejectable_by_scout") is not True:
        raise ContractError("GT scout may never append a passing candidate rejection")
    ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
    existing = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    identity = (roster_row["pair_id"], int(candidate["candidate_index"]))
    matches = [
        row
        for row in existing
        if (row["pair_id"], int(row["candidate_index"])) == identity
    ]
    if matches:
        if len(matches) != 1 or matches[0]["candidate_identity_sha256"] != candidate[
            "candidate_identity_sha256"
        ]:
            raise ContractError("Existing GT scout ledger binding is ambiguous")
        appended = False
    else:
        terminal_path = destination / "gt_scout_terminal_receipt.json"
        if not terminal_path.is_file():
            recovery_terminal = destination / "recovery_terminal_receipt.json"
            recovery_decision = (
                decision.get("contract")
                == GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
                and decision.get("rejection_reasons")
                == ["eligibility:source_weed_track_present"]
            )
            if not recovery_decision or not recovery_terminal.is_file():
                raise ContractError("GT scout rejection terminal receipt is missing")
            terminal_path = recovery_terminal
        row = {
            "schema_version": 1,
            "status": "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": roster_row["pair_id"],
            "candidate_index": int(candidate["candidate_index"]),
            "candidate_identity_sha256": candidate["candidate_identity_sha256"],
            "reason_type": "GtScoutCandidateRejected",
            "reason": "; ".join(decision["rejection_reasons"]),
            "gt_scout_terminal_receipt_sha256": sha256_file(terminal_path),
            "gt_scout_decision_receipt_sha256": sha256_file(
                destination / "decision_receipt.json"
            ),
            "rejection_families": [
                "frozen_semantic_operability",
                "frozen_eligible_weed_temporal_denominator",
            ],
            "model_or_outcome_inputs_used": False,
            "bulk_payload_retained": False,
        }
        _append_candidate_rejection(ledger_path, row)
        appended = True
    receipt = {
        "schema_version": 1,
        "pair_id": roster_row["pair_id"],
        "candidate_index": int(candidate["candidate_index"]),
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "canonical_rejection_ledger_sha256": sha256_file(ledger_path),
        "appended_by_this_call": appended,
        "idempotent": True,
        "model_or_outcome_inputs_used": False,
    }
    commit_path = destination / "ledger_commit_receipt.json"
    if commit_path.exists():
        observed = load_json(commit_path)
        if (
            observed["pair_id"] != receipt["pair_id"]
            or observed["candidate_index"] != receipt["candidate_index"]
            or observed["candidate_identity_sha256"]
            != receipt["candidate_identity_sha256"]
        ):
            raise ContractError("GT scout ledger commit receipt changed")
    else:
        write_json(commit_path, receipt)
    return receipt


def run_gt_scout_candidate(
    config_path: Path,
    pair_id: str,
    *,
    candidate_index: int | None = None,
    dry_run: bool = False,
    reference_published_pair: bool = False,
) -> dict[str, Any]:
    if dry_run and reference_published_pair:
        raise ContractError("GT scout dry-run and reference modes are mutually exclusive")
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    preflight_receipt = preflight(config_path, scope="fixture")
    paths = full_paths(config)
    full_root = paths["synthetic"]
    roster_row = full_roster_row(config, pair_id)
    published_pair = (
        full_root / "pairs" / str(roster_row["protocol_split"]) / pair_id
    )
    if published_pair.exists() and not reference_published_pair:
        raise ContractError("GT scout cannot select against an already published pair")
    if reference_published_pair and not published_pair.is_dir():
        raise ContractError("GT scout reference mode requires a published full pair")
    next_candidate = _next_gt_scout_candidate(full_root, roster_row)
    if candidate_index is None:
        candidate = next_candidate
    else:
        if int(candidate_index) != int(next_candidate["candidate_index"]):
            raise ContractError(
                "GT scout explicit candidate is not the next canonical roster candidate"
            )
        candidate = roster_row["candidates"][int(candidate_index)]
    if reference_published_pair:
        published_receipt = load_json(published_pair / "full_pair_receipt.json")
        if int(published_receipt["selected_candidate_index"]) != int(
            candidate["candidate_index"]
        ):
            raise ContractError("GT scout reference candidate differs from published selection")

    purpose = (
        "reference_equivalence"
        if reference_published_pair
        else "dry_run"
        if dry_run
        else "roster"
    )
    scout_root = full_root / "planning/gt_scout_v1"
    destination = (
        scout_root
        / purpose
        / pair_id
        / f"candidate_{int(candidate['candidate_index']):02d}"
    )
    if destination.exists():
        terminal = load_json(destination / "gt_scout_terminal_receipt.json")
        decision = load_json(destination / "decision_receipt.json")
        if (
            terminal.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or terminal.get("gt_scout_implementation_sha256")
            != gt_scout_implementation_sha256()
        ):
            raise ContractError("Existing GT scout result binding changed")
        commit = None
        if not dry_run and not reference_published_pair and decision[
            "rejectable_by_scout"
        ]:
            commit = _commit_gt_scout_rejection(
                full_root, destination, roster_row, candidate, decision
            )
        return {
            "status": f"SKIP_EXISTING_{decision['status']}",
            "pair_id": pair_id,
            "candidate_index": int(candidate["candidate_index"]),
            "destination": str(destination),
            "gt_scout_terminal_receipt_sha256": sha256_file(
                destination / "gt_scout_terminal_receipt.json"
            ),
            "ledger_commit": commit,
            "model_loaded": False,
            "inference_calls": 0,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = scout_root / (
        f".partial-{purpose}-{pair_id}-candidate-"
        f"{int(candidate['candidate_index']):02d}-{uuid.uuid4().hex}"
    )
    _require_child(staging, scout_root, "GT scout staging")
    staging.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        asset_partition = load_json(full_root / "planning/asset_partition_v1.json")
        asset_role = asset_partition["roles"][roster_row["protocol_split"]]
        source_path = full_candidate_source_path(config, roster_row, candidate)
        derived = derive_full_native_scene_config(
            load_yaml(source_path), roster_row, candidate, asset_role, config
        )
        derived_path = staging / "scene_config.yaml"
        derived_path.write_text(
            yaml.safe_dump(derived, sort_keys=False), encoding="utf-8"
        )
        patch_path = staging / "bindings/gt_scout_scene.patch"
        patch_receipt = compose_gt_scout_patch(config, patch_path)
        scout_lock = ensure_gt_scout_execution_lock(
            config_path, config, plan, patch_receipt
        )
        scene_root = staging / "source_scene"
        generation = run_cropcraft_scene(
            derived_path, scene_root, patch_path, config
        )
        capture = _validate_gt_scout_capture_receipt(
            scene_root, roster_row, candidate
        )
        botanical_validation = validate_botanical_scene(
            scene_root, config, full_candidate=True
        )
        used_assets = validate_full_used_assets(scene_root, asset_role)
        audit = audit_gt_scout_scene(scene_root, staging, roster_row, config)
        decision = evaluate_gt_scout_decision(audit, config)
        write_json(staging / "gt_audit_receipt.json", audit)
        write_json(staging / "decision_receipt.json", decision)
        equivalence = None
        if reference_published_pair:
            equivalence = _gt_scout_reference_equivalence(
                audit,
                used_assets,
                staging,
                roster_row,
                candidate,
                config,
            )

        evidence_root = staging / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=False)
        retained: dict[str, str] = {}
        for source, name in (
            (scene_root / "generation_receipt.json", "generation_receipt.json"),
            (scene_root / "gt_scout_capture_receipt.json", "capture_receipt.json"),
            (
                scene_root / "botanical_ground_truth/source_objects.json",
                "source_objects.json",
            ),
            (
                scene_root / "botanical_ground_truth/track_registry.json",
                "track_registry.json",
            ),
            (
                scene_root / "botanical_ground_truth/tracks.jsonl",
                "tracks.jsonl",
            ),
            (staging / "source_scene.runner.log", "cropcraft_runner.log"),
        ):
            if not source.is_file():
                raise ContractError(f"GT scout retained evidence is missing: {source}")
            target = evidence_root / name
            shutil.copy2(source, target)
            retained[name] = sha256_file(target)
        bulk_bytes_before_cleanup = _tree_bytes(scene_root) + _tree_bytes(
            staging / "canonical_gt"
        )
        shutil.rmtree(scene_root)
        shutil.rmtree(staging / "canonical_gt")
        (staging / "source_scene.runner.log").unlink()
        cleanup = {
            "bulk_bytes_removed": bulk_bytes_before_cleanup,
            "source_scene_removed": True,
            "canonical_mask_payload_removed": True,
            "retained_receipts_and_log": retained,
            "bulk_payload_retained": False,
            "bounded_to_gt_scout_staging": True,
        }
        write_json(staging / "bounded_cleanup_receipt.json", cleanup)
        inventory = artifact_inventory(staging)
        if any("prediction" in row["path"].lower() for row in inventory):
            raise ContractError("Prediction output exists in GT scout staging")
        terminal = {
            "schema_version": 1,
            "contract": GT_SCOUT_EXECUTION_CONTRACT,
            "status": decision["status"],
            "pair_id": pair_id,
            "protocol_split": roster_row["protocol_split"],
            "pair_slot_identity_sha256": roster_row["pair_slot_identity_sha256"],
            "candidate_index": int(candidate["candidate_index"]),
            "candidate_identity_sha256": candidate["candidate_identity_sha256"],
            "candidate_seeds": copy.deepcopy(candidate["seeds"]),
            "all_five_seed_bindings_exact": set(capture["seed_bindings"])
            == set(candidate["seeds"]),
            "source_template": copy.deepcopy(candidate["source_template"]),
            "source_template_sha256_exact": sha256_file(source_path)
            == candidate["source_template"]["sha256"],
            "role_asset_validation": used_assets,
            "botanical_validation": botanical_validation,
            "canonical_gt_sha256": audit["canonical_gt_sha256"],
            "decision": decision,
            "reference_equivalence": equivalence,
            "dry_run": dry_run,
            "reference_published_pair": reference_published_pair,
            "canonical_rejection_ledger_mutated_before_atomic_publish": False,
            "full_render_still_required_for_acceptance": True,
            "generation": generation,
            "composed_patch": patch_receipt,
            "gt_scout_execution_lock_sha256": scout_lock["sha256"],
            "gt_scout_implementation_sha256": scout_lock[
                "gt_scout_implementation_sha256"
            ],
            "sealed_full_render_execution_lock_sha256": scout_lock[
                "sealed_full_render_execution_lock_sha256"
            ],
            "sealed_full_render_implementation_sha256": scout_lock[
                "sealed_full_render_implementation_sha256"
            ],
            "preflight": {
                "scope": preflight_receipt["scope"],
                "capacity": preflight_receipt["capacity"],
                "gpu": preflight_receipt["gpu"],
                "checkpoint_hash_verified_as_source_lock": True,
                "checkpoint_loaded": False,
            },
            "bounded_cleanup": cleanup,
            "inventory_sha256": stable_sha256(inventory),
            "inventory_file_count_before_terminal_receipt": len(inventory),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "model_loaded": False,
            "inference_calls": 0,
            "outcome_inputs": [],
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        write_json(staging / "gt_scout_terminal_receipt.json", terminal)
        staging.replace(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    commit = None
    if not dry_run and not reference_published_pair and decision[
        "rejectable_by_scout"
    ]:
        commit = _commit_gt_scout_rejection(
            full_root, destination, roster_row, candidate, decision
        )
    docs_root = paths["docs"] / "gt_scout_v1"
    docs_root.mkdir(parents=True, exist_ok=True)
    write_json(
        docs_root / f"{purpose}_{pair_id}_candidate_{int(candidate['candidate_index']):02d}.json",
        load_json(destination / "gt_scout_terminal_receipt.json"),
    )
    return {
        "status": decision["status"],
        "pair_id": pair_id,
        "candidate_index": int(candidate["candidate_index"]),
        "destination": str(destination),
        "canonical_gt_sha256": audit["canonical_gt_sha256"],
        "rejection_reasons": decision["rejection_reasons"],
        "reference_equivalence_passed": bool(
            equivalence and all(equivalence["checks"].values())
        ),
        "ledger_commit": commit,
        "gt_scout_terminal_receipt_sha256": sha256_file(
            destination / "gt_scout_terminal_receipt.json"
        ),
        "elapsed_wall_seconds": load_json(
            destination / "gt_scout_terminal_receipt.json"
        )["elapsed_wall_seconds"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def _audit_zero_source_weed_failure(
    scene_root: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Admit only the exact source-cardinality failure blocked by the legacy validator."""
    native = config["native_contract"]
    frame_count = int(native["frames_per_arm"])
    expected_size = (int(native["width_px"]), int(native["height_px"]))
    gt_root = scene_root / "botanical_ground_truth"
    source_path = gt_root / "source_objects.json"
    registry_path = gt_root / "track_registry.json"
    tracks_path = gt_root / "tracks.jsonl"
    if not all(path.is_file() for path in (source_path, registry_path, tracks_path)):
        raise ContractError("Source-cardinality recovery evidence is incomplete")

    source = load_json(source_path)
    source_tracks = source.get("tracks")
    if not isinstance(source_tracks, list) or not source_tracks:
        raise ContractError("Source-cardinality recovery has no source tracks")
    track_ids = [str(row["track_id"]) for row in source_tracks]
    render_ids = [int(row["render_id"]) for row in source_tracks]
    if len(set(track_ids)) != len(track_ids) or len(set(render_ids)) != len(
        render_ids
    ):
        raise ContractError("Source-cardinality recovery track identity is ambiguous")
    crop_count = sum(row.get("class_name") == "crop" for row in source_tracks)
    weed_count = sum(row.get("class_name") == "weed" for row in source_tracks)
    if crop_count < 1 or weed_count != 0:
        raise ContractError(
            "Source-cardinality recovery is restricted to crop-present, zero-weed scenes"
        )

    instance_paths = sorted((gt_root / "instance_masks").glob("frame_*.png"))
    semantic_paths = sorted((scene_root / "render/masks").glob("frame_*.png"))
    if len(instance_paths) != frame_count or len(semantic_paths) != frame_count:
        raise ContractError("Source-cardinality recovery native frame count changed")
    for path in (instance_paths[0], instance_paths[-1], semantic_paths[0], semantic_paths[-1]):
        with Image.open(path) as image:
            if image.size != expected_size:
                raise ContractError(
                    "Source-cardinality recovery native raster geometry changed"
                )

    rows = read_jsonl(tracks_path)
    expected_grid = {
        (f"frame_{frame_index + 1:04d}", track_id)
        for frame_index in range(frame_count)
        for track_id in track_ids
    }
    observed_grid = {
        (str(row["frame_id"]), str(row["track_id"])) for row in rows
    }
    if observed_grid != expected_grid or len(rows) != len(expected_grid):
        raise ContractError("Source-cardinality recovery track table grid changed")

    expected_error = "Too few source weed tracks: 0"
    try:
        validate_botanical_scene(scene_root, config, full_candidate=True)
    except RuntimeError as error:
        if str(error) != expected_error:
            raise ContractError(
                f"Source-cardinality recovery saw a different validator failure: {error}"
            ) from error
    else:
        raise ContractError(
            "Source-cardinality recovery expected the locked zero-weed validator failure"
        )

    return {
        "schema_version": 1,
        "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "source_scene_graph_identity_sha256": source[
            "source_scene_graph_identity_sha256"
        ],
        "source_track_count": len(source_tracks),
        "source_crop_track_count": crop_count,
        "source_weed_track_count": weed_count,
        "frame_count": frame_count,
        "native_dimensions_px": list(expected_size),
        "track_table_full_grid": True,
        "locked_botanical_validator_failure": expected_error,
        "rejection_reason": "eligibility:source_weed_track_present",
        "source_gt_file_sha256": {
            "source_objects.json": sha256_file(source_path),
            "track_registry.json": sha256_file(registry_path),
            "tracks.jsonl": sha256_file(tracks_path),
        },
        "model_or_outcome_inputs_used": False,
    }


def run_gt_source_cardinality_recovery(
    config_path: Path,
    pair_id: str,
    *,
    candidate_index: int,
) -> dict[str, Any]:
    """Reproduce and commit one exact zero-source-weed eligibility rejection."""
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    preflight_receipt = preflight(config_path, scope="fixture")
    paths = full_paths(config)
    full_root = paths["synthetic"]
    roster_row = full_roster_row(config, pair_id)
    if roster_row["protocol_split"] != "calibration":
        raise ContractError("Source-cardinality recovery is calibration-only")
    published_pair = full_root / "pairs/calibration" / pair_id
    if published_pair.exists():
        raise ContractError("Source-cardinality recovery cannot target a published pair")
    candidates = roster_row["candidates"]
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise ContractError("Source-cardinality recovery candidate escaped the roster")
    candidate = candidates[candidate_index]

    recovery_root = full_root / "planning/gt_source_cardinality_recovery_v1"
    destination = (
        recovery_root
        / "roster"
        / pair_id
        / f"candidate_{candidate_index:02d}"
    )
    docs_path = (
        paths["docs"]
        / "gt_scout_v1"
        / f"source_cardinality_recovery_{pair_id}_candidate_{candidate_index:02d}.json"
    )
    if destination.exists():
        terminal_path = destination / "recovery_terminal_receipt.json"
        decision_path = destination / "decision_receipt.json"
        terminal = load_json(terminal_path)
        decision = load_json(decision_path)
        if (
            terminal.get("status")
            != "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
            or terminal.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or terminal.get("recovery_implementation_sha256")
            != gt_source_cardinality_recovery_implementation_sha256()
            or decision.get("rejection_reasons")
            != ["eligibility:source_weed_track_present"]
        ):
            raise ContractError("Existing source-cardinality recovery binding changed")
        commit = _commit_gt_scout_rejection(
            full_root, destination, roster_row, candidate, decision
        )
        _write_json_once_atomically(docs_path, terminal)
        return {
            "status": "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "candidate_index": candidate_index,
            "destination": str(destination),
            "recovery_terminal_receipt_sha256": sha256_file(terminal_path),
            "ledger_commit": commit,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    next_candidate = _next_gt_scout_candidate(full_root, roster_row)
    if int(next_candidate["candidate_index"]) != candidate_index:
        raise ContractError(
            "Source-cardinality recovery candidate is not the next canonical candidate"
        )
    recovery_root.mkdir(parents=True, exist_ok=True)
    staging = recovery_root / (
        f".partial-{pair_id}-candidate-{candidate_index:02d}-{uuid.uuid4().hex}"
    )
    _require_child(staging, recovery_root, "source-cardinality recovery staging")
    staging.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        asset_partition = load_json(full_root / "planning/asset_partition_v1.json")
        asset_role = asset_partition["roles"]["calibration"]
        source_path = full_candidate_source_path(config, roster_row, candidate)
        derived = derive_full_native_scene_config(
            load_yaml(source_path), roster_row, candidate, asset_role, config
        )
        derived_path = staging / "scene_config.yaml"
        derived_path.write_text(
            yaml.safe_dump(derived, sort_keys=False), encoding="utf-8"
        )
        patch_path = staging / "bindings/gt_scout_scene.patch"
        patch_receipt = compose_gt_scout_patch(config, patch_path)
        scout_lock = ensure_gt_scout_execution_lock(
            config_path, config, plan, patch_receipt
        )
        recovery_lock = ensure_gt_source_cardinality_recovery_execution_lock(
            config_path, config, plan
        )
        scene_root = staging / "source_scene"
        generation = run_cropcraft_scene(
            derived_path, scene_root, patch_path, config
        )
        capture = _validate_gt_scout_capture_receipt(
            scene_root, roster_row, candidate
        )
        used_assets = validate_full_used_assets(scene_root, asset_role)
        audit = _audit_zero_source_weed_failure(scene_root, config)
        decision = {
            "schema_version": 1,
            "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "status": "REJECT_FROZEN_GT_ONLY_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "rejectable_by_scout": True,
            "rejection_reasons": ["eligibility:source_weed_track_present"],
            "source_cardinality_checks": {
                "source_crop_track_present": True,
                "source_weed_track_present": False,
            },
            "decision_contract_sha256": gt_scout_decision_contract(config)[
                "contract_sha256"
            ],
            "full_render_still_required_for_acceptance": True,
            "recovery_has_acceptance_authority": False,
            "model_or_outcome_inputs_used": False,
            "registered_targets_used": False,
            "synthetic_only": True,
        }
        write_json(staging / "source_cardinality_audit.json", audit)
        write_json(staging / "decision_receipt.json", decision)

        evidence_root = staging / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=False)
        retained: dict[str, str] = {}
        for source, name in (
            (scene_root / "generation_receipt.json", "generation_receipt.json"),
            (scene_root / "gt_scout_capture_receipt.json", "capture_receipt.json"),
            (
                scene_root / "botanical_ground_truth/source_objects.json",
                "source_objects.json",
            ),
            (
                scene_root / "botanical_ground_truth/track_registry.json",
                "track_registry.json",
            ),
            (
                scene_root / "botanical_ground_truth/tracks.jsonl",
                "tracks.jsonl",
            ),
            (staging / "source_scene.runner.log", "cropcraft_runner.log"),
        ):
            if not source.is_file():
                raise ContractError(
                    f"Source-cardinality retained evidence is missing: {source}"
                )
            target = evidence_root / name
            shutil.copy2(source, target)
            retained[name] = sha256_file(target)
        bulk_bytes_before_cleanup = _tree_bytes(scene_root)
        shutil.rmtree(scene_root)
        (staging / "source_scene.runner.log").unlink()
        cleanup = {
            "bulk_bytes_removed": bulk_bytes_before_cleanup,
            "source_scene_removed": True,
            "retained_receipts_and_log": retained,
            "bulk_payload_retained": False,
            "bounded_to_recovery_staging": True,
        }
        write_json(staging / "bounded_cleanup_receipt.json", cleanup)
        inventory = artifact_inventory(staging)
        if any("prediction" in row["path"].lower() for row in inventory):
            raise ContractError("Prediction output exists in source-cardinality recovery")
        terminal = {
            "schema_version": 1,
            "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "protocol_split": "calibration",
            "pair_slot_identity_sha256": roster_row["pair_slot_identity_sha256"],
            "candidate_index": candidate_index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "candidate_seeds": copy.deepcopy(candidate["seeds"]),
            "all_five_seed_bindings_exact": set(capture["seed_bindings"])
            == set(candidate["seeds"]),
            "source_template": copy.deepcopy(candidate["source_template"]),
            "source_template_sha256_exact": sha256_file(source_path)
            == candidate["source_template"]["sha256"],
            "role_asset_validation": used_assets,
            "source_cardinality_audit": audit,
            "decision": decision,
            "generation": generation,
            "composed_patch": patch_receipt,
            "sealed_gt_scout_execution_lock_sha256": scout_lock["sha256"],
            "sealed_full_render_execution_lock_sha256": scout_lock[
                "sealed_full_render_execution_lock_sha256"
            ],
            "recovery_execution_lock_sha256": recovery_lock["sha256"],
            "recovery_implementation_sha256": recovery_lock[
                "recovery_implementation_sha256"
            ],
            "preflight": {
                "scope": preflight_receipt["scope"],
                "capacity": preflight_receipt["capacity"],
                "gpu": preflight_receipt["gpu"],
                "checkpoint_hash_verified_as_source_lock": True,
                "checkpoint_loaded": False,
            },
            "bounded_cleanup": cleanup,
            "inventory_sha256": stable_sha256(inventory),
            "inventory_file_count_before_terminal_receipt": len(inventory),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "model_loaded": False,
            "inference_calls": 0,
            "outcome_inputs": [],
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        write_json(staging / "recovery_terminal_receipt.json", terminal)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    commit = _commit_gt_scout_rejection(
        full_root, destination, roster_row, candidate, decision
    )
    terminal_path = destination / "recovery_terminal_receipt.json"
    _write_json_once_atomically(docs_path, load_json(terminal_path))
    return {
        "status": terminal["status"],
        "pair_id": pair_id,
        "candidate_index": candidate_index,
        "destination": str(destination),
        "recovery_terminal_receipt_sha256": sha256_file(terminal_path),
        "rejection_reasons": decision["rejection_reasons"],
        "ledger_commit": commit,
        "elapsed_wall_seconds": terminal["elapsed_wall_seconds"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def gt_source_cardinality_recovery_implementation_sha256() -> str:
    functions = (
        _audit_zero_source_weed_failure,
        run_gt_source_cardinality_recovery,
        ensure_gt_source_cardinality_recovery_execution_lock,
    )
    return stable_sha256(
        {
            "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "sealed_gt_scout_implementation_sha256": gt_scout_implementation_sha256(),
            "sealed_full_render_implementation_sha256": (
                SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
            ),
        }
    )


def ensure_gt_source_cardinality_recovery_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    worker_locks = _calibration_batch_source_locks(config)
    expected = {
        "schema_version": 1,
        "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "status": "SEALED_ZERO_SOURCE_WEED_RECOVERY_MODEL_FREE_SYNTHETIC_ONLY",
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan["pair_roster_sha256"],
        "sealed_full_render_execution_lock_sha256": worker_locks[
            "sealed_full_render_execution_lock_sha256"
        ],
        "sealed_full_render_implementation_sha256": worker_locks[
            "sealed_full_render_implementation_sha256"
        ],
        "sealed_gt_scout_execution_lock_sha256": worker_locks[
            "gt_scout_execution_lock_sha256"
        ],
        "sealed_gt_scout_implementation_sha256": worker_locks[
            "gt_scout_implementation_sha256"
        ],
        "recovery_implementation_sha256": (
            gt_source_cardinality_recovery_implementation_sha256()
        ),
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
        "model_access_allowed": False,
        "outcome_inputs_allowed": False,
        "registered_targets_allowed": False,
        "locked_test_access_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    path = (
        full_paths(config)["synthetic"]
        / "planning/gt_source_cardinality_recovery_execution_lock_v1.json"
    )
    if path.exists():
        if load_json(path) != expected:
            raise ContractError("Source-cardinality recovery execution lock changed")
    else:
        write_json(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


def _validate_calibration_batch_targets(
    rows: Sequence[Mapping[str, Any]],
    pair_ids: Sequence[str],
    max_new_pairs: int,
) -> list[dict[str, Any]]:
    if isinstance(max_new_pairs, bool) or max_new_pairs < 1:
        raise ContractError("Calibration batch max-new-pairs must be positive")
    normalized = [str(pair_id) for pair_id in pair_ids]
    if not normalized:
        raise ContractError("Calibration batch requires at least one explicit pair ID")
    if len(set(normalized)) != len(normalized):
        raise ContractError("Calibration batch pair IDs must be unique")
    if max_new_pairs > len(normalized):
        raise ContractError("Calibration batch limit exceeds its explicit target count")

    by_id = {str(row["pair_id"]): row for row in rows}
    missing = [pair_id for pair_id in normalized if pair_id not in by_id]
    if missing:
        raise ContractError(f"Calibration batch pair IDs are outside the roster: {missing}")
    selected = [by_id[pair_id] for pair_id in normalized]
    if any(row["protocol_split"] != "calibration" for row in selected):
        raise ContractError("Calibration batch may never target locked-test pairs")

    calibration_order = [
        str(row["pair_id"])
        for row in rows
        if row["protocol_split"] == "calibration"
    ]
    positions = [calibration_order.index(pair_id) for pair_id in normalized]
    expected = list(range(positions[0], positions[0] + len(positions)))
    if positions != expected:
        raise ContractError(
            "Calibration batch targets must be contiguous canonical roster slots"
        )
    return [dict(row) for row in selected]


def _calibration_batch_source_locks(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    full_lock = _validate_sealed_full_render_lock(config)
    scout_path = (
        full_paths(config)["synthetic"]
        / "planning/gt_scout_execution_lock_v1.json"
    )
    if not scout_path.is_file():
        raise ContractError("Calibration batch requires the sealed GT scout lock")
    scout = load_json(scout_path)
    if (
        scout.get("status") != "SEALED_GT_ONLY_SCOUT_MODEL_FREE_SYNTHETIC_ONLY"
        or scout.get("sealed_full_render_execution_lock_sha256")
        != full_lock["sha256"]
        or scout.get("sealed_full_render_implementation_sha256")
        != full_lock["render_implementation_sha256"]
        or scout.get("gt_scout_implementation_sha256")
        != gt_scout_implementation_sha256()
        or scout.get("model_access_allowed") is not False
        or scout.get("outcome_inputs_allowed") is not False
        or scout.get("registered_targets_allowed") is not False
    ):
        raise ContractError("Calibration batch GT scout lock changed")
    return {
        "sealed_full_render_execution_lock_sha256": full_lock["sha256"],
        "sealed_full_render_implementation_sha256": full_lock[
            "render_implementation_sha256"
        ],
        "gt_scout_execution_lock_sha256": sha256_file(scout_path),
        "gt_scout_implementation_sha256": scout[
            "gt_scout_implementation_sha256"
        ],
    }


def _write_json_once_atomically(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        if load_json(path) != dict(value):
            raise ContractError(f"Refusing to overwrite changed receipt: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".partial-{path.name}-{uuid.uuid4().hex}"
    try:
        write_json(temporary, value)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _publish_calibration_batch_intent(
    batch_parent: Path,
    batch_id: str,
    intent: Mapping[str, Any],
) -> Path:
    if SAFE_ID_RE.fullmatch(batch_id) is None:
        raise ContractError(f"Unsafe calibration batch ID: {batch_id}")
    batch_parent.mkdir(parents=True, exist_ok=True)
    batch_root = batch_parent / batch_id
    _require_child(batch_root, batch_parent, "calibration batch intent")
    if batch_root.exists():
        intent_path = batch_root / "batch_intent.json"
        if not intent_path.is_file() or load_json(intent_path) != dict(intent):
            raise ContractError("Existing calibration batch intent changed")
        return batch_root
    staging = batch_parent / f".partial-{batch_id}-{uuid.uuid4().hex}"
    _require_child(staging, batch_parent, "calibration batch intent staging")
    staging.mkdir(parents=False, exist_ok=False)
    try:
        write_json(staging / "batch_intent.json", intent)
        staging.replace(batch_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return batch_root


def _assert_model_free_batch_result(
    result: Mapping[str, Any], label: str
) -> None:
    if result.get("model_loaded") is not False or result.get("inference_calls") != 0:
        raise ContractError(f"{label} escaped the model-free calibration batch")


def _validate_calibration_batch_receipt(
    receipt: Mapping[str, Any],
    request_identity_sha256: str,
    target_pair_ids: Sequence[str],
) -> None:
    valid = (
        receipt.get("contract") == CALIBRATION_BATCH_CONTRACT
        and receipt.get("status")
        == "PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
        and receipt.get("request_identity_sha256") == request_identity_sha256
        and receipt.get("target_pair_ids") == list(target_pair_ids)
        and receipt.get("new_pair_count")
        == len(receipt.get("new_pair_ids", []))
        and receipt.get("model_loaded") is False
        and receipt.get("inference_calls") == 0
        and receipt.get("locked_test_outcome_accessed") is False
        and receipt.get("outcome_inputs") == []
    )
    if not valid:
        raise ContractError("Calibration batch terminal receipt changed")


def run_calibration_batch(
    config_path: Path,
    pair_ids: Sequence[str],
    *,
    max_new_pairs: int = 1,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    paths = full_paths(config)
    full_root = paths["synthetic"]
    rows = full_roster_rows(config)
    targets = _validate_calibration_batch_targets(
        rows, pair_ids, max_new_pairs
    )
    target_pair_ids = [str(row["pair_id"]) for row in targets]
    locks = ensure_calibration_batch_execution_lock(config_path, config, plan)
    request = {
        "schema_version": 1,
        "contract": CALIBRATION_BATCH_CONTRACT,
        "execution_config_sha256": sha256_file(config_path),
        "pair_roster_sha256": plan["pair_roster_sha256"],
        "batch_execution_lock_sha256": locks["sha256"],
        "target_pair_ids": target_pair_ids,
        "max_new_pairs": int(max_new_pairs),
        "protocol_split": "calibration",
        "model_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
    }
    request_identity = stable_sha256(request)
    batch_id = (
        f"calibration_batch_{target_pair_ids[0]}_{request_identity[:16]}"
    )
    batch_parent = full_root / "planning/calibration_batches_v1"
    batch_root = batch_parent / batch_id
    receipt_path = batch_root / "batch_receipt.json"
    docs_path = paths["docs"] / "calibration_batches" / f"{batch_id}.json"
    all_by_id = {str(row["pair_id"]): row for row in rows}

    if receipt_path.is_file():
        receipt = load_json(receipt_path)
        _validate_calibration_batch_receipt(
            receipt, request_identity, target_pair_ids
        )
        state = inspect_full_render_state(full_root, rows)
        if any(pair_id not in state["completed_pair_ids"] for pair_id in receipt[
            "new_pair_ids"
        ]):
            raise ContractError("Published calibration batch pair disappeared")
        _write_json_once_atomically(docs_path, receipt)
        return {
            "status": "SKIP_EXISTING_PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY",
            "batch_id": batch_id,
            "target_pair_ids": target_pair_ids,
            "new_pair_ids": receipt["new_pair_ids"],
            "batch_receipt_sha256": sha256_file(receipt_path),
            "render_state": state,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    intent_path = batch_root / "batch_intent.json"
    resumed_from_existing_intent = intent_path.is_file()
    if resumed_from_existing_intent:
        intent = load_json(intent_path)
        if intent.get("request") != request:
            raise ContractError("Existing calibration batch request changed")
    else:
        if batch_root.exists():
            raise ContractError("Calibration batch root has no valid intent")
        initial_state = inspect_full_render_state(full_root, rows)
        pending_calibration = [
            str(row["pair_id"])
            for row in rows
            if row["protocol_split"] == "calibration"
            and row["pair_id"] in initial_state["pending_pair_ids"]
        ]
        if target_pair_ids != pending_calibration[: len(target_pair_ids)]:
            raise ContractError(
                "Calibration batch must start at the earliest pending canonical slot"
            )
        ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
        intent = {
            "schema_version": 1,
            "status": "LOCKED_CALIBRATION_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY",
            "request_identity_sha256": request_identity,
            "batch_id": batch_id,
            "request": request,
            "completed_pair_ids_at_start": initial_state["completed_pair_ids"],
            "candidate_rejection_ledger_sha256_at_start": sha256_file(
                ledger_path
            ),
            "model_loaded": False,
            "inference_calls": 0,
            "outcome_inputs": [],
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        batch_root = _publish_calibration_batch_intent(
            batch_parent, batch_id, intent
        )
        intent_path = batch_root / "batch_intent.json"
        receipt_path = batch_root / "batch_receipt.json"

    completed_at_start = set(intent["completed_pair_ids_at_start"])
    state_before = inspect_full_render_state(full_root, rows)
    recovered_pair_ids = [
        pair_id
        for pair_id in target_pair_ids
        if pair_id in state_before["completed_pair_ids"]
        and pair_id not in completed_at_start
    ]
    if len(recovered_pair_ids) > max_new_pairs:
        raise ContractError("Calibration batch published beyond its declared limit")
    new_pair_ids = list(recovered_pair_ids)
    invocation_events: list[dict[str, Any]] = []
    started = time.perf_counter()
    full_preflight = preflight(config_path, scope="full")
    capacity = build_full_capacity_receipt(config, full_preflight)

    for roster_row in targets:
        if len(new_pair_ids) >= max_new_pairs:
            break
        pair_id = str(roster_row["pair_id"])
        if pair_id in state_before["completed_pair_ids"]:
            continue
        seen_candidate_indices: set[int] = set()
        for _ in range(len(roster_row["candidates"])):
            candidate = _next_gt_scout_candidate(full_root, roster_row)
            candidate_index = int(candidate["candidate_index"])
            if candidate_index in seen_candidate_indices:
                raise ContractError("Calibration batch candidate loop did not advance")
            seen_candidate_indices.add(candidate_index)
            scout = run_gt_scout_candidate(config_path, pair_id)
            _assert_model_free_batch_result(scout, "GT scout")
            scout_destination = Path(str(scout["destination"]))
            decision = load_json(scout_destination / "decision_receipt.json")
            event: dict[str, Any] = {
                "stage": "gt_scout",
                "pair_id": pair_id,
                "candidate_index": candidate_index,
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
                "status": scout["status"],
                "terminal_receipt_sha256": sha256_file(
                    scout_destination / "gt_scout_terminal_receipt.json"
                ),
                "rejection_reasons": decision["rejection_reasons"],
            }
            invocation_events.append(event)
            if decision["rejectable_by_scout"]:
                if scout.get("ledger_commit") is None:
                    raise ContractError("GT scout rejection was not committed")
                continue
            if decision.get("full_render_still_required_for_acceptance") is not True:
                raise ContractError("GT scout improperly claimed acceptance authority")
            try:
                rendered = render_full_pair(config_path, pair_id)
            except CandidateRejected as error:
                invocation_events.append(
                    {
                        "stage": "full_render",
                        "pair_id": pair_id,
                        "candidate_index": candidate_index,
                        "status": "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY",
                        "reason_type": type(error).__name__,
                        "reason": str(error),
                    }
                )
                continue
            _assert_model_free_batch_result(rendered, "Full renderer")
            if rendered["status"] != "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY":
                raise ContractError("Calibration batch full renderer did not publish")
            new_pair_ids.append(pair_id)
            invocation_events.append(
                {
                    "stage": "full_render",
                    "pair_id": pair_id,
                    "candidate_index": candidate_index,
                    "status": rendered["status"],
                    "terminal_receipt_sha256": rendered[
                        "full_pair_receipt_sha256"
                    ],
                }
            )
            break
        else:
            raise ContractError(f"Calibration batch exhausted candidates: {pair_id}")

    if len(new_pair_ids) != max_new_pairs:
        raise ContractError(
            "Calibration batch ended before publishing its declared new-pair limit"
        )
    final_state = inspect_full_render_state(full_root, rows)
    if any(pair_id not in final_state["completed_pair_ids"] for pair_id in new_pair_ids):
        raise ContractError("Calibration batch terminal state lost a new pair")
    write_json(full_root / "planning/render_state_v1.json", final_state)
    write_json(paths["docs"] / "render_state_v1.json", final_state)

    ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
    ledger = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    selected_pairs: list[dict[str, Any]] = []
    for pair_id in new_pair_ids:
        row = all_by_id[pair_id]
        pair_root = full_root / "pairs/calibration" / pair_id
        terminal = load_json(pair_root / "full_pair_receipt.json")
        _validate_publishable_full_pair_receipt(terminal, row)
        selected_pairs.append(
            {
                "pair_id": pair_id,
                "selected_candidate_index": terminal[
                    "selected_candidate_index"
                ],
                "candidate_identity_sha256": terminal[
                    "candidate_identity_sha256"
                ],
                "canonical_gt_sha256": terminal["canonical_gt_sha256"],
                "full_pair_receipt_sha256": sha256_file(
                    pair_root / "full_pair_receipt.json"
                ),
                "all_pair_quality_gates_passed": all(
                    terminal["pair_quality_gates"].values()
                ),
            }
        )
    target_rejections = [
        row for row in ledger if row["pair_id"] in target_pair_ids
    ]
    receipt = {
        "schema_version": 1,
        "contract": CALIBRATION_BATCH_CONTRACT,
        "status": "PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY",
        "batch_id": batch_id,
        "request_identity_sha256": request_identity,
        "batch_execution_lock_sha256": locks["sha256"],
        "target_pair_ids": target_pair_ids,
        "max_new_pairs": int(max_new_pairs),
        "new_pair_count": len(new_pair_ids),
        "new_pair_ids": new_pair_ids,
        "selected_pairs": selected_pairs,
        "canonical_rejection_rows": target_rejections,
        "candidate_events_current_invocation": invocation_events,
        "resume": {
            "resumed_from_existing_intent": resumed_from_existing_intent,
            "recovered_published_pair_ids": recovered_pair_ids,
            "intent_sha256": sha256_file(intent_path),
        },
        "render_state": final_state,
        "capacity_check": capacity["projection"],
        "gpu": full_preflight["gpu"],
        "elapsed_wall_seconds_current_invocation": time.perf_counter() - started,
        "model_loaded": False,
        "inference_calls": 0,
        "locked_test_outcome_accessed": False,
        "outcome_inputs": [],
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    _validate_calibration_batch_receipt(
        receipt, request_identity, target_pair_ids
    )
    _write_json_once_atomically(receipt_path, receipt)
    _write_json_once_atomically(docs_path, receipt)
    return {
        "status": receipt["status"],
        "batch_id": batch_id,
        "target_pair_ids": target_pair_ids,
        "new_pair_ids": new_pair_ids,
        "batch_receipt_sha256": sha256_file(receipt_path),
        "render_state": final_state,
        "elapsed_wall_seconds": receipt[
            "elapsed_wall_seconds_current_invocation"
        ],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def calibration_batch_implementation_sha256() -> str:
    functions = (
        _validate_calibration_batch_targets,
        _calibration_batch_source_locks,
        _write_json_once_atomically,
        _publish_calibration_batch_intent,
        _assert_model_free_batch_result,
        _validate_calibration_batch_receipt,
        run_calibration_batch,
        ensure_calibration_batch_execution_lock,
    )
    return stable_sha256(
        {
            "contract": CALIBRATION_BATCH_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "sealed_full_render_implementation_sha256": (
                SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
            ),
            "sealed_full_render_execution_lock_sha256": (
                SEALED_FULL_RENDER_EXECUTION_LOCK_SHA256
            ),
        }
    )


def ensure_calibration_batch_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    source_locks = _calibration_batch_source_locks(config)
    expected = {
        "schema_version": 1,
        "contract": CALIBRATION_BATCH_CONTRACT,
        "status": "SEALED_CALIBRATION_BATCH_MODEL_FREE_SYNTHETIC_ONLY",
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan["pair_roster_sha256"],
        "calibration_batch_implementation_sha256": (
            calibration_batch_implementation_sha256()
        ),
        **source_locks,
        "target_scope": "explicit_contiguous_canonical_calibration_slots_only",
        "new_pair_limit_required": True,
        "durable_intent_required": True,
        "model_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
        "outcome_inputs_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    path = (
        full_paths(config)["synthetic"]
        / "planning/calibration_batch_execution_lock_v1.json"
    )
    if path.exists():
        if load_json(path) != expected:
            raise ContractError("Calibration batch execution lock changed")
    else:
        _write_json_once_atomically(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


def _validate_locked_test_render_batch_targets(
    rows: Sequence[Mapping[str, Any]],
    pair_ids: Sequence[str],
    max_new_pairs: int,
) -> list[dict[str, Any]]:
    if isinstance(max_new_pairs, bool) or max_new_pairs < 1:
        raise ContractError("Locked-test render batch max-new-pairs must be positive")
    normalized = [str(pair_id) for pair_id in pair_ids]
    if not normalized:
        raise ContractError(
            "Locked-test render batch requires at least one explicit pair ID"
        )
    if len(set(normalized)) != len(normalized):
        raise ContractError("Locked-test render batch pair IDs must be unique")
    if max_new_pairs > len(normalized):
        raise ContractError(
            "Locked-test render batch limit exceeds its explicit target count"
        )

    by_id = {str(row["pair_id"]): row for row in rows}
    missing = [pair_id for pair_id in normalized if pair_id not in by_id]
    if missing:
        raise ContractError(
            f"Locked-test render batch pair IDs are outside the roster: {missing}"
        )
    selected = [by_id[pair_id] for pair_id in normalized]
    if any(row["protocol_split"] != "locked_test" for row in selected):
        raise ContractError(
            "Locked-test render batch may never target calibration pairs"
        )

    locked_test_order = [
        str(row["pair_id"])
        for row in rows
        if row["protocol_split"] == "locked_test"
    ]
    positions = [locked_test_order.index(pair_id) for pair_id in normalized]
    expected = list(range(positions[0], positions[0] + len(positions)))
    if positions != expected:
        raise ContractError(
            "Locked-test render batch targets must be contiguous canonical roster slots"
        )
    return [dict(row) for row in selected]


def _locked_test_render_batch_source_locks(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    return _calibration_batch_source_locks(config)


def _assert_locked_test_render_batch_access_guard(
    paths: Mapping[str, Path],
    rows: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
) -> None:
    calibration_pair_ids = {
        str(row["pair_id"])
        for row in rows
        if row["protocol_split"] == "calibration"
    }
    completed_pair_ids = set(state["completed_pair_ids"])
    missing_calibration = sorted(calibration_pair_ids - completed_pair_ids)
    if missing_calibration:
        raise ContractError(
            "Locked-test rendering requires complete calibration rendering first: "
            f"{missing_calibration[:3]}"
        )
    if state.get("model_outputs_present") is not False:
        raise ContractError(
            "Locked-test rendering is forbidden after full-benchmark model output exists"
        )
    if Path(paths["run"]).exists():
        raise ContractError(
            "Locked-test rendering requires the full-benchmark model run root to be absent"
        )


def _publish_locked_test_render_batch_intent(
    batch_parent: Path,
    batch_id: str,
    intent: Mapping[str, Any],
) -> Path:
    if SAFE_ID_RE.fullmatch(batch_id) is None:
        raise ContractError(f"Unsafe locked-test render batch ID: {batch_id}")
    batch_parent.mkdir(parents=True, exist_ok=True)
    batch_root = batch_parent / batch_id
    _require_child(batch_root, batch_parent, "locked-test render batch intent")
    if batch_root.exists():
        intent_path = batch_root / "batch_intent.json"
        if not intent_path.is_file() or load_json(intent_path) != dict(intent):
            raise ContractError("Existing locked-test render batch intent changed")
        return batch_root
    staging = batch_parent / f".partial-{batch_id}-{uuid.uuid4().hex}"
    _require_child(
        staging, batch_parent, "locked-test render batch intent staging"
    )
    staging.mkdir(parents=False, exist_ok=False)
    try:
        write_json(staging / "batch_intent.json", intent)
        staging.replace(batch_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return batch_root


def _assert_model_free_locked_test_render_batch_result(
    result: Mapping[str, Any], label: str
) -> None:
    if result.get("model_loaded") is not False or result.get("inference_calls") != 0:
        raise ContractError(f"{label} escaped the model-free locked-test render batch")


def _validate_locked_test_render_batch_receipt(
    receipt: Mapping[str, Any],
    request_identity_sha256: str,
    target_pair_ids: Sequence[str],
) -> None:
    valid = (
        receipt.get("contract") == LOCKED_TEST_RENDER_BATCH_CONTRACT
        and receipt.get("status")
        == "PASS_LOCKED_TEST_RENDER_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
        and receipt.get("request_identity_sha256") == request_identity_sha256
        and receipt.get("target_pair_ids") == list(target_pair_ids)
        and receipt.get("new_pair_count")
        == len(receipt.get("new_pair_ids", []))
        and receipt.get("model_loaded") is False
        and receipt.get("inference_calls") == 0
        and receipt.get("locked_test_prediction_accessed") is False
        and receipt.get("locked_test_outcome_accessed") is False
        and receipt.get("outcome_inputs") == []
    )
    if not valid:
        raise ContractError("Locked-test render batch terminal receipt changed")


def run_locked_test_render_batch(
    config_path: Path,
    pair_ids: Sequence[str],
    *,
    max_new_pairs: int = 1,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    paths = full_paths(config)
    full_root = paths["synthetic"]
    rows = full_roster_rows(config)
    targets = _validate_locked_test_render_batch_targets(
        rows, pair_ids, max_new_pairs
    )
    target_pair_ids = [str(row["pair_id"]) for row in targets]
    locks = ensure_locked_test_render_batch_execution_lock(
        config_path, config, plan
    )
    initial_guard_state = inspect_full_render_state(full_root, rows)
    _assert_locked_test_render_batch_access_guard(
        paths, rows, initial_guard_state
    )
    request = {
        "schema_version": 1,
        "contract": LOCKED_TEST_RENDER_BATCH_CONTRACT,
        "execution_config_sha256": sha256_file(config_path),
        "pair_roster_sha256": plan["pair_roster_sha256"],
        "batch_execution_lock_sha256": locks["sha256"],
        "target_pair_ids": target_pair_ids,
        "max_new_pairs": int(max_new_pairs),
        "protocol_split": "locked_test",
        "render_and_machine_audit_only": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
    }
    request_identity = stable_sha256(request)
    batch_id = (
        f"locked_test_render_batch_{target_pair_ids[0]}_"
        f"{request_identity[:16]}"
    )
    batch_parent = full_root / "planning/locked_test_render_batches_v1"
    batch_root = batch_parent / batch_id
    receipt_path = batch_root / "batch_receipt.json"
    docs_path = (
        paths["docs"] / "locked_test_render_batches" / f"{batch_id}.json"
    )
    all_by_id = {str(row["pair_id"]): row for row in rows}

    if receipt_path.is_file():
        receipt = load_json(receipt_path)
        _validate_locked_test_render_batch_receipt(
            receipt, request_identity, target_pair_ids
        )
        state = inspect_full_render_state(full_root, rows)
        _assert_locked_test_render_batch_access_guard(paths, rows, state)
        if any(
            pair_id not in state["completed_pair_ids"]
            for pair_id in receipt["new_pair_ids"]
        ):
            raise ContractError("Published locked-test render batch pair disappeared")
        _write_json_once_atomically(docs_path, receipt)
        return {
            "status": (
                "SKIP_EXISTING_PASS_LOCKED_TEST_RENDER_BATCH_"
                "PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "batch_id": batch_id,
            "target_pair_ids": target_pair_ids,
            "new_pair_ids": receipt["new_pair_ids"],
            "batch_receipt_sha256": sha256_file(receipt_path),
            "render_state": state,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    intent_path = batch_root / "batch_intent.json"
    resumed_from_existing_intent = intent_path.is_file()
    if resumed_from_existing_intent:
        intent = load_json(intent_path)
        if intent.get("request") != request:
            raise ContractError("Existing locked-test render batch request changed")
    else:
        if batch_root.exists():
            raise ContractError("Locked-test render batch root has no valid intent")
        pending_locked_test = [
            str(row["pair_id"])
            for row in rows
            if row["protocol_split"] == "locked_test"
            and row["pair_id"] in initial_guard_state["pending_pair_ids"]
        ]
        if target_pair_ids != pending_locked_test[: len(target_pair_ids)]:
            raise ContractError(
                "Locked-test render batch must start at the earliest pending "
                "canonical slot"
            )
        ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
        intent = {
            "schema_version": 1,
            "status": (
                "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "request_identity_sha256": request_identity,
            "batch_id": batch_id,
            "request": request,
            "completed_pair_ids_at_start": initial_guard_state[
                "completed_pair_ids"
            ],
            "candidate_rejection_ledger_sha256_at_start": sha256_file(
                ledger_path
            ),
            "locked_test_predictions_present_at_start": False,
            "model_loaded": False,
            "inference_calls": 0,
            "outcome_inputs": [],
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        batch_root = _publish_locked_test_render_batch_intent(
            batch_parent, batch_id, intent
        )
        intent_path = batch_root / "batch_intent.json"
        receipt_path = batch_root / "batch_receipt.json"

    completed_at_start = set(intent["completed_pair_ids_at_start"])
    state_before = inspect_full_render_state(full_root, rows)
    _assert_locked_test_render_batch_access_guard(paths, rows, state_before)
    recovered_pair_ids = [
        pair_id
        for pair_id in target_pair_ids
        if pair_id in state_before["completed_pair_ids"]
        and pair_id not in completed_at_start
    ]
    if len(recovered_pair_ids) > max_new_pairs:
        raise ContractError(
            "Locked-test render batch published beyond its declared limit"
        )
    new_pair_ids = list(recovered_pair_ids)
    invocation_events: list[dict[str, Any]] = []
    started = time.perf_counter()
    full_preflight = preflight(config_path, scope="full")
    capacity = build_full_capacity_receipt(config, full_preflight)

    for roster_row in targets:
        if len(new_pair_ids) >= max_new_pairs:
            break
        pair_id = str(roster_row["pair_id"])
        if pair_id in state_before["completed_pair_ids"]:
            continue
        seen_candidate_indices: set[int] = set()
        for _ in range(len(roster_row["candidates"])):
            candidate = _next_gt_scout_candidate(full_root, roster_row)
            candidate_index = int(candidate["candidate_index"])
            if candidate_index in seen_candidate_indices:
                raise ContractError(
                    "Locked-test render batch candidate loop did not advance"
                )
            seen_candidate_indices.add(candidate_index)
            scout = run_gt_scout_candidate(config_path, pair_id)
            _assert_model_free_locked_test_render_batch_result(
                scout, "GT scout"
            )
            scout_destination = Path(str(scout["destination"]))
            decision = load_json(scout_destination / "decision_receipt.json")
            event: dict[str, Any] = {
                "stage": "gt_scout",
                "pair_id": pair_id,
                "candidate_index": candidate_index,
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
                "status": scout["status"],
                "terminal_receipt_sha256": sha256_file(
                    scout_destination / "gt_scout_terminal_receipt.json"
                ),
                "rejection_reasons": decision["rejection_reasons"],
            }
            invocation_events.append(event)
            if decision["rejectable_by_scout"]:
                if scout.get("ledger_commit") is None:
                    raise ContractError("GT scout rejection was not committed")
                continue
            if decision.get("full_render_still_required_for_acceptance") is not True:
                raise ContractError(
                    "GT scout improperly claimed acceptance authority"
                )
            try:
                rendered = render_full_pair(config_path, pair_id)
            except CandidateRejected as error:
                invocation_events.append(
                    {
                        "stage": "full_render",
                        "pair_id": pair_id,
                        "candidate_index": candidate_index,
                        "status": (
                            "REJECTED_FULL_PAIR_CANDIDATE_"
                            "PREOUTCOME_SYNTHETIC_ONLY"
                        ),
                        "reason_type": type(error).__name__,
                        "reason": str(error),
                    }
                )
                continue
            _assert_model_free_locked_test_render_batch_result(
                rendered, "Full renderer"
            )
            if rendered["status"] != "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY":
                raise ContractError(
                    "Locked-test render batch full renderer did not publish"
                )
            new_pair_ids.append(pair_id)
            invocation_events.append(
                {
                    "stage": "full_render",
                    "pair_id": pair_id,
                    "candidate_index": candidate_index,
                    "status": rendered["status"],
                    "terminal_receipt_sha256": rendered[
                        "full_pair_receipt_sha256"
                    ],
                }
            )
            break
        else:
            raise ContractError(
                f"Locked-test render batch exhausted candidates: {pair_id}"
            )

    if len(new_pair_ids) != max_new_pairs:
        raise ContractError(
            "Locked-test render batch ended before publishing its declared "
            "new-pair limit"
        )
    final_state = inspect_full_render_state(full_root, rows)
    _assert_locked_test_render_batch_access_guard(paths, rows, final_state)
    if any(
        pair_id not in final_state["completed_pair_ids"]
        for pair_id in new_pair_ids
    ):
        raise ContractError("Locked-test render batch terminal state lost a new pair")
    write_json(full_root / "planning/render_state_v1.json", final_state)
    write_json(paths["docs"] / "render_state_v1.json", final_state)

    ledger_path = full_root / "planning/candidate_rejection_ledger_v1.jsonl"
    ledger = read_jsonl(ledger_path) if ledger_path.stat().st_size else []
    selected_pairs: list[dict[str, Any]] = []
    for pair_id in new_pair_ids:
        row = all_by_id[pair_id]
        pair_root = full_root / "pairs/locked_test" / pair_id
        terminal = load_json(pair_root / "full_pair_receipt.json")
        _validate_publishable_full_pair_receipt(terminal, row)
        selected_pairs.append(
            {
                "pair_id": pair_id,
                "selected_candidate_index": terminal[
                    "selected_candidate_index"
                ],
                "candidate_identity_sha256": terminal[
                    "candidate_identity_sha256"
                ],
                "canonical_gt_sha256": terminal["canonical_gt_sha256"],
                "full_pair_receipt_sha256": sha256_file(
                    pair_root / "full_pair_receipt.json"
                ),
                "all_pair_quality_gates_passed": all(
                    terminal["pair_quality_gates"].values()
                ),
            }
        )
    target_rejections = [
        row for row in ledger if row["pair_id"] in target_pair_ids
    ]
    receipt = {
        "schema_version": 1,
        "contract": LOCKED_TEST_RENDER_BATCH_CONTRACT,
        "status": "PASS_LOCKED_TEST_RENDER_BATCH_PREOUTCOME_SYNTHETIC_ONLY",
        "batch_id": batch_id,
        "request_identity_sha256": request_identity,
        "batch_execution_lock_sha256": locks["sha256"],
        "target_pair_ids": target_pair_ids,
        "max_new_pairs": int(max_new_pairs),
        "new_pair_count": len(new_pair_ids),
        "new_pair_ids": new_pair_ids,
        "selected_pairs": selected_pairs,
        "canonical_rejection_rows": target_rejections,
        "candidate_events_current_invocation": invocation_events,
        "resume": {
            "resumed_from_existing_intent": resumed_from_existing_intent,
            "recovered_published_pair_ids": recovered_pair_ids,
            "intent_sha256": sha256_file(intent_path),
        },
        "render_state": final_state,
        "capacity_check": capacity["projection"],
        "gpu": full_preflight["gpu"],
        "elapsed_wall_seconds_current_invocation": time.perf_counter() - started,
        "render_and_machine_audit_only": True,
        "model_loaded": False,
        "inference_calls": 0,
        "locked_test_prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "outcome_inputs": [],
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    _validate_locked_test_render_batch_receipt(
        receipt, request_identity, target_pair_ids
    )
    _write_json_once_atomically(receipt_path, receipt)
    _write_json_once_atomically(docs_path, receipt)
    return {
        "status": receipt["status"],
        "batch_id": batch_id,
        "target_pair_ids": target_pair_ids,
        "new_pair_ids": new_pair_ids,
        "batch_receipt_sha256": sha256_file(receipt_path),
        "render_state": final_state,
        "elapsed_wall_seconds": receipt[
            "elapsed_wall_seconds_current_invocation"
        ],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def locked_test_render_batch_implementation_sha256() -> str:
    functions = (
        _validate_locked_test_render_batch_targets,
        _locked_test_render_batch_source_locks,
        _assert_locked_test_render_batch_access_guard,
        _publish_locked_test_render_batch_intent,
        _assert_model_free_locked_test_render_batch_result,
        _validate_locked_test_render_batch_receipt,
        run_locked_test_render_batch,
        _HISTORICAL_ENSURE_LOCKED_TEST_RENDER_BATCH_EXECUTION_LOCK,
    )
    return stable_sha256(
        {
            "contract": LOCKED_TEST_RENDER_BATCH_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "sealed_full_render_implementation_sha256": (
                SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
            ),
            "sealed_full_render_execution_lock_sha256": (
                SEALED_FULL_RENDER_EXECUTION_LOCK_SHA256
            ),
            "sealed_gt_scout_implementation_sha256": (
                gt_scout_implementation_sha256()
            ),
        }
    )


def ensure_locked_test_render_batch_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    source_locks = _locked_test_render_batch_source_locks(config)
    expected = {
        "schema_version": 1,
        "contract": LOCKED_TEST_RENDER_BATCH_CONTRACT,
        "status": "SEALED_LOCKED_TEST_RENDER_BATCH_MODEL_FREE_SYNTHETIC_ONLY",
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan["pair_roster_sha256"],
        "locked_test_render_batch_implementation_sha256": (
            locked_test_render_batch_implementation_sha256()
        ),
        **source_locks,
        "target_scope": "explicit_contiguous_canonical_locked_test_slots_only",
        "calibration_render_completion_required": True,
        "new_pair_limit_required": True,
        "durable_intent_required": True,
        "render_and_machine_audit_only": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
        "outcome_inputs_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    path = (
        full_paths(config)["synthetic"]
        / "planning/locked_test_render_batch_execution_lock_v1.json"
    )
    if path.exists():
        if load_json(path) != expected:
            raise ContractError("Locked-test render batch execution lock changed")
    else:
        _write_json_once_atomically(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


_HISTORICAL_ENSURE_LOCKED_TEST_RENDER_BATCH_EXECUTION_LOCK = (
    ensure_locked_test_render_batch_execution_lock
)


def _dispatch_locked_test_render_batch_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_roster_extension_config(config):
        return _HISTORICAL_ENSURE_LOCKED_TEST_RENDER_BATCH_EXECUTION_LOCK(
            config_path, config, plan
        )
    lock = _extension_execution_lock(
        config,
        "locked_test_render_batch_execution_lock_extension_v1.json",
    )
    if (
        lock.get("locked_test_render_batch_implementation_sha256")
        != locked_test_render_batch_implementation_sha256()
        or lock.get("execution_lock_dispatch_sha256")
        != stable_sha256(
            inspect.getsource(_dispatch_locked_test_render_batch_execution_lock)
        )
        or lock.get("render_and_machine_audit_only") is not True
        or lock.get("model_access_allowed") is not False
        or lock.get("prediction_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
    ):
        raise ContractError("Roster extension locked-test batch lock changed")
    return lock


ensure_locked_test_render_batch_execution_lock = (
    _dispatch_locked_test_render_batch_execution_lock
)


def _validate_locked_test_zero_source_recovery_context(
    config: Mapping[str, Any],
    paths: Mapping[str, Path],
    rows: Sequence[Mapping[str, Any]],
    pair_id: str,
    batch_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    if SAFE_ID_RE.fullmatch(batch_id) is None:
        raise ContractError(f"Unsafe locked-test render batch ID: {batch_id}")
    by_id = {str(row["pair_id"]): row for row in rows}
    if pair_id not in by_id:
        raise ContractError("Locked-test recovery pair escaped the frozen roster")
    roster_row = dict(by_id[pair_id])
    if roster_row["protocol_split"] != "locked_test":
        raise ContractError("Locked-test recovery may never target calibration")

    full_root = paths["synthetic"]
    state = inspect_full_render_state(full_root, rows)
    _assert_locked_test_render_batch_access_guard(paths, rows, state)
    if pair_id not in state["pending_pair_ids"]:
        raise ContractError("Locked-test recovery pair is not pending")
    if state["pending_pair_ids"][0] != pair_id:
        raise ContractError(
            "Locked-test recovery must target the earliest pending canonical slot"
        )
    if (full_root / "pairs/locked_test" / pair_id).exists():
        raise ContractError("Locked-test recovery cannot target a published pair")

    batch_parent = full_root / "planning/locked_test_render_batches_v1"
    batch_root = batch_parent / batch_id
    _require_child(batch_root, batch_parent, "locked-test recovery batch")
    intent_path = batch_root / "batch_intent.json"
    if not intent_path.is_file():
        raise ContractError("Locked-test recovery requires an immutable batch intent")
    if (batch_root / "batch_receipt.json").exists():
        raise ContractError("Locked-test recovery cannot target a terminal batch")
    intent = load_json(intent_path)
    request = intent.get("request")
    valid = (
        isinstance(request, dict)
        and intent.get("status")
        == "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY"
        and intent.get("batch_id") == batch_id
        and intent.get("request_identity_sha256") == stable_sha256(request)
        and request.get("contract") == LOCKED_TEST_RENDER_BATCH_CONTRACT
        and request.get("protocol_split") == "locked_test"
        and pair_id in request.get("target_pair_ids", [])
        and request.get("render_and_machine_audit_only") is True
        and request.get("model_access_allowed") is False
        and request.get("prediction_access_allowed") is False
        and request.get("locked_test_outcome_access_allowed") is False
        and intent.get("locked_test_predictions_present_at_start") is False
        and intent.get("model_loaded") is False
        and intent.get("inference_calls") == 0
        and intent.get("outcome_inputs") == []
    )
    if not valid:
        raise ContractError("Locked-test recovery batch intent changed")
    return roster_row, intent, state, batch_root


def run_locked_test_gt_source_cardinality_recovery(
    config_path: Path,
    pair_id: str,
    *,
    candidate_index: int,
    batch_id: str,
) -> dict[str, Any]:
    """Commit one exact locked-test zero-source-weed rejection without outcomes."""
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    plan = validate_full_plan(config_path)
    preflight_receipt = preflight(config_path, scope="fixture")
    paths = full_paths(config)
    full_root = paths["synthetic"]
    rows = full_roster_rows(config)
    roster_row, intent, _, batch_root = (
        _validate_locked_test_zero_source_recovery_context(
            config, paths, rows, pair_id, batch_id
        )
    )
    candidates = roster_row["candidates"]
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise ContractError("Locked-test recovery candidate escaped the roster")
    candidate = candidates[candidate_index]

    recovery_root = (
        full_root / "planning/locked_test_gt_source_cardinality_recovery_v1"
    )
    destination = (
        recovery_root
        / "roster"
        / pair_id
        / f"candidate_{candidate_index:02d}"
    )
    docs_path = (
        paths["docs"]
        / "gt_scout_v1"
        / (
            "locked_test_source_cardinality_recovery_"
            f"{pair_id}_candidate_{candidate_index:02d}.json"
        )
    )
    if destination.exists():
        terminal_path = destination / "recovery_terminal_receipt.json"
        decision_path = destination / "decision_receipt.json"
        terminal = load_json(terminal_path)
        decision = load_json(decision_path)
        valid = (
            terminal.get("contract")
            == LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
            and terminal.get("status")
            == "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
            and terminal.get("protocol_split") == "locked_test"
            and terminal.get("batch_id") == batch_id
            and terminal.get("batch_intent_sha256")
            == sha256_file(batch_root / "batch_intent.json")
            and terminal.get("candidate_identity_sha256")
            == candidate["candidate_identity_sha256"]
            and terminal.get("recovery_implementation_sha256")
            == locked_test_gt_source_cardinality_recovery_implementation_sha256()
            and terminal.get("model_loaded") is False
            and terminal.get("inference_calls") == 0
            and terminal.get("locked_test_prediction_accessed") is False
            and terminal.get("locked_test_outcome_accessed") is False
            and terminal.get("outcome_inputs") == []
            and decision.get("rejection_reasons")
            == ["eligibility:source_weed_track_present"]
        )
        if not valid:
            raise ContractError("Existing locked-test recovery binding changed")
        commit = _commit_gt_scout_rejection(
            full_root, destination, roster_row, candidate, decision
        )
        _write_json_once_atomically(docs_path, terminal)
        return {
            "status": (
                "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_"
                "LOCKED_TEST_PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "pair_id": pair_id,
            "candidate_index": candidate_index,
            "batch_id": batch_id,
            "destination": str(destination),
            "recovery_terminal_receipt_sha256": sha256_file(terminal_path),
            "ledger_commit": commit,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    next_candidate = _next_gt_scout_candidate(full_root, roster_row)
    if int(next_candidate["candidate_index"]) != candidate_index:
        raise ContractError(
            "Locked-test recovery candidate is not the next canonical candidate"
        )
    recovery_root.mkdir(parents=True, exist_ok=True)
    staging = recovery_root / (
        f".partial-{pair_id}-candidate-{candidate_index:02d}-{uuid.uuid4().hex}"
    )
    _require_child(staging, recovery_root, "locked-test recovery staging")
    staging.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        asset_partition = load_json(full_root / "planning/asset_partition_v1.json")
        asset_role = asset_partition["roles"]["locked_test"]
        source_path = full_candidate_source_path(config, roster_row, candidate)
        derived = derive_full_native_scene_config(
            load_yaml(source_path), roster_row, candidate, asset_role, config
        )
        derived_path = staging / "scene_config.yaml"
        derived_path.write_text(
            yaml.safe_dump(derived, sort_keys=False), encoding="utf-8"
        )
        patch_path = staging / "bindings/gt_scout_scene.patch"
        patch_receipt = compose_gt_scout_patch(config, patch_path)
        scout_lock = ensure_gt_scout_execution_lock(
            config_path, config, plan, patch_receipt
        )
        recovery_lock = (
            ensure_locked_test_gt_source_cardinality_recovery_execution_lock(
                config_path, config, plan
            )
        )
        scene_root = staging / "source_scene"
        generation = run_cropcraft_scene(
            derived_path, scene_root, patch_path, config
        )
        capture = _validate_gt_scout_capture_receipt(
            scene_root, roster_row, candidate
        )
        used_assets = validate_full_used_assets(scene_root, asset_role)
        audit = _audit_zero_source_weed_failure(scene_root, config)
        decision = {
            "schema_version": 1,
            "contract": GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "locked_test_recovery_contract": (
                LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
            ),
            "status": "REJECT_FROZEN_GT_ONLY_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "protocol_split": "locked_test",
            "rejectable_by_scout": True,
            "rejection_reasons": ["eligibility:source_weed_track_present"],
            "source_cardinality_checks": {
                "source_crop_track_present": True,
                "source_weed_track_present": False,
            },
            "decision_contract_sha256": gt_scout_decision_contract(config)[
                "contract_sha256"
            ],
            "full_render_still_required_for_acceptance": True,
            "recovery_has_acceptance_authority": False,
            "model_or_outcome_inputs_used": False,
            "registered_targets_used": False,
            "locked_test_prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "synthetic_only": True,
        }
        write_json(staging / "source_cardinality_audit.json", audit)
        write_json(staging / "decision_receipt.json", decision)

        evidence_root = staging / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=False)
        retained: dict[str, str] = {}
        for source, name in (
            (scene_root / "generation_receipt.json", "generation_receipt.json"),
            (scene_root / "gt_scout_capture_receipt.json", "capture_receipt.json"),
            (
                scene_root / "botanical_ground_truth/source_objects.json",
                "source_objects.json",
            ),
            (
                scene_root / "botanical_ground_truth/track_registry.json",
                "track_registry.json",
            ),
            (
                scene_root / "botanical_ground_truth/tracks.jsonl",
                "tracks.jsonl",
            ),
            (staging / "source_scene.runner.log", "cropcraft_runner.log"),
        ):
            if not source.is_file():
                raise ContractError(
                    "Locked-test source-cardinality retained evidence is missing: "
                    f"{source}"
                )
            target = evidence_root / name
            shutil.copy2(source, target)
            retained[name] = sha256_file(target)
        bulk_bytes_before_cleanup = _tree_bytes(scene_root)
        shutil.rmtree(scene_root)
        (staging / "source_scene.runner.log").unlink()
        cleanup = {
            "bulk_bytes_removed": bulk_bytes_before_cleanup,
            "source_scene_removed": True,
            "retained_receipts_and_log": retained,
            "bulk_payload_retained": False,
            "bounded_to_locked_test_recovery_staging": True,
        }
        write_json(staging / "bounded_cleanup_receipt.json", cleanup)
        inventory = artifact_inventory(staging)
        if any("prediction" in row["path"].lower() for row in inventory):
            raise ContractError("Prediction output exists in locked-test recovery")
        terminal = {
            "schema_version": 1,
            "contract": LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "status": (
                "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "pair_id": pair_id,
            "protocol_split": "locked_test",
            "evaluator_split": roster_row["evaluator_split"],
            "pair_slot_identity_sha256": roster_row[
                "pair_slot_identity_sha256"
            ],
            "candidate_index": candidate_index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "candidate_seeds": copy.deepcopy(candidate["seeds"]),
            "all_five_seed_bindings_exact": set(capture["seed_bindings"])
            == set(candidate["seeds"]),
            "source_template": copy.deepcopy(candidate["source_template"]),
            "source_template_sha256_exact": sha256_file(source_path)
            == candidate["source_template"]["sha256"],
            "role_asset_validation": used_assets,
            "source_cardinality_audit": audit,
            "decision": decision,
            "generation": generation,
            "composed_patch": patch_receipt,
            "batch_id": batch_id,
            "batch_request_identity_sha256": intent[
                "request_identity_sha256"
            ],
            "batch_intent_sha256": sha256_file(
                batch_root / "batch_intent.json"
            ),
            "sealed_gt_scout_execution_lock_sha256": scout_lock["sha256"],
            "sealed_full_render_execution_lock_sha256": scout_lock[
                "sealed_full_render_execution_lock_sha256"
            ],
            "recovery_execution_lock_sha256": recovery_lock["sha256"],
            "recovery_implementation_sha256": recovery_lock[
                "recovery_implementation_sha256"
            ],
            "preflight": {
                "scope": preflight_receipt["scope"],
                "capacity": preflight_receipt["capacity"],
                "gpu": preflight_receipt["gpu"],
                "checkpoint_hash_verified_as_source_lock": True,
                "checkpoint_loaded": False,
            },
            "bounded_cleanup": cleanup,
            "inventory_sha256": stable_sha256(inventory),
            "inventory_file_count_before_terminal_receipt": len(inventory),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "model_loaded": False,
            "inference_calls": 0,
            "locked_test_prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "outcome_inputs": [],
            "acceptance_authority": "none",
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        write_json(staging / "recovery_terminal_receipt.json", terminal)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    commit = _commit_gt_scout_rejection(
        full_root, destination, roster_row, candidate, decision
    )
    terminal_path = destination / "recovery_terminal_receipt.json"
    _write_json_once_atomically(docs_path, load_json(terminal_path))
    return {
        "status": terminal["status"],
        "pair_id": pair_id,
        "candidate_index": candidate_index,
        "batch_id": batch_id,
        "destination": str(destination),
        "recovery_terminal_receipt_sha256": sha256_file(terminal_path),
        "rejection_reasons": decision["rejection_reasons"],
        "ledger_commit": commit,
        "elapsed_wall_seconds": terminal["elapsed_wall_seconds"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def locked_test_gt_source_cardinality_recovery_implementation_sha256() -> str:
    functions = (
        _validate_locked_test_zero_source_recovery_context,
        run_locked_test_gt_source_cardinality_recovery,
        _HISTORICAL_ENSURE_LOCKED_TEST_RECOVERY_EXECUTION_LOCK,
    )
    return stable_sha256(
        {
            "contract": LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "exact_failure_auditor_source_sha256": stable_sha256(
                inspect.getsource(_audit_zero_source_weed_failure)
            ),
            "legacy_recovery_implementation_sha256": (
                gt_source_cardinality_recovery_implementation_sha256()
            ),
            "sealed_gt_scout_implementation_sha256": (
                gt_scout_implementation_sha256()
            ),
            "sealed_full_render_implementation_sha256": (
                SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
            ),
            "locked_test_render_batch_implementation_sha256": (
                locked_test_render_batch_implementation_sha256()
            ),
        }
    )


def ensure_locked_test_gt_source_cardinality_recovery_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    worker_locks = _locked_test_render_batch_source_locks(config)
    batch_lock = ensure_locked_test_render_batch_execution_lock(
        config_path, config, plan
    )
    expected = {
        "schema_version": 1,
        "contract": LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "status": (
            "SEALED_LOCKED_TEST_ZERO_SOURCE_WEED_RECOVERY_"
            "MODEL_FREE_SYNTHETIC_ONLY"
        ),
        "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
        "execution_config_sha256": sha256_file(config_path),
        "historical_plan_roster_sha256": plan["pair_roster_sha256"],
        "sealed_full_render_execution_lock_sha256": worker_locks[
            "sealed_full_render_execution_lock_sha256"
        ],
        "sealed_full_render_implementation_sha256": worker_locks[
            "sealed_full_render_implementation_sha256"
        ],
        "sealed_gt_scout_execution_lock_sha256": worker_locks[
            "gt_scout_execution_lock_sha256"
        ],
        "sealed_gt_scout_implementation_sha256": worker_locks[
            "gt_scout_implementation_sha256"
        ],
        "locked_test_render_batch_execution_lock_sha256": batch_lock[
            "sha256"
        ],
        "locked_test_render_batch_implementation_sha256": batch_lock[
            "locked_test_render_batch_implementation_sha256"
        ],
        "recovery_implementation_sha256": (
            locked_test_gt_source_cardinality_recovery_implementation_sha256()
        ),
        "target_scope": (
            "earliest_pending_locked_test_candidate_in_active_batch_only"
        ),
        "rejection_authority": (
            "exact_locked_validator_zero_source_weed_failure_only"
        ),
        "acceptance_authority": "none",
        "immutable_batch_intent_required": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
        "outcome_inputs_allowed": False,
        "registered_targets_allowed": False,
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    path = (
        full_paths(config)["synthetic"]
        / (
            "planning/locked_test_gt_source_cardinality_"
            "recovery_execution_lock_v1.json"
        )
    )
    if path.exists():
        if load_json(path) != expected:
            raise ContractError("Locked-test source-cardinality recovery lock changed")
    else:
        _write_json_once_atomically(path, expected)
    return {"path": display_path(path), "sha256": sha256_file(path), **expected}


_HISTORICAL_ENSURE_LOCKED_TEST_RECOVERY_EXECUTION_LOCK = (
    ensure_locked_test_gt_source_cardinality_recovery_execution_lock
)


def _dispatch_locked_test_recovery_execution_lock(
    config_path: Path,
    config: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_roster_extension_config(config):
        return _HISTORICAL_ENSURE_LOCKED_TEST_RECOVERY_EXECUTION_LOCK(
            config_path, config, plan
        )
    lock = _extension_execution_lock(
        config,
        "locked_test_recovery_execution_lock_extension_v1.json",
    )
    if (
        lock.get("recovery_implementation_sha256")
        != locked_test_gt_source_cardinality_recovery_implementation_sha256()
        or lock.get("execution_lock_dispatch_sha256")
        != stable_sha256(
            inspect.getsource(_dispatch_locked_test_recovery_execution_lock)
        )
        or lock.get("rejection_authority")
        != "exact_locked_validator_zero_source_weed_failure_only"
        or lock.get("acceptance_authority") != "none"
        or lock.get("model_access_allowed") is not False
        or lock.get("prediction_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
    ):
        raise ContractError("Roster extension recovery lock changed")
    return lock


ensure_locked_test_gt_source_cardinality_recovery_execution_lock = (
    _dispatch_locked_test_recovery_execution_lock
)


def build_execution_inference_config(
    destination: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    base_path = resolve_path(
        str(config["source_locks"]["simulation_evaluator_config"]["path"])
    )
    result = load_yaml(base_path)
    native = config["native_contract"]
    inference = config["inference"]
    result["source"]["mode"] = "external_botanical_native_manifest"
    result["source"]["v12_smoke"]["gsd_mm_per_px"] = float(
        native["ground_fov_mm"]
    ) / float(native["width_px"])
    result["source"]["v12_smoke"]["limitation"] = (
        "Source-object botanical IDs are emitted before rendering by the admitted "
        "CropCraft botanical patch; evidence remains synthetic and non-deployment."
    )
    result["inference"]["image_size_px"] = int(inference["image_size_px"])
    result["inference"]["confidence_floor"] = float(inference["confidence_floor"])
    result["inference"]["nms_iou"] = float(inference["nms_iou"])
    result["inference"]["device"] = int(config["runtime"]["cuda_device"])
    result["inference"]["half"] = bool(inference["half"])
    result["inference"]["deterministic"] = bool(inference["deterministic"])
    result["inference"]["seed"] = int(inference["seed"])
    result["tracking"]["association_min_mask_iou"] = float(
        inference["tracker_association_min_mask_iou"]
    )
    result["tracking"]["association_max_centroid_distance_px"] = float(
        inference["tracker_association_max_centroid_distance_px"]
    )
    result["tracking"]["maximum_frame_gap"] = int(
        inference["tracker_maximum_frame_gap"]
    )
    result["video"]["fps"] = float(inference["overlay_fps"])
    result["video"]["codec"] = str(inference["overlay_codec"])
    result["outputs"]["run_root"] = str(config["outputs"]["run_root"])
    result["outputs"]["docs_root"] = str(config["outputs"]["results_root"])
    result["outputs"]["default_run_name"] = str(config["outputs"]["fixture_name"])
    result["claims"] = list(config["claims"])
    destination.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    return result


def artifact_inventory(root: Path, *, excluded: set[str] | None = None) -> list[dict[str, Any]]:
    omitted = set() if excluded is None else set(excluded)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in omitted:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def fixture_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    name = str(config["outputs"]["fixture_name"])
    return {
        "synthetic": resolve_path(str(config["outputs"]["synthetic_root"])) / name,
        "run": resolve_path(str(config["outputs"]["run_root"])) / name,
        "docs": resolve_path(str(config["outputs"]["results_root"])) / name,
    }


def render_fixture(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    paths = fixture_paths(config)
    if any(path.exists() for path in paths.values()):
        existing = [str(path) for path in paths.values() if path.exists()]
        raise ContractError(f"Fixture output already exists: {existing}")
    final_root = paths["synthetic"]
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = final_root.parent / f".{final_root.name}.partial-{uuid.uuid4().hex}"
    started = time.perf_counter()
    staging.mkdir(parents=False, exist_ok=False)
    try:
        preflight_receipt = preflight(config_path, scope="fixture")
        write_json(staging / "preflight_receipt.json", preflight_receipt)
        patch_receipt = compose_scene_patch(
            config, staging / "bindings/0006-surface-plus-0002-botanical.patch"
        )
        combined_patch = staging / "bindings/0006-surface-plus-0002-botanical.patch"
        all_sequences: list[dict[str, Any]] = []
        pair_receipts: list[dict[str, Any]] = []
        scene_receipts: list[dict[str, Any]] = []
        scene_validations: list[dict[str, Any]] = []
        for scene in config["fixture"]["scenes"]:
            pair_id = str(scene["pair_id"])
            print(f"fixture-render start {pair_id}", flush=True)
            source_spec = config["source_locks"][str(scene["source_lock"])]
            source_path = resolve_path(str(source_spec["path"]))
            base = load_yaml(source_path)
            derived = derive_native_scene_config(base, scene, config)
            derived_path = staging / "scene_configs" / f"{pair_id}.yaml"
            derived_path.parent.mkdir(parents=True, exist_ok=True)
            derived_path.write_text(
                yaml.safe_dump(derived, sort_keys=False), encoding="utf-8"
            )
            scene_root = staging / "source_scenes" / pair_id
            generation = run_cropcraft_scene(
                derived_path, scene_root, combined_patch, config
            )
            validation = validate_botanical_scene(scene_root, config)
            sequences, pair_receipt = build_pair_package(
                scene_root,
                staging / "pairs" / str(scene["split"]) / pair_id,
                scene,
                config,
                staging,
            )
            generation["pair_id"] = pair_id
            generation["derived_scene_config"] = {
                "path": _relative(derived_path, staging),
                "sha256": sha256_file(derived_path),
            }
            scene_receipts.append(generation)
            scene_validations.append({"pair_id": pair_id, "validation": validation})
            pair_receipts.append(pair_receipt)
            all_sequences.extend(sequences)
            print(f"fixture-render complete {pair_id}", flush=True)

        inference_config_path = staging / "inference_config.yaml"
        build_execution_inference_config(inference_config_path, config)
        manifest = {
            "schema_version": 1,
            "contract": SEQUENCE_CONTRACT,
            "dataset_id": "spot_spray_simulation_video_ab_execution_v1_native_fixture",
            "evidence_scope": "synthetic_diagnostic_only",
            "declared_splits": {"calibration": "calibration", "locked_test": "test"},
            "conditions": ["ideal", "degraded"],
            "provenance": {
                "protocol_sha256": config["source_locks"]["protocol"]["sha256"],
                "botanical_validation_receipt_sha256": config["source_locks"][
                    "botanical_validation_receipt"
                ]["sha256"],
                "botanical_patch_sha256": config["source_locks"]["botanical_patch"][
                    "sha256"
                ],
                "paired_validation_receipt_sha256": config["source_locks"][
                    "paired_validation_receipt"
                ]["sha256"],
                "paired_renderer_sha256": config["source_locks"]["paired_renderer"][
                    "sha256"
                ],
                "simulation_evaluator_sha256": config["source_locks"][
                    "simulation_evaluator"
                ]["sha256"],
                "composed_scene_patch_sha256": patch_receipt["sha256"],
            },
            "derivation": {
                "type": "native_2048_botanical_source_object_matched_pair_fixture",
                "frames_per_arm": 30,
                "frame_rate_hz": 15,
                "outcome_inputs_used": [],
            },
            "sequences": all_sequences,
        }
        manifest_path = staging / "sequence_manifest.json"
        write_json(manifest_path, manifest)

        evaluator = _import_binding("scripts.evaluate_spot_spray_simulation_video_v1")
        evaluator_config = evaluator.load_config(inference_config_path)
        _, manifest_validation = evaluator.load_sequence_manifest(
            manifest_path, evaluator_config
        )
        if manifest_validation["matched_pair_count"] != 2:
            raise ContractError("Fixture manifest did not validate exactly two pairs")

        pair_manifest_rows = [
            {
                "pair_id": row["pair_id"],
                "split": row["split"],
                "canonical_gt_sha256": row["canonical_gt_sha256"],
                "source_scene_graph_identity_sha256": row[
                    "source_scene_graph_identity_sha256"
                ],
                "travel_speed_m_s": row["travel_speed_m_s"],
                "scene_profile": row["scene_profile"],
                "degraded_motion_path": row["degraded_motion_path"],
            }
            for row in pair_receipts
        ]
        pair_manifest_path = staging / "pair_manifest_v1.jsonl"
        write_jsonl(pair_manifest_path, pair_manifest_rows)
        output_scan = artifact_inventory(staging)
        release_lock = {
            "schema_version": 1,
            "contract": "spot_spray_simulation_video_ab_release_lock_v1",
            "status": "SEALED_NO_MODEL_OUTPUTS_SYNTHETIC_ONLY",
            "protocol_config_sha256": config["source_locks"]["protocol"]["sha256"],
            "execution_config_sha256": sha256_file(config_path),
            "execution_script_sha256": sha256_file(Path(__file__).resolve()),
            "source_lock_receipt_sha256": preflight_receipt["sources"][
                "execution_locks_sha256"
            ],
            "exact_renderer_and_environment_identity": patch_receipt,
            "exact_inference_and_tracker_identity": {
                "evaluator_sha256": config["source_locks"]["simulation_evaluator"][
                    "sha256"
                ],
                "resolved_config_sha256": sha256_file(inference_config_path),
            },
            "pair_manifest_sha256": sha256_file(pair_manifest_path),
            "sequence_manifest_sha256": sha256_file(manifest_path),
            "split_pair_counts": {"calibration": 1, "test": 1},
            "frame_count_per_arm": 30,
            "gt_identity_digest": stable_sha256(
                sorted(row["canonical_gt_sha256"] for row in pair_receipts)
            ),
            "ideal_and_degraded_image_set_digests": {
                condition: stable_sha256(
                    sorted(
                        frame["image_sha256"]
                        for sequence in all_sequences
                        if sequence["condition"] == condition
                        for frame in sequence["frames"]
                    )
                )
                for condition in ("ideal", "degraded")
            },
            "preoutcome_audit_sha256": stable_sha256(pair_receipts),
            "calibration_review_manifest_sha256": None,
            "locked_test_access_state": "sealed_no_prediction",
            "model_outputs_present_false": not any(
                "prediction" in row["path"] for row in output_scan
            ),
            "descriptive_targets_used": False,
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        if release_lock["model_outputs_present_false"] is not True:
            raise ContractError("Model outputs exist before release lock")
        release_lock_path = staging / "release_lock_v1.json"
        write_json(release_lock_path, release_lock)
        render_receipt = {
            "schema_version": 1,
            "contract": CONTRACT,
            "status": "PASS_NATIVE_FIXTURE_RENDER_SYNTHETIC_ONLY",
            "config": {
                "path": display_path(config_path),
                "sha256": sha256_file(config_path),
            },
            "preflight_receipt_sha256": sha256_file(
                staging / "preflight_receipt.json"
            ),
            "patch_binding": patch_receipt,
            "scenes": scene_receipts,
            "scene_validations": scene_validations,
            "pairs": pair_receipts,
            "sequence_manifest": {
                "path": "sequence_manifest.json",
                "sha256": sha256_file(manifest_path),
                "validation": manifest_validation,
            },
            "release_lock": {
                "path": "release_lock_v1.json",
                "sha256": sha256_file(release_lock_path),
            },
            "elapsed_wall_seconds": time.perf_counter() - started,
            "bytes_before_receipt": sum(
                row["bytes"] for row in artifact_inventory(staging)
            ),
            "synthetic_only": True,
            "field_product_or_chemical_go": False,
        }
        render_receipt_path = staging / "render_receipt.json"
        write_json(render_receipt_path, render_receipt)
        staging.replace(final_root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    docs = paths["docs"]
    docs.mkdir(parents=True, exist_ok=False)
    final_receipt = load_json(final_root / "render_receipt.json")
    write_json(docs / "render_receipt.json", final_receipt)
    write_json(docs / "preflight_receipt.json", load_json(final_root / "preflight_receipt.json"))
    return {
        "status": final_receipt["status"],
        "fixture_root": str(final_root),
        "docs_root": str(docs),
        "sequence_manifest": str(final_root / "sequence_manifest.json"),
        "release_lock_sha256": sha256_file(final_root / "release_lock_v1.json"),
        "elapsed_wall_seconds": final_receipt["elapsed_wall_seconds"],
    }


def _prediction_metadata(
    *,
    evaluator: Any,
    rows: Sequence[Mapping[str, Any]],
    condition: str,
    split: str,
    checkpoint_sha256: str,
    manifest_sha256: str,
    config_sha256: str,
    selected_threshold: float | None,
) -> list[dict[str, Any]]:
    return [
        {
            "record_type": "prediction_metadata",
            "schema_version": 1,
            "contract": "spot_spray_simulation_video_predictions_v1",
            "condition": condition,
            "split": split,
            "checkpoint_sha256": checkpoint_sha256,
            "sequence_manifest_sha256": manifest_sha256,
            "config_sha256": config_sha256,
            "selected_shared_threshold": selected_threshold,
        },
        *[dict(row) for row in rows],
    ]


def _condition_map(
    predictions: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = defaultdict(dict)
    for sequence_id, prediction in predictions.items():
        output[prediction.sequence.condition][sequence_id] = prediction
    return dict(output)


def run_fixture_inference(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = load_config(config_path)
    verify_all_sources(config)
    paths = fixture_paths(config)
    fixture_root, final_run, docs = paths["synthetic"], paths["run"], paths["docs"]
    if not fixture_root.is_dir():
        raise ContractError("Render fixture must exist before inference")
    if final_run.exists():
        raise ContractError(f"Fixture inference output already exists: {final_run}")
    inference_docs = docs / "inference"
    if inference_docs.exists():
        raise ContractError(f"Fixture inference docs already exist: {inference_docs}")
    release_lock_path = fixture_root / "release_lock_v1.json"
    release_lock = load_json(release_lock_path)
    if release_lock.get("model_outputs_present_false") is not True:
        raise ContractError("Release lock does not prove model outputs absent")
    forbidden_preexisting = list(fixture_root.rglob("*test*prediction*"))
    if forbidden_preexisting:
        raise ContractError(f"Test predictions predate threshold lock: {forbidden_preexisting}")

    evaluator = _import_binding("scripts.evaluate_spot_spray_simulation_video_v1")
    evaluator_config_path = fixture_root / "inference_config.yaml"
    evaluator_config = evaluator.load_config(evaluator_config_path)
    manifest_path = fixture_root / "sequence_manifest.json"
    sequences, manifest_metadata = evaluator.load_sequence_manifest(
        manifest_path, evaluator_config
    )
    calibration = [row for row in sequences if row.split == "calibration"]
    test = [row for row in sequences if row.split == "test"]
    degraded_calibration = [row for row in calibration if row.condition == "degraded"]
    ideal_calibration = [row for row in calibration if row.condition == "ideal"]
    if len(degraded_calibration) != 1 or len(ideal_calibration) != 1 or len(test) != 2:
        raise ContractError("Fixture inference split/condition allocation changed")

    final_run.parent.mkdir(parents=True, exist_ok=True)
    staging = final_run.parent / f".{final_run.name}.partial-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    guard = ExecutionAccessGuard()
    guard.seal_release(
        sha256_file(release_lock_path), model_outputs_present=False
    )
    evaluator_ledger = evaluator.AccessLedger("calibration", "test")
    started = time.perf_counter()
    test_inference_started = False
    try:
        deterministic = evaluator.configure_determinism(
            int(evaluator_config["inference"]["seed"])
        )
        checkpoint_path = resolve_path(
            str(config["source_locks"]["selected_checkpoint"]["path"])
        )
        model, checkpoint_metadata = evaluator.load_verified_model(
            checkpoint_path,
            str(config["source_locks"]["selected_checkpoint"]["sha256"]),
            task="segment",
        )
        prediction_root = staging / "prediction_masks"
        for sequence in degraded_calibration:
            guard.record_calibration_inference(sequence.condition, sequence.sequence_id)
        degraded_predictions, degraded_rows = evaluator.predict_sequences(
            model,
            degraded_calibration,
            evaluator_config,
            evaluator_ledger,
            prediction_root,
        )
        curve, selection = evaluator.calibration_curve(
            degraded_predictions, evaluator_config
        )
        selection["source_conditions"] = ["degraded"]
        selection["source_arm"] = "degraded"
        threshold = float(selection["threshold"])
        degraded_cal_path = staging / "degraded_calibration_predictions_v1.jsonl"
        write_jsonl(
            degraded_cal_path,
            _prediction_metadata(
                evaluator=evaluator,
                rows=degraded_rows,
                condition="degraded",
                split="calibration",
                checkpoint_sha256=checkpoint_metadata["sha256"],
                manifest_sha256=manifest_metadata["sha256"],
                config_sha256=sha256_file(evaluator_config_path),
                selected_threshold=threshold,
            ),
        )
        test_prediction_paths = [
            staging / "ideal_test_predictions_v1.jsonl",
            staging / "degraded_test_predictions_v1.jsonl",
        ]
        test_predictions_present = any(path.exists() for path in test_prediction_paths)
        guard.seal_threshold(
            threshold,
            source_condition="degraded",
            test_predictions_present=test_predictions_present,
        )
        evaluator_ledger.freeze_threshold(threshold)
        threshold_lock = {
            "schema_version": 1,
            "contract": "spot_spray_simulation_video_ab_threshold_lock_v1",
            "release_lock_sha256": sha256_file(release_lock_path),
            "checkpoint_sha256": checkpoint_metadata["sha256"],
            "inference_and_tracker_config_sha256": sha256_file(evaluator_config_path),
            "degraded_calibration_prediction_sha256": sha256_file(degraded_cal_path),
            "action_config_sha256": config["source_locks"]["frozen_action_contract"][
                "sha256"
            ],
            "action_evaluator_sha256": config["source_locks"]["frozen_action_evaluator"][
                "sha256"
            ],
            "selected_threshold_and_feasibility": selection,
            "calibration_sufficient_counts": {
                "fixture_pair_count": 1,
                "full_protocol_minimum_not_claimed": True,
            },
            "test_predictions_present_false": not test_predictions_present,
            "source_split": "calibration",
            "source_arm": "degraded",
            "shared_for_both_test_arms": True,
        }
        threshold_lock_path = staging / "threshold_lock_v1.json"
        write_json(threshold_lock_path, threshold_lock)

        for sequence in ideal_calibration:
            guard.record_calibration_inference(sequence.condition, sequence.sequence_id)
        ideal_cal_predictions, ideal_cal_rows = evaluator.predict_sequences(
            model,
            ideal_calibration,
            evaluator_config,
            evaluator_ledger,
            prediction_root,
        )
        ideal_cal_path = staging / "ideal_calibration_predictions_v1.jsonl"
        write_jsonl(
            ideal_cal_path,
            _prediction_metadata(
                evaluator=evaluator,
                rows=ideal_cal_rows,
                condition="ideal",
                split="calibration",
                checkpoint_sha256=checkpoint_metadata["sha256"],
                manifest_sha256=manifest_metadata["sha256"],
                config_sha256=sha256_file(evaluator_config_path),
                selected_threshold=threshold,
            ),
        )

        for sequence in sorted(test, key=lambda row: (row.pair_id, row.condition)):
            guard.record_test_inference(sequence.condition, sequence.sequence_id)
        test_inference_started = True
        test_predictions, test_rows = evaluator.predict_sequences(
            model,
            test,
            evaluator_config,
            evaluator_ledger,
            prediction_root,
        )
        test_rows_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in test_rows:
            test_rows_by_condition[str(row["condition"])].append(row)
        for condition in ("ideal", "degraded"):
            path = staging / f"{condition}_test_predictions_v1.jsonl"
            write_jsonl(
                path,
                _prediction_metadata(
                    evaluator=evaluator,
                    rows=test_rows_by_condition[condition],
                    condition=condition,
                    split="test",
                    checkpoint_sha256=checkpoint_metadata["sha256"],
                    manifest_sha256=manifest_metadata["sha256"],
                    config_sha256=sha256_file(evaluator_config_path),
                    selected_threshold=threshold,
                ),
            )

        calibration_by_condition = {
            "degraded": degraded_predictions,
            "ideal": ideal_cal_predictions,
        }
        calibration_results = {
            condition: evaluator.evaluate_prediction_set(
                predictions,
                evaluator_config,
                threshold,
                include_uncertainty=True,
            )
            for condition, predictions in calibration_by_condition.items()
        }
        evaluator_ledger.begin_locked_test_evaluation()
        guard.begin_locked_test_evaluation()
        test_by_condition = _condition_map(test_predictions)
        test_results = {
            condition: evaluator.evaluate_prediction_set(
                test_by_condition[condition],
                evaluator_config,
                threshold,
                include_uncertainty=True,
            )
            for condition in ("ideal", "degraded")
        }
        deltas = evaluator.paired_condition_deltas(
            test_results, test_by_condition, evaluator_config
        )
        target_assessment = evaluator.assess_descriptive_targets(
            test_results, evaluator_config
        )
        evaluator_ledger.finish()
        guard.finish()
        videos = evaluator.render_overlay_videos(
            test_by_condition,
            test_results,
            threshold,
            evaluator_config,
            staging / "videos",
        )
        ffmpeg = resolve_path(str(config["source_locks"]["ffmpeg"]["path"]))
        ffprobe = resolve_path(str(config["source_locks"]["ffprobe"]["path"]))
        overlay_side_by_side = staging / "videos/locked_test_overlay_side_by_side.mp4"
        create_side_by_side_video(
            ffmpeg,
            staging / "videos/ideal_locked_test_overlay.mp4",
            staging / "videos/degraded_locked_test_overlay.mp4",
            overlay_side_by_side,
        )
        renderer = _import_binding("scripts.build_spot_spray_simulation_video_pairs_v1")
        side_probe = renderer.probe_video(ffprobe, overlay_side_by_side)
        if side_probe["decoded_frame_count"] != 30:
            raise ContractError("Side-by-side overlay is not readable at exactly 30 frames")
        videos["side_by_side"] = side_probe

        runtime = evaluator.runtime_summary(
            [degraded_predictions, ideal_cal_predictions, test_predictions]
        )
        metrics = {
            "schema_version": 1,
            "contract": CONTRACT,
            "status": "PASS_NATIVE_FIXTURE_INFERENCE_SYNTHETIC_ONLY",
            "checkpoint": checkpoint_metadata,
            "sequence_manifest": manifest_metadata,
            "release_lock_sha256": sha256_file(release_lock_path),
            "threshold_lock_sha256": sha256_file(threshold_lock_path),
            "determinism": deterministic,
            "calibration": {
                "sole_threshold_source": "degraded_calibration",
                "curve": curve,
                "selection": selection,
                "conditions_at_selected_threshold": calibration_results,
                "ideal_used_for_selection": False,
                "test_accessed_during_selection": False,
            },
            "locked_test": {
                "evaluation_count": 1,
                "shared_threshold": threshold,
                "conditions": test_results,
                "paired_deltas": deltas,
                "descriptive_target_assessment": target_assessment,
            },
            "runtime": runtime,
            "videos": videos,
            "access_guard": guard.receipt(),
            "evaluator_access_ledger": evaluator_ledger.receipt(),
            "native_inference_binding": {
                "input_dimensions_px": [2048, 2048],
                "image_size_px": int(evaluator_config["inference"]["image_size_px"]),
                "full_frame_resize_requested": False,
                "prediction_masks_native_shape_required": True,
                "adapter_status": "full_frame_native_2048_fixture_path",
                "full_protocol_tiled_halo_preflight_deferred": True,
            },
            "decision": {
                "fixture_only_not_full_benchmark": True,
                "ideal_track_f1_reaches_0_97": target_assessment["ideal"][
                    "reaches_minimum"
                ],
                "degraded_track_f1_within_0_70_to_0_80": target_assessment[
                    "degraded"
                ]["within_near_range"],
                "descriptive_targets_used_for_tuning": False,
                "field_product_or_chemical_go": False,
            },
            "claim_boundary": copy.deepcopy(config["evidence_policy"]),
        }
        metrics_path = staging / "metrics.json"
        write_json(metrics_path, metrics)
        receipt = {
            "schema_version": 1,
            "contract": CONTRACT,
            "status": metrics["status"],
            "checkpoint_sha256": checkpoint_metadata["sha256"],
            "selected_shared_threshold": threshold,
            "locked_test_evaluation_count": 1,
            "test_accessed_before_threshold_lock": False,
            "metrics_sha256": sha256_file(metrics_path),
            "threshold_lock_sha256": sha256_file(threshold_lock_path),
            "access_guard": guard.receipt(),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "artifacts": artifact_inventory(staging, excluded={"run_receipt.json"}),
            "decision": metrics["decision"],
        }
        receipt_path = staging / "run_receipt.json"
        write_json(receipt_path, receipt)
        staging.replace(final_run)
    except Exception as error:
        if staging.exists():
            if test_inference_started:
                write_json(
                    staging / "INVALID_FAIL_CLOSED.json",
                    {
                        "status": "SIM_AB_INVALID_FAIL_CLOSED",
                        "reason": str(error),
                        "test_inference_started": True,
                        "rerun_under_same_v1_lock_allowed": False,
                        "access_guard": guard.receipt(),
                    },
                )
                invalid = staging.parent / f"{staging.name}.invalid"
                staging.replace(invalid)
            else:
                shutil.rmtree(staging)
        raise

    inference_docs.mkdir(parents=True, exist_ok=False)
    final_metrics = load_json(final_run / "metrics.json")
    final_receipt = load_json(final_run / "run_receipt.json")
    write_json(inference_docs / "metrics.json", final_metrics)
    write_json(inference_docs / "run_receipt.json", final_receipt)
    readme = [
        "# Native fixture inference",
        "",
        "Status: **PASS_NATIVE_FIXTURE_INFERENCE_SYNTHETIC_ONLY**",
        "",
        "This is a two-pair integration fixture, not the 32/64 locked benchmark.",
        f"Shared degraded-calibration threshold: `{final_receipt['selected_shared_threshold']:.2f}`.",
        "Locked-test metric evaluation count: `1`.",
        "The ideal/degraded references were not used for tuning.",
        "No field, product, dry-marker, or chemical GO is allowed.",
        "",
    ]
    (inference_docs / "README.md").write_text("\n".join(readme), encoding="utf-8")
    return {
        "status": final_receipt["status"],
        "run_root": str(final_run),
        "metrics": str(final_run / "metrics.json"),
        "run_receipt": str(final_run / "run_receipt.json"),
        "selected_shared_threshold": final_receipt["selected_shared_threshold"],
        "locked_test_evaluation_count": final_receipt[
            "locked_test_evaluation_count"
        ],
        "elapsed_wall_seconds": final_receipt["elapsed_wall_seconds"],
    }


def validate_fixture(config_path: Path, *, require_inference: bool) -> dict[str, Any]:
    config = load_config(config_path)
    verify_all_sources(config)
    paths = fixture_paths(config)
    fixture_root = paths["synthetic"]
    if not fixture_root.is_dir():
        raise ContractError("Fixture render output is missing")
    render_receipt = load_json(fixture_root / "render_receipt.json")
    if render_receipt.get("status") != "PASS_NATIVE_FIXTURE_RENDER_SYNTHETIC_ONLY":
        raise ContractError("Fixture render receipt is not passing")
    renderer = _import_binding("scripts.build_spot_spray_simulation_video_pairs_v1")
    ffprobe = resolve_path(str(config["source_locks"]["ffprobe"]["path"]))
    pair_video_rows: list[dict[str, Any]] = []
    for pair in render_receipt["pairs"]:
        pair_root = fixture_root / "pairs" / pair["split"] / pair["pair_id"]
        for relative in ("ideal/rgb.mp4", "degraded/rgb.mp4", "side_by_side.mp4"):
            probe = renderer.probe_video(ffprobe, pair_root / relative)
            if probe["decoded_frame_count"] != 30:
                raise ContractError(f"Fixture video failed readback: {pair_root / relative}")
            pair_video_rows.append(
                {"pair_id": pair["pair_id"], "video": relative, "probe": probe}
            )
    result: dict[str, Any] = {
        "status": "PASS_NATIVE_FIXTURE_VALIDATION_SYNTHETIC_ONLY",
        "render": {
            "pair_count": len(render_receipt["pairs"]),
            "frames_per_arm": 30,
            "all_pair_quality_gates_passed": all(
                all(row["quality_gates"].values()) for row in render_receipt["pairs"]
            ),
            "videos": pair_video_rows,
            "release_lock_sha256": sha256_file(fixture_root / "release_lock_v1.json"),
        },
        "inference_required": require_inference,
        "synthetic_only": True,
        "field_product_or_chemical_go": False,
    }
    if require_inference:
        run_root = paths["run"]
        receipt = load_json(run_root / "run_receipt.json")
        metrics = load_json(run_root / "metrics.json")
        access = receipt["access_guard"]
        if (
            receipt["checkpoint_sha256"]
            != config["source_locks"]["selected_checkpoint"]["sha256"]
            or receipt["locked_test_evaluation_count"] != 1
            or access["test_accessed_before_threshold_lock"] is not False
            or metrics["calibration"]["sole_threshold_source"]
            != "degraded_calibration"
            or metrics["calibration"]["ideal_used_for_selection"] is not False
        ):
            raise ContractError("Inference receipt violated calibration/test guards")
        overlay = renderer.probe_video(
            ffprobe, run_root / "videos/locked_test_overlay_side_by_side.mp4"
        )
        if overlay["decoded_frame_count"] != 30:
            raise ContractError("Overlay side-by-side video failed readback")
        result["inference"] = {
            "checkpoint_sha256": receipt["checkpoint_sha256"],
            "selected_shared_threshold": receipt["selected_shared_threshold"],
            "locked_test_evaluation_count": receipt[
                "locked_test_evaluation_count"
            ],
            "test_accessed_before_threshold_lock": False,
            "ideal_used_for_threshold_selection": False,
            "overlay_side_by_side": overlay,
            "decision": metrics["decision"],
        }
    docs = paths["docs"]
    docs.mkdir(parents=True, exist_ok=True)
    write_json(docs / "fixture_validation_receipt.json", result)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--scope", choices=("fixture", "full"), default="fixture")
    subparsers.add_parser("fixture-render")
    subparsers.add_parser("fixture-infer")
    validate_parser = subparsers.add_parser("fixture-validate")
    validate_parser.add_argument("--require-inference", action="store_true")
    subparsers.add_parser("full-plan")
    subparsers.add_parser("full-plan-validate")
    subparsers.add_parser("full-seal-roster-extension")
    subparsers.add_parser("full-roster-extension-validate")
    subparsers.add_parser("full-seal-runtime-compatibility")
    subparsers.add_parser("full-runtime-compatibility-validate")
    full_render_parser = subparsers.add_parser("full-render-one")
    full_render_parser.add_argument(
        "--pair-id", default="calibration_c000_r00"
    )
    gt_scout_parser = subparsers.add_parser("full-scout-one")
    gt_scout_parser.add_argument(
        "--pair-id", default="calibration_c000_r01"
    )
    gt_scout_parser.add_argument("--candidate-index", type=int)
    gt_scout_mode = gt_scout_parser.add_mutually_exclusive_group()
    gt_scout_mode.add_argument("--dry-run", action="store_true")
    gt_scout_mode.add_argument(
        "--reference-published-pair", action="store_true"
    )
    source_cardinality_recovery_parser = subparsers.add_parser(
        "full-recover-zero-weed-scout"
    )
    source_cardinality_recovery_parser.add_argument("--pair-id", required=True)
    source_cardinality_recovery_parser.add_argument(
        "--candidate-index", type=int, required=True
    )
    locked_test_source_cardinality_recovery_parser = subparsers.add_parser(
        "full-recover-zero-weed-locked-test-scout"
    )
    locked_test_source_cardinality_recovery_parser.add_argument(
        "--pair-id", required=True
    )
    locked_test_source_cardinality_recovery_parser.add_argument(
        "--candidate-index", type=int, required=True
    )
    locked_test_source_cardinality_recovery_parser.add_argument(
        "--batch-id", required=True
    )
    calibration_batch_parser = subparsers.add_parser(
        "full-render-calibration-batch"
    )
    calibration_batch_parser.add_argument(
        "--pair-id", action="append", required=True
    )
    calibration_batch_parser.add_argument(
        "--max-new-pairs", type=int, default=1
    )
    locked_test_render_batch_parser = subparsers.add_parser(
        "full-render-locked-test-batch"
    )
    locked_test_render_batch_parser.add_argument(
        "--pair-id", action="append", required=True
    )
    locked_test_render_batch_parser.add_argument(
        "--max-new-pairs", type=int, default=1
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        if arguments.command == "preflight":
            result = preflight(arguments.config, scope=arguments.scope)
        elif arguments.command == "fixture-render":
            result = render_fixture(arguments.config)
        elif arguments.command == "fixture-infer":
            result = run_fixture_inference(arguments.config)
        elif arguments.command == "fixture-validate":
            result = validate_fixture(
                arguments.config, require_inference=arguments.require_inference
            )
        elif arguments.command == "full-plan":
            result = initialize_full_plan(arguments.config)
        elif arguments.command == "full-plan-validate":
            result = validate_full_plan(arguments.config)
        elif arguments.command == "full-seal-roster-extension":
            result = seal_roster_extension_release(arguments.config)
        elif arguments.command == "full-roster-extension-validate":
            result = validate_roster_extension_release(arguments.config)
        elif arguments.command == "full-seal-runtime-compatibility":
            result = seal_runtime_compatibility_release(arguments.config)
        elif arguments.command == "full-runtime-compatibility-validate":
            result = validate_runtime_compatibility_release(arguments.config)
        elif arguments.command == "full-render-one":
            result = render_full_pair(arguments.config, arguments.pair_id)
        elif arguments.command == "full-scout-one":
            result = run_gt_scout_candidate(
                arguments.config,
                arguments.pair_id,
                candidate_index=arguments.candidate_index,
                dry_run=arguments.dry_run,
                reference_published_pair=arguments.reference_published_pair,
            )
        elif arguments.command == "full-recover-zero-weed-scout":
            result = run_gt_source_cardinality_recovery(
                arguments.config,
                arguments.pair_id,
                candidate_index=arguments.candidate_index,
            )
        elif arguments.command == "full-recover-zero-weed-locked-test-scout":
            result = run_locked_test_gt_source_cardinality_recovery(
                arguments.config,
                arguments.pair_id,
                candidate_index=arguments.candidate_index,
                batch_id=arguments.batch_id,
            )
        elif arguments.command == "full-render-calibration-batch":
            result = run_calibration_batch(
                arguments.config,
                arguments.pair_id,
                max_new_pairs=arguments.max_new_pairs,
            )
        elif arguments.command == "full-render-locked-test-batch":
            result = run_locked_test_render_batch(
                arguments.config,
                arguments.pair_id,
                max_new_pairs=arguments.max_new_pairs,
            )
        else:
            raise AssertionError(arguments.command)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
