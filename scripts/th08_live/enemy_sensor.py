"""TH08 enemy-body decoding, snapshot alignment, and contact capture."""

from __future__ import annotations

import struct
import time
from dataclasses import replace

from th08_enemy_collision import enemy_contact_size_to_lethal_half_extent
from th08_live.bullet_decode import finite
from th08_live.enemy_combat_progress import (
    decode_enemy_combat_progress_inventory,
)
from th08_live.enemy_ecl_inventory import (
    decode_enemy_main_ecl_vm_inventory,
)
from th08_live.models import (
    EnemyBody,
    EnemyPoolSnapshot,
    SpellEnemyBodyGuard,
)
from th08_runtime_agent import (
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_PLAYER,
    ProcessReader,
)

# This vector advances the enemy's internal +0x2D34 motion component in
# sub_42DEB0. It is not, in general, the derivative of the lethal world
# position because scripted/relative motion contributes separately.
ENEMY_VELOCITY_OFFSET = 0x2D4C
ENEMY_CONTACT_SIZE_OFFSET = 0x2D70
ENEMY_POSITION_OFFSET = 0x2D88
ENEMY_FLAGS_OFFSET = 0x3324

# First of 480 ordinary timeline-enemy slots. Spell owners may live outside
# this range, so their authoritative pointers have a separate guard path.
ENEMY_POOL_BASE = 0x005826C0
ENEMY_POOL_SIZE = 480
ENEMY_STRIDE = 0x53D0
# The manager-owned record immediately before the ordinary pool is reused as
# an active non-spell hostile source.  It is not merely inert template bytes:
# retained native root 2129 observed a body and auxiliary ECL fire here.
ENEMY_MANAGER_TEMPLATE_BASE = ENEMY_POOL_BASE - ENEMY_STRIDE
ENEMY_LOCAL_PREFIX_SIZE = 64
ENEMY_BODY_READ_OFFSET = ENEMY_VELOCITY_OFFSET
ENEMY_BODY_READ_SIZE = ENEMY_FLAGS_OFFSET + 4 - ENEMY_BODY_READ_OFFSET
ENEMY_ACTIVE_FLAG = 0x00000001
ENEMY_CONTACT_ENABLED_FLAG = 0x00000004
ENEMY_CONTACT_BLOCKING_FLAGS = 0x00000830

PLAYER_LETHAL_AABB_OFFSET = 0x038C
PLAYER_LETHAL_AABB_SIZE = 0x14


def _decode_enemy_body_geometry(
    blob: bytes,
    *,
    pointer: int,
) -> EnemyBody | None:
    if len(blob) < ENEMY_BODY_READ_SIZE:
        raise ValueError(
            f"enemy body window requires {ENEMY_BODY_READ_SIZE} bytes"
        )
    velocity_offset = ENEMY_VELOCITY_OFFSET - ENEMY_BODY_READ_OFFSET
    contact_offset = ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET
    position_offset = ENEMY_POSITION_OFFSET - ENEMY_BODY_READ_OFFSET
    flags_offset = ENEMY_FLAGS_OFFSET - ENEMY_BODY_READ_OFFSET
    internal_vx, internal_vy = struct.unpack_from(
        "<ff",
        blob,
        velocity_offset,
    )
    contact_width, contact_height = struct.unpack_from(
        "<ff",
        blob,
        contact_offset,
    )
    x, y = struct.unpack_from("<ff", blob, position_offset)
    flags = struct.unpack_from("<I", blob, flags_offset)[0]
    if not flags & ENEMY_ACTIVE_FLAG:
        return None
    if not finite(
        (
            x,
            y,
            internal_vx,
            internal_vy,
            contact_width,
            contact_height,
        )
    ):
        return None
    if contact_width < 0.0 or contact_height < 0.0:
        return None
    return EnemyBody(
        pointer=pointer,
        x=x,
        y=y,
        # +0x2D4C advances an internal motion component, not necessarily the
        # collision position. EnemyBodyModeMemory supplies the observed
        # world-position derivative before this body reaches planning.
        vx=0.0,
        vy=0.0,
        # Target 0x42C290 stores raw / 1.5f before 0x44A360 halves it.
        half_width=enemy_contact_size_to_lethal_half_extent(contact_width),
        half_height=enemy_contact_size_to_lethal_half_extent(contact_height),
        flags=flags,
        internal_vx=internal_vx,
        internal_vy=internal_vy,
    )


def decode_enemy_body(blob: bytes, *, pointer: int) -> EnemyBody | None:
    body = _decode_enemy_body_geometry(blob, pointer=pointer)
    if body is None or (
        not body.flags & ENEMY_CONTACT_ENABLED_FLAG
        or body.flags & ENEMY_CONTACT_BLOCKING_FLAGS
    ):
        return None
    return body


def enemy_body_contact_enabled(body: EnemyBody) -> bool:
    """Return the native contact-mode gate represented by one body sample."""

    return bool(
        body.flags & ENEMY_CONTACT_ENABLED_FLAG
        and not body.flags & ENEMY_CONTACT_BLOCKING_FLAGS
    )


def enemy_pointer_in_scanned_pool(pointer: int) -> bool:
    """Return whether a pointer is one of the 480 async-scanned slots."""

    offset = pointer - ENEMY_POOL_BASE
    return (
        0 <= offset < ENEMY_POOL_SIZE * ENEMY_STRIDE
        and offset % ENEMY_STRIDE == 0
    )


def decode_spell_enemy_body_guard(
    blob: bytes,
    *,
    pointer: int,
) -> SpellEnemyBodyGuard | None:
    """Retain the spell owner even when the async pool cannot observe it."""

    body = _decode_enemy_body_geometry(blob, pointer=pointer)
    if body is None:
        return None
    contact_offset = ENEMY_CONTACT_SIZE_OFFSET - ENEMY_BODY_READ_OFFSET
    raw_contact_width, raw_contact_height = struct.unpack_from(
        "<ff",
        blob,
        contact_offset,
    )
    return SpellEnemyBodyGuard(
        body=body,
        contact_enabled=bool(
            body.flags & ENEMY_CONTACT_ENABLED_FLAG
            and not body.flags & ENEMY_CONTACT_BLOCKING_FLAGS
        ),
        raw_contact_width=raw_contact_width,
        raw_contact_height=raw_contact_height,
    )


def decode_enemy_bodies(
    blob: bytes,
    *,
    pool_base: int = ENEMY_POOL_BASE,
    pool_size: int = ENEMY_POOL_SIZE,
    include_contact_disabled: bool = False,
) -> tuple[EnemyBody, ...]:
    """Decode ordinary enemy collision geometry from a contiguous pool."""

    if not 0 <= pool_size <= ENEMY_POOL_SIZE:
        raise ValueError("enemy pool size must belong to the native pool")
    expected_size = pool_size * ENEMY_STRIDE
    if len(blob) < expected_size:
        raise ValueError(f"enemy pool requires {expected_size} bytes")
    bodies: list[EnemyBody] = []
    for slot in range(pool_size):
        base = slot * ENEMY_STRIDE
        flags = struct.unpack_from(
            "<I",
            blob,
            base + ENEMY_FLAGS_OFFSET,
        )[0]
        if not flags & ENEMY_ACTIVE_FLAG:
            continue
        if not include_contact_disabled and (
            flags & ENEMY_CONTACT_BLOCKING_FLAGS
            or not flags & ENEMY_CONTACT_ENABLED_FLAG
        ):
            continue
        internal_vx, internal_vy = struct.unpack_from(
            "<ff",
            blob,
            base + ENEMY_VELOCITY_OFFSET,
        )
        contact_width, contact_height = struct.unpack_from(
            "<ff",
            blob,
            base + ENEMY_CONTACT_SIZE_OFFSET,
        )
        x, y = struct.unpack_from(
            "<ff",
            blob,
            base + ENEMY_POSITION_OFFSET,
        )
        if not finite(
            (
                x,
                y,
                internal_vx,
                internal_vy,
                contact_width,
                contact_height,
            )
        ):
            continue
        if contact_width < 0.0 or contact_height < 0.0:
            continue
        if (
            include_contact_disabled
            and not flags & ENEMY_CONTACT_ENABLED_FLAG
            and (contact_width == 0.0 or contact_height == 0.0)
        ):
            continue
        bodies.append(
            EnemyBody(
                pointer=pool_base + base,
                x=x,
                y=y,
                vx=0.0,
                vy=0.0,
                half_width=enemy_contact_size_to_lethal_half_extent(
                    contact_width
                ),
                half_height=enemy_contact_size_to_lethal_half_extent(
                    contact_height
                ),
                flags=flags,
                internal_vx=internal_vx,
                internal_vy=internal_vy,
            )
        )
    return tuple(bodies)


def capture_enemy_pool_snapshot_contiguous(
    reader: ProcessReader,
) -> EnemyPoolSnapshot:
    started = time.perf_counter()
    frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
    blob = reader.read(
        ENEMY_POOL_BASE,
        ENEMY_POOL_SIZE * ENEMY_STRIDE,
    )
    frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
    return EnemyPoolSnapshot(
        frame_before,
        frame_after,
        decode_enemy_bodies(blob),
        (time.perf_counter() - started) * 1000.0,
    )


def capture_enemy_pool_prefix_contiguous(
    reader: ProcessReader,
    *,
    pool_size: int = ENEMY_LOCAL_PREFIX_SIZE,
    maximum_attempts: int = 2,
    include_main_ecl_vms: bool = False,
    include_combat_progress: bool = False,
) -> EnemyPoolSnapshot:
    """Capture the allocation head once per local decision."""

    if not 0 < pool_size <= ENEMY_POOL_SIZE:
        raise ValueError("enemy prefix size must belong to the native pool")
    if maximum_attempts <= 0:
        raise ValueError("enemy prefix attempts must be positive")
    started = time.perf_counter()
    snapshot = None
    for attempt in range(1, maximum_attempts + 1):
        frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        blob = reader.read(ENEMY_POOL_BASE, pool_size * ENEMY_STRIDE)
        frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        main_ecl_vm_inventory = (
            decode_enemy_main_ecl_vm_inventory(
                blob,
                pool_base=ENEMY_POOL_BASE,
                pool_size=pool_size,
                enemy_stride=ENEMY_STRIDE,
                enemy_flags_offset=ENEMY_FLAGS_OFFSET,
                enemy_active_flag=ENEMY_ACTIVE_FLAG,
            )
            if include_main_ecl_vms
            else None
        )
        combat_progress_inventory = (
            decode_enemy_combat_progress_inventory(
                blob,
                pool_base=ENEMY_POOL_BASE,
                pool_size=pool_size,
                enemy_stride=ENEMY_STRIDE,
                enemy_active_flag=ENEMY_ACTIVE_FLAG,
            )
            if include_combat_progress
            else None
        )
        snapshot = EnemyPoolSnapshot(
            frame_before,
            frame_after,
            decode_enemy_bodies(
                blob,
                pool_size=pool_size,
                include_contact_disabled=True,
            ),
            (time.perf_counter() - started) * 1000.0,
            attempt,
            main_ecl_vm_inventory,
            combat_progress_inventory,
        )
        if snapshot.stable:
            return snapshot
    assert snapshot is not None
    return snapshot


def read_enemy_bodies_sparse(
    reader: ProcessReader,
) -> tuple[EnemyBody, ...]:
    """Read the manager singleton plus every ordinary pool body."""

    bodies = []
    pointers = (
        ENEMY_MANAGER_TEMPLATE_BASE,
        *(
            ENEMY_POOL_BASE + slot * ENEMY_STRIDE
            for slot in range(ENEMY_POOL_SIZE)
        ),
    )
    for pointer in pointers:
        flags = reader.u32(pointer + ENEMY_FLAGS_OFFSET)
        if (
            not flags & ENEMY_ACTIVE_FLAG
            or not flags & ENEMY_CONTACT_ENABLED_FLAG
            or flags & ENEMY_CONTACT_BLOCKING_FLAGS
        ):
            continue
        body = decode_enemy_body(
            reader.read(
                pointer + ENEMY_BODY_READ_OFFSET,
                ENEMY_BODY_READ_SIZE,
            ),
            pointer=pointer,
        )
        if body is not None:
            bodies.append(body)
    return tuple(bodies)


def capture_enemy_pool_snapshot_sparse(
    reader: ProcessReader,
) -> EnemyPoolSnapshot:
    started = time.perf_counter()
    frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
    bodies = read_enemy_bodies_sparse(reader)
    frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
    return EnemyPoolSnapshot(
        frame_before,
        frame_after,
        bodies,
        (time.perf_counter() - started) * 1000.0,
    )


# Sparse reads retained the same bodies in paused multi-enemy runtime
# differentials while reducing capture latency enough to scan four times as
# often at approximately the old bandwidth duty cycle.
capture_enemy_pool_snapshot = capture_enemy_pool_snapshot_sparse


def project_enemy_pool_snapshot(
    snapshot: EnemyPoolSnapshot | None,
    *,
    frame: int,
) -> tuple[EnemyBody, ...]:
    if snapshot is None:
        return ()
    age = frame - snapshot.frame_after
    uncertainty = min(16.0, 0.75 * abs(age))
    return tuple(
        replace(
            body,
            x=body.x + body.vx * age,
            y=body.y + body.vy * age,
            uncertainty=body.uncertainty + uncertainty,
        )
        for body in snapshot.bodies
    )


def merge_enemy_pool_prefix(
    background_bodies: tuple[EnemyBody, ...],
    prefix_bodies: tuple[EnemyBody, ...],
    *,
    pool_size: int = ENEMY_LOCAL_PREFIX_SIZE,
) -> tuple[EnemyBody, ...]:
    """Replace stale background copies in the synchronously read prefix."""

    if not 0 < pool_size <= ENEMY_POOL_SIZE:
        raise ValueError("enemy prefix size must belong to the native pool")
    prefix_end = ENEMY_POOL_BASE + pool_size * ENEMY_STRIDE
    tail = tuple(
        body
        for body in background_bodies
        if not ENEMY_POOL_BASE <= body.pointer < prefix_end
    )
    return prefix_bodies + tail


def enemy_pool_snapshot_changes(
    planned: EnemyPoolSnapshot,
    current: EnemyPoolSnapshot,
    *,
    position_tolerance: float = 2.0,
    velocity_tolerance: float = 0.25,
    size_tolerance: float = 0.25,
) -> tuple[str, ...]:
    """Detect contact-topology or non-linear changes during planning."""

    if not planned.stable or not current.stable:
        return ("unstable_capture",)
    if current.frame_after < planned.frame_after:
        return ("frame_reversed",)
    planned_by_pointer = {body.pointer: body for body in planned.bodies}
    current_by_pointer = {body.pointer: body for body in current.bodies}
    changes = []
    for pointer in sorted(current_by_pointer.keys() - planned_by_pointer.keys()):
        changes.append(f"added:{pointer:#x}")
    for pointer in sorted(planned_by_pointer.keys() - current_by_pointer.keys()):
        changes.append(f"removed:{pointer:#x}")
    frame_delta = current.frame_after - planned.frame_after
    relevant_flags = (
        ENEMY_ACTIVE_FLAG
        | ENEMY_CONTACT_ENABLED_FLAG
        | ENEMY_CONTACT_BLOCKING_FLAGS
    )
    for pointer in sorted(planned_by_pointer.keys() & current_by_pointer.keys()):
        before = planned_by_pointer[pointer]
        after = current_by_pointer[pointer]
        expected_x = before.x + before.vx * frame_delta
        expected_y = before.y + before.vy * frame_delta
        if (
            abs(after.x - expected_x) > position_tolerance
            or abs(after.y - expected_y) > position_tolerance
        ):
            changes.append(f"trajectory:{pointer:#x}")
        if (
            abs(after.vx - before.vx) > velocity_tolerance
            or abs(after.vy - before.vy) > velocity_tolerance
        ):
            changes.append(f"velocity:{pointer:#x}")
        if (
            abs(after.half_width - before.half_width) > size_tolerance
            or abs(after.half_height - before.half_height) > size_tolerance
        ):
            changes.append(f"size:{pointer:#x}")
        if (after.flags ^ before.flags) & relevant_flags:
            changes.append(f"contact_mode:{pointer:#x}")
    return tuple(changes)


def issue_enemy_snapshot_changes(
    planned_raw: EnemyPoolSnapshot,
    current_raw: EnemyPoolSnapshot,
    planned_aligned: EnemyPoolSnapshot,
    current_aligned: EnemyPoolSnapshot,
) -> tuple[str, ...]:
    """Version an issue guard by topology and aligned world trajectories."""

    raw_changes = enemy_pool_snapshot_changes(planned_raw, current_raw)
    aligned_changes = enemy_pool_snapshot_changes(
        planned_aligned,
        current_aligned,
    )
    topology_kinds = {
        "added",
        "removed",
        "size",
        "contact_mode",
        "unstable_capture",
        "frame_reversed",
    }
    return tuple(
        dict.fromkeys(
            change
            for change in (*raw_changes, *aligned_changes)
            if change.split(":", 1)[0] in topology_kinds
            or change in aligned_changes
        )
    )


def read_spell_enemy_bodies(
    reader: ProcessReader,
    spell: dict[str, object],
) -> tuple[EnemyBody, ...]:
    if not bool(spell.get("active")):
        return ()
    pointer = int(spell.get("enemy_pointer", 0))
    if pointer == 0:
        return ()
    blob = reader.read(
        pointer + ENEMY_BODY_READ_OFFSET,
        ENEMY_BODY_READ_SIZE,
    )
    body = decode_enemy_body(blob, pointer=pointer)
    return (body,) if body is not None else ()


def read_spell_enemy_body_guard(
    reader: ProcessReader,
    spell: dict[str, object],
) -> SpellEnemyBodyGuard | None:
    if not bool(spell.get("active")):
        return None
    pointer = int(spell.get("enemy_pointer", 0))
    if pointer == 0:
        return None
    return read_enemy_body_guard(reader, pointer=pointer)


def read_enemy_body_guard(
    reader: ProcessReader,
    *,
    pointer: int,
) -> SpellEnemyBodyGuard | None:
    """Read one active enemy body, including latent contact geometry."""

    return decode_spell_enemy_body_guard(
        reader.read(
            pointer + ENEMY_BODY_READ_OFFSET,
            ENEMY_BODY_READ_SIZE,
        ),
        pointer=pointer,
    )


def merge_spell_enemy_body_guard(
    bodies: tuple[EnemyBody, ...],
    guard: SpellEnemyBodyGuard | None,
) -> tuple[EnemyBody, ...]:
    if guard is None:
        return bodies
    return tuple(
        body for body in bodies if body.pointer != guard.body.pointer
    ) + (guard.body,)


def decode_player_lethal_aabb(
    blob: bytes,
) -> tuple[float, float, float, float] | None:
    if len(blob) < PLAYER_LETHAL_AABB_SIZE:
        raise ValueError(
            f"player lethal AABB requires {PLAYER_LETHAL_AABB_SIZE} bytes"
        )
    left, top = struct.unpack_from("<ff", blob, 0)
    right, bottom = struct.unpack_from("<ff", blob, 0x0C)
    if not finite((left, top, right, bottom)):
        return None
    if left > right or top > bottom:
        return None
    return left, top, right, bottom


def _serialized_enemy_bodies(
    bodies: tuple[EnemyBody, ...],
) -> list[list[float | int | None]]:
    return [
        [
            body.pointer,
            body.x,
            body.y,
            body.vx,
            body.vy,
            body.half_width,
            body.half_height,
            body.flags,
            body.uncertainty,
            body.internal_vx,
            body.internal_vy,
        ]
        for body in bodies
    ]


def capture_hit_contact_observation(
    reader: ProcessReader,
    spell: dict[str, object],
    *,
    attempts: int = 3,
) -> dict[str, object]:
    observation: dict[str, object] = {}
    for _ in range(max(1, attempts)):
        frame_before = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        player_blob = reader.read(
            ADDR_PLAYER + PLAYER_LETHAL_AABB_OFFSET,
            PLAYER_LETHAL_AABB_SIZE,
        )
        enemy_blob = reader.read(
            ENEMY_POOL_BASE,
            ENEMY_POOL_SIZE * ENEMY_STRIDE,
        )
        enemy_bodies = decode_enemy_bodies(enemy_blob)
        frame_after = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
        player_aabb = decode_player_lethal_aabb(player_blob)
        observation = {
            "frame_before": frame_before,
            "frame_after": frame_after,
            "stable": frame_before == frame_after,
            "player_lethal_aabb": (
                list(player_aabb) if player_aabb is not None else None
            ),
            "enemy_bodies": _serialized_enemy_bodies(enemy_bodies),
        }
        if observation["stable"]:
            break
    return observation
