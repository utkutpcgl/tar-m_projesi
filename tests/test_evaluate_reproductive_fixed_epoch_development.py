from pathlib import Path

import pytest

from scripts.evaluate_reproductive_fixed_epoch_development import (
    validate_training_inputs,
)


def test_forbidden_real_rice_dataset_ids_are_explicit() -> None:
    from scripts.evaluate_reproductive_fixed_epoch_development import (
        FORBIDDEN_REAL_RICE_DATASETS,
    )

    assert FORBIDDEN_REAL_RICE_DATASETS == {"rice_seedling_weed", "riceseg"}


def test_training_weight_guard_rejects_riceseg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.evaluate_reproductive_fixed_epoch_development.base.validate_training_inputs",
        lambda config, data_root: Path("unused.csv"),
    )
    monkeypatch.setattr(
        "scripts.evaluate_reproductive_fixed_epoch_development.base.manifest_rows",
        lambda path: [],
    )
    config = {"training": {"dataset_weights": {"core": 0.9, "riceseg": 0.1}}}

    with pytest.raises(ValueError, match="weights contain real Rice"):
        validate_training_inputs(config, Path("/tmp"))
