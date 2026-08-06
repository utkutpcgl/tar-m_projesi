from __future__ import annotations

import numpy as np

from scripts.build_domain_adaptation_curve_v1 import farthest_point_order


def test_farthest_point_order_is_deterministic_and_complete() -> None:
    features = np.asarray([[0.0], [1.0], [2.0], [10.0]], dtype=np.float32)
    ids = ["a", "b", "c", "d"]
    first = farthest_point_order(features, ids)
    second = farthest_point_order(features, ids)
    assert first == second
    assert sorted(first) == list(range(4))
    assert first[0] in {1, 2}


def test_farthest_point_ties_are_broken_by_sample_id() -> None:
    features = np.asarray([[-1.0], [0.0], [1.0]], dtype=np.float32)
    order = farthest_point_order(features, ["z", "m", "a"])
    assert order[0] == 1
    assert order[1] == 2
