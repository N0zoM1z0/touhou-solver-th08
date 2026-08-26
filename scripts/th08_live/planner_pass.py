"""One complete local-planner pass behind an explicit controller boundary."""

from __future__ import annotations

import math
import time
from dataclasses import replace

from th08_local_planner import (
    Decision,
    LocalPlannerRequest,
    PlannerPassPreparation,
    SearchNode,
)
from th08_live.planner_pass_baseline import (
    prepare_baseline_stage,
    run_baseline_stage,
)
from th08_live.planner_pass_finalize import (
    PlannerFinalizationContext,
    finalize_planner_pass,
)
from th08_live.planner_pass_types import (
    LocalCertificateTimingAccumulator,
    PlannerModeTransition,
    PlannerPassDependencies,
)
def _run_local_planner_pass(
    request: LocalPlannerRequest,
    preparation: PlannerPassPreparation,
    *,
    dependencies: PlannerPassDependencies,
    _certificate_timing_accumulator: (
        LocalCertificateTimingAccumulator
    ),
) -> Decision | PlannerModeTransition:
    _PLANNER_ACTIONS = dependencies.planner_actions
    FOCUS = dependencies.focus_mask
    SHOT = dependencies.shot_mask
    _boundary_control_reserve_deficit = (
        dependencies.boundary_control_reserve_deficit
    )
    _build_bullet_frames = dependencies.build_bullet_frames
    _control_prefix_hazards = dependencies.control_prefix_hazards
    _node_key = dependencies.node_key
    _project_player_for_read_lag = (
        dependencies.project_player_for_read_lag
    )

    physical = request.physical
    actuator = request.actuator
    guidance = request.guidance
    config = request.config

    player_x = physical.player_x
    player_y = physical.player_y
    bullets = physical.bullets
    lasers = physical.lasers
    enemy_bodies = physical.enemy_bodies
    snapshot_lag = physical.snapshot_lag

    control_delay_frames = actuator.control_delay_frames
    control_delay_candidates = actuator.control_delay_candidates

    target_x = guidance.target_x
    target_y = guidance.target_y
    target_deadline = guidance.target_deadline
    allowed_first_actions = guidance.allowed_first_actions

    preloss_continuation_preference = (
        config.preloss_continuation_preference
    )
    validated = preparation.validated
    target_deadline = validated.target_deadline
    repair_by_action = validated.repair_by_action
    recovery_by_action = validated.recovery_by_action
    safety_value_actions = validated.safety_value_actions
    survival_actions = validated.survival_actions
    observed_player_x = player_x
    observed_player_y = player_y
    prepared = preparation.hazards
    selected_items = prepared.selected_items
    delayed_mask = prepared.delayed_mask
    main_laser_offset = prepared.main_laser_offset
    diagnostic_losing_reserve_distance = (
        prepared.diagnostic_losing_reserve_distance
    )
    recovery_reserve_distance = prepared.recovery_reserve_distance
    potential_threat_horizon = prepared.potential_threat_horizon
    laser_timeline = prepared.laser_timeline
    preflight = preparation.preflight
    robust_preflight_certificates = preflight.certificates
    viability_constraint_relaxed = (
        preflight.viability_constraint_relaxed
    )
    effective_allowed_first_actions = (
        preflight.effective_allowed_first_actions
    )
    viability_fresh_prefix_relaxed = (
        preflight.viability_fresh_prefix_relaxed
    )
    effective_action_names = set(effective_allowed_first_actions or ())
    preloss_continuation_preference_active = bool(
        preloss_continuation_preference
        and allowed_first_actions is not None
        and effective_action_names
        and not viability_constraint_relaxed
        and not viability_fresh_prefix_relaxed
        and effective_action_names <= repair_by_action.keys()
    )
    preloss_reserve_distance = (
        diagnostic_losing_reserve_distance
        if preloss_continuation_preference_active
        else 0.0
    )
    effective_threat_horizon = potential_threat_horizon
    control_prefix_started_ns = time.perf_counter_ns()
    prefix_risk, prefix_collisions, prefix_clearance = _control_prefix_hazards(
        player_x=player_x,
        player_y=player_y,
        input_mask=delayed_mask,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        frames=control_delay_frames,
        player_scale_bits=(
            physical.time_scale_schedule.require_player_horizon(
                control_delay_frames
            )
        ),
        laser_scale_bits=(
            physical.time_scale_schedule.require_laser_horizon(
                control_delay_frames
            )
        ),
        laser_frames=laser_timeline[:control_delay_frames],
        future_hazard_projection=physical.future_hazard_projection,
        future_projection_offset=physical.future_projection_offset,
    )
    _certificate_timing_accumulator.control_prefix_ms += (
        time.perf_counter_ns() - control_prefix_started_ns
    ) / 1_000_000.0
    player_x, player_y = _project_player_for_read_lag(
        player_x,
        player_y,
        delayed_mask,
        control_delay_frames,
        player_scale_bits=(
            physical.time_scale_schedule.require_player_horizon(
                control_delay_frames
            )
        ),
    )
    planning_projection_started_ns = time.perf_counter_ns()
    bullet_frames = _build_bullet_frames(
        bullets,
        horizon=effective_threat_horizon,
        snapshot_lag=max(
            0,
            control_delay_frames - max(0, snapshot_lag),
        ),
    )
    _certificate_timing_accumulator.planning_bullet_projection_ms += (
        time.perf_counter_ns() - planning_projection_started_ns
    ) / 1_000_000.0
    laser_frames = laser_timeline[
        main_laser_offset:
        main_laser_offset + effective_threat_horizon
    ]
    if len(laser_frames) < effective_threat_horizon:
        raise RuntimeError(
            "shared laser timeline does not cover local planning horizon"
        )
    neutral = _PLANNER_ACTIONS[0]
    beam = [
        SearchNode(
            player_x,
            player_y,
            neutral,
            neutral,
            prefix_risk,
            prefix_collisions,
            prefix_clearance,
            prefix_clearance,
            0,
            0.0,
        )
    ]
    initial_node = beam[0]

    def pruning_key(
        node: SearchNode,
        *,
        step: int,
    ) -> tuple[object, ...]:
        base = _node_key(
            node,
            step=step,
            selected_items=selected_items,
            target_x=target_x,
            target_y=target_y,
            target_deadline=target_deadline,
        )
        certificate = robust_preflight_certificates.get(
            node.first_action.name
        )
        return (
            base[0],
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
            max(-node.min_clearance, 0.0),
            (
                0
                if (
                    not survival_actions
                    or node.first_action.name in survival_actions
                )
                else 1
            ),
            base[1],
            base[2],
            (
                0
                if (
                    not safety_value_actions
                    or node.first_action.name in safety_value_actions
                )
                else 1
            ),
            _boundary_control_reserve_deficit(
                node.x,
                node.y,
                reserve_distance=recovery_reserve_distance,
            ),
            recovery_by_action.get(node.first_action.name, math.inf),
            *base[3:],
        )

    if (
        not bullets
        and not lasers
        and not enemy_bodies
        and not selected_items
        and target_x is None
        and allowed_first_actions is None
        and not repair_by_action
        and not recovery_by_action
        and not safety_value_actions
        and not survival_actions
        and physical.future_hazard_projection is None
    ):
        return Decision(
            SHOT | FOCUS,
            "stay",
            9999.0,
            9999.0,
            0.0,
            False,
            robust_delay_frames=control_delay_candidates or (),
            local_certificate_timing=(
                _certificate_timing_accumulator.snapshot()
            ),
        )
    baseline_stage = prepare_baseline_stage(
        request=request,
        planner_preparation=preparation,
        dependencies=dependencies,
    )
    baseline_result = run_baseline_stage(
        baseline_stage,
        initial_beam=beam,
        bullet_frames=bullet_frames,
        laser_frames=laser_frames,
        pruning_key=pruning_key,
    )
    beam = list(baseline_result.beam)
    if not beam:
        beam = [
            SearchNode(
                initial_node.x,
                initial_node.y,
                neutral,
                neutral,
                1e12,
                1,
                -9999.0,
                -9999.0,
                0,
                0.0,
            )
        ]
    positioned_beam: list[SearchNode] = []
    for node in beam:
        if target_x is None or target_y is None:
            position_cost = (
                ((node.x - 192.0) / 96.0) ** 2
                + ((node.y - 400.0) / 128.0) ** 2
            )
        else:
            position_cost = 0.25 * (
                ((node.x - target_x) / 8.0) ** 2
                + ((node.y - target_y) / 8.0) ** 2
            )
        positioned_beam.append(
            replace(node, risk=node.risk + position_cost)
        )
    beam = positioned_beam
    _certificate_timing_accumulator.beam_search_ms += (
        time.perf_counter_ns() - baseline_result.started_ns
    ) / 1_000_000.0
    terminal_started_ns = time.perf_counter_ns()
    terminal_threats = dependencies.terminal_threat_scores(
        beam,
        start_step=config.horizon,
        end_step=effective_threat_horizon,
        control_delay_frames=control_delay_frames,
        bullet_frames=bullet_frames,
        laser_frames=laser_frames,
        enemy_bodies=enemy_bodies,
        future_hazard_projection=physical.future_hazard_projection,
        future_projection_offset=physical.future_projection_offset,
    )
    _certificate_timing_accumulator.terminal_threat_ms += (
        time.perf_counter_ns() - terminal_started_ns
    ) / 1_000_000.0
    return finalize_planner_pass(
        PlannerFinalizationContext(
            baseline_stage=baseline_stage,
            beam=tuple(beam),
            terminal_threats=terminal_threats,
            continuation_preference_active=(
                preloss_continuation_preference_active
            ),
            prefix_clearance=prefix_clearance,
            observed_player_x=observed_player_x,
            observed_player_y=observed_player_y,
            delayed_mask=delayed_mask,
            laser_timeline=laser_timeline,
            preloss_reserve_distance=preloss_reserve_distance,
        ),
        timing=_certificate_timing_accumulator,
    )
