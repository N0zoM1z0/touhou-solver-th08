#!/usr/bin/env python3
"""Regression tests for TH08 bullet-transform field semantics."""

import math
import struct
import unittest
from pathlib import Path

from th08_bullet_transform_model import (
    ReflectionState,
    TRANSFORM_PROGRAM_SIZE,
    TransformKind,
    TransformRecord,
    apply_reflection_event,
    copy_transform_program,
    decode_derived_pattern,
    pack_transform_program,
    parse_transform_program,
    step_countdown_transform,
    transform_field_meanings,
    transform_record_from_decoded,
    wrap_coordinate,
)
from th08_ecl import decode_bullet_transform, parse_ecl


ROOT = Path(__file__).resolve().parents[1]


class BulletTransformModelTests(unittest.TestCase):
    def test_complete_program_pack_parse_and_copy_preserve_native_abi(self) -> None:
        record = TransformRecord(
            index=0,
            kind=int(TransformKind.VECTOR_ACCELERATION),
            allow_while_active=True,
            int_0=-7,
            int_1=11,
            float_0=-0.0,
            float_1=1.25,
        )

        program = pack_transform_program((record,))

        self.assertEqual(len(program), TRANSFORM_PROGRAM_SIZE)
        self.assertEqual(
            program[:24],
            struct.pack("<ffiiII", -0.0, 1.25, -7, 11, 0x10, 1),
        )
        self.assertEqual(program[24:], bytes(TRANSFORM_PROGRAM_SIZE - 24))
        self.assertEqual(parse_transform_program(program)[0], record)
        self.assertEqual(copy_transform_program(b"prefix" + program, program_offset=6), program)
        with self.assertRaisesRegex(ValueError, "truncated"):
            copy_transform_program(program[:-1])
        with self.assertRaisesRegex(ValueError, "canonical indexed prefix"):
            pack_transform_program((TransformRecord(1, 0, False, 0, 0, 0.0, 0.0),))

    def test_extra_derived_pattern_pair_decodes_exactly(self) -> None:
        ecl = parse_ecl(ROOT / "artifacts" / "decoded" / "ecldata8.ecl")
        instructions = ecl.subroutines[127].instructions
        index = next(i for i, insn in enumerate(instructions) if insn.offset == 0xE264)
        first = transform_record_from_decoded(decode_bullet_transform(instructions[index]))
        second = transform_record_from_decoded(
            decode_bullet_transform(instructions[index + 1])
        )
        pattern = decode_derived_pattern(first, second)
        self.assertTrue(pattern.kill_parent)
        self.assertEqual(
            (
                pattern.mode,
                pattern.bullet_type,
                pattern.color,
                pattern.start_transform_index,
                pattern.count_1,
                pattern.count_2,
                pattern.child_transform_flags,
            ),
            (8, 7, 1, 3, 4, 1, 0x01020240),
        )
        self.assertEqual((pattern.angle_1, pattern.angle_2), (0.5, 4.0))

    def test_field_meanings_cover_all_corpus_kinds(self) -> None:
        kinds = {
            0x10,
            0x20,
            0x40,
            0x80,
            0x400,
            0x800,
            0x2000,
            0x4000,
            0x20000,
            0x40000,
            0x80000,
            0x400000,
            0x800000,
            0x1000000,
            0x2000000,
        }
        self.assertTrue(all(kind in TransformKind._value2member_map_ for kind in kinds))
        self.assertTrue(all(transform_field_meanings(kind) or kind == 0x40000 for kind in kinds))

    def test_reflection_waits_until_sprite_is_fully_outside(self) -> None:
        partial = ReflectionState(-1.0, 100.0, 1.0, 0.0, 2.0, 2)
        self.assertEqual(
            apply_reflection_event(
                partial,
                kind=TransformKind.REFLECT_ALL_EDGES,
                sprite_width=4.0,
                sprite_height=4.0,
            ),
            partial,
        )
        outside = ReflectionState(-3.0, 100.0, 1.0, 0.0, 2.0, 2)
        reflected = apply_reflection_event(
            outside,
            kind=TransformKind.REFLECT_ALL_EDGES,
            sprite_width=4.0,
            sprite_height=4.0,
        )
        self.assertAlmostEqual(reflected.angle, -math.pi)
        self.assertEqual((reflected.speed, reflected.event_count), (2.0, 1))
        self.assertTrue(reflected.active)

    def test_0x800_bottom_exit_counts_without_reflecting(self) -> None:
        state = ReflectionState(100.0, 451.0, 1.0, 0.75, 2.0, 1)
        result = apply_reflection_event(
            state,
            kind=TransformKind.REFLECT_SIDES_AND_TOP,
            sprite_width=4.0,
            sprite_height=4.0,
        )
        self.assertEqual(result.angle, 0.75)
        self.assertEqual(result.event_count, 1)
        self.assertFalse(result.active)

    def test_countdown_expiration_is_checked_before_decrement(self) -> None:
        self.assertEqual(step_countdown_transform(1), (0, True))
        self.assertEqual(step_countdown_transform(0), (0, False))

    def test_wrap_boundaries_are_strict(self) -> None:
        self.assertEqual(wrap_coordinate(-1.0, vertical=False), 383.0)
        self.assertEqual(wrap_coordinate(384.0, vertical=False), 384.0)
        self.assertEqual(wrap_coordinate(385.0, vertical=False), 1.0)
        self.assertEqual(wrap_coordinate(449.0, vertical=True), 1.0)


if __name__ == "__main__":
    unittest.main()
