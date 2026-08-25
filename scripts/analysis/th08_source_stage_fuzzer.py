#!/usr/bin/env python3
"""Generate/replay complete stages and run source + solver differentials."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_semantics.campaign import (
    StageCampaignConfig,
    StageCampaignResult,
    run_closed_loop_stage,
)
from th08_semantics.stage import StageProgram
from th08_semantics.stage_differential import (
    StageSourceDifferentialResult,
    compare_stage_with_c_source_oracle,
)
from th08_semantics.stage_generation import (
    STAGE_PROFILES,
    generate_stage_program,
)
from th08_semantics.stage_shrink import shrink_stage_program


REPORT_SCHEMA = "th08-source-stateful-stage-fuzzer-report-v2-spawn-lifecycle"


def _load_program(path: Path) -> StageProgram:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "program" in payload:
        payload = payload["program"]
    if not isinstance(payload, dict):
        raise ValueError("stage replay must contain one program object")
    return StageProgram.from_payload(payload)


def _failure_signature(
    campaign: StageCampaignResult,
    source: StageSourceDifferentialResult | None,
) -> str | None:
    if source is not None and not source.passed:
        return f"source:{source.first_mismatch}"
    if campaign.planner_failures:
        return f"planner:{campaign.planner_failures[0].split(':', 2)[-1]}"
    for label, count in (
        ("bomb", campaign.bomb_policy_violations),
        ("geometry_collision", campaign.geometry_collision_mismatches),
        (
            "geometry_clearance_sign",
            campaign.geometry_clearance_sign_mismatches,
        ),
        ("geometry_clearance", campaign.geometry_clearance_mismatches),
        ("geometry_risk", campaign.geometry_risk_mismatches),
    ):
        if count:
            return label
    if not campaign.completed:
        return "incomplete_stage"
    return None


def _run_one(
    program: StageProgram,
    *,
    config: StageCampaignConfig,
    source_oracle: bool,
) -> tuple[StageCampaignResult, StageSourceDifferentialResult | None]:
    source = (
        compare_stage_with_c_source_oracle(program)
        if source_oracle
        else None
    )
    campaign = run_closed_loop_stage(program, config=config)
    return campaign, source


def _summary(cases: list[dict[str, object]]) -> dict[str, object]:
    campaigns = [case["campaign"] for case in cases]
    assert all(isinstance(value, dict) for value in campaigns)
    source_differentials = [
        value
        for case in cases
        if isinstance((value := case["source_differential"]), dict)
    ]
    solve_p95 = [
        float(value["planner_solve_ms_p95"])
        for value in campaigns
        if value["planner_solve_ms_p95"] is not None
    ]
    return {
        "case_count": len(cases),
        "pass_count": sum(case["failure"] is None for case in cases),
        "failure_count": sum(case["failure"] is not None for case in cases),
        "frames": sum(int(value["frames"]) for value in campaigns),
        "births_requested": sum(
            int(value["runtime_metrics"]["births_requested"])
            for value in campaigns
        ),
        "birth_allocation_calls": sum(
            int(value["runtime_metrics"]["birth_allocation_calls"])
            for value in campaigns
        ),
        "births_allocated": sum(
            int(value["runtime_metrics"]["births_allocated"])
            for value in campaigns
        ),
        "births_suppressed_by_pool": sum(
            int(value["runtime_metrics"]["births_suppressed_by_pool"])
            for value in campaigns
        ),
        "maximum_active_bullets": max(
            int(value["runtime_metrics"]["max_active_bullets"])
            for value in campaigns
        ),
        "pool_saturation_frames": sum(
            int(value["runtime_metrics"]["pool_saturation_frames"])
            for value in campaigns
        ),
        "spawn_lifecycle_activations": sum(
            int(value["runtime_metrics"]["spawn_lifecycle_activations"])
            for value in campaigns
        ),
        "source_lifecycle_samples_compared": sum(
            int(value["lifecycle_samples_compared"])
            for value in source_differentials
        ),
        "maximum_source_lifecycle_position_error": max(
            (
                float(value["maximum_lifecycle_position_error"])
                for value in source_differentials
            ),
            default=None,
        ),
        "normalized_hits": sum(
            int(value["normalized_hits"]) for value in campaigns
        ),
        "collision_frames": sum(
            int(value["collision_frames"]) for value in campaigns
        ),
        "planner_calls": sum(
            int(value["planner_calls"]) for value in campaigns
        ),
        "planner_case_p95_ms_median": (
            statistics.median(solve_p95) if solve_p95 else None
        ),
        "wall_time_seconds": sum(
            float(value["wall_time_seconds"]) for value in campaigns
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(STAGE_PROFILES), default="quick")
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xCE0132)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--counterexample-dir", type=Path)
    parser.add_argument("--planner-stride", type=int, default=8)
    parser.add_argument("--planner-horizon", type=int, default=12)
    parser.add_argument("--planner-threat-horizon", type=int, default=16)
    parser.add_argument("--planner-beam-width", type=int, default=8)
    parser.add_argument("--action-hold-frames", type=int, default=2)
    parser.add_argument("--sensing-latency-frames", type=int, default=1)
    parser.add_argument("--issue-latency-frames", type=int, default=1)
    parser.add_argument("--geometry-oracle-stride", type=int, default=16)
    parser.add_argument("--geometry-oracle-horizon", type=int, default=3)
    parser.add_argument("--hit-cooldown-frames", type=int, default=8)
    parser.add_argument("--skip-source-oracle", action="store_true")
    parser.add_argument("--shrink-failures", action="store_true")
    parser.add_argument("--shrink-attempts", type=int, default=96)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.count <= 0:
        raise ValueError("stage fuzzer count must be positive")
    if args.replay is not None and args.count != 1:
        raise ValueError("replay accepts exactly one stage")
    config = StageCampaignConfig(
        planner_stride=args.planner_stride,
        planner_horizon=args.planner_horizon,
        planner_threat_horizon=args.planner_threat_horizon,
        planner_beam_width=args.planner_beam_width,
        action_hold_frames=args.action_hold_frames,
        sensing_latency_frames=args.sensing_latency_frames,
        issue_latency_frames=args.issue_latency_frames,
        geometry_oracle_stride=args.geometry_oracle_stride,
        geometry_oracle_horizon=args.geometry_oracle_horizon,
        hit_cooldown_frames=args.hit_cooldown_frames,
    )
    programs = (
        (_load_program(args.replay),)
        if args.replay is not None
        else tuple(
            generate_stage_program(seed=args.seed + index, profile=args.profile)
            for index in range(args.count)
        )
    )
    cases: list[dict[str, object]] = []
    run_started = time.perf_counter()
    for program in programs:
        campaign, source = _run_one(
            program,
            config=config,
            source_oracle=not args.skip_source_oracle,
        )
        failure = _failure_signature(campaign, source)
        case: dict[str, object] = {
            "identity": program.identity,
            "program": program.to_payload(),
            "campaign": campaign.to_payload(),
            "source_differential": (
                source.to_payload() if source is not None else None
            ),
            "failure": failure,
        }
        if failure is not None and args.counterexample_dir is not None:
            args.counterexample_dir.mkdir(parents=True, exist_ok=True)
            original_path = (
                args.counterexample_dir / f"{program.digest}-original.json"
            )
            original_path.write_text(
                json.dumps(case, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            case["counterexample"] = str(original_path)
            if args.shrink_failures:

                def preserves(candidate: StageProgram) -> bool:
                    candidate_campaign, candidate_source = _run_one(
                        candidate,
                        config=config,
                        source_oracle=not args.skip_source_oracle,
                    )
                    return (
                        _failure_signature(
                            candidate_campaign,
                            candidate_source,
                        )
                        == failure
                    )

                reduced, attempts = shrink_stage_program(
                    program,
                    fails=preserves,
                    maximum_attempts=args.shrink_attempts,
                )
                reduced_path = (
                    args.counterexample_dir / f"{program.digest}-reduced.json"
                )
                reduced_path.write_text(
                    json.dumps(
                        {
                            "failure": failure,
                            "attempts": attempts,
                            "program": reduced.to_payload(),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                case["reduced_counterexample"] = str(reduced_path)
                case["shrink_attempts"] = attempts
        cases.append(case)

    report = {
        "schema": REPORT_SCHEMA,
        "config": asdict(config),
        "source_oracle_enabled": not args.skip_source_oracle,
        "cases": cases,
        "summary": _summary(cases),
        "total_wall_time_seconds": time.perf_counter() - run_started,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    return 0 if report["summary"]["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
