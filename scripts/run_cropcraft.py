#!/usr/bin/env python3
"""Run a pinned CropCraft checkout and emit a fail-closed generation receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image


DEFAULT_DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
DEFAULT_REPOSITORY = DEFAULT_DATA_ROOT / "raw/cropcraft/repository"
DEFAULT_PYTHON_ENV = DEFAULT_DATA_ROOT / "cache/cropcraft_py311"
DEFAULT_BLENDER = Path(
    "/home/ankaref/Documents/Projects/simulation/"
    ".tools/blender-4.5.12-linux-x64/blender"
)
PINNED_REVISION = "7128cd2acade50cc4a5a1761210b55989ab62527"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPATIBILITY_PATCH = (
    PROJECT_ROOT / "patches/cropcraft/0001-blender-4.5-eevee-next.patch"
)


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


def tree_inventory(root: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Asset packs may not contain symlinks: {path}")
        if not path.is_file() or path.name == "PACK.json":
            continue
        inventory.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return inventory


def validate_asset_pack(
    asset_pack: Path, ground_material_id: str | None, config: dict[str, Any]
) -> dict[str, Any]:
    manifest_path = asset_pack / "PACK.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing asset pack manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Expected asset pack object: {manifest_path}")
    expected_inventory = manifest.get("inventory")
    if not isinstance(expected_inventory, list):
        raise ValueError("Asset pack does not contain a frozen inventory")
    observed_inventory = tree_inventory(asset_pack)
    if observed_inventory != expected_inventory:
        raise RuntimeError("Asset pack inventory does not match PACK.json")
    inventory_hash = canonical_sha256(observed_inventory)
    if inventory_hash != manifest.get("inventory_sha256"):
        raise RuntimeError("Asset pack inventory digest does not match PACK.json")
    if not ground_material_id:
        raise ValueError("--ground-material-id is required with --asset-pack")
    if ground_material_id not in manifest.get("grounds", []):
        raise ValueError(f"Unknown ground material ID: {ground_material_id}")
    ground_root = asset_pack / "grounds" / ground_material_id
    ground_files = {
        "diff.jpg": ground_root / "diff.jpg",
        "rough.jpg": ground_root / "rough.jpg",
        "nor_gl.exr": ground_root / "nor_gl.exr",
        "disp.png": ground_root / "disp.png",
    }
    missing_ground = [str(path) for path in ground_files.values() if not path.is_file()]
    if missing_ground:
        raise FileNotFoundError(f"Incomplete ground material: {missing_ground}")
    render = config.get("render", {})
    environment_path = Path(str(render.get("env_path", ""))).expanduser().resolve()
    if not environment_path.is_file():
        raise FileNotFoundError(f"Missing configured environment: {environment_path}")
    try:
        environment_relative = environment_path.relative_to(asset_pack.resolve())
    except ValueError as error:
        raise ValueError(
            "Asset-pack runs must use an environment contained in that pack"
        ) from error
    if environment_relative.as_posix() not in {
        row["path"] for row in observed_inventory
    }:
        raise RuntimeError("Configured environment is absent from pack inventory")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "inventory": observed_inventory,
        "inventory_sha256": inventory_hash,
        "ground_material_id": ground_material_id,
        "ground_files": ground_files,
        "environment_path": environment_path,
        "environment_relative_path": environment_relative.as_posix(),
    }


def git_output(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML object: {path}")
    return value


def site_packages(environment: Path) -> Path:
    candidates = sorted((environment / "lib").glob("python*/site-packages"))
    if len(candidates) != 1 or not candidates[0].is_dir():
        raise FileNotFoundError(
            f"Expected one Python site-packages directory under {environment}"
        )
    return candidates[0]


def validate_outputs(
    destination: Path, config: dict[str, Any]
) -> dict[str, Any]:
    render = config.get("render")
    if not isinstance(render, dict):
        raise ValueError("CropCraft config must contain a render block")
    render_dir = destination / str(render.get("directory", "render"))
    images = sorted((render_dir / "images").glob("*.jpg"))
    masks = sorted((render_dir / "masks").glob("*.png"))
    expected_frames = int(render.get("frames", 1))
    if len(images) != expected_frames or len(masks) != expected_frames:
        raise RuntimeError(
            f"Expected {expected_frames} RGB/mask pairs, got "
            f"{len(images)}/{len(masks)}"
        )
    image_by_stem = {path.stem: path for path in images}
    mask_by_stem = {path.stem: path for path in masks}
    if set(image_by_stem) != set(mask_by_stem):
        raise RuntimeError("CropCraft RGB/mask stems do not match")

    label_colors = render.get("label_colors", {})
    class_colors = {
        "background": tuple(label_colors.get("background", [0, 0, 0])),
        "crop": tuple(label_colors.get("crop", [0, 255, 0])),
        "weed": tuple(label_colors.get("weed", [255, 0, 0])),
    }
    allowed = set(class_colors.values())
    class_pixels = {name: 0 for name in class_colors}
    per_frame: list[dict[str, Any]] = []
    expected_size = (
        int(render.get("resolution_x", 1920)),
        int(render.get("resolution_y", 1080)),
    )
    for stem in sorted(image_by_stem):
        with Image.open(image_by_stem[stem]) as image:
            image_size = image.size
        with Image.open(mask_by_stem[stem]) as mask:
            rgb_mask = mask.convert("RGB")
            mask_size = rgb_mask.size
            colors = rgb_mask.getcolors(maxcolors=mask_size[0] * mask_size[1])
        if image_size != expected_size or mask_size != expected_size:
            raise RuntimeError(
                f"Unexpected RGB/mask shape for {stem}: "
                f"{image_size}/{mask_size} != {expected_size}"
            )
        if colors is None:
            raise RuntimeError(f"Could not enumerate mask colors: {stem}")
        observed = {tuple(color) for _, color in colors}
        if not observed <= allowed:
            raise RuntimeError(
                f"Unexpected semantic colors in {stem}: {sorted(observed - allowed)}"
            )
        frame_counts: dict[str, int] = {}
        color_counts = {tuple(color): int(count) for count, color in colors}
        for name, color in class_colors.items():
            count = color_counts.get(color, 0)
            frame_counts[name] = count
            class_pixels[name] += count
        per_frame.append({"stem": stem, "class_pixels": frame_counts})

    if class_pixels["crop"] <= 0:
        raise RuntimeError(f"Pilot scene must contain crop pixels: {class_pixels}")
    return {
        "expected_frames": expected_frames,
        "validated_pairs": len(images),
        "image_size": list(expected_size),
        "allowed_colors": {
            name: list(color) for name, color in class_colors.items()
        },
        "class_pixels": class_pixels,
        "per_frame": per_frame,
    }


def output_inventory(destination: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.name == "generation_receipt.json":
            continue
        inventory.append(
            {
                "path": path.relative_to(destination).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repository", default=str(DEFAULT_REPOSITORY))
    parser.add_argument("--blender", default=str(DEFAULT_BLENDER))
    parser.add_argument("--python-environment", default=str(DEFAULT_PYTHON_ENV))
    parser.add_argument("--expected-revision", default=PINNED_REVISION)
    parser.add_argument(
        "--compatibility-patch", default=str(DEFAULT_COMPATIBILITY_PATCH)
    )
    parser.add_argument("--asset-pack")
    parser.add_argument("--ground-material-id")
    parser.add_argument(
        "--scene-patch",
        help="Optional second, provenance-recorded patch applied after compatibility",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    repository = Path(args.repository).expanduser().resolve()
    blender = Path(args.blender).expanduser().resolve()
    python_environment = Path(args.python_environment).expanduser().resolve()
    compatibility_patch = Path(args.compatibility_patch).expanduser().resolve()
    scene_patch = (
        Path(args.scene_patch).expanduser().resolve() if args.scene_patch else None
    )
    asset_pack = (
        Path(args.asset_pack).expanduser().resolve() if args.asset_pack else None
    )
    if destination.exists():
        raise FileExistsError(destination)
    if (
        not config_path.is_file()
        or not blender.is_file()
        or not compatibility_patch.is_file()
    ):
        raise FileNotFoundError(
            "Missing CropCraft config, Blender executable, or compatibility patch"
        )
    if scene_patch is not None and not scene_patch.is_file():
        raise FileNotFoundError(f"Missing scene patch: {scene_patch}")
    revision = git_output(repository, "rev-parse", "HEAD")
    if revision != args.expected_revision:
        raise RuntimeError(
            f"CropCraft revision mismatch: {revision} != {args.expected_revision}"
        )
    dirty = git_output(repository, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError("Pinned CropCraft checkout has tracked modifications")

    config = load_config(config_path)
    asset_pack_state = (
        validate_asset_pack(asset_pack, args.ground_material_id, config)
        if asset_pack is not None
        else None
    )
    if asset_pack is None and args.ground_material_id:
        raise ValueError("--ground-material-id requires --asset-pack")
    destination.mkdir(parents=True, exist_ok=False)
    copied_config = destination / "config.input.yaml"
    shutil.copy2(config_path, copied_config)
    log_path = destination / "blender.log"
    python_path = site_packages(python_environment)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(python_path), environment.get("PYTHONPATH", "")))
    )
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    cache_root = DEFAULT_DATA_ROOT / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="cropcraft-source-", dir=cache_root
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        source_archive = temporary_root / "source.tar"
        run_repository = temporary_root / "repository"
        run_repository.mkdir()
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "archive",
                "--format=tar",
                f"--output={source_archive}",
                revision,
            ],
            check=True,
        )
        shutil.unpack_archive(source_archive, run_repository)
        patch_result = subprocess.run(
            [
                "patch",
                "--batch",
                "--forward",
                "-p1",
                "-i",
                str(compatibility_patch),
            ],
            cwd=run_repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if patch_result.returncode != 0:
            raise RuntimeError(
                "CropCraft compatibility patch failed:\n"
                f"{patch_result.stdout}{patch_result.stderr}"
            )
        if scene_patch is not None:
            scene_patch_result = subprocess.run(
                [
                    "patch",
                    "--batch",
                    "--forward",
                    "-p1",
                    "-i",
                    str(scene_patch),
                ],
                cwd=run_repository,
                check=False,
                capture_output=True,
                text=True,
            )
            if scene_patch_result.returncode != 0:
                raise RuntimeError(
                    "CropCraft scene patch failed:\n"
                    f"{scene_patch_result.stdout}{scene_patch_result.stderr}"
                )
        isolated_xdg = temporary_root / "xdg"
        if asset_pack_state is None:
            isolated_xdg.mkdir()
        else:
            isolated_xdg = asset_pack / "xdg"
            plants_root = isolated_xdg / "cropcraft/plants"
            if not plants_root.is_dir():
                raise FileNotFoundError(
                    f"Asset pack has no CropCraft plant directory: {plants_root}"
                )
            source_stones = asset_pack / "overlay/stones"
            if not source_stones.is_dir():
                raise FileNotFoundError(
                    f"Asset pack has no background debris: {source_stones}"
                )
            target_stones = run_repository / "assets/stones"
            shutil.rmtree(target_stones)
            shutil.copytree(source_stones, target_stones)
            texture_names = {
                "diff.jpg": "dry_mud_field_001_diff_2k.jpg",
                "rough.jpg": "dry_mud_field_001_rough_2k.jpg",
                "nor_gl.exr": "dry_mud_field_001_nor_gl_2k.exr",
                "disp.png": "dry_mud_field_001_disp_2k.png",
            }
            texture_root = run_repository / "assets/textures"
            for source_name, target_name in texture_names.items():
                shutil.copy2(
                    asset_pack_state["ground_files"][source_name],
                    texture_root / target_name,
                )
        environment["XDG_DATA_HOME"] = str(isolated_xdg)
        configured_profile = config.get("agri_asset_profile", {})
        if not isinstance(configured_profile, dict):
            raise ValueError("agri_asset_profile must be a mapping")
        surface_profile = configured_profile.get("surface_profile")
        surface_parameters = configured_profile.get("surface_parameters", {})
        if not isinstance(surface_parameters, dict):
            raise ValueError("surface_parameters must be a mapping")
        if surface_profile is not None:
            if asset_pack_state is None:
                raise ValueError("A surface profile requires an asset pack")
            declared_profiles = asset_pack_state["manifest"].get(
                "surface_profiles", {}
            )
            if not isinstance(declared_profiles, dict) or str(surface_profile) not in declared_profiles:
                raise ValueError(
                    f"Surface profile is not declared by the asset pack: {surface_profile}"
                )
            environment["CROPCRAFT_SURFACE_PROFILE"] = str(surface_profile)
            for name, value in sorted(surface_parameters.items()):
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise ValueError(f"Non-finite surface parameter {name}: {value}")
                environment[
                    "CROPCRAFT_SURFACE_" + str(name).upper()
                ] = format(numeric, ".9g")
        entrypoint = run_repository / "core/blender_entrypoint.py"
        command = [
            str(blender),
            "--background",
            "--python-use-system-env",
            "--python",
            str(entrypoint),
            "--",
            str(config_path),
            str(destination),
        ]
        result = subprocess.run(
            command,
            cwd=run_repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    log_path.write_text(result.stdout, encoding="utf-8")
    if (
        result.returncode != 0
        or "Traceback (most recent call last):" in result.stdout
    ):
        tail = "\n".join(result.stdout.splitlines()[-40:])
        raise RuntimeError(f"CropCraft Blender run failed:\n{tail}")

    validation = validate_outputs(destination, config)
    requirements = PROJECT_ROOT / "configs/simulation/cropcraft_py311_requirements.txt"
    asset_receipt = None
    if asset_pack_state is not None:
        asset_receipt = {
            "root": str(asset_pack),
            "pack_id": asset_pack_state["manifest"].get("pack_id"),
            "manifest": str(asset_pack_state["manifest_path"]),
            "manifest_sha256": sha256(asset_pack_state["manifest_path"]),
            "inventory_sha256": asset_pack_state["inventory_sha256"],
            "inventory_files": len(asset_pack_state["inventory"]),
            "inventory_bytes": sum(
                int(row["size_bytes"]) for row in asset_pack_state["inventory"]
            ),
            "ground_material_id": asset_pack_state["ground_material_id"],
            "ground_files": {
                name: {
                    "path": str(path),
                    "sha256": sha256(path),
                }
                for name, path in asset_pack_state["ground_files"].items()
            },
            "environment": {
                "path": str(asset_pack_state["environment_path"]),
                "relative_path": asset_pack_state["environment_relative_path"],
                "sha256": sha256(asset_pack_state["environment_path"]),
            },
            "user_asset_isolation": "XDG_DATA_HOME fixed to declared pack",
            "stock_stones_replaced": True,
        }
    receipt = {
        "schema_version": 1,
        "runner_script": str(Path(__file__).resolve()),
        "runner_script_sha256": sha256(Path(__file__).resolve()),
        "generator": "Romea/CropCraft",
        "generator_license": "Apache-2.0",
        "generator_repository": str(repository),
        "generator_revision": revision,
        "generator_checkout_clean": True,
        "source_materialization": "git archive of pinned revision",
        "compatibility_patch": str(compatibility_patch),
        "compatibility_patch_sha256": sha256(compatibility_patch),
        "scene_patch": None if scene_patch is None else str(scene_patch),
        "scene_patch_sha256": None if scene_patch is None else sha256(scene_patch),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "copied_config_sha256": sha256(copied_config),
        "blender": str(blender),
        "blender_version": subprocess.run(
            [str(blender), "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()[0],
        "python_environment": str(python_environment),
        "asset_pack": asset_receipt,
        "surface_profile": config.get("agri_asset_profile", {}).get(
            "surface_profile"
        ),
        "surface_parameters": config.get("agri_asset_profile", {}).get(
            "surface_parameters", {}
        ),
        "undeclared_user_assets_isolated": True,
        "requirements": str(requirements),
        "requirements_sha256": sha256(requirements),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": time.monotonic() - started,
        "returncode": result.returncode,
        "validation": validation,
        "outputs": output_inventory(destination),
    }
    temporary = destination / "generation_receipt.tmp.json"
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(destination / "generation_receipt.json")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
