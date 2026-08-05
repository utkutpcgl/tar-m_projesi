#!/usr/bin/env python3
"""Refine soybean v5 leaf shape and colour while preserving R1 provenance.

R1 remains immutable. This script rebuilds only procedural plant geometry and
maps, then copies the already verified official Poly Haven Bermuda variants
byte-for-byte from R1. Soil, HDRI, debris, downloads and licenses are unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import build_cropcraft_soy_assets_v5 as v1
from build_cropcraft_agri_assets import Mesh, canonical_sha256, sha256, tree_inventory, write_description
from enhance_cropcraft_assets_v3 import geometry_sha256, obj_stats, validate_base_pack


PACK_ID = "cropcraft_soy_robust_v5_r2"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def refined_leaf_maps(
    family: str,
    phenotype: str,
    output_directory: Path,
    seed: int,
) -> dict[str, Any]:
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size]
    rng = np.random.default_rng(seed)
    palettes = {
        "healthy_dark": np.array([36.0, 105.0, 36.0]),
        "healthy_light": np.array([62.0, 137.0, 50.0]),
        "field_stress": np.array([76.0, 132.0, 49.0]),
        "amaranthus_green": np.array([49.0, 119.0, 45.0]),
        "amaranthus_reddish": np.array([66.0, 109.0, 43.0]),
        "cynodon_green": np.array([65.0, 130.0, 44.0]),
        "cynodon_dry": np.array([103.0, 132.0, 50.0]),
    }
    base = palettes[phenotype]
    coarse = (
        0.50 * np.sin(xx / 41.0 + yy / 89.0)
        + 0.29 * np.sin(xx / 131.0 - yy / 61.0)
        + 0.16 * np.sin(yy / 19.0)
    )
    modulation = 1.0 + 0.043 * coarse + 0.012 * rng.normal(
        0.0, 1.0, size=(size, size)
    )
    rgb = base[None, None, :] * modulation[:, :, None]
    midrib_width = 6.0 if family == v1.CYNODON_TYPE else 9.0
    midrib = np.exp(-((xx - size / 2.0) / midrib_width) ** 2)
    lateral = np.zeros((size, size), dtype=np.float64)
    if family != v1.CYNODON_TYPE:
        for offset in range(-420, 421, 82):
            distance = np.abs((yy - size / 2.0) - offset)
            left = np.exp(-((xx - size / 2.0 + 0.72 * distance) / 5.5) ** 2)
            right = np.exp(-((xx - size / 2.0 - 0.72 * distance) / 5.5) ** 2)
            lateral = np.maximum(lateral, np.maximum(left, right))
    vein = np.clip(midrib + 0.30 * lateral, 0.0, 1.0)
    rgb += vein[:, :, None] * np.array([13.0, 21.0, 7.0])
    if phenotype == "field_stress":
        patch = np.zeros((size, size), dtype=np.float64)
        for _ in range(10):
            cx, cy = rng.uniform(0, size, size=2)
            rx, ry = rng.uniform(35, 150, size=2)
            patch += np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2))
        patch = np.clip(patch, 0.0, 1.0)
        rgb[:, :, 0] += 17.0 * patch
        rgb[:, :, 1] -= 5.0 * patch
    elif phenotype == "cynodon_dry":
        variation = 0.5 + 0.5 * np.sin(xx / 57.0 + yy / 103.0)
        rgb[:, :, 0] += 14.0 * variation
        rgb[:, :, 1] -= 5.0 * variation
    elif phenotype == "amaranthus_reddish":
        edge = np.clip(np.abs(xx - size / 2.0) / (size / 2.0), 0.0, 1.0)
        rgb[:, :, 0] += 18.0 * edge
        rgb[:, :, 1] -= 9.0 * edge
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    height = 0.5 + 0.13 * np.sin(xx / 25.0) + 0.06 * np.sin(
        yy / 49.0 + xx / 113.0
    ) + 0.15 * vein
    gy, gx = np.gradient(height)
    normal = np.dstack((-2.0 * gx, -2.0 * gy, np.ones_like(gx)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
    normal_rgb = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)

    output_directory.mkdir(parents=True, exist_ok=True)
    stem = f"{family}_{phenotype}_v5_r2"
    albedo = output_directory / f"{stem}_albedo.png"
    normal_path = output_directory / f"{stem}_normal_gl.png"
    Image.fromarray(rgb).save(albedo, optimize=True)
    Image.fromarray(normal_rgb).save(normal_path, optimize=True)
    return {
        "family": family,
        "phenotype": phenotype,
        "dimensions": [size, size],
        "albedo": albedo.name,
        "albedo_sha256": sha256(albedo),
        "normal_gl": normal_path.name,
        "normal_gl_sha256": sha256(normal_path),
    }


def add_pointed_leaf(
    mesh: Mesh,
    base: tuple[float, float, float],
    blade_length: float,
    azimuth: float,
    elevation: float,
    half_width: float,
    arch: float,
    droop: float,
    twist: float,
    fold: float,
    leaf_material: str,
    midrib_material: str,
    segments: int,
    rounded: bool,
) -> None:
    across = (-1.0, -0.32, 0.0, 0.32, 1.0)
    rows: list[list[int]] = []
    for step in range(segments + 1):
        t = step / segments
        theta = azimuth + twist * (t - 0.5)
        planar = blade_length * math.cos(elevation) * t
        center = (
            base[0] + planar * math.cos(theta),
            base[1] + planar * math.sin(theta),
            base[2]
            + blade_length
            * (
                math.sin(elevation) * t
                + arch * math.sin(math.pi * t)
                - droop * t * t
            ),
        )
        cross_axis = (-math.sin(theta), math.cos(theta), 0.0)
        if rounded:
            profile = max(0.10, math.sin(math.pi * t)) ** 0.58
        else:
            profile = 0.025 if step in {0, segments} else math.sin(math.pi * t) ** 0.55
            profile *= 0.92 + 0.08 * t
        width = half_width * profile
        row: list[int] = []
        for across_position in across:
            lateral = tuple(value * across_position * width for value in cross_axis)
            crease = -fold * abs(across_position) * width
            row.append(
                mesh.vertex(
                    (
                        center[0] + lateral[0],
                        center[1] + lateral[1],
                        center[2] + crease,
                    )
                )
            )
        rows.append(row)
    for step in range(segments):
        for strip in range(len(across) - 1):
            material = midrib_material if strip in (1, 2) else leaf_material
            mesh.face(
                (
                    rows[step][strip],
                    rows[step + 1][strip],
                    rows[step + 1][strip + 1],
                    rows[step][strip + 1],
                ),
                material,
            )


def refined_add_leaflet(
    mesh: Mesh,
    base: tuple[float, float, float],
    blade_length: float,
    azimuth: float,
    elevation: float,
    rng: Any,
    leaf_material: str,
    midrib_material: str,
    width_ratio: float = 0.29,
    segments: int = 48,
) -> None:
    add_pointed_leaf(
        mesh,
        base,
        blade_length,
        azimuth,
        elevation,
        blade_length * width_ratio,
        rng.uniform(0.025, 0.075),
        rng.uniform(0.0, 0.030),
        rng.uniform(-0.12, 0.12),
        rng.uniform(0.055, 0.12),
        leaf_material,
        midrib_material,
        segments,
        rounded=width_ratio >= 0.35,
    )


def build_refined_botanical_assets(root: Path) -> dict[str, Any]:
    original_leaf_maps = v1.leaf_maps
    original_add_leaflet = v1.add_leaflet
    original_soybean_mesh = v1.soybean_mesh

    def refined_soybean_mesh(seed: int, height: float, stage: int):
        mesh, materials, traits = original_soybean_mesh(seed, height, stage)
        for name in list(materials):
            if "petiole" in name:
                materials[name] = ((0.14, 0.39, 0.13), 0.54)
            elif "stem" in name:
                materials[name] = ((0.13, 0.35, 0.12), 0.56)
        return mesh, materials, traits

    v1.leaf_maps = refined_leaf_maps
    v1.add_leaflet = refined_add_leaflet
    v1.soybean_mesh = refined_soybean_mesh
    try:
        return v1.build_procedural_botanical_assets(root)
    finally:
        v1.leaf_maps = original_leaf_maps
        v1.add_leaflet = original_add_leaflet
        v1.soybean_mesh = original_soybean_mesh


def copy_reference_models(
    base_root: Path,
    root: Path,
    base_pack: dict[str, Any],
    botanical: dict[str, Any],
) -> list[dict[str, Any]]:
    source_directory = base_root / "xdg/cropcraft/plants" / v1.CYNODON_TYPE
    destination = root / "xdg/cropcraft/plants" / v1.CYNODON_TYPE
    output_rows: list[dict[str, Any]] = []
    for original in base_pack["soy_v5_assets"]["texture_backed_reference_models"]:
        row = deepcopy(original)
        obj_name = str(row["filename"])
        mtl_name = str(row["mtl_filename"])
        shutil.copy2(source_directory / obj_name, destination / obj_name)
        shutil.copy2(source_directory / mtl_name, destination / mtl_name)
        for line in (destination / mtl_name).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if line.startswith("map_Kd ") or line.startswith("map_Bump "):
                texture_name = line.split()[-1]
                target = destination / texture_name
                if not target.exists():
                    shutil.copy2(source_directory / texture_name, target)
        stats = obj_stats(destination / obj_name)
        row.update(stats)
        row["geometry_sha256"] = geometry_sha256(destination / obj_name)
        row["obj_sha256"] = sha256(destination / obj_name)
        row["mtl_sha256"] = sha256(destination / mtl_name)
        output_rows.append(row)
    botanical["weeds"][v1.CYNODON_TYPE]["models"].extend(output_rows)
    write_description(
        destination,
        botanical["weeds"][v1.CYNODON_TYPE]["models"],
    )
    return output_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-pack", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_root = Path(args.base_pack).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    base_pack = validate_base_pack(base_root)
    if base_pack.get("pack_id") != "cropcraft_soy_robust_v5_r1":
        raise ValueError("R2 refinement requires the frozen soybean v5 R1 pack")
    free_bytes = shutil.disk_usage(destination.parent).free
    base_bytes = int(base_pack["inventory_bytes"])
    required_free = 2 * base_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-soy-v5-r2-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_V5_R1.json")
        botanical = build_refined_botanical_assets(root)
        reference_rows = copy_reference_models(base_root, root, base_pack, botanical)

        generated = {
            "crop": botanical["crop"],
            "weeds": botanical["weeds"],
            "background_debris": deepcopy(
                base_pack["generated_assets"]["background_debris"]
            ),
        }
        final_rows = [
            row for row in botanical["crop"]["models"] if int(row["growth_stage"]) == 5
        ]
        soy_assets = deepcopy(base_pack["soy_v5_assets"])
        soy_assets.update(
            {
                "crop_albedo_phenotypes": list(v1.CROP_PHENOTYPES),
                "unique_crop_geometries": len(
                    botanical["crop"]["unique_geometry_sha256"]
                ),
                "stage_trait_contract": {
                    "cotyledon_stage_present": any(
                        int(row["stage_traits"]["cotyledon_pairs"]) >= 1
                        for row in botanical["crop"]["models"]
                    ),
                    "unifoliolate_stage_present": any(
                        int(row["stage_traits"]["unifoliolate_pairs"]) >= 1
                        for row in botanical["crop"]["models"]
                    ),
                    "minimum_final_stage_trifoliolate_nodes": min(
                        int(row["stage_traits"]["trifoliolate_nodes"])
                        for row in final_rows
                    ),
                },
                "texture_backed_reference_models": reference_rows,
                "refinement": {
                    "revision": "r2",
                    "changes": [
                        "pointed asymmetric ovate soybean and Amaranthus leaves",
                        "greener patch-localized chlorosis phenotype",
                        "darker soybean stem and petiole material",
                    ],
                    "unchanged": [
                        "all 20 soybean morphology seeds and stage topology",
                        "official Bermuda reference OBJ/MTL/texture bytes",
                        "soil PBR, HDRI, debris, licenses and downloads",
                    ],
                },
            }
        )
        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "manual-visual soybean botanical refinement",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "refiner_script": str(Path(__file__).resolve()),
            "refiner_script_sha256": sha256(__file__),
            "base_builder": {
                "path": base_pack["builder_script"],
                "sha256": base_pack["builder_script_sha256"],
            },
            "helper_scripts": deepcopy(base_pack["helper_scripts"]),
            "mesh_provenance": (
                "R2 deterministic pointed-leaf procedural refinement; R1 official "
                "Poly Haven Bermuda reference variants copied byte-for-byte"
            ),
            "generated_geometry_license": "CC0-1.0",
            "third_party_source": base_pack["third_party_source"],
            "third_party_license": base_pack["third_party_license"],
            "third_party_license_url": base_pack["third_party_license_url"],
            "api_user_agent": base_pack["api_user_agent"],
            "capacity_check": {
                "base_inventory_bytes": base_bytes,
                "advertised_download_bytes": 0,
                "free_bytes_before_build": free_bytes,
                "required_free_bytes": required_free,
                "passed": True,
            },
            "sources": deepcopy(base_pack["sources"]),
            "downloads": deepcopy(base_pack["downloads"]),
            "generated_assets": generated,
            "soy_v5_assets": soy_assets,
            "grounds": deepcopy(base_pack["grounds"]),
            "environments": deepcopy(base_pack["environments"]),
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(int(row["size_bytes"]) for row in inventory),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        root.replace(destination)

    print(
        json.dumps(
            {
                "output": str(destination),
                "pack_id": PACK_ID,
                "pack_sha256": sha256(destination / "PACK.json"),
                "free_bytes_before_build": free_bytes,
                "inventory_bytes": json.loads(
                    (destination / "PACK.json").read_text(encoding="utf-8")
                )["inventory_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
