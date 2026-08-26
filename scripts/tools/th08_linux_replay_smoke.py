#!/usr/bin/env python3
"""Load one retained replay in native TH08 and hash a bounded semantic spine."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_linux import (  # noqa: E402
    LinuxGameSession,
    ReplayTitleDriver,
    canonical_fingerprint_bytes,
    capture_gameplay_bootstrap,
    capture_semantic_spine,
    capture_title_snapshot,
    enrich_with_collision_control_projection,
    validate_request_memory_witness,
    write_semantic_trace,
)
from th08_replay import decode_replay  # noqa: E402
from th08_runtime.sensing import observe_state  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--replay-name", required=True)
    parser.add_argument("--stage-index", type=int, required=True)
    parser.add_argument("--start-manager-frame", type=int, default=1)
    parser.add_argument("--gameplay-epochs", type=int, default=300)
    parser.add_argument("--maximum-bootstrap-epochs", type=int, default=4096)
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--fingerprint-output",
        type=Path,
        help="write every sampled spine to a new .jsonl or .jsonl.gz file",
    )
    parser.add_argument(
        "--collision-control-projection",
        action="store_true",
        help=(
            "attach decoded bullet/laser/enemy/ECL state at every sampled "
            "root; intended only for short differential windows"
        ),
    )
    return parser


def run(args: argparse.Namespace) -> int:
    if args.gameplay_epochs <= 0:
        raise ValueError("gameplay fingerprint epoch count must be positive")
    if args.start_manager_frame <= 0:
        raise ValueError("starting manager frame must be positive")
    if args.maximum_bootstrap_epochs <= 0:
        raise ValueError("maximum bootstrap epoch count must be positive")
    if args.fingerprint_output is not None and args.fingerprint_output.exists():
        raise FileExistsError(
            f"refusing to replace semantic trace: {args.fingerprint_output}"
        )
    replay_path = args.data_directory / "replay" / args.replay_name
    metadata, _decoded = decode_replay(replay_path)
    stage = next(
        (item for item in metadata.stages if item.stage_index == args.stage_index),
        None,
    )
    if stage is None:
        raise ValueError(
            f"replay {args.replay_name} has no Stage {args.stage_index} record"
        )
    if stage.bomb_press_frames:
        raise ValueError("replay smoke target contains Bomb input")

    driver = ReplayTitleDriver(
        replay_name=args.replay_name,
        stage_index=args.stage_index,
    )
    transitions: list[dict[str, object]] = []
    previous_key: tuple[object, ...] | None = None
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
            ready = None
            for _ in range(args.maximum_bootstrap_epochs):
                request = session.bridge.receive()
                gameplay = capture_gameplay_bootstrap(session.reader)
                validate_request_memory_witness(
                    request,
                    session.reader,
                    verify_rng=(
                        not gameplay.registered or gameplay.loading_state == 0
                    ),
                )
                if gameplay.registered:
                    state = observe_state(session.reader)
                    session.bridge.respond(0)
                    key = (
                        "gameplay",
                        gameplay.loading_state,
                        state["gameplay_active"],
                    )
                    if key != previous_key:
                        transitions.append(
                            {
                                "epoch": request.epoch,
                                "phase": "gameplay-load",
                                "loading_state": gameplay.loading_state,
                                "gameplay_active": state["gameplay_active"],
                            }
                        )
                        previous_key = key
                    if gameplay.ready and state["gameplay_active"]:
                        ready = gameplay
                        break
                    continue

                snapshot = None
                if request.current_input == 0:
                    snapshot = capture_title_snapshot(session.reader)
                decision = driver.decide(
                    snapshot,
                    current_input=request.current_input,
                )
                session.bridge.respond(decision.input_mask)
                if snapshot is None:
                    key = ("release-or-root", decision.action)
                    if key != previous_key:
                        transitions.append(
                            {
                                "epoch": request.epoch,
                                "phase": "release-or-root",
                                "action": decision.action,
                            }
                        )
                        previous_key = key
                    continue
                key = (
                    "title",
                    snapshot.current_screen,
                    snapshot.current_screen_state,
                    snapshot.cursor,
                    decision.action,
                )
                if key != previous_key:
                    transitions.append(
                        {
                            "epoch": request.epoch,
                            "phase": "title",
                            "screen": snapshot.current_screen,
                            "screen_state": snapshot.current_screen_state,
                            "cursor": snapshot.cursor,
                            "replay_count": snapshot.replay_count,
                            "action": decision.action,
                            "input_mask": decision.input_mask,
                        }
                    )
                    previous_key = key
            else:
                raise RuntimeError(
                    "source-driven replay bootstrap exceeded its diagnostic "
                    f"guard of {args.maximum_bootstrap_epochs} input epochs"
                )

            assert ready is not None
            bootstrap_last_epoch = request.epoch
            if (
                ready.difficulty_index != metadata.difficulty_index
                or ready.shot_type_index != metadata.route_id
                or ready.stage_route_index != args.stage_index
            ):
                raise RuntimeError(
                    "loaded replay identity does not match decoded replay metadata"
                )

            digest = hashlib.sha256()
            first = None
            last = None
            nonzero_gui_epochs = 0
            replay_frames: list[int] = []
            fingerprints: list[dict[str, object]] = []
            rng_calls_origin = None
            skipped_gameplay_epochs = 0
            for relative_epoch in range(1, args.gameplay_epochs + 1):
                while True:
                    request = session.bridge.receive()
                    fingerprint = capture_semantic_spine(
                        session.reader,
                        request,
                        relative_epoch=relative_epoch,
                        rng_calls_origin=rng_calls_origin,
                    )
                    if args.collision_control_projection:
                        fingerprint = enrich_with_collision_control_projection(
                            session.reader,
                            fingerprint,
                        )
                    manager_frame = int(fingerprint["manager_frame"])
                    expected_manager_frame = (
                        args.start_manager_frame + relative_epoch - 1
                    )
                    if (
                        relative_epoch == 1
                        and manager_frame < expected_manager_frame
                    ):
                        session.bridge.respond(0)
                        skipped_gameplay_epochs += 1
                        continue
                    session.bridge.respond(0)
                    if manager_frame != expected_manager_frame:
                        raise RuntimeError(
                            "replay manager-frame alignment changed: "
                            f"expected={expected_manager_frame} "
                            f"observed={manager_frame}"
                        )
                    break
                trace_locators = fingerprint["trace_locators"]
                assert isinstance(trace_locators, dict)
                if rng_calls_origin is None:
                    rng_calls_origin = int(trace_locators["rng_calls_absolute"])
                if not fingerprint["gameplay_active"]:
                    raise RuntimeError(
                        "replay gameplay became inactive inside the requested sample"
                    )
                if not int(fingerprint["game_manager_flags"]) & 0x08:
                    raise RuntimeError("gameplay sample is not in replay mode")
                if fingerprint["difficulty_index"] != metadata.difficulty_index:
                    raise RuntimeError("replay difficulty changed inside sample")
                if fingerprint["shot_type_index"] != metadata.route_id:
                    raise RuntimeError("replay shot type changed inside sample")
                encoded = canonical_fingerprint_bytes(fingerprint)
                digest.update(encoded)
                digest.update(b"\n")
                if args.fingerprint_output is not None:
                    fingerprints.append(fingerprint)
                if first is None:
                    first = fingerprint
                last = fingerprint
                if int(fingerprint["input"]["gui_current"]) != 0:
                    nonzero_gui_epochs += 1
                replay = fingerprint["replay"]
                if replay is not None:
                    replay_frames.append(int(replay["frame_counter"]))

            if args.fingerprint_output is not None:
                write_semantic_trace(args.fingerprint_output, fingerprints)

            report = {
                "schema": "th08-linux-replay-semantic-smoke-v4",
                "runtime": {
                    "path": str(session.identity.path),
                    "size": session.identity.size,
                    "sha256": session.identity.sha256,
                },
                "replay": {
                    "path": str(replay_path),
                    "sha256": metadata.sha256,
                    "route_id": metadata.route_id,
                    "difficulty_index": metadata.difficulty_index,
                    "stage_index": args.stage_index,
                    "stage_rng_seed": stage.rng_seed,
                    "stage_frame_count": stage.frame_count,
                },
                "bootstrap_last_epoch": bootstrap_last_epoch,
                "skipped_gameplay_epochs": skipped_gameplay_epochs,
                "start_manager_frame": args.start_manager_frame,
                "sample_epochs": args.gameplay_epochs,
                "semantic_spine_sha256": digest.hexdigest(),
                "rng_calls_origin": rng_calls_origin,
                "fingerprint_output": (
                    None
                    if args.fingerprint_output is None
                    else str(args.fingerprint_output)
                ),
                "nonzero_gui_input_epochs": nonzero_gui_epochs,
                "replay_frame_range": (
                    [min(replay_frames), max(replay_frames)]
                    if replay_frames
                    else None
                ),
                "first": first,
                "last": last,
                "transitions": transitions,
                "route_duration_limit": None,
                "scope": "bounded replay differential bootstrap; no route claim",
                "collision_control_projection": bool(
                    args.collision_control_projection
                ),
            }
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
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
