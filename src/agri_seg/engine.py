"""Training, calibration, evaluation, and checkpoint lifecycle."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
import yaml
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

from .constants import CROP, IGNORE, WEED
from .data import (
    DomainBalancedSampler,
    EvalTransform,
    FixedCropTransform,
    ManifestDataset,
    TrainTransform,
    padded_collate,
)
from .losses import SafetyAwareLoss
from .manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    read_manifest,
)
from .metrics import (
    SafetyCounts,
    confusion_matrix,
    metrics_from_confusion,
)
from .models import ModelConfig, build_model, trainable_parameter_count
from .safety import SafetyPolicy
from .safety import apply_safety_policy, dilate


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return config


def set_reproducibility(seed: int, deterministic: bool = False) -> None:
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(deterministic, warn_only=False)
    torch.backends.cudnn.deterministic = deterministic
    torch.backends.cudnn.benchmark = not deterministic


def configure_cache(config: Mapping[str, Any]) -> None:
    cache_root = config.get("cache_root")
    if not cache_root:
        return
    root = Path(str(cache_root)).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(root / "huggingface"))
    os.environ.setdefault("HF_HUB_CACHE", str(root / "huggingface/hub"))
    os.environ.setdefault("TORCH_HOME", str(root / "torch"))


def source_tree_sha256() -> str:
    digest = hashlib.sha256()
    package_root = Path(__file__).resolve().parent
    for path in sorted(package_root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _checkpoint_code_provenance(
    checkpoint: Mapping[str, Any],
) -> dict[str, object]:
    metadata = checkpoint.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RuntimeError(
            "Checkpoint has no provenance metadata and cannot be evaluated safely"
        )
    stored = metadata.get("source_tree_sha256")
    current = source_tree_sha256()
    if not isinstance(stored, str):
        raise RuntimeError("Checkpoint has no source_tree_sha256 provenance")
    matches = stored == current
    if not matches:
        raise RuntimeError(
            "Checkpoint code provenance mismatch: the model forward/evaluation "
            "code changed after training. Retrain with the current source tree."
        )
    return {
        "checkpoint_source_tree_sha256": stored,
        "runtime_source_tree_sha256": current,
        "source_tree_match": matches,
    }


def _validation_selection_key(
    metrics: Mapping[str, Any],
) -> tuple[float, ...]:
    """Lexicographic, safety-first key used to select a training epoch."""
    selected = metrics["selected_operating_point"]
    constraint_met = bool(metrics["safety_constraint"]["met"])
    risk = float(selected["worst_domain_crop_spray_risk"])
    image_risk = selected["per_image_crop_spray_risk"]
    violation_rate = float(image_risk.get("violation_rate", 0.0))
    risk_p99 = float(image_risk.get("p99", 0.0))
    worst_recall = float(selected["worst_domain_safe_weed_recall"])
    macro_recall = float(selected["macro_domain_safe_weed_recall"])
    worst_weed_iou = float(metrics["worst_domain_weed_iou"])
    if not math.isfinite(worst_weed_iou):
        worst_weed_iou = -1.0
    if constraint_met:
        unknown_rate = float(selected["global"]["unknown_rate"])
        return (
            1.0,
            worst_recall,
            macro_recall,
            -violation_rate,
            -risk_p99,
            worst_weed_iou,
            -unknown_rate,
        )
    # If no point is safe, minimize aggregate and per-image crop damage before
    # considering recall. This prevents tail-unsafe epochs winning on averages.
    return (
        0.0,
        -risk,
        -violation_rate,
        -risk_p99,
        worst_recall,
        macro_recall,
        worst_weed_iou,
    )

def _model_revision(model: nn.Module) -> str:
    for module in model.modules():
        config = getattr(module, "config", None)
        revision = getattr(config, "_commit_hash", None)
        if revision:
            return str(revision)
    return "torchvision_or_local"


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _worker_seed(worker_id: int) -> None:
    seed = torch.initial_seed() % (2**32)
    random.seed(seed + worker_id)
    np.random.seed(seed + worker_id)


def _model_config(config: Mapping[str, Any]) -> ModelConfig:
    return ModelConfig(**dict(config["model"]))


def _safety_policy(config: Mapping[str, Any]) -> SafetyPolicy:
    return SafetyPolicy(**dict(config.get("safety", {})))


def _records_for(
    records: Sequence[SampleRecord],
    split: str,
    commercial_only: bool,
    limit: int | None = None,
) -> list[SampleRecord]:
    selected = [
        record
        for record in records
        if record.split == split
        and (not commercial_only or record.commercial_allowed)
    ]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise ValueError(
            f"No records for split={split!r}, commercial_only={commercial_only}"
        )
    return selected


def create_loaders(
    config: Mapping[str, Any],
) -> tuple[
    DataLoader[dict[str, object]],
    DataLoader[dict[str, object]],
    DomainBalancedSampler,
]:
    data_root = config["data_root"]
    records = read_manifest(config["manifest"])
    train_cfg = config["training"]
    commercial_only = bool(config.get("commercial_only", True))
    train_records = _records_for(
        records,
        str(train_cfg.get("train_split", "train")),
        commercial_only,
        train_cfg.get("limit_train_samples"),
    )
    val_records = _records_for(
        records,
        str(train_cfg.get("val_split", "val")),
        commercial_only,
        train_cfg.get("limit_val_samples"),
    )
    crop_size = int(train_cfg.get("crop_size", 512))
    if train_cfg.get("augment", True):
        train_transform = TrainTransform(
            crop_size=crop_size,
            scale_min=float(train_cfg.get("scale_min", 0.65)),
            scale_max=float(train_cfg.get("scale_max", 1.6)),
        )
    else:
        train_transform = FixedCropTransform(crop_size)
    train_dataset = ManifestDataset(
        train_records, data_root, train_transform, verify_files=True
    )
    val_transform = (
        FixedCropTransform(crop_size)
        if bool(train_cfg.get("eval_fixed_crop", False))
        else EvalTransform()
    )
    val_dataset = ManifestDataset(
        val_records, data_root, val_transform, verify_files=True
    )
    epoch_samples = int(train_cfg.get("samples_per_epoch", len(train_records)))
    sampler = DomainBalancedSampler(
        train_records,
        num_samples=epoch_samples,
        seed=int(config["seed"]),
        dataset_weights=train_cfg.get("dataset_weights"),
    )
    generator = torch.Generator().manual_seed(int(config["seed"]))
    workers = int(train_cfg.get("workers", 8))
    train_loader = DataLoader(
        train_dataset,
        batch_size=int(train_cfg.get("batch_size", 4)),
        sampler=sampler,
        num_workers=workers,
        pin_memory=True,
        persistent_workers=workers > 0,
        worker_init_fn=_worker_seed,
        generator=generator,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=int(train_cfg.get("eval_batch_size", 1)),
        shuffle=False,
        num_workers=max(1, workers // 2) if workers else 0,
        pin_memory=True,
        persistent_workers=workers > 0,
        collate_fn=padded_collate,
    )
    return train_loader, val_loader, sampler


def _optimizer(
    model: nn.Module, learning_rate: float, backbone_multiplier: float, weight_decay: float
) -> AdamW:
    backbone: list[nn.Parameter] = []
    task: list[nn.Parameter] = []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if "backbone" in name or ".segformer." in name:
            backbone.append(parameter)
        else:
            task.append(parameter)
    groups: list[dict[str, object]] = []
    if backbone:
        groups.append({"params": backbone, "lr": learning_rate * backbone_multiplier})
    if task:
        groups.append({"params": task, "lr": learning_rate})
    if not groups:
        raise ValueError("Model has no trainable parameters")
    return AdamW(groups, lr=learning_rate, weight_decay=weight_decay)


def _scheduler(
    optimizer: AdamW, total_steps: int, warmup_steps: int
) -> LambdaLR:
    def multiplier(step: int) -> float:
        if step < warmup_steps:
            return max(1e-3, step / max(1, warmup_steps))
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))

    return LambdaLR(optimizer, multiplier)


def _set_frozen_modules_to_eval(model: nn.Module) -> None:
    """Prevent dropout/stochastic-depth drift in completely frozen submodules."""
    for module in model.modules():
        parameters = list(module.parameters())
        if parameters and not any(parameter.requires_grad for parameter in parameters):
            module.eval()


@dataclass
class _ComponentCounts:
    components: int = 0
    detected_at_50_percent: int = 0
    ground_truth_pixels: int = 0
    detected_pixels: int = 0

    def update(self, areas: np.ndarray, hits: np.ndarray) -> None:
        self.components += int(len(areas))
        self.detected_at_50_percent += int(
            np.count_nonzero(hits >= 0.5 * areas)
        )
        self.ground_truth_pixels += int(areas.sum())
        self.detected_pixels += int(hits.sum())

    def compute(self) -> dict[str, float | int]:
        return {
            "components": self.components,
            "component_detection_recall_at_50_percent_coverage": (
                self.detected_at_50_percent / max(1, self.components)
            ),
            "ground_truth_pixels": self.ground_truth_pixels,
            "pixel_recall_within_components": (
                self.detected_pixels / max(1, self.ground_truth_pixels)
            ),
        }


class EvaluationAccumulator:
    def __init__(
        self,
        base_policy: SafetyPolicy,
        thresholds: Sequence[float],
        max_crop_spray_risk: float,
        dilation_sensitivity_radii: Sequence[int] = (),
        component_metrics: bool = False,
        calibrate_by_crop_id: bool = True,
        max_per_image_crop_spray_risk_p99: float | None = None,
        max_crop_spray_risk_violation_rate: float | None = None,
    ) -> None:
        self.base_policy = base_policy
        self.base_policy.validate()
        self.thresholds = list(dict.fromkeys(float(value) for value in thresholds))
        if not self.thresholds:
            raise ValueError("At least one weed threshold is required")
        if any(not 0.0 <= value <= 1.0 for value in self.thresholds):
            raise ValueError("Weed thresholds must be in [0, 1]")
        self.max_crop_spray_risk = float(max_crop_spray_risk)
        if not 0.0 <= self.max_crop_spray_risk <= 1.0:
            raise ValueError("max_crop_spray_risk must be in [0, 1]")
        self.max_per_image_crop_spray_risk_p99 = float(
            1.0
            if max_per_image_crop_spray_risk_p99 is None
            else max_per_image_crop_spray_risk_p99
        )
        self.max_crop_spray_risk_violation_rate = float(
            1.0
            if max_crop_spray_risk_violation_rate is None
            else max_crop_spray_risk_violation_rate
        )
        if not 0.0 <= self.max_per_image_crop_spray_risk_p99 <= 1.0:
            raise ValueError(
                "max_per_image_crop_spray_risk_p99 must be in [0, 1]"
            )
        if not 0.0 <= self.max_crop_spray_risk_violation_rate <= 1.0:
            raise ValueError(
                "max_crop_spray_risk_violation_rate must be in [0, 1]"
            )
        self.calibrate_by_crop_id = bool(calibrate_by_crop_id)
        self.fixed_crop_policy = bool(base_policy.weed_threshold_by_crop_id)
        if self.fixed_crop_policy and len(self.thresholds) != 1:
            raise ValueError(
                "A frozen crop-ID policy must be evaluated as one operating point"
            )
        self.dilation_sensitivity_radii = sorted(
            {int(radius) for radius in dilation_sensitivity_radii}
        )
        if any(radius < 0 for radius in self.dilation_sensitivity_radii):
            raise ValueError("Dilation sensitivity radii cannot be negative")
        self.component_metrics = component_metrics
        self.confusion = torch.zeros((3, 3), dtype=torch.int64)
        self.domain_confusion: dict[str, torch.Tensor] = defaultdict(
            lambda: torch.zeros((3, 3), dtype=torch.int64)
        )
        self.counts = {threshold: SafetyCounts() for threshold in self.thresholds}
        self.domain_counts: dict[str, dict[float, SafetyCounts]] = defaultdict(
            lambda: {
                threshold: SafetyCounts() for threshold in self.thresholds
            }
        )
        self.crop_counts: dict[int, dict[float, SafetyCounts]] = defaultdict(
            lambda: {
                threshold: SafetyCounts() for threshold in self.thresholds
            }
        )
        self.crop_domain_counts: dict[
            int, dict[str, dict[float, SafetyCounts]]
        ] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    threshold: SafetyCounts() for threshold in self.thresholds
                }
            )
        )
        self.strata_confusion: dict[
            str, dict[str, torch.Tensor]
        ] = defaultdict(
            lambda: defaultdict(
                lambda: torch.zeros((3, 3), dtype=torch.int64)
            )
        )
        self.strata_counts: dict[
            str, dict[str, dict[float, SafetyCounts]]
        ] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    threshold: SafetyCounts()
                    for threshold in self.thresholds
                }
            )
        )
        self.crop_strata_counts: dict[
            int, dict[str, dict[str, dict[float, SafetyCounts]]]
        ] = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: {
                        threshold: SafetyCounts()
                        for threshold in self.thresholds
                    }
                )
            )
        )
        self.image_crop_spray_risks = {
            threshold: [] for threshold in self.thresholds
        }
        self.image_safe_weed_recalls = {
            threshold: [] for threshold in self.thresholds
        }
        self.crop_image_crop_spray_risks: dict[
            int, dict[float, list[float]]
        ] = defaultdict(
            lambda: {threshold: [] for threshold in self.thresholds}
        )
        self.crop_image_safe_weed_recalls: dict[
            int, dict[float, list[float]]
        ] = defaultdict(
            lambda: {threshold: [] for threshold in self.thresholds}
        )
        self.dilation_counts = {
            radius: {
                threshold: SafetyCounts() for threshold in self.thresholds
            }
            for radius in self.dilation_sensitivity_radii
        }
        self.dilation_domain_counts = {
            radius: defaultdict(
                lambda: {
                    threshold: SafetyCounts()
                    for threshold in self.thresholds
                }
            )
            for radius in self.dilation_sensitivity_radii
        }
        self.dilation_crop_counts = {
            radius: defaultdict(
                lambda: {
                    threshold: SafetyCounts()
                    for threshold in self.thresholds
                }
            )
            for radius in self.dilation_sensitivity_radii
        }
        self.dilation_crop_domain_counts = {
            radius: defaultdict(
                lambda: defaultdict(
                    lambda: {
                        threshold: SafetyCounts()
                        for threshold in self.thresholds
                    }
                )
            )
            for radius in self.dilation_sensitivity_radii
        }
        bins = ("small", "medium", "large")
        self.semantic_component_counts = {
            name: _ComponentCounts() for name in bins
        }
        self.safe_component_counts = {
            threshold: {name: _ComponentCounts() for name in bins}
            for threshold in self.thresholds
        }
        self.crop_safe_component_counts: dict[
            int, dict[float, dict[str, _ComponentCounts]]
        ] = defaultdict(
            lambda: {
                threshold: {name: _ComponentCounts() for name in bins}
                for threshold in self.thresholds
            }
        )

    @staticmethod
    def _add_safety_counts(
        destination: SafetyCounts, source: SafetyCounts
    ) -> None:
        for field, value in asdict(source).items():
            setattr(destination, field, getattr(destination, field) + int(value))

    @classmethod
    def _sum_safety_counts(
        cls, sources: Iterable[SafetyCounts]
    ) -> SafetyCounts:
        destination = SafetyCounts()
        for source in sources:
            cls._add_safety_counts(destination, source)
        return destination

    @staticmethod
    def _add_component_counts(
        destination: _ComponentCounts, source: _ComponentCounts
    ) -> None:
        destination.components += source.components
        destination.detected_at_50_percent += source.detected_at_50_percent
        destination.ground_truth_pixels += source.ground_truth_pixels
        destination.detected_pixels += source.detected_pixels

    @staticmethod
    def _update_component_bins(
        destinations: Mapping[str, _ComponentCounts],
        labels: np.ndarray,
        count: int,
        detected: np.ndarray,
    ) -> None:
        if count == 0:
            return
        areas = np.bincount(labels.reshape(-1), minlength=count + 1)[1:]
        hits = np.bincount(
            labels.reshape(-1),
            weights=detected.reshape(-1).astype(np.uint8),
            minlength=count + 1,
        )[1:]
        fractions = areas / labels.size
        selections = {
            "small": fractions <= 1e-4,
            "medium": (fractions > 1e-4) & (fractions <= 1e-3),
            "large": fractions > 1e-3,
        }
        for name, selection in selections.items():
            destinations[name].update(areas[selection], hits[selection])

    def _effective_threshold(self, crop_id: int) -> float:
        configured = {
            int(key): float(value)
            for key, value in self.base_policy.weed_threshold_by_crop_id.items()
        }
        fallback = (
            float(self.base_policy.unknown_crop_weed_threshold)
            if self.base_policy.unknown_crop_weed_threshold is not None
            else float(self.base_policy.weed_threshold)
        )
        return configured.get(crop_id, fallback)

    def update(
        self,
        probabilities: torch.Tensor,
        target: torch.Tensor,
        domain: str,
        strata: Mapping[str, str] | None = None,
        crop_id: int | None = None,
    ) -> None:
        probabilities = probabilities.detach()
        if probabilities.shape[0] != 1 or target.shape[0] != 1:
            raise ValueError(
                "EvaluationAccumulator.update expects one unpadded image"
            )
        crop_id_value = -1 if crop_id is None else int(crop_id)
        all_strata = dict(strata or {})
        all_strata["target_crop_id"] = str(crop_id_value)
        target_cpu = target.detach().cpu()
        matrix = confusion_matrix(
            probabilities.argmax(dim=1).cpu(), target_cpu
        )
        self.confusion += matrix
        self.domain_confusion[domain] += matrix
        for dimension, value in all_strata.items():
            self.strata_confusion[dimension][value] += matrix
        target_device = target.to(probabilities.device, non_blocking=True)
        valid = target_device != IGNORE
        crop = target_device == CROP
        weed = target_device == WEED
        crop_id_tensor = torch.tensor(
            [crop_id_value], dtype=torch.long, device=probabilities.device
        )
        shared = apply_safety_policy(
            probabilities,
            self.base_policy,
            crop_id_tensor if self.fixed_crop_policy else None,
        )
        weed_dominant = probabilities[:, WEED] > probabilities[:, CROP]
        if self.fixed_crop_policy:
            evaluated_thresholds = [self._effective_threshold(crop_id_value)]
        else:
            evaluated_thresholds = self.thresholds
        threshold_tensor = torch.tensor(
            evaluated_thresholds,
            dtype=probabilities.dtype,
            device=probabilities.device,
        )[:, None, None, None]
        weed_candidate = (
            probabilities[:, WEED].unsqueeze(0) >= threshold_tensor
        ) & weed_dominant.unsqueeze(0)
        raw_weed = weed_candidate & ~shared["unknown"].unsqueeze(0)
        safe_weed = raw_weed & ~shared["crop_guard"].unsqueeze(0)
        crop_stack = crop.unsqueeze(0)
        weed_stack = weed.unsqueeze(0)
        valid_stack = valid.unsqueeze(0)
        varying = torch.stack(
            (
                (raw_weed & crop_stack).sum(dim=(1, 2, 3)),
                (raw_weed & weed_stack).sum(dim=(1, 2, 3)),
                (safe_weed & crop_stack).sum(dim=(1, 2, 3)),
                (safe_weed & weed_stack).sum(dim=(1, 2, 3)),
                (safe_weed & valid_stack).sum(dim=(1, 2, 3)),
            ),
            dim=1,
        ).cpu().tolist()
        base = {
            "crop_pixels": int(crop.sum()),
            "weed_pixels": int(weed.sum()),
            "vegetation_pixels": int((crop | weed).sum()),
            "valid_pixels": int(valid.sum()),
            "unknown_pixels": int((shared["unknown"] & valid).sum()),
            "unknown_vegetation_pixels": int(
                (shared["unknown"] & (crop | weed)).sum()
            ),
        }
        varying_fields = (
            "crop_as_raw_weed",
            "weed_as_raw_weed",
            "crop_as_safe_weed",
            "weed_as_safe_weed",
            "safe_weed_pixels",
        )
        for index, storage_threshold in enumerate(self.thresholds):
            if base["crop_pixels"] > 0:
                risk = int(varying[index][2]) / base["crop_pixels"]
                self.image_crop_spray_risks[storage_threshold].append(risk)
                self.crop_image_crop_spray_risks[crop_id_value][
                    storage_threshold
                ].append(risk)
            if base["weed_pixels"] > 0:
                recall = int(varying[index][3]) / base["weed_pixels"]
                self.image_safe_weed_recalls[storage_threshold].append(recall)
                self.crop_image_safe_weed_recalls[crop_id_value][
                    storage_threshold
                ].append(recall)
            destinations = [
                self.counts[storage_threshold],
                self.domain_counts[domain][storage_threshold],
                self.crop_counts[crop_id_value][storage_threshold],
                self.crop_domain_counts[crop_id_value][domain][storage_threshold],
            ]
            destinations.extend(
                self.strata_counts[dimension][value][storage_threshold]
                for dimension, value in all_strata.items()
            )
            destinations.extend(
                self.crop_strata_counts[crop_id_value][dimension][value][
                    storage_threshold
                ]
                for dimension, value in all_strata.items()
            )
            for destination in destinations:
                for field, value in base.items():
                    setattr(
                        destination,
                        field,
                        getattr(destination, field) + value,
                    )
                for field, value in zip(varying_fields, varying[index]):
                    setattr(
                        destination,
                        field,
                        getattr(destination, field) + int(value),
                    )

        crop_candidate = probabilities[:, CROP] >= self.base_policy.crop_threshold
        for radius in self.dilation_sensitivity_radii:
            guard = dilate(crop_candidate, radius)
            sensitivity_safe = raw_weed & ~guard.unsqueeze(0)
            sensitivity_varying = torch.stack(
                (
                    (raw_weed & crop_stack).sum(dim=(1, 2, 3)),
                    (raw_weed & weed_stack).sum(dim=(1, 2, 3)),
                    (sensitivity_safe & crop_stack).sum(dim=(1, 2, 3)),
                    (sensitivity_safe & weed_stack).sum(dim=(1, 2, 3)),
                    (sensitivity_safe & valid_stack).sum(dim=(1, 2, 3)),
                ),
                dim=1,
            ).cpu().tolist()
            for index, storage_threshold in enumerate(self.thresholds):
                for destination in (
                    self.dilation_counts[radius][storage_threshold],
                    self.dilation_domain_counts[radius][domain][storage_threshold],
                    self.dilation_crop_counts[radius][crop_id_value][
                        storage_threshold
                    ],
                    self.dilation_crop_domain_counts[radius][crop_id_value][domain][
                        storage_threshold
                    ],
                ):
                    for field, value in base.items():
                        setattr(
                            destination,
                            field,
                            getattr(destination, field) + value,
                        )
                    for field, value in zip(
                        varying_fields, sensitivity_varying[index]
                    ):
                        setattr(
                            destination,
                            field,
                            getattr(destination, field) + int(value),
                        )

        if self.component_metrics:
            from scipy import ndimage

            semantic_weed = probabilities.argmax(dim=1).cpu().numpy() == WEED
            target_weed = target_cpu.numpy() == WEED
            safe_cpu = safe_weed.cpu().numpy()
            for batch_index in range(target_weed.shape[0]):
                labels, count = ndimage.label(
                    target_weed[batch_index],
                    structure=np.ones((3, 3), dtype=np.uint8),
                )
                self._update_component_bins(
                    self.semantic_component_counts,
                    labels,
                    int(count),
                    semantic_weed[batch_index],
                )
                for threshold_index, storage_threshold in enumerate(self.thresholds):
                    self._update_component_bins(
                        self.safe_component_counts[storage_threshold],
                        labels,
                        int(count),
                        safe_cpu[threshold_index, batch_index],
                    )
                    self._update_component_bins(
                        self.crop_safe_component_counts[crop_id_value][
                            storage_threshold
                        ],
                        labels,
                        int(count),
                        safe_cpu[threshold_index, batch_index],
                    )

    def compute(self) -> dict[str, object]:
        def distribution(
            values: Sequence[float], violation_limit: float | None = None
        ) -> dict[str, float | int]:
            array = np.asarray(values, dtype=np.float64)
            if not len(array):
                return {"images": 0}
            result: dict[str, float | int] = {
                "images": int(len(array)),
                "mean": float(array.mean()),
                "p50": float(np.quantile(array, 0.50)),
                "p95": float(np.quantile(array, 0.95)),
                "p99": float(np.quantile(array, 0.99)),
                "max": float(array.max()),
            }
            if violation_limit is not None:
                result["violation_rate"] = float(
                    (array > violation_limit).mean()
                )
            return result

        def candidate(
            reported_threshold: float,
            global_counts: SafetyCounts,
            per_domain_counts: Mapping[str, SafetyCounts],
            image_risks: Sequence[float],
            image_recalls: Sequence[float],
        ) -> dict[str, object]:
            global_metrics = global_counts.compute()
            per_domain = {
                domain: counts.compute()
                for domain, counts in sorted(per_domain_counts.items())
            }
            worst_risk = max(
                (
                    float(values["crop_spray_risk"])
                    for values in per_domain.values()
                ),
                default=0.0,
            )
            recall_values = [
                float(values["safe_weed_recall"])
                for values in per_domain.values()
                if int(values["weed_pixels"]) > 0
            ]
            return {
                "weed_threshold": float(reported_threshold),
                "global": global_metrics,
                "per_domain": per_domain,
                "worst_domain_crop_spray_risk": worst_risk,
                "macro_domain_safe_weed_recall": (
                    sum(recall_values) / max(1, len(recall_values))
                ),
                "worst_domain_safe_weed_recall": min(
                    recall_values, default=0.0
                ),
                "per_image_crop_spray_risk": distribution(
                    image_risks, self.max_crop_spray_risk
                ),
                "per_image_safe_weed_recall": distribution(image_recalls),
            }

        def point_constraints_met(point: Mapping[str, object]) -> bool:
            image_risk = point["per_image_crop_spray_risk"]
            tolerance = 1e-12
            return (
                float(point["worst_domain_crop_spray_risk"])
                <= self.max_crop_spray_risk + tolerance
                and float(image_risk.get("p99", 0.0))
                <= self.max_per_image_crop_spray_risk_p99 + tolerance
                and float(image_risk.get("violation_rate", 0.0))
                <= self.max_crop_spray_risk_violation_rate + tolerance
            )

        def constraint_deficits(
            point: Mapping[str, object],
        ) -> tuple[float, ...]:
            image_risk = point["per_image_crop_spray_risk"]
            aggregate = float(point["worst_domain_crop_spray_risk"])
            p99_risk = float(image_risk.get("p99", 0.0))
            violation_rate = float(image_risk.get("violation_rate", 0.0))
            return (
                max(0.0, aggregate - self.max_crop_spray_risk),
                max(
                    0.0,
                    violation_rate
                    - self.max_crop_spray_risk_violation_rate,
                ),
                max(
                    0.0,
                    p99_risk - self.max_per_image_crop_spray_risk_p99,
                ),
                aggregate,
                violation_rate,
                p99_risk,
            )

        def select_curve(
            curve: Sequence[dict[str, object]],
        ) -> tuple[dict[str, object], bool]:
            feasible = [point for point in curve if point_constraints_met(point)]
            if feasible:
                return (
                    max(
                        feasible,
                        key=lambda point: (
                            float(point["worst_domain_safe_weed_recall"]),
                            float(point["macro_domain_safe_weed_recall"]),
                            -float(
                                point["per_image_crop_spray_risk"].get(
                                    "violation_rate", 0.0
                                )
                            ),
                            -float(
                                point["per_image_crop_spray_risk"].get(
                                    "p99", 0.0
                                )
                            ),
                            -float(point["global"]["unknown_rate"]),
                            float(point["weed_threshold"]),
                        ),
                    ),
                    True,
                )
            return min(curve, key=constraint_deficits), False

        domains = sorted(self.domain_counts)
        scalar_candidates = [
            candidate(
                threshold,
                self.counts[threshold],
                {
                    domain: self.domain_counts[domain][threshold]
                    for domain in domains
                },
                self.image_crop_spray_risks[threshold],
                self.image_safe_weed_recalls[threshold],
            )
            for threshold in self.thresholds
        ]
        crop_curves: dict[str, list[dict[str, object]]] = {}
        crop_points: dict[str, dict[str, object]] = {}
        storage_threshold_by_crop_id: dict[int, float] = {}
        reported_threshold_by_crop_id: dict[int, float] = {}

        if self.fixed_crop_policy:
            storage_threshold = self.thresholds[0]
            for crop_id in sorted(self.crop_counts):
                storage_threshold_by_crop_id[crop_id] = storage_threshold
                reported_threshold_by_crop_id[crop_id] = self._effective_threshold(
                    crop_id
                )
            calibration_mode = "frozen_source_crop_id_policy"
        elif self.calibrate_by_crop_id:
            all_crop_constraints_met = True
            for crop_id in sorted(self.crop_counts):
                crop_domains = sorted(self.crop_domain_counts[crop_id])
                curve = [
                    candidate(
                        threshold,
                        self.crop_counts[crop_id][threshold],
                        {
                            domain: self.crop_domain_counts[crop_id][domain][
                                threshold
                            ]
                            for domain in crop_domains
                        },
                        self.crop_image_crop_spray_risks[crop_id][threshold],
                        self.crop_image_safe_weed_recalls[crop_id][threshold],
                    )
                    for threshold in self.thresholds
                ]
                selected_crop, crop_met = select_curve(curve)
                selected_threshold = float(selected_crop["weed_threshold"])
                storage_threshold_by_crop_id[crop_id] = selected_threshold
                reported_threshold_by_crop_id[crop_id] = selected_threshold
                crop_curves[str(crop_id)] = curve
                crop_points[str(crop_id)] = selected_crop
                all_crop_constraints_met = all_crop_constraints_met and crop_met
            calibration_mode = "source_validation_per_crop_id"
        else:
            selected_scalar, scalar_met = select_curve(scalar_candidates)
            selected_threshold = float(selected_scalar["weed_threshold"])
            for crop_id in sorted(self.crop_counts):
                storage_threshold_by_crop_id[crop_id] = selected_threshold
                reported_threshold_by_crop_id[crop_id] = selected_threshold
            all_crop_constraints_met = scalar_met
            calibration_mode = "source_validation_global"

        fallback_threshold = (
            float(self.base_policy.unknown_crop_weed_threshold)
            if self.fixed_crop_policy
            and self.base_policy.unknown_crop_weed_threshold is not None
            else max(reported_threshold_by_crop_id.values())
        )
        configured_thresholds = {
            int(key): float(value)
            for key, value in self.base_policy.weed_threshold_by_crop_id.items()
        }
        if self.fixed_crop_policy:
            policy_thresholds = configured_thresholds
        else:
            policy_thresholds = reported_threshold_by_crop_id

        selected_global_counts = self._sum_safety_counts(
            self.crop_counts[crop_id][storage_threshold]
            for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
        )
        selected_domain_counts: dict[str, SafetyCounts] = {}
        for domain in domains:
            selected_domain_counts[domain] = self._sum_safety_counts(
                self.crop_domain_counts[crop_id][domain][storage_threshold]
                for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
                if domain in self.crop_domain_counts[crop_id]
            )
        selected_image_risks = [
            value
            for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
            for value in self.crop_image_crop_spray_risks[crop_id][
                storage_threshold
            ]
        ]
        selected_image_recalls = [
            value
            for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
            for value in self.crop_image_safe_weed_recalls[crop_id][
                storage_threshold
            ]
        ]
        selected = candidate(
            fallback_threshold,
            selected_global_counts,
            selected_domain_counts,
            selected_image_risks,
            selected_image_recalls,
        )
        selected["weed_threshold_by_crop_id"] = {
            str(crop_id): threshold
            for crop_id, threshold in sorted(policy_thresholds.items())
        }
        selected["unknown_crop_weed_threshold"] = fallback_threshold
        selected["calibration_mode"] = calibration_mode
        selected["crop_id_operating_points"] = crop_points
        constraint_met = point_constraints_met(selected)
        if not self.fixed_crop_policy and self.calibrate_by_crop_id:
            constraint_met = constraint_met and all_crop_constraints_met
        elif not self.fixed_crop_policy and not self.calibrate_by_crop_id:
            constraint_met = constraint_met and all_crop_constraints_met

        overall = metrics_from_confusion(self.confusion)
        domain_metrics = {
            domain: metrics_from_confusion(self.domain_confusion[domain])
            for domain in sorted(self.domain_confusion)
        }
        weed_ious = [
            float(values["iou"]["other_vegetation"])
            for values in domain_metrics.values()
            if math.isfinite(float(values["iou"]["other_vegetation"]))
        ]

        strata_output: dict[str, dict[str, dict[str, object]]] = {}
        for dimension, values in sorted(self.strata_confusion.items()):
            strata_output[dimension] = {}
            for value in sorted(values):
                safety_counts = self._sum_safety_counts(
                    self.crop_strata_counts[crop_id][dimension][value][
                        storage_threshold
                    ]
                    for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
                    if value in self.crop_strata_counts[crop_id][dimension]
                )
                strata_output[dimension][value] = {
                    **metrics_from_confusion(
                        self.strata_confusion[dimension][value]
                    ),
                    "safety": safety_counts.compute(),
                }

        dilation_sensitivity: list[dict[str, object]] = []
        for radius in self.dilation_sensitivity_radii:
            global_safety_counts = self._sum_safety_counts(
                self.dilation_crop_counts[radius][crop_id][storage_threshold]
                for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
            )
            domain_safety_counts = {
                domain: self._sum_safety_counts(
                    self.dilation_crop_domain_counts[radius][crop_id][domain][
                        storage_threshold
                    ]
                    for crop_id, storage_threshold in storage_threshold_by_crop_id.items()
                    if domain
                    in self.dilation_crop_domain_counts[radius][crop_id]
                )
                for domain in domains
            }
            domain_safety = {
                domain: counts.compute()
                for domain, counts in domain_safety_counts.items()
            }
            recall_values = [
                float(values["safe_weed_recall"])
                for values in domain_safety.values()
                if int(values["weed_pixels"]) > 0
            ]
            dilation_sensitivity.append(
                {
                    "crop_dilation_px": radius,
                    "global": global_safety_counts.compute(),
                    "worst_domain_crop_spray_risk": max(
                        (
                            float(values["crop_spray_risk"])
                            for values in domain_safety.values()
                        ),
                        default=0.0,
                    ),
                    "macro_domain_safe_weed_recall": (
                        sum(recall_values) / max(1, len(recall_values))
                    ),
                    "worst_domain_safe_weed_recall": min(
                        recall_values, default=0.0
                    ),
                }
            )

        component_output: dict[str, object] | None = None
        if self.component_metrics:
            selected_components = {
                name: _ComponentCounts() for name in ("small", "medium", "large")
            }
            for crop_id, storage_threshold in storage_threshold_by_crop_id.items():
                for name, source in self.crop_safe_component_counts[crop_id][
                    storage_threshold
                ].items():
                    self._add_component_counts(selected_components[name], source)
            component_output = {
                "size_bins_by_fraction_of_image": {
                    "small": "<=0.0001",
                    "medium": "(0.0001, 0.001]",
                    "large": ">0.001",
                },
                "semantic_argmax": {
                    name: counts.compute()
                    for name, counts in self.semantic_component_counts.items()
                },
                "safe_weed_at_selected_threshold": {
                    name: counts.compute()
                    for name, counts in selected_components.items()
                },
            }

        return {
            **overall,
            "domains": domain_metrics,
            "strata": strata_output,
            "worst_domain_weed_iou": min(weed_ious, default=float("nan")),
            "safety_constraint": {
                "max_crop_spray_risk": self.max_crop_spray_risk,
                "max_per_image_crop_spray_risk_p99": (
                    self.max_per_image_crop_spray_risk_p99
                ),
                "max_crop_spray_risk_violation_rate": (
                    self.max_crop_spray_risk_violation_rate
                ),
                "aggregate_met": (
                    float(selected["worst_domain_crop_spray_risk"])
                    <= self.max_crop_spray_risk + 1e-12
                ),
                "per_image_p99_met": (
                    float(
                        selected["per_image_crop_spray_risk"].get("p99", 0.0)
                    )
                    <= self.max_per_image_crop_spray_risk_p99 + 1e-12
                ),
                "per_image_violation_rate_met": (
                    float(
                        selected["per_image_crop_spray_risk"].get(
                            "violation_rate", 0.0
                        )
                    )
                    <= self.max_crop_spray_risk_violation_rate + 1e-12
                ),
                "met": constraint_met,
            },
            "selected_operating_point": selected,
            "threshold_curve": scalar_candidates,
            "crop_id_threshold_curves": crop_curves,
            "crop_dilation_sensitivity": dilation_sensitivity,
            "weed_component_metrics": component_output,
        }

def _tile_starts(length: int, tile_size: int, overlap: int) -> list[int]:
    if length <= tile_size:
        return [0]
    stride = tile_size - overlap
    starts = list(range(0, length - tile_size + 1, stride))
    if starts[-1] != length - tile_size:
        starts.append(length - tile_size)
    return starts


def predict_logits(
    model: nn.Module,
    images: torch.Tensor,
    crop_ids: torch.Tensor,
    use_amp: bool = True,
    tile_size: int | None = None,
    tile_overlap: int = 128,
    tile_trigger_pixels: int = 4_000_000,
) -> torch.Tensor:
    """Predict a padded batch, tiling large native images with overlap blending."""
    if tile_size is None or images.shape[-2] * images.shape[-1] <= tile_trigger_pixels:
        with torch.autocast(
            device_type=images.device.type,
            dtype=torch.float16,
            enabled=use_amp and images.device.type == "cuda",
        ):
            return model(images, crop_ids)
    if tile_size <= 0 or tile_overlap < 0 or tile_overlap >= tile_size:
        raise ValueError("Invalid evaluation tile_size/tile_overlap")

    outputs: list[torch.Tensor] = []
    for batch_index in range(images.shape[0]):
        sample = images[batch_index : batch_index + 1]
        crop_id = crop_ids[batch_index : batch_index + 1]
        height, width = sample.shape[-2:]
        y_starts = _tile_starts(height, tile_size, tile_overlap)
        x_starts = _tile_starts(width, tile_size, tile_overlap)
        logits_sum: torch.Tensor | None = None
        weight_sum = torch.zeros(
            (1, 1, height, width),
            dtype=torch.float32,
            device=sample.device,
        )
        weights: dict[tuple[int, int], torch.Tensor] = {}
        for top in y_starts:
            for left in x_starts:
                tile = sample[
                    :,
                    :,
                    top : min(top + tile_size, height),
                    left : min(left + tile_size, width),
                ]
                with torch.autocast(
                    device_type=sample.device.type,
                    dtype=torch.float16,
                    enabled=use_amp and sample.device.type == "cuda",
                ):
                    tile_logits = model(tile, crop_id)
                tile_logits = tile_logits.float()
                if logits_sum is None:
                    logits_sum = torch.zeros(
                        (1, tile_logits.shape[1], height, width),
                        dtype=torch.float32,
                        device=sample.device,
                    )
                tile_height, tile_width = tile.shape[-2:]
                key = (tile_height, tile_width)
                if key not in weights:
                    vertical = torch.hann_window(
                        tile_height,
                        periodic=False,
                        dtype=torch.float32,
                        device=sample.device,
                    ).clamp_min_(0.05)
                    horizontal = torch.hann_window(
                        tile_width,
                        periodic=False,
                        dtype=torch.float32,
                        device=sample.device,
                    ).clamp_min_(0.05)
                    weights[key] = (
                        vertical[:, None] * horizontal[None, :]
                    )[None, None]
                weight = weights[key]
                logits_sum[
                    :,
                    :,
                    top : top + tile_height,
                    left : left + tile_width,
                ] += tile_logits * weight
                weight_sum[
                    :,
                    :,
                    top : top + tile_height,
                    left : left + tile_width,
                ] += weight
        if logits_sum is None:
            raise RuntimeError("Tiled inference produced no tiles")
        outputs.append(logits_sum / weight_sum.clamp_min_(1e-6))
    return torch.cat(outputs, dim=0)


@torch.inference_mode()
def evaluate(
    model: nn.Module,
    loader: DataLoader[dict[str, object]],
    device: torch.device,
    policy: SafetyPolicy,
    thresholds: Sequence[float],
    max_crop_spray_risk: float,
    use_amp: bool = True,
    tile_size: int | None = None,
    tile_overlap: int = 128,
    tile_trigger_pixels: int = 4_000_000,
    dilation_sensitivity_radii: Sequence[int] = (),
    component_metrics: bool = False,
    calibrate_unknown_crop: bool = False,
    unknown_crop_id: int = 32,
    max_per_image_crop_spray_risk_p99: float | None = None,
    max_crop_spray_risk_violation_rate: float | None = None,
) -> dict[str, object]:
    model.eval()
    accumulator = EvaluationAccumulator(
        policy,
        thresholds,
        max_crop_spray_risk,
        dilation_sensitivity_radii,
        component_metrics,
        max_per_image_crop_spray_risk_p99=(
            max_per_image_crop_spray_risk_p99
        ),
        max_crop_spray_risk_violation_rate=(
            max_crop_spray_risk_violation_rate
        ),
    )
    unknown_accumulator = (
        EvaluationAccumulator(
            policy,
            thresholds,
            max_crop_spray_risk,
            calibrate_by_crop_id=False,
            max_per_image_crop_spray_risk_p99=(
                max_per_image_crop_spray_risk_p99
            ),
            max_crop_spray_risk_violation_rate=(
                max_crop_spray_risk_violation_rate
            ),
        )
        if calibrate_unknown_crop
        else None
    )
    uses_crop_conditioning = any(
        getattr(module, "crop_embedding", None) is not None
        for module in model.modules()
    )
    start = time.monotonic()
    image_count = 0
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
        logits = predict_logits(
            model,
            images,
            crop_ids,
            use_amp=use_amp,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_trigger_pixels=tile_trigger_pixels,
        )
        probabilities = logits.float().softmax(dim=1)
        unknown_probabilities = probabilities
        if unknown_accumulator is not None and uses_crop_conditioning:
            unknown_ids = torch.full_like(crop_ids, int(unknown_crop_id))
            unknown_logits = predict_logits(
                model,
                images,
                unknown_ids,
                use_amp=use_amp,
                tile_size=tile_size,
                tile_overlap=tile_overlap,
                tile_trigger_pixels=tile_trigger_pixels,
            )
            unknown_probabilities = unknown_logits.float().softmax(dim=1)
        for index, (height, width) in enumerate(batch["valid_size"]):
            # A robustness domain is a capture group, not merely a dataset name.
            domain = str(batch["group_id"][index])
            target = batch["mask"][index : index + 1, :height, :width]
            prediction = probabilities[
                index : index + 1, :, :height, :width
            ]
            strata = {
                "dataset": str(batch["dataset_id"][index]),
                "growth_stage": str(batch["growth_stage"][index]),
                "crop_species": str(batch["crop_species"][index]),
                "platform": str(batch["platform"][index]),
                "sensor": str(batch["sensor"][index]),
            }
            accumulator.update(
                prediction,
                target,
                domain,
                strata,
                crop_id=int(crop_ids[index].item()),
            )
            if unknown_accumulator is not None:
                unknown_prediction = unknown_probabilities[
                    index : index + 1, :, :height, :width
                ]
                unknown_accumulator.update(
                    unknown_prediction,
                    target,
                    domain,
                    strata,
                    crop_id=-1,
                )
            image_count += 1
    metrics = accumulator.compute()
    if unknown_accumulator is not None:
        unknown_metrics = unknown_accumulator.compute()
        known_selected = dict(metrics["selected_operating_point"])
        unknown_selected = unknown_metrics["selected_operating_point"]
        selected = metrics["selected_operating_point"]
        unknown_threshold = float(unknown_selected["weed_threshold"])
        selected["weed_threshold"] = unknown_threshold
        selected["unknown_crop_weed_threshold"] = unknown_threshold
        selected["calibration_mode"] = (
            "source_validation_per_crop_id_plus_unknown_embedding"
            if uses_crop_conditioning
            else "source_validation_per_crop_id_plus_crop_independent_fallback"
        )
        selected["known_crop_policy_worst_domain_crop_spray_risk"] = float(
            known_selected["worst_domain_crop_spray_risk"]
        )
        selected["known_crop_policy_worst_domain_safe_weed_recall"] = float(
            known_selected["worst_domain_safe_weed_recall"]
        )
        selected["unknown_crop_policy"] = unknown_selected
        selected["worst_domain_crop_spray_risk"] = max(
            float(known_selected["worst_domain_crop_spray_risk"]),
            float(unknown_selected["worst_domain_crop_spray_risk"]),
        )
        selected["worst_domain_safe_weed_recall"] = min(
            float(known_selected["worst_domain_safe_weed_recall"]),
            float(unknown_selected["worst_domain_safe_weed_recall"]),
        )
        selected["macro_domain_safe_weed_recall"] = min(
            float(known_selected["macro_domain_safe_weed_recall"]),
            float(unknown_selected["macro_domain_safe_weed_recall"]),
        )
        selected["per_image_crop_spray_risk_by_policy_mode"] = {
            "known_crop_ids": known_selected["per_image_crop_spray_risk"],
            "unknown_crop": unknown_selected["per_image_crop_spray_risk"],
        }
        known_p99 = float(
            known_selected["per_image_crop_spray_risk"].get("p99", 0.0)
        )
        unknown_p99 = float(
            unknown_selected["per_image_crop_spray_risk"].get("p99", 0.0)
        )
        if unknown_p99 > known_p99:
            selected["per_image_crop_spray_risk"] = unknown_selected[
                "per_image_crop_spray_risk"
            ]
        metrics["known_crop_id_calibration"] = {
            "selected_operating_point": known_selected,
            "safety_constraint": dict(metrics["safety_constraint"]),
        }
        metrics["unknown_crop_calibration"] = {
            "uses_unknown_model_embedding": uses_crop_conditioning,
            "selected_operating_point": unknown_selected,
            "threshold_curve": unknown_metrics["threshold_curve"],
            "safety_constraint": unknown_metrics["safety_constraint"],
        }
        metrics["safety_constraint"]["known_crop_ids_met"] = bool(
            metrics["safety_constraint"]["met"]
        )
        metrics["safety_constraint"]["unknown_crop_met"] = bool(
            unknown_metrics["safety_constraint"]["met"]
        )
        metrics["safety_constraint"]["met"] = bool(
            metrics["safety_constraint"]["known_crop_ids_met"]
            and metrics["safety_constraint"]["unknown_crop_met"]
        )
    elapsed = time.monotonic() - start
    metrics["runtime"] = {
        "images": image_count,
        "seconds": elapsed,
        "images_per_second": image_count / max(elapsed, 1e-9),
        "device": str(device),
        "unknown_crop_calibration_pass": calibrate_unknown_crop,
    }
    return metrics


def _atomic_torch_save(payload: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(dict(payload), temporary)
    temporary.replace(path)


def _write_json(payload: Mapping[str, object], path: Path) -> None:
    def json_safe(value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            json_safe(dict(payload)),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def train_from_config(config_path: str | Path) -> Path:
    config = load_config(config_path)
    configure_cache(config)
    seed = int(config.get("seed", 17))
    set_reproducibility(seed, bool(config.get("deterministic", False)))
    if not torch.cuda.is_available():
        raise RuntimeError("The benchmark training configuration requires CUDA")
    device = torch.device(str(config.get("device", "cuda")))
    train_cfg = config["training"]
    output_root = Path(config["output_root"]).expanduser()
    run_dir = output_root / str(config["experiment"]) / f"seed_{seed}"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(
            f"Refusing to overwrite non-empty training run: {run_dir}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(config, run_dir / "config.resolved.json")

    train_loader, val_loader, sampler = create_loaders(config)
    model = build_model(_model_config(config)).to(device)
    total_parameters, trainable_parameters = trainable_parameter_count(model)
    learning_rate = float(train_cfg.get("learning_rate", 3e-4))
    optimizer = _optimizer(
        model,
        learning_rate=learning_rate,
        backbone_multiplier=float(train_cfg.get("backbone_lr_multiplier", 0.1)),
        weight_decay=float(train_cfg.get("weight_decay", 0.05)),
    )
    accumulation = int(train_cfg.get("gradient_accumulation", 1))
    epochs = int(train_cfg.get("epochs", 30))
    optimizer_steps_per_epoch = math.ceil(len(train_loader) / accumulation)
    total_steps = max(1, optimizer_steps_per_epoch * epochs)
    scheduler = _scheduler(
        optimizer,
        total_steps,
        int(train_cfg.get("warmup_steps", max(10, total_steps // 20))),
    )
    loss_cfg = config.get("loss", {})
    criterion = SafetyAwareLoss(
        class_weights=tuple(loss_cfg.get("class_weights", (0.25, 1.5, 1.0))),
        dice_weight=float(loss_cfg.get("dice_weight", 0.5)),
        crop_safety_weight=float(loss_cfg.get("crop_safety_weight", 1.0)),
        crop_safety_tail_fraction=float(
            loss_cfg.get("crop_safety_tail_fraction", 1.0)
        ),
    ).to(device)
    scaler = torch.amp.GradScaler(
        "cuda", enabled=bool(train_cfg.get("amp", True))
    )
    thresholds = train_cfg.get(
        "weed_thresholds",
        [round(value, 2) for value in np.arange(0.5, 0.951, 0.05)],
    )
    policy = _safety_policy(config)
    max_risk = float(train_cfg.get("max_crop_spray_risk", 0.005))
    max_p99_risk = float(
        train_cfg.get("max_per_image_crop_spray_risk_p99", 1.0)
    )
    max_violation_rate = float(
        train_cfg.get("max_crop_spray_risk_violation_rate", 1.0)
    )
    metadata = {
        "total_parameters": total_parameters,
        "trainable_parameters": trainable_parameters,
        "manifest_sha256": manifest_sha256(config["manifest"]),
        "normalized_mask_tree_sha256": mask_tree_sha256(
            read_manifest(config["manifest"]), config["data_root"]
        ),
        "torch_version": torch.__version__,
        "torchvision_version": _package_version("torchvision"),
        "transformers_version": _package_version("transformers"),
        "cuda_version": torch.version.cuda,
        "device_name": torch.cuda.get_device_name(device),
        "model_revision": _model_revision(model),
        "source_tree_sha256": source_tree_sha256(),
    }
    _write_json(metadata, run_dir / "run_metadata.json")

    log_path = run_dir / "history.jsonl"
    best_key: tuple[float, ...] | None = None
    global_step = 0
    started = time.monotonic()
    for epoch in range(epochs):
        sampler.set_epoch(epoch)
        model.train()
        _set_frozen_modules_to_eval(model)
        optimizer.zero_grad(set_to_none=True)
        running: dict[str, float] = defaultdict(float)
        batches = 0
        epoch_started = time.monotonic()
        for batch_index, batch in enumerate(train_loader):
            images = batch["image"].to(device, non_blocking=True)
            masks = batch["mask"].to(device, non_blocking=True)
            crop_ids = batch["target_crop_id"].to(device, non_blocking=True)
            with torch.autocast(
                device_type="cuda",
                dtype=torch.float16,
                enabled=bool(train_cfg.get("amp", True)),
            ):
                logits = model(images, crop_ids)
                loss, components = criterion(logits, masks)
                scaled_loss = loss / accumulation
            scaler.scale(scaled_loss).backward()
            should_step = (
                (batch_index + 1) % accumulation == 0
                or batch_index + 1 == len(train_loader)
            )
            if should_step:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    float(train_cfg.get("gradient_clip", 1.0)),
                )
                previous_scale = scaler.get_scale()
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                # GradScaler skips optimizer.step on overflow; keep LR schedule aligned.
                if scaler.get_scale() >= previous_scale:
                    scheduler.step()
                    global_step += 1
            for name, value in components.items():
                running[name] += float(value)
            batches += 1

        validate_every = int(train_cfg.get("validate_every", 1))
        validate_now = (
            (epoch + 1) % validate_every == 0 or epoch + 1 == epochs
        )
        if not validate_now:
            epoch_log = {
                "epoch": epoch + 1,
                "global_step": global_step,
                "learning_rates": [
                    group["lr"] for group in optimizer.param_groups
                ],
                "train": {
                    name: value / max(1, batches)
                    for name, value in running.items()
                },
                "val": None,
                "epoch_seconds": time.monotonic() - epoch_started,
            }
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(epoch_log, sort_keys=True) + "\n")
            _atomic_torch_save(
                {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scheduler": scheduler.state_dict(),
                    "epoch": epoch + 1,
                    "global_step": global_step,
                    "config": config,
                    "metadata": metadata,
                    "validation": None,
                },
                run_dir / "last.pt",
            )
            continue

        val_metrics = evaluate(
            model,
            val_loader,
            device,
            policy,
            thresholds,
            max_risk,
            use_amp=bool(train_cfg.get("amp", True)),
            tile_size=train_cfg.get("eval_tile_size"),
            tile_overlap=int(train_cfg.get("eval_tile_overlap", 128)),
            tile_trigger_pixels=int(
                train_cfg.get("eval_tile_trigger_pixels", 4_000_000)
            ),
            calibrate_unknown_crop=bool(
                train_cfg.get("calibrate_unknown_crop", True)
            ),
            unknown_crop_id=int(config["model"].get("num_crop_ids", 32)),
            max_per_image_crop_spray_risk_p99=max_p99_risk,
            max_crop_spray_risk_violation_rate=max_violation_rate,
        )
        selection_key = _validation_selection_key(val_metrics)
        epoch_log = {
            "epoch": epoch + 1,
            "global_step": global_step,
            "learning_rates": [group["lr"] for group in optimizer.param_groups],
            "train": {
                name: value / max(1, batches) for name, value in running.items()
            },
            "val": val_metrics,
            "epoch_seconds": time.monotonic() - epoch_started,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(epoch_log, sort_keys=True) + "\n")
        checkpoint = {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "epoch": epoch + 1,
            "global_step": global_step,
            "config": config,
            "metadata": metadata,
            "validation": val_metrics,
            "validation_selection_key": selection_key,
        }
        _atomic_torch_save(checkpoint, run_dir / "last.pt")
        if best_key is None or selection_key > best_key:
            best_key = selection_key
            _atomic_torch_save(checkpoint, run_dir / "best.pt")
            _write_json(val_metrics, run_dir / "metrics.json")

    summary = {
        "status": "complete",
        "epochs": epochs,
        "global_steps": global_step,
        "best_selection_key": best_key,
        "wall_seconds": time.monotonic() - started,
        **metadata,
    }
    _write_json(summary, run_dir / "summary.json")
    return run_dir


def load_checkpoint(
    checkpoint_path: str | Path, device: torch.device
) -> tuple[nn.Module, dict[str, Any]]:
    checkpoint = torch.load(
        Path(checkpoint_path), map_location="cpu", weights_only=False
    )
    checkpoint["runtime_provenance"] = _checkpoint_code_provenance(checkpoint)
    config = checkpoint["config"]
    configure_cache(config)
    model_config = _model_config(config)
    # Checkpoints contain a complete state_dict. Accessible architectures must
    # not re-download their initialization weights during eval/export.
    if model_config.architecture != "dinov3_convnext_tiny_fpn":
        model_config = replace(model_config, pretrained=False)
    model = build_model(model_config)
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.to(device), checkpoint


def evaluate_checkpoint(
    checkpoint_path: str | Path,
    manifest_path: str | Path,
    data_root: str | Path,
    split: str,
    output_path: str | Path,
    batch_size: int = 1,
    workers: int = 4,
) -> dict[str, object]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the configured benchmark")
    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    config = checkpoint["config"]
    records = [
        record for record in read_manifest(manifest_path) if record.split == split
    ]
    if not records:
        raise ValueError(f"No {split!r} samples in {manifest_path}")
    dataset = ManifestDataset(records, data_root, EvalTransform(), verify_files=True)
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        pin_memory=True,
        collate_fn=padded_collate,
    )
    training = config["training"]
    validation = checkpoint.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError(
            "Checkpoint has no source-validation result; external evaluation "
            "refuses to use an uncalibrated default threshold"
        )
    selected = validation.get("selected_operating_point")
    if not isinstance(selected, Mapping) or "weed_threshold" not in selected:
        raise ValueError(
            "Checkpoint has no source-selected weed threshold; external "
            "threshold tuning is intentionally disabled"
        )
    base_policy = _safety_policy(config)
    selected_by_crop_id = selected.get("weed_threshold_by_crop_id", {})
    if not isinstance(selected_by_crop_id, Mapping):
        raise ValueError("Source crop-ID threshold policy is not a mapping")
    unknown_threshold = float(
        selected.get(
            "unknown_crop_weed_threshold", selected["weed_threshold"]
        )
    )
    base_policy = replace(
        base_policy,
        weed_threshold=unknown_threshold,
        weed_threshold_by_crop_id={
            int(crop_id): float(threshold)
            for crop_id, threshold in selected_by_crop_id.items()
        },
        unknown_crop_weed_threshold=unknown_threshold,
    )
    # The source-validation-selected threshold is the only primary point.
    metrics = evaluate(
        model,
        loader,
        device,
        base_policy,
        thresholds=[base_policy.weed_threshold],
        max_crop_spray_risk=float(
            training.get("max_crop_spray_risk", 0.005)
        ),
        use_amp=bool(training.get("amp", True)),
        tile_size=training.get("eval_tile_size"),
        tile_overlap=int(training.get("eval_tile_overlap", 128)),
        tile_trigger_pixels=int(
            training.get("eval_tile_trigger_pixels", 4_000_000)
        ),
        dilation_sensitivity_radii=(0, 5, 10, 20),
        component_metrics=True,
        max_per_image_crop_spray_risk_p99=float(
            training.get("max_per_image_crop_spray_risk_p99", 1.0)
        ),
        max_crop_spray_risk_violation_rate=float(
            training.get("max_crop_spray_risk_violation_rate", 1.0)
        ),
    )
    metrics["calibration_source"] = {
        "checkpoint": str(Path(checkpoint_path).resolve()),
        "weed_threshold": base_policy.weed_threshold,
        "weed_threshold_by_crop_id": dict(
            base_policy.weed_threshold_by_crop_id
        ),
        "unknown_crop_weed_threshold": unknown_threshold,
        "external_threshold_sweep_performed": False,
    }
    metrics["provenance"] = {
        **checkpoint["runtime_provenance"],
        "evaluation_manifest_sha256": manifest_sha256(manifest_path),
        "evaluation_mask_tree_sha256": mask_tree_sha256(records, data_root),
    }
    _write_json(metrics, Path(output_path))
    return metrics
