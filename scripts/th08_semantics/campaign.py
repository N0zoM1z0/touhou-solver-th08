"""Closed-loop solver and implementation differential over complete stages."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
import statistics
import time

import numpy as np

import th08_live_dodge_agent as live
from th08_live.movement import advance_planner_action
from th08_semantics.future_hazards import join_stage_future_hazards
from th08_semantics.stage import StageProgram, StageRuntime
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS


@dataclass(frozen=True)
class StageCampaignConfig:
    planner_stride: int = 4
    planner_horizon: int = 12
    planner_threat_horizon: int = 16
    planner_beam_width: int = 8
    action_hold_frames: int = 2
    sensing_latency_frames: int = 1
    issue_latency_frames: int = 1
    geometry_oracle_stride: int = 16
    geometry_oracle_horizon: int = 3
    hit_cooldown_frames: int = 8
    future_hazards_enabled: bool = True

    def __post_init__(self) -> None:
        if min(
            self.planner_stride,
            self.geometry_oracle_stride,
            self.sensing_latency_frames,
            self.issue_latency_frames,
        ) < 0:
            raise ValueError("campaign cadence and latency cannot be negative")
        if min(
            self.planner_horizon,
            self.planner_threat_horizon,
            self.planner_beam_width,
            self.action_hold_frames,
            self.geometry_oracle_horizon,
            self.hit_cooldown_frames,
        ) <= 0:
            raise ValueError("campaign horizons and widths must be positive")


@dataclass(frozen=True)
class StageCampaignResult:
    identity: str
    program_digest: str
    source_closed: bool
    completed: bool
    frames: int
    final_player_x: float
    final_player_y: float
    normalized_hits: int
    normalized_hit_frames: tuple[int, ...]
    normalized_hit_contexts: tuple[dict[str, object], ...]
    collision_frames: int
    collision_frame_indices: tuple[int, ...]
    raw_bullet_collisions: int
    raw_laser_collisions: int
    planner_calls: int
    planner_failures: tuple[str, ...]
    effective_action_hold_frames: int
    future_hazards_enabled: bool
    future_join_attempts: int
    future_join_complete: int
    future_join_incomplete_reasons: dict[str, int]
    future_direct_fire_events: int
    future_laser_events: int
    future_tagged_callbacks: int
    future_callback_transform_fallbacks: int
    bomb_policy_violations: int
    geometry_checks: int
    geometry_collision_mismatches: int
    geometry_clearance_sign_mismatches: int
    geometry_clearance_mismatches: int
    geometry_risk_mismatches: int
    planner_solve_ms_median: float | None
    planner_solve_ms_p95: float | None
    planner_solve_ms_maximum: float | None
    wall_time_seconds: float
    runtime_metrics: dict[str, int]

    @property
    def passed(self) -> bool:
        return (
            self.source_closed
            and self.completed
            and not self.planner_failures
            and (
                not self.future_hazards_enabled
                or (
                    self.future_join_attempts == self.planner_calls
                    and self.future_join_complete == self.future_join_attempts
                    and not self.future_join_incomplete_reasons
                )
            )
            and self.bomb_policy_violations == 0
            and self.geometry_collision_mismatches == 0
            and self.geometry_clearance_sign_mismatches == 0
            and self.geometry_clearance_mismatches == 0
            and self.geometry_risk_mismatches == 0
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self) | {"passed": self.passed}


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _geometry_positions(
    player_x: float,
    player_y: float,
) -> tuple[np.ndarray, np.ndarray]:
    positions = [(player_x, player_y)]
    for action in live._PLANNER_ACTIONS:
        positions.append(
            advance_planner_action(
                player_x,
                player_y,
                action,
                time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            )
        )
    # Deliberately repeat the player point to exercise batch invariance and
    # float32 broadphase bounds with non-unique queries.
    positions.append((player_x, player_y))
    return (
        np.asarray([value[0] for value in positions], dtype=np.float32),
        np.asarray([value[1] for value in positions], dtype=np.float32),
    )


def _geometry_differential(
    *,
    bullets: tuple[live.Bullet, ...],
    lasers: tuple[object, ...],
    player_x: float,
    player_y: float,
    horizon: int,
) -> tuple[int, int, int, int, int]:
    positions_x, positions_y = _geometry_positions(player_x, player_y)
    laser_frames = live._build_packed_laser_collision_frames(
        lasers,
        horizon=horizon,
    )
    checks = 0
    collision_mismatches = 0
    sign_mismatches = 0
    clearance_mismatches = 0
    risk_mismatches = 0
    # Exercise both an atomic snapshot and the common one-frame-straddled
    # live-read contract.  The latter must retain one conservative hull per
    # native slot and remain identical across the NumPy/native kernels.
    for age_support in (None, (0, 1)):
        bullet_frames = live._build_bullet_frames(
            bullets,
            horizon=horizon,
            snapshot_lag=0,
            snapshot_age_support=age_support,
        )
        for step, (bullet_frame, laser_frame) in enumerate(
            zip(bullet_frames, laser_frames),
            start=1,
        ):
            values = {
                "positions_x": positions_x,
                "positions_y": positions_y,
                "step": step,
                "bullet_frame": bullet_frame,
                "lasers": laser_frame,
                "enemy_bodies": (),
            }
            reference = live._numpy_hazards_for_positions(**values)
            candidate = live._native_hazards_for_positions(**values)
            checks += 1
            collision_mismatches += int(
                not np.array_equal(reference[1], candidate[1])
            )
            sign_mismatches += int(
                not np.array_equal(
                    reference[2] <= 0.0,
                    candidate[2] <= 0.0,
                )
            )
            clearance_mismatches += int(
                not np.allclose(
                    reference[2],
                    candidate[2],
                    rtol=1.0e-6,
                    atol=1.0e-4,
                    equal_nan=False,
                )
            )
            risk_mismatches += int(
                not np.allclose(
                    reference[0],
                    candidate[0],
                    rtol=2.0e-5,
                    atol=1.0e-3,
                    equal_nan=False,
                )
            )
    return (
        checks,
        collision_mismatches,
        sign_mismatches,
        clearance_mismatches,
        risk_mismatches,
    )


def run_closed_loop_stage(
    program: StageProgram,
    *,
    config: StageCampaignConfig = StageCampaignConfig(),
) -> StageCampaignResult:
    """Run one complete immortal, hard-no-Bomb offline solver campaign."""

    runtime = StageRuntime(program)
    player_x = 192.0
    player_y = 400.0
    actions = {action.name: action for action in live._PLANNER_ACTIONS}
    current_action = actions["stay"]
    pending_actions: deque[tuple[int, str]] = deque()
    snapshots: deque[
        tuple[
            int,
            float,
            float,
            tuple[live.Bullet, ...],
            tuple[object, ...],
        ]
    ] = deque(maxlen=config.sensing_latency_frames + 1)
    snapshots.append((0, player_x, player_y, (), ()))
    solve_times: list[float] = []
    planner_failures: list[str] = []
    planner_calls = 0
    bomb_violations = 0
    future_join_attempts = 0
    future_join_complete = 0
    future_join_incomplete_reasons: dict[str, int] = {}
    future_direct_fire_events = 0
    future_laser_events = 0
    future_tagged_callbacks = 0
    future_callback_transform_fallbacks = 0
    effective_action_hold_frames = max(
        config.action_hold_frames,
        config.planner_stride,
    )
    geometry_checks = 0
    collision_mismatches = 0
    sign_mismatches = 0
    clearance_mismatches = 0
    risk_mismatches = 0
    normalized_hits = 0
    normalized_hit_frames: list[int] = []
    normalized_hit_contexts: list[dict[str, object]] = []
    collision_frames = 0
    collision_frame_indices: list[int] = []
    next_hit_frame = 0
    decision_history: deque[dict[str, object]] = deque(maxlen=6)
    started = time.perf_counter()

    while not runtime.complete:
        frame = runtime.frame
        while pending_actions and pending_actions[0][0] <= frame:
            _, action_name = pending_actions.popleft()
            current_action = actions[action_name]
        player_x, player_y = advance_planner_action(
            player_x,
            player_y,
            current_action,
            time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )
        step = runtime.step(player_x=player_x, player_y=player_y)
        collision = bool(
            step.bullet_collision_slots or step.laser_collision_slots
        )
        collision_frames += int(collision)
        if collision:
            collision_frame_indices.append(frame)
        if collision and frame >= next_hit_frame:
            normalized_hits += 1
            normalized_hit_frames.append(frame)
            normalized_hit_contexts.append(
                {
                    "frame": frame,
                    "player": [player_x, player_y],
                    "active_action": current_action.name,
                    "bullet_collision_slots": list(
                        step.bullet_collision_slots
                    ),
                    "bullet_collisions": [
                        {
                            "slot": slot,
                            "source": bullet.source,
                            "age": bullet.age,
                            "position": [bullet.x, bullet.y],
                            "velocity": [
                                bullet.velocity_x,
                                bullet.velocity_y,
                            ],
                            "half_extents": [
                                bullet.half_width,
                                bullet.half_height,
                            ],
                            "native_state": bullet.native_state,
                            "native_state_age": bullet.native_state_age,
                            "original_flags": (
                                bullet.original_transform_flags
                            ),
                            "active_transform_flags": (
                                bullet.active_transform_flags
                            ),
                            "callback_phase_state": bullet.phase_state,
                            "callback_aux_state": bullet.collision_aux,
                        }
                        for slot in step.bullet_collision_slots
                        if (bullet := runtime.bullets[slot]) is not None
                    ],
                    "laser_collision_slots": list(step.laser_collision_slots),
                    "recent_decisions": list(decision_history),
                }
            )
            next_hit_frame = frame + config.hit_cooldown_frames

        geometry_due = (
            config.geometry_oracle_stride
            and frame % config.geometry_oracle_stride == 0
        )
        snapshot = (
            runtime.live_snapshot()
            if config.planner_stride or geometry_due
            else None
        )
        if config.planner_stride:
            assert snapshot is not None
            snapshots.append(
                (
                    runtime.frame,
                    player_x,
                    player_y,
                    snapshot[0],
                    snapshot[1],
                )
            )
        if geometry_due:
            assert snapshot is not None
            differential = _geometry_differential(
                bullets=snapshot[0],
                lasers=snapshot[1],
                player_x=player_x,
                player_y=player_y,
                horizon=config.geometry_oracle_horizon,
            )
            geometry_checks += differential[0]
            collision_mismatches += differential[1]
            sign_mismatches += differential[2]
            clearance_mismatches += differential[3]
            risk_mismatches += differential[4]

        if config.planner_stride and frame % config.planner_stride == 0:
            (
                sensed_root_frame,
                sensed_player_x,
                sensed_player_y,
                sensed_bullets,
                sensed_lasers,
            ) = snapshots[0]
            control_delay_frames = (
                runtime.frame
                - sensed_root_frame
                + config.issue_latency_frames
            )
            planner_started = time.perf_counter_ns()
            planning_bullets = sensed_bullets
            future_projection = None
            if config.future_hazards_enabled:
                future_join = join_stage_future_hazards(
                    program,
                    root_frame=sensed_root_frame,
                    root_player_x=sensed_player_x,
                    root_player_y=sensed_player_y,
                    bullets=sensed_bullets,
                    horizon_frames=(
                        control_delay_frames
                        + max(
                            config.planner_threat_horizon,
                            effective_action_hold_frames,
                        )
                    ),
                )
                future_join_attempts += 1
                future_direct_fire_events += (
                    future_join.direct_fire_event_count
                )
                future_laser_events += future_join.future_laser_count
                future_tagged_callbacks += future_join.tagged_callback_count
                future_callback_transform_fallbacks += (
                    future_join.callback_transform_fallback_count
                )
                if future_join.complete:
                    future_join_complete += 1
                    planning_bullets = tuple(future_join.bullets)
                    future_projection = future_join.projection
                else:
                    reason = future_join.reason or "unknown"
                    future_join_incomplete_reasons[reason] = (
                        future_join_incomplete_reasons.get(reason, 0) + 1
                    )
            try:
                decision = live.choose_action(
                    player_x=sensed_player_x,
                    player_y=sensed_player_y,
                    bullets=planning_bullets,
                    lasers=sensed_lasers,
                    previous_direction=current_action.direction,
                    previous_focus=current_action.focused,
                    can_bomb=False,
                    bombs=0.0,
                    # Player, bullet, and laser values come from one coherent
                    # sensed root. Their relative lag is zero; elapsed sensing
                    # and issue time is carried only by control_delay_frames.
                    snapshot_lag=0,
                    control_delay_frames=control_delay_frames,
                    action_hold_frames=effective_action_hold_frames,
                    horizon=config.planner_horizon,
                    threat_horizon=config.planner_threat_horizon,
                    beam_width=config.planner_beam_width,
                    target_x=192.0,
                    target_y=360.0,
                    target_deadline=config.planner_horizon + 12,
                    recovery_control_reserve=True,
                    preserve_previous_direction_inertia=True,
                    future_hazard_projection=future_projection,
                    future_projection_offset=0,
                )
            except Exception as exc:  # retained as replayable fuzzer failure
                planner_failures.append(
                    f"frame={frame}:{type(exc).__name__}:{exc}"
                )
            else:
                planner_calls += 1
                bomb_violations += int(
                    bool(decision.bomb) or bool(decision.mask & live.BOMB)
                )
                if decision.action not in actions:
                    planner_failures.append(
                        f"frame={frame}:unknown_action:{decision.action}"
                    )
                else:
                    decision_history.append(
                        {
                            "decision_frame": frame,
                            "sensed_root_frame": sensed_root_frame,
                            "sensed_player": [
                                sensed_player_x,
                                sensed_player_y,
                            ],
                            "action": decision.action,
                            "effective_frame": (
                                frame + config.issue_latency_frames + 1
                            ),
                            "control_delay_frames": control_delay_frames,
                            "action_hold_frames": (
                                effective_action_hold_frames
                            ),
                            "min_clearance": decision.min_clearance,
                            "immediate_clearance": (
                                decision.immediate_clearance
                            ),
                            "local_collisions": decision.local_collisions,
                            "terminal_threat_collisions": (
                                decision.terminal_threat_collisions
                            ),
                            "terminal_threat_min_clearance": (
                                decision.terminal_threat_min_clearance
                            ),
                            "future_join_complete": (
                                future_projection is not None
                            ),
                        }
                    )
                    pending_actions.append(
                        (
                            frame + config.issue_latency_frames + 1,
                            decision.action,
                        )
                    )
            solve_times.append(
                (time.perf_counter_ns() - planner_started) / 1_000_000.0
            )

    wall_time = time.perf_counter() - started
    return StageCampaignResult(
        identity=program.identity,
        program_digest=program.digest,
        source_closed=program.source_closed,
        completed=runtime.complete,
        frames=runtime.frame,
        final_player_x=player_x,
        final_player_y=player_y,
        normalized_hits=normalized_hits,
        normalized_hit_frames=tuple(normalized_hit_frames),
        normalized_hit_contexts=tuple(normalized_hit_contexts),
        collision_frames=collision_frames,
        collision_frame_indices=tuple(collision_frame_indices),
        raw_bullet_collisions=runtime.metrics.raw_bullet_collisions,
        raw_laser_collisions=runtime.metrics.raw_laser_collisions,
        planner_calls=planner_calls,
        planner_failures=tuple(planner_failures),
        effective_action_hold_frames=effective_action_hold_frames,
        future_hazards_enabled=config.future_hazards_enabled,
        future_join_attempts=future_join_attempts,
        future_join_complete=future_join_complete,
        future_join_incomplete_reasons=future_join_incomplete_reasons,
        future_direct_fire_events=future_direct_fire_events,
        future_laser_events=future_laser_events,
        future_tagged_callbacks=future_tagged_callbacks,
        future_callback_transform_fallbacks=(
            future_callback_transform_fallbacks
        ),
        bomb_policy_violations=bomb_violations,
        geometry_checks=geometry_checks,
        geometry_collision_mismatches=collision_mismatches,
        geometry_clearance_sign_mismatches=sign_mismatches,
        geometry_clearance_mismatches=clearance_mismatches,
        geometry_risk_mismatches=risk_mismatches,
        planner_solve_ms_median=(
            statistics.median(solve_times) if solve_times else None
        ),
        planner_solve_ms_p95=_p95(solve_times),
        planner_solve_ms_maximum=(max(solve_times) if solve_times else None),
        wall_time_seconds=wall_time,
        runtime_metrics={
            key: int(value) for key, value in asdict(runtime.metrics).items()
        },
    )


__all__ = [
    "StageCampaignConfig",
    "StageCampaignResult",
    "run_closed_loop_stage",
]
