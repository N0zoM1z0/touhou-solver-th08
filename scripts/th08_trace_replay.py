"""TH08-specific reconstruction helpers for retained compact trace rows."""

from __future__ import annotations

from th08_laser_model import LaserPhase, LaserState
from th08_live_dodge_agent import (
    SUPPORTED_INPUT_MASK,
    Bullet,
    EnemyBody,
    Laser,
    _local_pipeline_action_from_mask,
)
from th08_live.models import BULLET_LIFECYCLE_TRACE_SCHEMA
from touhou_control.local_pipeline_oracle import LocalPipelineRoot
from th08_update_order import (
    TH08_INPUT_PUBLICATION_TO_MOTION_LAG_FRAMES,
)
from touhou_control.trajectory import CollisionStateChange, VelocityChange


def laser_from_trace(values: list[object]) -> Laser:
    state = None
    if len(values) >= 22 and values[7] is not None:
        state = LaserState(
            origin_x=float(values[0]),
            origin_y=float(values[1]),
            angle=float(values[2]),
            tail_distance=float(values[3]),
            head_distance=float(values[4]),
            maximum_length=float(values[7]),
            width=float(values[8]),
            speed=float(values[10]),
            warmup_frames=int(values[15]),
            active_frames=int(values[17]),
            fade_frames=int(values[18]),
            collision_enable_frame=int(values[16]),
            collision_disable_frame=int(values[19]),
            flags=int(values[13]),
            current_width=float(values[9]),
            phase=LaserPhase(int(values[11])),
            timer=int(values[12]),
            timer_fraction=float(values[20]),
            active=True,
        )
    return Laser(
        origin_x=float(values[0]),
        origin_y=float(values[1]),
        angle=float(values[2]),
        tail=float(values[3]),
        head=float(values[4]),
        half_width=float(values[5]),
        state=state,
        slot=int(values[6]),
        collision_flag=int(values[14]) if len(values) > 14 else 0,
        uncertainty=float(values[21]) if len(values) > 21 else 0.0,
        uncertainty_per_frame=(
            float(values[22])
            if len(values) > 22
            else (0.0 if state is not None else 0.08)
        ),
    )


def bullet_from_trace(values: list[object]) -> Bullet:
    """Reconstruct the gameplay trajectory retained by the live trace."""

    runtime = values[8] if len(values) > 8 else None
    projection = values[9] if len(values) > 9 else None
    diagnostic_runtime = isinstance(runtime, list) and len(runtime) >= 12
    planning_projection = (
        not diagnostic_runtime
        and isinstance(projection, list)
        and len(projection) >= 8
    )
    payload = (
        runtime
        if diagnostic_runtime
        else (projection if planning_projection else None)
    )
    lifecycle = next(
        (
            candidate
            for candidate in reversed(values[9:])
            if (
                isinstance(candidate, list)
                and len(candidate) == 4
                and candidate[0] == BULLET_LIFECYCLE_TRACE_SCHEMA
            )
        ),
        None,
    )
    if diagnostic_runtime:
        callback_phase = int(runtime[12]) if len(runtime) > 12 else 0
        callback_aux = int(runtime[13]) if len(runtime) > 13 else 0
        raw_changes = runtime[14] if len(runtime) > 14 else ()
        uncertainty_x = float(runtime[15]) if len(runtime) > 15 else 0.0
        uncertainty_y = float(runtime[16]) if len(runtime) > 16 else 0.0
        raw_collision_changes = runtime[17] if len(runtime) > 17 else ()
    elif planning_projection:
        assert isinstance(projection, list)
        callback_phase = int(projection[3])
        callback_aux = int(projection[4])
        raw_changes = projection[5]
        uncertainty_x = float(projection[6])
        uncertainty_y = float(projection[7])
        raw_collision_changes = projection[8] if len(projection) > 8 else ()
    else:
        callback_phase = 0
        callback_aux = 0
        raw_changes = ()
        uncertainty_x = 0.0
        uncertainty_y = 0.0
        raw_collision_changes = ()
    if lifecycle is not None:
        callback_aux = int(lifecycle[3])
    changes = tuple(
        VelocityChange(
            int(change[0]),
            float(change[1]),
            float(change[2]),
        )
        for change in raw_changes
    )
    collision_changes = tuple(
        CollisionStateChange(int(change[0]), bool(change[1]))
        for change in raw_collision_changes
    )
    return Bullet(
        x=float(values[1]),
        y=float(values[2]),
        vx=float(values[3]),
        vy=float(values[4]),
        half_width=float(values[5]),
        half_height=float(values[6]),
        transform_flags=int(values[7]),
        slot=int(values[0]),
        speed=(
            float(payload[0])
            if isinstance(payload, list) and payload[0] is not None
            else None
        ),
        angle=(
            float(payload[1])
            if isinstance(payload, list) and payload[1] is not None
            else None
        ),
        callback_phase_state=callback_phase,
        callback_aux_state=callback_aux,
        velocity_changes=changes,
        collision_state_changes=collision_changes,
        trajectory_uncertainty_x=uncertainty_x,
        trajectory_uncertainty_y=uncertainty_y,
        original_transform_flags=(
            int(payload[2]) if isinstance(payload, list) else 0
        ),
        native_state=(int(lifecycle[1]) if lifecycle is not None else 1),
        native_state_timer_elapsed=(
            int(lifecycle[2]) if lifecycle is not None else 0
        ),
    )


def hazards_from_trace(
    row: dict[str, object],
) -> tuple[tuple[Bullet, ...], tuple[Laser, ...], tuple[EnemyBody, ...]]:
    return (
        tuple(
            bullet_from_trace(values)
            for values in row.get("nearby_bullets", ())
        ),
        tuple(
            laser_from_trace(values)
            for values in row.get("lasers", ())
        ),
        tuple(
            EnemyBody(*values)
            for values in row.get("enemy_bodies", ())
        ),
    )


def local_pipeline_root_from_trace(
    row: dict[str, object],
) -> tuple[LocalPipelineRoot, int, int, bool]:
    """Parse and cross-check one directly retained shadow root, fail-closed."""

    record = row.get("local_pipeline_root")
    if not isinstance(record, dict):
        raise ValueError("local pipeline root record is not an object")
    if record.get("role") != "shadow_no_action_authority":
        raise ValueError("local pipeline root has unexpected authority role")
    if record.get("estimator_consistent") is not True:
        raise ValueError("local pipeline root estimator is inconsistent")

    active_action = record.get("active_action")
    held_action = record.get("held_desired_action")
    pending_action = record.get("pending_action")
    active_mask = record.get("active_mask")
    held_mask = record.get("held_desired_mask")
    pending_mask = record.get("pending_mask")
    if not isinstance(active_action, str) or not isinstance(held_action, str):
        raise ValueError("local pipeline root action names are invalid")
    if pending_action is not None and not isinstance(pending_action, str):
        raise ValueError("local pipeline pending action is invalid")
    if type(active_mask) is not int or type(held_mask) is not int:
        raise ValueError("local pipeline root masks are invalid")
    if (
        active_mask != active_mask & SUPPORTED_INPUT_MASK
        or held_mask != held_mask & SUPPORTED_INPUT_MASK
    ):
        raise ValueError("local pipeline root contains unsupported mask bits")

    input_snapshot = row.get("input_snapshot")
    if (
        not isinstance(input_snapshot, dict)
        or type(input_snapshot.get("current")) is not int
        or (
            int(input_snapshot["current"]) & SUPPORTED_INPUT_MASK
            != active_mask
        )
    ):
        raise ValueError("direct active mask disagrees with trace snapshot")
    if _local_pipeline_action_from_mask(active_mask) != active_action:
        raise ValueError("direct active mask/action disagree")
    if _local_pipeline_action_from_mask(held_mask) != held_action:
        raise ValueError("direct held mask/action disagree")

    remaining_raw = record.get("remaining_delay_support", ())
    if not isinstance(remaining_raw, (list, tuple)) or any(
        type(value) is not int for value in remaining_raw
    ):
        raise ValueError("direct remaining-delay support is invalid")
    remaining = tuple(int(value) for value in remaining_raw)
    if pending_action is None:
        if pending_mask is not None:
            raise ValueError("direct root has a mask without pending action")
        if active_mask != held_mask:
            raise ValueError(
                "direct no-pending root has different active/held masks"
            )
    elif (
        type(pending_mask) is not int
        or pending_mask != pending_mask & SUPPORTED_INPUT_MASK
        or pending_mask != held_mask
        or _local_pipeline_action_from_mask(pending_mask) != pending_action
    ):
        raise ValueError("direct pending mask/action disagree")

    root = LocalPipelineRoot(
        active_action=active_action,
        held_desired_action=held_action,
        pending_action=pending_action,
        remaining_delay_support=remaining,
        input_publication_to_motion_lag_frames=(
            TH08_INPUT_PUBLICATION_TO_MOTION_LAG_FRAMES
        ),
    )
    issue_age_raw = record.get("issue_age")
    if issue_age_raw is None:
        issue_age = 0
    elif type(issue_age_raw) is int and issue_age_raw >= 0:
        issue_age = int(issue_age_raw)
    else:
        raise ValueError("direct issue age is invalid")
    overdue = record.get("overdue", False)
    if not isinstance(overdue, bool):
        raise ValueError("direct overdue flag is invalid")
    return root, held_mask, issue_age, overdue


__all__ = [
    "bullet_from_trace",
    "hazards_from_trace",
    "laser_from_trace",
    "local_pipeline_root_from_trace",
]
