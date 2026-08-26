from __future__ import annotations

import struct
import unittest
from pathlib import Path
from types import SimpleNamespace

from th08_live.enemy_sensor import (
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_SIZE,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
)
from th08_runtime.game_state import (
    ADDR_PLAYER,
    ADDR_SPELL_CARD_STATE,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_DAMAGE_TIMER_OFFSET,
    PLAYER_PRIMARY_SHT_POINTER_OFFSET,
    PLAYER_SHOT_POOL_OFFSET,
    PLAYER_SHOT_SLOT_ANGLE_OFFSET,
    PLAYER_SHOT_SLOT_DAMAGE_OFFSET,
    PLAYER_SHOT_SLOT_FOCUS_OFFSET,
    PLAYER_SHOT_SLOT_HITBOX_OFFSET,
    PLAYER_SHOT_SLOT_HIT_CALLBACK_OFFSET,
    PLAYER_SHOT_SLOT_POSITION_OFFSET,
    PLAYER_SHOT_SLOT_SOURCE_RECORD_OFFSET,
    PLAYER_SHOT_SLOT_SPEED_OFFSET,
    PLAYER_SHOT_SLOT_STRIDE,
    PLAYER_SHOT_SLOT_TIMER_OFFSET,
    PLAYER_SHOT_SLOT_UPDATE_CALLBACK_OFFSET,
    PLAYER_SHOT_SLOT_VELOCITY_OFFSET,
    PLAYER_SHOT_TIMER_OFFSET,
    SPELL_STATE_CAPTURE_SIZE,
)
from th08_runtime.native_combat_projection import (
    ADDR_GLOBAL_DAMAGE_MODE_FLAGS,
    ADDR_GLOBAL_MODE_MANAGER,
    ADDR_ROUTE_ID,
    ENEMY_ALTERNATE_HITBOX_OFFSET,
    ENEMY_DAMAGE_HITBOX_OFFSET,
    ENEMY_FLAGS2_OFFSET,
    ENEMY_FRAME_DAMAGE_OFFSET,
    ENEMY_HITPOINTS_OFFSET,
    ENEMY_MAIN_VM_OFFSET,
    ENEMY_MAIN_VM_TIMER_CURRENT_OFFSET,
    ENEMY_POSITION_OFFSET,
    NATIVE_COMBAT_PROJECTION_SCHEMA,
    PLAYER_DAMAGE_REGION_POOL_BYTES,
    PLAYER_DAMAGE_REGION_POOL_OFFSET,
    PLAYER_DAMAGE_REGION_SLOT_STRIDE,
    PLAYER_DAMAGE_REGION_STATE_SCHEMA,
    GLOBAL_MODE_STATE_POINTER_OFFSET,
    GLOBAL_MODE_STATE_VALUE_OFFSET,
    GLOBAL_PLAYER_DAMAGE_BONUS_THRESHOLD_OFFSET,
    PLAYER_SHOT_COMBAT_STATE_SCHEMA,
    PLAYER_SHOT_POOL_BYTES,
    capture_native_combat_projection,
    capture_player_damage_region_state,
    capture_player_shot_combat_state,
    decode_enemy_damage_targets,
    decode_player_shot_pool,
)
from th08_runtime.route2_sht_provenance import (
    RANDOM_SPREAD_CALLBACK_POINTER,
    SHT_CALLBACK_OFFSETS,
    SHT_FIXED_HEADER_SIZE,
    SHT_LEVEL_ENTRY_SIZE,
    SHT_SHOT_RECORD_SIZE,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SHT = ROOT / "artifacts" / "decoded" / "ply02a.sht"
SECONDARY_SHT = ROOT / "artifacts" / "decoded" / "ply02as.sht"
PRIMARY_SHT_BASE = 0x03000000
SECONDARY_SHT_BASE = 0x03100000
PRIMARY_FIRST_RECORD_POINTER = PRIMARY_SHT_BASE + 0x68


def _relocate_sht(path: Path, *, base_pointer: int) -> bytes:
    data = bytearray(path.read_bytes())
    level_count = struct.unpack_from("<H", data, 2)[0]
    level_offsets = []
    for level in range(level_count):
        table_offset = SHT_FIXED_HEADER_SIZE + level * SHT_LEVEL_ENTRY_SIZE
        record_offset = struct.unpack_from("<I", data, table_offset)[0]
        level_offsets.append(record_offset)
        struct.pack_into("<I", data, table_offset, base_pointer + record_offset)
    level_ends = (*level_offsets[1:], len(data))
    for start, end in zip(level_offsets, level_ends, strict=True):
        cursor = start
        while cursor < end:
            if struct.unpack_from("<h", data, cursor)[0] < 0:
                break
            for callback_slot, callback_offset in enumerate(
                SHT_CALLBACK_OFFSETS
            ):
                index = struct.unpack_from(
                    "<I",
                    data,
                    cursor + callback_offset,
                )[0]
                pointer = (
                    RANDOM_SPREAD_CALLBACK_POINTER
                    if callback_slot == 0 and index == 7
                    else 0
                )
                struct.pack_into(
                    "<I",
                    data,
                    cursor + callback_offset,
                    pointer,
                )
            cursor += SHT_SHOT_RECORD_SIZE
    return bytes(data)


def _install_shot(
    pool: bytearray,
    slot: int,
    *,
    state: int = 1,
    shot_type: int = 0,
    damage: int = 20,
    hit_callback: int = 0,
    source_record_pointer: int = PRIMARY_FIRST_RECORD_POINTER,
) -> None:
    base = slot * PLAYER_SHOT_SLOT_STRIDE
    struct.pack_into(
        "<ff",
        pool,
        base + PLAYER_SHOT_SLOT_POSITION_OFFSET,
        100.0,
        50.0,
    )
    struct.pack_into(
        "<ff",
        pool,
        base + PLAYER_SHOT_SLOT_HITBOX_OFFSET,
        8.0,
        8.0,
    )
    struct.pack_into(
        "<ff",
        pool,
        base + PLAYER_SHOT_SLOT_VELOCITY_OFFSET,
        0.0,
        -12.0,
    )
    struct.pack_into(
        "<f",
        pool,
        base + PLAYER_SHOT_SLOT_SPEED_OFFSET,
        12.0,
    )
    struct.pack_into(
        "<f",
        pool,
        base + PLAYER_SHOT_SLOT_ANGLE_OFFSET,
        -1.5707964,
    )
    struct.pack_into(
        "<iIi",
        pool,
        base + PLAYER_SHOT_SLOT_TIMER_OFFSET,
        3,
        0x3F000000,
        4,
    )
    struct.pack_into(
        "<hhh",
        pool,
        base + PLAYER_SHOT_SLOT_DAMAGE_OFFSET,
        damage,
        state,
        shot_type,
    )
    pool[base + PLAYER_SHOT_SLOT_FOCUS_OFFSET] = 1
    struct.pack_into(
        "<I",
        pool,
        base + PLAYER_SHOT_SLOT_UPDATE_CALLBACK_OFFSET,
        0,
    )
    struct.pack_into(
        "<I",
        pool,
        base + PLAYER_SHOT_SLOT_HIT_CALLBACK_OFFSET,
        hit_callback,
    )
    struct.pack_into(
        "<I",
        pool,
        base + PLAYER_SHOT_SLOT_SOURCE_RECORD_OFFSET,
        source_record_pointer,
    )


def _install_damage_region(
    pool: bytearray,
    slot: int,
    *,
    center: tuple[float, float] = (100.0, 50.0),
    radius: float = 16.0,
    frames_remaining: int = 8,
    damage: int = 30,
    accumulated: int = 0,
    damage_cap: int = 0,
    tick_interval: int = 1,
) -> None:
    base = slot * PLAYER_DAMAGE_REGION_SLOT_STRIDE
    struct.pack_into(
        "<fffffffff",
        pool,
        base,
        center[0],
        center[1],
        radius,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    struct.pack_into(
        "<iiiiii",
        pool,
        base + 0x24,
        frames_remaining,
        0,
        damage,
        accumulated,
        damage_cap,
        tick_interval,
    )
    pool[base + 0x3C] = 1


def _install_enemy(
    component: bytearray,
    slot: int,
    *,
    flags: int = 0x49,
    position: tuple[float, float] = (100.0, 50.0),
    hitbox: tuple[float, float] = (24.0, 16.0),
    hitpoints: int = 100,
) -> None:
    base = slot * ENEMY_STRIDE
    struct.pack_into("<I", component, base + ENEMY_FLAGS_OFFSET, flags)
    struct.pack_into("<I", component, base + ENEMY_FLAGS2_OFFSET, 0)
    struct.pack_into(
        "<ff",
        component,
        base + ENEMY_POSITION_OFFSET,
        *position,
    )
    struct.pack_into(
        "<ff",
        component,
        base + ENEMY_DAMAGE_HITBOX_OFFSET,
        *hitbox,
    )
    struct.pack_into(
        "<iii",
        component,
        base + ENEMY_HITPOINTS_OFFSET,
        hitpoints,
        hitpoints,
        0,
    )


def _native_root(enemy_component: bytes) -> object:
    return SimpleNamespace(
        components=(
            SimpleNamespace(
                spec=SimpleNamespace(
                    name="ordinary_enemy_template_and_pool",
                    address=ENEMY_SLOT_ZERO_BASE,
                ),
                data=enemy_component,
            ),
        )
    )


class _Reader:
    def __init__(
        self,
        *,
        pool: bytes,
        emission_timer: bytes,
        damage_timer: bytes,
        spell: bytes,
        player_context: bytes,
        damage_regions: bytes = bytes(PLAYER_DAMAGE_REGION_POOL_BYTES),
        route_id: int = 2,
    ) -> None:
        global_mode_state_pointer = 0x02000000
        self._memory = {
            (ADDR_PLAYER + PLAYER_SHOT_POOL_OFFSET, len(pool)): pool,
            (
                ADDR_PLAYER + PLAYER_SHOT_TIMER_OFFSET,
                len(emission_timer),
            ): emission_timer,
            (
                ADDR_PLAYER + PLAYER_DAMAGE_TIMER_OFFSET,
                len(damage_timer),
            ): damage_timer,
            (ADDR_SPELL_CARD_STATE, len(spell)): spell,
            (ADDR_PLAYER, len(player_context)): player_context,
            (
                ADDR_PLAYER + PLAYER_DAMAGE_REGION_POOL_OFFSET,
                len(damage_regions),
            ): damage_regions,
            (ADDR_GLOBAL_DAMAGE_MODE_FLAGS, 4): bytes(4),
            (ADDR_ROUTE_ID, 1): bytes((route_id,)),
            (
                ADDR_GLOBAL_MODE_MANAGER + GLOBAL_MODE_STATE_POINTER_OFFSET,
                4,
            ): struct.pack("<I", global_mode_state_pointer),
            (
                global_mode_state_pointer + GLOBAL_MODE_STATE_VALUE_OFFSET,
                2,
            ): struct.pack("<h", 0),
            (
                ADDR_GLOBAL_MODE_MANAGER
                + GLOBAL_PLAYER_DAMAGE_BONUS_THRESHOLD_OFFSET,
                2,
            ): struct.pack("<h", 1),
            (
                ADDR_PLAYER + PLAYER_PRIMARY_SHT_POINTER_OFFSET,
                8,
            ): struct.pack(
                "<II",
                PRIMARY_SHT_BASE,
                SECONDARY_SHT_BASE,
            ),
        }
        primary_sht = _relocate_sht(
            PRIMARY_SHT,
            base_pointer=PRIMARY_SHT_BASE,
        )
        secondary_sht = _relocate_sht(
            SECONDARY_SHT,
            base_pointer=SECONDARY_SHT_BASE,
        )
        self._memory[(PRIMARY_SHT_BASE, len(primary_sht))] = primary_sht
        self._memory[(SECONDARY_SHT_BASE, len(secondary_sht))] = secondary_sht

    def read(self, address: int, size: int) -> bytes:
        try:
            return self._memory[(address, size)]
        except KeyError as exc:
            raise AssertionError(f"unexpected read {address:#x}/{size:#x}") from exc


class NativeCombatProjectionTests(unittest.TestCase):
    def test_damage_region_pool_decode_and_cap_contribution(self) -> None:
        pool = bytearray(PLAYER_DAMAGE_REGION_POOL_BYTES)
        _install_damage_region(
            pool,
            9,
            damage=7,
            accumulated=8,
            damage_cap=12,
        )
        state = capture_player_damage_region_state(
            _Reader(
                pool=bytes(PLAYER_SHOT_POOL_BYTES),
                emission_timer=bytes(12),
                damage_timer=bytes(12),
                spell=bytes(SPELL_STATE_CAPTURE_SIZE),
                player_context=bytes(PLAYER_BOMB_ACTIVE_OFFSET + 4),
                damage_regions=bytes(pool),
            )
        )
        self.assertEqual(state.record()["schema"], PLAYER_DAMAGE_REGION_STATE_SCHEMA)
        self.assertEqual(len(state.slots), 1)
        self.assertEqual(state.slots[0].slot, 9)
        self.assertEqual(state.slots[0].region.damage, 7)
        self.assertEqual(state.slots[0].region.damage_cap, 12)

    def test_full_player_shot_pool_retains_causal_and_decoded_identity(
        self,
    ) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(pool, 7, state=2, shot_type=3, damage=11)
        state = capture_player_shot_combat_state(
            _Reader(
                pool=bytes(pool),
                emission_timer=struct.pack("<iIi", 4, 0, 5),
                damage_timer=struct.pack("<iIi", 8, 0x3F000000, 9),
                spell=bytes(SPELL_STATE_CAPTURE_SIZE),
                player_context=bytes(PLAYER_BOMB_ACTIVE_OFFSET + 4),
            )
        )

        self.assertTrue(state.emission_timer.integer_changed)
        self.assertTrue(state.damage_timer.integer_changed)
        self.assertEqual(state.occupied_slot_indices, (7,))
        self.assertEqual(state.damage_eligible_slot_indices, (7,))
        slot = state.slots[0]
        self.assertEqual(slot.damage, 11)
        self.assertEqual(slot.shot_type, 3)
        self.assertEqual(slot.focus_logic_at_birth, 1)
        self.assertEqual(
            slot.source_record_pointer,
            PRIMARY_FIRST_RECORD_POINTER,
        )
        record = state.record()
        self.assertEqual(record["schema"], PLAYER_SHOT_COMBAT_STATE_SCHEMA)
        self.assertEqual(record["pool"]["occupied_count"], 1)
        self.assertEqual(len(record["pool"]["sha256"]), 64)
        self.assertEqual(len(record["pool"]["active_slots"][0]["raw_sha256"]), 64)

    def test_inactive_stale_bytes_change_pool_identity_without_inventing_shot(
        self,
    ) -> None:
        left = bytearray(PLAYER_SHOT_POOL_BYTES)
        right = bytearray(left)
        right[PLAYER_SHOT_SLOT_STRIDE + 17] = 1

        left_slots = decode_player_shot_pool(bytes(left))
        right_slots = decode_player_shot_pool(bytes(right))

        self.assertEqual(left_slots, ())
        self.assertEqual(right_slots, ())
        self.assertNotEqual(bytes(left), bytes(right))

    def test_damage_targets_include_slot_zero_and_exclude_failure_sentinel(
        self,
    ) -> None:
        component = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        _install_enemy(component, 0)
        struct.pack_into(
            "<I",
            component,
            ENEMY_POOL_SIZE * ENEMY_STRIDE + ENEMY_FLAGS_OFFSET,
            1,
        )

        targets = decode_enemy_damage_targets(_native_root(bytes(component)))

        self.assertEqual([target.slot for target in targets], [0])
        self.assertEqual(targets[0].enemy_pointer, ENEMY_SLOT_ZERO_BASE)

    def test_legacy_slot_one_pool_is_not_damage_authority(self) -> None:
        legacy_root = SimpleNamespace(
            components=(
                SimpleNamespace(
                    spec=SimpleNamespace(
                        name="ordinary_enemy_template_and_pool",
                        address=ENEMY_SLOT_ZERO_BASE + ENEMY_STRIDE,
                    ),
                    data=bytes(ENEMY_POOL_SIZE * ENEMY_STRIDE),
                ),
            )
        )

        with self.assertRaisesRegex(ValueError, "legacy slot-1 pool"):
            decode_enemy_damage_targets(legacy_root)

    def test_projection_exposes_supported_and_unresolved_native_passes(
        self,
    ) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(pool, 0, damage=20)
        _install_shot(pool, 1, state=2, shot_type=3, damage=10)
        _install_shot(pool, 2, shot_type=4, damage=7)
        _install_shot(pool, 3, damage=9, hit_callback=0x00450100)
        damage_regions = bytearray(PLAYER_DAMAGE_REGION_POOL_BYTES)
        _install_damage_region(
            damage_regions,
            4,
            damage=7,
            accumulated=8,
            damage_cap=12,
        )

        enemy_component = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        base = 0
        struct.pack_into("<I", enemy_component, base + ENEMY_FLAGS_OFFSET, 0x49)
        struct.pack_into("<I", enemy_component, base + ENEMY_FLAGS2_OFFSET, 0)
        struct.pack_into(
            "<ff",
            enemy_component,
            base + ENEMY_POSITION_OFFSET,
            100.0,
            50.0,
        )
        struct.pack_into(
            "<ff",
            enemy_component,
            base + ENEMY_DAMAGE_HITBOX_OFFSET,
            24.0,
            16.0,
        )
        struct.pack_into(
            "<ff",
            enemy_component,
            base + ENEMY_ALTERNATE_HITBOX_OFFSET,
            12.0,
            12.0,
        )
        struct.pack_into(
            "<iii",
            enemy_component,
            base + ENEMY_HITPOINTS_OFFSET,
            100,
            120,
            0,
        )
        struct.pack_into(
            "<i",
            enemy_component,
            base + ENEMY_FRAME_DAMAGE_OFFSET,
            0,
        )
        struct.pack_into(
            "<I",
            enemy_component,
            base + ENEMY_MAIN_VM_OFFSET,
            0x00600000,
        )
        struct.pack_into(
            "<i",
            enemy_component,
            base + ENEMY_MAIN_VM_TIMER_CURRENT_OFFSET,
            77,
        )

        spell = bytearray(SPELL_STATE_CAPTURE_SIZE)
        player_context = bytearray(PLAYER_BOMB_ACTIVE_OFFSET + 4)
        projection = capture_native_combat_projection(
            _Reader(
                pool=bytes(pool),
                emission_timer=struct.pack("<iIi", 4, 0, 5),
                damage_timer=struct.pack("<iIi", 8, 0, 9),
                spell=bytes(spell),
                player_context=bytes(player_context),
                damage_regions=bytes(damage_regions),
            ),
            native_root_projection=_native_root(bytes(enemy_component)),
            compact_state={
                "manager_frame": 100,
                "input_current": 0x05,
                "focus_logic": 1,
            },
        )

        self.assertEqual(projection.record()["schema"], NATIVE_COMBAT_PROJECTION_SCHEMA)
        self.assertEqual(projection.summary["active_shot_count"], 4)
        self.assertEqual(projection.summary["route_id"], 2)
        self.assertFalse(projection.summary["bomb_active"])
        self.assertEqual(projection.summary["active_input"], 0x05)
        self.assertEqual(projection.summary["damage_eligible_shot_count"], 4)
        self.assertEqual(
            projection.summary[
                "route2_normal_damage_path_compatible_active_shot_count"
            ],
            1,
        )
        self.assertEqual(
            projection.summary[
                "route2_normal_damage_path_incompatible_active_shot_count"
            ],
            3,
        )
        self.assertEqual(
            projection.summary[
                "route2_exact_normal_source_active_shot_count"
            ],
            4,
        )
        self.assertEqual(
            projection.summary[
                "route2_non_normal_or_unknown_source_active_shot_count"
            ],
            0,
        )
        self.assertEqual(projection.summary["active_enemy_target_count"], 1)
        self.assertEqual(projection.summary["active_damage_region_count"], 1)
        self.assertEqual(projection.summary["open_hp_gate_target_count"], 1)
        self.assertEqual(projection.summary["positive_hp_sum"], 100)
        self.assertEqual(
            projection.summary["supported_primary_contribution_sum"],
            30,
        )
        self.assertEqual(
            projection.summary[
                "open_gate_supported_primary_contribution_sum"
            ],
            30,
        )
        self.assertEqual(
            projection.summary["supported_alternate_contribution_sum"],
            10,
        )
        self.assertEqual(
            projection.summary[
                "supported_primary_damage_region_contribution_sum"
            ],
            4,
        )
        self.assertEqual(
            projection.summary[
                "supported_alternate_damage_region_contribution_sum"
            ],
            0,
        )
        self.assertEqual(
            projection.summary["supported_resolved_hp_damage_sum"],
            39,
        )
        self.assertEqual(
            projection.summary["supported_primary_overlap_target_count"],
            1,
        )
        self.assertEqual(projection.summary["unresolved_overlap_target_count"], 1)
        target = projection.payload["enemy_targets"][0]
        self.assertEqual(target["hitpoints"], 100)
        self.assertTrue(target["alternate_hitbox"]["enabled"])
        self.assertTrue(target["damage_gate"]["hp_subtraction_open"])
        primary = target["ordinary_shot_passes"]["primary"]
        alternate = target["ordinary_shot_passes"]["alternate"]
        primary_regions = target["damage_region_passes"]["primary"]
        alternate_regions = target["damage_region_passes"]["alternate"]
        self.assertEqual(primary["supported_hit_slots"], [0, 1])
        self.assertEqual(primary["supported_return_damage_subtotal"], 30)
        self.assertEqual(
            primary["supported_feedback_accumulator_increment"],
            30,
        )
        self.assertEqual(primary["type45_mode_dependent_overlap_slots"], [2])
        self.assertEqual(primary["callback_dependent_overlap_slots"], [3])
        self.assertEqual(alternate["supported_hit_slots"], [1])
        self.assertEqual(alternate["supported_return_damage_subtotal"], 10)
        self.assertEqual(primary_regions["hit_slots"], [4])
        self.assertEqual(primary_regions["return_damage_contribution"], 4)
        self.assertEqual(alternate_regions["hit_slots"], [4])
        self.assertEqual(alternate_regions["return_damage_contribution"], 0)
        self.assertEqual(
            target["supported_resolved_hp_damage"]["hp_damage"],
            39,
        )

    def test_manager_order_propagates_shot_and_region_mutation(self) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(pool, 0, damage=20)
        damage_regions = bytearray(PLAYER_DAMAGE_REGION_POOL_BYTES)
        _install_damage_region(
            damage_regions,
            4,
            damage=7,
            accumulated=8,
            damage_cap=12,
        )
        enemy_component = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        _install_enemy(enemy_component, 5)
        _install_enemy(enemy_component, 2)

        projection = capture_native_combat_projection(
            _Reader(
                pool=bytes(pool),
                emission_timer=struct.pack("<iIi", 4, 0, 5),
                damage_timer=struct.pack("<iIi", 8, 0, 9),
                spell=bytes(SPELL_STATE_CAPTURE_SIZE),
                player_context=bytes(PLAYER_BOMB_ACTIVE_OFFSET + 4),
                damage_regions=bytes(damage_regions),
            ),
            native_root_projection=_native_root(bytes(enemy_component)),
            compact_state={
                "manager_frame": 100,
                "input_current": 0x05,
                "focus_logic": 1,
            },
        )

        self.assertEqual(
            projection.payload["enemy_manager_processing_order"]["slots"],
            [2, 5],
        )
        first, second = projection.payload["enemy_targets"]
        self.assertEqual(
            first["ordinary_shot_passes"]["primary"][
                "supported_return_damage_subtotal"
            ],
            20,
        )
        self.assertEqual(
            second["ordinary_shot_passes"]["primary"][
                "supported_return_damage_subtotal"
            ],
            0,
        )
        self.assertEqual(
            first["damage_region_passes"]["primary"][
                "return_damage_contribution"
            ],
            4,
        )
        self.assertEqual(
            second["damage_region_passes"]["primary"][
                "return_damage_contribution"
            ],
            0,
        )
        self.assertEqual(
            projection.summary["supported_resolved_hp_damage_sum"],
            24,
        )

    def test_closed_first_target_gate_does_not_consume_shared_state(self) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(pool, 0, damage=20)
        damage_regions = bytearray(PLAYER_DAMAGE_REGION_POOL_BYTES)
        _install_damage_region(
            damage_regions,
            4,
            damage=7,
            accumulated=8,
            damage_cap=12,
        )
        enemy_component = bytearray((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)
        _install_enemy(enemy_component, 5)
        _install_enemy(enemy_component, 2, flags=0x09)

        projection = capture_native_combat_projection(
            _Reader(
                pool=bytes(pool),
                emission_timer=struct.pack("<iIi", 4, 0, 5),
                damage_timer=struct.pack("<iIi", 8, 0, 9),
                spell=bytes(SPELL_STATE_CAPTURE_SIZE),
                player_context=bytes(PLAYER_BOMB_ACTIVE_OFFSET + 4),
                damage_regions=bytes(damage_regions),
            ),
            native_root_projection=_native_root(bytes(enemy_component)),
            compact_state={
                "manager_frame": 100,
                "input_current": 0x05,
                "focus_logic": 1,
            },
        )

        first, second = projection.payload["enemy_targets"]
        self.assertFalse(first["damage_gate"]["shot_collision_open"])
        self.assertEqual(
            first["ordinary_shot_passes"]["primary"]["numeric_authority"],
            "not_evaluated_shot_collision_gate_closed",
        )
        self.assertEqual(
            second["ordinary_shot_passes"]["primary"][
                "supported_return_damage_subtotal"
            ],
            20,
        )
        self.assertEqual(
            second["damage_region_passes"]["primary"][
                "return_damage_contribution"
            ],
            4,
        )
        self.assertEqual(
            second["supported_resolved_hp_damage"]["hp_damage"],
            24,
        )

    def test_nonfinite_active_shot_fails_closed(self) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(pool, 0)
        struct.pack_into(
            "<f",
            pool,
            PLAYER_SHOT_SLOT_POSITION_OFFSET,
            float("nan"),
        )

        with self.assertRaisesRegex(ValueError, "not finite"):
            decode_player_shot_pool(bytes(pool))

    def test_unknown_source_record_remains_explicit(self) -> None:
        pool = bytearray(PLAYER_SHOT_POOL_BYTES)
        _install_shot(
            pool,
            5,
            source_record_pointer=0xDEADBEEF,
        )
        enemy_component = bytes((ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE)

        projection = capture_native_combat_projection(
            _Reader(
                pool=bytes(pool),
                emission_timer=struct.pack("<iIi", 4, 0, 5),
                damage_timer=struct.pack("<iIi", 8, 0, 9),
                spell=bytes(SPELL_STATE_CAPTURE_SIZE),
                player_context=bytes(PLAYER_BOMB_ACTIVE_OFFSET + 4),
            ),
            native_root_projection=_native_root(enemy_component),
            compact_state={
                "manager_frame": 100,
                "input_current": 0x05,
                "focus_logic": 0,
            },
        )

        self.assertEqual(
            projection.summary[
                "route2_exact_normal_source_active_shot_count"
            ],
            0,
        )
        self.assertEqual(
            projection.summary[
                "route2_non_normal_or_unknown_source_active_shot_count"
            ],
            1,
        )
        source = projection.payload["player_shot_source_provenance"][0]
        self.assertFalse(source["exact_loaded_sht_record"])
        self.assertIsNone(source["provenance"])


if __name__ == "__main__":
    unittest.main()
