"""Value models shared by TH08 live sensing, planning, and tracing."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterator

import numpy as np

from th08_bullet_transform_model import (
    BulletTransformRuntime,
    TransformRecord,
)
from touhou_control.trajectory import VelocityChange

if TYPE_CHECKING:
    from th08_live.enemy_combat_progress import EnemyCombatProgressInventory
    from th08_live.enemy_ecl_inventory import EnemyMainEclVmInventory


ENEMY_MAX_OBSERVED_WORLD_SPEED = 32.0
BULLET_LIFECYCLE_TRACE_SCHEMA = "th08-bullet-lifecycle-v1"


@dataclass(frozen=True)
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    half_width: float
    half_height: float
    transform_flags: int = 0
    slot: int = -1
    speed: float | None = None
    angle: float | None = None
    transform_runtime: BulletTransformRuntime | None = None
    callback_phase_state: int = 0
    callback_aux_state: int = 0
    velocity_changes: tuple[VelocityChange, ...] = ()
    trajectory_uncertainty_x: float = 0.0
    trajectory_uncertainty_y: float = 0.0
    original_transform_flags: int = 0
    native_state: int = 1
    native_state_timer_elapsed: int = 0


@dataclass(frozen=True)
class PackedBulletSnapshot:
    """Owned planning fields with lazy compatibility materialization."""

    x: np.ndarray
    y: np.ndarray
    velocity_x: np.ndarray
    velocity_y: np.ndarray
    half_width: np.ndarray
    half_height: np.ndarray
    transform_flags: np.ndarray
    slots: np.ndarray
    speed: np.ndarray
    angle: np.ndarray
    callback_phase: np.ndarray
    callback_aux: np.ndarray
    original_transform_flags: np.ndarray
    native_state: np.ndarray
    native_state_timer_elapsed: np.ndarray

    def __len__(self) -> int:
        return len(self.x)

    def materialize(self, index: int) -> Bullet:
        speed = float(self.speed[index])
        angle = float(self.angle[index])
        return Bullet(
            x=float(self.x[index]),
            y=float(self.y[index]),
            vx=float(self.velocity_x[index]),
            vy=float(self.velocity_y[index]),
            half_width=float(self.half_width[index]),
            half_height=float(self.half_height[index]),
            transform_flags=int(self.transform_flags[index]),
            slot=int(self.slots[index]),
            speed=speed if math.isfinite(speed) else None,
            angle=angle if math.isfinite(angle) else None,
            callback_phase_state=int(self.callback_phase[index]),
            callback_aux_state=int(self.callback_aux[index]),
            original_transform_flags=int(
                self.original_transform_flags[index]
            ),
            native_state=int(self.native_state[index]),
            native_state_timer_elapsed=int(
                self.native_state_timer_elapsed[index]
            ),
        )

    def __iter__(self) -> Iterator[Bullet]:
        return (
            self.materialize(index)
            for index in range(len(self))
        )


def serialize_transform_record(
    record: TransformRecord | None,
) -> list[float | int] | None:
    if record is None:
        return None
    return [
        record.index,
        record.kind,
        int(record.allow_while_active),
        float(record.float_0),
        float(record.float_1),
        record.int_0,
        record.int_1,
    ]


def serialize_bullet_trace(bullet: Bullet) -> list[object]:
    """Retain legacy geometry plus optional diagnostic/gameplay state."""

    legacy: list[object] = [
        bullet.slot,
        bullet.x,
        bullet.y,
        bullet.vx,
        bullet.vy,
        bullet.half_width,
        bullet.half_height,
        bullet.transform_flags,
    ]
    runtime = bullet.transform_runtime
    lifecycle = (
        [
            BULLET_LIFECYCLE_TRACE_SCHEMA,
            bullet.native_state,
            bullet.native_state_timer_elapsed,
            bullet.callback_aux_state,
        ]
        if (
            bullet.native_state != 1
            or bullet.native_state_timer_elapsed != 0
            or bullet.callback_aux_state != 0
        )
        else None
    )
    if runtime is None:
        if (
            bullet.original_transform_flags
            or bullet.velocity_changes
            or bullet.trajectory_uncertainty_x
            or bullet.trajectory_uncertainty_y
        ):
            values = [
                *legacy,
                None,
                [
                    bullet.speed,
                    bullet.angle,
                    bullet.original_transform_flags,
                    bullet.callback_phase_state,
                    bullet.callback_aux_state,
                    [
                        [
                            change.frame,
                            change.velocity_x,
                            change.velocity_y,
                        ]
                        for change in bullet.velocity_changes
                    ],
                    bullet.trajectory_uncertainty_x,
                    bullet.trajectory_uncertainty_y,
                ],
            ]
            return [*values, lifecycle] if lifecycle is not None else values
        values = [*legacy, None]
        return [*values, lifecycle] if lifecycle is not None else values
    values = [
        *legacy,
        [
            bullet.speed,
            bullet.angle,
            runtime.original_flags,
            runtime.queue_cursor,
            serialize_transform_record(runtime.next_record),
            runtime.timer_fraction,
            runtime.timer_elapsed,
            runtime.duration,
            runtime.resume_speed,
            runtime.angle_operand,
            runtime.repeat_limit,
            runtime.repeat_count,
            bullet.callback_phase_state,
            bullet.callback_aux_state,
            [
                [
                    change.frame,
                    change.velocity_x,
                    change.velocity_y,
                ]
                for change in bullet.velocity_changes
            ],
            bullet.trajectory_uncertainty_x,
            bullet.trajectory_uncertainty_y,
        ],
    ]
    return [*values, lifecycle] if lifecycle is not None else values


@dataclass(frozen=True)
class EnemyBody:
    pointer: int
    x: float
    y: float
    vx: float
    vy: float
    half_width: float
    half_height: float
    flags: int
    uncertainty: float = 0.0
    internal_vx: float | None = None
    internal_vy: float | None = None


@dataclass(frozen=True)
class SpellEnemyBodyGuard:
    """Current spell-owner geometry under an uncertain contact mode."""

    body: EnemyBody
    contact_enabled: bool
    raw_contact_width: float | None = None
    raw_contact_height: float | None = None


@dataclass(frozen=True)
class EnemyPoolSnapshot:
    frame_before: int
    frame_after: int
    bodies: tuple[EnemyBody, ...]
    read_ms: float
    attempts: int = 1
    main_ecl_vm_inventory: EnemyMainEclVmInventory | None = None
    combat_progress_inventory: EnemyCombatProgressInventory | None = None

    @property
    def stable(self) -> bool:
        return self.frame_before == self.frame_after


class EnemyBodyModeMemory:
    """Estimate world motion and retain bodies hidden by mode switches."""

    def __init__(
        self,
        *,
        maximum_age_frames: int,
        maximum_world_speed: float = ENEMY_MAX_OBSERVED_WORLD_SPEED,
    ) -> None:
        if maximum_age_frames <= 0:
            raise ValueError("enemy body memory age must be positive")
        if maximum_world_speed <= 0.0:
            raise ValueError("enemy world speed limit must be positive")
        self.maximum_age_frames = maximum_age_frames
        self.maximum_world_speed = maximum_world_speed
        self._context: object = None
        self._samples: dict[int, tuple[int, EnemyBody, bool]] = {}

    def set_context(self, context: object) -> bool:
        if context == self._context:
            return False
        self._context = context
        self._samples.clear()
        return True

    def clear(self) -> None:
        self._samples.clear()

    def merge_snapshot(
        self,
        snapshot: EnemyPoolSnapshot,
        *,
        frame: int,
    ) -> tuple[tuple[EnemyBody, ...], frozenset[int]]:
        """Merge current bodies with bounded projections of absent slots."""

        observed_pointers = {body.pointer for body in snapshot.bodies}
        for body in snapshot.bodies:
            previous = self._samples.get(body.pointer)
            velocity_known = body.internal_vx is None
            velocity_x = body.vx if velocity_known else 0.0
            velocity_y = body.vy if velocity_known else 0.0
            uncertainty = body.uncertainty
            if previous is not None:
                previous_frame, previous_body, previous_known = previous
                elapsed = snapshot.frame_after - previous_frame
                if elapsed > 0:
                    measured_x = (body.x - previous_body.x) / elapsed
                    measured_y = (body.y - previous_body.y) / elapsed
                    if (
                        abs(measured_x) <= self.maximum_world_speed
                        and abs(measured_y) <= self.maximum_world_speed
                    ):
                        velocity_x = measured_x
                        velocity_y = measured_y
                        velocity_known = True
                        uncertainty = body.uncertainty
                    else:
                        velocity_x = (
                            previous_body.vx if previous_known else 0.0
                        )
                        velocity_y = (
                            previous_body.vy if previous_known else 0.0
                        )
                        velocity_known = previous_known
                        uncertainty = body.uncertainty
                elif elapsed == 0:
                    velocity_x = previous_body.vx
                    velocity_y = previous_body.vy
                    velocity_known = previous_known
                    uncertainty = max(
                        body.uncertainty,
                        previous_body.uncertainty,
                    )
                else:
                    continue
            tracked = replace(
                body,
                vx=velocity_x,
                vy=velocity_y,
                uncertainty=uncertainty,
            )
            self._samples[body.pointer] = (
                snapshot.frame_after,
                tracked,
                velocity_known,
            )
        expired = [
            pointer
            for pointer, (
                sample_frame,
                _body,
                _velocity_known,
            ) in self._samples.items()
            if snapshot.frame_after - sample_frame
            > self.maximum_age_frames
        ]
        for pointer in expired:
            del self._samples[pointer]

        bodies = []
        dormant = set()
        for pointer, (
            sample_frame,
            body,
            _velocity_known,
        ) in sorted(self._samples.items()):
            age = frame - sample_frame
            if pointer not in observed_pointers:
                if age < 0 or age > self.maximum_age_frames:
                    continue
                dormant.add(pointer)
            bodies.append(
                replace(
                    body,
                    x=body.x + body.vx * age,
                    y=body.y + body.vy * age,
                    uncertainty=(
                        body.uncertainty
                        + min(16.0, 0.75 * abs(age))
                    ),
                )
            )
        return tuple(bodies), frozenset(dormant)


@dataclass(frozen=True)
class Item:
    slot: int
    x: float
    y: float
    vx: float
    vy: float
    item_type: int
    motion_state: int
    full_value: bool


__all__ = [
    "BULLET_LIFECYCLE_TRACE_SCHEMA",
    "Bullet",
    "ENEMY_MAX_OBSERVED_WORLD_SPEED",
    "EnemyBody",
    "EnemyBodyModeMemory",
    "EnemyPoolSnapshot",
    "Item",
    "PackedBulletSnapshot",
    "SpellEnemyBodyGuard",
    "serialize_bullet_trace",
    "serialize_transform_record",
]
