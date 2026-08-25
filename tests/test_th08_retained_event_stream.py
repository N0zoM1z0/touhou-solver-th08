"""Gates for generic retained-root to resolved-event-stream lowering."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from th08_future_birth_envelope import FloatInterval, FutureDirectFire
from th08_semantics.retained_event_stream import (
    RetainedEventStreamError,
    import_retained_future_event_stream,
    resolved_direct_fire_stage_program,
)
from th08_semantics.source_primitives import f32
from th08_semantics.stage import (
    RESOLVED_AIM_STAGE_SCHEMA,
    STAGE_SCHEMA,
    StageProgram,
    StageRuntime,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = (
    ROOT
    / "artifacts"
    / "runtime_reports"
    / "lunatic_route2_stage5_unattended_20260825_011207.root"
)
ECL = ROOT / "artifacts" / "decoded" / "ecldata5.ecl"


def _event(**updates: object) -> FutureDirectFire:
    fields: dict[str, object] = {
        "source": "fixture:main",
        "activation_frames": (1, 3),
        "origin_x": FloatInterval.point(120.0),
        "origin_y": FloatInterval.point(80.0),
        "mode": 0,
        "count1": 1,
        "count2": 1,
        "speed1": FloatInterval.point(0.0),
        "speed2": FloatInterval.point(0.0),
        "angle1": FloatInterval.point(0.25),
        "angle2": FloatInterval.point(0.0),
        "aim_angle": FloatInterval.point(1.0),
        "half_width": 2.0,
        "half_height": 3.0,
        "original_flags": 0,
        "transform_program_zero": True,
    }
    fields.update(updates)
    return FutureDirectFire(**fields)


def _capsules_by_spell() -> dict[int, Path]:
    manifest = json.loads(
        (CORPUS / "manifest.json").read_text(encoding="utf-8")
    )
    return {
        int(row["spell_id"]): CORPUS
        / (
            f"sha256-{row['content_sha256']}"
            ".th08-future-root.json.gz"
        )
        for row in manifest["capsules"]
    }


class RetainedEventStreamTests(unittest.TestCase):
    def test_point_event_round_trips_exact_resolved_aim(self) -> None:
        program = resolved_direct_fire_stage_program(
            (_event(),),
            horizon_frames=4,
            gameplay_rng_seed=0x1234,
            root_sha256="a" * 64,
        )

        self.assertEqual(len(program.phases[0].emitters), 2)
        self.assertEqual(program.schema, RESOLVED_AIM_STAGE_SCHEMA)
        emitter = program.phases[0].emitters[0]
        self.assertIn("resolved_aim_override", emitter.to_payload())
        _x, _y, descriptor = emitter.resolved_descriptor(
            1,
            player_x=-1000.0,
            player_y=1000.0,
        )
        self.assertEqual(descriptor.angle_to_player, f32(1.0))
        replay = StageProgram.from_payload(program.to_payload())
        self.assertEqual(replay, program)
        self.assertEqual(replay.digest, program.digest)

        runtime = StageRuntime(replay)
        steps = [runtime.step() for _frame in range(replay.frame_count)]
        self.assertEqual(
            [step.births_allocated for step in steps],
            [0, 1, 0, 1, 0],
        )
        angles = sorted(
            bullet.base_angle
            for bullet in runtime.bullets
            if bullet is not None
        )
        self.assertEqual(angles, [f32(1.25), f32(1.25)])

        downgraded = program.to_payload()
        downgraded.pop("sha256")
        downgraded["schema"] = STAGE_SCHEMA
        with self.assertRaisesRegex(ValueError, "resolved-aim features"):
            StageProgram.from_payload(downgraded)

    def test_interval_operand_is_rejected_without_midpoint(self) -> None:
        event = replace(
            _event(),
            aim_angle=FloatInterval(0.5, 1.5),
        )

        with self.assertRaisesRegex(
            RetainedEventStreamError,
            "aim_angle is not point-valued",
        ):
            resolved_direct_fire_stage_program(
                (event,),
                horizon_frames=4,
                gameplay_rng_seed=0,
                root_sha256="b" * 64,
            )

    def test_unlowered_lifecycle_flags_fail_closed(self) -> None:
        event = replace(_event(), original_flags=0x02)

        with self.assertRaisesRegex(
            RetainedEventStreamError,
            "ANM/lifecycle/transform/callback flags",
        ):
            resolved_direct_fire_stage_program(
                (event,),
                horizon_frames=4,
                gameplay_rng_seed=0,
                root_sha256="c" * 64,
            )

    def test_physical_roots_obey_generic_eligibility_and_prefix_gate(
        self,
    ) -> None:
        capsules = _capsules_by_spell()

        transition_107 = import_retained_future_event_stream(
            capsules[107], ECL
        )
        transition_111 = import_retained_future_event_stream(
            capsules[111], ECL
        )
        for result in (transition_107, transition_111):
            self.assertFalse(result.accepted_prefix)
            self.assertIn("player phase 0", result.rejection_reason)
            self.assertIsNone(result.closure)

        callback_boundary = import_retained_future_event_stream(
            capsules[103], ECL
        )
        self.assertFalse(callback_boundary.accepted_prefix)
        self.assertEqual(callback_boundary.proven_horizon_frames, 0)
        self.assertIn(
            "installed callback requires address-specific lowering",
            callback_boundary.rejection_reason,
        )

        callback_tag_boundary = import_retained_future_event_stream(
            capsules[115], ECL
        )
        self.assertTrue(callback_tag_boundary.accepted_prefix)
        self.assertIsNone(callback_tag_boundary.rejection_reason)
        self.assertFalse(callback_tag_boundary.full_horizon_complete)
        self.assertEqual(callback_tag_boundary.proven_horizon_frames, 86)
        self.assertEqual(callback_tag_boundary.producer_event_count, 0)
        self.assertEqual(callback_tag_boundary.emitter_count, 0)
        self.assertIn(
            "unsupported future bullet flags 0x100000",
            callback_tag_boundary.causal_prefix_reason,
        )
        assert callback_tag_boundary.program is not None
        runtime = StageRuntime(callback_tag_boundary.program)
        while not runtime.complete:
            runtime.step(player_x=192.0, player_y=400.0)
        self.assertEqual(runtime.metrics.births_allocated, 0)


if __name__ == "__main__":
    unittest.main()
