#!/usr/bin/env python3
"""Append a scene-audited synthetic pilot to a real-development manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
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
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--synthetic", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-synthetic-dataset", required=True)
    args = parser.parse_args()

    base_path = Path(args.base).expanduser().resolve()
    synthetic_path = Path(args.synthetic).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    base = read_manifest(base_path)
    synthetic = read_manifest(synthetic_path)

    forbidden_base = sorted({row.split for row in base} - {"train", "val"})
    if forbidden_base:
        raise ValueError(f"Base manifest contains forbidden roles: {forbidden_base}")
    if {row.split for row in synthetic} != {"train", "val"}:
        raise ValueError("Synthetic pilot must have scene-disjoint train and val")
    synthetic_datasets = {row.dataset_id for row in synthetic}
    expected = args.expected_synthetic_dataset
    if synthetic_datasets != {expected}:
        raise ValueError(
            f"Unexpected synthetic dataset IDs: {sorted(synthetic_datasets)}"
        )
    train_groups = {row.group_id for row in synthetic if row.split == "train"}
    val_groups = {row.group_id for row in synthetic if row.split == "val"}
    overlap = sorted(train_groups & val_groups)
    if overlap:
        raise ValueError(f"Synthetic scene leakage: {overlap[:10]}")

    # The synthetic validation scenes validate the renderer only. They are
    # relabeled train here because model selection remains entirely real-data
    # based and the sampler controls synthetic exposure at exactly 10%.
    combined = base + [replace(row, split="train") for row in synthetic]
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
            "synthetic": {
                "path": str(synthetic_path),
                "sha256": sha256(synthetic_path),
                "mask_tree_sha256": mask_tree_sha256(synthetic, data_root),
                **counts(synthetic),
            },
        },
        "scene_audit": {
            "passed": True,
            "train_groups": len(train_groups),
            "validation_groups": len(val_groups),
            "overlap": overlap,
        },
        "role_policy": {
            "base": "train_and_val_only",
            "synthetic_original": "scene_disjoint_80_20_renderer_QC",
            "synthetic_combined": (
                "all_pilot_scenes_train; downstream selection is real-only"
            ),
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
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
