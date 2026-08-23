"""Exact TH08 enemy contact-size conversions used by the solver.

The Japanese 1.00d target computes lethal player contact in
``Enemy::FUN_0042c290`` (0x0042C290) by dividing the raw enemy contact-size
vector by ``1.5f``.  The resulting ``Float3`` is stored as binary32 before
``Player::FUN_0044a360`` (0x0044A360) constructs ``center +/- size / 2``.
Player-shot damage instead passes the raw vector directly to
``Player::FUN_00451670`` (0x00451670), whose AABB builder also takes half.
"""

from __future__ import annotations

from numeric_model import binary32_store


ENEMY_LETHAL_FULL_SIZE_DIVISOR = 1.5


def enemy_contact_size_to_lethal_half_extent(contact_size: float) -> float:
    """Mirror the target's stored ``contact / 1.5f``, then AABB halving."""

    stored_contact_size = binary32_store(contact_size)
    lethal_full_size = binary32_store(
        stored_contact_size / ENEMY_LETHAL_FULL_SIZE_DIVISOR
    )
    return lethal_full_size / 2.0


def enemy_contact_size_to_damage_half_extent(contact_size: float) -> float:
    """Return the player-shot target half-extent from a raw contact size."""

    return binary32_store(contact_size) / 2.0


def enemy_lethal_to_damage_half_extent(lethal_half_extent: float) -> float:
    """Compatibility fallback when a legacy body lacks its raw contact size."""

    return float(lethal_half_extent) * ENEMY_LETHAL_FULL_SIZE_DIVISOR


__all__ = [
    "ENEMY_LETHAL_FULL_SIZE_DIVISOR",
    "enemy_contact_size_to_damage_half_extent",
    "enemy_contact_size_to_lethal_half_extent",
    "enemy_lethal_to_damage_half_extent",
]
