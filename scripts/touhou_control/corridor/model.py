"""Data contracts for game-neutral corridor planning."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..query_survival import SurvivalQueryProblem
from ..trajectory import (
    CollisionStateChange,
    PiecewiseLinearTrajectory,
    collision_enabled_at,
)
from ..viability import (
    ControlAction,
    RobustSafetyValuePolicy,
    RobustViabilityPolicy,
)


@dataclass(frozen=True)
class CorridorBounds:
    left: float
    right: float
    top: float
    bottom: float

    def __post_init__(self) -> None:
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("corridor bounds must have positive area")


@dataclass(frozen=True)
class MovingAabbHazard:
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    half_width: float
    half_height: float
    base_uncertainty: float = 0.0
    uncertainty_per_frame: float = 0.0

    def __post_init__(self) -> None:
        if min(
            self.half_width,
            self.half_height,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        ) < 0.0:
            raise ValueError(
                "hazard dimensions and uncertainty cannot be negative"
            )


@dataclass(frozen=True)
class AabbHazard:
    """One time-indexed axis-aligned hazard sample."""

    x: float
    y: float
    half_width: float
    half_height: float
    base_uncertainty: float = 0.0
    uncertainty_per_frame: float = 0.0

    def __post_init__(self) -> None:
        if min(
            self.half_width,
            self.half_height,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        ) < 0.0:
            raise ValueError(
                "hazard dimensions and uncertainty cannot be negative"
            )


@dataclass(frozen=True)
class AabbTrajectoryHazard:
    """A finite time-indexed AABB trajectory supplied by a game adapter."""

    samples: tuple[AabbHazard | None, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError("AABB trajectory must contain at least one frame")

    def sample(self, frame: int) -> AabbHazard | None:
        if frame < 0 or frame >= len(self.samples):
            return None
        return self.samples[frame]

    def rebase(
        self,
        *,
        offset: int,
        horizon_frames: int,
    ) -> AabbTrajectoryHazard:
        if offset < 0 or horizon_frames < 0:
            raise ValueError("AABB trajectory rebase range is invalid")
        end = offset + horizon_frames + 1
        if end > len(self.samples):
            raise ValueError("AABB trajectory does not cover rebase horizon")
        return AabbTrajectoryHazard(samples=self.samples[offset:end])


@dataclass(frozen=True)
class AnnularSectorTrajectoryHazard:
    """A compact set-valued trajectory of possible disc centers.

    At each frame the possible center lies in the annular sector defined by
    ``minimum_radii``/``maximum_radii`` and the closed continuous angle
    interval.  ``origin_uncertainty`` and ``half_extent_radius`` are radial
    Minkowski inflations; adapters may use them to conservatively contain an
    uncertain origin and a non-circular native collision shape.
    """

    origin_x: float
    origin_y: float
    minimum_angle: float
    maximum_angle: float
    minimum_radii: tuple[float | None, ...]
    maximum_radii: tuple[float | None, ...]
    half_extent_radius: float
    origin_uncertainty: float = 0.0
    base_uncertainty: float = 0.0
    uncertainty_per_frame: float = 0.0

    def __post_init__(self) -> None:
        scalar_values = (
            self.origin_x,
            self.origin_y,
            self.minimum_angle,
            self.maximum_angle,
            self.half_extent_radius,
            self.origin_uncertainty,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        )
        if not all(math.isfinite(value) for value in scalar_values):
            raise ValueError("annular-sector trajectory values must be finite")
        if self.minimum_angle > self.maximum_angle:
            raise ValueError("annular-sector angle interval must be ordered")
        if min(
            self.half_extent_radius,
            self.origin_uncertainty,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        ) < 0.0:
            raise ValueError("annular-sector inflation cannot be negative")
        if (
            not self.minimum_radii
            or len(self.minimum_radii) != len(self.maximum_radii)
        ):
            raise ValueError(
                "annular-sector radius samples must be nonempty and paired"
            )
        for minimum, maximum in zip(
            self.minimum_radii,
            self.maximum_radii,
            strict=True,
        ):
            if (minimum is None) != (maximum is None):
                raise ValueError(
                    "annular-sector radius absence must be paired"
                )
            if minimum is None:
                continue
            assert maximum is not None
            if (
                not math.isfinite(minimum)
                or not math.isfinite(maximum)
                or minimum < 0.0
                or minimum > maximum
            ):
                raise ValueError(
                    "annular-sector radii must be finite, nonnegative, "
                    "and ordered"
                )

    def radial_sample(self, frame: int) -> tuple[float, float] | None:
        if frame < 0 or frame >= len(self.minimum_radii):
            return None
        minimum = self.minimum_radii[frame]
        maximum = self.maximum_radii[frame]
        if minimum is None:
            return None
        assert maximum is not None
        return minimum, maximum

    def rebase(
        self,
        *,
        offset: int,
        horizon_frames: int,
    ) -> AnnularSectorTrajectoryHazard:
        if offset < 0 or horizon_frames < 0:
            raise ValueError("annular-sector rebase range is invalid")
        end = offset + horizon_frames + 1
        if end > len(self.minimum_radii):
            raise ValueError("annular-sector rebase exceeds trajectory")
        return AnnularSectorTrajectoryHazard(
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            minimum_angle=self.minimum_angle,
            maximum_angle=self.maximum_angle,
            minimum_radii=self.minimum_radii[offset:end],
            maximum_radii=self.maximum_radii[offset:end],
            half_extent_radius=self.half_extent_radius,
            origin_uncertainty=self.origin_uncertainty,
            base_uncertainty=self.base_uncertainty,
            uncertainty_per_frame=self.uncertainty_per_frame,
        )


@dataclass(frozen=True)
class PiecewiseAabbHazard:
    """A sparse piecewise-linear AABB trajectory.

    Keeping velocity replacements sparse lets native backends project hazards
    without adapters materializing one Python object per hazard per frame.
    """

    motion: PiecewiseLinearTrajectory
    half_width: float
    half_height: float
    base_uncertainty: float = 0.0
    uncertainty_per_frame: float = 0.0
    collision_enabled: bool = True
    collision_state_changes: tuple[CollisionStateChange, ...] = ()

    def __post_init__(self) -> None:
        if min(
            self.half_width,
            self.half_height,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        ) < 0.0:
            raise ValueError(
                "hazard dimensions and uncertainty cannot be negative"
            )
        collision_enabled_at(
            self.collision_enabled,
            self.collision_state_changes,
            0,
        )

    def sample(self, frame: int) -> AabbHazard | None:
        if frame < 0:
            return None
        if not collision_enabled_at(
            self.collision_enabled,
            self.collision_state_changes,
            frame,
        ):
            return None
        x, y = self.motion.position(frame)
        return AabbHazard(
            x=x,
            y=y,
            half_width=self.half_width,
            half_height=self.half_height,
            base_uncertainty=self.base_uncertainty,
            uncertainty_per_frame=self.uncertainty_per_frame,
        )


@dataclass(frozen=True)
class SegmentHazard:
    origin_x: float
    origin_y: float
    angle: float
    tail: float
    head: float
    half_width: float
    base_uncertainty: float = 0.0
    uncertainty_per_frame: float = 0.0

    def __post_init__(self) -> None:
        if min(
            self.half_width,
            self.base_uncertainty,
            self.uncertainty_per_frame,
        ) < 0.0:
            raise ValueError(
                "segment width and uncertainty cannot be negative"
            )


@dataclass(frozen=True)
class SegmentTrajectoryHazard:
    """A finite time-indexed segment trajectory supplied by a game adapter."""

    samples: tuple[SegmentHazard | None, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError(
                "segment trajectory must contain at least one frame"
            )

    def sample(self, frame: int) -> SegmentHazard | None:
        if frame < 0 or frame >= len(self.samples):
            return None
        return self.samples[frame]


@dataclass(frozen=True)
class CorridorConfig:
    grid_step: float = 8.0
    frames_per_layer: int = 4
    horizon_frames: int = 80
    cardinal_speed: float = 4.0
    diagonal_axis_speed: float = 2.8284270763397217
    player_radius: float = 2.0
    required_clearance: float = 0.0
    preferred_clearance: float = 10.0
    danger_radius: float = 48.0
    boundary_danger_radius: float = 24.0
    preferred_position_weight: float = 0.05

    def __post_init__(self) -> None:
        if self.grid_step <= 0.0:
            raise ValueError("grid step must be positive")
        if self.frames_per_layer <= 0 or self.horizon_frames <= 0:
            raise ValueError("corridor horizon fields must be positive")
        if self.horizon_frames % self.frames_per_layer:
            raise ValueError(
                "horizon must be divisible by frames per layer"
            )
        if min(
            self.cardinal_speed,
            self.diagonal_axis_speed,
            self.player_radius,
            self.danger_radius,
            self.boundary_danger_radius,
        ) < 0.0:
            raise ValueError(
                "corridor speeds and radii cannot be negative"
            )


@dataclass(frozen=True)
class CorridorPoint:
    frame: int
    x: float
    y: float
    clearance: float


@dataclass(frozen=True)
class CorridorPlan:
    reachable: bool
    path: tuple[CorridorPoint, ...]
    bottleneck_clearance: float
    terminal_clearance: float
    lane: str
    gate: CorridorPoint | None
    reason: str
    planning_mode: str = "forward_reachability"
    viability_policy: RobustViabilityPolicy | None = None
    safety_value_policy: RobustSafetyValuePolicy | None = None
    survival_policy: RobustViabilityPolicy | None = None
    survival_query_problem: SurvivalQueryProblem | None = None
    initial_safe_action_count: int = 0
    initial_repair_volume: int = 0
    viability_backend: str | None = None
    viability_grid_step: float | None = None
    solver_timing_ms: tuple[tuple[str, float], ...] = ()

    def waypoint(self, frame: int) -> CorridorPoint:
        if not self.path:
            raise ValueError("unreachable corridor has no waypoint")
        for point in self.path:
            if point.frame >= frame:
                return point
        return self.path[-1]


@dataclass(frozen=True)
class RobustControlSpec:
    actions: tuple[ControlAction, ...]
    delay_frames: tuple[int, ...]
    nominal_delay: int
    active_action: str
    safety_value_horizon_frames: int = 0
    retain_safety_action_values: bool = False
    terminal_viable: np.ndarray | None = None
    survival_labels: bool = False
    retain_query_survival_problem: bool = False
    refinement_grid_steps: tuple[float, ...] = ()
    pre_viability_problem_hook: (
        Callable[[SurvivalQueryProblem], None] | None
    ) = None

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("robust control requires at least one action")
        if self.active_action not in {
            action.name for action in self.actions
        }:
            raise ValueError(
                "active action is absent from robust action set"
            )
        if self.safety_value_horizon_frames < 0:
            raise ValueError("safety-value horizon cannot be negative")
        if (
            any(
                not math.isfinite(step) or step <= 0.0
                for step in self.refinement_grid_steps
            )
            or tuple(
                sorted(set(self.refinement_grid_steps), reverse=True)
            )
            != self.refinement_grid_steps
        ):
            raise ValueError(
                "refinement grid steps must be unique positive descending"
            )
        if self.refinement_grid_steps and self.terminal_viable is not None:
            raise ValueError(
                "adaptive refinement does not yet remap terminal masks"
            )
        if (
            self.pre_viability_problem_hook is not None
            and (
                self.refinement_grid_steps
                or self.terminal_viable is not None
                or not self.retain_query_survival_problem
            )
        ):
            raise ValueError(
                "pre-viability query hooks require one retained, "
                "unrefined policy without an external terminal mask"
            )


__all__ = [
    "AabbHazard",
    "AabbTrajectoryHazard",
    "AnnularSectorTrajectoryHazard",
    "CorridorBounds",
    "CorridorConfig",
    "CorridorPlan",
    "CorridorPoint",
    "MovingAabbHazard",
    "PiecewiseAabbHazard",
    "RobustControlSpec",
    "SegmentHazard",
    "SegmentTrajectoryHazard",
]
