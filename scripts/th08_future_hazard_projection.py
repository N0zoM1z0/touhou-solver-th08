"""Versioned ordinary-stage future-hazard publication for TH08 policies."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from th08_future_birth_envelope import (
    AUTOMATIC_PLAYER_AIM_MODES,
    FUTURE_BIRTH_SECTOR_SEMANTICS_VERSION,
    FloatInterval,
    FutureDirectFire,
    lower_complete_future_birth_sectors,
)
from touhou_control.corridor import (
    AabbHazard,
    AabbTrajectoryHazard,
    AnnularSectorTrajectoryHazard,
)
from touhou_control.packed_hazards import PackedAnnularSectorFrames
from touhou_control.hazard_coverage import (
    HazardCoverageAssessment,
    HazardCoverageClass,
    HazardCoverageSlab,
    assess_hazard_coverage,
)
from touhou_control.pipeline_identity import VersionIdentity


ORDINARY_FUTURE_HAZARD_PROJECTION_SCHEMA = (
    "th08-ordinary-future-hazard-projection-v5-source-auto-aim"
)

_TWO_PI = 2.0 * math.pi
_CAUSAL_POSITION_NUMERIC_GUARD = 2.0e-5


def _trajectory_record(
    trajectory: AnnularSectorTrajectoryHazard,
) -> dict[str, object]:
    return {
        "origin": [trajectory.origin_x, trajectory.origin_y],
        "angle": [trajectory.minimum_angle, trajectory.maximum_angle],
        "minimum_radii": trajectory.minimum_radii,
        "maximum_radii": trajectory.maximum_radii,
        "half_extent_radius": trajectory.half_extent_radius,
        "origin_uncertainty": trajectory.origin_uncertainty,
        "base_uncertainty": trajectory.base_uncertainty,
        "uncertainty_per_frame": trajectory.uncertainty_per_frame,
    }


def _aabb_trajectory_record(
    trajectory: AabbTrajectoryHazard,
) -> list[dict[str, float] | None]:
    return [
        (
            None
            if sample is None
            else {
                "x": sample.x,
                "y": sample.y,
                "half_width": sample.half_width,
                "half_height": sample.half_height,
                "base_uncertainty": sample.base_uncertainty,
                "uncertainty_per_frame": sample.uncertainty_per_frame,
            }
        )
        for sample in trajectory.samples
    ]


def _interval_record(interval: FloatInterval) -> list[float]:
    return [float(interval.lower), float(interval.upper)]


def _causal_event_record(event: FutureDirectFire) -> dict[str, object]:
    return {
        "source": event.source,
        "activation_frames": event.activation_frames,
        "origin_x": _interval_record(event.origin_x),
        "origin_y": _interval_record(event.origin_y),
        "mode": event.mode,
        "count1": event.count1,
        "count2": event.count2,
        "speed1": _interval_record(event.speed1),
        "speed2": _interval_record(event.speed2),
        "angle1": _interval_record(event.angle1),
        "angle2": _interval_record(event.angle2),
        "aim_angle": _interval_record(event.aim_angle),
        "half_width": event.half_width,
        "half_height": event.half_height,
        "original_flags": event.original_flags,
        "transform_program_zero": event.transform_program_zero,
        "transform_program_size": len(event.transform_program),
        "transform_program_sha256": hashlib.sha256(
            event.transform_program
        ).hexdigest(),
        "angle1_player_aim_coefficient": (
            event.angle1_player_aim_coefficient
        ),
        "angle1_player_aim_residual": (
            None
            if event.angle1_player_aim_residual is None
            else _interval_record(event.angle1_player_aim_residual)
        ),
        "angle2_player_aim_coefficient": (
            event.angle2_player_aim_coefficient
        ),
        "angle2_player_aim_residual": (
            None
            if event.angle2_player_aim_residual is None
            else _interval_record(event.angle2_player_aim_residual)
        ),
    }


@dataclass(frozen=True)
class OrdinaryFutureHazardProjection:
    """Complete or fail-closed future hostility rooted at one observation."""

    root_frame: int
    horizon_frames: int
    trajectories: tuple[AnnularSectorTrajectoryHazard, ...]
    aabb_trajectories: tuple[AabbTrajectoryHazard, ...]
    direct_fire_events: tuple[FutureDirectFire, ...]
    source_closure_complete: bool
    source_closure_reason: str | None
    source_semantics_version: str
    producer_count: int
    digest: str
    version: VersionIdentity
    coverage: HazardCoverageAssessment
    _packed_annular_sector_frames: PackedAnnularSectorFrames = field(
        init=False,
        repr=False,
        compare=False,
    )
    _aabb_samples_by_frame: tuple[tuple[AabbHazard, ...], ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.root_frame < 0 or self.horizon_frames < 0:
            raise ValueError("future-hazard projection horizon is invalid")
        if not self.source_semantics_version:
            raise ValueError("source semantics version must not be empty")
        if self.producer_count < 0:
            raise ValueError("producer count cannot be negative")
        if len(self.digest) != 64:
            raise ValueError("future-hazard digest must be SHA-256")
        if self.coverage.root_frame != self.root_frame:
            raise ValueError("future-hazard coverage root disagrees")
        if (
            self.coverage.horizon_frame
            != self.root_frame + self.horizon_frames
        ):
            raise ValueError("future-hazard coverage horizon disagrees")
        if self.source_closure_complete != self.coverage.complete:
            raise ValueError("source closure and coverage completeness disagree")
        if self.source_closure_complete and self.source_closure_reason is not None:
            raise ValueError("complete source closure cannot carry a reason")
        if (
            not self.source_closure_complete
            and not self.source_closure_reason
        ):
            raise ValueError("incomplete source closure requires a reason")
        frame_count = self.horizon_frames + 1
        object.__setattr__(
            self,
            "_packed_annular_sector_frames",
            PackedAnnularSectorFrames.from_trajectories(
                self.trajectories,
                frame_count=frame_count,
            ),
        )
        object.__setattr__(
            self,
            "_aabb_samples_by_frame",
            tuple(
                tuple(
                    sample
                    for trajectory in self.aabb_trajectories
                    if (sample := trajectory.sample(frame)) is not None
                )
                for frame in range(frame_count)
            ),
        )

    @property
    def horizon_frame(self) -> int:
        return self.root_frame + self.horizon_frames

    @property
    def packed_annular_sector_frames(self) -> PackedAnnularSectorFrames:
        return self._packed_annular_sector_frames

    def aabb_samples(self, frame: int) -> tuple[AabbHazard, ...]:
        if frame < 0 or frame >= len(self._aabb_samples_by_frame):
            return ()
        return self._aabb_samples_by_frame[frame]

    def trajectories_for_policy(
        self,
        *,
        source_frame: int,
        horizon_frames: int,
    ) -> tuple[AnnularSectorTrajectoryHazard, ...]:
        """Rebase root-relative envelopes onto one future policy epoch."""

        if source_frame < self.root_frame:
            raise ValueError("policy source predates future-hazard root")
        if horizon_frames < 0:
            raise ValueError("policy hazard horizon cannot be negative")
        if source_frame + horizon_frames > self.horizon_frame:
            raise ValueError(
                "future-hazard projection does not cover policy horizon"
            )
        offset = source_frame - self.root_frame
        return tuple(
            trajectory.rebase(
                offset=offset,
                horizon_frames=horizon_frames,
            )
            for trajectory in self.trajectories
        )

    def aabb_trajectories_for_policy(
        self,
        *,
        source_frame: int,
        horizon_frames: int,
    ) -> tuple[AabbTrajectoryHazard, ...]:
        if source_frame < self.root_frame:
            raise ValueError("policy source predates future-hazard root")
        if horizon_frames < 0:
            raise ValueError("policy hazard horizon cannot be negative")
        if source_frame + horizon_frames > self.horizon_frame:
            raise ValueError(
                "future-hazard projection does not cover policy horizon"
            )
        offset = source_frame - self.root_frame
        return tuple(
            trajectory.rebase(
                offset=offset,
                horizon_frames=horizon_frames,
            )
            for trajectory in self.aabb_trajectories
        )

    def record(self) -> dict[str, object]:
        return {
            "schema": ORDINARY_FUTURE_HAZARD_PROJECTION_SCHEMA,
            "root_frame": self.root_frame,
            "horizon_frames": self.horizon_frames,
            "source_closure_complete": self.source_closure_complete,
            "source_closure_reason": self.source_closure_reason,
            "source_semantics_version": self.source_semantics_version,
            "producer_count": self.producer_count,
            "trajectory_count": len(self.trajectories),
            "aabb_trajectory_count": len(self.aabb_trajectories),
            "direct_fire_event_count": len(self.direct_fire_events),
            "causal_player_aim_event_count": sum(
                event.angle1_player_aim_coefficient is not None
                and event.angle2_player_aim_coefficient is not None
                for event in self.direct_fire_events
            ),
            "digest": self.digest,
            "version": self.version.record(),
            "coverage": self.coverage.record(),
        }


def _build_projection(
    *,
    root_frame: int,
    horizon_frames: int,
    trajectories: tuple[AnnularSectorTrajectoryHazard, ...],
    aabb_trajectories: tuple[AabbTrajectoryHazard, ...],
    direct_fire_events: tuple[FutureDirectFire, ...],
    source_closure_complete: bool,
    source_closure_reason: str | None,
    source_semantics_version: str,
    producer_count: int,
) -> OrdinaryFutureHazardProjection:
    identity_payload = {
        "schema": ORDINARY_FUTURE_HAZARD_PROJECTION_SCHEMA,
        "root_frame": root_frame,
        "horizon_frames": horizon_frames,
        "source_closure_complete": source_closure_complete,
        "source_closure_reason": source_closure_reason,
        "source_semantics_version": source_semantics_version,
        "birth_semantics_version": (
            FUTURE_BIRTH_SECTOR_SEMANTICS_VERSION
        ),
        "producer_count": producer_count,
        "trajectories": [
            _trajectory_record(trajectory)
            for trajectory in trajectories
        ],
        "aabb_trajectories": [
            _aabb_trajectory_record(trajectory)
            for trajectory in aabb_trajectories
        ],
        "direct_fire_events": [
            _causal_event_record(event) for event in direct_fire_events
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    version = VersionIdentity.from_mapping(
        "th08-ordinary-future-hazard-projection-v5",
        {
            "root_frame": root_frame,
            "horizon_frames": horizon_frames,
            "digest": digest,
            "source_semantics_version": source_semantics_version,
        },
    )
    if horizon_frames == 0:
        slabs: tuple[HazardCoverageSlab, ...] = ()
    else:
        slabs = (
            HazardCoverageSlab(
                start_frame=root_frame + 1,
                end_frame=root_frame + horizon_frames,
                coverage_class=(
                    HazardCoverageClass.BOUNDED_ENVELOPE
                    if source_closure_complete
                    else HazardCoverageClass.UNKNOWN
                ),
                source="th08_ordinary_future_sources",
                version=version,
                rationale=(
                    "all reachable ordinary ECL/timeline producers were "
                    "lowered into consumed continuous annular-sector and "
                    "future hostile-body AABB envelopes"
                    if source_closure_complete
                    else str(source_closure_reason)
                ),
            ),
        )
    coverage = assess_hazard_coverage(
        root_frame=root_frame,
        horizon_frame=root_frame + horizon_frames,
        slabs=slabs,
    )
    return OrdinaryFutureHazardProjection(
        root_frame=root_frame,
        horizon_frames=horizon_frames,
        trajectories=trajectories,
        aabb_trajectories=aabb_trajectories,
        direct_fire_events=direct_fire_events,
        source_closure_complete=source_closure_complete,
        source_closure_reason=source_closure_reason,
        source_semantics_version=source_semantics_version,
        producer_count=producer_count,
        digest=digest,
        version=version,
        coverage=coverage,
    )


def complete_future_hazard_projection(
    *,
    root_frame: int,
    horizon_frames: int,
    events: tuple[FutureDirectFire, ...],
    aabb_trajectories: tuple[AabbTrajectoryHazard, ...] = (),
    source_semantics_version: str,
) -> OrdinaryFutureHazardProjection:
    envelopes = lower_complete_future_birth_sectors(
        events,
        horizon_frames=horizon_frames,
    )
    return _build_projection(
        root_frame=root_frame,
        horizon_frames=horizon_frames,
        trajectories=tuple(
            envelope.trajectory for envelope in envelopes
        ),
        aabb_trajectories=aabb_trajectories,
        direct_fire_events=events,
        source_closure_complete=True,
        source_closure_reason=None,
        source_semantics_version=source_semantics_version,
        producer_count=len(events) + len(aabb_trajectories),
    )


def unknown_future_hazard_projection(
    *,
    root_frame: int,
    horizon_frames: int,
    reason: str,
    source_semantics_version: str,
) -> OrdinaryFutureHazardProjection:
    if not reason:
        raise ValueError("unknown future-hazard projection requires a reason")
    return _build_projection(
        root_frame=root_frame,
        horizon_frames=horizon_frames,
        trajectories=(),
        aabb_trajectories=(),
        direct_fire_events=(),
        source_closure_complete=False,
        source_closure_reason=reason,
        source_semantics_version=source_semantics_version,
        producer_count=0,
    )


def _causal_aim_interval(
    *,
    player_positions: tuple[tuple[float, float], ...],
    origin_x: FloatInterval,
    origin_y: FloatInterval,
) -> FloatInterval:
    """Bound atan2(player-origin) by the shortest containing circular arc."""

    if not player_positions:
        raise ValueError("causal player path has no position at an emission")
    if any(
        not math.isfinite(x) or not math.isfinite(y)
        for x, y in player_positions
    ):
        raise ValueError("causal player path contains a nonfinite position")
    player_x_low = min(x for x, _ in player_positions)
    player_x_high = max(x for x, _ in player_positions)
    player_y_low = min(y for _, y in player_positions)
    player_y_high = max(y for _, y in player_positions)
    dx_low = (
        player_x_low
        - float(origin_x.upper)
        - _CAUSAL_POSITION_NUMERIC_GUARD
    )
    dx_high = (
        player_x_high
        - float(origin_x.lower)
        + _CAUSAL_POSITION_NUMERIC_GUARD
    )
    dy_low = (
        player_y_low
        - float(origin_y.upper)
        - _CAUSAL_POSITION_NUMERIC_GUARD
    )
    dy_high = (
        player_y_high
        - float(origin_y.lower)
        + _CAUSAL_POSITION_NUMERIC_GUARD
    )
    if dx_low <= 0.0 <= dx_high and dy_low <= 0.0 <= dy_high:
        return FloatInterval(-math.pi, math.pi)
    angles = sorted(
        math.atan2(y, x) % _TWO_PI
        for x in (dx_low, dx_high)
        for y in (dy_low, dy_high)
    )
    gaps = [
        angles[index + 1] - angles[index]
        for index in range(len(angles) - 1)
    ]
    gaps.append(angles[0] + _TWO_PI - angles[-1])
    largest_gap_index = max(range(len(gaps)), key=gaps.__getitem__)
    start = angles[(largest_gap_index + 1) % len(angles)]
    end = angles[largest_gap_index]
    if end < start:
        end += _TWO_PI
    return FloatInterval(start, end)


def condition_future_hazard_projection_on_player_paths(
    projection: OrdinaryFutureHazardProjection,
    *,
    source_frame: int,
    horizon_frames: int,
    player_positions_by_step: tuple[
        tuple[tuple[float, float], ...], ...
    ],
) -> OrdinaryFutureHazardProjection:
    """Build a hard future slab for one selected action's hidden paths.

    Births at or before ``source_frame`` are already exhaustively represented
    by the current native bullet-pool snapshot. Future ECL births retain all
    RNG/source uncertainty, but replace the noncausal global player-reachable
    rectangle by the selected action's exact pickup/pending path set.
    """

    if not projection.source_closure_complete or not projection.coverage.complete:
        raise ValueError("causal conditioning requires complete source coverage")
    if source_frame < projection.root_frame or horizon_frames <= 0:
        raise ValueError("causal conditioning interval is invalid")
    source_offset = source_frame - projection.root_frame
    if source_offset + horizon_frames > projection.horizon_frames:
        raise ValueError("causal conditioning exceeds projection coverage")
    if len(player_positions_by_step) < horizon_frames + 1:
        raise ValueError("causal player paths do not cover the horizon")

    conditioned_events: list[FutureDirectFire] = []
    for event in projection.direct_fire_events:
        if (
            event.angle1_player_aim_coefficient is None
            or event.angle1_player_aim_residual is None
            or event.angle2_player_aim_coefficient is None
            or event.angle2_player_aim_residual is None
        ):
            raise ValueError(
                f"{event.source} lacks complete causal player-aim metadata"
            )
        for activation in event.activation_frames:
            relative_activation = activation - source_offset
            if relative_activation <= 0 or relative_activation > horizon_frames:
                continue
            causal_aim = _causal_aim_interval(
                player_positions=player_positions_by_step[
                    relative_activation
                ],
                origin_x=event.origin_x,
                origin_y=event.origin_y,
            )
            conditioned_events.append(
                FutureDirectFire(
                    source=f"{event.source}:causal@{activation}",
                    activation_frames=(relative_activation,),
                    origin_x=event.origin_x,
                    origin_y=event.origin_y,
                    mode=event.mode,
                    count1=event.count1,
                    count2=event.count2,
                    speed1=event.speed1,
                    speed2=event.speed2,
                    angle1=event.angle1_player_aim_residual.add(
                        causal_aim.scale(
                            event.angle1_player_aim_coefficient
                        )
                    ),
                    angle2=event.angle2_player_aim_residual.add(
                        causal_aim.scale(
                            event.angle2_player_aim_coefficient
                        )
                    ),
                    # Modes 0/2/4 add angleToPlayer inside the native spawn
                    # helper, independently of any ECL operand that already
                    # reads the same player-aim variable.
                    aim_angle=(
                        causal_aim
                        if event.mode in AUTOMATIC_PLAYER_AIM_MODES
                        else event.aim_angle
                    ),
                    half_width=event.half_width,
                    half_height=event.half_height,
                    original_flags=event.original_flags,
                    transform_program_zero=event.transform_program_zero,
                    transform_program=event.transform_program,
                    angle1_player_aim_coefficient=(
                        event.angle1_player_aim_coefficient
                    ),
                    angle1_player_aim_residual=(
                        event.angle1_player_aim_residual
                    ),
                    angle2_player_aim_coefficient=(
                        event.angle2_player_aim_coefficient
                    ),
                    angle2_player_aim_residual=(
                        event.angle2_player_aim_residual
                    ),
                )
            )

    return complete_future_hazard_projection(
        root_frame=source_frame,
        horizon_frames=horizon_frames,
        events=tuple(conditioned_events),
        aabb_trajectories=projection.aabb_trajectories_for_policy(
            source_frame=source_frame,
            horizon_frames=horizon_frames,
        ),
        source_semantics_version=(
            f"{projection.source_semantics_version}+causal-player-path-v1"
        ),
    )


__all__ = [
    "ORDINARY_FUTURE_HAZARD_PROJECTION_SCHEMA",
    "OrdinaryFutureHazardProjection",
    "condition_future_hazard_projection_on_player_paths",
    "complete_future_hazard_projection",
    "unknown_future_hazard_projection",
]
