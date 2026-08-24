"""TH08 local hazard projection and independent NumPy/native kernels."""

from __future__ import annotations

import math

import numpy as np

from th08_collision_versions import LIVE_LOCAL_COLLISION_SEMANTICS_VERSION
from th08_laser_runtime import (
    Laser,
    PackedLaserFrame as _PackedLaserFrame,
    pack_laser_frame as _pack_laser_frame,
)
from th08_live.models import Bullet, EnemyBody, Item, PackedBulletSnapshot
from th08_live.movement import (
    PLAYER_LETHAL_HALF_HEIGHT,
    PLAYER_LETHAL_HALF_WIDTH,
)
from touhou_control import native_backend


# Observed in the retained native root2129 H=8 lifecycle differential:
# state 2 remains in its spawn ANM through timer 9.  Each non-completing
# update adds velocity/2.  The timer-9 completion update first stores that
# half-step, transitions to state 1, then stores the ordinary full step in the
# same bullet-manager call.
_STATE2_COMPLETION_TIMER = 9
_RETIRED_BULLET_STATE = 5


def _source_aabb_overlap_mask(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    hazard_x: np.ndarray,
    hazard_y: np.ndarray,
    hazard_half_width: np.ndarray,
    hazard_half_height: np.ndarray,
) -> np.ndarray:
    """Fast local transcription of TH08's stored Float3 AABB predicate."""

    player_x = np.asarray(positions_x, dtype=np.float32)[:, None]
    player_y = np.asarray(positions_y, dtype=np.float32)[:, None]
    hazard_x = np.asarray(hazard_x, dtype=np.float32)[None, :]
    hazard_y = np.asarray(hazard_y, dtype=np.float32)[None, :]
    hazard_half_width = np.asarray(
        hazard_half_width,
        dtype=np.float32,
    )[None, :]
    hazard_half_height = np.asarray(
        hazard_half_height,
        dtype=np.float32,
    )[None, :]
    player_left = np.asarray(
        player_x - np.float32(PLAYER_LETHAL_HALF_WIDTH),
        dtype=np.float32,
    )
    player_right = np.asarray(
        player_x + np.float32(PLAYER_LETHAL_HALF_WIDTH),
        dtype=np.float32,
    )
    player_top = np.asarray(
        player_y - np.float32(PLAYER_LETHAL_HALF_HEIGHT),
        dtype=np.float32,
    )
    player_bottom = np.asarray(
        player_y + np.float32(PLAYER_LETHAL_HALF_HEIGHT),
        dtype=np.float32,
    )
    hazard_left = np.asarray(
        hazard_x - hazard_half_width,
        dtype=np.float32,
    )
    hazard_right = np.asarray(
        hazard_x + hazard_half_width,
        dtype=np.float32,
    )
    hazard_top = np.asarray(
        hazard_y - hazard_half_height,
        dtype=np.float32,
    )
    hazard_bottom = np.asarray(
        hazard_y + hazard_half_height,
        dtype=np.float32,
    )
    return ~(
        (player_left > hazard_right)
        | (player_top > hazard_bottom)
        | (player_right < hazard_left)
        | (player_bottom < hazard_top)
    )


def _align_clearance_sign(
    clearance: np.ndarray,
    overlap: np.ndarray,
) -> np.ndarray:
    """Retain the risk metric while making its sign match source booleans."""

    zero = np.asarray(0.0, dtype=clearance.dtype)
    positive = np.nextafter(zero, np.asarray(np.inf, dtype=clearance.dtype))
    return np.where(
        overlap,
        np.minimum(clearance, zero),
        np.maximum(clearance, positive),
    )


def _bullet_frame_without_retired_state(
    bullet_frame: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, ...]:
    """Remove native-retired and callback-disabled collision states."""

    if len(bullet_frame) < 6:
        return bullet_frame
    native_state = np.asarray(bullet_frame[5])
    retained = native_state != _RETIRED_BULLET_STATE
    if len(bullet_frame) >= 7:
        callback_aux = np.asarray(bullet_frame[6])
        retained &= callback_aux == 0
    if np.all(retained):
        return bullet_frame
    return tuple(np.asarray(field)[retained] for field in bullet_frame)


def _aabb_clearance(
    px: float, py: float, bullet_x: float, bullet_y: float, bullet: Bullet
) -> float:
    dx = abs(px - bullet_x) - (
        PLAYER_LETHAL_HALF_WIDTH + bullet.half_width
    )
    dy = abs(py - bullet_y) - (
        PLAYER_LETHAL_HALF_HEIGHT + bullet.half_height
    )
    if dx <= 0.0 and dy <= 0.0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def _segment_clearance(px: float, py: float, laser: Laser) -> float:
    cosine = math.cos(laser.angle)
    sine = math.sin(laser.angle)
    start_x = laser.origin_x + cosine * laser.tail
    start_y = laser.origin_y + sine * laser.tail
    end_x = laser.origin_x + cosine * laser.head
    end_y = laser.origin_y + sine * laser.head
    segment_x = end_x - start_x
    segment_y = end_y - start_y
    length_sq = segment_x * segment_x + segment_y * segment_y
    if length_sq <= 1e-9:
        distance = math.hypot(px - start_x, py - start_y)
    else:
        projection = max(
            0.0,
            min(
                1.0,
                ((px - start_x) * segment_x + (py - start_y) * segment_y)
                / length_sq,
            ),
        )
        nearest_x = start_x + projection * segment_x
        nearest_y = start_y + projection * segment_y
        distance = math.hypot(px - nearest_x, py - nearest_y)
    return distance - laser.half_width - PLAYER_RADIUS


def _project_item(item: Item, step: int) -> tuple[float, float, float]:
    """Short-horizon item estimate plus confidence in that estimate.

    State 2 stores interpolation endpoints in the velocity-area fields, so a
    live record without its timer/start/target tuple is deliberately treated
    as low confidence. States 3/5 are usable only as a coarse acceleration
    estimate until their state transition is observed on a later frame.
    """

    scale = 0.8
    if item.motion_state == 2:
        return item.x, item.y, 0.15
    acceleration = 0.0
    if item.motion_state == 0:
        acceleration = 0.03 * scale
    elif item.motion_state in (3, 5):
        acceleration = 0.05
    x = item.x + item.vx * scale * step
    y = item.y + item.vy * scale * step + 0.5 * acceleration * step * (step - 1)
    confidence = 1.0 if item.motion_state in (0, 1) else 0.4
    return x, y, confidence


def _item_value(item: Item, *, power: float, bombs: float) -> float:
    if item.item_type == 5:
        return 320.0
    if item.item_type == 3:
        return 240.0 if bombs < 8.0 else 0.0
    if item.item_type == 4:
        return 300.0 if power < 128.0 else 5.0
    if item.item_type == 2:
        return 90.0 if power < 128.0 else 3.0
    if item.item_type == 0:
        return 24.0 if power < 128.0 else 2.0
    if item.item_type == 7:
        return 10.0
    if item.item_type == 1:
        return 5.0 if item.full_value else 2.0
    if item.item_type in (6, 8):
        return 1.0
    return 0.0


def _select_items(
    items: tuple[Item, ...], *, power: float, bombs: float, limit: int = 12
) -> tuple[tuple[Item, float], ...]:
    ranked = [
        (item, _item_value(item, power=power, bombs=bombs))
        for item in items
        if item.motion_state in (0, 1, 2, 3, 5)
    ]
    ranked = [entry for entry in ranked if entry[1] > 0.0]
    ranked.sort(key=lambda entry: (-entry[1], entry[0].y, entry[0].slot))
    return tuple(ranked[:limit])


def _build_bullet_frames(
    bullets: tuple[Bullet, ...] | PackedBulletSnapshot,
    *,
    horizon: int,
    snapshot_lag: int,
) -> tuple[tuple[np.ndarray, ...], ...]:
    frames: list[tuple[np.ndarray, ...]] = []
    if isinstance(bullets, PackedBulletSnapshot):
        base_x = bullets.x
        base_y = bullets.y
        velocity_x = bullets.velocity_x
        velocity_y = bullets.velocity_y
        half_width = bullets.half_width
        half_height = bullets.half_height
        transformed = np.not_equal(bullets.transform_flags, 0)
        native_state = bullets.native_state
        native_state_timer_elapsed = bullets.native_state_timer_elapsed
        callback_aux = bullets.callback_aux
    else:
        base_x = np.fromiter(
            (bullet.x for bullet in bullets),
            dtype=np.float32,
        )
        base_y = np.fromiter(
            (bullet.y for bullet in bullets),
            dtype=np.float32,
        )
        velocity_x = np.fromiter(
            (bullet.vx for bullet in bullets),
            dtype=np.float32,
        )
        velocity_y = np.fromiter(
            (bullet.vy for bullet in bullets),
            dtype=np.float32,
        )
        half_width = np.fromiter(
            (bullet.half_width for bullet in bullets),
            dtype=np.float32,
        )
        half_height = np.fromiter(
            (bullet.half_height for bullet in bullets),
            dtype=np.float32,
        )
        trajectory_uncertainty_x = np.fromiter(
            (
                bullet.trajectory_uncertainty_x
                for bullet in bullets
            ),
            dtype=np.float32,
        )
        trajectory_uncertainty_y = np.fromiter(
            (
                bullet.trajectory_uncertainty_y
                for bullet in bullets
            ),
            dtype=np.float32,
        )
        half_width = half_width + trajectory_uncertainty_x
        half_height = half_height + trajectory_uncertainty_y
        transformed = np.fromiter(
            (bool(bullet.transform_flags) for bullet in bullets),
            dtype=np.bool_,
        )
        native_state = np.fromiter(
            (bullet.native_state for bullet in bullets),
            dtype=np.uint16,
        )
        native_state_timer_elapsed = np.fromiter(
            (bullet.native_state_timer_elapsed for bullet in bullets),
            dtype=np.int32,
        )
        callback_aux = np.fromiter(
            (bullet.callback_aux_state for bullet in bullets),
            dtype=np.uint8,
        )
    event_indices: list[int] = []
    event_frames: list[int] = []
    event_velocity_x: list[float] = []
    event_velocity_y: list[float] = []
    collision_event_indices: list[int] = []
    collision_event_frames: list[int] = []
    collision_event_enabled: list[bool] = []
    if not isinstance(bullets, PackedBulletSnapshot):
        for bullet_index, bullet in enumerate(bullets):
            for change in bullet.velocity_changes:
                event_indices.append(bullet_index)
                event_frames.append(change.frame)
                event_velocity_x.append(change.velocity_x)
                event_velocity_y.append(change.velocity_y)
            for change in bullet.collision_state_changes:
                collision_event_indices.append(bullet_index)
                collision_event_frames.append(change.frame)
                collision_event_enabled.append(change.collision_enabled)
    packed_event_indices = np.asarray(event_indices, dtype=np.intp)
    packed_event_frames = np.asarray(event_frames, dtype=np.int32)
    packed_event_velocity_x = np.asarray(event_velocity_x, dtype=np.float32)
    packed_event_velocity_y = np.asarray(event_velocity_y, dtype=np.float32)
    packed_collision_event_indices = np.asarray(
        collision_event_indices,
        dtype=np.intp,
    )
    packed_collision_event_frames = np.asarray(
        collision_event_frames,
        dtype=np.int32,
    )
    packed_collision_event_enabled = np.asarray(
        collision_event_enabled,
        dtype=np.bool_,
    )
    projected_x = base_x.copy()
    projected_y = base_y.copy()
    current_velocity_x = velocity_x.copy()
    current_velocity_y = velocity_y.copy()
    projected_native_state = native_state.copy()
    projected_state_timer_elapsed = native_state_timer_elapsed.copy()
    callback_aux = callback_aux.copy()
    projected_elapsed = 0
    for step in range(1, horizon + 1):
        elapsed = snapshot_lag + step
        if elapsed <= 0:
            # Negative snapshot alignment has no native future-update
            # recurrence. Preserve the existing linear rewind convention.
            frame_x = base_x + velocity_x * elapsed
            frame_y = base_y + velocity_y * elapsed
        else:
            while projected_elapsed < elapsed:
                projected_elapsed += 1
                active = packed_event_frames == projected_elapsed
                if np.any(active):
                    current_velocity_x[packed_event_indices[active]] = (
                        packed_event_velocity_x[active]
                    )
                    current_velocity_y[packed_event_indices[active]] = (
                        packed_event_velocity_y[active]
                    )
                collision_active = (
                    packed_collision_event_frames == projected_elapsed
                )
                if np.any(collision_active):
                    callback_aux[
                        packed_collision_event_indices[collision_active]
                    ] = np.where(
                        packed_collision_event_enabled[collision_active],
                        0,
                        1,
                    )
                # Native bullet motion stores binary32 after every update.
                # State 2 is a distinct spawn-animation recurrence: a
                # non-completing update takes one half-step, while completion
                # takes a separately rounded half-step and full step.
                state2 = projected_native_state == 2
                ordinary = ~state2
                if np.any(ordinary):
                    projected_x[ordinary] = (
                        projected_x[ordinary]
                        + current_velocity_x[ordinary]
                    )
                    projected_y[ordinary] = (
                        projected_y[ordinary]
                        + current_velocity_y[ordinary]
                    )
                if np.any(state2):
                    half_velocity_x = (
                        current_velocity_x[state2] * np.float32(0.5)
                    )
                    half_velocity_y = (
                        current_velocity_y[state2] * np.float32(0.5)
                    )
                    projected_x[state2] = (
                        projected_x[state2] + half_velocity_x
                    )
                    projected_y[state2] = (
                        projected_y[state2] + half_velocity_y
                    )
                    completing = (
                        state2
                        & (
                            projected_state_timer_elapsed
                            >= _STATE2_COMPLETION_TIMER
                        )
                    )
                    if np.any(completing):
                        projected_x[completing] = (
                            projected_x[completing]
                            + current_velocity_x[completing]
                        )
                        projected_y[completing] = (
                            projected_y[completing]
                            + current_velocity_y[completing]
                        )
                        projected_native_state[completing] = 1
                        projected_state_timer_elapsed[completing] = 1
                    continuing = state2 & ~completing
                    projected_state_timer_elapsed[continuing] += 1
            frame_x = projected_x.copy()
            frame_y = projected_y.copy()
        frames.append(
            (
                frame_x,
                frame_y,
                half_width,
                half_height,
                transformed,
                projected_native_state.copy(),
                callback_aux.copy(),
            )
        )
    return tuple(frames)


def _numpy_hazards_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[Laser, ...] | _PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = positions_x.size
    risk = np.zeros(count, dtype=np.float64)
    collisions = np.zeros(count, dtype=np.int32)
    minimum = np.full(count, np.inf, dtype=np.float64)
    time_weight = 1.0 / (1.0 + 0.08 * (step - 1))
    bullet_frame = _bullet_frame_without_retired_state(bullet_frame)
    bullet_x, bullet_y, half_width, half_height, transformed = bullet_frame[:5]
    if bullet_x.size:
        margin = 84.0
        relevant = (
            (bullet_x >= float(positions_x.min()) - margin)
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
                PLAYER_LETHAL_HALF_WIDTH + half_width[None, :]
            )
            dy = np.abs(positions_y[:, None] - bullet_y[None, :]) - (
                PLAYER_LETHAL_HALF_HEIGHT + half_height[None, :]
            )
            overlap = _source_aabb_overlap_mask(
                positions_x,
                positions_y,
                bullet_x,
                bullet_y,
                half_width,
                half_height,
            )
            clearance = np.where(
                (dx <= 0.0) & (dy <= 0.0),
                np.maximum(dx, dy),
                np.hypot(np.maximum(dx, 0.0), np.maximum(dy, 0.0)),
            )
            clearance = _align_clearance_sign(clearance, overlap)
            collisions += (
                overlap & position_relevant
            ).sum(axis=1, dtype=np.int32)
            uncertainty = 0.2 * math.sqrt(step) + transformed.astype(np.float32) * min(
                10.0, 3.0 + 0.35 * step
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
        lasers
        if isinstance(lasers, _PackedLaserFrame)
        else _pack_laser_frame(lasers)
    )
    if packed_lasers.start_x.size:
        start_x = packed_lasers.start_x
        start_y = packed_lasers.start_y
        segment_x = packed_lasers.segment_x
        segment_y = packed_lasers.segment_y
        uncertainty = (
            packed_lasers.base_uncertainty
            + np.minimum(
                6.0,
                packed_lasers.uncertainty_per_frame * step,
            )
        )
        occupied_radius = packed_lasers.collision_radius + uncertainty
        margin = 56.0
        relevant = (
            (
                np.maximum(start_x, start_x + segment_x)
                + occupied_radius
                >= float(positions_x.min()) - margin
            )
            & (
                np.minimum(start_x, start_x + segment_x)
                - occupied_radius
                <= float(positions_x.max()) + margin
            )
            & (
                np.maximum(start_y, start_y + segment_y)
                + occupied_radius
                >= float(positions_y.min()) - margin
            )
            & (
                np.minimum(start_y, start_y + segment_y)
                - occupied_radius
                <= float(positions_y.max()) + margin
            )
        )
        if np.any(relevant):
            start_x = start_x[relevant]
            start_y = start_y[relevant]
            segment_x = segment_x[relevant]
            segment_y = segment_y[relevant]
            collision_radius = packed_lasers.collision_radius[relevant]
            uncertainty = uncertainty[relevant]
            occupied_radius = collision_radius + uncertainty
            position_relevant = (
                (
                    np.maximum(start_x, start_x + segment_x)[None, :]
                    + occupied_radius[None, :]
                    >= positions_x[:, None] - margin
                )
                & (
                    np.minimum(start_x, start_x + segment_x)[None, :]
                    - occupied_radius[None, :]
                    <= positions_x[:, None] + margin
                )
                & (
                    np.maximum(start_y, start_y + segment_y)[None, :]
                    + occupied_radius[None, :]
                    >= positions_y[:, None] - margin
                )
                & (
                    np.minimum(start_y, start_y + segment_y)[None, :]
                    - occupied_radius[None, :]
                    <= positions_y[:, None] + margin
                )
            )
            length_sq = segment_x * segment_x + segment_y * segment_y
            flat_x = positions_x[:, None]
            flat_y = positions_y[:, None]
            numerator = (
                (flat_x - start_x[None, :]) * segment_x[None, :]
                + (flat_y - start_y[None, :]) * segment_y[None, :]
            )
            projection = np.divide(
                numerator,
                length_sq[None, :],
                out=np.zeros_like(numerator),
                where=length_sq[None, :] > 1e-9,
            )
            projection = np.clip(projection, 0.0, 1.0)
            distance = np.hypot(
                flat_x - (start_x + projection * segment_x),
                flat_y - (start_y + projection * segment_y),
            )
            clearance = distance - collision_radius[None, :]
            collisions += (
                (clearance <= 0.0) & position_relevant
            ).sum(
                axis=1,
                dtype=np.int32,
            )
            robust_clearance = np.where(
                position_relevant,
                clearance - uncertainty[None, :],
                np.inf,
            )
            minimum = np.minimum(
                minimum,
                robust_clearance.min(axis=1),
            )
            danger = np.maximum(56.0 - robust_clearance, 0.0)
            risk += (
                2.0 * np.square(danger).sum(axis=1) * time_weight
            )
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
            (
                body.half_width + body.uncertainty
                for body in enemy_bodies
            ),
            dtype=np.float32,
        )
        half_height = np.fromiter(
            (
                body.half_height + body.uncertainty
                for body in enemy_bodies
            ),
            dtype=np.float32,
        )
        dx = np.abs(positions_x[:, None] - body_x[None, :]) - (
            PLAYER_LETHAL_HALF_WIDTH + half_width[None, :]
        )
        dy = np.abs(positions_y[:, None] - body_y[None, :]) - (
            PLAYER_LETHAL_HALF_HEIGHT + half_height[None, :]
        )
        overlap = _source_aabb_overlap_mask(
            positions_x,
            positions_y,
            body_x,
            body_y,
            half_width,
            half_height,
        )
        clearance = np.where(
            (dx <= 0.0) & (dy <= 0.0),
            np.maximum(dx, dy),
            np.hypot(np.maximum(dx, 0.0), np.maximum(dy, 0.0)),
        )
        clearance = _align_clearance_sign(clearance, overlap)
        collisions += overlap.sum(axis=1, dtype=np.int32)
        robust_clearance = clearance - min(12.0, 0.5 * step)
        minimum = np.minimum(minimum, robust_clearance.min(axis=1))
        danger = np.maximum(64.0 - robust_clearance, 0.0)
        risk += 2.0 * np.square(danger).sum(axis=1) * time_weight
    return risk, collisions, minimum


def _native_hazards_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[Laser, ...] | _PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parity-gated native implementation of `_hazards_for_positions`."""

    bullet_frame = _bullet_frame_without_retired_state(bullet_frame)
    bullet_x, bullet_y, half_width, half_height, transformed = bullet_frame[:5]
    packed_lasers = (
        lasers
        if isinstance(lasers, _PackedLaserFrame)
        else _pack_laser_frame(lasers)
    )
    (
        laser_start_x,
        laser_start_y,
        laser_segment_x,
        laser_segment_y,
        laser_collision_radius,
        laser_base_uncertainty,
        laser_uncertainty_per_frame,
    ) = packed_lasers.fields_for_native()
    body_x = np.fromiter(
        (body.x + body.vx * step for body in enemy_bodies),
        dtype=np.float32,
        count=len(enemy_bodies),
    )
    body_y = np.fromiter(
        (body.y + body.vy * step for body in enemy_bodies),
        dtype=np.float32,
        count=len(enemy_bodies),
    )
    body_half_width = np.fromiter(
        (
            body.half_width + body.uncertainty
            for body in enemy_bodies
        ),
        dtype=np.float32,
        count=len(enemy_bodies),
    )
    body_half_height = np.fromiter(
        (
            body.half_height + body.uncertainty
            for body in enemy_bodies
        ),
        dtype=np.float32,
        count=len(enemy_bodies),
    )
    result = native_backend.query_local_hazards(
        positions_x=positions_x,
        positions_y=positions_y,
        step=step,
        player_radius=PLAYER_LETHAL_HALF_WIDTH,
        bullet_x=bullet_x,
        bullet_y=bullet_y,
        bullet_half_width=half_width,
        bullet_half_height=half_height,
        bullet_transformed=transformed,
        laser_start_x=laser_start_x,
        laser_start_y=laser_start_y,
        laser_segment_x=laser_segment_x,
        laser_segment_y=laser_segment_y,
        laser_collision_radius=laser_collision_radius,
        laser_base_uncertainty=laser_base_uncertainty,
        laser_uncertainty_per_frame=laser_uncertainty_per_frame,
        body_x=body_x,
        body_y=body_y,
        body_half_width=body_half_width,
        body_half_height=body_half_height,
    )
    if result is None:
        raise RuntimeError("native local hazard kernel is unavailable")
    return result
