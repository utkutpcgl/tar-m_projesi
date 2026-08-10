from scripts.build_fair_detection_segmentation_report_v1 import (
    pct,
    portable_filename,
    verdict,
)


def test_report_helpers() -> None:
    assert pct(0.955) == "%95,5"
    passed = {"segmentation_preference_gate": {"passed": True}}
    failed = {"segmentation_preference_gate": {"passed": False}}
    assert verdict(passed)[0].startswith("SEGMENTATION")
    assert verdict(failed)[0].startswith("SPREY")
    assert portable_filename("01_phenobench:val:image.jpg") == (
        "01_phenobench__val__image.jpg"
    )
