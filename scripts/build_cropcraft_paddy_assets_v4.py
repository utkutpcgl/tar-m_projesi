#!/usr/bin/env python3
"""Build a provenance-locked early-rice paddy CropCraft asset pack.

The botanical meshes and leaf maps are deterministic in-project procedural
assets released as CC0-1.0. Wet-soil PBR maps and environment HDRIs come only
from the official Poly Haven API and are verified against advertised MD5 and
byte counts. No downloaded model is represented as a measured rice scan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from build_cropcraft_agri_assets import (
    API_ROOT,
    LICENSE_URL,
    Mesh,
    USER_AGENT as POLY_HAVEN_USER_AGENT,
    canonical_sha256,
    download_file,
    sha256,
    tree_inventory,
    url_json,
    write_description,
    write_mesh,
)
from enhance_cropcraft_assets_v3 import geometry_sha256, obj_stats, validate_base_pack


PACK_ID = "cropcraft_paddy_robust_v4_r1"
USER_AGENT = POLY_HAVEN_USER_AGENT
WET_GROUND_IDS = ("aerial_mud_1", "brown_mud_03", "muddy_tracks")
PADDY_ENVIRONMENT_IDS = ("pond", "mud_road_puresky", "cloudy_vondelpark")
CROP_TYPE = "rice_seedling_v4"
CROP_SPECIES = "Oryza sativa"
CROP_PHENOTYPES = ("healthy_dark", "healthy_light", "nitrogen_stress")
WEED_TYPES = (
    "sagittaria_trifolia_v4",
    "paddy_grass_weed_v4",
    "aquatic_broadleaf_v4",
)


def nested_file(
    files: dict[str, Any], role: str, resolution: str, extension: str
) -> dict[str, Any]:
    value = files[role][resolution][extension]
    if not isinstance(value, dict) or not {"url", "size", "md5"} <= set(value):
        raise ValueError(f"Incomplete Poly Haven metadata: {role}/{resolution}/{extension}")
    return value


def selected_downloads(files_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ground_roles = {
        "diff.jpg": ("Diffuse", "jpg", "diffuse"),
        "rough.jpg": ("Rough", "jpg", "roughness"),
        "nor_gl.exr": ("nor_gl", "exr", "normal_gl"),
        "disp.png": ("Displacement", "png", "displacement"),
    }
    for asset_id in WET_GROUND_IDS:
        for output_name, (api_role, extension, role) in ground_roles.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "kind": "wet_ground_pbr",
                    "role": role,
                    "output_name": output_name,
                    "metadata": nested_file(
                        files_by_id[asset_id], api_role, "2k", extension
                    ),
                }
            )
    for asset_id in PADDY_ENVIRONMENT_IDS:
        rows.append(
            {
                "asset_id": asset_id,
                "kind": "paddy_environment_hdri",
                "role": "environment_hdr",
                "output_name": f"{asset_id}_2k.hdr",
                "metadata": nested_file(
                    files_by_id[asset_id], "hdri", "2k", "hdr"
                ),
            }
        )
    return rows


def leaf_maps(
    family: str,
    phenotype: str,
    output_directory: Path,
    seed: int,
) -> dict[str, Any]:
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size]
    rng = np.random.default_rng(seed)
    palette = {
        "healthy_dark": np.array([39.0, 112.0, 34.0]),
        "healthy_light": np.array([66.0, 145.0, 48.0]),
        "nitrogen_stress": np.array([105.0, 133.0, 38.0]),
        "sagittaria": np.array([47.0, 126.0, 57.0]),
        "paddy_grass": np.array([76.0, 139.0, 43.0]),
        "aquatic_broadleaf": np.array([40.0, 118.0, 69.0]),
    }
    base = palette[phenotype]
    longitudinal = 0.58 * np.sin(xx / 18.0) + 0.26 * np.sin(xx / 63.0)
    transverse = 0.12 * np.sin(yy / 31.0 + xx / 97.0)
    mottling = rng.normal(0.0, 1.0, size=(size, size))
    modulation = 1.0 + 0.045 * longitudinal + 0.025 * transverse + 0.012 * mottling
    rgb = base[None, None, :] * modulation[:, :, None]
    midrib = np.exp(-((xx - size / 2.0) / 9.0) ** 2)
    rgb += midrib[:, :, None] * np.array([17.0, 28.0, 9.0])
    if phenotype == "nitrogen_stress":
        stripe = 0.5 + 0.5 * np.sin(xx / 42.0 + yy / 85.0)
        rgb[:, :, 0] += 24.0 * stripe
        rgb[:, :, 1] -= 12.0 * stripe
    if family == "sagittaria_trifolia_v4":
        veins = np.maximum(
            np.exp(-((xx - (0.5 * size + 0.28 * (yy - size / 2))) / 7.0) ** 2),
            np.exp(-((xx - (0.5 * size - 0.28 * (yy - size / 2))) / 7.0) ** 2),
        )
        rgb += veins[:, :, None] * np.array([10.0, 17.0, 7.0])
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    height = (
        0.5
        + 0.16 * np.sin(xx / 18.0)
        + 0.08 * np.sin(xx / 63.0)
        + 0.14 * midrib
    )
    gy, gx = np.gradient(height)
    strength = 2.2
    normal = np.dstack((-gx * strength, -gy * strength, np.ones_like(gx)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
    normal_rgb = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)

    output_directory.mkdir(parents=True, exist_ok=True)
    stem = f"{family}_{phenotype}_v4"
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


def add_uv_and_maps(
    obj_path: Path,
    mtl_path: Path,
    albedo_name: str,
    normal_name: str,
    roughness: float,
) -> None:
    vertices: list[tuple[float, float, float]] = []
    source_lines = obj_path.read_text(encoding="utf-8").splitlines()
    for line in source_lines:
        if line.startswith("v "):
            values = line.split()
            vertices.append(tuple(float(value) for value in values[1:4]))
    minimum_z = min(vertex[2] for vertex in vertices)
    height = max(vertex[2] for vertex in vertices) - minimum_z
    uv_rows = []
    for x, y, z in vertices:
        u = (math.atan2(y, x) + math.pi) / math.tau
        v = 0.0 if height <= 0 else (z - minimum_z) / height
        uv_rows.append(f"vt {u:.9f} {v:.9f}")
    output: list[str] = []
    inserted = False
    for line in source_lines:
        if not line.startswith("v ") and not inserted and vertices:
            output.extend(uv_rows)
            inserted = True
        if line.startswith("f "):
            fields = [token.split("/")[0] for token in line.split()[1:]]
            output.append("f " + " ".join(f"{value}/{value}" for value in fields))
        else:
            output.append(line)
    if not inserted:
        output.extend(uv_rows)
    obj_path.write_text("\n".join(output) + "\n", encoding="utf-8")

    sections: list[list[str]] = []
    current: list[str] = []
    for line in mtl_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("newmtl ") and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    rewritten_sections: list[str] = []
    for section in sections:
        header = next((line for line in section if line.startswith("newmtl ")), "")
        material_name = header.split(maxsplit=1)[1] if header else ""
        mapped = "leaf" in material_name or "midrib" in material_name
        rewritten: list[str] = []
        for line in section:
            if mapped and line.startswith("Kd "):
                rewritten.append("Kd 1.000000 1.000000 1.000000")
            elif mapped and line.startswith("Pr "):
                rewritten.append(f"Pr {roughness:.6f}")
            else:
                rewritten.append(line)
        if mapped:
            rewritten.append(f"map_Kd {albedo_name}")
            rewritten.append(f"map_Bump -bm 0.180000 {normal_name}")
        rewritten_sections.append("\n".join(rewritten))
    mtl_path.write_text("\n\n".join(rewritten_sections) + "\n", encoding="utf-8")


def rice_mesh(seed: int, target_height: float, stage: int) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    tillers = 1 + min(3, stage // 2) + (seed % 2)
    blades_per_tiller = 3 + stage + (seed % 2)
    for tiller in range(tillers):
        azimuth = math.tau * tiller / tillers + rng.uniform(-0.24, 0.24)
        radial = target_height * rng.uniform(0.006, 0.022) * tiller
        base = (radial * math.cos(azimuth), radial * math.sin(azimuth), 0.0)
        stem_height = target_height * rng.uniform(0.28, 0.42)
        top = (
            base[0] + target_height * rng.uniform(-0.025, 0.025),
            base[1] + target_height * rng.uniform(-0.025, 0.025),
            stem_height,
        )
        mesh.add_tube(
            base,
            top,
            target_height * 0.010,
            target_height * 0.006,
            10,
            stem_material,
        )
        for blade in range(blades_per_tiller):
            maturity = (blade + 1) / blades_per_tiller
            blade_length = target_height * rng.uniform(0.72, 1.10) * (
                1.03 - 0.13 * maturity
            )
            mesh.add_blade(
                (
                    base[0],
                    base[1],
                    stem_height * (0.12 + 0.72 * maturity),
                ),
                blade_length,
                azimuth
                + blade * math.radians(137.5)
                + rng.uniform(-0.18, 0.18),
                math.radians(rng.uniform(52.0, 79.0)),
                blade_length * rng.uniform(0.018, 0.033),
                rng.uniform(0.04, 0.13),
                rng.uniform(0.005, 0.055),
                rng.uniform(-0.20, 0.20),
                rng.uniform(0.20, 0.34),
                leaf_material,
                midrib_material,
                segments=40,
                profile_power=0.78,
            )
    mesh.scale_to_height(target_height)
    green = rng.uniform(0.38, 0.52)
    materials = {
        leaf_material: ((green * 0.34, green, green * 0.25), 0.38),
        midrib_material: ((green * 0.56, min(0.75, green * 1.20), green * 0.36), 0.34),
        stem_material: ((green * 0.54, green * 0.92, green * 0.30), 0.42),
    }
    return mesh, materials


def add_sagittate_leaf(
    mesh: Mesh,
    base: tuple[float, float, float],
    length: float,
    azimuth: float,
    elevation: float,
    material: str,
) -> None:
    forward = np.array(
        [math.cos(azimuth) * math.cos(elevation), math.sin(azimuth) * math.cos(elevation), math.sin(elevation)],
        dtype=np.float64,
    )
    across = np.array([-math.sin(azimuth), math.cos(azimuth), 0.0], dtype=np.float64)
    origin = np.asarray(base, dtype=np.float64)
    outline = (
        (1.00, 0.00),
        (0.70, 0.22),
        (0.35, 0.34),
        (0.05, 0.18),
        (0.30, 0.00),
        (0.05, -0.18),
        (0.35, -0.34),
        (0.70, -0.22),
    )
    center = mesh.vertex(tuple(origin + forward * length * 0.43))
    vertices = [
        mesh.vertex(tuple(origin + forward * length * x + across * length * y))
        for x, y in outline
    ]
    for index in range(len(vertices)):
        nxt = (index + 1) % len(vertices)
        mesh.face((center, vertices[index], vertices[nxt]), material)


def sagittaria_mesh(seed: int, target_height: float) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    stem = f"sagittaria_{seed}_stem"
    leaf = f"sagittaria_{seed}_leaf"
    midrib = f"sagittaria_{seed}_midrib"
    leaf_count = rng.randint(5, 8)
    phase = rng.uniform(0.0, math.tau)
    for index in range(leaf_count):
        azimuth = phase + index * math.tau / leaf_count + rng.uniform(-0.18, 0.18)
        petiole_height = target_height * rng.uniform(0.48, 0.76)
        end = (
            target_height * rng.uniform(0.05, 0.16) * math.cos(azimuth),
            target_height * rng.uniform(0.05, 0.16) * math.sin(azimuth),
            petiole_height,
        )
        mesh.add_tube(
            (0.0, 0.0, 0.0),
            end,
            target_height * 0.014,
            target_height * 0.009,
            9,
            stem,
        )
        leaf_length = target_height * rng.uniform(0.42, 0.68)
        elevation = math.radians(rng.uniform(10.0, 32.0))
        add_sagittate_leaf(mesh, end, leaf_length, azimuth, elevation, leaf)
        tip = (
            end[0] + leaf_length * math.cos(azimuth) * math.cos(elevation),
            end[1] + leaf_length * math.sin(azimuth) * math.cos(elevation),
            end[2] + leaf_length * math.sin(elevation),
        )
        mesh.add_tube(end, tip, target_height * 0.006, target_height * 0.002, 6, midrib)
    mesh.scale_to_height(target_height)
    materials = {
        leaf: ((0.13, 0.48, 0.18), 0.34),
        midrib: ((0.31, 0.62, 0.25), 0.32),
        stem: ((0.24, 0.54, 0.22), 0.38),
    }
    return mesh, materials


def blade_weed_mesh(
    family: str, seed: int, target_height: float
) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    stem = f"{family}_{seed}_stem"
    leaf = f"{family}_{seed}_leaf"
    midrib = f"{family}_{seed}_midrib"
    phase = rng.uniform(0.0, math.tau)
    if family == "paddy_grass_weed_v4":
        count = rng.randint(6, 10)
        for index in range(count):
            length = target_height * rng.uniform(0.82, 1.24)
            mesh.add_blade(
                (rng.uniform(-0.003, 0.003), rng.uniform(-0.003, 0.003), 0.0),
                length,
                phase + index * math.tau / count + rng.uniform(-0.22, 0.22),
                math.radians(rng.uniform(45.0, 77.0)),
                length * rng.uniform(0.022, 0.043),
                rng.uniform(0.04, 0.14),
                rng.uniform(0.01, 0.08),
                rng.uniform(-0.18, 0.18),
                rng.uniform(0.18, 0.30),
                leaf,
                midrib,
                segments=24,
                profile_power=0.76,
            )
    else:
        stem_height = target_height * rng.uniform(0.35, 0.58)
        mesh.add_tube(
            (0.0, 0.0, 0.0),
            (0.0, 0.0, stem_height),
            target_height * 0.018,
            target_height * 0.010,
            9,
            stem,
        )
        count = rng.randint(5, 8)
        for index in range(count):
            length = target_height * rng.uniform(0.55, 0.95)
            mesh.add_blade(
                (0.0, 0.0, stem_height * rng.uniform(0.35, 0.95)),
                length,
                phase + index * math.tau / count + rng.uniform(-0.20, 0.20),
                math.radians(rng.uniform(18.0, 48.0)),
                length * rng.uniform(0.20, 0.32),
                rng.uniform(0.02, 0.10),
                rng.uniform(0.0, 0.04),
                rng.uniform(-0.20, 0.20),
                rng.uniform(0.08, 0.18),
                leaf,
                midrib,
                segments=20,
                profile_power=0.48,
            )
    mesh.scale_to_height(target_height)
    materials = {
        leaf: ((0.18, 0.50, 0.20), 0.38),
        midrib: ((0.34, 0.64, 0.27), 0.34),
        stem: ((0.25, 0.52, 0.21), 0.40),
    }
    return mesh, materials


def finalize_model(
    directory: Path,
    name: str,
    mesh: Mesh,
    materials: dict[str, Any],
    texture: dict[str, Any],
) -> dict[str, Any]:
    row = write_mesh(directory, name, mesh, materials)
    obj_path = directory / f"{name}.obj"
    mtl_path = directory / f"{name}.mtl"
    add_uv_and_maps(
        obj_path,
        mtl_path,
        str(texture["albedo"]),
        str(texture["normal_gl"]),
        roughness=0.36,
    )
    row.update(obj_stats(obj_path))
    row["geometry_sha256"] = geometry_sha256(obj_path)
    row["obj_sha256"] = sha256(obj_path)
    row["mtl_sha256"] = sha256(mtl_path)
    row["leaf_area_m2"] = mesh.surface_area(
        {name for name in materials if "leaf" in name or "midrib" in name}
    )
    return row


def build_botanical_assets(root: Path) -> dict[str, Any]:
    plants_root = root / "xdg/cropcraft/plants"
    if plants_root.exists():
        shutil.rmtree(plants_root)
    plants_root.mkdir(parents=True)

    crop_directory = plants_root / CROP_TYPE
    crop_textures = {
        phenotype: leaf_maps(CROP_TYPE, phenotype, crop_directory, 4100 + index)
        for index, phenotype in enumerate(CROP_PHENOTYPES)
    }
    crop_rows: list[dict[str, Any]] = []
    heights = (0.08, 0.11, 0.14, 0.18, 0.23)
    for stage, height in enumerate(heights, start=1):
        for variant in range(1, 5):
            seed = 4200 + stage * 10 + variant
            mesh, materials = rice_mesh(seed, height, stage)
            source_geometry = f"rice_stage{stage}_v{variant}"
            for phenotype in CROP_PHENOTYPES:
                name = f"{source_geometry}_{phenotype}"
                row = finalize_model(
                    crop_directory,
                    name,
                    mesh,
                    materials,
                    crop_textures[phenotype],
                )
                row.update(
                    {
                        "growth_stage": stage,
                        "phenotype": phenotype,
                        "source_geometry": source_geometry,
                    }
                )
                crop_rows.append(row)
    write_description(crop_directory, crop_rows)

    texture_specs = {
        "sagittaria_trifolia_v4": ("sagittaria", 4310),
        "paddy_grass_weed_v4": ("paddy_grass", 4320),
        "aquatic_broadleaf_v4": ("aquatic_broadleaf", 4330),
    }
    weed_rows: dict[str, list[dict[str, Any]]] = {}
    weed_textures: dict[str, dict[str, Any]] = {}
    weed_heights = (0.04, 0.065, 0.095, 0.14)
    for family_index, family in enumerate(WEED_TYPES):
        directory = plants_root / family
        phenotype, texture_seed = texture_specs[family]
        texture = leaf_maps(family, phenotype, directory, texture_seed)
        weed_textures[family] = texture
        rows: list[dict[str, Any]] = []
        for height_index, height in enumerate(weed_heights):
            for variant in range(1, 4):
                seed = 4400 + family_index * 100 + height_index * 10 + variant
                if family == "sagittaria_trifolia_v4":
                    mesh, materials = sagittaria_mesh(seed, height)
                else:
                    mesh, materials = blade_weed_mesh(family, seed, height)
                name = f"{family}_{height_index + 1:02d}_{variant:02d}"
                row = finalize_model(directory, name, mesh, materials, texture)
                row.update(
                    {
                        "growth_stage": height_index + 1,
                        "texture_backed": True,
                        "license": "CC0-1.0",
                    }
                )
                rows.append(row)
        write_description(directory, rows)
        weed_rows[family] = rows
    return {
        "crop": {
            "plant_type": CROP_TYPE,
            "models": crop_rows,
            "albedo_phenotypes": list(CROP_PHENOTYPES),
            "textures": list(crop_textures.values()),
            "unique_geometry_sha256": sorted(
                {row["geometry_sha256"] for row in crop_rows}
            ),
        },
        "weeds": {
            family: {
                "plant_type": family,
                "models": rows,
                "texture": weed_textures[family],
            }
            for family, rows in weed_rows.items()
        },
    }


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

    selected_ids = (*WET_GROUND_IDS, *PADDY_ENVIRONMENT_IDS)
    catalog = url_json(f"{API_ROOT}/assets")
    files_by_id = {
        asset_id: url_json(f"{API_ROOT}/files/{asset_id}")
        for asset_id in selected_ids
    }
    downloads = selected_downloads(files_by_id)
    advertised_bytes = sum(int(row["metadata"]["size"]) for row in downloads)
    base_bytes = int(base_pack["inventory_bytes"])
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = 2 * base_bytes + 3 * advertised_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-paddy-v4-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_V3.json")

        botanical = build_botanical_assets(root)
        downloaded_rows: list[dict[str, Any]] = []
        for row in downloads:
            if row["kind"] == "wet_ground_pbr":
                output = root / "grounds" / row["asset_id"] / row["output_name"]
            else:
                output = root / "environments" / row["output_name"]
            receipt = download_file(row["metadata"], output)
            receipt.update(
                {
                    "path": output.relative_to(root).as_posix(),
                    "asset_id": row["asset_id"],
                    "kind": row["kind"],
                    "role": row["role"],
                }
            )
            downloaded_rows.append(receipt)

        sources = deepcopy(base_pack["sources"])
        for asset_id in selected_ids:
            metadata = catalog[asset_id]
            sources[asset_id] = {
                "name": metadata["name"],
                "type": metadata["type"],
                "category": metadata.get("category"),
                "categories": metadata.get("categories"),
                "authors": metadata.get("authors", {}),
                "files_hash": metadata.get("files_hash"),
                "asset_url": f"https://polyhaven.com/a/{asset_id}",
                "api_files_url": f"{API_ROOT}/files/{asset_id}",
                "license": "CC0-1.0",
                "license_url": LICENSE_URL,
            }

        license_path = root / "LICENSES.txt"
        license_path.write_text(
            license_path.read_text(encoding="utf-8")
            + "\nPaddy v4 procedural botanical assets\n"
            + "=====================================\n"
            + "Rice, Sagittaria-like, paddy-grass and aquatic-broadleaf OBJ/MTL "
            + "meshes and their generated leaf maps are released under CC0-1.0. "
            + "They are procedural approximations, not botanical scans.\n\n"
            + "Paddy v4 Poly Haven inputs\n"
            + "===========================\n"
            + "Wet-ground PBR maps and HDRIs are official Poly Haven CC0-1.0 "
            + f"assets. License: {LICENSE_URL}\n",
            encoding="utf-8",
        )

        generated = {
            "crop": botanical["crop"],
            "weeds": botanical["weeds"],
            "background_debris": deepcopy(
                base_pack["generated_assets"]["background_debris"]
            ),
        }
        environments = [f"{asset_id}_2k.hdr" for asset_id in PADDY_ENVIRONMENT_IDS]
        surface_profiles = {
            "shallow_paddy_v4": {
                "implementation": "provenance-recorded CropCraft second patch",
                "water_depth_m": [0.002, 0.008],
                "water_coverage": [0.45, 0.95],
                "water_roughness": [0.04, 0.24],
                "wave_scale": [2.5, 14.0],
                "ior": 1.333,
                "semantic_class": "background",
            }
        }
        paddy_assets = {
            "crop_species": CROP_SPECIES,
            "primary_weed_species": "Sagittaria trifolia",
            "crop_albedo_phenotypes": list(CROP_PHENOTYPES),
            "unique_crop_geometries": len(
                botanical["crop"]["unique_geometry_sha256"]
            ),
            "wet_ground_families": list(WET_GROUND_IDS),
            "paddy_environments": environments,
            "surface_profile": "shallow_paddy_v4",
            "botanical_provenance": (
                "deterministic in-project procedural approximation; not a scan"
            ),
        }
        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "paddy-domain synthetic contribution ablation",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "builder_script": str(Path(__file__).resolve()),
            "builder_script_sha256": sha256(__file__),
            "mesh_provenance": (
                "deterministic procedural early-rice and paddy-weed meshes; "
                "official Poly Haven wet-ground PBR and HDRI inputs"
            ),
            "generated_geometry_license": "CC0-1.0",
            "third_party_source": "Poly Haven official API",
            "third_party_license": "CC0-1.0",
            "third_party_license_url": LICENSE_URL,
            "api_user_agent": USER_AGENT,
            "capacity_check": {
                "base_inventory_bytes": base_bytes,
                "advertised_download_bytes": advertised_bytes,
                "free_bytes_before_build": free_bytes,
                "required_free_bytes": required_free,
                "passed": True,
            },
            "sources": sources,
            "downloads": deepcopy(base_pack["downloads"]) + downloaded_rows,
            "generated_assets": generated,
            "paddy_v4_assets": paddy_assets,
            "surface_profiles": surface_profiles,
            "grounds": list(WET_GROUND_IDS),
            "environments": environments,
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
                "advertised_download_bytes": advertised_bytes,
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
