"""Coherent native root for ordinary future-source closure."""

from __future__ import annotations

import hashlib
import math
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from th08_ecl_tool.core import EclFile
from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_runtime.game_state import (
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_FRSCREEN_UPDATE_SERIAL,
)
from th08_runtime.native_combat_projection import (
    capture_player_shot_combat_state,
)
from th08_runtime.native_snapshot_projection import (
    COLLISION_CONTROL_PROJECTION_SCHEMA,
    _bullet_template_geometry_record,
    _enemy_source_record,
    _timeline_runtime_inventory_record,
)
from th08_runtime.sensing import observe_state
from th08_runtime.route2_sht_provenance import (
    LoadedRoute2ShtState,
    capture_loaded_route2_sht_state,
)
from th08_ordinary_future_sources import (
    OrdinaryFutureSourceClosure,
    project_ordinary_future_sources,
)
from th08_runtime.future_source_retention import (
    FutureSourceRetentionExpectation,
    RetainedFutureSourceRoot,
    future_source_retention_rejection_reason,
    write_retained_future_source_root,
)


ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA = (
    "th08-ordinary-future-source-snapshot-v2-player-enemy-clock-bracket"
)
ROUTE2_HEALTH_DAMAGE_ENVELOPE_SCHEMA = (
    "th08-route2-normal-shot-health-transition-damage-envelope-v1"
)
_SHOT_MASK = 0x01
_SHOT_CADENCE_LENGTH = 20


@dataclass(frozen=True)
class OrdinaryFutureSourceSnapshot:
    frame_before: int
    frame_after: int
    update_serial_before: int
    update_serial_after: int
    payload: dict[str, object]
    read_ms: float
    attempts: int

    @property
    def stable(self) -> bool:
        return (
            self.frame_before == self.frame_after
            and self.update_serial_before == self.update_serial_after
        )


@dataclass(frozen=True)
class OrdinaryFutureSourceCaptureResult:
    snapshot: OrdinaryFutureSourceSnapshot
    closure: OrdinaryFutureSourceClosure
    retained_root: RetainedFutureSourceRoot | None = None
    retention_rejection_reason: str | None = None


_CAPTURE_BUFFERS = threading.local()


def _normal_future_damage_by_cadence_phase(
    loaded: LoadedRoute2ShtState,
    *,
    minimum_level: int = 0,
) -> tuple[int, ...]:
    """Return the greatest raw normal-shot emission at each cadence phase.

    Taking the maximum over both exactly loaded Route-2 profiles and every
    selector-reachable level at or above ``minimum_level`` covers every future
    focus choice and Power increase.  Levels below the exact root selection
    are unreachable on the survival branches for which global viability is
    queried: normal play has no Power decay, and a hit terminates that branch.
    """

    if minimum_level < 0:
        raise ValueError("minimum normal SHT level cannot be negative")
    level_records: dict[tuple[str, int], list[object]] = {}
    for record in loaded.records_by_pointer.values():
        if (
            not record.normal_selector_reachable
            or record.level < minimum_level
        ):
            continue
        if (
            record.fire_period <= 0
            or record.fire_phase < 0
            or record.damage < 0
            or record.shot_type != 0
            or record.callback_indices[0] not in (0, 7)
            or any(record.callback_indices[index] for index in (1, 2, 3))
        ):
            raise ValueError(
                "loaded Route-2 normal SHT is outside the nonpiercing "
                "default damage envelope"
            )
        level_records.setdefault((record.profile, record.level), []).append(
            record
        )
    if not level_records:
        raise ValueError("loaded Route-2 SHT has no normal shot levels")
    result: list[int] = []
    for cadence in range(_SHOT_CADENCE_LENGTH):
        result.append(
            max(
                sum(
                    record.damage
                    for record in records
                    if cadence % record.fire_period == record.fire_phase
                )
                for records in level_records.values()
            )
        )
    return tuple(result)


def _route2_health_damage_envelope_record(
    reader: Any,
    state: dict[str, object],
) -> dict[str, object]:
    """Capture a hard upper envelope for health-transition reachability."""

    loaded = capture_loaded_route2_sht_state(reader)
    shots = capture_player_shot_combat_state(reader)
    resources = state.get("resources")
    power = (
        float(resources["power"])
        if isinstance(resources, dict) and "power" in resources
        else math.nan
    )
    native_power = math.trunc(power) if math.isfinite(power) else -1
    current_normal_level = next(
        (
            level
            for level, upper_bound in enumerate(
                loaded.primary.spec.power_upper_bounds[
                    : loaded.primary.spec.normal_level_count
                ]
            )
            if native_power < upper_bound
        ),
        -1,
    )
    cadence_damage = (
        _normal_future_damage_by_cadence_phase(
            loaded,
            minimum_level=current_normal_level,
        )
        if current_normal_level >= 0
        else (0,) * _SHOT_CADENCE_LENGTH
    )
    incompatible_slots: list[int] = []
    active_raw_damage = 0
    for shot in shots.slots:
        provenance = loaded.provenance_for_pointer(
            shot.source_record_pointer
        )
        if (
            provenance is None
            or not provenance.normal_selector_reachable
            or not shot.route2_normal_damage_path_compatible
        ):
            incompatible_slots.append(shot.slot)
            continue
        active_raw_damage += shot.damage

    player = state["player"]
    spell = state["spell"]
    assert isinstance(player, dict)
    assert isinstance(spell, dict)
    input_raw = int(state["input_raw"])
    input_current = int(state["input_current"])
    root_conditions = {
        "route_id_2": int(state["route_id"]) == 2,
        "ordinary_player_phase_0": int(player["phase"]) == 0,
        "bomb_inactive": int(player["bomb_active"]) == 0,
        "spell_inactive": not bool(spell["active"]),
        "shot_held_in_raw_and_active_input": bool(
            input_raw & _SHOT_MASK and input_current & _SHOT_MASK
        ),
        "all_active_shots_are_exact_route2_normal_nonpiercing": not (
            incompatible_slots
        ),
        "finite_nonnegative_power_selects_normal_sht_level": bool(
            math.isfinite(power)
            and power >= 0.0
            and current_normal_level >= 0
        ),
        "active_shot_cadence_timer_is_in_cycle": bool(
            0 <= shots.emission_timer.current < _SHOT_CADENCE_LENGTH
        ),
    }
    return {
        "schema": ROUTE2_HEALTH_DAMAGE_ENVELOPE_SCHEMA,
        "complete": all(root_conditions.values()),
        "root_conditions": root_conditions,
        "input": {
            "raw": input_raw,
            "current": input_current,
            "previous": int(state["input_previous"]),
        },
        "active_shot_count": len(shots.slots),
        "active_incompatible_slots": incompatible_slots,
        "active_raw_damage_upper_bound": active_raw_damage,
        "root_power": power if math.isfinite(power) else None,
        "root_native_power": native_power,
        "minimum_future_normal_sht_level": current_normal_level,
        "future_raw_damage_by_cadence_phase": list(cadence_damage),
        "future_cadence_phase_support": [shots.emission_timer.current],
        "root_emission_timer": shots.emission_timer.record(),
        "cadence_length": _SHOT_CADENCE_LENGTH,
        "loaded_sht_normalized_sha256": {
            "primary": loaded.primary.normalized_sha256,
            "secondary": loaded.secondary.normalized_sha256,
        },
        "player_damage_bonus_upper_ratio": [106, 100],
        "authority": (
            "health_transition_unreachability_only_while_every_causal_"
            "pipeline_and_branch_mask_continues_to_hold_shot_and_survival_"
            "branches_preserve_the_native_non_decreasing_power_level"
        ),
    }


def _persistent_enemy_slab_buffer(reader: Any) -> Any | None:
    """Return one worker-local RPM destination when the reader supports it.

    ``ProcessReader.read`` allocates and zeroes a ctypes destination, copies
    the remote slab into it, then copies it again through ``buffer.raw``.
    Future-source capture runs on one dedicated worker, so retaining the
    destination there removes both observer-only operations from the native
    manager-frame bracket without sharing mutable storage across workers.
    """

    allocate_buffer = getattr(reader, "allocate_buffer", None)
    read_into = getattr(reader, "read_into", None)
    if not callable(allocate_buffer) or not callable(read_into):
        return None
    expected_size = (ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE
    buffer = getattr(_CAPTURE_BUFFERS, "enemy_slab", None)
    if buffer is None or len(buffer) != expected_size:
        buffer = allocate_buffer(expected_size)
        _CAPTURE_BUFFERS.enemy_slab = buffer
    return buffer


def _unsigned_byte_view(data: Any) -> memoryview:
    view = memoryview(data)
    if view.ndim == 1 and view.format == "B":
        return view
    return view.cast("B")


def _read_active_enemy_records(
    reader: Any,
    *,
    slab_buffer: Any | None = None,
) -> tuple[memoryview, memoryview, int]:
    # The manager singleton is immediately before the ordinary pool.  Capture
    # both in one ReadProcessMemory transaction: the former sparse scan made
    # at least 481 cross-process calls, and retained physical traces showed
    # that 1,726/1,754 roots crossed enemy_manager_frame before closure could
    # even be attempted.  One contiguous image is larger (~9.8 MiB) but is a
    # single versioned native observation and retains every slot coordinate.
    expected_size = (ENEMY_POOL_SIZE + 1) * ENEMY_STRIDE
    if slab_buffer is None:
        slab = _unsigned_byte_view(
            reader.read(
                ENEMY_MANAGER_TEMPLATE_BASE,
                expected_size,
            )
        )
    else:
        reader.read_into(ENEMY_MANAGER_TEMPLATE_BASE, slab_buffer)
        slab = _unsigned_byte_view(slab_buffer)
    if len(slab) != expected_size:
        raise ValueError("ordinary future-source enemy slab is truncated")
    manager_blob = slab[:ENEMY_STRIDE]
    ordinary_blob = slab[ENEMY_STRIDE:]
    active_record_count = int(
        bool(
            struct.unpack_from(
                "<I",
                manager_blob,
                ENEMY_FLAGS_OFFSET,
            )[0]
            & ENEMY_ACTIVE_FLAG
        )
    )
    for slot in range(ENEMY_POOL_SIZE):
        base = slot * ENEMY_STRIDE
        flags = struct.unpack_from(
            "<I",
            ordinary_blob,
            base + ENEMY_FLAGS_OFFSET,
        )[0]
        active_record_count += int(bool(flags & ENEMY_ACTIVE_FLAG))
    return manager_blob, ordinary_blob, active_record_count


def _canonical_runtime_ecl_sha256(
    reader: Any,
    timeline_runtime: dict[str, object],
) -> str:
    ecl_file = timeline_runtime["ecl_file"]
    assert isinstance(ecl_file, dict)
    file_base = int(ecl_file["file_base"])
    size = int(ecl_file["static_data_end_offset"])
    subroutine_count = int(ecl_file["subroutine_count"])
    if size < 0x48 + subroutine_count * 4:
        raise ValueError("runtime ECL image is shorter than its pointer tables")
    canonical = bytearray(reader.read(file_base, size))
    if len(canonical) != size:
        raise ValueError("runtime ECL image read is truncated")
    # ecl_load_file relocates the 16 timeline/data-end slots and every
    # subroutine-table entry in place.  Undo only those documented pointer
    # tables; instruction bytes remain the shipped file bytes.
    for offset in range(0x08, 0x48, 4):
        pointer = struct.unpack_from("<I", canonical, offset)[0]
        if pointer:
            if not file_base <= pointer <= file_base + size:
                raise ValueError("runtime ECL timeline pointer is out of range")
            struct.pack_into("<I", canonical, offset, pointer - file_base)
    for index in range(subroutine_count):
        offset = 0x48 + index * 4
        pointer = struct.unpack_from("<I", canonical, offset)[0]
        if not file_base <= pointer < file_base + size:
            raise ValueError("runtime ECL subroutine pointer is out of range")
        struct.pack_into("<I", canonical, offset, pointer - file_base)
    return hashlib.sha256(canonical).hexdigest()


def _compact_state(state: dict[str, object]) -> dict[str, object]:
    player = state["player"]
    spell = state["spell"]
    assert isinstance(player, dict)
    assert isinstance(spell, dict)
    return {
        "manager_frame": int(state["enemy_manager_frame"]),
        "time_scale_bits": int(state["time_scale_bits"]),
        "rng_state": int(state["rng_state"]),
        "rng_calls": int(state["rng_calls"]),
        "player_x": float(player["x"]),
        "player_y": float(player["y"]),
        "player_phase": int(player["phase"]),
        "predeath_counter": int(player["predeath_counter"]),
        "route_id": int(state["route_id"]),
        "difficulty_index": int(state["difficulty_index"]),
        "stage_route_index": int(state["stage_route_index"]),
        "input_raw": int(state["input_raw"]),
        "input_current": int(state["input_current"]),
        "input_previous": int(state["input_previous"]),
        "bomb_active": int(player["bomb_active"]),
        "spell_id": (
            int(spell["spell_id"]) if bool(spell["active"]) else None
        ),
    }


def _payload(
    reader: Any,
    *,
    manager_blob: bytes | memoryview,
    ordinary_blob: bytes | memoryview,
    state: dict[str, object],
) -> dict[str, object]:
    manager = _enemy_source_record(
        reader,
        enemy_blob=manager_blob,
        pool_base=ENEMY_MANAGER_TEMPLATE_BASE,
        pool_size=1,
        source_role="enemy_manager_template_or_special_singleton",
    )
    ordinary = _enemy_source_record(
        reader,
        enemy_blob=ordinary_blob,
        pool_base=ENEMY_POOL_BASE,
        pool_size=ENEMY_POOL_SIZE,
        source_role="ordinary_enemy_pool",
    )
    timeline = _timeline_runtime_inventory_record(reader)
    ecl_file = timeline["ecl_file"]
    assert isinstance(ecl_file, dict)
    ecl_file["canonical_sha256"] = _canonical_runtime_ecl_sha256(
        reader,
        timeline,
    )
    return {
        "schema": COLLISION_CONTROL_PROJECTION_SCHEMA,
        "compact_state": _compact_state(state),
        "route2_health_transition_damage_envelope": (
            _route2_health_damage_envelope_record(reader, state)
        ),
        "enemy_manager_template_source": manager,
        "enemy_bodies": ordinary["enemy_bodies"],
        "enemy_main_ecl_vm_inventory": ordinary[
            "main_ecl_vm_inventory"
        ],
        "enemy_main_ecl_installed_callbacks": ordinary[
            "main_ecl_installed_callbacks"
        ],
        "enemy_periodic_emission_state": ordinary[
            "periodic_emission_state"
        ],
        "enemy_emission_state": ordinary["emission_state"],
        "enemy_motion_state": ordinary["motion_state"],
        "enemy_phase_transition_state": ordinary[
            "phase_transition_state"
        ],
        "enemy_auxiliary_ecl_contexts": ordinary[
            "auxiliary_ecl_contexts"
        ],
        "bullet_template_geometry": _bullet_template_geometry_record(reader),
        "stage_timeline_runtime": timeline,
    }


def capture_ordinary_future_source_snapshot(
    reader: Any,
    *,
    maximum_attempts: int = 2,
) -> OrdinaryFutureSourceSnapshot:
    """Capture one complete future-source root under a manager-frame bracket."""

    if maximum_attempts <= 0:
        raise ValueError("future-source capture attempts must be positive")
    started = time.perf_counter()
    # Allocate the reusable 9.8 MiB destination before the native clock
    # bracket. Allocation/zeroing is observer work and is not part of the
    # source observation.
    enemy_slab_buffer = _persistent_enemy_slab_buffer(reader)
    snapshot: OrdinaryFutureSourceSnapshot | None = None
    for attempt in range(1, maximum_attempts + 1):
        update_serial_before = reader.u32(ADDR_FRSCREEN_UPDATE_SERIAL)
        frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        manager_blob, ordinary_blob, _active_count = (
            _read_active_enemy_records(
                reader,
                slab_buffer=enemy_slab_buffer,
            )
        )
        state = observe_state(reader)
        payload = _payload(
            reader,
            manager_blob=manager_blob,
            ordinary_blob=ordinary_blob,
            state=state,
        )
        frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        update_serial_after = reader.u32(ADDR_FRSCREEN_UPDATE_SERIAL)
        snapshot = OrdinaryFutureSourceSnapshot(
            frame_before=frame_before,
            frame_after=frame_after,
            update_serial_before=update_serial_before,
            update_serial_after=update_serial_after,
            payload=payload,
            read_ms=(time.perf_counter() - started) * 1000.0,
            attempts=attempt,
        )
        if (
            snapshot.stable
            and int(payload["compact_state"]["manager_frame"])
            == frame_before
        ):
            return snapshot
    assert snapshot is not None
    return snapshot


def capture_and_project_ordinary_future_sources(
    reader: Any,
    ecl: EclFile,
    *,
    horizon_frames: int,
    maximum_attempts: int = 2,
    retain_dir: Path | None = None,
    retention_expectation: FutureSourceRetentionExpectation | None = None,
) -> OrdinaryFutureSourceCaptureResult:
    if (retain_dir is None) != (retention_expectation is None):
        raise ValueError(
            "future-source retention directory and expectation must be paired"
        )
    snapshot = capture_ordinary_future_source_snapshot(
        reader,
        maximum_attempts=maximum_attempts,
    )
    if not snapshot.stable:
        raise RuntimeError(
            "ordinary future-source snapshot crossed native clock bracket: "
            f"manager={snapshot.frame_before}->{snapshot.frame_after}, "
            "frscreen_serial="
            f"{snapshot.update_serial_before}->{snapshot.update_serial_after}"
        )
    closure = project_ordinary_future_sources(
        snapshot.payload,
        ecl,
        horizon_frames=horizon_frames,
    )
    retention_rejection_reason = (
        future_source_retention_rejection_reason(
            snapshot,
            retention_expectation,
        )
        if retention_expectation is not None
        else None
    )
    retained_root = (
        write_retained_future_source_root(
            snapshot,
            closure,
            retain_dir,
            snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
            requested_horizon_frames=horizon_frames,
        )
        if retain_dir is not None and retention_rejection_reason is None
        else None
    )
    return OrdinaryFutureSourceCaptureResult(
        snapshot=snapshot,
        closure=closure,
        retained_root=retained_root,
        retention_rejection_reason=retention_rejection_reason,
    )


__all__ = [
    "ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA",
    "OrdinaryFutureSourceSnapshot",
    "OrdinaryFutureSourceCaptureResult",
    "capture_and_project_ordinary_future_sources",
    "capture_ordinary_future_source_snapshot",
]
