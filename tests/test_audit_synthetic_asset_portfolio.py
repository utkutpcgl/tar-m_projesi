import pytest

from scripts.audit_synthetic_asset_portfolio import nested_value


def test_nested_value_reads_frozen_json_assertion() -> None:
    assert nested_value({"a": {"b": {"accepted": True}}}, "a.b.accepted") is True


def test_nested_value_rejects_missing_assertion() -> None:
    with pytest.raises(KeyError):
        nested_value({"a": {}}, "a.b.accepted")
