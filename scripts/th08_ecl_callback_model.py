#!/usr/bin/env python3
"""Executable models for TH08 ECL built-in callbacks used by target routes.

Opcode 0x88 invokes an entry immediately. Opcode 0x89 installs the same entry
as an enemy per-frame callback. The table and formulas here were recovered
from the native table referenced at 0x0041D4F4 and its target procedures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CallbackSpec:
    index: int
    address: int
    name: str
    confidence: str = "observed"


CALLBACK_ADDRESSES = (
    0x423390, 0x4233D0, 0x423400, 0x423530, 0x423A60, 0x424130,
    0x424170, 0x4241E0, 0x4244F0, 0x424730, 0x4246E0, 0x424820,
    0x424A20, 0x424E00, 0x424C40, 0x424E20, 0x424E50, 0x424F60,
    0x424F90, 0x424FC0, 0x423DB0, 0x423E20, 0x424FF0, 0x425020,
    0x425040, 0x424910, 0x425070, 0x4250D0, 0x4251B0, 0x425290,
    0x424A00, 0x425390,
)

_TARGET_NAMES = {
    0: "publish_enemy_object_fields_24_56",
    1: "spawn_screen_effect_type_1",
    2: "enemy_reflect_at_playfield_bounds",
    5: "disable_barrier_effect_pair",
    6: "spawn_barrier_effect_pair_type_58",
    7: "update_barrier_portal_center_y_224",
    12: "toggle_tagged_bullet_phase_two_state",
    13: "tint_enemy_object_argb_ffc03030",
    14: "toggle_tagged_bullet_phase_three_state",
    15: "spawn_screen_effect_type_20",
    16: "trigger_linked_enemy_near_flagged_bullet",
    17: "spawn_screen_effect_type_1_alt",
    18: "set_global_time_scale_reciprocal",
    20: "spawn_barrier_effect_pair_type_65",
    21: "update_barrier_portal_center_y_208",
    22: "start_special_spell_ui",
    23: "finish_special_spell_ui",
    24: "copy_global_state_field_1c_to_enemy_object",
    31: "spawn_item_type_3_or_5",
}

CALLBACK_SPECS = tuple(
    CallbackSpec(
        index,
        address,
        _TARGET_NAMES.get(index, f"callback_{index:02d}_unmodeled"),
        "observed" if index in _TARGET_NAMES else "unknown",
    )
    for index, address in enumerate(CALLBACK_ADDRESSES)
)


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class PortalProfile:
    center_x: float
    center_y: float
    inner: Bounds
    current_outer: Bounds
    predicted_outer: Bounds
    shrink_scale: float


REIMU_DANMAKU_BARRIER = PortalProfile(
    center_x=192.0,
    center_y=224.0,
    inner=Bounds(56.235489, 88.235489, 327.76453, 359.76453),
    current_outer=Bounds(-32.0, 0.0, 416.0, 448.0),
    predicted_outer=Bounds(-31.100006, 0.0, 416.0, 448.0),
    shrink_scale=135.76451 / 224.0,
)

REIMU_DOUBLE_BARRIER = PortalProfile(
    center_x=192.0,
    center_y=208.0,
    inner=Bounds(112.80403, 128.80403, 271.19595, 287.19595),
    current_outer=Bounds(33.60807, 49.60807, 350.39194, 366.39194),
    predicted_outer=Bounds(33.60807, 49.60807, 350.39194, 366.39194),
    shrink_scale=79.195969 / 158.39194,
)


@dataclass(frozen=True)
class PortalBullet:
    x: float
    y: float
    vx: float
    vy: float
    angle: float
    portal_cooldown: int = 0


def _region(x: float, y: float, inner: Bounds, outer: Bounds) -> int:
    if inner.left < x < inner.right and inner.top < y < inner.bottom:
        return 0
    if outer.left < x < outer.right and outer.top < y < outer.bottom:
        return 1
    return 2


def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= math.tau
    while angle < -math.pi:
        angle += math.tau
    return angle


def portal_callback_step(
    bullet: PortalBullet, profile: PortalProfile
) -> tuple[PortalBullet, bool]:
    """Apply callback 7/21 to one active bullet for one callback update."""

    if bullet.portal_cooldown:
        return replace(bullet, portal_cooldown=bullet.portal_cooldown - 1), False

    current = _region(
        bullet.x, bullet.y, profile.inner, profile.current_outer
    )
    predicted = _region(
        bullet.x + bullet.vx,
        bullet.y + bullet.vy,
        profile.inner,
        profile.predicted_outer,
    )
    if current == predicted:
        return bullet, False

    scale = (
        profile.shrink_scale
        if current != 0 and predicted != 0
        else 1.0 / profile.shrink_scale
    )
    return (
        PortalBullet(
            x=(bullet.x - profile.center_x) * scale + profile.center_x,
            y=(bullet.y - profile.center_y) * scale + profile.center_y,
            vx=-bullet.vx,
            vy=-bullet.vy,
            angle=_normalize_angle(bullet.angle + math.pi),
            portal_cooldown=2,
        ),
        True,
    )


@dataclass(frozen=True)
class EnemyMotion:
    x: float
    y: float
    vx: float
    vy: float
    angle: float
    flag_10000000: bool = True


def callback_2_enemy_motion(
    motion: EnemyMotion, vertical_acceleration: float, vertical_limit: float
) -> EnemyMotion:
    """Apply target-used callback index 2's bounce/vertical update."""

    vx = motion.vx
    vy = motion.vy
    changed = False
    flag = motion.flag_10000000
    if motion.x <= 0.0 or motion.x >= 384.0:
        vx = -vx
        changed = True
    if vy < vertical_limit:
        vy += vertical_acceleration
        changed = True
    if motion.y < -64.0:
        vy = -vy
        changed = True
    elif motion.y >= 480.0:
        flag = False
    angle = math.atan2(vy, vx) if changed else motion.angle
    return replace(motion, vx=vx, vy=vy, angle=angle, flag_10000000=flag)


@dataclass(frozen=True)
class TaggedBullet:
    active: bool
    tag_flags: int
    phase_state: int
    presentation_flags: int
    animation_index: int
    aux_byte: int
    vx: float
    vy: float
    angle: float
    base_speed: float


@dataclass(frozen=True)
class Callback12PhaseTransition:
    """Source-exact non-geometric state selected by callback 12."""

    next_phase_state: int
    use_callback_velocity: bool
    collision_enabled: bool
    presentation_mask: int
    animation_delta: int
    aux_byte: int


def callback_12_phase_transition(
    phase_state: int,
) -> Callback12PhaseTransition:
    """Return the shared callback-12 transition before velocity evaluation.

    ``EclExIns.cpp`` address 0x424A20 branches only on equality with phase
    state one.  Its +0x10B4 write is gameplay state: ``BulletManager`` skips
    the bullet collision block while that byte is nonzero.
    """

    if phase_state == 1:
        return Callback12PhaseTransition(
            next_phase_state=0,
            use_callback_velocity=True,
            collision_enabled=False,
            presentation_mask=0x10,
            animation_delta=16,
            aux_byte=1,
        )
    return Callback12PhaseTransition(
        next_phase_state=1,
        use_callback_velocity=False,
        collision_enabled=True,
        presentation_mask=0,
        animation_delta=-16,
        aux_byte=0,
    )


def _polar(angle: float, speed: float) -> tuple[float, float]:
    return math.cos(angle) * speed, math.sin(angle) * speed


def callback_12_toggle_tagged_bullet(
    bullet: TaggedBullet,
    tag_mask: int,
    callback_angle: float,
    callback_speed: float,
    time_scale: float,
) -> tuple[TaggedBullet, bool]:
    if not bullet.active or not bullet.tag_flags & tag_mask:
        return bullet, False
    transition = callback_12_phase_transition(bullet.phase_state)
    if transition.use_callback_velocity:
        vx, vy = _polar(callback_angle, callback_speed * time_scale)
    else:
        vx, vy = _polar(bullet.angle, bullet.base_speed * time_scale)
    return (
        replace(
            bullet,
            phase_state=transition.next_phase_state,
            presentation_flags=(
                (bullet.presentation_flags & ~0x30)
                | transition.presentation_mask
            ),
            animation_index=(
                bullet.animation_index + transition.animation_delta
            ),
            aux_byte=transition.aux_byte,
            vx=vx,
            vy=vy,
        ),
        True,
    )


def callback_14_cycle_tagged_bullet(
    bullet: TaggedBullet,
    tag_mask: int,
    callback_speed: float,
    time_scale: float,
) -> tuple[TaggedBullet, str]:
    if not bullet.active or not bullet.tag_flags & tag_mask:
        return bullet, "unchanged"
    if bullet.phase_state == 1:
        vx, vy = _polar(bullet.angle, callback_speed * time_scale)
        return (
            replace(
                bullet,
                phase_state=0,
                presentation_flags=(bullet.presentation_flags & ~0x30) | 0x10,
                animation_index=bullet.animation_index + 16,
                aux_byte=1,
                vx=vx,
                vy=vy,
            ),
            "phase_1_to_0",
        )
    if bullet.phase_state:
        vx, vy = _polar(bullet.angle, bullet.base_speed * time_scale)
        return (
            replace(
                bullet,
                phase_state=1,
                presentation_flags=bullet.presentation_flags & ~0x30,
                animation_index=bullet.animation_index - 16,
                aux_byte=0,
                vx=vx,
                vy=vy,
            ),
            "phase_nonzero_to_1",
        )
    return replace(bullet, phase_state=2), "phase_0_to_2_animation_15"


def callback_16_triggers_linked_enemy(
    bullet_x: float, bullet_y: float, enemy_x: float, enemy_y: float
) -> bool:
    return (bullet_x - enemy_x) ** 2 + (bullet_y - enemy_y) ** 2 < 4096.0


def callback_18_time_scale(divisor: int) -> float:
    return 1.0 / divisor


def callback_31_item_type(global_flag: bool) -> int:
    return 3 if global_flag else 5
