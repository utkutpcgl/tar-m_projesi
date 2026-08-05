"""Manifest-backed datasets and deterministic domain-balanced sampling."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Mapping, Sequence, TypeAlias

import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset, Sampler
from torchvision.transforms import ColorJitter
from torchvision.transforms import functional as F
from torchvision.transforms.functional import InterpolationMode

from .constants import IGNORE, IMAGENET_MEAN, IMAGENET_STD
from .manifest import SampleRecord, iter_resolved

ImageInput: TypeAlias = Image.Image | torch.Tensor


def load_rgb_image(path: str | Path) -> ImageInput:
    """Load ordinary RGB files or lossless uint16 HWC arrays."""
    source = Path(path)
    if source.suffix.lower() == ".npy":
        array = np.load(source, allow_pickle=False)
        if array.ndim != 3 or array.shape[2] != 3:
            raise ValueError(f"Expected HWC RGB array at {source}, got {array.shape}")
        if array.dtype == np.uint16:
            scale = 65535.0
        elif array.dtype == np.uint8:
            scale = 255.0
        elif np.issubdtype(array.dtype, np.floating):
            scale = 1.0
        else:
            raise ValueError(f"Unsupported RGB array dtype at {source}: {array.dtype}")
        tensor = torch.from_numpy(np.ascontiguousarray(array)).permute(2, 0, 1)
        tensor = tensor.float().div_(scale)
        if not torch.isfinite(tensor).all() or tensor.min() < 0 or tensor.max() > 1:
            raise ValueError(f"RGB array values must normalize to [0, 1]: {source}")
        return tensor
    with Image.open(source) as handle:
        return handle.convert("RGB")


def image_hw(image: ImageInput) -> tuple[int, int]:
    if isinstance(image, Image.Image):
        return image.height, image.width
    return int(image.shape[-2]), int(image.shape[-1])


def to_display_pil(image: ImageInput) -> Image.Image:
    """Create an 8-bit visualization without changing training radiometry."""
    if isinstance(image, Image.Image):
        return image.copy()
    return F.to_pil_image(image.clamp(0, 1))


def _normalized_tensor(image: ImageInput) -> torch.Tensor:
    if isinstance(image, Image.Image):
        tensor = F.pil_to_tensor(image).float().div_(255.0)
    else:
        tensor = image.float()
    return F.normalize(tensor, IMAGENET_MEAN, IMAGENET_STD)


class TrainTransform:
    def __init__(
        self,
        crop_size: int = 512,
        scale_min: float = 0.65,
        scale_max: float = 1.6,
    ) -> None:
        self.crop_size = crop_size
        self.scale_min = scale_min
        self.scale_max = scale_max
        self.color = ColorJitter(
            brightness=0.35, contrast=0.35, saturation=0.3, hue=0.06
        )

    def __call__(
        self, image: ImageInput, mask: Image.Image
    ) -> tuple[torch.Tensor, torch.Tensor]:
        scale = random.uniform(self.scale_min, self.scale_max)
        image_h, image_w = image_hw(image)
        target_h = max(1, round(image_h * scale))
        target_w = max(1, round(image_w * scale))
        image = F.resize(
            image,
            [target_h, target_w],
            interpolation=InterpolationMode.BILINEAR,
            antialias=True,
        )
        mask = F.resize(
            mask,
            [target_h, target_w],
            interpolation=InterpolationMode.NEAREST,
        )

        image_h, image_w = image_hw(image)
        pad_w = max(0, self.crop_size - image_w)
        pad_h = max(0, self.crop_size - image_h)
        if pad_w or pad_h:
            left = random.randint(0, pad_w)
            top = random.randint(0, pad_h)
            padding = (left, top, pad_w - left, pad_h - top)
            if isinstance(image, Image.Image):
                image = ImageOps.expand(
                    image, border=padding, fill=(0, 0, 0)
                )
            else:
                image = F.pad(image, list(padding), fill=0)
            mask = ImageOps.expand(mask, border=padding, fill=IGNORE)

        image_h, image_w = image_hw(image)
        top = random.randint(0, image_h - self.crop_size)
        left = random.randint(0, image_w - self.crop_size)
        image = F.crop(image, top, left, self.crop_size, self.crop_size)
        mask = F.crop(mask, top, left, self.crop_size, self.crop_size)

        if random.random() < 0.5:
            image = F.hflip(image)
            mask = F.hflip(mask)
        if random.random() < 0.5:
            image = F.vflip(image)
            mask = F.vflip(mask)
        if random.random() < 0.8:
            image = self.color(image)
        if random.random() < 0.15:
            image = F.gaussian_blur(image, kernel_size=5)

        image_tensor = _normalized_tensor(image)
        mask_tensor = torch.from_numpy(
            np.asarray(mask, dtype=np.uint8).copy()
        ).long()
        return image_tensor, mask_tensor


class EvalTransform:
    def __call__(
        self, image: ImageInput, mask: Image.Image
    ) -> tuple[torch.Tensor, torch.Tensor]:
        image_tensor = _normalized_tensor(image)
        mask_tensor = torch.from_numpy(
            np.asarray(mask, dtype=np.uint8).copy()
        ).long()
        return image_tensor, mask_tensor


class FixedCropTransform:
    """Deterministic fixed-size transform for overfit and pipeline tests."""

    def __init__(self, crop_size: int = 512) -> None:
        self.crop_size = crop_size

    def __call__(
        self, image: ImageInput, mask: Image.Image
    ) -> tuple[torch.Tensor, torch.Tensor]:
        image_h, image_w = image_hw(image)
        scale = max(
            self.crop_size / image_h,
            self.crop_size / image_w,
            1.0,
        )
        if scale != 1.0:
            size = [round(image_h * scale), round(image_w * scale)]
            image = F.resize(
                image,
                size,
                interpolation=InterpolationMode.BILINEAR,
                antialias=True,
            )
            mask = F.resize(
                mask, size, interpolation=InterpolationMode.NEAREST
            )
        image_h, image_w = image_hw(image)
        top = (image_h - self.crop_size) // 2
        left = (image_w - self.crop_size) // 2
        image = F.crop(image, top, left, self.crop_size, self.crop_size)
        mask = F.crop(mask, top, left, self.crop_size, self.crop_size)
        image_tensor = _normalized_tensor(image)
        mask_tensor = torch.from_numpy(
            np.asarray(mask, dtype=np.uint8).copy()
        ).long()
        return image_tensor, mask_tensor


class ManifestDataset(Dataset[dict[str, object]]):
    def __init__(
        self,
        records: Sequence[SampleRecord],
        data_root: str | Path,
        transform: TrainTransform | EvalTransform | FixedCropTransform,
        verify_files: bool = True,
    ) -> None:
        self.records = list(records)
        self.samples = list(iter_resolved(self.records, data_root))
        self.transform = transform
        if verify_files:
            missing: list[str] = []
            for _, image, mask in self.samples:
                if not image.is_file():
                    missing.append(str(image))
                if not mask.is_file():
                    missing.append(str(mask))
            if missing:
                raise FileNotFoundError(
                    f"{len(missing)} manifest files are missing; first: {missing[:5]}"
                )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, object]:
        record, image_path, mask_path = self.samples[index]
        image = load_rgb_image(image_path)
        original_height, original_width = image_hw(image)
        with Image.open(mask_path) as mask_handle:
            mask = mask_handle.convert("L")
        image_tensor, mask_tensor = self.transform(image, mask)
        return {
            "image": image_tensor,
            "mask": mask_tensor,
            "target_crop_id": torch.tensor(record.target_crop_id, dtype=torch.long),
            "sample_id": record.sample_id,
            "dataset_id": record.dataset_id,
            "group_id": record.group_id,
            "growth_stage": record.growth_stage,
            "crop_species": record.crop_species,
            "platform": record.platform,
            "sensor": record.sensor,
            "original_size": (original_height, original_width),
        }


def padded_collate(
    batch: Sequence[dict[str, object]], multiple: int = 32
) -> dict[str, object]:
    """Pad variable-resolution evaluation images without adding valid labels."""
    max_h = max(int(item["image"].shape[-2]) for item in batch)  # type: ignore[union-attr]
    max_w = max(int(item["image"].shape[-1]) for item in batch)  # type: ignore[union-attr]
    target_h = math.ceil(max_h / multiple) * multiple
    target_w = math.ceil(max_w / multiple) * multiple
    images: list[torch.Tensor] = []
    masks: list[torch.Tensor] = []
    valid_sizes: list[tuple[int, int]] = []
    for item in batch:
        image = item["image"]  # type: ignore[assignment]
        mask = item["mask"]  # type: ignore[assignment]
        height, width = image.shape[-2:]
        valid_sizes.append((height, width))
        images.append(F.pad(image, [0, 0, target_w - width, target_h - height], 0.0))
        masks.append(F.pad(mask, [0, 0, target_w - width, target_h - height], IGNORE))
    return {
        "image": torch.stack(images),
        "mask": torch.stack(masks),
        "target_crop_id": torch.stack(
            [item["target_crop_id"] for item in batch]  # type: ignore[list-item]
        ),
        "sample_id": [item["sample_id"] for item in batch],
        "dataset_id": [item["dataset_id"] for item in batch],
        "group_id": [item["group_id"] for item in batch],
        "growth_stage": [item["growth_stage"] for item in batch],
        "crop_species": [item["crop_species"] for item in batch],
        "platform": [item["platform"] for item in batch],
        "sensor": [item["sensor"] for item in batch],
        "valid_size": valid_sizes,
    }


class DomainBalancedSampler(Sampler[int]):
    """Sample dataset -> field/session group -> image with equal domain weight."""

    def __init__(
        self,
        records: Sequence[SampleRecord],
        num_samples: int | None = None,
        seed: int = 17,
        dataset_weights: Mapping[str, float] | None = None,
    ) -> None:
        self.records = list(records)
        self.num_samples = num_samples or len(records)
        self.seed = seed
        self.epoch = 0
        nested: dict[str, dict[str, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for index, record in enumerate(records):
            nested[record.dataset_id][record.group_id].append(index)
        if not nested:
            raise ValueError("DomainBalancedSampler needs at least one sample")
        self.index = {
            dataset: dict(groups) for dataset, groups in nested.items()
        }
        self.datasets = sorted(self.index)
        configured = dict(dataset_weights or {})
        if dataset_weights is not None:
            configured_datasets = set(configured)
            observed_datasets = set(self.datasets)
            if configured_datasets != observed_datasets:
                raise ValueError(
                    "Domain sampler dataset_weights must exactly match the "
                    f"training datasets: configured={sorted(configured_datasets)}, "
                    f"observed={sorted(observed_datasets)}"
                )
        self.dataset_weights = [
            float(configured.get(dataset, 1.0)) for dataset in self.datasets
        ]
        if any(weight <= 0 for weight in self.dataset_weights):
            raise ValueError("Domain sampler dataset weights must be positive")
        if dataset_weights is not None and not math.isclose(
            sum(self.dataset_weights), 1.0, abs_tol=1e-9
        ):
            raise ValueError("Domain sampler dataset weights must sum to 1")

    def __iter__(self) -> Iterator[int]:
        rng = random.Random(self.seed + self.epoch)
        for _ in range(self.num_samples):
            dataset = rng.choices(
                self.datasets, weights=self.dataset_weights, k=1
            )[0]
            group = rng.choice(sorted(self.index[dataset]))
            yield rng.choice(self.index[dataset][group])

    def __len__(self) -> int:
        return self.num_samples

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch
