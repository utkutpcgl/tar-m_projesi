#!/usr/bin/env python3
"""Render deterministic side and oblique morphology previews inside Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def arguments() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-pack", required=True)
    parser.add_argument("--output-prefix", required=True)
    return parser.parse_args(values)


def look_at(obj: bpy.types.Object, point: tuple[float, float, float]) -> None:
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_ground() -> None:
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(1.8, 0.0, -0.006))
    ground = bpy.context.object
    ground.name = "neutral_preview_ground"
    material = bpy.data.materials.new("neutral_preview_ground")
    material.diffuse_color = (0.12, 0.10, 0.075, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.12, 0.10, 0.075, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    ground.data.materials.append(material)


def add_label(text: str, x: float) -> None:
    bpy.ops.object.text_add(location=(x, -0.26, 0.03), rotation=(math.pi / 2, 0.0, 0.0))
    label = bpy.context.object
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.size = 0.13
    label.data.extrude = 0.002
    material = bpy.data.materials.new(f"label_{text}")
    material.diffuse_color = (0.92, 0.92, 0.92, 1.0)
    label.data.materials.append(material)


def main() -> None:
    args = arguments()
    pack_root = Path(args.asset_pack).expanduser().resolve()
    output_prefix = Path(args.output_prefix).expanduser().resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    plant_root = pack_root / "xdg/cropcraft/plants/rice_reproductive_v9"
    selected = (
        ("heading", "rice_reproductive_v9_heading_v01_heading_green.obj"),
        ("flowering", "rice_reproductive_v9_flowering_v02_grain_fill_transition.obj"),
        ("grain fill", "rice_reproductive_v9_grain_fill_v03_mature_senescent.obj"),
        ("mature", "rice_reproductive_v9_mature_v04_mature_senescent.obj"),
    )
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    imported: list[dict[str, str]] = []
    for index, (stage, filename) in enumerate(selected):
        path = plant_root / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        before = set(bpy.context.scene.objects)
        bpy.ops.wm.obj_import(
            filepath=str(path), up_axis="Z", forward_axis="Y", use_split_objects=False
        )
        objects = [obj for obj in set(bpy.context.scene.objects) - before if obj.type == "MESH"]
        if len(objects) != 1:
            raise RuntimeError(f"Expected one imported mesh for {path}, got {len(objects)}")
        obj = objects[0]
        obj.location.x = index * 1.2
        obj.rotation_euler[2] = math.radians((17, -11, 23, -19)[index])
        add_label(stage, index * 1.2)
        imported.append({"stage": stage, "path": str(path), "sha256": sha256(path)})

    add_ground()
    bpy.ops.object.light_add(type="AREA", location=(1.5, -2.2, 4.2))
    key = bpy.context.object
    key.data.energy = 950.0
    key.data.shape = "DISK"
    key.data.size = 4.0
    look_at(key, (1.8, 0.0, 0.5))
    bpy.ops.object.light_add(type="AREA", location=(-2.0, 1.8, 2.2))
    fill = bpy.context.object
    fill.data.energy = 500.0
    fill.data.size = 3.0
    look_at(fill, (1.8, 0.0, 0.55))
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 4.0))
    bpy.context.object.data.energy = 1.4
    bpy.context.object.rotation_euler = (math.radians(28), math.radians(-18), math.radians(24))

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.lens = 58.0
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.world.color = (0.025, 0.025, 0.025)
    scene.view_settings.look = "AgX - Medium High Contrast"

    outputs: list[dict[str, str]] = []
    for name, location, target in (
        ("side", (1.8, -5.8, 1.35), (1.8, 0.0, 0.48)),
        ("oblique", (4.9, -5.5, 3.25), (1.8, 0.0, 0.48)),
    ):
        camera.location = location
        look_at(camera, target)
        output = output_prefix.with_name(output_prefix.name + f"_{name}.png")
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append({"view": name, "path": str(output), "sha256": sha256(output)})

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "asset_pack": str(pack_root),
        "pack_manifest_sha256": sha256(pack_root / "PACK.json"),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "models": imported,
        "outputs": outputs,
        "render_engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "purpose": "manual morphology review only; not training data",
    }
    receipt_path = output_prefix.with_suffix(".json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
