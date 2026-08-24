from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from analysis.th08_issue_recertification_audit import audit_trace


def _decision(
    *,
    stage: int,
    changes: list[str] | None = None,
    planned_safe: bool = True,
    selected_action: str = "stay",
    preferred: bool = False,
) -> dict[str, object]:
    guard = None
    if changes:
        planned = {
            "worst_collisions": 0 if planned_safe else 1,
            "min_clearance": 2.0 if planned_safe else -1.0,
        }
        guard = {
            "changes": changes,
            "recertificate_ms": 4.0,
            "transaction": {
                "planned_action": "stay",
                "selected_action": selected_action,
                "selection_reason": (
                    "prefer_requested_fresh_safe"
                    if preferred
                    else "preserve_fresh_safe_planned"
                ),
                "preference_applied": preferred,
                "planned_certificate": planned,
                "selected_certificate": {
                    "worst_collisions": 0,
                    "min_clearance": 3.0,
                },
            },
        }
    return {
        "kind": "decision",
        "stage_route_index": stage,
        "issue_time_enemy_guard": guard,
    }


class IssueRecertificationAuditTests(unittest.TestCase):
    def test_counts_exact_terminal_probes_and_fallbacks(self) -> None:
        records = (
            _decision(stage=0),
            _decision(stage=3, changes=["velocity:0x1"]),
            _decision(
                stage=3,
                changes=["trajectory:0x2", "contact_mode:0x2"],
                planned_safe=False,
                selected_action="left",
            ),
            _decision(
                stage=5,
                changes=["added:0x3"],
                planned_safe=False,
                selected_action="right",
                preferred=True,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            report = audit_trace(path)

        summary = report["summary"]
        self.assertEqual(summary["decision_count"], 4)
        self.assertEqual(summary["fresh_enemy_changed_count"], 3)
        self.assertEqual(summary["planned_fresh_safe_count"], 1)
        self.assertEqual(summary["exact_lazy_terminal_count"], 2)
        self.assertEqual(summary["exact_lazy_fallback_count"], 1)
        self.assertEqual(summary["preferred_terminal_count"], 1)
        self.assertEqual(summary["recertification_ms"]["total"], 12.0)
        self.assertEqual(
            report["changed_decision_counts_by_stage"],
            {"3": 2, "5": 1},
        )
