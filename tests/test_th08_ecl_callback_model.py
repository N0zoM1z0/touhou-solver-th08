#!/usr/bin/env python3
"""Regression tests for target-route ECL built-in callbacks."""

from __future__ import annotations

import math
import unittest

from th08_ecl_callback_model import (
    CALLBACK_SPECS,
    REIMU_DOUBLE_BARRIER,
    EnemyMotion,
    PortalBullet,
    TaggedBullet,
    callback_2_enemy_motion,
    callback_12_phase_transition,
    callback_12_toggle_tagged_bullet,
    callback_14_cycle_tagged_bullet,
    callback_16_triggers_linked_enemy,
    callback_18_time_scale,
    callback_31_item_type,
    portal_callback_step,
)


class EclCallbackModelTests(unittest.TestCase):
    def test_callback_table_has_all_32_native_entries(self) -> None:
        self.assertEqual(len(CALLBACK_SPECS), 32)
        self.assertEqual(CALLBACK_SPECS[0].address, 0x423390)
        self.assertEqual(CALLBACK_SPECS[31].address, 0x425390)

    def test_double_barrier_inner_to_outer_portal(self) -> None:
        bullet = PortalBullet(112.9, 208.0, -1.0, 0.0, math.pi)
        result, warped = portal_callback_step(bullet, REIMU_DOUBLE_BARRIER)
        self.assertTrue(warped)
        self.assertAlmostEqual(result.x, 33.8, places=3)
        self.assertAlmostEqual(result.vx, 1.0)
        self.assertAlmostEqual(result.angle, 0.0)
        self.assertEqual(result.portal_cooldown, 2)

    def test_double_barrier_outer_to_inner_portal_and_cooldown(self) -> None:
        bullet = PortalBullet(33.7, 208.0, -1.0, 0.0, math.pi)
        result, warped = portal_callback_step(bullet, REIMU_DOUBLE_BARRIER)
        self.assertTrue(warped)
        self.assertAlmostEqual(result.x, 112.85, places=3)
        result, warped = portal_callback_step(result, REIMU_DOUBLE_BARRIER)
        self.assertFalse(warped)
        self.assertEqual(result.portal_cooldown, 1)

    def test_callback_2_reflects_and_recomputes_angle(self) -> None:
        result = callback_2_enemy_motion(
            EnemyMotion(-1.0, 100.0, -2.0, 0.25, 99.0), 0.5, 1.0
        )
        self.assertEqual((result.vx, result.vy), (2.0, 0.75))
        self.assertAlmostEqual(result.angle, math.atan2(0.75, 2.0))

    def test_callback_12_switches_tagged_bullet_velocity_source(self) -> None:
        bullet = TaggedBullet(True, 0x20, 1, 0, 10, 0, 3.0, 4.0, 0.0, 5.0)
        result, changed = callback_12_toggle_tagged_bullet(
            bullet, 0x20, math.pi / 2, 8.0, 0.5
        )
        self.assertTrue(changed)
        self.assertEqual((result.phase_state, result.animation_index), (0, 26))
        self.assertEqual(result.aux_byte, 1)
        self.assertAlmostEqual(result.vx, 0.0, places=6)
        self.assertAlmostEqual(result.vy, 4.0)

        restored, changed = callback_12_toggle_tagged_bullet(
            result, 0x20, math.pi / 2, 8.0, 0.5
        )
        self.assertTrue(changed)
        self.assertEqual(restored.phase_state, 1)
        self.assertEqual(restored.aux_byte, 0)
        self.assertEqual(
            callback_12_phase_transition(1).collision_enabled,
            False,
        )
        self.assertTrue(
            callback_12_phase_transition(0).collision_enabled
        )

    def test_callback_14_cycles_zero_to_two_without_velocity_change(self) -> None:
        bullet = TaggedBullet(True, 1, 0, 0, 10, 0, 3.0, 4.0, 0.0, 5.0)
        result, action = callback_14_cycle_tagged_bullet(bullet, 1, 8.0, 1.0)
        self.assertEqual(action, "phase_0_to_2_animation_15")
        self.assertEqual(result.phase_state, 2)
        self.assertEqual((result.vx, result.vy), (3.0, 4.0))

    def test_callback_16_radius_is_strict(self) -> None:
        self.assertTrue(callback_16_triggers_linked_enemy(63.999, 0, 0, 0))
        self.assertFalse(callback_16_triggers_linked_enemy(64.0, 0, 0, 0))

    def test_time_scale_and_extra_item_callback(self) -> None:
        self.assertEqual(callback_18_time_scale(4), 0.25)
        self.assertEqual(callback_18_time_scale(1), 1.0)
        self.assertEqual(callback_31_item_type(True), 3)
        self.assertEqual(callback_31_item_type(False), 5)


if __name__ == "__main__":
    unittest.main()
