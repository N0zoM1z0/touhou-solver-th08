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
    MANAGER_FRAME_TRANSITION_SAME,
    ReplayTitleDriver,
    canonical_fingerprint_bytes,
    capture_gameplay_bootstrap,
    capture_semantic_spine,
    capture_title_snapshot,
    classify_manager_frame_transition,
    enrich_with_collision_control_projection,
    enrich_with_effect_lifecycle_summary,
    partial_semantic_trace_path,
    replay_stage_binding_mismatch,
    replay_stage_terminal_reason,
    validate_request_memory_witness,
    write_semantic_trace,
)
from th08_replay import decode_replay  # noqa: E402
from th08_runtime.game_state import ADDR_ENEMY_MANAGER_FRAME  # noqa: E402
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
    parser.add_argument(
        "--stop-at-stage-terminal",
        action="store_true",
        help=(
            "treat gameplay-inactive replay-binding teardown as successful "
            "completion before the epoch guard"
        ),
    )
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


def run(args: argparse.Namespace) -> int:
    if args.gameplay_epochs <= 0:
        raise ValueError("gameplay fingerprint epoch count must be positive")
    if args.start_manager_frame <= 0:
        raise ValueError("starting manager frame must be positive")
    if args.collision_control_projection and args.effect_lifecycle_summary:
        raise ValueError(
            "collision/control and effect-summary projections are mutually "
            "exclusive"
        )
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
    fingerprints: list[dict[str, object]] = []
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
            rng_calls_origin = None
            skipped_gameplay_epochs = 0
            same_manager_input_epochs = 0
            manager_forward_jump_epochs = 0
            manager_frames_skipped = 0
            inactive_gameplay_epochs = 0
            previous_manager_frame = None
            replay_frame_origin = None
            sample_epochs = 0
            terminal_observation = None
            lives_preserved_attested = None
            for relative_epoch in range(1, args.gameplay_epochs + 1):
                while True:
                    request = session.bridge.receive()
                    request_lives_preserved = request.lives_preserved
                    if lives_preserved_attested is None:
                        lives_preserved_attested = request_lives_preserved
                    elif (
                        lives_preserved_attested
                        != request_lives_preserved
                    ):
                        session.bridge.respond(0)
                        raise RuntimeError(
                            "runtime no-life-decrement attestation changed "
                            "inside one bridge session"
                        )
                    if (
                        args.stop_at_stage_terminal
                        and not request_lives_preserved
                    ):
                        session.bridge.respond(0)
                        raise RuntimeError(
                            "stage-terminal authority requires a runtime "
                            "that attests no-life-decrement parity"
                        )
                    if relative_epoch == 1:
                        seek_manager_frame = session.reader.u32(
                            ADDR_ENEMY_MANAGER_FRAME
                        )
                        if seek_manager_frame < args.start_manager_frame:
                            validate_request_memory_witness(
                                request,
                                session.reader,
                            )
                            session.bridge.respond(0)
                            skipped_gameplay_epochs += 1
                            continue
                        if seek_manager_frame > args.start_manager_frame:
                            validate_request_memory_witness(
                                request,
                                session.reader,
                            )
                            session.bridge.respond(0)
                            raise RuntimeError(
                                "replay seek skipped the requested manager "
                                "frame: "
                                f"requested={args.start_manager_frame} "
                                f"observed={seek_manager_frame}"
                            )
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
                    elif args.effect_lifecycle_summary:
                        fingerprint = enrich_with_effect_lifecycle_summary(
                            session.reader,
                            fingerprint,
                        )
                    session.bridge.respond(0)
                    break
                binding_mismatch = replay_stage_binding_mismatch(
                    fingerprint,
                    difficulty_index=metadata.difficulty_index,
                    shot_type_index=metadata.route_id,
                    stage_index=args.stage_index,
                )
                terminal_reason = replay_stage_terminal_reason(
                    fingerprint,
                    difficulty_index=metadata.difficulty_index,
                    shot_type_index=metadata.route_id,
                    stage_index=args.stage_index,
                )
                if terminal_reason is not None:
                    if not args.stop_at_stage_terminal:
                        raise RuntimeError(
                            "replay stage binding ended inside fixed sample: "
                            f"{terminal_reason}"
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
                        "gameplay_active": fingerprint.get(
                            "gameplay_active"
                        ),
                        "reason": terminal_reason,
                    }
                    break
                if binding_mismatch is not None:
                    raise RuntimeError(
                        "replay stage binding changed while still active: "
                        f"{binding_mismatch}"
                    )
                manager_frame = int(fingerprint["manager_frame"])
                if previous_manager_frame is None:
                    if manager_frame != args.start_manager_frame:
                        raise RuntimeError(
                            "replay manager-frame seek changed during root "
                            f"capture: requested={args.start_manager_frame} "
                            f"observed={manager_frame}"
                        )
                    manager_frame_delta = 0
                else:
                    try:
                        manager_relation = classify_manager_frame_transition(
                            previous=previous_manager_frame,
                            observed=manager_frame,
                        )
                    except ValueError as error:
                        raise RuntimeError(
                            "replay manager-frame transition changed across "
                            "logical input epochs: "
                            f"previous={previous_manager_frame} "
                            f"observed={manager_frame}"
                        ) from error
                    manager_frame_delta = (
                        manager_frame - previous_manager_frame
                    )
                    if manager_relation == MANAGER_FRAME_TRANSITION_SAME:
                        same_manager_input_epochs += 1
                    elif manager_frame_delta > 1:
                        manager_forward_jump_epochs += 1
                        manager_frames_skipped += manager_frame_delta - 1
                previous_manager_frame = manager_frame
                trace_locators = fingerprint["trace_locators"]
                assert isinstance(trace_locators, dict)
                trace_locators["manager_frame_delta_from_previous_root"] = (
                    manager_frame_delta
                )
                if rng_calls_origin is None:
                    rng_calls_origin = int(trace_locators["rng_calls_absolute"])
                if not fingerprint["gameplay_active"]:
                    inactive_gameplay_epochs += 1
                replay = fingerprint["replay"]
                assert isinstance(replay, dict)
                replay_frame = int(replay["frame_counter"])
                if replay_frame_origin is None:
                    replay_frame_origin = replay_frame
                expected_replay_frame = (
                    replay_frame_origin + relative_epoch - 1
                )
                if replay_frame != expected_replay_frame:
                    raise RuntimeError(
                        "replay logical input clock changed: "
                        f"expected={expected_replay_frame} "
                        f"observed={replay_frame}"
                    )
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
                replay_frames.append(replay_frame)
                sample_epochs += 1

            if args.stop_at_stage_terminal and terminal_observation is None:
                raise RuntimeError(
                    "replay stage terminal was not reached inside the "
                    f"{args.gameplay_epochs}-epoch guard"
                )
            if sample_epochs == 0:
                raise RuntimeError("replay sample contains no bound input epoch")

            if args.fingerprint_output is not None:
                write_semantic_trace(args.fingerprint_output, fingerprints)

            report = {
                "schema": "th08-linux-replay-semantic-smoke-v7",
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
                    "stage_stored_input_word_count": (
                        stage.stored_input_word_count
                    ),
                },
                "bootstrap_last_epoch": bootstrap_last_epoch,
                "skipped_gameplay_epochs": skipped_gameplay_epochs,
                "same_manager_input_epochs": same_manager_input_epochs,
                "manager_forward_jump_epochs": manager_forward_jump_epochs,
                "manager_frames_skipped": manager_frames_skipped,
                "inactive_gameplay_epochs": inactive_gameplay_epochs,
                "start_manager_frame": args.start_manager_frame,
                "start_replay_frame": replay_frame_origin,
                "sample_epochs": sample_epochs,
                "maximum_sample_epochs": args.gameplay_epochs,
                "stop_at_stage_terminal": bool(args.stop_at_stage_terminal),
                "lives_preserved_attested": lives_preserved_attested,
                "stage_terminal": terminal_observation,
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
                "effect_lifecycle_summary": bool(
                    args.effect_lifecycle_summary
                ),
            }
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except BaseException:
        if (
            args.fingerprint_output is not None
            and fingerprints
            and not args.fingerprint_output.exists()
        ):
            partial_path = partial_semantic_trace_path(
                args.fingerprint_output
            )
            if not partial_path.exists():
                write_semantic_trace(partial_path, fingerprints)
                print(
                    f"partial semantic trace: {partial_path}",
                    file=sys.stderr,
                )
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
