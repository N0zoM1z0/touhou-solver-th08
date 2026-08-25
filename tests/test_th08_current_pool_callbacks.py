from __future__ import annotations

import math
import unittest

import numpy as np

from th08_future_birth_envelope import (
    FloatInterval,
    FutureTaggedBulletCallback,
)
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_live.current_pool_callbacks import (
    compose_current_pool_callbacks,
    join_projection_callbacks_to_current_pool,
)
from th08_live.local_hazards import _build_bullet_frames
from th08_live.models import Bullet, PackedBulletSnapshot
from touhou_control.trajectory import VelocityChange


def _callback(
    frame: int,
    index: int,
    *,
    mask: int = 0x100000,
    speed: FloatInterval | None = None,
    angle: FloatInterval | None = None,
) -> FutureTaggedBulletCallback:
    return FutureTaggedBulletCallback(
        source="test",
        frame=frame,
        callback_index=index,
        tag_mask=mask,
        callback_angle=(
            angle
            if index == 12
            else None
        ),
        callback_speed=speed or FloatInterval.point(4.0),
    )


def _bullet(**overrides: object) -> Bullet:
    values: dict[str, object] = {
        "x": 10.0,
        "y": 20.0,
        "vx": 2.0,
        "vy": 0.0,
        "half_width": 1.0,
        "half_height": 1.0,
        "slot": 7,
        "speed": 2.0,
        "angle": 0.0,
        "callback_phase_state": 1,
        "callback_aux_state": 0,
        "original_transform_flags": 0x100000,
        "native_state": 1,
        "native_state_timer_elapsed": 0,
        "bullet_type": 0,
    }
    values.update(overrides)
    return Bullet(**values)


def _packed(bullet: Bullet) -> PackedBulletSnapshot:
    return PackedBulletSnapshot(
        x=np.asarray([bullet.x], dtype=np.float32),
        y=np.asarray([bullet.y], dtype=np.float32),
        velocity_x=np.asarray([bullet.vx], dtype=np.float32),
        velocity_y=np.asarray([bullet.vy], dtype=np.float32),
        half_width=np.asarray([bullet.half_width], dtype=np.float32),
        half_height=np.asarray([bullet.half_height], dtype=np.float32),
        transform_flags=np.asarray(
            [bullet.transform_flags],
            dtype=np.uint32,
        ),
        slots=np.asarray([bullet.slot], dtype=np.int16),
        speed=np.asarray([bullet.speed], dtype=np.float32),
        angle=np.asarray([bullet.angle], dtype=np.float32),
        callback_phase=np.asarray(
            [bullet.callback_phase_state],
            dtype=np.uint8,
        ),
        callback_aux=np.asarray(
            [bullet.callback_aux_state],
            dtype=np.uint8,
        ),
        original_transform_flags=np.asarray(
            [bullet.original_transform_flags],
            dtype=np.uint32,
        ),
        native_state=np.asarray([bullet.native_state], dtype=np.uint16),
        native_state_timer_elapsed=np.asarray(
            [bullet.native_state_timer_elapsed],
            dtype=np.int32,
        ),
        bullet_type=np.asarray([bullet.bullet_type], dtype=np.int16),
    )


class Th08CurrentPoolCallbackTests(unittest.TestCase):
    def test_projection_join_binds_source_bullet_and_policy_clocks(self) -> None:
        callback = _callback(
            5,
            14,
            speed=FloatInterval.point(0.75),
        )
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(),
            tagged_callbacks=(callback,),
            source_semantics_version="test-source-v1",
        )
        join = join_projection_callbacks_to_current_pool(
            (_bullet(),),
            projection=projection,
            bullet_root_frame=102,
            policy_source_frame=104,
            policy_horizon_frames=10,
            time_scale=1.0,
        )
        self.assertTrue(join.complete, join.reason)
        self.assertTrue(join.matches_projection(projection))
        self.assertEqual(join.required_bullet_horizon_frames, 12)
        self.assertEqual(join.composition.source_offset, 2)
        composed = tuple(join.bullets)[0]
        self.assertEqual(composed.velocity_changes[0].frame, 3)
        self.assertEqual(join.record()["callback_count"], 1)

        other_projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(),
            tagged_callbacks=(callback,),
            source_semantics_version="test-source-v2",
        )
        self.assertFalse(join.matches_projection(other_projection))

    def test_projection_join_rejects_unproved_clock_boundaries(self) -> None:
        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=20,
            events=(),
            tagged_callbacks=(_callback(5, 14),),
            source_semantics_version="test-source-v1",
        )
        cases = (
            (
                dict(
                    bullet_root_frame=99,
                    policy_source_frame=104,
                    policy_horizon_frames=10,
                ),
                "predates future source",
            ),
            (
                dict(
                    bullet_root_frame=102,
                    policy_source_frame=101,
                    policy_horizon_frames=10,
                ),
                "policy source predates",
            ),
            (
                dict(
                    bullet_root_frame=102,
                    policy_source_frame=115,
                    policy_horizon_frames=10,
                ),
                "misses policy horizon",
            ),
        )
        for values, reason in cases:
            with self.subTest(reason=reason):
                join = join_projection_callbacks_to_current_pool(
                    (_bullet(),),
                    projection=projection,
                    time_scale=1.0,
                    **values,
                )
                self.assertFalse(join.complete)
                self.assertIn(reason, join.reason or "")

        uncertain = join_projection_callbacks_to_current_pool(
            (_bullet(),),
            projection=projection,
            bullet_root_frame=102,
            policy_source_frame=104,
            policy_horizon_frames=10,
            time_scale=1.0,
            bullet_frame_uncertainty=1,
        )
        self.assertFalse(uncertain.complete)
        self.assertIn("point-aligned", uncertain.reason or "")

    def test_rebases_and_composes_ordered_callback12_and_14(self) -> None:
        callbacks = (
            _callback(1, 14),
            _callback(3, 14, speed=FloatInterval.point(0.5)),
            _callback(3, 14, speed=FloatInterval.point(9.0)),
            _callback(
                5,
                12,
                speed=FloatInterval.point(3.0),
                angle=FloatInterval.point(math.pi / 2.0),
            ),
        )
        result = compose_current_pool_callbacks(
            (
                _bullet(
                    vx=4.0,
                    callback_phase_state=0,
                    callback_aux_state=1,
                ),
            ),
            callbacks=callbacks,
            time_scale=1.0,
            source_offset=1,
            horizon_frames=4,
        )
        self.assertTrue(result.complete, result.reason)
        self.assertEqual(result.callback_count, 3)
        self.assertEqual(result.affected_bullet_count, 1)
        bullet = tuple(result.bullets)[0]
        # Two same-frame callback-14 transitions are source-ordered and then
        # collapsed to their final phase-2 motion/collision state.
        self.assertEqual(
            tuple(change.frame for change in bullet.velocity_changes),
            (2, 4),
        )
        self.assertAlmostEqual(bullet.velocity_changes[0].velocity_x, 2.0)
        self.assertAlmostEqual(bullet.velocity_changes[0].velocity_y, 0.0)
        self.assertLess(abs(bullet.velocity_changes[1].velocity_x), 2.0e-7)
        self.assertAlmostEqual(bullet.velocity_changes[1].velocity_y, 3.0)
        self.assertEqual(
            tuple(
                change.collision_enabled
                for change in bullet.collision_state_changes
            ),
            (True, False),
        )

    def test_set_valued_operand_fails_only_when_pool_tag_matches(self) -> None:
        callback = _callback(
            2,
            14,
            speed=FloatInterval(1.0, 2.0),
        )
        matching = compose_current_pool_callbacks(
            (_bullet(),),
            callbacks=(callback,),
            time_scale=1.0,
            source_offset=0,
            horizon_frames=4,
        )
        self.assertFalse(matching.complete)
        self.assertIn("set-valued", matching.reason or "")

        nonmatching_bullet = _bullet(original_transform_flags=0x200000)
        nonmatching = compose_current_pool_callbacks(
            (nonmatching_bullet,),
            callbacks=(callback,),
            time_scale=1.0,
            source_offset=0,
            horizon_frames=4,
        )
        self.assertTrue(nonmatching.complete, nonmatching.reason)
        self.assertIs(nonmatching.bullets[0], nonmatching_bullet)

    def test_point_alignment_and_existing_schedule_fail_closed(self) -> None:
        callback = _callback(2, 14)
        uncertain = compose_current_pool_callbacks(
            (_bullet(),),
            callbacks=(callback,),
            time_scale=1.0,
            source_offset=0,
            horizon_frames=3,
            event_frame_uncertainty=1,
        )
        self.assertFalse(uncertain.complete)
        self.assertIn("point-aligned", uncertain.reason or "")

        scheduled = _bullet(
            velocity_changes=(VelocityChange(1, 1.0, 0.0),),
        )
        conflict = compose_current_pool_callbacks(
            (scheduled,),
            callbacks=(callback,),
            time_scale=1.0,
            source_offset=0,
            horizon_frames=3,
        )
        self.assertFalse(conflict.complete)
        self.assertIn("already has", conflict.reason or "")

    def test_packed_and_materialized_inputs_have_identical_schedules(self) -> None:
        bullet = _bullet()
        callbacks = (
            _callback(1, 14, speed=FloatInterval.point(0.25)),
            _callback(
                4,
                12,
                speed=FloatInterval.point(7.0),
                angle=FloatInterval.point(-1.0),
            ),
        )
        ordinary = compose_current_pool_callbacks(
            (bullet,),
            callbacks=callbacks,
            time_scale=1.0,
            source_offset=0,
            horizon_frames=4,
        )
        packed = compose_current_pool_callbacks(
            _packed(bullet),
            callbacks=callbacks,
            time_scale=1.0,
            source_offset=0,
            horizon_frames=4,
        )
        self.assertTrue(ordinary.complete, ordinary.reason)
        self.assertTrue(packed.complete, packed.reason)
        ordinary_bullet = tuple(ordinary.bullets)[0]
        packed_bullet = tuple(packed.bullets)[0]
        self.assertEqual(
            ordinary_bullet.velocity_changes,
            packed_bullet.velocity_changes,
        )
        self.assertEqual(
            ordinary_bullet.collision_state_changes,
            packed_bullet.collision_state_changes,
        )

    def test_local_projector_applies_callback_before_native_motion(self) -> None:
        callbacks = (
            _callback(1, 14, speed=FloatInterval.point(4.0)),
            _callback(2, 14, speed=FloatInterval.point(9.0)),
            _callback(
                3,
                12,
                speed=FloatInterval.point(6.0),
                angle=FloatInterval.point(math.pi),
            ),
        )
        result = compose_current_pool_callbacks(
            (_bullet(x=0.0, y=0.0),),
            callbacks=callbacks,
            time_scale=1.0,
            source_offset=0,
            horizon_frames=3,
        )
        self.assertTrue(result.complete, result.reason)
        frames = _build_bullet_frames(
            result.bullets,
            horizon=3,
            snapshot_lag=0,
        )
        self.assertAlmostEqual(float(frames[0][0][0]), 4.0)
        self.assertEqual(int(frames[0][6][0]), 1)
        self.assertAlmostEqual(float(frames[1][0][0]), 8.0)
        self.assertEqual(int(frames[1][6][0]), 1)
        self.assertAlmostEqual(float(frames[2][0][0]), 10.0)
        self.assertEqual(int(frames[2][6][0]), 0)

    def test_callback_precedes_divided_spawn_lifecycle_motion(self) -> None:
        result = compose_current_pool_callbacks(
            (
                _bullet(
                    x=0.0,
                    y=0.0,
                    native_state=2,
                    native_state_timer_elapsed=0,
                    bullet_type=0,
                ),
            ),
            callbacks=(
                _callback(1, 14, speed=FloatInterval.point(4.0)),
            ),
            time_scale=1.0,
            source_offset=0,
            horizon_frames=1,
        )
        self.assertTrue(result.complete, result.reason)
        frames = _build_bullet_frames(
            result.bullets,
            horizon=1,
            snapshot_lag=0,
        )
        # State 2 uses divisor 2, after the callback replaces velocity.
        self.assertAlmostEqual(float(frames[0][0][0]), 2.0)
        self.assertEqual(int(frames[0][5][0]), 2)
        self.assertEqual(int(frames[0][6][0]), 1)

    def test_full_native_pool_composes_without_partial_output(self) -> None:
        bullets = tuple(_bullet(slot=slot) for slot in range(1536))
        callbacks = tuple(
            _callback(
                frame,
                14,
                speed=FloatInterval.point(float(frame) / 8.0),
            )
            for frame in range(1, 17)
        )
        result = compose_current_pool_callbacks(
            bullets,
            callbacks=callbacks,
            time_scale=1.0,
            source_offset=0,
            horizon_frames=16,
        )
        self.assertTrue(result.complete, result.reason)
        self.assertEqual(result.callback_count, 16)
        self.assertEqual(result.affected_bullet_count, 1536)
        composed = tuple(result.bullets)
        self.assertEqual(len(composed), 1536)
        self.assertTrue(
            all(len(bullet.velocity_changes) == 16 for bullet in composed)
        )


if __name__ == "__main__":
    unittest.main()
