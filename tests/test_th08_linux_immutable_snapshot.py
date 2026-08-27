from __future__ import annotations

import socket
import struct
import unittest

from th08_linux.immutable_snapshot import (
    BULLET_POOL_BASE,
    BULLET_POOL_SIZE,
    BULLET_STRIDE,
    RANGE_KIND_BULLET,
    RANGE_KIND_EXACT,
    SNAPSHOT_FLAG_COMPLETE,
    SNAPSHOT_HEADER_SIZE,
    SNAPSHOT_MAGIC,
    SNAPSHOT_VERSION,
    PublishedSnapshotRoot,
)
from th08_linux.online_bridge import OnlineSolverBridgeClient
from th08_linux.online_protocol import REQUEST_SIZE, SNAPSHOT_RELEASE_MAGIC
from th08_live.bullet_decode import decode_bullets
from th08_linux.protocol import (
    FOCUS,
    IMMUTABLE_SNAPSHOT_PRESENT,
    LIVES_PRESERVED,
    REPLAY_TARGET_STAMPED,
    SHOOT,
)


_HEADER = struct.Struct("<IHHQQ14I")
_ENTRY = struct.Struct("<IIII")


def _packed_root(*, generation: int = 9, source_epoch: int = 41) -> bytes:
    exact = struct.pack("<I", 0xAABBCCDD)
    bullet = bytearray(BULLET_STRIDE)
    bullet[0x0DB8 : 0x0DBA] = struct.pack("<H", 1)
    entries = (
        (0x00123450, len(exact), RANGE_KIND_EXACT, exact),
        (
            BULLET_POOL_BASE + 7 * BULLET_STRIDE,
            len(bullet),
            RANGE_KIND_BULLET,
            bytes(bullet),
        ),
    )
    directory_offset = SNAPSHOT_HEADER_SIZE
    data_offset = directory_offset + len(entries) * _ENTRY.size
    payload = bytearray(data_offset)
    cursor = data_offset
    for index, (address, size, kind, data) in enumerate(entries):
        _ENTRY.pack_into(
            payload,
            directory_offset + index * _ENTRY.size,
            address,
            size,
            cursor,
            kind,
        )
        payload.extend(data)
        cursor += size
    _HEADER.pack_into(
        payload,
        0,
        SNAPSHOT_MAGIC,
        SNAPSHOT_VERSION,
        SNAPSHOT_HEADER_SIZE,
        generation,
        source_epoch,
        123,
        456,
        len(payload),
        len(entries),
        directory_offset,
        data_offset,
        SNAPSHOT_FLAG_COMPLETE,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    return bytes(payload)


def _request(payload: bytes, *, address: int = 0x70000000) -> bytes:
    return struct.pack(
        "<IHHQQHHHHIIIIQQIIIIIIIIII",
        0x51523854,
        4,
        REQUEST_SIZE,
        41,
        42,
        SHOOT | FOCUS,
        SHOOT | FOCUS,
        0x9630,
        1,
        REPLAY_TARGET_STAMPED
        | LIVES_PRESERVED
        | IMMUTABLE_SNAPSHOT_PRESENT,
        0,
        0,
        0,
        123_000,
        9,
        address,
        len(payload),
        2,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


class _Reader:
    def __init__(self, address: int, payload: bytes) -> None:
        self.address = address
        self.payload = payload
        self.reads: list[tuple[int, int]] = []

    def read(self, address: int, size: int) -> bytes:
        self.reads.append((address, size))
        if (address, size) != (self.address, len(self.payload)):
            raise AssertionError(f"unexpected process read {address:#x}+{size:#x}")
        return self.payload


class LinuxImmutableSnapshotTests(unittest.TestCase):
    def test_sparse_pool_is_reconstructed_only_from_local_root(self) -> None:
        payload = _packed_root()
        root = PublishedSnapshotRoot.parse(
            payload,
            expected_generation=9,
            expected_source_epoch=41,
            expected_entry_count=2,
        )

        self.assertEqual(root.reader.u32(0x00123450), 0xAABBCCDD)
        pool = root.reader.read(
            BULLET_POOL_BASE,
            BULLET_POOL_SIZE * BULLET_STRIDE,
        )
        self.assertEqual(len(pool), BULLET_POOL_SIZE * BULLET_STRIDE)
        self.assertEqual(
            struct.unpack_from("<H", pool, 7 * BULLET_STRIDE + 0x0DB8)[0],
            1,
        )
        self.assertFalse(any(pool[: 7 * BULLET_STRIDE]))
        self.assertFalse(any(pool[8 * BULLET_STRIDE :]))

        records = root.reader.packed_pool_records(RANGE_KIND_BULLET)
        self.assertEqual([record.slot for record in records], [7])
        compact = decode_bullets(
            b"".join(record.data for record in records),
            record_slots=tuple(record.slot for record in records),
        )
        legacy = decode_bullets(pool)
        self.assertEqual(compact, legacy)

    def test_certificate_rejects_a_mismatched_generation(self) -> None:
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            PublishedSnapshotRoot.parse(
                _packed_root(),
                expected_generation=10,
                expected_source_epoch=41,
                expected_entry_count=2,
            )

    def test_parsed_root_does_not_alias_the_mutable_copy_buffer(self) -> None:
        payload = bytearray(_packed_root())
        root = PublishedSnapshotRoot.parse(
            payload,
            expected_generation=9,
            expected_source_epoch=41,
            expected_entry_count=2,
        )
        first_data_offset = struct.unpack_from("<I", payload, 44)[0]
        payload[first_data_offset] ^= 0xFF

        self.assertEqual(root.reader.u32(0x00123450), 0xAABBCCDD)

    def test_bridge_copies_then_releases_without_delaying_action_packet(self) -> None:
        payload = _packed_root()
        address = 0x70000000
        process = _Reader(address, payload)
        game, solver = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(game.close)
        client = OnlineSolverBridgeClient(solver)
        self.addCleanup(client.close)
        game.send(_request(payload, address=address))

        request = client.receive()
        root = client.capture_snapshot(process, request)
        self.assertEqual(root.generation, 9)
        self.assertTrue(client.respond(SHOOT | FOCUS))

        response = game.recv(40)
        release = game.recv(24)
        self.assertEqual(struct.unpack_from("<I", response)[0], 0x53523854)
        self.assertEqual(struct.unpack_from("<I", release)[0], SNAPSHOT_RELEASE_MAGIC)
        self.assertEqual(struct.unpack_from("<QH", release, 8), (9, 1))
        self.assertEqual(process.reads, [(address, len(payload))])
        self.assertEqual(client.snapshot_releases_sent, 1)


if __name__ == "__main__":
    unittest.main()
