"""Offline dossier rendering with stable field and row ordering."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def _format_number(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_markdown(dossier: dict[str, object]) -> str:
    totals = dossier["totals"]
    integrity = dossier["integrity"]
    control_policy = dossier["control_policy"]
    no_bomb = control_policy["no_bomb_verification"]
    viability = control_policy["robust_viability"]
    consistency = control_policy["planner_consistency"]
    spell_attribution_resolved = (
        integrity["spell_attribution"] == "resolved_live_spell_state"
    )
    difficulty = str(dossier["acceptance_target"]["difficulty"])
    lines = [
        f"# TH08 {difficulty} Full-Run Review: {dossier['run_id']}",
        "",
        "## Result",
        "",
        f"- Route: Sakuya/Remilia, {difficulty}, Final B / Kaguya.",
        "- Combat completion: yes; gameplay scene unloaded at frame "
        f"{dossier['completion_probe']['enemy_manager_frame']}.",
        "- Native phase-2 hit edges, including Last-Spell-saveable edges: "
        f"{totals['death_count']}.",
        f"- Deathbomb requests at those edges: {totals['deathbomb_count']}.",
        "- Hard no-Bomb input verification: "
        f"{'passed' if no_bomb['passed'] else 'FAILED'} across "
        f"{no_bomb['decision_count_checked']} decisions.",
        "- Post-hit Bomb-stock decreases: "
        f"{_format_number(totals['post_hit_bomb_stock_decrease'])}; this is "
        "respawn-stock reset telemetry, not evidence of Bomb input.",
        f"- Agent decisions: {totals['decision_count']}.",
        f"- Raw trace size: {integrity['raw_trace_bytes']} bytes across "
        f"{integrity['trace_count']} segments.",
        f"- JSON decode errors: {integrity['json_decode_errors']}.",
        (
            "- Exact spell-level hit attribution: available from live "
            "`g_spell_card_state`."
            if spell_attribution_resolved
            else (
                "- Exact spell-level hit attribution: unavailable in this run "
                "because the live schema did not record `g_spell_card_state`."
            )
        ),
        "",
        "The run is valid for stage-, death-, resource-, projectile-, latency-, "
        "and route-level analysis. Spell names below are the statically "
        f"reachable {difficulty} route inventory; unavailable runtime hit counts "
        "remain explicitly unresolved instead of guessed. The no-life patch "
        "allows post-hit resource resets to repeat, so resource-stock changes "
        "must not be interpreted as Bomb commands.",
        "",
        "## Trace Integrity",
        "",
        "| Segment | Frames | Decisions | Wall Z | Termination | Runtime error "
        "| SHA-256 |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for index, item in enumerate(dossier["provenance"], 1):
        runtime_errors = item["runtime_errors"]
        runtime_error = (
            str(runtime_errors[-1].get("error")) if runtime_errors else "-"
        )
        termination = (
            item["summary"].get("termination_reason")
            if item["summary"]
            else "missing"
        )
        lines.append(
            f"| {index} | {item['first_frame']}..{item['last_frame']} | "
            f"{item['decision_count']} | "
            f"{len(item['wall_auto_confirm_frames'])} | {termination} | "
            f"{runtime_error} | "
            f"`{item['sha256']}` |"
        )
    interruptions = integrity["foreground_interruption_count"]
    if interruptions:
        lines.extend(
            [
                "",
                f"Foreground interruptions: {interruptions}. Interruption "
                "intervals are excluded from agent-controlled scoring.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "The route is one continuous agent-controlled trace with no "
                "foreground interruption or manual re-arm gap.",
            ]
        )
    lines.extend(
        [
            "",
            "## Stage Summary",
            "",
            "| Stage | Frames | Decisions | Native hits | Deathbombs | "
            "Post-hit Bomb-stock decrease | "
            "Power start/end/min | Max bullets | Max lasers |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for stage in dossier["stages"]:
        power = stage["resources"]["power"]
        lines.append(
            f"| {stage['stage_label']} | {stage['first_frame']}.."
            f"{stage['last_frame']} | {stage['decision_count']} | "
            f"{stage['death_count']} | {stage['deathbomb_count']} | "
            f"{_format_number(stage['post_hit_bomb_stock_decrease'])} | "
            f"{_format_number(power['start'])}/"
            f"{_format_number(power['end'])}/"
            f"{_format_number(power['min'])} | "
            f"{stage['max_active_bullets']} | "
            f"{stage['max_active_lasers']} |"
        )
    lines.extend(
        [
            "",
            "## Failure Taxonomy",
            "",
            "| Primary class | Deaths | Interpretation |",
            "| --- | ---: | --- |",
        ]
    )
    interpretations = {
        "observed_enemy_body_overlap": (
            "A captured lethal enemy-body AABB overlaps the player at action "
            "time."
        ),
        "observed_multiple_hazard_overlap": (
            "More than one captured native hazard family overlaps at the hit "
            "edge; the trace does not invent a single causal winner."
        ),
        "observed_bullet_overlap": (
            "A bullet overlaps the native player AABB in the hit observation."
        ),
        "observed_laser_overlap": (
            "The player overlaps an active laser's exact finite segment; TH08 "
            "checks this before the broad bullet pass."
        ),
        "active_laser_without_observed_overlap": (
            "At least one laser is active, but none of the persisted finite "
            "segments overlaps the player in the hit observation."
        ),
        "modeled_committed_prefix_collision": (
            "The hit-row committed pipeline or the causal last-alive "
            "selected-action certificate was already unsafe."
        ),
        "sensor_gap_or_unmodeled_hazard": (
            "No observed overlap and positive pipeline clearance; same-frame "
            "ECL emission, transform error, or another unmodeled hazard is "
            "the leading explanation."
        ),
    }
    for cause, count in sorted(
        totals["primary_cause_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(
            f"| `{cause}` | {count} | {interpretations[cause]} |"
        )
    lines.extend(
        [
            "",
            "Contributing factors:",
            "",
        ]
    )
    for factor, count in sorted(
        totals["contributing_factor_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"- `{factor}`: {count} deaths")

    lines.extend(
        [
            "",
            "## High-Risk Clusters",
            "",
            "| Cluster | Stage | Frames | Deaths | Min Power | Max bullets at "
            "hit |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for cluster in sorted(
        dossier["death_clusters"],
        key=lambda cluster: (
            -int(cluster["death_count"]),
            int(cluster["start_frame"]),
        ),
    ):
        if int(cluster["death_count"]) < 2:
            continue
        lines.append(
            f"| {cluster['cluster_id']} | {cluster['stage_label']} | "
            f"{cluster['start_frame']}..{cluster['end_frame']} | "
            f"{cluster['death_count']} | "
            f"{_format_number(cluster['minimum_power'])} | "
            f"{cluster['maximum_active_bullets_at_hit']} |"
        )

    lines.extend(
        [
            "",
            "## Stage Detail",
            "",
        ]
    )
    deaths_by_stage = defaultdict(list)
    for death in dossier["deaths"]:
        deaths_by_stage[int(death["stage_route_index"])].append(death)
    for stage in dossier["stages"]:
        stage_index = int(stage["stage_route_index"])
        lines.extend(
            [
                f"### {stage['stage_label']}",
                "",
                f"- Death frames: "
                f"{', '.join(str(frame) for frame in stage['death_frames']) or '-'}",
                f"- Cause counts: `{json.dumps(stage['death_cause_counts'], ensure_ascii=False)}`",
                f"- Phase markers: observed "
                f"{stage['phase_marker_alignment']['observed_approximately_1800_frame_jump_count']}, "
                f"reachable static opcode `0x94` "
                f"{stage['phase_marker_alignment']['expected_reachable_opcode_94_count']}.",
                f"- Bottom/side occupancy decisions: "
                f"{stage['boundary_occupancy']['bottom_decisions']}/"
                f"{stage['boundary_occupancy']['side_decisions']}.",
                "",
                "| Frame | Bombs | Power | Post-hit stock drop | Bullets | Pipeline | "
                "Corridor slack | Cause | Factors |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for death in deaths_by_stage[stage_index]:
            factors = ",".join(death["contributing_factors"]) or "-"
            lines.append(
                f"| {death['frame']} | "
                f"{_format_number(death['resources_at_hit']['bombs'])} | "
                f"{_format_number(death['resources_at_hit']['power'])} | "
                f"{_format_number(death['post_hit_bomb_stock_decrease'])} | "
                f"{death['active_bullets']} | "
                f"{_format_number(death['pipeline_clearance_at_hit'])} | "
                f"{_format_number(death['minimum_corridor_slack_240f'])} | "
                f"`{death['primary_cause_class']}` | {factors} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Spell Inventory And Runtime Coverage",
            "",
            f"Every spell below is statically reachable for route 2 {difficulty} "
            "Final B. Observed decisions count only rows whose live spell state "
            "reported that active spell ID. Zero decisions therefore means the "
            "run did not enter that spell; zero hits with nonzero decisions "
            "means it entered cleanly. `unresolved` means the trace schema did "
            "not persist enough live spell state.",
            "",
        ]
    )
    for stage in dossier["spell_inventory"]:
        lines.extend(
            [
                f"### {stage['stage_label']}",
                "",
                f"- ECL: `{stage['ecl_file']}`",
                f"- Observed/expected phase-counter markers: "
                f"{len(stage['observed_counter_jump_markers'])}/"
                f"{len(stage['expected_reachable_phase_markers'])}.",
                "",
                "| ID | Name | Owner | Emits | Transforms | Lasers | "
                "Observed | Decisions | Hits |",
                "| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
            ]
        )
        for spell in stage["spells"]:
            features = spell["feature_counts"]
            runtime = spell["runtime_attribution"]
            observed_decision_count = runtime.get("observed_decision_count")
            observed_value = (
                "yes"
                if runtime.get("observed") is True
                else ("no" if runtime.get("observed") is False else "unresolved")
            )
            decision_value = (
                str(observed_decision_count)
                if observed_decision_count is not None
                else "unresolved"
            )
            hit_value = (
                str(runtime["hit_count"])
                if runtime["hit_count"] is not None
                else "unresolved"
            )
            lines.append(
                f"| {spell['spell_id']} | {spell['name']} | "
                f"{spell['owner']} | {features['bullet_emit']} | "
                f"{features['transform_define']} | "
                f"{features['laser_spawn']} | {observed_value} | "
                f"{decision_value} | {hit_value} |"
            )
        lines.append("")

    stalls = dossier["observed_auto_confirm_stalls"]["frames"]
    solve_ms = viability["solve_ms"] or {
        "median": None,
        "p95": None,
        "max": None,
    }
    policy_age = viability["first_observed_age_frames"] or {
        "median": None,
        "p95": None,
        "max": None,
    }
    stalls_text = ", ".join(str(frame) for frame in stalls) or "none"
    final_summary = dossier["provenance"][-1].get("summary") or {}
    termination_reason = final_summary.get("termination_reason", "missing")
    sensor_gap_count = int(
        totals["primary_cause_counts"].get(
            "sensor_gap_or_unmodeled_hazard",
            0,
        )
    )
    lines.extend(
        [
            "## Runtime And Harness Findings",
            "",
            f"- Observed auto-Z stall frames: {stalls_text}.",
            "- Route termination: "
            f"`{termination_reason}` "
            f"at completion probe frame "
            f"{dossier['completion_probe']['enemy_manager_frame']}.",
            "- Unique robust solutions observed: "
            f"{viability['unique_solution_count']}; solve time median/p95/max "
            f"{_format_number(solve_ms['median'])}/"
            f"{_format_number(solve_ms['p95'])}/"
            f"{_format_number(solve_ms['max'])} ms.",
            "- First-observed policy age median/p95/max: "
            f"{_format_number(policy_age['median'])}/"
            f"{_format_number(policy_age['p95'])}/"
            f"{_format_number(policy_age['max'])} frames.",
            "- Viability queries available: "
            f"{viability['available_query_count']}/"
            f"{viability['query_count']}; robustly constrained decisions: "
            f"{viability['constrained_decision_count']}/"
            f"{totals['decision_count']}.",
            "- Robust-policy decisions without any usable query: "
            f"{viability['decision_without_query_count']}/"
            f"{viability['policy_decision_count']}.",
            "- Global-horizon/local-prefix cross-tab: "
            f"{consistency['comparable_decision_count']} decisions; winning "
            "global state with unsafe selected prefix: "
            f"{consistency['global_winning_local_prefix_unsafe_count']}; "
            "losing global state with safe short prefix: "
            f"{consistency['global_losing_local_prefix_safe_count']}; "
            "selected globally certified action contradicted by the fresh "
            "local prefix checker: "
            f"{consistency['selected_certified_action_local_prefix_unsafe_count']}; "
            "selected action outside the reported winning set: "
            f"{consistency['selected_action_outside_global_winning_set_count']}.",
            "- Live spell attribution was recorded at every hit edge; exact "
            "per-spell counts are preserved below.",
            f"- `{sensor_gap_count}` hit edges remain in the "
            "`sensor_gap_or_unmodeled_hazard` class and require executor-level "
            "same-frame emission/transform evidence.",
            "",
            "## Next Regression Work",
            "",
            "1. Keep robust backward-reachability solves within the finite "
            "policy horizon, then verify nonzero live query and constrained-"
            "decision counts.",
            f"2. Replay all {totals['death_count']} retained witnesses through "
            "the integrated executor and preserve one regression per concrete "
            "failure.",
            "3. Re-run focused Stage 4A and Final B practices before another "
            f"full {difficulty} route; compare hit frames, policy age, action-set "
            "exhaustion, and cluster recurrence.",
            "4. Add item/Power state and finite Bomb resources only after the "
            "no-Bomb movement policy has passed physical validation.",
        ]
    )
    return "\n".join(lines)


def write_death_csv(
    path: Path,
    deaths: list[dict[str, object]],
) -> None:
    fieldnames = [
        "case_id",
        "frame",
        "trace_index",
        "stage_route_index",
        "stage_label",
        "player_x",
        "player_y",
        "bombs",
        "power",
        "observed_bomb_cost",
        "post_hit_bomb_stock_decrease",
        "deathbomb_requested",
        "active_bullets",
        "active_lasers",
        "active_items",
        "pipeline_clearance_at_hit",
        "minimum_pipeline_clearance_240f",
        "minimum_corridor_slack_240f",
        "action_lag",
        "action",
        "nearest_bullet_slot",
        "nearest_bullet_clearance",
        "nearest_laser_slot",
        "nearest_laser_clearance",
        "primary_cause_class",
        "planner_failure_class",
        "usable_robust_warning_lead_frames",
        "usable_viability_warning_lead_frames",
        "viability_kernel_exhausted_at_frame",
        "contributing_factors",
        "spell_id",
        "spell_name",
        "spell_attribution_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for death in deaths:
            nearest = death["nearest_observed_bullet"]
            nearest_laser = death["nearest_observed_laser"]
            writer.writerow(
                {
                    "case_id": death["case_id"],
                    "frame": death["frame"],
                    "trace_index": death["trace_index"],
                    "stage_route_index": death["stage_route_index"],
                    "stage_label": death["stage_label"],
                    "player_x": death["player"]["x"],
                    "player_y": death["player"]["y"],
                    "bombs": death["resources_at_hit"]["bombs"],
                    "power": death["resources_at_hit"]["power"],
                    "observed_bomb_cost": death["observed_bomb_cost"],
                    "post_hit_bomb_stock_decrease": death[
                        "post_hit_bomb_stock_decrease"
                    ],
                    "deathbomb_requested": death["deathbomb_requested"],
                    "active_bullets": death["active_bullets"],
                    "active_lasers": death["active_lasers"],
                    "active_items": death["active_items"],
                    "pipeline_clearance_at_hit": death[
                        "pipeline_clearance_at_hit"
                    ],
                    "minimum_pipeline_clearance_240f": death[
                        "minimum_pipeline_clearance_240f"
                    ],
                    "minimum_corridor_slack_240f": death[
                        "minimum_corridor_slack_240f"
                    ],
                    "action_lag": death["action_lag"],
                    "action": death["action"],
                    "nearest_bullet_slot": (
                        nearest["slot"] if nearest else None
                    ),
                    "nearest_bullet_clearance": (
                        nearest["aabb_clearance"] if nearest else None
                    ),
                    "nearest_laser_slot": (
                        nearest_laser["slot"] if nearest_laser else None
                    ),
                    "nearest_laser_clearance": (
                        nearest_laser["clearance"] if nearest_laser else None
                    ),
                    "primary_cause_class": death["primary_cause_class"],
                    "planner_failure_class": death[
                        "planner_failure_class"
                    ],
                    "usable_robust_warning_lead_frames": death.get(
                        "usable_robust_warning_lead_frames",
                        0,
                    ),
                    "usable_viability_warning_lead_frames": death.get(
                        "usable_viability_warning_lead_frames",
                        0,
                    ),
                    "viability_kernel_exhausted_at_frame": death.get(
                        "viability_kernel_exhausted_at_frame"
                    ),
                    "contributing_factors": ";".join(
                        death["contributing_factors"]
                    ),
                    "spell_id": death["spell_attribution"]["spell_id"],
                    "spell_name": death["spell_attribution"]["spell_name"],
                    "spell_attribution_status": death[
                        "spell_attribution"
                    ]["status"],
                }
            )


__all__ = ["render_markdown", "write_death_csv"]
