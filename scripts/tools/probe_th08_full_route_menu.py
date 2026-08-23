#!/usr/bin/env python3
"""Probe native normal-Game-Start menu modes without entering gameplay."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from th08_automation.practice_menu import MenuTap
from th08_full_route_supervisor import anchor_game_start
from th08_practice_supervisor import (
    DEFAULT_GAME_DIR,
    DEFAULT_LAUNCH_BAT,
    RUNTIME_REPORT_DIR,
    TITLE_MODE_MAIN,
    _configure_supervisor_api,
    _navigate_title_cursor,
    _read_title_menu_state,
    _stop_batch_process,
    drive_menu_plan,
    ensure_caps_lock_enabled,
    focus_target_window,
    launch_patch_batch,
    terminate_exact_target,
    wait_for_patched_target,
    wait_for_title_menu,
)
from th08_runtime_agent import Win32, release_injected_keys


def _confirm_and_observe(
    api: Win32,
    pid: int,
    *,
    previous_mode: int,
    purpose: str,
    timeout_seconds: float = 4.0,
) -> dict[str, int]:
    drive_menu_plan(
        api,
        pid,
        (MenuTap("confirm", purpose, 700),),
        hold_ms=65,
    )
    deadline = time.perf_counter() + timeout_seconds
    last = None
    while time.perf_counter() < deadline:
        last = _read_title_menu_state(api, pid)
        if last["mode"] != previous_mode and last["substate"] == 1:
            return last
        time.sleep(0.02)
    raise TimeoutError(
        f"menu did not leave mode {previous_mode}; last={last}"
    )


def main() -> int:
    api = Win32()
    _configure_supervisor_api(api)
    game_dir = DEFAULT_GAME_DIR.resolve()
    expected_exe = game_dir / "th08.exe"
    launch_bat = game_dir / DEFAULT_LAUNCH_BAT
    batch_process = None
    batch_log = None
    states = []
    try:
        terminate_exact_target(api, expected_exe)
        batch_process, batch_log = launch_patch_batch(
            game_dir=game_dir,
            launch_bat=launch_bat,
            log_path=RUNTIME_REPORT_DIR / "full_route_menu_probe.launch.log",
        )
        pid, _identity = wait_for_patched_target(
            api,
            expected_exe=expected_exe,
            timeout_seconds=25.0,
        )
        focus_target_window(api, pid, timeout_seconds=10.0)
        ensure_caps_lock_enabled(api)
        time.sleep(1.0)
        states.append(
            {
                "label": "main",
                **wait_for_title_menu(
                    api,
                    pid,
                    mode=TITLE_MODE_MAIN,
                    timeout_seconds=3.0,
                ),
            }
        )
        state, _taps = anchor_game_start(
            api,
            pid,
            hold_ms=65,
            tap_gap_ms=180,
        )
        states.append({"label": "game_start_selected", **state})
        difficulty = _confirm_and_observe(
            api,
            pid,
            previous_mode=TITLE_MODE_MAIN,
            purpose="enter Game Start",
        )
        states.append({"label": "difficulty", **difficulty})
        state, _taps = _navigate_title_cursor(
            api,
            pid,
            mode=difficulty["mode"],
            target=3,
            option_count=4,
            purpose="select Lunatic",
            hold_ms=65,
            tap_gap_ms=180,
            timeout_seconds=4.0,
        )
        states.append({"label": "lunatic_selected", **state})
        team = _confirm_and_observe(
            api,
            pid,
            previous_mode=difficulty["mode"],
            purpose="accept Lunatic",
        )
        states.append({"label": "team", **team})
        state, _taps = _navigate_title_cursor(
            api,
            pid,
            mode=team["mode"],
            target=2,
            option_count=4,
            purpose="select Sakuya/Remilia",
            hold_ms=65,
            tap_gap_ms=180,
            timeout_seconds=4.0,
            direction_key="right",
        )
        states.append({"label": "team_selected", **state})
        print(json.dumps(states, indent=2), flush=True)
        return 0
    finally:
        try:
            release_injected_keys(api)
        except OSError:
            pass
        terminate_exact_target(api, expected_exe)
        _stop_batch_process(batch_process)
        if batch_log is not None:
            batch_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
