from scripts.select_real_data_riceseg_additive import aggregate, screen_checks


def test_aggregate_separates_existing_and_expanded_domains() -> None:
    values = {
        "source": 0.8,
        "cwfid": 0.6,
        "riceseg": 0.4,
        "riceseg_reproductive": 0.2,
    }
    result = aggregate(values, ["source", "cwfid"])
    assert result["existing_robust_mean_iou"] == 0.6
    assert result["expanded_robust_mean_iou"] == 0.2


def test_screen_requires_target_gain_and_every_existing_domain() -> None:
    delta = {
        "riceseg_mean_iou": 0.1,
        "riceseg_reproductive_mean_iou": 0.1,
        "existing_robust_mean_iou": 0.01,
        "existing_macro_mean_iou": 0.01,
        "expanded_robust_mean_iou": 0.05,
        "expanded_macro_mean_iou": 0.02,
        "source_mean_iou": 0.0,
        "cwfid_mean_iou": -0.02,
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
    assert checks["riceseg_gain"] is True
    assert checks["cwfid_noninferiority"] is False
