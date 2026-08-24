#!/usr/bin/env python3
"""Regression gates for binary32/inclusive source AABB fuzzing."""

from __future__ import annotations

import unittest

from analysis.th08_source_aabb_binary32_differential import (
    DEFAULT_SEED,
    density_stress,
    edge_fuzz,
)


class SourceAabbBinary32DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.edge = edge_fuzz(
            sample_count=100_000,
            seed=DEFAULT_SEED,
        )
        cls.density = density_stress(
            position_count=3_072,
            seed=DEFAULT_SEED ^ 0x600,
        )

    def test_edge_fuzz_matches_independent_source_oracle(self) -> None:
        self.assertEqual(self.edge["corrected_oracle_mismatch_count"], 0)
        self.assertGreater(self.edge["legacy_oracle_mismatch_count"], 0)
        self.assertEqual(
            self.edge["legacy_oracle_mismatch_count"],
            self.edge["legacy_false_source_true_count"]
            + self.edge["legacy_true_source_false_count"],
        )
        self.assertIsNotNone(self.edge["first_legacy_false_source_true"])

    def test_full_pool_vectorized_collision_counts_match_oracle(self) -> None:
        self.assertEqual(self.density["bullet_count"], 1_536)
        self.assertEqual(self.density["pair_count"], 4_718_592)
        self.assertEqual(self.density["corrected_oracle_mismatch_count"], 0)
        self.assertEqual(
            self.density["integration_collision_count_mismatch_positions"],
            0,
        )
        self.assertEqual(
            self.density["maximum_integration_collision_count"],
            self.density["maximum_oracle_collision_count"],
        )
        self.assertTrue(self.density["all_outputs_finite"])


if __name__ == "__main__":
    unittest.main()
