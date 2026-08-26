#!/usr/bin/env python3
"""Bootstrap native TH08 to one verified Easy Sakuya/Remilia game epoch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_linux import (  # noqa: E402
    EASY_DIFFICULTY,
    SAKUYA_REMILIA_SHOT_TYPE,
    LinuxGameSession,
    RouteTitleDriver,
    TitleSnapshot,
    capture_gameplay_bootstrap,
    capture_title_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--maximum-bootstrap-epochs", type=int, default=4096)
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    return parser


def _title_transition(
    *, epoch: int, snapshot: TitleSnapshot, action: str, input_mask: int
) -> dict[str, object]:
    return {
        "epoch": epoch,
        "phase": "title",
        "screen": snapshot.current_screen,
        "screen_state": snapshot.current_screen_state,
        "lifecycle_state": snapshot.lifecycle_state,
        "cursor": snapshot.cursor,
        "state_timer2": snapshot.state_timer2,
        "action": action,
        "input_mask": input_mask,
    }


def run(args: argparse.Namespace) -> int:
    if args.maximum_bootstrap_epochs <= 0:
        raise ValueError("maximum bootstrap epoch count must be positive")
    driver = RouteTitleDriver(
        difficulty_index=EASY_DIFFICULTY,
        shot_type_index=SAKUYA_REMILIA_SHOT_TYPE,
    )
    transitions: list[dict[str, object]] = []
    previous_key: tuple[object, ...] | None = None
    ready = None
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
            for _ in range(args.maximum_bootstrap_epochs):
                request = session.bridge.receive()
                gameplay = capture_gameplay_bootstrap(session.reader)
                if gameplay.registered:
                    session.bridge.respond(0)
                    key = (
                        "gameplay",
                        gameplay.loading_state,
                        gameplay.difficulty_index,
                        gameplay.shot_type_index,
                        gameplay.stage_route_index,
                    )
                    if key != previous_key:
                        transitions.append(
                            {
                                "epoch": request.epoch,
                                "phase": "gameplay-load",
                                "loading_state": gameplay.loading_state,
                                "difficulty_index": gameplay.difficulty_index,
                                "shot_type_index": gameplay.shot_type_index,
                                "stage_route_index": gameplay.stage_route_index,
                            }
                        )
                        previous_key = key
                    if gameplay.ready:
                        ready = gameplay
                        break
                    continue

                # `TitleScreen::DeletedCallback` frees the object without
                # clearing g_TitleScreen.  A nonzero current input only needs
                # an edge release, so do that without dereferencing the title
                # root.  This covers the exact post-character-confirm handoff
                # epoch before GameManager::RegisterChain becomes observable.
                snapshot = None
                if request.current_input == 0:
                    snapshot = capture_title_snapshot(session.reader)
                decision = driver.decide(
                    snapshot,
                    current_input=request.current_input,
                )
                session.bridge.respond(decision.input_mask)
                if snapshot is None:
                    phase = (
                        "input-release"
                        if request.current_input != 0
                        else "title-root"
                    )
                    key = (phase, None, decision.action)
                    if key != previous_key:
                        transitions.append(
                            {
                                "epoch": request.epoch,
                                "phase": phase,
                                "action": decision.action,
                                "input_mask": decision.input_mask,
                            }
                        )
                        previous_key = key
                    continue
                key = (
                    "title",
                    snapshot.current_screen,
                    snapshot.current_screen_state,
                    snapshot.lifecycle_state,
                    snapshot.cursor,
                    decision.action,
                    decision.input_mask,
                )
                if key != previous_key:
                    transitions.append(
                        _title_transition(
                            epoch=request.epoch,
                            snapshot=snapshot,
                            action=decision.action,
                            input_mask=decision.input_mask,
                        )
                    )
                    previous_key = key
            else:
                raise RuntimeError(
                    "source-driven title bootstrap exceeded its diagnostic "
                    f"guard of {args.maximum_bootstrap_epochs} input epochs"
                )

            assert ready is not None
            if ready.difficulty_index != EASY_DIFFICULTY:
                raise RuntimeError(
                    "gameplay initialized with unexpected difficulty "
                    f"{ready.difficulty_index}"
                )
            if ready.shot_type_index != SAKUYA_REMILIA_SHOT_TYPE:
                raise RuntimeError(
                    "gameplay initialized with unexpected shot type "
                    f"{ready.shot_type_index}"
                )
            if ready.stage_route_index != 0:
                raise RuntimeError(
                    "gameplay initialized outside Stage 1 route index 0: "
                    f"{ready.stage_route_index}"
                )
            report = {
                "schema": "th08-linux-title-bootstrap-smoke-v1",
                "runtime": {
                    "path": str(session.identity.path),
                    "size": session.identity.size,
                    "sha256": session.identity.sha256,
                },
                "pid": session.pid,
                "target": {
                    "difficulty_index": EASY_DIFFICULTY,
                    "shot_type_index": SAKUYA_REMILIA_SHOT_TYPE,
                    "stage_route_index": 0,
                },
                "ready": {
                    "calc_callback": ready.calc_callback,
                    "loading_state": ready.loading_state,
                    "difficulty_index": ready.difficulty_index,
                    "shot_type_index": ready.shot_type_index,
                    "stage_route_index": ready.stage_route_index,
                },
                "last_epoch": request.epoch,
                "transitions": transitions,
                "route_duration_limit": None,
                "scope": "bounded bootstrap diagnostic; no gameplay claim",
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
