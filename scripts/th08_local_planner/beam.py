"""Baseline local beam expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .models import PlannerAction, SearchNode


@dataclass(frozen=True)
class BaselineBeamContext:
    initial_beam: tuple[SearchNode, ...]
    actions: tuple[PlannerAction, ...]
    action_hold_frames: int
    horizon: int
    effective_allowed_first_actions: tuple[str, ...] | None
    preserve_previous_direction_inertia: bool
    previous_direction: int
    previous_focus: bool
    selected_items: tuple[tuple[Any, float], ...]
    control_delay_frames: int
    bullet_frames: tuple[Any, ...]
    laser_frames: tuple[Any, ...]
    enemy_bodies: tuple[Any, ...]
    native_beam_enabled: bool
    planner_action_indices: dict[str, int]
    native_certificate_collisions: np.ndarray
    native_certificate_minimum: np.ndarray
    native_survival_preferred: np.ndarray
    native_safety_preferred: np.ndarray
    native_recovery_distance: np.ndarray
    beam_width: int
    beam_dedup_mode: str
    target_x: float | None
    target_y: float | None
    target_deadline: int | None
    item_safety_clearance: float
    collection_half_width: float
    playfield_left: float
    playfield_right: float
    playfield_top: float
    playfield_bottom: float
    recovery_reserve_distance: float
    diagonal_speed: float
    cardinal_speed: float
    player_scale_bits: tuple[int, ...]


def _within_held_action_boundary_window(
    *,
    x: float,
    y: float,
    playfield_left: float,
    playfield_right: float,
    playfield_top: float,
    playfield_bottom: float,
    cardinal_speed: float,
    action_hold_frames: int,
) -> bool:
    """Return whether one held action can consume the nearest edge reserve."""

    hold_escape_distance = cardinal_speed * action_hold_frames
    return hold_escape_distance > 0.0 and min(
        x - playfield_left,
        playfield_right - x,
        y - playfield_top,
        playfield_bottom - y,
    ) < hold_escape_distance


def _boundary_action_strata_required(
    context: BaselineBeamContext,
) -> bool:
    """Activate action diversity only in an irreversible boundary window.

    Action-family diversity is valuable at a boundary, where pruning the sole
    escape direction can be irreversible, but it is not free: reserving every
    action everywhere displaces globally better continuations.  Use the
    physical distance covered by one non-preemptible action hold as the
    generic activation window.
    """

    if not context.initial_beam:
        return False
    return any(
        _within_held_action_boundary_window(
            x=node.x,
            y=node.y,
            playfield_left=context.playfield_left,
            playfield_right=context.playfield_right,
            playfield_top=context.playfield_top,
            playfield_bottom=context.playfield_bottom,
            cardinal_speed=context.cardinal_speed,
            action_hold_frames=context.action_hold_frames,
        )
        for node in context.initial_beam
    )


def _retain_first_action_strata(
    nodes: list[SearchNode],
    *,
    step: int,
    beam_width: int,
    pruning_key: Callable[..., tuple[object, ...]],
) -> list[SearchNode]:
    """Keep one continuation per first action in the best hard class.

    A globally truncated beam can otherwise spend every slot on minor
    variations of one first action and discard a still-safe escape action.
    The first six pruning components are the non-tradeable collision,
    clearance, survival, and route-gate class.  Stratification never reserves
    an action from a worse hard class; remaining capacity is filled by the
    ordinary global ordering.
    """

    ranked = sorted(
        (
            (node, pruning_key(node, step=step))
            for node in nodes
        ),
        key=lambda value: value[1],
    )
    if len(ranked) <= beam_width:
        return [node for node, _key in ranked]

    best_hard_class = ranked[0][1][:6]
    leaders: dict[str, SearchNode] = {}
    for node, _key in ranked:
        leaders.setdefault(node.first_action.name, node)

    retained = [
        node
        for node, key in ranked
        if leaders[node.first_action.name] is node
        and key[:6] == best_hard_class
    ][:beam_width]
    retained_ids = {id(node) for node in retained}
    for node, _key in ranked:
        if len(retained) >= beam_width:
            break
        if id(node) in retained_ids:
            continue
        retained.append(node)
        retained_ids.add(id(node))
    return sorted(
        retained,
        key=lambda node: pruning_key(node, step=step),
    )


def run_baseline_beam(
    context: BaselineBeamContext,
    *,
    boundary_risk: Callable[[float, float], float],
    directions_opposed: Callable[[int, int], bool],
    project_item: Callable[[Any, int], tuple[float, float, float]],
    advance_action: Callable[..., tuple[float, float]],
    hazard_query: Callable[..., tuple[np.ndarray, np.ndarray, np.ndarray]],
    pruning_key: Callable[..., tuple[object, ...]],
    native_reducer: Callable[..., np.ndarray | None],
) -> list[SearchNode]:
    beam = list(context.initial_beam)
    preserve_boundary_action_strata = _boundary_action_strata_required(
        context
    )
    for step in range(1, context.horizon + 1):
        drafts: list[
            tuple[SearchNode, PlannerAction, float, float, float, int, float]
        ] = []
        draft_first_actions: list[PlannerAction] = []
        candidates: dict[
            tuple[int, int, int, bool, int]
            | tuple[int, int, int, bool, int, str]
            | tuple[float, float, int, bool, int, str],
            SearchNode,
        ] = {}
        for node in beam:
            actions = (
                context.actions
                if (step - 1) % context.action_hold_frames == 0
                else (node.last_action,)
            )
            if (
                step == 1
                and context.effective_allowed_first_actions is not None
            ):
                allowed = set(context.effective_allowed_first_actions)
                actions = tuple(
                    action for action in actions if action.name in allowed
                )
            for action in actions:
                x, y = advance_action(
                    node.x,
                    node.y,
                    action,
                    time_scale_bits=context.player_scale_bits[step - 1],
                )
                transition_risk = boundary_risk(x, y)
                if action.direction != node.last_action.direction:
                    transition_risk += 0.08
                if directions_opposed(
                    action.direction,
                    node.last_action.direction,
                ):
                    transition_risk += 24.0
                if action.focused != node.last_action.focused:
                    transition_risk += 0.12
                if (
                    step == 1
                    and context.preserve_previous_direction_inertia
                ):
                    if action.direction != context.previous_direction:
                        transition_risk += 0.08
                    if directions_opposed(
                        action.direction,
                        context.previous_direction,
                    ):
                        transition_risk += 24.0
                    if action.focused != context.previous_focus:
                        transition_risk += 0.12
                collected_mask = node.collected_mask
                item_utility = node.item_utility
                for index, (item, value) in enumerate(
                    context.selected_items
                ):
                    bit = 1 << index
                    if collected_mask & bit:
                        continue
                    item_x, item_y, confidence = project_item(item, step)
                    collection_allowed = item.motion_state != 3 and not (
                        item.motion_state == 5 and item.vy <= 0.0
                    )
                    if (
                        collection_allowed
                        and abs(x - item_x)
                        <= context.collection_half_width
                        and abs(y - item_y)
                        <= context.collection_half_width
                    ):
                        collected_mask |= bit
                        item_utility += value * confidence
                first_action = action if step == 1 else node.first_action
                drafts.append(
                    (
                        node,
                        action,
                        x,
                        y,
                        transition_risk,
                        collected_mask,
                        item_utility,
                    )
                )
                draft_first_actions.append(first_action)
        if not drafts:
            break

        positions_x = np.fromiter(
            (draft[2] for draft in drafts),
            dtype=np.float32,
        )
        positions_y = np.fromiter(
            (draft[3] for draft in drafts),
            dtype=np.float32,
        )
        hazard_risk, hazard_collisions, hazard_clearance = hazard_query(
            positions_x,
            positions_y,
            step=context.control_delay_frames + step,
            bullet_frame=context.bullet_frames[step - 1],
            lasers=context.laser_frames[step - 1],
            enemy_bodies=context.enemy_bodies,
        )
        if context.native_beam_enabled:
            candidate_risk = np.fromiter(
                (
                    draft[0].risk
                    + draft[4]
                    + float(hazard_risk[index])
                    for index, draft in enumerate(drafts)
                ),
                dtype=np.float64,
                count=len(drafts),
            )
            candidate_collisions = np.fromiter(
                (
                    draft[0].collisions
                    + int(hazard_collisions[index])
                    for index, draft in enumerate(drafts)
                ),
                dtype=np.int32,
                count=len(drafts),
            )
            candidate_minimum = np.fromiter(
                (
                    min(
                        draft[0].min_clearance,
                        float(hazard_clearance[index]),
                    )
                    for index, draft in enumerate(drafts)
                ),
                dtype=np.float64,
                count=len(drafts),
            )
            retained_indices = native_reducer(
                draft_x=np.fromiter(
                    (draft[2] for draft in drafts),
                    dtype=np.float64,
                    count=len(drafts),
                ),
                draft_y=np.fromiter(
                    (draft[3] for draft in drafts),
                    dtype=np.float64,
                    count=len(drafts),
                ),
                first_action=np.fromiter(
                    (
                        context.planner_action_indices[action.name]
                        for action in draft_first_actions
                    ),
                    dtype=np.int32,
                    count=len(drafts),
                ),
                last_direction=np.fromiter(
                    (draft[1].direction for draft in drafts),
                    dtype=np.int32,
                    count=len(drafts),
                ),
                last_focused=np.fromiter(
                    (draft[1].focused for draft in drafts),
                    dtype=np.uint8,
                    count=len(drafts),
                ),
                collected_mask=np.fromiter(
                    (draft[5] for draft in drafts),
                    dtype=np.uint32,
                    count=len(drafts),
                ),
                risk=candidate_risk,
                collisions=candidate_collisions,
                minimum_clearance=candidate_minimum,
                step=step,
                beam_width=context.beam_width,
                position_quantization=0.5,
                target_x=context.target_x,
                target_y=context.target_y,
                target_deadline=context.target_deadline,
                item_safety_clearance=context.item_safety_clearance,
                playfield_left=context.playfield_left,
                playfield_right=context.playfield_right,
                playfield_top=context.playfield_top,
                playfield_bottom=context.playfield_bottom,
                reserve_distance=context.recovery_reserve_distance,
                diagonal_speed=context.diagonal_speed,
                cardinal_speed=context.cardinal_speed,
                certificate_collisions=(
                    context.native_certificate_collisions
                ),
                certificate_minimum=context.native_certificate_minimum,
                survival_preferred=context.native_survival_preferred,
                safety_preferred=context.native_safety_preferred,
                recovery_distance=context.native_recovery_distance,
                preserve_first_action_strata=(
                    preserve_boundary_action_strata
                ),
            )
            if retained_indices is not None:
                retained_beam: list[SearchNode] = []
                for retained_index in retained_indices:
                    draft_index = int(retained_index)
                    (
                        node,
                        action,
                        x,
                        y,
                        _transition_risk,
                        collected_mask,
                        item_utility,
                    ) = drafts[draft_index]
                    clearance = float(hazard_clearance[draft_index])
                    retained_beam.append(
                        SearchNode(
                            x=x,
                            y=y,
                            first_action=(
                                draft_first_actions[draft_index]
                            ),
                            last_action=action,
                            risk=float(candidate_risk[draft_index]),
                            collisions=int(
                                candidate_collisions[draft_index]
                            ),
                            min_clearance=float(
                                candidate_minimum[draft_index]
                            ),
                            immediate_clearance=(
                                min(
                                    node.immediate_clearance,
                                    clearance,
                                )
                                if step == 1
                                else node.immediate_clearance
                            ),
                            collected_mask=collected_mask,
                            item_utility=item_utility,
                        )
                    )
                beam = retained_beam
                continue

        for draft_index, draft in enumerate(drafts):
            (
                node,
                action,
                x,
                y,
                transition_risk,
                collected_mask,
                item_utility,
            ) = draft
            clearance = float(hazard_clearance[draft_index])
            first_action = draft_first_actions[draft_index]
            candidate = SearchNode(
                x=x,
                y=y,
                first_action=first_action,
                last_action=action,
                risk=(
                    node.risk
                    + transition_risk
                    + float(hazard_risk[draft_index])
                ),
                collisions=(
                    node.collisions
                    + int(hazard_collisions[draft_index])
                ),
                min_clearance=min(node.min_clearance, clearance),
                immediate_clearance=(
                    min(node.immediate_clearance, clearance)
                    if step == 1
                    else node.immediate_clearance
                ),
                collected_mask=collected_mask,
                item_utility=item_utility,
            )
            quantized: (
                tuple[int, int, int, bool, int]
                | tuple[int, int, int, bool, int, str]
                | tuple[float, float, int, bool, int, str]
            ) = (
                int(round(x * 0.5)),
                int(round(y * 0.5)),
                action.direction,
                action.focused,
                collected_mask,
            )
            if (
                context.beam_dedup_mode == "first_action"
                or preserve_boundary_action_strata
            ):
                quantized = (*quantized, first_action.name)
            elif context.beam_dedup_mode == "exact_first_action":
                quantized = (
                    x,
                    y,
                    action.direction,
                    action.focused,
                    collected_mask,
                    first_action.name,
                )
            incumbent = candidates.get(quantized)
            if incumbent is None or pruning_key(
                candidate,
                step=step,
            ) < pruning_key(incumbent, step=step):
                candidates[quantized] = candidate
        if not candidates:
            break
        if preserve_boundary_action_strata:
            beam = _retain_first_action_strata(
                list(candidates.values()),
                step=step,
                beam_width=context.beam_width,
                pruning_key=pruning_key,
            )
        else:
            beam = sorted(
                candidates.values(),
                key=lambda node: pruning_key(node, step=step),
            )[: context.beam_width]
    return beam
