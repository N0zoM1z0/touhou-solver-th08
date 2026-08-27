from __future__ import annotations

import unittest

from th08_linux.planner import (
    LinuxOneEpochPlanner,
    LinuxPlannerConfig,
    LinuxPlannerSnapshot,
    NEUTRAL_GAMEPLAY_MASK,
    validate_lockstep_root_frames,
)
from th08_live.models import Bullet
from th08_live.movement import BOMB, FOCUS, LEFT, SHOT
from th08_local_planner.models import Decision


def _snapshot(
    *,
    player_phase: int = 0,
    bullets: tuple[Bullet, ...] = (),
) -> LinuxPlannerSnapshot:
    return LinuxPlannerSnapshot(
        frame=100,
        player_phase=player_phase,
        player_x=192.0,
        player_y=400.0,
        time_scale_bits=0x3F800000,
        power=0.0,
        bombs=3.0,
        bullets=bullets,
        lasers=(),
        enemy_bodies=(),
        items=(),
    )


class LinuxOneEpochPlannerTests(unittest.TestCase):
    def test_root_validator_rejects_any_capture_drift(self) -> None:
        self.assertEqual(validate_lockstep_root_frames(10, 10, 10), 10)
        with self.assertRaisesRegex(RuntimeError, "root changed"):
            validate_lockstep_root_frames(10, 11, 10)

    def test_contract_is_zero_delay_one_epoch_and_current_root_only(self) -> None:
        captured: dict[str, object] = {}

        def chooser(**kwargs: object) -> Decision:
            captured.update(kwargs)
            return Decision(
                SHOT | FOCUS | LEFT,
                "left",
                12.0,
                12.0,
                0.0,
                False,
            )

        planner = LinuxOneEpochPlanner(
            config=LinuxPlannerConfig(horizon=6, threat_horizon=12),
            chooser=chooser,
        )
        plan = planner.choose(_snapshot(), previous_mask=SHOT | FOCUS)
        self.assertEqual(plan.input_mask, SHOT | FOCUS | LEFT)
        self.assertEqual(captured["control_delay_frames"], 0)
        self.assertEqual(captured["control_delay_candidates"], (0,))
        self.assertEqual(captured["action_hold_frames"], 1)
        self.assertEqual(captured["snapshot_lag"], 0)
        self.assertEqual(captured["bullet_snapshot_age_support"], (0,))
        self.assertFalse(captured["can_bomb"])
        schedule = captured["time_scale_schedule"]
        self.assertEqual(schedule.complete_horizon, 12)
        self.assertIn("assumption", schedule.provenance)

    def test_uncontrollable_player_gets_neutral_shoot_focus_mask(self) -> None:
        def chooser(**_kwargs: object) -> Decision:
            raise AssertionError("planner must not run during death/respawn")

        plan = LinuxOneEpochPlanner(chooser=chooser).choose(
            _snapshot(player_phase=2),
            previous_mask=SHOT | FOCUS | LEFT,
        )
        self.assertEqual(plan.input_mask, NEUTRAL_GAMEPLAY_MASK)
        self.assertIsNone(plan.decision)
        self.assertEqual(plan.reason, "player-uncontrollable")

    def test_bomb_capable_result_fails_closed(self) -> None:
        def chooser(**_kwargs: object) -> Decision:
            return Decision(
                SHOT | FOCUS | BOMB,
                "stay",
                -1.0,
                -1.0,
                1.0,
                True,
            )

        with self.assertRaisesRegex(ValueError, "Bomb input is forbidden"):
            LinuxOneEpochPlanner(chooser=chooser).choose(
                _snapshot(),
                previous_mask=SHOT | FOCUS,
            )

    def test_real_local_planner_moves_for_incoming_bullet_without_bomb(self) -> None:
        planner = LinuxOneEpochPlanner(
            config=LinuxPlannerConfig(
                horizon=4,
                threat_horizon=4,
                beam_width=8,
            )
        )
        plan = planner.choose(
            _snapshot(
                bullets=(
                    Bullet(192.0, 364.0, 0.0, 3.0, 3.0, 3.0),
                )
            ),
            previous_mask=SHOT | FOCUS,
        )
        self.assertNotEqual(plan.action, "stay")
        self.assertFalse(plan.input_mask & BOMB)
        self.assertTrue(plan.input_mask & SHOT)


if __name__ == "__main__":
    unittest.main()
