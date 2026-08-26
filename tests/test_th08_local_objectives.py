from __future__ import annotations

import unittest

import numpy as np

from th08_live.local_objectives import terminal_threat_scores
from th08_local_planner import PlannerAction, SearchNode


class TerminalThreatTests(unittest.TestCase):
    def test_tail_uses_exact_step_callback_and_matching_scale_index(self) -> None:
        action = PlannerAction("right", 0x80, 4.0, 0.0, False)
        node = SearchNode(
            x=10.0,
            y=20.0,
            first_action=action,
            last_action=action,
            risk=0.0,
            collisions=0,
            min_clearance=1.0,
            immediate_clearance=1.0,
            collected_mask=0,
            item_utility=0.0,
        )
        scale_bits = (101, 202, 303, 404)
        advances: list[tuple[float, float, int]] = []
        queried_positions: list[tuple[float, float, int]] = []

        def advance(
            x: float,
            y: float,
            _action: PlannerAction,
            *,
            time_scale_bits: int,
        ) -> tuple[float, float]:
            advances.append((x, y, time_scale_bits))
            increment = time_scale_bits / 100.0
            return x + increment, y - increment

        def hazards(
            positions_x: np.ndarray,
            positions_y: np.ndarray,
            *,
            step: int,
            **_kwargs: object,
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            queried_positions.append(
                (float(positions_x[0]), float(positions_y[0]), step)
            )
            return (
                np.zeros(1, dtype=np.float64),
                np.zeros(1, dtype=np.int32),
                np.full(1, 9.0, dtype=np.float64),
            )

        result = terminal_threat_scores(
            [node],
            hazards_for_positions=hazards,
            advance_action=advance,
            start_step=2,
            end_step=4,
            control_delay_frames=5,
            player_scale_bits=scale_bits,
            bullet_frames=((), (), (), ()),
            laser_frames=((), (), (), ()),
            enemy_bodies=(),
        )

        self.assertEqual(
            [entry[2] for entry in advances],
            [303, 404],
        )
        np.testing.assert_allclose(
            [entry[:2] for entry in advances],
            [(10.0, 20.0), (13.03, 16.97)],
            rtol=0.0,
            atol=2e-6,
        )
        np.testing.assert_allclose(
            queried_positions,
            [(13.03, 16.97, 8), (17.07, 12.93, 9)],
            rtol=0.0,
            atol=2e-6,
        )
        self.assertEqual(result[node], (0, 9.0))

    def test_tail_rejects_incomplete_player_scale_schedule(self) -> None:
        action = PlannerAction("stay", 0, 0.0, 0.0, True)
        node = SearchNode(
            10.0,
            20.0,
            action,
            action,
            0.0,
            0,
            1.0,
            1.0,
            0,
            0.0,
        )

        with self.assertRaisesRegex(ValueError, "does not cover"):
            terminal_threat_scores(
                [node],
                hazards_for_positions=lambda *_args, **_kwargs: (),
                advance_action=lambda x, y, _action, **_kwargs: (x, y),
                start_step=1,
                end_step=3,
                control_delay_frames=0,
                player_scale_bits=(0, 0),
                bullet_frames=((), (), ()),
                laser_frames=((), (), ()),
                enemy_bodies=(),
            )


if __name__ == "__main__":
    unittest.main()
