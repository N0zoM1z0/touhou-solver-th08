"""Lockstep stage differential against the separately compiled C kernels."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from th08_semantics.native_oracle import NativeSourceOracle
from th08_semantics.stage import StageProgram, StageRuntime


_BINARY32_MIN_NORMAL = math.ldexp(1.0, -126)
_BINARY32_MIN_SUBNORMAL = math.ldexp(1.0, -149)


def _binary32_spacing(value: float) -> float:
    """Return a conservative adjacent-float spacing at a finite value."""

    magnitude = abs(value)
    if magnitude < _BINARY32_MIN_NORMAL:
        return _BINARY32_MIN_SUBNORMAL
    _, exponent = math.frexp(magnitude)
    return math.ldexp(1.0, exponent - 24)


@dataclass(frozen=True)
class StageSourceDifferentialResult:
    identity: str
    frames_compared: int
    passed: bool
    first_mismatch: str | None
    maximum_position_error: float
    maximum_non_lifecycle_position_error: float
    maximum_velocity_error: float
    maximum_callback_velocity_error: float
    lifecycle_samples_compared: int
    maximum_lifecycle_position_error: float
    final_rng_state_equal: bool
    final_rng_calls_equal: bool

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def compare_stage_with_c_source_oracle(
    program: StageProgram,
    *,
    oracle: NativeSourceOracle | None = None,
) -> StageSourceDifferentialResult:
    """Compare every reached spawn/callback while retaining full history."""

    native = oracle or NativeSourceOracle.load()

    def native_pattern(pattern, bullet_index, ring_index, rng):
        return native.pattern_sample(
            pattern,
            bullet_index=bullet_index,
            ring_index=ring_index,
            rng=rng,
        )

    reference = StageRuntime(program)
    candidate = StageRuntime(
        program,
        pattern_sampler=native_pattern,
        callback12_applier=native.callback12,
        callback14_applier=native.callback14,
    )
    first_mismatch: str | None = None
    maximum_position_error = 0.0
    maximum_non_lifecycle_position_error = 0.0
    maximum_velocity_error = 0.0
    maximum_callback_velocity_error = 0.0
    lifecycle_samples_compared = 0
    maximum_lifecycle_position_error = 0.0
    # Python uses double-libm sin/cos followed by a binary32 store; the C
    # source oracle calls the host sinf/cosf.  A one-ULP velocity difference
    # can cause the two binary32 position additions to round differently on
    # every later frame.  Carry the actual velocity disagreement plus one
    # coordinate ULP per update instead of using an empirical age threshold.
    position_budgets: dict[int, tuple[str, int, float]] = {}
    frames = 0
    while not reference.complete and first_mismatch is None:
        reference_step = reference.step()
        candidate_step = candidate.step()
        frames += 1
        if (
            reference_step.births_requested
            != candidate_step.births_requested
            or reference_step.birth_allocation_calls
            != candidate_step.birth_allocation_calls
            or reference_step.births_allocated
            != candidate_step.births_allocated
            or reference_step.births_suppressed_by_pool
            != candidate_step.births_suppressed_by_pool
            or reference_step.callback_changes
            != candidate_step.callback_changes
            or reference_step.callback12_changes
            != candidate_step.callback12_changes
            or reference_step.callback14_changes
            != candidate_step.callback14_changes
            or reference_step.callback14_reactivated_slots
            != candidate_step.callback14_reactivated_slots
            or reference_step.spawn_lifecycle_activations
            != candidate_step.spawn_lifecycle_activations
            or reference_step.transform_activations
            != candidate_step.transform_activations
            or reference_step.active_bullets
            != candidate_step.active_bullets
            or reference_step.active_lasers
            != candidate_step.active_lasers
        ):
            first_mismatch = f"frame={reference_step.frame}:step_discrete"
            break
        if (
            reference.rng.state != candidate.rng.state
            or reference.rng.calls != candidate.rng.calls
        ):
            first_mismatch = f"frame={reference_step.frame}:gameplay_rng"
            break
        if (
            reference_step.bullet_collision_slots
            != candidate_step.bullet_collision_slots
            or reference_step.laser_collision_slots
            != candidate_step.laser_collision_slots
        ):
            first_mismatch = f"frame={reference_step.frame}:collision_membership"
            break
        for slot, (left, right) in enumerate(
            zip(reference.bullets, candidate.bullets)
        ):
            if (left is None) != (right is None):
                first_mismatch = f"frame={reference_step.frame}:slot={slot}:occupancy"
                break
            if left is None or right is None:
                position_budgets.pop(slot, None)
                continue
            if (
                left.source != right.source
                or left.tag_flags != right.tag_flags
                or left.bullet_type != right.bullet_type
                or left.spawn_flags != right.spawn_flags
                or left.native_state != right.native_state
                or left.native_state_age != right.native_state_age
                or left.phase_state != right.phase_state
                or left.collision_aux != right.collision_aux
                or left.transform_cursor != right.transform_cursor
                or left.active_transform_flags != right.active_transform_flags
                or {
                    kind: (runtime.timer, runtime.repeat_count)
                    for kind, runtime in left.active_transforms.items()
                }
                != {
                    kind: (runtime.timer, runtime.repeat_count)
                    for kind, runtime in right.active_transforms.items()
                }
            ):
                first_mismatch = f"frame={reference_step.frame}:slot={slot}:state"
                break
            if right.spawn_lifecycle is not None:
                if right.bullet_type is None:
                    first_mismatch = (
                        f"frame={reference_step.frame}:slot={slot}:"
                        "lifecycle_type"
                    )
                    break
                authority = native.spawn_lifecycle_sample(
                    bullet_type=right.bullet_type,
                    original_flags=right.spawn_flags,
                    age=right.age,
                    origin_x=right.spawn_origin_x,
                    origin_y=right.spawn_origin_y,
                    velocity_x=right.initial_velocity_x,
                    velocity_y=right.initial_velocity_y,
                )
                lifecycle_position_error = max(
                    abs(right.x - authority.x),
                    abs(right.y - authority.y),
                )
                lifecycle_samples_compared += 1
                maximum_lifecycle_position_error = max(
                    maximum_lifecycle_position_error,
                    lifecycle_position_error,
                )
                if (
                    right.native_state != authority.state
                    or lifecycle_position_error > 1.0e-5
                ):
                    first_mismatch = (
                        f"frame={reference_step.frame}:slot={slot}:"
                        "lifecycle_oracle:"
                        f"state={right.native_state}/{authority.state}:"
                        f"position={lifecycle_position_error}"
                    )
                    break
            position_error = max(
                abs(left.x - right.x),
                abs(left.y - right.y),
            )
            velocity_error = max(
                abs(left.velocity_x - right.velocity_x),
                abs(left.velocity_y - right.velocity_y),
            )
            speed_error = abs(left.base_speed - right.base_speed)
            angle_error = abs(
                (left.base_angle - right.base_angle + math.pi)
                % (2.0 * math.pi)
                - math.pi
            )
            maximum_position_error = max(
                maximum_position_error,
                position_error,
            )
            if left.spawn_lifecycle is None:
                maximum_non_lifecycle_position_error = max(
                    maximum_non_lifecycle_position_error,
                    position_error,
                )
            maximum_velocity_error = max(
                maximum_velocity_error,
                velocity_error,
            )
            if reference_step.callback_changes:
                maximum_callback_velocity_error = max(
                    maximum_callback_velocity_error,
                    velocity_error,
                )
            # Separate libm sin/cos versus sinf/cosf approximations can differ
            # by a binary32 ULP. Propagate only the forward error admitted by
            # the observed velocity difference and binary32 addition. A slot
            # reuse resets the budget. Collision membership, discrete state,
            # and RNG remain exact requirements.
            previous = position_budgets.get(slot)
            if (
                previous is None
                or previous[0] != left.source
                or left.age <= previous[1]
            ):
                position_tolerance = 0.0
            else:
                position_tolerance = previous[2]
            position_tolerance += velocity_error + max(
                _binary32_spacing(left.x),
                _binary32_spacing(left.y),
                _binary32_spacing(right.x),
                _binary32_spacing(right.y),
            )
            position_budgets[slot] = (
                left.source,
                left.age,
                position_tolerance,
            )
            if (
                position_error > position_tolerance
                or velocity_error > 2.0e-5
                or speed_error > 2.0e-5
                or angle_error > 2.0e-5
            ):
                first_mismatch = (
                    f"frame={reference_step.frame}:slot={slot}:numeric:"
                    f"position={position_error}:"
                    f"position_tolerance={position_tolerance}:"
                    f"velocity={velocity_error}"
                )
                break

    return StageSourceDifferentialResult(
        identity=program.identity,
        frames_compared=frames,
        passed=first_mismatch is None and reference.complete and candidate.complete,
        first_mismatch=first_mismatch,
        maximum_position_error=maximum_position_error,
        maximum_non_lifecycle_position_error=(
            maximum_non_lifecycle_position_error
        ),
        maximum_velocity_error=maximum_velocity_error,
        maximum_callback_velocity_error=maximum_callback_velocity_error,
        lifecycle_samples_compared=lifecycle_samples_compared,
        maximum_lifecycle_position_error=(
            maximum_lifecycle_position_error
        ),
        final_rng_state_equal=reference.rng.state == candidate.rng.state,
        final_rng_calls_equal=reference.rng.calls == candidate.rng.calls,
    )


__all__ = [
    "StageSourceDifferentialResult",
    "compare_stage_with_c_source_oracle",
]
