from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from scripts.build_spot_spray_simulation_video_pairs_v1 import (
    PROJECT_ROOT,
    apply_degraded_capture,
    build_track_proxy,
    encode_semantic_video,
    load_palette,
    probe_video,
    resolve_source_asset,
    semantic_class_map,
    sha256_file,
    trajectory_offsets,
    translate_integer,
    validate_provenance,
    verify_semantic_video_roundtrip,
    verify_track_alignment,
)


CONFIG_PATH = (
    PROJECT_ROOT / "configs/simulation/spot_spray_simulation_video_pairs_v1.yaml"
)


def load_config() -> dict:
    value = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def synthetic_semantic_mask() -> np.ndarray:
    mask = np.zeros((64, 64, 3), dtype=np.uint8)
    mask[7:20, 8:23] = (0, 255, 0)
    mask[32:48, 35:54] = (255, 0, 0)
    mask[55:57, 4:6] = (255, 0, 0)  # deliberately below the track threshold
    return mask


def test_config_is_synthetic_only_and_outcome_agnostic() -> None:
    config = load_config()
    boundary = config["claim_boundary"]
    assert config["status"] == "SYNTHETIC_PAIRED_DIAGNOSTIC_ONLY"
    assert boundary["real_capture"] is False
    assert boundary["field_realism_proven"] is False
    assert boundary["botanical_instance_ground_truth"] is False
    assert boundary["outcome_targeting_forbidden"] is True
    assert config["profiles"]["fixture"]["sequences"][0]["role"] == "val"
    assert {row["role"] for row in config["profiles"]["heldout"]["sequences"]} == {
        "test"
    }


def test_pinned_v12_and_sensor_sources_validate() -> None:
    config = load_config()
    state = validate_provenance(config, PROJECT_ROOT)
    sequence = config["profiles"]["fixture"]["sequences"][0]
    source = resolve_source_asset(sequence, config, state, PROJECT_ROOT)
    assert source.rgb_path.is_file()
    assert source.mask_path.is_file()
    assert source.role == "val"
    declared = json.loads(source.generation_receipt_path.read_text(encoding="utf-8"))
    outputs = {row["path"]: row for row in declared["outputs"]}
    assert sha256_file(source.rgb_path) == outputs["render/images/frame_0001.jpg"][
        "sha256"
    ]
    assert sha256_file(source.mask_path) == outputs["render/masks/frame_0001.png"][
        "sha256"
    ]


def test_track_proxy_is_deterministic_and_semantically_aligned() -> None:
    config = load_config()
    palette = load_palette(config)
    class_map = semantic_class_map(synthetic_semantic_mask(), palette)
    first_mask, first_rows, first_dropped = build_track_proxy(class_map, 8, 16)
    second_mask, second_rows, second_dropped = build_track_proxy(class_map, 8, 16)
    assert np.array_equal(first_mask, second_mask)
    assert first_rows == second_rows
    assert first_dropped == second_dropped == {"crop": 0, "weed": 1}
    assert [row["class_name"] for row in first_rows] == ["crop", "weed"]
    assert all(row["botanical_instance_ground_truth"] is False for row in first_rows)
    assert verify_track_alignment(first_mask, class_map, first_rows)


def test_shared_integer_trajectory_preserves_mask_and_track_alignment() -> None:
    config = load_config()
    palette = load_palette(config)
    source_mask = synthetic_semantic_mask()
    source_class = semantic_class_map(source_mask, palette)
    source_tracks, records, _ = build_track_proxy(source_class, 8, 16)
    translated_mask = translate_integer(source_mask, 5, -3, (0, 0, 0))
    translated_tracks = translate_integer(source_tracks, 5, -3, 0)
    translated_class = semantic_class_map(translated_mask, palette)
    assert verify_track_alignment(translated_tracks, translated_class, records)
    assert set(np.unique(translated_tracks)) == set(np.unique(source_tracks))


def test_fixture_trajectory_is_bounded_and_repeatable() -> None:
    sequence = load_config()["profiles"]["fixture"]["sequences"][0]
    first = trajectory_offsets(sequence)
    second = trajectory_offsets(sequence)
    assert first == second
    assert len(first) == sequence["frame_count"]
    assert len(set(first)) > 1
    assert max(abs(dx) for dx, _ in first) < 32
    assert max(abs(dy) for _, dy in first) <= sequence["trajectory"][
        "y_amplitude_px"
    ]


def test_degraded_capture_is_seeded_rgb_only_and_not_identity() -> None:
    config = load_config()
    condition = config["conditions"]["degraded"]
    pack_root = PROJECT_ROOT / config["provenance"]["sensor_motion_pack"]["root"]
    pack = json.loads((pack_root / "PACK.json").read_text(encoding="utf-8"))
    row = next(item for item in pack["kernel_bank"] if item["kernel_id"] == "psf_00")
    kernel = np.load(pack_root / row["npy"], allow_pickle=False)
    yy, xx = np.indices((96, 96), dtype=np.uint16)
    latent = np.stack(
        ((xx * 3) % 256, (yy * 5) % 256, ((xx + yy) * 7) % 256), axis=2
    ).astype(np.uint8)
    first, first_state = apply_degraded_capture(latent, 2, 6, 710001, condition, kernel)
    second, second_state = apply_degraded_capture(latent, 2, 6, 710001, condition, kernel)
    assert np.array_equal(first, second)
    assert first_state == second_state
    assert not np.array_equal(first, latent)
    assert float(np.sqrt(np.mean((first.astype(float) - latent.astype(float)) ** 2))) > 3


def test_ffv1_semantic_video_roundtrips_losslessly(tmp_path: Path) -> None:
    config = load_config()
    ffmpeg = Path(config["runtime_audit"]["ffmpeg"]["path"])
    ffprobe = Path(config["runtime_audit"]["ffprobe"]["path"])
    if not ffmpeg.is_file() or not ffprobe.is_file():
        pytest.skip("pinned ffmpeg runtime unavailable")
    frames = tmp_path / "frames"
    frames.mkdir()
    expected: list[Path] = []
    source = synthetic_semantic_mask()
    for index, dx in enumerate((-3, 0, 4)):
        path = frames / f"frame_{index:06d}.png"
        Image.fromarray(translate_integer(source, dx, 0, (0, 0, 0))).save(
            path, format="PNG"
        )
        expected.append(path)
    semantic_encoding = config["encoding"]["semantic_video"]
    assert semantic_encoding["container"] == "nut"
    output = tmp_path / f"semantic_first.{semantic_encoding['container']}"
    encode_semantic_video(
        ffmpeg,
        frames,
        output,
        len(expected),
        15,
        semantic_encoding,
    )
    replay = tmp_path / f"semantic_replay.{semantic_encoding['container']}"
    encode_semantic_video(
        ffmpeg,
        frames,
        replay,
        len(expected),
        15,
        semantic_encoding,
    )
    probe = probe_video(ffprobe, output)
    assert probe["width"] == 64
    assert probe["height"] == 64
    assert probe["decoded_frame_count"] == 3
    assert probe["average_frame_rate"] == "15/1"
    assert verify_semantic_video_roundtrip(ffmpeg, output, expected)
    assert sha256_file(output) == sha256_file(replay)
