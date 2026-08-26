"""Immutable stage contracts for one live-controller decision iteration.

These records do not implement control policy. They make the physical-frame,
service-publication, guidance-lookup, and fresh-issue boundaries explicit so
the live loop can be decomposed without moving mutable controller ownership
between modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from th08_laser_runtime import Laser
from th08_local_planner import Decision, LocalProposal
from th08_time_scale import (
    Th08TimeScaleSchedule,
    validate_time_scale_bits,
)
from touhou_control.delay import DelayEstimate
from touhou_control.epochs import ActionIssueAlignment, HazardEpochAlignment

from .issue_controller import InputDispatch
from .models import Bullet, EnemyBody, Item, PackedBulletSnapshot
from .pipeline_shadow import PipelineShadowSnapshot


def _finite(value: float, field: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True)
class CapturedIteration:
    """One coherent native observation and decoded hazard snapshot."""

    gameplay_epoch: int
    stage_route_index: int
    spell_id: int | None
    context_key: tuple[int, int, int | None]
    source_frame: int
    snapshot_frame: int
    source_time_scale_bits: int
    time_scale_schedule: Th08TimeScaleSchedule
    player_projection_authority: str
    player_x: float
    player_y: float
    projected_player_x: float
    projected_player_y: float
    native_active_mask: int
    held_desired_mask: int
    previous_direction: int
    can_bomb: bool
    power: float
    bombs: float
    bullets: tuple[Bullet, ...] | PackedBulletSnapshot
    lasers: tuple[Laser, ...]
    enemy_bodies: tuple[EnemyBody, ...]
    items: tuple[Item, ...]
    hazard_alignment: HazardEpochAlignment
    snapshot_lag: int
    player_to_hazard_lag: int
    hazard_snapshot_age: int
    bullet_snapshot_age_support: tuple[int, ...]
    delay_estimate: DelayEstimate
    control_delay_frames: int
    context_changed: bool

    def __post_init__(self) -> None:
        if self.gameplay_epoch < 0:
            raise ValueError("gameplay epoch cannot be negative")
        if self.stage_route_index < 0:
            raise ValueError("stage route index cannot be negative")
        if self.context_key != (
            self.gameplay_epoch,
            self.stage_route_index,
            self.spell_id,
        ):
            raise ValueError("capture context key does not match its components")
        if self.source_frame < 0 or self.snapshot_frame < self.source_frame:
            raise ValueError("capture frames must be ordered and nonnegative")
        if self.snapshot_frame != self.hazard_alignment.current_frame:
            raise ValueError("capture frame must match hazard-alignment current frame")
        if self.source_frame != self.hazard_alignment.source_frame:
            raise ValueError("source frame must match hazard alignment")
        if self.snapshot_lag != self.snapshot_frame - self.source_frame:
            raise ValueError("snapshot lag does not match capture frames")
        validate_time_scale_bits(
            self.source_time_scale_bits,
            field="captured source time scale",
        )
        if self.time_scale_schedule.source_frame != self.snapshot_frame:
            raise ValueError(
                "time-scale schedule source frame must match capture frame"
            )
        if self.player_projection_authority not in {
            "exact_current_control_root",
            "exact_zero_lag",
            "exact_source_root_one_step",
            "unknown_incomplete_source_schedule",
        }:
            raise ValueError("unknown player projection authority")
        if self.player_to_hazard_lag != self.hazard_alignment.source_to_hazard_lag:
            raise ValueError("player-to-hazard lag does not match alignment")
        if self.hazard_snapshot_age != self.hazard_alignment.hazard_age:
            raise ValueError("hazard age does not match alignment")
        if (
            not self.bullet_snapshot_age_support
            or tuple(sorted(set(self.bullet_snapshot_age_support)))
            != self.bullet_snapshot_age_support
            or self.bullet_snapshot_age_support[0] < 0
        ):
            raise ValueError(
                "bullet snapshot age support must be sorted, unique, and "
                "nonnegative"
            )
        if self.control_delay_frames != self.delay_estimate.nominal:
            raise ValueError("control delay does not match its estimate")
        if not self.delay_estimate.support:
            raise ValueError("control delay support cannot be empty")
        for field, value in (
            ("player x", self.player_x),
            ("player y", self.player_y),
            ("projected player x", self.projected_player_x),
            ("projected player y", self.projected_player_y),
            ("power", self.power),
            ("bombs", self.bombs),
        ):
            _finite(value, field)


@dataclass(frozen=True)
class ServiceUpdate:
    """Completed background work staged for one immutable query version."""

    context_key: tuple[int, int, int | None]
    query_frame: int
    active_solution: object | None
    pending_solution: object | None
    corridor_updated: bool
    elapsed_ms: float

    def __post_init__(self) -> None:
        if self.query_frame < 0:
            raise ValueError("service query frame cannot be negative")
        _finite(self.elapsed_ms, "service update elapsed time")
        if self.elapsed_ms < 0.0:
            raise ValueError("service update elapsed time cannot be negative")


@dataclass(frozen=True)
class PublishedGuidance:
    """Lookup-only guidance assembled for one captured physical version."""

    capture: CapturedIteration
    service_update: ServiceUpdate
    request: object
    primary_query: object
    completed_query: object
    pipeline_shadow: PipelineShadowSnapshot

    def __post_init__(self) -> None:
        if self.service_update.context_key != self.capture.context_key:
            raise ValueError("guidance service context does not match capture")
        if self.service_update.query_frame != self.capture.snapshot_frame:
            raise ValueError("guidance query frame does not match capture")


@dataclass(frozen=True)
class FreshIssueResult:
    """Fresh recertification, deadline, and physical dispatch result."""

    capture: CapturedIteration
    proposal: LocalProposal
    decision: Decision
    alignment: ActionIssueAlignment
    dispatch: InputDispatch
    issue_frame: int
    pre_issue_action: str
    pre_issue_mask: int
    post_guard_action: str
    post_guard_mask: int
    planned_action: str
    planned_mask: int
    fresh_enemy_changed: bool
    deadline_missed: bool
    recertification_ms: float
    issue_path_ms: float
    observe_to_issue_ms: float

    def __post_init__(self) -> None:
        if self.issue_frame != self.alignment.issue_frame:
            raise ValueError("fresh issue frame does not match action alignment")
        if self.capture.source_frame != self.alignment.source_frame:
            raise ValueError("fresh issue source frame does not match capture")
        if self.capture.snapshot_frame != self.alignment.capture_frame:
            raise ValueError("fresh issue capture frame does not match capture")
        if self.deadline_missed != self.alignment.deadline_missed:
            raise ValueError("fresh issue deadline flag does not match alignment")
        if self.dispatch.target_mask != self.decision.mask:
            raise ValueError("physical dispatch target does not match issued decision")
        if self.pre_issue_mask != self.proposal.decision.mask:
            raise ValueError("pre-issue mask does not match local proposal")
        for field, value in (
            ("recertification time", self.recertification_ms),
            ("issue-path time", self.issue_path_ms),
            ("observe-to-issue time", self.observe_to_issue_ms),
        ):
            _finite(value, field)
            if value < 0.0:
                raise ValueError(f"{field} cannot be negative")


__all__ = [
    "CapturedIteration",
    "FreshIssueResult",
    "PublishedGuidance",
    "ServiceUpdate",
]
