from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.acquire_farmbot_soy_unseen import inspect_archive, safe_name
from scripts.select_real_only_recovery import generalist_checks


def test_farmbot_archive_quarantines_only_declared_macos_metadata(tmp_path: Path) -> None:
    archive = tmp_path / "payload.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("dataset/image.jpg", b"image")
        output.writestr("dataset/.DS_Store", b"desktop")
        output.writestr("__MACOSX/dataset/._image.jpg", b"fork")
    config = {
        "gates": {
            "maximum_members": 10,
            "maximum_uncompressed_bytes": 1000,
            "allowed_file_suffixes": [".jpg"],
            "minimum_free_bytes_after_extraction": 0,
        },
        "metadata_quarantine": {
            "path_prefixes": ["__MACOSX/"],
            "basenames": [".DS_Store"],
            "maximum_members": 2,
            "maximum_uncompressed_bytes": 100,
        },
    }
    report = inspect_archive(archive, tmp_path / "out", config)
    assert report["regular_file_count"] == 1
    assert report["quarantined_member_count"] == 2
    assert report["quarantine_reason_counts"] == {
        "publisher_desktop_metadata": 1,
        "publisher_macos_resource_fork": 1,
    }


def test_farmbot_safe_name_rejects_traversal_and_backslashes() -> None:
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        safe_name("../escape.jpg")
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        safe_name("folder\\escape.jpg")


def scored_run(domain_values: dict[str, list[float]], tail: float, target: float) -> dict:
    domains = {}
    for name, values in domain_values.items():
        domains[name] = {
            "field_session_macro": {"mean_iou": sum(values) / len(values)},
            "field_session_units": {
                f"field_{index}": {"mean_iou": value}
                for index, value in enumerate(values)
            },
        }
    return {
        "real_domains": domains,
        "aggregate": {
            "domain_balanced_field_tail_mean_iou": tail,
            "target_like_mean_iou": target,
        },
    }


def generalist_rules() -> dict:
    return {
        "minimum_primary_gain": 0.002,
        "maximum_target_like_macro_regression": 0.010,
        "maximum_lower_tail_regression": 0.015,
        "critical_target_domains": ["cwfid", "sugarbeets2016_holdout"],
        "maximum_critical_domain_regression": 0.030,
        "maximum_fraction_fields_regressing_more_than_0_025": 0.20,
    }


def test_generalist_gate_rewards_broad_gain_without_target_regression() -> None:
    base = scored_run(
        {"cwfid": [0.50], "sugarbeets2016_holdout": [0.50], "breadth": [0.40]},
        tail=0.35,
        target=0.50,
    )
    candidate = scored_run(
        {"cwfid": [0.51], "sugarbeets2016_holdout": [0.50], "breadth": [0.44]},
        tail=0.37,
        target=0.505,
    )
    result = generalist_checks(base, candidate, generalist_rules())
    assert result["deltas"]["generalist_primary"] > 0.002
    assert result["passed"] is True


def test_generalist_gate_rejects_too_many_field_regressions() -> None:
    base = scored_run(
        {
            "cwfid": [0.5, 0.5, 0.5],
            "sugarbeets2016_holdout": [0.5],
            "breadth": [0.4],
        },
        tail=0.35,
        target=0.50,
    )
    candidate = scored_run(
        {
            "cwfid": [0.47, 0.47, 0.60],
            "sugarbeets2016_holdout": [0.51],
            "breadth": [0.50],
        },
        tail=0.36,
        target=0.50,
    )
    result = generalist_checks(base, candidate, generalist_rules())
    assert result["fraction_fields_regressing_more_than_0_025"] == pytest.approx(0.4)
    assert result["checks"]["field_regression_fraction_within_limit"] is False
    assert result["passed"] is False
