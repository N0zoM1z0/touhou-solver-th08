"""TH08 laser trace records and local collision-frame projection.

This module is the boundary between decoded TH08 laser lifecycle state and the
numeric frames consumed by the local controller.  It deliberately contains no
process I/O or action selection so lifecycle parity can be tested separately
from the live agent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from th08_laser_model import LaserState, laser_collision_geometry_frames
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    validate_time_scale_bits,
)


PLAYER_RADIUS = 2.0


@dataclass(frozen=True)
class Laser:
    origin_x: float
    origin_y: float
    angle: float
    tail: float
    head: float
    half_width: float
    state: LaserState | None = None
    slot: int = -1
    collision_flag: int = 0
    uncertainty: float = 0.0
    # Exact native LaserState projection has no measured horizon drift.
    # Records without executable lifecycle state retain the conservative
    # fallback growth used by the local planner.
    uncertainty_per_frame: float = 0.08


def serialize_laser_trace(laser: Laser) -> list[float | int | None]:
    """Retain enough native lifecycle state for offline reprojection."""

    state = laser.state
    return [
        laser.origin_x,
        laser.origin_y,
        laser.angle,
        laser.tail,
        laser.head,
        laser.half_width,
        laser.slot,
        state.maximum_length if state is not None else None,
        state.width if state is not None else None,
        state.current_width if state is not None else None,
        state.speed if state is not None else None,
        int(state.phase) if state is not None else None,
        state.timer if state is not None else None,
        state.flags if state is not None else None,
        laser.collision_flag,
        state.warmup_frames if state is not None else None,
        state.collision_enable_frame if state is not None else None,
        state.active_frames if state is not None else None,
        state.fade_frames if state is not None else None,
        state.collision_disable_frame if state is not None else None,
        state.timer_fraction if state is not None else None,
        laser.uncertainty,
        laser.uncertainty_per_frame,
    ]


@dataclass(frozen=True)
class PackedLaserFrame:
    start_x: np.ndarray
    start_y: np.ndarray
    segment_x: np.ndarray
    segment_y: np.ndarray
    collision_radius: np.ndarray
    base_uncertainty: np.ndarray
    uncertainty_per_frame: np.ndarray
    # Shadow-only source-rectangle fields.  Legacy/native capsule consumers
    # continue to read only the seven arrays returned by fields_for_native().
    rectangle_half_width: np.ndarray | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    rectangle_cosine: np.ndarray | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    rectangle_sine: np.ndarray | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    native_float32_fields: tuple[np.ndarray, ...] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def fields_for_native(self) -> tuple[np.ndarray, ...]:
        if self.native_float32_fields is not None:
            return self.native_float32_fields
        return tuple(
            np.ascontiguousarray(values, dtype=np.float32)
            for values in (
                self.start_x,
                self.start_y,
                self.segment_x,
                self.segment_y,
                self.collision_radius,
                self.base_uncertainty,
                self.uncertainty_per_frame,
            )
        )


def build_laser_collision_frames(
    lasers: tuple[Laser, ...],
    *,
    horizon: int,
    snapshot_lag: int = 0,
    time_scale_bits: int = TH08_UNIT_TIME_SCALE_BITS,
    time_scale_schedule_bits: tuple[int, ...] = (),
) -> tuple[tuple[Laser, ...], ...]:
    """Project allocated records into the lethal segments for each update."""

    if horizon < 0 or snapshot_lag < 0:
        raise ValueError("laser projection horizon and lag cannot be negative")
    frames: list[list[Laser]] = [[] for _ in range(horizon)]
    total_frames = snapshot_lag + horizon
    validate_time_scale_bits(time_scale_bits)
    if time_scale_schedule_bits:
        if len(time_scale_schedule_bits) < total_frames:
            raise ValueError(
                "laser time-scale schedule does not cover projection horizon"
            )
        for bits in time_scale_schedule_bits[:total_frames]:
            validate_time_scale_bits(bits)
    for laser in lasers:
        state = laser.state
        if state is None:
            for projected in frames:
                projected.append(laser)
            continue
        geometry_frames = laser_collision_geometry_frames(
            state,
            frame_count=total_frames,
            time_scale_bits=time_scale_bits,
            time_scale_schedule_bits=time_scale_schedule_bits,
        )[snapshot_lag:]
        for projected, geometry in zip(frames, geometry_frames):
            projected.extend(
                Laser(
                    origin_x=state.origin_x,
                    origin_y=state.origin_y,
                    angle=state.angle,
                    tail=tail,
                    head=head,
                    half_width=half_width,
                    slot=laser.slot,
                    collision_flag=laser.collision_flag,
                    uncertainty=laser.uncertainty,
                    uncertainty_per_frame=laser.uncertainty_per_frame,
                )
                for tail, head, half_width in geometry
            )
    return tuple(tuple(frame) for frame in frames)


def pack_laser_frame(
    lasers: tuple[Laser, ...],
) -> PackedLaserFrame:
    angle = np.fromiter(
        (laser.angle for laser in lasers),
        dtype=np.float64,
        count=len(lasers),
    )
    tail = np.fromiter(
        (laser.tail for laser in lasers),
        dtype=np.float64,
        count=len(lasers),
    )
    head = np.fromiter(
        (laser.head for laser in lasers),
        dtype=np.float64,
        count=len(lasers),
    )
    cosine = np.cos(angle)
    sine = np.sin(angle)
    origin_x = np.fromiter(
        (laser.origin_x for laser in lasers),
        dtype=np.float64,
        count=len(lasers),
    )
    origin_y = np.fromiter(
        (laser.origin_y for laser in lasers),
        dtype=np.float64,
        count=len(lasers),
    )
    fields = (
        origin_x + cosine * tail,
        origin_y + sine * tail,
        cosine * (head - tail),
        sine * (head - tail),
        np.fromiter(
            (laser.half_width + PLAYER_RADIUS for laser in lasers),
            dtype=np.float64,
            count=len(lasers),
        ),
        np.fromiter(
            (laser.uncertainty for laser in lasers),
            dtype=np.float64,
            count=len(lasers),
        ),
        np.fromiter(
            (laser.uncertainty_per_frame for laser in lasers),
            dtype=np.float64,
            count=len(lasers),
        ),
    )
    return PackedLaserFrame(
        start_x=fields[0],
        start_y=fields[1],
        segment_x=fields[2],
        segment_y=fields[3],
        collision_radius=fields[4],
        base_uncertainty=fields[5],
        uncertainty_per_frame=fields[6],
        rectangle_half_width=np.fromiter(
            (laser.half_width for laser in lasers),
            dtype=np.float64,
            count=len(lasers),
        ),
        rectangle_cosine=cosine,
        rectangle_sine=sine,
        native_float32_fields=tuple(
            np.ascontiguousarray(values, dtype=np.float32)
            for values in fields
        ),
    )


def build_packed_laser_collision_frames(
    lasers: tuple[Laser, ...],
    *,
    horizon: int,
    snapshot_lag: int = 0,
    time_scale_bits: int = TH08_UNIT_TIME_SCALE_BITS,
    time_scale_schedule_bits: tuple[int, ...] = (),
) -> tuple[PackedLaserFrame, ...]:
    """Fuse lifecycle projection and numeric packing without Laser objects."""

    if horizon < 0 or snapshot_lag < 0:
        raise ValueError("laser projection horizon and lag cannot be negative")
    packed_values: list[list[float]] = [[] for _ in range(horizon)]
    total_frames = snapshot_lag + horizon
    validate_time_scale_bits(time_scale_bits)
    if time_scale_schedule_bits:
        if len(time_scale_schedule_bits) < total_frames:
            raise ValueError(
                "laser time-scale schedule does not cover projection horizon"
            )
        for bits in time_scale_schedule_bits[:total_frames]:
            validate_time_scale_bits(bits)
    for laser in lasers:
        state = laser.state
        cosine = math.cos(laser.angle)
        sine = math.sin(laser.angle)
        if state is None:
            segment_length = laser.head - laser.tail
            values = (
                laser.origin_x + cosine * laser.tail,
                laser.origin_y + sine * laser.tail,
                cosine * segment_length,
                sine * segment_length,
                laser.half_width + PLAYER_RADIUS,
                laser.uncertainty,
                laser.uncertainty_per_frame,
                laser.half_width,
                cosine,
                sine,
            )
            for frame_values in packed_values:
                frame_values.extend(values)
            continue
        geometry_frames = laser_collision_geometry_frames(
            state,
            frame_count=total_frames,
            time_scale_bits=time_scale_bits,
            time_scale_schedule_bits=time_scale_schedule_bits,
        )[snapshot_lag:]
        for frame_values, geometry in zip(
            packed_values,
            geometry_frames,
        ):
            for tail, head, half_width in geometry:
                segment_length = head - tail
                frame_values.extend(
                    (
                        state.origin_x + cosine * tail,
                        state.origin_y + sine * tail,
                        cosine * segment_length,
                        sine * segment_length,
                        half_width + PLAYER_RADIUS,
                        laser.uncertainty,
                        laser.uncertainty_per_frame,
                        half_width,
                        cosine,
                        sine,
                    )
                )
    frames: list[PackedLaserFrame] = []
    for values in packed_values:
        # One transposed copy makes every field contiguous. The local
        # collision kernel consumes fields repeatedly, so column views over
        # an interleaved matrix would merely defer the same copies.
        fields = (
            np.asarray(values, dtype=np.float64)
            .reshape((-1, 10))
            .transpose()
            .copy()
        )
        frames.append(
            PackedLaserFrame(
                start_x=fields[0],
                start_y=fields[1],
                segment_x=fields[2],
                segment_y=fields[3],
                collision_radius=fields[4],
                base_uncertainty=fields[5],
                uncertainty_per_frame=fields[6],
                rectangle_half_width=fields[7],
                rectangle_cosine=fields[8],
                rectangle_sine=fields[9],
                native_float32_fields=tuple(
                    np.ascontiguousarray(
                        values,
                        dtype=np.float32,
                    )
                    for values in fields[:7]
                ),
            )
        )
    return tuple(frames)
