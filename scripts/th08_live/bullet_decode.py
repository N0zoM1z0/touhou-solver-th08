"""TH08 hostile-bullet pool decoding and ECL event attachment."""

from __future__ import annotations

import math
import struct
from dataclasses import replace

import numpy as np

from th08_bullet_template_contract import (
    BulletTemplateContractError,
    bullet_type_from_normal_script,
)
from th08_bullet_transform_model import (
    AngularVelocityRuntime,
    BulletTransformProgramRuntime,
    BulletTransformRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformTimerRuntime,
    VectorAccelerationRuntime,
    copy_transform_program,
    parse_next_transform_record,
)
from th08_ecl_runtime import (
    EclVmSnapshot,
    TaggedVelocityToggle,
    trajectory_changes_for_tagged_bullet,
)
from touhou_control import native_backend

from .models import Bullet, PackedBulletSnapshot
from .sensor import BULLET_POOL_SIZE, BULLET_STRIDE


BULLET_GEOMETRY_OFFSET = 0x0D34
BULLET_NORMAL_SCRIPT_INDEX_OFFSET = 0x021A
BULLET_CALLBACK_PHASE_STATE_OFFSET = 0x01FC
BULLET_POSITION_OFFSET = 0x0D44
BULLET_VELOCITY_OFFSET = 0x0D50
BULLET_SPEED_OFFSET = 0x0D68
BULLET_ANGLE_OFFSET = 0x0D74
BULLET_CULL_SUPPRESSION_COUNTDOWN_OFFSET = 0x0DA8
BULLET_TRANSFORM_FLAGS_OFFSET = 0x0DAC
BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET = 0x0DB0
BULLET_STATE_OFFSET = 0x0DB8
BULLET_OFFSCREEN_COUNTER_OFFSET = 0x0DBA
BULLET_STATE_TIMER_ELAPSED_OFFSET = 0x0D88
BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET = 0x0DCC
BULLET_TRANSFORM_PROGRAM_OFFSET = 0x0DD0
BULLET_DECELERATE_TIMER_OFFSET = 0x0F80
BULLET_VECTOR_TIMER_OFFSET = 0x0FAC
BULLET_VECTOR_MAGNITUDE_OFFSET = 0x0FB8
BULLET_VECTOR_ANGLE_OFFSET = 0x0FBC
BULLET_VECTOR_ACCELERATION_OFFSET = 0x0FC0
BULLET_VECTOR_DURATION_OFFSET = 0x0FCC
BULLET_ANGULAR_TIMER_OFFSET = 0x0FD8
BULLET_ANGULAR_SPEED_ACCELERATION_OFFSET = 0x0FE4
BULLET_ANGULAR_VELOCITY_OFFSET = 0x0FE8
BULLET_ANGULAR_DURATION_OFFSET = 0x0FF8
BULLET_STOP_TIMER_OFFSET = 0x1004
BULLET_STOP_TIMER_FRACTION_OFFSET = 0x1008
BULLET_STOP_TIMER_ELAPSED_OFFSET = 0x100C
BULLET_STOP_RESUME_SPEED_OFFSET = 0x1010
BULLET_STOP_ANGLE_OPERAND_OFFSET = 0x1014
BULLET_STOP_DURATION_OFFSET = 0x1024
BULLET_STOP_REPEAT_LIMIT_OFFSET = 0x1028
BULLET_STOP_REPEAT_COUNT_OFFSET = 0x102C
BULLET_REFLECTION_RESTORED_SPEED_OFFSET = 0x103C
BULLET_REFLECTION_EVENT_COUNT_OFFSET = 0x1050
BULLET_REFLECTION_EVENT_LIMIT_OFFSET = 0x1054
BULLET_BARRIER_TIMER_OFFSET = 0x105C
BULLET_WRAP_TIMER_OFFSET = 0x1088
BULLET_CALLBACK_AUX_STATE_OFFSET = 0x10B4

PLANNING_BULLET_VECTOR_THRESHOLD = 512
NATIVE_PACKED_BULLET_MIN_COUNT = 16


def finite(values: tuple[float, ...]) -> bool:
    return all(math.isfinite(value) for value in values)


def _transform_timer_runtime(
    blob: bytes,
    *,
    offset: int,
) -> TransformTimerRuntime:
    previous, subframe, current = struct.unpack_from("<ifi", blob, offset)
    return TransformTimerRuntime(
        previous=previous,
        subframe=subframe,
        current=current,
    )


def native_bullet_half_extents(
    width: float,
    height: float,
) -> tuple[float, float]:
    """Preserve the dimensions passed to native bullet collision."""

    return abs(width) * 0.5, abs(height) * 0.5


def _native_bullet_type(normal_script_index: int) -> int | None:
    try:
        return bullet_type_from_normal_script(normal_script_index)
    except BulletTemplateContractError:
        return None


def _native_bullet_type_index(normal_script_index: int) -> int:
    bullet_type = _native_bullet_type(normal_script_index)
    return bullet_type if bullet_type is not None else -1


def planning_bullet_active_slots(
    blob: bytes | bytearray | memoryview,
) -> np.ndarray:
    return np.flatnonzero(
        np.ndarray(
            (BULLET_POOL_SIZE,),
            dtype="<u2",
            buffer=blob,
            offset=BULLET_STATE_OFFSET,
            strides=(BULLET_STRIDE,),
        )
    )


def decode_planning_bullets(
    blob: bytes | bytearray | memoryview,
    *,
    active_slots: np.ndarray | None = None,
) -> tuple[Bullet, ...]:
    """Decode gameplay fields in bulk without diagnostic queue objects."""

    required_size = BULLET_POOL_SIZE * BULLET_STRIDE
    if len(blob) < required_size:
        raise ValueError(f"bullet pool requires {required_size} bytes")

    def scalar_field(offset: int, dtype: str) -> np.ndarray:
        return np.ndarray(
            (BULLET_POOL_SIZE,),
            dtype=dtype,
            buffer=blob,
            offset=offset,
            strides=(BULLET_STRIDE,),
        )

    def pair_field(offset: int, dtype: str) -> np.ndarray:
        item_size = np.dtype(dtype).itemsize
        return np.ndarray(
            (BULLET_POOL_SIZE, 2),
            dtype=dtype,
            buffer=blob,
            offset=offset,
            strides=(BULLET_STRIDE, item_size),
        )

    slots = (
        planning_bullet_active_slots(blob)
        if active_slots is None
        else active_slots
    )
    if not slots.size:
        return ()
    if slots.size < PLANNING_BULLET_VECTOR_THRESHOLD:
        bullets: list[Bullet] = []
        for slot in slots:
            base = int(slot) * BULLET_STRIDE
            width, height = struct.unpack_from(
                "<ff",
                blob,
                base + BULLET_GEOMETRY_OFFSET,
            )
            x, y = struct.unpack_from(
                "<ff",
                blob,
                base + BULLET_POSITION_OFFSET,
            )
            vx, vy = struct.unpack_from(
                "<ff",
                blob,
                base + BULLET_VELOCITY_OFFSET,
            )
            if not finite((x, y, vx, vy, width, height)):
                continue
            half_width, half_height = native_bullet_half_extents(
                width,
                height,
            )
            speed = struct.unpack_from(
                "<f",
                blob,
                base + BULLET_SPEED_OFFSET,
            )[0]
            angle = struct.unpack_from(
                "<f",
                blob,
                base + BULLET_ANGLE_OFFSET,
            )[0]
            bullets.append(
                Bullet(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    half_width=half_width,
                    half_height=half_height,
                    transform_flags=struct.unpack_from(
                        "<I",
                        blob,
                        base + BULLET_TRANSFORM_FLAGS_OFFSET,
                    )[0],
                    slot=int(slot),
                    speed=speed if math.isfinite(speed) else None,
                    angle=angle if math.isfinite(angle) else None,
                    callback_phase_state=struct.unpack_from(
                        "<h",
                        blob,
                        base + BULLET_CALLBACK_PHASE_STATE_OFFSET,
                    )[0],
                    callback_aux_state=blob[
                        base + BULLET_CALLBACK_AUX_STATE_OFFSET
                    ],
                    original_transform_flags=struct.unpack_from(
                        "<I",
                        blob,
                        base + BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
                    )[0],
                    native_state=struct.unpack_from(
                        "<H",
                        blob,
                        base + BULLET_STATE_OFFSET,
                    )[0],
                    native_state_timer_elapsed=struct.unpack_from(
                        "<i",
                        blob,
                        base + BULLET_STATE_TIMER_ELAPSED_OFFSET,
                    )[0],
                    bullet_type=_native_bullet_type(
                        struct.unpack_from(
                            "<h",
                            blob,
                            base + BULLET_NORMAL_SCRIPT_INDEX_OFFSET,
                        )[0]
                    ),
                )
            )
        return tuple(bullets)
    geometry = pair_field(BULLET_GEOMETRY_OFFSET, "<f4")[slots]
    position = pair_field(BULLET_POSITION_OFFSET, "<f4")[slots]
    velocity = pair_field(BULLET_VELOCITY_OFFSET, "<f4")[slots]
    finite_rows = np.isfinite(
        np.concatenate((geometry, position, velocity), axis=1)
    ).all(axis=1)
    if not np.all(finite_rows):
        slots = slots[finite_rows]
        geometry = geometry[finite_rows]
        position = position[finite_rows]
        velocity = velocity[finite_rows]
    speed = scalar_field(BULLET_SPEED_OFFSET, "<f4")[slots]
    angle = scalar_field(BULLET_ANGLE_OFFSET, "<f4")[slots]
    transform_flags = scalar_field(
        BULLET_TRANSFORM_FLAGS_OFFSET,
        "<u4",
    )[slots]
    original_flags = scalar_field(
        BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
        "<u4",
    )[slots]
    callback_phase = scalar_field(
        BULLET_CALLBACK_PHASE_STATE_OFFSET,
        "<i2",
    )[slots]
    callback_aux = scalar_field(
        BULLET_CALLBACK_AUX_STATE_OFFSET,
        "u1",
    )[slots]
    native_state = scalar_field(BULLET_STATE_OFFSET, "<u2")[slots]
    native_state_timer_elapsed = scalar_field(
        BULLET_STATE_TIMER_ELAPSED_OFFSET,
        "<i4",
    )[slots]
    normal_script_index = scalar_field(
        BULLET_NORMAL_SCRIPT_INDEX_OFFSET,
        "<i2",
    )[slots]
    bullet_type = np.fromiter(
        (
            _native_bullet_type_index(int(script))
            for script in normal_script_index
        ),
        dtype=np.int16,
        count=len(slots),
    )
    half_size = np.abs(geometry) * 0.5
    return tuple(
        Bullet(
            x=float(x),
            y=float(y),
            vx=float(vx),
            vy=float(vy),
            half_width=float(half_width),
            half_height=float(half_height),
            transform_flags=int(active_flags),
            slot=int(slot),
            speed=(
                float(native_speed)
                if math.isfinite(native_speed)
                else None
            ),
            angle=(
                float(native_angle)
                if math.isfinite(native_angle)
                else None
            ),
            callback_phase_state=int(phase),
            callback_aux_state=int(auxiliary),
            original_transform_flags=int(tag_flags),
            native_state=int(state),
            native_state_timer_elapsed=int(state_timer_elapsed),
            bullet_type=(int(type_index) if type_index >= 0 else None),
        )
        for (
            slot,
            (x, y),
            (vx, vy),
            (half_width, half_height),
            active_flags,
            native_speed,
            native_angle,
            tag_flags,
            phase,
            auxiliary,
            state,
            state_timer_elapsed,
            type_index,
        ) in zip(
            slots,
            position,
            velocity,
            half_size,
            transform_flags,
            speed,
            angle,
            original_flags,
            callback_phase,
            callback_aux,
            native_state,
            native_state_timer_elapsed,
            bullet_type,
        )
    )


def decode_packed_bullets(
    blob: bytes | bytearray | memoryview,
) -> PackedBulletSnapshot:
    """Decode the live planning snapshot through the parity-gated C ABI."""

    decoded = native_backend.decode_bullet_pool(
        blob,
        record_count=BULLET_POOL_SIZE,
        stride=BULLET_STRIDE,
        state_offset=BULLET_STATE_OFFSET,
        geometry_offset=BULLET_GEOMETRY_OFFSET,
        position_offset=BULLET_POSITION_OFFSET,
        velocity_offset=BULLET_VELOCITY_OFFSET,
        speed_offset=BULLET_SPEED_OFFSET,
        angle_offset=BULLET_ANGLE_OFFSET,
        transform_flags_offset=BULLET_TRANSFORM_FLAGS_OFFSET,
        original_transform_flags_offset=(
            BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET
        ),
        callback_phase_offset=BULLET_CALLBACK_PHASE_STATE_OFFSET,
        callback_aux_offset=BULLET_CALLBACK_AUX_STATE_OFFSET,
    )
    if decoded is None:
        raise RuntimeError("native packed bullet decoder is unavailable")
    native_state = np.ndarray(
        (BULLET_POOL_SIZE,),
        dtype="<u2",
        buffer=blob,
        offset=BULLET_STATE_OFFSET,
        strides=(BULLET_STRIDE,),
    )[decoded.slots].copy()
    native_state_timer_elapsed = np.ndarray(
        (BULLET_POOL_SIZE,),
        dtype="<i4",
        buffer=blob,
        offset=BULLET_STATE_TIMER_ELAPSED_OFFSET,
        strides=(BULLET_STRIDE,),
    )[decoded.slots].copy()
    normal_script_index = np.ndarray(
        (BULLET_POOL_SIZE,),
        dtype="<i2",
        buffer=blob,
        offset=BULLET_NORMAL_SCRIPT_INDEX_OFFSET,
        strides=(BULLET_STRIDE,),
    )[decoded.slots]
    bullet_type = np.fromiter(
        (
            _native_bullet_type_index(int(script))
            for script in normal_script_index
        ),
        dtype=np.int16,
        count=len(decoded.slots),
    )
    return PackedBulletSnapshot(
        x=decoded.x,
        y=decoded.y,
        velocity_x=decoded.velocity_x,
        velocity_y=decoded.velocity_y,
        half_width=decoded.half_width,
        half_height=decoded.half_height,
        transform_flags=decoded.transform_flags,
        slots=decoded.slots,
        speed=decoded.speed,
        angle=decoded.angle,
        callback_phase=decoded.callback_phase,
        callback_aux=decoded.callback_aux,
        original_transform_flags=decoded.original_transform_flags,
        native_state=native_state,
        native_state_timer_elapsed=native_state_timer_elapsed,
        bullet_type=bullet_type,
    )


def decode_live_planning_bullets(
    blob: bytes | bytearray | memoryview,
    *,
    backend: str,
) -> tuple[Bullet, ...] | PackedBulletSnapshot:
    """Decode with the selected rollback and sparse crossover."""

    if backend == "python":
        return decode_planning_bullets(blob)
    if backend != "native":
        raise ValueError(f"unknown bullet decode backend {backend!r}")
    active_slots = planning_bullet_active_slots(blob)
    if len(active_slots) < NATIVE_PACKED_BULLET_MIN_COUNT:
        return decode_planning_bullets(
            blob,
            active_slots=active_slots,
        )
    return decode_packed_bullets(blob)


def decode_bullets(
    blob: bytes,
    *,
    retain_transform_runtime: bool = True,
) -> tuple[Bullet, ...]:
    """Decode active bullets with optional diagnostic queue state."""

    if not retain_transform_runtime:
        return decode_planning_bullets(blob)
    bullets: list[Bullet] = []
    for index in range(BULLET_POOL_SIZE):
        base = index * BULLET_STRIDE
        state = struct.unpack_from(
            "<H",
            blob,
            base + BULLET_STATE_OFFSET,
        )[0]
        if state == 0:
            continue
        width, height = struct.unpack_from(
            "<ff",
            blob,
            base + BULLET_GEOMETRY_OFFSET,
        )
        x, y = struct.unpack_from(
            "<ff",
            blob,
            base + BULLET_POSITION_OFFSET,
        )
        vx, vy = struct.unpack_from(
            "<ff",
            blob,
            base + BULLET_VELOCITY_OFFSET,
        )
        speed = struct.unpack_from(
            "<f",
            blob,
            base + BULLET_SPEED_OFFSET,
        )[0]
        angle = struct.unpack_from(
            "<f",
            blob,
            base + BULLET_ANGLE_OFFSET,
        )[0]
        callback_phase_state = struct.unpack_from(
            "<h",
            blob,
            base + BULLET_CALLBACK_PHASE_STATE_OFFSET,
        )[0]
        callback_aux_state = blob[
            base + BULLET_CALLBACK_AUX_STATE_OFFSET
        ]
        transform_flags = struct.unpack_from(
            "<I",
            blob,
            base + BULLET_TRANSFORM_FLAGS_OFFSET,
        )[0]
        original_transform_flags = struct.unpack_from(
            "<I",
            blob,
            base + BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
        )[0]
        if not finite((x, y, vx, vy, width, height)):
            continue
        half_width, half_height = native_bullet_half_extents(
            width,
            height,
        )
        transform_runtime = None
        transform_program_runtime = None
        queue_cursor = struct.unpack_from(
            "<i",
            blob,
            base + BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET,
        )[0]
        next_record = parse_next_transform_record(
            blob,
            program_offset=base + BULLET_TRANSFORM_PROGRAM_OFFSET,
            queue_cursor=queue_cursor,
        )
        if (
            transform_flags
            or original_transform_flags
            or (next_record is not None and next_record.kind)
        ):
            program = copy_transform_program(
                blob,
                program_offset=base + BULLET_TRANSFORM_PROGRAM_OFFSET,
            )
            transform_runtime = BulletTransformRuntime(
                original_flags=original_transform_flags,
                queue_cursor=queue_cursor,
                next_record=next_record,
                timer_fraction=struct.unpack_from(
                    "<f",
                    blob,
                    base + BULLET_STOP_TIMER_FRACTION_OFFSET,
                )[0],
                timer_elapsed=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_STOP_TIMER_ELAPSED_OFFSET,
                )[0],
                resume_speed=struct.unpack_from(
                    "<f",
                    blob,
                    base + BULLET_STOP_RESUME_SPEED_OFFSET,
                )[0],
                angle_operand=struct.unpack_from(
                    "<f",
                    blob,
                    base + BULLET_STOP_ANGLE_OPERAND_OFFSET,
                )[0],
                duration=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_STOP_DURATION_OFFSET,
                )[0],
                repeat_limit=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_STOP_REPEAT_LIMIT_OFFSET,
                )[0],
                repeat_count=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_STOP_REPEAT_COUNT_OFFSET,
                )[0],
            )
            vector_acceleration = None
            if transform_flags & int(TransformKind.VECTOR_ACCELERATION):
                acceleration_x, acceleration_y = struct.unpack_from(
                    "<ff",
                    blob,
                    base + BULLET_VECTOR_ACCELERATION_OFFSET,
                )
                vector_acceleration = VectorAccelerationRuntime(
                    timer=_transform_timer_runtime(
                        blob,
                        offset=base + BULLET_VECTOR_TIMER_OFFSET,
                    ),
                    magnitude=struct.unpack_from(
                        "<f", blob, base + BULLET_VECTOR_MAGNITUDE_OFFSET
                    )[0],
                    angle=struct.unpack_from(
                        "<f", blob, base + BULLET_VECTOR_ANGLE_OFFSET
                    )[0],
                    acceleration_x=acceleration_x,
                    acceleration_y=acceleration_y,
                    duration=struct.unpack_from(
                        "<i", blob, base + BULLET_VECTOR_DURATION_OFFSET
                    )[0],
                )
            angular_velocity = None
            if transform_flags & int(TransformKind.ANGULAR_VELOCITY):
                angular_velocity = AngularVelocityRuntime(
                    timer=_transform_timer_runtime(
                        blob,
                        offset=base + BULLET_ANGULAR_TIMER_OFFSET,
                    ),
                    speed_acceleration=struct.unpack_from(
                        "<f",
                        blob,
                        base + BULLET_ANGULAR_SPEED_ACCELERATION_OFFSET,
                    )[0],
                    angular_velocity=struct.unpack_from(
                        "<f", blob, base + BULLET_ANGULAR_VELOCITY_OFFSET
                    )[0],
                    duration=struct.unpack_from(
                        "<i", blob, base + BULLET_ANGULAR_DURATION_OFFSET
                    )[0],
                )
            stop = None
            if transform_flags & int(
                TransformKind.STOP_TURN_REPEAT
                | TransformKind.STOP_REAIM_REPEAT
                | TransformKind.STOP_SNAP_REPEAT
            ):
                stop = StopTransformRuntime(
                    timer=_transform_timer_runtime(
                        blob,
                        offset=base + BULLET_STOP_TIMER_OFFSET,
                    ),
                    resume_speed=transform_runtime.resume_speed,
                    angle_operand=transform_runtime.angle_operand,
                    duration=transform_runtime.duration,
                    repeat_limit=transform_runtime.repeat_limit,
                    repeat_count=transform_runtime.repeat_count,
                )
            reflection = None
            if transform_flags & int(
                TransformKind.REFLECT_ALL_EDGES
                | TransformKind.REFLECT_SIDES_AND_TOP
            ):
                reflection = ReflectionTransformRuntime(
                    restored_speed=struct.unpack_from(
                        "<f",
                        blob,
                        base + BULLET_REFLECTION_RESTORED_SPEED_OFFSET,
                    )[0],
                    event_count=struct.unpack_from(
                        "<i",
                        blob,
                        base + BULLET_REFLECTION_EVENT_COUNT_OFFSET,
                    )[0],
                    event_limit=struct.unpack_from(
                        "<i",
                        blob,
                        base + BULLET_REFLECTION_EVENT_LIMIT_OFFSET,
                    )[0],
                )
            transform_program_runtime = BulletTransformProgramRuntime(
                program=program,
                original_flags=original_transform_flags,
                queue_cursor=queue_cursor,
                cull_suppression_countdown=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_CULL_SUPPRESSION_COUNTDOWN_OFFSET,
                )[0],
                offscreen_counter=struct.unpack_from(
                    "<H",
                    blob,
                    base + BULLET_OFFSCREEN_COUNTER_OFFSET,
                )[0],
                decelerate_timer=(
                    _transform_timer_runtime(
                        blob,
                        offset=base + BULLET_DECELERATE_TIMER_OFFSET,
                    )
                    if transform_flags & int(TransformKind.DECELERATE_16F)
                    else None
                ),
                vector_acceleration=vector_acceleration,
                angular_velocity=angular_velocity,
                stop=stop,
                reflection=reflection,
                barrier_timer=(
                    _transform_timer_runtime(
                        blob,
                        offset=base + BULLET_BARRIER_TIMER_OFFSET,
                    )
                    if transform_flags & int(TransformKind.TIMED_QUEUE_BARRIER)
                    else None
                ),
                wrap_timer=(
                    _transform_timer_runtime(
                        blob,
                        offset=base + BULLET_WRAP_TIMER_OFFSET,
                    )
                    if transform_flags
                    & int(
                        TransformKind.WRAP_HORIZONTAL
                        | TransformKind.WRAP_VERTICAL
                    )
                    else None
                ),
            )
        bullets.append(
            Bullet(
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                half_width=half_width,
                half_height=half_height,
                transform_flags=transform_flags,
                slot=index,
                speed=speed if math.isfinite(speed) else None,
                angle=angle if math.isfinite(angle) else None,
                transform_runtime=transform_runtime,
                transform_program_runtime=transform_program_runtime,
                callback_phase_state=callback_phase_state,
                callback_aux_state=callback_aux_state,
                original_transform_flags=original_transform_flags,
                native_state=state,
                native_state_timer_elapsed=struct.unpack_from(
                    "<i",
                    blob,
                    base + BULLET_STATE_TIMER_ELAPSED_OFFSET,
                )[0],
                bullet_type=_native_bullet_type(
                    struct.unpack_from(
                        "<h",
                        blob,
                        base + BULLET_NORMAL_SCRIPT_INDEX_OFFSET,
                    )[0]
                ),
            )
        )
    return tuple(bullets)


def attach_tagged_velocity_toggles(
    bullets: tuple[Bullet, ...],
    *,
    vm_snapshot: EclVmSnapshot,
    toggles: tuple[TaggedVelocityToggle, ...],
    frame_offset: int = 0,
    event_frame_uncertainty: int = 0,
) -> tuple[Bullet, ...]:
    """Attach callback-12 events in each bullet snapshot coordinate."""

    if frame_offset < 0 or event_frame_uncertainty < 0:
        raise ValueError("ECL event alignment values cannot be negative")
    if not toggles:
        return bullets
    aligned_toggles = tuple(
        replace(toggle, frame=toggle.frame + frame_offset)
        for toggle in toggles
    )
    attached: list[Bullet] = []
    for bullet in bullets:
        runtime = bullet.transform_runtime
        tag_flags = (
            bullet.original_transform_flags
            or (runtime.original_flags if runtime is not None else 0)
        )
        changes = trajectory_changes_for_tagged_bullet(
            tag_flags=tag_flags,
            phase_state=bullet.callback_phase_state,
            base_speed=bullet.speed,
            base_angle=bullet.angle,
            time_scale=vm_snapshot.time_scale,
            toggles=aligned_toggles,
        )
        uncertainty_x = bullet.trajectory_uncertainty_x
        uncertainty_y = bullet.trajectory_uncertainty_y
        previous_x = bullet.vx
        previous_y = bullet.vy
        for change in changes.velocity_changes:
            uncertainty_x += (
                abs(change.velocity_x - previous_x)
                * event_frame_uncertainty
            )
            uncertainty_y += (
                abs(change.velocity_y - previous_y)
                * event_frame_uncertainty
            )
            previous_x = change.velocity_x
            previous_y = change.velocity_y
        attached.append(
            replace(
                bullet,
                velocity_changes=changes.velocity_changes,
                collision_state_changes=changes.collision_changes,
                trajectory_uncertainty_x=uncertainty_x,
                trajectory_uncertainty_y=uncertainty_y,
            )
            if changes.velocity_changes or changes.collision_changes
            else bullet
        )
    return tuple(attached)


__all__ = [
    "BULLET_ANGLE_OFFSET",
    "BULLET_CALLBACK_AUX_STATE_OFFSET",
    "BULLET_CALLBACK_PHASE_STATE_OFFSET",
    "BULLET_GEOMETRY_OFFSET",
    "BULLET_NORMAL_SCRIPT_INDEX_OFFSET",
    "BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET",
    "BULLET_POSITION_OFFSET",
    "BULLET_SPEED_OFFSET",
    "BULLET_STATE_OFFSET",
    "BULLET_STATE_TIMER_ELAPSED_OFFSET",
    "BULLET_STOP_ANGLE_OPERAND_OFFSET",
    "BULLET_STOP_DURATION_OFFSET",
    "BULLET_STOP_REPEAT_COUNT_OFFSET",
    "BULLET_STOP_REPEAT_LIMIT_OFFSET",
    "BULLET_STOP_RESUME_SPEED_OFFSET",
    "BULLET_STOP_TIMER_ELAPSED_OFFSET",
    "BULLET_STOP_TIMER_FRACTION_OFFSET",
    "BULLET_TRANSFORM_FLAGS_OFFSET",
    "BULLET_TRANSFORM_PROGRAM_OFFSET",
    "BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET",
    "BULLET_VELOCITY_OFFSET",
    "NATIVE_PACKED_BULLET_MIN_COUNT",
    "PLANNING_BULLET_VECTOR_THRESHOLD",
    "attach_tagged_velocity_toggles",
    "decode_bullets",
    "decode_live_planning_bullets",
    "decode_packed_bullets",
    "decode_planning_bullets",
    "finite",
    "native_bullet_half_extents",
    "planning_bullet_active_slots",
]
