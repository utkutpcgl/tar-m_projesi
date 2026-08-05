from agri_seg.manifest import SampleRecord
from scripts.train_exact_replay_replacement import (
    ExactIndexReplayReplacementSampler,
    replacement_positions,
)


def record(sample_id: str, dataset: str, group: str) -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        image_path=f"images/{sample_id}.png",
        mask_path=f"masks/{sample_id}.png",
        split="train",
        dataset_id=dataset,
        field_id=group,
        session_id=group,
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


def test_replacement_positions_are_even_and_unique() -> None:
    assert replacement_positions(40, 4) == [5, 15, 25, 35]


def test_sampler_preserves_every_non_replaced_baseline_position() -> None:
    base = [record(f"old-{index}", "old", f"g{index % 2}") for index in range(8)]
    target = [record(f"rice-{index}", "riceseg", f"r{index % 2}") for index in range(4)]
    records = base + target
    replay = {
        "target_dataset_id": "riceseg",
        "replacements_per_epoch": 2,
        "target_seed_offset": 101,
        "baseline_dataset_weights": {"old": 1.0},
    }
    sampler = ExactIndexReplayReplacementSampler(
        records,
        num_samples=8,
        seed=17,
        dataset_weights={"old": 0.75, "riceseg": 0.25},
        replay=replay,
    )
    baseline_sampler = sampler.base_sampler
    baseline_sampler.set_epoch(0)
    baseline = [base[index].sample_id for index in baseline_sampler]
    sampler.set_epoch(0)
    candidate = [records[index] for index in sampler]
    positions = set(replacement_positions(8, 2))
    assert all(
        candidate[index].dataset_id == "riceseg"
        for index in positions
    )
    assert all(
        candidate[index].sample_id == baseline[index]
        for index in range(8)
        if index not in positions
    )
