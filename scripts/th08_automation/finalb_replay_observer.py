"""Native-state replay driver for the read-only Final-B scale observer."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from th08_automation.practice_menu import MenuTap
from th08_automation.practice_native_menu import (
    TITLE_MODE_MAIN,
    confirm_title_menu,
    navigate_title_cursor,
    read_title_menu_state,
    wait_for_title_menu,
)
from th08_automation.practice_windows import drive_menu_plan
from th08_replay import ReplayError, decode_replay
from th08_runtime_agent import ProcessReader, SUPPORTED_INPUT_MASK, Win32, observe_state


TITLE_MODE_REPLAY = 7
REPLAY_SUBSTATE_LIST = 1
REPLAY_SUBSTATE_STAGE = 2
REPLAY_SUBSTATE_CONFIRM = 3
REPLAY_FIXED_SLOT_COUNT = 15
REPLAY_ENTRY_COUNT_OFFSET = 0xC288
REPLAY_SELECTED_ENTRY_OFFSET = 0xC28C
REPLAY_SELECTED_STAGE_OFFSET = 0xC290
ADDR_GLOBAL_MODE_FLAGS = 0x0164D0B4
REPLAY_PLAYBACK_FLAG = 0x08
FINAL_B_ROUTE_ID = 2
FINAL_B_DIFFICULTY_INDEX = 3
FINAL_B_STAGE_ROUTE_INDEX = 7


@dataclass(frozen=True)
class NativeReplayStageContract:
    slot: int
    compact_index: int
    path: Path
    sha256: str
    route_id: int
    difficulty_index: int
    stage_route_index: int
    stage_stored_input_word_count: int
    stage_input_sha256: str
    stage_bomb_press_frames: tuple[int, ...]

    def compact_record(self) -> dict[str, object]:
        record = asdict(self)
        record["path"] = self.path.as_posix()
        record["stage_bomb_press_frames"] = list(
            self.stage_bomb_press_frames
        )
        return record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_native_stage_replay(
    game_dir: Path,
    *,
    slot: int,
    expected_sha256: str,
    expected_route_id: int,
    expected_difficulty_index: int,
    expected_stage_route_index: int,
    require_single_stage: bool = True,
) -> NativeReplayStageContract:
    """Bind one fixed replay slot to one exact zero-Bomb native stage."""

    if not 1 <= slot <= REPLAY_FIXED_SLOT_COUNT:
        raise ValueError(
            f"fixed replay slot must be in 1..{REPLAY_FIXED_SLOT_COUNT}"
        )
    expected_sha256 = expected_sha256.lower()
    if len(expected_sha256) != 64:
        raise ValueError("expected replay SHA-256 must contain 64 hex digits")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise ValueError(
            "expected replay SHA-256 must contain only hex digits"
        ) from exc

    target_metadata = None
    target_path = None
    for fixed_slot in range(1, slot + 1):
        replay_path = (
            game_dir / "replay" / f"th8_{fixed_slot:02d}.rpy"
        )
        if not replay_path.is_file():
            raise FileNotFoundError(
                "fixed replay slots must be contiguous through the target: "
                f"missing {replay_path}"
            )
        try:
            metadata, _decoded = decode_replay(replay_path)
        except (OSError, ReplayError) as exc:
            raise RuntimeError(
                f"fixed replay slot {fixed_slot} is not game-decodable"
            ) from exc
        if fixed_slot == slot:
            target_metadata = metadata
            target_path = replay_path

    if target_metadata is None or target_path is None:
        raise AssertionError("target replay metadata was not selected")
    actual_sha256 = _sha256(target_path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "target replay SHA-256 mismatch: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    if target_metadata.sha256 != actual_sha256:
        raise RuntimeError("replay decoder/file SHA-256 disagreement")
    if target_metadata.route_id != expected_route_id:
        raise RuntimeError(
            "target replay route is "
            f"{target_metadata.route_id}, expected {expected_route_id}"
        )
    if target_metadata.difficulty_index != expected_difficulty_index:
        raise RuntimeError(
            "target replay difficulty is "
            f"{target_metadata.difficulty_index}, "
            f"expected {expected_difficulty_index}"
        )
    matching_stages = tuple(
        stage
        for stage in target_metadata.stages
        if stage.stage_index == expected_stage_route_index
    )
    if len(matching_stages) != 1:
        raise RuntimeError(
            "target replay must contain exactly one requested stage "
            f"index {expected_stage_route_index}"
        )
    if require_single_stage and len(target_metadata.stages) != 1:
        raise RuntimeError("target replay must contain only the requested stage")
    stage = matching_stages[0]
    if stage.frame_count <= 0:
        raise RuntimeError("target replay stage has no input frames")
    if stage.bomb_press_frames:
        raise RuntimeError(
            "target replay contains Bomb presses and cannot drive this gate"
        )
    return NativeReplayStageContract(
        slot=slot,
        compact_index=slot - 1,
        path=target_path,
        sha256=actual_sha256,
        route_id=target_metadata.route_id,
        difficulty_index=target_metadata.difficulty_index,
        stage_route_index=stage.stage_index,
        stage_stored_input_word_count=stage.stored_input_word_count,
        stage_input_sha256=stage.input_sha256,
        stage_bomb_press_frames=stage.bomb_press_frames,
    )


FinalBReplayContract = NativeReplayStageContract


def validate_finalb_replay(
    game_dir: Path,
    *,
    slot: int,
    expected_sha256: str,
) -> FinalBReplayContract:
    """Bind one fixed replay slot to an exact zero-Bomb Final-B practice."""

    try:
        return validate_native_stage_replay(
            game_dir,
            slot=slot,
            expected_sha256=expected_sha256,
            expected_route_id=FINAL_B_ROUTE_ID,
            expected_difficulty_index=FINAL_B_DIFFICULTY_INDEX,
            expected_stage_route_index=FINAL_B_STAGE_ROUTE_INDEX,
        )
    except RuntimeError as exc:
        if str(exc) == "target replay must contain only the requested stage":
            raise RuntimeError(
                "target replay must contain only Final-B stage index 7"
            ) from exc
        raise


def read_replay_menu_state(api: Win32, pid: int) -> dict[str, int]:
    state = read_title_menu_state(api, pid)
    manager = state["manager"]
    if manager == 0:
        raise RuntimeError("title menu manager is not allocated")
    reader = ProcessReader(api, pid)
    try:
        state.update(
            {
                "replay_entry_count": reader.u32(
                    manager + REPLAY_ENTRY_COUNT_OFFSET
                ),
                "replay_selected_entry": reader.u32(
                    manager + REPLAY_SELECTED_ENTRY_OFFSET
                ),
                "replay_selected_stage": reader.u32(
                    manager + REPLAY_SELECTED_STAGE_OFFSET
                ),
            }
        )
    finally:
        reader.close()
    return state


def wait_for_replay_substate(
    api: Win32,
    pid: int,
    *,
    substate: int,
    timeout_seconds: float,
    clock: Callable[[], float] = time.perf_counter,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    if timeout_seconds <= 0.0:
        raise ValueError("replay menu timeout must be positive")
    deadline = clock() + timeout_seconds
    last: dict[str, int] | None = None
    while clock() < deadline:
        last = read_replay_menu_state(api, pid)
        if (
            last["mode"] == TITLE_MODE_REPLAY
            and last["substate"] == substate
        ):
            return last
        sleeper(0.02)
    raise TimeoutError(
        f"replay menu did not reach substate {substate}; last={last}"
    )


def _confirm_replay_substate(
    api: Win32,
    pid: int,
    *,
    current_substate: int,
    next_substate: int,
    purpose: str,
    hold_ms: int,
    screen_settle_ms: int,
    timeout_seconds: float,
) -> tuple[dict[str, int], MenuTap]:
    state = wait_for_replay_substate(
        api,
        pid,
        substate=current_substate,
        timeout_seconds=timeout_seconds,
    )
    tap = MenuTap("confirm", purpose, screen_settle_ms)
    drive_menu_plan(api, pid, (tap,), hold_ms=hold_ms)
    next_state = wait_for_replay_substate(
        api,
        pid,
        substate=next_substate,
        timeout_seconds=timeout_seconds,
    )
    if state["mode"] != next_state["mode"]:
        raise RuntimeError("replay confirmation changed the title mode")
    return next_state, tap


def _navigate_replay_substate_cursor(
    api: Win32,
    pid: int,
    *,
    substate: int,
    target: int,
    option_count: int,
    purpose: str,
    hold_ms: int,
    tap_gap_ms: int,
    timeout_seconds: float,
) -> tuple[dict[str, int], tuple[MenuTap, ...]]:
    if not 0 <= target < option_count:
        raise ValueError(
            f"target replay cursor {target} outside 0..{option_count - 1}"
        )
    state = wait_for_replay_substate(
        api,
        pid,
        substate=substate,
        timeout_seconds=timeout_seconds,
    )
    taps: list[MenuTap] = []
    visited = [state["cursor"]]
    deadline = time.perf_counter() + timeout_seconds
    for attempt in range(option_count * 3):
        if state["cursor"] == target:
            return state, tuple(taps)
        tap = MenuTap(
            "down",
            f"{purpose} feedback step {attempt + 1}",
            tap_gap_ms,
        )
        drive_menu_plan(api, pid, (tap,), hold_ms=hold_ms)
        taps.append(tap)
        state = read_replay_menu_state(api, pid)
        visited.append(state["cursor"])
        if (
            state["mode"] != TITLE_MODE_REPLAY
            or state["substate"] != substate
        ):
            raise RuntimeError(
                "replay cursor navigation left its expected state: "
                f"last={state}"
            )
        if time.perf_counter() >= deadline:
            break
    raise RuntimeError(
        f"replay cursor {target} is not reachable; "
        f"visited={visited} last={state}"
    )


def drive_native_stage_replay_menu(
    api: Win32,
    pid: int,
    *,
    contract: NativeReplayStageContract,
    hold_ms: int,
    tap_gap_ms: int,
    screen_settle_ms: int,
    timeout_seconds: float,
) -> tuple[dict[str, object], ...]:
    """Select the exact replay and return before any gameplay input."""

    trace: list[dict[str, object]] = []

    def retain(
        label: str,
        state: dict[str, int],
        taps: tuple[MenuTap, ...],
    ) -> None:
        trace.append(
            {
                "label": label,
                "state": state,
                "taps": [asdict(tap) for tap in taps],
            }
        )

    wait_for_title_menu(
        api,
        pid,
        mode=TITLE_MODE_MAIN,
        timeout_seconds=timeout_seconds,
    )
    state, taps = navigate_title_cursor(
        api,
        pid,
        mode=TITLE_MODE_MAIN,
        target=4,
        option_count=9,
        purpose="select Replay",
        hold_ms=hold_ms,
        tap_gap_ms=tap_gap_ms,
        timeout_seconds=timeout_seconds,
    )
    retain("replay_main_entry_selected", state, taps)
    tap = confirm_title_menu(
        api,
        pid,
        next_mode=TITLE_MODE_REPLAY,
        purpose="enter Replay",
        hold_ms=hold_ms,
        screen_settle_ms=screen_settle_ms,
        timeout_seconds=timeout_seconds,
    )
    state = wait_for_replay_substate(
        api,
        pid,
        substate=REPLAY_SUBSTATE_LIST,
        timeout_seconds=timeout_seconds,
    )
    retain("replay_list_entered", state, (tap,))
    entry_count = state["replay_entry_count"]
    if entry_count < contract.slot:
        raise RuntimeError(
            "game replay list has fewer decoded entries than the bound slot: "
            f"entry_count={entry_count} slot={contract.slot}"
        )

    state, taps = _navigate_replay_substate_cursor(
        api,
        pid,
        substate=REPLAY_SUBSTATE_LIST,
        target=contract.compact_index,
        option_count=entry_count,
        purpose=f"select fixed replay slot {contract.slot}",
        hold_ms=hold_ms,
        tap_gap_ms=tap_gap_ms,
        timeout_seconds=timeout_seconds,
    )
    retain("replay_entry_selected", state, taps)
    state, tap = _confirm_replay_substate(
        api,
        pid,
        current_substate=REPLAY_SUBSTATE_LIST,
        next_substate=REPLAY_SUBSTATE_STAGE,
        purpose=f"open fixed replay slot {contract.slot}",
        hold_ms=hold_ms,
        screen_settle_ms=screen_settle_ms,
        timeout_seconds=timeout_seconds,
    )
    if state["replay_selected_entry"] != contract.compact_index:
        raise RuntimeError(
            "native replay selection disagrees with the bound compact index"
        )
    retain("replay_stage_list_entered", state, (tap,))
    state, taps = _navigate_replay_substate_cursor(
        api,
        pid,
        substate=REPLAY_SUBSTATE_STAGE,
        target=contract.stage_route_index,
        option_count=9,
        purpose=(
            f"select replay stage {contract.stage_route_index}"
        ),
        hold_ms=hold_ms,
        tap_gap_ms=tap_gap_ms,
        timeout_seconds=timeout_seconds,
    )
    retain("replay_stage_selected", state, taps)
    state, tap = _confirm_replay_substate(
        api,
        pid,
        current_substate=REPLAY_SUBSTATE_STAGE,
        next_substate=REPLAY_SUBSTATE_CONFIRM,
        purpose="open replay confirmation",
        hold_ms=hold_ms,
        screen_settle_ms=screen_settle_ms,
        timeout_seconds=timeout_seconds,
    )
    if (
        state["replay_selected_entry"] != contract.compact_index
        or state["replay_selected_stage"] != contract.stage_route_index
    ):
        raise RuntimeError(
            "native replay entry/stage identity drifted before launch"
        )
    retain("replay_confirmation_entered", state, (tap,))

    final_tap = MenuTap(
        "confirm",
        (
            "start native-verified stage "
            f"{contract.stage_route_index} replay"
        ),
        screen_settle_ms,
    )
    drive_menu_plan(api, pid, (final_tap,), hold_ms=hold_ms)
    trace.append(
        {
            "label": "replay_launch_confirmed",
            "state": {
                "replay_selected_entry": contract.compact_index,
                "replay_selected_stage": contract.stage_route_index,
            },
            "taps": [asdict(final_tap)],
        }
    )
    return tuple(trace)


def drive_finalb_replay_menu(
    api: Win32,
    pid: int,
    *,
    contract: FinalBReplayContract,
    hold_ms: int,
    tap_gap_ms: int,
    screen_settle_ms: int,
    timeout_seconds: float,
) -> tuple[dict[str, object], ...]:
    return drive_native_stage_replay_menu(
        api,
        pid,
        contract=contract,
        hold_ms=hold_ms,
        tap_gap_ms=tap_gap_ms,
        screen_settle_ms=screen_settle_ms,
        timeout_seconds=timeout_seconds,
    )


def wait_for_bound_replay_gameplay(
    api: Win32,
    pid: int,
    *,
    contract: NativeReplayStageContract,
    timeout_seconds: float,
) -> tuple[ProcessReader, dict[str, object]]:
    reader = ProcessReader(api, pid)
    deadline = time.perf_counter() + timeout_seconds
    last: dict[str, object] | None = None
    try:
        while time.perf_counter() < deadline:
            last = observe_state(reader)
            if not last["gameplay_active"]:
                time.sleep(0.02)
                continue
            flags = reader.u32(ADDR_GLOBAL_MODE_FLAGS)
            if flags & REPLAY_PLAYBACK_FLAG == 0:
                raise RuntimeError(
                    "gameplay began without the native replay-playback flag"
                )
            if (
                last["route_id"] != contract.route_id
                or last["difficulty_index"] != contract.difficulty_index
                or last["stage_route_index"]
                != contract.stage_route_index
            ):
                raise RuntimeError(
                    "native gameplay identity disagrees with replay contract: "
                    f"state={last}"
                )
            if int(last["input_raw"]) & SUPPORTED_INPUT_MASK:
                raise RuntimeError(
                    "raw gameplay input remained active after replay launch"
                )
            return reader, last
        raise TimeoutError(
            f"bound native replay did not enter gameplay; last={last}"
        )
    except Exception:
        reader.close()
        raise


__all__ = [
    "ADDR_GLOBAL_MODE_FLAGS",
    "FINAL_B_DIFFICULTY_INDEX",
    "FINAL_B_ROUTE_ID",
    "FINAL_B_STAGE_ROUTE_INDEX",
    "FinalBReplayContract",
    "NativeReplayStageContract",
    "REPLAY_ENTRY_COUNT_OFFSET",
    "REPLAY_FIXED_SLOT_COUNT",
    "REPLAY_PLAYBACK_FLAG",
    "REPLAY_SELECTED_ENTRY_OFFSET",
    "REPLAY_SELECTED_STAGE_OFFSET",
    "REPLAY_SUBSTATE_CONFIRM",
    "REPLAY_SUBSTATE_LIST",
    "REPLAY_SUBSTATE_STAGE",
    "TITLE_MODE_REPLAY",
    "drive_native_stage_replay_menu",
    "drive_finalb_replay_menu",
    "read_replay_menu_state",
    "validate_finalb_replay",
    "validate_native_stage_replay",
    "wait_for_bound_replay_gameplay",
    "wait_for_replay_substate",
]
