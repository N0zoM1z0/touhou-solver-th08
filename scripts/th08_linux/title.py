"""Source-derived title-menu sensing and deterministic route selection."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Protocol

from th08_linux.protocol import DOWN, LEFT, RIGHT, SHOOT, UP
from th08_runtime.game_state import (
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENGINE_FLAGS,
    ADDR_ROUTE_ID,
    ADDR_STAGE_ROUTE_INDEX,
)


class TitleStateReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...

    def u32(self, address: int) -> int: ...


# Fixed global addresses are retained by the modern Linux linker script and
# match config/reccmp-globals.csv in the source reconstruction.
ADDR_TITLE_SCREEN_POINTER = 0x018BDE08
ADDR_GAME_MANAGER = 0x0160F508
ADDR_GAME_MANAGER_LOADING_STATE = ADDR_GAME_MANAGER + 0x38
ADDR_GAME_MANAGER_CALC_CHAIN = 0x0164D344
CHAIN_ELEM_CALLBACK_OFFSET = 0x04
ADDR_GAME_MANAGER_CALC_CALLBACK = (
    ADDR_GAME_MANAGER_CALC_CHAIN + CHAIN_ELEM_CALLBACK_OFFSET
)

# `gdb ptype /o th08::TitleScreen` against the pinned i386 runtime confirms
# these source-member offsets.  Capture through `state`, the last field needed
# by the menu controller, in one allocation-independent process read.
TITLE_CURSOR_OFFSET = 0
TITLE_CURRENT_SCREEN_STATE_OFFSET = 12
TITLE_STATE_TIMER_OFFSET = 16
TITLE_PREVIOUS_SCREEN_OFFSET = 104
TITLE_IDLE_FRAMES_OFFSET = 49812
TITLE_CURRENT_SCREEN_OFFSET = 82984
TITLE_STATE_TIMER2_OFFSET = 82988
TITLE_START_MENU_IDLE_FRAMES_OFFSET = 82992
TITLE_STATE_OFFSET = 82996
TITLE_CAPTURE_SIZE = TITLE_STATE_OFFSET + 4

TITLE_SCREEN_START = 0
TITLE_SCREEN_DIFFICULTY = 4
TITLE_SCREEN_CHARACTER = 5

TITLE_LIFECYCLE_READY = 0
TITLE_LIFECYCLE_LOADING = 1
TITLE_LIFECYCLE_CLOSE = 2

TITLE_CURRENT_STATE_INIT = 0
TITLE_CURRENT_STATE_READY = 1
TITLE_CURRENT_STATE_EXIT = 2
TITLE_CURRENT_STATE_CHANGING = 3

EASY_DIFFICULTY = 0
SAKUYA_REMILIA_SHOT_TYPE = 2

_NORMAL_DIFFICULTY_COUNT = 4
_NORMAL_TEAM_COUNT = 4
_UNLOCKED_SHOT_TYPE_COUNT = 12
_START_MENU_COUNT = 9
_ALL_TEAMS_UNLOCKED_FLAG = 1 << 17


def _i32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<i", blob, offset)[0]


@dataclass(frozen=True, slots=True)
class TitleSnapshot:
    pointer: int
    cursor: int
    current_screen_state: int
    state_timer: int
    previous_screen: int
    idle_frames: int
    current_screen: int
    state_timer2: int
    start_menu_idle_frames: int
    lifecycle_state: int
    game_manager_flags: int

    @property
    def ready_for_input(self) -> bool:
        return (
            self.lifecycle_state == TITLE_LIFECYCLE_READY
            and self.current_screen_state == TITLE_CURRENT_STATE_READY
        )

    @property
    def character_menu_length(self) -> int:
        if self.game_manager_flags & _ALL_TEAMS_UNLOCKED_FLAG:
            return _UNLOCKED_SHOT_TYPE_COUNT
        return _NORMAL_TEAM_COUNT


@dataclass(frozen=True, slots=True)
class GameplayBootstrapSnapshot:
    calc_callback: int
    loading_state: int
    difficulty_index: int
    shot_type_index: int
    stage_route_index: int

    @property
    def registered(self) -> bool:
        return self.calc_callback != 0

    @property
    def ready(self) -> bool:
        return self.registered and self.loading_state == 0


@dataclass(frozen=True, slots=True)
class TitleDecision:
    input_mask: int
    action: str


def capture_title_snapshot(reader: TitleStateReader) -> TitleSnapshot | None:
    pointer = reader.u32(ADDR_TITLE_SCREEN_POINTER)
    if pointer == 0:
        return None
    blob = reader.read(pointer, TITLE_CAPTURE_SIZE)
    pointer_after = reader.u32(ADDR_TITLE_SCREEN_POINTER)
    if pointer_after != pointer:
        raise RuntimeError("title-screen root changed during one lockstep capture")
    return TitleSnapshot(
        pointer=pointer,
        cursor=_i32(blob, TITLE_CURSOR_OFFSET),
        current_screen_state=_i32(
            blob, TITLE_CURRENT_SCREEN_STATE_OFFSET
        ),
        state_timer=_i32(blob, TITLE_STATE_TIMER_OFFSET),
        previous_screen=_i32(blob, TITLE_PREVIOUS_SCREEN_OFFSET),
        idle_frames=_i32(blob, TITLE_IDLE_FRAMES_OFFSET),
        current_screen=_i32(blob, TITLE_CURRENT_SCREEN_OFFSET),
        state_timer2=_i32(blob, TITLE_STATE_TIMER2_OFFSET),
        start_menu_idle_frames=_i32(
            blob, TITLE_START_MENU_IDLE_FRAMES_OFFSET
        ),
        lifecycle_state=_i32(blob, TITLE_STATE_OFFSET),
        game_manager_flags=reader.u32(ADDR_ENGINE_FLAGS),
    )


def capture_gameplay_bootstrap(
    reader: TitleStateReader,
) -> GameplayBootstrapSnapshot:
    return GameplayBootstrapSnapshot(
        calc_callback=reader.u32(ADDR_GAME_MANAGER_CALC_CALLBACK),
        loading_state=reader.u32(ADDR_GAME_MANAGER_LOADING_STATE),
        difficulty_index=reader.u32(ADDR_DIFFICULTY_INDEX),
        shot_type_index=reader.u32(ADDR_ROUTE_ID) & 0xFF,
        stage_route_index=reader.u32(ADDR_STAGE_ROUTE_INDEX),
    )


def _circular_step(
    cursor: int,
    target: int,
    length: int,
    *,
    negative: int,
    positive: int,
) -> int:
    if not 0 <= cursor < length:
        raise RuntimeError(
            f"observed menu cursor {cursor} outside source-derived length {length}"
        )
    if not 0 <= target < length:
        raise ValueError(f"target menu cursor {target} is outside length {length}")
    if cursor == target:
        return 0
    positive_distance = (target - cursor) % length
    negative_distance = (cursor - target) % length
    return positive if positive_distance <= negative_distance else negative


class RouteTitleDriver:
    """Select one normal route using only observed, source-defined menu state."""

    _SCREEN_ORDER = {
        TITLE_SCREEN_START: 0,
        TITLE_SCREEN_DIFFICULTY: 1,
        TITLE_SCREEN_CHARACTER: 2,
    }

    def __init__(self, *, difficulty_index: int, shot_type_index: int) -> None:
        if not 0 <= difficulty_index < _NORMAL_DIFFICULTY_COUNT:
            raise ValueError("normal-route difficulty must be in [0, 3]")
        if not 0 <= shot_type_index < _UNLOCKED_SHOT_TYPE_COUNT:
            raise ValueError("shot type must be in [0, 11]")
        self.difficulty_index = difficulty_index
        self.shot_type_index = shot_type_index
        self._furthest_screen_order = -1

    def decide(
        self,
        snapshot: TitleSnapshot | None,
        *,
        current_input: int,
    ) -> TitleDecision:
        # Every menu action is an edge.  Releasing a prior mask takes priority
        # over interpreting the next screen, including after a confirm.
        if current_input != 0:
            return TitleDecision(0, "release")
        if snapshot is None:
            return TitleDecision(0, "wait-title-root")
        if snapshot.lifecycle_state == TITLE_LIFECYCLE_CLOSE:
            raise RuntimeError("title screen entered the source-defined close state")
        if snapshot.lifecycle_state != TITLE_LIFECYCLE_READY:
            return TitleDecision(0, "wait-title-lifecycle")

        screen_order = self._SCREEN_ORDER.get(snapshot.current_screen)
        if screen_order is None:
            raise RuntimeError(
                f"unexpected title screen {snapshot.current_screen} on route bootstrap"
            )
        if screen_order < self._furthest_screen_order:
            raise RuntimeError("title route moved backwards unexpectedly")
        self._furthest_screen_order = max(
            self._furthest_screen_order, screen_order
        )

        if snapshot.current_screen_state != TITLE_CURRENT_STATE_READY:
            if snapshot.current_screen_state not in (
                TITLE_CURRENT_STATE_INIT,
                TITLE_CURRENT_STATE_CHANGING,
            ):
                raise RuntimeError(
                    "unexpected source-defined title current-screen state "
                    f"{snapshot.current_screen_state}"
                )
            return TitleDecision(0, "wait-screen-ready")

        if snapshot.current_screen == TITLE_SCREEN_START:
            step = _circular_step(
                snapshot.cursor,
                0,
                _START_MENU_COUNT,
                negative=UP,
                positive=DOWN,
            )
            if step:
                return TitleDecision(step, "select-start")
            # OnUpdateStartMenu intentionally ignores confirm for its first ten
            # Ready-state ticks.
            if snapshot.state_timer2 < 10:
                return TitleDecision(0, "wait-start-confirm-gate")
            return TitleDecision(SHOOT, "confirm-start")

        if snapshot.current_screen == TITLE_SCREEN_DIFFICULTY:
            step = _circular_step(
                snapshot.cursor,
                self.difficulty_index,
                _NORMAL_DIFFICULTY_COUNT,
                negative=UP,
                positive=DOWN,
            )
            if step:
                return TitleDecision(step, "select-difficulty")
            return TitleDecision(SHOOT, "confirm-difficulty")

        menu_length = snapshot.character_menu_length
        step = _circular_step(
            snapshot.cursor,
            self.shot_type_index,
            menu_length,
            negative=LEFT,
            positive=RIGHT,
        )
        if step:
            return TitleDecision(step, "select-shot-type")
        return TitleDecision(SHOOT, "confirm-shot-type")


__all__ = (
    "ADDR_GAME_MANAGER_CALC_CALLBACK",
    "ADDR_GAME_MANAGER_LOADING_STATE",
    "ADDR_TITLE_SCREEN_POINTER",
    "EASY_DIFFICULTY",
    "GameplayBootstrapSnapshot",
    "RouteTitleDriver",
    "SAKUYA_REMILIA_SHOT_TYPE",
    "TITLE_CAPTURE_SIZE",
    "TITLE_CURRENT_STATE_READY",
    "TITLE_LIFECYCLE_READY",
    "TITLE_SCREEN_CHARACTER",
    "TITLE_SCREEN_DIFFICULTY",
    "TITLE_SCREEN_START",
    "TitleDecision",
    "TitleSnapshot",
    "capture_gameplay_bootstrap",
    "capture_title_snapshot",
)
