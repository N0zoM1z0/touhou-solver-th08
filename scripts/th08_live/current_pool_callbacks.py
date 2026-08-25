"""Fail-closed callback composition for the sensed TH08 bullet pool.

Future-source callbacks are expressed in the projection root's frame
coordinate.  This module rebases the still-future suffix to one coherent
bullet snapshot and lowers source callbacks 12/14 to the motion and collision
schedules consumed by the local hazard projector.  It never substitutes a
point for a set-valued operand.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from th08_future_birth_envelope import FutureTaggedBulletCallback
from th08_future_hazard_projection import OrdinaryFutureHazardProjection
from th08_live.models import Bullet, PackedBulletSnapshot
from th08_semantics.source_primitives import (
    Callback12State,
    apply_callback12,
    apply_callback14,
)
from touhou_control.pipeline_identity import VersionIdentity
from touhou_control.trajectory import CollisionStateChange, VelocityChange


CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION = (
    "th08-current-pool-callback-composition-v1-source-callback12-14"
)
CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION = (
    "th08-current-pool-callback-join-v1-projection-bullet-policy-clocks"
)

BulletPoolSnapshot = tuple[Bullet, ...] | PackedBulletSnapshot


@dataclass(frozen=True)
class CurrentPoolCallbackComposition:
    """One bounded callback-to-live-pool composition result."""

    bullets: BulletPoolSnapshot
    complete: bool
    reason: str | None
    source_offset: int
    covered_through_frame: int
    callback_count: int
    affected_bullet_count: int

    def __post_init__(self) -> None:
        if self.complete != (self.reason is None):
            raise ValueError(
                "complete callback composition must have exactly no reason"
            )
        if self.source_offset < 0 or self.covered_through_frame < 0:
            raise ValueError("callback composition frames cannot be negative")
        if self.callback_count < 0 or self.affected_bullet_count < 0:
            raise ValueError("callback composition counts cannot be negative")

    @property
    def semantics_version(self) -> str:
        return CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION


@dataclass(frozen=True)
class CurrentPoolProjectionCallbackJoin:
    """Bind one callback composition to its projection and policy clocks."""

    bullets: BulletPoolSnapshot
    projection_digest: str
    projection_version: VersionIdentity
    projection_root_frame: int
    bullet_root_frame: int
    policy_source_frame: int
    policy_horizon_frames: int
    required_bullet_horizon_frames: int
    complete: bool
    reason: str | None
    composition: CurrentPoolCallbackComposition | None

    def __post_init__(self) -> None:
        if len(self.projection_digest) != 64:
            raise ValueError("callback join projection digest must be SHA-256")
        if min(
            self.projection_root_frame,
            self.bullet_root_frame,
            self.policy_source_frame,
            self.policy_horizon_frames,
            self.required_bullet_horizon_frames,
        ) < 0:
            raise ValueError("callback join frames cannot be negative")
        if self.complete != (self.reason is None):
            raise ValueError("complete callback join must have no reason")
        if self.complete and (
            self.composition is None or not self.composition.complete
        ):
            raise ValueError("complete callback join needs complete composition")
        if self.composition is not None:
            expected_offset = (
                self.bullet_root_frame - self.projection_root_frame
            )
            if self.composition.source_offset != expected_offset:
                raise ValueError("callback join composition offset disagrees")
            if (
                self.composition.covered_through_frame
                != self.required_bullet_horizon_frames
            ):
                raise ValueError("callback join composition horizon disagrees")
            if self.composition.bullets is not self.bullets:
                raise ValueError("callback join bullets are not composed output")

    @property
    def semantics_version(self) -> str:
        return CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION

    def matches_projection(
        self,
        projection: OrdinaryFutureHazardProjection,
    ) -> bool:
        return (
            self.projection_digest == projection.digest
            and self.projection_version == projection.version
            and self.projection_root_frame == projection.root_frame
        )

    def record(self) -> dict[str, object]:
        return {
            "semantics_version": self.semantics_version,
            "composition_semantics_version": (
                self.composition.semantics_version
                if self.composition is not None
                else None
            ),
            "projection_digest": self.projection_digest,
            "projection_version": self.projection_version.record(),
            "projection_root_frame": self.projection_root_frame,
            "bullet_root_frame": self.bullet_root_frame,
            "policy_source_frame": self.policy_source_frame,
            "policy_horizon_frames": self.policy_horizon_frames,
            "required_bullet_horizon_frames": (
                self.required_bullet_horizon_frames
            ),
            "complete": self.complete,
            "reason": self.reason,
            "callback_count": (
                self.composition.callback_count
                if self.composition is not None
                else None
            ),
            "affected_bullet_count": (
                self.composition.affected_bullet_count
                if self.composition is not None
                else None
            ),
        }


def _result(
    bullets: BulletPoolSnapshot,
    *,
    complete: bool,
    reason: str | None,
    source_offset: int,
    horizon_frames: int,
    callback_count: int,
    affected_bullet_count: int = 0,
) -> CurrentPoolCallbackComposition:
    return CurrentPoolCallbackComposition(
        bullets=bullets,
        complete=complete,
        reason=reason,
        source_offset=source_offset,
        covered_through_frame=horizon_frames,
        callback_count=callback_count,
        affected_bullet_count=affected_bullet_count,
    )


def _bullet_tag_flags(bullet: Bullet) -> tuple[int | None, str | None]:
    captured = int(bullet.original_transform_flags)
    runtime = bullet.transform_runtime
    if runtime is None:
        return captured, None
    runtime_flags = int(runtime.original_flags)
    if captured and captured != runtime_flags:
        return None, (
            f"bullet slot {bullet.slot} has conflicting original tag flags"
        )
    return captured or runtime_flags, None


def _point_value(
    callback: FutureTaggedBulletCallback,
    *,
    operand: str,
) -> tuple[float | None, str | None]:
    interval = (
        callback.callback_speed
        if operand == "speed"
        else callback.callback_angle
    )
    if interval is None:
        return None, (
            f"callback {callback.callback_index} has no {operand} operand"
        )
    if interval.lower != interval.upper:
        return None, (
            f"callback {callback.callback_index} {operand} is set-valued"
        )
    return interval.lower, None


def compose_current_pool_callbacks(
    bullets: BulletPoolSnapshot,
    *,
    callbacks: tuple[FutureTaggedBulletCallback, ...],
    time_scale: float,
    source_offset: int,
    horizon_frames: int,
    event_frame_uncertainty: int = 0,
) -> CurrentPoolCallbackComposition:
    """Compose callbacks strictly after ``source_offset`` through a horizon.

    ``source_offset`` is the bullet snapshot frame measured from the future
    projection root.  A callback at or before that offset is already reflected
    in the sensed bullet state; a later callback is rebased by subtracting the
    offset.  Equal-frame callbacks retain tuple order and are collapsed to one
    final pre-movement schedule entry per bullet.
    """

    if source_offset < 0 or horizon_frames < 0:
        raise ValueError("callback composition frames cannot be negative")
    if event_frame_uncertainty < 0:
        raise ValueError("callback event-frame uncertainty cannot be negative")
    if not math.isfinite(time_scale) or time_scale <= 0.0:
        raise ValueError("callback time scale must be finite and positive")
    if any(
        later.frame < earlier.frame
        for earlier, later in zip(callbacks, callbacks[1:])
    ):
        raise ValueError("callback stream must preserve source frame order")

    projection_end = source_offset + horizon_frames
    relevant = tuple(
        callback
        for callback in callbacks
        if source_offset < callback.frame <= projection_end
    )
    if not relevant:
        return _result(
            bullets,
            complete=True,
            reason=None,
            source_offset=source_offset,
            horizon_frames=horizon_frames,
            callback_count=0,
        )
    if event_frame_uncertainty:
        return _result(
            bullets,
            complete=False,
            reason="callback event frame is not point-aligned to bullet state",
            source_offset=source_offset,
            horizon_frames=horizon_frames,
            callback_count=len(relevant),
        )

    materialized = tuple(bullets)
    tag_flags: list[int] = []
    for bullet in materialized:
        flags, reason = _bullet_tag_flags(bullet)
        if reason is not None or flags is None:
            return _result(
                bullets,
                complete=False,
                reason=reason or "bullet tag flags are unavailable",
                source_offset=source_offset,
                horizon_frames=horizon_frames,
                callback_count=len(relevant),
            )
        tag_flags.append(flags)

    pool_tags = 0
    for flags in tag_flags:
        pool_tags |= flags
    effective = tuple(
        callback
        for callback in relevant
        if callback.tag_mask & pool_tags
    )
    if not effective:
        return _result(
            bullets,
            complete=True,
            reason=None,
            source_offset=source_offset,
            horizon_frames=horizon_frames,
            callback_count=len(relevant),
        )

    resolved: list[tuple[FutureTaggedBulletCallback, float | None, float]] = []
    for callback in effective:
        speed, reason = _point_value(callback, operand="speed")
        if reason is not None or speed is None:
            return _result(
                bullets,
                complete=False,
                reason=reason or "callback speed is unavailable",
                source_offset=source_offset,
                horizon_frames=horizon_frames,
                callback_count=len(relevant),
            )
        angle: float | None = None
        if callback.callback_index == 12:
            angle, reason = _point_value(callback, operand="angle")
            if reason is not None or angle is None:
                return _result(
                    bullets,
                    complete=False,
                    reason=reason or "callback angle is unavailable",
                    source_offset=source_offset,
                    horizon_frames=horizon_frames,
                    callback_count=len(relevant),
                )
        resolved.append((callback, angle, speed))

    attached: list[Bullet] = []
    affected_bullet_count = 0
    for bullet, flags in zip(materialized, tag_flags):
        matching = tuple(
            entry
            for entry in resolved
            if entry[0].tag_mask & flags
        )
        if not matching:
            attached.append(bullet)
            continue
        if bullet.transform_flags or bullet.transform_runtime is not None:
            return _result(
                bullets,
                complete=False,
                reason=(
                    f"bullet slot {bullet.slot} requires callback/transform "
                    "composition"
                ),
                source_offset=source_offset,
                horizon_frames=horizon_frames,
                callback_count=len(relevant),
            )
        if bullet.velocity_changes or bullet.collision_state_changes:
            return _result(
                bullets,
                complete=False,
                reason=(
                    f"bullet slot {bullet.slot} already has a trajectory "
                    "schedule"
                ),
                source_offset=source_offset,
                horizon_frames=horizon_frames,
                callback_count=len(relevant),
            )
        if (
            bullet.speed is None
            or bullet.angle is None
            or not all(
                math.isfinite(value)
                for value in (
                    bullet.speed,
                    bullet.angle,
                    bullet.vx,
                    bullet.vy,
                )
            )
        ):
            return _result(
                bullets,
                complete=False,
                reason=f"bullet slot {bullet.slot} lacks finite callback state",
                source_offset=source_offset,
                horizon_frames=horizon_frames,
                callback_count=len(relevant),
            )

        state = Callback12State(
            phase_state=bullet.callback_phase_state,
            collision_aux=bullet.callback_aux_state,
            # Presentation fields do not feed any callback motion/collision
            # branch. They are carried only because the shared scalar oracle
            # transcribes the complete native callback record.
            presentation_flags=0,
            animation_index=0,
            base_speed=bullet.speed,
            base_angle=bullet.angle,
            velocity_x=bullet.vx,
            velocity_y=bullet.vy,
        )
        velocity_changes: list[VelocityChange] = []
        collision_changes: list[CollisionStateChange] = []
        cursor = 0
        while cursor < len(matching):
            source_frame = matching[cursor][0].frame
            while (
                cursor < len(matching)
                and matching[cursor][0].frame == source_frame
            ):
                callback, angle, speed = matching[cursor]
                if callback.callback_index == 12:
                    assert angle is not None
                    state, changed = apply_callback12(
                        state,
                        bullet_tags=flags,
                        selected_tags=callback.tag_mask,
                        callback_angle=angle,
                        callback_speed=speed,
                        time_scale=time_scale,
                    )
                else:
                    state, changed = apply_callback14(
                        state,
                        bullet_tags=flags,
                        selected_tags=callback.tag_mask,
                        callback_speed=speed,
                        time_scale=time_scale,
                    )
                if not changed:
                    raise AssertionError("preselected callback did not match")
                cursor += 1
            local_frame = source_frame - source_offset
            velocity_changes.append(
                VelocityChange(
                    local_frame,
                    state.velocity_x,
                    state.velocity_y,
                )
            )
            collision_changes.append(
                CollisionStateChange(
                    local_frame,
                    state.collision_aux == 0,
                )
            )
        attached.append(
            replace(
                bullet,
                velocity_changes=tuple(velocity_changes),
                collision_state_changes=tuple(collision_changes),
            )
        )
        affected_bullet_count += 1

    return _result(
        tuple(attached),
        complete=True,
        reason=None,
        source_offset=source_offset,
        horizon_frames=horizon_frames,
        callback_count=len(relevant),
        affected_bullet_count=affected_bullet_count,
    )


def join_projection_callbacks_to_current_pool(
    bullets: BulletPoolSnapshot,
    *,
    projection: OrdinaryFutureHazardProjection,
    bullet_root_frame: int,
    policy_source_frame: int,
    policy_horizon_frames: int,
    time_scale: float,
    bullet_frame_uncertainty: int = 0,
) -> CurrentPoolProjectionCallbackJoin:
    """Bind source, bullet, and policy clocks around one composition."""

    if min(
        bullet_root_frame,
        policy_source_frame,
        policy_horizon_frames,
        bullet_frame_uncertainty,
    ) < 0:
        raise ValueError("callback join frames cannot be negative")
    policy_horizon_frame = policy_source_frame + policy_horizon_frames
    required_bullet_horizon = max(
        0,
        policy_horizon_frame - bullet_root_frame,
    )

    def incomplete(reason: str) -> CurrentPoolProjectionCallbackJoin:
        return CurrentPoolProjectionCallbackJoin(
            bullets=bullets,
            projection_digest=projection.digest,
            projection_version=projection.version,
            projection_root_frame=projection.root_frame,
            bullet_root_frame=bullet_root_frame,
            policy_source_frame=policy_source_frame,
            policy_horizon_frames=policy_horizon_frames,
            required_bullet_horizon_frames=required_bullet_horizon,
            complete=False,
            reason=reason,
            composition=None,
        )

    if not projection.source_closure_complete or not projection.coverage.complete:
        return incomplete("future source projection is incomplete")
    if bullet_root_frame < projection.root_frame:
        return incomplete("bullet snapshot predates future source root")
    if policy_source_frame < bullet_root_frame:
        return incomplete("policy source predates bullet snapshot")
    if policy_horizon_frame > projection.horizon_frame:
        return incomplete("future source projection misses policy horizon")
    if projection.tagged_callbacks and bullet_frame_uncertainty:
        return incomplete("bullet snapshot is not point-aligned to callbacks")

    composition = compose_current_pool_callbacks(
        bullets,
        callbacks=projection.tagged_callbacks,
        time_scale=time_scale,
        source_offset=bullet_root_frame - projection.root_frame,
        horizon_frames=required_bullet_horizon,
        event_frame_uncertainty=bullet_frame_uncertainty,
    )
    return CurrentPoolProjectionCallbackJoin(
        bullets=composition.bullets,
        projection_digest=projection.digest,
        projection_version=projection.version,
        projection_root_frame=projection.root_frame,
        bullet_root_frame=bullet_root_frame,
        policy_source_frame=policy_source_frame,
        policy_horizon_frames=policy_horizon_frames,
        required_bullet_horizon_frames=required_bullet_horizon,
        complete=composition.complete,
        reason=composition.reason,
        composition=composition,
    )


__all__ = [
    "CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION",
    "CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION",
    "CurrentPoolCallbackComposition",
    "CurrentPoolProjectionCallbackJoin",
    "compose_current_pool_callbacks",
    "join_projection_callbacks_to_current_pool",
]
