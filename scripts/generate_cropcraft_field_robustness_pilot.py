#!/usr/bin/env python3
"""Generate split-aware CropCraft field-robustness pilots.

This wrapper deliberately reuses the immutable historical pilot generator per
role, then adds stronger cross-role gates.  Synthetic val/test are stress
diagnostics only and must never be merged into the real model-selection score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_GENERATOR = PROJECT_ROOT / "scripts/generate_cropcraft_pilot.py"
ROLES = ("train", "val", "test")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings while replacing scalars and sequences."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_study(
    path: Path, visited: set[Path] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Load an optional base_study chain and return one effective study."""
    resolved = path.expanduser().resolve()
    chain = set() if visited is None else set(visited)
    if resolved in chain:
        raise ValueError(f"Cyclic base_study reference: {resolved}")
    chain.add(resolved)
    raw = load_yaml(resolved)
    base_value = raw.pop("base_study", None)
    sources = [{"path": str(resolved), "sha256": sha256(resolved)}]
    if base_value is None:
        return raw, sources
    base_path = resolve_project_path(str(base_value))
    base, base_sources = load_study(base_path, chain)
    return deep_merge(base, raw), sources + base_sources


def merge_ranges(
    shared: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    merged = deepcopy(shared)
    merged.update(deepcopy(overrides))
    return merged


def validate_asset_contract(
    study: dict[str, Any], pack: dict[str, Any]
) -> dict[str, Any]:
    declared = pack.get("split_asset_contract")
    if not isinstance(declared, dict) or set(declared) != set(ROLES):
        raise ValueError("Asset pack has no complete train/val/test contract")
    observed: dict[str, dict[str, list[str]]] = {}
    for role in ROLES:
        role_cfg = study["splits"][role]
        profile = role_cfg.get("asset_profile")
        if not isinstance(profile, dict):
            raise ValueError(f"Missing asset profile for {role}")
        observed[role] = {
            "grounds": sorted(
                {str(value) for value in profile["ground_material_ids"]}
            ),
            "environments": sorted(
                {str(value) for value in profile["environment_files"]}
            ),
        }
        expected = {
            "grounds": sorted(str(value) for value in declared[role]["grounds"]),
            "environments": sorted(
                str(value) for value in declared[role]["environments"]
            ),
        }
        if observed[role] != expected:
            raise ValueError(
                f"Study {role} assets differ from frozen pack contract: "
                f"{observed[role]} != {expected}"
            )
    overlap: dict[str, dict[str, list[str]]] = {}
    for kind in ("grounds", "environments"):
        for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
            values = sorted(set(observed[left][kind]) & set(observed[right][kind]))
            overlap[f"{left}_vs_{right}_{kind}"] = {
                "values": values,
                "count": len(values),
            }
    if any(item["count"] for item in overlap.values()):
        raise ValueError(f"Synthetic split asset leakage: {overlap}")
    return {"observed": observed, "overlap": overlap, "passed": True}


def role_study(
    study: dict[str, Any], role: str, destination: Path
) -> dict[str, Any]:
    role_cfg = deepcopy(study["splits"][role])
    scene_count = int(role_cfg.pop("scenes"))
    if scene_count <= 0:
        raise ValueError(f"{role}.scenes must be positive")
    required_role = {
        "base_seed",
        "asset_profile",
        "ranges",
        "quality_gates",
    }
    missing = required_role - set(role_cfg)
    if missing:
        raise ValueError(f"Missing {role} settings: {sorted(missing)}")
    result = {
        key: deepcopy(value)
        for key, value in study.items()
        if key not in {"splits", "shared_ranges", "quality_contract"}
    }
    result.update(role_cfg)
    result["release"] = f"{study['release']}_{role}"
    result["purpose"] = (
        f"{study['purpose']}; synthetic_{role}_role; "
        "not_a_real_validation_or_test_substitute"
    )
    result["scene_count"] = scene_count
    result["frames_per_scene"] = int(study["frames_per_scene"])
    result["train_scenes"] = scene_count
    result["validation_scenes"] = 0
    result["ranges"] = merge_ranges(
        study.get("shared_ranges", {}), role_cfg["ranges"]
    )
    result["synthetic_role"] = role
    result["parent_release"] = study["release"]
    result["role_output"] = str(destination / "roles" / role)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("study")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate and materialize role studies without invoking Blender",
    )
    args = parser.parse_args()

    study_path = Path(args.study).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    study, study_sources = load_study(study_path)
    if set(study.get("splits", {})) != set(ROLES):
        raise ValueError("Study must define exactly train, val and test roles")
    if study.get("synthetic_evaluation_policy") != "diagnostic_only_real_score_weight_zero":
        raise ValueError("Synthetic diagnostic isolation policy is not frozen")
    pack_root = resolve_project_path(study["asset_pack"])
    pack_path = pack_root / "PACK.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    if pack.get("pack_id") != study.get("asset_pack_id"):
        raise ValueError("Asset pack ID mismatch")
    asset_contract = validate_asset_contract(study, pack)

    destination.mkdir(parents=True, exist_ok=False)
    role_studies_root = destination / "role_studies"
    role_studies_root.mkdir()
    (destination / "roles").mkdir()
    (destination / "study.input.yaml").write_bytes(study_path.read_bytes())
    resolved_study_path = destination / "study.resolved.yaml"
    resolved_study_path.write_text(
        yaml.safe_dump(study, sort_keys=False), encoding="utf-8"
    )
    started_at = datetime.now(timezone.utc)
    role_rows: list[dict[str, Any]] = []
    all_seeds: list[int] = []
    rgb_hash_roles: dict[str, set[str]] = {}
    mask_hash_roles: dict[str, set[str]] = {}

    for role in ROLES:
        resolved = role_study(study, role, destination)
        resolved_path = role_studies_root / f"{role}.yaml"
        resolved_path.write_text(
            yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8"
        )
        role_output = destination / "roles" / role
        row: dict[str, Any] = {
            "role": role,
            "study": str(resolved_path),
            "study_sha256": sha256(resolved_path),
            "output": str(role_output),
            "scene_count": int(resolved["scene_count"]),
            "expected_pairs": int(resolved["quality_gates"]["expected_pairs"]),
        }
        if not args.plan_only:
            command = [
                sys.executable,
                str(LEGACY_GENERATOR),
                str(resolved_path),
                "--output",
                str(role_output),
            ]
            result = subprocess.run(
                command, cwd=PROJECT_ROOT, capture_output=True, text=True
            )
            (destination / f"{role}.stdout.log").write_text(
                result.stdout, encoding="utf-8"
            )
            (destination / f"{role}.stderr.log").write_text(
                result.stderr, encoding="utf-8"
            )
            if result.returncode != 0:
                tail = "\n".join(result.stderr.splitlines()[-40:])
                raise RuntimeError(f"{role} generation failed:\n{tail}")
            receipt_path = role_output / "release_receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("all_quality_gates_passed") is not True:
                raise RuntimeError(f"{role} role gates failed")
            seeds = [int(scene["seed"]) for scene in receipt["scenes"]]
            all_seeds.extend(seeds)
            row.update(
                {
                    "receipt": str(receipt_path),
                    "receipt_sha256": sha256(receipt_path),
                    "frames": int(receipt["frames"]),
                    "seeds": seeds,
                    "used_ground_materials": receipt["used_ground_materials"],
                    "used_environments": receipt["used_environments"],
                    "surface_parameter_values": receipt["surface_parameter_values"],
                    "all_role_quality_gates_passed": True,
                }
            )
            for path in sorted(role_output.glob("scenes/*/render/images/*.jpg")):
                rgb_hash_roles.setdefault(sha256(path), set()).add(role)
            for path in sorted(role_output.glob("scenes/*/render/masks/*.png")):
                mask_hash_roles.setdefault(sha256(path), set()).add(role)
        role_rows.append(row)

    cross_role_rgb_duplicates = {
        digest: sorted(roles)
        for digest, roles in rgb_hash_roles.items()
        if len(roles) > 1
    }
    cross_role_mask_duplicates = {
        digest: sorted(roles)
        for digest, roles in mask_hash_roles.items()
        if len(roles) > 1
    }
    gates = {
        "asset_family_disjoint": asset_contract["passed"],
        "unique_scene_seeds": args.plan_only or len(all_seeds) == len(set(all_seeds)),
        "no_cross_role_rgb_exact_duplicates": not cross_role_rgb_duplicates,
        "no_cross_role_mask_exact_duplicates": not cross_role_mask_duplicates,
        "all_role_gates_passed": args.plan_only
        or all(row.get("all_role_quality_gates_passed") is True for row in role_rows),
        "real_score_weight_is_zero": True,
    }
    receipt = {
        "schema_version": 1,
        "release": study["release"],
        "purpose": study["purpose"],
        "synthetic_evaluation_policy": study["synthetic_evaluation_policy"],
        "real_model_selection_score_weight": 0.0,
        "roles": role_rows,
        "asset_contract": asset_contract,
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "cross_role_rgb_exact_duplicates": cross_role_rgb_duplicates,
        "cross_role_mask_exact_duplicates": cross_role_mask_duplicates,
        "plan_only": args.plan_only,
        "generator": str(Path(__file__).resolve()),
        "generator_sha256": sha256(__file__),
        "legacy_generator": str(LEGACY_GENERATOR),
        "legacy_generator_sha256": sha256(LEGACY_GENERATOR),
        "study": str(study_path),
        "study_sha256": sha256(study_path),
        "study_sources": study_sources,
        "resolved_study": str(resolved_study_path),
        "resolved_study_sha256": sha256(resolved_study_path),
        "asset_pack": str(pack_root),
        "asset_pack_manifest_sha256": sha256(pack_path),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "synthetic stress roles do not estimate real-field accuracy",
            "procedural macro soil structure is shader-normal detail, not measured geometry",
            "weather covers lighting, moisture and shallow water but not physical rain or wind",
            "botanical assets remain procedural approximations",
        ],
    }
    receipt_path = destination / (
        "plan_receipt.json" if args.plan_only else "release_receipt.json"
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"Cross-role gates failed; see {receipt_path}")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
