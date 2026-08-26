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
    canonical_fingerprint_bytes,
    capture_runtime_semantic_spine,
    enrich_with_collision_control_projection,
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
    parser.add_argument("--launch-timeout", type=float, default=60.0)
    parser.add_argument("--focus-timeout", type=float, default=20.0)
    parser.add_argument("--startup-settle", type=float, default=2.0)
    parser.add_argument("--menu-timeout", type=float, default=30.0)
    parser.add_argument("--gameplay-timeout", type=float, default=60.0)
    parser.add_argument("--root-timeout", type=float, default=90.0)
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
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_semantic_sample(
    fingerprint: dict[str, object],
    *,
    contract: NativeReplayStageContract,
    expected_manager_frame: int,
) -> None:
    if int(fingerprint["manager_frame"]) != expected_manager_frame:
        raise RuntimeError(
            "retail barrier manager-frame alignment changed: "
            f"expected={expected_manager_frame} "
            f"observed={fingerprint['manager_frame']}"
        )
    if not fingerprint["gameplay_active"]:
        raise RuntimeError("retail replay gameplay became inactive inside sample")
    if not int(fingerprint["game_manager_flags"]) & 0x08:
        raise RuntimeError("retail gameplay sample is not in replay mode")
    for field, expected in (
        ("difficulty_index", contract.difficulty_index),
        ("shot_type_index", contract.route_id),
        ("stage_index", contract.stage_route_index),
    ):
        if int(fingerprint[field]) != expected:
            raise RuntimeError(
                f"retail replay {field} changed: "
                f"expected={expected} observed={fingerprint[field]}"
            )
    replay = fingerprint["replay"]
    if not isinstance(replay, dict):
        raise RuntimeError("retail replay manager is absent at barrier root")
    if int(replay["frame_counter"]) != expected_manager_frame:
        raise RuntimeError(
            "retail replay/manager clocks are not aligned: "
            f"manager={expected_manager_frame} "
            f"replay={replay['frame_counter']}"
        )


def _validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.replay_slot <= 15:
        raise ValueError("retail replay slot must be in 1..15")
    if args.start_manager_frame <= 0:
        raise ValueError("starting manager frame must be positive")
    if args.gameplay_epochs <= 0:
        raise ValueError("gameplay fingerprint epoch count must be positive")
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
        "schema": "th08-windows-replay-semantic-smoke-v1",
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

        fingerprints: list[dict[str, object]] = []
        digest = hashlib.sha256()
        rng_calls_origin = None
        for relative_epoch in range(1, args.gameplay_epochs + 1):
            expected_frame = args.start_manager_frame + relative_epoch - 1
            fingerprint = capture_runtime_semantic_spine(
                reader,
                relative_epoch=relative_epoch,
                rng_calls_origin=rng_calls_origin,
                trace_locators={
                    "barrier_arrival_serial": root.arrival_serial,
                },
            )
            if args.collision_control_projection:
                fingerprint = enrich_with_collision_control_projection(
                    reader,
                    fingerprint,
                )
            locators = fingerprint["trace_locators"]
            assert isinstance(locators, dict)
            if rng_calls_origin is None:
                rng_calls_origin = int(locators["rng_calls_absolute"])
            validate_semantic_sample(
                fingerprint,
                contract=contract,
                expected_manager_frame=expected_frame,
            )
            fingerprints.append(fingerprint)
            digest.update(canonical_fingerprint_bytes(fingerprint))
            digest.update(b"\n")
            if relative_epoch != args.gameplay_epochs:
                root = barrier.natural_advance(
                    timeout_seconds=args.step_timeout
                )
                if root.root_manager_frame != expected_frame + 1:
                    raise RuntimeError(
                        "retail natural frame pump did not reach the next "
                        "manager frame"
                    )

        write_semantic_trace(args.fingerprint_output, fingerprints)
        report.update(
            {
                "sample_epochs": args.gameplay_epochs,
                "start_manager_frame": args.start_manager_frame,
                "manager_frame_range": [
                    args.start_manager_frame,
                    args.start_manager_frame + args.gameplay_epochs - 1,
                ],
                "rng_calls_origin": rng_calls_origin,
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
            }
        )
        result_code = 0
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
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
