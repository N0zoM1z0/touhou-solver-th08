"""Native geometry and signed-clearance bindings."""

from __future__ import annotations

import ctypes

import numpy as np

from ..packed_hazards import (
    PackedAnnularSectorFrames,
    PackedSegmentFrames,
)
from .arrays import (
    as_contiguous_array,
    attribute_array as _attribute_array,
    attribute_array64 as _attribute_array64,
)
from .library import (
    cache_function,
    cached_function,
    load_library as _load_library,
)


def _load_clearance_function():
    cached = cached_function("touhou_clearance_volume_v1")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    function = library.touhou_clearance_volume_v1
    float_pointer = ctypes.POINTER(ctypes.c_float)
    function.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        ctypes.c_int,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function("touhou_clearance_volume_v1", function)


def _load_trajectory_clearance_function():
    cached = cached_function("touhou_segment_trajectory_clearance_v1")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_segment_trajectory_clearance_v1
    except AttributeError:
        return None
    float_pointer = ctypes.POINTER(ctypes.c_float)
    function.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_int32),
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function(
        "touhou_segment_trajectory_clearance_v1",
        function,
    )


def _load_aabb_trajectory_clearance_function():
    cached = cached_function("touhou_aabb_trajectory_clearance_v1")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_aabb_trajectory_clearance_v1
    except AttributeError:
        return None
    float_pointer = ctypes.POINTER(ctypes.c_float)
    function.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_int32),
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function(
        "touhou_aabb_trajectory_clearance_v1",
        function,
    )


def _load_annular_sector_trajectory_clearance_function():
    cached = cached_function(
        "touhou_annular_sector_trajectory_clearance_v1"
    )
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_annular_sector_trajectory_clearance_v1
    except AttributeError:
        return None
    float_pointer = ctypes.POINTER(ctypes.c_float)
    double_pointer = ctypes.POINTER(ctypes.c_double)
    function.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_int32),
        *([double_pointer] * 10),
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function(
        "touhou_annular_sector_trajectory_clearance_v1",
        function,
    )


def _load_annular_sector_frame_clearance_function():
    cached = cached_function("touhou_annular_sector_frame_clearance_v1")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_annular_sector_frame_clearance_v1
    except AttributeError:
        return None
    float_pointer = ctypes.POINTER(ctypes.c_float)
    double_pointer = ctypes.POINTER(ctypes.c_double)
    function.argtypes = [
        float_pointer,
        float_pointer,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        *([double_pointer] * 10),
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function("touhou_annular_sector_frame_clearance_v1", function)


def _load_piecewise_aabb_clearance_function():
    cached = cached_function("touhou_piecewise_aabb_clearance_v1")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_piecewise_aabb_clearance_v1
    except AttributeError:
        return None
    float_pointer = ctypes.POINTER(ctypes.c_float)
    double_pointer = ctypes.POINTER(ctypes.c_double)
    function.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        double_pointer,
        double_pointer,
        double_pointer,
        double_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        float_pointer,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        double_pointer,
        double_pointer,
        ctypes.c_int,
        float_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function(
        "touhou_piecewise_aabb_clearance_v1",
        function,
    )


def build_clearance_volume(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    frame_count: int,
    player_radius: float,
    clearance_cap: float,
    aabbs: tuple[object, ...],
    segments: tuple[object, ...],
) -> np.ndarray | None:
    function = _load_clearance_function()
    if function is None:
        return None
    x_axis = as_contiguous_array(x_axis, dtype=np.float32)
    y_axis = as_contiguous_array(y_axis, dtype=np.float32)
    aabb_fields = tuple(
        _attribute_array(aabbs, name)
        for name in (
            "x",
            "y",
            "velocity_x",
            "velocity_y",
            "half_width",
            "half_height",
            "base_uncertainty",
            "uncertainty_per_frame",
        )
    )
    segment_fields = tuple(
        _attribute_array(segments, name)
        for name in (
            "origin_x",
            "origin_y",
            "angle",
            "tail",
            "head",
            "half_width",
            "base_uncertainty",
            "uncertainty_per_frame",
        )
    )
    output = np.empty(
        (frame_count, len(y_axis), len(x_axis)),
        dtype=np.float32,
    )
    float_pointer = ctypes.POINTER(ctypes.c_float)
    result = function(
        float(x_axis[0]),
        float(x_axis[1] - x_axis[0]),
        len(x_axis),
        float(y_axis[0]),
        float(y_axis[1] - y_axis[0]),
        len(y_axis),
        frame_count,
        player_radius,
        clearance_cap,
        *(
            values.ctypes.data_as(float_pointer)
            for values in aabb_fields
        ),
        len(aabbs),
        *(
            values.ctypes.data_as(float_pointer)
            for values in segment_fields
        ),
        len(segments),
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(f"native clearance kernel returned {result}")
    return output


def apply_segment_trajectory_clearance(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    player_radius: float,
    segment_trajectories: tuple[object, ...],
    clearance_volume: np.ndarray,
) -> np.ndarray | None:
    """Apply finite segment samples to an existing clearance volume."""

    if _load_trajectory_clearance_function() is None:
        return None
    packed = PackedSegmentFrames.from_trajectories(
        segment_trajectories,
        frame_count=clearance_volume.shape[0],
    )
    return apply_packed_segment_clearance(
        x_axis=x_axis,
        y_axis=y_axis,
        player_radius=player_radius,
        packed_segments=packed,
        clearance_volume=clearance_volume,
    )


def apply_packed_segment_clearance(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    player_radius: float,
    packed_segments: PackedSegmentFrames,
    clearance_volume: np.ndarray,
) -> np.ndarray | None:
    """Apply an already frame-major segment batch without object repacking."""

    function = _load_trajectory_clearance_function()
    if function is None:
        return None
    x_axis = as_contiguous_array(x_axis, dtype=np.float32)
    y_axis = as_contiguous_array(y_axis, dtype=np.float32)
    output = as_contiguous_array(clearance_volume, dtype=np.float32)
    frame_count = output.shape[0]
    if output.shape[1:] != (len(y_axis), len(x_axis)):
        raise ValueError("clearance volume does not match the supplied axes")
    if packed_segments.frame_count != frame_count:
        raise ValueError(
            "packed segment frame count does not match clearance volume"
        )
    segment_fields = (
        packed_segments.origin_x,
        packed_segments.origin_y,
        packed_segments.angle,
        packed_segments.tail,
        packed_segments.head,
        packed_segments.half_width,
        packed_segments.base_uncertainty,
        packed_segments.uncertainty_per_frame,
    )
    float_pointer = ctypes.POINTER(ctypes.c_float)
    result = function(
        float(x_axis[0]),
        float(x_axis[1] - x_axis[0]),
        len(x_axis),
        float(y_axis[0]),
        float(y_axis[1] - y_axis[0]),
        len(y_axis),
        frame_count,
        player_radius,
        packed_segments.frame_offsets.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32)
        ),
        *(
            values.ctypes.data_as(float_pointer)
            for values in segment_fields
        ),
        packed_segments.sample_count,
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(
            f"native segment trajectory clearance kernel returned {result}"
        )
    return output


def apply_annular_sector_trajectory_clearance(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    player_radius: float,
    annular_sector_trajectories: tuple[object, ...],
    clearance_volume: np.ndarray,
) -> np.ndarray | None:
    """Apply continuous set-valued future centers with the native kernel."""

    function = _load_annular_sector_trajectory_clearance_function()
    if function is None:
        return None
    x_axis = as_contiguous_array(x_axis, dtype=np.float32)
    y_axis = as_contiguous_array(y_axis, dtype=np.float32)
    output = as_contiguous_array(clearance_volume, dtype=np.float32)
    if output.shape[1:] != (len(y_axis), len(x_axis)):
        raise ValueError("clearance volume does not match the supplied axes")
    packed = PackedAnnularSectorFrames.from_trajectories(
        annular_sector_trajectories,
        frame_count=output.shape[0],
    )
    fields = tuple(
        getattr(packed, name)
        for name in (
            "origin_x",
            "origin_y",
            "minimum_angle",
            "maximum_angle",
            "minimum_radius",
            "maximum_radius",
            "half_extent_radius",
            "origin_uncertainty",
            "base_uncertainty",
            "uncertainty_per_frame",
        )
    )
    double_pointer = ctypes.POINTER(ctypes.c_double)
    float_pointer = ctypes.POINTER(ctypes.c_float)
    result = function(
        float(x_axis[0]),
        float(x_axis[1] - x_axis[0]),
        len(x_axis),
        float(y_axis[0]),
        float(y_axis[1] - y_axis[0]),
        len(y_axis),
        output.shape[0],
        player_radius,
        packed.frame_offsets.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32)
        ),
        *(
            values.ctypes.data_as(double_pointer)
            for values in fields
        ),
        packed.sample_count,
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(
            f"native annular-sector clearance kernel returned {result}"
        )
    return output


def query_packed_annular_sector_clearance(
    *,
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    player_radius: float,
    packed_sectors: PackedAnnularSectorFrames,
    frame: int,
) -> np.ndarray | None:
    """Query one packed sector frame at arbitrary branch positions."""

    function = _load_annular_sector_frame_clearance_function()
    if function is None:
        return None
    positions_x = as_contiguous_array(positions_x, dtype=np.float32)
    positions_y = as_contiguous_array(positions_y, dtype=np.float32)
    if (
        positions_x.ndim != 1
        or positions_y.shape != positions_x.shape
        or not len(positions_x)
    ):
        raise ValueError("sector query positions must be nonempty 1D peers")
    frame_slice = packed_sectors.frame_slice(frame)
    if frame_slice.start == frame_slice.stop:
        return np.full(positions_x.shape, np.inf, dtype=np.float32)
    fields = tuple(
        getattr(packed_sectors, name)[frame_slice]
        for name in (
            "origin_x",
            "origin_y",
            "minimum_angle",
            "maximum_angle",
            "minimum_radius",
            "maximum_radius",
            "half_extent_radius",
            "origin_uncertainty",
            "base_uncertainty",
            "uncertainty_per_frame",
        )
    )
    output = np.empty(len(positions_x), dtype=np.float32)
    float_pointer = ctypes.POINTER(ctypes.c_float)
    double_pointer = ctypes.POINTER(ctypes.c_double)
    result = function(
        positions_x.ctypes.data_as(float_pointer),
        positions_y.ctypes.data_as(float_pointer),
        len(positions_x),
        frame,
        player_radius,
        *(values.ctypes.data_as(double_pointer) for values in fields),
        frame_slice.stop - frame_slice.start,
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(
            f"native annular-sector frame kernel returned {result}"
        )
    return output


def apply_aabb_trajectory_clearance(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    player_radius: float,
    aabb_trajectories: tuple[object, ...],
    clearance_volume: np.ndarray,
) -> np.ndarray | None:
    """Apply finite AABB samples to an existing clearance volume."""

    function = _load_aabb_trajectory_clearance_function()
    if function is None:
        return None
    x_axis = as_contiguous_array(x_axis, dtype=np.float32)
    y_axis = as_contiguous_array(y_axis, dtype=np.float32)
    output = as_contiguous_array(clearance_volume, dtype=np.float32)
    frame_count = output.shape[0]
    if output.shape[1:] != (len(y_axis), len(x_axis)):
        raise ValueError("clearance volume does not match the supplied axes")

    frame_offsets = np.empty(frame_count + 1, dtype=np.int32)
    samples: list[object] = []
    for frame in range(frame_count):
        frame_offsets[frame] = len(samples)
        samples.extend(
            sample
            for trajectory in aabb_trajectories
            if (sample := trajectory.sample(frame)) is not None
        )
    frame_offsets[frame_count] = len(samples)
    packed_samples = tuple(samples)
    aabb_fields = tuple(
        _attribute_array(packed_samples, name)
        for name in (
            "x",
            "y",
            "half_width",
            "half_height",
            "base_uncertainty",
            "uncertainty_per_frame",
        )
    )
    float_pointer = ctypes.POINTER(ctypes.c_float)
    result = function(
        float(x_axis[0]),
        float(x_axis[1] - x_axis[0]),
        len(x_axis),
        float(y_axis[0]),
        float(y_axis[1] - y_axis[0]),
        len(y_axis),
        frame_count,
        player_radius,
        frame_offsets.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        *(
            values.ctypes.data_as(float_pointer)
            for values in aabb_fields
        ),
        len(packed_samples),
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(
            f"native AABB trajectory clearance kernel returned {result}"
        )
    return output


def apply_piecewise_aabb_clearance(
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    player_radius: float,
    piecewise_aabbs: tuple[object, ...],
    clearance_volume: np.ndarray,
) -> np.ndarray | None:
    """Project sparse velocity events and apply their AABBs natively."""

    # ABI v1 has no collision-state event channel. Falling back preserves
    # exact omission/re-enable semantics instead of treating callback-hidden
    # bullets as continuously lethal.
    if any(
        not hazard.collision_enabled or hazard.collision_state_changes
        for hazard in piecewise_aabbs
    ):
        return None

    function = _load_piecewise_aabb_clearance_function()
    if function is None:
        return None
    x_axis = as_contiguous_array(x_axis, dtype=np.float32)
    y_axis = as_contiguous_array(y_axis, dtype=np.float32)
    output = as_contiguous_array(clearance_volume, dtype=np.float32)
    if output.shape[1:] != (len(y_axis), len(x_axis)):
        raise ValueError("clearance volume does not match the supplied axes")

    motions = tuple(hazard.motion for hazard in piecewise_aabbs)
    hazard_fields = (
        _attribute_array64(motions, "x"),
        _attribute_array64(motions, "y"),
        _attribute_array64(motions, "velocity_x"),
        _attribute_array64(motions, "velocity_y"),
        *(
            _attribute_array(piecewise_aabbs, name)
            for name in (
                "half_width",
                "half_height",
                "base_uncertainty",
                "uncertainty_per_frame",
            )
        ),
    )
    event_offsets = np.empty(len(motions) + 1, dtype=np.int32)
    event_offsets[0] = 0
    event_frames: list[int] = []
    event_velocity_x: list[float] = []
    event_velocity_y: list[float] = []
    for index, motion in enumerate(motions):
        for change in motion.changes:
            event_frames.append(change.frame)
            event_velocity_x.append(change.velocity_x)
            event_velocity_y.append(change.velocity_y)
        event_offsets[index + 1] = len(event_frames)
    packed_event_frames = np.asarray(event_frames, dtype=np.int32)
    packed_event_velocity_x = np.asarray(event_velocity_x, dtype=np.float64)
    packed_event_velocity_y = np.asarray(event_velocity_y, dtype=np.float64)

    float_pointer = ctypes.POINTER(ctypes.c_float)
    double_pointer = ctypes.POINTER(ctypes.c_double)
    result = function(
        float(x_axis[0]),
        float(x_axis[1] - x_axis[0]),
        len(x_axis),
        float(y_axis[0]),
        float(y_axis[1] - y_axis[0]),
        len(y_axis),
        output.shape[0],
        player_radius,
        *(
            values.ctypes.data_as(double_pointer)
            for values in hazard_fields[:4]
        ),
        *(
            values.ctypes.data_as(float_pointer)
            for values in hazard_fields[4:]
        ),
        len(motions),
        event_offsets.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        packed_event_frames.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32)
        ),
        packed_event_velocity_x.ctypes.data_as(double_pointer),
        packed_event_velocity_y.ctypes.data_as(double_pointer),
        len(event_frames),
        output.ctypes.data_as(float_pointer),
    )
    if result != 0:
        raise RuntimeError(
            f"native piecewise AABB clearance kernel returned {result}"
        )
    return output
