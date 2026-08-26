from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from th08_live.enemy_ecl_inventory import (  # noqa: E402
    ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
    ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT,
    decode_enemy_main_ecl_vm_inventory,
)
from th08_live.enemy_sensor import (  # noqa: E402
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_prefix_contiguous,
)
from th08_runtime_agent import ADDR_ENEMY_MANAGER_FRAME  # noqa: E402


_STRIDE = 0x53D0
_FLAGS = 0x3324
_VM = 0x07F8


def _write_active_record(
    blob: bytearray,
    *,
    slot: int,
    instruction_pointer: int,
    timer_fraction_bits: int,
    timer_elapsed: int,
    auxiliary_context_pointers: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    base = slot * _STRIDE
    struct.pack_into("<I", blob, base + _FLAGS, 0x00000005)
    struct.pack_into("<I", blob, base + _VM, instruction_pointer)
    struct.pack_into("<I", blob, base + _VM + 0x08, timer_fraction_bits)
    struct.pack_into("<i", blob, base + _VM + 0x0C, timer_elapsed)
    struct.pack_into(
        "<8i",
        blob,
        base + _VM + 0x18,
        *range(-4, 4),
    )
    struct.pack_into(
        "<8I",
        blob,
        base + _VM + 0x38,
        *(0x3F800000 + index for index in range(8)),
    )
    struct.pack_into(
        "<4i",
        blob,
        base + _VM + 0x58,
        101,
        102,
        103,
        104,
    )
    struct.pack_into("<2I", blob, base + _VM + 0x68, 201, 202)
    struct.pack_into("<4i", blob, base + _VM + 0x70, -1, 2, 3, 4)
    struct.pack_into("<4I", blob, base + _VM + 0x80, 301, 302, 303, 304)
    struct.pack_into(
        "<4I",
        blob,
        base + ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
        *auxiliary_context_pointers,
    )
    struct.pack_into("<ff", blob, base + 0x2D4C, 1.0, -2.0)
    struct.pack_into("<ff", blob, base + 0x2D70, 8.0, 10.0)
    struct.pack_into("<ff", blob, base + 0x2D88, 100.0 + slot, 200.0)


class _Reader:
    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.reads: list[tuple[int, int]] = []
        self.frame_reads = 0

    def u32(self, address: int) -> int:
        if address != ADDR_ENEMY_MANAGER_FRAME:
            raise AssertionError(f"unexpected u32 address {address:#x}")
        self.frame_reads += 1
        return 900

    def read(self, address: int, size: int) -> bytes:
        self.reads.append((address, size))
        if address != ENEMY_POOL_BASE:
            raise AssertionError(f"unexpected read address {address:#x}")
        return self.blob[:size]


class EnemyEclInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertEqual(ENEMY_STRIDE, _STRIDE)
        self.assertEqual(ENEMY_FLAGS_OFFSET, _FLAGS)
        self.assertEqual(ENEMY_ACTIVE_FLAG, 1)
        self.blob = bytearray(3 * _STRIDE)
        _write_active_record(
            self.blob,
            slot=0,
            instruction_pointer=0x015A1234,
            timer_fraction_bits=0x3E800000,
            timer_elapsed=17,
            auxiliary_context_pointers=(
                0x02100000,
                0,
                0x021024B0,
                0,
            ),
        )
        _write_active_record(
            self.blob,
            slot=1,
            instruction_pointer=0,
            timer_fraction_bits=0x7FC01234,
            timer_elapsed=-9,
            auxiliary_context_pointers=(0, 0xFFFFFFF0, 0, 0),
        )

    def test_independent_raw_layout_oracle_preserves_exact_vm_state(self) -> None:
        times = iter((10.0, 10.00025))
        inventory = decode_enemy_main_ecl_vm_inventory(
            bytes(self.blob),
            pool_base=0x005826C0,
            pool_size=3,
            enemy_stride=_STRIDE,
            enemy_flags_offset=_FLAGS,
            enemy_active_flag=1,
            clock=lambda: next(times),
        )
        self.assertEqual(inventory.scanned_slots, 3)
        self.assertEqual(inventory.active_slots, 2)
        self.assertEqual(len(inventory.observations), 1)
        self.assertEqual(len(inventory.invalid), 1)
        row = inventory.observations[0]
        self.assertEqual(row.slot, 0)
        self.assertEqual(row.enemy_pointer, 0x005826C0)
        self.assertEqual(row.enemy_flags, 5)
        self.assertEqual(row.instruction_pointer, 0x015A1234)
        self.assertEqual(row.timer_fraction_bits, 0x3E800000)
        self.assertEqual(row.timer_elapsed, 17)
        self.assertEqual(row.local_projection.integer_locals, tuple(range(-4, 4)))
        self.assertEqual(
            row.local_projection.float_local_bits,
            tuple(0x3F800000 + index for index in range(8)),
        )
        self.assertEqual(
            row.local_projection.scratch_integers,
            (101, 102, 103, 104),
        )
        self.assertEqual(
            row.local_projection.spawn_float_parameter_bits,
            (201, 202),
        )
        self.assertEqual(
            row.local_projection.call_integer_parameters,
            (-1, 2, 3, 4),
        )
        self.assertEqual(
            row.local_projection.call_float_parameter_bits,
            (301, 302, 303, 304),
        )
        self.assertEqual(inventory.invalid[0].slot, 1)
        self.assertEqual(inventory.invalid[0].instruction_pointer, 0)
        self.assertEqual(len(inventory.auxiliary_contexts), 2)
        self.assertEqual(
            inventory.auxiliary_contexts[0].context_pointers,
            (0x02100000, 0, 0x021024B0, 0),
        )
        self.assertEqual(
            inventory.auxiliary_contexts[1].context_pointers,
            (0, 0xFFFFFFF0, 0, 0),
        )
        self.assertEqual(len(inventory.invalid_auxiliary_contexts), 1)
        self.assertEqual(
            inventory.invalid_auxiliary_contexts[0].record(),
            [1, 0x005826C0 + _STRIDE, 1, 0xFFFFFFF0],
        )
        self.assertAlmostEqual(inventory.decode_ms, 0.25)

    def test_compact_record_is_deterministic_and_versioned(self) -> None:
        times = iter((1.0, 1.0))
        inventory = decode_enemy_main_ecl_vm_inventory(
            bytes(self.blob),
            pool_base=ENEMY_POOL_BASE,
            pool_size=3,
            enemy_stride=ENEMY_STRIDE,
            enemy_flags_offset=ENEMY_FLAGS_OFFSET,
            enemy_active_flag=ENEMY_ACTIVE_FLAG,
            clock=lambda: next(times),
        )
        record = inventory.record()
        self.assertEqual(
            record["layout"],
            ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT,
        )
        self.assertEqual(record["active_slots"], 2)
        self.assertEqual(record["valid_vms"], 1)
        self.assertEqual(record["invalid_active_vms"], 1)
        self.assertEqual(record["non_null_auxiliary_contexts"], 3)
        self.assertEqual(record["invalid_auxiliary_contexts"], 1)
        self.assertEqual(len(record["auxiliary_context_rows"]), 2)
        self.assertEqual(len(record["rows"][0]), 12)
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
        self.assertEqual(encoded, json.dumps(record, sort_keys=True, separators=(",", ":")))
        self.assertNotIn("instruction_pointer", encoded)

    def test_main_only_capture_keeps_current_vm_schema(self) -> None:
        auxiliary = decode_enemy_main_ecl_vm_inventory(
            bytes(self.blob),
            pool_base=ENEMY_POOL_BASE,
            pool_size=3,
            enemy_stride=ENEMY_STRIDE,
            enemy_flags_offset=ENEMY_FLAGS_OFFSET,
            enemy_active_flag=ENEMY_ACTIVE_FLAG,
        )
        baseline = decode_enemy_main_ecl_vm_inventory(
            bytes(self.blob),
            pool_base=ENEMY_POOL_BASE,
            pool_size=3,
            enemy_stride=ENEMY_STRIDE,
            enemy_flags_offset=ENEMY_FLAGS_OFFSET,
            enemy_active_flag=ENEMY_ACTIVE_FLAG,
            include_auxiliary_context_pointers=False,
        )
        self.assertEqual(auxiliary.observations, baseline.observations)
        record = baseline.record()
        self.assertEqual(
            record["layout"],
            ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT,
        )
        self.assertEqual(len(record["rows"][0]), 12)
        self.assertFalse(record["auxiliary_pointer_coverage"])
        self.assertNotIn("auxiliary_context_rows", record)
        self.assertFalse(baseline.auxiliary_pointer_coverage)

    def test_exact_ecl_bounds_admit_a_high_linux_runtime_mapping(self) -> None:
        blob = bytearray(_STRIDE)
        _write_active_record(
            blob,
            slot=0,
            instruction_pointer=0xD7553B68,
            timer_fraction_bits=0,
            timer_elapsed=7,
            auxiliary_context_pointers=(0xD7001000, 0, 0, 0),
        )

        inventory = decode_enemy_main_ecl_vm_inventory(
            bytes(blob),
            pool_base=ENEMY_POOL_BASE,
            pool_size=1,
            enemy_stride=ENEMY_STRIDE,
            enemy_flags_offset=ENEMY_FLAGS_OFFSET,
            enemy_active_flag=ENEMY_ACTIVE_FLAG,
            runtime_instruction_bounds=(0xD75532B0, 0xD755EB28),
            maximum_runtime_address=0xFFFFFFFF,
        )

        self.assertEqual(len(inventory.observations), 1)
        self.assertEqual(inventory.invalid, ())
        self.assertEqual(inventory.invalid_auxiliary_contexts, ())
        self.assertEqual(
            inventory.observations[0].instruction_pointer,
            0xD7553B68,
        )

    def test_exact_ecl_bounds_reject_high_pointer_outside_image(self) -> None:
        blob = bytearray(_STRIDE)
        _write_active_record(
            blob,
            slot=0,
            instruction_pointer=0xD7560000,
            timer_fraction_bits=0,
            timer_elapsed=7,
        )

        inventory = decode_enemy_main_ecl_vm_inventory(
            bytes(blob),
            pool_base=ENEMY_POOL_BASE,
            pool_size=1,
            enemy_stride=ENEMY_STRIDE,
            enemy_flags_offset=ENEMY_FLAGS_OFFSET,
            enemy_active_flag=ENEMY_ACTIVE_FLAG,
            runtime_instruction_bounds=(0xD75532B0, 0xD755EB28),
            maximum_runtime_address=0xFFFFFFFF,
        )

        self.assertEqual(inventory.observations, ())
        self.assertEqual(len(inventory.invalid), 1)

    def test_capture_reuses_one_blob_and_preserves_body_parity(self) -> None:
        plain_reader = _Reader(bytes(self.blob))
        traced_reader = _Reader(bytes(self.blob))
        plain = capture_enemy_pool_prefix_contiguous(
            plain_reader,
            pool_size=3,
        )
        traced = capture_enemy_pool_prefix_contiguous(
            traced_reader,
            pool_size=3,
            include_main_ecl_vms=True,
        )
        self.assertEqual(plain.bodies, traced.bodies)
        self.assertIsNone(plain.main_ecl_vm_inventory)
        self.assertIsNotNone(traced.main_ecl_vm_inventory)
        self.assertEqual(
            plain_reader.reads,
            [(ENEMY_POOL_BASE, 3 * ENEMY_STRIDE)],
        )
        self.assertEqual(traced_reader.reads, plain_reader.reads)
        self.assertEqual(plain_reader.frame_reads, 2)
        self.assertEqual(traced_reader.frame_reads, 2)
        self.assertEqual(
            traced.main_ecl_vm_inventory.active_slots,
            2,
        )

    def test_truncated_blob_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires"):
            decode_enemy_main_ecl_vm_inventory(
                bytes(self.blob[:-1]),
                pool_base=ENEMY_POOL_BASE,
                pool_size=3,
                enemy_stride=ENEMY_STRIDE,
                enemy_flags_offset=ENEMY_FLAGS_OFFSET,
                enemy_active_flag=ENEMY_ACTIVE_FLAG,
            )


if __name__ == "__main__":
    unittest.main()
