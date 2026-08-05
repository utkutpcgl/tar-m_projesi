#!/usr/bin/env python3
"""Evaluate the frozen real-phase checkpoint from its exact source snapshot.

The old checkpoint hashes every ``agri_seg/*.py`` file, so adding a dataset
converter invalidates it even though inference code is unchanged. This helper
materializes a temporary source tree, reverses only the two known non-inference
edits, and refuses to run unless the reconstructed tree exactly matches the
hash embedded in the checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import torch


LEGACY_REAL_SOURCE_SHA256 = (
    "733c4f49238d129fd3128effd09d7a50bd5d81d32e6b3978684cea087b9b42b4"
)
V3_CONTROL_SOURCE_SHA256 = (
    "4d08a822084321404609c3c43b5d32283249be7d93c1e3358ac02b449ac2e8f5"
)
SUPPORTED_SOURCE_SHA256 = {LEGACY_REAL_SOURCE_SHA256, V3_CONTROL_SOURCE_SHA256}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "src/agri_seg"
DEFAULT_CACHE_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/cache"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_tree_sha256(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def replace_once(value: str, current: str, legacy: str, description: str) -> str:
    count = value.count(current)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one {description} block, observed {count}"
        )
    return value.replace(current, legacy)


def reconstruct_supported_tree(destination: Path, stored_hash: str) -> list[str]:
    destination.mkdir(parents=True, exist_ok=False)
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        shutil.copy2(path, destination / path.name)

    if stored_hash == V3_CONTROL_SOURCE_SHA256:
        prepare_path = destination / "prepare.py"
        prepare = prepare_path.read_text(encoding="utf-8")
        prepare = replace_once(prepare, "import tarfile\n", "", "tarfile import")
        tar_start = "def safe_extract_tar("
        tar_end = "def acquire_dataset("
        if prepare.count(tar_start) != 1 or prepare.count(tar_end) != 1:
            raise RuntimeError("Could not isolate the TAR extraction helper")
        start = prepare.index(tar_start)
        end = prepare.index(tar_end, start)
        prepare = prepare[:start] + prepare[end:]
        current_extraction = '''    if extract:
        if zipfile.is_zipfile(archive):
            safe_extract_zip(archive, extracted)
        elif tarfile.is_tarfile(archive):
            safe_extract_tar(archive, extracted)
        else:
            raise ValueError(f"Unsupported dataset archive format: {archive}")
        return extracted
'''
        v3_extraction = '''    if extract:
        safe_extract_zip(archive, extracted)
        return extracted
'''
        prepare = replace_once(
            prepare,
            current_extraction,
            v3_extraction,
            "TAR-aware acquisition",
        )
        cropandweed_start = "_CROPANDWEED_CROPS:"
        cropandweed_end = "def _ewis_metadata("
        if (
            prepare.count(cropandweed_start) != 1
            or prepare.count(cropandweed_end) != 1
        ):
            raise RuntimeError("Could not isolate the CropAndWeed converter")
        start = prepare.index(cropandweed_start)
        end = prepare.index(cropandweed_end, start)
        prepare = prepare[:start] + prepare[end:]
        prepare_path.write_text(prepare, encoding="utf-8")

        cli_path = destination / "cli.py"
        cli = cli_path.read_text(encoding="utf-8")
        for line in (
            "    convert_cropandweed,\n",
            '            "cropandweed",\n',
        ):
            cli = replace_once(cli, line, "", f"CLI line {line.strip()}")
        gate_argument = '''    convert.add_argument(
        "--gate-config", default="configs/data/cropandweed_real_gate_v1.yaml"
    )
'''
        cli = replace_once(
            cli, gate_argument, "", "CropAndWeed gate CLI argument"
        )
        cropandweed_dispatch = '''        if args.dataset == "cropandweed":
            path = convert_cropandweed(data_root, args.gate_config)
        else:
            path = converters[args.dataset](data_root)
'''
        cli = replace_once(
            cli,
            cropandweed_dispatch,
            "        path = converters[args.dataset](data_root)\n",
            "CropAndWeed CLI dispatch",
        )
        cli_path.write_text(cli, encoding="utf-8")
        return [
            "TAR archive support in prepare.py",
            "CropAndWeed converter in prepare.py",
            "CropAndWeed CLI registration in cli.py",
        ]

    if stored_hash != LEGACY_REAL_SOURCE_SHA256:
        raise RuntimeError(f"Unsupported checkpoint source hash: {stored_hash}")

    prepare_path = destination / "prepare.py"
    prepare = prepare_path.read_text(encoding="utf-8")
    start_marker = "_SORGHUM_WEED_SPLITS = {"
    end_marker = "@dataclass(frozen=True)\nclass AuditResult:"
    if prepare.count(start_marker) != 1 or prepare.count(end_marker) != 1:
        raise RuntimeError("Could not isolate the SorghumWeed converter block")
    start = prepare.index(start_marker)
    end = prepare.index(end_marker, start)
    prepare = prepare[:start] + prepare[end:]

    current_acquisition = '''            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--no-tags",
                    source,
                    str(extracted),
                ],
                check=True,
            )
        revision = spec.get("revision")
        if revision:
            expected_revision = str(revision)
            actual_revision = subprocess.run(
                ["git", "-C", str(extracted), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if actual_revision != expected_revision:
                raise RuntimeError(
                    f"Pinned revision mismatch for {name}: "
                    f"{actual_revision} != {expected_revision}"
                )
'''
    legacy_acquisition = '''            subprocess.run(
                ["git", "clone", "--depth", "1", source, str(extracted)],
                check=True,
            )
'''
    prepare = replace_once(
        prepare,
        current_acquisition,
        legacy_acquisition,
        "pinned git acquisition",
    )
    prepare_path.write_text(prepare, encoding="utf-8")

    cli_path = destination / "cli.py"
    cli = cli_path.read_text(encoding="utf-8")
    for line in (
        "    convert_sorghum_weed,\n",
        '            "sorghum_weed",\n',
        '            "sorghum_weed": convert_sorghum_weed,\n',
    ):
        cli = replace_once(cli, line, "", f"CLI line {line.strip()}")
    cli_path.write_text(cli, encoding="utf-8")

    benchmark_path = destination / "benchmark.py"
    benchmark = benchmark_path.read_text(encoding="utf-8")
    dataset_override = '''            for key in ("manifest", "data_root", "commercial_only"):
                if key in matrix:
                    config[key] = matrix[key]
                if key in candidate:
                    config[key] = candidate[key]
'''
    benchmark = replace_once(
        benchmark,
        dataset_override,
        "",
        "benchmark dataset override",
    )
    benchmark_path.write_text(benchmark, encoding="utf-8")
    return [
        "dataset-ablation override support in benchmark.py",
        "CropCraft git acquisition pin check in prepare.py",
        "SorghumWeed converter in prepare.py",
        "SorghumWeed CLI registration in cli.py",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("manifest")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--split", default="external_calibration")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    cache_root = Path(args.cache_root).expanduser().resolve()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    metadata = checkpoint.get("metadata", {})
    stored_hash = metadata.get("source_tree_sha256")
    if stored_hash not in SUPPORTED_SOURCE_SHA256:
        raise RuntimeError(
            f"Unsupported checkpoint source hash: {stored_hash!r}"
        )

    cache_root.mkdir(parents=True, exist_ok=True)
    current_hash = source_tree_sha256(PACKAGE_ROOT)
    with tempfile.TemporaryDirectory(
        prefix="agri-seg-legacy-source-", dir=cache_root
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        legacy_package = temporary_root / "src/agri_seg"
        legacy_package.parent.mkdir()
        reversed_changes = reconstruct_supported_tree(legacy_package, stored_hash)
        reconstructed_hash = source_tree_sha256(legacy_package)
        if reconstructed_hash != stored_hash:
            raise RuntimeError(
                "Known non-inference edits do not reconstruct the checkpoint "
                f"source tree: {reconstructed_hash} != {stored_hash}"
            )

        runner = (
            "import sys; "
            "from agri_seg.engine import evaluate_checkpoint; "
            "evaluate_checkpoint(sys.argv[1], sys.argv[2], sys.argv[3], "
            "sys.argv[4], sys.argv[5], int(sys.argv[6]), int(sys.argv[7]))"
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (
                    str(legacy_package.parent),
                    environment.get("PYTHONPATH", ""),
                ),
            )
        )
        subprocess.run(
            [
                sys.executable,
                "-c",
                runner,
                str(checkpoint_path),
                str(manifest_path),
                str(data_root),
                args.split,
                str(output_path),
                str(args.batch_size),
                str(args.workers),
            ],
            cwd=temporary_root,
            env=environment,
            check=True,
        )

    receipt = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": file_sha256(checkpoint_path),
        "checkpoint_source_tree_sha256": stored_hash,
        "current_source_tree_sha256": current_hash,
        "reconstructed_source_tree_sha256": reconstructed_hash,
        "exact_checkpoint_source_match": reconstructed_hash == stored_hash,
        "reversed_non_inference_changes": reversed_changes,
        "manifest": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "split": args.split,
        "metrics": str(output_path),
        "metrics_sha256": file_sha256(output_path),
    }
    receipt_path = output_path.with_name(
        f"{output_path.stem}.legacy_compatibility.json"
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
