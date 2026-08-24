#!/usr/bin/env python3
"""Focused tests for route timing and global-delivery audit evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.th08_route_delivery_timing_audit import (
    REPORT_SCHEMA,
    analyze_trace,
)


def _decision(
    *,
    frame: int,
    stage: int,
    hit_count: int,
    hit_started: bool,
    span: int,
    bullet_x: float,
) -> dict[str, object]:
    return {
        "kind": "decision",
        "frame": frame,
        "stage_route_index": stage,
        "gameplay_epoch": 0,
        "hit_count": hit_count,
        "hit_started": hit_started,
        "action": "left_fast",
        "focused": False,
        "active_bullets": 1,
        "active_lasers": 0,
        "action_lag": 4,
        "immediate_clearance": 0.5,
        "minimum_clearance": 0.5,
        "pipeline_clearance": 0.5,
        "timing_ms": {
            "observe_to_input": 80.0,
            "read_bullet_pool": 7.0,
        },
        "hazard_alignment": {
            "bullet_capture_span": span,
            "bullet_frame_before": frame - span,
            "bullet_frame_after": frame,
            "hazard_snapshot_age": 0,
            "player_to_hazard_lag": span,
        },
        "player": {"x": 100.0, "y": 100.0},
        "source_collision_shadow": {
            "player": {"position": [100.0, 100.0]},
        },
        "nearby_bullets": [
            [0, bullet_x, 100.0, -1.0, 0.0, 1.0, 1.0, 0, None]
        ],
        "robust_control": {"worst_collisions": 1, "local_collisions": 0},
        "spell": {"spell_id": 57, "name": "test"},
        "time_scale": {
            "hard_authority": False,
            "provenance": "experimental_unit",
        },
        "corridor_delivery": {
            "executor_enabled": True,
            "submission_due": True,
            "submission_authority_required": True,
            "submission_authority_available": False,
            "authority_blocked_submission": True,
            "scale_schedule_supported": True,
            "submitted_this_decision": False,
            "completed_this_decision": False,
            "worker_pending": False,
            "pending_publication": False,
            "active_publication": False,
            "action_authority": False,
        },
        "local_pipeline_root": {
            "hazard_coverage": {"status": "model_unknown"},
        },
    }


class RouteDeliveryTimingAuditTests(unittest.TestCase):
    def test_streams_capture_geometry_and_global_root_cause(self) -> None:
        rows = [
            {
                "kind": "controller_config",
                "global_planner": "finite_horizon_robust_backward_viability",
                "corridor_submission_policy": "hard_time_scale_authority_only",
                "runtime_ecl_static_sha256": "finalb",
            },
            {
                "kind": "runtime_ecl_identity",
                "status": "byte_mismatch",
                "authority": "trace_only_instruction_byte_identity",
                "stage_route_index": 0,
                "decision_frame": 10,
                "static_image": {
                    "label": "ecldata7.ecl",
                    "length": 200,
                    "sha256": "finalb",
                },
                "capture": {
                    "image_length": 100,
                    "normalized_sha256": "stage1",
                },
                "identity": {
                    "exact_match": False,
                    "first_difference_offset": 4,
                },
            },
            _decision(
                frame=10,
                stage=0,
                hit_count=0,
                hit_started=False,
                span=1,
                bullet_x=102.5,
            ),
            _decision(
                frame=12,
                stage=0,
                hit_count=1,
                hit_started=True,
                span=0,
                bullet_x=102.5,
            ),
            _decision(
                frame=20,
                stage=5,
                hit_count=1,
                hit_started=False,
                span=0,
                bullet_x=110.0,
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
                        "decision_count": 3,
                        "hit_count": 1,
                        "last_frame": 20,
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_trace(
                trace,
                summary_path=summary,
                hit_window_decisions=4,
            )

        self.assertEqual(report["schema"], REPORT_SCHEMA)
        route = report["route"]
        self.assertEqual(
            route["sensor_epoch"]["capture_span_counts"], {"0": 2, "1": 1}
        )
        self.assertEqual(
            route["sensor_epoch"]["hit_row_capture_span_counts"], {"0": 1}
        )
        self.assertEqual(
            route["global_delivery"]["gate_counts"][
                "submitted_this_decision:false"
            ],
            3,
        )
        self.assertEqual(
            route["global_delivery"]["future_hazard_coverage_status_counts"],
            {"model_unknown": 3},
        )
        hit = report["hit_windows"][0]
        self.assertTrue(hit["window_any_cross_frame_capture"])
        prior_geometry = hit["decisions"][0]["nearby_bullet_geometry"]
        self.assertEqual(prior_geometry["source_physical_overlap_count"], 0)
        self.assertEqual(prior_geometry["legacy_player2_overlap_count"], 1)
        self.assertEqual(prior_geometry["capture_envelope_overlap_count"], 1)
        global_root = report["global_root"]
        self.assertEqual(global_root["runtime_ecl_identity_attempt_count"], 1)
        self.assertEqual(
            global_root["stages_without_runtime_ecl_identity_attempt"], [5]
        )
        self.assertEqual(
            global_root["runtime_ecl_identity_observations"][0]["status"],
            "byte_mismatch",
        )

    def test_non_positive_hit_window_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "route.jsonl"
            trace.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be positive"):
                analyze_trace(trace, hit_window_decisions=0)


if __name__ == "__main__":
    unittest.main()
