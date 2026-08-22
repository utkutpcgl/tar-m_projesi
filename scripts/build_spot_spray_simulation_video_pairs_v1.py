#!/usr/bin/env python3
"""Build deterministic same-latent CropCraft ideal/degraded video pairs.

The builder deliberately treats CropCraft semantic connected components as
track *proxies*. They are stable across the shared image-plane trajectory but
are not botanical plant-instance annotations and must not be presented as real
capture evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "configs/simulation/spot_spray_simulation_video_pairs_v1.yaml"
)
CLASS_IDS = {"background": 0, "crop": 1, "weed": 2}


class ContractError(RuntimeError):
    """Raised when a frozen provenance or pairing contract is violated."""


@dataclass(frozen=True)
class SourceAsset:
    role: str
    scene_id: str
    source_frame: str
    scene_root: Path
    rgb_path: Path
    mask_path: Path
    field_description_path: Path
    scene_config_path: Path
    generation_receipt_path: Path
    provenance_rows: tuple[dict[str, Any], ...]


def sha256_file(path: str | Path) -> str:
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            )


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"Expected YAML mapping: {path}")
    return value


def resolve_path(value: str | Path, repo_root: Path = PROJECT_ROOT) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def file_row(path: Path, label: str, display_path: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "label": label,
        "path": display_path or str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_pinned_file(
    spec: dict[str, Any], label: str, repo_root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    path = resolve_path(str(spec["path"]), repo_root)
    row = file_row(path, label, str(spec["path"]))
    expected = str(spec["sha256"])
    if row["sha256"] != expected:
        raise ContractError(
            f"Pinned {label} hash changed: {row['sha256']} != {expected}"
        )
    return row


def _run_text(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ContractError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def audit_runtime(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    runtime = config["runtime_audit"]
    blender = runtime["blender"]
    blender_path = resolve_path(str(blender["path"]), repo_root)
    blender_row = file_row(blender_path, "blender", str(blender["path"]))
    if blender_row["sha256"] != str(blender["sha256"]):
        raise ContractError("Blender binary hash changed")
    blender_version = _run_text([str(blender_path), "--version"]).splitlines()[0]
    if not blender_version.startswith(str(blender["required_version_prefix"])):
        raise ContractError(f"Unexpected Blender version: {blender_version}")

    ffmpeg = runtime["ffmpeg"]
    ffmpeg_path = resolve_path(str(ffmpeg["path"]), repo_root)
    ffmpeg_row = file_row(ffmpeg_path, "ffmpeg", str(ffmpeg["path"]))
    if ffmpeg_row["sha256"] != str(ffmpeg["sha256"]):
        raise ContractError("ffmpeg binary hash changed")
    ffmpeg_version = _run_text([str(ffmpeg_path), "-version"]).splitlines()[0]
    if str(ffmpeg["required_version_substring"]) not in ffmpeg_version:
        raise ContractError(f"Unexpected ffmpeg version: {ffmpeg_version}")

    ffprobe_path = resolve_path(str(runtime["ffprobe"]["path"]), repo_root)
    ffprobe_row = file_row(
        ffprobe_path, "ffprobe", str(runtime["ffprobe"]["path"])
    )
    return {
        "blender": {**blender_row, "version": blender_version, "invoked_for_render": False},
        "ffmpeg": {**ffmpeg_row, "version": ffmpeg_version},
        "ffprobe": ffprobe_row,
        "python": {
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "pillow": Image.__version__,
        },
    }


def validate_provenance(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    provenance = config["provenance"]
    rows = [
        verify_pinned_file(provenance["cropcraft_v12_study"], "cropcraft_v12_study", repo_root),
        verify_pinned_file(provenance["sensor_motion_builder"], "sensor_motion_builder", repo_root),
        verify_pinned_file(provenance["product_architecture"], "product_architecture", repo_root),
        verify_pinned_file(
            provenance["product_architecture_config"],
            "product_architecture_config",
            repo_root,
        ),
    ]

    release_spec = provenance["cropcraft_v12_release"]
    release_path = resolve_path(str(release_spec["receipt"]), repo_root)
    release_row = file_row(
        release_path, "cropcraft_v12_release_receipt", str(release_spec["receipt"])
    )
    if release_row["sha256"] != str(release_spec["sha256"]):
        raise ContractError("CropCraft V12 release receipt hash changed")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if bool(release.get("all_quality_gates_passed")) is not bool(
        release_spec["required_all_quality_gates_passed"]
    ):
        raise ContractError("CropCraft V12 release quality gate is not accepted")
    rows.append(release_row)

    pack_spec = provenance["sensor_motion_pack"]
    pack_path = resolve_path(str(pack_spec["manifest"]), repo_root)
    pack_row = file_row(
        pack_path, "sensor_motion_pack_manifest", str(pack_spec["manifest"])
    )
    if pack_row["sha256"] != str(pack_spec["sha256"]):
        raise ContractError("Sensor-motion pack manifest hash changed")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    if pack.get("isolated_change") != pack_spec["required_isolated_change"]:
        raise ContractError("Sensor-motion isolated-change contract changed")
    rows.append(pack_row)

    architecture_path = resolve_path(
        str(provenance["product_architecture"]["path"]), repo_root
    )
    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    optics = architecture["baseline"]["sensor_optics"]
    capture = config["capture_contract"]
    if float(optics["acquisition_rate_hz"]) != float(capture["frame_rate_hz"]):
        raise ContractError("Configured frame rate diverges from product architecture")
    if list(optics["active_roi_px"]) != [2048, 2048]:
        raise ContractError("Unexpected frozen architecture ROI")
    if float(capture["source_gsd_mm_per_px"]) != 0.244140625:
        raise ContractError("Unexpected V12 tile GSD")
    return {
        "files": rows,
        "cropcraft_release": release,
        "sensor_motion_pack": pack,
        "architecture_capture": {
            "acquisition_rate_hz": optics["acquisition_rate_hz"],
            "active_roi_px": optics["active_roi_px"],
            "maximum_blur_px": optics["maximum_blur_px"],
            "trial_speeds_m_s": architecture["baseline"]["platform_carrier"][
                "trial_speeds_m_s"
            ],
        },
    }


def _find_unique(rows: list[dict[str, Any]], key: str, value: str, label: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get(key)) == value]
    if len(matches) != 1:
        raise ContractError(f"Expected one {label} for {key}={value}, found {len(matches)}")
    return matches[0]


def resolve_source_asset(
    sequence: dict[str, Any],
    config: dict[str, Any],
    provenance_state: dict[str, Any],
    repo_root: Path,
) -> SourceAsset:
    role = str(sequence["role"])
    scene_id = str(sequence["scene_id"])
    source_frame = str(sequence["source_frame"])
    release_spec = config["provenance"]["cropcraft_v12_release"]
    if role not in {str(value) for value in release_spec["permitted_roles"]}:
        raise ContractError(f"Source role is not permitted: {role}")

    release = provenance_state["cropcraft_release"]
    role_row = _find_unique(release["roles"], "role", role, "role receipt")
    role_receipt_path = resolve_path(str(role_row["receipt"]), repo_root)
    if sha256_file(role_receipt_path) != str(role_row["receipt_sha256"]):
        raise ContractError(f"Role receipt hash changed: {role}")
    role_receipt = json.loads(role_receipt_path.read_text(encoding="utf-8"))
    if not role_receipt.get("all_quality_gates_passed"):
        raise ContractError(f"Role quality gates failed: {role}")
    scene_row = _find_unique(role_receipt["scenes"], "scene", scene_id, "scene")

    release_root = resolve_path(str(release_spec["root"]), repo_root)
    scene_root = release_root / "roles" / role / "scenes" / scene_id
    generation_receipt_path = scene_root / "generation_receipt.json"
    if sha256_file(generation_receipt_path) != str(scene_row["receipt_sha256"]):
        raise ContractError(f"Scene generation receipt hash changed: {role}/{scene_id}")
    generation_receipt = json.loads(
        generation_receipt_path.read_text(encoding="utf-8")
    )
    if generation_receipt.get("returncode") != 0:
        raise ContractError(f"Source scene renderer did not report success: {role}/{scene_id}")
    if generation_receipt["validation"]["image_size"] != [1024, 1024]:
        raise ContractError("Source scene is not a native 1024 V12 tile")
    output_rows = {
        str(row["path"]): row for row in generation_receipt.get("outputs", [])
    }

    required = {
        "rgb": scene_root / f"render/images/{source_frame}.jpg",
        "semantic_mask": scene_root / f"render/masks/{source_frame}.png",
        "field_description": scene_root / "field_description.json",
        "scene_config": scene_root / "config.input.yaml",
    }
    required_rel = {
        "rgb": f"render/images/{source_frame}.jpg",
        "semantic_mask": f"render/masks/{source_frame}.png",
        "field_description": "field_description.json",
        "scene_config": "config.input.yaml",
    }
    provenance_rows: list[dict[str, Any]] = [
        file_row(
            role_receipt_path,
            "role_release_receipt",
            str(role_receipt_path),
        ),
        file_row(
            generation_receipt_path,
            "scene_generation_receipt",
            str(generation_receipt_path),
        ),
    ]
    for label, path in required.items():
        relative = required_rel[label]
        declared = output_rows.get(relative)
        if declared is None:
            raise ContractError(f"Source receipt does not declare {relative}")
        observed = file_row(path, label, str(path))
        if observed["sha256"] != str(declared["sha256"]):
            raise ContractError(f"Source output hash changed: {path}")
        if observed["bytes"] != int(declared["size_bytes"]):
            raise ContractError(f"Source output size changed: {path}")
        provenance_rows.append(observed)

    return SourceAsset(
        role=role,
        scene_id=scene_id,
        source_frame=source_frame,
        scene_root=scene_root,
        rgb_path=required["rgb"],
        mask_path=required["semantic_mask"],
        field_description_path=required["field_description"],
        scene_config_path=required["scene_config"],
        generation_receipt_path=generation_receipt_path,
        provenance_rows=tuple(provenance_rows),
    )


def load_palette(config: dict[str, Any]) -> dict[str, tuple[int, int, int]]:
    raw = config["capture_contract"]["semantic_palette_rgb"]
    palette: dict[str, tuple[int, int, int]] = {}
    for name in ("background", "crop", "weed"):
        values = tuple(int(value) for value in raw[name])
        if len(values) != 3 or any(value < 0 or value > 255 for value in values):
            raise ContractError(f"Invalid palette entry: {name}={values}")
        palette[name] = values
    if len(set(palette.values())) != len(palette):
        raise ContractError("Semantic palette colours must be unique")
    return palette


def semantic_class_map(
    mask_rgb: np.ndarray, palette: dict[str, tuple[int, int, int]]
) -> np.ndarray:
    if mask_rgb.ndim != 3 or mask_rgb.shape[2] != 3:
        raise ContractError("Expected RGB semantic mask")
    class_map = np.full(mask_rgb.shape[:2], 255, dtype=np.uint8)
    for name, colour in palette.items():
        class_map[np.all(mask_rgb == colour, axis=2)] = CLASS_IDS[name]
    if np.any(class_map == 255):
        unexpected = np.unique(mask_rgb[class_map == 255], axis=0)
        raise ContractError(f"Unexpected semantic mask colours: {unexpected[:8].tolist()}")
    return class_map


def build_track_proxy(
    class_map: np.ndarray, connectivity: int, minimum_component_pixels: int
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, int]]:
    if connectivity not in (4, 8):
        raise ContractError("Track proxy connectivity must be 4 or 8")
    tracks = np.zeros(class_map.shape, dtype=np.uint16)
    records: list[dict[str, Any]] = []
    dropped = {"crop": 0, "weed": 0}
    next_track_id = 1
    for class_name in ("crop", "weed"):
        class_id = CLASS_IDS[class_name]
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            (class_map == class_id).astype(np.uint8), connectivity=connectivity
        )
        components: list[tuple[int, int, int, int, int, int]] = []
        for label_id in range(1, count):
            x, y, width, height, area = (
                int(value) for value in stats[label_id].tolist()
            )
            if area < minimum_component_pixels:
                dropped[class_name] += 1
                continue
            components.append((y, x, -area, label_id, width, height))
        components.sort()
        for y, x, negative_area, label_id, width, height in components:
            if next_track_id > np.iinfo(np.uint16).max:
                raise ContractError("Too many semantic component track proxies")
            area = -negative_area
            tracks[labels == label_id] = next_track_id
            records.append(
                {
                    "track_id": next_track_id,
                    "class_id": class_id,
                    "class_name": class_name,
                    "source_bbox_xywh_px": [x, y, width, height],
                    "source_area_px": area,
                    "identity_basis": "source_semantic_connected_component_proxy",
                    "botanical_instance_ground_truth": False,
                }
            )
            next_track_id += 1
    return tracks, records, dropped


def translate_integer(array: np.ndarray, dx: int, dy: int, fill: Any) -> np.ndarray:
    height, width = array.shape[:2]
    if abs(dx) >= width or abs(dy) >= height:
        raise ContractError(f"Translation leaves no source pixels: dx={dx}, dy={dy}")
    output = np.empty_like(array)
    output[...] = fill
    source_x0 = max(0, -dx)
    source_x1 = min(width, width - dx)
    source_y0 = max(0, -dy)
    source_y1 = min(height, height - dy)
    target_x0 = source_x0 + dx
    target_x1 = source_x1 + dx
    target_y0 = source_y0 + dy
    target_y1 = source_y1 + dy
    output[target_y0:target_y1, target_x0:target_x1] = array[
        source_y0:source_y1, source_x0:source_x1
    ]
    return output


def trajectory_offsets(sequence: dict[str, Any]) -> list[tuple[int, int]]:
    frame_count = int(sequence["frame_count"])
    if frame_count < 2:
        raise ContractError("Each sequence must contain at least two frames")
    trajectory = sequence["trajectory"]
    x_step = int(trajectory["x_step_px"])
    amplitude = float(trajectory["y_amplitude_px"])
    phase = float(trajectory["y_phase_rad"])
    centre = (frame_count - 1) / 2.0
    return [
        (
            int(round((index - centre) * x_step)),
            int(round(amplitude * math.sin(phase + 2.0 * math.pi * index / frame_count))),
        )
        for index in range(frame_count)
    ]


def border_soil_colour(rgb: np.ndarray, class_map: np.ndarray) -> tuple[int, int, int]:
    width = min(64, rgb.shape[0] // 4, rgb.shape[1] // 4)
    edge = np.zeros(class_map.shape, dtype=bool)
    edge[:width, :] = True
    edge[-width:, :] = True
    edge[:, :width] = True
    edge[:, -width:] = True
    candidates = rgb[edge & (class_map == CLASS_IDS["background"])]
    if candidates.size == 0:
        candidates = rgb[class_map == CLASS_IDS["background"]]
    if candidates.size == 0:
        raise ContractError("Source frame has no semantic background for trajectory fill")
    median = np.rint(np.median(candidates, axis=0)).astype(np.uint8)
    return tuple(int(value) for value in median)


def image_gradient_mean(rgb: np.ndarray) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.sqrt(gx * gx + gy * gy).mean())


def apply_degraded_capture(
    latent_rgb: np.ndarray,
    frame_index: int,
    frame_count: int,
    sequence_seed: int,
    condition: dict[str, Any],
    kernel: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    working = latent_rgb.astype(np.float32) / 255.0
    working = cv2.filter2D(
        working, -1, kernel.astype(np.float32), borderType=cv2.BORDER_REFLECT_101
    )

    height, width = working.shape[:2]
    yy, xx = np.indices((height, width), dtype=np.float32)
    nx = (xx - (width - 1) / 2.0) / max((width - 1) / 2.0, 1.0)
    ny = (yy - (height - 1) / 2.0) / max((height - 1) / 2.0, 1.0)
    radius = np.clip((nx * nx + ny * ny) / 2.0, 0.0, 1.0)
    falloff = 1.0 - float(condition["radial_falloff_strength"]) * radius
    working *= falloff[:, :, None]

    phase = math.radians(sequence_seed % 360)
    gain = float(condition["gain_base"]) + float(condition["gain_amplitude"]) * math.sin(
        phase + 2.0 * math.pi * frame_index / frame_count
    )
    white_balance = np.asarray(condition["white_balance_rgb"], dtype=np.float32)
    working *= gain * white_balance[None, None, :]
    working = np.power(np.clip(working, 0.0, 1.0), float(condition["gamma"]))

    noise_seed = int(sequence_seed) * 1_000_003 + frame_index * 97
    rng = np.random.default_rng(noise_seed)
    sigma = float(condition["read_noise_sigma_dn"]) / 255.0
    working += rng.normal(0.0, sigma, working.shape).astype(np.float32)
    degraded = np.clip(np.rint(working * 255.0), 0, 255).astype(np.uint8)
    return degraded, {
        "gain": gain,
        "white_balance_rgb": [float(value) for value in white_balance],
        "gamma": float(condition["gamma"]),
        "radial_falloff_strength": float(condition["radial_falloff_strength"]),
        "read_noise_sigma_dn": float(condition["read_noise_sigma_dn"]),
        "noise_seed": noise_seed,
    }


def save_rgb_png(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array.astype(np.uint8)).save(
        path, format="PNG", compress_level=6, optimize=False
    )


def save_track_png(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array.astype(np.uint16)).save(
        path, format="PNG", compress_level=6, optimize=False
    )


def hardlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    os.link(source, destination)


def visible_track_rows(
    track_mask: np.ndarray, track_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {int(row["track_id"]): row for row in track_records}
    rows: list[dict[str, Any]] = []
    for track_id in sorted(int(value) for value in np.unique(track_mask) if value):
        ys, xs = np.nonzero(track_mask == track_id)
        source = by_id[track_id]
        rows.append(
            {
                "track_id": track_id,
                "class_id": int(source["class_id"]),
                "class_name": source["class_name"],
                "visible_area_px": int(len(xs)),
                "visible_bbox_xywh_px": [
                    int(xs.min()),
                    int(ys.min()),
                    int(xs.max() - xs.min() + 1),
                    int(ys.max() - ys.min() + 1),
                ],
            }
        )
    return rows


def verify_track_alignment(
    track_mask: np.ndarray,
    class_map: np.ndarray,
    track_records: list[dict[str, Any]],
) -> bool:
    by_id = {int(row["track_id"]): int(row["class_id"]) for row in track_records}
    for track_id in (int(value) for value in np.unique(track_mask) if value):
        if track_id not in by_id:
            return False
        if np.any(class_map[track_mask == track_id] != by_id[track_id]):
            return False
    return True


def encode_rgb_video(
    ffmpeg: Path,
    frames_directory: Path,
    output_path: Path,
    frame_count: int,
    frame_rate: int,
    encoding: dict[str, Any],
) -> None:
    command = [
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "+bitexact",
        "-framerate",
        str(frame_rate),
        "-start_number",
        "0",
        "-i",
        str(frames_directory / "frame_%06d.png"),
        "-frames:v",
        str(frame_count),
        "-an",
        "-c:v",
        str(encoding["codec"]),
        "-preset",
        str(encoding["preset"]),
        "-crf",
        str(encoding["crf"]),
        "-pix_fmt",
        str(encoding["pixel_format"]),
        "-threads",
        str(encoding["deterministic_threads"]),
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        "-n",
        str(output_path),
    ]
    _run_text(command)


def encode_semantic_video(
    ffmpeg: Path,
    frames_directory: Path,
    output_path: Path,
    frame_count: int,
    frame_rate: int,
    encoding: dict[str, Any],
) -> None:
    command = [
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "+bitexact",
        "-framerate",
        str(frame_rate),
        "-start_number",
        "0",
        "-i",
        str(frames_directory / "frame_%06d.png"),
        "-frames:v",
        str(frame_count),
        "-an",
        "-c:v",
        str(encoding["codec"]),
        "-level",
        str(encoding["level"]),
        "-pix_fmt",
        str(encoding["pixel_format"]),
        "-threads",
        str(encoding["deterministic_threads"]),
        "-flags:v",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-f",
        str(encoding["container"]),
        "-n",
        str(output_path),
    ]
    _run_text(command)


def probe_video(ffprobe: Path, path: Path) -> dict[str, Any]:
    payload = json.loads(
        _run_text(
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_read_frames,pix_fmt,codec_name",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    streams = payload.get("streams", [])
    if len(streams) != 1:
        raise ContractError(f"Expected one video stream: {path}")
    stream = streams[0]
    return {
        "path": path.name,
        "codec_name": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "average_frame_rate": str(stream["avg_frame_rate"]),
        "decoded_frame_count": int(stream["nb_read_frames"]),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_semantic_video_roundtrip(
    ffmpeg: Path,
    video_path: Path,
    expected_paths: list[Path],
) -> bool:
    with tempfile.TemporaryDirectory(prefix="spot-spray-mask-decode-") as temporary:
        root = Path(temporary)
        _run_text(
            [
                str(ffmpeg),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vsync",
                "0",
                "-start_number",
                "0",
                str(root / "frame_%06d.png"),
            ]
        )
        decoded = sorted(root.glob("frame_*.png"))
        if len(decoded) != len(expected_paths):
            return False
        for observed, expected in zip(decoded, expected_paths):
            observed_rgb = np.asarray(Image.open(observed).convert("RGB"), dtype=np.uint8)
            expected_rgb = np.asarray(Image.open(expected).convert("RGB"), dtype=np.uint8)
            if not np.array_equal(observed_rgb, expected_rgb):
                return False
    return True


def build_contact_sheet(
    output_path: Path,
    ideal_paths: list[Path],
    degraded_paths: list[Path],
    semantic_paths: list[Path],
) -> None:
    selected = sorted({0, len(ideal_paths) // 2, len(ideal_paths) - 1})
    tile = 288
    header = 26
    canvas = Image.new("RGB", (tile * 3, (tile + header) * len(selected)), "white")
    draw = ImageDraw.Draw(canvas)
    for row_index, frame_index in enumerate(selected):
        ideal = np.asarray(Image.open(ideal_paths[frame_index]).convert("RGB"), dtype=np.uint8)
        degraded = np.asarray(
            Image.open(degraded_paths[frame_index]).convert("RGB"), dtype=np.uint8
        )
        semantic = np.asarray(
            Image.open(semantic_paths[frame_index]).convert("RGB"), dtype=np.uint8
        )
        foreground = np.any(semantic != 0, axis=2)
        overlay = ideal.copy()
        overlay[foreground] = np.rint(
            ideal[foreground].astype(np.float32) * 0.55
            + semantic[foreground].astype(np.float32) * 0.45
        ).astype(np.uint8)
        for column, (label, image) in enumerate(
            (("ideal", ideal), ("degraded", degraded), ("shared mask overlay", overlay))
        ):
            x = column * tile
            y = row_index * (tile + header)
            draw.rectangle((x, y, x + tile, y + header), fill=(20, 20, 20))
            draw.text((x + 6, y + 6), f"f{frame_index:03d} {label}", fill="white")
            resized = Image.fromarray(image).resize(
                (tile, tile), Image.Resampling.BILINEAR
            )
            canvas.paste(resized, (x, y + header))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", compress_level=6, optimize=False)


def output_inventory(root: Path, excluded_names: set[str] | None = None) -> list[dict[str, Any]]:
    excluded_names = excluded_names or set()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in excluded_names:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def storage_usage(root: Path) -> dict[str, int]:
    logical = 0
    unique = 0
    seen: set[tuple[int, int]] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        logical += stat.st_size
        identity = (stat.st_dev, stat.st_ino)
        if identity not in seen:
            seen.add(identity)
            unique += stat.st_size
    return {
        "logical_bytes_including_hardlinks": logical,
        "unique_file_bytes": unique,
        "unique_inodes": len(seen),
    }


def _kernel_state(
    config: dict[str, Any], provenance_state: dict[str, Any], repo_root: Path
) -> dict[str, dict[str, Any]]:
    pack_spec = config["provenance"]["sensor_motion_pack"]
    pack_root = resolve_path(str(pack_spec["root"]), repo_root)
    pack = provenance_state["sensor_motion_pack"]
    by_id = {str(row["kernel_id"]): row for row in pack["kernel_bank"]}
    selected: dict[str, dict[str, Any]] = {}
    for kernel_id in config["conditions"]["degraded"]["psf_ids"]:
        row = by_id.get(str(kernel_id))
        if row is None:
            raise ContractError(f"Unknown sensor-motion PSF: {kernel_id}")
        path = pack_root / str(row["npy"])
        observed = sha256_file(path)
        if observed != str(row["npy_sha256"]):
            raise ContractError(f"Sensor-motion PSF hash changed: {kernel_id}")
        kernel = np.load(path, allow_pickle=False)
        if kernel.shape != tuple(row["shape"]) or not np.isclose(kernel.sum(), 1.0, atol=1e-6):
            raise ContractError(f"Invalid sensor-motion PSF: {kernel_id}")
        selected[str(kernel_id)] = {
            "path": path,
            "manifest": row,
            "kernel": kernel.astype(np.float32),
        }
    return selected


def build_sequence(
    destination: Path,
    sequence: dict[str, Any],
    config: dict[str, Any],
    provenance_state: dict[str, Any],
    runtime_state: dict[str, Any],
    kernels: dict[str, dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    sequence_id = str(sequence["sequence_id"])
    sequence_root = destination / "sequences" / sequence_id
    sequence_root.mkdir(parents=True, exist_ok=False)
    source = resolve_source_asset(sequence, config, provenance_state, repo_root)
    palette = load_palette(config)
    rgb = np.asarray(Image.open(source.rgb_path).convert("RGB"), dtype=np.uint8)
    mask_rgb = np.asarray(Image.open(source.mask_path).convert("RGB"), dtype=np.uint8)
    capture = config["capture_contract"]
    expected_shape = (int(capture["height_px"]), int(capture["width_px"]), 3)
    if rgb.shape != expected_shape or mask_rgb.shape != expected_shape:
        raise ContractError(
            f"Source frame shape mismatch: {rgb.shape}/{mask_rgb.shape} != {expected_shape}"
        )
    class_map = semantic_class_map(mask_rgb, palette)
    track_spec = capture["track_proxy"]
    source_tracks, track_records, dropped = build_track_proxy(
        class_map,
        int(track_spec["connectivity"]),
        int(track_spec["minimum_component_pixels"]),
    )
    weed_track_count = sum(row["class_name"] == "weed" for row in track_records)
    if weed_track_count < int(config["quality_gates"]["minimum_weed_tracks_per_sequence"]):
        raise ContractError(f"Source has insufficient weed track proxies: {sequence_id}")
    fill_colour = border_soil_colour(rgb, class_map)
    offsets = trajectory_offsets(sequence)

    directories = {
        "latent_rgb": sequence_root / "latent/rgb",
        "ground_semantic": sequence_root / "ground_truth/semantic_masks",
        "ground_tracks": sequence_root / "ground_truth/track_masks",
        "ideal_rgb": sequence_root / "ideal/rgb",
        "ideal_semantic": sequence_root / "ideal/semantic_masks",
        "ideal_tracks": sequence_root / "ideal/track_masks",
        "degraded_rgb": sequence_root / "degraded/rgb",
        "degraded_semantic": sequence_root / "degraded/semantic_masks",
        "degraded_tracks": sequence_root / "degraded/track_masks",
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=False)

    condition = config["conditions"]["degraded"]
    kernel_ids = [str(value) for value in condition["psf_ids"]]
    frame_rows: list[dict[str, Any]] = []
    ideal_paths: list[Path] = []
    degraded_paths: list[Path] = []
    semantic_paths: list[Path] = []
    rmse_values: list[float] = []
    changed_values: list[float] = []
    gradient_ratios: list[float] = []
    mean_brightness_values: list[float] = []
    clipped_black_values: list[float] = []
    clipped_white_values: list[float] = []
    trajectory_fill_values: list[float] = []
    track_alignment = True
    masks_identical = True
    tracks_identical = True
    latent_ideal_identical = True
    degraded_different = True
    semantic_palette_valid = True
    frame_rate = int(capture["frame_rate_hz"])

    for frame_index, (dx, dy) in enumerate(offsets):
        stem = f"frame_{frame_index:06d}"
        latent = translate_integer(rgb, dx, dy, fill_colour)
        semantic = translate_integer(mask_rgb, dx, dy, palette["background"])
        frame_class_map = semantic_class_map(semantic, palette)
        track_mask = translate_integer(source_tracks, dx, dy, 0)
        kernel_id = kernel_ids[frame_index % len(kernel_ids)]
        kernel_state = kernels[kernel_id]
        degraded, operator_state = apply_degraded_capture(
            latent,
            frame_index,
            len(offsets),
            int(sequence["seed"]),
            condition,
            kernel_state["kernel"],
        )

        latent_path = directories["latent_rgb"] / f"{stem}.png"
        ideal_path = directories["ideal_rgb"] / f"{stem}.png"
        degraded_path = directories["degraded_rgb"] / f"{stem}.png"
        ground_semantic_path = directories["ground_semantic"] / f"{stem}.png"
        ground_track_path = directories["ground_tracks"] / f"{stem}.png"
        ideal_semantic_path = directories["ideal_semantic"] / f"{stem}.png"
        degraded_semantic_path = directories["degraded_semantic"] / f"{stem}.png"
        ideal_track_path = directories["ideal_tracks"] / f"{stem}.png"
        degraded_track_path = directories["degraded_tracks"] / f"{stem}.png"

        save_rgb_png(latent_path, latent)
        hardlink(latent_path, ideal_path)
        save_rgb_png(degraded_path, degraded)
        save_rgb_png(ground_semantic_path, semantic)
        save_track_png(ground_track_path, track_mask)
        hardlink(ground_semantic_path, ideal_semantic_path)
        hardlink(ground_semantic_path, degraded_semantic_path)
        hardlink(ground_track_path, ideal_track_path)
        hardlink(ground_track_path, degraded_track_path)

        latent_hash = sha256_file(latent_path)
        ideal_hash = sha256_file(ideal_path)
        degraded_hash = sha256_file(degraded_path)
        semantic_hash = sha256_file(ground_semantic_path)
        track_hash = sha256_file(ground_track_path)
        latent_ideal_identical &= latent_hash == ideal_hash
        degraded_different &= degraded_hash != ideal_hash
        masks_identical &= (
            semantic_hash
            == sha256_file(ideal_semantic_path)
            == sha256_file(degraded_semantic_path)
        )
        tracks_identical &= (
            track_hash
            == sha256_file(ideal_track_path)
            == sha256_file(degraded_track_path)
        )
        semantic_palette_valid &= set(np.unique(frame_class_map).tolist()) <= {0, 1, 2}
        track_alignment &= verify_track_alignment(
            track_mask, frame_class_map, track_records
        )

        delta = degraded.astype(np.float32) - latent.astype(np.float32)
        rmse = float(np.sqrt(np.mean(delta * delta)))
        changed = float(np.any(degraded != latent, axis=2).mean())
        ideal_gradient = image_gradient_mean(latent)
        degraded_gradient = image_gradient_mean(degraded)
        gradient_ratio = degraded_gradient / max(ideal_gradient, 1e-12)
        condition_frames = (latent, degraded)
        frame_brightness = [float(value.mean()) for value in condition_frames]
        frame_clipped_black = [
            float(np.all(value <= 5, axis=2).mean()) for value in condition_frames
        ]
        frame_clipped_white = [
            float(np.all(value >= 250, axis=2).mean()) for value in condition_frames
        ]
        trajectory_fill_fraction = 1.0 - (
            (latent.shape[1] - abs(dx)) * (latent.shape[0] - abs(dy))
        ) / float(latent.shape[0] * latent.shape[1])
        rmse_values.append(rmse)
        changed_values.append(changed)
        gradient_ratios.append(gradient_ratio)
        mean_brightness_values.extend(frame_brightness)
        clipped_black_values.extend(frame_clipped_black)
        clipped_white_values.extend(frame_clipped_white)
        trajectory_fill_values.append(trajectory_fill_fraction)
        visible_tracks = visible_track_rows(track_mask, track_records)
        frame_rows.append(
            {
                "frame_index": frame_index,
                "frame_id": f"{sequence_id}_{stem}",
                "timestamp_ns": int(round(frame_index * 1_000_000_000 / frame_rate)),
                "shared_trajectory_offset_px": [dx, dy],
                "latent_rgb": {
                    "path": latent_path.relative_to(sequence_root).as_posix(),
                    "sha256": latent_hash,
                },
                "ideal_rgb": {
                    "path": ideal_path.relative_to(sequence_root).as_posix(),
                    "sha256": ideal_hash,
                },
                "degraded_rgb": {
                    "path": degraded_path.relative_to(sequence_root).as_posix(),
                    "sha256": degraded_hash,
                },
                "shared_semantic_mask": {
                    "path": ground_semantic_path.relative_to(sequence_root).as_posix(),
                    "sha256": semantic_hash,
                    "condition_paths": [
                        ideal_semantic_path.relative_to(sequence_root).as_posix(),
                        degraded_semantic_path.relative_to(sequence_root).as_posix(),
                    ],
                },
                "shared_track_proxy_mask": {
                    "path": ground_track_path.relative_to(sequence_root).as_posix(),
                    "sha256": track_hash,
                    "condition_paths": [
                        ideal_track_path.relative_to(sequence_root).as_posix(),
                        degraded_track_path.relative_to(sequence_root).as_posix(),
                    ],
                },
                "visible_track_proxies": visible_tracks,
                "degraded_operators": {
                    **operator_state,
                    "psf_id": kernel_id,
                    "psf_sha256": kernel_state["manifest"]["npy_sha256"],
                    "psf_declared_length_px": float(
                        kernel_state["manifest"]["declared_length_px"]
                    ),
                },
                "pair_metrics": {
                    "rgb_rmse": rmse,
                    "changed_rgb_pixel_fraction": changed,
                    "degraded_to_ideal_gradient_ratio": gradient_ratio,
                    "ideal_mean_brightness": frame_brightness[0],
                    "degraded_mean_brightness": frame_brightness[1],
                    "maximum_fully_clipped_black_fraction": max(frame_clipped_black),
                    "maximum_fully_clipped_white_fraction": max(frame_clipped_white),
                    "trajectory_fill_fraction": trajectory_fill_fraction,
                    "crop_pixels": int((frame_class_map == CLASS_IDS["crop"]).sum()),
                    "weed_pixels": int((frame_class_map == CLASS_IDS["weed"]).sum()),
                    "tracked_foreground_pixels": int((track_mask > 0).sum()),
                },
            }
        )
        ideal_paths.append(ideal_path)
        degraded_paths.append(degraded_path)
        semantic_paths.append(ground_semantic_path)

    frame_manifest_path = sequence_root / "frame_manifest.jsonl"
    track_manifest_path = sequence_root / "track_manifest.json"
    write_jsonl(frame_manifest_path, frame_rows)
    write_json(
        track_manifest_path,
        {
            "schema_version": 1,
            "sequence_id": sequence_id,
            "identity_basis": "source_semantic_connected_component_proxy",
            "botanical_instance_ground_truth": False,
            "connectivity": int(track_spec["connectivity"]),
            "minimum_component_pixels": int(track_spec["minimum_component_pixels"]),
            "dropped_small_components": dropped,
            "tracks": track_records,
        },
    )

    ffmpeg = Path(runtime_state["ffmpeg"]["path"])
    ffprobe = Path(runtime_state["ffprobe"]["path"])
    rgb_encoding = config["encoding"]["rgb_video"]
    semantic_encoding = config["encoding"]["semantic_video"]
    ideal_video = sequence_root / "ideal/rgb.mp4"
    degraded_video = sequence_root / "degraded/rgb.mp4"
    semantic_suffix = str(semantic_encoding["container"])
    ideal_semantic_video = sequence_root / f"ideal/semantic_masks_ffv1.{semantic_suffix}"
    degraded_semantic_video = sequence_root / f"degraded/semantic_masks_ffv1.{semantic_suffix}"
    encode_rgb_video(
        ffmpeg,
        directories["ideal_rgb"],
        ideal_video,
        len(offsets),
        frame_rate,
        rgb_encoding,
    )
    encode_rgb_video(
        ffmpeg,
        directories["degraded_rgb"],
        degraded_video,
        len(offsets),
        frame_rate,
        rgb_encoding,
    )
    encode_semantic_video(
        ffmpeg,
        directories["ground_semantic"],
        ideal_semantic_video,
        len(offsets),
        frame_rate,
        semantic_encoding,
    )
    hardlink(ideal_semantic_video, degraded_semantic_video)

    probes = {
        "ideal_rgb": probe_video(ffprobe, ideal_video),
        "degraded_rgb": probe_video(ffprobe, degraded_video),
        "ideal_semantic": probe_video(ffprobe, ideal_semantic_video),
        "degraded_semantic": probe_video(ffprobe, degraded_semantic_video),
    }
    dimensions_ok = all(
        row["width"] == int(capture["width_px"])
        and row["height"] == int(capture["height_px"])
        and row["decoded_frame_count"] == len(offsets)
        and row["average_frame_rate"] == f"{frame_rate}/1"
        for row in probes.values()
    )
    semantic_video_shared = (
        probes["ideal_semantic"]["sha256"]
        == probes["degraded_semantic"]["sha256"]
    )
    semantic_roundtrip = verify_semantic_video_roundtrip(
        ffmpeg, ideal_semantic_video, semantic_paths
    )
    contact_sheet_path = sequence_root / "qc_contact_sheet.png"
    build_contact_sheet(
        contact_sheet_path, ideal_paths, degraded_paths, semantic_paths
    )

    source_reference_path = sequence_root / "source_reference.json"
    source_reference = {
        "role": source.role,
        "scene_id": source.scene_id,
        "source_frame": source.source_frame,
        "rows": list(source.provenance_rows),
        "source_contract_sha256": canonical_sha256(list(source.provenance_rows)),
    }
    write_json(source_reference_path, source_reference)

    gates = {
        "latent_and_ideal_rgb_byte_identical": latent_ideal_identical,
        "degraded_rgb_differs_from_ideal_every_frame": degraded_different,
        "condition_semantic_masks_byte_identical": masks_identical,
        "condition_track_masks_byte_identical": tracks_identical,
        "semantic_palette_preserved": semantic_palette_valid,
        "track_proxy_pixels_align_with_semantic_class": track_alignment,
        "minimum_degraded_rgb_rmse": min(rmse_values)
        >= float(config["quality_gates"]["minimum_degraded_rgb_rmse"]),
        "minimum_changed_rgb_pixel_fraction": min(changed_values)
        >= float(config["quality_gates"]["minimum_changed_rgb_pixel_fraction"]),
        "frame_mean_brightness_within_v12_bounds": min(mean_brightness_values)
        >= float(config["quality_gates"]["minimum_frame_mean_brightness"])
        and max(mean_brightness_values)
        <= float(config["quality_gates"]["maximum_frame_mean_brightness"]),
        "fully_clipped_black_fraction_within_v12_bound": max(clipped_black_values)
        <= float(config["quality_gates"]["maximum_fully_clipped_black_fraction"]),
        "fully_clipped_white_fraction_within_v12_bound": max(clipped_white_values)
        <= float(config["quality_gates"]["maximum_fully_clipped_white_fraction"]),
        "trajectory_fill_fraction_bounded": max(trajectory_fill_values)
        <= float(config["quality_gates"]["maximum_trajectory_fill_fraction"]),
        "minimum_weed_tracks": weed_track_count
        >= int(config["quality_gates"]["minimum_weed_tracks_per_sequence"]),
        "all_videos_decodable_with_exact_timing_and_shape": dimensions_ok,
        "semantic_video_shared_byte_identically": semantic_video_shared,
        "semantic_video_lossless_roundtrip": semantic_roundtrip,
    }
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise ContractError(f"Sequence quality gates failed ({sequence_id}): {failed}")

    pair_manifest_path = sequence_root / "pair_manifest.json"
    pair_manifest = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "sequence_id": sequence_id,
        "profile_role": source.role,
        "latent_scene_id": f"cropcraft_v12/{source.role}/{source.scene_id}/{source.source_frame}",
        "frame_count": len(offsets),
        "frame_rate_hz": frame_rate,
        "frame_timing_policy": "exact_integer_nanosecond_schedule_shared_by_conditions",
        "shared": {
            "source_scene_and_plant_geometry": True,
            "image_plane_trajectory": True,
            "frame_timing": True,
            "semantic_ground_truth": True,
            "track_proxy_ids": True,
        },
        "condition_difference_scope": "declared_rgb_capture_operators_only",
        "condition_lock": config["conditions"],
        "condition_lock_sha256": canonical_sha256(config["conditions"]),
        "trajectory": {
            "offsets_px": [list(value) for value in offsets],
            "policy": capture["trajectory_policy"],
            "metric_platform_motion_calibrated": False,
        },
        "source_reference": {
            "path": source_reference_path.relative_to(sequence_root).as_posix(),
            "sha256": sha256_file(source_reference_path),
            "source_contract_sha256": source_reference["source_contract_sha256"],
        },
        "track_proxy": {
            "manifest": track_manifest_path.relative_to(sequence_root).as_posix(),
            "manifest_sha256": sha256_file(track_manifest_path),
            "track_count": len(track_records),
            "weed_track_count": weed_track_count,
            "botanical_instance_ground_truth": False,
            "limitation": track_spec["limitation"],
        },
        "frames": {
            "manifest": frame_manifest_path.relative_to(sequence_root).as_posix(),
            "manifest_sha256": sha256_file(frame_manifest_path),
        },
        "videos": {
            "ideal_rgb": probes["ideal_rgb"],
            "degraded_rgb": probes["degraded_rgb"],
            "ideal_semantic": probes["ideal_semantic"],
            "degraded_semantic": probes["degraded_semantic"],
        },
        "pair_metrics": {
            "rgb_rmse": {
                "minimum": min(rmse_values),
                "mean": float(np.mean(rmse_values)),
                "maximum": max(rmse_values),
            },
            "changed_rgb_pixel_fraction": {
                "minimum": min(changed_values),
                "mean": float(np.mean(changed_values)),
                "maximum": max(changed_values),
            },
            "degraded_to_ideal_gradient_ratio": {
                "minimum": min(gradient_ratios),
                "mean": float(np.mean(gradient_ratios)),
                "maximum": max(gradient_ratios),
            },
            "frame_mean_brightness": {
                "minimum": min(mean_brightness_values),
                "mean": float(np.mean(mean_brightness_values)),
                "maximum": max(mean_brightness_values),
            },
            "fully_clipped_black_fraction_maximum": max(clipped_black_values),
            "fully_clipped_white_fraction_maximum": max(clipped_white_values),
            "trajectory_fill_fraction_maximum": max(trajectory_fill_values),
        },
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "claim_boundary": config["claim_boundary"],
        "qc_contact_sheet": {
            "path": contact_sheet_path.relative_to(sequence_root).as_posix(),
            "sha256": sha256_file(contact_sheet_path),
        },
    }
    write_json(pair_manifest_path, pair_manifest)
    return {
        "sequence_id": sequence_id,
        "pair_manifest": pair_manifest_path.relative_to(destination).as_posix(),
        "pair_manifest_sha256": sha256_file(pair_manifest_path),
        "contact_sheet": contact_sheet_path.relative_to(destination).as_posix(),
        "contact_sheet_sha256": sha256_file(contact_sheet_path),
        "frame_count": len(offsets),
        "weed_track_proxy_count": weed_track_count,
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "pair_metrics": pair_manifest["pair_metrics"],
    }


def _reject_protected_target(target: Path, protected_roots: list[Path]) -> None:
    resolved = target.resolve()
    for protected in protected_roots:
        protected = protected.resolve()
        if (
            resolved == protected
            or protected in resolved.parents
            or resolved in protected.parents
        ):
            raise ContractError(f"Output target collides with protected input: {target}")


def build_release(
    config_path: Path,
    profile_name: str,
    repo_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_yaml_mapping(config_path)
    if int(config.get("schema_version", -1)) != 1:
        raise ContractError("Unsupported pair-generator schema version")
    if config.get("status") != "SYNTHETIC_PAIRED_DIAGNOSTIC_ONLY":
        raise ContractError("Synthetic-only claim boundary is not frozen")
    if config["claim_boundary"].get("outcome_targeting_forbidden") is not True:
        raise ContractError("Outcome-targeting prohibition must be explicit")
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        raise ContractError(f"Unknown profile: {profile_name}")
    profile = profiles[profile_name]
    sequence_ids = [str(row["sequence_id"]) for row in profile["sequences"]]
    if len(sequence_ids) != len(set(sequence_ids)) or not sequence_ids:
        raise ContractError("Profile sequence IDs must be non-empty and unique")

    output_root = resolve_path(str(config["outputs"]["release_root"]), repo_root)
    results_root = resolve_path(str(config["outputs"]["results_root"]), repo_root)
    destination = output_root / str(profile["output_directory"])
    result_destination = results_root / str(profile["output_directory"])
    if destination.exists() or result_destination.exists():
        existing = destination if destination.exists() else result_destination
        raise FileExistsError(f"Refusing to overwrite existing release evidence: {existing}")
    source_root = resolve_path(
        str(config["provenance"]["cropcraft_v12_release"]["root"]), repo_root
    )
    sensor_root = resolve_path(
        str(config["provenance"]["sensor_motion_pack"]["root"]), repo_root
    )
    _reject_protected_target(destination, [source_root, sensor_root])
    _reject_protected_target(result_destination, [source_root, sensor_root])

    output_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(output_root).free
    maximum_bytes = int(profile["maximum_unique_output_bytes"])
    minimum_free_after = int(config["quality_gates"]["minimum_free_bytes_after"])
    if free_before - maximum_bytes < minimum_free_after:
        raise ContractError(
            "Insufficient data-disk budget for declared worst-case profile output"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{profile_name}-", dir=output_root))
    result_staging = Path(
        tempfile.mkdtemp(prefix=f".{profile_name}-", dir=results_root)
    )
    try:
        provenance_state = validate_provenance(config, repo_root)
        runtime_state = audit_runtime(config, repo_root)
        kernels = _kernel_state(config, provenance_state, repo_root)
        sequence_rows = [
            build_sequence(
                staging,
                sequence,
                config,
                provenance_state,
                runtime_state,
                kernels,
                repo_root,
            )
            for sequence in profile["sequences"]
        ]
        usage = storage_usage(staging)
        free_after_build = shutil.disk_usage(output_root).free
        release_gates = {
            "all_sequence_quality_gates_passed": all(
                row["all_quality_gates_passed"] for row in sequence_rows
            ),
            "unique_output_within_profile_budget": usage["unique_file_bytes"]
            <= maximum_bytes,
            "minimum_free_bytes_after_preserved": free_after_build
            >= minimum_free_after,
            "source_roles_exclude_train": all(
                str(row["role"]) != "train" for row in profile["sequences"]
            ),
            "outcome_targeting_forbidden": config["claim_boundary"][
                "outcome_targeting_forbidden"
            ]
            is True,
            "field_realism_not_claimed": config["claim_boundary"][
                "field_realism_proven"
            ]
            is False,
        }
        if not all(release_gates.values()):
            failed = [name for name, passed in release_gates.items() if not passed]
            raise ContractError(f"Release quality gates failed: {failed}")

        inventory = output_inventory(staging, {"release_receipt.json"})
        receipt = {
            "schema_version": 1,
            "dataset_id": config["dataset_id"],
            "profile": profile_name,
            "status": config["status"],
            "config": str(config_path.relative_to(repo_root)),
            "config_sha256": sha256_file(config_path),
            "generator": str(Path(__file__).resolve().relative_to(repo_root)),
            "generator_sha256": sha256_file(Path(__file__).resolve()),
            "determinism_contract_sha256": canonical_sha256(
                {
                    "config_sha256": sha256_file(config_path),
                    "conditions": config["conditions"],
                    "sequences": profile["sequences"],
                    "source_release_sha256": config["provenance"][
                        "cropcraft_v12_release"
                    ]["sha256"],
                    "sensor_motion_pack_sha256": config["provenance"][
                        "sensor_motion_pack"
                    ]["sha256"],
                }
            ),
            "provenance_files": provenance_state["files"],
            "architecture_capture": provenance_state["architecture_capture"],
            "runtime_audit": runtime_state,
            "sequences": sequence_rows,
            "sequence_count": len(sequence_rows),
            "frame_count": sum(int(row["frame_count"]) for row in sequence_rows),
            "storage": {
                **usage,
                "maximum_unique_output_bytes": maximum_bytes,
                "minimum_free_bytes_after": minimum_free_after,
                "free_bytes_before": free_before,
                "free_bytes_after_build": free_after_build,
            },
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "quality_gates": release_gates,
            "all_quality_gates_passed": all(release_gates.values()),
            "claim_boundary": config["claim_boundary"],
            "limitations": [
                "synthetic CropCraft imagery is not field or installed-rig evidence",
                "track IDs are semantic connected-component proxies, not botanical instances",
                "shared image-plane translation is not metric tractor motion calibration",
                "degraded PSFs are fixed stress assets and exceed the nominal architecture blur gate",
                "no model result or requested F1 target influenced operator selection",
            ],
        }
        receipt_path = staging / "release_receipt.json"
        write_json(receipt_path, receipt)

        summary = {
            "schema_version": 1,
            "dataset_id": config["dataset_id"],
            "profile": profile_name,
            "release": (
                Path(config["outputs"]["release_root"])
                / str(profile["output_directory"])
            ).as_posix(),
            "release_receipt": (
                Path(config["outputs"]["release_root"])
                / str(profile["output_directory"])
                / "release_receipt.json"
            ).as_posix(),
            "release_receipt_sha256": sha256_file(receipt_path),
            "sequence_count": receipt["sequence_count"],
            "frame_count": receipt["frame_count"],
            "storage": receipt["storage"],
            "quality_gates": release_gates,
            "all_quality_gates_passed": receipt["all_quality_gates_passed"],
            "claim_boundary": config["claim_boundary"],
            "sequences": sequence_rows,
        }
        write_json(result_staging / "summary.json", summary)
        qc_root = result_staging / "qc"
        qc_root.mkdir()
        for row in sequence_rows:
            source_contact = staging / row["contact_sheet"]
            shutil.copy2(source_contact, qc_root / f"{row['sequence_id']}.png")

        os.replace(staging, destination)
        os.replace(result_staging, result_destination)
        return {
            "release": str(destination),
            "release_receipt": str(destination / "release_receipt.json"),
            "release_receipt_sha256": sha256_file(destination / "release_receipt.json"),
            "results": str(result_destination),
            "all_quality_gates_passed": True,
            "sequence_count": receipt["sequence_count"],
            "frame_count": receipt["frame_count"],
            "unique_output_bytes": usage["unique_file_bytes"],
        }
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if result_staging.exists():
            shutil.rmtree(result_staging)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", required=True, choices=("fixture", "heldout"))
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    try:
        result = build_release(arguments.config, arguments.profile)
    except Exception as error:
        print(
            json.dumps(
                {"status": "ERROR", "error_type": type(error).__name__, "error": str(error)},
                sort_keys=True,
            ),
            file=os.sys.stderr,
        )
        raise SystemExit(1) from error
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
