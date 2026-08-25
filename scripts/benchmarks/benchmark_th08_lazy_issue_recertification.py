#!/usr/bin/env python3
"""Deterministic dense-safe benchmark for exact lazy issue recertification."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time

import numpy as np

import th08_live.controller as live
from th08_live.models import PackedBulletSnapshot
from th08_local_planner import Decision, LocalProposal
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)
from touhou_control.local_pipeline_oracle import LocalPipelineRoot


SCHEMA = "th08-lazy-issue-recertification-benchmark-v1"


def _bullets(count: int) -> PackedBulletSnapshot:
    rng = np.random.default_rng(8)
    zeros_u8 = np.zeros(count, dtype=np.uint8)
    zeros_u32 = np.zeros(count, dtype=np.uint32)
    return PackedBulletSnapshot(
        x=rng.uniform(110.0, 274.0, count).astype(np.float32),
        y=rng.uniform(320.0, 350.0, count).astype(np.float32),
        velocity_x=rng.uniform(-0.1, 0.1, count).astype(np.float32),
        velocity_y=rng.uniform(-0.1, 0.1, count).astype(np.float32),
        half_width=rng.uniform(1.0, 4.0, count).astype(np.float32),
        half_height=rng.uniform(1.0, 4.0, count).astype(np.float32),
        transform_flags=zeros_u32.copy(),
        slots=np.arange(count, dtype=np.int32),
        speed=np.full(count, np.nan, dtype=np.float32),
        angle=np.full(count, np.nan, dtype=np.float32),
        callback_phase=zeros_u8.copy(),
        callback_aux=zeros_u8.copy(),
        original_transform_flags=zeros_u32.copy(),
        native_state=np.ones(count, dtype=np.uint16),
        native_state_timer_elapsed=np.zeros(count, dtype=np.int32),
        bullet_type=np.zeros(count, dtype=np.int16),
    )


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "minimum_ms": ordered[0],
        "maximum_ms": ordered[-1],
    }


def benchmark(*, bullet_count: int, repeats: int) -> dict[str, object]:
    bullets = _bullets(bullet_count)
    decision = Decision(
        mask=live.SHOT | live.FOCUS,
        action="stay",
        min_clearance=1.0,
        immediate_clearance=1.0,
        score=0.0,
        bomb=False,
    )
    proposal = LocalProposal.from_decision(decision)
    schedule = Th08TimeScaleSchedule.constant(
        TH08_UNIT_TIME_SCALE_BITS,
        horizon=12,
        provenance="lazy_issue_recertification_benchmark",
    )
    root = LocalPipelineRoot(
        active_action="stay",
        held_desired_action="stay",
    )

    def run(lazy: bool):
        started = time.perf_counter_ns()
        issued = live.commit_local_proposal_for_fresh_hazards(
            proposal,
            player_x=192.0,
            player_y=400.0,
            previous_mask=decision.mask,
            delay_frames=(2, 3, 4, 5, 6),
            action_hold_frames=4,
            bullets=bullets,
            lasers=(),
            enemy_bodies=(),
            snapshot_lag=0,
            pipeline_root=root,
            time_scale_schedule=schedule,
            lazy_safe_action_probe=lazy,
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        return elapsed_ms, issued

    run(False)
    run(True)
    results: dict[str, dict[str, object]] = {}
    representative = {}
    for label, lazy in (("full", False), ("lazy", True)):
        timings = []
        for _ in range(repeats):
            elapsed_ms, issued = run(lazy)
            timings.append(elapsed_ms)
            representative[label] = issued
        results[label] = {
            **_summary(timings),
            "certificate_count": len(
                representative[label].decision.issue_action_certificates
            ),
            "certificate_mode": (
                representative[label].transaction.certificate_mode
            ),
        }

    full = representative["full"]
    lazy = representative["lazy"]
    exact_selected_certificate_match = (
        full.transaction.selected_certificate
        == lazy.transaction.selected_certificate
    )
    if not exact_selected_certificate_match:
        raise AssertionError("lazy and full selected certificates differ")
    full_median = float(results["full"]["median_ms"])
    lazy_median = float(results["lazy"]["median_ms"])
    return {
        "schema": SCHEMA,
        "workload": {
            "bullet_count": bullet_count,
            "planner_action_count": len(live._PLANNER_ACTIONS),
            "delay_frames": [2, 3, 4, 5, 6],
            "action_hold_frames": 4,
            "repeats": repeats,
            "selected_action": "stay",
            "selected_path_is_fresh_safe": True,
        },
        "authority": {
            "role": "deterministic synthetic performance differential",
            "physical_hit_claim": False,
            "exact_selected_certificate_match": (
                exact_selected_certificate_match
            ),
        },
        "results": results,
        "median_speedup": full_median / lazy_median,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bullet-count", type=int, default=1200)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.bullet_count <= 0 or args.repeats <= 0:
        parser.error("bullet count and repeats must be positive")
    report = benchmark(
        bullet_count=args.bullet_count,
        repeats=args.repeats,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
