"""Default-off complete-source trace gate for TH08 time-scale schedules.

This module never issues input and does not itself publish a schedule to live
action authority.  It binds one exact shipped runtime ECL image, captures the
manager singleton, full 480-slot ordinary-enemy pool, and any other
out-of-pool spell owner in one stable phase transaction, inventories installed
callbacks and auxiliary contexts, and runs the causal scale producer only
when the deliberately narrow Final-B spell-190 source contract is complete.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import struct
import time
from typing import Callable, Protocol

from th08_ecl_callback_model import CALLBACK_ADDRESSES
from th08_ecl_runtime import (
    ECL_VM_SNAPSHOT_SIZE,
    ECL_VM_TIMER_ELAPSED_OFFSET,
    ECL_VM_TIMER_FRACTION_OFFSET,
    ENEMY_MAIN_ECL_VM_OFFSET,
    EclVmSnapshot,
)
from th08_ecl_scale_schedule import (
    CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE,
    CALLBACK_SET_TIME_SCALE_RECIPROCAL,
    CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
    EclScaleEnvironment,
    EclScaleScheduleResult,
    EclScaleSourceAuthority,
    synthesize_ecl_time_scale_schedule,
)
from th08_ecl_tool.core import parse_ecl
from th08_ecl_vm_state import EclVmLocalProjection
from th08_live.enemy_ecl_inventory import (
    ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
)
from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_live.runtime_ecl_image import (
    ECL_FILE_CONTEXT_ADDRESS,
    ECL_SUBROUTINE_TABLE_OFFSET,
    RuntimeEclImageCapture,
    RuntimeEclImageIdentity,
    capture_runtime_ecl_image,
    compare_runtime_ecl_image,
)
from th08_live.runtime_ecl_index import build_exact_runtime_instruction_index
from th08_runtime.game_state import (
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_ENGINE_FLAGS,
    ADDR_GAMEPLAY_TIME_SCALE,
    ADDR_PLAYER,
    ADDR_ROUTE_ID,
    ADDR_SPELL_CARD_STATE,
    ADDR_STAGE_ROUTE_INDEX,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_PREDEATH_COUNTER_OFFSET,
    SPELL_STATE_ACTIVE_FLAG,
    SPELL_STATE_CAPTURE_SIZE,
)
from th08_time_scale import (
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    Th08TimeScaleSchedule,
    validate_time_scale_bits,
)


FINAL_B_SCALE_SOURCE_TRACE_SCHEMA = "th08-finalb-scale-source-trace-v1"
FINAL_B_SCALE_SOURCE_TRACE_AUTHORITY = "trace_only_no_action_authority"
FINAL_B_STAGE_ROUTE_INDEX = 7
FINAL_B_SCALE_SPELL_IDS = (187, 188, 189, 190)
FINAL_B_SCALE_SPELL_ID = FINAL_B_SCALE_SPELL_IDS[3]
FINAL_B_SCALE_SUBROUTINE = 44
FINAL_B_SCALE_HORIZON_FRAMES = 300
FINAL_B_QUARTER_SCALE_BITS = 0x3E800000
FINAL_B_ECL_STATIC_SHA256 = (
    "20b35dca3820438f0b90ae44e3362a7af27d2fc1ac7ae5888c477dc1c89a3734"
)

ECL_VM_INSTALLED_CALLBACK_OFFSET = 0x10
ECL_VM_INSTALLED_CALLBACK_RECORD_OFFSET = 0x14
ENEMY_SCALE_SOURCE_READ_SIZE = (
    ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET + 16
)
MINIMUM_RUNTIME_ADDRESS = 0x00010000
MAXIMUM_RUNTIME_ADDRESS = 0x7FFFFFFF
_SCALE_CALLBACK_INDICES = frozenset(
    {
        CALLBACK_SET_TIME_SCALE_RECIPROCAL,
        CALLBACK_SLOWDOWN_AND_SCALE_BULLETS,
        CALLBACK_RESTORE_BULLETS_AND_TIME_SCALE,
    }
)
_SCALE_CALLBACK_ADDRESSES = frozenset(
    CALLBACK_ADDRESSES[index] for index in _SCALE_CALLBACK_INDICES
)


def final_b_scale_spell_id(difficulty_index: int) -> int:
    """Return the shipped Final-B terminal spell for one main difficulty.

    ``ecldata7.ecl`` contains the four difficulty records 187..190 in one
    shared spell root.  The scale transition itself is the all-difficulty
    subroutine 44, so difficulty selects only the active spell-card record.
    """

    if type(difficulty_index) is not int or not 0 <= difficulty_index < len(
        FINAL_B_SCALE_SPELL_IDS
    ):
        raise ValueError(
            "Final-B scale authority requires a main difficulty index 0..3"
        )
    return FINAL_B_SCALE_SPELL_IDS[difficulty_index]


class ScaleSourceReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...


def _read_exact(reader: ScaleSourceReader, address: int, size: int) -> bytes:
    blob = reader.read(address, size)
    if len(blob) != size:
        raise OSError(
            f"process read at {address:#x} returned {len(blob)} of {size} bytes"
        )
    return blob


def _u32(reader: ScaleSourceReader, address: int) -> int:
    return struct.unpack("<I", _read_exact(reader, address, 4))[0]


@dataclass(frozen=True, slots=True)
class ScaleSourcePhaseIdentity:
    route_id: int
    difficulty_index: int
    stage_route_index: int
    engine_flags: int
    spell_blob: bytes
    ecl_context: bytes
    scale_bits: int
    player_phase: int
    player_bomb_active: int
    player_predeath_counter: int

    @classmethod
    def capture(cls, reader: ScaleSourceReader) -> ScaleSourcePhaseIdentity:
        return cls(
            route_id=_read_exact(reader, ADDR_ROUTE_ID, 1)[0],
            difficulty_index=_u32(reader, ADDR_DIFFICULTY_INDEX),
            stage_route_index=_u32(reader, ADDR_STAGE_ROUTE_INDEX),
            engine_flags=_u32(reader, ADDR_ENGINE_FLAGS),
            spell_blob=_read_exact(
                reader,
                ADDR_SPELL_CARD_STATE,
                SPELL_STATE_CAPTURE_SIZE,
            ),
            ecl_context=_read_exact(reader, ECL_FILE_CONTEXT_ADDRESS, 8),
            scale_bits=_u32(reader, ADDR_GAMEPLAY_TIME_SCALE),
            player_phase=_read_exact(reader, ADDR_PLAYER, 1)[0],
            player_bomb_active=_u32(
                reader,
                ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET,
            ),
            player_predeath_counter=struct.unpack(
                "<i",
                _read_exact(
                    reader,
                    ADDR_PLAYER + PLAYER_PREDEATH_COUNTER_OFFSET,
                    4,
                ),
            )[0],
        )

    @property
    def spell_flags(self) -> int:
        return struct.unpack_from("<I", self.spell_blob)[0]

    @property
    def spell_enemy_pointer(self) -> int:
        return struct.unpack_from("<I", self.spell_blob, 4)[0]

    @property
    def spell_id(self) -> int:
        return struct.unpack_from("<I", self.spell_blob, 8)[0]

    @property
    def spell_timer_elapsed(self) -> int:
        return struct.unpack_from("<i", self.spell_blob, 0x110)[0]

    @property
    def spell_active(self) -> bool:
        return bool(self.spell_flags & SPELL_STATE_ACTIVE_FLAG)

    @property
    def gameplay_active(self) -> bool:
        return bool(self.engine_flags & 0x04)

    def compact_record(self) -> dict[str, object]:
        runtime_base, subroutine_table = struct.unpack(
            "<II",
            self.ecl_context,
        )
        return {
            "route_id": self.route_id,
            "difficulty_index": self.difficulty_index,
            "stage_route_index": self.stage_route_index,
            "engine_flags": self.engine_flags,
            "gameplay_active": self.gameplay_active,
            "spell_active": self.spell_active,
            "spell_flags": self.spell_flags,
            "spell_enemy_pointer": self.spell_enemy_pointer,
            "spell_id": self.spell_id,
            "spell_timer_elapsed": self.spell_timer_elapsed,
            "runtime_ecl_base": runtime_base,
            "runtime_ecl_subroutine_table": subroutine_table,
            "scale_bits": self.scale_bits,
            "player_phase": self.player_phase,
            "player_bomb_active": self.player_bomb_active,
            "player_predeath_counter": self.player_predeath_counter,
        }


@dataclass(frozen=True, slots=True)
class ScaleVmSource:
    role: str
    slot: int | None
    enemy_pointer: int
    enemy_flags: int
    installed_callback: int
    installed_callback_record: int
    auxiliary_context_pointers: tuple[int, int, int, int]
    snapshot: EclVmSnapshot | None
    invalid_reason: str | None

    @property
    def source_id(self) -> int:
        return self.enemy_pointer

    @property
    def installed_callback_index(self) -> int | None:
        if self.installed_callback == 0:
            return None
        try:
            return CALLBACK_ADDRESSES.index(self.installed_callback)
        except ValueError:
            return None

    def compact_record(self) -> dict[str, object]:
        snapshot = self.snapshot
        projection = (
            snapshot.local_projection if snapshot is not None else None
        )
        return {
            "role": self.role,
            "slot": self.slot,
            "enemy_pointer": self.enemy_pointer,
            "enemy_flags": self.enemy_flags,
            "installed_callback": self.installed_callback,
            "installed_callback_index": self.installed_callback_index,
            "installed_callback_record": self.installed_callback_record,
            "auxiliary_context_pointers": list(
                self.auxiliary_context_pointers
            ),
            "instruction_pointer": (
                snapshot.instruction_pointer
                if snapshot is not None
                else None
            ),
            "timer_fraction_bits": (
                snapshot.timer_fraction_bits
                if snapshot is not None
                else None
            ),
            "timer_elapsed": (
                snapshot.timer_elapsed if snapshot is not None else None
            ),
            "integer_locals": (
                list(projection.integer_locals)
                if projection is not None
                else None
            ),
            "float_local_bits": (
                list(projection.float_local_bits)
                if projection is not None
                else None
            ),
            "scratch_integers": (
                list(projection.scratch_integers)
                if projection is not None
                else None
            ),
            "invalid_reason": self.invalid_reason,
        }


def decode_scale_vm_source(
    record: bytes,
    *,
    role: str,
    slot: int | None,
    enemy_pointer: int,
    scale_bits: int,
    runtime_instruction_bounds: tuple[int, int] | None = None,
) -> ScaleVmSource:
    if len(record) < ENEMY_SCALE_SOURCE_READ_SIZE:
        raise ValueError("enemy scale-source record is truncated")
    if runtime_instruction_bounds is not None:
        lower, upper = runtime_instruction_bounds
        if not MINIMUM_RUNTIME_ADDRESS <= lower < upper <= 0x100000000:
            raise ValueError("runtime instruction bounds are invalid")
    enemy_flags = struct.unpack_from("<I", record, ENEMY_FLAGS_OFFSET)[0]
    vm = record[
        ENEMY_MAIN_ECL_VM_OFFSET :
        ENEMY_MAIN_ECL_VM_OFFSET + ECL_VM_SNAPSHOT_SIZE
    ]
    installed_callback, callback_record = struct.unpack_from(
        "<II",
        vm,
        ECL_VM_INSTALLED_CALLBACK_OFFSET,
    )
    auxiliary = struct.unpack_from(
        "<4I",
        record,
        ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
    )
    instruction_pointer = struct.unpack_from("<I", vm)[0]
    fraction = struct.unpack_from(
        "<f",
        vm,
        ECL_VM_TIMER_FRACTION_OFFSET,
    )[0]
    timer_elapsed = struct.unpack_from(
        "<i",
        vm,
        ECL_VM_TIMER_ELAPSED_OFFSET,
    )[0]
    instruction_pointer_valid = (
        runtime_instruction_bounds[0]
        <= instruction_pointer
        < runtime_instruction_bounds[1]
        if runtime_instruction_bounds is not None
        else (
            MINIMUM_RUNTIME_ADDRESS
            <= instruction_pointer
            <= MAXIMUM_RUNTIME_ADDRESS
        )
    )
    if not instruction_pointer_valid:
        snapshot = None
        invalid_reason = "main_vm_instruction_pointer_invalid"
    elif not math.isfinite(fraction):
        snapshot = None
        invalid_reason = "main_vm_timer_fraction_nonfinite"
    else:
        projection = EclVmLocalProjection.from_vm_bytes(vm)
        scale = struct.unpack("<f", struct.pack("<I", scale_bits))[0]
        snapshot = EclVmSnapshot(
            instruction_pointer=instruction_pointer,
            timer_fraction=fraction,
            timer_elapsed=timer_elapsed,
            tag_mask=projection.integer_locals[0] & 0xFFFFFFFF,
            callback_angle=(
                projection.float_value(10016)
                if projection.float_value(10016) is not None
                else 0.0
            ),
            callback_speed=(
                projection.float_value(10017)
                if projection.float_value(10017) is not None
                else 0.0
            ),
            time_scale=scale,
            local_projection=projection,
        )
        invalid_reason = None
    return ScaleVmSource(
        role=role,
        slot=slot,
        enemy_pointer=enemy_pointer,
        enemy_flags=enemy_flags,
        installed_callback=installed_callback,
        installed_callback_record=callback_record,
        auxiliary_context_pointers=auxiliary,
        snapshot=snapshot,
        invalid_reason=invalid_reason,
    )


@dataclass(frozen=True, slots=True)
class CompleteScaleSourceCapture:
    status: str
    attempts: int
    expected_manager_frame: int
    manager_frame_before: int
    manager_frame_after: int
    phase_before: ScaleSourcePhaseIdentity
    phase_after: ScaleSourcePhaseIdentity
    sources: tuple[ScaleVmSource, ...]
    manager_template_active: bool
    ordinary_active_slots: int
    spell_owner_in_ordinary_pool: bool
    spell_owner_in_manager_template: bool
    process_read_count: int
    process_read_bytes: int
    capture_ms: float

    @property
    def coherent(self) -> bool:
        return self.status == "coherent"

    def compact_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "coherent": self.coherent,
            "attempts": self.attempts,
            "expected_manager_frame": self.expected_manager_frame,
            "manager_frame_before": self.manager_frame_before,
            "manager_frame_after": self.manager_frame_after,
            "ordinary_pool_base": ENEMY_POOL_BASE,
            "ordinary_pool_slots_scanned": ENEMY_POOL_SIZE,
            "ordinary_pool_complete": True,
            "manager_template_scanned": True,
            "manager_template_active": self.manager_template_active,
            "ordinary_active_slots": self.ordinary_active_slots,
            "spell_owner_in_ordinary_pool": (
                self.spell_owner_in_ordinary_pool
            ),
            "spell_owner_in_manager_template": (
                self.spell_owner_in_manager_template
            ),
            "source_count": len(self.sources),
            "phase_before": self.phase_before.compact_record(),
            "phase_after": self.phase_after.compact_record(),
            "sources": [source.compact_record() for source in self.sources],
            "process_read_count": self.process_read_count,
            "process_read_bytes": self.process_read_bytes,
            "capture_ms": self.capture_ms,
        }


def _pointer_in_ordinary_pool(pointer: int) -> bool:
    offset = pointer - ENEMY_POOL_BASE
    return (
        0 <= offset < ENEMY_POOL_SIZE * ENEMY_STRIDE
        and offset % ENEMY_STRIDE == 0
    )


def capture_complete_scale_sources(
    reader: ScaleSourceReader,
    *,
    expected_manager_frame: int,
    runtime_instruction_bounds: tuple[int, int] | None = None,
    maximum_attempts: int = 3,
    clock: Callable[[], float] = time.perf_counter,
) -> CompleteScaleSourceCapture:
    """Capture all potential enemy VM sources without issuing input."""

    if expected_manager_frame < 0:
        raise ValueError("expected manager frame cannot be negative")
    if maximum_attempts <= 0:
        raise ValueError("scale-source capture attempts must be positive")
    if runtime_instruction_bounds is not None:
        lower, upper = runtime_instruction_bounds
        if not MINIMUM_RUNTIME_ADDRESS <= lower < upper <= 0x100000000:
            raise ValueError("runtime instruction bounds are invalid")
    started = clock()
    selected: CompleteScaleSourceCapture | None = None
    pool_read_size = ENEMY_POOL_SIZE * ENEMY_STRIDE
    allocate_buffer = getattr(reader, "allocate_buffer", None)
    read_into = getattr(reader, "read_into", None)
    pool_buffer = (
        allocate_buffer(pool_read_size)
        if callable(allocate_buffer) and callable(read_into)
        else None
    )
    for attempt in range(1, maximum_attempts + 1):
        read_count = 0
        read_bytes = 0

        def read(address: int, size: int) -> bytes:
            nonlocal read_count, read_bytes
            blob = _read_exact(reader, address, size)
            read_count += 1
            read_bytes += size
            return blob

        def read_pool() -> bytes | memoryview:
            nonlocal read_count, read_bytes
            if pool_buffer is None:
                return read(ENEMY_POOL_BASE, pool_read_size)
            assert callable(read_into)
            read_into(ENEMY_POOL_BASE, pool_buffer)
            read_count += 1
            read_bytes += pool_read_size
            return memoryview(pool_buffer).cast("B")

        manager_before = struct.unpack(
            "<I",
            read(ADDR_ENEMY_MANAGER_FRAME, 4),
        )[0]

        class _CountingReader:
            def read(self, address: int, size: int) -> bytes:
                return read(address, size)

        counting_reader = _CountingReader()
        phase_before = ScaleSourcePhaseIdentity.capture(counting_reader)
        pool = read_pool()
        manager_template = read(
            ENEMY_MANAGER_TEMPLATE_BASE,
            ENEMY_SCALE_SOURCE_READ_SIZE,
        )
        spell_pointer = phase_before.spell_enemy_pointer
        owner_in_pool = _pointer_in_ordinary_pool(spell_pointer)
        owner_in_manager_template = (
            spell_pointer == ENEMY_MANAGER_TEMPLATE_BASE
        )
        external_owner = (
            read(spell_pointer, ENEMY_SCALE_SOURCE_READ_SIZE)
            if (
                phase_before.spell_active
                and spell_pointer
                and not owner_in_pool
                and not owner_in_manager_template
            )
            else None
        )
        phase_after = ScaleSourcePhaseIdentity.capture(counting_reader)
        manager_after = struct.unpack(
            "<I",
            read(ADDR_ENEMY_MANAGER_FRAME, 4),
        )[0]

        sources: list[ScaleVmSource] = []
        manager_template_flags = struct.unpack_from(
            "<I",
            manager_template,
            ENEMY_FLAGS_OFFSET,
        )[0]
        manager_template_active = bool(
            manager_template_flags & ENEMY_ACTIVE_FLAG
        )
        if manager_template_active:
            sources.append(
                decode_scale_vm_source(
                    manager_template,
                    role="manager_template",
                    slot=None,
                    enemy_pointer=ENEMY_MANAGER_TEMPLATE_BASE,
                    scale_bits=phase_before.scale_bits,
                    runtime_instruction_bounds=runtime_instruction_bounds,
                )
            )
        ordinary_active_slots = 0
        for slot in range(ENEMY_POOL_SIZE):
            base = slot * ENEMY_STRIDE
            record = pool[base : base + ENEMY_SCALE_SOURCE_READ_SIZE]
            flags = struct.unpack_from("<I", record, ENEMY_FLAGS_OFFSET)[0]
            if not flags & ENEMY_ACTIVE_FLAG:
                continue
            ordinary_active_slots += 1
            sources.append(
                decode_scale_vm_source(
                    record,
                    role="ordinary_pool",
                    slot=slot,
                    enemy_pointer=ENEMY_POOL_BASE + base,
                    scale_bits=phase_before.scale_bits,
                    runtime_instruction_bounds=runtime_instruction_bounds,
                )
            )
        if external_owner is not None:
            sources.append(
                decode_scale_vm_source(
                    external_owner,
                    role="spell_owner_outside_ordinary_pool",
                    slot=None,
                    enemy_pointer=spell_pointer,
                    scale_bits=phase_before.scale_bits,
                    runtime_instruction_bounds=runtime_instruction_bounds,
                )
            )

        if manager_before != manager_after:
            status = "manager_frame_changed"
        elif phase_before != phase_after:
            status = "phase_identity_changed"
        elif (
            phase_before.spell_active
            and spell_pointer
            and not any(
                source.enemy_pointer == spell_pointer for source in sources
            )
        ):
            status = "spell_owner_missing"
        else:
            status = "coherent"
        selected = CompleteScaleSourceCapture(
            status=status,
            attempts=attempt,
            expected_manager_frame=expected_manager_frame,
            manager_frame_before=manager_before,
            manager_frame_after=manager_after,
            phase_before=phase_before,
            phase_after=phase_after,
            sources=tuple(sources),
            manager_template_active=manager_template_active,
            ordinary_active_slots=ordinary_active_slots,
            spell_owner_in_ordinary_pool=owner_in_pool,
            spell_owner_in_manager_template=(
                owner_in_manager_template
            ),
            process_read_count=read_count,
            process_read_bytes=read_bytes,
            capture_ms=(clock() - started) * 1000.0,
        )
        if selected.coherent:
            return selected
    assert selected is not None
    return selected


@dataclass(frozen=True, slots=True)
class FinalBScaleSourceTraceConfiguration:
    static_path: Path
    expected_static_sha256: str = FINAL_B_ECL_STATIC_SHA256
    expected_route_id: int = 2
    expected_difficulty_index: int = 3
    expected_stage_route_index: int = FINAL_B_STAGE_ROUTE_INDEX
    target_spell_id: int | None = None
    target_subroutine: int = FINAL_B_SCALE_SUBROUTINE
    horizon_frames: int = FINAL_B_SCALE_HORIZON_FRAMES
    maximum_capture_attempts: int = 3

    def __post_init__(self) -> None:
        shipped_spell_id = final_b_scale_spell_id(
            self.expected_difficulty_index
        )
        if self.target_spell_id is None:
            object.__setattr__(self, "target_spell_id", shipped_spell_id)
        elif self.target_spell_id != shipped_spell_id:
            raise ValueError(
                "Final-B scale target spell does not match its difficulty"
            )
        if self.expected_stage_route_index != FINAL_B_STAGE_ROUTE_INDEX:
            raise ValueError(
                "Final-B scale authority requires stage route index 7"
            )


class FinalBScaleSourceTraceService:
    """One-shot complete-source observer for the spell-190 scale transition."""

    def __init__(
        self,
        configuration: FinalBScaleSourceTraceConfiguration,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if configuration.horizon_frames <= 0:
            raise ValueError("scale-source horizon must be positive")
        if configuration.maximum_capture_attempts <= 0:
            raise ValueError("scale-source capture attempts must be positive")
        static_image = configuration.static_path.read_bytes()
        digest = hashlib.sha256(static_image).hexdigest()
        if digest != configuration.expected_static_sha256.lower():
            raise ValueError("Final-B ECL image does not match its digest")
        ecl = parse_ecl(configuration.static_path)
        if not 0 <= configuration.target_subroutine < len(ecl.subroutines):
            raise ValueError("Final-B scale target subroutine is absent")
        target = ecl.subroutines[configuration.target_subroutine]
        scale_callbacks = {
            instruction.arguments[0]
            for instruction in target.instructions
            if (
                instruction.opcode == 0x88
                and instruction.arguments
                and not instruction.parameter_mask & 1
                and instruction.arguments[0] in _SCALE_CALLBACK_INDICES
            )
        }
        if not scale_callbacks:
            raise ValueError(
                "Final-B scale target has no literal scale callback"
            )
        self.configuration = configuration
        self._static_image = static_image
        self._static_sha256 = digest
        self._ecl = ecl
        self._clock = clock
        self._attempted = False
        self._accepted_schedule: Th08TimeScaleSchedule | None = None

    @property
    def attempted(self) -> bool:
        return self._attempted

    @property
    def accepted_schedule(self) -> Th08TimeScaleSchedule | None:
        """Return the typed schedule from the accepted one-shot capture."""

        return self._accepted_schedule

    def reset(self) -> None:
        """Rearm after an explicit physical gameplay-epoch reset."""

        self._attempted = False
        self._accepted_schedule = None

    def _trigger_matches(
        self,
        *,
        route_id: int,
        difficulty_index: int,
        stage_route_index: int,
        spell_id: int | None,
    ) -> bool:
        configuration = self.configuration
        return (
            route_id == configuration.expected_route_id
            and difficulty_index == configuration.expected_difficulty_index
            and stage_route_index
            == configuration.expected_stage_route_index
            and spell_id == configuration.target_spell_id
        )

    def observe_if_due(
        self,
        reader: ScaleSourceReader,
        *,
        decision_frame: int,
        expected_manager_frame: int,
        gameplay_epoch: int,
        route_id: int,
        difficulty_index: int,
        stage_route_index: int,
        spell_id: int | None,
        observed_root_scale_bits: int,
        observed_player_bomb_active: int,
    ) -> dict[str, object] | None:
        if self._attempted or not self._trigger_matches(
            route_id=route_id,
            difficulty_index=difficulty_index,
            stage_route_index=stage_route_index,
            spell_id=spell_id,
        ):
            return None
        if (
            observed_root_scale_bits != FINAL_B_QUARTER_SCALE_BITS
            or observed_player_bomb_active != 0
        ):
            return None
        self._attempted = True
        total_started = self._clock()
        runtime_capture: RuntimeEclImageCapture | None = None
        runtime_identity: RuntimeEclImageIdentity | None = None
        source_capture: CompleteScaleSourceCapture | None = None
        schedule_result: EclScaleScheduleResult | None = None
        reasons: list[str] = []
        error: str | None = None
        try:
            runtime_capture = capture_runtime_ecl_image(
                reader,
                clock=self._clock,
            )
            runtime_identity = compare_runtime_ecl_image(
                runtime_capture,
                self._static_image,
            )
            source_capture = capture_complete_scale_sources(
                reader,
                expected_manager_frame=expected_manager_frame,
                runtime_instruction_bounds=(
                    runtime_capture.runtime_base,
                    runtime_capture.runtime_base
                    + runtime_capture.image_length,
                ),
                maximum_attempts=(
                    self.configuration.maximum_capture_attempts
                ),
                clock=self._clock,
            )
            reasons.extend(
                self._capture_incomplete_reasons(
                    source_capture,
                    runtime_capture=runtime_capture,
                    runtime_identity=runtime_identity,
                )
            )
            if not reasons:
                schedule_result = self._synthesize(
                    source_capture,
                    runtime_base=runtime_capture.runtime_base,
                    source_frame=source_capture.manager_frame_before,
                )
                if not schedule_result.horizon_covered:
                    reasons.append(
                        f"schedule_incomplete:{schedule_result.stop_reason}"
                    )
                if not schedule_result.writes:
                    reasons.append("scale_write_absent")
                if schedule_result.bullet_velocity_rescale_frames:
                    reasons.append(
                        "callback_28_or_29_bullet_side_effect_unconsumed"
                    )
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            struct.error,
        ) as exception:
            error = f"{type(exception).__name__}: {exception}"
            reasons.append("capture_or_synthesis_error")

        status = (
            "accepted_complete_source_trace"
            if not reasons and schedule_result is not None
            else "unknown"
        )
        self._accepted_schedule = (
            schedule_result.schedule
            if status == "accepted_complete_source_trace"
            and schedule_result is not None
            else None
        )
        return {
            "kind": "finalb_scale_source_trace",
            "schema": FINAL_B_SCALE_SOURCE_TRACE_SCHEMA,
            "authority": FINAL_B_SCALE_SOURCE_TRACE_AUTHORITY,
            "status": status,
            "hard_action_authority": False,
            "changes_input": False,
            "decision_frame": decision_frame,
            "expected_manager_frame": expected_manager_frame,
            "capture_manager_frame": (
                source_capture.manager_frame_before
                if source_capture is not None
                else None
            ),
            "gameplay_epoch": gameplay_epoch,
            "route_id": route_id,
            "difficulty_index": difficulty_index,
            "stage_route_index": stage_route_index,
            "spell_id": spell_id,
            "configuration": {
                "static_path": self.configuration.static_path.as_posix(),
                "static_sha256": self._static_sha256,
                "target_subroutine": self.configuration.target_subroutine,
                "horizon_frames": self.configuration.horizon_frames,
                "maximum_capture_attempts": (
                    self.configuration.maximum_capture_attempts
                ),
                "continuation": (
                    "no_new_hit_no_bomb_scale_target_not_future_observation"
                ),
                "scheduler_order": (
                    "player_priority_9_enemy_ecl_11_laser_bullet_14"
                ),
            },
            "runtime_ecl_capture": (
                runtime_capture.record()
                if runtime_capture is not None
                else None
            ),
            "runtime_ecl_identity": (
                runtime_identity.record()
                if runtime_identity is not None
                else None
            ),
            "source_capture": (
                source_capture.compact_record()
                if source_capture is not None
                else None
            ),
            "schedule": (
                self._schedule_record(schedule_result)
                if schedule_result is not None
                else None
            ),
            "incomplete_reasons": reasons,
            "error": error,
            "timing_ms": {
                "total": (self._clock() - total_started) * 1000.0,
            },
        }

    def _capture_incomplete_reasons(
        self,
        capture: CompleteScaleSourceCapture,
        *,
        runtime_capture: RuntimeEclImageCapture,
        runtime_identity: RuntimeEclImageIdentity,
    ) -> list[str]:
        reasons: list[str] = []
        phase = capture.phase_before
        expected_context = struct.pack(
            "<II",
            runtime_capture.runtime_base,
            runtime_capture.runtime_base + ECL_SUBROUTINE_TABLE_OFFSET,
        )
        if not runtime_identity.exact_match:
            reasons.append("runtime_ecl_identity")
        if not capture.coherent:
            reasons.append(f"source_capture:{capture.status}")
        if phase.ecl_context != expected_context:
            reasons.append("runtime_ecl_context")
        if not phase.gameplay_active:
            reasons.append("gameplay_inactive")
        if (
            phase.route_id != self.configuration.expected_route_id
            or phase.difficulty_index
            != self.configuration.expected_difficulty_index
            or phase.stage_route_index
            != self.configuration.expected_stage_route_index
        ):
            reasons.append("route_difficulty_stage")
        if (
            not phase.spell_active
            or phase.spell_id != self.configuration.target_spell_id
        ):
            reasons.append("spell_identity")
        if phase.player_bomb_active:
            reasons.append("bomb_active")
        try:
            validate_time_scale_bits(
                phase.scale_bits,
                field="captured time scale",
            )
        except ValueError:
            reasons.append("time_scale_invalid")
        if phase.scale_bits != FINAL_B_QUARTER_SCALE_BITS:
            reasons.append("target_quarter_scale_not_observed")
        if any(source.snapshot is None for source in capture.sources):
            reasons.append("invalid_active_main_vm")
        if any(
            not source.enemy_flags & ENEMY_ACTIVE_FLAG
            for source in capture.sources
        ):
            reasons.append("inactive_captured_source")
        if len(capture.sources) != 1:
            reasons.append("active_main_vm_source_set_not_singleton")
        if any(
            pointer != 0
            for source in capture.sources
            for pointer in source.auxiliary_context_pointers
        ):
            reasons.append("auxiliary_context_present")
        if any(
            source.installed_callback
            and source.installed_callback not in CALLBACK_ADDRESSES
            for source in capture.sources
        ):
            reasons.append("installed_callback_unknown")
        if any(
            source.installed_callback in _SCALE_CALLBACK_ADDRESSES
            for source in capture.sources
        ):
            reasons.append("installed_scale_callback_present")
        if capture.sources and (
            capture.sources[0].enemy_pointer != phase.spell_enemy_pointer
        ):
            reasons.append("singleton_source_is_not_spell_owner")
        return list(dict.fromkeys(reasons))

    def _synthesize(
        self,
        capture: CompleteScaleSourceCapture,
        *,
        runtime_base: int,
        source_frame: int,
    ) -> EclScaleScheduleResult:
        source = capture.sources[0]
        snapshot = source.snapshot
        assert snapshot is not None
        instruction_index = build_exact_runtime_instruction_index(
            self._ecl,
            self._static_image,
            runtime_base=runtime_base,
            expected_sha256=self._static_sha256,
        )
        owner_by_address = {
            runtime_base + instruction.offset: subroutine.index
            for subroutine in self._ecl.subroutines
            for instruction in subroutine.instructions
        }
        if (
            owner_by_address.get(snapshot.instruction_pointer)
            != self.configuration.target_subroutine
        ):
            raise ValueError(
                "singleton scale source is outside target subroutine"
            )
        phase = capture.phase_before
        authority = EclScaleSourceAuthority(
            scale_writer_source_ids=(source.source_id,),
            writer_inventory_complete=True,
            scheduler_order_complete=True,
            installed_scale_callbacks_absent=True,
            unmodeled_phase_transitions_absent=True,
            post_update_capture=True,
            external_state_coherent=True,
            no_hit_no_bomb_continuation=True,
            provenance=(
                "physical_complete_ordinary_pool_spell_owner_transaction:"
                f"{self._static_sha256}"
            ),
        )
        return synthesize_ecl_time_scale_schedule(
            snapshot,
            source_id=source.source_id,
            source_frame=source_frame,
            authority=authority,
            environment=EclScaleEnvironment(
                difficulty_index=phase.difficulty_index,
                route_id=phase.route_id,
                spell_flags=phase.spell_flags,
            ),
            instruction_at=instruction_index.__getitem__,
            horizon_frames=self.configuration.horizon_frames,
            active_difficulty_mask=1 << phase.difficulty_index,
        )

    @staticmethod
    def _schedule_record(
        result: EclScaleScheduleResult,
    ) -> dict[str, object]:
        return {
            "semantics_version": TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
            "coverage": result.schedule.coverage,
            "root_scale_bits": result.schedule.root_scale_bits,
            "player_scale_bits": list(result.schedule.player_scale_bits),
            "laser_scale_bits": list(result.schedule.laser_scale_bits),
            "complete_horizon": result.schedule.complete_horizon,
            "provenance": result.schedule.provenance,
            "source_frame": result.schedule.source_frame,
            "stop_reason": result.stop_reason,
            "stop_frame": result.stop_frame,
            "instructions_scanned": result.instructions_scanned,
            "writes": [
                {
                    "frame": write.frame,
                    "callback_index": write.callback_index,
                    "scale_bits_before": write.scale_bits_before,
                    "scale_bits_after": write.scale_bits_after,
                    "instruction_address": write.instruction_address,
                    "scales_active_bullet_velocity": (
                        write.scales_active_bullet_velocity
                    ),
                }
                for write in result.writes
            ],
            "bullet_velocity_rescale_frames": list(
                result.bullet_velocity_rescale_frames
            ),
            "consumed_external_variables": list(
                result.consumed_external_variables
            ),
            "final_instruction_pointer": (
                result.final_instruction_pointer
            ),
            "final_timer_elapsed": result.final_timer_elapsed,
            "final_timer_fraction_bits": (
                result.final_timer_fraction_bits
            ),
        }


__all__ = [
    "CompleteScaleSourceCapture",
    "ECL_VM_INSTALLED_CALLBACK_OFFSET",
    "ECL_VM_INSTALLED_CALLBACK_RECORD_OFFSET",
    "ENEMY_SCALE_SOURCE_READ_SIZE",
    "FINAL_B_ECL_STATIC_SHA256",
    "FINAL_B_SCALE_HORIZON_FRAMES",
    "FINAL_B_QUARTER_SCALE_BITS",
    "FINAL_B_SCALE_SOURCE_TRACE_AUTHORITY",
    "FINAL_B_SCALE_SOURCE_TRACE_SCHEMA",
    "FINAL_B_SCALE_SPELL_ID",
    "FINAL_B_SCALE_SPELL_IDS",
    "FINAL_B_SCALE_SUBROUTINE",
    "FINAL_B_STAGE_ROUTE_INDEX",
    "FinalBScaleSourceTraceConfiguration",
    "FinalBScaleSourceTraceService",
    "ScaleSourcePhaseIdentity",
    "ScaleVmSource",
    "capture_complete_scale_sources",
    "decode_scale_vm_source",
    "final_b_scale_spell_id",
]
