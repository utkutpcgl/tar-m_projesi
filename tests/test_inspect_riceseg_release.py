from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
import yaml
from PIL import Image

from scripts.inspect_riceseg_release import (
    canonical_pair_key,
    infer_subdataset,
    inspect_raster_archive,
    safe_members,
    validate_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_frozen_riceseg_metadata_and_split_contract() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs/data/riceseg_release_gate_v1.yaml").read_text(
            encoding="utf-8"
        )
    )

    result = validate_metadata(config)

    assert result["expected_samples"] == 3078
    assert result["subdatasets"] == 19
    assert result["coverage_roles"] == {"train": 2474, "external_calibration": 604}
    assert result["country_transfer"] == {"source": 1824, "target": 1254}


def test_subdataset_inference_uses_boundaries_and_aliases() -> None:
    subdatasets = {
        "JS_1": {"aliases": ["JS_1"]},
        "Kilimanjaro": {"aliases": ["Kilimanjaro", "Kil"]},
    }

    assert infer_subdataset("RiceSEG/JS_1/images/0001.jpg", subdatasets) == "JS_1"
    assert infer_subdataset("labels/Kil/mask-002.png", subdatasets) == "Kilimanjaro"
    with pytest.raises(ValueError, match="Cannot infer"):
        infer_subdataset("labels/skilled/mask-002.png", subdatasets)


def test_canonical_pair_key_removes_only_modality_suffix() -> None:
    assert canonical_pair_key("rgb/JS_1/plot_001_image.jpg", "JS_1") == "JS_1/plot_001"
    assert canonical_pair_key("labels/JS_1/plot_001_mask.png", "JS_1") == "JS_1/plot_001"


def _write_image(archive: ZipFile, name: str, path: Path) -> None:
    archive.write(path, name)


def test_raster_inspector_decodes_and_counts_source_masks(tmp_path: Path) -> None:
    first = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    second = np.array([[4, 5], [0, 1]], dtype=np.uint8)
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    Image.fromarray(first).save(first_path)
    Image.fromarray(second).save(second_path)
    archive_path = tmp_path / "masks.zip"
    with ZipFile(archive_path, "w") as archive:
        _write_image(archive, "RiceSEG/JS_1/plot_001_mask.png", first_path)
        _write_image(archive, "RiceSEG/TG/plot_002_mask.png", second_path)

    result = inspect_raster_archive(
        archive_path,
        kind="mask",
        subdatasets={"JS_1": {"aliases": ["JS_1"]}, "TG": {"aliases": ["TG"]}},
        expected_count=2,
        expected_size=(2, 2),
        allowed_mask_values={0, 1, 2, 3, 4, 5},
    )

    assert result["subdataset_counts"] == {"JS_1": 1, "TG": 1}
    assert result["class_pixels"] == {"0": 2, "1": 2, "2": 1, "3": 1, "4": 1, "5": 1}


def test_raster_inspector_rejects_unknown_mask_value(tmp_path: Path) -> None:
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.array([[0, 6], [1, 2]], dtype=np.uint8)).save(mask_path)
    archive_path = tmp_path / "masks.zip"
    with ZipFile(archive_path, "w") as archive:
        _write_image(archive, "RiceSEG/JS_1/plot_001_mask.png", mask_path)

    with pytest.raises(ValueError, match="Unexpected RiceSEG mask values"):
        inspect_raster_archive(
            archive_path,
            kind="mask",
            subdatasets={"JS_1": {"aliases": ["JS_1"]}},
            expected_count=1,
            expected_size=(2, 2),
            allowed_mask_values={0, 1, 2, 3, 4, 5},
        )


def test_safe_members_rejects_parent_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.png", b"not an image")

    with ZipFile(archive_path) as archive, pytest.raises(ValueError, match="Unsafe"):
        safe_members(archive, "fixture")
