#!/usr/bin/env python3
"""Finalize the bounded CropCraft reproductive-rice asset/data gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.manifest import manifest_sha256, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve_locked_inputs(
    config: dict[str, Any], project_root: Path, data_root: Path
) -> dict[str, Path]:
    roots = {"project": project_root, "data": data_root}
    paths: dict[str, Path] = {}
    for name, specification in config["locked_inputs"].items():
        root_name = str(specification["root"])
        if root_name not in roots:
            raise ValueError(f"Unknown lock root for {name}: {root_name}")
        path = (roots[root_name] / str(specification["path"])).resolve()
        try:
            path.relative_to(roots[root_name].resolve())
        except ValueError as exc:
            raise ValueError(f"Locked input escapes {root_name} root: {path}") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        require_equal(f"locked SHA-256 {name}", sha256(path), specification["sha256"])
        paths[name] = path
    return paths


def validate_duplicate_audit(
    audit: dict[str, Any], expected_candidate: int, expected_reference: int
) -> dict[str, int | bool]:
    summary: dict[str, int | bool] = {
        "candidate_samples": int(audit["scope"]["candidate_samples"]),
        "reference_samples": int(audit["scope"]["reference_samples"]),
        "candidate_to_reference_matches": int(
            audit["candidate_to_reference_match_count"]
        ),
        "within_candidate_matches": int(audit["within_candidate_match_count"]),
        "within_candidate_cross_split_matches": int(
            audit["within_candidate_cross_split_match_count"]
        ),
        "within_candidate_same_split_matches": int(
            audit["within_candidate_same_split_match_count"]
        ),
        "passed": bool(audit["passed"]),
    }
    require_equal("duplicate candidate samples", summary["candidate_samples"], expected_candidate)
    require_equal("duplicate reference samples", summary["reference_samples"], expected_reference)
    require_equal("candidate/reference duplicate matches", summary["candidate_to_reference_matches"], 0)
    require_equal("within-candidate duplicate matches", summary["within_candidate_matches"], 0)
    require_equal("cross-split duplicate matches", summary["within_candidate_cross_split_matches"], 0)
    require_equal("same-split duplicate matches", summary["within_candidate_same_split_matches"], 0)
    require_equal("duplicate audit passed", summary["passed"], True)
    return summary


def validate_distribution(
    report: dict[str, Any], phase: str, required_metrics: list[str]
) -> dict[str, float]:
    require_equal(f"{phase} distribution phase", report["phase"], phase)
    require_equal(
        f"{phase} distribution gate", report["all_quality_gates_passed"], True
    )
    comparisons = report["required_metric_comparison"]
    require_equal(f"{phase} distribution metrics", set(comparisons), set(required_metrics))
    medians: dict[str, float] = {}
    for metric in required_metrics:
        require_equal(f"{phase} distribution {metric}", comparisons[metric]["passed"], True)
        medians[metric] = float(comparisons[metric]["synthetic_q50"])
    return medians


def finalize(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    config = load_yaml(config_path)
    require_equal("gate schema", config.get("schema_version"), 1)
    project_root = Path(str(config["project_root"])).expanduser().resolve()
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    locked = resolve_locked_inputs(config, project_root, data_root)
    expected = config["expected"]

    selection = load_json(locked["factor_selection"])
    require_equal("factor selection status", selection["status"], "verified_and_factor_selected")
    require_equal("factor selection pass", selection["passed"], True)
    require_equal("selected factor", selection["selection"]["selected_factor"], expected["selected_factor"])
    require_equal("factor selection model results", selection["selection"]["model_results_used"], False)

    static = load_json(locked["static_asset_audit"])
    require_equal("static asset gate", static["all_quality_gates_passed"], True)
    require_equal("asset pack id", static["pack_id"], expected["asset_pack_id"])
    require_equal("asset manifest SHA", static["pack_manifest_sha256"], sha256(locked["asset_pack_manifest"]))
    require_equal("asset inventory SHA", static["inventory_sha256"], expected["asset_inventory_sha256"])
    require_equal("asset inventory files", int(static["inventory_files"]), int(expected["asset_inventory_files"]))
    require_equal("asset models", int(static["model_summary"]["models"]), int(expected["asset_models"]))
    require_equal("asset geometries", int(static["model_summary"]["unique_geometries"]), int(expected["asset_unique_geometries"]))
    require_equal("large batch at static gate", static["large_synthetic_batch_generated"], False)

    smoke_release = load_json(locked["smoke_release_receipt"])
    require_equal("smoke release gate", smoke_release["all_quality_gates_passed"], True)
    require_equal("smoke frames", int(smoke_release["frames"]), int(expected["smoke_frames"]))
    require_equal("smoke asset pack", smoke_release["asset_pack"]["pack_id"], expected["asset_pack_id"])
    require_equal("smoke asset manifest", smoke_release["asset_pack"]["manifest_sha256"], sha256(locked["asset_pack_manifest"]))
    smoke_distribution = load_json(locked["smoke_distribution_audit"])
    smoke_medians = validate_distribution(
        smoke_distribution, "smoke", list(expected["distribution_metrics"])
    )
    require_equal("smoke distribution release lock", smoke_distribution["release_receipt_sha256"], sha256(locked["smoke_release_receipt"]))
    smoke_manual = load_json(locked["smoke_manual_review"])
    require_equal("smoke manual review", smoke_manual["passed"], True)
    require_equal("smoke manual static lock", smoke_manual["scope"]["static_asset_receipt_sha256"], sha256(locked["static_asset_audit"]))
    require_equal("smoke manual release lock", smoke_manual["scope"]["release_receipt_sha256"], sha256(locked["smoke_release_receipt"]))
    require_equal("smoke manual distribution lock", smoke_manual["scope"]["riceseg_distribution_receipt_sha256"], sha256(locked["smoke_distribution_audit"]))

    pilot_release = load_json(locked["pilot_release_receipt"])
    require_equal("pilot release gate", pilot_release["all_quality_gates_passed"], True)
    require_equal("pilot frames", int(pilot_release["frames"]), int(expected["pilot_samples"]))
    require_equal("pilot scenes", int(pilot_release["scene_count"]), int(expected["pilot_scenes"]))
    require_equal("pilot exact RGB duplicates", int(pilot_release["exact_rgb_duplicates"]), 0)
    require_equal("pilot cross-scene mask duplicates", int(pilot_release["exact_mask_duplicates_across_scenes"]), 0)
    require_equal("pilot asset pack", pilot_release["asset_pack"]["pack_id"], expected["asset_pack_id"])
    require_equal("pilot asset manifest", pilot_release["asset_pack"]["manifest_sha256"], sha256(locked["asset_pack_manifest"]))
    pilot_distribution = load_json(locked["pilot_distribution_audit"])
    pilot_medians = validate_distribution(
        pilot_distribution, "pilot", list(expected["distribution_metrics"])
    )
    require_equal("pilot distribution release lock", pilot_distribution["release_receipt_sha256"], sha256(locked["pilot_release_receipt"]))
    pilot_manual = load_json(locked["pilot_manual_review"])
    require_equal("pilot manual review", pilot_manual["passed"], True)
    require_equal("pilot external test", pilot_manual["external_test_used"], False)
    require_equal("pilot manual static lock", pilot_manual["review_scope"]["static_asset_receipt_sha256"], sha256(locked["static_asset_audit"]))
    require_equal("pilot manual release lock", pilot_manual["review_scope"]["release_receipt_sha256"], sha256(locked["pilot_release_receipt"]))
    require_equal("pilot manual distribution lock", pilot_manual["review_scope"]["distribution_receipt_sha256"], sha256(locked["pilot_distribution_audit"]))
    visual = load_json(locked["pilot_visual_receipt"])
    require_equal("pilot visual receipt", visual["passed"], True)
    require_equal("pilot visual release lock", visual["release_receipt_sha256"], sha256(locked["pilot_release_receipt"]))
    require_equal("pilot visual manual lock", visual["manual_review_sha256"], sha256(locked["pilot_manual_review"]))
    require_equal("pilot visual contact lock", visual["contact_sheet_sha256"], sha256(locked["pilot_contact_sheet"]))

    conversion = load_json(locked["conversion_receipt"])
    require_equal("conversion samples", int(conversion["samples"]), int(expected["pilot_samples"]))
    require_equal("conversion dataset", conversion["dataset_id"], expected["dataset_id"])
    require_equal("conversion splits", conversion["split_counts"], expected["split_counts"])
    require_equal("conversion scene split", conversion["scene_disjoint_split"]["passed"], True)
    require_equal("conversion release lock", conversion["release_receipt_sha256"], sha256(locked["pilot_release_receipt"]))
    require_equal("conversion asset pack", conversion["asset_pack"]["pack_id"], expected["asset_pack_id"])
    require_equal("conversion class pixels", conversion["class_pixels"], expected["class_pixels"])
    require_equal("commercial-use claim", conversion["manifest_metadata"]["commercial_allowed"], False)

    manifest_path = locked["pilot_manifest"]
    require_equal("manifest hash", manifest_sha256(manifest_path), sha256(manifest_path))
    records = read_manifest(manifest_path)
    require_equal("manifest samples", len(records), int(expected["pilot_samples"]))
    require_equal("manifest datasets", {record.dataset_id for record in records}, {expected["dataset_id"]})
    require_equal("manifest commercial flags", {record.commercial_allowed for record in records}, {False})
    manifest_audit = load_json(locked["manifest_audit"])
    require_equal("manifest audit samples", int(manifest_audit["samples"]), int(expected["pilot_samples"]))
    require_equal("manifest audit datasets", manifest_audit["dataset_counts"], {expected["dataset_id"]: int(expected["pilot_samples"])})
    require_equal("manifest audit splits", manifest_audit["split_counts"], expected["split_counts"])
    for field in ("invalid_masks", "missing_files", "shape_mismatches"):
        require_equal(f"manifest audit {field}", int(manifest_audit[field]), 0)
    require_equal(
        "manifest class pixels",
        manifest_audit["class_pixel_counts"],
        {
            "background": int(expected["class_pixels"]["background"]),
            "ignore": 0,
            "other_vegetation": int(expected["class_pixels"]["weed"]),
            "target_crop": int(expected["class_pixels"]["crop"]),
        },
    )

    duplicate = load_json(locked["duplicate_audit"])
    require_equal("duplicate candidate manifest", Path(duplicate["scope"]["candidate_manifest"]).resolve(), manifest_path.resolve())
    require_equal("duplicate candidate manifest hash", duplicate["scope"]["candidate_manifest_sha256"], sha256(manifest_path))
    duplicate_summary = validate_duplicate_audit(
        duplicate,
        int(expected["pilot_samples"]),
        int(expected["duplicate_reference_samples"]),
    )

    freeze = config["freeze"]
    require_equal("model results used", freeze["model_results_used"], False)
    require_equal("external test used", freeze["external_test_used"], False)
    require_equal("large synthetic batch generated", freeze["large_synthetic_batch_generated"], False)

    output = (data_root / str(config["output"])).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "all_quality_gates_passed": True,
        "eligible_for_equal_budget_model_ab": True,
        "model_benefit_established": False,
        "selected_factor": expected["selected_factor"],
        "dataset_id": expected["dataset_id"],
        "asset_pack_id": expected["asset_pack_id"],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "locked_inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in locked.items()
        },
        "asset": {
            "models": int(static["model_summary"]["models"]),
            "unique_geometries": int(static["model_summary"]["unique_geometries"]),
            "inventory_files": int(static["inventory_files"]),
            "inventory_bytes": int(static["inventory_bytes"]),
            "inventory_sha256": static["inventory_sha256"],
            "manual_morphology_review": "pass",
        },
        "smoke": {
            "frames": int(smoke_release["frames"]),
            "distribution_medians": smoke_medians,
            "manual_review": "pass",
        },
        "pilot": {
            "samples": len(records),
            "split_counts": conversion["split_counts"],
            "class_pixels": conversion["class_pixels"],
            "mean_crop_fraction": float(pilot_release["mean_crop_fraction"]),
            "mean_weed_fraction": float(pilot_release["mean_weed_fraction"]),
            "distribution_medians": pilot_medians,
            "manual_review": "pass",
            "manifest_sha256": sha256(manifest_path),
        },
        "duplicates": {
            **duplicate_summary,
            "nearest_real_dhash_hamming": duplicate[
                "candidate_to_reference_nearest_hamming"
            ],
        },
        "license": {
            "commercial_allowed": False,
            "status": conversion["manifest_metadata"]["license_status"],
        },
        "limitations": [
            "Procedural morphology and generated textures are not botanical scans.",
            "Low-order RiceSEG distribution agreement does not establish model value.",
            "Wind, disease, wet-leaf deformation, measured optics, and motion blur are outside this isolated factor.",
            "A frozen equal-budget real-development A/B is still required.",
        ],
        "external_test_used": False,
        "model_results_used": False,
        "finalizer": str(Path(__file__).resolve()),
        "finalizer_sha256": sha256(Path(__file__).resolve()),
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/simulation/cropcraft_reproductive_final_gate_v9_r3.yaml"),
    )
    arguments = parser.parse_args()
    output = finalize(arguments.config)
    print(json.dumps({"quality_receipt": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
