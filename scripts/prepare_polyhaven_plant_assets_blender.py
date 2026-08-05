#!/usr/bin/env python3
"""Normalize Poly Haven GLTF plant variants into CropCraft OBJ assets.

This file is executed by Blender, not by the project virtual environment.  It
keeps the imported PBR material references, applies world transforms, centers
each logical variant at the origin, and scales it to a declared early-weed
height.  The caller supplies a JSON spec after Blender's ``--`` separator.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import bpy


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def mesh_objects() -> list[bpy.types.Object]:
    return sorted(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.type == "MESH" and obj.data and len(obj.data.polygons) > 0
        ),
        key=lambda obj: obj.name,
    )


def lineage(obj: bpy.types.Object) -> list[bpy.types.Object]:
    result = [obj]
    while result[-1].parent is not None:
        result.append(result[-1].parent)
    result.reverse()
    return result


def logical_groups(objects: list[bpy.types.Object]) -> list[list[bpy.types.Object]]:
    """Use the GLTF hierarchy when it exposes several authored variants.

    Poly Haven plant assets normally contain one node per photographed model
    under a common root.  If the hierarchy is flat, each mesh is treated as a
    variant.  Groups with no geometry are ignored.
    """

    if len(objects) == 1:
        return [objects]
    chains = [lineage(obj) for obj in objects]
    top_roots = {chain[0].name for chain in chains}
    keys: list[str]
    if len(top_roots) > 1:
        keys = [chain[0].name for chain in chains]
    else:
        second_level = {
            chain[1].name if len(chain) > 1 else chain[0].name for chain in chains
        }
        if len(second_level) > 1:
            keys = [
                chain[1].name if len(chain) > 1 else chain[0].name
                for chain in chains
            ]
        else:
            keys = [obj.name for obj in objects]
    grouped: dict[str, list[bpy.types.Object]] = {}
    for key, obj in zip(keys, objects, strict=True):
        grouped.setdefault(key, []).append(obj)
    return [grouped[key] for key in sorted(grouped)]


def duplicate_and_join(objects: list[bpy.types.Object], name: str) -> bpy.types.Object:
    duplicates: list[bpy.types.Object] = []
    for source in objects:
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        duplicate.matrix_world = source.matrix_world.copy()
        duplicate.parent = None
        bpy.context.collection.objects.link(duplicate)
        duplicates.append(duplicate)
    bpy.ops.object.select_all(action="DESELECT")
    for duplicate in duplicates:
        duplicate.select_set(True)
    active = duplicates[0]
    bpy.context.view_layer.objects.active = active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(duplicates) > 1:
        bpy.ops.object.join()
        active = bpy.context.view_layer.objects.active
    active.name = name
    return active


def normalize_height(obj: bpy.types.Object, target_height: float) -> dict[str, Any]:
    vertices = obj.data.vertices
    xs = [vertex.co.x for vertex in vertices]
    ys = [vertex.co.y for vertex in vertices]
    zs = [vertex.co.z for vertex in vertices]
    current_height = max(zs) - min(zs)
    if not math.isfinite(current_height) or current_height <= 1e-8:
        raise ValueError(f"Degenerate source height for {obj.name}: {current_height}")
    center_x = (min(xs) + max(xs)) / 2.0
    center_y = (min(ys) + max(ys)) / 2.0
    minimum_z = min(zs)
    scale = target_height / current_height
    for vertex in vertices:
        vertex.co.x = (vertex.co.x - center_x) * scale
        vertex.co.y = (vertex.co.y - center_y) * scale
        vertex.co.z = (vertex.co.z - minimum_z) * scale
    obj.data.update()
    xs = [vertex.co.x for vertex in vertices]
    ys = [vertex.co.y for vertex in vertices]
    zs = [vertex.co.z for vertex in vertices]
    width = max(max(xs) - min(xs), max(ys) - min(ys))
    surface_area = sum(float(polygon.area) for polygon in obj.data.polygons)
    return {
        "height_m": max(zs) - min(zs),
        "width_m": width,
        "surface_area_m2": surface_area,
        "source_height_units": current_height,
        "scale_factor": scale,
    }


def export_obj(obj: bpy.types.Object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.obj_export(
        filepath=str(path),
        export_selected_objects=True,
        apply_modifiers=True,
        export_uv=True,
        export_normals=True,
        export_colors=False,
        export_materials=True,
        export_pbr_extensions=True,
        path_mode="COPY",
        forward_axis="Y",
        up_axis="Z",
    )


def convert_asset(spec: dict[str, Any]) -> dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = Path(spec["input_gltf"]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects = mesh_objects()
    if not objects:
        raise RuntimeError(f"No mesh objects imported from {source}")
    groups = logical_groups(objects)
    target_heights = [float(value) for value in spec["target_heights_m"]]
    if not target_heights or any(value <= 0 for value in target_heights):
        raise ValueError("target_heights_m must contain positive values")
    output_root = Path(spec["output_directory"]).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    source_rows = []
    for obj in objects:
        source_rows.append(
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "faces": len(obj.data.polygons),
                "lineage": [node.name for node in lineage(obj)],
            }
        )
    for index, group in enumerate(groups):
        target_height = target_heights[index % len(target_heights)]
        asset_name = f"ph_{safe_name(str(spec['asset_id']))}_{index + 1:02d}"
        obj = duplicate_and_join(group, asset_name)
        dimensions = normalize_height(obj, target_height)
        if dimensions["width_m"] / dimensions["height_m"] > float(
            spec.get("maximum_width_height_ratio", 4.5)
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        output_path = output_root / f"{asset_name}.obj"
        export_obj(obj, output_path)
        mtl_path = output_path.with_suffix(".mtl")
        rows.append(
            {
                "filename": output_path.name,
                "mtl_filename": mtl_path.name,
                "source_asset_id": spec["asset_id"],
                "target_family": spec["target_family"],
                "source_group": [source.name for source in group],
                "vertices": len(obj.data.vertices),
                "faces": len(obj.data.polygons),
                "materials": sorted(
                    material.name for material in obj.data.materials if material
                ),
                "obj_sha256": sha256(output_path),
                "mtl_sha256": sha256(mtl_path),
                **dimensions,
            }
        )
        bpy.data.objects.remove(obj, do_unlink=True)
    if not rows:
        raise RuntimeError(f"No usable logical variants exported from {source}")
    return {
        "asset_id": spec["asset_id"],
        "target_family": spec["target_family"],
        "input_gltf": str(source),
        "input_gltf_sha256": sha256(source),
        "imported_objects": source_rows,
        "logical_group_count": len(groups),
        "exported_models": rows,
    }


def main() -> None:
    try:
        separator = sys.argv.index("--")
    except ValueError as error:
        raise SystemExit("Expected JSON spec path after Blender --") from error
    arguments = sys.argv[separator + 1 :]
    if len(arguments) != 1:
        raise SystemExit("Expected exactly one JSON spec path")
    spec_path = Path(arguments[0]).resolve()
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    reports = [convert_asset(row) for row in payload["assets"]]
    output = Path(payload["output_report"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "blender_version": bpy.app.version_string,
                "assets": reports,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
