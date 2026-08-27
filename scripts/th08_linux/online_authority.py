"""Fail-closed global/future publication join for Linux online actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Callable

from th08_corridor_adapter import TH08_CORRIDOR_CONFIG
from th08_corridor_runtime import CorridorSolution
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_global_authority import (
    GlobalActionAuthorityAssessment,
    RuntimeEclVersion,
    assess_th08_global_action_authority,
)
from th08_linux.planner import LinuxPlannerGuidance, LinuxPlannerSnapshot
from th08_live.movement import action_name_from_mask
from th08_live.policy import PolicyCoordinator, PolicyQueryRequest
from th08_time_scale import Th08TimeScaleSchedule
from touhou_control.corridor import CorridorConfig


ONLINE_GLOBAL_ACTION_AUTHORITY = "linux_online_exact_global_future_unit_cadence_v2"
TH08_ONLINE_AUTHORITY_CONFIG = replace(
    TH08_CORRIDOR_CONFIG,
    # A hard online query chooses only the next physical-frame action.  The
    # generic corridor transition holds one selected action for an entire
    # layer, so any larger layer would be a macro-action contract and cannot
    # safely constrain a controller that is free to choose again next frame.
    frames_per_layer=1,
    grid_step=4.0,
    required_clearance=math.sqrt(2.0) * 2.0,
)


@dataclass(frozen=True, slots=True)
class OnlineAuthorityResult:
    guidance: LinuxPlannerGuidance
    status: str
    reasons: tuple[str, ...]
    solution_source_frame: int | None
    solution_source_input_epoch: int | None
    policy_version: str | None
    global_constraint_applied: bool
    future_projection_applied_locally: bool


class OnlineActionAuthority:
    """Admit only a current, exact-version corridor result to local control."""

    def __init__(
        self,
        *,
        corridor_config: CorridorConfig = TH08_ONLINE_AUTHORITY_CONFIG,
        lookahead_frames: int = 16,
        local_future_horizon_frames: int = 32,
        max_age_frames: int | None = None,
        policy_coordinator: PolicyCoordinator | None = None,
        assess: Callable[..., GlobalActionAuthorityAssessment] = (
            assess_th08_global_action_authority
        ),
    ) -> None:
        if lookahead_frames < 0:
            raise ValueError("corridor lookahead cannot be negative")
        if local_future_horizon_frames <= 0:
            raise ValueError("local future horizon must be positive")
        if corridor_config.frames_per_layer != 1:
            raise ValueError(
                "online hard action authority requires one physical frame "
                "per control layer"
            )
        configured_max_age = (
            corridor_config.horizon_frames - 1
            if max_age_frames is None
            else max_age_frames
        )
        if configured_max_age < 0:
            raise ValueError("corridor maximum age cannot be negative")
        self._corridor_config = corridor_config
        self._lookahead_frames = lookahead_frames
        self._local_future_horizon_frames = local_future_horizon_frames
        self._max_age_frames = configured_max_age
        self._policy = policy_coordinator or PolicyCoordinator()
        self._assess = assess
        self._active: CorridorSolution | None = None
        self._pending: CorridorSolution | None = None
        self._active_source_input_epoch: int | None = None
        self._pending_source_input_epoch: int | None = None
        self._context: tuple[int, int, int | None] | None = None
        self.query_count = 0
        self.allowed_query_count = 0
        self.constrained_action_count = 0

    @property
    def active_solution(self) -> CorridorSolution | None:
        return self._active

    @property
    def pending_solution(self) -> CorridorSolution | None:
        return self._pending

    @property
    def active_source_input_epoch(self) -> int | None:
        return self._active_source_input_epoch

    @property
    def pending_source_input_epoch(self) -> int | None:
        return self._pending_source_input_epoch

    def reset(self, context: tuple[int, int, int | None] | None = None) -> None:
        self._active = None
        self._pending = None
        self._active_source_input_epoch = None
        self._pending_source_input_epoch = None
        self._context = context

    @staticmethod
    def _mapping_matches(
        solution: CorridorSolution,
        *,
        solution_source_input_epoch: int,
        current_frame: int,
        current_input_epoch: int,
    ) -> bool:
        return (
            current_frame - solution.source_frame
            == current_input_epoch - solution_source_input_epoch
        )

    def advance(
        self,
        *,
        current_frame: int,
        current_input_epoch: int,
        context: tuple[int, int, int | None],
    ) -> bool:
        if self._context != context:
            self.reset(context)
        for solution, source_epoch in (
            (self._active, self._active_source_input_epoch),
            (self._pending, self._pending_source_input_epoch),
        ):
            if solution is None:
                continue
            if (
                source_epoch is None
                or solution.context_key != context
                or not self._mapping_matches(
                    solution,
                    solution_source_input_epoch=source_epoch,
                    current_frame=current_frame,
                    current_input_epoch=current_input_epoch,
                )
            ):
                self.reset(context)
                return False
        if (
            self._pending is not None
            and self._pending_source_input_epoch is not None
            and current_input_epoch >= self._pending_source_input_epoch
        ):
            self._active = self._pending
            self._active_source_input_epoch = self._pending_source_input_epoch
            self._pending = None
            self._pending_source_input_epoch = None
        return True

    def publish(
        self,
        solution: CorridorSolution,
        *,
        solution_source_input_epoch: int,
        current_frame: int,
        current_input_epoch: int,
        context: tuple[int, int, int | None],
    ) -> bool:
        if solution_source_input_epoch <= 0 or current_input_epoch <= 0:
            return False
        if not self.advance(
            current_frame=current_frame,
            current_input_epoch=current_input_epoch,
            context=context,
        ):
            return False
        if (
            solution.context_key != context
            or not self._mapping_matches(
                solution,
                solution_source_input_epoch=solution_source_input_epoch,
                current_frame=current_frame,
                current_input_epoch=current_input_epoch,
            )
        ):
            return False
        # Preserve the earliest already-solved future epoch.  Replacing it
        # with every newer rolling result can move the pending boundary ahead
        # forever when solves finish faster than their publication lead.
        if (
            self._pending is not None
            and self._pending_source_input_epoch is not None
            and solution_source_input_epoch > current_input_epoch
            and (
                solution.context_key != context
                or solution_source_input_epoch
                >= self._pending_source_input_epoch
            )
        ):
            return False
        if solution_source_input_epoch <= current_input_epoch:
            self._active = solution
            self._active_source_input_epoch = solution_source_input_epoch
        else:
            self._pending = solution
            self._pending_source_input_epoch = solution_source_input_epoch
        return True

    def guidance_for(
        self,
        snapshot: LinuxPlannerSnapshot,
        *,
        current_input_epoch: int,
        current_input: int,
        context: tuple[int, int, int | None],
        runtime_ecl_version: RuntimeEclVersion | None,
        time_scale_schedule: Th08TimeScaleSchedule,
    ) -> OnlineAuthorityResult:
        mapping_current = self.advance(
            current_frame=snapshot.frame,
            current_input_epoch=current_input_epoch,
            context=context,
        )
        self.query_count += 1
        if not mapping_current:
            return OnlineAuthorityResult(
                guidance=LinuxPlannerGuidance(
                    time_scale_schedule=time_scale_schedule,
                ),
                status="withheld",
                reasons=("input-manager-policy-clock-mismatch",),
                solution_source_frame=None,
                solution_source_input_epoch=None,
                policy_version=None,
                global_constraint_applied=False,
                future_projection_applied_locally=False,
            )
        assessment = self._assess(
            self._active,
            current_frame=snapshot.frame,
            context_key=context,
            runtime_ecl_version=runtime_ecl_version,
            time_scale_schedule=time_scale_schedule,
            corridor_config=self._corridor_config,
        )
        solution = self._active
        version = assessment.version
        version_digest = version.digest if version is not None else None
        if not assessment.allowed or solution is None:
            return OnlineAuthorityResult(
                guidance=LinuxPlannerGuidance(
                    time_scale_schedule=time_scale_schedule,
                ),
                status="withheld",
                reasons=assessment.reasons,
                solution_source_frame=(
                    solution.source_frame if solution is not None else None
                ),
                solution_source_input_epoch=(
                    self._active_source_input_epoch
                    if solution is not None
                    else None
                ),
                policy_version=version_digest,
                global_constraint_applied=False,
                future_projection_applied_locally=False,
            )

        self.allowed_query_count += 1
        active_action = action_name_from_mask(current_input)
        queries = self._policy.query(
            PolicyQueryRequest(
                solution=solution,
                target_frame=snapshot.frame,
                query_frame=snapshot.frame,
                player_x=snapshot.player_x,
                player_y=snapshot.player_y,
                active_action=active_action,
                observed_action=active_action,
                lookahead_frames=self._lookahead_frames,
                max_age_frames=self._max_age_frames,
                current_delay_frames=(0,),
            )
        )
        local = queries.guidance
        target = queries.primary.target
        allowed = (
            local.allowed_first_actions
            if local.support_covers_current
            else None
        )
        projection = solution.future_hazard_projection
        projection_offset = -1
        local_projection: OrdinaryFutureHazardProjection | None = None
        if isinstance(projection, OrdinaryFutureHazardProjection):
            projection_offset = snapshot.frame - projection.root_frame
            if (
                projection.current_pool_callback_composition_complete
                and projection_offset >= 0
                and projection_offset
                + max(
                    self._corridor_config.frames_per_layer,
                    self._lookahead_frames,
                    self._local_future_horizon_frames,
                )
                <= projection.horizon_frames
            ):
                local_projection = projection

        constrained = allowed is not None
        if constrained:
            self.constrained_action_count += 1
        return OnlineAuthorityResult(
            guidance=LinuxPlannerGuidance(
                target_x=target[0] if target is not None else None,
                target_y=target[1] if target is not None else None,
                target_deadline=target[2] if target is not None else None,
                allowed_first_actions=allowed,
                allowed_action_authority=(
                    ONLINE_GLOBAL_ACTION_AUTHORITY if constrained else None
                ),
                viability_repair_volumes=local.repair_volumes,
                viability_recovery_distances=local.recovery_distances,
                viability_safety_actions=local.safety_actions,
                viability_safety_state_value=local.safety_state_value,
                viability_survival_actions=local.survival_actions,
                viability_survival_frames=local.survival_frames,
                viability_survival_bottleneck_margin=(
                    local.survival_bottleneck_margin
                ),
                viability_position_error=local.position_error,
                future_hazard_projection=local_projection,
                future_projection_offset=(
                    projection_offset if local_projection is not None else 0
                ),
                time_scale_schedule=time_scale_schedule,
                authority_version=version_digest,
            ),
            status=("constrained" if constrained else "global-losing-or-unavailable"),
            reasons=(() if constrained else ("no-current-viable-action-set",)),
            solution_source_frame=solution.source_frame,
            solution_source_input_epoch=self._active_source_input_epoch,
            policy_version=version_digest,
            global_constraint_applied=constrained,
            future_projection_applied_locally=local_projection is not None,
        )


__all__ = (
    "ONLINE_GLOBAL_ACTION_AUTHORITY",
    "TH08_ONLINE_AUTHORITY_CONFIG",
    "OnlineActionAuthority",
    "OnlineAuthorityResult",
)
