from pathlib import Path

import pytest

from scripts.compare_phenobench_domain_adaptation_v1 import filter_plot_groups
from scripts.evaluate_phenobench_detect_segment_fair_v1 import GroundTruth


def _record(sample: str) -> GroundTruth:
    return GroundTruth(
        sample_id=sample,
        image_path=Path("image.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={},
        crop_ids=frozenset(),
    )


def test_plot_filter_is_exact_and_preserves_order() -> None:
    records = [_record("a"), _record("b"), _record("c")]
    selected = filter_plot_groups(
        records,
        {"a": "P1", "b": "P2", "c": "P1"},
        ["P1"],
    )
    assert [record.sample_id for record in selected] == ["a", "c"]


def test_plot_filter_fails_closed_on_missing_group() -> None:
    with pytest.raises(ValueError, match="P2"):
        filter_plot_groups([_record("a")], {"a": "P1"}, ["P1", "P2"])
