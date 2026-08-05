#!/usr/bin/env python3
"""Profiled CropCraft generator with deterministic stratified range coverage."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.generate_cropcraft_profiled_pilot as base


BASE_PROFILED_SCENE_CONFIG = base.profiled_scene_config


def stratified_index(rank: int, count: int, key: str) -> int:
    if count <= 1:
        return 0
    digest = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    strides = [value for value in range(1, count) if math.gcd(value, count) == 1]
    stride = strides[digest % len(strides)]
    offset = (digest // len(strides)) % count
    return (rank * stride + offset) % count


def stratified_scene_config(
    raw_base: dict[str, Any],
    study: dict[str, Any],
    scene_index: int,
    asset_pack: Path | None = None,
) -> dict[str, Any]:
    result = BASE_PROFILED_SCENE_CONFIG(
        raw_base, study, scene_index, asset_pack
    )
    profiles = base.profile_contract(study)
    profile_index = scene_index % len(profiles)
    profile = profiles[profile_index]
    occurrence = scene_index // len(profiles)
    scene_count = int(study["scene_count"])
    occurrence_count = sum(
        index % len(profiles) == profile_index for index in range(scene_count)
    )
    surface = result["agri_asset_profile"]["surface_parameters"]
    seed = int(study["base_seed"])
    for name, bounds in sorted(profile["surface_parameter_ranges"].items()):
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError(f"Invalid stratified range {name}: {bounds}")
        index = stratified_index(
            occurrence,
            occurrence_count,
            f"{seed}|{profile['name']}|{name}",
        )
        quantile = 0.5 if occurrence_count == 1 else index / (occurrence_count - 1)
        surface[str(name)] = round(
            float(bounds[0])
            + quantile * (float(bounds[1]) - float(bounds[0])),
            6,
        )
    result["agri_asset_profile"]["correlated_profile_sampling"] = (
        "deterministic_per_parameter_stratified_endpoints"
    )
    return result


def main() -> None:
    destination = base.output_argument(sys.argv[1:])
    base.profiled_scene_config = stratified_scene_config
    base.main()
    receipt_path = destination / "release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_profiled_generator"] = receipt["pilot_generator"]
    receipt["base_profiled_generator_sha256"] = receipt[
        "pilot_generator_sha256"
    ]
    receipt["pilot_generator"] = str(Path(__file__).resolve())
    receipt["pilot_generator_sha256"] = base.legacy.sha256(
        Path(__file__).resolve()
    )
    receipt["correlated_profile_sampling"] = {
        "method": "deterministic_per_parameter_stratified_endpoints",
        "guarantees": [
            "every declared profile has balanced scene count",
            "every overridden range reaches both endpoints when a profile has at least two scenes",
            "parameter permutations are deterministic and parameter-specific",
        ],
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release_receipt": str(receipt_path),
                "release_receipt_sha256": base.legacy.sha256(receipt_path),
                "sampling": receipt["correlated_profile_sampling"],
                "all_quality_gates_passed": receipt["all_quality_gates_passed"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
