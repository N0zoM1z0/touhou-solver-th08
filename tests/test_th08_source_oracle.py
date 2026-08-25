#!/usr/bin/env python3
"""Differential gates for the tracked C transcription of source kernels."""

from __future__ import annotations

import math
from pathlib import Path
import random
import shutil
import struct
import tempfile
import unittest

from build_th08_source_oracle import build
from th08_bullet_template_contract import bullet_spawn_lifecycle
from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    lower_future_direct_fire,
    lower_future_direct_fire_sectors,
    spawn_lifecycle_position_coefficient,
)
from th08_rng import Th08Rng
from th08_semantics.native_oracle import (
    NativeSourceOracle,
    NativeTransformState,
)
from th08_semantics.source_primitives import (
    Callback12State,
    SourcePattern,
    aabb_overlap,
    apply_callback12,
    f32,
    pattern_sample,
)
from th08_semantics.stage import (
    RuntimeBullet,
    StageRuntime,
    TRANSFORM_ANGULAR_VELOCITY,
    TRANSFORM_DECELERATE,
    TRANSFORM_REFLECT_ALL,
    TRANSFORM_REFLECT_SIDES_TOP,
    TRANSFORM_STOP_REAIM,
    TRANSFORM_STOP_SNAP,
    TRANSFORM_STOP_TURN,
    TRANSFORM_VECTOR_ACCELERATION,
    TransformSpec,
    _TransformRuntime,
)
from th08_semantics.stage_generation import generate_stage_program


def _bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _ulp_distance(left: float, right: float) -> int:
    left_bits = _bits(left)
    right_bits = _bits(right)
    # Samples here are finite. Map sign-magnitude float ordering to integers.
    if left_bits & 0x80000000:
        left_bits = 0x80000000 - (left_bits & 0x7FFFFFFF)
    else:
        left_bits += 0x80000000
    if right_bits & 0x80000000:
        right_bits = 0x80000000 - (right_bits & 0x7FFFFFFF)
    else:
        right_bits += 0x80000000
    return abs(left_bits - right_bits)


def _distance_to_annular_sector(
    x: float,
    y: float,
    *,
    minimum_angle: float,
    maximum_angle: float,
    minimum_radius: float,
    maximum_radius: float,
) -> float:
    radius = math.hypot(x, y)
    angle = math.atan2(y, x)
    candidates: list[float] = []
    if minimum_angle <= angle <= maximum_angle:
        candidates.append(
            max(minimum_radius - radius, 0.0, radius - maximum_radius)
        )
    for boundary in (minimum_angle, maximum_angle):
        direction_x = math.cos(boundary)
        direction_y = math.sin(boundary)
        projected = x * direction_x + y * direction_y
        closest_radius = min(
            maximum_radius,
            max(minimum_radius, projected),
        )
        candidates.append(
            math.hypot(
                x - closest_radius * direction_x,
                y - closest_radius * direction_y,
            )
        )
    return min(candidates)


class Th08SourceOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("cc") is None:
            raise unittest.SkipTest("C compiler unavailable")
        cls.temporary = tempfile.TemporaryDirectory()
        path = Path(cls.temporary.name) / "libth08_source_oracle.so"
        build(path)
        cls.oracle = NativeSourceOracle.load(path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_rng_binary32_cast_matches_c_for_full_seed_space(self) -> None:
        for seed in range(0x10000):
            python_rng = Th08Rng(seed)
            native_rng = Th08Rng(seed)
            self.assertEqual(
                python_rng.next_unit(),
                self.oracle.rng_next_f32(native_rng),
            )
            self.assertEqual(
                (python_rng.state, python_rng.calls),
                (native_rng.state, native_rng.calls),
            )

    def test_all_pattern_modes_match_independent_c_transcription(self) -> None:
        generator = random.Random(0xCE0132)
        for mode in range(9):
            for case_index in range(48):
                count1 = generator.randint(1, 64)
                count2 = generator.randint(1, 5)
                pattern = SourcePattern(
                    mode=mode,
                    count1=count1,
                    count2=count2,
                    speed1=generator.uniform(0.25, 8.0),
                    speed2=generator.uniform(0.1, 4.0),
                    angle=generator.uniform(-math.pi, math.pi),
                    angle_step=generator.uniform(-math.pi, math.pi),
                    angle_to_player=generator.uniform(-math.pi, math.pi),
                    time_scale=generator.choice((0.5, 0.75, 1.0)),
                )
                bullet_index = generator.randrange(count1)
                ring_index = generator.randrange(count2)
                python_rng = Th08Rng((mode * 977 + case_index) & 0xFFFF)
                native_rng = Th08Rng(python_rng.state)

                candidate = pattern_sample(
                    pattern,
                    bullet_index=bullet_index,
                    ring_index=ring_index,
                    rng=python_rng,
                )
                authority = self.oracle.pattern_sample(
                    pattern,
                    bullet_index=bullet_index,
                    ring_index=ring_index,
                    rng=native_rng,
                )

                self.assertEqual(candidate.speed, authority.speed)
                self.assertEqual(candidate.angle, authority.angle)
                # Python's libm double sin/cos and the C oracle's sinf/cosf
                # are separate approximations. Angle/speed remain bit exact;
                # admit only sub-micro-pixel velocity disagreement here.
                self.assertLessEqual(
                    abs(candidate.velocity_x - authority.velocity_x),
                    1.0e-6,
                )
                self.assertLessEqual(
                    abs(candidate.velocity_y - authority.velocity_y),
                    1.0e-6,
                )
                self.assertEqual(
                    (python_rng.state, python_rng.calls),
                    (native_rng.state, native_rng.calls),
                )

    def test_callback12_phase_aux_and_velocity_match_c(self) -> None:
        for phase in (-7, 0, 1, 2, 19):
            state = Callback12State(
                phase_state=phase,
                collision_aux=9,
                presentation_flags=0xFFFF,
                animation_index=31,
                base_speed=2.25,
                base_angle=-0.75,
                velocity_x=3.0,
                velocity_y=-4.0,
            )
            candidate, candidate_changed = apply_callback12(
                state,
                bullet_tags=0x102000,
                selected_tags=0x100000,
                callback_angle=1.25,
                callback_speed=4.5,
                time_scale=0.75,
            )
            authority, authority_changed = self.oracle.callback12(
                state,
                bullet_tags=0x102000,
                selected_tags=0x100000,
                callback_angle=1.25,
                callback_speed=4.5,
                time_scale=0.75,
            )
            self.assertEqual(candidate_changed, authority_changed)
            self.assertEqual(
                candidate.__dict__
                | {
                    "velocity_x": authority.velocity_x,
                    "velocity_y": authority.velocity_y,
                },
                authority.__dict__,
            )
            self.assertLessEqual(
                _ulp_distance(candidate.velocity_x, authority.velocity_x),
                1,
            )
            self.assertLessEqual(
                _ulp_distance(candidate.velocity_y, authority.velocity_y),
                1,
            )

    def test_all_spawn_lifecycle_type_flag_classes_match_c(self) -> None:
        generator = random.Random(0x433070)
        flag_classes = (0, 0x02, 0x04, 0x08, 0x06, 0x0C, 0x0E)
        legacy_guard_escape_samples = 0
        maximum_legacy_axis_error = 0.0
        for bullet_type in range(21):
            for original_flags in flag_classes:
                lifecycle = bullet_spawn_lifecycle(
                    bullet_type,
                    original_flags,
                )
                terminal_age = (
                    lifecycle.terminal_age if lifecycle is not None else 0
                )
                ages = sorted(
                    {
                        1,
                        max(1, terminal_age - 1),
                        max(1, terminal_age),
                        max(1, terminal_age + 1),
                        max(1, terminal_age + 37),
                    }
                )
                speed = f32(generator.uniform(0.1, 8.0))
                angle = f32(generator.uniform(-math.pi, math.pi))
                origin_x = f32(generator.uniform(16.0, 368.0))
                origin_y = f32(generator.uniform(16.0, 432.0))
                pattern = SourcePattern(
                    mode=1,
                    count1=1,
                    count2=1,
                    speed1=speed,
                    speed2=speed,
                    angle=angle,
                    angle_step=0.0,
                    angle_to_player=0.0,
                    time_scale=1.0,
                )
                velocity = self.oracle.pattern_sample(
                    pattern,
                    bullet_index=0,
                    ring_index=0,
                    rng=Th08Rng(1),
                )
                event = FutureDirectFire(
                    source="spawn-lifecycle-differential",
                    activation_frames=(1,),
                    bullet_type=bullet_type,
                    origin_x=FloatInterval.point(origin_x),
                    origin_y=FloatInterval.point(origin_y),
                    mode=1,
                    count1=1,
                    count2=1,
                    speed1=FloatInterval.point(speed),
                    speed2=FloatInterval.point(speed),
                    angle1=FloatInterval.point(angle),
                    angle2=FloatInterval.point(0.0),
                    aim_angle=FloatInterval.point(0.0),
                    half_width=0.0,
                    half_height=0.0,
                    original_flags=original_flags,
                    transform_program_zero=True,
                )
                trajectory = lower_future_direct_fire(
                    event,
                    horizon_frames=max(ages),
                )[0].trajectory
                sector = lower_future_direct_fire_sectors(
                    event,
                    horizon_frames=max(ages),
                )[0].trajectory
                for age in ages:
                    with self.subTest(
                        bullet_type=bullet_type,
                        original_flags=original_flags,
                        age=age,
                    ):
                        authority = self.oracle.spawn_lifecycle_sample(
                            bullet_type=bullet_type,
                            original_flags=original_flags,
                            age=age,
                            origin_x=origin_x,
                            origin_y=origin_y,
                            velocity_x=velocity.velocity_x,
                            velocity_y=velocity.velocity_y,
                        )
                        expected_state = (
                            lifecycle.state
                            if lifecycle is not None
                            and age < lifecycle.terminal_age
                            else 1
                        )
                        self.assertEqual(authority.state, expected_state)
                        self.assertEqual(
                            authority.lethal_active,
                            expected_state == 1,
                        )
                        self.assertEqual(authority.terminal_age, terminal_age)
                        if lifecycle is not None:
                            self.assertEqual(
                                authority.motion_divisor,
                                lifecycle.motion_divisor,
                            )
                        sample = trajectory.sample(age)
                        if not authority.lethal_active:
                            self.assertIsNone(sample)
                            continue
                        self.assertIsNotNone(sample)
                        assert sample is not None
                        self.assertLessEqual(
                            abs(authority.x - sample.x),
                            sample.half_width,
                        )
                        self.assertLessEqual(
                            abs(authority.y - sample.y),
                            sample.half_height,
                        )
                        coefficient = (
                            spawn_lifecycle_position_coefficient(
                                age,
                                lifecycle,
                            )
                            if lifecycle is not None
                            else float(age)
                        )
                        ideal_x = (
                            origin_x
                            + coefficient * speed * math.cos(angle)
                        )
                        ideal_y = (
                            origin_y
                            + coefficient * speed * math.sin(angle)
                        )
                        legacy_axis_error = max(
                            abs(authority.x - ideal_x),
                            abs(authority.y - ideal_y),
                        )
                        maximum_legacy_axis_error = max(
                            maximum_legacy_axis_error,
                            legacy_axis_error,
                        )
                        if legacy_axis_error > 2.0e-5:
                            legacy_guard_escape_samples += 1
                        self.assertLessEqual(
                            math.hypot(
                                authority.x - ideal_x,
                                authority.y - ideal_y,
                            ),
                            sector.base_uncertainty,
                        )
        # The former fixed two-ulp-at-screen-scale guard is intentionally
        # retained as a falsified baseline, not silently forgotten after the
        # source-order interval recurrence replaced it.
        self.assertGreater(legacy_guard_escape_samples, 0)
        self.assertGreater(maximum_legacy_axis_error, 2.0e-5)

    def test_random_speed_angle_sector_contains_c_lifecycle_samples(self) -> None:
        origin_x = f32(192.0)
        origin_y = f32(224.0)
        pattern = SourcePattern(
            mode=8,
            count1=1,
            count2=1,
            speed1=f32(8.0),
            speed2=f32(0.5),
            angle=f32(1.0),
            angle_step=f32(-1.0),
            angle_to_player=0.0,
            time_scale=1.0,
        )
        event = FutureDirectFire(
            source="random-sector-lifecycle-differential",
            activation_frames=(1,),
            bullet_type=7,
            origin_x=FloatInterval.point(origin_x),
            origin_y=FloatInterval.point(origin_y),
            mode=8,
            count1=1,
            count2=1,
            speed1=FloatInterval.point(pattern.speed1),
            speed2=FloatInterval.point(pattern.speed2),
            angle1=FloatInterval.point(pattern.angle),
            angle2=FloatInterval.point(pattern.angle_step),
            aim_angle=FloatInterval.point(0.0),
            half_width=0.0,
            half_height=0.0,
            original_flags=0x02,
            transform_program_zero=True,
        )
        sector = lower_future_direct_fire_sectors(
            event,
            horizon_frames=67,
        )[0].trajectory

        for seed in range(256):
            velocity = self.oracle.pattern_sample(
                pattern,
                bullet_index=0,
                ring_index=0,
                rng=Th08Rng(seed),
            )
            for age in (30, 31, 67):
                with self.subTest(seed=seed, age=age):
                    authority = self.oracle.spawn_lifecycle_sample(
                        bullet_type=7,
                        original_flags=0x02,
                        age=age,
                        origin_x=origin_x,
                        origin_y=origin_y,
                        velocity_x=velocity.velocity_x,
                        velocity_y=velocity.velocity_y,
                    )
                    radial_sample = sector.radial_sample(age)
                    self.assertIsNotNone(radial_sample)
                    assert radial_sample is not None
                    distance = _distance_to_annular_sector(
                        authority.x - origin_x,
                        authority.y - origin_y,
                        minimum_angle=sector.minimum_angle,
                        maximum_angle=sector.maximum_angle,
                        minimum_radius=radial_sample[0],
                        maximum_radius=radial_sample[1],
                    )
                    self.assertLessEqual(distance, sector.base_uncertainty)

    def test_inclusive_aabb_tangent_cases_match_c(self) -> None:
        for epsilon in (-1e-4, 0.0, 1e-4):
            values = {
                "player_x": 10.0,
                "player_y": 20.0,
                "player_half_width": 1.0,
                "player_half_height": 2.0,
                "hazard_x": 13.0 + epsilon,
                "hazard_y": 25.0,
                "hazard_half_width": 2.0,
                "hazard_half_height": 3.0,
            }
            self.assertEqual(
                aabb_overlap(**values),
                self.oracle.aabb_overlap(**values),
            )

    def test_transform_handlers_match_c_field_transitions(self) -> None:
        generator = random.Random(0x432210)
        kinds = (
            TRANSFORM_DECELERATE,
            TRANSFORM_VECTOR_ACCELERATION,
            TRANSFORM_ANGULAR_VELOCITY,
            TRANSFORM_STOP_TURN,
            TRANSFORM_STOP_REAIM,
            TRANSFORM_STOP_SNAP,
            TRANSFORM_REFLECT_ALL,
            TRANSFORM_REFLECT_SIDES_TOP,
        )
        runtime = StageRuntime(
            generate_stage_program(seed=3, profile="quick")
        )
        for kind in kinds:
            for case_index in range(48):
                duration = generator.randint(0, 45)
                repeat_limit = generator.randint(1, 4)
                parameter_0 = f32(generator.uniform(-2.5, 2.5))
                parameter_1 = f32(generator.uniform(-0.2, 4.0))
                spec = TransformSpec(
                    kind=kind,
                    duration=duration,
                    repeat_limit=repeat_limit,
                    float_0=parameter_0,
                    float_1=parameter_1,
                )
                x = f32(
                    generator.choice((-8.0, 192.0, 392.0))
                    if kind in (TRANSFORM_REFLECT_ALL, TRANSFORM_REFLECT_SIDES_TOP)
                    else generator.uniform(16.0, 368.0)
                )
                y = f32(
                    generator.choice((-8.0, 200.0, 456.0))
                    if kind in (TRANSFORM_REFLECT_ALL, TRANSFORM_REFLECT_SIDES_TOP)
                    else generator.uniform(16.0, 432.0)
                )
                velocity_x = f32(generator.uniform(-5.0, 5.0))
                velocity_y = f32(generator.uniform(-5.0, 5.0))
                base_speed = f32(generator.uniform(0.2, 6.0))
                base_angle = f32(generator.uniform(-math.pi, math.pi))
                restored_speed = f32(generator.uniform(0.2, 5.0))
                acceleration_x = f32(generator.uniform(-0.1, 0.1))
                acceleration_y = f32(generator.uniform(-0.1, 0.1))
                timer = generator.randint(0, max(17, duration + 1))
                repeat_count = generator.randint(0, repeat_limit - 1)
                bullet = RuntimeBullet(
                    slot=0,
                    source="transform-differential",
                    x=x,
                    y=y,
                    velocity_x=velocity_x,
                    velocity_y=velocity_y,
                    half_width=2.0,
                    half_height=3.0,
                    base_speed=base_speed,
                    base_angle=base_angle,
                    tag_flags=0,
                    transforms=(),
                )
                transform = _TransformRuntime(
                    spec=spec,
                    timer=timer,
                    repeat_count=repeat_count,
                    restored_speed=restored_speed,
                    acceleration_x=acceleration_x,
                    acceleration_y=acceleration_y,
                )
                bullet.active_transforms[kind] = transform
                authority = self.oracle.transform_step(
                    kind,
                    NativeTransformState(
                        x=x,
                        y=y,
                        half_width=2.0,
                        half_height=3.0,
                        velocity_x=velocity_x,
                        velocity_y=velocity_y,
                        base_speed=base_speed,
                        base_angle=base_angle,
                        parameter_0=parameter_0,
                        parameter_1=parameter_1,
                        restored_speed=restored_speed,
                        acceleration_x=acceleration_x,
                        acceleration_y=acceleration_y,
                        timer=timer,
                        duration=duration,
                        repeat_limit=repeat_limit,
                        repeat_count=repeat_count,
                    ),
                    player_x=192.0,
                    player_y=400.0,
                )

                runtime._apply_transform_handlers(
                    bullet,
                    player_x=192.0,
                    player_y=400.0,
                )

                self.assertEqual(
                    kind in bullet.active_transforms,
                    authority.active,
                )
                self.assertEqual(transform.timer, authority.timer)
                self.assertEqual(
                    transform.repeat_count,
                    authority.repeat_count,
                )
                for candidate, expected in (
                    (bullet.base_speed, authority.base_speed),
                    (bullet.base_angle, authority.base_angle),
                    (bullet.velocity_x, authority.velocity_x),
                    (bullet.velocity_y, authority.velocity_y),
                ):
                    self.assertLessEqual(abs(candidate - expected), 2.0e-6)


if __name__ == "__main__":
    unittest.main()
