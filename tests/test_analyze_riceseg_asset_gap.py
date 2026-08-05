from collections import Counter

from scripts.analyze_riceseg_asset_gap import factor_evidence, select_factor


def test_selection_chooses_largest_uncovered_semantic_fraction() -> None:
    candidates = {
        "early": {
            "source_classes": [1],
            "accepted_pack_explicitly_covered": True,
            "evidence": "covered",
        },
        "reproductive": {
            "source_classes": [2, 3],
            "accepted_pack_explicitly_covered": False,
            "evidence": "missing",
        },
        "duckweed": {
            "source_classes": [5],
            "accepted_pack_explicitly_covered": False,
            "evidence": "missing",
        },
    }
    pixels = Counter({0: 700, 1: 200, 2: 25, 3: 50, 5: 25})
    bearing = Counter({1: 10, 2: 4, 3: 6, 5: 8})

    evidence = factor_evidence(candidates, pixels, bearing, total_pixels=1000)

    assert evidence["reproductive"]["source_pixel_fraction"] == 0.075
    assert evidence["duckweed"]["source_pixel_fraction"] == 0.025
    assert select_factor(evidence, "reproductive") == "reproductive"


def test_covered_factor_cannot_win_even_if_more_prevalent() -> None:
    evidence = {
        "covered": {
            "source_pixel_fraction": 0.9,
            "class_bearing_sample_sum": 100,
            "accepted_pack_explicitly_covered": True,
        },
        "missing": {
            "source_pixel_fraction": 0.01,
            "class_bearing_sample_sum": 2,
            "accepted_pack_explicitly_covered": False,
        },
    }

    assert select_factor(evidence, "missing") == "missing"
