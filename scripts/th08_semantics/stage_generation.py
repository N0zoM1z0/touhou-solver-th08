"""Seeded, unbounded composition of complete source-stateful TH08 stages."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from th08_semantics.stage import (
    BulletEmitter,
    Callback12Event,
    LaserSpawnEvent,
    StagePhase,
    StageProgram,
    TRANSFORM_ANGULAR_VELOCITY,
    TRANSFORM_DECELERATE,
    TRANSFORM_REFLECT_ALL,
    TRANSFORM_REFLECT_SIDES_TOP,
    TRANSFORM_STOP_REAIM,
    TRANSFORM_STOP_SNAP,
    TRANSFORM_STOP_TURN,
    TRANSFORM_VECTOR_ACCELERATION,
    TransformSpec,
)


@dataclass(frozen=True)
class StageGenerationProfile:
    name: str
    frame_count: int
    phase_count: int
    emitters_per_phase: int
    lasers_per_phase: int
    interval_min: int
    interval_max: int
    count1_min: int
    count1_max: int
    count2_max: int
    transform_probability: float


STAGE_PROFILES = {
    "quick": StageGenerationProfile(
        "quick", 480, 4, 3, 2, 7, 18, 8, 28, 2, 0.45
    ),
    "gate": StageGenerationProfile(
        "gate", 3600, 12, 4, 5, 3, 12, 18, 64, 3, 0.68
    ),
    "research": StageGenerationProfile(
        "research", 7200, 18, 5, 8, 2, 8, 28, 96, 4, 0.78
    ),
    # Birth pressure intentionally saturates the real 1,536/256 pools.  This
    # is denser than shipped Lunatic while retaining native pool semantics.
    "extreme": StageGenerationProfile(
        "extreme", 12000, 24, 7, 14, 1, 5, 48, 160, 5, 0.88
    ),
}

_TAGS = (0x100000, 0x200000, 0x400000, 0x800000)
_TRANSFORM_KINDS = (
    TRANSFORM_DECELERATE,
    TRANSFORM_VECTOR_ACCELERATION,
    TRANSFORM_ANGULAR_VELOCITY,
    TRANSFORM_STOP_TURN,
    TRANSFORM_STOP_REAIM,
    TRANSFORM_STOP_SNAP,
    TRANSFORM_REFLECT_ALL,
    TRANSFORM_REFLECT_SIDES_TOP,
)


def _mixed_seed(seed: int) -> int:
    value = seed & 0xFFFFFFFFFFFFFFFF
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return value ^ (value >> 31)


def _transform_for_kind(
    generator: random.Random,
    kind: int,
) -> TransformSpec:
    if kind == TRANSFORM_DECELERATE:
        return TransformSpec(kind=kind, duration=17)
    if kind == TRANSFORM_VECTOR_ACCELERATION:
        return TransformSpec(
            kind=kind,
            duration=generator.randint(30, 150),
            float_0=generator.uniform(-0.045, 0.065),
            float_1=generator.uniform(-math.pi, math.pi),
        )
    if kind == TRANSFORM_ANGULAR_VELOCITY:
        return TransformSpec(
            kind=kind,
            duration=generator.randint(45, 190),
            float_0=generator.uniform(-0.012, 0.025),
            float_1=generator.uniform(-0.045, 0.045),
        )
    if kind in (
        TRANSFORM_STOP_TURN,
        TRANSFORM_STOP_REAIM,
        TRANSFORM_STOP_SNAP,
    ):
        return TransformSpec(
            kind=kind,
            duration=generator.randint(18, 80),
            repeat_limit=generator.randint(1, 4),
            float_0=generator.uniform(-math.pi, math.pi),
            float_1=generator.uniform(0.7, 4.5),
        )
    return TransformSpec(
        kind=kind,
        duration=0,
        repeat_limit=generator.randint(1, 5),
        float_0=generator.choice((-1.0, generator.uniform(0.6, 4.5))),
    )


def _transform_queue(
    generator: random.Random,
    *,
    probability: float,
    selector: int,
) -> tuple[TransformSpec, ...]:
    if generator.random() >= probability:
        return ()
    first = _TRANSFORM_KINDS[selector % len(_TRANSFORM_KINDS)]
    queue = [_transform_for_kind(generator, first)]
    # Sequential queues exercise the source wait-for-active-clear gate. Keep
    # kinds unique so their native per-kind runtime fields never alias.
    if generator.random() < probability * 0.45:
        second = _TRANSFORM_KINDS[(selector + 3) % len(_TRANSFORM_KINDS)]
        if second != first:
            queue.append(_transform_for_kind(generator, second))
    return tuple(queue)


def _phase_bounds(
    frame_count: int,
    phase_count: int,
    phase_index: int,
) -> tuple[int, int]:
    start = frame_count * phase_index // phase_count
    end = frame_count * (phase_index + 1) // phase_count - 1
    return start, end


def generate_stage_program(*, seed: int, profile: str) -> StageProgram:
    """Generate a complete replayable stage from an effectively unbounded seed."""

    try:
        limits = STAGE_PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"unknown source-stage profile {profile!r}") from exc
    generator = random.Random(_mixed_seed(seed) ^ 0xCE0132A5)
    phases: list[StagePhase] = []
    emitter_serial = 0
    for phase_index in range(limits.phase_count):
        start, end = _phase_bounds(
            limits.frame_count,
            limits.phase_count,
            phase_index,
        )
        phase_duration = end - start + 1
        emitters: list[BulletEmitter] = []
        phase_tags: set[int] = set()
        for local_index in range(limits.emitters_per_phase):
            mode = emitter_serial % 9
            emitter_serial += 1
            tag = _TAGS[(phase_index + local_index) % len(_TAGS)]
            phase_tags.add(tag)
            margin = max(2, phase_duration // 20)
            emitter_start = start + generator.randint(0, margin)
            emitter_end = end - generator.randint(0, margin)
            interval = generator.randint(
                limits.interval_min,
                limits.interval_max,
            )
            count1 = generator.randint(
                limits.count1_min,
                limits.count1_max,
            )
            # Preserve parity diversity for fan modes.
            if local_index & 1:
                count1 |= 1
            else:
                count1 += count1 & 1
            count2 = generator.randint(1, limits.count2_max)
            origin_x = generator.uniform(56.0, 328.0)
            origin_y = generator.uniform(24.0, 152.0)
            emitters.append(
                BulletEmitter(
                    emitter_id=f"p{phase_index:02d}-e{local_index:02d}-m{mode}",
                    start_frame=emitter_start,
                    end_frame=max(emitter_start, emitter_end),
                    interval=interval,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    origin_velocity_x=generator.uniform(-0.12, 0.12),
                    origin_velocity_y=generator.uniform(-0.04, 0.08),
                    origin_wave_x=generator.uniform(0.0, 72.0),
                    origin_wave_y=generator.uniform(0.0, 30.0),
                    origin_wave_step=generator.uniform(-0.22, 0.22),
                    mode=mode,
                    count1=count1,
                    count2=count2,
                    speed1=generator.uniform(1.0, 6.8),
                    speed2=generator.uniform(0.25, 3.4),
                    angle=generator.uniform(-math.pi, math.pi),
                    angle_step=generator.uniform(-0.32, 0.32),
                    angle_per_emission=generator.uniform(-0.15, 0.15),
                    tag_flags=tag,
                    half_width=generator.uniform(1.5, 7.0),
                    half_height=generator.uniform(1.5, 7.0),
                    transforms=_transform_queue(
                        generator,
                        probability=limits.transform_probability,
                        selector=phase_index * limits.emitters_per_phase
                        + local_index,
                    ),
                )
            )

        callbacks: list[Callback12Event] = []
        for tag_index, tag in enumerate(sorted(phase_tags)):
            first = start + phase_duration * (2 + tag_index) // 7
            second = start + phase_duration * (5 + tag_index) // 8
            if second <= first:
                second = min(end, first + 1)
            callbacks.extend(
                (
                    Callback12Event(
                        frame=min(end, first),
                        tag_mask=tag,
                        angle=generator.uniform(-math.pi, math.pi),
                        speed=generator.uniform(0.0, 3.8),
                    ),
                    Callback12Event(
                        frame=min(end, second),
                        tag_mask=tag,
                        angle=generator.uniform(-math.pi, math.pi),
                        speed=generator.uniform(0.0, 5.2),
                    ),
                )
            )
        callbacks.sort(key=lambda event: (event.frame, event.tag_mask))

        lasers: list[LaserSpawnEvent] = []
        for laser_index in range(limits.lasers_per_phase):
            laser_frame = start + (
                (laser_index + 1) * phase_duration
                // (limits.lasers_per_phase + 1)
            )
            aimed = math.atan2(
                400.0 - generator.uniform(40.0, 150.0),
                192.0 - generator.uniform(40.0, 344.0),
            )
            lasers.append(
                LaserSpawnEvent(
                    frame=min(end, laser_frame),
                    origin_x=generator.uniform(40.0, 344.0),
                    origin_y=generator.uniform(32.0, 150.0),
                    angle=aimed + generator.uniform(-0.8, 0.8),
                    speed=generator.uniform(2.0, 10.0),
                    tail=generator.uniform(-32.0, 24.0),
                    head=generator.uniform(0.0, 64.0),
                    maximum_length=generator.uniform(220.0, 760.0),
                    width=generator.uniform(8.0, 40.0),
                    warmup_frames=generator.randint(12, 45),
                    active_frames=generator.randint(45, 150),
                    fade_frames=generator.randint(12, 40),
                    collision_enable_frame=generator.randint(2, 10),
                    collision_disable_frame=generator.randint(4, 18),
                    flags=laser_index & 1,
                )
            )

        phases.append(
            StagePhase(
                name=f"generated-phase-{phase_index:02d}",
                start_frame=start,
                end_frame=end,
                clear_at_start=True,
                emitters=tuple(emitters),
                callbacks=tuple(callbacks),
                lasers=tuple(lasers),
            )
        )

    return StageProgram(
        seed=seed,
        profile=profile,
        frame_count=limits.frame_count,
        gameplay_rng_seed=_mixed_seed(seed ^ 0x5A17E) & 0xFFFF,
        phases=tuple(phases),
    )


__all__ = [
    "STAGE_PROFILES",
    "StageGenerationProfile",
    "generate_stage_program",
]
