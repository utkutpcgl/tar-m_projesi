#!/usr/bin/env python3
"""Apply one deterministic barrel camera model to RGB and instance masks.

The Unreal perspective captures are preserved byte-for-byte in
``raw/*_pre_camera_model``.  The same inverse radial mesh is then applied to
RGB, visible masks and amodal masks.  This keeps instance-derived bounding
boxes aligned after the CCTV-like lens warp.

Depth is deliberately fail-closed: Pillow cannot safely remap the 32-bit EXR
depth contract used by this project.  Detection releases must therefore use
``DEPTH=0`` until a shared RGB/mask/depth camera model is implemented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Unreal dataset output root")
    parser.add_argument("--config", type=Path, required=True, help="EBIS scene JSON")
    return parser.parse_args()


def preserve_inputs(current: Path, preserved: Path) -> list[Path]:
    paths = sorted(current.glob("*.png"))
    if not paths:
        raise FileNotFoundError(f"No PNG files under {current}")
    preserved.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = preserved / path.name
        if not target.exists():
            shutil.copy2(path, target)
    sources = sorted(preserved.glob("*.png"))
    if [path.name for path in sources] != [path.name for path in paths]:
        raise ValueError(f"Camera-model source/current file-set mismatch: {preserved} vs {current}")
    return sources


def source_point(
    x: float,
    y: float,
    width: int,
    height: int,
    strength: float,
) -> tuple[float, float]:
    """Map output coordinates to the wider perspective source.

    The ``1 + 2k`` normalization keeps all four corners in-bounds.  The
    104-degree raw FOV compensates the central magnification introduced by
    k=0.12, keeping specimen scale close to the measured bbox target.
    """

    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    nx = (x - cx) / max(cx, 1.0)
    ny = (y - cy) / max(cy, 1.0)
    radial = (1.0 + strength * (nx * nx + ny * ny)) / (1.0 + 2.0 * strength)
    sx = cx + nx * radial * cx
    sy = cy + ny * radial * cy
    return (
        max(0.0, min(width - 1.0, sx)),
        max(0.0, min(height - 1.0, sy)),
    )


def build_mesh(
    width: int,
    height: int,
    strength: float,
    step: int,
) -> list[tuple[tuple[int, int, int, int], tuple[float, ...]]]:
    mesh = []
    for top in range(0, height, step):
        bottom = min(top + step, height)
        for left in range(0, width, step):
            right = min(left + step, width)
            upper_left = source_point(left, top, width, height, strength)
            lower_left = source_point(left, bottom, width, height, strength)
            lower_right = source_point(right, bottom, width, height, strength)
            upper_right = source_point(right, top, width, height, strength)
            mesh.append(
                (
                    (left, top, right, bottom),
                    (
                        upper_left[0],
                        upper_left[1],
                        lower_left[0],
                        lower_left[1],
                        lower_right[0],
                        lower_right[1],
                        upper_right[0],
                        upper_right[1],
                    ),
                )
            )
    return mesh


def transform(
    source: Path,
    destination: Path,
    strength: float,
    step: int,
    is_mask: bool,
) -> None:
    with Image.open(source) as opened:
        image = opened.convert("L" if is_mask else "RGB")
        mesh = build_mesh(image.width, image.height, strength, step)
        warped = image.transform(
            image.size,
            Image.MESH,
            mesh,
            resample=Image.NEAREST if is_mask else Image.BICUBIC,
        )
        if is_mask:
            warped = warped.point([0 if value < 128 else 255 for value in range(256)], mode="L")
        temporary = destination.with_name(destination.name + ".tmp")
        warped.save(temporary, format="PNG", compress_level=6)
    temporary.replace(destination)


def camera_for_name(name: str, metadata_by_stem: dict[str, dict[str, Any]]) -> str:
    stem = Path(name).stem.split("__", 1)[0]
    metadata = metadata_by_stem.get(stem)
    if not metadata:
        raise KeyError(f"No metadata for camera-model input {name}")
    return str(metadata["camera"])


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = config.get("camera_model", {})
    if not model.get("enabled"):
        print(f"CAMERA_MODEL_SKIPPED root={root}")
        return 0
    if model.get("profile") != "bounded_radial_barrel_v1":
        raise ValueError(f"Unsupported camera model: {model.get('profile')}")
    if model.get("depth_policy") != "reject_until_shared_exr_warp_is_implemented":
        raise ValueError("Camera-model depth policy must fail closed")
    depth_paths = sorted((root / "raw" / "depth").glob("*.exr"))
    if depth_paths:
        raise RuntimeError(
            "Depth exists but the bounded radial camera model has no shared EXR warp; "
            "rerun this detection release with DEPTH=0"
        )

    step = int(model["mesh_step_px"])
    if not 8 <= step <= 128:
        raise ValueError("camera_model.mesh_step_px must be in [8, 128]")
    camera_models = model["cameras"]
    for name, camera in config["cameras"].items():
        if name not in camera_models:
            raise ValueError(f"Missing camera-model settings for {name}")
        strength = float(camera_models[name]["radial_strength"])
        if not 0.0 <= strength <= 0.25:
            raise ValueError(f"Unsafe radial strength for {name}: {strength}")
        if float(camera["horizontal_fov_deg"]) < 100.0:
            raise ValueError(f"Raw FOV lacks camera-model overscan for {name}")

    metadata_paths = sorted((root / "raw" / "metadata").glob("*.json"))
    if not metadata_paths:
        raise FileNotFoundError("No raw metadata for camera model")
    metadata_by_stem = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in metadata_paths
    }

    config_digest = sha256(config_path)
    manifest_path = root / "raw" / "camera_model_manifest.json"
    if manifest_path.is_file():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("config_sha256") != config_digest:
            raise RuntimeError("Refusing to mutate an existing run with a different camera config")

    groups = (
        ("rgb", root / "raw" / "images", root / "raw" / "images_pre_camera_model", False),
        (
            "visible",
            root / "raw" / "masks_visible",
            root / "raw" / "masks_visible_pre_camera_model",
            True,
        ),
        (
            "amodal",
            root / "raw" / "masks_amodal",
            root / "raw" / "masks_amodal_pre_camera_model",
            True,
        ),
    )
    entries: dict[str, list[dict[str, Any]]] = {}
    for group_name, destination_dir, source_dir, is_mask in groups:
        sources = preserve_inputs(destination_dir, source_dir)
        group_entries = []
        for source in sources:
            destination = destination_dir / source.name
            camera = camera_for_name(source.name, metadata_by_stem)
            strength = float(camera_models[camera]["radial_strength"])
            transform(source, destination, strength, step, is_mask)
            group_entries.append(
                {
                    "name": source.name,
                    "camera": camera,
                    "radial_strength": strength,
                    "pre_camera_sha256": sha256(source),
                    "post_camera_sha256": sha256(destination),
                }
            )
        entries[group_name] = group_entries

    for path in metadata_paths:
        metadata = metadata_by_stem[path.stem]
        camera = str(metadata["camera"])
        metadata["camera_model"] = {
            "profile": model["profile"],
            "calibration_status": model["calibration_status"],
            "raw_horizontal_fov_deg": float(
                metadata.get("camera_realization", {}).get(
                    "horizontal_fov_deg",
                    config["cameras"][camera]["horizontal_fov_deg"],
                )
            ),
            "radial_strength": float(camera_models[camera]["radial_strength"]),
            "rgb_and_instance_masks_warped_together": True,
            "depth_status": "not_rendered",
        }
        path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "profile": model["profile"],
        "calibration_status": model["calibration_status"],
        "config_sha256": config_digest,
        "script_sha256": sha256(Path(__file__).resolve()),
        "mesh_step_px": step,
        "frame_count": len(entries["rgb"]),
        "visible_mask_count": len(entries["visible"]),
        "amodal_mask_count": len(entries["amodal"]),
        "rgb_and_instance_masks_warped_together": True,
        "depth_status": "not_rendered_fail_closed",
        "entries": entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "CAMERA_MODEL_OK "
        f"frames={manifest['frame_count']} masks="
        f"{manifest['visible_mask_count'] + manifest['amodal_mask_count']} root={root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
