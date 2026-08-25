#!/usr/bin/env python3
"""Recovered TH08 bullet-transform record semantics.

The queue/setup behavior comes from bullet_apply_next_transform (0x0042FFC0),
reflection from 0x00432830, and timed wrap handlers from 0x004329F0 and
0x00432AA0. The derived-pattern transform consumes two adjacent 24-byte
records and is used by the stage-8/Extra corpus.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Mapping, Sequence


PLAYFIELD_WIDTH = 384.0
PLAYFIELD_HEIGHT = 448.0
TRANSFORM_PROGRAM_LENGTH = 18
TRANSFORM_RECORD_SIZE = 24
TRANSFORM_PROGRAM_SIZE = TRANSFORM_PROGRAM_LENGTH * TRANSFORM_RECORD_SIZE


class TransformKind(IntEnum):
    DECELERATE_16F = 0x0000001
    VECTOR_ACCELERATION = 0x0000010
    ANGULAR_VELOCITY = 0x0000020
    STOP_TURN_REPEAT = 0x0000040
    STOP_REAIM_REPEAT = 0x0000080
    STOP_SNAP_REPEAT = 0x0000100
    REFLECT_ALL_EDGES = 0x0000400
    REFLECT_SIDES_AND_TOP = 0x0000800
    SUPPRESS_OFFSCREEN_CULL = 0x0002000
    REPLACE_BULLET_TEMPLATE = 0x0004000
    TIMED_QUEUE_BARRIER = 0x0020000
    ENTER_FADE_STATE = 0x0040000
    PLAY_SOUND = 0x0080000
    WRAP_HORIZONTAL = 0x0400000
    WRAP_VERTICAL = 0x0800000
    EMIT_DERIVED_PATTERN = 0x1000000
    DERIVED_PATTERN_PARAMETERS = 0x2000000


@dataclass(frozen=True)
class TransformRecord:
    index: int
    kind: int
    allow_while_active: bool
    int_0: int
    int_1: int
    float_0: float | str
    float_1: float | str


@dataclass(frozen=True)
class BulletTransformRuntime:
    """Legacy queue plus stop-handler projection retained by old traces.

    This is intentionally *not* the complete native transform runtime.  The
    fields after ``next_record`` all come from the shared 0x1004 stop/turn
    block.  New retained roots use :class:`BulletTransformProgramRuntime`.
    """

    original_flags: int
    queue_cursor: int
    next_record: TransformRecord | None
    timer_fraction: float
    timer_elapsed: int
    resume_speed: float
    angle_operand: float
    duration: int
    repeat_limit: int
    repeat_count: int


@dataclass(frozen=True)
class TransformTimerRuntime:
    """One native ``ZunTimer`` embedded in a transform-handler block."""

    previous: int
    subframe: float
    current: int


@dataclass(frozen=True)
class VectorAccelerationRuntime:
    timer: TransformTimerRuntime
    magnitude: float
    angle: float
    acceleration_x: float
    acceleration_y: float
    duration: int


@dataclass(frozen=True)
class AngularVelocityRuntime:
    timer: TransformTimerRuntime
    speed_acceleration: float
    angular_velocity: float
    duration: int


@dataclass(frozen=True)
class StopTransformRuntime:
    timer: TransformTimerRuntime
    resume_speed: float
    angle_operand: float
    duration: int
    repeat_limit: int
    repeat_count: int


@dataclass(frozen=True)
class ReflectionTransformRuntime:
    restored_speed: float
    event_count: int
    event_limit: int


@dataclass(frozen=True)
class BulletTransformProgramRuntime:
    """Complete retained state required to resume the native transform queue.

    ``program`` is the exact 18-record, 432-byte native program.  Handler
    blocks are present only while their corresponding active flag is set, so
    inactive/uninitialized union bytes never become false state authority.
    """

    program: bytes
    original_flags: int
    queue_cursor: int
    cull_suppression_countdown: int
    offscreen_counter: int
    decelerate_timer: TransformTimerRuntime | None = None
    vector_acceleration: VectorAccelerationRuntime | None = None
    angular_velocity: AngularVelocityRuntime | None = None
    stop: StopTransformRuntime | None = None
    reflection: ReflectionTransformRuntime | None = None
    barrier_timer: TransformTimerRuntime | None = None
    wrap_timer: TransformTimerRuntime | None = None


@dataclass(frozen=True)
class DerivedPattern:
    kill_parent: bool
    mode: int
    bullet_type: int
    color: int
    start_transform_index: int
    count_1: int
    count_2: int
    angle_1: float | str
    angle_2: float | str
    speed_1: float | str
    speed_2: float | str
    child_transform_flags: int


@dataclass(frozen=True)
class ReflectionState:
    x: float
    y: float
    speed: float
    angle: float
    restored_speed: float
    event_limit: int
    event_count: int = 0
    active: bool = True


def parse_transform_record(
    blob: bytes | bytearray | memoryview,
    *,
    offset: int = 0,
    index: int = 0,
) -> TransformRecord:
    """Parse one native 24-byte record without interpreting its kind."""

    float_0, float_1, int_0, int_1, kind, allow_while_active = struct.unpack_from(
        "<ffiiII",
        blob,
        offset,
    )
    return TransformRecord(
        index=index,
        kind=kind,
        allow_while_active=bool(allow_while_active),
        int_0=int_0,
        int_1=int_1,
        float_0=float_0,
        float_1=float_1,
    )


def parse_next_transform_record(
    blob: bytes | bytearray | memoryview,
    *,
    program_offset: int,
    queue_cursor: int,
) -> TransformRecord | None:
    """Parse the next unconsumed record selected by the native queue cursor."""

    if not 0 <= queue_cursor < TRANSFORM_PROGRAM_LENGTH:
        return None
    return parse_transform_record(
        blob,
        offset=program_offset + queue_cursor * TRANSFORM_RECORD_SIZE,
        index=queue_cursor,
    )


def copy_transform_program(
    blob: bytes | bytearray | memoryview,
    *,
    program_offset: int = 0,
) -> bytes:
    """Copy exactly one native 18-record transform program."""

    view = memoryview(blob)
    end = program_offset + TRANSFORM_PROGRAM_SIZE
    if program_offset < 0 or end > len(view):
        raise ValueError("transform program is truncated")
    return bytes(view[program_offset:end])


def parse_transform_program(
    blob: bytes | bytearray | memoryview,
    *,
    program_offset: int = 0,
) -> tuple[TransformRecord, ...]:
    """Parse all 18 records, including zero terminators and unused slots."""

    program = copy_transform_program(blob, program_offset=program_offset)
    return tuple(
        parse_transform_record(
            program,
            offset=index * TRANSFORM_RECORD_SIZE,
            index=index,
        )
        for index in range(TRANSFORM_PROGRAM_LENGTH)
    )


def pack_transform_program(records: Sequence[TransformRecord]) -> bytes:
    """Pack an indexed prefix and zero-fill the remaining native records."""

    if len(records) > TRANSFORM_PROGRAM_LENGTH:
        raise ValueError("transform program exceeds the native 18-record limit")
    program = bytearray(TRANSFORM_PROGRAM_SIZE)
    for index, record in enumerate(records):
        if record.index != index:
            raise ValueError("transform records must be a canonical indexed prefix")
        if isinstance(record.float_0, str) or isinstance(record.float_1, str):
            raise ValueError("native transform programs cannot contain VM operands")
        try:
            struct.pack_into(
                "<ffiiII",
                program,
                index * TRANSFORM_RECORD_SIZE,
                float(record.float_0),
                float(record.float_1),
                int(record.int_0),
                int(record.int_1),
                int(record.kind),
                int(record.allow_while_active),
            )
        except (OverflowError, struct.error) as exc:
            raise ValueError("transform record does not fit the native ABI") from exc
    return bytes(program)


def transform_record_from_decoded(
    values: Mapping[str, int | float | str],
) -> TransformRecord:
    """Convert ``decode_bullet_transform`` output without losing VM operands."""

    integer_fields = ("index", "kind", "wait_for_clear", "int_0", "int_1")
    if any(not isinstance(values[key], (int, float)) for key in integer_fields):
        raise ValueError("transform control field contains an unresolved VM operand")
    return TransformRecord(
        index=int(values["index"]),
        kind=int(values["kind"]),
        allow_while_active=bool(values["wait_for_clear"]),
        int_0=int(values["int_0"]),
        int_1=int(values["int_1"]),
        float_0=(
            float(values["float_0"])
            if isinstance(values["float_0"], (int, float))
            else str(values["float_0"])
        ),
        float_1=(
            float(values["float_1"])
            if isinstance(values["float_1"], (int, float))
            else str(values["float_1"])
        ),
    )


def _signed_i16(value: int) -> int:
    value &= 0xFFFF
    return value if value < 0x8000 else value - 0x10000


def decode_derived_pattern(first: TransformRecord, second: TransformRecord) -> DerivedPattern:
    """Decode the exact two-record descriptor consumed at 0x0043065C."""

    if first.kind != TransformKind.EMIT_DERIVED_PATTERN:
        raise ValueError("first record is not a derived-pattern transform")
    if second.kind != TransformKind.DERIVED_PATTERN_PARAMETERS:
        raise ValueError("second record is not the shipped parameter extension")
    packed = first.int_0 & 0xFFFFFFFF
    return DerivedPattern(
        kill_parent=bool(packed & 0x80000000),
        mode=(packed >> 24) & 0x7F,
        bullet_type=(packed >> 16) & 0xFF,
        color=(packed >> 8) & 0xFF,
        start_transform_index=packed & 0xFF,
        count_1=_signed_i16(first.int_1),
        count_2=_signed_i16(second.int_0),
        angle_1=first.float_0,
        angle_2=first.float_1,
        speed_1=second.float_0,
        speed_2=second.float_1,
        child_transform_flags=second.int_1 & 0xFFFFFFFF,
    )


def transform_field_meanings(kind: int) -> dict[str, str]:
    """Return only field meanings directly established by setup/handler code."""

    meanings = {
        TransformKind.DECELERATE_16F: {},
        TransformKind.VECTOR_ACCELERATION: {
            "float_0": "acceleration magnitude",
            "float_1": "acceleration angle; <= -990 uses current bullet angle",
            "int_0": "duration frames",
        },
        TransformKind.ANGULAR_VELOCITY: {
            "float_0": "speed acceleration per frame",
            "float_1": "angular velocity per frame",
            "int_0": "duration frames",
        },
        TransformKind.STOP_TURN_REPEAT: {
            "float_0": "angle delta after each stop",
            "float_1": "resume speed; <= -999 uses current speed",
            "int_0": "deceleration/stop duration",
            "int_1": "repeat count",
        },
        TransformKind.STOP_REAIM_REPEAT: {
            "float_0": "offset added to angle-to-player after each stop",
            "float_1": "resume speed; <= -999 uses current speed",
            "int_0": "deceleration/stop duration",
            "int_1": "repeat count",
        },
        TransformKind.STOP_SNAP_REPEAT: {
            "float_0": "absolute angle after each stop",
            "float_1": "resume speed; <= -999 uses current speed",
            "int_0": "deceleration/stop duration",
            "int_1": "repeat count",
        },
        TransformKind.REFLECT_ALL_EDGES: {
            "float_0": "speed restored after reflection; negative uses current speed",
            "int_0": "offscreen reflection-event limit",
        },
        TransformKind.REFLECT_SIDES_AND_TOP: {
            "float_0": "speed restored after reflection; negative uses current speed",
            "int_0": "offscreen event limit; bottom exit is counted but not reflected",
        },
        TransformKind.SUPPRESS_OFFSCREEN_CULL: {
            "int_0": "offscreen-culling suppression countdown",
        },
        TransformKind.REPLACE_BULLET_TEMPLATE: {
            "int_0": "bullet template index",
            "int_1": "animation index adjustment",
        },
        TransformKind.TIMED_QUEUE_BARRIER: {
            "int_0": "active-transform countdown that blocks later queue records",
        },
        TransformKind.PLAY_SOUND: {"int_0": "spatialized sound id"},
        TransformKind.WRAP_HORIZONTAL: {"int_0": "wrap-active countdown"},
        TransformKind.WRAP_VERTICAL: {"int_0": "wrap-active countdown"},
        TransformKind.EMIT_DERIVED_PATTERN: {
            "float_0": "child angle_1",
            "float_1": "child angle_2",
            "int_0": "packed kill/mode/type/color/start-index",
            "int_1": "child count_1 (low signed 16 bits)",
        },
        TransformKind.DERIVED_PATTERN_PARAMETERS: {
            "float_0": "child speed_1",
            "float_1": "child speed_2",
            "int_0": "child count_2 (low signed 16 bits)",
            "int_1": "child original transform flags",
        },
    }
    try:
        return meanings[TransformKind(kind)]
    except (KeyError, ValueError):
        return {}


def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= math.tau
    while angle < -math.pi:
        angle += math.tau
    return angle


def _fully_outside_playfield(
    x: float, y: float, sprite_width: float, sprite_height: float
) -> bool:
    return (
        x + sprite_width / 2.0 < 0.0
        or x - sprite_width / 2.0 > PLAYFIELD_WIDTH
        or y + sprite_height / 2.0 < 0.0
        or y - sprite_height / 2.0 > PLAYFIELD_HEIGHT
    )


def apply_reflection_event(
    state: ReflectionState,
    *,
    kind: TransformKind,
    sprite_width: float,
    sprite_height: float,
) -> ReflectionState:
    """Apply one 0x400/0x800 handler call after bullet movement."""

    if kind not in (
        TransformKind.REFLECT_ALL_EDGES,
        TransformKind.REFLECT_SIDES_AND_TOP,
    ):
        raise ValueError("reflection kind must be 0x400 or 0x800")
    if not state.active or not _fully_outside_playfield(
        state.x, state.y, sprite_width, sprite_height
    ):
        return state

    angle = state.angle
    if state.x < 0.0 or state.x >= PLAYFIELD_WIDTH:
        angle = _normalize_angle(-angle - math.pi)
    if state.y < 0.0 or (
        state.y >= PLAYFIELD_HEIGHT and kind == TransformKind.REFLECT_ALL_EDGES
    ):
        angle = -angle
    event_count = state.event_count + 1
    return replace(
        state,
        speed=state.restored_speed,
        angle=angle,
        event_count=event_count,
        active=event_count < state.event_limit,
    )


def step_countdown_transform(frames_remaining: int) -> tuple[int, bool]:
    """Match the pre-decrement expiration used by barrier/wrap transforms."""

    if frames_remaining <= 0:
        return frames_remaining, False
    return frames_remaining - 1, True


def wrap_coordinate(value: float, *, vertical: bool) -> float:
    """Apply one strict-boundary wrap handler before its timer decrement."""

    extent = PLAYFIELD_HEIGHT if vertical else PLAYFIELD_WIDTH
    if value < 0.0:
        return value + extent
    if value > extent:
        return value - extent
    return value
