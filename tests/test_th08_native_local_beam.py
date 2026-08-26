from __future__ import annotations

import unittest

import numpy as np

import th08_live_dodge_agent as live
from touhou_control.native.local_reducers import reduce_local_beam


class NativeLocalBeamTests(unittest.TestCase):
    def test_native_reducer_preserves_best_hard_class_action_leaders(
        self,
    ) -> None:
        if live.native_backend._load_local_beam_reduce_function() is None:
            self.skipTest("native local beam reducer unavailable")
        retained = reduce_local_beam(
            # Action 1 deliberately aliases action 0's best quantized state.
            # First-action identity must survive deduplication before strata
            # are selected.
            draft_x=np.asarray((0.0, 10.0, 0.0), dtype=np.float64),
            draft_y=np.zeros(3, dtype=np.float64),
            first_action=np.asarray((0, 0, 1), dtype=np.int32),
            last_direction=np.zeros(3, dtype=np.int32),
            last_focused=np.ones(3, dtype=np.uint8),
            collected_mask=np.zeros(3, dtype=np.uint32),
            risk=np.asarray((0.0, 1.0, 100.0), dtype=np.float64),
            collisions=np.zeros(3, dtype=np.int32),
            minimum_clearance=np.ones(3, dtype=np.float64),
            step=5,
            beam_width=2,
            position_quantization=0.5,
            target_x=None,
            target_y=None,
            target_deadline=None,
            item_safety_clearance=6.0,
            playfield_left=0.0,
            playfield_right=384.0,
            playfield_top=16.0,
            playfield_bottom=432.0,
            reserve_distance=0.0,
            diagonal_speed=3.25,
            cardinal_speed=4.6,
            certificate_collisions=np.zeros(2, dtype=np.int32),
            certificate_minimum=np.ones(2, dtype=np.float64),
            survival_preferred=np.ones(2, dtype=np.uint8),
            safety_preferred=np.ones(2, dtype=np.uint8),
            recovery_distance=np.zeros(2, dtype=np.float64),
            preserve_first_action_strata=True,
        )

        self.assertEqual(retained.tolist(), [0, 2])

    def test_native_reducer_keeps_legacy_global_reduction_interior(
        self,
    ) -> None:
        if live.native_backend._load_local_beam_reduce_function() is None:
            self.skipTest("native local beam reducer unavailable")
        common = {
            "draft_x": np.asarray((0.0, 10.0, 0.0), dtype=np.float64),
            "draft_y": np.zeros(3, dtype=np.float64),
            "first_action": np.asarray((0, 0, 1), dtype=np.int32),
            "last_direction": np.zeros(3, dtype=np.int32),
            "last_focused": np.ones(3, dtype=np.uint8),
            "collected_mask": np.zeros(3, dtype=np.uint32),
            "risk": np.asarray((0.0, 1.0, 100.0), dtype=np.float64),
            "collisions": np.zeros(3, dtype=np.int32),
            "minimum_clearance": np.ones(3, dtype=np.float64),
            "step": 5,
            "beam_width": 2,
            "position_quantization": 0.5,
            "target_x": None,
            "target_y": None,
            "target_deadline": None,
            "item_safety_clearance": 6.0,
            "playfield_left": 0.0,
            "playfield_right": 384.0,
            "playfield_top": 16.0,
            "playfield_bottom": 432.0,
            "reserve_distance": 0.0,
            "diagonal_speed": 3.25,
            "cardinal_speed": 4.6,
            "certificate_collisions": np.zeros(2, dtype=np.int32),
            "certificate_minimum": np.ones(2, dtype=np.float64),
            "survival_preferred": np.ones(2, dtype=np.uint8),
            "safety_preferred": np.ones(2, dtype=np.uint8),
            "recovery_distance": np.zeros(2, dtype=np.float64),
        }

        retained = reduce_local_beam(
            **common,
            preserve_first_action_strata=False,
        )

        self.assertEqual(retained.tolist(), [0, 1])

    def test_native_reducer_matches_python_decision(self) -> None:
        if live.native_backend._load_local_beam_reduce_function() is None:
            self.skipTest("native local beam reducer unavailable")
        common = {
            "bullets": (
                live.Bullet(192.0, 330.0, 0.0, 2.5, 3.0, 3.0),
                live.Bullet(210.0, 350.0, -1.0, 1.0, 2.0, 2.0),
            ),
            "lasers": (),
            "previous_direction": live.LEFT,
            "previous_focus": True,
            "can_bomb": False,
            "control_delay_frames": 2,
            "control_delay_candidates": (1, 2, 3),
            "action_hold_frames": 3,
            "horizon": 8,
            "threat_horizon": 12,
            "beam_width": 24,
        }
        try:
            for player_x, player_y in (
                (192.0, 360.0),
                (356.0, 424.0),
            ):
                with self.subTest(player_x=player_x, player_y=player_y):
                    arguments = {
                        **common,
                        "player_x": player_x,
                        "player_y": player_y,
                    }
                    live._configure_local_beam_reducer("python")
                    reference = live.choose_action(**arguments)
                    live._configure_local_beam_reducer("native")
                    actual = live.choose_action(**arguments)

                    self.assertEqual(actual.action, reference.action)
                    self.assertEqual(actual.mask, reference.mask)
                    self.assertEqual(
                        actual.robust_collisions,
                        reference.robust_collisions,
                    )
                    self.assertEqual(
                        actual.local_collisions,
                        reference.local_collisions,
                    )
        finally:
            live._configure_local_beam_reducer("python")


if __name__ == "__main__":
    unittest.main()
