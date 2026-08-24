"""Shared physical-contact and death-ledger attribution."""

from __future__ import annotations

import math
from collections import Counter

from analysis.th08_trial_report import STAGE_ROUTE_LABELS


DEATH_WINDOW_FRAMES = 240
CLUSTER_GAP_FRAMES = 600


def _case_prefix_for_difficulty(difficulty: str) -> str:
    prefixes = {
        "easy": "EASY",
        "normal": "NORMAL",
        "hard": "HARD",
        "lunatic": "LUN",
        "extra": "EXTRA",
    }
    try:
        return prefixes[difficulty.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported case difficulty {difficulty!r}") from exc


def _nearest_bullet(row: dict[str, object]) -> dict[str, object] | None:
    player = row["player"]
    candidates = []
    for bullet in row.get("nearby_bullets", ()):
        if not isinstance(bullet, list) or len(bullet) < 7:
            continue
        dx = abs(float(bullet[1]) - float(player["x"]))
        dy = abs(float(bullet[2]) - float(player["y"]))
        clearance_x = dx - (2.0 + float(bullet[5]))
        clearance_y = dy - (2.0 + float(bullet[6]))
        if clearance_x <= 0.0 and clearance_y <= 0.0:
            clearance = max(clearance_x, clearance_y)
        else:
            clearance = math.hypot(
                max(clearance_x, 0.0),
                max(clearance_y, 0.0),
            )
        candidates.append(
            {
                "slot": int(bullet[0]),
                "x": float(bullet[1]),
                "y": float(bullet[2]),
                "velocity_x": float(bullet[3]),
                "velocity_y": float(bullet[4]),
                "half_width": float(bullet[5]),
                "half_height": float(bullet[6]),
                "transform_flags": int(bullet[7]) if len(bullet) >= 8 else 0,
                "center_distance": math.hypot(dx, dy),
                "aabb_clearance": clearance,
            }
        )
    overlapping = [
        candidate
        for candidate in candidates
        if float(candidate["aabb_clearance"]) <= 0.0
    ]
    if overlapping:
        return min(
            overlapping,
            key=lambda candidate: candidate["center_distance"],
        )
    if candidates:
        return min(
            candidates,
            key=lambda candidate: candidate["center_distance"],
        )
    return None


def _nearest_laser(row: dict[str, object]) -> dict[str, object] | None:
    player = row["player"]
    player_x = float(player["x"])
    player_y = float(player["y"])
    candidates = []
    for slot, laser in enumerate(row.get("lasers", ())):
        if not isinstance(laser, list) or len(laser) < 6:
            continue
        origin_x = float(laser[0])
        origin_y = float(laser[1])
        angle = float(laser[2])
        tail = float(laser[3])
        head = float(laser[4])
        half_width = float(laser[5])
        cosine = math.cos(angle)
        sine = math.sin(angle)
        start_x = origin_x + cosine * tail
        start_y = origin_y + sine * tail
        end_x = origin_x + cosine * head
        end_y = origin_y + sine * head
        segment_x = end_x - start_x
        segment_y = end_y - start_y
        length_sq = segment_x * segment_x + segment_y * segment_y
        if length_sq <= 1e-9:
            projection = 0.0
        else:
            projection = min(
                1.0,
                max(
                    0.0,
                    (
                        (player_x - start_x) * segment_x
                        + (player_y - start_y) * segment_y
                    )
                    / length_sq,
                ),
            )
        closest_x = start_x + projection * segment_x
        closest_y = start_y + projection * segment_y
        center_distance = math.hypot(
            player_x - closest_x,
            player_y - closest_y,
        )
        candidates.append(
            {
                "slot": slot,
                "origin_x": origin_x,
                "origin_y": origin_y,
                "angle": angle,
                "tail": tail,
                "head": head,
                "half_width": half_width,
                "closest_x": closest_x,
                "closest_y": closest_y,
                "center_distance": center_distance,
                "clearance": center_distance - half_width - 2.0,
            }
        )
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate["clearance"])


def _nearest_enemy_body(
    row: dict[str, object],
) -> dict[str, object] | None:
    hit_observation = row.get("hit_contact_observation")
    if (
        isinstance(hit_observation, dict)
        and hit_observation.get("stable")
        and isinstance(hit_observation.get("player_lethal_aabb"), list)
    ):
        player_aabb = hit_observation["player_lethal_aabb"]
        if len(player_aabb) >= 4:
            candidates = []
            player_left, player_top, player_right, player_bottom = map(
                float,
                player_aabb[:4],
            )
            for body in hit_observation.get("enemy_bodies", ()):
                if not isinstance(body, list) or len(body) < 8:
                    continue
                x = float(body[1])
                y = float(body[2])
                half_width = float(body[5])
                half_height = float(body[6])
                dx = max(
                    player_left - (x + half_width),
                    (x - half_width) - player_right,
                )
                dy = max(
                    player_top - (y + half_height),
                    (y - half_height) - player_bottom,
                )
                clearance = (
                    max(dx, dy)
                    if dx <= 0.0 and dy <= 0.0
                    else math.hypot(max(dx, 0.0), max(dy, 0.0))
                )
                candidates.append(
                    {
                        "pointer": int(body[0]),
                        "x_at_observation": x,
                        "y_at_observation": y,
                        "velocity_x": float(body[3]),
                        "velocity_y": float(body[4]),
                        "internal_motion_x": (
                            float(body[9])
                            if len(body) >= 11 and body[9] is not None
                            else None
                        ),
                        "internal_motion_y": (
                            float(body[10])
                            if len(body) >= 11 and body[10] is not None
                            else None
                        ),
                        "half_width": half_width,
                        "half_height": half_height,
                        "flags": int(body[7]),
                        "observation_frame": int(
                            hit_observation["frame_after"]
                        ),
                        "player_lethal_aabb": [
                            player_left,
                            player_top,
                            player_right,
                            player_bottom,
                        ],
                        "exact_same_epoch": True,
                        "aabb_clearance": clearance,
                    }
                )
            if candidates:
                return min(
                    candidates,
                    key=lambda candidate: candidate["aabb_clearance"],
                )

    player = row["player"]
    action_frame = int(row["frame"])
    snapshot_value = row.get("enemy_body_snapshot_frame", action_frame)
    snapshot_frame = (
        action_frame if snapshot_value is None else int(snapshot_value)
    )
    elapsed = max(0, action_frame - snapshot_frame)
    candidates = []
    for body in row.get("enemy_bodies", ()):
        if not isinstance(body, list) or len(body) < 8:
            continue
        x = float(body[1]) + float(body[3]) * elapsed
        y = float(body[2]) + float(body[4]) * elapsed
        dx = abs(float(player["x"]) - x) - (2.0 + float(body[5]))
        dy = abs(float(player["y"]) - y) - (2.0 + float(body[6]))
        if dx <= 0.0 and dy <= 0.0:
            clearance = max(dx, dy)
        else:
            clearance = math.hypot(max(dx, 0.0), max(dy, 0.0))
        candidates.append(
            {
                "pointer": int(body[0]),
                "x_at_snapshot": float(body[1]),
                "y_at_snapshot": float(body[2]),
                "velocity_x": float(body[3]),
                "velocity_y": float(body[4]),
                "internal_motion_x": (
                    float(body[9])
                    if len(body) >= 11 and body[9] is not None
                    else None
                ),
                "internal_motion_y": (
                    float(body[10])
                    if len(body) >= 11 and body[10] is not None
                    else None
                ),
                "projected_x_at_action": x,
                "projected_y_at_action": y,
                "half_width": float(body[5]),
                "half_height": float(body[6]),
                "flags": int(body[7]),
                "snapshot_frame": snapshot_frame,
                "elapsed_frames": elapsed,
                "exact_same_epoch": False,
                "aabb_clearance": clearance,
            }
        )
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate["aabb_clearance"])


def _spell_attribution(row: dict[str, object]) -> dict[str, object]:
    spell = row.get("spell")
    if not isinstance(spell, dict):
        return {
            "status": "unresolved_current_trace_schema",
            "spell_id": None,
            "spell_name": None,
        }
    flags = int(spell.get("flags", 0))
    if not bool(spell.get("active")):
        return {
            "status": "no_active_spell_at_hit",
            "spell_id": None,
            "spell_name": None,
            "flags": flags,
        }
    return {
        "status": "resolved_live_spell_state",
        "spell_id": int(spell["spell_id"]),
        "spell_name": str(spell.get("name", "")),
        "flags": flags,
        "enemy_pointer": int(spell.get("enemy_pointer", 0)),
    }


def _input_mask_action(mask: int) -> str:
    directions = []
    if mask & 0x10:
        directions.append("up")
    if mask & 0x20:
        directions.append("down")
    if mask & 0x40:
        directions.append("left")
    if mask & 0x80:
        directions.append("right")
    action = "_".join(directions) if directions else "stay"
    if directions and not mask & 0x04:
        action += "_fast"
    if mask & 0x02:
        action += "+bomb"
    return action


def _classify_death(
    row: dict[str, object],
    *,
    window: list[dict[str, object]],
) -> tuple[
    str,
    list[str],
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    nearest_bullet = _nearest_bullet(row)
    nearest_laser = _nearest_laser(row)
    nearest_enemy_body = _nearest_enemy_body(row)
    last_alive = next(
        (
            sample
            for sample in reversed(window[:-1])
            if int(sample.get("player", {}).get("phase", 0)) == 0
            and int(
                sample.get("player", {}).get("phase_at_action", 0)
            )
            == 0
        ),
        None,
    )
    last_alive_selected_action_unsafe = (
        last_alive is not None and _robust_control_unsafe(last_alive)
    )
    pipeline = float(row["pipeline_clearance"])
    lasers = int(row["active_lasers"])
    exact_enemy_overlap = (
        nearest_enemy_body is not None
        and bool(nearest_enemy_body.get("exact_same_epoch"))
        and float(nearest_enemy_body["aabb_clearance"]) <= 0.0
    )
    if exact_enemy_overlap:
        hit_body_pointers = {
            int(pointer)
            for pointer in row.get("enemy_body_pointers", ())
        }
        causal_row = last_alive if last_alive is not None else row
        causal_body_pointers = {
            int(pointer)
            for pointer in causal_row.get("enemy_body_pointers", ())
        }
        pointer = int(nearest_enemy_body["pointer"])
        nearest_enemy_body["present_in_hit_decision_snapshot"] = (
            pointer in hit_body_pointers
        )
        nearest_enemy_body["present_in_causal_snapshot"] = (
            pointer in causal_body_pointers
        )
        # Compatibility field retained for downstream regression readers.  Its
        # intended semantics are the last action that could have prevented the
        # hit, not the already-too-late hit-detection decision.
        nearest_enemy_body["present_in_action_snapshot"] = (
            pointer in causal_body_pointers
        )
    exact_overlaps = sum(
        (
            exact_enemy_overlap,
            nearest_laser is not None
            and float(nearest_laser["clearance"]) <= 0.0,
            nearest_bullet is not None
            and float(nearest_bullet["aabb_clearance"]) <= 0.0,
        )
    )
    if exact_overlaps > 1:
        primary = "observed_multiple_hazard_overlap"
    elif exact_enemy_overlap:
        primary = "observed_enemy_body_overlap"
    elif (
        nearest_laser is not None
        and float(nearest_laser["clearance"]) <= 0.0
    ):
        primary = "observed_laser_overlap"
    elif (
        nearest_bullet is not None
        and float(nearest_bullet["aabb_clearance"]) <= 0.0
    ):
        primary = "observed_bullet_overlap"
    elif pipeline <= 0.0 or last_alive_selected_action_unsafe:
        primary = "modeled_committed_prefix_collision"
    elif lasers:
        primary = "active_laser_without_observed_overlap"
    else:
        primary = "sensor_gap_or_unmodeled_hazard"

    contributing = []
    player = row["player"]
    if (
        float(player["y"]) >= 428.0
        or float(player["x"]) <= 12.0
        or float(player["x"]) >= 372.0
    ):
        contributing.append("playfield_boundary")
    slacks = [
        float(sample["corridor_slack"])
        for sample in window
        if sample["corridor_slack"] is not None
    ]
    if slacks and min(slacks) < 0.0:
        contributing.append("corridor_deadline_miss")
    if _action_lag_over_model(row) or (
        last_alive is not None and _action_lag_over_model(last_alive)
    ):
        contributing.append("action_lag_over_model")
    if int(row["active_bullets"]) >= 1000:
        contributing.append("pool_density_over_1000")
    input_snapshot = row.get("input_snapshot")
    active_mask = (
        int(input_snapshot.get("current", row.get("mask", 0x05)))
        if isinstance(input_snapshot, dict)
        else int(row.get("mask", 0x05))
    )
    if "_fast" in _input_mask_action(active_mask):
        contributing.append("fast_mode")
    if (
        exact_enemy_overlap
        and not bool(nearest_enemy_body["present_in_action_snapshot"])
    ):
        contributing.append("enemy_body_absent_from_action_snapshot")
    return (
        primary,
        contributing,
        nearest_bullet,
        nearest_laser,
        nearest_enemy_body,
    )


def _action_lag_over_model(row: dict[str, object]) -> bool:
    """Whether issue lag exceeds the decision's complete delay support."""

    support = tuple(
        int(value) for value in row.get("control_delay_candidates", ())
    )
    support_high = (
        max(support)
        if support
        else int(row.get("control_delay_frames", 3))
    )
    return int(row.get("action_lag", 0)) > support_high


def _robust_control_unsafe(row: dict[str, object]) -> bool:
    robust = row.get("robust_control")
    if not isinstance(robust, dict) or not robust:
        return False
    return (
        int(robust.get("worst_collisions", 0)) > 0
        or float(robust.get("min_clearance", 9999.0)) < 0.0
    )


def _viability_action_set_empty(row: dict[str, object]) -> bool:
    viability = row.get("viability")
    if not isinstance(viability, dict) or not viability:
        return False
    return (
        bool(viability.get("available"))
        and bool(viability.get("support_covers_current", True))
    ) and (
        not bool(viability.get("state_viable"))
        or int(viability.get("safe_action_count", 0)) == 0
    )


def _death_ledger(
    decisions: list[dict[str, object]],
    *,
    case_prefix: str = "LUN",
) -> list[dict[str, object]]:
    deaths = []
    for index, row in enumerate(decisions):
        if not row["hit_started"]:
            continue
        frame = int(row["frame"])
        stage = int(row["stage_route_index"])
        trace_index = int(row["trace_index"])
        window = []
        cursor = index
        while cursor >= 0:
            sample = decisions[cursor]
            if (
                int(sample["trace_index"]) != trace_index
                or int(sample["stage_route_index"]) != stage
                or int(sample["frame"]) < frame - DEATH_WINDOW_FRAMES
            ):
                break
            window.append(sample)
            cursor -= 1
        window.reverse()
        last_alive = next(
            (
                sample
                for sample in reversed(window[:-1])
                if int(sample["player"]["phase"]) == 0
                and int(sample["player"]["phase_at_action"]) == 0
            ),
            None,
        )
        unsafe_suffix_start = None
        if (
            last_alive is not None
            and float(last_alive["pipeline_clearance"]) <= 0.0
        ):
            last_alive_index = window.index(last_alive)
            unsafe_suffix_start = last_alive
            for sample in reversed(window[:last_alive_index]):
                if (
                    int(sample["player"]["phase"]) != 0
                    or int(sample["player"]["phase_at_action"]) != 0
                    or float(sample["pipeline_clearance"]) > 0.0
                ):
                    break
                unsafe_suffix_start = sample
        robust_unsafe_suffix_start = None
        if last_alive is not None and _robust_control_unsafe(last_alive):
            last_alive_index = window.index(last_alive)
            robust_unsafe_suffix_start = last_alive
            for sample in reversed(window[:last_alive_index]):
                if (
                    int(sample["player"]["phase"]) != 0
                    or int(sample["player"]["phase_at_action"]) != 0
                    or not _robust_control_unsafe(sample)
                ):
                    break
                robust_unsafe_suffix_start = sample
        viability_empty_suffix_start = None
        if (
            last_alive is not None
            and _viability_action_set_empty(last_alive)
        ):
            last_alive_index = window.index(last_alive)
            viability_empty_suffix_start = last_alive
            for sample in reversed(window[:last_alive_index]):
                if (
                    int(sample["player"]["phase"]) != 0
                    or int(sample["player"]["phase_at_action"]) != 0
                    or not _viability_action_set_empty(sample)
                ):
                    break
                viability_empty_suffix_start = sample

        next_bombs = float(row["resources"]["bombs"])
        next_power = float(row["resources"]["power"])
        for sample in decisions[index + 1 :]:
            if (
                int(sample["trace_index"]) != trace_index
                or int(sample["stage_route_index"]) != stage
                or int(sample["frame"]) > frame + DEATH_WINDOW_FRAMES
            ):
                break
            bombs = float(sample["resources"]["bombs"])
            power = float(sample["resources"]["power"])
            if bombs != float(row["resources"]["bombs"]):
                next_bombs = bombs
                next_power = power
                break

        (
            primary,
            contributing,
            nearest_bullet,
            nearest_laser,
            nearest_enemy_body,
        ) = _classify_death(row, window=window)
        pipeline_samples = [
            float(sample["pipeline_clearance"]) for sample in window
        ]
        slack_samples = [
            float(sample["corridor_slack"])
            for sample in window
            if sample["corridor_slack"] is not None
        ]
        bombs_at_hit = float(row["resources"]["bombs"])
        input_snapshot = row.get("input_snapshot")
        active_input_mask = (
            int(input_snapshot.get("current", row["mask"]))
            if isinstance(input_snapshot, dict)
            else int(row["mask"])
        )
        if last_alive is None:
            planner_failure_class = "missing_pre_hit_alive_decision"
        elif viability_empty_suffix_start is not None:
            planner_failure_class = (
                "global_viability_kernel_exhausted_before_hit"
            )
        elif robust_unsafe_suffix_start is not None:
            planner_failure_class = "robust_action_set_exhausted_before_hit"
        elif float(last_alive["pipeline_clearance"]) <= 0.0:
            planner_failure_class = "committed_prefix_unsafe_before_hit"
        elif (
            float(last_alive["minimum_clearance"]) <= 0.0
            or primary
            in {
                "observed_bullet_overlap",
                "observed_laser_overlap",
                "observed_enemy_body_overlap",
                "observed_multiple_hazard_overlap",
            }
            or float(row["pipeline_clearance"]) <= 0.0
        ):
            planner_failure_class = (
                "late_collision_after_positive_causal_margin"
            )
        else:
            planner_failure_class = "unresolved_planner_failure"
        death = {
            "case_id": (
                f"{case_prefix}-S{stage}-F{frame}-"
                f"T{trace_index + 1}"
            ),
            "frame": frame,
            "trace_index": trace_index,
            "trace_path": row["trace_path"],
            "stage_route_index": stage,
            "stage_label": STAGE_ROUTE_LABELS.get(stage),
            "player": row["player"],
            "resources_at_hit": row["resources"],
            "post_hit_first_changed_resources": {
                "bombs": next_bombs,
                "power": next_power,
            },
            "post_hit_bomb_stock_decrease": max(
                0.0,
                bombs_at_hit - next_bombs,
            ),
            # V1 regression readers require this compatibility field. A stock
            # reset is not evidence that the controller pressed Bomb.
            "observed_bomb_cost": max(0.0, bombs_at_hit - next_bombs),
            "deathbomb_requested": "+deathbomb" in str(row["action"]),
            "action": row["action"],
            "mask": row["mask"],
            "issued_action_after_hit_detection": row["action"],
            "issued_mask_after_hit_detection": row["mask"],
            "active_input_action": _input_mask_action(active_input_mask),
            "active_input_mask": active_input_mask,
            "last_alive_decision": (
                {
                    "frame": int(last_alive["frame"]),
                    "issued_action": str(last_alive["action"]),
                    "issued_mask": int(last_alive["mask"]),
                    "active_input_action": _input_mask_action(
                        int(
                            last_alive.get("input_snapshot", {}).get(
                                "current",
                                last_alive["mask"],
                            )
                        )
                    ),
                    "active_input_mask": int(
                        last_alive.get("input_snapshot", {}).get(
                            "current",
                            last_alive["mask"],
                        )
                    ),
                    "pipeline_clearance": float(
                        last_alive["pipeline_clearance"]
                    ),
                    "minimum_clearance": float(
                        last_alive["minimum_clearance"]
                    ),
                    "action_hold_frames": int(
                        last_alive["action_hold_frames"]
                    ),
                    "control_delay_frames": int(
                        last_alive["control_delay_frames"]
                    ),
                    "control_delay_candidates": list(
                        last_alive["control_delay_candidates"]
                    ),
                    "robust_control": dict(
                        last_alive["robust_control"]
                    ),
                    "terminal_threat": dict(
                        last_alive["terminal_threat"]
                    ),
                    "viability": dict(last_alive["viability"]),
                    "action_lag": int(last_alive["action_lag"]),
                }
                if last_alive is not None
                else None
            ),
            "action_deadline_miss": {
                "at_hit": _action_lag_over_model(row),
                "last_alive": (
                    _action_lag_over_model(last_alive)
                    if last_alive is not None
                    else False
                ),
                "hit_action_lag": int(row["action_lag"]),
                "hit_support_high": max(
                    tuple(row["control_delay_candidates"])
                    or (int(row["control_delay_frames"]),)
                ),
                "last_alive_action_lag": (
                    int(last_alive["action_lag"])
                    if last_alive is not None
                    else None
                ),
                "last_alive_support_high": (
                    max(
                        tuple(last_alive["control_delay_candidates"])
                        or (int(last_alive["control_delay_frames"]),)
                    )
                    if last_alive is not None
                    else None
                ),
            },
            "usable_pipeline_warning_lead_frames": (
                frame - int(unsafe_suffix_start["frame"])
                if unsafe_suffix_start is not None
                else 0
            ),
            "usable_robust_warning_lead_frames": (
                frame - int(robust_unsafe_suffix_start["frame"])
                if robust_unsafe_suffix_start is not None
                else 0
            ),
            "robust_action_set_exhausted_at_frame": (
                int(robust_unsafe_suffix_start["frame"])
                if robust_unsafe_suffix_start is not None
                else None
            ),
            "usable_viability_warning_lead_frames": (
                frame - int(viability_empty_suffix_start["frame"])
                if viability_empty_suffix_start is not None
                else 0
            ),
            "viability_kernel_exhausted_at_frame": (
                int(viability_empty_suffix_start["frame"])
                if viability_empty_suffix_start is not None
                else None
            ),
            "planner_failure_class": planner_failure_class,
            "active_bullets": row["active_bullets"],
            "active_lasers": row["active_lasers"],
            "active_items": row["active_items"],
            "active_enemy_bodies": row["active_enemy_bodies"],
            "enemy_body_snapshot_frame": row[
                "enemy_body_snapshot_frame"
            ],
            "hit_contact_observation": row.get(
                "hit_contact_observation"
            ),
            "snapshot_lag": row["snapshot_lag"],
            "action_lag": row["action_lag"],
            "control_delay_frames": row["control_delay_frames"],
            "control_delay_candidates": list(
                row["control_delay_candidates"]
            ),
            "control_delay_estimator": dict(
                row["control_delay_estimator"]
            ),
            "robust_control": dict(row["robust_control"]),
            "terminal_threat": dict(row["terminal_threat"]),
            "viability": dict(row["viability"]),
            "read_ms": row["read_ms"],
            "plan_ms": row["plan_ms"],
            "pipeline_clearance_at_hit": row["pipeline_clearance"],
            "modeled_collision_evidence": (
                {
                    "hit_pipeline_unsafe": (
                        float(row["pipeline_clearance"]) <= 0.0
                    ),
                    "last_alive_selected_action_unsafe": (
                        last_alive is not None
                        and _robust_control_unsafe(last_alive)
                    ),
                    "last_alive_frame": (
                        int(last_alive["frame"])
                        if last_alive is not None
                        else None
                    ),
                }
                if primary == "modeled_committed_prefix_collision"
                else None
            ),
            "minimum_pipeline_clearance_240f": min(pipeline_samples),
            "minimum_corridor_slack_240f": (
                min(slack_samples) if slack_samples else None
            ),
            "corridor_lane": row["corridor_lane"],
            "nearest_observed_bullet": nearest_bullet,
            "observed_bullet_contact_candidate": (
                nearest_bullet
                if nearest_bullet is not None
                and float(nearest_bullet["aabb_clearance"]) <= 0.0
                else None
            ),
            "nearest_observed_laser": nearest_laser,
            "observed_laser_contact_candidate": (
                nearest_laser
                if nearest_laser is not None
                and float(nearest_laser["clearance"]) <= 0.0
                else None
            ),
            "nearest_observed_enemy_body": nearest_enemy_body,
            "observed_enemy_body_contact_candidate": (
                nearest_enemy_body
                if nearest_enemy_body is not None
                and bool(nearest_enemy_body.get("exact_same_epoch"))
                and float(nearest_enemy_body["aabb_clearance"]) <= 0.0
                else None
            ),
            "primary_cause_class": primary,
            "contributing_factors": contributing,
            "spell_attribution": _spell_attribution(row),
        }
        deaths.append(death)
    return deaths


def _death_clusters(
    deaths: list[dict[str, object]],
) -> list[dict[str, object]]:
    clusters = []
    current = []
    for death in deaths:
        if (
            current
            and (
                int(death["stage_route_index"])
                != int(current[-1]["stage_route_index"])
                or int(death["frame"]) - int(current[-1]["frame"])
                > CLUSTER_GAP_FRAMES
            )
        ):
            clusters.append(current)
            current = []
        current.append(death)
    if current:
        clusters.append(current)
    rendered = []
    for index, cluster in enumerate(clusters, 1):
        rendered.append(
            {
                "cluster_id": f"cluster-{index:02d}",
                "stage_route_index": cluster[0]["stage_route_index"],
                "stage_label": cluster[0]["stage_label"],
                "start_frame": cluster[0]["frame"],
                "end_frame": cluster[-1]["frame"],
                "death_count": len(cluster),
                "death_frames": [death["frame"] for death in cluster],
                "minimum_power": min(
                    float(death["resources_at_hit"]["power"])
                    for death in cluster
                ),
                "maximum_active_bullets_at_hit": max(
                    int(death["active_bullets"]) for death in cluster
                ),
                "cause_counts": dict(
                    Counter(
                        str(death["primary_cause_class"])
                        for death in cluster
                    )
                ),
            }
        )
    return rendered


case_prefix_for_difficulty = _case_prefix_for_difficulty
nearest_bullet = _nearest_bullet
nearest_laser = _nearest_laser
nearest_enemy_body = _nearest_enemy_body
spell_attribution = _spell_attribution
input_mask_action = _input_mask_action
classify_death = _classify_death
action_lag_over_model = _action_lag_over_model
robust_control_unsafe = _robust_control_unsafe
viability_action_set_empty = _viability_action_set_empty
build_death_ledger = _death_ledger
cluster_deaths = _death_clusters


__all__ = [
    "action_lag_over_model",
    "build_death_ledger",
    "case_prefix_for_difficulty",
    "classify_death",
    "cluster_deaths",
    "input_mask_action",
    "nearest_bullet",
    "nearest_enemy_body",
    "nearest_laser",
    "robust_control_unsafe",
    "spell_attribution",
    "viability_action_set_empty",
]
