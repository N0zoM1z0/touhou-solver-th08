"""Survival-first local planner objectives and terminal warning heuristics."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from th08_laser_runtime import Laser
from th08_live.local_hazards import _project_item
from th08_live.models import EnemyBody, Item
from th08_live.movement import (
    PLANNER_ACTIONS,
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
    minimum_travel_frames,
)
from th08_local_planner import SearchNode

COLLECTION_HALF_WIDTH = 24.0
ITEM_SAFETY_CLEARANCE = 8.0
# Item value is a bounded tie-breaker inside the viable action set. Raw item
# values range into the hundreds and previously overwhelmed the entire
# conservative-position cost, so a dense post-phase drop could pull the
# player through an incompletely observed boss-contact transition.
ITEM_UTILITY_WEIGHT = 0.25
ITEM_UTILITY_SATURATION = 32.0
ITEM_APPROACH_POTENTIAL_WEIGHT = 0.02
# Current acceptance work is survival-only. Items may still be collected
# passively, but cannot affect beam pruning, action choice, or predicted
# collections until promoted as a survival-equivalent tie-breaker.
ITEM_OBJECTIVES_ENABLED = False

HazardQuery = Callable[..., tuple[np.ndarray, np.ndarray, np.ndarray]]
AdvanceAction = Callable[..., tuple[float, float]]


def item_potential(
    x: float,
    y: float,
    *,
    step: int,
    selected_items: tuple[tuple[Item, float], ...],
    collected_mask: int,
) -> float:
    potential = 0.0
    for index, (item, value) in enumerate(selected_items):
        if collected_mask & (1 << index):
            continue
        item_x, item_y, confidence = _project_item(item, step)
        distance = math.hypot(x - item_x, y - item_y)
        if distance < 144.0:
            potential += (
                value * confidence * (144.0 - distance) / 144.0
            )
    return potential


def node_key(
    node: SearchNode,
    *,
    step: int,
    selected_items: tuple[tuple[Item, float], ...],
    target_x: float | None = None,
    target_y: float | None = None,
    target_deadline: int | None = None,
) -> tuple[int, float, float, float, float]:
    usable_item_utility = (
        node.item_utility
        if node.min_clearance >= ITEM_SAFETY_CLEARANCE
        else 0.0
    )
    potential = (
        item_potential(
            node.x,
            node.y,
            step=step,
            selected_items=selected_items,
            collected_mask=node.collected_mask,
        )
        if node.min_clearance >= ITEM_SAFETY_CLEARANCE
        else 0.0
    )
    raw_utility = (
        usable_item_utility
        + ITEM_APPROACH_POTENTIAL_WEIGHT * potential
    )
    utility = ITEM_UTILITY_SATURATION * (
        1.0 - math.exp(-raw_utility / ITEM_UTILITY_SATURATION)
    )
    safety_deficit = max(
        ITEM_SAFETY_CLEARANCE - node.min_clearance,
        0.0,
    )
    gate_deficit = 0.0
    if (
        target_x is not None
        and target_y is not None
        and target_deadline is not None
    ):
        required_frames = minimum_travel_frames(
            node.x,
            node.y,
            target_x,
            target_y,
        )
        gate_deficit = max(
            required_frames - max(target_deadline - step, 0),
            0.0,
        )
    return (
        node.collisions,
        gate_deficit,
        safety_deficit,
        node.risk - ITEM_UTILITY_WEIGHT * utility,
        -node.min_clearance,
    )


def terminal_threat_scores(
    nodes: list[SearchNode],
    *,
    hazards_for_positions: HazardQuery,
    advance_action: AdvanceAction,
    start_step: int,
    end_step: int,
    control_delay_frames: int,
    player_scale_bits: tuple[int, ...],
    bullet_frames: tuple[tuple[np.ndarray, ...], ...],
    laser_frames: tuple[tuple[Laser, ...], ...],
    enemy_bodies: tuple[EnemyBody, ...],
) -> dict[SearchNode, tuple[int, float]]:
    """Extend terminal actions cheaply; this is a warning, not a certificate."""

    if not nodes or end_step <= start_step:
        return {node: (0, math.inf) for node in nodes}
    if len(player_scale_bits) < end_step:
        raise ValueError(
            "player time-scale schedule does not cover terminal threat tail"
        )
    positions_x = np.asarray(
        [node.x for node in nodes],
        dtype=np.float32,
    )
    positions_y = np.asarray(
        [node.y for node in nodes],
        dtype=np.float32,
    )
    collisions = np.zeros(len(nodes), dtype=np.int32)
    minimum = np.full(len(nodes), np.inf, dtype=np.float64)
    for step in range(start_step + 1, end_step + 1):
        scale_bits = player_scale_bits[step - 1]
        advanced = tuple(
            advance_action(
                float(positions_x[index]),
                float(positions_y[index]),
                node.last_action,
                time_scale_bits=scale_bits,
            )
            for index, node in enumerate(nodes)
        )
        positions_x = np.fromiter(
            (position[0] for position in advanced),
            dtype=np.float32,
            count=len(nodes),
        )
        positions_y = np.fromiter(
            (position[1] for position in advanced),
            dtype=np.float32,
            count=len(nodes),
        )
        _, step_collisions, step_clearance = hazards_for_positions(
            positions_x,
            positions_y,
            step=control_delay_frames + step,
            bullet_frame=bullet_frames[step - 1],
            lasers=laser_frames[step - 1],
            enemy_bodies=enemy_bodies,
        )
        collisions += step_collisions
        minimum = np.minimum(minimum, step_clearance)
    return {
        node: (int(collisions[index]), float(minimum[index]))
        for index, node in enumerate(nodes)
    }


def terminal_threat_degeneracy(
    *,
    player_x: float,
    player_y: float,
    action_hold_frames: int,
    allowed_first_actions: tuple[str, ...] | None,
    viability_position_error: float,
) -> str | None:
    """Detect stale-policy control collapse near a clamped boundary."""

    if allowed_first_actions is None:
        return None
    allowed = set(allowed_first_actions)
    successors: set[tuple[float, float]] = set()
    action_count = 0
    clamped = False
    unclamped_motion = False
    for action in PLANNER_ACTIONS:
        if action.name not in allowed:
            continue
        action_count += 1
        raw_x = player_x + action.dx * action_hold_frames
        raw_y = player_y + action.dy * action_hold_frames
        successor_x = min(
            PLAYFIELD_RIGHT,
            max(PLAYFIELD_LEFT, raw_x),
        )
        successor_y = min(
            PLAYFIELD_BOTTOM,
            max(PLAYFIELD_TOP, raw_y),
        )
        action_clamped = (
            successor_x != raw_x or successor_y != raw_y
        )
        clamped |= action_clamped
        unclamped_motion |= (
            not action_clamped
            and (abs(action.dx) > 1e-6 or abs(action.dy) > 1e-6)
        )
        successors.add(
            (round(successor_x, 3), round(successor_y, 3))
        )
    off_grid_singleton = (
        action_count == 1 and viability_position_error > 1e-3
    )
    if off_grid_singleton:
        return "off_grid_singleton"
    if clamped and 0 < len(successors) < action_count:
        return (
            "partial_clamped_alias"
            if unclamped_motion
            else "complete_clamped_alias"
        )
    return None


__all__ = [
    "COLLECTION_HALF_WIDTH",
    "ITEM_APPROACH_POTENTIAL_WEIGHT",
    "ITEM_OBJECTIVES_ENABLED",
    "ITEM_SAFETY_CLEARANCE",
    "ITEM_UTILITY_SATURATION",
    "ITEM_UTILITY_WEIGHT",
    "item_potential",
    "node_key",
    "terminal_threat_degeneracy",
    "terminal_threat_scores",
]
