#!/usr/bin/env python3
"""Tests for decision timing and optional hazard trace payloads."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from th08_live.decision_trace import (
    DecisionTimingTraceInput,
    build_decision_timing_trace_fields,
    build_optional_hazard_trace_fields,
)


class DecisionTraceTests(unittest.TestCase):
    def test_timing_builder_preserves_declared_boundary(self) -> None:
        timing = SimpleNamespace(
            shared_laser_projection_ms=1.0,
            certificate_total_ms=2.0,
            geometry_kernel_ms=1.5,
        )
        decision = SimpleNamespace(
            local_certificate_timing=timing,
            issue_certificate_timing=SimpleNamespace(
                certificate_total_ms=3.0
            ),
        )
        values = {
            field: float(index)
            for index, field in enumerate(
                (
                    "observe_ms",
                    "read_ms",
                    "enemy_background_ms",
                    "enemy_prefix_capture_ms",
                    "enemy_prefix_merge_ms",
                    "bullet_pool_read_ms",
                    "laser_pool_read_ms",
                    "item_pool_read_ms",
                    "boss_phase_read_ms",
                    "spell_enemy_guard_read_ms",
                    "ecl_lookahead_read_ms",
                    "hazard_read_bookkeeping_ms",
                    "player_control_root_ms",
                    "enemy_pool_read_ms",
                    "enemy_prefix_read_ms",
                    "issue_enemy_read_ms",
                    "decode_ms",
                    "bullet_decode_ms",
                    "bullet_event_attach_ms",
                    "laser_decode_ms",
                    "item_decode_ms",
                    "corridor_overhead_ms",
                    "plan_ms",
                    "issue_enemy_recertificate_ms",
                    "issue_path_ms",
                    "observe_to_issue_ms",
                    "input_ms",
                    "before_trace_ms",
                )
            )
        }
        trace_input = DecisionTimingTraceInput(
            **values,
            decision=decision,
            local_pipeline_certificate_shadow={"wall_ms": 4.5},
            previous_trace_ms=5.0,
            previous_iteration_ms=6.0,
        )

        fields = build_decision_timing_trace_fields(trace_input)

        self.assertEqual(fields["read_ms"], values["read_ms"])
        self.assertEqual(
            fields["timing_ms"]["local_plan_initial"],
            values["plan_ms"] - values["issue_enemy_recertificate_ms"],
        )
        self.assertEqual(
            fields["timing_ms"]["post_issue_root_shadow"],
            4.5,
        )
        self.assertEqual(
            fields["timing_ms"]["before_trace"],
            values["before_trace_ms"],
        )
        self.assertEqual(
            fields["timing_ms"]["read_player_control_root"],
            values["player_control_root_ms"],
        )

    def test_optional_hazards_respect_radius_and_transform_flags(self) -> None:
        near = SimpleNamespace(
            x=10.0,
            y=10.0,
            transform_runtime=object(),
        )
        far = SimpleNamespace(
            x=100.0,
            y=100.0,
            transform_runtime=None,
        )
        laser = SimpleNamespace(slot=2)
        item = SimpleNamespace(
            slot=3,
            x=1.0,
            y=2.0,
            vx=3.0,
            vy=4.0,
            item_type=5,
            motion_state=6,
            full_value=True,
        )

        fields = build_optional_hazard_trace_fields(
            trace_radius=5.0,
            trace_transform_runtime=True,
            bullets=(near, far),
            lasers=(laser,),
            items=(item,),
            projected_player_x=12.0,
            projected_player_y=12.0,
            serialize_bullet_trace=lambda bullet: [bullet.x, bullet.y],
            serialize_laser_trace=lambda value: value.slot,
        )

        self.assertEqual(fields["nearby_bullets"], [[10.0, 10.0]])
        self.assertEqual(fields["lasers"], [2])
        self.assertEqual(fields["items"], [[3, 1.0, 2.0, 3.0, 4.0, 5, 6, True]])
        self.assertEqual(fields["transform_bullets"], [[10.0, 10.0]])


if __name__ == "__main__":
    unittest.main()
