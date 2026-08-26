"""Independent fixed-address witness for one blocked bridge request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from th08_linux.protocol import InputRequest
from th08_runtime.game_state import (
    ADDR_GAMEPLAY_RNG,
    ADDR_LAST_FRAME_INPUT,
    ADDR_RAW_INPUT,
)


class WireStateReader(Protocol):
    def u16(self, address: int) -> int: ...


@dataclass(frozen=True, slots=True)
class LockstepMemoryWitness:
    supervisor_current_input: int
    supervisor_previous_input: int
    rng_seed: int


def validate_request_memory_witness(
    request: InputRequest,
    reader: WireStateReader,
    *,
    verify_rng: bool = True,
) -> LockstepMemoryWitness:
    """Match the wire fields to their exact source globals, or fail closed."""

    witness = LockstepMemoryWitness(
        supervisor_current_input=reader.u16(ADDR_RAW_INPUT),
        supervisor_previous_input=reader.u16(ADDR_LAST_FRAME_INPUT),
        rng_seed=reader.u16(ADDR_GAMEPLAY_RNG),
    )
    if request.current_input != witness.supervisor_current_input:
        raise RuntimeError(
            "bridge/g_CurFrameInput memory witness mismatch: "
            f"wire={request.current_input:#06x}, "
            f"memory={witness.supervisor_current_input:#06x}"
        )
    if request.previous_input != witness.supervisor_previous_input:
        raise RuntimeError(
            "bridge/g_LastFrameInput memory witness mismatch: "
            f"wire={request.previous_input:#06x}, "
            f"memory={witness.supervisor_previous_input:#06x}"
        )
    if verify_rng and request.rng_seed != witness.rng_seed:
        raise RuntimeError(
            "bridge/RNG memory witness mismatch: "
            f"wire={request.rng_seed:#06x}, memory={witness.rng_seed:#06x}"
        )
    if not request.replay_target_stamped:
        raise RuntimeError("runtime did not stamp original replay target")
    return witness


__all__ = (
    "LockstepMemoryWitness",
    "validate_request_memory_witness",
)
