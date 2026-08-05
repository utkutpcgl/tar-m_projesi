#!/usr/bin/env python3
"""Quantify RiceSEG condition/semantic gaps against the accepted paddy pack."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from agri_seg.constants import CROP, WEED
from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def require_inside(path: Path, root: Path, name: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{name} must remain below {root}: {resolved}") from exc
    return resolved


def resolve(recorded: str, data_root: Path) -> Path:
    path = Path(recorded)
    result = (path if path.is_absolute() else data_root / path).resolve()
    if not result.is_file():
        raise FileNotFoundError(result)
    return result


def source_mask_path(record: SampleRecord, data_root: Path) -> Path:
    common = resolve(record.mask_path, data_root)
    common_root = (data_root / "processed/riceseg/common_masks").resolve()
    relative = common.relative_to(common_root)
    source = data_root / "processed/riceseg/source_masks" / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    return source


def subgroup(record: SampleRecord) -> str:
    parts = record.sample_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "riceseg":
        raise ValueError(f"Unexpected RiceSEG sample ID: {record.sample_id}")
    return parts[1]


def image_stats(image_path: Path, mask_path: Path) -> dict[str, float]:
    with Image.open(image_path) as handle:
        rgb = np.asarray(
            handle.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR),
            dtype=np.float32,
        ) / 255.0
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    saturation = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )
    gray = rgb.mean(axis=2)
    texture = (
        np.abs(np.diff(gray, axis=0)).mean()
        + np.abs(np.diff(gray, axis=1)).mean()
    ) / 2.0
    laplacian = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    with Image.open(mask_path) as handle:
        mask = np.asarray(handle.convert("L"), dtype=np.uint8)
    if not set(int(value) for value in np.unique(mask)) <= {0, 1, 2}:
        raise ValueError(f"Expected exhaustive common mask: {mask_path}")
    return {
        "brightness_mean": float(rgb.mean()),
        "brightness_std": float(rgb.std()),
        "saturation_mean": float(saturation.mean()),
        "green_dominance": float(
            (rgb[:, :, 1] - (rgb[:, :, 0] + rgb[:, :, 2]) / 2.0).mean()
        ),
        "texture_abs_gradient": float(texture),
        "laplacian_variance": float(laplacian.var()),
        "shadow_fraction": float(np.count_nonzero(maximum < 0.08) / maximum.size),
        "highlight_fraction": float(np.count_nonzero(minimum > 0.92) / minimum.size),
        "crop_fraction": float(np.count_nonzero(mask == CROP) / mask.size),
        "weed_fraction": float(np.count_nonzero(mask == WEED) / mask.size),
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Cannot aggregate empty condition statistics")
    metrics: dict[str, Any] = {}
    for name in sorted(rows[0]):
        values = np.asarray([row[name] for row in rows], dtype=np.float64)
        metrics[name] = {
            "mean": float(values.mean()),
            "q05": float(np.quantile(values, 0.05)),
            "q50": float(np.quantile(values, 0.50)),
            "q95": float(np.quantile(values, 0.95)),
        }
    return {"samples": len(rows), "metrics": metrics}


def factor_evidence(
    candidates: dict[str, Any],
    source_pixels: Counter[int],
    bearing_samples: Counter[int],
    total_pixels: int,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, specification in candidates.items():
        classes = [int(value) for value in specification["source_classes"]]
        pixels = sum(source_pixels[value] for value in classes)
        bearing = sum(bearing_samples[value] for value in classes)
        result[str(name)] = {
            "source_classes": classes,
            "source_pixels": pixels,
            "source_pixel_fraction": pixels / total_pixels,
            "class_bearing_sample_sum": bearing,
            "class_bearing_sample_note": (
                "Sum over source classes; a sample containing multiple selected classes is counted per class."
            ),
            "accepted_pack_explicitly_covered": bool(
                specification["accepted_pack_explicitly_covered"]
            ),
            "evidence": str(specification["evidence"]),
        }
    return result


def select_factor(
    evidence: dict[str, dict[str, Any]], selected_in_config: str
) -> str:
    eligible = [
        (name, row)
        for name, row in evidence.items()
        if not row["accepted_pack_explicitly_covered"]
    ]
    if not eligible:
        raise ValueError("No uncovered synthetic factor remains")
    selected = max(
        eligible,
        key=lambda item: (
            float(item[1]["source_pixel_fraction"]),
            int(item[1]["class_bearing_sample_sum"]),
            item[0],
        ),
    )[0]
    require_equal("frozen selected factor", selected, selected_in_config)
    return selected


def accepted_pack_inventory(pack: dict[str, Any], manifest: list[SampleRecord]) -> dict[str, Any]:
    assets = pack["generated_assets"]
    crop = assets["crop"]
    paddy = pack["paddy_v4_assets"]
    phenotypes = [str(value) for value in crop["albedo_phenotypes"]]
    model_rows = crop["models"]
    serialized = json.dumps(crop, sort_keys=True).lower()
    late_records = [
        record.sample_id
        for record in manifest
        if any(token in record.growth_stage.lower() for token in ("reproductive", "panicle", "mature", "senescent"))
    ]
    return {
        "pack_id": pack["pack_id"],
        "crop_models": len(model_rows),
        "unique_crop_geometries": len(crop["unique_geometry_sha256"]),
        "declared_growth_stage_bins": len({int(row["growth_stage"]) for row in model_rows}),
        "target_age_days": paddy["rice_morphology_contract"]["target_age_days"],
        "phenotypes": phenotypes,
        "weed_models": sum(len(group["models"]) for group in assets["weeds"].values()),
        "explicit_panicle_models": sum("panicle" in str(row).lower() for row in model_rows),
        "explicit_senescent_phenotypes": sum("senesc" in value.lower() for value in phenotypes),
        "explicit_duckweed_models": serialized.count("duckweed"),
        "pilot_records_declaring_late_stage": len(late_records),
        "pilot_growth_stage_examples": sorted({record.growth_stage for record in manifest})[:5],
        "interpretation": (
            "The five numeric bins are early height/morphology variants at 15-25 days, "
            "not five full-cycle rice stages."
        ),
    }


def analyze(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    config = load_yaml(config_path)
    require_equal("schema version", config.get("schema_version"), 1)
    data_root = Path(str(config["data_root"])).expanduser().resolve()
    project_root = Path(str(config["project_root"])).expanduser().resolve()
    locked_paths: dict[str, Path] = {}
    for name, specification in config["locked_inputs"].items():
        root = project_root if specification.get("root") == "project" else data_root
        path = require_inside(root / str(specification["path"]), root, name)
        if not path.is_file():
            raise FileNotFoundError(path)
        require_equal(f"{name} SHA-256", sha256(path), str(specification["sha256"]))
        locked_paths[name] = path

    quality = load_json(locked_paths["riceseg_quality_receipt"])
    require_equal("RiceSEG quality pass", quality.get("passed"), True)
    release_gate = load_yaml(locked_paths["riceseg_release_gate"])
    pack = load_json(locked_paths["accepted_paddy_pack"])
    paddy_quality = load_json(locked_paths["accepted_paddy_quality"])
    paddy_release = load_json(locked_paths["accepted_paddy_release"])
    require_equal("accepted paddy static gate", paddy_quality["custom"]["all_quality_gates_passed"], True)
    require_equal("accepted paddy release gate", paddy_release["all_quality_gates_passed"], True)
    require_equal("accepted paddy pack id", pack["pack_id"], "cropcraft_paddy_robust_v4_r5")
    require_equal(
        "accepted release pack SHA-256",
        paddy_release["asset_pack"]["manifest_sha256"],
        sha256(locked_paths["accepted_paddy_pack"]),
    )

    real_records = read_manifest(locked_paths["riceseg_manifest"])
    synthetic_records = read_manifest(locked_paths["accepted_paddy_manifest"])
    require_equal("eligible RiceSEG samples", len(real_records), int(quality["eligible_samples"]))
    require_equal("accepted paddy pilot samples", len(synthetic_records), 100)
    require_equal("RiceSEG manifest hash", manifest_sha256(locked_paths["riceseg_manifest"]), quality["manifests"]["eligible"]["sha256"])

    source_pixels: Counter[int] = Counter()
    bearing_samples: Counter[int] = Counter()
    subgroup_pixels: dict[str, Counter[int]] = defaultdict(Counter)
    subgroup_samples: Counter[str] = Counter()
    real_stats: list[dict[str, float]] = []
    real_stats_by_subgroup: dict[str, list[dict[str, float]]] = defaultdict(list)
    for record in real_records:
        source_path = source_mask_path(record, data_root)
        with Image.open(source_path) as handle:
            source = np.asarray(handle.convert("L"), dtype=np.uint8)
        counts = np.bincount(source.ravel(), minlength=6)
        values = set(int(value) for value in np.unique(source))
        if not values <= set(range(6)):
            raise ValueError(f"Unexpected RiceSEG source mask: {source_path}")
        name = subgroup(record)
        for value, count in enumerate(counts):
            source_pixels[value] += int(count)
            subgroup_pixels[name][value] += int(count)
            if count > 0:
                bearing_samples[value] += 1
        subgroup_samples[name] += 1
        row = image_stats(resolve(record.image_path, data_root), resolve(record.mask_path, data_root))
        real_stats.append(row)
        real_stats_by_subgroup[name].append(row)

    synthetic_stats = [
        image_stats(resolve(record.image_path, data_root), resolve(record.mask_path, data_root))
        for record in synthetic_records
    ]
    total_pixels = sum(source_pixels.values())
    require_equal("eligible RiceSEG pixel total", total_pixels, len(real_records) * 512 * 512)
    evidence = factor_evidence(
        config["factor_candidates"], source_pixels, bearing_samples, total_pixels
    )
    selected = select_factor(
        evidence, str(config["selection_rule"]["selected_factor"])
    )
    inventory = accepted_pack_inventory(pack, synthetic_records)
    require_equal("accepted explicit panicle coverage", inventory["explicit_panicle_models"], 0)
    require_equal("accepted explicit senescent coverage", inventory["explicit_senescent_phenotypes"], 0)
    require_equal("accepted explicit duckweed coverage", inventory["explicit_duckweed_models"], 0)
    require_equal("accepted late-stage pilot records", inventory["pilot_records_declaring_late_stage"], 0)

    real_aggregate = aggregate(real_stats)
    synthetic_aggregate = aggregate(synthetic_stats)
    median_outside: dict[str, bool] = {}
    for metric, synthetic_values in synthetic_aggregate["metrics"].items():
        real_values = real_aggregate["metrics"][metric]
        median_outside[metric] = not (
            real_values["q05"] <= synthetic_values["q50"] <= real_values["q95"]
        )
    subgroup_summary: dict[str, Any] = {}
    for name in sorted(subgroup_pixels):
        pixels = subgroup_pixels[name]
        subtotal = sum(pixels.values())
        specification = release_gate["subdatasets"][name]
        subgroup_summary[name] = {
            "samples": subgroup_samples[name],
            "role": specification["coverage_role"],
            "growth_stages": specification["growth_stages"],
            "source_class_pixels": {str(value): pixels[value] for value in range(6)},
            "source_class_fraction": {
                str(value): pixels[value] / subtotal for value in range(6)
            },
            "late_reproductive_rice_fraction": (pixels[2] + pixels[3]) / subtotal,
            "duckweed_fraction": pixels[5] / subtotal,
            "rgb_common_statistics": aggregate(real_stats_by_subgroup[name]),
        }

    output = require_inside(
        data_root / str(config["output"]), data_root, "RiceSEG asset-gap output"
    )
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified_and_factor_selected",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "locked_inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in locked_paths.items()
        },
        "riceseg": {
            "samples": len(real_records),
            "source_class_pixels": {str(value): source_pixels[value] for value in range(6)},
            "source_class_fraction": {
                str(value): source_pixels[value] / total_pixels for value in range(6)
            },
            "source_class_bearing_samples": {
                str(value): bearing_samples[value] for value in range(6)
            },
            "by_subdataset": subgroup_summary,
            "rgb_common_statistics": real_aggregate,
        },
        "accepted_paddy": {
            "inventory": inventory,
            "rgb_common_statistics": synthetic_aggregate,
            "synthetic_median_outside_riceseg_q05_q95": median_outside,
        },
        "factor_evidence": evidence,
        "selection": {
            "rule": config["selection_rule"]["primary"],
            "tie_breaker": config["selection_rule"]["tie_breaker"],
            "selected_factor": selected,
            "deferred_factor": config["selection_rule"]["deferred_factor"],
            "model_results_used": False,
            "interpretation": (
                "Late reproductive rice is the largest semantically explicit missing factor. "
                "Classes 2+3 represent senescent rice tissue and panicles; the accepted paddy "
                "pack covers only 15-25-day early plants. Duckweed is real and uncovered but has "
                "lower eligible source-pixel prevalence, so it remains the next isolated factor."
            ),
        },
        "external_asset_candidates": config["external_asset_candidates"],
        "external_asset_bytes_acquired": False,
        "large_synthetic_batch_generated": False,
        "external_test_used": False,
        "passed": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/simulation/riceseg_condition_asset_selection_v9.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    output = analyze(arguments.config)
    print(
        json.dumps(
            {"output": str(output), "sha256": sha256(output)},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
