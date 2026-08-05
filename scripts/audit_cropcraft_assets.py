#!/usr/bin/env python3
"""Audit stock and custom CropCraft assets against a frozen quality gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

import yaml
from PIL import Image


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def obj_stats(path: Path) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    faces = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                values = line.split()
                vertices.append(tuple(float(value) for value in values[1:4]))
            elif line.startswith("f "):
                faces += 1
    if not vertices:
        raise ValueError(f"OBJ has no vertices: {path}")
    minimum = tuple(min(vertex[index] for vertex in vertices) for index in range(3))
    maximum = tuple(max(vertex[index] for vertex in vertices) for index in range(3))
    return {
        "path": str(path),
        "vertices": len(vertices),
        "faces": faces,
        "bounds_min_m": list(minimum),
        "bounds_max_m": list(maximum),
        "height_m": maximum[2] - minimum[2],
        "width_m": max(maximum[0] - minimum[0], maximum[1] - minimum[1]),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def obj_geometry_sha256(path: Path) -> str:
    """Hash only positions and topology, ignoring material/UV variants."""

    rows: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                rows.append(line.strip())
            elif line.startswith("f "):
                indexes = [token.split("/")[0] for token in line.split()[1:]]
                rows.append("f " + " ".join(indexes))
    if not rows:
        raise ValueError(f"OBJ has no hashable geometry: {path}")
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


def summarize_models(rows: list[dict[str, Any]]) -> dict[str, Any]:
    face_counts = [int(row["faces"]) for row in rows]
    vertex_counts = [int(row["vertices"]) for row in rows]
    return {
        "models": len(rows),
        "faces": {
            "min": min(face_counts),
            "median": statistics.median(face_counts),
            "max": max(face_counts),
        },
        "vertices": {
            "min": min(vertex_counts),
            "median": statistics.median(vertex_counts),
            "max": max(vertex_counts),
        },
        "bytes": sum(int(row["size_bytes"]) for row in rows),
    }


def texture_inventory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".exr",
            ".hdr",
        }:
            continue
        dimensions = None
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            with Image.open(path) as image:
                dimensions = list(image.size)
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "dimensions": dimensions,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return rows


def stock_audit(repository: Path, release: Path) -> dict[str, Any]:
    plants_root = repository / "assets/plants"
    groups: dict[str, Any] = {}
    for directory in sorted(path for path in plants_root.iterdir() if path.is_dir()):
        models = [obj_stats(path) for path in sorted(directory.glob("*.obj"))]
        if models:
            groups[directory.name] = {
                "summary": summarize_models(models),
                "models": models,
            }
    used_crop_models: dict[str, int] = {}
    for description_path in sorted(release.glob("scenes/*/field_description.json")):
        description = load_object(description_path)
        for bed in description.get("field", {}).get("beds", []):
            for row in bed.get("rows", []):
                for crop in row.get("crops", []):
                    filename = str(crop["filename"])
                    used_crop_models[filename] = used_crop_models.get(filename, 0) + 1
    return {
        "repository": str(repository),
        "repository_revision": (
            "7128cd2acade50cc4a5a1761210b55989ab62527"
        ),
        "plant_groups": groups,
        "crop_group": "maize",
        "crop_summary": groups["maize"]["summary"],
        "weed_groups_used": ["portulaca", "polygonum", "taraxacum"],
        "weed_models_used_available": sum(
            groups[name]["summary"]["models"]
            for name in ("portulaca", "polygonum", "taraxacum")
        ),
        "used_crop_model_counts": used_crop_models,
        "used_crop_model_variants": len(used_crop_models),
        "ground_families": 1,
        "environment_families": 1,
        "background_stone_models": len(
            list((repository / "assets/stones").glob("*.obj"))
        ),
        "textures": texture_inventory(repository / "assets"),
        "license_status": (
            "generator Apache-2.0; bundled asset provenance not itemized upstream"
        ),
        "commercial_allowed": False,
    }


def actual_tree_inventory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Unexpected asset-pack symlink: {path}")
        if path.is_file() and path.name != "PACK.json":
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return rows


def custom_audit(pack_root: Path, gate: dict[str, Any]) -> dict[str, Any]:
    pack = load_object(pack_root / "PACK.json")
    inventory = actual_tree_inventory(pack_root)
    pack_gate = gate["asset_pack_gate"]
    plants_root = pack_root / "xdg/cropcraft/plants"
    groups: dict[str, Any] = {}
    height_errors: list[float] = []
    for directory in sorted(path for path in plants_root.iterdir() if path.is_dir()):
        description = load_object(directory / "description.yaml")
        declared = {
            str(row["filename"]): float(row["height"])
            for row in description["models"]
        }
        models = []
        for path in sorted(directory.glob("*.obj")):
            row = obj_stats(path)
            row["geometry_sha256"] = obj_geometry_sha256(path)
            declared_height = declared[path.name]
            relative_error = abs(row["height_m"] - declared_height) / declared_height
            row["declared_height_m"] = declared_height
            row["declared_height_relative_error"] = relative_error
            height_errors.append(relative_error)
            models.append(row)
        groups[directory.name] = {
            "summary": summarize_models(models),
            "models": models,
        }
    crop_type = str(pack_gate["crop_plant_type"])
    weed_types = [str(value) for value in pack_gate["weed_plant_types"]]
    generated = pack["generated_assets"]
    download_metadata_complete = all(
        row.get("source_url") and row.get("sha256") for row in pack["downloads"]
    )
    checks = {
        "inventory_exact": inventory == pack.get("inventory"),
        "inventory_digest": canonical_sha256(inventory)
        == pack.get("inventory_sha256"),
        "minimum_crop_models": groups[crop_type]["summary"]["models"]
        >= int(pack_gate["minimum_crop_models"]),
        "minimum_crop_growth_stages": len(
            {row["growth_stage"] for row in generated["crop"]["models"]}
        )
        >= int(pack_gate["minimum_crop_growth_stages"]),
        "minimum_faces_per_crop_model": groups[crop_type]["summary"]["faces"]["min"]
        >= int(pack_gate["minimum_faces_per_crop_model"]),
        "weed_types_present": set(weed_types) <= set(groups),
        "minimum_models_per_weed_type": min(
            groups[name]["summary"]["models"] for name in weed_types
        )
        >= int(pack_gate["minimum_models_per_weed_type"]),
        "minimum_background_debris_models": len(
            generated["background_debris"]
        )
        >= int(pack_gate["minimum_background_debris_models"]),
        "maximum_degenerate_faces": max(
            row["degenerate_faces"]
            for section in (
                generated["crop"]["models"],
                *(value["models"] for value in generated["weeds"].values()),
                generated["background_debris"],
            )
            for row in section
        )
        <= int(pack_gate["maximum_degenerate_faces_per_model"]),
        "declared_height_accuracy": max(height_errors)
        <= float(pack_gate["maximum_declared_height_relative_error"]),
        "ground_families": len(pack["grounds"])
        >= int(pack_gate["required_ground_families"]),
        "environment_families": len(pack["environments"])
        >= int(pack_gate["required_environment_families"]),
        "third_party_license": pack["third_party_license"]
        in pack_gate["accepted_third_party_asset_licenses"],
        "download_hashes_and_urls": download_metadata_complete,
        "capacity_check": pack["capacity_check"].get("passed") is True,
    }
    v3_assets = pack.get("v3_assets")
    if isinstance(v3_assets, dict):
        crop_models = groups[crop_type]["models"]
        source_ids = {
            str(value) for value in v3_assets.get("polyhaven_plant_sources", [])
        }
        texture_backed = v3_assets.get("texture_backed_weed_models", [])
        roles_by_source: dict[str, set[str]] = {
            source_id: set() for source_id in source_ids
        }
        for row in pack.get("downloads", []):
            asset_id = str(row.get("asset_id", ""))
            if asset_id in roles_by_source and row.get("role"):
                roles_by_source[asset_id].add(str(row["role"]))
        required_roles = {
            str(value)
            for value in pack_gate.get("required_reference_texture_roles", [])
        }
        crop_mtl_paths = [
            path.with_suffix(".mtl")
            for path in sorted((plants_root / crop_type).glob("*.obj"))
        ]
        texture_mapped_crop_models = sum(
            "map_Kd " in path.read_text(encoding="utf-8", errors="replace")
            for path in crop_mtl_paths
        )
        reference_materials_complete = True
        for model in texture_backed if isinstance(texture_backed, list) else []:
            family = str(model.get("target_family", ""))
            mtl_name = str(model.get("mtl_filename", ""))
            mtl_path = plants_root / family / mtl_name
            if not mtl_path.is_file():
                reference_materials_complete = False
                continue
            material_lines = mtl_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            map_lines = [
                line
                for line in material_lines
                if line.startswith("map_Kd ") or line.startswith("map_Bump ")
            ]
            if not any(line.startswith("map_Kd ") for line in map_lines):
                reference_materials_complete = False
            for line in map_lines:
                texture_name = line.split()[-1]
                if not (mtl_path.parent / texture_name).is_file():
                    reference_materials_complete = False
        checks.update(
            {
                "minimum_unique_crop_geometries": len(
                    {row["geometry_sha256"] for row in crop_models}
                )
                >= int(pack_gate.get("minimum_unique_crop_geometries", 0)),
                "minimum_crop_albedo_phenotypes": len(
                    v3_assets.get("crop_albedo_phenotypes", [])
                )
                >= int(pack_gate.get("minimum_crop_albedo_phenotypes", 0)),
                "crop_models_are_texture_mapped": texture_mapped_crop_models
                == len(crop_models),
                "minimum_cc0_reference_model_sources": len(source_ids)
                >= int(pack_gate.get("minimum_cc0_reference_model_sources", 0)),
                "minimum_texture_backed_weed_models": isinstance(
                    texture_backed, list
                )
                and len(texture_backed)
                >= int(pack_gate.get("minimum_texture_backed_weed_models", 0)),
                "required_reference_texture_roles": all(
                    required_roles <= roles for roles in roles_by_source.values()
                ),
                "reference_sources_are_cc0": all(
                    pack.get("sources", {}).get(source_id, {}).get("license")
                    == "CC0-1.0"
                    for source_id in source_ids
                ),
                "reference_material_texture_files_exist": (
                    reference_materials_complete
                ),
            }
        )

    paddy_assets = pack.get("paddy_v4_assets")
    if isinstance(paddy_assets, dict):
        crop_models = groups[crop_type]["models"]
        crop_mtls = [
            path.with_suffix(".mtl")
            for path in sorted((plants_root / crop_type).glob("*.obj"))
        ]
        weed_mtls = [
            path.with_suffix(".mtl")
            for family in weed_types
            for path in sorted((plants_root / family).glob("*.obj"))
        ]

        def material_maps_exist(path: Path) -> bool:
            if not path.is_file():
                return False
            map_lines = [
                line
                for line in path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if line.startswith("map_Kd ") or line.startswith("map_Bump ")
            ]
            return (
                any(line.startswith("map_Kd ") for line in map_lines)
                and any(line.startswith("map_Bump ") for line in map_lines)
                and all(
                    (path.parent / line.split()[-1]).is_file()
                    for line in map_lines
                )
            )

        wet_ground_ids = {
            str(value) for value in paddy_assets.get("wet_ground_families", [])
        }
        paddy_environment_ids = {
            str(value) for value in paddy_assets.get("paddy_environments", [])
        }
        surface_profile = str(paddy_assets.get("surface_profile", ""))
        checks.update(
            {
                "paddy_minimum_unique_crop_geometries": len(
                    {row["geometry_sha256"] for row in crop_models}
                )
                >= int(pack_gate.get("minimum_unique_crop_geometries", 0)),
                "paddy_minimum_crop_albedo_phenotypes": len(
                    paddy_assets.get("crop_albedo_phenotypes", [])
                )
                >= int(pack_gate.get("minimum_crop_albedo_phenotypes", 0)),
                "paddy_crop_material_maps_exist": all(
                    material_maps_exist(path) for path in crop_mtls
                ),
                "paddy_weed_material_maps_exist": all(
                    material_maps_exist(path) for path in weed_mtls
                ),
                "paddy_minimum_texture_backed_weed_models": len(weed_mtls)
                >= int(pack_gate.get("minimum_texture_backed_weed_models", 0)),
                "paddy_wet_ground_families": len(wet_ground_ids)
                >= int(pack_gate.get("minimum_wet_ground_families", 0)),
                "paddy_environment_families": len(paddy_environment_ids)
                >= int(pack_gate.get("minimum_paddy_environment_families", 0)),
                "paddy_surface_profile_declared": surface_profile
                == str(pack_gate.get("required_surface_profile", ""))
                and surface_profile in pack.get("surface_profiles", {}),
                "paddy_required_crop_species": str(
                    paddy_assets.get("crop_species", "")
                )
                == str(pack_gate.get("required_crop_species", "")),
                "paddy_required_weed_species": str(
                    paddy_assets.get("primary_weed_species", "")
                )
                == str(pack_gate.get("required_primary_weed_species", "")),
            }
        )

    soy_assets = pack.get("soy_v5_assets")
    if isinstance(soy_assets, dict):
        crop_models = groups[crop_type]["models"]
        crop_mtls = [
            path.with_suffix(".mtl")
            for path in sorted((plants_root / crop_type).glob("*.obj"))
        ]
        weed_mtls = [
            path.with_suffix(".mtl")
            for family in weed_types
            for path in sorted((plants_root / family).glob("*.obj"))
        ]

        def soy_material_maps_exist(path: Path) -> bool:
            if not path.is_file():
                return False
            map_lines = [
                line
                for line in path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if line.startswith("map_Kd ") or line.startswith("map_Bump ")
            ]
            return (
                any(line.startswith("map_Kd ") for line in map_lines)
                and any(line.startswith("map_Bump ") for line in map_lines)
                and all(
                    (path.parent / line.split()[-1]).is_file()
                    for line in map_lines
                )
            )

        reference_sources = {
            str(value)
            for value in soy_assets.get("exact_species_reference_sources", [])
        }
        reference_models = soy_assets.get("texture_backed_reference_models", [])
        if not isinstance(reference_models, list):
            reference_models = []
        roles_by_source: dict[str, set[str]] = {
            source_id: set() for source_id in reference_sources
        }
        for row in pack.get("downloads", []):
            asset_id = str(row.get("asset_id", ""))
            if asset_id in roles_by_source and row.get("role"):
                roles_by_source[asset_id].add(str(row["role"]))
        required_roles = {
            str(value)
            for value in pack_gate.get("required_reference_texture_roles", [])
        }
        stage_traits = soy_assets.get("stage_trait_contract", {})
        required_species = {
            str(value) for value in pack_gate.get("required_weed_species", [])
        }
        maximum_reference_ratio = float(
            pack_gate.get("maximum_reference_width_height_ratio", math.inf)
        )
        reference_ratios = [
            float(row["width_m"]) / float(row["height_m"])
            for row in reference_models
            if float(row.get("height_m", 0.0)) > 0.0
        ]
        reference_materials_complete = True
        for row in reference_models:
            family = str(row.get("target_family", ""))
            mtl_name = str(row.get("mtl_filename", ""))
            if not soy_material_maps_exist(plants_root / family / mtl_name):
                reference_materials_complete = False
        checks.update(
            {
                "soy_minimum_unique_crop_geometries": len(
                    {row["geometry_sha256"] for row in crop_models}
                )
                >= int(pack_gate.get("minimum_unique_crop_geometries", 0)),
                "soy_minimum_crop_albedo_phenotypes": len(
                    soy_assets.get("crop_albedo_phenotypes", [])
                )
                >= int(pack_gate.get("minimum_crop_albedo_phenotypes", 0)),
                "soy_crop_material_maps_exist": all(
                    soy_material_maps_exist(path) for path in crop_mtls
                ),
                "soy_weed_material_maps_exist": all(
                    soy_material_maps_exist(path) for path in weed_mtls
                ),
                "soy_minimum_texture_backed_reference_models": len(
                    reference_models
                )
                >= int(pack_gate.get("minimum_texture_backed_weed_models", 0)),
                "soy_minimum_exact_species_reference_sources": len(
                    reference_sources
                )
                >= int(pack_gate.get("minimum_exact_species_reference_sources", 0)),
                "soy_required_reference_texture_roles": all(
                    required_roles <= roles for roles in roles_by_source.values()
                ),
                "soy_reference_sources_are_cc0": all(
                    pack.get("sources", {}).get(source_id, {}).get("license")
                    == "CC0-1.0"
                    for source_id in reference_sources
                ),
                "soy_reference_material_texture_files_exist": (
                    reference_materials_complete
                ),
                "soy_reference_width_height_ratio": bool(reference_ratios)
                and max(reference_ratios) <= maximum_reference_ratio,
                "soy_required_crop_species": str(
                    soy_assets.get("crop_species", "")
                )
                == str(pack_gate.get("required_crop_species", "")),
                "soy_required_weed_species": required_species
                <= {str(value) for value in soy_assets.get("weed_species", [])},
                "soy_final_stage_trifoliolate_nodes": int(
                    stage_traits.get("minimum_final_stage_trifoliolate_nodes", 0)
                )
                >= int(pack_gate.get("minimum_final_stage_trifoliolate_nodes", 0)),
                "soy_cotyledon_and_unifoliolate_stage_traits": (
                    not bool(
                        pack_gate.get(
                            "require_cotyledon_and_unifoliolate_stage_traits",
                            False,
                        )
                    )
                    or (
                        stage_traits.get("cotyledon_stage_present") is True
                        and stage_traits.get("unifoliolate_stage_present") is True
                    )
                ),
                "soy_zero_real_growingsoy_asset_exposure": int(
                    soy_assets.get("real_growingsoy_training_or_asset_exposure", -1)
                )
                == 0,
            }
        )
    return {
        "pack": str(pack_root),
        "pack_id": pack["pack_id"],
        "pack_manifest_sha256": sha256(pack_root / "PACK.json"),
        "inventory_sha256": canonical_sha256(inventory),
        "inventory_files": len(inventory),
        "inventory_bytes": sum(row["size_bytes"] for row in inventory),
        "plant_groups": groups,
        "crop_summary": groups[crop_type]["summary"],
        "weed_types": weed_types,
        "weed_models": sum(groups[name]["summary"]["models"] for name in weed_types),
        "background_debris_models": len(generated["background_debris"]),
        "ground_families": len(pack["grounds"]),
        "environment_families": len(pack["environments"]),
        "maximum_declared_height_relative_error": max(height_errors),
        "license_status": (
            "procedural geometry CC0-1.0; Poly Haven CC0-1.0"
            if not isinstance(v3_assets, dict)
            else "procedural geometry/textures CC0-1.0; Poly Haven models/maps CC0-1.0"
        ),
        "commercial_allowed": True,
        "quality_gate_checks": checks,
        "all_quality_gates_passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-repository", required=True)
    parser.add_argument("--stock-release", required=True)
    parser.add_argument("--asset-pack", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    stock_repository = Path(args.stock_repository).expanduser().resolve()
    stock_release = Path(args.stock_release).expanduser().resolve()
    asset_pack = Path(args.asset_pack).expanduser().resolve()
    gate_path = Path(args.gate).expanduser().resolve()
    gate = load_object(gate_path)
    stock = stock_audit(stock_repository, stock_release)
    custom = custom_audit(asset_pack, gate)
    report = {
        "schema_version": 1,
        "gate": str(gate_path),
        "gate_sha256": sha256(gate_path),
        "stock": stock,
        "custom": custom,
        "comparison": {
            "crop_model_count_ratio": custom["crop_summary"]["models"]
            / stock["crop_summary"]["models"],
            "crop_median_faces_ratio": custom["crop_summary"]["faces"]["median"]
            / stock["crop_summary"]["faces"]["median"],
            "weed_type_delta": len(custom["weed_types"])
            - len(stock["weed_groups_used"]),
            "ground_family_delta": custom["ground_families"]
            - stock["ground_families"],
            "environment_family_delta": custom["environment_families"]
            - stock["environment_families"],
            "license_improvement": (
                "bundled-unitemized research-only -> itemized CC0-1.0"
            ),
        },
        "interpretation": (
            "Geometry and provenance gates establish asset fitness only; the frozen "
            "equal-budget real-development model A/B remains authoritative."
        ),
    }
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "all_custom_asset_gates_passed": custom[
                    "all_quality_gates_passed"
                ],
                "comparison": report["comparison"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
