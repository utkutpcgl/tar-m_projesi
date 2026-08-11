from pathlib import Path

import pytest

from scripts.prepare_phenobench_cropcraft_deploy_ab_v1 import (
    deterministic_replay,
    label_for,
)


def test_deterministic_replay_is_fixed_unique_and_sorted() -> None:
    paths = [Path(f"/x/images/train/{index}.png") for index in range(20)]
    first = deterministic_replay(paths, 5, 17)
    assert first == deterministic_replay(list(reversed(paths)), 5, 17)
    assert first == sorted(first)
    assert len(set(first)) == 5


def test_replay_rejects_invalid_count() -> None:
    with pytest.raises(ValueError, match="Replay count"):
        deterministic_replay([Path("/x/images/train/a.png")], 2, 1)


def test_label_for_maps_last_images_component() -> None:
    assert label_for(Path("/x/images/train/a.png")) == Path("/x/labels/train/a.txt")
