#!/usr/bin/env python3
"""Compare legacy and source-derived collision sets on one retained TH08 root."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import partial
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from th08_live.local_certificates import legacy_robust_action_certificates
from th08_live.models import Bullet
from th08_live.movement import (
    LOCAL_PIPELINE_STATE_ACTIONS,
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
)
from th08_source_collision import (
    TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
    player_half_extents_from_aabb,
    source_collision_hazards_for_positions,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT_REPORT = (
    ROOT
    / "artifacts"
    / "runtime_reports"
    / "th08_native_model_consumable_h1_root2129_20260730.json"
)
REPORT_SCHEMA = "th08-source-collision-root-differential-v1"


def _historical_radius2_hazards_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[object, ...],
    enemy_bodies: tuple[object, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Freeze the pre-promotion radius-2/all-state root comparison.

    The root contains no lasers or enemy bodies, and the binary32-v2
    regeneration already proved that exact-edge storage does not change this
    root.  Keeping this oracle local prevents a later live-kernel promotion
    from silently rewriting historical audit terminology.
    """

    return source_collision_hazards_for_positions(
        positions_x,
        positions_y,
        step=step,
        bullet_frame=bullet_frame,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        player_half_width=2.0,
        player_half_height=2.0,
        filter_bullet_lifecycle=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _root_payload(document: dict[str, Any]) -> dict[str, Any]:
    try:
        return document["artifacts"]["native_hazard_root"]["payload"]
    except (KeyError, TypeError) as error:
        raise ValueError("report lacks an embedded native hazard root") from error


def _root_bullets(payload: dict[str, Any]) -> tuple[Bullet, ...]:
    return tuple(
        Bullet(
            x=float(row["x"]),
            y=float(row["y"]),
            vx=float(row["vx"]),
            vy=float(row["vy"]),
            half_width=float(row["half_width"]),
            half_height=float(row["half_height"]),
            transform_flags=int(row["transform_flags"]),
            slot=int(row["slot"]),
            original_transform_flags=int(row["original_transform_flags"]),
            # This retained legacy root predates callback-aux retention.
            # State-1 records are therefore kept lethal; only states 2..5 are
            # removed.
            callback_aux_state=0,
            native_state=int(row["state"]),
            native_state_timer_elapsed=int(row["timer_d80_elapsed"]),
        )
        for row in payload["bullets"]
    )


def _current_bullet_frame(bullets: tuple[Bullet, ...]) -> tuple[np.ndarray, ...]:
    return (
        np.fromiter((bullet.x for bullet in bullets), dtype=np.float32),
        np.fromiter((bullet.y for bullet in bullets), dtype=np.float32),
        np.fromiter((bullet.half_width for bullet in bullets), dtype=np.float32),
        np.fromiter((bullet.half_height for bullet in bullets), dtype=np.float32),
        np.fromiter(
            (bool(bullet.transform_flags) for bullet in bullets),
            dtype=np.bool_,
        ),
        np.fromiter(
            (bullet.native_state for bullet in bullets),
            dtype=np.uint16,
        ),
        np.zeros(len(bullets), dtype=np.uint8),
    )


def _safe_actions(certificates: dict[str, Any]) -> list[str]:
    return [
        name
        for name, certificate in certificates.items()
        if certificate.worst_collisions == 0
        and certificate.min_clearance >= 0.0
    ]


def _membership_grid(
    *,
    bullet_frame: tuple[np.ndarray, ...],
    player_half_width: float,
    player_half_height: float,
    grid_step: float,
) -> dict[str, object]:
    if not np.isfinite(grid_step) or grid_step <= 0.0:
        raise ValueError("collision differential grid step must be positive")
    xs = np.arange(
        PLAYFIELD_LEFT,
        PLAYFIELD_RIGHT + grid_step * 0.5,
        grid_step,
        dtype=np.float32,
    )
    ys = np.arange(
        PLAYFIELD_TOP,
        PLAYFIELD_BOTTOM + grid_step * 0.5,
        grid_step,
        dtype=np.float32,
    )
    counts: Counter[str] = Counter()
    geometry_query = partial(
        source_collision_hazards_for_positions,
        player_half_width=player_half_width,
        player_half_height=player_half_height,
        filter_bullet_lifecycle=False,
    )
    source_query = partial(
        source_collision_hazards_for_positions,
        player_half_width=player_half_width,
        player_half_height=player_half_height,
        filter_bullet_lifecycle=True,
    )
    # Bound peak temporary matrices independently of VPS RAM so this remains
    # usable on ordinary development machines too.
    rows_per_chunk = max(1, min(16, len(ys)))
    for start in range(0, len(ys), rows_per_chunk):
        chunk_y = ys[start : start + rows_per_chunk]
        grid_x, grid_y = np.meshgrid(xs, chunk_y)
        positions_x = grid_x.ravel()
        positions_y = grid_y.ravel()
        legacy_collisions = _historical_radius2_hazards_for_positions(
            positions_x,
            positions_y,
            step=0,
            bullet_frame=bullet_frame,
            lasers=(),
            enemy_bodies=(),
        )[1]
        geometry_collisions = geometry_query(
            positions_x,
            positions_y,
            step=0,
            bullet_frame=bullet_frame,
            lasers=(),
            enemy_bodies=(),
        )[1]
        source_collisions = source_query(
            positions_x,
            positions_y,
            step=0,
            bullet_frame=bullet_frame,
            lasers=(),
            enemy_bodies=(),
        )[1]
        legacy = legacy_collisions > 0
        geometry = geometry_collisions > 0
        source = source_collisions > 0
        counts.update(
            {
                "sampled_positions": positions_x.size,
                "legacy_collision_positions": int(np.count_nonzero(legacy)),
                "source_geometry_collision_positions": int(
                    np.count_nonzero(geometry)
                ),
                "source_geometry_lifecycle_collision_positions": int(
                    np.count_nonzero(source)
                ),
                "legacy_only_geometry_positions": int(
                    np.count_nonzero(legacy & ~geometry)
                ),
                "geometry_only_legacy_positions": int(
                    np.count_nonzero(geometry & ~legacy)
                ),
                "known_lifecycle_removed_positions": int(
                    np.count_nonzero(geometry & ~source)
                ),
                "source_only_legacy_positions": int(
                    np.count_nonzero(source & ~legacy)
                ),
                "legacy_collision_instances": int(legacy_collisions.sum()),
                "source_geometry_collision_instances": int(
                    geometry_collisions.sum()
                ),
                "source_geometry_lifecycle_collision_instances": int(
                    source_collisions.sum()
                ),
            }
        )
    return {
        "grid_step": grid_step,
        "x_count": len(xs),
        "y_count": len(ys),
        **dict(counts),
    }


def analyze_root_report(
    path: Path,
    *,
    grid_step: float = 1.0,
) -> dict[str, object]:
    path = path.resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = _root_payload(document)
    state = payload["compact_state"]
    player_x = float(state["player_x"])
    player_y = float(state["player_y"])
    player_half_width, player_half_height = player_half_extents_from_aabb(
        player_x=player_x,
        player_y=player_y,
        lethal_aabb=payload["player_lethal_aabb"],
    )
    bullets = _root_bullets(payload)
    state_counts = Counter(bullet.native_state for bullet in bullets)
    current_frame = _current_bullet_frame(bullets)
    membership = _membership_grid(
        bullet_frame=current_frame,
        player_half_width=player_half_width,
        player_half_height=player_half_height,
        grid_step=grid_step,
    )

    certificate_arguments = {
        "player_x": player_x,
        "player_y": player_y,
        "previous_mask": int(state["input_current"]),
        "actions": LOCAL_PIPELINE_STATE_ACTIONS,
        "delay_frames": (0,),
        "action_hold_frames": 1,
        "bullets": bullets,
        "lasers": (),
        "enemy_bodies": (),
        "snapshot_lag": 0,
        "player_scale_bits": (int(state["time_scale_bits"]),),
        "laser_scale_bits": (int(state["time_scale_bits"]),),
    }
    legacy_certificates = legacy_robust_action_certificates(
        hazards_for_positions=_historical_radius2_hazards_for_positions,
        **certificate_arguments,
    )
    geometry_certificates = legacy_robust_action_certificates(
        hazards_for_positions=partial(
            source_collision_hazards_for_positions,
            player_half_width=player_half_width,
            player_half_height=player_half_height,
            filter_bullet_lifecycle=False,
        ),
        **certificate_arguments,
    )
    source_certificates = legacy_robust_action_certificates(
        hazards_for_positions=partial(
            source_collision_hazards_for_positions,
            player_half_width=player_half_width,
            player_half_height=player_half_height,
            filter_bullet_lifecycle=True,
        ),
        **certificate_arguments,
    )
    legacy_safe = _safe_actions(legacy_certificates)
    geometry_safe = _safe_actions(geometry_certificates)
    source_safe = _safe_actions(source_certificates)
    action_rows = []
    for action in LOCAL_PIPELINE_STATE_ACTIONS:
        legacy = legacy_certificates[action.name]
        geometry = geometry_certificates[action.name]
        source = source_certificates[action.name]
        action_rows.append(
            {
                "action": action.name,
                "legacy_collisions": legacy.worst_collisions,
                "legacy_min_clearance": legacy.min_clearance,
                "source_geometry_collisions": geometry.worst_collisions,
                "source_geometry_min_clearance": geometry.min_clearance,
                "source_lifecycle_collisions": source.worst_collisions,
                "source_lifecycle_min_clearance": source.min_clearance,
            }
        )

    h1_exact = document["artifacts"]["first_mismatch_report"]["payload"][
        "corrected_root_active_bullet_h1"
    ]
    return {
        "schema": REPORT_SCHEMA,
        "source_collision_semantics": TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
        "source": {
            "path": str(path),
            "sha256": _sha256(path),
            "embedded_collision_projection_schema": payload.get(
                "collision_projection_schema"
            ),
        },
        "root": {
            "manager_frame": int(payload["manager_frame"]),
            "player": {
                "x": player_x,
                "y": player_y,
                "lethal_aabb": list(payload["player_lethal_aabb"]),
                "lethal_half_extents": [
                    player_half_width,
                    player_half_height,
                ],
            },
            "bullet_count": len(bullets),
            "native_state_counts": {
                str(state): count for state, count in sorted(state_counts.items())
            },
            "known_nonlethal_state_count": sum(
                count for state, count in state_counts.items() if state != 1
            ),
            "laser_count": len(payload.get("lasers", ())),
        },
        "root_membership_grid": membership,
        "one_step_action_set": {
            "role": "shadow_root_active_bullet_cohort_only",
            "coverage": {
                "common_slots_with_exact_h1_motion": int(
                    document["result"]["corrected_exact_common_slots"]
                ),
                "unapplied_native_removals": int(
                    document["result"]["removal_count"]
                ),
                "excluded_native_births": int(document["result"]["birth_count"]),
                "complete_hazard_inventory": False,
            },
            "horizon_frames": 1,
            "delay_frames": [0],
            "legacy_safe_actions": legacy_safe,
            "source_geometry_safe_actions": geometry_safe,
            "source_geometry_lifecycle_safe_actions": source_safe,
            "source_added_safe_actions": sorted(set(source_safe) - set(legacy_safe)),
            "source_removed_safe_actions": sorted(set(legacy_safe) - set(source_safe)),
            "rows": action_rows,
        },
        "authority": {
            "historical_legacy_geometry": (
                "frozen_radius2_all_state_aabb; root proven insensitive to "
                "binary32-v2 edge correction"
            ),
            "player_geometry": "exact_cached_native_aabb",
            "bullet_state": "retained_native_state",
            "bullet_callback_aux": (
                "unavailable_in_legacy_root; state1 conservatively_kept_lethal"
            ),
            "one_step_motion": h1_exact,
            "one_step_inventory": (
                "incomplete_root_cohort_only; native births excluded and "
                "native removals retained"
            ),
            "lasers": "root_contains_none",
            "enemy_bodies": "not_retained_in_compact_root",
            "accepted_for": (
                "shadow lower bound on legacy false positives from player "
                "extent and known nonlethal bullet states"
            ),
            "not_accepted_for": (
                "live action authority, callback-suppressed classification, "
                "multi-frame lifecycle, laser/body promotion, or hit-count claim"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_ROOT_REPORT)
    parser.add_argument("--grid-step", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_root_report(args.input, grid_step=args.grid_step)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
