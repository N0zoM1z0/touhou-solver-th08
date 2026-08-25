#!/usr/bin/env python3
"""Closed-loop solver gate on history-valid generated stage snapshots."""

from __future__ import annotations

import unittest

from th08_semantics.campaign import (
    StageCampaignConfig,
    run_closed_loop_stage,
)
from th08_semantics.stage_generation import generate_stage_program


class SourceStageCampaignTests(unittest.TestCase):
    def test_quick_campaign_closes_and_preserves_hard_no_bomb(self) -> None:
        program = generate_stage_program(seed=0xCE0132, profile="quick")
        result = run_closed_loop_stage(
            program,
            config=StageCampaignConfig(
                planner_stride=120,
                planner_horizon=8,
                planner_threat_horizon=10,
                planner_beam_width=4,
                geometry_oracle_stride=120,
                geometry_oracle_horizon=2,
            ),
        )

        self.assertTrue(result.passed, result.planner_failures)
        self.assertEqual(result.frames, program.frame_count)
        self.assertEqual(result.planner_calls, 4)
        self.assertEqual(result.bomb_policy_violations, 0)
        self.assertGreater(result.geometry_checks, 0)
        self.assertEqual(result.geometry_collision_mismatches, 0)
        self.assertEqual(result.geometry_clearance_sign_mismatches, 0)
        self.assertGreater(result.runtime_metrics["births_requested"], 4000)
        self.assertIsNotNone(result.planner_solve_ms_p95)


if __name__ == "__main__":
    unittest.main()
