#!/usr/bin/env python3
"""Fail-closed static audit for the isolated reproductive-rice asset pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageChops

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from audit_cropcraft_assets import obj_geometry_sha256, obj_stats  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def resolve_project(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def tree_inventory(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Asset pack contains a symlink: {path}")
        if path.is_file() and path.name != "PACK.json":
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return rows


def degenerate_face_count(path: Path) -> int:
    vertices: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                values = line.split()
                vertices.append(tuple(float(value) for value in values[1:4]))
            elif line.startswith("f "):
                faces.append(
                    [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
                )

    def area(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> float:
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        return 0.5 * math.sqrt(sum(value * value for value in cross))

    degenerate = 0
    for face in faces:
        origin = vertices[face[0]]
        face_area = sum(
            area(origin, vertices[face[index]], vertices[face[index + 1]])
            for index in range(1, len(face) - 1)
        )
        degenerate += int(face_area <= 1e-12)
    return degenerate


def edge_max_abs_difference(path: Path) -> int:
    with Image.open(path) as source:
        image = source.convert("RGB")
        left = image.crop((0, 0, 1, image.height))
        right = image.crop((image.width - 1, 0, image.width, image.height))
        top = image.crop((0, 0, image.width, 1))
        bottom = image.crop((0, image.height - 1, image.width, image.height))
        horizontal = ImageChops.difference(left, right).getextrema()
        vertical = ImageChops.difference(top, bottom).getextrema()
    return max(high for _, high in (*horizontal, *vertical))


def material_maps(mtl_path: Path) -> dict[str, Any]:
    lines = mtl_path.read_text(encoding="utf-8", errors="replace").splitlines()
    albedos = [line.split()[-1] for line in lines if line.startswith("map_Kd ")]
    normals = [line.split()[-1] for line in lines if line.startswith("map_Bump ")]
    referenced = sorted(set(albedos + normals))
    return {
        "albedo_maps": albedos,
        "normal_maps": normals,
        "referenced_files": referenced,
        "all_exist": all((mtl_path.parent / name).is_file() for name in referenced),
    }


def audit(pack_root: Path, gate_path: Path) -> dict[str, Any]:
    gate = load_object(gate_path)
    pack = load_object(pack_root / "PACK.json")
    asset_gate = gate["asset_pack_gate"]
    base_lock = gate["base_pack_lock"]
    base_root = resolve_project(base_lock["path"])
    base_pack = load_object(base_root / "PACK.json")
    inventory = tree_inventory(pack_root)
    base_inventory = tree_inventory(base_root)

    lock_rows: dict[str, dict[str, Any]] = {}
    lock_checks: dict[str, bool] = {}
    for section_name in ("selection_evidence_lock", "builder_lock"):
        section = gate[section_name]
        locked_path = resolve_project(section.get("report", section.get("path")))
        observed = sha256(locked_path)
        expected = str(section["sha256"])
        lock_rows[section_name] = {
            "path": str(locked_path),
            "expected_sha256": expected,
            "observed_sha256": observed,
        }
        lock_checks[f"{section_name}_sha256"] = observed == expected
    for name, section in gate.get("builder_dependency_locks", {}).items():
        locked_path = resolve_project(section["path"])
        observed = sha256(locked_path)
        expected = str(section["sha256"])
        lock_rows[f"builder_dependency_{name}"] = {
            "path": str(locked_path),
            "expected_sha256": expected,
            "observed_sha256": observed,
        }
        lock_checks[f"builder_dependency_{name}_sha256"] = observed == expected
    for name, section in gate.get("refinement_control_lock", {}).items():
        if not isinstance(section, dict) or "path" not in section:
            continue
        locked_path = resolve_project(section["path"])
        observed = sha256(locked_path)
        expected = str(section["sha256"])
        lock_rows[f"refinement_control_{name}"] = {
            "path": str(locked_path),
            "expected_sha256": expected,
            "observed_sha256": observed,
        }
        lock_checks[f"refinement_control_{name}_sha256"] = observed == expected
        if "expected_passed" in section:
            payload = load_object(locked_path)
            lock_checks[f"refinement_control_{name}_verdict"] = (
                payload.get("passed") is bool(section["expected_passed"])
            )
    prompt = gate["source_texture_lock"]["prompt_receipt"]
    prompt_path = resolve_project(prompt["path"])
    prompt_observed = sha256(prompt_path)
    lock_rows["prompt_receipt"] = {
        "path": str(prompt_path),
        "expected_sha256": prompt["sha256"],
        "observed_sha256": prompt_observed,
    }
    lock_checks["prompt_receipt_sha256"] = prompt_observed == prompt["sha256"]
    source_rows: list[dict[str, Any]] = []
    for phenotype, source_lock in sorted(gate["source_texture_lock"]["files"].items()):
        source_path = resolve_project(source_lock["path"])
        with Image.open(source_path) as image:
            dimensions = list(image.size)
        observed = sha256(source_path)
        source_rows.append(
            {
                "phenotype": phenotype,
                "path": str(source_path),
                "expected_sha256": source_lock["sha256"],
                "observed_sha256": observed,
                "dimensions": dimensions,
            }
        )
        lock_checks[f"source_{phenotype}_sha256"] = observed == source_lock["sha256"]
        lock_checks[f"source_{phenotype}_dimensions"] = dimensions == source_lock["dimensions"]

    reproductive = pack["generated_assets"]["reproductive_crop"]
    rows = reproductive["models"]
    plant_root = pack_root / "xdg/cropcraft/plants" / str(asset_gate["plant_type"])
    description = load_object(plant_root / "description.yaml")
    description_by_name = {
        str(row["filename"]): row for row in description["models"]
    }
    declared_by_name = {str(row["filename"]): row for row in rows}
    actual_obj_paths = sorted(plant_root.glob("*.obj"))
    model_audits: list[dict[str, Any]] = []
    for obj_path in actual_obj_paths:
        stats = obj_stats(obj_path)
        stats["geometry_sha256"] = obj_geometry_sha256(obj_path)
        stats["degenerate_faces"] = degenerate_face_count(obj_path)
        declared = declared_by_name[obj_path.name]
        described = description_by_name[obj_path.name]
        stats["declared_height_m"] = float(declared["height_m"])
        stats["description_height_m"] = float(described["height"])
        stats["declared_height_relative_error"] = abs(
            stats["height_m"] - stats["declared_height_m"]
        ) / stats["declared_height_m"]
        stats["manifest_obj_sha256_matches"] = stats["sha256"] == declared["obj_sha256"]
        stats["manifest_geometry_sha256_matches"] = (
            stats["geometry_sha256"] == declared["geometry_sha256"]
        )
        stats["material"] = material_maps(obj_path.with_suffix(".mtl"))
        model_audits.append(stats)

    morphology_rows = reproductive["morphology_by_geometry"]
    stage_names = [str(row["growth_stage_name"]) for row in rows]
    geometry_by_stage = {
        stage: {
            str(row["geometry_sha256"])
            for row in rows
            if row["growth_stage_name"] == stage
        }
        for stage in asset_gate["expected_growth_stages"]
    }
    observed_stage_phenotypes = {
        stage: sorted(
            {
                str(row["phenotype"])
                for row in rows
                if row["growth_stage_name"] == stage
            }
        )
        for stage in asset_gate["expected_growth_stages"]
    }
    expected_stage_phenotypes = {
        stage: sorted(str(value) for value in values)
        for stage, values in asset_gate["allowed_stage_phenotypes"].items()
    }

    texture_rows: list[dict[str, Any]] = []
    for texture in reproductive["textures"]:
        phenotype = str(texture["phenotype"])
        albedo = plant_root / str(texture["albedo"])
        normal = plant_root / str(texture["normal_gl"])
        with Image.open(albedo) as image:
            albedo_dimensions = list(image.size)
        with Image.open(normal) as image:
            normal_dimensions = list(image.size)
        texture_rows.append(
            {
                "phenotype": phenotype,
                "albedo": str(albedo),
                "albedo_sha256": sha256(albedo),
                "albedo_manifest_sha256": texture["albedo_sha256"],
                "albedo_dimensions": albedo_dimensions,
                "albedo_edge_max_abs_difference": edge_max_abs_difference(albedo),
                "normal": str(normal),
                "normal_sha256": sha256(normal),
                "normal_manifest_sha256": texture["normal_gl_sha256"],
                "normal_dimensions": normal_dimensions,
                "normal_edge_max_abs_difference": edge_max_abs_difference(normal),
            }
        )

    base_by_path = {row["path"]: row for row in base_inventory}
    observed_by_path = {row["path"]: row for row in inventory}
    invariant_paths = sorted(path for path in base_by_path if path != "LICENSES.txt")
    changed_base_paths = [
        path for path in invariant_paths if observed_by_path.get(path) != base_by_path[path]
    ]
    base_plants = {
        path.name
        for path in (base_root / "xdg/cropcraft/plants").iterdir()
        if path.is_dir()
    }
    pack_plants = {
        path.name
        for path in (pack_root / "xdg/cropcraft/plants").iterdir()
        if path.is_dir()
    }
    added_plant_groups = sorted(pack_plants - base_plants)
    full_cycle = pack["paddy_v4_assets"]["full_cycle_extension"]
    provenance_root = pack_root / "provenance/imagegen_rice_reproductive_v9"
    provenance_source_exact = all(
        sha256(provenance_root / Path(row["path"]).name) == row["observed_sha256"]
        for row in source_rows
    )
    provenance_prompt_exact = sha256(provenance_root / "PROMPTS.json") == prompt_observed

    maximum_height_error = max(
        row["declared_height_relative_error"] for row in model_audits
    )
    maximum_degenerate = max(row["degenerate_faces"] for row in model_audits)
    face_counts = [int(row["faces"]) for row in model_audits]
    checks = {
        **lock_checks,
        "base_pack_manifest_sha256": sha256(base_root / "PACK.json")
        == base_lock["pack_manifest_sha256"],
        "base_pack_id": base_pack["pack_id"] == base_lock["pack_id"],
        "declared_base_pack_hash": pack["base_pack"]["pack_manifest_sha256"]
        == base_lock["pack_manifest_sha256"],
        "inventory_exact": inventory == pack["inventory"],
        "inventory_digest": canonical_sha256(inventory) == pack["inventory_sha256"],
        "capacity_check": pack["capacity_check"].get("passed") is True,
        "pack_id": pack["pack_id"] == asset_gate["pack_id"],
        "plant_type": reproductive["plant_type"] == asset_gate["plant_type"],
        "crop_species": reproductive["crop_species"] == asset_gate["crop_species"],
        "expected_models": len(rows) == int(asset_gate["expected_models"]),
        "actual_obj_count": len(actual_obj_paths) == int(asset_gate["expected_models"]),
        "description_model_count": len(description_by_name) == int(asset_gate["expected_models"]),
        "model_filename_sets": set(declared_by_name)
        == set(description_by_name)
        == {path.name for path in actual_obj_paths},
        "expected_unique_geometries": len(
            {row["geometry_sha256"] for row in rows}
        )
        == int(asset_gate["expected_unique_geometries"]),
        "morphology_geometry_count": len(morphology_rows)
        == int(asset_gate["expected_unique_geometries"]),
        "expected_growth_stages": sorted(set(stage_names))
        == sorted(asset_gate["expected_growth_stages"]),
        "geometry_variants_per_stage": all(
            len(values) == int(asset_gate["expected_geometry_variants_per_stage"])
            for values in geometry_by_stage.values()
        ),
        "stage_phenotypes": observed_stage_phenotypes == expected_stage_phenotypes,
        "target_heights": sorted(
            {round(float(row["target_height_m"]), 6) for row in morphology_rows}
        )
        == sorted(round(float(value), 6) for value in asset_gate["expected_target_heights_m"]),
        "minimum_faces": min(face_counts) >= int(asset_gate["minimum_faces_per_model"]),
        "maximum_faces": max(face_counts) <= int(asset_gate["maximum_faces_per_model"]),
        "maximum_degenerate_faces": maximum_degenerate
        <= int(asset_gate["maximum_degenerate_faces_per_model"]),
        "declared_height_accuracy": maximum_height_error
        <= float(asset_gate["maximum_declared_height_relative_error"]),
        "manifest_obj_hashes": all(row["manifest_obj_sha256_matches"] for row in model_audits),
        "manifest_geometry_hashes": all(
            row["manifest_geometry_sha256_matches"] for row in model_audits
        ),
        "minimum_tillers": min(int(row["tiller_count"]) for row in morphology_rows)
        >= int(asset_gate["minimum_tillers_per_geometry"]),
        "minimum_leaves": min(int(row["leaf_count"]) for row in morphology_rows)
        >= int(asset_gate["minimum_leaves_per_geometry"]),
        "minimum_panicles": min(int(row["panicle_count"]) for row in morphology_rows)
        >= int(asset_gate["minimum_panicles_per_geometry"]),
        "minimum_panicle_branches": min(
            int(row["panicle_branch_count"]) for row in morphology_rows
        )
        >= int(asset_gate["minimum_panicle_branches_per_geometry"]),
        "minimum_grains": min(int(row["grain_count"]) for row in morphology_rows)
        >= int(asset_gate["minimum_grains_per_geometry"]),
        "material_maps_per_model": all(
            row["material"]["albedo_maps"]
            and row["material"]["normal_maps"]
            and row["material"]["all_exist"]
            for row in model_audits
        ),
        "expected_texture_phenotypes": len(texture_rows)
        == int(asset_gate["expected_texture_phenotypes"]),
        "texture_dimensions": all(
            row["albedo_dimensions"] == asset_gate["processed_texture_dimensions"]
            and row["normal_dimensions"] == asset_gate["processed_texture_dimensions"]
            for row in texture_rows
        ),
        "texture_manifest_hashes": all(
            row["albedo_sha256"] == row["albedo_manifest_sha256"]
            and row["normal_sha256"] == row["normal_manifest_sha256"]
            for row in texture_rows
        ),
        "texture_seams": all(
            row["albedo_edge_max_abs_difference"]
            <= int(asset_gate["maximum_texture_edge_abs_difference"])
            and row["normal_edge_max_abs_difference"]
            <= int(asset_gate["maximum_texture_edge_abs_difference"])
            for row in texture_rows
        ),
        "base_nonlicense_files_byte_exact": not changed_base_paths,
        "base_generated_crop_unchanged": pack["generated_assets"]["crop"]
        == base_pack["generated_assets"]["crop"],
        "base_weeds_unchanged": pack["generated_assets"]["weeds"]
        == base_pack["generated_assets"]["weeds"],
        "base_debris_unchanged": pack["generated_assets"]["background_debris"]
        == base_pack["generated_assets"]["background_debris"],
        "base_surfaces_unchanged": pack["grounds"] == base_pack["grounds"]
        and pack["environments"] == base_pack["environments"]
        and pack["surface_profiles"] == base_pack["surface_profiles"],
        "only_reproductive_plant_group_added": added_plant_groups
        == [asset_gate["plant_type"]],
        "source_provenance_exact": provenance_source_exact and provenance_prompt_exact,
        "external_asset_bytes_not_acquired": reproductive["external_asset_bytes_acquired"]
        is bool(asset_gate["require_external_asset_bytes_acquired"]),
        "duckweed_not_added": full_cycle["duckweed_added"]
        is bool(asset_gate["require_duckweed_added"]),
        "commercial_claim_disabled": pack["commercial_allowed"]
        is bool(asset_gate["commercial_allowed"]),
        "license_does_not_claim_imagegen_cc0": "not relabelled as CC0"
        in (pack_root / "LICENSES.txt").read_text(encoding="utf-8"),
    }
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "gate": str(gate_path),
        "gate_sha256": sha256(gate_path),
        "pack": str(pack_root),
        "pack_id": pack["pack_id"],
        "pack_manifest_sha256": sha256(pack_root / "PACK.json"),
        "inventory_sha256": canonical_sha256(inventory),
        "inventory_files": len(inventory),
        "inventory_bytes": sum(int(row["size_bytes"]) for row in inventory),
        "locked_inputs": lock_rows,
        "source_textures": source_rows,
        "model_summary": {
            "models": len(model_audits),
            "unique_geometries": len({row["geometry_sha256"] for row in model_audits}),
            "faces_min": min(face_counts),
            "faces_max": max(face_counts),
            "maximum_degenerate_faces": maximum_degenerate,
            "maximum_declared_height_relative_error": maximum_height_error,
            "minimum_tillers": min(int(row["tiller_count"]) for row in morphology_rows),
            "minimum_leaves": min(int(row["leaf_count"]) for row in morphology_rows),
            "minimum_panicles": min(int(row["panicle_count"]) for row in morphology_rows),
            "minimum_panicle_branches": min(
                int(row["panicle_branch_count"]) for row in morphology_rows
            ),
            "minimum_grains": min(int(row["grain_count"]) for row in morphology_rows),
        },
        "texture_summary": texture_rows,
        "added_plant_groups": added_plant_groups,
        "changed_base_paths": changed_base_paths,
        "quality_gate_checks": checks,
        "all_quality_gates_passed": all(checks.values()),
        "large_synthetic_batch_generated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-pack", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pack_root = Path(args.asset_pack).expanduser().resolve()
    gate_path = Path(args.gate).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    report = audit(pack_root, gate_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["all_quality_gates_passed"]:
        raise RuntimeError(f"Reproductive asset gates failed; see {output}")


if __name__ == "__main__":
    main()
