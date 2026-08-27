#!/usr/bin/env python3
"""Run the generic synchronous planner on native Easy Sakuya/Remilia."""

from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict
import json
import math
from pathlib import Path
import shutil
import sys
import time
from typing import Mapping

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
from th08_linux.elf import resolve_defined_symbol  # noqa: E402
from th08_linux.planner import (  # noqa: E402
    LinuxHazardCapture,
    LinuxOneEpochPlanner,
    LinuxPlannerConfig,
    NEUTRAL_GAMEPLAY_MASK,
    UNCONTROLLABLE_PLAYER_PHASES,
)
from th08_linux.protocol import BOMB, validate_hard_no_bomb_mask  # noqa: E402
from th08_replay import decode_replay  # noqa: E402
from th08_runtime.sensing import observe_state  # noqa: E402


RESULT_UPDATE_SYMBOL = "_ZN4th0812ResultScreen8OnUpdateEPS0_"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--replay-slot", type=int, default=1)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--threat-horizon", type=int, default=12)
    parser.add_argument("--beam-width", type=int, default=8)
    parser.add_argument("--capture-items", action="store_true")
    parser.add_argument(
        "--retail-life-decrement",
        action="store_true",
        help="diagnostic only: disable the default preserved-life route patch",
    )
    parser.add_argument(
        "--diagnostic-gameplay-epochs",
        type=int,
        help=(
            "explicit short-smoke sample cap; omitted for a full route. "
            "This is an epoch guard, never a wall-clock duration timeout."
        ),
    )
    parser.add_argument(
        "--maximum-bootstrap-epochs",
        type=int,
        default=4096,
        help="title/menu-only fail-closed guard; does not bound gameplay",
    )
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    return parser


def _record_transition(
    records: list[dict[str, object]],
    key_holder: list[tuple[object, ...] | None],
    *,
    key: tuple[object, ...],
    record: dict[str, object],
) -> None:
    if key != key_holder[0]:
        records.append(record)
        key_holder[0] = key


def _timing_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "mean_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(values)
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "count": len(values),
        "mean_ms": sum(values) / len(values),
        "p95_ms": ordered[rank],
        "max_ms": ordered[-1],
    }


def _spell_id(state: Mapping[str, object]) -> int | None:
    spell = state.get("spell")
    if not isinstance(spell, Mapping) or not spell.get("active"):
        return None
    value = spell.get("spell_id")
    return int(value) if value is not None else None


def _compact_plan(
    *,
    request_epoch: int,
    state: Mapping[str, object],
    snapshot: object,
    plan: object,
) -> dict[str, object]:
    decision = plan.decision
    return {
        "request_epoch": request_epoch,
        "frame": snapshot.frame,
        "stage_route_index": int(state["stage_route_index"]),
        "spell_id": _spell_id(state),
        "player_phase": snapshot.player_phase,
        "player_x": snapshot.player_x,
        "player_y": snapshot.player_y,
        "action": plan.action,
        "input_mask": plan.input_mask,
        "bullets": len(snapshot.bullets),
        "lasers": len(snapshot.lasers),
        "enemy_bodies": len(snapshot.enemy_bodies),
        "items": len(snapshot.items),
        "pool_read_ms": snapshot.pool_read_ms,
        "decode_ms": snapshot.decode_ms,
        "planning_ms": plan.planning_ms,
        "min_clearance": decision.min_clearance,
        "immediate_clearance": decision.immediate_clearance,
        "robust_collisions": decision.robust_collisions,
        "robust_min_clearance": decision.robust_min_clearance,
        "terminal_threat_collisions": decision.terminal_threat_collisions,
        "terminal_threat_min_clearance": (
            decision.terminal_threat_min_clearance
        ),
    }


def _runtime_identity_record(session: LinuxGameSession) -> dict[str, object]:
    return {
        "path": str(session.identity.path),
        "size": session.identity.size,
        "sha256": session.identity.sha256,
    }


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.replay_slot <= 15:
        raise ValueError("replay slot must be in [1, 15]")
    if args.maximum_bootstrap_epochs <= 0:
        raise ValueError("maximum bootstrap epoch count must be positive")
    if (
        args.diagnostic_gameplay_epochs is not None
        and args.diagnostic_gameplay_epochs <= 0
    ):
        raise ValueError("diagnostic gameplay epoch cap must be positive")

    executable = args.executable.resolve(strict=True)
    data_directory = args.data_directory.resolve(strict=True)
    if not data_directory.is_dir():
        raise ValueError("runtime data directory is not a directory")
    report_path = args.report.resolve()
    if report_path.exists():
        raise FileExistsError(f"refusing to replace route report: {report_path}")
    replay_path = data_directory / "replay" / f"th8_{args.replay_slot:02d}.rpy"
    full_route = args.diagnostic_gameplay_epochs is None
    if full_route and replay_path.exists():
        raise FileExistsError(f"full-route replay slot must be empty: {replay_path}")
    replay_output = (
        args.replay_output.resolve() if args.replay_output is not None else None
    )
    if replay_output is not None and replay_output.exists():
        raise FileExistsError(f"refusing to replace replay output: {replay_output}")

    config = LinuxPlannerConfig(
        horizon=args.horizon,
        threat_horizon=args.threat_horizon,
        beam_width=args.beam_width,
        capture_items=args.capture_items,
    )
    result_callback = resolve_defined_symbol(executable, RESULT_UPDATE_SYMBOL)
    title_driver = RouteTitleDriver(
        difficulty_index=EASY_DIFFICULTY,
        shot_type_index=SAKUYA_REMILIA_SHOT_TYPE,
    )
    retry_driver = RetryExitDriver()
    result_driver = ReplaySaveDriver(replay_slot=args.replay_slot - 1)
    environment = {"SDL_AUDIODRIVER": "dummy"}
    if args.retail_life_decrement:
        environment["TH08_SOLVER_PRESERVE_LIVES"] = "0"

    session = LinuxGameSession(
        executable=executable,
        data_directory=data_directory,
        expected_sha256=args.expected_sha256,
        display=args.display,
        environment=environment,
        startup_timeout_seconds=args.startup_timeout_seconds,
    )
    transitions: list[dict[str, object]] = []
    transition_key: list[tuple[object, ...] | None] = [None]
    hit_records: list[dict[str, object]] = []
    precursor = deque(maxlen=12)
    action_counts: Counter[str] = Counter()
    stage_hit_counts: Counter[int] = Counter()
    maximum_hazard_counts = {
        "bullets": 0,
        "lasers": 0,
        "enemy_bodies": 0,
        "items": 0,
    }
    minimum_clearances = {
        "immediate": 9999.0,
        "planned": 9999.0,
        "robust": 9999.0,
        "terminal_threat": 9999.0,
    }
    maximum_collision_predictions = {
        "robust": 0,
        "terminal_threat": 0,
    }
    first_action_witnesses: dict[str, dict[str, object]] = {}
    peak_bullet_witness: dict[str, object] | None = None
    timings: dict[str, list[float]] = {
        "pool_read": [],
        "decode": [],
        "planning": [],
        "total_solver": [],
    }
    wire_checks = 0
    planned_epochs = 0
    gameplay_epochs = 0
    bridge_epochs = 0
    hit_count = 0
    bomb_policy_violations = 0
    input_echo_mismatches: list[dict[str, int]] = []
    previous_response: int | None = None
    previous_player_phase: int | None = None
    gameplay_ready_epoch: int | None = None
    first_gameplay_frame: int | None = None
    last_gameplay_frame: int | None = None
    observed_stages: set[int] = set()
    finish_reason = "not-started"
    runtime_identity: dict[str, object] | None = None
    failure: dict[str, str] | None = None
    started = time.perf_counter()

    def attest_request(request: object) -> None:
        nonlocal bomb_policy_violations
        if not request.replay_target_stamped:
            raise RuntimeError("runtime did not stamp the original replay target")
        expected_lives_preserved = not args.retail_life_decrement
        if request.lives_preserved != expected_lives_preserved:
            raise RuntimeError(
                "runtime preserved-life attestation does not match route mode"
            )
        if request.current_input & BOMB or request.previous_input & BOMB:
            bomb_policy_violations += 1
            raise RuntimeError("Bomb bit appeared in native input state")

    try:
        with session:
            runtime_identity = _runtime_identity_record(session)
            for _ in range(args.maximum_bootstrap_epochs):
                request = session.bridge.receive()
                bridge_epochs += 1
                attest_request(request)
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
                    mask = 0
                    action = (
                        "gameplay-ready" if gameplay.ready else "wait-gameplay-load"
                    )
                    session.bridge.respond(mask)
                    previous_response = mask
                    _record_transition(
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
                        initial = observe_state(session.reader)
                        previous_player_phase = int(initial["player"]["phase"])
                        break
                    continue

                snapshot = (
                    capture_title_snapshot(session.reader)
                    if request.current_input == 0
                    else None
                )
                decision = title_driver.decide(
                    snapshot,
                    current_input=request.current_input,
                )
                session.bridge.respond(decision.input_mask)
                previous_response = decision.input_mask
                _record_transition(
                    transitions,
                    transition_key,
                    key=(
                        "title",
                        None if snapshot is None else snapshot.current_screen,
                        None if snapshot is None else snapshot.cursor,
                        decision.action,
                    ),
                    record={
                        "epoch": request.epoch,
                        "phase": "title",
                        "screen": (
                            None if snapshot is None else snapshot.current_screen
                        ),
                        "cursor": None if snapshot is None else snapshot.cursor,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    },
                )
            else:
                raise RuntimeError(
                    "title bootstrap exceeded its menu-only guard of "
                    f"{args.maximum_bootstrap_epochs} epochs"
                )

            capture = LinuxHazardCapture(
                session.reader,
                capture_items=config.capture_items,
            )
            planner = LinuxOneEpochPlanner(config=config)
            finish_reason = "gameplay-active"
            while True:
                request = session.bridge.receive()
                bridge_epochs += 1
                attest_request(request)
                gameplay = capture_gameplay_bootstrap(session.reader)
                validate_request_memory_witness(
                    request,
                    session.reader,
                    verify_rng=(
                        not gameplay.registered or gameplay.loading_state == 0
                    ),
                )
                wire_checks += 1
                if (
                    previous_response is not None
                    and request.current_input != previous_response
                ):
                    mismatch = {
                        "epoch": request.epoch,
                        "expected": previous_response,
                        "observed": request.current_input,
                    }
                    input_echo_mismatches.append(mismatch)
                    raise RuntimeError(
                        "native input did not echo the preceding complete mask: "
                        f"{mismatch}"
                    )

                if full_route and replay_path.is_file():
                    session.bridge.respond(0)
                    previous_response = 0
                    finish_reason = "replay-saved"
                    break

                state = observe_state(session.reader)
                state_active = bool(state["gameplay_active"])
                result = None
                retry = None
                if not state_active:
                    result = capture_result_screen(
                        session.reader,
                        update_callback=result_callback,
                    )
                    retry = capture_retry_menu(session.reader)

                if state_active and gameplay.ready:
                    if int(state["difficulty_index"]) != EASY_DIFFICULTY:
                        raise RuntimeError("live route left Easy difficulty")
                    if int(state["route_id"]) != SAKUYA_REMILIA_SHOT_TYPE:
                        raise RuntimeError("live route left Sakuya/Remilia")
                    frame = int(state["enemy_manager_frame"])
                    stage = int(state["stage_route_index"])
                    phase = int(state["player"]["phase"])
                    first_gameplay_frame = (
                        frame if first_gameplay_frame is None else first_gameplay_frame
                    )
                    last_gameplay_frame = frame
                    observed_stages.add(stage)
                    gameplay_epochs += 1
                    if phase == 2 and previous_player_phase != 2:
                        hit_count += 1
                        stage_hit_counts[stage] += 1
                        hit_records.append(
                            {
                                "hit_index": hit_count,
                                "request_epoch": request.epoch,
                                "frame": frame,
                                "stage_route_index": stage,
                                "spell_id": _spell_id(state),
                                "player_x": float(state["player"]["x"]),
                                "player_y": float(state["player"]["y"]),
                                "precursor": list(precursor),
                            }
                        )
                    previous_player_phase = phase

                    if phase in UNCONTROLLABLE_PLAYER_PHASES:
                        mask = NEUTRAL_GAMEPLAY_MASK
                        action = "stay"
                        reason = "player-uncontrollable"
                    else:
                        snapshot = capture.capture(state)
                        plan = planner.choose(
                            snapshot,
                            previous_mask=request.current_input,
                        )
                        mask = plan.input_mask
                        action = plan.action
                        reason = plan.reason
                        compact = _compact_plan(
                            request_epoch=request.epoch,
                            state=state,
                            snapshot=snapshot,
                            plan=plan,
                        )
                        precursor.append(compact)
                        first_action_witnesses.setdefault(plan.action, compact)
                        counts = {
                            "bullets": len(snapshot.bullets),
                            "lasers": len(snapshot.lasers),
                            "enemy_bodies": len(snapshot.enemy_bodies),
                            "items": len(snapshot.items),
                        }
                        for name, count in counts.items():
                            maximum_hazard_counts[name] = max(
                                maximum_hazard_counts[name], count
                            )
                        if (
                            peak_bullet_witness is None
                            or counts["bullets"]
                            > int(peak_bullet_witness["bullets"])
                        ):
                            peak_bullet_witness = compact
                        decision = plan.decision
                        minimum_clearances["immediate"] = min(
                            minimum_clearances["immediate"],
                            decision.immediate_clearance,
                        )
                        minimum_clearances["planned"] = min(
                            minimum_clearances["planned"],
                            decision.min_clearance,
                        )
                        minimum_clearances["robust"] = min(
                            minimum_clearances["robust"],
                            decision.robust_min_clearance,
                        )
                        minimum_clearances["terminal_threat"] = min(
                            minimum_clearances["terminal_threat"],
                            decision.terminal_threat_min_clearance,
                        )
                        maximum_collision_predictions["robust"] = max(
                            maximum_collision_predictions["robust"],
                            decision.robust_collisions,
                        )
                        maximum_collision_predictions["terminal_threat"] = max(
                            maximum_collision_predictions["terminal_threat"],
                            decision.terminal_threat_collisions,
                        )
                        timings["pool_read"].append(snapshot.pool_read_ms)
                        timings["decode"].append(snapshot.decode_ms)
                        timings["planning"].append(plan.planning_ms)
                        timings["total_solver"].append(
                            snapshot.pool_read_ms
                            + snapshot.decode_ms
                            + plan.planning_ms
                        )
                        planned_epochs += 1
                    validate_hard_no_bomb_mask(mask)
                    action_counts[action] += 1
                    session.bridge.respond(mask)
                    previous_response = mask
                    _record_transition(
                        transitions,
                        transition_key,
                        key=("gameplay", stage, phase, reason),
                        record={
                            "epoch": request.epoch,
                            "phase": "gameplay",
                            "frame": frame,
                            "stage_route_index": stage,
                            "player_phase": phase,
                            "action_reason": reason,
                        },
                    )
                    if (
                        args.diagnostic_gameplay_epochs is not None
                        and gameplay_epochs >= args.diagnostic_gameplay_epochs
                    ):
                        finish_reason = "diagnostic-gameplay-epoch-cap"
                        break
                    continue

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
                        "supervisor_state": capture_supervisor_state(
                            session.reader
                        ),
                        "result_state": result.state,
                        "frame_timer": result.frame_timer,
                        "cursor": result.cursor,
                        "selected_character": result.selected_character,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    }
                elif retry is not None and retry.showing:
                    decision = retry_driver.decide(
                        retry,
                        current_input=request.current_input,
                    )
                    key = ("retry", retry.state, decision.action)
                    record = {
                        "epoch": request.epoch,
                        "phase": "retry",
                        "retry_state": retry.state,
                        "frame_timer": retry.frame_timer,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    }
                else:
                    decision = ResultDecision(
                        NEUTRAL_GAMEPLAY_MASK,
                        (
                            "wait-stage-load"
                            if gameplay.registered
                            else "advance-ending-or-result-transition"
                        ),
                    )
                    key = (
                        "transition",
                        gameplay.registered,
                        gameplay.loading_state,
                        gameplay.stage_route_index,
                        decision.action,
                    )
                    record = {
                        "epoch": request.epoch,
                        "phase": "gameplay-or-result-transition",
                        "gameplay_registered": gameplay.registered,
                        "loading_state": gameplay.loading_state,
                        "stage_route_index": gameplay.stage_route_index,
                        "action": decision.action,
                        "input_mask": decision.input_mask,
                    }
                validate_hard_no_bomb_mask(decision.input_mask)
                session.bridge.respond(decision.input_mask)
                previous_response = decision.input_mask
                _record_transition(
                    transitions,
                    transition_key,
                    key=key,
                    record=record,
                )
    except BaseException as error:
        finish_reason = "error"
        failure = {"type": type(error).__name__, "message": str(error)}

    replay_record = None
    bomb_frames: list[int] = []
    if finish_reason == "replay-saved":
        metadata, _decoded = decode_replay(replay_path)
        if (
            metadata.difficulty_index != EASY_DIFFICULTY
            or metadata.route_id != SAKUYA_REMILIA_SHOT_TYPE
        ):
            failure = {
                "type": "RuntimeError",
                "message": (
                    "saved replay identity mismatch: "
                    f"difficulty={metadata.difficulty_index} "
                    f"route={metadata.route_id}"
                ),
            }
            finish_reason = "error"
        bomb_frames = [
            frame
            for stage in metadata.stages
            for frame in stage.bomb_press_frames
        ]
        if bomb_frames:
            bomb_policy_violations += len(bomb_frames)
            failure = {
                "type": "RuntimeError",
                "message": f"saved replay contains Bomb presses: {bomb_frames[:8]}",
            }
            finish_reason = "error"
        replay_record = asdict(metadata)
        if replay_output is not None and finish_reason == "replay-saved":
            replay_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(replay_path, replay_output)

    report = {
        "schema": "th08-linux-easy-lockstep-route-v1",
        "runtime": runtime_identity,
        "target": {
            "difficulty_index": EASY_DIFFICULTY,
            "shot_type_index": SAKUYA_REMILIA_SHOT_TYPE,
            "hard_no_bomb": True,
            "lives_preserved": not args.retail_life_decrement,
        },
        "planner": asdict(config),
        "contract": {
            "snapshot_lag_frames": 0,
            "control_delay_frames": [0],
            "action_hold_frames": 1,
            "future_birth_authority": False,
            "time_scale": "root constant-horizon assumption, replanned each epoch",
            "gameplay_duration_limit": None,
            "diagnostic_gameplay_epoch_cap": args.diagnostic_gameplay_epochs,
        },
        "finish_reason": finish_reason,
        "failure": failure,
        "elapsed_wall_seconds": time.perf_counter() - started,
        "bridge_epochs": bridge_epochs,
        "wire_memory_checks": wire_checks,
        "gameplay_ready_epoch": gameplay_ready_epoch,
        "planned_epochs": planned_epochs,
        "gameplay_epochs": gameplay_epochs,
        "first_gameplay_frame": first_gameplay_frame,
        "last_gameplay_frame": last_gameplay_frame,
        "observed_stage_route_indices": sorted(observed_stages),
        "hit_count": hit_count,
        "stage_hit_counts": {
            str(stage): count for stage, count in sorted(stage_hit_counts.items())
        },
        "bomb_policy_violations": bomb_policy_violations,
        "input_echo_mismatches": input_echo_mismatches,
        "action_counts": dict(sorted(action_counts.items())),
        "maximum_hazard_counts": maximum_hazard_counts,
        "minimum_clearances": minimum_clearances,
        "maximum_collision_predictions": maximum_collision_predictions,
        "first_action_witnesses": {
            name: first_action_witnesses[name]
            for name in sorted(first_action_witnesses)
        },
        "peak_bullet_witness": peak_bullet_witness,
        "timings": {
            name: _timing_summary(values) for name, values in timings.items()
        },
        "hits": hit_records,
        "transitions": transitions,
        "replay": replay_record,
        "replay_source": str(replay_path) if replay_record is not None else None,
        "replay_output": str(replay_output) if replay_output is not None else None,
        "replay_bomb_frames": bomb_frames,
        "route_completion_observed": bool(
            finish_reason == "replay-saved"
            and not args.retail_life_decrement
            and 7 in observed_stages
        ),
        "result_update_symbol": RESULT_UPDATE_SYMBOL,
        "result_update_address": result_callback,
        "runtime_log_tail": session.runtime_log_tail if failure is not None else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
