from pathlib import Path

import pytest

from scripts.train_phenobench_cropcraft_deploy_ab_v1 import ARMS, locked_inputs


def test_ab_training_arms_are_exactly_control_and_challenger() -> None:
    assert ARMS == ("control_real_replay", "challenger_real_synthetic")


def test_locked_inputs_rejects_unknown_arm() -> None:
    with pytest.raises(ValueError, match="Unknown arm"):
        locked_inputs(Path("missing.yaml"), "not_an_arm")
