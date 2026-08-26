"""Endpoint selection and decision assembly for one live planner pass."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from th08_local_planner import (
    DamageDecisionFields,
    Decision,
    EndpointRanker,
    ObjectiveContext,
    PlannerAction,
    PlannerMode,
    ProposalAssemblyContext,
    RobustActionCertificate,
    SearchNode,
)
from th08_live.planner_pass_baseline import BaselineStagePreparation
from th08_live.planner_pass_types import (
    LocalCertificateTimingAccumulator,
    PlannerModeTransition,
)
from touhou_control.phase_progress import ProgressCandidate


@dataclass(frozen=True)
class PlannerFinalizationContext:
    baseline_stage: BaselineStagePreparation
    beam: tuple[SearchNode, ...]
    terminal_threats: dict[SearchNode, tuple[int, float]]
    continuation_preference_active: bool
    prefix_clearance: float
    observed_player_x: float
    observed_player_y: float
    delayed_mask: int
    laser_timeline: tuple[Any, ...] | list[Any]
    preloss_reserve_distance: float


def finalize_planner_pass(
    context: PlannerFinalizationContext,
    *,
    timing: LocalCertificateTimingAccumulator,
) -> Decision | PlannerModeTransition:
    """Select, assemble, and optionally request the historical relaxed retry."""

    stage = context.baseline_stage
    request = stage.request
    preparation = stage.planner_preparation
    dependencies = stage.dependencies
    physical = request.physical
    actuator = request.actuator
    guidance = request.guidance
    config = request.config
    objective = request.objective
    validated = preparation.validated
    prepared = preparation.hazards
    preflight = preparation.preflight
    actions = dependencies.planner_actions
    beam = list(context.beam)
    endpoint_pool = beam
    terminal_threats = context.terminal_threats
    continuation_preference_active = (
        context.continuation_preference_active
    )
    effective_allowed_first_actions = (
        preflight.effective_allowed_first_actions
    )
    survival_actions = validated.survival_actions
    safety_value_actions = validated.safety_value_actions
    recovery_by_action = validated.recovery_by_action
    repair_by_action = validated.repair_by_action
    recovery_reserve_distance = prepared.recovery_reserve_distance
    target_x = guidance.target_x
    target_y = guidance.target_y
    target_deadline = validated.target_deadline

    selection_started_ns = time.perf_counter_ns()
    endpoint_ranker = EndpointRanker(
        terminal_threats=terminal_threats,
        survival_actions=survival_actions,
        safety_value_actions=safety_value_actions,
        recovery_by_action=recovery_by_action,
        repair_by_action=repair_by_action,
        recovery_reserve_distance=recovery_reserve_distance,
        preloss_reserve_distance=context.preloss_reserve_distance,
        preloss_continuation_preference_active=(
            continuation_preference_active
        ),
        item_safety_clearance=dependencies.item_safety_clearance,
        horizon=config.horizon,
        selected_items=prepared.selected_items,
        target_x=target_x,
        target_y=target_y,
        target_deadline=target_deadline,
        boundary_control_reserve_deficit=(
            dependencies.boundary_control_reserve_deficit
        ),
        node_key=dependencies.node_key,
        minimum_travel_frames=dependencies.minimum_travel_frames,
    )
    historical_selection_key = endpoint_ranker.historical_key
    selection_key = endpoint_ranker.selection_key
    route_gate_deficit = endpoint_ranker.route_gate_deficit

    robust_certificates: dict[str, RobustActionCertificate] = {}
    nodes_by_action: dict[str, SearchNode] = {}
    robust_override = False
    robust_certificate: RobustActionCertificate | None = None
    historical_best = min(beam, key=historical_selection_key)
    historical_route_gate_deficit = route_gate_deficit(historical_best)

    if continuation_preference_active:
        actions_by_name: dict[str, PlannerAction] = {}
        for node in endpoint_pool:
            action_name = node.first_action.name
            actions_by_name[action_name] = node.first_action
        if actuator.control_delay_candidates is not None:
            if actions_by_name.keys() <= preflight.certificates.keys():
                robust_certificates = {
                    action_name: preflight.certificates[action_name]
                    for action_name in actions_by_name
                }
            else:
                robust_certificates = (
                    dependencies.robust_action_certificates(
                        player_x=context.observed_player_x,
                        player_y=context.observed_player_y,
                        previous_mask=context.delayed_mask,
                        actions=tuple(actions_by_name.values()),
                        delay_frames=actuator.control_delay_candidates,
                        action_hold_frames=actuator.action_hold_frames,
                        bullets=physical.bullets,
                        lasers=physical.lasers,
                        enemy_bodies=physical.enemy_bodies,
                        snapshot_lag=physical.snapshot_lag,
                        bullet_snapshot_age_support=(
                            physical.bullet_snapshot_age_support
                        ),
                        laser_frames=context.laser_timeline[
                            : prepared.certificate_horizon
                        ],
                        pipeline_root=actuator.local_pipeline_root,
                        future_hazard_projection=(
                            physical.future_hazard_projection
                        ),
                        future_projection_offset=(
                            physical.future_projection_offset
                        ),
                        timing_accumulator=timing,
                    )
                )

        historical_nodes_by_action: dict[str, SearchNode] = {}
        for node in beam:
            action_name = node.first_action.name
            incumbent = historical_nodes_by_action.get(action_name)
            if (
                incumbent is None
                or historical_selection_key(node)
                < historical_selection_key(incumbent)
            ):
                historical_nodes_by_action[action_name] = node
        historical_provisional = historical_best
        if robust_certificates:
            nominal_certificate = robust_certificates[
                historical_best.first_action.name
            ]
            if (
                nominal_certificate.worst_collisions > 0
                or nominal_certificate.min_clearance < 0.0
            ):
                historical_best = min(
                    historical_nodes_by_action.values(),
                    key=lambda node: (
                        robust_certificates[
                            node.first_action.name
                        ].worst_collisions,
                        max(
                            -robust_certificates[
                                node.first_action.name
                            ].min_clearance,
                            0.0,
                        ),
                        robust_certificates[
                            node.first_action.name
                        ].cvar_risk,
                        -robust_certificates[
                            node.first_action.name
                        ].min_clearance,
                        historical_selection_key(node),
                    ),
                )
                robust_override = (
                    historical_best.first_action
                    != historical_provisional.first_action
                )
        historical_route_gate_deficit = route_gate_deficit(
            historical_best
        )

        def hard_components(
            node: SearchNode,
        ) -> tuple[int | float, ...]:
            threat_collisions, threat_clearance = terminal_threats[node]
            certificate = robust_certificates.get(
                node.first_action.name
            )
            return (
                (
                    certificate.worst_collisions
                    if certificate is not None
                    else 0
                ),
                (
                    max(-certificate.min_clearance, 0.0)
                    if certificate is not None
                    else 0.0
                ),
                node.collisions,
                max(-node.min_clearance, 0.0),
                threat_collisions,
                max(-threat_clearance, 0.0),
            )

        historical_hard = hard_components(historical_best)
        historical_survival_deficit = (
            0
            if (
                not survival_actions
                or historical_best.first_action.name in survival_actions
            )
            else 1
        )
        historical_continuation_key = (
            -repair_by_action.get(
                historical_best.first_action.name,
                0,
            ),
            dependencies.boundary_control_reserve_deficit(
                historical_best.x,
                historical_best.y,
                reserve_distance=context.preloss_reserve_distance,
            ),
        )
        effective_set = set(effective_allowed_first_actions or ())
        admitted: list[SearchNode] = []
        for node in endpoint_pool:
            node_hard = hard_components(node)
            if not all(
                candidate <= incumbent
                for candidate, incumbent in zip(
                    node_hard,
                    historical_hard,
                )
            ):
                continue
            if (
                route_gate_deficit(node)
                > historical_route_gate_deficit
            ):
                continue
            if (
                effective_set
                and node.first_action.name not in effective_set
            ):
                continue
            survival_deficit = (
                0
                if (
                    not survival_actions
                    or node.first_action.name in survival_actions
                )
                else 1
            )
            if survival_deficit > historical_survival_deficit:
                continue
            continuation_key = (
                -repair_by_action.get(node.first_action.name, 0),
                dependencies.boundary_control_reserve_deficit(
                    node.x,
                    node.y,
                    reserve_distance=context.preloss_reserve_distance,
                ),
            )
            if continuation_key >= historical_continuation_key:
                continue
            admitted.append(node)
        best = (
            min(
                admitted,
                key=lambda node: (
                    hard_components(node),
                    (
                        0
                        if (
                            not survival_actions
                            or node.first_action.name
                            in survival_actions
                        )
                        else 1
                    ),
                    -repair_by_action.get(
                        node.first_action.name,
                        0,
                    ),
                    dependencies.boundary_control_reserve_deficit(
                        node.x,
                        node.y,
                        reserve_distance=(
                            context.preloss_reserve_distance
                        ),
                    ),
                    historical_selection_key(node),
                ),
            )
            if admitted
            else historical_best
        )
        for node in endpoint_pool:
            action_name = node.first_action.name
            incumbent = nodes_by_action.get(action_name)
            if (
                incumbent is None
                or selection_key(node) < selection_key(incumbent)
            ):
                nodes_by_action[action_name] = node
        robust_certificate = robust_certificates.get(
            best.first_action.name
        )
    else:
        best = min(beam, key=selection_key)
        if actuator.control_delay_candidates is not None:
            actions_by_name: dict[str, PlannerAction] = {}
            for node in beam:
                action_name = node.first_action.name
                actions_by_name[action_name] = node.first_action
                incumbent = nodes_by_action.get(action_name)
                if incumbent is None or selection_key(
                    node
                ) < selection_key(incumbent):
                    nodes_by_action[action_name] = node
            if actions_by_name.keys() <= preflight.certificates.keys():
                robust_certificates = {
                    action_name: preflight.certificates[action_name]
                    for action_name in actions_by_name
                }
            else:
                robust_certificates = (
                    dependencies.robust_action_certificates(
                        player_x=context.observed_player_x,
                        player_y=context.observed_player_y,
                        previous_mask=context.delayed_mask,
                        actions=tuple(actions_by_name.values()),
                        delay_frames=actuator.control_delay_candidates,
                        action_hold_frames=actuator.action_hold_frames,
                        bullets=physical.bullets,
                        lasers=physical.lasers,
                        enemy_bodies=physical.enemy_bodies,
                        snapshot_lag=physical.snapshot_lag,
                        bullet_snapshot_age_support=(
                            physical.bullet_snapshot_age_support
                        ),
                        laser_frames=context.laser_timeline[
                            : prepared.certificate_horizon
                        ],
                        pipeline_root=actuator.local_pipeline_root,
                        future_hazard_projection=(
                            physical.future_hazard_projection
                        ),
                        future_projection_offset=(
                            physical.future_projection_offset
                        ),
                        timing_accumulator=timing,
                    )
                )
            nominal_certificate = robust_certificates[
                best.first_action.name
            ]
            if (
                nominal_certificate.worst_collisions > 0
                or nominal_certificate.min_clearance < 0.0
            ):
                robust_best = min(
                    nodes_by_action.values(),
                    key=lambda node: (
                        robust_certificates[
                            node.first_action.name
                        ].worst_collisions,
                        max(
                            -robust_certificates[
                                node.first_action.name
                            ].min_clearance,
                            0.0,
                        ),
                        robust_certificates[
                            node.first_action.name
                        ].cvar_risk,
                        -robust_certificates[
                            node.first_action.name
                        ].min_clearance,
                        selection_key(node),
                    ),
                )
                robust_override = (
                    robust_best.first_action != best.first_action
                )
                best = robust_best
            robust_certificate = robust_certificates[
                best.first_action.name
            ]

    damage_target_x = objective.damage_target_x
    damage_reason = "boss_not_damageable"
    if objective.damageable:
        damage_reason = "boss_geometry_unavailable"
    if objective.damageable and damage_target_x is not None:
        damage_reason = "fresh_viability_unavailable"
    if (
        objective.damageable
        and damage_target_x is not None
        and effective_allowed_first_actions is not None
    ):
        damage_reason = (
            "viability_constraint_relaxed"
            if preflight.viability_fresh_prefix_relaxed
            else "issue_certificate_unavailable"
        )
    damage_shadow_action: str | None = None
    damage_baseline_action = best.first_action.name
    damage_current_alignment_cost: float | None = None
    damage_shadow_alignment_cost: float | None = None
    damage_eligible_action_count = 0
    damage_objective_available = bool(
        objective.damageable
        and damage_target_x is not None
        and effective_allowed_first_actions is not None
        and not preflight.viability_fresh_prefix_relaxed
        and robust_certificates
        and nodes_by_action
    )
    if damage_objective_available:
        viable_actions = set(effective_allowed_first_actions or ())
        progress_candidates = tuple(
            ProgressCandidate(
                action=action_name,
                progress_cost=max(
                    abs(node.x - damage_target_x)
                    - objective.damage_target_half_width,
                    0.0,
                ),
                viable=action_name in viable_actions,
                issue_collisions=robust_certificates[
                    action_name
                ].worst_collisions,
                issue_min_clearance=robust_certificates[
                    action_name
                ].min_clearance,
                baseline_rank=selection_key(node),
            )
            for action_name, node in nodes_by_action.items()
        )
        damage_eligible_action_count = sum(
            candidate.viable
            and candidate.issue_collisions == 0
            and candidate.issue_min_clearance >= 0.0
            for candidate in progress_candidates
        )
        damage_candidate = dependencies.select_progress_action(
            progress_candidates
        )
        if damage_candidate is None:
            damage_objective_available = False
            damage_reason = "no_issue_safe_viable_action"
        else:
            damage_reason = "shadow_lexicographic_tiebreak"
            damage_shadow_action = damage_candidate.action
            damage_current_alignment_cost = max(
                abs(best.x - damage_target_x)
                - objective.damage_target_half_width,
                0.0,
            )
            damage_shadow_alignment_cost = damage_candidate.progress_cost

    threat_collisions, threat_clearance = terminal_threats[best]
    decision = dependencies.assemble_local_decision(
        ProposalAssemblyContext(
            request=request,
            validated=validated,
            prepared=prepared,
            preflight=preflight,
            best=best,
            robust_certificate=robust_certificate,
            robust_override=robust_override,
            terminal_threat=(threat_collisions, threat_clearance),
            prefix_clearance=context.prefix_clearance,
            damage=DamageDecisionFields(
                available=damage_objective_available,
                baseline_action=damage_baseline_action,
                shadow_action=damage_shadow_action,
                current_alignment_cost=damage_current_alignment_cost,
                shadow_alignment_cost=damage_shadow_alignment_cost,
                eligible_action_count=damage_eligible_action_count,
                reason=damage_reason,
            ),
            historical_action=(
                historical_best.first_action.name
                if continuation_preference_active
                else None
            ),
            historical_route_gate_deficit=(
                historical_route_gate_deficit
            ),
            route_gate_deficit=route_gate_deficit(best),
            local_collisions=best.collisions,
        ),
        actions=actions,
        shot_mask=dependencies.shot_mask,
        focus_mask=dependencies.focus_mask,
        bomb_mask=dependencies.bomb_mask,
        boundary_control_reserve_deficit=(
            dependencies.boundary_control_reserve_deficit
        ),
    )
    timing.selection_finalize_ms += (
        time.perf_counter_ns() - selection_started_ns
    ) / 1_000_000.0

    if (
        effective_allowed_first_actions is not None
        and prepared.potential_threat_horizon > config.horizon
        and (
            threat_collisions > 0
            or decision.robust_collisions > 0
            or decision.min_clearance <= 0.0
        )
        and config.relax_stale_viability_contradiction
        and request.mode is not PlannerMode.RELAXED_VIABILITY
    ):
        return PlannerModeTransition(
            current_decision=decision,
            next_request=replace(
                request,
                physical=replace(
                    physical,
                    player_x=context.observed_player_x,
                    player_y=context.observed_player_y,
                ),
                guidance=replace(
                    guidance,
                    allowed_first_actions=None,
                ),
                # Preserve the historical retry contract: damage guidance was
                # not forwarded into the relaxed pass.
                objective=ObjectiveContext(
                    power=objective.power,
                    bombs=objective.bombs,
                ),
                mode=PlannerMode.RELAXED_VIABILITY,
            ),
            original_allowed_action_count=len(
                guidance.allowed_first_actions or ()
            ),
        )
    return replace(
        decision,
        local_certificate_timing=timing.snapshot(),
    )


__all__ = [
    "PlannerFinalizationContext",
    "finalize_planner_pass",
]
