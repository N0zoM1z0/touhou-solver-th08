"""ctypes boundary for the separately compiled TH08 C source oracle."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from build_th08_source_oracle import DEFAULT_OUTPUT, build, requires_rebuild
from th08_bullet_transform_model import (
    AngularVelocityRuntime,
    BulletTransformProgramRuntime,
    ReflectionTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformTimerRuntime,
    VectorAccelerationRuntime,
)
from th08_current_transform_stepper import (
    CurrentBulletTransformState,
    CurrentTransformUnsupported,
    validate_current_transform_state,
)
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


class _SpawnLifecycleSample(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_int32),
        ("lethal_active", ctypes.c_int32),
        ("terminal_age", ctypes.c_int32),
        ("motion_divisor", ctypes.c_float),
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
    ]


class _EnemySpawnInput(ctypes.Structure):
    _fields_ = [
        ("opcode", ctypes.c_int32),
        ("operand_x", ctypes.c_float),
        ("operand_y", ctypes.c_float),
        ("parent_base_x", ctypes.c_float),
        ("parent_base_y", ctypes.c_float),
        ("parent_world_x", ctypes.c_float),
        ("parent_world_y", ctypes.c_float),
        ("template_relative_x", ctypes.c_float),
        ("template_relative_y", ctypes.c_float),
        ("template_flags", ctypes.c_uint32),
        ("parent_flags", ctypes.c_uint32),
        ("parent_hitpoints", ctypes.c_int32),
        ("player_is_youkais", ctypes.c_int32),
        ("pool_available", ctypes.c_int32),
        ("bootstrap_succeeded", ctypes.c_int32),
        ("bootstrap_base_x", ctypes.c_float),
        ("bootstrap_base_y", ctypes.c_float),
        ("bootstrap_relative_x", ctypes.c_float),
        ("bootstrap_relative_y", ctypes.c_float),
        ("bootstrap_world_x", ctypes.c_float),
        ("bootstrap_world_y", ctypes.c_float),
        ("bootstrap_flags", ctypes.c_uint32),
    ]


class _EnemySpawnSample(ctypes.Structure):
    _fields_ = [
        ("constructor_admitted", ctypes.c_int32),
        ("spawned", ctypes.c_int32),
        ("linked_child", ctypes.c_int32),
        ("follow_parent_base", ctypes.c_int32),
        ("constructor_base_x", ctypes.c_float),
        ("constructor_base_y", ctypes.c_float),
        ("constructor_world_x", ctypes.c_float),
        ("constructor_world_y", ctypes.c_float),
        ("constructor_flags", ctypes.c_uint32),
        ("post_link_base_x", ctypes.c_float),
        ("post_link_base_y", ctypes.c_float),
        ("post_link_relative_x", ctypes.c_float),
        ("post_link_relative_y", ctypes.c_float),
        ("post_link_world_x", ctypes.c_float),
        ("post_link_world_y", ctypes.c_float),
        ("post_link_flags", ctypes.c_uint32),
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


class _TransformState(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("cull_half_width", ctypes.c_float),
        ("cull_half_height", ctypes.c_float),
        ("velocity_x", ctypes.c_float),
        ("velocity_y", ctypes.c_float),
        ("base_speed", ctypes.c_float),
        ("base_angle", ctypes.c_float),
        ("parameter_0", ctypes.c_float),
        ("parameter_1", ctypes.c_float),
        ("restored_speed", ctypes.c_float),
        ("acceleration_x", ctypes.c_float),
        ("acceleration_y", ctypes.c_float),
        ("timer", ctypes.c_int32),
        ("duration", ctypes.c_int32),
        ("repeat_limit", ctypes.c_int32),
        ("repeat_count", ctypes.c_int32),
        ("active", ctypes.c_int32),
    ]


class _TransformTimer(ctypes.Structure):
    _fields_ = [
        ("previous", ctypes.c_int32),
        ("subframe", ctypes.c_float),
        ("current", ctypes.c_int32),
    ]


class _TransformRecord(ctypes.Structure):
    _fields_ = [
        ("float0", ctypes.c_float),
        ("float1", ctypes.c_float),
        ("int0", ctypes.c_int32),
        ("int1", ctypes.c_int32),
        ("kind", ctypes.c_uint32),
        ("allow_while_active", ctypes.c_uint32),
    ]


class _TransformProgramState(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("velocity_x", ctypes.c_float),
        ("velocity_y", ctypes.c_float),
        ("collision_half_width", ctypes.c_float),
        ("collision_half_height", ctypes.c_float),
        ("cull_half_width", ctypes.c_float),
        ("cull_half_height", ctypes.c_float),
        ("base_speed", ctypes.c_float),
        ("base_angle", ctypes.c_float),
        ("bullet_type", ctypes.c_int32),
        ("native_state", ctypes.c_int32),
        ("active_flags", ctypes.c_uint32),
        ("original_flags", ctypes.c_uint32),
        ("queue_cursor", ctypes.c_int32),
        ("cull_suppression_countdown", ctypes.c_int32),
        ("offscreen_counter", ctypes.c_uint16),
        ("retired", ctypes.c_uint16),
        ("program", _TransformRecord * 18),
        ("decelerate_timer", _TransformTimer),
        ("vector_timer", _TransformTimer),
        ("vector_magnitude", ctypes.c_float),
        ("vector_angle", ctypes.c_float),
        ("acceleration_x", ctypes.c_float),
        ("acceleration_y", ctypes.c_float),
        ("vector_duration", ctypes.c_int32),
        ("angular_timer", _TransformTimer),
        ("speed_acceleration", ctypes.c_float),
        ("angular_velocity", ctypes.c_float),
        ("angular_duration", ctypes.c_int32),
        ("stop_timer", _TransformTimer),
        ("stop_resume_speed", ctypes.c_float),
        ("stop_angle_operand", ctypes.c_float),
        ("stop_duration", ctypes.c_int32),
        ("stop_repeat_limit", ctypes.c_int32),
        ("stop_repeat_count", ctypes.c_int32),
        ("reflection_restored_speed", ctypes.c_float),
        ("reflection_event_count", ctypes.c_int32),
        ("reflection_event_limit", ctypes.c_int32),
        ("barrier_timer", _TransformTimer),
        ("wrap_timer", _TransformTimer),
        ("unsupported_kind", ctypes.c_uint32),
    ]


@dataclass(frozen=True)
class NativeTransformState:
    x: float
    y: float
    cull_half_width: float
    cull_half_height: float
    velocity_x: float
    velocity_y: float
    base_speed: float
    base_angle: float
    parameter_0: float
    parameter_1: float
    restored_speed: float
    acceleration_x: float
    acceleration_y: float
    timer: int
    duration: int
    repeat_limit: int
    repeat_count: int
    active: bool = True


@dataclass(frozen=True)
class NativeSpawnLifecycleSample:
    state: int
    lethal_active: bool
    terminal_age: int
    motion_divisor: float
    x: float
    y: float


@dataclass(frozen=True)
class NativeEnemySpawnSample:
    constructor_admitted: bool
    spawned: bool
    linked_child: bool
    follow_parent_base: bool
    constructor_base_x: float
    constructor_base_y: float
    constructor_world_x: float
    constructor_world_y: float
    constructor_flags: int
    post_link_base_x: float
    post_link_base_y: float
    post_link_relative_x: float
    post_link_relative_y: float
    post_link_world_x: float
    post_link_world_y: float
    post_link_flags: int


@dataclass
class NativeTransformProgramBatch:
    """Owned flat native states reusable across projected frames."""

    items: ctypes.Array
    count: int
    poisoned: bool = False


@dataclass
class NativeSourceOracle:
    """Loaded native authority with explicit gameplay-RNG synchronization."""

    library: ctypes.CDLL

    @classmethod
    def load(cls, path: Path = DEFAULT_OUTPUT, *, rebuild: bool = False) -> "NativeSourceOracle":
        if rebuild or requires_rebuild(path):
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
        library.th08_oracle_spawn_lifecycle_sample.argtypes = [
            ctypes.c_int32,
            ctypes.c_uint32,
            ctypes.c_int32,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.POINTER(_SpawnLifecycleSample),
        ]
        library.th08_oracle_spawn_lifecycle_sample.restype = ctypes.c_int32
        library.th08_oracle_enemy_spawn_sample.argtypes = [
            ctypes.POINTER(_EnemySpawnInput),
            ctypes.POINTER(_EnemySpawnSample),
        ]
        library.th08_oracle_enemy_spawn_sample.restype = ctypes.c_int32
        library.th08_oracle_callback12.argtypes = [
            ctypes.POINTER(_Callback12State),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
        ]
        library.th08_oracle_callback12.restype = ctypes.c_int32
        library.th08_oracle_callback14.argtypes = [
            ctypes.POINTER(_Callback12State),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_float,
            ctypes.c_float,
        ]
        library.th08_oracle_callback14.restype = ctypes.c_int32
        library.th08_oracle_aabb_overlap.argtypes = [ctypes.c_float] * 8
        library.th08_oracle_aabb_overlap.restype = ctypes.c_int32
        library.th08_oracle_rng_next_f32.argtypes = [ctypes.POINTER(_Rng)]
        library.th08_oracle_rng_next_f32.restype = ctypes.c_float
        library.th08_oracle_transform_step.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_TransformState),
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
        ]
        library.th08_oracle_transform_step.restype = ctypes.c_int32
        library.th08_oracle_transform_program_frame.argtypes = [
            ctypes.POINTER(_TransformProgramState),
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        library.th08_oracle_transform_program_frame.restype = ctypes.c_int32
        library.th08_oracle_transform_program_batch.argtypes = [
            ctypes.POINTER(_TransformProgramState),
            ctypes.c_uint32,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        library.th08_oracle_transform_program_batch.restype = ctypes.c_int32
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

    def spawn_lifecycle_sample(
        self,
        *,
        bullet_type: int,
        original_flags: int,
        age: int,
        origin_x: float,
        origin_y: float,
        velocity_x: float,
        velocity_y: float,
    ) -> NativeSpawnLifecycleSample:
        output = _SpawnLifecycleSample()
        status = self.library.th08_oracle_spawn_lifecycle_sample(
            bullet_type,
            original_flags,
            age,
            origin_x,
            origin_y,
            velocity_x,
            velocity_y,
            output,
        )
        if status != 0:
            raise ValueError("native source oracle rejected spawn lifecycle")
        return NativeSpawnLifecycleSample(
            state=int(output.state),
            lethal_active=bool(output.lethal_active),
            terminal_age=int(output.terminal_age),
            motion_divisor=float(output.motion_divisor),
            x=float(output.x),
            y=float(output.y),
        )

    def enemy_spawn_sample(
        self,
        *,
        opcode: int,
        operand_x: float,
        operand_y: float,
        parent_base_x: float,
        parent_base_y: float,
        parent_world_x: float,
        parent_world_y: float,
        template_relative_x: float,
        template_relative_y: float,
        template_flags: int,
        parent_flags: int,
        parent_hitpoints: int,
        player_is_youkais: bool,
        pool_available: bool,
        bootstrap_succeeded: bool,
        bootstrap_base_x: float,
        bootstrap_base_y: float,
        bootstrap_relative_x: float,
        bootstrap_relative_y: float,
        bootstrap_world_x: float,
        bootstrap_world_y: float,
        bootstrap_flags: int,
    ) -> NativeEnemySpawnSample:
        native_input = _EnemySpawnInput(
            opcode,
            operand_x,
            operand_y,
            parent_base_x,
            parent_base_y,
            parent_world_x,
            parent_world_y,
            template_relative_x,
            template_relative_y,
            template_flags,
            parent_flags,
            parent_hitpoints,
            int(player_is_youkais),
            int(pool_available),
            int(bootstrap_succeeded),
            bootstrap_base_x,
            bootstrap_base_y,
            bootstrap_relative_x,
            bootstrap_relative_y,
            bootstrap_world_x,
            bootstrap_world_y,
            bootstrap_flags,
        )
        output = _EnemySpawnSample()
        status = self.library.th08_oracle_enemy_spawn_sample(
            native_input,
            output,
        )
        if status != 0:
            raise ValueError(
                f"native source oracle rejected enemy spawn opcode {opcode:#x}"
            )
        return NativeEnemySpawnSample(
            constructor_admitted=bool(output.constructor_admitted),
            spawned=bool(output.spawned),
            linked_child=bool(output.linked_child),
            follow_parent_base=bool(output.follow_parent_base),
            constructor_base_x=float(output.constructor_base_x),
            constructor_base_y=float(output.constructor_base_y),
            constructor_world_x=float(output.constructor_world_x),
            constructor_world_y=float(output.constructor_world_y),
            constructor_flags=int(output.constructor_flags),
            post_link_base_x=float(output.post_link_base_x),
            post_link_base_y=float(output.post_link_base_y),
            post_link_relative_x=float(output.post_link_relative_x),
            post_link_relative_y=float(output.post_link_relative_y),
            post_link_world_x=float(output.post_link_world_x),
            post_link_world_y=float(output.post_link_world_y),
            post_link_flags=int(output.post_link_flags),
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

    def callback14(
        self,
        state: Callback12State,
        *,
        bullet_tags: int,
        selected_tags: int,
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
            self.library.th08_oracle_callback14(
                native,
                bullet_tags,
                selected_tags,
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

    def transform_step(
        self,
        kind: int,
        state: NativeTransformState,
        *,
        player_x: float,
        player_y: float,
        time_scale: float = 1.0,
    ) -> NativeTransformState:
        native = _TransformState(
            state.x,
            state.y,
            state.cull_half_width,
            state.cull_half_height,
            state.velocity_x,
            state.velocity_y,
            state.base_speed,
            state.base_angle,
            state.parameter_0,
            state.parameter_1,
            state.restored_speed,
            state.acceleration_x,
            state.acceleration_y,
            state.timer,
            state.duration,
            state.repeat_limit,
            state.repeat_count,
            int(state.active),
        )
        status = self.library.th08_oracle_transform_step(
            kind,
            native,
            player_x,
            player_y,
            time_scale,
        )
        if status != 0:
            raise ValueError(
                f"native source oracle rejected transform {kind:#x}"
            )
        return NativeTransformState(
            x=float(native.x),
            y=float(native.y),
            cull_half_width=float(native.cull_half_width),
            cull_half_height=float(native.cull_half_height),
            velocity_x=float(native.velocity_x),
            velocity_y=float(native.velocity_y),
            base_speed=float(native.base_speed),
            base_angle=float(native.base_angle),
            parameter_0=float(native.parameter_0),
            parameter_1=float(native.parameter_1),
            restored_speed=float(native.restored_speed),
            acceleration_x=float(native.acceleration_x),
            acceleration_y=float(native.acceleration_y),
            timer=int(native.timer),
            duration=int(native.duration),
            repeat_limit=int(native.repeat_limit),
            repeat_count=int(native.repeat_count),
            active=bool(native.active),
        )

    @staticmethod
    def _transform_timer(
        timer: TransformTimerRuntime | None,
    ) -> _TransformTimer:
        if timer is None:
            return _TransformTimer()
        return _TransformTimer(timer.previous, timer.subframe, timer.current)

    @staticmethod
    def _program_state(
        state: CurrentBulletTransformState,
    ) -> _TransformProgramState:
        validate_current_transform_state(state)
        runtime = state.runtime
        if len(runtime.program) != ctypes.sizeof(_TransformRecord) * 18:
            raise ValueError("transform program must be exactly 432 bytes")
        native = _TransformProgramState(
            x=state.x,
            y=state.y,
            velocity_x=state.velocity_x,
            velocity_y=state.velocity_y,
            collision_half_width=state.collision_half_width,
            collision_half_height=state.collision_half_height,
            cull_half_width=state.cull_half_width,
            cull_half_height=state.cull_half_height,
            base_speed=state.base_speed,
            base_angle=state.base_angle,
            bullet_type=state.bullet_type,
            native_state=state.native_state,
            active_flags=state.active_flags,
            original_flags=runtime.original_flags,
            queue_cursor=runtime.queue_cursor,
            cull_suppression_countdown=runtime.cull_suppression_countdown,
            offscreen_counter=runtime.offscreen_counter,
            retired=int(state.retired),
        )
        ctypes.memmove(
            ctypes.addressof(native.program),
            runtime.program,
            len(runtime.program),
        )
        native.decelerate_timer = NativeSourceOracle._transform_timer(
            runtime.decelerate_timer
        )
        vector = runtime.vector_acceleration
        if vector is not None:
            native.vector_timer = NativeSourceOracle._transform_timer(
                vector.timer
            )
            native.vector_magnitude = vector.magnitude
            native.vector_angle = vector.angle
            native.acceleration_x = vector.acceleration_x
            native.acceleration_y = vector.acceleration_y
            native.vector_duration = vector.duration
        angular = runtime.angular_velocity
        if angular is not None:
            native.angular_timer = NativeSourceOracle._transform_timer(
                angular.timer
            )
            native.speed_acceleration = angular.speed_acceleration
            native.angular_velocity = angular.angular_velocity
            native.angular_duration = angular.duration
        stop = runtime.stop
        if stop is not None:
            native.stop_timer = NativeSourceOracle._transform_timer(stop.timer)
            native.stop_resume_speed = stop.resume_speed
            native.stop_angle_operand = stop.angle_operand
            native.stop_duration = stop.duration
            native.stop_repeat_limit = stop.repeat_limit
            native.stop_repeat_count = stop.repeat_count
        reflection = runtime.reflection
        if reflection is not None:
            native.reflection_restored_speed = reflection.restored_speed
            native.reflection_event_count = reflection.event_count
            native.reflection_event_limit = reflection.event_limit
        native.barrier_timer = NativeSourceOracle._transform_timer(
            runtime.barrier_timer
        )
        native.wrap_timer = NativeSourceOracle._transform_timer(
            runtime.wrap_timer
        )
        return native

    @staticmethod
    def _runtime_timer(native: _TransformTimer) -> TransformTimerRuntime:
        return TransformTimerRuntime(
            int(native.previous),
            float(native.subframe),
            int(native.current),
        )

    @staticmethod
    def _current_state(
        native: _TransformProgramState,
    ) -> CurrentBulletTransformState:
        active = int(native.active_flags)
        program = ctypes.string_at(
            ctypes.addressof(native.program),
            ctypes.sizeof(native.program),
        )
        decelerate = None
        if active & int(TransformKind.DECELERATE_16F):
            decelerate = NativeSourceOracle._runtime_timer(
                native.decelerate_timer
            )
        vector = None
        if active & int(TransformKind.VECTOR_ACCELERATION):
            vector = VectorAccelerationRuntime(
                timer=NativeSourceOracle._runtime_timer(native.vector_timer),
                magnitude=float(native.vector_magnitude),
                angle=float(native.vector_angle),
                acceleration_x=float(native.acceleration_x),
                acceleration_y=float(native.acceleration_y),
                duration=int(native.vector_duration),
            )
        angular = None
        if active & int(TransformKind.ANGULAR_VELOCITY):
            angular = AngularVelocityRuntime(
                timer=NativeSourceOracle._runtime_timer(native.angular_timer),
                speed_acceleration=float(native.speed_acceleration),
                angular_velocity=float(native.angular_velocity),
                duration=int(native.angular_duration),
            )
        stop = None
        if active & 0x1C0:
            stop = StopTransformRuntime(
                timer=NativeSourceOracle._runtime_timer(native.stop_timer),
                resume_speed=float(native.stop_resume_speed),
                angle_operand=float(native.stop_angle_operand),
                duration=int(native.stop_duration),
                repeat_limit=int(native.stop_repeat_limit),
                repeat_count=int(native.stop_repeat_count),
            )
        reflection = None
        if active & 0xC00:
            reflection = ReflectionTransformRuntime(
                restored_speed=float(native.reflection_restored_speed),
                event_count=int(native.reflection_event_count),
                event_limit=int(native.reflection_event_limit),
            )
        barrier = None
        if active & int(TransformKind.TIMED_QUEUE_BARRIER):
            barrier = NativeSourceOracle._runtime_timer(native.barrier_timer)
        wrap = None
        if active & 0xC00000:
            wrap = NativeSourceOracle._runtime_timer(native.wrap_timer)
        runtime = BulletTransformProgramRuntime(
            program=program,
            original_flags=int(native.original_flags),
            queue_cursor=int(native.queue_cursor),
            cull_suppression_countdown=int(
                native.cull_suppression_countdown
            ),
            offscreen_counter=int(native.offscreen_counter),
            decelerate_timer=decelerate,
            vector_acceleration=vector,
            angular_velocity=angular,
            stop=stop,
            reflection=reflection,
            barrier_timer=barrier,
            wrap_timer=wrap,
        )
        return CurrentBulletTransformState(
            x=float(native.x),
            y=float(native.y),
            velocity_x=float(native.velocity_x),
            velocity_y=float(native.velocity_y),
            collision_half_width=float(native.collision_half_width),
            collision_half_height=float(native.collision_half_height),
            cull_half_width=float(native.cull_half_width),
            cull_half_height=float(native.cull_half_height),
            base_speed=float(native.base_speed),
            base_angle=float(native.base_angle),
            bullet_type=int(native.bullet_type),
            native_state=int(native.native_state),
            active_flags=active,
            runtime=runtime,
            retired=bool(native.retired),
        )

    @staticmethod
    def _raise_program_status(
        status: int,
        native: _TransformProgramState,
    ) -> None:
        kind = int(native.unsupported_kind)
        if status == 2:
            raise CurrentTransformUnsupported(
                "template_replacement_requires_color_geometry_state",
                kind=kind,
            )
        if status == 3:
            raise CurrentTransformUnsupported(
                "derived_pattern_requires_child_birth_allocation",
                kind=kind,
            )
        if status == 4:
            raise CurrentTransformUnsupported(
                "unmodeled_active_transform_flags",
                kind=kind,
            )
        raise ValueError("native source oracle rejected transform program")

    def transform_program_frame(
        self,
        state: CurrentBulletTransformState,
        *,
        player_x: float,
        player_y: float,
        ecl_time_scale: float = 1.0,
        timer_scale: float = 1.0,
        movement_frozen: bool = False,
        timer_force_tick: bool = False,
    ) -> CurrentBulletTransformState:
        native = self._program_state(state)
        status = self.library.th08_oracle_transform_program_frame(
            native,
            player_x,
            player_y,
            ecl_time_scale,
            timer_scale,
            int(movement_frozen),
            int(timer_force_tick),
        )
        if status != 0:
            self._raise_program_status(status, native)
        return self._current_state(native)

    def transform_program_batch(
        self,
        states: Sequence[CurrentBulletTransformState],
        *,
        player_x: float,
        player_y: float,
        ecl_time_scale: float = 1.0,
        timer_scale: float = 1.0,
        movement_frozen: bool = False,
        timer_force_tick: bool = False,
    ) -> tuple[CurrentBulletTransformState, ...]:
        native = self.prepare_transform_program_batch(states)
        self.advance_transform_program_batch(
            native,
            player_x=player_x,
            player_y=player_y,
            ecl_time_scale=ecl_time_scale,
            timer_scale=timer_scale,
            movement_frozen=movement_frozen,
            timer_force_tick=timer_force_tick,
        )
        return self.decode_transform_program_batch(native)

    def prepare_transform_program_batch(
        self,
        states: Sequence[CurrentBulletTransformState],
    ) -> NativeTransformProgramBatch:
        native_type = _TransformProgramState * len(states)
        items = native_type(*(self._program_state(state) for state in states))
        return NativeTransformProgramBatch(items=items, count=len(states))

    def advance_transform_program_batch(
        self,
        native: NativeTransformProgramBatch,
        *,
        player_x: float,
        player_y: float,
        ecl_time_scale: float = 1.0,
        timer_scale: float = 1.0,
        movement_frozen: bool = False,
        timer_force_tick: bool = False,
    ) -> None:
        if native.poisoned:
            raise ValueError("native transform program batch is poisoned")
        status = self.library.th08_oracle_transform_program_batch(
            native.items,
            native.count,
            player_x,
            player_y,
            ecl_time_scale,
            timer_scale,
            int(movement_frozen),
            int(timer_force_tick),
        )
        if status != 0:
            # The C loop may already have advanced earlier entries. Never let
            # a caller mistake that partial prefix for one coherent frame.
            native.poisoned = True
            failed = next(
                (item for item in native.items if item.unsupported_kind),
                native.items[0],
            )
            self._raise_program_status(status, failed)

    def decode_transform_program_batch(
        self,
        native: NativeTransformProgramBatch,
    ) -> tuple[CurrentBulletTransformState, ...]:
        if native.poisoned:
            raise ValueError("native transform program batch is poisoned")
        return tuple(self._current_state(item) for item in native.items)


__all__ = [
    "NativeEnemySpawnSample",
    "NativeSourceOracle",
    "NativeSpawnLifecycleSample",
    "NativeTransformProgramBatch",
    "NativeTransformState",
]
