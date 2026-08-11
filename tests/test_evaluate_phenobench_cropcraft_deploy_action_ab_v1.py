from pathlib import Path

from scripts.evaluate_phenobench_detect_segment_fair_v1 import Action, GroundTruth
from scripts.evaluate_phenobench_cropcraft_deploy_action_ab_v1 import eligibility_view


def test_eligibility_view_ignores_actions_on_smaller_weeds() -> None:
    record = GroundTruth(
        sample_id="x",
        image_path=Path("image.png"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={1: 20.0, 2: 50.0},
        crop_ids=frozenset(),
    )
    actions = {
        "x": [
            Action("x", 0.9, 1, 1, "weed", 1),
            Action("x", 0.8, 2, 2, "weed", 2),
        ]
    }
    records, filtered = eligibility_view([record], actions, 42.0)
    assert records[0].weed_sizes == {2: 50.0}
    assert filtered["x"][0].target_kind == "ignore"
    assert filtered["x"][1].target_kind == "weed"
