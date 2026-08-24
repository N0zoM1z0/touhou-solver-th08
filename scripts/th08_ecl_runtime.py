#!/usr/bin/env python3
"""Minimal live TH08 ECL lookahead for pool-wide velocity callbacks.

This adapter reads the current enemy VM, follows only literal control flow,
and emits game-neutral velocity-change events. Unsupported expressions stop
the lookahead instead of guessing.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Callable, Protocol

from th08_ecl_callback_model import callback_12_phase_transition
from touhou_control.trajectory import CollisionStateChange, VelocityChange
from th08_ecl_vm_state import (
    ECL_VM_FLOAT_LOCALS_OFFSET,
    ECL_VM_INTEGER_LOCALS_OFFSET,
    ECL_VM_LOCAL_PROJECTION_SIZE,
    EclVmLocalProjection,
    float32_bits,
)
from th08_native_timer import (
    TH08_NATIVE_TIMER_SEMANTICS_VERSION,
    Th08TimerState,
    advance_until_elapsed,
)


GAMEPLAY_TIME_SCALE_ADDRESS = 0x017CE8E0
ENEMY_MAIN_ECL_VM_OFFSET = 0x07F8
ECL_VM_TAG_MASK_OFFSET = ECL_VM_INTEGER_LOCALS_OFFSET
ECL_VM_CALLBACK_ANGLE_OFFSET = ECL_VM_FLOAT_LOCALS_OFFSET
ECL_VM_CALLBACK_SPEED_OFFSET = ECL_VM_FLOAT_LOCALS_OFFSET + 0x04
# The main VM timer begins immediately after the current-instruction pointer.
# Its root/previous value is +0x04, fractional elapsed is +0x08, and integer
# elapsed is +0x0C. VM +0x90 is a separate -999-gated wait timer.
ECL_VM_TIMER_OFFSET = 0x04
ECL_VM_TIMER_FRACTION_OFFSET = ECL_VM_TIMER_OFFSET + 0x04
ECL_VM_TIMER_ELAPSED_OFFSET = ECL_VM_TIMER_OFFSET + 0x08
ECL_VM_SNAPSHOT_SIZE = ECL_VM_LOCAL_PROJECTION_SIZE

ECL_HEADER_SIZE = 12
ECL_OP_TERMINATE = 0x01
ECL_OP_RESET_TIMER = 0x02
ECL_OP_JUMP = 0x04
ECL_OP_LOOP_DECREMENT_JUMP = 0x05
ECL_OP_SET_INT = 0x06
ECL_OP_SET_FLOAT = 0x07
ECL_OP_FIRST_CONDITIONAL_JUMP = 0x28
ECL_OP_LAST_CONDITIONAL_JUMP = 0x33
ECL_OP_CALL_SUBROUTINE = 0x34
ECL_OP_RETURN_SUBROUTINE = 0x35
ECL_OP_INVOKE_CALLBACK = 0x88

ECL_INT_TAG_MASK = 10000
ECL_FLOAT_CALLBACK_ANGLE = 10016
ECL_FLOAT_CALLBACK_SPEED = 10017
CALLBACK_TOGGLE_TAGGED_BULLET = 12
LOOKAHEAD_COVERAGE_COMPLETE = "complete"
LOOKAHEAD_COVERAGE_UNKNOWN = "unknown"
ECL_LOOKAHEAD_SEMANTICS_VERSION = (
    "th08-ecl-velocity-lookahead-v2-native-timer-components"
)


class ProcessMemoryReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...


@dataclass(frozen=True)
class EclVmSnapshot:
    instruction_pointer: int
    timer_fraction: float
    timer_elapsed: int
    tag_mask: int
    callback_angle: float
    callback_speed: float
    time_scale: float
    local_projection: EclVmLocalProjection | None = None

    def __post_init__(self) -> None:
        projection = self.local_projection
        if projection is None:
            return
        if self.tag_mask != projection.integer_locals[0] & 0xFFFFFFFF:
            raise ValueError("ECL tag mask disagrees with its local projection")
        if float32_bits(self.callback_angle) != projection.float_local_bits[0]:
            raise ValueError("ECL callback angle disagrees with its local projection")
        if float32_bits(self.callback_speed) != projection.float_local_bits[1]:
            raise ValueError("ECL callback speed disagrees with its local projection")

    @property
    def timer_value(self) -> float:
        """Diagnostic sum only; native timer identity is component-wise."""

        return self.timer_elapsed + self.timer_fraction

    @property
    def timer_fraction_bits(self) -> int:
        return float32_bits(self.timer_fraction)

    @property
    def time_scale_bits(self) -> int:
        return float32_bits(self.time_scale)

    @property
    def timer_identity(self) -> tuple[int, int]:
        return self.timer_elapsed, self.timer_fraction_bits


@dataclass(frozen=True)
class RuntimeEclInstruction:
    address: int
    time: int
    opcode: int
    size: int
    difficulty_mask: int
    parameter_mask: int
    payload: bytes


@dataclass(frozen=True)
class TaggedVelocityToggle:
    """One future callback that toggles bullets matching ``tag_mask``."""

    frame: int
    callback_index: int
    tag_mask: int
    alternate_velocity_x: float
    alternate_velocity_y: float


@dataclass(frozen=True)
class TaggedBulletTrajectoryChanges:
    """Motion and collision changes produced by reached callback-12 events."""

    velocity_changes: tuple[VelocityChange, ...]
    collision_changes: tuple[CollisionStateChange, ...]


@dataclass(frozen=True)
class EclLookaheadResult:
    """Auditable prefix plus explicit horizon-completeness support."""

    events: tuple[TaggedVelocityToggle, ...]
    instructions_scanned: int
    stop_reason: str
    horizon_covered: bool
    requested_horizon_frames: int
    stop_frame: int

    def __post_init__(self) -> None:
        if self.requested_horizon_frames < 0:
            raise ValueError("lookahead horizon cannot be negative")
        if not 0 <= self.stop_frame <= self.requested_horizon_frames:
            raise ValueError("lookahead stop frame is outside its horizon")
        complete_stop = self.stop_reason in {"horizon", "terminate"}
        if self.horizon_covered != complete_stop:
            raise ValueError("lookahead completeness disagrees with its stop reason")

    @property
    def coverage_status(self) -> str:
        return (
            LOOKAHEAD_COVERAGE_COMPLETE
            if self.horizon_covered
            else LOOKAHEAD_COVERAGE_UNKNOWN
        )

    @property
    def semantics_version(self) -> str:
        return ECL_LOOKAHEAD_SEMANTICS_VERSION

    @property
    def timer_semantics_version(self) -> str:
        return TH08_NATIVE_TIMER_SEMANTICS_VERSION

    @property
    def covered_through_frame(self) -> int:
        if self.horizon_covered:
            return self.requested_horizon_frames
        return max(0, self.stop_frame - 1)

    @property
    def unknown_from_frame(self) -> int | None:
        if self.horizon_covered:
            return None
        return self.covered_through_frame + 1

    @property
    def complete_events(self) -> tuple[TaggedVelocityToggle, ...] | None:
        """Return a lowerable complete schedule, never a partial prefix."""

        return self.events if self.horizon_covered else None

    def require_complete_events(self) -> tuple[TaggedVelocityToggle, ...]:
        events = self.complete_events
        if events is None:
            raise IncompleteEclLookaheadError(
                "ECL callback lookahead is incomplete: "
                f"{self.stop_reason} at relative frame {self.stop_frame}"
            )
        return events


class IncompleteEclLookaheadError(RuntimeError):
    """A prefix-only callback result was requested as a complete schedule."""


class EclInstructionCache:
    """Cache immutable ECL instructions read from the target process."""

    def __init__(self) -> None:
        self._instructions: dict[int, RuntimeEclInstruction] = {}

    def clear(self) -> None:
        self._instructions.clear()

    def cached_instruction(self, address: int) -> RuntimeEclInstruction:
        """Return an immutable instruction without performing process I/O."""

        cached = self._instructions.get(address)
        if cached is None:
            raise RuntimeError(
                f"ECL instruction {address:#x} is absent from the warm cache"
            )
        return cached

    def instruction(
        self,
        read_memory: Callable[[int, int], bytes],
        address: int,
    ) -> RuntimeEclInstruction:
        cached = self._instructions.get(address)
        if cached is not None:
            return cached
        header = read_memory(address, ECL_HEADER_SIZE)
        time, opcode, size, _, difficulty_mask, parameter_mask = struct.unpack(
            "<iHHBBH",
            header,
        )
        if size < ECL_HEADER_SIZE or size > 0x400:
            raise ValueError(f"invalid live ECL instruction size {size}")
        payload_size = size - ECL_HEADER_SIZE
        payload = (
            read_memory(address + ECL_HEADER_SIZE, payload_size)
            if payload_size
            else b""
        )
        instruction = RuntimeEclInstruction(
            address,
            time,
            opcode,
            size,
            difficulty_mask,
            parameter_mask,
            payload,
        )
        self._instructions[address] = instruction
        return instruction


def read_main_ecl_vm_snapshot(
    reader: ProcessMemoryReader,
    enemy_pointer: int,
) -> EclVmSnapshot:
    if enemy_pointer <= 0:
        raise ValueError("enemy pointer must be positive")
    vm = reader.read(
        enemy_pointer + ENEMY_MAIN_ECL_VM_OFFSET,
        ECL_VM_SNAPSHOT_SIZE,
    )
    local_projection = EclVmLocalProjection.from_vm_bytes(vm)
    instruction_pointer = struct.unpack_from("<I", vm, 0)[0]
    tag_mask = local_projection.integer_locals[0] & 0xFFFFFFFF
    callback_angle = local_projection.float_value(ECL_FLOAT_CALLBACK_ANGLE)
    callback_speed = local_projection.float_value(ECL_FLOAT_CALLBACK_SPEED)
    assert callback_angle is not None
    assert callback_speed is not None
    timer_fraction = struct.unpack_from(
        "<f",
        vm,
        ECL_VM_TIMER_FRACTION_OFFSET,
    )[0]
    timer_elapsed = struct.unpack_from(
        "<i",
        vm,
        ECL_VM_TIMER_ELAPSED_OFFSET,
    )[0]
    time_scale = struct.unpack(
        "<f",
        reader.read(GAMEPLAY_TIME_SCALE_ADDRESS, 4),
    )[0]
    finite = (
        timer_fraction,
        callback_angle,
        callback_speed,
        time_scale,
    )
    if (
        instruction_pointer < 0x10000
        or not all(math.isfinite(value) for value in finite)
        or time_scale <= 0.0
    ):
        raise ValueError("invalid live ECL VM snapshot")
    return EclVmSnapshot(
        instruction_pointer,
        timer_fraction,
        timer_elapsed,
        tag_mask,
        callback_angle,
        callback_speed,
        time_scale,
        local_projection,
    )


def _eligible(
    instruction: RuntimeEclInstruction,
    active_difficulty_mask: int,
) -> bool:
    return (
        active_difficulty_mask & instruction.difficulty_mask
    ) == active_difficulty_mask


def _literal_pair(instruction: RuntimeEclInstruction) -> tuple[int, int] | None:
    if len(instruction.payload) < 8:
        return None
    return struct.unpack_from("<ii", instruction.payload)


def predict_tagged_velocity_toggles(
    snapshot: EclVmSnapshot,
    *,
    instruction_at: Callable[[int], RuntimeEclInstruction],
    horizon_frames: int,
    active_difficulty_mask: int,
    max_instructions: int = 256,
) -> tuple[TaggedVelocityToggle, ...]:
    """Return events only when the audited lookahead covers the horizon."""

    return analyze_tagged_velocity_toggles(
        snapshot,
        instruction_at=instruction_at,
        horizon_frames=horizon_frames,
        active_difficulty_mask=active_difficulty_mask,
        max_instructions=max_instructions,
    ).require_complete_events()


def analyze_tagged_velocity_toggles(
    snapshot: EclVmSnapshot,
    *,
    instruction_at: Callable[[int], RuntimeEclInstruction],
    horizon_frames: int,
    active_difficulty_mask: int,
    max_instructions: int = 256,
) -> EclLookaheadResult:
    """Follow literal main-VM control flow and report why scanning stopped."""

    if horizon_frames < 0:
        raise ValueError("ECL lookahead horizon cannot be negative")
    if active_difficulty_mask <= 0:
        raise ValueError("active difficulty mask must be positive")
    if max_instructions <= 0:
        raise ValueError("instruction limit must be positive")
    pc = snapshot.instruction_pointer
    try:
        timer = Th08TimerState(
            snapshot.timer_elapsed,
            snapshot.timer_fraction_bits,
        )
        time_scale_bits = snapshot.time_scale_bits
        if not math.isfinite(snapshot.time_scale) or snapshot.time_scale <= 0.0:
            raise ValueError("unsupported live ECL time scale")
    except (OverflowError, struct.error, ValueError):
        return EclLookaheadResult(
            events=(),
            instructions_scanned=0,
            stop_reason="unsupported_native_timer_state",
            horizon_covered=False,
            requested_horizon_frames=horizon_frames,
            stop_frame=0,
        )
    physical_frame = 0
    tag_mask = snapshot.tag_mask
    callback_angle = snapshot.callback_angle
    callback_speed = snapshot.callback_speed
    events: list[TaggedVelocityToggle] = []
    visited: set[tuple[int, int, int, int]] = set()
    instructions_scanned = 0
    stop_reason = "instruction_limit"
    horizon_covered = False

    for _ in range(max_instructions):
        state = (
            pc,
            timer.elapsed,
            timer.fraction_bits,
            physical_frame,
        )
        if state in visited:
            stop_reason = "repeated_state"
            break
        visited.add(state)
        instruction = instruction_at(pc)
        instructions_scanned += 1
        try:
            timer, delta, reached = advance_until_elapsed(
                timer,
                target_elapsed=instruction.time,
                time_scale_bits=time_scale_bits,
                max_physical_frames=horizon_frames - physical_frame,
            )
        except ValueError:
            stop_reason = "unsupported_native_timer_transition"
            break
        physical_frame += delta
        if not reached:
            stop_reason = "horizon"
            horizon_covered = True
            break

        eligible = _eligible(instruction, active_difficulty_mask)
        if eligible and instruction.opcode == ECL_OP_TERMINATE:
            stop_reason = "terminate"
            horizon_covered = True
            break
        if eligible and instruction.opcode == ECL_OP_JUMP:
            pair = _literal_pair(instruction)
            if pair is None or instruction.parameter_mask:
                stop_reason = "unsupported_jump"
                break
            target_time, relative_offset = pair
            pc = instruction.address + relative_offset
            timer = timer.with_elapsed_preserving_fraction(target_time)
            continue
        if eligible and instruction.opcode == ECL_OP_RESET_TIMER:
            stop_reason = "unsupported_timer_reset"
            break
        if eligible and (
            instruction.opcode == ECL_OP_LOOP_DECREMENT_JUMP
            or ECL_OP_FIRST_CONDITIONAL_JUMP
            <= instruction.opcode
            <= ECL_OP_LAST_CONDITIONAL_JUMP
            or instruction.opcode in (ECL_OP_CALL_SUBROUTINE, ECL_OP_RETURN_SUBROUTINE)
        ):
            stop_reason = "unsupported_control_flow"
            break
        if eligible and instruction.opcode == ECL_OP_SET_INT:
            pair = _literal_pair(instruction)
            if pair is not None:
                destination, value = pair
                if (
                    destination == ECL_INT_TAG_MASK
                    and instruction.parameter_mask & 0x01
                    and not instruction.parameter_mask & 0x02
                ):
                    tag_mask = value & 0xFFFFFFFF
        elif eligible and instruction.opcode == ECL_OP_SET_FLOAT:
            pair = _literal_pair(instruction)
            if pair is not None:
                destination_bits, value_bits = pair
                destination = struct.unpack(
                    "<f",
                    struct.pack("<I", destination_bits & 0xFFFFFFFF),
                )[0]
                value = struct.unpack(
                    "<f",
                    struct.pack("<I", value_bits & 0xFFFFFFFF),
                )[0]
                if (
                    instruction.parameter_mask & 0x01
                    and not instruction.parameter_mask & 0x02
                    and math.isfinite(value)
                ):
                    if math.isclose(
                        destination,
                        float(ECL_FLOAT_CALLBACK_ANGLE),
                    ):
                        callback_angle = value
                    elif math.isclose(
                        destination,
                        float(ECL_FLOAT_CALLBACK_SPEED),
                    ):
                        callback_speed = value
        elif eligible and instruction.opcode == ECL_OP_INVOKE_CALLBACK:
            pair = _literal_pair(instruction)
            if pair is None or instruction.parameter_mask & 0x01:
                stop_reason = "unsupported_callback"
                break
            callback_index, _ = pair
            if (
                callback_index == CALLBACK_TOGGLE_TAGGED_BULLET
                and physical_frame > 0
                and tag_mask
                and all(
                    math.isfinite(value) for value in (callback_angle, callback_speed)
                )
            ):
                speed = callback_speed * snapshot.time_scale
                events.append(
                    TaggedVelocityToggle(
                        physical_frame,
                        callback_index,
                        tag_mask,
                        math.cos(callback_angle) * speed,
                        math.sin(callback_angle) * speed,
                    )
                )
        pc = instruction.address + instruction.size
    else:
        stop_reason = "instruction_limit"
    return EclLookaheadResult(
        events=tuple(events),
        instructions_scanned=instructions_scanned,
        stop_reason=stop_reason,
        horizon_covered=horizon_covered,
        requested_horizon_frames=horizon_frames,
        stop_frame=physical_frame,
    )


def velocity_changes_for_tagged_bullet(
    *,
    tag_flags: int,
    phase_state: int,
    base_speed: float | None,
    base_angle: float | None,
    time_scale: float,
    toggles: tuple[TaggedVelocityToggle, ...],
) -> tuple[VelocityChange, ...]:
    """Compatibility view of callback-12 motion changes."""

    return trajectory_changes_for_tagged_bullet(
        tag_flags=tag_flags,
        phase_state=phase_state,
        base_speed=base_speed,
        base_angle=base_angle,
        time_scale=time_scale,
        toggles=toggles,
    ).velocity_changes


def trajectory_changes_for_tagged_bullet(
    *,
    tag_flags: int,
    phase_state: int,
    base_speed: float | None,
    base_angle: float | None,
    time_scale: float,
    toggles: tuple[TaggedVelocityToggle, ...],
) -> TaggedBulletTrajectoryChanges:
    """Lower callback 12 without dropping its native collision gate."""

    if (
        base_speed is None
        or base_angle is None
        or not math.isfinite(base_speed)
        or not math.isfinite(base_angle)
        or not math.isfinite(time_scale)
        or time_scale <= 0.0
    ):
        return TaggedBulletTrajectoryChanges((), ())
    state = phase_state
    changes: list[VelocityChange] = []
    collision_changes: list[CollisionStateChange] = []
    for toggle in toggles:
        if toggle.callback_index != CALLBACK_TOGGLE_TAGGED_BULLET:
            continue
        if not tag_flags & toggle.tag_mask:
            continue
        transition = callback_12_phase_transition(state)
        state = transition.next_phase_state
        if transition.use_callback_velocity:
            velocity_x = toggle.alternate_velocity_x
            velocity_y = toggle.alternate_velocity_y
        else:
            speed = base_speed * time_scale
            velocity_x = math.cos(base_angle) * speed
            velocity_y = math.sin(base_angle) * speed
        changes.append(VelocityChange(toggle.frame, velocity_x, velocity_y))
        collision_changes.append(
            CollisionStateChange(
                toggle.frame,
                transition.collision_enabled,
            )
        )
    return TaggedBulletTrajectoryChanges(
        tuple(changes),
        tuple(collision_changes),
    )
