from __future__ import annotations

import unittest

from th08_linux.protocol import InputRequest, REPLAY_TARGET_STAMPED
from th08_linux.witness import validate_request_memory_witness
from th08_runtime.game_state import (
    ADDR_CURRENT_INPUT,
    ADDR_GAMEPLAY_RNG,
    ADDR_LAST_FRAME_INPUT,
    ADDR_PREVIOUS_INPUT,
    ADDR_RAW_INPUT,
)


class _ScalarReader:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def u16(self, address: int) -> int:
        return self.values.get(address, 0)


def _request() -> InputRequest:
    return InputRequest(
        epoch=9,
        current_input=0x0080,
        previous_input=0x0001,
        rng_seed=0x9630,
        flags=REPLAY_TARGET_STAMPED,
        paused_milliseconds=4,
    )


class LinuxLockstepWitnessTests(unittest.TestCase):
    def test_uses_supervisor_inputs_not_adjacent_gui_replay_inputs(self) -> None:
        reader = _ScalarReader(
            {
                ADDR_RAW_INPUT: 0x0080,
                ADDR_CURRENT_INPUT: 0x0040,
                ADDR_LAST_FRAME_INPUT: 0x0001,
                ADDR_PREVIOUS_INPUT: 0,
                ADDR_GAMEPLAY_RNG: 0x9630,
            }
        )

        witness = validate_request_memory_witness(_request(), reader)

        self.assertEqual(witness.supervisor_current_input, 0x0080)
        self.assertEqual(witness.supervisor_previous_input, 0x0001)

    def test_rejects_previous_input_compared_to_the_wrong_source_global(self) -> None:
        reader = _ScalarReader(
            {
                ADDR_RAW_INPUT: 0x0080,
                ADDR_LAST_FRAME_INPUT: 0,
                ADDR_GAMEPLAY_RNG: 0x9630,
            }
        )
        with self.assertRaisesRegex(RuntimeError, "g_LastFrameInput"):
            validate_request_memory_witness(_request(), reader)

    def test_can_defer_only_rng_equality_during_async_gameplay_setup(self) -> None:
        reader = _ScalarReader(
            {
                ADDR_RAW_INPUT: 0x0080,
                ADDR_LAST_FRAME_INPUT: 0x0001,
                ADDR_GAMEPLAY_RNG: 0x1234,
            }
        )
        witness = validate_request_memory_witness(
            _request(), reader, verify_rng=False
        )
        self.assertEqual(witness.rng_seed, 0x1234)
        with self.assertRaisesRegex(RuntimeError, "wire=0x9630"):
            validate_request_memory_witness(_request(), reader)


if __name__ == "__main__":
    unittest.main()
