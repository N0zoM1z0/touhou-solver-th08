#!/usr/bin/env python3
"""Executable TH08 player-shot rules recovered from ``th08.exe``.

The model covers the shipped 56-byte SHT shot-record path for callback-0
indices 0 and 7. It is based on
player_emit_shot_level (0x00450F60), player_shot_initialize (0x0044FB70),
player_shot_record_emit_if_due (0x0044FD80), player_update_shots
(0x00451150), player_update_shot_cadence (0x00451500), and
player_compute_damage_to_enemy (0x00451670).

Callback 7 is the narrow random-spread option-shot callback used by the
route-2 secondary normal SHT. Other custom SHT callbacks and enemy-specific
hit callbacks remain outside this module. Random-spread RNG consumption and
stored angle are represented, but native-bit trigonometric geometry remains
outside exact authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from th08_ecl_vm_state import float32_bits, float32_from_bits
from th08_rng import Th08Rng
from th08_sht import ShtFile, ShtLevel, ShtShotRecord


SHOT_CADENCE_LENGTH = 20
PLAYER_SHOT_POOL_SIZE = 128
PLAYER_SHOT_FEEDBACK_INCREMENT_CAP = 50
DEFAULT_SHOT_CALLBACK_INDEX = 0
RANDOM_SPREAD_SHOT_CALLBACK_INDEX = 7
RANDOM_SPREAD_PI_BITS = 0x40490FDB
RANDOM_SPREAD_DIVISOR_BITS = 0x42400000
RANDOM_SPREAD_CENTER_BITS = 0x3FC90FDB
REMILIA_NORMAL_BOMB_LEVEL = 6
REMILIA_LAST_SPELL_LEVEL = 7
PIERCING_SHOT_TYPES = frozenset((4, 5, 6))


class UnsupportedPlayerShotCallback(ValueError):
    """Raised when an SHT callback/collision branch lacks semantics."""


def _stored_float32(value: float) -> float:
    """Round one native memory write to IEEE-754 binary32."""

    return float32_from_bits(float32_bits(value))


@dataclass(frozen=True)
class PlayerShot:
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    angle: float
    hitbox_width: float
    hitbox_height: float
    damage: int
    shot_type: int
    source_index: int
    record_offset: int
    update_callback_index: int = 0
    hit_callback_index: int = 0
    state: int = 1
    active: bool = True


@dataclass(frozen=True)
class PlayerShotLevelSelection:
    profile: str
    sht_sha256: str
    native_power: int
    level: ShtLevel


@dataclass(frozen=True)
class PlayerShotEmission:
    shots: tuple[PlayerShot, ...]
    records_evaluated: int
    free_slots_before: int
    pool_slots_used: int
    stopped_for_pool_capacity: bool
    rng_calls_consumed: int


def remilia_bomb_sht_level(callback_index: int, bomb_frame: int) -> int | None:
    """Return the direct SHT level used by a route-2 Remilia Bomb callback.

    Callback index 1 is the normal Bomb and index 3 is Remilia's Last Spell.
    The special level override is gated until Bomb-local frame 60.
    """

    if callback_index not in (1, 3):
        raise ValueError("Remilia Bomb callback index must be 1 or 3")
    if bomb_frame < 0:
        raise ValueError("Bomb frame cannot be negative")
    if bomb_frame < 60:
        return None
    return (
        REMILIA_LAST_SPELL_LEVEL
        if callback_index & 2
        else REMILIA_NORMAL_BOMB_LEVEL
    )


def select_normal_sht_level(sht: ShtFile, power: float) -> tuple[int, ShtLevel]:
    """Match normal Power-threshold selection at 0x00451015.

    ``get_player_power`` converts the stored float through ``__ftol2`` before
    comparison. Supported gameplay Power is finite, non-negative, and below
    the terminal threshold in the shipped SHT table.
    """

    if not math.isfinite(power) or power < 0.0:
        raise ValueError("player Power must be finite and non-negative")
    native_power = math.trunc(power)
    for level in sht.levels:
        if native_power < level.power_upper_bound:
            return native_power, level
    raise ValueError("player Power reaches no terminal SHT threshold")


def select_player_shot_level(
    primary_sht: ShtFile,
    secondary_sht: ShtFile,
    *,
    focus_logic_value: int,
    power: float,
) -> PlayerShotLevelSelection:
    """Select the active primary/secondary normal SHT level.

    The native selector tests player byte ``+0x03`` directly: zero selects the
    primary SHT, and any nonzero Focus-logic value selects the secondary SHT.
    """

    if not 0 <= focus_logic_value <= 0xFF:
        raise ValueError("Focus-logic value must fit in one byte")
    profile = "secondary" if focus_logic_value else "primary"
    sht = secondary_sht if focus_logic_value else primary_sht
    native_power, level = select_normal_sht_level(sht, power)
    return PlayerShotLevelSelection(
        profile=profile,
        sht_sha256=sht.sha256,
        native_power=native_power,
        level=level,
    )


def shot_record_due(record: ShtShotRecord, cadence_frame: int) -> bool:
    """Match the signed remainder test at 0x0044FD8C.

    The firing timer cycles over integer values 0..19 while shot is held.
    Parsed live records have positive periods and non-negative phases.
    """

    if record.fire_period <= 0:
        raise ValueError("a live SHT shot record must have a positive period")
    if not 0 <= cadence_frame < SHOT_CADENCE_LENGTH:
        raise ValueError("cadence frame must be in [0, 20)")
    return cadence_frame % record.fire_period == record.fire_phase


def due_shot_records(level: ShtLevel, cadence_frame: int) -> tuple[ShtShotRecord, ...]:
    """Return all records emitted for one integer cadence tick."""

    return tuple(
        record for record in level.shots if shot_record_due(record, cadence_frame)
    )


def _source_position(
    source_index: int,
    player_position: tuple[float, float],
    option_positions: Mapping[int, tuple[float, float]]
    | Sequence[tuple[float, float]],
) -> tuple[float, float]:
    if source_index == 0:
        return player_position
    if not 1 <= source_index <= 4:
        raise ValueError("SHT source index must be in [0, 4]")
    try:
        if isinstance(option_positions, Mapping):
            return option_positions[source_index]
        return option_positions[source_index - 1]
    except (IndexError, KeyError) as exc:
        raise ValueError(f"missing option position for source {source_index}") from exc


def spawn_player_shot(
    record: ShtShotRecord,
    *,
    player_position: tuple[float, float],
    option_positions: Mapping[int, tuple[float, float]]
    | Sequence[tuple[float, float]],
    angle_override: float | None = None,
) -> PlayerShot:
    """Initialize the solver-visible fields of one default SHT shot."""

    source_x, source_y = _source_position(
        record.source_index, player_position, option_positions
    )
    angle = record.angle if angle_override is None else angle_override
    if not math.isfinite(angle):
        raise ValueError("player-shot angle must be finite")
    stored_angle = _stored_float32(angle)
    stored_speed = _stored_float32(record.speed)
    return PlayerShot(
        x=_stored_float32(
            _stored_float32(source_x)
            + _stored_float32(record.spawn_offset_x)
        ),
        y=_stored_float32(
            _stored_float32(source_y)
            + _stored_float32(record.spawn_offset_y)
        ),
        velocity_x=_stored_float32(
            math.cos(stored_angle) * stored_speed
        ),
        velocity_y=_stored_float32(
            math.sin(stored_angle) * stored_speed
        ),
        angle=stored_angle,
        hitbox_width=record.hitbox_width,
        hitbox_height=record.hitbox_height,
        damage=record.damage,
        shot_type=record.shot_type,
        source_index=record.source_index,
        record_offset=record.offset,
        update_callback_index=record.callback_1_index,
        hit_callback_index=record.callback_3_index,
    )


def random_spread_shot_angle(rng: Th08Rng) -> float:
    """Return callback 7's stored float32 angle and consume two u16 calls.

    Retail v1.00d ``FUN_004501B0`` calls the signed generator at
    ``0x0043ED80``.  This distinction is observable even though the signed
    and unsigned generators consume the same two words: using the unsigned
    result mirrors the whole spread into the adjacent angular interval.

    The x87 intermediate rounding and the native polar helper have not yet
    received a native-bit differential. The returned binary32 angle is the
    correctly ordered scalar projection of the revalidated formula, while
    velocity geometry remains unknown-direction numerical approximation.
    """

    pi = float32_from_bits(RANDOM_SPREAD_PI_BITS)
    divisor = float32_from_bits(RANDOM_SPREAD_DIVISOR_BITS)
    center = float32_from_bits(RANDOM_SPREAD_CENTER_BITS)
    projected = rng.next_signed_unit() * pi / divisor - center
    return _stored_float32(projected)


def emit_player_shot_level(
    level: ShtLevel,
    *,
    cadence_frame: int,
    player_position: tuple[float, float],
    option_positions: Mapping[int, tuple[float, float]]
    | Sequence[tuple[float, float]],
    free_slots: int,
    rng: Th08Rng,
) -> PlayerShotEmission:
    """Evaluate one selected SHT level in native record/pool order.

    Only the number of free slots affects emission order: every free native
    slot consumes the next due record, while occupied slots do not advance the
    SHT cursor. A full pool evaluates no callback and consumes no RNG.
    """

    if not 0 <= free_slots <= PLAYER_SHOT_POOL_SIZE:
        raise ValueError("free player-shot slots must be in [0, 128]")
    if not 0 <= cadence_frame < SHOT_CADENCE_LENGTH:
        raise ValueError("cadence frame must be in [0, 20)")

    calls_before = rng.calls
    emitted: list[PlayerShot] = []
    records_evaluated = 0
    for record in level.shots:
        if len(emitted) >= free_slots:
            break
        records_evaluated += 1
        callback = record.callback_0_index
        if callback not in (
            DEFAULT_SHOT_CALLBACK_INDEX,
            RANDOM_SPREAD_SHOT_CALLBACK_INDEX,
        ):
            raise UnsupportedPlayerShotCallback(
                f"unsupported callback-0 index {callback} "
                f"at SHT offset {record.offset:#x}"
            )
        if not shot_record_due(record, cadence_frame):
            continue
        angle_override = (
            random_spread_shot_angle(rng)
            if callback == RANDOM_SPREAD_SHOT_CALLBACK_INDEX
            else None
        )
        emitted.append(
            spawn_player_shot(
                record,
                player_position=player_position,
                option_positions=option_positions,
                angle_override=angle_override,
            )
        )

    return PlayerShotEmission(
        shots=tuple(emitted),
        records_evaluated=records_evaluated,
        free_slots_before=free_slots,
        pool_slots_used=len(emitted),
        stopped_for_pool_capacity=(
            len(emitted) >= free_slots and records_evaluated < len(level.shots)
        ),
        rng_calls_consumed=rng.calls - calls_before,
    )


def step_player_shot(shot: PlayerShot, *, time_scale: float = 1.0) -> PlayerShot:
    """Apply the default per-frame position update at 0x00451150."""

    if time_scale < 0.0 or not math.isfinite(time_scale):
        raise ValueError("time scale must be finite and non-negative")
    if not shot.active:
        return shot
    if shot.update_callback_index:
        raise UnsupportedPlayerShotCallback(
            "player-shot update callback "
            f"{shot.update_callback_index} lacks executable semantics"
        )
    stored_scale = _stored_float32(time_scale)
    return replace(
        shot,
        x=_stored_float32(
            _stored_float32(shot.x)
            + _stored_float32(shot.velocity_x) * stored_scale
        ),
        y=_stored_float32(
            _stored_float32(shot.y)
            + _stored_float32(shot.velocity_y) * stored_scale
        ),
    )


def player_shot_overlaps_enemy(
    shot: PlayerShot,
    *,
    enemy_x: float,
    enemy_y: float,
    enemy_width: float,
    enemy_height: float,
    type45_collision_suppressed: bool | None = None,
) -> bool:
    """Use the native pre-gates and inclusive center/size AABB test.

    Active state-1 shots are eligible, as are active type-3 shots in any
    state. Types 4 and 5 additionally depend on the native mode-2 predicate;
    callers must supply it for those types. A nonzero hit callback is invoked
    only after geometric overlap and can veto the hit, so unsupported
    callbacks fail closed at that point.
    """

    if not shot.active or (shot.state != 1 and shot.shot_type != 3):
        return False
    if enemy_width < 0.0 or enemy_height < 0.0:
        raise ValueError("enemy dimensions cannot be negative")
    if shot.shot_type in (4, 5):
        if type45_collision_suppressed is None:
            raise UnsupportedPlayerShotCallback(
                "shot types 4/5 require the native mode-2 collision predicate"
            )
        if type45_collision_suppressed:
            return False
    overlaps = (
        shot.x + shot.hitbox_width / 2.0
        >= enemy_x - enemy_width / 2.0
        and shot.x - shot.hitbox_width / 2.0
        <= enemy_x + enemy_width / 2.0
        and shot.y + shot.hitbox_height / 2.0
        >= enemy_y - enemy_height / 2.0
        and shot.y - shot.hitbox_height / 2.0
        <= enemy_y + enemy_height / 2.0
    )
    if overlaps and shot.hit_callback_index:
        raise UnsupportedPlayerShotCallback(
            "player-shot hit callback "
            f"{shot.hit_callback_index} lacks executable semantics"
        )
    return overlaps


def shot_damage_contribution(base_damage: int, *, bomb_active: bool) -> int:
    """Apply the active-Bomb damage divisor used by ordinary shot slots."""

    if base_damage < 0:
        raise ValueError("shot damage cannot be negative")
    if not bomb_active:
        return base_damage
    return max(base_damage // 5, 1)


def resolve_default_shot_damage(
    shots: Sequence[PlayerShot],
    *,
    enemy_x: float,
    enemy_y: float,
    enemy_width: float,
    enemy_height: float,
    bomb_active: bool,
    type45_collision_suppressed: bool | None = None,
) -> tuple[tuple[PlayerShot, ...], int]:
    """Resolve one enemy collision pass and return the uncapped damage subtotal.

    Shot types 4, 5, and 6 remain active after a hit. Other default shot types
    enter hit state 2 and have velocity divided by 8. Enemy-specific hit
    callbacks can override this path and are intentionally not modeled here.

    The native `min(total, 50)` at 0x0045199F limits only the increment applied
    to the enemy's hit-feedback accumulator at +0x2E10.  It does not replace
    the damage accumulator returned to `enemy_manager_update`.
    """

    updated: list[PlayerShot] = []
    total = 0
    for shot in shots:
        if not player_shot_overlaps_enemy(
            shot,
            enemy_x=enemy_x,
            enemy_y=enemy_y,
            enemy_width=enemy_width,
            enemy_height=enemy_height,
            type45_collision_suppressed=type45_collision_suppressed,
        ):
            updated.append(shot)
            continue
        total += shot_damage_contribution(shot.damage, bomb_active=bomb_active)
        if shot.shot_type in PIERCING_SHOT_TYPES:
            updated.append(shot)
        else:
            updated.append(
                replace(
                    shot,
                    state=2,
                    velocity_x=(
                        shot.velocity_x
                        if shot.shot_type == 3
                        else shot.velocity_x / 8.0
                    ),
                    velocity_y=(
                        shot.velocity_y
                        if shot.shot_type == 3
                        else shot.velocity_y / 8.0
                    ),
                )
            )
    return tuple(updated), total


def player_shot_feedback_increment(damage_subtotal: int) -> int:
    """Return the capped +0x2E10 feedback-meter increment for one pass."""

    return min(damage_subtotal, PLAYER_SHOT_FEEDBACK_INCREMENT_CAP)
