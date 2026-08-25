#!/usr/bin/env python3
"""Long-history gates for the source-stateful stage generator/runtime."""

from __future__ import annotations

import json
import unittest

from th08_semantics.stage import (
    BULLET_POOL_SIZE,
    BulletEmitter,
    Callback12Event,
    StagePhase,
    StageProgram,
    StageRuntime,
)
from th08_semantics.stage_generation import generate_stage_program


def _emitter(
    *,
    emitter_id: str = "fixture",
    start: int = 0,
    end: int = 0,
    mode: int = 3,
    count1: int = 1,
    count2: int = 1,
    tag: int = 0x100000,
) -> BulletEmitter:
    return BulletEmitter(
        emitter_id=emitter_id,
        start_frame=start,
        end_frame=end,
        interval=1,
        origin_x=192.0,
        origin_y=100.0,
        origin_velocity_x=0.0,
        origin_velocity_y=0.0,
        origin_wave_x=0.0,
        origin_wave_y=0.0,
        origin_wave_step=0.0,
        mode=mode,
        count1=count1,
        count2=count2,
        speed1=0.0,
        speed2=0.0,
        angle=0.0,
        angle_step=0.0,
        angle_per_emission=0.0,
        tag_flags=tag,
        half_width=2.0,
        half_height=2.0,
    )


class SourceStatefulStageTests(unittest.TestCase):
    def test_callback_history_is_derived_instead_of_randomized_snapshot(self) -> None:
        program = StageProgram(
            seed=1,
            profile="fixture",
            frame_count=3,
            gameplay_rng_seed=0x1234,
            phases=(
                StagePhase(
                    name="phase",
                    start_frame=0,
                    end_frame=2,
                    clear_at_start=True,
                    emitters=(_emitter(),),
                    callbacks=(
                        Callback12Event(1, 0x100000, 1.0, 2.0),
                        Callback12Event(2, 0x100000, -1.0, 3.0),
                    ),
                    lasers=(),
                ),
            ),
        )
        runtime = StageRuntime(program)

        runtime.step()
        bullet = next(value for value in runtime.bullets if value is not None)
        self.assertEqual((bullet.phase_state, bullet.collision_aux), (0, 0))
        runtime.step()
        self.assertEqual((bullet.phase_state, bullet.collision_aux), (1, 0))
        runtime.step()
        self.assertEqual((bullet.phase_state, bullet.collision_aux), (0, 1))
        self.assertEqual(runtime.metrics.callback_changes, 2)

    def test_pool_exhaustion_does_not_consume_rejected_random_pattern_rng(
        self,
    ) -> None:
        program = StageProgram(
            seed=2,
            profile="fixture",
            frame_count=1,
            gameplay_rng_seed=0xBEEF,
            phases=(
                StagePhase(
                    name="phase",
                    start_frame=0,
                    end_frame=0,
                    clear_at_start=True,
                    emitters=(
                        _emitter(
                            emitter_id="fills-pool",
                            mode=8,
                            count1=BULLET_POOL_SIZE,
                        ),
                        _emitter(
                            emitter_id="must-not-consume-rng",
                            mode=8,
                            count1=64,
                        ),
                    ),
                    callbacks=(),
                    lasers=(),
                ),
            ),
        )
        runtime = StageRuntime(program)

        step = runtime.step()

        self.assertEqual(step.active_bullets, BULLET_POOL_SIZE)
        # Mode 8 consumes two U32 / four U16 values per accepted bullet.
        self.assertEqual(runtime.rng.calls, BULLET_POOL_SIZE * 4)
        self.assertEqual(step.births_allocated, BULLET_POOL_SIZE)
        self.assertEqual(step.births_dropped, 64)

    def test_generated_stage_replay_is_canonical_and_seeded(self) -> None:
        first = generate_stage_program(seed=0xCE0132, profile="quick")
        second = generate_stage_program(seed=0xCE0132, profile="quick")
        different = generate_stage_program(seed=0xCE0133, profile="quick")

        self.assertEqual(first, second)
        self.assertEqual(first.digest, second.digest)
        self.assertNotEqual(first.digest, different.digest)
        replay = StageProgram.from_payload(
            json.loads(json.dumps(first.to_payload()))
        )
        self.assertEqual(replay, first)
        self.assertEqual(replay.digest, first.digest)
        self.assertTrue(replay.source_closed)
        self.assertEqual(
            {emitter.mode for phase in replay.phases for emitter in phase.emitters},
            set(range(9)),
        )

    def test_complete_quick_stage_exercises_long_transition_history(self) -> None:
        program = generate_stage_program(seed=0xCE0132, profile="quick")
        first = StageRuntime(program)
        second = StageRuntime(program)
        while not first.complete:
            first.step()
            second.step()

        self.assertEqual(first.frame, program.frame_count)
        self.assertEqual(first.state_digest(), second.state_digest())
        self.assertGreater(first.metrics.births_attempted, 4000)
        self.assertGreater(first.metrics.max_active_bullets, 1200)
        self.assertGreater(first.metrics.callback_changes, 1000)
        self.assertGreater(first.metrics.transform_activations, 500)
        self.assertGreater(first.metrics.laser_spawns, 0)
        self.assertEqual(first.metrics.clear_events, len(program.phases))
        self.assertGreater(first.metrics.raw_bullet_collisions, 0)

    def test_runtime_refuses_unknown_source_semantics(self) -> None:
        program = generate_stage_program(seed=9, profile="quick")
        unknown = StageProgram(
            seed=program.seed,
            profile=program.profile,
            frame_count=program.frame_count,
            gameplay_rng_seed=program.gameplay_rng_seed,
            phases=program.phases,
            source_unknowns=("unmodeled_callback_7",),
        )
        with self.assertRaisesRegex(ValueError, "UNKNOWN"):
            StageRuntime(unknown)


if __name__ == "__main__":
    unittest.main()
