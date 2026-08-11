from pathlib import Path

from scripts.evaluate_phenobench_cropcraft_deploy_action_ab_v1 import eligibility_view
from scripts.evaluate_phenobench_detect_segment_fair_v1 import Action, GroundTruth


def test_physical_size_view_ignores_subservice_region_actions() -> None:
    truth = GroundTruth(
        sample_id="synthetic",
        image_path=Path("rgb.jpg"),
        semantics_path=Path("semantics.png"),
        instances_path=Path("instances.png"),
        weed_sizes={1: 40.9, 2: 82.1},
        crop_ids=frozenset({3}),
    )
    actions = {
        "synthetic": [
            Action("synthetic", 0.9, 1, 1, "weed", 1),
            Action("synthetic", 0.8, 2, 2, "weed", 2),
        ]
    }
    records, filtered = eligibility_view([truth], actions, 82.0)
    assert records[0].weed_sizes == {2: 82.1}
    assert filtered["synthetic"][0].target_kind == "ignore"
    assert filtered["synthetic"][1].target_kind == "weed"
