#!/usr/bin/env python3
"""Pure timing and optional hazard payloads for live decision traces."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionTimingTraceInput:
    observe_ms: float
    read_ms: float
    enemy_background_ms: float
    enemy_prefix_capture_ms: float
    enemy_prefix_merge_ms: float
    bullet_pool_read_ms: float
    laser_pool_read_ms: float
    item_pool_read_ms: float
    boss_phase_read_ms: float
    spell_enemy_guard_read_ms: float
    ecl_lookahead_read_ms: float
    hazard_read_bookkeeping_ms: float
    player_control_root_ms: float
    enemy_pool_read_ms: float
    enemy_prefix_read_ms: float
    issue_enemy_read_ms: float
    decode_ms: float
    bullet_decode_ms: float
    bullet_event_attach_ms: float
    laser_decode_ms: float
    item_decode_ms: float
    corridor_overhead_ms: float
    plan_ms: float
    issue_enemy_recertificate_ms: float
    issue_path_ms: float
    observe_to_issue_ms: float
    decision: Any
    local_pipeline_certificate_shadow: dict[str, object] | None
    input_ms: float
    before_trace_ms: float
    previous_trace_ms: float | None
    previous_iteration_ms: float | None


def build_decision_timing_trace_fields(
    trace_input: DecisionTimingTraceInput,
) -> dict[str, object]:
    """Serialize a declared timing boundary without measuring inside it."""

    decision = trace_input.decision
    local_shadow = trace_input.local_pipeline_certificate_shadow
    return {
        "read_ms": trace_input.read_ms,
        "plan_ms": trace_input.plan_ms,
        "timing_ms": {
            "observe": trace_input.observe_ms,
            "read_pools": trace_input.read_ms,
            "read_enemy_background": trace_input.enemy_background_ms,
            "read_enemy_prefix_capture": trace_input.enemy_prefix_capture_ms,
            "read_enemy_prefix_merge": trace_input.enemy_prefix_merge_ms,
            "read_bullet_pool": trace_input.bullet_pool_read_ms,
            "read_laser_pool": trace_input.laser_pool_read_ms,
            "read_item_pool": trace_input.item_pool_read_ms,
            "read_boss_phase": trace_input.boss_phase_read_ms,
            "read_spell_enemy_guard": (
                trace_input.spell_enemy_guard_read_ms
            ),
            "read_ecl_lookahead": trace_input.ecl_lookahead_read_ms,
            "read_hazard_bookkeeping": (
                trace_input.hazard_read_bookkeeping_ms
            ),
            "read_player_control_root": trace_input.player_control_root_ms,
            "read_enemy_pool": trace_input.enemy_pool_read_ms,
            "read_enemy_prefix": trace_input.enemy_prefix_read_ms,
            "read_enemy_issue_prefix": trace_input.issue_enemy_read_ms,
            "decode_pools": trace_input.decode_ms,
            "decode_bullets": trace_input.bullet_decode_ms,
            "attach_bullet_events": trace_input.bullet_event_attach_ms,
            "decode_lasers": trace_input.laser_decode_ms,
            "decode_items": trace_input.item_decode_ms,
            "corridor_bookkeeping": trace_input.corridor_overhead_ms,
            "local_plan": trace_input.plan_ms,
            "local_plan_initial": (
                trace_input.plan_ms
                - trace_input.issue_enemy_recertificate_ms
            ),
            "issue_enemy_recertificate": (
                trace_input.issue_enemy_recertificate_ms
            ),
            "issue_path_to_input": trace_input.issue_path_ms,
            "observe_to_input": trace_input.observe_to_issue_ms,
            "local_shared_laser_projection": (
                decision.local_certificate_timing.shared_laser_projection_ms
            ),
            "local_certificate_total": (
                decision.local_certificate_timing.certificate_total_ms
            ),
            "local_certificate_geometry": (
                decision.local_certificate_timing.geometry_kernel_ms
            ),
            "issue_certificate_total": (
                decision.issue_certificate_timing.certificate_total_ms
            ),
            "post_issue_root_shadow": (
                float(local_shadow.get("wall_ms", 0.0))
                if local_shadow is not None
                else 0.0
            ),
            "input": trace_input.input_ms,
            "before_trace": trace_input.before_trace_ms,
            "previous_trace": trace_input.previous_trace_ms,
            "previous_iteration": trace_input.previous_iteration_ms,
        },
    }


def build_optional_hazard_trace_fields(
    *,
    trace_radius: float,
    trace_transform_runtime: bool,
    bullets: Sequence[Any],
    lasers: Sequence[Any],
    items: Sequence[Any],
    projected_player_x: float,
    projected_player_y: float,
    serialize_bullet_trace: Callable[[Any], object],
    serialize_laser_trace: Callable[[Any], object],
) -> dict[str, object]:
    """Serialize opt-in detailed hazards without changing live sensing."""

    fields: dict[str, object] = {}
    if trace_radius > 0.0:
        fields["nearby_bullets"] = [
            serialize_bullet_trace(bullet)
            for bullet in bullets
            if abs(bullet.x - projected_player_x) <= trace_radius
            and abs(bullet.y - projected_player_y) <= trace_radius
        ]
        fields["lasers"] = [
            serialize_laser_trace(laser) for laser in lasers
        ]
        fields["items"] = [
            [
                item.slot,
                item.x,
                item.y,
                item.vx,
                item.vy,
                item.item_type,
                item.motion_state,
                item.full_value,
            ]
            for item in items
        ]
    if trace_transform_runtime:
        fields["transform_bullets"] = [
            serialize_bullet_trace(bullet)
            for bullet in bullets
            if bullet.transform_runtime is not None
        ]
    return fields


__all__ = [
    "DecisionTimingTraceInput",
    "build_decision_timing_trace_fields",
    "build_optional_hazard_trace_fields",
]
