#!/usr/bin/env python3
"""Run the frozen CropCraft pilot generator with correlated scene profiles.

The historical generator samples every range independently.  This versioned
adapter keeps that implementation immutable, then deterministically replaces
the coupled illumination/weather variables with one declared profile per
scene.  The final role receipt records and gates the profile assignment.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.generate_cropcraft_pilot as legacy


BASE_SCENE_CONFIG = legacy.scene_config


def output_argument(argv: list[str]) -> Path:
    try:
        index = argv.index("--output")
        return Path(argv[index + 1]).expanduser().resolve()
    except (ValueError, IndexError) as error:
        raise ValueError("Expected --output PATH") from error


def profile_contract(study: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = study.get("correlated_scene_profiles")
    if not isinstance(profiles, list) or len(profiles) < 2:
        raise ValueError("correlated_scene_profiles must contain at least two profiles")
    names: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Correlated scene profiles must be mappings")
        name = str(profile.get("name", ""))
        if not name:
            raise ValueError("Every correlated scene profile needs a name")
        names.append(name)
        ranges = profile.get("surface_parameter_ranges")
        if not isinstance(ranges, dict) or not ranges:
            raise ValueError(f"Profile {name} has no surface_parameter_ranges")
        environments = profile.get("environment_files")
        if not isinstance(environments, list) or not environments:
            raise ValueError(f"Profile {name} has no environment_files")
    if len(names) != len(set(names)):
        raise ValueError("Correlated scene profile names must be unique")
    return profiles


def sampled_bounds(rng: random.Random, bounds: Any, name: str) -> float:
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or float(bounds[0]) > float(bounds[1])
    ):
        raise ValueError(f"Invalid profile range {name!r}: {bounds!r}")
    return round(rng.uniform(float(bounds[0]), float(bounds[1])), 6)


def profiled_scene_config(
    base: dict[str, Any],
    study: dict[str, Any],
    scene_index: int,
    asset_pack: Path | None = None,
) -> dict[str, Any]:
    result = BASE_SCENE_CONFIG(base, study, scene_index, asset_pack)
    profiles = profile_contract(study)
    profile = profiles[scene_index % len(profiles)]
    profile_name = str(profile["name"])
    agri_profile = result.get("agri_asset_profile")
    if not isinstance(agri_profile, dict) or asset_pack is None:
        raise ValueError("Correlated profiles require a validated asset pack")
    surface = agri_profile.get("surface_parameters")
    if not isinstance(surface, dict):
        raise ValueError("Correlated profiles require surface parameters")
    overrides = profile["surface_parameter_ranges"]
    unknown = sorted(set(overrides) - set(surface))
    if unknown:
        raise ValueError(f"Profile {profile_name} overrides unknown parameters: {unknown}")

    seed = int(study["base_seed"]) + scene_index
    rng = random.Random(seed ^ 0x5A17F11D)
    for name, bounds in sorted(overrides.items()):
        surface[str(name)] = sampled_bounds(rng, bounds, str(name))

    declared_environments = {
        str(value) for value in study["asset_profile"]["environment_files"]
    }
    profile_environments = [str(value) for value in profile["environment_files"]]
    if not set(profile_environments) <= declared_environments:
        raise ValueError(
            f"Profile {profile_name} uses an environment outside the role contract"
        )
    occurrence = scene_index // len(profiles)
    environment_file = profile_environments[occurrence % len(profile_environments)]
    environment_path = (asset_pack / "environments" / environment_file).resolve()
    if not environment_path.is_file():
        raise FileNotFoundError(environment_path)
    result["render"]["env_path"] = str(environment_path)
    agri_profile["environment_file"] = environment_file
    agri_profile["correlated_scene_profile"] = profile_name
    return result


def finalize_profile_receipt(destination: Path) -> dict[str, Any]:
    receipt_path = destination / "release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    study_path = destination / "study.input.yaml"
    study = legacy.load_yaml(study_path)
    profiles = profile_contract(study)
    expected_names = [str(profile["name"]) for profile in profiles]
    counts: Counter[str] = Counter()
    observed_environments: dict[str, set[str]] = {
        name: set() for name in expected_names
    }
    assignments: list[dict[str, Any]] = []
    for config_path in sorted((destination / "scene_configs").glob("scene_*.yaml")):
        config = legacy.load_yaml(config_path)
        agri_profile = config.get("agri_asset_profile", {})
        name = str(agri_profile.get("correlated_scene_profile", ""))
        environment = str(agri_profile.get("environment_file", ""))
        counts[name] += 1
        observed_environments.setdefault(name, set()).add(environment)
        assignments.append(
            {
                "scene": config_path.stem,
                "profile": name,
                "environment_file": environment,
            }
        )
    count_values = [counts[name] for name in expected_names]
    gates = {
        "all_scenes_have_declared_correlated_profile": (
            len(assignments) == int(receipt["scene_count"])
            and set(counts) == set(expected_names)
        ),
        "correlated_profiles_balanced": max(count_values) - min(count_values) <= 1,
        "profile_environment_contract_respected": all(
            observed_environments[name]
            <= {
                str(value)
                for value in next(
                    profile
                    for profile in profiles
                    if str(profile["name"]) == name
                )["environment_files"]
            }
            for name in expected_names
        ),
    }
    receipt["base_pilot_generator"] = receipt["pilot_generator"]
    receipt["base_pilot_generator_sha256"] = receipt["pilot_generator_sha256"]
    receipt["pilot_generator"] = str(Path(__file__).resolve())
    receipt["pilot_generator_sha256"] = legacy.sha256(Path(__file__).resolve())
    receipt["correlated_scene_profiles"] = {
        "names": expected_names,
        "counts": {name: counts[name] for name in expected_names},
        "observed_environments": {
            name: sorted(observed_environments[name]) for name in expected_names
        },
        "assignments": assignments,
    }
    receipt["quality_gates"].update(gates)
    receipt["all_quality_gates_passed"] = all(receipt["quality_gates"].values())
    receipt["limitations"].append(
        "weather/light profiles are physically motivated authored proxies, not a measured joint field distribution"
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"Correlated profile gates failed; see {receipt_path}")
    return receipt


def main() -> None:
    destination = output_argument(sys.argv[1:])
    legacy.scene_config = profiled_scene_config
    legacy.main()
    receipt = finalize_profile_receipt(destination)
    print(
        json.dumps(
            {
                "release_receipt": str(destination / "release_receipt.json"),
                "correlated_scene_profiles": receipt["correlated_scene_profiles"],
                "all_quality_gates_passed": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
