from agri_seg.manifest import SampleRecord

from scripts.build_reproductive_ab_manifests_v9 import select_reproductive_calibration


def record(sample_id: str, split: str, stage: str, dataset_id: str = "riceseg") -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        image_path=f"{sample_id}.jpg",
        mask_path=f"{sample_id}.png",
        split=split,
        dataset_id=dataset_id,
        field_id=sample_id,
        session_id=sample_id,
        capture_date="2022",
        platform="camera",
        sensor="rgb",
        target_crop_id=12,
        crop_species="Oryza sativa",
        weed_species_optional="weed",
        growth_stage=stage,
        annotation_exhaustive=True,
        license_status="research",
        commercial_allowed=False,
    )


def test_late_subset_is_upstream_reproductive_calibration_only() -> None:
    rows = [
        record("keep", "external_calibration", "reproductive"),
        record("mixed", "external_calibration", "vegetative;transition;reproductive"),
        record("train", "train", "reproductive"),
        record("other", "external_calibration", "reproductive", "other"),
    ]

    assert [row.sample_id for row in select_reproductive_calibration(rows)] == ["keep"]
