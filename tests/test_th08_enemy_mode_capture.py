#!/usr/bin/env python3
"""Tests for the frame-bracketed player/enemy mode observation."""

from __future__ import annotations

import struct
import unittest

from th08_live.enemy_mode_capture import (
    PlayerModeObservation,
    capture_player_enemy_mode_prefix,
)
from th08_live.enemy_sensor import (
    ENEMY_CONTACT_SIZE_OFFSET,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_POSITION_OFFSET,
    ENEMY_STRIDE,
)
from th08_runtime.game_state import (
    ADDR_CURRENT_INPUT,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_PLAYER,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_BOMB_INDEX_OFFSET,
    PLAYER_FOCUS_LOGIC_OFFSET,
    PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET,
    PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET,
)


def _player_prefix(
    *,
    focus_logic: int,
    secondary_active: bool,
    counter: int,
) -> bytes:
    blob = bytearray(12)
    blob[0] = 0
    blob[PLAYER_FOCUS_LOGIC_OFFSET] = focus_logic
    blob[PLAYER_SECONDARY_CHARACTER_ACTIVE_OFFSET] = int(
        secondary_active
    )
    struct.pack_into(
        "<i",
        blob,
        PLAYER_FOCUS_TRANSITION_COUNTER_OFFSET,
        counter,
    )
    return bytes(blob)


def _enemy_blob(flags: int) -> bytes:
    blob = bytearray(ENEMY_STRIDE)
    struct.pack_into(
        "<ff",
        blob,
        ENEMY_CONTACT_SIZE_OFFSET,
        24.0,
        24.0,
    )
    struct.pack_into(
        "<ff",
        blob,
        ENEMY_POSITION_OFFSET,
        192.0,
        300.0,
    )
    struct.pack_into("<I", blob, ENEMY_FLAGS_OFFSET, flags)
    return bytes(blob)


class _Reader:
    def __init__(
        self,
        *,
        player_prefixes: list[bytes],
        enemy_blobs: list[bytes],
        frames: list[int],
        inputs: list[int] | None = None,
        bomb_active: int = 0,
        bomb_index: int = 0,
    ) -> None:
        self.player_prefixes = player_prefixes
        self.enemy_blobs = enemy_blobs
        self.frames = frames
        self.inputs = inputs or [0] * len(player_prefixes)
        self.bomb_active = bomb_active
        self.bomb_index = bomb_index
        self.read_into_destinations: list[int] = []

    def read(self, address: int, _size: int) -> bytes:
        if address == ADDR_PLAYER:
            return self.player_prefixes.pop(0)
        if address == ENEMY_POOL_BASE:
            return self.enemy_blobs.pop(0)
        raise AssertionError(f"unexpected read at {address:#x}")

    def read_into(self, address: int, destination: bytearray) -> bytearray:
        self.read_into_destinations.append(id(destination))
        destination[:] = self.read(address, len(destination))
        return destination

    def u16(self, address: int) -> int:
        if address != ADDR_CURRENT_INPUT:
            raise AssertionError(f"unexpected u16 at {address:#x}")
        return self.inputs.pop(0)

    def u32(self, address: int) -> int:
        if address == ADDR_ENEMY_MANAGER_FRAME:
            return self.frames.pop(0)
        if address == ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET:
            return self.bomb_active
        raise AssertionError(f"unexpected u32 at {address:#x}")

    def i32(self, address: int) -> int:
        if address != ADDR_PLAYER + PLAYER_BOMB_INDEX_OFFSET:
            raise AssertionError(f"unexpected i32 at {address:#x}")
        return self.bomb_index


class EnemyModeCaptureTests(unittest.TestCase):
    def test_coherent_capture_forwards_persistent_pool_destination(self) -> None:
        prefix = _player_prefix(
            focus_logic=0,
            secondary_active=False,
            counter=7,
        )
        reader = _Reader(
            player_prefixes=[prefix, prefix],
            enemy_blobs=[_enemy_blob(0x0100114D)],
            frames=[10075, 10075],
        )
        destination = bytearray(ENEMY_STRIDE)

        capture = capture_player_enemy_mode_prefix(
            reader,
            pool_size=1,
            pool_buffer=destination,
        )

        self.assertTrue(capture.coherent)
        self.assertEqual(reader.read_into_destinations, [id(destination)])
        self.assertEqual(capture.enemy_snapshot.bodies[0].flags, 0x0100114D)

    def test_coherent_capture_retains_mode_root_and_raw_body(self) -> None:
        prefix = _player_prefix(
            focus_logic=0,
            secondary_active=False,
            counter=7,
        )
        capture = capture_player_enemy_mode_prefix(
            _Reader(
                player_prefixes=[prefix, prefix],
                enemy_blobs=[_enemy_blob(0x0100114D)],
                frames=[10075, 10075],
            ),
            pool_size=1,
        )
        self.assertTrue(capture.coherent)
        self.assertEqual(capture.status, "coherent")
        self.assertEqual(capture.attempts, 1)
        self.assertEqual(
            capture.player_after.mode_key,
            (0, False, 7),
        )
        self.assertEqual(capture.enemy_snapshot.bodies[0].flags, 0x0100114D)
        self.assertEqual(capture.sync_mismatch_pointers, ())
        compact = capture.compact_record()
        self.assertEqual(compact["mode_sensitive_body_count"], 1)
        self.assertEqual(
            compact["mode_sensitive_bodies"],
            [[ENEMY_POOL_BASE, 0x0100114D]],
        )
        self.assertFalse(compact["action_authority"])

    def test_enemy_sync_mismatch_retries_until_flags_match_player(self) -> None:
        prefix = _player_prefix(
            focus_logic=1,
            secondary_active=True,
            counter=7,
        )
        capture = capture_player_enemy_mode_prefix(
            _Reader(
                player_prefixes=[prefix, prefix, prefix, prefix],
                enemy_blobs=[
                    _enemy_blob(0x0100114D),
                    _enemy_blob(0x0100194D),
                ],
                frames=[10, 10, 11, 11],
            ),
            pool_size=1,
        )
        self.assertTrue(capture.coherent)
        self.assertEqual(capture.attempts, 2)
        self.assertEqual(capture.enemy_snapshot.attempts, 2)
        self.assertEqual(capture.enemy_snapshot.bodies[0].flags, 0x0100194D)

    def test_crossed_player_transition_retries_complete_transaction(self) -> None:
        before = _player_prefix(
            focus_logic=0,
            secondary_active=True,
            counter=6,
        )
        after = _player_prefix(
            focus_logic=0,
            secondary_active=False,
            counter=7,
        )
        capture = capture_player_enemy_mode_prefix(
            _Reader(
                player_prefixes=[before, after, after, after],
                enemy_blobs=[
                    _enemy_blob(0x0100194D),
                    _enemy_blob(0x0100114D),
                ],
                frames=[20, 20, 21, 21],
            ),
            pool_size=1,
        )
        self.assertTrue(capture.coherent)
        self.assertEqual(capture.attempts, 2)
        self.assertEqual(capture.player_before, capture.player_after)
        self.assertEqual(capture.player_after.mode_key, (0, False, 7))

    def test_exhausted_crossed_frames_remain_explicitly_unstable(self) -> None:
        prefix = _player_prefix(
            focus_logic=0,
            secondary_active=False,
            counter=7,
        )
        capture = capture_player_enemy_mode_prefix(
            _Reader(
                player_prefixes=[prefix, prefix, prefix, prefix],
                enemy_blobs=[
                    _enemy_blob(0x0100114D),
                    _enemy_blob(0x0100114D),
                ],
                frames=[30, 31, 32, 33],
            ),
            pool_size=1,
        )
        self.assertFalse(capture.coherent)
        self.assertEqual(capture.status, "enemy_frame_unstable")
        self.assertEqual(capture.attempts, 2)

    def test_bomb_callback_parity_overrides_input_focus(self) -> None:
        observation = PlayerModeObservation(
            input_current=0x04,
            phase=0,
            focus_logic_value=1,
            secondary_character_raw=1,
            transition_counter=7,
            bomb_active=1,
            bomb_callback_index=2,
        )
        self.assertFalse(observation.effective_focus)


if __name__ == "__main__":
    unittest.main()
