from scripts.select_real_data_riceseg_additive import screen_checks


def test_exact_replay_screen_keeps_per_domain_noninferiority() -> None:
    delta = {
        "riceseg_mean_iou": 0.3,
        "riceseg_reproductive_mean_iou": 0.2,
        "existing_robust_mean_iou": 0.01,
        "existing_macro_mean_iou": 0.01,
        "expanded_robust_mean_iou": 0.1,
        "expanded_macro_mean_iou": 0.1,
        "source_mean_iou": 0.0,
        "cwfid_mean_iou": -0.011,
    }
    rules = {
        "riceseg_mean_iou_delta_must_be_at_least": 0.02,
        "riceseg_reproductive_mean_iou_delta_must_be_at_least": 0.01,
        "existing_robust_delta_must_be_at_least": 0.0,
        "existing_macro_delta_must_be_at_least": 0.0,
        "expanded_robust_delta_must_be_at_least": 0.01,
        "expanded_macro_delta_must_be_at_least": 0.0,
        "maximum_existing_domain_mean_iou_regression": {
            "source": 0.01,
            "cwfid": 0.01,
        },
    }
    checks = screen_checks(delta, rules)
    assert checks["cwfid_noninferiority"] is False
