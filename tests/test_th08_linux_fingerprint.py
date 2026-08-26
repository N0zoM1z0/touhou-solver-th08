from __future__ import annotations

import json
import unittest

from th08_linux.fingerprint import (
    ReplayClockSnapshot,
    canonical_fingerprint_bytes,
    semantic_spine_from_observation,
)
from th08_linux.protocol import InputRequest, REPLAY_TARGET_STAMPED
from th08_linux.witness import LockstepMemoryWitness


class LinuxSemanticFingerprintTests(unittest.TestCase):
    def test_spine_is_pointer_free_and_preserves_float_bits(self) -> None:
        request = InputRequest(
            epoch=101,
            current_input=0,
            previous_input=0x80,
            rng_seed=0x9630,
            flags=REPLAY_TARGET_STAMPED,
            paused_milliseconds=0,
        )
        witness = LockstepMemoryWitness(0, 0x80, 0x9630)
        state = {
            "enemy_manager_frame": 17,
            "difficulty_index": 3,
            "route_id": 2,
            "stage_route_index": 5,
            "engine_flags": 0x0C,
            "gameplay_active": True,
            "time_scale_bits": 0x3F800000,
            "input_current": 0x05,
            "input_previous": 0x01,
            "rng_calls": 7,
            "player": {
                "phase": 0,
                "focus_logic": 1,
                "deathbomb": 0,
                "secondary_character_active": False,
                "forced_bomb": 0,
                "focus_transition_counter": 0,
                "x": 192.0,
                "y": 400.0,
                "bomb_active": 0,
                "bomb_index": -1,
                "bomb_timer": 0,
                "predeath_counter": 0,
                "bomb_lockout": 0,
            },
            "resources": {"lives": 8.0, "bombs": 3.0, "power": 128.0},
            "spell": {
                "active": False,
                "flags": 0,
                "enemy_pointer": 0xDEADBEEF,
                "spell_id": 0,
                "name": "",
                "timer_elapsed": 0,
            },
        }
        fingerprint = semantic_spine_from_observation(
            request=request,
            witness=witness,
            state=state,
            replay_clock=ReplayClockSnapshot(4, 0, 1, 0x9630, 0),
            relative_epoch=1,
            rng_calls_origin=3,
        )

        encoded = canonical_fingerprint_bytes(fingerprint)

        self.assertNotIn(b"3735928559", encoded)
        self.assertEqual(fingerprint["player"]["x_bits"], 0x43400000)
        self.assertEqual(fingerprint["resources"]["power_bits"], 0x43000000)
        self.assertEqual(fingerprint["rng"]["calls_since_trace_start"], 4)
        self.assertEqual(json.loads(encoded)["replay"]["frame_counter"], 4)

    def test_canonical_encoding_is_independent_of_mapping_insertion_order(self) -> None:
        self.assertEqual(
            canonical_fingerprint_bytes({"b": 2, "a": 1}),
            canonical_fingerprint_bytes({"a": 1, "b": 2}),
        )

    def test_absolute_bridge_epoch_is_a_locator_not_replay_semantics(self) -> None:
        self.assertEqual(
            canonical_fingerprint_bytes(
                {
                    "relative_epoch": 1,
                    "trace_locators": {
                        "bridge_epoch": 100,
                        "rng_calls_absolute": 7,
                    },
                    "rng": {"seed": 9, "calls_since_trace_start": 2},
                }
            ),
            canonical_fingerprint_bytes(
                {
                    "relative_epoch": 1,
                    "trace_locators": {
                        "bridge_epoch": 900,
                        "rng_calls_absolute": 99,
                    },
                    "rng": {"seed": 9, "calls_since_trace_start": 2},
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
