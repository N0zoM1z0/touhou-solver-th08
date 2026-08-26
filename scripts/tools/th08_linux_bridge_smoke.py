#!/usr/bin/env python3
"""Run a bounded neutral-input smoke against the native Linux TH08 bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_linux import (  # noqa: E402
    LinuxGameSession,
    validate_request_memory_witness,
)
from th08_runtime.sensing import observe_state  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    return parser


def run(args: argparse.Namespace) -> int:
    if args.epochs <= 0:
        raise ValueError("smoke epoch count must be positive")
    observations: list[dict[str, object]] = []
    session = LinuxGameSession(
        executable=args.executable,
        data_directory=args.data_directory,
        expected_sha256=args.expected_sha256,
        display=args.display,
        environment={"SDL_AUDIODRIVER": "dummy"},
        startup_timeout_seconds=args.startup_timeout_seconds,
    )
    try:
        with session:
            for _ in range(args.epochs):
                request = session.bridge.receive()
                state = observe_state(session.reader)
                memory_witness = validate_request_memory_witness(
                    request, session.reader
                )
                witness = {
                "epoch": request.epoch,
                "request_current_input": request.current_input,
                "memory_supervisor_current_input": (
                    memory_witness.supervisor_current_input
                ),
                "request_previous_input": request.previous_input,
                "memory_supervisor_previous_input": (
                    memory_witness.supervisor_previous_input
                ),
                "memory_gui_current_input": state["input_current"],
                "memory_gui_previous_input": state["input_previous"],
                "request_rng_seed": request.rng_seed,
                "memory_rng_seed": memory_witness.rng_seed,
                "enemy_manager_frame": state["enemy_manager_frame"],
                "engine_flags": state["engine_flags"],
                "stage_route_index": state["stage_route_index"],
                "difficulty_index": state["difficulty_index"],
                "replay_target_stamped": request.replay_target_stamped,
                "paused_milliseconds": request.paused_milliseconds,
                }
                observations.append(witness)
                session.bridge.respond(0)
            report = {
                "schema": "th08-linux-lockstep-smoke-v2",
                "runtime": {
                    "path": str(session.identity.path),
                    "size": session.identity.size,
                    "sha256": session.identity.sha256,
                },
                "pid": session.pid,
                "epochs": observations,
                "route_duration_limit": None,
            }
            print(json.dumps(report, sort_keys=True))
    except BaseException:
        if session.runtime_log_tail:
            print("runtime log tail:", file=sys.stderr)
            print(session.runtime_log_tail, file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
