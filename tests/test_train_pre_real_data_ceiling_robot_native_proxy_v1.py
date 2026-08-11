from pathlib import Path

import pytest

from scripts.train_pre_real_data_ceiling_robot_native_proxy_v1 import (
    completed_epochs,
    locked_inputs,
)


def test_locked_inputs_fail_closed_on_missing_config() -> None:
    with pytest.raises(FileNotFoundError):
        locked_inputs(Path("missing-pre-real-data-ceiling-config.yaml"))


def test_completed_epochs_counts_only_data_rows(tmp_path: Path) -> None:
    path = tmp_path / "results.csv"
    path.write_text("epoch,loss\n1,0.5\n2,0.4\n", encoding="utf-8")
    assert completed_epochs(path) == 2
    assert completed_epochs(tmp_path / "missing.csv") == 0
