#!/usr/bin/env python3
"""Audit the accepted real-data coverage inventory without reading pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest, validate_records


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve(project_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def summarize_dataset(records: list[SampleRecord], policy: dict[str, Any]) -> dict[str, Any]:
    if not records:
        raise ValueError("Cannot summarize an empty dataset")
    dataset_ids = {record.dataset_id for record in records}
    if len(dataset_ids) != 1:
        raise ValueError(f"Expected one dataset, got {sorted(dataset_ids)}")
    crop_by_id: dict[int, set[str]] = defaultdict(set)
    for record in records:
        crop_by_id[record.target_crop_id].add(record.crop_species)
    return {
        "dataset_id": records[0].dataset_id,
        "records": len(records),
        "splits": dict(sorted(Counter(record.split for record in records).items())),
        "capture_groups": len({record.group_id for record in records}),
        "fields": sorted({record.field_id for record in records}),
        "field_count": len({record.field_id for record in records}),
        "sessions": len({record.session_id for record in records}),
        "target_crops": {
            str(crop_id): sorted(species) for crop_id, species in sorted(crop_by_id.items())
        },
        "platforms": sorted({record.platform for record in records}),
        "sensors": sorted({record.sensor for record in records}),
        "growth_stages": sorted({record.growth_stage for record in records}),
        "annotation_exhaustive_counts": dict(
            sorted(Counter(str(record.annotation_exhaustive).lower() for record in records).items())
        ),
        "licenses": sorted({record.license_status for record in records}),
        "commercial_allowed_counts": dict(
            sorted(Counter(str(record.commercial_allowed).lower() for record in records).items())
        ),
        "policy": dict(policy),
    }


def audit(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    project_root = config_path.parents[2]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected YAML mapping: {config_path}")
    require_equal("schema version", config.get("schema_version"), 1)
    source_receipts: list[dict[str, Any]] = []
    records: list[SampleRecord] = []
    for specification in config["source_manifests"]:
        path = resolve(project_root, str(specification["path"]))
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_hash = manifest_sha256(path)
        require_equal(f"manifest SHA {path}", actual_hash, str(specification["sha256"]))
        manifest_records = read_manifest(path)
        records.extend(manifest_records)
        source_receipts.append(
            {"path": str(path), "sha256": actual_hash, "records": len(manifest_records)}
        )
    validate_records(records)
    expected = config["expected"]
    require_equal("accepted real records", len(records), int(expected["records"]))
    by_dataset: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in records:
        by_dataset[record.dataset_id].append(record)
    require_equal("accepted real datasets", len(by_dataset), int(expected["datasets"]))
    counts = {dataset_id: len(values) for dataset_id, values in sorted(by_dataset.items())}
    require_equal("dataset counts", counts, {str(k): int(v) for k, v in expected["dataset_counts"].items()})
    policies = config["dataset_policy"]
    require_equal("policy dataset inventory", set(policies), set(by_dataset))
    summaries = [
        summarize_dataset(by_dataset[dataset_id], policies[dataset_id])
        for dataset_id in sorted(by_dataset)
    ]
    partial_tracks = {"positive_only_partial", "partial_three_class"}
    partial_records = sum(
        summary["records"]
        for summary in summaries
        if summary["policy"]["supervision_track"] in partial_tracks
    )
    common_records = len(records) - partial_records
    require_equal("partial training-locked records", partial_records, int(expected["partial_training_locked_records"]))
    require_equal("common-compatible records", common_records, int(expected["common_semantic_compatible_records"]))
    partial_train = sum(
        int(summary["splits"].get("train", 0))
        for summary in summaries
        if summary["policy"]["supervision_track"] in partial_tracks
    )
    partial_calibration = sum(
        int(summary["splits"].get("external_calibration", 0))
        for summary in summaries
        if summary["policy"]["supervision_track"] in partial_tracks
    )
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "scope": {
            "records": len(records),
            "datasets": len(by_dataset),
            "capture_groups": len({record.group_id for record in records}),
            "fields": len({(record.dataset_id, record.field_id) for record in records}),
            "target_crop_ids": sorted({record.target_crop_id for record in records}),
            "target_crop_species": sorted({record.crop_species for record in records}),
            "split_counts": dict(sorted(Counter(record.split for record in records).items())),
            "commercial_allowed_records": sum(record.commercial_allowed for record in records),
            "research_only_records": sum(not record.commercial_allowed for record in records),
            "common_semantic_compatible_records": common_records,
            "partial_training_locked_records": partial_records,
            "partial_training_locked_train_candidates": partial_train,
            "partial_external_calibration_records": partial_calibration,
        },
        "source_manifests": source_receipts,
        "datasets": summaries,
        "pixel_files_read": False,
        "external_test_pixels_read": False,
        "model_outputs_read": False,
        "model_selection_used": False,
        "note": "This is a manifest/provenance coverage audit. It does not unlock partial labels or re-open any pixel-level external test.",
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    output = resolve(project_root, str(config["outputs"]["audit"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/data/real_data_coverage_matrix_v1.yaml"))
    arguments = parser.parse_args()
    output = audit(arguments.config)
    print(json.dumps({"audit": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
