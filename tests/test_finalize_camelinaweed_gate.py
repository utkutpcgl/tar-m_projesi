import pytest

from scripts.finalize_camelinaweed_gate import validate_duplicate_audit


def duplicate_fixture() -> dict[str, object]:
    return {
        "scope": {"candidate_samples": 10, "reference_samples": 20},
        "candidate_to_reference_match_count": 0,
        "candidate_to_reference_nearest_hamming": {"min": 12, "median": 20, "max": 30},
        "within_candidate_match_count": 1,
        "within_candidate_cross_split_match_count": 0,
        "within_candidate_matches": [
            {"sha256_exact": False, "candidate_split": "train", "reference_split": "train"}
        ],
        "passed": True,
    }


def test_duplicate_gate_allows_reported_same_role_near_pair() -> None:
    checks = validate_duplicate_audit(duplicate_fixture(), 10, 20)

    assert checks["audit_passed"] is True
    assert checks["within_candidate_near_pairs"] == 1
    assert checks["within_candidate_exact_duplicates"] == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("candidate_to_reference_match_count", 1),
        ("within_candidate_cross_split_match_count", 1),
        ("passed", False),
    ],
)
def test_duplicate_gate_rejects_leakage(key: str, value: object) -> None:
    audit = duplicate_fixture()
    audit[key] = value
    with pytest.raises(ValueError):
        validate_duplicate_audit(audit, 10, 20)
