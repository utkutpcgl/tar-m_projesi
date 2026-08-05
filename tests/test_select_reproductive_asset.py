from scripts.select_reproductive_asset import aggregate, screen_checks


def test_aggregate_uses_all_domains_for_robust_minimum() -> None:
    values = {
        "source": 0.8,
        "cwfid": 0.6,
        "sorghum_weed": 0.82,
        "cropandweed": 0.7,
        "early_rice": 0.4,
        "riceseg": 0.5,
        "riceseg_reproductive": 0.3,
    }

    result = aggregate(values)

    assert result["robust_mean_iou"] == 0.3
    assert result["riceseg_reproductive_mean_iou"] == 0.3


def test_screen_requires_target_gain_and_existing_noninferiority() -> None:
    delta = {
        "robust_mean_iou": 0.01,
        "macro_mean_iou": 0.001,
        "riceseg_mean_iou": 0.01,
        "riceseg_reproductive_mean_iou": 0.02,
        "source_mean_iou": -0.001,
        "cwfid_mean_iou": 0.0,
        "sorghum_weed_mean_iou": 0.0,
        "cropandweed_mean_iou": -0.02,
        "early_rice_mean_iou": 0.0,
    }
    rules = {
        "robust_mean_iou_delta_must_be_at_least": 0.003,
        "riceseg_mean_iou_delta_must_be_at_least": 0.005,
        "riceseg_reproductive_mean_iou_delta_must_be_at_least": 0.01,
        "macro_mean_iou_delta_must_be_at_least": 0.0,
        "maximum_existing_domain_mean_iou_regression": {
            "source": 0.01,
            "cwfid": 0.01,
            "sorghum_weed": 0.01,
            "cropandweed": 0.01,
            "early_rice": 0.01,
        },
    }

    checks = screen_checks(delta, rules)

    assert checks["riceseg_reproductive_gain"] is True
    assert checks["cropandweed_noninferiority"] is False
