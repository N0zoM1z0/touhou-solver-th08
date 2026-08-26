"""Pointer-free TH08 effect/ANM lifecycle projection at one stable root.

The layout is source-authoritative from ``EffectManager`` and ``AnmVm``.
Allocator and code/data pointers are deliberately replaced by slot identity,
presence bits, and the pointed-to immutable ANM instruction bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import struct
from typing import Any


EFFECT_PROJECTION_SCHEMA = "th08-effect-anm-lifecycle-projection-v1"
EFFECT_MANAGER_BASE = 0x004ECE60
EFFECT_MANAGER_SIZE = 0x8B05C
EFFECT_MANAGER_CURSOR_OFFSET = 0x00
EFFECT_MANAGER_ACTIVE_COUNT_OFFSET = 0x08
EFFECT_MANAGER_SCALE_OFFSET = 0x0C
EFFECT_MANAGER_TIMER_OFFSET = 0x8B050
EFFECT_POOL_OFFSET = 0x1C
EFFECT_SLOT_COUNT = 653
EFFECT_SLOT_STRIDE = 0x360

ANM_CURRENT_TIME_OFFSET = 0x038
ANM_WAIT_TIMER_OFFSET = 0x044
ANM_FLAGS_OFFSET = 0x1F8
ANM_TYPE_OFFSET = 0x1FA
ANM_PENDING_INTERRUPT_OFFSET = 0x1FC
ANM_PLAYER_BULLET_HIT_ANIMATION_TYPE_OFFSET = 0x200
ANM_FILE_POINTER_OFFSET = 0x204
ANM_ACTIVE_SPRITE_INDEX_OFFSET = 0x214
ANM_FILE_INDEX_OFFSET = 0x216
ANM_BASE_SPRITE_INDEX_OFFSET = 0x218
ANM_SCRIPT_INDEX_OFFSET = 0x21A
ANM_BEGINNING_OF_SCRIPT_POINTER_OFFSET = 0x21C
ANM_CURRENT_INSTRUCTION_POINTER_OFFSET = 0x220
ANM_LOADED_SPRITE_POINTER_OFFSET = 0x224
ANM_INTERRUPT_RETURN_TIMER_OFFSET = 0x228
ANM_INTERRUPT_RETURN_INSTRUCTION_POINTER_OFFSET = 0x234
EFFECT_VECTOR_BLOCK_OFFSET = 0x2A4
EFFECT_VECTOR_FLOAT_COUNT = 9 * 3
EFFECT_TIMER_OFFSET = 0x338
EFFECT_UPDATE_CALLBACK_POINTER_OFFSET = 0x348
EFFECT_DRAW_CALLBACK_POINTER_OFFSET = 0x34C
EFFECT_ACTIVE_OFFSET = 0x350
EFFECT_ID_OFFSET = 0x351
EFFECT_CONTROL_BYTES_OFFSET = 0x352
EFFECT_CONTROL_BYTES_SIZE = 6
EFFECT_AUXILIARY_ALLOCATION_POINTER_OFFSET = 0x358
ANM_INSTRUCTION_HEADER_SIZE = 8
MAXIMUM_ANM_INSTRUCTION_SIZE = 0x400
MAXIMUM_ANM_SCRIPT_RELATIVE_OFFSET = 0x01000000


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def _timer_record(blob: bytes, offset: int) -> dict[str, int]:
    previous, fraction_bits, elapsed = struct.unpack_from("<iIi", blob, offset)
    return {
        "previous": previous,
        "fraction_bits": fraction_bits,
        "elapsed": elapsed,
    }


def _script_relative_offset(
    *,
    beginning_pointer: int,
    instruction_pointer: int,
    field: str,
) -> int | None:
    if instruction_pointer == 0:
        return None
    if beginning_pointer == 0:
        raise ValueError(f"active-effect {field} has no ANM script root")
    if instruction_pointer < beginning_pointer:
        raise ValueError(f"active-effect {field} precedes ANM script root")
    offset = instruction_pointer - beginning_pointer
    if offset > MAXIMUM_ANM_SCRIPT_RELATIVE_OFFSET:
        raise ValueError(f"active-effect {field} is implausibly far from root")
    return offset


def _instruction_record(
    reader: Any,
    pointer: int,
    *,
    beginning_pointer: int,
) -> dict[str, object] | None:
    if pointer == 0:
        return None
    header = reader.read(pointer, ANM_INSTRUCTION_HEADER_SIZE)
    if len(header) != ANM_INSTRUCTION_HEADER_SIZE:
        raise ValueError("short active-effect ANM instruction header")
    opcode, size, time_value, variable_mask = struct.unpack("<hHhH", header)
    if not ANM_INSTRUCTION_HEADER_SIZE <= size <= MAXIMUM_ANM_INSTRUCTION_SIZE:
        raise ValueError(f"invalid active-effect ANM instruction size {size}")
    payload_size = size - ANM_INSTRUCTION_HEADER_SIZE
    payload = (
        b""
        if payload_size == 0
        else reader.read(pointer + ANM_INSTRUCTION_HEADER_SIZE, payload_size)
    )
    if len(payload) != payload_size:
        raise ValueError("short active-effect ANM instruction payload")
    return {
        "script_relative_offset": _script_relative_offset(
            beginning_pointer=beginning_pointer,
            instruction_pointer=pointer,
            field="current instruction",
        ),
        "opcode": opcode,
        "size": size,
        "time": time_value,
        "variable_mask": variable_mask,
        "payload_hex": payload.hex(),
    }


@dataclass(frozen=True, slots=True)
class EffectLifecycleProjection:
    payload: dict[str, object]
    sha256: str

    def record(self, *, include_payload: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": EFFECT_PROJECTION_SCHEMA,
            "sha256": self.sha256,
            "summary": {
                "active_effect_count": len(self.payload["rows"]),
                "reported_active_count": self.payload[
                    "reported_active_count"
                ],
                "active_effect_ids": self.payload["active_effect_ids"],
            },
            "authority": (
                "effect_allocator_anm_lifecycle_and_callback_presence_only"
            ),
        }
        if include_payload:
            record["payload"] = self.payload
        return record


def capture_effect_lifecycle_projection(reader: Any) -> EffectLifecycleProjection:
    """Capture the complete source-scanned effect pool without raw artifacts."""

    blob = reader.read(EFFECT_MANAGER_BASE, EFFECT_MANAGER_SIZE)
    if len(blob) != EFFECT_MANAGER_SIZE:
        raise ValueError("short TH08 effect-manager read")
    rows: list[dict[str, object]] = []
    counts: dict[int, int] = {}
    for slot in range(EFFECT_SLOT_COUNT):
        base = EFFECT_POOL_OFFSET + slot * EFFECT_SLOT_STRIDE
        active = blob[base + EFFECT_ACTIVE_OFFSET]
        if active == 0:
            continue
        effect_id = blob[base + EFFECT_ID_OFFSET]
        counts[effect_id] = counts.get(effect_id, 0) + 1
        current_instruction_pointer = struct.unpack_from(
            "<I",
            blob,
            base + ANM_CURRENT_INSTRUCTION_POINTER_OFFSET,
        )[0]
        beginning_of_script_pointer = struct.unpack_from(
            "<I",
            blob,
            base + ANM_BEGINNING_OF_SCRIPT_POINTER_OFFSET,
        )[0]
        interrupt_return_instruction_pointer = struct.unpack_from(
            "<I",
            blob,
            base + ANM_INTERRUPT_RETURN_INSTRUCTION_POINTER_OFFSET,
        )[0]
        rows.append(
            {
                "slot": slot,
                "active": active,
                "effect_id": effect_id,
                "control_bytes_hex": bytes(
                    blob[
                        base + EFFECT_CONTROL_BYTES_OFFSET :
                        base
                        + EFFECT_CONTROL_BYTES_OFFSET
                        + EFFECT_CONTROL_BYTES_SIZE
                    ]
                ).hex(),
                "update_callback_installed": bool(
                    struct.unpack_from(
                        "<I",
                        blob,
                        base + EFFECT_UPDATE_CALLBACK_POINTER_OFFSET,
                    )[0]
                ),
                "draw_callback_installed": bool(
                    struct.unpack_from(
                        "<I",
                        blob,
                        base + EFFECT_DRAW_CALLBACK_POINTER_OFFSET,
                    )[0]
                ),
                "allocated_auxiliary_present": bool(
                    struct.unpack_from(
                        "<I",
                        blob,
                        base + EFFECT_AUXILIARY_ALLOCATION_POINTER_OFFSET,
                    )[0]
                ),
                "effect_timer": _timer_record(
                    blob,
                    base + EFFECT_TIMER_OFFSET,
                ),
                "anm": {
                    "flags": struct.unpack_from(
                        "<H", blob, base + ANM_FLAGS_OFFSET
                    )[0],
                    "type": struct.unpack_from(
                        "<h", blob, base + ANM_TYPE_OFFSET
                    )[0],
                    "pending_interrupt": struct.unpack_from(
                        "<h", blob, base + ANM_PENDING_INTERRUPT_OFFSET
                    )[0],
                    "player_bullet_hit_animation_type": struct.unpack_from(
                        "<i",
                        blob,
                        base + ANM_PLAYER_BULLET_HIT_ANIMATION_TYPE_OFFSET,
                    )[0],
                    "anm_file_installed": bool(
                        struct.unpack_from(
                            "<I", blob, base + ANM_FILE_POINTER_OFFSET
                        )[0]
                    ),
                    "active_sprite_index": struct.unpack_from(
                        "<h", blob, base + ANM_ACTIVE_SPRITE_INDEX_OFFSET
                    )[0],
                    "anm_file_index": struct.unpack_from(
                        "<h", blob, base + ANM_FILE_INDEX_OFFSET
                    )[0],
                    "base_sprite_index": struct.unpack_from(
                        "<h", blob, base + ANM_BASE_SPRITE_INDEX_OFFSET
                    )[0],
                    "script_index": struct.unpack_from(
                        "<h", blob, base + ANM_SCRIPT_INDEX_OFFSET
                    )[0],
                    "loaded_sprite_present": bool(
                        struct.unpack_from(
                            "<I", blob, base + ANM_LOADED_SPRITE_POINTER_OFFSET
                        )[0]
                    ),
                    "current_time": _timer_record(
                        blob,
                        base + ANM_CURRENT_TIME_OFFSET,
                    ),
                    "wait_timer": _timer_record(
                        blob,
                        base + ANM_WAIT_TIMER_OFFSET,
                    ),
                    "interrupt_return_timer": _timer_record(
                        blob,
                        base + ANM_INTERRUPT_RETURN_TIMER_OFFSET,
                    ),
                    "interrupt_return_instruction_offset": (
                        _script_relative_offset(
                            beginning_pointer=beginning_of_script_pointer,
                            instruction_pointer=(
                                interrupt_return_instruction_pointer
                            ),
                            field="interrupt return instruction",
                        )
                    ),
                    "current_instruction": _instruction_record(
                        reader,
                        current_instruction_pointer,
                        beginning_pointer=beginning_of_script_pointer,
                    ),
                },
                "vector_bits": list(
                    struct.unpack_from(
                        f"<{EFFECT_VECTOR_FLOAT_COUNT}I",
                        blob,
                        base + EFFECT_VECTOR_BLOCK_OFFSET,
                    )
                ),
            }
        )
    active_effect_ids = [
        {"effect_id": effect_id, "count": counts[effect_id]}
        for effect_id in sorted(counts)
    ]
    payload: dict[str, object] = {
        "schema": EFFECT_PROJECTION_SCHEMA,
        "allocator_cursor": struct.unpack_from(
            "<i", blob, EFFECT_MANAGER_CURSOR_OFFSET
        )[0],
        "reported_active_count": struct.unpack_from(
            "<i", blob, EFFECT_MANAGER_ACTIVE_COUNT_OFFSET
        )[0],
        "scale_bits": list(
            struct.unpack_from("<4I", blob, EFFECT_MANAGER_SCALE_OFFSET)
        ),
        "manager_timer": struct.unpack_from(
            "<i", blob, EFFECT_MANAGER_TIMER_OFFSET
        )[0],
        "active_effect_ids": active_effect_ids,
        "rows": rows,
        "pointer_exclusions": [
            "effect_update_and_draw_callback_addresses_replaced_by_presence",
            "anm_file_and_instruction_addresses_replaced_by_script_and_bytes",
            "loaded_sprite_address_replaced_by_presence",
            "effect_auxiliary_allocation_address_replaced_by_presence",
            "effect_heap_and_draw_list_links_excluded",
        ],
    }
    return EffectLifecycleProjection(
        payload=payload,
        sha256=_canonical_digest(payload),
    )


__all__ = (
    "EFFECT_MANAGER_BASE",
    "EFFECT_MANAGER_SIZE",
    "EFFECT_PROJECTION_SCHEMA",
    "EFFECT_SLOT_COUNT",
    "EFFECT_SLOT_STRIDE",
    "EffectLifecycleProjection",
    "capture_effect_lifecycle_projection",
)
