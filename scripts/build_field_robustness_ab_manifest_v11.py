#!/usr/bin/env python3
"""Add only quality-filtered V11 synthetic-train rows to the accepted base."""

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
EXPECTED_V11_SHA256 = (
    "576bf35a4ed203534a89d836a5a3eb23c966c99ee43a6df98a848e39cedd0aa1"
)
EXPECTED_CONVERSION_SHA256 = (
    "6ec8ebfab7cb4e33c5866f259c81b9d783d9f22afd6911a248964ede2657dd08"
)
V11_DATASET_ID = "cropcraft_field_robustness_pilot_v11_r2q"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--v11", required=True)
    parser.add_argument("--conversion", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    base_path = Path(arguments.base).expanduser().resolve()
    v11_path = Path(arguments.v11).expanduser().resolve()
    conversion_path = Path(arguments.conversion).expanduser().resolve()
    output = Path(arguments.output).expanduser().resolve()
    receipt_path = output.with_name(f"{output.stem}_receipt.json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError(output if output.exists() else receipt_path)
    if sha256(base_path) != EXPECTED_BASE_SHA256:
        raise RuntimeError("Accepted baseline manifest SHA-256 changed")
    if sha256(v11_path) != EXPECTED_V11_SHA256:
        raise RuntimeError("V11 quarantined manifest SHA-256 changed")
    if sha256(conversion_path) != EXPECTED_CONVERSION_SHA256:
        raise RuntimeError("V11 conversion receipt SHA-256 changed")
    conversion = json.loads(conversion_path.read_text(encoding="utf-8"))
    if (
        conversion.get("all_quality_gates_passed") is not True
        or conversion.get("derived_quarantined_dataset_accepted") is not True
        or conversion.get("manifest_sha256") != EXPECTED_V11_SHA256
    ):
        raise RuntimeError("V11 quarantined conversion is not accepted")

    base = read_manifest(base_path)
    v11 = read_manifest(v11_path)
    if Counter(record.split for record in v11) != Counter(
        {"train": 78, "val": 16, "test": 16}
    ):
        raise RuntimeError("Unexpected V11 split counts")
    if {record.dataset_id for record in v11} != {V11_DATASET_ID}:
        raise RuntimeError("Unexpected V11 dataset ID")
    selected = [record for record in v11 if record.split == "train"]
    base_groups = {record.group_id for record in base}
    selected_groups = {record.group_id for record in selected}
    if base_groups & selected_groups:
        raise RuntimeError("V11 training groups overlap the accepted manifest")
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
        raise RuntimeError("V11 training files overlap the accepted manifest")
    combined = [*base, *selected]
    write_manifest(combined, output)
    validation_datasets = sorted(
        {record.dataset_id for record in combined if record.split == "val"}
    )
    if V11_DATASET_ID in validation_datasets:
        raise RuntimeError("Synthetic V11 leaked into source validation")
    receipt = {
        "schema_version": 1,
        "base_manifest": str(base_path),
        "base_manifest_sha256": sha256(base_path),
        "v11_manifest": str(v11_path),
        "v11_manifest_sha256": sha256(v11_path),
        "v11_conversion": str(conversion_path),
        "v11_conversion_sha256": sha256(conversion_path),
        "output_manifest": str(output),
        "output_manifest_sha256": sha256(output),
        "rows": len(combined),
        "split_counts": dict(Counter(record.split for record in combined)),
        "dataset_split_counts": {
            f"{dataset}::{split}": count
            for (dataset, split), count in sorted(
                Counter(
                    (record.dataset_id, record.split) for record in combined
                ).items()
            )
        },
        "v11_rows_added": len(selected),
        "v11_roles_excluded": ["val", "test"],
        "validation_dataset_ids": validation_datasets,
        "synthetic_validation_in_source_model_selection": False,
        "group_overlap": [],
        "path_overlap": [],
        "quality_gates": {
            "inputs_sha256_locked": True,
            "quarantined_conversion_accepted": True,
            "only_v11_train_added": True,
            "v11_val_test_excluded": True,
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
