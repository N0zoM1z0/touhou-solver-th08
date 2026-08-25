#!/usr/bin/env python3
"""Tests for sensing and hazard-alignment trace fields."""

from __future__ import annotations

from dataclasses import replace
import unittest
from types import SimpleNamespace

import numpy as np

from th08_live.sensing_trace import (
    SOURCE_COLLISION_SHADOW_SCHEMA,
    SensingTraceInput,
    _bullet_lifecycle_record,
    build_sensing_trace_fields,
)
from th08_ecl_vm_state import EclVmLocalProjection
from th08_ecl_runtime import ECL_LOOKAHEAD_SEMANTICS_VERSION
from th08_native_timer import TH08_NATIVE_TIMER_SEMANTICS_VERSION
from th08_time_scale import (
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)


class SensingTraceTests(unittest.TestCase):
    def test_packed_bullet_lifecycle_shadow_is_vectorized_and_complete(
        self,
    ) -> None:
        class PackedLifecycle:
            native_state = np.asarray([1, 1, 2, 5], dtype=np.uint16)
            native_state_timer_elapsed = np.asarray(
                [0, 7, 8, 2],
                dtype=np.int32,
            )
            callback_aux = np.asarray([0, 3, 0, 0], dtype=np.uint8)
            bullet_type = np.asarray([0, 1, 7, 10], dtype=np.int16)

            def __len__(self) -> int:
                return len(self.native_state)

        record = _bullet_lifecycle_record(PackedLifecycle())

        self.assertEqual(record["coverage"], "complete")
        self.assertEqual(
            record["native_state_counts"],
            {"1": 2, "2": 1, "5": 1},
        )
        self.assertEqual(record["source_lethal_eligible_count"], 1)
        self.assertEqual(record["legacy_only_candidate_count"], 3)
        self.assertEqual(record["callback_suppressed_state1_count"], 1)
        self.assertEqual(record["native_template_type_known_count"], 4)
        self.assertEqual(
            record["spawn_lifecycle_projection_coverage"],
            "complete",
        )

    def test_fields_preserve_captured_and_issue_guard_state(self) -> None:
        active_body = SimpleNamespace(pointer=1, contact=True)
        dormant_body = SimpleNamespace(pointer=2, contact=False)
        enemy_prefix = SimpleNamespace(
            frame_before=100,
            frame_after=101,
            bodies=(active_body,),
            attempts=1,
        )
        issue_prefix = SimpleNamespace(
            frame_before=102,
            frame_after=103,
            bodies=(active_body, dormant_body),
            attempts=2,
            stable=True,
        )
        bullet = SimpleNamespace(
            original_transform_flags=0x10,
            transform_runtime=None,
            velocity_changes=((2, 1.0, 0.0),),
            callback_phase_state=0,
            callback_aux_state=1,
            native_state=1,
            native_state_timer_elapsed=7,
        )
        issue = SimpleNamespace(
            capture=SimpleNamespace(
                source_time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
                time_scale_schedule=(
                    Th08TimeScaleSchedule.root_observation(
                        TH08_UNIT_TIME_SCALE_BITS,
                        source_frame=103,
                        provenance="sensing_trace_test_fixture",
                    )
                ),
                player_projection_authority="exact_source_root_one_step",
            ),
            pre_issue_action="stay",
            pre_issue_mask=0x01,
            post_guard_action="right",
            post_guard_mask=0x81,
            decision=SimpleNamespace(issue_recertification="transaction"),
        )
        player_control_root = SimpleNamespace(
            x=192.0,
            y=400.0,
            lethal_aabb=(191.0, 399.0, 193.0, 401.0),
            lethal_half_extents=(1.0, 1.0),
            lethal_aabb_before=(191.0, 399.0, 193.0, 401.0),
            lethal_half_extents_before=(1.0, 1.0),
            collision_geometry_stable=True,
        )
        progress = SimpleNamespace(
            status="active",
            frame_delta=2,
            health_delta=-4.0,
            damage_per_frame=2.0,
            completion_cause=None,
            state=SimpleNamespace(
                damageable=True,
                completion_pending=None,
                health_remaining=40,
                health_progress=0.5,
                time_remaining=120.0,
            ),
        )
        ecl_snapshot = SimpleNamespace(
            instruction_pointer=0x5000,
            timer_fraction=0.5,
            timer_fraction_bits=0x3F000000,
            timer_elapsed=20,
            time_scale=1.0,
            time_scale_bits=0x3F800000,
            tag_mask=0x10,
            local_projection=EclVmLocalProjection(
                (0x10, 1, 2, 3, 4, 5, 6, 7),
                (
                    0x3F800000,
                    0x40000000,
                    0x40400000,
                    0x40800000,
                    0x40A00000,
                    0x40C00000,
                    0x40E00000,
                    0x41000000,
                ),
                (9, 8, 7, 6),
            ),
        )
        toggle = SimpleNamespace(
            frame=5,
            callback_index=12,
            tag_mask=0x10,
            alternate_velocity_x=1.0,
            alternate_velocity_y=2.0,
        )
        ecl_lookahead = SimpleNamespace(
            instructions_scanned=4,
            stop_reason="horizon",
            horizon_covered=True,
            coverage_status="complete",
            requested_horizon_frames=80,
            stop_frame=80,
            covered_through_frame=80,
            unknown_from_frame=None,
            events=(toggle,),
        )
        guard = SimpleNamespace(body=active_body, contact_enabled=True)
        trace_input = SensingTraceInput(
            resources={"bombs": 3.0},
            stage_route_index=1,
            spell=4,
            boss_phase_snapshot=SimpleNamespace(frame=10),
            boss_phase_error=None,
            boss_phase_progress=progress,
            ecl_vm_snapshot=ecl_snapshot,
            ecl_lookahead=ecl_lookahead,
            tagged_velocity_toggles=(toggle,),
            bullets=(bullet,),
            ecl_event_frame_offset=1,
            ecl_event_frame_uncertainty=(0, 1),
            ecl_lookahead_error=None,
            lasers=(),
            items=(object(),),
            enemy_bodies=(active_body, dormant_body),
            dormant_enemy_body_pointers={2},
            bullet_frame_before=100,
            bullet_frame_after=101,
            enemy_prefix_snapshot=enemy_prefix,
            enemy_prefix_bodies=(active_body, dormant_body),
            bullet_capture_span=1,
            hazard_snapshot_age=2,
            player_to_hazard_lag=3,
            ecl_frame_before=100,
            ecl_frame_after=101,
            boss_guard_frame_before=100,
            boss_guard_frame_after=101,
            enemy_body_snapshot_frame=99,
            query_frame=103,
            issue_enemy_prefix_snapshot=issue_prefix,
            issue_enemy_prefix_bodies=(active_body, dormant_body),
            issue_dormant_enemy_body_pointers={2},
            issue_enemy_changes=(("added", 2),),
            issue_enemy_read_ms=1.25,
            issue_enemy_recertificate_ms=2.5,
            issue=issue,
            player_control_root=player_control_root,
            spell_enemy_body_guard=guard,
            spell_enemy_body_guard_error=None,
        )

        fields = build_sensing_trace_fields(
            trace_input,
            serialize_boss_phase_snapshot=lambda _snapshot: {"frame": 10},
            serialize_enemy_bodies=lambda bodies: [
                {"pointer": body.pointer} for body in bodies
            ],
            enemy_body_contact_enabled=lambda body: body.contact,
            enemy_pointer_in_scanned_pool=lambda pointer: pointer == 1,
            issue_recertification_record=lambda value: {"value": value},
        )

        self.assertEqual(fields["boss_phase"]["frame"], 10)
        self.assertEqual(
            fields["source_collision_shadow"]["schema"],
            SOURCE_COLLISION_SHADOW_SCHEMA,
        )
        self.assertEqual(
            fields["source_collision_shadow"]["player"][
                "lethal_half_extents"
            ],
            [1.0, 1.0],
        )
        self.assertTrue(
            fields["source_collision_shadow"]["player"][
                "cached_aabb_coherent"
            ]
        )
        self.assertEqual(
            fields["source_collision_shadow"]["bullets"][
                "source_lethal_eligible_count"
            ],
            0,
        )
        self.assertEqual(
            fields["source_collision_shadow"]["bullets"][
                "callback_suppressed_state1_count"
            ],
            1,
        )
        self.assertEqual(
            fields["time_scale"]["semantics_version"],
            TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
        )
        self.assertFalse(fields["time_scale"]["hard_authority"])
        self.assertFalse(fields["time_scale"]["phase_schedule_omitted"])
        self.assertEqual(
            fields["boss_phase_progress"]["damage_per_second_60hz"],
            120.0,
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["tagged_bullets"],
            1,
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["coverage_status"],
            "complete",
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["lookahead_semantics_version"],
            ECL_LOOKAHEAD_SEMANTICS_VERSION,
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["timer_identity"],
            {
                "semantics_version": TH08_NATIVE_TIMER_SEMANTICS_VERSION,
                "elapsed": 20,
                "fraction_bits": 0x3F000000,
                "time_scale_bits": 0x3F800000,
            },
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["prefix_events"],
            fields["bullet_velocity_lookahead"]["events"],
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["lowering_status"],
            "complete_schedule_lowered",
        )
        self.assertEqual(
            fields["bullet_velocity_lookahead"]["vm_local_projection"],
            {
                "layout": "th08-ecl-vm-local-projection-v1",
                "capture_bytes": 104,
                "integer_locals": [0x10, 1, 2, 3, 4, 5, 6, 7],
                "float_local_bits": [
                    0x3F800000,
                    0x40000000,
                    0x40400000,
                    0x40800000,
                    0x40A00000,
                    0x40C00000,
                    0x40E00000,
                    0x41000000,
                ],
                "scratch_integers": [9, 8, 7, 6],
            },
        )
        self.assertEqual(fields["enemy_body_contact_enabled_count"], 1)
        self.assertEqual(fields["enemy_body_dormant_count"], 1)
        self.assertEqual(fields["enemy_body_snapshot_age"], 4)
        self.assertEqual(
            fields["issue_time_enemy_guard"]["action_after_guard"],
            "right",
        )
        self.assertEqual(
            fields["issue_time_enemy_guard"]["transaction"],
            {"value": "transaction"},
        )
        self.assertTrue(fields["spell_enemy_body_guard"]["covered_by_async_pool"])

        incomplete = SimpleNamespace(
            instructions_scanned=256,
            stop_reason="repeated_state",
            horizon_covered=False,
            coverage_status="unknown",
            requested_horizon_frames=80,
            stop_frame=4,
            covered_through_frame=3,
            unknown_from_frame=4,
            events=(toggle,),
        )
        incomplete_fields = build_sensing_trace_fields(
            replace(
                trace_input,
                ecl_lookahead=incomplete,
                tagged_velocity_toggles=(),
            ),
            serialize_boss_phase_snapshot=lambda _snapshot: {"frame": 10},
            serialize_enemy_bodies=lambda bodies: [
                {"pointer": body.pointer} for body in bodies
            ],
            enemy_body_contact_enabled=lambda body: body.contact,
            enemy_pointer_in_scanned_pool=lambda pointer: pointer == 1,
            issue_recertification_record=lambda value: {"value": value},
        )["bullet_velocity_lookahead"]
        self.assertEqual(incomplete_fields["coverage_status"], "unknown")
        self.assertEqual(len(incomplete_fields["prefix_events"]), 1)
        self.assertEqual(incomplete_fields["events"], [])
        self.assertEqual(
            incomplete_fields["lowering_status"],
            "incomplete_prefix_not_lowered",
        )


if __name__ == "__main__":
    unittest.main()
