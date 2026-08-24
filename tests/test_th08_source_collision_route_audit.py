#!/usr/bin/env python3
"""Focused tests for the streamed source-collision route ledger."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.th08_source_collision_route_audit import (
    REPORT_SCHEMA,
    analyze_trace,
)
from th08_live.sensing_trace import SOURCE_COLLISION_SHADOW_SCHEMA


def _decision(
    *,
    frame: int,
    stage: int,
    hit_count: int,
    hit_started: bool,
    native_states: dict[str, int],
    callback_suppressed: int = 0,
    lasers: int = 0,
) -> dict[str, object]:
    decoded = sum(native_states.values())
    source_lethal = native_states.get("1", 0) - callback_suppressed
    legacy_only = decoded - source_lethal
    return {
        "kind": "decision",
        "frame": frame,
        "stage_route_index": stage,
        "hit_count": hit_count,
        "hit_started": hit_started,
        "read_ms": 2.0,
        "plan_ms": 5.0,
        "action_lag": 2,
        "timing_ms": {"observe_to_input": 9.0},
        "spell": {
            "spell_id": 57 if stage == 3 else 0,
            "name": "test spell" if stage == 3 else "",
        },
        "source_collision_shadow": {
            "schema": SOURCE_COLLISION_SHADOW_SCHEMA,
            "player": {
                "valid": True,
                "cached_aabb_coherent": True,
                "geometry_stable_across_control_root": True,
                "lethal_half_extents": [1.0, 1.0],
            },
            "bullets": {
                "decoded_nonzero_state_count": decoded,
                "native_state_counts": native_states,
                "source_lethal_eligible_count": source_lethal,
                "source_nonlethal_lifecycle_count": legacy_only,
                "legacy_collision_candidate_count": decoded,
                "legacy_only_candidate_count": legacy_only,
                "callback_suppressed_state1_count": callback_suppressed,
            },
            "lasers": {"observed_count": lasers},
        },
    }


class SourceCollisionRouteAuditTests(unittest.TestCase):
    def test_streamed_route_retains_lifecycle_density_and_authority_boundary(
        self,
    ) -> None:
        rows = [
            _decision(
                frame=10,
                stage=0,
                hit_count=0,
                hit_started=False,
                native_states={"1": 3, "2": 2},
            ),
            _decision(
                frame=20,
                stage=3,
                hit_count=1,
                hit_started=True,
                native_states={"1": 5, "3": 1},
                callback_suppressed=2,
                lasers=255,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "route.jsonl"
            trace.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            summary = root / "route.summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "termination_reason": "route_complete",
                        "decision_count": 2,
                        "hit_count": 1,
                        "last_frame": 20,
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_trace(trace, summary_path=summary)

        self.assertEqual(report["schema"], REPORT_SCHEMA)
        route = report["route"]
        self.assertEqual(route["decision_count"], 2)
        self.assertEqual(route["hit_count"], 1)
        self.assertEqual(
            route["bullets"]["native_state_observations"],
            {"1": 8, "2": 2, "3": 1},
        )
        self.assertEqual(
            route["bullets"]["legacy_only_candidate_observations"],
            5,
        )
        self.assertEqual(
            route["bullets"]["callback_suppressed_state1_observations"],
            2,
        )
        self.assertEqual(route["lasers"]["max_laser_count"], 255)
        self.assertEqual(route["player"]["half_extent_counts"], {"1x1": 2})
        self.assertEqual(
            report["stages"][1]["decision_row_spell_hits"][0]["spell_id"],
            57,
        )
        self.assertFalse(
            report["authority"]["complete_geometric_inventory_retained"]
        )
        self.assertIn("ANM VM", report["authority"]["not_accepted_for"])

    def test_missing_shadow_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "route.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "kind": "decision",
                        "frame": 1,
                        "stage_route_index": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "lacks source shadow"):
                analyze_trace(trace)


if __name__ == "__main__":
    unittest.main()
