#!/usr/bin/env python3
"""Offline benchmark of equivalent TH08 enemy-pool capture strategies."""

from __future__ import annotations

import argparse
import json
import statistics

from th08_live_dodge_agent import (
    ENEMY_POOL_SIZE,
    ENEMY_SLOT_ZERO_BASE,
    ENEMY_STRIDE,
    capture_enemy_pool_snapshot_contiguous,
    capture_enemy_pool_snapshot_sparse,
)
from th08_runtime_agent import ProcessReader, Win32


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": statistics.median(ordered),
        "p95": ordered[int(0.95 * (len(ordered) - 1))],
        "max": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")

    api = Win32()
    reader = ProcessReader(api, args.pid)
    contiguous_buffer = reader.allocate_buffer(
        ENEMY_POOL_SIZE * ENEMY_STRIDE
    )
    timings = {"contiguous": [], "sparse": []}
    body_counts = {"contiguous": [], "sparse": []}
    stable_pair_equivalence = []
    try:
        for _ in range(args.iterations):
            contiguous = capture_enemy_pool_snapshot_contiguous(
                reader,
                pool_base=ENEMY_SLOT_ZERO_BASE,
                pool_size=ENEMY_POOL_SIZE,
                pool_buffer=contiguous_buffer,
            )
            sparse = capture_enemy_pool_snapshot_sparse(reader)
            for name, snapshot in (
                ("contiguous", contiguous),
                ("sparse", sparse),
            ):
                timings[name].append(snapshot.read_ms)
                body_counts[name].append(len(snapshot.bodies))
            if (
                contiguous.frame_before == contiguous.frame_after
                == sparse.frame_before
                == sparse.frame_after
            ):
                stable_pair_equivalence.append(
                    {
                        body.pointer
                        for body in contiguous.bodies
                    }
                    == {body.pointer for body in sparse.bodies}
                )
    finally:
        reader.close()

    print(
        json.dumps(
            {
                "pid": args.pid,
                "iterations": args.iterations,
                "timing_ms": {
                    name: _stats(values)
                    for name, values in timings.items()
                },
                "body_counts": body_counts,
                "stable_pair_count": len(stable_pair_equivalence),
                "stable_pair_equivalent_count": sum(
                    stable_pair_equivalence
                ),
                "stable_pairs_equivalent": (
                    bool(stable_pair_equivalence)
                    and all(stable_pair_equivalence)
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
