"""Request validation and normalized derived inputs for the local planner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .requests import LocalPlannerRequest, PlannerMode


@dataclass(frozen=True)
class ValidatedPlannerRequest:
    threat_horizon: int
    target_deadline: int | None
    repair_by_action: dict[str, int]
    recovery_by_action: dict[str, float]
    safety_value_actions: frozenset[str]
    survival_actions: frozenset[str]
    viability_degeneracy: str | None
    viability_relaxation_candidate: bool
    force_terminal_threat: bool


def validate_local_planner_request(
    request: LocalPlannerRequest,
    *,
    planner_action_names: frozenset[str],
    terminal_threat_degeneracy: Callable[..., str | None],
) -> ValidatedPlannerRequest:
    physical = request.physical
    actuator = request.actuator
    guidance = request.guidance
    config = request.config
    objective = request.objective

    if config.horizon <= 0 or config.beam_width <= 0:
        raise ValueError("planner horizon and beam width must be positive")
    if config.beam_dedup_mode not in {
        "quantized",
        "first_action",
        "exact_first_action",
    }:
        raise ValueError("unknown beam deduplication mode")

    threat_horizon = (
        config.horizon
        if config.threat_horizon is None
        else config.threat_horizon
    )
    if threat_horizon < config.horizon:
        raise ValueError(
            "threat horizon cannot be shorter than planner horizon"
        )
    if actuator.control_delay_frames < 0:
        raise ValueError("control delay cannot be negative")
    delay_candidates = actuator.control_delay_candidates
    if delay_candidates is not None:
        if (
            not delay_candidates
            or any(delay < 0 for delay in delay_candidates)
            or tuple(sorted(set(delay_candidates))) != delay_candidates
        ):
            raise ValueError(
                "control delay candidates must be sorted unique nonnegative "
                "frames"
            )
        if actuator.control_delay_frames not in delay_candidates:
            raise ValueError(
                "nominal control delay must belong to its candidates"
            )
    if actuator.action_hold_frames <= 0:
        raise ValueError("action hold must be positive")
    maximum_delay = (
        max(delay_candidates)
        if delay_candidates is not None
        else actuator.control_delay_frames
    )
    required_scale_horizon = max(
        actuator.control_delay_frames + threat_horizon,
        maximum_delay + actuator.action_hold_frames,
    )
    physical.time_scale_schedule.require_complete_horizon(
        required_scale_horizon
    )
    if physical.future_projection_offset < 0:
        raise ValueError("future hazard projection offset cannot be negative")
    future_projection = physical.future_hazard_projection
    if future_projection is None:
        if physical.future_projection_offset:
            raise ValueError(
                "future hazard projection offset requires a projection"
            )
    else:
        if (
            not future_projection.source_closure_complete
            or not future_projection.coverage.complete
            or not (
                future_projection
                .current_pool_callback_composition_complete
            )
        ):
            raise ValueError(
                "local future hazards require complete source and "
                "current-pool callback coverage"
            )
        if (
            physical.future_projection_offset + required_scale_horizon
            > future_projection.horizon_frames
        ):
            raise ValueError(
                "future hazard projection does not cover planner horizon"
            )
    if (
        not math.isfinite(guidance.viability_position_error)
        or guidance.viability_position_error < 0.0
    ):
        raise ValueError(
            "viability position error must be finite and nonnegative"
        )
    if (
        objective.damage_target_x is not None
        and not math.isfinite(objective.damage_target_x)
    ):
        raise ValueError("damage target x must be finite")
    if (
        not math.isfinite(objective.damage_target_half_width)
        or objective.damage_target_half_width < 0.0
    ):
        raise ValueError(
            "damage target half-width must be finite and nonnegative"
        )

    allowed = guidance.allowed_first_actions
    if (
        guidance.allowed_action_authority is not None
        and allowed is None
    ):
        raise ValueError(
            "allowed action authority requires allowed first actions"
        )
    if allowed is not None:
        if not allowed:
            raise ValueError("allowed first actions cannot be empty")
        if len(set(allowed)) != len(allowed):
            raise ValueError("allowed first actions must be unique")
        unknown = set(allowed) - planner_action_names
        if unknown:
            raise ValueError(
                f"unknown allowed first actions: {sorted(unknown)}"
            )

    degeneracy = (
        terminal_threat_degeneracy(
            player_x=physical.player_x,
            player_y=physical.player_y,
            action_hold_frames=actuator.action_hold_frames,
            allowed_first_actions=allowed,
            viability_position_error=(
                guidance.viability_position_error
            ),
        )
        if (
            threat_horizon > config.horizon
            and guidance.allow_coarse_viability_relaxation
        )
        else None
    )

    repair_by_action = dict(guidance.viability_repair_volumes)
    if len(repair_by_action) != len(
        guidance.viability_repair_volumes
    ):
        raise ValueError("viability repair action names must be unique")
    if set(repair_by_action) - planner_action_names:
        raise ValueError("viability repair contains unknown action")
    if any(volume < 0 for volume in repair_by_action.values()):
        raise ValueError("viability repair volume cannot be negative")

    recovery_by_action = dict(
        guidance.viability_recovery_distances
    )
    if len(recovery_by_action) != len(
        guidance.viability_recovery_distances
    ):
        raise ValueError("viability recovery action names must be unique")
    if set(recovery_by_action) - planner_action_names:
        raise ValueError("viability recovery contains unknown action")
    if any(
        not math.isfinite(distance) or distance < 0.0
        for distance in recovery_by_action.values()
    ):
        raise ValueError(
            "viability recovery distance must be finite and nonnegative"
        )

    safety_actions = guidance.viability_safety_actions
    if len(set(safety_actions)) != len(safety_actions):
        raise ValueError("safety-value actions must be unique")
    if set(safety_actions) - planner_action_names:
        raise ValueError("safety value contains unknown action")

    survival_actions = guidance.viability_survival_actions
    if len(set(survival_actions)) != len(survival_actions):
        raise ValueError("survival-label actions must be unique")
    if set(survival_actions) - planner_action_names:
        raise ValueError("survival label contains unknown action")
    if guidance.viability_survival_frames is not None and (
        guidance.viability_survival_frames < 0
        or guidance.viability_survival_frames > 0xFFFF
    ):
        raise ValueError(
            "survival frames must fit an unsigned 16-bit label"
        )
    if (
        guidance.viability_survival_bottleneck_margin is not None
        and not math.isfinite(
            guidance.viability_survival_bottleneck_margin
        )
    ):
        raise ValueError("survival bottleneck margin must be finite")

    if (guidance.target_x is None) != (guidance.target_y is None):
        raise ValueError("target_x and target_y must be supplied together")
    target_deadline = guidance.target_deadline
    if guidance.target_x is not None:
        if target_deadline is None:
            target_deadline = config.horizon
        if target_deadline < 0:
            raise ValueError("target deadline cannot be negative")

    return ValidatedPlannerRequest(
        threat_horizon=threat_horizon,
        target_deadline=target_deadline,
        repair_by_action=repair_by_action,
        recovery_by_action=recovery_by_action,
        safety_value_actions=frozenset(safety_actions),
        survival_actions=frozenset(survival_actions),
        viability_degeneracy=degeneracy,
        viability_relaxation_candidate=degeneracy is not None,
        force_terminal_threat=(
            request.mode is PlannerMode.RELAXED_VIABILITY
        ),
    )
