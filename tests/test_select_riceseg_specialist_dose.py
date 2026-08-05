from scripts.select_riceseg_specialist_dose import (
    screen_checks,
    selection_key,
    target_summary,
)


def _run(early: float, full: float, reproductive: float) -> dict:
    return {
        "artifacts": {
            "early_rice": {"mean_iou": early},
            "riceseg": {"mean_iou": full},
            "riceseg_reproductive": {"mean_iou": reproductive},
        }
    }


def test_target_summary_uses_worst_and_macro() -> None:
    summary = target_summary(_run(0.5, 0.7, 0.4))
    assert summary["target_robust_mean_iou"] == 0.4
    assert summary["target_macro_mean_iou"] == (0.5 + 0.7 + 0.4) / 3


def test_selection_is_robust_first_then_prefers_lower_exposure() -> None:
    first = target_summary(_run(0.55, 0.7, 0.42))
    second = target_summary(_run(0.60, 0.8, 0.41))
    assert selection_key(first, 0.50) > selection_key(second, 0.10)
    assert selection_key(first, 0.10) > selection_key(first, 0.50)


def test_screen_checks_require_each_declared_gain() -> None:
    fallback = target_summary(_run(0.30, 0.25, 0.05))
    specialist = target_summary(_run(0.40, 0.60, 0.30))
    rules = {
        "minimum_early_rice_gain": 0.05,
        "minimum_riceseg_gain": 0.10,
        "minimum_riceseg_reproductive_gain": 0.10,
        "minimum_target_robust_gain": 0.10,
    }
    _, checks = screen_checks(specialist, fallback, rules)
    assert checks == {
        "early_rice_gain": True,
        "riceseg_gain": True,
        "riceseg_reproductive_gain": True,
        "target_robust_gain": True,
    }
