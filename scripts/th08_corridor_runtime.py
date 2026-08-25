#!/usr/bin/env python3
"""Asynchronous TH08 corridor-policy runtime.

This module owns policy epochs, corridor commitments, capsule publication, and
optional shadow-policy queries.  The live agent should only coordinate these
results with its local issue-time controller.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from th08_corridor_adapter import (
    TH08_CORRIDOR_CONFIG,
    lower_th08_corridor_hazards,
    plan_prepared_lowered_th08_corridor,
    prepare_lowered_th08_corridor,
)
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_global_authority import (
    RuntimeEclVersion,
    build_th08_global_authority_version,
)
from th08_callback_join_contract import (
    CurrentPoolProjectionCallbackJoinContract,
)
from th08_corridor_audit import submit_corridor_audit
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
    UnsupportedTimeScaleScheduleError,
)
from touhou_control import native_backend
from touhou_control.background_priority import (
    lower_current_thread_priority,
)
from touhou_control.corridor.runtime import (
    CorridorPolicyArtifact,
    CorridorPublication,
    CorridorRuntimeHandles,
    CorridorSolution,
)
from touhou_control.corridor import (
    AabbTrajectoryHazard,
    AnnularSectorTrajectoryHazard,
    CorridorConfig,
)
from touhou_control.query_survival import (
    PendingCommand,
    QueryLocalSurvivalResult,
    ReachablePipelineRoot,
    StalePipelineWorkspaceError,
    SurvivalQueryProblem,
)
from touhou_control.viability import SafetyValueQuery, ViabilityQuery


CORRIDOR_MIN_COMMIT_FRAMES = 32
# The full-horizon 8px policy is retained as an offline/shadow CE-0100 gate.
# A physical Stage-4A trial showed that enabling it on every coarse-empty
# source made rolling policies stale enough to harm the local controller.
LIVE_REFINEMENT_GRID_STEPS: tuple[float, ...] = ()
SHADOW_REFINEMENT_GRID_STEPS = (8.0,)
# Fused survival labels have scalar parity inside one frozen hazard model, but
# the Stage-4A live trial showed that their extra service time and stale-model
# authority are not yet acceptable.  Keep them available to replay/shadow
# callers without allowing them to rank live actions.
LIVE_SURVIVAL_LABELS = False
SHADOW_SURVIVAL_LABELS = True
class SlottedHazard(Protocol):
    slot: int


class PointerHazard(Protocol):
    pointer: int


@dataclass
class CorridorCommitment:
    """Retain a viable gate component across asynchronous replans."""

    lane: str | None = None
    expires_frame: int = -1
    context_key: tuple[int, int, int | None] | None = None

    def set_context(
        self,
        context_key: tuple[int, int, int | None],
    ) -> bool:
        if self.context_key == context_key:
            return False
        self.context_key = context_key
        self.lane = None
        self.expires_frame = -1
        return True

    def active_lane(self, frame: int) -> str | None:
        if self.lane is None or frame >= self.expires_frame:
            return None
        return self.lane

    def accept(self, solution: CorridorSolution, *, current_frame: int) -> None:
        if not solution.plan.reachable or solution.plan.gate is None:
            return
        active_lane = self.active_lane(current_frame)
        if (
            active_lane is not None
            and (
                (
                    solution.required_gate_lane == active_lane
                    and solution.constraint_honored
                )
                or solution.plan.lane == active_lane
            )
        ):
            return
        if active_lane is None and solution.required_gate_lane is not None:
            self.lane = None
            self.expires_frame = -1
            return
        self.lane = solution.plan.lane
        self.expires_frame = max(
            current_frame + CORRIDOR_MIN_COMMIT_FRAMES,
            solution.source_frame + solution.plan.gate.frame,
        )


def solve_corridor(
    *,
    source_frame: int,
    snapshot_frame: int,
    forecast_lead_frames: int,
    player_x: float,
    player_y: float,
    bullets: tuple[SlottedHazard, ...],
    lasers: tuple[SlottedHazard, ...],
    enemy_bodies: tuple[PointerHazard, ...],
    future_aabb_trajectories: tuple[AabbTrajectoryHazard, ...] = (),
    future_hazard_projection: OrdinaryFutureHazardProjection | None = None,
    current_pool_callback_join: (
        CurrentPoolProjectionCallbackJoinContract | None
    ) = None,
    runtime_ecl_version: RuntimeEclVersion | None = None,
    snapshot_lag: int,
    control_delay_candidates: tuple[int, ...],
    nominal_control_delay: int,
    active_action: str,
    observed_control_delay_candidates: tuple[int, ...] | None = None,
    safety_value_horizon_frames: int = 0,
    retain_safety_action_values: bool = False,
    required_gate_lane: str | None = None,
    context_key: tuple[int, int, int | None] | None = None,
    audit_capsule_dir: Path | None = None,
    audit_executor: ThreadPoolExecutor | None = None,
    background_low_priority: bool = False,
    native_viability_worker_limit: int | None = None,
    time_scale_schedule: Th08TimeScaleSchedule,
    corridor_config: CorridorConfig = TH08_CORRIDOR_CONFIG,
) -> CorridorSolution:
    if (
        native_viability_worker_limit is not None
        and not 1 <= native_viability_worker_limit <= 16
    ):
        raise ValueError("native viability worker limit must be 1..16")
    if current_pool_callback_join is not None:
        if not isinstance(
            current_pool_callback_join,
            CurrentPoolProjectionCallbackJoinContract,
        ):
            raise ValueError("callback join does not satisfy its contract")
        if future_hazard_projection is None:
            raise ValueError(
                "callback join requires a future-hazard projection"
            )
        if not current_pool_callback_join.complete:
            raise ValueError("callback join must be complete")
        if (
            current_pool_callback_join.time_scale_bits
            != TH08_UNIT_TIME_SCALE_BITS
        ):
            raise ValueError("callback join must use exact unit time scale")
        if not current_pool_callback_join.matches_projection(
            future_hazard_projection
        ):
            raise ValueError("callback join projection identity disagrees")
        if current_pool_callback_join.bullets is not bullets:
            raise ValueError("corridor bullets are not callback-join output")
        if current_pool_callback_join.policy_source_frame != source_frame:
            raise ValueError("callback join policy source disagrees")
        if (
            current_pool_callback_join.policy_horizon_frames
            != corridor_config.horizon_frames
        ):
            raise ValueError("callback join policy horizon disagrees")
        expected_bullet_root = snapshot_frame - max(0, snapshot_lag)
        if current_pool_callback_join.bullet_root_frame != expected_bullet_root:
            raise ValueError("callback join bullet root disagrees")
    if (
        future_hazard_projection is not None
        and future_hazard_projection.tagged_callbacks
        and current_pool_callback_join is None
    ):
        raise ValueError(
            "future callbacks require a current-pool callback join"
        )
    scale_horizon = (
        max(0, snapshot_lag)
        + max(0, forecast_lead_frames)
        + corridor_config.horizon_frames
        + 1
    )
    time_scale_schedule.require_complete_horizon(scale_horizon)
    player_scale_bits = time_scale_schedule.require_player_horizon(
        scale_horizon
    )
    laser_scale_bits = time_scale_schedule.require_laser_horizon(
        scale_horizon
    )
    if any(
        bits != TH08_UNIT_TIME_SCALE_BITS
        for bits in (*player_scale_bits, *laser_scale_bits)
    ):
        raise UnsupportedTimeScaleScheduleError(
            "corridor recurrence supports only an exact complete unit-scale "
            "schedule; nonunit or varying coverage is UNKNOWN"
        )
    time_scale_identity = time_scale_schedule.serialized_identity
    authority_version = build_th08_global_authority_version(
        source_frame=source_frame,
        snapshot_frame=snapshot_frame,
        forecast_lead_frames=forecast_lead_frames,
        player_x=player_x,
        player_y=player_y,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        control_delay_candidates=control_delay_candidates,
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        required_gate_lane=required_gate_lane,
        context_key=context_key,
        runtime_ecl_version=runtime_ecl_version,
        time_scale_schedule=time_scale_schedule,
        future_hazard_projection=future_hazard_projection,
        current_pool_callback_join_version=(
            current_pool_callback_join.version
            if current_pool_callback_join is not None
            else None
        ),
        corridor_config=corridor_config,
    )
    background_priority_lowered = (
        lower_current_thread_priority()
        if background_low_priority
        else False
    )
    native_worker_limit_applied = (
        native_backend.set_current_thread_viability_worker_limit(
            native_viability_worker_limit
        )
        if native_viability_worker_limit is not None
        else False
    )
    started = time.perf_counter()
    future_annular_sector_trajectories: tuple[
        AnnularSectorTrajectoryHazard, ...
    ] = ()
    if future_hazard_projection is not None:
        if future_aabb_trajectories:
            raise ValueError(
                "future projection and raw future trajectories are exclusive"
            )
        future_annular_sector_trajectories = (
            future_hazard_projection.trajectories_for_policy(
                source_frame=source_frame,
                horizon_frames=corridor_config.horizon_frames,
            )
        )
        future_aabb_trajectories = (
            future_hazard_projection.aabb_trajectories_for_policy(
                source_frame=source_frame,
                horizon_frames=corridor_config.horizon_frames,
            )
        )
    hazards = lower_th08_corridor_hazards(
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        forecast_frames=forecast_lead_frames,
        horizon_frames=corridor_config.horizon_frames,
        laser_time_scale_bits=laser_scale_bits,
        future_aabb_trajectories=future_aabb_trajectories,
        future_annular_sector_trajectories=(
            future_annular_sector_trajectories
        ),
    )
    prepared_problem = prepare_lowered_th08_corridor(
        hazards=hazards,
        config=corridor_config,
        control_delay_candidates=control_delay_candidates,
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        safety_value_horizon_frames=safety_value_horizon_frames,
        retain_safety_action_values=retain_safety_action_values,
        survival_labels=LIVE_SURVIVAL_LABELS,
        retain_query_survival_problem=True,
        refinement_grid_steps=LIVE_REFINEMENT_GRID_STEPS,
    )
    plan = plan_prepared_lowered_th08_corridor(
        player_x=player_x,
        player_y=player_y,
        prepared_problem=prepared_problem,
        required_gate_lane=required_gate_lane,
    )
    constraint_honored = (
        required_gate_lane is None
        or (plan.reachable and plan.lane == required_gate_lane)
    )
    solve_finished = time.perf_counter()
    audit = submit_corridor_audit(
        audit_capsule_dir=audit_capsule_dir,
        audit_executor=audit_executor,
        source_frame=source_frame,
        snapshot_frame=snapshot_frame,
        forecast_lead_frames=forecast_lead_frames,
        player_x=player_x,
        player_y=player_y,
        snapshot_lag=snapshot_lag,
        control_delay_candidates=control_delay_candidates,
        observed_control_delay_candidates=(
            observed_control_delay_candidates
        ),
        nominal_control_delay=nominal_control_delay,
        active_action=active_action,
        required_gate_lane=required_gate_lane,
        context_key=context_key,
        grid_step=corridor_config.grid_step,
        frames_per_layer=corridor_config.frames_per_layer,
        horizon_frames=corridor_config.horizon_frames,
        bullet_slots=tuple(bullet.slot for bullet in bullets),
        laser_slots=tuple(laser.slot for laser in lasers),
        enemy_pointers=tuple(
            body.pointer for body in enemy_bodies
        ),
        plan_reachable=plan.reachable,
        hazards=hazards,
        time_scale_identity=time_scale_identity,
    )
    return CorridorSolution(
        artifact=CorridorPolicyArtifact(
            source_frame=source_frame,
            plan=plan,
            solve_ms=(solve_finished - started) * 1000.0,
            snapshot_frame=snapshot_frame,
            forecast_lead_frames=forecast_lead_frames,
            required_gate_lane=required_gate_lane,
            constraint_honored=constraint_honored,
            context_key=context_key,
            worker_ms=(time.perf_counter() - started) * 1000.0,
            background_priority_lowered=(
                background_priority_lowered
            ),
            native_viability_worker_limit=(
                native_viability_worker_limit
            ),
            native_viability_worker_limit_applied=(
                native_worker_limit_applied
            ),
            time_scale_identity=time_scale_identity,
            future_hazard_version=(
                future_hazard_projection.version
                if future_hazard_projection is not None
                else None
            ),
            future_hazard_coverage=(
                future_hazard_projection.coverage
                if future_hazard_projection is not None
                else None
            ),
            current_pool_callback_join_version=(
                current_pool_callback_join.version
                if current_pool_callback_join is not None
                else None
            ),
            authority_version=authority_version,
        ),
        publication=CorridorPublication(
            audit_capsule=audit.capsule,
            audit_write_ms=audit.write_ms,
            audit_error=audit.error,
        ),
        handles=CorridorRuntimeHandles(
            audit_future=audit.future,
            future_hazard_projection=future_hazard_projection,
            current_pool_callback_join=current_pool_callback_join,
        ),
    )


def require_corridor_background_priority(
    solution: CorridorSolution,
    *,
    requested: bool,
) -> None:
    """Fail an explicit priority experiment that did not apply its request."""

    if requested and not solution.background_priority_lowered:
        raise RuntimeError(
            "requested corridor background priority was not applied"
        )


def corridor_target(
    solution: CorridorSolution | None,
    *,
    current_frame: int,
    lookahead_frames: int,
    max_age_frames: int,
) -> tuple[float, float, int] | None:
    if solution is None or not solution.plan.reachable:
        return None
    age = current_frame - solution.source_frame
    if age < 0 or age > max_age_frames:
        return None
    waypoint = solution.plan.waypoint(age + lookahead_frames)
    return waypoint.x, waypoint.y, max(waypoint.frame - age, 0)


def corridor_viability_query(
    solution: CorridorSolution | None,
    *,
    current_frame: int,
    player_x: float,
    player_y: float,
    active_action: str,
    max_age_frames: int,
) -> ViabilityQuery | None:
    if solution is None or solution.plan.viability_policy is None:
        return None
    age = current_frame - solution.source_frame
    if age < 0 or age > max_age_frames:
        return None
    query = solution.plan.viability_policy.query(
        frame=age,
        x=player_x,
        y=player_y,
        active_action=active_action,
    )
    survival_policy = solution.plan.survival_policy
    if (
        query.available
        and not query.state_viable
        and not query.survival_best_actions
        and survival_policy is not None
        and survival_policy is not solution.plan.viability_policy
    ):
        survival_query = survival_policy.query(
            frame=age,
            x=player_x,
            y=player_y,
            active_action=active_action,
        )
        if survival_query.available:
            query = replace(
                query,
                survival_frames=survival_query.survival_frames,
                survival_bottleneck_margin=(
                    survival_query.survival_bottleneck_margin
                ),
                survival_best_actions=(
                    survival_query.survival_best_actions
                ),
            )
    return query


def _pipeline_policy_version(
    solution: CorridorSolution,
) -> tuple[object, ...]:
    legacy = (
        solution.source_frame,
        solution.snapshot_frame,
        solution.context_key,
        solution.time_scale_identity,
    )
    if solution.authority_version is None:
        return legacy
    return (*legacy, solution.authority_version.digest)


def prepare_pipeline_survival_workspace(
    solution: CorridorSolution,
) -> CorridorSolution:
    """Attach a versioned exact-phase workspace without querying it."""

    if (
        solution.pipeline_survival_workspace is not None
        and not solution.pipeline_survival_workspace.closed
    ):
        return solution
    problem = solution.plan.survival_query_problem
    if problem is None:
        return solution
    started = time.perf_counter()
    workspace = problem.build_pipeline_workspace(
        policy_version=_pipeline_policy_version(solution),
    )
    return solution.with_handles(
        pipeline_survival_workspace=workspace,
    ).with_publication(
        pipeline_survival_workspace_ms=(
            (time.perf_counter() - started) * 1000.0
        ),
    )


def corridor_pipeline_survival_query(
    solution: CorridorSolution | None,
    *,
    current_frame: int,
    player_x: float,
    player_y: float,
    observed_action: str,
    pending_command: PendingCommand | None,
    max_age_frames: int,
) -> QueryLocalSurvivalResult | None:
    """Run an exact shadow query, with stale versions returning no result.

    This call may expand a cold reachable tube.  Live orchestration must run
    it on the isolated survival executor until a warm-deadline gate passes.
    """

    if solution is None or solution.pipeline_survival_workspace is None:
        return None
    age = current_frame - solution.source_frame
    if age < 0 or age > max_age_frames:
        return None
    try:
        return solution.pipeline_survival_workspace.query(
            policy_version=_pipeline_policy_version(solution),
            frame=age,
            x=player_x,
            y=player_y,
            observed_action=observed_action,
            pending_command=pending_command,
        )
    except StalePipelineWorkspaceError:
        return None


def corridor_safety_value_query(
    solution: CorridorSolution | None,
    *,
    current_frame: int,
    player_x: float,
    player_y: float,
    active_action: str,
    max_age_frames: int,
) -> SafetyValueQuery | None:
    if solution is None or solution.plan.safety_value_policy is None:
        return None
    age = current_frame - solution.source_frame
    if age < 0 or age > max_age_frames:
        return None
    return solution.plan.safety_value_policy.query(
        frame=age,
        x=player_x,
        y=player_y,
        active_action=active_action,
    )


def corridor_policy_status(
    solution: CorridorSolution | None,
    *,
    current_frame: int,
    max_age_frames: int,
) -> str:
    if solution is None or solution.plan.viability_policy is None:
        return "unavailable"
    age = current_frame - solution.source_frame
    if age < 0:
        return "pending_future_epoch"
    if age > max_age_frames:
        return "expired"
    if age >= solution.plan.viability_policy.horizon_frames:
        return "outside_policy_horizon"
    return "queryable"


def stage_corridor_solution(
    active: CorridorSolution | None,
    candidate: CorridorSolution,
    *,
    current_frame: int,
    context_key: tuple[int, int, int | None],
) -> tuple[CorridorSolution | None, CorridorSolution | None]:
    """Keep the active policy until a matching future epoch is reached."""

    if candidate.context_key != context_key:
        return active, None
    if candidate.source_frame <= current_frame:
        return candidate, None
    return active, candidate


def corridor_submit_due(
    *,
    current_frame: int,
    last_submit_frame: int,
    interval_frames: int,
) -> bool:
    return current_frame - last_submit_frame >= interval_frames


__all__ = [
    "CorridorCommitment",
    "CorridorPolicyArtifact",
    "CorridorPublication",
    "CorridorRuntimeHandles",
    "CorridorSolution",
    "LIVE_REFINEMENT_GRID_STEPS",
    "LIVE_SURVIVAL_LABELS",
    "SHADOW_REFINEMENT_GRID_STEPS",
    "SHADOW_SURVIVAL_LABELS",
    "corridor_pipeline_survival_query",
    "corridor_policy_status",
    "corridor_safety_value_query",
    "corridor_submit_due",
    "corridor_target",
    "corridor_viability_query",
    "prepare_pipeline_survival_workspace",
    "require_corridor_background_priority",
    "solve_corridor",
    "stage_corridor_solution",
]
