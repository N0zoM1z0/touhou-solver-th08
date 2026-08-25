#!/usr/bin/env python3
"""Benchmark source-order current-bullet transform projection batches."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

from th08_bullet_transform_model import (
    BulletTransformProgramRuntime,
    TransformKind,
    TransformRecord,
    pack_transform_program,
)
from th08_current_transform_stepper import (
    CurrentBulletTransformState,
    step_current_transform,
)
from th08_semantics.native_oracle import NativeSourceOracle
from th08_semantics.source_primitives import f32


def _state(index: int) -> CurrentBulletTransformState:
    kinds = (
        TransformKind.VECTOR_ACCELERATION,
        TransformKind.ANGULAR_VELOCITY,
        TransformKind.STOP_TURN_REPEAT,
        TransformKind.TIMED_QUEUE_BARRIER,
        TransformKind.WRAP_HORIZONTAL,
    )
    kind = kinds[index % len(kinds)]
    int_0 = 1_000_000
    int_1 = 1_000_000
    float_0 = 0.002 if kind != TransformKind.STOP_TURN_REPEAT else 0.01
    float_1 = -0.7 + (index % 128) / 128.0
    record = TransformRecord(
        index=0,
        kind=int(kind),
        allow_while_active=False,
        int_0=int_0,
        int_1=int_1,
        float_0=float_0,
        float_1=float_1,
    )
    angle = f32(-1.0 + (index % 256) / 128.0)
    speed = f32(0.75 + (index % 31) / 64.0)
    return CurrentBulletTransformState(
        x=f32(32.0 + index % 320),
        y=f32(64.0 + index % 320),
        velocity_x=f32(math.cos(angle) * speed),
        velocity_y=f32(math.sin(angle) * speed),
        collision_half_width=2.0,
        collision_half_height=2.0,
        cull_half_width=4.0,
        cull_half_height=4.0,
        base_speed=speed,
        base_angle=angle,
        bullet_type=2,
        native_state=1,
        active_flags=0,
        runtime=BulletTransformProgramRuntime(
            program=pack_transform_program((record,)),
            original_flags=int(kind),
            queue_cursor=0,
            cull_suppression_countdown=1_000_000,
            offscreen_counter=0,
        ),
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1),
    )
    return ordered[index]


def _measure(function, *, warmup: int, samples: int) -> dict[str, float]:
    for _ in range(warmup):
        function()
    timings: list[float] = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        function()
        timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return {
        "median_ms": _percentile(timings, 0.5),
        "p95_ms": _percentile(timings, 0.95),
        "max_ms": max(timings),
    }


def _parity(
    left: tuple[CurrentBulletTransformState, ...],
    right: tuple[CurrentBulletTransformState, ...],
) -> bool:
    if len(left) != len(right):
        return False
    for left_state, right_state in zip(left, right):
        if (
            left_state.active_flags != right_state.active_flags
            or left_state.runtime.queue_cursor
            != right_state.runtime.queue_cursor
            or left_state.native_state != right_state.native_state
            or left_state.retired != right_state.retired
        ):
            return False
        for name in (
            "x",
            "y",
            "velocity_x",
            "velocity_y",
            "base_speed",
            "base_angle",
        ):
            if not math.isclose(
                getattr(left_state, name),
                getattr(right_state, name),
                rel_tol=2.0e-6,
                abs_tol=2.0e-5,
            ):
                return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=(1, 32, 128, 512, 1536),
    )
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args(argv)
    if (
        not args.sizes
        or min(args.sizes) < 0
        or max(args.sizes) > 1536
        or args.warmup < 0
        or args.samples <= 0
    ):
        raise ValueError("invalid benchmark arguments")

    oracle = NativeSourceOracle.load()
    results: list[dict[str, object]] = []
    for size in args.sizes:
        states = tuple(_state(index) for index in range(size))
        native = oracle.prepare_transform_program_batch(states)

        def python_scalar():
            return tuple(
                step_current_transform(
                    state,
                    player_x=192.0,
                    player_y=400.0,
                )
                for state in states
            )

        def native_prepare():
            return oracle.prepare_transform_program_batch(states)

        def native_kernel():
            oracle.advance_transform_program_batch(
                native,
                player_x=192.0,
                player_y=400.0,
                movement_frozen=True,
            )

        def native_decode():
            return oracle.decode_transform_program_batch(native)

        def native_end_to_end():
            return oracle.transform_program_batch(
                states,
                player_x=192.0,
                player_y=400.0,
            )

        python_result = python_scalar()
        native_result = native_end_to_end()
        parity = _parity(python_result, native_result)
        if not parity:
            raise AssertionError(f"transform parity failed at size {size}")
        measurements = {
            name: _measure(
                function,
                warmup=args.warmup,
                samples=args.samples,
            )
            for name, function in (
                ("python_scalar", python_scalar),
                ("native_prepare", native_prepare),
                ("native_kernel", native_kernel),
                ("native_decode", native_decode),
                ("native_end_to_end", native_end_to_end),
            )
        }
        results.append(
            {
                "states": size,
                "parity": parity,
                "measurements": measurements,
                "kernel_state_frames_per_second": (
                    0.0
                    if size == 0
                    else size
                    / measurements["native_kernel"]["median_ms"]
                    * 1000.0
                ),
            }
        )

    output = {
        "schema": "th08-transform-program-oracle-benchmark-v1",
        "scope": (
            "One source-order current-bullet frame. Native prepare/decode "
            "measure Python object conversion separately; native_kernel "
            "reuses one owned flat batch and excludes conversion."
        ),
        "warmup": args.warmup,
        "samples": args.samples,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
