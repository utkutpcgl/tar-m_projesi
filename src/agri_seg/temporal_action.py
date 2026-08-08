"""Minimal world-coordinate temporal confirmation for plant intervention.

Inputs must already be projected from image pixels onto a calibrated ground
plane.  This module deliberately avoids appearance ReID: plants are stationary
targets and robot/camera motion should be handled by geometry upstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class ActionObservation:
    frame_index: int
    x: float
    y: float
    weed_score: float
    crop_guard_score: float


@dataclass(frozen=True)
class FireEvent:
    track_id: int
    frame_index: int
    x: float
    y: float
    confirmations: int
    mean_weed_score: float
    maximum_residual: float


@dataclass
class _Track:
    track_id: int
    observations: list[ActionObservation] = field(default_factory=list)
    fired: bool = False

    @property
    def x(self) -> float:
        return median(item.x for item in self.observations)

    @property
    def y(self) -> float:
        return median(item.y for item in self.observations)

    @property
    def last_frame(self) -> int:
        return self.observations[-1].frame_index

    @property
    def mean_weed_score(self) -> float:
        return sum(item.weed_score for item in self.observations) / len(
            self.observations
        )

    @property
    def maximum_crop_guard_score(self) -> float:
        return max(item.crop_guard_score for item in self.observations)

    @property
    def maximum_residual(self) -> float:
        center_x, center_y = self.x, self.y
        return max(
            math.hypot(item.x - center_x, item.y - center_y)
            for item in self.observations
        )


class TemporalActionConfirmer:
    """Associate stationary targets and emit at most one confirmed fire event."""

    def __init__(
        self,
        *,
        association_radius: float,
        fired_target_suppression_radius: float | None = None,
        minimum_confirmations: int = 3,
        minimum_mean_weed_score: float = 0.80,
        maximum_crop_guard_score: float = 0.20,
        maximum_point_residual: float | None = None,
        maximum_frame_gap: int = 5,
    ) -> None:
        if association_radius <= 0.0:
            raise ValueError("association_radius must be positive")
        if minimum_confirmations < 1:
            raise ValueError("minimum_confirmations must be at least one")
        if maximum_frame_gap < 1:
            raise ValueError("maximum_frame_gap must be at least one")
        self.association_radius = association_radius
        self.fired_target_suppression_radius = (
            association_radius
            if fired_target_suppression_radius is None
            else fired_target_suppression_radius
        )
        if self.fired_target_suppression_radius <= 0.0:
            raise ValueError("fired_target_suppression_radius must be positive")
        self.minimum_confirmations = minimum_confirmations
        self.minimum_mean_weed_score = minimum_mean_weed_score
        self.maximum_crop_guard_score = maximum_crop_guard_score
        self.maximum_point_residual = (
            association_radius / 2.0
            if maximum_point_residual is None
            else maximum_point_residual
        )
        self.maximum_frame_gap = maximum_frame_gap
        self._tracks: dict[int, _Track] = {}
        # Mission-local exclusion memory prevents a plant from being fired on
        # again after its short-lived association track has expired.
        self._fired_locations: list[tuple[float, float]] = []
        self._next_track_id = 1

    @property
    def active_tracks(self) -> int:
        return len(self._tracks)

    @property
    def fired_targets(self) -> int:
        return len(self._fired_locations)

    def _already_fired(self, observation: ActionObservation) -> bool:
        return any(
            math.hypot(observation.x - x, observation.y - y)
            <= self.fired_target_suppression_radius
            for x, y in self._fired_locations
        )

    def _expire(self, frame_index: int) -> None:
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if frame_index - track.last_frame <= self.maximum_frame_gap
        }

    def update(
        self, frame_index: int, observations: Iterable[ActionObservation]
    ) -> list[FireEvent]:
        observations = list(observations)
        if any(item.frame_index != frame_index for item in observations):
            raise ValueError("observation frame_index must equal update frame_index")
        observations = [item for item in observations if not self._already_fired(item)]
        self._expire(frame_index)
        candidates: list[tuple[float, int, int]] = []
        for observation_index, observation in enumerate(observations):
            for track_id, track in self._tracks.items():
                if track.last_frame == frame_index:
                    continue
                distance = math.hypot(observation.x - track.x, observation.y - track.y)
                if distance <= self.association_radius:
                    candidates.append((distance, observation_index, track_id))
        candidates.sort()
        used_observations: set[int] = set()
        used_tracks: set[int] = set()
        for _, observation_index, track_id in candidates:
            if observation_index in used_observations or track_id in used_tracks:
                continue
            self._tracks[track_id].observations.append(observations[observation_index])
            used_observations.add(observation_index)
            used_tracks.add(track_id)
        for observation_index, observation in enumerate(observations):
            if observation_index in used_observations:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = _Track(
                track_id=track_id, observations=[observation]
            )
        events: list[FireEvent] = []
        for track in self._tracks.values():
            if (
                not track.fired
                and len(track.observations) >= self.minimum_confirmations
                and track.mean_weed_score >= self.minimum_mean_weed_score
                and track.maximum_crop_guard_score <= self.maximum_crop_guard_score
                and track.maximum_residual <= self.maximum_point_residual
            ):
                track.fired = True
                self._fired_locations.append((track.x, track.y))
                events.append(
                    FireEvent(
                        track_id=track.track_id,
                        frame_index=frame_index,
                        x=track.x,
                        y=track.y,
                        confirmations=len(track.observations),
                        mean_weed_score=track.mean_weed_score,
                        maximum_residual=track.maximum_residual,
                    )
                )
        return sorted(events, key=lambda item: item.track_id)
