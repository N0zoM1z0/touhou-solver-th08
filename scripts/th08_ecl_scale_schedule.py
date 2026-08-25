"""Causal TH08 ECL producer for player/laser time-scale phase schedules.

The producer starts from a coherent post-enemy-update VM/root observation.
For every future physical update it records the player-phase scale, executes
the supported ready ECL prefix, records the post-ECL laser-phase scale, then
advances the native VM timer with that post-write scale. Unsupported source,
control, or external-state dependencies truncate authority before guessing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable

from th08_ecl_runtime import (
    ECL_OP_FIRST_CONDITIONAL_JUMP,
    ECL_OP_INVOKE_CALLBACK,
    ECL_OP_JUMP,
    ECL_OP_LAST_CONDITIONAL_JUMP,
    ECL_OP_LOOP_DECREMENT_JUMP,
    ECL_OP_SET_INT,
    ECL_OP_TERMINATE,
    EclVmSnapshot,
    RuntimeEclInstruction,
)
from th08_ecl_shadow.registers import signed_int32
from th08_ecl_vm_state import EclVmLocalProjection
from th08_native_timer import Th08TimerState, advance_scaled_timer
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
    reciprocal_int32_time_scale_bits,
    validate_time_scale_bits,
)


TH08_ECL_SCALE_SCHEDULE_SEMANTICS_VERSION = (
    "th08-ecl-scale-schedule-v1-post-update-player-ecl-laser"
)

CALLBACK_SET_TIME_SCALE_RECIPROCAL = 18
CALLBACK_SLOWDOWN_AND_SCALE_BULLETS = 28
CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE = 29
ECL_OP_INSTALL_CALLBACK = 0x89
ECL_OP_FINISH_SPELL_CARD = 0x7B

ECL_INT_DIFFICULTY_INDEX = 10040
ECL_INT_ROUTE_ID = 10052
ECL_INT_SPELL_FINISH_RESULT = 10099
ECL_INT_SPELL_TIMER_ELAPSED = 10100

_INTEGER_CONDITIONALS = {
    0x28: lambda left, right: left == right,
    0x2A: lambda left, right: left != right,
    0x2C: lambda left, right: left < right,
    0x2E: lambda left, right: left <= right,
    0x30: lambda left, right: left > right,
    0x32: lambda left, right: left >= right,
}

# These shipped operations do not mutate the supported integer control
# projection or global time scale. Float mutations remain irrelevant because
# float conditional control is deliberately unsupported.
_SUPPORTED_SCALE_NEUTRAL_OPCODES = frozenset(
    {
        0x00,  # nop
        0x07,  # set_float
        0x0F,  # add_float
        0x25,  # normalize_angle
        0x7C,  # play_sound_at_enemy
        0x7F,  # set_boss_slot
        0x8C,  # spawn_effect_with_vector
    }
)


@dataclass(frozen=True)
class EclScaleSourceAuthority:
    """Evidence required before one VM can stand for every scale writer."""

    scale_writer_source_ids: tuple[int, ...]
    writer_inventory_complete: bool
    scheduler_order_complete: bool
    installed_scale_callbacks_absent: bool
    unmodeled_phase_transitions_absent: bool
    post_update_capture: bool
    external_state_coherent: bool
    no_hit_no_bomb_continuation: bool
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.scale_writer_source_ids, tuple):
            raise ValueError("scale-writer source IDs must be an immutable tuple")
        if not self.scale_writer_source_ids or any(
            type(source_id) is not int or source_id <= 0
            for source_id in self.scale_writer_source_ids
        ):
            raise ValueError("scale-writer source IDs must be positive integers")
        if len(set(self.scale_writer_source_ids)) != len(
            self.scale_writer_source_ids
        ):
            raise ValueError("scale-writer source IDs must be unique")
        if type(self.provenance) is not str or not self.provenance:
            raise ValueError("scale-source provenance cannot be empty")

    def incomplete_reasons(self, source_id: int) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.scale_writer_source_ids != (source_id,):
            reasons.append("writer_source_set")
        for field in (
            "writer_inventory_complete",
            "scheduler_order_complete",
            "installed_scale_callbacks_absent",
            "unmodeled_phase_transitions_absent",
            "post_update_capture",
            "external_state_coherent",
        ):
            if not getattr(self, field):
                reasons.append(field)
        return tuple(reasons)


@dataclass(frozen=True)
class EclScaleEnvironment:
    """Root observations used by the supported dynamic integer evaluator."""

    difficulty_index: int
    route_id: int
    spell_flags: int
    spell_timer_elapsed_by_frame: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.difficulty_index) is not int or self.difficulty_index < 0:
            raise ValueError("difficulty index must be a nonnegative integer")
        if type(self.route_id) is not int or not 0 <= self.route_id <= 0xFF:
            raise ValueError("route ID must be a byte")
        if type(self.spell_flags) is not int or not 0 <= self.spell_flags <= 0xFFFFFFFF:
            raise ValueError("spell flags must be a dword")
        if not isinstance(self.spell_timer_elapsed_by_frame, tuple) or any(
            type(value) is not int or not -(1 << 31) <= value < (1 << 31)
            for value in self.spell_timer_elapsed_by_frame
        ):
            raise ValueError("spell timer schedule must contain signed int32 values")


@dataclass(frozen=True)
class EclScaleWrite:
    frame: int
    callback_index: int
    scale_bits_before: int
    scale_bits_after: int
    instruction_address: int
    scales_active_bullet_velocity: bool


@dataclass(frozen=True)
class EclScaleScheduleResult:
    schedule: Th08TimeScaleSchedule
    writes: tuple[EclScaleWrite, ...]
    instructions_scanned: int
    stop_reason: str
    horizon_covered: bool
    requested_horizon_frames: int
    stop_frame: int
    consumed_external_variables: tuple[int, ...]
    final_instruction_pointer: int
    final_timer_elapsed: int
    final_timer_fraction_bits: int
    final_projection: EclVmLocalProjection | None

    def __post_init__(self) -> None:
        if self.instructions_scanned < 0:
            raise ValueError("scale schedule instruction count cannot be negative")
        if not 0 <= self.stop_frame <= self.requested_horizon_frames:
            raise ValueError("scale schedule stop frame is outside its horizon")
        if self.horizon_covered != (
            self.schedule.complete_horizon == self.requested_horizon_frames
        ):
            raise ValueError("scale schedule result disagrees with coverage")

    @property
    def bullet_velocity_rescale_frames(self) -> tuple[int, ...]:
        return tuple(
            write.frame
            for write in self.writes
            if write.scales_active_bullet_velocity
        )


class _IntegerProjection:
    def __init__(self, projection: EclVmLocalProjection) -> None:
        self._values = {
            **{
                10000 + index: value
                for index, value in enumerate(projection.integer_locals)
            },
            **{
                10036 + index: value
                for index, value in enumerate(projection.scratch_integers)
            },
        }
        self._float_bits = projection.float_local_bits
        self._spawn_float_parameter_bits = (
            projection.spawn_float_parameter_bits
        )
        self._call_integer_parameters = projection.call_integer_parameters
        self._call_float_parameter_bits = projection.call_float_parameter_bits

    def read(self, variable: int) -> int | None:
        return self._values.get(variable)

    def write(self, variable: int, value: int) -> bool:
        if variable not in self._values:
            return False
        self._values[variable] = signed_int32(value)
        return True

    def freeze(self) -> EclVmLocalProjection:
        return EclVmLocalProjection(
            tuple(self._values[10000 + index] for index in range(8)),
            self._float_bits,
            tuple(self._values[10036 + index] for index in range(4)),
            self._spawn_float_parameter_bits,
            self._call_integer_parameters,
            self._call_float_parameter_bits,
        )


def _integer_arguments(
    instruction: RuntimeEclInstruction,
    count: int,
) -> tuple[int, ...] | None:
    if len(instruction.payload) != count * 4:
        return None
    return struct.unpack(f"<{count}i", instruction.payload)


def _eligible(
    instruction: RuntimeEclInstruction,
    active_difficulty_mask: int,
) -> bool:
    return (
        active_difficulty_mask & instruction.difficulty_mask
    ) == active_difficulty_mask


def _spell_finish_flags(flags: int) -> int:
    """Project the control-relevant flag writes of spell_card_finish."""

    if flags & 0x01:
        flags &= ~0x01
        if not flags & 0x08 and flags & 0x04:
            flags |= 0x200
    return flags & ~0x800


def _resolve_integer(
    raw: int,
    *,
    dynamic: bool,
    projection: _IntegerProjection,
    environment: EclScaleEnvironment,
    spell_flags: int,
    frame: int,
) -> tuple[int | None, int | None]:
    if not dynamic:
        return signed_int32(raw), None
    variable = signed_int32(raw)
    local = projection.read(variable)
    if local is not None:
        return local, variable
    if variable == ECL_INT_DIFFICULTY_INDEX:
        return environment.difficulty_index, variable
    if variable == ECL_INT_ROUTE_ID:
        return environment.route_id, variable
    if variable == ECL_INT_SPELL_FINISH_RESULT:
        return (
            ((spell_flags >> 2) & 1)
            if spell_flags & 1
            else ((spell_flags >> 9) & 1),
            variable,
        )
    if variable == ECL_INT_SPELL_TIMER_ELAPSED:
        index = frame - 1
        if 0 <= index < len(environment.spell_timer_elapsed_by_frame):
            return environment.spell_timer_elapsed_by_frame[index], variable
    return None, variable


def _partial_result(
    *,
    root_scale_bits: int,
    player: list[int],
    laser: list[int],
    provenance: str,
    source_frame: int,
    writes: list[EclScaleWrite],
    instructions_scanned: int,
    stop_reason: str,
    horizon_frames: int,
    stop_frame: int,
    consumed: set[int],
    pc: int,
    timer: Th08TimerState,
    projection: _IntegerProjection | None,
) -> EclScaleScheduleResult:
    schedule = (
        Th08TimeScaleSchedule.root_observation(
            root_scale_bits,
            source_frame=source_frame,
            provenance=provenance,
        )
        if player == [root_scale_bits] and not laser
        else Th08TimeScaleSchedule.explicit(
            root_scale_bits=root_scale_bits,
            player_scale_bits=tuple(player),
            laser_scale_bits=tuple(laser),
            complete=False,
            provenance=provenance,
            source_frame=source_frame,
        )
    )
    return EclScaleScheduleResult(
        schedule=schedule,
        writes=tuple(writes),
        instructions_scanned=instructions_scanned,
        stop_reason=stop_reason,
        horizon_covered=False,
        requested_horizon_frames=horizon_frames,
        stop_frame=stop_frame,
        consumed_external_variables=tuple(sorted(consumed)),
        final_instruction_pointer=pc,
        final_timer_elapsed=timer.elapsed,
        final_timer_fraction_bits=timer.fraction_bits,
        final_projection=projection.freeze() if projection is not None else None,
    )


def synthesize_ecl_time_scale_schedule(
    snapshot: EclVmSnapshot,
    *,
    source_id: int,
    source_frame: int,
    authority: EclScaleSourceAuthority,
    environment: EclScaleEnvironment,
    instruction_at: Callable[[int], RuntimeEclInstruction],
    horizon_frames: int,
    active_difficulty_mask: int,
    max_instructions: int = 4096,
) -> EclScaleScheduleResult:
    """Produce an exact supported phase prefix or fail closed at first unknown."""

    if type(source_id) is not int or source_id <= 0:
        raise ValueError("scale-writer source ID must be positive")
    if type(source_frame) is not int or source_frame < 0:
        raise ValueError("scale source frame must be nonnegative")
    if type(horizon_frames) is not int or horizon_frames < 0:
        raise ValueError("scale schedule horizon must be nonnegative")
    if not 0 < active_difficulty_mask <= 0xFF:
        raise ValueError("active difficulty mask must be a nonzero byte")
    if type(max_instructions) is not int or max_instructions <= 0:
        raise ValueError("scale schedule instruction limit must be positive")

    root_scale_bits = snapshot.time_scale_bits
    validate_time_scale_bits(root_scale_bits, field="root time scale")
    timer = Th08TimerState(snapshot.timer_elapsed, snapshot.timer_fraction_bits)
    pc = snapshot.instruction_pointer
    provenance = (
        f"{TH08_ECL_SCALE_SCHEDULE_SEMANTICS_VERSION}:{authority.provenance}"
    )
    if horizon_frames == 0:
        schedule = Th08TimeScaleSchedule.explicit(
            root_scale_bits=root_scale_bits,
            player_scale_bits=(),
            laser_scale_bits=(),
            complete=True,
            provenance=provenance,
            source_frame=source_frame,
        )
        return EclScaleScheduleResult(
            schedule,
            (),
            0,
            "horizon",
            True,
            0,
            0,
            (),
            pc,
            timer.elapsed,
            timer.fraction_bits,
            snapshot.local_projection,
        )

    authority_reasons = authority.incomplete_reasons(source_id)
    if authority_reasons:
        return _partial_result(
            root_scale_bits=root_scale_bits,
            player=[root_scale_bits],
            laser=[],
            provenance=provenance,
            source_frame=source_frame,
            writes=[],
            instructions_scanned=0,
            stop_reason="incomplete_source_authority:" + ",".join(authority_reasons),
            horizon_frames=horizon_frames,
            stop_frame=0,
            consumed=set(),
            pc=pc,
            timer=timer,
            projection=None,
        )
    if snapshot.local_projection is None:
        return _partial_result(
            root_scale_bits=root_scale_bits,
            player=[root_scale_bits],
            laser=[],
            provenance=provenance,
            source_frame=source_frame,
            writes=[],
            instructions_scanned=0,
            stop_reason="missing_local_projection",
            horizon_frames=horizon_frames,
            stop_frame=0,
            consumed=set(),
            pc=pc,
            timer=timer,
            projection=None,
        )

    projection = _IntegerProjection(snapshot.local_projection)
    scale_bits = root_scale_bits
    spell_flags = environment.spell_flags
    player: list[int] = []
    laser: list[int] = []
    writes: list[EclScaleWrite] = []
    consumed: set[int] = set()
    instructions_scanned = 0
    terminated = False

    for frame in range(1, horizon_frames + 1):
        player.append(scale_bits)
        phase_visited: set[tuple[object, ...]] = set()
        while not terminated:
            state = (
                pc,
                timer.elapsed,
                timer.fraction_bits,
                scale_bits,
                spell_flags,
                projection.freeze(),
            )
            if state in phase_visited:
                return _partial_result(
                    root_scale_bits=root_scale_bits,
                    player=player,
                    laser=laser,
                    provenance=provenance,
                    source_frame=source_frame,
                    writes=writes,
                    instructions_scanned=instructions_scanned,
                    stop_reason="repeated_same_phase_state",
                    horizon_frames=horizon_frames,
                    stop_frame=frame,
                    consumed=consumed,
                    pc=pc,
                    timer=timer,
                    projection=projection,
                )
            phase_visited.add(state)
            try:
                instruction = instruction_at(pc)
            except (OSError, RuntimeError, ValueError, struct.error):
                return _partial_result(
                    root_scale_bits=root_scale_bits,
                    player=player,
                    laser=laser,
                    provenance=provenance,
                    source_frame=source_frame,
                    writes=writes,
                    instructions_scanned=instructions_scanned,
                    stop_reason="instruction_read_error",
                    horizon_frames=horizon_frames,
                    stop_frame=frame,
                    consumed=consumed,
                    pc=pc,
                    timer=timer,
                    projection=projection,
                )
            if instruction.time != timer.elapsed:
                break
            instructions_scanned += 1
            if instructions_scanned > max_instructions:
                return _partial_result(
                    root_scale_bits=root_scale_bits,
                    player=player,
                    laser=laser,
                    provenance=provenance,
                    source_frame=source_frame,
                    writes=writes,
                    instructions_scanned=instructions_scanned,
                    stop_reason="instruction_limit",
                    horizon_frames=horizon_frames,
                    stop_frame=frame,
                    consumed=consumed,
                    pc=pc,
                    timer=timer,
                    projection=projection,
                )
            if not _eligible(instruction, active_difficulty_mask):
                pc = instruction.address + instruction.size
                continue

            opcode = instruction.opcode
            if opcode == ECL_OP_TERMINATE:
                if instruction.payload:
                    reason = "unsupported_terminate_payload"
                    return _partial_result(
                        root_scale_bits=root_scale_bits,
                        player=player,
                        laser=laser,
                        provenance=provenance,
                        source_frame=source_frame,
                        writes=writes,
                        instructions_scanned=instructions_scanned,
                        stop_reason=reason,
                        horizon_frames=horizon_frames,
                        stop_frame=frame,
                        consumed=consumed,
                        pc=pc,
                        timer=timer,
                        projection=projection,
                    )
                terminated = True
                break
            if opcode == ECL_OP_JUMP:
                arguments = _integer_arguments(instruction, 2)
                if arguments is None or instruction.parameter_mask:
                    reason = "unsupported_jump"
                else:
                    target_time, relative_offset = arguments
                    pc = instruction.address + relative_offset
                    timer = timer.with_elapsed_preserving_fraction(target_time)
                    continue
            elif opcode == ECL_OP_LOOP_DECREMENT_JUMP:
                arguments = _integer_arguments(instruction, 3)
                if arguments is None or instruction.parameter_mask != 0x04:
                    reason = "unsupported_loop"
                else:
                    target_time, relative_offset, variable = arguments
                    counter = projection.read(variable)
                    if counter is None:
                        reason = "unsupported_loop_lvalue"
                    else:
                        post_decrement = signed_int32(counter - 1)
                        assert projection.write(variable, post_decrement)
                        if post_decrement > 0:
                            pc = instruction.address + relative_offset
                            timer = timer.with_elapsed_preserving_fraction(
                                target_time
                            )
                            continue
                        reason = ""
            elif opcode == ECL_OP_SET_INT:
                arguments = _integer_arguments(instruction, 2)
                if arguments is None or instruction.parameter_mask != 0x01:
                    reason = "unsupported_integer_assignment"
                else:
                    variable, value = arguments
                    projection.write(variable, value)
                    reason = ""
            elif opcode in _INTEGER_CONDITIONALS:
                arguments = _integer_arguments(instruction, 4)
                if arguments is None or instruction.parameter_mask & ~0x03:
                    reason = "unsupported_integer_conditional"
                else:
                    left_raw, right_raw, target_time, relative_offset = arguments
                    left, left_variable = _resolve_integer(
                        left_raw,
                        dynamic=bool(instruction.parameter_mask & 0x01),
                        projection=projection,
                        environment=environment,
                        spell_flags=spell_flags,
                        frame=frame,
                    )
                    right, right_variable = _resolve_integer(
                        right_raw,
                        dynamic=bool(instruction.parameter_mask & 0x02),
                        projection=projection,
                        environment=environment,
                        spell_flags=spell_flags,
                        frame=frame,
                    )
                    consumed.update(
                        variable
                        for variable in (left_variable, right_variable)
                        if variable is not None
                    )
                    if left is None or right is None:
                        reason = "unsupported_integer_operand"
                    else:
                        if _INTEGER_CONDITIONALS[opcode](left, right):
                            pc = instruction.address + relative_offset
                            timer = timer.with_elapsed_preserving_fraction(
                                target_time
                            )
                            continue
                        reason = ""
            elif (
                ECL_OP_FIRST_CONDITIONAL_JUMP
                <= opcode
                <= ECL_OP_LAST_CONDITIONAL_JUMP
            ):
                reason = "unsupported_float_conditional"
            elif opcode == ECL_OP_INVOKE_CALLBACK:
                arguments = _integer_arguments(instruction, 2)
                if arguments is None or instruction.parameter_mask & 0x01:
                    reason = "unsupported_callback_index"
                else:
                    callback_index, argument = arguments
                    if callback_index not in {
                        CALLBACK_SET_TIME_SCALE_RECIPROCAL,
                        CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
                        CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE,
                    }:
                        reason = "unsupported_non_scale_callback"
                    elif callback_index == CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE:
                        before = scale_bits
                        scale_bits = TH08_UNIT_TIME_SCALE_BITS
                        writes.append(
                            EclScaleWrite(
                                frame,
                                callback_index,
                                before,
                                scale_bits,
                                instruction.address,
                                True,
                            )
                        )
                        reason = ""
                    else:
                        divisor, variable = _resolve_integer(
                            argument,
                            dynamic=bool(instruction.parameter_mask & 0x02),
                            projection=projection,
                            environment=environment,
                            spell_flags=spell_flags,
                            frame=frame,
                        )
                        if variable is not None:
                            consumed.add(variable)
                        if divisor is None:
                            reason = "unsupported_scale_divisor"
                        else:
                            try:
                                next_scale = reciprocal_int32_time_scale_bits(
                                    divisor
                                )
                            except ValueError:
                                reason = "unsupported_scale_divisor"
                            else:
                                before = scale_bits
                                scale_bits = next_scale
                                writes.append(
                                    EclScaleWrite(
                                        frame,
                                        callback_index,
                                        before,
                                        scale_bits,
                                        instruction.address,
                                        callback_index
                                        == CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
                                    )
                                )
                                reason = ""
            elif opcode == ECL_OP_INSTALL_CALLBACK:
                reason = "unsupported_callback_install"
            elif opcode == ECL_OP_FINISH_SPELL_CARD:
                if instruction.payload:
                    reason = "unsupported_finish_spell_payload"
                elif not authority.no_hit_no_bomb_continuation:
                    reason = "missing_no_hit_no_bomb_continuation"
                else:
                    spell_flags = _spell_finish_flags(spell_flags)
                    reason = ""
            elif opcode in _SUPPORTED_SCALE_NEUTRAL_OPCODES:
                reason = ""
            else:
                reason = f"unsupported_opcode_{opcode:04x}"

            if reason:
                return _partial_result(
                    root_scale_bits=root_scale_bits,
                    player=player,
                    laser=laser,
                    provenance=provenance,
                    source_frame=source_frame,
                    writes=writes,
                    instructions_scanned=instructions_scanned,
                    stop_reason=reason,
                    horizon_frames=horizon_frames,
                    stop_frame=frame,
                    consumed=consumed,
                    pc=pc,
                    timer=timer,
                    projection=projection,
                )
            pc = instruction.address + instruction.size

        laser.append(scale_bits)
        if not terminated:
            timer = advance_scaled_timer(timer, time_scale_bits=scale_bits)

    schedule = Th08TimeScaleSchedule.explicit(
        root_scale_bits=root_scale_bits,
        player_scale_bits=tuple(player),
        laser_scale_bits=tuple(laser),
        complete=True,
        provenance=provenance,
        source_frame=source_frame,
    )
    return EclScaleScheduleResult(
        schedule=schedule,
        writes=tuple(writes),
        instructions_scanned=instructions_scanned,
        stop_reason="horizon",
        horizon_covered=True,
        requested_horizon_frames=horizon_frames,
        stop_frame=horizon_frames,
        consumed_external_variables=tuple(sorted(consumed)),
        final_instruction_pointer=pc,
        final_timer_elapsed=timer.elapsed,
        final_timer_fraction_bits=timer.fraction_bits,
        final_projection=projection.freeze(),
    )


__all__ = [
    "CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE",
    "CALLBACK_SET_TIME_SCALE_RECIPROCAL",
    "CALLBACK_SLOWDOWN_AND_SCALE_BULLETS",
    "ECL_INT_SPELL_FINISH_RESULT",
    "ECL_INT_SPELL_TIMER_ELAPSED",
    "ECL_OP_FINISH_SPELL_CARD",
    "ECL_OP_INSTALL_CALLBACK",
    "EclScaleEnvironment",
    "EclScaleScheduleResult",
    "EclScaleSourceAuthority",
    "EclScaleWrite",
    "TH08_ECL_SCALE_SCHEDULE_SEMANTICS_VERSION",
    "synthesize_ecl_time_scale_schedule",
]
