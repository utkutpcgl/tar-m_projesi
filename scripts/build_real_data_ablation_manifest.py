#!/usr/bin/env python3
"""Append only the train role of a session-frozen real dataset ablation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from agri_seg.manifest import (
    SampleRecord,
    mask_tree_sha256,
    read_manifest,
    write_manifest,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(records: list[SampleRecord]) -> dict[str, object]:
    return {
        "samples": len(records),
        "splits": {
            split: sum(record.split == split for record in records)
            for split in sorted({record.split for record in records})
        },
        "datasets": {
            dataset: sum(record.dataset_id == dataset for record in records)
            for dataset in sorted({record.dataset_id for record in records})
        },
        "sessions": len({record.group_id for record in records}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--added-real", required=True)
    parser.add_argument("--expected-added-dataset", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    base_path = Path(args.base).expanduser().resolve()
    added_path = Path(args.added_real).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    base = read_manifest(base_path)
    added = read_manifest(added_path)

    forbidden_base = sorted({record.split for record in base} - {"train", "val"})
    if forbidden_base:
        raise ValueError(f"Base manifest contains forbidden roles: {forbidden_base}")
    expected_dataset = args.expected_added_dataset
    if {record.dataset_id for record in added} != {expected_dataset}:
        raise ValueError(
            "Unexpected added dataset IDs: "
            f"{sorted({record.dataset_id for record in added})}"
        )
    if {record.split for record in added} != {"train", "external_calibration"}:
        raise ValueError(
            "Added real data must contain frozen train and external_calibration roles"
        )
    added_train = [record for record in added if record.split == "train"]
    added_calibration = [
        record for record in added if record.split == "external_calibration"
    ]
    train_groups = {record.group_id for record in added_train}
    calibration_groups = {record.group_id for record in added_calibration}
    overlap = sorted(train_groups & calibration_groups)
    if overlap:
        raise ValueError(f"Added real-data session leakage: {overlap[:10]}")

    combined = base + added_train
    write_manifest(combined, output_path)
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "base": {
                "path": str(base_path),
                "sha256": sha256(base_path),
                "mask_tree_sha256": mask_tree_sha256(base, data_root),
                **counts(base),
            },
            "added_real": {
                "path": str(added_path),
                "sha256": sha256(added_path),
                "mask_tree_sha256": mask_tree_sha256(added, data_root),
                **counts(added),
            },
        },
        "session_audit": {
            "passed": not overlap,
            "train_groups": len(train_groups),
            "external_calibration_groups": len(calibration_groups),
            "overlap": overlap,
        },
        "role_policy": {
            "base": "train_and_val_only",
            "added_real_train": "included_in_challenger_training",
            "added_real_external_calibration": "excluded_from_training",
            "external_test_present": False,
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256(output_path),
            "mask_tree_sha256": mask_tree_sha256(combined, data_root),
            **counts(combined),
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
