from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
import yaml

from scripts.convert_riceseg import (
    archive_pair_index,
    common_from_source,
    record_for,
    write_exact,
)
from scripts.inspect_riceseg_release import validate_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_conversion_gate_keeps_correlated_jiangsu_groups_together() -> None:
    conversion = yaml.safe_load(
        (PROJECT_ROOT / "configs/data/riceseg_conversion_gate_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    release = yaml.safe_load(
        (PROJECT_ROOT / "configs/data/riceseg_release_gate_v1.yaml").read_text(
            encoding="utf-8"
        )
    )

    metadata = validate_metadata(release)

    assert conversion["contract"]["coverage_roles"] == {
        "train": 2474,
        "external_calibration": 604,
    }
    assert set(conversion["contract"]["coverage_holdout_subdatasets"]) == {
        "GD",
        "TKO_2",
    }
    assert release["subdatasets"]["JS_3"]["coverage_role"] == "train"
    assert release["subdatasets"]["JS_4"]["coverage_role"] == "train"
    assert metadata["coverage_roles"] == conversion["contract"]["coverage_roles"]


def test_common_mapping_preserves_crop_organs_and_weed_classes() -> None:
    source = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint8)

    common = common_from_source(source, {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 2})

    assert common.dtype == np.uint8
    assert common.tolist() == [[0, 1, 1], [1, 2, 2]]


def test_common_mapping_rejects_unknown_source_label() -> None:
    with pytest.raises(ValueError, match="Unexpected RiceSEG source labels"):
        common_from_source(
            np.array([[0, 6]], dtype=np.uint8),
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 2},
        )


def test_archive_index_requires_exact_canonical_pairing(tmp_path: Path) -> None:
    archive_path = tmp_path / "pairs.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("RiceSEG/China/JS_1/rgb/plot_001.jpg", b"rgb")
        archive.writestr("RiceSEG/China/JS_1/label/plot_001.png", b"mask")

    with ZipFile(archive_path) as archive:
        rgb, masks = archive_pair_index(
            archive,
            subdatasets={"JS_1": {"aliases": ["JS_1"]}},
            rgb_directory="rgb",
            mask_directory="label",
        )

    assert set(rgb) == {"JS_1/plot_001"}
    assert set(masks) == {"JS_1/plot_001"}


def test_archive_index_rejects_unpaired_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unpaired.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("RiceSEG/China/JS_1/rgb/plot_001.jpg", b"rgb")

    with ZipFile(archive_path) as archive, pytest.raises(
        ValueError, match="RGB/mask keys"
    ):
        archive_pair_index(
            archive,
            subdatasets={"JS_1": {"aliases": ["JS_1"]}},
            rgb_directory="rgb",
            mask_directory="label",
        )


def test_record_grouping_joins_js3_and_js4_same_field_year(tmp_path: Path) -> None:
    data_root = tmp_path.resolve()
    metadata = {
        "dataset_id": "riceseg",
        "target_crop_id": 12,
        "crop_species": "Oryza sativa",
        "weed_species_optional": "weed;duckweed",
        "annotation_exhaustive": True,
        "license_status": "research-only",
        "commercial_allowed": False,
    }
    base = {
        "country": "China",
        "site": "Jiangsu",
        "institute": "NJAU",
        "year": 2023,
        "platform": "handheld_rod",
        "sensor": "SONY_RX0_RGB",
        "growth_stages": ["vegetative"],
        "coverage_role": "train",
    }
    image = data_root / "image.jpg"
    mask = data_root / "mask.png"

    js3 = record_for(
        key="JS_3/a",
        subdataset="JS_3",
        image_path=image,
        common_mask_path=mask,
        specification=base,
        metadata=metadata,
        data_root=data_root,
    )
    js4 = record_for(
        key="JS_4/b",
        subdataset="JS_4",
        image_path=image,
        common_mask_path=mask,
        specification=base,
        metadata=metadata,
        data_root=data_root,
    )

    assert js3.field_id == js4.field_id == "china_jiangsu_njau"
    assert js3.session_id == js4.session_id == "jiangsu_njau_2023"
    assert js3.split == js4.split == "train"


def test_write_exact_is_idempotent_but_refuses_rewrite(tmp_path: Path) -> None:
    destination = tmp_path / "payload.bin"

    assert write_exact(destination, b"original") is True
    assert write_exact(destination, b"original") is False
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        write_exact(destination, b"changed")
