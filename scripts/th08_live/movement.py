"""TH08 input masks, movement geometry, and local planner actions."""

from __future__ import annotations

import numpy as np

from movement_model import MovementBounds
from th08_movement_model import step_route2_movement
from th08_local_planner import PlannerAction

SHOT = 0x01
BOMB = 0x02
FOCUS = 0x04
UP = 0x10
DOWN = 0x20
LEFT = 0x40
RIGHT = 0x80

PLAYFIELD_LEFT = 8.0
PLAYFIELD_RIGHT = 376.0
PLAYFIELD_TOP = 16.0
PLAYFIELD_BOTTOM = 432.0
# The live route is locked to Sakuya/Remilia.  Its native SHT lethal box and
# every stable GEO-001A root capture use a 2x2 box centered on the player.
# Keep PLAYER_RADIUS as the legacy conservative radius used by the still-
# approximate laser/corridor paths; bullet and enemy-body AABBs use the
# source-authoritative axis extents below.
PLAYER_LETHAL_HALF_WIDTH = 1.0
PLAYER_LETHAL_HALF_HEIGHT = 1.0
PLAYER_RADIUS = 2.0
FOCUSED_CARDINAL_SPEED = 2.299999952316284
FOCUSED_DIAGONAL_SPEED = 1.6263456344604492
UNFOCUSED_CARDINAL_SPEED = 4.0
UNFOCUSED_DIAGONAL_SPEED = 2.8284270763397217
_LIVE_MOVEMENT_BOUNDS = MovementBounds(
    PLAYFIELD_LEFT,
    PLAYFIELD_TOP,
    PLAYFIELD_RIGHT,
    PLAYFIELD_BOTTOM,
)


def _action(
    name: str,
    direction: int,
    unit_x: float,
    unit_y: float,
    *,
    focused: bool,
) -> PlannerAction:
    diagonal = unit_x != 0.0 and unit_y != 0.0
    if focused:
        speed = (
            FOCUSED_DIAGONAL_SPEED
            if diagonal
            else FOCUSED_CARDINAL_SPEED
        )
    else:
        speed = (
            UNFOCUSED_DIAGONAL_SPEED
            if diagonal
            else UNFOCUSED_CARDINAL_SPEED
        )
    return PlannerAction(
        name,
        direction,
        unit_x * speed,
        unit_y * speed,
        focused,
    )


_DIRECTION_ACTIONS = (
    ("left", LEFT, -1.0, 0.0),
    ("right", RIGHT, 1.0, 0.0),
    ("up", UP, 0.0, -1.0),
    ("down", DOWN, 0.0, 1.0),
    ("up_left", UP | LEFT, -1.0, -1.0),
    ("up_right", UP | RIGHT, 1.0, -1.0),
    ("down_left", DOWN | LEFT, -1.0, 1.0),
    ("down_right", DOWN | RIGHT, 1.0, 1.0),
)

PLANNER_ACTIONS = (
    PlannerAction("stay", 0, 0.0, 0.0, True),
    *(
        _action(name, direction, unit_x, unit_y, focused=True)
        for name, direction, unit_x, unit_y in _DIRECTION_ACTIONS
    ),
    *(
        _action(
            f"{name}_fast",
            direction,
            unit_x,
            unit_y,
            focused=False,
        )
        for name, direction, unit_x, unit_y in _DIRECTION_ACTIONS
    ),
)
LOCAL_PIPELINE_STATE_ACTIONS = (
    *PLANNER_ACTIONS,
    PlannerAction("stay_unfocused", 0, 0.0, 0.0, False),
)


def action_name_from_mask(input_mask: int) -> str:
    direction = input_mask & (UP | DOWN | LEFT | RIGHT)
    if direction & (UP | LEFT) == UP | LEFT:
        name = "up_left"
    elif direction & (DOWN | LEFT) == DOWN | LEFT:
        name = "down_left"
    elif direction & (UP | RIGHT) == UP | RIGHT:
        name = "up_right"
    elif direction & (DOWN | RIGHT) == DOWN | RIGHT:
        name = "down_right"
    elif direction & DOWN:
        name = "down"
    elif direction & UP:
        name = "up"
    elif direction & LEFT:
        name = "left"
    elif direction & RIGHT:
        name = "right"
    else:
        return "stay"
    return name if input_mask & FOCUS else f"{name}_fast"


def local_pipeline_action_from_mask(input_mask: int) -> str:
    """Return the injective movement/focus local actuator state."""

    direction = input_mask & (UP | DOWN | LEFT | RIGHT)
    if direction == 0 and not input_mask & FOCUS:
        return "stay_unfocused"
    return action_name_from_mask(input_mask)


def project_player_for_read_lag(
    x: float,
    y: float,
    input_mask: int,
    frames: int,
    *,
    player_scale_bits: tuple[int, ...],
) -> tuple[float, float]:
    """Project held physical input through an already committed frame prefix."""

    if frames < 0:
        raise ValueError("movement projection frames cannot be negative")
    if len(player_scale_bits) < frames:
        raise ValueError(
            "player time-scale schedule does not cover movement projection"
        )
    if frames == 0:
        return x, y
    current_x = x
    current_y = y
    for scale_bits in player_scale_bits[:frames]:
        movement = step_route2_movement(
            x=current_x,
            y=current_y,
            input_mask=input_mask,
            time_scale_bits=scale_bits,
            bounds=_LIVE_MOVEMENT_BOUNDS,
        )
        current_x = movement.x
        current_y = movement.y
    return current_x, current_y


def advance_planner_action(
    x: float,
    y: float,
    action: PlannerAction,
    *,
    time_scale_bits: int,
) -> tuple[float, float]:
    """Apply one exact native-order movement step for a planner action."""

    input_mask = action.direction | (FOCUS if action.focused else 0)
    movement = step_route2_movement(
        x=x,
        y=y,
        input_mask=input_mask,
        time_scale_bits=time_scale_bits,
        bounds=_LIVE_MOVEMENT_BOUNDS,
    )
    return movement.x, movement.y


def minimum_travel_frames(
    x: float,
    y: float,
    target_x: float,
    target_y: float,
    *,
    tolerance: float = 6.0,
) -> float:
    horizontal = max(abs(x - target_x) - tolerance, 0.0)
    vertical = max(abs(y - target_y) - tolerance, 0.0)
    diagonal = min(horizontal, vertical)
    straight = max(horizontal, vertical) - diagonal
    return (
        diagonal / UNFOCUSED_DIAGONAL_SPEED
        + straight / UNFOCUSED_CARDINAL_SPEED
    )


def boundary_risk(x: float, y: float) -> float:
    horizontal = min(x - PLAYFIELD_LEFT, PLAYFIELD_RIGHT - x)
    vertical = min(y - PLAYFIELD_TOP, PLAYFIELD_BOTTOM - y)
    risk = 0.0
    if horizontal < 12.0:
        risk += 2.0 * (12.0 - horizontal) ** 2
    if vertical < 12.0:
        risk += 3.0 * (12.0 - vertical) ** 2
    if horizontal < 20.0 and vertical < 20.0:
        risk += (20.0 - horizontal) * (20.0 - vertical)
    return risk


def boundary_risk_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
) -> np.ndarray:
    """Vectorized form of :func:`boundary_risk` for packed branch batches."""

    horizontal = np.minimum(
        positions_x - PLAYFIELD_LEFT,
        PLAYFIELD_RIGHT - positions_x,
    ).astype(np.float64, copy=False)
    vertical = np.minimum(
        positions_y - PLAYFIELD_TOP,
        PLAYFIELD_BOTTOM - positions_y,
    ).astype(np.float64, copy=False)
    risk = np.zeros(positions_x.size, dtype=np.float64)
    horizontal_near = horizontal < 12.0
    vertical_near = vertical < 12.0
    corner_near = (horizontal < 20.0) & (vertical < 20.0)
    risk[horizontal_near] += (
        2.0 * np.square(12.0 - horizontal[horizontal_near])
    )
    risk[vertical_near] += (
        3.0 * np.square(12.0 - vertical[vertical_near])
    )
    risk[corner_near] += (
        (20.0 - horizontal[corner_near])
        * (20.0 - vertical[corner_near])
    )
    return risk


def boundary_control_reserve_deficit(
    x: float,
    y: float,
    *,
    reserve_distance: float,
) -> float:
    """Measure lost axis-wise control range near clamped boundaries."""

    if reserve_distance <= 0.0:
        return 0.0
    return sum(
        (
            max(reserve_distance - (x - PLAYFIELD_LEFT), 0.0),
            max(reserve_distance - (PLAYFIELD_RIGHT - x), 0.0),
            max(reserve_distance - (y - PLAYFIELD_TOP), 0.0),
            max(reserve_distance - (PLAYFIELD_BOTTOM - y), 0.0),
        )
    )


def directions_opposed(left: int, right: int) -> bool:
    horizontal = bool(left & LEFT and right & RIGHT) or bool(
        left & RIGHT and right & LEFT
    )
    vertical = bool(left & UP and right & DOWN) or bool(
        left & DOWN and right & UP
    )
    return horizontal or vertical


__all__ = [
    "BOMB",
    "DOWN",
    "FOCUS",
    "FOCUSED_CARDINAL_SPEED",
    "FOCUSED_DIAGONAL_SPEED",
    "LEFT",
    "LOCAL_PIPELINE_STATE_ACTIONS",
    "PLANNER_ACTIONS",
    "PLAYER_RADIUS",
    "PLAYFIELD_BOTTOM",
    "PLAYFIELD_LEFT",
    "PLAYFIELD_RIGHT",
    "PLAYFIELD_TOP",
    "RIGHT",
    "SHOT",
    "UNFOCUSED_CARDINAL_SPEED",
    "UNFOCUSED_DIAGONAL_SPEED",
    "UP",
    "action_name_from_mask",
    "advance_planner_action",
    "boundary_control_reserve_deficit",
    "boundary_risk",
    "boundary_risk_for_positions",
    "directions_opposed",
    "local_pipeline_action_from_mask",
    "minimum_travel_frames",
    "project_player_for_read_lag",
]
