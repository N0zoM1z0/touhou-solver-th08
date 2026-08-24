"""Frame-bracketed TH08 player-mode and enemy-prefix observation."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, replace
from typing import Protocol

from th08_enemy_mode import (
    ENEMY_SECONDARY_CHARACTER_BLOCK_FLAG,
    ENEMY_SECONDARY_CHARACTER_SYNC_FLAG,
)
from th08_live.enemy_sensor import (
    ENEMY_LOCAL_PREFIX_SIZE,
    ENEMY_POOL_SIZE,
    capture_enemy_pool_prefix_contiguous,
)
from th08_live.models import EnemyPoolSnapshot
from th08_runtime.game_state import (
    ADDR_CURRENT_INPUT,
    ADDR_PLAYER,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_BOMB_INDEX_OFFSET,
    PLAYER_FOCUS_LOGIC_OFFSET,
    PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET,
    PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET,
)

_PLAYER_MODE_PREFIX_SIZE = PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET + 4
_INPUT_FOCUS = 0x04


class EnemyModeCaptureReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...

    def read_into(self, address: int, destination: object) -> object: ...

    def u16(self, address: int) -> int: ...

    def u32(self, address: int) -> int: ...

    def i32(self, address: int) -> int: ...


@dataclass(frozen=True)
class PlayerModeObservation:
    """Native inputs and player fields needed by the route-2 mode recurrence."""

    input_current: int
    phase: int
    focus_logic_value: int
    secondary_character_raw: int
    transition_counter: int
    bomb_active: int
    bomb_callback_index: int

    @property
    def secondary_character_active(self) -> bool:
        return bool(self.secondary_character_raw & 1)

    @property
    def effective_focus(self) -> bool:
        if self.bomb_active:
            return bool(self.bomb_callback_index & 1)
        return bool(self.input_current & _INPUT_FOCUS)

    @property
    def mode_key(self) -> tuple[int, bool, int]:
        return (
            self.focus_logic_value,
            self.secondary_character_active,
            self.transition_counter,
        )

    def compact_record(self) -> dict[str, object]:
        return {
            "input_current": self.input_current,
            "phase": self.phase,
            "focus_logic": self.focus_logic_value,
            "secondary_character_raw": self.secondary_character_raw,
            "secondary_character_active": (
                self.secondary_character_active
            ),
            "focus_transition_counter": self.transition_counter,
            "bomb_active": self.bomb_active,
            "bomb_callback_index": self.bomb_callback_index,
            "effective_focus": self.effective_focus,
        }


@dataclass(frozen=True)
class PlayerEnemyModePrefixCapture:
    """One bounded player/input observation around one enemy-prefix capture."""

    player_before: PlayerModeObservation
    enemy_snapshot: EnemyPoolSnapshot
    player_after: PlayerModeObservation
    sync_mismatch_pointers: tuple[int, ...]
    attempts: int
    read_ms: float

    @property
    def player_stable(self) -> bool:
        return self.player_before == self.player_after

    @property
    def coherent(self) -> bool:
        return bool(
            self.enemy_snapshot.stable
            and self.player_stable
            and not self.sync_mismatch_pointers
        )

    @property
    def status(self) -> str:
        if not self.enemy_snapshot.stable:
            return "enemy_frame_unstable"
        if not self.player_stable:
            return "player_or_input_changed"
        if self.sync_mismatch_pointers:
            return "enemy_mode_sync_mismatch"
        return "coherent"

    def compact_record(self) -> dict[str, object]:
        mode_sensitive_bodies = [
            [body.pointer, body.flags]
            for body in self.enemy_snapshot.bodies
            if body.flags & ENEMY_SECONDARY_CHARACTER_SYNC_FLAG
        ]
        return {
            "role": "diagnostic_shadow",
            "status": self.status,
            "coherent": self.coherent,
            "attempts": self.attempts,
            "read_ms": self.read_ms,
            "enemy_frame_before": self.enemy_snapshot.frame_before,
            "enemy_frame_after": self.enemy_snapshot.frame_after,
            "enemy_body_count": len(self.enemy_snapshot.bodies),
            "mode_sensitive_body_count": len(mode_sensitive_bodies),
            "mode_sensitive_bodies": mode_sensitive_bodies,
            "player_before": self.player_before.compact_record(),
            "player_after": self.player_after.compact_record(),
            "sync_mismatch_pointers": list(
                self.sync_mismatch_pointers
            ),
            "action_authority": False,
        }


def _read_player_mode(
    reader: EnemyModeCaptureReader,
) -> PlayerModeObservation:
    input_current = reader.u16(ADDR_CURRENT_INPUT)
    prefix = reader.read(ADDR_PLAYER, _PLAYER_MODE_PREFIX_SIZE)
    if len(prefix) != _PLAYER_MODE_PREFIX_SIZE:
        raise OSError("short player-mode prefix read")
    bomb_active = reader.u32(ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET)
    bomb_callback_index = reader.i32(
        ADDR_PLAYER + PLAYER_BOMB_INDEX_OFFSET
    )
    return PlayerModeObservation(
        input_current=input_current,
        phase=prefix[0],
        focus_logic_value=prefix[PLAYER_FOCUS_LOGIC_OFFSET],
        secondary_character_raw=prefix[
            PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET
        ],
        transition_counter=struct.unpack_from(
            "<i",
            prefix,
            PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET,
        )[0],
        bomb_active=bomb_active,
        bomb_callback_index=bomb_callback_index,
    )


def _mode_sync_mismatches(
    snapshot: EnemyPoolSnapshot,
    *,
    secondary_character_active: bool,
) -> tuple[int, ...]:
    return tuple(
        body.pointer
        for body in snapshot.bodies
        if (
            body.flags & ENEMY_SECONDARY_CHARACTER_SYNC_FLAG
            and bool(
                body.flags & ENEMY_SECONDARY_CHARACTER_BLOCK_FLAG
            )
            != secondary_character_active
        )
    )


def capture_player_enemy_mode_prefix(
    reader: EnemyModeCaptureReader,
    *,
    pool_size: int = ENEMY_LOCAL_PREFIX_SIZE,
    maximum_attempts: int = 2,
    include_main_ecl_vms: bool = False,
    include_combat_progress: bool = False,
    pool_buffer: object | None = None,
) -> PlayerEnemyModePrefixCapture:
    """Capture a stable player/input root around the existing enemy prefix.

    A stable enemy-manager frame alone cannot rule out an interleaving between
    the priority-9 player update and priority-11 enemy mode sync.  This capture
    therefore requires equal input/player/Bomb observations on both sides and
    checks every retained mode-sensitive body against the delayed player byte.
    """

    if not 0 < pool_size <= ENEMY_POOL_SIZE:
        raise ValueError("enemy prefix size must belong to the native pool")
    if maximum_attempts <= 0:
        raise ValueError("enemy mode capture attempts must be positive")

    started = time.perf_counter()
    capture = None
    for attempt in range(1, maximum_attempts + 1):
        player_before = _read_player_mode(reader)
        enemy_snapshot = capture_enemy_pool_prefix_contiguous(
            reader,  # type: ignore[arg-type]
            pool_size=pool_size,
            maximum_attempts=1,
            include_main_ecl_vms=include_main_ecl_vms,
            include_combat_progress=include_combat_progress,
            pool_buffer=pool_buffer,
        )
        player_after = _read_player_mode(reader)
        mismatches = _mode_sync_mismatches(
            enemy_snapshot,
            secondary_character_active=(
                player_after.secondary_character_active
            ),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        enemy_snapshot = replace(
            enemy_snapshot,
            read_ms=elapsed_ms,
            attempts=attempt,
        )
        capture = PlayerEnemyModePrefixCapture(
            player_before=player_before,
            enemy_snapshot=enemy_snapshot,
            player_after=player_after,
            sync_mismatch_pointers=mismatches,
            attempts=attempt,
            read_ms=elapsed_ms,
        )
        if capture.coherent:
            return capture

    assert capture is not None
    return capture


__all__ = [
    "EnemyModeCaptureReader",
    "PlayerEnemyModePrefixCapture",
    "PlayerModeObservation",
    "capture_player_enemy_mode_prefix",
]
