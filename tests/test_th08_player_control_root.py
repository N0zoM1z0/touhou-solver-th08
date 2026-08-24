from __future__ import annotations

import struct
import unittest

from th08_runtime.game_state import (
    ADDR_CURRENT_INPUT,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_GAMEPLAY_TIME_SCALE,
    ADDR_PLAYER,
    ADDR_PREVIOUS_INPUT,
    ADDR_RAW_INPUT,
    PLAYER_POSITION_OFFSET,
)
from th08_runtime.sensing import capture_player_control_root


class _Reader:
    def __init__(
        self,
        values: dict[tuple[object, ...], list[object]],
    ) -> None:
        self.values = {
            key: list(sequence) for key, sequence in values.items()
        }
        self.calls: list[tuple[object, ...]] = []

    def _next(self, key: tuple[object, ...]):
        self.calls.append(key)
        return self.values[key].pop(0)

    def u32(self, address: int) -> int:
        return int(self._next(("u32", address)))

    def read(self, address: int, size: int) -> bytes:
        return bytes(self._next(("read", address, size)))


_INPUT_CAPTURE_SIZE = ADDR_PREVIOUS_INPUT + 2 - ADDR_RAW_INPUT
_POSITION_CAPTURE_SIZE = 8


def _input_blob(
    *,
    raw: int = 0x100,
    current: int = 0x05,
    previous: int = 0x01,
) -> bytes:
    blob = bytearray(_INPUT_CAPTURE_SIZE)
    struct.pack_into("<H", blob, 0, raw)
    struct.pack_into(
        "<H",
        blob,
        ADDR_CURRENT_INPUT - ADDR_RAW_INPUT,
        current,
    )
    struct.pack_into(
        "<H",
        blob,
        ADDR_PREVIOUS_INPUT - ADDR_RAW_INPUT,
        previous,
    )
    return bytes(blob)


def _values(
    *,
    frames: list[int],
    xs: list[float],
    ys: list[float],
    attempts: int,
) -> dict[tuple[object, ...], list[object]]:
    return {
        ("u32", ADDR_ENEMY_MANAGER_FRAME): frames,
        ("u32", ADDR_GAMEPLAY_TIME_SCALE): [0x3F800000] * attempts,
        ("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE): [
            _input_blob()
        ]
        * (2 * attempts),
        (
            "read",
            ADDR_PLAYER + PLAYER_POSITION_OFFSET,
            _POSITION_CAPTURE_SIZE,
        ): [
            struct.pack("<ff", x, y) for x, y in zip(xs, ys, strict=True)
        ],
    }


class PlayerControlRootTests(unittest.TestCase):
    def test_stable_root_binds_position_input_scale_and_frame(self) -> None:
        reader = _Reader(
            _values(
                frames=[100, 100],
                xs=[192.0, 192.0],
                ys=[400.0, 400.0],
                attempts=1,
            )
        )
        capture = capture_player_control_root(reader)

        self.assertTrue(capture.stable)
        self.assertEqual(capture.attempts, 1)
        self.assertEqual(capture.frame_after, 100)
        self.assertEqual(capture.x, 192.0)
        self.assertEqual(capture.y, 400.0)
        self.assertEqual(capture.input_current, 0x05)
        self.assertEqual(capture.scale_bits, 0x3F800000)
        self.assertEqual(
            reader.calls,
            [
                ("u32", ADDR_ENEMY_MANAGER_FRAME),
                ("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE),
                (
                    "read",
                    ADDR_PLAYER + PLAYER_POSITION_OFFSET,
                    _POSITION_CAPTURE_SIZE,
                ),
                ("u32", ADDR_GAMEPLAY_TIME_SCALE),
                (
                    "read",
                    ADDR_PLAYER + PLAYER_POSITION_OFFSET,
                    _POSITION_CAPTURE_SIZE,
                ),
                ("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE),
                ("u32", ADDR_ENEMY_MANAGER_FRAME),
            ],
        )

    def test_frozen_manager_frame_does_not_hide_player_motion(self) -> None:
        capture = capture_player_control_root(
            _Reader(
                _values(
                    frames=[100, 100],
                    xs=[192.0, 194.0],
                    ys=[400.0, 400.0],
                    attempts=1,
                )
            ),
            maximum_attempts=1,
        )

        self.assertFalse(capture.stable)

    def test_frozen_manager_frame_does_not_hide_input_change(self) -> None:
        values = _values(
            frames=[100, 100],
            xs=[192.0, 192.0],
            ys=[400.0, 400.0],
            attempts=1,
        )
        values[("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE)] = [
            _input_blob(current=0x05),
            _input_blob(current=0x15),
        ]

        capture = capture_player_control_root(
            _Reader(values),
            maximum_attempts=1,
        )

        self.assertFalse(capture.stable)

    def test_retry_accepts_only_the_later_coherent_root(self) -> None:
        capture = capture_player_control_root(
            _Reader(
                _values(
                    frames=[100, 100, 101, 101],
                    xs=[192.0, 193.0, 194.0, 194.0],
                    ys=[400.0, 400.0, 398.0, 398.0],
                    attempts=2,
                )
            ),
            maximum_attempts=2,
        )

        self.assertTrue(capture.stable)
        self.assertEqual(capture.attempts, 2)
        self.assertEqual(capture.frame_after, 101)
        self.assertEqual((capture.x, capture.y), (194.0, 398.0))

    def test_attempt_count_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "attempts"):
            capture_player_control_root(
                _Reader({}),
                maximum_attempts=0,
            )

    def test_input_fields_decode_from_their_authoritative_offsets(self) -> None:
        values = _values(
            frames=[200, 200],
            xs=[12.5, 12.5],
            ys=[34.5, 34.5],
            attempts=1,
        )
        values[("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE)] = [
            _input_blob(raw=0x1234, current=0x5678, previous=0x9ABC),
            _input_blob(raw=0x1234, current=0x5678, previous=0x9ABC),
        ]

        capture = capture_player_control_root(_Reader(values))

        self.assertEqual(capture.input_raw, 0x1234)
        self.assertEqual(capture.input_current, 0x5678)
        self.assertEqual(capture.input_previous, 0x9ABC)

    def test_short_input_capture_fails_closed(self) -> None:
        values = _values(
            frames=[100, 100],
            xs=[192.0, 192.0],
            ys=[400.0, 400.0],
            attempts=1,
        )
        values[("read", ADDR_RAW_INPUT, _INPUT_CAPTURE_SIZE)][0] = bytes(
            _INPUT_CAPTURE_SIZE - 1
        )

        with self.assertRaisesRegex(ValueError, "exactly 14 bytes"):
            capture_player_control_root(_Reader(values))

    def test_short_position_capture_fails_closed(self) -> None:
        values = _values(
            frames=[100, 100],
            xs=[192.0, 192.0],
            ys=[400.0, 400.0],
            attempts=1,
        )
        position_key = (
            "read",
            ADDR_PLAYER + PLAYER_POSITION_OFFSET,
            _POSITION_CAPTURE_SIZE,
        )
        values[position_key][0] = bytes(_POSITION_CAPTURE_SIZE - 1)

        with self.assertRaisesRegex(ValueError, "exactly 8 bytes"):
            capture_player_control_root(_Reader(values))


if __name__ == "__main__":
    unittest.main()
