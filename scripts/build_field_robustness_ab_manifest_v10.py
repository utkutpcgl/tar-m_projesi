#!/usr/bin/env python3
"""Add only V10 synthetic-train rows to the accepted training manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from agri_seg.manifest import read_manifest, write_manifest


EXPECTED_BASE_SHA256 = (
    "49747a1a614138dfe36faa105793ccbcca81d753b28702ffa07599fa78d10df2"
)
EXPECTED_V10_SHA256 = (
    "a9da5ccfa05b730436bd0fe30394a6abd37cf9319b3247f5e63eeec169aaf1ec"
)
V10_DATASET_ID = "cropcraft_field_robustness_pilot_v10_r1"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--v10", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    base_path = Path(arguments.base).expanduser().resolve()
    v10_path = Path(arguments.v10).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    receipt_path = output.with_name(f"{output.stem}_receipt.json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError(output if output.exists() else receipt_path)
    if sha256(base_path) != EXPECTED_BASE_SHA256:
        raise RuntimeError("Accepted baseline manifest SHA-256 changed")
    if sha256(v10_path) != EXPECTED_V10_SHA256:
        raise RuntimeError("V10 field-robustness manifest SHA-256 changed")
    base = read_manifest(base_path)
    v10 = read_manifest(v10_path)
    if Counter(record.split for record in v10) != Counter(
        {"train": 48, "val": 12, "test": 12}
    ):
        raise RuntimeError("Unexpected V10 split counts")
    if {record.dataset_id for record in v10} != {V10_DATASET_ID}:
        raise RuntimeError("Unexpected V10 dataset ID")
    selected = [record for record in v10 if record.split == "train"]
    if len(selected) != 48:
        raise RuntimeError("Expected exactly 48 V10 training rows")
    base_groups = {record.group_id for record in base}
    if base_groups & {record.group_id for record in selected}:
        raise RuntimeError("V10 training groups overlap the accepted manifest")
    base_paths = {
        value
        for record in base
        for value in (record.image_path, record.mask_path)
    }
    selected_paths = {
        value
        for record in selected
        for value in (record.image_path, record.mask_path)
    }
    if base_paths & selected_paths:
        raise RuntimeError("V10 training files overlap the accepted manifest")
    combined = [*base, *selected]
    write_manifest(combined, output)
    validation_datasets = sorted(
        {record.dataset_id for record in combined if record.split == "val"}
    )
    if V10_DATASET_ID in validation_datasets:
        raise RuntimeError("Synthetic V10 leaked into model-selection validation")
    receipt = {
        "schema_version": 1,
        "base_manifest": str(base_path),
        "base_manifest_sha256": sha256(base_path),
        "v10_manifest": str(v10_path),
        "v10_manifest_sha256": sha256(v10_path),
        "output_manifest": str(output),
        "output_manifest_sha256": sha256(output),
        "rows": len(combined),
        "split_counts": dict(Counter(record.split for record in combined)),
        "dataset_split_counts": {
            f"{dataset}::{split}": count
            for (dataset, split), count in sorted(
                Counter((record.dataset_id, record.split) for record in combined).items()
            )
        },
        "v10_rows_added": 48,
        "v10_roles_excluded": ["val", "test"],
        "validation_dataset_ids": validation_datasets,
        "synthetic_validation_in_source_model_selection": False,
        "group_overlap": [],
        "path_overlap": [],
        "quality_gates": {
            "inputs_sha256_locked": True,
            "only_v10_train_added": True,
            "v10_val_test_excluded": True,
            "groups_disjoint": True,
            "paths_disjoint": True,
        },
        "all_quality_gates_passed": True,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
