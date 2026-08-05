import pytest

from scripts.finalize_weedy_rice_uav_gate import validate_duplicate_audit


def duplicate_payload() -> dict:
    return {
        "scope": {"candidate_samples": 734, "reference_samples": 15857},
        "candidate_to_reference_match_count": 0,
        "within_candidate_matches": [
            {"sha256_exact": False, "candidate_split": "train", "reference_split": "train"}
        ],
        "within_candidate_cross_split_match_count": 0,
        "passed": True,
    }


def test_duplicate_gate_allows_same_role_near_frames() -> None:
    checks = validate_duplicate_audit(duplicate_payload(), 734, 15857)

    assert checks["within_candidate_exact_duplicates"] == 0
    assert checks["cross_role_exact_or_near_duplicates"] == 0


def test_duplicate_gate_rejects_exact_duplicates() -> None:
    payload = duplicate_payload()
    payload["within_candidate_matches"][0]["sha256_exact"] = True

    with pytest.raises(ValueError, match="exact duplicates"):
        validate_duplicate_audit(payload, 734, 15857)


def test_duplicate_gate_rejects_cross_role_near_frames() -> None:
    payload = duplicate_payload()
    payload["within_candidate_cross_split_match_count"] = 1

    with pytest.raises(ValueError, match="cross-role"):
        validate_duplicate_audit(payload, 734, 15857)
