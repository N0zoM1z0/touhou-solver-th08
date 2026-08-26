"""Exact-root TH08 player-shot and enemy-damage combat projection.

This module decodes combat state already retained by the rolling native-root
capture.  It does not install a probe or grant predictive/live authority.
The pass projection is deliberately narrow: only ordinary shot slots whose
native type gate and hit callback are fully supported contribute a numeric
subtotal.  Callback-dependent and type-4/5 overlaps remain explicit unknowns.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, replace
from typing import Any, Iterable

from th08_attack_model import (
    AttackRegion,
    apply_damage_region,
    damage_region_overlaps_enemy,
)
from th08_enemy_damage_model import (
    EnemyPlayerShotDamageContext,
    EnemyResolvedDamageContext,
    evaluate_enemy_player_shot_damage_gate,
    resolve_enemy_hp_damage,
)
from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_MANAGER_SCANNED_SLOT_COUNT,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
)
from th08_runtime.game_state import (
    ADDR_PLAYER,
    ADDR_SPELL_CARD_STATE,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_DAMAGE_TIMER_OFFSET,
    PLAYER_SHOT_POOL_OFFSET,
    PLAYER_SHOT_POOL_SIZE,
    PLAYER_SHOT_SLOT_ANGLE_OFFSET,
    PLAYER_SHOT_SLOT_ANM_INDEX_OFFSET,
    PLAYER_SHOT_SLOT_DAMAGE_OFFSET,
    PLAYER_SHOT_SLOT_FOCUS_OFFSET,
    PLAYER_SHOT_SLOT_HITBOX_OFFSET,
    PLAYER_SHOT_SLOT_HIT_CALLBACK_OFFSET,
    PLAYER_SHOT_SLOT_POSITION_OFFSET,
    PLAYER_SHOT_SLOT_SOURCE_RECORD_OFFSET,
    PLAYER_SHOT_SLOT_SPEED_OFFSET,
    PLAYER_SHOT_SLOT_STATE_OFFSET,
    PLAYER_SHOT_SLOT_STRIDE,
    PLAYER_SHOT_SLOT_TIMER_OFFSET,
    PLAYER_SHOT_SLOT_TYPE_OFFSET,
    PLAYER_SHOT_SLOT_UPDATE_CALLBACK_OFFSET,
    PLAYER_SHOT_SLOT_VELOCITY_OFFSET,
    PLAYER_SHOT_TIMER_OFFSET,
    SPELL_STATE_CAPTURE_SIZE,
)
from th08_runtime.route2_sht_provenance import (
    capture_loaded_route2_sht_state,
)
from th08_runtime.sensing import decode_spell_state


NATIVE_COMBAT_PROJECTION_SCHEMA = "th08-native-combat-root-projection-v8"
PLAYER_SHOT_COMBAT_STATE_SCHEMA = "th08-player-shot-combat-state-v1"
PLAYER_DAMAGE_REGION_STATE_SCHEMA = "th08-player-damage-region-state-v1"
ENEMY_DAMAGE_TARGET_STATE_SCHEMA = "th08-enemy-damage-target-state-v2"
SUPPORTED_SHOT_PASS_SCHEMA = "th08-supported-ordinary-shot-pass-v2"
SUPPORTED_DAMAGE_REGION_PASS_SCHEMA = "th08-supported-damage-region-pass-v1"

TH08_TIMER_SIZE = 12
PLAYER_SHOT_POOL_BYTES = PLAYER_SHOT_POOL_SIZE * PLAYER_SHOT_SLOT_STRIDE
PLAYER_SHOT_FEEDBACK_INCREMENT_CAP = 50
PIERCING_SHOT_TYPES = frozenset((4, 5, 6))
PLAYER_DAMAGE_REGION_POOL_OFFSET = 0xB8834
PLAYER_DAMAGE_REGION_POOL_SIZE = 192
PLAYER_DAMAGE_REGION_SLOT_STRIDE = 0x40
PLAYER_DAMAGE_REGION_POOL_BYTES = (
    PLAYER_DAMAGE_REGION_POOL_SIZE * PLAYER_DAMAGE_REGION_SLOT_STRIDE
)

ENEMY_DAMAGE_HITBOX_OFFSET = 0x2D70
ENEMY_ALTERNATE_HITBOX_OFFSET = 0x2D7C
ENEMY_POSITION_OFFSET = 0x2D88
ENEMY_HITPOINTS_OFFSET = 0x2DFC
ENEMY_MAX_HITPOINTS_OFFSET = 0x2E00
ENEMY_MAIN_VM_OFFSET = 0x7F8
ENEMY_MAIN_VM_TIMER_CURRENT_OFFSET = ENEMY_MAIN_VM_OFFSET + 0x0C
ENEMY_FLAGS2_OFFSET = 0x3328
ENEMY_FRAME_DAMAGE_OFFSET = 0x3354
ENEMY_SPECIAL_DAMAGE_BLOCKER_OFFSET = 0x2DA4
ENEMY_POST_DAMAGE_TIMER_CURRENT_OFFSET = 0x535C
ENEMY_CAUSAL_TAIL_OFFSET = 0x7F8
ADDR_GLOBAL_DAMAGE_MODE_FLAGS = 0x004EA670
ADDR_ROUTE_ID = 0x0164D0B1
ADDR_GLOBAL_MODE_MANAGER = 0x0160F508
GLOBAL_MODE_STATE_POINTER_OFFSET = 0x08
GLOBAL_MODE_STATE_VALUE_OFFSET = 0x22
GLOBAL_PLAYER_DAMAGE_BONUS_THRESHOLD_OFFSET = 0x3DDFE

_ENEMY_COMPONENT_NAME = "ordinary_enemy_template_and_pool"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(value: object) -> str:
    return _sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


def _read_exact(reader: Any, address: int, size: int, *, field: str) -> bytes:
    data = reader.read(address, size)
    if len(data) != size:
        raise ValueError(
            f"short {field} read at {address:#x}: "
            f"expected {size:#x}, received {len(data):#x}"
        )
    return data


@dataclass(frozen=True)
class Th08TimerIdentity:
    previous: int
    fraction_bits: int
    current: int

    @classmethod
    def decode(cls, data: bytes) -> Th08TimerIdentity:
        if len(data) != TH08_TIMER_SIZE:
            raise ValueError("TH08 timer identity requires 12 exact bytes")
        return cls(*struct.unpack("<iIi", data))

    @property
    def integer_changed(self) -> bool:
        return self.previous != self.current

    def record(self) -> dict[str, object]:
        return {
            "previous": self.previous,
            "fraction_bits": self.fraction_bits,
            "current": self.current,
            "integer_changed": self.integer_changed,
        }


@dataclass(frozen=True)
class PlayerDamageRegionSlot:
    slot: int
    region: AttackRegion
    suppress_hit_effect: bool
    raw_sha256: str

    def __post_init__(self) -> None:
        if not 0 <= self.slot < PLAYER_DAMAGE_REGION_POOL_SIZE:
            raise ValueError("damage-region slot is outside the native pool")
        if self.region.active:
            geometry = (
                self.region.center_x,
                self.region.center_y,
                self.region.radius,
                self.region.radius_delta,
                self.region.width,
                self.region.height,
                self.region.width_delta,
                self.region.height_delta,
                self.region.angle,
            )
            if not all(math.isfinite(value) for value in geometry):
                raise ValueError(
                    f"active damage-region slot {self.slot} is not finite"
                )
            if self.region.tick_interval <= 0:
                raise ValueError(
                    f"active damage-region slot {self.slot} has invalid "
                    f"tick interval {self.region.tick_interval}"
                )
            if (
                self.region.damage < 0
                or self.region.accumulated < 0
                or self.region.damage_cap < 0
            ):
                raise ValueError(
                    f"active damage-region slot {self.slot} has unsupported "
                    "negative damage accounting"
                )
            if (
                self.region.damage_cap > 0
                and self.region.accumulated >= self.region.damage_cap
                and self.region.damage != 0
            ):
                raise ValueError(
                    f"active damage-region slot {self.slot} violates the "
                    "native exhausted-cap invariant"
                )

    def record(self) -> dict[str, object]:
        region = self.region
        return {
            "slot": self.slot,
            "center": [region.center_x, region.center_y],
            "radius": region.radius,
            "radius_delta": region.radius_delta,
            "size": [region.width, region.height],
            "size_delta": [region.width_delta, region.height_delta],
            "angle": region.angle,
            "frames_remaining": region.frames_remaining,
            "cancel_code": region.cancel_code,
            "damage": region.damage,
            "accumulated_damage": region.accumulated,
            "damage_cap": region.damage_cap,
            "tick_interval": region.tick_interval,
            "active": region.active,
            "suppress_hit_effect": self.suppress_hit_effect,
            "raw_sha256": self.raw_sha256,
        }


@dataclass(frozen=True)
class PlayerDamageRegionState:
    pool_sha256: str
    slots: tuple[PlayerDamageRegionSlot, ...]

    def record(self) -> dict[str, object]:
        return {
            "schema": PLAYER_DAMAGE_REGION_STATE_SCHEMA,
            "pool": {
                "address": ADDR_PLAYER + PLAYER_DAMAGE_REGION_POOL_OFFSET,
                "slot_count": PLAYER_DAMAGE_REGION_POOL_SIZE,
                "slot_stride": PLAYER_DAMAGE_REGION_SLOT_STRIDE,
                "bytes": PLAYER_DAMAGE_REGION_POOL_BYTES,
                "sha256": self.pool_sha256,
                "active_count": len(self.slots),
                "active_slots": [slot.record() for slot in self.slots],
            },
        }


def decode_player_damage_region_pool(
    data: bytes,
) -> tuple[PlayerDamageRegionSlot, ...]:
    if len(data) != PLAYER_DAMAGE_REGION_POOL_BYTES:
        raise ValueError(
            "player damage-region pool requires "
            f"{PLAYER_DAMAGE_REGION_POOL_BYTES:#x} exact bytes"
        )
    slots = []
    for slot in range(PLAYER_DAMAGE_REGION_POOL_SIZE):
        offset = slot * PLAYER_DAMAGE_REGION_SLOT_STRIDE
        raw = data[offset : offset + PLAYER_DAMAGE_REGION_SLOT_STRIDE]
        active = bool(raw[0x3C])
        if not active:
            continue
        (
            center_x,
            center_y,
            radius,
            radius_delta,
            width,
            height,
            width_delta,
            height_delta,
            angle,
        ) = struct.unpack_from("<fffffffff", raw)
        (
            frames_remaining,
            cancel_code,
            damage,
            accumulated,
            damage_cap,
            tick_interval,
        ) = struct.unpack_from("<iiiiii", raw, 0x24)
        slots.append(
            PlayerDamageRegionSlot(
                slot=slot,
                region=AttackRegion(
                    center_x=center_x,
                    center_y=center_y,
                    radius=radius,
                    radius_delta=radius_delta,
                    width=width,
                    height=height,
                    width_delta=width_delta,
                    height_delta=height_delta,
                    angle=angle,
                    frames_remaining=frames_remaining,
                    cancel_code=cancel_code,
                    damage=damage,
                    accumulated=accumulated,
                    damage_cap=damage_cap,
                    tick_interval=tick_interval,
                    active=True,
                ),
                suppress_hit_effect=bool(raw[0x3D]),
                raw_sha256=_sha256(raw),
            )
        )
    return tuple(slots)


def capture_player_damage_region_state(
    reader: Any,
) -> PlayerDamageRegionState:
    data = _read_exact(
        reader,
        ADDR_PLAYER + PLAYER_DAMAGE_REGION_POOL_OFFSET,
        PLAYER_DAMAGE_REGION_POOL_BYTES,
        field="player damage-region pool",
    )
    return PlayerDamageRegionState(
        pool_sha256=_sha256(data),
        slots=decode_player_damage_region_pool(data),
    )


@dataclass(frozen=True)
class PlayerShotCombatSlot:
    slot: int
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    hitbox_width: float
    hitbox_height: float
    speed: float
    angle: float
    timer: Th08TimerIdentity
    damage: int
    state: int
    shot_type: int
    focus_logic_at_birth: int
    anm_index: int
    update_callback_pointer: int
    hit_callback_pointer: int
    source_record_pointer: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if not 0 <= self.slot < PLAYER_SHOT_POOL_SIZE:
            raise ValueError("player-shot slot index is outside the native pool")
        if self.state == 0:
            raise ValueError("combat slot cannot represent an inactive shot")
        if not all(
            math.isfinite(value)
            for value in (
                self.x,
                self.y,
                self.velocity_x,
                self.velocity_y,
                self.hitbox_width,
                self.hitbox_height,
                self.speed,
                self.angle,
            )
        ):
            raise ValueError("active player-shot geometry is not finite")
        if self.hitbox_width < 0.0 or self.hitbox_height < 0.0:
            raise ValueError("active player-shot hitbox is negative")
        if self.damage < 0:
            raise ValueError("active player-shot damage is negative")
        if not 0 <= self.focus_logic_at_birth <= 0xFF:
            raise ValueError("player-shot Focus byte is invalid")
        for pointer in (
            self.update_callback_pointer,
            self.hit_callback_pointer,
            self.source_record_pointer,
        ):
            if not 0 <= pointer <= 0xFFFFFFFF:
                raise ValueError("player-shot pointer is outside uint32")
        if len(self.raw_sha256) != 64:
            raise ValueError("player-shot raw identity is not SHA-256")

    @property
    def damage_loop_eligible(self) -> bool:
        return self.state != 0 and (self.state == 1 or self.shot_type == 3)

    @property
    def route2_normal_damage_path_compatible(self) -> bool:
        return (
            self.shot_type == 0
            and self.update_callback_pointer == 0
            and self.hit_callback_pointer == 0
        )

    def record(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "position": {"x": self.x, "y": self.y},
            "velocity": {"x": self.velocity_x, "y": self.velocity_y},
            "hitbox": {
                "width": self.hitbox_width,
                "height": self.hitbox_height,
            },
            "speed": self.speed,
            "angle": self.angle,
            "timer": self.timer.record(),
            "damage": self.damage,
            "state": self.state,
            "type": self.shot_type,
            "focus_logic_at_birth": self.focus_logic_at_birth,
            "anm_index": self.anm_index,
            "update_callback_pointer": self.update_callback_pointer,
            "hit_callback_pointer": self.hit_callback_pointer,
            "source_record_pointer": self.source_record_pointer,
            "damage_loop_eligible": self.damage_loop_eligible,
            "route2_normal_damage_path_compatible": (
                self.route2_normal_damage_path_compatible
            ),
            "raw_sha256": self.raw_sha256,
        }


def decode_player_shot_pool(data: bytes) -> tuple[PlayerShotCombatSlot, ...]:
    """Decode all active native player-shot slots from one exact pool image."""

    if len(data) != PLAYER_SHOT_POOL_BYTES:
        raise ValueError(
            "player-shot combat pool requires "
            f"{PLAYER_SHOT_POOL_BYTES:#x} exact bytes"
        )
    slots: list[PlayerShotCombatSlot] = []
    for slot in range(PLAYER_SHOT_POOL_SIZE):
        base = slot * PLAYER_SHOT_SLOT_STRIDE
        state = struct.unpack_from(
            "<h",
            data,
            base + PLAYER_SHOT_SLOT_STATE_OFFSET,
        )[0]
        if state == 0:
            continue
        x, y = struct.unpack_from(
            "<ff",
            data,
            base + PLAYER_SHOT_SLOT_POSITION_OFFSET,
        )
        hitbox_width, hitbox_height = struct.unpack_from(
            "<ff",
            data,
            base + PLAYER_SHOT_SLOT_HITBOX_OFFSET,
        )
        velocity_x, velocity_y = struct.unpack_from(
            "<ff",
            data,
            base + PLAYER_SHOT_SLOT_VELOCITY_OFFSET,
        )
        speed = struct.unpack_from(
            "<f",
            data,
            base + PLAYER_SHOT_SLOT_SPEED_OFFSET,
        )[0]
        angle = struct.unpack_from(
            "<f",
            data,
            base + PLAYER_SHOT_SLOT_ANGLE_OFFSET,
        )[0]
        slots.append(
            PlayerShotCombatSlot(
                slot=slot,
                x=x,
                y=y,
                velocity_x=velocity_x,
                velocity_y=velocity_y,
                hitbox_width=hitbox_width,
                hitbox_height=hitbox_height,
                speed=speed,
                angle=angle,
                timer=Th08TimerIdentity.decode(
                    data[
                        base + PLAYER_SHOT_SLOT_TIMER_OFFSET :
                        base + PLAYER_SHOT_SLOT_TIMER_OFFSET + TH08_TIMER_SIZE
                    ]
                ),
                damage=struct.unpack_from(
                    "<h",
                    data,
                    base + PLAYER_SHOT_SLOT_DAMAGE_OFFSET,
                )[0],
                state=state,
                shot_type=struct.unpack_from(
                    "<h",
                    data,
                    base + PLAYER_SHOT_SLOT_TYPE_OFFSET,
                )[0],
                focus_logic_at_birth=data[
                    base + PLAYER_SHOT_SLOT_FOCUS_OFFSET
                ],
                anm_index=struct.unpack_from(
                    "<h",
                    data,
                    base + PLAYER_SHOT_SLOT_ANM_INDEX_OFFSET,
                )[0],
                update_callback_pointer=struct.unpack_from(
                    "<I",
                    data,
                    base + PLAYER_SHOT_SLOT_UPDATE_CALLBACK_OFFSET,
                )[0],
                hit_callback_pointer=struct.unpack_from(
                    "<I",
                    data,
                    base + PLAYER_SHOT_SLOT_HIT_CALLBACK_OFFSET,
                )[0],
                source_record_pointer=struct.unpack_from(
                    "<I",
                    data,
                    base + PLAYER_SHOT_SLOT_SOURCE_RECORD_OFFSET,
                )[0],
                raw_sha256=_sha256(data[base : base + PLAYER_SHOT_SLOT_STRIDE]),
            )
        )
    return tuple(slots)


@dataclass(frozen=True)
class PlayerShotCombatState:
    emission_timer: Th08TimerIdentity
    damage_timer: Th08TimerIdentity
    pool_sha256: str
    slots: tuple[PlayerShotCombatSlot, ...]

    @property
    def occupied_slot_indices(self) -> tuple[int, ...]:
        return tuple(slot.slot for slot in self.slots)

    @property
    def damage_eligible_slot_indices(self) -> tuple[int, ...]:
        return tuple(
            slot.slot for slot in self.slots if slot.damage_loop_eligible
        )

    def record(self) -> dict[str, object]:
        return {
            "schema": PLAYER_SHOT_COMBAT_STATE_SCHEMA,
            "emission_timer": self.emission_timer.record(),
            "damage_timer": self.damage_timer.record(),
            "pool": {
                "slot_count": PLAYER_SHOT_POOL_SIZE,
                "occupied_count": len(self.slots),
                "free_count": PLAYER_SHOT_POOL_SIZE - len(self.slots),
                "occupied_slot_indices": list(self.occupied_slot_indices),
                "damage_eligible_slot_indices": list(
                    self.damage_eligible_slot_indices
                ),
                "sha256": self.pool_sha256,
                "active_slots": [slot.record() for slot in self.slots],
            },
        }


def capture_player_shot_combat_state(reader: Any) -> PlayerShotCombatState:
    """Read both player timers and the complete 128-slot shot pool."""

    pool = _read_exact(
        reader,
        ADDR_PLAYER + PLAYER_SHOT_POOL_OFFSET,
        PLAYER_SHOT_POOL_BYTES,
        field="player-shot combat pool",
    )
    emission_timer = Th08TimerIdentity.decode(
        _read_exact(
            reader,
            ADDR_PLAYER + PLAYER_SHOT_TIMER_OFFSET,
            TH08_TIMER_SIZE,
            field="player-shot emission timer",
        )
    )
    damage_timer = Th08TimerIdentity.decode(
        _read_exact(
            reader,
            ADDR_PLAYER + PLAYER_DAMAGE_TIMER_OFFSET,
            TH08_TIMER_SIZE,
            field="player-shot damage timer",
        )
    )
    return PlayerShotCombatState(
        emission_timer=emission_timer,
        damage_timer=damage_timer,
        pool_sha256=_sha256(pool),
        slots=decode_player_shot_pool(pool),
    )


@dataclass(frozen=True)
class EnemyDamageTarget:
    slot: int
    enemy_pointer: int
    hitpoints: int
    maximum_hitpoints: int
    frame_damage: int
    flags: int
    flags2: int
    x: float
    y: float
    primary_width: float
    primary_height: float
    alternate_width: float
    alternate_height: float
    main_vm_pc: int
    main_vm_timer_current: int
    special_damage_blocker: int
    post_damage_timer_current: int
    causal_tail_sha256: str

    def __post_init__(self) -> None:
        if not 0 <= self.slot < ENEMY_MANAGER_SCANNED_SLOT_COUNT:
            raise ValueError("enemy damage target slot is outside manager scan")
        if (
            self.enemy_pointer
            != ENEMY_SLOT_ZERO_BASE + self.slot * ENEMY_STRIDE
        ):
            raise ValueError("enemy damage target pointer/slot disagree")
        if not self.flags & ENEMY_ACTIVE_FLAG:
            raise ValueError("enemy damage target is inactive")
        if not all(
            math.isfinite(value)
            for value in (
                self.x,
                self.y,
                self.primary_width,
                self.primary_height,
                self.alternate_width,
                self.alternate_height,
            )
        ):
            raise ValueError("enemy damage target geometry is not finite")
        if self.primary_width < 0.0 or self.primary_height < 0.0:
            raise ValueError("enemy primary damage hitbox is negative")
        if self.alternate_width > 0.0 and self.alternate_height < 0.0:
            raise ValueError("enabled enemy alternate damage hitbox is negative")
        if len(self.causal_tail_sha256) != 64:
            raise ValueError("enemy causal-tail identity is not SHA-256")

    @property
    def alternate_enabled(self) -> bool:
        # 0x42D0EE..0x42D0FF enters the second native damage pass only for
        # ordered alternate width > +0.0; negative zero and NaN do not enter.
        return self.alternate_width > 0.0

    def record(self) -> dict[str, object]:
        return {
            "schema": ENEMY_DAMAGE_TARGET_STATE_SCHEMA,
            "slot": self.slot,
            "enemy_pointer": self.enemy_pointer,
            "hitpoints": self.hitpoints,
            "maximum_hitpoints": self.maximum_hitpoints,
            "frame_damage": self.frame_damage,
            "flags": self.flags,
            "flags2": self.flags2,
            "position": {"x": self.x, "y": self.y},
            "primary_hitbox": {
                "width": self.primary_width,
                "height": self.primary_height,
            },
            "alternate_hitbox": {
                "width": self.alternate_width,
                "height": self.alternate_height,
                "enabled": self.alternate_enabled,
            },
            "main_vm_pc": self.main_vm_pc,
            "main_vm_timer_current": self.main_vm_timer_current,
            "special_damage_blocker": self.special_damage_blocker,
            "post_damage_timer_current": self.post_damage_timer_current,
            "causal_tail_sha256": self.causal_tail_sha256,
        }


def _native_component(
    native_root_projection: object,
    name: str,
) -> object:
    matches = tuple(
        component
        for component in getattr(native_root_projection, "components")
        if getattr(getattr(component, "spec"), "name") == name
    )
    if len(matches) != 1:
        raise ValueError(f"native combat projection requires one {name!r}")
    return matches[0]


def decode_enemy_damage_targets(
    native_root_projection: object,
) -> tuple[EnemyDamageTarget, ...]:
    """Decode active targets from the already-retained template+pool bytes."""

    component = _native_component(
        native_root_projection,
        _ENEMY_COMPONENT_NAME,
    )
    spec = getattr(component, "spec")
    data = bytes(getattr(component, "data"))
    expected_pool_size = ENEMY_MANAGER_SCANNED_SLOT_COUNT * ENEMY_STRIDE
    if (
        int(getattr(spec, "address")) == ENEMY_SLOT_ZERO_BASE
        and len(data) in (expected_pool_size, expected_pool_size + ENEMY_STRIDE)
    ):
        pool_offset = 0
    else:
        raise ValueError(
            "native combat requires the source-authoritative manager scan "
            "beginning at enemy slot zero; the legacy slot-1 pool omits an "
            "executable target"
        )

    targets: list[EnemyDamageTarget] = []
    for slot in range(ENEMY_MANAGER_SCANNED_SLOT_COUNT):
        base = pool_offset + slot * ENEMY_STRIDE
        flags = struct.unpack_from("<I", data, base + ENEMY_FLAGS_OFFSET)[0]
        if not flags & ENEMY_ACTIVE_FLAG:
            continue
        x, y = struct.unpack_from("<ff", data, base + ENEMY_POSITION_OFFSET)
        primary_width, primary_height = struct.unpack_from(
            "<ff",
            data,
            base + ENEMY_DAMAGE_HITBOX_OFFSET,
        )
        alternate_width, alternate_height = struct.unpack_from(
            "<ff",
            data,
            base + ENEMY_ALTERNATE_HITBOX_OFFSET,
        )
        targets.append(
            EnemyDamageTarget(
                slot=slot,
                enemy_pointer=ENEMY_SLOT_ZERO_BASE + slot * ENEMY_STRIDE,
                hitpoints=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_HITPOINTS_OFFSET,
                )[0],
                maximum_hitpoints=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_MAX_HITPOINTS_OFFSET,
                )[0],
                frame_damage=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_FRAME_DAMAGE_OFFSET,
                )[0],
                flags=flags,
                flags2=struct.unpack_from(
                    "<I",
                    data,
                    base + ENEMY_FLAGS2_OFFSET,
                )[0],
                x=x,
                y=y,
                primary_width=primary_width,
                primary_height=primary_height,
                alternate_width=alternate_width,
                alternate_height=alternate_height,
                main_vm_pc=struct.unpack_from(
                    "<I",
                    data,
                    base + ENEMY_MAIN_VM_OFFSET,
                )[0],
                main_vm_timer_current=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_MAIN_VM_TIMER_CURRENT_OFFSET,
                )[0],
                special_damage_blocker=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_SPECIAL_DAMAGE_BLOCKER_OFFSET,
                )[0],
                post_damage_timer_current=struct.unpack_from(
                    "<i",
                    data,
                    base + ENEMY_POST_DAMAGE_TIMER_CURRENT_OFFSET,
                )[0],
                causal_tail_sha256=_sha256(
                    data[
                        base + ENEMY_CAUSAL_TAIL_OFFSET :
                        base + ENEMY_STRIDE
                    ]
                ),
            )
        )
    return tuple(targets)


def _overlaps(
    shot: PlayerShotCombatSlot,
    target: EnemyDamageTarget,
    *,
    width: float,
    height: float,
) -> bool:
    return (
        shot.x + shot.hitbox_width / 2.0 >= target.x - width / 2.0
        and shot.x - shot.hitbox_width / 2.0 <= target.x + width / 2.0
        and shot.y + shot.hitbox_height / 2.0 >= target.y - height / 2.0
        and shot.y - shot.hitbox_height / 2.0 <= target.y + height / 2.0
    )


def _shot_contribution(shot: PlayerShotCombatSlot, *, bomb_active: bool) -> int:
    if not bomb_active:
        return shot.damage
    return max(shot.damage // 5, 1)


def _supported_shot_pass(
    slots: Iterable[PlayerShotCombatSlot],
    target: EnemyDamageTarget,
    *,
    width: float,
    height: float,
    bomb_active: bool,
    pass_name: str,
) -> tuple[dict[str, object], tuple[PlayerShotCombatSlot, ...]]:
    supported_hits: list[int] = []
    callback_unknown: list[int] = []
    type45_unknown: list[int] = []
    contribution = 0
    updated: list[PlayerShotCombatSlot] = []
    for shot in slots:
        if (
            not shot.damage_loop_eligible
            or not _overlaps(shot, target, width=width, height=height)
        ):
            updated.append(shot)
            continue
        if shot.shot_type in (4, 5):
            type45_unknown.append(shot.slot)
            updated.append(shot)
            continue
        if shot.hit_callback_pointer:
            callback_unknown.append(shot.slot)
            updated.append(shot)
            continue
        supported_hits.append(shot.slot)
        contribution += _shot_contribution(shot, bomb_active=bomb_active)
        if shot.shot_type in PIERCING_SHOT_TYPES:
            updated.append(shot)
        else:
            updated.append(replace(shot, state=2))
    feedback_increment = min(
        contribution,
        PLAYER_SHOT_FEEDBACK_INCREMENT_CAP,
    )
    return (
        {
            "schema": SUPPORTED_SHOT_PASS_SCHEMA,
            "pass": pass_name,
            "hitbox": {"width": width, "height": height},
            "supported_hit_slots": supported_hits,
            "callback_dependent_overlap_slots": callback_unknown,
            "type45_mode_dependent_overlap_slots": type45_unknown,
            "supported_return_damage_subtotal": contribution,
            "supported_feedback_accumulator_increment": feedback_increment,
            "feedback_accumulator_increment_cap": (
                PLAYER_SHOT_FEEDBACK_INCREMENT_CAP
            ),
            "numeric_authority": (
                "supported_uncapped_return_subtotal_only_before_attack_regions_"
                "alternate_scaling_spell_boss_and_hp_write"
            ),
        },
        tuple(updated),
    )


def _supported_damage_region_pass(
    slots: Iterable[PlayerDamageRegionSlot],
    target: EnemyDamageTarget,
    *,
    width: float,
    height: float,
    bomb_active: bool,
    pass_name: str,
) -> tuple[
    dict[str, object],
    tuple[PlayerDamageRegionSlot, ...],
]:
    hit_slots = []
    contribution = 0
    bomb_overlap = False
    updated = []
    for slot in slots:
        hit = (
            slot.region.active
            and slot.region.frames_remaining % slot.region.tick_interval == 0
            and damage_region_overlaps_enemy(
                slot.region,
                enemy_x=target.x,
                enemy_y=target.y,
                enemy_width=width,
                enemy_height=height,
            )
        )
        next_region, slot_contribution = apply_damage_region(
            slot.region,
            enemy_x=target.x,
            enemy_y=target.y,
            enemy_width=width,
            enemy_height=height,
        )
        updated.append(replace(slot, region=next_region))
        if not hit:
            continue
        hit_slots.append(slot.slot)
        contribution += slot_contribution
        bomb_overlap = bomb_overlap or bomb_active
    return (
        {
            "schema": SUPPORTED_DAMAGE_REGION_PASS_SCHEMA,
            "pass": pass_name,
            "hitbox": {"width": width, "height": height},
            "hit_slots": hit_slots,
            "return_damage_contribution": contribution,
            "bomb_region_overlap_signal": bomb_overlap,
            "numeric_authority": (
                "manager_ordered_supported_active_due_overlap_and_per_region_"
                "cap_before_late_enemy_scaling"
            ),
        },
        tuple(updated),
    )


def _target_combat_record(
    target: EnemyDamageTarget,
    shot_state: PlayerShotCombatState,
    shot_slots: tuple[PlayerShotCombatSlot, ...],
    damage_region_slots: tuple[PlayerDamageRegionSlot, ...],
    *,
    bomb_active: bool,
    player_state: int,
    spell_active: bool,
    spell_enemy_pointer: int,
    route_id: int,
    global_damage_mode_flags: int,
    player_damage_bonus_active: bool,
) -> tuple[
    dict[str, object],
    tuple[PlayerShotCombatSlot, ...],
    tuple[PlayerDamageRegionSlot, ...],
]:
    gate = evaluate_enemy_player_shot_damage_gate(
        EnemyPlayerShotDamageContext(
            flags=target.flags,
            flags2=target.flags2,
            bomb_active=bomb_active,
            player_transition_state=player_state,
            damage_tick_due=shot_state.damage_timer.integer_changed,
            spell_active=spell_active,
            active_spell_owner=(
                spell_active and target.enemy_pointer == spell_enemy_pointer
            ),
        )
    )
    if gate.shot_collision_open:
        primary, after_primary = _supported_shot_pass(
            shot_slots,
            target,
            width=target.primary_width,
            height=target.primary_height,
            bomb_active=bomb_active,
            pass_name="primary",
        )
        primary_regions, after_primary_regions = (
            _supported_damage_region_pass(
                damage_region_slots,
                target,
                width=target.primary_width,
                height=target.primary_height,
                bomb_active=bomb_active,
                pass_name="primary",
            )
        )
    else:
        primary = {
            "schema": SUPPORTED_SHOT_PASS_SCHEMA,
            "pass": "primary",
            "hitbox": {
                "width": target.primary_width,
                "height": target.primary_height,
            },
            "supported_hit_slots": [],
            "callback_dependent_overlap_slots": [],
            "type45_mode_dependent_overlap_slots": [],
            "supported_return_damage_subtotal": 0,
            "supported_feedback_accumulator_increment": 0,
            "feedback_accumulator_increment_cap": (
                PLAYER_SHOT_FEEDBACK_INCREMENT_CAP
            ),
            "numeric_authority": "not_evaluated_shot_collision_gate_closed",
        }
        primary_regions = {
            "schema": SUPPORTED_DAMAGE_REGION_PASS_SCHEMA,
            "pass": "primary",
            "hitbox": {
                "width": target.primary_width,
                "height": target.primary_height,
            },
            "hit_slots": [],
            "return_damage_contribution": 0,
            "bomb_region_overlap_signal": False,
            "numeric_authority": "not_evaluated_shot_collision_gate_closed",
        }
        after_primary = shot_slots
        after_primary_regions = damage_region_slots
    alternate = None
    alternate_regions = None
    if target.alternate_enabled and gate.shot_collision_open:
        alternate, after_alternate = _supported_shot_pass(
            after_primary,
            target,
            width=target.alternate_width,
            height=target.alternate_height,
            bomb_active=bomb_active,
            pass_name="alternate_after_supported_primary_mutation",
        )
        alternate_regions, after_alternate_regions = (
            _supported_damage_region_pass(
                after_primary_regions,
                target,
                width=target.alternate_width,
                height=target.alternate_height,
                bomb_active=bomb_active,
                pass_name="alternate_after_primary_region_mutation",
            )
        )
    else:
        after_alternate = after_primary
        after_alternate_regions = after_primary_regions
    primary_supported = (
        int(primary["supported_return_damage_subtotal"])
        + int(primary_regions["return_damage_contribution"])
    )
    alternate_supported = 0
    if alternate is not None and alternate_regions is not None:
        alternate_supported = (
            int(alternate["supported_return_damage_subtotal"])
            + int(alternate_regions["return_damage_contribution"])
        )
    bomb_region_overlap = bool(
        primary_regions["bomb_region_overlap_signal"]
        or (
            alternate_regions is not None
            and alternate_regions["bomb_region_overlap_signal"]
        )
    )
    resolved = resolve_enemy_hp_damage(
        EnemyResolvedDamageContext(
            primary_return_damage=primary_supported,
            alternate_return_damage=alternate_supported,
            alternate_enabled=target.alternate_enabled,
            bomb_region_overlap=bomb_region_overlap,
            route_id=route_id,
            player_damage_bonus_active=player_damage_bonus_active,
            hp_subtraction_open=gate.hp_subtraction_open,
            special_enemy_damage_mode_active=bool(
                global_damage_mode_flags & 0x01
            ),
            bomb_region_damage_allowed=bool(
                global_damage_mode_flags & 0x80
                and target.special_damage_blocker == 0
            ),
            post_damage_timer_active=target.post_damage_timer_current > 0,
            post_damage_timer_reduction_enabled=bool(target.flags & 0x02),
        )
    )
    record = {
        **target.record(),
        "damage_gate": gate.record(),
        "ordinary_shot_passes": {
            "primary": primary,
            "alternate": alternate,
        },
        "damage_region_passes": {
            "primary": primary_regions,
            "alternate": alternate_regions,
        },
        "supported_resolved_hp_damage": {
            **resolved.record(),
            "authority": (
                "supported_slots_and_manager_ordered_regions_only_"
                "unknown_direction_if_unresolved_overlap"
            ),
        },
    }
    return record, after_alternate, after_alternate_regions


@dataclass(frozen=True)
class NativeCombatProjection:
    payload: dict[str, object]
    sha256: str
    summary: dict[str, object]

    def record(self, *, include_payload: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": NATIVE_COMBAT_PROJECTION_SCHEMA,
            "sha256": self.sha256,
            "summary": self.summary,
            "authority": (
                "offline_exact_root_combat_state_and_supported_"
                "ordinary_shot_subtotals_only"
            ),
            "physical_predictive_authority": False,
            "live_ranking_authority": False,
        }
        if include_payload:
            record["payload"] = self.payload
        return record


def capture_native_combat_projection(
    reader: Any,
    *,
    native_root_projection: object,
    compact_state: dict[str, object],
) -> NativeCombatProjection:
    """Capture one exact-root combat projection without another enemy read."""

    shot_state = capture_player_shot_combat_state(reader)
    damage_region_state = capture_player_damage_region_state(reader)
    spell = decode_spell_state(
        _read_exact(
            reader,
            ADDR_SPELL_CARD_STATE,
            SPELL_STATE_CAPTURE_SIZE,
            field="combat spell state",
        )
    )
    player_context = _read_exact(
        reader,
        ADDR_PLAYER,
        PLAYER_BOMB_ACTIVE_OFFSET + 4,
        field="combat player context",
    )
    player_state = player_context[0]
    bomb_active = bool(
        struct.unpack_from("<I", player_context, PLAYER_BOMB_ACTIVE_OFFSET)[0]
    )
    targets = decode_enemy_damage_targets(native_root_projection)
    global_damage_mode_flags = struct.unpack(
        "<I",
        _read_exact(
            reader,
            ADDR_GLOBAL_DAMAGE_MODE_FLAGS,
            4,
            field="global damage mode flags",
        ),
    )[0]
    route_id = _read_exact(
        reader,
        ADDR_ROUTE_ID,
        1,
        field="route id",
    )[0]
    global_mode_state_pointer = struct.unpack(
        "<I",
        _read_exact(
            reader,
            ADDR_GLOBAL_MODE_MANAGER + GLOBAL_MODE_STATE_POINTER_OFFSET,
            4,
            field="global mode state pointer",
        ),
    )[0]
    global_mode_state_value = struct.unpack(
        "<h",
        _read_exact(
            reader,
            global_mode_state_pointer + GLOBAL_MODE_STATE_VALUE_OFFSET,
            2,
            field="global mode state value",
        ),
    )[0]
    player_damage_bonus_threshold = struct.unpack(
        "<h",
        _read_exact(
            reader,
            (
                ADDR_GLOBAL_MODE_MANAGER
                + GLOBAL_PLAYER_DAMAGE_BONUS_THRESHOLD_OFFSET
            ),
            2,
            field="player damage bonus threshold",
        ),
    )[0]
    player_damage_bonus_active = (
        global_mode_state_value >= player_damage_bonus_threshold
    )
    loaded_sht_state = capture_loaded_route2_sht_state(reader)
    shot_source_provenance = []
    for shot in shot_state.slots:
        provenance = loaded_sht_state.provenance_for_pointer(
            shot.source_record_pointer
        )
        shot_source_provenance.append(
            {
                "slot": shot.slot,
                "source_record_pointer": shot.source_record_pointer,
                "exact_loaded_sht_record": provenance is not None,
                "provenance": (
                    None if provenance is None else provenance.record()
                ),
            }
        )
    target_records: list[dict[str, object]] = []
    current_shot_slots = shot_state.slots
    current_damage_region_slots = damage_region_state.slots
    for target in targets:
        (
            target_record,
            current_shot_slots,
            current_damage_region_slots,
        ) = _target_combat_record(
            target,
            shot_state,
            current_shot_slots,
            current_damage_region_slots,
            bomb_active=bomb_active,
            player_state=player_state,
            spell_active=bool(spell["active"]),
            spell_enemy_pointer=int(spell["enemy_pointer"]),
            route_id=route_id,
            global_damage_mode_flags=global_damage_mode_flags,
            player_damage_bonus_active=player_damage_bonus_active,
        )
        target_records.append(target_record)
    payload: dict[str, object] = {
        "schema": NATIVE_COMBAT_PROJECTION_SCHEMA,
        "manager_frame": int(compact_state["manager_frame"]),
        "active_input": int(compact_state["input_current"]),
        "focus_logic": int(compact_state["focus_logic"]),
        "player_state": player_state,
        "bomb_active": bomb_active,
        "resolved_damage_context": {
            "route_id": route_id,
            "global_damage_mode_flags": global_damage_mode_flags,
            "global_mode_state_pointer": global_mode_state_pointer,
            "global_mode_state_value": global_mode_state_value,
            "player_damage_bonus_threshold": player_damage_bonus_threshold,
            "player_damage_bonus_active": player_damage_bonus_active,
        },
        "spell": {
            "active": bool(spell["active"]),
            "enemy_pointer": int(spell["enemy_pointer"]),
            "spell_id": int(spell["spell_id"]) if spell["active"] else None,
        },
        "player_shots": shot_state.record(),
        "player_damage_regions": damage_region_state.record(),
        "loaded_route2_sht": loaded_sht_state.record(),
        "player_shot_source_provenance": shot_source_provenance,
        "enemy_manager_processing_order": {
            "kind": "ascending_pool_slot",
            "slots": [target.slot for target in targets],
            "slot_zero_base": ENEMY_SLOT_ZERO_BASE,
            "pool_size": ENEMY_MANAGER_SCANNED_SLOT_COUNT,
            "slot_stride": ENEMY_STRIDE,
        },
        "enemy_targets": target_records,
        "scope": {
            "root_identity": (
                "full_player_shot_pool_digest_plus_active_slot_fields_"
                "full_player_damage_region_pool_digest_"
                "and_active_enemy_causal_tail_digests"
            ),
            "pass_projection": (
                "instantaneous_native_geometry_supported_slots_"
                "manager_ordered_cross_target_mutation"
            ),
            "omitted": [
                "future_action_delivery_and_focus_transition",
                "future_player_shot_update_callbacks",
                "type45_mode_predicate",
                "nonzero_hit_callback_semantics",
                "unresolved_ordinary_shot_callbacks",
                "generation_safe_cross_frame_hp_attribution",
                "hostile_birth_prevention",
                "survival_feasibility",
            ],
        },
    }
    summary = {
        "manager_frame": int(compact_state["manager_frame"]),
        "route_id": route_id,
        "bomb_active": bomb_active,
        "active_input": int(compact_state["input_current"]),
        "active_shot_count": len(shot_state.slots),
        "damage_eligible_shot_count": len(
            shot_state.damage_eligible_slot_indices
        ),
        "hit_state_shot_count": sum(slot.state == 2 for slot in shot_state.slots),
        "route2_normal_damage_path_compatible_active_shot_count": sum(
            slot.route2_normal_damage_path_compatible
            for slot in shot_state.slots
        ),
        "route2_normal_damage_path_incompatible_active_shot_count": sum(
            not slot.route2_normal_damage_path_compatible
            for slot in shot_state.slots
        ),
        "route2_exact_normal_source_active_shot_count": sum(
            bool(
                row["provenance"] is not None
                and row["provenance"]["normal_selector_reachable"]
            )
            for row in shot_source_provenance
        ),
        "route2_non_normal_or_unknown_source_active_shot_count": sum(
            not bool(
                row["provenance"] is not None
                and row["provenance"]["normal_selector_reachable"]
            )
            for row in shot_source_provenance
        ),
        "active_enemy_target_count": len(targets),
        "active_damage_region_count": len(damage_region_state.slots),
        "positive_hp_target_count": sum(target.hitpoints > 0 for target in targets),
        "positive_hp_sum": sum(
            max(target.hitpoints, 0) for target in targets
        ),
        "published_frame_damage_sum": sum(
            max(target.frame_damage, 0) for target in targets
        ),
        "open_hp_gate_target_count": sum(
            bool(record["damage_gate"]["hp_subtraction_open"])
            for record in target_records
        ),
        "supported_primary_overlap_target_count": sum(
            bool(
                record["ordinary_shot_passes"]["primary"][
                    "supported_hit_slots"
                ]
            )
            for record in target_records
        ),
        "unresolved_overlap_target_count": sum(
            bool(
                record["ordinary_shot_passes"]["primary"][
                    "callback_dependent_overlap_slots"
                ]
                or record["ordinary_shot_passes"]["primary"][
                    "type45_mode_dependent_overlap_slots"
                ]
                or (
                    record["ordinary_shot_passes"]["alternate"] is not None
                    and (
                        record["ordinary_shot_passes"]["alternate"][
                            "callback_dependent_overlap_slots"
                        ]
                        or record["ordinary_shot_passes"]["alternate"][
                            "type45_mode_dependent_overlap_slots"
                        ]
                    )
                )
            )
            for record in target_records
        ),
        "supported_primary_contribution_sum": sum(
            int(
                record["ordinary_shot_passes"]["primary"][
                    "supported_return_damage_subtotal"
                ]
            )
            for record in target_records
        ),
        "open_gate_supported_primary_contribution_sum": sum(
            int(
                record["ordinary_shot_passes"]["primary"][
                    "supported_return_damage_subtotal"
                ]
            )
            for record in target_records
            if bool(record["damage_gate"]["hp_subtraction_open"])
        ),
        "supported_alternate_contribution_sum": sum(
            int(
                alternate["supported_return_damage_subtotal"]
            )
            for record in target_records
            if (
                alternate
                := record["ordinary_shot_passes"]["alternate"]
            )
            is not None
        ),
        "player_shot_pool_sha256": shot_state.pool_sha256,
        "player_damage_region_pool_sha256": (
            damage_region_state.pool_sha256
        ),
        "supported_primary_damage_region_contribution_sum": sum(
            int(
                record["damage_region_passes"]["primary"][
                    "return_damage_contribution"
                ]
            )
            for record in target_records
        ),
        "supported_alternate_damage_region_contribution_sum": sum(
            int(alternate["return_damage_contribution"])
            for record in target_records
            if (
                alternate := record["damage_region_passes"]["alternate"]
            )
            is not None
        ),
        "supported_resolved_hp_damage_sum": sum(
            int(record["supported_resolved_hp_damage"]["hp_damage"])
            for record in target_records
        ),
    }
    return NativeCombatProjection(
        payload=payload,
        sha256=_canonical_digest(payload),
        summary=summary,
    )


def native_combat_projection_changes(
    left: NativeCombatProjection,
    right: NativeCombatProjection,
) -> tuple[dict[str, object], ...]:
    if left.sha256 == right.sha256:
        return ()
    changes: list[dict[str, object]] = []
    for field in sorted(set(left.payload) | set(right.payload)):
        left_value = left.payload.get(field)
        right_value = right.payload.get(field)
        if left_value == right_value:
            continue
        changes.append(
            {
                "field": field,
                "left_sha256": _canonical_digest(left_value),
                "right_sha256": _canonical_digest(right_value),
            }
        )
    return tuple(changes)


__all__ = [
    "ENEMY_ALTERNATE_HITBOX_OFFSET",
    "ENEMY_DAMAGE_HITBOX_OFFSET",
    "ENEMY_DAMAGE_TARGET_STATE_SCHEMA",
    "NATIVE_COMBAT_PROJECTION_SCHEMA",
    "PLAYER_DAMAGE_REGION_POOL_BYTES",
    "PLAYER_DAMAGE_REGION_POOL_OFFSET",
    "PLAYER_DAMAGE_REGION_POOL_SIZE",
    "PLAYER_DAMAGE_REGION_SLOT_STRIDE",
    "PLAYER_DAMAGE_REGION_STATE_SCHEMA",
    "PLAYER_SHOT_COMBAT_STATE_SCHEMA",
    "PLAYER_SHOT_POOL_BYTES",
    "SUPPORTED_SHOT_PASS_SCHEMA",
    "SUPPORTED_DAMAGE_REGION_PASS_SCHEMA",
    "EnemyDamageTarget",
    "NativeCombatProjection",
    "PlayerDamageRegionSlot",
    "PlayerDamageRegionState",
    "PlayerShotCombatSlot",
    "PlayerShotCombatState",
    "Th08TimerIdentity",
    "capture_native_combat_projection",
    "capture_player_damage_region_state",
    "capture_player_shot_combat_state",
    "decode_enemy_damage_targets",
    "decode_player_damage_region_pool",
    "decode_player_shot_pool",
    "native_combat_projection_changes",
]
