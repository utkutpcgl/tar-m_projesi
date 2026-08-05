from scripts.select_riceseg_specialist_confirmation import paired_confirmation


def _run(seed: int, early: float, full: float, reproductive: float) -> dict:
    return {
        "seed": seed,
        "artifacts": {
            "early_rice": {"mean_iou": early},
            "riceseg": {"mean_iou": full},
            "riceseg_reproductive": {"mean_iou": reproductive},
        },
    }


def test_paired_confirmation_requires_declared_gains_and_wins() -> None:
    fallback = {
        seed: _run(seed, 0.30, 0.25, 0.05) for seed in (17, 29, 43)
    }
    specialist = {
        seed: _run(seed, 0.42, 0.62, 0.31) for seed in (17, 29, 43)
    }
    rules = {
        "minimum_mean_early_rice_gain": 0.05,
        "minimum_mean_riceseg_gain": 0.10,
        "minimum_mean_riceseg_reproductive_gain": 0.10,
        "minimum_mean_target_robust_gain": 0.10,
        "minimum_target_robust_wins_out_of_3": 3,
    }
    result = paired_confirmation(specialist, fallback, rules)
    assert result["accepted"] is True
    assert result["target_robust_wins"] == 3
    assert all(result["checks"].values())


def test_paired_confirmation_rejects_one_robust_seed_loss() -> None:
    fallback = {
        seed: _run(seed, 0.30, 0.25, 0.20) for seed in (17, 29, 43)
    }
    specialist = {
        17: _run(17, 0.50, 0.60, 0.40),
        29: _run(29, 0.50, 0.60, 0.40),
        43: _run(43, 0.50, 0.60, 0.19),
    }
    rules = {
        "minimum_mean_early_rice_gain": 0.0,
        "minimum_mean_riceseg_gain": 0.0,
        "minimum_mean_riceseg_reproductive_gain": 0.0,
        "minimum_mean_target_robust_gain": 0.0,
        "minimum_target_robust_wins_out_of_3": 3,
    }
    result = paired_confirmation(specialist, fallback, rules)
    assert result["accepted"] is False
    assert result["checks"]["target_robust_seed_wins"] is False
