#!/usr/bin/env python3
"""Render reference-quality front/back macro views of the EBIS visual RFID asset."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import generate_ebis as ebis  # noqa: E402


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolution", default="1920x1080")
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args(argv)


def add_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], lens: float):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36.0
    data.dof.use_dof = True
    data.dof.focus_distance = (Vector(location) - Vector(target)).length
    data.dof.aperture_fstop = 8.0
    camera = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    ebis.point_object_at(camera, target)
    return camera


def configure_scene(cfg: dict, resolution: str, samples: int, force_cpu: bool) -> dict:
    width, height = (int(value) for value in resolution.lower().split("x", 1))
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.72
    device = ebis.configure_cycles(scene, cfg, force_cpu)
    scene.cycles.samples = samples
    scene.cycles.seed = 90451
    scene.cycles.use_denoising = True
    return {"resolution_px": [width, height], "samples": samples, "device": device}


def build_macro_scene(cfg: dict, resolution: str, samples: int, force_cpu: bool):
    ebis.clean_scene()
    scene = bpy.context.scene
    scene.name = "EBIS_RFID_FRONT_BACK_REFERENCE"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    rng = random.Random(90451)
    mats = ebis.build_materials(cfg, moisture=0.08, rng=rng)
    hero_collection = ebis.ensure_collection("RFID_HERO_STAGE")

    board, _, _ = ebis.new_principled(
        "Neutral graphite macro board",
        ebis.srgb((0.055, 0.064, 0.073)),
        roughness=0.63,
        metallic=0.04,
        coat=0.08,
    )
    ebis.make_box(
        "Macro backing board",
        (0.0, 0.007, 0.0),
        (0.092, 0.008, 0.078),
        board,
        hero_collection,
        bevel=0.004,
    )

    front_root, _ = ebis.build_rfid_geometry(cfg, mats)
    front_root.name = "RFID_FRONT_REFERENCE"
    front_root.matrix_world = Matrix.Translation(Vector((0.0, 0.0018, 0.019)))

    back_root, _ = ebis.build_rfid_geometry(cfg, mats)
    back_root.name = "RFID_BACK_REFERENCE"
    back_root.matrix_world = (
        Matrix.Translation(Vector((0.0, 0.0018, -0.019)))
        @ Matrix.Rotation(math.pi, 4, "X")
    )

    lights = ebis.ensure_collection("RFID_HERO_LIGHTS")
    ebis.add_area_light(
        "Large warm key",
        (-0.105, -0.12, 0.13),
        (0.0, 0.0, 0.01),
        ebis.kelvin_to_srgb(5100.0),
        6.0,
        0.13,
        0.13,
        lights,
    )
    ebis.add_area_light(
        "Cool soft fill",
        (0.11, -0.08, 0.06),
        (0.0, 0.0, -0.005),
        ebis.kelvin_to_srgb(6500.0),
        2.6,
        0.1,
        0.12,
        lights,
    )
    ebis.add_area_light(
        "Copper edge light",
        (0.0, 0.05, 0.11),
        (0.0, 0.0, 0.0),
        ebis.kelvin_to_srgb(3900.0),
        3.8,
        0.08,
        0.04,
        lights,
    )
    world = bpy.data.worlds.new("RFID macro dark world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = ebis.srgb((0.008, 0.011, 0.015))
    background.inputs["Strength"].default_value = 0.025
    scene.world = world

    cameras = {
        "rfid_front_back": add_camera(
            "RFID combined macro camera", (0.0, -0.185, 0.004), (0.0, 0.0, 0.0), 58.0
        ),
        "rfid_front": add_camera(
            "RFID front macro camera", (0.0, -0.15, 0.019), (0.0, 0.0, 0.019), 72.0
        ),
        "rfid_back": add_camera(
            "RFID back macro camera", (0.0, -0.15, -0.019), (0.0, 0.0, -0.019), 72.0
        ),
    }
    render_state = configure_scene(cfg, resolution, samples, force_cpu)
    return scene, front_root, back_root, cameras, render_state


def set_root_visibility(root, visible: bool) -> None:
    root.hide_render = not visible
    for child in root.children_recursive:
        child.hide_render = not visible


def main() -> int:
    args = parse_args()
    cfg = ebis.load_config(args.config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene, front_root, back_root, cameras, render_state = build_macro_scene(
        cfg, args.resolution, args.samples, args.cpu
    )

    started = time.perf_counter()
    images = {}
    view_visibility = {
        "rfid_front_back": (True, True),
        "rfid_front": (True, False),
        "rfid_back": (False, True),
    }
    for view_name, camera in cameras.items():
        show_front, show_back = view_visibility[view_name]
        set_root_visibility(front_root, show_front)
        set_root_visibility(back_root, show_back)
        scene.camera = camera
        image_path = output / f"{view_name}.png"
        scene.render.filepath = str(image_path)
        bpy.ops.render.render(write_still=True)
        if not image_path.is_file() or image_path.stat().st_size < 20_000:
            raise RuntimeError(f"RFID macro render is missing or too small: {image_path}")
        images[view_name] = {
            "path": image_path.name,
            "sha256": ebis.sha256_file(image_path),
            "bytes": image_path.stat().st_size,
        }

    set_root_visibility(front_root, True)
    set_root_visibility(back_root, True)
    scene.camera = cameras["rfid_front_back"]
    blend_path = output / "ebis_rfid_front_back_reference.blend"
    bpy.context.preferences.filepaths.use_file_compression = True
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    manifest = {
        "schema_version": 1,
        "asset": "EBIS visual RFID tag",
        "scope": "visual appearance only; no RF, UID or read-range simulation",
        "physical_size_m": cfg["rfid_tag"]["size_m"],
        "front_srgb": cfg["rfid_tag"]["front_srgb"],
        "back_srgb": cfg["rfid_tag"]["back_srgb"],
        "center_dome_diameter_m": cfg["rfid_tag"]["center_dome_diameter_m"],
        "reference": "ebis.odt embedded front/back tag photographs",
        "generator_script_sha256": ebis.SCRIPT_SHA256,
        "config_sha256": ebis.config_sha256(cfg),
        "blender_version": bpy.app.version_string,
        "render": render_state | {"elapsed_seconds": time.perf_counter() - started},
        "view_order": {"combined_top": "front", "combined_bottom": "back"},
        "images": images,
        "blend": {
            "path": blend_path.name,
            "sha256": ebis.sha256_file(blend_path),
            "bytes": blend_path.stat().st_size,
        },
    }
    ebis.write_json_atomic(output / "manifest.json", manifest)
    print(f"EBIS_RFID_HERO_OK {output}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"EBIS_RFID_HERO_ERROR {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
