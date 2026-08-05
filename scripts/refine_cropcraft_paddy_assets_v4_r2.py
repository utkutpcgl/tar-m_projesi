#!/usr/bin/env python3
"""Refine the rejected paddy-v4 R1 rice morphology without new downloads."""

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

from build_cropcraft_agri_assets import Mesh, canonical_sha256, sha256, tree_inventory, write_description
from enhance_cropcraft_assets_v3 import validate_base_pack
import build_cropcraft_paddy_assets_v4 as r1


PACK_ID = "cropcraft_paddy_robust_v4_r2"


def rice_mesh_r2(
    seed: int, target_height: float, stage: int
) -> tuple[Mesh, dict[str, Any]]:
    """Create denser, curved rice tillers closer to the real 20-day target."""

    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_r2_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    tillers = 2 + min(3, stage // 2) + (seed % 2)
    blades_per_tiller = 4 + stage + (seed % 2)
    for tiller in range(tillers):
        azimuth = rng.uniform(0.0, math.tau)
        radial = target_height * rng.uniform(0.006, 0.028)
        base = (radial * math.cos(azimuth), radial * math.sin(azimuth), 0.0)
        stem_height = target_height * rng.uniform(0.22, 0.34)
        lean = target_height * rng.uniform(0.015, 0.055)
        top = (
            base[0] + lean * math.cos(azimuth),
            base[1] + lean * math.sin(azimuth),
            stem_height,
        )
        mesh.add_tube(
            base,
            top,
            target_height * 0.011,
            target_height * 0.006,
            10,
            stem_material,
        )
        leaf_phase = rng.uniform(0.0, math.tau)
        for blade in range(blades_per_tiller):
            maturity = (blade + 1) / blades_per_tiller
            blade_length = target_height * rng.uniform(0.90, 1.36) * (
                1.05 - 0.11 * maturity
            )
            mesh.add_blade(
                (
                    base[0],
                    base[1],
                    stem_height * (0.10 + 0.76 * maturity),
                ),
                blade_length,
                leaf_phase
                + blade * math.radians(137.5)
                + rng.uniform(-0.28, 0.28),
                math.radians(rng.uniform(30.0, 61.0)),
                blade_length * rng.uniform(0.026, 0.046),
                rng.uniform(0.10, 0.24),
                rng.uniform(0.035, 0.13),
                rng.uniform(-0.28, 0.28),
                rng.uniform(0.16, 0.30),
                leaf_material,
                midrib_material,
                segments=44,
                profile_power=0.72,
            )
    mesh.scale_to_height(target_height)
    green = rng.uniform(0.42, 0.56)
    materials = {
        leaf_material: ((green * 0.36, green, green * 0.25), 0.40),
        midrib_material: (
            (green * 0.58, min(0.78, green * 1.18), green * 0.36),
            0.36,
        ),
        stem_material: ((green * 0.56, green * 0.94, green * 0.31), 0.43),
    }
    return mesh, materials


def replace_crop_assets(root: Path) -> dict[str, Any]:
    crop_directory = root / "xdg/cropcraft/plants" / r1.CROP_TYPE
    shutil.rmtree(crop_directory)
    crop_directory.mkdir(parents=True)
    textures = {
        phenotype: r1.leaf_maps(
            r1.CROP_TYPE,
            phenotype,
            crop_directory,
            5100 + index,
        )
        for index, phenotype in enumerate(r1.CROP_PHENOTYPES)
    }
    rows: list[dict[str, Any]] = []
    heights = (0.08, 0.11, 0.14, 0.18, 0.23)
    for stage, height in enumerate(heights, start=1):
        for variant in range(1, 5):
            seed = 5200 + stage * 10 + variant
            mesh, materials = rice_mesh_r2(seed, height, stage)
            source_geometry = f"rice_r2_stage{stage}_v{variant}"
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
                    }
                )
                rows.append(row)
    write_description(crop_directory, rows)
    return {
        "plant_type": r1.CROP_TYPE,
        "models": rows,
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
        prefix="cropcraft-paddy-v4-r2-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_PADDY_R1.json")
        crop = replace_crop_assets(root)
        generated = deepcopy(base_pack["generated_assets"])
        generated["crop"] = crop
        paddy_assets = deepcopy(base_pack["paddy_v4_assets"])
        paddy_assets.update(
            {
                "unique_crop_geometries": len(crop["unique_geometry_sha256"]),
                "refinement_revision": "r2",
                "refinement_reason": (
                    "R1 manual smoke rejection: radial upright rice morphology, "
                    "low crop coverage and excessive water mirror response"
                ),
                "rice_morphology_changes": [
                    "more tillers",
                    "longer and wider blades",
                    "lower elevation and stronger arch/droop",
                    "less radial symmetry",
                ],
            }
        )
        surface_profiles = deepcopy(base_pack["surface_profiles"])
        surface_profiles["shallow_paddy_v4"].update(
            {
                "water_roughness": [0.16, 0.38],
                "environment_strength": [2.0, 3.4],
                "shader_revision": "r2_turbid_low_mirror",
            }
        )
        inventory = tree_inventory(root)
        pack = {
            **{
                key: deepcopy(value)
                for key, value in base_pack.items()
                if key
                not in {
                    "pack_id",
                    "created_utc",
                    "purpose",
                    "base_pack",
                    "builder_script",
                    "builder_script_sha256",
                    "generated_assets",
                    "paddy_v4_assets",
                    "surface_profiles",
                    "inventory",
                    "inventory_sha256",
                    "inventory_bytes",
                    "capacity_check",
                }
            },
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "paddy-domain R2 synthetic contribution ablation",
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
            "surface_profiles": surface_profiles,
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
                "pack_id": PACK_ID,
                "pack_sha256": sha256(destination / "PACK.json"),
                "free_bytes_before_build": free_bytes,
                "inventory_bytes": payload["inventory_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
