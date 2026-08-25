"""Fail-closed TH08 authority contract for asynchronously solved policies."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Mapping, Protocol

import numpy as np

from th08_corridor_adapter import (
    TH08_CORRIDOR_BULLET_SEMANTICS_VERSION,
    TH08_VIABILITY_ACTIONS,
)
from th08_collision_versions import (
    LIVE_LOCAL_COLLISION_SEMANTICS_VERSION,
    TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
)
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_laser_model import TH08_LASER_SCALE_SEMANTICS_VERSION
from th08_callback_join_contract import (
    CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION,
    CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION,
    CurrentPoolProjectionCallbackJoinContract,
)
from th08_movement_model import (
    TH08_PLAYER_CENTER_BOUNDS_SEMANTICS_VERSION,
    TH08_ROUTE2_MOVEMENT_SCALE_SEMANTICS_VERSION,
)
from th08_time_scale import (
    SCALE_COVERAGE_COMPLETE,
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)
from touhou_control.corridor import CorridorConfig
from touhou_control.hazard_coverage import HazardCoverageAssessment
from touhou_control.pipeline_identity import VersionIdentity
from touhou_control.policy_authority import PolicyAuthorityVersion


TH08_GLOBAL_AUTHORITY_ROOT_SCHEMA = "th08-global-policy-root-v1"
TH08_GLOBAL_GEOMETRY_AUTHORITY_SEMANTICS_VERSION = (
    "th08-global-geometry-v3-current-pool-callback-join"
)
TH08_GLOBAL_POLICY_AUTHORITY_SEMANTICS_VERSION = (
    "th08-global-corridor-policy-v1-robust-delay-unit-scale"
)


class _GlobalSolution(Protocol):
    source_frame: int
    snapshot_frame: int | None
    forecast_lead_frames: int
    context_key: tuple[int, int, int | None] | None
    time_scale_identity: tuple[object, ...] | None
    future_hazard_version: VersionIdentity | None
    future_hazard_coverage: HazardCoverageAssessment | None
    future_hazard_projection: object | None
    current_pool_callback_join_version: VersionIdentity | None
    current_pool_callback_join: object | None
    authority_version: PolicyAuthorityVersion | None


class RuntimeEclVersion(Protocol):
    runtime_base: int
    image_length: int
    relocated_sha256: str
    normalized_sha256: str
    static_sha256: str
    route_id: int
    difficulty_index: int
    stage_route_index: int
    gameplay_epoch: int
    decision_frame: int
    snapshot_frame: int


def _canonical_value(value: object) -> object:
    """Return a deterministic exact-value JSON form for one frozen root."""

    if value is None or type(value) in (bool, int, str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("global authority root contains a nonfinite float")
        return {"float_hex": value.hex()}
    if isinstance(value, np.generic):
        return _canonical_value(value.item())
    if isinstance(value, np.ndarray):
        contiguous = np.ascontiguousarray(value)
        return {
            "ndarray_dtype": contiguous.dtype.str,
            "ndarray_shape": list(contiguous.shape),
            "ndarray_sha256": hashlib.sha256(
                contiguous.tobytes(order="C")
            ).hexdigest(),
        }
    if isinstance(value, bytes):
        return {
            "bytes_length": len(value),
            "bytes_sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, Enum):
        return {
            "enum": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": _canonical_value(value.value),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "dataclass": (
                f"{type(value).__module__}.{type(value).__qualname__}"
            ),
            "fields": {
                field.name: _canonical_value(getattr(value, field.name))
                for field in fields(value)
                if field.compare
            },
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("global authority mappings require string keys")
        return {
            key: _canonical_value(value[key])
            for key in sorted(value)
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    raise TypeError(
        "unsupported global authority root value: "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _payload_digest(payload: object) -> str:
    encoded = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def runtime_ecl_version_identity(
    version: RuntimeEclVersion,
) -> VersionIdentity:
    return VersionIdentity.from_mapping(
        "th08-runtime-ecl-accepted-version-v1",
        {
            "decision_frame": version.decision_frame,
            "difficulty_index": version.difficulty_index,
            "gameplay_epoch": version.gameplay_epoch,
            "image_length": version.image_length,
            "normalized_sha256": version.normalized_sha256,
            "relocated_sha256": version.relocated_sha256,
            "route_id": version.route_id,
            "runtime_base": version.runtime_base,
            "snapshot_frame": version.snapshot_frame,
            "stage_route_index": version.stage_route_index,
            "static_sha256": version.static_sha256,
        },
    )


def time_scale_version_identity(
    serialized_identity: tuple[object, ...],
) -> VersionIdentity:
    return VersionIdentity.from_mapping(
        "th08-time-scale-schedule-version-v1",
        {
            "digest": _payload_digest(serialized_identity),
            "semantics": TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
        },
    )


def th08_global_geometry_identity() -> VersionIdentity:
    return VersionIdentity.from_mapping(
        TH08_GLOBAL_GEOMETRY_AUTHORITY_SEMANTICS_VERSION,
        {
            "bullet": TH08_CORRIDOR_BULLET_SEMANTICS_VERSION,
            "callback_composition": (
                CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION
            ),
            "callback_join": CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION,
            "laser": TH08_LASER_SCALE_SEMANTICS_VERSION,
            "live_local": LIVE_LOCAL_COLLISION_SEMANTICS_VERSION,
            "movement": TH08_ROUTE2_MOVEMENT_SCALE_SEMANTICS_VERSION,
            "player_bounds": TH08_PLAYER_CENTER_BOUNDS_SEMANTICS_VERSION,
            "source_collision": TH08_SOURCE_COLLISION_SEMANTICS_VERSION,
        },
    )


def th08_global_policy_identity(
    corridor_config: CorridorConfig,
) -> VersionIdentity:
    payload = {
        "semantics": TH08_GLOBAL_POLICY_AUTHORITY_SEMANTICS_VERSION,
        "config": {
            field.name: getattr(corridor_config, field.name)
            for field in fields(corridor_config)
        },
        "actions": tuple(
            (action.name, action.velocity_x, action.velocity_y)
            for action in TH08_VIABILITY_ACTIONS
        ),
        "survival_labels": False,
        "live_refinement_grid_steps": (),
    }
    return VersionIdentity.from_mapping(
        "th08-global-corridor-policy-version-v1",
        {
            "digest": _payload_digest(payload),
            "semantics": TH08_GLOBAL_POLICY_AUTHORITY_SEMANTICS_VERSION,
        },
    )


def th08_global_root_identity(
    *,
    source_frame: int,
    snapshot_frame: int,
    forecast_lead_frames: int,
    player_x: float,
    player_y: float,
    bullets: object,
    lasers: object,
    enemy_bodies: object,
    snapshot_lag: int,
    control_delay_candidates: tuple[int, ...],
    nominal_control_delay: int,
    active_action: str,
    required_gate_lane: str | None,
    context_key: tuple[int, int, int | None] | None,
    current_pool_callback_join_version: VersionIdentity | None = None,
) -> VersionIdentity:
    payload = {
        "schema": TH08_GLOBAL_AUTHORITY_ROOT_SCHEMA,
        "source_frame": source_frame,
        "snapshot_frame": snapshot_frame,
        "forecast_lead_frames": forecast_lead_frames,
        "player": (player_x, player_y),
        "bullets": bullets,
        "lasers": lasers,
        "enemy_bodies": enemy_bodies,
        "snapshot_lag": snapshot_lag,
        "control_delay_candidates": control_delay_candidates,
        "nominal_control_delay": nominal_control_delay,
        "active_action": active_action,
        "required_gate_lane": required_gate_lane,
        "context_key": context_key,
        "current_pool_callback_join_version": (
            current_pool_callback_join_version
        ),
    }
    return VersionIdentity.from_mapping(
        TH08_GLOBAL_AUTHORITY_ROOT_SCHEMA,
        {
            "context_epoch": (
                context_key[0] if context_key is not None else None
            ),
            "context_route": (
                context_key[1] if context_key is not None else None
            ),
            "context_spell": (
                context_key[2] if context_key is not None else None
            ),
            "digest": _payload_digest(payload),
            "snapshot_frame": snapshot_frame,
            "source_frame": source_frame,
            "current_pool_callback_join": (
                _payload_digest(current_pool_callback_join_version)
                if current_pool_callback_join_version is not None
                else None
            ),
        },
    )


def build_th08_global_authority_version(
    *,
    source_frame: int,
    snapshot_frame: int,
    forecast_lead_frames: int,
    player_x: float,
    player_y: float,
    bullets: object,
    lasers: object,
    enemy_bodies: object,
    snapshot_lag: int,
    control_delay_candidates: tuple[int, ...],
    nominal_control_delay: int,
    active_action: str,
    required_gate_lane: str | None,
    context_key: tuple[int, int, int | None] | None,
    runtime_ecl_version: RuntimeEclVersion | None,
    time_scale_schedule: Th08TimeScaleSchedule,
    future_hazard_projection: OrdinaryFutureHazardProjection | None,
    current_pool_callback_join_version: VersionIdentity | None = None,
    corridor_config: CorridorConfig,
) -> PolicyAuthorityVersion:
    return PolicyAuthorityVersion(
        root=th08_global_root_identity(
            source_frame=source_frame,
            snapshot_frame=snapshot_frame,
            forecast_lead_frames=forecast_lead_frames,
            player_x=player_x,
            player_y=player_y,
            bullets=bullets,
            lasers=lasers,
            enemy_bodies=enemy_bodies,
            snapshot_lag=snapshot_lag,
            control_delay_candidates=control_delay_candidates,
            nominal_control_delay=nominal_control_delay,
            active_action=active_action,
            required_gate_lane=required_gate_lane,
            context_key=context_key,
            current_pool_callback_join_version=(
                current_pool_callback_join_version
            ),
        ),
        runtime_content=(
            runtime_ecl_version_identity(runtime_ecl_version)
            if runtime_ecl_version is not None
            else None
        ),
        time_scale=time_scale_version_identity(
            time_scale_schedule.serialized_identity
        ),
        future_hazard=(
            future_hazard_projection.version
            if future_hazard_projection is not None
            else None
        ),
        geometry=th08_global_geometry_identity(),
        policy=th08_global_policy_identity(corridor_config),
    )


def time_scale_schedule_hard_authority(
    schedule: Th08TimeScaleSchedule,
) -> bool:
    return (
        schedule.coverage == SCALE_COVERAGE_COMPLETE
        and not schedule.provenance.startswith(
            "experimental_pretarget_unit_transport"
        )
        and not schedule.provenance.startswith(
            "diagnostic_constant_current_root_unknown_direction"
        )
    )


def _unit_schedule_covers(
    schedule: Th08TimeScaleSchedule,
    horizon: int,
) -> bool:
    if horizon < 0 or not time_scale_schedule_hard_authority(schedule):
        return False
    if schedule.root_scale_bits != TH08_UNIT_TIME_SCALE_BITS:
        return False
    if schedule.complete_horizon < horizon:
        return False
    return all(
        bits == TH08_UNIT_TIME_SCALE_BITS
        for bits in (
            *schedule.player_scale_bits[:horizon],
            *schedule.laser_scale_bits[:horizon],
        )
    )


def _serialized_schedule_provenance(
    identity: tuple[object, ...] | None,
) -> str | None:
    if identity is None or len(identity) != 7:
        return None
    provenance = identity[5]
    return provenance if isinstance(provenance, str) else None


@dataclass(frozen=True)
class GlobalActionAuthorityAssessment:
    allowed: bool
    reasons: tuple[str, ...]
    version: PolicyAuthorityVersion | None

    def record(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "version_complete": (
                self.version.complete if self.version is not None else False
            ),
            "version_digest": (
                self.version.digest if self.version is not None else None
            ),
        }


def assess_th08_global_action_authority(
    solution: _GlobalSolution | None,
    *,
    current_frame: int,
    context_key: tuple[int, int, int | None],
    runtime_ecl_version: RuntimeEclVersion | None,
    time_scale_schedule: Th08TimeScaleSchedule,
    corridor_config: CorridorConfig,
) -> GlobalActionAuthorityAssessment:
    """Require one exact root/content/scale/future/geometry/policy join."""

    if solution is None:
        return GlobalActionAuthorityAssessment(
            allowed=False,
            reasons=("solution_unavailable",),
            version=None,
        )
    version = solution.authority_version
    if version is None:
        return GlobalActionAuthorityAssessment(
            allowed=False,
            reasons=("authority_version_unavailable",),
            version=None,
        )

    reasons: list[str] = []
    if not version.complete:
        reasons.append("authority_version_incomplete")
    if solution.context_key != context_key:
        reasons.append("context_mismatch")
    if not (
        solution.source_frame
        <= current_frame
        < solution.source_frame + corridor_config.horizon_frames
    ):
        reasons.append("policy_frame_out_of_range")

    root_components = dict(version.root.components)
    expected_root_components = {
        "context_epoch": context_key[0],
        "context_route": context_key[1],
        "context_spell": context_key[2],
        "snapshot_frame": solution.snapshot_frame,
        "source_frame": solution.source_frame,
    }
    if any(
        root_components.get(name) != value
        for name, value in expected_root_components.items()
    ):
        reasons.append("root_version_mismatch")

    expected_geometry = th08_global_geometry_identity()
    if version.geometry != expected_geometry:
        reasons.append("geometry_version_mismatch")
    expected_policy = th08_global_policy_identity(corridor_config)
    if version.policy != expected_policy:
        reasons.append("policy_version_mismatch")

    if runtime_ecl_version is None:
        reasons.append("runtime_ecl_identity_unavailable")
    else:
        current_runtime_identity = runtime_ecl_version_identity(
            runtime_ecl_version
        )
        if version.runtime_content != current_runtime_identity:
            reasons.append("runtime_ecl_identity_mismatch")
        if (
            runtime_ecl_version.gameplay_epoch != context_key[0]
            or runtime_ecl_version.stage_route_index != context_key[1]
        ):
            reasons.append("runtime_ecl_context_mismatch")

    stored_scale_identity = solution.time_scale_identity
    if stored_scale_identity is None:
        reasons.append("policy_time_scale_identity_unavailable")
    else:
        if (
            version.time_scale
            != time_scale_version_identity(stored_scale_identity)
        ):
            reasons.append("policy_time_scale_version_mismatch")
        stored_provenance = _serialized_schedule_provenance(
            stored_scale_identity
        )
        if stored_provenance is None:
            reasons.append("policy_time_scale_identity_malformed")
        elif time_scale_schedule.provenance != stored_provenance:
            reasons.append("time_scale_provenance_mismatch")
    remaining_scale_horizon = max(
        1,
        solution.source_frame
        + corridor_config.horizon_frames
        - current_frame
        + 1,
    )
    if not _unit_schedule_covers(
        time_scale_schedule,
        remaining_scale_horizon,
    ):
        reasons.append("current_unit_scale_coverage_incomplete")

    projection = solution.future_hazard_projection
    coverage = solution.future_hazard_coverage
    callback_join = solution.current_pool_callback_join
    callback_join_version = solution.current_pool_callback_join_version
    if not isinstance(projection, OrdinaryFutureHazardProjection):
        reasons.append("future_hazard_projection_unavailable")
    else:
        if not projection.source_closure_complete:
            reasons.append("future_hazard_source_incomplete")
        if not projection.current_pool_callback_composition_complete:
            if not isinstance(
                callback_join,
                CurrentPoolProjectionCallbackJoinContract,
            ):
                reasons.append(
                    "future_hazard_current_pool_callback_join_unavailable"
                )
            else:
                if not callback_join.complete:
                    reasons.append(
                        "future_hazard_current_pool_callback_join_incomplete"
                    )
                if not callback_join.matches_projection(projection):
                    reasons.append(
                        "future_hazard_current_pool_callback_join_mismatch"
                    )
                if callback_join.policy_source_frame != solution.source_frame:
                    reasons.append(
                        "future_hazard_current_pool_callback_policy_root_mismatch"
                    )
                if (
                    callback_join.policy_horizon_frames
                    != corridor_config.horizon_frames
                ):
                    reasons.append(
                        "future_hazard_current_pool_callback_horizon_mismatch"
                    )
                if callback_join.time_scale_bits != TH08_UNIT_TIME_SCALE_BITS:
                    reasons.append(
                        "future_hazard_current_pool_callback_scale_mismatch"
                    )
                if callback_join_version != callback_join.version:
                    reasons.append(
                        "future_hazard_current_pool_callback_version_mismatch"
                    )
                stored_join_digest = root_components.get(
                    "current_pool_callback_join"
                )
                if stored_join_digest != _payload_digest(callback_join.version):
                    reasons.append(
                        "future_hazard_current_pool_callback_root_mismatch"
                    )
        if version.future_hazard != projection.version:
            reasons.append("future_hazard_authority_version_mismatch")
        if solution.future_hazard_version != projection.version:
            reasons.append("future_hazard_artifact_version_mismatch")
        if coverage != projection.coverage:
            reasons.append("future_hazard_coverage_mismatch")
    if coverage is None:
        reasons.append("future_hazard_coverage_unavailable")
    else:
        if not coverage.complete:
            reasons.append("future_hazard_coverage_incomplete")
        if coverage.root_frame > solution.source_frame:
            reasons.append("future_hazard_root_too_late")
        if (
            coverage.horizon_frame
            < solution.source_frame + corridor_config.horizon_frames
        ):
            reasons.append("future_hazard_horizon_incomplete")
        if not coverage.slabs:
            reasons.append("future_hazard_slabs_unavailable")
        elif any(
            slab.version != version.future_hazard
            for slab in coverage.slabs
        ):
            reasons.append("future_hazard_slab_version_mismatch")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return GlobalActionAuthorityAssessment(
        allowed=not unique_reasons,
        reasons=unique_reasons,
        version=version,
    )


__all__ = [
    "GlobalActionAuthorityAssessment",
    "RuntimeEclVersion",
    "TH08_GLOBAL_AUTHORITY_ROOT_SCHEMA",
    "TH08_GLOBAL_GEOMETRY_AUTHORITY_SEMANTICS_VERSION",
    "TH08_GLOBAL_POLICY_AUTHORITY_SEMANTICS_VERSION",
    "assess_th08_global_action_authority",
    "build_th08_global_authority_version",
    "runtime_ecl_version_identity",
    "th08_global_geometry_identity",
    "th08_global_policy_identity",
    "th08_global_root_identity",
    "time_scale_schedule_hard_authority",
    "time_scale_version_identity",
]
