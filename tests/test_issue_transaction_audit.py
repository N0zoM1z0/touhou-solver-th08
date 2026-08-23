#!/usr/bin/env python3
"""Focused authority-boundary tests for fresh/global issue auditing."""

from __future__ import annotations

import unittest

from analysis.issue_transaction_audit import audit_rows


def _row(*, selected: str = "left", relaxed: bool = False):
    intersection = [] if relaxed else ["left"]
    selected_certificate = {
        "action": selected,
        "worst_collisions": 0,
        "min_clearance": 4.0,
        "worst_delay": None,
    }
    return {
        "kind": "decision",
        "frame": 100,
        "action": selected,
        "mask": 0x41,
        "bomb": False,
        "planner_guidance": {
            "allowed_first_actions": ["up_fast", "left"],
            "repair_volumes": {"up_fast": 1, "left": 9},
            "recovery_distances": {"left": 16.0},
            "safety_actions": ["left"],
            "survival_actions": ["left"],
        },
        "issue_time_enemy_guard": {
            "recertified": True,
            "planned_action_before_guard": "up_fast",
            "action_after_guard": selected,
            "transaction": {
                "planned_action": "up_fast",
                "global_allowed_actions": ["up_fast", "left"],
                "global_constraint_applicable": True,
                "fresh_safe_actions": [selected],
                "fresh_global_intersection": intersection,
                "selected_action": selected,
                "selection_reason": (
                    "relax_empty_fresh_global_intersection"
                    if relaxed
                    else "replace_unsafe_from_fresh_global_intersection"
                ),
                "global_constraint_relaxed": relaxed,
                "selected_outside_global_without_relaxation": False,
                "planned_certificate": {
                    "action": "up_fast",
                    "worst_collisions": 1,
                    "min_clearance": -2.0,
                    "worst_delay": 3,
                },
                "selected_certificate": selected_certificate,
            },
        },
        "robust_control": {
            "worst_collisions": 0,
            "min_clearance": 4.0,
            "worst_delay": None,
            "viability_constrained": not relaxed,
            "viability_fresh_prefix_relaxed": relaxed,
            "viability_repair_volume": 9 if selected == "left" else 0,
            "viability_recovery_distance": (
                16.0 if selected == "left" else None
            ),
            "viability_safety_value_preferred": selected == "left",
            "viability_survival_preferred": selected == "left",
            "viability_control_reserve_valid": False,
        },
    }


class IssueTransactionAuditTests(unittest.TestCase):
    def test_consistent_intersection_transaction_passes(self) -> None:
        report = audit_rows([_row()])
        self.assertEqual(report["transaction_count"], 1)
        self.assertEqual(report["violation_count"], 0)

    def test_silent_outside_global_selection_is_rejected(self) -> None:
        row = _row(selected="down_fast", relaxed=False)
        row["issue_time_enemy_guard"]["transaction"][
            "fresh_global_intersection"
        ] = ["left"]
        row["issue_time_enemy_guard"]["transaction"][
            "selected_outside_global_without_relaxation"
        ] = True
        report = audit_rows([row])
        self.assertGreater(report["violation_count"], 0)
        self.assertEqual(report["silent_outside_global_count"], 1)

    def test_empty_intersection_preserve_requires_relaxation_reason(
        self,
    ) -> None:
        row = _row(selected="down_fast", relaxed=True)
        row["issue_time_enemy_guard"]["transaction"][
            "planned_action"
        ] = "down_fast"
        row["issue_time_enemy_guard"][
            "planned_action_before_guard"
        ] = "down_fast"
        row["issue_time_enemy_guard"]["transaction"][
            "selection_reason"
        ] = "preserve_planned_in_fresh_global_intersection"
        report = audit_rows([row])
        codes = {item["code"] for item in report["violations"]}
        self.assertIn(
            "empty_intersection_selection_reason_mismatch",
            codes,
        )

    def test_deadline_hold_is_an_audited_post_guard_override(self) -> None:
        row = _row()
        row["action"] = "right_fast+deadline_hold"
        row["mask"] = 0x61
        row["deadline_guard"] = {
            "missed": True,
            "input_suppressed": True,
            "planned_action": "left",
            "issued_action": "right_fast+deadline_hold",
            "issued_mask": 0x61,
        }
        row["input_dispatch"] = {
            "previous_mask": 0x61,
            "target_mask": 0x61,
            "write_required": False,
        }

        report = audit_rows([row])

        self.assertEqual(report["deadline_hold_count"], 1)
        self.assertEqual(report["violation_count"], 0)

    def test_deadline_hold_allows_auto_confirm_shot_release(self) -> None:
        row = _row()
        row["action"] = "left+deadline_hold"
        row["mask"] = 0x40
        row["auto_confirm"] = "release"
        row["deadline_guard"] = {
            "missed": True,
            "input_suppressed": True,
            "planned_action": "left",
            "issued_action": "left+deadline_hold",
            "issued_mask": 0x40,
        }
        row["input_dispatch"] = {
            "previous_mask": 0x41,
            "target_mask": 0x40,
            "write_required": True,
        }

        report = audit_rows([row])

        self.assertEqual(report["deadline_hold_count"], 1)
        self.assertEqual(report["violation_count"], 0)

    def test_deadline_hold_rejects_auto_confirm_movement_change(self) -> None:
        row = _row()
        row["action"] = "right_fast+deadline_hold"
        row["mask"] = 0x20
        row["auto_confirm"] = "release"
        row["deadline_guard"] = {
            "missed": True,
            "input_suppressed": True,
            "planned_action": "left",
            "issued_action": "right_fast+deadline_hold",
            "issued_mask": 0x20,
        }
        row["input_dispatch"] = {
            "previous_mask": 0x41,
            "target_mask": 0x20,
            "write_required": True,
        }

        report = audit_rows([row])
        codes = {item["code"] for item in report["violations"]}

        self.assertIn("deadline_hold_auto_confirm_mismatch", codes)

    def test_unlabeled_deadline_override_is_rejected(self) -> None:
        row = _row()
        row["action"] = "right_fast"
        row["mask"] = 0x61
        row["deadline_guard"] = {
            "missed": True,
            "input_suppressed": True,
            "planned_action": "left",
            "issued_action": "right_fast",
            "issued_mask": 0x61,
        }
        row["input_dispatch"] = {
            "previous_mask": 0x61,
            "target_mask": 0x61,
            "write_required": False,
        }

        report = audit_rows([row])
        codes = {item["code"] for item in report["violations"]}

        self.assertIn("deadline_hold_action_not_labeled", codes)


if __name__ == "__main__":
    unittest.main()
