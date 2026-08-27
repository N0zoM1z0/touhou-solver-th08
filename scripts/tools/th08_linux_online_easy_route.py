#!/usr/bin/env python3
"""Continuously running 60 Hz native-Linux Easy Route-2 solver.

The game never waits for this process.  Every gameplay response is tied to the
immediately following native input epoch; stale capture or planning work is
abandoned and the game keeps its complete held mask.
"""

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

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_linux.elf import resolve_defined_symbol  # noqa: E402
from th08_linux.online_session import LinuxOnlineGameSession  # noqa: E402
from th08_linux.online_services import (  # noqa: E402
    LinuxOnlineFutureGlobalService,
    LinuxOnlineServiceConfig,
)
from th08_linux.planner import (  # noqa: E402
    LinuxOnlineHazardCapture,
    LinuxOneEpochPlanner,
    LinuxPlannerConfig,
    NEUTRAL_GAMEPLAY_MASK,
)
from th08_linux.protocol import validate_hard_no_bomb_mask  # noqa: E402
from th08_linux.result import (  # noqa: E402
    ReplaySaveDriver,
    ResultDecision,
    RetryExitDriver,
    capture_result_screen,
    capture_retry_menu,
)
from th08_linux.title import (  # noqa: E402
    EASY_DIFFICULTY,
    SAKUYA_REMILIA_SHOT_TYPE,
    RouteTitleDriver,
    capture_gameplay_bootstrap,
    capture_title_snapshot,
)
from th08_live.movement import BOMB  # noqa: E402
from th08_replay import decode_replay  # noqa: E402
from th08_runtime.sensing import observe_state  # noqa: E402


RESULT_UPDATE_SYMBOL = "_ZN4th0812ResultScreen8OnUpdateEPv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--decoded-ecl-directory", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--replay-slot", type=int, default=15)
    # The foreground tier must race one physical input epoch. The retained
    # native route measured 8/12/8; deeper reachability belongs to the rolling
    # future/global worker, not this deadline path.
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--threat-horizon", type=int, default=12)
    parser.add_argument("--beam-width", type=int, default=8)
    parser.add_argument("--capture-items", action="store_true")
    parser.add_argument(
        "--retail-life-decrement",
        action="store_true",
        help="diagnostic only; default preserves lives while counting hits",
    )
    parser.add_argument(
        "--diagnostic-gameplay-epochs",
        type=int,
        help="explicit sample cap; omitted for a complete route",
    )
    parser.add_argument("--maximum-bootstrap-epochs", type=int, default=4096)
    parser.add_argument("--startup-timeout-seconds", type=float, default=120.0)
    return parser


def _spell_id(state: Mapping[str, object]) -> int | None:
    spell = state.get("spell")
    if not isinstance(spell, Mapping) or not bool(spell.get("active")):
        return None
    value = spell.get("spell_id")
    return int(value) if value is not None else None


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


def _request_record(request: object) -> dict[str, int | float]:
    return {
        "source_epoch": request.source_epoch,
        "target_epoch": request.target_epoch,
        "publication_age_ms": request.publication_age_ms(),
        "deadline_misses": request.deadline_misses,
        "late_responses": request.late_responses,
        "dropped_requests": request.dropped_requests,
    }


def _respond_if_current(
    session: LinuxOnlineGameSession,
    request: object,
    mask: int,
) -> bool:
    validate_hard_no_bomb_mask(mask)
    native_epoch = session.reader.u32(session.input_epoch_address)
    if native_epoch != (request.source_epoch & 0xFFFFFFFF):
        session.bridge.abandon()
        return False
    return session.bridge.respond(mask)


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.replay_slot <= 15:
        raise ValueError("replay slot must be in [1, 15]")
    if args.maximum_bootstrap_epochs <= 0:
        raise ValueError("maximum bootstrap epochs must be positive")
    if (
        args.diagnostic_gameplay_epochs is not None
        and args.diagnostic_gameplay_epochs <= 0
    ):
        raise ValueError("diagnostic gameplay epochs must be positive")

    executable = args.executable.resolve(strict=True)
    data_directory = args.data_directory.resolve(strict=True)
    decoded_ecl_directory = args.decoded_ecl_directory.resolve(strict=True)
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

    planner_config = LinuxPlannerConfig(
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
    result_driver = ReplaySaveDriver(replay_slot=args.replay_slot - 1)
    retry_driver = RetryExitDriver()
    environment = {"SDL_AUDIODRIVER": "dummy"}
    if args.retail_life_decrement:
        environment["TH08_SOLVER_PRESERVE_LIVES"] = "0"

    session = LinuxOnlineGameSession(
        executable=executable,
        data_directory=data_directory,
        expected_sha256=args.expected_sha256,
        display=args.display,
        environment=environment,
        startup_timeout_seconds=args.startup_timeout_seconds,
    )
    started = time.perf_counter()
    finish_reason = "not-started"
    failure: dict[str, str] | None = None
    runtime_record: dict[str, object] | None = None
    service_metrics: dict[str, object] = {}
    action_counts: Counter[str] = Counter()
    stage_hit_counts: Counter[int] = Counter()
    observed_stages: set[int] = set()
    hit_records: list[dict[str, object]] = []
    authority_witnesses: list[dict[str, object]] = []
    precursor: deque[dict[str, object]] = deque(maxlen=12)
    timings: dict[str, list[float]] = {
        "publication_age": [],
        "pool_read": [],
        "decode": [],
        "planning": [],
        "decision_total": [],
    }
    bridge_publications = 0
    gameplay_epochs = 0
    coherent_gameplay_captures = 0
    stale_capture_abandons = 0
    stale_plan_abandons = 0
    response_queue_drops = 0
    response_packets_sent = 0
    bridge_drained_publications = 0
    bridge_observed_epoch_gaps = 0
    hit_count = 0
    previous_player_phase: int | None = None
    first_request_counters: dict[str, int] | None = None
    last_request_counters: dict[str, int] | None = None

    def attest(request: object) -> None:
        nonlocal first_request_counters, last_request_counters
        if not request.replay_target_stamped:
            raise RuntimeError("runtime did not stamp the original replay target")
        if request.lives_preserved != (not args.retail_life_decrement):
            raise RuntimeError("runtime life-preservation attestation mismatch")
        if request.current_input & BOMB or request.previous_input & BOMB:
            raise RuntimeError("Bomb bit appeared in native input state")
        counters = {
            "deadline_misses": request.deadline_misses,
            "late_responses": request.late_responses,
            "dropped_requests": request.dropped_requests,
        }
        if first_request_counters is None:
            first_request_counters = counters
        last_request_counters = counters

    try:
        with session:
            runtime_record = {
                "path": str(session.identity.path),
                "size": session.identity.size,
                "sha256": session.identity.sha256,
                "input_epoch_address": session.input_epoch_address,
            }
            for _ in range(args.maximum_bootstrap_epochs):
                request = session.bridge.receive()
                bridge_publications += 1
                attest(request)
                epoch_before = session.reader.u32(session.input_epoch_address)
                gameplay = capture_gameplay_bootstrap(session.reader)
                if gameplay.registered:
                    mask = 0
                    sent = _respond_if_current(session, request, mask)
                    response_packets_sent += int(sent)
                    response_queue_drops += int(not sent and epoch_before == request.source_epoch)
                    if gameplay.ready:
                        finish_reason = "gameplay-active"
                        break
                    continue
                title = capture_title_snapshot(session.reader)
                decision = title_driver.decide(
                    title,
                    current_input=request.current_input,
                )
                sent = _respond_if_current(
                    session,
                    request,
                    decision.input_mask,
                )
                response_packets_sent += int(sent)
            else:
                raise RuntimeError("title bootstrap exceeded its epoch guard")

            capture = LinuxOnlineHazardCapture(
                session.reader,
                input_epoch_address=session.input_epoch_address,
                capture_items=planner_config.capture_items,
            )
            planner = LinuxOneEpochPlanner(config=planner_config)
            service = LinuxOnlineFutureGlobalService(
                reader=session.reader,
                input_epoch_address=session.input_epoch_address,
                decoded_ecl_directory=decoded_ecl_directory,
                route_id=SAKUYA_REMILIA_SHOT_TYPE,
                difficulty_index=EASY_DIFFICULTY,
                config=LinuxOnlineServiceConfig(
                    local_future_horizon_frames=(
                        planner_config.threat_horizon
                    ),
                ),
            )
            try:
                while True:
                    request = session.bridge.receive()
                    bridge_publications += 1
                    attest(request)
                    timings["publication_age"].append(
                        request.publication_age_ms()
                    )
                    if full_route and replay_path.is_file():
                        _respond_if_current(session, request, 0)
                        finish_reason = "replay-saved"
                        break

                    gameplay = capture_gameplay_bootstrap(session.reader)
                    if gameplay.ready:
                        decision_started = time.perf_counter()
                        try:
                            state, snapshot = capture.capture_transaction(
                                request,
                                observe=lambda: observe_state(session.reader),
                            )
                        except RuntimeError as error:
                            if "epoch" not in str(error) and "root changed" not in str(error):
                                raise
                            session.bridge.abandon()
                            stale_capture_abandons += 1
                            continue
                        coherent_gameplay_captures += 1
                        if int(state["difficulty_index"]) != EASY_DIFFICULTY:
                            raise RuntimeError("online route left Easy difficulty")
                        if int(state["route_id"]) != SAKUYA_REMILIA_SHOT_TYPE:
                            raise RuntimeError("online route left Sakuya/Remilia")
                        stage = int(state["stage_route_index"])
                        observed_stages.add(stage)
                        gameplay_epochs += 1
                        player = state["player"]
                        if not isinstance(player, Mapping):
                            raise RuntimeError("online state omitted player")
                        phase = int(player["phase"])
                        if phase == 2 and previous_player_phase != 2:
                            hit_count += 1
                            stage_hit_counts[stage] += 1
                            hit_records.append(
                                {
                                    "hit_index": hit_count,
                                    "source_epoch": request.source_epoch,
                                    "frame": snapshot.frame,
                                    "stage_route_index": stage,
                                    "spell_id": _spell_id(state),
                                    "player_x": snapshot.player_x,
                                    "player_y": snapshot.player_y,
                                    "precursor": list(precursor),
                                }
                            )
                        previous_player_phase = phase

                        update = service.update(
                            snapshot,
                            state,
                            source_epoch=request.source_epoch,
                            current_input=request.current_input,
                        )
                        plan = planner.choose(
                            snapshot,
                            previous_mask=request.current_input,
                            guidance=update.guidance,
                        )
                        validate_hard_no_bomb_mask(plan.input_mask)
                        if (
                            session.reader.u32(session.input_epoch_address)
                            != (request.source_epoch & 0xFFFFFFFF)
                        ):
                            session.bridge.abandon()
                            stale_plan_abandons += 1
                            continue
                        sent = session.bridge.respond(plan.input_mask)
                        response_packets_sent += int(sent)
                        response_queue_drops += int(not sent)
                        action_counts[plan.action] += 1
                        record = {
                            "source_epoch": request.source_epoch,
                            "target_epoch": request.target_epoch,
                            "frame": snapshot.frame,
                            "stage_route_index": stage,
                            "spell_id": _spell_id(state),
                            "action": plan.action,
                            "mask": plan.input_mask,
                            "reason": plan.reason,
                            "global_status": update.authority.status,
                            "global_reasons": list(update.authority.reasons),
                            "global_constraint": (
                                update.authority.global_constraint_applied
                            ),
                            "future_local": (
                                update.authority
                                .future_projection_applied_locally
                            ),
                            "scale_status": update.scale_status,
                            "future_status": update.future_status,
                            "corridor_status": update.corridor_status,
                            "clock_status": update.clock_status,
                            "clock_certified": update.clock_certified,
                            "clock_generation": update.clock_generation,
                            "policy_source_frame": (
                                update.authority.solution_source_frame
                            ),
                            "policy_source_input_epoch": (
                                update.authority.solution_source_input_epoch
                            ),
                        }
                        precursor.append(record)
                        if (
                            update.authority.global_constraint_applied
                            and len(authority_witnesses) < 16
                        ):
                            authority_witnesses.append(record)
                        timings["pool_read"].append(snapshot.pool_read_ms)
                        timings["decode"].append(snapshot.decode_ms)
                        timings["planning"].append(plan.planning_ms)
                        timings["decision_total"].append(
                            (time.perf_counter() - decision_started) * 1000.0
                        )
                        if (
                            args.diagnostic_gameplay_epochs is not None
                            and gameplay_epochs
                            >= args.diagnostic_gameplay_epochs
                        ):
                            finish_reason = "diagnostic-gameplay-epoch-cap"
                            break
                        continue

                    epoch_before = session.reader.u32(session.input_epoch_address)
                    result = capture_result_screen(
                        session.reader,
                        update_callback=result_callback,
                    )
                    retry = capture_retry_menu(session.reader)
                    if result is not None:
                        decision = result_driver.decide(
                            result,
                            current_input=request.current_input,
                        )
                    elif retry is not None and retry.showing:
                        decision = retry_driver.decide(
                            retry,
                            current_input=request.current_input,
                        )
                    else:
                        decision = ResultDecision(
                            NEUTRAL_GAMEPLAY_MASK,
                            "wait-stage-load-or-result-transition",
                        )
                    sent = _respond_if_current(
                        session,
                        request,
                        decision.input_mask,
                    )
                    response_packets_sent += int(sent)
                    response_queue_drops += int(
                        not sent and epoch_before == request.source_epoch
                    )
            finally:
                service_metrics = service.metrics()
                service.close()
            bridge_drained_publications = session.bridge.drained_publications
            bridge_observed_epoch_gaps = session.bridge.observed_epoch_gaps
    except BaseException as error:
        finish_reason = "error"
        failure = {"type": type(error).__name__, "message": str(error)}

    replay_record = None
    replay_bomb_frames: list[int] = []
    if finish_reason == "replay-saved":
        metadata, _decoded = decode_replay(replay_path)
        replay_bomb_frames = [
            frame
            for stage in metadata.stages
            for frame in stage.bomb_press_frames
        ]
        if replay_bomb_frames:
            failure = {
                "type": "RuntimeError",
                "message": f"saved replay contains Bomb: {replay_bomb_frames[:8]}",
            }
            finish_reason = "error"
        replay_record = asdict(metadata)
        if replay_output is not None and failure is None:
            replay_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(replay_path, replay_output)

    counter_delta = {
        key: (
            int(last_request_counters[key]) - int(first_request_counters[key])
            if first_request_counters is not None
            and last_request_counters is not None
            else 0
        )
        for key in ("deadline_misses", "late_responses", "dropped_requests")
    }
    report = {
        "schema": "th08-linux-online-easy-route-v1",
        "runtime": runtime_record,
        "target": {
            "difficulty_index": EASY_DIFFICULTY,
            "route_id": SAKUYA_REMILIA_SHOT_TYPE,
            "hard_no_bomb": True,
            "lives_preserved": not args.retail_life_decrement,
        },
        "contract": {
            "game_waits_for_solver": False,
            "solver_time_removed_from_game_clock": False,
            "publication": "post-update source epoch",
            "response": "exact next input epoch or discard",
            "fallback": (
                "connected deadline miss holds complete input mask; "
                "disconnect/failure selects neutral Shot+Focus"
            ),
            "control_delay_frames": [0],
            "action_hold_frames": 1,
            "held_fallback_horizon_certified": False,
            "global_future_action_authority": "exact-version fail-closed",
        },
        "planner": asdict(planner_config),
        "finish_reason": finish_reason,
        "failure": failure,
        "elapsed_wall_seconds": time.perf_counter() - started,
        "bridge_publications": bridge_publications,
        "bridge_drained_publications": (
            bridge_drained_publications
        ),
        "bridge_observed_epoch_gaps": (
            bridge_observed_epoch_gaps
        ),
        "runtime_counter_delta": counter_delta,
        "response_packets_sent": response_packets_sent,
        "response_queue_drops": response_queue_drops,
        "coherent_gameplay_captures": coherent_gameplay_captures,
        "stale_capture_abandons": stale_capture_abandons,
        "stale_plan_abandons": stale_plan_abandons,
        "gameplay_epochs": gameplay_epochs,
        "hit_count": hit_count,
        "stage_hit_counts": {
            str(stage): count for stage, count in sorted(stage_hit_counts.items())
        },
        "observed_stage_route_indices": sorted(observed_stages),
        "action_counts": dict(sorted(action_counts.items())),
        "future_global_service": service_metrics,
        "online_authority_integration_observed": bool(authority_witnesses),
        "authority_witnesses": authority_witnesses,
        "timings": {
            name: _timing_summary(values) for name, values in timings.items()
        },
        "hits": hit_records,
        "replay": replay_record,
        "replay_source": str(replay_path) if replay_record is not None else None,
        "replay_output": str(replay_output) if replay_output is not None else None,
        "replay_bomb_frames": replay_bomb_frames,
        "route_completion_observed": bool(
            finish_reason == "replay-saved"
            and not args.retail_life_decrement
            and 7 in observed_stages
            and not replay_bomb_frames
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
