from __future__ import annotations

import struct
import unittest

from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_CONTACT_ENABLED_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POSITION_OFFSET,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_snapshot_contiguous,
    merge_enemy_pool_prefix,
)


def _pool_blob(*active_slots: int, pool_size: int = 4) -> bytes:
    blob = bytearray(pool_size * ENEMY_STRIDE)
    for slot in active_slots:
        offset = slot * ENEMY_STRIDE
        struct.pack_into(
            "<I",
            blob,
            offset + ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG | ENEMY_CONTACT_ENABLED_FLAG,
        )
        struct.pack_into(
            "<ff",
            blob,
            offset + ENEMY_POSITION_OFFSET,
            float(slot),
            100.0 + slot,
        )
    return bytes(blob)


class _Reader:
    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.frames = iter((100, 100))
        self.read_into_events: list[tuple[int, int]] = []

    def u32(self, _address: int) -> int:
        return next(self.frames)

    def read(self, _address: int, _size: int) -> bytes:
        raise AssertionError("persistent capture must not allocate")

    def read_into(self, address: int, destination: bytearray) -> bytearray:
        self.read_into_events.append((address, len(destination)))
        destination[:] = self.blob
        return destination


class SourceContiguousEnemyPoolTests(unittest.TestCase):
    def test_slot_zero_rooted_capture_reads_one_complete_contiguous_range(
        self,
    ) -> None:
        blob = _pool_blob(0, 3)
        reader = _Reader(blob)
        destination = bytearray(len(blob))

        snapshot = capture_enemy_pool_snapshot_contiguous(
            reader,
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=4,
            pool_buffer=destination,
        )

        self.assertTrue(snapshot.stable)
        self.assertEqual(
            reader.read_into_events,
            [(ENEMY_SLOT_ZERO_BASE, 4 * ENEMY_STRIDE)],
        )
        self.assertEqual(
            [body.pointer for body in snapshot.bodies],
            [
                ENEMY_SLOT_ZERO_BASE,
                ENEMY_SLOT_ZERO_BASE + 3 * ENEMY_STRIDE,
            ],
        )

    def test_slot_zero_prefix_replaces_only_its_source_range(self) -> None:
        prefix_blob = _pool_blob(0, pool_size=2)
        prefix = capture_enemy_pool_snapshot_contiguous(
            _Reader(prefix_blob),
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=2,
            pool_buffer=bytearray(len(prefix_blob)),
        ).bodies
        tail_blob = _pool_blob(2, pool_size=4)
        background = capture_enemy_pool_snapshot_contiguous(
            _Reader(tail_blob),
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=4,
            pool_buffer=bytearray(len(tail_blob)),
        ).bodies

        merged = merge_enemy_pool_prefix(
            background,
            prefix,
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=2,
        )

        self.assertEqual(
            [body.pointer for body in merged],
            [
                ENEMY_SLOT_ZERO_BASE,
                ENEMY_SLOT_ZERO_BASE + 2 * ENEMY_STRIDE,
            ],
        )

    def test_reusable_buffer_must_match_requested_source_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly match"):
            capture_enemy_pool_snapshot_contiguous(
                object(),
                pool_base=ENEMY_SLOT_ZERO_BASE,
                pool_size=4,
                pool_buffer=bytearray(1),
            )


if __name__ == "__main__":
    unittest.main()
