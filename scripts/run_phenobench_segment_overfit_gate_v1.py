#!/usr/bin/env python3
"""Run an intentional small-set overfit gate for the locked segmenter."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
import yaml

from scripts.analyze_phenobench_actionable_size_v1 import (
    SizedAction,
    evaluate_policy,
    select_validation_policy,
)
from scripts.evaluate_phenobench_detect_segment_fair_v1 import (
    Action,
    GroundTruth,
    evaluate_actions,
    infer_actions,
    load_ground_truth,
    release_cuda,
    sha256,
)
from scripts.train_phenobench_detect_segment_fair_v1 import run as train_arm


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _rank(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def select_balanced_subset(
    records: Sequence[GroundTruth],
    metadata_by_sample: Mapping[str, Mapping[str, Any]],
    *,
    count: int,
    minimum_size_px: float,
    seed: int,
) -> list[GroundTruth]:
    """Select actionable frames round-robin across plot groups."""
    if count <= 0:
        raise ValueError("count must be positive")
    groups: dict[str, list[GroundTruth]] = defaultdict(list)
    for record in records:
        if not any(float(size) >= minimum_size_px for size in record.weed_sizes.values()):
            continue
        metadata = metadata_by_sample.get(record.sample_id)
        if metadata is None:
            raise ValueError(f"Missing metadata for {record.sample_id}")
        groups[str(metadata["plot_group"])].append(record)
    available = sum(len(values) for values in groups.values())
    if count > available:
        raise ValueError(f"Requested {count} records, only {available} are eligible")
    for values in groups.values():
        values.sort(key=lambda record: _rank(seed, record.sample_id))
    group_names = sorted(groups, key=lambda name: _rank(seed, name))
    selected: list[GroundTruth] = []
    round_index = 0
    while len(selected) < count:
        progress = False
        for group_name in group_names:
            values = groups[group_name]
            if round_index < len(values):
                selected.append(values[round_index])
                progress = True
                if len(selected) == count:
                    break
        if not progress:
            raise RuntimeError("Balanced selector stalled")
        round_index += 1
    return selected


def _sized_actions(
    actions: Mapping[str, Sequence[Action]],
) -> dict[str, list[SizedAction]]:
    return {
        sample_id: [
            SizedAction(
                sample_id=action.sample_id,
                confidence=action.confidence,
                x=action.x,
                y=action.y,
                target_kind=action.target_kind,
                target_instance_id=action.target_instance_id,
                predicted_box_size_px=float("inf"),
                predicted_mask_size_px=float("inf"),
            )
            for action in sample_actions
        ]
        for sample_id, sample_actions in actions.items()
    }


def _thresholds(config: Mapping[str, Any]) -> list[float]:
    start = float(config["confidence_start"])
    stop = float(config["confidence_stop"])
    step = float(config["confidence_step"])
    if step <= 0 or stop < start:
        raise ValueError("Invalid confidence grid")
    count = int(round((stop - start) / step)) + 1
    return [round(start + index * step, 10) for index in range(count)]


def _load_metadata(membership: Path, split: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for line in membership.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["logical_split"] == split:
            output[str(row["sample_id"])] = row
    return output


def _write_runtime_protocol(
    *,
    static_config: Mapping[str, Any],
    config_path: Path,
    data_root: Path,
    source_segment_yaml: Path,
    initial_checkpoint: Path,
    selected: Sequence[GroundTruth],
    output_project: Path,
) -> tuple[Path, Path, Path]:
    protocol_directory = output_project / "protocol"
    protocol_directory.mkdir(parents=True, exist_ok=False)
    source_yaml = yaml.safe_load(source_segment_yaml.read_text(encoding="utf-8"))
    segment_root = Path(str(source_yaml["path"]))
    logical_split = str(static_config["subset"]["logical_split"])
    image_list = protocol_directory / "train_images.txt"
    processed_images: list[Path] = []
    for record in selected:
        path = segment_root / f"images/{logical_split}" / record.image_path.name
        label = segment_root / f"labels/{logical_split}" / f"{path.stem}.txt"
        if not path.is_file() or not label.is_file():
            raise FileNotFoundError(f"Missing processed pair for {record.sample_id}")
        processed_images.append(path)
    image_list.write_text(
        "".join(f"{path}\n" for path in processed_images), encoding="utf-8"
    )
    subset_yaml = protocol_directory / "subset_dataset.yaml"
    subset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(segment_root),
                "train": str(image_list),
                "val": str(image_list),
                "names": {0: "weed", 1: "crop"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    runtime_config = {
        "schema_version": 1,
        "protocol": static_config["protocol"],
        "data_root": str(data_root),
        "dataset_receipt": static_config["dataset_receipt"],
        "dataset_receipt_sha256": static_config["dataset_receipt_sha256"],
        "arms": {
            "segment": {
                "task": "segment",
                "dataset_yaml": str(subset_yaml),
                "dataset_yaml_sha256": sha256(subset_yaml),
                "pretrained_checkpoint": str(initial_checkpoint),
                "pretrained_checkpoint_sha256": sha256(initial_checkpoint),
                "run_name": static_config["output"]["run_name"],
            }
        },
        "model_family": static_config["model_family"],
        "training": static_config["training"],
        "selection": {
            "checkpoint": "last.pt",
            "reason": "intentional final-epoch same-set capacity test",
            "validation_role": "same-set training diagnostic only",
            "test_role": "not used",
        },
        "output": {"project": str(output_project)},
        "claims": static_config["claims"],
    }
    training_config = protocol_directory / "runtime_training_config.yaml"
    training_config.write_text(
        yaml.safe_dump(runtime_config, sort_keys=False), encoding="utf-8"
    )
    manifest = protocol_directory / "subset_manifest.jsonl"
    metadata = _load_metadata(
        _resolve(data_root, static_config["membership"]),
        str(static_config["subset"]["logical_split"]),
    )
    with manifest.open("w", encoding="utf-8") as handle:
        for record, processed_path in zip(selected, processed_images, strict=True):
            row = metadata[record.sample_id]
            handle.write(
                json.dumps(
                    {
                        "sample_id": record.sample_id,
                        "capture_date": row["capture_date"],
                        "plot_group": row["plot_group"],
                        "source_image": str(record.image_path),
                        "training_image": str(processed_path),
                        "eligible_weeds": len(record.weed_sizes),
                        "actionable_weeds": sum(
                            float(size)
                            >= float(static_config["subset"]["minimum_actionable_gt_size_px"])
                            for size in record.weed_sizes.values()
                        ),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return training_config, manifest, image_list


def _resume_interrupted_training(
    *,
    static_config: Mapping[str, Any],
    runtime_config: Path,
    output_project: Path,
) -> dict[str, Any]:
    """Resume only from the last fully serialized epoch of this exact protocol."""
    from ultralytics import YOLO, __version__ as ultralytics_version, settings

    disabled_integrations = {
        "clearml": False,
        "comet": False,
        "dvc": False,
        "hub": False,
        "mlflow": False,
        "neptune": False,
        "wandb": False,
    }
    settings.update(disabled_integrations)
    run_directory = output_project / str(static_config["output"]["run_name"])
    last = run_directory / "weights/last.pt"
    best = run_directory / "weights/best.pt"
    results_csv = run_directory / "results.csv"
    required = (runtime_config, last, best, results_csv)
    if any(not path.is_file() for path in required):
        raise FileNotFoundError("Interrupted run is missing a resume artifact")
    epochs_before = len(results_csv.read_text(encoding="utf-8").splitlines()) - 1
    requested_epochs = int(static_config["training"]["epochs"])
    if not 0 < epochs_before < requested_epochs:
        raise ValueError(
            f"Resume requires 1..{requested_epochs - 1} completed epochs, got {epochs_before}"
        )
    checkpoint_before_sha256 = sha256(last)
    model = YOLO(str(last))
    checkpoint_args = model.ckpt.get("train_args", {})
    locked_args = {
        "batch": int(static_config["training"]["batch"]),
        "imgsz": int(static_config["training"]["image_size"]),
        "mask_ratio": int(static_config["training"]["mask_ratio"]),
        "epochs": requested_epochs,
    }
    for key, expected in locked_args.items():
        if int(checkpoint_args.get(key, -1)) != expected:
            raise ValueError(f"Resume checkpoint argument drift: {key}")
    started = time.monotonic()
    model.train(resume=True)
    elapsed = time.monotonic() - started
    completed_epochs = len(results_csv.read_text(encoding="utf-8").splitlines()) - 1
    if completed_epochs != requested_epochs:
        raise RuntimeError(
            f"Resume exposure violated: requested {requested_epochs}, completed {completed_epochs}"
        )
    parameter_count = sum(parameter.numel() for parameter in model.model.parameters())
    release_cuda(model)
    receipt = {
        "schema_version": 1,
        "protocol": static_config["protocol"],
        "status": "capacity_training_complete_after_external_gpu_contention_resume",
        "arm": "segment",
        "task": "segment",
        "config": str(runtime_config),
        "config_sha256": sha256(runtime_config),
        "dataset_yaml": str(output_project / "protocol/subset_dataset.yaml"),
        "dataset_yaml_sha256": sha256(output_project / "protocol/subset_dataset.yaml"),
        "pretrained_checkpoint": str(
            _resolve(Path(str(static_config["data_root"])), static_config["initial_checkpoint"])
        ),
        "pretrained_checkpoint_sha256": static_config["initial_checkpoint_sha256"],
        "ultralytics_version": ultralytics_version,
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(int(static_config["training"]["device"])),
            "resume_elapsed_seconds": elapsed,
            "interruption_reason": "an unrelated Ollama model occupied 8.2 GiB GPU memory",
        },
        "training": {
            "epochs_completed_before_resume": epochs_before,
            "epochs_completed": completed_epochs,
            "epochs_requested": requested_epochs,
            "batch": int(static_config["training"]["batch"]),
            "parameter_count": parameter_count,
            "resume_checkpoint_sha256": checkpoint_before_sha256,
        },
        "selection": {
            "checkpoint": "last.pt",
            "reason": "fixed final epoch; resume continued exact optimizer state",
            "validation_role": "same-set training diagnostic only",
            "test_role": "not used",
        },
        "artifacts": {
            "run_directory": str(run_directory),
            "best_checkpoint": str(best),
            "best_checkpoint_sha256": sha256(best),
            "fixed_final_checkpoint": str(last),
            "fixed_final_checkpoint_sha256": sha256(last),
            "results_csv": str(results_csv),
            "results_csv_sha256": sha256(results_csv),
        },
        "claims": static_config["claims"],
    }
    receipt_path = run_directory / "run_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def run(
    config_path: Path,
    *,
    resume: bool = False,
    evaluate_only: bool = False,
) -> dict[str, Any]:
    from ultralytics import YOLO, __version__ as ultralytics_version

    config_path = config_path.expanduser().resolve()
    static_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    data_root = _resolve(project_root, static_config["data_root"])
    receipt = _resolve(data_root, static_config["dataset_receipt"])
    membership = _resolve(data_root, static_config["membership"])
    source_segment_yaml = _resolve(data_root, static_config["source_segment_yaml"])
    initial_checkpoint = _resolve(data_root, static_config["initial_checkpoint"])
    locked = (
        (receipt, static_config["dataset_receipt_sha256"]),
        (membership, static_config["membership_sha256"]),
        (source_segment_yaml, static_config["source_segment_yaml_sha256"]),
        (initial_checkpoint, static_config["initial_checkpoint_sha256"]),
    )
    for path, expected in locked:
        if not path.is_file() or sha256(path) != str(expected):
            raise ValueError(f"Locked input mismatch: {path}")
    if ultralytics_version != str(static_config["model_family"]["package_version"]):
        raise ValueError("Ultralytics version mismatch")

    subset_config = static_config["subset"]
    split = str(subset_config["logical_split"])
    dataset_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    minimum_area = int(dataset_receipt["label_contract"]["minimum_full_instance_area_px"])
    records = load_ground_truth(membership, split, minimum_area)
    metadata = _load_metadata(membership, split)
    allowed_groups = {
        str(group) for group in subset_config.get("allowed_plot_groups", ())
    }
    if allowed_groups:
        records = [
            record
            for record in records
            if str(metadata[record.sample_id]["plot_group"]) in allowed_groups
        ]
        observed_groups = {
            str(metadata[record.sample_id]["plot_group"]) for record in records
        }
        if observed_groups != allowed_groups:
            raise ValueError(
                f"Allowed plot groups missing: {sorted(allowed_groups - observed_groups)}"
            )
    selected = select_balanced_subset(
        records,
        metadata,
        count=int(subset_config["images"]),
        minimum_size_px=float(subset_config["minimum_actionable_gt_size_px"]),
        seed=int(subset_config["seed"]),
    )
    output_project = _resolve(data_root, static_config["output"]["project"])
    if resume and evaluate_only:
        raise ValueError("--resume and --evaluate-only are mutually exclusive")
    if evaluate_only:
        receipt_path = (
            output_project
            / str(static_config["output"]["run_name"])
            / "run_receipt.json"
        )
        if not receipt_path.is_file():
            raise FileNotFoundError(receipt_path)
        training_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = output_project / "protocol/subset_manifest.jsonl"
        image_list = output_project / "protocol/train_images.txt"
    elif resume:
        if not output_project.is_dir():
            raise FileNotFoundError(output_project)
        training_config = output_project / "protocol/runtime_training_config.yaml"
        manifest = output_project / "protocol/subset_manifest.jsonl"
        image_list = output_project / "protocol/train_images.txt"
        training_receipt = _resume_interrupted_training(
            static_config=static_config,
            runtime_config=training_config,
            output_project=output_project,
        )
    else:
        if output_project.exists():
            raise FileExistsError(output_project)
        training_config, manifest, image_list = _write_runtime_protocol(
            static_config=static_config,
            config_path=config_path,
            data_root=data_root,
            source_segment_yaml=source_segment_yaml,
            initial_checkpoint=initial_checkpoint,
            selected=selected,
            output_project=output_project,
        )
        training_receipt = train_arm(training_config, "segment")
    checkpoint = Path(training_receipt["artifacts"]["fixed_final_checkpoint"])
    model = YOLO(str(checkpoint))
    action_sets, timing = infer_actions(
        model,
        "segment",
        selected,
        static_config["evaluation"],
    )
    minimum_size = float(subset_config["minimum_actionable_gt_size_px"])
    thresholds = _thresholds(static_config["evaluation"])
    actionable_metrics: dict[str, Any] = {}
    all_weeds_metrics: dict[str, Any] = {}
    for method, actions in action_sets.items():
        selected_metric = select_validation_policy(
            _sized_actions(actions),
            selected,
            minimum_gt_size_px=minimum_size,
            confidence_thresholds=thresholds,
            prediction_size_thresholds=[0.0],
        )
        actionable_metrics[method] = selected_metric
        all_weeds_metrics[method] = evaluate_actions(
            actions,
            selected,
            float(selected_metric["policy"]["confidence_threshold"]),
        )
    gate_config = static_config["gate"]
    primary_method = str(gate_config["method"])
    if primary_method not in actionable_metrics:
        raise ValueError(f"Unknown gate method: {primary_method}")
    selected_metric = actionable_metrics[primary_method]
    gate_checks = {
        "precision": float(selected_metric["precision"])
        >= float(gate_config["minimum_precision"]),
        "recall": float(selected_metric["recall"])
        >= float(gate_config["minimum_recall"]),
        "f1": float(selected_metric["f1"]) >= float(gate_config["minimum_f1"]),
        "crop_collision": float(selected_metric["crop_collision_rate_per_attempt"])
        <= float(gate_config["maximum_crop_collision_rate_per_attempt"]),
    }
    plot_counts = Counter(metadata[item.sample_id]["plot_group"] for item in selected)
    date_counts = Counter(metadata[item.sample_id]["capture_date"] for item in selected)
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "protocol": static_config["protocol"],
        "status": "capacity_gate_passed" if all(gate_checks.values()) else "capacity_gate_failed",
        "interpretation": "same-image fit capacity only; no generalisation or field-success claim",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "locked_initial_checkpoint": str(initial_checkpoint),
        "locked_initial_checkpoint_sha256": sha256(initial_checkpoint),
        "trained_checkpoint": str(checkpoint),
        "trained_checkpoint_sha256": sha256(checkpoint),
        "subset": {
            "images": len(selected),
            "plot_counts": dict(sorted(plot_counts.items())),
            "capture_date_counts": dict(sorted(date_counts.items())),
            "eligible_weeds_all_sizes": sum(len(item.weed_sizes) for item in selected),
            "actionable_weeds": sum(
                float(size) >= minimum_size
                for item in selected
                for size in item.weed_sizes.values()
            ),
            "minimum_actionable_gt_size_px": minimum_size,
            "manifest": str(manifest),
            "manifest_sha256": sha256(manifest),
            "image_list_sha256": sha256(image_list),
        },
        "training": training_receipt,
        "same_set_actionable_metric": selected_metric,
        "same_set_actionable_metrics_by_method": actionable_metrics,
        "same_set_all_weed_metrics_at_method_threshold": all_weeds_metrics,
        "inference_timing": timing,
        "gate": {"requirements": gate_config, "checks": gate_checks},
        "claims": static_config["claims"],
    }
    metrics_path = output_project / "capacity_gate_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    release_cuda(model)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/phenobench_segment_overfit_gate_v1.yaml"),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the exact interrupted checkpoint, then evaluate it",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Evaluate the completed locked checkpoint without training",
    )
    arguments = parser.parse_args()
    metrics = run(
        arguments.config,
        resume=arguments.resume,
        evaluate_only=arguments.evaluate_only,
    )
    print(json.dumps({
        "status": metrics["status"],
        "same_set_actionable_metric": metrics["same_set_actionable_metric"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
