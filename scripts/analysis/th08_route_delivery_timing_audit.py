#!/usr/bin/env python3
"""Audit TH08 hit timing, sensor epochs, and global-planner delivery gates.

The route trace is intentionally too large to retain in Git.  This tool
streams it once and emits a compact ledger that keeps the associations needed
to distinguish three different contracts:

* source physical collision geometry at the captured epoch;
* uncertainty introduced when the bullet-pool read spans manager frames; and
* whether a global corridor job was actually submitted and authority-eligible.

The hit windows are observational.  They do not claim that the decision row
that first observed a hit caused that hit, or that linear projection is exact
for transformed bullets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from analysis.th08_trial_report import STAGE_ROUTE_LABELS
from th08_live.models import BULLET_LIFECYCLE_TRACE_SCHEMAS
from th08_live.movement import (
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
    PLAYER_LETHAL_HALF_HEIGHT,
    PLAYER_LETHAL_HALF_WIDTH,
)


REPORT_SCHEMA = "th08-route-delivery-timing-audit-v1"
DEFAULT_HIT_WINDOW_DECISIONS = 4
TIMING_COMPONENTS = (
    "local_plan_initial",
    "issue_enemy_recertificate",
    "local_shared_laser_projection",
    "local_certificate_total",
    "local_certificate_geometry",
    "issue_certificate_total",
    "issue_path_to_input",
    "decode_bullets",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median": _percentile(values, 0.5),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _bool_label(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def _counter_dict(counter: Counter[object]) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(counter.items(), key=lambda item: str(item[0]))
    }


def _hazard_alignment(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("hazard_alignment")
    return value if isinstance(value, dict) else {}


def _capture_span(row: dict[str, Any]) -> int | None:
    value = _hazard_alignment(row).get("bullet_capture_span")
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _aabb_clearance(
    player_x: float,
    player_y: float,
    bullet_x: float,
    bullet_y: float,
    bullet_half_width: float,
    bullet_half_height: float,
    *,
    player_half_width: float,
    player_half_height: float,
) -> tuple[float, bool]:
    dx = abs(player_x - bullet_x) - (player_half_width + bullet_half_width)
    dy = abs(player_y - bullet_y) - (player_half_height + bullet_half_height)
    overlap = dx <= 0.0 and dy <= 0.0
    if overlap:
        return max(dx, dy), True
    return math.hypot(max(dx, 0.0), max(dy, 0.0)), False


def _bullet_lifecycle(record: list[object]) -> tuple[int, int]:
    if record:
        candidate = record[-1]
        if (
            isinstance(candidate, list)
            and len(candidate) >= 4
            and candidate[0] in BULLET_LIFECYCLE_TRACE_SCHEMAS
        ):
            return int(candidate[1]), int(candidate[3])
    return 1, 0


def _serialized_trajectory_uncertainty(
    record: list[object],
) -> tuple[float, float]:
    if len(record) <= 9 or not isinstance(record[9], list):
        return 0.0, 0.0
    runtime = record[9]
    if len(runtime) >= 17:
        x_value = _finite_number(runtime[-2])
        y_value = _finite_number(runtime[-1])
    elif len(runtime) >= 8:
        x_value = _finite_number(runtime[6])
        y_value = _finite_number(runtime[7])
    else:
        return 0.0, 0.0
    return max(0.0, x_value or 0.0), max(0.0, y_value or 0.0)


def _player_position(row: dict[str, Any]) -> tuple[float, float] | None:
    shadow = row.get("source_collision_shadow")
    if isinstance(shadow, dict):
        player = shadow.get("player")
        if isinstance(player, dict):
            position = player.get("position")
            if isinstance(position, list) and len(position) == 2:
                x = _finite_number(position[0])
                y = _finite_number(position[1])
                if x is not None and y is not None:
                    return x, y
    player = row.get("player")
    if not isinstance(player, dict):
        return None
    x = _finite_number(player.get("x"))
    y = _finite_number(player.get("y"))
    if x is None or y is None:
        return None
    return x, y


def _nearby_bullet_geometry(row: dict[str, Any]) -> dict[str, object]:
    position = _player_position(row)
    nearby = row.get("nearby_bullets")
    span = _capture_span(row)
    if position is None or not isinstance(nearby, list):
        return {
            "available": False,
            "reason": "missing_player_or_nearby_bullet_trace",
        }
    player_x, player_y = position
    source_minimum = math.inf
    legacy_minimum = math.inf
    capture_minimum = math.inf
    source_overlap_count = 0
    legacy_overlap_count = 0
    capture_overlap_count = 0
    eligible_count = 0
    transformed_count = 0
    for raw_record in nearby:
        if not isinstance(raw_record, list) or len(raw_record) < 8:
            continue
        values = [_finite_number(raw_record[index]) for index in range(1, 7)]
        if any(value is None for value in values):
            continue
        state, callback_aux = _bullet_lifecycle(raw_record)
        if state != 1 or callback_aux != 0:
            continue
        eligible_count += 1
        bullet_x, bullet_y, velocity_x, velocity_y, half_width, half_height = (
            float(value) for value in values
        )
        transformed_count += int(bool(int(raw_record[7])))
        prior_uncertainty_x, prior_uncertainty_y = (
            _serialized_trajectory_uncertainty(raw_record)
        )
        source_clearance, source_overlap = _aabb_clearance(
            player_x,
            player_y,
            bullet_x,
            bullet_y,
            half_width,
            half_height,
            player_half_width=PLAYER_LETHAL_HALF_WIDTH,
            player_half_height=PLAYER_LETHAL_HALF_HEIGHT,
        )
        legacy_clearance, legacy_overlap = _aabb_clearance(
            player_x,
            player_y,
            bullet_x,
            bullet_y,
            half_width,
            half_height,
            player_half_width=2.0,
            player_half_height=2.0,
        )
        capture_frames = float(span or 0)
        capture_half_width = (
            half_width
            + prior_uncertainty_x
            + abs(velocity_x) * capture_frames
        )
        capture_half_height = (
            half_height
            + prior_uncertainty_y
            + abs(velocity_y) * capture_frames
        )
        capture_clearance, capture_overlap = _aabb_clearance(
            player_x,
            player_y,
            bullet_x,
            bullet_y,
            capture_half_width,
            capture_half_height,
            player_half_width=PLAYER_LETHAL_HALF_WIDTH,
            player_half_height=PLAYER_LETHAL_HALF_HEIGHT,
        )
        source_minimum = min(source_minimum, source_clearance)
        legacy_minimum = min(legacy_minimum, legacy_clearance)
        capture_minimum = min(capture_minimum, capture_clearance)
        source_overlap_count += int(source_overlap)
        legacy_overlap_count += int(legacy_overlap)
        capture_overlap_count += int(capture_overlap)
    return {
        "available": True,
        "source_lethal_eligible_nearby_count": eligible_count,
        "transformed_nearby_count": transformed_count,
        "source_physical_overlap_count": source_overlap_count,
        "legacy_player2_overlap_count": legacy_overlap_count,
        "capture_envelope_overlap_count": capture_overlap_count,
        "source_physical_min_clearance": (
            source_minimum if math.isfinite(source_minimum) else None
        ),
        "legacy_player2_min_clearance": (
            legacy_minimum if math.isfinite(legacy_minimum) else None
        ),
        "capture_envelope_min_clearance": (
            capture_minimum if math.isfinite(capture_minimum) else None
        ),
        "capture_envelope_contract": (
            "captured_center_plus_axis_abs_velocity_times_capture_span; "
            "diagnostic containment, not executable action authority"
        ),
    }


def _boundary_margin(position: tuple[float, float] | None) -> float | None:
    if position is None:
        return None
    x, y = position
    return min(
        x - PLAYFIELD_LEFT,
        PLAYFIELD_RIGHT - x,
        y - PLAYFIELD_TOP,
        PLAYFIELD_BOTTOM - y,
    )


def _compact_decision(row: dict[str, Any]) -> dict[str, object]:
    alignment = _hazard_alignment(row)
    timing = row.get("timing_ms")
    timing = timing if isinstance(timing, dict) else {}
    robust = row.get("robust_control")
    robust = robust if isinstance(robust, dict) else {}
    spell = row.get("spell")
    spell = spell if isinstance(spell, dict) else {}
    position = _player_position(row)
    action = str(row.get("action") or "")
    return {
        "frame": int(row["frame"]),
        "stage_route_index": int(row["stage_route_index"]),
        "gameplay_epoch": int(row.get("gameplay_epoch") or 0),
        "hit_started": bool(row.get("hit_started")),
        "spell_id": int(spell.get("spell_id") or 0),
        "spell_name": str(spell.get("name") or ""),
        "action": action,
        "focused": bool(row.get("focused")),
        "fast_action": action.endswith("_fast"),
        "player_position": list(position) if position is not None else None,
        "boundary_margin": _boundary_margin(position),
        "active_bullets": int(row.get("active_bullets") or 0),
        "active_lasers": int(row.get("active_lasers") or 0),
        "bullet_capture_span": _capture_span(row),
        "bullet_frame_before": alignment.get("bullet_frame_before"),
        "bullet_frame_after": alignment.get("bullet_frame_after"),
        "hazard_snapshot_age": alignment.get("hazard_snapshot_age"),
        "player_to_hazard_lag": alignment.get("player_to_hazard_lag"),
        "action_lag": row.get("action_lag"),
        "read_bullet_pool_ms": timing.get("read_bullet_pool"),
        "observe_to_input_ms": timing.get("observe_to_input"),
        "plan_ms": row.get("plan_ms"),
        "immediate_clearance": row.get("immediate_clearance"),
        "minimum_clearance": row.get("minimum_clearance"),
        "pipeline_clearance": row.get("pipeline_clearance"),
        "worst_collisions": robust.get("worst_collisions"),
        "local_collisions": robust.get("local_collisions"),
        "delay_frames": robust.get("delay_frames"),
        "nearby_bullet_geometry": _nearby_bullet_geometry(row),
    }


def _new_aggregate() -> dict[str, Any]:
    return {
        "decision_count": 0,
        "hit_started_count": 0,
        "capture_spans": Counter(),
        "hit_capture_spans": Counter(),
        "cross_frame_capture_count": 0,
        "hit_cross_frame_capture_count": 0,
        "action_lag": [],
        "hit_action_lag": [],
        "observe_to_input_ms": [],
        "hit_observe_to_input_ms": [],
        "bullet_pool_ms": [],
        "hit_bullet_pool_ms": [],
        "plan_ms": [],
        "hit_plan_ms": [],
        "timing_components": {
            component: [] for component in TIMING_COMPONENTS
        },
        "hit_timing_components": {
            component: [] for component in TIMING_COMPONENTS
        },
        "boundary_decision_count": 0,
        "hit_boundary_decision_count": 0,
        "fast_action_count": 0,
        "hit_fast_action_count": 0,
        "planner_already_losing_count": 0,
        "hit_planner_already_losing_count": 0,
        "immediate_overlap_count": 0,
        "hit_immediate_overlap_count": 0,
        "global": Counter(),
        "scale_provenance": Counter(),
        "hazard_coverage_status": Counter(),
    }


def _record_aggregate(aggregate: dict[str, Any], row: dict[str, Any]) -> None:
    hit = bool(row.get("hit_started"))
    aggregate["decision_count"] += 1
    aggregate["hit_started_count"] += int(hit)
    span = _capture_span(row)
    span_label: object = span if span is not None else "missing"
    aggregate["capture_spans"][span_label] += 1
    aggregate["cross_frame_capture_count"] += int(span is not None and span > 0)
    if hit:
        aggregate["hit_capture_spans"][span_label] += 1
        aggregate["hit_cross_frame_capture_count"] += int(
            span is not None and span > 0
        )

    action_lag = _finite_number(row.get("action_lag"))
    timing = row.get("timing_ms")
    timing = timing if isinstance(timing, dict) else {}
    observe_to_input = _finite_number(timing.get("observe_to_input"))
    bullet_pool_ms = _finite_number(timing.get("read_bullet_pool"))
    for key, value in (
        ("action_lag", action_lag),
        ("observe_to_input_ms", observe_to_input),
        ("bullet_pool_ms", bullet_pool_ms),
    ):
        if value is not None:
            aggregate[key].append(value)
            if hit:
                aggregate[f"hit_{key}"].append(value)
    plan_ms = _finite_number(row.get("plan_ms"))
    if plan_ms is not None:
        aggregate["plan_ms"].append(plan_ms)
        if hit:
            aggregate["hit_plan_ms"].append(plan_ms)
    for component in TIMING_COMPONENTS:
        value = _finite_number(timing.get(component))
        if value is None:
            continue
        aggregate["timing_components"][component].append(value)
        if hit:
            aggregate["hit_timing_components"][component].append(value)

    position = _player_position(row)
    margin = _boundary_margin(position)
    boundary = margin is not None and margin <= 8.0
    fast = str(row.get("action") or "").endswith("_fast")
    robust = row.get("robust_control")
    robust = robust if isinstance(robust, dict) else {}
    worst_collisions = _finite_number(robust.get("worst_collisions"))
    already_losing = worst_collisions is not None and worst_collisions > 0
    immediate = _finite_number(row.get("immediate_clearance"))
    immediate_overlap = immediate is not None and immediate <= 0.0
    for key, value in (
        ("boundary_decision_count", boundary),
        ("fast_action_count", fast),
        ("planner_already_losing_count", already_losing),
        ("immediate_overlap_count", immediate_overlap),
    ):
        aggregate[key] += int(value)
        if hit:
            aggregate[f"hit_{key}"] += int(value)

    delivery = row.get("corridor_delivery")
    delivery = delivery if isinstance(delivery, dict) else {}
    for key in (
        "executor_enabled",
        "submission_due",
        "submission_authority_required",
        "submission_authority_available",
        "authority_blocked_submission",
        "scale_schedule_supported",
        "submitted_this_decision",
        "completed_this_decision",
        "worker_pending",
        "pending_publication",
        "active_publication",
        "action_authority",
    ):
        aggregate["global"][f"{key}:{_bool_label(delivery.get(key))}"] += 1
    scale = row.get("time_scale")
    scale = scale if isinstance(scale, dict) else {}
    aggregate["global"][
        f"time_scale_hard_authority:{_bool_label(scale.get('hard_authority'))}"
    ] += 1
    aggregate["scale_provenance"][
        str(scale.get("provenance") or "missing")
    ] += 1
    local_root = row.get("local_pipeline_root")
    local_root = local_root if isinstance(local_root, dict) else {}
    coverage = local_root.get("hazard_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    aggregate["hazard_coverage_status"][
        str(coverage.get("status") or "missing")
    ] += 1


def _finish_aggregate(aggregate: dict[str, Any]) -> dict[str, object]:
    decisions = int(aggregate["decision_count"])
    hits = int(aggregate["hit_started_count"])
    cross_frame = int(aggregate["cross_frame_capture_count"])
    hit_cross_frame = int(aggregate["hit_cross_frame_capture_count"])
    return {
        "decision_count": decisions,
        "hit_started_count": hits,
        "sensor_epoch": {
            "capture_span_counts": _counter_dict(aggregate["capture_spans"]),
            "cross_frame_capture_count": cross_frame,
            "cross_frame_capture_fraction": (
                cross_frame / decisions if decisions else None
            ),
            "hit_row_capture_span_counts": _counter_dict(
                aggregate["hit_capture_spans"]
            ),
            "hit_row_cross_frame_capture_count": hit_cross_frame,
            "hit_row_cross_frame_capture_fraction": (
                hit_cross_frame / hits if hits else None
            ),
            "bullet_pool_ms": _numeric_summary(aggregate["bullet_pool_ms"]),
            "hit_row_bullet_pool_ms": _numeric_summary(
                aggregate["hit_bullet_pool_ms"]
            ),
        },
        "timing": {
            "action_lag_frames": _numeric_summary(aggregate["action_lag"]),
            "hit_row_action_lag_frames": _numeric_summary(
                aggregate["hit_action_lag"]
            ),
            "observe_to_input_ms": _numeric_summary(
                aggregate["observe_to_input_ms"]
            ),
            "hit_row_observe_to_input_ms": _numeric_summary(
                aggregate["hit_observe_to_input_ms"]
            ),
            "plan_ms": _numeric_summary(aggregate["plan_ms"]),
            "hit_row_plan_ms": _numeric_summary(aggregate["hit_plan_ms"]),
            "components_ms": {
                component: _numeric_summary(
                    aggregate["timing_components"][component]
                )
                for component in TIMING_COMPONENTS
            },
            "hit_row_components_ms": {
                component: _numeric_summary(
                    aggregate["hit_timing_components"][component]
                )
                for component in TIMING_COMPONENTS
            },
        },
        "local_policy": {
            key: int(aggregate[key])
            for key in (
                "boundary_decision_count",
                "hit_boundary_decision_count",
                "fast_action_count",
                "hit_fast_action_count",
                "planner_already_losing_count",
                "hit_planner_already_losing_count",
                "immediate_overlap_count",
                "hit_immediate_overlap_count",
            )
        },
        "global_delivery": {
            "gate_counts": _counter_dict(aggregate["global"]),
            "scale_provenance_counts": _counter_dict(
                aggregate["scale_provenance"]
            ),
            "future_hazard_coverage_status_counts": _counter_dict(
                aggregate["hazard_coverage_status"]
            ),
        },
    }


def _compact_runtime_ecl_identity(row: dict[str, Any]) -> dict[str, object]:
    static = row.get("static_image")
    static = static if isinstance(static, dict) else {}
    capture = row.get("capture")
    capture = capture if isinstance(capture, dict) else {}
    identity = row.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    return {
        "status": row.get("status"),
        "authority": row.get("authority"),
        "route_id": row.get("route_id"),
        "difficulty_index": row.get("difficulty_index"),
        "stage_route_index": row.get("stage_route_index"),
        "gameplay_epoch": row.get("gameplay_epoch"),
        "decision_frame": row.get("decision_frame"),
        "snapshot_frame": row.get("snapshot_frame"),
        "static_label": static.get("label"),
        "static_length": static.get("length"),
        "static_sha256": static.get("sha256"),
        "runtime_length": capture.get("image_length"),
        "normalized_runtime_sha256": capture.get("normalized_sha256"),
        "exact_match": identity.get("exact_match"),
        "first_difference_offset": identity.get("first_difference_offset"),
        "error": row.get("error"),
    }


def analyze_trace(
    trace_path: Path,
    *,
    summary_path: Path | None = None,
    hit_window_decisions: int = DEFAULT_HIT_WINDOW_DECISIONS,
) -> dict[str, object]:
    if hit_window_decisions <= 0:
        raise ValueError("hit_window_decisions must be positive")
    trace_path = trace_path.resolve()
    digest = hashlib.sha256()
    overall = _new_aggregate()
    per_stage: dict[int, dict[str, Any]] = defaultdict(_new_aggregate)
    histories: dict[tuple[int, int], deque[dict[str, object]]] = {}
    hit_windows: list[dict[str, object]] = []
    runtime_ecl_identities: list[dict[str, object]] = []
    controller_config: dict[str, object] | None = None
    stages_seen: Counter[int] = Counter()
    maximum_hit_count = 0
    last_decision_frame: int | None = None

    with trace_path.open("rb") as source:
        for line_number, raw_line in enumerate(source, 1):
            digest.update(raw_line)
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON at {trace_path}:{line_number}: {error}"
                ) from error
            if not isinstance(row, dict):
                raise ValueError(f"expected object at {trace_path}:{line_number}")
            kind = row.get("kind")
            if kind == "controller_config":
                controller_config = {
                    key: row.get(key)
                    for key in (
                        "global_planner",
                        "corridor_submission_policy",
                        "corridor_background_low_priority",
                        "corridor_native_viability_workers",
                        "runtime_ecl_static_sha256",
                        "no_scale_writer_schedule_authority",
                        "no_scale_writer_static_audit",
                        "finalb_scale_source_authority",
                        "finalb_scale_pretarget_transport",
                        "local_collision_semantics",
                    )
                }
                continue
            if kind == "runtime_ecl_identity":
                runtime_ecl_identities.append(_compact_runtime_ecl_identity(row))
                continue
            if kind != "decision":
                continue

            stage = int(row["stage_route_index"])
            epoch = int(row.get("gameplay_epoch") or 0)
            stages_seen[stage] += 1
            _record_aggregate(overall, row)
            _record_aggregate(per_stage[stage], row)
            compact = _compact_decision(row)
            history = histories.setdefault(
                (epoch, stage), deque(maxlen=hit_window_decisions)
            )
            history.append(compact)
            if bool(row.get("hit_started")):
                window = list(history)
                spans = [
                    item.get("bullet_capture_span")
                    for item in window
                    if isinstance(item.get("bullet_capture_span"), int)
                ]
                hit_windows.append(
                    {
                        "hit_index": len(hit_windows) + 1,
                        "observed_frame": int(row["frame"]),
                        "stage_route_index": stage,
                        "stage_label": STAGE_ROUTE_LABELS.get(
                            stage, f"Stage {stage}"
                        ),
                        "window_decision_count": len(window),
                        "window_any_cross_frame_capture": any(
                            int(span) > 0 for span in spans
                        ),
                        "window_max_capture_span": max(spans) if spans else None,
                        "decisions": [
                            {
                                "relative_decision_index": index - len(window) + 1,
                                **item,
                            }
                            for index, item in enumerate(window)
                        ],
                        "hit_contact_observation": row.get(
                            "hit_contact_observation"
                        ),
                    }
                )
            maximum_hit_count = max(maximum_hit_count, int(row["hit_count"]))
            last_decision_frame = int(row["frame"])

    decision_count = int(overall["decision_count"])
    summary_record: dict[str, object] | None = None
    if summary_path is not None:
        summary_path = summary_path.resolve()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_record = {
            "path": str(summary_path),
            "sha256": _sha256(summary_path),
            "termination_reason": summary.get("termination_reason"),
            "decision_count": int(summary["decision_count"]),
            "hit_count": int(summary["hit_count"]),
            "last_frame": int(summary["last_frame"]),
        }
        expected = (
            int(summary["decision_count"]),
            int(summary["hit_count"]),
            int(summary["last_frame"]),
        )
        observed = (decision_count, maximum_hit_count, last_decision_frame)
        if expected != observed:
            raise ValueError(
                f"trace/summary mismatch: expected {expected}, observed {observed}"
            )

    attempted_stages = {
        int(record["stage_route_index"])
        for record in runtime_ecl_identities
        if isinstance(record.get("stage_route_index"), int)
    }
    stage_rows = []
    for stage, aggregate in sorted(per_stage.items()):
        finished = _finish_aggregate(aggregate)
        finished["stage_route_index"] = stage
        finished["stage_label"] = STAGE_ROUTE_LABELS.get(stage, f"Stage {stage}")
        stage_rows.append(finished)
    return {
        "schema": REPORT_SCHEMA,
        "trace": {
            "path": str(trace_path),
            "sha256": digest.hexdigest(),
            "size_bytes": trace_path.stat().st_size,
        },
        "summary": summary_record,
        "route": _finish_aggregate(overall),
        "stages": stage_rows,
        "hit_windows": hit_windows,
        "global_root": {
            "controller_config": controller_config,
            "runtime_ecl_identity_attempt_count": len(runtime_ecl_identities),
            "runtime_ecl_identity_observations": runtime_ecl_identities,
            "stage_decision_counts": _counter_dict(stages_seen),
            "stages_seen": sorted(stages_seen),
            "stages_with_runtime_ecl_identity_attempt": sorted(attempted_stages),
            "stages_without_runtime_ecl_identity_attempt": sorted(
                set(stages_seen) - attempted_stages
            ),
        },
        "authority": {
            "hit_window_role": (
                "observational association only; hit_started is detected after "
                "the causal motion/input interval"
            ),
            "nearby_bullet_geometry_role": (
                "serialized current-pool source-lifecycle AABB diagnostic only"
            ),
            "capture_envelope_role": (
                "conservative axis interval containment candidate; transformed "
                "future motion and unseen births remain outside this claim"
            ),
            "global_delivery_role": (
                "complete per-decision delivery/gate telemetry; zero submission "
                "is stronger evidence than zero publication"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument(
        "--hit-window-decisions",
        type=int,
        default=DEFAULT_HIT_WINDOW_DECISIONS,
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_trace(
        args.trace,
        summary_path=args.summary,
        hit_window_decisions=args.hit_window_decisions,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
