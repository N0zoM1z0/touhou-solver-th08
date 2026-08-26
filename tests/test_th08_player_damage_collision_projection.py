from __future__ import annotations

import struct
import unittest

from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_runtime.game_state import (
    ADDR_PLAYER,
    PLAYER_DAMAGE_TIMER_OFFSET,
    PLAYER_SHOT_POOL_OFFSET,
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
    PLAYER_SHOT_POOL_BYTES,
)
from th08_runtime.player_damage_collision_projection import (
    capture_player_damage_collision_projection,
)


class _Reader:
    def __init__(
        self,
        *,
        shot_pool: bytes,
        enemy_pool: bytes,
    ) -> None:
        self._segments = {
            ADDR_PLAYER + PLAYER_SHOT_POOL_OFFSET: shot_pool,
            ADDR_PLAYER + PLAYER_SHOT_TIMER_OFFSET: struct.pack(
                "<iIi", 8, 0x3F000000, 9
            ),
            ADDR_PLAYER + PLAYER_DAMAGE_TIMER_OFFSET: struct.pack(
                "<iIi", 10, 0, 11
            ),
            ENEMY_POOL_BASE: enemy_pool,
        }

    def read(self, address: int, size: int) -> bytes:
        data = self._segments.get(address)
        if data is None:
            return b""
        return data[:size]


def _shot_pool(*, pointer_root: int) -> bytes:
    pool = bytearray(PLAYER_SHOT_POOL_BYTES)
    base = 3 * PLAYER_SHOT_SLOT_STRIDE
    struct.pack_into(
        "<2f", pool, base + PLAYER_SHOT_SLOT_POSITION_OFFSET, 226.75, 66.125
    )
    struct.pack_into(
        "<2f", pool, base + PLAYER_SHOT_SLOT_HITBOX_OFFSET, 16.0, 12.0
    )
    struct.pack_into(
        "<2f", pool, base + PLAYER_SHOT_SLOT_VELOCITY_OFFSET, 1.5, -8.0
    )
    struct.pack_into("<f", pool, base + PLAYER_SHOT_SLOT_SPEED_OFFSET, 8.25)
    struct.pack_into("<f", pool, base + PLAYER_SHOT_SLOT_ANGLE_OFFSET, -1.5)
    struct.pack_into(
        "<iIi", pool, base + PLAYER_SHOT_SLOT_TIMER_OFFSET, 4, 0, 5
    )
    struct.pack_into("<h", pool, base + PLAYER_SHOT_SLOT_DAMAGE_OFFSET, 17)
    struct.pack_into("<h", pool, base + PLAYER_SHOT_SLOT_STATE_OFFSET, 1)
    struct.pack_into("<h", pool, base + PLAYER_SHOT_SLOT_TYPE_OFFSET, 0)
    pool[base + PLAYER_SHOT_SLOT_FOCUS_OFFSET] = 1
    struct.pack_into("<h", pool, base + PLAYER_SHOT_SLOT_ANM_INDEX_OFFSET, 9)
    struct.pack_into(
        "<I", pool, base + PLAYER_SHOT_SLOT_UPDATE_CALLBACK_OFFSET, pointer_root
    )
    struct.pack_into(
        "<I", pool, base + PLAYER_SHOT_SLOT_HIT_CALLBACK_OFFSET, pointer_root + 4
    )
    struct.pack_into(
        "<I", pool, base + PLAYER_SHOT_SLOT_SOURCE_RECORD_OFFSET, pointer_root + 8
    )
    return bytes(pool)


def _enemy_pool() -> bytes:
    pool = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
    base = 7 * ENEMY_STRIDE
    struct.pack_into("<I", pool, base + ENEMY_FLAGS_OFFSET, ENEMY_ACTIVE_FLAG)
    struct.pack_into("<I", pool, base + ENEMY_FLAGS2_OFFSET, 0x82)
    struct.pack_into("<2f", pool, base + ENEMY_POSITION_OFFSET, 227.0, 64.0)
    struct.pack_into(
        "<2f", pool, base + ENEMY_DAMAGE_HITBOX_OFFSET, 32.0, 24.0
    )
    struct.pack_into(
        "<2f", pool, base + ENEMY_ALTERNATE_HITBOX_OFFSET, 0.0, 0.0
    )
    struct.pack_into("<i", pool, base + ENEMY_HITPOINTS_OFFSET, 90)
    struct.pack_into("<i", pool, base + ENEMY_MAX_HITPOINTS_OFFSET, 100)
    struct.pack_into("<i", pool, base + ENEMY_FRAME_DAMAGE_OFFSET, 10)
    struct.pack_into(
        "<I", pool, base + ENEMY_SPECIAL_DAMAGE_BLOCKER_OFFSET, 0x50000000
    )
    struct.pack_into(
        "<i", pool, base + ENEMY_POST_DAMAGE_TIMER_CURRENT_OFFSET, 6
    )
    return bytes(pool)


class PlayerDamageCollisionProjectionTests(unittest.TestCase):
    def test_active_shot_and_enemy_aabb_inputs_are_pointer_free(self) -> None:
        projection = capture_player_damage_collision_projection(
            _Reader(
                shot_pool=_shot_pool(pointer_root=0x401000),
                enemy_pool=_enemy_pool(),
            )
        )

        shot = projection.payload["player_shots"]["rows"][0]
        self.assertEqual(shot["slot"], 3)
        self.assertEqual(shot["state"], 1)
        self.assertEqual(shot["position_bits"], [0x4362C000, 0x42844000])
        self.assertTrue(shot["update_callback_installed"])
        self.assertTrue(shot["hit_callback_installed"])
        target = projection.payload["enemy_targets"][0]
        self.assertEqual(target["slot"], 7)
        self.assertEqual(target["position_bits"], [0x43630000, 0x42800000])
        self.assertEqual(target["flags2"], 0x82)
        self.assertTrue(target["special_damage_blocker_present"])

    def test_relocated_player_shot_pointers_do_not_change_digest(self) -> None:
        enemy_pool = _enemy_pool()
        left = capture_player_damage_collision_projection(
            _Reader(
                shot_pool=_shot_pool(pointer_root=0x401000),
                enemy_pool=enemy_pool,
            )
        )
        right = capture_player_damage_collision_projection(
            _Reader(
                shot_pool=_shot_pool(pointer_root=0xD0100000),
                enemy_pool=enemy_pool,
            )
        )

        self.assertEqual(left.payload, right.payload)
        self.assertEqual(left.sha256, right.sha256)

    def test_short_enemy_pool_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "enemy damage-collision pool"):
            capture_player_damage_collision_projection(
                _Reader(
                    shot_pool=_shot_pool(pointer_root=0x401000),
                    enemy_pool=b"",
                )
            )


if __name__ == "__main__":
    unittest.main()
