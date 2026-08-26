"""Collision/control projection for TH08 native snapshot differentials.

This projection is deliberately narrower than a whole-process or whole-game
state identity.  It retains the native state that can explain a player hit:
input/RNG/clock state, hostile bullet and laser lifecycle state, enemy body
and ECL state, player collision state, and the route-2 option recurrence.
Renderer-owned ANM bytes remain visible in the broad native-root diagnostic
but do not decide collision/control equivalence.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from th08_bullet_template_contract import (
    BULLET_MANAGER_BASE,
    BULLET_TEMPLATE_COUNT,
    BULLET_TEMPLATE_STRIDE,
)
from th08_live.bullet_decode import BULLET_STATE_OFFSET, decode_bullets
from th08_live.enemy_ecl_inventory import (
    EnemyMainEclVmInventory,
    decode_enemy_main_ecl_vm_inventory,
)
from th08_live.enemy_sensor import (
    ENEMY_ACTIVE_FLAG,
    ENEMY_FLAGS_OFFSET,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
    PLAYER_LETHAL_AABB_OFFSET,
    PLAYER_LETHAL_AABB_SIZE,
    decode_enemy_bodies,
    decode_player_lethal_aabb,
)
from th08_live.hazard_decode import decode_lasers
from th08_runtime.auxiliary_ecl_state import (
    ACTIVE_VM_BYTES,
    AuxiliaryEclVmState,
    CONTEXT_ACTIVE_VM_OFFSET,
    CONTEXT_CALL_DEPTH_OFFSET,
    CONTEXT_TARGET_OFFSET,
    MAXIMUM_RESTORABLE_FRAMES,
)
from th08_live.models import serialize_bullet_trace
from th08_live.sensor import (
    BULLET_POOL_BASE,
    BULLET_POOL_SIZE,
    BULLET_STRIDE,
    LASER_POOL_BASE,
    LASER_POOL_SIZE,
    LASER_STRIDE,
)
from th08_ecl_runtime import EclInstructionCache, ENEMY_MAIN_ECL_VM_OFFSET
from th08_native_future_body_root import (
    TH08_ENEMY_MANAGER_TEMPLATE_BASE,
    TH08_TIMELINE_RUNTIME_BASE,
)
from th08_runtime.game_state import ADDR_PLAYER


COLLISION_CONTROL_PROJECTION_SCHEMA = (
    "th08-native-snapshot-collision-control-projection-v14"
)

# Revalidated in bullet_manager_update (0x00431240).  These two adjacent
# Th08Timer objects are advanced separately at the end of each active bullet
# update.  Keep offset-based names here: +0xD8C/+0xD94 is used as the
# collision-age gate, but the complete interpretation of both timers across
# every spawn/fade state is not yet claimed.
BULLET_TIMER_D80_OFFSET = 0x0D80
BULLET_TIMER_D8C_OFFSET = 0x0D8C
TH08_TIMER_FRACTION_OFFSET = 0x04
TH08_TIMER_ELAPSED_OFFSET = 0x08

# Native spawn-state motion before the ordinary state-1 update.  A finishing
# ANM VM can transition to state 1 in the same manager call, so these divisors
# alone are exact only while the spawn/fade state remains active.
BULLET_STATE_MOTION_DIVISORS = {
    1: 1.0,
    2: 2.0,
    3: 2.5,
    4: 3.0,
    5: 2.0,
}

# Revalidated native layout:
# - enemy main ECL VM begins at +0x7F8; render/ANM state is before it;
# - route-2 option records begin at player +0x40C, have stride 0x2F4,
#   and their update recurrence consumes/writes the +0x2A4..+0x2F4 tail.
ENEMY_ANM_PREFIX_SIZE = 0x7F8
ROUTE2_OPTION_BASE_OFFSET = 0x40C
ROUTE2_OPTION_COUNT = 4
ROUTE2_OPTION_STRIDE = 0x2F4
ROUTE2_OPTION_CAUSAL_TAIL_OFFSET = 0x2A4

# Revalidated in the ECL 0x60..0x68 handler (0x0041B4E6) and the periodic
# post-VM emitter (0x00423150).  An enemy may stage one exact 44-byte fire
# instruction, then emit it whenever its period timer reaches the configured
# interval after the main and auxiliary VMs have run.
ENEMY_HITPOINTS_OFFSET = 0x2DFC
ENEMY_MAX_HITPOINTS_OFFSET = 0x2E00
ENEMY_PHASE_START_HITPOINTS_OFFSET = 0x2E04
ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET = 0x3034
ENEMY_PERIODIC_EMISSION_DESCRIPTOR_SIZE = 0x2C
ENEMY_PERIODIC_EMISSION_PERIOD_OFFSET = 0x3060
ENEMY_PERIODIC_EMISSION_TIMER_OFFSET = 0x3064

# Revalidated in enemy_ecl_emit_bullets (0x00422720).  Direct fire adds this
# source-local vector to enemy+0x2D88, applies the four rank fields below in
# non-spell play, and copies the descriptor's 18x24-byte transform program to
# every allocated bullet.
ENEMY_EMISSION_OFFSET_OFFSET = 0x2DB8
ENEMY_RANK_SPEED_INTERVAL_OFFSET = 0x2DEC
ENEMY_RANK_COUNT_INTERVAL_OFFSET = 0x2DF4
ENEMY_EMISSION_DESCRIPTOR_OFFSET = 0x2E24
ENEMY_EMISSION_DESCRIPTOR_SIZE = 0x214
ENEMY_EMISSION_TRANSFORM_PROGRAM_OFFSET = 0x20
ENEMY_EMISSION_TRANSFORM_PROGRAM_SIZE = 18 * 24
ENEMY_MINIMUM_FIRE_DISTANCE_SQUARED_OFFSET = 0x3350
ENEMY_PHASE_TIMER_OFFSET = 0x2E14
ENEMY_HEALTH_TRANSITION_THRESHOLDS_OFFSET = 0x3358
ENEMY_HEALTH_TRANSITION_COUNT = 4
ENEMY_HEALTH_TRANSITION_SUCCESSORS_OFFSET = 0x3368
ENEMY_TIMEOUT_TRANSITION_FRAME_OFFSET = 0x3378
ENEMY_TIMEOUT_TRANSITION_SUBROUTINE_OFFSET = 0x337C

# Revalidated in enemy_ecl_vm_step (0x004184B0), enemy_motion_update
# (0x00422C40), and the internal-position integrator (0x0042DEB0).
# Direct fire observes the composed world position at +0x2D88 before the
# current update's motion integration.  The base position, relative offset,
# polar state, and velocity are all required to advance a future source
# without substituting the currently composed world derivative.
ENEMY_MOTION_BASE_POSITION_OFFSET = 0x2D34
ENEMY_MOTION_RELATIVE_POSITION_OFFSET = 0x2D40
ENEMY_MOTION_VELOCITY_OFFSET = 0x2D4C
ENEMY_MOTION_WORLD_POSITION_OFFSET = 0x2D88
ENEMY_MOTION_ANGLE_OFFSET = 0x2D94
ENEMY_MOTION_ANGULAR_VELOCITY_OFFSET = 0x2D98
ENEMY_MOTION_SPEED_OFFSET = 0x2DA8
ENEMY_MOTION_SPEED_ACCELERATION_OFFSET = 0x2DAC
ENEMY_MOTION_ORBIT_ANGLE_OFFSET = 0x2D9C
ENEMY_MOTION_ORBIT_ANGULAR_VELOCITY_OFFSET = 0x2DA0
ENEMY_MOTION_ORBIT_RADIUS_OFFSET = 0x2DB0
ENEMY_MOTION_ORBIT_RADIUS_ACCELERATION_OFFSET = 0x2DB4
# State 2 reads this displacement vector and the shared +0x2DD0 origin on
# every update (enemy_motion_update 0x00422F77..0x00422FAF). It cannot be
# reconstructed from the instantaneous +0x2D4C velocity.
ENEMY_MOTION_TIMED_DISPLACEMENT_OFFSET = 0x2DC4
ENEMY_MOTION_ORBIT_CENTER_OFFSET = 0x2DD0
ENEMY_MOTION_TIMER_OFFSET = 0x2DDC
ENEMY_MOTION_DURATION_OFFSET = 0x2DE8

# Revalidated in bullet_emitter_spawn_pattern (0x00430E10),
# bullet_spawn_from_emission_descriptor (0x0042F5F0), and the 21-iteration
# template initializer (0x00433070).  The descriptor's type selects one of
# the manager-owned templates; collision x/y are copied without a clamp into
# live bullet +0xD34/+0xD38.
BULLET_TEMPLATE_COLLISION_OFFSET = 0x0D34

_ENEMY_COMPONENT_NAMES = frozenset(
    {
        "ordinary_enemy_template_and_pool",
        "ordinary_enemy_ecl_and_callback_roots",
    }
)
_PLAYER_BROAD_COMPONENT_NAME = "player_state_through_resource_transitions"
_SCHEDULER_COMPONENT_NAME = "scheduler_gate_globals"
FRSCREEN_NOTIFICATION_COUNTERS_OFFSET = 0x04
FRSCREEN_NOTIFICATION_COUNTERS_SIZE = 0x04

# Revalidated in ecl_load_file (0x00418330), stage_timeline_step
# (0x0042A8A0), and enemy_manager_update (0x0042C660).  The file header is
# relocated in place: its timeline offsets and data-end sentinel are absolute
# process pointers after load.
ECL_FILE_CONTEXT_ADDRESS = 0x004ECCB8
ECL_FILE_HEADER_SIZE = 0x48
ECL_FILE_MAGIC = 0x800
ECL_MAXIMUM_TIMELINE_COUNT = 15
TIMELINE_RUNTIME_SLOT_COUNT = 16
TIMELINE_RUNTIME_SLOT_SIZE = 0x10
TIMELINE_RUNTIME_INSTRUCTION_POINTER_OFFSET = 0x0C
TIMELINE_MARKERS_ADDRESS = 0x00F54E1C
TIMELINE_SPAWN_SUPPRESSED_ADDRESS = 0x00F54E2C
INDEXED_ENEMY_REGISTRY_ADDRESS = 0x00F54CC0
INDEXED_ENEMY_REGISTRY_COUNT = 8
INDEXED_ENEMY_TIMELINE_FIELD_OFFSET = 0x2D30
FRSCREEN_STATE_ADDRESS = 0x0160F428
FRSCREEN_INNER_POINTER_OFFSET = 0x08
FRSCREEN_TIMELINE_SPAWN_GATE_OFFSET = 0x2C
FRSCREEN_INNER_MESSAGE_TIMER_OFFSET = 0x2181C
FRSCREEN_INNER_MESSAGE_OVERRIDE_OFFSET = 0x22D78
ECL_DIFFICULTY_MASK_ADDRESS = 0x0160F53C
STAGE_TIMELINE_FLAG_10_ADDRESS = 0x0164D0BB


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_digest(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return _sha256(payload)


def _read_exact(
    reader: Any,
    address: int,
    size: int,
    *,
    field: str,
) -> bytes:
    data = reader.read(address, size)
    if len(data) != size:
        raise ValueError(
            f"short {field} read at {address:#x}: "
            f"expected {size:#x}, received {len(data):#x}"
        )
    return data


def _enemy_causal_tail_digest(data: bytes) -> tuple[str, int]:
    if len(data) % ENEMY_STRIDE:
        raise ValueError("enemy native-root component is not record aligned")
    digest = hashlib.sha256()
    record_count = len(data) // ENEMY_STRIDE
    for record_index in range(record_count):
        base = record_index * ENEMY_STRIDE
        digest.update(data[base + ENEMY_ANM_PREFIX_SIZE : base + ENEMY_STRIDE])
    return digest.hexdigest(), record_count


def normalized_causal_component_records(
    components: Iterable[object],
) -> tuple[dict[str, object], ...]:
    """Normalize broad root components without hiding non-render state.

    Enemy records retain every byte from the revalidated main-ECL boundary
    onward.  The broad player component is replaced by explicit
    collision/control fields in :func:`capture_collision_control_projection`.
    Every other component remains byte-exact.
    """

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for component in components:
        spec = getattr(component, "spec")
        name = str(getattr(spec, "name"))
        data = bytes(getattr(component, "data"))
        if name in seen:
            raise ValueError(f"duplicate native-root component {name!r}")
        seen.add(name)
        if name == _PLAYER_BROAD_COMPONENT_NAME:
            records.append(
                {
                    "name": name,
                    "mode": "replaced_by_explicit_collision_control_fields",
                    "source_size": len(data),
                }
            )
            continue
        if name in _ENEMY_COMPONENT_NAMES:
            digest, record_count = _enemy_causal_tail_digest(data)
            records.append(
                {
                    "name": name,
                    "mode": "exact_per_record_tail_after_render_anm_prefix",
                    "source_size": len(data),
                    "record_count": record_count,
                    "retained_offset": ENEMY_ANM_PREFIX_SIZE,
                    "retained_bytes_per_record": (ENEMY_STRIDE - ENEMY_ANM_PREFIX_SIZE),
                    "sha256": digest,
                }
            )
            continue
        if name == _SCHEDULER_COMPONENT_NAME:
            excluded_end = (
                FRSCREEN_NOTIFICATION_COUNTERS_OFFSET
                + FRSCREEN_NOTIFICATION_COUNTERS_SIZE
            )
            if len(data) < excluded_end:
                raise ValueError("scheduler native-root component omits FRScreen flags")
            normalized = (
                data[:FRSCREEN_NOTIFICATION_COUNTERS_OFFSET] + data[excluded_end:]
            )
            records.append(
                {
                    "name": name,
                    "mode": (
                        "exact_except_render_consumed_frscreen_"
                        "resource_notification_counters"
                    ),
                    "source_size": len(data),
                    "excluded_offset": FRSCREEN_NOTIFICATION_COUNTERS_OFFSET,
                    "excluded_size": FRSCREEN_NOTIFICATION_COUNTERS_SIZE,
                    "sha256": _sha256(normalized),
                }
            )
            continue
        records.append(
            {
                "name": name,
                "mode": "exact",
                "source_size": len(data),
                "sha256": _sha256(data),
            }
        )
    return tuple(sorted(records, key=lambda record: str(record["name"])))


def _route2_option_causal_tails(reader: Any) -> tuple[str, ...]:
    tails: list[str] = []
    for option_index in range(ROUTE2_OPTION_COUNT):
        address = (
            ADDR_PLAYER
            + ROUTE2_OPTION_BASE_OFFSET
            + option_index * ROUTE2_OPTION_STRIDE
            + ROUTE2_OPTION_CAUSAL_TAIL_OFFSET
        )
        size = ROUTE2_OPTION_STRIDE - ROUTE2_OPTION_CAUSAL_TAIL_OFFSET
        tails.append(reader.read(address, size).hex())
    return tuple(tails)


def _player_lethal_aabb(reader: Any) -> list[float] | None:
    blob = reader.read(
        ADDR_PLAYER + PLAYER_LETHAL_AABB_OFFSET,
        PLAYER_LETHAL_AABB_SIZE,
    )
    decoded = decode_player_lethal_aabb(blob)
    return list(decoded) if decoded is not None else None


def _nearest_bullet_summary(
    bullets: tuple[object, ...],
    *,
    player_x: float,
    player_y: float,
    limit: int = 12,
) -> list[dict[str, object]]:
    ranked: list[tuple[float, object]] = []
    for bullet in bullets:
        dx = abs(float(getattr(bullet, "x")) - player_x) - float(
            getattr(bullet, "half_width")
        )
        dy = abs(float(getattr(bullet, "y")) - player_y) - float(
            getattr(bullet, "half_height")
        )
        signed_box_separation = max(dx, dy)
        ranked.append((signed_box_separation, bullet))
    ranked.sort(key=lambda item: (item[0], int(getattr(item[1], "slot"))))
    return [
        {
            "slot": int(getattr(bullet, "slot")),
            "signed_box_separation": separation,
            "x": float(getattr(bullet, "x")),
            "y": float(getattr(bullet, "y")),
            "vx": float(getattr(bullet, "vx")),
            "vy": float(getattr(bullet, "vy")),
            "half_width": float(getattr(bullet, "half_width")),
            "half_height": float(getattr(bullet, "half_height")),
            "transform_flags": int(getattr(bullet, "transform_flags")),
        }
        for separation, bullet in ranked[:limit]
    ]


def _bullet_lifecycle_records(
    bullet_blob: bytes | bytearray | memoryview,
    bullets: Iterable[object],
) -> list[dict[str, object]]:
    """Retain lifecycle fields omitted by the legacy geometry trace.

    The positional ``serialize_bullet_trace`` format predates native
    ModelTrajectory work and intentionally remains stable.  The separate
    slot-keyed ledger prevents spawn states 2..5 from being silently merged
    with ordinary state 1 merely because geometry/velocity/transform fields
    agree.
    """

    view = memoryview(bullet_blob)
    expected_size = BULLET_POOL_SIZE * BULLET_STRIDE
    if len(view) != expected_size:
        raise ValueError(
            "bullet lifecycle capture requires the complete native pool: "
            f"expected {expected_size} bytes, got {len(view)}"
        )
    records: list[dict[str, object]] = []
    for bullet in bullets:
        slot = int(getattr(bullet, "slot"))
        if not 0 <= slot < BULLET_POOL_SIZE:
            raise ValueError(f"decoded bullet slot is outside native pool: {slot}")
        base = slot * BULLET_STRIDE
        state = struct.unpack_from(
            "<H",
            view,
            base + BULLET_STATE_OFFSET,
        )[0]
        records.append(
            {
                "slot": slot,
                "state": int(state),
                "timer_d80_fraction_bits": struct.unpack_from(
                    "<I",
                    view,
                    base
                    + BULLET_TIMER_D80_OFFSET
                    + TH08_TIMER_FRACTION_OFFSET,
                )[0],
                "timer_d80_elapsed": struct.unpack_from(
                    "<i",
                    view,
                    base
                    + BULLET_TIMER_D80_OFFSET
                    + TH08_TIMER_ELAPSED_OFFSET,
                )[0],
                "timer_d8c_fraction_bits": struct.unpack_from(
                    "<I",
                    view,
                    base
                    + BULLET_TIMER_D8C_OFFSET
                    + TH08_TIMER_FRACTION_OFFSET,
                )[0],
                "timer_d8c_elapsed": struct.unpack_from(
                    "<i",
                    view,
                    base
                    + BULLET_TIMER_D8C_OFFSET
                    + TH08_TIMER_ELAPSED_OFFSET,
                )[0],
                "callback_phase_state": int(
                    getattr(bullet, "callback_phase_state", 0)
                ),
                "callback_aux_state": int(
                    getattr(bullet, "callback_aux_state", 0)
                ),
            }
        )
    return records


def _enemy_main_ecl_inventory_record(
    enemy_blob: bytes,
    *,
    pool_base: int = ENEMY_POOL_BASE,
    pool_size: int = ENEMY_POOL_SIZE,
    runtime_instruction_bounds: tuple[int, int] | None = None,
    maximum_runtime_address: int = 0x7FFFFFFF,
) -> tuple[EnemyMainEclVmInventory, dict[str, object]]:
    """Decode one deterministic active-enemy VM inventory.

    ``decode_ms`` is intentionally excluded from collision/control identity:
    it is observer timing, not native state.
    """

    inventory = decode_enemy_main_ecl_vm_inventory(
        enemy_blob,
        pool_base=pool_base,
        pool_size=pool_size,
        enemy_stride=ENEMY_STRIDE,
        enemy_flags_offset=ENEMY_FLAGS_OFFSET,
        enemy_active_flag=ENEMY_ACTIVE_FLAG,
        runtime_instruction_bounds=runtime_instruction_bounds,
        maximum_runtime_address=maximum_runtime_address,
    )
    record = inventory.record()
    record.pop("decode_ms", None)
    return inventory, record


def _enemy_source_record(
    reader: Any,
    *,
    enemy_blob: bytes,
    pool_base: int,
    pool_size: int,
    source_role: str,
    runtime_instruction_bounds: tuple[int, int] | None = None,
    maximum_runtime_address: int = 0x7FFFFFFF,
) -> dict[str, object]:
    """Decode every emission root for one contiguous enemy source range."""

    inventory, inventory_record = _enemy_main_ecl_inventory_record(
        enemy_blob,
        pool_base=pool_base,
        pool_size=pool_size,
        runtime_instruction_bounds=runtime_instruction_bounds,
        maximum_runtime_address=maximum_runtime_address,
    )
    bodies = decode_enemy_bodies(
        enemy_blob,
        pool_base=pool_base,
        pool_size=pool_size,
        include_contact_disabled=True,
    )
    return {
        "schema": "th08-enemy-hostile-source-range-v1",
        "source_role": source_role,
        "pool_base": pool_base,
        "pool_size": pool_size,
        "active": bool(inventory.observations),
        "enemy_bodies": [asdict(body) for body in bodies],
        "main_ecl_vm_inventory": inventory_record,
        "periodic_emission_state": _enemy_periodic_emission_records(
            enemy_blob,
            inventory,
        ),
        "main_ecl_installed_callbacks": _enemy_main_ecl_callback_records(
            reader,
            enemy_blob,
            inventory,
        ),
        "current_ecl_instructions": _enemy_current_instruction_records(
            reader,
            inventory,
        ),
        "emission_state": _enemy_emission_state_records(
            enemy_blob,
            inventory,
        ),
        "motion_state": _enemy_motion_state_records(
            enemy_blob,
            inventory,
        ),
        "phase_transition_state": _enemy_phase_transition_state_records(
            enemy_blob,
            inventory,
        ),
        "auxiliary_ecl_contexts": _enemy_auxiliary_ecl_context_records(
            reader,
            inventory,
            runtime_instruction_bounds=runtime_instruction_bounds,
        ),
    }


def _enemy_motion_state_records(
    enemy_blob: bytes,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        base = observation.slot * ENEMY_STRIDE
        rows.append(
            {
                "slot": observation.slot,
                "enemy_pointer": observation.enemy_pointer,
                "movement_state": (int(observation.enemy_flags) >> 12) & 3,
                "timed_mode": (int(observation.enemy_flags) >> 14) & 7,
                "mirror_x": bool(int(observation.enemy_flags) & 0x00040000),
                "base_position": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_BASE_POSITION_OFFSET,
                    )
                ),
                "relative_position": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_RELATIVE_POSITION_OFFSET,
                    )
                ),
                "velocity": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_VELOCITY_OFFSET,
                    )
                ),
                "world_position": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_WORLD_POSITION_OFFSET,
                    )
                ),
                "angle": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ANGLE_OFFSET,
                )[0],
                "angular_velocity": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ANGULAR_VELOCITY_OFFSET,
                )[0],
                "speed": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_SPEED_OFFSET,
                )[0],
                "speed_acceleration": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_SPEED_ACCELERATION_OFFSET,
                )[0],
                "orbit_angle": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ORBIT_ANGLE_OFFSET,
                )[0],
                "orbit_angular_velocity": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ORBIT_ANGULAR_VELOCITY_OFFSET,
                )[0],
                "orbit_radius": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ORBIT_RADIUS_OFFSET,
                )[0],
                "orbit_radius_acceleration": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MOTION_ORBIT_RADIUS_ACCELERATION_OFFSET,
                )[0],
                "timed_displacement": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_TIMED_DISPLACEMENT_OFFSET,
                    )
                ),
                "orbit_center_position": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_MOTION_ORBIT_CENTER_OFFSET,
                    )
                ),
                "motion_timer_elapsed": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base
                    + ENEMY_MOTION_TIMER_OFFSET
                    + TH08_TIMER_ELAPSED_OFFSET,
                )[0],
                "motion_timer_fraction_bits": struct.unpack_from(
                    "<I",
                    enemy_blob,
                    base
                    + ENEMY_MOTION_TIMER_OFFSET
                    + TH08_TIMER_FRACTION_OFFSET,
                )[0],
                "motion_duration": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_MOTION_DURATION_OFFSET,
                )[0],
            }
        )
    return {
        "schema": "th08-active-enemy-motion-state-v1",
        "scope": (
            "exact_preupdate_composed_world_base_relative_velocity_and_"
            "state1_polar_state3_orbit_timer_fields"
        ),
        "rows": rows,
    }


def _enemy_phase_transition_state_records(
    enemy_blob: bytes,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        base = observation.slot * ENEMY_STRIDE
        rows.append(
            {
                "slot": observation.slot,
                "enemy_pointer": observation.enemy_pointer,
                "current_hitpoints": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_HITPOINTS_OFFSET,
                )[0],
                "maximum_hitpoints": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_MAX_HITPOINTS_OFFSET,
                )[0],
                "phase_start_hitpoints": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_PHASE_START_HITPOINTS_OFFSET,
                )[0],
                "health_thresholds": list(
                    struct.unpack_from(
                        f"<{ENEMY_HEALTH_TRANSITION_COUNT}i",
                        enemy_blob,
                        base + ENEMY_HEALTH_TRANSITION_THRESHOLDS_OFFSET,
                    )
                ),
                "health_successor_subroutines": list(
                    struct.unpack_from(
                        f"<{ENEMY_HEALTH_TRANSITION_COUNT}i",
                        enemy_blob,
                        base + ENEMY_HEALTH_TRANSITION_SUCCESSORS_OFFSET,
                    )
                ),
                "phase_timer_previous": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_PHASE_TIMER_OFFSET,
                )[0],
                "phase_timer_fraction_bits": struct.unpack_from(
                    "<I",
                    enemy_blob,
                    base
                    + ENEMY_PHASE_TIMER_OFFSET
                    + TH08_TIMER_FRACTION_OFFSET,
                )[0],
                "phase_timer_elapsed": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base
                    + ENEMY_PHASE_TIMER_OFFSET
                    + TH08_TIMER_ELAPSED_OFFSET,
                )[0],
                "timeout_frame": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_TIMEOUT_TRANSITION_FRAME_OFFSET,
                )[0],
                "timeout_subroutine": struct.unpack_from(
                    "<i",
                    enemy_blob,
                    base + ENEMY_TIMEOUT_TRANSITION_SUBROUTINE_OFFSET,
                )[0],
            }
        )
    return {
        "schema": "th08-active-enemy-phase-transition-state-v1",
        "scope": (
            "exact_current_max_phase_start_health_threshold_successor_and_"
            "integer_phase_timer_timeout_registry_for_bounded_transition_"
            "reachability"
        ),
        "rows": rows,
    }


def _enemy_emission_state_records(
    enemy_blob: bytes,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        base = observation.slot * ENEMY_STRIDE
        descriptor_base = base + ENEMY_EMISSION_DESCRIPTOR_OFFSET
        descriptor = enemy_blob[
            descriptor_base :
            descriptor_base + ENEMY_EMISSION_DESCRIPTOR_SIZE
        ]
        if len(descriptor) != ENEMY_EMISSION_DESCRIPTOR_SIZE:
            raise ValueError("enemy emission descriptor is truncated")
        rows.append(
            {
                "slot": observation.slot,
                "enemy_pointer": observation.enemy_pointer,
                "emission_offset": list(
                    struct.unpack_from(
                        "<fff",
                        enemy_blob,
                        base + ENEMY_EMISSION_OFFSET_OFFSET,
                    )
                ),
                "rank_speed_interval": list(
                    struct.unpack_from(
                        "<ff",
                        enemy_blob,
                        base + ENEMY_RANK_SPEED_INTERVAL_OFFSET,
                    )
                ),
                "rank_count_interval": list(
                    struct.unpack_from(
                        "<hhhh",
                        enemy_blob,
                        base + ENEMY_RANK_COUNT_INTERVAL_OFFSET,
                    )
                ),
                "minimum_fire_distance_squared": struct.unpack_from(
                    "<f",
                    enemy_blob,
                    base + ENEMY_MINIMUM_FIRE_DISTANCE_SQUARED_OFFSET,
                )[0],
                "descriptor": {
                    "type": struct.unpack_from("<h", descriptor, 0x00)[0],
                    "color": struct.unpack_from("<h", descriptor, 0x02)[0],
                    "origin": list(struct.unpack_from("<fff", descriptor, 0x04)),
                    "angle1": struct.unpack_from("<f", descriptor, 0x10)[0],
                    "angle2": struct.unpack_from("<f", descriptor, 0x14)[0],
                    "speed1": struct.unpack_from("<f", descriptor, 0x18)[0],
                    "speed2": struct.unpack_from("<f", descriptor, 0x1C)[0],
                    "transform_program_hex": descriptor[
                        ENEMY_EMISSION_TRANSFORM_PROGRAM_OFFSET :
                        (
                            ENEMY_EMISSION_TRANSFORM_PROGRAM_OFFSET
                            + ENEMY_EMISSION_TRANSFORM_PROGRAM_SIZE
                        )
                    ].hex(),
                    "count1": struct.unpack_from("<h", descriptor, 0x1F4)[0],
                    "count2": struct.unpack_from("<h", descriptor, 0x1F6)[0],
                    "mode": struct.unpack_from("<h", descriptor, 0x1F8)[0],
                    "flags": struct.unpack_from("<I", descriptor, 0x1FC)[0],
                    "queue_cursor": struct.unpack_from(
                        "<I",
                        descriptor,
                        0x208,
                    )[0],
                    "template_pointer": struct.unpack_from(
                        "<I",
                        descriptor,
                        0x20C,
                    )[0],
                },
            }
        )
    return {
        "schema": "th08-active-enemy-emission-state-v1",
        "scope": (
            "exact_root_origin_rank_fields_current_descriptor_and_"
            "complete_transform_program"
        ),
        "rows": rows,
    }


def _bullet_template_geometry_record(reader: Any) -> dict[str, object]:
    blob = _read_exact(
        reader,
        BULLET_MANAGER_BASE,
        BULLET_TEMPLATE_COUNT * BULLET_TEMPLATE_STRIDE,
        field="bullet template table",
    )
    rows: list[dict[str, object]] = []
    for template_type in range(BULLET_TEMPLATE_COUNT):
        base = (
            template_type * BULLET_TEMPLATE_STRIDE
            + BULLET_TEMPLATE_COLLISION_OFFSET
        )
        width, height, collision_z = struct.unpack_from(
            "<fff",
            blob,
            base,
        )
        rows.append(
            {
                "type": template_type,
                "width": width,
                "height": height,
                "half_width": abs(width) * 0.5,
                "half_height": abs(height) * 0.5,
                "collision_z": collision_z,
            }
        )
    return {
        "schema": "th08-bullet-template-geometry-v1",
        "manager_base": BULLET_MANAGER_BASE,
        "template_stride": BULLET_TEMPLATE_STRIDE,
        "rows": rows,
    }


def _runtime_instruction_record(
    cache: EclInstructionCache,
    reader: Any,
    instruction_pointer: int,
) -> dict[str, object]:
    instruction = cache.instruction(reader.read, instruction_pointer)
    return {
        "instruction_pointer": instruction_pointer,
        "time": instruction.time,
        "opcode": instruction.opcode,
        "size": instruction.size,
        "difficulty_mask": instruction.difficulty_mask,
        "parameter_mask": instruction.parameter_mask,
        "payload_hex": instruction.payload.hex(),
    }


def _stored_ecl_instruction_record(data: bytes) -> dict[str, object] | None:
    if len(data) != ENEMY_PERIODIC_EMISSION_DESCRIPTOR_SIZE:
        raise ValueError("stored ECL fire descriptor has the wrong size")
    if not any(data):
        return None
    time, opcode, size, unknown_byte, difficulty_mask, parameter_mask = (
        struct.unpack_from("<iHHBBH", data)
    )
    if size < 12 or size > len(data):
        raise ValueError(f"invalid stored ECL fire descriptor size {size}")
    return {
        "time": time,
        "opcode": opcode,
        "size": size,
        "unknown_byte": unknown_byte,
        "difficulty_mask": difficulty_mask,
        "parameter_mask": parameter_mask,
        "payload_hex": data[12:size].hex(),
        "retained_bytes_hex": data.hex(),
    }


def _enemy_periodic_emission_records(
    enemy_blob: bytes,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        base = observation.slot * ENEMY_STRIDE
        descriptor = bytes(
            enemy_blob[
                base + ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET :
                base
                + ENEMY_PERIODIC_EMISSION_DESCRIPTOR_OFFSET
                + ENEMY_PERIODIC_EMISSION_DESCRIPTOR_SIZE
            ]
        )
        hitpoints = struct.unpack_from(
            "<i",
            enemy_blob,
            base + ENEMY_HITPOINTS_OFFSET,
        )[0]
        period = struct.unpack_from(
            "<i",
            enemy_blob,
            base + ENEMY_PERIODIC_EMISSION_PERIOD_OFFSET,
        )[0]
        timer_previous, timer_fraction_bits, timer_elapsed = struct.unpack_from(
            "<iIi",
            enemy_blob,
            base + ENEMY_PERIODIC_EMISSION_TIMER_OFFSET,
        )
        enabled = hitpoints > 0 and period > 0
        rows.append(
            {
                "slot": observation.slot,
                "enemy_pointer": observation.enemy_pointer,
                "hitpoints": hitpoints,
                "period": period,
                "timer_previous": timer_previous,
                "timer_fraction_bits": timer_fraction_bits,
                "timer_elapsed": timer_elapsed,
                "enabled": enabled,
                "stored_fire_descriptor": (
                    _stored_ecl_instruction_record(descriptor)
                    if enabled
                    else None
                ),
            }
        )
    return {
        "schema": "th08-active-enemy-periodic-emission-state-v1",
        "scope": (
            "fixed_post_vm_staged_descriptor_period_and_timer_"
            "before_one_native_timer_advance"
        ),
        "rows": rows,
    }


def _enemy_current_instruction_records(
    reader: Any,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    """Capture only each initialized main VM's current immutable instruction."""

    cache = EclInstructionCache()
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        rows.append(
            {
                "slot": observation.slot,
                **_runtime_instruction_record(
                    cache,
                    reader,
                    observation.instruction_pointer,
                ),
            }
        )
    return {
        "schema": "th08-active-enemy-current-ecl-instruction-v1",
        "scope": "current_instruction_only_no_control_flow_closure",
        "rows": rows,
    }


def _installed_callback_record(
    cache: EclInstructionCache,
    reader: Any,
    *,
    function_pointer: int,
    argument_record_pointer: int,
) -> dict[str, object]:
    return {
        "function_pointer": function_pointer,
        "argument_record_pointer": argument_record_pointer,
        "argument_record_instruction": (
            _runtime_instruction_record(
                cache,
                reader,
                argument_record_pointer,
            )
            if function_pointer and argument_record_pointer
            else None
        ),
        "authority": (
            "root_identity_and_argument_record_only_callback_semantics_"
            "require_address_specific_lowering"
        ),
    }


def _enemy_main_ecl_callback_records(
    reader: Any,
    enemy_blob: bytes,
    inventory: EnemyMainEclVmInventory,
) -> dict[str, object]:
    cache = EclInstructionCache()
    rows: list[dict[str, object]] = []
    for observation in inventory.observations:
        base = (
            observation.slot * ENEMY_STRIDE
            + ENEMY_MAIN_ECL_VM_OFFSET
        )
        function_pointer, argument_record_pointer = struct.unpack_from(
            "<II",
            enemy_blob,
            base + 0x10,
        )
        rows.append(
            {
                "slot": observation.slot,
                "enemy_pointer": observation.enemy_pointer,
                "vm_kind": "main",
                "installed_callback": _installed_callback_record(
                    cache,
                    reader,
                    function_pointer=function_pointer,
                    argument_record_pointer=argument_record_pointer,
                ),
            }
        )
    return {
        "schema": "th08-active-enemy-main-ecl-installed-callback-v1",
        "execution_order": (
            "after_selected_main_interpreter_before_auxiliary_context_zero"
        ),
        "rows": rows,
    }


def _enemy_auxiliary_ecl_context_records(
    reader: Any,
    inventory: EnemyMainEclVmInventory,
    *,
    runtime_instruction_bounds: tuple[int, int] | None = None,
) -> dict[str, object]:
    """Dereference only non-null active auxiliary contexts at the seam."""

    cache = EclInstructionCache()
    rows: list[dict[str, object]] = []
    for owner in inventory.auxiliary_contexts:
        for auxiliary_index, context_pointer in enumerate(
            owner.context_pointers
        ):
            if context_pointer == 0:
                continue
            context = reader.read(
                context_pointer,
                CONTEXT_ACTIVE_VM_OFFSET + ACTIVE_VM_BYTES,
            )
            if len(context) != CONTEXT_ACTIVE_VM_OFFSET + ACTIVE_VM_BYTES:
                raise ValueError("short auxiliary ECL context read")
            target_subroutine = struct.unpack_from(
                "<I",
                context,
                CONTEXT_TARGET_OFFSET,
            )[0]
            call_depth = struct.unpack_from(
                "<H",
                context,
                CONTEXT_CALL_DEPTH_OFFSET,
            )[0]
            if call_depth > MAXIMUM_RESTORABLE_FRAMES:
                raise ValueError(
                    "auxiliary ECL call depth exceeds retained native layout"
                )
            active_vm = bytes(
                context[
                    CONTEXT_ACTIVE_VM_OFFSET :
                    CONTEXT_ACTIVE_VM_OFFSET + ACTIVE_VM_BYTES
                ]
            )
            state = AuxiliaryEclVmState.from_active_vm(
                active_vm,
                runtime_instruction_bounds=runtime_instruction_bounds,
            )
            callback_function, callback_argument_record = struct.unpack_from(
                "<II",
                active_vm,
                0x10,
            )
            rows.append(
                {
                    "slot": owner.slot,
                    "auxiliary_index": auxiliary_index,
                    "enemy_pointer": owner.enemy_pointer,
                    "context_pointer": context_pointer,
                    "target_subroutine": target_subroutine,
                    "call_depth": call_depth,
                    "state": state.record(),
                    "installed_callback": _installed_callback_record(
                        cache,
                        reader,
                        function_pointer=callback_function,
                        argument_record_pointer=callback_argument_record,
                    ),
                    "current_instruction": _runtime_instruction_record(
                        cache,
                        reader,
                        state.instruction_pointer,
                    ),
                }
            )
    return {
        "schema": "th08-active-enemy-auxiliary-ecl-context-v1",
        "scope": (
            "active_vm_and_current_instruction_only_"
            "no_saved_frame_or_control_flow_closure"
        ),
        "rows": rows,
    }


def _runtime_timeline_instruction_record(
    reader: Any,
    *,
    instruction_pointer: int,
    ecl_file_base: int,
    ecl_data_end_pointer: int,
) -> dict[str, object]:
    if not ecl_file_base <= instruction_pointer < ecl_data_end_pointer:
        raise ValueError(
            "timeline instruction pointer lies outside the loaded ECL image"
        )
    header = _read_exact(
        reader,
        instruction_pointer,
        8,
        field="timeline instruction header",
    )
    time, opcode, size, difficulty_mask = struct.unpack("<iHBB", header)
    record: dict[str, object] = {
        "instruction_pointer": instruction_pointer,
        "static_offset": instruction_pointer - ecl_file_base,
        "time": time,
        "opcode": opcode,
        "size": size,
        "difficulty_mask": difficulty_mask,
    }
    if time < 0:
        record["payload_hex"] = ""
        record["terminal"] = True
        return record
    if size < 8 or size % 4 or size > 0x400:
        raise ValueError(f"invalid live timeline instruction size {size}")
    if instruction_pointer + size > ecl_data_end_pointer:
        raise ValueError("timeline instruction crosses the loaded ECL image")
    payload = _read_exact(
        reader,
        instruction_pointer + 8,
        size - 8,
        field="timeline instruction payload",
    )
    record["payload_hex"] = payload.hex()
    record["terminal"] = False
    return record


def _timeline_external_state_record(reader: Any) -> dict[str, object]:
    markers = struct.unpack(
        "<4i",
        _read_exact(
            reader,
            TIMELINE_MARKERS_ADDRESS,
            16,
            field="timeline markers",
        ),
    )
    spawn_suppressed_raw = struct.unpack(
        "<I",
        _read_exact(
            reader,
            TIMELINE_SPAWN_SUPPRESSED_ADDRESS,
            4,
            field="timeline spawn suppression",
        ),
    )[0]
    frscreen_spawn_gate_raw = _read_exact(
        reader,
        FRSCREEN_STATE_ADDRESS + FRSCREEN_TIMELINE_SPAWN_GATE_OFFSET,
        1,
        field="FRScreen timeline spawn gate",
    )[0]
    frscreen_inner_pointer = struct.unpack(
        "<I",
        _read_exact(
            reader,
            FRSCREEN_STATE_ADDRESS + FRSCREEN_INNER_POINTER_OFFSET,
            4,
            field="FRScreen inner pointer",
        ),
    )[0]
    message_timer: int | None = None
    message_override_raw: int | None = None
    if frscreen_inner_pointer:
        message_timer = struct.unpack(
            "<i",
            _read_exact(
                reader,
                frscreen_inner_pointer + FRSCREEN_INNER_MESSAGE_TIMER_OFFSET,
                4,
                field="FRScreen message timer",
            ),
        )[0]
        message_override_raw = struct.unpack(
            "<I",
            _read_exact(
                reader,
                frscreen_inner_pointer + FRSCREEN_INNER_MESSAGE_OVERRIDE_OFFSET,
                4,
                field="FRScreen message override",
            ),
        )[0]
    conditional_gate_blocked = bool(
        frscreen_inner_pointer
        and message_override_raw == 0
        and message_timer is not None
        and message_timer >= 0
    )

    registry_blob = _read_exact(
        reader,
        INDEXED_ENEMY_REGISTRY_ADDRESS,
        INDEXED_ENEMY_REGISTRY_COUNT * 4,
        field="indexed enemy registry",
    )
    indexed_enemies: list[dict[str, object] | None] = []
    for pointer in struct.unpack(
        f"<{INDEXED_ENEMY_REGISTRY_COUNT}I",
        registry_blob,
    ):
        if pointer == 0:
            indexed_enemies.append(None)
            continue
        flags = struct.unpack(
            "<I",
            _read_exact(
                reader,
                pointer + ENEMY_FLAGS_OFFSET,
                4,
                field="indexed enemy flags",
            ),
        )[0]
        field_2d30 = struct.unpack(
            "<H",
            _read_exact(
                reader,
                pointer + INDEXED_ENEMY_TIMELINE_FIELD_OFFSET,
                2,
                field="indexed enemy timeline field",
            ),
        )[0]
        indexed_enemies.append(
            {
                "enemy_pointer": pointer,
                "flags": flags,
                "active": bool(flags & ENEMY_ACTIVE_FLAG),
                "field_2d30": field_2d30,
            }
        )

    return {
        "schema": "th08-stage-timeline-external-state-v1",
        "markers": list(markers),
        "spawn_suppressed": bool(spawn_suppressed_raw),
        "spawn_suppressed_raw": spawn_suppressed_raw,
        "stage_transition_busy": bool(frscreen_spawn_gate_raw),
        "frscreen_spawn_gate_raw": frscreen_spawn_gate_raw,
        "conditional_gate_blocked": conditional_gate_blocked,
        "frscreen_inner_pointer": frscreen_inner_pointer,
        "message_timer": message_timer,
        "message_override_raw": message_override_raw,
        "indexed_enemies": indexed_enemies,
    }


def _timeline_runtime_inventory_record(reader: Any) -> dict[str, object]:
    """Capture the causal root needed by the existing stage-timeline model."""

    context = _read_exact(
        reader,
        ECL_FILE_CONTEXT_ADDRESS,
        8,
        field="runtime ECL file context",
    )
    ecl_file_base, subroutine_pointer_table = struct.unpack("<II", context)
    if ecl_file_base == 0:
        raise ValueError("runtime ECL file base is null")
    header = _read_exact(
        reader,
        ecl_file_base,
        ECL_FILE_HEADER_SIZE,
        field="relocated runtime ECL header",
    )
    magic, subroutine_count, timeline_count = struct.unpack_from(
        "<IHH",
        header,
    )
    if magic != ECL_FILE_MAGIC:
        raise ValueError(f"unexpected runtime ECL magic {magic:#x}")
    if not 0 <= timeline_count <= ECL_MAXIMUM_TIMELINE_COUNT:
        raise ValueError(
            f"runtime ECL timeline count {timeline_count} has no sentinel slot"
        )
    if subroutine_pointer_table != ecl_file_base + ECL_FILE_HEADER_SIZE:
        raise ValueError("runtime ECL subroutine table pointer is inconsistent")
    relocated_timeline_pointers = struct.unpack_from("<16I", header, 8)
    ecl_data_end_pointer = relocated_timeline_pointers[timeline_count]
    if ecl_data_end_pointer <= ecl_file_base:
        raise ValueError("runtime ECL data-end sentinel is invalid")

    runtime_table = _read_exact(
        reader,
        TH08_TIMELINE_RUNTIME_BASE,
        TIMELINE_RUNTIME_SLOT_COUNT * TIMELINE_RUNTIME_SLOT_SIZE,
        field="timeline runtime table",
    )
    rows: list[dict[str, object]] = []
    for timeline_index in range(timeline_count):
        base = timeline_index * TIMELINE_RUNTIME_SLOT_SIZE
        previous_elapsed, fraction_bits, elapsed, instruction_pointer = (
            struct.unpack_from("<iIiI", runtime_table, base)
        )
        initialized = instruction_pointer != 0
        effective_instruction_pointer = (
            instruction_pointer
            if initialized
            else relocated_timeline_pointers[timeline_index]
        )
        rows.append(
            {
                "timeline_index": timeline_index,
                "previous_elapsed": previous_elapsed,
                "fraction_bits": fraction_bits,
                "elapsed": elapsed,
                "initialized": initialized,
                "instruction_pointer": instruction_pointer,
                "effective_instruction_pointer": effective_instruction_pointer,
                "timeline_start_pointer": relocated_timeline_pointers[
                    timeline_index
                ],
                "timeline_start_static_offset": (
                    relocated_timeline_pointers[timeline_index] - ecl_file_base
                ),
                "current_instruction": _runtime_timeline_instruction_record(
                    reader,
                    instruction_pointer=effective_instruction_pointer,
                    ecl_file_base=ecl_file_base,
                    ecl_data_end_pointer=ecl_data_end_pointer,
                ),
            }
        )

    difficulty_mask = _read_exact(
        reader,
        ECL_DIFFICULTY_MASK_ADDRESS,
        1,
        field="ECL difficulty mask",
    )[0]
    stage_flag_10 = _read_exact(
        reader,
        STAGE_TIMELINE_FLAG_10_ADDRESS,
        1,
        field="stage timeline flag 0x10",
    )[0]
    return {
        "schema": "th08-stage-timeline-runtime-inventory-v1",
        "scope": (
            "causal_root_clocks_current_instructions_and_external_gates_"
            "no_enemy_spawn_or_main_vm_execution"
        ),
        "ecl_file": {
            "context_address": ECL_FILE_CONTEXT_ADDRESS,
            "file_base": ecl_file_base,
            "subroutine_pointer_table": subroutine_pointer_table,
            "magic": magic,
            "subroutine_count": subroutine_count,
            "timeline_count": timeline_count,
            "data_end_pointer": ecl_data_end_pointer,
            "static_data_end_offset": ecl_data_end_pointer - ecl_file_base,
            "timeline_start_pointers": list(
                relocated_timeline_pointers[:timeline_count]
            ),
        },
        "difficulty_mask": difficulty_mask,
        "stage_flag_10": bool(stage_flag_10),
        "stage_flag_10_raw": stage_flag_10,
        "rows": rows,
        "external": _timeline_external_state_record(reader),
    }


@dataclass(frozen=True)
class CollisionControlProjection:
    payload: dict[str, object]
    sha256: str
    summary: dict[str, object]

    def record(
        self,
        *,
        include_model_payload: bool = False,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": COLLISION_CONTROL_PROJECTION_SCHEMA,
            "sha256": self.sha256,
            "summary": self.summary,
            "authority": (
                "collision_control_equivalence_only_not_full_gameplay_identity"
            ),
        }
        if include_model_payload:
            record["model_payload"] = self.payload
            record["model_payload_authority"] = (
                "decoded_native_state_for_offline_model_differential_only"
            )
        return record


def capture_collision_control_projection(
    reader: Any,
    *,
    native_root_projection: object,
    compact_state: dict[str, object],
) -> CollisionControlProjection:
    """Capture exact decoded hit-relevant state at one calculation seam."""

    stage_timeline_runtime = _timeline_runtime_inventory_record(reader)
    ecl_file = stage_timeline_runtime["ecl_file"]
    assert isinstance(ecl_file, dict)
    runtime_instruction_bounds = (
        int(ecl_file["file_base"]),
        int(ecl_file["data_end_pointer"]),
    )
    maximum_runtime_address = (
        0xFFFFFFFF
        if runtime_instruction_bounds[0] > 0x7FFFFFFF
        else 0x7FFFFFFF
    )
    bullet_blob = reader.read(
        BULLET_POOL_BASE,
        BULLET_POOL_SIZE * BULLET_STRIDE,
    )
    laser_blob = reader.read(
        LASER_POOL_BASE,
        LASER_POOL_SIZE * LASER_STRIDE,
    )
    enemy_blob = reader.read(
        ENEMY_POOL_BASE,
        ENEMY_POOL_SIZE * ENEMY_STRIDE,
    )
    manager_template_blob = reader.read(
        TH08_ENEMY_MANAGER_TEMPLATE_BASE,
        ENEMY_STRIDE,
    )
    bullets = decode_bullets(bullet_blob, retain_transform_runtime=True)
    lasers = decode_lasers(laser_blob)
    enemy_bodies = decode_enemy_bodies(
        enemy_blob,
        pool_size=ENEMY_POOL_SIZE,
        include_contact_disabled=True,
    )
    enemy_ecl_inventory, enemy_ecl_inventory_record = (
        _enemy_main_ecl_inventory_record(
            enemy_blob,
            runtime_instruction_bounds=runtime_instruction_bounds,
            maximum_runtime_address=maximum_runtime_address,
        )
    )
    manager_template_source = _enemy_source_record(
        reader,
        enemy_blob=manager_template_blob,
        pool_base=TH08_ENEMY_MANAGER_TEMPLATE_BASE,
        pool_size=1,
        source_role="native_enemy_slot_zero_legacy_manager_singleton",
        runtime_instruction_bounds=runtime_instruction_bounds,
        maximum_runtime_address=maximum_runtime_address,
    )
    player_x = float(compact_state["player_x"])
    player_y = float(compact_state["player_y"])
    normalized_components = normalized_causal_component_records(
        getattr(native_root_projection, "components")
    )
    payload: dict[str, object] = {
        "schema": COLLISION_CONTROL_PROJECTION_SCHEMA,
        "compact_state": compact_state,
        "player_lethal_aabb": _player_lethal_aabb(reader),
        "route2_option_causal_tails": list(_route2_option_causal_tails(reader)),
        "bullets": [serialize_bullet_trace(bullet) for bullet in bullets],
        "bullet_lifecycle": _bullet_lifecycle_records(bullet_blob, bullets),
        "bullet_lifecycle_semantics": {
            "state_motion_divisors": {
                str(state): divisor
                for state, divisor in BULLET_STATE_MOTION_DIVISORS.items()
            },
            "transition_authority": (
                "state-local motion observed; same-update ANM completion "
                "remains UNKNOWN without the corresponding ANM VM"
            ),
        },
        "lasers": [asdict(laser) for laser in lasers],
        "enemy_bodies": [asdict(body) for body in enemy_bodies],
        "enemy_main_ecl_vm_inventory": enemy_ecl_inventory_record,
        "enemy_periodic_emission_state": (
            _enemy_periodic_emission_records(
                enemy_blob,
                enemy_ecl_inventory,
            )
        ),
        "enemy_main_ecl_installed_callbacks": (
            _enemy_main_ecl_callback_records(
                reader,
                enemy_blob,
                enemy_ecl_inventory,
            )
        ),
        "enemy_current_ecl_instructions": (
            _enemy_current_instruction_records(reader, enemy_ecl_inventory)
        ),
        "enemy_emission_state": _enemy_emission_state_records(
            enemy_blob,
            enemy_ecl_inventory,
        ),
        "enemy_motion_state": _enemy_motion_state_records(
            enemy_blob,
            enemy_ecl_inventory,
        ),
        "enemy_phase_transition_state": (
            _enemy_phase_transition_state_records(
                enemy_blob,
                enemy_ecl_inventory,
            )
        ),
        "enemy_auxiliary_ecl_contexts": (
            _enemy_auxiliary_ecl_context_records(
                reader,
                enemy_ecl_inventory,
                runtime_instruction_bounds=runtime_instruction_bounds,
            )
        ),
        "enemy_manager_template_source": manager_template_source,
        "bullet_template_geometry": _bullet_template_geometry_record(reader),
        "stage_timeline_runtime": stage_timeline_runtime,
        "normalized_native_components": list(normalized_components),
    }
    summary = {
        "manager_frame": int(compact_state["manager_frame"]),
        "bullet_count": len(bullets),
        "laser_count": len(lasers),
        "enemy_body_count": len(enemy_bodies),
        "active_enemy_main_ecl_vm_count": len(
            enemy_ecl_inventory.observations
        ),
        "active_enemy_auxiliary_ecl_context_count": len(
            payload["enemy_auxiliary_ecl_contexts"]["rows"]
        ),
        "active_enemy_periodic_emitter_count": sum(
            bool(row["enabled"])
            for row in payload["enemy_periodic_emission_state"]["rows"]
        ),
        "active_enemy_installed_callback_count": (
            sum(
                bool(row["installed_callback"]["function_pointer"])
                for row in payload[
                    "enemy_main_ecl_installed_callbacks"
                ]["rows"]
            )
            + sum(
                bool(row["installed_callback"]["function_pointer"])
                for row in payload[
                    "enemy_auxiliary_ecl_contexts"
                ]["rows"]
            )
            + sum(
                bool(row["installed_callback"]["function_pointer"])
                for row in manager_template_source[
                    "main_ecl_installed_callbacks"
                ]["rows"]
            )
            + sum(
                bool(row["installed_callback"]["function_pointer"])
                for row in manager_template_source[
                    "auxiliary_ecl_contexts"
                ]["rows"]
            )
        ),
        "enemy_manager_template_source_active": manager_template_source[
            "active"
        ],
        "stage_timeline_count": len(
            payload["stage_timeline_runtime"]["rows"]
        ),
        "player_lethal_aabb": payload["player_lethal_aabb"],
        "nearest_bullets": _nearest_bullet_summary(
            bullets,
            player_x=player_x,
            player_y=player_y,
        ),
        "normalized_native_components": list(normalized_components),
        "presentation_exclusions": {
            "enemy_per_record_prefix": ENEMY_ANM_PREFIX_SIZE,
            "frscreen_resource_notification_counters": {
                "component": _SCHEDULER_COMPONENT_NAME,
                "offset": FRSCREEN_NOTIFICATION_COUNTERS_OFFSET,
                "size": FRSCREEN_NOTIFICATION_COUNTERS_SIZE,
                "consumer": "FRScreen render 0x0043625D",
            },
            "broad_player_component": (
                "replaced by compact player/resource state, lethal AABB, "
                "route-2 option causal tails, hostile hazards, enemy state"
            ),
        },
    }
    return CollisionControlProjection(
        payload=payload,
        sha256=_canonical_json_digest(payload),
        summary=summary,
    )


def collision_control_projection_changes(
    left: CollisionControlProjection,
    right: CollisionControlProjection,
) -> tuple[dict[str, object], ...]:
    if left.sha256 == right.sha256:
        return ()
    changes: list[dict[str, object]] = []
    keys = sorted(set(left.payload) | set(right.payload))
    for key in keys:
        left_value = left.payload.get(key)
        right_value = right.payload.get(key)
        if left_value == right_value:
            continue
        record: dict[str, object] = {"field": key}
        if isinstance(left_value, list) and isinstance(right_value, list):
            first_difference = None
            for index, (left_item, right_item) in enumerate(
                zip(left_value, right_value)
            ):
                if left_item != right_item:
                    first_difference = index
                    break
            if first_difference is None and len(left_value) != len(right_value):
                first_difference = min(len(left_value), len(right_value))
            record.update(
                {
                    "left_count": len(left_value),
                    "right_count": len(right_value),
                    "first_difference": first_difference,
                }
            )
        else:
            record.update(
                {
                    "left": left_value,
                    "right": right_value,
                }
            )
        changes.append(record)
    return tuple(changes)


__all__ = [
    "COLLISION_CONTROL_PROJECTION_SCHEMA",
    "CollisionControlProjection",
    "ENEMY_ANM_PREFIX_SIZE",
    "FRSCREEN_NOTIFICATION_COUNTERS_OFFSET",
    "FRSCREEN_NOTIFICATION_COUNTERS_SIZE",
    "ROUTE2_OPTION_BASE_OFFSET",
    "ROUTE2_OPTION_CAUSAL_TAIL_OFFSET",
    "ROUTE2_OPTION_COUNT",
    "ROUTE2_OPTION_STRIDE",
    "capture_collision_control_projection",
    "collision_control_projection_changes",
    "normalized_causal_component_records",
]
