#!/usr/bin/env python3
"""High-density gate for the source AABB semantics promoted into live play."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from th08_laser_runtime import PackedLaserFrame
from th08_live.local_hazards import (
    _native_hazards_for_positions,
    _numpy_hazards_for_positions,
)
from th08_live.movement import (
    PLAYER_LETHAL_HALF_HEIGHT,
    PLAYER_LETHAL_HALF_WIDTH,
)
from th08_collision_versions import LIVE_LOCAL_COLLISION_SEMANTICS_VERSION
from th08_source_collision import TH08_SOURCE_COLLISION_SEMANTICS_VERSION
from touhou_control import native_backend


SCHEMA = "th08-live-source-aabb-promotion-differential-v2-state1-lifecycle"
DEFAULT_SEED = 0x44A23005
DEFAULT_REPORT = Path(
    "artifacts/runtime_reports/"
    "th08_live_source_aabb_promotion_differential_20260824.json"
)


def _empty_lasers() -> PackedLaserFrame:
    empty = np.empty(0, dtype=np.float32)
    return PackedLaserFrame(
        start_x=empty,
        start_y=empty,
        segment_x=empty,
        segment_y=empty,
        collision_radius=empty,
        base_uncertainty=empty,
        uncertainty_per_frame=empty,
    )


def _oracle_bounds(
    center: np.ndarray,
    half_extent: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray]:
    """Independent transcription of each stored source Float3 component."""

    center = np.asarray(center, dtype=np.float32)
    half_extent = np.asarray(half_extent, dtype=np.float32)
    return (
        np.asarray(center - half_extent, dtype=np.float32),
        np.asarray(center + half_extent, dtype=np.float32),
    )


def oracle_overlap_mask(
    *,
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    hazard_x: np.ndarray,
    hazard_y: np.ndarray,
    hazard_half_width: np.ndarray,
    hazard_half_height: np.ndarray,
    player_half_width: float = PLAYER_LETHAL_HALF_WIDTH,
    player_half_height: float = PLAYER_LETHAL_HALF_HEIGHT,
) -> np.ndarray:
    player_left, player_right = _oracle_bounds(
        positions_x[:, None],
        player_half_width,
    )
    player_top, player_bottom = _oracle_bounds(
        positions_y[:, None],
        player_half_height,
    )
    hazard_left, hazard_right = _oracle_bounds(
        hazard_x[None, :],
        hazard_half_width[None, :],
    )
    hazard_top, hazard_bottom = _oracle_bounds(
        hazard_y[None, :],
        hazard_half_height[None, :],
    )
    return ~(
        (player_left > hazard_right)
        | (player_top > hazard_bottom)
        | (player_right < hazard_left)
        | (player_bottom < hazard_top)
    )


def legacy_radius2_overlap_mask(
    *,
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    hazard_x: np.ndarray,
    hazard_y: np.ndarray,
    hazard_half_width: np.ndarray,
    hazard_half_height: np.ndarray,
) -> np.ndarray:
    """Historical live center-distance predicate, including state 5."""

    dx = np.abs(positions_x[:, None] - hazard_x[None, :]) - (
        2.0 + hazard_half_width[None, :]
    )
    dy = np.abs(positions_y[:, None] - hazard_y[None, :]) - (
        2.0 + hazard_half_height[None, :]
    )
    return (dx <= 0.0) & (dy <= 0.0)


def _workload(
    *,
    position_count: int,
    bullet_count: int,
    seed: int,
) -> dict[str, np.ndarray]:
    if position_count < 4 or bullet_count < 5:
        raise ValueError("dense promotion workload is too small")
    generator = np.random.default_rng(seed)
    bullet_x = generator.uniform(12.0, 372.0, bullet_count).astype(np.float32)
    bullet_y = generator.uniform(20.0, 428.0, bullet_count).astype(np.float32)
    extent_choices = np.asarray(
        [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0],
        dtype=np.float32,
    )
    half_width = generator.choice(extent_choices, bullet_count).astype(np.float32)
    half_height = generator.choice(extent_choices, bullet_count).astype(np.float32)
    native_state = np.resize(
        np.asarray([1, 2, 3, 4, 5], dtype=np.uint16),
        bullet_count,
    )
    generator.shuffle(native_state)

    owner = np.arange(position_count, dtype=np.intp) % bullet_count
    mode = np.arange(position_count, dtype=np.intp) % 4
    positions_x = np.empty(position_count, dtype=np.float32)
    positions_y = np.empty(position_count, dtype=np.float32)

    edge = mode == 0
    hazard_right = np.asarray(
        bullet_x[owner[edge]] + half_width[owner[edge]],
        dtype=np.float32,
    )
    edge_center = np.asarray(
        hazard_right + np.float32(PLAYER_LETHAL_HALF_WIDTH),
        dtype=np.float32,
    )
    edge_steps = generator.integers(-2, 3, edge_center.size)
    for index, steps in enumerate(edge_steps):
        value = edge_center[index]
        direction = np.float32(-np.inf if steps < 0 else np.inf)
        for _ in range(abs(int(steps))):
            value = np.nextafter(value, direction, dtype=np.float32)
        edge_center[index] = value
    positions_x[edge] = edge_center
    positions_y[edge] = bullet_y[owner[edge]]

    radius_gap = mode == 1
    positions_x[radius_gap] = np.asarray(
        bullet_x[owner[radius_gap]]
        + half_width[owner[radius_gap]]
        + np.float32(1.5),
        dtype=np.float32,
    )
    positions_y[radius_gap] = bullet_y[owner[radius_gap]]

    interior = mode == 2
    positions_x[interior] = np.asarray(
        bullet_x[owner[interior]]
        + generator.uniform(-0.75, 0.75, interior.sum()),
        dtype=np.float32,
    )
    positions_y[interior] = np.asarray(
        bullet_y[owner[interior]]
        + generator.uniform(-0.75, 0.75, interior.sum()),
        dtype=np.float32,
    )

    random_field = mode == 3
    positions_x[random_field] = generator.uniform(
        8.0,
        376.0,
        random_field.sum(),
    ).astype(np.float32)
    positions_y[random_field] = generator.uniform(
        16.0,
        432.0,
        random_field.sum(),
    ).astype(np.float32)

    return {
        "positions_x": positions_x,
        "positions_y": positions_y,
        "bullet_x": bullet_x,
        "bullet_y": bullet_y,
        "half_width": half_width,
        "half_height": half_height,
        "transformed": generator.integers(
            0,
            2,
            bullet_count,
            dtype=np.uint8,
        ).astype(np.bool_),
        "native_state": native_state,
        "callback_aux": generator.integers(
            0,
            8,
            bullet_count,
            dtype=np.uint8,
        ),
    }


def _collision_counts(
    mask: np.ndarray,
) -> np.ndarray:
    return mask.sum(axis=1, dtype=np.int32)


def density_stress(
    *,
    position_count: int,
    bullet_count: int,
    seed: int,
) -> dict[str, object]:
    workload = _workload(
        position_count=position_count,
        bullet_count=bullet_count,
        seed=seed,
    )
    state_lethal = workload["native_state"] == 1
    callback_collision_enabled = workload["callback_aux"] == 0
    collision_enabled = state_lethal & callback_collision_enabled
    oracle_started = time.perf_counter()
    oracle_counts = _collision_counts(
        oracle_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"][collision_enabled],
            hazard_y=workload["bullet_y"][collision_enabled],
            hazard_half_width=workload["half_width"][collision_enabled],
            hazard_half_height=workload["half_height"][collision_enabled],
        )
    )
    oracle_ms = (time.perf_counter() - oracle_started) * 1000.0

    frame = (
        workload["bullet_x"],
        workload["bullet_y"],
        workload["half_width"],
        workload["half_height"],
        workload["transformed"],
        workload["native_state"],
        workload["callback_aux"],
    )
    arguments = {
        "step": 11,
        "bullet_frame": frame,
        "lasers": _empty_lasers(),
        "enemy_bodies": (),
    }
    numpy_started = time.perf_counter()
    numpy_result = _numpy_hazards_for_positions(
        workload["positions_x"],
        workload["positions_y"],
        **arguments,
    )
    numpy_ms = (time.perf_counter() - numpy_started) * 1000.0
    native_started = time.perf_counter()
    native_result = _native_hazards_for_positions(
        workload["positions_x"],
        workload["positions_y"],
        **arguments,
    )
    native_ms = (time.perf_counter() - native_started) * 1000.0

    geometry_started = time.perf_counter()
    legacy_retained_counts = _collision_counts(
        legacy_radius2_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"][collision_enabled],
            hazard_y=workload["bullet_y"][collision_enabled],
            hazard_half_width=workload["half_width"][collision_enabled],
            hazard_half_height=workload["half_height"][collision_enabled],
        )
    )
    legacy_all_counts = _collision_counts(
        legacy_radius2_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"],
            hazard_y=workload["bullet_y"],
            hazard_half_width=workload["half_width"],
            hazard_half_height=workload["half_height"],
        )
    )
    source_all_counts = _collision_counts(
        oracle_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"],
            hazard_y=workload["bullet_y"],
            hazard_half_width=workload["half_width"],
            hazard_half_height=workload["half_height"],
        )
    )
    source_state1_counts = _collision_counts(
        oracle_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"][state_lethal],
            hazard_y=workload["bullet_y"][state_lethal],
            hazard_half_width=workload["half_width"][state_lethal],
            hazard_half_height=workload["half_height"][state_lethal],
        )
    )
    source_callback_enabled_counts = _collision_counts(
        oracle_overlap_mask(
            positions_x=workload["positions_x"],
            positions_y=workload["positions_y"],
            hazard_x=workload["bullet_x"][callback_collision_enabled],
            hazard_y=workload["bullet_y"][callback_collision_enabled],
            hazard_half_width=workload["half_width"][callback_collision_enabled],
            hazard_half_height=workload["half_height"][callback_collision_enabled],
        )
    )
    decomposition_ms = (time.perf_counter() - geometry_started) * 1000.0
    gc.collect()

    numpy_collision_mismatch = int(
        np.count_nonzero(numpy_result[1] != oracle_counts)
    )
    native_collision_mismatch = int(
        np.count_nonzero(native_result[1] != oracle_counts)
    )
    finite_minimum = np.isfinite(numpy_result[2]) & np.isfinite(native_result[2])
    minimum_error = (
        float(
            np.max(
                np.abs(
                    numpy_result[2][finite_minimum]
                    - native_result[2][finite_minimum]
                )
            )
        )
        if np.any(finite_minimum)
        else 0.0
    )
    risk_error = float(np.max(np.abs(numpy_result[0] - native_result[0])))
    return {
        "seed": seed,
        "position_count": position_count,
        "bullet_count": bullet_count,
        "retained_bullet_count": int(collision_enabled.sum()),
        "state1_bullet_count": int(state_lethal.sum()),
        "callback_collision_enabled_bullet_count": int(
            callback_collision_enabled.sum()
        ),
        "callback_collision_disabled_bullet_count": int(
            (~callback_collision_enabled).sum()
        ),
        "nonlethal_state_count": int((~state_lethal).sum()),
        "pair_count": position_count * bullet_count,
        "retained_pair_count": position_count * int(collision_enabled.sum()),
        "oracle_collision_total": int(oracle_counts.sum()),
        "numpy_collision_total": int(numpy_result[1].sum()),
        "native_collision_total": int(native_result[1].sum()),
        "numpy_oracle_collision_mismatch_positions": numpy_collision_mismatch,
        "native_oracle_collision_mismatch_positions": native_collision_mismatch,
        "numpy_native_collision_mismatch_positions": int(
            np.count_nonzero(numpy_result[1] != native_result[1])
        ),
        "numpy_native_minimum_max_abs_error": minimum_error,
        "numpy_native_risk_max_abs_error": risk_error,
        "legacy_radius2_retained_collision_total": int(
            legacy_retained_counts.sum()
        ),
        "legacy_radius2_all_state_collision_total": int(
            legacy_all_counts.sum()
        ),
        "source_radius1_all_state_collision_total": int(
            source_all_counts.sum()
        ),
        "geometry_only_changed_positions": int(
            np.count_nonzero(legacy_retained_counts != oracle_counts)
        ),
        "nonlethal_state_changed_positions": int(
            np.count_nonzero(source_callback_enabled_counts != oracle_counts)
        ),
        "callback_aux_changed_positions": int(
            np.count_nonzero(source_state1_counts != oracle_counts)
        ),
        "combined_historical_changed_positions": int(
            np.count_nonzero(legacy_all_counts != oracle_counts)
        ),
        "timing_ms": {
            "oracle": oracle_ms,
            "numpy_live": numpy_ms,
            "native_live": native_ms,
            "effect_decomposition": decomposition_ms,
        },
        "finite_outputs": bool(
            np.all(np.isfinite(numpy_result[0]))
            and np.all(np.isfinite(native_result[0]))
            and np.all(
                np.isfinite(numpy_result[2]) | np.isposinf(numpy_result[2])
            )
            and np.all(
                np.isfinite(native_result[2]) | np.isposinf(native_result[2])
            )
        ),
    }


def build_report(
    *,
    position_count: int,
    bullet_count: int,
    seed: int,
) -> dict[str, object]:
    native_available = native_backend._load_local_hazards_function() is not None
    if not native_available:
        raise RuntimeError("native local hazard kernel is not built")
    stress = density_stress(
        position_count=position_count,
        bullet_count=bullet_count,
        seed=seed,
    )
    checks = {
        "numpy_matches_independent_source_oracle": (
            stress["numpy_oracle_collision_mismatch_positions"] == 0
        ),
        "native_matches_independent_source_oracle": (
            stress["native_oracle_collision_mismatch_positions"] == 0
        ),
        "native_matches_numpy_collision_counts": (
            stress["numpy_native_collision_mismatch_positions"] == 0
        ),
        "historical_geometry_difference_exercised": (
            stress["geometry_only_changed_positions"] > 0
        ),
        "nonlethal_state_difference_exercised": (
            stress["nonlethal_state_changed_positions"] > 0
        ),
        "callback_aux_difference_exercised": (
            stress["callback_aux_changed_positions"] > 0
        ),
        "all_outputs_valid": stress["finite_outputs"],
    }
    return {
        "schema": SCHEMA,
        "role": "offline_promotion_gate_no_action_authority",
        "source_collision_semantics": TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
        "live_local_collision_semantics": LIVE_LOCAL_COLLISION_SEMANTICS_VERSION,
        "live_player_lethal_half_extents": [
            PLAYER_LETHAL_HALF_WIDTH,
            PLAYER_LETHAL_HALF_HEIGHT,
        ],
        "lifecycle_policy": (
            "source_lethal_state1_and_callback_aux_zero_after_exact_"
            "type_authoritative_spawn_projection"
        ),
        "native_available": native_available,
        "stress": stress,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=4096)
    parser.add_argument("--bullets", type=int, default=1536)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        position_count=args.positions,
        bullet_count=args.bullets,
        seed=args.seed,
    )
    payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(args.output)
    print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
    print(json.dumps(report["checks"], indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
