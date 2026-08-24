"""Native-state-driven TH08 Practice Start menu navigation."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from collections.abc import Callable

from th08_automation.practice_menu import (
    MenuTap,
    PracticeDifficulty,
    PracticeStage,
)
from th08_automation.practice_windows import drive_menu_plan
from th08_runtime_agent import (
    ADDR_DIFFICULTY_INDEX,
    ADDR_ROUTE_ID,
    ADDR_STAGE_ROUTE_INDEX,
    ProcessReader,
    Win32,
)

ADDR_TITLE_MENU_MANAGER = 0x018BDE08
ADDR_TITLE_DIFFICULTY_CURSOR = 0x017CE891
ADDR_PRACTICE_STAGE_AVAILABILITY = 0x0164B9AE
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
TITLE_CURSOR_OFFSET = 0
TITLE_SUBSTATE_OFFSET = 12
TITLE_MODE_OFFSET = 82_984
TITLE_SCREEN_AGE_OFFSET = 82_988
TITLE_MODE_MAIN = 0
TITLE_MODE_PRACTICE_DIFFICULTY = 8
TITLE_MODE_PRACTICE_TEAM = 9
TITLE_MODE_PRACTICE_STAGE = 11


def practice_stage_availability_address(
    route_id: int,
    difficulty_index: int,
) -> int:
    if not 0 <= route_id <= 12:
        raise ValueError("practice route/shot index is outside 0..12")
    if not 0 <= difficulty_index <= 4:
        raise ValueError("practice difficulty index is outside 0..4")
    # Source Clrd is 0x24 bytes (18 u16 values). This base is
    # difficultiesClearedWithRetries[0] for shot/route zero.
    return ADDR_PRACTICE_STAGE_AVAILABILITY + 2 * (
        18 * route_id + difficulty_index
    )


def write_process_u16(api: Win32, pid: int, address: int, value: int) -> None:
    if not 0 <= value <= 0xFFFF:
        raise ValueError("u16 process write is outside 0..65535")
    api.kernel32.WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.LPCVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    api.kernel32.WriteProcessMemory.restype = wintypes.BOOL
    handle = api.kernel32.OpenProcess(
        PROCESS_VM_OPERATION | PROCESS_VM_WRITE,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(
            ctypes.get_last_error(),
            f"OpenProcess({pid}) for practice-stage unlock",
        )
    try:
        payload = ctypes.c_ushort(value)
        written = ctypes.c_size_t()
        if not api.kernel32.WriteProcessMemory(
            handle,
            ctypes.c_void_p(address),
            ctypes.byref(payload),
            ctypes.sizeof(payload),
            ctypes.byref(written),
        ):
            raise ctypes.WinError(
                ctypes.get_last_error(),
                f"WriteProcessMemory(0x{address:08X})",
            )
        if written.value != ctypes.sizeof(payload):
            raise RuntimeError(
                "short practice-stage unlock write: "
                f"{written.value}/{ctypes.sizeof(payload)}"
            )
    finally:
        api.kernel32.CloseHandle(handle)


def unlock_requested_practice_stage(
    api: Win32,
    pid: int,
    *,
    stage_index: int,
    expected_route_id: int,
    expected_difficulty_index: int,
    timeout_seconds: float,
) -> dict[str, int | bool]:
    if not 0 <= stage_index < 8:
        raise ValueError("practice stage index is outside 0..7")
    state = wait_for_title_menu(
        api,
        pid,
        mode=TITLE_MODE_PRACTICE_STAGE,
        timeout_seconds=timeout_seconds,
    )
    if state["route_id"] != expected_route_id:
        raise RuntimeError(
            "practice-stage unlock route mismatch: "
            f"expected {expected_route_id}, got {state['route_id']}"
        )
    if state["difficulty_cursor"] != expected_difficulty_index:
        raise RuntimeError(
            "practice-stage unlock difficulty mismatch: "
            f"expected {expected_difficulty_index}, "
            f"got {state['difficulty_cursor']}"
        )
    address = practice_stage_availability_address(
        state["route_id"],
        state["difficulty_cursor"],
    )
    before = state["practice_stage_availability_mask"]
    requested_bit = 1 << stage_index
    after = before | requested_bit
    wrote = after != before
    if wrote:
        write_process_u16(api, pid, address, after)
        verified = read_title_menu_state(api, pid)
        if (
            verified["mode"] != TITLE_MODE_PRACTICE_STAGE
            or verified["substate"] != 1
            or verified["route_id"] != expected_route_id
            or verified["difficulty_cursor"] != expected_difficulty_index
            or verified["practice_stage_availability_mask"] != after
        ):
            raise RuntimeError(
                "practice-stage unlock verification failed: "
                f"expected mask 0x{after:04X}, got {verified}"
            )
    return {
        "requested": True,
        "address": address,
        "stage_index": stage_index,
        "requested_bit": requested_bit,
        "mask_before": before,
        "mask_after": after,
        "wrote": wrote,
        "verified": True,
    }


def read_menu_selection(api: Win32, pid: int) -> dict[str, int]:
    reader = ProcessReader(api, pid)
    try:
        difficulty = reader.u32(ADDR_DIFFICULTY_INDEX)
        route = reader.u8(ADDR_ROUTE_ID)
    finally:
        reader.close()
    return {"difficulty_index": difficulty, "route_id": route}


def read_title_menu_state(api: Win32, pid: int) -> dict[str, int]:
    reader = ProcessReader(api, pid)
    try:
        manager = reader.u32(ADDR_TITLE_MENU_MANAGER)
        if not manager:
            raise RuntimeError("title menu manager is not allocated")
        difficulty_cursor = reader.u8(ADDR_TITLE_DIFFICULTY_CURSOR)
        route_id = reader.u8(ADDR_ROUTE_ID)
        return {
            "manager": manager,
            "mode": reader.u32(manager + TITLE_MODE_OFFSET),
            "substate": reader.u32(manager + TITLE_SUBSTATE_OFFSET),
            "screen_age": reader.u32(manager + TITLE_SCREEN_AGE_OFFSET),
            "cursor": reader.u32(manager + TITLE_CURSOR_OFFSET),
            "difficulty_cursor": difficulty_cursor,
            "difficulty_index": reader.u32(ADDR_DIFFICULTY_INDEX),
            "route_id": route_id,
            "stage_route_index": reader.u32(ADDR_STAGE_ROUTE_INDEX),
            "practice_stage_availability_mask": reader.u16(
                practice_stage_availability_address(
                    route_id,
                    difficulty_cursor,
                )
            ),
        }
    finally:
        reader.close()


def wait_for_title_menu(
    api: Win32,
    pid: int,
    *,
    mode: int,
    timeout_seconds: float,
) -> dict[str, int]:
    deadline = time.perf_counter() + timeout_seconds
    last: dict[str, int] | None = None
    while time.perf_counter() < deadline:
        try:
            last = read_title_menu_state(api, pid)
        except RuntimeError as exc:
            if str(exc) != "title menu manager is not allocated":
                raise
            time.sleep(0.02)
            continue
        if last["mode"] == mode and last["substate"] == 1:
            return last
        time.sleep(0.02)
    raise TimeoutError(
        f"title menu mode {mode} did not become interactive; last={last}"
    )


def practice_stage_available(mask: int, stage_index: int) -> bool:
    return bool(mask & (1 << stage_index))


def navigate_title_cursor(
    api: Win32,
    pid: int,
    *,
    mode: int,
    target: int,
    option_count: int,
    purpose: str,
    hold_ms: int,
    tap_gap_ms: int,
    timeout_seconds: float,
    direction_key: str = "down",
) -> tuple[dict[str, int], tuple[MenuTap, ...]]:
    state = wait_for_title_menu(
        api,
        pid,
        mode=mode,
        timeout_seconds=timeout_seconds,
    )
    if not 0 <= target < option_count:
        raise ValueError(f"target cursor {target} outside menu option count")
    if (
        mode == TITLE_MODE_PRACTICE_STAGE
        and not practice_stage_available(
            state["practice_stage_availability_mask"],
            target,
        )
    ):
        raise RuntimeError(
            f"title cursor {target} is disabled in mode {mode}; "
            "practice_stage_availability_mask="
            f"0x{state['practice_stage_availability_mask']:04X} "
            f"state={state}"
        )
    taps: list[MenuTap] = []
    visited = [state["cursor"]]
    deadline = time.perf_counter() + timeout_seconds
    max_attempts = option_count * 3
    for attempt in range(max_attempts):
        if state["cursor"] == target:
            return state, tuple(taps)
        tap = MenuTap(
            direction_key,
            f"{purpose} feedback step {attempt + 1}",
            tap_gap_ms,
        )
        drive_menu_plan(api, pid, (tap,), hold_ms=hold_ms)
        taps.append(tap)
        state = read_title_menu_state(api, pid)
        visited.append(state["cursor"])
        if (
            state["mode"] == mode
            and state["substate"] == 1
            and state["cursor"] == target
        ):
            return state, tuple(taps)
        if time.perf_counter() >= deadline:
            break
    raise RuntimeError(
        f"title cursor {target} is not reachable in mode {mode}; "
        f"visited={visited} last={state}"
    )


def confirm_title_menu(
    api: Win32,
    pid: int,
    *,
    next_mode: int,
    purpose: str,
    hold_ms: int,
    screen_settle_ms: int,
    timeout_seconds: float,
) -> MenuTap:
    tap = MenuTap("confirm", purpose, screen_settle_ms)
    drive_menu_plan(api, pid, (tap,), hold_ms=hold_ms)
    wait_for_title_menu(
        api,
        pid,
        mode=next_mode,
        timeout_seconds=timeout_seconds,
    )
    return tap


def validate_practice_selection(
    api: Win32,
    pid: int,
    *,
    stage: PracticeStage,
    difficulty: PracticeDifficulty,
    read_state: Callable[[Win32, int], dict[str, int]] = read_title_menu_state,
) -> dict[str, int]:
    state = read_state(api, pid)
    if (
        state["mode"] != TITLE_MODE_PRACTICE_STAGE
        or state["substate"] != 1
        or state["cursor"] != stage.menu_index
        or state["difficulty_cursor"] != difficulty.menu_index
        or state["route_id"] != 2
    ):
        raise RuntimeError(
            "native Practice selection mismatch before final confirm: "
            f"mode={state['mode']} substate={state['substate']} "
            f"cursor={state['cursor']} difficulty_cursor="
            f"{state['difficulty_cursor']} difficulty_index="
            f"{state['difficulty_index']} route={state['route_id']}"
        )
    return state
