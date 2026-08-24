from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

import th08_live_dodge_agent as live
from th08_local_planner import (
    IssueAdapter,
    IssueRequest,
    IssueTransaction,
    LocalProposal,
)
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)
from touhou_control.local_pipeline_oracle import LocalPipelineRoot


def _certificates(
    overrides: dict[str, tuple[int, float, float]],
):
    def provide(**kwargs):
        delays = kwargs["delay_frames"]
        return {
            action.name: live.RobustActionCertificate(
                action=action.name,
                delay_frames=delays,
                worst_collisions=overrides.get(
                    action.name,
                    (0, 4.0, 1.0),
                )[0],
                min_clearance=overrides.get(
                    action.name,
                    (0, 4.0, 1.0),
                )[1],
                cvar_risk=overrides.get(
                    action.name,
                    (0, 4.0, 1.0),
                )[2],
                worst_delay=max(delays),
            )
            for action in kwargs["actions"]
        }

    return provide


class IssueTransactionTests(unittest.TestCase):
    def _decision(self) -> live.Decision:
        return live.Decision(
            mask=live.SHOT | live.UP,
            action="up_fast",
            min_clearance=10.0,
            immediate_clearance=10.0,
            score=0.0,
            bomb=False,
            viability_constrained=True,
            viability_safe_action_count=3,
            viability_repair_volume=1,
            viability_recovery_distance=99.0,
            viability_control_reserve_deficit=7.0,
        )

    def _arguments(self) -> dict[str, object]:
        return {
            "player_x": 192.0,
            "player_y": 400.0,
            "previous_mask": live.SHOT | live.UP,
            "delay_frames": (2, 3),
            "action_hold_frames": 4,
            "bullets": (),
            "lasers": (),
            "enemy_bodies": (),
            "snapshot_lag": 0,
            "time_scale_schedule": Th08TimeScaleSchedule.constant(
                TH08_UNIT_TIME_SCALE_BITS,
                horizon=7,
                provenance="issue_transaction_test_fixture",
            ),
            "allowed_first_actions": ("up_fast", "left", "right"),
            "viability_repair_volumes": (
                ("up_fast", 1),
                ("left", 11),
                ("right", 7),
            ),
            "viability_recovery_distances": (
                ("up_fast", 99.0),
                ("left", 22.0),
                ("right", 33.0),
            ),
            "viability_safety_actions": ("left",),
            "viability_survival_actions": ("left",),
        }

    def test_commit_rebinds_selected_action_metadata_field_by_field(
        self,
    ) -> None:
        cases = (
            (
                {
                    "up_fast": (0, 1.0, 10.0),
                    "left": (0, 5.0, 0.0),
                },
                "up_fast",
                "preserve_planned_in_fresh_global_intersection",
                False,
            ),
            (
                {
                    "up_fast": (1, -2.0, 100.0),
                    "left": (0, 5.0, 0.0),
                    "right": (0, 2.0, 0.0),
                },
                "left",
                "replace_unsafe_from_fresh_global_intersection",
                False,
            ),
            (
                {
                    "up_fast": (1, -2.0, 100.0),
                    "left": (1, -3.0, 20.0),
                    "right": (1, -1.0, 30.0),
                },
                "down",
                "relax_empty_fresh_global_intersection",
                True,
            ),
        )
        rebound_fields = {
            "mask",
            "action",
            "bomb",
            "planned_focus",
            "robust_override",
            "robust_collisions",
            "robust_min_clearance",
            "robust_cvar_risk",
            "robust_worst_delay",
            "viability_constrained",
            "viability_safe_action_count",
            "viability_repair_volume",
            "viability_constraint_relaxed",
            "viability_recovery_distance",
            "viability_control_reserve_valid",
            "viability_safety_value_preferred",
            "viability_fresh_prefix_filtered",
            "viability_fresh_prefix_relaxed",
            "viability_survival_preferred",
            "issue_action_certificates",
            "issue_certificate_timing",
            "issue_recertification",
        }
        for overrides, selected, reason, relaxed in cases:
            with self.subTest(overrides=overrides):
                original = self._decision()
                provider = _certificates(overrides)
                with patch.object(
                    live,
                    "_robust_action_certificates",
                    side_effect=provider,
                ):
                    issued = live.issue_transaction_for_fresh_hazards(
                        original,
                        **self._arguments(),
                    )

                decision = issued.decision
                certificate = issued.transaction.selected_certificate
                self.assertEqual(decision.action, selected)
                self.assertEqual(decision.bomb, False)
                self.assertEqual(decision.mask & live.BOMB, 0)
                self.assertEqual(
                    decision.robust_collisions,
                    certificate.worst_collisions,
                )
                self.assertEqual(
                    decision.robust_min_clearance,
                    certificate.min_clearance,
                )
                self.assertEqual(
                    decision.robust_cvar_risk,
                    certificate.cvar_risk,
                )
                self.assertEqual(
                    decision.robust_worst_delay,
                    certificate.worst_delay,
                )
                self.assertEqual(
                    issued.transaction.selection_reason,
                    reason,
                )
                self.assertEqual(
                    decision.viability_constraint_relaxed,
                    relaxed,
                )
                self.assertEqual(
                    decision.viability_repair_volume,
                    dict(
                        self._arguments()["viability_repair_volumes"]
                    ).get(selected, 0),
                )
                self.assertEqual(
                    decision.viability_recovery_distance,
                    dict(
                        self._arguments()[
                            "viability_recovery_distances"
                        ]
                    ).get(selected),
                )
                for field in dataclasses.fields(live.Decision):
                    if field.name not in rebound_fields:
                        self.assertEqual(
                            getattr(decision, field.name),
                            getattr(original, field.name),
                            field.name,
                        )
                self.assertEqual(
                    issued.telemetry,
                    live.DecisionTelemetry.from_decision(
                        decision
                    ),
                )
                self.assertEqual(
                    issued.action_certificates.safe_actions,
                    issued.transaction.fresh_safe_actions,
                )
                self.assertEqual(decision.mask & live.BOMB, 0)

    def test_commit_is_idempotent(self) -> None:
        decision = self._decision()
        request = IssueRequest(
            **self._arguments(),
        )
        transaction = IssueTransaction(
            LocalProposal.from_decision(decision),
            request,
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=_certificates(
                    {"up_fast": (0, 1.0, 0.0)}
                ),
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        first = transaction.commit()
        second = transaction.commit()

        self.assertIs(first, second)
        self.assertEqual(first.decision.mask & live.BOMB, 0)

    def test_lazy_probe_commits_a_fresh_safe_planned_action_exactly(self) -> None:
        arguments = self._arguments()
        arguments["lazy_safe_action_probe"] = True
        calls: list[tuple[str, ...]] = []
        base_provider = _certificates({"up_fast": (0, 3.0, 2.0)})

        def provider(**kwargs):
            calls.append(tuple(action.name for action in kwargs["actions"]))
            return base_provider(**kwargs)

        transaction = IssueTransaction(
            LocalProposal.from_decision(self._decision()),
            IssueRequest(**arguments),
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=provider,
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        issued = transaction.commit()

        self.assertEqual(calls, [("up_fast",)])
        self.assertEqual(issued.decision.action, "up_fast")
        self.assertEqual(
            tuple(
                certificate.action
                for certificate in issued.decision.issue_action_certificates
            ),
            ("up_fast",),
        )
        self.assertEqual(
            issued.transaction.fresh_safe_actions,
            ("up_fast",),
        )
        self.assertFalse(
            issued.transaction.fresh_action_set_complete
        )
        self.assertEqual(
            issued.transaction.certificate_mode,
            "lazy_safe_selection",
        )
        self.assertEqual(issued.decision.mask & live.BOMB, 0)

    def test_lazy_probe_falls_back_to_the_complete_action_batch(self) -> None:
        arguments = self._arguments()
        arguments["lazy_safe_action_probe"] = True
        calls: list[tuple[str, ...]] = []
        base_provider = _certificates(
            {
                "up_fast": (1, -2.0, 100.0),
                "left": (0, 5.0, 0.0),
            }
        )

        def provider(**kwargs):
            calls.append(tuple(action.name for action in kwargs["actions"]))
            return base_provider(**kwargs)

        transaction = IssueTransaction(
            LocalProposal.from_decision(self._decision()),
            IssueRequest(**arguments),
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=provider,
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        issued = transaction.commit()

        self.assertEqual(calls[0], ("up_fast",))
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[1],
            tuple(action.name for action in live._PLANNER_ACTIONS),
        )
        self.assertEqual(issued.decision.action, "left")
        self.assertEqual(
            len(issued.decision.issue_action_certificates),
            len(live._PLANNER_ACTIONS),
        )
        self.assertTrue(
            issued.transaction.fresh_action_set_complete
        )
        self.assertEqual(
            issued.transaction.certificate_mode,
            "lazy_fallback_full",
        )
        self.assertEqual(issued.decision.mask & live.BOMB, 0)

    def test_lazy_probe_cannot_preserve_outside_hard_global_authority(
        self,
    ) -> None:
        arguments = self._arguments()
        arguments["lazy_safe_action_probe"] = True
        arguments["allowed_first_actions"] = ("left", "right")
        arguments["allowed_action_authority"] = "exact_global_test"
        calls: list[tuple[str, ...]] = []
        base_provider = _certificates(
            {
                "up_fast": (0, 9.0, 0.0),
                "left": (0, 5.0, 0.0),
                "right": (1, -1.0, 1.0),
            }
        )

        def provider(**kwargs):
            calls.append(tuple(action.name for action in kwargs["actions"]))
            return base_provider(**kwargs)

        transaction = IssueTransaction(
            LocalProposal.from_decision(self._decision()),
            IssueRequest(**arguments),
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=provider,
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        issued = transaction.commit()

        self.assertEqual(calls[0], ("up_fast",))
        self.assertEqual(
            calls[1],
            tuple(action.name for action in live._PLANNER_ACTIONS),
        )
        self.assertEqual(issued.decision.action, "left")
        self.assertEqual(
            issued.transaction.allowed_action_authority,
            "exact_global_test",
        )
        self.assertFalse(
            issued.transaction.global_constraint_relaxed
        )

    def test_allowed_action_authority_is_retained_at_fresh_issue(self) -> None:
        arguments = self._arguments()
        arguments["allowed_first_actions"] = ("left", "right")
        arguments["allowed_action_authority"] = (
            "causal_ordinary_nonspell_control_reserve_v1"
        )
        with patch.object(
            live,
            "_robust_action_certificates",
            side_effect=_certificates(
                {
                    "up_fast": (0, 9.0, 0.0),
                    "left": (0, 5.0, 0.0),
                    "right": (1, -1.0, 1.0),
                }
            ),
        ):
            issued = live.issue_transaction_for_fresh_hazards(
                self._decision(),
                **arguments,
            )

        self.assertEqual(issued.decision.action, "left")
        self.assertEqual(
            issued.transaction.allowed_action_authority,
            arguments["allowed_action_authority"],
        )
        self.assertEqual(
            issued.transaction.fresh_global_intersection,
            ("left",),
        )
        self.assertFalse(
            issued.transaction.global_constraint_relaxed
        )

    def test_explicit_pipeline_root_reaches_issue_certificate(self) -> None:
        root = LocalPipelineRoot(
            active_action="stay",
            held_desired_action="left",
            pending_action="left",
            remaining_delay_support=(0, 1),
        )
        arguments = self._arguments()
        arguments["pipeline_root"] = root
        observed_roots: list[object] = []
        base_provider = _certificates({})

        def provider(**kwargs):
            observed_roots.append(kwargs["pipeline_root"])
            return base_provider(**kwargs)

        transaction = IssueTransaction(
            LocalProposal.from_decision(self._decision()),
            IssueRequest(**arguments),
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=provider,
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        transaction.commit()

        self.assertEqual(observed_roots, [root])

    def test_allowed_action_authority_without_actions_is_rejected(self) -> None:
        arguments = self._arguments()
        arguments["allowed_first_actions"] = None
        arguments["allowed_action_authority"] = "authority_without_actions"
        transaction = IssueTransaction(
            LocalProposal.from_decision(self._decision()),
            IssueRequest(**arguments),
            IssueAdapter(
                actions=live._PLANNER_ACTIONS,
                certificate_provider=_certificates({}),
                timing_factory=live._LocalCertificateTimingAccumulator,
                shot_mask=live.SHOT,
                focus_mask=live.FOCUS,
                bomb_mask=live.BOMB,
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "requires allowed first actions",
        ):
            transaction.commit()

    def test_preference_applies_only_inside_fresh_global_safe_set(
        self,
    ) -> None:
        arguments = self._arguments()
        arguments["preferred_action"] = "up_fast"
        arguments["preference_reason"] = "kill_before_saturation"
        arguments["allowed_first_actions"] = ("up_fast", "up")
        decision = dataclasses.replace(
            self._decision(),
            mask=live.SHOT | live.FOCUS | live.UP,
            action="up",
            planned_focus=True,
        )
        with patch.object(
            live,
            "_robust_action_certificates",
            side_effect=_certificates(
                {
                    "up": (0, 6.0, 0.0),
                    "up_fast": (0, 2.0, 1.0),
                }
            ),
        ):
            issued = live.issue_transaction_for_fresh_hazards(
                decision,
                **arguments,
            )

        self.assertEqual(issued.decision.action, "up_fast")
        self.assertFalse(issued.decision.planned_focus)
        self.assertEqual(issued.decision.mask & live.BOMB, 0)
        self.assertTrue(issued.transaction.preference_applied)
        self.assertEqual(
            issued.transaction.selection_reason,
            "prefer_requested_fresh_global_intersection",
        )

        arguments["allowed_first_actions"] = ("up",)
        with patch.object(
            live,
            "_robust_action_certificates",
            side_effect=_certificates({}),
        ):
            rejected = live.issue_transaction_for_fresh_hazards(
                decision,
                **arguments,
            )
        self.assertEqual(rejected.decision.action, "up")
        self.assertFalse(rejected.transaction.preference_applied)

    def test_least_bad_coincidence_is_not_preference_authority(
        self,
    ) -> None:
        arguments = self._arguments()
        arguments["allowed_first_actions"] = None
        arguments["preferred_action"] = "up_fast"
        arguments["preference_reason"] = "kill_before_saturation"
        decision = dataclasses.replace(
            self._decision(),
            mask=live.SHOT | live.FOCUS | live.UP,
            action="up",
            planned_focus=True,
        )
        unsafe = {
            action.name: (1, -2.0, 10.0)
            for action in live._PLANNER_ACTIONS
        }
        unsafe["up_fast"] = (1, -1.0, 0.0)

        with patch.object(
            live,
            "_robust_action_certificates",
            side_effect=_certificates(unsafe),
        ):
            issued = live.issue_transaction_for_fresh_hazards(
                decision,
                **arguments,
            )

        self.assertEqual(issued.decision.action, "up_fast")
        self.assertEqual(
            issued.transaction.selection_reason,
            "replace_unsafe_with_least_bad",
        )
        self.assertFalse(issued.transaction.preference_applied)


if __name__ == "__main__":
    unittest.main()
