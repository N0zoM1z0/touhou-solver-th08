#!/usr/bin/env python3
"""Windows-side exact-game, patch, title, NumPy, and native-DLL smoke."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import numpy as np

from th08_automation.practice_supervisor import (
    TITLE_MODE_MAIN,
    _configure_supervisor_api,
    _matching_targets,
    _read_title_menu_state,
    _stop_batch_process,
    focus_target_window,
    launch_patch_batch,
    terminate_exact_target,
    wait_for_patched_target,
    wait_for_title_menu,
)
from th08_runtime_agent import TARGET_EXE, Win32, release_injected_keys
from touhou_control import native_backend
from touhou_control.native.library import library_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--launch-bat", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--launch-timeout", type=float, default=40.0)
    parser.add_argument("--focus-timeout", type=float, default=15.0)
    parser.add_argument("--title-timeout", type=float, default=30.0)
    return parser


def run(args: argparse.Namespace) -> int:
    report: dict[str, object] = {
        "schema": "th08-wine-windows-smoke-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "python_pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
        "numpy_version": np.__version__,
        "native_library": str(library_path()),
    }
    api: Win32 | None = None
    expected_exe = args.game_dir.resolve() / TARGET_EXE
    batch_process = None
    batch_log = None
    result_code = 78
    try:
        if os.name != "nt":
            raise RuntimeError("TH08 Wine smoke requires Windows Python")
        if report["python_pointer_bits"] != 32:
            raise RuntimeError("TH08 Wine smoke requires 32-bit Python")
        native_probe = np.asarray([0.0, 1.0], dtype=np.float32)
        report["numpy_probe_sum"] = float(native_probe.sum())
        if not native_backend.set_current_thread_viability_worker_limit(1):
            raise RuntimeError("Win32 native viability DLL is unavailable")
        report["native_worker_limit_applied"] = True
        api = Win32()
        _configure_supervisor_api(api)
        if _matching_targets(api, expected_exe):
            raise RuntimeError("exact TH08 target already exists in this prefix")
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
        report["target"] = identity
        report["pid"] = pid
        report["window"] = focus_target_window(
            api,
            pid,
            timeout_seconds=args.focus_timeout,
        )
        report["caps_lock_bootstrap"] = {
            "required": False,
            "reason": "direct supervisor arm has no Caps Lock dependency",
        }
        wait_for_title_menu(
            api,
            pid,
            mode=TITLE_MODE_MAIN,
            timeout_seconds=args.title_timeout,
        )
        report["title_state"] = _read_title_menu_state(api, pid)
        report["status"] = "passed"
        result_code = 0
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if isinstance(error, KeyboardInterrupt):
            result_code = 130
    finally:
        if api is not None:
            try:
                release_injected_keys(api)
            except OSError:
                pass
            try:
                report["game_terminated"] = terminate_exact_target(
                    api,
                    expected_exe,
                )
            except BaseException as error:
                report["termination_error"] = (
                    f"{type(error).__name__}: {error}"
                )
                report["status"] = "failed"
                if result_code == 0:
                    result_code = 78
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


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
