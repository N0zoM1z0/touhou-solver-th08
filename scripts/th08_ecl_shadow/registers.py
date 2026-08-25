"""Mutable working registers for the offline TH08 ECL local shadow."""

from __future__ import annotations

import math

from th08_ecl_vm_state import (
    ECL_VM_CALL_FLOAT_PARAMETER_COUNT,
    ECL_VM_CALL_FLOAT_PARAMETER_FIRST,
    ECL_VM_CALL_INTEGER_PARAMETER_COUNT,
    ECL_VM_CALL_INTEGER_PARAMETER_FIRST,
    ECL_VM_FLOAT_LOCAL_COUNT,
    ECL_VM_FLOAT_LOCAL_FIRST,
    ECL_VM_INTEGER_LOCAL_COUNT,
    ECL_VM_INTEGER_LOCAL_FIRST,
    ECL_VM_SCRATCH_INTEGER_COUNT,
    ECL_VM_SCRATCH_INTEGER_FIRST,
    ECL_VM_SPAWN_FLOAT_PARAMETER_COUNT,
    ECL_VM_SPAWN_FLOAT_PARAMETER_FIRST,
    EclVmLocalProjection,
    float32_from_bits,
)


def signed_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & (1 << 31) else value


def float_destination_variable(bits: int) -> int | None:
    value = float32_from_bits(bits & 0xFFFFFFFF)
    if not math.isfinite(value) or not value.is_integer():
        return None
    variable = int(value)
    ranges = (
        (ECL_VM_FLOAT_LOCAL_FIRST, ECL_VM_FLOAT_LOCAL_COUNT),
        (
            ECL_VM_SPAWN_FLOAT_PARAMETER_FIRST,
            ECL_VM_SPAWN_FLOAT_PARAMETER_COUNT,
        ),
        (
            ECL_VM_CALL_FLOAT_PARAMETER_FIRST,
            ECL_VM_CALL_FLOAT_PARAMETER_COUNT,
        ),
    )
    return (
        variable
        if any(first <= variable < first + count for first, count in ranges)
        else None
    )


class LocalRegisters:
    """Mutable copy that freezes back to one immutable projection."""

    def __init__(self, projection: EclVmLocalProjection) -> None:
        self.integer_locals = list(projection.integer_locals)
        self.float_local_bits = list(projection.float_local_bits)
        self.scratch_integers = list(projection.scratch_integers)
        self.spawn_float_parameter_bits = (
            list(projection.spawn_float_parameter_bits)
            if projection.spawn_float_parameter_bits is not None
            else None
        )
        self.call_integer_parameters = (
            list(projection.call_integer_parameters)
            if projection.call_integer_parameters is not None
            else None
        )
        self.call_float_parameter_bits = (
            list(projection.call_float_parameter_bits)
            if projection.call_float_parameter_bits is not None
            else None
        )

    def freeze(self) -> EclVmLocalProjection:
        return EclVmLocalProjection(
            tuple(self.integer_locals),
            tuple(self.float_local_bits),
            tuple(self.scratch_integers),
            (
                tuple(self.spawn_float_parameter_bits)
                if self.spawn_float_parameter_bits is not None
                else None
            ),
            (
                tuple(self.call_integer_parameters)
                if self.call_integer_parameters is not None
                else None
            ),
            (
                tuple(self.call_float_parameter_bits)
                if self.call_float_parameter_bits is not None
                else None
            ),
        )

    def read_integer(self, variable: int) -> int | None:
        index = variable - ECL_VM_INTEGER_LOCAL_FIRST
        if 0 <= index < ECL_VM_INTEGER_LOCAL_COUNT:
            return self.integer_locals[index]
        index = variable - ECL_VM_SCRATCH_INTEGER_FIRST
        if 0 <= index < ECL_VM_SCRATCH_INTEGER_COUNT:
            return self.scratch_integers[index]
        index = variable - ECL_VM_CALL_INTEGER_PARAMETER_FIRST
        if (
            self.call_integer_parameters is not None
            and 0 <= index < ECL_VM_CALL_INTEGER_PARAMETER_COUNT
        ):
            return self.call_integer_parameters[index]
        return None

    def write_integer(self, variable: int, value: int) -> bool:
        value = signed_int32(value)
        index = variable - ECL_VM_INTEGER_LOCAL_FIRST
        if 0 <= index < ECL_VM_INTEGER_LOCAL_COUNT:
            self.integer_locals[index] = value
            return True
        index = variable - ECL_VM_SCRATCH_INTEGER_FIRST
        if 0 <= index < ECL_VM_SCRATCH_INTEGER_COUNT:
            self.scratch_integers[index] = value
            return True
        index = variable - ECL_VM_CALL_INTEGER_PARAMETER_FIRST
        if (
            self.call_integer_parameters is not None
            and 0 <= index < ECL_VM_CALL_INTEGER_PARAMETER_COUNT
        ):
            self.call_integer_parameters[index] = value
            return True
        return False

    def write_float_bits(self, variable: int, bits: int) -> bool:
        index = variable - ECL_VM_FLOAT_LOCAL_FIRST
        if 0 <= index < ECL_VM_FLOAT_LOCAL_COUNT:
            self.float_local_bits[index] = bits & 0xFFFFFFFF
            return True
        index = variable - ECL_VM_SPAWN_FLOAT_PARAMETER_FIRST
        if (
            self.spawn_float_parameter_bits is not None
            and 0 <= index < ECL_VM_SPAWN_FLOAT_PARAMETER_COUNT
        ):
            self.spawn_float_parameter_bits[index] = bits & 0xFFFFFFFF
            return True
        index = variable - ECL_VM_CALL_FLOAT_PARAMETER_FIRST
        if (
            self.call_float_parameter_bits is not None
            and 0 <= index < ECL_VM_CALL_FLOAT_PARAMETER_COUNT
        ):
            self.call_float_parameter_bits[index] = bits & 0xFFFFFFFF
            return True
        return False


__all__ = ["LocalRegisters", "float_destination_variable", "signed_int32"]
