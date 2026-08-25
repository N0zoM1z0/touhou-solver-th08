#!/usr/bin/env python3
"""Scalar source-order gates for retained current-bullet transforms."""

from __future__ import annotations

import math
import unittest

from th08_bullet_transform_model import (
    BulletTransformProgramRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformRecord,
    TransformTimerRuntime,
    pack_transform_program,
)
from th08_current_transform_stepper import (
    CurrentBulletTransformState,
    CurrentTransformUnsupported,
    state_from_bullet,
    step_current_transform,
)
from th08_live.models import Bullet


def _record(
    index: int,
    kind: TransformKind,
    *,
    int_0: int = 0,
    int_1: int = 0,
    float_0: float = 0.0,
    float_1: float = 0.0,
    allow: bool = False,
) -> TransformRecord:
    return TransformRecord(
        index=index,
        kind=int(kind),
        allow_while_active=allow,
        int_0=int_0,
        int_1=int_1,
        float_0=float_0,
        float_1=float_1,
    )


def _state(
    records: tuple[TransformRecord, ...] = (),
    *,
    original_flags: int | None = None,
    active_flags: int = 0,
    cursor: int = 0,
    x: float = 192.0,
    y: float = 224.0,
    velocity_x: float = 0.0,
    velocity_y: float = 0.0,
    base_speed: float = 0.0,
    base_angle: float = 0.0,
    collision_half_width: float = 2.0,
    collision_half_height: float = 2.0,
    cull_half_width: float = 4.0,
    cull_half_height: float = 4.0,
    native_state: int = 1,
    cull_countdown: int = 100,
    offscreen_counter: int = 0,
    decelerate_timer: TransformTimerRuntime | None = None,
    stop: StopTransformRuntime | None = None,
    reflection: ReflectionTransformRuntime | None = None,
    barrier_timer: TransformTimerRuntime | None = None,
    wrap_timer: TransformTimerRuntime | None = None,
) -> CurrentBulletTransformState:
    flags = (
        original_flags
        if original_flags is not None
        else sum(int(record.kind) for record in records)
    )
    return CurrentBulletTransformState(
        x=x,
        y=y,
        velocity_x=velocity_x,
        velocity_y=velocity_y,
        collision_half_width=collision_half_width,
        collision_half_height=collision_half_height,
        cull_half_width=cull_half_width,
        cull_half_height=cull_half_height,
        base_speed=base_speed,
        base_angle=base_angle,
        bullet_type=0,
        native_state=native_state,
        active_flags=active_flags,
        runtime=BulletTransformProgramRuntime(
            program=pack_transform_program(records),
            original_flags=flags,
            queue_cursor=cursor,
            cull_suppression_countdown=cull_countdown,
            offscreen_counter=offscreen_counter,
            decelerate_timer=decelerate_timer,
            stop=stop,
            reflection=reflection,
            barrier_timer=barrier_timer,
            wrap_timer=wrap_timer,
        ),
    )


class CurrentTransformStepperTests(unittest.TestCase):
    def test_live_root_derives_visual_culling_geometry_from_template(self) -> None:
        runtime = BulletTransformProgramRuntime(
            program=pack_transform_program(()),
            original_flags=0,
            queue_cursor=0,
            cull_suppression_countdown=0,
            offscreen_counter=0,
        )
        bullet = Bullet(
            x=1.0,
            y=2.0,
            vx=3.0,
            vy=4.0,
            half_width=12.0,
            half_height=12.0,
            speed=5.0,
            angle=0.25,
            bullet_type=10,
            transform_program_runtime=runtime,
        )

        state = state_from_bullet(bullet)

        self.assertEqual(
            (
                state.collision_half_width,
                state.cull_half_width,
                state.cull_half_height,
            ),
            (12.0, 32.0, 32.0),
        )

    def test_queue_chains_immediate_records_then_activates_one_handler(
        self,
    ) -> None:
        records = (
            _record(
                0,
                TransformKind.SUPPRESS_OFFSCREEN_CULL,
                int_0=3,
            ),
            _record(1, TransformKind.PLAY_SOUND, int_0=7),
            _record(
                2,
                TransformKind.VECTOR_ACCELERATION,
                int_0=2,
                float_0=2.0,
                float_1=0.0,
            ),
            _record(
                3,
                TransformKind.ANGULAR_VELOCITY,
                int_0=2,
                float_0=0.25,
                float_1=0.5,
            ),
        )

        result = step_current_transform(
            _state(records, cull_countdown=0),
            player_x=192.0,
            player_y=400.0,
            ecl_time_scale=0.5,
        )

        self.assertEqual(result.runtime.queue_cursor, 3)
        self.assertEqual(
            result.active_flags,
            int(TransformKind.VECTOR_ACCELERATION),
        )
        # Setup stores an acceleration magnitude of scale*2 = 1, and the
        # same-frame handler adds it with scale once more.
        self.assertEqual(result.velocity_x, 0.5)
        self.assertEqual(result.velocity_y, 0.0)
        self.assertEqual(result.runtime.cull_suppression_countdown, 2)

    def test_wait_for_clear_delays_next_record_until_following_frame(self) -> None:
        records = (
            _record(
                0,
                TransformKind.DECELERATE_16F,
            ),
            _record(
                1,
                TransformKind.ANGULAR_VELOCITY,
                int_0=1,
            ),
        )
        state = _state(records, base_speed=1.0)
        for _ in range(18):
            state = step_current_transform(
                state,
                player_x=192.0,
                player_y=400.0,
            )

        self.assertEqual(state.active_flags, 0)
        self.assertEqual(state.runtime.queue_cursor, 1)
        state = step_current_transform(
            state,
            player_x=192.0,
            player_y=400.0,
        )
        self.assertEqual(
            state.active_flags,
            int(TransformKind.ANGULAR_VELOCITY),
        )
        self.assertEqual(state.runtime.queue_cursor, 2)

    def test_shared_stop_block_runs_turn_then_snap_in_source_order(self) -> None:
        active = int(
            TransformKind.STOP_TURN_REPEAT
            | TransformKind.STOP_SNAP_REPEAT
        )
        stop = StopTransformRuntime(
            timer=TransformTimerRuntime(-999, 0.0, 0),
            resume_speed=2.0,
            angle_operand=0.5,
            duration=0,
            repeat_limit=10,
            repeat_count=0,
        )

        result = step_current_transform(
            _state(
                active_flags=active,
                base_angle=1.0,
                stop=stop,
            ),
            player_x=192.0,
            player_y=400.0,
        )

        self.assertEqual(result.base_angle, 0.5)
        assert result.runtime.stop is not None
        self.assertEqual(result.runtime.stop.repeat_count, 2)
        self.assertEqual(result.runtime.stop.timer.current, 1)

    def test_horizontal_and_vertical_wrap_share_and_double_consume_timer(
        self,
    ) -> None:
        active = int(
            TransformKind.WRAP_HORIZONTAL | TransformKind.WRAP_VERTICAL
        )
        state = _state(
            active_flags=active,
            x=-1.0,
            y=-1.0,
            wrap_timer=TransformTimerRuntime(-999, 0.0, 1),
        )

        first = step_current_transform(
            state,
            player_x=192.0,
            player_y=400.0,
        )

        self.assertEqual((first.x, first.y), (383.0, 447.0))
        self.assertEqual(
            first.active_flags,
            int(TransformKind.WRAP_HORIZONTAL),
        )
        assert first.runtime.wrap_timer is not None
        self.assertEqual(first.runtime.wrap_timer.current, 0)
        second = step_current_transform(
            first,
            player_x=192.0,
            player_y=400.0,
        )
        self.assertEqual(second.active_flags, 0)
        self.assertIsNone(second.runtime.wrap_timer)

    def test_reflection_uses_visual_not_collision_extents(self) -> None:
        kind = int(TransformKind.REFLECT_ALL_EDGES)
        reflection = ReflectionTransformRuntime(2.0, 0, 4)
        inside = step_current_transform(
            _state(
                active_flags=kind,
                x=-20.0,
                collision_half_width=12.0,
                collision_half_height=12.0,
                cull_half_width=32.0,
                cull_half_height=32.0,
                base_speed=1.0,
                base_angle=0.0,
                reflection=reflection,
            ),
            player_x=192.0,
            player_y=400.0,
        )
        assert inside.runtime.reflection is not None
        self.assertEqual(inside.runtime.reflection.event_count, 0)

        outside = step_current_transform(
            _state(
                active_flags=kind,
                x=-33.0,
                collision_half_width=12.0,
                collision_half_height=12.0,
                cull_half_width=32.0,
                cull_half_height=32.0,
                base_speed=1.0,
                base_angle=0.0,
                reflection=reflection,
            ),
            player_x=192.0,
            player_y=400.0,
        )
        assert outside.runtime.reflection is not None
        self.assertEqual(outside.runtime.reflection.event_count, 1)
        self.assertAlmostEqual(abs(outside.base_angle), math.pi, places=6)

    def test_culling_and_fade_lifecycle_are_explicit(self) -> None:
        retired = step_current_transform(
            _state(x=-5.0, cull_countdown=0),
            player_x=192.0,
            player_y=400.0,
        )
        self.assertTrue(retired.retired)
        self.assertFalse(retired.lethal)

        fade = step_current_transform(
            _state(
                (_record(0, TransformKind.ENTER_FADE_STATE),),
                cull_countdown=2,
            ),
            player_x=192.0,
            player_y=400.0,
        )
        self.assertEqual(fade.native_state, 5)
        self.assertFalse(fade.lethal)

    def test_template_and_derived_birth_transitions_fail_closed(self) -> None:
        cases = (
            (
                TransformKind.REPLACE_BULLET_TEMPLATE,
                "template_replacement_requires_color_geometry_state",
            ),
            (
                TransformKind.EMIT_DERIVED_PATTERN,
                "derived_pattern_requires_child_birth_allocation",
            ),
        )
        for kind, reason in cases:
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(CurrentTransformUnsupported, reason):
                    step_current_transform(
                        _state((_record(0, kind),)),
                        player_x=192.0,
                        player_y=400.0,
                    )

    def test_active_handler_without_retained_block_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "active transform/block"):
            step_current_transform(
                _state(active_flags=int(TransformKind.DECELERATE_16F)),
                player_x=192.0,
                player_y=400.0,
            )


if __name__ == "__main__":
    unittest.main()
