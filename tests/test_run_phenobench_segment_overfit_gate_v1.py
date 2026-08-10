from pathlib import Path

import pytest

from scripts.evaluate_phenobench_detect_segment_fair_v1 import GroundTruth
from scripts.run_phenobench_segment_overfit_gate_v1 import (
    _thresholds,
    select_balanced_subset,
)


def _record(sample: str, sizes: tuple[float, ...]) -> GroundTruth:
    return GroundTruth(
        sample_id=sample,
        image_path=Path(f"{sample}.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={index + 1: size for index, size in enumerate(sizes)},
        crop_ids=frozenset(),
    )


def test_balanced_selector_is_deterministic_and_round_robin() -> None:
    records = [
        _record("a1", (50,)),
        _record("a2", (55,)),
        _record("a3", (10,)),
        _record("b1", (60,)),
        _record("b2", (70,)),
    ]
    metadata = {
        "a1": {"plot_group": "A"},
        "a2": {"plot_group": "A"},
        "a3": {"plot_group": "A"},
        "b1": {"plot_group": "B"},
        "b2": {"plot_group": "B"},
    }
    first = select_balanced_subset(
        records, metadata, count=4, minimum_size_px=42, seed=23
    )
    second = select_balanced_subset(
        records, metadata, count=4, minimum_size_px=42, seed=23
    )
    assert [item.sample_id for item in first] == [item.sample_id for item in second]
    assert {item.sample_id for item in first} == {"a1", "a2", "b1", "b2"}


def test_balanced_selector_rejects_impossible_request() -> None:
    record = _record("a", (10,))
    with pytest.raises(ValueError, match="only 0"):
        select_balanced_subset(
            [record], {"a": {"plot_group": "A"}}, count=1, minimum_size_px=42, seed=1
        )


def test_confidence_grid_is_inclusive() -> None:
    assert _thresholds(
        {"confidence_start": 0.01, "confidence_stop": 0.03, "confidence_step": 0.01}
    ) == [0.01, 0.02, 0.03]
