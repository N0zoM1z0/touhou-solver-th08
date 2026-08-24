#!/usr/bin/env python3
"""Pure sensing and hazard-alignment fields for live decision traces."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from th08_ecl_runtime import ECL_LOOKAHEAD_SEMANTICS_VERSION
from th08_live.iteration import FreshIssueResult
from th08_live.models import BULLET_LIFECYCLE_TRACE_SCHEMA
from th08_native_timer import TH08_NATIVE_TIMER_SEMANTICS_VERSION
from th08_time_scale import (
    SCALE_COVERAGE_COMPLETE,
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    Th08TimeScaleSchedule,
)


SOURCE_COLLISION_SHADOW_SCHEMA = "th08-source-collision-shadow-v1"


def _player_geometry_record(root: Any) -> dict[str, object]:
    x = float(root.x)
    y = float(root.y)
    half_width, half_height = map(float, root.lethal_half_extents)
    left, top, right, bottom = map(float, root.lethal_aabb)
    values = (x, y, half_width, half_height, left, top, right, bottom)
    valid = bool(
        all(math.isfinite(value) for value in values)
        and half_width >= 0.0
        and half_height >= 0.0
        and left <= right
        and top <= bottom
    )
    cache_coherent = bool(
        valid
        and math.isclose(left, x - half_width, rel_tol=0.0, abs_tol=1e-5)
        and math.isclose(top, y - half_height, rel_tol=0.0, abs_tol=1e-5)
        and math.isclose(right, x + half_width, rel_tol=0.0, abs_tol=1e-5)
        and math.isclose(bottom, y + half_height, rel_tol=0.0, abs_tol=1e-5)
    )
    before_if_changed = None
    if not root.collision_geometry_stable:
        before_if_changed = {
            "lethal_aabb": list(root.lethal_aabb_before),
            "lethal_half_extents": list(root.lethal_half_extents_before),
        }
    return {
        "position": [x, y],
        "lethal_aabb": [left, top, right, bottom],
        "lethal_half_extents": [half_width, half_height],
        "valid": valid,
        "cached_aabb_coherent": cache_coherent,
        "geometry_stable_across_control_root": (
            root.collision_geometry_stable
        ),
        "before_if_changed": before_if_changed,
    }


def _bullet_lifecycle_record(bullets: Sequence[Any]) -> dict[str, object]:
    packed_states = getattr(bullets, "native_state", None)
    packed_timers = getattr(bullets, "native_state_timer_elapsed", None)
    packed_aux = getattr(bullets, "callback_aux", None)
    if (
        packed_states is not None
        and packed_timers is not None
        and packed_aux is not None
    ):
        states = np.asarray(packed_states)
        timers = np.asarray(packed_timers)
        auxiliary = np.asarray(packed_aux)
        complete = bool(
            states.size == timers.size == auxiliary.size == len(bullets)
        )
        state_values, state_counts = np.unique(states, return_counts=True)
        counts = {
            str(int(state)): int(count)
            for state, count in zip(state_values, state_counts, strict=True)
        }
        lethal_eligible = int(
            np.count_nonzero((states == 1) & (auxiliary == 0))
        )
        callback_suppressed = int(
            np.count_nonzero((states == 1) & (auxiliary != 0))
        )
    else:
        counts_counter: Counter[int] = Counter()
        lethal_eligible = 0
        callback_suppressed = 0
        complete = True
        for bullet in bullets:
            if not all(
                hasattr(bullet, field)
                for field in (
                    "native_state",
                    "native_state_timer_elapsed",
                    "callback_aux_state",
                )
            ):
                complete = False
            state = int(getattr(bullet, "native_state", 1))
            auxiliary = int(getattr(bullet, "callback_aux_state", 0))
            counts_counter[state] += 1
            lethal_eligible += state == 1 and auxiliary == 0
            callback_suppressed += state == 1 and auxiliary != 0
        counts = {
            str(state): count
            for state, count in sorted(counts_counter.items())
        }
    total = len(bullets)
    return {
        "coverage": "complete" if complete else "incomplete_missing_fields",
        "decoded_nonzero_state_count": total,
        "native_state_counts": counts,
        "source_lethal_eligible_count": lethal_eligible,
        "source_nonlethal_lifecycle_count": total - lethal_eligible,
        "callback_suppressed_state1_count": callback_suppressed,
        "legacy_collision_candidate_count": total,
        "legacy_only_candidate_count": total - lethal_eligible,
        "exception_trace_schema": BULLET_LIFECYCLE_TRACE_SCHEMA,
        "default_trace_state": [1, 0, 0],
    }


def _time_scale_schedule_hard_authority(
    schedule: Th08TimeScaleSchedule,
) -> bool:
    return (
        schedule.coverage == SCALE_COVERAGE_COMPLETE
        and not schedule.provenance.startswith(
            "experimental_pretarget_unit_transport"
        )
        and not schedule.provenance.startswith(
            "diagnostic_constant_current_root_unknown_direction"
        )
    )


@dataclass(frozen=True)
class SensingTraceInput:
    """Already-captured sensing values for one post-issue trace record."""

    resources: Mapping[str, object]
    stage_route_index: int
    spell: object
    boss_phase_snapshot: Any
    boss_phase_error: str | None
    boss_phase_progress: Any
    ecl_vm_snapshot: Any
    ecl_lookahead: Any
    tagged_velocity_toggles: Sequence[Any]
    bullets: Sequence[Any]
    ecl_event_frame_offset: int
    ecl_event_frame_uncertainty: Sequence[int]
    ecl_lookahead_error: str | None
    lasers: Sequence[Any]
    items: Sequence[Any]
    enemy_bodies: Sequence[Any]
    dormant_enemy_body_pointers: Collection[int]
    bullet_frame_before: int
    bullet_frame_after: int
    enemy_prefix_snapshot: Any
    enemy_prefix_bodies: Sequence[Any]
    bullet_capture_span: int
    hazard_snapshot_age: int
    player_to_hazard_lag: int
    ecl_frame_before: int | None
    ecl_frame_after: int | None
    boss_guard_frame_before: int | None
    boss_guard_frame_after: int | None
    enemy_body_snapshot_frame: int | None
    query_frame: int
    issue_enemy_prefix_snapshot: Any
    issue_enemy_prefix_bodies: Sequence[Any]
    issue_dormant_enemy_body_pointers: Collection[int]
    issue_enemy_changes: Sequence[object]
    issue_enemy_read_ms: float
    issue_enemy_recertificate_ms: float
    issue: FreshIssueResult
    player_control_root: Any
    spell_enemy_body_guard: Any
    spell_enemy_body_guard_error: str | None


def build_sensing_trace_fields(
    trace_input: SensingTraceInput,
    *,
    serialize_boss_phase_snapshot: Callable[[Any], dict[str, object] | None],
    serialize_enemy_bodies: Callable[[Sequence[Any]], list[object]],
    enemy_body_contact_enabled: Callable[[Any], bool],
    enemy_pointer_in_scanned_pool: Callable[[int], bool],
    issue_recertification_record: Callable[[Any], dict[str, object] | None],
) -> dict[str, object]:
    """Serialize observed sensing state without reads or model expansion."""

    boss_snapshot = trace_input.boss_phase_snapshot
    boss_error = trace_input.boss_phase_error
    progress = trace_input.boss_phase_progress
    ecl_snapshot = trace_input.ecl_vm_snapshot
    ecl_lookahead = trace_input.ecl_lookahead
    bullets = trace_input.bullets
    dormant = trace_input.dormant_enemy_body_pointers
    enemy_bodies = trace_input.enemy_bodies
    enemy_prefix = trace_input.enemy_prefix_snapshot
    issue_prefix = trace_input.issue_enemy_prefix_snapshot
    issue = trace_input.issue
    time_scale_schedule = issue.capture.time_scale_schedule
    phase_schedule_omitted = time_scale_schedule.provenance.startswith(
        "experimental_pretarget_unit_transport"
    )

    ecl_tagged_bullets = (
        tuple(
            bullet
            for bullet in bullets
            if (
                (
                    bullet.original_transform_flags
                    or (
                        bullet.transform_runtime.original_flags
                        if bullet.transform_runtime is not None
                        else 0
                    )
                )
                & ecl_snapshot.tag_mask
            )
        )
        if ecl_snapshot is not None
        else ()
    )

    return {
        "source_collision_shadow": {
            "schema": SOURCE_COLLISION_SHADOW_SCHEMA,
            "role": "shadow_no_action_ranking_or_hard_authority",
            "player": _player_geometry_record(
                trace_input.player_control_root
            ),
            "bullets": _bullet_lifecycle_record(bullets),
            "lasers": {
                "observed_count": len(trace_input.lasers),
                "native_finite_rectangle_fields_retained": True,
                "collision_promotion": False,
            },
        },
        "time_scale": {
            "semantics_version": (
                TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION
            ),
            "source_time_scale_bits": (
                issue.capture.source_time_scale_bits
            ),
            "root_scale_bits": time_scale_schedule.root_scale_bits,
            "player_scale_bits": (
                []
                if phase_schedule_omitted
                else list(time_scale_schedule.player_scale_bits)
            ),
            "laser_scale_bits": (
                []
                if phase_schedule_omitted
                else list(time_scale_schedule.laser_scale_bits)
            ),
            "phase_schedule_omitted": phase_schedule_omitted,
            "coverage": time_scale_schedule.coverage,
            "provenance": time_scale_schedule.provenance,
            "source_frame": time_scale_schedule.source_frame,
            "complete_horizon": time_scale_schedule.complete_horizon,
            "player_projection_authority": (
                issue.capture.player_projection_authority
            ),
            "hard_authority": _time_scale_schedule_hard_authority(
                time_scale_schedule
            ),
        },
        "resources": trace_input.resources,
        "stage_route_index": trace_input.stage_route_index,
        "spell": trace_input.spell,
        "boss_phase": (
            {
                **(serialize_boss_phase_snapshot(boss_snapshot) or {}),
                "error": boss_error,
            }
            if boss_snapshot is not None or boss_error is not None
            else None
        ),
        "boss_phase_progress": (
            {
                "status": progress.status,
                "frame_delta": progress.frame_delta,
                "health_delta": progress.health_delta,
                "damage_per_frame": progress.damage_per_frame,
                "completion_pending": progress.state.completion_pending,
                "completion_cause": progress.completion_cause,
                "health_remaining": progress.state.health_remaining,
                "health_progress": progress.state.health_progress,
                "time_remaining": progress.state.time_remaining,
                "damage_per_second_60hz": (
                    progress.damage_per_frame * 60.0
                    if progress.damage_per_frame is not None
                    else None
                ),
                "damageable": progress.state.damageable,
            }
            if progress is not None
            else None
        ),
        "bullet_velocity_lookahead": (
            {
                "instruction_pointer": ecl_snapshot.instruction_pointer,
                "timer_fraction": ecl_snapshot.timer_fraction,
                "timer_fraction_bits": ecl_snapshot.timer_fraction_bits,
                "timer_elapsed": ecl_snapshot.timer_elapsed,
                "time_scale": ecl_snapshot.time_scale,
                "time_scale_bits": ecl_snapshot.time_scale_bits,
                "timer_identity": {
                    "semantics_version": (TH08_NATIVE_TIMER_SEMANTICS_VERSION),
                    "elapsed": ecl_snapshot.timer_elapsed,
                    "fraction_bits": ecl_snapshot.timer_fraction_bits,
                    "time_scale_bits": ecl_snapshot.time_scale_bits,
                },
                "lookahead_semantics_version": (ECL_LOOKAHEAD_SEMANTICS_VERSION),
                "tag_mask": ecl_snapshot.tag_mask,
                "vm_local_projection": (
                    projection.trace_record()
                    if (
                        projection := getattr(
                            ecl_snapshot,
                            "local_projection",
                            None,
                        )
                    )
                    is not None
                    else None
                ),
                "instructions_scanned": (
                    ecl_lookahead.instructions_scanned
                    if ecl_lookahead is not None
                    else 0
                ),
                "stop_reason": (
                    ecl_lookahead.stop_reason if ecl_lookahead is not None else None
                ),
                "horizon_covered": (
                    ecl_lookahead.horizon_covered
                    if ecl_lookahead is not None
                    else False
                ),
                "coverage_status": (
                    ecl_lookahead.coverage_status
                    if ecl_lookahead is not None
                    else "unknown"
                ),
                "requested_horizon_frames": (
                    ecl_lookahead.requested_horizon_frames
                    if ecl_lookahead is not None
                    else None
                ),
                "stop_frame": (
                    ecl_lookahead.stop_frame if ecl_lookahead is not None else None
                ),
                "covered_through_frame": (
                    ecl_lookahead.covered_through_frame
                    if ecl_lookahead is not None
                    else 0
                ),
                "unknown_from_frame": (
                    ecl_lookahead.unknown_from_frame if ecl_lookahead is not None else 1
                ),
                "result_kind": (
                    (
                        "complete_schedule"
                        if ecl_lookahead.horizon_covered
                        else "prefix_only"
                    )
                    if ecl_lookahead is not None
                    else "unavailable"
                ),
                "prefix_events": [
                    [
                        event.frame,
                        event.callback_index,
                        event.tag_mask,
                        event.alternate_velocity_x,
                        event.alternate_velocity_y,
                    ]
                    for event in (
                        ecl_lookahead.events if ecl_lookahead is not None else ()
                    )
                ],
                "events": [
                    [
                        event.frame,
                        event.callback_index,
                        event.tag_mask,
                        event.alternate_velocity_x,
                        event.alternate_velocity_y,
                    ]
                    for event in trace_input.tagged_velocity_toggles
                ],
                "lowering_status": (
                    "complete_schedule_lowered"
                    if (ecl_lookahead is not None and ecl_lookahead.horizon_covered)
                    else "incomplete_prefix_not_lowered"
                ),
                "attached_bullets": sum(
                    bool(bullet.velocity_changes) for bullet in bullets
                ),
                "tagged_bullets": len(ecl_tagged_bullets),
                "stopped_tagged_bullets": sum(
                    bullet.callback_phase_state == 0 and bullet.callback_aux_state == 1
                    for bullet in ecl_tagged_bullets
                ),
                "event_frame_offset": trace_input.ecl_event_frame_offset,
                "event_frame_uncertainty": (trace_input.ecl_event_frame_uncertainty),
                "error": trace_input.ecl_lookahead_error,
            }
            if ecl_snapshot is not None
            else (
                {"error": trace_input.ecl_lookahead_error}
                if trace_input.ecl_lookahead_error is not None
                else None
            )
        ),
        "active_bullets": len(bullets),
        "active_lasers": len(trace_input.lasers),
        "active_items": len(trace_input.items),
        "active_enemy_bodies": len(enemy_bodies),
        "enemy_body_contact_enabled_count": sum(
            body.pointer not in dormant and enemy_body_contact_enabled(body)
            for body in enemy_bodies
        ),
        "enemy_body_anticipatory_count": sum(
            body.pointer not in dormant and not enemy_body_contact_enabled(body)
            for body in enemy_bodies
        ),
        "enemy_body_dormant_count": sum(
            body.pointer in dormant for body in enemy_bodies
        ),
        "hazard_alignment": {
            "bullet_frame_before": trace_input.bullet_frame_before,
            "bullet_frame_after": trace_input.bullet_frame_after,
            "enemy_prefix_frame_before": enemy_prefix.frame_before,
            "enemy_prefix_frame_after": enemy_prefix.frame_after,
            "enemy_prefix_body_count": len(trace_input.enemy_prefix_bodies),
            "enemy_prefix_observed_body_count": len(enemy_prefix.bodies),
            "enemy_prefix_contact_enabled_count": sum(
                body.pointer not in dormant and enemy_body_contact_enabled(body)
                for body in trace_input.enemy_prefix_bodies
            ),
            "enemy_prefix_anticipatory_count": sum(
                body.pointer not in dormant and not enemy_body_contact_enabled(body)
                for body in trace_input.enemy_prefix_bodies
            ),
            "enemy_prefix_dormant_count": len(dormant),
            "enemy_prefix_attempts": enemy_prefix.attempts,
            "bullet_capture_span": trace_input.bullet_capture_span,
            "hazard_snapshot_age": trace_input.hazard_snapshot_age,
            "player_to_hazard_lag": trace_input.player_to_hazard_lag,
            "ecl_frame_before": trace_input.ecl_frame_before,
            "ecl_frame_after": trace_input.ecl_frame_after,
            "boss_guard_frame_before": trace_input.boss_guard_frame_before,
            "boss_guard_frame_after": trace_input.boss_guard_frame_after,
        },
        "enemy_body_snapshot_frame": trace_input.enemy_body_snapshot_frame,
        "enemy_body_snapshot_age": (
            trace_input.query_frame - trace_input.enemy_body_snapshot_frame
            if trace_input.enemy_body_snapshot_frame is not None
            else None
        ),
        "issue_time_enemy_guard": {
            "frame_before": issue_prefix.frame_before,
            "frame_after": issue_prefix.frame_after,
            "body_count": len(trace_input.issue_enemy_prefix_bodies),
            "observed_body_count": len(issue_prefix.bodies),
            "contact_enabled_count": sum(
                enemy_body_contact_enabled(body) for body in issue_prefix.bodies
            ),
            "anticipatory_count": sum(
                not enemy_body_contact_enabled(body) for body in issue_prefix.bodies
            ),
            "dormant_count": len(trace_input.issue_dormant_enemy_body_pointers),
            "attempts": issue_prefix.attempts,
            "stable": issue_prefix.stable,
            "changes": list(trace_input.issue_enemy_changes),
            "recertified": bool(trace_input.issue_enemy_changes),
            "planned_action_before_guard": issue.pre_issue_action,
            "planned_mask_before_guard": issue.pre_issue_mask,
            "action_after_guard": issue.post_guard_action,
            "mask_after_guard": issue.post_guard_mask,
            "read_ms": trace_input.issue_enemy_read_ms,
            "recertificate_ms": trace_input.issue_enemy_recertificate_ms,
            "transaction": issue_recertification_record(
                issue.decision.issue_recertification
            ),
        },
        "spell_enemy_body_guard": (
            {
                "source": "boss_registry_or_spell_owner",
                "body": serialize_enemy_bodies(
                    (trace_input.spell_enemy_body_guard.body,)
                )[0],
                "contact_enabled": (trace_input.spell_enemy_body_guard.contact_enabled),
                "raw_contact_size": [
                    getattr(
                        trace_input.spell_enemy_body_guard,
                        "raw_contact_width",
                        None,
                    ),
                    getattr(
                        trace_input.spell_enemy_body_guard,
                        "raw_contact_height",
                        None,
                    ),
                ],
                "anticipatory": (
                    not trace_input.spell_enemy_body_guard.contact_enabled
                ),
                "covered_by_async_pool": enemy_pointer_in_scanned_pool(
                    trace_input.spell_enemy_body_guard.body.pointer
                ),
                "error": None,
            }
            if trace_input.spell_enemy_body_guard is not None
            else (
                {"error": trace_input.spell_enemy_body_guard_error}
                if trace_input.spell_enemy_body_guard_error is not None
                else None
            )
        ),
    }


__all__ = [
    "SOURCE_COLLISION_SHADOW_SCHEMA",
    "SensingTraceInput",
    "build_sensing_trace_fields",
]
