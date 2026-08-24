#!/usr/bin/env python3
"""Implement supervised original-game TH08 Practice Start trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from th08_agent_hotkey import AgentHotkey
from th08_automation.agent_contract import LONG_RUN_DURATION_SECONDS
from th08_automation.practice_artifacts import (
    TrialArtifacts,
    materialize_artifacts as _materialize_artifacts,
    previous_dossier as _select_previous_dossier,
)
from th08_automation.practice_menu import (
    MenuTap,
    PracticeDifficulty,
    PracticeStage,
    build_practice_menu_plan,
    parse_practice_difficulty,
    parse_practice_stage,
)
from th08_automation.practice_monitor import (  # noqa: F401
    accepted_practice_termination,
    monitor_trial,
    progress_text as _progress_text,
    read_last_json_record,
)
from th08_automation.practice_replay_save import (
    save_completed_practice_replay,
)
from th08_automation.practice_native_menu import (  # noqa: F401
    ADDR_PRACTICE_STAGE_AVAILABILITY,
    ADDR_TITLE_DIFFICULTY_CURSOR,
    ADDR_TITLE_MENU_MANAGER,
    TITLE_CURSOR_OFFSET,
    TITLE_MODE_MAIN,
    TITLE_MODE_OFFSET,
    TITLE_MODE_PRACTICE_DIFFICULTY,
    TITLE_MODE_PRACTICE_STAGE,
    TITLE_MODE_PRACTICE_TEAM,
    TITLE_SCREEN_AGE_OFFSET,
    TITLE_SUBSTATE_OFFSET,
    confirm_title_menu as _confirm_title_menu,
    navigate_title_cursor as _navigate_title_cursor,
    practice_stage_available,
    read_menu_selection as _read_menu_selection,
    read_title_menu_state as _read_title_menu_state,
    validate_practice_selection as _validate_practice_selection_impl,
    wait_for_title_menu,
)
from th08_automation.practice_windows import (  # noqa: F401
    WNDENUMPROC,
    build_patch_batch_command,
    configure_supervisor_api as _configure_supervisor_api,
    drive_menu_plan,
    focus_target_window,
    launch_patch_batch,
    matching_targets as _matching_targets,
    same_path as _same_path,
    target_windows as _target_windows,
    terminate_exact_target,
    wait_for_patched_target,
)
from th08_runtime_agent import TARGET_EXE, Win32, release_injected_keys


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_REPORT_DIR = ROOT / "artifacts" / "runtime_reports"
RUN_NOTE_DIR = ROOT / "notes" / "runs"
REPLAY_ARCHIVE_DIR = ROOT / "artifacts" / "replays" / "archive"
DEFAULT_GAME_DIR = (
    Path("D:/Entertainment/Game/Touhou")
    / "[th08] \u4e1c\u65b9\u6c38\u591c\u6284 (\u65e5\u6587\u7248)"
)
DEFAULT_LAUNCH_BAT = "run_th08_no_life_decrement_attach.bat"


def resolve_runtime_ecl_static_image(
    path: Path | None,
    expected_sha256: str | None,
) -> Path | None:
    """Validate immutable ECL input before any game or process side effect."""

    if (path is None) != (expected_sha256 is None):
        raise ValueError(
            "runtime ECL identity requires both a static image and SHA-256"
        )
    if path is None:
        return None
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"runtime ECL static image is not readable: {path}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(
            f"runtime ECL static image is not a file: {resolved}"
        )
    actual_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
    assert expected_sha256 is not None
    if actual_sha256 != expected_sha256.lower():
        raise ValueError(
            "runtime ECL static image SHA-256 mismatch: "
            f"expected {expected_sha256.lower()}, observed {actual_sha256}"
        )
    return resolved


def select_no_save_before_termination(
    api: Win32,
    pid: int,
    *,
    hold_ms: int,
    tap_gap_ms: int,
) -> dict[str, object]:
    """Move the completed-stage save prompt to No; cleanup kills immediately."""

    result: dict[str, object] = {"attempted": True, "key": "right"}
    try:
        focus_target_window(api, pid, timeout_seconds=1.0)
        tap = MenuTap("right", "post-stage do not save", tap_gap_ms)
        drive_menu_plan(api, pid, (tap,), hold_ms=hold_ms)
        result["sent"] = True
    except (OSError, RuntimeError, TimeoutError) as exc:
        result["sent"] = False
        result["error"] = str(exc)
    return result


def _previous_dossier(
    stage: PracticeStage,
    current: Path,
    difficulty_key: str = "lunatic",
) -> Path | None:
    return _select_previous_dossier(
        stage,
        current,
        runtime_report_dir=RUNTIME_REPORT_DIR,
        difficulty_key=difficulty_key,
    )


def materialize_artifacts(
    *,
    run_id: str,
    stage: PracticeStage,
    difficulty: PracticeDifficulty,
    trace: Path,
    session_json: Path,
    compare_to_baseline: bool = True,
) -> TrialArtifacts:
    return _materialize_artifacts(
        run_id=run_id,
        stage=stage,
        difficulty=difficulty,
        trace=trace,
        session_json=session_json,
        runtime_report_dir=RUNTIME_REPORT_DIR,
        run_note_dir=RUN_NOTE_DIR,
        compare_to_baseline=compare_to_baseline,
    )


def _validate_practice_selection(
    api: Win32,
    pid: int,
    *,
    stage: PracticeStage,
    difficulty: PracticeDifficulty,
) -> dict[str, int]:
    """Preserve the historical patch seam for native title-state reads."""

    return _validate_practice_selection_impl(
        api,
        pid,
        stage=stage,
        difficulty=difficulty,
        read_state=_read_title_menu_state,
    )


def _stop_batch_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def run_trial(
    args: argparse.Namespace,
    *,
    api: Win32,
    stage: PracticeStage,
    iteration: int,
) -> TrialArtifacts:
    runtime_ecl_static_image = resolve_runtime_ecl_static_image(
        args.runtime_ecl_static_image,
        args.runtime_ecl_static_sha256,
    )
    game_dir = args.game_dir.resolve()
    expected_exe = game_dir / TARGET_EXE
    launch_bat = args.launch_bat or game_dir / DEFAULT_LAUNCH_BAT
    if args.kill_existing:
        if terminate_exact_target(api, expected_exe):
            print("terminated previous verified TH08 process", flush=True)
    elif _matching_targets(api, expected_exe):
        raise RuntimeError("verified TH08 is already running")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    difficulty = args.difficulty
    run_kind = "unattended"
    run_id = (
        f"{difficulty.key}_route2_stage{stage.key}_{run_kind}_{timestamp}"
    )
    trace = RUNTIME_REPORT_DIR / f"{run_id}.jsonl"
    session_json = RUNTIME_REPORT_DIR / f"{run_id}.session.json"
    launch_log = RUNTIME_REPORT_DIR / f"{run_id}.launch.log"
    menu_plan = build_practice_menu_plan(
        stage,
        tap_gap_ms=args.tap_gap_ms,
        screen_settle_ms=args.screen_settle_ms,
        difficulty=difficulty,
    )
    session: dict[str, object] = {
        "schema": "th08-unattended-practice-session-v1",
        "run_id": run_id,
        "iteration": iteration,
        "stage": asdict(stage),
        "difficulty": asdict(difficulty),
        "game_dir": str(game_dir),
        "launch_bat": str(launch_bat),
        "menu_plan": [asdict(tap) for tap in menu_plan],
        "hard_no_bomb": True,
        "trace_transform_runtime": args.trace_transform_runtime,
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
        "runtime_ecl_static_image": (
            str(runtime_ecl_static_image)
            if runtime_ecl_static_image is not None
            else None
        ),
        "runtime_ecl_static_sha256": (
            args.runtime_ecl_static_sha256
        ),
        "viability_audit": args.viability_audit,
        "input_clock_boundary_shadow": (
            args.input_clock_boundary_shadow
        ),
        "input_clock_shadow_sample_ms": (
            args.input_clock_shadow_sample_ms
        ),
        "local_pipeline_root_shadow_every": (
            args.local_pipeline_root_shadow_every
        ),
        "local_hazard_backend": args.local_hazard_backend,
        "local_beam_reducer": args.local_beam_reducer,
        "bullet_decode_backend": args.bullet_decode_backend,
        "agent_duration_seconds": args.agent_duration,
        "trial_timeout_seconds": args.trial_timeout,
        "save_replay_slot": args.save_replay_slot,
        "replay_save_timeout": args.replay_save_timeout,
        "caps_lock_bootstrap": {
            "required": False,
            "reason": "direct supervisor arm has no Caps Lock dependency",
        },
        "started_at": datetime.now().astimezone().isoformat(),
    }
    batch_process: subprocess.Popen[bytes] | None = None
    batch_log = None
    agent: AgentHotkey | None = None
    try:
        agent = AgentHotkey(
            expected_difficulty=difficulty.menu_index,
            expected_stage=stage.route_index,
            terminal_stage=stage.route_index,
            trace_transform_runtime=args.trace_transform_runtime,
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
            safety_value_horizon=args.safety_value_horizon,
            viability_audit_dir=(
                ROOT
                / "artifacts"
                / "viability_audit"
                / "raw"
                / run_id
                if args.viability_audit
                else None
            ),
            input_clock_boundary_shadow=(
                args.input_clock_boundary_shadow
            ),
            input_clock_shadow_sample_ms=(
                args.input_clock_shadow_sample_ms
            ),
            local_pipeline_root_shadow_every=(
                args.local_pipeline_root_shadow_every
            ),
            local_hazard_backend=args.local_hazard_backend,
            local_beam_reducer=args.local_beam_reducer,
            bullet_decode_backend=args.bullet_decode_backend,
            duration_seconds=args.agent_duration,
            detailed_summary=True,
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
        menu_native_trace: list[dict[str, object]] = []
        executed_menu_taps: list[dict[str, object]] = []

        def capture_menu_state(label: str) -> dict[str, int]:
            state = _read_title_menu_state(api, pid)
            menu_native_trace.append({"label": label, **state})
            session["menu_native_trace"] = menu_native_trace
            return state

        def retain_taps(taps: tuple[MenuTap, ...] | list[MenuTap]) -> None:
            executed_menu_taps.extend(asdict(tap) for tap in taps)
            session["executed_menu_taps"] = executed_menu_taps

        transition_timeout = max(3.0, args.screen_settle_ms / 1000.0 + 1.0)
        wait_for_title_menu(
            api,
            pid,
            mode=TITLE_MODE_MAIN,
            timeout_seconds=transition_timeout,
        )
        state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_MAIN,
            target=3,
            option_count=9,
            purpose="select Practice Start",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps(taps)
        capture_menu_state("practice_start_selected")
        tap = _confirm_title_menu(
            api,
            pid,
            next_mode=TITLE_MODE_PRACTICE_DIFFICULTY,
            purpose="enter Practice Start",
            hold_ms=args.tap_hold_ms,
            screen_settle_ms=args.screen_settle_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps((tap,))
        capture_menu_state("difficulty_screen_entered")
        state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_PRACTICE_DIFFICULTY,
            target=difficulty.menu_index,
            option_count=4,
            purpose=f"select {difficulty.label}",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps(taps)
        capture_menu_state("difficulty_selected")
        tap = _confirm_title_menu(
            api,
            pid,
            next_mode=TITLE_MODE_PRACTICE_TEAM,
            purpose=f"accept native-verified {difficulty.label}",
            hold_ms=args.tap_hold_ms,
            screen_settle_ms=args.screen_settle_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps((tap,))
        capture_menu_state("team_screen_entered")
        state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_PRACTICE_TEAM,
            target=2,
            option_count=4,
            purpose="select Sakuya/Remilia",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
            direction_key="right",
        )
        retain_taps(taps)
        capture_menu_state("team_selected")
        tap = _confirm_title_menu(
            api,
            pid,
            next_mode=TITLE_MODE_PRACTICE_STAGE,
            purpose="accept native-verified Sakuya/Remilia",
            hold_ms=args.tap_hold_ms,
            screen_settle_ms=args.screen_settle_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps((tap,))
        capture_menu_state("stage_screen_entered")
        state, taps = _navigate_title_cursor(
            api,
            pid,
            mode=TITLE_MODE_PRACTICE_STAGE,
            target=stage.menu_index,
            option_count=8,
            purpose=f"select {stage.label}",
            hold_ms=args.tap_hold_ms,
            tap_gap_ms=args.tap_gap_ms,
            timeout_seconds=transition_timeout,
        )
        retain_taps(taps)
        capture_menu_state("stage_selected")
        session["menu_native_state"] = _validate_practice_selection(
            api,
            pid,
            stage=stage,
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
        accepted = accepted_practice_termination(agent.last_summary)
        session["trial_accepted"] = accepted
        session["acceptance_scope"] = "complete_practice_stage"
        if not args.leave_game_running:
            if (
                accepted
                and args.save_replay_slot is not None
            ):
                session["post_stage_replay_save"] = (
                    save_completed_practice_replay(
                        api,
                        pid,
                        game_dir=game_dir,
                        slot=args.save_replay_slot,
                        archive_dir=REPLAY_ARCHIVE_DIR,
                        expected_route_id=2,
                        expected_difficulty_index=difficulty.menu_index,
                        expected_stage_route_index=stage.route_index,
                        hold_ms=args.tap_hold_ms,
                        tap_gap_ms=args.tap_gap_ms,
                        timeout_seconds=args.replay_save_timeout,
                    )
                )
                session["post_stage_no_save"] = {
                    "attempted": False,
                    "reason": "accepted replay was saved and verified",
                }
            elif accepted:
                session["post_stage_no_save"] = (
                    select_no_save_before_termination(
                        api,
                        pid,
                        hold_ms=args.tap_hold_ms,
                        tap_gap_ms=args.tap_gap_ms,
                    )
                )
            else:
                session["post_stage_no_save"] = {
                    "attempted": False,
                    "reason": "trial did not terminate with route_complete",
                }
            session["game_terminated_after_trial"] = terminate_exact_target(
                api,
                expected_exe,
            )
        session["finished_at"] = datetime.now().astimezone().isoformat()
        session["status"] = "completed" if accepted else "discarded"
        session_json.write_text(
            json.dumps(
                session,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        artifacts = materialize_artifacts(
            run_id=run_id,
            stage=stage,
            difficulty=difficulty,
            trace=trace,
            session_json=session_json,
            compare_to_baseline=True,
        )
        print(f"trial artifacts: {artifacts.dossier_markdown}", flush=True)
        return artifacts
    except Exception as exc:
        session["finished_at"] = datetime.now().astimezone().isoformat()
        session["status"] = "failed"
        session["error_type"] = type(exc).__name__
        session["error"] = str(exc)
        session_json.parent.mkdir(parents=True, exist_ok=True)
        session_json.write_text(
            json.dumps(
                session,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
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
        if not args.leave_game_running:
            terminate_exact_target(api, expected_exe)
        _stop_batch_process(batch_process)
        if batch_log is not None:
            batch_log.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        type=parse_practice_stage,
        default=parse_practice_stage("1"),
        metavar="{1,2,3,4a,4b,5,6a,6b}",
    )
    parser.add_argument(
        "--difficulty",
        type=parse_practice_difficulty,
        default=parse_practice_difficulty("lunatic"),
        metavar="{easy,normal,hard,lunatic}",
        help="Practice Start difficulty; defaults to lunatic",
    )
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
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--launch-timeout", type=float, default=25.0)
    parser.add_argument("--focus-timeout", type=float, default=10.0)
    parser.add_argument("--startup-settle", type=float, default=1.0)
    parser.add_argument("--tap-hold-ms", type=int, default=65)
    parser.add_argument("--tap-gap-ms", type=int, default=180)
    parser.add_argument("--screen-settle-ms", type=int, default=700)
    parser.add_argument(
        "--replay-save-timeout",
        type=float,
        default=20.0,
        help="native-state wait deadline for an accepted replay save",
    )
    parser.add_argument(
        "--agent-duration",
        type=float,
        default=float(LONG_RUN_DURATION_SECONDS),
        help="maximum live-agent duration in seconds",
    )
    parser.add_argument("--trial-timeout", type=float, default=4500.0)
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=120.0,
        help="stop and kill when the runtime trace makes no progress",
    )
    parser.add_argument("--status-seconds", type=float, default=30.0)
    parser.add_argument(
        "--trace-transform-runtime",
        action="store_true",
        help="retain transform-relevant bullets from the complete native pool",
    )
    parser.add_argument(
        "--trace-enemy-mode-transitions",
        action="store_true",
        help=(
            "frame-bracket player mode and first-64 enemy flags for the "
            "whole stage; no mode-conditioned action authority, but trace "
            "cost may perturb cadence"
        ),
    )
    parser.add_argument(
        "--trace-enemy-lifecycle-events",
        action="store_true",
        help=(
            "install the reversible bounded ordinary-enemy lifecycle ring "
            "for the whole stage; trace only, no action authority"
        ),
    )
    parser.add_argument(
        "--kill-before-saturation",
        action="store_true",
        help=(
            "enable the default-off ordinary-enemy pre-exhaustion "
            "target-alignment/unfocus preference inside the fresh "
            "certified issue action set"
        ),
    )
    parser.add_argument(
        "--ordinary-preexhaustion-authority",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "enable the default-off signed ordinary prepublication "
            "predecessor; incomplete future birth/event coverage remains "
            "fail-closed"
        ),
    )
    parser.add_argument(
        "--diagnostic-continue-root-only-scale",
        action="store_true",
        help=(
            "continue a whole-stage diagnostic under an explicitly "
            "unknown-direction constant-current-root time-scale proxy"
        ),
    )
    parser.add_argument(
        "--runtime-ecl-static-image",
        type=Path,
        help=(
            "decoded static ECL image for one default-off post-issue "
            "runtime byte-identity observation"
        ),
    )
    parser.add_argument(
        "--runtime-ecl-static-sha256",
        help="required immutable SHA-256 for --runtime-ecl-static-image",
    )
    parser.add_argument(
        "--safety-value-horizon",
        type=int,
        default=0,
        help=(
            "enable the compact max-min empty-kernel preference for this "
            "many game frames"
        ),
    )
    parser.add_argument(
        "--viability-audit",
        action="store_true",
        help=(
            "retain ignored neutral policy capsules for offline "
            "multi-resolution audit; do not treat timing as a baseline"
        ),
    )
    parser.add_argument(
        "--input-clock-boundary-shadow",
        action="store_true",
        help=(
            "record native FRScreen/input/player clock-boundary telemetry; "
            "never changes input, epochs, estimator state, or policies"
        ),
    )
    parser.add_argument(
        "--input-clock-shadow-sample-ms",
        type=float,
        default=1.0,
        help=(
            "minimum repeated-frame telemetry sampling cadence; never used "
            "as a semantic classifier"
        ),
    )
    parser.add_argument(
        "--local-pipeline-root-shadow-every",
        type=int,
        default=0,
        metavar="DECISIONS",
        help=(
            "sample a late explicit-root local certificate after input every "
            "N decisions; zero disables it and sampled work may perturb the "
            "next cadence"
        ),
    )
    parser.add_argument(
        "--local-hazard-backend",
        choices=("numpy", "native"),
        default="native",
        help=(
            "select the local hazard-query implementation; parity-gated "
            "native is the default and numpy is the reference rollback"
        ),
    )
    parser.add_argument(
        "--local-beam-reducer",
        choices=("python", "native"),
        default="native",
        help=(
            "select quantized local beam reduction; parity-gated native is "
            "the default and python is the reference rollback"
        ),
    )
    parser.add_argument(
        "--bullet-decode-backend",
        choices=("python", "native"),
        default="native",
        help=(
            "select planning bullet decode; parity-gated native packed "
            "snapshots are the default and Python objects are the reference "
            "rollback"
        ),
    )
    parser.add_argument(
        "--refuse-existing",
        action="store_false",
        dest="kill_existing",
        help="fail instead of terminating a verified existing TH08 process",
    )
    parser.add_argument("--leave-game-running", action="store_true")
    parser.add_argument(
        "--save-replay-slot",
        type=int,
        choices=range(1, 16),
        metavar="1..15",
        help=(
            "after one accepted complete practice, archive and overwrite the "
            "exact replay slot, then decode/identity/no-Bomb verify it"
        ),
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
        raise RuntimeError("th08_practice_supervisor.py requires Windows Python")
    if not args.armed:
        raise RuntimeError("unattended physical control requires --armed")
    if args.repeat <= 0:
        raise ValueError("--repeat must be positive")
    if args.replay_save_timeout <= 0.0:
        raise ValueError("--replay-save-timeout must be positive")
    if args.save_replay_slot is not None and (
        args.leave_game_running or args.forever or args.repeat != 1
    ):
        raise ValueError(
            "--save-replay-slot requires one supervised iteration and cannot "
            "be combined with --leave-game-running or --forever"
        )
    if args.safety_value_horizon < 0:
        raise ValueError("--safety-value-horizon cannot be negative")
    if args.input_clock_shadow_sample_ms <= 0.0:
        raise ValueError(
            "--input-clock-shadow-sample-ms must be positive"
        )
    if args.local_pipeline_root_shadow_every < 0:
        raise ValueError(
            "--local-pipeline-root-shadow-every cannot be negative"
        )
    if (args.runtime_ecl_static_image is None) != (
        args.runtime_ecl_static_sha256 is None
    ):
        raise ValueError(
            "runtime ECL identity requires both a static image and SHA-256"
        )
    if min(
        args.cooldown,
        args.launch_timeout,
        args.focus_timeout,
        args.startup_settle,
        args.trial_timeout,
        args.stall_timeout,
        args.status_seconds,
    ) <= 0:
        raise ValueError("supervisor timing arguments must be positive")
    api = Win32()
    _configure_supervisor_api(api)
    iteration = 0
    try:
        while args.forever or iteration < args.repeat:
            iteration += 1
            artifacts = run_trial(
                args,
                api=api,
                stage=args.stage,
                iteration=iteration,
            )
            print(
                f"completed iteration {iteration}: {artifacts.run_id}",
                flush=True,
            )
            if args.forever or iteration < args.repeat:
                time.sleep(args.cooldown)
    except KeyboardInterrupt:
        print("supervisor interrupted; inputs released", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
