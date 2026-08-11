#!/usr/bin/env python3
"""Apply the controlled spot-spray camera geometry to profiled CropCraft scenes."""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.generate_cropcraft_profiled_pilot_v2 as stratified


BASE_STRATIFIED_SCENE_CONFIG = stratified.stratified_scene_config


def ground_fov_deg(field_width_m: float, camera_height_m: float) -> float:
    if field_width_m <= 0 or camera_height_m <= 0:
        raise ValueError("Field width and camera height must be positive")
    return math.degrees(2.0 * math.atan(field_width_m / (2.0 * camera_height_m)))


def deploy_scene_config(
    raw_base: dict[str, Any],
    study: dict[str, Any],
    scene_index: int,
    asset_pack: Path | None = None,
) -> dict[str, Any]:
    contract = study.get("deploy_imaging_contract")
    if not isinstance(contract, dict):
        raise ValueError("deploy_imaging_contract is required")
    result = BASE_STRATIFIED_SCENE_CONFIG(
        raw_base, study, scene_index, asset_pack
    )
    resolution = int(contract["tile_resolution_px"])
    if resolution <= 0:
        raise ValueError("tile_resolution_px must be positive")
    height_bounds = contract["camera_height_m"]
    if (
        not isinstance(height_bounds, list)
        or len(height_bounds) != 2
        or float(height_bounds[0]) <= 0
        or float(height_bounds[0]) > float(height_bounds[1])
    ):
        raise ValueError("camera_height_m must be a positive [min, max] range")
    seed = int(study["base_seed"]) + scene_index
    rng = random.Random(seed ^ 0xD3E10A12)
    height = rng.uniform(float(height_bounds[0]), float(height_bounds[1]))
    field_width = float(contract["tile_ground_width_m"])
    camera = result["render"]["camera"]
    camera["height"] = round(height, 6)
    camera["fov_deg"] = round(ground_fov_deg(field_width, height), 6)
    for output_name, contract_name in (
        ("roll_deg", "camera_roll_deg"),
        ("pitch_deg", "camera_pitch_deg"),
        ("yaw_deg", "camera_yaw_deg"),
        ("y_jitter", "camera_y_jitter_m"),
    ):
        bounds = contract.get(contract_name)
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or float(bounds[0]) > float(bounds[1])
        ):
            raise ValueError(f"{contract_name} must be a valid [min, max] range")
        camera[output_name] = round(
            rng.uniform(float(bounds[0]), float(bounds[1])), 6
        )
    result["render"]["resolution_x"] = resolution
    result["render"]["resolution_y"] = resolution
    result["deploy_imaging_contract"] = {
        **contract,
        "sampled_camera_height_m": camera["height"],
        "derived_tile_fov_deg": camera["fov_deg"],
        "derived_ground_gsd_mm_per_px": field_width * 1000.0 / resolution,
    }
    result["agri_asset_profile"]["capture_distribution"] = (
        "controlled_hood_strobed_rgb_proxy_v12"
    )
    return result


def main() -> None:
    destination = stratified.base.output_argument(sys.argv[1:])
    stratified.stratified_scene_config = deploy_scene_config
    stratified.main()
    receipt_path = destination / "release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_deploy_generator"] = receipt["pilot_generator"]
    receipt["base_deploy_generator_sha256"] = receipt[
        "pilot_generator_sha256"
    ]
    receipt["pilot_generator"] = str(Path(__file__).resolve())
    receipt["pilot_generator_sha256"] = stratified.base.legacy.sha256(
        Path(__file__).resolve()
    )
    receipt["capture_distribution"] = (
        "controlled_hood_strobed_rgb_proxy_v12"
    )
    receipt["limitations"].extend(
        [
            "illumination energy values are renderer units, not measured lux or flash energy",
            "one broad camera-mounted area light approximates the future multi-angle diffuse strobe",
            "each 1024 render approximates one centered crop of a 2048 module frame; off-axis lens effects are not modeled",
        ]
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release_receipt": str(receipt_path),
                "capture_distribution": receipt["capture_distribution"],
                "all_quality_gates_passed": receipt[
                    "all_quality_gates_passed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
