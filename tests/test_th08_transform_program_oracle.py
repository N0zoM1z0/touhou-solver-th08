#!/usr/bin/env python3
"""Long differential gates for the source-order bullet transform oracle."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
import random
import shutil
import tempfile
import unittest

from build_th08_source_oracle import build
from th08_bullet_transform_model import (
    AngularVelocityRuntime,
    BulletTransformProgramRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformRecord,
    TransformTimerRuntime,
    VectorAccelerationRuntime,
    pack_transform_program,
)
from th08_current_transform_stepper import (
    CurrentBulletTransformState,
    CurrentTransformUnsupported,
    step_current_transform,
)
from th08_semantics.native_oracle import NativeSourceOracle
from th08_semantics.source_primitives import f32


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
    active_flags: int = 0,
    original_flags: int | None = None,
    x: float = 192.0,
    y: float = 224.0,
    velocity_x: float = 0.0,
    velocity_y: float = 0.0,
    base_speed: float = 0.0,
    base_angle: float = 0.0,
    cull_countdown: int = 1024,
    decelerate_timer: TransformTimerRuntime | None = None,
    vector: VectorAccelerationRuntime | None = None,
    angular: AngularVelocityRuntime | None = None,
    stop: StopTransformRuntime | None = None,
    reflection: ReflectionTransformRuntime | None = None,
    barrier: TransformTimerRuntime | None = None,
    wrap: TransformTimerRuntime | None = None,
) -> CurrentBulletTransformState:
    flags = 0
    for record in records:
        flags |= int(record.kind)
    if original_flags is not None:
        flags = original_flags
    return CurrentBulletTransformState(
        x=f32(x),
        y=f32(y),
        velocity_x=f32(velocity_x),
        velocity_y=f32(velocity_y),
        collision_half_width=2.0,
        collision_half_height=2.0,
        cull_half_width=4.0,
        cull_half_height=4.0,
        base_speed=f32(base_speed),
        base_angle=f32(base_angle),
        bullet_type=2,
        native_state=1,
        active_flags=active_flags,
        runtime=BulletTransformProgramRuntime(
            program=pack_transform_program(records),
            original_flags=flags,
            queue_cursor=0,
            cull_suppression_countdown=cull_countdown,
            offscreen_counter=0,
            decelerate_timer=decelerate_timer,
            vector_acceleration=vector,
            angular_velocity=angular,
            stop=stop,
            reflection=reflection,
            barrier_timer=barrier,
            wrap_timer=wrap,
        ),
    )


class TransformProgramOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("cc") is None:
            raise unittest.SkipTest("C compiler is unavailable")
        cls._temporary = tempfile.TemporaryDirectory()
        output = Path(cls._temporary.name) / "th08-source-oracle.so"
        build(output)
        cls.oracle = NativeSourceOracle.load(output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def assertSourceValueEqual(
        self,
        left: object,
        right: object,
        *,
        path: str = "state",
    ) -> None:
        if dataclasses.is_dataclass(left):
            self.assertEqual(type(left), type(right), path)
            for field in dataclasses.fields(left):
                self.assertSourceValueEqual(
                    getattr(left, field.name),
                    getattr(right, field.name),
                    path=f"{path}.{field.name}",
                )
            return
        if isinstance(left, float):
            assert isinstance(right, float)
            tolerance = 2.0e-5 + 2.0e-6 * max(abs(left), abs(right))
            self.assertLessEqual(abs(left - right), tolerance, path)
            return
        self.assertEqual(left, right, path)

    def _run_independent_differential(
        self,
        state: CurrentBulletTransformState,
        *,
        frames: int,
        player_x: float = 171.25,
        player_y: float = 389.5,
        ecl_time_scale: float = 1.0,
        timer_scale: float = 1.0,
        movement_frozen: bool = False,
        timer_force_tick: bool = False,
    ) -> tuple[CurrentBulletTransformState, CurrentBulletTransformState]:
        python_state = state
        native_state = state
        for frame in range(frames):
            if python_state.retired or python_state.native_state != 1:
                break
            python_state = step_current_transform(
                python_state,
                player_x=player_x,
                player_y=player_y,
                ecl_time_scale=ecl_time_scale,
                timer_scale=timer_scale,
                movement_frozen=movement_frozen,
                timer_force_tick=timer_force_tick,
            )
            native_state = self.oracle.transform_program_frame(
                native_state,
                player_x=player_x,
                player_y=player_y,
                ecl_time_scale=ecl_time_scale,
                timer_scale=timer_scale,
                movement_frozen=movement_frozen,
                timer_force_tick=timer_force_tick,
            )
            self.assertSourceValueEqual(
                python_state,
                native_state,
                path=f"frame[{frame}]",
            )
        return python_state, native_state

    def test_long_queue_matches_independent_c_frame_by_frame(self) -> None:
        records = (
            _record(
                0,
                TransformKind.SUPPRESS_OFFSCREEN_CULL,
                int_0=512,
            ),
            _record(1, TransformKind.DECELERATE_16F),
            _record(
                2,
                TransformKind.VECTOR_ACCELERATION,
                int_0=13,
                float_0=0.075,
                float_1=0.4,
            ),
            _record(
                3,
                TransformKind.ANGULAR_VELOCITY,
                int_0=19,
                float_0=0.015,
                float_1=-0.0475,
            ),
            _record(
                4,
                TransformKind.TIMED_QUEUE_BARRIER,
                int_0=8,
            ),
            _record(
                5,
                TransformKind.STOP_TURN_REPEAT,
                int_0=6,
                int_1=3,
                float_0=0.21,
                float_1=1.6,
            ),
            _record(6, TransformKind.PLAY_SOUND, int_0=7),
            _record(7, TransformKind.ENTER_FADE_STATE),
        )
        state = _state(
            records,
            velocity_x=1.1 * math.cos(0.25),
            velocity_y=1.1 * math.sin(0.25),
            base_speed=1.1,
            base_angle=0.25,
        )

        python_state, native_state = self._run_independent_differential(
            state,
            frames=160,
        )

        self.assertEqual(python_state.native_state, 5)
        self.assertEqual(native_state.native_state, 5)
        self.assertEqual(python_state.runtime.queue_cursor, 8)

    def test_long_reflection_history_matches_c(self) -> None:
        kind = int(TransformKind.REFLECT_ALL_EDGES)
        state = _state(
            active_flags=kind,
            x=382.0,
            y=100.0,
            velocity_x=8.0,
            base_speed=8.0,
            base_angle=0.0,
            reflection=ReflectionTransformRuntime(
                restored_speed=8.0,
                event_count=0,
                event_limit=6,
            ),
            cull_countdown=2048,
        )

        python_state, _ = self._run_independent_differential(
            state,
            frames=400,
        )

        self.assertEqual(python_state.active_flags, 0)
        self.assertIsNone(python_state.runtime.reflection)

    def test_fractional_timers_and_shared_blocks_match_c(self) -> None:
        active = int(
            TransformKind.STOP_TURN_REPEAT
            | TransformKind.STOP_SNAP_REPEAT
            | TransformKind.WRAP_HORIZONTAL
            | TransformKind.WRAP_VERTICAL
            | TransformKind.TIMED_QUEUE_BARRIER
        )
        state = _state(
            active_flags=active,
            x=-2.0,
            y=-3.0,
            base_speed=2.25,
            base_angle=-0.6,
            stop=StopTransformRuntime(
                timer=TransformTimerRuntime(-999, 0.0, 0),
                resume_speed=1.75,
                angle_operand=0.35,
                duration=3,
                repeat_limit=4,
                repeat_count=0,
            ),
            barrier=TransformTimerRuntime(-999, 0.0, 9),
            wrap=TransformTimerRuntime(-999, 0.0, 11),
        )

        self._run_independent_differential(
            state,
            frames=80,
            ecl_time_scale=0.75,
            timer_scale=0.625,
            timer_force_tick=True,
        )

    def test_binary32_timer_threshold_takes_the_source_slow_path(self) -> None:
        kind = int(TransformKind.TIMED_QUEUE_BARRIER)
        state = _state(
            active_flags=kind,
            barrier=TransformTimerRuntime(-999, 0.0, 2),
        )

        python_state, native_state = self._run_independent_differential(
            state,
            frames=1,
            timer_scale=f32(0.99),
        )

        expected = TransformTimerRuntime(2, f32(0.01), 1)
        self.assertSourceValueEqual(
            python_state.runtime.barrier_timer,
            expected,
        )
        self.assertSourceValueEqual(
            native_state.runtime.barrier_timer,
            expected,
        )

    def test_native_batch_matches_repeated_native_frames(self) -> None:
        records = (
            _record(
                0,
                TransformKind.VECTOR_ACCELERATION,
                int_0=20,
                float_0=0.04,
                float_1=-991.0,
            ),
        )
        states = tuple(
            _state(
                records,
                x=40.0 + index * 2.0,
                y=80.0 + index,
                base_speed=0.5 + index / 128.0,
                base_angle=-1.0 + index / 64.0,
            )
            for index in range(128)
        )

        batch = self.oracle.transform_program_batch(
            states,
            player_x=192.0,
            player_y=400.0,
            ecl_time_scale=0.8,
            timer_scale=0.8,
        )
        scalar = tuple(
            self.oracle.transform_program_frame(
                state,
                player_x=192.0,
                player_y=400.0,
                ecl_time_scale=0.8,
                timer_scale=0.8,
            )
            for state in states
        )

        self.assertSourceValueEqual(batch, scalar)
        self.assertEqual(
            self.oracle.transform_program_batch(
                (),
                player_x=192.0,
                player_y=400.0,
            ),
            (),
        )

    def test_deterministic_mixed_program_corpus_matches_c(self) -> None:
        rng = random.Random(0x42FFC0)
        kinds = (
            TransformKind.DECELERATE_16F,
            TransformKind.VECTOR_ACCELERATION,
            TransformKind.ANGULAR_VELOCITY,
            TransformKind.STOP_TURN_REPEAT,
            TransformKind.STOP_REAIM_REPEAT,
            TransformKind.STOP_SNAP_REPEAT,
            TransformKind.REFLECT_ALL_EDGES,
            TransformKind.REFLECT_SIDES_AND_TOP,
            TransformKind.TIMED_QUEUE_BARRIER,
            TransformKind.WRAP_HORIZONTAL,
            TransformKind.WRAP_VERTICAL,
            TransformKind.PLAY_SOUND,
            TransformKind.ENTER_FADE_STATE,
        )
        for case_index in range(48):
            records = [
                _record(
                    0,
                    TransformKind.SUPPRESS_OFFSCREEN_CULL,
                    int_0=1024,
                )
            ]
            for record_index in range(1, 9):
                kind = rng.choice(kinds)
                float_0 = rng.uniform(-0.15, 0.15)
                float_1 = rng.uniform(-1.0, 1.0)
                if kind in (
                    TransformKind.REFLECT_ALL_EDGES,
                    TransformKind.REFLECT_SIDES_AND_TOP,
                ):
                    float_0 = rng.choice((-1.0, rng.uniform(0.4, 3.0)))
                if kind in (
                    TransformKind.VECTOR_ACCELERATION,
                    TransformKind.STOP_TURN_REPEAT,
                    TransformKind.STOP_REAIM_REPEAT,
                    TransformKind.STOP_SNAP_REPEAT,
                ) and rng.randrange(4) == 0:
                    float_1 = -1000.0
                records.append(
                    _record(
                        record_index,
                        kind,
                        int_0=rng.randrange(0, 13),
                        int_1=rng.randrange(1, 5),
                        float_0=float_0,
                        float_1=float_1,
                        allow=bool(rng.randrange(2)),
                    )
                )
            angle = rng.uniform(-math.pi, math.pi)
            speed = rng.uniform(0.25, 2.5)
            state = _state(
                tuple(records),
                x=rng.uniform(16.0, 368.0),
                y=rng.uniform(16.0, 432.0),
                velocity_x=math.cos(angle) * speed,
                velocity_y=math.sin(angle) * speed,
                base_speed=speed,
                base_angle=angle,
            )
            with self.subTest(case=case_index):
                self._run_independent_differential(
                    state,
                    frames=96,
                    player_x=rng.uniform(8.0, 376.0),
                    player_y=rng.uniform(8.0, 440.0),
                    ecl_time_scale=rng.choice((0.5, 0.75, 1.0)),
                    timer_scale=rng.choice((0.5, f32(0.99), 1.0)),
                )

    def test_unsupported_births_match_typed_scalar_boundary(self) -> None:
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
            state = _state((_record(0, kind),))
            for step in (
                lambda: step_current_transform(
                    state,
                    player_x=192.0,
                    player_y=400.0,
                ),
                lambda: self.oracle.transform_program_frame(
                    state,
                    player_x=192.0,
                    player_y=400.0,
                ),
            ):
                with self.subTest(kind=kind, step=step):
                    with self.assertRaisesRegex(
                        CurrentTransformUnsupported,
                        reason,
                    ):
                        step()

    def test_partial_native_batch_is_poisoned_after_unsupported_birth(
        self,
    ) -> None:
        valid = _state()
        unsupported = _state(
            (_record(0, TransformKind.EMIT_DERIVED_PATTERN),)
        )
        native = self.oracle.prepare_transform_program_batch(
            (valid, unsupported)
        )

        with self.assertRaises(CurrentTransformUnsupported):
            self.oracle.advance_transform_program_batch(
                native,
                player_x=192.0,
                player_y=400.0,
            )

        self.assertTrue(native.poisoned)
        with self.assertRaisesRegex(ValueError, "batch is poisoned"):
            self.oracle.decode_transform_program_batch(native)
        with self.assertRaisesRegex(ValueError, "batch is poisoned"):
            self.oracle.advance_transform_program_batch(
                native,
                player_x=192.0,
                player_y=400.0,
            )

    def test_fade_is_a_stable_nonlethal_transform_batch_terminal(self) -> None:
        state = _state(
            (_record(0, TransformKind.ENTER_FADE_STATE),),
        )
        native = self.oracle.prepare_transform_program_batch((state,))

        self.oracle.advance_transform_program_batch(
            native,
            player_x=192.0,
            player_y=400.0,
        )
        faded = self.oracle.decode_transform_program_batch(native)[0]
        self.assertEqual(faded.native_state, 5)
        self.assertFalse(faded.lethal)

        self.oracle.advance_transform_program_batch(
            native,
            player_x=192.0,
            player_y=400.0,
        )
        stable = self.oracle.decode_transform_program_batch(native)[0]
        self.assertSourceValueEqual(stable, faded)
        self.assertSourceValueEqual(
            step_current_transform(
                faded,
                player_x=192.0,
                player_y=400.0,
            ),
            faded,
        )


if __name__ == "__main__":
    unittest.main()
