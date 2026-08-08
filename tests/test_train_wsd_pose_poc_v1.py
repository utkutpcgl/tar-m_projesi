from pathlib import Path

import pytest
import yaml

from scripts.train_wsd_pose_poc_v1 import _locked_input, sha256


def test_locked_input_requires_research_only_receipt(tmp_path: Path) -> None:
    dataset = tmp_path / "data.yaml"
    dataset.write_text("path: .\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        '{"quality_gates":{"research_pilot_approved":true,'
        '"production_release_approved":false}}\n',
        encoding="utf-8",
    )
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"weights")
    config = {
        "dataset_yaml": dataset.name,
        "dataset_receipt": receipt.name,
        "dataset_receipt_sha256": sha256(receipt),
        "model": {
            "pretrained_checkpoint": weights.name,
            "pretrained_checkpoint_sha256": sha256(weights),
        },
    }

    assert _locked_input(config, tmp_path) == (dataset, receipt, weights)

    payload = yaml.safe_load("quality_gates: {research_pilot_approved: false, production_release_approved: false}")
    import json

    receipt.write_text(json.dumps(payload), encoding="utf-8")
    config["dataset_receipt_sha256"] = sha256(receipt)
    with pytest.raises(ValueError, match="not approved"):
        _locked_input(config, tmp_path)
