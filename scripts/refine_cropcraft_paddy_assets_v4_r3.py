#!/usr/bin/env python3
"""Build paddy-v4 R3 with tiller-local fan leaves after R2 smoke rejection."""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from build_cropcraft_agri_assets import Mesh, sha256, write_description
import refine_cropcraft_paddy_assets_v4_r2 as r2


PACK_ID = "cropcraft_paddy_robust_v4_r3"


def rice_mesh_r3(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_r3_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    tillers = 1 + min(2, (stage + 1) // 2) + (seed % 2)
    blades_per_tiller = 3 + stage + (seed % 2)
    clump_axis = rng.uniform(0.0, math.tau)
    for tiller in range(tillers):
        tiller_axis = (
            clump_axis
            + tiller * math.pi / max(1, tillers)
            + rng.uniform(-0.35, 0.35)
        )
        radial = target_height * rng.uniform(0.004, 0.022)
        base = (
            radial * math.cos(tiller_axis),
            radial * math.sin(tiller_axis),
            0.0,
        )
        stem_height = target_height * rng.uniform(0.22, 0.34)
        lean = target_height * rng.uniform(0.010, 0.040)
        top = (
            base[0] + lean * math.cos(tiller_axis),
            base[1] + lean * math.sin(tiller_axis),
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
        fan_axis = tiller_axis + rng.uniform(-0.25, 0.25)
        for blade in range(blades_per_tiller):
            maturity = (blade + 1) / blades_per_tiller
            side = 0.0 if blade % 2 == 0 else math.pi
            spread = (blade // 2) * rng.uniform(0.045, 0.105)
            azimuth = fan_axis + side + (spread if blade % 2 == 0 else -spread)
            azimuth += rng.uniform(-0.13, 0.13)
            blade_length = target_height * rng.uniform(0.88, 1.30) * (
                1.04 - 0.10 * maturity
            )
            mesh.add_blade(
                (
                    base[0],
                    base[1],
                    stem_height * (0.12 + 0.74 * maturity),
                ),
                blade_length,
                azimuth,
                math.radians(rng.uniform(29.0, 59.0)),
                blade_length * rng.uniform(0.027, 0.046),
                rng.uniform(0.11, 0.24),
                rng.uniform(0.045, 0.14),
                rng.uniform(-0.20, 0.20),
                rng.uniform(0.17, 0.29),
                leaf_material,
                midrib_material,
                segments=44,
                profile_power=0.72,
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
    return mesh, materials


def replace_crop_assets_r3(root: Path) -> dict[str, Any]:
    crop_directory = root / "xdg/cropcraft/plants" / r2.r1.CROP_TYPE
    import shutil

    shutil.rmtree(crop_directory)
    crop_directory.mkdir(parents=True)
    textures = {
        phenotype: r2.r1.leaf_maps(
            r2.r1.CROP_TYPE,
            phenotype,
            crop_directory,
            6100 + index,
        )
        for index, phenotype in enumerate(r2.r1.CROP_PHENOTYPES)
    }
    rows: list[dict[str, Any]] = []
    for stage, height in enumerate((0.08, 0.11, 0.14, 0.18, 0.23), start=1):
        for variant in range(1, 5):
            seed = 6200 + stage * 10 + variant
            mesh, materials = rice_mesh_r3(seed, height, stage)
            source_geometry = f"rice_r3_stage{stage}_v{variant}"
            for phenotype in r2.r1.CROP_PHENOTYPES:
                name = f"{source_geometry}_{phenotype}"
                row = r2.r1.finalize_model(
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
                    }
                )
                rows.append(row)
    write_description(crop_directory, rows)
    return {
        "plant_type": r2.r1.CROP_TYPE,
        "models": rows,
        "albedo_phenotypes": list(r2.r1.CROP_PHENOTYPES),
        "textures": list(textures.values()),
        "unique_geometry_sha256": sorted(
            {row["geometry_sha256"] for row in rows}
        ),
    }


def main() -> None:
    r2.PACK_ID = PACK_ID
    r2.rice_mesh_r2 = rice_mesh_r3
    r2.replace_crop_assets = replace_crop_assets_r3
    r2.main()
    output_index = sys.argv.index("--output") + 1
    destination = Path(sys.argv[output_index]).expanduser().resolve()
    manifest_path = destination / "PACK.json"
    pack = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack["purpose"] = "paddy-domain R3 synthetic contribution ablation"
    pack["builder_script"] = str(Path(__file__).resolve())
    pack["builder_script_sha256"] = sha256(__file__)
    pack["paddy_v4_assets"].update(
        {
            "refinement_revision": "r3",
            "refinement_reason": (
                "R2 smoke rejected for 0.288 crop fraction, radial rosette-like "
                "rice clumps and 0.083 weed-free frame fraction"
            ),
            "rice_morphology_changes": [
                "tiller-local alternating leaf fans",
                "intermediate tiller and blade counts",
                "long curved strap leaves without radial rosette layout",
            ],
        }
    )
    pack["surface_profiles"]["shallow_paddy_v4"].update(
        {
            "environment_strength": [3.3, 4.7],
            "shader_revision": "r2_turbid_low_mirror_with_r3_exposure_range",
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
