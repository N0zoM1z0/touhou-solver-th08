#!/usr/bin/env python3
"""Source-derived lethal collision predicates and shadow adapter tests."""

from __future__ import annotations

import math
import unittest

import numpy as np

from th08_laser_runtime import (
    Laser,
    build_packed_laser_collision_frames,
)
from th08_live.local_hazards import _numpy_hazards_for_positions
from th08_source_collision import (
    player_half_extents_from_aabb,
    source_aabb_clearance,
    source_aabb_overlap_mask,
    source_aabb_overlaps,
    source_bullet_lethal_eligible,
    source_collision_hazards_for_positions,
    source_laser_rectangle_clearance,
)


def _bullet_frame() -> tuple[np.ndarray, ...]:
    return (
        np.asarray([0.0, 10.0, 20.0], dtype=np.float32),
        np.asarray([0.0, 0.0, 0.0], dtype=np.float32),
        np.asarray([2.0, 2.0, 2.0], dtype=np.float32),
        np.asarray([2.0, 2.0, 2.0], dtype=np.float32),
        np.asarray([False, False, False], dtype=np.bool_),
        np.asarray([1, 2, 1], dtype=np.uint16),
        np.asarray([0, 0, 4], dtype=np.uint8),
    )


class SourceCollisionTests(unittest.TestCase):
    def test_player_half_extents_recover_from_centered_cached_aabb(self) -> None:
        self.assertEqual(
            player_half_extents_from_aabb(
                player_x=192.0,
                player_y=400.0,
                lethal_aabb=(191.0, 399.0, 193.0, 401.0),
            ),
            (1.0, 1.0),
        )
        with self.assertRaisesRegex(ValueError, "centered"):
            player_half_extents_from_aabb(
                player_x=192.0,
                player_y=400.0,
                lethal_aabb=(190.0, 399.0, 193.0, 401.0),
            )

    def test_bullet_lifecycle_gate_matches_source_branch(self) -> None:
        self.assertTrue(
            source_bullet_lethal_eligible(
                native_state=1,
                callback_aux_state=0,
            )
        )
        for state, auxiliary in ((2, 0), (3, 0), (4, 0), (5, 0), (1, 1)):
            self.assertFalse(
                source_bullet_lethal_eligible(
                    native_state=state,
                    callback_aux_state=auxiliary,
                )
            )

    def test_aabb_collision_is_inclusive_and_axis_specific(self) -> None:
        self.assertEqual(
            source_aabb_clearance(
                player_x=0.0,
                player_y=0.0,
                player_half_width=1.0,
                player_half_height=2.0,
                hazard_x=3.0,
                hazard_y=5.0,
                hazard_half_width=2.0,
                hazard_half_height=3.0,
            ),
            0.0,
        )

    def test_aabb_uses_stored_binary32_bounds_at_touching_edge(self) -> None:
        player_x = float(np.float32(129.168609619))
        hazard_x = float(np.float32(121.566139221))
        hazard_size = float(np.float32(13.204931259))
        hazard_half_width = float(np.float32(hazard_size * 0.5))
        naive_double_clearance = abs(player_x - hazard_x) - (
            1.0 + hazard_half_width
        )
        self.assertGreater(naive_double_clearance, 0.0)
        self.assertEqual(
            np.float32(player_x - 1.0),
            np.float32(hazard_x + hazard_half_width),
        )

        self.assertTrue(
            source_aabb_overlaps(
                player_x=player_x,
                player_y=100.0,
                player_half_width=1.0,
                player_half_height=1.0,
                hazard_x=hazard_x,
                hazard_y=100.0,
                hazard_half_width=hazard_half_width,
                hazard_half_height=1.0,
            )
        )
        self.assertEqual(
            source_aabb_clearance(
                player_x=player_x,
                player_y=100.0,
                player_half_width=1.0,
                player_half_height=1.0,
                hazard_x=hazard_x,
                hazard_y=100.0,
                hazard_half_width=hazard_half_width,
                hazard_half_height=1.0,
            ),
            0.0,
        )
        np.testing.assert_array_equal(
            source_aabb_overlap_mask(
                player_x=np.asarray([[player_x]], dtype=np.float32),
                player_y=np.asarray([[100.0]], dtype=np.float32),
                player_half_width=1.0,
                player_half_height=1.0,
                hazard_x=np.asarray([[hazard_x]], dtype=np.float32),
                hazard_y=np.asarray([[100.0]], dtype=np.float32),
                hazard_half_width=np.asarray(
                    [[hazard_half_width]],
                    dtype=np.float32,
                ),
                hazard_half_height=1.0,
            ),
            np.asarray([[True]]),
        )
        self.assertGreater(
            source_aabb_clearance(
                player_x=0.0,
                player_y=0.0,
                player_half_width=1.0,
                player_half_height=2.0,
                hazard_x=3.001,
                hazard_y=5.0,
                hazard_half_width=2.0,
                hazard_half_height=3.0,
            ),
            0.0,
        )

    def test_laser_uses_rotated_finite_rectangle_with_inclusive_edges(self) -> None:
        laser = Laser(
            origin_x=0.0,
            origin_y=0.0,
            angle=math.pi / 2.0,
            tail=10.0,
            head=20.0,
            half_width=2.0,
        )
        self.assertAlmostEqual(
            source_laser_rectangle_clearance(
                player_x=-3.0,
                player_y=9.0,
                player_half_width=1.0,
                player_half_height=1.0,
                laser=laser,
            ),
            0.0,
            places=6,
        )
        self.assertGreater(
            source_laser_rectangle_clearance(
                player_x=-3.01,
                player_y=9.0,
                player_half_width=1.0,
                player_half_height=1.0,
                laser=laser,
            ),
            0.0,
        )

    def test_vectorized_bullet_geometry_matches_live_when_bound_equal(self) -> None:
        positions_x = np.asarray([0.0, 3.5, 10.0, 20.0], dtype=np.float32)
        positions_y = np.zeros(4, dtype=np.float32)
        frame = _bullet_frame()

        legacy = _numpy_hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=frame,
            lasers=(),
            enemy_bodies=(),
        )
        geometry_only = source_collision_hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=frame,
            lasers=(),
            enemy_bodies=(),
            player_half_width=1.0,
            player_half_height=1.0,
            filter_bullet_lifecycle=False,
        )

        for legacy_values, source_values in zip(legacy, geometry_only):
            np.testing.assert_array_equal(legacy_values, source_values)

    def test_vectorized_source_filter_removes_state_and_callback_false_hazards(
        self,
    ) -> None:
        positions_x = np.asarray([0.0, 3.5, 10.0, 20.0], dtype=np.float32)
        positions_y = np.zeros(4, dtype=np.float32)

        _, collisions, _ = source_collision_hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=_bullet_frame(),
            lasers=(),
            enemy_bodies=(),
            player_half_width=1.0,
            player_half_height=1.0,
        )

        np.testing.assert_array_equal(
            collisions,
            np.asarray([1, 0, 0, 0], dtype=np.int32),
        )

    def test_packed_laser_retains_rectangle_orientation_at_zero_length(
        self,
    ) -> None:
        laser = Laser(
            origin_x=12.0,
            origin_y=13.0,
            angle=math.pi / 2.0,
            tail=5.0,
            head=5.0,
            half_width=2.5,
        )

        packed = build_packed_laser_collision_frames(
            (laser,),
            horizon=1,
        )[0]

        self.assertAlmostEqual(float(packed.rectangle_half_width[0]), 2.5)
        self.assertAlmostEqual(float(packed.rectangle_cosine[0]), 0.0, places=6)
        self.assertAlmostEqual(float(packed.rectangle_sine[0]), 1.0, places=6)
        self.assertEqual(len(packed.fields_for_native()), 7)

    def test_vectorized_laser_rectangle_matches_scalar_source_predicate(
        self,
    ) -> None:
        laser = Laser(
            origin_x=100.0,
            origin_y=200.0,
            angle=0.37,
            tail=12.0,
            head=48.0,
            half_width=3.0,
        )
        positions_x = np.asarray([100.0, 112.0, 125.0, 160.0], dtype=np.float32)
        positions_y = np.asarray([200.0, 203.0, 210.0, 220.0], dtype=np.float32)
        empty_bullets = tuple(
            np.asarray([], dtype=dtype)
            for dtype in (
                np.float32,
                np.float32,
                np.float32,
                np.float32,
                np.bool_,
                np.uint16,
                np.uint8,
            )
        )

        _, collisions, _ = source_collision_hazards_for_positions(
            positions_x,
            positions_y,
            step=1,
            bullet_frame=empty_bullets,
            lasers=(laser,),
            enemy_bodies=(),
            player_half_width=1.0,
            player_half_height=1.0,
        )
        expected = np.asarray(
            [
                source_laser_rectangle_clearance(
                    player_x=float(x),
                    player_y=float(y),
                    player_half_width=1.0,
                    player_half_height=1.0,
                    laser=laser,
                )
                <= 0.0
                for x, y in zip(positions_x, positions_y, strict=True)
            ],
            dtype=np.int32,
        )

        np.testing.assert_array_equal(collisions, expected)


if __name__ == "__main__":
    unittest.main()
