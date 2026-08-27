"""Native Linux sensing and one-input-epoch local planning adapters.

The historical capture is synchronous. ``LinuxOnlineHazardCapture`` retains
that transaction only for compatibility tests; route authority decodes one
runtime-published immutable root while the game continues at 60 Hz.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping
import math
import time

from th08_live.bullet_decode import decode_bullets
import th08_live.controller as live_controller
from th08_live.enemy_sensor import (
    ENEMY_MANAGER_SCANNED_SLOT_COUNT,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_snapshot_contiguous,
    decode_enemy_bodies,
)
from th08_live.hazard_decode import decode_items, decode_lasers
from th08_laser_runtime import Laser
from th08_live.models import Bullet, EnemyBody, Item
from th08_live.movement import BOMB, FOCUS, SHOT
from th08_live.sensor import ENEMY_MANAGER_FRAME_ADDRESS, Sensor
from th08_local_planner.models import Decision
from th08_runtime.sensing import capture_player_control_root
from th08_runtime.game_state import (
    ADDR_FRSCREEN_IMPL_POINTER,
    ADDR_FRSCREEN_UPDATE_SERIAL,
    ADDR_SCRIPTED_UPDATE_FREEZE,
    FRSCREEN_MSG_STATE_OFFSET,
)
from th08_time_scale import Th08TimeScaleSchedule
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_linux.online_protocol import OnlineInputRequest
from th08_linux.immutable_snapshot import (
    RANGE_KIND_BULLET,
    RANGE_KIND_ENEMY,
    RANGE_KIND_ITEM,
    RANGE_KIND_LASER,
    PublishedSnapshotRoot,
)

from th08_linux.protocol import validate_hard_no_bomb_mask


choose_action = live_controller.choose_action


NEUTRAL_GAMEPLAY_MASK = SHOT | FOCUS
UNCONTROLLABLE_PLAYER_PHASES = frozenset((1, 2))


def require_native_online_planner_backends() -> None:
    """Fail closed unless both parity-gated deadline kernels are available."""

    if live_controller.native_backend._load_local_hazards_function() is None:
        raise RuntimeError("native online local hazard kernel is unavailable")
    if (
        live_controller.native_backend._load_local_beam_reduce_function()
        is None
    ):
        raise RuntimeError("native online local beam reducer is unavailable")
    live_controller._configure_local_hazard_backend("native")
    live_controller._configure_local_beam_reducer("native")


@dataclass(frozen=True, slots=True)
class LinuxPlannerConfig:
    """Small generic local-planner contract for one input epoch."""

    horizon: int = 8
    threat_horizon: int = 12
    beam_width: int = 8
    capture_items: bool = False

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError("planner horizon must be positive")
        if self.threat_horizon < self.horizon:
            raise ValueError("threat horizon cannot be shorter than search horizon")
        if self.beam_width <= 0:
            raise ValueError("planner beam width must be positive")


@dataclass(frozen=True, slots=True)
class LinuxPlannerSnapshot:
    """Decoded physical state belonging to one coherent bridge root."""

    frame: int
    player_phase: int
    player_x: float
    player_y: float
    time_scale_bits: int
    power: float
    bombs: float
    bullets: tuple[Bullet, ...]
    lasers: tuple[Laser, ...]
    enemy_bodies: tuple[EnemyBody, ...]
    items: tuple[Item, ...]
    pool_read_ms: float = 0.0
    decode_ms: float = 0.0
    source_input_epoch: int | None = None
    root_generation: int | None = None
    dialogue_active: bool | None = None
    scripted_update_freeze: bool | None = None


@dataclass(frozen=True, slots=True)
class LinuxFallbackLease:
    """Finite repeated-mask authority derived from one exact packed root."""

    source_input_epoch: int
    snapshot_generation: int
    input_mask: int
    continuation_frames: int
    min_clearance: float
    authority_version: str

    def __post_init__(self) -> None:
        if self.source_input_epoch <= 0 or self.snapshot_generation <= 0:
            raise ValueError("fallback lease requires a positive root version")
        validate_hard_no_bomb_mask(self.input_mask)
        if not 1 <= self.continuation_frames <= 8:
            raise ValueError("fallback lease horizon must be in [1, 8]")
        if not math.isfinite(self.min_clearance) or self.min_clearance <= 0.0:
            raise ValueError("fallback lease requires positive signed clearance")
        if not self.authority_version:
            raise ValueError("fallback lease requires an authority version")


@dataclass(frozen=True, slots=True)
class LinuxEpochPlan:
    """One complete immediate response to one input request."""

    input_mask: int
    action: str
    reason: str
    planning_ms: float
    decision: Decision | None
    fallback_lease: LinuxFallbackLease | None = None
    fallback_certificate_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class LinuxPlannerGuidance:
    """Fresh future/global constraints admitted to one online local decision."""

    target_x: float | None = None
    target_y: float | None = None
    target_deadline: int | None = None
    allowed_first_actions: tuple[str, ...] | None = None
    allowed_action_authority: str | None = None
    viability_repair_volumes: tuple[tuple[str, int], ...] = ()
    viability_recovery_distances: tuple[tuple[str, float], ...] = ()
    viability_safety_actions: tuple[str, ...] = ()
    viability_safety_state_value: float | None = None
    viability_survival_actions: tuple[str, ...] = ()
    viability_survival_frames: int | None = None
    viability_survival_bottleneck_margin: float | None = None
    viability_position_error: float = 0.0
    future_hazard_projection: OrdinaryFutureHazardProjection | None = None
    future_projection_offset: int = 0
    time_scale_schedule: Th08TimeScaleSchedule | None = None
    authority_version: str | None = None

    def __post_init__(self) -> None:
        if (
            self.allowed_action_authority is not None
            and self.allowed_first_actions is None
        ):
            raise ValueError("global action authority requires allowed actions")
        if self.future_projection_offset < 0:
            raise ValueError("future projection offset cannot be negative")
        if self.authority_version is not None and not self.authority_version:
            raise ValueError("authority version cannot be empty")

    @property
    def constrains_action(self) -> bool:
        return self.allowed_first_actions is not None

    @property
    def predicts_future_births(self) -> bool:
        return self.future_hazard_projection is not None


def validate_lockstep_root_frames(*frames: int) -> int:
    """Require every capture bracket to belong to the same blocked root."""

    if not frames:
        raise ValueError("at least one lockstep frame is required")
    if any(type(frame) is not int or frame < 0 for frame in frames):
        raise ValueError("lockstep frames must be nonnegative integers")
    unique = set(frames)
    if len(unique) != 1:
        raise RuntimeError(
            "Linux lockstep root changed during capture: "
            + ", ".join(str(frame) for frame in frames)
        )
    return frames[0]


class LinuxHazardCapture:
    """Own reusable full-pool buffers for synchronous native sensing."""

    def __init__(
        self,
        reader: object,
        *,
        capture_items: bool = False,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._reader = reader
        self._clock = clock
        self._sensor = Sensor(
            reader,
            capture_items=capture_items,
            clock=clock,
        )
        self._capture_items = capture_items
        self._enemy_buffer = reader.allocate_buffer(
            ENEMY_MANAGER_SCANNED_SLOT_COUNT * ENEMY_STRIDE
        )

    def capture(
        self,
        state: Mapping[str, object],
        *,
        reader: object | None = None,
    ) -> LinuxPlannerSnapshot:
        source = self._reader if reader is None else reader
        if not bool(state.get("gameplay_active")):
            raise ValueError("planner capture requires active gameplay")
        state_frame = int(state["enemy_manager_frame"])
        player = state["player"]
        if not isinstance(player, Mapping):
            raise TypeError("player state must be a mapping")
        resources = state.get("resources")
        if not isinstance(resources, Mapping):
            raise RuntimeError("active gameplay omitted resource state")

        player_root = capture_player_control_root(
            source,
            maximum_attempts=1,
        )
        if not player_root.stable:
            raise RuntimeError("player control fields changed inside one source root")
        if (
            player_root.x_after != float(player["x"])
            or player_root.y_after != float(player["y"])
            or player_root.scale_bits != int(state["time_scale_bits"])
        ):
            raise RuntimeError(
                "player/control state disagreed inside one source root"
            )
        packed_pool_records = getattr(source, "packed_pool_records", None)
        if callable(packed_pool_records):
            pool_started = self._clock()
            bullet_records = packed_pool_records(RANGE_KIND_BULLET)
            laser_records = packed_pool_records(RANGE_KIND_LASER)
            enemy_records = tuple(
                record
                for record in packed_pool_records(RANGE_KIND_ENEMY)
                if record.slot < ENEMY_MANAGER_SCANNED_SLOT_COUNT
            )
            item_records = (
                packed_pool_records(RANGE_KIND_ITEM)
                if self._capture_items
                else ()
            )
            bullet_blob = b"".join(record.data for record in bullet_records)
            laser_blob = b"".join(record.data for record in laser_records)
            enemy_blob = b"".join(record.data for record in enemy_records)
            item_blob = b"".join(record.data for record in item_records)
            pool_read_ms = (self._clock() - pool_started) * 1000.0
            ending_frame = source.u32(ENEMY_MANAGER_FRAME_ADDRESS)
            frame = validate_lockstep_root_frames(
                state_frame,
                player_root.frame_before,
                player_root.frame_after,
                ending_frame,
            )
            decode_started = self._clock()
            bullets = decode_bullets(
                bullet_blob,
                retain_transform_runtime=True,
                record_slots=tuple(record.slot for record in bullet_records),
            )
            lasers = decode_lasers(
                laser_blob,
                record_slots=tuple(record.slot for record in laser_records),
            )
            enemy_bodies = decode_enemy_bodies(
                enemy_blob,
                pool_base=ENEMY_SLOT_ZERO_BASE,
                pool_size=ENEMY_MANAGER_SCANNED_SLOT_COUNT,
                record_slots=tuple(record.slot for record in enemy_records),
            )
            items = (
                decode_items(
                    item_blob,
                    record_slots=tuple(record.slot for record in item_records),
                )
                if self._capture_items
                else ()
            )
            decode_ms = (self._clock() - decode_started) * 1000.0
            return LinuxPlannerSnapshot(
                frame=frame,
                player_phase=int(player["phase"]),
                player_x=player_root.x_after,
                player_y=player_root.y_after,
                time_scale_bits=player_root.scale_bits,
                power=float(resources["power"]),
                bombs=float(resources["bombs"]),
                bullets=bullets,
                lasers=lasers,
                enemy_bodies=enemy_bodies,
                items=items,
                pool_read_ms=pool_read_ms,
                decode_ms=decode_ms,
            )
        raw = self._sensor.capture_raw_pools(reader=source)
        enemies = capture_enemy_pool_snapshot_contiguous(
            source,
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=ENEMY_MANAGER_SCANNED_SLOT_COUNT,
            pool_buffer=self._enemy_buffer,
        )
        ending_frame = source.u32(ENEMY_MANAGER_FRAME_ADDRESS)
        frame = validate_lockstep_root_frames(
            state_frame,
            player_root.frame_before,
            player_root.frame_after,
            raw.bullet_frame_before,
            raw.bullet_frame_after,
            enemies.frame_before,
            enemies.frame_after,
            ending_frame,
        )

        decode_started = self._clock()
        bullets = decode_bullets(
            raw.bullet_blob,
            retain_transform_runtime=True,
        )
        lasers = decode_lasers(raw.laser_blob)
        items = decode_items(raw.item_blob) if self._capture_items else ()
        decode_ms = (self._clock() - decode_started) * 1000.0
        return LinuxPlannerSnapshot(
            frame=frame,
            player_phase=int(player["phase"]),
            player_x=player_root.x_after,
            player_y=player_root.y_after,
            time_scale_bits=player_root.scale_bits,
            power=float(resources["power"]),
            bombs=float(resources["bombs"]),
            bullets=bullets,
            lasers=lasers,
            enemy_bodies=enemies.bodies,
            items=items,
            pool_read_ms=(
                raw.bullet_pool_read_ms
                + raw.laser_pool_read_ms
                + raw.item_pool_read_ms
                + enemies.read_ms
            ),
            decode_ms=decode_ms,
        )


class LinuxOnlineHazardCapture(LinuxHazardCapture):
    """Decode a published immutable root; retain the live bracket as legacy."""

    def __init__(
        self,
        reader: object,
        *,
        input_epoch_address: int,
        capture_items: bool = False,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if input_epoch_address <= 0:
            raise ValueError("online input epoch address must be positive")
        super().__init__(
            reader,
            capture_items=capture_items,
            clock=clock,
        )
        self._input_epoch_address = input_epoch_address

    def capture_transaction(
        self,
        request: OnlineInputRequest,
        *,
        observe: Callable[[], Mapping[str, object]],
    ) -> tuple[Mapping[str, object], LinuxPlannerSnapshot]:
        expected = request.source_epoch & 0xFFFFFFFF
        epoch_before = self._reader.u32(self._input_epoch_address)
        if epoch_before != expected:
            raise RuntimeError(
                "online source epoch expired before observation: "
                f"published {expected}, native {epoch_before}"
            )
        state = observe()
        snapshot = self.capture(state)
        impl_pointer = self._reader.u32(ADDR_FRSCREEN_IMPL_POINTER)
        message_state = (
            self._reader.i32(impl_pointer + FRSCREEN_MSG_STATE_OFFSET)
            if impl_pointer
            else None
        )
        scripted_update_freeze = bool(
            self._reader.u8(ADDR_SCRIPTED_UPDATE_FREEZE)
        )
        epoch_after = self._reader.u32(self._input_epoch_address)
        if epoch_after != expected:
            raise RuntimeError(
                "online observation crossed its input epoch: "
                f"published {expected}, native {epoch_before}->{epoch_after}"
            )
        return state, replace(
            snapshot,
            source_input_epoch=request.source_epoch,
            dialogue_active=bool(
                message_state is not None
                and (message_state >= 0 or message_state == -2)
            ),
            scripted_update_freeze=scripted_update_freeze,
        )

    def capture_published_root(
        self,
        request: OnlineInputRequest,
        root: PublishedSnapshotRoot,
        *,
        observe: Callable[[object], Mapping[str, object]],
    ) -> tuple[Mapping[str, object], LinuxPlannerSnapshot]:
        """Decode one runtime publication without consulting live state."""

        if root.source_epoch != request.source_epoch:
            raise RuntimeError("published root belongs to a different input epoch")
        source = root.reader
        state = observe(source)
        snapshot = self.capture(state, reader=source)
        if snapshot.frame != root.manager_frame:
            raise RuntimeError("published root manager-frame certificate mismatch")
        if source.u32(ADDR_FRSCREEN_UPDATE_SERIAL) != root.update_serial:
            raise RuntimeError("published root update-serial certificate mismatch")
        impl_pointer = source.u32(ADDR_FRSCREEN_IMPL_POINTER)
        message_state = (
            source.i32(impl_pointer + FRSCREEN_MSG_STATE_OFFSET)
            if impl_pointer
            else None
        )
        return state, replace(
            snapshot,
            source_input_epoch=request.source_epoch,
            root_generation=root.generation,
            dialogue_active=bool(
                message_state is not None
                and (message_state >= 0 or message_state == -2)
            ),
            scripted_update_freeze=bool(
                source.u8(ADDR_SCRIPTED_UPDATE_FREEZE)
            ),
        )


class LinuxOneEpochPlanner:
    """Convert one coherent root into one exact-epoch no-Bomb input mask."""

    def __init__(
        self,
        *,
        config: LinuxPlannerConfig = LinuxPlannerConfig(),
        chooser: Callable[..., Decision] = choose_action,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.config = config
        self._chooser = chooser
        self._clock = clock

    @staticmethod
    def _certify_one_missed_epoch(
        snapshot: LinuxPlannerSnapshot,
        *,
        previous_mask: int,
        decision: Decision,
        guidance: LinuxPlannerGuidance,
    ) -> LinuxFallbackLease | None:
        """Certify exactly one continuation frame or withhold the lease.

        The ordinary one-epoch action stays unchanged.  A lease is admitted
        only when a versioned global viable-action set, complete future-birth
        envelope, exact scale schedule, and controllable runtime gates all
        describe the same immutable root.  The selected complete mask is then
        checked for two physical transitions from that root: its requested
        target plus one possible deadline fallback.
        """

        if (
            snapshot.source_input_epoch is None
            or snapshot.source_input_epoch <= 0
            or snapshot.root_generation is None
            or snapshot.root_generation <= 0
            or snapshot.dialogue_active is not False
            or snapshot.scripted_update_freeze is not False
            or guidance.allowed_first_actions is None
            or guidance.allowed_action_authority is None
            or decision.action not in guidance.allowed_first_actions
            or guidance.future_hazard_projection is None
            or guidance.time_scale_schedule is None
            or guidance.authority_version is None
        ):
            return None
        selected = next(
            (
                action
                for action in live_controller._PLANNER_ACTIONS
                if action.name == decision.action
            ),
            None,
        )
        if selected is None:
            raise RuntimeError("online decision has no local planner action")
        continuation_horizon = 2
        certificates = live_controller._robust_action_certificates(
            player_x=snapshot.player_x,
            player_y=snapshot.player_y,
            previous_mask=previous_mask,
            actions=(selected,),
            delay_frames=(0,),
            action_hold_frames=continuation_horizon,
            bullets=snapshot.bullets,
            lasers=snapshot.lasers,
            enemy_bodies=snapshot.enemy_bodies,
            snapshot_lag=0,
            bullet_snapshot_age_support=(0,),
            player_scale_bits=(
                guidance.time_scale_schedule.require_player_horizon(
                    continuation_horizon
                )
            ),
            laser_scale_bits=(
                guidance.time_scale_schedule.require_laser_horizon(
                    continuation_horizon
                )
            ),
            future_hazard_projection=guidance.future_hazard_projection,
            future_projection_offset=guidance.future_projection_offset,
        )
        certificate = certificates.get(decision.action)
        if (
            certificate is None
            or certificate.worst_collisions != 0
            or certificate.min_clearance <= 0.0
        ):
            return None
        return LinuxFallbackLease(
            source_input_epoch=snapshot.source_input_epoch,
            snapshot_generation=snapshot.root_generation,
            input_mask=decision.mask,
            continuation_frames=1,
            min_clearance=certificate.min_clearance,
            authority_version=guidance.authority_version,
        )

    def choose(
        self,
        snapshot: LinuxPlannerSnapshot,
        *,
        previous_mask: int,
        guidance: LinuxPlannerGuidance = LinuxPlannerGuidance(),
        certify_fallback_lease: bool = False,
    ) -> LinuxEpochPlan:
        validate_hard_no_bomb_mask(previous_mask)
        if snapshot.player_phase in UNCONTROLLABLE_PLAYER_PHASES:
            return LinuxEpochPlan(
                input_mask=NEUTRAL_GAMEPLAY_MASK,
                action="stay",
                reason="player-uncontrollable",
                planning_ms=0.0,
                decision=None,
            )

        # The root proves the next player scale only.  This bounded constant
        # continuation is an explicit local-planner assumption, recomputed on
        # every epoch; it is not promoted as future scale authority.
        schedule = guidance.time_scale_schedule
        if schedule is None:
            schedule = Th08TimeScaleSchedule.constant(
                snapshot.time_scale_bits,
                horizon=max(self.config.horizon, self.config.threat_horizon),
                provenance="linux_online_root_constant_horizon_assumption",
                source_frame=snapshot.frame,
            )
        started = self._clock()
        decision = self._chooser(
            player_x=snapshot.player_x,
            player_y=snapshot.player_y,
            bullets=snapshot.bullets,
            lasers=snapshot.lasers,
            previous_direction=previous_mask,
            can_bomb=False,
            enemy_bodies=snapshot.enemy_bodies,
            items=snapshot.items,
            power=snapshot.power,
            bombs=snapshot.bombs,
            previous_focus=bool(previous_mask & FOCUS),
            snapshot_lag=0,
            bullet_snapshot_age_support=(0,),
            control_delay_frames=0,
            control_delay_candidates=(0,),
            action_hold_frames=1,
            horizon=self.config.horizon,
            threat_horizon=self.config.threat_horizon,
            beam_width=self.config.beam_width,
            target_x=guidance.target_x,
            target_y=guidance.target_y,
            target_deadline=guidance.target_deadline,
            allowed_first_actions=guidance.allowed_first_actions,
            allowed_action_authority=guidance.allowed_action_authority,
            viability_repair_volumes=guidance.viability_repair_volumes,
            viability_recovery_distances=(
                guidance.viability_recovery_distances
            ),
            viability_safety_actions=guidance.viability_safety_actions,
            viability_safety_state_value=(
                guidance.viability_safety_state_value
            ),
            viability_survival_actions=guidance.viability_survival_actions,
            viability_survival_frames=guidance.viability_survival_frames,
            viability_survival_bottleneck_margin=(
                guidance.viability_survival_bottleneck_margin
            ),
            viability_position_error=guidance.viability_position_error,
            time_scale_schedule=schedule,
            future_hazard_projection=guidance.future_hazard_projection,
            future_projection_offset=guidance.future_projection_offset,
        )
        mask = validate_hard_no_bomb_mask(decision.mask)
        if mask & BOMB or decision.bomb:
            raise RuntimeError("local planner attempted to use Bomb")
        if not mask & SHOT:
            raise RuntimeError("local planner returned a non-shooting gameplay mask")
        fallback_lease = None
        fallback_certificate_ms = 0.0
        if certify_fallback_lease:
            # This opt-in remains outside the live Easy route until the
            # selected repeated action also has a same-version second-layer
            # global viability predecessor.  Local two-frame clearance alone
            # is insufficient action authority.
            certificate_started = self._clock()
            fallback_lease = self._certify_one_missed_epoch(
                snapshot,
                previous_mask=previous_mask,
                decision=decision,
                guidance=guidance,
            )
            fallback_certificate_ms = (
                self._clock() - certificate_started
            ) * 1000.0
        planning_ms = (self._clock() - started) * 1000.0
        return LinuxEpochPlan(
            input_mask=mask,
            action=decision.action,
            reason=(
                "local+global+future-online-plan"
                if guidance.constrains_action
                and guidance.predicts_future_births
                else "local+global-online-plan"
                if guidance.constrains_action
                else "local+future-online-plan"
                if guidance.predicts_future_births
                else "local-current-hazard-plan"
            ),
            planning_ms=planning_ms,
            decision=decision,
            fallback_lease=fallback_lease,
            fallback_certificate_ms=fallback_certificate_ms,
        )


__all__ = (
    "LinuxEpochPlan",
    "LinuxFallbackLease",
    "LinuxHazardCapture",
    "LinuxOnlineHazardCapture",
    "LinuxOneEpochPlanner",
    "LinuxPlannerConfig",
    "LinuxPlannerGuidance",
    "LinuxPlannerSnapshot",
    "NEUTRAL_GAMEPLAY_MASK",
    "UNCONTROLLABLE_PLAYER_PHASES",
    "require_native_online_planner_backends",
    "validate_lockstep_root_frames",
)
