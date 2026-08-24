#!/usr/bin/env python3
"""Aggregate the shadow-only source collision contract from one TH08 route.

The raw JSONL is intentionally not retained by Git.  This tool streams it once
and emits a compact, reproducible ledger of player geometry, bullet lifecycle,
laser density, hit attribution, and controller latency.  The ledger is an
observability gate only; it does not grant action authority to the shadow
collision model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analysis.th08_trial_report import STAGE_ROUTE_LABELS
from th08_live.sensing_trace import SOURCE_COLLISION_SHADOW_SCHEMA


REPORT_SCHEMA = "th08-source-collision-route-audit-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _latency_summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median": _percentile(values, 0.5),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _new_aggregate() -> dict[str, Any]:
    return {
        "decision_count": 0,
        "hit_count": 0,
        "player_valid_count": 0,
        "player_cached_aabb_coherent_count": 0,
        "player_geometry_stable_count": 0,
        "player_half_extents": Counter(),
        "decoded_nonzero_state_observations": 0,
        "native_state_observations": Counter(),
        "source_lethal_eligible_observations": 0,
        "source_nonlethal_lifecycle_observations": 0,
        "legacy_collision_candidate_observations": 0,
        "legacy_only_candidate_observations": 0,
        "callback_suppressed_state1_observations": 0,
        "frames_with_legacy_only_candidates": 0,
        "frames_with_callback_suppression": 0,
        "max_decoded_nonzero_state_count": 0,
        "max_legacy_only_candidate_count": 0,
        "laser_observations": 0,
        "frames_with_lasers": 0,
        "max_laser_count": 0,
        "read_ms": [],
        "plan_ms": [],
        "observe_to_input_ms": [],
        "action_lag_frames": [],
        "decision_row_spell_hits": Counter(),
    }


def _record(
    aggregate: dict[str, Any],
    row: dict[str, Any],
    shadow: dict[str, Any],
) -> None:
    aggregate["decision_count"] += 1
    player = shadow.get("player")
    bullets = shadow.get("bullets")
    lasers = shadow.get("lasers")
    if not isinstance(player, dict):
        raise ValueError("source collision shadow lacks player geometry")
    if not isinstance(bullets, dict):
        raise ValueError("source collision shadow lacks bullet lifecycle")
    if not isinstance(lasers, dict):
        raise ValueError("source collision shadow lacks laser inventory")

    aggregate["player_valid_count"] += int(bool(player.get("valid")))
    aggregate["player_cached_aabb_coherent_count"] += int(
        bool(player.get("cached_aabb_coherent"))
    )
    aggregate["player_geometry_stable_count"] += int(
        bool(player.get("geometry_stable_across_control_root"))
    )
    half_extents = player.get("lethal_half_extents")
    if not isinstance(half_extents, list) or len(half_extents) != 2:
        raise ValueError("source collision shadow has malformed player extents")
    extent_key = f"{float(half_extents[0]):g}x{float(half_extents[1]):g}"
    aggregate["player_half_extents"][extent_key] += 1

    decoded = int(bullets["decoded_nonzero_state_count"])
    legacy_only = int(bullets["legacy_only_candidate_count"])
    callback_suppressed = int(bullets["callback_suppressed_state1_count"])
    aggregate["decoded_nonzero_state_observations"] += decoded
    aggregate["source_lethal_eligible_observations"] += int(
        bullets["source_lethal_eligible_count"]
    )
    aggregate["source_nonlethal_lifecycle_observations"] += int(
        bullets["source_nonlethal_lifecycle_count"]
    )
    aggregate["legacy_collision_candidate_observations"] += int(
        bullets["legacy_collision_candidate_count"]
    )
    aggregate["legacy_only_candidate_observations"] += legacy_only
    aggregate["callback_suppressed_state1_observations"] += callback_suppressed
    aggregate["frames_with_legacy_only_candidates"] += int(legacy_only > 0)
    aggregate["frames_with_callback_suppression"] += int(callback_suppressed > 0)
    aggregate["max_decoded_nonzero_state_count"] = max(
        aggregate["max_decoded_nonzero_state_count"], decoded
    )
    aggregate["max_legacy_only_candidate_count"] = max(
        aggregate["max_legacy_only_candidate_count"], legacy_only
    )
    state_counts = bullets.get("native_state_counts")
    if not isinstance(state_counts, dict):
        raise ValueError("source collision shadow lacks native state counts")
    for state, count in state_counts.items():
        aggregate["native_state_observations"][str(state)] += int(count)

    laser_count = int(lasers["observed_count"])
    aggregate["laser_observations"] += laser_count
    aggregate["frames_with_lasers"] += int(laser_count > 0)
    aggregate["max_laser_count"] = max(
        aggregate["max_laser_count"], laser_count
    )

    for key in ("read_ms", "plan_ms"):
        value = row.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            aggregate[key].append(float(value))
    timing = row.get("timing_ms")
    if isinstance(timing, dict):
        value = timing.get("observe_to_input")
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            aggregate["observe_to_input_ms"].append(float(value))
    action_lag = row.get("action_lag")
    if isinstance(action_lag, (int, float)) and math.isfinite(float(action_lag)):
        aggregate["action_lag_frames"].append(float(action_lag))

    if bool(row.get("hit_started")):
        aggregate["hit_count"] += 1
        spell = row.get("spell")
        spell_id = 0
        spell_name = ""
        if isinstance(spell, dict):
            spell_id = int(spell.get("spell_id") or 0)
            spell_name = str(spell.get("name") or "")
        aggregate["decision_row_spell_hits"][(spell_id, spell_name)] += 1


def _finish_aggregate(aggregate: dict[str, Any]) -> dict[str, Any]:
    decision_count = int(aggregate["decision_count"])
    legacy = int(aggregate["legacy_collision_candidate_observations"])
    legacy_only = int(aggregate["legacy_only_candidate_observations"])
    return {
        "decision_count": decision_count,
        "hit_count": int(aggregate["hit_count"]),
        "player": {
            "valid_count": int(aggregate["player_valid_count"]),
            "cached_aabb_coherent_count": int(
                aggregate["player_cached_aabb_coherent_count"]
            ),
            "geometry_stable_count": int(
                aggregate["player_geometry_stable_count"]
            ),
            "half_extent_counts": dict(
                sorted(aggregate["player_half_extents"].items())
            ),
        },
        "bullets": {
            "decoded_nonzero_state_observations": int(
                aggregate["decoded_nonzero_state_observations"]
            ),
            "native_state_observations": dict(
                sorted(aggregate["native_state_observations"].items())
            ),
            "source_lethal_eligible_observations": int(
                aggregate["source_lethal_eligible_observations"]
            ),
            "source_nonlethal_lifecycle_observations": int(
                aggregate["source_nonlethal_lifecycle_observations"]
            ),
            "legacy_collision_candidate_observations": legacy,
            "legacy_only_candidate_observations": legacy_only,
            "legacy_only_candidate_fraction": (
                legacy_only / legacy if legacy else 0.0
            ),
            "callback_suppressed_state1_observations": int(
                aggregate["callback_suppressed_state1_observations"]
            ),
            "frames_with_legacy_only_candidates": int(
                aggregate["frames_with_legacy_only_candidates"]
            ),
            "frames_with_callback_suppression": int(
                aggregate["frames_with_callback_suppression"]
            ),
            "max_decoded_nonzero_state_count": int(
                aggregate["max_decoded_nonzero_state_count"]
            ),
            "max_legacy_only_candidate_count": int(
                aggregate["max_legacy_only_candidate_count"]
            ),
        },
        "lasers": {
            "laser_observations": int(aggregate["laser_observations"]),
            "frames_with_lasers": int(aggregate["frames_with_lasers"]),
            "max_laser_count": int(aggregate["max_laser_count"]),
        },
        "timing": {
            "read_ms": _latency_summary(aggregate["read_ms"]),
            "plan_ms": _latency_summary(aggregate["plan_ms"]),
            "observe_to_input_ms": _latency_summary(
                aggregate["observe_to_input_ms"]
            ),
            "action_lag_frames": _latency_summary(
                aggregate["action_lag_frames"]
            ),
        },
        "decision_row_spell_hits": [
            {"spell_id": spell_id, "name": name, "hit_count": count}
            for (spell_id, name), count in sorted(
                aggregate["decision_row_spell_hits"].items()
            )
        ],
    }


def analyze_trace(
    trace_path: Path,
    *,
    summary_path: Path | None = None,
) -> dict[str, object]:
    trace_path = trace_path.resolve()
    digest = hashlib.sha256()
    overall = _new_aggregate()
    per_stage: dict[int, dict[str, Any]] = defaultdict(_new_aggregate)
    decision_count = 0
    maximum_hit_count = 0
    last_decision_frame: int | None = None
    with trace_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            digest.update(raw_line)
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON at {trace_path}:{line_number}: {error}"
                ) from error
            if row.get("kind") != "decision":
                continue
            shadow = row.get("source_collision_shadow")
            if not isinstance(shadow, dict):
                raise ValueError(
                    f"decision at line {line_number} lacks source shadow"
                )
            if shadow.get("schema") != SOURCE_COLLISION_SHADOW_SCHEMA:
                raise ValueError(
                    f"decision at line {line_number} has source shadow drift"
                )
            stage = int(row["stage_route_index"])
            _record(overall, row, shadow)
            _record(per_stage[stage], row, shadow)
            decision_count += 1
            last_decision_frame = int(row["frame"])
            maximum_hit_count = max(maximum_hit_count, int(row["hit_count"]))

    summary: dict[str, Any] | None = None
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

    stage_rows = []
    for stage, aggregate in sorted(per_stage.items()):
        row = _finish_aggregate(aggregate)
        row["stage_route_index"] = stage
        row["stage_label"] = STAGE_ROUTE_LABELS.get(stage, f"Stage {stage}")
        stage_rows.append(row)
    finished = _finish_aggregate(overall)
    return {
        "schema": REPORT_SCHEMA,
        "shadow_schema": SOURCE_COLLISION_SHADOW_SCHEMA,
        "trace": {
            "path": str(trace_path),
            "sha256": digest.hexdigest(),
            "size_bytes": trace_path.stat().st_size,
        },
        "summary": summary_record,
        "route": finished,
        "stages": stage_rows,
        "authority": {
            "accepted_for": (
                "complete per-decision current-pool lifecycle counts, native "
                "player AABB stability, observed laser density, and latency"
            ),
            "not_accepted_for": (
                "hit-count causality, complete route-wide geometric replay, "
                "multi-frame state2/3/4 activation without ANM VM state, "
                "callback-aux future transitions, executable-bit-exact laser "
                "trigonometry, or live action authority"
            ),
            "nearby_geometry_trace_radius": 160.0,
            "complete_geometric_inventory_retained": False,
            "shadow_changed_actions": False,
            "hit_spell_attribution": (
                "decision_row_observation_only; use the causal run dossier "
                "for spell hit attribution"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_trace(args.trace, summary_path=args.summary)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
