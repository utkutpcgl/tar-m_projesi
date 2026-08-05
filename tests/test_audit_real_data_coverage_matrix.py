from scripts.audit_real_data_coverage_matrix import summarize_dataset
from agri_seg.manifest import SampleRecord


def record(sample: str, split: str, exhaustive: bool) -> SampleRecord:
    return SampleRecord(
        sample_id=sample,
        image_path=f"raw/{sample}.jpg",
        mask_path=f"processed/{sample}.png",
        split=split,
        dataset_id="example",
        field_id="field",
        session_id="session",
        capture_date="",
        platform="uav",
        sensor="rgb",
        target_crop_id=7,
        crop_species="Example crop",
        weed_species_optional="",
        growth_stage="mixed",
        annotation_exhaustive=exhaustive,
        license_status="CC-BY-4.0",
        commercial_allowed=True,
    )


def test_summarize_dataset_preserves_roles_and_exhaustiveness() -> None:
    summary = summarize_dataset(
        [record("a", "train", True), record("b", "external_calibration", False)],
        {"supervision_track": "common_semantic_fail_closed"},
    )

    assert summary["records"] == 2
    assert summary["splits"] == {"external_calibration": 1, "train": 1}
    assert summary["capture_groups"] == 1
    assert summary["annotation_exhaustive_counts"] == {"false": 1, "true": 1}
    assert summary["target_crops"] == {"7": ["Example crop"]}
