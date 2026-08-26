"""Independently testable preparation and hard-preflight planner stages."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .models import RobustActionCertificate
from .requests import LocalPlannerRequest
from .validation import (
    ValidatedPlannerRequest,
    validate_local_planner_request,
)


@dataclass(frozen=True)
class PreparedLocalHazards:
    selected_items: tuple[Any, ...]
    delayed_mask: int
    main_laser_offset: int
    certificate_delay_frames: tuple[int, ...]
    diagnostic_losing_reserve_distance: float
    recovery_reserve_distance: float
    certificate_horizon: int
    potential_threat_horizon: int
    laser_timeline: tuple[Any, ...]


@dataclass(frozen=True)
class HardPreflightResult:
    certificates: dict[str, RobustActionCertificate]
    viability_constraint_relaxed: bool
    effective_allowed_first_actions: tuple[str, ...] | None
    viability_fresh_prefix_filtered: bool
    viability_fresh_prefix_relaxed: bool


@dataclass(frozen=True)
class PlannerPassPreparation:
    validated: ValidatedPlannerRequest
    hazards: PreparedLocalHazards
    preflight: HardPreflightResult


def prepare_local_hazards(
    request: LocalPlannerRequest,
    validated: ValidatedPlannerRequest,
    *,
    item_objectives_enabled: bool,
    select_items: Callable[..., tuple[Any, ...]],
    focus_mask: int,
    unfocused_cardinal_speed: float,
    build_laser_timeline: Callable[..., tuple[Any, ...]],
    timing_accumulator: Any,
) -> PreparedLocalHazards:
    physical = request.physical
    actuator = request.actuator
    config = request.config
    objective = request.objective

    selected_items = (
        select_items(
            physical.items,
            power=objective.power,
            bombs=objective.bombs,
        )
        if item_objectives_enabled
        else ()
    )
    delayed_mask = actuator.previous_direction | (
        focus_mask if actuator.previous_focus else 0
    )
    main_laser_offset = max(
        0,
        actuator.control_delay_frames - max(0, physical.snapshot_lag),
    )
    certificate_delay_frames = (
        actuator.control_delay_candidates
        if actuator.control_delay_candidates is not None
        else (actuator.control_delay_frames,)
    )
    latency_control_reserve = (
        unfocused_cardinal_speed * max(certificate_delay_frames)
    )
    # This is actuator reachability, not global-planner advice.  A missing or
    # losing corridor must not erase the distance needed to reverse an input
    # that can remain pending for the full measured delay support.
    diagnostic_reserve = (
        latency_control_reserve
        if (
            validated.recovery_by_action
            or validated.repair_by_action
            or validated.survival_actions
        )
        else 0.0
    )
    recovery_reserve = (
        latency_control_reserve
        if (
            config.recovery_control_reserve
            or (
                config.losing_control_reserve
                and (
                    validated.repair_by_action
                    or validated.survival_actions
                )
            )
        )
        else 0.0
    )
    certificate_horizon = (
        actuator.action_hold_frames + max(certificate_delay_frames)
        if (
            actuator.control_delay_candidates is not None
            or validated.viability_relaxation_candidate
        )
        else 0
    )
    potential_threat_horizon = (
        validated.threat_horizon
        if (
            validated.viability_relaxation_candidate
            or validated.force_terminal_threat
        )
        else config.horizon
    )
    laser_timeline_horizon = max(
        actuator.control_delay_frames,
        main_laser_offset + potential_threat_horizon,
        certificate_horizon,
    )
    started_ns = time.perf_counter_ns()
    laser_timeline = build_laser_timeline(
        physical.lasers,
        horizon=laser_timeline_horizon,
        time_scale_schedule_bits=(
            physical.time_scale_schedule.require_laser_horizon(
                laser_timeline_horizon
            )
        ),
    )
    timing_accumulator.shared_laser_projection_ms += (
        time.perf_counter_ns() - started_ns
    ) / 1_000_000.0
    return PreparedLocalHazards(
        selected_items=selected_items,
        delayed_mask=delayed_mask,
        main_laser_offset=main_laser_offset,
        certificate_delay_frames=certificate_delay_frames,
        diagnostic_losing_reserve_distance=diagnostic_reserve,
        recovery_reserve_distance=recovery_reserve,
        certificate_horizon=certificate_horizon,
        potential_threat_horizon=potential_threat_horizon,
        laser_timeline=laser_timeline,
    )


def run_hard_preflight(
    request: LocalPlannerRequest,
    validated: ValidatedPlannerRequest,
    prepared: PreparedLocalHazards,
    *,
    actions: tuple[Any, ...],
    certificate_provider: Callable[
        ..., dict[str, RobustActionCertificate]
    ],
    timing_accumulator: Any,
) -> HardPreflightResult:
    physical = request.physical
    actuator = request.actuator
    guidance = request.guidance
    config = request.config
    allowed = guidance.allowed_first_actions
    degeneracy = validated.viability_degeneracy
    certificates: dict[str, RobustActionCertificate] = {}

    if (
        actuator.control_delay_candidates is not None
        or degeneracy == "off_grid_singleton"
    ):
        preflight_names = (
            set(allowed)
            if allowed is not None and degeneracy is None
            else None
        )
        preflight_actions = tuple(
            action
            for action in actions
            if preflight_names is None or action.name in preflight_names
        )
        certificates = certificate_provider(
            player_x=physical.player_x,
            player_y=physical.player_y,
            previous_mask=prepared.delayed_mask,
            actions=preflight_actions,
            delay_frames=prepared.certificate_delay_frames,
            action_hold_frames=actuator.action_hold_frames,
            bullets=physical.bullets,
            lasers=physical.lasers,
            enemy_bodies=physical.enemy_bodies,
            snapshot_lag=physical.snapshot_lag,
            player_scale_bits=(
                physical.time_scale_schedule.require_player_horizon(
                    prepared.certificate_horizon
                )
            ),
            laser_scale_bits=(
                physical.time_scale_schedule.require_laser_horizon(
                    prepared.certificate_horizon
                )
            ),
            laser_frames=prepared.laser_timeline[
                : prepared.certificate_horizon
            ],
            pipeline_root=actuator.local_pipeline_root,
            future_hazard_projection=physical.future_hazard_projection,
            future_projection_offset=physical.future_projection_offset,
            timing_accumulator=timing_accumulator,
        )

    viability_certificates = (
        {
            name: certificates[name]
            for name in allowed
            if name in certificates
        }
        if degeneracy == "off_grid_singleton" and allowed is not None
        else {}
    )
    relaxed = (
        degeneracy == "complete_clamped_alias"
        or (
            degeneracy == "off_grid_singleton"
            and not any(
                certificate.worst_collisions == 0
                and certificate.min_clearance >= 0.0
                and validated.repair_by_action.get(action_name, 0) > 1
                for action_name, certificate
                in viability_certificates.items()
            )
        )
    )
    effective_allowed = None if relaxed else allowed
    fresh_filtered = False
    fresh_relaxed = False
    if (
        config.enforce_fresh_viability_intersection
        and effective_allowed is not None
        and certificates
    ):
        locally_safe_global = tuple(
            action_name
            for action_name in effective_allowed
            if (
                certificates[action_name].worst_collisions == 0
                and certificates[action_name].min_clearance >= 0.0
            )
        )
        if locally_safe_global:
            fresh_filtered = (
                len(locally_safe_global) != len(effective_allowed)
            )
            effective_allowed = locally_safe_global
        elif not guidance.allow_coarse_viability_relaxation:
            # An exact action authority may not be widened merely because the
            # shorter-horizon local certificate disagrees.  Preserve the hard
            # set and let ranking choose its least-bad member; the issue-time
            # transaction will recertify the same set against fresh hazards.
            pass
        else:
            certificates = certificate_provider(
                player_x=physical.player_x,
                player_y=physical.player_y,
                previous_mask=prepared.delayed_mask,
                actions=actions,
                delay_frames=prepared.certificate_delay_frames,
                action_hold_frames=actuator.action_hold_frames,
                bullets=physical.bullets,
                lasers=physical.lasers,
                enemy_bodies=physical.enemy_bodies,
                snapshot_lag=physical.snapshot_lag,
                player_scale_bits=(
                    physical.time_scale_schedule.require_player_horizon(
                        prepared.certificate_horizon
                    )
                ),
                laser_scale_bits=(
                    physical.time_scale_schedule.require_laser_horizon(
                        prepared.certificate_horizon
                    )
                ),
                laser_frames=prepared.laser_timeline[
                    : prepared.certificate_horizon
                ],
                pipeline_root=actuator.local_pipeline_root,
                future_hazard_projection=physical.future_hazard_projection,
                future_projection_offset=physical.future_projection_offset,
                timing_accumulator=timing_accumulator,
            )
            locally_safe = tuple(
                action.name
                for action in actions
                if (
                    certificates[action.name].worst_collisions == 0
                    and certificates[action.name].min_clearance >= 0.0
                )
            )
            effective_allowed = locally_safe or None
            relaxed = True
            fresh_relaxed = True

    return HardPreflightResult(
        certificates=certificates,
        viability_constraint_relaxed=relaxed,
        effective_allowed_first_actions=effective_allowed,
        viability_fresh_prefix_filtered=fresh_filtered,
        viability_fresh_prefix_relaxed=fresh_relaxed,
    )


def prepare_planner_pass(
    request: LocalPlannerRequest,
    *,
    planner_action_names: frozenset[str],
    terminal_threat_degeneracy: Callable[..., str | None],
    item_objectives_enabled: bool,
    select_items: Callable[..., tuple[Any, ...]],
    focus_mask: int,
    unfocused_cardinal_speed: float,
    build_laser_timeline: Callable[..., tuple[Any, ...]],
    actions: tuple[Any, ...],
    certificate_provider: Callable[
        ..., dict[str, RobustActionCertificate]
    ],
    timing_accumulator: Any,
) -> PlannerPassPreparation:
    validated = validate_local_planner_request(
        request,
        planner_action_names=planner_action_names,
        terminal_threat_degeneracy=terminal_threat_degeneracy,
    )
    hazards = prepare_local_hazards(
        request,
        validated,
        item_objectives_enabled=item_objectives_enabled,
        select_items=select_items,
        focus_mask=focus_mask,
        unfocused_cardinal_speed=unfocused_cardinal_speed,
        build_laser_timeline=build_laser_timeline,
        timing_accumulator=timing_accumulator,
    )
    preflight = run_hard_preflight(
        request,
        validated,
        hazards,
        actions=actions,
        certificate_provider=certificate_provider,
        timing_accumulator=timing_accumulator,
    )
    return PlannerPassPreparation(
        validated=validated,
        hazards=hazards,
        preflight=preflight,
    )
