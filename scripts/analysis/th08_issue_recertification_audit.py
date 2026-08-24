#!/usr/bin/env python3
"""Stream a TH08 route trace and audit issue-time recertification work."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any


SCHEMA = "th08-issue-recertification-audit-v1"


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
            for change in changes:
                change_kind_counts[str(change).split(":", 1)[0]] += 1
            transaction = guard.get("transaction") or {}
            reason = str(transaction.get("selection_reason") or "unknown")
            reason_counts[reason] += 1
            planned_safe = _safe(transaction.get("planned_certificate"))
            planned_safe_count += int(planned_safe)
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
            recertification_ms.append(
                float(guard.get("recertificate_ms") or 0.0)
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
