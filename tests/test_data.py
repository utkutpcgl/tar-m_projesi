from pathlib import Path

import numpy as np
import pytest
import torch

from agri_seg.data import DomainBalancedSampler, load_rgb_image
from agri_seg.manifest import SampleRecord


def test_uint16_rgb_array_keeps_full_normalized_precision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "multispectral_rgb.npy"
    values = np.array([[[0, 32768, 65535], [1, 257, 4097]]], dtype=np.uint16)
    np.save(source, values)

    image = load_rgb_image(source)
    assert isinstance(image, torch.Tensor)
    assert image.shape == (3, 1, 2)
    torch.testing.assert_close(
        image[:, 0, 1],
        torch.tensor([1, 257, 4097], dtype=torch.float32) / 65535.0,
    )


def _sample(sample_id: str, dataset_id: str) -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        image_path=f"{sample_id}.jpg",
        mask_path=f"{sample_id}.png",
        split="train",
        dataset_id=dataset_id,
        field_id="field",
        session_id="session",
        capture_date="2026-01-01",
        platform="ground",
        sensor="rgb",
        target_crop_id=0,
        crop_species="crop",
        weed_species_optional="weed",
        growth_stage="early",
        annotation_exhaustive=True,
        license_status="test",
        commercial_allowed=True,
    )


def test_domain_sampler_requires_exact_normalized_dataset_weights() -> None:
    records = [_sample("a", "alpha"), _sample("b", "beta")]

    with pytest.raises(ValueError, match="exactly match"):
        DomainBalancedSampler(records, dataset_weights={"alpha": 1.0})
    with pytest.raises(ValueError, match="sum to 1"):
        DomainBalancedSampler(
            records, dataset_weights={"alpha": 0.7, "beta": 0.7}
        )

    sampler = DomainBalancedSampler(
        records, dataset_weights={"alpha": 0.4, "beta": 0.6}
    )
    assert sampler.datasets == ["alpha", "beta"]
