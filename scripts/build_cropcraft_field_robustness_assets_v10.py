#!/usr/bin/env python3
"""Build the asset-disjoint CropCraft field-robustness V10 pack.

The pack extends the accepted paddy R5 botany/debris pack with verified 2K
Poly Haven CC0 soil PBRs and HDRIs.  Asset families are frozen by split so a
synthetic stress score cannot benefit from seeing the same material or light
probe during training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_cropcraft_agri_assets import (
    API_ROOT,
    GROUND_CHANNELS,
    LICENSE_URL,
    USER_AGENT,
    canonical_sha256,
    download_file,
    nested,
    sha256,
    tree_inventory,
    url_json,
)


PACK_ID = "cropcraft_field_robustness_v10_r1"

EXISTING_TRAIN_GROUNDS = (
    "dry_mud_field_001",
    "brown_mud",
    "cracked_red_ground",
    "aerial_mud_1",
    "brown_mud_03",
    "muddy_tracks",
)
NEW_TRAIN_GROUNDS = (
    "raked_dirt",
    "brown_mud_02",
    "red_dirt_mud_01",
    "dirt_aerial_03",
)
VALIDATION_GROUNDS = ("brown_mud_dry", "dry_ground_01")
TEST_GROUNDS = ("red_mud_stones", "dirt_aerial_02")

EXISTING_TRAIN_ENVIRONMENTS = (
    "farm_field_puresky",
    "overcast_soil_puresky",
    "citrus_orchard_puresky",
    "pond",
    "mud_road_puresky",
    "cloudy_vondelpark",
)
NEW_TRAIN_ENVIRONMENTS = (
    "farmland_overcast",
    "harvest",
    "mealie_road",
    "kloppenheim_01_puresky",
)
VALIDATION_ENVIRONMENTS = ("dry_hay_field", "approaching_storm")
TEST_ENVIRONMENTS = ("rural_evening_road", "sunflowers_puresky")


def asset_contract() -> dict[str, dict[str, list[str]]]:
    return {
        "train": {
            "grounds": list(EXISTING_TRAIN_GROUNDS + NEW_TRAIN_GROUNDS),
            "environments": [
                f"{asset_id}_2k.hdr"
                for asset_id in EXISTING_TRAIN_ENVIRONMENTS
                + NEW_TRAIN_ENVIRONMENTS
            ],
        },
        "val": {
            "grounds": list(VALIDATION_GROUNDS),
            "environments": [
                f"{asset_id}_2k.hdr" for asset_id in VALIDATION_ENVIRONMENTS
            ],
        },
        "test": {
            "grounds": list(TEST_GROUNDS),
            "environments": [
                f"{asset_id}_2k.hdr" for asset_id in TEST_ENVIRONMENTS
            ],
        },
    }


def validate_contract(contract: dict[str, dict[str, list[str]]]) -> None:
    for kind in ("grounds", "environments"):
        roles = {role: set(values[kind]) for role, values in contract.items()}
        for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
            overlap = roles[left] & roles[right]
            if overlap:
                raise ValueError(f"{kind} overlap between {left}/{right}: {sorted(overlap)}")


def selected_downloads(
    files_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    new_grounds = NEW_TRAIN_GROUNDS + VALIDATION_GROUNDS + TEST_GROUNDS
    new_environments = (
        NEW_TRAIN_ENVIRONMENTS + VALIDATION_ENVIRONMENTS + TEST_ENVIRONMENTS
    )
    for asset_id in new_grounds:
        for output_name, path in GROUND_CHANNELS.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "kind": "ground",
                    "output_name": output_name,
                    "metadata": nested(files_by_id[asset_id], path),
                }
            )
    for asset_id in new_environments:
        rows.append(
            {
                "asset_id": asset_id,
                "kind": "environment",
                "output_name": f"{asset_id}_2k.hdr",
                "metadata": nested(files_by_id[asset_id], ("hdri", "2k", "hdr")),
            }
        )
    return rows


def source_record(asset_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
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


def reuse_verified_file(
    metadata: dict[str, Any], source: Path, output: Path
) -> dict[str, Any]:
    if source.stat().st_size != int(metadata["size"]):
        raise RuntimeError(f"Reusable file size mismatch: {source}")
    md5 = hashlib.md5(usedforsecurity=False)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            md5.update(block)
            digest.update(block)
    if md5.hexdigest() != str(metadata["md5"]):
        raise RuntimeError(f"Reusable file MD5 mismatch: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return {
        "path": output.as_posix(),
        "source_url": metadata["url"],
        "size_bytes": source.stat().st_size,
        "source_md5": metadata["md5"],
        "sha256": digest.hexdigest(),
        "reused_from_verified_partial": str(source),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-pack", required=True)
    parser.add_argument(
        "--dryland-pack",
        required=True,
        help="Validated dryland pack whose botanical families are merged",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--reuse-partial-root",
        help="Reuse already downloaded files only after API size/MD5 verification",
    )
    args = parser.parse_args()

    base_root = Path(args.base_pack).expanduser().resolve()
    dryland_root = Path(args.dryland_pack).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    reuse_root = (
        Path(args.reuse_partial_root).expanduser().resolve()
        if args.reuse_partial_root
        else None
    )
    if destination.exists():
        raise FileExistsError(destination)
    base_manifest_path = base_root / "PACK.json"
    if not base_manifest_path.is_file():
        raise FileNotFoundError(base_manifest_path)
    base_pack = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    observed_base_inventory = tree_inventory(base_root)
    if observed_base_inventory != base_pack.get("inventory"):
        raise RuntimeError("Base pack inventory does not match PACK.json")
    if canonical_sha256(observed_base_inventory) != base_pack.get("inventory_sha256"):
        raise RuntimeError("Base pack inventory digest mismatch")
    dryland_manifest_path = dryland_root / "PACK.json"
    if not dryland_manifest_path.is_file():
        raise FileNotFoundError(dryland_manifest_path)
    dryland_pack = json.loads(dryland_manifest_path.read_text(encoding="utf-8"))
    observed_dryland_inventory = tree_inventory(dryland_root)
    if observed_dryland_inventory != dryland_pack.get("inventory"):
        raise RuntimeError("Dryland pack inventory does not match PACK.json")
    if canonical_sha256(observed_dryland_inventory) != dryland_pack.get(
        "inventory_sha256"
    ):
        raise RuntimeError("Dryland pack inventory digest mismatch")

    contract = asset_contract()
    validate_contract(contract)
    selected_ids = (
        NEW_TRAIN_GROUNDS
        + VALIDATION_GROUNDS
        + TEST_GROUNDS
        + NEW_TRAIN_ENVIRONMENTS
        + VALIDATION_ENVIRONMENTS
        + TEST_ENVIRONMENTS
    )
    catalog = url_json(f"{API_ROOT}/assets")
    missing_catalog = [asset_id for asset_id in selected_ids if asset_id not in catalog]
    if missing_catalog:
        raise ValueError(f"Poly Haven assets are unavailable: {missing_catalog}")
    files_by_id = {
        asset_id: url_json(f"{API_ROOT}/files/{asset_id}")
        for asset_id in selected_ids
    }
    downloads = selected_downloads(files_by_id)
    advertised_bytes = sum(int(row["metadata"]["size"]) for row in downloads)
    base_bytes = int(base_pack["inventory_bytes"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = 2 * base_bytes + 3 * advertised_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-field-robustness-v10-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir(exist_ok=True)
        shutil.copy2(base_manifest_path, provenance / "BASE_PACK_PADDY_R5.json")
        shutil.copy2(
            dryland_manifest_path, provenance / "BOTANY_PACK_DRYLAND_V3.json"
        )

        paddy_plants = root / "xdg/cropcraft/plants"
        dryland_plants = dryland_root / "xdg/cropcraft/plants"
        merged_dryland_families: list[str] = []
        for source in sorted(dryland_plants.iterdir()):
            if not source.is_dir():
                continue
            target = paddy_plants / source.name
            if target.exists():
                raise RuntimeError(f"Botanical family collision: {source.name}")
            shutil.copytree(source, target)
            merged_dryland_families.append(source.name)
        if "sorghum_seedling_v2" not in merged_dryland_families:
            raise RuntimeError("Dryland botany merge lacks sorghum_seedling_v2")

        downloaded_rows: list[dict[str, Any]] = []
        for row in downloads:
            if row["kind"] == "ground":
                output = root / "grounds" / row["asset_id"] / row["output_name"]
            else:
                output = root / "environments" / row["output_name"]
            reusable = (
                None
                if reuse_root is None
                else reuse_root
                / (
                    Path("grounds") / row["asset_id"] / row["output_name"]
                    if row["kind"] == "ground"
                    else Path("environments") / row["output_name"]
                )
            )
            receipt = (
                reuse_verified_file(row["metadata"], reusable, output)
                if reusable is not None and reusable.is_file()
                else download_file(row["metadata"], output)
            )
            receipt.update(
                {
                    "path": output.relative_to(root).as_posix(),
                    "asset_id": row["asset_id"],
                    "kind": row["kind"],
                }
            )
            downloaded_rows.append(receipt)

        sources = deepcopy(base_pack["sources"])
        for asset_id in selected_ids:
            sources[asset_id] = source_record(asset_id, catalog[asset_id])

        license_path = root / "LICENSES.txt"
        license_path.write_text(
            license_path.read_text(encoding="utf-8")
            + "\nField robustness V10 Poly Haven inputs\n"
            + "========================================\n"
            + "Additional 2K soil PBR maps and HDRIs were fetched from the "
            + "official Poly Haven API and are CC0-1.0. "
            + f"License: {LICENSE_URL}\n",
            encoding="utf-8",
        )

        all_grounds = sorted(
            {value for role in contract.values() for value in role["grounds"]}
        )
        all_environments = sorted(
            {value for role in contract.values() for value in role["environments"]}
        )
        for ground in all_grounds:
            expected = {"diff.jpg", "rough.jpg", "nor_gl.exr", "disp.png"}
            observed = {path.name for path in (root / "grounds" / ground).iterdir()}
            if not expected <= observed:
                raise RuntimeError(f"Incomplete ground {ground}: {sorted(expected-observed)}")
        for environment in all_environments:
            if not (root / "environments" / environment).is_file():
                raise FileNotFoundError(root / "environments" / environment)

        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": (
                "asset-family-disjoint field robustness training and synthetic "
                "stress diagnostics; never a substitute for real validation"
            ),
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_manifest_path),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "dryland_botany_pack": {
                "path": str(dryland_root),
                "pack_id": dryland_pack["pack_id"],
                "pack_manifest_sha256": sha256(dryland_manifest_path),
                "inventory_sha256": dryland_pack["inventory_sha256"],
                "merged_plant_families": merged_dryland_families,
            },
            "builder_script": str(Path(__file__).resolve()),
            "builder_script_sha256": sha256(__file__),
            "mesh_provenance": base_pack.get("mesh_provenance"),
            "generated_geometry_license": base_pack.get("generated_geometry_license"),
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
            "generated_assets": deepcopy(base_pack["generated_assets"]),
            "dryland_generated_assets": deepcopy(
                dryland_pack.get("generated_assets", {})
            ),
            "paddy_v4_assets": deepcopy(base_pack.get("paddy_v4_assets", {})),
            "split_asset_contract": contract,
            "split_asset_overlap": {
                "grounds": 0,
                "environments": 0,
                "validated": True,
            },
            "surface_profiles": {
                **deepcopy(base_pack.get("surface_profiles", {})),
                "field_robustness_v10": {
                    "implementation": (
                        "provenance-recorded CropCraft field robustness patch"
                    ),
                    "semantic_surface_class": "background",
                    "soil_moisture": [0.0, 1.0],
                    "tillage_mode": [0, 3],
                    "tillage_strength": [0.0, 0.65],
                    "tillage_scale": [3.0, 24.0],
                    "tillage_angle_deg": [0.0, 180.0],
                    "clod_strength": [0.0, 0.4],
                    "clod_scale": [8.0, 65.0],
                    "environment_strength": [0.45, 4.8],
                    "sun_energy": [0.0, 5.0],
                    "sun_elevation_deg": [8.0, 82.0],
                    "sun_azimuth_deg": [0.0, 360.0],
                    "sun_angle_deg": [0.2, 12.0],
                    "local_shadow_fraction": [0.0, 0.55],
                    "artificial_light_energy": [0.0, 900.0],
                    "artificial_light_size_m": [0.08, 1.2],
                    "artificial_light_warmth": [0.0, 1.0],
                    "water_coverage": [0.0, 0.95],
                    "water_depth_m": [0.002, 0.008],
                    "water_roughness": [0.12, 0.48],
                    "wave_scale": [2.5, 14.0],
                },
            },
            "grounds": all_grounds,
            "environments": all_environments,
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(int(row["size_bytes"]) for row in inventory),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        root.replace(destination)

    built = json.loads((destination / "PACK.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output": str(destination),
                "pack_id": PACK_ID,
                "pack_sha256": sha256(destination / "PACK.json"),
                "advertised_download_bytes": advertised_bytes,
                "free_bytes_before_build": free_bytes,
                "inventory_bytes": built["inventory_bytes"],
                "split_asset_overlap": built["split_asset_overlap"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
