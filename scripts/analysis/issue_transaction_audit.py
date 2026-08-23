#!/usr/bin/env python3
"""Audit fresh/global issue transactions in a TH08 runtime trace."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def _hard_safe(certificate: object) -> bool:
    return bool(
        isinstance(certificate, dict)
        and int(certificate.get("worst_collisions", -1)) == 0
        and float(certificate.get("min_clearance", -1.0)) >= 0.0
    )


def _same_float(left: object, right: object) -> bool:
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except (TypeError, ValueError):
        return left is right


def audit_rows(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    decisions = 0
    recertified = 0
    transactions = 0
    preserved = 0
    changed = 0
    global_applicable = 0
    fresh_intersection_nonempty = 0
    fresh_empty_relaxations = 0
    inherited_relaxations = 0
    deadline_holds = 0
    outside_global = 0
    silent_outside_global = 0
    no_bomb_violations = 0
    reason_counts: Counter[str] = Counter()
    violations: list[dict[str, object]] = []
    violation_count = 0

    def reject(frame: object, code: str, detail: object = None) -> None:
        nonlocal violation_count
        violation_count += 1
        if len(violations) < 100:
            violations.append(
                {"frame": frame, "code": code, "detail": detail}
            )

    for row in rows:
        if row.get("kind") != "decision":
            continue
        decisions += 1
        frame = row.get("frame")
        if (
            int(row.get("mask", 0)) & 0x02
            or bool(row.get("bomb"))
        ):
            no_bomb_violations += 1
            reject(frame, "bomb_input")
        guard = row.get("issue_time_enemy_guard")
        if not isinstance(guard, dict) or not bool(guard.get("recertified")):
            continue
        recertified += 1
        transaction = guard.get("transaction")
        if not isinstance(transaction, dict):
            reject(frame, "missing_transaction")
            continue
        transactions += 1
        planned = str(transaction.get("planned_action"))
        selected = str(transaction.get("selected_action"))
        reason_counts[str(transaction.get("selection_reason"))] += 1
        preserved += planned == selected
        changed += planned != selected

        if planned != str(guard.get("planned_action_before_guard")):
            reject(frame, "planned_action_guard_mismatch")
        if selected != str(guard.get("action_after_guard")):
            reject(frame, "selected_action_guard_mismatch")

        deadline_guard = row.get("deadline_guard")
        deadline_guard = (
            deadline_guard if isinstance(deadline_guard, dict) else {}
        )
        deadline_suppressed = bool(deadline_guard.get("input_suppressed"))
        if deadline_suppressed:
            deadline_holds += 1
            issued_action = str(deadline_guard.get("issued_action"))
            issued_mask = deadline_guard.get("issued_mask")
            dispatch = row.get("input_dispatch")
            dispatch = dispatch if isinstance(dispatch, dict) else {}
            if not bool(deadline_guard.get("missed")):
                reject(frame, "deadline_hold_without_miss")
            if str(deadline_guard.get("planned_action")) != selected:
                reject(frame, "deadline_hold_planned_action_mismatch")
            if not issued_action.endswith("+deadline_hold"):
                reject(frame, "deadline_hold_action_not_labeled")
            if (
                str(row.get("action")) != issued_action
                or row.get("mask") != issued_mask
            ):
                reject(frame, "deadline_hold_output_mismatch")
            if (
                bool(dispatch.get("write_required"))
                or dispatch.get("previous_mask") != issued_mask
                or dispatch.get("target_mask") != issued_mask
            ):
                reject(frame, "deadline_hold_dispatch_mismatch")
        elif selected != str(row.get("action")):
            reject(frame, "selected_action_output_mismatch")

        guidance = row.get("planner_guidance")
        guidance = guidance if isinstance(guidance, dict) else {}
        expected_global = guidance.get("allowed_first_actions")
        global_actions = transaction.get("global_allowed_actions")
        if global_actions != expected_global:
            reject(
                frame,
                "global_actions_guidance_mismatch",
                {"transaction": global_actions, "guidance": expected_global},
            )
        allowed = tuple(global_actions or ())
        fresh_safe = tuple(transaction.get("fresh_safe_actions") or ())
        expected_intersection = tuple(
            action for action in allowed if action in set(fresh_safe)
        )
        intersection = tuple(
            transaction.get("fresh_global_intersection") or ()
        )
        if intersection != expected_intersection:
            reject(
                frame,
                "intersection_mismatch",
                {
                    "reported": intersection,
                    "expected": expected_intersection,
                },
            )

        applicable = bool(
            transaction.get("global_constraint_applicable")
        )
        relaxed = bool(transaction.get("global_constraint_relaxed"))
        reason = str(transaction.get("selection_reason"))
        global_applicable += applicable
        fresh_intersection_nonempty += bool(applicable and intersection)
        fresh_empty_relaxations += bool(
            applicable and not intersection and relaxed
        )
        inherited_relaxations += bool(not applicable and relaxed)
        if applicable and intersection:
            if relaxed:
                reject(frame, "nonempty_intersection_marked_relaxed")
            if selected not in intersection:
                reject(frame, "selected_outside_intersection")
            if planned in intersection and selected != planned:
                reject(frame, "safe_planned_action_not_preserved")
            expected_reason = (
                "preserve_planned_in_fresh_global_intersection"
                if planned == selected
                else "replace_unsafe_from_fresh_global_intersection"
            )
            if reason != expected_reason:
                reject(
                    frame,
                    "intersection_selection_reason_mismatch",
                    {"reported": reason, "expected": expected_reason},
                )
        if applicable and not intersection and not relaxed:
            reject(frame, "empty_intersection_not_relaxed")
        if applicable and not intersection:
            if planned == selected and selected in fresh_safe:
                expected_reason = (
                    "relax_empty_fresh_global_intersection_preserve_planned"
                )
            elif fresh_safe:
                expected_reason = "relax_empty_fresh_global_intersection"
            else:
                expected_reason = (
                    "relax_empty_fresh_global_intersection_least_bad"
                )
            if reason != expected_reason:
                reject(
                    frame,
                    "empty_intersection_selection_reason_mismatch",
                    {"reported": reason, "expected": expected_reason},
                )

        selected_outside = bool(allowed and selected not in allowed)
        outside_global += selected_outside
        silent = bool(selected_outside and not relaxed)
        silent_outside_global += silent
        if silent:
            reject(frame, "selected_outside_global_without_relaxation")
        if bool(
            transaction.get(
                "selected_outside_global_without_relaxation"
            )
        ) != silent:
            reject(frame, "silent_violation_flag_mismatch")

        planned_certificate = transaction.get("planned_certificate")
        selected_certificate = transaction.get("selected_certificate")
        if (
            isinstance(planned_certificate, dict)
            and str(planned_certificate.get("action")) != planned
        ):
            reject(frame, "planned_certificate_action_mismatch")
        if (
            not isinstance(selected_certificate, dict)
            or str(selected_certificate.get("action")) != selected
        ):
            reject(frame, "selected_certificate_action_mismatch")
            continue
        if intersection and not _hard_safe(selected_certificate):
            reject(frame, "intersection_selected_certificate_unsafe")

        robust = row.get("robust_control")
        robust = robust if isinstance(robust, dict) else {}
        if int(robust.get("worst_collisions", -1)) != int(
            selected_certificate.get("worst_collisions", -2)
        ):
            reject(frame, "selected_collision_telemetry_mismatch")
        if not _same_float(
            robust.get("min_clearance"),
            selected_certificate.get("min_clearance"),
        ):
            reject(frame, "selected_clearance_telemetry_mismatch")
        if (
            robust.get("worst_delay")
            != selected_certificate.get("worst_delay")
        ):
            reject(frame, "selected_worst_delay_telemetry_mismatch")
        if applicable and intersection:
            if not bool(robust.get("viability_constrained")):
                reject(frame, "nonempty_intersection_not_constrained")
            if bool(robust.get("viability_fresh_prefix_relaxed")):
                reject(frame, "nonempty_intersection_fresh_relaxed")
        if applicable and not intersection:
            if bool(robust.get("viability_constrained")):
                reject(frame, "empty_intersection_still_constrained")
            if not bool(robust.get("viability_fresh_prefix_relaxed")):
                reject(frame, "empty_intersection_missing_fresh_relaxation")

        repairs = dict(guidance.get("repair_volumes") or {})
        recoveries = dict(guidance.get("recovery_distances") or {})
        if int(robust.get("viability_repair_volume", -1)) != int(
            repairs.get(selected, 0)
        ):
            reject(frame, "selected_repair_telemetry_mismatch")
        if robust.get("viability_recovery_distance") != recoveries.get(
            selected
        ):
            reject(frame, "selected_recovery_telemetry_mismatch")
        if bool(robust.get("viability_safety_value_preferred")) != bool(
            selected in tuple(guidance.get("safety_actions") or ())
        ):
            reject(frame, "selected_safety_telemetry_mismatch")
        if bool(robust.get("viability_survival_preferred")) != bool(
            selected in tuple(guidance.get("survival_actions") or ())
        ):
            reject(frame, "selected_survival_telemetry_mismatch")
        if planned != selected and bool(
            robust.get("viability_control_reserve_valid", True)
        ):
            reject(frame, "changed_action_retained_control_reserve")

    return {
        "schema": "th08-issue-transaction-audit-v1",
        "decision_count": decisions,
        "recertified_count": recertified,
        "transaction_count": transactions,
        "planned_action_preserved_count": preserved,
        "action_changed_count": changed,
        "global_constraint_applicable_count": global_applicable,
        "fresh_intersection_nonempty_count": (
            fresh_intersection_nonempty
        ),
        "fresh_empty_intersection_relaxation_count": (
            fresh_empty_relaxations
        ),
        "inherited_constraint_relaxation_count": inherited_relaxations,
        "deadline_hold_count": deadline_holds,
        "selected_outside_global_count": outside_global,
        "silent_outside_global_count": silent_outside_global,
        "no_bomb_violation_count": no_bomb_violations,
        "selection_reason_counts": dict(reason_counts),
        "violation_count": violation_count,
        "violations": violations,
    }


def audit_trace(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as source:
        report = audit_rows(json.loads(line) for line in source)
    report["trace"] = str(path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit_trace(args.trace)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["violation_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
