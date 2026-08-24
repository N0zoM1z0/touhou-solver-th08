#!/usr/bin/env python3
"""Regression gates for source-authored direct-fire pattern semantics."""

from __future__ import annotations

import unittest
from pathlib import Path

from analysis.th08_source_spawn_pattern_differential import (
    atlas_differential,
    density_stress,
    synthetic_differential,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS = (
    REPO_ROOT
    / "artifacts/runtime_reports/"
    "th08_source_emission_program_atlas_20260731.json"
)


class SourceSpawnPatternDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.synthetic = synthetic_differential()
        cls.atlas = atlas_differential(ATLAS)
        cls.density = density_stress(horizon_frames=16)

    def test_synthetic_sweep_closes_legacy_fan_parity_defect(self) -> None:
        self.assertEqual(self.synthetic["sample_count"], 58_752)
        self.assertEqual(self.synthetic["legacy_mismatch_count"], 9_792)
        self.assertEqual(self.synthetic["fixed_mismatch_count"], 0)
        self.assertLessEqual(
            self.synthetic["maximum_fixed_wrapped_angle_error"],
            self.synthetic["semantic_tolerance"],
        )

    def test_route2_source_owned_atlas_has_expected_affected_sites(self) -> None:
        route = self.atlas["route"]
        self.assertEqual(route["fan_literal_count_sites"], 83)
        self.assertEqual(
            route["fan_count_flag_parity_disagreement_sites"],
            42,
        )
        self.assertEqual(route["fan_fully_literal_sites"], 45)
        self.assertEqual(
            route["fan_fully_literal_parity_disagreement_sites"],
            22,
        )
        self.assertEqual(route["automatic_player_aim_sites"], 128)
        self.assertEqual(route["fixed_mismatch_count"], 0)

    def test_native_pool_density_lowering_is_complete_and_finite(self) -> None:
        self.assertEqual(self.density["requested_birth_count"], 1_536)
        self.assertEqual(self.density["lowered_envelope_count"], 1_536)
        self.assertEqual(self.density["unique_pattern_index_count"], 1_536)
        self.assertTrue(self.density["all_values_finite"])


if __name__ == "__main__":
    unittest.main()
