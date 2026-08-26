from __future__ import annotations

import struct
import unittest

from th08_runtime.effect_projection import (
    ANM_ACTIVE_SPRITE_INDEX_OFFSET,
    ANM_BASE_SPRITE_INDEX_OFFSET,
    ANM_BEGINNING_OF_SCRIPT_POINTER_OFFSET,
    ANM_CURRENT_INSTRUCTION_POINTER_OFFSET,
    ANM_CURRENT_TIME_OFFSET,
    ANM_FILE_INDEX_OFFSET,
    ANM_FILE_POINTER_OFFSET,
    ANM_FLAGS_OFFSET,
    ANM_INTERRUPT_RETURN_INSTRUCTION_POINTER_OFFSET,
    ANM_INTERRUPT_RETURN_TIMER_OFFSET,
    ANM_LOADED_SPRITE_POINTER_OFFSET,
    ANM_PENDING_INTERRUPT_OFFSET,
    ANM_PLAYER_BULLET_HIT_ANIMATION_TYPE_OFFSET,
    ANM_SCRIPT_INDEX_OFFSET,
    ANM_TYPE_OFFSET,
    ANM_WAIT_TIMER_OFFSET,
    EFFECT_ACTIVE_OFFSET,
    EFFECT_AUXILIARY_ALLOCATION_POINTER_OFFSET,
    EFFECT_CONTROL_BYTES_OFFSET,
    EFFECT_DRAW_CALLBACK_POINTER_OFFSET,
    EFFECT_ID_OFFSET,
    EFFECT_MANAGER_ACTIVE_COUNT_OFFSET,
    EFFECT_MANAGER_BASE,
    EFFECT_MANAGER_CURSOR_OFFSET,
    EFFECT_MANAGER_SCALE_OFFSET,
    EFFECT_MANAGER_SIZE,
    EFFECT_MANAGER_TIMER_OFFSET,
    EFFECT_POOL_OFFSET,
    EFFECT_SLOT_STRIDE,
    EFFECT_TIMER_OFFSET,
    EFFECT_UPDATE_CALLBACK_POINTER_OFFSET,
    EFFECT_VECTOR_BLOCK_OFFSET,
    EFFECT_VECTOR_FLOAT_COUNT,
    capture_effect_lifecycle_projection,
)


class _Reader:
    def __init__(self, manager: bytes, segments: dict[int, bytes]) -> None:
        self._segments = {EFFECT_MANAGER_BASE: manager, **segments}

    def read(self, address: int, size: int) -> bytes:
        for base, data in self._segments.items():
            offset = address - base
            if 0 <= offset and offset + size <= len(data):
                return data[offset : offset + size]
        return b""


def _instruction(*, opcode: int = 79, size: int = 12) -> bytes:
    if size < 8:
        return struct.pack("<hHhH", opcode, size, 10, 0)
    return struct.pack("<hHhH", opcode, size, 10, 0) + bytes(range(size - 8))


def _manager_with_active_effect(
    *,
    pointer_root: int,
    instruction_size: int = 12,
) -> tuple[bytes, dict[int, bytes]]:
    manager = bytearray(EFFECT_MANAGER_SIZE)
    struct.pack_into("<i", manager, EFFECT_MANAGER_CURSOR_OFFSET, 17)
    struct.pack_into("<i", manager, EFFECT_MANAGER_ACTIVE_COUNT_OFFSET, 1)
    struct.pack_into(
        "<4I",
        manager,
        EFFECT_MANAGER_SCALE_OFFSET,
        0x3F800000,
        0x40000000,
        0x40400000,
        0x40800000,
    )
    struct.pack_into("<i", manager, EFFECT_MANAGER_TIMER_OFFSET, 91)

    base = EFFECT_POOL_OFFSET + 12 * EFFECT_SLOT_STRIDE
    manager[base + EFFECT_ACTIVE_OFFSET] = 1
    manager[base + EFFECT_ID_OFFSET] = 38
    manager[base + EFFECT_CONTROL_BYTES_OFFSET : base + EFFECT_CONTROL_BYTES_OFFSET + 6] = (
        b"\x01\x02\x03\x04\x05\x06"
    )
    struct.pack_into("<I", manager, base + EFFECT_UPDATE_CALLBACK_POINTER_OFFSET, 0x401000)
    struct.pack_into("<I", manager, base + EFFECT_DRAW_CALLBACK_POINTER_OFFSET, 0x402000)
    struct.pack_into(
        "<I",
        manager,
        base + EFFECT_AUXILIARY_ALLOCATION_POINTER_OFFSET,
        0x12345000,
    )
    struct.pack_into("<iIi", manager, base + EFFECT_TIMER_OFFSET, 8, 0x3F000000, 9)

    struct.pack_into("<H", manager, base + ANM_FLAGS_OFFSET, 0x2345)
    struct.pack_into("<h", manager, base + ANM_TYPE_OFFSET, -2)
    struct.pack_into("<h", manager, base + ANM_PENDING_INTERRUPT_OFFSET, 3)
    struct.pack_into(
        "<i",
        manager,
        base + ANM_PLAYER_BULLET_HIT_ANIMATION_TYPE_OFFSET,
        44,
    )
    struct.pack_into("<I", manager, base + ANM_FILE_POINTER_OFFSET, pointer_root + 0x8000)
    struct.pack_into("<h", manager, base + ANM_ACTIVE_SPRITE_INDEX_OFFSET, 27)
    struct.pack_into("<h", manager, base + ANM_FILE_INDEX_OFFSET, 6)
    struct.pack_into("<h", manager, base + ANM_BASE_SPRITE_INDEX_OFFSET, 18)
    struct.pack_into("<h", manager, base + ANM_SCRIPT_INDEX_OFFSET, 73)
    struct.pack_into(
        "<I",
        manager,
        base + ANM_BEGINNING_OF_SCRIPT_POINTER_OFFSET,
        pointer_root,
    )
    current_pointer = pointer_root + 0x20
    struct.pack_into(
        "<I",
        manager,
        base + ANM_CURRENT_INSTRUCTION_POINTER_OFFSET,
        current_pointer,
    )
    struct.pack_into(
        "<I", manager, base + ANM_LOADED_SPRITE_POINTER_OFFSET, pointer_root + 0x9000
    )
    struct.pack_into("<iIi", manager, base + ANM_CURRENT_TIME_OFFSET, 10, 0, 11)
    struct.pack_into("<iIi", manager, base + ANM_WAIT_TIMER_OFFSET, 0, 0, 0)
    struct.pack_into(
        "<iIi", manager, base + ANM_INTERRUPT_RETURN_TIMER_OFFSET, 4, 0, 5
    )
    struct.pack_into(
        "<I",
        manager,
        base + ANM_INTERRUPT_RETURN_INSTRUCTION_POINTER_OFFSET,
        pointer_root + 0x10,
    )
    struct.pack_into(
        f"<{EFFECT_VECTOR_FLOAT_COUNT}I",
        manager,
        base + EFFECT_VECTOR_BLOCK_OFFSET,
        *range(EFFECT_VECTOR_FLOAT_COUNT),
    )
    instruction = _instruction(size=instruction_size)
    return bytes(manager), {current_pointer: instruction}


class EffectLifecycleProjectionTests(unittest.TestCase):
    def test_source_scanned_pool_is_decoded_without_raw_pointers(self) -> None:
        manager, segments = _manager_with_active_effect(pointer_root=0x51000000)

        projection = capture_effect_lifecycle_projection(_Reader(manager, segments))

        self.assertEqual(projection.payload["allocator_cursor"], 17)
        self.assertEqual(projection.payload["reported_active_count"], 1)
        self.assertEqual(
            projection.payload["active_effect_ids"],
            [{"effect_id": 38, "count": 1}],
        )
        row = projection.payload["rows"][0]
        self.assertEqual(row["slot"], 12)
        self.assertEqual(row["effect_id"], 38)
        self.assertTrue(row["update_callback_installed"])
        self.assertTrue(row["draw_callback_installed"])
        self.assertTrue(row["allocated_auxiliary_present"])
        self.assertEqual(row["anm"]["flags"], 0x2345)
        self.assertEqual(row["anm"]["type"], -2)
        self.assertEqual(row["anm"]["player_bullet_hit_animation_type"], 44)
        self.assertEqual(
            row["anm"]["current_instruction"]["script_relative_offset"],
            0x20,
        )
        self.assertEqual(row["anm"]["interrupt_return_instruction_offset"], 0x10)
        self.assertEqual(row["vector_bits"], list(range(EFFECT_VECTOR_FLOAT_COUNT)))

    def test_runtime_pointer_relocation_does_not_change_digest(self) -> None:
        left_manager, left_segments = _manager_with_active_effect(
            pointer_root=0x51000000
        )
        right_manager, right_segments = _manager_with_active_effect(
            pointer_root=0xD1000000
        )

        left = capture_effect_lifecycle_projection(
            _Reader(left_manager, left_segments)
        )
        right = capture_effect_lifecycle_projection(
            _Reader(right_manager, right_segments)
        )

        self.assertEqual(left.payload, right.payload)
        self.assertEqual(left.sha256, right.sha256)

    def test_invalid_current_instruction_size_fails_closed(self) -> None:
        manager, segments = _manager_with_active_effect(
            pointer_root=0x51000000,
            instruction_size=4,
        )

        with self.assertRaisesRegex(ValueError, "instruction size 4"):
            capture_effect_lifecycle_projection(_Reader(manager, segments))

    def test_header_only_terminal_instruction_needs_no_zero_byte_read(self) -> None:
        manager, segments = _manager_with_active_effect(
            pointer_root=0x51000000,
            instruction_size=8,
        )

        projection = capture_effect_lifecycle_projection(_Reader(manager, segments))

        instruction = projection.payload["rows"][0]["anm"]["current_instruction"]
        self.assertEqual(instruction["size"], 8)
        self.assertEqual(instruction["payload_hex"], "")


if __name__ == "__main__":
    unittest.main()
