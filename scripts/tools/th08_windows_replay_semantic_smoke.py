#!/usr/bin/env python3
"""Capture a bounded retail-TH08 replay spine at exact calc-chain roots."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from th08_automation.finalb_replay_observer import (
    NativeReplayStageContract,
    drive_native_stage_replay_menu,
    validate_native_stage_replay,
    wait_for_bound_replay_gameplay,
)
from th08_automation.practice_supervisor import _stop_batch_process
from th08_automation.practice_windows import (
    configure_supervisor_api,
    focus_target_window,
    launch_patch_batch,
    matching_targets,
    terminate_exact_target,
    wait_for_patched_target,
)
from th08_linux import (
    MANAGER_FRAME_TRANSITION_SAME,
    canonical_fingerprint_bytes,
    capture_runtime_semantic_spine,
    classify_manager_frame_transition,
    enrich_with_collision_control_projection,
    enrich_with_effect_lifecycle_summary,
    partial_semantic_trace_path,
    replay_stage_binding_mismatch,
    replay_stage_terminal_reason,
    write_semantic_trace,
)
from th08_runtime.game_state import TARGET_EXE
from th08_runtime.native_snapshot import NativeCalculationBarrier
from th08_runtime.win32 import ProcessReader, Win32, verify_target
from th08_runtime_agent import release_injected_keys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--launch-bat", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fingerprint-output", type=Path, required=True)
    parser.add_argument("--replay-slot", type=int, required=True)
    parser.add_argument("--expected-replay-sha256", required=True)
    parser.add_argument("--expected-route-id", type=int, required=True)
    parser.add_argument("--expected-difficulty-index", type=int, required=True)
    parser.add_argument("--expected-stage-index", type=int, required=True)
    parser.add_argument("--start-manager-frame", type=int, default=600)
    parser.add_argument("--gameplay-epochs", type=int, default=300)
    parser.add_argument(
        "--stop-at-stage-terminal",
        action="store_true",
        help=(
            "treat gameplay-inactive replay-binding teardown as successful "
            "completion before the epoch guard"
        ),
    )
    parser.add_argument("--launch-timeout", type=float, default=60.0)
    parser.add_argument("--focus-timeout", type=float, default=20.0)
    parser.add_argument("--startup-settle", type=float, default=2.0)
    parser.add_argument("--menu-timeout", type=float, default=30.0)
    parser.add_argument("--gameplay-timeout", type=float, default=60.0)
    parser.add_argument("--root-timeout", type=float, default=300.0)
    parser.add_argument("--step-timeout", type=float, default=5.0)
    parser.add_argument("--tap-hold-ms", type=int, default=65)
    parser.add_argument("--tap-gap-ms", type=int, default=90)
    parser.add_argument("--screen-settle-ms", type=int, default=350)
    parser.add_argument(
        "--collision-control-projection",
        action="store_true",
        help=(
            "attach decoded hostile, effect/ANM, and player-shot damage "
            "state at every sampled root; intended only for short windows"
        ),
    )
    parser.add_argument(
        "--effect-lifecycle-summary",
        action="store_true",
        help=(
            "decode and hash the complete effect/ANM pool but retain only "
            "its bounded summary at every sampled root"
        ),
    )
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _compact_root(fingerprint: dict[str, object]) -> dict[str, object]:
    replay = fingerprint.get("replay")
    return {
        "relative_epoch": fingerprint.get("relative_epoch"),
        "manager_frame": fingerprint.get("manager_frame"),
        "replay_frame": (
            replay.get("frame_counter") if isinstance(replay, dict) else None
        ),
        "gameplay_active": fingerprint.get("gameplay_active"),
        "game_manager_flags": fingerprint.get("game_manager_flags"),
        "difficulty_index": fingerprint.get("difficulty_index"),
        "shot_type_index": fingerprint.get("shot_type_index"),
        "stage_index": fingerprint.get("stage_index"),
    }


def validate_semantic_sample(
    fingerprint: dict[str, object],
    *,
    contract: NativeReplayStageContract,
    expected_replay_frame: int | None = None,
) -> None:
    mismatch = replay_stage_binding_mismatch(
        fingerprint,
        difficulty_index=contract.difficulty_index,
        shot_type_index=contract.route_id,
        stage_index=contract.stage_route_index,
    )
    if mismatch is not None:
        raise RuntimeError(f"retail replay stage binding changed: {mismatch}")
    replay = fingerprint["replay"]
    if not isinstance(replay, dict):
        raise RuntimeError("retail replay manager is absent at barrier root")
    if (
        expected_replay_frame is not None
        and int(replay["frame_counter"]) != expected_replay_frame
    ):
        raise RuntimeError(
            "retail replay logical input clock changed: "
            f"expected={expected_replay_frame} "
            f"observed={replay['frame_counter']}"
        )


def validate_replay_frame_advance(*, previous: int, observed: int) -> int:
    """Return a positive replay delta across two observable barrier roots."""

    delta = observed - previous
    if delta <= 0:
        raise RuntimeError(
            "retail replay logical input clock did not advance: "
            f"previous={previous} observed={observed}"
        )
    return delta


def _validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.replay_slot <= 15:
        raise ValueError("retail replay slot must be in 1..15")
    if args.start_manager_frame <= 0:
        raise ValueError("starting manager frame must be positive")
    if args.gameplay_epochs <= 0:
        raise ValueError("gameplay fingerprint epoch count must be positive")
    if args.collision_control_projection and args.effect_lifecycle_summary:
        raise ValueError(
            "collision/control and effect-summary projections are mutually "
            "exclusive"
        )
    for name in (
        "launch_timeout",
        "focus_timeout",
        "menu_timeout",
        "gameplay_timeout",
        "root_timeout",
        "step_timeout",
    ):
        if float(getattr(args, name)) <= 0.0:
            raise ValueError(f"{name.replace('_', ' ')} must be positive")
    if args.startup_settle < 0.0:
        raise ValueError("startup settle must be nonnegative")
    for name in ("tap_hold_ms", "tap_gap_ms", "screen_settle_ms"):
        if int(getattr(args, name)) < 0:
            raise ValueError(f"{name.replace('_', ' ')} must be nonnegative")
    if args.fingerprint_output.exists():
        raise FileExistsError(
            "refusing to replace retail semantic trace: "
            f"{args.fingerprint_output}"
        )


def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    report: dict[str, object] = {
        "schema": "th08-windows-replay-semantic-smoke-v5",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "scope": "bounded barrier-aligned replay differential; no route claim",
        "route_duration_limit": None,
    }
    api: Win32 | None = None
    reader: ProcessReader | None = None
    barrier: NativeCalculationBarrier | None = None
    batch_process = None
    batch_log = None
    result_code = 78
    expected_exe = args.game_dir.resolve() / TARGET_EXE
    fingerprints: list[dict[str, object]] = []
    failure_fingerprint: dict[str, object] | None = None
    try:
        if os.name != "nt":
            raise RuntimeError("retail replay capture requires Windows Python")
        if ctypes.sizeof(ctypes.c_void_p) * 8 != 32:
            raise RuntimeError("retail replay capture requires 32-bit Python")
        contract = validate_native_stage_replay(
            args.game_dir.resolve(),
            slot=args.replay_slot,
            expected_sha256=args.expected_replay_sha256,
            expected_route_id=args.expected_route_id,
            expected_difficulty_index=args.expected_difficulty_index,
            expected_stage_route_index=args.expected_stage_index,
        )
        report["replay"] = contract.compact_record()
        api = Win32()
        configure_supervisor_api(api)
        if matching_targets(api, expected_exe):
            raise RuntimeError("exact retail TH08 target already exists")
        batch_process, batch_log = launch_patch_batch(
            game_dir=args.game_dir.resolve(),
            launch_bat=args.launch_bat.resolve(),
            log_path=args.report.with_suffix(".launch.log"),
        )
        pid, identity = wait_for_patched_target(
            api,
            expected_exe=expected_exe,
            timeout_seconds=args.launch_timeout,
        )
        report["pid"] = pid
        report["target"] = identity
        report["window"] = focus_target_window(
            api, pid, timeout_seconds=args.focus_timeout
        )
        if args.startup_settle:
            time.sleep(args.startup_settle)
            focus_target_window(api, pid, timeout_seconds=args.focus_timeout)
        report["menu_trace"] = list(
            drive_native_stage_replay_menu(
                api,
                pid,
                contract=contract,
                hold_ms=args.tap_hold_ms,
                tap_gap_ms=args.tap_gap_ms,
                screen_settle_ms=args.screen_settle_ms,
                timeout_seconds=args.menu_timeout,
            )
        )
        reader, initial_state = wait_for_bound_replay_gameplay(
            api,
            pid,
            contract=contract,
            timeout_seconds=args.gameplay_timeout,
        )
        report["initial_gameplay_state"] = initial_state
        report["target"] = verify_target(reader)
        initial_manager_frame = int(initial_state["enemy_manager_frame"])
        if initial_manager_frame >= args.start_manager_frame:
            raise RuntimeError(
                "retail replay passed the requested barrier frame before "
                f"installation: current={initial_manager_frame} "
                f"target={args.start_manager_frame}"
            )
        barrier = NativeCalculationBarrier.install(
            api,
            pid,
            target_manager_frame=args.start_manager_frame,
        )
        report["barrier"] = barrier.installation_record()
        root = barrier.wait_for_root(timeout_seconds=args.root_timeout)
        if root.root_manager_frame != args.start_manager_frame:
            raise RuntimeError("retail barrier trapped the wrong manager frame")

        digest = hashlib.sha256()
        rng_calls_origin = None
        same_manager_input_epochs = 0
        manager_forward_jump_epochs = 0
        manager_frames_skipped = 0
        replay_forward_jump_epochs = 0
        replay_frames_skipped = 0
        inactive_gameplay_epochs = 0
        previous_manager_frame = None
        previous_replay_frame = None
        replay_frame_origin = None
        sample_epochs = 0
        terminal_observation = None
        for relative_epoch in range(1, args.gameplay_epochs + 1):
            manager_frame = root.root_manager_frame
            if previous_manager_frame is None:
                manager_frame_delta = 0
            else:
                manager_frame_delta = manager_frame - previous_manager_frame
            fingerprint = capture_runtime_semantic_spine(
                reader,
                relative_epoch=relative_epoch,
                rng_calls_origin=rng_calls_origin,
                trace_locators={
                    "barrier_arrival_serial": root.arrival_serial,
                    "manager_frame_delta_from_previous_root": (
                        manager_frame_delta
                    ),
                },
            )
            failure_fingerprint = fingerprint
            if args.collision_control_projection:
                fingerprint = enrich_with_collision_control_projection(
                    reader,
                    fingerprint,
                )
            elif args.effect_lifecycle_summary:
                fingerprint = enrich_with_effect_lifecycle_summary(
                    reader,
                    fingerprint,
                )
            terminal_reason = replay_stage_terminal_reason(
                fingerprint,
                difficulty_index=contract.difficulty_index,
                shot_type_index=contract.route_id,
                stage_index=contract.stage_route_index,
            )
            if terminal_reason is not None:
                if not args.stop_at_stage_terminal:
                    raise RuntimeError(
                        "retail replay stage binding ended inside fixed "
                        f"sample: {terminal_reason}"
                    )
                replay_at_terminal = fingerprint.get("replay")
                terminal_observation = {
                    "relative_epoch": relative_epoch,
                    "manager_frame": fingerprint.get("manager_frame"),
                    "replay_frame": (
                        replay_at_terminal.get("frame_counter")
                        if isinstance(replay_at_terminal, dict)
                        else None
                    ),
                    "gameplay_active": fingerprint.get("gameplay_active"),
                    "reason": terminal_reason,
                }
                break
            if previous_manager_frame is not None:
                try:
                    manager_relation = classify_manager_frame_transition(
                        previous=previous_manager_frame,
                        observed=manager_frame,
                    )
                except ValueError as error:
                    raise RuntimeError(
                        "retail manager-frame transition changed across "
                        "logical input epochs: "
                        f"previous={previous_manager_frame} "
                        f"observed={manager_frame}"
                    ) from error
                if manager_relation == MANAGER_FRAME_TRANSITION_SAME:
                    same_manager_input_epochs += 1
                elif manager_frame_delta > 1:
                    manager_forward_jump_epochs += 1
                    manager_frames_skipped += manager_frame_delta - 1
            previous_manager_frame = manager_frame
            locators = fingerprint["trace_locators"]
            assert isinstance(locators, dict)
            if rng_calls_origin is None:
                rng_calls_origin = int(locators["rng_calls_absolute"])
            if int(fingerprint["manager_frame"]) != manager_frame:
                raise RuntimeError(
                    "retail barrier header and semantic manager frame "
                    "disagree"
                )
            replay = fingerprint["replay"]
            if not isinstance(replay, dict):
                raise RuntimeError(
                    "retail replay manager is absent at barrier root"
                )
            replay_frame = int(replay["frame_counter"])
            if replay_frame_origin is None:
                replay_frame_origin = replay_frame
            validate_semantic_sample(
                fingerprint,
                contract=contract,
            )
            if previous_replay_frame is not None:
                replay_frame_delta = validate_replay_frame_advance(
                    previous=previous_replay_frame,
                    observed=replay_frame,
                )
                if replay_frame_delta > 1:
                    replay_forward_jump_epochs += 1
                    replay_frames_skipped += replay_frame_delta - 1
            previous_replay_frame = replay_frame
            if not fingerprint["gameplay_active"]:
                inactive_gameplay_epochs += 1
            fingerprints.append(fingerprint)
            failure_fingerprint = None
            sample_epochs += 1
            digest.update(canonical_fingerprint_bytes(fingerprint))
            digest.update(b"\n")
            if relative_epoch != args.gameplay_epochs:
                root = barrier.natural_advance(
                    timeout_seconds=args.step_timeout
                )

        if args.stop_at_stage_terminal and terminal_observation is None:
            raise RuntimeError(
                "retail replay stage terminal was not reached inside the "
                f"{args.gameplay_epochs}-epoch guard"
            )
        if sample_epochs == 0:
            raise RuntimeError("retail replay sample contains no bound input epoch")

        write_semantic_trace(args.fingerprint_output, fingerprints)
        report.update(
            {
                "sample_epochs": sample_epochs,
                "maximum_sample_epochs": args.gameplay_epochs,
                "stop_at_stage_terminal": bool(args.stop_at_stage_terminal),
                "stage_terminal": terminal_observation,
                "start_manager_frame": args.start_manager_frame,
                "manager_frame_range": [
                    int(fingerprints[0]["manager_frame"]),
                    int(fingerprints[-1]["manager_frame"]),
                ],
                "start_replay_frame": replay_frame_origin,
                "replay_frame_range": [
                    int(fingerprints[0]["replay"]["frame_counter"]),
                    int(fingerprints[-1]["replay"]["frame_counter"]),
                ],
                "rng_calls_origin": rng_calls_origin,
                "same_manager_input_epochs": same_manager_input_epochs,
                "manager_forward_jump_epochs": manager_forward_jump_epochs,
                "manager_frames_skipped": manager_frames_skipped,
                "replay_forward_jump_epochs": replay_forward_jump_epochs,
                "replay_frames_skipped": replay_frames_skipped,
                "inactive_gameplay_epochs": inactive_gameplay_epochs,
                "semantic_spine_sha256": digest.hexdigest(),
                "fingerprint_output": str(args.fingerprint_output),
                "fingerprint_output_sha256": _sha256(
                    args.fingerprint_output
                ),
                "first": fingerprints[0],
                "last": fingerprints[-1],
                "status": "passed",
                "collision_control_projection": bool(
                    args.collision_control_projection
                ),
                "effect_lifecycle_summary": bool(
                    args.effect_lifecycle_summary
                ),
            }
        )
        result_code = 0
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["partial_sample_epochs"] = len(fingerprints)
        if failure_fingerprint is not None:
            report["failure_root"] = _compact_root(failure_fingerprint)
        if fingerprints and not args.fingerprint_output.exists():
            partial_path = partial_semantic_trace_path(
                args.fingerprint_output
            )
            try:
                if not partial_path.exists():
                    write_semantic_trace(partial_path, fingerprints)
                report["partial_fingerprint_output"] = str(partial_path)
                report["partial_fingerprint_output_sha256"] = _sha256(
                    partial_path
                )
            except BaseException as partial_error:
                report["partial_fingerprint_error"] = (
                    f"{type(partial_error).__name__}: {partial_error}"
                )
        if isinstance(error, KeyboardInterrupt):
            result_code = 130
    finally:
        if reader is not None:
            reader.close()
        if api is not None:
            try:
                release_injected_keys(api)
            except OSError:
                pass
            try:
                report["game_terminated"] = terminate_exact_target(
                    api, expected_exe
                )
            except BaseException as error:
                report["termination_error"] = (
                    f"{type(error).__name__}: {error}"
                )
                report["status"] = "failed"
                if result_code == 0:
                    result_code = 78
        if barrier is not None:
            barrier.close_after_target_termination()
        _stop_batch_process(batch_process)
        if batch_log is not None:
            batch_log.close()
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return result_code


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
