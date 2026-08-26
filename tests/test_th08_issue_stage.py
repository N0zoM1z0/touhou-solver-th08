#!/usr/bin/env python3
"""Tests for the typed live physical-issue stage."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from runtime_agent import InputTransition
from th08_live.issue_controller import InputDispatch
from th08_live.issue_stage import (
    PhysicalIssueRequest,
    commit_physical_issue,
    observe_action_issue,
)
from th08_runtime.game_state import (
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_PLAYER,
    ADDR_SPELL_CARD_STATE,
    ADDR_STAGE_ROUTE_INDEX,
    PLAYER_PREDEATH_COUNTER_OFFSET,
)
from th08_live import CapturedIteration
from touhou_control.delay import DelayEstimate
from touhou_control.epochs import ActionIssueAlignment
from touhou_control.epochs import FrameWindow, HazardEpochAlignment
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)


class _Reader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def u8(self, address: int) -> int:
        self.calls.append(("u8", address))
        return 2

    def i32(self, address: int) -> int:
        self.calls.append(("i32", address))
        return 14

    def u32(self, address: int) -> int:
        self.calls.append(("u32", address))
        return 13


class _IssueController:
    def __init__(
        self,
        transitions: tuple[InputTransition, ...],
    ) -> None:
        self.transitions = transitions
        self.calls: list[tuple[int, int]] = []

    def dispatch(
        self,
        previous_mask: int,
        target_mask: int,
    ) -> InputDispatch:
        self.calls.append((previous_mask, target_mask))
        return InputDispatch(
            previous_mask=previous_mask,
            target_mask=target_mask,
            transitions=self.transitions,
            input_ms=0.25,
        )


class _DelayRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def issued(self, **arguments: object) -> None:
        self.calls.append(arguments)


class IssueStageTests(unittest.TestCase):
    @staticmethod
    def _capture() -> CapturedIteration:
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
                provenance="issue_stage_test_fixture",
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
            hazard_alignment=HazardEpochAlignment(
                source_frame=10,
                hazard_window=FrameWindow(10, 11),
                current_frame=12,
            ),
            snapshot_lag=2,
            player_to_hazard_lag=1,
            hazard_snapshot_age=1,
            bullet_snapshot_age_support=(1, 2),
            delay_estimate=DelayEstimate(
                nominal=2,
                support=(1, 2, 3),
                computation_samples=0,
                pickup_samples=0,
                end_to_end_samples=0,
                guard_active=False,
                overruns=0,
                censored=0,
            ),
            control_delay_frames=2,
            context_changed=False,
        )

    def _request(self) -> PhysicalIssueRequest:
        capture = self._capture()
        proposal = SimpleNamespace(
            decision=SimpleNamespace(mask=0x45),
        )
        decision = SimpleNamespace(mask=0x54)
        alignment = ActionIssueAlignment(
            source_frame=10,
            capture_frame=12,
            issue_frame=13,
            delay_support=(1, 2, 3),
        )
        return PhysicalIssueRequest(
            capture=capture,
            proposal=proposal,
            decision=decision,
            alignment=alignment,
            previous_mask=0x45,
            direction_mask=0xF0,
            pre_issue_action="left",
            pre_issue_mask=0x45,
            post_guard_action="right",
            post_guard_mask=0x54,
            planned_action="right",
            planned_mask=0x54,
            fresh_enemy_changed=True,
            recertification_ms=0.5,
            issue_path_started=1.0,
            iteration_started=0.5,
        )

    def test_observation_preserves_read_order_and_frame_identity(self) -> None:
        reader = _Reader()
        observation = observe_action_issue(
            reader,
            source_frame=10,
            capture_frame=12,
            delay_support=(1, 2, 3),
        )
        self.assertEqual(
            reader.calls,
            [
                ("u8", ADDR_PLAYER),
                (
                    "i32",
                    ADDR_PLAYER + PLAYER_PREDEATH_COUNTER_OFFSET,
                ),
                ("u32", ADDR_SPELL_CARD_STATE),
                ("u32", ADDR_STAGE_ROUTE_INDEX),
                ("u32", ADDR_ENEMY_MANAGER_FRAME),
            ],
        )
        self.assertEqual(observation.player_phase, 2)
        self.assertEqual(observation.predeath_counter, 14)
        self.assertTrue(observation.spell_active)
        self.assertEqual(observation.stage_route_index, 13)
        self.assertEqual(observation.issue_frame, 13)
        self.assertEqual(observation.alignment.action_lag, 3)

    def test_write_dispatch_registers_delay_and_next_actuator_state(
        self,
    ) -> None:
        transition = InputTransition(0x10, True)
        controller = _IssueController((transition,))
        recorder = _DelayRecorder()
        ticks = iter((1.004, 1.006))
        committed = commit_physical_issue(
            self._request(),
            issue_controller=controller,  # type: ignore[arg-type]
            delay_recorder=recorder,
            clock=lambda: next(ticks),
        )
        self.assertEqual(controller.calls, [(0x45, 0x54)])
        self.assertEqual(
            recorder.calls,
            [
                {
                    "snapshot_frame": 10,
                    "issue_frame": 13,
                    "expected_mask": 0x54,
                    "support_high": 3,
                    "support": (1, 2, 3),
                }
            ],
        )
        self.assertEqual(committed.issue.dispatch.transitions, (transition,))
        self.assertAlmostEqual(committed.issue.issue_path_ms, 4.0)
        self.assertAlmostEqual(committed.issue.observe_to_issue_ms, 506.0)
        self.assertEqual(committed.previous_mask, 0x54)
        self.assertEqual(committed.previous_direction, 0x50)

    def test_no_write_preserves_pending_delay_recorder_state(self) -> None:
        controller = _IssueController(())
        recorder = _DelayRecorder()
        ticks = iter((1.001, 1.002))
        committed = commit_physical_issue(
            self._request(),
            issue_controller=controller,  # type: ignore[arg-type]
            delay_recorder=recorder,
            clock=lambda: next(ticks),
        )
        self.assertEqual(recorder.calls, [])
        self.assertEqual(committed.issue.dispatch.transitions, ())
        self.assertEqual(committed.previous_mask, 0x54)
        self.assertEqual(committed.previous_direction, 0x50)

    def test_real_write_retains_complete_publication_serial_bracket(
        self,
    ) -> None:
        controller = _IssueController((InputTransition(0x10, True),))
        recorder = _DelayRecorder()
        serials = iter((40, 41))
        ticks = iter((1.001, 1.002))

        committed = commit_physical_issue(
            self._request(),
            issue_controller=controller,  # type: ignore[arg-type]
            delay_recorder=recorder,
            publication_serial_sampler=lambda: next(serials),
            clock=lambda: next(ticks),
        )

        bracket = committed.publication_serial_bracket
        self.assertEqual(bracket.status, "complete")
        self.assertEqual(bracket.pre_dispatch_serial, 40)
        self.assertEqual(bracket.post_dispatch_serial, 41)
        self.assertEqual(bracket.serial_advance_during_dispatch, 1)
        self.assertFalse(bracket.compact_record()["action_authority"])

    def test_publication_sampler_error_does_not_suppress_dispatch(
        self,
    ) -> None:
        controller = _IssueController((InputTransition(0x10, True),))
        recorder = _DelayRecorder()
        ticks = iter((1.001, 1.002))

        def unavailable() -> int:
            raise OSError("diagnostic read failed")

        committed = commit_physical_issue(
            self._request(),
            issue_controller=controller,  # type: ignore[arg-type]
            delay_recorder=recorder,
            publication_serial_sampler=unavailable,
            clock=lambda: next(ticks),
        )

        self.assertEqual(controller.calls, [(0x45, 0x54)])
        bracket = committed.publication_serial_bracket
        self.assertEqual(bracket.status, "read_error")
        self.assertIsNone(bracket.pre_dispatch_serial)
        self.assertIsNone(bracket.post_dispatch_serial)
        self.assertIn("pre:OSError", bracket.error)
        self.assertIn("post:OSError", bracket.error)

    def test_no_write_does_not_sample_publication_serial(self) -> None:
        request = replace(self._request(), previous_mask=0x54)
        controller = _IssueController(())
        recorder = _DelayRecorder()
        ticks = iter((1.001, 1.002))
        samples = 0

        def sample() -> int:
            nonlocal samples
            samples += 1
            return 1

        committed = commit_physical_issue(
            request,
            issue_controller=controller,  # type: ignore[arg-type]
            delay_recorder=recorder,
            publication_serial_sampler=sample,
            clock=lambda: next(ticks),
        )

        self.assertEqual(samples, 0)
        self.assertEqual(
            committed.publication_serial_bracket.status,
            "no_write",
        )


if __name__ == "__main__":
    unittest.main()
