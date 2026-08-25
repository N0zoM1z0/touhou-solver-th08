#!/usr/bin/env python3
"""Regression gate for the source AABB semantics used by live planning."""

from __future__ import annotations

import unittest

from analysis.th08_live_source_aabb_promotion_differential import density_stress
from touhou_control import native_backend


@unittest.skipUnless(
    native_backend._load_local_hazards_function() is not None,
    "native local hazard kernel is not built",
)
class LiveSourceAabbPromotionDifferentialTests(unittest.TestCase):
    def test_dense_native_numpy_and_source_oracle_agree(self) -> None:
        result = density_stress(
            position_count=1024,
            bullet_count=512,
            seed=0x44A23005,
        )
        self.assertEqual(result["pair_count"], 524_288)
        self.assertEqual(
            result["numpy_oracle_collision_mismatch_positions"],
            0,
        )
        self.assertEqual(
            result["native_oracle_collision_mismatch_positions"],
            0,
        )
        self.assertEqual(
            result["numpy_native_collision_mismatch_positions"],
            0,
        )
        self.assertGreater(result["geometry_only_changed_positions"], 0)
        self.assertGreater(result["nonlethal_state_changed_positions"], 0)
        self.assertGreater(result["callback_aux_changed_positions"], 0)
        self.assertTrue(result["finite_outputs"])


if __name__ == "__main__":
    unittest.main()
