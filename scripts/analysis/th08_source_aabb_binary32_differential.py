#!/usr/bin/env python3
"""Fuzz TH08 bullet/player AABB collision at binary32 edge boundaries.

The independent oracle transcribes the Float3 stores and inclusive separated-
axis comparisons in ``Player::FUN_0044a230``.  It compares that result with
the former real-valued symmetric-clearance predicate, the corrected source
kernel, and a full 1,536-slot vectorized integration stress.  Laser rotation
is intentionally excluded because its sinf/cosf boundary needs a separate
oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from th08_source_collision import (
    TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
    source_aabb_overlap_mask,
    source_collision_hazards_for_positions,
)


SCHEMA = "th08-source-aabb-binary32-differential-v1"
DEFAULT_SEED = 0x44A230


def _oracle_bounds(
    center: np.ndarray,
    half_extent: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Independent source transcription: two Float3 binary32 stores."""

    center32 = np.asarray(center, dtype=np.float32)
    half32 = np.asarray(half_extent, dtype=np.float32)
    return (
        np.asarray(center32 - half32, dtype=np.float32),
        np.asarray(center32 + half32, dtype=np.float32),
    )


def oracle_overlap_mask(
    *,
    player_x: np.ndarray,
    player_y: np.ndarray,
    player_half_width: np.ndarray,
    player_half_height: np.ndarray,
    hazard_x: np.ndarray,
    hazard_y: np.ndarray,
    hazard_half_width: np.ndarray,
    hazard_half_height: np.ndarray,
) -> np.ndarray:
    player_left, player_right = _oracle_bounds(player_x, player_half_width)
    player_top, player_bottom = _oracle_bounds(player_y, player_half_height)
    hazard_left, hazard_right = _oracle_bounds(hazard_x, hazard_half_width)
    hazard_top, hazard_bottom = _oracle_bounds(hazard_y, hazard_half_height)
    return ~(
        (player_left > hazard_right)
        | (player_top > hazard_bottom)
        | (player_right < hazard_left)
        | (player_bottom < hazard_top)
    )


def legacy_overlap_mask(
    *,
    player_x: np.ndarray,
    player_y: np.ndarray,
    player_half_width: np.ndarray,
    player_half_height: np.ndarray,
    hazard_x: np.ndarray,
    hazard_y: np.ndarray,
    hazard_half_width: np.ndarray,
    hazard_half_height: np.ndarray,
) -> np.ndarray:
    """Former Python topology evaluated as binary64 center distances."""

    px = player_x.astype(np.float64)
    py = player_y.astype(np.float64)
    phw = player_half_width.astype(np.float64)
    phh = player_half_height.astype(np.float64)
    hx = hazard_x.astype(np.float64)
    hy = hazard_y.astype(np.float64)
    hhw = hazard_half_width.astype(np.float64)
    hhh = hazard_half_height.astype(np.float64)
    return (np.abs(px - hx) <= phw + hhw) & (
        np.abs(py - hy) <= phh + hhh
    )


def _step_float32(
    values: np.ndarray,
    steps: np.ndarray,
) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32).copy()
    positive = np.asarray(np.inf, dtype=np.float32)
    negative = np.asarray(-np.inf, dtype=np.float32)
    for threshold in (1, 2):
        result = np.where(
            steps >= threshold,
            np.nextafter(result, positive),
            result,
        )
        result = np.where(
            steps <= -threshold,
            np.nextafter(result, negative),
            result,
        )
    return result.astype(np.float32, copy=False)


def _edge_batch(
    generator: np.random.Generator,
    count: int,
) -> dict[str, np.ndarray]:
    player_x = generator.uniform(8.0, 376.0, count).astype(np.float32)
    player_y = generator.uniform(16.0, 432.0, count).astype(np.float32)
    extent_choices = np.asarray(
        [0.5, 1.0, 1.5, 2.0, 3.0, 4.0],
        dtype=np.float32,
    )
    player_half_width = generator.choice(extent_choices, count)
    player_half_height = generator.choice(extent_choices, count)
    hazard_half_width = generator.uniform(0.125, 32.0, count).astype(
        np.float32
    )
    hazard_half_height = generator.uniform(0.125, 32.0, count).astype(
        np.float32
    )
    axis = generator.integers(0, 2, count, dtype=np.int8)
    side = generator.choice(np.asarray([-1, 1], dtype=np.int8), count)
    construction = generator.integers(0, 2, count, dtype=np.int8)
    ulp_steps = generator.integers(-2, 3, count, dtype=np.int8)

    player_left, player_right = _oracle_bounds(
        player_x,
        player_half_width,
    )
    player_top, player_bottom = _oracle_bounds(
        player_y,
        player_half_height,
    )
    x_boundary = np.where(side > 0, player_right, player_left)
    y_boundary = np.where(side > 0, player_bottom, player_top)
    stored_hazard_x_edge = np.where(
        side > 0,
        x_boundary + hazard_half_width,
        x_boundary - hazard_half_width,
    ).astype(np.float32)
    stored_hazard_y_edge = np.where(
        side > 0,
        y_boundary + hazard_half_height,
        y_boundary - hazard_half_height,
    ).astype(np.float32)
    signed_side = side.astype(np.float32)
    symmetric_hazard_x_edge = np.asarray(
        player_x
        + signed_side * (player_half_width + hazard_half_width),
        dtype=np.float32,
    )
    symmetric_hazard_y_edge = np.asarray(
        player_y
        + signed_side * (player_half_height + hazard_half_height),
        dtype=np.float32,
    )
    hazard_x_edge = np.where(
        construction == 0,
        stored_hazard_x_edge,
        symmetric_hazard_x_edge,
    ).astype(np.float32)
    hazard_y_edge = np.where(
        construction == 0,
        stored_hazard_y_edge,
        symmetric_hazard_y_edge,
    ).astype(np.float32)
    hazard_x_edge = _step_float32(hazard_x_edge, ulp_steps)
    hazard_y_edge = _step_float32(hazard_y_edge, ulp_steps)
    hazard_x = np.where(axis == 0, hazard_x_edge, player_x).astype(np.float32)
    hazard_y = np.where(axis == 1, hazard_y_edge, player_y).astype(np.float32)
    return {
        "player_x": player_x,
        "player_y": player_y,
        "player_half_width": player_half_width,
        "player_half_height": player_half_height,
        "hazard_x": hazard_x,
        "hazard_y": hazard_y,
        "hazard_half_width": hazard_half_width,
        "hazard_half_height": hazard_half_height,
        "axis": axis,
        "side": side,
        "construction": construction,
        "ulp_steps": ulp_steps,
    }


def _witness(
    batch: dict[str, np.ndarray],
    index: int,
    *,
    oracle: bool,
    legacy: bool,
) -> dict[str, object]:
    keys = (
        "player_x",
        "player_y",
        "player_half_width",
        "player_half_height",
        "hazard_x",
        "hazard_y",
        "hazard_half_width",
        "hazard_half_height",
    )
    values = {key: float(batch[key][index]) for key in keys}
    player_left, player_right = _oracle_bounds(
        batch["player_x"][index],
        batch["player_half_width"][index],
    )
    player_top, player_bottom = _oracle_bounds(
        batch["player_y"][index],
        batch["player_half_height"][index],
    )
    hazard_left, hazard_right = _oracle_bounds(
        batch["hazard_x"][index],
        batch["hazard_half_width"][index],
    )
    hazard_top, hazard_bottom = _oracle_bounds(
        batch["hazard_y"][index],
        batch["hazard_half_height"][index],
    )
    values.update(
        {
            "axis": "x" if int(batch["axis"][index]) == 0 else "y",
            "side": int(batch["side"][index]),
            "construction": (
                "stored_edge"
                if int(batch["construction"][index]) == 0
                else "symmetric_center"
            ),
            "ulp_steps": int(batch["ulp_steps"][index]),
            "oracle_overlap": oracle,
            "legacy_overlap": legacy,
            "player_bounds": [
                float(player_left),
                float(player_top),
                float(player_right),
                float(player_bottom),
            ],
            "hazard_bounds": [
                float(hazard_left),
                float(hazard_top),
                float(hazard_right),
                float(hazard_bottom),
            ],
        }
    )
    return values


def edge_fuzz(
    *,
    sample_count: int,
    seed: int,
    chunk_size: int = 250_000,
) -> dict[str, object]:
    if sample_count <= 0 or chunk_size <= 0:
        raise ValueError("edge fuzz counts must be positive")
    generator = np.random.default_rng(seed)
    legacy_mismatches = 0
    corrected_mismatches = 0
    legacy_false_source_true = 0
    legacy_true_source_false = 0
    first_false_true: dict[str, object] | None = None
    first_true_false: dict[str, object] | None = None
    processed = 0
    while processed < sample_count:
        count = min(chunk_size, sample_count - processed)
        batch = _edge_batch(generator, count)
        arguments = {
            key: batch[key]
            for key in (
                "player_x",
                "player_y",
                "player_half_width",
                "player_half_height",
                "hazard_x",
                "hazard_y",
                "hazard_half_width",
                "hazard_half_height",
            )
        }
        oracle = oracle_overlap_mask(**arguments)
        legacy = legacy_overlap_mask(**arguments)
        corrected = source_aabb_overlap_mask(**arguments)
        legacy_difference = legacy != oracle
        corrected_difference = corrected != oracle
        legacy_mismatches += int(np.count_nonzero(legacy_difference))
        corrected_mismatches += int(np.count_nonzero(corrected_difference))
        false_true = (~legacy) & oracle
        true_false = legacy & (~oracle)
        legacy_false_source_true += int(np.count_nonzero(false_true))
        legacy_true_source_false += int(np.count_nonzero(true_false))
        if first_false_true is None and np.any(false_true):
            index = int(np.flatnonzero(false_true)[0])
            first_false_true = _witness(
                batch,
                index,
                oracle=True,
                legacy=False,
            )
        if first_true_false is None and np.any(true_false):
            index = int(np.flatnonzero(true_false)[0])
            first_true_false = _witness(
                batch,
                index,
                oracle=False,
                legacy=True,
            )
        processed += count
    return {
        "seed": seed,
        "sample_count": sample_count,
        "chunk_size": chunk_size,
        "legacy_oracle_mismatch_count": legacy_mismatches,
        "legacy_false_source_true_count": legacy_false_source_true,
        "legacy_true_source_false_count": legacy_true_source_false,
        "corrected_oracle_mismatch_count": corrected_mismatches,
        "first_legacy_false_source_true": first_false_true,
        "first_legacy_true_source_false": first_true_false,
    }


def density_stress(
    *,
    position_count: int,
    seed: int,
) -> dict[str, object]:
    if position_count < 0x600 * 2:
        raise ValueError("density stress needs two edge positions per slot")
    generator = np.random.default_rng(seed)
    bullet_count = 0x600
    hazard_x = generator.uniform(8.0, 376.0, bullet_count).astype(np.float32)
    hazard_y = generator.uniform(16.0, 432.0, bullet_count).astype(np.float32)
    hazard_half_width = generator.uniform(0.25, 24.0, bullet_count).astype(
        np.float32
    )
    hazard_half_height = generator.uniform(0.25, 24.0, bullet_count).astype(
        np.float32
    )
    player_half_width = np.float32(1.0)
    player_half_height = np.float32(1.0)
    positions_x = generator.uniform(8.0, 376.0, position_count).astype(np.float32)
    positions_y = generator.uniform(16.0, 432.0, position_count).astype(np.float32)
    hazard_left, hazard_right = _oracle_bounds(hazard_x, hazard_half_width)
    hazard_top, hazard_bottom = _oracle_bounds(hazard_y, hazard_half_height)
    positions_x[:bullet_count] = np.asarray(
        hazard_right + player_half_width,
        dtype=np.float32,
    )
    positions_y[:bullet_count] = hazard_y
    positions_x[bullet_count : 2 * bullet_count] = hazard_x
    positions_y[bullet_count : 2 * bullet_count] = np.asarray(
        hazard_bottom + player_half_height,
        dtype=np.float32,
    )

    native_state = generator.integers(
        1,
        6,
        bullet_count,
        dtype=np.uint16,
    )
    callback_aux = generator.integers(
        0,
        3,
        bullet_count,
        dtype=np.uint8,
    )
    # Keep a substantial exact-lethal cohort while retaining lifecycle noise.
    native_state[: bullet_count // 2] = 1
    callback_aux[: bullet_count // 3] = 0
    eligible = (native_state == 1) & (callback_aux == 0)
    bullet_frame = (
        hazard_x,
        hazard_y,
        hazard_half_width,
        hazard_half_height,
        np.zeros(bullet_count, dtype=np.bool_),
        native_state,
        callback_aux,
    )
    _risk, integration_collisions, _minimum = (
        source_collision_hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=bullet_frame,
            lasers=(),
            enemy_bodies=(),
            player_half_width=1.0,
            player_half_height=1.0,
        )
    )

    corrected_mismatches = 0
    legacy_mismatches = 0
    oracle_collision_counts = np.zeros(position_count, dtype=np.int32)
    chunk_size = 256
    for start in range(0, position_count, chunk_size):
        stop = min(position_count, start + chunk_size)
        arguments = {
            "player_x": positions_x[start:stop, None],
            "player_y": positions_y[start:stop, None],
            "player_half_width": player_half_width,
            "player_half_height": player_half_height,
            "hazard_x": hazard_x[None, :],
            "hazard_y": hazard_y[None, :],
            "hazard_half_width": hazard_half_width[None, :],
            "hazard_half_height": hazard_half_height[None, :],
        }
        oracle = oracle_overlap_mask(**arguments)
        corrected = source_aabb_overlap_mask(**arguments)
        legacy = legacy_overlap_mask(**arguments)
        corrected_mismatches += int(np.count_nonzero(corrected != oracle))
        legacy_mismatches += int(np.count_nonzero(legacy != oracle))
        oracle_collision_counts[start:stop] = (
            oracle[:, eligible].sum(axis=1, dtype=np.int32)
        )
    integration_difference = integration_collisions != oracle_collision_counts
    return {
        "seed": seed,
        "position_count": position_count,
        "bullet_count": bullet_count,
        "pair_count": position_count * bullet_count,
        "eligible_bullet_count": int(np.count_nonzero(eligible)),
        "corrected_oracle_mismatch_count": corrected_mismatches,
        "legacy_oracle_mismatch_count": legacy_mismatches,
        "integration_collision_count_mismatch_positions": int(
            np.count_nonzero(integration_difference)
        ),
        "maximum_oracle_collision_count": int(oracle_collision_counts.max()),
        "maximum_integration_collision_count": int(
            integration_collisions.max()
        ),
        "all_outputs_finite": bool(
            np.all(np.isfinite(_risk)) and np.all(np.isfinite(_minimum))
        ),
    }


def build_report(
    *,
    sample_count: int,
    position_count: int,
    seed: int,
) -> dict[str, object]:
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "source_authority": {
            "function": "Player::FUN_0044a230",
            "source_path": "../th08/src/Player.cpp",
            "matching_ledger": "../th08/config/matches.csv",
            "bounds_storage": "Float3 binary32",
            "separation_comparisons": [">", ">", "<", "<"],
            "touching_edges_overlap": True,
        },
        "corrected_semantics_version": TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
        "edge_fuzz": edge_fuzz(
            sample_count=sample_count,
            seed=seed,
        ),
        "density_stress": density_stress(
            position_count=position_count,
            seed=seed ^ 0x600,
        ),
        "authority": {
            "accepted_for": (
                "bullet/player and axis-aligned enemy/player binary32 AABB "
                "topology, inclusive edge booleans, lifecycle-filtered "
                "vectorized collision counts, and dense-pool numerical stress"
            ),
            "not_accepted_for": (
                "player slot interception, laser rotation, multi-frame bullet "
                "motion/lifecycle, uncertainty calibration, hit causality, "
                "or live action authority"
            ),
            "edge_fuzz_rate_is_live_route_estimate": False,
        },
    }
    digest_payload = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_digest"] = hashlib.sha256(digest_payload).hexdigest()
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2_000_000)
    parser.add_argument("--positions", type=int, default=4_096)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        sample_count=args.samples,
        position_count=args.positions,
        seed=args.seed,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
