#!/usr/bin/env python3
"""Build role-safe manifests for real-data and synthetic-data ablations."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from agri_seg.manifest import SampleRecord, read_manifest, write_manifest


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
    parser.add_argument("--real", required=True)
    parser.add_argument("--sorghum", required=True)
    parser.add_argument("--synthetic", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    real_path = Path(args.real).expanduser().resolve()
    sorghum_path = Path(args.sorghum).expanduser().resolve()
    synthetic_path = Path(args.synthetic).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    real = [
        record for record in read_manifest(real_path) if record.split in {"train", "val"}
    ]
    sorghum_train = [
        record for record in read_manifest(sorghum_path) if record.split == "train"
    ]
    synthetic = read_manifest(synthetic_path)
    real_sorghum = real + sorghum_train
    combined_synthetic = [replace(record, split="train") for record in synthetic]
    real_sorghum_synthetic = real_sorghum + combined_synthetic

    outputs = {
        "real_sorghum": output_dir / "real_sorghum_trainval_v1.csv",
        "real_sorghum_synthetic": (
            output_dir / "real_sorghum_cropcraft_trainval_v1.csv"
        ),
        "synthetic_only": output_dir / "cropcraft_stock_pilot_trainval_v1.csv",
    }
    payloads = {
        "real_sorghum": real_sorghum,
        "real_sorghum_synthetic": real_sorghum_synthetic,
        "synthetic_only": synthetic,
    }
    for name, path in outputs.items():
        write_manifest(payloads[name], path)

    receipt = {
        "schema_version": 1,
        "sources": {
            "real": {"path": str(real_path), "sha256": sha256(real_path)},
            "sorghum": {
                "path": str(sorghum_path),
                "sha256": sha256(sorghum_path),
            },
            "synthetic": {
                "path": str(synthetic_path),
                "sha256": sha256(synthetic_path),
            },
        },
        "role_policy": {
            "real": "train_and_val_only",
            "sorghum": "official_train_only; calibration/test kept external",
            "synthetic_combined": "all pilot scenes train; selection remains real-only",
            "synthetic_only": "scene-disjoint 80/20 train/val",
        },
        "outputs": {
            name: {
                "path": str(path),
                "sha256": sha256(path),
                **counts(payloads[name]),
            }
            for name, path in outputs.items()
        },
    }
    receipt_path = output_dir / "simulation_ablation_manifests_v1.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
