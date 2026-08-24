"""Deterministic delta-debugging for replayable TH08 semantic cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import math

import th08_live_dodge_agent as live
from th08_laser_runtime import Laser
from th08_semantics.model import SemanticCase


def _ddmin_tuple(
    values: tuple[object, ...],
    *,
    update: Callable[[tuple[object, ...]], SemanticCase],
    fails: Callable[[SemanticCase], bool],
    attempts: list[int],
    maximum_attempts: int,
) -> tuple[object, ...]:
    current = values
    granularity = 2
    while current and attempts[0] < maximum_attempts:
        chunk = max(1, math.ceil(len(current) / granularity))
        reduced = False
        for start in range(0, len(current), chunk):
            candidate = current[:start] + current[start + chunk :]
            attempts[0] += 1
            if fails(update(candidate)):
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
            if attempts[0] >= maximum_attempts:
                break
        if reduced:
            continue
        if granularity >= len(current):
            break
        granularity = min(len(current), granularity * 2)
    return current


def shrink_case(
    case: SemanticCase,
    *,
    fails: Callable[[SemanticCase], bool],
    maximum_attempts: int = 256,
) -> tuple[SemanticCase, int]:
    """Deterministically shrink hazards and planner dimensions."""

    if maximum_attempts <= 0 or not fails(case):
        return case, 0
    attempts = [0]
    current = case

    def retain(candidate: SemanticCase) -> bool:
        nonlocal current
        if attempts[0] >= maximum_attempts or candidate == current:
            return False
        attempts[0] += 1
        if not fails(candidate):
            return False
        current = candidate
        return True

    for field in ("bullets", "lasers", "enemy_bodies"):
        original = getattr(current, field)

        def update(
            values: tuple[object, ...],
            *,
            field_name: str = field,
        ) -> SemanticCase:
            return replace(current, **{field_name: values})

        reduced = _ddmin_tuple(
            original,
            update=update,
            fails=fails,
            attempts=attempts,
            maximum_attempts=maximum_attempts,
        )
        current = replace(current, **{field: reduced})
        if attempts[0] >= maximum_attempts:
            return current, attempts[0]

    # Remove individual piecewise transform and collision-gate events before
    # simplifying their numeric state.  Each accepted edit is based on the
    # latest current case, so a later edit cannot silently restore a previous
    # reduction.
    for bullet_index in range(len(current.bullets)):
        if attempts[0] >= maximum_attempts:
            return current, attempts[0]
        for field in ("velocity_changes", "collision_state_changes"):
            changes = getattr(current.bullets[bullet_index], field)
            if not changes:
                continue

            def update_changes(
                values: tuple[object, ...],
                *,
                index: int = bullet_index,
                field_name: str = field,
            ) -> SemanticCase:
                bullets = list(current.bullets)
                bullets[index] = replace(
                    bullets[index],
                    **{field_name: tuple(values)},
                )
                return replace(current, bullets=tuple(bullets))

            reduced_changes = _ddmin_tuple(
                tuple(changes),
                update=update_changes,
                fails=fails,
                attempts=attempts,
                maximum_attempts=maximum_attempts,
            )
            current = update_changes(reduced_changes)

    retain(
        replace(
            current,
            horizon=max(1, current.horizon // 2),
            action_hold_frames=min(
                current.action_hold_frames,
                max(1, current.horizon // 2),
            ),
        )
    )
    retain(replace(current, beam_width=1))
    retain(
        replace(
            current,
            allowed_first_actions=current.allowed_first_actions[:1],
        )
    )
    retain(replace(current, control_delay_frames=1))
    retain(replace(current, player_x=192.0, player_y=400.0))

    # Axis/zero and tangent simplifications make geometry failures readable.
    for bullet_index in range(len(current.bullets)):
        if attempts[0] >= maximum_attempts:
            break

        def retain_bullet(variant: live.Bullet) -> None:
            bullets = list(current.bullets)
            bullets[bullet_index] = variant
            retain(replace(current, bullets=tuple(bullets)))

        bullet = current.bullets[bullet_index]
        retain_bullet(
            replace(
                bullet,
                velocity_changes=(),
                collision_state_changes=(),
                trajectory_uncertainty_x=0.0,
                trajectory_uncertainty_y=0.0,
            )
        )
        retain_bullet(replace(current.bullets[bullet_index], vx=0.0))
        retain_bullet(replace(current.bullets[bullet_index], vy=0.0))
        retain_bullet(
            replace(current.bullets[bullet_index], vx=0.0, vy=0.0)
        )
        retain_bullet(
            replace(current.bullets[bullet_index], x=0.0, y=0.0)
        )
        bullet = current.bullets[bullet_index]
        retain_bullet(
            replace(
                bullet,
                x=(
                    current.player_x
                    + live.PLAYER_RADIUS
                    + max(bullet.half_width, 0.0)
                ),
                y=current.player_y,
                vx=0.0,
                vy=0.0,
            )
        )

    for laser_index in range(len(current.lasers)):
        if attempts[0] >= maximum_attempts:
            break

        def retain_laser(variant: Laser) -> None:
            lasers = list(current.lasers)
            lasers[laser_index] = variant
            retain(replace(current, lasers=tuple(lasers)))

        laser = current.lasers[laser_index]
        retain_laser(
            replace(
                laser,
                angle=0.0,
                uncertainty=0.0,
                uncertainty_per_frame=0.0,
            )
        )
        laser = current.lasers[laser_index]
        retain_laser(replace(laser, head=laser.tail))
        retain_laser(replace(current.lasers[laser_index], state=None))
        retain_laser(
            replace(
                current.lasers[laser_index],
                origin_x=current.player_x,
                origin_y=current.player_y,
                angle=0.0,
                tail=0.0,
                head=0.0,
            )
        )

    for body_index in range(len(current.enemy_bodies)):
        if attempts[0] >= maximum_attempts:
            break

        def retain_body(variant: live.EnemyBody) -> None:
            bodies = list(current.enemy_bodies)
            bodies[body_index] = variant
            retain(replace(current, enemy_bodies=tuple(bodies)))

        retain_body(
            replace(
                current.enemy_bodies[body_index],
                vx=0.0,
                vy=0.0,
                uncertainty=0.0,
            )
        )
        body = current.enemy_bodies[body_index]
        retain_body(
            replace(
                body,
                x=(
                    current.player_x
                    + live.PLAYER_RADIUS
                    + max(body.half_width, 0.0)
                ),
                y=current.player_y,
                vx=0.0,
                vy=0.0,
                uncertainty=0.0,
            )
        )

    retain(
        replace(
            current,
            positions_x=(current.player_x,),
            positions_y=(current.player_y,),
        )
    )
    return current, attempts[0]
