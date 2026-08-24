"""Independent source-level primitives used by the stateful stage runtime.

These functions follow the recovered C statements with explicit binary32
stores.  The separately compiled C oracle in ``native/th08_source_oracle`` is
the differential authority; this module is the readable scalar candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from th08_ecl_callback_model import callback_12_phase_transition
from th08_rng import Th08Rng


_PI = struct.unpack("<f", struct.pack("<I", 0x40490FDB))[0]
_TWO_PI = struct.unpack("<f", struct.pack("<I", 0x40C90FDB))[0]


def f32(value: float | int) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def _sub(left: float, right: float) -> float:
    return f32(f32(left) - f32(right))


def _mul(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def _div(left: float, right: float) -> float:
    return f32(f32(left) / f32(right))


def _cosf(value: float) -> float:
    return f32(math.cos(f32(value)))


def _sinf(value: float) -> float:
    return f32(math.sin(f32(value)))


def normalize_angle(angle: float) -> float:
    """Transcribe ``AddNormalizeAngle(angle, 0)`` including its loop cap."""

    value = f32(angle)
    iterations = 0
    while value > _PI:
        value = _sub(value, _TWO_PI)
        if iterations > 16:
            break
        iterations += 1
    while value < -_PI:
        value = _add(value, _TWO_PI)
        if iterations > 16:
            break
        iterations += 1
    return value


def rng_next_f32(rng: Th08Rng) -> float:
    """Return source ``GetRandomF32`` with the pre-division U32 cast."""

    numerator = f32(rng.next_u32())
    denominator = f32(0xFFFFFFFF)
    return _div(numerator, denominator)


@dataclass(frozen=True)
class SourcePattern:
    mode: int
    count1: int
    count2: int
    speed1: float
    speed2: float
    angle: float
    angle_step: float
    angle_to_player: float
    time_scale: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.mode <= 8:
            raise ValueError("source pattern mode must be in 0..8")
        if self.count1 <= 0 or self.count2 <= 0:
            raise ValueError("source pattern counts must be positive")
        if not all(
            math.isfinite(value)
            for value in (
                self.speed1,
                self.speed2,
                self.angle,
                self.angle_step,
                self.angle_to_player,
                self.time_scale,
            )
        ):
            raise ValueError("source pattern operands must be finite")


@dataclass(frozen=True)
class SourcePatternSample:
    speed: float
    angle: float
    velocity_x: float
    velocity_y: float


def pattern_sample(
    pattern: SourcePattern,
    *,
    bullet_index: int,
    ring_index: int,
    rng: Th08Rng | None,
) -> SourcePatternSample:
    """Transcribe ``BulletManager::FUN_0042f5f0`` for one allocation."""

    if not 0 <= bullet_index < pattern.count1:
        raise ValueError("bullet index is outside source pattern")
    if not 0 <= ring_index < pattern.count2:
        raise ValueError("ring index is outside source pattern")
    if pattern.mode in (6, 7, 8) and rng is None:
        raise ValueError("random source pattern requires gameplay RNG")

    if pattern.count2 > 1:
        difference = _sub(pattern.speed1, pattern.speed2)
        scaled = _mul(difference, ring_index)
        speed = _sub(
            pattern.speed1,
            _div(scaled, pattern.count2),
        )
    else:
        speed = f32(pattern.speed1)

    angle = f32(0.0)
    if pattern.mode in (0, 1):
        if pattern.count1 & 1:
            angle = _add(
                angle,
                _mul((bullet_index + 1) // 2, pattern.angle_step),
            )
        else:
            angle = _add(
                angle,
                _add(
                    _mul(bullet_index // 2, pattern.angle_step),
                    _mul(pattern.angle_step, 0.5),
                ),
            )
        if bullet_index & 1:
            angle = f32(-angle)
        if pattern.mode == 0:
            angle = _add(angle, pattern.angle_to_player)
        angle = _add(angle, pattern.angle)
    elif pattern.mode in (2, 3):
        if pattern.mode == 2:
            angle = _add(angle, pattern.angle_to_player)
        angle = _add(
            angle,
            _div(_mul(bullet_index, _TWO_PI), pattern.count1),
        )
        angle = _add(
            angle,
            _add(_mul(ring_index, pattern.angle_step), pattern.angle),
        )
    elif pattern.mode in (4, 5):
        if pattern.mode == 4:
            angle = _add(angle, pattern.angle_to_player)
        angle = _add(angle, _div(_PI, pattern.count1))
        angle = _add(
            angle,
            _div(_mul(bullet_index, _TWO_PI), pattern.count1),
        )
        angle = _add(angle, pattern.angle)
    elif pattern.mode == 6:
        assert rng is not None
        angle = _add(
            _mul(rng_next_f32(rng), _sub(pattern.angle, pattern.angle_step)),
            pattern.angle_step,
        )
    elif pattern.mode == 7:
        assert rng is not None
        speed = _add(
            _mul(rng_next_f32(rng), _sub(pattern.speed1, pattern.speed2)),
            pattern.speed2,
        )
        angle = _add(
            angle,
            _div(_mul(bullet_index, _TWO_PI), pattern.count1),
        )
        angle = _add(
            angle,
            _add(_mul(ring_index, pattern.angle_step), pattern.angle),
        )
    elif pattern.mode == 8:
        assert rng is not None
        angle = _add(
            _mul(rng_next_f32(rng), _sub(pattern.angle, pattern.angle_step)),
            pattern.angle_step,
        )
        speed = _add(
            _mul(rng_next_f32(rng), _sub(pattern.speed1, pattern.speed2)),
            pattern.speed2,
        )

    stored_angle = normalize_angle(angle)
    scaled_speed = _mul(speed, pattern.time_scale)
    return SourcePatternSample(
        speed=f32(speed),
        angle=stored_angle,
        # ``FromAngleMagnitude`` receives the unnormalized local angle in the
        # recovered source; sine/cosine are periodic but retaining the same
        # operand matters for very large synthetic angles.
        velocity_x=_mul(_cosf(angle), scaled_speed),
        velocity_y=_mul(_sinf(angle), scaled_speed),
    )


@dataclass(frozen=True)
class Callback12State:
    phase_state: int
    collision_aux: int
    presentation_flags: int
    animation_index: int
    base_speed: float
    base_angle: float
    velocity_x: float
    velocity_y: float


def apply_callback12(
    state: Callback12State,
    *,
    bullet_tags: int,
    selected_tags: int,
    callback_angle: float,
    callback_speed: float,
    time_scale: float,
) -> tuple[Callback12State, bool]:
    if not bullet_tags & selected_tags:
        return state, False
    transition = callback_12_phase_transition(state.phase_state)
    if transition.use_callback_velocity:
        angle = f32(callback_angle)
        speed = _mul(callback_speed, time_scale)
    else:
        angle = f32(state.base_angle)
        speed = _mul(state.base_speed, time_scale)
    return (
        Callback12State(
            phase_state=transition.next_phase_state,
            collision_aux=transition.aux_byte,
            presentation_flags=(
                (state.presentation_flags & 0xFFFFFFCF)
                | transition.presentation_mask
            ),
            animation_index=(
                state.animation_index + transition.animation_delta
            ),
            base_speed=f32(state.base_speed),
            base_angle=f32(state.base_angle),
            velocity_x=_mul(_cosf(angle), speed),
            velocity_y=_mul(_sinf(angle), speed),
        ),
        True,
    )


def aabb_overlap(
    *,
    player_x: float,
    player_y: float,
    player_half_width: float,
    player_half_height: float,
    hazard_x: float,
    hazard_y: float,
    hazard_half_width: float,
    hazard_half_height: float,
) -> bool:
    """Inclusive source AABB test with binary32 boundary arithmetic."""

    return (
        _sub(player_x, player_half_width)
        <= _add(hazard_x, hazard_half_width)
        and _add(player_x, player_half_width)
        >= _sub(hazard_x, hazard_half_width)
        and _sub(player_y, player_half_height)
        <= _add(hazard_y, hazard_half_height)
        and _add(player_y, player_half_height)
        >= _sub(hazard_y, hazard_half_height)
    )


__all__ = [
    "Callback12State",
    "SourcePattern",
    "SourcePatternSample",
    "aabb_overlap",
    "apply_callback12",
    "f32",
    "normalize_angle",
    "pattern_sample",
    "rng_next_f32",
]
