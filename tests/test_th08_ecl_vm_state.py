#!/usr/bin/env python3
"""Tests for the capture-aligned TH08 ECL VM-local projection."""

from __future__ import annotations

import math
import struct
import unittest

from th08_ecl_vm_state import (
    ECL_VM_CALL_FLOAT_PARAMETERS_OFFSET,
    ECL_VM_CALL_INTEGER_PARAMETERS_OFFSET,
    ECL_VM_FLOAT_LOCALS_OFFSET,
    ECL_VM_INTEGER_LOCALS_OFFSET,
    ECL_VM_LEGACY_LOCAL_PROJECTION_SIZE,
    ECL_VM_LOCAL_PROJECTION_LAYOUT,
    ECL_VM_LOCAL_PROJECTION_LAYOUT_V1,
    ECL_VM_LOCAL_PROJECTION_SIZE,
    ECL_VM_SCRATCH_INTEGERS_OFFSET,
    ECL_VM_SPAWN_FLOAT_PARAMETERS_OFFSET,
    EclVmLocalProjection,
    float32_bits,
    float32_from_bits,
)


class EclVmStateTests(unittest.TestCase):
    def test_decodes_fixed_local_ranges_without_normalizing_float_bits(
        self,
    ) -> None:
        vm = bytearray(ECL_VM_LOCAL_PROJECTION_SIZE)
        integer_locals = (-1, 2, 3, 4, 5, 6, 7, -(1 << 31))
        float_bits = (
            0x80000000,
            0x7FC12345,
            0x7F800000,
            0xFF800000,
            0x00000001,
            0x3F800000,
            0x40490FDB,
            0xFFFFFFFF,
        )
        scratch_integers = (0, 1, 2, (1 << 31) - 1)
        struct.pack_into(
            "<8i",
            vm,
            ECL_VM_INTEGER_LOCALS_OFFSET,
            *integer_locals,
        )
        struct.pack_into(
            "<8I",
            vm,
            ECL_VM_FLOAT_LOCALS_OFFSET,
            *float_bits,
        )
        struct.pack_into(
            "<4i",
            vm,
            ECL_VM_SCRATCH_INTEGERS_OFFSET,
            *scratch_integers,
        )
        struct.pack_into(
            "<2I",
            vm,
            ECL_VM_SPAWN_FLOAT_PARAMETERS_OFFSET,
            float32_bits(12.5),
            float32_bits(-3.0),
        )
        struct.pack_into(
            "<4i",
            vm,
            ECL_VM_CALL_INTEGER_PARAMETERS_OFFSET,
            -7,
            8,
            9,
            10,
        )
        struct.pack_into(
            "<4I",
            vm,
            ECL_VM_CALL_FLOAT_PARAMETERS_OFFSET,
            *(float32_bits(value) for value in (1.0, 2.0, 3.0, 4.0)),
        )

        projection = EclVmLocalProjection.from_vm_bytes(bytes(vm))

        self.assertEqual(projection.integer_locals, integer_locals)
        self.assertEqual(projection.float_local_bits, float_bits)
        self.assertEqual(projection.scratch_integers, scratch_integers)
        self.assertEqual(projection.integer_value(10000), -1)
        self.assertEqual(projection.integer_value(10039), (1 << 31) - 1)
        self.assertIsNone(projection.integer_value(10008))
        self.assertEqual(projection.float_bits_value(10017), 0x7FC12345)
        self.assertEqual(projection.float_value(10094), 12.5)
        self.assertEqual(projection.integer_value(10053), -7)
        self.assertEqual(projection.float_value(10060), 4.0)
        self.assertIsNone(projection.float_bits_value(10024))
        self.assertTrue(math.isnan(projection.float_value(10017)))

    def test_trace_record_is_versioned_and_uses_fixed_arrays(self) -> None:
        projection = EclVmLocalProjection(
            tuple(range(8)),
            tuple(range(8)),
            tuple(range(4)),
            (10, 11),
            (12, 13, 14, 15),
            (16, 17, 18, 19),
        )

        self.assertEqual(
            projection.trace_record(),
            {
                "layout": ECL_VM_LOCAL_PROJECTION_LAYOUT,
                "capture_bytes": 0x90,
                "integer_locals": list(range(8)),
                "float_local_bits": list(range(8)),
                "scratch_integers": list(range(4)),
                "spawn_float_parameter_bits": [10, 11],
                "call_integer_parameters": [12, 13, 14, 15],
                "call_float_parameter_bits": [16, 17, 18, 19],
            },
        )

    def test_legacy_projection_remains_explicitly_readable(self) -> None:
        projection = EclVmLocalProjection.from_vm_bytes(
            b"\0" * ECL_VM_LEGACY_LOCAL_PROJECTION_SIZE
        )

        self.assertFalse(projection.copied_parameter_block_complete)
        self.assertEqual(
            projection.trace_record()["layout"],
            ECL_VM_LOCAL_PROJECTION_LAYOUT_V1,
        )
        self.assertEqual(projection.trace_record()["capture_bytes"], 0x68)
        self.assertIsNone(projection.float_value(10094))

    def test_rejects_short_or_out_of_range_projections(self) -> None:
        with self.assertRaisesRegex(ValueError, "shorter"):
            EclVmLocalProjection.from_vm_bytes(b"\x00" * 0x67)
        with self.assertRaisesRegex(ValueError, "eight"):
            EclVmLocalProjection((), tuple(range(8)), tuple(range(4)))
        with self.assertRaisesRegex(ValueError, "uint32"):
            EclVmLocalProjection(
                tuple(range(8)),
                (0, 1, 2, 3, 4, 5, 6, 1 << 32),
                tuple(range(4)),
            )

    def test_float_helpers_preserve_signed_zero_and_raw_nonfinite_bits(
        self,
    ) -> None:
        self.assertEqual(float32_bits(-0.0), 0x80000000)
        self.assertTrue(math.isnan(float32_from_bits(0x7FC12345)))
        with self.assertRaisesRegex(ValueError, "uint32"):
            float32_from_bits(-1)


if __name__ == "__main__":
    unittest.main()
