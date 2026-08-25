#!/usr/bin/env python3
"""Tests for the TH08-to-neutral corridor planning boundary."""

from __future__ import annotations

import math
import random
import unittest
from dataclasses import replace

import numpy as np

from th08_bullet_template_contract import BULLET_TEMPLATE_PROFILES
from th08_corridor_adapter import (
    TH08_CORRIDOR_CELL_RADIUS,
    TH08_CORRIDOR_CONFIG,
    TH08_VIABILITY_ACTIONS,
    lower_bullet_trajectories,
    lower_bullets,
    lower_enemy_bodies,
    lower_lasers,
    lower_lasers_packed,
    lower_th08_corridor_hazards,
)
from th08_live.local_hazards import _build_bullet_frames
from th08_live_dodge_agent import Bullet, EnemyBody, Laser
from th08_laser_model import LaserPhase, spawn_laser_state
from touhou_control.corridor import AabbHazard, AabbTrajectoryHazard
from touhou_control.trajectory import CollisionStateChange, VelocityChange
from touhou_control.packed_hazards import PackedSegmentFrames


class Th08CorridorAdapterTests(unittest.TestCase):
    def test_live_corridor_keeps_long_horizon_at_coarse_resolution(self) -> None:
        self.assertEqual(TH08_CORRIDOR_CONFIG.grid_step, 16.0)
        self.assertEqual(TH08_CORRIDOR_CONFIG.frames_per_layer, 8)
        self.assertEqual(TH08_CORRIDOR_CONFIG.horizon_frames, 80)
        self.assertAlmostEqual(
            TH08_CORRIDOR_CONFIG.required_clearance,
            TH08_CORRIDOR_CELL_RADIUS,
        )
        self.assertAlmostEqual(
            TH08_CORRIDOR_CELL_RADIUS,
            math.sqrt(2.0) * 8.0,
        )

    def test_future_birth_trajectory_is_retained_for_clearance(self) -> None:
        trajectory = AabbTrajectoryHazard(
            (
                None,
                AabbHazard(
                    x=192.0,
                    y=368.0,
                    half_width=2.0,
                    half_height=2.0,
                ),
            )
        )
        hazards = lower_th08_corridor_hazards(
            bullets=(),
            lasers=(),
            future_aabb_trajectories=(trajectory,),
        )
        self.assertEqual(hazards.aabb_trajectories, (trajectory,))

    def test_viability_actions_match_live_route2_action_names_and_speeds(
        self,
    ) -> None:
        by_name = {action.name: action for action in TH08_VIABILITY_ACTIONS}
        self.assertEqual(len(by_name), 17)
        self.assertAlmostEqual(by_name["left"].velocity_x, -2.299999952316284)
        self.assertAlmostEqual(by_name["left_fast"].velocity_x, -4.0)
        self.assertAlmostEqual(
            by_name["up_right"].velocity_x,
            1.6263456344604492,
        )
        self.assertEqual(
            (by_name["stay"].velocity_x, by_name["stay"].velocity_y),
            (0.0, 0.0),
        )

    def test_read_lag_projects_bullet_before_corridor_prediction(self) -> None:
        hazards = lower_bullets(
            (Bullet(10.0, 20.0, 2.0, -1.0, 3.0, 4.0),),
            snapshot_lag=3,
        )
        self.assertEqual(len(hazards), 1)
        self.assertAlmostEqual(hazards[0].x, 16.0)
        self.assertAlmostEqual(hazards[0].y, 17.0)
        self.assertGreater(hazards[0].base_uncertainty, 0.0)

    def test_transforming_bullet_gets_growing_robust_margin(self) -> None:
        straight = lower_bullets(
            (Bullet(10.0, 20.0, 0.0, 1.0, 2.0, 2.0),),
            snapshot_lag=0,
        )[0]
        transformed = lower_bullets(
            (Bullet(10.0, 20.0, 0.0, 1.0, 2.0, 2.0, transform_flags=1),),
            snapshot_lag=0,
        )[0]
        self.assertGreater(
            transformed.base_uncertainty, straight.base_uncertainty
        )
        self.assertGreater(
            transformed.uncertainty_per_frame,
            straight.uncertainty_per_frame,
        )

    def test_future_policy_epoch_projects_and_inflates_bullet(self) -> None:
        present = lower_bullets(
            (Bullet(10.0, 20.0, 2.0, -1.0, 3.0, 4.0),),
            snapshot_lag=1,
        )[0]
        future = lower_bullets(
            (Bullet(10.0, 20.0, 2.0, -1.0, 3.0, 4.0),),
            snapshot_lag=1,
            forecast_frames=12,
        )[0]
        self.assertEqual((future.x, future.y), (36.0, 7.0))
        self.assertGreater(future.base_uncertainty, present.base_uncertainty)

    def test_velocity_event_bullet_uses_time_indexed_trajectory(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            2.0,
            0.0,
            3.0,
            4.0,
            velocity_changes=(
                VelocityChange(3, 0.0, 0.0),
                VelocityChange(6, -1.0, 0.0),
            ),
        )
        self.assertEqual(lower_bullets((bullet,), snapshot_lag=0), ())
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=0,
            horizon_frames=7,
        )[0]
        self.assertEqual(trajectory.sample(2).x, 14.0)
        self.assertEqual(trajectory.sample(3).x, 14.0)
        self.assertEqual(trajectory.sample(6).x, 13.0)
        self.assertEqual(trajectory.sample(7).x, 12.0)

    def test_piecewise_projection_consumes_and_rebases_past_events(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            2.0,
            0.0,
            3.0,
            4.0,
            velocity_changes=(
                VelocityChange(3, 0.0, 0.0),
                VelocityChange(6, -1.0, 0.0),
            ),
        )
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=4,
            horizon_frames=4,
        )[0]
        self.assertEqual(trajectory.sample(0).x, 14.0)
        self.assertEqual(trajectory.sample(1).x, 14.0)
        self.assertEqual(trajectory.sample(2).x, 13.0)
        self.assertEqual(trajectory.motion.changes[0].frame, 2)

    def test_callback_collision_gate_removes_only_disabled_interval(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            2.0,
            0.0,
            3.0,
            4.0,
            collision_state_changes=(
                CollisionStateChange(3, False),
                CollisionStateChange(6, True),
            ),
        )
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=0,
            horizon_frames=7,
        )[0]

        self.assertIsNotNone(trajectory.sample(2))
        self.assertIsNone(trajectory.sample(3))
        self.assertIsNone(trajectory.sample(5))
        self.assertIsNotNone(trajectory.sample(6))

        observed_disabled = replace(
            bullet,
            callback_aux_state=1,
            collision_state_changes=(),
        )
        self.assertEqual(
            lower_bullets((observed_disabled,), snapshot_lag=0),
            (),
        )
        self.assertEqual(
            lower_bullet_trajectories(
                (observed_disabled,),
                snapshot_lag=0,
                horizon_frames=7,
            ),
            (),
        )

    def test_spawn_lifecycle_is_not_lowered_as_ordinary_motion(self) -> None:
        terminal_age = BULLET_TEMPLATE_PROFILES[0].state2_terminal_age
        bullet = Bullet(
            0.0,
            0.0,
            2.0,
            0.0,
            1.0,
            1.0,
            native_state=2,
            native_state_timer_elapsed=0,
            bullet_type=0,
        )
        self.assertEqual(lower_bullets((bullet,), snapshot_lag=0), ())
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=0,
            horizon_frames=terminal_age + 1,
        )[0]
        self.assertIsNone(trajectory.sample(terminal_age - 1))
        terminal = trajectory.sample(terminal_age)
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertAlmostEqual(terminal.x, terminal_age + 2.0)
        after = trajectory.sample(terminal_age + 1)
        self.assertIsNotNone(after)
        assert after is not None
        self.assertAlmostEqual(after.x, terminal_age + 4.0)

    def test_all_spawn_lifecycle_classes_contain_local_source_recurrence(
        self,
    ) -> None:
        for bullet_type, profile in enumerate(BULLET_TEMPLATE_PROFILES):
            for state, terminal_age in (
                (2, profile.state2_terminal_age),
                (3, profile.state3_terminal_age),
                (4, profile.state4_terminal_age),
            ):
                with self.subTest(bullet_type=bullet_type, state=state):
                    bullet = Bullet(
                        13.25,
                        -7.5,
                        3.125,
                        -1.75,
                        1.0,
                        1.5,
                        native_state=state,
                        native_state_timer_elapsed=terminal_age - 3,
                        bullet_type=bullet_type,
                    )
                    local_frames = _build_bullet_frames(
                        (bullet,),
                        horizon=5,
                        snapshot_lag=0,
                    )
                    trajectory = lower_bullet_trajectories(
                        (bullet,),
                        snapshot_lag=0,
                        horizon_frames=5,
                    )[0]
                    for frame, local in enumerate(local_frames, start=1):
                        lethal = (
                            int(local[5][0]) == 1
                            and int(local[6][0]) == 0
                        )
                        sample = trajectory.sample(frame)
                        self.assertEqual(sample is not None, lethal)
                        if sample is None:
                            continue
                        uncertainty = (
                            sample.base_uncertainty
                            + sample.uncertainty_per_frame * frame
                        )
                        self.assertLessEqual(
                            abs(sample.x - float(local[0][0])),
                            uncertainty,
                        )
                        self.assertLessEqual(
                            abs(sample.y - float(local[1][0])),
                            uncertainty,
                        )

    def test_lifecycle_and_callback_schedules_share_native_order(self) -> None:
        terminal_age = BULLET_TEMPLATE_PROFILES[0].state2_terminal_age
        bullet = Bullet(
            0.0,
            0.0,
            2.0,
            0.0,
            1.0,
            1.0,
            native_state=2,
            native_state_timer_elapsed=terminal_age - 3,
            bullet_type=0,
            velocity_changes=(
                VelocityChange(2, 4.0, 0.0),
                VelocityChange(4, -1.0, 0.0),
            ),
            collision_state_changes=(
                CollisionStateChange(2, False),
                CollisionStateChange(4, True),
            ),
        )
        local_frames = _build_bullet_frames(
            (bullet,),
            horizon=5,
            snapshot_lag=0,
        )
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=0,
            horizon_frames=5,
        )[0]
        self.assertIsNone(trajectory.sample(3))
        self.assertIsNotNone(trajectory.sample(4))
        for frame, local in enumerate(local_frames, start=1):
            sample = trajectory.sample(frame)
            lethal = int(local[5][0]) == 1 and int(local[6][0]) == 0
            self.assertEqual(sample is not None, lethal)
            if sample is not None:
                self.assertLessEqual(
                    abs(sample.x - float(local[0][0])),
                    sample.base_uncertainty
                    + sample.uncertainty_per_frame * frame,
                )

    def test_future_policy_rebase_consumes_lifecycle_activation(self) -> None:
        terminal_age = BULLET_TEMPLATE_PROFILES[0].state2_terminal_age
        bullet = Bullet(
            5.0,
            9.0,
            2.0,
            -1.0,
            1.0,
            1.0,
            native_state=2,
            native_state_timer_elapsed=terminal_age - 3,
            bullet_type=0,
        )
        source_frames = _build_bullet_frames(
            (bullet,),
            horizon=5,
            snapshot_lag=0,
        )
        trajectory = lower_bullet_trajectories(
            (bullet,),
            snapshot_lag=0,
            forecast_frames=3,
            horizon_frames=2,
        )[0]
        root = trajectory.sample(0)
        self.assertIsNotNone(root)
        assert root is not None
        self.assertLessEqual(
            abs(root.x - float(source_frames[2][0][0])),
            root.base_uncertainty,
        )
        self.assertLessEqual(
            abs(root.y - float(source_frames[2][1][0])),
            root.base_uncertainty,
        )

    def test_random_lifecycle_callback_composition_contains_local_oracle(
        self,
    ) -> None:
        generator = random.Random(0x430E10)
        for case in range(256):
            bullet_type = generator.randrange(len(BULLET_TEMPLATE_PROFILES))
            profile = BULLET_TEMPLATE_PROFILES[bullet_type]
            state = generator.choice((2, 3, 4))
            terminal_age = {
                2: profile.state2_terminal_age,
                3: profile.state3_terminal_age,
                4: profile.state4_terminal_age,
            }[state]
            timer = generator.randrange(terminal_age)
            event_frames = tuple(
                sorted(generator.sample(range(1, 21), generator.randrange(5)))
            )
            velocity_changes = tuple(
                VelocityChange(
                    frame,
                    generator.uniform(-8.0, 8.0),
                    generator.uniform(-8.0, 8.0),
                )
                for frame in event_frames
            )
            collision_changes = tuple(
                CollisionStateChange(frame, bool(generator.randrange(2)))
                for frame in event_frames
            )
            bullet = Bullet(
                generator.uniform(-64.0, 448.0),
                generator.uniform(-64.0, 512.0),
                generator.uniform(-8.0, 8.0),
                generator.uniform(-8.0, 8.0),
                1.0,
                1.0,
                callback_aux_state=generator.randrange(2),
                velocity_changes=velocity_changes,
                collision_state_changes=collision_changes,
                native_state=state,
                native_state_timer_elapsed=timer,
                bullet_type=bullet_type,
            )
            with self.subTest(case=case, state=state, bullet_type=bullet_type):
                local_frames = _build_bullet_frames(
                    (bullet,),
                    horizon=20,
                    snapshot_lag=0,
                )
                trajectories = lower_bullet_trajectories(
                    (bullet,),
                    snapshot_lag=0,
                    horizon_frames=20,
                )
                trajectory = trajectories[0] if trajectories else None
                for frame, local in enumerate(local_frames, start=1):
                    lethal = (
                        int(local[5][0]) == 1
                        and int(local[6][0]) == 0
                    )
                    sample = (
                        trajectory.sample(frame)
                        if trajectory is not None
                        else None
                    )
                    self.assertEqual(sample is not None, lethal)
                    if sample is None:
                        continue
                    uncertainty = (
                        sample.base_uncertainty
                        + sample.uncertainty_per_frame * frame
                    )
                    self.assertLessEqual(
                        abs(sample.x - float(local[0][0])),
                        uncertainty,
                    )
                    self.assertLessEqual(
                        abs(sample.y - float(local[1][0])),
                        uncertainty,
                    )

    def test_spawn_lifecycle_without_type_fails_closed(self) -> None:
        bullet = Bullet(
            0.0,
            0.0,
            1.0,
            0.0,
            1.0,
            1.0,
            native_state=2,
            native_state_timer_elapsed=0,
            bullet_type=None,
        )
        with self.assertRaisesRegex(ValueError, "source template type"):
            lower_bullet_trajectories(
                (bullet,),
                snapshot_lag=0,
                horizon_frames=4,
            )

    def test_laser_uncertainty_accounts_for_snapshot_age(self) -> None:
        trajectory = lower_lasers(
            (Laser(12.0, 34.0, 0.5, 4.0, 80.0, 6.0),),
            snapshot_lag=5,
        )[0]
        hazard = trajectory.sample(0)
        self.assertIsNotNone(hazard)
        self.assertEqual(hazard.origin_x, 12.0)
        self.assertEqual(hazard.head, 80.0)
        self.assertEqual(hazard.base_uncertainty, 2.0)
        self.assertGreater(hazard.uncertainty_per_frame, 0.0)

    def test_lifecycle_laser_trajectory_omits_disabled_warning_frames(
        self,
    ) -> None:
        state = replace(
            spawn_laser_state(
                origin_x=12.0,
                origin_y=34.0,
                angle=0.0,
                speed=0.0,
                tail_distance=0.0,
                head_distance=80.0,
                maximum_length=80.0,
                width=16.0,
                warmup_frames=10,
                active_frames=20,
                fade_frames=10,
                collision_enable_frame=5,
                collision_disable_frame=5,
            ),
            timer=4,
        )
        laser = Laser(
            12.0,
            34.0,
            0.0,
            0.0,
            80.0,
            4.0,
            state,
        )
        trajectory = lower_lasers(
            (laser,),
            snapshot_lag=0,
            horizon_frames=2,
        )[0]
        self.assertIsNone(trajectory.sample(0))
        enabled = trajectory.sample(1)
        self.assertIsNotNone(enabled)
        assert enabled is not None
        self.assertLess(enabled.head - enabled.tail, 10.0)
        frozen = lower_lasers(
            (laser,),
            snapshot_lag=0,
            horizon_frames=2,
            time_scale_schedule_bits=(0, 0, 0),
        )
        self.assertEqual(frozen, ())

    def test_state_backed_laser_does_not_invent_horizon_drift(self) -> None:
        state = replace(
            spawn_laser_state(
                origin_x=12.0,
                origin_y=34.0,
                angle=0.0,
                speed=2.5,
                tail_distance=0.0,
                head_distance=80.0,
                maximum_length=80.0,
                width=16.0,
                warmup_frames=0,
                active_frames=200,
                fade_frames=10,
                collision_enable_frame=0,
                collision_disable_frame=5,
            ),
            phase=LaserPhase.ACTIVE,
        )
        trajectory = lower_lasers(
            (
                Laser(
                    12.0,
                    34.0,
                    0.0,
                    0.0,
                    80.0,
                    4.0,
                    state,
                    uncertainty=0.75,
                ),
            ),
            snapshot_lag=3,
            forecast_frames=16,
            horizon_frames=80,
        )[0]
        samples = tuple(
            sample
            for sample in trajectory.samples
            if sample is not None
        )
        self.assertTrue(samples)
        self.assertEqual(
            {sample.base_uncertainty for sample in samples},
            {0.75},
        )
        self.assertEqual(
            {sample.uncertainty_per_frame for sample in samples},
            {0.0},
        )

    def test_packed_laser_lowering_matches_object_reference_by_frame(
        self,
    ) -> None:
        state = replace(
            spawn_laser_state(
                origin_x=12.0,
                origin_y=34.0,
                angle=0.25,
                speed=1.5,
                tail_distance=0.0,
                head_distance=80.0,
                maximum_length=80.0,
                width=16.0,
                warmup_frames=3,
                active_frames=5,
                fade_frames=3,
                collision_enable_frame=2,
                collision_disable_frame=2,
            ),
            timer=1,
        )
        lasers = (
            Laser(12.0, 34.0, 0.25, 0.0, 80.0, 4.0, state, 0.75),
            Laser(80.0, 42.0, 1.0, -2.0, 40.0, 3.0),
        )
        reference = PackedSegmentFrames.from_trajectories(
            lower_lasers(
                lasers,
                snapshot_lag=1,
                forecast_frames=1,
                horizon_frames=10,
            ),
            frame_count=11,
        )
        packed = lower_lasers_packed(
            lasers,
            snapshot_lag=1,
            forecast_frames=1,
            horizon_frames=10,
        )
        np.testing.assert_array_equal(
            packed.frame_offsets,
            reference.frame_offsets,
        )
        for field in (
            "origin_x",
            "origin_y",
            "angle",
            "tail",
            "head",
            "half_width",
            "base_uncertainty",
            "uncertainty_per_frame",
        ):
            np.testing.assert_array_equal(
                getattr(packed, field),
                getattr(reference, field),
            )

    def test_live_lowering_emits_packed_lasers_without_segment_objects(
        self,
    ) -> None:
        hazards = lower_th08_corridor_hazards(
            bullets=(),
            lasers=(Laser(12.0, 34.0, 0.5, 4.0, 80.0, 6.0),),
            horizon_frames=4,
        )
        self.assertEqual(hazards.segment_trajectories, ())
        self.assertIsNotNone(hazards.packed_segments)
        assert hazards.packed_segments is not None
        self.assertEqual(hazards.packed_segments.frame_count, 5)
        self.assertEqual(hazards.packed_segments.sample_count, 5)

    def test_enemy_body_keeps_native_half_extents_and_motion(self) -> None:
        hazard = lower_enemy_bodies(
            (
                EnemyBody(
                    0x5826C0,
                    100.0,
                    80.0,
                    2.0,
                    -1.0,
                    12.0,
                    18.0,
                    5,
                ),
            ),
            snapshot_lag=3,
        )[0]
        self.assertEqual((hazard.x, hazard.y), (106.0, 77.0))
        self.assertEqual(
            (hazard.half_width, hazard.half_height),
            (12.0, 18.0),
        )
        self.assertGreater(hazard.uncertainty_per_frame, 0.0)

    def test_future_policy_epoch_inflates_laser_and_enemy_uncertainty(
        self,
    ) -> None:
        laser_trajectory = lower_lasers(
            (Laser(12.0, 34.0, 0.5, 4.0, 80.0, 6.0),),
            snapshot_lag=0,
            forecast_frames=10,
        )[0]
        laser = laser_trajectory.sample(0)
        self.assertIsNotNone(laser)
        enemy = lower_enemy_bodies(
            (
                EnemyBody(
                    0x5826C0,
                    100.0,
                    80.0,
                    2.0,
                    -1.0,
                    12.0,
                    18.0,
                    5,
                ),
            ),
            snapshot_lag=0,
            forecast_frames=10,
        )[0]
        self.assertEqual(laser.base_uncertainty, 4.0)
        self.assertEqual((enemy.x, enemy.y), (120.0, 70.0))
        self.assertEqual(enemy.base_uncertainty, 5.0)


if __name__ == "__main__":
    unittest.main()
