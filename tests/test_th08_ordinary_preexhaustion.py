from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from th08_live.controller import (
    _ordinary_authority_target,
    _ordinary_delayed_computation_guard,
    _ordinary_local_projection_from_solution,
    _ordinary_nonspell_preexhaustion_filter,
    _ordinary_prefix_candidate_actions,
    _ordinary_submission_projection,
    _ordinary_terminal_probe_actions,
    _prioritize_ordinary_delayed_actions,
    _ordinary_target_query_frame,
    _select_delayed_issue_action,
)
from th08_future_birth_envelope import (
    FloatInterval,
    FutureTaggedBulletCallback,
)
from th08_future_hazard_projection import (
    complete_future_hazard_projection,
)
from th08_local_planner import RobustActionCertificate
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS
from touhou_control.local_pipeline_oracle import LocalPipelineRoot


class OrdinaryNonspellPreexhaustionTests(unittest.TestCase):
    def test_global_callback_join_does_not_leak_into_local_prefix(self) -> None:
        plain = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=100,
            events=(),
            source_semantics_version="test-source-v1",
        )
        plain_solution = SimpleNamespace(
            future_hazard_projection=plain,
            future_hazard_version=plain.version,
        )
        self.assertEqual(
            _ordinary_local_projection_from_solution(
                plain_solution,
                current_frame=110,
            ),
            (plain, 10),
        )

        callback = FutureTaggedBulletCallback(
            source="test",
            frame=20,
            callback_index=14,
            tag_mask=0x100000,
            callback_angle=None,
            callback_speed=FloatInterval.point(2.0),
        )
        joined_global = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=100,
            events=(),
            tagged_callbacks=(callback,),
            source_semantics_version="test-source-v1",
        )
        joined_solution = SimpleNamespace(
            future_hazard_projection=joined_global,
            future_hazard_version=joined_global.version,
        )
        self.assertEqual(
            _ordinary_local_projection_from_solution(
                joined_solution,
                current_frame=110,
            ),
            (None, -1),
        )

    def test_delayed_issue_selection_uses_only_the_observed_age_row(
        self,
    ) -> None:
        safe_left = RobustActionCertificate(
            action="left_fast",
            delay_frames=(0, 1, 2),
            worst_collisions=0,
            min_clearance=4.0,
            cvar_risk=10.0,
            worst_delay=2,
        )
        unsafe_right = RobustActionCertificate(
            action="right_fast",
            delay_frames=(0, 1, 2),
            worst_collisions=1,
            min_clearance=-1.0,
            cvar_risk=20.0,
            worst_delay=2,
        )

        action, certificate, reason = _select_delayed_issue_action(
            certificates_by_issue_delay={
                7: {"left_fast": safe_left, "right_fast": unsafe_right},
                8: {"right_fast": unsafe_right},
            },
            issue_age=7,
            planned_action="right_fast",
            preferred_action="left_fast",
        )

        self.assertEqual(action, "left_fast")
        self.assertIs(certificate, safe_left)
        self.assertEqual(
            reason, "preferred_action_safe_for_observed_issue_age"
        )
        self.assertEqual(
            _select_delayed_issue_action(
                certificates_by_issue_delay={7: {"left_fast": safe_left}},
                issue_age=8,
                planned_action="left_fast",
                preferred_action=None,
            ),
            (None, None, "issue_age_outside_certified_support"),
        )

    def test_terminal_probe_is_a_bounded_held_and_recovery_subset(
        self,
    ) -> None:
        selected = _ordinary_terminal_probe_actions(
            held_action="right_fast",
            recovery_distances=(
                ("down_fast", 8.0),
                ("left_fast", 2.0),
                ("up_fast", 4.0),
            ),
            limit=3,
        )

        self.assertEqual(
            tuple(action.name for action in selected),
            ("right_fast", "left_fast", "up_fast"),
        )

    def test_terminal_probe_prioritizes_current_viable_repair_volume(
        self,
    ) -> None:
        selected = _ordinary_terminal_probe_actions(
            held_action="down_left",
            recovery_distances=(),
            viable_repair_volumes=(
                ("stay", 7),
                ("down", 8),
                ("up_left", 25),
                ("down_left", 28),
                ("down_fast", 8),
            ),
            limit=3,
        )

        self.assertEqual(
            tuple(action.name for action in selected),
            ("down_left", "up_left", "down"),
        )

    def test_long_scan_requires_lease_or_exact_held_action_guard(self) -> None:
        self.assertEqual(
            _ordinary_delayed_computation_guard(
                continuation_lease_active=False,
                held_action_safe=False,
                held_action_reason="constant_hold_remaining_horizon_unsafe",
            ),
            (
                False,
                "blocked_without_exact_hold:"
                "constant_hold_remaining_horizon_unsafe",
            ),
        )
        self.assertEqual(
            _ordinary_delayed_computation_guard(
                continuation_lease_active=False,
                held_action_safe=True,
                held_action_reason="constant_hold_remaining_horizon_safe",
            ),
            (True, "exact_constant_hold_horizon"),
        )
        self.assertEqual(
            _ordinary_delayed_computation_guard(
                continuation_lease_active=True,
                held_action_safe=False,
                held_action_reason="not_needed",
            ),
            (True, "compatible_continuation_lease"),
        )

    def test_delayed_computation_prioritizes_local_proposal_without_authority(
        self,
    ) -> None:
        candidates = _ordinary_terminal_probe_actions(
            held_action="up_right",
            recovery_distances=(),
        )

        prioritized = _prioritize_ordinary_delayed_actions(
            candidates,
            planned_action="right_fast",
        )

        self.assertEqual(
            tuple(action.name for action in prioritized),
            ("right_fast", "up_right", "left_fast"),
        )

    def test_prefix_certificate_selection_is_a_bounded_terminal_subset(
        self,
    ) -> None:
        terminal = (
            "stay",
            "left",
            "right",
            "up",
            "down",
            "left_fast",
            "right_fast",
            "up_fast",
            "down_fast",
        )

        selected = _ordinary_prefix_candidate_actions(
            held_action="right",
            terminal_candidates=terminal,
            recovery_actions=("up", "left", "down"),
            limit=6,
        )

        names = tuple(action.name for action in selected)
        self.assertEqual(names[0], "right")
        self.assertLessEqual(len(names), 6)
        self.assertTrue(set(names).issubset(terminal))

    def test_empty_terminal_set_never_manufactures_a_prefix_action(self) -> None:
        self.assertEqual(
            _ordinary_prefix_candidate_actions(
                held_action="right_fast",
                terminal_candidates=(),
                recovery_actions=("left_fast",),
            ),
            (),
        )

    def _build(self, **overrides):
        arguments = {
            "enabled": True,
            "spell_active": False,
            "player_phase": 0,
            "root_scale_bits": TH08_UNIT_TIME_SCALE_BITS,
            "root": LocalPipelineRoot("stay", "stay"),
            "action_hold_frames": 3,
            "player_x": 192.0,
            "player_y": 400.0,
            "current_frame": 100,
            "future_solution": None,
            "future_hazard_coverage": None,
        }
        arguments.update(overrides)
        return _ordinary_nonspell_preexhaustion_filter(**arguments)

    def test_phase_zero_is_not_blocked_by_retained_deathbomb_limit(self) -> None:
        result = self._build()

        self.assertTrue(result.state_eligible)
        self.assertEqual(result.reason, "future_policy_unavailable")

    def test_phase_three_remains_a_native_movement_phase(self) -> None:
        result = self._build(player_phase=3)

        self.assertTrue(result.state_eligible)
        self.assertEqual(result.reason, "future_policy_unavailable")

    def test_spell_phase_has_no_authority(self) -> None:
        result = self._build(spell_active=True)

        self.assertFalse(result.authority_eligible)
        self.assertEqual(result.reason, "spell_active")

    def test_nonunit_root_scale_fails_closed(self) -> None:
        result = self._build(root_scale_bits=0x3F000000)

        self.assertFalse(result.authority_eligible)
        self.assertEqual(result.reason, "nonunit_root_time_scale")

    def test_player_transition_fails_closed(self) -> None:
        result = self._build(player_phase=2)

        self.assertFalse(result.state_eligible)
        self.assertEqual(result.reason, "player_transition")

    def test_active_policy_target_keeps_a_complete_pickup_lease(self) -> None:
        policy = SimpleNamespace(
            config=SimpleNamespace(frames_per_layer=8),
            horizon_frames=80,
        )

        self.assertEqual(
            _ordinary_target_query_frame(policy=policy, policy_age=0),
            8,
        )
        self.assertEqual(
            _ordinary_target_query_frame(policy=policy, policy_age=1),
            8,
        )
        self.assertEqual(
            _ordinary_target_query_frame(policy=policy, policy_age=2),
            16,
        )
        self.assertIsNone(
            _ordinary_target_query_frame(policy=policy, policy_age=73)
        )

    def test_pending_policy_is_a_prepublication_terminal_kernel(self) -> None:
        policy = SimpleNamespace(
            config=SimpleNamespace(frames_per_layer=8),
            horizon_frames=80,
        )
        pending = SimpleNamespace(
            source_frame=180,
            plan=SimpleNamespace(viability_policy=policy),
        )

        with patch(
            "th08_live.controller._ordinary_lower_kernel",
            return_value=policy,
        ), patch(
            "th08_live.controller._ordinary_solution_hazard_authority",
            return_value=True,
        ):
            solution, query_frame = _ordinary_authority_target(
                active_solution=None,
                pending_solution=pending,
                current_frame=100,
            )

        self.assertIs(solution, pending)
        self.assertEqual(query_frame, 0)

    def test_incomplete_source_never_consumes_a_solver_slot(self) -> None:
        incomplete = SimpleNamespace(
            source_closure_complete=False,
            current_pool_callback_composition_complete=True,
            root_frame=100,
            horizon_frame=368,
        )
        result = SimpleNamespace(
            snapshot=SimpleNamespace(
                payload={"compact_state": {"spell_id": None}}
            ),
            closure=SimpleNamespace(projection=incomplete),
        )

        self.assertIsNone(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=None,
            )
        )

        incomplete.source_closure_complete = True
        self.assertIs(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=None,
            ),
            incomplete,
        )

    def test_complete_causal_prefix_must_cover_whole_policy(self) -> None:
        prefix = SimpleNamespace(
            source_closure_complete=True,
            current_pool_callback_composition_complete=True,
            root_frame=100,
            horizon_frame=259,
        )
        result = SimpleNamespace(
            snapshot=SimpleNamespace(
                payload={"compact_state": {"spell_id": None}}
            ),
            closure=SimpleNamespace(projection=prefix),
        )

        self.assertIs(
            _ordinary_submission_projection(
                result,
                policy_source_frame=179,
                policy_horizon_frames=80,
                expected_spell_id=None,
            ),
            prefix,
        )
        self.assertIsNone(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=None,
            )
        )

    def test_submission_projection_requires_exact_captured_spell_id(self) -> None:
        projection = SimpleNamespace(
            source_closure_complete=True,
            current_pool_callback_composition_complete=True,
            root_frame=100,
            horizon_frame=260,
        )
        result = SimpleNamespace(
            snapshot=SimpleNamespace(
                payload={"compact_state": {"spell_id": 103}}
            ),
            closure=SimpleNamespace(projection=projection),
        )

        self.assertIs(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=103,
            ),
            projection,
        )
        for expected_spell_id in (None, 107):
            self.assertIsNone(
                _ordinary_submission_projection(
                    result,
                    policy_source_frame=180,
                    policy_horizon_frames=80,
                    expected_spell_id=expected_spell_id,
                )
            )

        result.snapshot.payload = {}
        self.assertIsNone(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=103,
            )
        )

    def test_submission_rejects_uncomposed_current_pool_callbacks(self) -> None:
        projection = SimpleNamespace(
            source_closure_complete=True,
            current_pool_callback_composition_complete=False,
            root_frame=100,
            horizon_frame=260,
        )
        result = SimpleNamespace(
            snapshot=SimpleNamespace(
                payload={"compact_state": {"spell_id": 103}}
            ),
            closure=SimpleNamespace(projection=projection),
        )

        self.assertIsNone(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=103,
            )
        )
        join = SimpleNamespace(
            complete=True,
            policy_source_frame=180,
            policy_horizon_frames=80,
            time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            matches_projection=lambda candidate: candidate is projection,
        )
        self.assertIs(
            _ordinary_submission_projection(
                result,
                policy_source_frame=180,
                policy_horizon_frames=80,
                expected_spell_id=103,
                current_pool_callback_join=join,
            ),
            projection,
        )
