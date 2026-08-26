"""Pointer-free player-shot/enemy-damage collision state at one root.

This diagnostic projection follows ``Player::FUN_00451670``: it retains the
complete active player-shot geometry and the damage AABBs of every active
enemy in manager order.  Runtime pointers and render-only VM state are not
part of the identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import struct
from typing import Any

from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_runtime.native_combat_projection import (
    ENEMY_ALTERNATE_HITBOX_OFFSET,
    ENEMY_DAMAGE_HITBOX_OFFSET,
    ENEMY_FLAGS2_OFFSET,
    ENEMY_FRAME_DAMAGE_OFFSET,
    ENEMY_HITPOINTS_OFFSET,
    ENEMY_MAX_HITPOINTS_OFFSET,
    ENEMY_POSITION_OFFSET,
    ENEMY_POST_DAMAGE_TIMER_CURRENT_OFFSET,
    ENEMY_SPECIAL_DAMAGE_BLOCKER_OFFSET,
    capture_player_shot_combat_state,
)


PLAYER_DAMAGE_COLLISION_SCHEMA = "th08-player-damage-collision-projection-v1"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def _f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _player_shot_records(shot_state: Any) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shot in shot_state.slots:
        rows.append(
            {
                "slot": int(shot.slot),
                "position_bits": [_f32_bits(shot.x), _f32_bits(shot.y)],
                "velocity_bits": [
                    _f32_bits(shot.velocity_x),
                    _f32_bits(shot.velocity_y),
                ],
                "hitbox_bits": [
                    _f32_bits(shot.hitbox_width),
                    _f32_bits(shot.hitbox_height),
                ],
                "speed_bits": _f32_bits(shot.speed),
                "angle_bits": _f32_bits(shot.angle),
                "timer": shot.timer.record(),
                "damage": int(shot.damage),
                "state": int(shot.state),
                "type": int(shot.shot_type),
                "focus_logic_at_birth": int(shot.focus_logic_at_birth),
                "anm_index": int(shot.anm_index),
                "update_callback_installed": bool(
                    shot.update_callback_pointer
                ),
                "hit_callback_installed": bool(shot.hit_callback_pointer),
                "source_record_installed": bool(shot.source_record_pointer),
                "damage_loop_eligible": bool(shot.damage_loop_eligible),
            }
        )
    return rows


def _enemy_target_records(blob: bytes) -> list[dict[str, object]]:
    expected_size = ENEMY_POOL_SIZE * ENEMY_STRIDE
    if len(blob) != expected_size:
        raise ValueError(
            "enemy damage-collision pool requires "
            f"{expected_size:#x} exact bytes"
        )
    rows: list[dict[str, object]] = []
    for slot in range(ENEMY_POOL_SIZE):
        base = slot * ENEMY_STRIDE
        flags = struct.unpack_from("<I", blob, base + ENEMY_FLAGS_OFFSET)[0]
        if not flags & ENEMY_ACTIVE_FLAG:
            continue
        rows.append(
            {
                "slot": slot,
                "position_bits": list(
                    struct.unpack_from(
                        "<2I", blob, base + ENEMY_POSITION_OFFSET
                    )
                ),
                "primary_hitbox_bits": list(
                    struct.unpack_from(
                        "<2I", blob, base + ENEMY_DAMAGE_HITBOX_OFFSET
                    )
                ),
                "alternate_hitbox_bits": list(
                    struct.unpack_from(
                        "<2I", blob, base + ENEMY_ALTERNATE_HITBOX_OFFSET
                    )
                ),
                "hitpoints": struct.unpack_from(
                    "<i", blob, base + ENEMY_HITPOINTS_OFFSET
                )[0],
                "maximum_hitpoints": struct.unpack_from(
                    "<i", blob, base + ENEMY_MAX_HITPOINTS_OFFSET
                )[0],
                "published_frame_damage": struct.unpack_from(
                    "<i", blob, base + ENEMY_FRAME_DAMAGE_OFFSET
                )[0],
                "flags": flags,
                "flags2": struct.unpack_from(
                    "<I", blob, base + ENEMY_FLAGS2_OFFSET
                )[0],
                "special_damage_blocker_present": bool(
                    struct.unpack_from(
                        "<I",
                        blob,
                        base + ENEMY_SPECIAL_DAMAGE_BLOCKER_OFFSET,
                    )[0]
                ),
                "post_damage_timer_current": struct.unpack_from(
                    "<i",
                    blob,
                    base + ENEMY_POST_DAMAGE_TIMER_CURRENT_OFFSET,
                )[0],
            }
        )
    return rows


@dataclass(frozen=True, slots=True)
class PlayerDamageCollisionProjection:
    payload: dict[str, object]
    sha256: str

    def record(self, *, include_payload: bool = True) -> dict[str, object]:
        player_shots = self.payload["player_shots"]
        enemy_targets = self.payload["enemy_targets"]
        assert isinstance(player_shots, dict)
        assert isinstance(enemy_targets, list)
        shot_rows = player_shots["rows"]
        assert isinstance(shot_rows, list)
        record: dict[str, object] = {
            "schema": PLAYER_DAMAGE_COLLISION_SCHEMA,
            "sha256": self.sha256,
            "summary": {
                "active_player_shot_count": len(shot_rows),
                "damage_eligible_player_shot_count": sum(
                    bool(row["damage_loop_eligible"]) for row in shot_rows
                ),
                "hit_state_player_shot_count": sum(
                    int(row["state"]) == 2 for row in shot_rows
                ),
                "active_enemy_target_count": len(enemy_targets),
            },
            "authority": (
                "exact_root_aabb_inputs_and_post_collision_slot_state_only"
            ),
        }
        if include_payload:
            record["payload"] = self.payload
        return record


def capture_player_damage_collision_projection(
    reader: Any,
) -> PlayerDamageCollisionProjection:
    """Capture active shot slots and enemy damage targets without pointers."""

    shot_state = capture_player_shot_combat_state(reader)
    enemy_blob = reader.read(
        ENEMY_POOL_BASE,
        ENEMY_POOL_SIZE * ENEMY_STRIDE,
    )
    player_shot_rows = _player_shot_records(shot_state)
    enemy_target_rows = _enemy_target_records(enemy_blob)
    payload: dict[str, object] = {
        "schema": PLAYER_DAMAGE_COLLISION_SCHEMA,
        "player_shots": {
            "emission_timer": shot_state.emission_timer.record(),
            "damage_timer": shot_state.damage_timer.record(),
            "rows": player_shot_rows,
        },
        "enemy_targets": enemy_target_rows,
        "manager_processing_order": "ascending_enemy_pool_slot",
        "pointer_exclusions": [
            "player_shot_callbacks_replaced_by_presence",
            "loaded_sht_source_record_replaced_by_presence",
            "enemy_main_ecl_and_special_damage_addresses_excluded",
            "render_anm_state_excluded",
        ],
    }
    return PlayerDamageCollisionProjection(
        payload=payload,
        sha256=_canonical_digest(payload),
    )


__all__ = (
    "PLAYER_DAMAGE_COLLISION_SCHEMA",
    "PlayerDamageCollisionProjection",
    "capture_player_damage_collision_projection",
)
