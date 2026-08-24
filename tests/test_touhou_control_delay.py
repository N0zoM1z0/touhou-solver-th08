#!/usr/bin/env python3
"""Tests for game-neutral online actuation-delay identification."""

from __future__ import annotations

import unittest

from touhou_control.delay import AdaptiveControlDelay


class AdaptiveControlDelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.estimator = AdaptiveControlDelay(
            supported_mask=0xF7,
            minimum=1,
            maximum=4,
            window=16,
            guard_frames=20,
        )

    def test_initial_support_includes_pickup_uncertainty(self) -> None:
        estimate = self.estimator.estimate(frame=10, default=2)
        self.assertEqual(estimate.nominal, 3)
        self.assertEqual(estimate.support, (2, 3))

    def test_observed_mask_transition_learns_end_to_end_delay(self) -> None:
        self.estimator.issued(
            snapshot_frame=100,
            issue_frame=102,
            expected_mask=0x51,
            support_high=3,
        )
        self.estimator.observe(frame=103, input_mask=0x01)
        self.assertEqual(len(self.estimator.end_to_end_lags), 0)
        self.estimator.observe(frame=104, input_mask=0x51)
        estimate = self.estimator.estimate(frame=104)
        self.assertEqual(tuple(self.estimator.pickup_lags), (2,))
        self.assertEqual(tuple(self.estimator.end_to_end_lags), (4,))
        self.assertEqual(estimate.support, (4,))
        self.assertTrue(estimate.guard_active)
        self.assertEqual(estimate.overruns, 1)

    def test_overwritten_pending_command_is_censored(self) -> None:
        self.estimator.issued(
            snapshot_frame=10,
            issue_frame=11,
            expected_mask=0x41,
            support_high=3,
        )
        self.estimator.issued(
            snapshot_frame=12,
            issue_frame=13,
            expected_mask=0x81,
            support_high=3,
        )
        self.assertEqual(self.estimator.censored, 1)
        self.assertEqual(len(self.estimator.end_to_end_lags), 0)

    def test_pending_estimate_conditions_remaining_end_to_end_support(
        self,
    ) -> None:
        self.estimator.issued(
            snapshot_frame=10,
            issue_frame=12,
            expected_mask=0x41,
            support_high=4,
            support=(2, 3, 4),
        )
        estimate = self.estimator.pending_estimate(frame=13)
        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.expected_mask, 0x41)
        self.assertEqual(estimate.remaining_frames, (1,))
        self.assertEqual(estimate.snapshot_age, 3)
        self.assertEqual(estimate.issue_age, 1)
        self.assertFalse(estimate.overdue)

    def test_overdue_unobserved_command_stays_pending(self) -> None:
        self.estimator.issued(
            snapshot_frame=10,
            issue_frame=12,
            expected_mask=0x41,
            support_high=3,
            support=(2, 3),
        )
        estimate = self.estimator.pending_estimate(frame=14)
        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.remaining_frames, (1,))
        self.assertTrue(estimate.overdue)

    def test_hit_temporarily_expands_tail_support(self) -> None:
        for frame, total in enumerate((2, 2, 3, 3, 3, 3), start=100):
            self.estimator.issued(
                snapshot_frame=frame,
                issue_frame=frame + 1,
                expected_mask=frame & 0xF7,
                support_high=4,
            )
            self.estimator.observe(
                frame=frame + total,
                input_mask=frame & 0xF7,
            )
        before = self.estimator.estimate(frame=110)
        self.estimator.register_hit(110)
        guarded = self.estimator.estimate(frame=111)
        expired = self.estimator.estimate(frame=131)
        self.assertGreaterEqual(guarded.support[-1], before.support[-1])
        self.assertTrue(guarded.guard_active)
        self.assertFalse(expired.guard_active)

    def test_deadline_hold_widens_next_estimate_without_a_write(self) -> None:
        for index in range(12):
            frame = 10 + index * 3
            expected = 0x41 if index % 2 == 0 else 0x81
            self.estimator.issued(
                snapshot_frame=frame,
                issue_frame=frame,
                expected_mask=expected,
                support_high=3,
            )
            self.estimator.observe(
                frame=frame + 1,
                input_mask=expected,
            )
        narrowed = self.estimator.estimate(frame=45)
        self.assertEqual(narrowed.support, (1,))

        self.estimator.register_deadline_miss(
            frame=50,
            observed_lag=2,
        )

        recovered = self.estimator.estimate(frame=51)
        self.assertEqual(recovered.support, (1, 2, 3))
        self.assertTrue(recovered.guard_active)
        self.assertEqual(recovered.deadline_misses, 1)
        self.assertEqual(recovered.overruns, 0)
        self.assertEqual(recovered.censored, 0)
        self.assertEqual(
            self.estimator.estimate(frame=71).support,
            (1,),
        )

    def test_reset_clears_deadline_feedback(self) -> None:
        self.estimator.register_deadline_miss(
            frame=50,
            observed_lag=3,
        )
        self.estimator.reset()

        estimate = self.estimator.estimate(frame=51, default=2)
        self.assertEqual(estimate.support, (2, 3))
        self.assertEqual(estimate.deadline_misses, 0)
        self.assertFalse(estimate.guard_active)


if __name__ == "__main__":
    unittest.main()
