"""Offline gates for TH08 global-policy action authority."""

from __future__ import annotations

from dataclasses import replace
import unittest

from th08_corridor_adapter import TH08_CORRIDOR_CONFIG
from th08_corridor_runtime import CorridorSolution, solve_corridor
from th08_future_birth_envelope import (
    FloatInterval,
    FutureTaggedBulletCallback,
)
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_global_authority import assess_th08_global_action_authority
from th08_live.current_pool_callbacks import (
    CurrentPoolProjectionCallbackJoin,
    join_projection_callbacks_to_current_pool,
)
from th08_live.models import Bullet
from th08_live.runtime_ecl_identity import RuntimeEclAcceptedVersion
from th08_semantics.stage import StageRuntime
from th08_semantics.stage_generation import generate_stage_program
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS, Th08TimeScaleSchedule
from touhou_control.pipeline_identity import VersionIdentity


_CONTEXT = (7, 5, 107)
_PROVENANCE = "exact_runtime_ecl_no_scale_writer:test:stage=5"


def _runtime_ecl_version() -> RuntimeEclAcceptedVersion:
    return RuntimeEclAcceptedVersion(
        runtime_base=0x02100000,
        image_length=4096,
        relocated_sha256="1" * 64,
        normalized_sha256="2" * 64,
        static_sha256="3" * 64,
        route_id=2,
        difficulty_index=3,
        stage_route_index=5,
        gameplay_epoch=7,
        decision_frame=80,
        snapshot_frame=78,
    )


def _unit_schedule(*, source_frame: int) -> Th08TimeScaleSchedule:
    return Th08TimeScaleSchedule.constant(
        TH08_UNIT_TIME_SCALE_BITS,
        horizon=256,
        provenance=_PROVENANCE,
        source_frame=source_frame,
    )


def _projection(
    *,
    source_semantics: str = "test-source-v1",
    tagged_callbacks: tuple[FutureTaggedBulletCallback, ...] = (),
):
    return complete_future_hazard_projection(
        root_frame=90,
        horizon_frames=100,
        events=(),
        tagged_callbacks=tagged_callbacks,
        source_semantics_version=source_semantics,
    )


def _solve(
    *,
    include_future: bool = True,
    tagged_callbacks: tuple[FutureTaggedBulletCallback, ...] = (),
    projection=None,
    callback_join: CurrentPoolProjectionCallbackJoin | None = None,
    bullets=(),
) -> CorridorSolution:
    return solve_corridor(
        source_frame=100,
        snapshot_frame=90,
        forecast_lead_frames=10,
        player_x=192.0,
        player_y=400.0,
        bullets=bullets,
        lasers=(),
        enemy_bodies=(),
        future_hazard_projection=(
            projection
            if projection is not None
            else _projection(tagged_callbacks=tagged_callbacks)
            if include_future
            else None
        ),
        current_pool_callback_join=callback_join,
        runtime_ecl_version=_runtime_ecl_version(),
        snapshot_lag=0,
        control_delay_candidates=(0, 1, 2),
        nominal_control_delay=1,
        active_action="stay",
        context_key=_CONTEXT,
        time_scale_schedule=_unit_schedule(source_frame=90),
    )


def _assess(
    solution: CorridorSolution,
    *,
    runtime_ecl_version: RuntimeEclAcceptedVersion | None = None,
    schedule: Th08TimeScaleSchedule | None = None,
    context_key: tuple[int, int, int | None] = _CONTEXT,
    corridor_config=TH08_CORRIDOR_CONFIG,
):
    return assess_th08_global_action_authority(
        solution,
        current_frame=100,
        context_key=context_key,
        runtime_ecl_version=(
            _runtime_ecl_version()
            if runtime_ecl_version is None
            else runtime_ecl_version
        ),
        time_scale_schedule=(
            _unit_schedule(source_frame=100)
            if schedule is None
            else schedule
        ),
        corridor_config=corridor_config,
    )


class Th08GlobalAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.solution = _solve()

    def test_exact_complete_join_allows_rebased_unit_schedule(self) -> None:
        assessment = _assess(self.solution)

        self.assertTrue(assessment.allowed, assessment.reasons)
        self.assertEqual(assessment.reasons, ())
        self.assertTrue(self.solution.authority_version.complete)
        self.assertEqual(len(self.solution.authority_version.digest), 64)

    def test_spell_policy_without_future_births_is_shadow_only(self) -> None:
        solution = _solve(include_future=False)

        assessment = _assess(solution)

        self.assertFalse(assessment.allowed)
        self.assertIn("authority_version_incomplete", assessment.reasons)
        self.assertIn(
            "future_hazard_projection_unavailable",
            assessment.reasons,
        )

    def test_active_transform_heuristic_is_never_action_authority(self) -> None:
        transformed = Bullet(
            x=192.0,
            y=120.0,
            vx=0.0,
            vy=1.0,
            half_width=2.0,
            half_height=2.0,
            transform_flags=0x20,
            slot=7,
        )
        solution = _solve(bullets=(transformed,))

        assessment = _assess(solution)

        self.assertFalse(assessment.allowed)
        self.assertIn(
            "current_bullet_transform_geometry_incomplete",
            assessment.reasons,
        )
        assert solution.authority_version is not None
        self.assertFalse(
            dict(solution.authority_version.geometry.components)[
                "current_bullet_transforms_complete"
            ]
        )

    def test_source_stateful_transform_escapes_old_growth_envelope(self) -> None:
        runtime = StageRuntime(
            generate_stage_program(seed=0xCE0132, profile="quick")
        )
        for _ in range(20):
            runtime.step(player_x=192.0, player_y=400.0)
        root_frame = runtime.frame
        roots = tuple(
            (
                bullet,
                bullet.slot,
                bullet.x,
                bullet.y,
                bullet.velocity_x,
                bullet.velocity_y,
            )
            for bullet in runtime.bullets
            if bullet is not None and bullet.active_transform_flags
        )
        self.assertEqual(len(roots), 28)

        survivor_samples = 0
        violations = 0
        worst: tuple[float, int, int, float, float] | None = None
        for _ in range(80):
            runtime.step(player_x=192.0, player_y=400.0)
            horizon = runtime.frame - root_frame
            old_bound = 3.0 + 0.35 * horizon
            for root, slot, x, y, velocity_x, velocity_y in roots:
                bullet = runtime.bullets[slot]
                # Slot reuse must not alias a later birth to the root bullet.
                if bullet is not root:
                    continue
                survivor_samples += 1
                error_x = abs(bullet.x - (x + velocity_x * horizon))
                error_y = abs(bullet.y - (y + velocity_y * horizon))
                error = max(error_x, error_y)
                if error <= old_bound:
                    continue
                violations += 1
                ratio = error / old_bound
                if worst is None or ratio > worst[0]:
                    worst = (ratio, horizon, slot, error_x, old_bound)

        self.assertEqual(survivor_samples, 1_937)
        self.assertEqual(violations, 1_037)
        assert worst is not None
        ratio, horizon, slot, error_x, old_bound = worst
        self.assertEqual((horizon, slot), (80, 13))
        self.assertAlmostEqual(error_x, 97.06080222129822)
        self.assertEqual(old_bound, 31.0)
        self.assertGreater(ratio, 3.13)

    def test_uncomposed_current_pool_callbacks_are_shadow_only(self) -> None:
        callback = FutureTaggedBulletCallback(
            source="test",
            frame=4,
            callback_index=14,
            tag_mask=0x100000,
            callback_angle=None,
            callback_speed=FloatInterval.point(2.0),
        )
        projection = _projection(tagged_callbacks=(callback,))
        spoofed = CorridorSolution(
            artifact=replace(
                self.solution.artifact,
                future_hazard_version=projection.version,
                future_hazard_coverage=projection.coverage,
            ),
            publication=self.solution.publication,
            handles=replace(
                self.solution.handles,
                future_hazard_projection=projection,
            ),
        )
        assessment = _assess(spoofed)

        self.assertFalse(assessment.allowed)
        self.assertIn(
            "future_hazard_current_pool_callback_join_unavailable",
            assessment.reasons,
        )

    def test_solution_bound_callback_join_can_acquire_authority(self) -> None:
        callback = FutureTaggedBulletCallback(
            source="test",
            frame=4,
            callback_index=14,
            tag_mask=0x100000,
            callback_angle=None,
            callback_speed=FloatInterval.point(2.0),
        )
        projection = _projection(tagged_callbacks=(callback,))
        with self.assertRaisesRegex(
            ValueError,
            "current-pool callback join",
        ):
            _solve(projection=projection)
        with self.assertRaisesRegex(
            ValueError,
            "does not satisfy its contract",
        ):
            _solve(projection=projection, callback_join=object())
        half_scale_join = join_projection_callbacks_to_current_pool(
            (),
            projection=projection,
            bullet_root_frame=90,
            policy_source_frame=100,
            policy_horizon_frames=TH08_CORRIDOR_CONFIG.horizon_frames,
            time_scale=0.5,
        )
        with self.assertRaisesRegex(
            ValueError,
            "exact unit time scale",
        ):
            _solve(
                projection=projection,
                callback_join=half_scale_join,
                bullets=half_scale_join.bullets,
            )
        join = join_projection_callbacks_to_current_pool(
            (),
            projection=projection,
            bullet_root_frame=90,
            policy_source_frame=100,
            policy_horizon_frames=TH08_CORRIDOR_CONFIG.horizon_frames,
            time_scale=1.0,
        )
        solution = _solve(
            projection=projection,
            callback_join=join,
            bullets=join.bullets,
        )

        assessment = _assess(solution)
        self.assertTrue(assessment.allowed, assessment.reasons)
        self.assertEqual(
            solution.current_pool_callback_join_version,
            join.version,
        )
        self.assertIs(solution.current_pool_callback_join, join)
        wrong_scale = solution.with_handles(
            current_pool_callback_join=half_scale_join,
        )
        self.assertIn(
            "future_hazard_current_pool_callback_scale_mismatch",
            _assess(wrong_scale).reasons,
        )

    def test_legacy_solution_without_join_is_shadow_only(self) -> None:
        legacy = CorridorSolution(
            self.solution.source_frame,
            self.solution.plan,
            self.solution.solve_ms,
            snapshot_frame=self.solution.snapshot_frame,
            context_key=self.solution.context_key,
            time_scale_identity=self.solution.time_scale_identity,
            future_hazard_projection=(
                self.solution.future_hazard_projection
            ),
            future_hazard_version=self.solution.future_hazard_version,
            future_hazard_coverage=self.solution.future_hazard_coverage,
        )

        assessment = _assess(legacy)

        self.assertFalse(assessment.allowed)
        self.assertEqual(
            assessment.reasons,
            ("authority_version_unavailable",),
        )

    def test_runtime_context_and_scale_mismatches_fail_closed(self) -> None:
        wrong_ecl = replace(
            _runtime_ecl_version(),
            normalized_sha256="4" * 64,
        )
        self.assertIn(
            "runtime_ecl_identity_mismatch",
            _assess(
                self.solution,
                runtime_ecl_version=wrong_ecl,
            ).reasons,
        )
        self.assertIn(
            "context_mismatch",
            _assess(
                self.solution,
                context_key=(8, 5, 107),
            ).reasons,
        )
        wrong_provenance = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=256,
            provenance="another_exact_source",
            source_frame=100,
        )
        self.assertIn(
            "time_scale_provenance_mismatch",
            _assess(
                self.solution,
                schedule=wrong_provenance,
            ).reasons,
        )

    def test_future_geometry_and_policy_versions_fail_closed(self) -> None:
        other_projection = _projection(source_semantics="test-source-v2")
        projection_mismatch = self.solution.with_handles(
            future_hazard_projection=other_projection,
        )
        self.assertIn(
            "future_hazard_authority_version_mismatch",
            _assess(projection_mismatch).reasons,
        )

        wrong_policy = replace(
            TH08_CORRIDOR_CONFIG,
            preferred_clearance=(
                TH08_CORRIDOR_CONFIG.preferred_clearance + 1.0
            ),
        )
        self.assertIn(
            "policy_version_mismatch",
            _assess(
                self.solution,
                corridor_config=wrong_policy,
            ).reasons,
        )

        assert self.solution.authority_version is not None
        wrong_geometry_version = replace(
            self.solution.authority_version,
            geometry=VersionIdentity.from_mapping(
                "test-wrong-geometry",
                {"version": 1},
            ),
        )
        wrong_geometry = CorridorSolution(
            artifact=replace(
                self.solution.artifact,
                authority_version=wrong_geometry_version,
            ),
            publication=self.solution.publication,
            handles=self.solution.handles,
        )
        self.assertIn(
            "geometry_version_mismatch",
            _assess(wrong_geometry).reasons,
        )


if __name__ == "__main__":
    unittest.main()
