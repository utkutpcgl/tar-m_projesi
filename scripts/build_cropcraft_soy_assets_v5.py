#!/usr/bin/env python3
"""Build the frozen soybean-domain CropCraft v5 asset challenger.

The accepted dryland v3 pack remains the soil, HDRI and debris foundation.
This builder replaces only the plant library with deterministic early soybean,
Amaranthus viridis and Cynodon dactylon approximations, then adds the official
Poly Haven ``grass_bermuda_01`` CC0 texture-backed model as an exact-common-name
Cynodon appearance reference.  Procedural plants are explicitly not scans.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import subprocess
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
from build_cropcraft_paddy_assets_v4 import add_uv_and_maps
from enhance_cropcraft_assets_v3 import (
    geometry_sha256,
    gltf_downloads,
    obj_stats,
    validate_base_pack,
)


PACK_ID = "cropcraft_soy_robust_v5_r1"
USER_AGENT = POLY_HAVEN_USER_AGENT
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONVERTER = PROJECT_ROOT / "scripts/prepare_polyhaven_plant_assets_blender.py"
DEFAULT_BLENDER = Path(
    "/home/ankaref/Documents/Projects/simulation/"
    ".tools/blender-4.5.12-linux-x64/blender"
)
CROP_TYPE = "soybean_early_v5"
CROP_SPECIES = "Glycine max"
CROP_PHENOTYPES = ("healthy_dark", "healthy_light", "field_stress")
AMARANTHUS_TYPE = "amaranthus_viridis_v5"
CYNODON_TYPE = "cynodon_dactylon_v5"
WEED_TYPES = (AMARANTHUS_TYPE, CYNODON_TYPE)
REFERENCE_SPEC = {
    "asset_id": "grass_bermuda_01",
    "target_family": CYNODON_TYPE,
    "target_heights_m": [0.025, 0.035, 0.050, 0.065, 0.085, 0.110],
    "maximum_width_height_ratio": 6.0,
}


def direction(length: float, azimuth: float, elevation: float) -> tuple[float, float, float]:
    planar = length * math.cos(elevation)
    return (
        planar * math.cos(azimuth),
        planar * math.sin(azimuth),
        length * math.sin(elevation),
    )


def endpoint(
    base: tuple[float, float, float],
    length: float,
    azimuth: float,
    elevation: float,
) -> tuple[float, float, float]:
    offset = direction(length, azimuth, elevation)
    return tuple(base[index] + offset[index] for index in range(3))  # type: ignore[return-value]


def leaf_maps(
    family: str,
    phenotype: str,
    output_directory: Path,
    seed: int,
) -> dict[str, Any]:
    """Create deterministic 1K albedo and tangent-space normal maps."""

    size = 1024
    yy, xx = np.mgrid[0:size, 0:size]
    rng = np.random.default_rng(seed)
    palettes = {
        "healthy_dark": np.array([38.0, 111.0, 37.0]),
        "healthy_light": np.array([67.0, 146.0, 52.0]),
        "field_stress": np.array([111.0, 132.0, 42.0]),
        "amaranthus_green": np.array([52.0, 126.0, 47.0]),
        "amaranthus_reddish": np.array([71.0, 113.0, 43.0]),
        "cynodon_green": np.array([69.0, 137.0, 45.0]),
        "cynodon_dry": np.array([118.0, 139.0, 48.0]),
    }
    base = palettes[phenotype]
    coarse = (
        0.52 * np.sin(xx / 39.0 + yy / 91.0)
        + 0.31 * np.sin(xx / 127.0 - yy / 57.0)
        + 0.17 * np.sin(yy / 17.0)
    )
    fine = rng.normal(0.0, 1.0, size=(size, size))
    modulation = 1.0 + 0.048 * coarse + 0.014 * fine
    rgb = base[None, None, :] * modulation[:, :, None]

    midrib_width = 7.0 if family == CYNODON_TYPE else 11.0
    midrib = np.exp(-((xx - size / 2.0) / midrib_width) ** 2)
    lateral = np.zeros((size, size), dtype=np.float64)
    if family != CYNODON_TYPE:
        for offset in range(-420, 421, 84):
            branch = np.abs((yy - size / 2.0) - offset)
            left = np.exp(-((xx - size / 2.0 + 0.74 * branch) / 6.0) ** 2)
            right = np.exp(-((xx - size / 2.0 - 0.74 * branch) / 6.0) ** 2)
            lateral = np.maximum(lateral, np.maximum(left, right))
    vein = np.clip(midrib + 0.34 * lateral, 0.0, 1.0)
    rgb += vein[:, :, None] * np.array([15.0, 24.0, 8.0])

    if phenotype in {"field_stress", "cynodon_dry"}:
        stress = 0.5 + 0.5 * np.sin(xx / 53.0 + yy / 101.0)
        rgb[:, :, 0] += 22.0 * stress
        rgb[:, :, 1] -= 10.0 * stress
    if phenotype == "amaranthus_reddish":
        edge = np.clip(np.abs(xx - size / 2.0) / (size / 2.0), 0.0, 1.0)
        rgb[:, :, 0] += 22.0 * edge
        rgb[:, :, 1] -= 12.0 * edge
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    height = (
        0.5
        + 0.15 * np.sin(xx / 23.0)
        + 0.07 * np.sin(yy / 47.0 + xx / 109.0)
        + 0.16 * vein
    )
    gy, gx = np.gradient(height)
    normal = np.dstack((-2.0 * gx, -2.0 * gy, np.ones_like(gx)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
    normal_rgb = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)

    output_directory.mkdir(parents=True, exist_ok=True)
    stem = f"{family}_{phenotype}_v5"
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


def add_leaflet(
    mesh: Mesh,
    base: tuple[float, float, float],
    blade_length: float,
    azimuth: float,
    elevation: float,
    rng: random.Random,
    leaf_material: str,
    midrib_material: str,
    width_ratio: float = 0.29,
    segments: int = 48,
) -> None:
    mesh.add_blade(
        base,
        blade_length,
        azimuth,
        elevation,
        blade_length * width_ratio,
        rng.uniform(0.025, 0.085),
        rng.uniform(0.0, 0.035),
        rng.uniform(-0.14, 0.14),
        rng.uniform(0.07, 0.15),
        leaf_material,
        midrib_material,
        segments=segments,
        profile_power=rng.uniform(0.30, 0.42),
    )


def add_trifoliolate(
    mesh: Mesh,
    stem_base: tuple[float, float, float],
    plant_height: float,
    azimuth: float,
    rng: random.Random,
    petiole_material: str,
    leaf_material: str,
    midrib_material: str,
    scale: float = 1.0,
) -> None:
    petiole_length = plant_height * rng.uniform(0.105, 0.145) * scale
    petiole_elevation = math.radians(rng.uniform(13.0, 32.0))
    hub = endpoint(stem_base, petiole_length, azimuth, petiole_elevation)
    mesh.add_tube(
        stem_base,
        hub,
        plant_height * 0.0060,
        plant_height * 0.0038,
        8,
        petiole_material,
    )
    central_length = plant_height * rng.uniform(0.175, 0.235) * scale
    for index, offset in enumerate((0.0, -math.radians(53.0), math.radians(53.0))):
        length_scale = 1.0 if index == 0 else rng.uniform(0.76, 0.88)
        add_leaflet(
            mesh,
            hub,
            central_length * length_scale,
            azimuth + offset + rng.uniform(-0.06, 0.06),
            math.radians(rng.uniform(12.0, 31.0)),
            rng,
            leaf_material,
            midrib_material,
        )


def add_opposite_simple_pair(
    mesh: Mesh,
    stem_base: tuple[float, float, float],
    plant_height: float,
    azimuth: float,
    rng: random.Random,
    petiole_material: str,
    leaf_material: str,
    midrib_material: str,
    cotyledon: bool,
) -> None:
    for side in (0.0, math.pi):
        leaf_azimuth = azimuth + side + rng.uniform(-0.05, 0.05)
        petiole_length = plant_height * (0.035 if cotyledon else 0.075)
        hub = endpoint(
            stem_base,
            petiole_length,
            leaf_azimuth,
            math.radians(rng.uniform(7.0, 18.0)),
        )
        mesh.add_tube(
            stem_base,
            hub,
            plant_height * 0.0050,
            plant_height * 0.0032,
            8,
            petiole_material,
        )
        length = plant_height * rng.uniform(
            0.115 if cotyledon else 0.175,
            0.145 if cotyledon else 0.220,
        )
        add_leaflet(
            mesh,
            hub,
            length,
            leaf_azimuth,
            math.radians(rng.uniform(8.0, 24.0)),
            rng,
            leaf_material,
            midrib_material,
            width_ratio=rng.uniform(0.32, 0.40) if cotyledon else rng.uniform(0.28, 0.34),
        )


def soybean_mesh(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any], dict[str, int]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"soybean_{seed}"
    stem_material = f"{prefix}_stem"
    petiole_material = f"{prefix}_petiole"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    stem_height = target_height * rng.uniform(0.72, 0.86)
    lean_azimuth = rng.uniform(0.0, math.tau)
    stem_top = (
        target_height * rng.uniform(0.015, 0.045) * math.cos(lean_azimuth),
        target_height * rng.uniform(0.015, 0.045) * math.sin(lean_azimuth),
        stem_height,
    )
    mesh.add_tube(
        (0.0, 0.0, 0.0),
        stem_top,
        target_height * rng.uniform(0.013, 0.018),
        target_height * rng.uniform(0.007, 0.010),
        12,
        stem_material,
    )
    phase = rng.uniform(0.0, math.tau)
    cotyledon_pairs = 1 if stage <= 2 else 0
    if cotyledon_pairs:
        add_opposite_simple_pair(
            mesh,
            (0.0, 0.0, stem_height * 0.16),
            target_height,
            phase,
            rng,
            petiole_material,
            leaf_material,
            midrib_material,
            cotyledon=True,
        )
    add_opposite_simple_pair(
        mesh,
        (0.0, 0.0, stem_height * (0.34 if stage == 1 else 0.27)),
        target_height,
        phase + math.pi / 2.0,
        rng,
        petiole_material,
        leaf_material,
        midrib_material,
        cotyledon=False,
    )
    trifoliolate_nodes = max(0, stage - 1)
    for node in range(trifoliolate_nodes):
        fraction = 0.43 + (0.48 * node / max(1, trifoliolate_nodes - 1))
        base = (
            stem_top[0] * fraction,
            stem_top[1] * fraction,
            stem_height * fraction,
        )
        add_trifoliolate(
            mesh,
            base,
            target_height,
            phase + node * math.radians(137.5) + rng.uniform(-0.12, 0.12),
            rng,
            petiole_material,
            leaf_material,
            midrib_material,
            scale=1.02 - 0.06 * node,
        )
    branch_nodes = 0
    if stage >= 4:
        branch_nodes = stage - 3
        for branch in range(branch_nodes):
            fraction = 0.43 + 0.10 * branch
            branch_base = (
                stem_top[0] * fraction,
                stem_top[1] * fraction,
                stem_height * fraction,
            )
            branch_azimuth = phase + math.pi + branch * math.radians(111.0)
            branch_end = endpoint(
                branch_base,
                target_height * rng.uniform(0.10, 0.16),
                branch_azimuth,
                math.radians(rng.uniform(28.0, 50.0)),
            )
            mesh.add_tube(
                branch_base,
                branch_end,
                target_height * 0.0065,
                target_height * 0.0038,
                9,
                stem_material,
            )
            add_trifoliolate(
                mesh,
                branch_end,
                target_height,
                branch_azimuth + rng.uniform(-0.18, 0.18),
                rng,
                petiole_material,
                leaf_material,
                midrib_material,
                scale=0.76,
            )
    mesh.scale_to_height(target_height)
    mesh.clamp_width(target_height * 1.85)
    green = rng.uniform(0.38, 0.52)
    materials = {
        leaf_material: ((green * 0.36, green, green * 0.30), 0.42),
        midrib_material: ((green * 0.62, min(0.74, green * 1.18), green * 0.44), 0.38),
        petiole_material: ((green * 0.43, green * 0.84, green * 0.31), 0.48),
        stem_material: ((green * 0.40, green * 0.76, green * 0.28), 0.50),
    }
    return mesh, materials, {
        "cotyledon_pairs": cotyledon_pairs,
        "unifoliolate_pairs": 1,
        "trifoliolate_nodes": trifoliolate_nodes,
        "branch_nodes": branch_nodes,
    }


def amaranthus_mesh(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"amaranthus_{seed}"
    stem_material = f"{prefix}_stem"
    petiole_material = f"{prefix}_petiole"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    stem_height = target_height * rng.uniform(0.76, 0.90)
    mesh.add_tube(
        (0.0, 0.0, 0.0),
        (0.0, 0.0, stem_height),
        max(0.00065, target_height * 0.018),
        max(0.00035, target_height * 0.009),
        10,
        stem_material,
    )
    leaf_count = 4 + stage * 2 + seed % 2
    phase = rng.uniform(0.0, math.tau)
    for index in range(leaf_count):
        maturity = index / max(1, leaf_count - 1)
        base = (0.0, 0.0, stem_height * (0.22 + 0.70 * maturity))
        azimuth = phase + index * math.radians(137.5) + rng.uniform(-0.12, 0.12)
        petiole_length = target_height * rng.uniform(0.055, 0.105) * (1.0 - 0.18 * maturity)
        hub = endpoint(
            base,
            petiole_length,
            azimuth,
            math.radians(rng.uniform(13.0, 34.0)),
        )
        mesh.add_tube(
            base,
            hub,
            target_height * 0.0048,
            target_height * 0.0028,
            7,
            petiole_material,
        )
        add_leaflet(
            mesh,
            hub,
            target_height * rng.uniform(0.14, 0.24) * (1.0 - 0.24 * maturity),
            azimuth,
            math.radians(rng.uniform(15.0, 38.0)),
            rng,
            leaf_material,
            midrib_material,
            width_ratio=rng.uniform(0.25, 0.34),
            segments=36,
        )
    mesh.scale_to_height(target_height)
    mesh.clamp_width(target_height * 1.55)
    red = seed % 2 == 0
    green = rng.uniform(0.40, 0.56)
    materials = {
        leaf_material: ((green * 0.40, green, green * 0.31), 0.48),
        midrib_material: ((green * 0.65, min(0.77, green * 1.14), green * 0.43), 0.43),
        petiole_material: ((0.34, 0.11, 0.10), 0.49) if red else ((0.25, 0.48, 0.20), 0.50),
        stem_material: ((0.38, 0.10, 0.09), 0.52) if red else ((0.24, 0.46, 0.19), 0.52),
    }
    return mesh, materials


def cynodon_mesh(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"cynodon_{seed}"
    stolon_material = f"{prefix}_stolon"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    phase = rng.uniform(0.0, math.tau)
    stolon_count = 2 + stage // 2 + seed % 2
    for stolon in range(stolon_count):
        azimuth = phase + stolon * math.tau / stolon_count + rng.uniform(-0.20, 0.20)
        spread = target_height * rng.uniform(1.7, 3.0)
        start = (0.0, 0.0, target_height * 0.025)
        end = (
            spread * math.cos(azimuth),
            spread * math.sin(azimuth),
            target_height * rng.uniform(0.02, 0.06),
        )
        mesh.add_tube(
            start,
            end,
            max(0.00035, target_height * 0.010),
            max(0.00025, target_height * 0.006),
            7,
            stolon_material,
        )
        node_count = 2 + stage
        for node in range(node_count):
            t = (node + 1) / (node_count + 1)
            base = tuple(start[i] * (1.0 - t) + end[i] * t for i in range(3))
            blade_count = 2 + ((node + seed) % 2)
            for blade in range(blade_count):
                length = target_height * rng.uniform(0.56, 1.03)
                mesh.add_blade(
                    base,  # type: ignore[arg-type]
                    length,
                    azimuth + math.pi / 2.0 + blade * math.pi + rng.uniform(-0.26, 0.26),
                    math.radians(rng.uniform(48.0, 78.0)),
                    length * rng.uniform(0.022, 0.040),
                    rng.uniform(0.03, 0.11),
                    rng.uniform(0.0, 0.055),
                    rng.uniform(-0.24, 0.24),
                    rng.uniform(0.12, 0.24),
                    leaf_material,
                    midrib_material,
                    segments=24,
                    profile_power=0.70,
                )
    mesh.scale_to_height(target_height)
    mesh.clamp_width(target_height * 4.5)
    dry = seed % 3 == 0
    green = rng.uniform(0.42, 0.58)
    materials = {
        leaf_material: ((green * (0.52 if dry else 0.36), green, green * 0.24), 0.56),
        midrib_material: ((green * 0.69, min(0.79, green * 1.10), green * 0.36), 0.50),
        stolon_material: ((0.38, 0.29, 0.11), 0.58) if dry else ((0.24, 0.48, 0.18), 0.56),
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
        roughness=0.44,
    )
    row.update(obj_stats(obj_path))
    row["geometry_sha256"] = geometry_sha256(obj_path)
    row["obj_sha256"] = sha256(obj_path)
    row["mtl_sha256"] = sha256(mtl_path)
    row["leaf_area_m2"] = mesh.surface_area(
        {name for name in materials if "leaf" in name or "midrib" in name}
    )
    row["texture_backed"] = True
    row["license"] = "CC0-1.0"
    return row


def build_procedural_botanical_assets(root: Path) -> dict[str, Any]:
    plants_root = root / "xdg/cropcraft/plants"
    if plants_root.exists():
        shutil.rmtree(plants_root)
    plants_root.mkdir(parents=True)

    crop_directory = plants_root / CROP_TYPE
    crop_textures = {
        phenotype: leaf_maps(CROP_TYPE, phenotype, crop_directory, 5100 + index)
        for index, phenotype in enumerate(CROP_PHENOTYPES)
    }
    crop_rows: list[dict[str, Any]] = []
    crop_heights = (0.08, 0.14, 0.22, 0.32, 0.42)
    for stage, height in enumerate(crop_heights, start=1):
        for variant in range(1, 5):
            seed = 5200 + stage * 10 + variant
            mesh, materials, traits = soybean_mesh(seed, height, stage)
            source_geometry = f"soybean_stage{stage}_v{variant}"
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
                        "species": CROP_SPECIES,
                        "stage_traits": traits,
                    }
                )
                crop_rows.append(row)
    write_description(crop_directory, crop_rows)

    amaranthus_directory = plants_root / AMARANTHUS_TYPE
    amaranthus_textures = {
        phenotype: leaf_maps(
            AMARANTHUS_TYPE,
            phenotype,
            amaranthus_directory,
            5310 + index,
        )
        for index, phenotype in enumerate(("amaranthus_green", "amaranthus_reddish"))
    }
    amaranthus_rows: list[dict[str, Any]] = []
    for stage, height in enumerate((0.04, 0.08, 0.14, 0.23), start=1):
        for variant in range(1, 5):
            seed = 5400 + stage * 10 + variant
            phenotype = "amaranthus_reddish" if variant % 2 == 0 else "amaranthus_green"
            mesh, materials = amaranthus_mesh(seed, height, stage)
            name = f"amaranthus_stage{stage}_v{variant}"
            row = finalize_model(
                amaranthus_directory,
                name,
                mesh,
                materials,
                amaranthus_textures[phenotype],
            )
            row.update(
                {
                    "growth_stage": stage,
                    "phenotype": phenotype,
                    "species": "Amaranthus viridis",
                    "source_kind": "procedural_botanical_approximation",
                }
            )
            amaranthus_rows.append(row)
    write_description(amaranthus_directory, amaranthus_rows)

    cynodon_directory = plants_root / CYNODON_TYPE
    cynodon_textures = {
        phenotype: leaf_maps(
            CYNODON_TYPE,
            phenotype,
            cynodon_directory,
            5510 + index,
        )
        for index, phenotype in enumerate(("cynodon_green", "cynodon_dry"))
    }
    cynodon_rows: list[dict[str, Any]] = []
    for stage, height in enumerate((0.03, 0.05, 0.08, 0.12), start=1):
        for variant in range(1, 5):
            seed = 5600 + stage * 10 + variant
            phenotype = "cynodon_dry" if variant % 3 == 0 else "cynodon_green"
            mesh, materials = cynodon_mesh(seed, height, stage)
            name = f"cynodon_stage{stage}_v{variant}"
            row = finalize_model(
                cynodon_directory,
                name,
                mesh,
                materials,
                cynodon_textures[phenotype],
            )
            row.update(
                {
                    "growth_stage": stage,
                    "phenotype": phenotype,
                    "species": "Cynodon dactylon",
                    "source_kind": "procedural_stolon_approximation",
                }
            )
            cynodon_rows.append(row)
    write_description(cynodon_directory, cynodon_rows)
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
            AMARANTHUS_TYPE: {
                "plant_type": AMARANTHUS_TYPE,
                "models": amaranthus_rows,
                "textures": list(amaranthus_textures.values()),
            },
            CYNODON_TYPE: {
                "plant_type": CYNODON_TYPE,
                "models": cynodon_rows,
                "textures": list(cynodon_textures.values()),
            },
        },
    }


def append_reference_models(
    root: Path,
    botanical: dict[str, Any],
    conversion: dict[str, Any],
) -> list[dict[str, Any]]:
    directory = root / "xdg/cropcraft/plants" / CYNODON_TYPE
    rows: list[dict[str, Any]] = []
    for asset in conversion["assets"]:
        for model in asset["exported_models"]:
            obj_path = directory / str(model["filename"])
            stats = obj_stats(obj_path)
            row = {
                **model,
                **stats,
                "leaf_area_m2": float(model["surface_area_m2"]),
                "geometry_sha256": geometry_sha256(obj_path),
                "texture_backed": True,
                "license": "CC0-1.0",
                "species": "Cynodon dactylon",
                "source_kind": "official_CC0_exact_common_name_appearance_reference",
            }
            rows.append(row)
    botanical["weeds"][CYNODON_TYPE]["models"].extend(rows)
    write_description(
        directory,
        botanical["weeds"][CYNODON_TYPE]["models"],
    )
    return rows


def ensure_reference_material_maps(
    root: Path,
    conversion: dict[str, Any],
    downloaded_rows: list[dict[str, Any]],
) -> None:
    asset_id = str(REFERENCE_SPEC["asset_id"])
    target_directory = root / "xdg/cropcraft/plants" / CYNODON_TYPE
    source_texture_directory = root / "sources/polyhaven_models" / asset_id / "textures"
    for texture_path in sorted(source_texture_directory.glob("*")):
        if texture_path.is_file():
            shutil.copy2(texture_path, target_directory / texture_path.name)
    names = {
        str(row["role"]): Path(str(row["path"])).name
        for row in downloaded_rows
        if row["asset_id"] == asset_id
    }
    for asset in conversion["assets"]:
        for model in asset["exported_models"]:
            mtl_path = target_directory / str(model["mtl_filename"])
            material = mtl_path.read_text(encoding="utf-8")
            additions = []
            if "map_Kd " not in material:
                additions.append("map_Kd " + names["diffuse"])
            if "map_Bump " not in material:
                additions.append("map_Bump -bm 1.000000 " + names["normal"])
            if additions:
                mtl_path.write_text(
                    material.rstrip() + "\n" + "\n".join(additions) + "\n",
                    encoding="utf-8",
                )
            model["mtl_sha256"] = sha256(mtl_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-pack", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blender", default=str(DEFAULT_BLENDER))
    args = parser.parse_args()

    base_root = Path(args.base_pack).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    blender = Path(args.blender).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if not blender.is_file() or not CONVERTER.is_file():
        raise FileNotFoundError("Blender or conversion helper is missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    base_pack = validate_base_pack(base_root)

    catalog = url_json(f"{API_ROOT}/assets?t=models")
    asset_id = str(REFERENCE_SPEC["asset_id"])
    files = url_json(f"{API_ROOT}/files/{asset_id}")
    downloads = gltf_downloads(asset_id, files)
    advertised_bytes = sum(int(row["metadata"]["size"]) for row in downloads)
    base_bytes = int(base_pack["inventory_bytes"])
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = 2 * base_bytes + 3 * advertised_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-soy-v5-", dir=destination.parent
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        root = temporary / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_V3.json")

        botanical = build_procedural_botanical_assets(root)
        downloaded_rows: list[dict[str, Any]] = []
        input_gltf: Path | None = None
        for row in downloads:
            output = root / "sources/polyhaven_models" / asset_id / row["relative_path"]
            receipt = download_file(row["metadata"], output)
            receipt.update(
                {
                    "asset_id": asset_id,
                    "kind": "exact_common_name_reference_plant_model",
                    "role": row["role"],
                    "path": output.relative_to(root).as_posix(),
                }
            )
            downloaded_rows.append(receipt)
            if row["role"] == "gltf":
                input_gltf = output
        if input_gltf is None:
            raise RuntimeError("Poly Haven API did not provide a GLTF root")

        conversion_spec = {
            "assets": [
                {
                    **REFERENCE_SPEC,
                    "input_gltf": str(input_gltf),
                    "output_directory": str(
                        root / "xdg/cropcraft/plants" / CYNODON_TYPE
                    ),
                }
            ],
            "output_report": str(temporary / "conversion_report.raw.json"),
        }
        raw_spec = temporary / "conversion_spec.raw.json"
        raw_spec.write_text(
            json.dumps(conversion_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        conversion_process = subprocess.run(
            [
                str(blender),
                "--background",
                "--python",
                str(CONVERTER),
                "--",
                str(raw_spec),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        (provenance / "polyhaven_bermuda_conversion_blender.log").write_text(
            conversion_process.stdout + conversion_process.stderr,
            encoding="utf-8",
        )
        if conversion_process.returncode != 0:
            raise RuntimeError(
                "Poly Haven conversion failed:\n"
                + "\n".join(
                    (conversion_process.stdout + conversion_process.stderr).splitlines()[-60:]
                )
            )
        conversion = json.loads(
            Path(conversion_spec["output_report"]).read_text(encoding="utf-8")
        )
        conversion["assets"][0]["input_gltf"] = input_gltf.relative_to(root).as_posix()
        ensure_reference_material_maps(root, conversion, downloaded_rows)
        reference_rows = append_reference_models(root, botanical, conversion)
        (provenance / "polyhaven_bermuda_conversion_report.json").write_text(
            json.dumps(conversion, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        frozen_spec = deepcopy(conversion_spec)
        frozen_spec["output_report"] = "provenance/polyhaven_bermuda_conversion_report.json"
        frozen_spec["assets"][0]["input_gltf"] = input_gltf.relative_to(root).as_posix()
        frozen_spec["assets"][0]["output_directory"] = (
            Path(frozen_spec["assets"][0]["output_directory"])
            .relative_to(root)
            .as_posix()
        )
        (provenance / "polyhaven_bermuda_conversion_spec.json").write_text(
            json.dumps(frozen_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        metadata = catalog[asset_id]
        sources = deepcopy(base_pack["sources"])
        sources[asset_id] = {
            "name": metadata["name"],
            "type": metadata["type"],
            "category": metadata.get("category"),
            "categories": metadata.get("categories"),
            "description": metadata.get("description"),
            "authors": metadata.get("authors", {}),
            "files_hash": metadata.get("files_hash"),
            "polycount": metadata.get("polycount"),
            "dimensions": metadata.get("dimensions"),
            "asset_url": f"https://polyhaven.com/a/{asset_id}",
            "api_files_url": f"{API_ROOT}/files/{asset_id}",
            "license": "CC0-1.0",
            "license_url": LICENSE_URL,
            "semantic_caveat": (
                "exact common-name appearance reference; normalized authored "
                "variants, not measured single seedlings"
            ),
        }

        license_path = root / "LICENSES.txt"
        license_path.write_text(
            license_path.read_text(encoding="utf-8")
            + "\nSoybean-domain v5 procedural botanical assets\n"
            + "=============================================\n"
            + "Soybean, Amaranthus viridis and procedural Cynodon dactylon "
            + "OBJ/MTL meshes and generated leaf maps are released under "
            + "CC0-1.0. They are deterministic botanical approximations, not scans.\n\n"
            + "Soybean-domain v5 Poly Haven input\n"
            + "===================================\n"
            + "grass_bermuda_01 and its texture maps are official Poly Haven "
            + f"CC0-1.0 assets. License: {LICENSE_URL}\n",
            encoding="utf-8",
        )

        generated = {
            "crop": botanical["crop"],
            "weeds": botanical["weeds"],
            "background_debris": deepcopy(
                base_pack["generated_assets"]["background_debris"]
            ),
        }
        final_stage_rows = [
            row
            for row in botanical["crop"]["models"]
            if int(row["growth_stage"]) == 5
        ]
        soy_assets = {
            "crop_species": CROP_SPECIES,
            "weed_species": ["Amaranthus viridis", "Cynodon dactylon"],
            "crop_albedo_phenotypes": list(CROP_PHENOTYPES),
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
                    for row in final_stage_rows
                ),
            },
            "exact_species_reference_sources": [asset_id],
            "texture_backed_reference_models": reference_rows,
            "reference_conversion_report": (
                "provenance/polyhaven_bermuda_conversion_report.json"
            ),
            "botanical_provenance": (
                "deterministic in-project procedural approximation plus one "
                "official CC0 exact-common-name appearance reference; no real "
                "GrowingSoy imagery, mask, cutout or texture used"
            ),
            "real_growingsoy_training_or_asset_exposure": 0,
        }
        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "soybean-domain synthetic contribution ablation",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "builder_script": str(Path(__file__).resolve()),
            "builder_script_sha256": sha256(__file__),
            "helper_scripts": {
                "mesh_builder": {
                    "path": str(PROJECT_ROOT / "scripts/build_cropcraft_agri_assets.py"),
                    "sha256": sha256(PROJECT_ROOT / "scripts/build_cropcraft_agri_assets.py"),
                },
                "material_mapper": {
                    "path": str(PROJECT_ROOT / "scripts/build_cropcraft_paddy_assets_v4.py"),
                    "sha256": sha256(PROJECT_ROOT / "scripts/build_cropcraft_paddy_assets_v4.py"),
                },
                "asset_helpers": {
                    "path": str(PROJECT_ROOT / "scripts/enhance_cropcraft_assets_v3.py"),
                    "sha256": sha256(PROJECT_ROOT / "scripts/enhance_cropcraft_assets_v3.py"),
                },
                "blender_converter": {
                    "path": str(CONVERTER),
                    "sha256": sha256(CONVERTER),
                },
            },
            "mesh_provenance": (
                "deterministic procedural early soybean and target weed meshes; "
                "official Poly Haven Bermuda-grass CC0 reference variants"
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
            "soy_v5_assets": soy_assets,
            "grounds": deepcopy(base_pack["grounds"]),
            "environments": deepcopy(base_pack["environments"]),
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(int(row["size_bytes"]) for row in inventory),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
