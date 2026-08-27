"""Source-derived game-over and result-screen sensing for native TH08."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Protocol

from th08_linux.protocol import DOWN, LEFT, MENU, SHOOT, UP


class ResultStateReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...

    def u8(self, address: int) -> int: ...

    def u32(self, address: int) -> int: ...


# The modern linker retains these target-owned globals. The member offsets are
# from the authoritative source and the pinned i386 ELF's `gdb ptype /o`.
ADDR_CHAIN = 0x0164F548
CHAIN_ELEM_SIZE = 0x20
CHAIN_CALLBACK_OFFSET = 0x04
CHAIN_NEXT_OFFSET = 0x14
CHAIN_ARGUMENT_OFFSET = 0x1C

ADDR_ASCII_MANAGER = 0x004CCE20
ASCII_RETRY_MENU_OFFSET = 0x9FB4
ADDR_RETRY_MENU = ADDR_ASCII_MANAGER + ASCII_RETRY_MENU_OFFSET
ADDR_GAME_MANAGER = 0x0160F508
GAME_MANAGER_SHOW_RETRY_OFFSET = 0x3DBB3
ADDR_SHOW_RETRY_MENU = ADDR_GAME_MANAGER + GAME_MANAGER_SHOW_RETRY_OFFSET
ADDR_SUPERVISOR = 0x017CE758
SUPERVISOR_STATE_OFFSET = 0x15C
ADDR_SUPERVISOR_STATE = ADDR_SUPERVISOR + SUPERVISOR_STATE_OFFSET

RESULT_FRAME_TIMER_OFFSET = 0x04
RESULT_STATE_OFFSET = 0x08
RESULT_FRAME_TIMER2_OFFSET = 0x18
RESULT_CURSOR_OFFSET = 0x1C
RESULT_SELECTED_REPLAY_OFFSET = 0x28
RESULT_SELECTED_CHARACTER_OFFSET = 0x2C
RESULT_LAST_NAME_OFFSET = 0x58
RESULT_LAST_NAME_SIZE = 9
RESULT_CAPTURE_SIZE = RESULT_LAST_NAME_OFFSET + RESULT_LAST_NAME_SIZE

RETRY_MENU_STATE_INIT = 0
RETRY_MENU_STATE_YES_SELECTED = 1
RETRY_MENU_STATE_NO_SELECTED = 2
RETRY_MENU_STATE_RETRY = 3
RETRY_MENU_STATE_EXIT_TO_TITLE = 4

RESULT_SCREEN_STATE_EXITING = 2
RESULT_SCREEN_STATE_WRITING_HIGHSCORE_NAME = 9
RESULT_SCREEN_STATE_SAVE_REPLAY_QUESTION = 10
RESULT_SCREEN_STATE_CANT_SAVE_REPLAY = 11
RESULT_SCREEN_STATE_CHOOSING_REPLAY_FILE = 12
RESULT_SCREEN_STATE_WRITING_REPLAY_NAME = 13
RESULT_SCREEN_STATE_OVERWRITE_REPLAY_FILE = 14
RESULT_SCREEN_STATE_STATS_SCREEN = 15
RESULT_SCREEN_STATE_STATS_TO_SAVE_TRANSITION = 16
RESULT_SCREEN_STATE_MAX = 22

SUPERVISOR_STATE_RESULT_SCREEN_FROM_GAME = 6
RESULT_KEYBOARD_KEY_END = 95
RESULT_REPLAY_MAX_RESULTS = 15


def _i32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<i", blob, offset)[0]


def _u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


@dataclass(frozen=True, slots=True)
class RetryMenuSnapshot:
    showing: bool
    state: int
    frame_timer: int


@dataclass(frozen=True, slots=True)
class ResultScreenSnapshot:
    pointer: int
    frame_timer: int
    state: int
    frame_timer2: int
    cursor: int
    selected_replay: int
    selected_character: int
    last_name: bytes


@dataclass(frozen=True, slots=True)
class ResultDecision:
    input_mask: int
    action: str


def capture_retry_menu(reader: ResultStateReader) -> RetryMenuSnapshot:
    blob = reader.read(ADDR_RETRY_MENU, 8)
    state = _u32(blob, 0)
    if state > RETRY_MENU_STATE_EXIT_TO_TITLE:
        raise RuntimeError(f"observed invalid retry-menu state {state}")
    return RetryMenuSnapshot(
        showing=bool(reader.u8(ADDR_SHOW_RETRY_MENU)),
        state=state,
        frame_timer=_i32(blob, 4),
    )


def find_calc_chain_argument(
    reader: ResultStateReader,
    callback: int,
    *,
    maximum_elements: int = 128,
) -> int | None:
    """Find one callback argument while the bridge holds the game thread."""

    if callback <= 0:
        raise ValueError("chain callback address must be positive")
    if maximum_elements <= 0:
        raise ValueError("chain traversal bound must be positive")
    current = reader.u32(ADDR_CHAIN + CHAIN_NEXT_OFFSET)
    visited: set[int] = set()
    for _ in range(maximum_elements):
        if current == 0:
            return None
        if current in visited:
            raise RuntimeError("calc chain contains a cycle")
        visited.add(current)
        blob = reader.read(current, CHAIN_ELEM_SIZE)
        if _u32(blob, CHAIN_CALLBACK_OFFSET) == callback:
            argument = _u32(blob, CHAIN_ARGUMENT_OFFSET)
            if argument == 0:
                raise RuntimeError("result callback has a null argument")
            return argument
        current = _u32(blob, CHAIN_NEXT_OFFSET)
    raise RuntimeError(
        f"calc chain exceeded its guard of {maximum_elements} elements"
    )


def capture_result_screen(
    reader: ResultStateReader,
    *,
    update_callback: int,
) -> ResultScreenSnapshot | None:
    pointer = find_calc_chain_argument(reader, update_callback)
    if pointer is None:
        return None
    blob = reader.read(pointer, RESULT_CAPTURE_SIZE)
    pointer_after = find_calc_chain_argument(reader, update_callback)
    if pointer_after != pointer:
        raise RuntimeError("result-screen root changed during one lockstep capture")
    state = _i32(blob, RESULT_STATE_OFFSET)
    if not 0 <= state <= RESULT_SCREEN_STATE_MAX:
        raise RuntimeError(f"observed invalid result-screen state {state}")
    return ResultScreenSnapshot(
        pointer=pointer,
        frame_timer=_i32(blob, RESULT_FRAME_TIMER_OFFSET),
        state=state,
        frame_timer2=_i32(blob, RESULT_FRAME_TIMER2_OFFSET),
        cursor=_i32(blob, RESULT_CURSOR_OFFSET),
        selected_replay=_i32(blob, RESULT_SELECTED_REPLAY_OFFSET),
        selected_character=_i32(blob, RESULT_SELECTED_CHARACTER_OFFSET),
        last_name=blob[
            RESULT_LAST_NAME_OFFSET : RESULT_LAST_NAME_OFFSET
            + RESULT_LAST_NAME_SIZE
        ].split(b"\0", 1)[0],
    )


def capture_supervisor_state(reader: ResultStateReader) -> int:
    return reader.u32(ADDR_SUPERVISOR_STATE)


class RetryExitDriver:
    """Choose the source-default No path without using retry/continue."""

    def decide(
        self,
        snapshot: RetryMenuSnapshot,
        *,
        current_input: int,
    ) -> ResultDecision:
        if current_input != 0:
            return ResultDecision(0, "release")
        if not snapshot.showing:
            return ResultDecision(0, "wait-game-over")
        if snapshot.state == RETRY_MENU_STATE_INIT:
            return ResultDecision(0, "wait-retry-menu-init")
        if snapshot.state == RETRY_MENU_STATE_YES_SELECTED:
            if snapshot.frame_timer < 4:
                return ResultDecision(0, "wait-retry-menu-selection-gate")
            return ResultDecision(DOWN, "select-no-retry")
        if snapshot.state == RETRY_MENU_STATE_NO_SELECTED:
            if snapshot.frame_timer < 30:
                return ResultDecision(0, "wait-no-retry-confirm-gate")
            return ResultDecision(SHOOT, "confirm-no-retry")
        if snapshot.state == RETRY_MENU_STATE_EXIT_TO_TITLE:
            return ResultDecision(0, "wait-result-transition")
        raise RuntimeError("retry path was selected during replay capture")


class ReplaySaveDriver:
    """Save one normal-game replay using ResultScreen's observed state."""

    def __init__(self, *, replay_slot: int) -> None:
        if not 0 <= replay_slot < RESULT_REPLAY_MAX_RESULTS:
            raise ValueError("replay slot must be in [0, 14]")
        self.replay_slot = replay_slot

    def decide(
        self,
        snapshot: ResultScreenSnapshot,
        *,
        current_input: int,
    ) -> ResultDecision:
        if current_input != 0:
            return ResultDecision(0, "release")
        state = snapshot.state
        if state == RESULT_SCREEN_STATE_WRITING_HIGHSCORE_NAME:
            if snapshot.frame_timer < 10:
                return ResultDecision(0, "wait-highscore-keyboard-gate")
            return ResultDecision(MENU, "skip-highscore-name")
        if state == RESULT_SCREEN_STATE_STATS_SCREEN:
            if snapshot.frame_timer < 90:
                return ResultDecision(0, "wait-stats-confirm-gate")
            return ResultDecision(SHOOT, "confirm-stats")
        if state == RESULT_SCREEN_STATE_STATS_TO_SAVE_TRANSITION:
            return ResultDecision(0, "wait-save-question-transition")
        if state == RESULT_SCREEN_STATE_SAVE_REPLAY_QUESTION:
            if snapshot.frame_timer < 12:
                return ResultDecision(0, "wait-save-question-gate")
            if snapshot.cursor != 0:
                return ResultDecision(LEFT, "select-save-replay-yes")
            return ResultDecision(SHOOT, "confirm-save-replay")
        if state == RESULT_SCREEN_STATE_CANT_SAVE_REPLAY:
            raise RuntimeError(
                "game refused replay saving because retry, slow mode, or "
                "speedhack detection was active"
            )
        if state == RESULT_SCREEN_STATE_CHOOSING_REPLAY_FILE:
            if snapshot.frame_timer < 20:
                return ResultDecision(0, "wait-replay-slot-gate")
            if snapshot.cursor != self.replay_slot:
                forward = (self.replay_slot - snapshot.cursor) % (
                    RESULT_REPLAY_MAX_RESULTS
                )
                backward = (snapshot.cursor - self.replay_slot) % (
                    RESULT_REPLAY_MAX_RESULTS
                )
                mask = DOWN if forward <= backward else UP
                return ResultDecision(mask, "select-replay-slot")
            return ResultDecision(SHOOT, "confirm-replay-slot")
        if state == RESULT_SCREEN_STATE_OVERWRITE_REPLAY_FILE:
            raise RuntimeError("diagnostic replay slot was not empty")
        if state == RESULT_SCREEN_STATE_WRITING_REPLAY_NAME:
            if snapshot.frame_timer < 30:
                return ResultDecision(0, "wait-replay-name-gate")
            action = (
                "save-replay"
                if snapshot.selected_character == RESULT_KEYBOARD_KEY_END
                else "enter-replay-name-character"
            )
            return ResultDecision(SHOOT, action)
        if state == RESULT_SCREEN_STATE_EXITING:
            return ResultDecision(0, "wait-result-exit")
        raise RuntimeError(f"unexpected result-screen state {state}")


__all__ = (
    "ADDR_CHAIN",
    "ADDR_RETRY_MENU",
    "ADDR_SHOW_RETRY_MENU",
    "ADDR_SUPERVISOR_STATE",
    "ReplaySaveDriver",
    "ResultDecision",
    "ResultScreenSnapshot",
    "RetryExitDriver",
    "RetryMenuSnapshot",
    "capture_result_screen",
    "capture_retry_menu",
    "capture_supervisor_state",
    "find_calc_chain_argument",
)
