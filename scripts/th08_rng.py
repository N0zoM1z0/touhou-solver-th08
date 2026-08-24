#!/usr/bin/env python3
"""Exact TH08 gameplay RNG recovered from th08.exe at 0x0043ECC0."""

from __future__ import annotations

from dataclasses import dataclass
import struct


def _f32(value: float | int) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


@dataclass
class Th08Rng:
    """The game's shared 16-bit RNG state and its consumption counter."""

    state: int
    calls: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.state <= 0xFFFF:
            raise ValueError("TH08 RNG seed must fit in 16 bits")
        if self.calls < 0:
            raise ValueError("TH08 RNG call count cannot be negative")

    def next_u16(self) -> int:
        mixed = ((self.state ^ 0x9630) - 0x6553) & 0xFFFF
        self.state = ((mixed << 2) + ((mixed & 0xC000) >> 14)) & 0xFFFF
        self.calls += 1
        return self.state

    def next_u32(self) -> int:
        return (self.next_u16() << 16) | self.next_u16()

    def next_unit(self) -> float:
        """Match 0x0043ED50: a value in [0, 1)."""

        # Global.cpp casts the U32 numerator to f32 before division. UINT_MAX
        # itself rounds to 2**32 as f32. Keeping the old double numerator
        # changes 62,784 of the 65,536 possible first-seed results.
        return _f32(_f32(self.next_u32()) / _f32(0xFFFFFFFF))

    def next_signed_unit(self) -> float:
        """Match 0x0043ED80: a value in [-1, 1)."""

        return _f32(
            _f32(_f32(self.next_u32()) / _f32(0x7FFFFFFF)) - 1.0
        )

    def next_scaled(self, span: float) -> float:
        """Match 0x0040D390: a uniform value in [0, span)."""

        return _f32(self.next_unit() * _f32(span))

    def next_mod(self, modulus: int) -> int:
        """Match 0x00406EF0, including its zero-modulus result."""

        return self.next_u32() % modulus if modulus else 0
