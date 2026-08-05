#!/usr/bin/env python3
"""Add provenance-locked alpha cutouts to R2 Bermuda reference materials."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from build_cropcraft_agri_assets import canonical_sha256, sha256, tree_inventory
from enhance_cropcraft_assets_v3 import validate_base_pack


PACK_ID = "cropcraft_soy_robust_v5_r3"
REFERENCE_FAMILY = "cynodon_dactylon_v5"
DIFFUSE_SOURCE = "grass_bermuda_01_diff_2k.jpg"
RGBA_NAME = "grass_bermuda_01_diff_alpha_v5_r3.png"
OPACITY_NAME = "grass_bermuda_01_opacity_v5_r3.png"


def build_alpha_maps(source: Path, directory: Path) -> dict[str, Any]:
    with Image.open(source) as handle:
        rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    value = rgb.max(axis=2).astype(np.float32)
    alpha = np.clip((value - 5.0) / 16.0, 0.0, 1.0)
    alpha_image = Image.fromarray(np.round(alpha * 255.0).astype(np.uint8))
    alpha_image = alpha_image.filter(ImageFilter.MaxFilter(3)).filter(
        ImageFilter.GaussianBlur(0.55)
    )
    rgba = np.dstack((rgb, np.asarray(alpha_image, dtype=np.uint8)))
    rgba_path = directory / RGBA_NAME
    opacity_path = directory / OPACITY_NAME
    Image.fromarray(rgba).save(rgba_path, optimize=True)
    alpha_image.save(opacity_path, optimize=True)
    alpha_values = np.asarray(alpha_image, dtype=np.uint8)
    return {
        "source": source.name,
        "source_sha256": sha256(source),
        "rgba": rgba_path.name,
        "rgba_sha256": sha256(rgba_path),
        "opacity": opacity_path.name,
        "opacity_sha256": sha256(opacity_path),
        "dimensions": [int(rgb.shape[1]), int(rgb.shape[0])],
        "algorithm": (
            "alpha=smoothstep(max_rgb,5,21), 3px max-filter, 0.55px blur; "
            "CC0 source RGB preserved"
        ),
        "transparent_pixel_fraction": float((alpha_values < 16).mean()),
        "opaque_pixel_fraction": float((alpha_values > 239).mean()),
    }


def rewrite_mtl(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    inserted_opacity = False
    for line in lines:
        if line.startswith("map_Kd "):
            output.append(f"map_Kd {RGBA_NAME}")
        elif line.startswith("map_d "):
            output.append(f"map_d {OPACITY_NAME}")
            inserted_opacity = True
        else:
            output.append(line)
    if not inserted_opacity:
        output.append(f"map_d {OPACITY_NAME}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


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
    if base_pack.get("pack_id") != "cropcraft_soy_robust_v5_r2":
        raise ValueError("R3 alpha refinement requires soybean v5 R2")
    free_bytes = shutil.disk_usage(destination.parent).free
    base_bytes = int(base_pack["inventory_bytes"])
    required_free = 2 * base_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-soy-v5-r3-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK_V5_R2.json")
        plant_directory = root / "xdg/cropcraft/plants" / REFERENCE_FAMILY
        alpha_receipt = build_alpha_maps(
            plant_directory / DIFFUSE_SOURCE, plant_directory
        )

        reference_rows = deepcopy(
            base_pack["soy_v5_assets"]["texture_backed_reference_models"]
        )
        by_filename = {str(row["filename"]): row for row in reference_rows}
        for row in reference_rows:
            mtl_path = plant_directory / str(row["mtl_filename"])
            rewrite_mtl(mtl_path)
            row["mtl_sha256"] = sha256(mtl_path)
            row["alpha_cutout"] = {
                "rgba": RGBA_NAME,
                "opacity": OPACITY_NAME,
                "derived_asset_receipt": "provenance/bermuda_alpha_cutout_v5_r3.json",
            }
        (provenance / "bermuda_alpha_cutout_v5_r3.json").write_text(
            json.dumps(alpha_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        generated = deepcopy(base_pack["generated_assets"])
        for row in generated["weeds"][REFERENCE_FAMILY]["models"]:
            reference = by_filename.get(str(row["filename"]))
            if reference is not None:
                row.update(reference)
        soy_assets = deepcopy(base_pack["soy_v5_assets"])
        soy_assets["texture_backed_reference_models"] = reference_rows
        previous_refinement = deepcopy(soy_assets.get("refinement", {}))
        soy_assets["refinement"] = {
            "revision": "r3",
            "r2": previous_refinement,
            "changes": [
                "derived alpha cutout from official Bermuda diffuse luminance",
                "RGBA diffuse plus explicit MTL map_d on all 21 reference variants",
            ],
            "unchanged": [
                "all OBJ geometry and UV coordinates",
                "all procedural soybean and weed geometry/textures",
                "soil PBR, HDRI, debris, source downloads and licenses",
            ],
            "alpha_receipt": "provenance/bermuda_alpha_cutout_v5_r3.json",
        }

        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "manual-visual Bermuda alpha-material refinement",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "refiner_script": str(Path(__file__).resolve()),
            "refiner_script_sha256": sha256(__file__),
            "base_refiner": {
                "path": base_pack["refiner_script"],
                "sha256": base_pack["refiner_script_sha256"],
            },
            "base_builder": deepcopy(base_pack["base_builder"]),
            "helper_scripts": deepcopy(base_pack["helper_scripts"]),
            "mesh_provenance": base_pack["mesh_provenance"],
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
