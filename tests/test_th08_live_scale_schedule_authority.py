from __future__ import annotations

import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

from th08_ecl_callback_model import CALLBACK_ADDRESSES
from th08_ecl_tool.core import parse_ecl
from th08_live.runtime_ecl_identity import RuntimeEclAcceptedVersion
from th08_live.runtime_ecl_image import ECL_SUBROUTINE_TABLE_OFFSET
from th08_live.scale_schedule_authority import (
    FinalBScaleScheduleAuthority,
    NoScaleWriterAuthorityDependencies,
    NoScaleWriterScheduleAuthority,
    audit_no_scale_writer_ecl,
)
from th08_live.sensing_trace import _time_scale_schedule_hard_authority
from th08_live.controller import (
    CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES,
    DIAGNOSTIC_ROOT_ONLY_SCALE_HORIZON,
    MAX_SENSOR_EPOCH_EXTENT_FRAMES,
    _corridor_scale_schedule_supported,
    _corridor_submission_policy_allows,
    _diagnostic_constant_root_time_scale,
)
from th08_corridor_adapter import TH08_CORRIDOR_CONFIG
from th08_time_scale import (
    SCALE_COVERAGE_COMPLETE,
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)


QUARTER_SCALE_BITS = 0x3E800000
PHYSICAL_C4_ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "runtime_reports"
    / "finalb_scale_source_replay_20260729_215613.json"
)
STAGE4A_ECL = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "decoded"
    / "ecldata4a.ecl"
)
FINALB_ECL = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "decoded"
    / "ecldata7.ecl"
)


class _TraceService:
    def __init__(
        self,
        schedule: Th08TimeScaleSchedule | None,
        *,
        due: bool = True,
        accepted: bool = True,
        captured_predeath: int = 0,
        captured_player_phase: int = 0,
    ) -> None:
        self._schedule = schedule
        self.due = due
        self.accepted = accepted
        self.captured_predeath = captured_predeath
        self.captured_player_phase = captured_player_phase
        self.calls = 0
        self.resets = 0

    @property
    def accepted_schedule(self) -> Th08TimeScaleSchedule | None:
        return self._schedule if self.accepted and self.calls else None

    def observe_if_due(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object] | None:
        self.calls += 1
        if not self.due:
            return None
        return {
            "kind": "finalb_scale_source_trace",
            "status": (
                "accepted_complete_source_trace"
                if self.accepted
                else "unknown"
            ),
            "source_capture": {
                "phase_before": {
                    "player_predeath_counter": self.captured_predeath,
                    "player_phase": self.captured_player_phase,
                }
            },
        }

    def reset(self) -> None:
        self.calls = 0
        self.resets += 1


class _NoWriterCapture:
    def __init__(self, *, installed_callback: int = 0) -> None:
        runtime_base = 0x02100000
        self.status = "coherent"
        self.coherent = True
        self.phase_before = SimpleNamespace(
            gameplay_active=True,
            route_id=2,
            difficulty_index=2,
            stage_route_index=3,
            ecl_context=struct.pack(
                "<II",
                runtime_base,
                runtime_base + ECL_SUBROUTINE_TABLE_OFFSET,
            ),
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            player_bomb_active=0,
        )
        self.sources = (
            SimpleNamespace(
                snapshot=object(),
                installed_callback=installed_callback,
            ),
        )

    def compact_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "source_count": len(self.sources),
        }


class _NoWriterCaptureDependency:
    def __init__(self, *, installed_callback: int = 0) -> None:
        self.installed_callback = installed_callback
        self.calls = 0
        self.expected_manager_frames: list[int] = []

    def __call__(self, *_args: object, **kwargs: object) -> _NoWriterCapture:
        self.calls += 1
        self.expected_manager_frames.append(
            int(kwargs["expected_manager_frame"])
        )
        return _NoWriterCapture(
            installed_callback=self.installed_callback,
        )


def _runtime_ecl_version() -> RuntimeEclAcceptedVersion:
    return RuntimeEclAcceptedVersion(
        runtime_base=0x02100000,
        image_length=STAGE4A_ECL.stat().st_size,
        relocated_sha256="1" * 64,
        normalized_sha256="2" * 64,
        static_sha256=parse_ecl(STAGE4A_ECL).sha256,
        route_id=2,
        difficulty_index=2,
        stage_route_index=3,
        gameplay_epoch=0,
        decision_frame=99,
        snapshot_frame=49,
    )


def _origin(*, source_frame: int = 100) -> Th08TimeScaleSchedule:
    return Th08TimeScaleSchedule.explicit(
        root_scale_bits=QUARTER_SCALE_BITS,
        player_scale_bits=(
            QUARTER_SCALE_BITS,
            QUARTER_SCALE_BITS,
            TH08_UNIT_TIME_SCALE_BITS,
            TH08_UNIT_TIME_SCALE_BITS,
        ),
        laser_scale_bits=(
            QUARTER_SCALE_BITS,
            TH08_UNIT_TIME_SCALE_BITS,
            TH08_UNIT_TIME_SCALE_BITS,
            TH08_UNIT_TIME_SCALE_BITS,
        ),
        complete=True,
        provenance="physical_complete_source_fixture",
        source_frame=source_frame,
    )


def _resolve(
    authority: FinalBScaleScheduleAuthority,
    *,
    source_frame: int = 100,
    scale_bits: int = QUARTER_SCALE_BITS,
    gameplay_epoch: int = 1,
    spell_id: int | None = 190,
    bomb_active: int = 0,
    player_phase: int = 0,
    predeath_counter: int = 0,
    hit_started: bool = False,
):
    return authority.resolve(
        object(),
        decision_frame=source_frame,
        source_frame=source_frame,
        gameplay_epoch=gameplay_epoch,
        route_id=2,
        difficulty_index=3,
        stage_route_index=7,
        spell_id=spell_id,
        observed_root_scale_bits=scale_bits,
        observed_player_bomb_active=bomb_active,
        player_phase=player_phase,
        player_predeath_counter=predeath_counter,
        hit_started=hit_started,
    )


class NoScaleWriterScheduleAuthorityTests(unittest.TestCase):
    def _authority(
        self,
        dependency: _NoWriterCaptureDependency,
    ) -> NoScaleWriterScheduleAuthority:
        ecl = parse_ecl(STAGE4A_ECL)
        return NoScaleWriterScheduleAuthority(
            ecl,
            expected_static_sha256=ecl.sha256,
            expected_route_id=2,
            expected_difficulty_index=2,
            expected_stage_route_index=3,
            horizon_frames=269,
            dependencies=NoScaleWriterAuthorityDependencies(
                capture_sources=dependency,
            ),
        )

    def _resolve(
        self,
        authority: NoScaleWriterScheduleAuthority,
        **overrides: object,
    ):
        keywords: dict[str, object] = {
            "runtime_version": _runtime_ecl_version(),
            "source_frame": 100,
            "expected_manager_frame": 50,
            "gameplay_epoch": 4,
            "route_id": 2,
            "difficulty_index": 2,
            "stage_route_index": 3,
            "observed_root_scale_bits": TH08_UNIT_TIME_SCALE_BITS,
            "observed_player_bomb_active": 0,
        }
        keywords.update(overrides)
        return authority.resolve(object(), **keywords)

    def test_stage4a_static_inventory_accepts_while_finalb_rejects(self) -> None:
        stage4a = audit_no_scale_writer_ecl(parse_ecl(STAGE4A_ECL))
        finalb = audit_no_scale_writer_ecl(parse_ecl(FINALB_ECL))

        self.assertTrue(stage4a.eligible)
        self.assertEqual(stage4a.callback_instruction_count, 18)
        self.assertFalse(finalb.eligible)
        self.assertTrue(
            any("scale_callback_18_present" in reason for reason in finalb.incomplete_reasons)
        )

    def test_exact_identity_unit_root_and_inventory_publish_authority(self) -> None:
        dependency = _NoWriterCaptureDependency()
        authority = self._authority(dependency)

        accepted = self._resolve(authority)

        self.assertTrue(accepted.planner_scale_authority)
        self.assertTrue(
            _time_scale_schedule_hard_authority(accepted.schedule)
        )
        self.assertEqual(accepted.schedule.complete_horizon, 269)
        self.assertTrue(
            all(
                bits == TH08_UNIT_TIME_SCALE_BITS
                for bits in (
                    *accepted.schedule.player_scale_bits,
                    *accepted.schedule.laser_scale_bits,
                )
            )
        )
        self.assertEqual(dependency.calls, 1)
        self.assertEqual(dependency.expected_manager_frames, [50])
        self.assertIsNotNone(accepted.trace_record)
        self.assertTrue(accepted.compact_record()["hard_action_authority"])

        continued = self._resolve(authority, source_frame=101)
        self.assertTrue(continued.planner_scale_authority)
        self.assertEqual(dependency.calls, 1)
        self.assertIsNone(continued.trace_record)

    def test_decision_and_manager_clocks_are_checked_separately(self) -> None:
        authority = self._authority(_NoWriterCaptureDependency())

        stale_decision = self._resolve(authority, source_frame=98)
        stale_manager = self._resolve(authority, expected_manager_frame=48)

        self.assertEqual(stale_decision.reason, "immutable_context_mismatch")
        self.assertEqual(stale_manager.reason, "immutable_context_mismatch")

    def test_scale_callback_root_and_context_mismatch_fail_closed(self) -> None:
        dependency = _NoWriterCaptureDependency(
            installed_callback=CALLBACK_ADDRESSES[18],
        )
        authority = self._authority(dependency)

        callback = self._resolve(authority)
        self.assertFalse(callback.planner_scale_authority)
        self.assertEqual(callback.reason, "installed_scale_callback_present")

        nonunit = self._resolve(
            self._authority(_NoWriterCaptureDependency()),
            observed_root_scale_bits=QUARTER_SCALE_BITS,
        )
        self.assertFalse(nonunit.planner_scale_authority)
        self.assertEqual(nonunit.reason, "nonunit_root")

        wrong_stage = self._resolve(
            self._authority(_NoWriterCaptureDependency()),
            stage_route_index=4,
        )
        self.assertFalse(wrong_stage.planner_scale_authority)
        self.assertEqual(wrong_stage.reason, "immutable_context_mismatch")

    def test_epoch_reset_recaptures_runtime_inventory(self) -> None:
        dependency = _NoWriterCaptureDependency()
        authority = self._authority(dependency)
        self.assertTrue(self._resolve(authority).planner_scale_authority)

        next_epoch = self._resolve(authority, gameplay_epoch=5)

        self.assertTrue(next_epoch.planner_scale_authority)
        self.assertEqual(dependency.calls, 2)


class FinalBScaleScheduleAuthorityTests(unittest.TestCase):
    def test_authority_only_submission_skips_diagnostic_schedules(
        self,
    ) -> None:
        self.assertFalse(
            _corridor_submission_policy_allows(
                authority_only=True,
                time_scale_hard_authority=False,
            )
        )
        self.assertTrue(
            _corridor_submission_policy_allows(
                authority_only=True,
                time_scale_hard_authority=True,
            )
        )
        self.assertTrue(
            _corridor_submission_policy_allows(
                authority_only=False,
                time_scale_hard_authority=False,
            )
        )

    def test_not_due_remains_root_only(self) -> None:
        service = _TraceService(_origin(), due=False)
        resolution = _resolve(FinalBScaleScheduleAuthority(service))

        self.assertFalse(resolution.planner_scale_authority)
        self.assertEqual(
            resolution.status,
            "root_only_complete_source_not_due",
        )
        self.assertEqual(resolution.schedule.complete_horizon, 0)
        self.assertEqual(service.calls, 1)

    def test_accepted_source_is_delivered_at_the_exact_root(self) -> None:
        service = _TraceService(_origin())
        authority = FinalBScaleScheduleAuthority(service)
        resolution = _resolve(authority)

        self.assertTrue(resolution.planner_scale_authority)
        self.assertEqual(
            resolution.status,
            "complete_exact_source_schedule",
        )
        self.assertEqual(
            resolution.schedule.coverage,
            SCALE_COVERAGE_COMPLETE,
        )
        self.assertEqual(resolution.schedule.complete_horizon, 4)
        self.assertEqual(resolution.origin_source_frame, 100)
        self.assertEqual(resolution.frame_offset, 0)
        self.assertIsNotNone(resolution.trace_record)
        self.assertIs(authority.origin_schedule, service.accepted_schedule)

    def test_later_frame_rebases_the_same_immutable_schedule(self) -> None:
        service = _TraceService(_origin())
        authority = FinalBScaleScheduleAuthority(service)
        _resolve(authority)

        resolution = _resolve(
            authority,
            source_frame=102,
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )

        self.assertTrue(resolution.planner_scale_authority)
        self.assertEqual(resolution.frame_offset, 2)
        self.assertEqual(resolution.schedule.source_frame, 102)
        self.assertEqual(
            resolution.schedule.player_scale_bits,
            (
                TH08_UNIT_TIME_SCALE_BITS,
                TH08_UNIT_TIME_SCALE_BITS,
            ),
        )
        self.assertEqual(
            resolution.schedule.laser_scale_bits,
            (
                TH08_UNIT_TIME_SCALE_BITS,
                TH08_UNIT_TIME_SCALE_BITS,
            ),
        )
        self.assertEqual(service.calls, 1)

    def test_observed_root_mismatch_fails_closed(self) -> None:
        service = _TraceService(_origin())
        authority = FinalBScaleScheduleAuthority(service)
        _resolve(authority)

        resolution = _resolve(
            authority,
            source_frame=101,
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )

        self.assertFalse(resolution.planner_scale_authority)
        self.assertEqual(
            resolution.status,
            "root_only_observed_root_mismatch",
        )
        self.assertEqual(
            resolution.compact_record()["fallback"],
            "terminate_and_release_keys",
        )

    def test_capture_from_a_future_frame_cannot_backfill_the_root(self) -> None:
        service = _TraceService(_origin(source_frame=101))
        resolution = _resolve(FinalBScaleScheduleAuthority(service))

        self.assertFalse(resolution.planner_scale_authority)
        self.assertEqual(
            resolution.status,
            "root_only_source_frame_out_of_range",
        )
        self.assertEqual(resolution.frame_offset, -1)

    def test_capture_that_becomes_predeath_contaminated_fails_closed(
        self,
    ) -> None:
        service = _TraceService(_origin(), captured_predeath=7)
        resolution = _resolve(FinalBScaleScheduleAuthority(service))

        self.assertFalse(resolution.planner_scale_authority)
        self.assertEqual(
            resolution.status,
            "root_only_complete_source_unknown",
        )

    def test_hit_bomb_and_context_changes_never_reuse_authority(self) -> None:
        wrong_target_service = _TraceService(_origin())
        wrong_target = _resolve(
            FinalBScaleScheduleAuthority(wrong_target_service),
            spell_id=189,
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )
        self.assertFalse(wrong_target.planner_scale_authority)
        self.assertTrue(wrong_target.experimental_transport)
        self.assertFalse(
            _time_scale_schedule_hard_authority(wrong_target.schedule)
        )
        self.assertEqual(
            wrong_target.compact_record()["hard_action_authority"],
            False,
        )
        self.assertEqual(wrong_target_service.calls, 0)

        for keyword, expected_reason in (
            ({"hit_started": True}, "fresh_hit"),
            ({"bomb_active": 1}, "bomb_active"),
            ({"predeath_counter": 7}, "predeath_baseline_changed"),
        ):
            with self.subTest(expected_reason=expected_reason):
                service = _TraceService(_origin())
                authority = FinalBScaleScheduleAuthority(service)
                _resolve(authority)
                resolution = _resolve(
                    authority,
                    source_frame=101,
                    **keyword,
                )
                self.assertFalse(resolution.planner_scale_authority)
                self.assertEqual(resolution.reason, expected_reason)

        service = _TraceService(_origin())
        authority = FinalBScaleScheduleAuthority(service)
        _resolve(authority)
        changed = _resolve(
            authority,
            source_frame=101,
            gameplay_epoch=2,
        )
        self.assertFalse(changed.planner_scale_authority)
        self.assertEqual(changed.reason, "immutable_context_mismatch")
        self.assertEqual(changed.origin_source_frame, 100)
        self.assertEqual(changed.frame_offset, 1)
        self.assertEqual(changed.source_player_phase, 0)

    def test_stable_predeath_residue_can_bind_but_change_cannot(self) -> None:
        service = _TraceService(_origin(), captured_predeath=7)
        authority = FinalBScaleScheduleAuthority(service)
        accepted = _resolve(authority, predeath_counter=7)

        self.assertTrue(accepted.planner_scale_authority)
        self.assertEqual(accepted.baseline_predeath_counter, 7)
        changed = _resolve(
            authority,
            source_frame=101,
            predeath_counter=8,
        )
        self.assertFalse(changed.planner_scale_authority)
        self.assertEqual(changed.reason, "predeath_baseline_changed")

    def test_contaminated_phase_three_can_bind_scale_delivery(self) -> None:
        service = _TraceService(
            _origin(),
            captured_predeath=7,
            captured_player_phase=3,
        )
        authority = FinalBScaleScheduleAuthority(service)

        accepted = _resolve(
            authority,
            player_phase=3,
            predeath_counter=7,
        )

        self.assertTrue(accepted.planner_scale_authority)
        self.assertEqual(accepted.baseline_predeath_counter, 7)
        self.assertEqual(accepted.source_player_phase, 3)
        self.assertEqual(
            accepted.compact_record()["source_player_phase"],
            3,
        )

    def test_explicit_reset_rearms_the_physical_service(self) -> None:
        service = _TraceService(_origin())
        authority = FinalBScaleScheduleAuthority(service)
        _resolve(authority)
        authority.reset()

        self.assertIsNone(authority.origin_schedule)
        self.assertEqual(service.resets, 1)
        again = _resolve(authority, gameplay_epoch=2)
        self.assertTrue(again.planner_scale_authority)

    def test_corridor_remains_disabled_for_nonunit_or_short_schedules(
        self,
    ) -> None:
        varying = _origin()
        self.assertFalse(
            _corridor_scale_schedule_supported(varying, horizon=4)
        )
        unit = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=4,
            source_frame=100,
        )
        self.assertTrue(
            _corridor_scale_schedule_supported(unit, horizon=4)
        )
        self.assertFalse(
            _corridor_scale_schedule_supported(unit, horizon=5)
        )

    def test_diagnostic_constant_schedule_has_no_hard_action_authority(
        self,
    ) -> None:
        diagnostic = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=269,
            provenance=(
                "diagnostic_constant_current_root_unknown_direction_"
                "no_authority"
            ),
            source_frame=100,
        )

        self.assertFalse(
            _time_scale_schedule_hard_authority(diagnostic)
        )

    def test_diagnostic_horizon_covers_maximum_corridor_submit_lead(
        self,
    ) -> None:
        root = Th08TimeScaleSchedule.root_observation(
            TH08_UNIT_TIME_SCALE_BITS,
            source_frame=100,
        )
        diagnostic = _diagnostic_constant_root_time_scale(root)
        required = (
            MAX_SENSOR_EPOCH_EXTENT_FRAMES
            + CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES
            + TH08_CORRIDOR_CONFIG.horizon_frames
            + 1
        )

        self.assertEqual(
            DIAGNOSTIC_ROOT_ONLY_SCALE_HORIZON,
            required,
        )
        self.assertTrue(
            _corridor_scale_schedule_supported(
                diagnostic,
                horizon=required,
            )
        )
        self.assertFalse(
            _time_scale_schedule_hard_authority(diagnostic)
        )

    def test_retained_physical_schedule_rebases_across_the_restore(
        self,
    ) -> None:
        payload = json.loads(PHYSICAL_C4_ARTIFACT.read_text(encoding="utf-8"))
        record = payload["record"]
        schedule_record = record["schedule"]
        origin = Th08TimeScaleSchedule.explicit(
            root_scale_bits=schedule_record["root_scale_bits"],
            player_scale_bits=tuple(
                schedule_record["player_scale_bits"]
            ),
            laser_scale_bits=tuple(
                schedule_record["laser_scale_bits"]
            ),
            complete=True,
            provenance=schedule_record["provenance"],
            source_frame=schedule_record["source_frame"],
        )
        service = _TraceService(origin)
        authority = FinalBScaleScheduleAuthority(service)
        source = origin.source_frame
        assert source is not None
        first = _resolve(
            authority,
            source_frame=source,
            scale_bits=origin.root_scale_bits,
        )
        self.assertTrue(first.planner_scale_authority)

        transition = _resolve(
            authority,
            source_frame=source + 239,
            scale_bits=QUARTER_SCALE_BITS,
        )
        self.assertEqual(
            transition.schedule.player_scale_bits[0],
            QUARTER_SCALE_BITS,
        )
        self.assertEqual(
            transition.schedule.laser_scale_bits[0],
            TH08_UNIT_TIME_SCALE_BITS,
        )

        restored = _resolve(
            authority,
            source_frame=source + 240,
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )
        self.assertTrue(restored.planner_scale_authority)
        self.assertEqual(restored.schedule.complete_horizon, 60)
        self.assertTrue(
            all(
                bits == TH08_UNIT_TIME_SCALE_BITS
                for bits in (
                    *restored.schedule.player_scale_bits,
                    *restored.schedule.laser_scale_bits,
                )
            )
        )

    def test_delivery_completion_uses_the_captured_restore_not_legacy_240(
        self,
    ) -> None:
        origin = _origin()
        authority = FinalBScaleScheduleAuthority(_TraceService(origin))
        source = origin.source_frame
        assert source is not None

        still_scaled = _resolve(
            authority,
            source_frame=source + 1,
            scale_bits=QUARTER_SCALE_BITS,
        )

        restored = _resolve(
            authority,
            source_frame=source + 2,
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        )
        self.assertTrue(restored.planner_scale_authority)


if __name__ == "__main__":
    unittest.main()
