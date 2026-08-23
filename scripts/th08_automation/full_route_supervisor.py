#!/usr/bin/env python3
"""Launch and retain one continuous original-TH08 Route-2 run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from th08_agent_hotkey import AgentHotkey
from th08_automation.full_route_artifacts import (  # noqa: F401
    EXPECTED_ROUTE_STAGES,
    compare_full_dossiers,
    materialize_artifacts as _materialize_artifacts_impl,
    previous_full_dossier as _previous_full_dossier_impl,
    terminal_scene_record as _terminal_scene_record,
    write_compact_full_route_summary,
)
from th08_automation.full_route_menu import (
    TITLE_MODE_GAME_DIFFICULTY,
    TITLE_MODE_GAME_TEAM,
    anchor_game_start as _anchor_game_start_impl,
    confirm_title_mode as _confirm_title_mode_impl,
    retain_game_after_trial,
    validate_team_selection as _validate_team_selection_impl,
)
from th08_automation.practice_menu import (
    MenuTap,
    PracticeDifficulty,
    parse_practice_difficulty,
)
from th08_practice_supervisor import (
    DEFAULT_GAME_DIR,
    DEFAULT_LAUNCH_BAT,
    RUNTIME_REPORT_DIR,
    RUN_NOTE_DIR,
    TITLE_MODE_MAIN,
    _configure_supervisor_api,
    _matching_targets,
    _navigate_title_cursor,
    _read_title_menu_state,
    _stop_batch_process,
    drive_menu_plan,
    ensure_caps_lock_enabled,
    focus_target_window,
    launch_patch_batch,
    monitor_trial,
    resolve_runtime_ecl_static_image,
    terminate_exact_target,
    wait_for_patched_target,
    wait_for_title_menu,
)
from th08_runtime_agent import TARGET_EXE, Win32, release_injected_keys
from th08_live.scale_source_trace import FINAL_B_ECL_STATIC_SHA256


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGENT_DURATION_SECONDS = 4500.0
DEFAULT_TRIAL_TIMEOUT_SECONDS = 4650.0


def anchor_game_start(
    api: Win32,
    pid: int,
    *,
    hold_ms: int,
    tap_gap_ms: int,
) -> tuple[dict[str, int], tuple[MenuTap, ...]]:
    """Preserve the historical supervisor menu-operation patch seams."""

    return _anchor_game_start_impl(
        api,
        pid,
        hold_ms=hold_ms,
        tap_gap_ms=tap_gap_ms,
        drive_plan=drive_menu_plan,
        read_state=_read_title_menu_state,
        title_mode_main=TITLE_MODE_MAIN,
    )


def confirm_title_mode(
    api: Win32,
    pid: int,
    *,
    next_mode: int,
    purpose: str,
    hold_ms: int,
    screen_settle_ms: int,
    timeout_seconds: float,
) -> MenuTap:
    return _confirm_title_mode_impl(
        api,
        pid,
        next_mode=next_mode,
        purpose=purpose,
        hold_ms=hold_ms,
        screen_settle_ms=screen_settle_ms,
        timeout_seconds=timeout_seconds,
        drive_plan=drive_menu_plan,
        wait_for_menu=wait_for_title_menu,
    )


def validate_team_selection(
    api: Win32,
    pid: int,
    *,
    difficulty: PracticeDifficulty,
) -> dict[str, int]:
    """Preserve the historical patch seam for native title-state reads."""

    return _validate_team_selection_impl(
        api,
        pid,
        difficulty=difficulty,
        read_state=_read_title_menu_state,
    )


def _previous_full_dossier(
    current: Path,
    difficulty_key: str = "lunatic",
) -> Path | None:
    return _previous_full_dossier_impl(
        current,
        difficulty_key,
        runtime_report_dir=RUNTIME_REPORT_DIR,
    )


def materialize_artifacts(
    *,
    run_id: str,
    trace: Path,
    completion: dict[str, object],
    difficulty_key: str = "lunatic",
    difficulty_index: int = 3,
) -> dict[str, object]:
    return _materialize_artifacts_impl(
        run_id=run_id,
        trace=trace,
        completion=completion,
        difficulty_key=difficulty_key,
        difficulty_index=difficulty_index,
        root=ROOT,
        runtime_report_dir=RUNTIME_REPORT_DIR,
        run_note_dir=RUN_NOTE_DIR,
    )

def _write_session(path: Path, session: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            session,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def run_trial(args: argparse.Namespace, *, api: Win32) -> str:
    game_dir = args.game_dir.resolve()
    expected_exe = game_dir / TARGET_EXE
    launch_bat = args.launch_bat or game_dir / DEFAULT_LAUNCH_BAT
    runtime_ecl_static_image = resolve_runtime_ecl_static_image(
        args.runtime_ecl_static_image,
        args.runtime_ecl_static_sha256,
    )
    if args.kill_existing:
        if terminate_exact_target(api, expected_exe):
            print("terminated previous verified TH08 process", flush=True)
    elif _matching_targets(api, expected_exe):
        raise RuntimeError("verified TH08 is already running")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    difficulty = args.difficulty
    run_id = (
        f"{difficulty.key}_route2_fullrun_unattended_{timestamp}"
    )
    trace = RUNTIME_REPORT_DIR / f"{run_id}.jsonl"
    session_path = RUNTIME_REPORT_DIR / f"{run_id}.session.json"
    launch_log = RUNTIME_REPORT_DIR / f"{run_id}.launch.log"
    session: dict[str, object] = {
        "schema": "th08-unattended-full-route-session-v1",
        "run_id": run_id,
        "game_dir": str(game_dir),
        "launch_bat": str(launch_bat),
        "difficulty": difficulty.label,
        "difficulty_key": difficulty.key,
        "difficulty_index": difficulty.menu_index,
        "team": "Sakuya/Remilia",
        "route_id": 2,
        "expected_stage_sequence": list(EXPECTED_ROUTE_STAGES),
        "hard_no_bomb": True,
        "finalb_scale_source_authority": (
            args.enable_finalb_scale_source_authority
        ),
        "runtime_ecl_static_image": (
            str(runtime_ecl_static_image)
            if runtime_ecl_static_image is not None
            else None
        ),
        "runtime_ecl_static_sha256": args.runtime_ecl_static_sha256,
        "safety_value_horizon": 0,
        "trace_transform_runtime": False,
        "trace_enemy_mode_transitions": (
            args.trace_enemy_mode_transitions
        ),
        "trace_enemy_lifecycle_events": (
            args.trace_enemy_lifecycle_events
        ),
        "kill_before_saturation": args.kill_before_saturation,
        "ordinary_preexhaustion_authority": (
            args.ordinary_preexhaustion_authority
        ),
        "diagnostic_continue_root_only_scale": (
            args.diagnostic_continue_root_only_scale
        ),
        "viability_audit": False,
        "agent_duration_seconds": args.agent_duration,
        "leave_game_running": args.leave_game_running,
        "started_at": datetime.now().astimezone().isoformat(),
    }
    batch_process: subprocess.Popen[bytes] | None = None
    batch_log = None
    agent: AgentHotkey | None = None
    accepted = False
    try:
        session["caps_lock_changed"] = ensure_caps_lock_enabled(api)
        agent = AgentHotkey(
            expected_difficulty=difficulty.menu_index,
            expected_stage=0,
            terminal_stage=None,
            trace_enemy_mode_transitions=(
                args.trace_enemy_mode_transitions
            ),
            trace_enemy_lifecycle_events=(
                args.trace_enemy_lifecycle_events
            ),
            kill_before_saturation=args.kill_before_saturation,
            ordinary_preexhaustion_authority=(
                args.ordinary_preexhaustion_authority
            ),
            diagnostic_continue_root_only_scale=(
                args.diagnostic_continue_root_only_scale
            ),
            runtime_ecl_static_image=runtime_ecl_static_image,
            runtime_ecl_static_sha256=args.runtime_ecl_static_sha256,
            enable_finalb_scale_source_authority=(
                args.enable_finalb_scale_source_authority
            ),
            safety_value_horizon=0,
            duration_seconds=args.agent_duration,
            detailed_summary=False,
        )
        batch_process, batch_log = launch_patch_batch(
            game_dir=game_dir,
            launch_bat=launch_bat,
            log_path=launch_log,
        )
        pid, identity = wait_for_patched_target(
            api,
            expected_exe=expected_exe,
            timeout_seconds=args.launch_timeout,
        )
        session["target"] = identity
        session["pid"] = pid
        focus_target_window(api, pid, timeout_seconds=args.focus_timeout)
        time.sleep(args.startup_settle)

        menu_trace: list[dict[str, object]] = []
        menu_taps: list[dict[str, object]] = []

        def capture(label: str) -> None:
            menu_trace.append({"label": label, **_read_title_menu_state(api, pid)})
            session["menu_native_trace"] = menu_trace

        def retain(taps: tuple[MenuTap, ...]) -> None:
            menu_taps.extend(asdict(tap) for tap in taps)
            session["executed_menu_taps"] = menu_taps

        transition_timeout = max(
            3.0,
            args.screen_settle_ms / 1000.0 + 1.0,
        )
        wait_for_title_menu(
            api,
            pid,
            mode=TITLE_MODE_MAIN,
            timeout_seconds=transition_timeout,
        )
        capture("main")
        _state, taps = anchor_game_start(
            api,
            pid,
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
        )
        retain(taps)
        capture("game_start_selected")
        tap = confirm_title_mode(
            api,
            pid,
            next_mode=TITLE_MODE_GAME_DIFFICULTY,
            purpose="enter Game Start",
            hold_ms=args.tap_hold_ms,
            screen_settle_ms=args.screen_settle_ms,
            timeout_seconds=transition_timeout,
        )
        retain((tap,))
        capture("difficulty_screen_entered")
        _state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_GAME_DIFFICULTY,
            target=difficulty.menu_index,
            option_count=4,
            purpose=f"select {difficulty.label}",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
        )
        retain(taps)
        capture(f"{difficulty.key}_selected")
        tap = confirm_title_mode(
            api,
            pid,
            next_mode=TITLE_MODE_GAME_TEAM,
            purpose=f"accept native-verified {difficulty.label}",
            hold_ms=args.tap_hold_ms,
            screen_settle_ms=args.screen_settle_ms,
            timeout_seconds=transition_timeout,
        )
        retain((tap,))
        capture("team_screen_entered")
        _state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_GAME_TEAM,
            target=2,
            option_count=4,
            purpose="select Sakuya/Remilia",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
            direction_key="right",
        )
        retain(taps)
        capture("team_selected")
        session["menu_native_state"] = validate_team_selection(
            api,
            pid,
            difficulty=difficulty,
        )

        agent.arm(output_path=trace)
        session["agent_armed_at"] = datetime.now().astimezone().isoformat()
        monitor_trial(
            agent,
            trace=trace,
            timeout_seconds=args.trial_timeout,
            status_seconds=args.status_seconds,
            stall_timeout_seconds=args.stall_timeout,
        )
        session["agent_summary"] = agent.last_summary
        accepted = bool(
            isinstance(agent.last_summary, dict)
            and agent.last_summary.get("termination_reason")
            == "route_complete"
        )
        session["trial_accepted"] = accepted
        if not accepted:
            raise RuntimeError(
                "full route did not terminate with route_complete: "
                f"{agent.last_summary}"
            )
        completion = _terminal_scene_record(trace)
        session["completion_scene"] = completion
        if retain_game_after_trial(
            accepted=accepted,
            leave_game_running=args.leave_game_running,
        ):
            release_injected_keys(api)
            agent.close()
            agent = None
            session["game_terminated_after_trial"] = False
            session["game_left_running_after_trial"] = True
            session["input_released_before_handoff"] = True
            print(
                "GAME LEFT RUNNING: automation stopped and all injected "
                "keys were released; no post-route save choice or process "
                "termination was issued.",
                flush=True,
            )
        else:
            session["game_terminated_after_trial"] = (
                terminate_exact_target(api, expected_exe)
            )
            session["game_left_running_after_trial"] = False
        session["status"] = "completed_pending_artifacts"
        session["finished_at"] = datetime.now().astimezone().isoformat()
        _write_session(session_path, session)
        session["artifacts"] = materialize_artifacts(
            run_id=run_id,
            trace=trace,
            completion=completion,
            difficulty_key=difficulty.key,
            difficulty_index=difficulty.menu_index,
        )
        session["status"] = "completed"
        session["finished_at"] = datetime.now().astimezone().isoformat()
        _write_session(session_path, session)
        print(f"full-route artifacts: {session['artifacts']}", flush=True)
        return run_id
    except Exception as exc:
        session["trial_accepted"] = accepted
        session["status"] = (
            "completed_pending_artifacts"
            if accepted
            else ("discarded" if trace.exists() else "failed")
        )
        session["finished_at"] = datetime.now().astimezone().isoformat()
        session["error_type"] = type(exc).__name__
        session["error"] = str(exc)
        _write_session(session_path, session)
        raise
    finally:
        if agent is not None:
            if agent.agent_thread is not None and agent.agent_thread.is_alive():
                agent.stop()
                agent.agent_thread.join(timeout=15.0)
            agent.close()
        try:
            release_injected_keys(api)
        except OSError:
            pass
        if not retain_game_after_trial(
            accepted=accepted,
            leave_game_running=args.leave_game_running,
        ):
            terminate_exact_target(api, expected_exe)
        _stop_batch_process(batch_process)
        if batch_log is not None:
            batch_log.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-dir",
        type=Path,
        default=(
            type(DEFAULT_GAME_DIR)(os.environ["TH08_GAME_DIR"])
            if "TH08_GAME_DIR" in os.environ
            else DEFAULT_GAME_DIR
        ),
    )
    parser.add_argument("--launch-bat", type=Path)
    parser.add_argument("--launch-timeout", type=float, default=25.0)
    parser.add_argument("--focus-timeout", type=float, default=10.0)
    parser.add_argument("--startup-settle", type=float, default=1.0)
    parser.add_argument("--tap-hold-ms", type=int, default=65)
    parser.add_argument("--tap-gap-ms", type=int, default=180)
    parser.add_argument("--screen-settle-ms", type=int, default=700)
    parser.add_argument(
        "--agent-duration",
        type=float,
        default=DEFAULT_AGENT_DURATION_SECONDS,
    )
    parser.add_argument(
        "--trial-timeout",
        type=float,
        default=DEFAULT_TRIAL_TIMEOUT_SECONDS,
    )
    parser.add_argument("--stall-timeout", type=float, default=120.0)
    parser.add_argument("--status-seconds", type=float, default=30.0)
    parser.add_argument(
        "--trace-enemy-mode-transitions",
        action="store_true",
        help=(
            "frame-bracket player mode and first-64 enemy flags for the "
            "complete route; no mode-conditioned action authority, but "
            "trace cost may perturb cadence"
        ),
    )
    parser.add_argument(
        "--trace-enemy-lifecycle-events",
        action="store_true",
        help=(
            "install the reversible bounded ordinary-enemy lifecycle ring "
            "for the complete route; trace only, no action authority"
        ),
    )
    parser.add_argument(
        "--kill-before-saturation",
        action="store_true",
        help=(
            "enable observed ordinary-enemy target alignment/unfocus as a "
            "fresh-certified objective preference"
        ),
    )
    parser.add_argument(
        "--ordinary-preexhaustion-authority",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "enable the signed ordinary prepublication predecessor; "
            "incomplete future birth/event coverage remains fail-closed"
        ),
    )
    parser.add_argument(
        "--diagnostic-continue-root-only-scale",
        action="store_true",
        help=(
            "continue a whole-route diagnostic under an explicitly "
            "unknown-direction constant-current-root time-scale proxy"
        ),
    )
    parser.add_argument(
        "--runtime-ecl-static-image",
        type=Path,
        help="decoded ecldata7 image for the Final-B scale-source gate",
    )
    parser.add_argument(
        "--runtime-ecl-static-sha256",
        help="required immutable SHA-256 for --runtime-ecl-static-image",
    )
    parser.add_argument(
        "--enable-finalb-scale-source-authority",
        action="store_true",
        help=(
            "carry the exact Final-B scale schedule through the complete "
            "original Game Start route"
        ),
    )
    parser.add_argument(
        "--difficulty",
        type=parse_practice_difficulty,
        default=parse_practice_difficulty("lunatic"),
        metavar="{easy,normal,hard,lunatic}",
        help="original Game Start difficulty; defaults to lunatic",
    )
    parser.add_argument(
        "--leave-game-running",
        action="store_true",
        help=(
            "after accepted route completion, release injected keys but do "
            "not choose a save option or terminate the verified game"
        ),
    )
    parser.add_argument(
        "--refuse-existing",
        action="store_false",
        dest="kill_existing",
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="required acknowledgement for unattended physical input/process control",
    )
    parser.set_defaults(kill_existing=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.name != "nt":
        raise RuntimeError(
            "th08_full_route_supervisor.py requires Windows Python"
        )
    if not args.armed:
        raise RuntimeError("unattended physical control requires --armed")
    if min(
        args.launch_timeout,
        args.focus_timeout,
        args.startup_settle,
        args.agent_duration,
        args.trial_timeout,
        args.stall_timeout,
        args.status_seconds,
    ) <= 0.0:
        raise ValueError("supervisor timing arguments must be positive")
    if args.trial_timeout <= args.agent_duration:
        raise ValueError("trial timeout must exceed the agent duration")
    if args.enable_finalb_scale_source_authority and (
        args.difficulty.menu_index != 3
        or args.runtime_ecl_static_image is None
        or args.runtime_ecl_static_sha256 != FINAL_B_ECL_STATIC_SHA256
    ):
        raise ValueError(
            "full-route Final-B scale authority requires Lunatic and the "
            "exact ecldata7 identity"
        )
    if (
        args.diagnostic_continue_root_only_scale
        and not (
            args.trace_enemy_mode_transitions
        )
    ):
        raise ValueError(
            "diagnostic root-only scale continuation is scoped to the "
            "whole-route enemy-mode observer"
        )
    if (
        args.diagnostic_continue_root_only_scale
        and args.enable_finalb_scale_source_authority
    ):
        raise ValueError(
            "diagnostic root-only scale continuation conflicts with exact "
            "Final-B scale-source authority"
        )
    api = Win32()
    _configure_supervisor_api(api)
    run_id = run_trial(args, api=api)
    print(f"completed full route: {run_id}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
