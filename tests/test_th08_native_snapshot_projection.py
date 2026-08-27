from __future__ import annotations

import struct
import unittest
from types import SimpleNamespace

from th08_live.bullet_decode import BULLET_STATE_OFFSET
from th08_runtime.auxiliary_ecl_state import (
    ACTIVE_VM_AUXILIARY_MARKER_OFFSET,
    ACTIVE_VM_BYTES,
    CONTEXT_ACTIVE_VM_OFFSET,
    CONTEXT_CALL_DEPTH_OFFSET,
    CONTEXT_TARGET_OFFSET,
)
from th08_live.enemy_ecl_inventory import (
    ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
)
from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_ecl_runtime import ENEMY_MAIN_ECL_VM_OFFSET
from th08_live.sensor import BULLET_POOL_SIZE, BULLET_STRIDE
from th08_native_future_body_root import (
    TH08_ENEMY_MANAGER_TEMPLATE_BASE,
    TH08_TIMELINE_RUNTIME_BASE,
)
from th08_runtime.native_snapshot_projection import (
    BULLET_TIMER_D80_OFFSET,
    BULLET_TIMER_D8C_OFFSET,
    BULLET_MANAGER_BASE,
    BULLET_TEMPLATE_COLLISION_OFFSET,
    BULLET_TEMPLATE_COUNT,
    BULLET_TEMPLATE_STRIDE,
    COLLISION_CONTROL_PROJECTION_SCHEMA,
    CollisionControlProjection,
    ECL_DIFFICULTY_MASK_ADDRESS,
    ECL_FILE_CONTEXT_ADDRESS,
    EFFECT_POOL_BASE,
    EFFECT_SLOT_STRIDE,
    ENEMY_ANM_PREFIX_SIZE,
    ENEMY_ATTACHED_EFFECT_COUNT_OFFSET,
    ENEMY_ATTACHED_EFFECT_POINTERS_OFFSET,
    ENEMY_DEATH_CALLBACK_SUBROUTINE_OFFSET,
    ENEMY_HITPOINTS_OFFSET,
    ENEMY_MAX_HITPOINTS_OFFSET,
    ENEMY_MOTION_DURATION_OFFSET,
    ENEMY_MOTION_ORBIT_CENTER_OFFSET,
    ENEMY_MOTION_TIMED_DISPLACEMENT_OFFSET,
    ENEMY_MOTION_TIMER_OFFSET,
    ENEMY_PHASE_START_HITPOINTS_OFFSET,
    ENEMY_HEALTH_TRANSITION_SUCCESSORS_OFFSET,
    ENEMY_HEALTH_TRANSITION_THRESHOLDS_OFFSET,
    ENEMY_PHASE_TIMER_OFFSET,
    ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET,
    ENEMY_PERIODIC_EMISSION_PERIOD_OFFSET,
    ENEMY_PERIODIC_EMISSION_TIMER_OFFSET,
    ENEMY_SECONDARY_FLAGS_OFFSET,
    ENEMY_TIMEOUT_TRANSITION_FRAME_OFFSET,
    ENEMY_TIMEOUT_TRANSITION_SUBROUTINE_OFFSET,
    FRSCREEN_INNER_POINTER_OFFSET,
    FRSCREEN_NOTIFICATION_COUNTERS_OFFSET,
    FRSCREEN_STATE_ADDRESS,
    FRSCREEN_TIMELINE_SPAWN_GATE_OFFSET,
    INDEXED_ENEMY_REGISTRY_ADDRESS,
    INDEXED_ENEMY_TIMELINE_FIELD_OFFSET,
    STAGE_TIMELINE_FLAG_10_ADDRESS,
    TH08_TIMER_ELAPSED_OFFSET,
    TH08_TIMER_FRACTION_OFFSET,
    TIMELINE_MARKERS_ADDRESS,
    TIMELINE_SPAWN_SUPPRESSED_ADDRESS,
    _bullet_lifecycle_records,
    _bullet_template_geometry_record,
    _enemy_auxiliary_ecl_context_records,
    _enemy_attached_effect_records,
    _enemy_current_instruction_records,
    _enemy_main_ecl_callback_records,
    _enemy_main_ecl_inventory_record,
    _enemy_motion_state_records,
    _enemy_periodic_emission_records,
    _enemy_phase_transition_state_records,
    _enemy_source_record,
    _timeline_runtime_inventory_record,
    normalized_causal_component_records,
)


def _component(name: str, data: bytes) -> object:
    return SimpleNamespace(
        spec=SimpleNamespace(name=name),
        data=data,
    )


class NativeSnapshotProjectionTests(unittest.TestCase):
    def test_enemy_attached_effect_registry_normalizes_allocator_slots(
        self,
    ) -> None:
        enemy_blob = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG | 2,
        )
        struct.pack_into(
            "<i",
            enemy_blob,
            ENEMY_ATTACHED_EFFECT_COUNT_OFFSET,
            4,
        )
        struct.pack_into(
            "<4I",
            enemy_blob,
            ENEMY_ATTACHED_EFFECT_POINTERS_OFFSET,
            EFFECT_POOL_BASE + 7 * EFFECT_SLOT_STRIDE,
            0,
            EFFECT_POOL_BASE + 511 * EFFECT_SLOT_STRIDE,
            EFFECT_POOL_BASE + 1,
        )
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_SECONDARY_FLAGS_OFFSET,
            (1 << 3) | (1 << 6),
        )
        struct.pack_into(
            "<h",
            enemy_blob,
            ENEMY_DEATH_CALLBACK_SUBROUTINE_OFFSET,
            45,
        )

        result = _enemy_attached_effect_records(bytes(enemy_blob))

        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertTrue(row["active"])
        self.assertTrue(row["boss"])
        self.assertEqual(row["death_mode"], 0)
        self.assertTrue(row["death_latch"])
        self.assertTrue(row["no_death"])
        self.assertEqual(row["death_callback_subroutine"], 45)
        self.assertEqual(row["attached_effect_count"], 4)
        self.assertTrue(row["count_valid"])
        self.assertEqual(
            [reference["effect_slot"] for reference in row["references"]],
            [7, None, 511, None],
        )
        self.assertEqual(
            [reference["present"] for reference in row["references"]],
            [True, False, True, True],
        )

    def test_enemy_state2_retains_causal_timed_motion_root(self) -> None:
        enemy_blob = bytearray(ENEMY_STRIDE)
        flags = ENEMY_ACTIVE_FLAG | (2 << 12) | (5 << 14)
        struct.pack_into(
            "<fff",
            enemy_blob,
            ENEMY_MOTION_TIMED_DISPLACEMENT_OFFSET,
            96.0,
            -48.0,
            0.0,
        )
        struct.pack_into(
            "<fff",
            enemy_blob,
            ENEMY_MOTION_ORBIT_CENTER_OFFSET,
            80.0,
            40.0,
            0.0,
        )
        struct.pack_into(
            "<iIi",
            enemy_blob,
            ENEMY_MOTION_TIMER_OFFSET,
            -999,
            0x3F000000,
            7,
        )
        struct.pack_into(
            "<i",
            enemy_blob,
            ENEMY_MOTION_DURATION_OFFSET,
            12,
        )
        inventory = SimpleNamespace(
            observations=(
                SimpleNamespace(
                    slot=0,
                    enemy_pointer=ENEMY_POOL_BASE,
                    enemy_flags=flags,
                ),
            )
        )

        result = _enemy_motion_state_records(bytes(enemy_blob), inventory)

        row = result["rows"][0]
        self.assertEqual(row["movement_state"], 2)
        self.assertEqual(row["timed_mode"], 5)
        self.assertEqual(row["timed_displacement"], [96.0, -48.0, 0.0])
        self.assertEqual(row["orbit_center_position"], [80.0, 40.0, 0.0])
        self.assertEqual(row["motion_timer_fraction_bits"], 0x3F000000)
        self.assertEqual(row["motion_timer_elapsed"], 7)
        self.assertEqual(row["motion_duration"], 12)

    def test_enemy_phase_transition_retains_timer_and_successor_registry(
        self,
    ) -> None:
        enemy_blob = bytearray(ENEMY_STRIDE)
        struct.pack_into(
            "<iii",
            enemy_blob,
            ENEMY_HITPOINTS_OFFSET,
            1200,
            1800,
            1800,
        )
        struct.pack_into(
            "<4i",
            enemy_blob,
            ENEMY_HEALTH_TRANSITION_THRESHOLDS_OFFSET,
            500,
            -1,
            -1,
            -1,
        )
        struct.pack_into(
            "<4i",
            enemy_blob,
            ENEMY_HEALTH_TRANSITION_SUCCESSORS_OFFSET,
            28,
            29,
            30,
            31,
        )
        struct.pack_into(
            "<iIi",
            enemy_blob,
            ENEMY_PHASE_TIMER_OFFSET,
            98,
            0x3F000000,
            99,
        )
        struct.pack_into(
            "<ii",
            enemy_blob,
            ENEMY_TIMEOUT_TRANSITION_FRAME_OFFSET,
            2400,
            28,
        )
        inventory = SimpleNamespace(
            observations=(
                SimpleNamespace(slot=0, enemy_pointer=ENEMY_POOL_BASE),
            )
        )

        result = _enemy_phase_transition_state_records(
            bytes(enemy_blob),
            inventory,
        )

        row = result["rows"][0]
        self.assertEqual(row["current_hitpoints"], 1200)
        self.assertEqual(row["maximum_hitpoints"], 1800)
        self.assertEqual(row["phase_start_hitpoints"], 1800)
        self.assertEqual(row["health_thresholds"], [500, -1, -1, -1])
        self.assertEqual(
            row["health_successor_subroutines"],
            [28, 29, 30, 31],
        )
        self.assertEqual(row["phase_timer_previous"], 98)
        self.assertEqual(row["phase_timer_fraction_bits"], 0x3F000000)
        self.assertEqual(row["phase_timer_elapsed"], 99)
        self.assertEqual(row["timeout_frame"], 2400)
        self.assertEqual(row["timeout_subroutine"], 28)

    def test_enemy_periodic_emission_retains_descriptor_and_timer(
        self,
    ) -> None:
        enemy_blob = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_MAIN_ECL_VM_OFFSET,
            0x00610000,
        )
        descriptor = struct.pack(
            "<iHHBBH8I",
            0,
            0x61,
            44,
            0,
            0xFF,
            0x50,
            0x00060002,
            1,
            1,
            0x3F800000,
            0x3F000000,
            0,
            0,
            0x203,
        )
        enemy_blob[
            ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET :
            ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET + len(descriptor)
        ] = descriptor
        struct.pack_into("<i", enemy_blob, ENEMY_HITPOINTS_OFFSET, 100)
        struct.pack_into(
            "<i",
            enemy_blob,
            ENEMY_PERIODIC_EMISSION_PERIOD_OFFSET,
            2,
        )
        struct.pack_into(
            "<iIi",
            enemy_blob,
            ENEMY_PERIODIC_EMISSION_TIMER_OFFSET,
            0,
            0,
            1,
        )
        inventory, _record = _enemy_main_ecl_inventory_record(
            bytes(enemy_blob)
        )

        result = _enemy_periodic_emission_records(
            bytes(enemy_blob),
            inventory,
        )

        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertTrue(row["enabled"])
        self.assertEqual(row["hitpoints"], 100)
        self.assertEqual(row["period"], 2)
        self.assertEqual(row["timer_elapsed"], 1)
        self.assertEqual(row["stored_fire_descriptor"]["opcode"], 0x61)
        self.assertEqual(
            row["stored_fire_descriptor"]["retained_bytes_hex"],
            descriptor.hex(),
        )

    def test_timeline_runtime_inventory_is_model_consumable(self) -> None:
        ecl_file_base = 0x00600000
        timeline_start = ecl_file_base + 0x100
        ecl_data_end = ecl_file_base + 0x140
        header = bytearray(0x48)
        struct.pack_into("<IHH", header, 0, 0x800, 2, 1)
        relocated = [timeline_start, ecl_data_end] + [ecl_data_end] * 14
        struct.pack_into("<16I", header, 8, *relocated)

        instruction = struct.pack(
            "<iHBB6I",
            77,
            0,
            32,
            0x08,
            35,
            0x42C80000,
            0xC1000000,
            0,
            6,
            0,
        )
        runtime_table = bytearray(16 * 16)
        struct.pack_into(
            "<iIiI",
            runtime_table,
            0,
            76,
            0,
            77,
            timeline_start,
        )
        indexed_registry = bytearray(8 * 4)
        struct.pack_into("<I", indexed_registry, 0, ENEMY_POOL_BASE)
        memory = {
            ECL_FILE_CONTEXT_ADDRESS: struct.pack(
                "<II",
                ecl_file_base,
                ecl_file_base + 0x48,
            ),
            ecl_file_base: bytes(header),
            timeline_start: instruction,
            TH08_TIMELINE_RUNTIME_BASE: bytes(runtime_table),
            TIMELINE_MARKERS_ADDRESS: struct.pack("<4i", 4, -1, -1, -1),
            TIMELINE_SPAWN_SUPPRESSED_ADDRESS: struct.pack("<I", 0),
            FRSCREEN_STATE_ADDRESS + FRSCREEN_TIMELINE_SPAWN_GATE_OFFSET: b"\x00",
            FRSCREEN_STATE_ADDRESS + FRSCREEN_INNER_POINTER_OFFSET: (
                struct.pack("<I", 0)
            ),
            INDEXED_ENEMY_REGISTRY_ADDRESS: bytes(indexed_registry),
            ENEMY_POOL_BASE + INDEXED_ENEMY_TIMELINE_FIELD_OFFSET: (
                struct.pack("<H", 0x2345)
            ),
            ENEMY_POOL_BASE + ENEMY_FLAGS_OFFSET: struct.pack(
                "<I",
                ENEMY_ACTIVE_FLAG,
            ),
            ECL_DIFFICULTY_MASK_ADDRESS: b"\x08",
            STAGE_TIMELINE_FLAG_10_ADDRESS: b"\x01",
        }

        def read(address: int, size: int) -> bytes:
            for base, blob in memory.items():
                if base <= address and address + size <= base + len(blob):
                    offset = address - base
                    return blob[offset : offset + size]
            raise AssertionError(f"unexpected read {address:#x}+{size:#x}")

        result = _timeline_runtime_inventory_record(
            SimpleNamespace(read=read)
        )

        self.assertEqual(result["ecl_file"]["file_base"], ecl_file_base)
        self.assertEqual(result["ecl_file"]["timeline_count"], 1)
        self.assertEqual(result["difficulty_mask"], 0x08)
        self.assertTrue(result["stage_flag_10"])
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual(row["previous_elapsed"], 76)
        self.assertEqual(row["elapsed"], 77)
        self.assertEqual(row["current_instruction"]["static_offset"], 0x100)
        self.assertEqual(row["current_instruction"]["opcode"], 0)
        self.assertEqual(row["current_instruction"]["payload_hex"], instruction[8:].hex())
        self.assertEqual(result["external"]["markers"], [4, -1, -1, -1])
        self.assertFalse(result["external"]["stage_transition_busy"])
        self.assertFalse(result["external"]["conditional_gate_blocked"])
        self.assertTrue(result["external"]["indexed_enemies"][0]["active"])
        self.assertEqual(
            result["external"]["indexed_enemies"][0]["field_2d30"],
            0x2345,
        )

    def test_auxiliary_ecl_context_retains_active_vm_and_instruction(
        self,
    ) -> None:
        enemy_blob = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        instruction_pointer = 0x00600000
        context_pointer = 0x00700000
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_MAIN_ECL_VM_OFFSET,
            0x00610000,
        )
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
            context_pointer,
        )
        context = bytearray(CONTEXT_ACTIVE_VM_OFFSET + ACTIVE_VM_BYTES)
        struct.pack_into("<I", context, CONTEXT_TARGET_OFFSET, 35)
        struct.pack_into("<H", context, CONTEXT_CALL_DEPTH_OFFSET, 0)
        active_base = CONTEXT_ACTIVE_VM_OFFSET
        struct.pack_into("<I", context, active_base, instruction_pointer)
        struct.pack_into("<i", context, active_base + 0x04, 12)
        struct.pack_into("<I", context, active_base + 0x08, 0)
        struct.pack_into("<i", context, active_base + 0x0C, 13)
        struct.pack_into("<iIi", context, active_base + 0x90, 4, 0, 5)
        struct.pack_into(
            "<I",
            context,
            active_base + ACTIVE_VM_AUXILIARY_MARKER_OFFSET,
            1,
        )
        instruction = struct.pack(
            "<iHHBBH",
            14,
            0x60,
            16,
            0,
            0x08,
            0,
        ) + b"\x01\x02\x03\x04"
        memory = {
            context_pointer: bytes(context),
            instruction_pointer: instruction,
        }

        inventory, _record = _enemy_main_ecl_inventory_record(
            bytes(enemy_blob)
        )

        def read(address: int, size: int) -> bytes:
            for base, blob in memory.items():
                if base <= address and address + size <= base + len(blob):
                    offset = address - base
                    return blob[offset : offset + size]
            raise AssertionError(f"unexpected read {address:#x}+{size:#x}")

        result = _enemy_auxiliary_ecl_context_records(
            SimpleNamespace(read=read),
            inventory,
        )

        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual(row["slot"], 0)
        self.assertEqual(row["auxiliary_index"], 0)
        self.assertEqual(row["target_subroutine"], 35)
        self.assertEqual(row["call_depth"], 0)
        self.assertEqual(row["state"]["instruction_pointer"], instruction_pointer)
        self.assertEqual(row["state"]["timer_elapsed"], 13)
        self.assertEqual(row["state"]["delay_timer_elapsed"], 5)
        self.assertEqual(row["state"]["auxiliary_marker"], 1)
        self.assertEqual(row["current_instruction"]["opcode"], 0x60)
        self.assertEqual(row["current_instruction"]["payload_hex"], "01020304")

    def test_enemy_vm_inventory_and_current_instruction_are_deterministic(
        self,
    ) -> None:
        enemy_blob = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        vm_base = ENEMY_MAIN_ECL_VM_OFFSET
        instruction_pointer = 0x00600000
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        struct.pack_into("<I", enemy_blob, vm_base, instruction_pointer)
        struct.pack_into("<I", enemy_blob, vm_base + 0x04, 0x3F000000)
        struct.pack_into("<i", enemy_blob, vm_base + 0x08, 17)
        callback_function = 0x00420000
        callback_record_pointer = 0x00600100
        struct.pack_into(
            "<II",
            enemy_blob,
            vm_base + 0x10,
            callback_function,
            callback_record_pointer,
        )
        instruction = struct.pack(
            "<iHHBBH",
            18,
            0x60,
            16,
            0,
            0x08,
            0,
        ) + b"\x01\x02\x03\x04"
        callback_record = struct.pack(
            "<iHHBBH",
            18,
            0x88,
            16,
            0,
            0x08,
            0,
        ) + b"\x05\x06\x07\x08"
        memory = {
            instruction_pointer: instruction,
            callback_record_pointer: callback_record,
        }

        inventory, record = _enemy_main_ecl_inventory_record(bytes(enemy_blob))
        reader = SimpleNamespace(
            read=lambda address, size: next(
                blob[
                    address - base :
                    address - base + size
                ]
                for base, blob in memory.items()
                if base <= address and address + size <= base + len(blob)
            )
        )
        instructions = _enemy_current_instruction_records(
            reader,
            inventory,
        )
        callbacks = _enemy_main_ecl_callback_records(
            reader,
            bytes(enemy_blob),
            inventory,
        )

        self.assertNotIn("decode_ms", record)
        self.assertEqual(record["active_slots"], 1)
        self.assertEqual(record["valid_vms"], 1)
        self.assertEqual(record["rows"][0][0], 0)
        self.assertEqual(record["rows"][0][1], ENEMY_POOL_BASE)
        self.assertEqual(
            instructions,
            {
                "schema": "th08-active-enemy-current-ecl-instruction-v1",
                "scope": "current_instruction_only_no_control_flow_closure",
                "rows": [
                    {
                        "slot": 0,
                        "instruction_pointer": instruction_pointer,
                        "time": 18,
                        "opcode": 0x60,
                        "size": 16,
                        "difficulty_mask": 0x08,
                        "parameter_mask": 0,
                        "payload_hex": "01020304",
                    }
                ],
            },
        )
        callback = callbacks["rows"][0]["installed_callback"]
        self.assertEqual(callback["function_pointer"], callback_function)
        self.assertEqual(
            callback["argument_record_pointer"],
            callback_record_pointer,
        )
        self.assertEqual(
            callback["argument_record_instruction"]["opcode"],
            0x88,
        )

    def test_manager_template_singleton_is_a_complete_hostile_source(self) -> None:
        enemy_blob = bytearray(ENEMY_STRIDE)
        instruction_pointer = 0x00610000
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_FLAGS_OFFSET,
            ENEMY_ACTIVE_FLAG,
        )
        struct.pack_into(
            "<I",
            enemy_blob,
            ENEMY_MAIN_ECL_VM_OFFSET,
            instruction_pointer,
        )
        instruction = struct.pack(
            "<iHHBBH",
            9,
            0x61,
            16,
            0,
            0x08,
            0,
        ) + b"\x10\x20\x30\x40"
        reader = SimpleNamespace(
            read=lambda address, size: instruction[
                address - instruction_pointer :
                address - instruction_pointer + size
            ]
        )

        source = _enemy_source_record(
            reader,
            enemy_blob=bytes(enemy_blob),
            pool_base=TH08_ENEMY_MANAGER_TEMPLATE_BASE,
            pool_size=1,
            source_role="enemy_manager_template_or_special_singleton",
        )

        self.assertTrue(source["active"])
        self.assertEqual(
            source["main_ecl_vm_inventory"]["rows"][0][1],
            TH08_ENEMY_MANAGER_TEMPLATE_BASE,
        )
        self.assertEqual(
            source["current_ecl_instructions"]["rows"][0]["opcode"],
            0x61,
        )
        self.assertEqual(source["periodic_emission_state"]["rows"][0]["slot"], 0)
        self.assertEqual(source["auxiliary_ecl_contexts"]["rows"], [])
        self.assertEqual(
            len(
                source["emission_state"]["rows"][0]["descriptor"][
                    "transform_program_hex"
                ]
            ),
            18 * 24 * 2,
        )

    def test_bullet_template_geometry_is_retained_without_clamping(self) -> None:
        blob = bytearray(BULLET_TEMPLATE_COUNT * BULLET_TEMPLATE_STRIDE)
        type_two = 2 * BULLET_TEMPLATE_STRIDE
        struct.pack_into(
            "<fff",
            blob,
            type_two + BULLET_TEMPLATE_COLLISION_OFFSET,
            2.0,
            3.0,
            4.0,
        )
        reader = SimpleNamespace(
            read=lambda address, size: bytes(
                blob[
                    address - BULLET_MANAGER_BASE :
                    address - BULLET_MANAGER_BASE + size
                ]
            )
        )

        record = _bullet_template_geometry_record(reader)

        self.assertEqual(len(record["rows"]), 21)
        self.assertEqual(
            record["rows"][2],
            {
                "type": 2,
                "width": 2.0,
                "height": 3.0,
                "half_width": 1.0,
                "half_height": 1.5,
                "collision_z": 4.0,
            },
        )

    def test_bullet_lifecycle_retains_state_and_both_native_timers(self) -> None:
        blob = bytearray(BULLET_POOL_SIZE * BULLET_STRIDE)
        slot = 1192
        base = slot * BULLET_STRIDE
        struct.pack_into("<H", blob, base + BULLET_STATE_OFFSET, 2)
        struct.pack_into(
            "<I",
            blob,
            base + BULLET_TIMER_D80_OFFSET + TH08_TIMER_FRACTION_OFFSET,
            0x3F000000,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_TIMER_D80_OFFSET + TH08_TIMER_ELAPSED_OFFSET,
            7,
        )
        struct.pack_into(
            "<I",
            blob,
            base + BULLET_TIMER_D8C_OFFSET + TH08_TIMER_FRACTION_OFFSET,
            0x3E800000,
        )
        struct.pack_into(
            "<i",
            blob,
            base + BULLET_TIMER_D8C_OFFSET + TH08_TIMER_ELAPSED_OFFSET,
            11,
        )

        records = _bullet_lifecycle_records(
            blob,
            [
                SimpleNamespace(
                    slot=slot,
                    callback_phase_state=3,
                    callback_aux_state=4,
                )
            ],
        )

        self.assertEqual(
            records,
            [
                {
                    "slot": slot,
                    "state": 2,
                    "timer_d80_fraction_bits": 0x3F000000,
                    "timer_d80_elapsed": 7,
                    "timer_d8c_fraction_bits": 0x3E800000,
                    "timer_d8c_elapsed": 11,
                    "callback_phase_state": 3,
                    "callback_aux_state": 4,
                }
            ],
        )

    def test_model_payload_is_explicit_opt_in(self) -> None:
        projection = CollisionControlProjection(
            payload={"schema": COLLISION_CONTROL_PROJECTION_SCHEMA, "bullets": []},
            sha256="a" * 64,
            summary={"bullet_count": 0},
        )

        compact = projection.record()
        retained = projection.record(include_model_payload=True)

        self.assertNotIn("model_payload", compact)
        self.assertEqual(retained["model_payload"], projection.payload)
        self.assertEqual(retained["sha256"], compact["sha256"])

    def test_enemy_render_prefix_does_not_change_causal_digest(self) -> None:
        left = bytearray(ENEMY_STRIDE)
        right = bytearray(left)
        right[ENEMY_ANM_PREFIX_SIZE - 1] = 1

        left_record = normalized_causal_component_records(
            [_component("ordinary_enemy_ecl_and_callback_roots", left)]
        )
        right_record = normalized_causal_component_records(
            [_component("ordinary_enemy_ecl_and_callback_roots", right)]
        )

        self.assertEqual(left_record, right_record)

    def test_enemy_ecl_tail_change_changes_causal_digest(self) -> None:
        left = bytearray(ENEMY_STRIDE)
        right = bytearray(left)
        right[ENEMY_ANM_PREFIX_SIZE] = 1

        left_record = normalized_causal_component_records(
            [_component("ordinary_enemy_ecl_and_callback_roots", left)]
        )
        right_record = normalized_causal_component_records(
            [_component("ordinary_enemy_ecl_and_callback_roots", right)]
        )

        self.assertNotEqual(left_record, right_record)

    def test_broad_player_bytes_are_explicitly_replaced(self) -> None:
        left = normalized_causal_component_records(
            [
                _component(
                    "player_state_through_resource_transitions",
                    b"\x00" * 32,
                )
            ]
        )
        right = normalized_causal_component_records(
            [
                _component(
                    "player_state_through_resource_transitions",
                    b"\x01" * 32,
                )
            ]
        )

        self.assertEqual(left, right)
        self.assertEqual(
            left[0]["mode"],
            "replaced_by_explicit_collision_control_fields",
        )

    def test_unclassified_component_remains_byte_exact(self) -> None:
        left = normalized_causal_component_records(
            [_component("gameplay_rng_exact", b"\x00" * 8)]
        )
        right = normalized_causal_component_records(
            [_component("gameplay_rng_exact", b"\x00" * 7 + b"\x01")]
        )

        self.assertNotEqual(left, right)

    def test_frscreen_render_consumed_notification_counter_is_excluded(
        self,
    ) -> None:
        left = bytearray(0x118)
        right = bytearray(left)
        right[FRSCREEN_NOTIFICATION_COUNTERS_OFFSET] = 0x40

        left_record = normalized_causal_component_records(
            [_component("scheduler_gate_globals", left)]
        )
        right_record = normalized_causal_component_records(
            [_component("scheduler_gate_globals", right)]
        )

        self.assertEqual(left_record, right_record)

        right[0] = 1
        other_change = normalized_causal_component_records(
            [_component("scheduler_gate_globals", right)]
        )
        self.assertNotEqual(left_record, other_change)


if __name__ == "__main__":
    unittest.main()
