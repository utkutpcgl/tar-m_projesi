from dataclasses import asdict, replace

import torch

from agri_seg.constants import CROP, WEED
from agri_seg.engine import (
    EvaluationAccumulator,
    _validation_selection_key,
    evaluate,
)
from agri_seg.losses import SafetyAwareLoss
from agri_seg.metrics import (
    SafetyCounts,
    ThresholdPoint,
    confusion_matrix,
    metrics_from_confusion,
    select_operating_point,
)
from agri_seg.safety import SafetyPolicy, apply_safety_policy, normalized_entropy


def test_crop_dilation_blocks_neighboring_spray() -> None:
    probabilities = torch.zeros(1, 3, 7, 7)
    probabilities[:, 0] = 0.05
    probabilities[:, CROP, 3, 3] = 0.9
    probabilities[:, WEED] = 0.9
    probabilities[:, WEED, 3, 3] = 0.05
    probabilities /= probabilities.sum(dim=1, keepdim=True)
    decision = apply_safety_policy(
        probabilities,
        SafetyPolicy(
            weed_threshold=0.5,
            crop_threshold=0.5,
            min_confidence=0.0,
            min_margin=0.0,
            max_entropy=1.0,
            crop_dilation_px=1,
        ),
    )
    assert decision["crop_guard"][0, 2:5, 2:5].all()
    assert not decision["safe_weed"][0, 2:5, 2:5].any()


def test_saturated_fp16_entropy_remains_finite() -> None:
    probabilities = torch.tensor(
        [[[[1.0]], [[0.0]], [[0.0]]]], dtype=torch.float16
    )
    entropy = normalized_entropy(probabilities)
    assert torch.isfinite(entropy).all()
    assert entropy.item() == 0.0


def test_safety_counts_distinguish_raw_and_guarded_error() -> None:
    target = torch.tensor([[[CROP, WEED]]])
    probabilities = torch.tensor([[[[0.05, 0.05]], [[0.05, 0.05]], [[0.90, 0.90]]]])
    counts = SafetyCounts()
    counts.update(
        probabilities,
        target,
        SafetyPolicy(
            weed_threshold=0.5,
            crop_threshold=0.99,
            min_confidence=0.0,
            min_margin=0.0,
            max_entropy=1.0,
            crop_dilation_px=0,
        ),
    )
    result = counts.compute()
    assert result["crop_as_weed_rate_raw"] == 1.0
    assert result["crop_spray_risk"] == 1.0
    assert result["safe_weed_recall"] == 1.0


def test_confusion_metrics() -> None:
    target = torch.tensor([[0, 1, 2, 255]])
    prediction = torch.tensor([[0, 2, 2, 1]])
    matrix = confusion_matrix(prediction, target)
    assert matrix.tolist() == [[1, 0, 0], [0, 0, 1], [0, 0, 1]]
    metrics = metrics_from_confusion(matrix)
    assert metrics["iou"]["background"] == 1.0
    assert metrics["recall"]["other_vegetation"] == 1.0


def test_operating_point_obeys_risk_constraint() -> None:
    curve = [
        ThresholdPoint(0.5, 0.02, 0.02, 0.9, 0.1),
        ThresholdPoint(0.8, 0.004, 0.004, 0.6, 0.2),
        ThresholdPoint(0.9, 0.001, 0.001, 0.4, 0.3),
    ]
    selected = select_operating_point(curve, 0.005)
    assert selected.weed_threshold == 0.8


def test_vectorized_evaluation_counts_match_reference_policy() -> None:
    probabilities = torch.tensor(
        [
            [
                [[0.90, 0.05, 0.05, 0.05]],
                [[0.05, 0.90, 0.20, 0.55]],
                [[0.05, 0.05, 0.75, 0.40]],
            ]
        ]
    )
    target = torch.tensor([[[0, CROP, WEED, CROP]]])
    policy = SafetyPolicy(
        crop_threshold=0.8,
        min_confidence=0.0,
        min_margin=0.0,
        max_entropy=1.0,
        crop_dilation_px=0,
    )
    thresholds = [0.35, 0.70]
    accumulator = EvaluationAccumulator(policy, thresholds, 0.005)
    accumulator.update(probabilities, target, "domain")

    for threshold in thresholds:
        expected = SafetyCounts()
        expected.update(
            probabilities, target, replace(policy, weed_threshold=threshold)
        )
        assert asdict(accumulator.counts[threshold]) == asdict(expected)
        assert asdict(accumulator.domain_counts["domain"][threshold]) == asdict(
            expected
        )


def test_threshold_selection_rejects_aggregate_safe_but_tail_unsafe_point(
) -> None:
    policy = SafetyPolicy(
        crop_threshold=0.99,
        min_confidence=0.0,
        min_margin=0.0,
        max_entropy=1.0,
        crop_dilation_px=0,
    )
    accumulator = EvaluationAccumulator(
        policy,
        [0.5, 0.9],
        0.005,
        max_per_image_crop_spray_risk_p99=0.005,
        max_crop_spray_risk_violation_rate=0.01,
    )
    target = torch.full((1, 1, 101), CROP, dtype=torch.long)
    target[:, :, -1] = WEED
    for image_index in range(100):
        probabilities = torch.zeros((1, 3, 1, 101))
        probabilities[:, 0] = 0.05
        probabilities[:, CROP] = 0.90
        probabilities[:, WEED] = 0.05
        probabilities[:, 0, :, -1] = 0.05
        probabilities[:, CROP, :, -1] = 0.15
        probabilities[:, WEED, :, -1] = 0.80
        if image_index < 2:
            probabilities[:, CROP, :, :20] = 0.15
            probabilities[:, WEED, :, :20] = 0.80
        accumulator.update(
            probabilities, target, "domain", crop_id=0
        )

    metrics = accumulator.compute()
    low_threshold = metrics["crop_id_threshold_curves"]["0"][0]
    selected = metrics["selected_operating_point"]
    assert low_threshold["worst_domain_crop_spray_risk"] == 0.004
    assert low_threshold["per_image_crop_spray_risk"]["p99"] == 0.2
    assert low_threshold["per_image_crop_spray_risk"]["violation_rate"] == 0.02
    assert selected["weed_threshold_by_crop_id"] == {"0": 0.9}
    assert metrics["safety_constraint"]["met"] is True


def test_external_dilation_component_and_stratified_metrics() -> None:
    target = torch.tensor(
        [[[CROP, 0, WEED, WEED], [0, 0, 0, 0], [WEED, 0, 0, 0]]]
    )
    prediction = torch.tensor(
        [[[CROP, 0, WEED, 0], [0, 0, 0, 0], [0, 0, 0, 0]]]
    )
    probabilities = torch.full((1, 3, 3, 4), 0.05)
    probabilities.scatter_(1, prediction.unsqueeze(1), 0.90)
    policy = SafetyPolicy(
        weed_threshold=0.5,
        crop_threshold=0.5,
        min_confidence=0.0,
        min_margin=0.0,
        max_entropy=1.0,
        crop_dilation_px=0,
    )
    accumulator = EvaluationAccumulator(
        policy,
        [0.5],
        0.005,
        dilation_sensitivity_radii=[0, 1],
        component_metrics=True,
    )
    accumulator.update(
        probabilities,
        target,
        "capture",
        {"growth_stage": "early", "crop_species": "test"},
    )
    metrics = accumulator.compute()
    assert metrics["strata"]["growth_stage"]["early"]["iou"][
        "other_vegetation"
    ] == 1 / 3
    assert len(metrics["crop_dilation_sensitivity"]) == 2
    components = metrics["weed_component_metrics"]["semantic_argmax"]["large"]
    assert components["components"] == 2
    assert components[
        "component_detection_recall_at_50_percent_coverage"
    ] == 0.5


def test_epoch_selection_is_safety_first_and_lexicographic() -> None:
    def metrics(
        constraint_met: bool,
        risk: float,
        worst_recall: float,
        macro_recall: float,
    ) -> dict[str, object]:
        return {
            "safety_constraint": {"met": constraint_met},
            "worst_domain_weed_iou": 0.4,
            "selected_operating_point": {
                "worst_domain_crop_spray_risk": risk,
                "worst_domain_safe_weed_recall": worst_recall,
                "macro_domain_safe_weed_recall": macro_recall,
                "per_image_crop_spray_risk": {
                    "p99": risk,
                    "violation_rate": 0.0,
                },
                "global": {"unknown_rate": 0.2},
            },
        }

    unsafe_low_risk = _validation_selection_key(
        metrics(False, 0.006, 0.1, 0.2)
    )
    unsafe_high_recall = _validation_selection_key(
        metrics(False, 0.20, 0.9, 0.9)
    )
    assert unsafe_low_risk > unsafe_high_recall
    feasible_early = _validation_selection_key(
        metrics(True, 0.004, 0.0, 0.2)
    )
    feasible_later = _validation_selection_key(
        metrics(True, 0.004, 0.0, 0.8)
    )
    assert feasible_later > feasible_early


def test_flattened_cross_entropy_matches_spatial_reference() -> None:
    torch.manual_seed(17)
    logits = torch.randn(2, 3, 4, 5)
    target = torch.randint(0, 3, (2, 4, 5))
    target[0, 0, 0] = 255
    criterion = SafetyAwareLoss(
        dice_weight=0.0,
        crop_safety_weight=0.0,
    )
    _, parts = criterion(logits, target)
    reference = torch.nn.functional.cross_entropy(
        logits,
        target,
        weight=torch.tensor([0.25, 1.5, 1.0]),
        ignore_index=255,
    )
    torch.testing.assert_close(parts["cross_entropy"], reference)


def test_crop_safety_cvar_penalizes_high_confidence_tail() -> None:
    target = torch.tensor([[[CROP, CROP, CROP, CROP]]])
    logits = torch.tensor(
        [
            [
                [[0.0, 0.0, 0.0, 0.0]],
                [[4.0, 4.0, 4.0, 0.0]],
                [[0.0, 0.0, 0.0, 4.0]],
            ]
        ]
    )
    mean_loss = SafetyAwareLoss(crop_safety_tail_fraction=1.0)
    tail_loss = SafetyAwareLoss(crop_safety_tail_fraction=0.25)
    _, mean_parts = mean_loss(logits, target)
    _, tail_parts = tail_loss(logits, target)
    assert tail_parts["crop_as_weed_tail"] > mean_parts["crop_as_weed_tail"]
    assert tail_parts["crop_as_weed_soft"] == mean_parts["crop_as_weed_soft"]


def test_crop_id_policy_uses_conservative_unknown_fallback() -> None:
    probabilities = torch.tensor(
        [
            [[[0.10]], [[0.15]], [[0.75]]],
            [[[0.10]], [[0.15]], [[0.75]]],
            [[[0.10]], [[0.15]], [[0.75]]],
        ]
    )
    policy = SafetyPolicy(
        weed_threshold=0.95,
        weed_threshold_by_crop_id={0: 0.70, 2: 0.90},
        unknown_crop_weed_threshold=0.95,
        crop_threshold=0.99,
        min_confidence=0.0,
        min_margin=0.0,
        max_entropy=1.0,
        crop_dilation_px=0,
    )
    decisions = apply_safety_policy(
        probabilities, policy, torch.tensor([0, 2, 9])
    )
    assert decisions["safe_weed"][:, 0, 0].tolist() == [True, False, False]


def test_crop_id_calibration_avoids_global_threshold_bottleneck() -> None:
    policy = SafetyPolicy(
        crop_threshold=0.99,
        min_confidence=0.0,
        min_margin=0.0,
        max_entropy=1.0,
        crop_dilation_px=0,
    )
    accumulator = EvaluationAccumulator(policy, [0.5, 0.9], 0.005)
    beet_probabilities = torch.tensor(
        [[[[0.05, 0.30]], [[0.90, 0.10]], [[0.05, 0.60]]]]
    )
    bean_probabilities = torch.tensor(
        [[[[0.10, 0.02]], [[0.10, 0.03]], [[0.80, 0.95]]]]
    )
    target = torch.tensor([[[CROP, WEED]]])
    accumulator.update(
        beet_probabilities, target, "beet-domain", crop_id=0
    )
    accumulator.update(
        bean_probabilities, target, "bean-domain", crop_id=2
    )
    metrics = accumulator.compute()
    selected = metrics["selected_operating_point"]
    assert selected["weed_threshold_by_crop_id"] == {"0": 0.5, "2": 0.9}
    assert selected["unknown_crop_weed_threshold"] == 0.9
    assert selected["worst_domain_crop_spray_risk"] == 0.0
    assert selected["worst_domain_safe_weed_recall"] == 1.0
    assert metrics["threshold_curve"][1][
        "worst_domain_safe_weed_recall"
    ] == 0.0


def test_evaluate_calibrates_unknown_embedding_without_external_tuning() -> None:
    class ConditionedModel(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.crop_embedding = torch.nn.Embedding(5, 1)

        def forward(
            self, images: torch.Tensor, target_crop_id: torch.Tensor
        ) -> torch.Tensor:
            outputs = []
            for crop_id in target_crop_id.tolist():
                if crop_id == 0:
                    probabilities = torch.tensor(
                        [[[0.05, 0.30]], [[0.90, 0.10]], [[0.05, 0.60]]],
                        device=images.device,
                    )
                else:
                    probabilities = torch.tensor(
                        [[[0.10, 0.02]], [[0.10, 0.03]], [[0.80, 0.95]]],
                        device=images.device,
                    )
                outputs.append(probabilities.log())
            return torch.stack(outputs)

    batch = {
        "image": torch.zeros(2, 3, 1, 2),
        "mask": torch.tensor([[[CROP, WEED]], [[CROP, WEED]]]),
        "target_crop_id": torch.tensor([0, 2]),
        "sample_id": ["beet", "bean"],
        "dataset_id": ["source", "source"],
        "group_id": ["beet-domain", "bean-domain"],
        "growth_stage": ["early", "early"],
        "crop_species": ["beet", "bean"],
        "platform": ["ground", "ground"],
        "sensor": ["rgb", "rgb"],
        "valid_size": [(1, 2), (1, 2)],
    }
    metrics = evaluate(
        ConditionedModel(),
        [batch],  # type: ignore[arg-type]
        torch.device("cpu"),
        SafetyPolicy(
            crop_threshold=0.99,
            min_confidence=0.0,
            min_margin=0.0,
            max_entropy=1.0,
            crop_dilation_px=0,
        ),
        [0.5, 0.9],
        0.005,
        use_amp=False,
        calibrate_unknown_crop=True,
        unknown_crop_id=4,
    )
    selected = metrics["selected_operating_point"]
    assert selected["weed_threshold_by_crop_id"] == {"0": 0.5, "2": 0.9}
    assert selected["unknown_crop_weed_threshold"] == 0.9
    assert metrics["unknown_crop_calibration"][
        "uses_unknown_model_embedding"
    ] is True
    assert metrics["safety_constraint"]["met"] is True
