#!/usr/bin/env python3
"""Audit retained body-slot watermarks for source-correct enemy sensing."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Iterable

from th08_live.enemy_sensor import (
    ENEMY_LOCAL_PREFIX_SIZE,
    ENEMY_MANAGER_SCANNED_SLOT_COUNT,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def _timing(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median_ms": statistics.median(values) if values else None,
        "p95_ms": _percentile(values, 0.95),
        "maximum_ms": max(values) if values else None,
    }


def _native_slot(pointer: int) -> int | None:
    offset = pointer - ENEMY_SLOT_ZERO_BASE
    if offset < 0 or offset % ENEMY_STRIDE:
        return None
    slot = offset // ENEMY_STRIDE
    if not 0 <= slot < ENEMY_MANAGER_SCANNED_SLOT_COUNT:
        return None
    return slot


def audit_trace(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    decisions = 0
    body_rows = 0
    slot_zero_rows = 0
    outside_prefix_rows = 0
    outside_prefix_bodies = 0
    maximum_body_count = 0
    maximum_slot: int | None = None
    unaligned_pointers: set[int] = set()
    timings: dict[str, list[float]] = {
        "async_full_pool_worker": [],
        "synchronous_prefix": [],
        "local_plan": [],
        "observe_to_input": [],
    }
    timing_fields = {
        "async_full_pool_worker": "read_enemy_pool",
        "synchronous_prefix": "read_enemy_prefix_capture",
        "local_plan": "local_plan",
        "observe_to_input": "observe_to_input",
    }

    with path.open("rb") as source:
        for binary_line in source:
            digest.update(binary_line)
            row = json.loads(binary_line)
            if row.get("kind") != "decision":
                continue
            decisions += 1
            bodies = row.get("enemy_bodies") or ()
            maximum_body_count = max(maximum_body_count, len(bodies))
            body_rows += bool(bodies)
            row_has_slot_zero = False
            row_has_tail = False
            for body in bodies:
                pointer = int(body[0])
                slot = _native_slot(pointer)
                if slot is None:
                    unaligned_pointers.add(pointer)
                    continue
                maximum_slot = (
                    slot
                    if maximum_slot is None
                    else max(maximum_slot, slot)
                )
                row_has_slot_zero |= slot == 0
                if slot >= ENEMY_LOCAL_PREFIX_SIZE:
                    row_has_tail = True
                    outside_prefix_bodies += 1
            slot_zero_rows += row_has_slot_zero
            outside_prefix_rows += row_has_tail
            row_timings = row.get("timing_ms") or {}
            for label, field in timing_fields.items():
                value = row_timings.get(field)
                if isinstance(value, (int, float)):
                    timings[label].append(float(value))

    return {
        "trace": str(path),
        "sha256": digest.hexdigest(),
        "decision_rows": decisions,
        "rows_with_serialized_bodies": body_rows,
        "maximum_serialized_body_count": maximum_body_count,
        "maximum_native_slot_observed": maximum_slot,
        "rows_with_native_slot_zero": slot_zero_rows,
        "outside_slot_zero_to_63_rows": outside_prefix_rows,
        "outside_slot_zero_to_63_bodies": outside_prefix_bodies,
        "unaligned_manager_pointers": sorted(unaligned_pointers),
        "timing": {
            label: _timing(values) for label, values in timings.items()
        },
        "evidence_boundary": (
            "The retained trace proves the serialized collision-body slot "
            "watermark only and cannot prove that contact-disabled or "
            "zero-size active tail slots were absent. It therefore cannot "
            "justify a prefix-only live sensor. The source-contiguous profile "
            "keeps a complete asynchronous read of native slots 0..479."
        ),
    }


def build_report(paths: Iterable[Path]) -> dict[str, object]:
    return {
        "schema": "th08-enemy-prefix-profile-audit-v2",
        "generated_at": "2026-08-26",
        "profile": {
            "native_slot_start": 0,
            "native_slot_end_inclusive": ENEMY_LOCAL_PREFIX_SIZE - 1,
            "asynchronous_native_slot_start": 0,
            "asynchronous_native_slot_end_inclusive": (
                ENEMY_MANAGER_SCANNED_SLOT_COUNT - 1
            ),
            "asynchronous_read_path": "one_contiguous_process_read",
            "prefix_only_authority": False,
            "rejected_completeness_oracle": (
                "EnemyManagerUpdateOverlay::EnemyCount is a scan-encounter "
                "counter, not a current active-slot count"
            ),
        },
        "traces": [audit_trace(path) for path in paths],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.traces)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
