import pytest

from scripts.train_phenobench_target_replay_v1 import interleave_equal


def test_equal_replay_interleaves_without_overlap() -> None:
    assert interleave_equal(["s1", "s2"], ["t1", "t2"]) == [
        "s1",
        "t1",
        "s2",
        "t2",
    ]


def test_replay_fails_on_imbalance_or_overlap() -> None:
    with pytest.raises(ValueError, match="equal"):
        interleave_equal(["s1"], ["t1", "t2"])
    with pytest.raises(ValueError, match="overlap"):
        interleave_equal(["same"], ["same"])
