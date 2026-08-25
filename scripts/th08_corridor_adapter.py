#!/usr/bin/env python3
"""Lower live TH08 projectile snapshots into the neutral corridor planner."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from corridor_planner import (
    CorridorBounds,
    CorridorConfig,
    CorridorPlan,
    MovingAabbHazard,
    PiecewiseAabbHazard,
    RobustControlSpec,
    SegmentHazard,
    SegmentTrajectoryHazard,
    plan_corridor,
    plan_prepared_corridor,
)
from th08_bullet_template_contract import bullet_template_profile
from th08_laser_model import (
    LaserState,
    laser_collision_geometry_frames,
)
from th08_movement_model import ROUTE2_MOVEMENT_PROFILE
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS
from touhou_control.corridor import (
    AabbTrajectoryHazard,
    AnnularSectorTrajectoryHazard,
    PreparedCorridorProblem,
    prepare_corridor_problem,
)
from touhou_control.packed_hazards import PackedSegmentFrames
from touhou_control.query_survival import SurvivalQueryProblem
from touhou_control.viability import ControlAction
from touhou_control.trajectory import (
    CollisionStateChange,
    PiecewiseLinearTrajectory,
    VelocityChange,
    collision_enabled_at,
)


class BulletSnapshot(Protocol):
    x: float
    y: float
    vx: float
    vy: float
    half_width: float
    half_height: float
    transform_flags: int
    callback_aux_state: int
    velocity_changes: tuple[VelocityChange, ...]
    collision_state_changes: tuple[CollisionStateChange, ...]
    trajectory_uncertainty_x: float
    trajectory_uncertainty_y: float
    native_state: int
    native_state_timer_elapsed: int
    bullet_type: int | None


class LaserSnapshot(Protocol):
    origin_x: float
    origin_y: float
    angle: float
    tail: float
    head: float
    half_width: float
    state: LaserState | None
    uncertainty: float


class EnemyBodySnapshot(Protocol):
    x: float
    y: float
    vx: float
    vy: float
    half_width: float
    half_height: float
    uncertainty: float


TH08_PLAYFIELD = CorridorBounds(8.0, 376.0, 16.0, 432.0)
TH08_CORRIDOR_BULLET_SEMANTICS_VERSION = (
    "th08-corridor-bullet-v2-native-spawn-lifecycle-callback-schedule"
)
TH08_CORRIDOR_GRID_STEP = 16.0
TH08_CORRIDOR_CELL_RADIUS = (
    math.sqrt(2.0) * TH08_CORRIDOR_GRID_STEP / 2.0
)
TH08_CORRIDOR_CONFIG = CorridorConfig(
    # Each Boolean state represents the complete nearest-lattice cell, not
    # only its center. Euclidean clearance is 1-Lipschitz, so inflating the
    # required clearance by the 16px cell's half diagonal makes membership a
    # conservative continuous-position lower kernel. Fresh local geometry
    # may narrow this exact set but may never widen it.
    grid_step=TH08_CORRIDOR_GRID_STEP,
    frames_per_layer=8,
    horizon_frames=80,
    cardinal_speed=4.0,
    diagonal_axis_speed=2.8284270763397217,
    player_radius=2.0,
    required_clearance=TH08_CORRIDOR_CELL_RADIUS,
    preferred_clearance=10.0,
    danger_radius=48.0,
    boundary_danger_radius=24.0,
)

_DIRECTION_VECTORS = (
    ("left", -1.0, 0.0),
    ("right", 1.0, 0.0),
    ("up", 0.0, -1.0),
    ("down", 0.0, 1.0),
    ("up_left", -1.0, -1.0),
    ("up_right", 1.0, -1.0),
    ("down_left", -1.0, 1.0),
    ("down_right", 1.0, 1.0),
)


def _route2_control_action(
    name: str,
    unit_x: float,
    unit_y: float,
    *,
    focused: bool,
) -> ControlAction:
    diagonal = unit_x != 0.0 and unit_y != 0.0
    profile = ROUTE2_MOVEMENT_PROFILE
    if focused:
        speed = (
            profile.focused_diagonal_axis
            if diagonal
            else profile.focused_cardinal
        )
    else:
        speed = (
            profile.unfocused_diagonal_axis
            if diagonal
            else profile.unfocused_cardinal
        )
    return ControlAction(name, unit_x * speed, unit_y * speed)


TH08_VIABILITY_ACTIONS = (
    ControlAction("stay", 0.0, 0.0),
    *(
        _route2_control_action(name, unit_x, unit_y, focused=True)
        for name, unit_x, unit_y in _DIRECTION_VECTORS
    ),
    *(
        _route2_control_action(
            f"{name}_fast",
            unit_x,
            unit_y,
            focused=False,
        )
        for name, unit_x, unit_y in _DIRECTION_VECTORS
    ),
)


@dataclass(frozen=True)
class LoweredCorridorHazards:
    """Game-neutral hazards projected from one native TH08 snapshot."""

    aabbs: tuple[MovingAabbHazard, ...]
    piecewise_aabbs: tuple[PiecewiseAabbHazard, ...]
    segment_trajectories: tuple[SegmentTrajectoryHazard, ...]
    aabb_trajectories: tuple[AabbTrajectoryHazard, ...] = ()
    annular_sector_trajectories: tuple[
        AnnularSectorTrajectoryHazard, ...
    ] = ()
    packed_segments: PackedSegmentFrames | None = None


@dataclass(frozen=True)
class _NativeBulletTrajectory:
    motion: PiecewiseLinearTrajectory
    collision_enabled: bool
    collision_state_changes: tuple[CollisionStateChange, ...]


def _spawn_lifecycle_parameters(
    bullet: BulletSnapshot,
) -> tuple[int, float] | None:
    state = int(bullet.native_state)
    if state == 1:
        return None
    if state == 5:
        return (0, 1.0)
    if state not in (2, 3, 4):
        raise ValueError(f"unsupported native bullet state {state}")
    if bullet.bullet_type is None:
        raise ValueError(
            "native spawn lifecycle requires a source template type"
        )
    profile = bullet_template_profile(int(bullet.bullet_type))
    if state == 2:
        terminal_age = profile.state2_terminal_age
        divisor = 2.0
    elif state == 3:
        terminal_age = profile.state3_terminal_age
        divisor = 2.5
    else:
        terminal_age = profile.state4_terminal_age
        divisor = 3.0
    timer = int(bullet.native_state_timer_elapsed)
    if timer < 0 or timer >= terminal_age:
        raise ValueError(
            "native spawn lifecycle timer exceeds its source script"
        )
    return terminal_age - timer, divisor


def _native_bullet_trajectory(
    bullet: BulletSnapshot,
    *,
    horizon_frames: int,
) -> _NativeBulletTrajectory | None:
    """Compose spawn lifecycle and callback schedules in update order."""

    lifecycle = _spawn_lifecycle_parameters(bullet)
    if int(bullet.native_state) == 5:
        return None

    # Constructing the ordinary trajectories first validates strict source
    # frame order before lifecycle boundaries are merged into them.
    native_motion = PiecewiseLinearTrajectory(
        bullet.x,
        bullet.y,
        bullet.vx,
        bullet.vy,
        bullet.velocity_changes,
    )
    collision_enabled_at(
        bullet.callback_aux_state == 0,
        bullet.collision_state_changes,
        horizon_frames,
    )
    if lifecycle is None:
        return _NativeBulletTrajectory(
            motion=native_motion,
            collision_enabled=bullet.callback_aux_state == 0,
            collision_state_changes=bullet.collision_state_changes,
        )

    activation_frame, divisor = lifecycle

    def motion_multiplier(frame: int) -> float:
        if frame < activation_frame:
            return 1.0 / divisor
        if frame == activation_frame:
            # The terminal manager update performs the divided spawn step and
            # then the ordinary full step in the same call.
            return 1.0 + 1.0 / divisor
        return 1.0

    motion_boundaries = {
        change.frame
        for change in bullet.velocity_changes
        if change.frame <= horizon_frames
    }
    if activation_frame <= horizon_frames:
        motion_boundaries.add(activation_frame)
    if activation_frame + 1 <= horizon_frames:
        motion_boundaries.add(activation_frame + 1)
    native_velocity_x = float(bullet.vx)
    native_velocity_y = float(bullet.vy)
    multiplier = motion_multiplier(1)
    effective_velocity_x = native_velocity_x * multiplier
    effective_velocity_y = native_velocity_y * multiplier
    effective_changes: list[VelocityChange] = []
    velocity_changes = iter(bullet.velocity_changes)
    next_velocity_change = next(velocity_changes, None)
    for frame in sorted(motion_boundaries):
        while (
            next_velocity_change is not None
            and next_velocity_change.frame == frame
        ):
            native_velocity_x = next_velocity_change.velocity_x
            native_velocity_y = next_velocity_change.velocity_y
            next_velocity_change = next(velocity_changes, None)
        multiplier = motion_multiplier(frame)
        next_effective_x = native_velocity_x * multiplier
        next_effective_y = native_velocity_y * multiplier
        if (
            next_effective_x != effective_velocity_x
            or next_effective_y != effective_velocity_y
        ):
            effective_changes.append(
                VelocityChange(
                    frame,
                    next_effective_x,
                    next_effective_y,
                )
            )
            effective_velocity_x = next_effective_x
            effective_velocity_y = next_effective_y

    callback_collision_enabled = bullet.callback_aux_state == 0
    effective_collision_enabled = False
    effective_collision_changes: list[CollisionStateChange] = []
    collision_boundaries = {
        change.frame
        for change in bullet.collision_state_changes
        if change.frame <= horizon_frames
    }
    if activation_frame <= horizon_frames:
        collision_boundaries.add(activation_frame)
    collision_changes = iter(bullet.collision_state_changes)
    next_collision_change = next(collision_changes, None)
    for frame in sorted(collision_boundaries):
        while (
            next_collision_change is not None
            and next_collision_change.frame == frame
        ):
            callback_collision_enabled = (
                next_collision_change.collision_enabled
            )
            next_collision_change = next(collision_changes, None)
        next_enabled = (
            frame >= activation_frame and callback_collision_enabled
        )
        if next_enabled != effective_collision_enabled:
            effective_collision_changes.append(
                CollisionStateChange(frame, next_enabled)
            )
            effective_collision_enabled = next_enabled

    return _NativeBulletTrajectory(
        motion=PiecewiseLinearTrajectory(
            bullet.x,
            bullet.y,
            velocity_x=(
                float(bullet.vx) * motion_multiplier(1)
            ),
            velocity_y=(
                float(bullet.vy) * motion_multiplier(1)
            ),
            changes=tuple(effective_changes),
        ),
        collision_enabled=False,
        collision_state_changes=tuple(effective_collision_changes),
    )


def lower_bullets(
    bullets: tuple[BulletSnapshot, ...],
    *,
    snapshot_lag: int,
    forecast_frames: int = 0,
) -> tuple[MovingAabbHazard, ...]:
    lag = max(0, snapshot_lag)
    forecast = max(0, forecast_frames)
    read_uncertainty = 0.2 * math.sqrt(lag)
    hazards = []
    for bullet in bullets:
        native_state = int(bullet.native_state)
        if native_state == 5:
            continue
        if native_state not in (1, 2, 3, 4):
            raise ValueError(f"unsupported native bullet state {native_state}")
        if native_state != 1:
            # Spawn-ANM motion and lethal activation are lowered by the
            # piecewise path below.
            continue
        if bullet.velocity_changes or bullet.collision_state_changes:
            continue
        if bullet.callback_aux_state != 0:
            continue
        growth = 0.35 if bullet.transform_flags else 0.05
        hazards.append(
            MovingAabbHazard(
                x=bullet.x + bullet.vx * (lag + forecast),
                y=bullet.y + bullet.vy * (lag + forecast),
                velocity_x=bullet.vx,
                velocity_y=bullet.vy,
                half_width=bullet.half_width,
                half_height=bullet.half_height,
                base_uncertainty=(
                    read_uncertainty
                    + max(
                        bullet.trajectory_uncertainty_x,
                        bullet.trajectory_uncertainty_y,
                    )
                    + (3.0 if bullet.transform_flags else 0.0)
                    + growth * forecast
                ),
                uncertainty_per_frame=growth,
            )
        )
    return tuple(hazards)


def lower_bullet_trajectories(
    bullets: tuple[BulletSnapshot, ...],
    *,
    snapshot_lag: int,
    forecast_frames: int = 0,
    horizon_frames: int = TH08_CORRIDOR_CONFIG.horizon_frames,
) -> tuple[PiecewiseAabbHazard, ...]:
    """Lower event-driven bullets without dense per-frame materialization."""

    if horizon_frames < 0:
        raise ValueError("bullet trajectory horizon cannot be negative")
    lag = max(0, snapshot_lag)
    forecast = max(0, forecast_frames)
    read_uncertainty = 0.2 * math.sqrt(lag)
    trajectories: list[PiecewiseAabbHazard] = []
    for bullet in bullets:
        native_state = int(bullet.native_state)
        if native_state == 5:
            continue
        if (
            native_state == 1
            and not bullet.velocity_changes
            and not bullet.collision_state_changes
        ):
            continue
        elapsed = lag + forecast
        projected = _native_bullet_trajectory(
            bullet,
            horizon_frames=elapsed + horizon_frames,
        )
        if projected is None:
            continue
        motion = projected.motion
        projected_x, projected_y = motion.position(elapsed)
        projected_velocity_x, projected_velocity_y = motion.velocity(elapsed)
        remaining_changes = tuple(
            VelocityChange(
                change.frame - elapsed,
                change.velocity_x,
                change.velocity_y,
            )
            for change in motion.changes
            if change.frame > elapsed
            and change.frame - elapsed <= horizon_frames
        )
        remaining_collision_changes = tuple(
            CollisionStateChange(
                change.frame - elapsed,
                change.collision_enabled,
            )
            for change in projected.collision_state_changes
            if change.frame > elapsed
            and change.frame - elapsed <= horizon_frames
        )
        projected_collision_enabled = collision_enabled_at(
            projected.collision_enabled,
            projected.collision_state_changes,
            elapsed,
        )
        if not projected_collision_enabled and not remaining_collision_changes:
            continue
        growth = 0.35 if bullet.transform_flags else 0.05
        trajectories.append(
            PiecewiseAabbHazard(
                motion=PiecewiseLinearTrajectory(
                    projected_x,
                    projected_y,
                    projected_velocity_x,
                    projected_velocity_y,
                    remaining_changes,
                ),
                half_width=(
                    bullet.half_width
                    + bullet.trajectory_uncertainty_x
                ),
                half_height=(
                    bullet.half_height
                    + bullet.trajectory_uncertainty_y
                ),
                base_uncertainty=(
                    read_uncertainty
                    + (3.0 if bullet.transform_flags else 0.0)
                    + growth * forecast
                ),
                uncertainty_per_frame=growth,
                collision_enabled=projected_collision_enabled,
                collision_state_changes=remaining_collision_changes,
            )
        )
    return tuple(trajectories)


def lower_lasers(
    lasers: tuple[LaserSnapshot, ...],
    *,
    snapshot_lag: int,
    forecast_frames: int = 0,
    horizon_frames: int = TH08_CORRIDOR_CONFIG.horizon_frames,
    time_scale_schedule_bits: tuple[int, ...] | None = None,
) -> tuple[SegmentTrajectoryHazard, ...]:
    lag = max(0, snapshot_lag)
    forecast = max(0, forecast_frames)
    if horizon_frames < 0:
        raise ValueError("laser trajectory horizon cannot be negative")
    total_frames = lag + forecast + horizon_frames + 1
    if time_scale_schedule_bits is None:
        time_scale_schedule_bits = (
            TH08_UNIT_TIME_SCALE_BITS,
        ) * total_frames
    if len(time_scale_schedule_bits) < total_frames:
        raise ValueError(
            "laser time-scale schedule does not cover corridor lowering"
        )
    trajectories: list[SegmentTrajectoryHazard] = []
    for laser in lasers:
        state = laser.state
        if state is None:
            sample = SegmentHazard(
                origin_x=laser.origin_x,
                origin_y=laser.origin_y,
                angle=laser.angle,
                tail=laser.tail,
                head=laser.head,
                half_width=laser.half_width,
                base_uncertainty=(
                    laser.uncertainty
                    + min(12.0, 0.4 * lag)
                    + 0.4 * forecast
                ),
                uncertainty_per_frame=0.4,
            )
            trajectories.append(
                SegmentTrajectoryHazard((sample,) * (horizon_frames + 1))
            )
            continue
        geometry_frames = laser_collision_geometry_frames(
            state,
            frame_count=total_frames,
            time_scale_schedule_bits=(
                time_scale_schedule_bits[:total_frames]
            ),
        )[lag + forecast:]
        per_frame = [
            tuple(
                (
                    SegmentHazard(
                        origin_x=state.origin_x,
                        origin_y=state.origin_y,
                        angle=state.angle,
                        tail=tail,
                        head=head,
                        half_width=half_width,
                        # The reverse-engineered lifecycle is stepped to the
                        # exact target frame. Retain measured read uncertainty
                        # without inventing horizon-dependent model drift.
                        base_uncertainty=laser.uncertainty,
                    )
                )
                for tail, head, half_width in geometry
            )
            for frame, geometry in enumerate(geometry_frames)
        ]
        for check_index in range(max(map(len, per_frame), default=0)):
            trajectories.append(
                SegmentTrajectoryHazard(
                    tuple(
                        (
                            frame_segments[check_index]
                            if check_index < len(frame_segments)
                            else None
                        )
                        for frame_segments in per_frame
                    )
                )
            )
    return tuple(trajectories)


def lower_lasers_packed(
    lasers: tuple[LaserSnapshot, ...],
    *,
    snapshot_lag: int,
    forecast_frames: int = 0,
    horizon_frames: int = TH08_CORRIDOR_CONFIG.horizon_frames,
    time_scale_schedule_bits: tuple[int, ...] | None = None,
) -> PackedSegmentFrames:
    """Lower laser geometry directly into the native frame-major contract."""

    if horizon_frames < 0:
        raise ValueError("laser trajectory horizon cannot be negative")
    lag = max(0, snapshot_lag)
    forecast = max(0, forecast_frames)
    total_frames = lag + forecast + horizon_frames + 1
    if time_scale_schedule_bits is None:
        time_scale_schedule_bits = (
            TH08_UNIT_TIME_SCALE_BITS,
        ) * total_frames
    if len(time_scale_schedule_bits) < total_frames:
        raise ValueError(
            "laser time-scale schedule does not cover packed corridor lowering"
        )
    frames: list[list[tuple[float, ...]]] = [
        [] for _ in range(horizon_frames + 1)
    ]
    for laser in lasers:
        state = laser.state
        if state is None:
            row = (
                laser.origin_x,
                laser.origin_y,
                laser.angle,
                laser.tail,
                laser.head,
                laser.half_width,
                (
                    laser.uncertainty
                    + min(12.0, 0.4 * lag)
                    + 0.4 * forecast
                ),
                0.4,
            )
            for frame_rows in frames:
                frame_rows.append(row)
            continue
        geometry_frames = laser_collision_geometry_frames(
            state,
            frame_count=total_frames,
            time_scale_schedule_bits=(
                time_scale_schedule_bits[:total_frames]
            ),
        )[lag + forecast:]
        for frame_rows, geometry in zip(frames, geometry_frames):
            frame_rows.extend(
                (
                    state.origin_x,
                    state.origin_y,
                    state.angle,
                    tail,
                    head,
                    half_width,
                    laser.uncertainty,
                    0.0,
                )
                for tail, head, half_width in geometry
            )
    return PackedSegmentFrames.from_frame_rows(frames)


def lower_enemy_bodies(
    bodies: tuple[EnemyBodySnapshot, ...],
    *,
    snapshot_lag: int,
    forecast_frames: int = 0,
) -> tuple[MovingAabbHazard, ...]:
    lag = max(0, snapshot_lag)
    forecast = max(0, forecast_frames)
    return tuple(
        MovingAabbHazard(
            x=body.x + body.vx * (lag + forecast),
            y=body.y + body.vy * (lag + forecast),
            velocity_x=body.vx,
            velocity_y=body.vy,
            half_width=body.half_width,
            half_height=body.half_height,
            base_uncertainty=(
                body.uncertainty
                + 0.5 * math.sqrt(lag)
                + 0.5 * forecast
            ),
            uncertainty_per_frame=0.5,
        )
        for body in bodies
    )


def lower_th08_corridor_hazards(
    *,
    bullets: tuple[BulletSnapshot, ...],
    lasers: tuple[LaserSnapshot, ...],
    enemy_bodies: tuple[EnemyBodySnapshot, ...] = (),
    snapshot_lag: int = 0,
    forecast_frames: int = 0,
    horizon_frames: int = TH08_CORRIDOR_CONFIG.horizon_frames,
    laser_time_scale_bits: tuple[int, ...] | None = None,
    future_aabb_trajectories: tuple[AabbTrajectoryHazard, ...] = (),
    future_annular_sector_trajectories: tuple[
        AnnularSectorTrajectoryHazard, ...
    ] = (),
) -> LoweredCorridorHazards:
    """Lower one TH08 sensor epoch without constructing a planner policy."""

    return LoweredCorridorHazards(
        aabbs=(
            lower_bullets(
                bullets,
                snapshot_lag=snapshot_lag,
                forecast_frames=forecast_frames,
            )
            + lower_enemy_bodies(
                enemy_bodies,
                snapshot_lag=snapshot_lag,
                forecast_frames=forecast_frames,
            )
        ),
        piecewise_aabbs=lower_bullet_trajectories(
            bullets,
            snapshot_lag=snapshot_lag,
            forecast_frames=forecast_frames,
            horizon_frames=horizon_frames,
        ),
        segment_trajectories=(),
        aabb_trajectories=future_aabb_trajectories,
        annular_sector_trajectories=future_annular_sector_trajectories,
        packed_segments=lower_lasers_packed(
            lasers,
            snapshot_lag=snapshot_lag,
            forecast_frames=forecast_frames,
            horizon_frames=horizon_frames,
            time_scale_schedule_bits=laser_time_scale_bits,
        ),
    )


def _th08_robust_control_spec(
    *,
    control_delay_candidates: tuple[int, ...],
    nominal_control_delay: int,
    active_action: str,
    safety_value_horizon_frames: int,
    retain_safety_action_values: bool,
    terminal_viable: np.ndarray | None,
    survival_labels: bool,
    retain_query_survival_problem: bool,
    refinement_grid_steps: tuple[float, ...],
    pre_viability_problem_hook: (
        Callable[[SurvivalQueryProblem], None] | None
    ) = None,
) -> RobustControlSpec:
    return RobustControlSpec(
        actions=TH08_VIABILITY_ACTIONS,
        delay_frames=control_delay_candidates,
        nominal_delay=nominal_control_delay,
        active_action=active_action,
        safety_value_horizon_frames=safety_value_horizon_frames,
        retain_safety_action_values=retain_safety_action_values,
        terminal_viable=terminal_viable,
        survival_labels=survival_labels,
        retain_query_survival_problem=retain_query_survival_problem,
        refinement_grid_steps=refinement_grid_steps,
        pre_viability_problem_hook=pre_viability_problem_hook,
    )


def _prepare_lowered_th08_corridor_with_control(
    *,
    hazards: LoweredCorridorHazards,
    config: CorridorConfig,
    robust_control: RobustControlSpec,
) -> PreparedCorridorProblem:
    return prepare_corridor_problem(
        bounds=TH08_PLAYFIELD,
        config=config,
        robust_control=robust_control,
        aabbs=hazards.aabbs,
        piecewise_aabbs=hazards.piecewise_aabbs,
        aabb_trajectories=hazards.aabb_trajectories,
        annular_sector_trajectories=hazards.annular_sector_trajectories,
        segment_trajectories=hazards.segment_trajectories,
        packed_segments=hazards.packed_segments,
    )


def prepare_lowered_th08_corridor(
    *,
    hazards: LoweredCorridorHazards,
    config: CorridorConfig = TH08_CORRIDOR_CONFIG,
    control_delay_candidates: tuple[int, ...],
    nominal_control_delay: int,
    active_action: str = "stay",
    safety_value_horizon_frames: int = 0,
    retain_safety_action_values: bool = False,
    terminal_viable: np.ndarray | None = None,
    survival_labels: bool = False,
    retain_query_survival_problem: bool = False,
    refinement_grid_steps: tuple[float, ...] = (),
) -> PreparedCorridorProblem:
    """Prepare one TH08 robust problem without starting runtime services."""

    robust_control = _th08_robust_control_spec(
        control_delay_candidates=control_delay_candidates,
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        safety_value_horizon_frames=safety_value_horizon_frames,
        retain_safety_action_values=retain_safety_action_values,
        terminal_viable=terminal_viable,
        survival_labels=survival_labels,
        retain_query_survival_problem=retain_query_survival_problem,
        refinement_grid_steps=refinement_grid_steps,
    )
    return _prepare_lowered_th08_corridor_with_control(
        hazards=hazards,
        config=config,
        robust_control=robust_control,
    )


def plan_prepared_lowered_th08_corridor(
    *,
    player_x: float,
    player_y: float,
    prepared_problem: PreparedCorridorProblem,
    preferred_x: float = 192.0,
    preferred_y: float = 368.0,
    required_gate_lane: str | None = None,
    pre_viability_elapsed_ms: float = 0.0,
) -> CorridorPlan:
    """Solve an explicitly prepared TH08 robust corridor problem."""

    return plan_prepared_corridor(
        start_x=player_x,
        start_y=player_y,
        prepared_problem=prepared_problem,
        preferred_x=preferred_x,
        preferred_y=preferred_y,
        required_gate_lane=required_gate_lane,
        pre_viability_elapsed_ms=pre_viability_elapsed_ms,
    )


def plan_lowered_th08_corridor(
    *,
    player_x: float,
    player_y: float,
    hazards: LoweredCorridorHazards,
    preferred_x: float = 192.0,
    preferred_y: float = 368.0,
    required_gate_lane: str | None = None,
    config: CorridorConfig = TH08_CORRIDOR_CONFIG,
    control_delay_candidates: tuple[int, ...] | None = None,
    nominal_control_delay: int | None = None,
    active_action: str = "stay",
    safety_value_horizon_frames: int = 0,
    retain_safety_action_values: bool = False,
    terminal_viable: np.ndarray | None = None,
    survival_labels: bool = False,
    retain_query_survival_problem: bool = False,
    refinement_grid_steps: tuple[float, ...] = (),
    pre_viability_problem_hook: (
        Callable[[SurvivalQueryProblem], None] | None
    ) = None,
) -> CorridorPlan:
    """Plan from retained neutral hazards at any compatible resolution."""

    if control_delay_candidates is None:
        return plan_corridor(
            start_x=player_x,
            start_y=player_y,
            bounds=TH08_PLAYFIELD,
            aabbs=hazards.aabbs,
            piecewise_aabbs=hazards.piecewise_aabbs,
            segment_trajectories=hazards.segment_trajectories,
            packed_segments=hazards.packed_segments,
            preferred_x=preferred_x,
            preferred_y=preferred_y,
            required_gate_lane=required_gate_lane,
            config=config,
        )
    if nominal_control_delay is None:
        raise ValueError(
            "nominal control delay is required for robust viability"
        )
    robust_control = _th08_robust_control_spec(
        control_delay_candidates=control_delay_candidates,
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        safety_value_horizon_frames=safety_value_horizon_frames,
        retain_safety_action_values=retain_safety_action_values,
        terminal_viable=terminal_viable,
        survival_labels=survival_labels,
        retain_query_survival_problem=retain_query_survival_problem,
        refinement_grid_steps=refinement_grid_steps,
        pre_viability_problem_hook=pre_viability_problem_hook,
    )
    prepared_problem = _prepare_lowered_th08_corridor_with_control(
        hazards=hazards,
        config=config,
        robust_control=robust_control,
    )
    hook_elapsed_ms = 0.0
    if pre_viability_problem_hook is not None:
        assert prepared_problem.survival_query_problem is not None
        hook_started = time.perf_counter()
        pre_viability_problem_hook(
            prepared_problem.survival_query_problem
        )
        hook_elapsed_ms = (
            time.perf_counter() - hook_started
        ) * 1000.0
    return plan_prepared_lowered_th08_corridor(
        player_x=player_x,
        player_y=player_y,
        prepared_problem=prepared_problem,
        preferred_x=preferred_x,
        preferred_y=preferred_y,
        required_gate_lane=required_gate_lane,
        pre_viability_elapsed_ms=hook_elapsed_ms,
    )


def plan_th08_corridor(
    *,
    player_x: float,
    player_y: float,
    bullets: tuple[BulletSnapshot, ...],
    lasers: tuple[LaserSnapshot, ...],
    enemy_bodies: tuple[EnemyBodySnapshot, ...] = (),
    snapshot_lag: int = 0,
    forecast_frames: int = 0,
    preferred_x: float = 192.0,
    preferred_y: float = 368.0,
    required_gate_lane: str | None = None,
    config: CorridorConfig = TH08_CORRIDOR_CONFIG,
    control_delay_candidates: tuple[int, ...] | None = None,
    nominal_control_delay: int | None = None,
    active_action: str = "stay",
    safety_value_horizon_frames: int = 0,
    retain_safety_action_values: bool = False,
    terminal_viable: np.ndarray | None = None,
    survival_labels: bool = False,
    retain_query_survival_problem: bool = False,
    refinement_grid_steps: tuple[float, ...] = (),
) -> CorridorPlan:
    hazards = lower_th08_corridor_hazards(
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        forecast_frames=forecast_frames,
        horizon_frames=config.horizon_frames,
    )
    return plan_lowered_th08_corridor(
        player_x=player_x,
        player_y=player_y,
        hazards=hazards,
        preferred_x=preferred_x,
        preferred_y=preferred_y,
        required_gate_lane=required_gate_lane,
        config=config,
        control_delay_candidates=control_delay_candidates,
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        safety_value_horizon_frames=safety_value_horizon_frames,
        retain_safety_action_values=retain_safety_action_values,
        terminal_viable=terminal_viable,
        survival_labels=survival_labels,
        retain_query_survival_problem=retain_query_survival_problem,
        refinement_grid_steps=refinement_grid_steps,
    )


def prewarm_th08_corridor() -> None:
    """Populate transition geometry before the F8 gameplay handoff."""

    plan_th08_corridor(
        player_x=192.0,
        player_y=400.0,
        bullets=(),
        lasers=(),
        control_delay_candidates=(1, 2, 3),
        nominal_control_delay=2,
        active_action="stay",
    )
