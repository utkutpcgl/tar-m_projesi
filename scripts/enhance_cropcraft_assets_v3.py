#!/usr/bin/env python3
"""Build the frozen v3 CropCraft asset challenger from the accepted v2 pack.

The v3 change is deliberately narrow:

* retain the exact v2 soil, HDRI, debris, and plant geometry foundation;
* add three deterministic crop albedo phenotypes over each v2 morphology;
* add texture-backed CC0 Poly Haven weed references normalized for early weeds.

All remote inputs come from the official Poly Haven API and are checked against
its advertised byte count and MD5 before a SHA-256 inventory is frozen.
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
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image


USER_AGENT = "AgriSegSyntheticAssetCuration/2.0"
API_ROOT = "https://api.polyhaven.com"
LICENSE_URL = "https://polyhaven.com/license"
PACK_ID = "cropcraft_agri_robust_v3_r3"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONVERTER = PROJECT_ROOT / "scripts/prepare_polyhaven_plant_assets_blender.py"
DEFAULT_BLENDER = Path(
    "/home/ankaref/Documents/Projects/simulation/"
    ".tools/blender-4.5.12-linux-x64/blender"
)
SOURCE_SPECS = (
    {
        "asset_id": "weed_plant_02",
        "target_family": "weed_broadleaf_v2",
        "target_heights_m": [0.018, 0.026, 0.038, 0.052, 0.070],
        "maximum_width_height_ratio": 4.5,
    },
    {
        "asset_id": "nettle_plant",
        "target_family": "weed_broadleaf_v2",
        "target_heights_m": [0.022, 0.032, 0.045, 0.060, 0.078],
        "maximum_width_height_ratio": 3.5,
    },
    {
        "asset_id": "shrub_sorrel_01",
        "target_family": "weed_broadleaf_v2",
        "target_heights_m": [0.018, 0.026, 0.038, 0.052, 0.070],
        "maximum_width_height_ratio": 4.5,
    },
    {
        "asset_id": "dandelion_01",
        "target_family": "weed_rosette_v2",
        "target_heights_m": [0.018, 0.030, 0.044, 0.058],
        "maximum_width_height_ratio": 5.0,
    },
)
CROP_PHENOTYPES = ("healthy_dark", "healthy_light", "field_stress")


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


def url_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return value


def validate_base_pack(root: Path) -> dict[str, Any]:
    manifest_path = root / "PACK.json"
    pack = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed = tree_inventory(root)
    if observed != pack.get("inventory"):
        raise RuntimeError("Base pack inventory differs from its frozen manifest")
    if canonical_sha256(observed) != pack.get("inventory_sha256"):
        raise RuntimeError("Base pack inventory digest mismatch")
    return pack


def gltf_downloads(asset_id: str, files: dict[str, Any]) -> list[dict[str, Any]]:
    node = files["gltf"]["2k"]["gltf"]
    rows = [
        {
            "asset_id": asset_id,
            "relative_path": Path(str(node["url"])).name,
            "role": "gltf",
            "metadata": node,
        }
    ]
    for relative_path, metadata in sorted(node.get("include", {}).items()):
        lowered = relative_path.lower()
        role = "geometry_bin"
        if "_diff_" in lowered:
            role = "diffuse"
        elif "_nor_gl_" in lowered:
            role = "normal"
        elif "_arm_" in lowered:
            role = "arm"
        rows.append(
            {
                "asset_id": asset_id,
                "relative_path": relative_path,
                "role": role,
                "metadata": metadata,
            }
        )
    return rows


def download_file(metadata: dict[str, Any], output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        str(metadata["url"]), headers={"User-Agent": USER_AGENT}
    )
    md5 = hashlib.md5(usedforsecurity=False)
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=180) as response, output.open(
        "wb"
    ) as handle:
        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
            handle.write(block)
            md5.update(block)
            digest.update(block)
            size += len(block)
    if size != int(metadata["size"]):
        raise RuntimeError(f"Size mismatch for {output}: {size} != {metadata['size']}")
    if md5.hexdigest() != str(metadata["md5"]):
        raise RuntimeError(f"MD5 mismatch for {output}")
    return {
        "source_url": metadata["url"],
        "source_md5": metadata["md5"],
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def tree_inventory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Asset packs may not contain symlinks: {path}")
        if path.is_file() and path.name != "PACK.json":
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return rows


def crop_texture(phenotype: str, output: Path) -> dict[str, Any]:
    height = width = 512
    yy, xx = np.mgrid[0:height, 0:width]
    rng = np.random.default_rng(
        {"healthy_dark": 7311, "healthy_light": 7312, "field_stress": 7313}[
            phenotype
        ]
    )
    base = {
        "healthy_dark": np.array([46.0, 116.0, 31.0]),
        "healthy_light": np.array([72.0, 145.0, 48.0]),
        "field_stress": np.array([92.0, 126.0, 38.0]),
    }[phenotype]
    low_frequency = (
        0.55 * np.sin(xx / 29.0 + yy / 71.0)
        + 0.35 * np.sin(xx / 83.0 - yy / 37.0)
        + 0.20 * np.sin(yy / 11.0)
    )
    noise = rng.normal(0.0, 1.0, size=(height, width))
    modulation = 1.0 + 0.065 * low_frequency + 0.022 * noise
    rgb = base[None, None, :] * modulation[:, :, None]
    if phenotype == "field_stress":
        stress = np.zeros((height, width), dtype=np.float64)
        for _ in range(12):
            center_x = rng.uniform(0, width)
            center_y = rng.uniform(0, height)
            radius_x = rng.uniform(14, 60)
            radius_y = rng.uniform(18, 90)
            stress += np.exp(
                -(
                    ((xx - center_x) / radius_x) ** 2
                    + ((yy - center_y) / radius_y) ** 2
                )
            )
        stress = np.clip(stress, 0.0, 1.0)
        stressed_color = np.array([132.0, 103.0, 24.0])
        rgb = rgb * (1.0 - 0.72 * stress[:, :, None]) + stressed_color * (
            0.72 * stress[:, :, None]
        )
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(output, optimize=True)
    return {
        "phenotype": phenotype,
        "filename": output.name,
        "dimensions": [width, height],
        "sha256": sha256(output),
    }


def obj_vertices(path: Path) -> list[tuple[float, float, float]]:
    vertices = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                values = line.split()
                vertices.append(tuple(float(value) for value in values[1:4]))
    if not vertices:
        raise ValueError(f"OBJ has no vertices: {path}")
    return vertices


def geometry_sha256(path: Path) -> str:
    lines = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v ") or line.startswith("f "):
                if line.startswith("f "):
                    fields = [token.split("/")[0] for token in line.split()[1:]]
                    lines.append("f " + " ".join(fields))
                else:
                    lines.append(line.strip())
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def textured_obj(
    source_obj: Path,
    source_mtl: Path,
    output_obj: Path,
    output_mtl: Path,
    phenotype: str,
    texture_name: str,
) -> None:
    vertices = obj_vertices(source_obj)
    minimum_z = min(vertex[2] for vertex in vertices)
    height = max(vertex[2] for vertex in vertices) - minimum_z
    uv_rows = []
    for x, y, z in vertices:
        u = (math.atan2(y, x) + math.pi) / math.tau
        v = 0.0 if height <= 0 else (z - minimum_z) / height
        uv_rows.append(f"vt {u:.9f} {v:.9f}")
    source_lines = source_obj.read_text(encoding="utf-8").splitlines()
    output_lines: list[str] = []
    inserted_uv = False
    suffix = f"_{phenotype}"
    for line in source_lines:
        if line.startswith("mtllib "):
            output_lines.append(f"mtllib {output_mtl.name}")
            continue
        if not line.startswith("v ") and not inserted_uv and any(
            value.startswith("v ") for value in output_lines
        ):
            output_lines.extend(uv_rows)
            inserted_uv = True
        if line.startswith("usemtl "):
            output_lines.append(line + suffix)
        elif line.startswith("f "):
            fields = []
            for token in line.split()[1:]:
                vertex_index = token.split("/")[0]
                fields.append(f"{vertex_index}/{vertex_index}")
            output_lines.append("f " + " ".join(fields))
        else:
            output_lines.append(line)
    if not inserted_uv:
        output_lines.extend(uv_rows)
    output_obj.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    sections: list[list[str]] = []
    current: list[str] = []
    for line in source_mtl.read_text(encoding="utf-8").splitlines():
        if line.startswith("newmtl ") and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    output_sections = []
    for section in sections:
        header = next((line for line in section if line.startswith("newmtl ")), "")
        material = header.split(maxsplit=1)[1] if header else ""
        is_leaf = "leaf" in material or "midrib" in material
        rewritten = []
        for line in section:
            if line.startswith("newmtl "):
                rewritten.append(line + suffix)
            elif is_leaf and line.startswith("Kd "):
                rewritten.append("Kd 1.000000 1.000000 1.000000")
            else:
                rewritten.append(line)
        if is_leaf:
            rewritten.append(f"map_Kd {texture_name}")
        output_sections.append("\n".join(rewritten))
    output_mtl.write_text("\n\n".join(output_sections) + "\n", encoding="utf-8")


def obj_stats(path: Path) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    face_indexes: list[list[int]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                values = line.split()
                vertices.append(tuple(float(value) for value in values[1:4]))
            elif line.startswith("f "):
                face_indexes.append(
                    [int(token.split("/")[0]) for token in line.split()[1:]]
                )
    if not vertices or not face_indexes:
        raise ValueError(f"Incomplete OBJ: {path}")
    minimum = tuple(min(vertex[index] for vertex in vertices) for index in range(3))
    maximum = tuple(max(vertex[index] for vertex in vertices) for index in range(3))
    degenerate = 0
    for face in face_indexes:
        origin = np.asarray(vertices[face[0] - 1], dtype=np.float64)
        area = 0.0
        for index in range(1, len(face) - 1):
            left = np.asarray(vertices[face[index] - 1], dtype=np.float64) - origin
            right = np.asarray(vertices[face[index + 1] - 1], dtype=np.float64) - origin
            area += float(np.linalg.norm(np.cross(left, right)) / 2.0)
        degenerate += int(area <= 1e-12)
    return {
        "vertices": len(vertices),
        "faces": len(face_indexes),
        "degenerate_faces": degenerate,
        "bounds_min_m": list(minimum),
        "bounds_max_m": list(maximum),
        "height_m": maximum[2] - minimum[2],
        "width_m": max(maximum[0] - minimum[0], maximum[1] - minimum[1]),
    }


def enhance_crop_assets(root: Path, base_pack: dict[str, Any]) -> dict[str, Any]:
    crop_directory = root / "xdg/cropcraft/plants/sorghum_seedling_v2"
    with tempfile.TemporaryDirectory(prefix="v2-crop-source-", dir=root.parent) as tmp:
        source_directory = Path(tmp) / "sorghum_seedling_v2"
        shutil.copytree(crop_directory, source_directory)
        shutil.rmtree(crop_directory)
        crop_directory.mkdir(parents=True)
        textures = [
            crop_texture(
                phenotype,
                crop_directory / f"sorghum_leaf_{phenotype}_v3.png",
            )
            for phenotype in CROP_PHENOTYPES
        ]
        base_rows = {
            row["filename"]: row
            for row in base_pack["generated_assets"]["crop"]["models"]
        }
        rows = []
        for source_obj in sorted(source_directory.glob("*.obj")):
            source_mtl = source_obj.with_suffix(".mtl")
            if source_obj.name not in base_rows:
                raise RuntimeError(f"Missing base crop metadata: {source_obj.name}")
            for phenotype in CROP_PHENOTYPES:
                name = f"{source_obj.stem}_{phenotype}"
                output_obj = crop_directory / f"{name}.obj"
                output_mtl = crop_directory / f"{name}.mtl"
                textured_obj(
                    source_obj,
                    source_mtl,
                    output_obj,
                    output_mtl,
                    phenotype,
                    f"sorghum_leaf_{phenotype}_v3.png",
                )
                stats = obj_stats(output_obj)
                base_row = base_rows[source_obj.name]
                rows.append(
                    {
                        "filename": output_obj.name,
                        "phenotype": phenotype,
                        "growth_stage": base_row["growth_stage"],
                        "source_geometry": source_obj.name,
                        "geometry_sha256": geometry_sha256(output_obj),
                        "leaf_area_m2": base_row["leaf_area_m2"],
                        "obj_sha256": sha256(output_obj),
                        "mtl_sha256": sha256(output_mtl),
                        **stats,
                    }
                )
        description = {
            "models": [
                {
                    "filename": row["filename"],
                    "height": round(float(row["height_m"]), 6),
                    "width": round(float(row["width_m"]), 6),
                    "leaf_area": round(float(row["leaf_area_m2"]), 8),
                }
                for row in rows
            ]
        }
        (crop_directory / "description.yaml").write_text(
            yaml.safe_dump(description, sort_keys=False), encoding="utf-8"
        )
    return {
        "plant_type": "sorghum_seedling_v2",
        "models": rows,
        "albedo_textures": textures,
        "unique_geometry_sha256": sorted({row["geometry_sha256"] for row in rows}),
    }


def append_scan_descriptions(
    root: Path,
    base_pack: dict[str, Any],
    conversion: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    scan_rows: list[dict[str, Any]] = []
    for asset in conversion["assets"]:
        for model in asset["exported_models"]:
            path = (
                root
                / "xdg/cropcraft/plants"
                / str(model["target_family"])
                / str(model["filename"])
            )
            stats = obj_stats(path)
            row = {
                **model,
                **stats,
                "leaf_area_m2": float(model["surface_area_m2"]),
                "texture_backed": True,
                "license": "CC0-1.0",
            }
            by_family.setdefault(str(model["target_family"]), []).append(row)
            scan_rows.append(row)

    result: dict[str, Any] = {}
    for family, base_section in base_pack["generated_assets"]["weeds"].items():
        rows = deepcopy(base_section["models"])
        rows.extend(by_family.get(family, []))
        directory = root / "xdg/cropcraft/plants" / family
        description = {
            "models": [
                {
                    "filename": row["filename"],
                    "height": round(float(row["height_m"]), 6),
                    "width": round(float(row["width_m"]), 6),
                    "leaf_area": round(float(row["leaf_area_m2"]), 8),
                }
                for row in rows
            ]
        }
        (directory / "description.yaml").write_text(
            yaml.safe_dump(description, sort_keys=False), encoding="utf-8"
        )
        result[family] = {"plant_type": family, "models": rows}
    return result, scan_rows


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
    files_by_id = {
        str(spec["asset_id"]): url_json(f"{API_ROOT}/files/{spec['asset_id']}")
        for spec in SOURCE_SPECS
    }
    downloads = [
        row
        for spec in SOURCE_SPECS
        for row in gltf_downloads(str(spec["asset_id"]), files_by_id[str(spec["asset_id"])])
    ]
    advertised_bytes = sum(int(row["metadata"]["size"]) for row in downloads)
    free_bytes = shutil.disk_usage(destination.parent).free
    base_bytes = int(base_pack["inventory_bytes"])
    required_free = 2 * base_bytes + 3 * advertised_bytes + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free}, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-agri-v3-", dir=destination.parent
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        root = temporary / destination.name
        shutil.copytree(base_root, root)
        (root / "PACK.json").unlink()
        provenance = root / "provenance"
        provenance.mkdir()
        shutil.copy2(base_root / "PACK.json", provenance / "BASE_PACK.json")

        downloaded_rows = []
        input_gltfs: dict[str, Path] = {}
        for row in downloads:
            source_root = root / "sources/polyhaven_models" / row["asset_id"]
            output = source_root / row["relative_path"]
            receipt = download_file(row["metadata"], output)
            receipt.update(
                {
                    "asset_id": row["asset_id"],
                    "kind": "reference_plant_model",
                    "role": row["role"],
                    "path": output.relative_to(root).as_posix(),
                }
            )
            downloaded_rows.append(receipt)
            if row["role"] == "gltf":
                input_gltfs[row["asset_id"]] = output

        crop = enhance_crop_assets(root, base_pack)
        conversion_spec = {
            "assets": [
                {
                    **spec,
                    "input_gltf": str(input_gltfs[str(spec["asset_id"])]),
                    "output_directory": str(
                        root
                        / "xdg/cropcraft/plants"
                        / str(spec["target_family"])
                    ),
                }
                for spec in SOURCE_SPECS
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
        (provenance / "polyhaven_conversion_blender.log").write_text(
            conversion_process.stdout + conversion_process.stderr,
            encoding="utf-8",
        )
        if conversion_process.returncode != 0:
            raise RuntimeError(
                "Poly Haven conversion failed:\n"
                + "\n".join(
                    (conversion_process.stdout + conversion_process.stderr).splitlines()[
                        -60:
                    ]
                )
            )
        conversion = json.loads(
            Path(conversion_spec["output_report"]).read_text(encoding="utf-8")
        )
        for asset in conversion["assets"]:
            asset["input_gltf"] = input_gltfs[asset["asset_id"]].relative_to(
                root
            ).as_posix()
        # Blender's OBJ exporter writes portable basenames into each MTL but
        # does not copy GLTF-owned images when running headless. Materialize
        # those exact basenames beside the OBJ/MTL files as CropCraft requires.
        for spec in SOURCE_SPECS:
            asset_id = str(spec["asset_id"])
            target_directory = (
                root
                / "xdg/cropcraft/plants"
                / str(spec["target_family"])
            )
            texture_directory = (
                root / "sources/polyhaven_models" / asset_id / "textures"
            )
            for texture_path in sorted(texture_directory.glob("*")):
                if texture_path.is_file():
                    shutil.copy2(texture_path, target_directory / texture_path.name)
        texture_names = {
            (str(row["asset_id"]), str(row["role"])): Path(
                str(row["path"])
            ).name
            for row in downloaded_rows
            if row["role"] in {"diffuse", "normal"}
        }
        for asset in conversion["assets"]:
            target_directory = (
                root
                / "xdg/cropcraft/plants"
                / str(asset["target_family"])
            )
            for model in asset["exported_models"]:
                mtl_path = target_directory / str(model["mtl_filename"])
                material = mtl_path.read_text(encoding="utf-8")
                additions = []
                if "map_Kd " not in material:
                    additions.append(
                        "map_Kd "
                        + texture_names[(str(asset["asset_id"]), "diffuse")]
                    )
                if "map_Bump " not in material:
                    additions.append(
                        "map_Bump -bm 1.000000 "
                        + texture_names[(str(asset["asset_id"]), "normal")]
                    )
                if additions:
                    mtl_path.write_text(
                        material.rstrip() + "\n" + "\n".join(additions) + "\n",
                        encoding="utf-8",
                    )
                model["mtl_sha256"] = sha256(mtl_path)
        (provenance / "polyhaven_conversion_report.json").write_text(
            json.dumps(conversion, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        frozen_spec = deepcopy(conversion_spec)
        frozen_spec["output_report"] = "provenance/polyhaven_conversion_report.json"
        for asset in frozen_spec["assets"]:
            asset["input_gltf"] = Path(asset["input_gltf"]).relative_to(root).as_posix()
            asset["output_directory"] = Path(asset["output_directory"]).relative_to(
                root
            ).as_posix()
        (provenance / "polyhaven_conversion_spec.json").write_text(
            json.dumps(frozen_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        weeds, scan_rows = append_scan_descriptions(root, base_pack, conversion)

        license_path = root / "LICENSES.txt"
        license_path.write_text(
            license_path.read_text(encoding="utf-8")
            + "\nTexture-backed reference plant models\n"
            + "=====================================\n"
            + "The Poly Haven GLTF plant model inputs and their texture maps are "
            + f"distributed under CC0-1.0. License: {LICENSE_URL}\n",
            encoding="utf-8",
        )
        sources = deepcopy(base_pack["sources"])
        for spec in SOURCE_SPECS:
            asset_id = str(spec["asset_id"])
            metadata = catalog[asset_id]
            sources[asset_id] = {
                "name": metadata["name"],
                "type": metadata["type"],
                "category": metadata.get("category"),
                "description": metadata.get("description"),
                "authors": metadata.get("authors", {}),
                "files_hash": metadata.get("files_hash"),
                "asset_url": f"https://polyhaven.com/a/{asset_id}",
                "api_files_url": f"{API_ROOT}/files/{asset_id}",
                "license": "CC0-1.0",
                "license_url": LICENSE_URL,
            }
        generated = {
            "crop": crop,
            "weeds": weeds,
            "background_debris": deepcopy(
                base_pack["generated_assets"]["background_debris"]
            ),
        }
        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": PACK_ID,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "controlled texture-backed asset-quality ablation",
            "base_pack": {
                "path": str(base_root),
                "pack_id": base_pack["pack_id"],
                "pack_manifest_sha256": sha256(base_root / "PACK.json"),
                "inventory_sha256": base_pack["inventory_sha256"],
            },
            "enhancer_script": str(Path(__file__).resolve()),
            "enhancer_script_sha256": sha256(__file__),
            "converter_script": str(CONVERTER),
            "converter_script_sha256": sha256(CONVERTER),
            "mesh_provenance": (
                "v2 procedural CC0 geometry plus official Poly Haven "
                "texture-backed CC0 reference models"
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
            "v3_assets": {
                "crop_albedo_phenotypes": list(CROP_PHENOTYPES),
                "unique_crop_geometries": len(crop["unique_geometry_sha256"]),
                "polyhaven_plant_sources": [
                    str(spec["asset_id"]) for spec in SOURCE_SPECS
                ],
                "texture_backed_weed_models": scan_rows,
                "conversion_report": "provenance/polyhaven_conversion_report.json",
            },
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
