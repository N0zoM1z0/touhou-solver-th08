"""Decode TH08 laser and item pools into immutable live sensing values."""

from __future__ import annotations

import struct
from typing import Sequence

from th08_laser_model import LaserPhase, LaserState
from th08_laser_runtime import Laser
from th08_live.bullet_decode import finite
from th08_live.models import Item
from th08_live.sensor import (
    ITEM_POOL_SIZE,
    ITEM_STRIDE,
    LASER_POOL_SIZE,
    LASER_STRIDE,
)

LASER_ORIGIN_OFFSET = 0x0548
LASER_ANGLE_OFFSET = 0x0554
LASER_TAIL_OFFSET = 0x0558
LASER_HEAD_OFFSET = 0x055C
LASER_MAXIMUM_LENGTH_OFFSET = 0x0560
LASER_WIDTH_OFFSET = 0x0564
LASER_CURRENT_WIDTH_OFFSET = 0x0568
LASER_SPEED_OFFSET = 0x056C
LASER_WARMUP_FRAMES_OFFSET = 0x0570
LASER_COLLISION_ENABLE_FRAME_OFFSET = 0x0574
LASER_ACTIVE_FRAMES_OFFSET = 0x0578
LASER_FADE_FRAMES_OFFSET = 0x057C
LASER_COLLISION_DISABLE_FRAME_OFFSET = 0x0580
LASER_ACTIVE_OFFSET = 0x0584
LASER_TIMER_OFFSET = 0x0590
LASER_TIMER_FRACTION_OFFSET = 0x058C
LASER_FLAGS_OFFSET = 0x0594
LASER_PHASE_OFFSET = 0x0598
LASER_COLLISION_FLAG_OFFSET = 0x0599

ITEM_POSITION_OFFSET = 0x02A4
ITEM_VELOCITY_OFFSET = 0x02B0
ITEM_TYPE_OFFSET = 0x02D4
ITEM_ACTIVE_OFFSET = 0x02D5
ITEM_MOTION_STATE_OFFSET = 0x02D7
ITEM_FULL_VALUE_OFFSET = 0x02D8


def decode_lasers(
    blob: bytes,
    *,
    record_slots: Sequence[int] | None = None,
) -> tuple[Laser, ...]:
    slots = (
        tuple(range(LASER_POOL_SIZE))
        if record_slots is None
        else tuple(record_slots)
    )
    required_size = len(slots) * LASER_STRIDE
    if (
        len(blob) < required_size
        or (record_slots is not None and len(blob) != required_size)
    ):
        raise ValueError(f"laser records require {required_size} bytes")
    if (
        any(type(slot) is not int or not 0 <= slot < LASER_POOL_SIZE for slot in slots)
        or len(set(slots)) != len(slots)
    ):
        raise ValueError("laser record slots are invalid or duplicated")
    lasers: list[Laser] = []
    for record_index, slot in enumerate(slots):
        base = record_index * LASER_STRIDE
        if not struct.unpack_from("<I", blob, base + LASER_ACTIVE_OFFSET)[0]:
            continue
        origin_x, origin_y = struct.unpack_from(
            "<ff",
            blob,
            base + LASER_ORIGIN_OFFSET,
        )
        angle = struct.unpack_from("<f", blob, base + LASER_ANGLE_OFFSET)[0]
        tail = struct.unpack_from("<f", blob, base + LASER_TAIL_OFFSET)[0]
        head = struct.unpack_from("<f", blob, base + LASER_HEAD_OFFSET)[0]
        maximum_length, width, current_width, speed = struct.unpack_from(
            "<ffff",
            blob,
            base + LASER_MAXIMUM_LENGTH_OFFSET,
        )
        (
            warmup_frames,
            collision_enable_frame,
            active_frames,
            fade_frames,
            collision_disable_frame,
        ) = struct.unpack_from(
            "<iiiii",
            blob,
            base + LASER_WARMUP_FRAMES_OFFSET,
        )
        timer = struct.unpack_from("<i", blob, base + LASER_TIMER_OFFSET)[0]
        timer_fraction = struct.unpack_from(
            "<f",
            blob,
            base + LASER_TIMER_FRACTION_OFFSET,
        )[0]
        flags = struct.unpack_from("<H", blob, base + LASER_FLAGS_OFFSET)[0]
        phase_value = blob[base + LASER_PHASE_OFFSET]
        collision_flag = blob[base + LASER_COLLISION_FLAG_OFFSET]
        if not finite(
            (
                origin_x,
                origin_y,
                angle,
                tail,
                head,
                maximum_length,
                width,
                current_width,
                speed,
                timer_fraction,
            )
        ):
            continue
        if (
            phase_value not in tuple(int(phase) for phase in LaserPhase)
            or min(
                maximum_length,
                width,
                warmup_frames,
                collision_enable_frame,
                active_frames,
                fade_frames,
                collision_disable_frame,
                timer,
            )
            < 0
        ):
            continue
        state = LaserState(
            origin_x=origin_x,
            origin_y=origin_y,
            angle=angle,
            tail_distance=tail,
            head_distance=head,
            maximum_length=maximum_length,
            width=width,
            speed=speed,
            warmup_frames=warmup_frames,
            active_frames=active_frames,
            fade_frames=fade_frames,
            collision_enable_frame=collision_enable_frame,
            collision_disable_frame=collision_disable_frame,
            flags=flags,
            current_width=current_width,
            phase=LaserPhase(phase_value),
            timer=timer,
            timer_fraction=timer_fraction,
        )
        lasers.append(
            Laser(
                origin_x,
                origin_y,
                angle,
                tail,
                head,
                min(abs(width) * 0.25, 64.0),
                state,
                slot,
                collision_flag,
                0.75,
                0.0,
            )
        )
    return tuple(lasers)


def decode_items(
    blob: bytes,
    *,
    record_slots: Sequence[int] | None = None,
) -> tuple[Item, ...]:
    slots = (
        tuple(range(ITEM_POOL_SIZE))
        if record_slots is None
        else tuple(record_slots)
    )
    required_size = len(slots) * ITEM_STRIDE
    if (
        len(blob) < required_size
        or (record_slots is not None and len(blob) != required_size)
    ):
        raise ValueError(f"item records require {required_size} bytes")
    if (
        any(type(slot) is not int or not 0 <= slot < ITEM_POOL_SIZE for slot in slots)
        or len(set(slots)) != len(slots)
    ):
        raise ValueError("item record slots are invalid or duplicated")
    items: list[Item] = []
    for record_index, slot in enumerate(slots):
        base = record_index * ITEM_STRIDE
        if not blob[base + ITEM_ACTIVE_OFFSET]:
            continue
        x, y = struct.unpack_from("<ff", blob, base + ITEM_POSITION_OFFSET)
        vx, vy = struct.unpack_from("<ff", blob, base + ITEM_VELOCITY_OFFSET)
        if not finite((x, y, vx, vy)):
            continue
        items.append(
            Item(
                slot=slot,
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                item_type=blob[base + ITEM_TYPE_OFFSET],
                motion_state=blob[base + ITEM_MOTION_STATE_OFFSET],
                full_value=bool(blob[base + ITEM_FULL_VALUE_OFFSET]),
            )
        )
    return tuple(items)
