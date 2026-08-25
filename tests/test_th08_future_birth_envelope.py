"""Focused tests for causal future-birth geometry lowering."""

from __future__ import annotations

import math
import struct
import unittest

from th08_bullet_template_contract import bullet_spawn_lifecycle
from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    FutureTaggedBulletCallback,
    _pattern_speed_angle,
    lower_future_direct_fire,
    lower_future_direct_fire_sectors,
    spawn_lifecycle_position_coefficient,
)


def _h1_event(**updates: object) -> FutureDirectFire:
    fields: dict[str, object] = {
        "source": "root2129:singleton:aux0",
        "activation_frames": (1,),
        "bullet_type": 2,
        "origin_x": FloatInterval.point(60.05625534057617),
        "origin_y": FloatInterval.point(32.0),
        "mode": 1,
        "count1": 1,
        "count2": 1,
        "speed1": FloatInterval.point(0.9987534284591675),
        "speed2": FloatInterval.point(0.48124998807907104),
        "angle1": FloatInterval.point(-0.5760713815689087),
        "angle2": FloatInterval.point(0.0),
        "aim_angle": FloatInterval.point(0.0),
        "half_width": 2.0,
        "half_height": 2.0,
        "original_flags": 0x203,
        "transform_program_zero": True,
    }
    fields.update(updates)
    return FutureDirectFire(**fields)


def _stop_reaim_program(*, resume_speed: float = 2.5) -> bytes:
    program = bytearray(18 * 24)
    struct.pack_into(
        "<ffiiII",
        program,
        0,
        0.0,
        resume_speed,
        50,
        1,
        0x80,
        0,
    )
    return bytes(program)


def _angular_velocity_program(*, acceleration: float = 0.5) -> bytes:
    program = bytearray(18 * 24)
    struct.pack_into(
        "<ffiiII",
        program,
        0,
        acceleration,
        0.1,
        40,
        -1,
        0x20,
        0,
    )
    return bytes(program)


class FutureBirthEnvelopeTests(unittest.TestCase):
    def test_fan_centering_uses_count_parity_not_flag_parity(self) -> None:
        odd_count_even_flags = _h1_event(
            count1=3,
            original_flags=0,
            angle1=FloatInterval.point(0.25),
            angle2=FloatInterval.point(0.4),
        )
        _speed, angle = _pattern_speed_angle(
            odd_count_even_flags,
            bullet_index=0,
            ring_index=0,
        )
        self.assertEqual(angle, FloatInterval.point(0.25))

        even_count_odd_flags = _h1_event(
            count1=2,
            original_flags=1,
            angle1=FloatInterval.point(0.25),
            angle2=FloatInterval.point(0.4),
        )
        _speed, angle = _pattern_speed_angle(
            even_count_odd_flags,
            bullet_index=0,
            ring_index=0,
        )
        self.assertEqual(angle, FloatInterval.point(0.45))

    def test_mode_four_uses_source_binary32_pi_constants(self) -> None:
        source_pi = struct.unpack("<f", struct.pack("<f", math.pi))[0]
        source_two_pi = struct.unpack(
            "<f", struct.pack("<f", source_pi * 2.0)
        )[0]
        event = _h1_event(
            mode=4,
            count1=3,
            original_flags=0,
            angle1=FloatInterval.point(0.0),
            angle2=FloatInterval.point(0.0),
        )

        _speed, angle = _pattern_speed_angle(
            event,
            bullet_index=2,
            ring_index=0,
        )

        expected = source_pi / 3 + 2 * source_two_pi / 3
        self.assertEqual(angle, FloatInterval.point(expected))

    def test_native_state2_coefficients_retain_half_step_completion(self) -> None:
        lifecycle = bullet_spawn_lifecycle(2, 0x02)
        assert lifecycle is not None
        self.assertEqual(
            spawn_lifecycle_position_coefficient(1, lifecycle),
            -3.5,
        )
        self.assertEqual(
            spawn_lifecycle_position_coefficient(9, lifecycle),
            0.5,
        )
        self.assertEqual(
            spawn_lifecycle_position_coefficient(10, lifecycle),
            2.0,
        )
        self.assertEqual(
            spawn_lifecycle_position_coefficient(16, lifecycle),
            8.0,
        )

    def test_lifecycle_completion_varies_by_generic_bullet_type(self) -> None:
        cases = (
            (0, 0x02, 10),
            (7, 0x02, 30),
            (10, 0x02, 24),
            (2, 0x04, 15),
            (7, 0x04, 30),
            (10, 0x08, 24),
        )
        for bullet_type, flags, terminal_age in cases:
            with self.subTest(bullet_type=bullet_type, flags=flags):
                event = _h1_event(
                    bullet_type=bullet_type,
                    original_flags=flags,
                )
                trajectory = lower_future_direct_fire(
                    event,
                    horizon_frames=terminal_age,
                )[0].trajectory
                self.assertIsNone(trajectory.sample(terminal_age - 1))
                self.assertIsNotNone(trajectory.sample(terminal_age))

    def test_lifecycle_flag_priority_matches_native_else_if_chain(self) -> None:
        lifecycle = bullet_spawn_lifecycle(10, 0x0E)

        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle.state, 2)
        self.assertEqual(lifecycle.flag, 0x02)
        self.assertEqual(lifecycle.motion_divisor, 2.0)
        self.assertEqual(lifecycle.terminal_age, 24)

    def test_state3_completion_uses_divisor_and_same_update_activation(self) -> None:
        lifecycle = bullet_spawn_lifecycle(2, 0x04)
        assert lifecycle is not None

        self.assertEqual(
            spawn_lifecycle_position_coefficient(14, lifecycle),
            -4.0 + 14.0 / 2.5,
        )
        self.assertEqual(
            spawn_lifecycle_position_coefficient(15, lifecycle),
            -4.0 + 15.0 / 2.5 + 1.0,
        )

    def test_root2129_first_endpoint_matches_origin_minus_three_point_five_v(
        self,
    ) -> None:
        event = _h1_event()
        speed = event.speed1.lower
        angle = event.angle1.lower
        velocity_x = speed * math.cos(angle)
        velocity_y = speed * math.sin(angle)
        expected_x = event.origin_x.lower - 3.5 * velocity_x
        expected_y = event.origin_y.lower - 3.5 * velocity_y

        self.assertAlmostEqual(expected_x, 57.12478, places=4)
        self.assertAlmostEqual(expected_y, 33.90419, places=4)
        # State 2 is still in spawn ANM and therefore absent from the lethal
        # corridor hazard set at the first retained endpoint.
        result = lower_future_direct_fire(event, horizon_frames=16)
        self.assertIsNone(result[0].trajectory.sample(1))

    def test_state2_becomes_consumed_hazard_on_completion_update(self) -> None:
        result = lower_future_direct_fire(
            _h1_event(),
            horizon_frames=12,
        )
        trajectory = result[0].trajectory
        self.assertIsNone(trajectory.sample(9))
        sample = trajectory.sample(10)
        self.assertIsNotNone(sample)
        assert sample is not None
        speed = 0.9987534284591675
        angle = -0.5760713815689087
        self.assertAlmostEqual(
            sample.x,
            60.05625534057617 + 2.0 * speed * math.cos(angle),
            delta=2.0e-5,
        )
        self.assertAlmostEqual(
            sample.y,
            32.0 + 2.0 * speed * math.sin(angle),
            delta=2.0e-5,
        )

    def test_rng_angle_interval_is_a_bounded_envelope(self) -> None:
        event = _h1_event(
            mode=6,
            angle1=FloatInterval.point(-0.5),
            angle2=FloatInterval.point(0.5),
            original_flags=0x201,
        )
        result = lower_future_direct_fire(event, horizon_frames=1)
        sample = result[0].trajectory.sample(1)
        self.assertIsNotNone(sample)
        assert sample is not None
        for angle in (-0.5, 0.0, 0.5):
            x = event.origin_x.lower + event.speed1.lower * math.cos(angle)
            y = event.origin_y.lower + event.speed1.lower * math.sin(angle)
            self.assertLessEqual(abs(x - sample.x), sample.half_width)
            self.assertLessEqual(abs(y - sample.y), sample.half_height)

    def test_nonzero_transform_program_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "transform programs"):
            _h1_event(transform_program_zero=False)

    def test_inactive_transform_record_preserves_linear_sector(self) -> None:
        program = _stop_reaim_program()
        event = _h1_event(
            transform_program_zero=False,
            transform_program=program,
        )
        trajectory = lower_future_direct_fire_sectors(
            event,
            horizon_frames=12,
        )[0].trajectory
        self.assertEqual(trajectory.minimum_angle, event.angle1.lower)
        self.assertEqual(trajectory.maximum_angle, event.angle1.upper)

    def test_active_stop_reaim_uses_full_direction_path_bound(self) -> None:
        program = _stop_reaim_program(resume_speed=2.5)
        event = _h1_event(
            original_flags=0x283,
            transform_program_zero=False,
            transform_program=program,
        )
        sector = lower_future_direct_fire_sectors(
            event,
            horizon_frames=12,
        )[0].trajectory
        self.assertEqual(
            (sector.minimum_angle, sector.maximum_angle),
            (-math.pi, math.pi),
        )
        self.assertEqual(sector.minimum_radii[10], 0.0)
        self.assertEqual(sector.maximum_radii[10], 2.5 * 14.0)
        box = lower_future_direct_fire(event, horizon_frames=12)[0].trajectory
        sample = box.sample(10)
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertGreaterEqual(sample.half_width, 2.0 + 2.5 * 14.0)

    def test_active_angular_velocity_uses_accelerating_disc_bound(self) -> None:
        event = _h1_event(
            original_flags=0x223,
            transform_program_zero=False,
            transform_program=_angular_velocity_program(),
        )
        sector = lower_future_direct_fire_sectors(
            event,
            horizon_frames=12,
        )[0].trajectory
        self.assertEqual(
            (sector.minimum_angle, sector.maximum_angle),
            (-math.pi, math.pi),
        )
        # At age 10, state-2 uncertainty uses 14 conservative motion steps.
        expected = event.speed1.lower * 14.0 + 0.5 * 14.0 * 15.0 / 2.0
        self.assertGreaterEqual(sector.maximum_radii[10], expected)
        sample = lower_future_direct_fire(event, horizon_frames=12)[
            0
        ].trajectory.sample(10)
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertGreaterEqual(sample.half_width, event.half_width + expected)

    def test_matching_tagged_callback_uses_callback_speed_disc_bound(self) -> None:
        event = _h1_event(
            original_flags=0x100000,
            tagged_callbacks=(
                FutureTaggedBulletCallback(
                    source="enemy:7:main:callback12",
                    frame=5,
                    callback_index=12,
                    tag_mask=0x100000,
                    callback_angle=FloatInterval.point(0.75),
                    callback_speed=FloatInterval.point(3.0),
                ),
            ),
        )

        sector = lower_future_direct_fire_sectors(
            event,
            horizon_frames=10,
        )[0].trajectory

        self.assertEqual(
            (sector.minimum_angle, sector.maximum_angle),
            (-math.pi, math.pi),
        )
        self.assertEqual(sector.minimum_radii[10], 0.0)
        self.assertEqual(sector.maximum_radii[10], 30.0)

    def test_unknown_native_flag_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported future bullet flags"):
            _h1_event(original_flags=0x40000203)

    def test_bullet_type_outside_initialized_table_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the initialized table"):
            _h1_event(bullet_type=21)


if __name__ == "__main__":
    unittest.main()
