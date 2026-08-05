from dataclasses import replace

from agri_seg.manifest import SampleRecord
from scripts.audit_riceseg_sampler_streams import compare_streams


def record(sample_id: str, dataset_id: str = "old") -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        image_path=f"images/{sample_id}.png",
        mask_path=f"masks/{sample_id}.png",
        split="train",
        dataset_id=dataset_id,
        field_id="field",
        session_id="session",
        capture_date="2024",
        platform="ground",
        sensor="rgb",
        target_crop_id=1,
        crop_species="crop",
        weed_species_optional="weed",
        growth_stage="mixed",
        annotation_exhaustive=True,
        license_status="research",
        commercial_allowed=False,
    )


def test_compare_streams_distinguishes_volume_from_exact_replay() -> None:
    baseline = [[record("a"), record("b"), record("c")]]
    candidate = [[record("b"), record("a"), record("rice", "riceseg"), record("c")]]
    result = compare_streams(baseline, candidate, "riceseg")
    assert result["interpretation"] == "expected_volume_only_not_exact_index_replay"
    assert result["totals"]["candidate_old_draws"] == 3
    assert result["totals"]["old_sample_multiset_overlap"] == 3
    assert result["totals"]["exact_old_filtered_position_matches"] == 1


def test_compare_streams_accepts_exact_filtered_replay() -> None:
    baseline = [[record("a"), record("b")]]
    candidate = [[record("a"), record("b")]]
    result = compare_streams(baseline, candidate, "riceseg")
    assert result["interpretation"] == "exact_index_replay"
