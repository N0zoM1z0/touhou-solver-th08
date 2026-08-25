#!/usr/bin/env python3
"""Retained native-root gate for the source collision differential."""

from __future__ import annotations

import unittest

from analysis.th08_source_collision_root_differential import (
    DEFAULT_ROOT_REPORT,
    REPORT_SCHEMA,
    analyze_root_report,
)


class SourceCollisionRootDifferentialTests(unittest.TestCase):
    def test_root2129_proves_conservative_false_positive_lower_bound(
        self,
    ) -> None:
        report = analyze_root_report(DEFAULT_ROOT_REPORT, grid_step=16.0)

        self.assertEqual(report["schema"], REPORT_SCHEMA)
        self.assertEqual(report["root"]["manager_frame"], 2129)
        self.assertEqual(report["root"]["bullet_count"], 696)
        self.assertEqual(report["root"]["native_state_counts"], {"1": 668, "2": 28})
        self.assertEqual(report["root"]["known_nonlethal_state_count"], 28)
        self.assertEqual(
            report["root"]["player"]["lethal_half_extents"],
            [1.0, 1.0],
        )

        membership = report["root_membership_grid"]
        self.assertGreater(membership["legacy_only_geometry_positions"], 0)
        self.assertGreater(membership["known_lifecycle_removed_positions"], 0)
        self.assertEqual(membership["geometry_only_legacy_positions"], 0)
        self.assertEqual(membership["source_only_legacy_positions"], 0)

        actions = report["one_step_action_set"]
        self.assertFalse(actions["coverage"]["complete_hazard_inventory"])
        self.assertEqual(actions["coverage"]["excluded_native_births"], 7)
        self.assertEqual(actions["coverage"]["unapplied_native_removals"], 4)
        self.assertEqual(
            actions["coverage"]["spawn_lifecycle_projection"],
            "historical_current-state-lower-bound-no-template-type",
        )
        self.assertEqual(
            actions["legacy_safe_actions"],
            actions["source_geometry_lifecycle_safe_actions"],
        )
        self.assertTrue(
            all(
                row["source_geometry_min_clearance"]
                >= row["legacy_min_clearance"]
                for row in actions["rows"]
            )
        )
        self.assertIn(
            "unavailable",
            report["authority"]["bullet_callback_aux"],
        )


if __name__ == "__main__":
    unittest.main()
