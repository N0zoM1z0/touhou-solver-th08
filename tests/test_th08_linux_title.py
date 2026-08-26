from __future__ import annotations

import struct
import unittest

from th08_linux.protocol import BOMB, DOWN, RIGHT, SHOOT, UP
from th08_linux.title import (
    ADDR_GAME_MANAGER_CALC_CALLBACK,
    ADDR_GAME_MANAGER_LOADING_STATE,
    ADDR_TITLE_SCREEN_POINTER,
    EASY_DIFFICULTY,
    RouteTitleDriver,
    SAKUYA_REMILIA_SHOT_TYPE,
    TITLE_CAPTURE_SIZE,
    TITLE_CURRENT_SCREEN_OFFSET,
    TITLE_CURRENT_SCREEN_STATE_OFFSET,
    TITLE_CURRENT_STATE_READY,
    TITLE_CURSOR_OFFSET,
    TITLE_IDLE_FRAMES_OFFSET,
    TITLE_LIFECYCLE_READY,
    TITLE_PREVIOUS_SCREEN_OFFSET,
    TITLE_SCREEN_CHARACTER,
    TITLE_SCREEN_DIFFICULTY,
    TITLE_SCREEN_START,
    TITLE_START_MENU_IDLE_FRAMES_OFFSET,
    TITLE_STATE_OFFSET,
    TITLE_STATE_TIMER2_OFFSET,
    TITLE_STATE_TIMER_OFFSET,
    TitleSnapshot,
    capture_gameplay_bootstrap,
    capture_title_snapshot,
)
from th08_runtime.game_state import (
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENGINE_FLAGS,
    ADDR_ROUTE_ID,
    ADDR_STAGE_ROUTE_INDEX,
)


def _snapshot(
    *,
    screen: int,
    cursor: int,
    screen_state: int = TITLE_CURRENT_STATE_READY,
    state_timer2: int = 10,
    flags: int = 0,
) -> TitleSnapshot:
    return TitleSnapshot(
        pointer=0x20000000,
        cursor=cursor,
        current_screen_state=screen_state,
        state_timer=0,
        previous_screen=screen,
        idle_frames=0,
        current_screen=screen,
        state_timer2=state_timer2,
        start_menu_idle_frames=0,
        lifecycle_state=TITLE_LIFECYCLE_READY,
        game_manager_flags=flags,
    )


class _MemoryReader:
    def __init__(self) -> None:
        self.bytes: dict[int, int] = {}

    def put(self, address: int, data: bytes) -> None:
        for index, value in enumerate(data):
            self.bytes[address + index] = value

    def put_u32(self, address: int, value: int) -> None:
        self.put(address, struct.pack("<I", value))

    def read(self, address: int, size: int) -> bytes:
        return bytes(self.bytes.get(address + index, 0) for index in range(size))

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]


class LinuxTitleCaptureTests(unittest.TestCase):
    def test_decodes_source_and_debugger_confirmed_offsets(self) -> None:
        reader = _MemoryReader()
        pointer = 0x20000000
        blob = bytearray(TITLE_CAPTURE_SIZE)
        values = {
            TITLE_CURSOR_OFFSET: 2,
            TITLE_CURRENT_SCREEN_STATE_OFFSET: 1,
            TITLE_STATE_TIMER_OFFSET: 17,
            TITLE_PREVIOUS_SCREEN_OFFSET: 4,
            TITLE_IDLE_FRAMES_OFFSET: 23,
            TITLE_CURRENT_SCREEN_OFFSET: 5,
            TITLE_STATE_TIMER2_OFFSET: 11,
            TITLE_START_MENU_IDLE_FRAMES_OFFSET: 29,
            TITLE_STATE_OFFSET: 0,
        }
        for offset, value in values.items():
            struct.pack_into("<i", blob, offset, value)
        reader.put_u32(ADDR_TITLE_SCREEN_POINTER, pointer)
        reader.put(pointer, blob)
        reader.put_u32(ADDR_ENGINE_FLAGS, 1 << 17)

        snapshot = capture_title_snapshot(reader)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.cursor, 2)
        self.assertEqual(snapshot.current_screen, 5)
        self.assertEqual(snapshot.state_timer2, 11)
        self.assertEqual(snapshot.character_menu_length, 12)

    def test_absent_title_root_is_not_dereferenced(self) -> None:
        self.assertIsNone(capture_title_snapshot(_MemoryReader()))

    def test_gameplay_ready_requires_registered_chain_and_finished_load(self) -> None:
        reader = _MemoryReader()
        reader.put_u32(ADDR_GAME_MANAGER_CALC_CALLBACK, 0x00439BF0)
        reader.put_u32(ADDR_GAME_MANAGER_LOADING_STATE, 0)
        reader.put_u32(ADDR_DIFFICULTY_INDEX, EASY_DIFFICULTY)
        reader.put_u32(ADDR_ROUTE_ID, SAKUYA_REMILIA_SHOT_TYPE)
        reader.put_u32(ADDR_STAGE_ROUTE_INDEX, 0)

        snapshot = capture_gameplay_bootstrap(reader)

        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.difficulty_index, EASY_DIFFICULTY)
        self.assertEqual(snapshot.shot_type_index, SAKUYA_REMILIA_SHOT_TYPE)


class LinuxRouteTitleDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = RouteTitleDriver(
            difficulty_index=EASY_DIFFICULTY,
            shot_type_index=SAKUYA_REMILIA_SHOT_TYPE,
        )

    def test_start_confirm_honors_source_ten_tick_gate_and_edge_release(self) -> None:
        waiting = self.driver.decide(
            _snapshot(screen=TITLE_SCREEN_START, cursor=0, state_timer2=9),
            current_input=0,
        )
        pressed = self.driver.decide(
            _snapshot(screen=TITLE_SCREEN_START, cursor=0, state_timer2=10),
            current_input=0,
        )
        released = self.driver.decide(
            _snapshot(screen=TITLE_SCREEN_DIFFICULTY, cursor=0),
            current_input=SHOOT,
        )

        self.assertEqual(waiting.input_mask, 0)
        self.assertEqual(pressed.input_mask, SHOOT)
        self.assertEqual(released.input_mask, 0)

    def test_observed_cursor_feedback_drives_all_three_menus(self) -> None:
        self.assertEqual(
            self.driver.decide(
                _snapshot(screen=TITLE_SCREEN_START, cursor=8),
                current_input=0,
            ).input_mask,
            DOWN,
        )
        self.assertEqual(
            self.driver.decide(
                _snapshot(screen=TITLE_SCREEN_DIFFICULTY, cursor=1),
                current_input=0,
            ).input_mask,
            UP,
        )
        self.assertEqual(
            self.driver.decide(
                _snapshot(screen=TITLE_SCREEN_CHARACTER, cursor=0),
                current_input=0,
            ).input_mask,
            RIGHT,
        )
        self.assertEqual(
            self.driver.decide(
                _snapshot(screen=TITLE_SCREEN_CHARACTER, cursor=2),
                current_input=0,
            ).input_mask,
            SHOOT,
        )

    def test_no_decision_can_emit_bomb(self) -> None:
        cases = (
            _snapshot(screen=TITLE_SCREEN_START, cursor=0),
            _snapshot(screen=TITLE_SCREEN_DIFFICULTY, cursor=3),
            _snapshot(screen=TITLE_SCREEN_CHARACTER, cursor=1),
        )
        for snapshot in cases:
            with self.subTest(screen=snapshot.current_screen):
                decision = self.driver.decide(snapshot, current_input=0)
                self.assertEqual(decision.input_mask & BOMB, 0)

    def test_unexpected_route_screen_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unexpected title screen"):
            self.driver.decide(_snapshot(screen=7, cursor=0), current_input=0)


if __name__ == "__main__":
    unittest.main()
