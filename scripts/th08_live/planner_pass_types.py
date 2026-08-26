"""Shared contracts for the staged live local-planner pass."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from th08_local_planner import (
    Decision,
    LocalCertificateTiming,
    LocalPlannerRequest,
    PlannerAction,
)


@dataclass
class LocalCertificateTimingAccumulator:
    calls: int = 0
    explicit_root_calls: int = 0
    maximum_branch_count: int = 0
    shared_laser_projection_ms: float = 0.0
    validation_ms: float = 0.0
    hazard_projection_ms: float = 0.0
    branch_setup_ms: float = 0.0
    geometry_kernel_ms: float = 0.0
    reduction_ms: float = 0.0
    certificate_total_ms: float = 0.0
    control_prefix_ms: float = 0.0
    planning_bullet_projection_ms: float = 0.0
    beam_search_ms: float = 0.0
    terminal_threat_ms: float = 0.0
    selection_finalize_ms: float = 0.0

    def snapshot(self) -> LocalCertificateTiming:
        return LocalCertificateTiming(
            calls=self.calls,
            explicit_root_calls=self.explicit_root_calls,
            maximum_branch_count=self.maximum_branch_count,
            shared_laser_projection_ms=self.shared_laser_projection_ms,
            validation_ms=self.validation_ms,
            hazard_projection_ms=self.hazard_projection_ms,
            branch_setup_ms=self.branch_setup_ms,
            geometry_kernel_ms=self.geometry_kernel_ms,
            reduction_ms=self.reduction_ms,
            certificate_total_ms=self.certificate_total_ms,
            control_prefix_ms=self.control_prefix_ms,
            planning_bullet_projection_ms=(
                self.planning_bullet_projection_ms
            ),
            beam_search_ms=self.beam_search_ms,
            terminal_threat_ms=self.terminal_threat_ms,
            selection_finalize_ms=self.selection_finalize_ms,
        )


@dataclass(frozen=True)
class PlannerModeTransition:
    current_decision: Decision
    next_request: LocalPlannerRequest
    original_allowed_action_count: int


@dataclass(frozen=True)
class PlannerPassDependencies:
    """Controller-owned constants and hazard callbacks used by one pass."""

    planner_actions: tuple[PlannerAction, ...]
    local_beam_reducer: str
    bomb_mask: int
    focus_mask: int
    shot_mask: int
    collection_half_width: float
    item_safety_clearance: float
    player_radius: float
    playfield_left: float
    playfield_right: float
    playfield_top: float
    playfield_bottom: float
    unfocused_cardinal_speed: float
    unfocused_diagonal_speed: float
    boundary_control_reserve_deficit: Callable[..., float]
    boundary_risk: Callable[[float, float], float]
    build_bullet_frames: Callable[..., Any]
    bind_future_hazard_query: Callable[..., Any]
    control_prefix_hazards: Callable[..., Any]
    directions_opposed: Callable[[int, int], bool]
    hazards_for_positions: Callable[..., Any]
    minimum_travel_frames: Callable[..., float]
    node_key: Callable[..., tuple[object, ...]]
    project_item: Callable[..., tuple[float, float, float]]
    advance_planner_action: Callable[..., tuple[float, float]]
    project_player_for_read_lag: Callable[..., tuple[float, float]]
    robust_action_certificates: Callable[..., Any]
    terminal_threat_scores: Callable[..., Any]
    assemble_local_decision: Callable[..., Decision]
    run_baseline_beam: Callable[..., Any]
    select_progress_action: Callable[..., Any]


__all__ = [
    "LocalCertificateTimingAccumulator",
    "PlannerModeTransition",
    "PlannerPassDependencies",
]
