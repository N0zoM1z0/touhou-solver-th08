"""Compact, replayable current-pool state for retained TH08 roots.

The future-source capsule historically retained enemy/ECL/timeline state but
not the bullet and laser pools consumed by the same global solve.  This module
stores only active planning records, with explicit slot identities and the
native lifecycle/callback state needed by the corridor adapter.  It never
stores the multi-megabyte raw native slabs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from th08_bullet_transform_model import (
    BulletTransformRuntime,
    TransformRecord,
)
from th08_laser_model import LaserPhase, LaserState
from th08_laser_runtime import Laser
from th08_live.models import Bullet
from th08_live.sensor import BULLET_POOL_SIZE, LASER_POOL_SIZE
from touhou_control.trajectory import CollisionStateChange, VelocityChange


CURRENT_HAZARD_ROOT_SCHEMA = (
    "th08-current-hazard-root-v1-active-slot-planning-state"
)


def _finite_number(value: object, *, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, *, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return int(value)


def _optional_finite(value: object, *, label: str) -> float | None:
    return None if value is None else _finite_number(value, label=label)


def _transform_record_payload(
    record: TransformRecord | None,
) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "index": int(record.index),
        "kind": int(record.kind),
        "allow_while_active": bool(record.allow_while_active),
        "int_0": int(record.int_0),
        "int_1": int(record.int_1),
        "float_0": (
            record.float_0
            if isinstance(record.float_0, str)
            else float(record.float_0)
        ),
        "float_1": (
            record.float_1
            if isinstance(record.float_1, str)
            else float(record.float_1)
        ),
    }


def _transform_record_from_payload(
    payload: object,
) -> TransformRecord | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("bullet transform record must be a mapping")
    float_0 = payload.get("float_0")
    float_1 = payload.get("float_1")
    for label, value in (("float_0", float_0), ("float_1", float_1)):
        if not isinstance(value, (int, float, str)) or isinstance(value, bool):
            raise ValueError(f"bullet transform {label} is malformed")
        if isinstance(value, (int, float)):
            _finite_number(value, label=f"bullet transform {label}")
    allow = payload.get("allow_while_active")
    if type(allow) is not bool:
        raise ValueError("bullet transform allow flag must be Boolean")
    return TransformRecord(
        index=_integer(payload.get("index"), label="transform index"),
        kind=_integer(payload.get("kind"), label="transform kind"),
        allow_while_active=allow,
        int_0=_integer(payload.get("int_0"), label="transform int_0"),
        int_1=_integer(payload.get("int_1"), label="transform int_1"),
        float_0=(
            str(float_0)
            if isinstance(float_0, str)
            else float(float_0)
        ),
        float_1=(
            str(float_1)
            if isinstance(float_1, str)
            else float(float_1)
        ),
    )


def _transform_runtime_payload(
    runtime: BulletTransformRuntime | None,
) -> dict[str, object] | None:
    if runtime is None:
        return None
    return {
        "original_flags": runtime.original_flags,
        "queue_cursor": runtime.queue_cursor,
        "next_record": _transform_record_payload(runtime.next_record),
        "timer_fraction": runtime.timer_fraction,
        "timer_elapsed": runtime.timer_elapsed,
        "resume_speed": runtime.resume_speed,
        "angle_operand": runtime.angle_operand,
        "duration": runtime.duration,
        "repeat_limit": runtime.repeat_limit,
        "repeat_count": runtime.repeat_count,
    }


def _transform_runtime_from_payload(
    payload: object,
) -> BulletTransformRuntime | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("bullet transform runtime must be a mapping")
    return BulletTransformRuntime(
        original_flags=_integer(
            payload.get("original_flags"),
            label="transform original flags",
        ),
        queue_cursor=_integer(
            payload.get("queue_cursor"),
            label="transform queue cursor",
        ),
        next_record=_transform_record_from_payload(payload.get("next_record")),
        timer_fraction=_finite_number(
            payload.get("timer_fraction"),
            label="transform timer fraction",
        ),
        timer_elapsed=_integer(
            payload.get("timer_elapsed"),
            label="transform timer elapsed",
        ),
        resume_speed=_finite_number(
            payload.get("resume_speed"),
            label="transform resume speed",
        ),
        angle_operand=_finite_number(
            payload.get("angle_operand"),
            label="transform angle operand",
        ),
        duration=_integer(payload.get("duration"), label="transform duration"),
        repeat_limit=_integer(
            payload.get("repeat_limit"),
            label="transform repeat limit",
        ),
        repeat_count=_integer(
            payload.get("repeat_count"),
            label="transform repeat count",
        ),
    )


def _bullet_payload(bullet: Bullet) -> dict[str, object]:
    return {
        "slot": bullet.slot,
        "position": [bullet.x, bullet.y],
        "velocity": [bullet.vx, bullet.vy],
        "half_extents": [bullet.half_width, bullet.half_height],
        "transform_flags": bullet.transform_flags,
        "speed": bullet.speed,
        "angle": bullet.angle,
        "callback_phase_state": bullet.callback_phase_state,
        "callback_aux_state": bullet.callback_aux_state,
        "original_transform_flags": bullet.original_transform_flags,
        "native_state": bullet.native_state,
        "native_state_timer_elapsed": bullet.native_state_timer_elapsed,
        "bullet_type": bullet.bullet_type,
        "velocity_changes": [
            [change.frame, change.velocity_x, change.velocity_y]
            for change in bullet.velocity_changes
        ],
        "collision_state_changes": [
            [change.frame, change.collision_enabled]
            for change in bullet.collision_state_changes
        ],
        "trajectory_uncertainty": [
            bullet.trajectory_uncertainty_x,
            bullet.trajectory_uncertainty_y,
        ],
        "transform_runtime": _transform_runtime_payload(
            bullet.transform_runtime
        ),
    }


def _pair(payload: object, *, label: str) -> tuple[float, float]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError(f"{label} must be a pair")
    if len(payload) != 2:
        raise ValueError(f"{label} must contain two values")
    return (
        _finite_number(payload[0], label=f"{label}[0]"),
        _finite_number(payload[1], label=f"{label}[1]"),
    )


def _bullet_from_payload(payload: object) -> Bullet:
    if not isinstance(payload, Mapping):
        raise ValueError("retained bullet must be a mapping")
    position = _pair(payload.get("position"), label="bullet position")
    velocity = _pair(payload.get("velocity"), label="bullet velocity")
    half_extents = _pair(
        payload.get("half_extents"),
        label="bullet half extents",
    )
    uncertainty = _pair(
        payload.get("trajectory_uncertainty"),
        label="bullet trajectory uncertainty",
    )
    if min(*half_extents, *uncertainty) < 0.0:
        raise ValueError("bullet extents and uncertainty must be nonnegative")
    velocity_changes_raw = payload.get("velocity_changes")
    collision_changes_raw = payload.get("collision_state_changes")
    if not isinstance(velocity_changes_raw, Sequence) or isinstance(
        velocity_changes_raw,
        (str, bytes),
    ):
        raise ValueError("bullet velocity changes must be a sequence")
    if not isinstance(collision_changes_raw, Sequence) or isinstance(
        collision_changes_raw,
        (str, bytes),
    ):
        raise ValueError("bullet collision changes must be a sequence")
    velocity_changes: list[VelocityChange] = []
    for row in velocity_changes_raw:
        if not isinstance(row, Sequence) or len(row) != 3:
            raise ValueError("bullet velocity change is malformed")
        velocity_changes.append(
            VelocityChange(
                _integer(row[0], label="velocity-change frame"),
                _finite_number(row[1], label="velocity-change x"),
                _finite_number(row[2], label="velocity-change y"),
            )
        )
    collision_changes: list[CollisionStateChange] = []
    for row in collision_changes_raw:
        if not isinstance(row, Sequence) or len(row) != 2:
            raise ValueError("bullet collision-state change is malformed")
        if type(row[1]) is not bool:
            raise ValueError("bullet collision-state value must be Boolean")
        collision_changes.append(
            CollisionStateChange(
                _integer(row[0], label="collision-change frame"),
                row[1],
            )
        )
    bullet_type_raw = payload.get("bullet_type")
    if bullet_type_raw is not None and type(bullet_type_raw) is not int:
        raise ValueError("bullet type must be an integer or null")
    return Bullet(
        x=position[0],
        y=position[1],
        vx=velocity[0],
        vy=velocity[1],
        half_width=half_extents[0],
        half_height=half_extents[1],
        transform_flags=_integer(
            payload.get("transform_flags"),
            label="bullet transform flags",
        ),
        slot=_integer(payload.get("slot"), label="bullet slot"),
        speed=_optional_finite(payload.get("speed"), label="bullet speed"),
        angle=_optional_finite(payload.get("angle"), label="bullet angle"),
        transform_runtime=_transform_runtime_from_payload(
            payload.get("transform_runtime")
        ),
        callback_phase_state=_integer(
            payload.get("callback_phase_state"),
            label="bullet callback phase",
        ),
        callback_aux_state=_integer(
            payload.get("callback_aux_state"),
            label="bullet callback auxiliary state",
        ),
        velocity_changes=tuple(velocity_changes),
        collision_state_changes=tuple(collision_changes),
        trajectory_uncertainty_x=uncertainty[0],
        trajectory_uncertainty_y=uncertainty[1],
        original_transform_flags=_integer(
            payload.get("original_transform_flags"),
            label="bullet original transform flags",
        ),
        native_state=_integer(
            payload.get("native_state"),
            label="bullet native state",
        ),
        native_state_timer_elapsed=_integer(
            payload.get("native_state_timer_elapsed"),
            label="bullet native state timer",
        ),
        bullet_type=(
            int(bullet_type_raw) if bullet_type_raw is not None else None
        ),
    )


def _laser_state_payload(state: LaserState | None) -> dict[str, object] | None:
    if state is None:
        return None
    return {
        "origin": [state.origin_x, state.origin_y],
        "angle": state.angle,
        "tail_distance": state.tail_distance,
        "head_distance": state.head_distance,
        "maximum_length": state.maximum_length,
        "width": state.width,
        "speed": state.speed,
        "warmup_frames": state.warmup_frames,
        "active_frames": state.active_frames,
        "fade_frames": state.fade_frames,
        "collision_enable_frame": state.collision_enable_frame,
        "collision_disable_frame": state.collision_disable_frame,
        "flags": state.flags,
        "current_width": state.current_width,
        "phase": int(state.phase),
        "timer": state.timer,
        "timer_fraction": state.timer_fraction,
        "active": state.active,
    }


def _laser_payload(laser: Laser) -> dict[str, object]:
    return {
        "slot": laser.slot,
        "origin": [laser.origin_x, laser.origin_y],
        "angle": laser.angle,
        "tail": laser.tail,
        "head": laser.head,
        "half_width": laser.half_width,
        "collision_flag": laser.collision_flag,
        "uncertainty": laser.uncertainty,
        "uncertainty_per_frame": laser.uncertainty_per_frame,
        "state": _laser_state_payload(laser.state),
    }


def _laser_state_from_payload(payload: object) -> LaserState | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("retained laser state must be a mapping")
    origin = _pair(payload.get("origin"), label="laser-state origin")
    active = payload.get("active")
    if type(active) is not bool:
        raise ValueError("laser-state active flag must be Boolean")
    phase_value = _integer(payload.get("phase"), label="laser phase")
    try:
        phase = LaserPhase(phase_value)
    except ValueError as error:
        raise ValueError("laser phase is unsupported") from error
    return LaserState(
        origin_x=origin[0],
        origin_y=origin[1],
        angle=_finite_number(payload.get("angle"), label="laser-state angle"),
        tail_distance=_finite_number(
            payload.get("tail_distance"),
            label="laser-state tail",
        ),
        head_distance=_finite_number(
            payload.get("head_distance"),
            label="laser-state head",
        ),
        maximum_length=_finite_number(
            payload.get("maximum_length"),
            label="laser maximum length",
        ),
        width=_finite_number(payload.get("width"), label="laser width"),
        speed=_finite_number(payload.get("speed"), label="laser speed"),
        warmup_frames=_integer(
            payload.get("warmup_frames"),
            label="laser warmup frames",
        ),
        active_frames=_integer(
            payload.get("active_frames"),
            label="laser active frames",
        ),
        fade_frames=_integer(
            payload.get("fade_frames"),
            label="laser fade frames",
        ),
        collision_enable_frame=_integer(
            payload.get("collision_enable_frame"),
            label="laser collision-enable frame",
        ),
        collision_disable_frame=_integer(
            payload.get("collision_disable_frame"),
            label="laser collision-disable frame",
        ),
        flags=_integer(payload.get("flags"), label="laser flags"),
        current_width=_finite_number(
            payload.get("current_width"),
            label="laser current width",
        ),
        phase=phase,
        timer=_integer(payload.get("timer"), label="laser timer"),
        timer_fraction=_finite_number(
            payload.get("timer_fraction"),
            label="laser timer fraction",
        ),
        active=active,
    )


def _laser_from_payload(payload: object) -> Laser:
    if not isinstance(payload, Mapping):
        raise ValueError("retained laser must be a mapping")
    origin = _pair(payload.get("origin"), label="laser origin")
    return Laser(
        origin_x=origin[0],
        origin_y=origin[1],
        angle=_finite_number(payload.get("angle"), label="laser angle"),
        tail=_finite_number(payload.get("tail"), label="laser tail"),
        head=_finite_number(payload.get("head"), label="laser head"),
        half_width=_finite_number(
            payload.get("half_width"),
            label="laser half width",
        ),
        state=_laser_state_from_payload(payload.get("state")),
        slot=_integer(payload.get("slot"), label="laser slot"),
        collision_flag=_integer(
            payload.get("collision_flag"),
            label="laser collision flag",
        ),
        uncertainty=_finite_number(
            payload.get("uncertainty"),
            label="laser uncertainty",
        ),
        uncertainty_per_frame=_finite_number(
            payload.get("uncertainty_per_frame"),
            label="laser uncertainty per frame",
        ),
    )


def build_current_hazard_root(
    *,
    root_frame: int,
    bullets: Sequence[Bullet],
    lasers: Sequence[Laser],
) -> dict[str, object]:
    """Build one canonical active-slot record from a coherent native slab."""

    if type(root_frame) is not int or root_frame < 0:
        raise ValueError("current-hazard root frame must be nonnegative")
    ordered_bullets = tuple(sorted(bullets, key=lambda value: value.slot))
    ordered_lasers = tuple(sorted(lasers, key=lambda value: value.slot))
    bullet_slots = tuple(value.slot for value in ordered_bullets)
    laser_slots = tuple(value.slot for value in ordered_lasers)
    if (
        len(set(bullet_slots)) != len(bullet_slots)
        or any(not 0 <= slot < BULLET_POOL_SIZE for slot in bullet_slots)
    ):
        raise ValueError("current-hazard bullet slots are invalid")
    if (
        len(set(laser_slots)) != len(laser_slots)
        or any(not 0 <= slot < LASER_POOL_SIZE for slot in laser_slots)
    ):
        raise ValueError("current-hazard laser slots are invalid")
    record: dict[str, object] = {
        "schema": CURRENT_HAZARD_ROOT_SCHEMA,
        "root_frame": root_frame,
        "bullet_pool_capacity": BULLET_POOL_SIZE,
        "laser_pool_capacity": LASER_POOL_SIZE,
        "bullets": [_bullet_payload(value) for value in ordered_bullets],
        "lasers": [_laser_payload(value) for value in ordered_lasers],
        "role": "same-clock-global-planner-replay-root",
    }
    # Apply the reader's strict finite/type/range contract at construction as
    # well.  This prevents an in-memory caller from bypassing the fail-closed
    # checks that a JSON round trip would otherwise apply.
    current_hazards_from_root(record, expected_root_frame=root_frame)
    return record


def current_hazards_from_root(
    payload: object,
    *,
    expected_root_frame: int | None = None,
) -> tuple[tuple[Bullet, ...], tuple[Laser, ...]]:
    """Validate and reconstruct a retained compact current-pool root."""

    if not isinstance(payload, Mapping):
        raise ValueError("current-hazard root must be a mapping")
    if payload.get("schema") != CURRENT_HAZARD_ROOT_SCHEMA:
        raise ValueError("current-hazard root schema is unsupported")
    root_frame = _integer(
        payload.get("root_frame"),
        label="current-hazard root frame",
    )
    if root_frame < 0 or (
        expected_root_frame is not None and root_frame != expected_root_frame
    ):
        raise ValueError("current-hazard root frame disagrees")
    if payload.get("bullet_pool_capacity") != BULLET_POOL_SIZE:
        raise ValueError("current-hazard bullet-pool capacity disagrees")
    if payload.get("laser_pool_capacity") != LASER_POOL_SIZE:
        raise ValueError("current-hazard laser-pool capacity disagrees")
    bullet_payloads = payload.get("bullets")
    laser_payloads = payload.get("lasers")
    if not isinstance(bullet_payloads, list) or not isinstance(
        laser_payloads,
        list,
    ):
        raise ValueError("current-hazard active-slot arrays are malformed")
    bullets = tuple(_bullet_from_payload(value) for value in bullet_payloads)
    lasers = tuple(_laser_from_payload(value) for value in laser_payloads)
    if tuple(value.slot for value in bullets) != tuple(
        sorted(value.slot for value in bullets)
    ) or len({value.slot for value in bullets}) != len(bullets):
        raise ValueError("current-hazard bullet slots are not canonical")
    if tuple(value.slot for value in lasers) != tuple(
        sorted(value.slot for value in lasers)
    ) or len({value.slot for value in lasers}) != len(lasers):
        raise ValueError("current-hazard laser slots are not canonical")
    if any(not 0 <= value.slot < BULLET_POOL_SIZE for value in bullets):
        raise ValueError("current-hazard bullet slot is out of range")
    if any(not 0 <= value.slot < LASER_POOL_SIZE for value in lasers):
        raise ValueError("current-hazard laser slot is out of range")
    return bullets, lasers


__all__ = [
    "CURRENT_HAZARD_ROOT_SCHEMA",
    "build_current_hazard_root",
    "current_hazards_from_root",
]
