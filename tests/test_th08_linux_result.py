from __future__ import annotations

import struct
import unittest

from th08_linux.protocol import DOWN, MENU, SHOOT
from th08_linux.result import (
    ADDR_CHAIN,
    ADDR_RETRY_MENU,
    ADDR_SHOW_RETRY_MENU,
    CHAIN_ARGUMENT_OFFSET,
    CHAIN_CALLBACK_OFFSET,
    CHAIN_ELEM_SIZE,
    CHAIN_NEXT_OFFSET,
    RESULT_CAPTURE_SIZE,
    RESULT_CURSOR_OFFSET,
    RESULT_FRAME_TIMER_OFFSET,
    RESULT_SELECTED_CHARACTER_OFFSET,
    RESULT_STATE_OFFSET,
    RESULT_SCREEN_STATE_CHOOSING_REPLAY_FILE,
    RESULT_SCREEN_STATE_STATS_SCREEN,
    RESULT_SCREEN_STATE_WRITING_HIGHSCORE_NAME,
    RESULT_SCREEN_STATE_WRITING_REPLAY_NAME,
    RETRY_MENU_STATE_NO_SELECTED,
    RETRY_MENU_STATE_YES_SELECTED,
    ReplaySaveDriver,
    ResultScreenSnapshot,
    RetryExitDriver,
    RetryMenuSnapshot,
    capture_result_screen,
    capture_retry_menu,
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

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]


def _result_snapshot(
    *,
    state: int,
    frame_timer: int,
    cursor: int = 0,
    selected_character: int = 0,
) -> ResultScreenSnapshot:
    return ResultScreenSnapshot(
        pointer=0x22000000,
        frame_timer=frame_timer,
        state=state,
        frame_timer2=0,
        cursor=cursor,
        selected_replay=0,
        selected_character=selected_character,
        last_name=b"",
    )


class LinuxResultCaptureTests(unittest.TestCase):
    def test_finds_result_argument_and_decodes_source_offsets(self) -> None:
        reader = _MemoryReader()
        callback = 0x080D776C
        element = 0x21000000
        result = 0x22000000
        chain_blob = bytearray(CHAIN_ELEM_SIZE)
        struct.pack_into("<I", chain_blob, CHAIN_CALLBACK_OFFSET, callback)
        struct.pack_into("<I", chain_blob, CHAIN_ARGUMENT_OFFSET, result)
        reader.put_u32(ADDR_CHAIN + CHAIN_NEXT_OFFSET, element)
        reader.put(element, chain_blob)
        result_blob = bytearray(RESULT_CAPTURE_SIZE)
        struct.pack_into("<i", result_blob, RESULT_FRAME_TIMER_OFFSET, 91)
        struct.pack_into(
            "<i", result_blob, RESULT_STATE_OFFSET, RESULT_SCREEN_STATE_STATS_SCREEN
        )
        struct.pack_into("<i", result_blob, RESULT_CURSOR_OFFSET, 2)
        struct.pack_into("<i", result_blob, RESULT_SELECTED_CHARACTER_OFFSET, 95)
        reader.put(result, result_blob)

        snapshot = capture_result_screen(reader, update_callback=callback)

        assert snapshot is not None
        self.assertEqual(snapshot.pointer, result)
        self.assertEqual(snapshot.frame_timer, 91)
        self.assertEqual(snapshot.state, RESULT_SCREEN_STATE_STATS_SCREEN)
        self.assertEqual(snapshot.cursor, 2)
        self.assertEqual(snapshot.selected_character, 95)

    def test_absent_callback_returns_none(self) -> None:
        self.assertIsNone(
            capture_result_screen(_MemoryReader(), update_callback=0x080D776C)
        )

    def test_decodes_retry_menu_fixed_member(self) -> None:
        reader = _MemoryReader()
        reader.put_u32(ADDR_RETRY_MENU, RETRY_MENU_STATE_NO_SELECTED)
        reader.put_u32(ADDR_RETRY_MENU + 4, 31)
        reader.put(ADDR_SHOW_RETRY_MENU, b"\x01")

        snapshot = capture_retry_menu(reader)

        self.assertTrue(snapshot.showing)
        self.assertEqual(snapshot.state, RETRY_MENU_STATE_NO_SELECTED)
        self.assertEqual(snapshot.frame_timer, 31)


class LinuxResultDriverTests(unittest.TestCase):
    def test_retry_driver_selects_no_and_confirms_after_source_gate(self) -> None:
        driver = RetryExitDriver()
        select_no = driver.decide(
            RetryMenuSnapshot(True, RETRY_MENU_STATE_YES_SELECTED, 4),
            current_input=0,
        )
        confirm = driver.decide(
            RetryMenuSnapshot(True, RETRY_MENU_STATE_NO_SELECTED, 30),
            current_input=0,
        )
        release = driver.decide(
            RetryMenuSnapshot(True, RETRY_MENU_STATE_NO_SELECTED, 31),
            current_input=SHOOT,
        )
        self.assertEqual(select_no.input_mask, DOWN)
        self.assertEqual(confirm.input_mask, SHOOT)
        self.assertEqual(release.input_mask, 0)

    def test_result_driver_honors_each_source_timer_gate(self) -> None:
        driver = ReplaySaveDriver(replay_slot=0)
        highscore_wait = driver.decide(
            _result_snapshot(
                state=RESULT_SCREEN_STATE_WRITING_HIGHSCORE_NAME,
                frame_timer=9,
            ),
            current_input=0,
        )
        highscore_skip = driver.decide(
            _result_snapshot(
                state=RESULT_SCREEN_STATE_WRITING_HIGHSCORE_NAME,
                frame_timer=10,
            ),
            current_input=0,
        )
        stats_wait = driver.decide(
            _result_snapshot(state=RESULT_SCREEN_STATE_STATS_SCREEN, frame_timer=89),
            current_input=0,
        )
        stats_confirm = driver.decide(
            _result_snapshot(state=RESULT_SCREEN_STATE_STATS_SCREEN, frame_timer=90),
            current_input=0,
        )
        self.assertEqual(highscore_wait.input_mask, 0)
        self.assertEqual(highscore_skip.input_mask, MENU)
        self.assertEqual(stats_wait.input_mask, 0)
        self.assertEqual(stats_confirm.input_mask, SHOOT)

    def test_result_driver_selects_slot_and_finishes_name(self) -> None:
        driver = ReplaySaveDriver(replay_slot=3)
        choose = driver.decide(
            _result_snapshot(
                state=RESULT_SCREEN_STATE_CHOOSING_REPLAY_FILE,
                frame_timer=20,
                cursor=0,
            ),
            current_input=0,
        )
        type_name = driver.decide(
            _result_snapshot(
                state=RESULT_SCREEN_STATE_WRITING_REPLAY_NAME,
                frame_timer=30,
                selected_character=0,
            ),
            current_input=0,
        )
        save = driver.decide(
            _result_snapshot(
                state=RESULT_SCREEN_STATE_WRITING_REPLAY_NAME,
                frame_timer=30,
                selected_character=95,
            ),
            current_input=0,
        )
        self.assertEqual(choose.input_mask, DOWN)
        self.assertEqual(type_name.action, "enter-replay-name-character")
        self.assertEqual(save.action, "save-replay")
        self.assertEqual(save.input_mask, SHOOT)


if __name__ == "__main__":
    unittest.main()
