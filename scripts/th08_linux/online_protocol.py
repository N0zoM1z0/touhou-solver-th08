"""Non-blocking, exact-epoch wire contract for native Linux TH08.

The game publishes after a completed logical update and never waits for the
solver.  A response is eligible only for the immediately following input
epoch; late responses are discarded by the game.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import time

from th08_linux.protocol import (
    IMMUTABLE_SNAPSHOT_PRESENT,
    LIVES_PRESERVED,
    REPLAY_TARGET_STAMPED,
    REQUEST_MAGIC,
    RESPONSE_MAGIC,
    validate_hard_no_bomb_mask,
)


PROTOCOL_VERSION = 3
REQUEST_SIZE = 80
RESPONSE_SIZE = 32
SNAPSHOT_RELEASE_SIZE = 24
SNAPSHOT_RELEASE_MAGIC = 0x4C523854  # "T8RL" as little endian.
NO_SNAPSHOT_SLOT = 0xFFFF
MAXIMUM_SNAPSHOT_SIZE = 32 * 1024 * 1024
KNOWN_ONLINE_REQUEST_FLAGS = (
    REPLAY_TARGET_STAMPED
    | LIVES_PRESERVED
    | IMMUTABLE_SNAPSHOT_PRESENT
)

_REQUEST = struct.Struct("<IHHQQHHHHIIIIQQIIII")
_RESPONSE = struct.Struct("<IHHQQHHI")
_SNAPSHOT_RELEASE = struct.Struct("<IHHQHHI")


@dataclass(frozen=True, slots=True)
class OnlineInputRequest:
    source_epoch: int
    target_epoch: int
    current_input: int
    previous_input: int
    rng_seed: int
    snapshot_slot: int
    flags: int
    deadline_misses: int
    late_responses: int
    dropped_requests: int
    published_monotonic_us: int
    snapshot_generation: int
    snapshot_address: int
    snapshot_size: int
    snapshot_entry_count: int
    dropped_snapshots: int

    @property
    def epoch(self) -> int:
        """Compatibility spelling for the requested target input epoch."""

        return self.target_epoch

    @property
    def replay_target_stamped(self) -> bool:
        return bool(self.flags & REPLAY_TARGET_STAMPED)

    @property
    def lives_preserved(self) -> bool:
        return bool(self.flags & LIVES_PRESERVED)

    @property
    def snapshot_present(self) -> bool:
        return bool(self.flags & IMMUTABLE_SNAPSHOT_PRESENT)

    def publication_age_ms(self, *, now_ns: int | None = None) -> float:
        observed_ns = time.monotonic_ns() if now_ns is None else now_ns
        published_ns = self.published_monotonic_us * 1000
        return max(observed_ns - published_ns, 0) / 1_000_000.0


def decode_online_request(data: bytes) -> OnlineInputRequest:
    if len(data) != REQUEST_SIZE:
        raise ValueError(
            f"online solver request must be {REQUEST_SIZE} bytes, got {len(data)}"
        )
    (
        magic,
        version,
        declared_size,
        source_epoch,
        target_epoch,
        current_input,
        previous_input,
        rng_seed,
        snapshot_slot,
        flags,
        deadline_misses,
        late_responses,
        dropped_requests,
        published_monotonic_us,
        snapshot_generation,
        snapshot_address,
        snapshot_size,
        snapshot_entry_count,
        dropped_snapshots,
    ) = _REQUEST.unpack(data)
    if magic != REQUEST_MAGIC:
        raise ValueError(f"unknown online request magic {magic:#010x}")
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported online protocol version {version}")
    if declared_size != REQUEST_SIZE:
        raise ValueError(f"unexpected online request size {declared_size}")
    if source_epoch <= 0 or target_epoch != source_epoch + 1:
        raise ValueError(
            "online request must target exactly source input epoch + 1"
        )
    if flags & ~KNOWN_ONLINE_REQUEST_FLAGS:
        raise ValueError(f"online request has unknown flags: {flags:#010x}")
    if published_monotonic_us <= 0:
        raise ValueError("online request omitted its monotonic publication time")
    validate_hard_no_bomb_mask(current_input)
    validate_hard_no_bomb_mask(previous_input)
    snapshot_present = bool(flags & IMMUTABLE_SNAPSHOT_PRESENT)
    if snapshot_present:
        if snapshot_slot not in (0, 1):
            raise ValueError("online request snapshot slot is invalid")
        if (
            snapshot_generation <= 0
            or snapshot_address <= 0
            or snapshot_size < 80
            or snapshot_size > MAXIMUM_SNAPSHOT_SIZE
            or snapshot_entry_count <= 0
        ):
            raise ValueError("online request snapshot certificate is incomplete")
    elif (
        snapshot_slot != NO_SNAPSHOT_SLOT
        or snapshot_generation != 0
        or snapshot_address != 0
        or snapshot_size != 0
        or snapshot_entry_count != 0
    ):
        raise ValueError("snapshot metadata is present without its request flag")
    return OnlineInputRequest(
        source_epoch=source_epoch,
        target_epoch=target_epoch,
        current_input=current_input,
        previous_input=previous_input,
        rng_seed=rng_seed,
        snapshot_slot=snapshot_slot,
        flags=flags,
        deadline_misses=deadline_misses,
        late_responses=late_responses,
        dropped_requests=dropped_requests,
        published_monotonic_us=published_monotonic_us,
        snapshot_generation=snapshot_generation,
        snapshot_address=snapshot_address,
        snapshot_size=snapshot_size,
        snapshot_entry_count=snapshot_entry_count,
        dropped_snapshots=dropped_snapshots,
    )


def encode_online_response(
    *,
    source_epoch: int,
    target_epoch: int,
    input_mask: int,
) -> bytes:
    if source_epoch <= 0 or source_epoch > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("source epoch must be a positive unsigned 64-bit value")
    if target_epoch != source_epoch + 1 or target_epoch > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("response must target exactly source epoch + 1")
    mask = validate_hard_no_bomb_mask(input_mask)
    return _RESPONSE.pack(
        RESPONSE_MAGIC,
        PROTOCOL_VERSION,
        RESPONSE_SIZE,
        source_epoch,
        target_epoch,
        mask,
        0,
        0,
    )


def encode_snapshot_release(*, generation: int, slot: int) -> bytes:
    if generation <= 0 or generation > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("snapshot generation must be a positive u64")
    if slot not in (0, 1):
        raise ValueError("snapshot release slot is invalid")
    return _SNAPSHOT_RELEASE.pack(
        SNAPSHOT_RELEASE_MAGIC,
        PROTOCOL_VERSION,
        SNAPSHOT_RELEASE_SIZE,
        generation,
        slot,
        0,
        0,
    )


__all__ = (
    "OnlineInputRequest",
    "MAXIMUM_SNAPSHOT_SIZE",
    "PROTOCOL_VERSION",
    "REQUEST_SIZE",
    "RESPONSE_SIZE",
    "SNAPSHOT_RELEASE_MAGIC",
    "SNAPSHOT_RELEASE_SIZE",
    "decode_online_request",
    "encode_online_response",
    "encode_snapshot_release",
)
