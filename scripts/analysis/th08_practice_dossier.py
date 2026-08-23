#!/usr/bin/env python3
"""Build an offline scoped thprac no-Bomb practice dossier."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from analysis.dossier import practice_behavior as _behavior
from analysis.dossier import practice_control as _control
from analysis.dossier import planner_consistency as _planner_summary
from analysis.dossier.attribution import (
    build_death_ledger as _death_ledger,
    case_prefix_for_difficulty as _case_prefix_for_difficulty,
    cluster_deaths as _death_clusters,
)
from analysis.dossier import practice_render as _render
from analysis.dossier import practice_timing as _timing
from analysis.dossier.statistics import (
    percentiles as _percentiles,
    resource_range as _resource_range,
)
from analysis.dossier.trace_reader import (
    PracticeTrace,
    extract_scope,
    read_practice_trace,
    select_frame_epoch,
)
from analysis.th08_trial_report import STAGE_ROUTE_LABELS


ROOT = Path(__file__).resolve().parents[2]
_extract_scope = extract_scope
_select_frame_epoch = select_frame_epoch
_format = _render._format
render_markdown = _render.render_markdown
write_death_csv = _render.write_death_csv
_action_hold_summary = _control._action_hold_summary
_adaptive_control_summary = _control._adaptive_control_summary
_behavior_context = _behavior._behavior_context
_behavior_slice = _behavior._behavior_slice
_control_delay_summary = _control._control_delay_summary
_corridor_latency = _timing._corridor_latency
_decision_cadence = _timing._decision_cadence
_enemy_sensor_summary = _timing._enemy_sensor_summary
_input_visibility_summary = _control._input_visibility_summary
_issue_enemy_guard_summary = _timing._issue_enemy_guard_summary
_planner_consistency_summary = (
    _planner_summary.planner_consistency_summary
)
_robust_viability_summary = _control._robust_viability_summary
_runtime_timing = _timing._runtime_timing
_spell_owner_guard_summary = _timing._spell_owner_guard_summary
_spell_phase_summary = _behavior._spell_phase_summary
_terminal_threat_summary = _timing._terminal_threat_summary
BOMB_INPUT_BIT = 0x02
TERMINAL_THREAT_SAFETY_CLEARANCE = (
    _timing.TERMINAL_THREAT_SAFETY_CLEARANCE
)
ENEMY_POOL_BASE = _timing.ENEMY_POOL_BASE
ENEMY_POOL_SIZE = _timing.ENEMY_POOL_SIZE
ENEMY_STRIDE = _timing.ENEMY_STRIDE


def _no_bomb_verification(
    decisions: list[dict[str, object]],
    controller_configs: tuple[dict[str, object], ...],
) -> dict[str, object]:
    mask_violations = [
        int(row["frame"])
        for row in decisions
        if int(row["mask"]) & BOMB_INPUT_BIT
    ]
    flag_violations = [
        int(row["frame"]) for row in decisions if bool(row["bomb"])
    ]
    action_violations = [
        int(row["frame"])
        for row in decisions
        if "bomb" in str(row["action"]).lower()
    ]
    configured_disabled = any(
        row.get("bomb_policy") == "disabled" for row in controller_configs
    )
    passed = (
        configured_disabled
        and not mask_violations
        and not flag_violations
        and not action_violations
    )
    return {
        "passed": passed,
        "bomb_input_bit": BOMB_INPUT_BIT,
        "controller_policy_disabled": configured_disabled,
        "decision_count_checked": len(decisions),
        "mask_violation_frames": mask_violations,
        "bomb_flag_violation_frames": flag_violations,
        "bomb_action_violation_frames": action_violations,
        "resource_note": (
            "Bomb stock changes after a hit are practice-mode respawn-state "
            "changes, "
            "not Bomb input; the mask, decision flag, and action are the "
            "controller evidence."
        ),
    }


def _promote_enemy_body_candidates(
    deaths: list[dict[str, object]],
) -> None:
    for index, death in enumerate(deaths):
        spell = death["spell_attribution"]
        if not (
            death["primary_cause_class"]
            == "sensor_gap_or_unmodeled_hazard"
            and spell["status"] == "resolved_live_spell_state"
            and int(spell.get("enemy_pointer", 0)) != 0
            and int(death["active_bullets"]) == 0
            and int(death["active_lasers"]) == 0
            and float(death["pipeline_clearance_at_hit"]) > 0.0
        ):
            continue
        death["primary_cause_class"] = "enemy_body_contact_candidate"
        death["enemy_body_evidence"] = {
            "confidence": (
                "strong static candidate; exact runtime overlap not yet "
                "captured"
            ),
            "enemy_pointer": int(spell["enemy_pointer"]),
            "canonical_fresh_attempt_sample": index == 0,
            "native_path": [
                {
                    "address": "0x42cf7a",
                    "meaning": (
                        "enemy manager invokes player contact using enemy "
                        "+0x2d88 position, +0x2d70 contact size, and +0x3324 "
                        "contact flags"
                    ),
                },
                {
                    "address": "0x42c33f",
                    "meaning": (
                        "enemy contact size is divided by 1.5f and stored "
                        "before deadly-contact testing"
                    ),
                },
                {
                    "address": "0x44a360",
                    "name": "player_test_deadly_aabb_contact",
                    "meaning": (
                        "enemy AABB versus player lethal rectangle; overlap "
                        "calls player_dead_handler"
                    ),
                },
            ],
            "missing_runtime_field": (
                "active enemy position/contact-size/flags at the hit frame"
            ),
        }


def build_dossier(
    *,
    run_id: str,
    trace: PracticeTrace,
) -> dict[str, object]:
    decisions = list(trace.decisions)
    run_difficulty = run_id.split("_", 1)[0].lower()
    case_prefix = (
        _case_prefix_for_difficulty(run_difficulty)
        if run_difficulty
        in {"easy", "normal", "hard", "lunatic", "extra"}
        else "LUN"
    )
    deaths = _death_ledger(decisions, case_prefix=case_prefix)
    _promote_enemy_body_candidates(deaths)
    no_bomb = _no_bomb_verification(
        decisions,
        trace.controller_configs,
    )
    if not no_bomb["passed"]:
        raise ValueError("hard no-Bomb invariant failed")

    for index, death in enumerate(deaths):
        death["sample_role"] = (
            "canonical_fresh_attempt_causal_sample"
            if index == 0
            else "post_respawn_discovery_sample"
        )
        death["bomb_input_verified_absent"] = True

    stage = int(decisions[0]["stage_route_index"])
    cause_counts = Counter(
        str(death["primary_cause_class"]) for death in deaths
    )
    planner_failure_counts = Counter(
        str(death["planner_failure_class"]) for death in deaths
    )
    contributor_counts = Counter(
        factor
        for death in deaths
        for factor in death["contributing_factors"]
    )
    spell_counts = Counter(
        (
            str(death["spell_attribution"]["spell_id"])
            if death["spell_attribution"]["spell_id"] is not None
            else "nonspell"
        )
        for death in deaths
    )
    first_hit = deaths[0] if deaths else None
    first_hit_frame = int(first_hit["frame"]) if first_hit else None
    first_window = (
        [
            row
            for row in decisions
            if first_hit_frame - 240 <= int(row["frame"]) <= first_hit_frame
        ]
        if first_hit_frame is not None
        else []
    )
    operational_lag_rows = [
        row for row in decisions if int(row["action_lag"]) < 120
    ]
    phase_counter_discontinuities = len(decisions) - len(
        operational_lag_rows
    )
    accepted_completion = (
        trace.end_event.get("reason") != "runtime_error"
        and trace.raw_summary is not None
        and trace.raw_summary.get("termination_reason") == "route_complete"
    )

    return {
        "schema": "th08-practice-dossier-v1",
        "run_id": run_id,
        "practice_scope": {
            "stage_route_index": stage,
            "stage_label": STAGE_ROUTE_LABELS.get(stage),
            "first_frame": int(decisions[0]["frame"]),
            "last_frame": int(decisions[-1]["frame"]),
            "observed_frame_span": (
                int(decisions[-1]["frame"]) - int(decisions[0]["frame"])
            ),
            "decision_count": len(decisions),
            "selected_frame_epoch_index": trace.frame_epoch_index,
            "frame_epoch_count": trace.frame_epoch_count,
            "end_event": trace.end_event,
            "pre_scope_decision_count_excluded": (
                trace.pre_scope_decision_count
            ),
            "post_scope_decision_count_excluded": (
                trace.post_scope_decision_count
            ),
            "scene_events": list(trace.scene_events),
            "raw_summary_is_scope_valid": (
                trace.raw_summary is not None
                and trace.frame_epoch_count == 1
                and int(trace.raw_summary.get("last_frame", -1))
                == int(decisions[-1]["frame"])
            ),
            "accepted_completion": accepted_completion,
        },
        "provenance": {
            "path": trace.path,
            "sha256": trace.sha256,
            "size_bytes": trace.size_bytes,
            "parse_errors": trace.parse_errors,
            "identity": trace.identity,
            "controller_configs": list(trace.controller_configs),
            "raw_kind_counts": trace.raw_kind_counts,
            "raw_summary": trace.raw_summary,
        },
        "control_policy": {
            "practice_rule": "hard no-Bomb",
            "verification": no_bomb,
        },
        "interpretation_policy": {
            "canonical_sample": (
                "Only the first hit of a fresh practice attempt preserves the "
                "initial position, bullets, power, and respawn history."
            ),
            "later_samples": (
                "Later hits remain useful discovery evidence, but death and "
                "practice-mode respawn mutate position, projectile state, "
                "Bomb stock, and Power."
            ),
        },
        "totals": {
            "death_count": len(deaths),
            "death_frames": [int(death["frame"]) for death in deaths],
            "primary_cause_counts": dict(cause_counts),
            "planner_failure_counts": dict(planner_failure_counts),
            "contributing_factor_counts": dict(contributor_counts),
            "spell_hit_counts": dict(spell_counts),
            "max_active_bullets": max(
                int(row["active_bullets"]) for row in decisions
            ),
            "max_active_lasers": max(
                int(row["active_lasers"]) for row in decisions
            ),
            "hit_contact_epoch": {
                "stable_capture_count": sum(
                    isinstance(death.get("hit_contact_observation"), dict)
                    and bool(death["hit_contact_observation"].get("stable"))
                    for death in deaths
                ),
                "stable_capture_with_enemy_body_count": sum(
                    isinstance(death.get("hit_contact_observation"), dict)
                    and bool(death["hit_contact_observation"].get("stable"))
                    and bool(
                        death["hit_contact_observation"].get("enemy_bodies")
                    )
                    for death in deaths
                ),
                "exact_enemy_body_overlap_count": sum(
                    death["observed_enemy_body_contact_candidate"] is not None
                    for death in deaths
                ),
            },
            "resources": {
                key: _resource_range(decisions, key)
                for key in ("lives", "bombs", "power")
            },
            "latency_ms": {
                "read": _percentiles(row["read_ms"] for row in decisions),
                "plan": _percentiles(row["plan_ms"] for row in decisions),
                "corridor_solver": _corridor_latency(decisions),
            },
            "decision_cadence_frames": _decision_cadence(decisions),
            "action_hold_frames": _action_hold_summary(decisions),
            "control_delay_frames": _control_delay_summary(decisions),
            "adaptive_control_delay": _adaptive_control_summary(decisions),
            "robust_viability": _robust_viability_summary(decisions),
            "planner_consistency": _planner_consistency_summary(decisions),
            "input_visibility": _input_visibility_summary(decisions),
            "runtime_timing_ms": _runtime_timing(decisions),
            "enemy_sensor": _enemy_sensor_summary(decisions),
            "issue_enemy_guard": _issue_enemy_guard_summary(decisions),
            "spell_owner_guard": _spell_owner_guard_summary(decisions),
            "terminal_threat": _terminal_threat_summary(decisions),
            "behavior_context": _behavior_context(decisions, deaths),
            "per_spell": _spell_phase_summary(decisions, deaths),
            "frame_lag": {
                "interpretation": (
                    "Values >=120 are phase-counter discontinuities and are "
                    "excluded from operational lag percentiles."
                ),
                "phase_counter_discontinuity_count": (
                    phase_counter_discontinuities
                ),
                "snapshot": _percentiles(
                    row["snapshot_lag"] for row in operational_lag_rows
                ),
                "action": _percentiles(
                    row["action_lag"] for row in operational_lag_rows
                ),
            },
        },
        "canonical_first_hit": {
            "death": first_hit,
            "preceding_240f": {
                "sample_count": len(first_window),
                "first_frame": (
                    int(first_window[0]["frame"]) if first_window else None
                ),
                "minimum_pipeline_clearance": (
                    min(
                        float(row["pipeline_clearance"])
                        for row in first_window
                    )
                    if first_window
                    else None
                ),
                "minimum_corridor_slack": (
                    min(
                        float(row["corridor_slack"])
                        for row in first_window
                        if row["corridor_slack"] is not None
                    )
                    if any(
                        row["corridor_slack"] is not None
                        for row in first_window
                    )
                    else None
                ),
            },
        },
        "death_clusters": _death_clusters(deaths),
        "deaths": deaths,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument(
        "--frame-epoch",
        default=None,
        help="'first', 'last', or a zero-based monotone gameplay-frame epoch",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--death-csv", type=Path, required=True)
    parser.add_argument("--regression-output", type=Path, required=True)
    args = parser.parse_args(argv)

    trace = read_practice_trace(
        args.trace,
        frame_epoch=args.frame_epoch,
    )
    dossier = build_dossier(run_id=args.run_id, trace=trace)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(
            dossier,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(
        render_markdown(dossier) + "\n",
        encoding="utf-8",
    )
    write_death_csv(args.death_csv, dossier["deaths"])
    args.regression_output.parent.mkdir(parents=True, exist_ok=True)
    args.regression_output.write_text(
        json.dumps(
            {
                "schema": "th08-practice-death-regressions-v1",
                "run_id": args.run_id,
                "scope": dossier["practice_scope"],
                "no_bomb_verification": dossier["control_policy"][
                    "verification"
                ],
                "case_count": len(dossier["deaths"]),
                "cases": dossier["deaths"],
            },
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
