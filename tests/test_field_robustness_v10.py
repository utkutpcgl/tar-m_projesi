from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scripts.convert_cropcraft_field_robustness_release import common_mask
from scripts.generate_cropcraft_field_robustness_pilot import (
    deep_merge,
    validate_asset_contract,
)


def test_deep_merge_preserves_base_and_replaces_sequences() -> None:
    base = {
        "release": "smoke",
        "frames_per_scene": 1,
        "splits": {
            "train": {
                "scenes": 4,
                "quality_gates": {"expected_pairs": 4, "minimum": 1},
                "assets": ["old"],
            }
        },
    }
    result = deep_merge(
        base,
        {
            "release": "pilot",
            "frames_per_scene": 2,
            "splits": {
                "train": {
                    "scenes": 24,
                    "quality_gates": {"expected_pairs": 48},
                    "assets": ["new_a", "new_b"],
                }
            },
        },
    )
    assert result["release"] == "pilot"
    assert result["splits"]["train"]["quality_gates"] == {
        "expected_pairs": 48,
        "minimum": 1,
    }
    assert result["splits"]["train"]["assets"] == ["new_a", "new_b"]
    assert base["splits"]["train"]["assets"] == ["old"]


def test_asset_contract_rejects_cross_role_overlap() -> None:
    study = {
        "splits": {
            "train": {
                "asset_profile": {
                    "ground_material_ids": ["shared"],
                    "environment_files": ["train.hdr"],
                }
            },
            "val": {
                "asset_profile": {
                    "ground_material_ids": ["shared"],
                    "environment_files": ["val.hdr"],
                }
            },
            "test": {
                "asset_profile": {
                    "ground_material_ids": ["test"],
                    "environment_files": ["test.hdr"],
                }
            },
        }
    }
    pack = {
        "split_asset_contract": {
            "train": {"grounds": ["shared"], "environments": ["train.hdr"]},
            "val": {"grounds": ["shared"], "environments": ["val.hdr"]},
            "test": {"grounds": ["test"], "environments": ["test.hdr"]},
        }
    }
    with pytest.raises(ValueError, match="asset leakage"):
        validate_asset_contract(study, pack)


def test_common_mask_converts_exact_palette(tmp_path: Path) -> None:
    raw = np.array(
        [
            [[0, 0, 0], [0, 255, 0]],
            [[255, 0, 0], [0, 0, 0]],
        ],
        dtype=np.uint8,
    )
    path = tmp_path / "mask.png"
    Image.fromarray(raw).save(path)
    converted = common_mask(path)
    assert converted.tolist() == [[0, 1], [2, 0]]


def test_common_mask_fails_closed_on_unknown_colour(tmp_path: Path) -> None:
    path = tmp_path / "bad.png"
    Image.fromarray(np.array([[[1, 2, 3]]], dtype=np.uint8)).save(path)
    with pytest.raises(ValueError, match="Unexpected mask colours"):
        common_mask(path)
