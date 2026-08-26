"""Exact decoded-ECL image to runtime-instruction mapping."""

from __future__ import annotations

import hashlib
import struct

from th08_ecl_runtime import RuntimeEclInstruction
from th08_ecl_tool.core import EclFile


ECL_HEADER_SIZE = 12
MINIMUM_RUNTIME_ADDRESS = 0x00010000
MAXIMUM_RUNTIME_ADDRESS = 0xFFFFFFFF


def build_exact_runtime_instruction_index(
    ecl: EclFile,
    image: bytes,
    *,
    runtime_base: int,
    expected_sha256: str | None = None,
) -> dict[int, RuntimeEclInstruction]:
    """Build a runtime-address index while rechecking parsed fields to bytes."""

    if not MINIMUM_RUNTIME_ADDRESS <= runtime_base <= MAXIMUM_RUNTIME_ADDRESS:
        raise ValueError("runtime ECL base is outside the supported address range")
    digest = hashlib.sha256(image).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("runtime ECL image digest does not match its identity")
    if ecl.sha256 != digest:
        raise ValueError("parsed ECL identity does not match the supplied image")

    index: dict[int, RuntimeEclInstruction] = {}
    for subroutine in ecl.subroutines:
        for parsed in subroutine.instructions:
            end = parsed.offset + parsed.size
            if parsed.offset < 0 or end > len(image):
                raise ValueError("parsed ECL instruction is outside its image")
            header = image[parsed.offset : parsed.offset + ECL_HEADER_SIZE]
            if len(header) != ECL_HEADER_SIZE:
                raise ValueError("truncated ECL instruction header")
            (
                time_value,
                opcode,
                size,
                _byte_08,
                difficulty_mask,
                parameter_mask,
            ) = struct.unpack("<iHHBBH", header)
            if (
                time_value != parsed.time
                or opcode != parsed.opcode
                or size != parsed.size
                or difficulty_mask != parsed.difficulty_mask
                or parameter_mask != parsed.parameter_mask
            ):
                raise ValueError(
                    "parsed ECL instruction disagrees with exact image bytes"
                )
            address = runtime_base + parsed.offset
            if address > MAXIMUM_RUNTIME_ADDRESS:
                raise ValueError("runtime ECL instruction address overflows")
            if address in index:
                raise ValueError("duplicate runtime ECL instruction address")
            index[address] = RuntimeEclInstruction(
                address=address,
                time=time_value,
                opcode=opcode,
                size=size,
                difficulty_mask=difficulty_mask,
                parameter_mask=parameter_mask,
                payload=image[parsed.offset + ECL_HEADER_SIZE : end],
            )
    return index


__all__ = ["build_exact_runtime_instruction_index"]
