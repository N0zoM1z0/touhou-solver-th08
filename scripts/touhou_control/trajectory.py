"""Game-neutral finite piecewise-linear motion trajectories."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class VelocityChange:
    """Replace velocity before movement on one future update.

    Frame zero is the observed state. A change at frame one therefore affects
    the first projected movement update.
    """

    frame: int
    velocity_x: float
    velocity_y: float

    def __post_init__(self) -> None:
        if self.frame <= 0:
            raise ValueError("velocity changes must occur after frame zero")
        if not math.isfinite(self.velocity_x) or not math.isfinite(
            self.velocity_y
        ):
            raise ValueError("velocity changes must be finite")


@dataclass(frozen=True, order=True)
class CollisionStateChange:
    """Replace a trajectory hazard's collision-enabled state.

    As with :class:`VelocityChange`, frame zero is the observed state and a
    change at frame one applies before the first projected collision query.
    Keeping this independent from motion is important for native mechanics
    such as TH08 callback 12, which changes velocity and collision state in
    one transition.
    """

    frame: int
    collision_enabled: bool

    def __post_init__(self) -> None:
        if self.frame <= 0:
            raise ValueError(
                "collision-state changes must occur after frame zero"
            )


def collision_enabled_at(
    initial: bool,
    changes: tuple[CollisionStateChange, ...],
    frame: int,
) -> bool:
    """Return the collision state after changes through ``frame``."""

    enabled = bool(initial)
    previous = 0
    for change in changes:
        if change.frame <= previous:
            raise ValueError(
                "collision-state change frames must be strictly increasing"
            )
        previous = change.frame
        if change.frame <= frame:
            enabled = change.collision_enabled
    return enabled


@dataclass(frozen=True)
class PiecewiseLinearTrajectory:
    """A point trajectory with finite, time-indexed velocity replacements."""

    x: float
    y: float
    velocity_x: float
    velocity_y: float
    changes: tuple[VelocityChange, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value)
            for value in (self.x, self.y, self.velocity_x, self.velocity_y)
        ):
            raise ValueError("trajectory state must be finite")
        previous = 0
        for change in self.changes:
            if change.frame <= previous:
                raise ValueError(
                    "velocity-change frames must be strictly increasing"
                )
            previous = change.frame

    def position(self, frame: int) -> tuple[float, float]:
        """Return the position after ``frame`` future movement updates."""

        if frame <= 0:
            return (
                self.x + self.velocity_x * frame,
                self.y + self.velocity_y * frame,
            )
        x = self.x + self.velocity_x * frame
        y = self.y + self.velocity_y * frame
        previous_x = self.velocity_x
        previous_y = self.velocity_y
        for change in self.changes:
            if change.frame > frame:
                break
            affected_updates = frame - change.frame + 1
            x += (change.velocity_x - previous_x) * affected_updates
            y += (change.velocity_y - previous_y) * affected_updates
            previous_x = change.velocity_x
            previous_y = change.velocity_y
        return x, y

    def velocity(self, frame: int) -> tuple[float, float]:
        """Return velocity used by movement on the requested future update."""

        velocity_x = self.velocity_x
        velocity_y = self.velocity_y
        if frame <= 0:
            return velocity_x, velocity_y
        for change in self.changes:
            if change.frame > frame:
                break
            velocity_x = change.velocity_x
            velocity_y = change.velocity_y
        return velocity_x, velocity_y
