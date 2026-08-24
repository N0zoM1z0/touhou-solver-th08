"""Replayable TH08 semantic-case data and canonical serialization."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import th08_live_dodge_agent as live
from th08_laser_model import LaserPhase, LaserState
from th08_laser_runtime import Laser
from touhou_control.trajectory import CollisionStateChange, VelocityChange


SCHEMA = "th08-semantic-case-v2-stateful-collision"
_SUPPORTED_SCHEMAS = frozenset(("th08-semantic-case-v1", SCHEMA))
FAMILIES = (
    "aimed_fan",
    "radial_ring",
    "spiral",
    "wave_lanes",
    "wall",
    "crossfire",
    "random_cloud",
    "boundary_tangent",
    "laser_storm",
    "transform_adversarial",
    "off_tube",
    "mixed_phase",
)
DIFFICULTIES = ("normal", "hard", "lunatic", "beyond_pool")


@dataclass(frozen=True)
class SemanticCase:
    seed: int
    index: int
    profile: str
    family: str
    difficulty: str
    player_x: float
    player_y: float
    previous_direction: int
    previous_focused: bool
    control_delay_frames: int
    action_hold_frames: int
    horizon: int
    beam_width: int
    allowed_first_actions: tuple[str, ...]
    positions_x: tuple[float, ...]
    positions_y: tuple[float, ...]
    bullets: tuple[live.Bullet, ...]
    lasers: tuple[Laser, ...]
    enemy_bodies: tuple[live.EnemyBody, ...]

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError(f"unknown semantic family {self.family!r}")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(
                f"unknown semantic difficulty {self.difficulty!r}"
            )
        if (
            self.horizon <= 0
            or self.action_hold_frames <= 0
            or self.beam_width <= 0
            or len(self.positions_x) != len(self.positions_y)
            or not self.positions_x
            or not self.allowed_first_actions
        ):
            raise ValueError("invalid semantic case dimensions")

    @property
    def identity(self) -> str:
        return (
            f"{self.profile}:{self.seed:016x}:{self.index}:"
            f"{self.family}:{self.difficulty}"
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "seed": self.seed,
            "index": self.index,
            "profile": self.profile,
            "family": self.family,
            "difficulty": self.difficulty,
            "player": [
                self.player_x,
                self.player_y,
                self.previous_direction,
                int(self.previous_focused),
            ],
            "planner": [
                self.control_delay_frames,
                self.action_hold_frames,
                self.horizon,
                self.beam_width,
                list(self.allowed_first_actions),
            ],
            "positions": [
                list(self.positions_x),
                list(self.positions_y),
            ],
            "bullets": [_bullet_payload(bullet) for bullet in self.bullets],
            "lasers": [_laser_payload(laser) for laser in self.lasers],
            "enemy_bodies": [
                _body_payload(body) for body in self.enemy_bodies
            ],
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        payload["sha256"] = hashlib.sha256(canonical).hexdigest()
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> SemanticCase:
        if payload.get("schema") not in _SUPPORTED_SCHEMAS:
            raise ValueError("unsupported TH08 semantic case schema")
        unsigned = dict(payload)
        digest = unsigned.pop("sha256", None)
        if digest is not None:
            canonical = json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            if hashlib.sha256(canonical).hexdigest() != digest:
                raise ValueError("semantic case digest mismatch")
        player = unsigned["player"]
        planner = unsigned["planner"]
        positions = unsigned["positions"]
        assert isinstance(player, list)
        assert isinstance(planner, list)
        assert isinstance(positions, list)
        return cls(
            seed=int(unsigned["seed"]),
            index=int(unsigned["index"]),
            profile=str(unsigned["profile"]),
            family=str(unsigned["family"]),
            difficulty=str(unsigned["difficulty"]),
            player_x=float(player[0]),
            player_y=float(player[1]),
            previous_direction=int(player[2]),
            previous_focused=bool(player[3]),
            control_delay_frames=int(planner[0]),
            action_hold_frames=int(planner[1]),
            horizon=int(planner[2]),
            beam_width=int(planner[3]),
            allowed_first_actions=tuple(str(v) for v in planner[4]),
            positions_x=tuple(float(v) for v in positions[0]),
            positions_y=tuple(float(v) for v in positions[1]),
            bullets=tuple(
                _bullet_from_payload(values)
                for values in unsigned["bullets"]
            ),
            lasers=tuple(
                _laser_from_payload(values)
                for values in unsigned["lasers"]
            ),
            enemy_bodies=tuple(
                _body_from_payload(values)
                for values in unsigned["enemy_bodies"]
            ),
        )


def _bullet_payload(bullet: live.Bullet) -> list[object]:
    return [
        bullet.x,
        bullet.y,
        bullet.vx,
        bullet.vy,
        bullet.half_width,
        bullet.half_height,
        bullet.transform_flags,
        bullet.slot,
        bullet.speed,
        bullet.angle,
        bullet.callback_phase_state,
        bullet.callback_aux_state,
        [
            [change.frame, change.velocity_x, change.velocity_y]
            for change in bullet.velocity_changes
        ],
        bullet.trajectory_uncertainty_x,
        bullet.trajectory_uncertainty_y,
        bullet.original_transform_flags,
        [
            [change.frame, int(change.collision_enabled)]
            for change in bullet.collision_state_changes
        ],
    ]


def _bullet_from_payload(values: list[object]) -> live.Bullet:
    return live.Bullet(
        x=float(values[0]),
        y=float(values[1]),
        vx=float(values[2]),
        vy=float(values[3]),
        half_width=float(values[4]),
        half_height=float(values[5]),
        transform_flags=int(values[6]),
        slot=int(values[7]),
        speed=None if values[8] is None else float(values[8]),
        angle=None if values[9] is None else float(values[9]),
        callback_phase_state=int(values[10]),
        callback_aux_state=int(values[11]),
        velocity_changes=tuple(
            VelocityChange(int(change[0]), float(change[1]), float(change[2]))
            for change in values[12]
        ),
        trajectory_uncertainty_x=float(values[13]),
        trajectory_uncertainty_y=float(values[14]),
        original_transform_flags=int(values[15]),
        collision_state_changes=tuple(
            CollisionStateChange(int(change[0]), bool(change[1]))
            for change in (values[16] if len(values) > 16 else ())
        ),
    )


def _laser_payload(laser: Laser) -> list[object]:
    state = laser.state
    return [
        laser.origin_x,
        laser.origin_y,
        laser.angle,
        laser.tail,
        laser.head,
        laser.half_width,
        laser.slot,
        laser.collision_flag,
        laser.uncertainty,
        laser.uncertainty_per_frame,
        (
            None
            if state is None
            else [
                state.origin_x,
                state.origin_y,
                state.angle,
                state.tail_distance,
                state.head_distance,
                state.maximum_length,
                state.width,
                state.speed,
                state.warmup_frames,
                state.active_frames,
                state.fade_frames,
                state.collision_enable_frame,
                state.collision_disable_frame,
                state.flags,
                state.current_width,
                int(state.phase),
                state.timer,
                state.timer_fraction,
                int(state.active),
            ]
        ),
    ]


def _laser_from_payload(values: list[object]) -> Laser:
    state_values = values[10]
    state = None
    if state_values is not None:
        state = LaserState(
            origin_x=float(state_values[0]),
            origin_y=float(state_values[1]),
            angle=float(state_values[2]),
            tail_distance=float(state_values[3]),
            head_distance=float(state_values[4]),
            maximum_length=float(state_values[5]),
            width=float(state_values[6]),
            speed=float(state_values[7]),
            warmup_frames=int(state_values[8]),
            active_frames=int(state_values[9]),
            fade_frames=int(state_values[10]),
            collision_enable_frame=int(state_values[11]),
            collision_disable_frame=int(state_values[12]),
            flags=int(state_values[13]),
            current_width=float(state_values[14]),
            phase=LaserPhase(int(state_values[15])),
            timer=int(state_values[16]),
            timer_fraction=float(state_values[17]),
            active=bool(state_values[18]),
        )
    return Laser(
        origin_x=float(values[0]),
        origin_y=float(values[1]),
        angle=float(values[2]),
        tail=float(values[3]),
        head=float(values[4]),
        half_width=float(values[5]),
        slot=int(values[6]),
        collision_flag=int(values[7]),
        uncertainty=float(values[8]),
        uncertainty_per_frame=float(values[9]),
        state=state,
    )


def _body_payload(body: live.EnemyBody) -> list[object]:
    return [
        body.pointer,
        body.x,
        body.y,
        body.vx,
        body.vy,
        body.half_width,
        body.half_height,
        body.flags,
        body.uncertainty,
    ]


def _body_from_payload(values: list[object]) -> live.EnemyBody:
    return live.EnemyBody(
        pointer=int(values[0]),
        x=float(values[1]),
        y=float(values[2]),
        vx=float(values[3]),
        vy=float(values[4]),
        half_width=float(values[5]),
        half_height=float(values[6]),
        flags=int(values[7]),
        uncertainty=float(values[8]),
    )
