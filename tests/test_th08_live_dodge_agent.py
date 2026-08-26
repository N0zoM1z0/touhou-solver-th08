#!/usr/bin/env python3
"""Tests for the live agent's target-independent short-horizon geometry."""

from __future__ import annotations

import ctypes
import math
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from corridor_planner import (
    CorridorBounds,
    CorridorConfig,
    RobustControlSpec,
    plan_corridor,
)
from th08_laser_model import LaserPhase, LaserState
from th08_live_dodge_agent import (
    ASYNC_POLICY_DELAY_PADDING,
    AutoConfirmPulse,
    Bullet,
    CorridorCommitment,
    CORRIDOR_INITIAL_SUBMIT_FRAME,
    CORRIDOR_REPLAN_FRAMES,
    CORRIDOR_POLICY_MINIMUM_LEAD_FRAMES,
    CorridorSolution,
    DOWN,
    Decision,
    ENEMY_BODY_READ_OFFSET,
    ENEMY_BODY_READ_SIZE,
    ENEMY_CONTACT_SIZE_OFFSET,
    ENEMY_DORMANT_MEMORY_FRAMES,
    ENEMY_FLAGS_OFFSET,
    ENEMY_LOCAL_PREFIX_SIZE,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_POSITION_OFFSET,
    ENEMY_STRIDE,
    ENEMY_VELOCITY_OFFSET,
    EnemyBody,
    EnemyBodyModeMemory,
    EnemyPoolSnapshot,
    GameplaySceneGuard,
    Item,
    ITEM_ACTIVE_OFFSET,
    ITEM_FULL_VALUE_OFFSET,
    ITEM_MOTION_STATE_OFFSET,
    ITEM_POOL_SIZE,
    ITEM_POSITION_OFFSET,
    ITEM_STRIDE,
    ITEM_TYPE_OFFSET,
    ITEM_VELOCITY_OFFSET,
    LASER_ACTIVE_OFFSET,
    LASER_ANGLE_OFFSET,
    LASER_COLLISION_DISABLE_FRAME_OFFSET,
    LASER_COLLISION_ENABLE_FRAME_OFFSET,
    LASER_CURRENT_WIDTH_OFFSET,
    LASER_FADE_FRAMES_OFFSET,
    LASER_FLAGS_OFFSET,
    LASER_HEAD_OFFSET,
    LASER_MAXIMUM_LENGTH_OFFSET,
    LASER_ORIGIN_OFFSET,
    LASER_PHASE_OFFSET,
    LASER_POOL_SIZE,
    LASER_SPEED_OFFSET,
    LASER_STRIDE,
    LASER_TAIL_OFFSET,
    LASER_TIMER_OFFSET,
    LASER_WARMUP_FRAMES_OFFSET,
    LASER_ACTIVE_FRAMES_OFFSET,
    LASER_WIDTH_OFFSET,
    LEFT,
    Laser,
    RIGHT,
    RobustActionCertificate,
    SHOT,
    UP,
    _allow_coarse_viability_relaxation,
    _auto_confirm_eligible,
    _action_name_from_mask,
    _corridor_policy_status,
    _corridor_submit_due,
    _corridor_target,
    _corridor_viability_query,
    _decode_items_if_captured,
    _estimate_live_action_hold,
    _enemy_sensor_submit_due,
    _frozen_auto_confirm_eligible,
    _build_packed_laser_collision_frames,
    _hazards_for_positions,
    _issue_recertification_record,
    _pack_laser_frame,
    _semantic_clock_observation,
    _stage_corridor_solution,
    build_laser_collision_frames,
    capture_enemy_pool_prefix_contiguous,
    choose_action,
    decode_enemy_body,
    decode_enemy_bodies,
    decode_items,
    decode_spell_enemy_body_guard,
    enemy_pointer_in_scanned_pool,
    enemy_pool_snapshot_changes,
    issue_enemy_snapshot_changes,
    decode_lasers,
    decode_player_lethal_aabb,
    merge_spell_enemy_body_guard,
    merge_enemy_pool_prefix,
    issue_transaction_for_fresh_hazards,
    project_enemy_pool_snapshot,
    recertify_action_for_fresh_hazards,
    read_enemy_bodies_sparse,
    serialize_laser_trace,
)
from touhou_control.viability import ControlAction


def _issue_certificates(
    overrides: dict[str, tuple[int, float, float]],
):
    def certificates(*, actions, delay_frames, **_kwargs):
        result = {}
        for action in actions:
            collisions, clearance, cvar = overrides.get(
                action.name,
                (1, -100.0, 100.0),
            )
            result[action.name] = RobustActionCertificate(
                action=action.name,
                delay_frames=delay_frames,
                worst_collisions=collisions,
                min_clearance=clearance,
                cvar_risk=cvar,
                worst_delay=max(delay_frames),
            )
        return result

    return certificates


class LiveDodgeAgentTests(unittest.TestCase):
    def test_exact_corridor_authority_cannot_relax_to_local_fallback(self) -> None:
        self.assertFalse(
            _allow_coarse_viability_relaxation(
                "exact_corridor_viability_v1"
            )
        )
        self.assertTrue(_allow_coarse_viability_relaxation(None))

    def test_async_policy_minimum_covers_two_layers_and_control_latency(
        self,
    ) -> None:
        self.assertEqual(CORRIDOR_POLICY_MINIMUM_LEAD_FRAMES, 16)
        self.assertEqual(CORRIDOR_REPLAN_FRAMES, 8)
        self.assertEqual(ASYNC_POLICY_DELAY_PADDING, 5)

    def test_action_name_preserves_focus_speed_and_native_direction_priority(
        self,
    ) -> None:
        self.assertEqual(_action_name_from_mask(0), "stay")
        self.assertEqual(_action_name_from_mask(LEFT), "left_fast")
        self.assertEqual(_action_name_from_mask(LEFT | 0x04), "left")
        self.assertEqual(
            _action_name_from_mask(UP | LEFT | RIGHT | 0x04),
            "up_left",
        )

    def test_live_action_hold_tracks_recent_controller_cadence(self) -> None:
        self.assertEqual(_estimate_live_action_hold(()), 3)
        self.assertEqual(
            _estimate_live_action_hold((2, 2, 3, 3, 4, 4, 1803)),
            4,
        )
        self.assertEqual(_estimate_live_action_hold((9, 10, 11)), 6)

    def test_enemy_sensor_throttles_completed_background_scans(self) -> None:
        self.assertFalse(
            _enemy_sensor_submit_due(
                current_frame=103,
                last_submit_frame=100,
                pending=False,
            )
        )
        self.assertTrue(
            _enemy_sensor_submit_due(
                current_frame=104,
                last_submit_frame=100,
                pending=False,
            )
        )
        self.assertFalse(
            _enemy_sensor_submit_due(
                current_frame=140,
                last_submit_frame=100,
                pending=True,
            )
        )

    def test_auto_confirm_creates_fresh_z_edge_after_sustained_empty_scene(
        self,
    ) -> None:
        pulse = AutoConfirmPulse(interval_frames=15, idle_frames=20)
        mask, event = pulse.apply(frame=100, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x05, None))
        mask, event = pulse.apply(frame=119, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x05, None))
        mask, event = pulse.apply(frame=120, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x04, "release"))
        mask, event = pulse.apply(frame=121, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x05, "press"))
        mask, event = pulse.apply(frame=135, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x05, None))
        mask, event = pulse.apply(frame=136, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x04, "release"))

    def test_auto_confirm_combat_resets_idle_window_and_restores_z(self) -> None:
        pulse = AutoConfirmPulse(interval_frames=15, idle_frames=2)
        pulse.apply(frame=10, eligible=True, mask=0x05)
        mask, event = pulse.apply(frame=12, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x04, "release"))
        mask, event = pulse.apply(frame=13, eligible=False, mask=0x04)
        self.assertEqual((mask, event), (0x05, "press"))
        mask, event = pulse.apply(frame=14, eligible=True, mask=0x05)
        self.assertEqual((mask, event), (0x05, None))

    def test_auto_confirm_uses_wall_clock_when_game_frame_is_frozen(self) -> None:
        pulse = AutoConfirmPulse(interval_frames=15, idle_frames=20)
        self.assertFalse(
            pulse.frozen_pulse_due(
                now=10.2,
                last_progress=10.0,
                last_pulse=0.0,
                eligible=True,
            )
        )
        self.assertTrue(
            pulse.frozen_pulse_due(
                now=10.34,
                last_progress=10.0,
                last_pulse=0.0,
                eligible=True,
            )
        )
        self.assertFalse(
            pulse.frozen_pulse_due(
                now=10.34,
                last_progress=10.0,
                last_pulse=10.2,
                eligible=True,
            )
        )
        pulse.released = True
        pulse.mark_full_pulse(frame=400)
        self.assertFalse(pulse.released)
        self.assertEqual(pulse.next_release_frame, 415)

    def test_shadow_clock_observation_uses_native_active_input_evidence(
        self,
    ) -> None:
        observation = _semantic_clock_observation(
            {
                "monotonic_end_ns": 1234,
                "manager_frame_after": 77,
                "native_manager_clock_blocked": True,
                "player_after": {"x": 12.0, "y": 34.0},
                "input_after": {"current": LEFT | SHOT},
            },
            fallback_frame=76,
            context=(0, 4),
        )

        self.assertTrue(observation.semantic_active)
        self.assertEqual(observation.physical_frame, 77)
        self.assertEqual(observation.position, (12.0, 34.0))
        self.assertEqual(observation.active_input, LEFT | SHOT)

    def test_auto_confirm_hazard_policy_does_not_gate_on_residual_items(
        self,
    ) -> None:
        self.assertTrue(
            _auto_confirm_eligible(
                player_phase=0,
                bomb_active=False,
                active_bullets=0,
                active_lasers=0,
            )
        )
        self.assertFalse(
            _auto_confirm_eligible(
                player_phase=0,
                bomb_active=False,
                active_bullets=1,
                active_lasers=0,
            )
        )
        self.assertFalse(
            _auto_confirm_eligible(
                player_phase=3,
                bomb_active=True,
                active_bullets=0,
                active_lasers=0,
            )
        )

    def test_frozen_auto_confirm_only_excludes_an_active_bomb(self) -> None:
        # Projectile and item state are deliberately absent: once the manager
        # counter is frozen, neither can evolve into a collision.
        self.assertTrue(_frozen_auto_confirm_eligible(bomb_active=False))
        self.assertFalse(_frozen_auto_confirm_eligible(bomb_active=True))

    def test_scene_guard_waits_for_nonfinal_stage_transition(self) -> None:
        guard = GameplaySceneGuard({0: 1, 1: 2}, 90.0, 5.0)
        active = guard.observe(
            gameplay_active=True,
            current_stage=0,
            now=10.0,
        )
        self.assertEqual(active.status, "active")
        entered = guard.observe(
            gameplay_active=False,
            current_stage=0,
            now=11.0,
        )
        self.assertEqual(entered.status, "stage_transition")
        self.assertTrue(entered.entered)
        waiting = guard.observe(
            gameplay_active=False,
            current_stage=1,
            now=16.0,
        )
        self.assertEqual(waiting.status, "stage_transition")
        self.assertEqual(waiting.transition_from_stage, 0)
        self.assertEqual(waiting.expected_stage, 1)
        resumed = guard.observe(
            gameplay_active=True,
            current_stage=1,
            now=17.0,
        )
        self.assertEqual(resumed.status, "resumed")
        self.assertEqual(resumed.inactive_seconds, 6.0)

    def test_scene_guard_does_not_reclassify_stage5_transition_as_final(self) -> None:
        guard = GameplaySceneGuard({5: 7}, 90.0, 5.0)
        guard.observe(gameplay_active=True, current_stage=5, now=1.0)
        early_index_write = guard.observe(
            gameplay_active=True,
            current_stage=7,
            now=1.5,
        )
        self.assertEqual(early_index_write.status, "active")
        self.assertEqual(guard.last_active_stage, 5)
        guard.observe(gameplay_active=False, current_stage=5, now=2.0)
        waiting = guard.observe(
            gameplay_active=False,
            current_stage=7,
            now=10.0,
        )
        self.assertEqual(waiting.status, "stage_transition")
        self.assertEqual(waiting.transition_from_stage, 5)
        self.assertEqual(waiting.expected_stage, 7)

    def test_scene_guard_requires_stable_final_unload(self) -> None:
        guard = GameplaySceneGuard({5: 7}, 90.0, 5.0)
        guard.observe(gameplay_active=True, current_stage=7, now=20.0)
        entered = guard.observe(
            gameplay_active=False,
            current_stage=7,
            now=21.0,
        )
        self.assertEqual(entered.status, "terminal_unload")
        self.assertTrue(entered.entered)
        waiting = guard.observe(
            gameplay_active=False,
            current_stage=7,
            now=25.9,
        )
        self.assertEqual(waiting.status, "terminal_unload")
        finished = guard.observe(
            gameplay_active=False,
            current_stage=7,
            now=26.0,
        )
        self.assertEqual(finished.status, "route_complete")

    def test_scene_guard_reports_transition_timeout(self) -> None:
        guard = GameplaySceneGuard({0: 1}, 10.0, 5.0)
        guard.observe(gameplay_active=True, current_stage=0, now=1.0)
        guard.observe(gameplay_active=False, current_stage=0, now=2.0)
        timed_out = guard.observe(
            gameplay_active=False,
            current_stage=0,
            now=12.0,
        )
        self.assertEqual(timed_out.status, "stage_transition_timeout")

    def test_clear_field_returns_finite_clearance(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            can_bomb=False,
        )
        self.assertEqual(decision.action, "stay")
        self.assertEqual(decision.min_clearance, 9999.0)
        self.assertEqual(decision.immediate_clearance, 9999.0)
        self.assertTrue(math.isfinite(decision.score))

    def test_damage_shadow_only_ranks_the_fresh_viable_action_set(self) -> None:
        common = {
            "player_x": 100.0,
            "player_y": 400.0,
            "bullets": (),
            "lasers": (),
            "previous_direction": 0,
            "can_bomb": False,
            "control_delay_frames": 1,
            "control_delay_candidates": (1,),
            "horizon": 2,
            "threat_horizon": 2,
            "action_hold_frames": 1,
            "beam_width": 64,
            "allowed_first_actions": ("stay", "left", "right"),
            "damage_target_x": 300.0,
            "damage_target_half_width": 10.0,
            "damageable": True,
        }
        shadow = choose_action(**common)
        self.assertEqual(shadow.action, "stay")
        self.assertEqual(shadow.damage_shadow_action, "right")
        restricted = choose_action(
            **{**common, "allowed_first_actions": ("stay",)}
        )
        self.assertEqual(restricted.damage_shadow_action, "stay")

    def test_native_enemy_body_window_decodes_scaled_lethal_extents(
        self,
    ) -> None:
        blob = bytearray(ENEMY_BODY_READ_SIZE)
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_VELOCITY_OFFSET - ENEMY_BODY_READ_OFFSET,
            1.5,
            -0.5,
        )
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET,
            32.0,
            24.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_POSITION_OFFSET - ENEMY_BODY_READ_OFFSET,
            178.0,
            120.0,
        )
        struct.pack_into(
            "<I",
            blob,
            ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET,
            0x05,
        )
        body = decode_enemy_body(bytes(blob), pointer=0x5826C0)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(
            (body.half_width, body.half_height),
            (10.666666984558105, 8.0),
        )
        self.assertEqual((body.vx, body.vy), (0.0, 0.0))
        self.assertEqual((body.internal_vx, body.internal_vy), (1.5, -0.5))
        struct.pack_into(
            "<I",
            blob,
            ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET,
            0x01,
        )
        self.assertIsNone(
            decode_enemy_body(bytes(blob), pointer=0x5826C0)
        )

    def test_full_enemy_pool_retains_nonspell_contact_slots(self) -> None:
        blob = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        slot = 17
        base = slot * ENEMY_STRIDE
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_VELOCITY_OFFSET,
            -1.0,
            2.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_CONTACT_SIZE_OFFSET,
            20.0,
            12.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_POSITION_OFFSET,
            144.0,
            96.0,
        )
        struct.pack_into(
            "<I",
            blob,
            base + ENEMY_FLAGS_OFFSET,
            0x05,
        )
        bodies = decode_enemy_bodies(bytes(blob))
        self.assertEqual(len(bodies), 1)
        self.assertEqual(
            bodies[0].pointer,
            ENEMY_POOL_BASE + slot * ENEMY_STRIDE,
        )
        self.assertEqual(
            (bodies[0].half_width, bodies[0].half_height),
            (6.666666507720947, 4.0),
        )

    def test_ce_0094_prefix_retains_latent_contact_disabled_body(self) -> None:
        blob = bytearray(ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE)
        slot = 18
        base = slot * ENEMY_STRIDE
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_VELOCITY_OFFSET,
            -0.11290890723466873,
            3.198007583618164,
        )
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_CONTACT_SIZE_OFFSET,
            24.0,
            24.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_POSITION_OFFSET,
            156.9927892908454,
            331.7983570098877,
        )
        struct.pack_into(
            "<I",
            blob,
            base + ENEMY_FLAGS_OFFSET,
            0x01,
        )
        self.assertEqual(
            decode_enemy_bodies(
                bytes(blob),
                pool_size=ENEMY_LOCAL_PREFIX_SIZE,
            ),
            (),
        )
        latent = decode_enemy_bodies(
            bytes(blob),
            pool_size=ENEMY_LOCAL_PREFIX_SIZE,
            include_contact_disabled=True,
        )
        self.assertEqual(len(latent), 1)
        self.assertEqual(
            latent[0].pointer,
            ENEMY_POOL_BASE + slot * ENEMY_STRIDE,
        )
        self.assertEqual(
            (latent[0].half_width, latent[0].half_height),
            (8.0, 8.0),
        )

        class Reader:
            def u32(self, _address: int) -> int:
                return 9806

            def read(self, _address: int, _size: int) -> bytes:
                return bytes(blob)

        snapshot = capture_enemy_pool_prefix_contiguous(Reader())
        self.assertEqual(snapshot.bodies, latent)

    def test_ce_0176_prefix_retains_character_blocked_mode_body(self) -> None:
        blob = bytearray(ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE)
        slot = 15
        base = slot * ENEMY_STRIDE
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_CONTACT_SIZE_OFFSET,
            24.0,
            24.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            base + ENEMY_POSITION_OFFSET,
            192.0,
            300.0,
        )
        struct.pack_into(
            "<I",
            blob,
            base + ENEMY_FLAGS_OFFSET,
            0x0100194D,
        )
        self.assertEqual(
            decode_enemy_bodies(
                bytes(blob),
                pool_size=ENEMY_LOCAL_PREFIX_SIZE,
            ),
            (),
        )
        latent = decode_enemy_bodies(
            bytes(blob),
            pool_size=ENEMY_LOCAL_PREFIX_SIZE,
            include_contact_disabled=True,
        )
        self.assertEqual(len(latent), 1)
        self.assertEqual(latent[0].flags, 0x0100194D)
        self.assertEqual(
            latent[0].pointer,
            ENEMY_POOL_BASE + slot * ENEMY_STRIDE,
        )

    def test_ce_0094_contact_toggle_is_a_mode_change_not_a_respawn(self) -> None:
        disabled = EnemyBody(
            ENEMY_POOL_BASE + 18 * ENEMY_STRIDE,
            156.9927892908454,
            331.7983570098877,
            -0.11290890723466873,
            3.198007583618164,
            18.0,
            18.0,
            0x01,
        )
        enabled = replace(
            disabled,
            x=disabled.x + 3.0 * disabled.vx,
            y=disabled.y + 3.0 * disabled.vy,
            flags=0x05,
        )
        self.assertEqual(
            enemy_pool_snapshot_changes(
                EnemyPoolSnapshot(9806, 9806, (disabled,), 1.0),
                EnemyPoolSnapshot(9809, 9809, (enabled,), 1.0),
            ),
            (f"contact_mode:{disabled.pointer:#x}",),
        )

    def test_ce_0094_dormant_memory_avoids_frame_36180_reactivation(
        self,
    ) -> None:
        memory = EnemyBodyModeMemory(
            maximum_age_frames=ENEMY_DORMANT_MEMORY_FRAMES
        )
        memory.set_context((0, 3, None))
        body = EnemyBody(
            5970192,
            99.62682342529297,
            286.17047119140625,
            1.4705986976623535,
            2.8420660495758057,
            18.0,
            18.0,
            285217101,
        )
        observed, dormant = memory.merge_snapshot(
            EnemyPoolSnapshot(36144, 36144, (body,), 1.0),
            frame=36144,
        )
        self.assertEqual(observed, (body,))
        self.assertEqual(dormant, frozenset())
        projected, dormant = memory.merge_snapshot(
            EnemyPoolSnapshot(36171, 36171, (), 1.0),
            frame=36171,
        )
        self.assertEqual(dormant, frozenset((body.pointer,)))
        self.assertEqual(projected[0].uncertainty, 16.0)

        stale_decision = Decision(
            SHOT | UP | LEFT,
            "up_left_fast",
            9.381558418273926,
            9.381558418273926,
            0.0,
            False,
            planned_focus=False,
            robust_delay_frames=(3, 4, 5, 6),
            robust_min_clearance=9.381558418273926,
        )
        corrected = recertify_action_for_fresh_hazards(
            stale_decision,
            player_x=172.36550903320312,
            player_y=432.0,
            previous_mask=SHOT | DOWN | RIGHT,
            delay_frames=(3, 4, 5, 6),
            action_hold_frames=6,
            bullets=(),
            lasers=(),
            enemy_bodies=projected,
            snapshot_lag=1,
        )
        self.assertEqual(corrected.action, "right_fast")
        self.assertTrue(corrected.robust_override)
        self.assertEqual(corrected.robust_collisions, 0)
        self.assertGreater(corrected.robust_min_clearance, 0.0)

    def test_dormant_enemy_memory_expires_and_resets_by_context(self) -> None:
        memory = EnemyBodyModeMemory(maximum_age_frames=10)
        body = EnemyBody(
            ENEMY_POOL_BASE,
            100.0,
            120.0,
            1.0,
            2.0,
            18.0,
            18.0,
            0x05,
        )
        memory.set_context((0, 3, None))
        memory.merge_snapshot(
            EnemyPoolSnapshot(100, 100, (body,), 1.0),
            frame=100,
        )
        projected, dormant = memory.merge_snapshot(
            EnemyPoolSnapshot(110, 110, (), 1.0),
            frame=110,
        )
        self.assertEqual(len(projected), 1)
        self.assertEqual(dormant, frozenset((body.pointer,)))
        expired, dormant = memory.merge_snapshot(
            EnemyPoolSnapshot(111, 111, (), 1.0),
            frame=111,
        )
        self.assertEqual(expired, ())
        self.assertEqual(dormant, frozenset())
        memory.merge_snapshot(
            EnemyPoolSnapshot(112, 112, (body,), 1.0),
            frame=112,
        )
        self.assertTrue(memory.set_context((0, 3, 57)))
        cleared, dormant = memory.merge_snapshot(
            EnemyPoolSnapshot(113, 113, (), 1.0),
            frame=113,
        )
        self.assertEqual(cleared, ())
        self.assertEqual(dormant, frozenset())

    def test_ce_0096_internal_motion_component_is_not_world_velocity(
        self,
    ) -> None:
        memory = EnemyBodyModeMemory(maximum_age_frames=80)
        memory.set_context((0, 3, None))
        pointer = 5862912
        samples = (
            (28779, 381.9375305175781, 14.763214111328125, 18.511810302734375),
            (28784, -8.736358642578125, 14.07257080078125, 32.55963134765625),
            (28788, 59.03617858886719, 13.209136962890625, 49.1673583984375),
            (28792, 110.14616394042969, 12.518463134765625, 61.691925048828125),
            (28796, 158.49349975585938, 11.827789306640625, 73.53948974609375),
            (28800, 204.078125, 11.137115478515625, 84.71005249023438),
            (28803, 246.89999389648438, 10.446441650390625, 95.20358276367188),
            (28807, 277.2033996582031, 9.928497314453125, 102.62945556640625),
            (28811, 315.1906433105469, 9.23785400390625, 111.93829345703125),
            (28815, 350.4150695800781, 8.547149658203125, 120.570068359375),
            (28818, 382.8768310546875, 7.85650634765625, 128.52484130859375),
            (28822, 405.41009521484375, 7.33837890625, 134.04666137695312),
            (28826, -14.962890625, 6.647705078125, 140.81668090820312),
            (28830, 9.9014892578125, 5.95709228515625, 146.90972900390625),
        )
        tracked = ()
        for frame, x, internal_x, internal_y in samples:
            body = EnemyBody(
                pointer,
                x,
                164.0,
                0.0,
                0.0,
                36.0,
                24.0,
                287907919,
                internal_vx=internal_x,
                internal_vy=internal_y,
            )
            tracked, dormant = memory.merge_snapshot(
                EnemyPoolSnapshot(frame, frame, (body,), 1.0),
                frame=frame,
            )
            self.assertEqual(dormant, frozenset())

        self.assertEqual(len(tracked), 1)
        estimated = tracked[0]
        self.assertAlmostEqual(estimated.vx, 6.216094970703125)
        self.assertEqual(estimated.vy, 0.0)
        self.assertEqual(estimated.internal_vy, 146.90972900390625)
        self.assertEqual(estimated.y + 6.0 * estimated.vy, 164.0)
        self.assertLess(
            abs(178.264404296875 - estimated.y)
            - (2.0 + estimated.half_height),
            0.0,
        )

    def test_ce_0096_issue_guard_uses_aligned_world_trajectory(self) -> None:
        pointer = ENEMY_POOL_BASE
        raw_before = EnemyBody(
            pointer,
            100.0,
            120.0,
            0.0,
            0.0,
            18.0,
            18.0,
            0x05,
            internal_vx=1.0,
            internal_vy=90.0,
        )
        raw_after = replace(raw_before, x=110.0)
        self.assertEqual(
            enemy_pool_snapshot_changes(
                EnemyPoolSnapshot(100, 100, (raw_before,), 1.0),
                EnemyPoolSnapshot(102, 102, (raw_after,), 1.0),
            ),
            (f"trajectory:{pointer:#x}",),
        )
        aligned_before = replace(raw_before, vx=5.0)
        aligned_after = replace(raw_after, x=100.0, vx=5.0)
        self.assertEqual(
            issue_enemy_snapshot_changes(
                EnemyPoolSnapshot(100, 100, (raw_before,), 1.0),
                EnemyPoolSnapshot(102, 102, (raw_after,), 1.0),
                EnemyPoolSnapshot(90, 90, (aligned_before,), 1.0),
                EnemyPoolSnapshot(90, 90, (aligned_after,), 1.0),
            ),
            (),
        )

    def test_ce_0090_latent_spell_owner_replaces_stale_pool_body(self) -> None:
        # The historical solver treated source slot 0 as a special record,
        # but SpawnEnemy1/2 and OnUpdate both include it in enemies[0..479].
        pointer = ENEMY_POOL_BASE - ENEMY_STRIDE
        self.assertEqual(pointer, 0x57D2F0)
        self.assertTrue(enemy_pointer_in_scanned_pool(pointer))
        self.assertTrue(enemy_pointer_in_scanned_pool(ENEMY_POOL_BASE))
        self.assertTrue(
            enemy_pointer_in_scanned_pool(
                pointer + (ENEMY_POOL_SIZE - 1) * ENEMY_STRIDE
            )
        )
        self.assertFalse(
            enemy_pointer_in_scanned_pool(
                pointer + ENEMY_POOL_SIZE * ENEMY_STRIDE
            )
        )
        blob = bytearray(ENEMY_BODY_READ_SIZE)
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_VELOCITY_OFFSET - ENEMY_BODY_READ_OFFSET,
            0.0,
            0.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET,
            32.0,
            24.0,
        )
        struct.pack_into(
            "<ff",
            blob,
            ENEMY_POSITION_OFFSET - ENEMY_BODY_READ_OFFSET,
            192.0,
            96.0,
        )
        # Active owner, but contact mode has not yet enabled.
        struct.pack_into(
            "<I",
            blob,
            ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET,
            0x01,
        )
        self.assertIsNone(decode_enemy_body(bytes(blob), pointer=pointer))
        guard = decode_spell_enemy_body_guard(bytes(blob), pointer=pointer)
        self.assertIsNotNone(guard)
        assert guard is not None
        self.assertEqual(
            (guard.raw_contact_width, guard.raw_contact_height),
            (32.0, 24.0),
        )
        self.assertFalse(guard.contact_enabled)
        stale = EnemyBody(pointer, 180.0, 80.0, 0.0, 0.0, 1.0, 1.0, 5)
        other = EnemyBody(pointer + ENEMY_STRIDE, 40.0, 40.0, 0.0, 0.0, 2.0, 2.0, 5)
        merged = merge_spell_enemy_body_guard((stale, other), guard)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0], other)
        self.assertEqual(merged[1], guard.body)

    def test_ce_0090_latent_spell_owner_blocks_post_spell_item_chase(
        self,
    ) -> None:
        decision = choose_action(
            player_x=184.5,
            player_y=192.7,
            bullets=(),
            lasers=(),
            enemy_bodies=(
                EnemyBody(
                    ENEMY_POOL_BASE,
                    192.0,
                    96.0,
                    0.0,
                    0.0,
                    24.0,
                    18.0,
                    0x01,
                ),
            ),
            items=(Item(1891, 222.0, 62.5, 0.0, -0.1, 0, 0, False),),
            power=39.0,
            bombs=4.0,
            previous_direction=UP,
            previous_focus=False,
            can_bomb=False,
            snapshot_lag=0,
            control_delay_frames=5,
            control_delay_candidates=(3, 4, 5, 6),
            action_hold_frames=5,
            horizon=10,
            threat_horizon=32,
        )
        self.assertNotIn(decision.action, {"up", "up_fast"})
        self.assertGreaterEqual(decision.robust_min_clearance, 0.0)

    def test_sparse_enemy_reader_fetches_only_contact_enabled_windows(
        self,
    ) -> None:
        active_slot = 17
        active_pointer = ENEMY_POOL_BASE + active_slot * ENEMY_STRIDE
        body_blob = bytearray(ENEMY_BODY_READ_SIZE)
        struct.pack_into(
            "<ff",
            body_blob,
            ENEMY_VELOCITY_OFFSET - ENEMY_BODY_READ_OFFSET,
            -1.0,
            2.0,
        )
        struct.pack_into(
            "<ff",
            body_blob,
            ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET,
            20.0,
            12.0,
        )
        struct.pack_into(
            "<ff",
            body_blob,
            ENEMY_POSITION_OFFSET - ENEMY_BODY_READ_OFFSET,
            144.0,
            96.0,
        )
        struct.pack_into(
            "<I",
            body_blob,
            ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET,
            0x05,
        )

        class Reader:
            def __init__(self) -> None:
                self.body_reads = []

            def u32(self, address: int) -> int:
                slot = (address - ENEMY_POOL_BASE - ENEMY_FLAGS_OFFSET) // (
                    ENEMY_STRIDE
                )
                return 0x05 if slot == active_slot else 0x01

            def read(self, address: int, size: int) -> bytes:
                self.body_reads.append((address, size))
                return bytes(body_blob)

        reader = Reader()
        bodies = read_enemy_bodies_sparse(reader)
        self.assertEqual([body.pointer for body in bodies], [active_pointer])
        self.assertEqual(
            reader.body_reads,
            [(active_pointer + ENEMY_BODY_READ_OFFSET, ENEMY_BODY_READ_SIZE)],
        )

    def test_sparse_enemy_reader_includes_active_manager_singleton(self) -> None:
        body_blob = bytearray(ENEMY_BODY_READ_SIZE)
        struct.pack_into(
            "<ff",
            body_blob,
            ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET,
            24.0,
            24.0,
        )
        struct.pack_into(
            "<ff",
            body_blob,
            ENEMY_POSITION_OFFSET - ENEMY_BODY_READ_OFFSET,
            60.0,
            32.0,
        )
        struct.pack_into(
            "<I",
            body_blob,
            ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET,
            0x05,
        )

        class Reader:
            def u32(self, address: int) -> int:
                return (
                    0x05
                    if address
                    == ENEMY_MANAGER_TEMPLATE_BASE + ENEMY_FLAGS_OFFSET
                    else 0
                )

            def read(self, address: int, size: int) -> bytes:
                self.assert_read = (address, size)
                return bytes(body_blob)

        reader = Reader()
        bodies = read_enemy_bodies_sparse(reader)

        self.assertEqual(
            [body.pointer for body in bodies],
            [ENEMY_MANAGER_TEMPLATE_BASE],
        )
        self.assertEqual(
            reader.assert_read,
            (
                ENEMY_MANAGER_TEMPLATE_BASE + ENEMY_BODY_READ_OFFSET,
                ENEMY_BODY_READ_SIZE,
            ),
        )

    def test_local_enemy_prefix_is_one_contiguous_native_read(self) -> None:
        blob = bytes(ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE)

        class Reader:
            def __init__(self) -> None:
                self.reads = []

            def u32(self, _address: int) -> int:
                return 100

            def read(self, address: int, size: int) -> bytes:
                self.reads.append((address, size))
                return blob

        reader = Reader()
        snapshot = capture_enemy_pool_prefix_contiguous(reader)
        self.assertTrue(snapshot.stable)
        self.assertEqual(snapshot.attempts, 1)
        self.assertEqual(snapshot.bodies, ())
        self.assertEqual(
            reader.reads,
            [
                (
                    ENEMY_POOL_BASE,
                    ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE,
                )
            ],
        )

    def test_local_enemy_prefix_reuses_destination_without_snapshot_alias(
        self,
    ) -> None:
        read_size = ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE

        def body_blob(x: float) -> bytes:
            blob = bytearray(read_size)
            struct.pack_into(
                "<ff",
                blob,
                ENEMY_CONTACT_SIZE_OFFSET,
                24.0,
                24.0,
            )
            struct.pack_into(
                "<ff",
                blob,
                ENEMY_POSITION_OFFSET,
                x,
                300.0,
            )
            struct.pack_into("<I", blob, ENEMY_FLAGS_OFFSET, 0x05)
            return bytes(blob)

        class Reader:
            def __init__(self) -> None:
                self.frames = iter((100, 100, 101, 101))
                self.blobs = iter((body_blob(120.0), body_blob(240.0)))
                self.events = []

            def u32(self, _address: int) -> int:
                frame = next(self.frames)
                self.events.append(("frame", frame))
                return frame

            def read(self, _address: int, _size: int) -> bytes:
                raise AssertionError("persistent capture must not allocate")

            def read_into(self, address: int, destination: bytearray):
                self.events.append(
                    ("read_into", address, id(destination), len(destination))
                )
                destination[:] = next(self.blobs)
                return destination

        reader = Reader()
        destination = bytearray(read_size)
        first = capture_enemy_pool_prefix_contiguous(
            reader,
            pool_buffer=destination,
        )
        second = capture_enemy_pool_prefix_contiguous(
            reader,
            pool_buffer=destination,
        )

        self.assertEqual(first.bodies[0].x, 120.0)
        self.assertEqual(second.bodies[0].x, 240.0)
        self.assertEqual(first.bodies[0].x, 120.0)
        read_events = [event for event in reader.events if event[0] == "read_into"]
        self.assertEqual(
            read_events,
            [
                ("read_into", ENEMY_POOL_BASE, id(destination), read_size),
                ("read_into", ENEMY_POOL_BASE, id(destination), read_size),
            ],
        )
        self.assertEqual(
            [event[0] for event in reader.events],
            ["frame", "read_into", "frame"] * 2,
        )

    def test_local_enemy_prefix_rejects_wrong_destination_size(self) -> None:
        class Reader:
            pass

        with self.assertRaisesRegex(ValueError, "exactly match"):
            capture_enemy_pool_prefix_contiguous(
                Reader(),
                pool_buffer=bytearray(1),
            )

    def test_local_enemy_prefix_rejects_read_only_destination(self) -> None:
        class Reader:
            pass

        with self.assertRaisesRegex(ValueError, "writable"):
            capture_enemy_pool_prefix_contiguous(
                Reader(),
                pool_buffer=bytes(
                    ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE
                ),
            )

    def test_local_enemy_prefix_retries_one_crossed_frame_snapshot(
        self,
    ) -> None:
        blob = bytes(ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE)

        class Reader:
            def __init__(self) -> None:
                self.frames = iter((100, 101, 102, 102))
                self.reads = 0

            def u32(self, _address: int) -> int:
                return next(self.frames)

            def read(self, _address: int, _size: int) -> bytes:
                self.reads += 1
                return blob

        reader = Reader()
        snapshot = capture_enemy_pool_prefix_contiguous(reader)
        self.assertTrue(snapshot.stable)
        self.assertEqual(snapshot.attempts, 2)
        self.assertEqual(reader.reads, 2)

    def test_async_enemy_snapshot_projects_age_with_bounded_uncertainty(
        self,
    ) -> None:
        snapshot = EnemyPoolSnapshot(
            100,
            101,
            (
                EnemyBody(
                    ENEMY_POOL_BASE,
                    20.0,
                    40.0,
                    2.0,
                    -1.0,
                    12.0,
                    8.0,
                    0x05,
                ),
            ),
            14.0,
        )
        projected = project_enemy_pool_snapshot(snapshot, frame=105)[0]
        self.assertEqual((projected.x, projected.y), (28.0, 36.0))
        self.assertEqual(projected.uncertainty, 3.0)

    def test_fresh_enemy_prefix_backprojects_and_replaces_stale_slots(
        self,
    ) -> None:
        stale = EnemyBody(
            ENEMY_POOL_BASE,
            20.0,
            40.0,
            0.0,
            0.0,
            12.0,
            8.0,
            0x05,
        )
        outside_prefix = EnemyBody(
            ENEMY_POOL_BASE + ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE,
            300.0,
            80.0,
            0.0,
            0.0,
            8.0,
            8.0,
            0x05,
        )
        fresh_snapshot = EnemyPoolSnapshot(
            104,
            104,
            (
                EnemyBody(
                    ENEMY_POOL_BASE,
                    36.0,
                    32.0,
                    2.0,
                    -1.0,
                    12.0,
                    8.0,
                    0x05,
                ),
            ),
            2.0,
        )
        fresh = project_enemy_pool_snapshot(fresh_snapshot, frame=100)
        merged = merge_enemy_pool_prefix(
            (stale, outside_prefix),
            fresh,
        )
        self.assertEqual(
            [body.pointer for body in merged],
            [ENEMY_POOL_BASE, outside_prefix.pointer],
        )
        self.assertEqual((merged[0].x, merged[0].y), (28.0, 36.0))
        self.assertEqual(merged[0].uncertainty, 3.0)

    def test_ce_0092_synchronous_prefix_exposes_new_contact_ring(
        self,
    ) -> None:
        stale_boss_only = (
            EnemyBody(
                ENEMY_POOL_BASE,
                192.0,
                96.0,
                0.0,
                0.0,
                18.0,
                18.0,
                0x05,
            ),
        )
        fresh_ring = tuple(
            EnemyBody(
                ENEMY_POOL_BASE + slot * ENEMY_STRIDE,
                192.0 + slot,
                128.0,
                0.0,
                2.0,
                18.0,
                18.0,
                0x05,
            )
            for slot in range(1, 19)
        )
        merged = merge_enemy_pool_prefix(stale_boss_only, fresh_ring)
        self.assertEqual(len(merged), 18)
        self.assertEqual(
            {body.pointer for body in merged},
            {body.pointer for body in fresh_ring},
        )
        before = EnemyPoolSnapshot(
            35412,
            35412,
            stale_boss_only,
            1.0,
        )
        after = EnemyPoolSnapshot(
            35415,
            35415,
            stale_boss_only + fresh_ring,
            1.0,
        )
        changes = enemy_pool_snapshot_changes(before, after)
        self.assertEqual(
            sum(change.startswith("added:") for change in changes),
            18,
        )

    def test_issue_enemy_guard_accepts_expected_linear_motion(self) -> None:
        before_body = EnemyBody(
            ENEMY_POOL_BASE + 3 * ENEMY_STRIDE,
            80.0,
            120.0,
            1.5,
            -0.5,
            18.0,
            12.0,
            0x05,
        )
        after_body = replace(
            before_body,
            x=84.5,
            y=118.5,
        )
        self.assertEqual(
            enemy_pool_snapshot_changes(
                EnemyPoolSnapshot(100, 100, (before_body,), 1.0),
                EnemyPoolSnapshot(103, 103, (after_body,), 1.0),
            ),
            (),
        )

    def test_ce_0092_issue_time_ring_recertifies_stale_up_right(self) -> None:
        stale_decision = Decision(
            SHOT | UP | RIGHT,
            "up_right_fast",
            27.55,
            27.55,
            0.0,
            False,
            planned_focus=False,
            robust_delay_frames=(3, 4, 5, 6),
            robust_min_clearance=27.55,
        )
        # Exact Stage-4A contact body back-projected from stable frame 35420
        # to the causal player snapshot at frame 35412.
        body = EnemyBody(
            6163296,
            344.0525817871094,
            110.52362060546875,
            -2.274150848388672,
            2.251274824142456,
            18.0,
            18.0,
            285217101,
            6.0,
        )
        corrected = recertify_action_for_fresh_hazards(
            stale_decision,
            player_x=306.51348876953125,
            player_y=147.7181396484375,
            previous_mask=SHOT | UP | RIGHT,
            delay_frames=(3, 4, 5, 6),
            action_hold_frames=4,
            bullets=(),
            lasers=(),
            enemy_bodies=(body,),
            snapshot_lag=1,
        )
        self.assertNotEqual(corrected.action, "up_right_fast")
        self.assertTrue(corrected.robust_override)
        self.assertLess(corrected.robust_min_clearance, 0.0)

    def test_ce_0127_issue_recertification_preserves_safe_planned_action(
        self,
    ) -> None:
        decision = Decision(
            SHOT | UP,
            "up_fast",
            10.0,
            10.0,
            0.0,
            False,
            viability_constrained=True,
            viability_safe_action_count=2,
        )
        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=_issue_certificates(
                {
                    "up_fast": (0, 1.0, 10.0),
                    "down_fast": (0, 100.0, 0.0),
                }
            ),
        ):
            corrected = recertify_action_for_fresh_hazards(
                decision,
                player_x=192.0,
                player_y=400.0,
                previous_mask=SHOT | UP,
                delay_frames=(2, 3),
                action_hold_frames=4,
                bullets=(),
                lasers=(),
                enemy_bodies=(),
                snapshot_lag=0,
                allowed_first_actions=("up_fast", "down_fast"),
            )
        self.assertEqual(corrected.action, "up_fast")
        self.assertTrue(corrected.viability_constrained)
        self.assertFalse(corrected.viability_fresh_prefix_relaxed)
        self.assertIsNotNone(corrected.issue_recertification)
        assert corrected.issue_recertification is not None
        self.assertEqual(
            corrected.issue_recertification.selection_reason,
            "preserve_planned_in_fresh_global_intersection",
        )

    def test_ce_0127_issue_recertification_uses_fresh_global_intersection(
        self,
    ) -> None:
        decision = Decision(
            SHOT | UP,
            "up_fast",
            10.0,
            10.0,
            0.0,
            False,
            viability_constrained=True,
            viability_safe_action_count=3,
            viability_repair_volume=1,
            viability_recovery_distance=99.0,
            viability_control_reserve_deficit=7.0,
        )
        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=_issue_certificates(
                {
                    "up_fast": (1, -2.0, 100.0),
                    "left": (0, 5.0, 0.0),
                    "right": (0, 2.0, 0.0),
                    "down_fast": (0, 100.0, 0.0),
                }
            ),
        ):
            corrected = recertify_action_for_fresh_hazards(
                decision,
                player_x=192.0,
                player_y=400.0,
                previous_mask=SHOT | UP,
                delay_frames=(2, 3),
                action_hold_frames=4,
                bullets=(),
                lasers=(),
                enemy_bodies=(),
                snapshot_lag=0,
                allowed_first_actions=("up_fast", "left", "right"),
                viability_repair_volumes=(
                    ("up_fast", 1),
                    ("left", 11),
                    ("right", 7),
                ),
                viability_recovery_distances=(
                    ("up_fast", 99.0),
                    ("left", 22.0),
                    ("right", 33.0),
                ),
                viability_safety_actions=("left",),
                viability_survival_actions=("left",),
            )
        self.assertEqual(corrected.action, "left")
        self.assertTrue(corrected.viability_constrained)
        self.assertTrue(corrected.viability_fresh_prefix_filtered)
        self.assertFalse(corrected.viability_fresh_prefix_relaxed)
        self.assertEqual(corrected.viability_repair_volume, 11)
        self.assertEqual(corrected.viability_recovery_distance, 22.0)
        self.assertTrue(corrected.viability_safety_value_preferred)
        self.assertTrue(corrected.viability_survival_preferred)
        self.assertFalse(corrected.viability_control_reserve_valid)
        assert corrected.issue_recertification is not None
        self.assertEqual(
            corrected.issue_recertification.fresh_global_intersection,
            ("left", "right"),
        )
        self.assertEqual(
            corrected.issue_recertification.selection_reason,
            "replace_unsafe_from_fresh_global_intersection",
        )
        record = _issue_recertification_record(
            corrected.issue_recertification
        )
        assert record is not None
        self.assertFalse(
            record["selected_outside_global_without_relaxation"]
        )

    def test_ce_0127_issue_recertification_marks_empty_intersection_relaxation(
        self,
    ) -> None:
        decision = Decision(
            SHOT | UP,
            "up_fast",
            10.0,
            10.0,
            0.0,
            False,
            viability_constrained=True,
            viability_safe_action_count=1,
        )
        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=_issue_certificates(
                {
                    "up_fast": (1, -2.0, 100.0),
                    "down_fast": (0, 8.0, 0.0),
                }
            ),
        ):
            corrected = recertify_action_for_fresh_hazards(
                decision,
                player_x=192.0,
                player_y=400.0,
                previous_mask=SHOT | UP,
                delay_frames=(2, 3),
                action_hold_frames=4,
                bullets=(),
                lasers=(),
                enemy_bodies=(),
                snapshot_lag=0,
                allowed_first_actions=("up_fast",),
            )
        self.assertEqual(corrected.action, "down_fast")
        self.assertFalse(corrected.viability_constrained)
        self.assertTrue(corrected.viability_constraint_relaxed)
        self.assertTrue(corrected.viability_fresh_prefix_relaxed)
        assert corrected.issue_recertification is not None
        self.assertEqual(
            corrected.issue_recertification.fresh_global_intersection,
            (),
        )
        self.assertTrue(
            corrected.issue_recertification.global_constraint_relaxed
        )
        self.assertEqual(
            corrected.issue_recertification.selection_reason,
            "relax_empty_fresh_global_intersection",
        )
        record = _issue_recertification_record(
            corrected.issue_recertification
        )
        assert record is not None
        self.assertFalse(
            record["selected_outside_global_without_relaxation"]
        )

    def test_issue_recertification_cannot_escape_exact_action_authority(
        self,
    ) -> None:
        decision = Decision(
            SHOT | UP,
            "up_fast",
            10.0,
            10.0,
            0.0,
            False,
            viability_constrained=True,
            viability_safe_action_count=1,
        )
        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=_issue_certificates(
                {
                    "up_fast": (1, -2.0, 100.0),
                    "down_fast": (0, 8.0, 0.0),
                }
            ),
        ):
            corrected = issue_transaction_for_fresh_hazards(
                decision,
                player_x=192.0,
                player_y=400.0,
                previous_mask=SHOT | UP,
                delay_frames=(2, 3),
                action_hold_frames=4,
                bullets=(),
                lasers=(),
                enemy_bodies=(),
                snapshot_lag=0,
                allowed_first_actions=("up_fast",),
                allowed_action_authority="exact_test_authority",
            ).decision

        self.assertEqual(corrected.action, "up_fast")
        self.assertTrue(corrected.viability_constrained)
        self.assertFalse(corrected.viability_constraint_relaxed)
        self.assertFalse(corrected.viability_fresh_prefix_relaxed)
        assert corrected.issue_recertification is not None
        self.assertEqual(
            corrected.issue_recertification.selection_reason,
            "retain_hard_global_authority_least_bad",
        )

    def test_empty_intersection_can_preserve_safe_plan_with_relaxation(
        self,
    ) -> None:
        decision = Decision(
            SHOT | UP,
            "up_fast",
            10.0,
            10.0,
            0.0,
            False,
            viability_constrained=True,
            viability_safe_action_count=1,
        )
        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=_issue_certificates(
                {
                    "up_fast": (0, 2.0, 0.0),
                    "left": (1, -3.0, 100.0),
                }
            ),
        ):
            corrected = recertify_action_for_fresh_hazards(
                decision,
                player_x=192.0,
                player_y=400.0,
                previous_mask=SHOT | UP,
                delay_frames=(2, 3),
                action_hold_frames=4,
                bullets=(),
                lasers=(),
                enemy_bodies=(),
                snapshot_lag=0,
                allowed_first_actions=("left",),
            )
        self.assertEqual(corrected.action, "up_fast")
        self.assertFalse(corrected.viability_constrained)
        self.assertTrue(corrected.viability_fresh_prefix_relaxed)
        assert corrected.issue_recertification is not None
        self.assertEqual(
            corrected.issue_recertification.selection_reason,
            "relax_empty_fresh_global_intersection_preserve_planned",
        )

    def test_ce_0094_latent_ring_avoids_the_frame_9813_reactivation(self) -> None:
        stale_decision = Decision(
            SHOT | UP | RIGHT,
            "up_right_fast",
            75.65016174316406,
            75.65016174316406,
            0.0,
            False,
            planned_focus=False,
            robust_delay_frames=(3, 4, 5, 6),
            robust_min_clearance=75.65016174316406,
        )
        # Slot 7 was observed through frame 9785, then its native contact mode
        # disappeared from the old action snapshot before exact frame-9813
        # contact. Its position and velocity remained a continuous trajectory.
        body = EnemyBody(
            5927280,
            156.9927892908454,
            331.7983570098877,
            -0.11290890723466873,
            3.198007583618164,
            18.0,
            18.0,
            285217101 & ~0x04,
        )
        corrected = recertify_action_for_fresh_hazards(
            stale_decision,
            player_x=137.5178680419922,
            player_y=386.86676025390625,
            previous_mask=SHOT | 0x04 | RIGHT,
            delay_frames=(3, 4, 5, 6),
            action_hold_frames=5,
            bullets=(),
            lasers=(),
            enemy_bodies=(body,),
            snapshot_lag=0,
        )
        self.assertEqual(corrected.action, "down_fast")
        self.assertTrue(corrected.robust_override)
        self.assertEqual(corrected.robust_collisions, 0)
        self.assertGreater(corrected.robust_min_clearance, 0.0)

    def test_enemy_body_is_a_local_planner_hazard(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            enemy_bodies=(
                EnemyBody(
                    0x5826C0,
                    192.0,
                    365.0,
                    0.0,
                    0.0,
                    16.0,
                    16.0,
                    5,
                ),
            ),
            previous_direction=0,
            can_bomb=False,
        )
        self.assertNotIn(decision.action, {"up", "up_fast"})
        self.assertFalse(decision.bomb)

    def test_native_player_lethal_aabb_decoder_uses_exact_offsets(self) -> None:
        blob = bytearray(0x14)
        struct.pack_into("<ff", blob, 0, 190.5, 398.5)
        struct.pack_into("<ff", blob, 0x0C, 193.5, 401.5)
        self.assertEqual(
            decode_player_lethal_aabb(bytes(blob)),
            (190.5, 398.5, 193.5, 401.5),
        )

    def test_native_laser_decoder_retains_lifecycle_and_quarter_width(self) -> None:
        blob = bytearray(LASER_POOL_SIZE * LASER_STRIDE)
        struct.pack_into("<I", blob, LASER_ACTIVE_OFFSET, 1)
        struct.pack_into("<ff", blob, LASER_ORIGIN_OFFSET, 100.0, 200.0)
        struct.pack_into("<f", blob, LASER_ANGLE_OFFSET, 0.25)
        struct.pack_into("<f", blob, LASER_TAIL_OFFSET, 4.0)
        struct.pack_into("<f", blob, LASER_HEAD_OFFSET, 84.0)
        struct.pack_into("<f", blob, LASER_MAXIMUM_LENGTH_OFFSET, 120.0)
        struct.pack_into("<f", blob, LASER_WIDTH_OFFSET, 16.0)
        struct.pack_into("<f", blob, LASER_CURRENT_WIDTH_OFFSET, 8.0)
        struct.pack_into("<f", blob, LASER_SPEED_OFFSET, 3.0)
        struct.pack_into("<iiiii", blob, LASER_WARMUP_FRAMES_OFFSET, 10, 5, 20, 10, 5)
        struct.pack_into("<i", blob, LASER_TIMER_OFFSET, 4)
        struct.pack_into("<H", blob, LASER_FLAGS_OFFSET, 0)
        blob[LASER_PHASE_OFFSET] = 0
        lasers = decode_lasers(bytes(blob))
        persistent = ctypes.create_string_buffer(len(blob))
        ctypes.memmove(persistent, bytes(blob), len(blob))
        self.assertEqual(
            decode_lasers(memoryview(persistent).cast("B")),
            lasers,
        )
        self.assertEqual(len(lasers), 1)
        laser = lasers[0]
        self.assertEqual(laser.half_width, 4.0)
        self.assertEqual(laser.slot, 0)
        self.assertIsNotNone(laser.state)
        assert laser.state is not None
        self.assertEqual(laser.state.current_width, 8.0)
        self.assertEqual(laser.state.collision_enable_frame, 5)
        self.assertEqual(
            serialize_laser_trace(laser)[15:],
            [10, 5, 20, 10, 5, 0.0, 0.75, 0.0],
        )
        frames = build_laser_collision_frames(lasers, horizon=2)
        self.assertEqual(frames[0], ())
        self.assertEqual(len(frames[1]), 1)
        self.assertLess(frames[1][0].head - frames[1][0].tail, 10.0)

    def test_item_decoder_accepts_persistent_unsigned_byte_view(self) -> None:
        blob = bytearray(ITEM_POOL_SIZE * ITEM_STRIDE)
        struct.pack_into("<ff", blob, ITEM_POSITION_OFFSET, 100.0, 200.0)
        struct.pack_into("<ff", blob, ITEM_VELOCITY_OFFSET, 1.0, -2.0)
        blob[ITEM_TYPE_OFFSET] = 3
        blob[ITEM_ACTIVE_OFFSET] = 1
        blob[ITEM_MOTION_STATE_OFFSET] = 2
        blob[ITEM_FULL_VALUE_OFFSET] = 1
        persistent = ctypes.create_string_buffer(len(blob))
        ctypes.memmove(persistent, bytes(blob), len(blob))

        self.assertEqual(
            decode_items(memoryview(persistent).cast("B")),
            decode_items(bytes(blob)),
        )

    def test_omitted_item_capture_does_not_enter_the_fixed_pool_decoder(
        self,
    ) -> None:
        with patch("th08_live.controller.decode_items") as decoder:
            self.assertEqual(
                _decode_items_if_captured(memoryview(b""), captured=False),
                (),
            )
        decoder.assert_not_called()

    def test_laser_broad_phase_discards_only_segments_beyond_risk_radius(
        self,
    ) -> None:
        positions_x = np.asarray([100.0], dtype=np.float32)
        positions_y = np.asarray([100.0], dtype=np.float32)
        bullet_frame = tuple(
            np.asarray([], dtype=np.float32) for _ in range(5)
        )
        near = Laser(80.0, 100.0, 0.0, 0.0, 40.0, 2.0)
        far = Laser(400.0, 400.0, 0.0, 0.0, 40.0, 2.0)
        expected = _hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=bullet_frame,
            lasers=(near,),
            enemy_bodies=(),
        )
        actual = _hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=bullet_frame,
            lasers=(near, far),
            enemy_bodies=(),
        )
        for left, right in zip(expected, actual):
            np.testing.assert_allclose(left, right)

    def test_local_planner_projects_one_shared_laser_timeline(self) -> None:
        laser = Laser(80.0, 100.0, 0.0, 0.0, 180.0, 2.0)
        with patch(
            "th08_live_dodge_agent."
            "_build_packed_laser_collision_frames",
            wraps=_build_packed_laser_collision_frames,
        ) as build:
            choose_action(
                player_x=192.0,
                player_y=400.0,
                bullets=(),
                lasers=(laser,),
                previous_direction=0,
                can_bomb=False,
                control_delay_frames=2,
                control_delay_candidates=(2, 3),
                action_hold_frames=3,
                horizon=4,
                threat_horizon=8,
            )
        self.assertEqual(build.call_count, 1)
        self.assertEqual(build.call_args.kwargs["horizon"], 6)

    def test_fused_laser_projection_exactly_matches_object_pipeline(
        self,
    ) -> None:
        blob = bytearray(LASER_POOL_SIZE * LASER_STRIDE)
        struct.pack_into("<I", blob, LASER_ACTIVE_OFFSET, 1)
        struct.pack_into("<ff", blob, LASER_ORIGIN_OFFSET, 100.0, 200.0)
        struct.pack_into("<f", blob, LASER_ANGLE_OFFSET, 0.25)
        struct.pack_into("<f", blob, LASER_TAIL_OFFSET, 4.0)
        struct.pack_into("<f", blob, LASER_HEAD_OFFSET, 84.0)
        struct.pack_into("<f", blob, LASER_MAXIMUM_LENGTH_OFFSET, 120.0)
        struct.pack_into("<f", blob, LASER_WIDTH_OFFSET, 16.0)
        struct.pack_into("<f", blob, LASER_CURRENT_WIDTH_OFFSET, 8.0)
        struct.pack_into("<f", blob, LASER_SPEED_OFFSET, 3.0)
        struct.pack_into(
            "<iiiii",
            blob,
            LASER_WARMUP_FRAMES_OFFSET,
            10,
            5,
            20,
            10,
            5,
        )
        struct.pack_into("<i", blob, LASER_TIMER_OFFSET, 4)
        blob[LASER_PHASE_OFFSET] = 0
        stateful = decode_lasers(bytes(blob))[0]
        static = Laser(80.0, 100.0, 0.5, 3.0, 90.0, 2.0)
        lasers = (stateful, static)
        expected = tuple(
            _pack_laser_frame(frame)
            for frame in build_laser_collision_frames(
                lasers,
                horizon=8,
                snapshot_lag=2,
            )
        )
        actual = _build_packed_laser_collision_frames(
            lasers,
            horizon=8,
            snapshot_lag=2,
        )
        for expected_frame, actual_frame in zip(expected, actual):
            for field in (
                "start_x",
                "start_y",
                "segment_x",
                "segment_y",
                "collision_radius",
                "base_uncertainty",
                "uncertainty_per_frame",
            ):
                np.testing.assert_allclose(
                    getattr(actual_frame, field),
                    getattr(expected_frame, field),
                    rtol=0.0,
                    atol=1e-12,
                )

    def test_ce_0078_exact_local_laser_has_no_invented_horizon_drift(
        self,
    ) -> None:
        state = LaserState(
            origin_x=100.0,
            origin_y=200.0,
            angle=0.0,
            tail_distance=0.0,
            head_distance=80.0,
            maximum_length=80.0,
            width=16.0,
            speed=0.0,
            warmup_frames=0,
            active_frames=120,
            fade_frames=0,
            collision_enable_frame=0,
            collision_disable_frame=0,
            phase=LaserPhase.ACTIVE,
        )
        exact = Laser(
            100.0,
            200.0,
            0.0,
            0.0,
            80.0,
            4.0,
            state=state,
            uncertainty=0.75,
            uncertainty_per_frame=0.0,
        )
        fallback = Laser(
            100.0,
            200.0,
            0.0,
            0.0,
            80.0,
            4.0,
            uncertainty=0.75,
        )
        exact_frame = _build_packed_laser_collision_frames(
            (exact,),
            horizon=1,
        )[0]
        fallback_frame = _build_packed_laser_collision_frames(
            (fallback,),
            horizon=1,
        )[0]
        positions_x = np.asarray([140.0], dtype=np.float32)
        positions_y = np.asarray([212.0], dtype=np.float32)
        bullet_frame = tuple(
            np.asarray([], dtype=np.float32) for _ in range(5)
        )

        exact_near = _hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=bullet_frame,
            lasers=exact_frame,
            enemy_bodies=(),
        )[2][0]
        exact_far = _hazards_for_positions(
            positions_x,
            positions_y,
            step=40,
            bullet_frame=bullet_frame,
            lasers=exact_frame,
            enemy_bodies=(),
        )[2][0]
        fallback_far = _hazards_for_positions(
            positions_x,
            positions_y,
            step=40,
            bullet_frame=bullet_frame,
            lasers=fallback_frame,
            enemy_bodies=(),
        )[2][0]

        self.assertEqual(exact_near, exact_far)
        self.assertAlmostEqual(exact_far - fallback_far, 3.2)

    def test_incoming_bullet_forces_lateral_motion(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(Bullet(192.0, 364.0, 0.0, 3.0, 3.0, 3.0),),
            lasers=(),
            previous_direction=0,
            can_bomb=False,
        )
        self.assertNotEqual(decision.action, "stay")
        self.assertFalse(decision.bomb)

    def test_multi_delay_certificate_covers_until_next_command_effect(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(Bullet(192.0, 370.0, 0.0, 3.0, 3.0, 3.0),),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            control_delay_frames=3,
            control_delay_candidates=(2, 3, 4),
            action_hold_frames=3,
        )
        self.assertEqual(decision.robust_delay_frames, (2, 3, 4))
        self.assertEqual(decision.robust_collisions, 0)
        self.assertGreater(decision.robust_min_clearance, 0.0)
        self.assertIn(decision.robust_worst_delay, (2, 3, 4))

    def test_multi_delay_candidates_require_the_nominal_delay(self) -> None:
        with self.assertRaisesRegex(ValueError, "nominal control delay"):
            choose_action(
                player_x=192.0,
                player_y=400.0,
                bullets=(),
                lasers=(),
                previous_direction=0,
                can_bomb=False,
                control_delay_frames=2,
                control_delay_candidates=(3, 4),
            )

    def test_unavoidable_laser_requests_available_bomb(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(Laser(0.0, 400.0, 0.0, 0.0, 384.0, 80.0),),
            previous_direction=0,
            can_bomb=True,
        )
        self.assertTrue(decision.bomb)
        self.assertTrue(decision.mask & 0x02)

    def test_survival_only_policy_ignores_even_safe_large_power_item(
        self,
    ) -> None:
        common = dict(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            power=0.0,
            bombs=2.0,
            previous_direction=0,
            can_bomb=False,
        )
        without_item = choose_action(**common)
        with_item = choose_action(
            **common,
            items=(Item(17, 210.0, 400.0, 0.0, 0.0, 2, 0, False),),
        )
        self.assertEqual(with_item.action, without_item.action)
        self.assertEqual(with_item.score, without_item.score)
        self.assertEqual(with_item.predicted_collections, ())
        self.assertEqual(with_item.item_utility, 0.0)

    def test_small_top_item_does_not_override_conservative_position(self) -> None:
        decision = choose_action(
            player_x=184.5,
            player_y=192.7,
            bullets=(),
            lasers=(),
            items=(Item(1891, 222.0, 62.5, 0.0, -0.1, 0, 0, False),),
            power=39.0,
            bombs=4.0,
            previous_direction=UP,
            previous_focus=False,
            can_bomb=False,
            snapshot_lag=0,
            control_delay_frames=5,
            control_delay_candidates=(3, 4, 5, 6),
            action_hold_frames=5,
            horizon=10,
            threat_horizon=32,
        )
        self.assertNotIn(decision.action, {"up", "up_fast"})
        self.assertEqual(decision.predicted_collections, ())

    def test_ce_0090_spell_context_switch_drops_old_direction_inertia(
        self,
    ) -> None:
        decision = choose_action(
            player_x=184.5,
            player_y=192.7,
            bullets=(),
            lasers=(),
            previous_direction=UP,
            previous_focus=False,
            can_bomb=False,
            snapshot_lag=0,
            control_delay_frames=5,
            control_delay_candidates=(3, 4, 5, 6),
            action_hold_frames=5,
            horizon=10,
            threat_horizon=32,
            preserve_previous_direction_inertia=False,
        )
        self.assertNotIn(decision.action, {"up", "up_fast"})
        self.assertEqual(decision.robust_collisions, 0)

    def test_unsafe_bomb_item_is_rejected(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(Bullet(220.0, 400.0, 0.0, 0.0, 12.0, 12.0),),
            lasers=(),
            items=(Item(23, 240.0, 400.0, 0.0, 0.0, 3, 0, False),),
            power=0.0,
            bombs=2.0,
            previous_direction=0,
            can_bomb=False,
        )
        self.assertIn("left", decision.action)
        self.assertEqual(decision.predicted_collections, ())

    def test_fast_mode_is_available_for_urgent_escape(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(Bullet(192.0, 380.0, 0.0, 2.0, 8.0, 8.0),),
            lasers=(),
            previous_direction=0,
            can_bomb=False,
        )
        self.assertIn("fast", decision.action)
        self.assertFalse(decision.planned_focus)

    def test_global_gate_deadline_forces_commitment_before_local_danger(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            can_bomb=False,
            target_x=160.0,
            target_y=400.0,
            target_deadline=8,
        )
        self.assertIn("left", decision.action)
        self.assertNotEqual(decision.action, "stay")

    def test_gate_reachability_outranks_a_wider_local_dead_end(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(
                Bullet(176.0, 394.0, 0.0, 0.0, 4.0, 4.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            target_x=160.0,
            target_y=400.0,
            target_deadline=5,
        )
        self.assertEqual(decision.action, "down_left_fast")
        self.assertGreater(decision.min_clearance, 0.0)

    def test_async_corridor_age_advances_waypoint_and_deadline(self) -> None:
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            preferred_x=48.0,
            preferred_y=64.0,
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=32,
            ),
        )
        solution = CorridorSolution(100, plan, 12.0)
        target = _corridor_target(
            solution,
            current_frame=106,
            lookahead_frames=9,
            max_age_frames=20,
        )
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target[2], 10)
        self.assertIsNone(
            _corridor_target(
                solution,
                current_frame=121,
                lookahead_frames=9,
                max_age_frames=20,
            )
        )

    def test_corridor_commitment_survives_replans_without_rolling_expiry(
        self,
    ) -> None:
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            required_gate_lane="left",
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=32,
            ),
        )
        commitment = CorridorCommitment()
        self.assertTrue(commitment.set_context((0, 0, None)))
        commitment.accept(
            CorridorSolution(100, plan, 12.0, context_key=(0, 0, None)),
            current_frame=104,
        )
        original_expiry = commitment.expires_frame
        self.assertEqual(commitment.active_lane(104), "left")

        commitment.accept(
            CorridorSolution(
                120,
                plan,
                12.0,
                required_gate_lane="left",
                constraint_honored=True,
                context_key=(0, 0, None),
            ),
            current_frame=124,
        )
        self.assertEqual(commitment.expires_frame, original_expiry)
        self.assertIsNone(commitment.active_lane(original_expiry))

    def test_corridor_commitment_resets_at_spell_context_boundary(self) -> None:
        commitment = CorridorCommitment("right", 200, (0, 0, None))
        self.assertFalse(commitment.set_context((0, 0, None)))
        self.assertTrue(commitment.set_context((0, 0, 145)))
        self.assertIsNone(commitment.active_lane(150))

    def test_ce_frame_844_leaves_bottom_left_corner_early(self) -> None:
        bullets = (
            Bullet(27.520088, 385.47934, -1.7204704, 1.6792853, 2.0, 2.0),
            Bullet(50.196167, 446.35184, -1.8843979, 2.4929240, 2.0, 2.0),
        )
        decision = choose_action(
            player_x=8.0,
            player_y=432.0,
            bullets=bullets,
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            snapshot_lag=2,
            can_bomb=False,
        )
        self.assertIn("up", decision.action)
        self.assertNotEqual(decision.action, "stay")

    def test_viability_policy_hard_constrains_first_action(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            target_x=300.0,
            target_y=400.0,
            target_deadline=8,
            allowed_first_actions=("left",),
            viability_repair_volumes=(("left", 5),),
        )
        self.assertEqual(decision.action, "left")
        self.assertTrue(decision.viability_constrained)
        self.assertEqual(decision.viability_safe_action_count, 1)
        self.assertEqual(decision.viability_repair_volume, 5)

    def test_viability_repair_volume_outranks_soft_waypoint_preference(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            target_x=160.0,
            target_y=400.0,
            target_deadline=2,
            allowed_first_actions=("left", "right"),
            viability_repair_volumes=(("left", 1), ("right", 9)),
        )
        self.assertEqual(decision.action, "right")
        self.assertEqual(decision.viability_repair_volume, 9)

    def test_empty_kernel_recovery_is_soft_not_a_hard_action_constraint(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            target_x=160.0,
            target_y=400.0,
            target_deadline=2,
            viability_repair_volumes=(("left", 1), ("right", 9)),
        )
        self.assertEqual(decision.action, "right")
        self.assertFalse(decision.viability_constrained)
        self.assertEqual(decision.viability_safe_action_count, 0)
        self.assertEqual(decision.viability_repair_volume, 9)

    def test_empty_kernel_safety_value_is_soft_but_precedes_position(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            viability_safety_actions=("right",),
            viability_safety_state_value=-1.25,
        )
        self.assertEqual(decision.action, "right")
        self.assertTrue(decision.viability_safety_value_preferred)
        self.assertEqual(
            decision.viability_safety_state_value,
            -1.25,
        )

    def test_safety_value_never_overrides_local_collision_priority(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(
                Bullet(196.0, 400.0, 0.0, 0.0, 4.0, 4.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            viability_safety_actions=("right",),
            viability_safety_state_value=-2.0,
        )
        self.assertNotEqual(decision.action, "right")
        self.assertFalse(decision.viability_safety_value_preferred)

    def test_ce_0101_survival_horizon_precedes_endpoint_recovery(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            viability_survival_actions=("left",),
            viability_survival_frames=10,
            viability_survival_bottleneck_margin=-1.699,
            viability_recovery_distances=(
                ("left", 48.0),
                ("right", 0.0),
            ),
        )
        self.assertEqual(decision.action, "left")
        self.assertTrue(decision.viability_survival_preferred)
        self.assertEqual(decision.viability_survival_frames, 10)
        self.assertEqual(
            decision.viability_survival_bottleneck_margin,
            -1.699,
        )
        self.assertEqual(decision.viability_recovery_distance, 48.0)

    def test_local_collision_precedes_survival_horizon_label(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(
                Bullet(184.0, 400.0, 0.0, 0.0, 2.0, 2.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            viability_survival_actions=("left",),
            viability_survival_frames=10,
            viability_survival_bottleneck_margin=-1.0,
        )
        self.assertNotEqual(decision.action, "left")
        self.assertFalse(decision.viability_survival_preferred)

    def test_ce_stage1_frame_2512_distant_recovery_survives_beam_pruning(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            beam_width=1,
            viability_recovery_distances=(
                ("left", 48.0),
                ("right", 16.0),
            ),
        )
        self.assertEqual(decision.action, "right")
        self.assertFalse(decision.viability_constrained)
        self.assertEqual(decision.viability_recovery_distance, 16.0)

    def test_distant_recovery_preserves_delay_scaled_boundary_control(
        self,
    ) -> None:
        common = {
            "player_x": 8.0,
            "player_y": 424.0,
            "bullets": (),
            "lasers": (),
            "previous_direction": DOWN,
            "previous_focus": True,
            "can_bomb": False,
            "control_delay_frames": 3,
            "control_delay_candidates": (3, 4, 5, 6),
            "action_hold_frames": 6,
            "horizon": 10,
            "viability_recovery_distances": (
                ("stay", 226.0),
                ("down", 164.0),
                ("up_right_fast", 315.0),
            ),
        }
        baseline = choose_action(
            **common,
            recovery_control_reserve=False,
        )
        decision = choose_action(
            **common,
            recovery_control_reserve=True,
        )
        self.assertEqual(baseline.action, "down")
        self.assertGreater(
            baseline.viability_control_reserve_deficit,
            0.0,
        )
        self.assertEqual(decision.action, "up_right_fast")
        self.assertEqual(decision.viability_recovery_distance, 315.0)
        self.assertEqual(decision.viability_control_reserve_deficit, 0.0)

    def test_latency_boundary_reserve_does_not_require_global_guidance(
        self,
    ) -> None:
        common = {
            "player_x": 352.0,
            "player_y": 400.0,
            "bullets": (
                Bullet(192.0, 240.0, 0.0, 0.0, 2.0, 2.0),
            ),
            "lasers": (),
            "previous_direction": RIGHT,
            "previous_focus": False,
            "can_bomb": False,
            "control_delay_frames": 3,
            "control_delay_candidates": (3, 4, 5, 6),
            "action_hold_frames": 6,
            "horizon": 10,
        }
        baseline = choose_action(
            **common,
            recovery_control_reserve=False,
        )
        decision = choose_action(
            **common,
            recovery_control_reserve=True,
        )

        self.assertEqual(baseline.action, "stay")
        self.assertEqual(decision.action, "up_fast")
        self.assertEqual(decision.viability_control_reserve_deficit, 0.0)
        self.assertIsNone(decision.viability_recovery_distance)

    def test_repair_state_control_reserve_remains_shadow_only(self) -> None:
        common = {
            "player_x": 362.0,
            "player_y": 30.0,
            "bullets": (),
            "lasers": (),
            "previous_direction": DOWN,
            "previous_focus": True,
            "can_bomb": False,
            "control_delay_frames": 3,
            "control_delay_candidates": (3, 4, 5, 6),
            "action_hold_frames": 6,
            "horizon": 10,
            "recovery_control_reserve": False,
            "viability_repair_volumes": (
                ("stay", 1),
                ("down", 100),
                ("up_right_fast", 1),
            ),
        }
        baseline = choose_action(**common)
        shadow = choose_action(
            **common,
            losing_control_reserve=True,
        )
        self.assertEqual(baseline.action, "down")
        self.assertGreater(
            baseline.viability_control_reserve_deficit,
            0.0,
        )
        # The boundary-stratified beam can improve the continuation inside the
        # same first-action family; the diagnostic reserve still reaches zero
        # without requiring a different issued action.
        self.assertEqual(shadow.action, "down")
        self.assertEqual(shadow.viability_control_reserve_deficit, 0.0)

    def test_boundary_strata_preserve_best_exact_repair_under_preloss(
        self,
    ) -> None:
        def bullet(
            slot: int,
            x: float,
            y: float,
            vx: float,
            vy: float,
            half_size: float,
            speed: float,
            angle: float,
            original_flags: int,
            callback_phase: int,
        ) -> Bullet:
            return Bullet(
                x,
                y,
                vx,
                vy,
                # This is an algorithmic preference fixture.  Preserve its
                # historical occupied geometry after the live player box
                # changed from radius 2 to source half-extent 1.
                half_size + 1.0,
                half_size + 1.0,
                slot=slot,
                speed=speed,
                angle=angle,
                callback_phase_state=callback_phase,
                original_transform_flags=original_flags,
            )

        common = {
            "player_x": 369.55126953125,
            "player_y": 410.0467529296875,
            "bullets": (
                bullet(
                    213, 352.4305114746094, 355.86749267578125,
                    0.8665539026260376, 0.9815611839294434,
                    3.0, 1.309342622756958, 0.8475475311279297, 2, 0,
                ),
                bullet(
                    219, 341.50909423828125, 438.5190124511719,
                    0.8274074196815491, 1.277809739112854,
                    3.0, 1.522301197052002, 0.996166467666626, 2, 0,
                ),
                bullet(
                    304, 357.0599060058594, 356.3406982421875,
                    0.8425205945968628, 1.09906005859375,
                    3.0, 1.3848371505737305, 0.9167664051055908, 2, 0,
                ),
                bullet(
                    406, 323.64141845703125, 409.4451599121094,
                    1.030049443244934, 2.140005350112915,
                    2.0, 2.375, 1.1221957206726074, 514, 1,
                ),
                bullet(
                    441, 377.3912658691406, 377.52679443359375,
                    1.3860082626342773, 1.9286279678344727,
                    2.0, 2.375, 0.9476628303527832, 514, 1,
                ),
                bullet(
                    442, 286.3949890136719, 332.0615234375,
                    0.7833796739578247, 1.6275304555892944,
                    2.0, 1.806249976158142, 1.1221957206726074, 514, 1,
                ),
            ),
            "lasers": (),
            "previous_direction": 0,
            "previous_focus": True,
            "can_bomb": False,
            "control_delay_frames": 2,
            "control_delay_candidates": (2, 3, 4, 5, 6),
            "action_hold_frames": 3,
            "horizon": 10,
            "threat_horizon": 32,
            "beam_width": 24,
            "target_x": 360.0,
            "target_y": 416.0,
            "target_deadline": 23,
            "allowed_first_actions": (
                "stay",
                "left",
                "right",
                "down",
                "up_left",
                "down_right",
                "right_fast",
                "down_fast",
                "up_left_fast",
                "down_right_fast",
            ),
            "viability_repair_volumes": (
                ("stay", 58),
                ("left", 38),
                ("right", 50),
                ("down", 39),
                ("up_left", 35),
                ("down_right", 42),
                ("right_fast", 53),
                ("down_fast", 38),
                ("up_left_fast", 40),
                ("down_right_fast", 41),
            ),
            "viability_position_error": 8.776518406450759,
        }
        baseline = choose_action(**common)
        proposal = choose_action(
            **common,
            preloss_continuation_preference=True,
        )
        # Boundary action stratification already retains the stay leader,
        # which has the largest exact repair volume in this fixture.  Enabling
        # the pre-loss preference must not replace it with a smaller leader.
        self.assertEqual(baseline.action, "stay")
        self.assertEqual(proposal.action, "stay")
        self.assertEqual(proposal.viability_repair_volume, 58)
        self.assertTrue(
            proposal.preloss_continuation_preference_active
        )
        self.assertEqual(
            (
                proposal.robust_collisions,
                max(-proposal.robust_min_clearance, 0.0),
                proposal.terminal_threat_collisions,
                max(-proposal.terminal_threat_min_clearance, 0.0),
            ),
            (
                baseline.robust_collisions,
                max(-baseline.robust_min_clearance, 0.0),
                baseline.terminal_threat_collisions,
                max(-baseline.terminal_threat_min_clearance, 0.0),
            ),
        )

    def test_preloss_preference_fails_closed_without_complete_repairs(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            previous_direction=LEFT,
            previous_focus=True,
            can_bomb=False,
            control_delay_frames=2,
            control_delay_candidates=(1, 2, 3),
            action_hold_frames=4,
            horizon=4,
            threat_horizon=4,
            beam_width=1,
            allowed_first_actions=("left", "right"),
            viability_repair_volumes=(("left", 1),),
            preloss_continuation_preference=True,
        )
        self.assertEqual(decision.action, "left")
        self.assertFalse(
            decision.preloss_continuation_preference_active
        )

    def test_exact_local_collision_outranks_distant_kernel_recovery(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(
                Bullet(200.0, 400.0, 0.0, 0.0, 2.0, 2.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            viability_recovery_distances=(
                ("left", 48.0),
                ("right", 0.0),
            ),
        )
        self.assertEqual(decision.action, "left")
        self.assertEqual(decision.viability_recovery_distance, 48.0)

    def test_ce_0089_delay_certificate_precedes_recovery_beam_pruning(
        self,
    ) -> None:
        def certificates(*, actions, delay_frames, **_kwargs):
            return {
                action.name: RobustActionCertificate(
                    action=action.name,
                    delay_frames=delay_frames,
                    worst_collisions=1 if action.name == "left" else 0,
                    min_clearance=-1.0 if action.name == "left" else 10.0,
                    cvar_risk=100.0 if action.name == "left" else 0.0,
                    worst_delay=max(delay_frames),
                )
                for action in actions
            }

        with patch(
            "th08_live_dodge_agent._robust_action_certificates",
            side_effect=certificates,
        ):
            decision = choose_action(
                player_x=192.0,
                player_y=400.0,
                bullets=(),
                lasers=(),
                previous_direction=0,
                can_bomb=False,
                control_delay_frames=2,
                control_delay_candidates=(2, 3),
                action_hold_frames=2,
                horizon=4,
                beam_width=1,
                viability_recovery_distances=(
                    ("left", 0.0),
                    ("right", 100.0),
                ),
            )
        self.assertEqual(decision.action, "right")
        self.assertEqual(decision.robust_collisions, 0)

    def test_exact_local_collision_outranks_coarse_repair_volume(self) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=400.0,
            bullets=(
                Bullet(184.0, 400.0, 0.0, 0.0, 2.0, 2.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            horizon=2,
            allowed_first_actions=("left", "right"),
            viability_repair_volumes=(("left", 100), ("right", 1)),
        )
        self.assertEqual(decision.action, "right")
        self.assertEqual(decision.viability_repair_volume, 1)

    def test_fresh_prefix_contradiction_relaxes_stale_global_mask(
        self,
    ) -> None:
        decision = choose_action(
            player_x=192.0,
            player_y=432.0,
            bullets=(
                Bullet(160.0, 432.0, 4.0, 0.0, 2.0, 2.0),
            ),
            lasers=(),
            previous_direction=0,
            previous_focus=True,
            can_bomb=False,
            control_delay_frames=3,
            control_delay_candidates=(3, 4, 5, 6),
            action_hold_frames=5,
            horizon=10,
            threat_horizon=32,
            allowed_first_actions=("stay", "down", "left"),
            viability_repair_volumes=(
                ("stay", 10),
                ("down", 10),
                ("left", 10),
            ),
        )
        self.assertNotIn(decision.action, ("stay", "down", "left"))
        self.assertFalse(decision.viability_constrained)
        self.assertTrue(decision.viability_constraint_relaxed)
        self.assertTrue(decision.viability_fresh_prefix_relaxed)
        self.assertEqual(decision.robust_collisions, 0)
        self.assertEqual(decision.terminal_threat_collisions, 0)

    def test_async_viability_policy_is_queried_at_current_layer(self) -> None:
        actions = (
            ControlAction("stay", 0.0, 0.0),
            ControlAction("left", -4.0, 0.0),
            ControlAction("right", 4.0, 0.0),
        )
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=16,
                cardinal_speed=4.0,
                diagonal_axis_speed=2.8284270763397217,
            ),
            robust_control=RobustControlSpec(
                actions=actions,
                delay_frames=(1, 2),
                nominal_delay=1,
                active_action="stay",
            ),
        )
        solution = CorridorSolution(100, plan, 12.0)
        query = _corridor_viability_query(
            solution,
            current_frame=105,
            player_x=48.0,
            player_y=88.0,
            active_action="stay",
            max_age_frames=12,
        )
        self.assertIsNotNone(query)
        assert query is not None
        self.assertEqual(query.layer, 1)
        self.assertTrue(query.available)
        self.assertGreater(query.safe_action_count, 0)

    def test_future_policy_epoch_is_pending_then_queryable_then_expired(
        self,
    ) -> None:
        actions = (ControlAction("stay", 0.0, 0.0),)
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=16,
            ),
            robust_control=RobustControlSpec(
                actions=actions,
                delay_frames=(1,),
                nominal_delay=1,
                active_action="stay",
            ),
        )
        solution = CorridorSolution(
            120,
            plan,
            800.0,
            snapshot_frame=72,
            forecast_lead_frames=48,
            context_key=(0, 3, 57),
        )
        self.assertEqual(
            _corridor_policy_status(
                solution,
                current_frame=119,
                max_age_frames=15,
            ),
            "pending_future_epoch",
        )
        self.assertEqual(
            _corridor_policy_status(
                solution,
                current_frame=120,
                max_age_frames=15,
            ),
            "queryable",
        )
        self.assertEqual(
            _corridor_policy_status(
                solution,
                current_frame=136,
                max_age_frames=15,
            ),
            "expired",
        )

    def test_future_policy_does_not_replace_active_policy_before_epoch(
        self,
    ) -> None:
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=16,
            ),
        )
        active = CorridorSolution(100, plan, 10.0, context_key=(0, 3, 57))
        future = CorridorSolution(120, plan, 8.0, context_key=(0, 3, 57))
        staged_active, pending = _stage_corridor_solution(
            active,
            future,
            current_frame=119,
            context_key=(0, 3, 57),
        )
        self.assertIs(staged_active, active)
        self.assertIs(pending, future)
        staged_active, pending = _stage_corridor_solution(
            staged_active,
            pending,
            current_frame=120,
            context_key=(0, 3, 57),
        )
        self.assertIs(staged_active, future)
        self.assertIsNone(pending)

    def test_ce_0045_finalb_restart_discards_previous_gameplay_epoch_policy(
        self,
    ) -> None:
        self.assertFalse(
            _corridor_submit_due(
                current_frame=0,
                last_submit_frame=70_745,
                interval_frames=24,
            )
        )
        self.assertTrue(
            _corridor_submit_due(
                current_frame=0,
                last_submit_frame=CORRIDOR_INITIAL_SUBMIT_FRAME,
                interval_frames=24,
            )
        )
        plan = plan_corridor(
            start_x=48.0,
            start_y=88.0,
            bounds=CorridorBounds(0.0, 96.0, 0.0, 96.0),
            config=CorridorConfig(
                grid_step=8.0,
                frames_per_layer=4,
                horizon_frames=16,
            ),
        )
        old_future = CorridorSolution(
            70800,
            plan,
            4000.0,
            context_key=(0, 7, None),
        )
        active, pending = _stage_corridor_solution(
            None,
            old_future,
            current_frame=0,
            context_key=(1, 7, None),
        )
        self.assertIsNone(active)
        self.assertIsNone(pending)

    def test_ce_frame_1420_commits_away_before_bottom_edge_trap(self) -> None:
        bullet = Bullet(
            119.245995,
            408.33627,
            -1.3280246,
            2.8287764,
            2.0,
            2.0,
        )
        decision = choose_action(
            player_x=120.940872,
            player_y=432.0,
            bullets=(bullet,),
            lasers=(),
            previous_direction=0x40,
            previous_focus=True,
            snapshot_lag=0,
            can_bomb=False,
        )
        self.assertEqual(decision.action, "right_fast")

    def test_boundary_clamps_allowed_action_without_neutral_fallback(self) -> None:
        decision = choose_action(
            player_x=351.7697448730469,
            player_y=412.4698486328125,
            bullets=(),
            lasers=(),
            previous_direction=DOWN | RIGHT,
            previous_focus=True,
            snapshot_lag=0,
            control_delay_frames=6,
            control_delay_candidates=(4, 5, 6),
            action_hold_frames=6,
            can_bomb=False,
            horizon=10,
            threat_horizon=32,
            allowed_first_actions=("down_left_fast", "down_right_fast"),
            viability_repair_volumes=(
                ("down_left_fast", 10),
                ("down_right_fast", 2),
            ),
            viability_position_error=6.901441524171802,
        )
        self.assertIn(
            decision.action,
            ("down_left_fast", "down_right_fast"),
        )
        self.assertTrue(decision.viability_constrained)

    def test_ce_stage2_frame_13517_terminal_threat_leaves_clamped_aliases(
        self,
    ) -> None:
        bullets = tuple(
            Bullet(
                x,
                y,
                vx,
                vy,
                # Preserve the captured fixture's historical effective
                # occupancy so this test continues to isolate the terminal-
                # horizon/clamped-alias behavior rather than player geometry.
                width + 1.0,
                height + 1.0,
                slot=slot,
            )
            for slot, x, y, vx, vy, width, height in (
                (
                    246,
                    268.00494384765625,
                    423.29119873046875,
                    0.2894723415374756,
                    1.9789408445358276,
                    2.0,
                    2.0,
                ),
                (
                    255,
                    310.0292053222656,
                    399.29315185546875,
                    0.6699826121330261,
                    1.8844417333602905,
                    2.0,
                    2.0,
                ),
                (
                    344,
                    285.4129638671875,
                    398.8815002441406,
                    0.30125316977500916,
                    1.9771815538406372,
                    2.0,
                    2.0,
                ),
                (
                    391,
                    207.90084838867188,
                    325.9405822753906,
                    1.584021806716919,
                    1.221012830734253,
                    2.0,
                    2.0,
                ),
                (
                    570,
                    332.90472412109375,
                    385.6181640625,
                    0.4250517785549164,
                    3.3733270168304443,
                    5.0,
                    5.0,
                ),
                (
                    577,
                    334.0790710449219,
                    394.9444274902344,
                    0.4500548243522644,
                    3.5717580318450928,
                    5.0,
                    5.0,
                ),
            )
        )
        common = {
            "player_x": 304.103759765625,
            "player_y": 429.64422607421875,
            "bullets": bullets,
            "lasers": (),
            "previous_direction": 0,
            "previous_focus": True,
            "snapshot_lag": 1,
            "control_delay_frames": 3,
            "control_delay_candidates": (3, 4, 5, 6),
            "action_hold_frames": 4,
            "can_bomb": False,
            "horizon": 10,
            "allowed_first_actions": (
                "stay",
                "down",
                "left_fast",
                "down_fast",
            ),
            "viability_repair_volumes": (
                ("stay", 3),
                ("down", 3),
                ("left_fast", 1),
                ("down_fast", 3),
            ),
        }
        legacy = choose_action(**common, threat_horizon=10)
        decision = choose_action(**common, threat_horizon=32)
        self.assertIn(legacy.action, ("stay", "down", "down_fast"))
        self.assertEqual(decision.action, "down_fast")
        self.assertFalse(decision.viability_constraint_relaxed)
        self.assertEqual(decision.terminal_threat_horizon, 32)
        self.assertGreater(
            decision.terminal_threat_min_clearance,
            legacy.min_clearance,
        )
        self.assertFalse(decision.bomb)

        coarse_grid_common = {
            **common,
            "player_x": 366.32177734375,
            "player_y": 424.7275390625,
            "bullets": (
                Bullet(
                    347.1014404296875,
                    409.2017517089844,
                    1.6826684474945068,
                    1.0810304880142212,
                    2.0,
                    2.0,
                    slot=827,
                ),
            ),
            "snapshot_lag": 1,
            "control_delay_frames": 4,
            "allowed_first_actions": ("stay", "down", "down_fast"),
            "viability_repair_volumes": (
                ("stay", 8),
                ("down", 3),
                ("down_fast", 3),
            ),
        }
        coarse_grid_legacy = choose_action(
            **coarse_grid_common,
            threat_horizon=10,
        )
        coarse_grid_alias = choose_action(
            **coarse_grid_common,
            threat_horizon=32,
        )
        self.assertIn(
            coarse_grid_legacy.action,
            ("stay", "down", "down_fast"),
        )
        self.assertNotEqual(
            coarse_grid_alias.action,
            coarse_grid_legacy.action,
        )
        self.assertTrue(coarse_grid_alias.viability_constraint_relaxed)
        self.assertEqual(coarse_grid_alias.terminal_threat_horizon, 32)

        singleton_common = {
            **common,
            "player_x": 17.515056610107422,
            "player_y": 414.66705322265625,
            "bullets": (
                Bullet(
                    18.422264099121094,
                    394.4905700683594,
                    -0.27819836139678955,
                    1.2698835134506226,
                    2.0,
                    2.0,
                    slot=866,
                ),
            ),
            "snapshot_lag": 0,
            "control_delay_frames": 4,
            "allowed_first_actions": ("stay",),
            "viability_repair_volumes": (("stay", 1),),
            "viability_position_error": 6.620516436150773,
        }
        singleton_legacy = choose_action(
            **singleton_common,
            threat_horizon=10,
        )
        singleton_fixed = choose_action(
            **singleton_common,
            threat_horizon=32,
        )
        self.assertEqual(singleton_legacy.action, "stay")
        self.assertEqual(singleton_fixed.action, "right_fast")
        self.assertTrue(singleton_fixed.viability_constraint_relaxed)
        self.assertGreater(
            singleton_fixed.min_clearance,
            singleton_legacy.min_clearance,
        )
        self.assertEqual(
            singleton_fixed.viability_control_reserve_deficit,
            0.0,
        )
        self.assertLess(
            singleton_fixed.terminal_threat_min_clearance,
            9999.0,
        )

        safe_singleton = choose_action(
            **{
                **common,
                "player_x": 192.37,
                "player_y": 400.0,
                "bullets": (),
                "snapshot_lag": 0,
                "control_delay_frames": 4,
                "allowed_first_actions": ("stay",),
                "viability_repair_volumes": (("stay", 3),),
                "viability_position_error": 3.63,
            },
            threat_horizon=32,
        )
        self.assertEqual(safe_singleton.action, "stay")
        self.assertFalse(safe_singleton.viability_constraint_relaxed)
        self.assertEqual(safe_singleton.terminal_threat_horizon, 32)

        interior = choose_action(
            **{**common, "player_y": 400.0},
            threat_horizon=32,
        )
        self.assertEqual(interior.terminal_threat_horizon, 10)

    def test_ce_frame_3254_exposes_residual_timing_gap_after_source_geometry(
        self,
    ) -> None:
        bullet = Bullet(
            337.4276123046875,
            382.9591369628906,
            1.226178526878357,
            1.7048418521881104,
            2.0,
            2.0,
            slot=1136,
        )
        legacy = choose_action(
            player_x=340.20098876953125,
            player_y=392.4019775390625,
            bullets=(bullet,),
            lasers=(),
            previous_direction=UP | RIGHT,
            previous_focus=True,
            control_delay_frames=1,
            can_bomb=True,
        )
        decision = choose_action(
            player_x=340.20098876953125,
            player_y=392.4019775390625,
            bullets=(bullet,),
            lasers=(),
            previous_direction=UP | RIGHT,
            previous_focus=True,
            control_delay_frames=3,
            can_bomb=True,
        )
        self.assertFalse(legacy.bomb)
        # This retained root precedes a physical hit, but the exact 1px player
        # AABB leaves the current linear/timing projection barely positive.
        # Keep the discrepancy visible until sensing/issue timing is fixed;
        # the former radius-2 geometry merely hid it behind a false margin.
        self.assertFalse(decision.bomb)
        self.assertEqual(decision.action, "up_fast")
        self.assertGreater(decision.pipeline_clearance, 0.0)
        self.assertLess(decision.pipeline_clearance, 0.5)

    def test_ce_frame_4963_does_not_reverse_into_delayed_slot_471_path(self) -> None:
        bullet = Bullet(
            226.39694213867188,
            412.6267395019531,
            0.8104109168052673,
            2.0093977451324463,
            5.0,
            5.0,
            slot=471,
        )
        legacy = choose_action(
            player_x=233.82810974121094,
            player_y=432.0,
            bullets=(bullet,),
            lasers=(),
            previous_direction=LEFT,
            previous_focus=False,
            control_delay_frames=1,
            can_bomb=False,
        )
        decision = choose_action(
            player_x=233.82810974121094,
            player_y=432.0,
            bullets=(bullet,),
            lasers=(),
            previous_direction=LEFT,
            previous_focus=False,
            control_delay_frames=3,
            can_bomb=False,
        )
        self.assertEqual(legacy.action, "right_fast")
        self.assertEqual(decision.action, "left_fast")

    def test_ce_frame_4969_slot_471_explains_native_hit(self) -> None:
        bullet = Bullet(
            231.2593994140625,
            424.6827392578125,
            0.8104109168052673,
            2.0093977451324463,
            5.0,
            5.0,
            slot=471,
        )
        decision = choose_action(
            player_x=233.82810974121094,
            player_y=432.0,
            bullets=(bullet,),
            lasers=(),
            previous_direction=RIGHT,
            previous_focus=False,
            control_delay_frames=3,
            can_bomb=True,
        )
        self.assertTrue(decision.bomb)
        self.assertLess(decision.pipeline_clearance, 0.0)


if __name__ == "__main__":
    unittest.main()
