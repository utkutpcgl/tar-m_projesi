#!/usr/bin/env python3
"""Deterministic EBIS chamber, concrete and visual-RFID generator for Blender 4.5 LTS.

Run with Blender, for example:
  blender -b --factory-startup --python scripts/generate_ebis.py -- \
    --config configs/ebis_pilot.json --action render --seed 43102 \
    --camera camera_door --output output/preview

This script intentionally uses only Blender's bundled Python modules.  It builds the
scene, renders RGB + visible object-index masks + depth, derives instance-aware YOLO
boxes from the rendered masks, writes deterministic metadata, and can save the
generated .blend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import struct
import sys
import time
import zlib
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


SCRIPT_VERSION = "1.11.0"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
HISTORICAL_DISTORTION = [
    -0.2748546980,
    0.0015631931,
    -0.0006670383,
    -0.0014015330,
    0.0241547241,
]


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--action",
        choices=("build", "render", "batch", "validate"),
        default="render",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--expected-count", type=int, default=None, help="Validation count contract")
    parser.add_argument("--require-both-cameras", action="store_true")
    parser.add_argument("--camera", choices=("camera_door", "camera_angled"))
    parser.add_argument("--output", type=Path, default=Path("output/preview"))
    parser.add_argument("--resolution", type=str, help="WIDTHxHEIGHT override")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument("--cpu", action="store_true", help="Force Cycles CPU")
    parser.add_argument("--no-depth", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing render with the same camera and seed",
    )
    return parser.parse_args(argv)


def load_config(path: Path) -> dict:
    with path.resolve().open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    if cfg.get("schema_version") != 1 or cfg.get("domain") not in {
        "ebis_press_v1",
        "ebis_press_led_v2",
    }:
        raise ValueError("Unsupported or invalid EBIS config")
    if cfg.get("render", {}).get("engine") != "CYCLES":
        raise ValueError("This generator contract requires the Cycles render engine")
    machine_cfg = cfg.get("machine", {})
    chamber_width = float(machine_cfg.get("chamber_width_m", 0.0))
    platen_diameter = float(machine_cfg.get("platen_diameter_m", 0.4))
    if chamber_width <= 0.0 or not 0.1 < platen_diameter < chamber_width:
        raise ValueError("machine.platen_diameter_m must fit inside the positive chamber width")
    contact_face_thickness = float(
        machine_cfg.get("upper_contact_face_thickness_m", 0.0006)
    )
    contact_face_scale = float(
        machine_cfg.get("upper_contact_face_diameter_scale", 0.985)
    )
    contact_face_extension = float(
        machine_cfg.get("upper_contact_face_bottom_extension_m", 0.0001)
    )
    if (
        not 0.0002 <= contact_face_thickness <= 0.0015
        or not 0.94 <= contact_face_scale <= 1.0
        or not 0.0 <= contact_face_extension < contact_face_thickness
    ):
        raise ValueError(
            "machine upper-contact-face dimensions must remain a thin inset "
            "disc at the upper platen underside"
        )
    lower_contact_face_thickness = float(
        machine_cfg.get("lower_contact_face_thickness_m", 0.0008)
    )
    lower_contact_face_scale = float(
        machine_cfg.get("lower_contact_face_diameter_scale", 0.985)
    )
    lower_contact_face_weights = machine_cfg.get(
        "lower_contact_face_surface_profile_weights",
        {"dry_used": 0.46, "dusty_used": 0.34, "damp_residue": 0.20},
    )
    allowed_lower_contact_profiles = {"dry_used", "dusty_used", "damp_residue"}
    if (
        not 0.0002 <= lower_contact_face_thickness <= 0.0015
        or not 0.94 <= lower_contact_face_scale <= 1.0
        or set(lower_contact_face_weights) != allowed_lower_contact_profiles
        or any(float(value) < 0.0 for value in lower_contact_face_weights.values())
        or sum(map(float, lower_contact_face_weights.values())) <= 0.0
        or not str(
            machine_cfg.get(
                "lower_contact_face_surface_status",
                "provisional default used-steel augmentation; calibrate before production",
            )
        ).strip()
    ):
        raise ValueError(
            "machine lower-contact-face geometry/profile weights/status are invalid"
        )
    platen_scan_strength = float(
        machine_cfg.get("platen_scan_strength", 0.0)
    )
    if not 0.0 <= platen_scan_strength <= 1.0:
        raise ValueError("machine.platen_scan_strength must remain within 0..1")
    debris_profile = machine_cfg.get(
        "debris_morphology_profile", "rounded_ico_v1"
    )
    if debris_profile not in {
        "rounded_ico_v1",
        "angular_fracture_mix_v2",
    }:
        raise ValueError("unsupported machine.debris_morphology_profile")
    panel_materials = machine_cfg.get("interior_panel_materials", {})
    invalid_panel_materials = sorted(
        f"{key}={value}"
        for key, value in panel_materials.items()
        if key not in {"back", "left", "right", "ceiling", "tray"}
        or value not in {"grey", "blue", "overhead_dark"}
    )
    if invalid_panel_materials:
        raise ValueError(f"invalid machine.interior_panel_materials: {invalid_panel_materials}")
    if set(panel_materials) != {"back", "left", "right", "ceiling", "tray"}:
        raise ValueError(
            "machine.interior_panel_materials must define back/left/right/ceiling/tray"
        )
    if machine_cfg.get(
        "blue_wall_material_profile", "procedural_hammertone_v2"
    ) not in {
        "procedural_hammertone_v2",
        "polyhaven_blue_metal_plate_2k_trial",
    }:
        raise ValueError("machine.blue_wall_material_profile is unsupported")
    fixed_camera_stack_count = int(machine_cfg.get("fixed_camera_stack_count", 0))
    if (
        fixed_camera_stack_count not in {0, 3}
        or not str(machine_cfg.get("fixed_camera_stack_status", "")).strip()
    ):
        raise ValueError("machine fixed-camera-stack count/status is invalid")
    for profile_name, profile in machine_cfg.get("door_open_angle_profiles", {}).items():
        angle_range = list(map(float, profile.get("range_deg", [])))
        if (
            float(profile.get("weight", 0.0)) <= 0.0
            or len(angle_range) != 2
            or not 0.0 <= angle_range[0] <= angle_range[1] <= 135.0
        ):
            raise ValueError(f"invalid door angle profile: {profile_name}={profile}")
    door_width = float(
        machine_cfg.get("door_leaf_width_m", chamber_width - 0.014)
    )
    door_height = float(machine_cfg.get("door_leaf_height_m", 0.73))
    door_thickness = float(machine_cfg.get("door_leaf_thickness_m", 0.026))
    cover_size = list(
        map(
            float,
            machine_cfg.get("door_service_cover_size_m", [0.205, 0.205]),
        )
    )
    if (
        machine_cfg.get("door_side", "right") != "right"
        or not chamber_width * 0.9 <= door_width <= chamber_width * 1.02
        or not 0.64 <= door_height <= float(machine_cfg["chamber_height_m"]) * 1.02
        or not 0.012 <= door_thickness <= 0.045
        or len(cover_size) != 2
        or any(not 0.14 <= value <= 0.25 for value in cover_size)
    ):
        raise ValueError("machine front-door dimensions/hinge contract is invalid")
    cube_size = cfg.get("sample", {}).get("cube_size_m", cfg.get("sample", {}).get("size_m", []))
    if cube_size:
        ratio = platen_diameter / float(cube_size[0])
        if not 1.8 <= ratio <= 2.6:
            raise ValueError(
                "The EBIS platen diameter must remain approximately twice the cube edge "
                f"(observed ratio={ratio:.3f})"
            )
    if float(cfg.get("sample", {}).get("damage_distribution_power", 1.0)) <= 0.0:
        raise ValueError("sample.damage_distribution_power must be positive")
    sample_cfg = cfg.get("sample", {})
    pore_radius_range = list(
        map(float, sample_cfg.get("pore_radius_m", [0.00038, 0.00438]))
    )
    pore_count_base = int(sample_cfg.get("pore_count_base", 68))
    pore_count_damage_gain = int(sample_cfg.get("pore_count_damage_gain", 120))
    pore_radius_power = float(sample_cfg.get("pore_radius_distribution_power", 2.35))
    if (
        len(pore_radius_range) != 2
        or not 0.0002 <= pore_radius_range[0] <= pore_radius_range[1] <= 0.005
        or not 24 <= pore_count_base <= 160
        or not 0 <= pore_count_damage_gain <= 180
        or not 1.4 <= pore_radius_power <= 4.0
    ):
        raise ValueError("sample casting-pore scale/count contract is invalid")
    material_detail = sample_cfg.get("material_detail_profile", {})
    if material_detail and (
        not 0.0 <= float(material_detail.get("colour_mix", 0.38)) <= 0.60
        or not 0.0
        <= float(material_detail.get("roughness_mix", 0.42))
        <= 0.65
        or not 0.0
        <= float(material_detail.get("bump_strength", 0.32))
        <= 0.60
        or not 0.00005
        <= float(material_detail.get("bump_distance_m", 0.00072))
        <= 0.0012
    ):
        raise ValueError("sample.material_detail_profile is outside safe bounds")
    allowed_surface_regimes = {"clean_cast", "pitted", "edge_worn", "spalled"}
    regime_weights = sample_cfg.get("surface_regime_weights_by_shape", {})
    edge_count_ranges = sample_cfg.get("edge_relief_count_range_by_regime", {})
    if set(regime_weights) != {"cube", "cylinder"}:
        raise ValueError(
            "sample.surface_regime_weights_by_shape must define cube and cylinder"
        )
    for shape, weights in regime_weights.items():
        if set(weights) != allowed_surface_regimes or sum(map(float, weights.values())) <= 0.0:
            raise ValueError(f"invalid concrete surface regime weights: {shape}={weights}")
        if any(float(value) < 0.0 for value in weights.values()):
            raise ValueError(f"negative concrete surface regime weight: {shape}={weights}")
    if set(edge_count_ranges) != allowed_surface_regimes:
        raise ValueError(
            "sample.edge_relief_count_range_by_regime must define every surface regime"
        )
    for regime, count_range in edge_count_ranges.items():
        values = list(map(int, count_range))
        if len(values) != 2 or not 0 <= values[0] <= values[1] <= 32:
            raise ValueError(f"invalid concrete edge-relief count range: {regime}={count_range}")
    edge_size_range = list(map(float, sample_cfg.get("edge_relief_size_m", [])))
    if (
        len(edge_size_range) != 2
        or not 0.0003 <= edge_size_range[0] <= edge_size_range[1] <= 0.006
    ):
        raise ValueError(f"invalid concrete edge-relief size range: {edge_size_range}")
    aggregate_count_ranges = sample_cfg.get(
        "exposed_aggregate_count_range_by_regime", {}
    )
    if set(aggregate_count_ranges) != allowed_surface_regimes:
        raise ValueError(
            "sample.exposed_aggregate_count_range_by_regime must define every "
            "surface regime"
        )
    for regime, count_range in aggregate_count_ranges.items():
        values = list(map(int, count_range))
        if len(values) != 2 or not 0 <= values[0] <= values[1] <= 40:
            raise ValueError(
                f"invalid exposed-aggregate count range: {regime}={count_range}"
            )
    aggregate_radius_range = list(
        map(float, sample_cfg.get("exposed_aggregate_radius_m", []))
    )
    if (
        len(aggregate_radius_range) != 2
        or not 0.00035
        <= aggregate_radius_range[0]
        <= aggregate_radius_range[1]
        <= 0.004
    ):
        raise ValueError(
            f"invalid exposed-aggregate radius range: {aggregate_radius_range}"
        )
    cylinder_spall_range = list(
        map(float, sample_cfg.get("spalled_cylinder_cavity_size_m", []))
    )
    if (
        len(cylinder_spall_range) != 2
        or not 0.004
        <= cylinder_spall_range[0]
        <= cylinder_spall_range[1]
        <= 0.040
    ):
        raise ValueError(
            f"invalid spalled-cylinder cavity range: {cylinder_spall_range}"
        )
    weathering_count_ranges = sample_cfg.get(
        "top_load_weathering_patch_count_range_by_regime", {}
    )
    weathering_width_range = list(
        map(float, sample_cfg.get("top_load_weathering_width_fraction_range", []))
    )
    weathering_height_range = list(
        map(float, sample_cfg.get("top_load_weathering_height_fraction_range", []))
    )
    weathering_depth_range = list(
        map(
            float,
            sample_cfg.get(
                "top_load_weathering_depth_below_top_fraction_range", []
            ),
        )
    )
    weathering_thickness_range = list(
        map(float, sample_cfg.get("top_load_weathering_half_thickness_m", []))
    )
    if (
        set(weathering_count_ranges) != allowed_surface_regimes
        or any(
            len(list(map(int, count_range))) != 2
            or not 0
            <= int(count_range[0])
            <= int(count_range[1])
            <= 16
            for count_range in weathering_count_ranges.values()
        )
        or len(weathering_width_range) != 2
        or not 0.01
        <= weathering_width_range[0]
        <= weathering_width_range[1]
        <= 0.24
        or len(weathering_height_range) != 2
        or not 0.01
        <= weathering_height_range[0]
        <= weathering_height_range[1]
        <= 0.16
        or len(weathering_depth_range) != 2
        or not 0.01
        <= weathering_depth_range[0]
        <= weathering_depth_range[1]
        <= 0.24
        or len(weathering_thickness_range) != 2
        or not 0.00005
        <= weathering_thickness_range[0]
        <= weathering_thickness_range[1]
        <= 0.0006
        or not str(sample_cfg.get("top_load_weathering_status", "")).strip()
    ):
        raise ValueError("invalid concrete top-load weathering contract")
    notch_ranges = sample_cfg.get("spalled_cube_notch_fraction_range", {})
    if set(notch_ranges) != {"x", "y", "z"}:
        raise ValueError("sample.spalled_cube_notch_fraction_range must define x/y/z")
    for axis, bounds in notch_ranges.items():
        values = list(map(float, bounds))
        if (
            len(values) != 2
            or not 0.05 <= values[0] <= values[1] <= 0.30
        ):
            raise ValueError(
                f"invalid spalled-cube notch fraction range: {axis}={bounds}"
            )
    fracture_tooth_count_range = list(
        map(int, sample_cfg.get("spalled_cube_fracture_tooth_count_range", []))
    )
    fracture_cavity_count_range = list(
        map(int, sample_cfg.get("spalled_cube_fracture_cavity_count_range", []))
    )
    if (
        len(fracture_tooth_count_range) != 2
        or not 0
        <= fracture_tooth_count_range[0]
        <= fracture_tooth_count_range[1]
        <= 16
        or len(fracture_cavity_count_range) != 2
        or not 1
        <= fracture_cavity_count_range[0]
        <= fracture_cavity_count_range[1]
        <= 12
        or not str(sample_cfg.get("spalled_cube_notch_status", "")).strip()
    ):
        raise ValueError(
            "invalid spalled-cube fracture-cavity/tooth/status contract"
        )
    conditioned_yaw = cfg.get("sample", {}).get("yaw_range_deg_by_camera_shape", {})
    for camera_name, shape_ranges in conditioned_yaw.items():
        if camera_name not in cfg.get("cameras", {}):
            raise ValueError(f"unknown camera in conditioned sample yaw: {camera_name}")
        for shape, angle_range in shape_ranges.items():
            values = list(map(float, angle_range))
            if (
                shape not in {"cube", "cylinder"}
                or len(values) != 2
                or not -180.0 <= values[0] <= values[1] <= 180.0
            ):
                raise ValueError(
                    f"invalid conditioned sample yaw: {camera_name}:{shape}={angle_range}"
                )
    for required_output in ("rgb", "semantic_masks", "yolo_bbox", "metadata"):
        if not cfg.get("outputs", {}).get(required_output):
            raise ValueError(f"Required output is disabled: {required_output}")
    class_ids = [int(item["id"]) for item in cfg.get("classes", [])]
    object_indices = [int(item["object_index"]) for item in cfg.get("classes", [])]
    if class_ids != [0, 1] or object_indices != [1, 2]:
        raise ValueError("EBIS v1 requires class ids [0,1] and object indices [1,2]")
    tag_cfg = cfg.get("rfid_tag", {})
    count_weights = tag_cfg.get("instance_count_weights") or {"1": 1.0}
    try:
        maximum_instance_count = max(map(int, count_weights))
    except (TypeError, ValueError) as exc:
        raise ValueError("rfid_tag.instance_count_weights keys must be non-negative integers") from exc
    if maximum_instance_count < 0 or any(int(key) < 0 for key in count_weights):
        raise ValueError("rfid_tag.instance_count_weights keys must be non-negative integers")
    pass_index_start = int(tag_cfg.get("instance_pass_index_start", 1))
    dynamic_indices = set(range(pass_index_start, pass_index_start + maximum_instance_count))
    reserved_indices = set(object_indices)
    legacy_single_tag_index = maximum_instance_count == 1 and pass_index_start == 1
    if dynamic_indices & reserved_indices and not legacy_single_tag_index:
        raise ValueError(
            "RFID instance pass indices collide with semantic object indices: "
            f"{sorted(dynamic_indices & reserved_indices)}"
        )
    if dynamic_indices and (min(dynamic_indices) < 1 or max(dynamic_indices) > 32767):
        raise ValueError("RFID instance pass indices must be within Blender's 1..32767 range")
    paper_cfg = cfg.get("paper_label", {})
    if paper_cfg.get("enabled"):
        paper_size = list(map(float, paper_cfg.get("size_m", [])))
        visible_tip = list(map(float, paper_cfg.get("visible_tag_tip_fraction_range", [])))
        count_total = sum(map(float, paper_cfg.get("count_weights", {}).values()))
        colour_weights = paper_cfg.get("colour_profile_weights", {"aged_form": 1.0})
        if (
            len(paper_size) != 3
            or any(value <= 0.0 for value in paper_size)
            or len(visible_tip) != 2
            or not 0.0 <= visible_tip[0] <= visible_tip[1] <= 1.0
            or count_total <= 0.0
            or set(colour_weights)
            - {"white_form", "aged_form", "orange_decoy"}
            or any(float(value) < 0.0 for value in colour_weights.values())
            or sum(map(float, colour_weights.values())) <= 0.0
        ):
            raise ValueError("paper_label geometry/weights are invalid")
    lens_dust = cfg.get("camera_effects", {}).get("lens_dust", {})
    if lens_dust.get("enabled"):
        count_range = list(map(int, lens_dust.get("spot_count_range", [])))
        radius_range = list(
            map(float, lens_dust.get("radius_fraction_range", []))
        )
        opacity_range = list(map(float, lens_dust.get("opacity_range", [])))
        if (
            not 0.0
            <= float(lens_dust.get("occurrence_probability", 0.0))
            <= 1.0
            or len(count_range) != 2
            or not 0 <= count_range[0] <= count_range[1] <= 12
            or len(radius_range) != 2
            or not 0.002 <= radius_range[0] <= radius_range[1] <= 0.05
            or len(opacity_range) != 2
            or not 0.0 <= opacity_range[0] <= opacity_range[1] <= 0.08
        ):
            raise ValueError("camera_effects.lens_dust is outside subtle bounds")
    for camera_name, profile in cfg.get("cameras", {}).items():
        lens_range = list(
            map(float, profile.get("lens_mm_range", [profile.get("lens_mm", 0.0)] * 2))
        )
        distortion_range = list(
            map(
                float,
                profile.get(
                    "compositor_lens_distortion_range",
                    [cfg.get("camera_effects", {}).get("compositor_lens_distortion", 0.0)] * 2,
                ),
            )
        )
        if (
            len(lens_range) != 2
            or not 0.0 < lens_range[0] <= lens_range[1]
            or len(distortion_range) != 2
            or not -1.0 <= distortion_range[0] <= distortion_range[1] <= 1.0
        ):
            raise ValueError(f"invalid camera realization range: {camera_name}")
    annotation_policy = cfg.get("outputs", {}).get("annotation_policy")
    if annotation_policy is not None:
        if int(annotation_policy.get("model_input_px", 0)) < 320:
            raise ValueError("annotation_policy.model_input_px must be at least 320")
        for tier in ("standard", "hard"):
            values = annotation_policy.get("rfid_tag", {}).get(tier, {})
            required = {
                "min_short_side_px",
                "min_long_side_px",
                "min_foreground_pixels",
                "min_visibility_fraction_proxy",
                "min_largest_component_fraction",
            }
            missing = sorted(required - set(values))
            if missing:
                raise ValueError(f"annotation_policy.rfid_tag.{tier} is missing {missing}")
    return cfg


def canonical_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_sha256(cfg: dict) -> str:
    return hashlib.sha256(canonical_json(cfg).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def srgb_channel_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def srgb(values: tuple[float, float, float] | list[float], alpha: float = 1.0) -> tuple:
    return tuple(srgb_channel_to_linear(float(v)) for v in values[:3]) + (alpha,)


def hex_srgb(value: str, alpha: float = 1.0) -> tuple:
    clean = value.strip().lstrip("#")
    rgb_values = tuple(int(clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return srgb(rgb_values, alpha)


def kelvin_to_srgb(temperature: float) -> tuple[float, float, float]:
    temp = max(1000.0, min(40000.0, temperature)) / 100.0
    if temp <= 66.0:
        red = 255.0
        green = 99.4708025861 * math.log(temp) - 161.1195681661
        blue = 0.0 if temp <= 19.0 else 138.5177312231 * math.log(temp - 10.0) - 305.0447927307
    else:
        red = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
        blue = 255.0
    return tuple(max(0.0, min(255.0, v)) / 255.0 for v in (red, green, blue))


def weighted_choice(rng: random.Random, mapping: dict[str, float]) -> str:
    threshold = rng.random() * sum(mapping.values())
    cursor = 0.0
    ordered = sorted(mapping.items())
    for key, weight in ordered:
        cursor += weight
        if threshold <= cursor:
            return key
    return ordered[-1][0]


def set_input(node: bpy.types.Node, names: tuple[str, ...], value) -> None:
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def clean_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.world = None
    bpy.context.scene.use_nodes = False
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.textures,
        bpy.data.worlds,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)


def ensure_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in tuple(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def apply_modifier(obj: bpy.types.Object, modifier: bpy.types.Modifier) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def assign_material(obj: bpy.types.Object, material: bpy.types.Material | None) -> None:
    if material is not None:
        obj.data.materials.append(material)


def make_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    bevel: float = 0.0,
    pass_index: int = 0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0.0:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        apply_modifier(obj, modifier)
    assign_material(obj, material)
    obj.pass_index = pass_index
    move_to_collection(obj, collection)
    return obj


def make_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    vertices: int = 96,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.0,
    pass_index: int = 0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    if bevel > 0.0:
        modifier = obj.modifiers.new("Machined edge bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        apply_modifier(obj, modifier)
    assign_material(obj, material)
    obj.pass_index = pass_index
    move_to_collection(obj, collection)
    for polygon in obj.data.polygons:
        # Preserve a flat normal on circular end caps. Smoothing every polygon
        # bends highlights across concrete/platen faces and is especially
        # obvious in the close real-camera framing.
        polygon.use_smooth = abs(float(polygon.normal.z)) < 0.999
    return obj


def make_ico(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    subdivisions: int = 2,
    pass_index: int = 0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(obj, material)
    obj.pass_index = pass_index
    move_to_collection(obj, collection)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def make_polygon(
    name: str,
    vertices: list[tuple[float, float, float]],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    pass_index: int = 0,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], [list(range(len(vertices)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign_material(obj, material)
    obj.pass_index = pass_index
    return obj


def make_wrinkled_paper(
    name: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    rng: random.Random,
) -> bpy.types.Object:
    """Create a thin, irregular paper sheet in the local X/Z plane."""

    length, thickness, height = size
    center_x, center_y, center_z = center
    columns, rows = 7, 5
    vertices: list[tuple[float, float, float]] = []
    for row in range(rows):
        v = row / (rows - 1)
        for column in range(columns):
            u = column / (columns - 1)
            x = center_x + (u - 0.5) * length
            z = center_z + (v - 0.5) * height
            on_left_or_right = column in {0, columns - 1}
            on_top_or_bottom = row in {0, rows - 1}
            if on_left_or_right:
                x += rng.uniform(-0.0010, 0.0010)
            if on_top_or_bottom:
                z += rng.uniform(-0.0009, 0.0009)
            # Outward is negative local Y.  Two smooth folds plus a small
            # stochastic term create readable crumple shadows while staying
            # beneath the separately modelled ink/tape layer.
            fold = (
                math.sin(u * math.pi * 2.0 + 0.7) * 0.000030
                + math.sin(v * math.pi * 3.0 - 0.4) * 0.000024
            )
            edge_curl = -0.000055 if on_left_or_right or on_top_or_bottom else 0.0
            y = center_y + fold + edge_curl + rng.uniform(-0.000018, 0.000018)
            vertices.append((x, y, z))
    faces: list[tuple[int, int, int, int]] = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = row * columns + column
            b = a + 1
            d = (row + 1) * columns + column
            c = d + 1
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign_material(obj, material)
    solidify = obj.modifiers.new("Paper physical thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 0.0
    apply_modifier(obj, solidify)
    bevel = obj.modifiers.new("Paper softened cut edge", "BEVEL")
    bevel.width = min(0.000035, thickness * 0.20)
    bevel.segments = 2
    apply_modifier(obj, bevel)
    return obj


def make_curve_polyline(
    name: str,
    points: list[Vector],
    bevel_depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    pass_index: int = 0,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{name}_curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, value in zip(spline.points, points):
        point.co = (*value, 1.0)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    assign_material(obj, material)
    obj.pass_index = pass_index
    return obj


def point_object_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def parent_local(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)


def new_principled(
    name: str,
    base_color: tuple,
    roughness: float,
    metallic: float = 0.0,
    coat: float = 0.0,
    coat_roughness: float = 0.1,
    transmission: float = 0.0,
    alpha: float = 1.0,
) -> tuple[bpy.types.Material, bpy.types.Node, bpy.types.NodeTree]:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(shader, ("Base Color",), base_color)
    set_input(shader, ("Roughness",), roughness)
    set_input(shader, ("Metallic",), metallic)
    set_input(shader, ("Coat Weight", "Coat"), coat)
    set_input(shader, ("Coat Roughness",), coat_roughness)
    set_input(shader, ("Transmission Weight", "Transmission"), transmission)
    set_input(shader, ("Alpha",), alpha)
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = base_color
    return material, shader, material.node_tree


def add_micro_bump(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    scale: float,
    detail: float,
    roughness: float,
    strength: float,
    distance: float,
) -> None:
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = roughness
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def add_hammertone_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    base_dark: tuple[float, float, float],
    base_light: tuple[float, float, float],
    scale: float,
    seed_offset: float,
) -> None:
    """Add the millimetre-scale pebbled finish visible on EBIS sheet metal.

    The reference walls are powder-coated steel, not bare metal.  A metric
    object-space texture therefore drives colour, roughness and a shallow bump;
    this avoids the oversized, glossy procedural noise used by the early POC.
    """

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Location"].default_value = (seed_offset, seed_offset * 0.37, seed_offset * 0.71)
    pebbles = tree.nodes.new("ShaderNodeTexNoise")
    pebbles.inputs["Scale"].default_value = scale
    pebbles.inputs["Detail"].default_value = 3.2
    pebbles.inputs["Roughness"].default_value = 0.68
    pebbles.inputs["Distortion"].default_value = 0.22
    colour = tree.nodes.new("ShaderNodeValToRGB")
    colour.color_ramp.elements[0].position = 0.26
    colour.color_ramp.elements[0].color = srgb(base_dark)
    colour.color_ramp.elements[1].position = 0.78
    colour.color_ramp.elements[1].color = srgb(base_light)
    roughness = tree.nodes.new("ShaderNodeValToRGB")
    roughness.color_ramp.elements[0].position = 0.24
    roughness.color_ramp.elements[0].color = (0.24, 0.24, 0.24, 1.0)
    roughness.color_ramp.elements[1].position = 0.8
    roughness.color_ramp.elements[1].color = (0.46, 0.46, 0.46, 1.0)
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    bump.inputs["Distance"].default_value = 0.00032
    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], pebbles.inputs["Vector"])
    tree.links.new(pebbles.outputs["Fac"], colour.inputs["Fac"])
    tree.links.new(pebbles.outputs["Fac"], roughness.inputs["Fac"])
    tree.links.new(pebbles.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(colour.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(roughness.outputs["Color"], shader.inputs["Roughness"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def add_polyhaven_blue_metal_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
) -> None:
    """Attach the rights-cleared Poly Haven blue-metal PBR trial.

    The map represents 2.5 m of real surface, so object-space coordinates are
    scaled by 1/2.5.  This profile is intentionally opt-in: the scanned plate
    contains seams and long scratches that are not consistently present in the
    EBIS references.  It is retained for controlled A/B renders, not silently
    substituted for the calibrated hammertone fallback.
    """

    asset_root = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "external"
        / "polyhaven"
        / "blue_metal_plate_2k"
    )
    paths = {
        "diffuse": asset_root / "blue_metal_plate_diff_2k.jpg",
        "roughness": asset_root / "blue_metal_plate_rough_2k.jpg",
        "normal": asset_root / "blue_metal_plate_nor_gl_2k.jpg",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Poly Haven blue-metal trial maps missing: {missing}")

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.4, 0.4, 0.4)
    diffuse = tree.nodes.new("ShaderNodeTexImage")
    diffuse.image = bpy.data.images.load(str(paths["diffuse"]), check_existing=True)
    diffuse.extension = "REPEAT"
    roughness = tree.nodes.new("ShaderNodeTexImage")
    roughness.image = bpy.data.images.load(str(paths["roughness"]), check_existing=True)
    roughness.image.colorspace_settings.name = "Non-Color"
    roughness.extension = "REPEAT"
    normal_image = tree.nodes.new("ShaderNodeTexImage")
    normal_image.image = bpy.data.images.load(str(paths["normal"]), check_existing=True)
    normal_image.image.colorspace_settings.name = "Non-Color"
    normal_image.extension = "REPEAT"
    roughness_range = tree.nodes.new("ShaderNodeMapRange")
    roughness_range.inputs["From Min"].default_value = 0.0
    roughness_range.inputs["From Max"].default_value = 1.0
    roughness_range.inputs["To Min"].default_value = 0.34
    roughness_range.inputs["To Max"].default_value = 0.62
    normal = tree.nodes.new("ShaderNodeNormalMap")
    normal.space = "TANGENT"
    normal.inputs["Strength"].default_value = 0.22
    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    for image_node in (diffuse, roughness, normal_image):
        tree.links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
    tree.links.new(diffuse.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(roughness.outputs["Color"], roughness_range.inputs["Value"])
    tree.links.new(roughness_range.outputs["Result"], shader.inputs["Roughness"])
    tree.links.new(normal_image.outputs["Color"], normal.inputs["Color"])
    tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])


def add_ambientcg_concrete003_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    procedural_colour: bpy.types.NodeSocket,
    procedural_roughness: bpy.types.NodeSocket,
    procedural_normal: bpy.types.NodeSocket,
    detail_profile: dict | None = None,
) -> None:
    """Blend the CC0 ambientCG Concrete003 maps into the cast-concrete model.

    The photographed texture is exposed aggregate rather than a scanned EBIS
    specimen, so it is deliberately an opt-in A/B profile.  A box projection
    avoids cylinder seams, a high metric tiling rate keeps aggregates in the
    millimetre band, and the maps modulate rather than replace the procedural
    cast variation.  This preserves controlled moisture/damage variation.
    """

    asset_root = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "external"
        / "ambientcg"
        / "Concrete003_2K_JPG"
    )
    paths = {
        "colour": asset_root / "Concrete003_2K-JPG_Color.jpg",
        "roughness": asset_root / "Concrete003_2K-JPG_Roughness.jpg",
        "height": asset_root / "Concrete003_2K-JPG_Displacement.jpg",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"ambientCG Concrete003 trial maps missing: {missing}")

    detail_profile = detail_profile or {}
    colour_mix_factor = float(detail_profile.get("colour_mix", 0.38))
    roughness_mix_factor = float(detail_profile.get("roughness_mix", 0.42))
    bump_strength = float(detail_profile.get("bump_strength", 0.32))
    bump_distance_m = float(detail_profile.get("bump_distance_m", 0.00072))
    if not (
        0.0 <= colour_mix_factor <= 0.60
        and 0.0 <= roughness_mix_factor <= 0.65
        and 0.0 <= bump_strength <= 0.60
        and 0.00005 <= bump_distance_m <= 0.0012
    ):
        raise ValueError("ambientCG concrete detail profile is outside safe bounds")

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Scale"].default_value = (8.0, 8.0, 8.0)

    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(str(paths["colour"]), check_existing=True)
    colour.extension = "REPEAT"
    colour.projection = "BOX"
    colour.projection_blend = 0.22

    roughness = tree.nodes.new("ShaderNodeTexImage")
    roughness.image = bpy.data.images.load(str(paths["roughness"]), check_existing=True)
    roughness.image.colorspace_settings.name = "Non-Color"
    roughness.extension = "REPEAT"
    roughness.projection = "BOX"
    roughness.projection_blend = 0.22

    height = tree.nodes.new("ShaderNodeTexImage")
    height.image = bpy.data.images.load(str(paths["height"]), check_existing=True)
    height.image.colorspace_settings.name = "Non-Color"
    height.extension = "REPEAT"
    height.projection = "BOX"
    height.projection_blend = 0.22

    colour_modulation = tree.nodes.new("ShaderNodeMixRGB")
    colour_modulation.blend_type = "MULTIPLY"
    colour_modulation.inputs[0].default_value = colour_mix_factor
    roughness_mix = tree.nodes.new("ShaderNodeMixRGB")
    roughness_mix.blend_type = "MIX"
    roughness_mix.inputs[0].default_value = roughness_mix_factor
    pbr_bump = tree.nodes.new("ShaderNodeBump")
    pbr_bump.inputs["Strength"].default_value = bump_strength
    pbr_bump.inputs["Distance"].default_value = bump_distance_m

    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    for image_node in (colour, roughness, height):
        tree.links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
    tree.links.new(procedural_colour, colour_modulation.inputs[1])
    tree.links.new(colour.outputs["Color"], colour_modulation.inputs[2])
    tree.links.new(colour_modulation.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(procedural_roughness, roughness_mix.inputs[1])
    tree.links.new(roughness.outputs["Color"], roughness_mix.inputs[2])
    tree.links.new(roughness_mix.outputs["Color"], shader.inputs["Roughness"])
    tree.links.new(height.outputs["Color"], pbr_bump.inputs["Height"])
    tree.links.new(procedural_normal, pbr_bump.inputs["Normal"])
    tree.links.new(pbr_bump.outputs["Normal"], shader.inputs["Normal"])


def add_polyhaven_rough_concrete_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    procedural_colour: bpy.types.NodeSocket,
    procedural_roughness: bpy.types.NodeSocket,
    procedural_normal: bpy.types.NodeSocket,
) -> None:
    """Low-ratio CC0 rough-concrete PBR trial, never an implicit default.

    Poly Haven declares the scan as 1.2 m wide.  The EBIS specimen is much
    smaller, so the photographed colour is deliberately weak and the
    displacement map is used only as a shallow normal.  Object-space box
    projection avoids a cylinder seam while the procedural pores, damage and
    nominal silhouette remain authoritative.
    """

    asset_root = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "external"
        / "polyhaven"
        / "rough_concrete_1k"
    )
    paths = {
        "colour": asset_root / "rough_concrete_diff_1k.jpg",
        "roughness": asset_root / "rough_concrete_rough_1k.jpg",
        "height": asset_root / "rough_concrete_disp_1k.jpg",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Poly Haven rough-concrete trial maps missing: {missing}")

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    # One repeat per ~0.29 m keeps the 1.2 m source's broad plaster mottling
    # from becoming a detector shortcut on an 0.18 m specimen.
    mapping.inputs["Scale"].default_value = (3.45, 3.45, 3.45)

    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(str(paths["colour"]), check_existing=True)
    colour.extension = "REPEAT"
    colour.projection = "BOX"
    colour.projection_blend = 0.24

    roughness = tree.nodes.new("ShaderNodeTexImage")
    roughness.image = bpy.data.images.load(str(paths["roughness"]), check_existing=True)
    roughness.image.colorspace_settings.name = "Non-Color"
    roughness.extension = "REPEAT"
    roughness.projection = "BOX"
    roughness.projection_blend = 0.24

    height = tree.nodes.new("ShaderNodeTexImage")
    height.image = bpy.data.images.load(str(paths["height"]), check_existing=True)
    height.image.colorspace_settings.name = "Non-Color"
    height.extension = "REPEAT"
    height.projection = "BOX"
    height.projection_blend = 0.24

    colour_modulation = tree.nodes.new("ShaderNodeMixRGB")
    colour_modulation.blend_type = "MULTIPLY"
    colour_modulation.inputs[0].default_value = 0.22
    roughness_mix = tree.nodes.new("ShaderNodeMixRGB")
    roughness_mix.blend_type = "MIX"
    roughness_mix.inputs[0].default_value = 0.28
    pbr_bump = tree.nodes.new("ShaderNodeBump")
    pbr_bump.inputs["Strength"].default_value = 0.28
    pbr_bump.inputs["Distance"].default_value = 0.00072

    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    for image_node in (colour, roughness, height):
        tree.links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
    tree.links.new(procedural_colour, colour_modulation.inputs[1])
    tree.links.new(colour.outputs["Color"], colour_modulation.inputs[2])
    tree.links.new(colour_modulation.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(procedural_roughness, roughness_mix.inputs[1])
    tree.links.new(roughness.outputs["Color"], roughness_mix.inputs[2])
    tree.links.new(roughness_mix.outputs["Color"], shader.inputs["Roughness"])
    tree.links.new(height.outputs["Color"], pbr_bump.inputs["Height"])
    tree.links.new(procedural_normal, pbr_bump.inputs["Normal"])
    tree.links.new(pbr_bump.outputs["Normal"], shader.inputs["Normal"])


def add_machined_steel_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    ring_scale: float,
    rough_dark: float,
    rough_light: float,
    colour_dark: tuple[float, float, float] = (0.12, 0.13, 0.14),
    colour_light: tuple[float, float, float] = (0.34, 0.35, 0.36),
) -> None:
    """Layer sub-pixel machining, irregular wear and dirt onto a platen.

    A Wave texture must not drive the normal directly here.  In the close
    fisheye views that produced perfectly periodic, ceiling-sized ripples
    which do not exist in the reference steel.  The rings now make only a
    faint contribution to tonal/roughness variation; non-periodic fine noise
    supplies the very shallow normal.
    """

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    rings = tree.nodes.new("ShaderNodeTexWave")
    rings.wave_type = "RINGS"
    rings.rings_direction = "Z"
    rings.inputs["Scale"].default_value = ring_scale
    rings.inputs["Distortion"].default_value = 0.42
    rings.inputs["Detail"].default_value = 1.2
    dirt = tree.nodes.new("ShaderNodeTexNoise")
    dirt.inputs["Scale"].default_value = 37.0
    dirt.inputs["Detail"].default_value = 5.0
    dirt.inputs["Roughness"].default_value = 0.76
    micro = tree.nodes.new("ShaderNodeTexNoise")
    micro.inputs["Scale"].default_value = 760.0
    micro.inputs["Detail"].default_value = 2.4
    micro.inputs["Roughness"].default_value = 0.61
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs[0].default_value = 0.11
    roughness = tree.nodes.new("ShaderNodeValToRGB")
    roughness.color_ramp.elements[0].color = (rough_dark, rough_dark, rough_dark, 1.0)
    roughness.color_ramp.elements[1].color = (rough_light, rough_light, rough_light, 1.0)
    colour = tree.nodes.new("ShaderNodeValToRGB")
    colour.color_ramp.elements[0].position = 0.18
    colour.color_ramp.elements[0].color = srgb(colour_dark)
    colour.color_ramp.elements[1].position = 0.84
    colour.color_ramp.elements[1].color = srgb(colour_light)
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.000035
    tree.links.new(texcoord.outputs["Object"], rings.inputs["Vector"])
    tree.links.new(texcoord.outputs["Object"], dirt.inputs["Vector"])
    tree.links.new(texcoord.outputs["Object"], micro.inputs["Vector"])
    tree.links.new(dirt.outputs["Fac"], mix.inputs[1])
    tree.links.new(rings.outputs["Color"], mix.inputs[2])
    tree.links.new(mix.outputs["Color"], roughness.inputs["Fac"])
    tree.links.new(mix.outputs["Color"], colour.inputs["Fac"])
    tree.links.new(micro.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(roughness.outputs["Color"], shader.inputs["Roughness"])
    tree.links.new(colour.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def add_ambientcg_metal038_finish(
    tree: bpy.types.NodeTree,
    shader: bpy.types.Node,
    *,
    colour_mix: float,
    roughness_mix: float,
    bump_strength: float,
    rng: random.Random,
) -> None:
    """Add a deliberately weak, rights-cleared used-steel scan contribution.

    The ambientCG asset has no declared physical span and its preview is not a
    press-platen measurement.  It therefore cannot replace the calibrated
    procedural BRDF.  One generated-coordinate projection contributes sparse
    scratches and roughness breakup at a bounded ratio; the nominal steel
    colour, metalness and broad highlight remain authoritative.
    """

    asset_root = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "external"
        / "ambientcg"
        / "Metal038_1K_JPG"
    )
    paths = {
        "colour": asset_root / "Metal038_1K-JPG_Color.jpg",
        "roughness": asset_root / "Metal038_1K-JPG_Roughness.jpg",
        "height": asset_root / "Metal038_1K-JPG_Displacement.jpg",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"ambientCG Metal038 trial maps missing: {missing}")
    if not (
        0.0 <= colour_mix <= 0.25
        and 0.0 <= roughness_mix <= 0.40
        and 0.0 <= bump_strength <= 0.20
    ):
        raise ValueError("Metal038 contribution exceeds the bounded EBIS trial")

    base_input = shader.inputs["Base Color"]
    roughness_input = shader.inputs["Roughness"]
    normal_input = shader.inputs["Normal"]
    if not (base_input.is_linked and roughness_input.is_linked):
        raise RuntimeError("Metal038 hybrid requires the procedural steel finish first")
    procedural_base = base_input.links[0].from_socket
    procedural_roughness = roughness_input.links[0].from_socket
    procedural_normal = (
        normal_input.links[0].from_socket if normal_input.is_linked else None
    )
    for socket in (base_input, roughness_input, normal_input):
        for link in list(socket.links):
            tree.links.remove(link)

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Location"].default_value = (
        rng.uniform(-0.45, 0.45),
        rng.uniform(-0.45, 0.45),
        0.0,
    )
    mapping.inputs["Rotation"].default_value[2] = rng.uniform(0.0, math.tau)
    mapping.inputs["Scale"].default_value = (1.35, 1.35, 1.0)

    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(str(paths["colour"]), check_existing=True)
    colour.extension = "REPEAT"
    roughness = tree.nodes.new("ShaderNodeTexImage")
    roughness.image = bpy.data.images.load(
        str(paths["roughness"]), check_existing=True
    )
    roughness.image.colorspace_settings.name = "Non-Color"
    roughness.extension = "REPEAT"
    height = tree.nodes.new("ShaderNodeTexImage")
    height.image = bpy.data.images.load(str(paths["height"]), check_existing=True)
    height.image.colorspace_settings.name = "Non-Color"
    height.extension = "REPEAT"
    tree.links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    for image_node in (colour, roughness, height):
        tree.links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])

    colour_layer = tree.nodes.new("ShaderNodeMixRGB")
    colour_layer.blend_type = "MIX"
    colour_layer.inputs[0].default_value = colour_mix
    tree.links.new(procedural_base, colour_layer.inputs[1])
    tree.links.new(colour.outputs["Color"], colour_layer.inputs[2])

    roughness_range = tree.nodes.new("ShaderNodeMapRange")
    roughness_range.inputs["From Min"].default_value = 0.0
    roughness_range.inputs["From Max"].default_value = 1.0
    roughness_range.inputs["To Min"].default_value = 0.27
    roughness_range.inputs["To Max"].default_value = 0.62
    roughness_layer = tree.nodes.new("ShaderNodeMixRGB")
    roughness_layer.blend_type = "MIX"
    roughness_layer.inputs[0].default_value = roughness_mix
    tree.links.new(roughness.outputs["Color"], roughness_range.inputs["Value"])
    tree.links.new(procedural_roughness, roughness_layer.inputs[1])
    tree.links.new(roughness_range.outputs["Result"], roughness_layer.inputs[2])

    scan_bump = tree.nodes.new("ShaderNodeBump")
    scan_bump.inputs["Strength"].default_value = bump_strength
    scan_bump.inputs["Distance"].default_value = 0.000045
    tree.links.new(height.outputs["Color"], scan_bump.inputs["Height"])
    if procedural_normal is not None:
        tree.links.new(procedural_normal, scan_bump.inputs["Normal"])
    tree.links.new(colour_layer.outputs["Color"], base_input)
    tree.links.new(roughness_layer.outputs["Color"], roughness_input)
    tree.links.new(scan_bump.outputs["Normal"], normal_input)


def build_materials(cfg: dict, moisture: float, rng: random.Random) -> dict[str, bpy.types.Material]:
    machine = cfg["machine"]
    platen_scan_strength = float(machine.get("platen_scan_strength", 0.0))
    mats: dict[str, bpy.types.Material] = {}

    mats["blue"], shader, tree = new_principled(
        "EBIS cobalt powder coat",
        srgb(machine["blue_paint_rgb"]),
        roughness=0.43,
        metallic=0.02,
        coat=0.32,
        coat_roughness=0.18,
    )
    blue_profile = machine.get(
        "blue_wall_material_profile", "procedural_hammertone_v2"
    )
    if blue_profile == "procedural_hammertone_v2":
        add_hammertone_finish(
            tree,
            shader,
            (0.012, 0.105, 0.19),
            (0.025, 0.255, 0.45),
            360.0,
            0.7,
        )
    elif blue_profile == "polyhaven_blue_metal_plate_2k_trial":
        add_polyhaven_blue_metal_finish(tree, shader)
    else:
        raise ValueError(f"Unsupported machine.blue_wall_material_profile={blue_profile}")

    mats["grey"], shader, tree = new_principled(
        "EBIS dark grey pebbled powder coat",
        srgb(machine["grey_paint_rgb"]),
        roughness=0.49,
        metallic=0.025,
        coat=0.24,
        coat_roughness=0.2,
    )
    add_hammertone_finish(tree, shader, (0.19, 0.205, 0.215), (0.36, 0.38, 0.395), 410.0, 1.9)

    mats["overhead_dark"], shader, tree = new_principled(
        "EBIS dark low-glare overhead shell",
        srgb((0.055, 0.062, 0.075)),
        roughness=0.84,
        metallic=0.12,
        coat=0.02,
    )
    add_micro_bump(tree, shader, 390.0, 1.8, 0.72, 0.06, 0.00008)

    mats["steel"], shader, tree = new_principled(
        "Worn brushed platen steel",
        srgb((0.30, 0.315, 0.33)),
        roughness=0.43,
        metallic=0.96,
        coat=0.04,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.31)
    add_machined_steel_finish(
        tree,
        shader,
        440.0,
        0.32,
        0.55,
        colour_dark=(0.23, 0.245, 0.26),
        colour_light=(0.43, 0.445, 0.46),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.10 * platen_scan_strength,
        roughness_mix=0.18 * platen_scan_strength,
        bump_strength=0.07 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:steel-metal038-v1"),
    )

    mats["upper_platen"], shader, tree = new_principled(
        "Used upper compression steel with broad reflection",
        srgb((0.255, 0.275, 0.30)),
        roughness=0.42,
        metallic=0.96,
        coat=0.035,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.34)
    add_machined_steel_finish(
        tree,
        shader,
        390.0,
        0.34,
        0.56,
        colour_dark=(0.17, 0.19, 0.215),
        colour_light=(0.38, 0.405, 0.43),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.12 * platen_scan_strength,
        roughness_mix=0.20 * platen_scan_strength,
        bump_strength=0.06 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:upper-body-metal038-v1"),
    )
    mats["upper_contact_face"], shader, tree = new_principled(
        "Used upper platen contact face",
        srgb((0.205, 0.22, 0.24)),
        roughness=0.47,
        metallic=0.97,
        coat=0.025,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.38)
    add_machined_steel_finish(
        tree,
        shader,
        520.0,
        0.38,
        0.60,
        colour_dark=(0.14, 0.155, 0.17),
        colour_light=(0.34, 0.36, 0.38),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.13 * platen_scan_strength,
        roughness_mix=0.24 * platen_scan_strength,
        bump_strength=0.08 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:upper-face-metal038-v1"),
    )
    mats["lower_contact_dry_used"], shader, tree = new_principled(
        "Lower contact face - dry used steel",
        srgb((0.22, 0.235, 0.25)),
        roughness=0.40,
        metallic=0.97,
        coat=0.025,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.39)
    add_machined_steel_finish(
        tree,
        shader,
        610.0,
        0.31,
        0.55,
        colour_dark=(0.14, 0.15, 0.16),
        colour_light=(0.36, 0.375, 0.39),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.14 * platen_scan_strength,
        roughness_mix=0.26 * platen_scan_strength,
        bump_strength=0.09 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:lower-dry-metal038-v1"),
    )
    mats["lower_contact_dusty_used"], shader, tree = new_principled(
        "Lower contact face - concrete dusty used steel",
        srgb((0.16, 0.17, 0.18)),
        roughness=0.62,
        metallic=0.70,
        coat=0.012,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.18)
    add_machined_steel_finish(
        tree,
        shader,
        540.0,
        0.52,
        0.74,
        colour_dark=(0.10, 0.105, 0.11),
        colour_light=(0.27, 0.28, 0.29),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.10 * platen_scan_strength,
        roughness_mix=0.18 * platen_scan_strength,
        bump_strength=0.07 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:lower-dusty-metal038-v1"),
    )
    mats["lower_contact_damp_residue"], shader, tree = new_principled(
        "Lower contact face - damp residue used steel",
        srgb((0.15, 0.17, 0.18)),
        roughness=0.31,
        metallic=0.88,
        coat=0.12,
        coat_roughness=0.21,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.34)
    add_machined_steel_finish(
        tree,
        shader,
        470.0,
        0.22,
        0.46,
        colour_dark=(0.09, 0.10, 0.11),
        colour_light=(0.30, 0.325, 0.35),
    )
    add_ambientcg_metal038_finish(
        tree,
        shader,
        colour_mix=0.15 * platen_scan_strength,
        roughness_mix=0.28 * platen_scan_strength,
        bump_strength=0.08 * platen_scan_strength,
        rng=random.Random(f"{moisture:.12f}:lower-damp-metal038-v1"),
    )
    mats["platen_polish"], shader, tree = new_principled(
        "Compression platen polished wear",
        srgb((0.2, 0.21, 0.22)),
        roughness=0.5,
        metallic=0.7,
        coat=0.08,
    )
    set_input(shader, ("Anisotropic IOR Level", "Anisotropic"), 0.28)
    add_machined_steel_finish(
        tree,
        shader,
        620.0,
        0.48,
        0.68,
        colour_dark=(0.11, 0.12, 0.125),
        colour_light=(0.3, 0.31, 0.315),
    )
    mats["concrete_dust"], shader, tree = new_principled(
        "Pale concrete dust on steel", srgb((0.34, 0.335, 0.315)), roughness=0.93
    )
    add_micro_bump(tree, shader, 115.0, 2.1, 0.72, 0.19, 0.00038)
    mats["steel_stain"], shader, tree = new_principled(
        "Old platen oxide and grease stain",
        srgb((0.09, 0.075, 0.062)),
        roughness=0.66,
        metallic=0.48,
    )
    add_micro_bump(tree, shader, 78.0, 3.1, 0.74, 0.08, 0.00012)

    mats["dark_steel"], _, _ = new_principled(
        "Oxidized dark ram steel", srgb((0.075, 0.082, 0.088)), roughness=0.31, metallic=0.88
    )
    mats["rubber"], _, _ = new_principled(
        "Door gasket rubber", srgb((0.009, 0.012, 0.015)), roughness=0.69
    )
    mats["glass"], shader, _ = new_principled(
        "Safety glass", srgb((0.30, 0.38, 0.41), 0.08), roughness=0.035, transmission=1.0, alpha=0.08
    )
    set_input(shader, ("IOR",), 1.46)
    mats["glass"].surface_render_method = "DITHERED"

    concrete_base = 0.425 - 0.105 * moisture + rng.uniform(-0.022, 0.022)
    mats["concrete"], shader, tree = new_principled(
        "Concrete sample - procedural pores",
        srgb((concrete_base * 1.03, concrete_base, concrete_base * 0.92)),
        roughness=max(0.72, 0.92 - 0.36 * moisture),
        coat=0.004 + moisture * 0.025,
        coat_roughness=0.62,
    )
    set_input(shader, ("Specular IOR Level", "Specular"), 0.18)
    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    coarse_color = tree.nodes.new("ShaderNodeTexNoise")
    coarse_color.inputs["Scale"].default_value = 23.0
    coarse_color.inputs["Detail"].default_value = 5.2
    coarse_color.inputs["Roughness"].default_value = 0.74
    fine_color = tree.nodes.new("ShaderNodeTexNoise")
    fine_color.inputs["Scale"].default_value = 245.0
    fine_color.inputs["Detail"].default_value = 5.4
    fine_color.inputs["Roughness"].default_value = 0.78
    coarse_ramp = tree.nodes.new("ShaderNodeValToRGB")
    coarse_ramp.color_ramp.elements[0].position = 0.25
    coarse_ramp.color_ramp.elements[0].color = srgb((concrete_base * 0.90,) * 3)
    coarse_ramp.color_ramp.elements[1].position = 0.78
    coarse_ramp.color_ramp.elements[1].color = srgb(
        (min(0.82, concrete_base * 1.04),) * 3
    )
    fine_ramp = tree.nodes.new("ShaderNodeValToRGB")
    fine_ramp.color_ramp.elements[0].position = 0.2
    fine_ramp.color_ramp.elements[0].color = srgb((concrete_base * 0.92,) * 3)
    fine_ramp.color_ramp.elements[1].position = 0.83
    fine_ramp.color_ramp.elements[1].color = srgb(
        (min(0.82, concrete_base * 1.03),) * 3
    )
    colour_mix = tree.nodes.new("ShaderNodeMixRGB")
    colour_mix.blend_type = "MULTIPLY"
    colour_mix.inputs[0].default_value = 0.32
    # Real cast faces retain long, low-contrast mould-release streaks beneath
    # the much finer sand/aggregate skin.  An anisotropic object-space noise
    # supplies that missing scale without displacing the regular test-sample
    # silhouette or baking one photographic pattern into every seed.
    cast_mapping = tree.nodes.new("ShaderNodeMapping")
    cast_mapping.vector_type = "POINT"
    cast_mapping.inputs["Scale"].default_value = (1.0, 1.0, 0.16)
    cast_streaks = tree.nodes.new("ShaderNodeTexNoise")
    cast_streaks.inputs["Scale"].default_value = 46.0
    cast_streaks.inputs["Detail"].default_value = 3.2
    cast_streaks.inputs["Roughness"].default_value = 0.67
    cast_streak_ramp = tree.nodes.new("ShaderNodeValToRGB")
    cast_streak_ramp.color_ramp.elements[0].position = 0.24
    cast_streak_ramp.color_ramp.elements[0].color = srgb((0.90, 0.89, 0.86))
    cast_streak_ramp.color_ramp.elements[1].position = 0.79
    cast_streak_ramp.color_ramp.elements[1].color = srgb((1.02, 1.01, 0.98))
    cast_colour_mix = tree.nodes.new("ShaderNodeMixRGB")
    cast_colour_mix.blend_type = "MULTIPLY"
    cast_colour_mix.inputs[0].default_value = 0.08 + 0.06 * moisture
    # Object coordinates retain metric scale; Generated coordinates stretch a
    # 100x200 mm cylinder's texture vertically and create fake wood-like ribs.
    tree.links.new(texcoord.outputs["Object"], coarse_color.inputs["Vector"])
    tree.links.new(texcoord.outputs["Object"], fine_color.inputs["Vector"])
    tree.links.new(coarse_color.outputs["Fac"], coarse_ramp.inputs["Fac"])
    tree.links.new(fine_color.outputs["Fac"], fine_ramp.inputs["Fac"])
    tree.links.new(coarse_ramp.outputs["Color"], colour_mix.inputs[1])
    tree.links.new(fine_ramp.outputs["Color"], colour_mix.inputs[2])
    tree.links.new(texcoord.outputs["Object"], cast_mapping.inputs["Vector"])
    tree.links.new(cast_mapping.outputs["Vector"], cast_streaks.inputs["Vector"])
    tree.links.new(cast_streaks.outputs["Fac"], cast_streak_ramp.inputs["Fac"])
    tree.links.new(colour_mix.outputs["Color"], cast_colour_mix.inputs[1])
    tree.links.new(cast_streak_ramp.outputs["Color"], cast_colour_mix.inputs[2])
    tree.links.new(cast_colour_mix.outputs["Color"], shader.inputs["Base Color"])
    concrete_roughness = tree.nodes.new("ShaderNodeValToRGB")
    concrete_roughness.color_ramp.elements[0].color = (0.62, 0.62, 0.62, 1.0)
    concrete_roughness.color_ramp.elements[1].color = (0.94, 0.94, 0.94, 1.0)
    tree.links.new(fine_color.outputs["Fac"], concrete_roughness.inputs["Fac"])
    tree.links.new(concrete_roughness.outputs["Color"], shader.inputs["Roughness"])

    pore_noise = tree.nodes.new("ShaderNodeTexNoise")
    pore_noise.inputs["Scale"].default_value = 1050.0
    pore_noise.inputs["Detail"].default_value = 3.0
    pore_noise.inputs["Roughness"].default_value = 0.8
    pore_ramp = tree.nodes.new("ShaderNodeValToRGB")
    pore_ramp.color_ramp.elements[0].position = 0.41
    pore_ramp.color_ramp.elements[1].position = 0.54
    pore_ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.02, 1.0)
    pore_ramp.color_ramp.elements[1].color = (0.62, 0.62, 0.62, 1.0)
    cast_relief = tree.nodes.new("ShaderNodeTexNoise")
    cast_relief.inputs["Scale"].default_value = 360.0
    cast_relief.inputs["Detail"].default_value = 4.1
    cast_relief.inputs["Roughness"].default_value = 0.76
    concrete_bump = tree.nodes.new("ShaderNodeBump")
    surface_height = tree.nodes.new("ShaderNodeMixRGB")
    surface_height.blend_type = "MULTIPLY"
    surface_height.inputs[0].default_value = 0.48
    cast_height = tree.nodes.new("ShaderNodeMixRGB")
    cast_height.blend_type = "MULTIPLY"
    cast_height.inputs[0].default_value = 0.36
    concrete_bump.inputs["Strength"].default_value = 0.74
    concrete_bump.inputs["Distance"].default_value = 0.00122
    tree.links.new(texcoord.outputs["Object"], pore_noise.inputs["Vector"])
    tree.links.new(cast_mapping.outputs["Vector"], cast_relief.inputs["Vector"])
    tree.links.new(pore_noise.outputs["Fac"], pore_ramp.inputs["Fac"])
    tree.links.new(fine_color.outputs["Fac"], surface_height.inputs[1])
    tree.links.new(pore_ramp.outputs["Color"], surface_height.inputs[2])
    tree.links.new(surface_height.outputs["Color"], cast_height.inputs[1])
    tree.links.new(cast_relief.outputs["Fac"], cast_height.inputs[2])
    tree.links.new(cast_height.outputs["Color"], concrete_bump.inputs["Height"])
    tree.links.new(concrete_bump.outputs["Normal"], shader.inputs["Normal"])
    concrete_profile = cfg["sample"].get(
        "material_profile", "procedural_cast_concrete_v2"
    )
    if concrete_profile in {
        "ambientcg_concrete003_2k_trial",
        "ambientcg_concrete003_hybrid_v1",
    }:
        add_ambientcg_concrete003_finish(
            tree,
            shader,
            cast_colour_mix.outputs["Color"],
            concrete_roughness.outputs["Color"],
            concrete_bump.outputs["Normal"],
            cfg["sample"].get("material_detail_profile"),
        )
    elif concrete_profile == "polyhaven_rough_concrete_1k_trial":
        add_polyhaven_rough_concrete_finish(
            tree,
            shader,
            cast_colour_mix.outputs["Color"],
            concrete_roughness.outputs["Color"],
            concrete_bump.outputs["Normal"],
        )
    elif concrete_profile != "procedural_cast_concrete_v2":
        raise ValueError(
            f"Unsupported sample.material_profile={concrete_profile}"
        )

    mats["concrete_dark"], _, _ = new_principled(
        "Concrete pore and aggregate", srgb((0.305, 0.292, 0.268)), roughness=0.94
    )
    mats["pore_shadow"], _, _ = new_principled(
        "Concrete recessed pore shadow",
        srgb((0.045, 0.041, 0.034)),
        roughness=0.98,
    )
    mats["aggregate"], _, _ = new_principled(
        "Exposed aggregate", srgb((0.285, 0.275, 0.255)), roughness=0.94
    )
    mats["concrete_load_stain_ochre"], shader, tree = new_principled(
        "Concrete upper load-zone ochre residue",
        srgb((0.335, 0.295, 0.205), 0.42),
        roughness=0.96,
        coat=0.002,
        alpha=0.42,
    )
    mats["concrete_load_stain_ochre"].surface_render_method = "DITHERED"
    set_input(shader, ("Specular IOR Level", "Specular"), 0.12)
    add_micro_bump(tree, shader, 520.0, 2.2, 0.78, 0.08, 0.000035)
    stain_coord = tree.nodes.new("ShaderNodeTexCoord")
    stain_noise = tree.nodes.new("ShaderNodeTexNoise")
    stain_noise.inputs["Scale"].default_value = 380.0
    stain_noise.inputs["Detail"].default_value = 3.4
    stain_noise.inputs["Roughness"].default_value = 0.78
    stain_noise.inputs["Distortion"].default_value = 0.58
    stain_alpha = tree.nodes.new("ShaderNodeValToRGB")
    stain_alpha.color_ramp.elements[0].position = 0.24
    stain_alpha.color_ramp.elements[0].color = (0.12, 0.12, 0.12, 1.0)
    stain_alpha.color_ramp.elements[1].position = 0.76
    stain_alpha.color_ramp.elements[1].color = (0.50, 0.50, 0.50, 1.0)
    tree.links.new(stain_coord.outputs["Object"], stain_noise.inputs["Vector"])
    tree.links.new(stain_noise.outputs["Fac"], stain_alpha.inputs["Fac"])
    tree.links.new(stain_alpha.outputs["Color"], shader.inputs["Alpha"])
    mats["concrete_load_stain_dark"], shader, tree = new_principled(
        "Concrete upper load-zone dark residue",
        srgb((0.225, 0.215, 0.185), 0.34),
        roughness=0.98,
        alpha=0.34,
    )
    mats["concrete_load_stain_dark"].surface_render_method = "DITHERED"
    set_input(shader, ("Specular IOR Level", "Specular"), 0.10)
    add_micro_bump(tree, shader, 610.0, 2.0, 0.80, 0.07, 0.00003)
    stain_coord = tree.nodes.new("ShaderNodeTexCoord")
    stain_noise = tree.nodes.new("ShaderNodeTexNoise")
    stain_noise.inputs["Scale"].default_value = 440.0
    stain_noise.inputs["Detail"].default_value = 3.1
    stain_noise.inputs["Roughness"].default_value = 0.81
    stain_noise.inputs["Distortion"].default_value = 0.66
    stain_alpha = tree.nodes.new("ShaderNodeValToRGB")
    stain_alpha.color_ramp.elements[0].position = 0.22
    stain_alpha.color_ramp.elements[0].color = (0.09, 0.09, 0.09, 1.0)
    stain_alpha.color_ramp.elements[1].position = 0.78
    stain_alpha.color_ramp.elements[1].color = (0.39, 0.39, 0.39, 1.0)
    tree.links.new(stain_coord.outputs["Object"], stain_noise.inputs["Vector"])
    tree.links.new(stain_noise.outputs["Fac"], stain_alpha.inputs["Fac"])
    tree.links.new(stain_alpha.outputs["Color"], shader.inputs["Alpha"])
    mats["warning_red"], _, _ = new_principled(
        "Safety red", srgb((0.68, 0.018, 0.012)), roughness=0.3, coat=0.42
    )
    mats["warning_yellow"], _, _ = new_principled(
        "Safety yellow", srgb((0.94, 0.58, 0.015)), roughness=0.34, coat=0.24
    )
    mats["black_plastic"], _, _ = new_principled(
        "RFID epoxy", srgb((0.006, 0.007, 0.008)), roughness=0.26, coat=0.36, coat_roughness=0.1
    )
    mats["camera_white"], shader, tree = new_principled(
        "Hikvision warm light-grey shell", srgb((0.50, 0.515, 0.51)), roughness=0.41, coat=0.12
    )
    add_micro_bump(tree, shader, 170.0, 1.5, 0.65, 0.08, 0.0002)
    mats["camera_lens"], _, _ = new_principled(
        "Camera lens black glass", srgb((0.002, 0.004, 0.006)), roughness=0.08, metallic=0.12, coat=0.7
    )
    mats["camera_bezel"], _, _ = new_principled(
        "Recessed camera bezel", srgb((0.055, 0.06, 0.065)), roughness=0.38, metallic=0.72
    )
    mats["paper"], shader, tree = new_principled(
        "Used concrete specimen paper form",
        srgb((0.72, 0.685, 0.59)),
        roughness=0.88,
    )
    add_micro_bump(tree, shader, 185.0, 3.2, 0.76, 0.12, 0.00009)
    paper_coord = tree.nodes.new("ShaderNodeTexCoord")
    paper_stain = tree.nodes.new("ShaderNodeTexNoise")
    paper_stain.inputs["Scale"].default_value = 18.0
    paper_stain.inputs["Detail"].default_value = 4.0
    paper_stain.inputs["Roughness"].default_value = 0.72
    paper_colour = tree.nodes.new("ShaderNodeValToRGB")
    paper_colour.color_ramp.elements[0].position = 0.18
    paper_colour.color_ramp.elements[0].color = srgb((0.49, 0.43, 0.33))
    paper_colour.color_ramp.elements[1].position = 0.82
    paper_colour.color_ramp.elements[1].color = srgb((0.76, 0.72, 0.62))
    tree.links.new(paper_coord.outputs["Object"], paper_stain.inputs["Vector"])
    tree.links.new(paper_stain.outputs["Fac"], paper_colour.inputs["Fac"])
    tree.links.new(paper_colour.outputs["Color"], shader.inputs["Base Color"])
    # The real specimen forms are folded and hand-crumpled rather than clean
    # planar cards.  A second, centimetre-scale normal layer preserves the
    # fine fibre bump above while adding broad, low-amplitude wrinkles without
    # changing the physical silhouette or the RFID occlusion z-order.
    wrinkle_noise = tree.nodes.new("ShaderNodeTexNoise")
    wrinkle_noise.inputs["Scale"].default_value = 34.0
    wrinkle_noise.inputs["Detail"].default_value = 2.4
    wrinkle_noise.inputs["Roughness"].default_value = 0.58
    wrinkle_noise.inputs["Distortion"].default_value = 0.42
    wrinkle_bump = tree.nodes.new("ShaderNodeBump")
    wrinkle_bump.inputs["Strength"].default_value = 0.28
    wrinkle_bump.inputs["Distance"].default_value = 0.00042
    normal_input = shader.inputs["Normal"]
    prior_normal_socket = normal_input.links[0].from_socket if normal_input.is_linked else None
    if normal_input.is_linked:
        tree.links.remove(normal_input.links[0])
    tree.links.new(paper_coord.outputs["Object"], wrinkle_noise.inputs["Vector"])
    tree.links.new(wrinkle_noise.outputs["Fac"], wrinkle_bump.inputs["Height"])
    if prior_normal_socket is not None:
        tree.links.new(prior_normal_socket, wrinkle_bump.inputs["Normal"])
    tree.links.new(wrinkle_bump.outputs["Normal"], normal_input)
    mats["paper_aged_form"] = mats["paper"]
    mats["paper_white_form"], shader, tree = new_principled(
        "Dirty white concrete specimen form",
        srgb((0.80, 0.79, 0.73)),
        roughness=0.90,
    )
    add_micro_bump(tree, shader, 210.0, 3.0, 0.78, 0.11, 0.00008)
    mats["paper_orange_decoy"], shader, tree = new_principled(
        "Orange non-target specimen paper decoy",
        srgb((0.70, 0.24, 0.025)),
        roughness=0.83,
    )
    add_micro_bump(tree, shader, 195.0, 2.8, 0.74, 0.10, 0.00008)
    mats["paper_ink"], _, _ = new_principled(
        "Faded printed specimen form ink", srgb((0.085, 0.075, 0.065)), roughness=0.82
    )
    mats["paper_tape"], shader, tree = new_principled(
        "Dirty translucent label tape",
        srgb((0.62, 0.54, 0.32), 0.84),
        roughness=0.48,
        coat=0.12,
        transmission=0.04,
        alpha=0.9,
    )
    mats["paper_tape"].surface_render_method = "DITHERED"
    mats["rfid_front"], shader, _ = new_principled(
        "RFID glossy amber front",
        hex_srgb(cfg["rfid_tag"]["front_srgb"]),
        roughness=0.54,
        metallic=0.02,
        coat=0.08,
        coat_roughness=0.34,
        transmission=0.0,
    )
    set_input(shader, ("Specular IOR Level", "Specular"), 0.16)
    mats["rfid_back"], shader, _ = new_principled(
        "RFID matte copper back",
        hex_srgb(cfg["rfid_tag"]["back_srgb"]),
        roughness=0.68,
        metallic=0.02,
        coat=0.025,
        coat_roughness=0.46,
    )
    set_input(shader, ("Specular IOR Level", "Specular"), 0.14)
    mats["copper"], _, _ = new_principled(
        "RFID copper antenna", srgb((0.55, 0.16, 0.004)), roughness=0.46, metallic=0.35, coat=0.04
    )
    mats["rfid_slot"], _, _ = new_principled(
        "RFID antenna slot", srgb((0.12, 0.03, 0.004)), roughness=0.48, metallic=0.24
    )
    return mats


def add_screw(
    name: str,
    location: tuple[float, float, float],
    axis: str,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    rotations = {
        "X": (0.0, math.pi / 2.0, 0.0),
        "Y": (math.pi / 2.0, 0.0, 0.0),
        "Z": (0.0, 0.0, 0.0),
    }
    screw = make_cylinder(
        name,
        location,
        radius=0.0062,
        depth=0.0045,
        material=material,
        collection=collection,
        vertices=32,
        rotation=rotations[axis],
        bevel=0.0006,
    )
    return screw


def build_door(
    cfg: dict,
    mats: dict,
    machine_col: bpy.types.Collection,
    rng: random.Random,
) -> dict:
    """Build the solid right-hinged leaf across the front aperture.

    The cameras live on the rear half of the chamber and look toward this
    leaf.  Earlier revisions incorrectly placed a narrow blue/glass panel
    along a side wall and left a grey fixed rear wall in the image; that
    combination read as a sliding door.  In the supplied pixels the broad
    grey sheet and rounded access cover rotate together around the front-right
    hinge, while the fixed chamber walls remain blue.
    """

    machine = cfg["machine"]
    chamber_width = float(machine["chamber_width_m"])
    chamber_depth = float(machine["chamber_depth_m"])
    door_width = float(machine.get("door_leaf_width_m", chamber_width - 0.014))
    door_height = float(machine.get("door_leaf_height_m", 0.79))
    door_thickness = float(machine.get("door_leaf_thickness_m", 0.026))
    door_side = str(machine.get("door_side", "right"))
    if door_side != "right":
        raise ValueError("The calibrated EBIS front-door contract requires a right hinge")
    angle_profiles = machine.get("door_open_angle_profiles")
    if angle_profiles:
        angle_mode = weighted_choice(
            rng,
            {name: float(values["weight"]) for name, values in angle_profiles.items()},
        )
        angle_range = list(map(float, angle_profiles[angle_mode]["range_deg"]))
    else:
        angle_mode = "single_range"
        angle_range = list(map(float, machine.get("door_open_angle_deg_range", [90.0, 90.0])))
    door_angle = rng.uniform(angle_range[0], angle_range[1])
    front_y = -chamber_depth / 2.0
    # "Right" is defined from the operator/exterior view facing into +Y.
    # From the rear cameras looking toward -Y that physical side is world -X.
    hinge_x = -chamber_width / 2.0 - 0.010
    door_base_z = 0.015

    pivot = bpy.data.objects.new("Right front door hinge pivot", None)
    machine_col.objects.link(pivot)
    pivot.location = (hinge_x, front_y - 0.004, 0.0)
    pivot.rotation_euler.z = math.radians(-door_angle)
    pivot["door_open_angle_deg"] = door_angle
    pivot["door_angle_convention"] = (
        "0=closed across front aperture, positive=left latch edge rotates outward"
    )

    centre_x = door_width / 2.0
    centre_z = door_base_z + door_height / 2.0
    inner_y = door_thickness / 2.0
    leaf_parts: list[bpy.types.Object] = []
    leaf_parts.append(
        make_box(
            "Solid grey front door sheet",
            (centre_x, 0.0, centre_z),
            (door_width, door_thickness, door_height),
            mats["grey"],
            machine_col,
            0.008,
        )
    )

    gasket_inset = 0.022
    gasket_width = 0.012
    for name, location, dimensions in (
        (
            "Door inner gasket hinge",
            (gasket_inset, inner_y + 0.0015, centre_z),
            (gasket_width, 0.006, door_height - 2.0 * gasket_inset),
        ),
        (
            "Door inner gasket latch",
            (door_width - gasket_inset, inner_y + 0.0015, centre_z),
            (gasket_width, 0.006, door_height - 2.0 * gasket_inset),
        ),
        (
            "Door inner gasket top",
            (centre_x, inner_y + 0.0015, door_base_z + door_height - gasket_inset),
            (door_width - 2.0 * gasket_inset, 0.006, gasket_width),
        ),
        (
            "Door inner gasket bottom",
            (centre_x, inner_y + 0.0015, door_base_z + gasket_inset),
            (door_width - 2.0 * gasket_inset, 0.006, gasket_width),
        ),
    ):
        leaf_parts.append(make_box(name, location, dimensions, mats["rubber"], machine_col, 0.002))

    cover_distance = float(
        machine.get("door_service_cover_center_from_hinge_m", 0.36)
    )
    cover_z = float(machine.get("door_service_cover_center_z_m", 0.43))
    cover_w, cover_h = map(
        float, machine.get("door_service_cover_size_m", [0.205, 0.205])
    )
    cover_x = cover_distance
    leaf_parts.append(
        make_box(
            "Door service cover gasket",
            (cover_x, inner_y + 0.004, cover_z),
            (cover_w + 0.017, 0.006, cover_h + 0.017),
            mats["rubber"],
            machine_col,
            0.026,
        )
    )
    service_cover = make_box(
        "Door rounded service cover",
        (cover_x, inner_y + 0.008, cover_z),
        (cover_w, 0.008, cover_h),
        mats["camera_white"],
        machine_col,
        0.022,
    )
    service_cover["reference_role"] = (
        "rounded grey access cover on the inner face of the moving front door"
    )
    leaf_parts.append(service_cover)
    screw_dx = cover_w / 2.0 - 0.0285
    screw_dz = cover_h / 2.0 - 0.0285
    for screw_index, (dx, dz) in enumerate(
        (
            (-screw_dx, -screw_dz),
            (-screw_dx, screw_dz),
            (screw_dx, -screw_dz),
            (screw_dx, screw_dz),
        )
    ):
        leaf_parts.append(
            make_cylinder(
                f"Door service cover screw {screw_index}",
                (cover_x + dx, inner_y + 0.013, cover_z + dz),
                0.0062,
                0.0045,
                mats["steel"],
                machine_col,
                vertices=32,
                rotation=(math.pi / 2.0, 0.0, 0.0),
                bevel=0.0006,
            )
        )

    for hinge_index, hinge_z in enumerate((0.19, 0.60)):
        leaf_parts.append(
            make_cylinder(
                f"Front door hinge barrel {hinge_index}",
                (0.0, 0.0, hinge_z),
                0.011,
                0.092,
                mats["dark_steel"],
                machine_col,
                vertices=48,
                bevel=0.001,
            )
        )
    for part in leaf_parts:
        parent_local(part, pivot)

    return {
        "angle_deg": door_angle,
        "angle_mode": angle_mode,
        "angle_range_deg": angle_range,
        "side": door_side,
        "angle_convention": pivot["door_angle_convention"],
        "hinge_location_m": list(pivot.location),
        "leaf_width_m": door_width,
        "leaf_height_m": door_height,
        "leaf_thickness_m": door_thickness,
        "service_cover": {
            "center_from_hinge_m": cover_distance,
            "center_z_m": cover_z,
            "size_m": [cover_w, cover_h],
        },
    }


def build_machine(
    cfg: dict,
    mats: dict,
    rng: random.Random,
    sample_height_m: float | None = None,
    seed: int | None = None,
) -> dict:
    machine_col = ensure_collection("EBIS_MACHINE")
    detail_col = ensure_collection("EBIS_DETAILS")
    width = float(cfg["machine"]["chamber_width_m"])
    depth = float(cfg["machine"]["chamber_depth_m"])
    height = float(cfg["machine"]["chamber_height_m"])
    half_w = width / 2.0
    back_y = depth / 2.0
    platen_diameter = float(cfg["machine"].get("platen_diameter_m", 0.4))
    platen_radius = platen_diameter / 2.0
    lower_platen_depth = float(cfg["machine"].get("lower_platen_thickness_m", 0.035))
    upper_platen_depth = float(cfg["machine"].get("upper_platen_thickness_m", 0.05))
    upper_contact_face_depth = float(
        cfg["machine"].get("upper_contact_face_thickness_m", 0.0006)
    )
    upper_contact_face_scale = float(
        cfg["machine"].get("upper_contact_face_diameter_scale", 0.985)
    )
    upper_contact_face_extension = float(
        cfg["machine"].get("upper_contact_face_bottom_extension_m", 0.0001)
    )
    lower_contact_face_depth = float(
        cfg["machine"].get("lower_contact_face_thickness_m", 0.0008)
    )
    lower_contact_face_scale = float(
        cfg["machine"].get("lower_contact_face_diameter_scale", 0.985)
    )
    lower_contact_rng = random.Random(f"{seed}:lower-contact-v1") if seed is not None else rng
    lower_contact_profile = weighted_choice(
        lower_contact_rng,
        cfg["machine"].get(
            "lower_contact_face_surface_profile_weights",
            {"dry_used": 0.46, "dusty_used": 0.34, "damp_residue": 0.20},
        ),
    )
    lower_base_top_z = 0.2398
    lower_platen_top_z = 0.241
    specimen_height = float(sample_height_m or cfg["sample"]["size_m"][2])
    upper_platen_bottom_z = lower_platen_top_z + specimen_height + 0.0005

    # Material zones are profile-level invariants, not per-frame random draws.
    # The fixed chamber shell is blue pebbled powder coat.  Grey belongs to the
    # moving front door and bare-metal tray/press hardware.
    panel_materials = cfg["machine"].get("interior_panel_materials", {})
    panel_mats = {
        key: mats[panel_materials.get(key, "grey")]
        for key in ("back", "left", "right", "ceiling", "tray")
    }
    make_box(
        "Chamber back panel",
        (0.0, back_y, height / 2.0),
        (width, 0.026, height),
        panel_mats["back"],
        machine_col,
        0.006,
    )
    make_box(
        "Chamber cobalt left inner wall",
        (-half_w, 0.0, height / 2.0),
        (0.028, depth, height),
        panel_mats["left"],
        machine_col,
        0.005,
    )
    make_box(
        "Chamber cobalt right inner wall",
        (half_w, 0.0, height / 2.0),
        (0.028, depth, height),
        panel_mats["right"],
        machine_col,
        0.005,
    )
    make_box("Chamber ceiling", (0.0, 0.0, height), (width, depth, 0.03), panel_mats["ceiling"], machine_col, 0.005)
    make_box("Debris tray", (0.0, 0.015, 0.035), (0.55, 0.49, 0.065), panel_mats["tray"], machine_col, 0.009)
    make_box(
        "Rear lower rubber seam",
        (0.0, back_y - 0.018, 0.205),
        (width - 0.035, 0.009, 0.035),
        mats["rubber"],
        detail_col,
        0.003,
    )
    make_box(
        "Blue left front aperture jamb",
        (-half_w - 0.014, -depth / 2.0 - 0.006, height / 2.0),
        (0.055, 0.06, height + 0.07),
        mats["blue"],
        machine_col,
        0.006,
    )
    make_box(
        "Blue right front aperture jamb",
        (half_w + 0.014, -depth / 2.0 - 0.006, height / 2.0),
        (0.055, 0.06, height + 0.07),
        mats["blue"],
        machine_col,
        0.006,
    )
    make_box(
        "Blue front aperture header",
        (0.0, -depth / 2.0 - 0.006, height + 0.022),
        (width + 0.10, 0.06, 0.058),
        mats["blue"],
        machine_col,
        0.007,
    )
    make_box(
        "Blue front aperture sill",
        (0.0, -depth / 2.0 - 0.006, -0.004),
        (width + 0.10, 0.06, 0.066),
        mats["blue"],
        machine_col,
        0.007,
    )

    # Geometry-only workshop proxy through the front-door opening.  It is kept
    # deliberately out of focus/peripheral; a calibrated, rights-cleared
    # backplate remains the preferred production replacement.
    make_box(
        "Workshop exterior floor proxy",
        (0.0, -0.92, 0.005),
        (1.45, 1.15, 0.025),
        mats["grey"],
        machine_col,
        0.002,
    )
    make_box(
        "Workshop exterior back wall proxy",
        (0.0, -1.45, 0.45),
        (1.45, 0.025, 0.9),
        mats["grey"],
        machine_col,
        0.003,
    )
    for cabinet_index, cabinet_x in enumerate((-0.46, 0.0, 0.46)):
        make_box(
            f"Workshop muted cabinet proxy {cabinet_index:02d}",
            (cabinet_x, -1.34, 0.35),
            (0.34, 0.16, 0.67),
            mats["dark_steel"],
            machine_col,
            0.018,
        )
        make_box(
            f"Workshop grey cabinet door proxy {cabinet_index:02d}",
            (cabinet_x, -1.245, 0.39),
            (0.25, 0.012, 0.43),
            mats["grey"],
            detail_col,
            0.006,
        )

    # Small opposing-camera/service stacks on the side walls.  Earlier
    # versions copied the dominant rear service hatch onto both side walls;
    # in fisheye renders those became two huge white rectangles.  The
    # temporally stratified references instead retain mostly pebbled wall
    # around a compact camera/port stack.
    for side, sign in (("left", -1.0), ("right", 1.0)):
        cover_x = sign * (half_w - 0.017)
        make_box(
            f"{side.title()} camera access cover gasket",
            (cover_x + sign * 0.006, 0.075, 0.43),
            (0.006, 0.142, 0.174),
            mats["rubber"],
            detail_col,
            0.014,
        )
        cover = make_box(
            f"{side.title()} camera access cover",
            (cover_x, 0.075, 0.43),
            (0.012, 0.13, 0.162),
            mats["grey"],
            detail_col,
            0.012,
        )
        cover["reference_role"] = "compact opposing fisheye/service stack"
        for yi in (0.025, 0.125):
            for zi in (0.38, 0.48):
                add_screw(
                    f"{side.title()} cover screw {yi:+.3f} {zi:.3f}",
                    (cover_x - sign * 0.008, yi, zi),
                    "X",
                    mats["steel"],
                    detail_col,
                )

        cover["camera_mount_note"] = (
            "Opposing view sees a recessed fisheye lens/IR stack, never a protruding cube."
        )
        inward_x = cover_x - sign * 0.011
        lens_y = 0.075
        make_box(
            f"{side.title()} fisheye narrow backing plate",
            (cover_x, lens_y, 0.42),
            (0.012, 0.064, 0.138),
            mats["grey"],
            detail_col,
            0.006,
        )
        make_cylinder(
            f"{side.title()} opposing fisheye bezel",
            (inward_x, lens_y, 0.438),
            0.0205,
            0.008,
            mats["camera_bezel"],
            detail_col,
            vertices=64,
            rotation=(0.0, math.pi / 2.0, 0.0),
            bevel=0.001,
        )
        make_cylinder(
            f"{side.title()} opposing fisheye lens",
            (inward_x - sign * 0.005, lens_y, 0.438),
            0.013,
            0.004,
            mats["camera_lens"],
            detail_col,
            vertices=64,
            rotation=(0.0, math.pi / 2.0, 0.0),
            bevel=0.0008,
        )
        make_cylinder(
            f"{side.title()} IR circular port",
            (inward_x - sign * 0.003, lens_y, 0.386),
            0.009,
            0.003,
            mats["camera_lens"],
            detail_col,
            vertices=48,
            rotation=(0.0, math.pi / 2.0, 0.0),
            bevel=0.0005,
        )
        make_box(
            f"{side.title()} Hikvision dark sensor window",
            (inward_x - sign * 0.003, lens_y, 0.346),
            (0.003, 0.034, 0.016),
            mats["camera_lens"],
            detail_col,
            0.0007,
        )

    # Preserve the procedural objects for scene introspection, but exclude the
    # unsupported opposing-camera bodies from RGB and mask renders.  The real
    # time-diverse frames reliably support the rounded service cover, not
    # three cartoon-like exposed camera/IR faces.
    hidden_camera_stack_names: list[str] = []
    if int(cfg["machine"].get("fixed_camera_stack_count", 0)) == 0:
        stack_prefixes = (
            "Rear fisheye ",
            "Rear opposing ",
            "Rear IR ",
            "Rear Hikvision ",
            "Left camera access ",
            "Right camera access ",
            "Left cover screw ",
            "Right cover screw ",
            "Left fisheye ",
            "Right fisheye ",
            "Left opposing ",
            "Right opposing ",
            "Left IR ",
            "Right IR ",
            "Left Hikvision ",
            "Right Hikvision ",
        )
        for obj in detail_col.objects:
            if obj.name.startswith(stack_prefixes):
                obj.hide_render = True
                obj.hide_set(True)
                hidden_camera_stack_names.append(obj.name)

    # Compression stack: measured CAD is still required, but the canonical
    # physical description constrains both discs to about 2.2x an 18 cm cube
    # edge.  The old POC accidentally treated 0.305/0.342 m as radii, yielding
    # implausible 61--68 cm discs that clipped through the 62 cm chamber.
    make_cylinder("Lower hydraulic piston", (0.0, 0.052, 0.13), 0.102, 0.15, mats["steel"], machine_col, bevel=0.004)
    make_cylinder(
        "Lower press platen",
        (0.0, 0.052, lower_base_top_z - lower_platen_depth / 2.0),
        platen_radius,
        lower_platen_depth,
        mats["steel"],
        machine_col,
        bevel=0.003,
    )
    # A distinct, full-width top face fixes the dominant pass-5 material gap:
    # temporally diverse LED and all-REF IR frames show a dark, used-steel
    # platen with circular machining, residue and localized highlights—not a
    # uniformly bright/clean disc.  The regime is independently seeded so this
    # bounded appearance augmentation cannot perturb sample/tag placement.
    make_cylinder(
        "Lower platen used contact face",
        (
            0.0,
            0.052,
            lower_platen_top_z - lower_contact_face_depth / 2.0,
        ),
        platen_radius * lower_contact_face_scale,
        lower_contact_face_depth,
        mats[f"lower_contact_{lower_contact_profile}"],
        detail_col,
        bevel=min(0.00018, lower_contact_face_depth * 0.22),
    )
    make_cylinder(
        "Upper press platen",
        (0.0, 0.052, upper_platen_bottom_z + upper_platen_depth / 2.0),
        platen_radius,
        upper_platen_depth,
        mats["upper_platen"],
        machine_col,
        bevel=0.003,
    )
    upper_contact_face_bottom_z = (
        upper_platen_bottom_z - upper_contact_face_extension
    )
    make_cylinder(
        "Upper platen dark contact face",
        (
            0.0,
            0.052,
            upper_contact_face_bottom_z + upper_contact_face_depth / 2.0,
        ),
        platen_radius * upper_contact_face_scale,
        upper_contact_face_depth,
        mats["upper_contact_face"],
        detail_col,
        bevel=min(0.00018, upper_contact_face_depth * 0.22),
    )
    make_cylinder(
        "Upper ram",
        (0.0, 0.052, upper_platen_bottom_z + 0.159),
        0.125,
        0.245,
        mats["dark_steel"],
        machine_col,
        bevel=0.004,
    )
    make_cylinder(
        "Upper ram collar",
        (0.0, 0.052, upper_platen_bottom_z + 0.06),
        0.172,
        0.032,
        mats["dark_steel"],
        detail_col,
        bevel=0.002,
    )

    # Platen staining remains shader-driven.  Flattened ico "decals" produced
    # obvious capsule silhouettes/reflections in close fisheye views.

    # Broken concrete and dust remain background rather than target class 1.
    # The target accumulates mostly small, flat chips.  Centimetre-scale smooth
    # white icospheres read as decorative stones, so only a very small tail is
    # allowed to approach 15 mm and all other debris stays in the 2–8 mm band.
    debris_range = list(map(int, cfg["machine"].get("debris_count_range", [14, 34])))
    debris_profile = cfg["machine"].get(
        "debris_morphology_profile", "rounded_ico_v1"
    )
    debris_count = rng.randint(debris_range[0], debris_range[1])
    debris_shape_counts = {"angular_fragment": 0, "rounded_chip": 0}
    for index in range(debris_count):
        angle = rng.uniform(0.0, math.tau)
        radius = rng.uniform(platen_radius * 0.48, platen_radius * 0.91)
        x = math.cos(angle) * radius
        y = 0.052 + math.sin(angle) * radius * 0.72
        height_phase = rng.uniform(0.001, 0.0032)
        large_chip = index < min(2, debris_count)
        scale = (
            rng.uniform(0.006, 0.016) if large_chip else rng.uniform(0.002, 0.008),
            rng.uniform(0.004, 0.012) if large_chip else rng.uniform(0.0018, 0.0065),
            rng.uniform(0.0015, 0.004) if large_chip else rng.uniform(0.0007, 0.0026),
        )
        z = lower_platen_top_z + max(height_phase, scale[2] * 0.44)
        angular_fragment = (
            debris_profile == "angular_fracture_mix_v2" and index % 5 != 4
        )
        if angular_fragment:
            rubble = make_box(
                f"Background angular concrete fragment {index:02d}",
                (x, y, z),
                scale,
                mats["concrete_dust" if index % 4 else "aggregate"],
                detail_col,
                bevel=min(0.00018, scale[2] * 0.12),
            )
            debris_shape_counts["angular_fragment"] += 1
        else:
            rubble = make_ico(
                f"Background rounded concrete chip {index:02d}",
                (x, y, z),
                scale,
                mats["concrete_dust" if index % 4 else "aggregate"],
                detail_col,
                subdivisions=2 if debris_profile == "rounded_ico_v1" else 1,
            )
            debris_shape_counts["rounded_chip"] += 1
        rubble.rotation_euler = (
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
        )

    door_rng = random.Random(f"{seed}:door-v1") if seed is not None else rng
    door_state = build_door(cfg, mats, machine_col, door_rng)
    return {
        "lower_platen_top_z": lower_platen_top_z,
        "upper_platen_bottom_z": upper_platen_bottom_z,
        "platen_center_y": 0.052,
        "platen_radius_m": platen_radius,
        "lower_contact_face": {
            "diameter_m": platen_diameter * lower_contact_face_scale,
            "diameter_scale": lower_contact_face_scale,
            "thickness_m": lower_contact_face_depth,
            "top_z_m": lower_platen_top_z,
            "specimen_contact_gap_m": 0.0,
            "surface_profile": lower_contact_profile,
            "surface_status": cfg["machine"].get(
                "lower_contact_face_surface_status",
                "provisional default used-steel augmentation; calibrate before production",
            ),
        },
        "upper_contact_face": {
            "diameter_m": platen_diameter * upper_contact_face_scale,
            "diameter_scale": upper_contact_face_scale,
            "thickness_m": upper_contact_face_depth,
            "bottom_z_m": upper_contact_face_bottom_z,
            "contact_gap_m": upper_contact_face_bottom_z
            - (lower_platen_top_z + specimen_height),
            "material_profile": cfg["machine"][
                "upper_contact_face_material_profile"
            ],
            "scan_strength": float(
                cfg["machine"].get("platen_scan_strength", 0.0)
            ),
        },
        "fixed_camera_stack_count": int(
            cfg["machine"].get("fixed_camera_stack_count", 0)
        ),
        "fixed_camera_stack_status": cfg["machine"]["fixed_camera_stack_status"],
        "hidden_camera_stack_object_count": len(hidden_camera_stack_names),
        "workshop_backdrop": cfg["machine"]["workshop_backdrop"],
        "door": door_state,
        "debris_count": debris_count,
        "debris_shape_counts": debris_shape_counts,
        "debris_morphology": debris_profile,
        "debris_annotation_policy": (
            "background only, never concrete target class"
        ),
        "machine_profile": cfg["machine"].get("machine_profile", "legacy_unspecified"),
        "blue_wall_material_profile": cfg["machine"].get(
            "blue_wall_material_profile", "procedural_hammertone_v2"
        ),
        "interior_panel_materials": {
            key: panel_materials.get(key, "grey")
            for key in ("back", "left", "right", "ceiling", "tray")
        },
    }


def choose_sample_spec(cfg: dict, rng: random.Random) -> dict:
    sample_cfg = cfg["sample"]
    shape_weights = sample_cfg.get("shape_weights")
    shape = weighted_choice(rng, shape_weights) if shape_weights else sample_cfg.get("shape", "cube")
    if shape == "cylinder":
        diameter = float(sample_cfg.get("cylinder_diameter_m", 0.15))
        height = float(sample_cfg.get("cylinder_height_m", 0.30))
        dimensions = [diameter, diameter, height]
    elif shape == "cube":
        dimensions = list(map(float, sample_cfg.get("cube_size_m", sample_cfg["size_m"])))
    else:
        raise ValueError(f"Unsupported concrete sample shape: {shape}")
    return {"shape": shape, "dimensions_m": dimensions}


def build_concrete_sample(
    cfg: dict,
    mats: dict,
    rng: random.Random,
    machine_state: dict[str, float],
    sample_spec: dict | None = None,
    camera_name: str | None = None,
) -> tuple[bpy.types.Object, dict]:
    sample_cfg = cfg["sample"]
    sample_spec = sample_spec or choose_sample_spec(cfg, rng)
    shape = sample_spec["shape"]
    sx, sy, sz = map(float, sample_spec["dimensions_m"])
    px = rng.uniform(-sample_cfg["position_jitter_m"][0], sample_cfg["position_jitter_m"][0])
    py = machine_state["platen_center_y"] + rng.uniform(
        -sample_cfg["position_jitter_m"][1], sample_cfg["position_jitter_m"][1]
    )
    pz = machine_state["lower_platen_top_z"] + sz / 2.0
    damage_min, damage_max = map(float, sample_cfg["damage_range"])
    damage_power = float(sample_cfg.get("damage_distribution_power", 1.0))
    damage = damage_min + (damage_max - damage_min) * (rng.random() ** damage_power)
    # Keep surface-category augmentation independent from the scenario RNG.
    # This makes same-seed camera, lighting and RFID comparisons valid when the
    # surface model is revised.  The categorical prevalence is deliberately
    # provisional until the complete real corpus has been measured.
    surface_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:surface-regime-v1"
    )
    surface_regime = weighted_choice(
        surface_rng,
        sample_cfg["surface_regime_weights_by_shape"][shape],
    )
    sample_col = ensure_collection("CONCRETE_SAMPLE")
    if shape == "cylinder":
        sample = make_cylinder(
            "SEM_CONCRETE_SAMPLE",
            (px, py, pz),
            radius=sx / 2.0,
            depth=sz,
            material=mats["concrete"],
            collection=sample_col,
            vertices=256,
            bevel=0.0014 + damage * 0.0022,
            pass_index=2,
        )
    else:
        sample = make_box(
            "SEM_CONCRETE_SAMPLE",
            (px, py, pz),
            (sx, sy, sz),
            mats["concrete"],
            sample_col,
            bevel=0.0018 + damage * 0.0028,
            pass_index=2,
        )
    conditioned_range = (
        sample_cfg.get("yaw_range_deg_by_camera_shape", {})
        .get(camera_name or "", {})
        .get(shape)
    )
    if conditioned_range is not None:
        yaw_min_deg, yaw_max_deg = map(float, conditioned_range)
    else:
        yaw_offset_deg = float(
            sample_cfg.get("yaw_offset_deg_by_shape", {}).get(shape, 0.0)
        )
        yaw_jitter_deg = float(
            sample_cfg.get("yaw_jitter_deg_by_shape", {}).get(
                shape, sample_cfg["yaw_jitter_deg"]
            )
        )
        yaw_min_deg = yaw_offset_deg - yaw_jitter_deg
        yaw_max_deg = yaw_offset_deg + yaw_jitter_deg
    yaw = math.radians(rng.uniform(yaw_min_deg, yaw_max_deg))
    sample.rotation_euler.z = yaw
    sample["semantic_class"] = "concrete_sample"
    sample["physical_size_m"] = [sx, sy, sz]
    sample["sample_shape"] = shape
    body_profile = "solid_nominal_v1"
    spall_notch_m: list[float] | None = None
    spall_notch_side: str | None = None
    spall_fracture_tooth_count = 0
    spall_fracture_cavity_count = 0
    spall_notch_realization: str | None = None
    cylinder_spall_size_m: list[float] | None = None
    cylinder_spall_angle_deg: float | None = None
    cylinder_spall_aggregate_count = 0
    cube_spall_aggregate_count = 0
    spall_side_selection_profile: str | None = None

    if shape == "cube" and surface_regime == "spalled":
        notch_ranges = sample_cfg["spalled_cube_notch_fraction_range"]
        spall_notch_rng = random.Random(
            f"{px:.9f}:{py:.9f}:{yaw:.9f}:{damage:.9f}:spall-notch-v1"
        )
        notch_x = sx * spall_notch_rng.uniform(
            *map(float, notch_ranges["x"])
        )
        notch_y = sy * spall_notch_rng.uniform(
            *map(float, notch_ranges["y"])
        )
        notch_z = sz * spall_notch_rng.uniform(
            *map(float, notch_ranges["z"])
        )
        # Consume the historical draw so downstream fracture detail remains
        # stable, then place the single still-image cavity on the side the
        # selected physical camera can actually see. Pass-10 could generate a
        # valid but fully platen-hidden far-side cavity, defeating the intended
        # damage augmentation in RGB.
        historical_side_sign = (
            -1.0 if spall_notch_rng.random() < 0.5 else 1.0
        )
        if camera_name in cfg.get("cameras", {}):
            camera_location = Vector(
                tuple(map(float, cfg["cameras"][camera_name]["location_m"]))
            )
            to_camera = camera_location - Vector((px, py, pz))
            sample_plus_x_world = Vector(
                (math.cos(yaw), math.sin(yaw), 0.0)
            )
            notch_side_sign = (
                1.0
                if sample_plus_x_world.dot(to_camera) >= 0.0
                else -1.0
            )
            spall_side_selection_profile = (
                "camera_visible_local_x_side_for_independent_still_v1"
            )
        else:
            notch_side_sign = historical_side_sign
            spall_side_selection_profile = "seeded_unconditioned_side_v1"
        # The real cam-11 samples lose one irregular, faceted volume at a
        # loaded corner. A rectangular Boolean looked machined, while a cluster
        # of overlapping ico cutters left crystalline islands in the 1080p MCP
        # render. Build one closed convex hull instead: it opens beyond the
        # top/front/selected-side planes and leaves one connected fracture face.
        bpy.context.view_layer.update()
        cutter_collection = ensure_collection("TEMP_BOOLEAN_CUTTERS")
        cavity_range = list(
            map(
                int,
                sample_cfg["spalled_cube_fracture_cavity_count_range"],
            )
        )
        spall_fracture_cavity_count = spall_notch_rng.randint(
            *cavity_range
        )
        if spall_fracture_cavity_count != 1:
            raise RuntimeError(
                "single-hull spall realization requires exactly one cavity"
            )
        # Normalized coordinates are fractions inward from the selected
        # upper-front corner; negative coordinates extend beyond an exterior
        # plane. Small deterministic jitter avoids a repeated CAD-like facet
        # while the configured notch bounds retain the augmentation envelope.
        normalized_hull_points = [
            (-0.24, -0.22, -0.20),
            (-0.24, -0.18, 0.88),
            (-0.20, 0.90, -0.22),
            (0.90, -0.22, -0.18),
            (-0.18, 0.64, 0.68),
            (0.66, -0.18, 0.74),
            (0.72, 0.70, -0.16),
            (0.84, 0.34, 0.48),
            (0.36, 0.88, 0.52),
            (0.43, 0.46, 0.92),
        ]
        local_hull_points = []
        for index, (fraction_x, fraction_y, fraction_z) in enumerate(
            normalized_hull_points
        ):
            if index >= 4:
                fraction_x += spall_notch_rng.uniform(-0.055, 0.055)
                fraction_y += spall_notch_rng.uniform(-0.055, 0.055)
                fraction_z += spall_notch_rng.uniform(-0.055, 0.055)
            local_hull_points.append(
                Vector(
                    (
                        notch_side_sign
                        * (sx / 2.0 - notch_x * fraction_x),
                        sy / 2.0 - notch_y * fraction_y,
                        sz / 2.0 - notch_z * fraction_z,
                    )
                )
            )
        cavity_mesh = bpy.data.meshes.new(
            "Concrete irregular convex spall cutter mesh"
        )
        cavity_bmesh = bmesh.new()
        cavity_vertices = [
            cavity_bmesh.verts.new(tuple(point))
            for point in local_hull_points
        ]
        bmesh.ops.convex_hull(
            cavity_bmesh,
            input=cavity_vertices,
            use_existing_faces=False,
        )
        cavity_bmesh.normal_update()
        cavity_bmesh.to_mesh(cavity_mesh)
        cavity_bmesh.free()
        cavity = bpy.data.objects.new(
            "Concrete single irregular convex spall cutter",
            cavity_mesh,
        )
        cutter_collection.objects.link(cavity)
        cavity.matrix_world = sample.matrix_world.copy()
        bpy.context.view_layer.update()
        cavity_boolean = sample.modifiers.new(
            "Single connected faceted corner loss", "BOOLEAN"
        )
        cavity_boolean.operation = "DIFFERENCE"
        cavity_boolean.solver = "EXACT"
        cavity_boolean.object = cavity
        apply_modifier(sample, cavity_boolean)
        bpy.data.objects.remove(cavity, do_unlink=True)
        if cavity_mesh.users == 0:
            bpy.data.meshes.remove(cavity_mesh)

        tooth_range = list(
            map(
                int,
                sample_cfg["spalled_cube_fracture_tooth_count_range"],
            )
        )
        spall_fracture_tooth_count = spall_notch_rng.randint(*tooth_range)
        body_profile = "single_hull_faceted_upper_front_corner_loss_v5"
        spall_notch_realization = "irregular_convex_hull_boolean_v2"
        spall_notch_m = [notch_x, notch_y, notch_z]
        spall_notch_side = (
            "left" if notch_side_sign < 0.0 else "right"
        )
        cube_spall_aggregate_count = spall_notch_rng.randint(18, 28)
        for index in range(cube_spall_aggregate_count):
            grain_radius = spall_notch_rng.uniform(0.0008, 0.0030)
            fracture_mode = index % 3
            if fracture_mode == 0:
                grain_local = Vector(
                    (
                        notch_side_sign
                        * (
                            sx / 2.0
                            - notch_x
                            + grain_radius
                            * spall_notch_rng.uniform(0.10, 0.34)
                        ),
                        sy / 2.0
                        - notch_y * spall_notch_rng.uniform(0.10, 0.90),
                        sz / 2.0
                        - notch_z * spall_notch_rng.uniform(0.08, 0.92),
                    )
                )
            elif fracture_mode == 1:
                grain_local = Vector(
                    (
                        notch_side_sign
                        * (
                            sx / 2.0
                            - notch_x
                            * spall_notch_rng.uniform(0.08, 0.92)
                        ),
                        sy / 2.0
                        - notch_y
                        + grain_radius
                        * spall_notch_rng.uniform(0.10, 0.34),
                        sz / 2.0
                        - notch_z * spall_notch_rng.uniform(0.08, 0.92),
                    )
                )
            else:
                grain_local = Vector(
                    (
                        notch_side_sign
                        * (
                            sx / 2.0
                            - notch_x
                            * spall_notch_rng.uniform(0.08, 0.92)
                        ),
                        sy / 2.0
                        - notch_y * spall_notch_rng.uniform(0.08, 0.92),
                        sz / 2.0
                        - notch_z
                        + grain_radius
                        * spall_notch_rng.uniform(0.10, 0.34),
                    )
                )
            material_key = (
                "aggregate"
                if index % 3 == 0
                else "concrete_load_stain_ochre"
                if index % 5 == 0
                else "concrete"
            )
            grain = make_ico(
                f"SEM_CONCRETE cube spall aggregate {index:02d}",
                tuple(sample.matrix_world @ grain_local),
                (
                    grain_radius * spall_notch_rng.uniform(0.42, 0.95),
                    grain_radius * spall_notch_rng.uniform(0.34, 0.86),
                    grain_radius * spall_notch_rng.uniform(0.40, 0.98),
                ),
                mats[material_key],
                sample_col,
                subdivisions=1,
                pass_index=2,
            )
            grain.rotation_euler = (
                spall_notch_rng.uniform(-0.8, 0.8),
                spall_notch_rng.uniform(-0.8, 0.8),
                yaw + spall_notch_rng.uniform(-0.8, 0.8),
            )
            grain["semantic_class"] = "concrete_sample"
            grain["surface_detail_role"] = "cube_spall_aggregate"

    if shape == "cylinder" and surface_regime == "spalled":
        # The real cylinders remain straight cast specimens but occasionally
        # lose one bounded, faceted volume at the loaded upper side.  A single
        # convex cutter creates true silhouette/parallax without the repeated
        # inward-curved sidewall artefact caused by smooth/displaced normals.
        cylinder_spall_rng = random.Random(
            f"{px:.9f}:{py:.9f}:{yaw:.9f}:{damage:.9f}:"
            "cylinder-spall-v1"
        )
        cavity_min, cavity_max = map(
            float, sample_cfg["spalled_cylinder_cavity_size_m"]
        )
        cavity_width = cylinder_spall_rng.uniform(cavity_min, cavity_max)
        cavity_depth = cylinder_spall_rng.uniform(
            cavity_min * 0.78, cavity_width * 0.94
        )
        cavity_height = cylinder_spall_rng.uniform(
            cavity_min * 0.82, cavity_width * 1.12
        )
        theta = cylinder_spall_rng.uniform(-1.02, 1.02)
        normal = Vector((math.sin(theta), math.cos(theta), 0.0))
        tangent = Vector((math.cos(theta), -math.sin(theta), 0.0))
        center = (
            normal * (sx / 2.0 - cavity_depth * 0.10)
            + Vector(
                (
                    0.0,
                    0.0,
                    cylinder_spall_rng.uniform(
                        sz * 0.31, sz * 0.46
                    ),
                )
            )
        )
        # Local points deliberately cross the radial surface and the upper
        # silhouette.  Their asymmetric convex hull reads as a fracture, not
        # a drilled circular hole.
        hull_coordinates = [
            (-0.62, -0.72, -0.48),
            (0.70, -0.66, -0.36),
            (-0.82, 0.60, -0.20),
            (0.76, 0.72, -0.10),
            (-0.54, -0.44, 0.68),
            (0.48, -0.30, 0.86),
            (-0.64, 0.52, 0.72),
            (0.58, 0.66, 0.54),
            (0.02, 0.92, 0.16),
            (0.08, -0.88, 0.18),
        ]
        local_hull_points = []
        for tangent_fraction, radial_fraction, height_fraction in hull_coordinates:
            local_hull_points.append(
                center
                + tangent * (0.5 * cavity_width * tangent_fraction)
                + normal * (cavity_depth * radial_fraction)
                + Vector((0.0, 0.0, 0.5 * cavity_height * height_fraction))
            )
        cavity_mesh = bpy.data.meshes.new(
            "Concrete cylinder faceted spall cutter mesh"
        )
        cavity_bmesh = bmesh.new()
        cavity_vertices = [
            cavity_bmesh.verts.new(tuple(point))
            for point in local_hull_points
        ]
        bmesh.ops.convex_hull(
            cavity_bmesh,
            input=cavity_vertices,
            use_existing_faces=False,
        )
        cavity_bmesh.normal_update()
        cavity_bmesh.to_mesh(cavity_mesh)
        cavity_bmesh.free()
        cavity = bpy.data.objects.new(
            "Concrete cylinder faceted spall cutter",
            cavity_mesh,
        )
        cutter_collection = ensure_collection("TEMP_BOOLEAN_CUTTERS")
        cutter_collection.objects.link(cavity)
        cavity.matrix_world = sample.matrix_world.copy()
        bpy.context.view_layer.update()
        cavity_boolean = sample.modifiers.new(
            "Single faceted cylinder side loss", "BOOLEAN"
        )
        cavity_boolean.operation = "DIFFERENCE"
        cavity_boolean.solver = "EXACT"
        cavity_boolean.object = cavity
        apply_modifier(sample, cavity_boolean)
        bpy.data.objects.remove(cavity, do_unlink=True)
        if cavity_mesh.users == 0:
            bpy.data.meshes.remove(cavity_mesh)
        body_profile = "solid_nominal_with_local_faceted_cylinder_spall_v1"
        cylinder_spall_size_m = [
            cavity_width,
            cavity_depth,
            cavity_height,
        ]
        cylinder_spall_angle_deg = math.degrees(theta)
        cylinder_spall_aggregate_count = cylinder_spall_rng.randint(18, 26)
        for index in range(cylinder_spall_aggregate_count):
            grain_radius = cylinder_spall_rng.uniform(0.0010, 0.0032)
            grain_center = (
                normal
                * (
                    sx / 2.0
                    - cavity_depth
                    * cylinder_spall_rng.uniform(0.04, 0.22)
                )
                + tangent
                * cylinder_spall_rng.uniform(
                    -cavity_width * 0.38, cavity_width * 0.38
                )
                + Vector(
                    (
                        0.0,
                        0.0,
                        center.z
                        + cylinder_spall_rng.uniform(
                            -cavity_height * 0.38,
                            cavity_height * 0.38,
                        ),
                    )
                )
            )
            material_key = (
                "aggregate"
                if index % 3 == 0
                else "concrete_load_stain_ochre"
                if index % 4 == 0
                else "concrete"
            )
            grain = make_ico(
                f"SEM_CONCRETE cylinder spall aggregate {index:02d}",
                tuple(sample.matrix_world @ grain_center),
                (
                    grain_radius
                    * cylinder_spall_rng.uniform(0.46, 0.92),
                    grain_radius
                    * cylinder_spall_rng.uniform(0.32, 0.78),
                    grain_radius
                    * cylinder_spall_rng.uniform(0.42, 0.96),
                ),
                mats[material_key],
                sample_col,
                subdivisions=1,
                pass_index=2,
            )
            grain.rotation_euler = (
                cylinder_spall_rng.uniform(-0.8, 0.8),
                cylinder_spall_rng.uniform(-0.8, 0.8),
                yaw
                - theta
                + cylinder_spall_rng.uniform(-0.7, 0.7),
            )
            grain["semantic_class"] = "concrete_sample"
            grain["surface_detail_role"] = "cylinder_spall_aggregate"

    # Reference samples frequently lose material at a loaded upper corner.
    # Use an independent RNG so this added surface detail cannot reshuffle the
    # scenario-level RFID and lighting choices for an existing seed.
    if damage > 0.42:
        spall_rng = random.Random(f"{px:.9f}:{py:.9f}:{damage:.9f}:upper-spalls-v1")
        spall_count = 1 + int(damage > 0.57)
        for index in range(spall_count):
            radius = spall_rng.uniform(0.012, 0.021) * (0.9 + 0.3 * damage)
            if shape == "cylinder":
                theta = spall_rng.uniform(-1.15, 1.15)
                radial = Vector((math.sin(theta), math.cos(theta), 0.0))
                local = radial * (sx / 2.0 + radius * spall_rng.uniform(0.08, 0.22))
                local.z = spall_rng.uniform(sz * 0.38, sz * 0.49)
                spall_inward = -radial * radius * 0.74 + Vector((0.0, 0.0, -radius * 0.08))
            else:
                side = -1.0 if (index + int(spall_rng.random() > 0.5)) % 2 == 0 else 1.0
                local = Vector(
                    (
                        side * (sx / 2.0 + radius * spall_rng.uniform(0.08, 0.24)),
                        sy / 2.0 + radius * spall_rng.uniform(0.04, 0.2),
                        spall_rng.uniform(sz * 0.31, sz * 0.47),
                    )
                )
                spall_inward = Vector((-side * radius * 0.72, -radius * 0.72, -radius * 0.08))
            # Do not boolean-cut the loaded edge. Repeated exact booleans on a
            # bevelled cube occasionally generated a non-manifold triangle fan
            # spanning the whole front face (a large black wedge in RGB). The
            # embedded aggregate gives a stable chipped-edge cue; a measured
            # CAD/scan should replace this proxy before production realism is
            # claimed.
            aggregate_center = sample.matrix_world @ (local + spall_inward)
            exposed = make_ico(
                f"SEM_CONCRETE exposed spall aggregate {index:02d}",
                tuple(aggregate_center),
                (radius * 0.23, radius * 0.19, radius * 0.22),
                mats["aggregate"],
                sample_col,
                subdivisions=1,
                pass_index=2,
            )
            exposed.rotation_euler = (
                spall_rng.uniform(-0.7, 0.7),
                spall_rng.uniform(-0.7, 0.7),
                spall_rng.uniform(-0.7, 0.7),
            )
            exposed["semantic_class"] = "concrete_sample"

    # Real samples contain many casting voids.  Shallow boolean pits give those
    # pores true parallax and shadow instead of relying only on a flat texture.
    pore_count = int(
        int(sample_cfg.get("pore_count_base", 68))
        + int(sample_cfg.get("pore_count_damage_gain", 120)) * damage
    )
    pore_radius_min, pore_radius_max = map(
        float, sample_cfg.get("pore_radius_m", [0.00038, 0.00438])
    )
    pore_radius_power = float(
        sample_cfg.get("pore_radius_distribution_power", 2.35)
    )
    cutter_collection = ensure_collection("TEMP_BOOLEAN_CUTTERS")
    pore_shadow_count = 0
    pore_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{yaw:.9f}:{shape}:{damage:.9f}:"
        "casting-pores-v1"
    )
    for index in range(pore_count):
        face_roll = pore_rng.random()
        # Most casting voids in the LED frames are sub-millimetre to roughly
        # 2 mm; only a small tail reaches 4–5 mm.  Squaring the random value
        # prevents the regular field of large dark holes seen in the first POC.
        radius = (
            pore_radius_min
            + (pore_radius_max - pore_radius_min)
            * (pore_rng.random() ** pore_radius_power)
        ) * (1.0 + 0.16 * damage)
        if shape == "cylinder" and face_roll < 0.94:
            theta = pore_rng.uniform(-1.5, 1.5)
            face_normal = Vector((math.sin(theta), math.cos(theta), 0.0))
            local = face_normal * (sx / 2.0 + radius * 0.58)
            local.z = pore_rng.uniform(-sz * 0.44, sz * 0.44)
        elif shape == "cylinder":
            face_normal = Vector((0.0, 0.0, 1.0))
            theta = pore_rng.uniform(0.0, math.tau)
            radial = math.sqrt(pore_rng.random()) * sx * 0.42
            local = Vector(
                (
                    math.cos(theta) * radial,
                    math.sin(theta) * radial,
                    sz / 2.0 + radius * 0.58,
                )
            )
        elif face_roll < 0.74:
            face_normal = Vector((0.0, 1.0, 0.0))
            local = Vector(
                (
                    pore_rng.uniform(-sx * 0.43, sx * 0.43),
                    sy / 2.0 + radius * 0.58,
                    pore_rng.uniform(-sz * 0.42, sz * 0.42),
                )
            )
        elif face_roll < 0.94:
            side = -1.0 if pore_rng.random() < 0.5 else 1.0
            face_normal = Vector((side, 0.0, 0.0))
            local = Vector(
                (
                    side * (sx / 2.0 + radius * 0.58),
                    pore_rng.uniform(-sy * 0.4, sy * 0.4),
                    pore_rng.uniform(-sz * 0.4, sz * 0.4),
                )
            )
        else:
            face_normal = Vector((0.0, 0.0, 1.0))
            local = Vector(
                (
                    pore_rng.uniform(-sx * 0.4, sx * 0.4),
                    pore_rng.uniform(-sy * 0.4, sy * 0.4),
                    sz / 2.0 + radius * 0.58,
                )
            )
        world = sample.matrix_world @ local
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=world)
        cutter = bpy.context.object
        cutter.name = f"Concrete pore cutter {index:02d}"
        cutter.scale = (
            pore_rng.uniform(0.58, 1.48),
            pore_rng.uniform(0.62, 1.28),
            pore_rng.uniform(0.62, 1.52),
        )
        cutter.rotation_euler = (
            pore_rng.uniform(-0.55, 0.55),
            pore_rng.uniform(-0.55, 0.55),
            pore_rng.uniform(-0.55, 0.55),
        )
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        move_to_collection(cutter, cutter_collection)
        boolean = sample.modifiers.new(f"Casting air void {index:02d}", "BOOLEAN")
        boolean.operation = "DIFFERENCE"
        boolean.solver = "EXACT"
        boolean.object = cutter
        apply_modifier(sample, boolean)
        cutter_mesh = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if cutter_mesh.users == 0:
            bpy.data.meshes.remove(cutter_mesh)

        # Broad shadowless fill makes the shallow end of a true void too pale.
        # A much smaller backing grain sits safely below the nominal surface;
        # unlike the rejected full-size inner shells it cannot breach the face
        # and therefore reads as recessed depth rather than a black bead.
        if index % 5 != 0:
            pore_surface_local = local - face_normal * (radius * 0.58)
            backing_local = pore_surface_local - face_normal * (radius * 0.31)
            backing_radius = radius * 0.17
            backing = make_ico(
                f"SEM_CONCRETE recessed pore shadow {index:02d}",
                tuple(sample.matrix_world @ backing_local),
                (backing_radius, backing_radius, backing_radius),
                mats["pore_shadow"],
                sample_col,
                subdivisions=1,
                pass_index=2,
            )
            backing["semantic_class"] = "concrete_sample"
            backing["surface_detail_role"] = "recessed_pore_shadow"
            pore_shadow_count += 1

    # Do not subdivide/displace the post-boolean mesh: boolean vertices form
    # triangle fans around cavities and geometric displacement turns those fans
    # into visibly artificial radial ridges.  The concrete material already
    # supplies scale-correct micro bump; pores and spalls provide true parallax.

    rough_form_face = shape == "cube" and damage > 0.48 and rng.random() < 0.42
    if rough_form_face:
        # Some real cubes combine one smooth mould face with one locally
        # aggregate-rich/spalled face.  Embed most of each grain behind the
        # nominal plane so the silhouette remains a regular test cube rather
        # than a field of glued-on pebbles.
        for index in range(rng.randint(8, 15)):
            radius = rng.uniform(0.0008, 0.0032)
            local = Vector(
                (
                    rng.uniform(-sx * 0.43, sx * 0.43),
                    sy / 2.0 - radius * 0.30,
                    rng.uniform(-sz * 0.42, sz * 0.42),
                )
            )
            aggregate_position = sample.matrix_world @ local
            aggregate = make_ico(
                f"SEM_CONCRETE embedded rough-face aggregate {index:02d}",
                tuple(aggregate_position),
                (
                    radius * rng.uniform(0.60, 1.0),
                    radius * rng.uniform(0.20, 0.32),
                    radius * rng.uniform(0.55, 0.92),
                ),
                mats["aggregate" if index % 4 == 0 else "concrete_dark"],
                sample_col,
                subdivisions=1,
                pass_index=2,
            )
            aggregate.rotation_euler = (
                rng.uniform(-0.45, 0.45),
                rng.uniform(-0.45, 0.45),
                rng.uniform(-0.45, 0.45),
            )
            aggregate["semantic_class"] = "concrete_sample"

    # The strongest remaining real/synthetic gap in the blinded pass-9 crops
    # was localized, exposed aggregate rather than more homogeneous shader
    # noise.  Add a regime-bounded field of mostly embedded faceted grains on
    # camera-visible faces.  This RNG is independent so the same seed retains
    # its camera/RFID/paper/lighting realization during future material A/Bs.
    aggregate_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{yaw:.9f}:{shape}:{damage:.9f}:"
        f"{surface_regime}:exposed-aggregate-v1"
    )
    aggregate_count_range = list(
        map(
            int,
            sample_cfg["exposed_aggregate_count_range_by_regime"][
                surface_regime
            ],
        )
    )
    exposed_aggregate_count = aggregate_rng.randint(*aggregate_count_range)
    aggregate_radius_min, aggregate_radius_max = map(
        float, sample_cfg["exposed_aggregate_radius_m"]
    )
    exposed_aggregate_material_counts = {
        "light_aggregate": 0,
        "dark_mortar": 0,
        "body_tone": 0,
    }
    for index in range(exposed_aggregate_count):
        radius = aggregate_radius_min + (
            aggregate_radius_max - aggregate_radius_min
        ) * (aggregate_rng.random() ** 1.75)
        if shape == "cylinder":
            theta = aggregate_rng.uniform(-1.42, 1.42)
            normal = Vector((math.sin(theta), math.cos(theta), 0.0))
            local = normal * (
                sx / 2.0 - radius * aggregate_rng.uniform(0.10, 0.28)
            )
            local.z = aggregate_rng.uniform(-sz * 0.41, sz * 0.41)
            scale = (
                radius * aggregate_rng.uniform(0.48, 0.92),
                radius * aggregate_rng.uniform(0.16, 0.29),
                radius * aggregate_rng.uniform(0.44, 0.88),
            )
            aggregate_z_rotation = yaw - theta
        else:
            # Roughly four in five inclusions stay on the broad camera-facing
            # mould face; the remainder wraps to an adjacent side.
            on_front = aggregate_rng.random() < 0.82
            if on_front:
                local = Vector(
                    (
                        aggregate_rng.uniform(-sx * 0.42, sx * 0.42),
                        sy / 2.0
                        - radius * aggregate_rng.uniform(0.10, 0.28),
                        aggregate_rng.uniform(-sz * 0.41, sz * 0.41),
                    )
                )
                scale = (
                    radius * aggregate_rng.uniform(0.48, 0.92),
                    radius * aggregate_rng.uniform(0.16, 0.29),
                    radius * aggregate_rng.uniform(0.44, 0.88),
                )
                aggregate_z_rotation = yaw
            else:
                side = -1.0 if aggregate_rng.random() < 0.5 else 1.0
                local = Vector(
                    (
                        side
                        * (
                            sx / 2.0
                            - radius * aggregate_rng.uniform(0.10, 0.28)
                        ),
                        aggregate_rng.uniform(-sy * 0.20, sy * 0.42),
                        aggregate_rng.uniform(-sz * 0.40, sz * 0.40),
                    )
                )
                scale = (
                    radius * aggregate_rng.uniform(0.16, 0.29),
                    radius * aggregate_rng.uniform(0.48, 0.92),
                    radius * aggregate_rng.uniform(0.44, 0.88),
                )
                aggregate_z_rotation = yaw
        material_roll = aggregate_rng.random()
        if material_roll < 0.34:
            material_key = "aggregate"
            exposed_aggregate_material_counts["light_aggregate"] += 1
        elif material_roll < 0.54:
            material_key = "concrete_dark"
            exposed_aggregate_material_counts["dark_mortar"] += 1
        else:
            material_key = "concrete"
            exposed_aggregate_material_counts["body_tone"] += 1
        aggregate = make_ico(
            f"SEM_CONCRETE exposed aggregate {index:02d}",
            tuple(sample.matrix_world @ local),
            scale,
            mats[material_key],
            sample_col,
            subdivisions=1,
            pass_index=2,
        )
        aggregate.rotation_euler = (
            aggregate_rng.uniform(-0.30, 0.30),
            aggregate_rng.uniform(-0.30, 0.30),
            aggregate_z_rotation
            + aggregate_rng.uniform(-0.28, 0.28),
        )
        aggregate["semantic_class"] = "concrete_sample"
        aggregate["surface_regime"] = surface_regime
        aggregate["surface_detail_role"] = "exposed_aggregate"

    # One or two hairline cracks are present only on more damaged samples.
    crack_count = 1 if damage > 0.48 else 0
    if damage > 0.60:
        crack_count += 1
    for crack_index in range(crack_count):
        start_x = rng.uniform(-sx * 0.28, sx * 0.22)
        start_z = rng.uniform(-sz * 0.28, sz * 0.26)
        local_points = []
        x = start_x
        z = start_z
        for _step in range(rng.randint(4, 7)):
            surface_y = (
                math.sqrt(max(0.0, (sx / 2.0) ** 2 - x**2)) + 0.00010
                if shape == "cylinder"
                else sy / 2.0 + 0.00010
            )
            local_points.append(Vector((x, surface_y, z)))
            x += rng.uniform(-0.008, 0.009)
            z -= rng.uniform(0.005, 0.013)
        world_points = [sample.matrix_world @ point for point in local_points]
        crack = make_curve_polyline(
            f"SEM_CONCRETE hairline crack {crack_index}",
            world_points,
            rng.uniform(0.00007, 0.00015),
            mats["concrete_dark"],
            sample_col,
            pass_index=2,
        )
        crack["semantic_class"] = "concrete_sample"

    # Fresh LED frames across tasks 9-14 and all REF machine/camera groups
    # consistently show a localized, dirty load zone immediately below the
    # upper platen.  It is not a second object and must not become a detector
    # shortcut with a new silhouette.  Several sub-millimetre, mostly embedded
    # ellipsoids therefore form one irregular ochre/dark residue cluster.  The
    # independent RNG keeps every existing sample, RFID, paper, camera and
    # lighting decision stable for same-seed before/after comparisons.
    weathering_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:{surface_regime}:"
        "top-load-weathering-v1"
    )
    weathering_count_range = list(
        map(
            int,
            sample_cfg["top_load_weathering_patch_count_range_by_regime"][
                surface_regime
            ],
        )
    )
    top_load_weathering_patch_count = weathering_rng.randint(
        *weathering_count_range
    )
    weathering_width_min, weathering_width_max = map(
        float, sample_cfg["top_load_weathering_width_fraction_range"]
    )
    weathering_height_min, weathering_height_max = map(
        float, sample_cfg["top_load_weathering_height_fraction_range"]
    )
    weathering_depth_min, weathering_depth_max = map(
        float,
        sample_cfg["top_load_weathering_depth_below_top_fraction_range"],
    )
    weathering_thickness_min, weathering_thickness_max = map(
        float, sample_cfg["top_load_weathering_half_thickness_m"]
    )
    weathering_cluster_theta = weathering_rng.uniform(-0.72, 0.72)
    weathering_cluster_x = weathering_rng.uniform(-0.24, 0.24) * sx
    weathering_side_sign = -1.0 if weathering_rng.random() < 0.5 else 1.0
    weathering_cluster_depth = weathering_rng.uniform(
        weathering_depth_min, weathering_depth_max
    )
    weathering_material_counts = {"ochre": 0, "dark": 0}
    for index in range(top_load_weathering_patch_count):
        patch_width = sx * weathering_rng.uniform(
            weathering_width_min, weathering_width_max
        )
        patch_height = sz * weathering_rng.uniform(
            weathering_height_min, weathering_height_max
        )
        half_thickness = weathering_rng.uniform(
            weathering_thickness_min, weathering_thickness_max
        )
        patch_depth_fraction = max(
            weathering_depth_min,
            min(
                weathering_depth_max,
                weathering_cluster_depth
                + weathering_rng.uniform(-0.025, 0.025),
            ),
        )
        local_z = min(
            sz / 2.0 - patch_height * 0.52,
            sz / 2.0 - sz * patch_depth_fraction,
        )
        if shape == "cylinder":
            theta = max(
                -1.40,
                min(
                    1.40,
                    weathering_cluster_theta
                    + weathering_rng.uniform(-0.16, 0.16),
                ),
            )
            normal = Vector((math.sin(theta), math.cos(theta), 0.0))
            local = normal * (sx / 2.0 - half_thickness * 0.86)
            local.z = local_z
            patch_scale = (
                patch_width / 2.0,
                half_thickness,
                patch_height / 2.0,
            )
            patch_yaw = yaw + theta
        else:
            # Keep most of the cluster on the front mould face and let a
            # bounded tail wrap onto one adjacent face, as in cam-11 cubes.
            on_front = index % 4 != 3
            if on_front:
                local = Vector(
                    (
                        max(
                            -sx * 0.42,
                            min(
                                sx * 0.42,
                                weathering_cluster_x
                                + weathering_rng.uniform(-0.07, 0.07) * sx,
                            ),
                        ),
                        sy / 2.0 - half_thickness * 0.86,
                        local_z,
                    )
                )
                patch_scale = (
                    patch_width / 2.0,
                    half_thickness,
                    patch_height / 2.0,
                )
            else:
                local = Vector(
                    (
                        weathering_side_sign
                        * (sx / 2.0 - half_thickness * 0.86),
                        max(
                            -sy * 0.18,
                            min(
                                sy * 0.42,
                                sy * 0.26
                                + weathering_rng.uniform(-0.06, 0.06) * sy,
                            ),
                        ),
                        local_z,
                    )
                )
                patch_scale = (
                    half_thickness,
                    patch_width / 2.0,
                    patch_height / 2.0,
                )
            patch_yaw = yaw
        material_key = (
            "concrete_load_stain_ochre"
            if weathering_rng.random() < 0.68
            else "concrete_load_stain_dark"
        )
        weathering_material_counts[
            "ochre" if material_key.endswith("ochre") else "dark"
        ] += 1
        patch = make_ico(
            f"SEM_CONCRETE upper load-zone residue {index:02d}",
            tuple(sample.matrix_world @ local),
            patch_scale,
            mats[material_key],
            sample_col,
            subdivisions=2,
            pass_index=2,
        )
        patch.rotation_euler.z = patch_yaw
        patch.visible_shadow = False
        patch["semantic_class"] = "concrete_sample"
        patch["surface_regime"] = surface_regime
        patch["surface_detail_role"] = "top_load_weathering"

    # Exposed aggregate/chipped caps along the top perimeter.
    fragment_count = int(1 + damage * 4)
    for index in range(fragment_count):
        if shape == "cylinder":
            theta = rng.uniform(-1.55, 1.55)
            radial = sx / 2.0 - rng.uniform(0.0, 0.009)
            local_x = math.sin(theta) * radial
            local_y = -math.cos(theta) * radial
        else:
            edge = index % 4
            if edge in (0, 1):
                local_x = (sx / 2.0 - rng.uniform(0.0, 0.012)) * (-1.0 if edge == 0 else 1.0)
                local_y = rng.uniform(-sy * 0.46, sy * 0.46)
            else:
                local_x = rng.uniform(-sx * 0.46, sx * 0.46)
                local_y = (sy / 2.0 - rng.uniform(0.0, 0.012)) * (-1.0 if edge == 2 else 1.0)
        fragment_position = sample.matrix_world @ Vector(
            (local_x, local_y, sz / 2.0 + rng.uniform(-0.0065, -0.0022))
        )
        fragment = make_ico(
            f"SEM_CONCRETE chipped aggregate {index:02d}",
            tuple(fragment_position),
            (
                rng.uniform(0.0010, 0.0032),
                rng.uniform(0.0010, 0.0030),
                rng.uniform(0.0006, 0.0016),
            ),
            mats["aggregate" if index % 3 == 0 else "concrete"],
            sample_col,
            subdivisions=1,
            pass_index=2,
        )
        fragment["semantic_class"] = "concrete_sample"

    # Fresh time-diverse LED and IR review shows regular certified specimens but
    # much rougher loaded edges than the earlier smooth proxy.  Add only shallow,
    # mostly embedded irregular grains: they create silhouette/parallax variation
    # without changing the nominal sample size or risking unstable boolean cuts.
    relief_count_range = list(
        map(
            int,
            sample_cfg["edge_relief_count_range_by_regime"][surface_regime],
        )
    )
    edge_relief_count = surface_rng.randint(*relief_count_range)
    relief_min, relief_max = map(float, sample_cfg["edge_relief_size_m"])
    for index in range(edge_relief_count):
        radius = relief_min + (relief_max - relief_min) * (surface_rng.random() ** 2.1)
        if shape == "cylinder":
            theta = surface_rng.uniform(-1.52, 1.52)
            normal = Vector((math.sin(theta), math.cos(theta), 0.0))
            center_radius = sx / 2.0 - radius * surface_rng.uniform(0.52, 0.74)
            local = normal * center_radius
            local.z = sz / 2.0 - radius * surface_rng.uniform(0.52, 0.82)
            scale = (
                radius * surface_rng.uniform(0.55, 0.92),
                radius * surface_rng.uniform(0.48, 0.84),
                radius * surface_rng.uniform(0.35, 0.68),
            )
        else:
            edge_mode = surface_rng.randrange(3)
            side = -1.0 if surface_rng.random() < 0.5 else 1.0
            if edge_mode == 0:
                local = Vector(
                    (
                        surface_rng.uniform(-sx * 0.44, sx * 0.44),
                        sy / 2.0 - radius * surface_rng.uniform(0.54, 0.76),
                        sz / 2.0 - radius * surface_rng.uniform(0.50, 0.80),
                    )
                )
            elif edge_mode == 1:
                local = Vector(
                    (
                        side * (sx / 2.0 - radius * surface_rng.uniform(0.54, 0.76)),
                        surface_rng.uniform(-sy * 0.20, sy * 0.43),
                        sz / 2.0 - radius * surface_rng.uniform(0.52, 0.82),
                    )
                )
            else:
                local = Vector(
                    (
                        side * (sx / 2.0 - radius * surface_rng.uniform(0.54, 0.78)),
                        sy / 2.0 - radius * surface_rng.uniform(0.54, 0.78),
                        surface_rng.uniform(-sz * 0.35, sz * 0.35),
                    )
                )
            scale = (
                radius * surface_rng.uniform(0.48, 0.90),
                radius * surface_rng.uniform(0.35, 0.68),
                radius * surface_rng.uniform(0.42, 0.78),
            )
        relief_position = sample.matrix_world @ local
        relief = make_ico(
            f"SEM_CONCRETE bounded edge relief {index:02d}",
            tuple(relief_position),
            scale,
            mats[
                "aggregate"
                if (surface_regime == "spalled" and index % 3 == 0)
                else "concrete_dark"
                if index % 5 == 0
                else "concrete"
            ],
            sample_col,
            subdivisions=1,
            pass_index=2,
        )
        relief.rotation_euler = (
            surface_rng.uniform(-0.8, 0.8),
            surface_rng.uniform(-0.8, 0.8),
            surface_rng.uniform(-0.8, 0.8),
        )
        relief["semantic_class"] = "concrete_sample"
        relief["surface_regime"] = surface_regime

    if shape == "cylinder":
        # Repeated boolean pores split the cylindrical side into triangle fans.
        # Smooth normals across those fans produce long fake vertical ribs.
        # With 256 radial segments, flat post-boolean normals remain visually
        # continuous at the target resolution and remove that artefact.
        for polygon in sample.data.polygons:
            polygon.use_smooth = False

    state = {
        "shape": shape,
        "location_m": [px, py, pz],
        "dimensions_m": [sx, sy, sz],
        "yaw_deg": math.degrees(yaw),
        "damage": damage,
        "pore_count": pore_count,
        "pore_shadow_count": pore_shadow_count,
        "pore_shadow_profile": "subsurface_recessed_backing_v1",
        "pore_radius_range_m": [pore_radius_min, pore_radius_max],
        "pore_radius_distribution_power": pore_radius_power,
        "rough_form_face": rough_form_face,
        "surface_regime": surface_regime,
        "surface_profile": "cast_skin_with_scale_bounded_visible_pores_exposed_aggregate_faceted_spall_and_load_zone_v9",
        "body_profile": body_profile,
        "spall_notch_m": spall_notch_m,
        "spall_notch_side": spall_notch_side,
        "spall_side_selection_profile": spall_side_selection_profile,
        "spall_notch_realization": spall_notch_realization,
        "spall_fracture_tooth_count": spall_fracture_tooth_count,
        "spall_fracture_cavity_count": spall_fracture_cavity_count,
        "spall_notch_status": sample_cfg["spalled_cube_notch_status"],
        "cube_spall_aggregate_count": cube_spall_aggregate_count,
        "cylinder_spall_size_m": cylinder_spall_size_m,
        "cylinder_spall_angle_deg": cylinder_spall_angle_deg,
        "cylinder_spall_aggregate_count": (
            cylinder_spall_aggregate_count
        ),
        "cylinder_spall_status": sample_cfg["spalled_cylinder_cavity_status"],
        "exposed_aggregate_count": exposed_aggregate_count,
        "exposed_aggregate_radius_range_m": [
            aggregate_radius_min,
            aggregate_radius_max,
        ],
        "exposed_aggregate_material_counts": (
            exposed_aggregate_material_counts
        ),
        "edge_relief_count": edge_relief_count,
        "edge_relief_size_range_m": [relief_min, relief_max],
        "top_load_weathering_patch_count": top_load_weathering_patch_count,
        "top_load_weathering_material_counts": weathering_material_counts,
        "top_load_weathering_profile": "clustered_submillimetre_embedded_ochre_dark_residue_v1",
        "top_load_weathering_status": sample_cfg[
            "top_load_weathering_status"
        ],
        "surface_regime_distribution_status": sample_cfg["surface_regime_status"],
    }
    return sample, state


def build_rfid_geometry(
    cfg: dict,
    mats: dict,
    instance_index: int = 0,
    pass_index: int = 1,
) -> tuple[bpy.types.Object, list[bpy.types.Object], bpy.types.Object]:
    tag_col = ensure_collection("RFID_TAG")
    tag_cfg = cfg["rfid_tag"]
    length, width, thickness = map(float, tag_cfg["size_m"])
    prefix = f"SEM_RFID_{instance_index:02d}"
    root = bpy.data.objects.new(f"{prefix}_ROOT", None)
    tag_col.objects.link(root)
    root["semantic_class"] = "rfid_tag"
    root["instance_id"] = instance_index
    root["instance_pass_index"] = pass_index
    root["physical_size_m"] = [length, width, thickness]
    parts: list[bpy.types.Object] = []

    substrate = make_box(
        f"{prefix} film substrate",
        (0.0, 0.0, 0.0),
        (length, thickness, width),
        mats["rfid_front"],
        tag_col,
        bevel=0.000025,
        pass_index=pass_index,
    )
    substrate["semantic_class"] = "rfid_tag"
    parent_local(substrate, root)
    parts.append(substrate)

    front_y = -thickness * 0.62
    back_y = thickness * 0.62
    x0 = length / 2.0 - 0.0012
    inner = 0.0021
    z0 = width / 2.0 - 0.00075
    left = [
        (-x0, front_y, -z0),
        (-inner * 1.55, front_y, -z0),
        (-inner, front_y, -0.00115),
        (-0.00065, front_y, 0.0),
        (-inner, front_y, 0.00115),
        (-inner * 1.55, front_y, z0),
        (-x0, front_y, z0),
    ]
    right = [(-x, y, z) for x, y, z in reversed(left)]
    for name, vertices in (("left", left), ("right", right)):
        wing = make_polygon(
            f"{prefix} copper {name} wing",
            vertices,
            mats["copper"],
            tag_col,
            pass_index=pass_index,
        )
        wing["semantic_class"] = "rfid_tag"
        parent_local(wing, root)
        parts.append(wing)

    # Long asymmetric slots and center chevrons reproduce the supplied real tag.
    slot_specs = [
        (-0.013, -0.00205, 0.0145, 0.00145),
        (0.013, 0.00205, 0.0145, 0.00145),
    ]
    for index, (x, z, slot_l, slot_w) in enumerate(slot_specs):
        slot = make_box(
            f"{prefix} antenna slot {index}",
            (x, front_y - 0.000018, z),
            (slot_l, 0.000025, slot_w),
            mats["rfid_slot"],
            tag_col,
            bevel=0.00005,
            pass_index=pass_index,
        )
        slot["semantic_class"] = "rfid_tag"
        parent_local(slot, root)
        parts.append(slot)

    # Slightly domed black epoxy seal, about 5 mm across as observed in ODT photos.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0, location=(0.0, front_y - 0.00042, 0.0))
    dome = bpy.context.object
    dome.name = f"{prefix} central epoxy dome"
    dome.scale = (tag_cfg["center_dome_diameter_m"] / 2.0, 0.00055, tag_cfg["center_dome_diameter_m"] / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(dome, mats["black_plastic"])
    dome.pass_index = pass_index
    dome["semantic_class"] = "rfid_tag"
    move_to_collection(dome, tag_col)
    parent_local(dome, root)
    parts.append(dome)

    # Back is a distinct darker matte film and carries a small square package cue.
    back = make_box(
        f"{prefix} matte back layer",
        (0.0, back_y, 0.0),
        (length - 0.00025, 0.000025, width - 0.00025),
        mats["rfid_back"],
        tag_col,
        bevel=0.00002,
        pass_index=pass_index,
    )
    back["semantic_class"] = "rfid_tag"
    parent_local(back, root)
    parts.append(back)
    package = make_box(
        f"{prefix} back package",
        (0.0, back_y + 0.00019, 0.0),
        (0.0032, 0.00034, 0.0032),
        mats["black_plastic"],
        tag_col,
        bevel=0.00028,
        pass_index=pass_index,
    )
    package["semantic_class"] = "rfid_tag"
    parent_local(package, root)
    parts.append(package)
    return root, parts, substrate


def place_rfid(
    cfg: dict,
    rng: random.Random,
    root: bpy.types.Object,
    sample_state: dict,
    machine_state: dict[str, float],
    camera_name: str,
    instance_index: int = 0,
    forced_state: str | None = None,
) -> dict:
    tag_cfg = cfg["rfid_tag"]
    placement_weights = tag_cfg.get("placement_weights", tag_cfg["state_weights"])
    state = forced_state or weighted_choice(rng, placement_weights)
    angle_range = tag_cfg["in_plane_rotation_deg"]
    in_plane = math.radians(rng.uniform(*angle_range))
    sx, sy, sz = sample_state["dimensions_m"]
    sample_shape = sample_state.get("shape", "cube")
    px, py, pz = sample_state["location_m"]
    sample_yaw = math.radians(float(sample_state["yaw_deg"]))
    sample_rotation = Quaternion(Vector((0.0, 0.0, 1.0)), sample_yaw)
    missing = state == "missing"

    if missing:
        root.hide_render = True
        root.hide_viewport = True
        for child in root.children:
            child.hide_render = True
            child.hide_viewport = True
        location = [0.0, 0.0, -5.0]
        target_normal = Vector((0.0, 1.0, 0.0))
    elif state == "sample_front":
        front_slots = (
            (-0.038, 0.035),
            (0.034, 0.032),
            (-0.035, -0.028),
            (0.035, -0.026),
            (0.0, 0.002),
        )
        slot_x, slot_z = front_slots[instance_index % len(front_slots)]
        if sample_shape == "cylinder":
            slot_z *= 2.55
        local_x = slot_x + rng.uniform(-0.004, 0.004)
        surface_y = (
            math.sqrt(max(0.0, (sx / 2.0) ** 2 - local_x**2))
            if sample_shape == "cylinder"
            else sy / 2.0
        )
        local = Vector((local_x, surface_y + 0.00032, slot_z + rng.uniform(-0.004, 0.004)))
        location = list(Vector((px, py, pz)) + sample_rotation @ local)
        target_normal = sample_rotation @ (
            Vector((local_x, surface_y, 0.0)).normalized()
            if sample_shape == "cylinder"
            else Vector((0.0, 1.0, 0.0))
        )
    elif state == "sample_side":
        # Put a side-mounted tag on the camera-facing face. This keeps the
        # requested state meaningful instead of silently producing an
        # unintended fully-occluded positive sample.
        camera_x = float(cfg["cameras"][camera_name]["location_m"][0])
        side = (1.0 if camera_x >= px else -1.0) * (-1.0 if instance_index % 3 == 2 else 1.0)
        if sample_shape == "cylinder":
            theta = side * rng.uniform(0.78, 1.28)
            radial = Vector((math.sin(theta), math.cos(theta), 0.0))
            local = radial * (sx / 2.0 + 0.00032)
            local.z = rng.uniform(-sz * 0.28, sz * 0.28)
        else:
            radial = Vector((side, 0.0, 0.0))
            local = Vector(
                (
                    side * (sx / 2.0 + 0.00032),
                    rng.uniform(-0.025, 0.025),
                    rng.uniform(-0.03, 0.03),
                )
            )
        location = list(Vector((px, py, pz)) + sample_rotation @ local)
        target_normal = sample_rotation @ radial
    elif state in {"plate_gap_top", "plate_gap_bottom"}:
        # Real captures contain many tags pinched between the specimen and a
        # circular platen.  Only a controlled strip protrudes, which is an
        # important hard-positive regime for detection.
        top = state == "plate_gap_top"
        edge_mode = instance_index % 3
        overhang = rng.uniform(0.012, 0.027)
        if sample_shape == "cylinder":
            theta = (-0.78, 0.0, 0.78)[edge_mode]
            radial = Vector((math.sin(theta), math.cos(theta), 0.0))
            local = radial * (sx / 2.0 + overhang)
            local.z = sz / 2.0 if top else -sz / 2.0
        elif edge_mode == 0:
            local = Vector(
                (
                    rng.uniform(-sx * 0.34, sx * 0.34),
                    sy / 2.0 + overhang,
                    sz / 2.0 if top else -sz / 2.0,
                )
            )
        else:
            side = -1.0 if edge_mode == 1 else 1.0
            local = Vector(
                (
                    side * (sx / 2.0 + overhang),
                    rng.uniform(-sy * 0.3, sy * 0.3),
                    sz / 2.0 if top else -sz / 2.0,
                )
            )
        location = list(Vector((px, py, pz)) + sample_rotation @ local)
        location[2] += 0.00016 if top else 0.0002
        target_normal = Vector((0.0, 0.0, 1.0))
    else:
        platen_radius = float(machine_state["platen_radius_m"])
        sample_radius = max(sx, sy) / 2.0
        minimum_radius = min(platen_radius - 0.038, sample_radius + 0.025)
        maximum_radius = platen_radius - 0.034
        radius = rng.uniform(max(0.095, minimum_radius), max(0.096, maximum_radius))
        # Both loose orientations belong on the camera-facing half of the lower
        # platen.  ``loose_back`` changes which film side faces the camera; it
        # must not move the tag behind the concrete where it becomes a hidden
        # positive label.
        theta = rng.uniform(0.58, 2.52) + 0.21 * (instance_index % 3 - 1)
        location = [
            math.cos(theta) * radius,
            machine_state["platen_center_y"] + math.sin(theta) * radius * 0.62,
            # Keep the thin film just above the physical contact face instead
            # of floating several millimetres over the corrected platen.
            machine_state["lower_platen_top_z"] + 0.00035,
        ]
        target_normal = Vector((0.0, 0.0, 1.0))

    source_normal = Vector((0.0, 1.0, 0.0)) if state == "loose_back" else Vector((0.0, -1.0, 0.0))
    alignment = source_normal.rotation_difference(target_normal)
    spin = Quaternion(target_normal, in_plane)
    root.matrix_world = Matrix.Translation(Vector(location)) @ (spin @ alignment).to_matrix().to_4x4()
    root["state"] = state
    return {
        "instance_id": instance_index,
        "state": state,
        "visible_side": "back" if state == "loose_back" else "front",
        "location_m": location,
        "in_plane_rotation_deg": math.degrees(in_plane),
        "missing": missing,
    }


def sample_front_surface_matrix(
    sample_state: dict,
    rng: random.Random,
    *,
    in_plane_deg: float,
) -> Matrix:
    """Return an outward-facing transform on the visible concrete face."""

    sx, sy, sz = map(float, sample_state["dimensions_m"])
    px, py, pz = map(float, sample_state["location_m"])
    sample_shape = sample_state.get("shape", "cube")
    sample_rotation = Quaternion(
        Vector((0.0, 0.0, 1.0)),
        math.radians(float(sample_state["yaw_deg"])),
    )
    local_x = rng.uniform(-sx * 0.24, sx * 0.24)
    local_z = rng.uniform(-sz * 0.22, sz * 0.22)
    if sample_shape == "cylinder":
        surface_y = math.sqrt(max(0.0, (sx / 2.0) ** 2 - local_x**2))
        local_normal = Vector((local_x, surface_y, 0.0)).normalized()
    else:
        surface_y = sy / 2.0
        local_normal = Vector((0.0, 1.0, 0.0))
    local = Vector((local_x, surface_y + 0.00055, local_z))
    location = Vector((px, py, pz)) + sample_rotation @ local
    target_normal = sample_rotation @ local_normal
    alignment = Vector((0.0, -1.0, 0.0)).rotation_difference(target_normal)
    spin = Quaternion(target_normal, math.radians(in_plane_deg))
    return Matrix.Translation(location) @ (spin @ alignment).to_matrix().to_4x4()


def build_paper_labels(
    cfg: dict,
    mats: dict,
    rng: random.Random,
    sample_state: dict,
    tag_roots: list[bpy.types.Object],
    tag_states: list[dict],
) -> list[dict]:
    """Add non-target paper forms, including physically correct RFID occlusion."""

    paper_cfg = cfg.get("paper_label", {})
    if not paper_cfg.get("enabled", False):
        return []
    # A 70–95 mm flat form visibly bridges a 126 mm cylinder.  Until a
    # segmented/conformed paper mesh is calibrated, only the planar cube face
    # receives paper; this is safer than publishing a floating synthetic cue.
    if sample_state.get("shape") != "cube":
        return []
    paper_col = ensure_collection("PAPER_LABELS")
    count = int(weighted_choice(rng, paper_cfg.get("count_weights", {"0": 1.0})))
    paper_length, paper_height, paper_thickness = map(
        float,
        paper_cfg.get("size_m", [0.085, 0.06, 0.00016]),
    )
    link_states = set(paper_cfg.get("rfid_link_states", ["sample_front", "sample_side"]))
    candidates = [
        index
        for index, state in enumerate(tag_states)
        if not state["missing"] and state["state"] in link_states
    ]
    records: list[dict] = []

    for paper_index in range(count):
        colour_rng = random.Random(
            f"{sample_state.get('location_m')}:{sample_state.get('yaw_deg')}:"
            f"{paper_index}:paper-colour-v1"
        )
        colour_profile = weighted_choice(
            colour_rng,
            paper_cfg.get("colour_profile_weights", {"aged_form": 1.0}),
        )
        linked_tag_index: int | None = None
        occlusion_mode = "independent"
        visible_tip_fraction: float | None = None
        use_linked_tag = (
            bool(candidates)
            and rng.random() < float(paper_cfg.get("rfid_under_paper_probability", 0.55))
        )
        if use_linked_tag:
            linked_tag_index = candidates.pop(rng.randrange(len(candidates)))
            occlusion_mode = weighted_choice(
                rng,
                paper_cfg.get(
                    "rfid_occlusion_weights",
                    {"partial_tip_visible": 0.78, "fully_hidden": 0.22},
                ),
            )
            base_matrix = tag_roots[linked_tag_index].matrix_world.copy()
        else:
            base_matrix = sample_front_surface_matrix(
                sample_state,
                rng,
                in_plane_deg=rng.uniform(
                    *map(float, paper_cfg.get("rotation_deg", [-8.0, 8.0]))
                ),
            )

        paper_root = bpy.data.objects.new(f"Paper form {paper_index:02d} root", None)
        paper_col.objects.link(paper_root)
        paper_root.matrix_world = base_matrix

        paper_x = rng.uniform(-0.004, 0.004)
        paper_z = rng.uniform(-0.003, 0.003)
        if occlusion_mode == "partial_tip_visible":
            visible_range = list(
                map(float, paper_cfg.get("visible_tag_tip_fraction_range", [0.10, 0.32]))
            )
            visible_tip_fraction = rng.uniform(visible_range[0], visible_range[1])
            tag_half = float(cfg["rfid_tag"]["size_m"][0]) / 2.0
            visible_length = float(cfg["rfid_tag"]["size_m"][0]) * visible_tip_fraction
            visible_direction = -1.0 if rng.random() < 0.5 else 1.0
            cover_edge = visible_direction * (tag_half - visible_length)
            paper_x = cover_edge - visible_direction * paper_length / 2.0
            paper_z = rng.uniform(-0.004, 0.004)
        elif occlusion_mode == "fully_hidden":
            paper_x = rng.uniform(-0.004, 0.004)
            paper_z = rng.uniform(-0.003, 0.003)

        surface_y = -0.00124 if linked_tag_index is not None else -0.00012
        paper = make_wrinkled_paper(
            f"Paper form {paper_index:02d}",
            (paper_x, surface_y, paper_z),
            (paper_length, paper_thickness, paper_height),
            mats[f"paper_{colour_profile}"],
            paper_col,
            rng,
        )
        paper["occlusion_role"] = "non_target_opaque"
        paper["linked_rfid_instance_id"] = (
            int(tag_states[linked_tag_index]["instance_id"])
            if linked_tag_index is not None
            else -1
        )
        parent_local(paper, paper_root)

        # Printed header and form rows are geometry rather than an image with a
        # reusable ID.  This supplies realistic scale/ink without leaking QR,
        # timestamp or device-specific text shortcuts into synthetic training.
        ink_y = surface_y - paper_thickness * 0.65
        for line_index in range(8):
            line_length = paper_length * rng.uniform(0.38, 0.79)
            line_x = paper_x - paper_length * 0.08 + line_length * 0.04
            line_z = paper_z + paper_height * (0.31 - line_index * 0.075)
            line = make_box(
                f"Paper form {paper_index:02d} print line {line_index:02d}",
                (line_x, ink_y, line_z),
                (line_length, 0.000035, 0.00065 if line_index else 0.0011),
                mats["paper_ink"],
                paper_col,
                0.0,
            )
            parent_local(line, paper_root)
        # Real forms mix printed rows with short, irregular pen strokes.
        # These non-readable polylines supply the right visual frequency
        # without baking device IDs, QR codes or timestamp shortcuts.
        handwriting_range = list(
            map(int, paper_cfg.get("handwriting_stroke_range", [3, 6]))
        )
        handwriting_count = rng.randint(handwriting_range[0], handwriting_range[1])
        for stroke_index in range(handwriting_count):
            start_x = paper_x + rng.uniform(-paper_length * 0.30, paper_length * 0.16)
            start_z = paper_z + rng.uniform(-paper_height * 0.26, paper_height * 0.20)
            points: list[Vector] = []
            x = start_x
            z = start_z
            for _ in range(rng.randint(3, 5)):
                points.append(Vector((x, ink_y - 0.000055, z)))
                x += rng.uniform(paper_length * 0.045, paper_length * 0.11)
                z += rng.uniform(-paper_height * 0.045, paper_height * 0.045)
            stroke = make_curve_polyline(
                f"Paper form {paper_index:02d} handwriting {stroke_index:02d}",
                points,
                rng.uniform(0.00012, 0.00022),
                mats["paper_ink"],
                paper_col,
            )
            parent_local(stroke, paper_root)
        for tape_index, tape_z in enumerate(
            (paper_z - paper_height * 0.47, paper_z + paper_height * 0.47)
        ):
            tape = make_box(
                f"Paper form {paper_index:02d} tape {tape_index}",
                (paper_x + rng.uniform(-0.013, 0.013), ink_y - 0.00004, tape_z),
                (paper_length * rng.uniform(0.22, 0.38), 0.000045, 0.007),
                mats["paper_tape"],
                paper_col,
                0.00001,
            )
            tape.rotation_euler.y = math.radians(rng.uniform(-5.0, 5.0))
            parent_local(tape, paper_root)

        paper_root["occlusion_mode"] = occlusion_mode
        paper_root["linked_rfid_instance_id"] = (
            int(tag_states[linked_tag_index]["instance_id"])
            if linked_tag_index is not None
            else -1
        )
        if linked_tag_index is not None:
            tag_states[linked_tag_index]["paper_occlusion"] = {
                "mode": occlusion_mode,
                "paper_index": paper_index,
                "visible_tip_fraction_target": visible_tip_fraction,
            }
        records.append(
            {
                "paper_index": paper_index,
                "occlusion_mode": occlusion_mode,
                "linked_rfid_instance_id": (
                    int(tag_states[linked_tag_index]["instance_id"])
                    if linked_tag_index is not None
                    else None
                ),
                "visible_tag_tip_fraction_target": visible_tip_fraction,
                "size_m": [paper_length, paper_height, paper_thickness],
                "colour_profile": colour_profile,
                "target_class": None,
                "orange_decoy_policy": (
                    "non-target physical occluder; never RFID even when orange"
                    if colour_profile == "orange_decoy"
                    else "not applicable"
                ),
                "surface_profile": "irregular_grid_sheet_plus_stained_fibre_and_broad_wrinkle_normal",
                "print_row_count": 8,
                "handwriting_stroke_count": handwriting_count,
                "tape_count": 2,
            }
        )
    return records


def add_area_light(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    color_srgb: tuple[float, float, float],
    energy: float,
    size: float,
    size_y: float,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = size_y
    data.color = srgb(color_srgb)[:3]
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    point_object_at(obj, target)
    return obj


def build_lighting(
    cfg: dict,
    mats: dict,
    rng: random.Random,
    sample_state: dict | None = None,
    machine_state: dict[str, float] | None = None,
) -> dict:
    lights_col = ensure_collection("EBIS_LIGHTS")
    profiles = cfg["lighting_profiles"]
    profile_name = weighted_choice(rng, {name: value["weight"] for name, value in profiles.items()})
    profile = profiles[profile_name]
    energy_scale = rng.uniform(*profile["energy_scale"])
    door_angle = float((machine_state or {}).get("door", {}).get("angle_deg", 90.0))
    door_open_factor = max(0.22, min(1.0, math.sin(math.radians(max(0.0, door_angle)))))
    effective_door_fill = float(profile["door_fill"]) * door_open_factor
    kelvin = float(profile["temperature_k"]) + rng.uniform(-180.0, 180.0)
    light_color = kelvin_to_srgb(kelvin)

    emitter, emitter_shader, _ = new_principled(
        f"LED diffuser {profile_name}", srgb(light_color), roughness=0.28
    )
    set_input(emitter_shader, ("Emission Color",), srgb(light_color))
    set_input(
        emitter_shader,
        ("Emission Strength",),
        float(cfg["machine"].get("led_emission_strength", 4.8)) * energy_scale,
    )

    # Canonical geometry: a narrow opal channel follows the back, left and
    # right inner walls at the upper platen level.  It is a U-shaped strip,
    # not a large luminous back panel and not two vertical bars.
    width = float(cfg["machine"]["chamber_width_m"])
    depth = float(cfg["machine"]["chamber_depth_m"])
    half_w = width / 2.0
    back_y = float(cfg["machine"]["chamber_depth_m"]) / 2.0
    led_height = (
        float(machine_state["upper_platen_bottom_z"])
        + float(cfg["machine"].get("led_vertical_offset_m", 0.006))
        if machine_state
        else (
            float(sample_state["location_m"][2]) + float(sample_state["dimensions_m"][2]) / 2.0 + 0.006
            if sample_state
            else 0.427
        )
    )
    channel_height = float(cfg["machine"].get("led_channel_height_m", 0.034))
    diffuser_height = float(cfg["machine"].get("led_diffuser_height_m", 0.018))
    front_clearance = float(cfg["machine"].get("led_front_clearance_m", 0.055))
    side_end_y = back_y - 0.018
    default_side_start_y = -depth / 2.0 + front_clearance
    # The LED carrier sits in the upper rectangular beam and spans both sides
    # even where the left access wall opens below it.
    side_starts = {"left": default_side_start_y, "right": default_side_start_y}
    side_lengths = {name: side_end_y - start for name, start in side_starts.items()}
    back_emitter_length = width - 0.082
    total_emitter_length = back_emitter_length + sum(side_lengths.values())
    total_energy = float(cfg["machine"].get("led_area_energy_w", 34.0)) * energy_scale

    make_box(
        "U LED back aluminium channel",
        (0.0, back_y - 0.023, led_height),
        (width - 0.052, 0.028, channel_height),
        mats["dark_steel"],
        lights_col,
        0.003,
    )
    make_box(
        "U LED back opal diffuser",
        (0.0, back_y - 0.039, led_height),
        (width - 0.07, 0.005, diffuser_height),
        emitter,
        lights_col,
        0.002,
    )
    add_area_light(
        "U LED back diffused area",
        (0.0, back_y - 0.045, led_height - 0.002),
        (0.0, 0.045, led_height - 0.027),
        light_color,
        total_energy * back_emitter_length / total_emitter_length,
        width - 0.082,
        max(diffuser_height * 4.0, 0.048),
        lights_col,
    )
    for side_name, sign in (("left", -1.0), ("right", 1.0)):
        side_length = side_lengths[side_name]
        side_center_y = (side_end_y + side_starts[side_name]) / 2.0
        housing_x = sign * (half_w - 0.023)
        diffuser_x = sign * (half_w - 0.039)
        make_box(
            f"U LED {side_name} aluminium channel",
            (housing_x, side_center_y, led_height),
            (0.028, side_length, channel_height),
            mats["dark_steel"],
            lights_col,
            0.003,
        )
        make_box(
            f"U LED {side_name} opal diffuser",
            (diffuser_x, side_center_y, led_height),
            (0.005, side_length - 0.022, diffuser_height),
            emitter,
            lights_col,
            0.002,
        )
        add_area_light(
            f"U LED {side_name} diffused area",
            (sign * (half_w - 0.045), side_center_y, led_height - 0.002),
            (0.0, side_center_y, led_height - 0.022),
            light_color,
            total_energy * side_length / total_emitter_length,
            side_length - 0.028,
            max(diffuser_height * 4.0, 0.048),
            lights_col,
        )
    add_area_light(
        "Door daylight fill",
        (-0.18, -0.58, 0.50),
        (-0.04, -0.045, 0.37),
        kelvin_to_srgb(5900.0),
        29.0 * effective_door_fill,
        0.38,
        0.48,
        lights_col,
    )
    add_area_light(
        "Workshop exterior ambient proxy",
        (-0.12, -0.78, 0.66),
        (-0.05, -0.01, 0.34),
        kelvin_to_srgb(4800.0),
        8.0 + 64.0 * effective_door_fill,
        0.52,
        0.46,
        lights_col,
    )
    add_area_light(
        "Workshop ceiling luminaire proxy",
        (0.0, -1.02, 0.82),
        (0.0, -1.32, 0.36),
        kelvin_to_srgb(4700.0),
        55.0 + 95.0 * effective_door_fill,
        0.62,
        0.34,
        lights_col,
    )
    add_area_light(
        "Front door LED return",
        (0.0, 0.18, 0.50),
        (0.0, -depth / 2.0, 0.43),
        light_color,
        (1.1 + 0.55 * effective_door_fill) * energy_scale,
        0.38,
        0.32,
        lights_col,
    )
    add_area_light(
        "Upper platen soft bounce",
        (
            0.0,
            0.12,
            led_height
            - float(cfg["machine"].get("led_vertical_offset_m", 0.006))
            - 0.055,
        ),
        (
            0.0,
            0.052,
            led_height - float(cfg["machine"].get("led_vertical_offset_m", 0.006)),
        ),
        light_color,
        0.15 * energy_scale,
        0.32,
        0.08,
        lights_col,
    )
    add_area_light(
        "Lower platen diffuse bounce",
        (0.0, 0.12, 0.255),
        (0.0, 0.052, 0.39),
        light_color,
        (1.2 if (sample_state or {}).get("shape") == "cylinder" else 0.8) * energy_scale,
        0.34,
        0.18,
        lights_col,
    )
    for side_name, sign in (("left", -1.0), ("right", 1.0)):
        add_area_light(
            f"{side_name.title()} upper-contact LED spill",
            (sign * (half_w - 0.052), 0.04, led_height - 0.008),
            (sign * 0.045, 0.052, led_height - 0.035),
            light_color,
            1.65 * energy_scale,
            0.19,
            0.014,
            lights_col,
        )

    world = bpy.data.worlds.new("EBIS dark laboratory world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = srgb((0.018, 0.022, 0.028))
    background.inputs["Strength"].default_value = 0.040 + 0.030 * effective_door_fill
    bpy.context.scene.world = world
    return {
        "profile": profile_name,
        "diffuser_height_m": led_height,
        "diffuser_layout": "narrow_u_channel_back_left_right",
        "diffuser_segments": 3,
        "diffuser_segment_lengths_m": {
            "back": back_emitter_length,
            "left": side_lengths["left"],
            "right": side_lengths["right"],
        },
        "temperature_k": kelvin,
        "energy_scale": energy_scale,
        "door_fill": effective_door_fill,
        "door_fill_profile": profile["door_fill"],
        "door_open_factor": door_open_factor,
        "door_angle_deg": door_angle,
    }


def build_cameras(
    cfg: dict,
    rng: random.Random,
    sample_state: dict | None = None,
    seed: int | None = None,
) -> dict[str, bpy.types.Object]:
    cameras_col = ensure_collection("EBIS_CAMERAS")
    result: dict[str, bpy.types.Object] = {}
    for name, profile in sorted(cfg["cameras"].items()):
        camera_rng = random.Random(f"{seed}:camera:{name}:v1") if seed is not None else rng
        data = bpy.data.cameras.new(name)
        data.type = "PERSP"
        lens_range = list(
            map(float, profile.get("lens_mm_range", [profile["lens_mm"], profile["lens_mm"]]))
        )
        data.lens = camera_rng.uniform(lens_range[0], lens_range[1])
        data.sensor_width = float(profile["sensor_width_mm"])
        data.sensor_fit = "HORIZONTAL"
        data.dof.use_dof = True
        data.dof.focus_distance = 0.3
        fstop_range = list(map(float, profile.get("fstop_range", [5.6, 5.6])))
        data.dof.aperture_fstop = camera_rng.uniform(fstop_range[0], fstop_range[1])
        obj = bpy.data.objects.new(name, data)
        cameras_col.objects.link(obj)
        location_jitter = list(
            map(float, profile.get("location_jitter_m", [0.002, 0.002, 0.0015]))
        )
        jitter = Vector(
            tuple(camera_rng.uniform(-amount, amount) for amount in location_jitter)
        )
        obj.location = Vector(profile["location_m"]) + jitter
        target = Vector(profile["target_m"])
        sample_shape = (sample_state or {}).get("shape")
        if sample_shape in {"cube", "cylinder"}:
            target.z += float(profile.get(f"{sample_shape}_target_z_offset_m", 0.0))
            distance_scale = float(profile.get(f"{sample_shape}_distance_scale", 1.0))
            if distance_scale <= 0.0:
                raise ValueError(
                    f"{name}.{sample_shape}_distance_scale must be positive"
                )
            obj.location = target + (obj.location - target) * distance_scale
        target_jitter = list(
            map(float, profile.get("target_jitter_m", [0.002, 0.0, 0.002]))
        )
        target += Vector(
            tuple(camera_rng.uniform(-amount, amount) for amount in target_jitter)
        )
        data.dof.focus_distance = (target - obj.location).length
        point_object_at(obj, target)
        roll_range = list(map(float, profile.get("roll_jitter_deg", [-0.3, 0.3])))
        roll = math.radians(camera_rng.uniform(roll_range[0], roll_range[1]))
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = obj.rotation_quaternion @ Quaternion(
            Vector((0.0, 0.0, 1.0)),
            roll,
        )
        distortion_range = list(
            map(
                float,
                profile.get(
                    "compositor_lens_distortion_range",
                    [
                        cfg["camera_effects"]["compositor_lens_distortion"],
                        cfg["camera_effects"]["compositor_lens_distortion"],
                    ],
                ),
            )
        )
        dispersion_range = list(
            map(
                float,
                profile.get(
                    "chromatic_dispersion_range",
                    [
                        cfg["camera_effects"]["chromatic_dispersion"],
                        cfg["camera_effects"]["chromatic_dispersion"],
                    ],
                ),
            )
        )
        obj["compositor_lens_distortion"] = camera_rng.uniform(
            distortion_range[0],
            distortion_range[1],
        )
        obj["chromatic_dispersion"] = camera_rng.uniform(
            dispersion_range[0],
            dispersion_range[1],
        )
        vignette_range = list(map(float, profile.get("vignette_strength_range", [0.0, 0.0])))
        obj["vignette_strength"] = camera_rng.uniform(
            vignette_range[0],
            vignette_range[1],
        )
        dust_cfg = cfg.get("camera_effects", {}).get("lens_dust", {})
        dust_rng = random.Random(f"{seed}:camera:{name}:lens-dust-v1")
        dust_spots: list[dict[str, float]] = []
        if (
            dust_cfg.get("enabled")
            and dust_rng.random()
            < float(dust_cfg.get("occurrence_probability", 0.0))
        ):
            count_low, count_high = map(
                int, dust_cfg.get("spot_count_range", [0, 0])
            )
            radius_low, radius_high = map(
                float, dust_cfg.get("radius_fraction_range", [0.006, 0.018])
            )
            opacity_low, opacity_high = map(
                float, dust_cfg.get("opacity_range", [0.01, 0.03])
            )
            for _ in range(dust_rng.randint(count_low, count_high)):
                dust_spots.append(
                    {
                        "x": dust_rng.uniform(0.08, 0.92),
                        "y": dust_rng.uniform(0.08, 0.92),
                        "radius_fraction": dust_rng.uniform(
                            radius_low, radius_high
                        ),
                        "aspect": dust_rng.uniform(0.65, 1.35),
                        "opacity": dust_rng.uniform(opacity_low, opacity_high),
                    }
                )
        obj["lens_dust_spots_json"] = json.dumps(
            dust_spots, sort_keys=True, separators=(",", ":")
        )
        obj["realized_target_m"] = list(target)
        obj["realized_location_m"] = list(obj.location)
        obj["realized_lens_mm"] = data.lens
        obj["realized_horizontal_fov_deg"] = math.degrees(
            2.0 * math.atan(data.sensor_width / (2.0 * data.lens))
        )
        obj["realized_focus_distance_m"] = data.dof.focus_distance
        obj["realized_fstop"] = data.dof.aperture_fstop
        obj["realized_roll_deg"] = math.degrees(roll)
        obj["source_overlay"] = profile["source_overlay"]
        obj["intrinsics_status"] = profile["fov_status"]
        result[name] = obj
    return result


def configure_cycles(scene: bpy.types.Scene, cfg: dict, force_cpu: bool) -> dict:
    render_cfg = cfg["render"]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(render_cfg["samples"])
    scene.cycles.use_denoising = bool(render_cfg["denoise"])
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.012
    scene.cycles.max_bounces = int(render_cfg["max_bounces"])
    scene.cycles.diffuse_bounces = min(4, scene.cycles.max_bounces)
    scene.cycles.glossy_bounces = min(4, scene.cycles.max_bounces)
    scene.cycles.transmission_bounces = min(4, scene.cycles.max_bounces)
    scene.cycles.volume_bounces = 1
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.render.use_file_extension = True
    if force_cpu:
        scene.cycles.device = "CPU"
        return {"backend": "CPU", "devices": []}

    preferences = bpy.context.preferences.addons["cycles"].preferences
    errors: list[str] = []
    for backend in cfg["render"]["device_preference"]:
        if backend == "CPU":
            break
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
            selected = [device for device in preferences.devices if device.type == backend]
            if not selected:
                continue
            for device in preferences.devices:
                device.use = device.type == backend
            scene.cycles.device = "GPU"
            return {"backend": backend, "devices": [device.name for device in selected]}
        except Exception as exc:  # Blender builds expose different backend enums.
            errors.append(f"{backend}: {exc}")
    scene.cycles.device = "CPU"
    return {"backend": "CPU", "devices": [], "fallback_errors": errors}


def configure_scene_render(
    scene: bpy.types.Scene,
    cfg: dict,
    rng: random.Random,
    resolution_override: str | None,
    samples_override: int | None,
    force_cpu: bool,
    lighting_state: dict | None = None,
) -> dict:
    render_cfg = cfg["render"]
    if resolution_override:
        width, height = (int(value) for value in resolution_override.lower().split("x", 1))
    else:
        width, height = map(int, render_cfg["resolution_px"])
    if width < 320 or height < 240:
        raise ValueError("Resolution is too small for the RFID visibility contract")
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = int(render_cfg["resolution_percentage"])
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0
    scene.render.film_transparent = bool(render_cfg["transparent"])
    scene.render.image_settings.file_format = render_cfg["output_format"]
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = render_cfg["output_color_depth"]
    scene.render.image_settings.color_management = "FOLLOW_SCENE"
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = render_cfg["color_management"]
    scene.view_settings.look = render_cfg["look"]
    exposure_range = render_cfg.get("exposure_range", [-0.68, -0.28])
    base_exposure = rng.uniform(float(exposure_range[0]), float(exposure_range[1]))
    # Compensate deterministic LED-power variation in stops.  This preserves
    # controlled domain variation without coupling a bright draw to an already
    # bright exposure and clipping the concrete/steel detail around the strip.
    energy_scale = max(0.001, float((lighting_state or {}).get("energy_scale", 1.0)))
    door_fill = float((lighting_state or {}).get("door_fill", 0.0))
    camera_exposure_offset = float(
        cfg["cameras"].get(scene.camera.name, {}).get("exposure_offset_stops", 0.0)
    )
    exposure = (
        base_exposure
        - float(render_cfg.get("exposure_led_compensation", 0.0)) * math.log2(energy_scale)
        - float(render_cfg.get("exposure_door_fill_compensation", 0.0)) * door_fill
        + camera_exposure_offset
    )
    exposure_limits = render_cfg.get("exposure_limits", [-2.0, 1.0])
    scene.view_settings.exposure = max(float(exposure_limits[0]), min(float(exposure_limits[1]), exposure))
    scene.view_settings.gamma = 1.0
    scene.render.engine = "CYCLES"
    device = configure_cycles(scene, cfg, force_cpu)
    if samples_override is not None:
        scene.cycles.samples = int(samples_override)
    view_layer = scene.view_layers[0]
    view_layer.use_pass_object_index = True
    view_layer.use_pass_z = True
    scene.cycles.seed = int(scene.get("ebis_seed", 0))
    return {
        "resolution_px": [width, height],
        "samples": scene.cycles.samples,
        "device": device,
        "exposure": scene.view_settings.exposure,
        "base_exposure": base_exposure,
        "camera_exposure_offset_stops": camera_exposure_offset,
        "exposure_led_compensation_stops": base_exposure - scene.view_settings.exposure,
    }


def build_scene(
    cfg: dict,
    seed: int,
    camera_override: str | None,
    resolution_override: str | None,
    samples_override: int | None,
    force_cpu: bool,
) -> dict:
    clean_scene()
    rng = random.Random(seed)
    scene = bpy.context.scene
    scene.name = "EBIS_SYNTHETIC_DATA_SCENE"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_start = 1
    scene.frame_end = 1
    scene.frame_set(1)
    scene["ebis_seed"] = seed

    moisture = rng.uniform(*cfg["sample"]["moisture_range"])
    camera_name = camera_override or ("camera_door" if seed % 2 == 0 else "camera_angled")
    sample_spec = choose_sample_spec(cfg, rng)
    mats = build_materials(cfg, moisture, rng)
    machine_state = build_machine(
        cfg,
        mats,
        rng,
        sample_spec["dimensions_m"][2],
        seed=seed,
    )
    sample, sample_state = build_concrete_sample(
        cfg, mats, rng, machine_state, sample_spec, camera_name=camera_name
    )
    tag_cfg = cfg["rfid_tag"]
    count_weights = tag_cfg.get("instance_count_weights")
    tag_count = int(weighted_choice(rng, count_weights)) if count_weights else 1
    pass_index_start = int(tag_cfg.get("instance_pass_index_start", 1))
    tag_states: list[dict] = []
    tag_roots: list[bpy.types.Object] = []
    tag_projection_objects: list[bpy.types.Object] = []
    tag_pass_indices: list[int] = []
    for instance_index in range(tag_count):
        pass_index = pass_index_start + instance_index
        tag_root, _tag_parts, tag_substrate = build_rfid_geometry(
            cfg,
            mats,
            instance_index=instance_index,
            pass_index=pass_index,
        )
        tag_state = place_rfid(
            cfg,
            rng,
            tag_root,
            sample_state,
            machine_state,
            camera_name,
            instance_index=instance_index,
        )
        tag_state["pass_index"] = pass_index
        tag_states.append(tag_state)
        tag_roots.append(tag_root)
        tag_projection_objects.append(tag_substrate)
        tag_pass_indices.append(pass_index)
    paper_labels = build_paper_labels(
        cfg,
        mats,
        random.Random(f"{seed}:paper-v1"),
        sample_state,
        tag_roots,
        tag_states,
    )
    lighting_state = build_lighting(cfg, mats, rng, sample_state, machine_state)
    cameras = build_cameras(cfg, rng, sample_state, seed=seed)
    scene.camera = cameras[camera_name]
    active_camera = cameras[camera_name]
    camera_realization = {
        "location_m": list(map(float, active_camera["realized_location_m"])),
        "target_m": list(map(float, active_camera["realized_target_m"])),
        "lens_mm": float(active_camera["realized_lens_mm"]),
        "sensor_width_mm": float(active_camera.data.sensor_width),
        "horizontal_fov_deg_before_compositor_fit": float(
            active_camera["realized_horizontal_fov_deg"]
        ),
        "focus_distance_m": float(active_camera["realized_focus_distance_m"]),
        "fstop": float(active_camera["realized_fstop"]),
        "roll_deg": float(active_camera["realized_roll_deg"]),
        "compositor_lens_distortion": float(
            active_camera["compositor_lens_distortion"]
        ),
        "chromatic_dispersion": float(active_camera["chromatic_dispersion"]),
        "vignette_strength": float(active_camera["vignette_strength"]),
        "lens_dust_spots": json.loads(active_camera["lens_dust_spots_json"]),
        "lens_dust_scope": (
            "subtle RGB-only out-of-focus sensor/lens contamination; "
            "geometry, masks and depth unchanged"
        ),
        "model_status": "perspective camera plus visual radial compositor approximation; not calibrated fisheye",
    }
    render_state = configure_scene_render(
        scene,
        cfg,
        rng,
        resolution_override,
        samples_override,
        force_cpu,
        lighting_state,
    )
    scene["ebis_domain"] = cfg["domain"]
    scene["ebis_seed"] = seed
    scene["ebis_script_version"] = SCRIPT_VERSION
    scene["ebis_camera"] = camera_name
    scene["ebis_config_sha256"] = config_sha256(cfg)
    return {
        "seed": seed,
        "camera": camera_name,
        "camera_realization": camera_realization,
        "moisture": moisture,
        "sample": sample_state,
        "machine": machine_state,
        "paper_labels": paper_labels,
        "rfid_tag": {
            "state": tag_states[0]["state"] if len(tag_states) == 1 else ("multi" if tag_states else "missing"),
            "states": [item["state"] for item in tag_states],
            "instance_count": len(tag_states),
            "missing": not tag_states or all(item["missing"] for item in tag_states),
        },
        "rfid_tags": tag_states,
        "rfid_pass_indices": tag_pass_indices,
        "rfid_projection_objects": tag_projection_objects,
        "lighting": lighting_state,
        "render": render_state,
        "sample_object": sample,
    }


def setup_compositor(
    cfg: dict,
    output_dir: Path,
    include_depth: bool,
    rfid_pass_indices: list[int] | None = None,
) -> None:
    scene = bpy.context.scene
    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    links = scene.node_tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    composite = nodes.new("CompositorNodeComposite")
    camera_effects = cfg["camera_effects"]
    lens_distortion = float(
        scene.camera.get(
            "compositor_lens_distortion",
            camera_effects["compositor_lens_distortion"],
        )
    )
    chromatic_dispersion = float(
        scene.camera.get("chromatic_dispersion", camera_effects["chromatic_dispersion"])
    )
    lens_rgb = nodes.new("CompositorNodeLensdist")
    lens_rgb.name = "APPROXIMATE_HIKVISION_BARREL_DISTORTION"
    lens_rgb.inputs["Distortion"].default_value = lens_distortion
    lens_rgb.inputs["Dispersion"].default_value = chromatic_dispersion
    lens_rgb.use_fit = True
    links.new(render_layers.outputs["Image"], lens_rgb.inputs["Image"])
    rgb_output = lens_rgb.outputs["Image"]
    vignette_cfg = camera_effects.get("vignette", {})
    vignette_strength = float(scene.camera.get("vignette_strength", 0.0))
    if vignette_cfg.get("enabled") and vignette_strength > 0.0:
        ellipse = nodes.new("CompositorNodeEllipseMask")
        ellipse.name = "HIKVISION_SOFT_OPTICAL_VIGNETTE_MASK"
        ellipse.x = 0.5
        ellipse.y = 0.5
        ellipse.width = float(vignette_cfg.get("ellipse_width", 0.94))
        ellipse.height = float(vignette_cfg.get("ellipse_height", 1.12))
        blur = nodes.new("CompositorNodeBlur")
        blur.name = "HIKVISION_SOFT_OPTICAL_VIGNETTE_FEATHER"
        blur.filter_type = "GAUSS"
        blur.use_relative = True
        blur.factor_x = float(vignette_cfg.get("blur_fraction", 0.18))
        blur.factor_y = float(vignette_cfg.get("blur_fraction", 0.18))
        links.new(ellipse.outputs["Mask"], blur.inputs["Image"])
        vignette_scale = nodes.new("CompositorNodeMath")
        vignette_scale.name = "HIKVISION_VIGNETTE_STRENGTH"
        vignette_scale.operation = "MULTIPLY"
        vignette_scale.inputs[1].default_value = vignette_strength
        links.new(blur.outputs["Image"], vignette_scale.inputs[0])
        vignette_bias = nodes.new("CompositorNodeMath")
        vignette_bias.name = "HIKVISION_VIGNETTE_CENTER_ONE"
        vignette_bias.operation = "ADD"
        vignette_bias.inputs[1].default_value = 1.0 - vignette_strength
        links.new(vignette_scale.outputs["Value"], vignette_bias.inputs[0])
        vignette_mix = nodes.new("CompositorNodeMixRGB")
        vignette_mix.name = "HIKVISION_RGB_VIGNETTE"
        vignette_mix.blend_type = "MULTIPLY"
        vignette_mix.inputs[0].default_value = 1.0
        links.new(rgb_output, vignette_mix.inputs[1])
        links.new(vignette_bias.outputs["Value"], vignette_mix.inputs[2])
        rgb_output = vignette_mix.outputs["Image"]
    dust_spots = json.loads(
        str(scene.camera.get("lens_dust_spots_json", "[]"))
    )
    for spot_index, spot in enumerate(dust_spots):
        radius = float(spot["radius_fraction"])
        ellipse = nodes.new("CompositorNodeEllipseMask")
        ellipse.name = f"LENS_DUST_SPOT_{spot_index:02d}_MASK"
        ellipse.x = float(spot["x"])
        ellipse.y = float(spot["y"])
        ellipse.width = radius * 2.0
        ellipse.height = radius * 2.0 * float(spot["aspect"])
        blur = nodes.new("CompositorNodeBlur")
        blur.name = f"LENS_DUST_SPOT_{spot_index:02d}_DEFOCUS"
        blur.filter_type = "GAUSS"
        blur.use_relative = True
        blur.factor_x = max(0.002, radius * 0.55)
        blur.factor_y = max(0.002, radius * 0.55)
        links.new(ellipse.outputs["Mask"], blur.inputs["Image"])
        opacity = nodes.new("CompositorNodeMath")
        opacity.name = f"LENS_DUST_SPOT_{spot_index:02d}_OPACITY"
        opacity.operation = "MULTIPLY"
        opacity.inputs[1].default_value = float(spot["opacity"])
        links.new(blur.outputs["Image"], opacity.inputs[0])
        dust_mix = nodes.new("CompositorNodeMixRGB")
        dust_mix.name = f"LENS_DUST_SPOT_{spot_index:02d}_RGB_ONLY"
        dust_mix.blend_type = "MIX"
        dust_mix.inputs[2].default_value = (0.15, 0.14, 0.125, 1.0)
        links.new(opacity.outputs["Value"], dust_mix.inputs[0])
        links.new(rgb_output, dust_mix.inputs[1])
        rgb_output = dust_mix.outputs["Image"]
    sharpen_cfg = camera_effects.get("sensor_sharpen", {})
    if sharpen_cfg.get("enabled"):
        sharpen = nodes.new("CompositorNodeFilter")
        sharpen.name = "HIKVISION_FULL_EDGE_SHARPEN"
        sharpen.filter_type = "SHARPEN"
        links.new(rgb_output, sharpen.inputs["Image"])
        sharpen_mix = nodes.new("CompositorNodeMixRGB")
        sharpen_mix.name = "HIKVISION_SUBTLE_EDGE_SHARPEN_MIX"
        sharpen_mix.blend_type = "MIX"
        sharpen_mix.inputs[0].default_value = float(sharpen_cfg.get("factor", 0.08))
        links.new(rgb_output, sharpen_mix.inputs[1])
        links.new(sharpen.outputs["Image"], sharpen_mix.inputs[2])
        rgb_output = sharpen_mix.outputs["Image"]
    bloom_cfg = camera_effects.get("highlight_bloom", {})
    if bloom_cfg.get("enabled"):
        # A small thresholded blur is more predictable than Blender 4.5's
        # Glare node, whose deprecated mix property logs an RNA warning and
        # whose default fog radius created a conspicuous synthetic halo.
        luminance = nodes.new("CompositorNodeRGBToBW")
        luminance.name = "LED_BLOOM_LUMINANCE"
        links.new(rgb_output, luminance.inputs["Image"])
        threshold = nodes.new("CompositorNodeMath")
        threshold.name = "LED_BLOOM_THRESHOLD"
        threshold.operation = "GREATER_THAN"
        threshold.inputs[1].default_value = float(bloom_cfg.get("threshold", 0.9))
        links.new(luminance.outputs["Val"], threshold.inputs[0])
        bright_only = nodes.new("CompositorNodeMixRGB")
        bright_only.name = "LED_BLOOM_BRIGHT_PIXELS"
        bright_only.blend_type = "MULTIPLY"
        bright_only.inputs[0].default_value = 1.0
        links.new(rgb_output, bright_only.inputs[1])
        links.new(threshold.outputs["Value"], bright_only.inputs[2])
        bloom_blur = nodes.new("CompositorNodeBlur")
        bloom_blur.name = "LED_BLOOM_SMALL_SENSOR_BLUR"
        bloom_blur.filter_type = "GAUSS"
        bloom_blur.use_relative = True
        bloom_blur.factor_x = float(bloom_cfg.get("blur_fraction", 1.2))
        bloom_blur.factor_y = float(bloom_cfg.get("blur_fraction", 1.2))
        links.new(bright_only.outputs["Image"], bloom_blur.inputs["Image"])
        bloom_add = nodes.new("CompositorNodeMixRGB")
        bloom_add.name = "LED_BLOOM_ADD"
        bloom_add.blend_type = "ADD"
        bloom_add.inputs[0].default_value = float(bloom_cfg.get("strength", 0.18))
        links.new(rgb_output, bloom_add.inputs[1])
        links.new(bloom_blur.outputs["Image"], bloom_add.inputs[2])
        rgb_output = bloom_add.outputs["Image"]
    links.new(rgb_output, composite.inputs["Image"])

    masks = nodes.new("CompositorNodeOutputFile")
    masks.name = "VISIBLE_SEMANTIC_MASKS"
    masks.base_path = str(output_dir)
    masks.format.file_format = "PNG"
    masks.format.color_mode = "BW"
    masks.format.color_depth = "8"
    masks.file_slots[0].path = "rfid_tag_"
    masks.file_slots.new("concrete_sample")
    masks.file_slots[-1].path = "concrete_sample_"

    def warped_id_mask(object_index: int, name: str):
        id_mask = nodes.new("CompositorNodeIDMask")
        id_mask.name = name + "_ID"
        id_mask.index = int(object_index)
        id_mask.use_antialiasing = True
        mask_lens = nodes.new("CompositorNodeLensdist")
        mask_lens.name = name + "_LENS"
        mask_lens.inputs["Distortion"].default_value = lens_distortion
        mask_lens.inputs["Dispersion"].default_value = 0.0
        mask_lens.use_fit = True
        links.new(render_layers.outputs["IndexOB"], id_mask.inputs["ID value"])
        links.new(id_mask.outputs["Alpha"], mask_lens.inputs["Image"])
        return mask_lens.outputs["Image"]

    concrete_output = warped_id_mask(2, "CONCRETE_VISIBLE")
    links.new(concrete_output, masks.inputs[1])

    rfid_pass_indices = list(rfid_pass_indices or [])
    rfid_outputs = [
        warped_id_mask(pass_index, f"RFID_INSTANCE_{instance_index:02d}")
        for instance_index, pass_index in enumerate(rfid_pass_indices)
    ]
    if not rfid_outputs:
        rfid_outputs = [warped_id_mask(32767, "RFID_EMPTY")]
    rfid_union = rfid_outputs[0]
    for instance_index, instance_output in enumerate(rfid_outputs[1:], start=1):
        maximum = nodes.new("CompositorNodeMath")
        maximum.name = f"RFID_UNION_MAX_{instance_index:02d}"
        maximum.operation = "MAXIMUM"
        links.new(rfid_union, maximum.inputs[0])
        links.new(instance_output, maximum.inputs[1])
        rfid_union = maximum.outputs[0]
    links.new(rfid_union, masks.inputs[0])

    if rfid_pass_indices:
        instance_masks = nodes.new("CompositorNodeOutputFile")
        instance_masks.name = "VISIBLE_RFID_INSTANCE_MASKS"
        instance_masks.base_path = str(output_dir)
        instance_masks.format.file_format = "PNG"
        instance_masks.format.color_mode = "BW"
        instance_masks.format.color_depth = "8"
        for instance_index, instance_output in enumerate(rfid_outputs):
            if instance_index:
                instance_masks.file_slots.new(f"rfid_instance_{instance_index:02d}")
            instance_masks.file_slots[instance_index].path = f"rfid_instance_{instance_index:02d}_"
            links.new(instance_output, instance_masks.inputs[instance_index])

    if include_depth:
        depth_raw = nodes.new("CompositorNodeOutputFile")
        depth_raw.name = "CAMERA_DEPTH_RAW_METRIC_EXR"
        depth_raw.base_path = str(output_dir)
        depth_raw.format.file_format = "OPEN_EXR"
        depth_raw.format.color_mode = "BW"
        depth_raw.format.color_depth = "32"
        depth_raw.file_slots[0].path = "depth_raw_"
        links.new(render_layers.outputs["Depth"], depth_raw.inputs[0])

        depth_aligned = nodes.new("CompositorNodeOutputFile")
        depth_aligned.name = "CAMERA_DEPTH_APPROXIMATELY_ALIGNED_EXR"
        depth_aligned.base_path = str(output_dir)
        depth_aligned.format.file_format = "OPEN_EXR"
        depth_aligned.format.color_mode = "BW"
        depth_aligned.format.color_depth = "32"
        depth_aligned.file_slots[0].path = "depth_aligned_"
        depth_lens = nodes.new("CompositorNodeLensdist")
        depth_lens.name = "DEPTH_APPROXIMATELY_ALIGNED_WITH_RGB"
        depth_lens.inputs["Distortion"].default_value = lens_distortion
        depth_lens.inputs["Dispersion"].default_value = 0.0
        depth_lens.use_fit = True
        links.new(render_layers.outputs["Depth"], depth_lens.inputs["Image"])
        links.new(depth_lens.outputs["Image"], depth_aligned.inputs[0])


def find_compositor_file(directory: Path, prefix: str, suffix: str) -> Path:
    matches = sorted(directory.glob(f"{prefix}*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one compositor output {prefix}*{suffix}, got {matches}")
    return matches[0]


def write_binary_grayscale_png(path: Path, mask) -> None:
    """Write an 8-bit, filter-0 grayscale PNG without colour management."""

    height, width = mask.shape
    rows = []
    # Blender image buffers start at the lower-left; PNG scanlines start at the top.
    for row in mask[::-1]:
        rows.append(b"\x00" + (row.astype("uint8") * 255).tobytes())

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)))
    png.extend(chunk(b"IDAT", zlib.compress(b"".join(rows), level=9)))
    png.extend(chunk(b"IEND", b""))
    path.write_bytes(png)


def mask_bbox(
    path: Path,
    *,
    make_binary: bool = False,
    include_components: bool = False,
) -> dict | None:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Blender's bundled numpy is required for mask validation") from exc
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = map(int, image.size)
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    channel = pixels[0::4].reshape((height, width))
    binary = channel > 0.18
    ys, xs = np.nonzero(binary)
    bpy.data.images.remove(image)
    if make_binary:
        write_binary_grayscale_png(path, binary)
    if len(xs) == 0:
        return None
    min_x, max_x = int(xs.min()), int(xs.max())
    min_y, max_y = int(ys.min()), int(ys.max())
    box_width = max_x - min_x + 1
    box_height = max_y - min_y + 1
    x_center = (min_x + max_x + 1) / (2.0 * width)
    y_center = 1.0 - (min_y + max_y + 1) / (2.0 * height)
    component_count = None
    largest_component_fraction = None
    if include_components:
        # RFID masks are small, so an explicit 8-connected walk is both
        # dependency-free and fast enough in Blender's bundled Python.
        foreground = {int(y) * width + int(x) for y, x in zip(ys, xs)}
        component_sizes: list[int] = []
        while foreground:
            seed = foreground.pop()
            stack = [seed]
            size = 0
            while stack:
                current = stack.pop()
                size += 1
                cy, cx = divmod(current, width)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if not dx and not dy:
                            continue
                        nx, ny = cx + dx, cy + dy
                        if nx < 0 or nx >= width or ny < 0 or ny >= height:
                            continue
                        neighbour = ny * width + nx
                        if neighbour in foreground:
                            foreground.remove(neighbour)
                            stack.append(neighbour)
            component_sizes.append(size)
        component_count = len(component_sizes)
        largest_component_fraction = max(component_sizes) / len(xs)

    return {
        "pixels": int(len(xs)),
        "xyxy_bottom_left_px": [min_x, min_y, max_x, max_y],
        "yolo": [x_center, y_center, box_width / width, box_height / height],
        "size_px": [box_width, box_height],
        "bbox_fill_fraction": float(len(xs) / (box_width * box_height)),
        "touching_edges": {
            "left": min_x == 0,
            "right": max_x == width - 1,
            "bottom": min_y == 0,
            "top": max_y == height - 1,
        },
        "component_count": component_count,
        "largest_component_fraction": largest_component_fraction,
    }


def convex_hull_2d(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    points = sorted(set(points))
    if len(points) <= 1:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def clip_polygon_to_image(
    polygon: list[tuple[float, float]], width: int, height: int
) -> list[tuple[float, float]]:
    def clip(points, inside, intersect):
        if not points:
            return []
        result = []
        previous = points[-1]
        previous_inside = inside(previous)
        for current in points:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    result.append(intersect(previous, current))
                result.append(current)
            elif previous_inside:
                result.append(intersect(previous, current))
            previous, previous_inside = current, current_inside
        return result

    result = polygon
    result = clip(
        result,
        lambda p: p[0] >= 0.0,
        lambda a, b: (0.0, a[1] + (b[1] - a[1]) * (0.0 - a[0]) / (b[0] - a[0])),
    )
    result = clip(
        result,
        lambda p: p[0] <= width,
        lambda a, b: (float(width), a[1] + (b[1] - a[1]) * (width - a[0]) / (b[0] - a[0])),
    )
    result = clip(
        result,
        lambda p: p[1] >= 0.0,
        lambda a, b: (a[0] + (b[0] - a[0]) * (0.0 - a[1]) / (b[1] - a[1]), 0.0),
    )
    result = clip(
        result,
        lambda p: p[1] <= height,
        lambda a, b: (a[0] + (b[0] - a[0]) * (height - a[1]) / (b[1] - a[1]), float(height)),
    )
    return result


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def projected_object_footprint(obj: bpy.types.Object, scene: bpy.types.Scene) -> dict:
    """Approximate an in-frame amodal footprint before compositor lens warp."""

    from bpy_extras.object_utils import world_to_camera_view

    bpy.context.view_layer.update()
    width = int(scene.render.resolution_x * scene.render.resolution_percentage / 100)
    height = int(scene.render.resolution_y * scene.render.resolution_percentage / 100)
    projected = []
    for corner in obj.bound_box:
        coordinate = world_to_camera_view(scene, scene.camera, obj.matrix_world @ Vector(corner))
        if coordinate.z <= 0.0:
            continue
        projected.append((float(coordinate.x) * width, (1.0 - float(coordinate.y)) * height))
    hull = convex_hull_2d(projected)
    clipped = clip_polygon_to_image(hull, width, height)
    area = polygon_area(clipped)
    if clipped:
        xs = [point[0] for point in clipped]
        ys = [point[1] for point in clipped]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bbox = None
    return {
        "method": "projected_substrate_convex_hull_before_compositor_lens_warp",
        "in_frame_area_px": area,
        "in_frame_xyxy_top_left_px": bbox,
        "fully_outside_frame": not clipped,
        "lens_warp_note": "Visibility fraction is a proxy because RGB/visible masks receive compositor distortion.",
    }


def classify_rfid_annotation(
    visible: dict | None,
    projected: dict,
    resolution: list[int],
    policy: dict | None,
) -> dict:
    if visible is None:
        outside_frame = bool(projected.get("fully_outside_frame"))
        return {
            "label_status": (
                "present_but_outside_frame" if outside_frame else "present_but_fully_occluded"
            ),
            "include_in_yolo": False,
            "visibility_fraction_proxy": 0.0,
            "metrics_at_model_input": None,
            "reasons": [
                "projected_fully_outside_frame" if outside_frame else "no_visible_instance_pixels"
            ],
        }
    projected_area = float(projected.get("in_frame_area_px") or 0.0)
    visibility = min(1.0, float(visible["pixels"]) / projected_area) if projected_area > 0.0 else 0.0
    if not policy:
        return {
            "label_status": "standard_positive",
            "include_in_yolo": True,
            "visibility_fraction_proxy": visibility,
            "metrics_at_model_input": None,
            "reasons": [],
        }

    model_input = float(policy["model_input_px"])
    scale = model_input / max(float(resolution[0]), float(resolution[1]))
    width_px, height_px = map(float, visible["size_px"])
    xyxy = list(map(float, visible["xyxy_bottom_left_px"]))
    edge_margin = min(xyxy[0], xyxy[1], resolution[0] - 1 - xyxy[2], resolution[1] - 1 - xyxy[3]) * scale
    metrics = {
        "short_side_px": min(width_px, height_px) * scale,
        "long_side_px": max(width_px, height_px) * scale,
        "foreground_pixels": float(visible["pixels"]) * scale * scale,
        "edge_margin_px": edge_margin,
        "largest_component_fraction": float(visible.get("largest_component_fraction") or 0.0),
    }

    def passes(values: dict, *, require_margin: bool) -> tuple[bool, list[str]]:
        failures = []
        checks = (
            (metrics["short_side_px"] >= float(values["min_short_side_px"]), "short_side"),
            (metrics["long_side_px"] >= float(values["min_long_side_px"]), "long_side"),
            (metrics["foreground_pixels"] >= float(values["min_foreground_pixels"]), "foreground"),
            (visibility >= float(values["min_visibility_fraction_proxy"]), "visibility"),
            (
                metrics["largest_component_fraction"]
                >= float(values["min_largest_component_fraction"]),
                "largest_component",
            ),
        )
        failures.extend(name for passed, name in checks if not passed)
        if require_margin and metrics["edge_margin_px"] < float(values.get("min_edge_margin_px", 0.0)):
            failures.append("edge_margin")
        return not failures, failures

    standard_ok, standard_failures = passes(policy["rfid_tag"]["standard"], require_margin=True)
    hard_ok, hard_failures = passes(policy["rfid_tag"]["hard"], require_margin=False)
    if standard_ok:
        status, include, reasons = "standard_positive", True, []
    elif hard_ok:
        status, include, reasons = "hard_positive", True, standard_failures
    else:
        status, include, reasons = "excluded_too_small_or_occluded", False, hard_failures
    return {
        "label_status": status,
        "include_in_yolo": include,
        "visibility_fraction_proxy": visibility,
        "metrics_at_model_input": metrics,
        "reasons": reasons,
    }


def depth_stats(path: Path, expected_size: tuple[int, int] | list[int]) -> dict:
    """Inspect the rendered EXR before publication and reject unusable depth."""

    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Blender's bundled numpy is required for depth validation") from exc
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = map(int, image.size)
    if [width, height] != list(expected_size):
        bpy.data.images.remove(image)
        raise RuntimeError(f"Depth dimensions {[width, height]} do not match RGB {list(expected_size)}")
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    values = pixels[0::4]
    finite = np.isfinite(values)
    positive = finite & (values > 0.0) & (values < 1000.0)
    finite_values = values[positive]
    result = {
        "resolution_px": [width, height],
        "finite_fraction": float(finite.mean()),
        "valid_metric_fraction": float(positive.mean()),
        "min_m": float(finite_values.min()) if finite_values.size else None,
        "max_m": float(finite_values.max()) if finite_values.size else None,
        "mean_m": float(finite_values.mean()) if finite_values.size else None,
    }
    bpy.data.images.remove(image)
    if result["finite_fraction"] < 0.95 or result["valid_metric_fraction"] < 0.90:
        raise RuntimeError(f"Depth EXR contains too many invalid pixels: {result}")
    if result["min_m"] is None or result["max_m"] <= result["min_m"]:
        raise RuntimeError(f"Depth EXR has no usable metric range: {result}")
    return result


def binary_png_stats(path: Path) -> dict:
    """Validate and count the filter-0 binary grayscale PNGs written above."""

    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid_png_signature")
    cursor = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while cursor + 12 <= len(payload):
        length = struct.unpack(">I", payload[cursor : cursor + 4])[0]
        kind = payload[cursor + 4 : cursor + 8]
        data = payload[cursor + 8 : cursor + 8 + length]
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError("unsupported_png_header")
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
        cursor += 12 + length
    if width is None or height is None or bit_depth != 8 or color_type != 0:
        raise ValueError("mask_must_be_8bit_grayscale_png")
    raw = zlib.decompress(bytes(compressed))
    stride = width + 1
    if len(raw) != stride * height:
        raise ValueError("unexpected_png_payload_size")
    foreground = 0
    for row_index in range(height):
        row = raw[row_index * stride : (row_index + 1) * stride]
        if row[0] != 0:
            raise ValueError("mask_png_must_use_filter_zero")
        values = row[1:]
        if any(value not in (0, 255) for value in values):
            raise ValueError("mask_png_contains_nonbinary_values")
        foreground += values.count(255)
    return {"resolution_px": [width, height], "foreground_pixels": foreground}


def scene_manifest() -> dict:
    objects = []
    for obj in sorted(bpy.context.scene.objects, key=lambda value: value.name):
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "pass_index": int(obj.pass_index),
                "semantic_class": obj.get("semantic_class"),
                "location_m": [round(float(value), 7) for value in obj.matrix_world.translation],
            }
        )
    return {
        "object_count": len(objects),
        "semantic_object_counts": {
            "rfid_tag": sum(
                obj["semantic_class"] == "rfid_tag" and obj["type"] != "EMPTY" for obj in objects
            ),
            "concrete_sample": sum(
                obj["semantic_class"] == "concrete_sample" and obj["type"] != "EMPTY" for obj in objects
            ),
        },
        "objects": objects,
    }


def assert_scene_contract(cfg: dict, state: dict) -> list[str]:
    errors: list[str] = []
    scene = bpy.context.scene
    required = {
        "SEM_CONCRETE_SAMPLE",
        "Lower press platen",
        "Lower platen used contact face",
        "Upper press platen",
        "Upper platen dark contact face",
        "Right front door hinge pivot",
        "Solid grey front door sheet",
        "Door rounded service cover",
        "U LED back opal diffuser",
        "U LED left opal diffuser",
        "U LED right opal diffuser",
        "camera_door",
        "camera_angled",
    }
    missing = sorted(required - set(scene.objects.keys()))
    if missing:
        errors.append(f"missing_objects={missing}")
    if scene.unit_settings.system != "METRIC" or scene.unit_settings.scale_length != 1.0:
        errors.append("scene_units_are_not_metric_1m")
    if scene.camera is None or scene.camera.name != state["camera"]:
        errors.append("active_camera_mismatch")
    expected_camera_stack_count = int(
        cfg["machine"].get("fixed_camera_stack_count", 0)
    )
    if (
        int(state["machine"].get("fixed_camera_stack_count", -1))
        != expected_camera_stack_count
        or state["machine"].get("fixed_camera_stack_status")
        != cfg["machine"].get("fixed_camera_stack_status")
    ):
        errors.append("fixed_camera_stack_contract_mismatch")
    if expected_camera_stack_count == 0:
        exposed_stack_objects = [
            obj.name
            for obj in scene.objects
            if (
                "opposing fisheye" in obj.name.lower()
                or "camera access cover" in obj.name.lower()
                or "hikvision dark sensor" in obj.name.lower()
                or " ir circular port" in obj.name.lower()
            )
            and not obj.hide_render
        ]
        if exposed_stack_objects:
            errors.append(f"exposed_camera_stack_objects={exposed_stack_objects}")
    contact_face = scene.objects.get("Upper platen dark contact face")
    contact_cfg = cfg["machine"]
    if contact_face is not None:
        expected_diameter = float(contact_cfg["platen_diameter_m"]) * float(
            contact_cfg.get("upper_contact_face_diameter_scale", 0.985)
        )
        expected_thickness = float(
            contact_cfg.get("upper_contact_face_thickness_m", 0.0006)
        )
        if (
            not math.isclose(float(contact_face.dimensions.x), expected_diameter, abs_tol=2e-5)
            or not math.isclose(float(contact_face.dimensions.y), expected_diameter, abs_tol=2e-5)
            or not math.isclose(float(contact_face.dimensions.z), expected_thickness, abs_tol=2e-5)
        ):
            errors.append("upper_contact_face_geometry_mismatch")
    lower_contact_face = scene.objects.get("Lower platen used contact face")
    if lower_contact_face is not None:
        expected_diameter = float(contact_cfg["platen_diameter_m"]) * float(
            contact_cfg.get("lower_contact_face_diameter_scale", 0.985)
        )
        expected_thickness = float(
            contact_cfg.get("lower_contact_face_thickness_m", 0.0008)
        )
        expected_top = float(state["machine"]["lower_platen_top_z"])
        observed_top = (
            float(lower_contact_face.location.z)
            + float(lower_contact_face.dimensions.z) / 2.0
        )
        if (
            not math.isclose(
                float(lower_contact_face.dimensions.x),
                expected_diameter,
                abs_tol=2e-5,
            )
            or not math.isclose(
                float(lower_contact_face.dimensions.y),
                expected_diameter,
                abs_tol=2e-5,
            )
            or not math.isclose(
                float(lower_contact_face.dimensions.z),
                expected_thickness,
                abs_tol=2e-5,
            )
            or not math.isclose(observed_top, expected_top, abs_tol=2e-5)
        ):
            errors.append("lower_contact_face_geometry_mismatch")
    if state["rfid_tags"]:
        tag_dims = cfg["rfid_tag"]["size_m"]
        if abs(tag_dims[0] / tag_dims[1] - 6.0) > 0.01:
            errors.append("rfid_aspect_ratio_mismatch")
    expected_indices = {item["name"]: int(item["object_index"]) for item in cfg["classes"]}
    valid_rfid_indices = set(map(int, state["rfid_pass_indices"]))
    semantic_counts = {name: 0 for name in expected_indices}
    for obj in scene.objects:
        semantic_class = obj.get("semantic_class")
        if semantic_class not in expected_indices or obj.type == "EMPTY":
            continue
        semantic_counts[semantic_class] += 1
        expected_pass = (
            int(obj.pass_index) in valid_rfid_indices
            if semantic_class == "rfid_tag"
            else int(obj.pass_index) == expected_indices[semantic_class]
        )
        if not expected_pass:
            errors.append(
                f"semantic_pass_index_mismatch:{obj.name}:{semantic_class}:"
                f"{obj.pass_index}:{expected_indices[semantic_class]}"
            )
    for semantic_class, count in semantic_counts.items():
        if count == 0 and semantic_class != "rfid_tag":
            errors.append(f"semantic_class_has_no_renderable_objects:{semantic_class}")
    valid_tag_ids = {int(item["instance_id"]) for item in state["rfid_tags"]}
    for obj in scene.objects:
        if obj.get("occlusion_role") != "non_target_opaque":
            continue
        if int(obj.pass_index) != 0 or obj.get("semantic_class") is not None:
            errors.append(f"paper_occluder_semantic_leak:{obj.name}")
        linked_id = int(obj.get("linked_rfid_instance_id", -1))
        if linked_id >= 0 and linked_id not in valid_tag_ids:
            errors.append(f"paper_link_missing_rfid:{obj.name}:{linked_id}")
    door_state = state.get("machine", {}).get("door", {})
    if not (
        float(door_state.get("angle_range_deg", [0.0, 0.0])[0])
        <= float(door_state.get("angle_deg", -1.0))
        <= float(door_state.get("angle_range_deg", [0.0, 0.0])[1])
    ):
        errors.append("door_angle_outside_selected_profile")
    expected_door_convention = (
        "0=closed across front aperture, positive=left latch edge rotates outward"
    )
    if (
        door_state.get("side") != cfg["machine"].get("door_side")
        or door_state.get("angle_convention") != expected_door_convention
        or state["machine"].get("interior_panel_materials")
        != cfg["machine"].get("interior_panel_materials")
        or state["machine"].get("blue_wall_material_profile")
        != cfg["machine"].get("blue_wall_material_profile")
    ):
        errors.append("front_door_or_blue_chamber_contract_mismatch")
    door_leaf = scene.objects.get("Solid grey front door sheet")
    door_pivot = scene.objects.get("Right front door hinge pivot")
    door_cover = scene.objects.get("Door rounded service cover")
    if (
        door_leaf is None
        or door_pivot is None
        or door_cover is None
        or door_leaf.parent != door_pivot
        or door_cover.parent != door_pivot
        or not math.isclose(
            float(door_leaf.dimensions.x),
            float(cfg["machine"]["door_leaf_width_m"]),
            abs_tol=2e-5,
        )
        or not math.isclose(
            float(door_leaf.dimensions.y),
            float(cfg["machine"]["door_leaf_thickness_m"]),
            abs_tol=2e-5,
        )
    ):
        errors.append("front_door_geometry_or_parenting_mismatch")
    forbidden_door_objects = {
        "Left safety door hinge pivot",
        "Open safety door glass window",
        "Rear camera service cover",
        "Rear camera service cover gasket",
    }
    stale = sorted(forbidden_door_objects.intersection(scene.objects.keys()))
    if stale:
        errors.append(f"obsolete_sliding_door_proxy_present={stale}")
    if errors:
        raise RuntimeError("Scene contract failed: " + "; ".join(errors))
    return [
        "metric_units_ok",
        "two_cameras_present",
        f"instance_aware_semantic_pass_indices_present:{len(valid_rfid_indices)}_rfid_instance(s)",
        "press_stack_present",
        "hinged_safety_door_present",
        "three_segment_led_present",
        f"paper_occlusion_links_valid:{len(state.get('paper_labels', []))}_paper_form(s)",
        "rfid_reference_dimensions_declared",
    ]


def render_one(
    cfg: dict,
    seed: int,
    camera: str | None,
    output_root: Path,
    resolution: str | None,
    samples: int | None,
    force_cpu: bool,
    include_depth: bool,
    save_blend: bool,
    overwrite: bool,
) -> dict:
    started = time.perf_counter()
    output_root = output_root.resolve()
    for relative in (
        "images",
        "labels",
        "masks/rfid_tag",
        "masks/rfid_instances",
        "masks/concrete_sample",
        "metadata",
        "depth_raw",
        "depth_aligned",
        "scenes",
    ):
        (output_root / relative).mkdir(parents=True, exist_ok=True)
    state = build_scene(cfg, seed, camera, resolution, samples, force_cpu)
    assertions = assert_scene_contract(cfg, state)
    stem = f"ebis_{state['camera']}_{seed:06d}"
    metadata_path = output_root / "metadata" / f"{stem}.json"
    if metadata_path.exists() and not overwrite:
        raise FileExistsError(f"Render already exists; use --overwrite explicitly: {metadata_path}")
    temp_dir = output_root / f".tmp_{stem}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    try:
        setup_compositor(cfg, temp_dir, include_depth, state["rfid_pass_indices"])
        temp_image = temp_dir / "rgb.png"
        bpy.context.scene.render.filepath = str(temp_image)
        bpy.ops.render.render(write_still=True)
        if not temp_image.is_file() or temp_image.stat().st_size < 20_000:
            raise RuntimeError(f"RGB render missing or suspiciously small: {temp_image}")

        masks: dict[str, dict | None] = {}
        temp_masks: dict[str, Path] = {}
        for class_name in ("rfid_tag", "concrete_sample"):
            generated = find_compositor_file(temp_dir, class_name + "_", ".png")
            masks[class_name] = mask_bbox(generated, make_binary=True)
            temp_masks[class_name] = generated

        annotation_policy = cfg["outputs"].get("annotation_policy")
        rfid_instances: list[dict] = []
        temp_instance_masks: list[Path] = []
        for instance_index, (tag_state, projection_object) in enumerate(
            zip(state["rfid_tags"], state["rfid_projection_objects"])
        ):
            generated = find_compositor_file(temp_dir, f"rfid_instance_{instance_index:02d}_", ".png")
            visible = mask_bbox(generated, make_binary=True, include_components=True)
            projected = projected_object_footprint(projection_object, bpy.context.scene)
            if tag_state["missing"]:
                decision = {
                    "label_status": "missing",
                    "include_in_yolo": False,
                    "visibility_fraction_proxy": 0.0,
                    "metrics_at_model_input": None,
                    "reasons": [],
                }
            else:
                decision = classify_rfid_annotation(
                    visible,
                    projected,
                    state["render"]["resolution_px"],
                    annotation_policy,
                )
            rfid_instances.append(
                tag_state
                | {
                    "physical_size_m": cfg["rfid_tag"]["size_m"],
                    "visible_annotation": visible,
                    "projected_amodal_proxy": projected,
                    "detection_policy": decision,
                }
            )
            temp_instance_masks.append(generated)

        min_pixels = cfg["outputs"]["min_visible_pixels"]
        min_sizes = cfg["outputs"]["min_visible_size_px"]
        concrete_mask = masks["concrete_sample"]
        if concrete_mask is None or concrete_mask["pixels"] < min_pixels["concrete_sample"]:
            raise RuntimeError(
                "Concrete sample visibility is below the configured acceptance threshold: "
                f"observed={concrete_mask!r}, min_pixels={min_pixels['concrete_sample']}"
            )
        if any(
            actual < required
            for actual, required in zip(concrete_mask["size_px"], min_sizes["concrete_sample"])
        ):
            raise RuntimeError("Concrete sample bounding size is below the configured acceptance threshold")
        if not annotation_policy and not state["rfid_tag"]["missing"]:
            tag_mask = masks["rfid_tag"]
            if tag_mask is None or tag_mask["pixels"] < min_pixels["rfid_tag"]:
                raise RuntimeError(
                    "RFID tag visibility is below the configured acceptance threshold: "
                    f"state={state['rfid_tag']['state']}, observed={tag_mask!r}, "
                    f"min_pixels={min_pixels['rfid_tag']}"
                )
            if any(actual < required for actual, required in zip(tag_mask["size_px"], min_sizes["rfid_tag"])):
                raise RuntimeError("RFID tag bounding size is below the configured acceptance threshold")

        temp_depth_raw: Path | None = None
        temp_depth_aligned: Path | None = None
        rendered_depth_stats: dict[str, dict] | None = None
        if include_depth:
            temp_depth_raw = find_compositor_file(temp_dir, "depth_raw_", ".exr")
            temp_depth_aligned = find_compositor_file(temp_dir, "depth_aligned_", ".exr")
            rendered_depth_stats = {
                "raw_metric": depth_stats(temp_depth_raw, state["render"]["resolution_px"]),
                "aligned_approximate": depth_stats(temp_depth_aligned, state["render"]["resolution_px"]),
            }

        label_lines = []
        for instance in rfid_instances:
            bbox = instance["visible_annotation"]
            if bbox is not None and instance["detection_policy"]["include_in_yolo"]:
                label_lines.append("0 " + " ".join(f"{value:.8f}" for value in bbox["yolo"]))
        if concrete_mask is not None:
            label_lines.append("1 " + " ".join(f"{value:.8f}" for value in concrete_mask["yolo"]))
        temp_label = temp_dir / "label.txt"
        temp_label.write_text("\n".join(label_lines) + "\n", encoding="utf-8")

        label_statuses = [instance["detection_policy"]["label_status"] for instance in rfid_instances]
        if "excluded_too_small_or_occluded" in label_statuses:
            annotation_partition = "exclude"
        elif "hard_positive" in label_statuses:
            annotation_partition = "hard_occlusion"
        else:
            annotation_partition = "standard"
        # Policy-aware renders never share a train-visible image directory.
        # This makes it difficult to accidentally train on visible-but-unlabelled
        # excluded tags or to silently mix the hard occlusion ablation.
        dataset_relative_root = (
            Path("partitions") / annotation_partition if annotation_policy else Path()
        )
        (output_root / dataset_relative_root / "images").mkdir(parents=True, exist_ok=True)
        (output_root / dataset_relative_root / "labels").mkdir(parents=True, exist_ok=True)

        temp_blend: Path | None = None
        portable_blend_state: dict = {}
        if save_blend:
            temp_blend = temp_dir / "scene.blend"
            portable_blend_state = configure_portable_blend_outputs(bpy.context.scene, stem)
            bpy.context.preferences.filepaths.use_file_compression = True
            bpy.ops.wm.save_as_mainfile(filepath=str(temp_blend), compress=True)

        image_path = output_root / dataset_relative_root / "images" / f"{stem}.png"
        label_path = output_root / dataset_relative_root / "labels" / f"{stem}.txt"
        rfid_mask_path = output_root / "masks" / "rfid_tag" / f"{stem}.png"
        rfid_instance_mask_paths = [
            output_root / "masks" / "rfid_instances" / f"{stem}__rfid_{index:02d}.png"
            for index in range(len(temp_instance_masks))
        ]
        concrete_mask_path = output_root / "masks" / "concrete_sample" / f"{stem}.png"
        depth_raw_path = output_root / "depth_raw" / f"{stem}.exr" if temp_depth_raw else None
        depth_aligned_path = (
            output_root / "depth_aligned" / f"{stem}.exr" if temp_depth_aligned else None
        )
        blend_path = output_root / "scenes" / f"{stem}.blend" if temp_blend else None

        publications: list[tuple[Path, Path]] = [
            (temp_image, image_path),
            (temp_label, label_path),
            (temp_masks["rfid_tag"], rfid_mask_path),
            (temp_masks["concrete_sample"], concrete_mask_path),
        ]
        publications.extend(zip(temp_instance_masks, rfid_instance_mask_paths))
        if temp_depth_raw and depth_raw_path:
            publications.append((temp_depth_raw, depth_raw_path))
        if temp_depth_aligned and depth_aligned_path:
            publications.append((temp_depth_aligned, depth_aligned_path))
        if temp_blend and blend_path:
            publications.append((temp_blend, blend_path))
        for temporary, final in publications:
            os.replace(temporary, final)

        elapsed = time.perf_counter() - started
        rfid_summary = state["rfid_tag"] | {
            "physical_size_m": cfg["rfid_tag"]["size_m"],
            "labeled_instance_count": sum(
                bool(instance["detection_policy"]["include_in_yolo"]) for instance in rfid_instances
            ),
            "annotation_partition": annotation_partition,
        }
        metadata = {
            "schema_version": 2 if annotation_policy else 1,
            "domain": cfg["domain"],
            "generator": {
                "script_version": SCRIPT_VERSION,
                "blender_version": bpy.app.version_string,
                "script_sha256": SCRIPT_SHA256,
                "config_sha256": config_sha256(cfg),
            },
            "seed": seed,
            "camera": state["camera"],
            "camera_profile": cfg["cameras"][state["camera"]],
            "camera_realization": state["camera_realization"],
            "camera_effects": cfg["camera_effects"],
            "historical_distortion_unverified": HISTORICAL_DISTORTION,
            "sample": state["sample"] | {"moisture": state["moisture"]},
            "machine": state["machine"],
            "paper_labels": state["paper_labels"],
            "rfid_tag": rfid_summary,
            "rfid_tags": rfid_instances,
            "lighting": state["lighting"],
            "render": state["render"]
            | {"elapsed_seconds": elapsed, "depth_enabled": include_depth}
            | portable_blend_state,
            "determinism": {
                "scenario_rng": "Python random.Random(seed)",
                "cycles_seed": seed,
                "geometry_and_metadata": "deterministic for the pinned script/config/Blender version",
                "rgb_bit_exactness": "not guaranteed across GPU drivers, Blender builds or denoiser implementations",
            },
            "visible_annotations": masks,
            "detection_annotations": {
                "rfid_instances": [
                    {
                        "instance_id": instance["instance_id"],
                        "bbox": instance["visible_annotation"],
                        "label_status": instance["detection_policy"]["label_status"],
                        "included": instance["detection_policy"]["include_in_yolo"],
                    }
                    for instance in rfid_instances
                ],
                "concrete_sample": concrete_mask,
                "image_partition": annotation_partition,
            },
            "mask_encoding": {
                "format": "8-bit grayscale PNG",
                "background": 0,
                "foreground": 255,
                "antialiasing": False,
                "bbox_source": (
                    "per-instance published binary visible-object mask for RFID; "
                    "single-instance visible mask for concrete"
                ),
            },
            "depth_stats": rendered_depth_stats,
            "depth_convention": {
                "raw_metric": "Blender Render Layers Depth pass in scene metres; no compositor lens warp",
                "aligned_approximate": "bilinear lens-distortion resample for RGB correspondence; edge values are not metric ground truth",
                "invalid_values": "pixels outside rendered geometry may be non-finite or zero",
            },
            "assertions": assertions,
            "scene_manifest": scene_manifest(),
            "assumptions": {
                "sample_size": cfg["sample"]["size_status"],
                "rfid_size": cfg["rfid_tag"]["size_status"],
                "camera_intrinsics": cfg["evidence"]["camera_intrinsics_status"],
                "camera_conditioned_sample_yaw": cfg["sample"].get(
                    "camera_conditioned_yaw_scope", "disabled"
                ),
                "rfid_scope": "visual appearance only; no UID, RSSI or RF simulation",
                "fracture_scope": "visual surface/damage only; no FEM/DEM strength simulation",
            },
            "outputs": {
                "rgb": str(image_path.relative_to(output_root)),
                "label": str(label_path.relative_to(output_root)),
                "rfid_mask": str(rfid_mask_path.relative_to(output_root)),
                "rfid_instance_masks": [
                    str(path.relative_to(output_root)) for path in rfid_instance_mask_paths
                ],
                "concrete_mask": str(concrete_mask_path.relative_to(output_root)),
                "depth_raw": str(depth_raw_path.relative_to(output_root)) if depth_raw_path else None,
                "depth_aligned": (
                    str(depth_aligned_path.relative_to(output_root)) if depth_aligned_path else None
                ),
                "blend": str(blend_path.relative_to(output_root)) if blend_path else None,
            },
        }
        metadata["sha256"] = {
            "rgb": sha256_file(image_path),
            "label": sha256_file(label_path),
            "rfid_mask": sha256_file(rfid_mask_path),
            "rfid_instance_masks": [sha256_file(path) for path in rfid_instance_mask_paths],
            "concrete_mask": sha256_file(concrete_mask_path),
            "depth_raw": sha256_file(depth_raw_path) if depth_raw_path else None,
            "depth_aligned": sha256_file(depth_aligned_path) if depth_aligned_path else None,
            "blend": sha256_file(blend_path) if blend_path else None,
        }
        temp_metadata = temp_dir / "metadata.json"
        temp_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_metadata, metadata_path)
        print(f"EBIS_RENDER_OK {stem} {elapsed:.2f}s {image_path}", flush=True)
        return metadata
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def validate_dataset(
    output_root: Path,
    cfg: dict,
    expected_count: int | None = None,
    require_both_cameras: bool = False,
) -> dict:
    output_root = output_root.resolve()
    metadata_paths = sorted((output_root / "metadata").glob("ebis_*.json"))
    if not metadata_paths:
        raise RuntimeError(f"No metadata found below {output_root}")
    errors: list[str] = []
    warnings: list[str] = []
    seen_seeds: set[int] = set()
    seen_render_keys: set[tuple[int, str]] = set()
    expected_stems: set[str] = set()
    expected_instance_mask_relatives: set[str] = set()
    expected_partition_dataset_relatives: set[str] = set()
    script_hashes: set[str] = set()
    camera_counts: dict[str, int] = {}
    lighting_counts: dict[str, int] = {}
    rfid_state_counts: dict[str, int] = {}
    rfid_label_status_counts: dict[str, int] = {}
    annotation_partition_counts: dict[str, int] = {}
    paper_occlusion_counts: dict[str, int] = {}
    paper_rfid_links_checked = 0
    lower_contact_faces_checked = 0
    lower_contact_face_profile_counts: dict[str, int] = {}
    upper_contact_faces_checked = 0
    fixed_camera_stacks_checked = 0
    concrete_surface_regimes_checked = 0
    concrete_surface_regime_counts: dict[str, int] = {}
    concrete_body_profiles_checked = 0
    concrete_body_profile_counts: dict[str, int] = {}
    concrete_top_load_weathering_checked = 0
    concrete_top_load_weathering_patch_total = 0
    partition_image_relatives: dict[str, list[str]] = {
        "standard": [],
        "hard_occlusion": [],
        "exclude": [],
    }
    rfid_instance_count = 0
    class_image_counts = {"rfid_tag": 0, "concrete_sample": 0}
    render_seconds: list[float] = []
    checked_sha256 = 0
    binary_masks_checked = 0
    depth_files_checked = 0
    explicit_depth_disabled = 0
    current_config_sha = config_sha256(cfg)

    for metadata_path in metadata_paths:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        annotation_policy = cfg.get("outputs", {}).get("annotation_policy")
        expected_schema_version = 2 if annotation_policy else 1
        if int(metadata.get("schema_version", 0)) != expected_schema_version:
            errors.append(
                f"metadata_schema_version_mismatch:{metadata_path.name}:"
                f"{metadata.get('schema_version')}:{expected_schema_version}"
            )
        expected_stems.add(metadata_path.stem)
        seed = int(metadata["seed"])
        seen_seeds.add(seed)
        render_key = (seed, metadata["camera"])
        if render_key in seen_render_keys:
            errors.append(f"duplicate_render_key:{seed}:{metadata['camera']}")
        seen_render_keys.add(render_key)
        generator = metadata.get("generator", {})
        if generator.get("config_sha256") != current_config_sha:
            errors.append(f"config_sha256_mismatch:{metadata_path.name}")
        script_hash = generator.get("script_sha256")
        if not script_hash:
            errors.append(f"missing_script_sha256:{metadata_path.name}")
        else:
            script_hashes.add(script_hash)
            if script_hash != SCRIPT_SHA256:
                errors.append(f"generator_script_sha256_mismatch:{metadata_path.name}")
        camera_counts[metadata["camera"]] = camera_counts.get(metadata["camera"], 0) + 1
        machine_state = metadata.get("machine", {})
        if (
            int(machine_state.get("fixed_camera_stack_count", -1))
            != int(cfg["machine"].get("fixed_camera_stack_count", 0))
            or machine_state.get("fixed_camera_stack_status")
            != cfg["machine"].get("fixed_camera_stack_status")
            or machine_state.get("workshop_backdrop")
            != cfg["machine"].get("workshop_backdrop")
        ):
            errors.append(f"fixed_camera_stack_contract_mismatch:{metadata_path.name}")
        else:
            fixed_camera_stacks_checked += 1
        sample_record = metadata.get("sample", {})
        sample_shape = str(sample_record.get("shape", ""))
        surface_regime = str(sample_record.get("surface_regime", ""))
        allowed_regimes = cfg["sample"]["surface_regime_weights_by_shape"].get(
            sample_shape, {}
        )
        relief_range = cfg["sample"]["edge_relief_count_range_by_regime"].get(
            surface_regime
        )
        recorded_size_range = sample_record.get("edge_relief_size_range_m", [])
        expected_size_range = list(map(float, cfg["sample"]["edge_relief_size_m"]))
        size_range_valid = (
            isinstance(recorded_size_range, list)
            and len(recorded_size_range) == 2
            and all(
                math.isclose(float(actual), expected, abs_tol=1e-9)
                for actual, expected in zip(recorded_size_range, expected_size_range)
            )
        )
        edge_relief_count = int(sample_record.get("edge_relief_count", -1))
        weathering_count_range = cfg["sample"][
            "top_load_weathering_patch_count_range_by_regime"
        ].get(surface_regime)
        weathering_patch_count = int(
            sample_record.get("top_load_weathering_patch_count", -1)
        )
        weathering_material_counts = sample_record.get(
            "top_load_weathering_material_counts", {}
        )
        weathering_contract_valid = (
            weathering_count_range is not None
            and int(weathering_count_range[0])
            <= weathering_patch_count
            <= int(weathering_count_range[1])
            and isinstance(weathering_material_counts, dict)
            and set(weathering_material_counts) == {"ochre", "dark"}
            and sum(map(int, weathering_material_counts.values()))
            == weathering_patch_count
            and sample_record.get("top_load_weathering_profile")
            == "clustered_submillimetre_embedded_ochre_dark_residue_v1"
            and sample_record.get("top_load_weathering_status")
            == cfg["sample"]["top_load_weathering_status"]
        )
        body_profile = str(sample_record.get("body_profile", ""))
        notch = sample_record.get("spall_notch_m")
        notch_side = sample_record.get("spall_notch_side")
        notch_realization = sample_record.get("spall_notch_realization")
        fracture_tooth_count = int(
            sample_record.get("spall_fracture_tooth_count", -1)
        )
        fracture_cavity_count = int(
            sample_record.get("spall_fracture_cavity_count", -1)
        )
        cube_spall_aggregate_count = int(
            sample_record.get("cube_spall_aggregate_count", -1)
        )
        cylinder_spall_size = sample_record.get("cylinder_spall_size_m")
        cylinder_spall_angle = sample_record.get("cylinder_spall_angle_deg")
        cylinder_spall_aggregate_count = int(
            sample_record.get("cylinder_spall_aggregate_count", -1)
        )
        notch_contract_valid = False
        if sample_shape == "cube" and surface_regime == "spalled":
            notch_ranges = cfg["sample"][
                "spalled_cube_notch_fraction_range"
            ]
            tooth_range = list(
                map(
                    int,
                    cfg["sample"][
                        "spalled_cube_fracture_tooth_count_range"
                    ],
                )
            )
            cavity_range = list(
                map(
                    int,
                    cfg["sample"][
                        "spalled_cube_fracture_cavity_count_range"
                    ],
                )
            )
            sample_dims = list(map(float, sample_record["dimensions_m"]))
            notch_contract_valid = (
                body_profile
                == "single_hull_faceted_upper_front_corner_loss_v5"
                and isinstance(notch, list)
                and len(notch) == 3
                and notch_side in {"left", "right"}
                and notch_realization == "irregular_convex_hull_boolean_v2"
                and tooth_range[0]
                <= fracture_tooth_count
                <= tooth_range[1]
                and cavity_range[0]
                <= fracture_cavity_count
                <= cavity_range[1]
                and 18 <= cube_spall_aggregate_count <= 28
                and all(
                    float(notch_ranges[axis][0]) * sample_dims[index]
                    <= float(notch[index])
                    <= float(notch_ranges[axis][1]) * sample_dims[index]
                    for index, axis in enumerate(("x", "y", "z"))
                )
            )
        elif sample_shape == "cylinder" and surface_regime == "spalled":
            cylinder_spall_bounds = list(
                map(
                    float,
                    cfg["sample"]["spalled_cylinder_cavity_size_m"],
                )
            )
            notch_contract_valid = (
                body_profile
                == "solid_nominal_with_local_faceted_cylinder_spall_v1"
                and notch is None
                and notch_side is None
                and notch_realization is None
                and fracture_tooth_count == 0
                and fracture_cavity_count == 0
                and isinstance(cylinder_spall_size, list)
                and len(cylinder_spall_size) == 3
                and cylinder_spall_bounds[0]
                <= float(cylinder_spall_size[0])
                <= cylinder_spall_bounds[1]
                and cylinder_spall_bounds[0] * 0.78
                <= float(cylinder_spall_size[1])
                <= cylinder_spall_bounds[1] * 0.94
                and cylinder_spall_bounds[0] * 0.82
                <= float(cylinder_spall_size[2])
                <= cylinder_spall_bounds[1] * 1.12
                and cylinder_spall_angle is not None
                and -58.5 <= float(cylinder_spall_angle) <= 58.5
                and 18 <= cylinder_spall_aggregate_count <= 26
                and cube_spall_aggregate_count == 0
                and sample_record.get("cylinder_spall_status")
                == cfg["sample"]["spalled_cylinder_cavity_status"]
            )
        else:
            notch_contract_valid = (
                body_profile == "solid_nominal_v1"
                and notch is None
                and notch_side is None
                and notch_realization is None
                and fracture_tooth_count == 0
                and fracture_cavity_count == 0
                and cylinder_spall_size is None
                and cylinder_spall_angle is None
                and cylinder_spall_aggregate_count == 0
                and cube_spall_aggregate_count == 0
            )
        expected_pore_count = int(
            int(cfg["sample"]["pore_count_base"])
            + int(cfg["sample"]["pore_count_damage_gain"])
            * float(sample_record["damage"])
        )
        recorded_pore_radius_range = sample_record.get(
            "pore_radius_range_m", []
        )
        pore_contract_valid = (
            int(sample_record.get("pore_count", -1)) == expected_pore_count
            and isinstance(recorded_pore_radius_range, list)
            and len(recorded_pore_radius_range) == 2
            and all(
                math.isclose(float(actual), float(expected), abs_tol=1e-12)
                for actual, expected in zip(
                    recorded_pore_radius_range,
                    cfg["sample"]["pore_radius_m"],
                )
            )
            and math.isclose(
                float(sample_record.get("pore_radius_distribution_power", -1.0)),
                float(cfg["sample"]["pore_radius_distribution_power"]),
                abs_tol=1e-12,
            )
            and int(sample_record.get("pore_shadow_count", -1))
            == (expected_pore_count * 4) // 5
            and sample_record.get("pore_shadow_profile")
            == "subsurface_recessed_backing_v1"
        )
        aggregate_count = int(
            sample_record.get("exposed_aggregate_count", -1)
        )
        aggregate_count_range = cfg["sample"][
            "exposed_aggregate_count_range_by_regime"
        ].get(surface_regime)
        aggregate_radius_range = sample_record.get(
            "exposed_aggregate_radius_range_m", []
        )
        expected_aggregate_radius_range = list(
            map(float, cfg["sample"]["exposed_aggregate_radius_m"])
        )
        aggregate_material_counts = sample_record.get(
            "exposed_aggregate_material_counts", {}
        )
        aggregate_contract_valid = (
            aggregate_count_range is not None
            and int(aggregate_count_range[0])
            <= aggregate_count
            <= int(aggregate_count_range[1])
            and isinstance(aggregate_radius_range, list)
            and len(aggregate_radius_range) == 2
            and all(
                math.isclose(float(actual), expected, abs_tol=1e-12)
                for actual, expected in zip(
                    aggregate_radius_range,
                    expected_aggregate_radius_range,
                )
            )
            and isinstance(aggregate_material_counts, dict)
            and set(aggregate_material_counts)
            == {"light_aggregate", "dark_mortar", "body_tone"}
            and sum(map(int, aggregate_material_counts.values()))
            == aggregate_count
        )
        if (
            surface_regime not in allowed_regimes
            or relief_range is None
            or not int(relief_range[0]) <= edge_relief_count <= int(relief_range[1])
            or not size_range_valid
            or sample_record.get("surface_profile")
            != "cast_skin_with_scale_bounded_visible_pores_exposed_aggregate_faceted_spall_and_load_zone_v9"
            or not notch_contract_valid
            or not pore_contract_valid
            or not aggregate_contract_valid
            or not weathering_contract_valid
            or sample_record.get("spall_notch_status")
            != cfg["sample"]["spalled_cube_notch_status"]
            or sample_record.get("cylinder_spall_status")
            != cfg["sample"]["spalled_cylinder_cavity_status"]
            or sample_record.get("surface_regime_distribution_status")
            != cfg["sample"]["surface_regime_status"]
        ):
            errors.append(
                f"concrete_surface_regime_contract_mismatch:{metadata_path.name}:"
                f"{sample_shape}:{surface_regime}:{edge_relief_count}:"
                f"{recorded_size_range}"
            )
        else:
            concrete_surface_regimes_checked += 1
            concrete_surface_regime_counts[surface_regime] = (
                concrete_surface_regime_counts.get(surface_regime, 0) + 1
            )
            concrete_body_profiles_checked += 1
            concrete_body_profile_counts[body_profile] = (
                concrete_body_profile_counts.get(body_profile, 0) + 1
            )
            concrete_top_load_weathering_checked += 1
            concrete_top_load_weathering_patch_total += weathering_patch_count
        lower_face = metadata.get("machine", {}).get("lower_contact_face")
        if not isinstance(lower_face, dict):
            errors.append(f"missing_lower_contact_face:{metadata_path.name}")
        else:
            machine_cfg = cfg["machine"]
            expected_lower_diameter = float(machine_cfg["platen_diameter_m"]) * float(
                machine_cfg["lower_contact_face_diameter_scale"]
            )
            expected_lower_thickness = float(
                machine_cfg["lower_contact_face_thickness_m"]
            )
            sample_bottom = float(metadata["sample"]["location_m"][2]) - float(
                metadata["sample"]["dimensions_m"][2]
            ) / 2.0
            specimen_gap = sample_bottom - float(lower_face.get("top_z_m", -1.0))
            lower_profile = str(lower_face.get("surface_profile", ""))
            if (
                not math.isclose(
                    float(lower_face.get("diameter_m", -1.0)),
                    expected_lower_diameter,
                    abs_tol=2e-5,
                )
                or not math.isclose(
                    float(lower_face.get("thickness_m", -1.0)),
                    expected_lower_thickness,
                    abs_tol=2e-5,
                )
                or not math.isclose(specimen_gap, 0.0, abs_tol=2e-5)
                or lower_profile not in machine_cfg.get(
                    "lower_contact_face_surface_profile_weights",
                    {"dry_used": 0.46, "dusty_used": 0.34, "damp_residue": 0.20},
                )
                or lower_face.get("surface_status")
                != machine_cfg.get(
                    "lower_contact_face_surface_status",
                    "provisional default used-steel augmentation; calibrate before production",
                )
            ):
                errors.append(
                    f"lower_contact_face_contract_mismatch:{metadata_path.name}:"
                    f"{lower_face}:gap={specimen_gap}"
                )
            else:
                lower_contact_faces_checked += 1
                lower_contact_face_profile_counts[lower_profile] = (
                    lower_contact_face_profile_counts.get(lower_profile, 0) + 1
                )
        face = metadata.get("machine", {}).get("upper_contact_face")
        if not isinstance(face, dict):
            errors.append(f"missing_upper_contact_face:{metadata_path.name}")
        else:
            expected_face_diameter = float(cfg["machine"]["platen_diameter_m"]) * float(
                cfg["machine"].get("upper_contact_face_diameter_scale", 0.985)
            )
            expected_face_thickness = float(
                cfg["machine"].get("upper_contact_face_thickness_m", 0.0006)
            )
            sample_top = float(metadata["sample"]["location_m"][2]) + float(
                metadata["sample"]["dimensions_m"][2]
            ) / 2.0
            contact_gap = float(face.get("bottom_z_m", -1.0)) - sample_top
            if (
                not math.isclose(
                    float(face.get("diameter_m", -1.0)),
                    expected_face_diameter,
                    abs_tol=2e-5,
                )
                or not math.isclose(
                    float(face.get("thickness_m", -1.0)),
                    expected_face_thickness,
                    abs_tol=2e-5,
                )
                or contact_gap < float(cfg["rfid_tag"]["size_m"][2]) * 2.0
                or contact_gap > 0.001
                or face.get("material_profile")
                != cfg["machine"].get("upper_contact_face_material_profile")
            ):
                errors.append(
                    f"upper_contact_face_contract_mismatch:{metadata_path.name}:"
                    f"{face}:gap={contact_gap}"
                )
            else:
                upper_contact_faces_checked += 1
        lighting_name = metadata["lighting"]["profile"]
        lighting_counts[lighting_name] = lighting_counts.get(lighting_name, 0) + 1
        rfid_records = metadata.get("rfid_tags")
        if isinstance(rfid_records, list):
            rfid_instance_count += len(rfid_records)
            for record in rfid_records:
                rfid_state = record["state"]
                rfid_state_counts[rfid_state] = rfid_state_counts.get(rfid_state, 0) + 1
                label_status = record.get("detection_policy", {}).get("label_status", "unknown")
                rfid_label_status_counts[label_status] = rfid_label_status_counts.get(label_status, 0) + 1
            partition = metadata.get("detection_annotations", {}).get("image_partition", "unknown")
            annotation_partition_counts[partition] = annotation_partition_counts.get(partition, 0) + 1
            rfid_by_id = {int(record["instance_id"]): record for record in rfid_records}
            for paper in metadata.get("paper_labels", []):
                mode = str(paper.get("occlusion_mode", "unknown"))
                paper_occlusion_counts[mode] = paper_occlusion_counts.get(mode, 0) + 1
                linked_id = paper.get("linked_rfid_instance_id")
                if linked_id is None:
                    if mode != "independent":
                        errors.append(
                            f"paper_occlusion_missing_link:{metadata_path.name}:{mode}"
                        )
                    continue
                paper_rfid_links_checked += 1
                linked_record = rfid_by_id.get(int(linked_id))
                if linked_record is None:
                    errors.append(
                        f"paper_occlusion_unknown_rfid:{metadata_path.name}:{linked_id}"
                    )
                    continue
                policy_record = linked_record.get("detection_policy") or {}
                if mode == "fully_hidden":
                    if linked_record.get("visible_annotation") is not None:
                        errors.append(
                            f"fully_hidden_paper_tag_has_visible_pixels:"
                            f"{metadata_path.name}:{linked_id}"
                        )
                    if policy_record.get("include_in_yolo"):
                        errors.append(
                            f"fully_hidden_paper_tag_is_labelled:"
                            f"{metadata_path.name}:{linked_id}"
                        )
                elif mode == "partial_tip_visible":
                    if linked_record.get("visible_annotation") is None:
                        warnings.append(
                            f"partial_tip_target_lost_to_other_occlusion:"
                            f"{metadata_path.name}:{linked_id}"
                        )
                else:
                    errors.append(
                        f"paper_occlusion_unknown_mode:{metadata_path.name}:{mode}"
                    )
        else:
            rfid_state = metadata["rfid_tag"]["state"]
            rfid_state_counts[rfid_state] = rfid_state_counts.get(rfid_state, 0) + 1
        render_seconds.append(float(metadata["render"]["elapsed_seconds"]))

        outputs = metadata.get("outputs", {})
        for dataset_key in ("rgb", "label"):
            relative = outputs.get(dataset_key)
            if isinstance(relative, str) and relative.startswith("partitions/"):
                expected_partition_dataset_relatives.add(relative)
        for required_key in ("rgb", "label", "rfid_mask", "concrete_mask"):
            if not outputs.get(required_key):
                errors.append(f"missing_output_declaration:{metadata_path.name}:{required_key}")
        depth_enabled = bool(metadata.get("render", {}).get("depth_enabled"))
        if depth_enabled and not outputs.get("depth_raw"):
            errors.append(f"missing_output_declaration:{metadata_path.name}:depth_raw")
        if depth_enabled and not outputs.get("depth_aligned"):
            errors.append(f"missing_output_declaration:{metadata_path.name}:depth_aligned")
        if depth_enabled and not metadata.get("depth_stats"):
            errors.append(f"missing_depth_stats:{metadata_path.name}")
        elif not depth_enabled and cfg["outputs"]["depth_exr"]:
            explicit_depth_disabled += 1

        for key, relative in outputs.items():
            if relative is None or key == "blend" or isinstance(relative, list):
                continue
            target = output_root / relative
            if not target.is_file() or target.stat().st_size == 0:
                errors.append(f"missing_output:{metadata_path.name}:{key}:{relative}")
                continue
            expected = metadata.get("sha256", {}).get(key)
            if not expected:
                errors.append(f"missing_sha256:{metadata_path.name}:{key}")
            if expected and sha256_file(target) != expected:
                errors.append(f"sha256_mismatch:{metadata_path.name}:{key}")
            elif expected:
                checked_sha256 += 1

        expected_resolution = metadata["render"]["resolution_px"]
        annotations = metadata["visible_annotations"]
        for class_name, output_key in (("rfid_tag", "rfid_mask"), ("concrete_sample", "concrete_mask")):
            relative = outputs.get(output_key)
            if not relative or not (output_root / relative).is_file():
                continue
            try:
                mask_info = binary_png_stats(output_root / relative)
            except Exception as exc:
                errors.append(f"invalid_binary_mask:{metadata_path.name}:{class_name}:{exc}")
                continue
            binary_masks_checked += 1
            if mask_info["resolution_px"] != expected_resolution:
                errors.append(
                    f"mask_resolution_mismatch:{metadata_path.name}:{class_name}:"
                    f"{mask_info['resolution_px']}:{expected_resolution}"
                )
            box = annotations[class_name]
            expected_pixels = 0 if box is None else int(box["pixels"])
            if mask_info["foreground_pixels"] != expected_pixels:
                errors.append(
                    f"mask_pixel_count_mismatch:{metadata_path.name}:{class_name}:"
                    f"{mask_info['foreground_pixels']}:{expected_pixels}"
                )

        if isinstance(rfid_records, list):
            instance_relatives = outputs.get("rfid_instance_masks") or []
            instance_hashes = metadata.get("sha256", {}).get("rfid_instance_masks") or []
            if len(instance_relatives) != len(rfid_records) or len(instance_hashes) != len(rfid_records):
                errors.append(
                    f"rfid_instance_output_count_mismatch:{metadata_path.name}:"
                    f"{len(instance_relatives)}:{len(instance_hashes)}:{len(rfid_records)}"
                )
            for index, record in enumerate(rfid_records):
                if index >= len(instance_relatives):
                    continue
                relative = instance_relatives[index]
                expected_instance_mask_relatives.add(str(relative))
                target = output_root / relative
                if not target.is_file():
                    errors.append(f"missing_rfid_instance_mask:{metadata_path.name}:{relative}")
                    continue
                try:
                    mask_info = binary_png_stats(target)
                except Exception as exc:
                    errors.append(f"invalid_rfid_instance_mask:{metadata_path.name}:{index}:{exc}")
                    continue
                binary_masks_checked += 1
                if mask_info["resolution_px"] != expected_resolution:
                    errors.append(
                        f"rfid_instance_mask_resolution_mismatch:{metadata_path.name}:{index}"
                    )
                visible = record.get("visible_annotation")
                expected_pixels = 0 if visible is None else int(visible["pixels"])
                if mask_info["foreground_pixels"] != expected_pixels:
                    errors.append(
                        f"rfid_instance_mask_pixel_count_mismatch:{metadata_path.name}:{index}:"
                        f"{mask_info['foreground_pixels']}:{expected_pixels}"
                    )
                if index < len(instance_hashes) and sha256_file(target) != instance_hashes[index]:
                    errors.append(f"sha256_mismatch:{metadata_path.name}:rfid_instance_{index:02d}")
                else:
                    checked_sha256 += 1

        if depth_enabled:
            all_depth_stats = metadata.get("depth_stats") or {}
            for depth_kind in ("raw_metric", "aligned_approximate"):
                stats = all_depth_stats.get(depth_kind) or {}
                if stats.get("resolution_px") != expected_resolution:
                    errors.append(f"depth_resolution_mismatch:{metadata_path.name}:{depth_kind}")
                if float(stats.get("finite_fraction", 0.0)) < 0.95:
                    errors.append(f"invalid_depth_finite_fraction:{metadata_path.name}:{depth_kind}")
                if float(stats.get("valid_metric_fraction", 0.0)) < 0.90:
                    errors.append(f"invalid_depth_metric_fraction:{metadata_path.name}:{depth_kind}")
                depth_files_checked += 1

        concrete_box = annotations.get("concrete_sample")
        if concrete_box is not None:
            class_image_counts["concrete_sample"] += 1
            values = concrete_box["yolo"]
            if len(values) != 4 or any(not (0.0 <= float(value) <= 1.0) for value in values):
                errors.append(f"invalid_yolo_box:{metadata_path.name}:concrete_sample:{values}")
            if concrete_box["pixels"] < cfg["outputs"]["min_visible_pixels"]["concrete_sample"]:
                errors.append(
                    f"low_visibility:{metadata_path.name}:concrete_sample:{concrete_box['pixels']}"
                )
            min_size = cfg["outputs"]["min_visible_size_px"]["concrete_sample"]
            if any(actual < required for actual, required in zip(concrete_box["size_px"], min_size)):
                errors.append(
                    f"low_bbox_size:{metadata_path.name}:concrete_sample:"
                    f"{concrete_box['size_px']}:{min_size}"
                )

        if isinstance(rfid_records, list):
            labelled_instances = [
                record
                for record in rfid_records
                if record.get("detection_policy", {}).get("include_in_yolo")
            ]
            if labelled_instances:
                class_image_counts["rfid_tag"] += 1
            for record in rfid_records:
                visible = record.get("visible_annotation")
                policy_record = record.get("detection_policy") or {}
                status = policy_record.get("label_status")
                included = bool(policy_record.get("include_in_yolo"))
                projected = record.get("projected_amodal_proxy") or {}
                recomputed = classify_rfid_annotation(
                    visible,
                    projected,
                    metadata["render"]["resolution_px"],
                    annotation_policy,
                )
                for decision_key in ("label_status", "include_in_yolo", "reasons"):
                    if policy_record.get(decision_key) != recomputed.get(decision_key):
                        errors.append(
                            f"rfid_policy_mismatch:{metadata_path.name}:"
                            f"{record.get('instance_id')}:{decision_key}"
                        )
                observed_visibility = float(policy_record.get("visibility_fraction_proxy", -1.0))
                if not math.isclose(
                    observed_visibility,
                    float(recomputed["visibility_fraction_proxy"]),
                    rel_tol=1e-7,
                    abs_tol=1e-7,
                ):
                    errors.append(
                        f"rfid_policy_mismatch:{metadata_path.name}:"
                        f"{record.get('instance_id')}:visibility_fraction_proxy"
                    )
                if included and visible is None:
                    errors.append(
                        f"included_rfid_has_no_visible_bbox:{metadata_path.name}:{record.get('instance_id')}"
                    )
                if status == "excluded_too_small_or_occluded" and included:
                    errors.append(
                        f"excluded_rfid_is_labelled:{metadata_path.name}:{record.get('instance_id')}"
                    )
                if visible is not None:
                    values = visible["yolo"]
                    if len(values) != 4 or any(not (0.0 <= float(value) <= 1.0) for value in values):
                        errors.append(
                            f"invalid_yolo_box:{metadata_path.name}:rfid_instance:"
                            f"{record.get('instance_id')}:{values}"
                        )
            recomputed_statuses = [
                classify_rfid_annotation(
                    record.get("visible_annotation"),
                    record.get("projected_amodal_proxy") or {},
                    metadata["render"]["resolution_px"],
                    annotation_policy,
                )["label_status"]
                for record in rfid_records
            ]
            if "excluded_too_small_or_occluded" in recomputed_statuses:
                recomputed_partition = "exclude"
            elif "hard_positive" in recomputed_statuses:
                recomputed_partition = "hard_occlusion"
            else:
                recomputed_partition = "standard"
            observed_partition = metadata.get("detection_annotations", {}).get("image_partition")
            if observed_partition != recomputed_partition:
                errors.append(
                    f"annotation_partition_mismatch:{metadata_path.name}:"
                    f"{observed_partition}:{recomputed_partition}"
                )
            if annotation_policy:
                rgb_relative = outputs.get("rgb", "")
                label_relative = outputs.get("label", "")
                required_rgb_prefix = f"partitions/{recomputed_partition}/images/"
                required_label_prefix = f"partitions/{recomputed_partition}/labels/"
                if not str(rgb_relative).startswith(required_rgb_prefix):
                    errors.append(
                        f"unsafe_partition_rgb_path:{metadata_path.name}:{rgb_relative}:"
                        f"{required_rgb_prefix}"
                    )
                else:
                    partition_image_relatives[recomputed_partition].append(str(rgb_relative))
                if not str(label_relative).startswith(required_label_prefix):
                    errors.append(
                        f"unsafe_partition_label_path:{metadata_path.name}:{label_relative}:"
                        f"{required_label_prefix}"
                    )
        else:
            rfid_box = annotations.get("rfid_tag")
            if rfid_box is not None:
                class_image_counts["rfid_tag"] += 1
                values = rfid_box["yolo"]
                if len(values) != 4 or any(not (0.0 <= float(value) <= 1.0) for value in values):
                    errors.append(f"invalid_yolo_box:{metadata_path.name}:rfid_tag:{values}")
                if rfid_box["pixels"] < cfg["outputs"]["min_visible_pixels"]["rfid_tag"]:
                    errors.append(f"low_visibility:{metadata_path.name}:rfid_tag:{rfid_box['pixels']}")
                min_size = cfg["outputs"]["min_visible_size_px"]["rfid_tag"]
                if any(actual < required for actual, required in zip(rfid_box["size_px"], min_size)):
                    errors.append(
                        f"low_bbox_size:{metadata_path.name}:rfid_tag:{rfid_box['size_px']}:{min_size}"
                    )

            tag_missing = bool(metadata["rfid_tag"]["missing"])
            if tag_missing and rfid_box is not None:
                errors.append(f"missing_tag_has_foreground:{metadata_path.name}")
            if not tag_missing and rfid_box is None:
                errors.append(f"visible_tag_has_no_annotation:{metadata_path.name}")

        label_relative = outputs.get("label")
        if label_relative and (output_root / label_relative).is_file():
            label_path = output_root / label_relative
            actual_lines = label_path.read_text(encoding="utf-8").splitlines()
            expected_lines = []
            if isinstance(rfid_records, list):
                for record in rfid_records:
                    box = record.get("visible_annotation")
                    if box is not None and record.get("detection_policy", {}).get("include_in_yolo"):
                        expected_lines.append(
                            "0 " + " ".join(f"{float(value):.8f}" for value in box["yolo"])
                        )
            else:
                box = annotations.get("rfid_tag")
                if box is not None:
                    expected_lines.append(
                        "0 " + " ".join(f"{float(value):.8f}" for value in box["yolo"])
                    )
            box = annotations.get("concrete_sample")
            if box is not None:
                expected_lines.append(
                    "1 " + " ".join(f"{float(value):.8f}" for value in box["yolo"])
                )
            if actual_lines != expected_lines:
                errors.append(f"label_metadata_mismatch:{metadata_path.name}")

    if len(camera_counts) < 2 and len(metadata_paths) >= 2:
        warnings.append("pilot_contains_only_one_camera_profile")
    if expected_count is not None and len(metadata_paths) != expected_count:
        errors.append(f"image_count_mismatch:{len(metadata_paths)}:{expected_count}")
    required_camera_names = set(cfg["cameras"])
    if require_both_cameras and set(camera_counts) != required_camera_names:
        errors.append(
            f"camera_coverage_mismatch:{sorted(camera_counts)}:{sorted(required_camera_names)}"
        )
    if class_image_counts["concrete_sample"] != len(metadata_paths):
        errors.append("concrete_sample_not_visible_in_every_image")
    if len(script_hashes) > 1:
        errors.append(f"mixed_generator_script_hashes:{sorted(script_hashes)}")
    if explicit_depth_disabled:
        warnings.append(f"depth_explicitly_disabled_for_{explicit_depth_disabled}_image(s)")
    if annotation_partition_counts.get("hard_occlusion"):
        warnings.append(
            f"hard_occlusion_partition_contains_{annotation_partition_counts['hard_occlusion']}_image(s)"
        )
    if annotation_partition_counts.get("exclude"):
        warnings.append(
            f"excluded_annotation_partition_contains_{annotation_partition_counts['exclude']}_image(s)"
        )

    partition_manifest_paths: dict[str, str] = {}
    if cfg.get("outputs", {}).get("annotation_policy"):
        manifest_dir = output_root / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        for partition_name, relatives in partition_image_relatives.items():
            manifest_path = manifest_dir / f"{partition_name}_images.txt"
            manifest_path.write_text(
                "".join(f"{relative}\n" for relative in sorted(relatives)),
                encoding="utf-8",
            )
            partition_manifest_paths[partition_name] = str(manifest_path.relative_to(output_root))

    published_locations = (
        ("images", "*.png"),
        ("labels", "*.txt"),
        ("masks/rfid_tag", "*.png"),
        ("masks/concrete_sample", "*.png"),
        ("depth_raw", "*.exr"),
        ("depth_aligned", "*.exr"),
    )
    for relative, pattern in published_locations:
        directory = output_root / relative
        if not directory.exists():
            continue
        orphaned = sorted(path.name for path in directory.glob(pattern) if path.stem not in expected_stems)
        if orphaned:
            errors.append(f"orphan_outputs:{relative}:{orphaned}")
    for pattern in ("partitions/*/images/*.png", "partitions/*/labels/*.txt"):
        orphaned = sorted(
            str(path.relative_to(output_root))
            for path in output_root.glob(pattern)
            if str(path.relative_to(output_root)) not in expected_partition_dataset_relatives
        )
        if orphaned:
            errors.append(f"orphan_partition_outputs:{pattern}:{orphaned}")
    instance_directory = output_root / "masks" / "rfid_instances"
    if instance_directory.exists():
        orphaned_instances = sorted(
            str(path.relative_to(output_root))
            for path in instance_directory.glob("*.png")
            if str(path.relative_to(output_root)) not in expected_instance_mask_relatives
        )
        if orphaned_instances:
            errors.append(f"orphan_outputs:masks/rfid_instances:{orphaned_instances}")
    temporary_dirs = sorted(path.name for path in output_root.glob(".tmp_ebis_*") if path.is_dir())
    if temporary_dirs:
        errors.append(f"stale_temporary_directories:{temporary_dirs}")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "generator_contract": cfg["domain"],
        "image_count": len(metadata_paths),
        "expected_image_count": expected_count,
        "both_cameras_required": require_both_cameras,
        "unique_seed_count": len(seen_seeds),
        "unique_render_key_count": len(seen_render_keys),
        "camera_counts": camera_counts,
        "lighting_counts": lighting_counts,
        "rfid_state_counts": rfid_state_counts,
        "rfid_instance_count": rfid_instance_count,
        "rfid_label_status_counts": rfid_label_status_counts,
        "paper_occlusion_counts": paper_occlusion_counts,
        "paper_rfid_links_checked": paper_rfid_links_checked,
        "lower_contact_faces_checked": lower_contact_faces_checked,
        "lower_contact_face_profile_counts": lower_contact_face_profile_counts,
        "upper_contact_faces_checked": upper_contact_faces_checked,
        "fixed_camera_stacks_checked": fixed_camera_stacks_checked,
        "concrete_surface_regimes_checked": concrete_surface_regimes_checked,
        "concrete_surface_regime_counts": concrete_surface_regime_counts,
        "concrete_body_profiles_checked": concrete_body_profiles_checked,
        "concrete_body_profile_counts": concrete_body_profile_counts,
        "concrete_top_load_weathering_checked": concrete_top_load_weathering_checked,
        "concrete_top_load_weathering_patch_total": concrete_top_load_weathering_patch_total,
        "annotation_partition_counts": annotation_partition_counts,
        "partition_manifests": partition_manifest_paths,
        "class_image_counts": class_image_counts,
        "sha256_files_checked": checked_sha256,
        "binary_masks_checked": binary_masks_checked,
        "depth_files_checked": depth_files_checked,
        "config_sha256": current_config_sha,
        "generator_script_sha256": next(iter(script_hashes)) if len(script_hashes) == 1 else None,
        "render_seconds": {
            "total": sum(render_seconds),
            "mean": sum(render_seconds) / len(render_seconds),
            "min": min(render_seconds),
            "max": max(render_seconds),
        },
        "errors": errors,
        "warnings": warnings,
    }
    report_path = output_root / "validation.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise RuntimeError(f"Dataset validation failed with {len(errors)} error(s); see {report_path}")
    print(f"EBIS_DATASET_VALIDATION_OK {len(metadata_paths)} {report_path}", flush=True)
    return result


def configure_portable_blend_outputs(scene: bpy.types.Scene, stem: str) -> dict:
    """Reset transient absolute render paths before a .blend is published."""
    relative_root = f"//../manual_preview/{stem}"
    scene.render.filepath = f"{relative_root}/rgb.png"
    file_output_nodes: list[str] = []
    if scene.use_nodes and scene.node_tree:
        for node in scene.node_tree.nodes:
            if node.bl_idname == "CompositorNodeOutputFile":
                node.base_path = f"{relative_root}/passes"
                file_output_nodes.append(node.name)
    scene["ebis_portable_output_root"] = relative_root
    scene["ebis_file_output_nodes_rebased"] = len(file_output_nodes)
    return {
        "saved_blend_output_root": relative_root,
        "saved_blend_file_output_nodes": file_output_nodes,
    }


def build_and_save(
    cfg: dict,
    seed: int,
    camera: str | None,
    output_root: Path,
    resolution: str | None,
    samples: int | None,
    force_cpu: bool,
) -> Path:
    state = build_scene(cfg, seed, camera, resolution, samples, force_cpu)
    assert_scene_contract(cfg, state)
    output_path = output_root.resolve() / "scenes" / f"ebis_reference_{state['camera']}_{seed:06d}.blend"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    configure_portable_blend_outputs(bpy.context.scene, output_path.stem)
    bpy.context.preferences.filepaths.use_file_compression = True
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path), compress=True)
    print(f"EBIS_SCENE_BUILD_OK {output_path}", flush=True)
    return output_path


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    base_seed = args.seed if args.seed is not None else int(cfg["pilot"]["start_seed"])
    output_root = args.output
    include_depth = bool(cfg["outputs"]["depth_exr"]) and not args.no_depth

    if args.action in {"render", "batch"}:
        (output_root.resolve() / "validation.json").unlink(missing_ok=True)

    if args.action == "build":
        build_and_save(
            cfg,
            base_seed,
            args.camera,
            output_root,
            args.resolution,
            args.samples,
            args.cpu,
        )
        return 0
    if args.action == "render":
        render_one(
            cfg,
            base_seed,
            args.camera,
            output_root,
            args.resolution,
            args.samples,
            args.cpu,
            include_depth,
            args.save_blend,
            args.overwrite,
        )
        validate_dataset(output_root, cfg)
        return 0
    if args.action == "batch":
        count = args.count if args.count is not None else int(cfg["pilot"]["preview_count"])
        if count < 1:
            raise ValueError("--count must be positive")
        resolved_output = output_root.resolve()
        resolved_output.mkdir(parents=True, exist_ok=True)
        run_manifest_path = resolved_output / "run_manifest.json"
        lock_path = resolved_output / ".generation.lock"
        if run_manifest_path.exists() and not args.overwrite:
            raise FileExistsError(f"Batch run manifest exists; choose a fresh output or use --overwrite: {run_manifest_path}")
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise RuntimeError(f"Output is locked by another or interrupted generator: {lock_path}") from exc
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_fd)
        started = time.perf_counter()
        expected_render_keys = []
        for index in range(count):
            seed = base_seed + index
            camera_name = args.camera or ("camera_door" if seed % 2 == 0 else "camera_angled")
            expected_render_keys.append({"seed": seed, "camera": camera_name})
        run_manifest = {
            "schema_version": 1,
            "status": "IN_PROGRESS",
            "domain": cfg["domain"],
            "generator_script_sha256": SCRIPT_SHA256,
            "config_sha256": config_sha256(cfg),
            "base_seed": base_seed,
            "expected_count": count,
            "expected_render_keys": expected_render_keys,
            "depth_enabled": include_depth,
            "resolution_override": args.resolution,
            "samples_override": args.samples,
            "started_unix_s": time.time(),
        }
        write_json_atomic(run_manifest_path, run_manifest)
        try:
            for index in range(count):
                render_one(
                    cfg,
                    base_seed + index,
                    args.camera,
                    output_root,
                    args.resolution,
                    args.samples,
                    args.cpu,
                    include_depth,
                    args.save_blend and index == 0,
                    args.overwrite,
                )
            result = validate_dataset(
                output_root,
                cfg,
                expected_count=count,
                require_both_cameras=args.camera is None and count >= 2,
            )
        except Exception as exc:
            run_manifest["status"] = "FAIL"
            run_manifest["finished_unix_s"] = time.time()
            run_manifest["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            write_json_atomic(run_manifest_path, run_manifest)
            raise
        finally:
            lock_path.unlink(missing_ok=True)
        run_manifest["status"] = "PASS"
        run_manifest["finished_unix_s"] = time.time()
        run_manifest["validation_sha256"] = sha256_file(resolved_output / "validation.json")
        write_json_atomic(run_manifest_path, run_manifest)
        print(
            f"EBIS_BATCH_OK count={count} elapsed={time.perf_counter() - started:.2f}s "
            f"mean_render={result['render_seconds']['mean']:.2f}s",
            flush=True,
        )
        return 0
    if args.action == "validate":
        validate_dataset(
            output_root,
            cfg,
            expected_count=args.expected_count,
            require_both_cameras=args.require_both_cameras,
        )
        return 0
    raise AssertionError(args.action)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"EBIS_GENERATOR_ERROR {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
