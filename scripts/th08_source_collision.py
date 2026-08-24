"""Source-derived TH08 lethal geometry for shadow differentials.

This module has no action authority.  It isolates the collision predicates
matched in ``Player::FUN_0044a230``, ``Player::CalcLaserHitbox``,
``BulletManager::OnUpdate``, and ``Enemy::FUN_0042c290`` from the legacy
2-pixel scalar-radius/capsule approximation.  Robust uncertainty is retained
by the vectorized adapter so legacy-versus-source comparisons change geometry
and lifecycle semantics, not the surrounding risk policy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from th08_laser_runtime import Laser, PackedLaserFrame, pack_laser_frame
from th08_live.models import EnemyBody


TH08_SOURCE_COLLISION_SEMANTICS_VERSION = "th08-source-collision-v1"


def _require_player_half_extents(
    half_width: float,
    half_height: float,
) -> None:
    if (
        not math.isfinite(half_width)
        or not math.isfinite(half_height)
        or half_width < 0.0
        or half_height < 0.0
    ):
        raise ValueError("player lethal half-extents must be finite and nonnegative")


def player_half_extents_from_aabb(
    *,
    player_x: float,
    player_y: float,
    lethal_aabb: Sequence[float],
    center_tolerance: float = 1e-4,
) -> tuple[float, float]:
    """Validate one cached native player AABB and recover its half-extents."""

    if len(lethal_aabb) != 4:
        raise ValueError("player lethal AABB requires four coordinates")
    left, top, right, bottom = map(float, lethal_aabb)
    values = (player_x, player_y, left, top, right, bottom, center_tolerance)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("player lethal AABB values must be finite")
    if left > right or top > bottom:
        raise ValueError("player lethal AABB coordinates are unordered")
    if center_tolerance < 0.0:
        raise ValueError("player lethal AABB tolerance cannot be negative")
    center_x = (left + right) * 0.5
    center_y = (top + bottom) * 0.5
    if (
        not math.isclose(
            center_x,
            player_x,
            rel_tol=0.0,
            abs_tol=center_tolerance,
        )
        or not math.isclose(
            center_y,
            player_y,
            rel_tol=0.0,
            abs_tol=center_tolerance,
        )
    ):
        raise ValueError("player lethal AABB is not centered on the player root")
    return (right - left) * 0.5, (bottom - top) * 0.5


def source_bullet_lethal_eligible(
    *,
    native_state: int,
    callback_aux_state: int,
) -> bool:
    """Return the exact BulletManager gate for the lethal player call."""

    return native_state == 1 and callback_aux_state == 0


def source_aabb_clearance(
    *,
    player_x: float,
    player_y: float,
    player_half_width: float,
    player_half_height: float,
    hazard_x: float,
    hazard_y: float,
    hazard_half_width: float,
    hazard_half_height: float,
) -> float:
    """Signed inclusive-AABB clearance used by bullets and enemy bodies."""

    _require_player_half_extents(player_half_width, player_half_height)
    dx = abs(player_x - hazard_x) - (
        player_half_width + hazard_half_width
    )
    dy = abs(player_y - hazard_y) - (
        player_half_height + hazard_half_height
    )
    if dx <= 0.0 and dy <= 0.0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def source_laser_rectangle_clearance(
    *,
    player_x: float,
    player_y: float,
    player_half_width: float,
    player_half_height: float,
    laser: Laser,
) -> float:
    """Signed clearance after native rotation into laser-local coordinates."""

    _require_player_half_extents(player_half_width, player_half_height)
    cosine = math.cos(laser.angle)
    sine = math.sin(laser.angle)
    delta_x = player_x - laser.origin_x
    delta_y = player_y - laser.origin_y
    local_x = delta_x * cosine + delta_y * sine
    local_y = -delta_x * sine + delta_y * cosine
    center_x = (laser.tail + laser.head) * 0.5
    half_length = abs(laser.head - laser.tail) * 0.5
    dx = abs(local_x - center_x) - (half_length + player_half_width)
    dy = abs(local_y) - (laser.half_width + player_half_height)
    if dx <= 0.0 and dy <= 0.0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def _clearance_field(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    overlap = (dx <= 0.0) & (dy <= 0.0)
    return np.where(
        overlap,
        np.maximum(dx, dy),
        np.hypot(np.maximum(dx, 0.0), np.maximum(dy, 0.0)),
    )


def source_collision_hazards_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[Laser, ...] | PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
    player_half_width: float,
    player_half_height: float,
    filter_bullet_lifecycle: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized source geometry with legacy robust-risk weighting.

    The callback signature matches the local certificate engine after binding
    the player half-extents and lifecycle mode with ``functools.partial``.
    It is shadow-only until current-entity projection and callback coverage
    have their own hard certificate.
    """

    _require_player_half_extents(player_half_width, player_half_height)
    if positions_x.shape != positions_y.shape:
        raise ValueError("player position arrays must have identical shape")
    if step < 0:
        raise ValueError("source collision frame step cannot be negative")
    if len(bullet_frame) < 5:
        raise ValueError("bullet frame is missing legacy geometry fields")
    if filter_bullet_lifecycle and len(bullet_frame) < 7:
        raise ValueError("source collision frame is missing lifecycle fields")

    count = positions_x.size
    risk = np.zeros(count, dtype=np.float64)
    collisions = np.zeros(count, dtype=np.int32)
    minimum = np.full(count, np.inf, dtype=np.float64)
    time_weight = 1.0 / (1.0 + 0.08 * (step - 1))

    bullet_x, bullet_y, half_width, half_height, transformed = bullet_frame[:5]
    eligible = np.ones(bullet_x.shape, dtype=np.bool_)
    if filter_bullet_lifecycle:
        native_state = bullet_frame[5]
        callback_aux = bullet_frame[6]
        if native_state.shape != bullet_x.shape or callback_aux.shape != bullet_x.shape:
            raise ValueError("bullet lifecycle arrays do not match geometry")
        eligible = (native_state == 1) & (callback_aux == 0)
    if bullet_x.size and np.any(eligible):
        margin = 84.0
        relevant = (
            eligible
            & (bullet_x >= float(positions_x.min()) - margin)
            & (bullet_x <= float(positions_x.max()) + margin)
            & (bullet_y >= float(positions_y.min()) - margin)
            & (bullet_y <= float(positions_y.max()) + margin)
        )
        bullet_x = bullet_x[relevant]
        bullet_y = bullet_y[relevant]
        half_width = half_width[relevant]
        half_height = half_height[relevant]
        transformed = transformed[relevant]
        if bullet_x.size:
            position_relevant = (
                (bullet_x[None, :] >= positions_x[:, None] - margin)
                & (bullet_x[None, :] <= positions_x[:, None] + margin)
                & (bullet_y[None, :] >= positions_y[:, None] - margin)
                & (bullet_y[None, :] <= positions_y[:, None] + margin)
            )
            dx = np.abs(positions_x[:, None] - bullet_x[None, :]) - (
                player_half_width + half_width[None, :]
            )
            dy = np.abs(positions_y[:, None] - bullet_y[None, :]) - (
                player_half_height + half_height[None, :]
            )
            clearance = _clearance_field(dx, dy)
            collisions += (
                (clearance <= 0.0) & position_relevant
            ).sum(axis=1, dtype=np.int32)
            uncertainty = (
                0.2 * math.sqrt(step)
                + transformed.astype(np.float32)
                * min(10.0, 3.0 + 0.35 * step)
            )
            robust_clearance = np.where(
                position_relevant,
                clearance - uncertainty[None, :],
                np.inf,
            )
            minimum = np.minimum(minimum, robust_clearance.min(axis=1))
            danger = np.maximum(44.0 - robust_clearance, 0.0)
            risk += np.square(danger).sum(axis=1) * time_weight

    packed_lasers = (
        lasers if isinstance(lasers, PackedLaserFrame) else pack_laser_frame(lasers)
    )
    if packed_lasers.start_x.size:
        if any(
            values is None
            for values in (
                packed_lasers.rectangle_half_width,
                packed_lasers.rectangle_cosine,
                packed_lasers.rectangle_sine,
            )
        ):
            raise ValueError("packed laser frame lacks source rectangle fields")
        rectangle_half_width = packed_lasers.rectangle_half_width
        cosine = packed_lasers.rectangle_cosine
        sine = packed_lasers.rectangle_sine
        assert rectangle_half_width is not None
        assert cosine is not None
        assert sine is not None
        delta_x = positions_x[:, None] - packed_lasers.start_x[None, :]
        delta_y = positions_y[:, None] - packed_lasers.start_y[None, :]
        local_x = delta_x * cosine[None, :] + delta_y * sine[None, :]
        local_y = -delta_x * sine[None, :] + delta_y * cosine[None, :]
        segment_length = (
            packed_lasers.segment_x * cosine
            + packed_lasers.segment_y * sine
        )
        center_x = segment_length * 0.5
        dx = np.abs(local_x - center_x[None, :]) - (
            np.abs(segment_length)[None, :] * 0.5 + player_half_width
        )
        dy = np.abs(local_y) - (
            rectangle_half_width[None, :] + player_half_height
        )
        clearance = _clearance_field(dx, dy)
        collisions += (clearance <= 0.0).sum(axis=1, dtype=np.int32)
        uncertainty = (
            packed_lasers.base_uncertainty
            + np.minimum(
                6.0,
                packed_lasers.uncertainty_per_frame * step,
            )
        )
        robust_clearance = clearance - uncertainty[None, :]
        minimum = np.minimum(minimum, robust_clearance.min(axis=1))
        danger = np.maximum(56.0 - robust_clearance, 0.0)
        risk += 2.0 * np.square(danger).sum(axis=1) * time_weight

    if enemy_bodies:
        body_x = np.fromiter(
            (body.x + body.vx * step for body in enemy_bodies),
            dtype=np.float32,
        )
        body_y = np.fromiter(
            (body.y + body.vy * step for body in enemy_bodies),
            dtype=np.float32,
        )
        half_width = np.fromiter(
            (body.half_width + body.uncertainty for body in enemy_bodies),
            dtype=np.float32,
        )
        half_height = np.fromiter(
            (body.half_height + body.uncertainty for body in enemy_bodies),
            dtype=np.float32,
        )
        dx = np.abs(positions_x[:, None] - body_x[None, :]) - (
            player_half_width + half_width[None, :]
        )
        dy = np.abs(positions_y[:, None] - body_y[None, :]) - (
            player_half_height + half_height[None, :]
        )
        clearance = _clearance_field(dx, dy)
        collisions += (clearance <= 0.0).sum(axis=1, dtype=np.int32)
        robust_clearance = clearance - min(12.0, 0.5 * step)
        minimum = np.minimum(minimum, robust_clearance.min(axis=1))
        danger = np.maximum(64.0 - robust_clearance, 0.0)
        risk += 2.0 * np.square(danger).sum(axis=1) * time_weight

    return risk, collisions, minimum


__all__ = [
    "TH08_SOURCE_COLLISION_SEMANTICS_VERSION",
    "player_half_extents_from_aabb",
    "source_aabb_clearance",
    "source_bullet_lethal_eligible",
    "source_collision_hazards_for_positions",
    "source_laser_rectangle_clearance",
]
