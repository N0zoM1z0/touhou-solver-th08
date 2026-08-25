from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import gzip
import json
import random
import unittest

import numpy as np

from th08_bullet_transform_model import (
    BulletTransformProgramRuntime,
    BulletTransformRuntime,
    StopTransformRuntime,
    TransformKind,
    TransformRecord,
    TransformTimerRuntime,
    pack_transform_program,
    parse_transform_program,
)
from th08_laser_model import LaserPhase, LaserState
from th08_laser_runtime import Laser
from th08_corridor_runtime import solve_corridor
from th08_future_birth_envelope import FloatInterval, FutureDirectFire
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_live.models import Bullet
from th08_runtime.current_hazard_root import (
    CURRENT_HAZARD_ROOT_SCHEMA,
    CURRENT_HAZARD_ROOT_SCHEMA_V1,
    build_current_hazard_root,
    current_hazards_from_root,
)
from touhou_control.trajectory import CollisionStateChange, VelocityChange
from th08_semantics.stage import StageRuntime
from th08_semantics.stage_generation import generate_stage_program
from th08_time_scale import (
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)
from touhou_control.corridor import CorridorConfig


def _bullet(slot: int = 17) -> Bullet:
    program_records = tuple(
        TransformRecord(
            index=index,
            kind=(TransformKind.STOP_REAIM_REPEAT if index == 4 else 0),
            allow_while_active=(index == 4),
            int_0=(30 if index == 4 else 0),
            int_1=(5 if index == 4 else 0),
            float_0=(0.25 if index == 4 else 0.0),
            float_1=(2.5 if index == 4 else 0.0),
        )
        for index in range(5)
    )
    return Bullet(
        x=123.25,
        y=341.5,
        vx=-1.25,
        vy=2.75,
        half_width=2.5,
        half_height=3.5,
        transform_flags=int(TransformKind.STOP_REAIM_REPEAT),
        slot=slot,
        speed=3.25,
        angle=-0.75,
        transform_runtime=BulletTransformRuntime(
            original_flags=int(TransformKind.STOP_REAIM_REPEAT),
            queue_cursor=4,
            next_record=TransformRecord(
                index=4,
                kind=TransformKind.STOP_REAIM_REPEAT,
                allow_while_active=True,
                int_0=30,
                int_1=5,
                float_0="base_angle",
                float_1=2.5,
            ),
            timer_fraction=0.5,
            timer_elapsed=11,
            resume_speed=2.5,
            angle_operand=0.25,
            duration=30,
            repeat_limit=5,
            repeat_count=2,
        ),
        transform_program_runtime=BulletTransformProgramRuntime(
            program=pack_transform_program(program_records),
            original_flags=int(TransformKind.STOP_REAIM_REPEAT),
            queue_cursor=4,
            cull_suppression_countdown=13,
            offscreen_counter=7,
            stop=StopTransformRuntime(
                timer=TransformTimerRuntime(
                    previous=10,
                    subframe=0.5,
                    current=11,
                ),
                resume_speed=2.5,
                angle_operand=0.25,
                duration=30,
                repeat_limit=5,
                repeat_count=2,
            ),
        ),
        callback_phase_state=2,
        callback_aux_state=1,
        velocity_changes=(
            VelocityChange(3, 1.0, -2.0),
            VelocityChange(9, -3.0, 4.0),
        ),
        collision_state_changes=(
            CollisionStateChange(3, False),
            CollisionStateChange(9, True),
        ),
        trajectory_uncertainty_x=0.125,
        trajectory_uncertainty_y=0.25,
        original_transform_flags=int(TransformKind.STOP_REAIM_REPEAT),
        native_state=2,
        native_state_timer_elapsed=7,
        bullet_type=16,
    )


def _laser(slot: int = 5) -> Laser:
    state = LaserState(
        origin_x=190.0,
        origin_y=80.0,
        angle=0.75,
        tail_distance=12.0,
        head_distance=160.0,
        maximum_length=220.0,
        width=24.0,
        speed=5.0,
        warmup_frames=20,
        active_frames=90,
        fade_frames=30,
        collision_enable_frame=12,
        collision_disable_frame=105,
        flags=3,
        current_width=18.0,
        phase=LaserPhase.ACTIVE,
        timer=31,
        timer_fraction=0.25,
        active=True,
    )
    return Laser(
        origin_x=state.origin_x,
        origin_y=state.origin_y,
        angle=state.angle,
        tail=state.tail_distance,
        head=state.head_distance,
        half_width=6.0,
        state=state,
        slot=slot,
        collision_flag=1,
        uncertainty=0.75,
        uncertainty_per_frame=0.0,
    )


class CurrentHazardRootTests(unittest.TestCase):
    def test_complete_planning_state_round_trips_in_canonical_slot_order(
        self,
    ) -> None:
        bullets = (_bullet(17), _bullet(2))
        lasers = (_laser(9), _laser(5))

        root = build_current_hazard_root(
            root_frame=39998,
            bullets=bullets,
            lasers=lasers,
        )
        replayed_bullets, replayed_lasers = current_hazards_from_root(
            json.loads(json.dumps(root)),
            expected_root_frame=39998,
        )

        self.assertEqual(root["schema"], CURRENT_HAZARD_ROOT_SCHEMA)
        self.assertEqual([row["slot"] for row in root["bullets"]], [2, 17])
        self.assertEqual([row["slot"] for row in root["lasers"]], [5, 9])
        self.assertEqual(replayed_bullets, (_bullet(2), _bullet(17)))
        self.assertEqual(replayed_lasers, (_laser(5), _laser(9)))
        self.assertIn("program_le_b64", root["bullets"][0]["transform_program_runtime"])

    def test_record_contains_active_values_instead_of_raw_pool_slabs(self) -> None:
        bullets = []
        for slot in range(64):
            bullet = _bullet(slot)
            assert bullet.transform_program_runtime is not None
            bullets.append(
                replace(
                    bullet,
                    transform_program_runtime=replace(
                        bullet.transform_program_runtime,
                        program=random.Random(slot).randbytes(18 * 24),
                    ),
                )
            )
        root = build_current_hazard_root(
            root_frame=9,
            bullets=tuple(bullets),
            lasers=tuple(_laser(slot) for slot in range(16)),
        )
        canonical = json.dumps(
            root,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        self.assertNotIn("blob", json.dumps(root).lower())
        self.assertLess(len(gzip.compress(canonical, mtime=0)), 64 * 1024)

    def test_reader_rejects_frame_slot_and_numeric_corruption(self) -> None:
        root = build_current_hazard_root(
            root_frame=100,
            bullets=(_bullet(2), _bullet(17)),
            lasers=(_laser(5),),
        )
        cases: tuple[tuple[str, object, str], ...] = (
            ("root_frame", 101, "frame disagrees"),
            ("bullet_pool_capacity", 1, "capacity disagrees"),
            ("schema", "unknown", "schema is unsupported"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                malformed = deepcopy(root)
                malformed[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    current_hazards_from_root(
                        malformed,
                        expected_root_frame=100,
                    )

        noncanonical = deepcopy(root)
        noncanonical["bullets"].reverse()
        with self.assertRaisesRegex(ValueError, "not canonical"):
            current_hazards_from_root(noncanonical)

        duplicate = deepcopy(root)
        duplicate["bullets"][1]["slot"] = 2
        with self.assertRaisesRegex(ValueError, "not canonical"):
            current_hazards_from_root(duplicate)

        nonfinite = deepcopy(root)
        nonfinite["bullets"][0]["position"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "must be finite"):
            current_hazards_from_root(nonfinite)

        missing_program = deepcopy(root)
        missing_program["bullets"][0]["transform_program_runtime"] = None
        with self.assertRaisesRegex(ValueError, "missing complete transform-program"):
            current_hazards_from_root(missing_program)

        short_program = deepcopy(root)
        short_program["bullets"][0]["transform_program_runtime"][
            "program_le_b64"
        ] = "AA=="
        with self.assertRaisesRegex(ValueError, "exactly 432 bytes"):
            current_hazards_from_root(short_program)

        mismatched_handler = deepcopy(root)
        mismatched_handler["bullets"][0]["transform_program_runtime"]["stop"] = None
        with self.assertRaisesRegex(ValueError, "active flag.*disagree"):
            current_hazards_from_root(mismatched_handler)

    def test_v1_root_without_full_program_remains_readable(self) -> None:
        root = build_current_hazard_root(
            root_frame=100,
            bullets=(_bullet(2),),
            lasers=(),
        )
        root["schema"] = CURRENT_HAZARD_ROOT_SCHEMA_V1
        root["bullets"][0].pop("transform_program_runtime")

        bullets, lasers = current_hazards_from_root(root)

        self.assertEqual(len(bullets), 1)
        self.assertIsNone(bullets[0].transform_program_runtime)
        self.assertEqual(lasers, ())

    def test_stateful_stage_root_replays_the_same_current_plus_future_policy(
        self,
    ) -> None:
        runtime = StageRuntime(
            generate_stage_program(seed=0xCE0132, profile="quick")
        )
        for _ in range(120):
            runtime.step(player_x=192.0, player_y=400.0)
        bullets, lasers = runtime.live_snapshot()
        self.assertGreater(len(bullets), 200)
        self.assertGreater(len(lasers), 0)
        self.assertGreater(
            sum(bool(value.transform_flags) for value in bullets),
            0,
        )
        self.assertTrue(
            all(
                value.transform_program_runtime is not None
                for value in bullets
                if value.original_transform_flags
            )
        )
        for value in bullets:
            retained = value.transform_program_runtime
            source_bullet = runtime.bullets[value.slot]
            if retained is None or source_bullet is None:
                continue
            records = parse_transform_program(retained.program)
            for record, spec in zip(records, source_bullet.transforms):
                if spec.kind in (
                    TransformKind.REFLECT_ALL_EDGES,
                    TransformKind.REFLECT_SIDES_AND_TOP,
                ):
                    self.assertEqual(record.int_0, spec.repeat_limit)
                if spec.kind in (
                    TransformKind.STOP_TURN_REPEAT,
                    TransformKind.STOP_REAIM_REPEAT,
                    TransformKind.STOP_SNAP_REPEAT,
                ):
                    self.assertEqual(record.int_1, spec.repeat_limit)
        root = build_current_hazard_root(
            root_frame=runtime.frame,
            bullets=bullets,
            lasers=lasers,
        )
        replayed_bullets, replayed_lasers = current_hazards_from_root(root)
        future_event = FutureDirectFire(
            source="generic-stage-continuation",
            activation_frames=(8,),
            bullet_type=2,
            origin_x=FloatInterval.point(192.0),
            origin_y=FloatInterval.point(100.0),
            mode=1,
            count1=1,
            count2=1,
            speed1=FloatInterval.point(1.0),
            speed2=FloatInterval.point(1.0),
            angle1=FloatInterval.point(1.5707963267948966),
            angle2=FloatInterval.point(0.0),
            aim_angle=FloatInterval.point(0.0),
            half_width=2.0,
            half_height=2.0,
            original_flags=0,
            transform_program_zero=True,
        )
        future = complete_future_hazard_projection(
            root_frame=runtime.frame,
            horizon_frames=16,
            events=(future_event,),
            source_semantics_version="stateful-stage-integration-v1",
        )
        config = CorridorConfig(
            grid_step=16.0,
            frames_per_layer=4,
            horizon_frames=16,
            required_clearance=11.313708498984761,
        )
        scale = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=32,
            provenance="stateful-stage-current-hazard-root-test",
            source_frame=runtime.frame,
        )

        def solve(
            current_bullets: tuple[Bullet, ...],
            current_lasers: tuple[Laser, ...],
        ) -> object:
            return solve_corridor(
                source_frame=runtime.frame,
                snapshot_frame=runtime.frame,
                forecast_lead_frames=0,
                player_x=192.0,
                player_y=400.0,
                bullets=current_bullets,
                lasers=current_lasers,
                enemy_bodies=(),
                future_hazard_projection=future,
                snapshot_lag=0,
                control_delay_candidates=(0, 1),
                nominal_control_delay=1,
                active_action="stay",
                time_scale_schedule=scale,
                corridor_config=config,
            )

        original = solve(bullets, lasers)
        replayed = solve(replayed_bullets, replayed_lasers)
        self.assertEqual(original.authority_version, replayed.authority_version)
        self.assertEqual(original.plan.reachable, replayed.plan.reachable)
        self.assertEqual(
            original.plan.initial_safe_action_count,
            replayed.plan.initial_safe_action_count,
        )
        assert original.plan.viability_policy is not None
        assert replayed.plan.viability_policy is not None
        self.assertTrue(
            np.array_equal(
                original.plan.viability_policy.viable,
                replayed.plan.viability_policy.viable,
            )
        )
        self.assertTrue(
            np.array_equal(
                original.plan.viability_policy.safe_action_masks,
                replayed.plan.viability_policy.safe_action_masks,
            )
        )


if __name__ == "__main__":
    unittest.main()
