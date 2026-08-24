#!/usr/bin/env python3
"""Implement the TH08 runtime probe and fail-closed physical-key agent.

Run this script with Windows Python. ``probe`` and ``observe`` never write to
the target. ``play`` uses ordinary scan-code ``SendInput`` events; it never
patches process memory and requires an explicit ``--armed`` flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from runtime_agent import (
    FrameSynchronizedPlayback,
    InputTransition,
    load_input_masks,
)
from th08_runtime.game_state import (  # noqa: F401
    ADDR_CURRENT_INPUT,
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_ENGINE_FLAGS,
    ADDR_FRSCREEN_IMPL_POINTER,
    ADDR_FRSCREEN_UPDATE_SERIAL,
    ADDR_GAMEPLAY_RNG,
    ADDR_GAMEPLAY_TIME_SCALE,
    ADDR_NO_LIFE_DECREMENT_PATCH,
    ADDR_PLAYER,
    ADDR_PREVIOUS_INPUT,
    ADDR_RAW_INPUT,
    ADDR_ROUTE_ID,
    ADDR_RUN_STATE_INNER_POINTER,
    ADDR_SCRIPTED_UPDATE_FREEZE,
    ADDR_SPELL_CARD_STATE,
    ADDR_STAGE_ROUTE_INDEX,
    EXPECTED_EXE_SHA256,
    FRSCREEN_MSG_PC_OFFSET,
    FRSCREEN_MSG_RESOURCE_OFFSET,
    FRSCREEN_MSG_STATE_OFFSET,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_BOMB_INDEX_OFFSET,
    PLAYER_BOMB_LOCKOUT_OFFSET,
    PLAYER_BOMB_TIMER_OFFSET,
    PLAYER_POSITION_OFFSET,
    PLAYER_PREDEATH_COUNTER_OFFSET,
    PLAYER_VELOCITY_OFFSET,
    RUN_STATE_BOMBS_OFFSET,
    RUN_STATE_LIVES_OFFSET,
    RUN_STATE_POWER_OFFSET,
    SPELL_STATE_ACTIVE_FLAG,
    SPELL_STATE_CAPTURE_SIZE,
    SPELL_STATE_PREFIX_SIZE,
    SPELL_STATE_TIMER_ELAPSED_OFFSET,
    SUPPORTED_INPUT_MASK,
    TARGET_EXE,
)
from th08_runtime.sensing import (  # noqa: F401
    PLAYER_CONTROL_GEOMETRY_CAPTURE_SIZE,
    capture_input_clock_shadow,
    capture_player_control_root,
    capture_time_scale_root,
    decode_spell_state,
    frscreen_blocks_enemy_clock,
    observe_state,
)
from th08_runtime.input import (  # noqa: F401
    SCAN_CODES,
    TAP_NAMES,
    keyboard_input as _keyboard_input,
    release_all,
    scan_keyboard_input as _scan_keyboard_input,
    send_scan_key,
    send_transitions,
)
from th08_runtime.win32 import (  # noqa: F401
    HARDWAREINPUT,
    INJECTION_MARKER,
    INPUT,
    INPUT_KEYBOARD,
    INPUT_UNION,
    INVALID_HANDLE_VALUE,
    KEYBDINPUT,
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    MOUSEINPUT,
    PROCESSENTRY32W,
    PROCESS_QUERY_LIMITED_INFORMATION,
    PROCESS_SUSPEND_RESUME,
    PROCESS_VM_READ,
    TH32CS_SNAPPROCESS,
    ProcessReader,
    ProcessSuspension,
    Win32,
    require_windows as _require_windows,
    verify_target,
    win_error as _win_error,
)


def release_injected_keys(api: Win32) -> None:
    """Release every key this bridge can hold, including fast-forward."""

    # Resolve these through the compatibility module so historical tests and
    # recovery tooling can patch either call without bypassing the wrapper.
    release_all(api)
    send_scan_key(api, scan_code=0x1D, pressed=False)


def _open_target(args: argparse.Namespace) -> tuple[Win32, ProcessReader, dict[str, object]]:
    api = Win32()
    pid = args.pid if args.pid is not None else api.find_pid(TARGET_EXE)
    reader = ProcessReader(api, pid)
    try:
        identity = verify_target(reader)
    except Exception:
        reader.close()
        raise
    return api, reader, identity


def command_probe(args: argparse.Namespace) -> int:
    _, reader, identity = _open_target(args)
    try:
        print(json.dumps({"identity": identity, "state": observe_state(reader)}))
    finally:
        reader.close()
    return 0


def command_observe(args: argparse.Namespace) -> int:
    _, reader, identity = _open_target(args)
    deadline = time.perf_counter() + args.duration
    previous_counter = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"kind": "identity", **identity}) + "\n")
        try:
            while time.perf_counter() < deadline:
                state = observe_state(reader)
                counter = state["enemy_manager_frame"]
                if counter != previous_counter:
                    output.write(json.dumps({"kind": "frame", **state}) + "\n")
                    output.flush()
                    previous_counter = counter
                time.sleep(args.poll_ms / 1000.0)
        finally:
            reader.close()
    return 0


def _require_foreground(api: Win32, pid: int) -> None:
    if api.foreground_pid() != pid:
        raise RuntimeError("TH08 lost foreground; refusing to send or retain keys")


def command_play(args: argparse.Namespace) -> int:
    if not args.armed:
        raise RuntimeError("physical playback requires the explicit --armed flag")
    masks = load_input_masks(args.trace)
    api, reader, identity = _open_target(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = args.output.open("w", encoding="utf-8", newline="\n")
    try:
        initial = observe_state(reader)
        if initial["route_id"] != 2:
            raise RuntimeError(f"route ID {initial['route_id']} is not Sakuya/Remilia route 2")
        if not initial["gameplay_active"]:
            raise RuntimeError("TH08 gameplay update flag is not active")
        if initial["input_current"] & SUPPORTED_INPUT_MASK:
            raise RuntimeError("player input is already held before agent arming")
        _require_foreground(api, reader.pid)

        playback = FrameSynchronizedPlayback(masks, supported_mask=SUPPORTED_INPUT_MASK)
        counter = int(initial["enemy_manager_frame"])
        output.write(json.dumps({"kind": "identity", **identity}) + "\n")
        output.write(json.dumps({"kind": "arm", "counter": counter, "state": initial}) + "\n")
        send_transitions(api, playback.arm(counter))

        last_change = time.perf_counter()
        while True:
            _require_foreground(api, reader.pid)
            current_counter = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
            if current_counter == counter:
                if time.perf_counter() - last_change > args.frame_timeout:
                    raise RuntimeError("target frame counter stopped")
                time.sleep(args.poll_ms / 1000.0)
                continue
            state = observe_state(reader)
            current_counter = int(state["enemy_manager_frame"])
            advance = playback.observe(current_counter, int(state["input_current"]))
            output.write(
                json.dumps(
                    {
                        "kind": "verified_frame",
                        "trace_frame": advance.completed_frame_index,
                        "state": state,
                    }
                )
                + "\n"
            )
            output.flush()
            send_transitions(api, advance.transitions)
            counter = current_counter
            last_change = time.perf_counter()
            if advance.finished:
                break
    finally:
        try:
            release_all(api)
        finally:
            output.close()
            reader.close()
    return 0


def command_tap(args: argparse.Namespace) -> int:
    """Send bounded menu key taps after explicit operator arming."""

    if not args.armed:
        raise RuntimeError("physical menu taps require the explicit --armed flag")
    api, reader, _identity = _open_target(args)
    try:
        _require_foreground(api, reader.pid)
        release_injected_keys(api)
        for name in args.keys:
            _require_foreground(api, reader.pid)
            bit = TAP_NAMES[name]
            send_transitions(api, (InputTransition(bit, True),))
            time.sleep(args.hold_ms / 1000.0)
            send_transitions(api, (InputTransition(bit, False),))
            time.sleep(args.gap_ms / 1000.0)
    finally:
        try:
            release_injected_keys(api)
        finally:
            reader.close()
    return 0


def command_release_inputs(args: argparse.Namespace) -> int:
    """Recover from an interrupted controller without touching game memory."""

    if not args.armed:
        raise RuntimeError("physical input release requires the explicit --armed flag")
    api, reader, _identity = _open_target(args)
    try:
        _require_foreground(api, reader.pid)
        release_injected_keys(api)
    finally:
        reader.close()
    return 0


def command_capture_replay_bombs(args: argparse.Namespace) -> int:
    """Capture replay Bomb edges and accepted starts without screen analysis."""

    if args.fast_forward and not args.armed:
        raise RuntimeError("Ctrl fast-forward requires the explicit --armed flag")
    api, reader, identity = _open_target(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    control_held = False
    try:
        initial = observe_state(reader)
        if initial["route_id"] != 2 or not initial["gameplay_active"]:
            raise RuntimeError("capture requires active route-2 gameplay/replay")
        if initial["input_raw"] & SUPPORTED_INPUT_MASK:
            raise RuntimeError("physical gameplay input is already active")
        if args.fast_forward:
            _require_foreground(api, reader.pid)
            send_scan_key(api, scan_code=0x1D, pressed=True)
            control_held = True

        deadline = time.perf_counter() + args.timeout
        previous_counter = int(initial["enemy_manager_frame"])
        previous_input = int(initial["input_current"])
        previous_bomb_active = int(initial["player"]["bomb_active"])
        previous_bombs = initial["resources"]["bombs"] if initial["resources"] else None
        presses = 0
        starts = 0
        gaps = 0
        termination_reason = "timeout"
        with args.output.open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps({"kind": "identity", **identity}) + "\n")
            output.write(json.dumps({"kind": "initial", "state": initial}) + "\n")
            output.flush()
            while time.perf_counter() < deadline:
                if args.fast_forward:
                    _require_foreground(api, reader.pid)
                counter = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
                if counter == previous_counter:
                    time.sleep(args.poll_ms / 1000.0)
                    continue
                state = observe_state(reader)
                counter = int(state["enemy_manager_frame"])
                delta = counter - previous_counter
                if delta != 1:
                    gaps += 1
                if state["route_id"] != 2 or not state["gameplay_active"]:
                    termination_reason = "gameplay_ended"
                    previous_counter = counter
                    break
                current_input = int(state["input_current"])
                bomb_active = int(state["player"]["bomb_active"])
                bombs = state["resources"]["bombs"] if state["resources"] else None
                kinds: list[str] = []
                if current_input & 0x02 and not previous_input & 0x02:
                    kinds.append("bomb_press")
                    presses += 1
                if bomb_active and not previous_bomb_active:
                    kinds.append("bomb_start")
                    starts += 1
                if bombs != previous_bombs:
                    kinds.append("bomb_stock_change")
                if kinds:
                    output.write(
                        json.dumps(
                            {
                                "kind": "event",
                                "events": kinds,
                                "counter_delta": delta,
                                "state": state,
                            }
                        )
                        + "\n"
                    )
                    output.flush()

                previous_counter = counter
                previous_input = current_input
                previous_bomb_active = bomb_active
                previous_bombs = bombs
                if counter >= args.stop_counter or (
                    presses >= args.expected_presses and counter > args.minimum_stop_counter
                ):
                    termination_reason = "target_reached"
                    break

            output.write(
                json.dumps(
                    {
                        "kind": "summary",
                        "presses": presses,
                        "starts": starts,
                        "counter_gaps": gaps,
                        "last_counter": previous_counter,
                        "termination_reason": termination_reason,
                    }
                )
                + "\n"
            )
    finally:
        if control_held:
            release_injected_keys(api)
        reader.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="emit one read-only state snapshot")
    probe.set_defaults(func=command_probe)

    observe = subparsers.add_parser("observe", help="record read-only frame snapshots")
    observe.add_argument("output", type=Path)
    observe.add_argument("--duration", type=float, default=10.0)
    observe.add_argument("--poll-ms", type=float, default=0.5)
    observe.set_defaults(func=command_observe)

    play = subparsers.add_parser("play", help="play one trace through physical keyboard input")
    play.add_argument("trace", type=Path)
    play.add_argument("output", type=Path)
    play.add_argument("--armed", action="store_true")
    play.add_argument("--poll-ms", type=float, default=0.25)
    play.add_argument("--frame-timeout", type=float, default=0.5)
    play.set_defaults(func=command_play)

    tap = subparsers.add_parser(
        "tap", help="send explicitly armed foreground-only menu key taps"
    )
    tap.add_argument("keys", nargs="+", choices=tuple(TAP_NAMES))
    tap.add_argument("--armed", action="store_true")
    tap.add_argument("--hold-ms", type=float, default=50.0)
    tap.add_argument("--gap-ms", type=float, default=100.0)
    tap.set_defaults(func=command_tap)

    release = subparsers.add_parser(
        "release-inputs",
        help="release every key this bridge may have injected",
    )
    release.add_argument("--armed", action="store_true")
    release.set_defaults(func=command_release_inputs)

    capture = subparsers.add_parser(
        "capture-replay-bombs",
        help="capture route-2 replay Bomb edges from read-only runtime state",
    )
    capture.add_argument("output", type=Path)
    capture.add_argument("--fast-forward", action="store_true")
    capture.add_argument("--armed", action="store_true")
    capture.add_argument("--timeout", type=float, default=900.0)
    capture.add_argument("--poll-ms", type=float, default=0.25)
    capture.add_argument("--expected-presses", type=int, default=5)
    capture.add_argument("--minimum-stop-counter", type=int, default=64086)
    capture.add_argument("--stop-counter", type=int, default=66386)
    capture.set_defaults(func=command_capture_replay_bombs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
