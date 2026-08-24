from __future__ import annotations

import unittest

from analysis.dossier import (
    planner_consistency,
    practice_behavior,
    practice_control,
    practice_timing,
)
from analysis import th08_practice_dossier, th08_run_dossier


class Th08DossierSummaryOwnershipTests(unittest.TestCase):
    def test_shared_planner_summary_preserves_legacy_aliases(self) -> None:
        owner = planner_consistency.planner_consistency_summary
        self.assertIs(th08_run_dossier._planner_consistency_summary, owner)
        self.assertIs(
            th08_practice_dossier._planner_consistency_summary,
            owner,
        )

    def test_practice_summary_groups_preserve_exact_aliases(self) -> None:
        groups = {
            practice_timing: (
                "_corridor_latency",
                "_decision_cadence",
                "_enemy_sensor_summary",
                "_issue_enemy_guard_summary",
                "_runtime_timing",
                "_spell_owner_guard_summary",
                "_terminal_threat_summary",
            ),
            practice_control: (
                "_action_hold_summary",
                "_adaptive_control_summary",
                "_control_delay_summary",
                "_input_visibility_summary",
                "_robust_viability_summary",
            ),
            practice_behavior: (
                "_behavior_context",
                "_behavior_slice",
                "_spell_phase_summary",
            ),
        }
        for owner_module, names in groups.items():
            for name in names:
                with self.subTest(owner=owner_module.__name__, name=name):
                    self.assertIs(
                        getattr(th08_practice_dossier, name),
                        getattr(owner_module, name),
                    )

    def test_practice_timing_constants_preserve_exact_values(self) -> None:
        self.assertEqual(
            th08_practice_dossier.TERMINAL_THREAT_SAFETY_CLEARANCE,
            practice_timing.TERMINAL_THREAT_SAFETY_CLEARANCE,
        )
        self.assertEqual(
            th08_practice_dossier.ENEMY_POOL_BASE,
            practice_timing.ENEMY_POOL_BASE,
        )
        self.assertEqual(
            th08_practice_dossier.ENEMY_POOL_SIZE,
            practice_timing.ENEMY_POOL_SIZE,
        )
        self.assertEqual(
            th08_practice_dossier.ENEMY_STRIDE,
            practice_timing.ENEMY_STRIDE,
        )

    def test_runtime_timing_retains_player_control_root_metric(self) -> None:
        summary = practice_timing._runtime_timing(
            [
                {
                    "timing_ms": {
                        "read_player_control_root": 1.25,
                    }
                }
            ]
        )

        self.assertEqual(
            summary["read_player_control_root"]["median"],
            1.25,
        )


if __name__ == "__main__":
    unittest.main()
