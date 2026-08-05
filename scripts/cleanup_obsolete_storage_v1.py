#!/usr/bin/env python3
"""Remove verified duplicate/obsolete artifacts while preserving canonical models/data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import torch
from PIL import Image

from agri_seg.manifest import read_manifest


PROJECT_ROOT = Path("/home/ankaref/utku/tarım_projesi")
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
RUNS_ROOT = DATA_ROOT / "runs"
REPORT_ROOT = DATA_ROOT / "processed/audits/segmentation_visual_report_v2"
RECEIPT = DATA_ROOT / "processed/audits/storage_cleanup_obsolete_v1.json"

KEEP_CHECKPOINTS = {
    DATA_ROOT
    / "runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt":
    "b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f",
    DATA_ROOT
    / "runs/realab_riceseg_add025_compute3780_r5_e8_v2/seed_29/last.pt":
    "ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7",
}

MANIFESTS_TO_PRESERVE = [
    DATA_ROOT
    / "processed/manifests/real_sorghum_cropcraft_robust_v3_paddy_trainval_v4_r5.csv",
    DATA_ROOT
    / "processed/manifests/real_sorghum_cropcraft_robust_v3_paddy_riceseg_trainval_v10_r1.csv",
    DATA_ROOT / "processed/manifests/riceseg_country_transfer_v1.csv",
    DATA_ROOT / "processed/manifests/sugarbeets2016_multiclass_holdout_v1.csv",
    DATA_ROOT / "processed/manifests/weedmap_calibration_v1.csv",
    DATA_ROOT / "processed/manifests/cropcraft_field_robustness_pilot_v11_r2q.csv",
]

# Entire directories whose payload has a verified extracted/processed counterpart.
REMOVE_DATA_DIRS = [
    DATA_ROOT / "runs/_obsolete",
    DATA_ROOT / "runs/_aborted",
    DATA_ROOT / "runs/export_smoke_architectures",
    DATA_ROOT / "raw/candidate_screening",
    DATA_ROOT / "raw/cropandweed/archives",
    DATA_ROOT / "raw/rice_seedling_weed/archives",
    DATA_ROOT / "raw/deblurweedseg/archives",
    DATA_ROOT / "raw/unseen_video/farmbot_soy_2026/archives",
    DATA_ROOT / "raw/tobacco_aerial/archives",
    DATA_ROOT / "raw/weedmap/archives",
    DATA_ROOT / "raw/weedy_rice_uav/archives",
    DATA_ROOT / "processed/audits/segmentation_visual_v2_smoke_debug",
]

REMOVE_DATA_FILES = [
    DATA_ROOT / "raw/sugarbeets2016_multiclass_annotations_v1/annotations.zip",
    DATA_ROOT / "raw/ewis1/EWIS1_masks.zip",
    DATA_ROOT / "raw/deblurweedseg/upstream/data.zip",
    DATA_ROOT / "raw/carrot_weed/rgbweeddetection-2220f89.zip",
    DATA_ROOT
    / "raw/unseen_video/sugarbeets2016_bonirob_2016_05_23_11_36_43_4/bonirob_2016-05-23-11-36-43_4.zip",
    DATA_ROOT / "raw/riceseg/repository/RiceSEG.zip",
    DATA_ROOT / "raw/weedsgalore/weedsgalore-dataset.zip",
    DATA_ROOT / "raw/acre/The_ACRE_Crop-Weed_Dataset.zip",
    DATA_ROOT / "raw/riceseg/repository/original.zip",
    DATA_ROOT
    / "raw/sugarbeets2016_annotated_holdout_160523_103710_v1/bonirob_2016-05-23-10-37-10_0.zip",
    DATA_ROOT / "raw/sorghum_weed/SorghumWeedDataset_Segmentation.zip",
    DATA_ROOT / "raw/ewis1/EWIS1_images.zip",
    DATA_ROOT / "raw/rose/Dataset.zip",
    DATA_ROOT / "raw/phenobench/PhenoBench-v110.zip",
    DATA_ROOT / "raw/we3ds/WE3DS.zip",
]

# Failed or superseded source-asset revisions. Final/high-quality families remain.
REMOVE_ASSET_NAMES = [
    "cropcraft_agri_early_v2",
    "cropcraft_agri_early_v2_r1",
    "cropcraft_agri_early_v2_r2",
    "cropcraft_agri_early_v2_r3",
    "cropcraft_agri_robust_v3_r1",
    "cropcraft_agri_robust_v3_r2",
    "cropcraft_field_robustness_v10_r1_paddy_only_rejected",
    "cropcraft_paddy_reproductive_v9_r1",
    "cropcraft_paddy_reproductive_v9_r2",
    "cropcraft_paddy_robust_v4_r1",
    "cropcraft_paddy_robust_v4_r2",
    "cropcraft_paddy_robust_v4_r3",
    "cropcraft_paddy_robust_v4_r4",
    "cropcraft_soy_robust_v5_r1",
    "cropcraft_soy_robust_v5_r2",
]

KEEP_ASSET_NAMES = {
    "cropcraft_agri_robust_v3_r3",
    "cropcraft_field_robustness_v10_r1",
    "cropcraft_paddy_reproductive_v9_r3",
    "cropcraft_paddy_robust_v4_r5",
    "cropcraft_sensor_motion_v7_r1",
    "cropcraft_soy_robust_v5_r3",
}

# Keep only current training inputs and the final useful simulation/stress releases.
KEEP_SYNTHETIC_NAMES = {
    "agri_robust_pilot_v3_r1",
    "field_robustness_pilot_v10_r1",
    "field_robustness_pilot_v11_r2",
    "paddy_pilot_v4_r5",
    "reproductive_pilot_v9_r3",
    "sensor_motion_pilot_v7_r1",
    "sensor_motion_pilot_v7_r2",
    "soy_pilot_v5_r5",
    "soy_stress_pilot_v6_r5",
}

EXPECTED_SYNTHETIC_NAMES = {
    "agri_early_pilot_v2", "agri_early_pilot_v2_r1", "agri_early_pilot_v2_r2",
    "agri_robust_pilot_v3_r1", "agri_robust_smoke_v3_r1", "agri_robust_smoke_v3_r3",
    "agri_smoke_v2_r1", "agri_smoke_v2_r2", "agri_smoke_v2_r3", "agri_smoke_v2_r4",
    "agri_smoke_v2_r5", "field_robustness_pilot_v10_r1",
    "field_robustness_pilot_v10_r1_plan",
    "field_robustness_pilot_v10_r1_plan_rejected_strict_gates",
    "field_robustness_pilot_v10_r1_preflight_test",
    "field_robustness_pilot_v10_r1_preflight_val",
    "field_robustness_pilot_v10_r1_rejected_strict_crop_presence",
    "field_robustness_pilot_v11_r1", "field_robustness_pilot_v11_r2",
    "field_robustness_smoke_v10_r1", "field_robustness_smoke_v10_r1_plan",
    "field_robustness_smoke_v10_r1_rejected_bright_r2",
    "field_robustness_smoke_v10_r1_rejected_height_tolerance",
    "field_robustness_smoke_v10_r1_rejected_missing_botany",
    "field_robustness_smoke_v10_r1_rejected_overexposure",
    "field_robustness_smoke_v10_r1_rejected_test_crop_floor",
    "paddy_pilot_v4_r5", "paddy_smoke_v4_r1", "paddy_smoke_v4_r2",
    "paddy_smoke_v4_r3", "paddy_smoke_v4_r4", "paddy_smoke_v4_r5",
    "paddy_smoke_v4_r5_ripple_control", "paddy_smoke_v4_r5_ripples", "pilot_v1",
    "pilot_v1_accepted", "pilot_v1_accepted_r2", "reproductive_pilot_v9_r3",
    "reproductive_smoke_v9_r1", "reproductive_smoke_v9_r2",
    "reproductive_smoke_v9_r3", "sensor_motion_pilot_v7_r1",
    "sensor_motion_pilot_v7_r2", "smoke_description_only_v1", "smoke_v1", "smoke_v2",
    "soy_mask_patch_probe_v5_r5_scene0021", "soy_pilot_v5_r3", "soy_pilot_v5_r4",
    "soy_pilot_v5_r5", "soy_smoke_v5_r1", "soy_smoke_v5_r2",
    "soy_smoke_v5_r2_retry1", "soy_smoke_v5_r3", "soy_smoke_v5_r4",
    "soy_smoke_v5_r5", "soy_stress_pilot_v6_r1", "soy_stress_pilot_v6_r2",
    "soy_stress_pilot_v6_r3", "soy_stress_pilot_v6_r4", "soy_stress_pilot_v6_r5",
}

REMOVE_PROJECT_CACHE_DIRS = [
    PROJECT_ROOT / ".pytest_cache",
    PROJECT_ROOT / "scripts/__pycache__",
    PROJECT_ROOT / "tests/__pycache__",
    PROJECT_ROOT / "src/agri_seg/__pycache__",
]

COUNTERPARTS = {
    DATA_ROOT / "raw/candidate_screening": DATA_ROOT / "raw/camelinaweed/annotated_v1",
    DATA_ROOT / "raw/cropandweed/archives": DATA_ROOT / "raw/cropandweed/repository/images",
    DATA_ROOT / "raw/rice_seedling_weed/archives": DATA_ROOT / "raw/rice_seedling_weed/repository/image",
    DATA_ROOT / "raw/deblurweedseg/archives": DATA_ROOT / "raw/deblurweedseg/repository/data",
    DATA_ROOT / "raw/unseen_video/farmbot_soy_2026/archives": DATA_ROOT / "raw/unseen_video/farmbot_soy_2026/repository",
    DATA_ROOT / "raw/tobacco_aerial/archives": DATA_ROOT / "processed/tobacco_aerial/images",
    DATA_ROOT / "raw/weedmap/archives": DATA_ROOT / "processed/weedmap/images",
    DATA_ROOT / "raw/weedy_rice_uav/archives": DATA_ROOT / "raw/weedy_rice_uav/repository/RGB",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def under(path: Path, root: Path) -> bool:
    return path.absolute().is_relative_to(root.absolute())


def validate_target(path: Path) -> None:
    if path.absolute() in {DATA_ROOT.absolute(), PROJECT_ROOT.absolute()}:
        raise RuntimeError(f"Refusing broad target: {path}")
    if not (under(path, DATA_ROOT) or path in REMOVE_PROJECT_CACHE_DIRS):
        raise RuntimeError(f"Target is outside explicit roots: {path}")


def allocated_bytes(path: Path) -> int:
    if not path.exists() and not path.is_symlink():
        return 0
    seen: set[tuple[int, int]] = set()
    total = 0

    def add(candidate: Path) -> None:
        nonlocal total
        stat = candidate.lstat()
        key = (stat.st_dev, stat.st_ino)
        if key not in seen:
            seen.add(key)
            total += stat.st_blocks * 512

    if path.is_file() or path.is_symlink():
        add(path)
        return total
    for directory, subdirs, files in os.walk(path, followlinks=False):
        add(Path(directory))
        for name in subdirs:
            candidate = Path(directory) / name
            if candidate.is_symlink():
                add(candidate)
        for name in files:
            add(Path(directory) / name)
    return total


def verify_checkpoints() -> list[dict[str, object]]:
    rows = []
    for path, expected in KEEP_CHECKPOINTS.items():
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"Canonical checkpoint missing or changed: {path}")
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        rows.append(
            {
                "path": str(path),
                "sha256": expected,
                "experiment": checkpoint["config"]["experiment"],
                "seed": checkpoint["config"]["seed"],
                "manifest": checkpoint["config"]["manifest"],
            }
        )
    return rows


def resolve_data_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else DATA_ROOT / path


def verify_manifests() -> list[dict[str, object]]:
    summaries = []
    for manifest in MANIFESTS_TO_PRESERVE:
        rows = read_manifest(manifest)
        missing = []
        for row in rows:
            for value in (row.image_path, row.mask_path):
                path = resolve_data_path(value)
                if not path.is_file():
                    missing.append(str(path))
                    if len(missing) >= 10:
                        break
            if len(missing) >= 10:
                break
        if missing:
            raise RuntimeError(f"Manifest dependencies missing for {manifest}: {missing}")
        summaries.append({"path": str(manifest), "rows": len(rows)})
    return summaries


def verify_visual_report() -> dict[str, int]:
    index = json.loads((REPORT_ROOT / "report_index.json").read_text(encoding="utf-8"))
    contacts = sorted((REPORT_ROOT / "CONTACT_SHEETS").rglob("*.jpg"))
    individuals = sorted((REPORT_ROOT / "INDIVIDUAL").rglob("*.jpg"))
    if len(contacts) != 40 or len(individuals) != 313:
        raise RuntimeError("Final visual report counts changed")
    for path in [*contacts, *individuals]:
        with Image.open(path) as image:
            image.verify()
    if not index["quality_gates"]["all_passed"]:
        raise RuntimeError("Final visual report quality gate is not passing")
    return {"contact_sheets": len(contacts), "individual_artifacts": len(individuals)}


def build_targets() -> tuple[list[Path], list[Path], list[Path]]:
    asset_root = DATA_ROOT / "raw/synthetic_assets"
    current_assets = {path.name for path in asset_root.iterdir() if path.is_dir()}
    expected_assets = set(REMOVE_ASSET_NAMES) | KEEP_ASSET_NAMES
    if current_assets - expected_assets or KEEP_ASSET_NAMES - current_assets:
        raise RuntimeError(
            f"Synthetic asset inventory changed; unexpected={sorted(current_assets - expected_assets)}, "
            f"missing_kept={sorted(KEEP_ASSET_NAMES - current_assets)}"
        )

    synthetic_root = DATA_ROOT / "synthetic/cropcraft"
    current_synthetic = {path.name for path in synthetic_root.iterdir() if path.is_dir()}
    if current_synthetic - EXPECTED_SYNTHETIC_NAMES or KEEP_SYNTHETIC_NAMES - current_synthetic:
        raise RuntimeError(
            f"Synthetic release inventory changed; unexpected={sorted(current_synthetic - EXPECTED_SYNTHETIC_NAMES)}, "
            f"missing_kept={sorted(KEEP_SYNTHETIC_NAMES - current_synthetic)}"
        )

    directories = [
        *REMOVE_DATA_DIRS,
        *(asset_root / name for name in REMOVE_ASSET_NAMES),
        *(synthetic_root / name for name in sorted(current_synthetic - KEEP_SYNTHETIC_NAMES)),
        *REMOVE_PROJECT_CACHE_DIRS,
    ]
    temp_root = DATA_ROOT / "tmp/segmentation_visual_report_v2"
    directories.extend(sorted(temp_root.glob("pytest.*")))
    directories.extend(
        path for path in [temp_root / "runtime", temp_root / "torchinductor_ankaref"] if path.exists()
    )
    files = [*REMOVE_DATA_FILES]
    truncated = temp_root / "truncated_zero_source.py"
    if truncated.exists():
        files.append(truncated)

    checkpoint_files = sorted(RUNS_ROOT.rglob("*.pt"))
    prune_weights = [path for path in checkpoint_files if path not in KEEP_CHECKPOINTS]
    prune_weights.extend(sorted(RUNS_ROOT.rglob("*.onnx")))
    return directories, files, prune_weights


def is_inside(path: Path, parents: Iterable[Path]) -> bool:
    absolute = path.absolute()
    return any(absolute.is_relative_to(parent.absolute()) for parent in parents)


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="perform permanent deletion")
    args = parser.parse_args()

    before_data_free = shutil.disk_usage(DATA_ROOT).free
    before_root_free = shutil.disk_usage(PROJECT_ROOT).free
    checkpoints = verify_checkpoints()
    manifests = verify_manifests()
    visual_report = verify_visual_report()
    for source, counterpart in COUNTERPARTS.items():
        if source.exists() and not counterpart.exists():
            raise RuntimeError(f"Archive counterpart missing: {source} -> {counterpart}")

    directories, files, weights = build_targets()
    for target in [*directories, *files, *weights]:
        validate_target(target)
    for kept in KEEP_CHECKPOINTS:
        if is_inside(kept, directories):
            raise RuntimeError(f"Canonical checkpoint falls under deletion target: {kept}")

    # Avoid counting files twice when their whole parent directory is removed.
    standalone_files = [path for path in [*files, *weights] if not is_inside(path, directories)]
    existing_dirs = [path for path in directories if path.exists() or path.is_symlink()]
    existing_files = [path for path in standalone_files if path.exists() or path.is_symlink()]
    expected_reclaim = sum(allocated_bytes(path) for path in [*existing_dirs, *existing_files])
    summary = {
        "schema_version": 1,
        "mode": "execute" if args.execute else "dry_run",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "preserve_canonical_checkpoints": True,
            "preserve_manifest_dependencies": True,
            "preserve_final_visual_report": True,
            "preserve_final_high_quality_simulation_assets": True,
            "delete_historical_metrics": False,
            "delete_preexisting_simulation_workspace": False,
            "delete_unrelated_user_caches": False,
        },
        "canonical_checkpoints": checkpoints,
        "verified_manifests": manifests,
        "visual_report": visual_report,
        "targets": {
            "directories": [str(path) for path in existing_dirs],
            "standalone_files": [str(path) for path in existing_files],
            "checkpoint_or_onnx_files": sum(path in weights for path in existing_files),
        },
        "expected_reclaim_allocated_bytes": expected_reclaim,
        "data_disk_free_before": before_data_free,
        "root_disk_free_before": before_root_free,
    }
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return

    pending = RECEIPT.with_suffix(".pending.json")
    write_json_atomic(pending, {**summary, "status": "deletion_started"})
    for path in existing_files:
        path.unlink()
    for path in sorted(existing_dirs, key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)

    post_checkpoints = verify_checkpoints()
    post_manifests = verify_manifests()
    post_visual_report = verify_visual_report()
    remaining_weights = sorted(RUNS_ROOT.rglob("*.pt"))
    if set(remaining_weights) != set(KEEP_CHECKPOINTS):
        raise RuntimeError(f"Unexpected remaining checkpoints: {remaining_weights}")
    remaining_onnx = sorted(RUNS_ROOT.rglob("*.onnx"))
    if remaining_onnx:
        raise RuntimeError(f"Unexpected remaining ONNX files: {remaining_onnx}")
    after_data_free = shutil.disk_usage(DATA_ROOT).free
    after_root_free = shutil.disk_usage(PROJECT_ROOT).free
    final = {
        **summary,
        "status": "complete",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_checkpoints_after": post_checkpoints,
        "verified_manifests_after": post_manifests,
        "visual_report_after": post_visual_report,
        "remaining_checkpoint_files": [str(path) for path in remaining_weights],
        "remaining_onnx_files": [],
        "data_disk_free_after": after_data_free,
        "root_disk_free_after": after_root_free,
        "data_disk_reclaimed_bytes": after_data_free - before_data_free,
        "root_disk_reclaimed_bytes": after_root_free - before_root_free,
        "deletion_is_permanent": True,
    }
    write_json_atomic(RECEIPT, final)
    pending.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "status": final["status"],
                "receipt": str(RECEIPT),
                "expected_reclaim_allocated_bytes": expected_reclaim,
                "data_disk_reclaimed_bytes": final["data_disk_reclaimed_bytes"],
                "root_disk_reclaimed_bytes": final["root_disk_reclaimed_bytes"],
                "remaining_checkpoint_files": final["remaining_checkpoint_files"],
                "remaining_onnx_files": final["remaining_onnx_files"],
                "verified_manifest_rows": sum(row["rows"] for row in post_manifests),
                "visual_report_after": post_visual_report,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
