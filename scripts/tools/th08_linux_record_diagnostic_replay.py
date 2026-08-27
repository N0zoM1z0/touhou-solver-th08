#!/usr/bin/env python3
"""Create one normally saved Linux replay through the retail result UI."""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
    ReplaySaveDriver,
    ResultDecision,
    RetryExitDriver,
    RouteTitleDriver,
    capture_gameplay_bootstrap,
    capture_result_screen,
    capture_retry_menu,
    capture_supervisor_state,
    capture_title_snapshot,
    validate_request_memory_witness,
)
from th08_replay import decode_replay  # noqa: E402
from th08_linux.elf import resolve_defined_symbol  # noqa: E402


RESULT_UPDATE_SYMBOL = "_ZN4th0812ResultScreen8OnUpdateEPS0_"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--replay-slot", type=int, default=1)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--maximum-bootstrap-epochs", type=int, default=4096)
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    return parser


def _transition(
    transitions: list[dict[str, object]],
    key_holder: list[tuple[object, ...] | None],
    *,
    key: tuple[object, ...],
    record: dict[str, object],
) -> None:
    if key != key_holder[0]:
        transitions.append(record)
        key_holder[0] = key


def _attest_request(request: object) -> None:
    if request.lives_preserved:
        raise RuntimeError(
            "diagnostic runtime still attests preserved lives; refusing to "
            "claim a normal replay-save path"
        )
    if not request.replay_target_stamped:
        raise RuntimeError("runtime did not stamp the original replay target")


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.replay_slot <= 15:
        raise ValueError("replay slot must be in [1, 15]")
    if args.maximum_bootstrap_epochs <= 0:
        raise ValueError("maximum bootstrap epoch count must be positive")

    executable = args.executable.resolve(strict=True)
    data_directory = args.data_directory.resolve(strict=True)
    if not data_directory.is_dir():
        raise ValueError("runtime data directory is not a directory")
    replay_path = (
        data_directory / "replay" / f"th8_{args.replay_slot:02d}.rpy"
    )
    if replay_path.exists():
        raise FileExistsError(
            f"diagnostic replay slot must be empty: {replay_path}"
        )

    result_callback = resolve_defined_symbol(executable, RESULT_UPDATE_SYMBOL)
    title_driver = RouteTitleDriver(
        difficulty_index=EASY_DIFFICULTY,
        shot_type_index=SAKUYA_REMILIA_SHOT_TYPE,
    )
    retry_driver = RetryExitDriver()
    result_driver = ReplaySaveDriver(replay_slot=args.replay_slot - 1)
    transitions: list[dict[str, object]] = []
    transition_key: list[tuple[object, ...] | None] = [None]
    wire_checks = 0
    gameplay_ready_epoch = None
    replay_visible_epoch = None

    session = LinuxGameSession(
        executable=executable,
        data_directory=data_directory,
        expected_sha256=args.expected_sha256,
        display=args.display,
        environment={
            "SDL_AUDIODRIVER": "dummy",
            "TH08_SOLVER_PRESERVE_LIVES": "0",
        },
        startup_timeout_seconds=args.startup_timeout_seconds,
    )
    try:
        with session:
            for _ in range(args.maximum_bootstrap_epochs):
                request = session.bridge.receive()
                _attest_request(request)
                gameplay = capture_gameplay_bootstrap(session.reader)
                validate_request_memory_witness(
                    request,
                    session.reader,
                    verify_rng=(
                        not gameplay.registered or gameplay.loading_state == 0
                    ),
                )
                wire_checks += 1
                if gameplay.registered:
                    decision_mask = 0
                    action = "wait-gameplay-load"
                    if gameplay.ready:
                        action = "gameplay-ready"
                    session.bridge.respond(decision_mask)
                    _transition(
                        transitions,
                        transition_key,
                        key=(
                            "gameplay-load",
                            gameplay.loading_state,
                            gameplay.stage_route_index,
                            action,
                        ),
                        record={
                            "epoch": request.epoch,
                            "phase": "gameplay-load",
                            "loading_state": gameplay.loading_state,
                            "stage_route_index": gameplay.stage_route_index,
                            "action": action,
                        },
                    )
                    if gameplay.ready:
                        gameplay_ready_epoch = request.epoch
                        break
                    continue

                snapshot = None
                if request.current_input == 0:
                    snapshot = capture_title_snapshot(session.reader)
                decision = title_driver.decide(
                    snapshot,
                    current_input=request.current_input,
                )
                session.bridge.respond(decision.input_mask)
                screen = None if snapshot is None else snapshot.current_screen
                cursor = None if snapshot is None else snapshot.cursor
                _transition(
                    transitions,
                    transition_key,
                    key=("title", screen, cursor, decision.action),
                    record={
                        "epoch": request.epoch,
                        "phase": "title",
                        "screen": screen,
                        "cursor": cursor,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    },
                )
            else:
                raise RuntimeError(
                    "source-driven title bootstrap exceeded its diagnostic "
                    f"guard of {args.maximum_bootstrap_epochs} epochs"
                )

            while True:
                request = session.bridge.receive()
                _attest_request(request)
                validate_request_memory_witness(request, session.reader)
                wire_checks += 1

                if replay_path.is_file():
                    session.bridge.respond(0)
                    replay_visible_epoch = request.epoch
                    _transition(
                        transitions,
                        transition_key,
                        key=("saved",),
                        record={
                            "epoch": request.epoch,
                            "phase": "saved",
                            "action": "replay-file-visible",
                        },
                    )
                    break

                result = capture_result_screen(
                    session.reader,
                    update_callback=result_callback,
                )
                retry = capture_retry_menu(session.reader)
                supervisor_state = capture_supervisor_state(session.reader)
                if result is not None:
                    decision = result_driver.decide(
                        result,
                        current_input=request.current_input,
                    )
                    key = (
                        "result",
                        result.state,
                        result.cursor,
                        result.selected_character,
                        decision.action,
                    )
                    record = {
                        "epoch": request.epoch,
                        "phase": "result",
                        "supervisor_state": supervisor_state,
                        "result_state": result.state,
                        "frame_timer": result.frame_timer,
                        "cursor": result.cursor,
                        "selected_character": result.selected_character,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    }
                elif retry.showing:
                    decision = retry_driver.decide(
                        retry,
                        current_input=request.current_input,
                    )
                    key = (
                        "retry",
                        retry.state,
                        decision.action,
                    )
                    record = {
                        "epoch": request.epoch,
                        "phase": "retry",
                        "supervisor_state": supervisor_state,
                        "retry_state": retry.state,
                        "frame_timer": retry.frame_timer,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    }
                else:
                    gameplay = capture_gameplay_bootstrap(session.reader)
                    decision_mask = 0
                    action = (
                        "neutral-gameplay"
                        if gameplay.registered
                        else "wait-result-registration"
                    )
                    decision = ResultDecision(decision_mask, action)
                    key = (
                        "gameplay",
                        gameplay.registered,
                        gameplay.stage_route_index,
                        supervisor_state,
                        action,
                    )
                    record = {
                        "epoch": request.epoch,
                        "phase": "gameplay-or-transition",
                        "supervisor_state": supervisor_state,
                        "gameplay_registered": gameplay.registered,
                        "stage_route_index": gameplay.stage_route_index,
                        "action": action,
                        "input_mask": decision_mask,
                    }
                session.bridge.respond(decision.input_mask)
                _transition(
                    transitions,
                    transition_key,
                    key=key,
                    record=record,
                )
    except BaseException:
        if session.runtime_log_tail:
            print("runtime log tail:", file=sys.stderr)
            print(session.runtime_log_tail, file=sys.stderr)
        raise

    metadata, _decoded = decode_replay(replay_path)
    if metadata.difficulty_index != EASY_DIFFICULTY:
        raise RuntimeError(
            f"saved replay difficulty is {metadata.difficulty_index}, expected Easy"
        )
    if metadata.route_id != SAKUYA_REMILIA_SHOT_TYPE:
        raise RuntimeError(
            f"saved replay route is {metadata.route_id}, expected Sakuya/Remilia"
        )
    bomb_frames = [
        frame
        for stage in metadata.stages
        for frame in stage.bomb_press_frames
    ]
    if bomb_frames:
        raise RuntimeError(f"saved replay contains Bomb presses: {bomb_frames[:8]}")

    report = {
        "schema": "th08-linux-normal-save-diagnostic-replay-v1",
        "runtime": {
            "path": str(session.identity.path),
            "size": session.identity.size,
            "sha256": session.identity.sha256,
            "result_update_symbol": RESULT_UPDATE_SYMBOL,
            "result_update_address": result_callback,
        },
        "target": {
            "difficulty_index": EASY_DIFFICULTY,
            "shot_type_index": SAKUYA_REMILIA_SHOT_TYPE,
            "replay_slot": args.replay_slot,
        },
        "replay": asdict(metadata),
        "gameplay_ready_epoch": gameplay_ready_epoch,
        "replay_visible_epoch": replay_visible_epoch,
        "wire_memory_checks": wire_checks,
        "lives_preserved_attested": False,
        "bomb_policy_violations": 0,
        "transitions": transitions,
        "route_duration_limit": None,
        "scope": (
            "diagnostic normal-save replay only; original-v1.00d reverse "
            "playback still required"
        ),
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
