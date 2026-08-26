"""Native baseline local beam reducer."""

from __future__ import annotations

import ctypes

import numpy as np

from .arrays import as_contiguous_array
from .library import (
    cache_function,
    cached_function,
    load_library as _load_library,
)


def _load_local_beam_reduce_function():
    cached = cached_function("touhou_local_beam_reduce_v2")
    if cached is not None:
        return cached
    library = _load_library()
    if library is None:
        return None
    try:
        function = library.touhou_local_beam_reduce_v2
    except AttributeError:
        return None
    double_pointer = ctypes.POINTER(ctypes.c_double)
    int32_pointer = ctypes.POINTER(ctypes.c_int32)
    uint8_pointer = ctypes.POINTER(ctypes.c_uint8)
    function.argtypes = [
        double_pointer,
        double_pointer,
        int32_pointer,
        int32_pointer,
        uint8_pointer,
        ctypes.POINTER(ctypes.c_uint32),
        double_pointer,
        int32_pointer,
        double_pointer,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        int32_pointer,
        double_pointer,
        uint8_pointer,
        uint8_pointer,
        double_pointer,
        ctypes.c_int,
        ctypes.c_int,
        int32_pointer,
        int32_pointer,
    ]
    function.restype = ctypes.c_int
    return cache_function("touhou_local_beam_reduce_v2", function)



def reduce_local_beam(
    *,
    draft_x: np.ndarray,
    draft_y: np.ndarray,
    first_action: np.ndarray,
    last_direction: np.ndarray,
    last_focused: np.ndarray,
    collected_mask: np.ndarray,
    risk: np.ndarray,
    collisions: np.ndarray,
    minimum_clearance: np.ndarray,
    step: int,
    beam_width: int,
    position_quantization: float,
    target_x: float | None,
    target_y: float | None,
    target_deadline: int | None,
    item_safety_clearance: float,
    playfield_left: float,
    playfield_right: float,
    playfield_top: float,
    playfield_bottom: float,
    reserve_distance: float,
    diagonal_speed: float,
    cardinal_speed: float,
    certificate_collisions: np.ndarray,
    certificate_minimum: np.ndarray,
    survival_preferred: np.ndarray,
    safety_preferred: np.ndarray,
    recovery_distance: np.ndarray,
    preserve_first_action_strata: bool,
) -> np.ndarray | None:
    """Return exact retained draft indices for the quantized beam reducer."""

    function = _load_local_beam_reduce_function()
    if function is None:
        return None
    draft_fields = (
        as_contiguous_array(draft_x, dtype=np.float64),
        as_contiguous_array(draft_y, dtype=np.float64),
        as_contiguous_array(first_action, dtype=np.int32),
        as_contiguous_array(last_direction, dtype=np.int32),
        as_contiguous_array(last_focused, dtype=np.uint8),
        as_contiguous_array(collected_mask, dtype=np.uint32),
        as_contiguous_array(risk, dtype=np.float64),
        as_contiguous_array(collisions, dtype=np.int32),
        as_contiguous_array(minimum_clearance, dtype=np.float64),
    )
    draft_count = len(draft_fields[0])
    if (
        draft_count <= 0
        or any(values.ndim != 1 or len(values) != draft_count for values in draft_fields)
    ):
        raise ValueError("local beam draft fields must be nonempty 1D peers")
    action_fields = (
        as_contiguous_array(certificate_collisions, dtype=np.int32),
        as_contiguous_array(certificate_minimum, dtype=np.float64),
        as_contiguous_array(survival_preferred, dtype=np.uint8),
        as_contiguous_array(safety_preferred, dtype=np.uint8),
        as_contiguous_array(recovery_distance, dtype=np.float64),
    )
    action_count = len(action_fields[0])
    if (
        action_count <= 0
        or any(values.ndim != 1 or len(values) != action_count for values in action_fields)
    ):
        raise ValueError("local beam action fields must be nonempty 1D peers")
    if step <= 0 or beam_width <= 0:
        raise ValueError("local beam step and width must be positive")
    target_enabled = target_x is not None
    if target_enabled != (target_y is not None and target_deadline is not None):
        raise ValueError("local beam target fields must be all present or absent")

    retained = np.empty(min(beam_width, draft_count), dtype=np.int32)
    retained_count = ctypes.c_int32()
    double_pointer = ctypes.POINTER(ctypes.c_double)
    int32_pointer = ctypes.POINTER(ctypes.c_int32)
    uint8_pointer = ctypes.POINTER(ctypes.c_uint8)
    result = function(
        draft_fields[0].ctypes.data_as(double_pointer),
        draft_fields[1].ctypes.data_as(double_pointer),
        draft_fields[2].ctypes.data_as(int32_pointer),
        draft_fields[3].ctypes.data_as(int32_pointer),
        draft_fields[4].ctypes.data_as(uint8_pointer),
        draft_fields[5].ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
        draft_fields[6].ctypes.data_as(double_pointer),
        draft_fields[7].ctypes.data_as(int32_pointer),
        draft_fields[8].ctypes.data_as(double_pointer),
        draft_count,
        step,
        beam_width,
        position_quantization,
        int(target_enabled),
        0.0 if target_x is None else target_x,
        0.0 if target_y is None else target_y,
        0 if target_deadline is None else target_deadline,
        item_safety_clearance,
        playfield_left,
        playfield_right,
        playfield_top,
        playfield_bottom,
        reserve_distance,
        diagonal_speed,
        cardinal_speed,
        action_fields[0].ctypes.data_as(int32_pointer),
        action_fields[1].ctypes.data_as(double_pointer),
        action_fields[2].ctypes.data_as(uint8_pointer),
        action_fields[3].ctypes.data_as(uint8_pointer),
        action_fields[4].ctypes.data_as(double_pointer),
        action_count,
        int(preserve_first_action_strata),
        retained.ctypes.data_as(int32_pointer),
        ctypes.byref(retained_count),
    )
    if result != 0:
        raise RuntimeError(f"native local beam reducer returned {result}")
    count = int(retained_count.value)
    if count <= 0 or count > len(retained):
        raise RuntimeError(
            f"native local beam reducer returned invalid count {count}"
        )
    return retained[:count].copy()



__all__ = ["reduce_local_beam"]
