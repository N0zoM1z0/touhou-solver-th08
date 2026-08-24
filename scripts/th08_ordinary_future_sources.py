"""Fail-closed ordinary-stage ECL/timeline future-source closure.

The analyzer consumes one coherent native source projection and an immutable
decoded ECL program.  It advances only native semantics that have an explicit
lowering here.  Every reached unsupported callback, periodic emitter, main or
auxiliary opcode, child topology, timeline event, or movement state makes the
entire requested horizon UNKNOWN.

The supported subset is intentionally sufficient for the retained H1
ordinary root without using its native endpoint as model input:

* every active manager-singleton and ordinary-pool main/auxiliary VM is joined;
* every contact-enabled active source body is advanced by that same native
  motion state and retained as a root-to-horizon AABB trajectory;
* sub30's interval arithmetic, player aim, and RNG variables are lowered;
* direct-fire modes 0x60..0x68 become finite angle-sector AABB trajectories;
* native movement state 0/1 and the reached 0x41/0x47 writes are advanced;
* 0x5C children are accepted only when their complete reached subroutine is
  proven emission-, laser-, callback-, topology-, and contact-silent;
* the exact stage-timeline clocks are advanced and any reached event currently
  fails closed instead of being omitted.

Keeping an enemy alive after a possible player-shot kill is conservative.
RNG variables are therefore set-valued rather than replayed from the captured
global stream: a kill can remove RNG consumers in an action-diverged branch.
"""

from __future__ import annotations

import math
import struct
from copy import deepcopy
from dataclasses import dataclass, field, replace
from itertools import product
from typing import Any

from th08_ecl_tool.core import EclFile, SubInstruction
from th08_enemy_collision import enemy_contact_size_to_lethal_half_extent
from th08_future_birth_envelope import (
    AUTOMATIC_PLAYER_AIM_MODES,
    FloatInterval,
    FutureDirectFire,
)
from th08_future_hazard_projection import (
    OrdinaryFutureHazardProjection,
    complete_future_hazard_projection,
    unknown_future_hazard_projection,
)
from th08_native_timer import Th08TimerState
from th08_timeline_model import (
    IndexedEnemyView,
    StageTimelineState,
    TimelineClock,
    TimelineExternalState,
    TimelineSpawnRequest,
    step_stage_timelines,
)
from touhou_control.corridor import AabbHazard, AabbTrajectoryHazard


ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION = (
    "th08-ordinary-future-sources-v17-source-spawn-pattern"
)
_PROJECTION_SCHEMA = "th08-native-snapshot-collision-control-projection-v14"
_DIRECT_FIRE_OPCODES = frozenset(range(0x60, 0x69))
# Native table entry 51 is ANM/effect-only:
#   table 0x004C6F94 -> init 0x00426280, update 0x004264F0.
# Both callbacks only mutate the 0x360-byte effect record.  The initializer's
# gameplay-RNG samples are already covered by the set-valued hostile geometry
# below, so they cannot narrow a later hostile outcome.
_HOSTILITY_NEUTRAL_EFFECT_TYPES = frozenset((51,))
_FLOAT_LOCAL_FIRST = 10016
_FLOAT_LOCAL_LAST = 10023
_RNG_UNIT_VARIABLE = 10033
_RNG_SIGNED_UNIT_VARIABLE = 10035
_ANGLE_TO_PLAYER_VARIABLE = 10048
_SOURCE_MOTION_ANGLE_VARIABLE = 10069
_TWO_PI = 2.0 * math.pi
_FLOAT32_ONE_BITS = 0x3F800000
_PLAYER_MAX_AXIS_SPEED = 4.0
_POSITION_TOLERANCE = 1.0e-3
_MAX_INSTRUCTIONS_PER_UPDATE = 64
_ENEMY_CONTACT_ENABLED_FLAG = 0x00000004
_ENEMY_CONTACT_BLOCKING_FLAGS = 0x00000830
_AUXILIARY_SLOT_COUNT = 4
_TRANSFORM_PROGRAM_LENGTH = 18
_TRANSFORM_RECORD_SIZE = 24
_MAX_TIMELINE_FRONTIER_STATES = 4096
_HEALTH_DAMAGE_ENVELOPE_SCHEMA = (
    "th08-route2-normal-shot-health-transition-damage-envelope-v1"
)


class FutureSourceClosureError(ValueError):
    """One reached native source semantic has no hard lowering."""


@dataclass
class _MotionState:
    base_x: float
    base_y: float
    relative_x: float
    relative_y: float
    movement_state: int
    mirror_x: bool
    angle: float
    angular_velocity: float
    speed: float
    speed_acceleration: float
    velocity_x: float
    velocity_y: float
    uncertainty_x: float
    uncertainty_y: float
    supported: bool
    orbit_angle: float = 0.0
    orbit_angular_velocity: float = 0.0
    orbit_radius: float = 0.0
    orbit_radius_acceleration: float = 0.0
    orbit_center_x: float = 0.0
    orbit_center_y: float = 0.0
    motion_timer_elapsed: int = 0
    motion_duration: int = 0
    timed_duration: int = 0
    timed_remaining: int = 0
    timed_fraction: float = 0.0
    timed_mode: int = 0
    timed_start_x: float = 0.0
    timed_start_y: float = 0.0
    timed_displacement_x: float = 0.0
    timed_displacement_y: float = 0.0

    @property
    def world_x(self) -> float:
        return self.base_x + self.relative_x

    @property
    def world_y(self) -> float:
        return self.base_y + self.relative_y

    @property
    def world_x_interval(self) -> FloatInterval:
        return FloatInterval(
            self.world_x - self.uncertainty_x,
            self.world_x + self.uncertainty_x,
        )

    @property
    def world_y_interval(self) -> FloatInterval:
        return FloatInterval(
            self.world_y - self.uncertainty_y,
            self.world_y + self.uncertainty_y,
        )


@dataclass
class _VmState:
    instruction_offset: int
    timer_elapsed: int
    integer_locals: list[int]
    float_locals: list[FloatInterval]
    scratch_integers: list[int]
    stopped: bool = False
    delay_remaining: int = 0
    # Affine dependency of each observed/local float on the player-aim
    # operand for the current native source update.  Captured locals begin at
    # zero because their concrete values are already observed.  ``None`` is
    # a fail-closed marker for a reached nonlinear/unfactorable expression;
    # it never invalidates the existing set-valued union envelope.
    float_local_aim_coefficients: list[float | None] = field(
        default_factory=lambda: [0.0] * 8
    )


@dataclass
class _SourceState:
    identity: str
    enemy_pointer: int
    motion: _MotionState
    main: _VmState
    auxiliaries: list[_VmState | None]
    emission: dict[str, object]
    enemy_flags: int
    body_half_width: float
    body_half_height: float
    phase_transition_armed: bool
    timeline_spawned: bool = False
    spawn_frame: int | None = None
    precompose_origin_x: FloatInterval | None = None
    precompose_origin_y: FloatInterval | None = None
    precompose_world_x: FloatInterval | None = None
    precompose_world_y: FloatInterval | None = None


@dataclass(frozen=True)
class OrdinaryFutureSourceClosure:
    projection: OrdinaryFutureHazardProjection
    direct_fire_events: tuple[FutureDirectFire, ...]
    source_count: int
    auxiliary_count: int
    silent_child_count: int
    timeline_steps: int
    timeline_spawn_count: int
    health_transition_proven_count: int
    health_transition_minimum_margin: int | None
    causal_prefix_reason: str | None


def _source_contact_body_sample(
    source: _SourceState,
) -> AabbHazard | None:
    """Return the exact source-motion contact AABB at the current update."""

    if (
        not source.enemy_flags & _ENEMY_CONTACT_ENABLED_FLAG
        or source.enemy_flags & _ENEMY_CONTACT_BLOCKING_FLAGS
    ):
        return None
    return AabbHazard(
        x=source.motion.world_x,
        y=source.motion.world_y,
        half_width=source.body_half_width + source.motion.uncertainty_x,
        half_height=source.body_half_height + source.motion.uncertainty_y,
    )


def _fail(message: str) -> None:
    raise FutureSourceClosureError(message)


def _signed_u32(value: int) -> int:
    return struct.unpack("<i", struct.pack("<I", value & 0xFFFFFFFF))[0]


def _signed_i16(value: int) -> int:
    value &= 0xFFFF
    return value if value < 0x8000 else value - 0x10000


def _float32(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]


def _finite(values: Any, *, label: str) -> None:
    if not all(math.isfinite(float(value)) for value in values):
        _fail(f"{label} contains a non-finite value")


def _instruction_map(ecl: EclFile) -> dict[int, SubInstruction]:
    return {
        instruction.offset: instruction
        for subroutine in ecl.subroutines
        for instruction in subroutine.instructions
    }


def _eligible(instruction: SubInstruction, difficulty_mask: int) -> bool:
    return (
        (instruction.difficulty_mask & difficulty_mask)
        == difficulty_mask
    )


def _runtime_program_identity(
    payload: dict[str, object],
    ecl: EclFile,
) -> tuple[int, int]:
    runtime = payload.get("stage_timeline_runtime")
    if not isinstance(runtime, dict):
        _fail("stage timeline runtime inventory is absent")
    ecl_file = runtime.get("ecl_file")
    if not isinstance(ecl_file, dict):
        _fail("runtime ECL file identity is absent")
    if int(ecl_file.get("magic", -1)) != 0x800:
        _fail("runtime ECL magic is not TH08 ECL")
    if int(ecl_file.get("subroutine_count", -1)) != len(ecl.subroutines):
        _fail("runtime/decoded ECL subroutine counts disagree")
    if int(ecl_file.get("timeline_count", -1)) != len(ecl.timelines):
        _fail("runtime/decoded ECL timeline counts disagree")
    if int(ecl_file.get("static_data_end_offset", -1)) != int(
        ecl.header.data_end_offset
    ):
        _fail("runtime/decoded ECL data-end offsets disagree")
    runtime_sha256 = ecl_file.get("canonical_sha256")
    if runtime_sha256 is not None and str(runtime_sha256) != ecl.sha256:
        _fail("runtime/decoded ECL canonical SHA-256 disagrees")
    return int(ecl_file["file_base"]), int(runtime["difficulty_mask"])


def _source_groups(
    payload: dict[str, object],
) -> tuple[tuple[str, dict[str, object]], ...]:
    manager = payload.get("enemy_manager_template_source")
    if not isinstance(manager, dict):
        _fail("manager singleton hostile-source range is absent")
    ordinary = {
        "source_role": "ordinary_enemy_pool",
        "enemy_bodies": payload.get("enemy_bodies"),
        "main_ecl_vm_inventory": payload.get("enemy_main_ecl_vm_inventory"),
        "main_ecl_installed_callbacks": payload.get(
            "enemy_main_ecl_installed_callbacks"
        ),
        "periodic_emission_state": payload.get(
            "enemy_periodic_emission_state"
        ),
        "emission_state": payload.get("enemy_emission_state"),
        "motion_state": payload.get("enemy_motion_state"),
        "phase_transition_state": payload.get(
            "enemy_phase_transition_state"
        ),
        "auxiliary_ecl_contexts": payload.get(
            "enemy_auxiliary_ecl_contexts"
        ),
    }
    return (
        (str(manager.get("source_role", "manager_singleton")), manager),
        ("ordinary_enemy_pool", ordinary),
    )


def _rows(record: object, *, label: str) -> list[object]:
    if not isinstance(record, dict) or not isinstance(record.get("rows"), list):
        _fail(f"{label} rows are absent")
    return list(record["rows"])


def _point_float_locals(raw_bits: object, *, label: str) -> list[FloatInterval]:
    if not isinstance(raw_bits, list) or len(raw_bits) != 8:
        _fail(f"{label} does not contain eight float locals")
    values = [_float32(int(bits)) for bits in raw_bits]
    _finite(values, label=label)
    return [FloatInterval.point(value) for value in values]


def _point_integer_locals(raw_values: object, *, label: str) -> list[int]:
    if not isinstance(raw_values, list) or len(raw_values) != 8:
        _fail(f"{label} does not contain eight integer locals")
    return [int(value) for value in raw_values]


def _motion_state(row: dict[str, object]) -> _MotionState:
    base = row.get("base_position")
    relative = row.get("relative_position")
    velocity = row.get("velocity")
    world = row.get("world_position")
    if not all(
        isinstance(value, list) and len(value) == 3
        for value in (base, relative, velocity, world)
    ):
        _fail("future source motion vector layout drifted")
    assert isinstance(base, list)
    assert isinstance(relative, list)
    assert isinstance(velocity, list)
    assert isinstance(world, list)
    numeric = (
        *base,
        *relative,
        *velocity,
        *world,
        row.get("angle"),
        row.get("angular_velocity"),
        row.get("speed"),
        row.get("speed_acceleration"),
        row.get("orbit_angle"),
        row.get("orbit_angular_velocity"),
        row.get("orbit_radius"),
        row.get("orbit_radius_acceleration"),
    )
    movement_state = int(row.get("movement_state", -1))
    orbit_center = row.get("orbit_center_position")
    if not isinstance(orbit_center, list) or len(orbit_center) != 3:
        _fail("future source orbit-center layout drifted")
    timed_displacement = row.get("timed_displacement")
    if not isinstance(timed_displacement, list) or len(timed_displacement) != 3:
        _fail("future source timed-displacement layout drifted")
    timer_fraction = (
        _float32(int(row.get("motion_timer_fraction_bits", -1)))
        if movement_state == 2
        else 0.0
    )
    numeric = (*numeric, *orbit_center)
    if movement_state == 2:
        numeric = (*numeric, *timed_displacement, timer_fraction)
    _finite(numeric, label="future source motion state")
    if (
        abs(float(base[0]) + float(relative[0]) - float(world[0]))
        > _POSITION_TOLERANCE
        or abs(float(base[1]) + float(relative[1]) - float(world[1]))
        > _POSITION_TOLERANCE
    ):
        _fail("composed source world position disagrees with base+relative")
    state = _MotionState(
        base_x=float(base[0]),
        base_y=float(base[1]),
        relative_x=float(relative[0]),
        relative_y=float(relative[1]),
        movement_state=movement_state,
        mirror_x=bool(row.get("mirror_x")),
        angle=float(row["angle"]),
        angular_velocity=float(row["angular_velocity"]),
        speed=float(row["speed"]),
        speed_acceleration=float(row["speed_acceleration"]),
        velocity_x=float(velocity[0]),
        velocity_y=float(velocity[1]),
        uncertainty_x=0.0,
        uncertainty_y=0.0,
        supported=movement_state in (0, 1, 2, 3),
        orbit_angle=float(row["orbit_angle"]),
        orbit_angular_velocity=float(row["orbit_angular_velocity"]),
        orbit_radius=float(row["orbit_radius"]),
        orbit_radius_acceleration=float(
            row["orbit_radius_acceleration"]
        ),
        orbit_center_x=float(orbit_center[0]),
        orbit_center_y=float(orbit_center[1]),
        motion_timer_elapsed=int(row["motion_timer_elapsed"]),
        motion_duration=int(row["motion_duration"]),
        timed_duration=(
            int(row["motion_duration"]) if movement_state == 2 else 0
        ),
        timed_remaining=(
            int(row["motion_timer_elapsed"]) if movement_state == 2 else 0
        ),
        timed_fraction=timer_fraction if movement_state == 2 else 0.0,
        timed_mode=(
            int(row.get("timed_mode", -1)) if movement_state == 2 else 0
        ),
        timed_start_x=(float(orbit_center[0]) if movement_state == 2 else 0.0),
        timed_start_y=(float(orbit_center[1]) if movement_state == 2 else 0.0),
        timed_displacement_x=(
            float(timed_displacement[0]) if movement_state == 2 else 0.0
        ),
        timed_displacement_y=(
            float(timed_displacement[1]) if movement_state == 2 else 0.0
        ),
    )
    if movement_state == 0 and (
        abs(state.velocity_x) > _POSITION_TOLERANCE
        or abs(state.velocity_y) > _POSITION_TOLERANCE
    ):
        _fail("movement state 0 carries nonzero unlowered velocity")
    if movement_state == 2 and (
        state.timed_duration <= 0
        or state.timed_remaining <= 0
        or not 0 <= state.timed_mode <= 6
        or not 0.0 <= state.timed_fraction < 1.0
    ):
        _fail("captured timed movement state is malformed")
    return state


def _callback_is_clear(row: object, *, label: str) -> None:
    if not isinstance(row, dict):
        _fail(f"{label} callback row is malformed")
    callback = row.get("installed_callback")
    if (
        not isinstance(callback, dict)
        or int(callback.get("function_pointer", -1)) != 0
    ):
        _fail(f"{label} installed callback requires address-specific lowering")


def _health_transition_hp_loss_upper_bound(
    payload: dict[str, object],
    *,
    damage_frames: int,
) -> int:
    """Bound HP loss visible to phase checks in ``damage_frames`` updates.

    Native enemy phase checks run before player-shot collision/HP subtraction
    in the same physical update.  A source projection through future frame H
    therefore needs damage only from frames 1..H-1: damage first applied in H
    cannot select a successor until H+1.  With no intervening damage update,
    even already-active shots contribute zero to this bound.
    """

    if damage_frames < 0:
        _fail("health damage horizon is negative")
    envelope = payload.get("route2_health_transition_damage_envelope")
    if not isinstance(envelope, dict):
        _fail("health phase transition damage envelope is absent")
    if str(envelope.get("schema")) != _HEALTH_DAMAGE_ENVELOPE_SCHEMA:
        _fail("health phase transition damage envelope schema drifted")
    if not bool(envelope.get("complete")):
        conditions = envelope.get("root_conditions")
        failed = (
            sorted(
                str(name)
                for name, satisfied in conditions.items()
                if not bool(satisfied)
            )
            if isinstance(conditions, dict)
            else ["malformed_root_conditions"]
        )
        _fail(
            "health phase transition damage envelope is incomplete: "
            + ",".join(failed)
        )
    cadence_length = int(envelope.get("cadence_length", -1))
    phases = envelope.get("future_raw_damage_by_cadence_phase")
    if (
        cadence_length <= 0
        or not isinstance(phases, list)
        or len(phases) != cadence_length
    ):
        _fail("health damage cadence envelope layout drifted")
    phase_damage = tuple(int(value) for value in phases)
    raw_phase_support = envelope.get("future_cadence_phase_support")
    if not isinstance(raw_phase_support, list) or not raw_phase_support:
        _fail("health damage cadence root support is absent")
    phase_support = tuple(int(value) for value in raw_phase_support)
    if any(not 0 <= phase < cadence_length for phase in phase_support):
        _fail("health damage cadence root support is outside the cycle")
    active_damage = int(
        envelope.get("active_raw_damage_upper_bound", -1)
    )
    if active_damage < 0 or any(value < 0 for value in phase_damage):
        _fail("health damage envelope contains negative damage")
    if damage_frames == 0:
        return 0
    cycles, remainder = divmod(damage_frames, cadence_length)
    future_damage = cycles * sum(phase_damage)
    if remainder:
        doubled = phase_damage + phase_damage
        future_damage += max(
            sum(doubled[start : start + remainder])
            for start in phase_support
        )
    ratio = envelope.get("player_damage_bonus_upper_ratio")
    if ratio != [106, 100]:
        _fail("health damage bonus upper ratio drifted")
    # Native applies floor(raw * 106 / 100) only when the observed global
    # bonus is active.  Applying it to all active and future raw damage is an
    # upper bound; the native per-frame cap of 70 can only reduce HP loss.
    return (active_damage + future_damage) * 106 // 100


def _maximum_health_transition_free_horizon(
    payload: dict[str, object],
    *,
    current_hitpoints: int,
    trigger_hitpoints: int,
    requested_horizon_frames: int,
) -> int:
    """Return the longest prefix whose native phase checks cannot fire."""

    if requested_horizon_frames < 0:
        _fail("health transition horizon is negative")
    if current_hitpoints < trigger_hitpoints:
        return 0

    def safe(horizon: int) -> bool:
        return (
            current_hitpoints
            - _health_transition_hp_loss_upper_bound(
                payload,
                damage_frames=max(0, horizon - 1),
            )
            - trigger_hitpoints
            >= 0
        )

    if safe(requested_horizon_frames):
        return requested_horizon_frames
    lower = 0
    upper = requested_horizon_frames
    while lower + 1 < upper:
        midpoint = (lower + upper) // 2
        if safe(midpoint):
            lower = midpoint
        else:
            upper = midpoint
    return lower


def _build_sources(
    payload: dict[str, object],
    *,
    ecl_base: int,
    horizon_frames: int,
) -> tuple[list[_SourceState], int, int, int | None, int]:
    sources: list[_SourceState] = []
    auxiliary_count = 0
    health_guards: list[tuple[int, int]] = []
    transition_free_horizon = horizon_frames
    for role, group in _source_groups(payload):
        inventory = group.get("main_ecl_vm_inventory")
        if not isinstance(inventory, dict):
            _fail(f"{role} main VM inventory is absent")
        if (
            int(inventory.get("invalid_active_vms", 0))
            or int(inventory.get("invalid_auxiliary_contexts", 0))
            or bool(inventory.get("invalid_auxiliary_context_rows", ()))
        ):
            _fail(f"{role} contains an invalid active ECL source")
        main_rows = _rows(inventory, label=f"{role} main VM")
        callback_rows = _rows(
            group.get("main_ecl_installed_callbacks"),
            label=f"{role} main callback",
        )
        periodic_rows = _rows(
            group.get("periodic_emission_state"),
            label=f"{role} periodic emitter",
        )
        emission_rows = _rows(
            group.get("emission_state"),
            label=f"{role} emission state",
        )
        motion_rows = _rows(
            group.get("motion_state"),
            label=f"{role} motion state",
        )
        phase_rows = _rows(
            group.get("phase_transition_state"),
            label=f"{role} phase transition state",
        )
        auxiliary_rows = _rows(
            group.get("auxiliary_ecl_contexts"),
            label=f"{role} auxiliary VM",
        )
        body_rows = group.get("enemy_bodies")
        if not isinstance(body_rows, list):
            _fail(f"{role} enemy body rows are absent")
        callbacks_by_pointer = {
            int(row["enemy_pointer"]): row
            for row in callback_rows
            if isinstance(row, dict)
        }
        periodic_by_pointer = {
            int(row["enemy_pointer"]): row
            for row in periodic_rows
            if isinstance(row, dict)
        }
        emission_by_pointer = {
            int(row["enemy_pointer"]): row
            for row in emission_rows
            if isinstance(row, dict)
        }
        motion_by_pointer = {
            int(row["enemy_pointer"]): row
            for row in motion_rows
            if isinstance(row, dict)
        }
        phase_by_pointer = {
            int(row["enemy_pointer"]): row
            for row in phase_rows
            if isinstance(row, dict)
        }
        body_by_pointer = {
            int(row["pointer"]): row
            for row in body_rows
            if isinstance(row, dict)
        }
        auxiliaries_by_pointer: dict[int, list[dict[str, object]]] = {}
        for raw_auxiliary in auxiliary_rows:
            if not isinstance(raw_auxiliary, dict):
                _fail(f"{role} auxiliary VM row is malformed")
            _callback_is_clear(raw_auxiliary, label=f"{role} auxiliary")
            auxiliaries_by_pointer.setdefault(
                int(raw_auxiliary["enemy_pointer"]),
                [],
            ).append(raw_auxiliary)
        if not (
            len(main_rows)
            == len(callbacks_by_pointer)
            == len(periodic_by_pointer)
            == len(emission_by_pointer)
            == len(motion_by_pointer)
            == len(phase_by_pointer)
            == len(body_by_pointer)
        ):
            _fail(f"{role} active source join is incomplete")
        for raw_main in main_rows:
            if not isinstance(raw_main, list) or len(raw_main) != 9:
                _fail(f"{role} main VM row layout drifted")
            (
                slot,
                enemy_pointer,
                _enemy_flags,
                instruction_pointer,
                timer_fraction_bits,
                timer_elapsed,
                integer_locals,
                float_local_bits,
                scratch_integers,
            ) = raw_main
            pointer = int(enemy_pointer)
            _callback_is_clear(
                callbacks_by_pointer[pointer],
                label=f"{role} main",
            )
            periodic = periodic_by_pointer[pointer]
            if bool(periodic.get("enabled")):
                _fail(
                    f"{role}:{int(slot)} active periodic emitter is unsupported"
                )
            if int(timer_fraction_bits) != 0:
                _fail(f"{role}:{int(slot)} main VM has fractional time")
            main = _VmState(
                instruction_offset=int(instruction_pointer) - ecl_base,
                timer_elapsed=int(timer_elapsed),
                integer_locals=_point_integer_locals(
                    integer_locals,
                    label=f"{role}:{int(slot)} main integer locals",
                ),
                float_locals=_point_float_locals(
                    float_local_bits,
                    label=f"{role}:{int(slot)} main float locals",
                ),
                scratch_integers=[int(value) for value in scratch_integers],
            )
            auxiliaries: list[_VmState | None] = [None] * _AUXILIARY_SLOT_COUNT
            for auxiliary in auxiliaries_by_pointer.get(pointer, []):
                auxiliary_index = int(auxiliary["auxiliary_index"])
                if not 0 <= auxiliary_index < _AUXILIARY_SLOT_COUNT:
                    _fail(f"{role}:{int(slot)} auxiliary index is invalid")
                if auxiliaries[auxiliary_index] is not None:
                    _fail(f"{role}:{int(slot)} auxiliary slot is duplicated")
                if int(auxiliary.get("call_depth", -1)) != 0:
                    _fail(
                        f"{role}:{int(slot)} auxiliary saved stack is unsupported"
                    )
                state = auxiliary.get("state")
                if not isinstance(state, dict):
                    _fail(f"{role}:{int(slot)} auxiliary state is absent")
                # ECL scheduling reads only the signed integer elapsed member.
                # At the already-required unit time scale, timer advance keeps
                # a finite captured fraction unchanged while incrementing that
                # integer.  The native previous member does not affect dispatch.
                local = state.get("local_projection")
                if not isinstance(local, dict):
                    _fail(
                        f"{role}:{int(slot)} auxiliary locals are absent"
                    )
                auxiliaries[auxiliary_index] = _VmState(
                    instruction_offset=(
                        int(state["instruction_pointer"]) - ecl_base
                    ),
                    timer_elapsed=int(state["timer_elapsed"]),
                    integer_locals=_point_integer_locals(
                        local.get("integer_locals"),
                        label=(
                            f"{role}:{int(slot)} auxiliary integer locals"
                        ),
                    ),
                    float_locals=_point_float_locals(
                        local.get("float_local_bits"),
                        label=(
                            f"{role}:{int(slot)} auxiliary float locals"
                        ),
                    ),
                    scratch_integers=[
                        int(value)
                        for value in local.get("scratch_integers", [])
                    ],
                    delay_remaining=max(
                        0,
                        int(state.get("delay_timer_elapsed", 0)),
                    ),
                )
            auxiliary_count += sum(
                auxiliary is not None for auxiliary in auxiliaries
            )
            phase = phase_by_pointer[pointer]
            thresholds = phase.get("health_thresholds")
            if not isinstance(thresholds, list) or len(thresholds) != 4:
                _fail(f"{role}:{int(slot)} phase threshold layout drifted")
            successors = phase.get("health_successor_subroutines")
            if not isinstance(successors, list) or len(successors) != 4:
                _fail(f"{role}:{int(slot)} phase successor layout drifted")
            active_thresholds = tuple(
                int(value) for value in thresholds if int(value) >= 0
            )
            timeout_frame = int(phase.get("timeout_frame", -2))
            phase_timer_elapsed = int(
                phase.get("phase_timer_elapsed", -0x80000000)
            )
            if active_thresholds:
                current_hitpoints = int(
                    phase.get("current_hitpoints", -0x80000000)
                )
                trigger_hitpoints = max(active_thresholds)
                health_guards.append(
                    (current_hitpoints, trigger_hitpoints)
                )
                transition_free_horizon = min(
                    transition_free_horizon,
                    _maximum_health_transition_free_horizon(
                        payload,
                        current_hitpoints=current_hitpoints,
                        trigger_hitpoints=trigger_hitpoints,
                        requested_horizon_frames=horizon_frames,
                    ),
                )
            if timeout_frame >= 0:
                transition_free_horizon = min(
                    transition_free_horizon,
                    max(0, timeout_frame - phase_timer_elapsed - 1),
                )
            body = body_by_pointer[pointer]
            body_half_width = float(body["half_width"])
            body_half_height = float(body["half_height"])
            _finite(
                (body_half_width, body_half_height),
                label=f"{role}:{int(slot)} body geometry",
            )
            if body_half_width < 0.0 or body_half_height < 0.0:
                _fail(f"{role}:{int(slot)} body geometry is negative")
            sources.append(
                _SourceState(
                    identity=f"{role}:{int(slot)}:{pointer:#x}",
                    enemy_pointer=pointer,
                    motion=_motion_state(motion_by_pointer[pointer]),
                    main=main,
                    auxiliaries=auxiliaries,
                    emission=emission_by_pointer[pointer],
                    enemy_flags=int(body["flags"]),
                    body_half_width=body_half_width,
                    body_half_height=body_half_height,
                    phase_transition_armed=False,
                )
            )
    return (
        sources,
        auxiliary_count,
        len(health_guards),
        (
            min(
                current_hitpoints
                - _health_transition_hp_loss_upper_bound(
                    payload,
                    damage_frames=max(0, transition_free_horizon - 1),
                )
                - trigger_hitpoints
                for current_hitpoints, trigger_hitpoints in health_guards
            )
            if health_guards
            else None
        ),
        transition_free_horizon,
    )


def _variable_identifier(raw: int) -> int:
    value = _float32(raw)
    rounded = int(round(value))
    if not math.isfinite(value) or abs(value - rounded) > 1.0e-4:
        _fail(f"dynamic ECL float operand {value!r} is not a variable")
    return rounded


def _eval_float_operand(
    raw: int,
    *,
    dynamic: bool,
    vm: _VmState,
    aim_angle: FloatInterval,
    source: _SourceState,
) -> FloatInterval:
    if not dynamic:
        value = _float32(raw)
        if not math.isfinite(value):
            _fail("literal ECL float operand is non-finite")
        return FloatInterval.point(value)
    variable = _variable_identifier(raw)
    if _FLOAT_LOCAL_FIRST <= variable <= _FLOAT_LOCAL_LAST:
        return vm.float_locals[variable - _FLOAT_LOCAL_FIRST]
    if variable == _RNG_UNIT_VARIABLE:
        return FloatInterval(0.0, 1.0)
    if variable == _RNG_SIGNED_UNIT_VARIABLE:
        return FloatInterval(-1.0, 1.0)
    if variable == _ANGLE_TO_PLAYER_VARIABLE:
        return aim_angle
    # ecl_eval_float case 0x2755 reads enemy+0x2D94, the coherently
    # captured and subsequently advanced motion angle.
    if variable == _SOURCE_MOTION_ANGLE_VARIABLE:
        return FloatInterval.point(source.motion.angle)
    _fail(f"dynamic ECL float variable {variable} is unsupported")
    raise AssertionError("unreachable")


def _float_operand_aim_coefficient(
    raw: int,
    *,
    dynamic: bool,
    vm: _VmState,
) -> float | None:
    """Return a proved affine coefficient for native angle-to-player."""

    if not dynamic:
        return 0.0
    variable = _variable_identifier(raw)
    if _FLOAT_LOCAL_FIRST <= variable <= _FLOAT_LOCAL_LAST:
        return vm.float_local_aim_coefficients[
            variable - _FLOAT_LOCAL_FIRST
        ]
    if variable in (
        _RNG_UNIT_VARIABLE,
        _RNG_SIGNED_UNIT_VARIABLE,
        _SOURCE_MOTION_ANGLE_VARIABLE,
    ):
        return 0.0
    if variable == _ANGLE_TO_PLAYER_VARIABLE:
        return 1.0
    return None


def _scaled_affine_coefficient(
    left: FloatInterval,
    left_coefficient: float | None,
    right: FloatInterval,
    right_coefficient: float | None,
) -> float | None:
    """Factor a product only when the other operand is a proved point."""

    if left_coefficient is None or right_coefficient is None:
        return None
    if left_coefficient == 0.0 and right_coefficient == 0.0:
        return 0.0
    if left_coefficient == 0.0 and left.lower == left.upper:
        return left.lower * right_coefficient
    if right_coefficient == 0.0 and right.lower == right.upper:
        return right.lower * left_coefficient
    return None


def _apply_float_binary(
    *,
    source: _SourceState,
    vm: _VmState,
    instruction: SubInstruction,
    aim_angle: FloatInterval,
) -> None:
    """Apply shipped float add/subtract while retaining aim dependence."""

    opcode = int(instruction.opcode)
    if opcode not in (0x19, 0x1A) or len(instruction.arguments) != 3:
        _fail("float add/subtract argument layout drifted")
    destination = _float_lvalue(int(instruction.arguments[0]))
    left = _eval_float_operand(
        int(instruction.arguments[1]),
        dynamic=bool(instruction.parameter_mask & 0x02),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    right = _eval_float_operand(
        int(instruction.arguments[2]),
        dynamic=bool(instruction.parameter_mask & 0x04),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    vm.float_locals[destination] = (
        left.add(right)
        if opcode == 0x19
        else FloatInterval(
            left.lower - right.upper,
            left.upper - right.lower,
        )
    )
    left_coefficient = _float_operand_aim_coefficient(
        int(instruction.arguments[1]),
        dynamic=bool(instruction.parameter_mask & 0x02),
        vm=vm,
    )
    right_coefficient = _float_operand_aim_coefficient(
        int(instruction.arguments[2]),
        dynamic=bool(instruction.parameter_mask & 0x04),
        vm=vm,
    )
    vm.float_local_aim_coefficients[destination] = (
        None
        if left_coefficient is None or right_coefficient is None
        else (
            left_coefficient + right_coefficient
            if opcode == 0x19
            else left_coefficient - right_coefficient
        )
    )


def _normalize_angle_interval(
    value: FloatInterval,
) -> tuple[FloatInterval, bool]:
    """Conservatively lower native normalize_angle_pi over one interval."""

    if value.upper - value.lower >= _TWO_PI:
        return FloatInterval(-math.pi, math.pi), False
    lower_bin = math.floor((value.lower + math.pi) / _TWO_PI)
    upper_bin = math.floor((value.upper + math.pi) / _TWO_PI)
    if lower_bin != upper_bin:
        return FloatInterval(-math.pi, math.pi), False
    return (
        FloatInterval(
            value.lower - lower_bin * _TWO_PI,
            value.upper - lower_bin * _TWO_PI,
        ),
        True,
    )


def _normalize_float_lvalue_angle(
    *,
    source: _SourceState,
    vm: _VmState,
    instruction: SubInstruction,
    aim_angle: FloatInterval,
) -> None:
    if len(instruction.arguments) != 1:
        _fail("normalize-angle argument layout drifted")
    destination = _float_lvalue(int(instruction.arguments[0]))
    value = _eval_float_operand(
        int(instruction.arguments[0]),
        dynamic=bool(instruction.parameter_mask & 0x01),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    normalized, affine_preserved = _normalize_angle_interval(value)
    vm.float_locals[destination] = normalized
    if not affine_preserved:
        vm.float_local_aim_coefficients[destination] = None


def _define_bullet_transform(
    *,
    source: _SourceState,
    vm: _VmState,
    instruction: SubInstruction,
    aim_angle: FloatInterval,
) -> None:
    """Apply shipped opcode 0x6F to the captured 18-record descriptor."""

    if len(instruction.arguments) != 7:
        _fail("bullet-transform definition argument layout drifted")
    integer_values = [
        _eval_integer_operand(
            int(instruction.arguments[index]),
            dynamic=bool(instruction.parameter_mask & (1 << index)),
            vm=vm,
        )
        for index in range(5)
    ]
    index, kind, wait_for_clear, int_0, int_1 = integer_values
    if not 0 <= index < _TRANSFORM_PROGRAM_LENGTH:
        _fail(f"bullet-transform index {index} is out of range")
    float_values = [
        _eval_float_operand(
            int(instruction.arguments[index]),
            dynamic=bool(instruction.parameter_mask & (1 << index)),
            vm=vm,
            aim_angle=aim_angle,
            source=source,
        )
        for index in (5, 6)
    ]
    if any(value.lower != value.upper for value in float_values):
        _fail("bullet-transform float operand is set-valued")
    descriptor = source.emission.get("descriptor")
    if not isinstance(descriptor, dict):
        _fail("source emission descriptor is absent")
    transform_hex = descriptor.get("transform_program_hex")
    if not isinstance(transform_hex, str):
        _fail("source transform program is absent")
    try:
        program = bytearray.fromhex(transform_hex)
    except ValueError as error:
        raise FutureSourceClosureError(
            "source transform program is malformed"
        ) from error
    expected_size = _TRANSFORM_PROGRAM_LENGTH * _TRANSFORM_RECORD_SIZE
    if len(program) != expected_size:
        _fail("source transform program has the wrong size")
    struct.pack_into(
        "<ffiiII",
        program,
        index * _TRANSFORM_RECORD_SIZE,
        float_values[0].lower,
        float_values[1].lower,
        _signed_u32(int_0),
        _signed_u32(int_1),
        kind & 0xFFFFFFFF,
        wait_for_clear & 0xFFFFFFFF,
    )
    descriptor["transform_program_hex"] = bytes(program).hex()


def _aim_residual(
    value: FloatInterval,
    *,
    aim_angle: FloatInterval,
    coefficient: float | None,
) -> FloatInterval | None:
    if coefficient is None:
        return None
    dependency = aim_angle.scale(coefficient)
    lower = value.lower - dependency.lower
    upper = value.upper - dependency.upper
    # The affine endpoints are mathematically ordered. Binary64 evaluation of
    # the same binary32-derived angle can reverse two equal residual endpoints
    # by one rounding unit, which must widen rather than create false UNKNOWN.
    return FloatInterval(min(lower, upper), max(lower, upper))


def _float_lvalue(raw: int) -> int:
    variable = _variable_identifier(raw)
    if not _FLOAT_LOCAL_FIRST <= variable <= _FLOAT_LOCAL_LAST:
        _fail(f"ECL float lvalue {variable} is not a captured local")
    return variable - _FLOAT_LOCAL_FIRST


def _integer_lvalue(raw: int, vm: _VmState) -> tuple[list[int], int]:
    variable = _signed_u32(raw)
    if 10000 <= variable <= 10007:
        return vm.integer_locals, variable - 10000
    if 10036 <= variable <= 10039:
        index = variable - 10036
        if index >= len(vm.scratch_integers):
            _fail("ECL scratch integer is absent")
        return vm.scratch_integers, index
    _fail(f"ECL integer lvalue {variable} is not a captured local")
    raise AssertionError("unreachable")


def _eval_integer_operand(
    raw: int,
    *,
    dynamic: bool,
    vm: _VmState,
) -> int:
    if not dynamic:
        return _signed_u32(raw)
    variable = _signed_u32(raw)
    if 10000 <= variable <= 10007:
        return vm.integer_locals[variable - 10000]
    if 10036 <= variable <= 10039:
        index = variable - 10036
        if index >= len(vm.scratch_integers):
            _fail("ECL scratch integer is absent")
        return vm.scratch_integers[index]
    _fail(f"dynamic ECL integer variable {variable} is unsupported")
    raise AssertionError("unreachable")


def _direct_fire_count(
    raw: int,
    *,
    dynamic: bool,
    vm: _VmState,
) -> int:
    # The shipped direct-fire cases evaluate dynamic operands through
    # ecl_eval_int, then store the low signed word in the fire descriptor.
    value = _eval_integer_operand(raw, dynamic=dynamic, vm=vm)
    return struct.unpack("<h", struct.pack("<H", value & 0xFFFF))[0]


def _literal_integer(instruction: SubInstruction, index: int) -> int:
    if instruction.parameter_mask & (1 << index):
        _fail(
            f"dynamic integer operand {index} at "
            f"{instruction.offset:#x} is unsupported"
        )
    return _signed_u32(int(instruction.arguments[index]))


def _literal_float(
    instruction: SubInstruction,
    index: int,
) -> float:
    if instruction.parameter_mask & (1 << index):
        _fail(
            f"dynamic movement operand {index} at "
            f"{instruction.offset:#x} is unsupported"
        )
    value = _float32(int(instruction.arguments[index]))
    if not math.isfinite(value):
        _fail("movement operand is non-finite")
    return value


def _player_reachable_box(
    *,
    root_x: float,
    root_y: float,
    frame: int,
) -> tuple[float, float, float, float]:
    reach = _PLAYER_MAX_AXIS_SPEED * frame
    return (
        max(8.0, root_x - reach),
        min(376.0, root_x + reach),
        max(16.0, root_y - reach),
        min(432.0, root_y + reach),
    )


def _minimal_angle_interval(angles: list[float]) -> FloatInterval:
    normalized = sorted(angle % _TWO_PI for angle in angles)
    if len(normalized) == 1:
        return FloatInterval.point(normalized[0])
    gaps = [
        (
            (normalized[(index + 1) % len(normalized)] - normalized[index])
            % _TWO_PI,
            index,
        )
        for index in range(len(normalized))
    ]
    _gap, index = max(gaps)
    start = normalized[(index + 1) % len(normalized)]
    end = normalized[index]
    if end < start:
        end += _TWO_PI
    return FloatInterval(start, end)


def _aim_interval(
    *,
    source_x: FloatInterval,
    source_y: FloatInterval,
    root_player_x: float,
    root_player_y: float,
    frame: int,
) -> FloatInterval:
    left, right, top, bottom = _player_reachable_box(
        root_x=root_player_x,
        root_y=root_player_y,
        frame=frame,
    )
    if (
        source_x.lower <= right
        and source_x.upper >= left
        and source_y.lower <= bottom
        and source_y.upper >= top
    ):
        return FloatInterval(-math.pi, math.pi)
    return _minimal_angle_interval(
        [
            math.atan2(player_y - enemy_y, player_x - enemy_x)
            for enemy_x in (source_x.lower, source_x.upper)
            for enemy_y in (source_y.lower, source_y.upper)
            for player_x in (left, right)
            for player_y in (top, bottom)
        ]
    )


def _template_geometry(
    payload: dict[str, object],
    bullet_type: int,
) -> tuple[float, float]:
    geometry = payload.get("bullet_template_geometry")
    rows = _rows(geometry, label="bullet template geometry")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and int(row.get("type", -1)) == bullet_type
    ]
    if len(matches) != 1:
        _fail(f"bullet type {bullet_type} has no unique template geometry")
    half_width = float(matches[0]["half_width"])
    half_height = float(matches[0]["half_height"])
    _finite((half_width, half_height), label="bullet template geometry")
    if half_width < 0.0 or half_height < 0.0:
        _fail("bullet template half-extent is negative")
    return half_width, half_height


def _direct_fire_type_color(
    *,
    packed: int,
    parameter_mask: int,
    vm: _VmState,
) -> tuple[int, int]:
    """Resolve the independent signed-i16 type/color operands used natively."""

    raw_type = _signed_i16(packed)
    raw_color = _signed_i16(packed >> 16)
    bullet_type = _eval_integer_operand(
        raw_type,
        dynamic=bool(parameter_mask & 0x01),
        vm=vm,
    )
    bullet_color = _eval_integer_operand(
        raw_color,
        dynamic=bool(parameter_mask & 0x02),
        vm=vm,
    )
    return _signed_i16(bullet_type), _signed_i16(bullet_color)


def _maximum_transform_template_geometry(
    *,
    payload: dict[str, object],
    transform_program: bytes,
    original_flags: int,
    half_width: float,
    half_height: float,
) -> tuple[float, float]:
    """Include every reached template replacement in collision geometry."""

    if len(transform_program) != (
        _TRANSFORM_PROGRAM_LENGTH * _TRANSFORM_RECORD_SIZE
    ):
        _fail("source transform program has the wrong size")
    for index in range(_TRANSFORM_PROGRAM_LENGTH):
        _float_0, _float_1, int_0, _int_1, kind, _wait = (
            struct.unpack_from(
                "<ffiiII",
                transform_program,
                index * _TRANSFORM_RECORD_SIZE,
            )
        )
        if kind == 0:
            break
        if kind & original_flags and kind == 0x0004000:
            replacement_width, replacement_height = _template_geometry(
                payload,
                int_0,
            )
            half_width = max(half_width, replacement_width)
            half_height = max(half_height, replacement_height)
    return half_width, half_height


def _direct_fire_events(
    *,
    source: _SourceState,
    instruction: SubInstruction,
    vm: _VmState,
    frame: int,
    aim_angle: FloatInterval,
    payload: dict[str, object],
) -> tuple[FutureDirectFire, ...]:
    if not source.motion.supported:
        _fail(
            f"{source.identity} emits from unsupported movement state "
            f"{source.motion.movement_state}"
        )
    if len(instruction.arguments) != 8:
        _fail(f"direct fire at {instruction.offset:#x} argument layout drifted")
    bullet_type, _bullet_color = _direct_fire_type_color(
        packed=int(instruction.arguments[0]),
        parameter_mask=int(instruction.parameter_mask),
        vm=vm,
    )
    count1 = _direct_fire_count(
        int(instruction.arguments[1]),
        dynamic=bool(instruction.parameter_mask & 0x04),
        vm=vm,
    )
    count2 = _direct_fire_count(
        int(instruction.arguments[2]),
        dynamic=bool(instruction.parameter_mask & 0x08),
        vm=vm,
    )
    if count1 <= 0 or count2 <= 0:
        _fail("future direct-fire count is not positive")
    speed1 = _eval_float_operand(
        int(instruction.arguments[3]),
        dynamic=bool(instruction.parameter_mask & 0x10),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    speed2 = _eval_float_operand(
        int(instruction.arguments[4]),
        dynamic=bool(instruction.parameter_mask & 0x20),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    angle1 = _eval_float_operand(
        int(instruction.arguments[5]),
        dynamic=bool(instruction.parameter_mask & 0x40),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    angle2 = _eval_float_operand(
        int(instruction.arguments[6]),
        dynamic=bool(instruction.parameter_mask & 0x80),
        vm=vm,
        aim_angle=aim_angle,
        source=source,
    )
    angle1_aim_coefficient = _float_operand_aim_coefficient(
        int(instruction.arguments[5]),
        dynamic=bool(instruction.parameter_mask & 0x40),
        vm=vm,
    )
    angle2_aim_coefficient = _float_operand_aim_coefficient(
        int(instruction.arguments[6]),
        dynamic=bool(instruction.parameter_mask & 0x80),
        vm=vm,
    )
    original_flags = int(instruction.arguments[7])
    rank_count = source.emission.get("rank_count_interval")
    rank_speed = source.emission.get("rank_speed_interval")
    if (
        not isinstance(rank_count, list)
        or len(rank_count) != 4
        or any(int(value) != 0 for value in rank_count)
    ):
        _fail("nonzero rank count interpolation requires exact count lowering")
    if not isinstance(rank_speed, list) or len(rank_speed) != 2:
        _fail("rank speed interpolation layout drifted")
    rank_adjustment = FloatInterval(
        min(float(rank_speed[0]), float(rank_speed[1])),
        max(float(rank_speed[0]), float(rank_speed[1])),
    )
    speed1 = speed1.add(rank_adjustment)
    speed2 = speed2.add(rank_adjustment)
    if speed1.lower < 0.0 or speed2.lower < 0.0:
        _fail("future direct-fire speed interval crosses negative")
    descriptor = source.emission.get("descriptor")
    if not isinstance(descriptor, dict):
        _fail("source emission descriptor is absent")
    transform_hex = descriptor.get("transform_program_hex")
    if not isinstance(transform_hex, str):
        _fail("source transform program is absent")
    try:
        transform_program = bytes.fromhex(transform_hex)
        transform_zero = not any(transform_program)
    except ValueError as error:
        raise FutureSourceClosureError(
            "source transform program is malformed"
        ) from error
    emission_offset = source.emission.get("emission_offset")
    if not isinstance(emission_offset, list) or len(emission_offset) != 3:
        _fail("source emission offset is absent")
    _finite(emission_offset, label="source emission offset")
    origin_x = source.motion.world_x_interval.add(
        FloatInterval.point(float(emission_offset[0]))
    )
    origin_y = source.motion.world_y_interval.add(
        FloatInterval.point(float(emission_offset[1]))
    )
    if source.precompose_origin_x is not None:
        origin_x = FloatInterval(
            min(origin_x.lower, source.precompose_origin_x.lower),
            max(origin_x.upper, source.precompose_origin_x.upper),
        )
    if source.precompose_origin_y is not None:
        origin_y = FloatInterval(
            min(origin_y.lower, source.precompose_origin_y.lower),
            max(origin_y.upper, source.precompose_origin_y.upper),
        )
    half_width, half_height = _template_geometry(payload, bullet_type)
    half_width, half_height = _maximum_transform_template_geometry(
        payload=payload,
        transform_program=transform_program,
        original_flags=original_flags,
        half_width=half_width,
        half_height=half_height,
    )
    mode = int(instruction.opcode) - 0x60
    if mode in AUTOMATIC_PLAYER_AIM_MODES:
        compact_state = payload.get("compact_state")
        if not isinstance(compact_state, dict):
            _fail("compact root is absent for automatic direct-fire aim")
        root_player_x = compact_state.get("player_x")
        root_player_y = compact_state.get("player_y")
        if not isinstance(root_player_x, (int, float)) or not isinstance(
            root_player_y, (int, float)
        ):
            _fail("compact player root is absent for automatic direct-fire aim")
        _finite(
            (root_player_x, root_player_y),
            label="compact player root",
        )
        mode_aim_angle = _aim_interval(
            source_x=origin_x,
            source_y=origin_y,
            root_player_x=float(root_player_x),
            root_player_y=float(root_player_y),
            frame=frame,
        )
    else:
        mode_aim_angle = FloatInterval.point(0.0)
    return (
        FutureDirectFire(
            source=(
                f"{source.identity}:pc={instruction.offset:#x}:"
                f"frame={frame}"
            ),
            activation_frames=(frame,),
            origin_x=origin_x,
            origin_y=origin_y,
            mode=mode,
            count1=count1,
            count2=count2,
            speed1=speed1,
            speed2=speed2,
            angle1=angle1,
            angle2=angle2,
            aim_angle=mode_aim_angle,
            half_width=half_width,
            half_height=half_height,
            original_flags=original_flags,
            transform_program_zero=transform_zero,
            transform_program=transform_program,
            angle1_player_aim_coefficient=angle1_aim_coefficient,
            angle1_player_aim_residual=_aim_residual(
                angle1,
                aim_angle=aim_angle,
                coefficient=angle1_aim_coefficient,
            ),
            angle2_player_aim_coefficient=angle2_aim_coefficient,
            angle2_player_aim_residual=_aim_residual(
                angle2,
                aim_angle=aim_angle,
                coefficient=angle2_aim_coefficient,
            ),
        ),
    )


def _prove_child_silent(
    ecl: EclFile,
    *,
    subroutine_index: int,
    remaining_horizon: int,
) -> None:
    if not 0 <= subroutine_index < len(ecl.subroutines):
        _fail(f"child subroutine {subroutine_index} is out of range")
    allowed = frozenset((0x01, 0x36, 0x49, 0x4A, 0x4D, 0x50, 0x51, 0x53))
    subroutine = ecl.subroutines[subroutine_index]
    for instruction in subroutine.instructions:
        if instruction.time > remaining_horizon:
            continue
        if int(instruction.opcode) not in allowed:
            _fail(
                f"child sub{subroutine_index} reaches unsupported opcode "
                f"{instruction.opcode:#x} at {instruction.offset:#x}"
            )
        # 0x5C constructs the child synchronously, then clears contact bit
        # 0x4.  A later flag mutation could re-enable contact and is rejected.
        if instruction.time > 0 and int(instruction.opcode) in (0x4F, 0x50, 0x51):
            _fail(
                f"child sub{subroutine_index} mutates contact flags after spawn"
            )


def _execute_auxiliary(
    *,
    source: _SourceState,
    vm: _VmState,
    instructions: dict[int, SubInstruction],
    difficulty_mask: int,
    frame: int,
    aim_angle: FloatInterval,
    payload: dict[str, object],
) -> tuple[FutureDirectFire, ...]:
    events: list[FutureDirectFire] = []
    if vm.stopped:
        return ()
    if vm.delay_remaining > 0:
        # The selected VM's +0x90 delay timer is decremented once per update;
        # its ordinary ECL timer is decremented and then advanced, net zero.
        vm.delay_remaining -= 1
        return ()
    visited: set[tuple[int, int]] = set()
    for _ in range(_MAX_INSTRUCTIONS_PER_UPDATE):
        key = (vm.instruction_offset, vm.timer_elapsed)
        if key in visited:
            _fail(f"{source.identity} auxiliary loops within one update")
        visited.add(key)
        instruction = instructions.get(vm.instruction_offset)
        if instruction is None:
            _fail(f"{source.identity} auxiliary PC is outside static ECL")
        if instruction.time != vm.timer_elapsed:
            # Native timer_elapsed_eq dispatches only on exact equality.  A
            # future-dated PC waits while the ordinary VM timer advances.  A
            # stale PC can never regain equality under unit positive time, so
            # it is a permanently silent context until its owner replaces it
            # through opcode 0x87; retaining that replacement in the parent
            # source is sufficient.
            if instruction.time < vm.timer_elapsed:
                vm.stopped = True
            else:
                vm.timer_elapsed += 1
            return tuple(events)
        opcode = int(instruction.opcode)
        if not _eligible(instruction, difficulty_mask):
            vm.instruction_offset += int(instruction.size)
            continue
        if opcode == 0x04:
            if len(instruction.arguments) != 2:
                _fail("auxiliary jump argument layout drifted")
            vm.timer_elapsed = _signed_u32(int(instruction.arguments[0]))
            vm.instruction_offset += _signed_u32(
                int(instruction.arguments[1])
            )
            continue
        if opcode == 0x05:
            if len(instruction.arguments) != 3:
                _fail("auxiliary loop-jump argument layout drifted")
            values, destination = _integer_lvalue(
                int(instruction.arguments[2]),
                vm,
            )
            values[destination] -= 1
            loop_value = _eval_integer_operand(
                int(instruction.arguments[2]),
                dynamic=bool(instruction.parameter_mask & 0x04),
                vm=vm,
            )
            if loop_value > 0:
                vm.timer_elapsed = _signed_u32(
                    int(instruction.arguments[0])
                )
                vm.instruction_offset += _signed_u32(
                    int(instruction.arguments[1])
                )
                continue
            vm.instruction_offset += int(instruction.size)
            continue
        if opcode == 0x02:
            if len(instruction.arguments) != 1:
                _fail("auxiliary timer reset argument layout drifted")
            reset_value = _eval_integer_operand(
                int(instruction.arguments[0]),
                dynamic=bool(instruction.parameter_mask & 1),
                vm=vm,
            )
            vm.instruction_offset += int(instruction.size)
            if reset_value > 0:
                # Opcode 0x02 writes the independent +0x90 delay timer.  The
                # scheduler immediately revisits its gate in this update and
                # consumes the first tick before publishing the next root.
                vm.delay_remaining = reset_value - 1
                return tuple(events)
            continue
        if opcode == 0x06:
            if len(instruction.arguments) != 2:
                _fail("auxiliary integer assignment argument layout drifted")
            values, destination = _integer_lvalue(
                int(instruction.arguments[0]),
                vm,
            )
            values[destination] = _eval_integer_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
            )
        elif opcode == 0x07:
            if len(instruction.arguments) != 2:
                _fail("auxiliary float assignment argument layout drifted")
            destination = _float_lvalue(int(instruction.arguments[0]))
            vm.float_locals[destination] = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            vm.float_local_aim_coefficients[destination] = (
                _float_operand_aim_coefficient(
                    int(instruction.arguments[1]),
                    dynamic=bool(instruction.parameter_mask & 0x02),
                    vm=vm,
                )
            )
        elif opcode == 0x1B:
            if len(instruction.arguments) != 3:
                _fail("auxiliary multiply argument layout drifted")
            destination = _float_lvalue(int(instruction.arguments[0]))
            left = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            right = _eval_float_operand(
                int(instruction.arguments[2]),
                dynamic=bool(instruction.parameter_mask & 0x04),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            vm.float_locals[destination] = left.multiply(right)
            vm.float_local_aim_coefficients[destination] = (
                _scaled_affine_coefficient(
                    left,
                    _float_operand_aim_coefficient(
                        int(instruction.arguments[1]),
                        dynamic=bool(instruction.parameter_mask & 0x02),
                        vm=vm,
                    ),
                    right,
                    _float_operand_aim_coefficient(
                        int(instruction.arguments[2]),
                        dynamic=bool(instruction.parameter_mask & 0x04),
                        vm=vm,
                    ),
                )
            )
        elif opcode in (0x19, 0x1A):
            _apply_float_binary(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode == 0x25:
            _normalize_float_lvalue_angle(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode == 0x0F:
            if len(instruction.arguments) != 2:
                _fail("auxiliary add argument layout drifted")
            destination = _float_lvalue(int(instruction.arguments[0]))
            value = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            vm.float_locals[destination] = (
                vm.float_locals[destination].add(value)
            )
            current_coefficient = vm.float_local_aim_coefficients[
                destination
            ]
            value_coefficient = _float_operand_aim_coefficient(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
            )
            vm.float_local_aim_coefficients[destination] = (
                None
                if (
                    current_coefficient is None
                    or value_coefficient is None
                )
                else current_coefficient + value_coefficient
            )
        elif opcode == 0x2E:
            if len(instruction.arguments) != 4:
                _fail("auxiliary integer-LE jump layout drifted")
            left = _eval_integer_operand(
                int(instruction.arguments[0]),
                dynamic=bool(instruction.parameter_mask & 0x01),
                vm=vm,
            )
            right = _eval_integer_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
            )
            if left <= right:
                vm.timer_elapsed = _signed_u32(
                    int(instruction.arguments[2])
                )
                vm.instruction_offset += _signed_u32(
                    int(instruction.arguments[3])
                )
                continue
        elif opcode == 0x35:
            # Captured auxiliary contexts with a saved frame are rejected at
            # the observation join. Native return pre-decrements depth, so a
            # reached return at the retained depth zero terminates this VM.
            vm.stopped = True
            return tuple(events)
        elif opcode == 0x6F:
            _define_bullet_transform(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode in _DIRECT_FIRE_OPCODES:
            events.extend(
                _direct_fire_events(
                    source=source,
                    instruction=instruction,
                    vm=vm,
                    frame=frame,
                    aim_angle=aim_angle,
                    payload=payload,
                )
            )
        else:
            _fail(
                f"{source.identity} auxiliary reaches unsupported opcode "
                f"{opcode:#x} at {instruction.offset:#x}"
            )
        vm.instruction_offset += int(instruction.size)
    _fail(f"{source.identity} auxiliary exceeded its instruction bound")
    return ()


def _subroutine_start(ecl: EclFile, subroutine_index: int) -> int:
    if not 0 <= subroutine_index < len(ecl.subroutines):
        _fail(f"ECL subroutine {subroutine_index} is out of range")
    instructions = ecl.subroutines[subroutine_index].instructions
    if not instructions:
        _fail(f"ECL subroutine {subroutine_index} is empty")
    return int(instructions[0].offset)


def _clone_vm(vm: _VmState) -> _VmState:
    return _VmState(
        instruction_offset=vm.instruction_offset,
        timer_elapsed=vm.timer_elapsed,
        integer_locals=list(vm.integer_locals),
        float_locals=list(vm.float_locals),
        scratch_integers=list(vm.scratch_integers),
        stopped=vm.stopped,
        delay_remaining=vm.delay_remaining,
        float_local_aim_coefficients=list(
            vm.float_local_aim_coefficients
        ),
    )


def _start_auxiliary(
    *,
    source: _SourceState,
    instruction: SubInstruction,
    ecl: EclFile,
) -> None:
    if len(instruction.arguments) != 2:
        _fail("start auxiliary argument layout drifted")
    slot = _literal_integer(instruction, 0)
    subroutine = _literal_integer(instruction, 1)
    if not 0 <= slot < _AUXILIARY_SLOT_COUNT:
        _fail(f"auxiliary slot {slot} is out of range")
    if subroutine < 0:
        source.auxiliaries[slot] = None
        return
    # Native 0x87 allocates a zeroed context, starts the selected subroutine,
    # then copies the parent VM local block into the new active VM.
    vm = _clone_vm(source.main)
    vm.instruction_offset = _subroutine_start(ecl, subroutine)
    vm.timer_elapsed = 0
    vm.stopped = False
    source.auxiliaries[slot] = vm


def _apply_enemy_flag_opcode(
    source: _SourceState,
    instruction: SubInstruction,
) -> None:
    if len(instruction.arguments) != 1:
        _fail("enemy flag opcode argument layout drifted")
    value = _literal_integer(instruction, 0)
    opcode = int(instruction.opcode)
    if opcode == 0x4F:
        mappings = (
            (0x01, 0x40, False),
            (0x02, 0x04, False),
            (0x04, 0x08, False),
            (0x08, 0x10, True),
            (0x10, 0x10000000, True),
        )
        for input_bit, flag_bit, direct in mappings:
            enabled = bool(value & input_bit)
            if not direct:
                enabled = not enabled
            if enabled:
                source.enemy_flags |= flag_bit
            else:
                source.enemy_flags &= ~flag_bit
        return
    mappings = (
        (0x01, 0x40),
        (0x02, 0x04),
        (0x04, 0x08),
        (0x08, 0x10),
        (0x10, 0x10000000),
    )
    for input_bit, flag_bit in mappings:
        if not value & input_bit:
            continue
        if opcode == 0x50:
            # Native "clear flags" inverts the last two behavior flags.
            if input_bit in (0x08, 0x10):
                source.enemy_flags |= flag_bit
            else:
                source.enemy_flags &= ~flag_bit
        elif opcode == 0x51:
            if input_bit in (0x08, 0x10):
                source.enemy_flags &= ~flag_bit
            else:
                source.enemy_flags |= flag_bit
        else:
            raise AssertionError("unexpected enemy flag opcode")


def _install_timed_polar_motion(
    *,
    source: _SourceState,
    instruction: SubInstruction,
    aim_angle: FloatInterval,
) -> None:
    if len(instruction.arguments) != 4:
        _fail("timed polar movement argument layout drifted")
    duration = _literal_integer(instruction, 0)
    mode = _literal_integer(instruction, 1)
    if duration <= 0 or not 0 <= mode <= 6:
        _fail("timed polar movement duration/mode is unsupported")
    if (
        abs(source.motion.relative_x) > 1e-6
        or abs(source.motion.relative_y) > 1e-6
    ):
        _fail(
            "timed polar movement with a pre-existing relative offset "
            "is unsupported"
        )
    angle = _eval_float_operand(
        int(instruction.arguments[2]),
        dynamic=bool(instruction.parameter_mask & 0x04),
        vm=source.main,
        aim_angle=aim_angle,
        source=source,
    )
    speed = _eval_float_operand(
        int(instruction.arguments[3]),
        dynamic=bool(instruction.parameter_mask & 0x08),
        vm=source.main,
        aim_angle=aim_angle,
        source=source,
    )
    if angle.lower != angle.upper or speed.lower != speed.upper:
        _fail("timed polar movement requires point angle and speed")
    start_x = (
        source.precompose_world_x
        if source.precompose_world_x is not None
        else source.motion.world_x_interval
    )
    start_y = (
        source.precompose_world_y
        if source.precompose_world_y is not None
        else source.motion.world_y_interval
    )
    displacement_x = math.cos(angle.lower) * speed.lower * duration
    if source.motion.mirror_x:
        displacement_x = -displacement_x
    displacement_y = math.sin(angle.lower) * speed.lower * duration
    motion = source.motion
    motion.movement_state = 2
    motion.supported = True
    motion.timed_duration = duration
    motion.timed_remaining = duration
    motion.timed_fraction = 0.0
    motion.timed_mode = mode
    motion.timed_start_x = 0.5 * (start_x.lower + start_x.upper)
    motion.timed_start_y = 0.5 * (start_y.lower + start_y.upper)
    motion.timed_displacement_x = displacement_x
    motion.timed_displacement_y = displacement_y
    motion.uncertainty_x = 0.5 * (start_x.upper - start_x.lower)
    motion.uncertainty_y = 0.5 * (start_y.upper - start_y.lower)


def _execute_main(
    *,
    source: _SourceState,
    instructions: dict[int, SubInstruction],
    difficulty_mask: int,
    frame: int,
    aim_angle: FloatInterval,
    payload: dict[str, object],
    ecl: EclFile,
    remaining_horizon: int,
) -> tuple[tuple[FutureDirectFire, ...], int]:
    vm = source.main
    if vm.stopped:
        return (), 0
    events: list[FutureDirectFire] = []
    silent_children = 0
    visited: set[tuple[int, int]] = set()
    for _ in range(_MAX_INSTRUCTIONS_PER_UPDATE):
        key = (vm.instruction_offset, vm.timer_elapsed)
        if key in visited:
            _fail(f"{source.identity} main loops within one update")
        visited.add(key)
        instruction = instructions.get(vm.instruction_offset)
        if instruction is None:
            _fail(f"{source.identity} main PC is outside static ECL")
        if instruction.time > vm.timer_elapsed:
            break
        if instruction.time < vm.timer_elapsed:
            _fail(f"{source.identity} main PC is behind its timer")
        opcode = int(instruction.opcode)
        if not _eligible(instruction, difficulty_mask):
            vm.instruction_offset += int(instruction.size)
            continue
        if opcode == 0x01:
            vm.stopped = True
            break
        if opcode == 0x04:
            if len(instruction.arguments) != 2:
                _fail("main jump argument layout drifted")
            if instruction.parameter_mask:
                _fail("main jump has dynamic operands")
            vm.timer_elapsed = _signed_u32(
                int(instruction.arguments[0])
            )
            vm.instruction_offset += _signed_u32(
                int(instruction.arguments[1])
            )
            continue
        if opcode == 0x05:
            if len(instruction.arguments) != 3:
                _fail("main loop-jump argument layout drifted")
            values, destination = _integer_lvalue(
                int(instruction.arguments[2]),
                vm,
            )
            values[destination] -= 1
            loop_value = _eval_integer_operand(
                int(instruction.arguments[2]),
                dynamic=bool(instruction.parameter_mask & 0x04),
                vm=vm,
            )
            if loop_value > 0:
                vm.timer_elapsed = _signed_u32(
                    int(instruction.arguments[0])
                )
                vm.instruction_offset += _signed_u32(
                    int(instruction.arguments[1])
                )
                continue
            vm.instruction_offset += int(instruction.size)
            continue
        if opcode in (0x00, 0x03, 0x36, 0x39, 0x7C):
            pass
        elif opcode == 0x06:
            if len(instruction.arguments) != 2:
                _fail("main integer assignment argument layout drifted")
            values, destination = _integer_lvalue(
                int(instruction.arguments[0]),
                vm,
            )
            values[destination] = _eval_integer_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
            )
        elif opcode == 0x07:
            if len(instruction.arguments) != 2:
                _fail("main float assignment argument layout drifted")
            destination = _float_lvalue(int(instruction.arguments[0]))
            vm.float_locals[destination] = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            vm.float_local_aim_coefficients[destination] = (
                _float_operand_aim_coefficient(
                    int(instruction.arguments[1]),
                    dynamic=bool(instruction.parameter_mask & 0x02),
                    vm=vm,
                )
            )
        elif opcode in (0x19, 0x1A):
            _apply_float_binary(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode == 0x25:
            _normalize_float_lvalue_angle(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode == 0x41:
            if len(instruction.arguments) != 2:
                _fail("set_velocity_polar argument layout drifted")
            source.motion.angle = _literal_float(instruction, 0)
            source.motion.speed = _literal_float(instruction, 1)
            source.motion.movement_state = 1
            source.motion.supported = True
            source.motion.timed_duration = 0
            source.motion.timed_remaining = 0
        elif opcode == 0x42:
            _install_timed_polar_motion(
                source=source,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode == 0x47:
            if len(instruction.arguments) != 1:
                _fail("set_speed_acceleration argument layout drifted")
            source.motion.speed_acceleration = _literal_float(instruction, 0)
        elif opcode == 0x4A:
            if len(instruction.arguments) != 3:
                _fail("set orbit motion argument layout drifted")
            duration = _literal_integer(instruction, 0)
            if duration <= 0:
                _fail("set orbit motion duration is nonpositive")
            angular_velocity = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            radius_acceleration = _eval_float_operand(
                int(instruction.arguments[2]),
                dynamic=bool(instruction.parameter_mask & 0x04),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            if (
                angular_velocity.lower != angular_velocity.upper
                or radius_acceleration.lower != radius_acceleration.upper
            ):
                _fail("set orbit motion requires point-valued parameters")
            source.motion.orbit_angular_velocity = (
                angular_velocity.lower
            )
            source.motion.orbit_radius_acceleration = (
                radius_acceleration.lower
            )
            source.motion.motion_duration = duration
            source.motion.motion_timer_elapsed = duration
            source.motion.movement_state = 3
            source.motion.supported = True
        elif opcode == 0x4D:
            if len(instruction.arguments) != 2:
                _fail("set hitbox argument layout drifted")
            width = _eval_float_operand(
                int(instruction.arguments[0]),
                dynamic=bool(instruction.parameter_mask & 0x01),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            height = _eval_float_operand(
                int(instruction.arguments[1]),
                dynamic=bool(instruction.parameter_mask & 0x02),
                vm=vm,
                aim_angle=aim_angle,
                source=source,
            )
            if width.lower < 0.0 or height.lower < 0.0:
                _fail("enemy hitbox interval crosses negative")
            source.body_half_width = enemy_contact_size_to_lethal_half_extent(
                width.upper
            )
            source.body_half_height = enemy_contact_size_to_lethal_half_extent(
                height.upper
            )
        elif opcode in (0x4F, 0x50, 0x51):
            _apply_enemy_flag_opcode(source, instruction)
        elif opcode == 0x5C:
            if len(instruction.arguments) != 6:
                _fail("0x5C child-spawn argument layout drifted")
            child_subroutine = _signed_u32(int(instruction.arguments[0]))
            _prove_child_silent(
                ecl,
                subroutine_index=child_subroutine,
                remaining_horizon=remaining_horizon,
            )
            silent_children += 1
        elif opcode == 0x6F:
            _define_bullet_transform(
                source=source,
                vm=vm,
                instruction=instruction,
                aim_angle=aim_angle,
            )
        elif opcode in _DIRECT_FIRE_OPCODES:
            events.extend(
                _direct_fire_events(
                    source=source,
                    instruction=instruction,
                    vm=vm,
                    frame=frame,
                    aim_angle=aim_angle,
                    payload=payload,
                )
            )
        elif opcode == 0x87:
            _start_auxiliary(
                source=source,
                instruction=instruction,
                ecl=ecl,
            )
        elif opcode == 0x8B:
            if len(instruction.arguments) != 3:
                _fail("spawn effect argument layout drifted")
            effect_type = _literal_integer(instruction, 0)
            effect_count = _literal_integer(instruction, 1)
            _literal_integer(instruction, 2)
            if effect_type not in _HOSTILITY_NEUTRAL_EFFECT_TYPES:
                _fail(
                    f"{source.identity} reaches unaudited effect type "
                    f"{effect_type}"
                )
            if not 1 <= effect_count <= 512:
                _fail(
                    f"{source.identity} effect count is outside the "
                    "audited pool bound"
                )
        elif opcode == 0xA0:
            if len(instruction.arguments) != 1:
                _fail("phase timer assignment argument layout drifted")
            if source.phase_transition_armed:
                _fail(
                    f"{source.identity} phase timer write can reach an "
                    "unlowered successor source"
                )
        else:
            _fail(
                f"{source.identity} main reaches unsupported opcode "
                f"{opcode:#x} at {instruction.offset:#x}"
            )
        vm.instruction_offset += int(instruction.size)
    else:
        _fail(f"{source.identity} main exceeded its instruction bound")
    if not vm.stopped:
        vm.timer_elapsed += 1
    return tuple(events), silent_children


def _advance_motion(source: _SourceState) -> None:
    motion = source.motion
    if not motion.supported:
        if any(auxiliary is not None for auxiliary in source.auxiliaries):
            _fail(
                f"{source.identity} active auxiliary uses unsupported "
                f"movement state {motion.movement_state}"
            )
        source.precompose_origin_x = None
        source.precompose_origin_y = None
        source.precompose_world_x = None
        source.precompose_world_y = None
        return
    if motion.movement_state == 0:
        motion.velocity_x = 0.0
        motion.velocity_y = 0.0
        source.precompose_origin_x = None
        source.precompose_origin_y = None
        source.precompose_world_x = None
        source.precompose_world_y = None
        return
    if motion.movement_state == 2:
        if motion.timed_duration <= 0 or motion.timed_remaining <= 0:
            _fail(f"{source.identity} timed movement state is malformed")
        motion.timed_remaining -= 1
        progress = 1.0 - (
            (float(motion.timed_remaining) + motion.timed_fraction)
            / float(motion.timed_duration)
        )
        progress = max(0.0, progress)
        if motion.timed_mode == 1:
            eased = progress * progress
        elif motion.timed_mode == 2:
            eased = progress * progress * progress
        elif motion.timed_mode == 3:
            eased = progress * progress * progress * progress
        elif motion.timed_mode == 4:
            eased = 1.0 - (1.0 - progress) ** 2
        elif motion.timed_mode == 5:
            eased = 1.0 - (1.0 - progress) ** 3
        elif motion.timed_mode == 6:
            eased = 1.0 - (1.0 - progress) ** 4
        else:
            eased = progress
        desired_x = (
            motion.timed_start_x
            + motion.timed_displacement_x * eased
        )
        desired_y = (
            motion.timed_start_y
            + motion.timed_displacement_y * eased
        )
        motion.velocity_x = desired_x - motion.base_x
        motion.velocity_y = desired_y - motion.base_y
        motion.base_x = desired_x
        motion.base_y = desired_y
        if motion.timed_remaining <= 0:
            # Native expiry tests only the integer timer component and snaps
            # to the exact endpoint even when a retained fraction made the
            # intermediate eased point incomplete.
            motion.base_x = (
                motion.timed_start_x + motion.timed_displacement_x
            )
            motion.base_y = (
                motion.timed_start_y + motion.timed_displacement_y
            )
            motion.movement_state = 0
            motion.velocity_x = 0.0
            motion.velocity_y = 0.0
        source.precompose_origin_x = None
        source.precompose_origin_y = None
        source.precompose_world_x = None
        source.precompose_world_y = None
        return
    if motion.movement_state == 3:
        motion.orbit_angle += motion.orbit_angular_velocity
        motion.orbit_radius += motion.orbit_radius_acceleration
        if not all(
            math.isfinite(value)
            for value in (motion.orbit_angle, motion.orbit_radius)
        ):
            _fail(f"{source.identity} orbit motion became non-finite")
        motion.velocity_x = (
            motion.orbit_center_x
            + math.cos(motion.orbit_angle) * motion.orbit_radius
            - motion.base_x
        )
        motion.velocity_y = (
            motion.orbit_center_y
            + math.sin(motion.orbit_angle) * motion.orbit_radius
            - motion.base_y
        )
        motion.base_x += motion.velocity_x
        motion.base_y += motion.velocity_y
        if motion.motion_duration > 0:
            motion.motion_timer_elapsed -= 1
            if motion.motion_timer_elapsed <= 0:
                motion.movement_state = 0
                motion.velocity_x = 0.0
                motion.velocity_y = 0.0
        source.precompose_origin_x = None
        source.precompose_origin_y = None
        source.precompose_world_x = None
        source.precompose_world_y = None
        return
    motion.angle += motion.angular_velocity
    motion.speed += motion.speed_acceleration
    if not all(math.isfinite(value) for value in (motion.angle, motion.speed)):
        _fail(f"{source.identity} motion became non-finite")
    velocity_x = math.cos(motion.angle) * motion.speed
    if motion.mirror_x:
        velocity_x = -velocity_x
    motion.velocity_x = velocity_x
    motion.velocity_y = math.sin(motion.angle) * motion.speed
    motion.base_x += motion.velocity_x
    motion.base_y += motion.velocity_y
    source.precompose_origin_x = None
    source.precompose_origin_y = None
    source.precompose_world_x = None
    source.precompose_world_y = None


def _timeline_root(
    payload: dict[str, object],
    ecl: EclFile,
) -> tuple[StageTimelineState, TimelineExternalState, int]:
    runtime = payload["stage_timeline_runtime"]
    assert isinstance(runtime, dict)
    rows = _rows(runtime, label="stage timeline runtime")
    if len(rows) != len(ecl.timelines):
        _fail("timeline runtime/program count mismatch")
    clocks: list[TimelineClock] = []
    for timeline, raw_row in zip(ecl.timelines, rows, strict=True):
        if not isinstance(raw_row, dict):
            _fail("timeline runtime row is malformed")
        current = raw_row.get("current_instruction")
        if not isinstance(current, dict):
            _fail("timeline current instruction is absent")
        current_offset = int(current["static_offset"])
        index = next(
            (
                candidate
                for candidate, instruction in enumerate(timeline.instructions)
                if instruction.offset == current_offset
            ),
            None,
        )
        if index is None:
            _fail(f"timeline {timeline.index} PC is not static ECL")
        try:
            timer = Th08TimerState(
                elapsed=int(raw_row["elapsed"]),
                fraction_bits=int(raw_row.get("fraction_bits", -1)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            _fail(f"timeline {timeline.index} timer is not finite: {exc}")
        # _analyze has already required exact unit time scale.  The native
        # fast path at 0x00447421 increments the integer component and
        # preserves the fraction verbatim, while timeline dispatch observes
        # only the integer component.  The finite fraction is therefore
        # causally inert in this reduced unit-scale clock, not UNKNOWN state.
        clocks.append(
            TimelineClock(
                instruction_index=index,
                elapsed=timer.elapsed,
                stopped=bool(current.get("terminal")),
            )
        )
    external_record = runtime.get("external")
    if not isinstance(external_record, dict):
        _fail("timeline external state is absent")
    indexed: list[IndexedEnemyView | None] = []
    for row in external_record.get("indexed_enemies", []):
        if row is None:
            indexed.append(None)
        elif isinstance(row, dict) and "field_2d30" in row:
            indexed.append(
                IndexedEnemyView(
                    active=bool(row.get("active")),
                    field_2d30=int(row["field_2d30"]),
                )
            )
        else:
            _fail("non-null indexed enemy lacks its timeline-visible state")
    if len(indexed) != 8:
        _fail("timeline indexed-enemy registry layout drifted")
    compact = payload.get("compact_state")
    if not isinstance(compact, dict):
        _fail("compact RNG root is absent")
    state = StageTimelineState(
        clocks=tuple(clocks),
        markers=tuple(
            int(value) for value in external_record.get("markers", [])
        ),
        rng_state=int(compact["rng_state"]),
        rng_calls=int(compact["rng_calls"]),
        stage_flag_10=bool(runtime.get("stage_flag_10")),
    )
    external = TimelineExternalState(
        stage_transition_busy=bool(
            external_record.get("stage_transition_busy")
        ),
        spawn_suppressed=bool(external_record.get("spawn_suppressed")),
        conditional_gate_blocked=bool(
            external_record.get("conditional_gate_blocked")
        ),
        indexed_enemies=tuple(indexed),
    )
    return state, external, int(runtime["difficulty_mask"])


def _timeline_external_variants(
    root: TimelineExternalState,
) -> tuple[TimelineExternalState, ...]:
    active_indices = tuple(
        index
        for index, enemy in enumerate(root.indexed_enemies)
        if enemy is not None and enemy.active
    )
    conditional_values = (
        (False, True) if root.conditional_gate_blocked else (False,)
    )
    variants: list[TimelineExternalState] = []
    for conditional, active_values in product(
        conditional_values,
        product((False, True), repeat=len(active_indices)),
    ):
        indexed = list(root.indexed_enemies)
        for index, active in zip(
            active_indices,
            active_values,
            strict=True,
        ):
            enemy = indexed[index]
            assert enemy is not None
            indexed[index] = replace(enemy, active=active)
        variants.append(
            TimelineExternalState(
                # Both native spawn gates consume the same due record.  The
                # false branch is therefore hazard-maximal: it includes every
                # spawn that a currently-busy/suppressed root could omit, and
                # no omitted record can be replayed after the gate clears.
                stage_transition_busy=False,
                spawn_suppressed=False,
                # A blocked opcode 0x07 holds both its clock and PC. Applying
                # both values independently at every projected update covers
                # every possible message-release frame before future events.
                conditional_gate_blocked=conditional,
                indexed_enemies=tuple(indexed),
            )
        )
    return tuple(variants)


def _canonical_timeline_state(state: StageTimelineState) -> StageTimelineState:
    # Gameplay RNG affects only randomized spawn X in the timeline scheduler.
    # Spawn X is separately lifted to its whole static ECL interval, so carrying
    # branch-specific RNG values would prevent a sound observation merge.
    return replace(state, rng_state=0, rng_calls=0)


def _normalized_spawn(spawn: TimelineSpawnRequest) -> TimelineSpawnRequest:
    minimum_x = spawn.x if spawn.minimum_x is None else spawn.minimum_x
    maximum_x = spawn.x if spawn.maximum_x is None else spawn.maximum_x
    if not (
        math.isfinite(minimum_x)
        and math.isfinite(maximum_x)
        and minimum_x <= maximum_x
    ):
        _fail("timeline spawn X interval is malformed")
    return replace(
        spawn,
        x=0.5 * (minimum_x + maximum_x),
        minimum_x=minimum_x,
        maximum_x=maximum_x,
    )


def _lower_timeline_events(
    payload: dict[str, object],
    ecl: EclFile,
    *,
    horizon_frames: int,
) -> tuple[
    dict[int, tuple[TimelineSpawnRequest, ...]],
    int,
    str | None,
]:
    root_state, root_external, difficulty_mask = _timeline_root(payload, ecl)
    frontier = {_canonical_timeline_state(root_state)}
    external_variants = _timeline_external_variants(root_external)
    spawns_by_frame: dict[int, tuple[TimelineSpawnRequest, ...]] = {}
    for frame in range(1, horizon_frames + 1):
        next_frontier: set[StageTimelineState] = set()
        frame_spawns: dict[TimelineSpawnRequest, None] = {}
        try:
            for state in frontier:
                for external in external_variants:
                    step = step_stage_timelines(
                        ecl,
                        state,
                        active_difficulty_mask=difficulty_mask,
                        external=external,
                    )
                    if step.engine_events:
                        opcodes = sorted(
                            {event.opcode for event in step.engine_events}
                        )
                        _fail(
                            f"timeline reaches engine event(s) {opcodes} at "
                            f"future frame {frame}; event effects are not "
                            "lowered"
                        )
                    if step.field_writes:
                        _fail(
                            "timeline reaches indexed enemy field write at "
                            f"future frame {frame}; coupled enemy state is not "
                            "lowered"
                        )
                    for spawn in step.spawns:
                        frame_spawns[_normalized_spawn(spawn)] = None
                    next_frontier.add(_canonical_timeline_state(step.state))
            if len(next_frontier) > _MAX_TIMELINE_FRONTIER_STATES:
                _fail(
                    "set-valued timeline frontier exceeds deterministic bound "
                    f"{_MAX_TIMELINE_FRONTIER_STATES}"
                )
        except (
            FutureSourceClosureError,
            IndexError,
            RuntimeError,
            ValueError,
        ) as error:
            return (
                spawns_by_frame,
                frame - 1,
                f"timeline UNKNOWN begins at future frame {frame}: {error}",
            )
        frontier = next_frontier
        spawns_by_frame[frame] = tuple(frame_spawns)
    return spawns_by_frame, horizon_frames, None


def _timeline_source(
    *,
    template: _SourceState,
    spawn: TimelineSpawnRequest,
    frame: int,
    serial: int,
    ecl: EclFile,
) -> _SourceState:
    minimum_x = spawn.x if spawn.minimum_x is None else spawn.minimum_x
    maximum_x = spawn.x if spawn.maximum_x is None else spawn.maximum_x
    midpoint_x = 0.5 * (minimum_x + maximum_x)
    uncertainty_x = 0.5 * (maximum_x - minimum_x)
    motion = replace(
        template.motion,
        base_x=midpoint_x,
        base_y=float(spawn.y),
        uncertainty_x=uncertainty_x,
        uncertainty_y=0.0,
    )
    main = _clone_vm(template.main)
    main.instruction_offset = _subroutine_start(ecl, spawn.subroutine)
    main.timer_elapsed = 0
    main.stopped = False
    emission = deepcopy(template.emission)
    emission_offset = emission.get("emission_offset")
    if not isinstance(emission_offset, list) or len(emission_offset) != 3:
        _fail("timeline template emission offset is absent")
    precompose_origin_x = template.motion.world_x_interval.add(
        FloatInterval.point(float(emission_offset[0]))
    )
    precompose_origin_y = template.motion.world_y_interval.add(
        FloatInterval.point(float(emission_offset[1]))
    )
    return _SourceState(
        identity=(
            f"timeline:{frame}:{serial}:timeline{spawn.timeline_index}:"
            f"pc={spawn.instruction_offset:#x}:sub{spawn.subroutine}"
        ),
        enemy_pointer=-(serial + 1),
        motion=motion,
        main=main,
        auxiliaries=[
            _clone_vm(auxiliary) if auxiliary is not None else None
            for auxiliary in template.auxiliaries
        ],
        emission=emission,
        enemy_flags=template.enemy_flags,
        body_half_width=template.body_half_width,
        body_half_height=template.body_half_height,
        phase_transition_armed=template.phase_transition_armed,
        timeline_spawned=True,
        spawn_frame=frame,
        precompose_origin_x=precompose_origin_x,
        precompose_origin_y=precompose_origin_y,
        precompose_world_x=template.motion.world_x_interval,
        precompose_world_y=template.motion.world_y_interval,
    )


def _execute_source_update(
    *,
    source: _SourceState,
    frame: int,
    root_player_x: float,
    root_player_y: float,
    instructions: dict[int, SubInstruction],
    difficulty_mask: int,
    payload: dict[str, object],
    ecl: EclFile,
    remaining_horizon: int,
) -> tuple[tuple[FutureDirectFire, ...], int]:
    if source.precompose_origin_x is not None:
        aim_angle = FloatInterval(-math.pi, math.pi)
    else:
        aim_angle = _aim_interval(
            source_x=source.motion.world_x_interval,
            source_y=source.motion.world_y_interval,
            root_player_x=root_player_x,
            root_player_y=root_player_y,
            frame=frame,
        )
    main_events, child_count = _execute_main(
        source=source,
        instructions=instructions,
        difficulty_mask=difficulty_mask,
        frame=frame,
        aim_angle=aim_angle,
        payload=payload,
        ecl=ecl,
        remaining_horizon=remaining_horizon,
    )
    events = list(main_events)
    for auxiliary in source.auxiliaries:
        if auxiliary is None:
            continue
        events.extend(
            _execute_auxiliary(
                source=source,
                vm=auxiliary,
                instructions=instructions,
                difficulty_mask=difficulty_mask,
                frame=frame,
                aim_angle=aim_angle,
                payload=payload,
            )
        )
    return tuple(events), child_count


def _analyze(
    payload: dict[str, object],
    ecl: EclFile,
    *,
    horizon_frames: int,
) -> tuple[
    tuple[FutureDirectFire, ...],
    tuple[AabbTrajectoryHazard, ...],
    int,
    int,
    int,
    int,
    int,
    int,
    int | None,
    int,
    str | None,
]:
    if str(payload.get("schema")) != _PROJECTION_SCHEMA:
        _fail(
            f"future source closure requires {_PROJECTION_SCHEMA}, got "
            f"{payload.get('schema')!r}"
        )
    if horizon_frames < 0:
        _fail("future source horizon is negative")
    compact = payload.get("compact_state")
    if not isinstance(compact, dict):
        _fail("future source compact root is absent")
    if compact.get("spell_id") is not None:
        _fail("ordinary future source closure received an active spell")
    if int(compact.get("time_scale_bits", -1)) != _FLOAT32_ONE_BITS:
        _fail("future source closure currently requires exact unit time scale")
    player_x = float(compact["player_x"])
    player_y = float(compact["player_y"])
    _finite((player_x, player_y), label="future source player root")
    ecl_base, difficulty_mask = _runtime_program_identity(payload, ecl)
    (
        sources,
        auxiliary_count,
        health_transition_proven_count,
        health_transition_minimum_margin,
        projected_horizon_frames,
    ) = _build_sources(
        payload,
        ecl_base=ecl_base,
        horizon_frames=horizon_frames,
    )
    causal_prefix_reason = (
        (
            "health/timeout successor UNKNOWN begins after future frame "
            f"{projected_horizon_frames}"
        )
        if projected_horizon_frames < horizon_frames
        else None
    )
    (
        spawns_by_frame,
        timeline_steps,
        timeline_prefix_reason,
    ) = _lower_timeline_events(
        payload,
        ecl,
        horizon_frames=projected_horizon_frames,
    )
    if timeline_steps < projected_horizon_frames:
        projected_horizon_frames = timeline_steps
        causal_prefix_reason = timeline_prefix_reason
    if not sources:
        _fail("manager template source is absent")
    template = sources[0]
    instructions = _instruction_map(ecl)
    events: list[FutureDirectFire] = []
    future_body_samples: dict[str, list[AabbHazard | None]] = {
        source.identity: [
            _source_contact_body_sample(source),
            *([None] * projected_horizon_frames),
        ]
        for source in sources
    }
    silent_children = 0
    timeline_spawn_count = 0
    for frame in range(1, projected_horizon_frames + 1):
        event_count_before = len(events)
        source_count_before = len(sources)
        timeline_spawn_count_before = timeline_spawn_count
        silent_children_before = silent_children
        try:
            for spawn in spawns_by_frame.get(frame, ()):
                source = _timeline_source(
                    template=template,
                    spawn=spawn,
                    frame=frame,
                    serial=timeline_spawn_count,
                    ecl=ecl,
                )
                timeline_spawn_count += 1
                future_body_samples[source.identity] = [None] * (
                    projected_horizon_frames + 1
                )
                # Native timeline construction executes the new VM once;
                # the manager reaches the new slot and executes it again.
                bootstrap_events, child_count = _execute_source_update(
                    source=source,
                    frame=frame,
                    root_player_x=player_x,
                    root_player_y=player_y,
                    instructions=instructions,
                    difficulty_mask=difficulty_mask,
                    payload=payload,
                    ecl=ecl,
                    remaining_horizon=projected_horizon_frames - frame,
                )
                events.extend(bootstrap_events)
                silent_children += child_count
                sources.append(source)
            for source in sources:
                source_events, child_count = _execute_source_update(
                    source=source,
                    frame=frame,
                    root_player_x=player_x,
                    root_player_y=player_y,
                    instructions=instructions,
                    difficulty_mask=difficulty_mask,
                    payload=payload,
                    ecl=ecl,
                    remaining_horizon=projected_horizon_frames - frame,
                )
                events.extend(source_events)
                silent_children += child_count
                _advance_motion(source)
                future_body_samples[source.identity][frame] = (
                    _source_contact_body_sample(source)
                )
        except (
            FutureSourceClosureError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            del events[event_count_before:]
            del sources[source_count_before:]
            timeline_spawn_count = timeline_spawn_count_before
            silent_children = silent_children_before
            projected_horizon_frames = frame - 1
            causal_prefix_reason = (
                f"source UNKNOWN begins at future frame {frame}: {error}"
            )
            break
    body_trajectories = tuple(
        AabbTrajectoryHazard(
            samples=tuple(samples[: projected_horizon_frames + 1])
        )
        for samples in future_body_samples.values()
        if any(
            sample is not None
            for sample in samples[: projected_horizon_frames + 1]
        )
    )
    auxiliary_count = sum(
        auxiliary is not None
        for source in sources
        for auxiliary in source.auxiliaries
    )
    return (
        tuple(events),
        body_trajectories,
        len(sources),
        auxiliary_count,
        silent_children,
        timeline_steps,
        timeline_spawn_count,
        health_transition_proven_count,
        health_transition_minimum_margin,
        projected_horizon_frames,
        causal_prefix_reason,
    )


def project_ordinary_future_sources(
    payload: dict[str, object],
    ecl: EclFile,
    *,
    horizon_frames: int,
) -> OrdinaryFutureSourceClosure:
    """Return complete consumed hazards or one fail-closed UNKNOWN slab."""

    compact = payload.get("compact_state")
    root_frame = (
        int(compact.get("manager_frame", 0))
        if isinstance(compact, dict)
        else 0
    )
    try:
        (
            events,
            aabb_trajectories,
            source_count,
            auxiliary_count,
            silent_child_count,
            timeline_steps,
            timeline_spawn_count,
            health_transition_proven_count,
            health_transition_minimum_margin,
            projected_horizon_frames,
            causal_prefix_reason,
        ) = _analyze(payload, ecl, horizon_frames=horizon_frames)
    except (FutureSourceClosureError, KeyError, TypeError, ValueError) as error:
        projection = unknown_future_hazard_projection(
            root_frame=root_frame,
            horizon_frames=horizon_frames,
            reason=str(error),
            source_semantics_version=(
                ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION
            ),
        )
        return OrdinaryFutureSourceClosure(
            projection=projection,
            direct_fire_events=(),
            source_count=0,
            auxiliary_count=0,
            silent_child_count=0,
            timeline_steps=0,
            timeline_spawn_count=0,
            health_transition_proven_count=0,
            health_transition_minimum_margin=None,
            causal_prefix_reason=None,
        )
    projection = complete_future_hazard_projection(
        root_frame=root_frame,
        horizon_frames=projected_horizon_frames,
        events=events,
        aabb_trajectories=aabb_trajectories,
        source_semantics_version=ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION,
    )
    return OrdinaryFutureSourceClosure(
        projection=projection,
        direct_fire_events=events,
        source_count=source_count,
        auxiliary_count=auxiliary_count,
        silent_child_count=silent_child_count,
        timeline_steps=timeline_steps,
        timeline_spawn_count=timeline_spawn_count,
        health_transition_proven_count=health_transition_proven_count,
        health_transition_minimum_margin=(
            health_transition_minimum_margin
        ),
        causal_prefix_reason=causal_prefix_reason,
    )


__all__ = [
    "ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION",
    "FutureSourceClosureError",
    "OrdinaryFutureSourceClosure",
    "project_ordinary_future_sources",
]
