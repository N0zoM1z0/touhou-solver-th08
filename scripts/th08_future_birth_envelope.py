"""Conservative native-order geometry for future TH08 bullet births.

This module deliberately starts after ECL/timeline control-flow closure.  Its
input is a complete set of direct-fire events and its output is a finite set of
time-indexed AABB envelopes that can be consumed by the game-neutral corridor
solver.  Unsupported lifecycle or transform state raises instead of silently
dropping a future hostile.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from touhou_control.corridor import (
    AabbHazard,
    AabbTrajectoryHazard,
    AnnularSectorTrajectoryHazard,
)


FUTURE_BIRTH_ENVELOPE_SEMANTICS_VERSION = (
    "th08-future-birth-envelope-v4-source-spawn-pattern"
)
FUTURE_BIRTH_SECTOR_SEMANTICS_VERSION = (
    "th08-future-birth-sector-v4-source-spawn-pattern"
)
_TWO_PI = 2.0 * math.pi
_ZUN_PI = struct.unpack("<f", struct.pack("<f", math.pi))[0]
_ZUN_TWO_PI = struct.unpack("<f", struct.pack("<f", _ZUN_PI * 2.0))[0]
AUTOMATIC_PLAYER_AIM_MODES = frozenset((0, 2, 4))
_STATE2_COMPLETION_AGE = 10
_KNOWN_NONPROGRAM_FLAGS = 0x0203
_TRANSFORM_PROGRAM_LENGTH = 18
_TRANSFORM_RECORD_SIZE = 24
_VECTOR_ACCELERATION = 0x0000010
_ANGULAR_VELOCITY = 0x0000020
_STOP_REAIM_REPEAT = 0x0000080
_REFLECT_ALL_EDGES = 0x0000400
_REFLECT_SIDES_AND_TOP = 0x0000800
_SUPPRESS_OFFSCREEN_CULL = 0x0002000
_REPLACE_BULLET_TEMPLATE = 0x0004000
_TIMED_QUEUE_BARRIER = 0x0020000
_PLAY_SOUND = 0x0080000
_SUPPORTED_TRANSFORM_KINDS = frozenset(
    (
        _VECTOR_ACCELERATION,
        _ANGULAR_VELOCITY,
        _STOP_REAIM_REPEAT,
        _REFLECT_ALL_EDGES,
        _REFLECT_SIDES_AND_TOP,
        _SUPPRESS_OFFSCREEN_CULL,
        _REPLACE_BULLET_TEMPLATE,
        _TIMED_QUEUE_BARRIER,
        _PLAY_SOUND,
    )
)


@dataclass(frozen=True)
class _TransformRecord:
    float_0: float
    float_1: float
    int_0: int
    int_1: int
    kind: int
    allow_while_active: bool


def _active_transform_records(
    program: bytes,
    *,
    original_flags: int,
) -> tuple[_TransformRecord, ...]:
    if len(program) != _TRANSFORM_PROGRAM_LENGTH * _TRANSFORM_RECORD_SIZE:
        raise ValueError("future transform program must contain 18 records")
    records: list[_TransformRecord] = []
    for index in range(_TRANSFORM_PROGRAM_LENGTH):
        values = struct.unpack_from(
            "<ffiiII",
            program,
            index * _TRANSFORM_RECORD_SIZE,
        )
        record = _TransformRecord(
            float_0=float(values[0]),
            float_1=float(values[1]),
            int_0=int(values[2]),
            int_1=int(values[3]),
            kind=int(values[4]),
            allow_while_active=bool(values[5]),
        )
        if record.kind == 0:
            break
        if record.kind & original_flags:
            records.append(record)
    return tuple(records)


@dataclass(frozen=True)
class FloatInterval:
    """Closed finite interval used for set-valued native inputs."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.lower)
            or not math.isfinite(self.upper)
            or self.lower > self.upper
        ):
            raise ValueError("float interval must be finite and ordered")

    @classmethod
    def point(cls, value: float) -> FloatInterval:
        return cls(value, value)

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) * 0.5

    @property
    def radius(self) -> float:
        return (self.upper - self.lower) * 0.5

    def add(self, other: FloatInterval) -> FloatInterval:
        return FloatInterval(
            self.lower + other.lower,
            self.upper + other.upper,
        )

    def multiply(self, other: FloatInterval) -> FloatInterval:
        products = (
            self.lower * other.lower,
            self.lower * other.upper,
            self.upper * other.lower,
            self.upper * other.upper,
        )
        return FloatInterval(min(products), max(products))

    def scale(self, value: float) -> FloatInterval:
        return self.multiply(FloatInterval.point(value))


@dataclass(frozen=True)
class FutureDirectFire:
    """One exhaustively reached ECL direct-fire event.

    ``activation_frames`` are relative to the captured observable root and
    identify manager updates in which allocation can happen.  Suppression by
    distance, filters, or pool exhaustion need not be predicted: retaining the
    possible births is a safe bounded over-approximation.
    """

    source: str
    activation_frames: tuple[int, ...]
    origin_x: FloatInterval
    origin_y: FloatInterval
    mode: int
    count1: int
    count2: int
    speed1: FloatInterval
    speed2: FloatInterval
    angle1: FloatInterval
    angle2: FloatInterval
    aim_angle: FloatInterval
    half_width: float
    half_height: float
    original_flags: int
    transform_program_zero: bool
    transform_program: bytes = b""
    # Optional affine dependency retained by the ordinary ECL analyzer.
    # ``angleN == residual + coefficient * angle_to_player`` at the event's
    # native allocation update.  ``None`` means the analyzer could not prove
    # that factorization and any causal action-conditioned consumer must fail
    # closed.  The ordinary union envelope above remains valid either way.
    angle1_player_aim_coefficient: float | None = None
    angle1_player_aim_residual: FloatInterval | None = None
    angle2_player_aim_coefficient: float | None = None
    angle2_player_aim_residual: FloatInterval | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("future direct-fire source must not be empty")
        if (
            not self.activation_frames
            or any(frame <= 0 for frame in self.activation_frames)
            or tuple(sorted(set(self.activation_frames)))
            != self.activation_frames
        ):
            raise ValueError(
                "activation frames must be a sorted unique positive tuple"
            )
        if not 0 <= self.mode <= 8:
            raise ValueError("direct-fire mode must be in 0..8")
        if self.count1 <= 0 or self.count2 <= 0:
            raise ValueError("direct-fire counts must be positive")
        for label, coefficient, residual in (
            (
                "angle1",
                self.angle1_player_aim_coefficient,
                self.angle1_player_aim_residual,
            ),
            (
                "angle2",
                self.angle2_player_aim_coefficient,
                self.angle2_player_aim_residual,
            ),
        ):
            if (coefficient is None) != (residual is None):
                raise ValueError(
                    f"{label} causal aim coefficient/residual must be paired"
                )
            if coefficient is not None and not math.isfinite(coefficient):
                raise ValueError(f"{label} causal aim coefficient is nonfinite")
        if (
            not math.isfinite(self.half_width)
            or not math.isfinite(self.half_height)
            or self.half_width < 0.0
            or self.half_height < 0.0
        ):
            raise ValueError("future bullet geometry must be finite")
        if self.transform_program_zero:
            if self.transform_program and any(self.transform_program):
                raise ValueError("future transform zero marker is inconsistent")
            active_transforms: tuple[_TransformRecord, ...] = ()
        else:
            if not self.transform_program:
                raise ValueError(
                    "nonzero future transform programs require program bytes"
                )
            active_transforms = _active_transform_records(
                self.transform_program,
                original_flags=self.original_flags,
            )
            unsupported_kinds = sorted(
                record.kind
                for record in active_transforms
                if record.kind not in _SUPPORTED_TRANSFORM_KINDS
            )
            if unsupported_kinds:
                joined = ",".join(hex(kind) for kind in unsupported_kinds)
                raise ValueError(
                    "future transform programs contain unsupported active "
                    f"kinds {joined}"
                )
            if any(
                not math.isfinite(record.float_0)
                or not math.isfinite(record.float_1)
                for record in active_transforms
            ):
                raise ValueError("future transform operand is nonfinite")
        active_kind_mask = 0
        for record in active_transforms:
            active_kind_mask |= record.kind
        unsupported_flags = self.original_flags & ~(
            _KNOWN_NONPROGRAM_FLAGS | active_kind_mask
        )
        if unsupported_flags:
            raise ValueError(
                f"unsupported future bullet flags 0x{unsupported_flags:x}"
            )
        if self.original_flags & (0x04 | 0x08):
            raise ValueError(
                "future lifecycle states 3/4 require separate geometry"
            )

    @property
    def active_transform_records(self) -> tuple[_TransformRecord, ...]:
        if self.transform_program_zero:
            return ()
        return _active_transform_records(
            self.transform_program,
            original_flags=self.original_flags,
        )


def _transform_path_profile(
    event: FutureDirectFire,
) -> tuple[float, float] | None:
    """Return conservative maximum initial speed and per-step acceleration.

    Vector acceleration and angular-velocity records can change the native
    velocity every update. Reflections and stop/reaim can change direction.
    Treating every such update as immediately active, summing all acceleration
    magnitudes, and ignoring finite durations is a conservative superset of
    the shipped queue. Template, cull, barrier, and sound records do not move
    the bullet and therefore retain the sharper linear sector.
    """

    records = tuple(
        record
        for record in event.active_transform_records
        if record.kind
        in (
            _VECTOR_ACCELERATION,
            _ANGULAR_VELOCITY,
            _STOP_REAIM_REPEAT,
            _REFLECT_ALL_EDGES,
            _REFLECT_SIDES_AND_TOP,
        )
    )
    if not records:
        return None
    maximum_speed = max(
        abs(event.speed1.lower),
        abs(event.speed1.upper),
        abs(event.speed2.lower),
        abs(event.speed2.upper),
    )
    acceleration = 0.0
    for record in records:
        if record.kind in (_VECTOR_ACCELERATION, _ANGULAR_VELOCITY):
            acceleration += abs(record.float_0)
        elif record.kind == _STOP_REAIM_REPEAT:
            resume_speed = (
                maximum_speed
                if record.float_1 <= -999.0
                else abs(record.float_1)
            )
            maximum_speed = max(maximum_speed, resume_speed)
        elif record.kind in (_REFLECT_ALL_EDGES, _REFLECT_SIDES_AND_TOP):
            if record.float_0 >= 0.0:
                maximum_speed = max(maximum_speed, abs(record.float_0))
    return maximum_speed, acceleration


def _transform_path_radius_bound(
    profile: tuple[float, float] | None,
    *,
    age: int,
    state2: bool,
) -> float | None:
    if profile is None:
        return None
    maximum_speed, acceleration = profile
    steps = age + 4 if state2 else age
    return (
        maximum_speed * steps
        + acceleration * steps * (steps + 1) * 0.5
    )


@dataclass(frozen=True)
class FutureBirthEnvelope:
    """One conservative trajectory plus its causal producer identity."""

    source: str
    activation_frame: int
    pattern_index: tuple[int, int]
    trajectory: AabbTrajectoryHazard


@dataclass(frozen=True)
class FutureBirthSectorEnvelope:
    """One compact continuous angular envelope for a possible allocation."""

    source: str
    activation_frame: int
    pattern_index: tuple[int, int]
    trajectory: AnnularSectorTrajectoryHazard


def state2_position_coefficient(age: int) -> float:
    """Return the exact velocity coefficient after ``age`` manager updates."""

    if age <= 0:
        raise ValueError("state-2 age must be positive")
    if age < _STATE2_COMPLETION_AGE:
        return -4.0 + 0.5 * age
    return float(age - 8)


def _trig_bounds(angle: FloatInterval, *, cosine: bool) -> FloatInterval:
    if angle.upper - angle.lower >= _TWO_PI:
        return FloatInterval(-1.0, 1.0)
    function = math.cos if cosine else math.sin
    values = [function(angle.lower), function(angle.upper)]
    offset = 0.0 if cosine else math.pi * 0.5
    first = math.ceil((angle.lower - offset) / math.pi)
    last = math.floor((angle.upper - offset) / math.pi)
    values.extend(
        function(offset + index * math.pi)
        for index in range(first, last + 1)
    )
    return FloatInterval(min(values), max(values))


def _velocity_intervals(
    speed: FloatInterval,
    angle: FloatInterval,
) -> tuple[FloatInterval, FloatInterval]:
    return (
        speed.multiply(_trig_bounds(angle, cosine=True)),
        speed.multiply(_trig_bounds(angle, cosine=False)),
    )


def _speed_for_ring(
    event: FutureDirectFire,
    ring_index: int,
) -> FloatInterval:
    if event.count2 <= 1:
        return event.speed1
    fraction = ring_index / event.count2
    return event.speed1.scale(1.0 - fraction).add(
        event.speed2.scale(fraction)
    )


def _pattern_speed_angle(
    event: FutureDirectFire,
    *,
    bullet_index: int,
    ring_index: int,
) -> tuple[FloatInterval, FloatInterval]:
    speed = _speed_for_ring(event, ring_index)
    angle = event.angle1
    if event.mode in (0, 1):
        if event.count1 & 1:
            lateral = event.angle2.scale((bullet_index + 1) // 2)
        else:
            lateral = event.angle2.scale(bullet_index // 2 + 0.5)
        if bullet_index & 1:
            lateral = lateral.scale(-1.0)
        angle = angle.add(lateral)
        if event.mode == 0:
            angle = angle.add(event.aim_angle)
    elif event.mode in (2, 3):
        angle = angle.add(
            FloatInterval.point(
                bullet_index * _ZUN_TWO_PI / event.count1
            )
        ).add(event.angle2.scale(ring_index))
        if event.mode == 2:
            angle = angle.add(event.aim_angle)
    elif event.mode in (4, 5):
        angle = angle.add(
            FloatInterval.point(
                _ZUN_PI / event.count1
                + bullet_index * _ZUN_TWO_PI / event.count1
            )
        )
        if event.mode == 4:
            angle = angle.add(event.aim_angle)
    elif event.mode == 6:
        angle = FloatInterval(
            min(event.angle1.lower, event.angle2.lower),
            max(event.angle1.upper, event.angle2.upper),
        )
    elif event.mode == 7:
        speed = FloatInterval(
            min(event.speed1.lower, event.speed2.lower),
            max(event.speed1.upper, event.speed2.upper),
        )
        angle = angle.add(
            FloatInterval.point(
                bullet_index * _ZUN_TWO_PI / event.count1
            )
        ).add(event.angle2.scale(ring_index))
    elif event.mode == 8:
        speed = FloatInterval(
            min(event.speed1.lower, event.speed2.lower),
            max(event.speed1.upper, event.speed2.upper),
        )
        angle = FloatInterval(
            min(event.angle1.lower, event.angle2.lower),
            max(event.angle1.upper, event.angle2.upper),
        )
    return speed, angle


def _sample_from_bounds(
    x: FloatInterval,
    y: FloatInterval,
    *,
    half_width: float,
    half_height: float,
) -> AabbHazard:
    # Two ulps at screen-scale prevents a binary32 endpoint from escaping a
    # real-valued interval solely because Python evaluated trig in binary64.
    numeric_guard = 2.0e-5
    return AabbHazard(
        x=x.midpoint,
        y=y.midpoint,
        half_width=half_width + x.radius + numeric_guard,
        half_height=half_height + y.radius + numeric_guard,
    )


def lower_future_direct_fire(
    event: FutureDirectFire,
    *,
    horizon_frames: int,
) -> tuple[FutureBirthEnvelope, ...]:
    """Lower every possible allocation into consumed finite AABB envelopes."""

    if horizon_frames < 0:
        raise ValueError("future birth horizon cannot be negative")
    envelopes: list[FutureBirthEnvelope] = []
    state2 = bool(event.original_flags & 0x02)
    transform_profile = _transform_path_profile(event)
    for activation_frame in event.activation_frames:
        if activation_frame > horizon_frames:
            continue
        for ring_index in range(event.count2):
            for bullet_index in range(event.count1):
                speed, angle = _pattern_speed_angle(
                    event,
                    bullet_index=bullet_index,
                    ring_index=ring_index,
                )
                velocity_x, velocity_y = _velocity_intervals(speed, angle)
                samples: list[AabbHazard | None] = []
                for frame in range(horizon_frames + 1):
                    age = frame - activation_frame + 1
                    if age <= 0 or (state2 and age < _STATE2_COMPLETION_AGE):
                        samples.append(None)
                        continue
                    transformed_radius = _transform_path_radius_bound(
                        transform_profile,
                        age=age,
                        state2=state2,
                    )
                    if transformed_radius is not None:
                        radius = transformed_radius
                        samples.append(
                            AabbHazard(
                                x=event.origin_x.midpoint,
                                y=event.origin_y.midpoint,
                                half_width=(
                                    event.half_width
                                    + event.origin_x.radius
                                    + radius
                                ),
                                half_height=(
                                    event.half_height
                                    + event.origin_y.radius
                                    + radius
                                ),
                            )
                        )
                    else:
                        coefficient = (
                            state2_position_coefficient(age)
                            if state2
                            else float(age)
                        )
                        samples.append(
                            _sample_from_bounds(
                                event.origin_x.add(
                                    velocity_x.scale(coefficient)
                                ),
                                event.origin_y.add(
                                    velocity_y.scale(coefficient)
                                ),
                                half_width=event.half_width,
                                half_height=event.half_height,
                            )
                        )
                envelopes.append(
                    FutureBirthEnvelope(
                        source=event.source,
                        activation_frame=activation_frame,
                        pattern_index=(bullet_index, ring_index),
                        trajectory=AabbTrajectoryHazard(tuple(samples)),
                    )
                )
    return tuple(envelopes)


def lower_future_direct_fire_sectors(
    event: FutureDirectFire,
    *,
    horizon_frames: int,
) -> tuple[FutureBirthSectorEnvelope, ...]:
    """Lower births without replacing continuous direction sets by boxes."""

    if horizon_frames < 0:
        raise ValueError("future birth horizon cannot be negative")
    envelopes: list[FutureBirthSectorEnvelope] = []
    state2 = bool(event.original_flags & 0x02)
    transform_profile = _transform_path_profile(event)
    origin_uncertainty = math.hypot(
        event.origin_x.radius,
        event.origin_y.radius,
    )
    half_extent_radius = math.hypot(event.half_width, event.half_height)
    for activation_frame in event.activation_frames:
        if activation_frame > horizon_frames:
            continue
        for ring_index in range(event.count2):
            for bullet_index in range(event.count1):
                speed, angle = _pattern_speed_angle(
                    event,
                    bullet_index=bullet_index,
                    ring_index=ring_index,
                )
                if speed.lower < 0.0:
                    raise ValueError(
                        "annular-sector lowering requires nonnegative speed"
                    )
                transformed_path = (
                    _transform_path_radius_bound(
                        transform_profile,
                        age=1,
                        state2=state2,
                    )
                    is not None
                )
                minimum_radii: list[float | None] = []
                maximum_radii: list[float | None] = []
                for frame in range(horizon_frames + 1):
                    age = frame - activation_frame + 1
                    if age <= 0 or (
                        state2 and age < _STATE2_COMPLETION_AGE
                    ):
                        minimum_radii.append(None)
                        maximum_radii.append(None)
                        continue
                    transformed_radius = _transform_path_radius_bound(
                        transform_profile,
                        age=age,
                        state2=state2,
                    )
                    if transformed_radius is not None:
                        minimum_radii.append(0.0)
                        maximum_radii.append(transformed_radius)
                    else:
                        coefficient = (
                            state2_position_coefficient(age)
                            if state2
                            else float(age)
                        )
                        minimum_radii.append(speed.lower * coefficient)
                        maximum_radii.append(speed.upper * coefficient)
                envelopes.append(
                    FutureBirthSectorEnvelope(
                        source=event.source,
                        activation_frame=activation_frame,
                        pattern_index=(bullet_index, ring_index),
                        trajectory=AnnularSectorTrajectoryHazard(
                            origin_x=event.origin_x.midpoint,
                            origin_y=event.origin_y.midpoint,
                            minimum_angle=(
                                -math.pi
                                if transformed_path
                                else angle.lower
                            ),
                            maximum_angle=(
                                math.pi
                                if transformed_path
                                else angle.upper
                            ),
                            minimum_radii=tuple(minimum_radii),
                            maximum_radii=tuple(maximum_radii),
                            half_extent_radius=half_extent_radius,
                            origin_uncertainty=origin_uncertainty,
                        ),
                    )
                )
    return tuple(envelopes)


def lower_complete_future_births(
    events: tuple[FutureDirectFire, ...],
    *,
    horizon_frames: int,
) -> tuple[FutureBirthEnvelope, ...]:
    """Lower a source-closure result without discarding any producer."""

    return tuple(
        envelope
        for event in events
        for envelope in lower_future_direct_fire(
            event,
            horizon_frames=horizon_frames,
        )
    )


def lower_complete_future_birth_sectors(
    events: tuple[FutureDirectFire, ...],
    *,
    horizon_frames: int,
) -> tuple[FutureBirthSectorEnvelope, ...]:
    """Lower a complete source set into compact continuous sectors."""

    return tuple(
        envelope
        for event in events
        for envelope in lower_future_direct_fire_sectors(
            event,
            horizon_frames=horizon_frames,
        )
    )


__all__ = [
    "AUTOMATIC_PLAYER_AIM_MODES",
    "FUTURE_BIRTH_ENVELOPE_SEMANTICS_VERSION",
    "FUTURE_BIRTH_SECTOR_SEMANTICS_VERSION",
    "FloatInterval",
    "FutureBirthEnvelope",
    "FutureBirthSectorEnvelope",
    "FutureDirectFire",
    "lower_complete_future_births",
    "lower_complete_future_birth_sectors",
    "lower_future_direct_fire",
    "lower_future_direct_fire_sectors",
    "state2_position_coefficient",
]
