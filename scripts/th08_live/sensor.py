"""Stable raw-pool capture boundary for the TH08 live controller."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


BULLET_POOL_BASE = 0x00F6F710
BULLET_POOL_SIZE = 1536
BULLET_STRIDE = 0x10B8

LASER_POOL_BASE = 0x015B57C8
LASER_POOL_SIZE = 256
LASER_STRIDE = 0x059C

ITEM_MANAGER_BASE = 0x01653648
ITEM_POOL_SIZE = 2096
ITEM_STRIDE = 0x02E4

ENEMY_MANAGER_FRAME_ADDRESS = 0x0164D30C


@dataclass(frozen=True)
class RawPoolCapture:
    bullet_blob: memoryview
    laser_blob: memoryview
    item_blob: memoryview
    bullet_frame_before: int
    bullet_frame_after: int
    bullet_pool_read_ms: float
    laser_pool_read_ms: float
    item_pool_read_ms: float


class Sensor:
    """Own persistent pool destinations and preserve live read order."""

    def __init__(
        self,
        reader: Any,
        *,
        capture_items: bool = True,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._reader = reader
        self._clock = clock
        self._capture_items = capture_items
        self._bullet_buffer = reader.allocate_buffer(
            BULLET_POOL_SIZE * BULLET_STRIDE
        )
        self._laser_buffer = reader.allocate_buffer(
            LASER_POOL_SIZE * LASER_STRIDE
        )
        self._item_buffer = (
            reader.allocate_buffer(ITEM_POOL_SIZE * ITEM_STRIDE)
            if capture_items
            else bytearray()
        )
        self._bullet_blob = memoryview(self._bullet_buffer).cast("B")
        self._laser_blob = memoryview(self._laser_buffer).cast("B")
        self._item_blob = memoryview(self._item_buffer).cast("B")

    def capture_raw_pools(self) -> RawPoolCapture:
        bullet_frame_before = self._reader.u32(
            ENEMY_MANAGER_FRAME_ADDRESS
        )
        started = self._clock()
        self._reader.read_into(BULLET_POOL_BASE, self._bullet_buffer)
        bullet_pool_read_ms = (self._clock() - started) * 1000.0
        bullet_frame_after = self._reader.u32(
            ENEMY_MANAGER_FRAME_ADDRESS
        )

        started = self._clock()
        self._reader.read_into(LASER_POOL_BASE, self._laser_buffer)
        laser_pool_read_ms = (self._clock() - started) * 1000.0

        if self._capture_items:
            started = self._clock()
            self._reader.read_into(ITEM_MANAGER_BASE, self._item_buffer)
            item_pool_read_ms = (self._clock() - started) * 1000.0
        else:
            item_pool_read_ms = 0.0

        return RawPoolCapture(
            bullet_blob=self._bullet_blob,
            laser_blob=self._laser_blob,
            item_blob=self._item_blob,
            bullet_frame_before=bullet_frame_before,
            bullet_frame_after=bullet_frame_after,
            bullet_pool_read_ms=bullet_pool_read_ms,
            laser_pool_read_ms=laser_pool_read_ms,
            item_pool_read_ms=item_pool_read_ms,
        )


__all__ = [
    "BULLET_POOL_BASE",
    "BULLET_POOL_SIZE",
    "BULLET_STRIDE",
    "ITEM_MANAGER_BASE",
    "ITEM_POOL_SIZE",
    "ITEM_STRIDE",
    "LASER_POOL_BASE",
    "LASER_POOL_SIZE",
    "LASER_STRIDE",
    "RawPoolCapture",
    "Sensor",
]
