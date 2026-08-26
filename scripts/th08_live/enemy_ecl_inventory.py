"""Compact main-ECL VM inventory decoded from an existing enemy-pool blob."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import time
from typing import Callable

from th08_ecl_runtime import (
    ECL_VM_SNAPSHOT_SIZE,
    ECL_VM_TIMER_ELAPSED_OFFSET,
    ECL_VM_TIMER_FRACTION_OFFSET,
    ENEMY_MAIN_ECL_VM_OFFSET,
)
from th08_ecl_vm_state import (
    ECL_VM_LOCAL_PROJECTION_LAYOUT,
    EclVmLocalProjection,
)


ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT_V1 = (
    "th08-enemy-main-ecl-vm-inventory-v1"
)
ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT_V2 = (
    "th08-enemy-main-ecl-vm-inventory-v2"
)
ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT = (
    "th08-enemy-main-ecl-vm-inventory-v3"
)
ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET = 0x3384
ENEMY_AUXILIARY_ECL_CONTEXT_COUNT = 4
MINIMUM_RUNTIME_ECL_ADDRESS = 0x00010000
MAXIMUM_RUNTIME_ECL_ADDRESS = 0x7FFFFFFF


@dataclass(frozen=True, slots=True)
class EnemyMainEclVmObservation:
    """Exact capture-time state for one initialized active enemy main VM."""

    slot: int
    enemy_pointer: int
    enemy_flags: int
    instruction_pointer: int
    timer_fraction_bits: int
    timer_elapsed: int
    local_projection: EclVmLocalProjection

    def record(self) -> list[object]:
        """Serialize one fixed-position row without repeated field names."""

        row: list[object] = [
            self.slot,
            self.enemy_pointer,
            self.enemy_flags,
            self.instruction_pointer,
            self.timer_fraction_bits,
            self.timer_elapsed,
            list(self.local_projection.integer_locals),
            list(self.local_projection.float_local_bits),
            list(self.local_projection.scratch_integers),
        ]
        if self.local_projection.copied_parameter_block_complete:
            assert self.local_projection.spawn_float_parameter_bits is not None
            assert self.local_projection.call_integer_parameters is not None
            assert self.local_projection.call_float_parameter_bits is not None
            row.extend(
                (
                    list(self.local_projection.spawn_float_parameter_bits),
                    list(self.local_projection.call_integer_parameters),
                    list(self.local_projection.call_float_parameter_bits),
                )
            )
        return row


@dataclass(frozen=True, slots=True)
class InvalidEnemyMainEclVmObservation:
    """An active enemy slot whose main VM is not initialized or is invalid."""

    slot: int
    enemy_pointer: int
    enemy_flags: int
    instruction_pointer: int

    def record(self) -> list[int]:
        return [
            self.slot,
            self.enemy_pointer,
            self.enemy_flags,
            self.instruction_pointer,
        ]


@dataclass(frozen=True, slots=True)
class EnemyAuxiliaryEclContextPointerObservation:
    """Four raw auxiliary-context pointers owned by one active enemy."""

    slot: int
    enemy_pointer: int
    enemy_flags: int
    context_pointers: tuple[int, int, int, int]

    def record(self) -> list[object]:
        return [
            self.slot,
            self.enemy_pointer,
            self.enemy_flags,
            list(self.context_pointers),
        ]


@dataclass(frozen=True, slots=True)
class InvalidEnemyAuxiliaryEclContextPointer:
    """One non-null auxiliary-context pointer outside the declared range."""

    slot: int
    enemy_pointer: int
    auxiliary_index: int
    context_pointer: int

    def record(self) -> list[int]:
        return [
            self.slot,
            self.enemy_pointer,
            self.auxiliary_index,
            self.context_pointer,
        ]


@dataclass(frozen=True, slots=True)
class EnemyMainEclVmInventory:
    """Bounded main-VM and auxiliary-pointer observation from one blob."""

    scanned_slots: int
    active_slots: int
    observations: tuple[EnemyMainEclVmObservation, ...]
    invalid: tuple[InvalidEnemyMainEclVmObservation, ...]
    auxiliary_contexts: tuple[
        EnemyAuxiliaryEclContextPointerObservation,
        ...,
    ]
    invalid_auxiliary_contexts: tuple[
        InvalidEnemyAuxiliaryEclContextPointer,
        ...,
    ]
    decode_ms: float
    auxiliary_pointer_coverage: bool = True

    def record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "layout": ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT,
            "vm_local_layout": ECL_VM_LOCAL_PROJECTION_LAYOUT,
            "scope": (
                "ordinary_enemy_pool_prefix_main_vm_and_auxiliary_pointers"
                if self.auxiliary_pointer_coverage
                else "ordinary_enemy_pool_prefix_main_vm_only"
            ),
            "auxiliary_pointer_coverage": self.auxiliary_pointer_coverage,
            "scanned_slots": self.scanned_slots,
            "active_slots": self.active_slots,
            "valid_vms": len(self.observations),
            "invalid_active_vms": len(self.invalid),
            "rows": [observation.record() for observation in self.observations],
            "invalid_rows": [observation.record() for observation in self.invalid],
            "decode_ms": self.decode_ms,
        }
        if not self.auxiliary_pointer_coverage:
            return record
        non_null_auxiliary_contexts = sum(
            pointer != 0
            for observation in self.auxiliary_contexts
            for pointer in observation.context_pointers
        )
        record.update({
            "auxiliary_context_row_layout": (
                "slot_enemy_pointer_enemy_flags_four_raw_context_pointers"
            ),
            "auxiliary_context_rows": [
                observation.record()
                for observation in self.auxiliary_contexts
            ],
            "non_null_auxiliary_contexts": non_null_auxiliary_contexts,
            "invalid_auxiliary_contexts": len(
                self.invalid_auxiliary_contexts
            ),
            "invalid_auxiliary_context_rows": [
                observation.record()
                for observation in self.invalid_auxiliary_contexts
            ],
        })
        return record


def decode_enemy_main_ecl_vm_inventory(
    blob: bytes,
    *,
    pool_base: int,
    pool_size: int,
    enemy_stride: int,
    enemy_flags_offset: int,
    enemy_active_flag: int,
    include_auxiliary_context_pointers: bool = True,
    runtime_instruction_bounds: tuple[int, int] | None = None,
    maximum_runtime_address: int = MAXIMUM_RUNTIME_ECL_ADDRESS,
    clock: Callable[[], float] = time.perf_counter,
) -> EnemyMainEclVmInventory:
    """Decode active main VMs without issuing any process-memory read."""

    if pool_base <= 0:
        raise ValueError("enemy pool base must be positive")
    if pool_size < 0:
        raise ValueError("enemy pool size must be non-negative")
    if enemy_stride <= 0:
        raise ValueError("enemy stride must be positive")
    if not 0 <= enemy_flags_offset <= enemy_stride - 4:
        raise ValueError("enemy flags offset must belong to one record")
    if not enemy_active_flag:
        raise ValueError("enemy active flag must be non-zero")
    if not (
        MINIMUM_RUNTIME_ECL_ADDRESS
        <= maximum_runtime_address
        <= 0xFFFFFFFF
    ):
        raise ValueError("maximum runtime address is outside uint32 memory")
    if runtime_instruction_bounds is not None:
        lower, upper = runtime_instruction_bounds
        if not (
            MINIMUM_RUNTIME_ECL_ADDRESS <= lower < upper <= 0x100000000
        ):
            raise ValueError("runtime instruction bounds are invalid")
    if ENEMY_MAIN_ECL_VM_OFFSET + ECL_VM_SNAPSHOT_SIZE > enemy_stride:
        raise ValueError("main ECL VM prefix exceeds one enemy record")
    if (
        ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET
        + 4 * ENEMY_AUXILIARY_ECL_CONTEXT_COUNT
        > enemy_stride
    ):
        raise ValueError("auxiliary ECL context pointers exceed one enemy record")
    expected_size = pool_size * enemy_stride
    if len(blob) < expected_size:
        raise ValueError(f"enemy pool prefix requires {expected_size} bytes")

    started = clock()
    observations: list[EnemyMainEclVmObservation] = []
    invalid: list[InvalidEnemyMainEclVmObservation] = []
    auxiliary_contexts: list[
        EnemyAuxiliaryEclContextPointerObservation
    ] = []
    invalid_auxiliary_contexts: list[
        InvalidEnemyAuxiliaryEclContextPointer
    ] = []
    active_slots = 0
    for slot in range(pool_size):
        record_base = slot * enemy_stride
        enemy_flags = struct.unpack_from(
            "<I",
            blob,
            record_base + enemy_flags_offset,
        )[0]
        if not enemy_flags & enemy_active_flag:
            continue
        active_slots += 1
        enemy_pointer = pool_base + record_base
        if include_auxiliary_context_pointers:
            context_pointers = struct.unpack_from(
                "<4I",
                blob,
                record_base + ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
            )
            auxiliary_contexts.append(
                EnemyAuxiliaryEclContextPointerObservation(
                    slot=slot,
                    enemy_pointer=enemy_pointer,
                    enemy_flags=enemy_flags,
                    context_pointers=context_pointers,
                )
            )
            for auxiliary_index, context_pointer in enumerate(
                context_pointers
            ):
                if context_pointer != 0 and not (
                    MINIMUM_RUNTIME_ECL_ADDRESS
                    <= context_pointer
                    <= maximum_runtime_address
                ):
                    invalid_auxiliary_contexts.append(
                        InvalidEnemyAuxiliaryEclContextPointer(
                            slot=slot,
                            enemy_pointer=enemy_pointer,
                            auxiliary_index=auxiliary_index,
                            context_pointer=context_pointer,
                        )
                    )
        vm_base = record_base + ENEMY_MAIN_ECL_VM_OFFSET
        instruction_pointer = struct.unpack_from("<I", blob, vm_base)[0]
        instruction_pointer_valid = (
            runtime_instruction_bounds[0]
            <= instruction_pointer
            < runtime_instruction_bounds[1]
            if runtime_instruction_bounds is not None
            else (
                MINIMUM_RUNTIME_ECL_ADDRESS
                <= instruction_pointer
                <= maximum_runtime_address
            )
        )
        if not instruction_pointer_valid:
            invalid.append(
                InvalidEnemyMainEclVmObservation(
                    slot,
                    enemy_pointer,
                    enemy_flags,
                    instruction_pointer,
                )
            )
            continue
        vm = blob[vm_base : vm_base + ECL_VM_SNAPSHOT_SIZE]
        observations.append(
            EnemyMainEclVmObservation(
                slot=slot,
                enemy_pointer=enemy_pointer,
                enemy_flags=enemy_flags,
                instruction_pointer=instruction_pointer,
                timer_fraction_bits=struct.unpack_from(
                    "<I",
                    vm,
                    ECL_VM_TIMER_FRACTION_OFFSET,
                )[0],
                timer_elapsed=struct.unpack_from(
                    "<i",
                    vm,
                    ECL_VM_TIMER_ELAPSED_OFFSET,
                )[0],
                local_projection=EclVmLocalProjection.from_vm_bytes(vm),
            )
        )
    decode_ms = (clock() - started) * 1000.0
    return EnemyMainEclVmInventory(
        scanned_slots=pool_size,
        active_slots=active_slots,
        observations=tuple(observations),
        invalid=tuple(invalid),
        auxiliary_contexts=tuple(auxiliary_contexts),
        invalid_auxiliary_contexts=tuple(invalid_auxiliary_contexts),
        decode_ms=decode_ms,
        auxiliary_pointer_coverage=include_auxiliary_context_pointers,
    )


__all__ = [
    "ENEMY_AUXILIARY_ECL_CONTEXT_COUNT",
    "ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET",
    "ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT",
    "ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT_V1",
    "ENEMY_MAIN_ECL_VM_INVENTORY_LAYOUT_V2",
    "EnemyAuxiliaryEclContextPointerObservation",
    "EnemyMainEclVmInventory",
    "EnemyMainEclVmObservation",
    "InvalidEnemyAuxiliaryEclContextPointer",
    "InvalidEnemyMainEclVmObservation",
    "decode_enemy_main_ecl_vm_inventory",
]
