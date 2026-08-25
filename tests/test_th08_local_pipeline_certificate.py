from __future__ import annotations

import random
import struct
import unittest

import numpy as np

from th08_ecl_vm_state import float32_from_bits
from th08_future_birth_envelope import FloatInterval, FutureDirectFire
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_trace_replay import local_pipeline_root_from_trace
from th08_live_dodge_agent import (
    Bullet,
    DOWN,
    EnemyBody,
    FOCUS,
    LEFT,
    Laser,
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
    RIGHT,
    SHOT,
    _PLANNER_ACTIONS,
    _LocalCertificateTimingAccumulator,
    _boundary_risk,
    _boundary_risk_for_positions,
    _build_bullet_frames,
    _build_packed_laser_collision_frames,
    _causal_pipeline_player_positions,
    _delayed_issue_action_certificates,
    _delayed_causal_pipeline_player_positions,
    _advance_planner_action,
    _hazards_for_positions,
    _legacy_robust_action_certificates,
    _robust_action_certificates,
    _direct_root_certificate_shadow,
    _recertify_delayed_issue_rows_for_fresh_enemy_bodies,
)
from th08_live.local_certificates import delayed_issue_action_certificates
from th08_live.ordinary_continuation_lease import (
    OrdinaryContinuationLease,
    check_continuation_lease_capture,
)
from touhou_control.local_pipeline_oracle import (
    LocalPipelineRoot,
    enumerate_delayed_issue_pipeline_branches,
    scalar_local_pipeline_certificates,
)
from touhou_control.pipeline_identity import VersionIdentity
from touhou_control.corridor import AabbHazard, AabbTrajectoryHazard
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS


def _unit_scale_bits(horizon: int) -> tuple[int, ...]:
    return (TH08_UNIT_TIME_SCALE_BITS,) * horizon


class Th08LocalPipelineCertificateTests(unittest.TestCase):
    def test_retained_stage3_f566_held_path_hits_observed_slot_one(
        self,
    ) -> None:
        down_left = next(
            action for action in _PLANNER_ACTIONS
            if action.name == "down_left"
        )
        certificate = _robust_action_certificates(
            player_x=182.241943359375,
            player_y=425.9578857421875,
            previous_mask=SHOT | FOCUS | DOWN | LEFT,
            actions=(down_left,),
            delay_frames=tuple(range(7)),
            action_hold_frames=74,
            bullets=(
                Bullet(
                    slot=1,
                    x=151.16783142089844,
                    y=378.149169921875,
                    vx=-0.31652605533599854,
                    vy=2.4042537212371826,
                    half_width=2.0,
                    half_height=2.0,
                ),
            ),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(80),
            laser_scale_bits=_unit_scale_bits(80),
            pipeline_root=LocalPipelineRoot(
                "down_left",
                "down_left",
                input_publication_to_motion_lag_frames=1,
            ),
        )["down_left"]

        self.assertGreater(certificate.worst_collisions, 0)
        self.assertLess(certificate.min_clearance, 0.0)
        self.assertEqual(certificate.pipeline_branch_count, 1)

    def test_retained_stage4a_write_pickup_observation_precedes_motion(
        self,
    ) -> None:
        root = LocalPipelineRoot(
            "down_right_fast",
            "down_right_fast",
            input_publication_to_motion_lag_frames=1,
        )
        branches = enumerate_delayed_issue_pipeline_branches(
            root=root,
            selected_action="down_right",
            issue_delay_frames=(17,),
            pickup_delay_frames=tuple(range(7)),
            horizon_frames=80,
        )
        positions = _delayed_causal_pipeline_player_positions(
            root=root,
            selected_action="down_right",
            issue_delay_frames=(17,),
            pickup_delay_frames=tuple(range(7)),
            horizon_frames=80,
            player_x=197.6568603515625,
            player_y=389.6568603515625,
            player_scale_bits=_unit_scale_bits(80),
        )
        lease = OrdinaryContinuationLease(
            lease_id="stage4a-f3174-down-right",
            gameplay_epoch=3,
            stage_route_index=3,
            action="down_right",
            mask=0xA5,
            root_frame=3174,
            issue_frame=3191,
            horizon_frames=80,
            projection_digest="retained-stage4a-projection",
            projection_source="retained-physical",
            projection_version=VersionIdentity.from_mapping(
                "retained-stage4a-projection-v1",
                {"root_frame": 3174},
            ),
            pipeline_root=root,
            issue_delay=17,
            pickup_delay_support=tuple(range(7)),
            branches=branches,
            positions_by_step=positions,
            certified_enemy_boxes_by_step=((),) * 81,
            minimum_clearance=0.350982666015625,
            fresh_geometry_frame=3189,
            fresh_geometry_changed=True,
        )

        self.assertTrue(
            all(
                x == 248.568603515625 and y == 432.0
                for x, y in positions[18]
            )
        )
        check = check_continuation_lease_capture(
            lease,
            gameplay_epoch=3,
            stage_route_index=3,
            spell_active=False,
            player_phase=3,
            unit_time_scale=True,
            current_frame=3192,
            player_x=248.568603515625,
            player_y=432.0,
            pipeline_root=LocalPipelineRoot(
                "down_right",
                "down_right",
                input_publication_to_motion_lag_frames=1,
            ),
            minimum_remaining_frames=7,
        )

        self.assertTrue(check.valid)
        self.assertEqual(check.matched_branch_count, 1)

    def test_retained_physical_no_write_path_forms_exact_lease(self) -> None:
        root = LocalPipelineRoot(
            "left_fast",
            "left_fast",
            input_publication_to_motion_lag_frames=1,
        )
        branches = enumerate_delayed_issue_pipeline_branches(
            root=root,
            selected_action="left_fast",
            issue_delay_frames=(13,),
            pickup_delay_frames=tuple(range(7)),
            horizon_frames=80,
        )
        positions = _delayed_causal_pipeline_player_positions(
            root=root,
            selected_action="left_fast",
            issue_delay_frames=(13,),
            pickup_delay_frames=tuple(range(7)),
            horizon_frames=80,
            player_x=101.80775451660156,
            player_y=402.46063232421875,
            player_scale_bits=_unit_scale_bits(80),
        )
        lease = OrdinaryContinuationLease(
            lease_id="stage5-f1456-left-fast",
            gameplay_epoch=0,
            stage_route_index=5,
            action="left_fast",
            mask=0x41,
            root_frame=1456,
            issue_frame=1469,
            horizon_frames=80,
            projection_digest="retained-stage5-projection",
            projection_source="retained-physical",
            projection_version=VersionIdentity.from_mapping(
                "retained-stage5-projection-v1",
                {"root_frame": 1456},
            ),
            pipeline_root=root,
            issue_delay=13,
            pickup_delay_support=tuple(range(7)),
            branches=branches,
            positions_by_step=positions,
            certified_enemy_boxes_by_step=((),) * 81,
            minimum_clearance=48.942928314208984,
            fresh_geometry_frame=1469,
            fresh_geometry_changed=True,
        )

        retained = check_continuation_lease_capture(
            lease,
            gameplay_epoch=0,
            stage_route_index=5,
            spell_active=False,
            player_phase=0,
            unit_time_scale=True,
            current_frame=1470,
            player_x=45.80775451660156,
            player_y=402.46063232421875,
            pipeline_root=LocalPipelineRoot(
                "left_fast",
                "left_fast",
                input_publication_to_motion_lag_frames=1,
            ),
            minimum_remaining_frames=7,
        )
        discarded_by_old_controller = check_continuation_lease_capture(
            lease,
            gameplay_epoch=0,
            stage_route_index=5,
            spell_active=False,
            player_phase=0,
            unit_time_scale=True,
            current_frame=1479,
            player_x=9.807754516601562,
            player_y=402.46063232421875,
            pipeline_root=LocalPipelineRoot(
                "right_fast",
                "right_fast",
                input_publication_to_motion_lag_frames=1,
            ),
            minimum_remaining_frames=7,
        )

        self.assertTrue(retained.valid)
        self.assertEqual(
            discarded_by_old_controller.reason,
            "held_action_mismatch",
        )

    def test_held_no_write_rows_share_one_exact_physical_path(self) -> None:
        stay = next(
            action for action in _PLANNER_ACTIONS if action.name == "stay"
        )
        issue_delays = tuple(range(6))
        scale_bits = _unit_scale_bits(8)
        root = LocalPipelineRoot("stay", "stay")
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=8,
            events=(),
            source_semantics_version="test-held-renewal-v1",
        )

        optimized, conditioned = _delayed_issue_action_certificates(
            root=root,
            actions=(stay,),
            issue_delay_frames=issue_delays,
            pickup_delay_frames=(0, 1, 2),
            horizon_frames=8,
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=scale_bits,
            laser_scale_bits=scale_bits,
            future_hazard_projection=projection,
            source_frame=100,
        )
        scalar_rows = delayed_issue_action_certificates(
            hazards_for_positions=_hazards_for_positions,
            player_x=192.0,
            player_y=400.0,
            actions=(stay,),
            issue_delay_frames=issue_delays,
            pickup_delay_frames=(0, 1, 2),
            horizon_frames=8,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=scale_bits,
            laser_scale_bits=scale_bits,
            pipeline_root=root,
        )

        self.assertEqual(len(conditioned), 1)
        for issue_delay in issue_delays:
            self.assertEqual(
                optimized[issue_delay]["stay"],
                scalar_rows[issue_delay]["stay"],
            )

    def test_fresh_enemy_body_slab_is_conditioned_after_each_issue_age(
        self,
    ) -> None:
        left_fast = next(
            action for action in _PLANNER_ACTIONS
            if action.name == "left_fast"
        )

        def empty_hazard(
            positions_x: np.ndarray,
            positions_y: np.ndarray,
            **_ignored: object,
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            count = positions_x.size
            return (
                np.zeros(count),
                np.zeros(count, dtype=np.int32),
                np.full(count, np.inf),
            )

        issue_delays = (1, 3)
        scale_bits = _unit_scale_bits(5)
        base = delayed_issue_action_certificates(
            hazards_for_positions=empty_hazard,
            player_x=100.0,
            player_y=300.0,
            actions=(left_fast,),
            issue_delay_frames=issue_delays,
            pickup_delay_frames=(0,),
            horizon_frames=5,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=scale_bits,
            laser_scale_bits=scale_bits,
            pipeline_root=LocalPipelineRoot("stay", "stay"),
        )
        recertified = _recertify_delayed_issue_rows_for_fresh_enemy_bodies(
            certificates_by_issue_delay=base,
            root=LocalPipelineRoot("stay", "stay"),
            actions=(left_fast,),
            issue_delay_frames=issue_delays,
            pickup_delay_frames=(0,),
            horizon_frames=5,
            player_x=100.0,
            player_y=300.0,
            enemy_bodies=(
                EnemyBody(
                    pointer=0x1000,
                    x=84.0,
                    y=300.0,
                    vx=0.0,
                    vy=0.0,
                    half_width=1.0,
                    half_height=1.0,
                    flags=1,
                ),
            ),
            player_scale_bits=scale_bits,
            laser_scale_bits=scale_bits,
        )

        self.assertGreater(
            recertified[1]["left_fast"].worst_collisions, 0
        )
        self.assertEqual(
            recertified[3]["left_fast"].worst_collisions, 0
        )

    def test_packed_delayed_paths_match_native_order_scalar_bits(self) -> None:
        horizon = 9
        scale_bits = (
            TH08_UNIT_TIME_SCALE_BITS,
            0x3F000000,
            0x3F400000,
        ) * 3
        root = LocalPipelineRoot(
            active_action="up_left",
            held_desired_action="right_fast",
            pending_action="right_fast",
            remaining_delay_support=(0, 2, 5),
        )
        issue_delays = (0, 3, 6)
        pickup_delays = (0, 2)
        branches = enumerate_delayed_issue_pipeline_branches(
            root=root,
            selected_action="down_left",
            issue_delay_frames=issue_delays,
            pickup_delay_frames=pickup_delays,
            horizon_frames=horizon,
        )
        packed = _delayed_causal_pipeline_player_positions(
            root=root,
            selected_action="down_left",
            issue_delay_frames=issue_delays,
            pickup_delay_frames=pickup_delays,
            horizon_frames=horizon,
            player_x=9.25,
            player_y=430.75,
            player_scale_bits=scale_bits,
        )
        action_by_name = {action.name: action for action in _PLANNER_ACTIONS}
        expected = [[(9.25, 430.75) for _ in branches]]
        branch_positions = expected[0]
        for step in range(1, horizon + 1):
            branch_positions = [
                _advance_planner_action(
                    x,
                    y,
                    action_by_name[branch.active_actions[step - 1]],
                    time_scale_bits=scale_bits[step - 1],
                )
                for (x, y), branch in zip(branch_positions, branches)
            ]
            expected.append(branch_positions)

        def bits(value: float) -> bytes:
            return struct.pack("<f", value)

        self.assertEqual(len(packed), len(expected))
        for packed_step, expected_step in zip(packed, expected):
            self.assertEqual(len(packed_step), len(expected_step))
            for packed_position, expected_position in zip(
                packed_step, expected_step
            ):
                self.assertEqual(bits(packed_position[0]), bits(expected_position[0]))
                self.assertEqual(bits(packed_position[1]), bits(expected_position[1]))

    def test_delayed_issue_table_is_conditioned_on_observed_issue_age(
        self,
    ) -> None:
        left_fast = next(
            action for action in _PLANNER_ACTIONS
            if action.name == "left_fast"
        )
        right = next(
            action for action in _PLANNER_ACTIONS
            if action.name == "right"
        )

        def terminal_right_hazard(
            positions_x: np.ndarray,
            positions_y: np.ndarray,
            *,
            step: int,
            **_ignored: object,
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            clearance = (
                100.0 - positions_x
                if step == 5
                else np.full(positions_x.size, 100.0)
            )
            collisions = (clearance <= 0.0).astype(np.int32)
            risk = np.square(np.maximum(-clearance, 0.0))
            return risk, collisions, clearance

        rows = delayed_issue_action_certificates(
            hazards_for_positions=terminal_right_hazard,
            player_x=100.0,
            player_y=300.0,
            actions=(left_fast, right),
            issue_delay_frames=(1, 3),
            pickup_delay_frames=(0, 2),
            horizon_frames=5,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(5),
            laser_scale_bits=_unit_scale_bits(5),
            pipeline_root=LocalPipelineRoot("right", "right"),
        )

        self.assertEqual(rows[1]["left_fast"].worst_collisions, 0)
        self.assertGreater(rows[1]["left_fast"].min_clearance, 0.0)
        self.assertGreater(rows[3]["left_fast"].worst_collisions, 0)
        self.assertFalse(rows[1]["right"].write_required)
        self.assertEqual(rows[1]["right"].pipeline_branch_count, 1)
        self.assertEqual(
            rows[1]["right"].worst_collisions,
            rows[3]["right"].worst_collisions,
        )

    def test_causal_player_paths_preserve_held_no_write_pending_support(
        self,
    ) -> None:
        positions = _causal_pipeline_player_positions(
            root=LocalPipelineRoot(
                active_action="left",
                held_desired_action="right",
                pending_action="right",
                remaining_delay_support=(1, 3),
            ),
            selected_action="right",
            delay_frames=(0, 1, 2, 3),
            horizon_frames=4,
            player_x=100.0,
            player_y=200.0,
            player_scale_bits=_unit_scale_bits(4),
        )

        self.assertEqual(len(positions), 5)
        self.assertEqual(len(positions[0]), 2)
        self.assertAlmostEqual(positions[1][0][0], 97.69999694824219)
        self.assertAlmostEqual(positions[1][1][0], 97.69999694824219)
        self.assertGreater(positions[2][0][0], positions[2][1][0])
        self.assertEqual(
            {position[1] for step in positions for position in step},
            {200.0},
        )

    def test_future_birth_geometry_is_consumed_during_publication_prefix(
        self,
    ) -> None:
        body = AabbTrajectoryHazard(
            samples=(
                None,
                AabbHazard(192.0, 400.0, 1.0, 1.0),
                AabbHazard(192.0, 400.0, 1.0, 1.0),
            )
        )
        fire = FutureDirectFire(
            source="test:prefix",
            activation_frames=(1,),
            bullet_type=2,
            origin_x=FloatInterval.point(192.0),
            origin_y=FloatInterval.point(400.0),
            mode=1,
            count1=1,
            count2=1,
            speed1=FloatInterval.point(0.0),
            speed2=FloatInterval.point(0.0),
            angle1=FloatInterval.point(0.0),
            angle2=FloatInterval.point(0.0),
            aim_angle=FloatInterval.point(0.0),
            half_width=1.0,
            half_height=1.0,
            original_flags=0x203,
            transform_program_zero=True,
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=2,
            events=(fire,),
            aabb_trajectories=(body,),
            source_semantics_version="test-prefix-v1",
        )
        common = dict(
            player_x=192.0,
            player_y=400.0,
            previous_mask=FOCUS,
            actions=_PLANNER_ACTIONS,
            delay_frames=(0,),
            action_hold_frames=2,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(2),
            laser_scale_bits=_unit_scale_bits(2),
            pipeline_root=LocalPipelineRoot("stay", "stay"),
        )

        current_only = _robust_action_certificates(**common)
        covered = _robust_action_certificates(
            **common,
            future_hazard_projection=projection,
        )

        self.assertEqual(current_only["stay"].worst_collisions, 0)
        self.assertGreater(covered["stay"].worst_collisions, 0)
        self.assertLessEqual(covered["stay"].min_clearance, 0.0)

    def test_explicit_root_certificate_reports_segmented_timing(self) -> None:
        root = LocalPipelineRoot(
            active_action="stay",
            held_desired_action="right",
            pending_action="right",
            remaining_delay_support=(1, 2),
        )
        timing = _LocalCertificateTimingAccumulator()
        certificates = _robust_action_certificates(
            player_x=192.0,
            player_y=400.0,
            previous_mask=SHOT | FOCUS | RIGHT,
            actions=_PLANNER_ACTIONS,
            delay_frames=(1, 2),
            action_hold_frames=2,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(4),
            laser_scale_bits=_unit_scale_bits(4),
            pipeline_root=root,
            timing_accumulator=timing,
        )

        snapshot = timing.snapshot()
        self.assertEqual(snapshot.calls, 1)
        self.assertEqual(snapshot.explicit_root_calls, 1)
        self.assertGreater(
            snapshot.maximum_branch_count,
            len(_PLANNER_ACTIONS),
        )
        self.assertEqual(set(certificates), {
            action.name for action in _PLANNER_ACTIONS
        })
        segmented = (
            snapshot.validation_ms
            + snapshot.hazard_projection_ms
            + snapshot.branch_setup_ms
            + snapshot.geometry_kernel_ms
            + snapshot.reduction_ms
        )
        self.assertAlmostEqual(
            snapshot.certificate_total_ms,
            segmented,
            places=6,
        )

        shadow = _direct_root_certificate_shadow(
            root=root,
            player_x=192.0,
            player_y=400.0,
            previous_mask=SHOT | FOCUS | RIGHT,
            delay_frames=(1, 2),
            action_hold_frames=2,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(4),
            laser_scale_bits=_unit_scale_bits(4),
        )
        self.assertEqual(
            shadow["role"],
            "post_issue_shadow_no_action_authority",
        )
        self.assertTrue(shadow["computed_after_input"])
        self.assertEqual(shadow["timing"]["explicit_root_calls"], 1)

    def test_direct_trace_root_is_cross_checked(self) -> None:
        active_mask = SHOT | FOCUS | RIGHT
        held_mask = SHOT | FOCUS | DOWN | RIGHT
        row = {
            "input_snapshot": {"current": active_mask},
            "local_pipeline_root": {
                "role": "shadow_no_action_authority",
                "active_action": "right",
                "active_mask": active_mask,
                "held_desired_action": "down_right",
                "held_desired_mask": held_mask,
                "pending_action": "down_right",
                "pending_mask": held_mask,
                "remaining_delay_support": [1, 3],
                "issue_age": 2,
                "overdue": False,
                "estimator_consistent": True,
            },
        }

        root, parsed_held_mask, issue_age, overdue = (
            local_pipeline_root_from_trace(row)
        )

        self.assertEqual(root.active_action, "right")
        self.assertEqual(root.pending_action, "down_right")
        self.assertEqual(root.remaining_delay_support, (1, 3))
        self.assertEqual(parsed_held_mask, held_mask)
        self.assertEqual(issue_age, 2)
        self.assertFalse(overdue)

        row["local_pipeline_root"]["active_action"] = "left"
        with self.assertRaises(ValueError):
            local_pipeline_root_from_trace(row)

        aliased_stay_row = {
            "input_snapshot": {"current": SHOT},
            "local_pipeline_root": {
                "role": "shadow_no_action_authority",
                "active_action": "stay",
                "active_mask": SHOT,
                "held_desired_action": "stay",
                "held_desired_mask": SHOT | FOCUS,
                "pending_action": None,
                "pending_mask": None,
                "remaining_delay_support": [],
                "issue_age": None,
                "overdue": False,
                "estimator_consistent": True,
            },
        }
        with self.assertRaises(ValueError):
            local_pipeline_root_from_trace(aliased_stay_row)

    def test_vectorized_boundary_risk_matches_scalar(self) -> None:
        positions_x = np.asarray(
            [32.0, 39.5, 192.0, 344.5, 352.0],
            dtype=np.float32,
        )
        positions_y = np.asarray(
            [16.0, 27.0, 240.0, 437.5, 448.0],
            dtype=np.float32,
        )

        expected = np.fromiter(
            (
                _boundary_risk(float(x), float(y))
                for x, y in zip(positions_x, positions_y)
            ),
            dtype=np.float64,
        )
        actual = _boundary_risk_for_positions(
            positions_x,
            positions_y,
        )

        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)

    def test_hazard_batch_is_invariant_to_companion_positions(self) -> None:
        bullets = (
            Bullet(190.0, 210.0, 0.0, 0.0, 3.0, 3.0),
            Bullet(305.0, 310.0, 0.0, 0.0, 4.0, 4.0),
        )
        bullet_frame = _build_bullet_frames(
            bullets,
            horizon=3,
            snapshot_lag=0,
        )[2]
        laser_frame = _build_packed_laser_collision_frames(
            (Laser(120.0, 260.0, 0.0, 0.0, 100.0, 6.0),),
            horizon=3,
        )[2]
        positions_x = np.asarray([82.0, 300.0], dtype=np.float32)
        positions_y = np.asarray([165.0, 390.0], dtype=np.float32)

        batch = _hazards_for_positions(
            positions_x,
            positions_y,
            step=3,
            bullet_frame=bullet_frame,
            lasers=laser_frame,
            enemy_bodies=(),
        )
        scalar = tuple(
            np.concatenate(
                [
                    _hazards_for_positions(
                        positions_x[index : index + 1],
                        positions_y[index : index + 1],
                        step=3,
                        bullet_frame=bullet_frame,
                        lasers=laser_frame,
                        enemy_bodies=(),
                    )[field]
                    for index in range(len(positions_x))
                ]
            )
            for field in range(3)
        )

        np.testing.assert_allclose(batch[0], scalar[0], rtol=0.0, atol=0.0)
        np.testing.assert_array_equal(batch[1], scalar[1])
        np.testing.assert_allclose(batch[2], scalar[2], rtol=0.0, atol=0.0)

    def scalar_certificates(
        self,
        *,
        root: LocalPipelineRoot,
        bullets: tuple[Bullet, ...],
        enemy_bodies: tuple[EnemyBody, ...],
        delay_frames: tuple[int, ...],
        action_hold_frames: int,
        player_x: float,
        player_y: float,
        snapshot_lag: int = 0,
        player_scale_bits: tuple[int, ...] | None = None,
    ):
        horizon = action_hold_frames + max(delay_frames)
        player_scale_bits = (
            _unit_scale_bits(horizon)
            if player_scale_bits is None
            else player_scale_bits
        )
        bullet_frames = _build_bullet_frames(
            bullets,
            horizon=horizon,
            snapshot_lag=-max(0, snapshot_lag),
        )
        laser_frames = _build_packed_laser_collision_frames(
            (),
            horizon=horizon,
            time_scale_schedule_bits=_unit_scale_bits(horizon),
        )

        def sample(
            x: float,
            y: float,
            step: int,
        ) -> tuple[float, int, float]:
            risk, collisions, clearance = _hazards_for_positions(
                np.asarray([x], dtype=np.float32),
                np.asarray([y], dtype=np.float32),
                step=step,
                bullet_frame=bullet_frames[step - 1],
                lasers=laser_frames[step - 1],
                enemy_bodies=enemy_bodies,
            )
            return (
                float(risk[0]),
                int(collisions[0]),
                float(clearance[0]),
            )

        return scalar_local_pipeline_certificates(
            root=root,
            selected_actions=tuple(
                action.name for action in _PLANNER_ACTIONS
            ),
            action_velocities={
                **{
                    action.name: (action.dx, action.dy)
                    for action in _PLANNER_ACTIONS
                },
                "stay_unfocused": (0.0, 0.0),
            },
            delay_frames=delay_frames,
            horizon_frames=horizon,
            start_x=player_x,
            start_y=player_y,
            bounds=(
                PLAYFIELD_LEFT,
                PLAYFIELD_RIGHT,
                PLAYFIELD_TOP,
                PLAYFIELD_BOTTOM,
            ),
            hazard_sample=sample,
            boundary_risk=_boundary_risk,
            movement_scales=tuple(
                float32_from_bits(bits) for bits in player_scale_bits
            ),
        )

    def test_unfocused_stay_is_a_distinct_write_identity(self) -> None:
        root = LocalPipelineRoot(
            active_action="right_fast",
            held_desired_action="stay_unfocused",
            pending_action="stay_unfocused",
            remaining_delay_support=(2,),
        )
        common = {
            "player_x": 190.0,
            "player_y": 260.0,
            "previous_mask": SHOT,
            "actions": _PLANNER_ACTIONS,
            "delay_frames": (1, 3),
            "action_hold_frames": 2,
            "bullets": (
                Bullet(205.0, 260.0, 0.0, 0.0, 4.0, 4.0),
            ),
            "lasers": (),
            "enemy_bodies": (),
            "snapshot_lag": 0,
            "player_scale_bits": _unit_scale_bits(5),
            "laser_scale_bits": _unit_scale_bits(5),
        }
        packed = _robust_action_certificates(
            **common,
            pipeline_root=root,
        )
        scalar = self.scalar_certificates(
            root=root,
            bullets=common["bullets"],
            enemy_bodies=(),
            delay_frames=common["delay_frames"],
            action_hold_frames=common["action_hold_frames"],
            player_x=common["player_x"],
            player_y=common["player_y"],
        )

        self.assertTrue(packed["stay"].write_required)
        self.assertEqual(
            packed["stay"].pipeline_branch_count,
            len(common["delay_frames"]),
        )
        self.assertEqual(
            packed["stay"].worst_collisions,
            scalar["stay"].worst_collisions,
        )
        self.assertAlmostEqual(
            packed["stay"].min_clearance,
            scalar["stay"].min_clearance,
            places=5,
        )

    def test_pending_hold_matches_independent_scalar_oracle(self) -> None:
        root = LocalPipelineRoot(
            active_action="stay",
            held_desired_action="left",
            pending_action="left",
            remaining_delay_support=(1, 2, 3),
        )
        bullets = (
            Bullet(178.0, 375.0, 0.0, 2.0, 3.0, 3.0),
            Bullet(212.0, 390.0, -1.0, 1.0, 4.0, 4.0),
        )
        enemy_bodies = (
            EnemyBody(
                1,
                192.0,
                350.0,
                0.0,
                1.0,
                8.0,
                8.0,
                0,
            ),
        )
        arguments = dict(
            root=root,
            bullets=bullets,
            enemy_bodies=enemy_bodies,
            delay_frames=(2, 3, 4),
            action_hold_frames=4,
            player_x=192.0,
            player_y=400.0,
            snapshot_lag=1,
        )

        expected = self.scalar_certificates(**arguments)
        actual = _robust_action_certificates(
            player_x=arguments["player_x"],
            player_y=arguments["player_y"],
            previous_mask=0,
            actions=_PLANNER_ACTIONS,
            delay_frames=arguments["delay_frames"],
            action_hold_frames=arguments["action_hold_frames"],
            bullets=bullets,
            lasers=(),
            enemy_bodies=enemy_bodies,
            snapshot_lag=arguments["snapshot_lag"],
            player_scale_bits=_unit_scale_bits(8),
            laser_scale_bits=_unit_scale_bits(8),
            pipeline_root=root,
        )

        for action in _PLANNER_ACTIONS:
            scalar = expected[action.name]
            packed = actual[action.name]
            self.assertEqual(
                packed.worst_collisions,
                scalar.worst_collisions,
                action.name,
            )
            self.assertAlmostEqual(
                packed.min_clearance,
                scalar.min_clearance,
                delta=1e-3,
                msg=action.name,
            )
            self.assertAlmostEqual(
                packed.cvar_risk,
                scalar.cvar_risk,
                delta=1e-1,
                msg=action.name,
            )
            self.assertEqual(
                packed.write_required,
                scalar.write_required,
                action.name,
            )
            self.assertEqual(
                packed.pipeline_branch_count,
                scalar.branch_count,
                action.name,
            )
            self.assertEqual(
                packed.worst_delay,
                scalar.worst_new_delay,
                action.name,
            )
            self.assertEqual(
                packed.worst_pending_remaining,
                scalar.worst_pending_remaining,
                action.name,
            )

    def test_randomized_pipeline_roots_match_scalar_oracle(self) -> None:
        randomizer = random.Random(20260726)
        action_names = tuple(action.name for action in _PLANNER_ACTIONS)
        for seed in range(24):
            active = action_names[seed % len(action_names)]
            if seed % 3:
                held = action_names[(seed * 5 + 1) % len(action_names)]
                root = LocalPipelineRoot(
                    active_action=active,
                    held_desired_action=held,
                    pending_action=held,
                    remaining_delay_support=(
                        (1, 2, 4) if seed % 2 else (2, 3)
                    ),
                )
            else:
                root = LocalPipelineRoot(
                    active_action=active,
                    held_desired_action=active,
                )
            player_x = randomizer.uniform(40.0, 344.0)
            player_y = randomizer.uniform(80.0, 432.0)
            bullets = tuple(
                Bullet(
                    randomizer.uniform(20.0, 364.0),
                    randomizer.uniform(40.0, 448.0),
                    randomizer.uniform(-2.0, 2.0),
                    randomizer.uniform(-1.0, 3.0),
                    randomizer.uniform(1.0, 5.0),
                    randomizer.uniform(1.0, 5.0),
                )
                for _ in range(5)
            )
            enemy_bodies = tuple(
                EnemyBody(
                    index + 1,
                    randomizer.uniform(20.0, 364.0),
                    randomizer.uniform(40.0, 448.0),
                    randomizer.uniform(-1.0, 1.0),
                    randomizer.uniform(-1.0, 1.0),
                    randomizer.uniform(3.0, 12.0),
                    randomizer.uniform(3.0, 12.0),
                    0,
                    randomizer.uniform(0.0, 1.0),
                )
                for index in range(2)
            )
            delay_frames = (1, 2, 3)
            action_hold_frames = 3
            scale_choices = (
                TH08_UNIT_TIME_SCALE_BITS,
                0x3F000000,
                0x3FC00000,
                0x00000000,
            )
            player_scale_bits = tuple(
                scale_choices[(seed + step) % len(scale_choices)]
                for step in range(action_hold_frames + max(delay_frames))
            )
            expected = self.scalar_certificates(
                root=root,
                bullets=bullets,
                enemy_bodies=enemy_bodies,
                delay_frames=delay_frames,
                action_hold_frames=action_hold_frames,
                player_x=player_x,
                player_y=player_y,
                player_scale_bits=player_scale_bits,
            )
            actual = _robust_action_certificates(
                player_x=player_x,
                player_y=player_y,
                previous_mask=0,
                actions=_PLANNER_ACTIONS,
                delay_frames=delay_frames,
                action_hold_frames=action_hold_frames,
                bullets=bullets,
                lasers=(),
                enemy_bodies=enemy_bodies,
                snapshot_lag=0,
                player_scale_bits=player_scale_bits,
                laser_scale_bits=_unit_scale_bits(len(player_scale_bits)),
                pipeline_root=root,
            )
            for action in _PLANNER_ACTIONS:
                scalar = expected[action.name]
                packed = actual[action.name]
                self.assertEqual(
                    packed.worst_collisions,
                    scalar.worst_collisions,
                    (seed, action.name),
                )
                self.assertAlmostEqual(
                    packed.min_clearance,
                    scalar.min_clearance,
                    delta=1e-3,
                    msg=str((seed, action.name)),
                )
                self.assertAlmostEqual(
                    packed.cvar_risk,
                    scalar.cvar_risk,
                    delta=1e-1,
                    msg=str((seed, action.name)),
                )

    def test_no_pending_root_preserves_legacy_hard_labels(self) -> None:
        common = dict(
            player_x=192.0,
            player_y=400.0,
            previous_mask=0x04,
            actions=_PLANNER_ACTIONS,
            delay_frames=(2, 3, 4),
            action_hold_frames=3,
            bullets=(
                Bullet(192.0, 370.0, 0.0, 2.5, 3.0, 3.0),
            ),
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            player_scale_bits=_unit_scale_bits(7),
            laser_scale_bits=_unit_scale_bits(7),
        )

        legacy = _legacy_robust_action_certificates(**common)
        packed = _robust_action_certificates(**common)

        for action in _PLANNER_ACTIONS:
            self.assertEqual(
                packed[action.name].worst_collisions,
                legacy[action.name].worst_collisions,
                action.name,
            )
            self.assertAlmostEqual(
                packed[action.name].min_clearance,
                legacy[action.name].min_clearance,
                delta=1e-3,
                msg=action.name,
            )


if __name__ == "__main__":
    unittest.main()
