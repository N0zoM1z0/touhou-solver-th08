from __future__ import annotations

import math
import struct
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from th08_ecl_tool.core import SubInstruction, Subroutine, parse_ecl
from th08_enemy_spawn_model import (
    ENEMY_FLAG_CONTACT,
    ENEMY_FLAG_LINKED_CHILD,
)
from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    FutureTaggedBulletCallback,
)
from th08_ordinary_future_sources import (
    FutureSourceClosureError,
    _NativeEnemyPool,
    _VmState,
    _advance_motion,
    _attach_later_tagged_callbacks,
    _define_bullet_transform,
    _direct_fire_count,
    _direct_fire_type_color,
    _eval_float_operand,
    _execute_auxiliary,
    _execute_main,
    _execute_source_update,
    _health_transition_hp_loss_upper_bound,
    _integrate_motion,
    _instruction_map,
    _motion_state,
    _source_initialized_spawn,
    _spawn_vm,
    _tagged_callback_action,
    project_ordinary_future_sources,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ECL = parse_ecl(REPO_ROOT / "artifacts" / "decoded" / "ecldata5.ecl")
ECL3 = parse_ecl(REPO_ROOT / "artifacts" / "decoded" / "ecldata3.ecl")
ECL_BASE = 0x10000000
SOURCE_POINTER = 0x0057D2F0


def _bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _synthetic_subroutine(
    index: int,
    start: int,
    rows: tuple[tuple[int, int, int, tuple[int, ...]], ...],
) -> Subroutine:
    instructions: list[SubInstruction] = []
    offset = start
    for time, opcode, parameter_mask, arguments in rows:
        size = 12 + 4 * len(arguments)
        instructions.append(
            SubInstruction(
                offset=offset,
                time=time,
                opcode=opcode,
                size=size,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=parameter_mask,
                arguments=arguments,
            )
        )
        offset += size
    return Subroutine(
        index=index,
        start=start,
        end=offset,
        instructions=tuple(instructions),
        footer_offset=-1,
    )


def _inventory(rows: list[list[object]]) -> dict[str, object]:
    return {
        "invalid_active_vms": 0,
        "invalid_auxiliary_contexts": 0,
        "invalid_auxiliary_context_rows": [],
        "rows": rows,
    }


def _empty_source_group() -> dict[str, object]:
    return {
        "enemy_bodies": [],
        "main_ecl_vm_inventory": _inventory([]),
        "main_ecl_installed_callbacks": {"rows": []},
        "periodic_emission_state": {"rows": []},
        "emission_state": {"rows": []},
        "motion_state": {"rows": []},
        "phase_transition_state": {"rows": []},
        "auxiliary_ecl_contexts": {"rows": []},
    }


def _damage_envelope(*, active_raw_damage: int = 0) -> dict[str, object]:
    return {
        "schema": (
            "th08-route2-normal-shot-health-transition-damage-envelope-v1"
        ),
        "complete": True,
        "root_conditions": {"fixture": True},
        "active_raw_damage_upper_bound": active_raw_damage,
        "future_raw_damage_by_cadence_phase": [0] * 20,
        "future_cadence_phase_support": [0],
        "cadence_length": 20,
        "player_damage_bonus_upper_ratio": [106, 100],
    }


def _payload() -> dict[str, object]:
    first_timeline = ECL.timelines[0].instructions[0]
    main_row = [
        0,
        SOURCE_POINTER,
        0x01000049,
        ECL_BASE + 11480,
        0,
        0,
        [0] * 8,
        [0] * 8,
        [0] * 4,
    ]
    callback = {
        "enemy_pointer": SOURCE_POINTER,
        "installed_callback": {"function_pointer": 0},
    }
    periodic = {
        "enemy_pointer": SOURCE_POINTER,
        "enabled": False,
    }
    emission = {
        "enemy_pointer": SOURCE_POINTER,
        "emission_offset": [0.0, 0.0, 0.0],
        "rank_speed_interval": [-0.15, 0.15],
        "rank_count_interval": [0, 0, 0, 0],
        "descriptor": {
            "transform_program_hex": (b"\0" * (18 * 24)).hex(),
        },
    }
    motion = {
        "enemy_pointer": SOURCE_POINTER,
        "movement_state": 0,
        "timed_mode": 0,
        "mirror_x": False,
        "base_position": [60.0, 32.0, 0.0],
        "relative_position": [0.0, 0.0, 0.0],
        "velocity": [0.0, 0.0, 0.0],
        "world_position": [60.0, 32.0, 0.0],
        "angle": 0.0,
        "angular_velocity": 0.0,
        "speed": 0.0,
        "speed_acceleration": 0.0,
        "orbit_angle": 0.0,
        "orbit_angular_velocity": 0.0,
        "orbit_radius": 0.0,
        "orbit_radius_acceleration": 0.0,
        "timed_displacement": [0.0, 0.0, 0.0],
        "orbit_center_position": [0.0, 0.0, 0.0],
        "motion_timer_elapsed": 0,
        "motion_timer_fraction_bits": 0,
        "motion_duration": 0,
    }
    auxiliary = {
        "enemy_pointer": SOURCE_POINTER,
        "auxiliary_index": 0,
        "call_depth": 0,
        "installed_callback": {"function_pointer": 0},
        "state": {
            "instruction_pointer": ECL_BASE + 11812,
            "timer_elapsed": 0,
            "timer_fraction_bits": 0,
            "timer_previous": -1,
            "local_projection": {
                "integer_locals": [0] * 8,
                "float_local_bits": [
                    _bits(0.0),
                    _bits(1.0),
                    _bits(1.0),
                    0,
                    0,
                    0,
                    0,
                    0,
                ],
                "scratch_integers": [0, 0, 2, 0],
            },
        },
    }
    manager = {
        "source_role": "enemy_manager_template_or_special_singleton",
        "enemy_bodies": [
            {
                "pointer": SOURCE_POINTER,
                "flags": 0x01000049,
                "half_width": 8.0,
                "half_height": 8.0,
            }
        ],
        "main_ecl_vm_inventory": _inventory([main_row]),
        "main_ecl_installed_callbacks": {"rows": [callback]},
        "periodic_emission_state": {"rows": [periodic]},
        "emission_state": {"rows": [emission]},
        "motion_state": {"rows": [motion]},
        "phase_transition_state": {
            "rows": [
                {
                    "enemy_pointer": SOURCE_POINTER,
                    "current_hitpoints": 100,
                    "maximum_hitpoints": 100,
                    "phase_start_hitpoints": 100,
                    "health_thresholds": [-1, -1, -1, -1],
                    "health_successor_subroutines": [-1, -1, -1, -1],
                    "phase_timer_previous": -1,
                    "phase_timer_fraction_bits": 0,
                    "phase_timer_elapsed": 0,
                    "timeout_frame": -1,
                    "timeout_subroutine": -1,
                }
            ]
        },
        "auxiliary_ecl_contexts": {"rows": [auxiliary]},
    }
    ordinary = _empty_source_group()
    return {
        "schema": "th08-native-snapshot-collision-control-projection-v14",
        "compact_state": {
            "manager_frame": 2129,
            "time_scale_bits": 0x3F800000,
            "rng_state": 1,
            "rng_calls": 0,
            "player_x": 192.0,
            "player_y": 432.0,
            "player_phase": 0,
            "predeath_counter": 10,
            "spell_id": None,
        },
        "route2_health_transition_damage_envelope": _damage_envelope(),
        "enemy_manager_template_source": manager,
        "enemy_main_ecl_vm_inventory": ordinary[
            "main_ecl_vm_inventory"
        ],
        "enemy_bodies": ordinary["enemy_bodies"],
        "enemy_main_ecl_installed_callbacks": ordinary[
            "main_ecl_installed_callbacks"
        ],
        "enemy_periodic_emission_state": ordinary[
            "periodic_emission_state"
        ],
        "enemy_emission_state": ordinary["emission_state"],
        "enemy_motion_state": ordinary["motion_state"],
        "enemy_phase_transition_state": ordinary[
            "phase_transition_state"
        ],
        "enemy_auxiliary_ecl_contexts": ordinary[
            "auxiliary_ecl_contexts"
        ],
        "bullet_template_geometry": {
            "rows": [
                {
                    "type": 2,
                    "half_width": 2.0,
                    "half_height": 2.0,
                }
            ]
        },
        "stage_timeline_runtime": {
            "difficulty_mask": 8,
            "stage_flag_10": False,
            "ecl_file": {
                "magic": 0x800,
                "file_base": ECL_BASE,
                "subroutine_count": len(ECL.subroutines),
                "timeline_count": len(ECL.timelines),
                "static_data_end_offset": ECL.header.data_end_offset,
                "canonical_sha256": ECL.sha256,
            },
            "rows": [
                {
                    "elapsed": 0,
                    "fraction_bits": 0,
                    "current_instruction": {
                        "static_offset": first_timeline.offset,
                        "terminal": True,
                    },
                }
            ],
            "external": {
                "markers": [-1, -1, -1, -1],
                "stage_transition_busy": False,
                "spawn_suppressed": False,
                "conditional_gate_blocked": False,
                "indexed_enemies": [None] * 8,
            },
        },
    }


class OrdinaryFutureSourceTests(unittest.TestCase):
    def test_callback_12_and_14_lower_from_vm_filter_state(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0x100000] + [0] * 7,
            float_locals=[
                FloatInterval.point(0.75),
                FloatInterval.point(2.5),
            ]
            + [FloatInterval.point(0.0)] * 6,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(identity="synthetic-callback-source")

        def instruction(index: int) -> SubInstruction:
            return SubInstruction(
                offset=0x4240,
                time=0,
                opcode=0x88,
                size=20,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(index, 0),
            )

        freeze = _tagged_callback_action(
            source=source,
            vm=vm,
            instruction=instruction(12),
            frame=7,
        )
        visual = _tagged_callback_action(
            source=source,
            vm=vm,
            instruction=instruction(13),
            frame=7,
        )
        phase = _tagged_callback_action(
            source=source,
            vm=vm,
            instruction=instruction(14),
            frame=7,
        )

        self.assertIsInstance(freeze, FutureTaggedBulletCallback)
        assert freeze is not None
        self.assertEqual(freeze.callback_angle, FloatInterval.point(0.75))
        self.assertEqual(freeze.callback_speed, FloatInterval.point(2.5))
        self.assertIsNone(visual)
        self.assertIsInstance(phase, FutureTaggedBulletCallback)
        assert phase is not None
        self.assertIsNone(phase.callback_angle)

    def test_complete_copied_vm_block_is_accepted_without_narrowing(self) -> None:
        payload = deepcopy(_payload())
        row = payload["enemy_manager_template_source"][
            "main_ecl_vm_inventory"
        ]["rows"][0]
        row.extend(
            (
                [_bits(12.0), _bits(-4.0)],
                [1, 2, 3, 4],
                [_bits(5.0), _bits(6.0), _bits(7.0), _bits(8.0)],
            )
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(len(closure.direct_fire_events), 1)

    def test_active_spell_bypasses_source_unreached_rank_interpolation(
        self,
    ) -> None:
        ordinary_payload = deepcopy(_payload())
        spell_payload = deepcopy(ordinary_payload)
        spell_payload["compact_state"]["spell_id"] = 103

        ordinary = project_ordinary_future_sources(
            ordinary_payload,
            ECL,
            horizon_frames=1,
        )
        spell = project_ordinary_future_sources(
            spell_payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(ordinary.projection.source_closure_complete)
        self.assertTrue(spell.projection.source_closure_complete)
        self.assertEqual(len(ordinary.direct_fire_events), 1)
        self.assertEqual(len(spell.direct_fire_events), 1)
        ordinary_event = ordinary.direct_fire_events[0]
        spell_event = spell.direct_fire_events[0]
        self.assertEqual(ordinary_event.speed1.lower, 0.85)
        self.assertEqual(ordinary_event.speed1.upper, 2.15)
        self.assertEqual(spell_event.speed1.lower, 1.0)
        self.assertEqual(spell_event.speed1.upper, 2.0)
        self.assertEqual(spell_event.speed2.upper, spell_event.speed2.lower)

    def test_spell_does_not_read_dormant_rank_fields(self) -> None:
        payload = deepcopy(_payload())
        payload["compact_state"]["spell_id"] = 103
        emission = payload["enemy_manager_template_source"][
            "emission_state"
        ]["rows"][0]
        emission["rank_speed_interval"] = "source-unreached"
        emission["rank_count_interval"] = "source-unreached"

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(len(closure.direct_fire_events), 1)

    def test_spell103_source_exact_root_closes_global_horizon(self) -> None:
        payload = deepcopy(_payload())
        payload["compact_state"]["spell_id"] = 103
        manager = payload["enemy_manager_template_source"]
        main = manager["main_ecl_vm_inventory"]["rows"][0]
        # Route spell 103 is waiting at the first time-90 body instruction.
        # The source-exact 0x2762 random angle is set-valued, not UNKNOWN.
        main[3] = ECL_BASE + 0x6420
        main[5] = 0
        manager["auxiliary_ecl_contexts"]["rows"] = []
        manager["phase_transition_state"]["rows"][0].update(
            timeout_frame=3000,
            timeout_subroutine=53,
        )
        payload["bullet_template_geometry"]["rows"].append(
            {"type": 16, "half_width": 4.0, "half_height": 4.0}
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=80,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 80)
        self.assertEqual(closure.direct_fire_events, ())

    def test_spell103_random_angle_advances_to_tagged_birth_boundary(
        self,
    ) -> None:
        payload = deepcopy(_payload())
        payload["compact_state"]["spell_id"] = 103
        manager = payload["enemy_manager_template_source"]
        main = manager["main_ecl_vm_inventory"]["rows"][0]
        main[3] = ECL_BASE + 0x6420
        main[5] = 0
        manager["auxiliary_ecl_contexts"]["rows"] = []
        manager["phase_transition_state"]["rows"][0].update(
            timeout_frame=3000,
            timeout_subroutine=53,
        )
        payload["bullet_template_geometry"]["rows"].append(
            {"type": 16, "half_width": 4.0, "half_height": 4.0}
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=139,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 90)
        self.assertIn(
            "unsupported future bullet flags",
            closure.causal_prefix_reason,
        )
        self.assertNotIn(
            "dynamic ECL float variable 10082",
            closure.causal_prefix_reason,
        )
        self.assertEqual(closure.direct_fire_events, ())

    def test_reached_stage3_main_arithmetic_and_transform_wave_closes(
        self,
    ) -> None:
        payload = deepcopy(_payload())
        manager = payload["enemy_manager_template_source"]
        main = manager["main_ecl_vm_inventory"]["rows"][0]
        main[3] = ECL_BASE + 0x230
        main[5] = 65
        main[6] = [0] * 8
        main[7] = [0] * 8
        main[8] = [0] * 4
        manager["auxiliary_ecl_contexts"]["rows"] = []
        timeline = payload["stage_timeline_runtime"]
        timeline["ecl_file"].update(
            subroutine_count=len(ECL3.subroutines),
            timeline_count=len(ECL3.timelines),
            static_data_end_offset=ECL3.header.data_end_offset,
            canonical_sha256=ECL3.sha256,
        )
        timeline["rows"] = [
            {
                "elapsed": 0,
                "fraction_bits": 0,
                "current_instruction": {
                    "static_offset": item.instructions[0].offset,
                    "terminal": True,
                },
            }
            for item in ECL3.timelines
        ]
        payload["bullet_template_geometry"]["rows"] = [
            {"type": value, "half_width": 2.0, "half_height": 2.0}
            for value in (1, 2, 6)
        ]

        closure = project_ordinary_future_sources(
            payload,
            ECL3,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 1)
        self.assertEqual(len(closure.direct_fire_events), 6)
        self.assertTrue(
            any(
                any(
                    record.kind == 0x20
                    for record in event.active_transform_records
                )
                for event in closure.direct_fire_events
            )
        )

    def test_dynamic_direct_fire_type_and_color_are_independent_i16s(
        self,
    ) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[2, 7, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        packed = (10001 << 16) | 10000

        self.assertEqual(
            _direct_fire_type_color(
                packed=packed,
                parameter_mask=0x03,
                vm=vm,
            ),
            (2, 7),
        )

    def test_transform_definition_writes_exact_native_record_layout(
        self,
    ) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[2, 0x20, 1, 40, -1, 0, 0, 0],
            float_locals=[
                FloatInterval.point(0.25),
                FloatInterval.point(-0.5),
            ]
            + [FloatInterval.point(0.0)] * 6,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(
            emission={
                "descriptor": {
                    "transform_program_hex": (
                        b"\0" * (18 * 24)
                    ).hex(),
                }
            }
        )
        instruction = SubInstruction(
            offset=0,
            time=0,
            opcode=0x6F,
            size=40,
            byte_08=0,
            difficulty_mask=0xFF,
            parameter_mask=0x7F,
            arguments=(
                10000,
                10001,
                10002,
                10003,
                10004,
                _bits(10016.0),
                _bits(10017.0),
            ),
        )

        _define_bullet_transform(
            source=source,
            vm=vm,
            instruction=instruction,
            aim_angle=FloatInterval.point(0.0),
        )

        program = bytes.fromhex(
            source.emission["descriptor"]["transform_program_hex"]
        )
        self.assertEqual(
            struct.unpack_from("<ffiiII", program, 2 * 24),
            (0.25, -0.5, 40, -1, 0x20, 1),
        )
        vm.float_locals[0] = FloatInterval(0.2, 0.3)
        with self.assertRaisesRegex(ValueError, "set-valued"):
            _define_bullet_transform(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=FloatInterval.point(0.0),
            )

    def test_main_float_add_uses_same_captured_local_semantics(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[
                FloatInterval.point(0.0),
                FloatInterval.point(2.25),
            ]
            + [FloatInterval.point(0.0)] * 6,
            scratch_integers=[0] * 4,
        )
        vm.float_local_aim_coefficients[1] = 1.0
        source = SimpleNamespace(identity="test", main=vm)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x19,
                size=24,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x03,
                arguments=(
                    _bits(10016.0),
                    _bits(10017.0),
                    _bits(1.5),
                ),
            ),
            24: SubInstruction(
                offset=24,
                time=0,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        _execute_main(
            source=source,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
            ecl=ECL,
            remaining_horizon=1,
        )

        self.assertEqual(vm.float_locals[0], FloatInterval.point(3.75))
        self.assertEqual(vm.float_local_aim_coefficients[0], 1.0)

    def test_auxiliary_normalize_and_bottom_return_are_exact(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval(3.0, 3.2)]
            + [FloatInterval.point(0.0)] * 7,
            scratch_integers=[0] * 4,
        )
        vm.float_local_aim_coefficients[0] = 1.0
        source = SimpleNamespace(identity="test")
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x25,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(_bits(10016.0),),
            ),
            16: SubInstruction(
                offset=16,
                time=0,
                opcode=0x35,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        self.assertEqual(
            _execute_auxiliary(
                source=source,
                vm=vm,
                instructions=instructions,
                difficulty_mask=0x08,
                frame=1,
                aim_angle=FloatInterval.point(0.0),
                payload={},
            ),
            (),
        )
        self.assertEqual(
            vm.float_locals[0],
            FloatInterval(-math.pi, math.pi),
        )
        self.assertIsNone(vm.float_local_aim_coefficients[0])
        self.assertTrue(vm.stopped)

    def test_main_integer_assignment_uses_captured_local_contract(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(identity="test", main=vm)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x06,
                size=20,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10004, 8),
            ),
            20: SubInstruction(
                offset=20,
                time=0,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        _execute_main(
            source=source,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
            ecl=ECL,
            remaining_horizon=1,
        )

        self.assertEqual(vm.integer_locals[4], 8)
        self.assertTrue(vm.stopped)

    def test_dynamic_polar_writes_follow_source_resolvers_and_reset_timer(
        self,
    ) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
            spawn_float_parameters=[
                FloatInterval.point(4.0),
                FloatInterval.point(2.5),
            ],
            spawn_float_parameter_aim_coefficients=[0.0, 0.0],
            call_float_parameters=[FloatInterval.point(0.25)] + [None] * 3,
            call_float_parameter_aim_coefficients=[0.0] + [None] * 3,
        )
        motion = _motion_state(
            deepcopy(
                _payload()["enemy_manager_template_source"]["motion_state"][
                    "rows"
                ][0]
            )
        )
        motion.movement_state = 3
        motion.motion_duration = 19
        motion.motion_timer_elapsed = 7
        motion.timed_duration = 19
        motion.timed_remaining = 7
        source = SimpleNamespace(identity="dynamic-polar", main=vm, motion=motion)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x41,
                size=20,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x03,
                arguments=(_bits(10094.0), _bits(10095.0)),
            ),
            20: SubInstruction(
                offset=20,
                time=0,
                opcode=0x47,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(_bits(10057.0),),
            ),
            36: SubInstruction(
                offset=36,
                time=0,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        _execute_main(
            source=source,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
            ecl=ECL,
            remaining_horizon=1,
        )

        self.assertTrue(-math.pi <= motion.angle <= math.pi)
        self.assertAlmostEqual(motion.angle, 4.0 - 2.0 * math.pi, places=6)
        self.assertEqual(motion.speed, 2.5)
        self.assertEqual(motion.speed_acceleration, 0.25)
        self.assertEqual(motion.movement_state, 1)
        self.assertEqual(motion.motion_duration, 0)
        self.assertEqual(motion.motion_timer_elapsed, 0)
        self.assertEqual(motion.timed_duration, 0)
        self.assertEqual(motion.timed_remaining, 0)

    def test_timed_polar_resolves_dynamic_duration_and_truncates_mode(
        self,
    ) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
            spawn_float_parameters=[
                FloatInterval.point(0.0),
                FloatInterval.point(3.0),
            ],
            spawn_float_parameter_aim_coefficients=[0.0, 0.0],
            call_integer_parameters=[6, 15, None, None],
        )
        motion = _motion_state(
            deepcopy(
                _payload()["enemy_manager_template_source"]["motion_state"][
                    "rows"
                ][0]
            )
        )
        source = SimpleNamespace(
            identity="dynamic-timed-polar",
            main=vm,
            motion=motion,
            precompose_world_x=None,
            precompose_world_y=None,
        )
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x42,
                size=28,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x0F,
                arguments=(
                    10053,
                    10054,
                    _bits(10094.0),
                    _bits(10095.0),
                ),
            ),
            28: SubInstruction(
                offset=28,
                time=0,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        _execute_main(
            source=source,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
            ecl=ECL,
            remaining_horizon=1,
        )

        self.assertEqual(motion.movement_state, 2)
        self.assertEqual(motion.timed_mode, 7)
        self.assertEqual(motion.timed_duration, 6)
        self.assertEqual(motion.timed_remaining, 6)
        self.assertEqual(motion.motion_duration, 6)
        self.assertEqual(motion.motion_timer_elapsed, 6)

    def test_aim_dependency_expires_at_source_update_boundary(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        motion = _motion_state(
            deepcopy(
                _payload()["enemy_manager_template_source"]["motion_state"][
                    "rows"
                ][0]
            )
        )
        source = SimpleNamespace(
            identity="frame-local-aim",
            main=vm,
            motion=motion,
            auxiliaries=[],
            active=True,
            precompose_origin_x=None,
            precompose_origin_y=None,
            precompose_world_x=None,
            precompose_world_y=None,
        )
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x07,
                size=20,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x02,
                arguments=(_bits(10016.0), _bits(10048.0)),
            ),
            20: SubInstruction(
                offset=20,
                time=99,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
        }

        _execute_source_update(
            source=source,
            frame=1,
            root_player_x=192.0,
            root_player_y=400.0,
            instructions=instructions,
            difficulty_mask=0x08,
            payload={},
            ecl=ECL,
            remaining_horizon=10,
        )

        self.assertGreater(vm.float_locals[0].upper, vm.float_locals[0].lower)
        self.assertEqual(vm.float_local_aim_coefficients[0], 0.0)

    def test_child_vm_copy_keeps_values_but_not_parent_aim_identity(
        self,
    ) -> None:
        parent = _VmState(
            instruction_offset=123,
            timer_elapsed=9,
            integer_locals=list(range(8)),
            float_locals=[FloatInterval(-0.5, 0.75)]
            + [FloatInterval.point(0.0)] * 7,
            scratch_integers=list(range(4)),
            float_local_aim_coefficients=[1.0] + [0.0] * 7,
            spawn_float_parameters=[FloatInterval(-1.0, 1.0), None],
            spawn_float_parameter_aim_coefficients=[1.0, None],
            call_float_parameters=[FloatInterval(-2.0, 2.0)] + [None] * 3,
            call_float_parameter_aim_coefficients=[1.0] + [None] * 3,
        )

        child = _spawn_vm(ecl=ECL, subroutine=0, parent_vm=parent)

        self.assertEqual(child.float_locals, parent.float_locals)
        self.assertEqual(child.spawn_float_parameters, parent.spawn_float_parameters)
        self.assertEqual(child.call_float_parameters, parent.call_float_parameters)
        self.assertEqual(child.float_local_aim_coefficients, [0.0] * 8)
        self.assertEqual(
            child.spawn_float_parameter_aim_coefficients,
            [0.0, None],
        )
        self.assertEqual(
            child.call_float_parameter_aim_coefficients,
            [0.0, None, None, None],
        )

    def test_main_loop_decrements_dynamic_local_before_branch(self) -> None:
        vm = _VmState(
            instruction_offset=24,
            timer_elapsed=4,
            integer_locals=[2, 0, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(identity="test", main=vm)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x01,
                size=12,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(),
            ),
            24: SubInstruction(
                offset=24,
                time=4,
                opcode=0x05,
                size=24,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x04,
                arguments=(0, -24, 10000),
            ),
        }

        _execute_main(
            source=source,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
            ecl=ECL,
            remaining_horizon=1,
        )

        self.assertEqual(vm.integer_locals[0], 1)
        self.assertEqual(vm.timer_elapsed, 0)
        self.assertTrue(vm.stopped)

    def test_captured_state2_uses_native_origin_displacement_and_fraction(
        self,
    ) -> None:
        row = deepcopy(
            _payload()["enemy_manager_template_source"]["motion_state"][
                "rows"
            ][0]
        )
        row.update(
            {
                "movement_state": 2,
                "timed_mode": 0,
                "base_position": [100.0, 52.0, 0.0],
                "velocity": [10.0, 5.0, 0.0],
                "world_position": [100.0, 52.0, 0.0],
                "timed_displacement": [100.0, 50.0, 0.0],
                "orbit_center_position": [60.0, 32.0, 0.0],
                "motion_timer_elapsed": 6,
                "motion_timer_fraction_bits": _bits(0.5),
                "motion_duration": 10,
            }
        )
        motion = _motion_state(row)
        source = SimpleNamespace(
            identity="test",
            motion=motion,
            auxiliaries=[],
            precompose_origin_x=None,
            precompose_origin_y=None,
            precompose_world_x=None,
            precompose_world_y=None,
        )

        _advance_motion(source)

        self.assertEqual(motion.timed_remaining, 5)
        self.assertAlmostEqual(motion.base_x, 105.0)
        self.assertAlmostEqual(motion.base_y, 54.5)

    def test_captured_state2_integer_expiry_snaps_to_endpoint(self) -> None:
        row = deepcopy(
            _payload()["enemy_manager_template_source"]["motion_state"][
                "rows"
            ][0]
        )
        row.update(
            {
                "movement_state": 2,
                "timed_mode": 4,
                "base_position": [150.0, 77.0, 0.0],
                "velocity": [1.0, 1.0, 0.0],
                "world_position": [150.0, 77.0, 0.0],
                "timed_displacement": [100.0, 50.0, 0.0],
                "orbit_center_position": [60.0, 32.0, 0.0],
                "motion_timer_elapsed": 1,
                "motion_timer_fraction_bits": _bits(0.5),
                "motion_duration": 10,
            }
        )
        motion = _motion_state(row)
        source = SimpleNamespace(
            identity="test",
            motion=motion,
            auxiliaries=[],
            precompose_origin_x=None,
            precompose_origin_y=None,
            precompose_world_x=None,
            precompose_world_y=None,
        )

        _advance_motion(source)

        self.assertEqual((motion.base_x, motion.base_y), (160.0, 82.0))
        self.assertEqual((motion.velocity_x, motion.velocity_y), (0.0, 0.0))
        self.assertEqual(motion.movement_state, 0)

    def test_state_zero_preserves_and_integrates_residual_velocity(self) -> None:
        row = deepcopy(
            _payload()["enemy_manager_template_source"]["motion_state"][
                "rows"
            ][0]
        )
        row["movement_state"] = 0
        row["velocity"] = [1.25, -0.75, 0.0]
        motion = _motion_state(row)
        source = SimpleNamespace(
            identity="state-zero-residual",
            motion=motion,
            auxiliaries=[],
            enemy_flags=0,
            precompose_origin_x=None,
            precompose_origin_y=None,
            precompose_world_x=None,
            precompose_world_y=None,
        )

        _advance_motion(source)

        self.assertEqual(motion.base_x, 61.25)
        self.assertEqual(motion.base_y, 31.25)
        self.assertEqual(motion.velocity_x, 1.25)
        self.assertEqual(motion.velocity_y, -0.75)

    def test_native_pool_scan_orders_synchronous_child_updates(self) -> None:
        parent_sub = _synthetic_subroutine(
            0,
            0x1000,
            (
                (
                    0,
                    0x5D,
                    0,
                    (
                        1,
                        _bits(10.0),
                        _bits(20.0),
                        _bits(0.0),
                        1,
                        0,
                        0,
                    ),
                ),
                (999, 0x01, 0, ()),
            ),
        )
        child_sub = _synthetic_subroutine(
            1,
            0x2000,
            (
                (
                    0,
                    0x41,
                    0x02,
                    (_bits(0.0), _bits(10094.0)),
                ),
                (999, 0x01, 0, ()),
            ),
        )
        terminator_sub = _synthetic_subroutine(
            2,
            0x3000,
            ((0, 0x01, 0, ()),),
        )
        ecl = replace(
            ECL,
            subroutines=(parent_sub, child_sub, terminator_sub),
            timelines=(),
        )

        def run(*, parent_slot: int, release_slot_zero: bool):
            parent = _source_initialized_spawn(
                identity=f"parent-slot-{parent_slot}",
                pool_slot=parent_slot,
                subroutine=0,
                position_x=FloatInterval.point(0.0),
                position_y=FloatInterval.point(0.0),
                hitpoints=1,
                parent_vm=None,
                ecl=ecl,
            )
            parent.main.spawn_float_parameters[0] = FloatInterval.point(2.0)
            initial = [parent]
            if release_slot_zero:
                initial.insert(
                    0,
                    _source_initialized_spawn(
                        identity="slot-zero-terminator",
                        pool_slot=0,
                        subroutine=2,
                        position_x=FloatInterval.point(0.0),
                        position_y=FloatInterval.point(0.0),
                        hitpoints=1,
                        parent_vm=None,
                        ecl=ecl,
                    ),
                )
            births = []
            payload = _payload()
            instructions = _instruction_map(ecl)
            pool = _NativeEnemyPool(
                initial_sources=initial,
                instructions=instructions,
                difficulty_mask=8,
                payload=payload,
                ecl=ecl,
                root_player_x=192.0,
                root_player_y=400.0,
                on_birth=births.append,
            )
            pool.begin_frame(frame=1, remaining_horizon=10)
            for slot in range(480):
                source = pool.slots[slot]
                if source is None or not source.active:
                    continue
                _execute_source_update(
                    source=source,
                    frame=1,
                    root_player_x=192.0,
                    root_player_y=400.0,
                    instructions=instructions,
                    difficulty_mask=8,
                    payload=payload,
                    ecl=ecl,
                    remaining_horizon=10,
                    spawn_executor=pool.spawn_from_instruction,
                )
                if not source.active:
                    pool.release(source)
                    continue
                _integrate_motion(source, parent=pool.parent_for(source))
            self.assertEqual(len(births), 1)
            return births[0]

        higher_child = run(parent_slot=0, release_slot_zero=False)
        self.assertEqual(higher_child.pool_slot, 1)
        self.assertEqual(higher_child.motion.base_x, 12.0)
        self.assertEqual(higher_child.main.timer_elapsed, 2)

        lower_child = run(parent_slot=1, release_slot_zero=True)
        self.assertEqual(lower_child.pool_slot, 0)
        self.assertEqual(lower_child.motion.base_x, 10.0)
        self.assertEqual(lower_child.motion.velocity_x, 2.0)
        self.assertEqual(lower_child.main.timer_elapsed, 1)

    def test_real_stage5_child_emits_source_tagged_future_birth(self) -> None:
        payload = _payload()
        payload["compact_state"]["spell_id"] = 111
        payload["bullet_template_geometry"]["rows"] = [
            {"type": value, "half_width": 4.0, "half_height": 4.0}
            for value in range(21)
        ]
        parent = _source_initialized_spawn(
            identity="stage5-parent",
            pool_slot=0,
            subroutine=0,
            position_x=FloatInterval.point(192.0),
            position_y=FloatInterval.point(100.0),
            hitpoints=100,
            parent_vm=None,
            ecl=ECL,
        )
        parent.main.spawn_float_parameters = [
            FloatInterval.point(192.0),
            FloatInterval.point(100.0),
        ]
        births = []
        pool = _NativeEnemyPool(
            initial_sources=[parent],
            instructions=_instruction_map(ECL),
            difficulty_mask=8,
            payload=payload,
            ecl=ECL,
            root_player_x=192.0,
            root_player_y=400.0,
            on_birth=births.append,
        )
        spawn = next(
            instruction
            for instruction in ECL.subroutines[63].instructions
            if instruction.offset == 27864
        )
        pool.begin_frame(frame=1, remaining_horizon=268)

        events, count = pool.spawn_from_instruction(
            parent,
            spawn,
            FloatInterval.point(0.0),
        )

        self.assertEqual(events, ())
        self.assertEqual(count, 1)
        self.assertEqual(len(births), 1)
        child = births[0]
        self.assertTrue(child.enemy_flags & ENEMY_FLAG_LINKED_CHILD)
        self.assertFalse(child.enemy_flags & ENEMY_FLAG_CONTACT)
        # Sub64 immediately stores its constructed world position back into
        # the copied 10094/10095 parameter slots.
        self.assertEqual(child.main.spawn_float_parameters[0].lower, 16.0)
        self.assertEqual(child.main.spawn_float_parameters[1].lower, 368.0)
        instructions = _instruction_map(ECL)

        actions = []
        for frame in range(1, 80):
            pool.begin_frame(frame=frame, remaining_horizon=268 - frame)
            source_actions, _descendants = _execute_source_update(
                source=child,
                frame=frame,
                root_player_x=192.0,
                root_player_y=400.0,
                instructions=instructions,
                difficulty_mask=8,
                payload=payload,
                ecl=ECL,
                remaining_horizon=268 - frame,
                spawn_executor=pool.spawn_from_instruction,
            )
            actions.extend(source_actions)
            _integrate_motion(child, parent=parent)

        tagged_births = [
            action
            for action in actions
            if isinstance(action, FutureDirectFire)
            and action.original_flags & 0x100000
        ]
        self.assertTrue(tagged_births)
        tagged_birth = tagged_births[0]
        self.assertEqual(tagged_birth.original_flags, 0x100202)
        self.assertEqual(tagged_birth.tagged_callbacks, ())

        same_frame_callback = FutureTaggedBulletCallback(
            source="later-pool-slot:callback12",
            frame=tagged_birth.activation_frames[0],
            callback_index=12,
            tag_mask=0x100000,
            callback_angle=FloatInterval.point(0.25),
            callback_speed=FloatInterval.point(2.0),
        )
        before_birth = _attach_later_tagged_callbacks(
            (same_frame_callback, tagged_birth)
        )[0]
        after_birth = _attach_later_tagged_callbacks(
            (tagged_birth, same_frame_callback)
        )[0]
        self.assertEqual(before_birth.tagged_callbacks, ())
        self.assertEqual(
            after_birth.tagged_callbacks,
            (same_frame_callback,),
        )

    def test_active_auxiliary_remains_closed_from_captured_state2(self) -> None:
        payload = deepcopy(_payload())
        motion = payload["enemy_manager_template_source"]["motion_state"][
            "rows"
        ][0]
        motion.update(
            {
                "movement_state": 2,
                "timed_mode": 0,
                "base_position": [61.0, 32.0, 0.0],
                "velocity": [1.0, 0.0, 0.0],
                "world_position": [61.0, 32.0, 0.0],
                "timed_displacement": [4.0, 0.0, 0.0],
                "orbit_center_position": [60.0, 32.0, 0.0],
                "motion_timer_elapsed": 3,
                "motion_timer_fraction_bits": 0,
                "motion_duration": 4,
            }
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertIsNone(closure.causal_prefix_reason)

    def test_captured_state2_missing_timer_fraction_fails_closed(self) -> None:
        payload = deepcopy(_payload())
        motion = payload["enemy_manager_template_source"]["motion_state"][
            "rows"
        ][0]
        motion.update(
            {
                "movement_state": 2,
                "timed_mode": 0,
                "base_position": [61.0, 32.0, 0.0],
                "velocity": [1.0, 0.0, 0.0],
                "world_position": [61.0, 32.0, 0.0],
                "timed_displacement": [4.0, 0.0, 0.0],
                "orbit_center_position": [60.0, 32.0, 0.0],
                "motion_timer_elapsed": 3,
                "motion_duration": 4,
            }
        )
        del motion["motion_timer_fraction_bits"]

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertFalse(closure.projection.source_closure_complete)
        self.assertIn(
            "non-finite",
            closure.projection.source_closure_reason,
        )

    def test_health_damage_uses_captured_cadence_phase(self) -> None:
        payload = deepcopy(_payload())
        envelope = payload["route2_health_transition_damage_envelope"]
        envelope["future_raw_damage_by_cadence_phase"] = list(range(1, 21))
        envelope["future_cadence_phase_support"] = [3]

        self.assertEqual(
            _health_transition_hp_loss_upper_bound(
                payload,
                damage_frames=1,
            ),
            4,
        )

    def test_health_damage_zero_updates_excludes_active_shots(self) -> None:
        payload = deepcopy(_payload())
        payload["route2_health_transition_damage_envelope"] = (
            _damage_envelope(active_raw_damage=999)
        )

        self.assertEqual(
            _health_transition_hp_loss_upper_bound(
                payload,
                damage_frames=0,
            ),
            0,
        )

    def test_far_timeout_is_proven_outside_bounded_horizon(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["phase_timer_elapsed"] = 100
        phase["timeout_frame"] = 300
        phase["timeout_subroutine"] = 7

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=100,
        )

        self.assertTrue(closure.projection.source_closure_complete)

    def test_timeout_at_horizon_truncates_complete_causal_prefix(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["phase_timer_elapsed"] = 100
        phase["timeout_frame"] = 200
        phase["timeout_subroutine"] = 7

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=100,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 99)

    def test_health_transition_outside_damage_envelope_is_proven(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["health_thresholds"][0] = 50
        phase["health_successor_subroutines"][0] = 7
        payload["route2_health_transition_damage_envelope"] = (
            _damage_envelope(active_raw_damage=48)
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=2,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.health_transition_proven_count, 1)
        self.assertEqual(closure.health_transition_minimum_margin, 0)

    def test_health_transition_truncates_before_reachable_check(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["health_thresholds"][0] = 50
        phase["health_successor_subroutines"][0] = 7
        payload["route2_health_transition_damage_envelope"] = (
            _damage_envelope(active_raw_damage=49)
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=2,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 1)
        self.assertEqual(closure.health_transition_proven_count, 1)
        self.assertEqual(closure.health_transition_minimum_margin, 50)

    def test_last_frame_damage_cannot_trigger_transition_in_horizon(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["health_thresholds"][0] = 50
        phase["health_successor_subroutines"][0] = 7
        payload["route2_health_transition_damage_envelope"] = (
            _damage_envelope(active_raw_damage=49)
        )

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.health_transition_proven_count, 1)
        self.assertEqual(closure.health_transition_minimum_margin, 50)

    def test_cadence_damage_finds_exact_transition_free_prefix(self) -> None:
        payload = deepcopy(_payload())
        phase = payload["enemy_manager_template_source"][
            "phase_transition_state"
        ]["rows"][0]
        phase["health_thresholds"][0] = 50
        phase["health_successor_subroutines"][0] = 7
        envelope = _damage_envelope()
        envelope["future_raw_damage_by_cadence_phase"] = [10] * 20
        payload["route2_health_transition_damage_envelope"] = envelope

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=10,
        )

        # Four intervening 10-damage updates lose at most floor(40*1.06)=42;
        # five lose 53.  The phase check in future frame 5 is therefore the
        # last one proved unable to select the successor.
        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 5)
        self.assertEqual(closure.health_transition_minimum_margin, 8)

    def test_auxiliary_timer_reset_uses_captured_integer_local(self) -> None:
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10000,),
            )
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[4, 0, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(identity="test")

        _execute_auxiliary(
            source=source,
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )
        self.assertEqual(vm.instruction_offset, 16)
        self.assertEqual(vm.delay_remaining, 3)
        for frame, remaining in ((2, 2), (3, 1), (4, 0)):
            _execute_auxiliary(
                source=source,
                vm=vm,
                instructions=instructions,
                difficulty_mask=0x08,
                frame=frame,
                aim_angle=FloatInterval.point(0.0),
                payload={},
            )
            self.assertEqual(vm.delay_remaining, remaining)

    def test_auxiliary_future_pc_waits_on_native_equality_clock(self) -> None:
        instructions = {
            0: SubInstruction(
                offset=0,
                time=2,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(1,),
            )
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(identity="test")

        for frame, elapsed in ((1, 1), (2, 2)):
            self.assertEqual(
                _execute_auxiliary(
                    source=source,
                    vm=vm,
                    instructions=instructions,
                    difficulty_mask=0x08,
                    frame=frame,
                    aim_angle=FloatInterval.point(0.0),
                    payload={},
                ),
                (),
            )
            self.assertEqual(vm.timer_elapsed, elapsed)
        _execute_auxiliary(
            source=source,
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=3,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )
        self.assertEqual(vm.instruction_offset, 16)
        self.assertEqual(vm.timer_elapsed, 2)

    def test_auxiliary_stale_pc_is_silent_until_parent_replacement(self) -> None:
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x68,
                size=40,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0,
                arguments=(0,) * 7,
            )
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=1,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )

        self.assertEqual(
            _execute_auxiliary(
                source=SimpleNamespace(identity="test"),
                vm=vm,
                instructions=instructions,
                difficulty_mask=0x08,
                frame=1,
                aim_angle=FloatInterval.point(0.0),
                payload={},
            ),
            (),
        )
        self.assertTrue(vm.stopped)

    def test_native_motion_angle_variable_reads_captured_source(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        source = SimpleNamespace(motion=SimpleNamespace(angle=-1.25))

        value = _eval_float_operand(
            _bits(10069.0),
            dynamic=True,
            vm=vm,
            aim_angle=FloatInterval.point(0.0),
            source=source,
        )

        self.assertEqual(value, FloatInterval.point(-1.25))

    def test_native_random_angle_keeps_float32_endpoint_rounding(self) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )
        bound = struct.unpack("<f", struct.pack("<f", 3.1415927))[0]

        value = _eval_float_operand(
            _bits(10082.0),
            dynamic=True,
            vm=vm,
            aim_angle=FloatInterval.point(0.0),
            source=SimpleNamespace(motion=SimpleNamespace(angle=0.0)),
        )

        self.assertEqual(value, FloatInterval(-bound, bound))
        self.assertLess(value.lower, -math.pi)
        self.assertGreater(value.upper, math.pi)

    def test_auxiliary_previous_and_fraction_do_not_block_unit_root(self) -> None:
        payload = deepcopy(_payload())
        state = payload["enemy_manager_template_source"][
            "auxiliary_ecl_contexts"
        ]["rows"][0]["state"]
        state["timer_previous"] = 17
        state["timer_fraction_bits"] = _bits(0.5)

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(len(closure.direct_fire_events), 1)

    def test_auxiliary_float_subtraction_uses_interval_arithmetic(self) -> None:
        destination = _bits(10016.0)
        left = _bits(10017.0)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x1A,
                size=24,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x03,
                arguments=(destination, left, _bits(2.0)),
            ),
            24: SubInstruction(
                offset=24,
                time=0,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10036,),
            ),
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[
                FloatInterval.point(0.0),
                FloatInterval(3.0, 5.0),
                *[FloatInterval.point(0.0) for _ in range(6)],
            ],
            scratch_integers=[2, 0, 0, 0],
        )

        events = _execute_auxiliary(
            source=SimpleNamespace(identity="test"),
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )

        self.assertEqual(events, ())
        self.assertEqual(vm.float_locals[0], FloatInterval(1.0, 3.0))

    def test_auxiliary_float_addition_uses_interval_arithmetic(self) -> None:
        destination = _bits(10016.0)
        left = _bits(10017.0)
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x19,
                size=24,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x03,
                arguments=(destination, left, _bits(2.0)),
            ),
            24: SubInstruction(
                offset=24,
                time=0,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10036,),
            ),
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[0] * 8,
            float_locals=[
                FloatInterval.point(0.0),
                FloatInterval(3.0, 5.0),
                *[FloatInterval.point(0.0) for _ in range(6)],
            ],
            scratch_integers=[2, 0, 0, 0],
        )

        _execute_auxiliary(
            source=SimpleNamespace(identity="test"),
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )

        self.assertEqual(vm.float_locals[0], FloatInterval(5.0, 7.0))

    def test_auxiliary_integer_le_jump_uses_captured_local(self) -> None:
        instructions = {
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x2E,
                size=28,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10000, 8, 3, 44),
            ),
            44: SubInstruction(
                offset=44,
                time=3,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10036,),
            ),
        }
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[8, 0, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[1, 0, 0, 0],
        )

        _execute_auxiliary(
            source=SimpleNamespace(identity="test"),
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )

        self.assertEqual(vm.instruction_offset, 60)
        self.assertEqual(vm.timer_elapsed, 3)

    def test_auxiliary_loop_decrements_and_jumps_while_positive(self) -> None:
        instructions = {
            88: SubInstruction(
                offset=88,
                time=4,
                opcode=0x05,
                size=24,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x04,
                arguments=(0, -88, 10000),
            ),
            0: SubInstruction(
                offset=0,
                time=0,
                opcode=0x02,
                size=16,
                byte_08=0,
                difficulty_mask=0xFF,
                parameter_mask=0x01,
                arguments=(10036,),
            ),
        }
        vm = _VmState(
            instruction_offset=88,
            timer_elapsed=4,
            integer_locals=[2, 0, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[1, 0, 0, 0],
        )

        _execute_auxiliary(
            source=SimpleNamespace(identity="test"),
            vm=vm,
            instructions=instructions,
            difficulty_mask=0x08,
            frame=1,
            aim_angle=FloatInterval.point(0.0),
            payload={},
        )

        self.assertEqual(vm.integer_locals[0], 1)
        self.assertEqual(vm.instruction_offset, 16)
        self.assertEqual(vm.timer_elapsed, 0)

    def test_dynamic_direct_fire_count_resolves_captured_integer_local(
        self,
    ) -> None:
        vm = _VmState(
            instruction_offset=0,
            timer_elapsed=0,
            integer_locals=[9, 0, 0, 0, 0, 0, 0, 0],
            float_locals=[FloatInterval.point(0.0)] * 8,
            scratch_integers=[0] * 4,
        )

        self.assertEqual(
            _direct_fire_count(10000, dynamic=True, vm=vm),
            9,
        )
        vm.integer_locals[0] = 0x1_0002
        self.assertEqual(
            _direct_fire_count(10000, dynamic=True, vm=vm),
            2,
        )

    def test_auxiliary_fire_is_complete_and_consumed(self) -> None:
        closure = project_ordinary_future_sources(
            _payload(),
            ECL,
            horizon_frames=1,
        )
        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.source_count, 1)
        self.assertEqual(closure.auxiliary_count, 1)
        self.assertEqual(len(closure.direct_fire_events), 1)
        event = closure.direct_fire_events[0]
        self.assertEqual(event.mode, 1)
        self.assertEqual(event.aim_angle, FloatInterval.point(0.0))
        self.assertGreater(event.angle1.upper, event.angle1.lower)
        self.assertEqual(event.angle1_player_aim_coefficient, 1.0)
        self.assertIsNotNone(event.angle1_player_aim_residual)
        self.assertEqual(event.angle2_player_aim_coefficient, 0.0)
        self.assertEqual(
            event.angle2_player_aim_residual,
            FloatInterval.point(0.0),
        )
        self.assertEqual(
            len(closure.projection.trajectories),
            len(closure.direct_fire_events),
        )
        self.assertTrue(closure.projection.coverage.complete)

    def test_automatic_aim_mode_retains_native_player_angle(self) -> None:
        payload = _payload()
        payload["enemy_manager_template_source"]["emission_state"]["rows"][
            0
        ]["emission_offset"] = [100.0, 0.0, 0.0]
        replaced = False
        subroutines = []
        for subroutine in ECL.subroutines:
            instructions = []
            for instruction in subroutine.instructions:
                if instruction.offset == 0x2E7C:
                    instruction = replace(instruction, opcode=0x60)
                    replaced = True
                instructions.append(instruction)
            subroutines.append(
                replace(subroutine, instructions=tuple(instructions))
            )
        self.assertTrue(replaced)
        aimed_ecl = replace(ECL, subroutines=tuple(subroutines))

        closure = project_ordinary_future_sources(
            payload,
            aimed_ecl,
            horizon_frames=1,
        )

        self.assertEqual(len(closure.direct_fire_events), 1)
        event = closure.direct_fire_events[0]
        self.assertEqual(event.mode, 0)
        self.assertGreater(event.aim_angle.upper, event.aim_angle.lower)
        self.assertNotEqual(event.aim_angle, FloatInterval.point(0.0))
        descriptor_root_angle = math.atan2(432.0 - 32.0, 192.0 - 160.0)
        source_center_angle = math.atan2(432.0 - 32.0, 192.0 - 60.0)
        self.assertLessEqual(event.aim_angle.lower, descriptor_root_angle)
        self.assertGreaterEqual(event.aim_angle.upper, descriptor_root_angle)
        self.assertGreater(
            abs(event.aim_angle.midpoint - source_center_angle),
            0.1,
        )

    def test_active_hostile_body_motion_is_consumed_from_root(self) -> None:
        payload = deepcopy(_payload())
        body = payload["enemy_manager_template_source"]["enemy_bodies"][0]
        body["flags"] |= 0x04

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(len(closure.projection.aabb_trajectories), 1)
        sample = closure.projection.aabb_trajectories[0].sample(0)
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual((sample.x, sample.y), (60.0, 32.0))
        self.assertEqual((sample.half_width, sample.half_height), (8.0, 8.0))

    def test_installed_callback_fails_closed(self) -> None:
        payload = _payload()
        payload["enemy_manager_template_source"][
            "main_ecl_installed_callbacks"
        ]["rows"][0]["installed_callback"]["function_pointer"] = 0x401000
        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )
        self.assertFalse(closure.projection.source_closure_complete)
        self.assertIn(
            "installed callback",
            closure.projection.source_closure_reason,
        )
        self.assertFalse(closure.projection.coverage.complete)

    def test_future_unsupported_source_publishes_only_exact_prefix(self) -> None:
        payload = deepcopy(_payload())
        main = payload["enemy_manager_template_source"][
            "main_ecl_vm_inventory"
        ]["rows"][0]
        # Stage-5 sub46 offset 0x488C is an unsupported opcode 0x35 at ECL
        # time 4.  The native equality clock cannot reach it until update 5.
        main[3] = ECL_BASE + 0x488C
        main[5] = 0

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=10,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.projection.horizon_frames, 4)
        self.assertIn("future frame 5", closure.causal_prefix_reason)
        self.assertIn("unsupported opcode 0x35", closure.causal_prefix_reason)

    def test_reached_random_x_timeline_spawn_uses_fresh_constructor(self) -> None:
        payload = deepcopy(_payload())
        spawn = next(
            instruction
            for instruction in ECL.timelines[0].instructions
            if instruction.offset == 43348
        )
        row = payload["stage_timeline_runtime"]["rows"][0]
        row["elapsed"] = spawn.time
        row["current_instruction"]["static_offset"] = spawn.offset
        row["current_instruction"]["terminal"] = False
        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )
        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.timeline_spawn_count, 1)
        self.assertEqual(closure.source_count, 2)
        timeline_events = [
            event
            for event in closure.direct_fire_events
            if event.source.startswith("timeline:")
        ]
        # EnemyManager::SpawnEnemy1 copies firstEnemy, whose auxiliary VMs are
        # empty.  The old model cloned the live slot-zero auxiliary and emitted
        # a bullet here twenty frames before sub29 actually starts sub30.
        self.assertEqual(timeline_events, [])

    def test_unit_scale_timeline_fraction_is_causally_inert(self) -> None:
        payload = deepcopy(_payload())
        spawn = next(
            instruction
            for instruction in ECL.timelines[0].instructions
            if instruction.offset == 43348
        )
        row = payload["stage_timeline_runtime"]["rows"][0]
        row["elapsed"] = spawn.time
        row["fraction_bits"] = _bits(0.5)
        row["current_instruction"]["static_offset"] = spawn.offset
        row["current_instruction"]["terminal"] = False

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.timeline_spawn_count, 1)

    def test_nonfinite_timeline_fraction_fails_closed(self) -> None:
        payload = deepcopy(_payload())
        row = payload["stage_timeline_runtime"]["rows"][0]
        row["fraction_bits"] = 0x7FC00000

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertFalse(closure.projection.source_closure_complete)
        self.assertIn(
            "timeline 0 timer is not finite",
            closure.projection.source_closure_reason,
        )

    def test_frscreen_gates_are_lifted_as_hazard_maximal_variants(
        self,
    ) -> None:
        payload = deepcopy(_payload())
        spawn = next(
            instruction
            for instruction in ECL.timelines[0].instructions
            if instruction.offset == 43348
        )
        row = payload["stage_timeline_runtime"]["rows"][0]
        row["elapsed"] = spawn.time
        row["current_instruction"]["static_offset"] = spawn.offset
        row["current_instruction"]["terminal"] = False
        external = payload["stage_timeline_runtime"]["external"]
        external["stage_transition_busy"] = True
        external["spawn_suppressed"] = True
        external["conditional_gate_blocked"] = True

        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )

        self.assertTrue(closure.projection.source_closure_complete)
        # Busy/suppressed roots can only omit this consumed record.  Retaining
        # the false variant is the hazard-maximal hard projection.
        self.assertEqual(closure.timeline_spawn_count, 1)

    def test_spawn_wave_remains_closed_through_timed_motion(self) -> None:
        payload = deepcopy(_payload())
        spawn = next(
            instruction
            for instruction in ECL.timelines[0].instructions
            if instruction.offset == 43348
        )
        row = payload["stage_timeline_runtime"]["rows"][0]
        row["elapsed"] = spawn.time
        row["current_instruction"]["static_offset"] = spawn.offset
        row["current_instruction"]["terminal"] = False
        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=180,
        )
        self.assertTrue(closure.projection.source_closure_complete)
        self.assertEqual(closure.timeline_spawn_count, 9)
        # This locks the source-template result.  The former >700 expectation
        # included inherited live-slot auxiliary emissions that SpawnEnemy1
        # cannot produce.
        self.assertEqual(len(closure.direct_fire_events), 598)
        self.assertTrue(closure.projection.coverage.complete)

    def test_runtime_program_identity_mismatch_fails_closed(self) -> None:
        payload = _payload()
        payload["stage_timeline_runtime"]["ecl_file"][
            "canonical_sha256"
        ] = "0" * 64
        closure = project_ordinary_future_sources(
            payload,
            ECL,
            horizon_frames=1,
        )
        self.assertFalse(closure.projection.source_closure_complete)
        self.assertIn("SHA-256", closure.projection.source_closure_reason)


if __name__ == "__main__":
    unittest.main()
