from __future__ import annotations

import unittest

from th08_live import (
    BULLET_POOL_BASE,
    BULLET_POOL_SIZE,
    BULLET_STRIDE,
    ITEM_MANAGER_BASE,
    ITEM_POOL_SIZE,
    ITEM_STRIDE,
    LASER_POOL_BASE,
    LASER_POOL_SIZE,
    LASER_STRIDE,
    Sensor,
)


class _FakeReader:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.frames = iter((100, 101, 102, 103))

    def allocate_buffer(self, size: int) -> bytearray:
        self.events.append(("allocate", size))
        return bytearray(size)

    def u32(self, address: int) -> int:
        frame = next(self.frames)
        self.events.append(("frame", address, frame))
        return frame

    def read_into(self, address: int, destination: bytearray) -> None:
        self.events.append(("read_into", address, id(destination)))
        destination[0] = address & 0xFF


class SensorTests(unittest.TestCase):
    def test_raw_pool_capture_reuses_buffers_and_preserves_read_order(
        self,
    ) -> None:
        reader = _FakeReader()
        ticks = iter(
            (
                0.000,
                0.001,
                0.002,
                0.004,
                0.005,
                0.008,
                0.010,
                0.011,
                0.012,
                0.014,
                0.015,
                0.018,
            )
        )
        sensor = Sensor(reader, clock=lambda: next(ticks))

        first = sensor.capture_raw_pools()
        second = sensor.capture_raw_pools()

        self.assertIs(first.bullet_blob.obj, second.bullet_blob.obj)
        self.assertIs(first.laser_blob.obj, second.laser_blob.obj)
        self.assertIs(first.item_blob.obj, second.item_blob.obj)
        self.assertEqual(
            (
                first.bullet_frame_before,
                first.bullet_frame_after,
                second.bullet_frame_before,
                second.bullet_frame_after,
            ),
            (100, 101, 102, 103),
        )
        self.assertAlmostEqual(first.bullet_pool_read_ms, 1.0)
        self.assertAlmostEqual(first.laser_pool_read_ms, 2.0)
        self.assertAlmostEqual(first.item_pool_read_ms, 3.0)
        self.assertEqual(
            reader.events[:3],
            [
                ("allocate", BULLET_POOL_SIZE * BULLET_STRIDE),
                ("allocate", LASER_POOL_SIZE * LASER_STRIDE),
                ("allocate", ITEM_POOL_SIZE * ITEM_STRIDE),
            ],
        )
        first_capture_events = reader.events[3:8]
        self.assertEqual(first_capture_events[0], (
            "frame",
            0x0164D30C,
            100,
        ))
        self.assertEqual(
            first_capture_events[1][0:2],
            ("read_into", BULLET_POOL_BASE),
        )
        self.assertEqual(first_capture_events[2], (
            "frame",
            0x0164D30C,
            101,
        ))
        self.assertEqual(
            first_capture_events[3][0:2],
            ("read_into", LASER_POOL_BASE),
        )
        self.assertEqual(
            first_capture_events[4][0:2],
            ("read_into", ITEM_MANAGER_BASE),
        )

    def test_item_pool_can_be_omitted_when_it_has_no_consumer(self) -> None:
        reader = _FakeReader()
        ticks = iter((0.000, 0.001, 0.002, 0.004))
        sensor = Sensor(
            reader,
            capture_items=False,
            clock=lambda: next(ticks),
        )

        capture = sensor.capture_raw_pools()

        self.assertEqual(len(capture.item_blob), 0)
        self.assertEqual(capture.item_pool_read_ms, 0.0)
        self.assertNotIn(
            ("allocate", ITEM_POOL_SIZE * ITEM_STRIDE),
            reader.events,
        )
        self.assertFalse(
            any(
                event[0:2] == ("read_into", ITEM_MANAGER_BASE)
                for event in reader.events
                if isinstance(event, tuple)
            )
        )


if __name__ == "__main__":
    unittest.main()
