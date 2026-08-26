"""Immutable input contracts for one TH08 local-planner decision.

The contracts deliberately group data by authority and lifetime.  Concrete
hazard, pipeline-root, and service types remain owned by their existing
modules; this boundary only transports an already captured decision snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from th08_time_scale import Th08TimeScaleSchedule


class PlannerMode(Enum):
    """Explicit planner pass mode; modes are not recursive call flags."""

    STANDARD = "standard"
    RELAXED_VIABILITY = "relaxed_viability"


@dataclass(frozen=True)
class PhysicalHazardSnapshot:
    player_x: float
    player_y: float
    bullets: tuple[Any, ...]
    lasers: tuple[Any, ...]
    time_scale_schedule: Th08TimeScaleSchedule
    enemy_bodies: tuple[Any, ...] = ()
    items: tuple[Any, ...] = ()
    snapshot_lag: int = 0
    bullet_snapshot_age_support: tuple[int, ...] | None = None
    future_hazard_projection: Any | None = None
    future_projection_offset: int = 0


@dataclass(frozen=True)
class ActuatorPipeline:
    previous_direction: int
    can_bomb: bool
    previous_focus: bool = True
    local_pipeline_root: Any | None = None
    control_delay_frames: int = 2
    control_delay_candidates: tuple[int, ...] | None = None
    action_hold_frames: int = 2


@dataclass(frozen=True)
class GlobalGuidance:
    target_x: float | None = None
    target_y: float | None = None
    target_deadline: int | None = None
    allowed_first_actions: tuple[str, ...] | None = None
    allowed_action_authority: str | None = None
    allow_coarse_viability_relaxation: bool = True
    viability_repair_volumes: tuple[tuple[str, int], ...] = ()
    viability_recovery_distances: tuple[tuple[str, float], ...] = ()
    viability_safety_actions: tuple[str, ...] = ()
    viability_safety_state_value: float | None = None
    viability_survival_actions: tuple[str, ...] = ()
    viability_survival_frames: int | None = None
    viability_survival_bottleneck_margin: float | None = None
    viability_position_error: float = 0.0


@dataclass(frozen=True)
class PlannerConfig:
    horizon: int = 10
    threat_horizon: int | None = None
    beam_width: int = 24
    recovery_control_reserve: bool = True
    losing_control_reserve: bool = False
    preloss_continuation_preference: bool = False
    preserve_previous_direction_inertia: bool = True
    beam_dedup_mode: str = "quantized"
    relax_stale_viability_contradiction: bool = False
    enforce_fresh_viability_intersection: bool = True


@dataclass(frozen=True)
class ObjectiveContext:
    power: float = 0.0
    bombs: float = 0.0
    damage_target_x: float | None = None
    damage_target_half_width: float = 0.0
    damageable: bool = False


@dataclass(frozen=True)
class LocalPlannerRequest:
    physical: PhysicalHazardSnapshot
    actuator: ActuatorPipeline
    guidance: GlobalGuidance = GlobalGuidance()
    config: PlannerConfig = PlannerConfig()
    objective: ObjectiveContext = ObjectiveContext()
    mode: PlannerMode = PlannerMode.STANDARD
