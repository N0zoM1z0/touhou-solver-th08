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
from th08_rng import Th08Rng
from th08_semantics.native_oracle import NativeSourceOracle
from th08_semantics.source_primitives import (
    Callback12State,
    SourcePattern,
    aabb_overlap,
    apply_callback12,
    pattern_sample,
)


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


if __name__ == "__main__":
    unittest.main()
