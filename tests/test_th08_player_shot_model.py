#!/usr/bin/env python3
"""Regression tests for the recovered default player-shot path."""

import math
import struct
import unittest
from dataclasses import replace
from pathlib import Path

from th08_player_shot_model import (
    RANDOM_SPREAD_CENTER_BITS,
    RANDOM_SPREAD_DIVISOR_BITS,
    RANDOM_SPREAD_PI_BITS,
    UnsupportedPlayerShotCallback,
    due_shot_records,
    emit_player_shot_level,
    player_shot_overlaps_enemy,
    remilia_bomb_sht_level,
    resolve_default_shot_damage,
    player_shot_feedback_increment,
    random_spread_shot_angle,
    select_player_shot_level,
    select_normal_sht_level,
    shot_damage_contribution,
    spawn_player_shot,
    step_player_shot,
)
from th08_rng import Th08Rng
from th08_sht import parse_sht


ROOT = Path(__file__).resolve().parents[1]
SAKUYA_SHT = ROOT / "artifacts" / "decoded" / "ply02a.sht"
REMILIA_SHT = ROOT / "artifacts" / "decoded" / "ply02as.sht"


def _f32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


class _IndependentRng:
    def __init__(self, state: int, calls: int = 0) -> None:
        self.state = state
        self.calls = calls

    def next_u16(self) -> int:
        mixed = ((self.state ^ 0x9630) - 0x6553) & 0xFFFF
        self.state = ((mixed << 2) + ((mixed & 0xC000) >> 14)) & 0xFFFF
        self.calls += 1
        return self.state

    def next_random_spread_angle(self) -> float:
        value = (self.next_u16() << 16) | self.next_u16()
        signed = value / 2147483648.0 - 1.0
        return _f32(
            signed * _f32_from_bits(RANDOM_SPREAD_PI_BITS)
            / _f32_from_bits(RANDOM_SPREAD_DIVISOR_BITS)
            - _f32_from_bits(RANDOM_SPREAD_CENTER_BITS)
        )


class PlayerShotModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.primary_sht = parse_sht(SAKUYA_SHT)
        cls.secondary_sht = parse_sht(REMILIA_SHT)
        cls.normal = cls.secondary_sht.levels[6]
        cls.last_spell = cls.secondary_sht.levels[7]

    def test_remilia_bomb_level_gate(self) -> None:
        self.assertIsNone(remilia_bomb_sht_level(1, 59))
        self.assertEqual(remilia_bomb_sht_level(1, 60), 6)
        self.assertEqual(remilia_bomb_sht_level(3, 60), 7)
        with self.assertRaises(ValueError):
            remilia_bomb_sht_level(0, 60)

    def test_route2_special_level_invariants(self) -> None:
        self.assertEqual((len(self.normal.shots), len(self.last_spell.shots)), (16, 18))
        for record in (*self.normal.shots, *self.last_spell.shots):
            self.assertEqual(record.shot_type, 6)
            self.assertEqual(record.damage, 45)
            self.assertEqual((record.hitbox_width, record.hitbox_height), (32.0, 16.0))
            self.assertEqual(record.speed, 20.0)
            self.assertEqual(
                (
                    record.callback_0_index,
                    record.callback_1_index,
                    record.callback_2_index,
                    record.callback_3_index,
                ),
                (0, 0, 0, 0),
            )

    def test_shipped_normal_callback_partition(self) -> None:
        self.assertTrue(
            all(
                record.callback_0_index == 0
                for level in self.primary_sht.levels[:6]
                for record in level.shots
            )
        )
        for level in self.secondary_sht.levels[:6]:
            for record in level.shots:
                self.assertEqual(
                    record.callback_0_index,
                    0 if record.source_index == 0 else 7,
                )

    def test_power_thresholds_and_focus_profile_selection(self) -> None:
        expected = {
            0.0: 0,
            7.999: 0,
            8.0: 1,
            23.999: 1,
            24.0: 2,
            48.0: 3,
            80.0: 4,
            128.0: 5,
        }
        for power, index in expected.items():
            native_power, level = select_normal_sht_level(
                self.primary_sht,
                power,
            )
            self.assertEqual(native_power, math.trunc(power))
            self.assertEqual(level.index, index)

        primary = select_player_shot_level(
            self.primary_sht,
            self.secondary_sht,
            focus_logic_value=0,
            power=128.0,
        )
        secondary = select_player_shot_level(
            self.primary_sht,
            self.secondary_sht,
            focus_logic_value=2,
            power=128.0,
        )
        self.assertEqual((primary.profile, primary.level.index), ("primary", 5))
        self.assertEqual(
            (secondary.profile, secondary.level.index),
            ("secondary", 5),
        )

    def test_cadence_zero_emissions(self) -> None:
        normal_due = due_shot_records(self.normal, 0)
        last_due = due_shot_records(self.last_spell, 0)
        self.assertEqual(len(normal_due), 2)
        self.assertEqual(len(last_due), 4)
        self.assertEqual([shot.source_index for shot in normal_due], [1, 1])
        self.assertEqual([shot.source_index for shot in last_due[:2]], [0, 0])

    def test_focused_level5_callback7_rng_and_record_order(self) -> None:
        level = self.secondary_sht.levels[5]
        rng = Th08Rng(45644, 22684)
        independent = _IndependentRng(45644, 22684)
        expected_angles = (
            independent.next_random_spread_angle(),
            independent.next_random_spread_angle(),
        )
        result = emit_player_shot_level(
            level,
            cadence_frame=0,
            player_position=(192.0, 432.0),
            option_positions=((160.0, 420.0),) * 4,
            free_slots=128,
            rng=rng,
        )
        self.assertEqual(
            [shot.record_offset for shot in result.shots],
            [1316, 1372, 1484, 1540],
        )
        self.assertEqual(result.rng_calls_consumed, 4)
        self.assertEqual(rng.calls, independent.calls)
        self.assertEqual(rng.state, independent.state)
        self.assertEqual(
            tuple(shot.angle for shot in result.shots[2:]),
            expected_angles,
        )
        half_width = _f32_from_bits(RANDOM_SPREAD_PI_BITS) / 48.0
        center = -_f32_from_bits(RANDOM_SPREAD_CENTER_BITS)
        self.assertTrue(
            all(
                center - half_width <= shot.angle < center + half_width
                for shot in result.shots[2:]
            )
        )

    def test_retained_stage5_spread_uses_retail_signed_rng(self) -> None:
        rng = Th08Rng(32233)
        angles = (
            random_spread_shot_angle(rng),
            random_spread_shot_angle(rng),
        )

        self.assertEqual(
            tuple(
                struct.unpack("<I", struct.pack("<f", angle))[0]
                for angle in angles
            ),
            (3218062116, 3217486079),
        )
        self.assertEqual((rng.state, rng.calls), (17423, 4))

    def test_pool_capacity_controls_record_scan_and_rng(self) -> None:
        level = self.secondary_sht.levels[5]
        positions = ((0.0, 0.0),) * 4

        full_rng = Th08Rng(45644, 22684)
        full = emit_player_shot_level(
            level,
            cadence_frame=0,
            player_position=(0.0, 0.0),
            option_positions=positions,
            free_slots=0,
            rng=full_rng,
        )
        self.assertEqual((full.records_evaluated, full.rng_calls_consumed), (0, 0))
        self.assertTrue(full.stopped_for_pool_capacity)
        self.assertEqual((full_rng.state, full_rng.calls), (45644, 22684))

        one = emit_player_shot_level(
            level,
            cadence_frame=0,
            player_position=(0.0, 0.0),
            option_positions=positions,
            free_slots=1,
            rng=Th08Rng(45644, 22684),
        )
        self.assertEqual(
            (one.records_evaluated, one.pool_slots_used, one.rng_calls_consumed),
            (1, 1, 0),
        )

        three = emit_player_shot_level(
            level,
            cadence_frame=0,
            player_position=(0.0, 0.0),
            option_positions=positions,
            free_slots=3,
            rng=Th08Rng(45644, 22684),
        )
        self.assertEqual(
            (
                three.records_evaluated,
                three.pool_slots_used,
                three.rng_calls_consumed,
            ),
            (4, 3, 2),
        )

        non_due = emit_player_shot_level(
            level,
            cadence_frame=1,
            player_position=(0.0, 0.0),
            option_positions=positions,
            free_slots=128,
            rng=Th08Rng(45644, 22684),
        )
        self.assertEqual(
            (
                non_due.records_evaluated,
                non_due.pool_slots_used,
                non_due.rng_calls_consumed,
            ),
            (len(level.shots), 0, 0),
        )

    def test_unknown_emission_callback_fails_closed(self) -> None:
        level = self.secondary_sht.levels[5]
        unknown = replace(
            level,
            shots=(
                replace(level.shots[0], callback_0_index=8),
                *level.shots[1:],
            ),
        )
        with self.assertRaises(UnsupportedPlayerShotCallback):
            emit_player_shot_level(
                unknown,
                cadence_frame=1,
                player_position=(0.0, 0.0),
                option_positions=((0.0, 0.0),) * 4,
                free_slots=128,
                rng=Th08Rng(45644, 22684),
            )

    def test_spawn_uses_option_or_player_and_trigonometric_velocity(self) -> None:
        option_record = self.normal.shots[0]
        option_shot = spawn_player_shot(
            option_record,
            player_position=(100.0, 200.0),
            option_positions=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)),
        )
        self.assertEqual((option_shot.x, option_shot.y), (1.0, 2.0))
        self.assertAlmostEqual(option_shot.velocity_x, 0.0, places=5)
        self.assertAlmostEqual(option_shot.velocity_y, -20.0, places=5)

        player_record = self.last_spell.shots[0]
        player_shot = spawn_player_shot(
            player_record,
            player_position=(100.0, 200.0),
            option_positions=(),
        )
        self.assertEqual((player_shot.x, player_shot.y), (100.0, 200.0))
        self.assertAlmostEqual(player_shot.velocity_x, -math.sqrt(200.0), places=5)
        self.assertAlmostEqual(player_shot.velocity_y, -math.sqrt(200.0), places=5)
        self.assertEqual(player_shot.update_callback_index, 0)
        self.assertEqual(player_shot.hit_callback_index, 0)

    def test_spawn_and_motion_round_each_native_float32_store(self) -> None:
        record = replace(
            self.last_spell.shots[0],
            spawn_offset_x=1.0,
            spawn_offset_y=-1.0,
            angle=0.3,
            speed=7.0,
        )
        shot = spawn_player_shot(
            record,
            player_position=(16777216.0, -16777216.0),
            option_positions=(),
        )

        self.assertEqual(shot.x, 16777216.0)
        self.assertEqual(shot.y, -16777216.0)
        self.assertEqual(shot.angle, _f32(0.3))
        self.assertEqual(
            shot.velocity_x,
            _f32(math.cos(_f32(0.3)) * _f32(7.0)),
        )
        self.assertEqual(
            shot.velocity_y,
            _f32(math.sin(_f32(0.3)) * _f32(7.0)),
        )

        moved = step_player_shot(
            replace(
                shot,
                x=16777216.0,
                y=-16777216.0,
                velocity_x=1.0,
                velocity_y=-1.0,
            ),
        )
        self.assertEqual(moved.x, 16777216.0)
        self.assertEqual(moved.y, -16777216.0)

    def test_motion_and_inclusive_aabb_boundary(self) -> None:
        shot = spawn_player_shot(
            self.normal.shots[8],
            player_position=(0.0, 0.0),
            option_positions=((0.0, 0.0),) * 4,
        )
        moved = step_player_shot(shot, time_scale=0.5)
        self.assertAlmostEqual(moved.x, 10.0)
        self.assertTrue(
            player_shot_overlaps_enemy(
                moved,
                enemy_x=27.0,
                enemy_y=0.0,
                enemy_width=2.0,
                enemy_height=2.0,
            )
        )

    def test_bomb_damage_scaling_type6_piercing_and_feedback_cap(self) -> None:
        self.assertEqual(shot_damage_contribution(45, bomb_active=True), 9)
        shots = tuple(
            spawn_player_shot(
                record,
                player_position=(0.0, 0.0),
                option_positions=((0.0, 0.0),) * 4,
            )
            for record in self.last_spell.shots[:6]
        )
        updated, damage = resolve_default_shot_damage(
            shots,
            enemy_x=0.0,
            enemy_y=0.0,
            enemy_width=100.0,
            enemy_height=100.0,
            bomb_active=True,
        )
        self.assertEqual(damage, 54)
        self.assertEqual(player_shot_feedback_increment(damage), 50)
        self.assertTrue(all(shot.state == 1 and shot.active for shot in updated))

    def test_return_damage_is_not_feedback_capped(self) -> None:
        base = spawn_player_shot(
            self.normal.shots[8],
            player_position=(0.0, 0.0),
            option_positions=((0.0, 0.0),) * 4,
        )
        shots = (replace(base, damage=40), replace(base, damage=40))
        _updated, damage = resolve_default_shot_damage(
            shots,
            enemy_x=0.0,
            enemy_y=0.0,
            enemy_width=100.0,
            enemy_height=100.0,
            bomb_active=False,
        )
        self.assertEqual(damage, 80)
        self.assertEqual(player_shot_feedback_increment(damage), 50)

    def test_native_type3_state_and_type45_mode_gates(self) -> None:
        base = spawn_player_shot(
            self.normal.shots[8],
            player_position=(0.0, 0.0),
            option_positions=((0.0, 0.0),) * 4,
        )
        type3 = replace(
            base,
            shot_type=3,
            state=2,
            velocity_x=8.0,
            velocity_y=-16.0,
        )
        self.assertTrue(
            player_shot_overlaps_enemy(
                type3,
                enemy_x=0.0,
                enemy_y=0.0,
                enemy_width=2.0,
                enemy_height=2.0,
            )
        )
        updated, _damage = resolve_default_shot_damage(
            (type3,),
            enemy_x=0.0,
            enemy_y=0.0,
            enemy_width=2.0,
            enemy_height=2.0,
            bomb_active=False,
        )
        self.assertEqual(updated[0].state, 2)
        self.assertEqual(updated[0].velocity_x, 8.0)
        self.assertEqual(updated[0].velocity_y, -16.0)

        type4 = replace(base, shot_type=4)
        with self.assertRaisesRegex(
            UnsupportedPlayerShotCallback,
            "mode-2",
        ):
            player_shot_overlaps_enemy(
                type4,
                enemy_x=0.0,
                enemy_y=0.0,
                enemy_width=2.0,
                enemy_height=2.0,
            )
        self.assertFalse(
            player_shot_overlaps_enemy(
                type4,
                enemy_x=0.0,
                enemy_y=0.0,
                enemy_width=2.0,
                enemy_height=2.0,
                type45_collision_suppressed=True,
            )
        )

    def test_unknown_update_and_hit_callbacks_fail_closed(self) -> None:
        base = spawn_player_shot(
            self.normal.shots[8],
            player_position=(0.0, 0.0),
            option_positions=((0.0, 0.0),) * 4,
        )
        with self.assertRaisesRegex(
            UnsupportedPlayerShotCallback,
            "update callback",
        ):
            step_player_shot(replace(base, update_callback_index=5))
        with self.assertRaisesRegex(
            UnsupportedPlayerShotCallback,
            "hit callback",
        ):
            player_shot_overlaps_enemy(
                replace(base, hit_callback_index=9),
                enemy_x=0.0,
                enemy_y=0.0,
                enemy_width=2.0,
                enemy_height=2.0,
            )


if __name__ == "__main__":
    unittest.main()
