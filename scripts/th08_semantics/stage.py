"""Replayable source-valid TH08 bullet/laser stage transition runtime.

The stage IR begins at resolved ECL producer events.  It does not pretend to
execute arbitrary ECL bytecode: every emitter is a finite sequence of native
bullet descriptors, every callback is an explicit recovered callback-12/14
invocation, and every transform is one of the handlers modeled below.  This
gives offline tests long causal histories without inventing inconsistent
snapshot fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Callable

import th08_live_dodge_agent as live
from th08_bullet_transform_model import (
    AngularVelocityRuntime,
    BulletTransformProgramRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformRecord,
    TransformTimerRuntime,
    VectorAccelerationRuntime,
    pack_transform_program,
)
from th08_bullet_template_contract import (
    BulletSpawnLifecycle,
    bullet_spawn_lifecycle,
    bullet_template_profile,
)
from th08_laser_model import (
    LaserCollisionCheck,
    LaserState,
    spawn_laser_state,
    step_laser,
)
from th08_laser_runtime import Laser
from th08_rng import Th08Rng
from th08_semantics.source_primitives import (
    Callback12State,
    SourcePattern,
    SourcePatternSample,
    apply_callback12,
    apply_callback14,
    f32,
    normalize_angle,
    pattern_sample,
)


STAGE_SCHEMA = "th08-source-stateful-stage-v1"
RESOLVED_AIM_STAGE_SCHEMA = "th08-source-stateful-stage-v2"
LIFECYCLE_STAGE_SCHEMA = "th08-source-stateful-stage-v3-spawn-lifecycle"
CULL_GEOMETRY_STAGE_SCHEMA = (
    "th08-source-stateful-stage-v4-template-cull-geometry"
)
CALLBACK14_STAGE_SCHEMA = "th08-source-stateful-stage-v5-callback14"
SOURCE_AUTHORITY_COMMIT = "57ee34f"
BULLET_POOL_SIZE = 0x600
LASER_POOL_SIZE = 0x100
PLAYFIELD_WIDTH = 384.0
PLAYFIELD_HEIGHT = 448.0

TRANSFORM_DECELERATE = 0x000001
TRANSFORM_VECTOR_ACCELERATION = 0x000010
TRANSFORM_ANGULAR_VELOCITY = 0x000020
TRANSFORM_STOP_TURN = 0x000040
TRANSFORM_STOP_REAIM = 0x000080
TRANSFORM_STOP_SNAP = 0x000100
TRANSFORM_REFLECT_ALL = 0x000400
TRANSFORM_REFLECT_SIDES_TOP = 0x000800
_SUPPORTED_TRANSFORMS = frozenset(
    (
        TRANSFORM_DECELERATE,
        TRANSFORM_VECTOR_ACCELERATION,
        TRANSFORM_ANGULAR_VELOCITY,
        TRANSFORM_STOP_TURN,
        TRANSFORM_STOP_REAIM,
        TRANSFORM_STOP_SNAP,
        TRANSFORM_REFLECT_ALL,
        TRANSFORM_REFLECT_SIDES_TOP,
    )
)


def _add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def _sub(left: float, right: float) -> float:
    return f32(f32(left) - f32(right))


def _mul(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def _div(left: float, right: float) -> float:
    return f32(f32(left) / f32(right))


def _polar(angle: float, magnitude: float) -> tuple[float, float]:
    return (
        f32(f32(math.cos(f32(angle))) * f32(magnitude)),
        f32(f32(math.sin(f32(angle))) * f32(magnitude)),
    )


def _retained_timer(current: int) -> TransformTimerRuntime:
    """Reconstruct the unit-scale ZunTimer state used by this offline stage."""

    return TransformTimerRuntime(
        previous=current - 1 if current > 0 else -999,
        subframe=0.0,
        current=current,
    )


@dataclass(frozen=True)
class TransformSpec:
    """One generated record accepted by ``Bullet::FUN_0042ffc0``."""

    kind: int
    duration: int
    repeat_limit: int = 1
    float_0: float = 0.0
    float_1: float = -1000.0
    allow_while_active: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _SUPPORTED_TRANSFORMS:
            raise ValueError(f"unsupported stage transform {self.kind:#x}")
        if self.duration < 0 or self.repeat_limit < 0:
            raise ValueError("transform duration/repeat limit cannot be negative")
        if not math.isfinite(self.float_0) or not math.isfinite(self.float_1):
            raise ValueError("transform operands must be finite")

    def to_payload(self) -> list[object]:
        return [
            self.kind,
            self.duration,
            self.repeat_limit,
            self.float_0,
            self.float_1,
            int(self.allow_while_active),
        ]

    @classmethod
    def from_payload(cls, values: list[object]) -> "TransformSpec":
        return cls(
            kind=int(values[0]),
            duration=int(values[1]),
            repeat_limit=int(values[2]),
            float_0=float(values[3]),
            float_1=float(values[4]),
            allow_while_active=bool(values[5]),
        )


@dataclass(frozen=True)
class BulletEmitter:
    """A finite resolved direct-fire descriptor stream."""

    emitter_id: str
    start_frame: int
    end_frame: int
    interval: int
    origin_x: float
    origin_y: float
    origin_velocity_x: float
    origin_velocity_y: float
    origin_wave_x: float
    origin_wave_y: float
    origin_wave_step: float
    mode: int
    count1: int
    count2: int
    speed1: float
    speed2: float
    angle: float
    angle_step: float
    angle_per_emission: float
    tag_flags: int
    half_width: float
    half_height: float
    cull_half_width: float | None = None
    cull_half_height: float | None = None
    transforms: tuple[TransformSpec, ...] = ()
    resolved_aim_override: float | None = None
    bullet_type: int | None = None
    spawn_flags: int = 0

    def __post_init__(self) -> None:
        if not self.emitter_id:
            raise ValueError("emitter id must not be empty")
        if (
            self.start_frame < 0
            or self.end_frame < self.start_frame
            or self.interval <= 0
            or not 0 <= self.mode <= 8
            or self.count1 <= 0
            or self.count2 <= 0
        ):
            raise ValueError("invalid bullet emitter schedule")
        if self.half_width < 0.0 or self.half_height < 0.0:
            raise ValueError("bullet half extents cannot be negative")
        if (self.cull_half_width is None) != (self.cull_half_height is None):
            raise ValueError("bullet cull half extents must be supplied together")
        if self.cull_half_width is not None and (
            not math.isfinite(self.cull_half_width)
            or not math.isfinite(self.cull_half_height)
            or self.cull_half_width < 0.0
            or self.cull_half_height < 0.0
        ):
            raise ValueError(
                "bullet cull half extents must be finite and nonnegative"
            )
        if self.resolved_aim_override is not None and not math.isfinite(
            self.resolved_aim_override
        ):
            raise ValueError("resolved emitter aim override must be finite")
        if type(self.spawn_flags) is not int or self.spawn_flags < 0:
            raise ValueError("spawn lifecycle flags must be a nonnegative integer")
        if self.spawn_flags & ~0x0E:
            raise ValueError("spawn lifecycle emitter has unsupported flags")
        profile = None
        if self.bullet_type is not None:
            if type(self.bullet_type) is not int:
                raise ValueError("bullet template type must be an integer")
            try:
                profile = bullet_template_profile(self.bullet_type)
            except ValueError as error:
                raise ValueError("bullet template type is invalid") from error
            if (
                f32(self.half_width) != f32(profile.half_width)
                or f32(self.half_height) != f32(profile.half_height)
            ):
                raise ValueError(
                    "emitter collision geometry disagrees with template"
                )
            if self.cull_half_width is not None and (
                f32(self.cull_half_width) != f32(profile.cull_half_width)
                or f32(self.cull_half_height) != f32(
                    profile.cull_half_height
                )
            ):
                raise ValueError("emitter cull geometry disagrees with template")
        if self.spawn_flags:
            if profile is None:
                raise ValueError("spawn lifecycle emitter requires bullet type")
            lifecycle = bullet_spawn_lifecycle(
                self.bullet_type,
                self.spawn_flags,
            )
            if lifecycle is None:
                raise ValueError("spawn lifecycle flags select no native state")
            if self.tag_flags or self.transforms:
                raise ValueError(
                    "spawn lifecycle composition with callbacks/transforms "
                    "is not yet source-closed"
                )
        if len({transform.kind for transform in self.transforms}) != len(
            self.transforms
        ):
            raise ValueError("stage transform queue kinds must be unique")
        if not all(
            math.isfinite(value)
            for value in (
                self.origin_x,
                self.origin_y,
                self.origin_velocity_x,
                self.origin_velocity_y,
                self.origin_wave_x,
                self.origin_wave_y,
                self.origin_wave_step,
                self.speed1,
                self.speed2,
                self.angle,
                self.angle_step,
                self.angle_per_emission,
            )
        ):
            raise ValueError("bullet emitter operands must be finite")

    def due(self, frame: int) -> bool:
        return (
            self.start_frame <= frame <= self.end_frame
            and (frame - self.start_frame) % self.interval == 0
        )

    def resolved_descriptor(
        self,
        frame: int,
        *,
        player_x: float,
        player_y: float,
    ) -> tuple[float, float, SourcePattern]:
        if not self.due(frame):
            raise ValueError("emitter is not due on requested frame")
        emission = (frame - self.start_frame) // self.interval
        wave_angle = _mul(emission, self.origin_wave_step)
        x = _add(
            _add(self.origin_x, _mul(emission, self.origin_velocity_x)),
            _mul(self.origin_wave_x, math.sin(wave_angle)),
        )
        y = _add(
            _add(self.origin_y, _mul(emission, self.origin_velocity_y)),
            _mul(self.origin_wave_y, math.cos(wave_angle)),
        )
        aim = (
            f32(self.resolved_aim_override)
            if self.resolved_aim_override is not None
            else f32(math.atan2(f32(player_y - y), f32(player_x - x)))
        )
        return (
            x,
            y,
            SourcePattern(
                mode=self.mode,
                count1=self.count1,
                count2=self.count2,
                speed1=f32(self.speed1),
                speed2=f32(self.speed2),
                angle=_add(
                    self.angle,
                    _mul(emission, self.angle_per_emission),
                ),
                angle_step=f32(self.angle_step),
                angle_to_player=aim,
                time_scale=1.0,
            ),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.emitter_id,
            "schedule": [self.start_frame, self.end_frame, self.interval],
            "origin": [
                self.origin_x,
                self.origin_y,
                self.origin_velocity_x,
                self.origin_velocity_y,
                self.origin_wave_x,
                self.origin_wave_y,
                self.origin_wave_step,
            ],
            "pattern": [
                self.mode,
                self.count1,
                self.count2,
                self.speed1,
                self.speed2,
                self.angle,
                self.angle_step,
                self.angle_per_emission,
            ],
            "tags": self.tag_flags,
            "geometry": [self.half_width, self.half_height],
            "transforms": [value.to_payload() for value in self.transforms],
        }
        if self.cull_half_width is not None:
            payload["cull_geometry"] = [
                self.cull_half_width,
                self.cull_half_height,
            ]
        # Preserve existing generated-stage identities.  This field is only
        # present for an already-resolved retained producer event; ordinary
        # synthetic emitters continue to derive aim from the supplied player.
        if self.resolved_aim_override is not None:
            payload["resolved_aim_override"] = self.resolved_aim_override
        if self.spawn_flags:
            assert self.bullet_type is not None
            payload["spawn_lifecycle"] = [
                self.bullet_type,
                self.spawn_flags,
            ]
        elif self.bullet_type is not None:
            payload["bullet_type"] = self.bullet_type
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "BulletEmitter":
        schedule = payload["schedule"]
        origin = payload["origin"]
        pattern = payload["pattern"]
        geometry = payload["geometry"]
        cull_geometry = payload.get("cull_geometry")
        spawn_lifecycle = payload.get("spawn_lifecycle")
        assert isinstance(schedule, list)
        assert isinstance(origin, list)
        assert isinstance(pattern, list)
        assert isinstance(geometry, list)
        if cull_geometry is not None and (
            type(cull_geometry) is not list or len(cull_geometry) != 2
        ):
            raise ValueError("cull_geometry must contain two values")
        if spawn_lifecycle is not None and (
            type(spawn_lifecycle) is not list
            or len(spawn_lifecycle) != 2
            or type(spawn_lifecycle[0]) is not int
            or type(spawn_lifecycle[1]) is not int
        ):
            raise ValueError(
                "spawn_lifecycle must be [bullet_type, spawn_flags] integers"
            )
        return cls(
            emitter_id=str(payload["id"]),
            start_frame=int(schedule[0]),
            end_frame=int(schedule[1]),
            interval=int(schedule[2]),
            origin_x=float(origin[0]),
            origin_y=float(origin[1]),
            origin_velocity_x=float(origin[2]),
            origin_velocity_y=float(origin[3]),
            origin_wave_x=float(origin[4]),
            origin_wave_y=float(origin[5]),
            origin_wave_step=float(origin[6]),
            mode=int(pattern[0]),
            count1=int(pattern[1]),
            count2=int(pattern[2]),
            speed1=float(pattern[3]),
            speed2=float(pattern[4]),
            angle=float(pattern[5]),
            angle_step=float(pattern[6]),
            angle_per_emission=float(pattern[7]),
            tag_flags=int(payload["tags"]),
            half_width=float(geometry[0]),
            half_height=float(geometry[1]),
            cull_half_width=(
                float(cull_geometry[0])
                if cull_geometry is not None
                else None
            ),
            cull_half_height=(
                float(cull_geometry[1])
                if cull_geometry is not None
                else None
            ),
            transforms=tuple(
                TransformSpec.from_payload(values)
                for values in payload["transforms"]
            ),
            resolved_aim_override=(
                float(payload["resolved_aim_override"])
                if payload.get("resolved_aim_override") is not None
                else None
            ),
            bullet_type=(
                spawn_lifecycle[0]
                if spawn_lifecycle is not None
                else (
                    int(payload["bullet_type"])
                    if payload.get("bullet_type") is not None
                    else None
                )
            ),
            spawn_flags=(
                spawn_lifecycle[1]
                if spawn_lifecycle is not None
                else 0
            ),
        )


@dataclass(frozen=True)
class Callback12Event:
    frame: int
    tag_mask: int
    angle: float
    speed: float

    def __post_init__(self) -> None:
        if self.frame < 0 or self.tag_mask == 0:
            raise ValueError("invalid callback-12 event")
        if not math.isfinite(self.angle) or not math.isfinite(self.speed):
            raise ValueError("callback-12 operands must be finite")

    def to_payload(self) -> list[object]:
        return [self.frame, self.tag_mask, self.angle, self.speed]

    @classmethod
    def from_payload(cls, values: list[object]) -> "Callback12Event":
        return cls(
            int(values[0]),
            int(values[1]),
            float(values[2]),
            float(values[3]),
        )


@dataclass(frozen=True)
class Callback14Event:
    frame: int
    tag_mask: int
    speed: float

    def __post_init__(self) -> None:
        if self.frame < 0 or self.tag_mask == 0:
            raise ValueError("invalid callback-14 event")
        if not math.isfinite(self.speed):
            raise ValueError("callback-14 speed must be finite")

    def to_payload(self) -> list[object]:
        return [self.frame, self.tag_mask, self.speed]

    @classmethod
    def from_payload(cls, values: list[object]) -> "Callback14Event":
        return cls(
            int(values[0]),
            int(values[1]),
            float(values[2]),
        )


StageCallbackEvent = Callback12Event | Callback14Event


def _callback_event_from_payload(values: object) -> StageCallbackEvent:
    if not isinstance(values, list):
        raise ValueError("stage callback payload must be a list")
    if len(values) == 4:
        return Callback12Event.from_payload(values)
    if len(values) == 3:
        return Callback14Event.from_payload(values)
    raise ValueError("stage callback payload has a noncanonical layout")


@dataclass(frozen=True)
class LaserSpawnEvent:
    frame: int
    origin_x: float
    origin_y: float
    angle: float
    speed: float
    tail: float
    head: float
    maximum_length: float
    width: float
    warmup_frames: int
    active_frames: int
    fade_frames: int
    collision_enable_frame: int
    collision_disable_frame: int
    flags: int = 0

    def __post_init__(self) -> None:
        if self.frame < 0:
            raise ValueError("laser spawn frame cannot be negative")
        spawn_laser_state(
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            angle=self.angle,
            speed=self.speed,
            tail_distance=self.tail,
            head_distance=self.head,
            maximum_length=self.maximum_length,
            width=self.width,
            warmup_frames=self.warmup_frames,
            active_frames=self.active_frames,
            fade_frames=self.fade_frames,
            collision_enable_frame=self.collision_enable_frame,
            collision_disable_frame=self.collision_disable_frame,
            flags=self.flags,
        )

    def to_payload(self) -> list[object]:
        return [
            self.frame,
            self.origin_x,
            self.origin_y,
            self.angle,
            self.speed,
            self.tail,
            self.head,
            self.maximum_length,
            self.width,
            self.warmup_frames,
            self.active_frames,
            self.fade_frames,
            self.collision_enable_frame,
            self.collision_disable_frame,
            self.flags,
        ]

    @classmethod
    def from_payload(cls, values: list[object]) -> "LaserSpawnEvent":
        return cls(
            frame=int(values[0]),
            origin_x=float(values[1]),
            origin_y=float(values[2]),
            angle=float(values[3]),
            speed=float(values[4]),
            tail=float(values[5]),
            head=float(values[6]),
            maximum_length=float(values[7]),
            width=float(values[8]),
            warmup_frames=int(values[9]),
            active_frames=int(values[10]),
            fade_frames=int(values[11]),
            collision_enable_frame=int(values[12]),
            collision_disable_frame=int(values[13]),
            flags=int(values[14]),
        )


@dataclass(frozen=True)
class StagePhase:
    name: str
    start_frame: int
    end_frame: int
    clear_at_start: bool
    emitters: tuple[BulletEmitter, ...]
    callbacks: tuple[StageCallbackEvent, ...]
    lasers: tuple[LaserSpawnEvent, ...]

    def __post_init__(self) -> None:
        if (
            not self.name
            or self.start_frame < 0
            or self.end_frame < self.start_frame
        ):
            raise ValueError("invalid stage phase")
        if any(
            emitter.start_frame < self.start_frame
            or emitter.end_frame > self.end_frame
            for emitter in self.emitters
        ):
            raise ValueError("emitter escapes owning stage phase")
        if any(
            not self.start_frame <= event.frame <= self.end_frame
            for event in (*self.callbacks, *self.lasers)
        ):
            raise ValueError("phase event escapes owning stage phase")

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "frames": [self.start_frame, self.end_frame],
            "clear": int(self.clear_at_start),
            "emitters": [emitter.to_payload() for emitter in self.emitters],
            "callbacks": [event.to_payload() for event in self.callbacks],
            "lasers": [event.to_payload() for event in self.lasers],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "StagePhase":
        frames = payload["frames"]
        assert isinstance(frames, list)
        return cls(
            name=str(payload["name"]),
            start_frame=int(frames[0]),
            end_frame=int(frames[1]),
            clear_at_start=bool(payload["clear"]),
            emitters=tuple(
                BulletEmitter.from_payload(value)
                for value in payload["emitters"]
            ),
            callbacks=tuple(
                _callback_event_from_payload(value)
                for value in payload["callbacks"]
            ),
            lasers=tuple(
                LaserSpawnEvent.from_payload(value)
                for value in payload["lasers"]
            ),
        )


@dataclass(frozen=True)
class StageProgram:
    seed: int
    profile: str
    frame_count: int
    gameplay_rng_seed: int
    phases: tuple[StagePhase, ...]
    source_authority_commit: str = SOURCE_AUTHORITY_COMMIT
    source_unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.frame_count <= 0 or not 0 <= self.gameplay_rng_seed <= 0xFFFF:
            raise ValueError("invalid stage dimensions or RNG seed")
        if not self.profile or not self.phases:
            raise ValueError("stage profile and phases must be populated")
        expected_start = 0
        for phase in self.phases:
            if phase.start_frame != expected_start:
                raise ValueError("stage phases must be contiguous")
            expected_start = phase.end_frame + 1
        if expected_start != self.frame_count:
            raise ValueError("stage phases do not cover the complete stage")
        if self.source_authority_commit != SOURCE_AUTHORITY_COMMIT:
            raise ValueError("stage source-authority revision is unsupported")

    @property
    def source_closed(self) -> bool:
        return not self.source_unknowns and all(
            emitter.cull_half_width is not None
            for phase in self.phases
            for emitter in phase.emitters
        )

    @property
    def identity(self) -> str:
        return f"{self.profile}:{self.seed:016x}:{self.digest[:16]}"

    @property
    def schema(self) -> str:
        if any(
            isinstance(event, Callback14Event)
            for phase in self.phases
            for event in phase.callbacks
        ):
            return CALLBACK14_STAGE_SCHEMA
        if all(
            emitter.cull_half_width is not None
            for phase in self.phases
            for emitter in phase.emitters
        ):
            return CULL_GEOMETRY_STAGE_SCHEMA
        if any(
            emitter.spawn_flags
            for phase in self.phases
            for emitter in phase.emitters
        ):
            return LIFECYCLE_STAGE_SCHEMA
        if any(
            emitter.resolved_aim_override is not None
            for phase in self.phases
            for emitter in phase.emitters
        ):
            return RESOLVED_AIM_STAGE_SCHEMA
        return STAGE_SCHEMA

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_authority_commit": self.source_authority_commit,
            "seed": self.seed,
            "profile": self.profile,
            "frame_count": self.frame_count,
            "gameplay_rng_seed": self.gameplay_rng_seed,
            "source_unknowns": list(self.source_unknowns),
            "phases": [phase.to_payload() for phase in self.phases],
        }

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.unsigned_payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def to_payload(self) -> dict[str, object]:
        payload = self.unsigned_payload()
        payload["sha256"] = self.digest
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "StageProgram":
        schema = payload.get("schema")
        if schema not in (
            STAGE_SCHEMA,
            RESOLVED_AIM_STAGE_SCHEMA,
            LIFECYCLE_STAGE_SCHEMA,
            CULL_GEOMETRY_STAGE_SCHEMA,
            CALLBACK14_STAGE_SCHEMA,
        ):
            raise ValueError("unsupported source-stage schema")
        unsigned = dict(payload)
        digest = unsigned.pop("sha256", None)
        canonical = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if digest is not None and hashlib.sha256(canonical).hexdigest() != digest:
            raise ValueError("source-stage digest mismatch")
        program = cls(
            seed=int(unsigned["seed"]),
            profile=str(unsigned["profile"]),
            frame_count=int(unsigned["frame_count"]),
            gameplay_rng_seed=int(unsigned["gameplay_rng_seed"]),
            phases=tuple(
                StagePhase.from_payload(value) for value in unsigned["phases"]
            ),
            source_authority_commit=str(unsigned["source_authority_commit"]),
            source_unknowns=tuple(
                str(value) for value in unsigned["source_unknowns"]
            ),
        )
        if program.schema != schema:
            raise ValueError(
                "source-stage schema does not cover resolved-aim/lifecycle/"
                "cull-geometry/callback-14 features"
            )
        return program


@dataclass(slots=True)
class _TransformRuntime:
    spec: TransformSpec
    timer: int = 0
    repeat_count: int = 0
    restored_speed: float = 0.0
    acceleration_x: float = 0.0
    acceleration_y: float = 0.0
    resolved_angle: float = 0.0


@dataclass(slots=True)
class RuntimeBullet:
    slot: int
    source: str
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    half_width: float
    half_height: float
    cull_half_width: float
    cull_half_height: float
    base_speed: float
    base_angle: float
    tag_flags: int
    transforms: tuple[TransformSpec, ...]
    bullet_type: int | None = None
    spawn_flags: int = 0
    spawn_lifecycle: BulletSpawnLifecycle | None = None
    spawn_origin_x: float = 0.0
    spawn_origin_y: float = 0.0
    initial_velocity_x: float = 0.0
    initial_velocity_y: float = 0.0
    native_state: int = 1
    native_state_age: int = 0
    transform_cursor: int = 0
    active_transforms: dict[int, _TransformRuntime] = field(default_factory=dict)
    phase_state: int = 0
    collision_aux: int = 0
    presentation_flags: int = 0
    animation_index: int = 0
    age: int = 0
    offscreen_counter: int = 0

    @property
    def active_transform_flags(self) -> int:
        result = 0
        for kind in self.active_transforms:
            result |= kind
        return result

    @property
    def original_transform_flags(self) -> int:
        result = self.tag_flags | self.spawn_flags
        for transform in self.transforms:
            result |= transform.kind
        return result

    def retained_transform_program_runtime(
        self,
    ) -> BulletTransformProgramRuntime:
        records = tuple(
            TransformRecord(
                index=index,
                kind=spec.kind,
                allow_while_active=spec.allow_while_active,
                int_0=(
                    spec.repeat_limit
                    if spec.kind in (
                        TRANSFORM_REFLECT_ALL,
                        TRANSFORM_REFLECT_SIDES_TOP,
                    )
                    else spec.duration
                ),
                int_1=(
                    spec.repeat_limit
                    if spec.kind
                    in (
                        TRANSFORM_STOP_TURN,
                        TRANSFORM_STOP_REAIM,
                        TRANSFORM_STOP_SNAP,
                    )
                    else 0
                ),
                float_0=spec.float_0,
                float_1=spec.float_1,
            )
            for index, spec in enumerate(self.transforms)
        )

        def one_shared_runtime(kinds: tuple[int, ...]) -> _TransformRuntime | None:
            active = tuple(
                runtime
                for kind, runtime in self.active_transforms.items()
                if kind in kinds
            )
            if len(active) > 1:
                raise ValueError(
                    "stateful stage retained two independent runtimes for "
                    "one native shared transform block"
                )
            return active[0] if active else None

        vector = self.active_transforms.get(TRANSFORM_VECTOR_ACCELERATION)
        angular = self.active_transforms.get(TRANSFORM_ANGULAR_VELOCITY)
        stop = one_shared_runtime(
            (TRANSFORM_STOP_TURN, TRANSFORM_STOP_REAIM, TRANSFORM_STOP_SNAP)
        )
        reflection = one_shared_runtime(
            (TRANSFORM_REFLECT_ALL, TRANSFORM_REFLECT_SIDES_TOP)
        )
        return BulletTransformProgramRuntime(
            program=pack_transform_program(records),
            original_flags=self.original_transform_flags,
            queue_cursor=self.transform_cursor,
            cull_suppression_countdown=0,
            offscreen_counter=self.offscreen_counter,
            decelerate_timer=(
                _retained_timer(
                    self.active_transforms[TRANSFORM_DECELERATE].timer
                )
                if TRANSFORM_DECELERATE in self.active_transforms
                else None
            ),
            vector_acceleration=(
                VectorAccelerationRuntime(
                    timer=_retained_timer(vector.timer),
                    magnitude=vector.spec.float_0,
                    angle=vector.resolved_angle,
                    acceleration_x=vector.acceleration_x,
                    acceleration_y=vector.acceleration_y,
                    duration=vector.spec.duration,
                )
                if vector is not None
                else None
            ),
            angular_velocity=(
                AngularVelocityRuntime(
                    timer=_retained_timer(angular.timer),
                    speed_acceleration=angular.spec.float_0,
                    angular_velocity=angular.spec.float_1,
                    duration=angular.spec.duration,
                )
                if angular is not None
                else None
            ),
            stop=(
                StopTransformRuntime(
                    timer=_retained_timer(stop.timer),
                    resume_speed=stop.restored_speed,
                    angle_operand=stop.spec.float_0,
                    duration=stop.spec.duration,
                    repeat_limit=stop.spec.repeat_limit,
                    repeat_count=stop.repeat_count,
                )
                if stop is not None
                else None
            ),
            reflection=(
                ReflectionTransformRuntime(
                    restored_speed=reflection.restored_speed,
                    event_count=reflection.repeat_count,
                    event_limit=reflection.spec.repeat_limit,
                )
                if reflection is not None
                else None
            ),
        )

    def as_live_bullet(self) -> live.Bullet:
        return live.Bullet(
            x=self.x,
            y=self.y,
            vx=self.velocity_x,
            vy=self.velocity_y,
            half_width=self.half_width,
            half_height=self.half_height,
            transform_flags=self.active_transform_flags,
            slot=self.slot,
            speed=self.base_speed,
            angle=self.base_angle,
            transform_program_runtime=(
                self.retained_transform_program_runtime()
                if self.original_transform_flags
                else None
            ),
            callback_phase_state=self.phase_state,
            callback_aux_state=self.collision_aux,
            original_transform_flags=self.original_transform_flags,
            native_state=self.native_state,
            native_state_timer_elapsed=self.native_state_age,
            bullet_type=self.bullet_type,
        )


@dataclass(slots=True)
class RuntimeLaser:
    slot: int
    state: LaserState

    def as_live_laser(self) -> Laser:
        return Laser(
            origin_x=self.state.origin_x,
            origin_y=self.state.origin_y,
            angle=self.state.angle,
            tail=self.state.tail_distance,
            head=self.state.head_distance,
            half_width=self.state.current_width / 2.0,
            state=self.state,
            slot=self.slot,
            collision_flag=1,
            uncertainty=0.0,
            uncertainty_per_frame=0.0,
        )


@dataclass(frozen=True)
class StageStep:
    frame: int
    births_requested: int
    birth_allocation_calls: int
    births_allocated: int
    births_suppressed_by_pool: int
    callback_changes: int
    callback12_changes: int
    callback14_changes: int
    callback14_reactivated_slots: tuple[int, ...]
    spawn_lifecycle_activations: int
    transform_activations: int
    laser_spawns: int
    bullet_collision_slots: tuple[int, ...]
    laser_collision_slots: tuple[int, ...]
    active_bullets: int
    active_lasers: int


@dataclass
class StageMetrics:
    frames: int = 0
    births_requested: int = 0
    birth_allocation_calls: int = 0
    births_allocated: int = 0
    births_suppressed_by_pool: int = 0
    callback_changes: int = 0
    callback12_changes: int = 0
    callback14_changes: int = 0
    callback14_reactivations: int = 0
    callback14_reactivation_collisions: int = 0
    spawn_lifecycle_activations: int = 0
    transform_activations: int = 0
    laser_spawns: int = 0
    laser_spawns_dropped: int = 0
    clear_events: int = 0
    bullets_culled: int = 0
    max_active_bullets: int = 0
    max_active_lasers: int = 0
    pool_saturation_frames: int = 0
    raw_bullet_collisions: int = 0
    raw_laser_collisions: int = 0


PatternSampler = Callable[
    [SourcePattern, int, int, Th08Rng],
    SourcePatternSample,
]
Callback12Applier = Callable[..., tuple[Callback12State, bool]]
Callback14Applier = Callable[..., tuple[Callback12State, bool]]


def _python_pattern_sampler(
    pattern: SourcePattern,
    bullet_index: int,
    ring_index: int,
    rng: Th08Rng,
) -> SourcePatternSample:
    return pattern_sample(
        pattern,
        bullet_index=bullet_index,
        ring_index=ring_index,
        rng=rng,
    )


class StageRuntime:
    """Mutable native-order execution of one immutable stage program."""

    def __init__(
        self,
        program: StageProgram,
        *,
        pattern_sampler: PatternSampler = _python_pattern_sampler,
        callback12_applier: Callback12Applier = apply_callback12,
        callback14_applier: Callback14Applier = apply_callback14,
    ) -> None:
        if not program.source_closed:
            raise ValueError(
                "source-stage runtime refuses programs with UNKNOWN semantics"
            )
        self.program = program
        self.pattern_sampler = pattern_sampler
        self.callback12_applier = callback12_applier
        self.callback14_applier = callback14_applier
        self.rng = Th08Rng(program.gameplay_rng_seed)
        self.frame = 0
        self.bullets: list[RuntimeBullet | None] = [None] * BULLET_POOL_SIZE
        self.lasers: list[RuntimeLaser | None] = [None] * LASER_POOL_SIZE
        self.bullet_cursor = 0
        self.metrics = StageMetrics()
        self._emitters_by_frame = tuple(
            emitter
            for phase in program.phases
            for emitter in phase.emitters
        )
        self._callbacks = {
            frame: tuple(
                event
                for phase in program.phases
                for event in phase.callbacks
                if event.frame == frame
            )
            for frame in range(program.frame_count)
        }
        self._laser_spawns = {
            frame: tuple(
                event
                for phase in program.phases
                for event in phase.lasers
                if event.frame == frame
            )
            for frame in range(program.frame_count)
        }
        self._clear_frames = frozenset(
            phase.start_frame
            for phase in program.phases
            if phase.clear_at_start
        )

    @property
    def complete(self) -> bool:
        return self.frame >= self.program.frame_count

    def _next_bullet_slot(self) -> int | None:
        for offset in range(BULLET_POOL_SIZE):
            slot = (self.bullet_cursor + offset) % BULLET_POOL_SIZE
            if self.bullets[slot] is None:
                return slot
        return None

    def _activate_next_transform(self, bullet: RuntimeBullet) -> int:
        while bullet.transform_cursor < len(bullet.transforms):
            spec = bullet.transforms[bullet.transform_cursor]
            if bullet.active_transforms and not spec.allow_while_active:
                return 0
            bullet.transform_cursor += 1
            runtime = _TransformRuntime(spec=spec)
            if spec.kind == TRANSFORM_VECTOR_ACCELERATION:
                angle = (
                    bullet.base_angle if spec.float_1 <= -990.0 else spec.float_1
                )
                runtime.resolved_angle = f32(angle)
                runtime.acceleration_x, runtime.acceleration_y = _polar(
                    angle,
                    spec.float_0,
                )
            elif spec.kind in (
                TRANSFORM_STOP_TURN,
                TRANSFORM_STOP_REAIM,
                TRANSFORM_STOP_SNAP,
            ):
                runtime.restored_speed = (
                    bullet.base_speed if spec.float_1 <= -999.0 else f32(spec.float_1)
                )
            elif spec.kind in (
                TRANSFORM_REFLECT_ALL,
                TRANSFORM_REFLECT_SIDES_TOP,
            ):
                runtime.restored_speed = (
                    bullet.base_speed if spec.float_0 < 0.0 else f32(spec.float_0)
                )
            bullet.active_transforms[spec.kind] = runtime
            return 1
        return 0

    def _spawn_emitter(
        self,
        emitter: BulletEmitter,
        *,
        player_x: float,
        player_y: float,
    ) -> tuple[int, int, int, int]:
        origin_x, origin_y, pattern = emitter.resolved_descriptor(
            self.frame,
            player_x=player_x,
            player_y=player_y,
        )
        requested = pattern.count1 * pattern.count2
        allocation_calls = 0
        allocated = 0
        activations = 0
        for ring_index in range(pattern.count2):
            for bullet_index in range(pattern.count1):
                allocation_calls += 1
                slot = self._next_bullet_slot()
                if slot is None:
                    # FUN_0042F5F0 searches the pool before any random-mode
                    # operands are evaluated. Pool exhaustion therefore must
                    # not consume gameplay RNG for the rejected sample.
                    return requested, allocation_calls, allocated, activations
                sample = self.pattern_sampler(
                    pattern,
                    bullet_index,
                    ring_index,
                    self.rng,
                )
                spawn_origin_x = f32(origin_x)
                spawn_origin_y = f32(origin_y)
                lifecycle = (
                    bullet_spawn_lifecycle(
                        emitter.bullet_type,
                        emitter.spawn_flags,
                    )
                    if emitter.spawn_flags
                    else None
                )
                bullet_x = spawn_origin_x
                bullet_y = spawn_origin_y
                if lifecycle is not None:
                    bullet_x = _sub(
                        bullet_x,
                        _mul(sample.velocity_x, 4.0),
                    )
                    bullet_y = _sub(
                        bullet_y,
                        _mul(sample.velocity_y, 4.0),
                )
                cull_half_width = emitter.cull_half_width
                cull_half_height = emitter.cull_half_height
                if cull_half_width is None or cull_half_height is None:
                    raise ValueError(
                        "source-closed stage emitter lacks cull geometry"
                    )
                bullet = RuntimeBullet(
                    slot=slot,
                    source=emitter.emitter_id,
                    x=bullet_x,
                    y=bullet_y,
                    velocity_x=sample.velocity_x,
                    velocity_y=sample.velocity_y,
                    half_width=f32(emitter.half_width),
                    half_height=f32(emitter.half_height),
                    cull_half_width=f32(cull_half_width),
                    cull_half_height=f32(cull_half_height),
                    base_speed=sample.speed,
                    base_angle=sample.angle,
                    tag_flags=emitter.tag_flags,
                    transforms=emitter.transforms,
                    bullet_type=emitter.bullet_type,
                    spawn_flags=emitter.spawn_flags,
                    spawn_lifecycle=lifecycle,
                    spawn_origin_x=spawn_origin_x,
                    spawn_origin_y=spawn_origin_y,
                    initial_velocity_x=sample.velocity_x,
                    initial_velocity_y=sample.velocity_y,
                    native_state=(
                        lifecycle.state if lifecycle is not None else 1
                    ),
                )
                self.bullets[slot] = bullet
                self.bullet_cursor = (slot + 1) % BULLET_POOL_SIZE
                allocated += 1
                if lifecycle is None:
                    activations += self._activate_next_transform(bullet)
        return requested, allocation_calls, allocated, activations

    def _apply_callbacks(self) -> tuple[int, int, int, tuple[int, ...]]:
        changed = 0
        callback12_changes = 0
        callback14_changes = 0
        initial_aux = {
            bullet.slot: bullet.collision_aux
            for bullet in self.bullets
            if bullet is not None
        }
        callback14_touched: set[int] = set()
        for event in self._callbacks[self.frame]:
            for bullet in self.bullets:
                if bullet is None:
                    continue
                callback_state = Callback12State(
                    phase_state=bullet.phase_state,
                    collision_aux=bullet.collision_aux,
                    presentation_flags=bullet.presentation_flags,
                    animation_index=bullet.animation_index,
                    base_speed=bullet.base_speed,
                    base_angle=bullet.base_angle,
                    velocity_x=bullet.velocity_x,
                    velocity_y=bullet.velocity_y,
                )
                if isinstance(event, Callback12Event):
                    state, applied = self.callback12_applier(
                        callback_state,
                        bullet_tags=bullet.tag_flags,
                        selected_tags=event.tag_mask,
                        callback_angle=event.angle,
                        callback_speed=event.speed,
                        time_scale=1.0,
                    )
                else:
                    state, applied = self.callback14_applier(
                        callback_state,
                        bullet_tags=bullet.tag_flags,
                        selected_tags=event.tag_mask,
                        callback_speed=event.speed,
                        time_scale=1.0,
                    )
                if not applied:
                    continue
                bullet.phase_state = state.phase_state
                bullet.collision_aux = state.collision_aux
                bullet.presentation_flags = state.presentation_flags
                bullet.animation_index = state.animation_index
                bullet.velocity_x = state.velocity_x
                bullet.velocity_y = state.velocity_y
                changed += 1
                callback12_changes += int(isinstance(event, Callback12Event))
                callback14_changes += int(isinstance(event, Callback14Event))
                if isinstance(event, Callback14Event):
                    callback14_touched.add(bullet.slot)
        reactivated = tuple(
            sorted(
                slot
                for slot in callback14_touched
                if initial_aux.get(slot, 0) != 0
                and self.bullets[slot] is not None
                and self.bullets[slot].collision_aux == 0
            )
        )
        return (
            changed,
            callback12_changes,
            callback14_changes,
            reactivated,
        )

    def _apply_transform_handlers(
        self,
        bullet: RuntimeBullet,
        *,
        player_x: float,
        player_y: float,
    ) -> None:
        for kind in tuple(bullet.active_transforms):
            runtime = bullet.active_transforms.get(kind)
            if runtime is None:
                continue
            spec = runtime.spec
            if kind == TRANSFORM_DECELERATE:
                if runtime.timer <= 16:
                    magnitude = _sub(
                        _add(5.0, bullet.base_speed),
                        _div(_mul(runtime.timer, 5.0), 16.0),
                    )
                    bullet.velocity_x, bullet.velocity_y = _polar(
                        bullet.base_angle,
                        magnitude,
                    )
                else:
                    del bullet.active_transforms[kind]
                runtime.timer += 1
            elif kind == TRANSFORM_VECTOR_ACCELERATION:
                if runtime.timer >= spec.duration:
                    del bullet.active_transforms[kind]
                else:
                    bullet.velocity_x = _add(
                        bullet.velocity_x,
                        runtime.acceleration_x,
                    )
                    bullet.velocity_y = _add(
                        bullet.velocity_y,
                        runtime.acceleration_y,
                    )
                    if (
                        abs(bullet.velocity_x) > 0.0001
                        or abs(bullet.velocity_y) > 0.0001
                    ):
                        bullet.base_angle = f32(
                            math.atan2(bullet.velocity_y, bullet.velocity_x)
                        )
                runtime.timer += 1
            elif kind == TRANSFORM_ANGULAR_VELOCITY:
                if runtime.timer >= spec.duration:
                    del bullet.active_transforms[kind]
                else:
                    bullet.base_angle = normalize_angle(
                        _add(bullet.base_angle, spec.float_1)
                    )
                    bullet.base_speed = _add(
                        bullet.base_speed,
                        spec.float_0,
                    )
                    bullet.velocity_x, bullet.velocity_y = _polar(
                        bullet.base_angle,
                        bullet.base_speed,
                    )
                runtime.timer += 1
            elif kind in (
                TRANSFORM_STOP_TURN,
                TRANSFORM_STOP_REAIM,
                TRANSFORM_STOP_SNAP,
            ):
                if runtime.timer >= spec.duration:
                    runtime.repeat_count += 1
                    if runtime.repeat_count >= spec.repeat_limit:
                        del bullet.active_transforms[kind]
                    if kind == TRANSFORM_STOP_TURN:
                        bullet.base_angle = _add(
                            bullet.base_angle,
                            spec.float_0,
                        )
                    elif kind == TRANSFORM_STOP_REAIM:
                        bullet.base_angle = normalize_angle(
                            _add(
                                math.atan2(
                                    f32(player_y - bullet.y),
                                    f32(player_x - bullet.x),
                                ),
                                spec.float_0,
                            )
                        )
                    else:
                        bullet.base_angle = f32(spec.float_0)
                    bullet.base_speed = runtime.restored_speed
                    magnitude = bullet.base_speed
                    runtime.timer = 0
                else:
                    magnitude = _sub(
                        bullet.base_speed,
                        _div(
                            _mul(runtime.timer, bullet.base_speed),
                            spec.duration,
                        ),
                    )
                bullet.velocity_x, bullet.velocity_y = _polar(
                    bullet.base_angle,
                    magnitude,
                )
                runtime.timer += 1
            elif kind in (
                TRANSFORM_REFLECT_ALL,
                TRANSFORM_REFLECT_SIDES_TOP,
            ):
                if not self._inside_playfield(bullet):
                    if bullet.x < 0.0 or bullet.x >= PLAYFIELD_WIDTH:
                        bullet.base_angle = normalize_angle(
                            _sub(-bullet.base_angle, math.pi)
                        )
                    if bullet.y < 0.0 or (
                        bullet.y >= PLAYFIELD_HEIGHT
                        and kind == TRANSFORM_REFLECT_ALL
                    ):
                        bullet.base_angle = f32(-bullet.base_angle)
                    bullet.base_speed = runtime.restored_speed
                    bullet.velocity_x, bullet.velocity_y = _polar(
                        bullet.base_angle,
                        bullet.base_speed,
                    )
                    runtime.repeat_count += 1
                    if runtime.repeat_count >= spec.repeat_limit:
                        del bullet.active_transforms[kind]

    @staticmethod
    def _inside_playfield(bullet: RuntimeBullet) -> bool:
        return not (
            bullet.x + bullet.cull_half_width < 0.0
            or bullet.x - bullet.cull_half_width > PLAYFIELD_WIDTH
            or bullet.y + bullet.cull_half_height < 0.0
            or bullet.y - bullet.cull_half_height > PLAYFIELD_HEIGHT
        )

    def _update_bullets(
        self,
        *,
        player_x: float,
        player_y: float,
        player_half_width: float,
        player_half_height: float,
    ) -> tuple[int, int, tuple[int, ...]]:
        transform_activations = 0
        lifecycle_activations = 0
        collisions: list[int] = []
        # Manager physical scan is slot 0 followed by descending 1535..1.
        for slot in (0, *range(BULLET_POOL_SIZE - 1, 0, -1)):
            bullet = self.bullets[slot]
            if bullet is None:
                continue
            lifecycle = bullet.spawn_lifecycle
            lifecycle_activated_now = False
            if lifecycle is not None and bullet.native_state != 1:
                if bullet.native_state != lifecycle.state:
                    raise ValueError(
                        "spawn lifecycle state changed outside modeled path"
                    )
                next_age = bullet.age + 1
                if next_age > lifecycle.terminal_age:
                    raise ValueError("spawn lifecycle exceeded terminal age")
                bullet.x = _add(
                    bullet.x,
                    _div(bullet.velocity_x, lifecycle.motion_divisor),
                )
                bullet.y = _add(
                    bullet.y,
                    _div(bullet.velocity_y, lifecycle.motion_divisor),
                )
                if next_age < lifecycle.terminal_age:
                    bullet.age = next_age
                    bullet.native_state_age = next_age
                    continue
                bullet.native_state = 1
                bullet.native_state_age = 0
                lifecycle_activated_now = True
                lifecycle_activations += 1
            transform_activations += self._activate_next_transform(bullet)
            self._apply_transform_handlers(
                bullet,
                player_x=player_x,
                player_y=player_y,
            )
            bullet.x = _add(bullet.x, bullet.velocity_x)
            bullet.y = _add(bullet.y, bullet.velocity_y)
            if not self._inside_playfield(bullet):
                if bullet.active_transform_flags & 0xDC0:
                    bullet.offscreen_counter += 1
                    if bullet.offscreen_counter >= 0x80:
                        self.bullets[slot] = None
                        self.metrics.bullets_culled += 1
                        continue
                elif bullet.offscreen_counter == 0:
                    self.bullets[slot] = None
                    self.metrics.bullets_culled += 1
                    continue
                else:
                    bullet.offscreen_counter -= 1
            else:
                bullet.offscreen_counter = 0
            if bullet.native_state == 1 and bullet.collision_aux == 0 and (
                f32(player_x - player_half_width)
                <= f32(bullet.x + bullet.half_width)
                and f32(player_x + player_half_width)
                >= f32(bullet.x - bullet.half_width)
                and f32(player_y - player_half_height)
                <= f32(bullet.y + bullet.half_height)
                and f32(player_y + player_half_height)
                >= f32(bullet.y - bullet.half_height)
            ):
                collisions.append(slot)
            bullet.age += 1
            if not lifecycle_activated_now:
                bullet.native_state_age += 1
        return (
            transform_activations,
            lifecycle_activations,
            tuple(collisions),
        )

    def _spawn_lasers(self) -> int:
        spawned = 0
        for event in self._laser_spawns[self.frame]:
            slot = next(
                (
                    index
                    for index, laser in enumerate(self.lasers)
                    if laser is None
                ),
                None,
            )
            if slot is None:
                self.metrics.laser_spawns_dropped += 1
                continue
            self.lasers[slot] = RuntimeLaser(
                slot,
                spawn_laser_state(
                    origin_x=event.origin_x,
                    origin_y=event.origin_y,
                    angle=event.angle,
                    speed=event.speed,
                    tail_distance=event.tail,
                    head_distance=event.head,
                    maximum_length=event.maximum_length,
                    width=event.width,
                    warmup_frames=event.warmup_frames,
                    active_frames=event.active_frames,
                    fade_frames=event.fade_frames,
                    collision_enable_frame=event.collision_enable_frame,
                    collision_disable_frame=event.collision_disable_frame,
                    flags=event.flags,
                ),
            )
            spawned += 1
        return spawned

    def _update_lasers(
        self,
        *,
        player_x: float,
        player_y: float,
        player_half_width: float,
        player_half_height: float,
    ) -> tuple[int, ...]:
        from th08_laser_model import laser_overlaps_player

        collisions: list[int] = []
        for slot, runtime in enumerate(self.lasers):
            if runtime is None:
                continue
            result = step_laser(runtime.state)
            runtime.state = result.laser
            if any(
                laser_overlaps_player(
                    check.collision_box,
                    player_x=player_x,
                    player_y=player_y,
                    player_half_width=player_half_width,
                    player_half_height=player_half_height,
                )
                for check in result.checks
            ):
                collisions.append(slot)
            if not runtime.state.active:
                self.lasers[slot] = None
        return tuple(collisions)

    def step(
        self,
        *,
        player_x: float = 192.0,
        player_y: float = 400.0,
        player_half_width: float = 1.0,
        player_half_height: float = 1.0,
    ) -> StageStep:
        if self.complete:
            raise StopIteration("source stage is complete")
        if self.frame in self._clear_frames:
            self.bullets = [None] * BULLET_POOL_SIZE
            self.metrics.clear_events += 1

        (
            callback_changes,
            callback12_changes,
            callback14_changes,
            callback14_reactivated_slots,
        ) = self._apply_callbacks()
        requested = 0
        allocation_calls = 0
        allocated = 0
        activations = 0
        for emitter in self._emitters_by_frame:
            if not emitter.due(self.frame):
                continue
            (
                emitter_requested,
                emitter_allocation_calls,
                emitter_allocated,
                emitter_activations,
            ) = self._spawn_emitter(
                emitter,
                player_x=player_x,
                player_y=player_y,
            )
            requested += emitter_requested
            allocation_calls += emitter_allocation_calls
            allocated += emitter_allocated
            activations += emitter_activations

        laser_spawns = self._spawn_lasers()
        (
            update_activations,
            lifecycle_activations,
            bullet_collisions,
        ) = self._update_bullets(
            player_x=player_x,
            player_y=player_y,
            player_half_width=player_half_width,
            player_half_height=player_half_height,
        )
        activations += update_activations
        laser_collisions = self._update_lasers(
            player_x=player_x,
            player_y=player_y,
            player_half_width=player_half_width,
            player_half_height=player_half_height,
        )
        active_bullets = sum(bullet is not None for bullet in self.bullets)
        active_lasers = sum(laser is not None for laser in self.lasers)
        suppressed = requested - allocated
        result = StageStep(
            frame=self.frame,
            births_requested=requested,
            birth_allocation_calls=allocation_calls,
            births_allocated=allocated,
            births_suppressed_by_pool=suppressed,
            callback_changes=callback_changes,
            callback12_changes=callback12_changes,
            callback14_changes=callback14_changes,
            callback14_reactivated_slots=callback14_reactivated_slots,
            spawn_lifecycle_activations=lifecycle_activations,
            transform_activations=activations,
            laser_spawns=laser_spawns,
            bullet_collision_slots=bullet_collisions,
            laser_collision_slots=laser_collisions,
            active_bullets=active_bullets,
            active_lasers=active_lasers,
        )
        self.metrics.frames += 1
        self.metrics.births_requested += requested
        self.metrics.birth_allocation_calls += allocation_calls
        self.metrics.births_allocated += allocated
        self.metrics.births_suppressed_by_pool += suppressed
        self.metrics.callback_changes += callback_changes
        self.metrics.callback12_changes += callback12_changes
        self.metrics.callback14_changes += callback14_changes
        self.metrics.callback14_reactivations += len(
            callback14_reactivated_slots
        )
        self.metrics.callback14_reactivation_collisions += len(
            set(callback14_reactivated_slots).intersection(bullet_collisions)
        )
        self.metrics.spawn_lifecycle_activations += lifecycle_activations
        self.metrics.transform_activations += activations
        self.metrics.laser_spawns += laser_spawns
        self.metrics.max_active_bullets = max(
            self.metrics.max_active_bullets,
            active_bullets,
        )
        self.metrics.max_active_lasers = max(
            self.metrics.max_active_lasers,
            active_lasers,
        )
        self.metrics.pool_saturation_frames += int(
            active_bullets == BULLET_POOL_SIZE
        )
        self.metrics.raw_bullet_collisions += len(bullet_collisions)
        self.metrics.raw_laser_collisions += len(laser_collisions)
        self.frame += 1
        return result

    def live_snapshot(self) -> tuple[tuple[live.Bullet, ...], tuple[Laser, ...]]:
        return (
            tuple(
                bullet.as_live_bullet()
                for bullet in self.bullets
                if bullet is not None
            ),
            tuple(
                laser.as_live_laser()
                for laser in self.lasers
                if laser is not None
            ),
        )

    def state_digest(self) -> str:
        def float_bits(value: float) -> int:
            import struct

            return struct.unpack("<I", struct.pack("<f", value))[0]

        payload = {
            "frame": self.frame,
            "rng": [self.rng.state, self.rng.calls],
            "cursor": self.bullet_cursor,
            "bullets": [
                [
                    bullet.slot,
                    bullet.source,
                    float_bits(bullet.x),
                    float_bits(bullet.y),
                    float_bits(bullet.velocity_x),
                    float_bits(bullet.velocity_y),
                    float_bits(bullet.base_speed),
                    float_bits(bullet.base_angle),
                    bullet.bullet_type,
                    bullet.spawn_flags,
                    bullet.native_state,
                    bullet.native_state_age,
                    bullet.age,
                    bullet.tag_flags,
                    bullet.phase_state,
                    bullet.collision_aux,
                    bullet.transform_cursor,
                    sorted(
                        (
                            kind,
                            runtime.timer,
                            runtime.repeat_count,
                        )
                        for kind, runtime in bullet.active_transforms.items()
                    ),
                ]
                for bullet in self.bullets
                if bullet is not None
            ],
            "lasers": [
                [
                    laser.slot,
                    int(laser.state.phase),
                    laser.state.timer,
                    float_bits(laser.state.timer_fraction),
                    float_bits(laser.state.tail_distance),
                    float_bits(laser.state.head_distance),
                    float_bits(laser.state.current_width),
                    int(laser.state.active),
                ]
                for laser in self.lasers
                if laser is not None
            ],
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()


def run_stage(
    program: StageProgram,
    *,
    player_x: float = 192.0,
    player_y: float = 400.0,
) -> StageRuntime:
    runtime = StageRuntime(program)
    while not runtime.complete:
        runtime.step(player_x=player_x, player_y=player_y)
    return runtime


__all__ = [
    "BULLET_POOL_SIZE",
    "CALLBACK14_STAGE_SCHEMA",
    "CULL_GEOMETRY_STAGE_SCHEMA",
    "BulletEmitter",
    "Callback12Event",
    "Callback14Event",
    "LASER_POOL_SIZE",
    "LIFECYCLE_STAGE_SCHEMA",
    "LaserSpawnEvent",
    "RuntimeBullet",
    "RESOLVED_AIM_STAGE_SCHEMA",
    "SOURCE_AUTHORITY_COMMIT",
    "STAGE_SCHEMA",
    "StageMetrics",
    "StagePhase",
    "StageProgram",
    "StageRuntime",
    "StageStep",
    "TRANSFORM_ANGULAR_VELOCITY",
    "TRANSFORM_DECELERATE",
    "TRANSFORM_REFLECT_ALL",
    "TRANSFORM_REFLECT_SIDES_TOP",
    "TRANSFORM_STOP_REAIM",
    "TRANSFORM_STOP_SNAP",
    "TRANSFORM_STOP_TURN",
    "TRANSFORM_VECTOR_ACCELERATION",
    "TransformSpec",
    "run_stage",
]
