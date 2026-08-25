"""Exact-version live delivery for one accepted Final-B scale source.

The complete-source observer remains the shipped-runtime evidence producer.
This module adds only the narrow stateful delivery boundary needed by the
live controller: bind one accepted schedule to its physical context, rebase
it causally as manager frames advance, and fail closed on every mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Callable, Protocol

from th08_ecl_callback_model import CALLBACK_ADDRESSES
from th08_ecl_scale_schedule import (
    CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE,
    CALLBACK_SET_TIME_SCALE_RECIPROCAL,
    CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
)
from th08_ecl_tool.core import EclFile
from th08_live.runtime_ecl_identity import RuntimeEclAcceptedVersion
from th08_live.runtime_ecl_image import ECL_SUBROUTINE_TABLE_OFFSET
from th08_stage_ecl_catalog import NO_SCALE_WRITER_STAGE_ROUTE_INDICES

from th08_live.scale_source_trace import (
    CompleteScaleSourceCapture,
    FINAL_B_QUARTER_SCALE_BITS,
    FINAL_B_STAGE_ROUTE_INDEX,
    FinalBScaleSourceTraceService,
    capture_complete_scale_sources,
    final_b_scale_spell_id,
)
from th08_time_scale import (
    SCALE_COVERAGE_COMPLETE,
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)


FINAL_B_LIVE_SCALE_AUTHORITY_SCHEMA = (
    "th08-finalb-live-scale-schedule-authority-v1"
)
PRETARGET_UNIT_TRANSPORT_HORIZON = 256
NO_SCALE_WRITER_LIVE_AUTHORITY_SCHEMA = (
    "th08-no-scale-writer-live-schedule-authority-v1"
)
_SCALE_CALLBACK_INDICES = frozenset(
    {
        CALLBACK_SET_TIME_SCALE_RECIPROCAL,
        CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
        CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE,
    }
)
_SCALE_CALLBACK_ADDRESSES = frozenset(
    CALLBACK_ADDRESSES[index] for index in _SCALE_CALLBACK_INDICES
)


def _signed_int32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x100000000


@dataclass(frozen=True, slots=True)
class NoScaleWriterStaticAudit:
    static_sha256: str
    callback_instruction_count: int
    callback_indices: tuple[int, ...]
    incomplete_reasons: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return not self.incomplete_reasons

    def compact_record(self) -> dict[str, object]:
        return {
            "static_sha256": self.static_sha256,
            "callback_instruction_count": self.callback_instruction_count,
            "callback_indices": list(self.callback_indices),
            "scale_callback_indices": sorted(_SCALE_CALLBACK_INDICES),
            "complete": self.eligible,
            "incomplete_reasons": list(self.incomplete_reasons),
        }


def audit_no_scale_writer_ecl(ecl: EclFile) -> NoScaleWriterStaticAudit:
    """Prove that one complete decoded ECL image cannot select a scale callback."""

    callback_indices: list[int] = []
    reasons: list[str] = []
    instruction_count = 0
    for subroutine in ecl.subroutines:
        for instruction in subroutine.instructions:
            if instruction.opcode not in {0x88, 0x89}:
                continue
            instruction_count += 1
            location = f"sub{subroutine.index}:offset={instruction.offset:#x}"
            if not instruction.arguments:
                reasons.append(f"callback_index_missing:{location}")
                continue
            if instruction.parameter_mask & 0x01:
                reasons.append(f"callback_index_dynamic:{location}")
                continue
            callback_index = _signed_int32(instruction.arguments[0])
            callback_indices.append(callback_index)
            if instruction.opcode == 0x88 and not (
                0 <= callback_index < len(CALLBACK_ADDRESSES)
            ):
                reasons.append(f"callback_invoke_index_invalid:{location}")
            elif instruction.opcode == 0x89 and (
                callback_index >= len(CALLBACK_ADDRESSES)
            ):
                reasons.append(f"callback_install_index_invalid:{location}")
            if callback_index in _SCALE_CALLBACK_INDICES:
                reasons.append(
                    f"scale_callback_{callback_index}_present:{location}"
                )
    return NoScaleWriterStaticAudit(
        static_sha256=ecl.sha256,
        callback_instruction_count=instruction_count,
        callback_indices=tuple(sorted(set(callback_indices))),
        incomplete_reasons=tuple(dict.fromkeys(reasons)),
    )


@dataclass(frozen=True, slots=True)
class NoScaleWriterScheduleResolution:
    schedule: Th08TimeScaleSchedule
    status: str
    reason: str | None
    trace_record: dict[str, object] | None
    runtime_static_sha256: str | None
    inventory_source_count: int | None

    @property
    def planner_scale_authority(self) -> bool:
        return (
            self.status == "complete_exact_no_scale_writer_schedule"
            and self.schedule.coverage == SCALE_COVERAGE_COMPLETE
        )

    def compact_record(self) -> dict[str, object]:
        return {
            "kind": "no_scale_writer_live_scale_schedule_authority",
            "schema": NO_SCALE_WRITER_LIVE_AUTHORITY_SCHEMA,
            "status": self.status,
            "reason": self.reason,
            "planner_scale_schedule_authority": self.planner_scale_authority,
            "hard_action_authority": self.planner_scale_authority,
            "semantics_version": TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
            "runtime_static_sha256": self.runtime_static_sha256,
            "inventory_source_count": self.inventory_source_count,
            "root_scale_bits": self.schedule.root_scale_bits,
            "coverage": self.schedule.coverage,
            "complete_horizon": self.schedule.complete_horizon,
            "provenance": self.schedule.provenance,
            "fallback": (
                None
                if self.planner_scale_authority
                else "withhold_action_and_retry"
            ),
        }


@dataclass(frozen=True, slots=True)
class NoScaleWriterAuthorityDependencies:
    capture_sources: Callable[..., CompleteScaleSourceCapture] = (
        capture_complete_scale_sources
    )


class NoScaleWriterScheduleAuthority:
    """Publish a finite unit schedule only under an exact no-writer proof."""

    def __init__(
        self,
        ecl: EclFile,
        *,
        expected_static_sha256: str,
        expected_route_id: int,
        expected_difficulty_index: int,
        expected_stage_route_index: int,
        horizon_frames: int,
        dependencies: NoScaleWriterAuthorityDependencies = (
            NoScaleWriterAuthorityDependencies()
        ),
    ) -> None:
        if ecl.sha256 != expected_static_sha256.lower():
            raise ValueError("no-scale-writer ECL digest mismatch")
        if expected_stage_route_index not in NO_SCALE_WRITER_STAGE_ROUTE_INDICES:
            raise ValueError("stage is not in the pinned no-scale-writer catalog")
        if expected_route_id < 0 or expected_difficulty_index < 0:
            raise ValueError("no-scale-writer context cannot be negative")
        if horizon_frames <= 0:
            raise ValueError("no-scale-writer horizon must be positive")
        self.static_audit = audit_no_scale_writer_ecl(ecl)
        self._expected_static_sha256 = expected_static_sha256.lower()
        self._expected_route_id = expected_route_id
        self._expected_difficulty_index = expected_difficulty_index
        self._expected_stage_route_index = expected_stage_route_index
        self._horizon_frames = horizon_frames
        self._dependencies = dependencies
        self._binding: tuple[object, ...] | None = None
        self._inventory_source_count: int | None = None

    @property
    def static_eligible(self) -> bool:
        return self.static_audit.eligible

    def reset(self) -> None:
        self._binding = None
        self._inventory_source_count = None

    @staticmethod
    def _root_only(
        *,
        scale_bits: int,
        source_frame: int,
        status: str,
        reason: str,
        runtime_static_sha256: str | None = None,
        inventory_source_count: int | None = None,
        trace_record: dict[str, object] | None = None,
    ) -> NoScaleWriterScheduleResolution:
        return NoScaleWriterScheduleResolution(
            schedule=Th08TimeScaleSchedule.root_observation(
                scale_bits,
                source_frame=source_frame,
                provenance=f"no_scale_writer_authority_unavailable:{reason}",
            ),
            status=status,
            reason=reason,
            trace_record=trace_record,
            runtime_static_sha256=runtime_static_sha256,
            inventory_source_count=inventory_source_count,
        )

    def _complete(
        self,
        *,
        source_frame: int,
        runtime_version: RuntimeEclAcceptedVersion,
        trace_record: dict[str, object] | None,
    ) -> NoScaleWriterScheduleResolution:
        return NoScaleWriterScheduleResolution(
            schedule=Th08TimeScaleSchedule.constant(
                TH08_UNIT_TIME_SCALE_BITS,
                horizon=self._horizon_frames,
                provenance=(
                    "exact_runtime_ecl_no_scale_writer:"
                    f"{runtime_version.static_sha256}:"
                    f"stage={self._expected_stage_route_index}"
                ),
                source_frame=source_frame,
            ),
            status="complete_exact_no_scale_writer_schedule",
            reason=None,
            trace_record=trace_record,
            runtime_static_sha256=runtime_version.static_sha256,
            inventory_source_count=self._inventory_source_count,
        )

    def resolve(
        self,
        reader: object,
        *,
        runtime_version: RuntimeEclAcceptedVersion | None,
        source_frame: int,
        expected_manager_frame: int,
        gameplay_epoch: int,
        route_id: int,
        difficulty_index: int,
        stage_route_index: int,
        observed_root_scale_bits: int,
        observed_player_bomb_active: int,
    ) -> NoScaleWriterScheduleResolution:
        if not self.static_eligible:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_static_writer_inventory_unknown",
                reason="static_writer_inventory_unknown",
            )
        if runtime_version is None:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_runtime_identity_unavailable",
                reason="runtime_identity_unavailable",
            )
        runtime_key = (
            runtime_version.runtime_base,
            runtime_version.image_length,
            runtime_version.relocated_sha256,
            runtime_version.normalized_sha256,
            runtime_version.static_sha256,
        )
        context_matches = (
            route_id == self._expected_route_id
            and difficulty_index == self._expected_difficulty_index
            and stage_route_index == self._expected_stage_route_index
            and runtime_version.route_id == self._expected_route_id
            and runtime_version.difficulty_index
            == self._expected_difficulty_index
            and runtime_version.stage_route_index
            == self._expected_stage_route_index
            and runtime_version.static_sha256
            == self._expected_static_sha256
            and source_frame >= runtime_version.decision_frame
            and expected_manager_frame >= runtime_version.snapshot_frame
        )
        if not context_matches:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_immutable_context_mismatch",
                reason="immutable_context_mismatch",
                runtime_static_sha256=runtime_version.static_sha256,
            )
        if observed_root_scale_bits != TH08_UNIT_TIME_SCALE_BITS:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_nonunit_root",
                reason="nonunit_root",
                runtime_static_sha256=runtime_version.static_sha256,
            )
        if observed_player_bomb_active:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_bomb_active",
                reason="bomb_active",
                runtime_static_sha256=runtime_version.static_sha256,
            )
        binding = (runtime_key, gameplay_epoch)
        if self._binding is not None:
            if self._binding != binding:
                self.reset()
            else:
                return self._complete(
                    source_frame=source_frame,
                    runtime_version=runtime_version,
                    trace_record=None,
                )

        try:
            capture = self._dependencies.capture_sources(
                reader,
                expected_manager_frame=expected_manager_frame,
            )
        except (OSError, RuntimeError, TypeError, ValueError, struct.error) as error:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_source_inventory_error",
                reason=f"source_inventory_error:{type(error).__name__}",
                runtime_static_sha256=runtime_version.static_sha256,
            )
        phase = capture.phase_before
        expected_ecl_context = struct.pack(
            "<II",
            runtime_version.runtime_base,
            runtime_version.runtime_base + ECL_SUBROUTINE_TABLE_OFFSET,
        )
        reasons: list[str] = []
        if not capture.coherent:
            reasons.append(f"source_capture:{capture.status}")
        if not phase.gameplay_active:
            reasons.append("gameplay_inactive")
        if (
            phase.route_id != route_id
            or phase.difficulty_index != difficulty_index
            or phase.stage_route_index != stage_route_index
        ):
            reasons.append("source_context_mismatch")
        if phase.ecl_context != expected_ecl_context:
            reasons.append("runtime_ecl_context_mismatch")
        if phase.scale_bits != TH08_UNIT_TIME_SCALE_BITS:
            reasons.append("source_root_nonunit")
        if phase.player_bomb_active:
            reasons.append("source_bomb_active")
        if any(source.snapshot is None for source in capture.sources):
            reasons.append("invalid_active_main_vm")
        if any(
            source.installed_callback
            and source.installed_callback not in CALLBACK_ADDRESSES
            for source in capture.sources
        ):
            reasons.append("installed_callback_unknown")
        if any(
            source.installed_callback in _SCALE_CALLBACK_ADDRESSES
            for source in capture.sources
        ):
            reasons.append("installed_scale_callback_present")
        trace_record = {
            "kind": "no_scale_writer_source_inventory",
            "schema": NO_SCALE_WRITER_LIVE_AUTHORITY_SCHEMA,
            "status": "accepted" if not reasons else "unknown",
            "gameplay_epoch": gameplay_epoch,
            "source_frame": source_frame,
            "expected_manager_frame": expected_manager_frame,
            "static_audit": self.static_audit.compact_record(),
            "runtime_version": runtime_version.record(),
            "source_capture": capture.compact_record(),
            "incomplete_reasons": list(dict.fromkeys(reasons)),
            "changes_input": False,
        }
        if reasons:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                status="root_only_source_inventory_unknown",
                reason=reasons[0],
                runtime_static_sha256=runtime_version.static_sha256,
                inventory_source_count=len(capture.sources),
                trace_record=trace_record,
            )
        self._binding = binding
        self._inventory_source_count = len(capture.sources)
        return self._complete(
            source_frame=source_frame,
            runtime_version=runtime_version,
            trace_record=trace_record,
        )


class _ScaleSourceService(Protocol):
    @property
    def accepted_schedule(self) -> Th08TimeScaleSchedule | None: ...

    def observe_if_due(self, *args: object, **kwargs: object) -> dict[str, object] | None:
        ...

    def reset(self) -> None: ...


@dataclass(frozen=True)
class FinalBScaleScheduleResolution:
    schedule: Th08TimeScaleSchedule
    status: str
    reason: str | None
    trace_record: dict[str, object] | None
    origin_source_frame: int | None
    frame_offset: int | None
    baseline_predeath_counter: int | None
    source_player_phase: int | None

    @property
    def planner_scale_authority(self) -> bool:
        return (
            self.status == "complete_exact_source_schedule"
            and self.schedule.coverage == SCALE_COVERAGE_COMPLETE
        )

    @property
    def experimental_transport(self) -> bool:
        return (
            self.status == "complete_experimental_pretarget_unit_transport"
            and self.schedule.coverage == SCALE_COVERAGE_COMPLETE
        )

    def compact_record(self) -> dict[str, object]:
        return {
            "kind": "finalb_live_scale_schedule_authority",
            "schema": FINAL_B_LIVE_SCALE_AUTHORITY_SCHEMA,
            "status": self.status,
            "reason": self.reason,
            "planner_scale_schedule_authority": (
                self.planner_scale_authority
            ),
            "experimental_pretarget_transport": (
                self.experimental_transport
            ),
            "hard_action_authority": False,
            "semantics_version": TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
            "origin_source_frame": self.origin_source_frame,
            "current_source_frame": self.schedule.source_frame,
            "frame_offset": self.frame_offset,
            "baseline_predeath_counter": self.baseline_predeath_counter,
            "source_player_phase": self.source_player_phase,
            "root_scale_bits": self.schedule.root_scale_bits,
            "coverage": self.schedule.coverage,
            "complete_horizon": self.schedule.complete_horizon,
            "provenance": self.schedule.provenance,
            "fallback": (
                None
                if (
                    self.planner_scale_authority
                    or self.experimental_transport
                )
                else "terminate_and_release_keys"
            ),
        }


class FinalBScaleScheduleAuthority:
    """Bind and causally rebase one exact physical scale-source schedule."""

    def __init__(
        self,
        trace_service: _ScaleSourceService | FinalBScaleSourceTraceService,
    ) -> None:
        self._trace_service = trace_service
        self._origin_schedule: Th08TimeScaleSchedule | None = None
        self._binding: tuple[int, int, int, int, int | None] | None = None
        self._baseline_predeath_counter: int | None = None
        self._source_player_phase: int | None = None

    @property
    def origin_schedule(self) -> Th08TimeScaleSchedule | None:
        return self._origin_schedule

    def reset(self) -> None:
        self._origin_schedule = None
        self._binding = None
        self._baseline_predeath_counter = None
        self._source_player_phase = None
        self._trace_service.reset()

    @staticmethod
    def _root_only(
        *,
        scale_bits: int,
        source_frame: int,
        provenance: str,
        status: str,
        reason: str | None,
        trace_record: dict[str, object] | None = None,
        origin_source_frame: int | None = None,
        frame_offset: int | None = None,
        baseline_predeath_counter: int | None = None,
        source_player_phase: int | None = None,
    ) -> FinalBScaleScheduleResolution:
        return FinalBScaleScheduleResolution(
            schedule=Th08TimeScaleSchedule.root_observation(
                scale_bits,
                source_frame=source_frame,
                provenance=provenance,
            ),
            status=status,
            reason=reason,
            trace_record=trace_record,
            origin_source_frame=origin_source_frame,
            frame_offset=frame_offset,
            baseline_predeath_counter=baseline_predeath_counter,
            source_player_phase=source_player_phase,
        )

    @staticmethod
    def _experimental_unit_transport(
        *,
        source_frame: int,
    ) -> FinalBScaleScheduleResolution:
        return FinalBScaleScheduleResolution(
            schedule=Th08TimeScaleSchedule.constant(
                TH08_UNIT_TIME_SCALE_BITS,
                horizon=PRETARGET_UNIT_TRANSPORT_HORIZON,
                provenance=(
                    "experimental_pretarget_unit_transport_unknown_direction"
                ),
                source_frame=source_frame,
            ),
            status="complete_experimental_pretarget_unit_transport",
            reason="complete_finalb_source_not_yet_due",
            trace_record=None,
            origin_source_frame=None,
            frame_offset=None,
            baseline_predeath_counter=None,
            source_player_phase=None,
        )

    def _rebase(
        self,
        *,
        source_frame: int,
        observed_root_scale_bits: int,
        trace_record: dict[str, object] | None,
    ) -> FinalBScaleScheduleResolution:
        origin = self._origin_schedule
        assert origin is not None
        assert origin.source_frame is not None
        frame_offset = source_frame - origin.source_frame
        if frame_offset < 0 or frame_offset >= origin.complete_horizon:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                provenance="live_scale_source_frame_out_of_range",
                status="root_only_source_frame_out_of_range",
                reason="source_frame_out_of_range",
                trace_record=trace_record,
                origin_source_frame=origin.source_frame,
                frame_offset=frame_offset,
                baseline_predeath_counter=(
                    self._baseline_predeath_counter
                ),
                source_player_phase=self._source_player_phase,
            )
        expected_root = (
            origin.root_scale_bits
            if frame_offset == 0
            else origin.laser_scale_bits[frame_offset - 1]
        )
        if observed_root_scale_bits != expected_root:
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                provenance="live_scale_source_root_mismatch",
                status="root_only_observed_root_mismatch",
                reason="observed_root_mismatch",
                trace_record=trace_record,
                origin_source_frame=origin.source_frame,
                frame_offset=frame_offset,
                baseline_predeath_counter=(
                    self._baseline_predeath_counter
                ),
                source_player_phase=self._source_player_phase,
            )
        return FinalBScaleScheduleResolution(
            schedule=Th08TimeScaleSchedule.explicit(
                root_scale_bits=observed_root_scale_bits,
                player_scale_bits=origin.player_scale_bits[frame_offset:],
                laser_scale_bits=origin.laser_scale_bits[frame_offset:],
                complete=True,
                provenance=(
                    f"{origin.provenance}:live_exact_rebase:"
                    f"origin={origin.source_frame}"
                ),
                source_frame=source_frame,
            ),
            status="complete_exact_source_schedule",
            reason=None,
            trace_record=trace_record,
            origin_source_frame=origin.source_frame,
            frame_offset=frame_offset,
            baseline_predeath_counter=self._baseline_predeath_counter,
            source_player_phase=self._source_player_phase,
        )

    def resolve(
        self,
        reader: object,
        *,
        decision_frame: int,
        source_frame: int,
        gameplay_epoch: int,
        route_id: int,
        difficulty_index: int,
        stage_route_index: int,
        spell_id: int | None,
        observed_root_scale_bits: int,
        observed_player_bomb_active: int,
        player_phase: int,
        player_predeath_counter: int,
        hit_started: bool,
    ) -> FinalBScaleScheduleResolution:
        binding = (
            gameplay_epoch,
            route_id,
            difficulty_index,
            stage_route_index,
            spell_id,
        )
        target_context = (
            route_id == 2
            and 0 <= difficulty_index <= 3
            and stage_route_index == FINAL_B_STAGE_ROUTE_INDEX
            and spell_id == final_b_scale_spell_id(difficulty_index)
        )
        if self._origin_schedule is None and (
            not target_context
            or observed_root_scale_bits != FINAL_B_QUARTER_SCALE_BITS
            or hit_started
            or observed_player_bomb_active != 0
        ):
            if observed_root_scale_bits == TH08_UNIT_TIME_SCALE_BITS:
                return self._experimental_unit_transport(
                    source_frame=source_frame,
                )
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                provenance="live_scale_complete_source_not_due",
                status="root_only_complete_source_not_due",
                reason="complete_source_not_due",
            )
        if self._origin_schedule is not None and (
            hit_started
            or observed_player_bomb_active != 0
            or player_predeath_counter
            != self._baseline_predeath_counter
        ):
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                provenance="live_scale_continuation_invalid",
                status="root_only_continuation_invalid",
                reason=(
                    "fresh_hit"
                    if hit_started
                    else (
                        "bomb_active"
                        if observed_player_bomb_active != 0
                        else "predeath_baseline_changed"
                    )
                ),
                origin_source_frame=(
                    self._origin_schedule.source_frame
                    if self._origin_schedule is not None
                    else None
                ),
                baseline_predeath_counter=(
                    self._baseline_predeath_counter
                ),
            )
        if self._binding is not None and binding != self._binding:
            origin_source_frame = (
                self._origin_schedule.source_frame
                if self._origin_schedule is not None
                else None
            )
            return self._root_only(
                scale_bits=observed_root_scale_bits,
                source_frame=source_frame,
                provenance="live_scale_context_mismatch",
                status="root_only_context_mismatch",
                reason="immutable_context_mismatch",
                origin_source_frame=origin_source_frame,
                frame_offset=(
                    source_frame - origin_source_frame
                    if origin_source_frame is not None
                    else None
                ),
                baseline_predeath_counter=(
                    self._baseline_predeath_counter
                ),
                source_player_phase=self._source_player_phase,
            )

        trace_record: dict[str, object] | None = None
        if self._origin_schedule is None:
            trace_record = self._trace_service.observe_if_due(
                reader,
                decision_frame=decision_frame,
                expected_manager_frame=source_frame,
                gameplay_epoch=gameplay_epoch,
                route_id=route_id,
                difficulty_index=difficulty_index,
                stage_route_index=stage_route_index,
                spell_id=spell_id,
                observed_root_scale_bits=observed_root_scale_bits,
                observed_player_bomb_active=observed_player_bomb_active,
            )
            if trace_record is None:
                return self._root_only(
                    scale_bits=observed_root_scale_bits,
                    source_frame=source_frame,
                    provenance="live_scale_complete_source_not_due",
                    status="root_only_complete_source_not_due",
                    reason="complete_source_not_due",
                )
            accepted = self._trace_service.accepted_schedule
            source_capture = trace_record.get("source_capture")
            phase_before = (
                source_capture.get("phase_before")
                if isinstance(source_capture, dict)
                else None
            )
            if (
                trace_record.get("status")
                != "accepted_complete_source_trace"
                or accepted is None
                or accepted.coverage != SCALE_COVERAGE_COMPLETE
                or not isinstance(phase_before, dict)
                or type(phase_before.get("player_predeath_counter")) is not int
                or phase_before.get("player_predeath_counter")
                != player_predeath_counter
                or type(phase_before.get("player_phase")) is not int
                or phase_before.get("player_phase") != player_phase
            ):
                return self._root_only(
                    scale_bits=observed_root_scale_bits,
                    source_frame=source_frame,
                    provenance="live_scale_complete_source_unknown",
                    status="root_only_complete_source_unknown",
                    reason="complete_source_capture_unknown",
                    trace_record=trace_record,
                )
            self._origin_schedule = accepted
            self._binding = binding
            self._baseline_predeath_counter = player_predeath_counter
            self._source_player_phase = player_phase

        return self._rebase(
            source_frame=source_frame,
            observed_root_scale_bits=observed_root_scale_bits,
            trace_record=trace_record,
        )


__all__ = [
    "FINAL_B_LIVE_SCALE_AUTHORITY_SCHEMA",
    "NO_SCALE_WRITER_LIVE_AUTHORITY_SCHEMA",
    "NO_SCALE_WRITER_STAGE_ROUTE_INDICES",
    "FinalBScaleScheduleAuthority",
    "FinalBScaleScheduleResolution",
    "NoScaleWriterAuthorityDependencies",
    "NoScaleWriterScheduleAuthority",
    "NoScaleWriterScheduleResolution",
    "NoScaleWriterStaticAudit",
    "audit_no_scale_writer_ecl",
]
