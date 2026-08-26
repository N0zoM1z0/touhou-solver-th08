"""Baseline beam preparation and execution for one live planner pass."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from th08_local_planner import (
    BaselineBeamContext,
    LocalPlannerRequest,
    PlannerPassPreparation,
    SearchNode,
)
from th08_live.planner_pass_types import PlannerPassDependencies
from touhou_control import native_backend


@dataclass(frozen=True)
class BaselineStagePreparation:
    request: LocalPlannerRequest
    planner_preparation: PlannerPassPreparation
    dependencies: PlannerPassDependencies
    native_beam_enabled: bool
    planner_action_indices: dict[str, int]
    native_certificate_collisions: np.ndarray
    native_certificate_minimum: np.ndarray
    native_survival_preferred: np.ndarray
    native_safety_preferred: np.ndarray
    native_recovery_distance: np.ndarray


@dataclass(frozen=True)
class BaselineStageResult:
    beam: tuple[SearchNode, ...]
    started_ns: int


def prepare_baseline_stage(
    *,
    request: LocalPlannerRequest,
    planner_preparation: PlannerPassPreparation,
    dependencies: PlannerPassDependencies,
) -> BaselineStagePreparation:
    """Prepare reducer metadata for the active baseline beam."""

    selected_items = planner_preparation.hazards.selected_items
    validated = planner_preparation.validated
    robust_certificates = planner_preparation.preflight.certificates
    actions = dependencies.planner_actions
    native_beam_enabled = (
        dependencies.local_beam_reducer == "native"
        and request.config.beam_dedup_mode == "quantized"
        and not selected_items
    )
    planner_action_indices: dict[str, int] = {}
    certificate_collisions = np.empty(0, dtype=np.int32)
    certificate_minimum = np.empty(0, dtype=np.float64)
    survival_preferred = np.empty(0, dtype=np.uint8)
    safety_preferred = np.empty(0, dtype=np.uint8)
    recovery_distance = np.empty(0, dtype=np.float64)
    if native_beam_enabled:
        planner_action_indices = {
            action.name: index for index, action in enumerate(actions)
        }
        certificate_collisions = np.fromiter(
            (
                robust_certificates[action.name].worst_collisions
                if action.name in robust_certificates
                else 0
                for action in actions
            ),
            dtype=np.int32,
            count=len(actions),
        )
        certificate_minimum = np.fromiter(
            (
                robust_certificates[action.name].min_clearance
                if action.name in robust_certificates
                else 0.0
                for action in actions
            ),
            dtype=np.float64,
            count=len(actions),
        )
        survival_preferred = np.fromiter(
            (
                not validated.survival_actions
                or action.name in validated.survival_actions
                for action in actions
            ),
            dtype=np.uint8,
            count=len(actions),
        )
        safety_preferred = np.fromiter(
            (
                not validated.safety_value_actions
                or action.name in validated.safety_value_actions
                for action in actions
            ),
            dtype=np.uint8,
            count=len(actions),
        )
        recovery_distance = np.fromiter(
            (
                validated.recovery_by_action.get(action.name, math.inf)
                for action in actions
            ),
            dtype=np.float64,
            count=len(actions),
        )
    return BaselineStagePreparation(
        request=request,
        planner_preparation=planner_preparation,
        dependencies=dependencies,
        native_beam_enabled=native_beam_enabled,
        planner_action_indices=planner_action_indices,
        native_certificate_collisions=certificate_collisions,
        native_certificate_minimum=certificate_minimum,
        native_survival_preferred=survival_preferred,
        native_safety_preferred=safety_preferred,
        native_recovery_distance=recovery_distance,
    )


def run_baseline_stage(
    stage: BaselineStagePreparation,
    *,
    initial_beam: Sequence[SearchNode],
    bullet_frames: Sequence[Any],
    laser_frames: Sequence[Any],
    pruning_key: Callable[..., tuple[object, ...]],
) -> BaselineStageResult:
    """Run the historical baseline beam without changing its rank contract."""

    request = stage.request
    planner_preparation = stage.planner_preparation
    dependencies = stage.dependencies
    actuator = request.actuator
    guidance = request.guidance
    config = request.config
    prepared = planner_preparation.hazards
    validated = planner_preparation.validated
    started_ns = time.perf_counter_ns()
    hazard_query = dependencies.bind_future_hazard_query(
        future_hazard_projection=(
            request.physical.future_hazard_projection
        ),
        future_projection_offset=(
            request.physical.future_projection_offset
        ),
        required_horizon=(
            actuator.control_delay_frames + config.horizon
        ),
    )
    beam = dependencies.run_baseline_beam(
        BaselineBeamContext(
            initial_beam=tuple(initial_beam),
            actions=dependencies.planner_actions,
            action_hold_frames=actuator.action_hold_frames,
            horizon=config.horizon,
            effective_allowed_first_actions=(
                planner_preparation.preflight.effective_allowed_first_actions
            ),
            preserve_previous_direction_inertia=(
                config.preserve_previous_direction_inertia
            ),
            previous_direction=actuator.previous_direction,
            previous_focus=actuator.previous_focus,
            selected_items=prepared.selected_items,
            control_delay_frames=actuator.control_delay_frames,
            bullet_frames=bullet_frames,
            laser_frames=laser_frames,
            enemy_bodies=request.physical.enemy_bodies,
            native_beam_enabled=stage.native_beam_enabled,
            planner_action_indices=stage.planner_action_indices,
            native_certificate_collisions=(
                stage.native_certificate_collisions
            ),
            native_certificate_minimum=stage.native_certificate_minimum,
            native_survival_preferred=stage.native_survival_preferred,
            native_safety_preferred=stage.native_safety_preferred,
            native_recovery_distance=stage.native_recovery_distance,
            beam_width=config.beam_width,
            beam_dedup_mode=config.beam_dedup_mode,
            target_x=guidance.target_x,
            target_y=guidance.target_y,
            target_deadline=validated.target_deadline,
            item_safety_clearance=dependencies.item_safety_clearance,
            collection_half_width=dependencies.collection_half_width,
            playfield_left=dependencies.playfield_left,
            playfield_right=dependencies.playfield_right,
            playfield_top=dependencies.playfield_top,
            playfield_bottom=dependencies.playfield_bottom,
            recovery_reserve_distance=(
                prepared.recovery_reserve_distance
            ),
            diagonal_speed=dependencies.unfocused_diagonal_speed,
            cardinal_speed=dependencies.unfocused_cardinal_speed,
            player_scale_bits=(
                request.physical.time_scale_schedule.require_player_horizon(
                    actuator.control_delay_frames + config.horizon
                )[actuator.control_delay_frames:]
            ),
        ),
        boundary_risk=dependencies.boundary_risk,
        directions_opposed=dependencies.directions_opposed,
        project_item=dependencies.project_item,
        advance_action=dependencies.advance_planner_action,
        hazard_query=hazard_query,
        pruning_key=pruning_key,
        native_reducer=native_backend.reduce_local_beam,
    )
    return BaselineStageResult(beam=tuple(beam), started_ns=started_ns)


__all__ = [
    "BaselineStagePreparation",
    "BaselineStageResult",
    "prepare_baseline_stage",
    "run_baseline_stage",
]
