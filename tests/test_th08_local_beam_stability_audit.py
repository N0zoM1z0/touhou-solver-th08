#!/usr/bin/env python3
"""Tests for source-epoch authority in the local beam replay audit."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from analysis.local_beam_stability_audit import _decision
from analysis.local_pipeline_certificate_audit import ReconstructedRoot


def _root(*, alignment: object) -> ReconstructedRoot:
    return ReconstructedRoot(
        row={
            "player": {"x": 96.0, "y": 400.0},
            "resources": {"power": 64.0, "bombs": 0.0},
            "nearby_bullets": [],
            "lasers": [],
            "enemy_bodies": [],
            "items": [],
            "corridor": {},
            "planner_objective": {},
            "planner_guidance": {},
            # Deliberately different: this is observation-to-issue age, not
            # the player-to-hazard alignment required by the local model.
            "snapshot_lag": 9,
            "hazard_alignment": alignment,
            "control_delay_frames": 4,
            "control_delay_candidates": [3, 4, 5],
            "action_hold_frames": 2,
        },
        root=object(),
        held_mask=0x04,
        source_frame=100,
        issue_age=1,
        overdue=False,
        prehit=False,
    )


class LocalBeamStabilityAuditTests(unittest.TestCase):
    def test_replays_distinct_player_and_bullet_epochs(self) -> None:
        sentinel = object()
        with patch(
            "analysis.local_beam_stability_audit.choose_action",
            return_value=sentinel,
        ) as choose:
            result = _decision(
                _root(
                    alignment={
                        "player_to_hazard_lag": 1,
                        "bullet_snapshot_age_support": [2, 3],
                    }
                ),
                beam_dedup_mode="quantized",
                beam_width=24,
            )

        self.assertIs(result, sentinel)
        self.assertEqual(choose.call_args.kwargs["snapshot_lag"], 1)
        self.assertEqual(
            choose.call_args.kwargs["bullet_snapshot_age_support"],
            (2, 3),
        )

    def test_missing_epoch_authority_fails_closed(self) -> None:
        for alignment in (
            None,
            {"bullet_snapshot_age_support": [1]},
            {"player_to_hazard_lag": 0},
            {
                "player_to_hazard_lag": 0,
                "bullet_snapshot_age_support": [],
            },
        ):
            with self.subTest(alignment=alignment):
                with self.assertRaisesRegex(ValueError, "trace decision lacks"):
                    _decision(
                        _root(alignment=alignment),
                        beam_dedup_mode="quantized",
                        beam_width=24,
                    )


if __name__ == "__main__":
    unittest.main()
