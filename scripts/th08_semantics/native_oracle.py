"""ctypes boundary for the separately compiled TH08 C source oracle."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path

from build_th08_source_oracle import DEFAULT_OUTPUT, build
from th08_rng import Th08Rng
from th08_semantics.source_primitives import (
    Callback12State,
    SourcePattern,
    SourcePatternSample,
)


class _Rng(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16),
        ("calls", ctypes.c_uint32),
    ]


class _Pattern(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_int32),
        ("count1", ctypes.c_int32),
        ("count2", ctypes.c_int32),
        ("speed1", ctypes.c_float),
        ("speed2", ctypes.c_float),
        ("angle", ctypes.c_float),
        ("angle_step", ctypes.c_float),
        ("angle_to_player", ctypes.c_float),
        ("time_scale", ctypes.c_float),
    ]


class _PatternSample(ctypes.Structure):
    _fields_ = [
        ("speed", ctypes.c_float),
        ("angle", ctypes.c_float),
        ("velocity_x", ctypes.c_float),
        ("velocity_y", ctypes.c_float),
    ]


class _Callback12State(ctypes.Structure):
    _fields_ = [
        ("phase_state", ctypes.c_int16),
        ("collision_aux", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
        ("presentation_flags", ctypes.c_uint32),
        ("animation_index", ctypes.c_int32),
        ("base_speed", ctypes.c_float),
        ("base_angle", ctypes.c_float),
        ("velocity_x", ctypes.c_float),
        ("velocity_y", ctypes.c_float),
    ]


@dataclass
class NativeSourceOracle:
    """Loaded native authority with explicit gameplay-RNG synchronization."""

    library: ctypes.CDLL

    @classmethod
    def load(cls, path: Path = DEFAULT_OUTPUT, *, rebuild: bool = False) -> "NativeSourceOracle":
        if rebuild or not path.exists():
            build(path)
        library = ctypes.CDLL(str(path))
        library.th08_oracle_pattern_sample.argtypes = [
            ctypes.POINTER(_Pattern),
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(_Rng),
            ctypes.POINTER(_PatternSample),
        ]
        library.th08_oracle_pattern_sample.restype = ctypes.c_int32
        library.th08_oracle_callback12.argtypes = [
            ctypes.POINTER(_Callback12State),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
        ]
        library.th08_oracle_callback12.restype = ctypes.c_int32
        library.th08_oracle_aabb_overlap.argtypes = [ctypes.c_float] * 8
        library.th08_oracle_aabb_overlap.restype = ctypes.c_int32
        library.th08_oracle_rng_next_f32.argtypes = [ctypes.POINTER(_Rng)]
        library.th08_oracle_rng_next_f32.restype = ctypes.c_float
        return cls(library)

    @staticmethod
    def _rng(rng: Th08Rng) -> _Rng:
        return _Rng(rng.state, 0, rng.calls)

    @staticmethod
    def _commit_rng(native: _Rng, rng: Th08Rng) -> None:
        rng.state = int(native.state)
        rng.calls = int(native.calls)

    def rng_next_f32(self, rng: Th08Rng) -> float:
        native = self._rng(rng)
        value = float(self.library.th08_oracle_rng_next_f32(native))
        self._commit_rng(native, rng)
        return value

    def pattern_sample(
        self,
        pattern: SourcePattern,
        *,
        bullet_index: int,
        ring_index: int,
        rng: Th08Rng,
    ) -> SourcePatternSample:
        native_pattern = _Pattern(
            pattern.mode,
            pattern.count1,
            pattern.count2,
            pattern.speed1,
            pattern.speed2,
            pattern.angle,
            pattern.angle_step,
            pattern.angle_to_player,
            pattern.time_scale,
        )
        native_rng = self._rng(rng)
        output = _PatternSample()
        status = self.library.th08_oracle_pattern_sample(
            native_pattern,
            bullet_index,
            ring_index,
            native_rng,
            output,
        )
        if status != 0:
            raise ValueError("native source oracle rejected pattern sample")
        self._commit_rng(native_rng, rng)
        return SourcePatternSample(
            float(output.speed),
            float(output.angle),
            float(output.velocity_x),
            float(output.velocity_y),
        )

    def callback12(
        self,
        state: Callback12State,
        *,
        bullet_tags: int,
        selected_tags: int,
        callback_angle: float,
        callback_speed: float,
        time_scale: float,
    ) -> tuple[Callback12State, bool]:
        native = _Callback12State(
            state.phase_state,
            state.collision_aux,
            0,
            state.presentation_flags,
            state.animation_index,
            state.base_speed,
            state.base_angle,
            state.velocity_x,
            state.velocity_y,
        )
        changed = bool(
            self.library.th08_oracle_callback12(
                native,
                bullet_tags,
                selected_tags,
                callback_angle,
                callback_speed,
                time_scale,
            )
        )
        return (
            Callback12State(
                int(native.phase_state),
                int(native.collision_aux),
                int(native.presentation_flags),
                int(native.animation_index),
                float(native.base_speed),
                float(native.base_angle),
                float(native.velocity_x),
                float(native.velocity_y),
            ),
            changed,
        )

    def aabb_overlap(self, **values: float) -> bool:
        names = (
            "player_x",
            "player_y",
            "player_half_width",
            "player_half_height",
            "hazard_x",
            "hazard_y",
            "hazard_half_width",
            "hazard_half_height",
        )
        return bool(
            self.library.th08_oracle_aabb_overlap(
                *(values[name] for name in names)
            )
        )


__all__ = ["NativeSourceOracle"]
