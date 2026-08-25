from __future__ import annotations

import struct
import unittest
from unittest.mock import patch

from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_runtime.ordinary_future_source_capture import (
    OrdinaryFutureSourceSnapshot,
    capture_ordinary_future_source_snapshot,
    _read_active_enemy_records,
    _read_current_hazard_pools,
)
from th08_live.sensor import (
    BULLET_POOL_BASE,
    BULLET_POOL_SIZE,
    BULLET_STRIDE,
    LASER_POOL_BASE,
    LASER_POOL_SIZE,
    LASER_STRIDE,
)


class _Reader:
    def __init__(self, slab: bytes) -> None:
        self.slab = slab
        self.reads: list[tuple[int, int]] = []

    def read(self, address: int, size: int) -> bytes:
        self.reads.append((address, size))
        return self.slab

    def u32(self, _address: int) -> int:
        raise AssertionError("the coherent enemy slab must not use sparse reads")


class _IntoReader(_Reader):
    def __init__(self, slab: bytes) -> None:
        super().__init__(slab)
        self.into_reads: list[tuple[int, int]] = []

    @staticmethod
    def allocate_buffer(size: int) -> bytearray:
        return bytearray(size)

    def read_into(self, address: int, buffer: bytearray) -> bytearray:
        self.into_reads.append((address, len(buffer)))
        buffer[:] = self.slab
        return buffer

    def read(self, _address: int, _size: int) -> bytes:
        raise AssertionError("persistent capture must use read_into")


class _PoolIntoReader:
    def __init__(self) -> None:
        self.into_reads: list[tuple[int, int]] = []

    def read_into(self, address: int, buffer: bytearray) -> bytearray:
        self.into_reads.append((address, len(buffer)))
        return buffer

    def read(self, _address: int, _size: int) -> bytes:
        raise AssertionError("persistent hazard capture must use read_into")


class _ClockReader:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.serial_values = iter((20, 21, 22, 22))
        self.frame_values = iter((10, 11, 12, 12))

    def u32(self, address: int) -> int:
        from th08_runtime.game_state import (
            ADDR_ENEMY_MANAGER_FRAME,
            ADDR_FRSCREEN_UPDATE_SERIAL,
        )

        if address == ADDR_FRSCREEN_UPDATE_SERIAL:
            value = next(self.serial_values)
            self.events.append(f"serial:{value}")
            return value
        if address == ADDR_ENEMY_MANAGER_FRAME:
            value = next(self.frame_values)
            self.events.append(f"frame:{value}")
            return value
        raise AssertionError(f"unexpected clock address {address:#x}")


class OrdinaryFutureSourceCaptureTests(unittest.TestCase):
    def test_snapshot_requires_both_manager_and_player_clock_stability(self) -> None:
        stable = OrdinaryFutureSourceSnapshot(
            frame_before=10,
            frame_after=10,
            update_serial_before=20,
            update_serial_after=20,
            payload={},
            read_ms=1.0,
            attempts=1,
        )
        crossed_player = OrdinaryFutureSourceSnapshot(
            frame_before=10,
            frame_after=10,
            update_serial_before=20,
            update_serial_after=21,
            payload={},
            read_ms=1.0,
            attempts=1,
        )

        self.assertTrue(stable.stable)
        self.assertFalse(crossed_player.stable)

    def test_manager_and_pool_use_one_contiguous_versioned_read(self) -> None:
        slab = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        struct.pack_into(
            "<I",
            slab,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        active_slot = 479
        struct.pack_into(
            "<I",
            slab,
            (active_slot + 1) * ENEMY_STRIDE + ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        reader = _Reader(bytes(slab))

        manager, ordinary, active_count = _read_active_enemy_records(reader)

        self.assertEqual(len(manager), ENEMY_STRIDE)
        self.assertEqual(len(ordinary), ENEMY_POOL_SIZE * ENEMY_STRIDE)
        self.assertEqual(active_count, 2)
        self.assertEqual(
            reader.reads,
            [
                (
                    ENEMY_MANAGER_TEMPLATE_BASE,
                    (ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE,
                )
            ],
        )

    def test_truncated_enemy_slab_fails_closed(self) -> None:
        reader = _Reader(b"\0" * ENEMY_STRIDE)

        with self.assertRaisesRegex(ValueError, "slab is truncated"):
            _read_active_enemy_records(reader)

    def test_persistent_destination_avoids_raw_and_slice_copies(self) -> None:
        slab = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        struct.pack_into(
            "<I",
            slab,
            ENEMY_STRIDE + ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        reader = _IntoReader(bytes(slab))
        destination = reader.allocate_buffer(len(slab))

        manager, ordinary, active_count = _read_active_enemy_records(
            reader,
            slab_buffer=destination,
        )

        self.assertIsInstance(manager, memoryview)
        self.assertIsInstance(ordinary, memoryview)
        self.assertIs(manager.obj, destination)
        self.assertIs(ordinary.obj, destination)
        self.assertEqual(active_count, 1)
        self.assertEqual(
            reader.into_reads,
            [(ENEMY_MANAGER_TEMPLATE_BASE, len(slab))],
        )

    def test_current_hazard_pools_use_two_persistent_versioned_reads(
        self,
    ) -> None:
        reader = _PoolIntoReader()
        bullet_buffer = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        laser_buffer = bytearray(LASER_POOL_SIZE * LASER_STRIDE)

        bullets, lasers = _read_current_hazard_pools(
            reader,
            bullet_buffer=bullet_buffer,
            laser_buffer=laser_buffer,
        )

        self.assertIs(bullets.obj, bullet_buffer)
        self.assertIs(lasers.obj, laser_buffer)
        self.assertEqual(
            reader.into_reads,
            [
                (BULLET_POOL_BASE, BULLET_POOL_SIZE * BULLET_STRIDE),
                (LASER_POOL_BASE, LASER_POOL_SIZE * LASER_STRIDE),
            ],
        )

    def test_hazard_decode_runs_only_after_a_stable_closing_clock(self) -> None:
        events: list[str] = []
        reader = _ClockReader(events)

        def payload(*_args: object, **_kwargs: object) -> dict[str, object]:
            # The first attempt crosses 10 -> 11; the second is stable at 12.
            manager_frame = 10 if events[-1] == "frame:10" else 12
            return {"compact_state": {"manager_frame": manager_frame}}

        def decode_bullets(*_args: object, **_kwargs: object) -> tuple[object, ...]:
            events.append("decode_bullets")
            return ()

        def decode_lasers(*_args: object, **_kwargs: object) -> tuple[object, ...]:
            events.append("decode_lasers")
            return ()

        with (
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "_persistent_enemy_slab_buffer",
                return_value=None,
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "_persistent_hazard_pool_buffers",
                return_value=(None, None),
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "_read_active_enemy_records",
                return_value=(memoryview(b""), memoryview(b""), 0),
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture.observe_state",
                return_value={},
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture._payload",
                side_effect=payload,
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "_read_current_hazard_pools",
                return_value=(memoryview(b"bullet"), memoryview(b"laser")),
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture.decode_bullets",
                side_effect=decode_bullets,
            ) as bullet_decode,
            patch(
                "th08_runtime.ordinary_future_source_capture.decode_lasers",
                side_effect=decode_lasers,
            ) as laser_decode,
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "build_current_hazard_root",
                return_value={"schema": "fixture"},
            ),
        ):
            snapshot = capture_ordinary_future_source_snapshot(
                reader,
                maximum_attempts=2,
                retain_current_hazards=True,
            )

        self.assertTrue(snapshot.stable)
        self.assertEqual(snapshot.frame_before, 12)
        self.assertEqual(snapshot.attempts, 2)
        self.assertEqual(snapshot.current_hazard_root, {"schema": "fixture"})
        bullet_decode.assert_called_once()
        laser_decode.assert_called_once()
        closing_serial = max(
            index
            for index, event in enumerate(events)
            if event == "serial:22"
        )
        self.assertLess(closing_serial, events.index("decode_bullets"))


if __name__ == "__main__":
    unittest.main()
