#!/usr/bin/env python3
"""Build R5: a denser early-rice clump while retaining R4's linear habit."""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from build_cropcraft_agri_assets import Mesh, sha256, write_description
import build_cropcraft_paddy_assets_v4 as r1
import refine_cropcraft_paddy_assets_v4_r4 as r4


PACK_ID = "cropcraft_paddy_robust_v4_r5"


def rice_mesh_r5(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any], dict[str, Any]]:
    """Generate multi-tiller rice between R3's rosette and R4's wispy fan."""

    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_r5_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    tiller_count = (2, 2, 3, 3, 4)[stage - 1] + int(
        stage >= 2 and seed % 4 == 0
    )
    dominant_axis = rng.uniform(0.0, math.tau)
    axis_direction = (math.cos(dominant_axis), math.sin(dominant_axis))
    cross_direction = (-axis_direction[1], axis_direction[0])
    blade_counts: list[int] = []
    width_ratios: list[float] = []
    elevations_deg: list[float] = []
    fan_deviations_deg: list[float] = []

    for tiller in range(tiller_count):
        blade_count = (5, 5, 5, 6, 6)[stage - 1] + (
            (seed + tiller) % 2
        )
        blade_counts.append(blade_count)
        axial_offset = target_height * rng.gauss(0.0, 0.014)
        cross_offset = target_height * rng.gauss(0.0, 0.030)
        base = (
            axial_offset * axis_direction[0]
            + cross_offset * cross_direction[0],
            axial_offset * axis_direction[1]
            + cross_offset * cross_direction[1],
            0.0,
        )
        fan_deviation = rng.gauss(0.0, math.radians(22.0))
        fan_axis = dominant_axis + fan_deviation
        fan_deviations_deg.append(math.degrees(fan_deviation))
        stem_height = target_height * rng.uniform(0.32, 0.47)
        lean_direction = fan_axis + (math.pi if rng.random() < 0.44 else 0.0)
        lean = target_height * rng.uniform(0.010, 0.038)
        top = (
            base[0] + lean * math.cos(lean_direction),
            base[1] + lean * math.sin(lean_direction),
            stem_height,
        )
        mesh.add_tube(
            base,
            top,
            target_height * 0.0095,
            target_height * 0.0052,
            10,
            stem_material,
        )

        for blade in range(blade_count):
            rank = blade / max(1, blade_count - 1)
            side = 0.0 if blade % 2 == 0 else math.pi
            azimuth = (
                fan_axis
                + side
                + rng.gauss(0.0, math.radians(10.0 + 8.0 * rank))
            )
            length_profile = 0.95 + 0.25 * math.sin(math.pi * rank) - 0.06 * rank
            blade_length = (
                target_height * length_profile * rng.uniform(0.96, 1.15)
            )
            elevation_low = 32.0 + 18.0 * rank
            elevation_high = 50.0 + 23.0 * rank
            elevation_deg = min(74.0, rng.uniform(elevation_low, elevation_high))
            width_ratio = rng.uniform(0.023, 0.038)
            width_ratios.append(width_ratio)
            elevations_deg.append(elevation_deg)
            mesh.add_blade(
                (
                    base[0],
                    base[1],
                    stem_height * (0.07 + 0.80 * rank),
                ),
                blade_length,
                azimuth,
                math.radians(elevation_deg),
                blade_length * width_ratio,
                rng.uniform(0.08, 0.19) * (1.08 - 0.28 * rank),
                rng.uniform(0.025, 0.100) * (1.06 - 0.30 * rank),
                rng.uniform(-0.20, 0.20),
                rng.uniform(0.14, 0.25),
                leaf_material,
                midrib_material,
                segments=44,
                profile_power=0.80,
            )

    mesh.scale_to_height(target_height)
    green = rng.uniform(0.43, 0.56)
    materials = {
        leaf_material: ((green * 0.36, green, green * 0.25), 0.40),
        midrib_material: (
            (green * 0.58, min(0.78, green * 1.18), green * 0.36),
            0.36,
        ),
        stem_material: ((green * 0.56, green * 0.94, green * 0.31), 0.43),
    }
    morphology = {
        "architecture": "multitiller_distichous_clumped_asymmetric",
        "target_height_m": target_height,
        "tiller_count": tiller_count,
        "blade_count": sum(blade_counts),
        "blades_per_tiller": blade_counts,
        "leaf_half_width_to_length_min": min(width_ratios),
        "leaf_half_width_to_length_max": max(width_ratios),
        "leaf_elevation_deg_min": min(elevations_deg),
        "leaf_elevation_deg_max": max(elevations_deg),
        "tiller_fan_deviation_deg_min": min(fan_deviations_deg),
        "tiller_fan_deviation_deg_max": max(fan_deviations_deg),
    }
    return mesh, materials, morphology


def replace_crop_assets(root: Path) -> dict[str, Any]:
    import shutil

    crop_directory = root / "xdg/cropcraft/plants" / r1.CROP_TYPE
    shutil.rmtree(crop_directory)
    crop_directory.mkdir(parents=True)
    textures = {
        phenotype: r1.leaf_maps(
            r1.CROP_TYPE,
            phenotype,
            crop_directory,
            6100 + index,
        )
        for index, phenotype in enumerate(r1.CROP_PHENOTYPES)
    }
    rows: list[dict[str, Any]] = []
    morphology_rows: list[dict[str, Any]] = []
    for stage, height in enumerate(r4.TARGET_HEIGHTS_M, start=1):
        for variant in range(1, 5):
            seed = 8200 + stage * 10 + variant
            mesh, materials, morphology = rice_mesh_r5(seed, height, stage)
            source_geometry = f"rice_r5_stage{stage}_v{variant}"
            morphology_rows.append(
                {
                    "source_geometry": source_geometry,
                    "growth_stage": stage,
                    **morphology,
                }
            )
            for phenotype in r1.CROP_PHENOTYPES:
                name = f"{source_geometry}_{phenotype}"
                row = r1.finalize_model(
                    crop_directory,
                    name,
                    mesh,
                    materials,
                    textures[phenotype],
                )
                row.update(
                    {
                        "growth_stage": stage,
                        "phenotype": phenotype,
                        "source_geometry": source_geometry,
                        **morphology,
                    }
                )
                rows.append(row)
    write_description(crop_directory, rows)
    return {
        "plant_type": r1.CROP_TYPE,
        "models": rows,
        "morphology_by_geometry": morphology_rows,
        "albedo_phenotypes": list(r1.CROP_PHENOTYPES),
        "textures": list(textures.values()),
        "unique_geometry_sha256": sorted(
            {row["geometry_sha256"] for row in rows}
        ),
    }


def main() -> None:
    r4.PACK_ID = PACK_ID
    r4.replace_crop_assets = replace_crop_assets
    r4.main()
    output_index = sys.argv.index("--output") + 1
    destination = Path(sys.argv[output_index]).expanduser().resolve()
    manifest_path = destination / "PACK.json"
    pack = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack["purpose"] = "paddy-domain R5 synthetic contribution ablation"
    pack["builder_script"] = str(Path(__file__).resolve())
    pack["builder_script_sha256"] = sha256(__file__)
    pack["paddy_v4_assets"].update(
        {
            "refinement_revision": "r5",
            "refinement_reason": (
                "R4 manual morphology improved but actual-pixel smoke rejected "
                "0.0211 crop fraction against the frozen 0.025 floor and 0.108 "
                "real mean target"
            ),
            "rice_morphology_changes": [
                "retain asymmetric distichous leaf habit",
                "two-to-five stage-conditioned tillers",
                "ten-to-thirty-three narrow blades per plant",
                "moderately wider and lower leaves than R4",
                "larger tiller-axis variance to avoid line-like silhouettes",
            ],
            "rice_morphology_contract": {
                "architecture": "multitiller_distichous_clumped_asymmetric",
                "target_age_days": [15, 25],
                "growth_stages": 5,
                "tiller_count": [2, 5],
                "blade_count": [10, 35],
                "leaf_half_width_to_length": [0.023, 0.038],
                "reference_dataset": "Rice Seedling and Weed Dataset",
                "reference_frames": 224,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(destination),
                "final_pack_id": pack["pack_id"],
                "final_pack_sha256": sha256(manifest_path),
                "builder_script_sha256": pack["builder_script_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
