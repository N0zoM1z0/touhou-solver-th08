#!/usr/bin/env python3
"""Stream a TH08 route trace and audit issue-time recertification work."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any


SCHEMA = "th08-issue-recertification-audit-v2"


def _safe(certificate: dict[str, Any] | None) -> bool:
    if certificate is None:
        return False
    return bool(
        certificate.get("worst_collisions") == 0
        and float(certificate.get("min_clearance", -math.inf)) >= 0.0
    )


def _timing_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "median": 0.0, "p95": 0.0, "total": 0.0}
    ordered = sorted(values)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "total": sum(ordered),
    }


def _phase_key(record: dict[str, Any]) -> str:
    spell = record.get("spell") or {}
    if not spell.get("active"):
        return "nonspell"
    return f"spell-{int(spell.get('spell_id') or -1)}"


def audit_trace(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    decision_count = 0
    changed_count = 0
    planned_safe_count = 0
    lazy_terminal_count = 0
    preferred_terminal_count = 0
    recertification_ms: list[float] = []
    stage_counts: Counter[int] = Counter()
    reason_counts: Counter[str] = Counter()
    change_kind_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    mode_timings: dict[str, list[float]] = defaultdict(list)
    mode_branch_counts: dict[str, list[float]] = defaultdict(list)
    phase_counts: Counter[str] = Counter()
    phase_planned_safe_counts: Counter[str] = Counter()
    phase_terminal_counts: Counter[str] = Counter()
    phase_mode_counts: dict[str, Counter[str]] = defaultdict(Counter)
    phase_timings: dict[str, list[float]] = defaultdict(list)
    phase_mode_timings: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            record = json.loads(raw_line)
            if record.get("kind") != "decision":
                continue
            decision_count += 1
            guard = record.get("issue_time_enemy_guard") or {}
            changes = guard.get("changes") or ()
            if not changes:
                continue
            changed_count += 1
            stage_counts[int(record.get("stage_route_index", -1))] += 1
            phase = _phase_key(record)
            phase_counts[phase] += 1
            for change in changes:
                change_kind_counts[str(change).split(":", 1)[0]] += 1
            transaction = guard.get("transaction") or {}
            reason = str(transaction.get("selection_reason") or "unknown")
            reason_counts[reason] += 1
            planned_safe = _safe(transaction.get("planned_certificate"))
            planned_safe_count += int(planned_safe)
            phase_planned_safe_counts[phase] += int(planned_safe)
            selected_safe = _safe(transaction.get("selected_certificate"))
            preferred_applied = bool(transaction.get("preference_applied"))
            terminal = bool(
                selected_safe
                and (
                    preferred_applied
                    or (
                        planned_safe
                        and transaction.get("selected_action")
                        == transaction.get("planned_action")
                    )
                )
            )
            lazy_terminal_count += int(terminal)
            preferred_terminal_count += int(terminal and preferred_applied)
            phase_terminal_counts[phase] += int(terminal)
            mode = str(
                transaction.get("certificate_mode")
                or (
                    "counterfactual_lazy_terminal"
                    if terminal
                    else "counterfactual_full_fallback"
                )
            )
            elapsed_ms = float(guard.get("recertificate_ms") or 0.0)
            recertification_ms.append(elapsed_ms)
            mode_counts[mode] += 1
            mode_timings[mode].append(elapsed_ms)
            phase_mode_counts[phase][mode] += 1
            phase_timings[phase].append(elapsed_ms)
            phase_mode_timings[phase][mode].append(elapsed_ms)
            issue_timing = (
                (record.get("local_pipeline_timing") or {}).get(
                    "issue_recertificate"
                )
                or {}
            )
            if issue_timing.get("maximum_branch_count") is not None:
                mode_branch_counts[mode].append(
                    float(issue_timing["maximum_branch_count"])
                )

    return {
        "schema": SCHEMA,
        "trace": {
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        },
        "authority": {
            "role": "retained-route counterfactual work audit",
            "changes_input": False,
            "claim": (
                "A terminal lazy probe recomputes the selected/preferred "
                "certificate exactly; it does not infer unprobed safe actions."
            ),
        },
        "summary": {
            "decision_count": decision_count,
            "fresh_enemy_changed_count": changed_count,
            "fresh_enemy_changed_fraction": (
                changed_count / decision_count if decision_count else 0.0
            ),
            "planned_fresh_safe_count": planned_safe_count,
            "planned_fresh_safe_fraction": (
                planned_safe_count / changed_count if changed_count else 0.0
            ),
            "exact_lazy_terminal_count": lazy_terminal_count,
            "exact_lazy_terminal_fraction": (
                lazy_terminal_count / changed_count if changed_count else 0.0
            ),
            "exact_lazy_fallback_count": changed_count - lazy_terminal_count,
            "preferred_terminal_count": preferred_terminal_count,
            "recertification_ms": _timing_summary(recertification_ms),
        },
        "changed_decision_counts_by_stage": {
            str(stage): count for stage, count in sorted(stage_counts.items())
        },
        "selection_reason_counts": dict(sorted(reason_counts.items())),
        "certificate_modes": {
            mode: {
                "count": mode_counts[mode],
                "recertification_ms": _timing_summary(mode_timings[mode]),
                "maximum_branch_count": _timing_summary(
                    mode_branch_counts[mode]
                ),
            }
            for mode in sorted(mode_counts)
        },
        "phase_breakdown": {
            phase: {
                "fresh_enemy_changed_count": phase_counts[phase],
                "planned_fresh_safe_count": (
                    phase_planned_safe_counts[phase]
                ),
                "exact_lazy_terminal_count": phase_terminal_counts[phase],
                "exact_lazy_fallback_count": (
                    phase_counts[phase] - phase_terminal_counts[phase]
                ),
                "certificate_mode_counts": dict(
                    sorted(phase_mode_counts[phase].items())
                ),
                "recertification_ms": _timing_summary(
                    phase_timings[phase]
                ),
                "recertification_ms_by_mode": {
                    mode: _timing_summary(
                        phase_mode_timings[phase][mode]
                    )
                    for mode in sorted(phase_mode_timings[phase])
                },
            }
            for phase in sorted(phase_counts)
        },
        "change_kind_occurrence_counts": dict(
            sorted(change_kind_counts.items())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_trace(args.trace)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
