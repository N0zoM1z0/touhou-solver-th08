#!/usr/bin/env python3
"""Source-ordered TH08 current-bullet transform frame reference.

This module resumes one retained ``Bullet::FUN_0042ffc0`` program and then
executes the reached ``BulletManager::OnUpdate`` transform/movement/culling
prefix.  It is the readable scalar reference for the separately transcribed C
oracle.  Template replacement and derived child emission remain typed,
fail-closed boundaries until their dependent state is carried by the root.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from th08_bullet_template_contract import (
    BulletTemplateContractError,
    bullet_template_profile,
)
from th08_bullet_transform_model import (
    AngularVelocityRuntime,
    BulletTransformProgramRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformTimerRuntime,
    VectorAccelerationRuntime,
    parse_transform_program,
)
from th08_live.models import Bullet
from th08_semantics.source_primitives import f32, normalize_angle


PLAYFIELD_WIDTH = 384.0
PLAYFIELD_HEIGHT = 448.0
TIMER_RATE_THRESHOLD = f32(0.99)
VELOCITY_DIRECTION_THRESHOLD = f32(0.0001)
REFLECTION_ACTIVE_MASK = int(
    TransformKind.REFLECT_ALL_EDGES
    | TransformKind.REFLECT_SIDES_AND_TOP
)
STOP_ACTIVE_MASK = int(
    TransformKind.STOP_TURN_REPEAT
    | TransformKind.STOP_REAIM_REPEAT
    | TransformKind.STOP_SNAP_REPEAT
)
WRAP_ACTIVE_MASK = int(
    TransformKind.WRAP_HORIZONTAL | TransformKind.WRAP_VERTICAL
)
OFFSCREEN_GRACE_ACTIVE_MASK = 0xDC0
SUPPORTED_ACTIVE_MASK = int(
    TransformKind.DECELERATE_16F
    | TransformKind.VECTOR_ACCELERATION
    | TransformKind.ANGULAR_VELOCITY
) | STOP_ACTIVE_MASK | REFLECTION_ACTIVE_MASK | WRAP_ACTIVE_MASK | int(
    TransformKind.TIMED_QUEUE_BARRIER
)


class CurrentTransformUnsupported(ValueError):
    """A reached source transition needs state outside the retained root."""

    def __init__(self, reason: str, *, kind: int | None = None) -> None:
        self.reason = reason
        self.kind = kind
        suffix = "" if kind is None else f" ({kind:#x})"
        super().__init__(reason + suffix)


@dataclass(frozen=True)
class CurrentBulletTransformState:
    """Complete value state for the covered current-bullet update prefix."""

    x: float
    y: float
    velocity_x: float
    velocity_y: float
    collision_half_width: float
    collision_half_height: float
    cull_half_width: float
    cull_half_height: float
    base_speed: float
    base_angle: float
    bullet_type: int
    native_state: int
    active_flags: int
    runtime: BulletTransformProgramRuntime
    retired: bool = False

    @property
    def lethal(self) -> bool:
        return not self.retired and self.native_state == 1


def _add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def _sub(left: float, right: float) -> float:
    return f32(f32(left) - f32(right))


def _mul(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def _div(left: float, right: float) -> float:
    return f32(f32(left) / f32(right))


def _polar(angle: float, magnitude: float) -> tuple[float, float]:
    return (
        f32(math.cos(f32(angle)) * f32(magnitude)),
        f32(math.sin(f32(angle)) * f32(magnitude)),
    )


def _timer_set(current: int) -> TransformTimerRuntime:
    return TransformTimerRuntime(previous=-999, subframe=0.0, current=current)


def _timer_tick(
    timer: TransformTimerRuntime,
    *,
    timer_scale: float,
) -> TransformTimerRuntime:
    previous = timer.current
    current = timer.current
    subframe = timer.subframe
    if timer_scale <= TIMER_RATE_THRESHOLD:
        subframe = _add(subframe, timer_scale)
        if subframe >= 1.0:
            current += 1
            subframe = _sub(subframe, 1.0)
    else:
        current += 1
    return TransformTimerRuntime(previous, subframe, current)


def _timer_decrement(
    timer: TransformTimerRuntime,
    *,
    timer_scale: float,
    force_tick: bool,
) -> TransformTimerRuntime:
    previous = timer.previous
    subframe = timer.subframe
    current = timer.current
    if force_tick:
        current -= 1
        subframe = 0.0
        previous = -999
    if timer_scale > TIMER_RATE_THRESHOLD:
        current -= 1
        return TransformTimerRuntime(previous, subframe, current)
    previous = current
    subframe = _sub(subframe, timer_scale)
    while subframe < 0.0:
        current -= 1
        subframe = _add(subframe, 1.0)
    return TransformTimerRuntime(previous, subframe, current)


def _inside_playfield(
    x: float,
    y: float,
    half_width: float,
    half_height: float,
) -> bool:
    return not (
        _add(x, half_width) < 0.0
        or _sub(x, half_width) > PLAYFIELD_WIDTH
        or _add(y, half_height) < 0.0
        or _sub(y, half_height) > PLAYFIELD_HEIGHT
    )


def state_from_bullet(bullet: Bullet) -> CurrentBulletTransformState:
    """Build a covered state from one coherent diagnostic bullet root."""

    runtime = bullet.transform_program_runtime
    if runtime is None:
        raise CurrentTransformUnsupported("transform_program_state_unavailable")
    if bullet.speed is None or bullet.angle is None:
        raise CurrentTransformUnsupported("base_polar_state_unavailable")
    if bullet.bullet_type is None:
        raise CurrentTransformUnsupported("bullet_template_type_unavailable")
    try:
        template = bullet_template_profile(bullet.bullet_type)
    except BulletTemplateContractError as exc:
        raise CurrentTransformUnsupported(
            "bullet_template_type_unsupported"
        ) from exc
    return CurrentBulletTransformState(
        x=f32(bullet.x),
        y=f32(bullet.y),
        velocity_x=f32(bullet.vx),
        velocity_y=f32(bullet.vy),
        collision_half_width=f32(bullet.half_width),
        collision_half_height=f32(bullet.half_height),
        cull_half_width=f32(template.cull_half_width),
        cull_half_height=f32(template.cull_half_height),
        base_speed=f32(bullet.speed),
        base_angle=f32(bullet.angle),
        bullet_type=bullet.bullet_type,
        native_state=bullet.native_state,
        active_flags=bullet.transform_flags,
        runtime=runtime,
    )


def validate_current_transform_state(
    state: CurrentBulletTransformState,
) -> None:
    if state.retired or state.native_state == 5:
        return
    if state.native_state != 1:
        raise CurrentTransformUnsupported(
            "native_spawn_or_fade_lifecycle_requires_separate_step"
        )
    if state.active_flags & ~SUPPORTED_ACTIVE_MASK:
        raise CurrentTransformUnsupported(
            "unmodeled_active_transform_flags",
            kind=state.active_flags & ~SUPPORTED_ACTIVE_MASK,
        )
    runtime = state.runtime
    pairs = (
        (int(TransformKind.DECELERATE_16F), runtime.decelerate_timer),
        (int(TransformKind.VECTOR_ACCELERATION), runtime.vector_acceleration),
        (int(TransformKind.ANGULAR_VELOCITY), runtime.angular_velocity),
        (STOP_ACTIVE_MASK, runtime.stop),
        (REFLECTION_ACTIVE_MASK, runtime.reflection),
        (int(TransformKind.TIMED_QUEUE_BARRIER), runtime.barrier_timer),
        (WRAP_ACTIVE_MASK, runtime.wrap_timer),
    )
    for mask, block in pairs:
        if bool(state.active_flags & mask) != (block is not None):
            raise ValueError(
                f"active transform/block mismatch for mask {mask:#x}"
            )
    if not 0 <= runtime.queue_cursor <= 18:
        raise ValueError("transform queue cursor is outside 0..18")
    values = (
        state.x,
        state.y,
        state.velocity_x,
        state.velocity_y,
        state.collision_half_width,
        state.collision_half_height,
        state.cull_half_width,
        state.cull_half_height,
        state.base_speed,
        state.base_angle,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("current transform state contains nonfinite geometry")


def step_current_transform(
    state: CurrentBulletTransformState,
    *,
    player_x: float,
    player_y: float,
    ecl_time_scale: float = 1.0,
    timer_scale: float = 1.0,
    movement_frozen: bool = False,
    timer_force_tick: bool = False,
) -> CurrentBulletTransformState:
    """Execute one covered source-order manager frame."""

    validate_current_transform_state(state)
    if state.retired or state.native_state == 5:
        return state
    if not all(
        math.isfinite(value)
        for value in (player_x, player_y, ecl_time_scale, timer_scale)
    ):
        raise ValueError("transform frame operands must be finite")
    player_x = f32(player_x)
    player_y = f32(player_y)
    ecl_time_scale = f32(ecl_time_scale)
    timer_scale = f32(timer_scale)

    runtime = state.runtime
    records = parse_transform_program(runtime.program)
    active = state.active_flags
    cursor = runtime.queue_cursor
    native_state = state.native_state
    cull_countdown = runtime.cull_suppression_countdown
    offscreen_counter = runtime.offscreen_counter
    decelerate = runtime.decelerate_timer
    vector = runtime.vector_acceleration
    angular = runtime.angular_velocity
    stop = runtime.stop
    reflection = runtime.reflection
    barrier = runtime.barrier_timer
    wrap = runtime.wrap_timer
    x = state.x
    y = state.y
    velocity_x = state.velocity_x
    velocity_y = state.velocity_y
    base_speed = state.base_speed
    base_angle = state.base_angle

    # Bullet::FUN_0042ffc0: skip disabled records and chain only immediate
    # transforms.  An activated handler returns to OnUpdate for this frame.
    while cursor < len(records):
        record = records[cursor]
        kind = int(record.kind)
        if kind == 0:
            break
        if not record.allow_while_active and active != 0:
            break
        if runtime.original_flags & kind == 0:
            cursor += 1
            continue
        if kind == int(TransformKind.DECELERATE_16F):
            active |= kind
            decelerate = _timer_set(0)
        elif kind == int(TransformKind.VECTOR_ACCELERATION):
            angle = (
                float(record.float_1)
                if float(record.float_1) > -990.0
                else base_angle
            )
            magnitude = float(record.float_0)
            acceleration_x, acceleration_y = _polar(
                angle,
                _mul(ecl_time_scale, magnitude),
            )
            active |= kind
            vector = VectorAccelerationRuntime(
                timer=_timer_set(0),
                magnitude=f32(magnitude),
                angle=f32(angle),
                acceleration_x=acceleration_x,
                acceleration_y=acceleration_y,
                duration=record.int_0,
            )
        elif kind == int(TransformKind.ANGULAR_VELOCITY):
            active |= kind
            angular = AngularVelocityRuntime(
                timer=_timer_set(0),
                speed_acceleration=f32(float(record.float_0)),
                angular_velocity=f32(float(record.float_1)),
                duration=record.int_0,
            )
        elif kind & STOP_ACTIVE_MASK and kind in (
            int(TransformKind.STOP_TURN_REPEAT),
            int(TransformKind.STOP_REAIM_REPEAT),
            int(TransformKind.STOP_SNAP_REPEAT),
        ):
            active |= kind
            stop = StopTransformRuntime(
                timer=_timer_set(0),
                resume_speed=(
                    f32(float(record.float_1))
                    if float(record.float_1) > -999.0
                    else base_speed
                ),
                angle_operand=f32(float(record.float_0)),
                duration=record.int_0,
                repeat_limit=record.int_1,
                repeat_count=0,
            )
        elif kind in (
            int(TransformKind.REFLECT_ALL_EDGES),
            int(TransformKind.REFLECT_SIDES_AND_TOP),
        ):
            active |= kind
            reflection = ReflectionTransformRuntime(
                restored_speed=(
                    f32(float(record.float_0))
                    if float(record.float_0) >= 0.0
                    else base_speed
                ),
                event_count=0,
                event_limit=record.int_0,
            )
        elif kind in (
            int(TransformKind.WRAP_HORIZONTAL),
            int(TransformKind.WRAP_VERTICAL),
        ):
            active |= kind
            wrap = _timer_set(record.int_0)
        elif kind == int(TransformKind.TIMED_QUEUE_BARRIER):
            active |= kind
            barrier = _timer_set(record.int_0)
        elif kind == int(TransformKind.SUPPRESS_OFFSCREEN_CULL):
            cull_countdown = record.int_0
            cursor += 1
            continue
        elif kind == int(TransformKind.REPLACE_BULLET_TEMPLATE):
            raise CurrentTransformUnsupported(
                "template_replacement_requires_color_geometry_state",
                kind=kind,
            )
        elif kind == int(TransformKind.ENTER_FADE_STATE):
            native_state = 5
        elif kind == int(TransformKind.PLAY_SOUND):
            cursor += 1
            continue
        elif kind == int(TransformKind.EMIT_DERIVED_PATTERN):
            raise CurrentTransformUnsupported(
                "derived_pattern_requires_child_birth_allocation",
                kind=kind,
            )
        # The native default branch is a geometry no-op followed by cursor++.
        cursor += 1
        break

    if active & int(TransformKind.DECELERATE_16F):
        assert decelerate is not None
        if decelerate.current <= 16:
            magnitude = _sub(
                5.0,
                _div(_mul(float(decelerate.current), 5.0), 16.0),
            )
            velocity_x, velocity_y = _polar(
                base_angle,
                _mul(_add(magnitude, base_speed), ecl_time_scale),
            )
        else:
            active ^= int(TransformKind.DECELERATE_16F)
        decelerate = _timer_tick(decelerate, timer_scale=timer_scale)
        if not active & int(TransformKind.DECELERATE_16F):
            decelerate = None

    if active & int(TransformKind.VECTOR_ACCELERATION):
        assert vector is not None
        if vector.timer.current >= vector.duration:
            active &= ~int(TransformKind.VECTOR_ACCELERATION)
        else:
            velocity_x = _add(
                velocity_x,
                _mul(vector.acceleration_x, ecl_time_scale),
            )
            velocity_y = _add(
                velocity_y,
                _mul(vector.acceleration_y, ecl_time_scale),
            )
            if (
                abs(velocity_x) > VELOCITY_DIRECTION_THRESHOLD
                or abs(velocity_y) > VELOCITY_DIRECTION_THRESHOLD
            ):
                base_angle = f32(math.atan2(velocity_y, velocity_x))
        vector = replace(
            vector,
            timer=_timer_tick(vector.timer, timer_scale=timer_scale),
        )
        if not active & int(TransformKind.VECTOR_ACCELERATION):
            vector = None

    if active & int(TransformKind.ANGULAR_VELOCITY):
        assert angular is not None
        if angular.timer.current >= angular.duration:
            active &= ~int(TransformKind.ANGULAR_VELOCITY)
        else:
            base_angle = normalize_angle(
                _add(
                    base_angle,
                    _mul(ecl_time_scale, angular.angular_velocity),
                )
            )
            base_speed = _add(
                base_speed,
                _mul(ecl_time_scale, angular.speed_acceleration),
            )
            velocity_x, velocity_y = _polar(
                base_angle,
                _mul(ecl_time_scale, base_speed),
            )
        angular = replace(
            angular,
            timer=_timer_tick(angular.timer, timer_scale=timer_scale),
        )
        if not active & int(TransformKind.ANGULAR_VELOCITY):
            angular = None

    for kind in (
        int(TransformKind.STOP_TURN_REPEAT),
        int(TransformKind.STOP_SNAP_REPEAT),
        int(TransformKind.STOP_REAIM_REPEAT),
    ):
        if not active & kind:
            continue
        assert stop is not None
        timer = stop.timer
        repeat_count = stop.repeat_count
        if timer.current >= stop.duration:
            repeat_count += 1
            if repeat_count >= stop.repeat_limit:
                active &= ~kind
            if kind == int(TransformKind.STOP_TURN_REPEAT):
                base_angle = _add(base_angle, stop.angle_operand)
            elif kind == int(TransformKind.STOP_REAIM_REPEAT):
                base_angle = normalize_angle(
                    _add(
                        f32(math.atan2(_sub(player_y, y), _sub(player_x, x))),
                        stop.angle_operand,
                    )
                )
            else:
                base_angle = stop.angle_operand
            base_speed = stop.resume_speed
            magnitude = base_speed
            timer = _timer_set(0)
        else:
            magnitude = _sub(
                base_speed,
                _div(
                    _mul(float(timer.current), base_speed),
                    float(stop.duration),
                ),
            )
        velocity_x, velocity_y = _polar(
            base_angle,
            _mul(magnitude, ecl_time_scale),
        )
        stop = replace(
            stop,
            timer=_timer_tick(timer, timer_scale=timer_scale),
            repeat_count=repeat_count,
        )
    if not active & STOP_ACTIVE_MASK:
        stop = None

    if active & REFLECTION_ACTIVE_MASK:
        assert reflection is not None
        if not _inside_playfield(
            x,
            y,
            state.cull_half_width,
            state.cull_half_height,
        ):
            if x < 0.0 or x >= PLAYFIELD_WIDTH:
                base_angle = normalize_angle(
                    _sub(-base_angle, f32(math.pi))
                )
            if y < 0.0 or (
                y >= PLAYFIELD_HEIGHT
                and active & int(TransformKind.REFLECT_ALL_EDGES)
            ):
                base_angle = f32(-base_angle)
            base_speed = reflection.restored_speed
            velocity_x, velocity_y = _polar(
                base_angle,
                _mul(base_speed, ecl_time_scale),
            )
            event_count = reflection.event_count + 1
            if event_count >= reflection.event_limit:
                active &= ~REFLECTION_ACTIVE_MASK
            reflection = replace(reflection, event_count=event_count)
        if not active & REFLECTION_ACTIVE_MASK:
            reflection = None

    if active & int(TransformKind.WRAP_HORIZONTAL):
        assert wrap is not None
        if x < 0.0:
            x = _add(x, PLAYFIELD_WIDTH)
        elif x > PLAYFIELD_WIDTH:
            x = _sub(x, PLAYFIELD_WIDTH)
        if wrap.current <= 0:
            active ^= int(TransformKind.WRAP_HORIZONTAL)
        else:
            wrap = _timer_decrement(
                wrap,
                timer_scale=timer_scale,
                force_tick=timer_force_tick,
            )

    if active & int(TransformKind.WRAP_VERTICAL):
        assert wrap is not None
        if y < 0.0:
            y = _add(y, PLAYFIELD_HEIGHT)
        elif y > PLAYFIELD_HEIGHT:
            y = _sub(y, PLAYFIELD_HEIGHT)
        if wrap.current <= 0:
            active ^= int(TransformKind.WRAP_VERTICAL)
        else:
            wrap = _timer_decrement(
                wrap,
                timer_scale=timer_scale,
                force_tick=timer_force_tick,
            )
    if not active & WRAP_ACTIVE_MASK:
        wrap = None

    if active & int(TransformKind.TIMED_QUEUE_BARRIER):
        assert barrier is not None
        if barrier.current <= 0:
            active ^= int(TransformKind.TIMED_QUEUE_BARRIER)
            barrier = None
        else:
            barrier = _timer_decrement(
                barrier,
                timer_scale=timer_scale,
                force_tick=timer_force_tick,
            )

    if cull_countdown != 0:
        cull_countdown -= 1
    if not movement_frozen:
        x = _add(x, velocity_x)
        y = _add(y, velocity_y)

    retired = False
    if cull_countdown == 0:
        if not _inside_playfield(
            x,
            y,
            state.cull_half_width,
            state.cull_half_height,
        ):
            if active & OFFSCREEN_GRACE_ACTIVE_MASK:
                offscreen_counter = (offscreen_counter + 1) & 0xFFFF
                if offscreen_counter >= 0x80:
                    retired = True
            elif offscreen_counter == 0:
                retired = True
            else:
                offscreen_counter -= 1
        else:
            offscreen_counter = 0

    next_runtime = BulletTransformProgramRuntime(
        program=runtime.program,
        original_flags=runtime.original_flags,
        queue_cursor=cursor,
        cull_suppression_countdown=cull_countdown,
        offscreen_counter=offscreen_counter,
        decelerate_timer=decelerate,
        vector_acceleration=vector,
        angular_velocity=angular,
        stop=stop,
        reflection=reflection,
        barrier_timer=barrier,
        wrap_timer=wrap,
    )
    return replace(
        state,
        x=x,
        y=y,
        velocity_x=velocity_x,
        velocity_y=velocity_y,
        base_speed=base_speed,
        base_angle=base_angle,
        native_state=native_state,
        active_flags=active,
        runtime=next_runtime,
        retired=retired,
    )


__all__ = [
    "CurrentBulletTransformState",
    "CurrentTransformUnsupported",
    "OFFSCREEN_GRACE_ACTIVE_MASK",
    "SUPPORTED_ACTIVE_MASK",
    "state_from_bullet",
    "step_current_transform",
    "validate_current_transform_state",
]
