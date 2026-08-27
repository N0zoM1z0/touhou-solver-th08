"""Runtime-owned immutable packed roots for native Linux online play.

The runtime copies one post-update root into a leased slot and publishes only
its address, size, and generation over the non-blocking input bridge.  The
solver copies that compact slot once, releases the runtime lease, and performs
all immediate and background reads against these local immutable bytes.

Active fixed-pool records retain their original virtual addresses.  Reads of
an entire native pool are reconstructed locally with zero-filled inactive
records, so existing authoritative decoders can be reused without another
live-process read or an unchanged-frame bracket.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import threading
import time
from typing import Any


SNAPSHOT_MAGIC = 0x4E533854  # "T8SN" as little endian.
SNAPSHOT_VERSION = 1
SNAPSHOT_HEADER_SIZE = 80
SNAPSHOT_ENTRY_SIZE = 16
SNAPSHOT_FLAG_COMPLETE = 1 << 0
MAXIMUM_SNAPSHOT_ENTRIES = 8192
MAXIMUM_SNAPSHOT_SIZE = 32 * 1024 * 1024

RANGE_KIND_EXACT = 0
RANGE_KIND_BULLET = 1
RANGE_KIND_LASER = 2
RANGE_KIND_ENEMY = 3
RANGE_KIND_ITEM = 4
_KNOWN_RANGE_KINDS = frozenset(
    {
        RANGE_KIND_EXACT,
        RANGE_KIND_BULLET,
        RANGE_KIND_LASER,
        RANGE_KIND_ENEMY,
        RANGE_KIND_ITEM,
    }
)

# These are the source-authoritative fixed pool layouts already used by the
# TH08 live decoders.  Keeping them here avoids importing the planner stack in
# the protocol/session layer.
BULLET_POOL_BASE = 0x00F6F710
BULLET_POOL_SIZE = 1536
BULLET_STRIDE = 0x10B8
LASER_POOL_BASE = 0x015B57C8
LASER_POOL_SIZE = 256
LASER_STRIDE = 0x059C
ITEM_POOL_BASE = 0x01653648
ITEM_POOL_SIZE = 2096
ITEM_STRIDE = 0x02E4
ENEMY_MANAGER_TEMPLATE_BASE = 0x0057D2F0
ENEMY_POOL_RECORD_COUNT = 481
ENEMY_STRIDE = 0x53D0

_HEADER = struct.Struct("<IHHQQ14I")
_ENTRY = struct.Struct("<IIII")
_SCALARS = {
    "u8": struct.Struct("<B"),
    "u16": struct.Struct("<H"),
    "u32": struct.Struct("<I"),
    "i32": struct.Struct("<i"),
    "f32": struct.Struct("<f"),
}


@dataclass(frozen=True, slots=True)
class SnapshotRange:
    source_address: int
    size: int
    data_offset: int
    kind: int

    @property
    def source_end(self) -> int:
        return self.source_address + self.size


@dataclass(frozen=True, slots=True)
class PackedPoolRecord:
    slot: int
    source_address: int
    data: memoryview


@dataclass(frozen=True, slots=True)
class _SparsePool:
    base: int
    count: int
    stride: int
    kind: int

    @property
    def end(self) -> int:
        return self.base + self.count * self.stride


_SPARSE_POOLS = (
    _SparsePool(BULLET_POOL_BASE, BULLET_POOL_SIZE, BULLET_STRIDE, RANGE_KIND_BULLET),
    _SparsePool(LASER_POOL_BASE, LASER_POOL_SIZE, LASER_STRIDE, RANGE_KIND_LASER),
    _SparsePool(ITEM_POOL_BASE, ITEM_POOL_SIZE, ITEM_STRIDE, RANGE_KIND_ITEM),
    _SparsePool(
        ENEMY_MANAGER_TEMPLATE_BASE,
        ENEMY_POOL_RECORD_COUNT,
        ENEMY_STRIDE,
        RANGE_KIND_ENEMY,
    ),
)
_SPARSE_POOL_BY_KIND = {pool.kind: pool for pool in _SPARSE_POOLS}


class ImmutableSnapshotReader:
    """Address-space reader backed only by one local immutable root."""

    def __init__(self, payload: bytes, ranges: tuple[SnapshotRange, ...]) -> None:
        self._payload = payload
        self._ranges = ranges
        self._cache: dict[tuple[int, int], bytes] = {}
        self._cache_lock = threading.Lock()

    @staticmethod
    def allocate_buffer(size: int) -> bytearray:
        if size < 0:
            raise ValueError("snapshot buffer size cannot be negative")
        return bytearray(size)

    def _covering_range(self, address: int, size: int) -> SnapshotRange | None:
        end = address + size
        candidates = (
            entry
            for entry in self._ranges
            if entry.source_address <= address and end <= entry.source_end
        )
        return min(candidates, key=lambda entry: entry.size, default=None)

    @staticmethod
    def _sparse_pool(address: int, size: int) -> _SparsePool | None:
        end = address + size
        return next(
            (
                pool
                for pool in _SPARSE_POOLS
                if pool.base <= address and end <= pool.end
            ),
            None,
        )

    def _fill_sparse(
        self,
        address: int,
        target: memoryview,
        pool: _SparsePool,
    ) -> None:
        target[:] = b"\0" * len(target)
        requested_end = address + len(target)
        for entry in self._ranges:
            if entry.kind != pool.kind:
                continue
            overlap_start = max(address, entry.source_address)
            overlap_end = min(requested_end, entry.source_end)
            if overlap_start >= overlap_end:
                continue
            source_start = entry.data_offset + overlap_start - entry.source_address
            source_end = source_start + overlap_end - overlap_start
            target_start = overlap_start - address
            target[target_start : target_start + overlap_end - overlap_start] = (
                self._payload[source_start:source_end]
            )

    def packed_pool_records(self, kind: int) -> tuple[PackedPoolRecord, ...]:
        """Return the active fixed-pool records without synthesizing a slab."""

        pool = _SPARSE_POOL_BY_KIND.get(kind)
        if pool is None:
            raise ValueError("immutable snapshot kind is not a fixed pool")
        payload = memoryview(self._payload)
        records: list[PackedPoolRecord] = []
        seen_slots: set[int] = set()
        for entry in self._ranges:
            if entry.kind != kind or not (
                pool.base <= entry.source_address < pool.end
            ):
                continue
            offset = entry.source_address - pool.base
            if entry.size != pool.stride or offset % pool.stride:
                raise ValueError(
                    "immutable snapshot fixed-pool record is not canonical"
                )
            slot = offset // pool.stride
            if slot in seen_slots:
                raise ValueError("immutable snapshot fixed-pool slot is duplicated")
            seen_slots.add(slot)
            records.append(
                PackedPoolRecord(
                    slot=slot,
                    source_address=entry.source_address,
                    data=payload[
                        entry.data_offset : entry.data_offset + entry.size
                    ],
                )
            )
        records.sort(key=lambda record: record.slot)
        return tuple(records)

    def read_into(self, address: int, buffer: Any) -> None:
        target = memoryview(buffer)
        if target.readonly:
            raise ValueError("snapshot read destination must be writable")
        if target.ndim != 1 or target.format != "B":
            target = target.cast("B")
        size = len(target)
        if address < 0 or size < 0 or address + size > 0x100000000:
            raise ValueError("snapshot read is outside the 32-bit address space")
        entry = self._covering_range(address, size)
        if entry is not None:
            start = entry.data_offset + address - entry.source_address
            target[:] = self._payload[start : start + size]
            return
        pool = self._sparse_pool(address, size)
        if pool is None:
            raise OSError(
                f"immutable root does not cover read {address:#010x}+{size:#x}"
            )
        self._fill_sparse(address, target, pool)

    def read(self, address: int, size: int) -> bytes:
        key = (address, size)
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        output = bytearray(size)
        self.read_into(address, output)
        result = bytes(output)
        # Cache only synthesized or moderately sized roots.  Exact tiny reads
        # are cheap slices, while repeated pool materialization is not.
        if self._sparse_pool(address, size) is not None:
            with self._cache_lock:
                self._cache.setdefault(key, result)
                result = self._cache[key]
        return result

    def _scalar(self, name: str, address: int) -> int | float:
        codec = _SCALARS[name]
        return codec.unpack(self.read(address, codec.size))[0]

    def u8(self, address: int) -> int:
        return int(self._scalar("u8", address))

    def u16(self, address: int) -> int:
        return int(self._scalar("u16", address))

    def u32(self, address: int) -> int:
        return int(self._scalar("u32", address))

    def i32(self, address: int) -> int:
        return int(self._scalar("i32", address))

    def f32(self, address: int) -> float:
        return float(self._scalar("f32", address))


@dataclass(frozen=True, slots=True)
class PublishedSnapshotRoot:
    generation: int
    source_epoch: int
    manager_frame: int
    update_serial: int
    flags: int
    bullet_record_count: int
    laser_record_count: int
    enemy_record_count: int
    item_record_count: int
    auxiliary_context_count: int
    ranges: tuple[SnapshotRange, ...]
    reader: ImmutableSnapshotReader
    packed_size: int
    process_copy_ms: float

    @classmethod
    def parse(
        cls,
        payload: bytes,
        *,
        expected_generation: int,
        expected_source_epoch: int,
        expected_entry_count: int,
        process_copy_ms: float = 0.0,
    ) -> "PublishedSnapshotRoot":
        payload = bytes(payload)
        if len(payload) < SNAPSHOT_HEADER_SIZE:
            raise ValueError("immutable snapshot is shorter than its header")
        (
            magic,
            version,
            header_size,
            generation,
            source_epoch,
            manager_frame,
            update_serial,
            total_size,
            entry_count,
            directory_offset,
            data_offset,
            flags,
            bullet_count,
            laser_count,
            enemy_count,
            item_count,
            auxiliary_count,
            reserved0,
            reserved1,
        ) = _HEADER.unpack_from(payload)
        if magic != SNAPSHOT_MAGIC:
            raise ValueError(f"unknown immutable snapshot magic {magic:#010x}")
        if version != SNAPSHOT_VERSION or header_size != SNAPSHOT_HEADER_SIZE:
            raise ValueError("unsupported immutable snapshot format")
        if generation != expected_generation or source_epoch != expected_source_epoch:
            raise ValueError("immutable snapshot certificate version mismatch")
        if total_size != len(payload):
            raise ValueError("immutable snapshot size certificate mismatch")
        if total_size > MAXIMUM_SNAPSHOT_SIZE:
            raise ValueError("immutable snapshot exceeds its bounded slot")
        if entry_count != expected_entry_count:
            raise ValueError("immutable snapshot entry-count certificate mismatch")
        if not 0 < entry_count <= MAXIMUM_SNAPSHOT_ENTRIES:
            raise ValueError("immutable snapshot entry count is invalid")
        directory_end = directory_offset + entry_count * SNAPSHOT_ENTRY_SIZE
        if (
            directory_offset < header_size
            or directory_end > data_offset
            or data_offset > total_size
        ):
            raise ValueError("immutable snapshot directory bounds are invalid")
        if flags != SNAPSHOT_FLAG_COMPLETE or reserved0 or reserved1:
            raise ValueError("immutable snapshot is incomplete or noncanonical")

        ranges: list[SnapshotRange] = []
        kind_counts = {kind: 0 for kind in _KNOWN_RANGE_KINDS}
        for index in range(entry_count):
            source_address, size, offset, kind = _ENTRY.unpack_from(
                payload,
                directory_offset + index * SNAPSHOT_ENTRY_SIZE,
            )
            if (
                size <= 0
                or source_address + size > 0x100000000
                or offset < data_offset
                or offset + size > total_size
                or kind not in _KNOWN_RANGE_KINDS
            ):
                raise ValueError(f"immutable snapshot range {index} is invalid")
            if kind != RANGE_KIND_EXACT:
                pool = _SPARSE_POOL_BY_KIND[kind]
                in_fixed_pool = pool.base <= source_address < pool.end
                if size != pool.stride or (
                    in_fixed_pool
                    and (source_address - pool.base) % pool.stride
                ):
                    raise ValueError(
                        f"immutable snapshot typed range {index} is noncanonical"
                    )
                if kind != RANGE_KIND_ENEMY and not in_fixed_pool:
                    raise ValueError(
                        f"immutable snapshot typed range {index} is outside its pool"
                    )
            ranges.append(SnapshotRange(source_address, size, offset, kind))
            kind_counts[kind] += 1
        expected_counts = {
            RANGE_KIND_BULLET: bullet_count,
            RANGE_KIND_LASER: laser_count,
            RANGE_KIND_ENEMY: enemy_count,
            RANGE_KIND_ITEM: item_count,
        }
        for kind, expected in expected_counts.items():
            if kind_counts[kind] != expected:
                raise ValueError("immutable snapshot typed range count mismatch")
        if auxiliary_count > kind_counts[RANGE_KIND_EXACT]:
            raise ValueError("immutable snapshot auxiliary count is impossible")
        immutable_payload = payload
        immutable_ranges = tuple(ranges)
        return cls(
            generation=generation,
            source_epoch=source_epoch,
            manager_frame=manager_frame,
            update_serial=update_serial,
            flags=flags,
            bullet_record_count=bullet_count,
            laser_record_count=laser_count,
            enemy_record_count=enemy_count,
            item_record_count=item_count,
            auxiliary_context_count=auxiliary_count,
            ranges=immutable_ranges,
            reader=ImmutableSnapshotReader(immutable_payload, immutable_ranges),
            packed_size=total_size,
            process_copy_ms=process_copy_ms,
        )

    @classmethod
    def capture(cls, process_reader: Any, request: Any) -> "PublishedSnapshotRoot":
        if not bool(getattr(request, "snapshot_present", False)):
            raise ValueError("online request has no immutable snapshot")
        started = time.perf_counter()
        payload = process_reader.read(
            int(request.snapshot_address),
            int(request.snapshot_size),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if len(payload) != int(request.snapshot_size):
            raise OSError("runtime snapshot slot read was truncated")
        return cls.parse(
            payload,
            expected_generation=int(request.snapshot_generation),
            expected_source_epoch=int(request.source_epoch),
            expected_entry_count=int(request.snapshot_entry_count),
            process_copy_ms=elapsed_ms,
        )


__all__ = (
    "ImmutableSnapshotReader",
    "PackedPoolRecord",
    "PublishedSnapshotRoot",
    "RANGE_KIND_BULLET",
    "RANGE_KIND_ENEMY",
    "RANGE_KIND_EXACT",
    "RANGE_KIND_ITEM",
    "RANGE_KIND_LASER",
    "SNAPSHOT_ENTRY_SIZE",
    "SNAPSHOT_FLAG_COMPLETE",
    "SNAPSHOT_HEADER_SIZE",
    "SNAPSHOT_MAGIC",
    "SNAPSHOT_VERSION",
    "SnapshotRange",
)
