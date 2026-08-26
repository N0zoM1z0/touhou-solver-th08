#!/usr/bin/env python3
"""Windows-side exact-game, patch, title, NumPy, and native-DLL smoke."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics

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
from th08_live.enemy_sensor import (
    ENEMY_LOCAL_PREFIX_SIZE,
    ENEMY_MANAGER_SCANNED_SLOT_COUNT,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_prefix_contiguous,
    capture_enemy_pool_snapshot_contiguous,
    capture_enemy_pool_snapshot_sparse,
)
from th08_runtime_agent import (
    TARGET_EXE,
    ProcessReader,
    Win32,
    release_injected_keys,
)
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
    parser.add_argument("--enemy-sensor-iterations", type=int, default=12)
    return parser


def _timing_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[int(0.95 * (len(ordered) - 1))],
        "maximum_ms": ordered[-1],
    }


def _benchmark_enemy_sensors(
    reader: ProcessReader,
    *,
    iterations: int,
) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("enemy sensor iterations must be positive")
    full_size = ENEMY_MANAGER_SCANNED_SLOT_COUNT * ENEMY_STRIDE
    prefix_size = ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE
    full_buffer = reader.allocate_buffer(full_size)
    prefix_buffer = reader.allocate_buffer(prefix_size)
    timings: dict[str, list[float]] = {
        "legacy_sparse": [],
        "source_contiguous": [],
        "source_prefix": [],
    }
    body_counts: dict[str, list[int]] = {
        name: [] for name in timings
    }
    stable_counts = {name: 0 for name in timings}
    stable_pair_count = 0
    stable_pair_equivalent_count = 0
    for iteration in range(iterations):
        if iteration % 2:
            contiguous = capture_enemy_pool_snapshot_contiguous(
                reader,
                pool_base=ENEMY_SLOT_ZERO_BASE,
                pool_size=ENEMY_MANAGER_SCANNED_SLOT_COUNT,
                pool_buffer=full_buffer,
            )
            sparse = capture_enemy_pool_snapshot_sparse(reader)
        else:
            sparse = capture_enemy_pool_snapshot_sparse(reader)
            contiguous = capture_enemy_pool_snapshot_contiguous(
                reader,
                pool_base=ENEMY_SLOT_ZERO_BASE,
                pool_size=ENEMY_MANAGER_SCANNED_SLOT_COUNT,
                pool_buffer=full_buffer,
            )
        prefix = capture_enemy_pool_prefix_contiguous(
            reader,
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=ENEMY_LOCAL_PREFIX_SIZE,
            pool_buffer=prefix_buffer,
        )
        snapshots = {
            "legacy_sparse": sparse,
            "source_contiguous": contiguous,
            "source_prefix": prefix,
        }
        for name, snapshot in snapshots.items():
            timings[name].append(snapshot.read_ms)
            body_counts[name].append(len(snapshot.bodies))
            stable_counts[name] += snapshot.stable
        if sparse.stable and contiguous.stable:
            stable_pair_count += 1
            stable_pair_equivalent_count += (
                {body.pointer for body in sparse.bodies}
                == {body.pointer for body in contiguous.bodies}
            )
    return {
        "role": "read_only_title_microbenchmark",
        "iterations": iterations,
        "source_full_range": {
            "base": ENEMY_SLOT_ZERO_BASE,
            "slots": ENEMY_MANAGER_SCANNED_SLOT_COUNT,
            "bytes": full_size,
        },
        "timing_ms": {
            name: _timing_summary(values)
            for name, values in timings.items()
        },
        "stable_capture_count": stable_counts,
        "body_counts": body_counts,
        "stable_sparse_contiguous_pair_count": stable_pair_count,
        "stable_sparse_contiguous_equivalent_count": (
            stable_pair_equivalent_count
        ),
        "stable_sparse_contiguous_pairs_equivalent": bool(
            stable_pair_count
            and stable_pair_count == stable_pair_equivalent_count
        ),
    }


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
    reader: ProcessReader | None = None
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
        reader = ProcessReader(api, pid)
        report["enemy_sensor_benchmark"] = _benchmark_enemy_sensors(
            reader,
            iterations=args.enemy_sensor_iterations,
        )
        report["status"] = "passed"
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
