from pathlib import Path

import pytest

from agri_seg.manifest import (
    SampleRecord,
    assert_no_group_leakage,
    mask_tree_sha256,
    read_manifest,
    write_manifest,
)


def record(sample_id: str, split: str, session: str = "s1") -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        image_path="image.png",
        mask_path="mask.png",
        split=split,
        dataset_id="dataset",
        field_id="field",
        session_id=session,
        capture_date="2026-01-01",
        platform="robot",
        sensor="rgb",
        target_crop_id=0,
        crop_species="crop",
        weed_species_optional="",
        growth_stage="early",
        annotation_exhaustive=True,
        license_status="CC-BY-4.0",
        commercial_allowed=True,
    )


def test_manifest_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    expected = [record("one", "train", "train_session")]
    assert write_manifest(expected, path) == 1
    assert read_manifest(path) == expected


def test_group_leakage_is_rejected() -> None:
    with pytest.raises(ValueError, match="leakage"):
        assert_no_group_leakage(
            [record("train", "train"), record("val", "val")]
        )


def test_separate_sessions_are_allowed() -> None:
    assert_no_group_leakage(
        [
            record("train", "train", "train_session"),
            record("val", "val", "val_session"),
        ]
    )


def test_external_calibration_cannot_share_a_training_group() -> None:
    with pytest.raises(ValueError, match="leakage"):
        assert_no_group_leakage(
            [
                record("train", "train", "same_session"),
                record(
                    "calibration",
                    "external_calibration",
                    "same_session",
                ),
            ]
        )


def test_mask_tree_hash_detects_same_path_label_rewrite(tmp_path: Path) -> None:
    mask = tmp_path / "mask.bin"
    mask.write_bytes(b"first normalized label")
    sample = record("hash", "train", "hash_session")
    sample = SampleRecord(
        **{
            **sample.__dict__,
            "mask_path": "mask.bin",
        }
    )
    first = mask_tree_sha256([sample], tmp_path)
    mask.write_bytes(b"second normalized label")
    second = mask_tree_sha256([sample], tmp_path)
    assert first != second
