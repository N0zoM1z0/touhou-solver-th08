"""Asynchronous future-source and global-policy production for Linux online play."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from th08_corridor_runtime import CorridorSolution, solve_corridor
from th08_ecl_tool.core import EclFile, parse_ecl
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_linux.online_authority import (
    OnlineActionAuthority,
    OnlineAuthorityResult,
    TH08_ONLINE_AUTHORITY_CONFIG,
)
from th08_linux.online_clock import (
    OnlineClockAssessment,
    OnlineClockObservation,
    OnlineUnitCadenceAuthority,
)
from th08_linux.planner import LinuxPlannerGuidance, LinuxPlannerSnapshot
from th08_live.current_pool_callbacks import (
    join_projection_callbacks_to_current_pool,
)
from th08_live.movement import (
    action_name_from_mask,
    project_player_for_read_lag,
)
from th08_live.runtime_ecl_identity import RuntimeEclAcceptedVersion
from th08_live.runtime_ecl_image import (
    capture_runtime_ecl_image,
    compare_runtime_ecl_image,
)
from th08_live.scale_schedule_authority import (
    FinalBScaleScheduleAuthority,
    NoScaleWriterScheduleAuthority,
)
from th08_live.scale_source_trace import (
    FinalBScaleSourceTraceConfiguration,
    FinalBScaleSourceTraceService,
)
from th08_runtime.ordinary_future_source_capture import (
    OrdinaryFutureSourceCaptureResult,
    capture_and_project_ordinary_future_sources,
)
from th08_stage_ecl_catalog import (
    ROUTE_STAGE_ECL_IDENTITIES,
    SCALE_MODEL_FINAL_B,
    SCALE_MODEL_NO_WRITER,
    StageEclIdentity,
)
from th08_time_scale import Th08TimeScaleSchedule
from touhou_control.async_policy import AsyncPolicyLead
from touhou_control.background_priority import lower_current_thread_priority
from touhou_control.corridor import CorridorConfig


@dataclass(frozen=True, slots=True)
class LinuxOnlineServiceConfig:
    corridor_config: CorridorConfig = TH08_ONLINE_AUTHORITY_CONFIG
    future_capture_interval_frames: int = 8
    corridor_submit_interval_frames: int = 8
    policy_initial_lead_frames: int = 80
    policy_overlap_frames: int = 8
    policy_minimum_lead_frames: int = 48
    policy_maximum_lead_frames: int = 180
    native_viability_workers: int = 8
    scale_schedule_horizon_frames: int = 512
    local_future_horizon_frames: int = 32

    def __post_init__(self) -> None:
        positive = (
            self.future_capture_interval_frames,
            self.corridor_submit_interval_frames,
            self.policy_initial_lead_frames,
            self.policy_minimum_lead_frames,
            self.policy_maximum_lead_frames,
            self.native_viability_workers,
            self.scale_schedule_horizon_frames,
            self.local_future_horizon_frames,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("online service intervals and horizons must be positive")
        if not (
            self.policy_minimum_lead_frames
            <= self.policy_initial_lead_frames
            <= self.policy_maximum_lead_frames
        ):
            raise ValueError("online policy lead is outside its bounds")
        if not 1 <= self.native_viability_workers <= 16:
            raise ValueError("native viability workers must be in [1, 16]")
        if self.corridor_config.frames_per_layer != 1:
            raise ValueError(
                "online global authority requires one physical frame per "
                "control layer"
            )

    @property
    def future_horizon_frames(self) -> int:
        return (
            self.policy_maximum_lead_frames
            + self.corridor_config.horizon_frames
            + self.future_capture_interval_frames
        )


@dataclass(frozen=True, slots=True)
class LinuxOnlineServiceUpdate:
    authority: OnlineAuthorityResult
    gameplay_epoch: int
    context: tuple[int, int, int | None]
    runtime_ecl_version: RuntimeEclAcceptedVersion | None
    scale_status: str
    future_status: str
    corridor_status: str
    native_epoch_current: bool
    clock_status: str
    clock_certified: bool
    clock_generation: int

    @property
    def guidance(self) -> LinuxPlannerGuidance:
        return self.authority.guidance


@dataclass(frozen=True, slots=True)
class _StageBinding:
    identity: StageEclIdentity
    ecl: EclFile
    static_image: bytes
    runtime_version: RuntimeEclAcceptedVersion | None
    scale_authority: (
        NoScaleWriterScheduleAuthority | FinalBScaleScheduleAuthority | None
    )


@dataclass(frozen=True, slots=True)
class _TaggedFutureCapture:
    context: tuple[int, int, int | None]
    submitted_input_epoch: int
    clock_generation: int
    work: Future[OrdinaryFutureSourceCaptureResult]


@dataclass(frozen=True, slots=True)
class _TaggedCorridorSolve:
    context: tuple[int, int, int | None]
    submitted_input_epoch: int
    policy_source_input_epoch: int
    clock_generation: int
    work: Future[CorridorSolution]


def _capture_future_sources(
    reader: object,
    ecl: EclFile,
    horizon_frames: int,
) -> OrdinaryFutureSourceCaptureResult:
    lower_current_thread_priority()
    return capture_and_project_ordinary_future_sources(
        reader,
        ecl,
        horizon_frames=horizon_frames,
        maximum_attempts=2,
    )


class LinuxOnlineFutureGlobalService:
    """Keep expensive future/global work outside the next-input deadline."""

    def __init__(
        self,
        *,
        reader: object,
        input_epoch_address: int,
        decoded_ecl_directory: Path | str,
        route_id: int,
        difficulty_index: int,
        config: LinuxOnlineServiceConfig = LinuxOnlineServiceConfig(),
    ) -> None:
        if input_epoch_address <= 0:
            raise ValueError("online input epoch address must be positive")
        if route_id < 0 or difficulty_index < 0:
            raise ValueError("route and difficulty cannot be negative")
        self._reader = reader
        self._input_epoch_address = input_epoch_address
        self._decoded_ecl_directory = Path(decoded_ecl_directory).resolve(strict=True)
        if not self._decoded_ecl_directory.is_dir():
            raise ValueError("decoded ECL directory is not a directory")
        self._route_id = route_id
        self._difficulty_index = difficulty_index
        self.config = config
        self._identities = {
            identity.route_index: identity
            for identity in ROUTE_STAGE_ECL_IDENTITIES.values()
        }
        self._binding: _StageBinding | None = None
        self._stage_route_index: int | None = None
        self._gameplay_epoch = 0
        self._context: tuple[int, int, int | None] | None = None
        self._previous_player_phase: int | None = None
        self._future_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="th08-linux-online-future",
        )
        self._corridor_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="th08-linux-online-corridor",
        )
        self._future_work: _TaggedFutureCapture | None = None
        self._corridor_work: _TaggedCorridorSolve | None = None
        self._future_result: OrdinaryFutureSourceCaptureResult | None = None
        self._future_result_clock_generation: int | None = None
        self._last_future_submit_epoch = -10**9
        self._last_corridor_submit_epoch = -10**9
        self._clock_authority = OnlineUnitCadenceAuthority()
        self._lead = AsyncPolicyLead(
            initial_frames=config.policy_initial_lead_frames,
            overlap_frames=config.policy_overlap_frames,
            minimum_frames=config.policy_minimum_lead_frames,
            maximum_frames=config.policy_maximum_lead_frames,
        )
        self._authority = OnlineActionAuthority(
            corridor_config=config.corridor_config,
            local_future_horizon_frames=(
                config.local_future_horizon_frames
            ),
        )
        self.future_submissions = 0
        self.future_completions = 0
        self.future_rejections = 0
        self.corridor_submissions = 0
        self.corridor_completions = 0
        self.corridor_rejections = 0
        self.runtime_identity_attempts = 0
        self.runtime_identity_acceptances = 0
        self._closed = False

    @property
    def action_authority(self) -> OnlineActionAuthority:
        return self._authority

    def _native_epoch_matches(self, source_epoch: int) -> bool:
        return self._reader.u32(self._input_epoch_address) == (
            source_epoch & 0xFFFFFFFF
        )

    def _assess_physical_clock(
        self,
        snapshot: LinuxPlannerSnapshot,
        state: Mapping[str, object],
        *,
        source_epoch: int,
        context: tuple[int, int, int | None],
    ) -> OnlineClockAssessment:
        player = state.get("player")
        if not isinstance(player, Mapping):
            raise RuntimeError("online clock root omitted player state")
        return self._clock_authority.observe(
            OnlineClockObservation(
                source_input_epoch=source_epoch,
                captured_source_input_epoch=snapshot.source_input_epoch,
                manager_frame=snapshot.frame,
                engine_flags=int(state["engine_flags"]),
                player_phase=snapshot.player_phase,
                bomb_active=bool(player["bomb_active"]),
                dialogue_active=snapshot.dialogue_active,
                scripted_update_freeze=snapshot.scripted_update_freeze,
                context=context,
            )
        )

    @staticmethod
    def _spell_id(state: Mapping[str, object]) -> int | None:
        spell = state.get("spell")
        if not isinstance(spell, Mapping) or not bool(spell.get("active")):
            return None
        value = spell.get("spell_id")
        return int(value) if value is not None else None

    def _load_stage(self, stage_route_index: int) -> _StageBinding | None:
        identity = self._identities.get(stage_route_index)
        if identity is None:
            return None
        path = self._decoded_ecl_directory / identity.filename
        static_image = path.read_bytes()
        ecl = parse_ecl(path)
        if ecl.sha256 != identity.sha256:
            raise RuntimeError(
                f"decoded ECL identity mismatch for {identity.filename}"
            )
        scale_authority: (
            NoScaleWriterScheduleAuthority | FinalBScaleScheduleAuthority | None
        )
        if identity.scale_model == SCALE_MODEL_NO_WRITER:
            scale_authority = NoScaleWriterScheduleAuthority(
                ecl,
                expected_static_sha256=identity.sha256,
                expected_route_id=self._route_id,
                expected_difficulty_index=self._difficulty_index,
                expected_stage_route_index=stage_route_index,
                horizon_frames=self.config.scale_schedule_horizon_frames,
            )
        elif identity.scale_model == SCALE_MODEL_FINAL_B:
            scale_authority = FinalBScaleScheduleAuthority(
                FinalBScaleSourceTraceService(
                    FinalBScaleSourceTraceConfiguration(
                        static_path=path,
                        expected_static_sha256=identity.sha256,
                        expected_route_id=self._route_id,
                        expected_difficulty_index=self._difficulty_index,
                        expected_stage_route_index=stage_route_index,
                    )
                )
            )
        else:
            scale_authority = None
        return _StageBinding(
            identity=identity,
            ecl=ecl,
            static_image=static_image,
            runtime_version=None,
            scale_authority=scale_authority,
        )

    def _set_context(
        self,
        *,
        stage_route_index: int,
        spell_id: int | None,
    ) -> tuple[int, int, int | None]:
        if stage_route_index != self._stage_route_index:
            self._stage_route_index = stage_route_index
            self._gameplay_epoch += 1
            self._binding = self._load_stage(stage_route_index)
            self._previous_player_phase = None
            self._future_result = None
            self._future_result_clock_generation = None
            self._last_future_submit_epoch = -10**9
            self._last_corridor_submit_epoch = -10**9
        context = (self._gameplay_epoch, stage_route_index, spell_id)
        if context != self._context:
            self._context = context
            self._future_result = None
            self._future_result_clock_generation = None
            self._authority.reset(context)
        return context

    def _establish_runtime_identity(
        self,
        *,
        source_epoch: int,
        snapshot_frame: int,
        context: tuple[int, int, int | None],
    ) -> str:
        binding = self._binding
        if binding is None:
            return "stage-ecl-unsupported"
        if binding.runtime_version is not None:
            return "exact-runtime-ecl"
        if not self._native_epoch_matches(source_epoch):
            return "source-epoch-expired"
        self.runtime_identity_attempts += 1
        try:
            capture = capture_runtime_ecl_image(self._reader)
            identity = compare_runtime_ecl_image(
                capture,
                binding.static_image,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return "runtime-ecl-capture-unavailable"
        if not self._native_epoch_matches(source_epoch):
            return "runtime-ecl-capture-crossed-input-epoch"
        if not identity.exact_match:
            return "runtime-ecl-byte-mismatch"
        version = RuntimeEclAcceptedVersion(
            runtime_base=capture.runtime_base,
            image_length=capture.image_length,
            relocated_sha256=capture.relocated_sha256,
            normalized_sha256=capture.normalized_sha256,
            static_sha256=identity.static_sha256,
            route_id=self._route_id,
            difficulty_index=self._difficulty_index,
            stage_route_index=context[1],
            gameplay_epoch=context[0],
            decision_frame=snapshot_frame,
            snapshot_frame=snapshot_frame,
        )
        self._binding = replace(binding, runtime_version=version)
        self.runtime_identity_acceptances += 1
        return "exact-runtime-ecl"

    def _scale_schedule(
        self,
        snapshot: LinuxPlannerSnapshot,
        state: Mapping[str, object],
        *,
        context: tuple[int, int, int | None],
    ) -> tuple[Th08TimeScaleSchedule | None, str]:
        binding = self._binding
        if binding is None or binding.runtime_version is None:
            return None, "runtime-ecl-unavailable"
        authority = binding.scale_authority
        if authority is None:
            return None, "dynamic-scale-authority-not-wired"
        player = state.get("player")
        if not isinstance(player, Mapping):
            return None, "player-state-unavailable"
        if isinstance(authority, NoScaleWriterScheduleAuthority):
            resolution = authority.resolve(
                self._reader,
                runtime_version=binding.runtime_version,
                source_frame=snapshot.frame,
                expected_manager_frame=snapshot.frame,
                gameplay_epoch=context[0],
                route_id=self._route_id,
                difficulty_index=self._difficulty_index,
                stage_route_index=context[1],
                observed_root_scale_bits=snapshot.time_scale_bits,
                observed_player_bomb_active=int(player["bomb_active"]),
            )
        else:
            phase = int(player["phase"])
            resolution = authority.resolve(
                self._reader,
                decision_frame=snapshot.frame,
                source_frame=snapshot.frame,
                gameplay_epoch=context[0],
                route_id=self._route_id,
                difficulty_index=self._difficulty_index,
                stage_route_index=context[1],
                spell_id=context[2],
                observed_root_scale_bits=snapshot.time_scale_bits,
                observed_player_bomb_active=int(player["bomb_active"]),
                player_phase=phase,
                player_predeath_counter=int(player["predeath_counter"]),
                hit_started=(
                    phase == 2 and self._previous_player_phase != 2
                ),
            )
            self._previous_player_phase = phase
        return (
            resolution.schedule if resolution.planner_scale_authority else None,
            resolution.status,
        )

    @staticmethod
    def _future_matches_context(
        result: OrdinaryFutureSourceCaptureResult,
        context: tuple[int, int, int | None],
        *,
        route_id: int,
        difficulty_index: int,
    ) -> bool:
        payload = result.snapshot.payload
        compact = payload.get("compact_state") if isinstance(payload, dict) else None
        if not isinstance(compact, dict):
            return False
        observed_route = compact.get("route_id")
        observed_difficulty = compact.get("difficulty_index")
        observed_stage = compact.get("stage_route_index")
        if not all(
            type(value) is int
            for value in (
                observed_route,
                observed_difficulty,
                observed_stage,
            )
        ):
            return False
        projection = result.closure.projection
        return bool(
            observed_route == route_id
            and observed_difficulty == difficulty_index
            and observed_stage == context[1]
            and compact.get("spell_id") == context[2]
            and projection is not None
            and projection.source_closure_complete
            and projection.coverage.complete
        )

    def _poll_background(
        self,
        *,
        current_frame: int,
        current_input_epoch: int,
        context: tuple[int, int, int | None],
        clock: OnlineClockAssessment,
    ) -> tuple[str, str]:
        future_status = "idle"
        corridor_status = "idle"
        if self._future_work is not None:
            if not self._future_work.work.done():
                future_status = "running"
            else:
                tagged = self._future_work
                self._future_work = None
                try:
                    result = tagged.work.result()
                except (OSError, RuntimeError, TypeError, ValueError):
                    self.future_rejections += 1
                    future_status = "capture-error"
                else:
                    if (
                        tagged.context == context
                        and tagged.clock_generation == clock.generation
                        and clock.allowed
                        and self._future_matches_context(
                            result,
                            context,
                            route_id=self._route_id,
                            difficulty_index=self._difficulty_index,
                        )
                    ):
                        self._future_result = result
                        self._future_result_clock_generation = clock.generation
                        self.future_completions += 1
                        future_status = "fresh-complete"
                    else:
                        self.future_rejections += 1
                        future_status = "stale-or-incomplete"
        if self._corridor_work is not None:
            if not self._corridor_work.work.done():
                corridor_status = "running"
            else:
                tagged = self._corridor_work
                self._corridor_work = None
                try:
                    solution = tagged.work.result()
                except (OSError, RuntimeError, TypeError, ValueError):
                    self.corridor_rejections += 1
                    corridor_status = "solve-error"
                else:
                    if (
                        tagged.context == context
                        and tagged.clock_generation == clock.generation
                        and clock.allowed
                        and self._authority.publish(
                            solution,
                            solution_source_input_epoch=(
                                tagged.policy_source_input_epoch
                            ),
                            current_frame=current_frame,
                            current_input_epoch=current_input_epoch,
                            context=context,
                        )
                    ):
                        elapsed = (
                            solution.worker_ms
                            if solution.worker_ms is not None
                            else solution.solve_ms
                        )
                        self._lead.observe(elapsed)
                        self.corridor_completions += 1
                        corridor_status = "published"
                    else:
                        self.corridor_rejections += 1
                        corridor_status = "stale-context-or-clock"
        if clock.allowed:
            self._authority.advance(
                current_frame=current_frame,
                current_input_epoch=current_input_epoch,
                context=context,
            )
        else:
            self._authority.reset(context)
        return future_status, corridor_status

    def _submit_future_if_due(
        self,
        *,
        source_input_epoch: int,
        context: tuple[int, int, int | None],
        clock_generation: int,
    ) -> bool:
        binding = self._binding
        if (
            binding is None
            or binding.runtime_version is None
            or self._future_work is not None
            or source_input_epoch - self._last_future_submit_epoch
            < self.config.future_capture_interval_frames
        ):
            return False
        work = self._future_executor.submit(
            _capture_future_sources,
            self._reader,
            binding.ecl,
            self.config.future_horizon_frames,
        )
        self._future_work = _TaggedFutureCapture(
            context,
            source_input_epoch,
            clock_generation,
            work,
        )
        self._last_future_submit_epoch = source_input_epoch
        self.future_submissions += 1
        return True

    def _submit_corridor_if_due(
        self,
        snapshot: LinuxPlannerSnapshot,
        *,
        source_input_epoch: int,
        current_input: int,
        context: tuple[int, int, int | None],
        schedule: Th08TimeScaleSchedule,
        clock: OnlineClockAssessment,
    ) -> bool:
        binding = self._binding
        result = self._future_result
        if (
            binding is None
            or binding.runtime_version is None
            or result is None
            or self._future_result_clock_generation != clock.generation
            or not clock.allowed
            or self._corridor_work is not None
            or self._authority.pending_solution is not None
            or source_input_epoch - self._last_corridor_submit_epoch
            < self.config.corridor_submit_interval_frames
        ):
            return False
        projection = result.closure.projection
        if not isinstance(projection, OrdinaryFutureHazardProjection):
            return False
        policy_lead = self._lead.frames
        policy_source = snapshot.frame + policy_lead
        policy_source_input_epoch = source_input_epoch + policy_lead
        if (
            projection.root_frame > policy_source
            or projection.horizon_frame
            < policy_source + self.config.corridor_config.horizon_frames
        ):
            return False

        bullets = snapshot.bullets
        callback_join = None
        if not projection.current_pool_callback_composition_complete:
            callback_join = join_projection_callbacks_to_current_pool(
                bullets,
                projection=projection,
                bullet_root_frame=snapshot.frame,
                policy_source_frame=policy_source,
                policy_horizon_frames=(
                    self.config.corridor_config.horizon_frames
                ),
                time_scale=1.0,
                bullet_frame_uncertainty=0,
            )
            if not callback_join.complete:
                self.corridor_rejections += 1
                return False
            bullets = callback_join.bullets

        player_scale = schedule.require_player_horizon(policy_lead)
        forecast_x, forecast_y = project_player_for_read_lag(
            snapshot.player_x,
            snapshot.player_y,
            current_input,
            policy_lead,
            player_scale_bits=player_scale,
        )
        work = self._corridor_executor.submit(
            solve_corridor,
            source_frame=policy_source,
            snapshot_frame=snapshot.frame,
            forecast_lead_frames=policy_lead,
            player_x=forecast_x,
            player_y=forecast_y,
            bullets=bullets,
            lasers=snapshot.lasers,
            enemy_bodies=snapshot.enemy_bodies,
            future_hazard_projection=projection,
            current_pool_callback_join=callback_join,
            runtime_ecl_version=binding.runtime_version,
            snapshot_lag=0,
            control_delay_candidates=(0,),
            observed_control_delay_candidates=(0,),
            nominal_control_delay=0,
            active_action=action_name_from_mask(current_input),
            context_key=context,
            background_low_priority=True,
            native_viability_worker_limit=(
                self.config.native_viability_workers
            ),
            time_scale_schedule=schedule,
            corridor_config=self.config.corridor_config,
        )
        self._corridor_work = _TaggedCorridorSolve(
            context,
            source_input_epoch,
            policy_source_input_epoch,
            clock.generation,
            work,
        )
        self._last_corridor_submit_epoch = source_input_epoch
        self.corridor_submissions += 1
        return True

    @staticmethod
    def _withheld(
        *,
        reason: str,
        schedule: Th08TimeScaleSchedule | None = None,
    ) -> OnlineAuthorityResult:
        return OnlineAuthorityResult(
            guidance=LinuxPlannerGuidance(time_scale_schedule=schedule),
            status="withheld",
            reasons=(reason,),
            solution_source_frame=None,
            solution_source_input_epoch=None,
            policy_version=None,
            global_constraint_applied=False,
            future_projection_applied_locally=False,
        )

    def update(
        self,
        snapshot: LinuxPlannerSnapshot,
        state: Mapping[str, object],
        *,
        source_epoch: int,
        current_input: int,
    ) -> LinuxOnlineServiceUpdate:
        if self._closed:
            raise RuntimeError("Linux online future/global service is closed")
        stage = int(state["stage_route_index"])
        context = self._set_context(
            stage_route_index=stage,
            spell_id=self._spell_id(state),
        )
        if not self._native_epoch_matches(source_epoch):
            return LinuxOnlineServiceUpdate(
                authority=self._withheld(reason="source-epoch-expired"),
                gameplay_epoch=context[0],
                context=context,
                runtime_ecl_version=(
                    self._binding.runtime_version
                    if self._binding is not None
                    else None
                ),
                scale_status="not-queried",
                future_status="not-polled",
                corridor_status="not-polled",
                native_epoch_current=False,
                clock_status="not-observed-source-epoch-expired",
                clock_certified=False,
                clock_generation=self._clock_authority.generation,
            )
        clock = self._assess_physical_clock(
            snapshot,
            state,
            source_epoch=source_epoch,
            context=context,
        )
        if not clock.allowed:
            self._future_result = None
            self._future_result_clock_generation = None
            self._authority.reset(context)
        self._establish_runtime_identity(
            source_epoch=source_epoch,
            snapshot_frame=snapshot.frame,
            context=context,
        )
        future_status, corridor_status = self._poll_background(
            current_frame=snapshot.frame,
            current_input_epoch=source_epoch,
            context=context,
            clock=clock,
        )
        schedule, scale_status = self._scale_schedule(
            snapshot,
            state,
            context=context,
        )
        if clock.allowed and self._submit_future_if_due(
            source_input_epoch=source_epoch,
            context=context,
            clock_generation=clock.generation,
        ):
            future_status = "submitted"
        if clock.allowed and schedule is not None and self._submit_corridor_if_due(
            snapshot,
            source_input_epoch=source_epoch,
            current_input=current_input,
            context=context,
            schedule=schedule,
            clock=clock,
        ):
            corridor_status = "submitted"

        native_epoch_current = self._native_epoch_matches(source_epoch)
        binding = self._binding
        if schedule is None:
            authority = self._withheld(reason=scale_status)
        elif not native_epoch_current:
            authority = self._withheld(
                reason="service-work-crossed-input-epoch",
                schedule=schedule,
            )
        elif not clock.allowed:
            authority = self._withheld(
                reason=clock.reason,
                schedule=schedule,
            )
        else:
            authority = self._authority.guidance_for(
                snapshot,
                current_input_epoch=source_epoch,
                current_input=current_input,
                context=context,
                runtime_ecl_version=(
                    binding.runtime_version if binding is not None else None
                ),
                time_scale_schedule=schedule,
            )
        return LinuxOnlineServiceUpdate(
            authority=authority,
            gameplay_epoch=context[0],
            context=context,
            runtime_ecl_version=(
                binding.runtime_version if binding is not None else None
            ),
            scale_status=scale_status,
            future_status=future_status,
            corridor_status=corridor_status,
            native_epoch_current=native_epoch_current,
            clock_status=clock.reason,
            clock_certified=clock.allowed,
            clock_generation=clock.generation,
        )

    def metrics(self) -> dict[str, object]:
        return {
            "runtime_identity_attempts": self.runtime_identity_attempts,
            "runtime_identity_acceptances": self.runtime_identity_acceptances,
            "future_submissions": self.future_submissions,
            "future_completions": self.future_completions,
            "future_rejections": self.future_rejections,
            "corridor_submissions": self.corridor_submissions,
            "corridor_completions": self.corridor_completions,
            "corridor_rejections": self.corridor_rejections,
            "authority_queries": self._authority.query_count,
            "authority_allowed_queries": self._authority.allowed_query_count,
            "authority_constrained_actions": (
                self._authority.constrained_action_count
            ),
            "clock_certified_observations": (
                self._clock_authority.certified_observations
            ),
            "clock_rejected_observations": (
                self._clock_authority.rejected_observations
            ),
            "clock_delta_mismatches": self._clock_authority.delta_mismatches,
            "clock_generation": self._clock_authority.generation,
            "policy_lead_frames": self._lead.frames,
            "policy_lead_samples": self._lead.sample_count,
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._future_work is not None:
            self._future_work.work.cancel()
        if self._corridor_work is not None:
            self._corridor_work.work.cancel()
        self._future_executor.shutdown(wait=True, cancel_futures=True)
        self._corridor_executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> "LinuxOnlineFutureGlobalService":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()


__all__ = (
    "LinuxOnlineFutureGlobalService",
    "LinuxOnlineServiceConfig",
    "LinuxOnlineServiceUpdate",
)
