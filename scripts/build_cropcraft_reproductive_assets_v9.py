#!/usr/bin/env python3
"""Build the isolated late-reproductive rice extension for CropCraft.

The accepted paddy R5 pack is copied without changing its early-rice, weed,
ground, environment, or debris assets.  This builder adds deterministic
procedural heading-to-mature rice geometry and project-generated leaf textures.
It intentionally does not add duckweed or any other missing factor so a later
equal-budget contribution test remains attributable.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from build_cropcraft_agri_assets import (  # noqa: E402
    Mesh,
    canonical_sha256,
    sha256,
    tree_inventory,
    write_description,
)
import build_cropcraft_paddy_assets_v4 as paddy  # noqa: E402
from enhance_cropcraft_assets_v3 import validate_base_pack  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "cropcraft_paddy_reproductive_v9_r1"
PLANT_TYPE = "rice_reproductive_v9"
SPECIES = "Oryza sativa"
STAGES = (
    ("heading", 0.72, ("heading_green", "grain_fill_transition")),
    ("flowering", 0.82, ("heading_green", "grain_fill_transition")),
    ("grain_fill", 0.92, ("grain_fill_transition", "mature_senescent")),
    ("mature", 1.02, ("grain_fill_transition", "mature_senescent")),
)
SOURCE_TEXTURES = {
    "heading_green": "heading_green_imagegen.png",
    "grain_fill_transition": "grain_fill_transition_imagegen.png",
    "mature_senescent": "mature_senescent_imagegen.png",
}
TEXTURE_TARGET_MEDIANS = {
    "heading_green": (55.0, 120.0, 35.0),
    "grain_fill_transition": (118.0, 126.0, 42.0),
    "mature_senescent": (178.0, 145.0, 65.0),
}


def _unit(vector: tuple[float, float, float]) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(value))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize a zero-length vector")
    return value / norm


def add_oriented_ellipsoid(
    mesh: Mesh,
    center: tuple[float, float, float],
    axis: tuple[float, float, float],
    long_radius: float,
    cross_radius: float,
    material: str,
    rings: int = 5,
    sides: int = 8,
) -> None:
    """Add a closed, low-poly ellipsoid whose long axis follows ``axis``."""

    if long_radius <= 0.0 or cross_radius <= 0.0 or rings < 2 or sides < 5:
        raise ValueError("Invalid ellipsoid dimensions or tessellation")
    center_v = np.asarray(center, dtype=np.float64)
    long_axis = _unit(axis)
    reference = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(np.dot(long_axis, reference))) > 0.92:
        reference = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    basis_a = np.cross(long_axis, reference)
    basis_a /= np.linalg.norm(basis_a)
    basis_b = np.cross(long_axis, basis_a)
    basis_b /= np.linalg.norm(basis_b)

    bottom = mesh.vertex(tuple(center_v - long_axis * long_radius))
    latitude_rings: list[list[int]] = []
    for ring_index in range(1, rings + 1):
        phi = math.pi * ring_index / (rings + 1)
        axial = math.cos(phi) * long_radius
        radial = math.sin(phi) * cross_radius
        ring: list[int] = []
        for side in range(sides):
            theta = math.tau * side / sides
            point = (
                center_v
                + long_axis * axial
                + basis_a * (radial * math.cos(theta))
                + basis_b * (radial * math.sin(theta))
            )
            ring.append(mesh.vertex(tuple(point)))
        latitude_rings.append(ring)
    top = mesh.vertex(tuple(center_v + long_axis * long_radius))

    for side in range(sides):
        nxt = (side + 1) % sides
        mesh.face((bottom, latitude_rings[0][nxt], latitude_rings[0][side]), material)
    for ring_index in range(len(latitude_rings) - 1):
        lower = latitude_rings[ring_index]
        upper = latitude_rings[ring_index + 1]
        for side in range(sides):
            nxt = (side + 1) % sides
            mesh.face((lower[side], lower[nxt], upper[nxt], upper[side]), material)
    for side in range(sides):
        nxt = (side + 1) % sides
        mesh.face((latitude_rings[-1][side], latitude_rings[-1][nxt], top), material)


def _tube_chain(
    mesh: Mesh,
    points: list[tuple[float, float, float]],
    radius: float,
    material: str,
    sides: int,
) -> None:
    for index in range(len(points) - 1):
        mesh.add_tube(
            points[index],
            points[index + 1],
            radius * (1.0 - 0.10 * index),
            radius * (0.88 - 0.10 * index),
            sides,
            material,
        )


def _panicle(
    mesh: Mesh,
    rng: random.Random,
    origin: tuple[float, float, float],
    azimuth: float,
    target_height: float,
    stage_index: int,
    rachis_material: str,
    grain_material: str,
) -> tuple[int, int]:
    """Add one branched panicle and return branch and grain counts."""

    maturity = (stage_index - 1) / 3.0
    lean = target_height * rng.uniform(0.045, 0.095)
    panicle_height = target_height * rng.uniform(0.135, 0.190)
    droop = target_height * (0.012 + maturity * rng.uniform(0.025, 0.055))
    direction = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
    side = np.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
    p0 = np.asarray(origin, dtype=np.float64)
    p1 = p0 + direction * lean * 0.25 + np.array([0.0, 0.0, panicle_height * 0.38])
    p2 = p0 + direction * lean * 0.68 + side * rng.uniform(-0.012, 0.012) + np.array(
        [0.0, 0.0, panicle_height * 0.73]
    )
    p3 = p0 + direction * lean + np.array([0.0, 0.0, panicle_height - droop])
    axis_points = [tuple(p0), tuple(p1), tuple(p2), tuple(p3)]
    _tube_chain(
        mesh,
        axis_points,
        target_height * 0.0032,
        rachis_material,
        sides=7,
    )

    branches = rng.randint(5, 7 + int(stage_index >= 3))
    grains_total = 0
    for branch_index in range(branches):
        fraction = 0.18 + 0.68 * branch_index / max(1, branches - 1)
        if fraction < 0.38:
            start = p0 + (p1 - p0) * (fraction / 0.38)
        elif fraction < 0.73:
            start = p1 + (p2 - p1) * ((fraction - 0.38) / 0.35)
        else:
            start = p2 + (p3 - p2) * ((fraction - 0.73) / 0.27)
        branch_azimuth = azimuth + math.pi * 0.5 + branch_index * math.radians(137.5)
        branch_length = target_height * rng.uniform(0.050, 0.095) * (
            1.08 - 0.24 * fraction
        )
        branch_dir = np.array(
            [math.cos(branch_azimuth), math.sin(branch_azimuth), 0.0],
            dtype=np.float64,
        )
        mid = start + branch_dir * branch_length * 0.58
        mid[2] -= target_height * (0.004 + 0.012 * maturity)
        end = start + branch_dir * branch_length
        end[2] -= target_height * (0.010 + 0.032 * maturity)
        _tube_chain(
            mesh,
            [tuple(start), tuple(mid), tuple(end)],
            target_height * 0.0018,
            rachis_material,
            sides=6,
        )

        grain_count = rng.randint(7, 10)
        grains_total += grain_count
        for grain_index in range(grain_count):
            t = 0.18 + 0.78 * grain_index / max(1, grain_count - 1)
            if t <= 0.58:
                center = start + (mid - start) * (t / 0.58)
            else:
                center = mid + (end - mid) * ((t - 0.58) / 0.42)
            alternating = -1.0 if grain_index % 2 else 1.0
            lateral = np.array(
                [-branch_dir[1], branch_dir[0], 0.0], dtype=np.float64
            )
            center = center + lateral * alternating * target_height * rng.uniform(
                0.0025, 0.0055
            )
            center[2] -= target_height * rng.uniform(0.003, 0.009)
            grain_axis = tuple(
                branch_dir * rng.uniform(0.12, 0.30)
                + np.array([0.0, 0.0, -1.0], dtype=np.float64)
            )
            add_oriented_ellipsoid(
                mesh,
                tuple(center),
                grain_axis,
                target_height * rng.uniform(0.0050, 0.0068),
                target_height * rng.uniform(0.0020, 0.0028),
                grain_material,
            )
    return branches, grains_total


def reproductive_rice_mesh(
    seed: int, target_height: float, stage_index: int
) -> tuple[Mesh, dict[str, Any]]:
    """Generate deterministic rice from heading through mature senescence."""

    if stage_index not in range(1, 5):
        raise ValueError(f"Unsupported reproductive stage: {stage_index}")
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_reproductive_v9_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    rachis_material = f"{prefix}_rachis"
    grain_material = f"{prefix}_grain"

    tiller_min = (4, 5, 5, 5)[stage_index - 1]
    tiller_max = (5, 6, 7, 7)[stage_index - 1]
    panicle_min = (2, 3, 4, 5)[stage_index - 1]
    panicle_max = (3, 4, 5, 6)[stage_index - 1]
    tiller_count = rng.randint(tiller_min, tiller_max)
    panicle_count = min(tiller_count, rng.randint(panicle_min, panicle_max))
    dominant_axis = rng.uniform(0.0, math.tau)
    total_leaves = 0
    total_branches = 0
    total_grains = 0
    widths: list[float] = []
    elevations: list[float] = []

    for tiller in range(tiller_count):
        fan_axis = dominant_axis + math.pi * tiller / max(2, tiller_count) + rng.gauss(
            0.0, math.radians(14.0)
        )
        radial = target_height * rng.uniform(0.008, 0.045)
        base = (
            radial * math.cos(fan_axis),
            radial * math.sin(fan_axis),
            0.0,
        )
        culm_height = target_height * rng.uniform(0.72, 0.82)
        lean = target_height * rng.uniform(0.015, 0.055)
        middle = (
            base[0] + 0.35 * lean * math.cos(fan_axis),
            base[1] + 0.35 * lean * math.sin(fan_axis),
            culm_height * 0.52,
        )
        top = (
            base[0] + lean * math.cos(fan_axis),
            base[1] + lean * math.sin(fan_axis),
            culm_height,
        )
        _tube_chain(
            mesh,
            [base, middle, top],
            target_height * rng.uniform(0.0062, 0.0084),
            stem_material,
            sides=10,
        )

        leaves = rng.randint(5, 8)
        total_leaves += leaves
        for leaf_index in range(leaves):
            rank = leaf_index / max(1, leaves - 1)
            side_angle = 0.0 if leaf_index % 2 == 0 else math.pi
            azimuth = fan_axis + side_angle + rng.gauss(0.0, math.radians(11.0))
            leaf_length = target_height * rng.uniform(0.33, 0.58) * (
                1.10 - 0.24 * rank
            )
            elevation_deg = rng.uniform(18.0 + 16.0 * rank, 40.0 + 20.0 * rank)
            width_ratio = rng.uniform(0.018, 0.030)
            widths.append(width_ratio)
            elevations.append(elevation_deg)
            maturity = (stage_index - 1) / 3.0
            mesh.add_blade(
                (
                    base[0] + lean * 0.4 * rank * math.cos(fan_axis),
                    base[1] + lean * 0.4 * rank * math.sin(fan_axis),
                    culm_height * (0.12 + 0.65 * rank),
                ),
                leaf_length,
                azimuth,
                math.radians(elevation_deg),
                leaf_length * width_ratio,
                rng.uniform(0.06, 0.15),
                rng.uniform(0.035, 0.095) + 0.065 * maturity,
                rng.uniform(-0.24, 0.24),
                rng.uniform(0.15, 0.26),
                leaf_material,
                midrib_material,
                segments=30,
                profile_power=0.80,
            )

        if tiller < panicle_count:
            branches, grains = _panicle(
                mesh,
                rng,
                top,
                fan_axis + rng.uniform(-0.28, 0.28),
                target_height,
                stage_index,
                rachis_material,
                grain_material,
            )
            total_branches += branches
            total_grains += grains

    mesh.scale_to_height(target_height)
    morphology = {
        "architecture": "multitiller_distichous_branched_panicle",
        "target_height_m": target_height,
        "tiller_count": tiller_count,
        "leaf_count": total_leaves,
        "panicle_count": panicle_count,
        "panicle_branch_count": total_branches,
        "grain_count": total_grains,
        "leaf_half_width_to_length_min": min(widths),
        "leaf_half_width_to_length_max": max(widths),
        "leaf_elevation_deg_min": min(elevations),
        "leaf_elevation_deg_max": max(elevations),
    }
    return mesh, morphology


def material_palette(
    seed: int, phenotype: str, stage_index: int
) -> dict[str, tuple[tuple[float, float, float], float]]:
    rng = random.Random(seed + 100_000)
    prefix = f"rice_reproductive_v9_{seed}"
    leaf_green = {
        "heading_green": (0.18, 0.46, 0.12),
        "grain_fill_transition": (0.46, 0.49, 0.14),
        "mature_senescent": (0.66, 0.49, 0.20),
    }[phenotype]
    grain = {
        "heading_green": (0.34, 0.58, 0.16),
        "grain_fill_transition": (0.62, 0.63, 0.20),
        "mature_senescent": (0.76, 0.60, 0.25),
    }[phenotype]
    jitter = rng.uniform(0.94, 1.06)

    def scaled(color: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(min(1.0, value * jitter) for value in color)

    return {
        f"{prefix}_leaf": (scaled(leaf_green), 0.42),
        f"{prefix}_midrib": (
            scaled(tuple(min(1.0, value * 1.16) for value in leaf_green)),
            0.38,
        ),
        f"{prefix}_stem": (
            scaled((0.31 + 0.07 * stage_index, 0.55, 0.18)),
            0.45,
        ),
        f"{prefix}_rachis": (
            scaled((0.43 + 0.05 * stage_index, 0.56, 0.18)),
            0.48,
        ),
        f"{prefix}_grain": (scaled(grain), 0.53),
    }


def prepare_imagegen_texture(
    source: Path, output_directory: Path, phenotype: str
) -> dict[str, Any]:
    """Color-normalize and mirror-tile one traceable image-generation output."""

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        source_dimensions = [rgb.width, rgb.height]
        crop_size = min(512, rgb.width, rgb.height)
        left = (rgb.width - crop_size) // 2
        top = (rgb.height - crop_size) // 2
        crop = np.asarray(
            rgb.crop((left, top, left + crop_size, top + crop_size)),
            dtype=np.float32,
        )
    median = np.median(crop, axis=(0, 1))
    target = np.asarray(TEXTURE_TARGET_MEDIANS[phenotype], dtype=np.float32)
    normalized = target + 0.82 * (crop - median[None, None, :])
    normalized = np.clip(normalized, 0.0, 255.0).astype(np.uint8)
    top_row = np.concatenate((normalized, normalized[:, ::-1]), axis=1)
    tile = np.concatenate((top_row, top_row[::-1]), axis=0)

    gray = (
        0.2126 * tile[:, :, 0]
        + 0.7152 * tile[:, :, 1]
        + 0.0722 * tile[:, :, 2]
    ) / 255.0
    grad_y, grad_x = np.gradient(gray)
    normal = np.dstack((-3.0 * grad_x, -3.0 * grad_y, np.ones_like(gray)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
    normal_rgb = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    # Explicit periodic borders keep both maps seam-exact under repeat wrapping.
    tile[:, -1] = tile[:, 0]
    tile[-1, :] = tile[0, :]
    normal_rgb[:, -1] = normal_rgb[:, 0]
    normal_rgb[-1, :] = normal_rgb[0, :]

    output_directory.mkdir(parents=True, exist_ok=True)
    albedo = output_directory / f"{PLANT_TYPE}_{phenotype}_albedo.png"
    normal_path = output_directory / f"{PLANT_TYPE}_{phenotype}_normal_gl.png"
    Image.fromarray(tile).save(albedo, optimize=True)
    Image.fromarray(normal_rgb).save(normal_path, optimize=True)
    return {
        "phenotype": phenotype,
        "source_filename": source.name,
        "source_sha256": sha256(source),
        "source_dimensions": source_dimensions,
        "source_center_crop": [left, top, crop_size, crop_size],
        "processing": "center_crop_512;per_channel_median_target;contrast_0.82;mirror_2x2;periodic_border",
        "target_rgb_median": list(TEXTURE_TARGET_MEDIANS[phenotype]),
        "dimensions": [1024, 1024],
        "albedo": albedo.name,
        "albedo_sha256": sha256(albedo),
        "normal_gl": normal_path.name,
        "normal_gl_sha256": sha256(normal_path),
        "albedo_edge_max_abs_difference": int(
            max(
                np.abs(tile[:, 0].astype(np.int16) - tile[:, -1].astype(np.int16)).max(),
                np.abs(tile[0].astype(np.int16) - tile[-1].astype(np.int16)).max(),
            )
        ),
        "normal_edge_max_abs_difference": int(
            max(
                np.abs(normal_rgb[:, 0].astype(np.int16) - normal_rgb[:, -1].astype(np.int16)).max(),
                np.abs(normal_rgb[0].astype(np.int16) - normal_rgb[-1].astype(np.int16)).max(),
            )
        ),
    }


def build_reproductive_assets(
    root: Path, source_root: Path
) -> dict[str, Any]:
    directory = root / "xdg/cropcraft/plants" / PLANT_TYPE
    if directory.exists():
        raise FileExistsError(directory)
    directory.mkdir(parents=True)
    textures = {
        phenotype: prepare_imagegen_texture(
            source_root / filename, directory, phenotype
        )
        for phenotype, filename in SOURCE_TEXTURES.items()
    }
    rows: list[dict[str, Any]] = []
    morphology_rows: list[dict[str, Any]] = []
    for stage_index, (stage_name, height, phenotypes) in enumerate(STAGES, start=1):
        for variant in range(1, 7):
            seed = 9100 + stage_index * 100 + variant
            mesh, morphology = reproductive_rice_mesh(seed, height, stage_index)
            source_geometry = f"rice_reproductive_v9_{stage_name}_v{variant:02d}"
            morphology_rows.append(
                {
                    "source_geometry": source_geometry,
                    "growth_stage": stage_index,
                    "growth_stage_name": stage_name,
                    **morphology,
                }
            )
            for phenotype in phenotypes:
                name = f"{source_geometry}_{phenotype}"
                row = paddy.finalize_model(
                    directory,
                    name,
                    mesh,
                    material_palette(seed, phenotype, stage_index),
                    textures[phenotype],
                )
                row.update(
                    {
                        "growth_stage": stage_index,
                        "growth_stage_name": stage_name,
                        "phenotype": phenotype,
                        "source_geometry": source_geometry,
                        "texture_provenance": "project_generated_openai_imagegen",
                        **morphology,
                    }
                )
                rows.append(row)
    write_description(directory, rows)
    return {
        "plant_type": PLANT_TYPE,
        "crop_species": SPECIES,
        "models": rows,
        "morphology_by_geometry": morphology_rows,
        "growth_stages": [stage[0] for stage in STAGES],
        "albedo_phenotypes": list(SOURCE_TEXTURES),
        "textures": [textures[name] for name in SOURCE_TEXTURES],
        "unique_geometry_sha256": sorted({row["geometry_sha256"] for row in rows}),
        "explicit_panicle_models": len(rows),
        "explicit_senescent_models": sum(
            row["phenotype"] == "mature_senescent" for row in rows
        ),
        "external_asset_bytes_acquired": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-pack", required=True)
    parser.add_argument(
        "--source-textures",
        default=str(PROJECT_ROOT / "assets/source_textures/rice_reproductive_v9"),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base_root = Path(args.base_pack).expanduser().resolve()
    source_root = Path(args.source_textures).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if not (source_root / "PROMPTS.json").is_file():
        raise FileNotFoundError(source_root / "PROMPTS.json")
    for filename in SOURCE_TEXTURES.values():
        if not (source_root / filename).is_file():
            raise FileNotFoundError(source_root / filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    base_pack = validate_base_pack(base_root)
    base_bytes = int(base_pack["inventory_bytes"])
    source_bytes = sum(path.stat().st_size for path in source_root.iterdir() if path.is_file())
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = 2 * base_bytes + 4 * source_bytes + 2 * 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-reproductive-v9-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_PADDY_R5.json")
        imagegen_provenance = provenance / "imagegen_rice_reproductive_v9"
        shutil.copytree(source_root, imagegen_provenance)

        reproductive = build_reproductive_assets(root, source_root)
        license_path = root / "LICENSES.txt"
        license_path.write_text(
            license_path.read_text(encoding="utf-8")
            + "\nRice reproductive v9 procedural geometry and generated textures\n"
            + "===============================================================\n"
            + "The OBJ geometry is a deterministic in-project procedural botanical "
            + "approximation, not a measured scan. Leaf texture source images were "
            + "generated for this project with OpenAI image generation; prompts and "
            + "unaltered outputs are retained under provenance/. They are not "
            + "relabelled as CC0. Review the applicable OpenAI output terms before "
            + "making a commercial-use claim.\n",
            encoding="utf-8",
        )

        generated = deepcopy(base_pack["generated_assets"])
        generated["reproductive_crop"] = reproductive
        paddy_assets = deepcopy(base_pack["paddy_v4_assets"])
        paddy_assets["full_cycle_extension"] = {
            "revision": "v9_r1",
            "plant_type": PLANT_TYPE,
            "isolated_factor": "late_reproductive_rice",
            "growth_stages": [stage[0] for stage in STAGES],
            "target_height_m": [stage[1] for stage in STAGES],
            "model_count": len(reproductive["models"]),
            "unique_geometries": len(reproductive["unique_geometry_sha256"]),
            "phenotypes": list(SOURCE_TEXTURES),
            "panicle_models": reproductive["explicit_panicle_models"],
            "senescent_models": reproductive["explicit_senescent_models"],
            "selection_evidence": "riceseg_condition_asset_gap_v9",
            "duckweed_added": False,
        }
        external_review = list(paddy_assets.get("external_asset_review", []))
        external_review.extend(
            [
                {
                    "source": "Sketchfab official metadata",
                    "uid": "c6715ec94cee4abfb6edbfaaa4390bea",
                    "license": "CC0-1.0",
                    "triangles": 95700,
                    "decision": "metadata_only_not_acquired",
                    "reason": "authenticated Sketchfab download required",
                },
                {
                    "source": "Sketchfab official metadata",
                    "uid": "554d18dae9a846b2beb80b6301fe0c37",
                    "license": "CC0-1.0",
                    "triangles": 165800,
                    "decision": "metadata_only_not_acquired",
                    "reason": "authenticated Sketchfab download required",
                },
            ]
        )
        paddy_assets["external_asset_review"] = external_review

        inventory = tree_inventory(root)
        excluded = {
            "pack_id",
            "created_utc",
            "purpose",
            "base_pack",
            "builder_script",
            "builder_script_sha256",
            "capacity_check",
            "generated_assets",
            "paddy_v4_assets",
            "inventory",
            "inventory_sha256",
            "inventory_bytes",
            "commercial_allowed",
            "generated_texture_license_status",
        }
        pack = {
            **{
                key: deepcopy(value)
                for key, value in base_pack.items()
                if key not in excluded
            },
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "isolated late-reproductive rice synthetic contribution gate",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "builder_script": str(Path(__file__).resolve()),
            "builder_script_sha256": sha256(__file__),
            "capacity_check": {
                "base_inventory_bytes": base_bytes,
                "source_texture_bytes": source_bytes,
                "free_bytes_before_build": free_bytes,
                "required_free_bytes": required_free,
                "passed": True,
            },
            "generated_assets": generated,
            "paddy_v4_assets": paddy_assets,
            "commercial_allowed": False,
            "generated_texture_license_status": (
                "OpenAI-generated project output; no CC0 claim; terms review required"
            ),
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(int(row["size_bytes"]) for row in inventory),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        root.replace(destination)

    payload = json.loads((destination / "PACK.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output": str(destination),
                "pack_id": payload["pack_id"],
                "pack_manifest_sha256": sha256(destination / "PACK.json"),
                "inventory_sha256": payload["inventory_sha256"],
                "inventory_bytes": payload["inventory_bytes"],
                "reproductive_models": len(
                    payload["generated_assets"]["reproductive_crop"]["models"]
                ),
                "free_bytes_before_build": free_bytes,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
