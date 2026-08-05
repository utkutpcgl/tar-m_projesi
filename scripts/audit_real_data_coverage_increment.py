#!/usr/bin/env python3
"""Append one released dataset to a hash-locked real coverage audit."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from agri_seg.manifest import manifest_sha256, read_manifest, validate_records
try:
    from scripts.audit_real_data_coverage_matrix import summarize_dataset
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from audit_real_data_coverage_matrix import summarize_dataset


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def resolve(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def audit(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    project_root = config_path.parents[2]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    require_equal("schema version", config.get("schema_version"), 2)

    base_path = resolve(project_root, config["base_audit"]["path"])
    require_equal("base audit SHA-256", sha256(base_path), config["base_audit"]["sha256"])
    base = load_json(base_path)
    require_equal("base status", base.get("status"), "verified")

    evidence_path = resolve(project_root, config["release_evidence"]["path"])
    require_equal(
        "release evidence SHA-256",
        sha256(evidence_path),
        config["release_evidence"]["sha256"],
    )
    evidence = load_json(evidence_path)
    for key in config["release_evidence"]["required_true"]:
        require_equal(f"release flag {key}", evidence.get(key), True)

    manifest_path = resolve(project_root, config["additional_manifest"]["path"])
    require_equal(
        "additional manifest SHA-256",
        manifest_sha256(manifest_path),
        config["additional_manifest"]["sha256"],
    )
    added = read_manifest(manifest_path)
    validate_records(added)
    added_ids = {record.sample_id for record in added}
    if len(added_ids) != len(added):
        raise ValueError("Duplicate sample IDs in additional manifest")
    old_ids: set[str] = set()
    for row in base["source_manifests"]:
        old_ids.update(record.sample_id for record in read_manifest(row["path"]))
    if added_ids & old_ids:
        raise ValueError("Additional manifest overlaps the base sample IDs")
    existing_datasets = {row["dataset_id"] for row in base["datasets"]}
    added_datasets = {record.dataset_id for record in added}
    require_equal("one new dataset", len(added_datasets), 1)
    if added_datasets & existing_datasets:
        raise ValueError("Additional dataset ID already exists in base audit")

    added_summary = summarize_dataset(added, config["dataset_policy"])
    old_scope = base["scope"]
    split_counts = Counter(old_scope["split_counts"])
    split_counts.update(record.split for record in added)
    new_scope = {
        "records": int(old_scope["records"]) + len(added),
        "datasets": int(old_scope["datasets"]) + 1,
        "capture_groups": int(old_scope["capture_groups"])
        + len({record.group_id for record in added}),
        "fields": int(old_scope["fields"])
        + len({record.field_id for record in added}),
        "target_crop_ids": sorted(
            set(int(value) for value in old_scope["target_crop_ids"])
            | {record.target_crop_id for record in added}
        ),
        "target_crop_species": sorted(
            set(str(value) for value in old_scope["target_crop_species"])
            | {record.crop_species for record in added}
        ),
        "split_counts": dict(sorted(split_counts.items())),
        "commercial_allowed_records": int(old_scope["commercial_allowed_records"])
        + sum(record.commercial_allowed for record in added),
        "research_only_records": int(old_scope["research_only_records"])
        + sum(not record.commercial_allowed for record in added),
        "common_semantic_compatible_records": int(
            old_scope["common_semantic_compatible_records"]
        )
        + len(added),
        "partial_training_locked_records": int(
            old_scope["partial_training_locked_records"]
        ),
        "partial_training_locked_train_candidates": int(
            old_scope["partial_training_locked_train_candidates"]
        ),
        "partial_external_calibration_records": int(
            old_scope["partial_external_calibration_records"]
        ),
    }
    expected = config["expected_scope"]
    for key in (
        "records",
        "datasets",
        "capture_groups",
        "fields",
        "common_semantic_compatible_records",
        "partial_training_locked_records",
        "commercial_allowed_records",
        "research_only_records",
    ):
        require_equal(key, new_scope[key], int(expected[key]))
    require_equal(
        "external calibration rows",
        new_scope["split_counts"]["external_calibration"],
        int(expected["external_calibration"]),
    )

    report = {
        "schema_version": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "base_audit": str(base_path),
        "base_audit_sha256": sha256(base_path),
        "scope": new_scope,
        "source_manifests": [
            *base["source_manifests"],
            {
                "path": str(manifest_path),
                "sha256": manifest_sha256(manifest_path),
                "records": len(added),
            },
        ],
        "datasets": sorted(
            [*base["datasets"], added_summary], key=lambda row: row["dataset_id"]
        ),
        "release_evidence": {
            "path": str(evidence_path),
            "sha256": sha256(evidence_path),
        },
        "pixel_files_read": False,
        "external_test_pixels_read": False,
        "model_outputs_read": False,
        "model_selection_used": False,
        "note": (
            "Incremental manifest/provenance audit over the hash-locked v1 "
            "coverage receipt; 283 correlated frames add one capture group."
        ),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    output = resolve(project_root, config["outputs"]["audit"])
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/data/real_data_coverage_matrix_v2.yaml")
    )
    args = parser.parse_args()
    output = audit(args.config)
    print(json.dumps({"audit": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
