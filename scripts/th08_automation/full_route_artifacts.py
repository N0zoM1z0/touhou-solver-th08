"""Compact evidence materialization for supervised full-route TH08 trials."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from analysis.th08_fullrun_regression import load_and_validate
from analysis.th08_run_dossier import main as build_run_dossier
from th08_practice_supervisor import RUNTIME_REPORT_DIR, RUN_NOTE_DIR


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ROUTE_STAGES = (0, 1, 2, 3, 5, 7)


def terminal_scene_record(trace: Path) -> dict[str, object]:
    with trace.open("rb") as source:
        source.seek(0, os.SEEK_END)
        end = source.tell()
        source.seek(max(0, end - 1024 * 1024))
        tail = source.read()
    for binary_line in reversed(tail.splitlines()):
        try:
            row = json.loads(binary_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if (
            row.get("kind") == "scene_inactive"
            and row.get("status") == "terminal_unload"
            and row.get("transition_from_stage") == 7
            and row.get("expected_stage") is None
        ):
            return row
    raise ValueError("trace has no Final-B terminal_unload scene record")


def _change(before: float | int, after: float | int) -> dict[str, float | int]:
    return {
        "baseline": before,
        "candidate": after,
        "delta": after - before,
    }


def _percentile_change(
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> dict[str, object]:
    return {
        key: _optional_change(
            before.get(key) if before is not None else None,
            after.get(key) if after is not None else None,
        )
        for key in ("median", "p95", "max")
    }


def _optional_change(
    before: object,
    after: object,
) -> dict[str, object]:
    if before is None or after is None:
        return {"baseline": before, "candidate": after, "delta": None}
    return _change(float(before), float(after))


def compare_full_dossiers(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    before_totals = baseline["totals"]
    after_totals = candidate["totals"]
    before_stages = {
        int(stage["stage_route_index"]): stage for stage in baseline["stages"]
    }
    after_stages = {
        int(stage["stage_route_index"]): stage for stage in candidate["stages"]
    }
    per_stage = {}
    for stage_index in EXPECTED_ROUTE_STAGES:
        before = before_stages.get(stage_index)
        after = after_stages.get(stage_index)
        if before is None or after is None:
            continue
        per_stage[str(stage_index)] = {
            "stage_label": after["stage_label"],
            "death_count": _change(
                int(before["death_count"]),
                int(after["death_count"]),
            ),
            "decision_count": _change(
                int(before["decision_count"]),
                int(after["decision_count"]),
            ),
            "max_active_bullets": _change(
                int(before["max_active_bullets"]),
                int(after["max_active_bullets"]),
            ),
            "max_active_lasers": _change(
                int(before["max_active_lasers"]),
                int(after["max_active_lasers"]),
            ),
            "power_end": _change(
                float(before["resources"]["power"]["end"]),
                float(after["resources"]["power"]["end"]),
            ),
            "read_ms": _percentile_change(
                before["latency_ms"]["read"],
                after["latency_ms"]["read"],
            ),
            "plan_ms": _percentile_change(
                before["latency_ms"]["plan"],
                after["latency_ms"]["plan"],
            ),
            "action_lag_frames": _percentile_change(
                before["frame_lag"]["action"],
                after["frame_lag"]["action"],
            ),
        }
    before_solver = baseline["control_policy"]["robust_viability"]
    after_solver = candidate["control_policy"]["robust_viability"]
    return {
        "schema": "th08-full-route-comparison-v1",
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "route_complete": {
            "baseline": (
                baseline["provenance"][-1]["summary"]["termination_reason"]
                == "route_complete"
            ),
            "candidate": (
                candidate["provenance"][-1]["summary"]["termination_reason"]
                == "route_complete"
            ),
        },
        "hard_no_bomb_passed": {
            "baseline": bool(
                baseline["control_policy"]["no_bomb_verification"]["passed"]
            ),
            "candidate": bool(
                candidate["control_policy"]["no_bomb_verification"]["passed"]
            ),
        },
        "death_count": _change(
            int(before_totals["death_count"]),
            int(after_totals["death_count"]),
        ),
        "decision_count": _change(
            int(before_totals["decision_count"]),
            int(after_totals["decision_count"]),
        ),
        "post_hit_bomb_stock_decrease": _change(
            float(before_totals.get("post_hit_bomb_stock_decrease", 0.0)),
            float(after_totals.get("post_hit_bomb_stock_decrease", 0.0)),
        ),
        "primary_cause_counts": {
            key: _change(
                int(before_totals["primary_cause_counts"].get(key, 0)),
                int(after_totals["primary_cause_counts"].get(key, 0)),
            )
            for key in sorted(
                set(before_totals["primary_cause_counts"])
                | set(after_totals["primary_cause_counts"])
            )
        },
        "solver_delivery": {
            "solve_ms": _percentile_change(
                before_solver["solve_ms"],
                after_solver["solve_ms"],
            ),
            "first_observed_age_frames": _percentile_change(
                before_solver["first_observed_age_frames"],
                after_solver["first_observed_age_frames"],
            ),
            "unique_solution_count": _change(
                int(before_solver["unique_solution_count"]),
                int(after_solver["unique_solution_count"]),
            ),
            "query_count": _change(
                int(before_solver["query_count"]),
                int(after_solver["query_count"]),
            ),
            "reported_stale_solution_count": _change(
                int(before_solver["reported_stale_solution_count"]),
                int(after_solver["reported_stale_solution_count"]),
            ),
            "serial_worker_serviceable_count": _optional_change(
                before_solver.get("serial_worker_serviceable_count"),
                after_solver.get("serial_worker_serviceable_count"),
            ),
            "candidate_backend_counts": after_solver.get(
                "backend_counts",
                {},
            ),
            "candidate_solver_phase_ms": after_solver.get(
                "solver_phase_ms",
                {},
            ),
        },
        "per_stage": per_stage,
    }


def previous_full_dossier(
    current: Path,
    difficulty_key: str = "lunatic",
    *,
    runtime_report_dir: Path = RUNTIME_REPORT_DIR,
) -> Path | None:
    candidates = sorted(
        runtime_report_dir.glob(
            f"{difficulty_key}_route2_fullrun*.dossier.json"
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        if path == current:
            continue
        try:
            dossier = json.loads(path.read_text(encoding="utf-8"))
            verification = dossier["control_policy"]["no_bomb_verification"]
            summary = dossier["provenance"][-1]["summary"]
        except (OSError, KeyError, IndexError, json.JSONDecodeError):
            continue
        if (
            dossier.get("schema")
            in {
                "th08-lunatic-run-dossier-v2",
                "th08-route-run-dossier-v3",
                "th08-route-run-dossier-v4",
            }
            and verification.get("passed")
            and summary
            and summary.get("termination_reason") == "route_complete"
        ):
            return path
    return None


def write_compact_full_route_summary(
    *,
    path: Path,
    dossier: dict[str, object],
) -> None:
    existing = (
        json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    )
    stages = dossier["stages"]
    existing.update(
        {
            "decision_count": int(dossier["totals"]["decision_count"]),
            "first_frame": int(dossier["totals"]["first_frame"]),
            "last_frame": int(dossier["totals"]["last_frame"]),
            "termination_reason": "route_complete",
            "hit_count": int(dossier["totals"]["death_count"]),
            "hit_frames": [
                int(death["frame"]) for death in dossier["deaths"]
            ],
            "stage_progress": {
                "transitions": [
                    {
                        "frame": int(stage["first_frame"]),
                        "stage_route_index": int(
                            stage["stage_route_index"]
                        ),
                        "stage_label": stage["stage_label"],
                    }
                    for stage in stages
                ],
                "last_stage_route_index": int(
                    stages[-1]["stage_route_index"]
                ),
                "last_stage_label": stages[-1]["stage_label"],
            },
        }
    )
    path.write_text(
        json.dumps(
            existing,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def materialize_artifacts(
    *,
    run_id: str,
    trace: Path,
    completion: dict[str, object],
    difficulty_key: str = "lunatic",
    difficulty_index: int = 3,
    root: Path = ROOT,
    runtime_report_dir: Path = RUNTIME_REPORT_DIR,
    run_note_dir: Path = RUN_NOTE_DIR,
) -> dict[str, object]:
    prefix = runtime_report_dir / run_id
    dossier_json = prefix.with_suffix(".dossier.json")
    deaths_csv = prefix.with_suffix(".deaths.csv")
    regressions_json = prefix.with_suffix(".regressions.json")
    comparison_json = prefix.with_suffix(".comparison.json")
    run_note_dir.mkdir(parents=True, exist_ok=True)
    run_note = run_note_dir / f"{run_id}.md"
    dossier_markdown = run_note
    build_run_dossier(
        [
            "--run-id",
            run_id,
            "--trace",
            str(trace),
            "--manifest",
            str(
                root
                / "artifacts"
                / "route_manifests"
                / f"sakuya_remilia_{difficulty_key}_final_b.json"
            ),
            "--json-output",
            str(dossier_json),
            "--markdown-output",
            str(dossier_markdown),
            "--death-csv",
            str(deaths_csv),
            "--regression-output",
            str(regressions_json),
            "--completion-frame",
            str(int(completion["frame"])),
            "--completion-engine-flags",
            str(int(completion["engine_flags"])),
        ]
    )
    dossier = json.loads(dossier_json.read_text(encoding="utf-8"))
    acceptance_target = dossier["acceptance_target"]
    if (
        int(acceptance_target["difficulty_index"]) != difficulty_index
        or str(acceptance_target["difficulty"]).lower() != difficulty_key
    ):
        raise RuntimeError(
            "full-route dossier difficulty mismatch: "
            f"expected={difficulty_key}/{difficulty_index} "
            f"observed={acceptance_target['difficulty']}/"
            f"{acceptance_target['difficulty_index']}"
        )
    observed_stages = tuple(
        int(stage["stage_route_index"]) for stage in dossier["stages"]
    )
    if observed_stages != EXPECTED_ROUTE_STAGES:
        raise RuntimeError(
            f"full-route dossier stage sequence mismatch: {observed_stages}"
        )
    if not dossier["control_policy"]["no_bomb_verification"]["passed"]:
        raise RuntimeError("full-route dossier failed the hard no-Bomb gate")
    if (
        dossier["provenance"][-1]["summary"]["termination_reason"]
        != "route_complete"
    ):
        raise RuntimeError("full-route dossier did not retain route completion")
    summary_json = trace.with_suffix(".summary.json")
    write_compact_full_route_summary(path=summary_json, dossier=dossier)
    regression_summary = asdict(load_and_validate(regressions_json))

    baseline = previous_full_dossier(
        dossier_json,
        difficulty_key,
        runtime_report_dir=runtime_report_dir,
    )
    if baseline is not None:
        comparison_json.write_text(
            json.dumps(
                compare_full_dossiers(
                    json.loads(baseline.read_text(encoding="utf-8")),
                    dossier,
                ),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        comparison_json = None

    return {
        "dossier_json": str(dossier_json),
        "dossier_markdown": str(dossier_markdown),
        "deaths_csv": str(deaths_csv),
        "regressions_json": str(regressions_json),
        "regression_summary": regression_summary,
        "comparison_json": (
            str(comparison_json) if comparison_json is not None else None
        ),
        "comparison_baseline": str(baseline) if baseline is not None else None,
        "run_note": str(run_note),
        "summary_json": str(summary_json),
    }
