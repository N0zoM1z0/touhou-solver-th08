#!/usr/bin/env python3
"""Long-history gates for the source-stateful stage generator/runtime."""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import unittest

from th08_semantics.stage import (
    BULLET_POOL_SIZE,
    LIFECYCLE_STAGE_SCHEMA,
    STAGE_SCHEMA,
    BulletEmitter,
    Callback12Event,
    StagePhase,
    StageProgram,
    StageRuntime,
)
from th08_semantics.stage_generation import generate_stage_program
from th08_semantics.stage_differential import (
    _binary32_spacing,
    compare_stage_with_c_source_oracle,
)
from th08_semantics.stage_shrink import shrink_stage_program


ROOT = Path(__file__).resolve().parents[1]


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
    def test_source_differential_uses_binary32_position_spacing(self) -> None:
        self.assertEqual(_binary32_spacing(0.0), math.ldexp(1.0, -149))
        self.assertEqual(_binary32_spacing(1.0), math.ldexp(1.0, -23))
        self.assertEqual(_binary32_spacing(388.0), math.ldexp(1.0, -15))

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
        self.assertEqual(step.births_suppressed_by_pool, 64)
        self.assertEqual(
            step.birth_allocation_calls,
            BULLET_POOL_SIZE + 1,
        )

    def test_generated_stage_replay_is_canonical_and_seeded(self) -> None:
        first = generate_stage_program(seed=0xCE0132, profile="quick")
        second = generate_stage_program(seed=0xCE0132, profile="quick")
        different = generate_stage_program(seed=0xCE0133, profile="quick")

        self.assertEqual(first, second)
        self.assertEqual(first.schema, LIFECYCLE_STAGE_SCHEMA)
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

        downgraded = replay.to_payload()
        downgraded.pop("sha256")
        downgraded["schema"] = STAGE_SCHEMA
        with self.assertRaisesRegex(ValueError, "lifecycle features"):
            StageProgram.from_payload(downgraded)

    def test_tracked_v1_gate_program_remains_replayable(self) -> None:
        report = json.loads(
            (
                ROOT
                / "artifacts/benchmarks/"
                "th08_source_stage_fuzzer_gate_20260825.json"
            ).read_text(encoding="utf-8")
        )
        payload = report["cases"][0]["program"]
        program = StageProgram.from_payload(payload)

        self.assertEqual(program.schema, STAGE_SCHEMA)
        self.assertEqual(program.digest, payload["sha256"])

    def test_extreme_generator_covers_all_generic_lifecycle_types(self) -> None:
        program = generate_stage_program(seed=0xCE0132, profile="extreme")
        lifecycle_emitters = tuple(
            emitter
            for phase in program.phases
            for emitter in phase.emitters
            if emitter.spawn_flags
        )

        self.assertEqual(
            {emitter.bullet_type for emitter in lifecycle_emitters},
            set(range(21)),
        )
        self.assertEqual(
            {emitter.spawn_flags for emitter in lifecycle_emitters},
            {0x02, 0x04, 0x08},
        )

    def test_lifecycle_payload_rejects_noncanonical_operands(self) -> None:
        program = generate_stage_program(seed=0xCE0132, profile="quick")
        for malformed in ([7], [7, 2, 0], [7.0, 2], [7, True], "7,2"):
            with self.subTest(malformed=malformed):
                payload = program.to_payload()
                payload.pop("sha256")
                emitter = payload["phases"][0]["emitters"][0]
                emitter["spawn_lifecycle"] = malformed
                with self.assertRaisesRegex(ValueError, "spawn_lifecycle"):
                    StageProgram.from_payload(payload)

    def test_complete_quick_stage_exercises_long_transition_history(self) -> None:
        program = generate_stage_program(seed=0xCE0132, profile="quick")
        first = StageRuntime(program)
        second = StageRuntime(program)
        while not first.complete:
            first.step()
            second.step()

        self.assertEqual(first.frame, program.frame_count)
        self.assertEqual(first.state_digest(), second.state_digest())
        self.assertGreater(first.metrics.births_requested, 4000)
        self.assertGreater(first.metrics.max_active_bullets, 1200)
        self.assertGreater(first.metrics.callback_changes, 1000)
        self.assertGreater(first.metrics.spawn_lifecycle_activations, 0)
        self.assertGreater(first.metrics.transform_activations, 500)
        self.assertGreater(first.metrics.laser_spawns, 0)
        self.assertEqual(first.metrics.clear_events, len(program.phases))
        self.assertGreater(first.metrics.raw_bullet_collisions, 0)

    def test_complete_history_matches_tracked_c_spawn_and_callback_oracle(
        self,
    ) -> None:
        result = compare_stage_with_c_source_oracle(
            generate_stage_program(seed=0xCE0132, profile="quick")
        )

        self.assertTrue(result.passed, result.first_mismatch)
        self.assertEqual(result.frames_compared, 480)
        self.assertTrue(result.final_rng_state_equal)
        self.assertTrue(result.final_rng_calls_equal)
        self.assertLess(result.maximum_non_lifecycle_position_error, 1.0e-4)
        self.assertGreater(result.lifecycle_samples_compared, 0)
        self.assertLessEqual(result.maximum_lifecycle_position_error, 1.0e-5)

    def test_spawn_lifecycle_is_nonlethal_until_same_update_activation(
        self,
    ) -> None:
        lifecycle_emitter = _emitter(
            tag=0,
            start=0,
            end=0,
        )
        lifecycle_emitter = replace(
            lifecycle_emitter,
            speed1=2.0,
            speed2=2.0,
            half_width=5.0,
            half_height=5.0,
            bullet_type=7,
            spawn_flags=0x02,
        )
        program = StageProgram(
            seed=3,
            profile="lifecycle-fixture",
            frame_count=30,
            gameplay_rng_seed=1,
            phases=(
                StagePhase(
                    name="phase",
                    start_frame=0,
                    end_frame=29,
                    clear_at_start=True,
                    emitters=(lifecycle_emitter,),
                    callbacks=(),
                    lasers=(),
                ),
            ),
        )
        runtime = StageRuntime(program)

        for _frame in range(29):
            step = runtime.step(player_x=213.0, player_y=100.0)
            self.assertEqual(step.bullet_collision_slots, ())
            self.assertEqual(step.spawn_lifecycle_activations, 0)
        terminal = runtime.step(player_x=213.0, player_y=100.0)
        bullet = next(value for value in runtime.bullets if value is not None)
        self.assertEqual(bullet.native_state, 1)
        self.assertEqual(bullet.age, 30)
        self.assertEqual(terminal.spawn_lifecycle_activations, 1)
        self.assertEqual(terminal.bullet_collision_slots, (bullet.slot,))

    def test_mixed_lifecycle_flags_use_native_state2_priority(self) -> None:
        lifecycle_emitter = replace(
            _emitter(tag=0, start=0, end=0),
            half_width=12.0,
            half_height=12.0,
            bullet_type=10,
            spawn_flags=0x0E,
        )
        program = StageProgram(
            seed=4,
            profile="lifecycle-priority-fixture",
            frame_count=24,
            gameplay_rng_seed=1,
            phases=(
                StagePhase(
                    name="phase",
                    start_frame=0,
                    end_frame=23,
                    clear_at_start=True,
                    emitters=(lifecycle_emitter,),
                    callbacks=(),
                    lasers=(),
                ),
            ),
        )
        runtime = StageRuntime(program)

        for _frame in range(23):
            step = runtime.step()
            self.assertEqual(step.spawn_lifecycle_activations, 0)
        terminal = runtime.step()
        bullet = next(value for value in runtime.bullets if value is not None)
        self.assertEqual(bullet.spawn_lifecycle.state, 2)
        self.assertEqual(bullet.spawn_lifecycle.terminal_age, 24)
        self.assertEqual(terminal.spawn_lifecycle_activations, 1)

    def test_lifecycle_composition_fails_closed_before_audited(self) -> None:
        with self.assertRaisesRegex(ValueError, "callbacks/transforms"):
            replace(
                _emitter(tag=0x100000),
                half_width=5.0,
                half_height=5.0,
                bullet_type=7,
                spawn_flags=0x02,
            )

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

    def test_stage_shrinker_removes_unrelated_complete_history(self) -> None:
        program = generate_stage_program(seed=0xDDF00D, profile="quick")
        witness = program.phases[2].emitters[1].emitter_id

        def fails(candidate: StageProgram) -> bool:
            return any(
                emitter.emitter_id == witness
                for phase in candidate.phases
                for emitter in phase.emitters
            )

        reduced, attempts = shrink_stage_program(
            program,
            fails=fails,
            maximum_attempts=256,
        )

        self.assertGreater(attempts, 0)
        self.assertTrue(fails(reduced))
        self.assertLess(
            sum(len(phase.emitters) for phase in reduced.phases),
            sum(len(phase.emitters) for phase in program.phases),
        )
        # The reducer never breaks complete-stage or source-closure contracts.
        self.assertEqual(reduced.frame_count, program.frame_count)
        self.assertTrue(reduced.source_closed)


if __name__ == "__main__":
    unittest.main()
