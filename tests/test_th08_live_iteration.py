#!/usr/bin/env python3
"""Tests for immutable live-iteration stage contracts."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from th08_live import (
    CapturedIteration,
    FreshIssueResult,
    PublishedGuidance,
    ServiceUpdate,
)
from th08_live.issue_controller import InputDispatch
from touhou_control.delay import DelayEstimate
from touhou_control.epochs import (
    ActionIssueAlignment,
    FrameWindow,
    HazardEpochAlignment,
)
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)


class LiveIterationContractTests(unittest.TestCase):
    def _capture(self) -> CapturedIteration:
        alignment = HazardEpochAlignment(
            source_frame=10,
            hazard_window=FrameWindow(10, 11),
            current_frame=12,
        )
        delay = DelayEstimate(
            nominal=2,
            support=(1, 2, 3),
            computation_samples=0,
            pickup_samples=0,
            end_to_end_samples=0,
            guard_active=False,
            overruns=0,
            censored=0,
        )
        return CapturedIteration(
            gameplay_epoch=3,
            stage_route_index=1,
            spell_id=7,
            context_key=(3, 1, 7),
            source_frame=10,
            snapshot_frame=12,
            source_time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            time_scale_schedule=Th08TimeScaleSchedule.root_observation(
                TH08_UNIT_TIME_SCALE_BITS,
                source_frame=12,
                provenance="live_iteration_test_fixture",
            ),
            player_projection_authority=(
                "unknown_incomplete_source_schedule"
            ),
            player_x=100.0,
            player_y=200.0,
            projected_player_x=101.0,
            projected_player_y=200.0,
            native_active_mask=0x05,
            held_desired_mask=0x45,
            previous_direction=0x40,
            can_bomb=False,
            power=80.0,
            bombs=2.0,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            items=(),
            hazard_alignment=alignment,
            snapshot_lag=2,
            player_to_hazard_lag=1,
            hazard_snapshot_age=1,
            bullet_snapshot_age_support=(1, 2),
            delay_estimate=delay,
            control_delay_frames=2,
            context_changed=False,
        )

    def test_capture_rejects_inconsistent_physical_frame_identity(self) -> None:
        capture = self._capture()
        with self.assertRaisesRegex(ValueError, "snapshot lag"):
            CapturedIteration(
                **{
                    **capture.__dict__,
                    "snapshot_lag": 1,
                }
            )

    def test_stage_contracts_are_immutable_and_version_aligned(self) -> None:
        capture = self._capture()
        update = ServiceUpdate(
            context_key=capture.context_key,
            query_frame=capture.snapshot_frame,
            active_solution=object(),
            pending_solution=None,
            corridor_updated=True,
            elapsed_ms=1.25,
        )
        guidance = PublishedGuidance(
            capture=capture,
            service_update=update,
            request=object(),
            primary_query=object(),
            completed_query=object(),
            pipeline_shadow=object(),
        )

        self.assertIs(guidance.capture, capture)
        with self.assertRaises(FrozenInstanceError):
            guidance.service_update = update  # type: ignore[misc]

    def test_fresh_issue_binds_proposal_alignment_and_dispatch(self) -> None:
        capture = self._capture()
        proposal_decision = SimpleNamespace(mask=0x45)
        proposal = SimpleNamespace(decision=proposal_decision)
        issued_decision = SimpleNamespace(mask=0x05)
        alignment = ActionIssueAlignment(
            source_frame=10,
            capture_frame=12,
            issue_frame=12,
            delay_support=(1, 2, 3),
        )
        dispatch = InputDispatch(
            previous_mask=0x45,
            target_mask=0x05,
            transitions=(),
            input_ms=0.0,
        )

        result = FreshIssueResult(
            capture=capture,
            proposal=proposal,
            decision=issued_decision,
            alignment=alignment,
            dispatch=dispatch,
            issue_frame=12,
            pre_issue_action="left",
            pre_issue_mask=0x45,
            post_guard_action="stay",
            post_guard_mask=0x05,
            planned_action="stay",
            planned_mask=0x05,
            fresh_enemy_changed=True,
            deadline_missed=False,
            recertification_ms=0.5,
            issue_path_ms=1.0,
            observe_to_issue_ms=2.0,
        )

        self.assertEqual(result.dispatch.target_mask, result.decision.mask)
        with self.assertRaisesRegex(ValueError, "dispatch target"):
            FreshIssueResult(
                **{
                    **result.__dict__,
                    "dispatch": InputDispatch(0x45, 0x15, (), 0.0),
                }
            )


if __name__ == "__main__":
    unittest.main()
