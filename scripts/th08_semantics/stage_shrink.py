"""Deterministic delta debugging for source-stateful stage programs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import math

from th08_semantics.stage import StagePhase, StageProgram


def _ddmin(
    values: tuple[object, ...],
    *,
    update: Callable[[tuple[object, ...]], StageProgram],
    fails: Callable[[StageProgram], bool],
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


def _replace_phase(
    program: StageProgram,
    index: int,
    phase: StagePhase,
) -> StageProgram:
    phases = list(program.phases)
    phases[index] = phase
    return replace(program, phases=tuple(phases))


def shrink_stage_program(
    program: StageProgram,
    *,
    fails: Callable[[StageProgram], bool],
    maximum_attempts: int = 512,
) -> tuple[StageProgram, int]:
    """Remove phase content and simplify producers while failure persists."""

    if maximum_attempts <= 0 or not fails(program):
        return program, 0
    current = program
    attempts = [0]

    def retain(candidate: StageProgram) -> bool:
        nonlocal current
        if attempts[0] >= maximum_attempts or candidate == current:
            return False
        attempts[0] += 1
        if not fails(candidate):
            return False
        current = candidate
        return True

    for phase_index in range(len(current.phases)):
        for field_name in ("emitters", "callbacks", "lasers"):
            if attempts[0] >= maximum_attempts:
                return current, attempts[0]
            values = getattr(current.phases[phase_index], field_name)

            def update(
                reduced: tuple[object, ...],
                *,
                index: int = phase_index,
                field: str = field_name,
            ) -> StageProgram:
                phase = replace(
                    current.phases[index],
                    **{field: tuple(reduced)},
                )
                return _replace_phase(current, index, phase)

            reduced = _ddmin(
                tuple(values),
                update=update,
                fails=fails,
                attempts=attempts,
                maximum_attempts=maximum_attempts,
            )
            current = update(reduced)

    for phase_index in range(len(current.phases)):
        for emitter_index in range(len(current.phases[phase_index].emitters)):
            if attempts[0] >= maximum_attempts:
                return current, attempts[0]

            def retain_emitter(**changes: object) -> None:
                phase = current.phases[phase_index]
                emitters = list(phase.emitters)
                emitters[emitter_index] = replace(
                    emitters[emitter_index],
                    **changes,
                )
                retain(
                    _replace_phase(
                        current,
                        phase_index,
                        replace(phase, emitters=tuple(emitters)),
                    )
                )

            emitter = current.phases[phase_index].emitters[emitter_index]
            retain_emitter(transforms=())
            emitter = current.phases[phase_index].emitters[emitter_index]
            retain_emitter(count1=1, count2=1)
            emitter = current.phases[phase_index].emitters[emitter_index]
            retain_emitter(
                interval=max(
                    emitter.interval,
                    emitter.end_frame - emitter.start_frame + 1,
                )
            )
            retain_emitter(
                origin_velocity_x=0.0,
                origin_velocity_y=0.0,
                origin_wave_x=0.0,
                origin_wave_y=0.0,
                origin_wave_step=0.0,
                angle_per_emission=0.0,
            )
            retain_emitter(speed1=0.0, speed2=0.0)

    return current, attempts[0]


__all__ = ["shrink_stage_program"]
