#!/usr/bin/env python3
"""Apply PhenoBench-locked segmenter thresholds to the BoniRob real panel."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_cropcraft_deploy_synthetic_diagnostic_v1 import render_example
from scripts.evaluate_phenobench_cropcraft_deploy_action_ab_v1 import (
    METHODS,
    eligibility_view,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    GroundTruth,
    evaluate_actions,
    evaluate_segment_tissue,
    infer_actions,
    load_ground_truth,
    release_cuda,
    sha256,
)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def semantic_region_instances(
    semantics: np.ndarray, minimum_area_px: int
) -> tuple[np.ndarray, dict[str, int]]:
    if semantics.ndim != 2 or not set(int(value) for value in np.unique(semantics)) <= {0, 1, 2}:
        raise ValueError("Expected a 2-D common mask with IDs background=0,crop=1,weed=2")
    if minimum_area_px <= 0:
        raise ValueError("minimum_area_px must be positive")
    instances = np.zeros(semantics.shape, dtype=np.uint16)
    structure = np.ones((3, 3), dtype=np.uint8)
    next_id = 1
    counts = {"weed": 0, "crop": 0, "below_minimum": 0}
    for semantic_id, name in ((2, "weed"), (1, "crop")):
        labels, count = ndimage.label(semantics == semantic_id, structure=structure)
        for label_id in range(1, count + 1):
            region = labels == label_id
            if int(region.sum()) < minimum_area_px:
                counts["below_minimum"] += 1
                continue
            if next_id > np.iinfo(np.uint16).max:
                raise RuntimeError("Region ID overflow")
            instances[region] = next_id
            counts[name] += 1
            next_id += 1
    return instances, counts


def fixed_threshold(
    source: Mapping[str, Any], model: str, method: str, minimum_size: float
) -> float:
    return float(
        source["results"][model]["methods"][method]["eligible_size_views"]
        [str(int(minimum_size))]["validation_calibration"]
        ["balanced_max_f1"]["threshold"]
    )


def evaluate_model(
    model: Any,
    records: Sequence[GroundTruth],
    inference: Mapping[str, Any],
    threshold_source: Mapping[str, Any],
    model_name: str,
    size_views: Sequence[float],
    primary_method: str,
    primary_size: float,
) -> dict[str, Any]:
    actions, timing = infer_actions(model, "segment", records, inference)
    output: dict[str, Any] = {"timing": timing, "methods": {}}
    primary_records: list[GroundTruth] | None = None
    primary_threshold: float | None = None
    for method in METHODS:
        views: dict[str, Any] = {}
        for minimum in size_views:
            record_view, action_view = eligibility_view(
                records, actions[method], minimum
            )
            threshold = fixed_threshold(
                threshold_source, model_name, method, minimum
            )
            metric = evaluate_actions(
                action_view, record_view, threshold, include_per_sample=True
            )
            views[str(int(minimum))] = {
                "minimum_sqrt_gt_box_area_px": float(minimum),
                "fixed_threshold": threshold,
                "threshold_source": "PhenoBench validation; no BoniRob tuning",
                "test": metric,
            }
            if method == primary_method and float(minimum) == primary_size:
                primary_records = record_view
                primary_threshold = threshold
        output["methods"][method] = {"eligible_size_views": views}
    if primary_records is None or primary_threshold is None:
        raise ValueError("Primary service view is absent")
    output["primary_service"] = {
        "method": primary_method,
        "minimum_sqrt_gt_box_area_px": primary_size,
        "fixed_threshold": primary_threshold,
        "tissue": evaluate_segment_tissue(
            model, primary_records, primary_threshold, inference
        ),
    }
    release_cuda(model)
    return output


def run(config_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    settings.update(
        {name: False for name in ("clearml", "comet", "dvc", "hub", "mlflow", "neptune", "wandb")}
    )
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = resolve(PROJECT_ROOT, config["data_root"])
    if ultralytics_version != str(config["ultralytics_version"]):
        raise ValueError("Ultralytics version drift")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    locked_paths = {
        name: resolve(data_root, config[name])
        for name in ("manifest", "conversion_receipt", "manual_review", "threshold_source")
    }
    for name, path in locked_paths.items():
        if not path.is_file() or sha256(path) != str(config[f"{name}_sha256"]):
            raise ValueError(f"Locked input mismatch: {name}: {path}")
    conversion = json.loads(locked_paths["conversion_receipt"].read_text(encoding="utf-8"))
    manual_review = json.loads(locked_paths["manual_review"].read_text(encoding="utf-8"))
    if conversion.get("all_automated_conversion_gates_passed") is not True:
        raise RuntimeError("BoniRob conversion gate did not pass")
    if manual_review.get("all_release_gates_passed") is not True:
        raise RuntimeError("BoniRob manual release gate did not pass")
    if conversion["derived"]["manifest_sha256"] != sha256(locked_paths["manifest"]):
        raise RuntimeError("Conversion/manifest hash mismatch")
    threshold_source = json.loads(locked_paths["threshold_source"].read_text(encoding="utf-8"))
    output = resolve(data_root, config["output"])
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output if output.exists() else partial)
    partial.mkdir(parents=True)
    with locked_paths["manifest"].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 283 or {row["split"] for row in rows} != {"external_calibration"}:
        raise RuntimeError("Expected the frozen 283-frame external panel")
    inventory = {
        str(Path(row["rgb_path"]).resolve()): str(Path(row["common_mask_path"]).resolve())
        for row in conversion["frame_inventory"]
    }
    minimum_area = int(config["region_proxy"]["minimum_component_area_px"])
    membership_lines: list[str] = []
    total_regions = {"weed": 0, "crop": 0, "below_minimum": 0}
    for index, row in enumerate(rows):
        image_path = resolve(data_root, row["image_path"])
        semantics_path = resolve(data_root, row["mask_path"])
        if inventory.get(str(image_path)) != str(semantics_path):
            raise RuntimeError(f"Manifest/conversion inventory mismatch: {image_path}")
        semantics = np.asarray(Image.open(semantics_path), dtype=np.uint8)
        instances, counts = semantic_region_instances(semantics, minimum_area)
        for name, value in counts.items():
            total_regions[name] += int(value)
        instance_path = partial / "ground_truth/plant_instances" / f"frame_{index:05d}.png"
        instance_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(instances).save(instance_path, optimize=True)
        membership_lines.append(
            json.dumps(
                {
                    "sample_id": row["sample_id"],
                    "logical_split": "test",
                    "source_split": row["split"],
                    "field_id": row["field_id"],
                    "session_id": row["session_id"],
                    "image_path": str(image_path),
                    "semantics_path": str(semantics_path),
                    "plant_instances_path": str(
                        output / instance_path.relative_to(partial)
                    ),
                    "eligible_instances": counts["weed"] + counts["crop"],
                    "eligible_weed_instances": counts["weed"],
                    "eligible_crop_instances": counts["crop"],
                    "region_proxy_not_botanical_instance": True,
                },
                sort_keys=True,
            )
        )
    membership_partial = partial / "membership.jsonl"
    membership_partial.write_text("\n".join(membership_lines) + "\n", encoding="utf-8")
    partial.replace(output)
    membership = output / "membership.jsonl"
    records = load_ground_truth(membership, "test", minimum_area)
    size_views = [float(value) for value in config["eligible_minimum_sqrt_box_px"]]
    primary_method = str(config["primary_method"])
    primary_size = float(config["primary_service_minimum_sqrt_box_px"])
    model_results: dict[str, Any] = {}
    loaded: dict[str, Any] = {}
    locked_models: dict[str, Any] = {}
    try:
        for model_name, model_cfg in config["models"].items():
            checkpoint = resolve(data_root, model_cfg["checkpoint"])
            if not checkpoint.is_file() or sha256(checkpoint) != str(model_cfg["checkpoint_sha256"]):
                raise ValueError(f"Locked model mismatch: {model_name}")
            model = YOLO(str(checkpoint))
            if model.task != "segment":
                raise ValueError(f"Model is not segmentation: {model_name}")
            loaded[model_name] = model
            locked_models[model_name] = {"checkpoint": str(checkpoint), "sha256": sha256(checkpoint)}
            model_results[model_name] = evaluate_model(
                model,
                records,
                config["inference"],
                threshold_source,
                model_name,
                size_views,
                primary_method,
                primary_size,
            )
        gallery_cfg = config["gallery"]
        gallery_model = str(gallery_cfg["model"])
        if gallery_model not in loaded:
            raise ValueError("Gallery model must be selected from the real A/B")
        gallery_threshold = fixed_threshold(
            threshold_source, gallery_model, primary_method, primary_size
        )
        gallery_root = output / "gallery"
        gallery_root.mkdir()
        gallery_rows = []
        for index in [int(value) for value in gallery_cfg["frame_indices"]]:
            truth = records[index]
            path = gallery_root / f"bonirob_{index:03d}.jpg"
            render_example(
                loaded[gallery_model],
                truth,
                threshold=gallery_threshold,
                inference=config["inference"],
                output=path,
                title="BoniRob dış robot-view geliştirme paneli — sabit eşikli noktasal ilaçlama",
            )
            gallery_rows.append({"sample_id": truth.sample_id, "path": str(path), "sha256": sha256(path)})
    except Exception:
        # Preserve a complete provenance package for diagnosis, but never emit a
        # success receipt after partial inference.
        raise
    finally:
        for model in loaded.values():
            release_cuda(model)
    receipt = {
        "schema_version": 1,
        "protocol": config["protocol"],
        "status": "real_robot_external_development_panel_complete_not_deployment_proof",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in locked_paths.items()
        },
        "frames": len(records),
        "field_ids": sorted({row["field_id"] for row in rows}),
        "session_ids": sorted({row["session_id"] for row in rows}),
        "region_proxy_counts": total_regions,
        "membership": str(membership),
        "membership_sha256": sha256(membership),
        "locked_models": locked_models,
        "results": model_results,
        "gallery": {"model": gallery_model, "fixed_threshold": gallery_threshold, "frames": gallery_rows},
        "claims": config["claims"],
        "limitations": [
            "All 283 adjacent frames come from one field, date and robot session.",
            "This development panel was consumed by previous model studies.",
            "Semantic connected regions can merge touching plants or split occluded plants.",
            "The public camera geometry is not the proposed controlled deployment geometry.",
        ],
    }
    metrics = output / "external_action_metrics.json"
    metrics.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Gerçek BoniRob dış paneli\n\nYeşil mahsul, kırmızı gerçek yabani ot, mor model ot tahmini; mavi nokta doğru ve sarı çarpı hatalı müdahaledir. Eşikler PhenoBench validasyonundan sabittir; bu tek oturum nihai saha kanıtı değildir.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": receipt["status"], "metrics": str(metrics), "gallery": gallery_rows}, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/sugarbeets2016_yolo_segment_external_v1.yaml"),
    )
    arguments = parser.parse_args()
    run(arguments.config)


if __name__ == "__main__":
    main()
