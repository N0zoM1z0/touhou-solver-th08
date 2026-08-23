#!/usr/bin/env python3
"""Audit the fixed G5 corridor-parent priority experiment from a raw trace."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from analysis.dossier.statistics import percentiles


SCHEMA = "th08-corridor-priority-audit-v1"
EXPECTED_NATIVE_WORKERS = 4

SOLVE_P95_LIMIT_MS = 385.6
SOLVE_MAX_LIMIT_MS = 500.0
FIRST_AGE_MEDIAN_LIMIT_FRAMES = 3.0
FIRST_AGE_P95_LIMIT_FRAMES = 5.0
EXPIRED_FRACTION_LIMIT = 0.002
NO_QUERY_FRACTION_LIMIT = 0.01
QUERYABLE_FRACTION_MINIMUM = 0.98
LOCAL_PLAN_P95_LIMIT_MS = 20.0
ACTION_LAG_P95_LIMIT_FRAMES = 2.0
ACTION_LAG_MAX_LIMIT_FRAMES = 3.0


class CorridorPriorityAuditError(ValueError):
    """Raised when a trace cannot support the declared experiment."""


def _finite_number(
    value: object,
    *,
    field: str,
    line_number: int,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorridorPriorityAuditError(
            f"line {line_number}: {field} must be numeric"
        )
    result = float(value)
    if not math.isfinite(result):
        raise CorridorPriorityAuditError(
            f"line {line_number}: {field} must be finite"
        )
    return result


def _required_bool(
    record: dict[str, Any],
    field: str,
    *,
    line_number: int,
) -> bool:
    value = record.get(field)
    if not isinstance(value, bool):
        raise CorridorPriorityAuditError(
            f"line {line_number}: {field} must be Boolean"
        )
    return value


def _required_int(
    record: dict[str, Any],
    field: str,
    *,
    line_number: int,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CorridorPriorityAuditError(
            f"line {line_number}: {field} must be an integer"
        )
    return value


def _corridor_priority_request(
    controller_config: dict[str, Any],
    *,
    line_number: int,
) -> tuple[bool, str]:
    """Read the main-corridor request across the worker-policy split.

    New traces only carry ``ordinary_authority_background_low_priority``.
    That setting belongs to the separate ordinary-authority worker; absence
    of the legacy main-corridor field therefore means the main request is
    disabled, not malformed.
    """

    if "corridor_background_low_priority" in controller_config:
        return (
            _required_bool(
                controller_config,
                "corridor_background_low_priority",
                line_number=line_number,
            ),
            "explicit_main_corridor_field",
        )
    if "ordinary_authority_background_low_priority" in controller_config:
        _required_bool(
            controller_config,
            "ordinary_authority_background_low_priority",
            line_number=line_number,
        )
        return False, "implicit_disabled_after_ordinary_worker_split"
    raise CorridorPriorityAuditError(
        f"line {line_number}: corridor background priority policy is absent"
    )


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _distribution_gate(
    distribution: dict[str, float] | None,
    *,
    field: str,
    limit: float,
) -> bool:
    if distribution is None:
        return False
    return distribution[field] <= limit


def audit_trace(trace_path: Path) -> dict[str, object]:
    """Stream one raw controller trace and evaluate fixed delivery gates."""

    digest = hashlib.sha256()
    trace_bytes = 0
    controller_config: dict[str, Any] | None = None
    controller_config_line: int | None = None
    decision_count = 0
    policy_decision_count = 0
    query_count = 0
    support_uncovered_count = 0
    policy_statuses: Counter[str] = Counter()
    unique_solutions: dict[int, dict[str, object]] = {}
    local_plan_ms: list[float] = []
    action_lag_frames: list[float] = []

    with trace_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            digest.update(raw_line)
            trace_bytes += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise CorridorPriorityAuditError(
                    f"line {line_number}: invalid JSON: {error.msg}"
                ) from error
            if not isinstance(record, dict):
                raise CorridorPriorityAuditError(
                    f"line {line_number}: trace record must be an object"
                )

            kind = record.get("kind")
            if kind == "controller_config":
                if controller_config is not None:
                    raise CorridorPriorityAuditError(
                        "trace contains multiple controller_config records"
                    )
                controller_config = record
                controller_config_line = line_number
                continue
            if kind != "decision":
                continue

            decision_count += 1
            action_lag_frames.append(
                _finite_number(
                    record.get("action_lag"),
                    field="action_lag",
                    line_number=line_number,
                )
            )
            timing = record.get("timing_ms")
            if not isinstance(timing, dict):
                raise CorridorPriorityAuditError(
                    f"line {line_number}: timing_ms must be an object"
                )
            local_plan_ms.append(
                _finite_number(
                    timing.get("local_plan"),
                    field="timing_ms.local_plan",
                    line_number=line_number,
                )
            )

            corridor = record.get("corridor")
            if corridor is None:
                continue
            if not isinstance(corridor, dict):
                raise CorridorPriorityAuditError(
                    f"line {line_number}: corridor must be an object"
                )

            planning_mode = corridor.get("planning_mode")
            if planning_mode == "robust_viability":
                policy_decision_count += 1
                status = corridor.get("policy_status")
                if not isinstance(status, str):
                    raise CorridorPriorityAuditError(
                        f"line {line_number}: corridor.policy_status "
                        "must be a string"
                    )
                policy_statuses[status] += 1
                viability = corridor.get("viability")
                if viability is not None:
                    if not isinstance(viability, dict):
                        raise CorridorPriorityAuditError(
                            f"line {line_number}: corridor.viability "
                            "must be an object"
                        )
                    query_count += 1
                    available = _required_bool(
                        viability,
                        "available",
                        line_number=line_number,
                    )
                    if available and not _required_bool(
                        viability,
                        "support_covers_current",
                        line_number=line_number,
                    ):
                        support_uncovered_count += 1

            source_frame = _required_int(
                corridor,
                "source_frame",
                line_number=line_number,
            )
            if source_frame in unique_solutions:
                continue
            unique_solutions[source_frame] = {
                "first_line": line_number,
                "age_frames": _finite_number(
                    corridor.get("age"),
                    field="corridor.age",
                    line_number=line_number,
                ),
                "solve_ms": _finite_number(
                    corridor.get("solve_ms"),
                    field="corridor.solve_ms",
                    line_number=line_number,
                ),
                "background_priority_lowered": _required_bool(
                    corridor,
                    "background_priority_lowered",
                    line_number=line_number,
                ),
                "native_viability_worker_limit": _required_int(
                    corridor,
                    "native_viability_worker_limit",
                    line_number=line_number,
                ),
                "native_viability_worker_limit_applied": _required_bool(
                    corridor,
                    "native_viability_worker_limit_applied",
                    line_number=line_number,
                ),
            }

    if controller_config is None or controller_config_line is None:
        raise CorridorPriorityAuditError(
            "trace has no controller_config record"
        )
    requested, request_source = _corridor_priority_request(
        controller_config,
        line_number=controller_config_line,
    )
    configured_workers = _required_int(
        controller_config,
        "corridor_native_viability_workers",
        line_number=controller_config_line,
    )

    solutions = list(unique_solutions.values())
    priority_lowered_count = sum(
        solution["background_priority_lowered"] is True
        for solution in solutions
    )
    worker_limit_match_count = sum(
        solution["native_viability_worker_limit"] == configured_workers
        for solution in solutions
    )
    worker_limit_applied_count = sum(
        solution["native_viability_worker_limit_applied"] is True
        for solution in solutions
    )
    unique_solution_count = len(solutions)

    solve_distribution = percentiles(
        float(solution["solve_ms"]) for solution in solutions
    )
    first_age_distribution = percentiles(
        float(solution["age_frames"]) for solution in solutions
    )
    local_plan_distribution = percentiles(local_plan_ms)
    action_lag_distribution = percentiles(action_lag_frames)
    expired_count = policy_statuses["expired"]
    queryable_count = policy_statuses["queryable"]
    no_query_count = policy_decision_count - query_count
    expired_fraction = _fraction(expired_count, policy_decision_count)
    no_query_fraction = _fraction(no_query_count, policy_decision_count)
    queryable_fraction = _fraction(
        queryable_count,
        policy_decision_count,
    )

    application_gates = {
        "experiment_requested": requested,
        "configured_native_workers_is_four": (
            configured_workers == EXPECTED_NATIVE_WORKERS
        ),
        "has_completed_solution": unique_solution_count > 0,
        "all_solutions_lowered_parent_priority": (
            unique_solution_count > 0
            and priority_lowered_count == unique_solution_count
        ),
        "all_solutions_match_configured_native_workers": (
            unique_solution_count > 0
            and worker_limit_match_count == unique_solution_count
        ),
        "all_solutions_applied_native_worker_limit": (
            unique_solution_count > 0
            and worker_limit_applied_count == unique_solution_count
        ),
    }
    delivery_gates = {
        "solve_p95_ms": _distribution_gate(
            solve_distribution,
            field="p95",
            limit=SOLVE_P95_LIMIT_MS,
        ),
        "solve_max_ms": _distribution_gate(
            solve_distribution,
            field="max",
            limit=SOLVE_MAX_LIMIT_MS,
        ),
        "first_observed_age_median_frames": _distribution_gate(
            first_age_distribution,
            field="median",
            limit=FIRST_AGE_MEDIAN_LIMIT_FRAMES,
        ),
        "first_observed_age_p95_frames": _distribution_gate(
            first_age_distribution,
            field="p95",
            limit=FIRST_AGE_P95_LIMIT_FRAMES,
        ),
        "expired_fraction": (
            expired_fraction is not None
            and expired_fraction <= EXPIRED_FRACTION_LIMIT
        ),
        "no_query_fraction": (
            no_query_fraction is not None
            and no_query_fraction <= NO_QUERY_FRACTION_LIMIT
        ),
        "queryable_fraction": (
            queryable_fraction is not None
            and queryable_fraction >= QUERYABLE_FRACTION_MINIMUM
        ),
        "support_uncovered_count": support_uncovered_count == 0,
        "local_plan_p95_ms": _distribution_gate(
            local_plan_distribution,
            field="p95",
            limit=LOCAL_PLAN_P95_LIMIT_MS,
        ),
        "action_lag_p95_frames": _distribution_gate(
            action_lag_distribution,
            field="p95",
            limit=ACTION_LAG_P95_LIMIT_FRAMES,
        ),
        "action_lag_max_frames": _distribution_gate(
            action_lag_distribution,
            field="max",
            limit=ACTION_LAG_MAX_LIMIT_FRAMES,
        ),
    }

    return {
        "schema": SCHEMA,
        "trace": {
            "path": trace_path.name,
            "bytes": trace_bytes,
            "sha256": digest.hexdigest(),
        },
        "configuration": {
            "corridor_background_low_priority": requested,
            "corridor_background_low_priority_source": request_source,
            "corridor_native_viability_workers": configured_workers,
        },
        "counts": {
            "decision": decision_count,
            "policy_decision": policy_decision_count,
            "query": query_count,
            "no_query": no_query_count,
            "support_uncovered": support_uncovered_count,
            "unique_solution": unique_solution_count,
            "priority_lowered_solution": priority_lowered_count,
            "worker_limit_match_solution": worker_limit_match_count,
            "worker_limit_applied_solution": worker_limit_applied_count,
        },
        "policy_status_counts": {
            key: policy_statuses[key] for key in sorted(policy_statuses)
        },
        "distributions": {
            "corridor_solve_ms": solve_distribution,
            "first_observed_age_frames": first_age_distribution,
            "local_plan_ms": local_plan_distribution,
            "action_lag_frames": action_lag_distribution,
        },
        "fractions": {
            "expired": expired_fraction,
            "no_query": no_query_fraction,
            "queryable": queryable_fraction,
        },
        "limits": {
            "solve_p95_ms": SOLVE_P95_LIMIT_MS,
            "solve_max_ms": SOLVE_MAX_LIMIT_MS,
            "first_observed_age_median_frames": (
                FIRST_AGE_MEDIAN_LIMIT_FRAMES
            ),
            "first_observed_age_p95_frames": (
                FIRST_AGE_P95_LIMIT_FRAMES
            ),
            "expired_fraction": EXPIRED_FRACTION_LIMIT,
            "no_query_fraction": NO_QUERY_FRACTION_LIMIT,
            "queryable_fraction": QUERYABLE_FRACTION_MINIMUM,
            "local_plan_p95_ms": LOCAL_PLAN_P95_LIMIT_MS,
            "action_lag_p95_frames": ACTION_LAG_P95_LIMIT_FRAMES,
            "action_lag_max_frames": ACTION_LAG_MAX_LIMIT_FRAMES,
        },
        "gates": {
            "application": application_gates,
            "delivery": delivery_gates,
            "application_pass": all(application_gates.values()),
            "delivery_pass": all(delivery_gates.values()),
        },
        "scope": {
            "observer_latency_and_completion_transition_gate": (
                "evaluated_separately_by_th08-bullet-birth-residual-audit-v7"
            ),
            "physical_survival_and_warning_gate": (
                "evaluated_from_retained session, summary, and dossier"
            ),
        },
    }


def canonical_report_bytes(report: dict[str, object]) -> bytes:
    return (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = canonical_report_bytes(audit_trace(args.trace))
    if args.output is None:
        print(payload.decode("utf-8"), end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
