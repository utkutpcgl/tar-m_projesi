#!/usr/bin/env python3
"""Build the R4 paddy pack with sparse, distichous early-rice tillers.

R3 matched the real Rice Seedling and Weed pixel proportions, but manual review
still found overly radial, palm-like rice silhouettes.  R4 keeps every R3
surface, environment and weed asset fixed and changes only the crop geometry.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_cropcraft_agri_assets import (
    Mesh,
    canonical_sha256,
    sha256,
    tree_inventory,
    write_description,
)
from enhance_cropcraft_assets_v3 import validate_base_pack
import build_cropcraft_paddy_assets_v4 as r1


PACK_ID = "cropcraft_paddy_robust_v4_r4"
TARGET_HEIGHTS_M = (0.08, 0.11, 0.14, 0.18, 0.23)


def rice_mesh_r4(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any], dict[str, Any]]:
    """Create an asymmetric clump of botanically distichous rice tillers."""

    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_r4_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"

    base_tillers = (1, 1, 2, 2, 3)[stage - 1]
    extra_tiller = int(stage >= 4 and seed % 4 == 0)
    tiller_count = base_tillers + extra_tiller
    dominant_axis = rng.uniform(0.0, math.tau)
    axis_direction = (math.cos(dominant_axis), math.sin(dominant_axis))
    cross_direction = (-axis_direction[1], axis_direction[0])
    blade_counts: list[int] = []
    width_ratios: list[float] = []
    elevations_deg: list[float] = []
    fan_deviations_deg: list[float] = []

    for tiller in range(tiller_count):
        blade_count = (4, 4, 4, 5, 5)[stage - 1] + (
            (seed + tiller) % 2
        )
        blade_counts.append(blade_count)

        # Real young rice emerges as a compact, irregular bundle.  Offsetting
        # bases along one clump axis avoids the evenly spaced radial rosette of
        # R2/R3 while preserving natural plant-to-plant variation.
        axial_offset = target_height * rng.gauss(0.0, 0.010)
        cross_offset = target_height * rng.gauss(0.0, 0.022)
        base = (
            axial_offset * axis_direction[0]
            + cross_offset * cross_direction[0],
            axial_offset * axis_direction[1]
            + cross_offset * cross_direction[1],
            0.0,
        )
        fan_deviation = rng.gauss(0.0, math.radians(13.0))
        fan_axis = dominant_axis + fan_deviation
        fan_deviations_deg.append(math.degrees(fan_deviation))
        stem_height = target_height * rng.uniform(0.34, 0.49)
        lean_direction = fan_axis + (math.pi if rng.random() < 0.42 else 0.0)
        lean = target_height * rng.uniform(0.008, 0.030)
        top = (
            base[0] + lean * math.cos(lean_direction),
            base[1] + lean * math.sin(lean_direction),
            stem_height,
        )
        mesh.add_tube(
            base,
            top,
            target_height * 0.0085,
            target_height * 0.0048,
            10,
            stem_material,
        )

        for blade in range(blade_count):
            rank = blade / max(1, blade_count - 1)
            side = 0.0 if blade % 2 == 0 else math.pi
            azimuth = (
                fan_axis
                + side
                + rng.gauss(0.0, math.radians(6.0 + 5.0 * rank))
            )

            # Older basal leaves are longer and more arched; the youngest leaf
            # is shorter and upright.  This reproduces the long, narrow linear
            # projections visible in the 15--25 day real Rice reference frames.
            length_profile = 0.86 + 0.22 * math.sin(math.pi * rank) - 0.08 * rank
            blade_length = (
                target_height * length_profile * rng.uniform(0.91, 1.10)
            )
            elevation_low = 38.0 + 22.0 * rank
            elevation_high = 54.0 + 24.0 * rank
            elevation_deg = min(79.0, rng.uniform(elevation_low, elevation_high))
            width_ratio = rng.uniform(0.013, 0.022)
            width_ratios.append(width_ratio)
            elevations_deg.append(elevation_deg)
            mesh.add_blade(
                (
                    base[0],
                    base[1],
                    stem_height * (0.08 + 0.79 * rank),
                ),
                blade_length,
                azimuth,
                math.radians(elevation_deg),
                blade_length * width_ratio,
                rng.uniform(0.07, 0.17) * (1.08 - 0.30 * rank),
                rng.uniform(0.018, 0.090) * (1.05 - 0.32 * rank),
                rng.uniform(-0.16, 0.16),
                rng.uniform(0.14, 0.25),
                leaf_material,
                midrib_material,
                segments=44,
                profile_power=0.82,
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
        "architecture": "distichous_clumped_asymmetric",
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
    for stage, height in enumerate(TARGET_HEIGHTS_M, start=1):
        for variant in range(1, 5):
            seed = 7200 + stage * 10 + variant
            mesh, materials, morphology = rice_mesh_r4(seed, height, stage)
            source_geometry = f"rice_r4_stage{stage}_v{variant}"
            morphology_row = {
                "source_geometry": source_geometry,
                "growth_stage": stage,
                **morphology,
            }
            morphology_rows.append(morphology_row)
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
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = 2 * int(base_pack["inventory_bytes"]) + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-paddy-v4-r4-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        shutil.copy2(
            base_root / "PACK.json", provenance / "BASE_PACK_PADDY_R3.json"
        )
        crop = replace_crop_assets(root)
        generated = deepcopy(base_pack["generated_assets"])
        generated["crop"] = crop
        paddy_assets = deepcopy(base_pack["paddy_v4_assets"])
        paddy_assets.update(
            {
                "unique_crop_geometries": len(crop["unique_geometry_sha256"]),
                "refinement_revision": "r4",
                "refinement_reason": (
                    "R3 numerical smoke matched real crop/weed proportions, but "
                    "manual review rejected dense radial palm-like rice silhouettes"
                ),
                "rice_morphology_changes": [
                    "one shared but perturbed clump axis",
                    "botanically distichous alternating leaf fans",
                    "stage-conditioned one-to-four tillers",
                    "four-to-twenty-four narrow blades per plant",
                    "older arched and younger upright leaf progression",
                ],
                "rice_morphology_contract": {
                    "architecture": "distichous_clumped_asymmetric",
                    "target_age_days": [15, 25],
                    "growth_stages": 5,
                    "tiller_count": [1, 4],
                    "blade_count": [4, 24],
                    "leaf_half_width_to_length": [0.013, 0.022],
                    "reference_dataset": "Rice Seedling and Weed Dataset",
                    "reference_frames": 224,
                },
                "external_asset_review": [
                    {
                        "source": "Sketchfab official API",
                        "uid": "be6aa4ac9adc4f558cc789a0baed8ae3",
                        "license": "CC-BY-4.0",
                        "decision": "rejected",
                        "reason": "mature panicle; no textures; wrong target age",
                    },
                    {
                        "source": "Sketchfab official API",
                        "uid": "68fd8a9b358144d895e3f7838e33e2a1",
                        "license": "CC-BY-NC-4.0",
                        "decision": "rejected",
                        "reason": "non-commercial license and mature panicle",
                    },
                    {
                        "source": "Sketchfab official API",
                        "uid": "b6f400d10e1f4c55bd26e36de181444c",
                        "license": "CC-BY-4.0",
                        "decision": "rejected",
                        "reason": "single germinated grain; wrong field phenotype",
                    },
                ],
            }
        )
        inventory = tree_inventory(root)
        excluded = {
            "pack_id",
            "created_utc",
            "purpose",
            "base_pack",
            "builder_script",
            "builder_script_sha256",
            "generated_assets",
            "paddy_v4_assets",
            "inventory",
            "inventory_sha256",
            "inventory_bytes",
            "capacity_check",
        }
        pack = {
            **{
                key: deepcopy(value)
                for key, value in base_pack.items()
                if key not in excluded
            },
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "paddy-domain R4 synthetic contribution ablation",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "builder_script": str(Path(__file__).resolve()),
            "builder_script_sha256": sha256(__file__),
            "capacity_check": {
                "base_inventory_bytes": int(base_pack["inventory_bytes"]),
                "advertised_download_bytes": 0,
                "free_bytes_before_build": free_bytes,
                "required_free_bytes": required_free,
                "passed": True,
            },
            "generated_assets": generated,
            "paddy_v4_assets": paddy_assets,
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(
                int(row["size_bytes"]) for row in inventory
            ),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        root.replace(destination)

    payload = json.loads(
        (destination / "PACK.json").read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            {
                "output": str(destination),
                "pack_id": PACK_ID,
                "pack_sha256": sha256(destination / "PACK.json"),
                "builder_script_sha256": sha256(__file__),
                "free_bytes_before_build": free_bytes,
                "inventory_bytes": payload["inventory_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
