from __future__ import annotations

import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = (
    ROOT
    / "artifacts"
    / "runtime_reports"
    / "th08_ordinary_factorized_prefix_gate_20260731.json"
)


class OrdinaryFactorizedPrefixGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.points = {
            int(point["decision_frame"]): point
            for point in cls.report["points"]
        }

    def test_factorized_semantic_gate_passes(self) -> None:
        self.assertTrue(self.report["semantic_gate_passed"])
        self.assertTrue(self.report["native_worker_limit_applied"])
        self.assertEqual(self.report["native_workers"], 8)
        self.assertTrue(
            all(
                point["source_closure_complete"]
                and point["future_coverage_complete"]
                and point["complete"]
                and point["live_adapter_authority_eligible"]
                for point in self.report["points"]
            )
        )

    def test_first_root_recovers_a_directional_hard_lower_set(self) -> None:
        point = self.points[817]
        self.assertEqual(
            point["winning_actions"],
            ["left_fast", "down_left_fast"],
        )
        self.assertEqual(
            point["live_adapter_allowed_actions"],
            point["winning_actions"],
        )
        self.assertNotIn(
            point["pipeline_root"]["active_action"],
            point["winning_actions"],
        )
        self.assertEqual(
            point["live_adapter_reason"],
            "prepublication_viable_actions_found",
        )

    def test_future_kernel_consumes_the_four_pixel_cell_radius(self) -> None:
        for point in self.report["points"]:
            self.assertEqual(point["future_grid_step"], 4.0)
            self.assertAlmostEqual(
                point["future_required_clearance"],
                math.sqrt(8.0),
            )
            self.assertEqual(
                point["decision_frame_support"],
                [2, 3, 4],
            )
            self.assertEqual(point["unresolved_actions"], [])

    def test_late_retained_roots_remain_empty(self) -> None:
        for frame in (833, 835, 850, 910):
            self.assertEqual(self.points[frame]["winning_actions"], [])
            self.assertEqual(
                self.points[frame]["live_adapter_allowed_actions"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
