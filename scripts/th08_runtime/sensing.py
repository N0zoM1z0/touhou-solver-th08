"""Pure TH08 state decoding over a narrow process-reader protocol."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Protocol

from th08_runtime.game_state import (
    ADDR_CURRENT_INPUT,
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_ENGINE_FLAGS,
    ADDR_FRSCREEN_IMPL_POINTER,
    ADDR_FRSCREEN_UPDATE_SERIAL,
    ADDR_GAMEPLAY_RNG,
    ADDR_GAMEPLAY_TIME_SCALE,
    ADDR_PLAYER,
    ADDR_PREVIOUS_INPUT,
    ADDR_RAW_INPUT,
    ADDR_ROUTE_ID,
    ADDR_RUN_STATE_INNER_POINTER,
    ADDR_SCRIPTED_UPDATE_FREEZE,
    ADDR_SPELL_CARD_STATE,
    ADDR_STAGE_ROUTE_INDEX,
    FRSCREEN_MSG_PC_OFFSET,
    FRSCREEN_MSG_RESOURCE_OFFSET,
    FRSCREEN_MSG_STATE_OFFSET,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_BOMB_INDEX_OFFSET,
    PLAYER_BOMB_LOCKOUT_OFFSET,
    PLAYER_BOMB_TIMER_OFFSET,
    PLAYER_FOCUS_LOGIC_OFFSET,
    PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET,
    PLAYER_POSITION_OFFSET,
    PLAYER_PREDEATH_COUNTER_OFFSET,
    PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET,
    PLAYER_VELOCITY_OFFSET,
    RUN_STATE_BOMBS_OFFSET,
    RUN_STATE_LIVES_OFFSET,
    RUN_STATE_POWER_OFFSET,
    SPELL_STATE_ACTIVE_FLAG,
    SPELL_STATE_CAPTURE_SIZE,
    SPELL_STATE_PREFIX_SIZE,
    SPELL_STATE_TIMER_ELAPSED_OFFSET,
)


class StateReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...

    def u8(self, address: int) -> int: ...

    def u16(self, address: int) -> int: ...

    def u32(self, address: int) -> int: ...

    def i32(self, address: int) -> int: ...

    def f32(self, address: int) -> float: ...


_PLAYER_CONTROL_INPUT_CAPTURE_SIZE = (
    ADDR_PREVIOUS_INPUT + 2 - ADDR_RAW_INPUT
)
# Source: Player::FUN_0044a230 / Player::CalcLaserHitbox and the cached AABB
# update in Player.cpp.  One contiguous read now retains the already-read
# position plus the native lethal AABB and half-extents without adding RPM
# calls to the seven-call player-control-root transaction.
PLAYER_LETHAL_AABB_OFFSET = 0x038C
PLAYER_LETHAL_HALF_EXTENTS_OFFSET = 0x03D4
PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE = (
    PLAYER_LETHAL_HALF_EXTENTS_OFFSET + 8 - PLAYER_POSITION_OFFSET
)
_PLAYER_CONTROL_AABB_CAPTURE_OFFSET = (
    PLAYER_LETHAL_AABB_OFFSET - PLAYER_POSITION_OFFSET
)
_PLAYER_CONTROL_HALF_EXTENTS_CAPTURE_OFFSET = (
    PLAYER_LETHAL_HALF_EXTENTS_OFFSET - PLAYER_POSITION_OFFSET
)


def _decode_player_control_inputs(blob: bytes) -> tuple[int, int, int]:
    if len(blob) != _PLAYER_CONTROL_INPUT_CAPTURE_SIZE:
        raise ValueError(
            "player control input capture requires exactly "
            f"{_PLAYER_CONTROL_INPUT_CAPTURE_SIZE} bytes"
        )
    return (
        struct.unpack_from("<H", blob, 0)[0],
        struct.unpack_from("<H", blob, ADDR_CURRENT_INPUT - ADDR_RAW_INPUT)[0],
        struct.unpack_from("<H", blob, ADDR_PREVIOUS_INPUT - ADDR_RAW_INPUT)[0],
    )


def _decode_player_control_geometry(
    blob: bytes,
) -> tuple[float, float, float, float, float, float, float, float]:
    if len(blob) != PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE:
        raise ValueError(
            "player control geometry capture requires exactly "
            f"{PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE} bytes"
        )
    x, y = struct.unpack_from("<ff", blob, 0)
    lethal_left, lethal_top = struct.unpack_from(
        "<ff",
        blob,
        _PLAYER_CONTROL_AABB_CAPTURE_OFFSET,
    )
    lethal_right, lethal_bottom = struct.unpack_from(
        "<ff",
        blob,
        _PLAYER_CONTROL_AABB_CAPTURE_OFFSET + 0x0C,
    )
    lethal_half_width, lethal_half_height = struct.unpack_from(
        "<ff",
        blob,
        _PLAYER_CONTROL_HALF_EXTENTS_CAPTURE_OFFSET,
    )
    return (
        x,
        y,
        lethal_left,
        lethal_top,
        lethal_right,
        lethal_bottom,
        lethal_half_width,
        lethal_half_height,
    )


@dataclass(frozen=True)
class TimeScaleRootCapture:
    """One scale dword bracketed by the native enemy-manager frame."""

    frame_before: int
    scale_bits: int
    frame_after: int

    @property
    def stable(self) -> bool:
        return self.frame_before == self.frame_after


def capture_time_scale_root(reader: StateReader) -> TimeScaleRootCapture:
    """Bind a raw global-scale observation to one stable manager frame."""

    return TimeScaleRootCapture(
        frame_before=reader.u32(ADDR_ENEMY_MANAGER_FRAME),
        scale_bits=reader.u32(ADDR_GAMEPLAY_TIME_SCALE),
        frame_after=reader.u32(ADDR_ENEMY_MANAGER_FRAME),
    )


@dataclass(frozen=True)
class PlayerControlRootCapture:
    """Player position/input/scale held constant inside one frame bracket."""

    frame_before: int
    frame_after: int
    x_before: float
    y_before: float
    x_after: float
    y_after: float
    lethal_aabb_before: tuple[float, float, float, float]
    lethal_aabb_after: tuple[float, float, float, float]
    lethal_half_extents_before: tuple[float, float]
    lethal_half_extents_after: tuple[float, float]
    input_raw_before: int
    input_current_before: int
    input_previous_before: int
    input_raw_after: int
    input_current_after: int
    input_previous_after: int
    scale_bits: int
    attempts: int

    @property
    def stable(self) -> bool:
        return bool(
            self.frame_before == self.frame_after
            and self.x_before == self.x_after
            and self.y_before == self.y_after
            and self.input_raw_before == self.input_raw_after
            and self.input_current_before == self.input_current_after
            and self.input_previous_before == self.input_previous_after
        )

    @property
    def x(self) -> float:
        return self.x_after

    @property
    def y(self) -> float:
        return self.y_after

    @property
    def input_raw(self) -> int:
        return self.input_raw_after

    @property
    def input_current(self) -> int:
        return self.input_current_after

    @property
    def input_previous(self) -> int:
        return self.input_previous_after

    @property
    def collision_geometry_stable(self) -> bool:
        """Whether the new shadow-only collision fields agree across reads."""

        return bool(
            self.lethal_aabb_before == self.lethal_aabb_after
            and self.lethal_half_extents_before
            == self.lethal_half_extents_after
        )

    @property
    def lethal_aabb(self) -> tuple[float, float, float, float]:
        return self.lethal_aabb_after

    @property
    def lethal_half_extents(self) -> tuple[float, float]:
        return self.lethal_half_extents_after


def capture_player_control_root(
    reader: StateReader,
    *,
    maximum_attempts: int = 2,
) -> PlayerControlRootCapture:
    """Capture a current player root without assuming the manager clock moves.

    The duplicate position and input reads are required because held input may
    continue moving the player while ``enemy_manager_frame`` is frozen.
    """

    if maximum_attempts <= 0:
        raise ValueError("player control-root attempts must be positive")
    capture = None
    for attempt in range(1, maximum_attempts + 1):
        frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        (
            input_raw_before,
            input_current_before,
            input_previous_before,
        ) = _decode_player_control_inputs(
            reader.read(ADDR_RAW_INPUT, _PLAYER_CONTROL_INPUT_CAPTURE_SIZE)
        )
        (
            x_before,
            y_before,
            lethal_left_before,
            lethal_top_before,
            lethal_right_before,
            lethal_bottom_before,
            lethal_half_width_before,
            lethal_half_height_before,
        ) = _decode_player_control_geometry(
            reader.read(
                ADDR_PLAYER + PLAYER_POSITION_OFFSET,
                PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE,
            )
        )
        scale_bits = reader.u32(ADDR_GAMEPLAY_TIME_SCALE)
        (
            x_after,
            y_after,
            lethal_left_after,
            lethal_top_after,
            lethal_right_after,
            lethal_bottom_after,
            lethal_half_width_after,
            lethal_half_height_after,
        ) = _decode_player_control_geometry(
            reader.read(
                ADDR_PLAYER + PLAYER_POSITION_OFFSET,
                PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE,
            )
        )
        (
            input_raw_after,
            input_current_after,
            input_previous_after,
        ) = _decode_player_control_inputs(
            reader.read(ADDR_RAW_INPUT, _PLAYER_CONTROL_INPUT_CAPTURE_SIZE)
        )
        frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        capture = PlayerControlRootCapture(
            frame_before=frame_before,
            frame_after=frame_after,
            x_before=x_before,
            y_before=y_before,
            x_after=x_after,
            y_after=y_after,
            lethal_aabb_before=(
                lethal_left_before,
                lethal_top_before,
                lethal_right_before,
                lethal_bottom_before,
            ),
            lethal_aabb_after=(
                lethal_left_after,
                lethal_top_after,
                lethal_right_after,
                lethal_bottom_after,
            ),
            lethal_half_extents_before=(
                lethal_half_width_before,
                lethal_half_height_before,
            ),
            lethal_half_extents_after=(
                lethal_half_width_after,
                lethal_half_height_after,
            ),
            input_raw_before=input_raw_before,
            input_current_before=input_current_before,
            input_previous_before=input_previous_before,
            input_raw_after=input_raw_after,
            input_current_after=input_current_after,
            input_previous_after=input_previous_after,
            scale_bits=scale_bits,
            attempts=attempt,
        )
        if capture.stable:
            return capture
    assert capture is not None
    return capture


def decode_spell_state(blob: bytes) -> dict[str, object]:
    if len(blob) < SPELL_STATE_PREFIX_SIZE:
        raise ValueError(
            f"spell state prefix requires {SPELL_STATE_PREFIX_SIZE} bytes"
        )
    flags, enemy_pointer, spell_id = struct.unpack_from("<III", blob)
    encoded_name = blob[20:68].split(b"\0", 1)[0]
    return {
        "active": bool(flags & SPELL_STATE_ACTIVE_FLAG),
        "flags": flags,
        "enemy_pointer": enemy_pointer,
        "spell_id": spell_id,
        "name": encoded_name.decode("shift_jis", errors="replace"),
        "timer_elapsed": (
            struct.unpack_from("<i", blob, SPELL_STATE_TIMER_ELAPSED_OFFSET)[0]
            if len(blob) >= SPELL_STATE_CAPTURE_SIZE
            else None
        ),
    }


def frscreen_blocks_enemy_clock(
    impl_pointer: int,
    msg_state: int | None,
) -> bool:
    """Mirror the shipped predicate at 0x4358BB."""

    return bool(
        impl_pointer
        and msg_state is not None
        and (msg_state >= 0 or msg_state == -2)
    )


def capture_input_clock_shadow(reader: StateReader) -> dict[str, object]:
    """Capture a read-only interval around the native FRScreen clock gate."""

    monotonic_start_ns = time.perf_counter_ns()
    wall_time_ns = time.time_ns()
    try:
        manager_frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        update_serial_before = reader.u32(ADDR_FRSCREEN_UPDATE_SERIAL)
        impl_pointer_before = reader.u32(ADDR_FRSCREEN_IMPL_POINTER)
        engine_flags_before = reader.u32(ADDR_ENGINE_FLAGS)
        scripted_freeze_before = reader.u8(ADDR_SCRIPTED_UPDATE_FREEZE)
        msg_resource_before = (
            reader.u32(impl_pointer_before + FRSCREEN_MSG_RESOURCE_OFFSET)
            if impl_pointer_before
            else None
        )
        msg_pc_before = (
            reader.u32(impl_pointer_before + FRSCREEN_MSG_PC_OFFSET)
            if impl_pointer_before
            else None
        )
        msg_state_before = (
            reader.i32(impl_pointer_before + FRSCREEN_MSG_STATE_OFFSET)
            if impl_pointer_before
            else None
        )
        input_before = {
            "raw": reader.u16(ADDR_RAW_INPUT),
            "current": reader.u16(ADDR_CURRENT_INPUT),
            "previous": reader.u16(ADDR_PREVIOUS_INPUT),
        }
        player_before = {
            "phase": reader.u8(ADDR_PLAYER),
            "x": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET),
            "y": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET + 4),
            "dx": reader.f32(ADDR_PLAYER + PLAYER_VELOCITY_OFFSET),
            "dy": reader.f32(ADDR_PLAYER + PLAYER_VELOCITY_OFFSET + 4),
        }

        player_after = {
            "phase": reader.u8(ADDR_PLAYER),
            "x": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET),
            "y": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET + 4),
            "dx": reader.f32(ADDR_PLAYER + PLAYER_VELOCITY_OFFSET),
            "dy": reader.f32(ADDR_PLAYER + PLAYER_VELOCITY_OFFSET + 4),
        }
        input_after = {
            "raw": reader.u16(ADDR_RAW_INPUT),
            "current": reader.u16(ADDR_CURRENT_INPUT),
            "previous": reader.u16(ADDR_PREVIOUS_INPUT),
        }
        impl_pointer_after = reader.u32(ADDR_FRSCREEN_IMPL_POINTER)
        msg_resource_after = (
            reader.u32(impl_pointer_after + FRSCREEN_MSG_RESOURCE_OFFSET)
            if impl_pointer_after
            else None
        )
        msg_pc_after = (
            reader.u32(impl_pointer_after + FRSCREEN_MSG_PC_OFFSET)
            if impl_pointer_after
            else None
        )
        msg_state_after = (
            reader.i32(impl_pointer_after + FRSCREEN_MSG_STATE_OFFSET)
            if impl_pointer_after
            else None
        )
        scripted_freeze_after = reader.u8(ADDR_SCRIPTED_UPDATE_FREEZE)
        engine_flags_after = reader.u32(ADDR_ENGINE_FLAGS)
        update_serial_after = reader.u32(ADDR_FRSCREEN_UPDATE_SERIAL)
        manager_frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
    except (OSError, RuntimeError, struct.error, ValueError) as error:
        monotonic_end_ns = time.perf_counter_ns()
        return {
            "read_valid": False,
            "error": f"{type(error).__name__}: {error}",
            "wall_time_ns": wall_time_ns,
            "monotonic_start_ns": monotonic_start_ns,
            "monotonic_end_ns": monotonic_end_ns,
            "capture_us": (monotonic_end_ns - monotonic_start_ns) / 1000.0,
            "dialogue_active": None,
            "frscreen_special_pause": None,
            "native_manager_clock_blocked": None,
        }

    monotonic_end_ns = time.perf_counter_ns()
    message_available = bool(
        impl_pointer_before
        and impl_pointer_after
        and msg_state_before is not None
        and msg_state_after is not None
    )
    message_snapshot_stable = bool(
        message_available
        and impl_pointer_before == impl_pointer_after
        and msg_state_before == msg_state_after
    )
    stable_msg_state = msg_state_after if message_snapshot_stable else None
    native_manager_clock_blocked = (
        frscreen_blocks_enemy_clock(impl_pointer_after, stable_msg_state)
        if message_snapshot_stable
        else None
    )
    return {
        "read_valid": True,
        "error": None,
        "wall_time_ns": wall_time_ns,
        "monotonic_start_ns": monotonic_start_ns,
        "monotonic_end_ns": monotonic_end_ns,
        "capture_us": (monotonic_end_ns - monotonic_start_ns) / 1000.0,
        "manager_frame_before": manager_frame_before,
        "manager_frame_after": manager_frame_after,
        "manager_frame_stable": manager_frame_before == manager_frame_after,
        "frscreen_update_serial_before": update_serial_before,
        "frscreen_update_serial_after": update_serial_after,
        "frscreen_update_serial_delta": (
            update_serial_after - update_serial_before
        )
        & 0xFFFFFFFF,
        "frscreen_impl_pointer_before": impl_pointer_before,
        "frscreen_impl_pointer_after": impl_pointer_after,
        "msg_resource_before": msg_resource_before,
        "msg_resource_after": msg_resource_after,
        "msg_pc_before": msg_pc_before,
        "msg_pc_after": msg_pc_after,
        "msg_state_before": msg_state_before,
        "msg_state_after": msg_state_after,
        "message_available": message_available,
        "message_snapshot_stable": message_snapshot_stable,
        "dialogue_active": (
            stable_msg_state >= 0 if stable_msg_state is not None else None
        ),
        "frscreen_special_pause": (
            stable_msg_state == -2 if stable_msg_state is not None else None
        ),
        "native_manager_clock_blocked": native_manager_clock_blocked,
        "scripted_update_freeze_before": scripted_freeze_before,
        "scripted_update_freeze_after": scripted_freeze_after,
        "engine_flags_before": engine_flags_before,
        "engine_flags_after": engine_flags_after,
        "engine_flags_stable": engine_flags_before == engine_flags_after,
        "input_before": input_before,
        "input_after": input_after,
        "input_stable": input_before == input_after,
        "player_before": player_before,
        "player_after": player_after,
    }


def observe_state(reader: StateReader) -> dict[str, object]:
    engine_flags = reader.u32(ADDR_ENGINE_FLAGS)
    inner = reader.u32(ADDR_RUN_STATE_INNER_POINTER)
    resources = None
    if inner and engine_flags & 0x04:
        resources = {
            "lives": reader.f32(inner + RUN_STATE_LIVES_OFFSET),
            "bombs": reader.f32(inner + RUN_STATE_BOMBS_OFFSET),
            "power": reader.f32(inner + RUN_STATE_POWER_OFFSET),
        }
    return {
        "wall_time_ns": time.time_ns(),
        "enemy_manager_frame": reader.u32(ADDR_ENEMY_MANAGER_FRAME),
        "time_scale_bits": reader.u32(ADDR_GAMEPLAY_TIME_SCALE),
        "engine_flags": engine_flags,
        "gameplay_active": bool(engine_flags & 0x04),
        "route_id": reader.u8(ADDR_ROUTE_ID),
        "stage_route_index": reader.u32(ADDR_STAGE_ROUTE_INDEX),
        "difficulty_index": reader.u32(ADDR_DIFFICULTY_INDEX),
        "input_raw": reader.u16(ADDR_RAW_INPUT),
        "input_current": reader.u16(ADDR_CURRENT_INPUT),
        "input_previous": reader.u16(ADDR_PREVIOUS_INPUT),
        "rng_state": reader.u16(ADDR_GAMEPLAY_RNG),
        "rng_calls": reader.u32(ADDR_GAMEPLAY_RNG + 4),
        "spell": decode_spell_state(
            reader.read(ADDR_SPELL_CARD_STATE, SPELL_STATE_CAPTURE_SIZE)
        ),
        "player": {
            "phase": reader.u8(ADDR_PLAYER),
            "focus_logic": reader.u8(
                ADDR_PLAYER + PLAYER_FOCUS_LOGIC_OFFSET
            ),
            "deathbomb": reader.u8(ADDR_PLAYER + 4),
            "secondary_character_active": bool(
                reader.u8(
                    ADDR_PLAYER
                    + PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET
                )
                & 1
            ),
            "forced_bomb": reader.u8(ADDR_PLAYER + 6),
            "focus_transition_counter": reader.i32(
                ADDR_PLAYER + PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET
            ),
            "x": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET),
            "y": reader.f32(ADDR_PLAYER + PLAYER_POSITION_OFFSET + 4),
            "bomb_active": reader.u32(
                ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET
            ),
            "bomb_index": reader.i32(ADDR_PLAYER + PLAYER_BOMB_INDEX_OFFSET),
            "bomb_timer": reader.i32(ADDR_PLAYER + PLAYER_BOMB_TIMER_OFFSET),
            "predeath_counter": reader.i32(
                ADDR_PLAYER + PLAYER_PREDEATH_COUNTER_OFFSET
            ),
            "bomb_lockout": reader.i32(
                ADDR_PLAYER + PLAYER_BOMB_LOCKOUT_OFFSET
            ),
        },
        "resources": resources,
    }
