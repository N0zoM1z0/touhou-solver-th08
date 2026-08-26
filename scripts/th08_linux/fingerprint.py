"""Pointer-free semantic spine for cross-runtime replay differentials."""

from __future__ import annotations

from dataclasses import dataclass
import json
import struct
from typing import Mapping, Protocol

from th08_linux.protocol import InputRequest
from th08_linux.semantic_trace import semantic_trace_record
from th08_linux.witness import (
    LockstepMemoryWitness,
    capture_memory_witness,
    validate_request_memory_witness,
)
from th08_runtime.sensing import observe_state


ADDR_REPLAY_MANAGER_POINTER = 0x018B8A28
REPLAY_FRAME_COUNTER_OFFSET = 0x00
REPLAY_INPUT_DELAY_OFFSET = 0x04
REPLAY_IS_DEMO_OFFSET = 0x10
REPLAY_RNG_SEED_OFFSET = 0xD8
REPLAY_FLAGS_OFFSET = 0xDA


class FingerprintStateReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...

    def u8(self, address: int) -> int: ...

    def u16(self, address: int) -> int: ...

    def u32(self, address: int) -> int: ...

    def i32(self, address: int) -> int: ...

    def f32(self, address: int) -> float: ...


@dataclass(frozen=True, slots=True)
class ReplayClockSnapshot:
    frame_counter: int
    input_delay: int
    is_demo: int
    rng_seed: int
    flags: int


def _f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def capture_replay_clock(
    reader: FingerprintStateReader,
) -> ReplayClockSnapshot | None:
    root = reader.u32(ADDR_REPLAY_MANAGER_POINTER)
    if root == 0:
        return None
    snapshot = ReplayClockSnapshot(
        frame_counter=reader.i32(root + REPLAY_FRAME_COUNTER_OFFSET),
        input_delay=reader.i32(root + REPLAY_INPUT_DELAY_OFFSET),
        is_demo=reader.i32(root + REPLAY_IS_DEMO_OFFSET),
        rng_seed=reader.u16(root + REPLAY_RNG_SEED_OFFSET),
        flags=reader.u16(root + REPLAY_FLAGS_OFFSET),
    )
    if reader.u32(ADDR_REPLAY_MANAGER_POINTER) != root:
        raise RuntimeError("replay-manager root changed during one fingerprint")
    return snapshot


def semantic_spine_from_observation(
    *,
    witness: LockstepMemoryWitness,
    state: dict[str, object],
    replay_clock: ReplayClockSnapshot | None,
    relative_epoch: int,
    rng_calls_origin: int | None = None,
    trace_locators: Mapping[str, int] | None = None,
) -> dict[str, object]:
    player = state["player"]
    spell = state["spell"]
    resources = state["resources"]
    assert isinstance(player, dict)
    assert isinstance(spell, dict)
    assert resources is None or isinstance(resources, dict)
    rng_calls_absolute = int(state["rng_calls"])
    if rng_calls_origin is None:
        rng_calls_origin = rng_calls_absolute
    locators = dict(trace_locators or {})
    if "rng_calls_absolute" in locators:
        raise ValueError("RNG-call locator is captured from runtime state")
    locators["rng_calls_absolute"] = rng_calls_absolute
    return {
        "schema": "th08-semantic-spine-v3",
        "relative_epoch": relative_epoch,
        # The legacy replay path calls Rng::SetSeed without resetting the
        # generation counter and does not register OnUpdateLowPrio.  Async
        # setup can therefore leave a variable absolute prefix even when the
        # replay RNG trajectory is identical.  Retain that prefix only as a
        # trace locator and compare the modulo-u32 distance from sample start.
        "trace_locators": locators,
        "manager_frame": state["enemy_manager_frame"],
        "difficulty_index": state["difficulty_index"],
        "shot_type_index": state["route_id"],
        "stage_index": state["stage_route_index"],
        "game_manager_flags": state["engine_flags"],
        "gameplay_active": state["gameplay_active"],
        "time_scale_bits": state["time_scale_bits"],
        "input": {
            "supervisor_current": witness.supervisor_current_input,
            "supervisor_previous": witness.supervisor_previous_input,
            "gui_current": state["input_current"],
            "gui_previous": state["input_previous"],
        },
        "rng": {
            "seed": witness.rng_seed,
            "calls_since_trace_start": (
                rng_calls_absolute - rng_calls_origin
            )
            & 0xFFFFFFFF,
        },
        "player": {
            "phase": player["phase"],
            "focus_logic": player["focus_logic"],
            "deathbomb": player["deathbomb"],
            "secondary_character_active": player[
                "secondary_character_active"
            ],
            "forced_bomb": player["forced_bomb"],
            "focus_transition_counter": player[
                "focus_transition_counter"
            ],
            "x_bits": _f32_bits(float(player["x"])),
            "y_bits": _f32_bits(float(player["y"])),
            "bomb_active": player["bomb_active"],
            "bomb_index": player["bomb_index"],
            "bomb_timer": player["bomb_timer"],
            "predeath_counter": player["predeath_counter"],
            "bomb_lockout": player["bomb_lockout"],
        },
        "resources": (
            None
            if resources is None
            else {
                "lives_bits": _f32_bits(float(resources["lives"])),
                "bombs_bits": _f32_bits(float(resources["bombs"])),
                "power_bits": _f32_bits(float(resources["power"])),
            }
        ),
        "spell": {
            "active": spell["active"],
            "flags": spell["flags"],
            "spell_id": spell["spell_id"],
            "name": spell["name"],
            "timer_elapsed": spell["timer_elapsed"],
        },
        "replay": (
            None
            if replay_clock is None
            else {
                "frame_counter": replay_clock.frame_counter,
                "input_delay": replay_clock.input_delay,
                "is_demo": replay_clock.is_demo,
                "rng_seed": replay_clock.rng_seed,
                "flags": replay_clock.flags,
            }
        ),
    }


def capture_semantic_spine(
    reader: FingerprintStateReader,
    request: InputRequest,
    *,
    relative_epoch: int,
    rng_calls_origin: int | None = None,
) -> dict[str, object]:
    witness = validate_request_memory_witness(request, reader)
    state = observe_state(reader)
    replay_clock = capture_replay_clock(reader)
    return semantic_spine_from_observation(
        witness=witness,
        state=state,
        replay_clock=replay_clock,
        relative_epoch=relative_epoch,
        rng_calls_origin=rng_calls_origin,
        trace_locators={"bridge_epoch": request.epoch},
    )


def capture_runtime_semantic_spine(
    reader: FingerprintStateReader,
    *,
    relative_epoch: int,
    rng_calls_origin: int | None = None,
    trace_locators: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Capture at a caller-proven stable runtime boundary without a wire."""

    return semantic_spine_from_observation(
        witness=capture_memory_witness(reader),
        state=observe_state(reader),
        replay_clock=capture_replay_clock(reader),
        relative_epoch=relative_epoch,
        rng_calls_origin=rng_calls_origin,
        trace_locators=trace_locators,
    )


def canonical_fingerprint_bytes(fingerprint: dict[str, object]) -> bytes:
    # Absolute bridge epochs and the legacy replay's pre-sample RNG-call prefix
    # are locators, not replay semantics.  Relative replay epoch, relative RNG
    # calls, and all game clocks remain in the canonical body.
    semantic = semantic_trace_record(fingerprint)
    return json.dumps(
        semantic,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "ReplayClockSnapshot",
    "canonical_fingerprint_bytes",
    "capture_replay_clock",
    "capture_runtime_semantic_spine",
    "capture_semantic_spine",
    "semantic_spine_from_observation",
)
