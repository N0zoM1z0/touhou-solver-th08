#!/usr/bin/env python3
"""Regression tests for CE-0084 live bullet-transform observation."""

from __future__ import annotations

import ctypes
import random
import struct
import unittest

import numpy as np

from numeric_model import binary32_store
from th08_bullet_transform_model import (
    BulletTransformRuntime,
    TransformKind,
    TransformRecord,
    parse_next_transform_record,
    parse_transform_record,
)
from th08_corridor_adapter import lower_bullets
from th08_ecl_runtime import EclVmSnapshot, TaggedVelocityToggle
from th08_live.bullet_decode import BULLET_STATE_TIMER_ELAPSED_OFFSET
from th08_live_dodge_agent import (
    BULLET_ANGLE_OFFSET,
    BULLET_CALLBACK_AUX_STATE_OFFSET,
    BULLET_CALLBACK_PHASE_STATE_OFFSET,
    BULLET_GEOMETRY_OFFSET,
    BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
    BULLET_POOL_SIZE,
    BULLET_POSITION_OFFSET,
    BULLET_SPEED_OFFSET,
    BULLET_STATE_OFFSET,
    BULLET_STOP_ANGLE_OPERAND_OFFSET,
    BULLET_STOP_DURATION_OFFSET,
    BULLET_STOP_REPEAT_COUNT_OFFSET,
    BULLET_STOP_REPEAT_LIMIT_OFFSET,
    BULLET_STOP_RESUME_SPEED_OFFSET,
    BULLET_STOP_TIMER_ELAPSED_OFFSET,
    BULLET_STOP_TIMER_FRACTION_OFFSET,
    BULLET_STRIDE,
    BULLET_TRANSFORM_FLAGS_OFFSET,
    BULLET_TRANSFORM_PROGRAM_OFFSET,
    BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET,
    BULLET_VELOCITY_OFFSET,
    Bullet,
    PackedBulletSnapshot,
    _build_bullet_frames,
    attach_tagged_velocity_toggles,
    decode_bullets,
    decode_live_planning_bullets,
    decode_packed_bullets,
    serialize_bullet_trace,
)
from th08_live.models import BULLET_LIFECYCLE_TRACE_SCHEMA
from th08_trace_replay import bullet_from_trace
from touhou_control.trajectory import VelocityChange


def _record(
    *,
    index: int = 0,
    kind: int = TransformKind.STOP_REAIM_REPEAT,
) -> TransformRecord:
    return TransformRecord(
        index=index,
        kind=kind,
        allow_while_active=True,
        int_0=30,
        int_1=4,
        float_0=0.25,
        float_1=2.5,
    )


class BulletRuntimeDecoderTests(unittest.TestCase):
    def test_native_packed_decoder_matches_python_object_oracle(
        self,
    ) -> None:
        generator = random.Random(0xB017E7)
        densities = (0, 1, 7, 64, 511, 512, 800, 1536)
        for case in range(48):
            density = (
                densities[case]
                if case < len(densities)
                else generator.randrange(BULLET_POOL_SIZE + 1)
            )
            blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
            slots = generator.sample(range(BULLET_POOL_SIZE), density)
            for active_index, slot in enumerate(slots):
                base = slot * BULLET_STRIDE
                struct.pack_into(
                    "<H",
                    blob,
                    base + BULLET_STATE_OFFSET,
                    1 + active_index % 3,
                )
                width = generator.uniform(-96.0, 96.0)
                height = generator.uniform(-96.0, 96.0)
                x = generator.uniform(-128.0, 512.0)
                y = generator.uniform(-128.0, 640.0)
                vx = generator.uniform(-16.0, 16.0)
                vy = generator.uniform(-16.0, 16.0)
                if active_index == density - 1 and case % 5 == 0:
                    x = float("nan")
                struct.pack_into(
                    "<ff",
                    blob,
                    base + BULLET_GEOMETRY_OFFSET,
                    width,
                    height,
                )
                struct.pack_into(
                    "<ff",
                    blob,
                    base + BULLET_POSITION_OFFSET,
                    x,
                    y,
                )
                struct.pack_into(
                    "<ff",
                    blob,
                    base + BULLET_VELOCITY_OFFSET,
                    vx,
                    vy,
                )
                struct.pack_into(
                    "<f",
                    blob,
                    base + BULLET_SPEED_OFFSET,
                    (
                        float("nan")
                        if active_index % 17 == 0
                        else generator.uniform(0.0, 16.0)
                    ),
                )
                struct.pack_into(
                    "<f",
                    blob,
                    base + BULLET_ANGLE_OFFSET,
                    (
                        float("inf")
                        if active_index % 19 == 0
                        else generator.uniform(-4.0, 4.0)
                    ),
                )
                struct.pack_into(
                    "<I",
                    blob,
                    base + BULLET_TRANSFORM_FLAGS_OFFSET,
                    generator.getrandbits(32),
                )
                struct.pack_into(
                    "<I",
                    blob,
                    base + BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
                    generator.getrandbits(32),
                )
                struct.pack_into(
                    "<h",
                    blob,
                    base + BULLET_CALLBACK_PHASE_STATE_OFFSET,
                    generator.randrange(-32768, 32768),
                )
                blob[base + BULLET_CALLBACK_AUX_STATE_OFFSET] = (
                    generator.randrange(256)
                )
            expected = decode_bullets(
                blob,
                retain_transform_runtime=False,
            )
            packed = decode_packed_bullets(blob)
            self.assertIsInstance(packed, PackedBulletSnapshot)
            self.assertEqual(
                tuple(packed),
                expected,
                f"native/Python mismatch in randomized case {case}",
            )
            self.assertEqual(
                tuple(
                    decode_live_planning_bullets(
                        blob,
                        backend="native",
                    )
                ),
                expected,
                f"live hybrid mismatch in randomized case {case}",
            )

    def test_native_packed_projection_matches_python_object_projection(
        self,
    ) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        for slot in range(801):
            base = slot * BULLET_STRIDE
            struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 1)
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_GEOMETRY_OFFSET,
                -2.0 - slot % 13,
                4.0 + slot % 17,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_POSITION_OFFSET,
                slot * 0.25,
                448.0 - slot * 0.125,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_VELOCITY_OFFSET,
                slot % 7 - 3.0,
                slot % 11 - 5.0,
            )
            struct.pack_into(
                "<I",
                blob,
                base + BULLET_TRANSFORM_FLAGS_OFFSET,
                slot % 3,
            )
        object_snapshot = decode_bullets(
            blob,
            retain_transform_runtime=False,
        )
        packed_snapshot = decode_packed_bullets(blob)
        object_frames = _build_bullet_frames(
            object_snapshot,
            horizon=17,
            snapshot_lag=3,
        )
        packed_frames = _build_bullet_frames(
            packed_snapshot,
            horizon=17,
            snapshot_lag=3,
        )
        for object_frame, packed_frame in zip(
            object_frames,
            packed_frames,
        ):
            for object_field, packed_field in zip(
                object_frame,
                packed_frame,
            ):
                np.testing.assert_array_equal(
                    packed_field,
                    object_field,
                )

    def test_planning_decoder_accepts_persistent_ctypes_pool_buffer(self) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        struct.pack_into("<H", blob, BULLET_STATE_OFFSET, 1)
        struct.pack_into("<ff", blob, BULLET_GEOMETRY_OFFSET, 3.0, 5.0)
        struct.pack_into("<ff", blob, BULLET_POSITION_OFFSET, 40.0, 70.0)
        struct.pack_into("<ff", blob, BULLET_VELOCITY_OFFSET, 1.0, -2.0)
        buffer = ctypes.create_string_buffer(len(blob))
        ctypes.memmove(buffer, bytes(blob), len(blob))

        from_bytes = decode_bullets(
            bytes(blob),
            retain_transform_runtime=False,
        )
        from_persistent_buffer = decode_bullets(
            memoryview(buffer).cast("B"),
            retain_transform_runtime=False,
        )
        packed_from_persistent_buffer = decode_packed_bullets(
            memoryview(buffer).cast("B")
        )

        self.assertEqual(from_persistent_buffer, from_bytes)
        self.assertEqual(tuple(packed_from_persistent_buffer), from_bytes)

    def test_native_bullet_dimensions_are_not_clamped_by_visual_size(
        self,
    ) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        for slot, dimensions in enumerate(((0.5, 0.25), (96.0, 80.0))):
            base = slot * BULLET_STRIDE
            struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 1)
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_GEOMETRY_OFFSET,
                *dimensions,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_POSITION_OFFSET,
                100.0 + slot,
                200.0,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_VELOCITY_OFFSET,
                0.0,
                0.0,
            )
        expected = ((0.25, 0.125), (48.0, 40.0))
        for retain_runtime in (False, True):
            bullets = decode_bullets(
                bytes(blob),
                retain_transform_runtime=retain_runtime,
            )
            self.assertEqual(
                tuple(
                    (bullet.half_width, bullet.half_height)
                    for bullet in bullets
                ),
                expected,
            )

    def test_native_record_parser_preserves_signed_operands_and_gate(self) -> None:
        blob = struct.pack(
            "<ffiiII",
            1.25,
            -2.5,
            -3,
            4,
            TransformKind.STOP_REAIM_REPEAT,
            1,
        )
        record = parse_transform_record(blob, index=7)
        self.assertEqual(record.index, 7)
        self.assertEqual(record.kind, TransformKind.STOP_REAIM_REPEAT)
        self.assertTrue(record.allow_while_active)
        self.assertEqual((record.int_0, record.int_1), (-3, 4))
        self.assertEqual((record.float_0, record.float_1), (1.25, -2.5))

    def test_queue_cursor_selects_next_unconsumed_record(self) -> None:
        blob = bytearray(18 * 24)
        struct.pack_into(
            "<ffiiII",
            blob,
            5 * 24,
            0.5,
            3.0,
            12,
            2,
            TransformKind.STOP_TURN_REPEAT,
            0,
        )
        record = parse_next_transform_record(
            blob,
            program_offset=0,
            queue_cursor=5,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.index, 5)
        self.assertEqual(record.kind, TransformKind.STOP_TURN_REPEAT)
        self.assertFalse(record.allow_while_active)
        self.assertIsNone(
            parse_next_transform_record(
                blob,
                program_offset=0,
                queue_cursor=18,
            )
        )

    def test_ce_0084_stopped_bullet_retains_pending_queue_and_stop_state(
        self,
    ) -> None:
        slot = 23
        base = slot * BULLET_STRIDE
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 2)
        struct.pack_into("<ff", blob, base + BULLET_GEOMETRY_OFFSET, 4.0, 6.0)
        struct.pack_into("<ff", blob, base + BULLET_POSITION_OFFSET, 120.0, 80.0)
        struct.pack_into("<ff", blob, base + BULLET_VELOCITY_OFFSET, 0.0, 0.0)
        struct.pack_into("<f", blob, base + BULLET_SPEED_OFFSET, 0.0)
        struct.pack_into("<f", blob, base + BULLET_ANGLE_OFFSET, 1.5)
        struct.pack_into("<I", blob, base + BULLET_TRANSFORM_FLAGS_OFFSET, 0)
        struct.pack_into(
            "<I",
            blob,
            base + BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
            TransformKind.STOP_REAIM_REPEAT | TransformKind.REFLECT_ALL_EDGES,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET,
            3,
        )
        struct.pack_into(
            "<ffiiII",
            blob,
            base + BULLET_TRANSFORM_PROGRAM_OFFSET + 3 * 24,
            -1.0,
            2.0,
            4,
            5,
            TransformKind.REFLECT_ALL_EDGES,
            0,
        )
        struct.pack_into(
            "<f",
            blob,
            base + BULLET_STOP_TIMER_FRACTION_OFFSET,
            0.25,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_STOP_TIMER_ELAPSED_OFFSET,
            17,
        )
        struct.pack_into(
            "<f",
            blob,
            base + BULLET_STOP_RESUME_SPEED_OFFSET,
            2.75,
        )
        struct.pack_into(
            "<f",
            blob,
            base + BULLET_STOP_ANGLE_OPERAND_OFFSET,
            0.125,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_STOP_DURATION_OFFSET,
            30,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_STOP_REPEAT_LIMIT_OFFSET,
            4,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_STOP_REPEAT_COUNT_OFFSET,
            2,
        )

        bullets = decode_bullets(bytes(blob))
        self.assertEqual(len(bullets), 1)
        bullet = bullets[0]
        self.assertEqual((bullet.slot, bullet.transform_flags), (slot, 0))
        self.assertEqual((bullet.speed, bullet.angle), (0.0, 1.5))
        runtime = bullet.transform_runtime
        self.assertIsNotNone(runtime)
        self.assertEqual(
            runtime.original_flags,
            TransformKind.STOP_REAIM_REPEAT | TransformKind.REFLECT_ALL_EDGES,
        )
        self.assertEqual((runtime.queue_cursor, runtime.timer_elapsed), (3, 17))
        self.assertEqual(
            (runtime.duration, runtime.repeat_limit, runtime.repeat_count),
            (30, 4, 2),
        )
        self.assertEqual(
            (runtime.resume_speed, runtime.angle_operand, runtime.timer_fraction),
            (2.75, 0.125, 0.25),
        )
        self.assertEqual(
            (runtime.next_record.index, runtime.next_record.kind),
            (3, TransformKind.REFLECT_ALL_EDGES),
        )
        compact = decode_bullets(
            bytes(blob),
            retain_transform_runtime=False,
        )[0]
        self.assertIsNone(compact.transform_runtime)
        self.assertEqual(
            compact.original_transform_flags,
            runtime.original_flags,
        )
        compact_trace = serialize_bullet_trace(compact)
        self.assertIsNone(compact_trace[8])
        self.assertEqual(
            compact_trace[9],
            [
                0.0,
                1.5,
                runtime.original_flags,
                0,
                0,
                [],
                0.0,
                0.0,
            ],
        )
        for field in (
            "x",
            "y",
            "vx",
            "vy",
            "half_width",
            "half_height",
            "transform_flags",
            "slot",
            "speed",
            "angle",
            "callback_phase_state",
            "callback_aux_state",
        ):
            self.assertEqual(getattr(compact, field), getattr(bullet, field))

    def test_dense_planning_decoder_matches_diagnostic_gameplay_fields(
        self,
    ) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        for slot in range(800):
            base = slot * BULLET_STRIDE
            struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 1 + slot % 2)
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_GEOMETRY_OFFSET,
                -2.0 - slot % 50,
                4.0 + slot % 60,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_POSITION_OFFSET,
                float(slot) * 0.25,
                448.0 - float(slot) * 0.125,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_VELOCITY_OFFSET,
                float(slot % 7) - 3.0,
                float(slot % 11) - 5.0,
            )
            struct.pack_into(
                "<f",
                blob,
                base + BULLET_SPEED_OFFSET,
                float("nan") if slot == 17 else 0.5 + slot * 0.001,
            )
            struct.pack_into(
                "<f",
                blob,
                base + BULLET_ANGLE_OFFSET,
                float("inf") if slot == 31 else -1.0 + slot * 0.002,
            )
            struct.pack_into(
                "<I",
                blob,
                base + BULLET_TRANSFORM_FLAGS_OFFSET,
                slot * 3,
            )
            struct.pack_into(
                "<I",
                blob,
                base + BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
                0x00100202 if slot % 3 == 0 else 0,
            )
            struct.pack_into(
                "<h",
                blob,
                base + BULLET_CALLBACK_PHASE_STATE_OFFSET,
                slot % 32767,
            )
            blob[base + BULLET_CALLBACK_AUX_STATE_OFFSET] = slot % 256
            struct.pack_into(
                "<i",
                blob,
                base + BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET,
                18,
            )
        invalid_base = 799 * BULLET_STRIDE
        struct.pack_into(
            "<f",
            blob,
            invalid_base + BULLET_POSITION_OFFSET,
            float("nan"),
        )

        diagnostic = decode_bullets(bytes(blob))
        planning = decode_bullets(
            bytes(blob),
            retain_transform_runtime=False,
        )
        self.assertEqual(len(diagnostic), 799)
        self.assertEqual(len(planning), len(diagnostic))
        gameplay_fields = (
            "x",
            "y",
            "vx",
            "vy",
            "half_width",
            "half_height",
            "transform_flags",
            "slot",
            "speed",
            "angle",
            "callback_phase_state",
            "callback_aux_state",
            "original_transform_flags",
        )
        for compact, full in zip(planning, diagnostic):
            self.assertIsNone(compact.transform_runtime)
            self.assertEqual(
                tuple(getattr(compact, field) for field in gameplay_fields),
                tuple(getattr(full, field) for field in gameplay_fields),
            )

    def test_trace_keeps_first_eight_fields_and_appends_compact_runtime(
        self,
    ) -> None:
        runtime = BulletTransformRuntime(
            original_flags=TransformKind.STOP_REAIM_REPEAT,
            queue_cursor=4,
            next_record=_record(index=4),
            timer_fraction=0.5,
            timer_elapsed=12,
            resume_speed=2.5,
            angle_operand=0.25,
            duration=30,
            repeat_limit=4,
            repeat_count=1,
        )
        bullet = Bullet(
            10.0,
            20.0,
            1.0,
            -1.0,
            2.0,
            3.0,
            0,
            7,
            1.5,
            0.75,
            runtime,
        )
        values = serialize_bullet_trace(bullet)
        self.assertEqual(
            values[:8],
            [7, 10.0, 20.0, 1.0, -1.0, 2.0, 3.0, 0],
        )
        self.assertEqual(
            values[8],
            [
                1.5,
                0.75,
                TransformKind.STOP_REAIM_REPEAT,
                4,
                [4, TransformKind.STOP_REAIM_REPEAT, 1, 0.25, 2.5, 30, 4],
                0.5,
                12,
                30,
                2.5,
                0.25,
                4,
                1,
                0,
                0,
                [],
                0.0,
                0.0,
            ],
        )
        self.assertEqual(
            serialize_bullet_trace(Bullet(1.0, 2.0, 0.0, 0.0, 2.0, 2.0))[8],
            None,
        )

    def test_trace_retains_exceptional_native_lifecycle_for_replay(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            1.0,
            -1.0,
            2.0,
            3.0,
            slot=7,
            callback_aux_state=4,
            native_state=2,
            native_state_timer_elapsed=8,
        )

        values = serialize_bullet_trace(bullet)

        self.assertEqual(
            values[-1],
            [BULLET_LIFECYCLE_TRACE_SCHEMA, 2, 8, 4],
        )
        replayed = bullet_from_trace(values)
        self.assertEqual(replayed.native_state, 2)
        self.assertEqual(replayed.native_state_timer_elapsed, 8)
        self.assertEqual(replayed.callback_aux_state, 4)

        timed_state1 = bullet_from_trace(
            serialize_bullet_trace(
                Bullet(
                    1.0,
                    2.0,
                    0.0,
                    0.0,
                    2.0,
                    2.0,
                    native_state=1,
                    native_state_timer_elapsed=9,
                )
            )
        )
        self.assertEqual(timed_state1.native_state, 1)
        self.assertEqual(timed_state1.native_state_timer_elapsed, 9)

    def test_default_lethal_lifecycle_keeps_legacy_trace_shape(self) -> None:
        values = serialize_bullet_trace(
            Bullet(1.0, 2.0, 0.0, 0.0, 2.0, 2.0)
        )

        self.assertEqual(len(values), 9)
        replayed = bullet_from_trace(values)
        self.assertEqual(replayed.native_state, 1)
        self.assertEqual(replayed.native_state_timer_elapsed, 0)
        self.assertEqual(replayed.callback_aux_state, 0)

    def test_runtime_observation_is_behavior_neutral_until_projection_gate(
        self,
    ) -> None:
        plain = Bullet(40.0, 50.0, 1.0, -2.0, 2.0, 3.0)
        observed = Bullet(
            40.0,
            50.0,
            1.0,
            -2.0,
            2.0,
            3.0,
            speed=2.25,
            angle=-1.0,
            transform_runtime=BulletTransformRuntime(
                original_flags=TransformKind.STOP_REAIM_REPEAT,
                queue_cursor=18,
                next_record=None,
                timer_fraction=0.0,
                timer_elapsed=0,
                resume_speed=2.25,
                angle_operand=0.0,
                duration=30,
                repeat_limit=3,
                repeat_count=0,
            ),
        )
        plain_frames = _build_bullet_frames((plain,), horizon=3, snapshot_lag=2)
        observed_frames = _build_bullet_frames(
            (observed,),
            horizon=3,
            snapshot_lag=2,
        )
        for plain_frame, observed_frame in zip(plain_frames, observed_frames):
            for plain_values, observed_values in zip(plain_frame, observed_frame):
                np.testing.assert_array_equal(plain_values, observed_values)
        self.assertEqual(
            lower_bullets((plain,), snapshot_lag=2),
            lower_bullets((observed,), snapshot_lag=2),
        )

    def test_local_projection_applies_velocity_event_on_native_update(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            2.0,
            -1.0,
            2.0,
            3.0,
            velocity_changes=(VelocityChange(3, 0.0, 0.0),),
        )
        frames = _build_bullet_frames(
            (bullet,),
            horizon=5,
            snapshot_lag=0,
        )
        self.assertEqual(
            [float(frame[0][0]) for frame in frames],
            [12.0, 14.0, 14.0, 14.0, 14.0],
        )
        self.assertEqual(
            [float(frame[1][0]) for frame in frames],
            [19.0, 18.0, 18.0, 18.0, 18.0],
        )

    def test_state2_spawn_motion_and_same_update_completion_are_exact(
        self,
    ) -> None:
        bullet = Bullet(
            0.0,
            10.0,
            2.0,
            -1.0,
            2.0,
            3.0,
            native_state=2,
            native_state_timer_elapsed=8,
        )

        frames = _build_bullet_frames(
            (bullet,),
            horizon=4,
            snapshot_lag=0,
        )

        # Timer 8 -> 9 takes one half-step.  Timer 9 completes on the next
        # update: native stores a half-step, then a full state-1 step.
        self.assertEqual(
            [float(frame[0][0]) for frame in frames],
            [1.0, 4.0, 6.0, 8.0],
        )
        self.assertEqual(
            [float(frame[1][0]) for frame in frames],
            [9.5, 8.0, 7.0, 6.0],
        )

    def test_python_and_packed_decoders_retain_native_lifecycle_state(
        self,
    ) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        for slot in range(20):
            base = slot * BULLET_STRIDE
            struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 2)
            struct.pack_into(
                "<i",
                blob,
                base + BULLET_STATE_TIMER_ELAPSED_OFFSET,
                2 + slot % 4,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_GEOMETRY_OFFSET,
                4.0,
                4.0,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_POSITION_OFFSET,
                float(slot),
                20.0,
            )
            struct.pack_into(
                "<ff",
                blob,
                base + BULLET_VELOCITY_OFFSET,
                1.0,
                0.0,
            )

        objects = decode_bullets(blob, retain_transform_runtime=False)
        packed = decode_packed_bullets(blob)

        self.assertEqual(
            [bullet.native_state for bullet in objects],
            [2] * 20,
        )
        self.assertEqual(
            [bullet.native_state_timer_elapsed for bullet in objects],
            [2 + slot % 4 for slot in range(20)],
        )
        np.testing.assert_array_equal(packed.native_state, np.full(20, 2))
        np.testing.assert_array_equal(
            packed.native_state_timer_elapsed,
            np.asarray([2 + slot % 4 for slot in range(20)]),
        )

    def test_velocity_event_replaces_float32_value_without_delta_rounding(
        self,
    ) -> None:
        initial_velocity = 5.275492191314697
        replacement_velocity = -4.898619651794434
        bullet = Bullet(
            0.0,
            20.0,
            initial_velocity,
            0.0,
            2.0,
            3.0,
            velocity_changes=(
                VelocityChange(2, replacement_velocity, 0.0),
            ),
        )
        frames = _build_bullet_frames(
            (bullet,),
            horizon=3,
            snapshot_lag=0,
        )
        expected_x = 0.0
        expected = []
        for velocity in (
            initial_velocity,
            replacement_velocity,
            replacement_velocity,
        ):
            expected_x = binary32_store(expected_x + velocity)
            expected.append(expected_x)
        self.assertEqual(
            [float(frame[0][0]) for frame in frames],
            expected,
        )

    def test_callback_event_is_rebased_to_bullet_snapshot_epoch(self) -> None:
        bullet = Bullet(
            10.0,
            20.0,
            2.0,
            0.0,
            2.0,
            3.0,
            speed=2.0,
            angle=0.0,
            callback_phase_state=1,
            original_transform_flags=0x100202,
        )
        snapshot = EclVmSnapshot(
            0x500000,
            0.0,
            300,
            0x100000,
            0.0,
            0.0,
            1.0,
        )
        attached = attach_tagged_velocity_toggles(
            (bullet,),
            vm_snapshot=snapshot,
            toggles=(
                TaggedVelocityToggle(
                    3,
                    12,
                    0x100000,
                    0.0,
                    0.0,
                ),
            ),
            frame_offset=2,
            event_frame_uncertainty=1,
        )[0]
        self.assertEqual(attached.velocity_changes[0].frame, 5)
        self.assertEqual(attached.trajectory_uncertainty_x, 2.0)
        frames = _build_bullet_frames(
            (attached,),
            horizon=6,
            snapshot_lag=0,
        )
        self.assertEqual(
            [float(frame[0][0]) for frame in frames],
            [12.0, 14.0, 16.0, 18.0, 18.0, 18.0],
        )


if __name__ == "__main__":
    unittest.main()
