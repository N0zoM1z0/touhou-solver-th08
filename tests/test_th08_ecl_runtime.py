#!/usr/bin/env python3
"""Regression tests for TH08 live ECL callback lookahead."""

from __future__ import annotations

import math
import struct
import unittest
from pathlib import Path

from th08_ecl_runtime import (
    ECL_VM_CALLBACK_ANGLE_OFFSET,
    ECL_VM_CALLBACK_SPEED_OFFSET,
    ECL_VM_SNAPSHOT_SIZE,
    ECL_VM_TAG_MASK_OFFSET,
    ECL_VM_TIMER_ELAPSED_OFFSET,
    ECL_VM_TIMER_FRACTION_OFFSET,
    ENEMY_MAIN_ECL_VM_OFFSET,
    GAMEPLAY_TIME_SCALE_ADDRESS,
    ECL_OP_FIRST_CONDITIONAL_JUMP,
    ECL_OP_INVOKE_CALLBACK,
    ECL_OP_JUMP,
    ECL_OP_LOOP_DECREMENT_JUMP,
    ECL_OP_SET_INT,
    ECL_OP_TERMINATE,
    EclInstructionCache,
    EclVmSnapshot,
    IncompleteEclLookaheadError,
    TaggedVelocityToggle,
    analyze_tagged_velocity_toggles,
    predict_tagged_velocity_toggles,
    read_main_ecl_vm_snapshot,
    trajectory_changes_for_tagged_bullet,
    velocity_changes_for_tagged_bullet,
)
from th08_ecl_vm_state import EclVmLocalProjection


def _instruction(
    time: int,
    opcode: int,
    *arguments: int,
    parameter_mask: int = 0,
) -> bytes:
    size = 12 + 4 * len(arguments)
    return struct.pack(
        "<iHHBBH",
        time,
        opcode,
        size,
        0,
        0xFF,
        parameter_mask,
    ) + struct.pack(f"<{len(arguments)}i", *arguments)


class _Memory:
    def __init__(self, chunks: dict[int, bytes]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[int, int]] = []

    def read(self, address: int, size: int) -> bytes:
        self.calls.append((address, size))
        if size <= 0:
            raise ValueError("process read buffer size must be positive")
        for base, data in self.chunks.items():
            if base <= address and address + size <= base + len(data):
                start = address - base
                return data[start : start + size]
        raise OSError(f"unmapped test address {address:#x}")


class EclRuntimeTests(unittest.TestCase):
    def test_cached_instruction_never_performs_a_cold_read(self) -> None:
        address = 0x410000
        memory = _Memory({address: _instruction(0, ECL_OP_TERMINATE)})
        cache = EclInstructionCache()
        with self.assertRaisesRegex(RuntimeError, "absent from the warm cache"):
            cache.cached_instruction(address)
        decoded = cache.instruction(memory.read, address)
        self.assertIs(cache.cached_instruction(address), decoded)

    def test_reads_native_main_vm_timer_at_plus_04_08_0c(self) -> None:
        enemy = 0x580000
        vm = bytearray(ECL_VM_SNAPSHOT_SIZE)
        struct.pack_into("<I", vm, 0, 0x0B1D6FCC)
        struct.pack_into("<i", vm, 0x04, 199)
        struct.pack_into("<f", vm, ECL_VM_TIMER_FRACTION_OFFSET, 0.25)
        struct.pack_into("<i", vm, ECL_VM_TIMER_ELAPSED_OFFSET, 200)
        struct.pack_into("<I", vm, ECL_VM_TAG_MASK_OFFSET, 0x100000)
        struct.pack_into(
            "<f",
            vm,
            ECL_VM_CALLBACK_ANGLE_OFFSET,
            math.pi / 4,
        )
        struct.pack_into(
            "<f",
            vm,
            ECL_VM_CALLBACK_SPEED_OFFSET,
            1.5,
        )
        struct.pack_into("<4i", vm, 0x58, 9, 8, 7, 6)
        memory = _Memory(
            {
                enemy + ENEMY_MAIN_ECL_VM_OFFSET: bytes(vm),
                GAMEPLAY_TIME_SCALE_ADDRESS: struct.pack("<f", 1.0),
            }
        )
        snapshot = read_main_ecl_vm_snapshot(memory, enemy)
        self.assertEqual(snapshot.instruction_pointer, 0x0B1D6FCC)
        self.assertEqual(snapshot.timer_elapsed, 200)
        self.assertAlmostEqual(snapshot.timer_fraction, 0.25)
        self.assertEqual(snapshot.tag_mask, 0x100000)
        self.assertAlmostEqual(snapshot.callback_speed, 1.5)
        self.assertIsNotNone(snapshot.local_projection)
        assert snapshot.local_projection is not None
        self.assertEqual(
            snapshot.local_projection.scratch_integers,
            (9, 8, 7, 6),
        )
        self.assertEqual(
            memory.calls,
            [
                (
                    enemy + ENEMY_MAIN_ECL_VM_OFFSET,
                    ECL_VM_SNAPSHOT_SIZE,
                ),
                (GAMEPLAY_TIME_SCALE_ADDRESS, 4),
            ],
        )
        self.assertEqual(ECL_VM_SNAPSHOT_SIZE, 0x90)
        self.assertTrue(
            snapshot.local_projection.copied_parameter_block_complete
        )

    def test_snapshot_rejects_projection_compatibility_mismatch(self) -> None:
        vm = bytearray(ECL_VM_SNAPSHOT_SIZE)
        struct.pack_into("<i", vm, ECL_VM_TAG_MASK_OFFSET, 7)
        projection = EclVmLocalProjection.from_vm_bytes(vm)
        with self.assertRaisesRegex(ValueError, "tag mask"):
            EclVmSnapshot(
                0x500000,
                0.0,
                1,
                8,
                0.0,
                0.0,
                1.0,
                projection,
            )

    def test_projection_does_not_change_lookahead_authority(self) -> None:
        base = 0x590000
        memory = _Memory({base: _instruction(10, ECL_OP_TERMINATE)})
        cache = EclInstructionCache()
        plain = EclVmSnapshot(base, 0.0, 0, 0x10, 0.0, 0.0, 1.0)
        projection = EclVmLocalProjection(
            (0x10, 1, 2, 3, 4, 5, 6, 7),
            (0, 0, 2, 3, 4, 5, 6, 7),
            (9, 8, 7, 6),
        )
        projected = EclVmSnapshot(
            base,
            0.0,
            0,
            0x10,
            0.0,
            0.0,
            1.0,
            projection,
        )

        def analyze(snapshot: EclVmSnapshot):
            return analyze_tagged_velocity_toggles(
                snapshot,
                instruction_at=lambda address: cache.instruction(
                    memory.read,
                    address,
                ),
                horizon_frames=20,
                active_difficulty_mask=0x08,
            )

        self.assertEqual(analyze(projected), analyze(plain))

    def test_predicts_literal_callback_after_current_timer(self) -> None:
        base = 0x500000
        code = b"".join(
            (
                _instruction(
                    450,
                    ECL_OP_SET_INT,
                    10000,
                    0x100000,
                    parameter_mask=1,
                ),
                _instruction(450, ECL_OP_INVOKE_CALLBACK, 12, 0),
                _instruction(451, ECL_OP_TERMINATE),
            )
        )
        memory = _Memory({base: code})
        cache = EclInstructionCache()
        snapshot = EclVmSnapshot(
            base,
            0.0,
            351,
            0,
            math.pi,
            0.0,
            1.0,
        )
        events = predict_tagged_velocity_toggles(
            snapshot,
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=120,
            active_difficulty_mask=0x08,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].frame, events[0].tag_mask), (99, 0x100000))
        self.assertAlmostEqual(events[0].alternate_velocity_x, 0.0)
        self.assertAlmostEqual(events[0].alternate_velocity_y, 0.0)

    def test_literal_jump_preserves_periodic_callback_timing(self) -> None:
        callback_address = 0x600000
        jump_address = callback_address + 0x100
        relative = callback_address - jump_address
        memory = _Memory(
            {
                callback_address: b"".join(
                    (
                        _instruction(
                            350,
                            ECL_OP_INVOKE_CALLBACK,
                            12,
                            0,
                        ),
                        _instruction(351, ECL_OP_TERMINATE),
                    )
                ),
                jump_address: _instruction(
                    710,
                    ECL_OP_JUMP,
                    350,
                    relative,
                ),
            }
        )
        cache = EclInstructionCache()
        snapshot = EclVmSnapshot(
            jump_address,
            0.0,
            650,
            0x100000,
            0.0,
            0.0,
            1.0,
        )
        events = predict_tagged_velocity_toggles(
            snapshot,
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=80,
            active_difficulty_mask=0x08,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].frame, 60)

    def test_jump_preserves_nonzero_fraction_for_successor_timing(self) -> None:
        jump_address = 0x610000
        callback_address = jump_address + 0x80
        memory = _Memory(
            {
                jump_address: _instruction(
                    0,
                    ECL_OP_JUMP,
                    3,
                    callback_address - jump_address,
                ),
                callback_address: b"".join(
                    (
                        _instruction(
                            4,
                            ECL_OP_INVOKE_CALLBACK,
                            12,
                            0,
                        ),
                        _instruction(4, ECL_OP_TERMINATE),
                    )
                ),
            }
        )
        cache = EclInstructionCache()
        result = analyze_tagged_velocity_toggles(
            EclVmSnapshot(
                jump_address,
                0.5,
                0,
                0x100000,
                0.0,
                0.0,
                0.75,
            ),
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=3,
            active_difficulty_mask=0x08,
        )
        self.assertEqual(result.stop_reason, "terminate")
        self.assertEqual([event.frame for event in result.events], [1])
        self.assertIn("native-timer-components", result.semantics_version)
        self.assertIn("native-timer-components", result.timer_semantics_version)

    def test_past_instruction_time_is_not_executed_as_eligible(self) -> None:
        base = 0x620000
        memory = _Memory(
            {
                base: _instruction(
                    4,
                    ECL_OP_INVOKE_CALLBACK,
                    12,
                    0,
                )
            }
        )
        cache = EclInstructionCache()
        result = analyze_tagged_velocity_toggles(
            EclVmSnapshot(
                base,
                0.0,
                5,
                0x100000,
                0.0,
                0.0,
                1.0,
            ),
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=3,
            active_difficulty_mask=0x08,
        )
        self.assertEqual(result.stop_reason, "horizon")
        self.assertEqual(result.stop_frame, 3)
        self.assertEqual(result.events, ())

    def test_real_spell111_sub63_loop_predicts_stop_and_resume(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "decoded"
            / "ecldata5.ecl"
        )
        code = path.read_bytes()
        base = 0x500000
        memory = _Memory({base: code})
        cache = EclInstructionCache()
        snapshot = EclVmSnapshot(
            base + 0x6FE8,
            0.0,
            600,
            0x100000,
            2.356194,
            0.0,
            1.0,
        )
        result = analyze_tagged_velocity_toggles(
            snapshot,
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=256,
            active_difficulty_mask=0x08,
        )
        self.assertEqual(
            [(event.frame, event.tag_mask) for event in result.events],
            [(110, 0x100000), (210, 0x100000)],
        )
        self.assertEqual(result.stop_reason, "horizon")
        self.assertTrue(result.horizon_covered)

    def test_unobserved_control_successor_stops_before_false_completion(
        self,
    ) -> None:
        base = 0x680000
        callback = _instruction(
            0,
            ECL_OP_INVOKE_CALLBACK,
            12,
            0,
        )
        for opcode, arguments in (
            (
                ECL_OP_LOOP_DECREMENT_JUMP,
                (0, 36, 10000),
            ),
            (
                ECL_OP_FIRST_CONDITIONAL_JUMP,
                (10000, 1, 0, 40),
            ),
        ):
            with self.subTest(opcode=opcode):
                branch = _instruction(
                    0,
                    opcode,
                    *arguments,
                    parameter_mask=1,
                )
                memory = _Memory(
                    {
                        base: branch + _instruction(10, ECL_OP_TERMINATE) + callback,
                    }
                )
                cache = EclInstructionCache()
                snapshot = EclVmSnapshot(
                    base,
                    0.0,
                    0,
                    0x100000,
                    0.0,
                    0.0,
                    1.0,
                )
                result = analyze_tagged_velocity_toggles(
                    snapshot,
                    instruction_at=lambda address: cache.instruction(
                        memory.read,
                        address,
                    ),
                    horizon_frames=5,
                    active_difficulty_mask=0x08,
                )
                self.assertEqual(
                    result.stop_reason,
                    "unsupported_control_flow",
                )
                self.assertEqual(result.instructions_scanned, 1)
                self.assertEqual(result.coverage_status, "unknown")
                self.assertEqual(result.events, ())
                self.assertIsNone(result.complete_events)

    def test_shipped_stage4_loops_stop_at_first_unobserved_control(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "decoded"
            / "ecldata4asp.ecl"
        )
        code = path.read_bytes()
        base = 0x500000
        memory = _Memory({base: code})
        snapshots = (
            ("spell57", base + 0x331C, 32, 64),
            ("spell73", base + 0x70DC, 319, 16),
        )
        for name, pc, timer, instruction_limit in snapshots:
            with self.subTest(name=name):
                cache = EclInstructionCache()
                result = analyze_tagged_velocity_toggles(
                    EclVmSnapshot(
                        pc,
                        0.0,
                        timer,
                        0x10,
                        0.0,
                        0.0,
                        1.0,
                    ),
                    instruction_at=lambda address: cache.instruction(
                        memory.read,
                        address,
                    ),
                    horizon_frames=256,
                    active_difficulty_mask=0x08,
                )
                self.assertEqual(
                    result.stop_reason,
                    "unsupported_control_flow",
                )
                self.assertLess(
                    result.instructions_scanned,
                    instruction_limit,
                )
                self.assertEqual(result.coverage_status, "unknown")
                self.assertIsNone(result.complete_events)

    def test_callback_toggle_lowers_to_stop_then_original_velocity(self) -> None:
        snapshot = EclVmSnapshot(
            0x500000,
            0.0,
            0,
            0x100000,
            0.0,
            0.0,
            1.0,
        )
        changes = velocity_changes_for_tagged_bullet(
            tag_flags=0x100202,
            phase_state=1,
            base_speed=2.0,
            base_angle=math.pi / 2,
            time_scale=snapshot.time_scale,
            toggles=(
                TaggedVelocityToggle(10, 12, 0x100000, 0.0, 0.0),
                TaggedVelocityToggle(110, 12, 0x100000, 0.0, 0.0),
            ),
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(
            (changes[0].frame, changes[0].velocity_x, changes[0].velocity_y),
            (10, 0.0, 0.0),
        )
        self.assertEqual(changes[1].frame, 110)
        self.assertAlmostEqual(changes[1].velocity_x, 0.0, places=6)
        self.assertAlmostEqual(changes[1].velocity_y, 2.0)

        trajectory_changes = trajectory_changes_for_tagged_bullet(
            tag_flags=0x100202,
            phase_state=1,
            base_speed=2.0,
            base_angle=math.pi / 2,
            time_scale=snapshot.time_scale,
            toggles=(
                TaggedVelocityToggle(10, 12, 0x100000, 0.0, 0.0),
                TaggedVelocityToggle(110, 12, 0x100000, 0.0, 0.0),
            ),
        )
        self.assertEqual(
            [
                (change.frame, change.collision_enabled)
                for change in trajectory_changes.collision_changes
            ],
            [(10, False), (110, True)],
        )

    def test_instruction_limit_prefix_cannot_be_consumed_as_complete(self) -> None:
        base = 0x700000
        code = _instruction(
            1,
            ECL_OP_INVOKE_CALLBACK,
            12,
            0,
        )
        memory = _Memory({base: code})
        snapshot = EclVmSnapshot(
            base,
            0.0,
            0,
            0x100000,
            0.0,
            0.0,
            1.0,
        )
        cache = EclInstructionCache()
        result = analyze_tagged_velocity_toggles(
            snapshot,
            instruction_at=lambda address: cache.instruction(
                memory.read,
                address,
            ),
            horizon_frames=5,
            active_difficulty_mask=0x08,
            max_instructions=1,
        )
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.coverage_status, "unknown")
        self.assertEqual(result.stop_frame, 1)
        self.assertEqual(result.covered_through_frame, 0)
        self.assertEqual(result.unknown_from_frame, 1)
        self.assertIsNone(result.complete_events)
        with self.assertRaises(IncompleteEclLookaheadError):
            result.require_complete_events()
        with self.assertRaises(IncompleteEclLookaheadError):
            predict_tagged_velocity_toggles(
                snapshot,
                instruction_at=lambda address: cache.instruction(
                    memory.read,
                    address,
                ),
                horizon_frames=5,
                active_difficulty_mask=0x08,
                max_instructions=1,
            )


if __name__ == "__main__":
    unittest.main()
