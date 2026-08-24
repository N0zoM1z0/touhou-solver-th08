from __future__ import annotations

import unittest

import numpy as np

from th08_laser_runtime import PackedLaserFrame
from th08_live_dodge_agent import (
    EnemyBody,
    _configure_local_hazard_backend,
    _hazards_for_positions,
    _native_hazards_for_positions,
    _numpy_hazards_for_positions,
)
from touhou_control import native_backend


def _native_local_hazards_available() -> bool:
    return native_backend._load_local_hazards_function() is not None


def _packed_lasers(
    *,
    start_x: np.ndarray,
    start_y: np.ndarray,
    segment_x: np.ndarray,
    segment_y: np.ndarray,
    collision_radius: np.ndarray,
    base_uncertainty: np.ndarray,
    uncertainty_per_frame: np.ndarray,
) -> PackedLaserFrame:
    return PackedLaserFrame(
        start_x=np.asarray(start_x, dtype=np.float32),
        start_y=np.asarray(start_y, dtype=np.float32),
        segment_x=np.asarray(segment_x, dtype=np.float32),
        segment_y=np.asarray(segment_y, dtype=np.float32),
        collision_radius=np.asarray(collision_radius, dtype=np.float32),
        base_uncertainty=np.asarray(base_uncertainty, dtype=np.float32),
        uncertainty_per_frame=np.asarray(
            uncertainty_per_frame,
            dtype=np.float32,
        ),
    )


def _empty_lasers() -> PackedLaserFrame:
    empty = np.empty(0, dtype=np.float32)
    return _packed_lasers(
        start_x=empty,
        start_y=empty,
        segment_x=empty,
        segment_y=empty,
        collision_radius=empty,
        base_uncertainty=empty,
        uncertainty_per_frame=empty,
    )


def _assert_hazard_parity(
    case: unittest.TestCase,
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
) -> None:
    reference = _numpy_hazards_for_positions(
        positions_x,
        positions_y,
        step=step,
        bullet_frame=bullet_frame,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
    )
    native = _native_hazards_for_positions(
        positions_x,
        positions_y,
        step=step,
        bullet_frame=bullet_frame,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
    )
    np.testing.assert_array_equal(native[1], reference[1])
    np.testing.assert_array_equal(
        native[2] <= 0.0,
        reference[2] <= 0.0,
    )
    np.testing.assert_allclose(
        native[2],
        reference[2],
        rtol=0.0,
        atol=3e-5,
    )
    np.testing.assert_allclose(
        native[0],
        reference[0],
        rtol=4e-6,
        atol=4e-3,
    )
    case.assertEqual(native[0].dtype, np.dtype(np.float64))
    case.assertEqual(native[1].dtype, np.dtype(np.int32))
    case.assertEqual(native[2].dtype, np.dtype(np.float64))


@unittest.skipUnless(
    _native_local_hazards_available(),
    "native local hazard kernel is not built",
)
class NativeLocalHazardParityTests(unittest.TestCase):
    def tearDown(self) -> None:
        _configure_local_hazard_backend("numpy")

    def test_empty_hazard_frame_preserves_infinite_clearance(self) -> None:
        empty_float = np.empty(0, dtype=np.float32)
        empty_bool = np.empty(0, dtype=np.bool_)
        positions_x = np.asarray([0.0, 192.0, 384.0], dtype=np.float32)
        positions_y = np.asarray([32.0, 224.0, 432.0], dtype=np.float32)
        _assert_hazard_parity(
            self,
            positions_x,
            positions_y,
            step=1,
            bullet_frame=(
                empty_float,
                empty_float,
                empty_float,
                empty_float,
                empty_bool,
            ),
            lasers=_empty_lasers(),
            enemy_bodies=(),
        )

    def test_adversarial_boundaries_and_zero_length_laser_match(self) -> None:
        positions_x = np.asarray(
            [64.0, 100.0, 128.0, 160.0, 196.0],
            dtype=np.float32,
        )
        positions_y = np.asarray(
            [96.0, 128.0, 128.0, 128.0, 160.0],
            dtype=np.float32,
        )
        bullet_frame = (
            np.asarray([64.0, 184.0, 212.0, 280.001], dtype=np.float32),
            np.asarray([96.0, 128.0, 128.0, 160.0], dtype=np.float32),
            np.asarray([0.0, 2.0, 2.0, 4.0], dtype=np.float32),
            np.asarray([0.0, 3.0, 2.0, 4.0], dtype=np.float32),
            np.asarray([False, True, False, True], dtype=np.bool_),
        )
        lasers = _packed_lasers(
            start_x=np.asarray([100.0, 56.0, 252.001]),
            start_y=np.asarray([128.0, 164.0, 160.0]),
            segment_x=np.asarray([0.0, 144.0, 0.0]),
            segment_y=np.asarray([0.0, -72.0, 0.0]),
            collision_radius=np.asarray([2.0, 5.0, 1.0]),
            base_uncertainty=np.asarray([0.0, 1.5, 0.0]),
            uncertainty_per_frame=np.asarray([0.0, 0.25, 0.0]),
        )
        enemy_bodies = (
            EnemyBody(
                pointer=1,
                x=132.0,
                y=128.0,
                vx=-1.0,
                vy=0.5,
                half_width=6.0,
                half_height=8.0,
                flags=0,
                uncertainty=2.0,
            ),
            EnemyBody(
                pointer=2,
                x=360.0,
                y=400.0,
                vx=0.0,
                vy=0.0,
                half_width=12.0,
                half_height=12.0,
                flags=0,
            ),
        )
        for step in (1, 3, 8, 17):
            with self.subTest(step=step):
                _assert_hazard_parity(
                    self,
                    positions_x,
                    positions_y,
                    step=step,
                    bullet_frame=bullet_frame,
                    lasers=lasers,
                    enemy_bodies=enemy_bodies,
                )

    def test_live_bullet_aabb_uses_source_binary32_touching_edge(self) -> None:
        player_x = np.float32(129.168609619)
        hazard_x = np.float32(121.566139221)
        hazard_half_width = np.float32(np.float32(13.204931259) * 0.5)
        self.assertGreater(
            abs(float(player_x) - float(hazard_x))
            - (1.0 + float(hazard_half_width)),
            0.0,
        )
        frame = (
            np.asarray([hazard_x], dtype=np.float32),
            np.asarray([100.0], dtype=np.float32),
            np.asarray([hazard_half_width], dtype=np.float32),
            np.asarray([1.0], dtype=np.float32),
            np.asarray([False], dtype=np.bool_),
            np.asarray([1], dtype=np.uint16),
            np.asarray([0], dtype=np.uint8),
        )
        for implementation in (
            _numpy_hazards_for_positions,
            _native_hazards_for_positions,
        ):
            with self.subTest(implementation=implementation.__name__):
                _, collisions, minimum = implementation(
                    np.asarray([player_x], dtype=np.float32),
                    np.asarray([100.0], dtype=np.float32),
                    step=1,
                    bullet_frame=frame,
                    lasers=_empty_lasers(),
                    enemy_bodies=(),
                )
                np.testing.assert_array_equal(
                    collisions,
                    np.asarray([1], dtype=np.int32),
                )
                self.assertLessEqual(float(minimum[0]), 0.0)

    def test_only_irreversibly_retired_state_five_is_filtered(self) -> None:
        bullet_count = 5
        frame = (
            np.full(bullet_count, 100.0, dtype=np.float32),
            np.full(bullet_count, 120.0, dtype=np.float32),
            np.full(bullet_count, 2.0, dtype=np.float32),
            np.full(bullet_count, 2.0, dtype=np.float32),
            np.zeros(bullet_count, dtype=np.bool_),
            np.asarray([1, 2, 3, 4, 5], dtype=np.uint16),
            np.zeros(bullet_count, dtype=np.uint8),
        )
        for implementation in (
            _numpy_hazards_for_positions,
            _native_hazards_for_positions,
        ):
            with self.subTest(implementation=implementation.__name__):
                _, collisions, _ = implementation(
                    np.asarray([100.0], dtype=np.float32),
                    np.asarray([120.0], dtype=np.float32),
                    step=1,
                    bullet_frame=frame,
                    lasers=_empty_lasers(),
                    enemy_bodies=(),
                )
                # States 2/3/4 can still activate after their ANM completes;
                # only state 5 is guaranteed never to return to state 1.
                np.testing.assert_array_equal(
                    collisions,
                    np.asarray([4], dtype=np.int32),
                )

    def test_randomized_valid_frames_match_independent_numpy_oracle(
        self,
    ) -> None:
        rng = np.random.default_rng(0xCE0122)
        for case_index in range(48):
            position_count = int(rng.integers(1, 97))
            bullet_count = int(rng.integers(0, 385))
            laser_count = int(rng.integers(0, 25))
            body_count = int(rng.integers(0, 33))
            positions_x = rng.uniform(
                -48.0,
                432.0,
                position_count,
            ).astype(np.float32)
            positions_y = rng.uniform(
                -48.0,
                480.0,
                position_count,
            ).astype(np.float32)
            bullet_frame = (
                rng.uniform(-160.0, 544.0, bullet_count).astype(np.float32),
                rng.uniform(-160.0, 592.0, bullet_count).astype(np.float32),
                rng.uniform(0.0, 16.0, bullet_count).astype(np.float32),
                rng.uniform(0.0, 16.0, bullet_count).astype(np.float32),
                rng.integers(
                    0,
                    2,
                    bullet_count,
                    dtype=np.uint8,
                ).astype(np.bool_),
            )
            lasers = _packed_lasers(
                start_x=rng.uniform(-192.0, 576.0, laser_count),
                start_y=rng.uniform(-192.0, 624.0, laser_count),
                segment_x=rng.uniform(-512.0, 512.0, laser_count),
                segment_y=rng.uniform(-512.0, 512.0, laser_count),
                collision_radius=rng.uniform(0.0, 24.0, laser_count),
                base_uncertainty=rng.uniform(0.0, 8.0, laser_count),
                uncertainty_per_frame=rng.uniform(
                    0.0,
                    1.0,
                    laser_count,
                ),
            )
            enemy_bodies = tuple(
                EnemyBody(
                    pointer=index + 1,
                    x=float(rng.uniform(-96.0, 480.0)),
                    y=float(rng.uniform(-96.0, 528.0)),
                    vx=float(rng.uniform(-6.0, 6.0)),
                    vy=float(rng.uniform(-6.0, 6.0)),
                    half_width=float(rng.uniform(0.0, 32.0)),
                    half_height=float(rng.uniform(0.0, 32.0)),
                    flags=0,
                    uncertainty=float(rng.uniform(0.0, 12.0)),
                )
                for index in range(body_count)
            )
            with self.subTest(case=case_index):
                _assert_hazard_parity(
                    self,
                    positions_x,
                    positions_y,
                    step=int(rng.integers(1, 25)),
                    bullet_frame=bullet_frame,
                    lasers=lasers,
                    enemy_bodies=enemy_bodies,
                )

    def test_density_beyond_native_bullet_pool_matches(self) -> None:
        rng = np.random.default_rng(0xCE0122D)
        position_count = 72
        bullet_count = 2304
        positions_x = rng.uniform(
            0.0,
            384.0,
            position_count,
        ).astype(np.float32)
        positions_y = rng.uniform(
            16.0,
            448.0,
            position_count,
        ).astype(np.float32)
        bullet_frame = (
            rng.uniform(-80.0, 464.0, bullet_count).astype(np.float32),
            rng.uniform(-80.0, 528.0, bullet_count).astype(np.float32),
            rng.uniform(0.0, 12.0, bullet_count).astype(np.float32),
            rng.uniform(0.0, 12.0, bullet_count).astype(np.float32),
            rng.integers(
                0,
                2,
                bullet_count,
                dtype=np.uint8,
            ).astype(np.bool_),
        )
        _assert_hazard_parity(
            self,
            positions_x,
            positions_y,
            step=11,
            bullet_frame=bullet_frame,
            lasers=_empty_lasers(),
            enemy_bodies=(),
        )

    def test_explicit_native_backend_dispatches_to_parity_gated_export(
        self,
    ) -> None:
        empty_float = np.empty(0, dtype=np.float32)
        empty_bool = np.empty(0, dtype=np.bool_)
        positions_x = np.asarray([96.0, 192.0], dtype=np.float32)
        positions_y = np.asarray([128.0, 256.0], dtype=np.float32)
        arguments = {
            "step": 4,
            "bullet_frame": (
                empty_float,
                empty_float,
                empty_float,
                empty_float,
                empty_bool,
            ),
            "lasers": _empty_lasers(),
            "enemy_bodies": (),
        }
        expected = _native_hazards_for_positions(
            positions_x,
            positions_y,
            **arguments,
        )
        _configure_local_hazard_backend("native")
        actual = _hazards_for_positions(
            positions_x,
            positions_y,
            **arguments,
        )

        for actual_values, expected_values in zip(actual, expected):
            np.testing.assert_array_equal(actual_values, expected_values)
