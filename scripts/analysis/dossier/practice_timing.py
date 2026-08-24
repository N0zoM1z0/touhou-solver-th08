"""Practice-run timing and native-sensor summaries."""

from __future__ import annotations

from collections import Counter

from analysis.dossier.statistics import percentiles as _percentiles


TERMINAL_THREAT_SAFETY_CLEARANCE = 8.0
ENEMY_POOL_BASE = 0x005826C0
ENEMY_POOL_SIZE = 480
ENEMY_STRIDE = 0x53D0


def _corridor_latency(
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    unique: dict[int, dict[str, object]] = {}
    for row in decisions:
        source = row.get("corridor_source_frame")
        if source is None:
            continue
        unique.setdefault(int(source), row)

    def stats(
        rows: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "unique_solution_count": len(rows),
            "solve_ms": _percentiles(
                float(row["corridor_solve_ms"]) for row in rows
            ),
            "age_frames": _percentiles(
                float(row["corridor_age"]) for row in rows
            ),
            "stale_solution_count": sum(
                bool(row["corridor_stale"]) for row in rows
            ),
        }

    unique_rows = list(unique.values())
    spell_50_rows = [
        row
        for row in unique_rows
        if isinstance(row.get("spell"), dict)
        and bool(row["spell"].get("active"))
        and int(row["spell"].get("spell_id", -1)) == 50
    ]
    return {
        "all": stats(unique_rows),
        "active_spell_50": stats(spell_50_rows),
    }


def _decision_cadence(
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    deltas = [
        int(right["frame"]) - int(left["frame"])
        for left, right in zip(decisions, decisions[1:])
        if 0 < int(right["frame"]) - int(left["frame"]) < 120
    ]
    percentiles = _percentiles(deltas) or {
        "median": None,
        "p95": None,
        "max": None,
    }
    return {
        **percentiles,
        "mean": sum(deltas) / len(deltas) if deltas else None,
        "sample_count": len(deltas),
    }


def _runtime_timing(
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    keys = (
        "observe",
        "read_pools",
        "read_enemy_prefix",
        "read_enemy_issue_prefix",
        "read_player_control_root",
        "decode_pools",
        "corridor_bookkeeping",
        "local_plan",
        "local_plan_initial",
        "issue_enemy_recertificate",
        "input",
        "before_trace",
        "previous_trace",
        "previous_iteration",
    )
    result = {}
    for key in keys:
        values = [
            float(timing[key])
            for row in decisions
            if isinstance((timing := row.get("timing_ms")), dict)
            and timing.get(key) is not None
        ]
        if values:
            result[key] = _percentiles(values)
    return result


def _enemy_sensor_summary(
    decisions: list[dict[str, object]],
) -> dict[str, object] | None:
    valid_rows = []
    for row in decisions:
        timing = row.get("timing_ms")
        if not isinstance(timing, dict) or timing.get("read_enemy_pool") is None:
            continue
        source_value = row.get("enemy_body_snapshot_frame", 0)
        if source_value is None:
            continue
        source_frame = int(source_value)
        age = int(row["frame"]) - source_frame
        if source_frame <= 0 or age < 0:
            continue
        valid_rows.append((row, source_frame, age, timing))
    if not valid_rows:
        return None

    snapshots: dict[int, float] = {}
    for _row, source_frame, _age, timing in valid_rows:
        snapshots.setdefault(source_frame, float(timing["read_enemy_pool"]))
    source_frames = sorted(snapshots)
    intervals = [
        right - left
        for left, right in zip(source_frames, source_frames[1:])
        if 0 < right - left < 120
    ]
    body_counts = [
        int(row.get("active_enemy_bodies", 0))
        for row, _source, _age, _timing in valid_rows
    ]
    contact_enabled_counts = [
        int(
            row.get(
                "enemy_body_contact_enabled_count",
                row.get("active_enemy_bodies", 0),
            )
        )
        for row, _source, _age, _timing in valid_rows
    ]
    anticipatory_counts = [
        int(row.get("enemy_body_anticipatory_count", 0))
        for row, _source, _age, _timing in valid_rows
    ]
    dormant_counts = [
        int(row.get("enemy_body_dormant_count", 0))
        for row, _source, _age, _timing in valid_rows
    ]
    extended_bodies = [
        body
        for row, _source, _age, _timing in valid_rows
        for body in row.get("enemy_bodies", ())
        if isinstance(body, list) and len(body) >= 11
    ]
    world_speeds = [
        max(abs(float(body[3])), abs(float(body[4])))
        for body in extended_bodies
    ]
    internal_speeds = [
        max(
            abs(float(body[9] or 0.0)),
            abs(float(body[10] or 0.0)),
        )
        for body in extended_bodies
    ]
    motion_disagreements = [
        max(
            abs(float(body[3]) - float(body[9] or 0.0)),
            abs(float(body[4]) - float(body[10] or 0.0)),
        )
        for body in extended_bodies
    ]
    operational_ages = [
        age for _row, _source, age, _timing in valid_rows if age < 120
    ]
    return {
        "decision_count_with_snapshot": len(valid_rows),
        "snapshot_count": len(snapshots),
        "snapshot_age_frames": _percentiles(operational_ages),
        "snapshot_age_discontinuity_count": (
            len(valid_rows) - len(operational_ages)
        ),
        "snapshot_interval_frames": _percentiles(intervals),
        "capture_read_ms": _percentiles(snapshots.values()),
        "decision_count_with_active_bodies": sum(
            count > 0 for count in body_counts
        ),
        "max_active_bodies": max(body_counts, default=0),
        "decision_count_with_contact_enabled_bodies": sum(
            count > 0 for count in contact_enabled_counts
        ),
        "max_contact_enabled_bodies": max(
            contact_enabled_counts,
            default=0,
        ),
        "decision_count_with_anticipatory_bodies": sum(
            count > 0 for count in anticipatory_counts
        ),
        "max_anticipatory_bodies": max(anticipatory_counts, default=0),
        "decision_count_with_dormant_bodies": sum(
            count > 0 for count in dormant_counts
        ),
        "max_dormant_bodies": max(dormant_counts, default=0),
        "observed_world_motion_sample_count": len(extended_bodies),
        "observed_world_speed": _percentiles(world_speeds),
        "internal_component_speed": _percentiles(internal_speeds),
        "world_internal_motion_disagreement": _percentiles(
            motion_disagreements
        ),
        "world_internal_motion_disagreement_over_1px_count": sum(
            value > 1.0 for value in motion_disagreements
        ),
    }


def _issue_enemy_guard_summary(
    decisions: list[dict[str, object]],
) -> dict[str, object] | None:
    guards = [
        row["issue_time_enemy_guard"]
        for row in decisions
        if isinstance(row.get("issue_time_enemy_guard"), dict)
    ]
    if not guards:
        return None
    changes = [
        str(change)
        for guard in guards
        for change in guard.get("changes", ())
    ]
    transactions = [
        transaction
        for guard in guards
        if isinstance((transaction := guard.get("transaction")), dict)
    ]
    return {
        "observation_count": len(guards),
        "changed_observation_count": sum(
            bool(guard.get("changes")) for guard in guards
        ),
        "recertified_count": sum(
            bool(guard.get("recertified")) for guard in guards
        ),
        "action_override_count": sum(
            str(guard.get("planned_action_before_guard"))
            != str(guard.get("action_after_guard"))
            for guard in guards
        ),
        "transaction_count": len(transactions),
        "selection_reason_counts": dict(
            Counter(
                str(transaction.get("selection_reason"))
                for transaction in transactions
            )
        ),
        "planned_action_preserved_count": sum(
            str(transaction.get("planned_action"))
            == str(transaction.get("selected_action"))
            for transaction in transactions
        ),
        "fresh_global_intersection_count": sum(
            bool(transaction.get("global_constraint_applicable"))
            and bool(transaction.get("fresh_global_intersection"))
            for transaction in transactions
        ),
        "global_constraint_relaxation_count": sum(
            bool(transaction.get("global_constraint_relaxed"))
            for transaction in transactions
        ),
        "fresh_global_empty_relaxation_count": sum(
            bool(transaction.get("global_constraint_applicable"))
            and bool(transaction.get("global_constraint_relaxed"))
            for transaction in transactions
        ),
        "inherited_constraint_relaxation_count": sum(
            not bool(transaction.get("global_constraint_applicable"))
            and bool(transaction.get("global_constraint_relaxed"))
            for transaction in transactions
        ),
        "silent_outside_global_count": sum(
            bool(
                transaction.get(
                    "selected_outside_global_without_relaxation"
                )
            )
            for transaction in transactions
        ),
        "observation_count_with_anticipatory_bodies": sum(
            int(guard.get("anticipatory_count", 0)) > 0
            for guard in guards
        ),
        "max_anticipatory_bodies": max(
            (
                int(guard.get("anticipatory_count", 0))
                for guard in guards
            ),
            default=0,
        ),
        "observation_count_with_dormant_bodies": sum(
            int(guard.get("dormant_count", 0)) > 0
            for guard in guards
        ),
        "max_dormant_bodies": max(
            (
                int(guard.get("dormant_count", 0))
                for guard in guards
            ),
            default=0,
        ),
        "change_kind_counts": dict(
            Counter(change.split(":", 1)[0] for change in changes)
        ),
        "read_ms": _percentiles(
            float(guard.get("read_ms", 0.0)) for guard in guards
        ),
        "recertificate_ms": _percentiles(
            float(guard.get("recertificate_ms", 0.0))
            for guard in guards
            if bool(guard.get("recertified"))
        ),
    }


def _spell_owner_guard_summary(
    decisions: list[dict[str, object]],
) -> dict[str, object] | None:
    """Retain compact evidence for the synchronous spell-owner observation."""

    rows = [
        (row, guard)
        for row in decisions
        if isinstance((guard := row.get("spell_enemy_body_guard")), dict)
    ]
    if not rows:
        return None

    observed = [
        (row, guard)
        for row, guard in rows
        if isinstance(guard.get("body"), list) and guard["body"]
    ]
    pointer_counts: Counter[int] = Counter()
    per_spell: dict[str, Counter[str]] = {}
    outside_async_pool_count = 0
    for row, guard in observed:
        body = guard["body"]
        pointer = int(body[0])
        pointer_counts[pointer] += 1
        offset = pointer - ENEMY_POOL_BASE
        covered = (
            0 <= offset < ENEMY_POOL_SIZE * ENEMY_STRIDE
            and offset % ENEMY_STRIDE == 0
        )
        if not covered:
            outside_async_pool_count += 1
        spell = row.get("spell")
        spell_id = (
            str(spell.get("spell_id"))
            if isinstance(spell, dict) and spell.get("spell_id") is not None
            else "unknown"
        )
        counts = per_spell.setdefault(spell_id, Counter())
        counts["observation_count"] += 1
        counts["contact_enabled_count"] += bool(guard.get("contact_enabled"))
        counts["anticipatory_count"] += bool(guard.get("anticipatory"))

    return {
        "row_count": len(rows),
        "observation_count": len(observed),
        "error_count": sum(bool(guard.get("error")) for _row, guard in rows),
        "contact_enabled_count": sum(
            bool(guard.get("contact_enabled")) for _row, guard in observed
        ),
        "anticipatory_count": sum(
            bool(guard.get("anticipatory")) for _row, guard in observed
        ),
        "outside_async_pool_count": outside_async_pool_count,
        "pointer_counts": {
            f"0x{pointer:08X}": count
            for pointer, count in sorted(pointer_counts.items())
        },
        "per_spell": {
            spell_id: dict(sorted(counts.items()))
            for spell_id, counts in sorted(per_spell.items())
        },
    }


def _terminal_threat_summary(
    decisions: list[dict[str, object]],
) -> dict[str, object] | None:
    rows = [
        row["terminal_threat"]
        for row in decisions
        if isinstance(row.get("terminal_threat"), dict)
        and row["terminal_threat"]
    ]
    if not rows:
        return None
    clearances = [
        float(row["min_clearance"])
        for row in rows
        if float(row.get("min_clearance", 9999.0)) < 9999.0
    ]
    horizons = Counter(int(row.get("horizon_frames", 0)) for row in rows)
    return {
        "decision_count": len(rows),
        "mode_counts": dict(
            sorted(Counter(str(row.get("mode", "unknown")) for row in rows).items())
        ),
        "horizon_counts": {
            str(key): horizons[key] for key in sorted(horizons)
        },
        "collision_warning_count": sum(
            int(row.get("collisions", 0)) > 0 for row in rows
        ),
        "constraint_relaxed_count": sum(
            bool((decision.get("robust_control") or {}).get(
                "viability_constraint_relaxed"
            ))
            for decision in decisions
        ),
        "clearance_below_item_safety_count": sum(
            float(row.get("min_clearance", 9999.0))
            < TERMINAL_THREAT_SAFETY_CLEARANCE
            for row in rows
        ),
        "minimum_clearance": _percentiles(clearances),
    }


__all__ = [
    "_corridor_latency",
    "_decision_cadence",
    "_enemy_sensor_summary",
    "_issue_enemy_guard_summary",
    "_runtime_timing",
    "_spell_owner_guard_summary",
    "_terminal_threat_summary",
]
