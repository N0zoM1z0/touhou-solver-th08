"""Source-stage current-plus-future hazard join for offline solver campaigns.

This adapter consumes the resolved stage IR; it does not interpret arbitrary
ECL.  Every due emitter, callback-12/14 event, and laser spawn in the bounded
horizon is projected from the same root as the sensed bullet pool.  Possible
pool suppression and later culling are intentionally ignored, which retains a
safe superset of hostile geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from th08_bullet_transform_model import parse_transform_program
from th08_future_birth_envelope import (
    AUTOMATIC_PLAYER_AIM_MODES,
    FloatInterval,
    FutureDirectFire,
    FutureTaggedBulletCallback,
)
from th08_future_hazard_projection import (
    OrdinaryFutureHazardProjection,
    complete_future_hazard_projection,
    player_aim_interval,
)
from th08_laser_model import (
    LaserCollisionBox,
    spawn_laser_state,
    step_laser,
)
from th08_live.current_pool_callbacks import (
    CurrentPoolProjectionCallbackJoin,
    join_projection_callbacks_to_current_pool,
)
from th08_live.movement import (
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
    UNFOCUSED_CARDINAL_SPEED,
)
from th08_semantics.stage import (
    BulletEmitter,
    Callback12Event,
    Callback14Event,
    LaserSpawnEvent,
    StageProgram,
    TRANSFORM_ANGULAR_VELOCITY,
    TRANSFORM_DECELERATE,
    TRANSFORM_REFLECT_ALL,
    TRANSFORM_REFLECT_SIDES_TOP,
    TRANSFORM_STOP_REAIM,
    TRANSFORM_STOP_SNAP,
    TRANSFORM_STOP_TURN,
    TRANSFORM_VECTOR_ACCELERATION,
    pack_transform_specs,
)
from touhou_control.corridor.model import AabbHazard, AabbTrajectoryHazard


STAGE_FUTURE_HAZARD_SEMANTICS_VERSION = (
    "th08-source-stateful-stage-future-hazards-v1"
)


class StageFutureHazardError(ValueError):
    """The resolved stage cannot prove a requested future slab."""


@dataclass(frozen=True)
class StageFutureHazardJoin:
    """One clock-aligned current-pool and future-birth projection."""

    bullets: tuple[Any, ...]
    projection: OrdinaryFutureHazardProjection | None
    complete: bool
    reason: str | None
    callback_join: CurrentPoolProjectionCallbackJoin | None
    direct_fire_event_count: int
    future_laser_count: int
    tagged_callback_count: int
    callback_transform_fallback_count: int

    def __post_init__(self) -> None:
        if self.complete != (self.reason is None):
            raise ValueError("complete stage future join must have no reason")
        if self.complete != (self.projection is not None):
            raise ValueError("complete stage future join requires a projection")
        if min(
            self.direct_fire_event_count,
            self.future_laser_count,
            self.tagged_callback_count,
            self.callback_transform_fallback_count,
        ) < 0:
            raise ValueError("stage future join counts cannot be negative")


def _reachable_player_positions(
    *,
    root_x: float,
    root_y: float,
    steps: int,
) -> tuple[tuple[float, float], ...]:
    distance = UNFOCUSED_CARDINAL_SPEED * steps
    left = max(PLAYFIELD_LEFT, root_x - distance)
    right = min(PLAYFIELD_RIGHT, root_x + distance)
    top = max(PLAYFIELD_TOP, root_y - distance)
    bottom = min(PLAYFIELD_BOTTOM, root_y + distance)
    return (
        (left, top),
        (left, bottom),
        (right, top),
        (right, bottom),
    )


def _callback(
    event: Callback12Event | Callback14Event,
    *,
    root_frame: int,
) -> FutureTaggedBulletCallback:
    relative_frame = event.frame - root_frame + 1
    if isinstance(event, Callback12Event):
        return FutureTaggedBulletCallback(
            source=f"stage:callback12:frame={event.frame}:tag={event.tag_mask:#x}",
            frame=relative_frame,
            callback_index=12,
            tag_mask=event.tag_mask,
            callback_angle=FloatInterval.point(event.angle),
            callback_speed=FloatInterval.point(event.speed),
        )
    return FutureTaggedBulletCallback(
        source=f"stage:callback14:frame={event.frame}:tag={event.tag_mask:#x}",
        frame=relative_frame,
        callback_index=14,
        tag_mask=event.tag_mask,
        callback_angle=None,
        callback_speed=FloatInterval.point(event.speed),
    )


def _emitter_event(
    emitter: BulletEmitter,
    *,
    source_frame: int,
    root_frame: int,
    root_player_x: float,
    root_player_y: float,
    callbacks: tuple[FutureTaggedBulletCallback, ...],
) -> FutureDirectFire:
    if emitter.bullet_type is None:
        raise StageFutureHazardError(
            f"{emitter.emitter_id} lacks a source-resolved bullet type"
        )
    origin_x_value, origin_y_value, pattern = emitter.resolved_descriptor(
        source_frame,
        player_x=root_player_x,
        player_y=root_player_y,
    )
    origin_x = FloatInterval.point(origin_x_value)
    origin_y = FloatInterval.point(origin_y_value)
    activation = source_frame - root_frame + 1
    if emitter.resolved_aim_override is not None:
        aim = FloatInterval.point(emitter.resolved_aim_override)
    elif emitter.mode in AUTOMATIC_PLAYER_AIM_MODES:
        aim = player_aim_interval(
            player_positions=_reachable_player_positions(
                root_x=root_player_x,
                root_y=root_player_y,
                steps=activation,
            ),
            origin_x=origin_x,
            origin_y=origin_y,
        )
    else:
        aim = FloatInterval.point(0.0)

    transform_program = pack_transform_specs(emitter.transforms)
    original_flags = emitter.tag_flags | emitter.spawn_flags
    for transform in emitter.transforms:
        original_flags |= transform.kind
    later_callbacks = tuple(
        callback
        for callback in callbacks
        if callback.frame > activation and callback.tag_mask & original_flags
    )
    return FutureDirectFire(
        source=(
            f"stage:{emitter.emitter_id}:source-frame={source_frame}:"
            f"activation={activation}"
        ),
        activation_frames=(activation,),
        bullet_type=emitter.bullet_type,
        origin_x=origin_x,
        origin_y=origin_y,
        mode=emitter.mode,
        count1=emitter.count1,
        count2=emitter.count2,
        speed1=FloatInterval.point(pattern.speed1),
        speed2=FloatInterval.point(pattern.speed2),
        angle1=FloatInterval.point(pattern.angle),
        angle2=FloatInterval.point(pattern.angle_step),
        aim_angle=aim,
        half_width=emitter.half_width,
        half_height=emitter.half_height,
        original_flags=original_flags,
        transform_program_zero=not any(transform_program),
        transform_program=(transform_program if any(transform_program) else b""),
        # Generated descriptor operands do not read the player-aim variable;
        # modes 0/2/4 add it independently inside the native spawn helper.
        angle1_player_aim_coefficient=0.0,
        angle1_player_aim_residual=FloatInterval.point(pattern.angle),
        angle2_player_aim_coefficient=0.0,
        angle2_player_aim_residual=FloatInterval.point(pattern.angle_step),
        tagged_callbacks=later_callbacks,
    )


def _world_aabb(box: LaserCollisionBox) -> AabbHazard:
    cosine = math.cos(box.angle)
    sine = math.sin(box.angle)
    local_x = box.center_x - box.pivot_x
    local_y = box.center_y - box.pivot_y
    center_x = box.pivot_x + cosine * local_x - sine * local_y
    center_y = box.pivot_y + sine * local_x + cosine * local_y
    local_half_width = box.width / 2.0
    local_half_height = box.height / 2.0
    return AabbHazard(
        x=center_x,
        y=center_y,
        half_width=(
            abs(cosine) * local_half_width
            + abs(sine) * local_half_height
        ),
        half_height=(
            abs(sine) * local_half_width
            + abs(cosine) * local_half_height
        ),
    )


def _union_aabbs(samples: tuple[AabbHazard, ...]) -> AabbHazard:
    left = min(sample.x - sample.half_width for sample in samples)
    right = max(sample.x + sample.half_width for sample in samples)
    top = min(sample.y - sample.half_height for sample in samples)
    bottom = max(sample.y + sample.half_height for sample in samples)
    return AabbHazard(
        x=(left + right) / 2.0,
        y=(top + bottom) / 2.0,
        half_width=(right - left) / 2.0,
        half_height=(bottom - top) / 2.0,
    )


def _laser_trajectory(
    event: LaserSpawnEvent,
    *,
    root_frame: int,
    horizon_frames: int,
) -> AabbTrajectoryHazard:
    activation = event.frame - root_frame + 1
    state = spawn_laser_state(
        origin_x=event.origin_x,
        origin_y=event.origin_y,
        angle=event.angle,
        speed=event.speed,
        tail_distance=event.tail,
        head_distance=event.head,
        maximum_length=event.maximum_length,
        width=event.width,
        warmup_frames=event.warmup_frames,
        active_frames=event.active_frames,
        fade_frames=event.fade_frames,
        collision_enable_frame=event.collision_enable_frame,
        collision_disable_frame=event.collision_disable_frame,
        flags=event.flags,
    )
    samples: list[AabbHazard | None] = [None] * (horizon_frames + 1)
    for frame in range(activation, horizon_frames + 1):
        result = step_laser(state)
        checks = tuple(
            _world_aabb(check.collision_box) for check in result.checks
        )
        if checks:
            samples[frame] = _union_aabbs(checks)
        state = result.laser
        if not state.active:
            break
    return AabbTrajectoryHazard(tuple(samples))


def _callback_transform_fallback_trajectory(
    bullet: Any,
    *,
    callbacks: tuple[FutureTaggedBulletCallback, ...],
    horizon_frames: int,
) -> AabbTrajectoryHazard:
    """Conservatively consume a callback/transform ordering obligation.

    The current local projector cannot interleave callback writes with an
    active retained transform program.  For offline source stages, replace
    only that affected bullet by a finite reachable disk.  This preserves the
    exact current center and source collision geometry while allowing every
    callback speed, stop resume, reflection restore, and acceleration update.
    """

    retained = getattr(bullet, "transform_program_runtime", None)
    if retained is None:
        raise StageFutureHazardError(
            f"bullet slot {bullet.slot} lacks retained transform program"
        )
    records = tuple(
        record
        for record in parse_transform_program(retained.program)
        if record.kind
        and int(bullet.original_transform_flags) & record.kind
    )
    if not records:
        raise StageFutureHazardError(
            f"bullet slot {bullet.slot} active transform lacks a program record"
        )
    base_maximum_speed = max(
        math.hypot(float(bullet.vx), float(bullet.vy)),
        abs(float(bullet.speed or 0.0)),
    )
    callback_speed_schedule = tuple(
        (
            callback.frame,
            max(
                abs(callback.callback_speed.lower),
                abs(callback.callback_speed.upper),
            ),
        )
        for callback in callbacks
    )
    acceleration = 0.0
    for record in records:
        if record.kind == TRANSFORM_DECELERATE:
            # The recovered handler begins at speed 5 regardless of the
            # bullet's current magnitude, then linearly reaches zero.
            base_maximum_speed = max(base_maximum_speed, 5.0)
        elif record.kind in (
            TRANSFORM_VECTOR_ACCELERATION,
            TRANSFORM_ANGULAR_VELOCITY,
        ):
            acceleration += abs(float(record.float_0))
        elif record.kind in (
            TRANSFORM_STOP_TURN,
            TRANSFORM_STOP_REAIM,
            TRANSFORM_STOP_SNAP,
        ):
            if float(record.float_1) > -999.0:
                base_maximum_speed = max(
                    base_maximum_speed,
                    abs(float(record.float_1)),
                )
        elif record.kind in (
            TRANSFORM_REFLECT_ALL,
            TRANSFORM_REFLECT_SIDES_TOP,
        ) and float(record.float_0) >= 0.0:
            base_maximum_speed = max(
                base_maximum_speed,
                abs(float(record.float_0)),
            )

    samples: list[AabbHazard | None] = [
        AabbHazard(
            x=float(bullet.x),
            y=float(bullet.y),
            half_width=float(bullet.half_width),
            half_height=float(bullet.half_height),
        )
    ]
    radius = 0.0
    for frame in range(1, horizon_frames + 1):
        # A future callback may change speed/direction only on its own source
        # update.  Applying its speed from frame one made the fallback grow
        # discontinuously as soon as a far-future callback entered the rolling
        # horizon.  Sum a per-update speed bound instead: the active transform
        # is allowed from the root, while each callback branch starts at its
        # certified relative frame and may then receive every acceleration.
        step_speed = base_maximum_speed + acceleration * frame
        for callback_frame, callback_speed in callback_speed_schedule:
            if callback_frame <= frame:
                step_speed = max(
                    step_speed,
                    callback_speed
                    + acceleration * (frame - callback_frame + 1),
                )
        radius += step_speed
        samples.append(
            AabbHazard(
                x=float(bullet.x),
                y=float(bullet.y),
                half_width=float(bullet.half_width) + radius,
                half_height=float(bullet.half_height) + radius,
            )
        )
    return AabbTrajectoryHazard(tuple(samples))


def _extract_callback_transform_fallbacks(
    bullets: tuple[Any, ...],
    *,
    callbacks: tuple[FutureTaggedBulletCallback, ...],
    horizon_frames: int,
) -> tuple[tuple[Any, ...], tuple[AabbTrajectoryHazard, ...], int]:
    retained_bullets: list[Any] = []
    trajectories: list[AabbTrajectoryHazard] = []
    for bullet in bullets:
        flags = int(getattr(bullet, "original_transform_flags", 0))
        matching = tuple(
            callback
            for callback in callbacks
            if callback.tag_mask & flags
        )
        retained_program = getattr(bullet, "transform_program_runtime", None)
        program_active = bool(
            retained_program is not None and any(retained_program.program)
        )
        needs_fallback = bool(
            matching
            and (
                int(getattr(bullet, "transform_flags", 0))
                or getattr(bullet, "transform_runtime", None) is not None
                or program_active
            )
        )
        if not needs_fallback:
            retained_bullets.append(bullet)
            continue
        trajectories.append(
            _callback_transform_fallback_trajectory(
                bullet,
                callbacks=matching,
                horizon_frames=horizon_frames,
            )
        )
    return tuple(retained_bullets), tuple(trajectories), len(trajectories)


def build_stage_future_hazard_projection(
    program: StageProgram,
    *,
    root_frame: int,
    root_player_x: float,
    root_player_y: float,
    horizon_frames: int,
) -> OrdinaryFutureHazardProjection:
    """Project a bounded suffix of one source-closed resolved stage."""

    if not program.source_closed:
        raise StageFutureHazardError(
            "stage program does not have complete resolved source coverage"
        )
    if root_frame < 0 or root_frame > program.frame_count:
        raise ValueError("stage future root is outside the program")
    if horizon_frames < 0:
        raise ValueError("stage future horizon cannot be negative")
    if not math.isfinite(root_player_x) or not math.isfinite(root_player_y):
        raise ValueError("stage future player root must be finite")

    source_end = min(program.frame_count - 1, root_frame + horizon_frames - 1)
    phases = tuple(
        phase
        for phase in program.phases
        if phase.end_frame >= root_frame and phase.start_frame <= source_end
    ) if source_end >= root_frame else ()
    callbacks = tuple(
        _callback(event, root_frame=root_frame)
        for phase in phases
        for event in phase.callbacks
        if root_frame <= event.frame <= source_end
    )
    if any(
        later.frame < earlier.frame
        for earlier, later in zip(callbacks, callbacks[1:])
    ):
        raise StageFutureHazardError(
            "stage callback stream is not source-frame ordered"
        )

    direct_fire_events = tuple(
        _emitter_event(
            emitter,
            source_frame=source_frame,
            root_frame=root_frame,
            root_player_x=root_player_x,
            root_player_y=root_player_y,
            callbacks=callbacks,
        )
        for phase in phases
        for source_frame in range(
            max(root_frame, phase.start_frame),
            min(source_end, phase.end_frame) + 1,
        )
        for emitter in phase.emitters
        if emitter.due(source_frame)
    )
    laser_events = tuple(
        event
        for phase in phases
        for event in phase.lasers
        if root_frame <= event.frame <= source_end
    )
    laser_trajectories = tuple(
        _laser_trajectory(
            event,
            root_frame=root_frame,
            horizon_frames=horizon_frames,
        )
        for event in laser_events
    )
    return complete_future_hazard_projection(
        root_frame=root_frame,
        horizon_frames=horizon_frames,
        events=direct_fire_events,
        aabb_trajectories=laser_trajectories,
        tagged_callbacks=callbacks,
        source_semantics_version=(
            f"{STAGE_FUTURE_HAZARD_SEMANTICS_VERSION}:"
            f"{program.source_authority_commit}"
        ),
    )


def join_stage_future_hazards(
    program: StageProgram,
    *,
    root_frame: int,
    root_player_x: float,
    root_player_y: float,
    bullets: tuple[Any, ...],
    horizon_frames: int,
) -> StageFutureHazardJoin:
    """Attach future callbacks to the sensed pool and consume their stream."""

    try:
        projection = build_stage_future_hazard_projection(
            program,
            root_frame=root_frame,
            root_player_x=root_player_x,
            root_player_y=root_player_y,
            horizon_frames=horizon_frames,
        )
    except ValueError as error:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=None,
            complete=False,
            reason=str(error),
            callback_join=None,
            direct_fire_event_count=0,
            future_laser_count=0,
            tagged_callback_count=0,
            callback_transform_fallback_count=0,
        )

    event_count = len(projection.direct_fire_events)
    laser_count = len(projection.aabb_trajectories)
    callback_count = len(projection.tagged_callbacks)
    if not projection.tagged_callbacks:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=projection,
            complete=True,
            reason=None,
            callback_join=None,
            direct_fire_event_count=event_count,
            future_laser_count=laser_count,
            tagged_callback_count=0,
            callback_transform_fallback_count=0,
        )

    try:
        (
            composable_bullets,
            callback_transform_trajectories,
            callback_transform_fallback_count,
        ) = _extract_callback_transform_fallbacks(
            bullets,
            callbacks=projection.tagged_callbacks,
            horizon_frames=horizon_frames,
        )
    except StageFutureHazardError as error:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=None,
            complete=False,
            reason=str(error),
            callback_join=None,
            direct_fire_event_count=event_count,
            future_laser_count=laser_count,
            tagged_callback_count=callback_count,
            callback_transform_fallback_count=0,
        )
    try:
        callback_join = join_projection_callbacks_to_current_pool(
            composable_bullets,
            projection=projection,
            bullet_root_frame=root_frame,
            policy_source_frame=root_frame,
            policy_horizon_frames=horizon_frames,
            time_scale=1.0,
        )
    except ValueError as error:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=None,
            complete=False,
            reason=str(error),
            callback_join=None,
            direct_fire_event_count=event_count,
            future_laser_count=laser_count,
            tagged_callback_count=callback_count,
            callback_transform_fallback_count=(
                callback_transform_fallback_count
            ),
        )
    if not callback_join.complete:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=None,
            complete=False,
            reason=callback_join.reason,
            callback_join=callback_join,
            direct_fire_event_count=event_count,
            future_laser_count=laser_count,
            tagged_callback_count=callback_count,
            callback_transform_fallback_count=(
                callback_transform_fallback_count
            ),
        )

    # Direct-fire events already retain their matching later callbacks.  The
    # global callback tuple exists solely for bullets alive at the root; once
    # those schedules are attached, removing it marks that obligation as
    # consumed without weakening any future-birth trajectory.
    try:
        consumed = complete_future_hazard_projection(
            root_frame=projection.root_frame,
            horizon_frames=projection.horizon_frames,
            events=projection.direct_fire_events,
            aabb_trajectories=(
                *projection.aabb_trajectories,
                *callback_transform_trajectories,
            ),
            tagged_callbacks=(),
            source_semantics_version=(
                f"{projection.source_semantics_version}+"
                "current-pool-callbacks-consumed-v1"
            ),
        )
    except ValueError as error:
        return StageFutureHazardJoin(
            bullets=bullets,
            projection=None,
            complete=False,
            reason=str(error),
            callback_join=callback_join,
            direct_fire_event_count=event_count,
            future_laser_count=laser_count,
            tagged_callback_count=callback_count,
            callback_transform_fallback_count=(
                callback_transform_fallback_count
            ),
        )
    return StageFutureHazardJoin(
        bullets=tuple(callback_join.bullets),
        projection=consumed,
        complete=True,
        reason=None,
        callback_join=callback_join,
        direct_fire_event_count=event_count,
        future_laser_count=laser_count,
        tagged_callback_count=callback_count,
        callback_transform_fallback_count=(
            callback_transform_fallback_count
        ),
    )


__all__ = [
    "STAGE_FUTURE_HAZARD_SEMANTICS_VERSION",
    "StageFutureHazardError",
    "StageFutureHazardJoin",
    "build_stage_future_hazard_projection",
    "join_stage_future_hazards",
]
