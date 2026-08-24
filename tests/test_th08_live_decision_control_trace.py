#!/usr/bin/env python3
"""Tests for post-issue decision/control trace fields."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from th08_live.decision_control_trace import (
    DecisionControlTraceInput,
    build_decision_control_trace_fields,
)


class DecisionControlTraceTests(unittest.TestCase):
    @staticmethod
    def _decision() -> SimpleNamespace:
        values = {
            "action": "right",
            "mask": 0x81,
            "planned_focus": False,
            "min_clearance": 2.0,
            "immediate_clearance": 3.0,
            "pipeline_clearance": 1.0,
            "local_certificate_timing": "local",
            "issue_certificate_timing": "issue",
            "damage_objective_available": True,
            "damage_reason": "available",
            "damage_baseline_action": "stay",
            "damage_shadow_action": "right",
            "damage_current_alignment_cost": 2.0,
            "damage_shadow_alignment_cost": 1.0,
            "damage_eligible_action_count": 3,
            "robust_delay_frames": (2, 3),
            "robust_override": False,
            "robust_collisions": 0,
            "robust_min_clearance": 1.5,
            "robust_cvar_risk": 0.0,
            "robust_worst_delay": 3,
            "viability_constrained": True,
            "viability_safe_action_count": 2,
            "viability_repair_volume": 7,
            "viability_constraint_relaxed": False,
            "viability_recovery_distance": 0.0,
            "viability_control_reserve_deficit": 0.0,
            "viability_control_reserve_valid": True,
            "preloss_continuation_preference_active": False,
            "planned_route_gate_deficit": 0.0,
            "local_collisions": 0,
            "preloss_historical_action": None,
            "preloss_historical_route_gate_deficit": None,
            "viability_safety_value_preferred": False,
            "viability_safety_state_value": None,
            "viability_fresh_prefix_filtered": False,
            "viability_fresh_prefix_relaxed": False,
            "viability_survival_preferred": True,
            "viability_survival_frames": 32,
            "viability_survival_bottleneck_margin": 1.25,
            "terminal_threat_horizon": 32,
            "terminal_threat_collisions": 0,
            "terminal_threat_min_clearance": 0.5,
            "score": (0, 1.0),
            "item_utility": 4.0,
            "predicted_collections": 1,
            "bomb": False,
        }
        return SimpleNamespace(**values)

    def test_fields_preserve_issue_and_control_schema(self) -> None:
        decision = self._decision()
        dispatch = SimpleNamespace(
            previous_mask=0x01,
            target_mask=0x81,
            transitions=(SimpleNamespace(bit=0x80, pressed=True),),
        )
        issue = SimpleNamespace(
            decision=decision,
            alignment=SimpleNamespace(
                support_high=3,
                post_capture_advance=1,
            ),
            dispatch=dispatch,
            deadline_missed=False,
            planned_action="right",
            planned_mask=0x81,
        )
        delay = SimpleNamespace(
            support=(2, 3),
            end_to_end_samples=20,
            computation_samples=30,
            pickup_samples=20,
            guard_active=False,
            overruns=1,
            censored=2,
            deadline_misses=3,
        )
        guidance = SimpleNamespace(
            support_covers_current=True,
            allowed_first_actions=("right",),
            repair_volumes=(("right", 7),),
            recovery_distances=(("right", 0.0),),
            safety_actions=("right",),
            safety_state_value=1.0,
            survival_actions=("right",),
            survival_frames=32,
            survival_bottleneck_margin=1.25,
            position_error=0.25,
        )
        trace_input = DecisionControlTraceInput(
            issue=issue,
            delay_estimate=delay,
            control_delay_frames=2,
            action_hold_frames=3,
            input_state={
                "input_raw": 0x01,
                "input_current": 0x01,
                "input_previous": 0x00,
            },
            local_pipeline_root_record={"frame": 100},
            local_pipeline_certificate_shadow=None,
            corridor_target=(100.0, 200.0, 12),
            damage_target_x=128.0,
            damage_target_half_width=16.0,
            damageable=True,
            active_item_count=4,
            item_objectives_enabled=True,
            corridor_context_changed=False,
            policy_guidance=guidance,
            player={
                "x": 10.0,
                "y": 20.0,
                "phase": 1,
                "focus_logic": 0,
                "secondary_character_active": True,
                "focus_transition_counter": 4,
            },
            projected_player_x=11.0,
            projected_player_y=21.0,
            control_origin_x=12.0,
            control_origin_y=22.0,
            phase_at_action=1,
            predeath_at_action=False,
            local_horizon=16,
            serialized_enemy_bodies=({"pointer": 1},),
            hit_started=False,
            hit_count=0,
            auto_confirm_event=None,
        )

        fields = build_decision_control_trace_fields(
            trace_input,
            local_certificate_timing_record=lambda value: {
                "source": value
            },
        )

        self.assertEqual(fields["deadline_guard"]["planned_mask"], 0x81)
        self.assertEqual(
            fields["control_delay_estimator"]["deadline_misses"],
            3,
        )
        self.assertEqual(
            fields["input_dispatch"]["transitions"],
            [[0x80, True]],
        )
        self.assertEqual(
            fields["planner_objective"]["corridor_target"]["deadline"],
            12,
        )
        self.assertEqual(fields["planner_guidance"]["repair_volumes"], {"right": 7})
        self.assertEqual(fields["player"]["projected_x"], 11.0)
        self.assertEqual(fields["player"]["focus_logic"], 0)
        self.assertTrue(fields["player"]["secondary_character_active"])
        self.assertEqual(fields["player"]["focus_transition_counter"], 4)
        self.assertEqual(
            fields["local_pipeline_timing"]["issue_recertificate"],
            {"source": "issue"},
        )
        self.assertEqual(
            fields["terminal_threat"]["mode"],
            "constant_terminal_action_heuristic",
        )
        self.assertEqual(fields["enemy_bodies"], [{"pointer": 1}])


if __name__ == "__main__":
    unittest.main()
