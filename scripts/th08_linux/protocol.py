"""Versioned wire contract for the native Linux TH08 input bridge."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Protocol

REQUEST_MAGIC = 0x51523854
RESPONSE_MAGIC = 0x53523854
PROTOCOL_VERSION = 1
REQUEST_SIZE = 32
RESPONSE_SIZE = 24
REPLAY_TARGET_STAMPED = 1 << 0
LIVES_PRESERVED = 1 << 1
IMMUTABLE_SNAPSHOT_PRESENT = 1 << 2
# Version 1 has no immutable-root fields.  Its strict decoder must therefore
# continue to reject the version-3-only flag.
KNOWN_REQUEST_FLAGS = REPLAY_TARGET_STAMPED | LIVES_PRESERVED

SHOOT = 1 << 0
BOMB = 1 << 1
FOCUS = 1 << 2
MENU = 1 << 3
UP = 1 << 4
DOWN = 1 << 5
LEFT = 1 << 6
RIGHT = 1 << 7
SKIP = 1 << 8
Q = 1 << 9
S = 1 << 10
HOME = 1 << 11
ENTER = 1 << 12
D = 1 << 13
RESET = 1 << 14
KNOWN_HARD_NO_BOMB_MASK = 0x7FFD

_REQUEST = struct.Struct("<IHHQHHH2xII")
_RESPONSE = struct.Struct("<IHHQHHI")


class ReceivingSocket(Protocol):
    def recv(self, size: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class InputRequest:
    epoch: int
    current_input: int
    previous_input: int
    rng_seed: int
    flags: int
    paused_milliseconds: int

    @property
    def replay_target_stamped(self) -> bool:
        return bool(self.flags & REPLAY_TARGET_STAMPED)

    @property
    def lives_preserved(self) -> bool:
        return bool(self.flags & LIVES_PRESERVED)


def read_exact(connection: ReceivingSocket, size: int) -> bytes:
    if size <= 0:
        raise ValueError("wire read size must be positive")
    output = bytearray()
    while len(output) < size:
        block = connection.recv(size - len(output))
        if not block:
            raise EOFError("solver bridge closed during a wire record")
        output.extend(block)
    return bytes(output)


def decode_request(data: bytes) -> InputRequest:
    if len(data) != REQUEST_SIZE:
        raise ValueError(
            f"solver request must be {REQUEST_SIZE} bytes, got {len(data)}"
        )
    (
        magic,
        version,
        declared_size,
        epoch,
        current_input,
        previous_input,
        rng_seed,
        flags,
        paused_milliseconds,
    ) = _REQUEST.unpack(data)
    if magic != REQUEST_MAGIC:
        raise ValueError(f"unknown solver request magic {magic:#010x}")
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported solver protocol version {version}")
    if declared_size != REQUEST_SIZE:
        raise ValueError(f"unexpected solver request size {declared_size}")
    if epoch <= 0:
        raise ValueError("solver input epoch must be positive")
    if flags & ~KNOWN_REQUEST_FLAGS:
        raise ValueError(f"solver request has unknown flags: {flags:#010x}")
    return InputRequest(
        epoch=epoch,
        current_input=current_input,
        previous_input=previous_input,
        rng_seed=rng_seed,
        flags=flags,
        paused_milliseconds=paused_milliseconds,
    )


def validate_hard_no_bomb_mask(mask: int) -> int:
    if not 0 <= mask <= 0xFFFF:
        raise ValueError("input mask must fit an unsigned 16-bit value")
    if mask & BOMB:
        raise ValueError("Bomb input is forbidden")
    if mask & ~KNOWN_HARD_NO_BOMB_MASK:
        raise ValueError(f"input mask has unknown bits: {mask:#06x}")
    if mask & UP and mask & DOWN:
        raise ValueError("input mask contains both up and down")
    if mask & LEFT and mask & RIGHT:
        raise ValueError("input mask contains both left and right")
    return mask


def encode_response(epoch: int, input_mask: int) -> bytes:
    if not 0 < epoch <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("response epoch must be a positive unsigned 64-bit value")
    mask = validate_hard_no_bomb_mask(input_mask)
    return _RESPONSE.pack(
        RESPONSE_MAGIC,
        PROTOCOL_VERSION,
        RESPONSE_SIZE,
        epoch,
        mask,
        0,
        0,
    )
