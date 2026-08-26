from __future__ import annotations

import socket
import struct
import unittest

from th08_linux.bridge import SolverBridgeClient
from th08_linux.protocol import (
    BOMB,
    DOWN,
    FOCUS,
    LEFT,
    REPLAY_TARGET_STAMPED,
    RESPONSE_MAGIC,
    RIGHT,
    UP,
    decode_request,
    encode_response,
    read_exact,
)


def _request(*, epoch: int = 7, paused_milliseconds: int = 1234) -> bytes:
    return struct.pack(
        "<IHHQHHH2xII",
        0x51523854,
        1,
        32,
        epoch,
        LEFT | FOCUS,
        RIGHT,
        0x9630,
        REPLAY_TARGET_STAMPED,
        paused_milliseconds,
    )


class _ChunkReader:
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)

    def recv(self, size: int) -> bytes:
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > size:
            self.chunks.insert(0, chunk[size:])
            chunk = chunk[:size]
        return chunk


class LinuxBridgeProtocolTests(unittest.TestCase):
    def test_request_decodes_explicit_epoch_clock_and_target_stamp(self) -> None:
        request = decode_request(_request())
        self.assertEqual(request.epoch, 7)
        self.assertEqual(request.current_input, LEFT | FOCUS)
        self.assertEqual(request.previous_input, RIGHT)
        self.assertEqual(request.rng_seed, 0x9630)
        self.assertEqual(request.paused_milliseconds, 1234)
        self.assertTrue(request.replay_target_stamped)

    def test_wire_read_completes_fragmented_records(self) -> None:
        payload = _request()
        self.assertEqual(
            read_exact(_ChunkReader(payload[:3], payload[3:19], payload[19:]), 32),
            payload,
        )

    def test_wire_read_fails_closed_on_disconnect(self) -> None:
        with self.assertRaisesRegex(EOFError, "closed"):
            read_exact(_ChunkReader(b"short"), 32)

    def test_request_rejects_unknown_flags(self) -> None:
        payload = bytearray(_request())
        struct.pack_into("<I", payload, 24, 1 << 31)
        with self.assertRaisesRegex(ValueError, "unknown flags"):
            decode_request(bytes(payload))

    def test_response_is_exact_epoch_and_hard_no_bomb(self) -> None:
        encoded = encode_response(9, LEFT | UP | FOCUS)
        self.assertEqual(len(encoded), 24)
        self.assertEqual(
            struct.unpack("<IHHQHHI", encoded),
            (RESPONSE_MAGIC, 1, 24, 9, LEFT | UP | FOCUS, 0, 0),
        )
        for invalid in (BOMB, UP | DOWN, LEFT | RIGHT, 1 << 15):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    encode_response(9, invalid)

    def test_client_requires_one_response_per_request(self) -> None:
        game, solver = socket.socketpair()
        self.addCleanup(game.close)
        client = SolverBridgeClient(solver)
        self.addCleanup(client.close)
        game.sendall(_request(epoch=41))

        request = client.receive()
        self.assertEqual(request.epoch, 41)
        with self.assertRaisesRegex(RuntimeError, "still needs a response"):
            client.receive()
        client.respond(LEFT)

        response = read_exact(game, 24)
        self.assertEqual(struct.unpack("<Q", response[8:16])[0], 41)
        with self.assertRaisesRegex(RuntimeError, "no pending"):
            client.respond(0)


if __name__ == "__main__":
    unittest.main()
