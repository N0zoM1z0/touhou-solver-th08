#!/usr/bin/env python3
"""Pure decision/control fields for post-issue live trace records."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from th08_live.iteration import FreshIssueResult


@dataclass(frozen=True)
class DecisionControlTraceInput:
    """Already-observed values needed to serialize one issued decision."""

    issue: FreshIssueResult
    delay_estimate: Any
    control_delay_frames: int
    action_hold_frames: int
    input_state: Mapping[str, object]
    local_pipeline_root_record: dict[str, object] | None
    local_pipeline_certificate_shadow: dict[str, object] | None
    corridor_target: tuple[float, float, int] | None
    damage_target_x: float | None
    damage_target_half_width: float
    damageable: bool
    active_item_count: int | None
    item_objectives_enabled: bool
    corridor_context_changed: bool
    policy_guidance: Any
    player: Mapping[str, object]
    projected_player_x: float
    projected_player_y: float
    control_origin_x: float
    control_origin_y: float
    phase_at_action: int
    predeath_at_action: bool
    local_horizon: int
    serialized_enemy_bodies: Sequence[object]
    hit_started: bool
    hit_count: int
    auto_confirm_event: str | None
    kill_before_saturation: Mapping[str, object] | None = None


def build_decision_control_trace_fields(
    trace_input: DecisionControlTraceInput,
    *,
    local_certificate_timing_record: Callable[[Any], dict[str, object]],
) -> dict[str, object]:
    """Return schema-stable control fields without sensing or side effects."""

    issue = trace_input.issue
    decision = issue.decision
    alignment = issue.alignment
    dispatch = issue.dispatch
    delay_estimate = trace_input.delay_estimate
    guidance = trace_input.policy_guidance
    corridor_target = trace_input.corridor_target
    player = trace_input.player

    return {
        "deadline_guard": {
            "missed": issue.deadline_missed,
            "support_high": alignment.support_high,
            "post_capture_advance": alignment.post_capture_advance,
            "input_suppressed": issue.deadline_missed,
            "planned_action": issue.planned_action,
            "planned_mask": issue.planned_mask,
            "issued_action": decision.action,
            "issued_mask": decision.mask,
        },
        "control_delay_frames": trace_input.control_delay_frames,
        "control_delay_candidates": delay_estimate.support,
        "control_delay_sample_count": delay_estimate.end_to_end_samples,
        "control_delay_estimator": {
            "computation_samples": delay_estimate.computation_samples,
            "pickup_samples": delay_estimate.pickup_samples,
            "end_to_end_samples": delay_estimate.end_to_end_samples,
            "guard_active": delay_estimate.guard_active,
            "overruns": delay_estimate.overruns,
            "censored": delay_estimate.censored,
        },
        "action_hold_frames": trace_input.action_hold_frames,
        "input_snapshot": {
            "raw": trace_input.input_state["input_raw"],
            "current": trace_input.input_state["input_current"],
            "previous": trace_input.input_state["input_previous"],
        },
        "input_dispatch": {
            "role": "observed_issue_transaction",
            "previous_mask": dispatch.previous_mask,
            "target_mask": dispatch.target_mask,
            "write_required": bool(dispatch.transitions),
            "transition_count": len(dispatch.transitions),
            "transitions": [
                [transition.bit, transition.pressed]
                for transition in dispatch.transitions
            ],
            "estimator_issued": bool(dispatch.transitions),
        },
        "local_pipeline_root": trace_input.local_pipeline_root_record,
        "local_pipeline_timing": {
            "planning": local_certificate_timing_record(
                decision.local_certificate_timing
            ),
            "issue_recertificate": local_certificate_timing_record(
                decision.issue_certificate_timing
            ),
        },
        "local_pipeline_certificate_shadow": (
            trace_input.local_pipeline_certificate_shadow
        ),
        "planner_objective": {
            "corridor_target": (
                {
                    "x": corridor_target[0],
                    "y": corridor_target[1],
                    "deadline": corridor_target[2],
                }
                if corridor_target is not None
                else None
            ),
            "damage_target_x": trace_input.damage_target_x,
            "damage_target_half_width": trace_input.damage_target_half_width,
            "damageable": trace_input.damageable,
            "active_items": trace_input.active_item_count,
            "item_objectives_enabled": trace_input.item_objectives_enabled,
            "damage_action_authority": False,
            "preserve_previous_direction_inertia": (
                not trace_input.corridor_context_changed
            ),
            "corridor_context_changed": trace_input.corridor_context_changed,
        },
        "planner_guidance": {
            "support_covers_current": guidance.support_covers_current,
            "allowed_first_actions": guidance.allowed_first_actions,
            "repair_volumes": dict(guidance.repair_volumes),
            "recovery_distances": dict(guidance.recovery_distances),
            "safety_actions": guidance.safety_actions,
            "safety_state_value": guidance.safety_state_value,
            "survival_actions": guidance.survival_actions,
            "survival_frames": guidance.survival_frames,
            "survival_bottleneck_margin": (
                guidance.survival_bottleneck_margin
            ),
            "position_error": guidance.position_error,
        },
        "player": {
            "x": player["x"],
            "y": player["y"],
            "projected_x": trace_input.projected_player_x,
            "projected_y": trace_input.projected_player_y,
            "control_origin_x": trace_input.control_origin_x,
            "control_origin_y": trace_input.control_origin_y,
            "phase": player["phase"],
            "phase_at_action": trace_input.phase_at_action,
            "predeath_at_action": trace_input.predeath_at_action,
            "focus_logic": player.get("focus_logic"),
            "secondary_character_active": player.get(
                "secondary_character_active"
            ),
            "focus_transition_counter": player.get(
                "focus_transition_counter"
            ),
        },
        "damage_objective": {
            "role": "shadow",
            "available": decision.damage_objective_available,
            "reason": decision.damage_reason,
            "target_x": trace_input.damage_target_x,
            "target_half_width": trace_input.damage_target_half_width,
            "baseline_action": decision.damage_baseline_action,
            "shadow_action": decision.damage_shadow_action,
            "issued_action": decision.action,
            "live_selected": False,
            "current_alignment_cost": decision.damage_current_alignment_cost,
            "shadow_alignment_cost": decision.damage_shadow_alignment_cost,
            "eligible_action_count": decision.damage_eligible_action_count,
        },
        "kill_before_saturation": trace_input.kill_before_saturation,
        "action": decision.action,
        "mask": decision.mask,
        "focused": decision.planned_focus,
        "minimum_clearance": decision.min_clearance,
        "immediate_clearance": decision.immediate_clearance,
        "pipeline_clearance": decision.pipeline_clearance,
        "robust_control": {
            "delay_frames": decision.robust_delay_frames,
            "override": decision.robust_override,
            "worst_collisions": decision.robust_collisions,
            "min_clearance": decision.robust_min_clearance,
            "cvar_risk": decision.robust_cvar_risk,
            "worst_delay": decision.robust_worst_delay,
            "viability_constrained": decision.viability_constrained,
            "viability_safe_action_count": (
                decision.viability_safe_action_count
            ),
            "viability_repair_volume": decision.viability_repair_volume,
            "viability_constraint_relaxed": (
                decision.viability_constraint_relaxed
            ),
            "viability_recovery_distance": (
                decision.viability_recovery_distance
            ),
            "viability_control_reserve_deficit": (
                decision.viability_control_reserve_deficit
            ),
            "viability_control_reserve_valid": (
                decision.viability_control_reserve_valid
            ),
            "preloss_continuation_preference_active": (
                decision.preloss_continuation_preference_active
            ),
            "planned_route_gate_deficit": decision.planned_route_gate_deficit,
            "local_collisions": decision.local_collisions,
            "preloss_historical_action": decision.preloss_historical_action,
            "preloss_historical_route_gate_deficit": (
                decision.preloss_historical_route_gate_deficit
            ),
            "viability_safety_value_preferred": (
                decision.viability_safety_value_preferred
            ),
            "viability_safety_state_value": (
                decision.viability_safety_state_value
            ),
            "viability_fresh_prefix_filtered": (
                decision.viability_fresh_prefix_filtered
            ),
            "viability_fresh_prefix_relaxed": (
                decision.viability_fresh_prefix_relaxed
            ),
            "viability_survival_preferred": (
                decision.viability_survival_preferred
            ),
            "viability_survival_frames": decision.viability_survival_frames,
            "viability_survival_bottleneck_margin": (
                decision.viability_survival_bottleneck_margin
            ),
        },
        "terminal_threat": {
            "mode": (
                "constant_terminal_action_heuristic"
                if decision.terminal_threat_horizon > trace_input.local_horizon
                else "disabled_no_degenerate_boundary"
            ),
            "horizon_frames": decision.terminal_threat_horizon,
            "collisions": decision.terminal_threat_collisions,
            "min_clearance": decision.terminal_threat_min_clearance,
        },
        "score": decision.score,
        "item_utility": decision.item_utility,
        "predicted_collections": decision.predicted_collections,
        "bomb": decision.bomb,
        "hit_started": trace_input.hit_started,
        "hit_count": trace_input.hit_count,
        "auto_confirm": trace_input.auto_confirm_event,
        "enemy_bodies": list(trace_input.serialized_enemy_bodies),
    }


__all__ = [
    "DecisionControlTraceInput",
    "build_decision_control_trace_fields",
]
