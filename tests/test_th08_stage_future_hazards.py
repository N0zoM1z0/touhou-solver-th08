from __future__ import annotations

import math
import unittest
from dataclasses import replace

import th08_live_dodge_agent as live
from th08_bullet_template_contract import bullet_template_profile
from th08_future_birth_envelope import FloatInterval, FutureDirectFire
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_semantics.future_hazards import (
    build_stage_future_hazard_projection,
    join_stage_future_hazards,
)
from th08_semantics.stage import (
    BulletEmitter,
    Callback14Event,
    LaserSpawnEvent,
    StagePhase,
    StageProgram,
    StageRuntime,
    TRANSFORM_VECTOR_ACCELERATION,
    TransformSpec,
)


def _program() -> StageProgram:
    template = bullet_template_profile(2)
    emitter = BulletEmitter(
        emitter_id="future-root-emitter",
        start_frame=0,
        end_frame=0,
        interval=1,
        origin_x=192.0,
        origin_y=96.0,
        origin_velocity_x=0.0,
        origin_velocity_y=0.0,
        origin_wave_x=0.0,
        origin_wave_y=0.0,
        origin_wave_step=0.0,
        mode=0,
        count1=3,
        count2=1,
        speed1=2.0,
        speed2=2.0,
        angle=0.0,
        angle_step=0.1,
        angle_per_emission=0.0,
        tag_flags=0x100000,
        half_width=template.half_width,
        half_height=template.half_height,
        cull_half_width=template.cull_half_width,
        cull_half_height=template.cull_half_height,
        bullet_type=2,
    )
    return StageProgram(
        seed=0x8414,
        profile="future-join-test",
        frame_count=8,
        gameplay_rng_seed=0x1234,
        phases=(
            StagePhase(
                name="complete-resolved-phase",
                start_frame=0,
                end_frame=7,
                clear_at_start=True,
                emitters=(emitter,),
                callbacks=(
                    Callback14Event(
                        frame=2,
                        tag_mask=0x100000,
                        speed=3.0,
                    ),
                ),
                lasers=(
                    LaserSpawnEvent(
                        frame=1,
                        origin_x=80.0,
                        origin_y=80.0,
                        angle=0.6,
                        speed=4.0,
                        tail=0.0,
                        head=32.0,
                        maximum_length=300.0,
                        width=18.0,
                        warmup_frames=0,
                        active_frames=5,
                        fade_frames=2,
                        collision_enable_frame=0,
                        collision_disable_frame=1,
                    ),
                ),
            ),
        ),
    )


class StageFutureHazardTests(unittest.TestCase):
    def test_normal_local_beam_consumes_request_future_geometry(self) -> None:
        event = FutureDirectFire(
            source="local-request-future",
            activation_frames=(1,),
            bullet_type=2,
            origin_x=FloatInterval.point(180.0),
            origin_y=FloatInterval.point(400.0),
            mode=1,
            count1=1,
            count2=1,
            speed1=FloatInterval.point(4.0),
            speed2=FloatInterval.point(4.0),
            angle1=FloatInterval.point(0.0),
            angle2=FloatInterval.point(0.0),
            aim_angle=FloatInterval.point(0.0),
            half_width=2.0,
            half_height=2.0,
            original_flags=0,
            transform_program_zero=True,
        )
        projection = complete_future_hazard_projection(
            root_frame=0,
            horizon_frames=6,
            events=(event,),
            source_semantics_version="local-request-test-v1",
        )
        common = {
            "player_x": 192.0,
            "player_y": 400.0,
            "bullets": (),
            "lasers": (),
            "previous_direction": 0,
            "previous_focus": True,
            "can_bomb": False,
            "control_delay_frames": 0,
            "action_hold_frames": 2,
            "horizon": 4,
            "threat_horizon": 4,
            "beam_width": 24,
        }

        blind = live.choose_action(**common)
        future = live.choose_action(
            **common,
            future_hazard_projection=projection,
        )

        self.assertEqual(blind.action, "stay")
        self.assertNotEqual(future.action, "stay")
        self.assertEqual(future.local_collisions, 0)
        self.assertGreater(future.min_clearance, 0.0)

    def test_resolved_birth_callback_and_laser_share_one_root_clock(self) -> None:
        projection = build_stage_future_hazard_projection(
            _program(),
            root_frame=0,
            root_player_x=192.0,
            root_player_y=400.0,
            horizon_frames=6,
        )

        self.assertTrue(projection.source_closure_complete)
        self.assertEqual(len(projection.direct_fire_events), 1)
        event = projection.direct_fire_events[0]
        self.assertEqual(event.activation_frames, (1,))
        self.assertEqual([value.frame for value in event.tagged_callbacks], [3])
        self.assertEqual([value.frame for value in projection.tagged_callbacks], [3])
        self.assertEqual(len(projection.aabb_trajectories), 1)
        self.assertIsNotNone(projection.aabb_samples(2)[0])

    def test_automatic_aim_uses_reachable_arc_not_full_circle(self) -> None:
        projection = build_stage_future_hazard_projection(
            _program(),
            root_frame=0,
            root_player_x=192.0,
            root_player_y=400.0,
            horizon_frames=2,
        )
        aim = projection.direct_fire_events[0].aim_angle

        self.assertLess(aim.upper - aim.lower, 0.1)
        actual = math.atan2(400.0 - 96.0, 192.0 - 192.0)
        self.assertLessEqual(aim.lower, actual)
        self.assertGreaterEqual(aim.upper, actual)

    def test_current_pool_callback_is_composed_then_marked_consumed(self) -> None:
        program = _program()
        runtime = StageRuntime(program)
        runtime.step(player_x=192.0, player_y=400.0)
        bullets, _ = runtime.live_snapshot()

        joined = join_stage_future_hazards(
            program,
            root_frame=runtime.frame,
            root_player_x=192.0,
            root_player_y=400.0,
            bullets=bullets,
            horizon_frames=4,
        )

        self.assertTrue(joined.complete, joined.reason)
        self.assertIsNotNone(joined.callback_join)
        self.assertEqual(joined.tagged_callback_count, 1)
        assert joined.projection is not None
        self.assertTrue(
            joined.projection.current_pool_callback_composition_complete
        )
        self.assertEqual(joined.projection.tagged_callbacks, ())
        self.assertTrue(
            all(bullet.velocity_changes for bullet in joined.bullets)
        )
        self.assertEqual(
            {change.frame for bullet in joined.bullets for change in bullet.velocity_changes},
            {2},
        )

    def test_consumed_projection_retains_future_birth_callback_effect(self) -> None:
        joined = join_stage_future_hazards(
            _program(),
            root_frame=0,
            root_player_x=192.0,
            root_player_y=400.0,
            bullets=(),
            horizon_frames=6,
        )

        self.assertTrue(joined.complete, joined.reason)
        assert joined.projection is not None
        self.assertEqual(joined.projection.tagged_callbacks, ())
        self.assertEqual(
            [
                callback.frame
                for event in joined.projection.direct_fire_events
                for callback in event.tagged_callbacks
            ],
            [3],
        )

    def test_same_frame_callback_precedes_and_does_not_mutate_birth(self) -> None:
        base = _program()
        phase = base.phases[0]
        program = replace(
            base,
            phases=(
                replace(
                    phase,
                    callbacks=(replace(phase.callbacks[0], frame=0),),
                ),
            ),
        )

        projection = build_stage_future_hazard_projection(
            program,
            root_frame=0,
            root_player_x=192.0,
            root_player_y=400.0,
            horizon_frames=3,
        )

        self.assertEqual([value.frame for value in projection.tagged_callbacks], [1])
        self.assertEqual(projection.direct_fire_events[0].tagged_callbacks, ())

    def test_join_reports_unresolved_emitter_instead_of_crashing(self) -> None:
        base = _program()
        phase = base.phases[0]
        unresolved = replace(phase.emitters[0], bullet_type=None)
        program = replace(
            base,
            phases=(replace(phase, emitters=(unresolved,)),),
        )

        joined = join_stage_future_hazards(
            program,
            root_frame=0,
            root_player_x=192.0,
            root_player_y=400.0,
            bullets=(),
            horizon_frames=3,
        )

        self.assertFalse(joined.complete)
        self.assertIsNone(joined.projection)
        self.assertIn("source-resolved bullet type", joined.reason or "")

    def test_callback_over_active_transform_uses_bounded_pool_fallback(self) -> None:
        base = _program()
        phase = base.phases[0]
        transformed = replace(
            phase.emitters[0],
            transforms=(
                TransformSpec(
                    kind=TRANSFORM_VECTOR_ACCELERATION,
                    duration=60,
                    float_0=0.03,
                    float_1=0.5,
                ),
            ),
        )
        program = replace(
            base,
            phases=(replace(phase, emitters=(transformed,)),),
        )
        runtime = StageRuntime(program)
        runtime.step(player_x=192.0, player_y=400.0)
        bullets, _ = runtime.live_snapshot()

        joined = join_stage_future_hazards(
            program,
            root_frame=runtime.frame,
            root_player_x=192.0,
            root_player_y=400.0,
            bullets=bullets,
            horizon_frames=4,
        )

        self.assertTrue(joined.complete, joined.reason)
        self.assertEqual(joined.callback_transform_fallback_count, 3)
        self.assertEqual(joined.bullets, ())
        assert joined.projection is not None
        self.assertGreaterEqual(len(joined.projection.aabb_trajectories), 3)
        root_samples = joined.projection.aabb_samples(0)
        self.assertEqual(len(root_samples), 3)
        self.assertEqual(
            {(sample.x, sample.y) for sample in root_samples},
            {(bullet.x, bullet.y) for bullet in bullets},
        )


if __name__ == "__main__":
    unittest.main()
