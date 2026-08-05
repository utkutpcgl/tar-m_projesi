import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from agri_seg.gallery import (
    create_error_gallery,
    image_quality_metrics,
    select_gallery_entries,
    source_calibrated_policy,
)
from agri_seg.manifest import SampleRecord, write_manifest
from agri_seg.safety import SafetyPolicy


def _entry(index: int, weed_iou: float) -> dict[str, object]:
    return {
        "sample_id": f"sample-{index:02d}",
        "dataset_id": "synthetic",
        "group_id": f"synthetic::field::{index}",
        "image_path": f"images/{index}.png",
        "mask_path": f"masks/{index}.png",
        "metrics": {
            "crop_pixels": 10,
            "crop_spray_risk": 0.0,
            "crop_safety_constraint_met": True,
            "weed_iou_ranking_value": weed_iou,
        },
    }


def test_gallery_selects_disjoint_ten_best_and_ten_worst() -> None:
    entries = [_entry(index, index / 23) for index in range(24)]
    selected = select_gallery_entries(entries)
    best = [item for item in selected if item["selection"] == "best"]
    worst = [item for item in selected if item["selection"] == "worst"]
    assert len(best) == 10
    assert len(worst) == 10
    assert {item["sample_id"] for item in best}.isdisjoint(
        item["sample_id"] for item in worst
    )
    assert best[0]["sample_id"] == "sample-23"
    assert worst[0]["sample_id"] == "sample-00"


def test_gallery_uses_every_available_image_once_below_twenty() -> None:
    entries = [_entry(index, index / 6) for index in range(7)]
    selected = select_gallery_entries(entries)
    assert len(selected) == 7
    assert len({item["sample_id"] for item in selected}) == 7
    assert sum(item["selection"] == "best" for item in selected) == 4
    assert sum(item["selection"] == "worst" for item in selected) == 3


def test_image_quality_reports_crop_spray_and_semantic_weed_iou() -> None:
    probabilities = torch.tensor(
        [
            [
                [[0.05, 0.05], [0.90, 0.90]],
                [[0.05, 0.05], [0.05, 0.05]],
                [[0.90, 0.90], [0.05, 0.05]],
            ]
        ]
    )
    target = torch.tensor([[[1, 2], [0, 255]]])
    metrics = image_quality_metrics(
        probabilities,
        target,
        SafetyPolicy(
            weed_threshold=0.7,
            crop_threshold=0.4,
            min_confidence=0.5,
            min_margin=0.1,
            max_entropy=0.9,
            crop_dilation_px=0,
        ),
        max_crop_spray_risk=0.005,
    )
    assert metrics["weed_iou"] == 0.5
    assert metrics["crop_spray_risk"] == 1.0
    assert metrics["safe_weed_recall"] == 1.0
    assert metrics["crop_safety_constraint_met"] is False
    assert metrics["valid_pixels"] == 3


def test_gallery_requires_a_source_selected_threshold() -> None:
    with pytest.raises(ValueError, match="source-selected"):
        source_calibrated_policy(
            {
                "config": {"safety": {}, "training": {}},
                "validation": {"selected_operating_point": {}},
            }
        )


class _TinyModel(torch.nn.Module):
    def forward(
        self, images: torch.Tensor, target_crop_id: torch.Tensor
    ) -> torch.Tensor:
        logits = torch.zeros(
            images.shape[0],
            3,
            images.shape[-2],
            images.shape[-1],
            device=images.device,
        )
        logits[:, 0] = 2.0
        return logits


def test_create_error_gallery_cpu_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    (data_root / "images").mkdir(parents=True)
    (data_root / "masks").mkdir(parents=True)
    records: list[SampleRecord] = []
    for index in range(4):
        if index == 0:
            image_name = f"{index}.npy"
            rgb16 = np.zeros((8, 12, 3), dtype=np.uint16)
            rgb16[..., 0] = 32768
            rgb16[..., 1] = 8192
            rgb16[..., 2] = 65535
            np.save(data_root / f"images/{image_name}", rgb16)
        else:
            image_name = f"{index}.png"
            Image.new(
                "RGB", (12, 8), (30 + index * 20, 90, 40)
            ).save(data_root / f"images/{image_name}")
        mask = np.zeros((8, 12), dtype=np.uint8)
        mask[:, 2:5] = 1
        mask[:, 7 : 8 + index] = 2
        Image.fromarray(mask).save(data_root / f"masks/{index}.png")
        records.append(
            SampleRecord(
                sample_id=f"tiny-{index}",
                image_path=f"images/{image_name}",
                mask_path=f"masks/{index}.png",
                split="external_test",
                dataset_id="tiny",
                field_id="field",
                session_id=f"session-{index}",
                capture_date="2026-01-01",
                platform="test",
                sensor="rgb",
                target_crop_id=0,
                crop_species="test-crop",
                weed_species_optional="test-weed",
                growth_stage="test",
                annotation_exhaustive=True,
                license_status="test",
                commercial_allowed=True,
            )
        )
    manifest = tmp_path / "manifest.csv"
    write_manifest(records, manifest)
    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_path.write_bytes(b"synthetic checkpoint identity")
    checkpoint = {
        "config": {
            "model": {"architecture": "tiny"},
            "safety": {
                "weed_threshold": 0.7,
                "crop_threshold": 0.4,
                "min_confidence": 0.55,
                "min_margin": 0.15,
                "max_entropy": 0.85,
                "crop_dilation_px": 0,
            },
            "training": {"amp": False, "max_crop_spray_risk": 0.005},
        },
        "validation": {
            "selected_operating_point": {"weed_threshold": 0.77}
        },
        "epoch": 3,
        "global_step": 12,
    }

    monkeypatch.setattr(
        "agri_seg.gallery.load_checkpoint",
        lambda _path, _device: (_TinyModel().to(_device), checkpoint),
    )
    index_path = create_error_gallery(
        checkpoint_path,
        manifest,
        data_root,
        "external_test",
        tmp_path / "gallery",
        workers=0,
        device="cpu",
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["selection_counts"] == {"best": 2, "total": 4, "worst": 2}
    assert index["calibration"]["frozen_policy"]["weed_threshold"] == 0.77
    assert index["calibration"]["external_threshold_sweep_performed"] is False
    artifacts = list((tmp_path / "gallery").glob("*/*.jpg"))
    assert len(artifacts) == 4
    assert len(index["artifacts"]) == 4
