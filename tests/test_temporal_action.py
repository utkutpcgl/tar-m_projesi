import pytest

from agri_seg.temporal_action import ActionObservation, TemporalActionConfirmer


def observation(
    frame: int,
    x: float,
    y: float,
    *,
    weed: float = 0.9,
    crop: float = 0.05,
) -> ActionObservation:
    return ActionObservation(frame, x, y, weed, crop)


def test_one_frame_false_positive_never_fires() -> None:
    tracker = TemporalActionConfirmer(association_radius=10.0)
    assert tracker.update(0, [observation(0, 20.0, 30.0)]) == []
    assert tracker.update(1, []) == []


def test_three_stable_world_observations_fire_once() -> None:
    tracker = TemporalActionConfirmer(
        association_radius=10.0, maximum_point_residual=3.0
    )
    assert tracker.update(0, [observation(0, 100.0, 200.0)]) == []
    assert tracker.update(1, [observation(1, 102.0, 199.0)]) == []
    events = tracker.update(2, [observation(2, 101.0, 201.0)])
    assert len(events) == 1
    assert events[0].x == pytest.approx(101.0)
    assert events[0].y == pytest.approx(200.0)
    assert tracker.update(3, [observation(3, 101.0, 200.0)]) == []
    assert tracker.fired_targets == 1


def test_expired_track_cannot_refire_same_world_target() -> None:
    tracker = TemporalActionConfirmer(
        association_radius=10.0,
        minimum_confirmations=2,
        maximum_frame_gap=1,
    )
    tracker.update(0, [observation(0, 50.0, 60.0)])
    assert len(tracker.update(1, [observation(1, 51.0, 60.0)])) == 1
    assert tracker.update(3, []) == []
    assert tracker.active_tracks == 0
    assert tracker.update(4, [observation(4, 49.0, 61.0)]) == []
    assert tracker.update(5, [observation(5, 50.0, 60.0)]) == []
    assert tracker.fired_targets == 1


def test_crop_guard_vetoes_temporally_consistent_target() -> None:
    tracker = TemporalActionConfirmer(association_radius=10.0)
    tracker.update(0, [observation(0, 10.0, 10.0)])
    tracker.update(1, [observation(1, 11.0, 10.0, crop=0.8)])
    assert tracker.update(2, [observation(2, 10.0, 11.0)]) == []


def test_world_distance_creates_separate_tracks() -> None:
    tracker = TemporalActionConfirmer(
        association_radius=5.0, minimum_confirmations=2
    )
    tracker.update(0, [observation(0, 0.0, 0.0), observation(0, 100.0, 100.0)])
    events = tracker.update(
        1, [observation(1, 1.0, 0.0), observation(1, 99.0, 101.0)]
    )
    assert len(events) == 2
    assert tracker.active_tracks == 2


def test_observation_frame_must_match_update_frame() -> None:
    tracker = TemporalActionConfirmer(association_radius=5.0)
    with pytest.raises(ValueError, match="frame_index"):
        tracker.update(2, [observation(1, 0.0, 0.0)])
