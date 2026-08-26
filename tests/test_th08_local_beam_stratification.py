from __future__ import annotations

import unittest

from th08_local_planner.beam import (
    _retain_first_action_strata,
    _within_held_action_boundary_window,
)
from th08_local_planner.models import PlannerAction, SearchNode


def _node(
    action: PlannerAction,
    *,
    risk: float,
    collisions: int = 0,
) -> SearchNode:
    return SearchNode(
        x=risk,
        y=0.0,
        first_action=action,
        last_action=action,
        risk=risk,
        collisions=collisions,
        min_clearance=1.0,
        immediate_clearance=1.0,
        collected_mask=0,
        item_utility=0.0,
    )


class LocalBeamStratificationTests(unittest.TestCase):
    def test_boundary_window_uses_one_physical_action_hold(self) -> None:
        common = {
            "playfield_left": 8.0,
            "playfield_right": 376.0,
            "playfield_top": 16.0,
            "playfield_bottom": 432.0,
            "cardinal_speed": 4.0,
            "action_hold_frames": 4,
        }

        self.assertTrue(
            _within_held_action_boundary_window(
                x=356.78,
                y=424.12,
                **common,
            )
        )
        self.assertFalse(
            _within_held_action_boundary_window(
                x=192.0,
                y=400.0,
                **common,
            )
        )

    def test_preserves_each_first_action_only_in_best_hard_class(self) -> None:
        action_a = PlannerAction("a", 0, 0.0, 0.0, True)
        action_b = PlannerAction("b", 0, 0.0, 0.0, True)
        action_c = PlannerAction("c", 0, 0.0, 0.0, True)
        nodes = [
            _node(action_a, risk=0.0),
            _node(action_a, risk=1.0),
            _node(action_b, risk=100.0),
            _node(action_c, risk=-100.0, collisions=1),
        ]

        def key(node: SearchNode, *, step: int) -> tuple[object, ...]:
            self.assertEqual(step, 5)
            return (
                node.collisions,
                0,
                0.0,
                0.0,
                0,
                0.0,
                node.risk,
            )

        retained = _retain_first_action_strata(
            nodes,
            step=5,
            beam_width=2,
            pruning_key=key,
        )

        self.assertEqual(
            [node.first_action.name for node in retained],
            ["a", "b"],
        )
        self.assertEqual([node.risk for node in retained], [0.0, 100.0])


if __name__ == "__main__":
    unittest.main()
