#!/usr/bin/env python3
"""Shadow replay of first-action label preservation in the local beam."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from analysis.local_pipeline_certificate_audit import (
    ReconstructedRoot,
    _read_decisions,
    _reconstruct_roots,
)
from th08_live_dodge_agent import (
    Item,
    _PLANNER_ACTIONS,
    choose_action,
)
from th08_trace_replay import hazards_from_trace


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int(0.95 * (len(ordered) - 1))]


def _timing(values: list[float]) -> dict[str, float]:
    return {
        "median_ms": statistics.median(values),
        "p95_ms": _p95(values),
        "max_ms": max(values),
    }


def _even_sample(
    values: list[ReconstructedRoot],
    count: int,
) -> list[ReconstructedRoot]:
    if len(values) <= count:
        return values
    if count <= 1:
        return values[:count]
    indices = {
        round(index * (len(values) - 1) / (count - 1))
        for index in range(count)
    }
    return [values[index] for index in sorted(indices)]


def _beam_sample(
    roots: list[ReconstructedRoot],
    count: int,
) -> list[ReconstructedRoot]:
    losing = []
    prehit = []
    for root in roots:
        corridor = root.row.get("corridor") or {}
        viability = corridor.get("viability") or {}
        if (
            viability.get("available")
            and not viability.get("state_viable")
        ):
            losing.append(root)
        if root.prehit:
            prehit.append(root)
    selected = [
        *_even_sample(losing, count // 2),
        *_even_sample(prehit, count // 4),
        *_even_sample(roots, count),
    ]
    unique = {
        (
            int(root.row.get("gameplay_epoch", 0)),
            int(root.row["frame"]),
        ): root
        for root in selected
    }
    ordered = [unique[key] for key in sorted(unique)]
    if len(ordered) <= count:
        return ordered
    must_keep = {
        (
            int(root.row.get("gameplay_epoch", 0)),
            int(root.row["frame"]),
        )
        for root in (
            *_even_sample(losing, count // 2),
            *_even_sample(prehit, count // 4),
        )
    }
    retained = [
        root
        for root in ordered
        if (
            int(root.row.get("gameplay_epoch", 0)),
            int(root.row["frame"]),
        )
        in must_keep
    ]
    fill = [
        root
        for root in ordered
        if (
            int(root.row.get("gameplay_epoch", 0)),
            int(root.row["frame"]),
        )
        not in must_keep
    ]
    return (retained + _even_sample(fill, count - len(retained)))[:count]


def _hard_vector(decision) -> tuple[int, float, int, float, float]:
    return (
        decision.robust_collisions,
        max(-decision.robust_min_clearance, 0.0),
        decision.terminal_threat_collisions,
        max(-decision.terminal_threat_min_clearance, 0.0),
        max(-decision.min_clearance, 0.0),
    )


def _recorded_hard_vector(
    row: dict[str, object],
) -> tuple[int, float, int, float, float]:
    robust = row["robust_control"]
    terminal = row["terminal_threat"]
    return (
        int(robust["worst_collisions"]),
        max(-float(robust["min_clearance"]), 0.0),
        int(terminal["collisions"]),
        max(-float(terminal["min_clearance"]), 0.0),
        max(-float(row["minimum_clearance"]), 0.0),
    )


def _decision(
    root: ReconstructedRoot,
    *,
    beam_dedup_mode: str,
    beam_width: int,
    forced_first_action: str | None = None,
):
    row = root.row
    bullets, lasers, enemy_bodies = hazards_from_trace(row)
    items = tuple(Item(*values) for values in row.get("items", ()))
    corridor = row.get("corridor") or {}
    viability = corridor.get("viability") or {}
    planner_objective = row.get("planner_objective") or {}
    planner_guidance = row.get("planner_guidance") or {}
    target = (
        corridor.get("target")
        or planner_objective.get("corridor_target")
    )
    safe_actions = (
        (forced_first_action,)
        if forced_first_action is not None
        else (
            tuple(planner_guidance["allowed_first_actions"])
            if planner_guidance.get("allowed_first_actions") is not None
            else (
                None
                if "allowed_first_actions" in planner_guidance
                else (
                    tuple(viability.get("safe_actions", ())) or None
                )
            )
        )
    )
    repair_volumes = (
        planner_guidance.get("repair_volumes")
        if "repair_volumes" in planner_guidance
        else viability.get("repair_volumes", {})
    )
    recovery_distances = (
        planner_guidance.get("recovery_distances")
        if "recovery_distances" in planner_guidance
        else viability.get("recovery_distances", {})
    )
    held_mask = root.held_mask
    return choose_action(
        player_x=float(row["player"]["x"]),
        player_y=float(row["player"]["y"]),
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        items=items,
        power=float(row["resources"]["power"]),
        bombs=float(row["resources"]["bombs"]),
        previous_direction=held_mask & 0xF0,
        previous_focus=bool(held_mask & 0x04),
        local_pipeline_root=root.root,
        can_bomb=False,
        snapshot_lag=int(row["snapshot_lag"]),
        control_delay_frames=int(row["control_delay_frames"]),
        control_delay_candidates=tuple(
            int(value) for value in row["control_delay_candidates"]
        ),
        action_hold_frames=int(row["action_hold_frames"]),
        horizon=10,
        threat_horizon=32,
        beam_width=beam_width,
        target_x=float(target["x"]) if target is not None else None,
        target_y=float(target["y"]) if target is not None else None,
        target_deadline=(
            int(target["deadline"]) if target is not None else None
        ),
        allowed_first_actions=safe_actions,
        viability_repair_volumes=tuple(
            (repair_volumes or {}).items()
        ),
        viability_recovery_distances=tuple(
            (recovery_distances or {}).items()
        ),
        viability_safety_actions=tuple(
            planner_guidance.get("safety_actions", ())
        ),
        viability_safety_state_value=planner_guidance.get(
            "safety_state_value"
        ),
        viability_survival_actions=tuple(
            planner_guidance.get(
                "survival_actions",
                viability.get("survival_best_actions", ()),
            )
        ),
        viability_survival_frames=planner_guidance.get(
            "survival_frames",
            viability.get("survival_frames"),
        ),
        viability_survival_bottleneck_margin=(
            planner_guidance.get(
                "survival_bottleneck_margin",
                viability.get("survival_bottleneck_margin"),
            )
        ),
        viability_position_error=float(
            planner_guidance.get(
                "position_error",
                viability.get("position_error", 0.0),
            )
        ),
        beam_dedup_mode=beam_dedup_mode,
    )


def _decision_record(decision) -> dict[str, object]:
    return {
        "action": decision.action,
        "hard_vector": _hard_vector(decision),
        "robust_min_clearance": decision.robust_min_clearance,
        "terminal_threat_min_clearance": (
            decision.terminal_threat_min_clearance
        ),
        "minimum_clearance": decision.min_clearance,
        "score": decision.score,
    }


def _partition_first_actions(
    roots: list[ReconstructedRoot],
    *,
    count: int,
) -> dict[str, object]:
    eligible = []
    for root in roots:
        corridor = root.row.get("corridor") or {}
        viability = corridor.get("viability") or {}
        if root.prehit and (
            not viability.get("available")
            or not viability.get("state_viable")
        ):
            eligible.append(root)
    if len(eligible) < count:
        eligible = [
            root
            for root in roots
            if root.prehit
            or not (
                (root.row.get("corridor") or {})
                .get("viability", {})
                .get("state_viable", True)
            )
        ]
    sampled = _even_sample(eligible, count)
    durations = []
    action_changes = 0
    hard_better = 0
    hard_worse = 0
    examples = []
    for root in sampled:
        started = time.perf_counter()
        baseline = _decision(
            root,
            beam_dedup_mode="quantized",
            beam_width=24,
        )
        viability = (
            (root.row.get("corridor") or {}).get("viability") or {}
        )
        allowed = tuple(viability.get("safe_actions", ())) or tuple(
            action.name for action in _PLANNER_ACTIONS
        )
        candidates = tuple(
            _decision(
                root,
                beam_dedup_mode="exact_first_action",
                beam_width=24,
                forced_first_action=action,
            )
            for action in allowed
        )
        selected = min(
            (baseline, *candidates),
            key=lambda decision: (
                _hard_vector(decision),
                decision.robust_cvar_risk,
                -decision.robust_min_clearance,
                decision.score,
                decision.action,
            ),
        )
        durations.append((time.perf_counter() - started) * 1000.0)
        baseline_hard = _hard_vector(baseline)
        selected_hard = _hard_vector(selected)
        changed = baseline.action != selected.action
        better = selected_hard < baseline_hard
        worse = selected_hard > baseline_hard
        action_changes += int(changed)
        hard_better += int(better)
        hard_worse += int(worse)
        if changed and len(examples) < 12:
            examples.append(
                {
                    "frame": int(root.row["frame"]),
                    "gameplay_epoch": int(
                        root.row.get("gameplay_epoch", 0)
                    ),
                    "prehit_240f": root.prehit,
                    "candidate_count": len(candidates),
                    "baseline": _decision_record(baseline),
                    "partition_best": _decision_record(selected),
                }
            )
    return {
        "sample_count": len(sampled),
        "action_changes": action_changes,
        "hard_vector_better": hard_better,
        "hard_vector_worse": hard_worse,
        "whole_partition_timing": (
            _timing(durations) if durations else None
        ),
        "examples": examples,
        "interpretation": (
            "Each allowed first action receives an independent width-24 "
            "continuation beam. This is a sensitivity reference, not an "
            "issue-thread implementation or optimality certificate."
        ),
    }


def _audit_trace(
    trace: Path,
    *,
    sample_count: int,
    wide_beam: int,
    partition_roots: int,
) -> dict[str, object]:
    rows, digest = _read_decisions(trace)
    roots, population = _reconstruct_roots(rows)
    sampled = _beam_sample(roots, sample_count)
    timings = {
        "baseline_beam": [],
        "first_action_labels": [],
        "exact_first_action": [],
        "wide_reference": [],
    }
    changes = {"first_action_labels": 0, "exact_first_action": 0}
    hard_better = {"first_action_labels": 0, "exact_first_action": 0}
    hard_worse = {"first_action_labels": 0, "exact_first_action": 0}
    wide_changes = 0
    label_matches_wide = 0
    baseline_matches_recorded = 0
    label_matches_recorded = 0
    baseline_hard_better_than_recorded = 0
    baseline_hard_equal_to_recorded = 0
    baseline_hard_worse_than_recorded = 0
    changed_action_hard_better = 0
    changed_action_hard_equal = 0
    changed_action_hard_worse = 0
    same_action_hard_change = 0
    baseline_hard_nonzero = 0
    critical_roots: list[ReconstructedRoot] = []
    by_context = {
        name: {
            "count": 0,
            "action_changes": 0,
            "hard_better": 0,
            "hard_worse": 0,
        }
        for name in ("boolean_losing", "prehit_240f", "pending")
    }
    examples = []
    recorded_changes = []
    recorded_hard_changes = []

    for index, root in enumerate(sampled):
        variants = (
            (
                "baseline_beam",
                "first_action_labels",
                "exact_first_action",
                "wide_reference",
            )
            if index % 2 == 0
            else (
                "wide_reference",
                "exact_first_action",
                "first_action_labels",
                "baseline_beam",
            )
        )
        decisions = {}
        for variant in variants:
            started = time.perf_counter()
            decisions[variant] = _decision(
                root,
                beam_dedup_mode=(
                    "exact_first_action"
                    if variant in {"exact_first_action", "wide_reference"}
                    else (
                        "first_action"
                        if variant == "first_action_labels"
                        else "quantized"
                    )
                ),
                beam_width=(
                    wide_beam
                    if variant == "wide_reference"
                    else int(root.row.get("beam_width", 24))
                ),
            )
            timings[variant].append(
                (time.perf_counter() - started) * 1000.0
            )
        baseline = decisions["baseline_beam"]
        labeled = decisions["first_action_labels"]
        exact = decisions["exact_first_action"]
        wide = decisions["wide_reference"]
        baseline_hard = _hard_vector(baseline)
        recorded_hard = _recorded_hard_vector(root.row)
        recorded_action = str(root.row["action"]).split("+", 1)[0]
        baseline_hard_better_than_recorded += int(
            baseline_hard < recorded_hard
        )
        baseline_hard_equal_to_recorded += int(
            baseline_hard == recorded_hard
        )
        baseline_hard_worse_than_recorded += int(
            baseline_hard > recorded_hard
        )
        if baseline.action != recorded_action:
            changed_action_hard_better += int(
                baseline_hard < recorded_hard
            )
            changed_action_hard_equal += int(
                baseline_hard == recorded_hard
            )
            changed_action_hard_worse += int(
                baseline_hard > recorded_hard
            )
        else:
            same_action_hard_change += int(
                baseline_hard != recorded_hard
            )
        if (
            baseline_hard != recorded_hard
            and len(recorded_hard_changes) < 20
        ):
            recorded_hard_changes.append(
                {
                    "frame": int(root.row["frame"]),
                    "gameplay_epoch": int(
                        root.row.get("gameplay_epoch", 0)
                    ),
                    "recorded_action": str(root.row["action"]).split(
                        "+", 1
                    )[0],
                    "replayed_action": baseline.action,
                    "recorded_hard_vector": recorded_hard,
                    "replayed_hard_vector": baseline_hard,
                }
            )
        if baseline_hard != (0, 0.0, 0, 0.0, 0.0):
            baseline_hard_nonzero += 1
            critical_roots.append(root)
        comparison = {}
        for name, decision in (
            ("first_action_labels", labeled),
            ("exact_first_action", exact),
        ):
            candidate_hard = _hard_vector(decision)
            comparison[name] = (
                baseline.action != decision.action,
                candidate_hard < baseline_hard,
                candidate_hard > baseline_hard,
            )
            changed, better, worse = comparison[name]
            changes[name] += int(changed)
            hard_better[name] += int(better)
            hard_worse[name] += int(worse)
        wide_changes += int(baseline.action != wide.action)
        label_matches_wide += int(exact.action == wide.action)
        baseline_matches_recorded += int(baseline.action == recorded_action)
        label_matches_recorded += int(labeled.action == recorded_action)
        if (
            baseline.action != recorded_action
            and len(recorded_changes) < 20
        ):
            recorded_changes.append(
                {
                    "frame": int(root.row["frame"]),
                    "gameplay_epoch": int(
                        root.row.get("gameplay_epoch", 0)
                    ),
                    "recorded_action": recorded_action,
                    "replayed_action": baseline.action,
                    "recorded_hard_vector": recorded_hard,
                    "replayed_hard_vector": baseline_hard,
                }
            )

        corridor = root.row.get("corridor") or {}
        viability = corridor.get("viability") or {}
        context_names = []
        if viability.get("available") and not viability.get("state_viable"):
            context_names.append("boolean_losing")
        if root.prehit:
            context_names.append("prehit_240f")
        if root.root.pending_action is not None:
            context_names.append("pending")
        for name in context_names:
            context = by_context[name]
            context["count"] += 1
            exact_changed, exact_better, exact_worse = comparison[
                "exact_first_action"
            ]
            context["action_changes"] += int(exact_changed)
            context["hard_better"] += int(exact_better)
            context["hard_worse"] += int(exact_worse)

        changed, better, worse = comparison["exact_first_action"]
        if (
            changed
            and (better or worse or root.prehit)
            and len(examples) < 20
        ):
            examples.append(
                {
                    "frame": int(root.row["frame"]),
                    "gameplay_epoch": int(
                        root.row.get("gameplay_epoch", 0)
                    ),
                    "spell": root.row.get("spell"),
                    "active_bullets": int(
                        root.row.get("active_bullets", 0)
                    ),
                    "prehit_240f": root.prehit,
                    "boolean_losing": (
                        bool(viability.get("available"))
                        and not bool(viability.get("state_viable"))
                    ),
                    "pipeline_root": {
                        "active_action": root.root.active_action,
                        "held_desired_action": (
                            root.root.held_desired_action
                        ),
                        "pending_action": root.root.pending_action,
                        "remaining_delay_support": (
                            root.root.remaining_delay_support
                        ),
                    },
                    "baseline": _decision_record(baseline),
                    "first_action_labels": _decision_record(labeled),
                    "exact_first_action": _decision_record(exact),
                    "wide_reference": _decision_record(wide),
                }
            )

    return {
        "trace": str(trace),
        "trace_sha256": digest,
        "population": population,
        "sample": {
            "count": len(sampled),
            "method": (
                "bounded union of evenly spaced Boolean-losing, 240-frame "
                "pre-hit, and full action-eligible roots"
            ),
            "wide_beam": wide_beam,
        },
        "differential": {
            "first_action_labels": {
                "action_changes": changes["first_action_labels"],
                "hard_vector_better": hard_better[
                    "first_action_labels"
                ],
                "hard_vector_worse": hard_worse[
                    "first_action_labels"
                ],
            },
            "exact_first_action": {
                "action_changes": changes["exact_first_action"],
                "hard_vector_better": hard_better[
                    "exact_first_action"
                ],
                "hard_vector_worse": hard_worse[
                    "exact_first_action"
                ],
            },
            "baseline_vs_wide_action_changes": wide_changes,
            "exact_first_action_matches_wide": label_matches_wide,
            "baseline_matches_recorded_action": baseline_matches_recorded,
            "first_action_labels_match_recorded_action": (
                label_matches_recorded
            ),
            "baseline_hard_better_than_recorded": (
                baseline_hard_better_than_recorded
            ),
            "baseline_hard_equal_to_recorded": (
                baseline_hard_equal_to_recorded
            ),
            "baseline_hard_worse_than_recorded": (
                baseline_hard_worse_than_recorded
            ),
            "changed_action_hard_better_than_recorded": (
                changed_action_hard_better
            ),
            "changed_action_hard_equal_to_recorded": (
                changed_action_hard_equal
            ),
            "changed_action_hard_worse_than_recorded": (
                changed_action_hard_worse
            ),
            "same_action_hard_change_count": same_action_hard_change,
            "baseline_hard_nonzero_count": baseline_hard_nonzero,
            "by_context": by_context,
        },
        "timing": {
            name: _timing(values)
            for name, values in timings.items()
        },
        "examples": examples,
        "recorded_action_changes": recorded_changes,
        "recorded_hard_changes": recorded_hard_changes,
        "first_action_partition": _partition_first_actions(
            critical_roots or roots,
            count=partition_roots,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-trace", type=int, default=96)
    parser.add_argument("--wide-beam", type=int, default=256)
    parser.add_argument("--partition-roots", type=int, default=12)
    args = parser.parse_args()
    if args.samples_per_trace < 8:
        raise SystemExit("--samples-per-trace must be at least eight")
    if args.wide_beam <= 24:
        raise SystemExit("--wide-beam must exceed the live width")
    if args.partition_roots < 1:
        raise SystemExit("--partition-roots must be positive")

    artifact = {
        "schema": "th08-local-beam-stability-audit-v3-boundary-action-strata",
        "generated_at": "2026-08-26",
        "scope": (
            "Offline shadow replay only. Quantized beam reduction retains "
            "first-action identity and one leader per first action in the "
            "best hard class only when one held action can consume the "
            "nearest boundary reserve; interior roots retain ordinary global "
            "top-k reduction. The wide beam is a sensitivity reference, not "
            "an oracle."
        ),
        "evidence_labels": {
            "observed": (
                "same-row replay actions, hard vectors, and wall timing"
            ),
            "inferred": (
                "pending roots reconstructed from the previous retained "
                "write only when direct local-root fields are absent"
            ),
            "hypothesized": (
                "physical survival benefit or proof of beam optimality"
            ),
        },
        "traces": [
            _audit_trace(
                trace,
                sample_count=args.samples_per_trace,
                wide_beam=args.wide_beam,
                partition_roots=args.partition_roots,
            )
            for trace in args.traces
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
