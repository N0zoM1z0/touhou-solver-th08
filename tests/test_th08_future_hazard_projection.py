"""Tests for versioned ordinary future-hazard publications."""

from __future__ import annotations

import unittest
from dataclasses import replace
import math

from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    FutureTaggedBulletCallback,
)
from th08_future_hazard_projection import (
    condition_future_hazard_projection_on_player_paths,
    complete_future_hazard_projection,
    unknown_future_hazard_projection,
)
from touhou_control.corridor import AabbHazard, AabbTrajectoryHazard


def _event() -> FutureDirectFire:
    return FutureDirectFire(
        source="enemy:7:aux0",
        activation_frames=(1, 2),
        bullet_type=2,
        origin_x=FloatInterval.point(100.0),
        origin_y=FloatInterval.point(80.0),
        mode=1,
        count1=1,
        count2=1,
        speed1=FloatInterval.point(1.0),
        speed2=FloatInterval.point(1.0),
        angle1=FloatInterval.point(0.0),
        angle2=FloatInterval.point(0.0),
        aim_angle=FloatInterval.point(0.0),
        half_width=2.0,
        half_height=2.0,
        original_flags=0x203,
        transform_program_zero=True,
    )


class FutureHazardProjectionTests(unittest.TestCase):
    def test_complete_projection_versions_consumed_trajectories(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(_event(),),
            source_semantics_version="test-source-v1",
        )
        self.assertTrue(projection.coverage.complete)
        self.assertEqual(projection.producer_count, 1)
        self.assertEqual(len(projection.trajectories), 2)
        self.assertEqual(len(projection.digest), 64)
        self.assertEqual(
            projection.record()["coverage"]["status"],
            "complete",
        )

    def test_policy_rebase_drops_prepublication_prefix(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(_event(),),
            source_semantics_version="test-source-v1",
        )
        rebased = projection.trajectories_for_policy(
            source_frame=104,
            horizon_frames=16,
        )
        self.assertEqual(len(rebased[0].minimum_radii), 17)
        self.assertEqual(
            rebased[0].radial_sample(0),
            projection.trajectories[0].radial_sample(4),
        )

    def test_rebase_beyond_covered_horizon_fails_closed(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(_event(),),
            source_semantics_version="test-source-v1",
        )
        with self.assertRaisesRegex(ValueError, "does not cover"):
            projection.trajectories_for_policy(
                source_frame=105,
                horizon_frames=16,
            )

    def test_future_enemy_body_trajectory_is_published_and_rebased(self) -> None:
        body = AabbTrajectoryHazard(
            samples=(
                None,
                None,
                AabbHazard(120.0, 60.0, 18.0, 18.0),
                AabbHazard(121.0, 61.0, 18.0, 18.0),
            )
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=3,
            events=(),
            aabb_trajectories=(body,),
            source_semantics_version="test-source-v1",
        )
        self.assertEqual(projection.record()["aabb_trajectory_count"], 1)
        rebased = projection.aabb_trajectories_for_policy(
            source_frame=101,
            horizon_frames=2,
        )
        self.assertIsNone(rebased[0].sample(0))
        self.assertEqual(rebased[0].sample(1).x, 120.0)
        self.assertEqual(projection.aabb_samples(-1), ())
        self.assertEqual(projection.aabb_samples(0), ())
        self.assertEqual(projection.aabb_samples(2)[0].x, 120.0)
        self.assertEqual(projection.aabb_samples(4), ())

    def test_projection_preindexes_annular_sector_frames(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(_event(),),
            source_semantics_version="test-source-v1",
        )
        packed = projection.packed_annular_sector_frames
        self.assertEqual(packed.frame_count, 21)
        self.assertEqual(packed.sample_count, sum(
            trajectory.radial_sample(frame) is not None
            for frame in range(21)
            for trajectory in projection.trajectories
        ))

    def test_bullet_type_is_part_of_projection_identity(self) -> None:
        type_two = replace(_event(), original_flags=0, bullet_type=2)
        type_seven = replace(type_two, bullet_type=7)
        projection_two = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(type_two,),
            source_semantics_version="test-source-v1",
        )
        projection_seven = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(type_seven,),
            source_semantics_version="test-source-v1",
        )

        # With no lifecycle flag these two types have identical supplied
        # geometry and trajectories. Their causal identities must still not
        # alias now that type controls other valid future states.
        self.assertEqual(
            projection_two.trajectories,
            projection_seven.trajectories,
        )
        self.assertNotEqual(projection_two.digest, projection_seven.digest)
        self.assertNotEqual(projection_two.version, projection_seven.version)

    def test_bullet_type_selects_lifecycle_terminal_age(self) -> None:
        type_two = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(replace(_event(), bullet_type=2, original_flags=0x02),),
            source_semantics_version="test-source-v1",
        )
        type_seven = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(replace(_event(), bullet_type=7, original_flags=0x02),),
            source_semantics_version="test-source-v1",
        )

        self.assertIsNotNone(type_two.trajectories[0].radial_sample(10))
        self.assertIsNone(type_seven.trajectories[0].radial_sample(20))

    def test_unknown_source_closure_has_no_authority(self) -> None:
        projection = unknown_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            reason="unsupported_callback:0x1234",
            source_semantics_version="test-source-v1",
        )
        self.assertTrue(projection.coverage.model_unknown)
        self.assertEqual(projection.coverage.unknown_from_frame, 101)
        self.assertEqual(projection.trajectories, ())

    def test_causal_player_path_narrows_future_aim_without_dropping_rng(self) -> None:
        event = replace(
            _event(),
            activation_frames=(2,),
            angle1=FloatInterval(-math.pi, math.pi),
            angle1_player_aim_coefficient=1.0,
            angle1_player_aim_residual=FloatInterval(-0.25, 0.25),
            angle2_player_aim_coefficient=0.0,
            angle2_player_aim_residual=FloatInterval.point(0.0),
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=10,
            events=(event,),
            source_semantics_version="test-source-causal-v1",
        )
        paths = tuple(
            (((200.0, 80.0),)) for _ in range(11)
        )

        conditioned = condition_future_hazard_projection_on_player_paths(
            projection,
            source_frame=100,
            horizon_frames=10,
            player_positions_by_step=paths,
        )

        self.assertTrue(conditioned.coverage.complete)
        self.assertEqual(len(conditioned.direct_fire_events), 1)
        causal = conditioned.direct_fire_events[0]
        self.assertEqual(causal.activation_frames, (2,))
        self.assertLess(causal.angle1.upper - causal.angle1.lower, 0.501)
        wrapped_midpoint = (
            (causal.angle1.midpoint + math.pi) % (2.0 * math.pi)
            - math.pi
        )
        self.assertAlmostEqual(wrapped_midpoint, 0.0, places=5)
        self.assertEqual(
            causal.angle2,
            FloatInterval.point(0.0),
        )

    def test_tagged_callback_is_in_identity_and_rebases_causally(self) -> None:
        callback = FutureTaggedBulletCallback(
            source="enemy:7:main:callback14",
            frame=7,
            callback_index=14,
            tag_mask=0x100000,
            callback_angle=None,
            callback_speed=FloatInterval.point(2.5),
        )
        event = replace(
            _event(),
            activation_frames=(5,),
            original_flags=0x100000,
            angle1_player_aim_coefficient=0.0,
            angle1_player_aim_residual=FloatInterval.point(0.0),
            angle2_player_aim_coefficient=0.0,
            angle2_player_aim_residual=FloatInterval.point(0.0),
            tagged_callbacks=(callback,),
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=10,
            events=(event,),
            tagged_callbacks=(callback,),
            source_semantics_version="test-source-callback-v1",
        )
        without_callback = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=10,
            events=(replace(event, tagged_callbacks=()),),
            source_semantics_version="test-source-callback-v1",
        )

        self.assertNotEqual(projection.digest, without_callback.digest)
        self.assertEqual(projection.record()["tagged_callback_count"], 1)
        self.assertFalse(
            projection.current_pool_callback_composition_complete
        )
        conditioned = condition_future_hazard_projection_on_player_paths(
            projection,
            source_frame=103,
            horizon_frames=7,
            player_positions_by_step=tuple(
                ((192.0, 400.0),) for _ in range(8)
            ),
        )
        causal = conditioned.direct_fire_events[0]
        self.assertEqual(causal.activation_frames, (2,))
        self.assertEqual(len(causal.tagged_callbacks), 1)
        self.assertEqual(causal.tagged_callbacks[0].frame, 4)
        self.assertEqual(causal.tagged_callbacks[0].callback_index, 14)
        self.assertEqual(len(conditioned.tagged_callbacks), 1)
        self.assertEqual(conditioned.tagged_callbacks[0].frame, 4)

    def test_causal_path_recomputes_automatic_mode_aim(self) -> None:
        event = replace(
            _event(),
            activation_frames=(2,),
            mode=0,
            angle1=FloatInterval.point(0.0),
            angle2=FloatInterval.point(0.0),
            aim_angle=FloatInterval(-math.pi, math.pi),
            angle1_player_aim_coefficient=0.0,
            angle1_player_aim_residual=FloatInterval.point(0.0),
            angle2_player_aim_coefficient=0.0,
            angle2_player_aim_residual=FloatInterval.point(0.0),
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=10,
            events=(event,),
            source_semantics_version="test-source-auto-aim-v1",
        )
        paths = tuple((((200.0, 80.0),)) for _ in range(11))

        conditioned = condition_future_hazard_projection_on_player_paths(
            projection,
            source_frame=100,
            horizon_frames=10,
            player_positions_by_step=paths,
        )

        causal = conditioned.direct_fire_events[0]
        self.assertLess(causal.aim_angle.upper - causal.aim_angle.lower, 1e-3)
        wrapped_midpoint = (
            (causal.aim_angle.midpoint + math.pi) % (2.0 * math.pi)
            - math.pi
        )
        self.assertAlmostEqual(wrapped_midpoint, 0.0, places=5)
        self.assertLess(
            conditioned.trajectories[0].maximum_angle
            - conditioned.trajectories[0].minimum_angle,
            1e-3,
        )

    def test_causal_player_path_fails_closed_without_affine_metadata(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=10,
            events=(_event(),),
            source_semantics_version="test-source-v1",
        )
        paths = tuple((((200.0, 80.0),)) for _ in range(11))

        with self.assertRaisesRegex(ValueError, "lacks complete causal"):
            condition_future_hazard_projection_on_player_paths(
                projection,
                source_frame=100,
                horizon_frames=10,
                player_positions_by_step=paths,
            )


if __name__ == "__main__":
    unittest.main()
