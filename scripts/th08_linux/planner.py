"""Synchronous one-input-epoch adapter for the native Linux TH08 runtime.

The Linux bridge holds the game thread inside the DirectInput callback.  Pool
captures made here therefore describe one immutable post-update root: there is
no polling lag, pending command, or game-visible solver deadline to model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping
import time

from th08_live.bullet_decode import decode_bullets
from th08_live.controller import choose_action
from th08_live.enemy_sensor import (
    ENEMY_MANAGER_SCANNED_SLOT_COUNT,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_snapshot_contiguous,
)
from th08_live.hazard_decode import decode_items, decode_lasers
from th08_laser_runtime import Laser
from th08_live.models import Bullet, EnemyBody, Item
from th08_live.movement import BOMB, FOCUS, SHOT
from th08_live.sensor import ENEMY_MANAGER_FRAME_ADDRESS, Sensor
from th08_local_planner.models import Decision
from th08_runtime.sensing import capture_player_control_root
from th08_time_scale import Th08TimeScaleSchedule

from th08_linux.protocol import validate_hard_no_bomb_mask


NEUTRAL_GAMEPLAY_MASK = SHOT | FOCUS
UNCONTROLLABLE_PLAYER_PHASES = frozenset((1, 2))


@dataclass(frozen=True, slots=True)
class LinuxPlannerConfig:
    """Small generic local-planner contract for one blocked input epoch."""

    horizon: int = 10
    threat_horizon: int = 16
    beam_width: int = 24
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
    """Decoded physical state belonging to one immutable bridge root."""

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


@dataclass(frozen=True, slots=True)
class LinuxEpochPlan:
    """One complete immediate response to one input request."""

    input_mask: int
    action: str
    reason: str
    planning_ms: float
    decision: Decision | None


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

    def capture(self, state: Mapping[str, object]) -> LinuxPlannerSnapshot:
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
            self._reader,
            maximum_attempts=1,
        )
        if not player_root.stable:
            raise RuntimeError("player control root changed while game was blocked")
        raw = self._sensor.capture_raw_pools()
        enemies = capture_enemy_pool_snapshot_contiguous(
            self._reader,
            pool_base=ENEMY_SLOT_ZERO_BASE,
            pool_size=ENEMY_MANAGER_SCANNED_SLOT_COUNT,
            pool_buffer=self._enemy_buffer,
        )
        ending_frame = self._reader.u32(ENEMY_MANAGER_FRAME_ADDRESS)
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


class LinuxOneEpochPlanner:
    """Convert one decoded blocked root into one hard-no-Bomb input mask."""

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

    def choose(
        self,
        snapshot: LinuxPlannerSnapshot,
        *,
        previous_mask: int,
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
        schedule = Th08TimeScaleSchedule.constant(
            snapshot.time_scale_bits,
            horizon=max(self.config.horizon, self.config.threat_horizon),
            provenance="linux_lockstep_root_constant_horizon_assumption",
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
            time_scale_schedule=schedule,
        )
        planning_ms = (self._clock() - started) * 1000.0
        mask = validate_hard_no_bomb_mask(decision.mask)
        if mask & BOMB or decision.bomb:
            raise RuntimeError("local planner attempted to use Bomb")
        if not mask & SHOT:
            raise RuntimeError("local planner returned a non-shooting gameplay mask")
        return LinuxEpochPlan(
            input_mask=mask,
            action=decision.action,
            reason="local-current-hazard-plan",
            planning_ms=planning_ms,
            decision=decision,
        )


__all__ = (
    "LinuxEpochPlan",
    "LinuxHazardCapture",
    "LinuxOneEpochPlanner",
    "LinuxPlannerConfig",
    "LinuxPlannerSnapshot",
    "NEUTRAL_GAMEPLAY_MASK",
    "UNCONTROLLABLE_PLAYER_PHASES",
    "validate_lockstep_root_frames",
)
