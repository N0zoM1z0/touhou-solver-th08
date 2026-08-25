"""Source-derived TH08 enemy/linked-child construction primitives.

This module contains no stage or spell dispatch. It names the five generic
ECL constructors whose native implementations converge on
``EnemyManager::SpawnEnemy2``:

* 0x5A/0x5B/0x5C construct linked children;
* 0x5D/0x5E construct ordinary enemies with copied VM locals.

The ECL interpreter remains responsible for operand resolution, template
copying, synchronous VM execution, and pool scheduling. The compact point
model here isolates the constructor geometry/flag contract so it can be
differentially checked against the separately compiled C oracle.
"""

from __future__ import annotations

from dataclasses import dataclass

from numeric_model import binary32_store as f32


SOURCE_AUTHORITY_COMMIT = "57ee34f"

ECL_OP_SPAWN_LINKED_CHILD = 0x5A
ECL_OP_SPAWN_LINKED_CHILD_AT_PARENT = 0x5B
ECL_OP_SPAWN_LINKED_CHILD_FOLLOW_PARENT = 0x5C
ECL_OP_SPAWN_ENEMY = 0x5D
ECL_OP_SPAWN_ENEMY_AT_PARENT = 0x5E

ENEMY_FLAG_CONTACT = 1 << 2
ENEMY_FLAG_LINKED_CHILD = 1 << 8
ENEMY_FLAG_FOLLOW_PARENT_BASE = 1 << 9
ENEMY_FLAG_SUPPRESS_DEATH_EFFECTS = 1 << 10
ENEMY_FLAG_IS_YOUKAI = 1 << 11


@dataclass(frozen=True)
class EnemySpawnProfile:
    opcode: int
    add_parent_world_to_constructor_base: bool
    linked_child: bool
    follow_parent_base: bool
    requires_clear_suppress_death_effects: bool


@dataclass(frozen=True)
class EnemySpawnPointSample:
    constructor_admitted: bool
    spawned: bool
    linked_child: bool
    follow_parent_base: bool
    constructor_base_x: float
    constructor_base_y: float
    constructor_world_x: float
    constructor_world_y: float
    constructor_flags: int
    post_link_base_x: float
    post_link_base_y: float
    post_link_relative_x: float
    post_link_relative_y: float
    post_link_world_x: float
    post_link_world_y: float
    post_link_flags: int


_PROFILES = {
    ECL_OP_SPAWN_LINKED_CHILD: EnemySpawnProfile(
        opcode=ECL_OP_SPAWN_LINKED_CHILD,
        add_parent_world_to_constructor_base=False,
        linked_child=True,
        follow_parent_base=False,
        requires_clear_suppress_death_effects=True,
    ),
    ECL_OP_SPAWN_LINKED_CHILD_AT_PARENT: EnemySpawnProfile(
        opcode=ECL_OP_SPAWN_LINKED_CHILD_AT_PARENT,
        add_parent_world_to_constructor_base=True,
        linked_child=True,
        follow_parent_base=False,
        requires_clear_suppress_death_effects=True,
    ),
    ECL_OP_SPAWN_LINKED_CHILD_FOLLOW_PARENT: EnemySpawnProfile(
        opcode=ECL_OP_SPAWN_LINKED_CHILD_FOLLOW_PARENT,
        add_parent_world_to_constructor_base=False,
        linked_child=True,
        follow_parent_base=True,
        requires_clear_suppress_death_effects=True,
    ),
    ECL_OP_SPAWN_ENEMY: EnemySpawnProfile(
        opcode=ECL_OP_SPAWN_ENEMY,
        add_parent_world_to_constructor_base=False,
        linked_child=False,
        follow_parent_base=False,
        requires_clear_suppress_death_effects=False,
    ),
    ECL_OP_SPAWN_ENEMY_AT_PARENT: EnemySpawnProfile(
        opcode=ECL_OP_SPAWN_ENEMY_AT_PARENT,
        add_parent_world_to_constructor_base=True,
        linked_child=False,
        follow_parent_base=False,
        requires_clear_suppress_death_effects=False,
    ),
}


def enemy_spawn_profile(opcode: int) -> EnemySpawnProfile:
    """Return the generic native constructor class for one ECL opcode."""

    if type(opcode) is not int:
        raise ValueError("enemy spawn opcode must be an integer")
    try:
        return _PROFILES[opcode]
    except KeyError as error:
        raise ValueError(f"unsupported enemy spawn opcode {opcode:#x}") from error


def enemy_spawn_point_sample(
    *,
    opcode: int,
    operand_x: float,
    operand_y: float,
    parent_base_x: float,
    parent_base_y: float,
    parent_world_x: float,
    parent_world_y: float,
    template_relative_x: float,
    template_relative_y: float,
    template_flags: int,
    parent_flags: int,
    parent_hitpoints: int,
    player_is_youkais: bool,
    pool_available: bool,
    bootstrap_succeeded: bool,
    bootstrap_base_x: float,
    bootstrap_base_y: float,
    bootstrap_relative_x: float,
    bootstrap_relative_y: float,
    bootstrap_world_x: float,
    bootstrap_world_y: float,
    bootstrap_flags: int,
) -> EnemySpawnPointSample:
    """Transcribe constructor admission and the post-bootstrap link mutation.

    ``constructor_*`` is the state seen by the synchronous ``RunEcl`` inside
    ``SpawnEnemy2``. The ``bootstrap_*`` inputs are the state returned by that
    call: the child ECL may change position and flags before opcodes 0x5A..0x5C
    attach it to the parent. Keeping both phases explicit prevents the pure
    constructor model from assuming that an arbitrary child root is inert.

    ``constructor_admitted`` means the parent/slot guards allowed
    ``SpawnEnemy2`` to run. ``spawned`` additionally requires its synchronous
    ECL bootstrap to succeed. Failed constructors receive no post-link writes.
    """

    profile = enemy_spawn_profile(opcode)
    for name, value in (
        ("template_flags", template_flags),
        ("parent_flags", parent_flags),
        ("parent_hitpoints", parent_hitpoints),
        ("bootstrap_flags", bootstrap_flags),
    ):
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    for name, value in (
        ("player_is_youkais", player_is_youkais),
        ("pool_available", pool_available),
        ("bootstrap_succeeded", bootstrap_succeeded),
    ):
        if type(value) is not bool:
            raise ValueError(f"{name} must be a bool")
    for name, value in (
        ("template_flags", template_flags),
        ("parent_flags", parent_flags),
        ("bootstrap_flags", bootstrap_flags),
    ):
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError(f"{name} must fit in an unsigned 32-bit word")
    if not -(1 << 31) <= parent_hitpoints < (1 << 31):
        raise ValueError("parent_hitpoints must fit in a signed 32-bit word")

    constructor_admitted = pool_available and parent_hitpoints > 0
    if profile.requires_clear_suppress_death_effects:
        constructor_admitted = constructor_admitted and not bool(
            parent_flags & ENEMY_FLAG_SUPPRESS_DEATH_EFFECTS
        )
    spawned = constructor_admitted and bootstrap_succeeded

    constructor_base_x = f32(operand_x)
    constructor_base_y = f32(operand_y)
    if profile.add_parent_world_to_constructor_base:
        constructor_base_x = f32(constructor_base_x + f32(parent_world_x))
        constructor_base_y = f32(constructor_base_y + f32(parent_world_y))
    constructor_world_x = f32(
        constructor_base_x + f32(template_relative_x)
    )
    constructor_world_y = f32(
        constructor_base_y + f32(template_relative_y)
    )

    post_base_x = f32(bootstrap_base_x)
    post_base_y = f32(bootstrap_base_y)
    post_relative_x = f32(bootstrap_relative_x)
    post_relative_y = f32(bootstrap_relative_y)
    post_world_x = f32(bootstrap_world_x)
    post_world_y = f32(bootstrap_world_y)
    post_flags = bootstrap_flags
    if spawned and profile.linked_child:
        post_flags |= ENEMY_FLAG_LINKED_CHILD
        post_flags &= ~ENEMY_FLAG_CONTACT
        if player_is_youkais:
            post_flags |= ENEMY_FLAG_IS_YOUKAI
        else:
            post_flags &= ~ENEMY_FLAG_IS_YOUKAI
        if profile.follow_parent_base:
            post_relative_x = f32(parent_base_x)
            post_relative_y = f32(parent_base_y)
            post_world_x = f32(post_relative_x + post_base_x)
            post_world_y = f32(post_relative_y + post_base_y)
            post_flags |= ENEMY_FLAG_FOLLOW_PARENT_BASE

    return EnemySpawnPointSample(
        constructor_admitted=constructor_admitted,
        spawned=spawned,
        linked_child=spawned and profile.linked_child,
        follow_parent_base=(
            spawned and profile.linked_child and profile.follow_parent_base
        ),
        constructor_base_x=constructor_base_x,
        constructor_base_y=constructor_base_y,
        constructor_world_x=constructor_world_x,
        constructor_world_y=constructor_world_y,
        constructor_flags=template_flags,
        post_link_base_x=post_base_x,
        post_link_base_y=post_base_y,
        post_link_relative_x=post_relative_x,
        post_link_relative_y=post_relative_y,
        post_link_world_x=post_world_x,
        post_link_world_y=post_world_y,
        post_link_flags=post_flags,
    )


__all__ = [
    "ECL_OP_SPAWN_ENEMY",
    "ECL_OP_SPAWN_ENEMY_AT_PARENT",
    "ECL_OP_SPAWN_LINKED_CHILD",
    "ECL_OP_SPAWN_LINKED_CHILD_AT_PARENT",
    "ECL_OP_SPAWN_LINKED_CHILD_FOLLOW_PARENT",
    "ENEMY_FLAG_CONTACT",
    "ENEMY_FLAG_FOLLOW_PARENT_BASE",
    "ENEMY_FLAG_IS_YOUKAI",
    "ENEMY_FLAG_LINKED_CHILD",
    "ENEMY_FLAG_SUPPRESS_DEATH_EFFECTS",
    "EnemySpawnPointSample",
    "EnemySpawnProfile",
    "enemy_spawn_point_sample",
    "enemy_spawn_profile",
]
