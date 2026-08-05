from pathlib import Path

import numpy as np
import yaml
from PIL import Image

from scripts.finalize_riceseg_quality_gate import decoded_difference


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_quality_gate_quarantines_only_same_train_conflict() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs/data/riceseg_quality_gate_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    contract = config["quality_contract"]

    assert contract["release_samples_preserved"] == 3078
    assert contract["eligible_samples"] == 3077
    assert contract["eligible_roles"] == {
        "train": 2473,
        "external_calibration": 604,
    }
    assert contract["candidate_to_reference_matches"] == 0
    assert contract["cross_split_matches"] == 0
    assert contract["allowed_same_split_matches"] == 1
    assert (
        contract["allowed_same_split_pair"]["quarantine_sample"]
        == "riceseg:JS_2:21js2_subset_overlap_0_0"
    )


def test_decoded_difference_reports_content_not_container_bytes(tmp_path: Path) -> None:
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    Image.fromarray(np.array([[0, 1], [1, 2]], dtype=np.uint8)).save(left)
    Image.fromarray(np.array([[0, 1], [2, 2]], dtype=np.uint8)).save(right)

    result = decoded_difference(left, right, "L")

    assert result == {
        "array_equal": False,
        "max_abs": 1,
        "mae": 0.25,
        "different_values": 1,
        "total_values": 4,
    }
