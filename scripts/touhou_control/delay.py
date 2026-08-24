"""Online identification of frame-quantized input actuation delay."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


def _nearest_rank(values: tuple[int, ...], quantile: float) -> int:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


@dataclass(frozen=True)
class DelayEstimate:
    nominal: int
    support: tuple[int, ...]
    computation_samples: int
    pickup_samples: int
    end_to_end_samples: int
    guard_active: bool
    overruns: int
    censored: int
    deadline_misses: int = 0


@dataclass(frozen=True)
class _PendingActuation:
    snapshot_frame: int
    issue_frame: int
    expected_mask: int
    support_high: int
    support: tuple[int, ...]


@dataclass(frozen=True)
class PendingCommandEstimate:
    """Conditioned estimator support for an unobserved final desired input.

    Remaining frames use the enemy-manager snapshot coordinate. They are not
    native input-publication callback counts.
    """

    expected_mask: int
    remaining_frames: tuple[int, ...]
    snapshot_age: int
    issue_age: int
    overdue: bool


class AdaptiveControlDelay:
    """Learn snapshot-to-visible-final-input delay from live observations.

    This controller estimator timestamps asynchronous captures with the
    enemy-manager frame. It does not identify the priority-17 callback in
    which an ordered intermediate or final input was published.
    """

    def __init__(
        self,
        *,
        supported_mask: int,
        minimum: int = 1,
        maximum: int = 4,
        window: int = 120,
        guard_frames: int = 600,
        default_pickup_frames: int = 1,
    ) -> None:
        if minimum < 0 or maximum < minimum:
            raise ValueError("invalid delay bounds")
        if window <= 0 or guard_frames <= 0:
            raise ValueError("window and guard duration must be positive")
        self.supported_mask = supported_mask
        self.minimum = minimum
        self.maximum = maximum
        self.guard_frames = guard_frames
        self.default_pickup_frames = default_pickup_frames
        self.computation_lags: deque[int] = deque(maxlen=window)
        self.pickup_lags: deque[int] = deque(maxlen=window)
        self.end_to_end_lags: deque[int] = deque(maxlen=window)
        self.pending: _PendingActuation | None = None
        self.guard_until = -1
        self.deadline_floor_until = -1
        self.deadline_support_floor = self.minimum
        self.overruns = 0
        self.censored = 0
        self.deadline_misses = 0

    def reset(self) -> None:
        self.computation_lags.clear()
        self.pickup_lags.clear()
        self.end_to_end_lags.clear()
        self.pending = None
        self.guard_until = -1
        self.deadline_floor_until = -1
        self.deadline_support_floor = self.minimum
        self.overruns = 0
        self.censored = 0
        self.deadline_misses = 0

    def observe(self, *, frame: int, input_mask: int) -> None:
        pending = self.pending
        if pending is None:
            return
        if input_mask & self.supported_mask == pending.expected_mask:
            pickup_lag = frame - pending.issue_frame
            end_to_end_lag = frame - pending.snapshot_frame
            if 0 <= pickup_lag < 120 and 0 < end_to_end_lag < 120:
                self.pickup_lags.append(pickup_lag)
                self.end_to_end_lags.append(end_to_end_lag)
                if end_to_end_lag > pending.support_high:
                    self.overruns += 1
                    self.guard_until = max(
                        self.guard_until,
                        frame + self.guard_frames,
                    )
            self.pending = None
        elif frame - pending.issue_frame >= 12:
            self.censored += 1
            self.pending = None

    def issued(
        self,
        *,
        snapshot_frame: int,
        issue_frame: int,
        expected_mask: int,
        support_high: int,
        support: tuple[int, ...] | None = None,
    ) -> None:
        if self.pending is not None:
            self.censored += 1
        if support is None:
            support = tuple(range(self.minimum, support_high + 1))
        if (
            not support
            or tuple(sorted(set(support))) != support
            or support[0] < self.minimum
            or support[-1] > self.maximum
            or support_high != support[-1]
        ):
            raise ValueError("pending actuation support is invalid")
        self.pending = _PendingActuation(
            snapshot_frame=snapshot_frame,
            issue_frame=issue_frame,
            expected_mask=expected_mask & self.supported_mask,
            support_high=support_high,
            support=support,
        )

    def pending_estimate(
        self,
        *,
        frame: int,
    ) -> PendingCommandEstimate | None:
        """Return estimator support conditioned on final input still unseen.

        The subtraction is from ``snapshot_frame`` by construction. Consumers
        must not reinterpret the result as a post-issue publication deadline.
        """

        pending = self.pending
        if pending is None:
            return None
        snapshot_age = max(0, frame - pending.snapshot_frame)
        remaining = tuple(
            delay - snapshot_age for delay in pending.support if delay > snapshot_age
        )
        overdue = not remaining
        if overdue:
            # The native observation has already disproved the modeled upper
            # support. Keep one conservative future frame instead of silently
            # treating the unobserved desired action as active.
            remaining = (1,)
        return PendingCommandEstimate(
            expected_mask=pending.expected_mask,
            remaining_frames=remaining,
            snapshot_age=snapshot_age,
            issue_age=max(0, frame - pending.issue_frame),
            overdue=overdue,
        )

    def record_computation_lag(self, lag: int) -> None:
        if 0 <= lag < 120:
            self.computation_lags.append(lag)

    def register_hit(self, frame: int) -> None:
        self.guard_until = max(
            self.guard_until,
            frame + self.guard_frames,
        )

    def register_deadline_miss(
        self,
        *,
        frame: int,
        observed_lag: int,
    ) -> None:
        """Retain a proven delay lower bound even when no action is issued.

        A proposal whose issue epoch exceeds its modeled support must remain
        held. That no-write transaction cannot later produce a visible-input
        sample, however, so the observed snapshot-to-issue lag has to widen
        the next estimate directly or the controller can self-lock forever.
        One default pickup frame is included because ``observed_lag`` ends at
        issue, before a newly issued final mask can become observable.
        """

        if frame < 0 or observed_lag < 0:
            raise ValueError("deadline evidence cannot be negative")
        if frame > self.deadline_floor_until:
            self.deadline_support_floor = self.minimum
        self.deadline_support_floor = max(
            self.deadline_support_floor,
            min(
                self.maximum,
                observed_lag + self.default_pickup_frames,
            ),
        )
        self.deadline_floor_until = max(
            self.deadline_floor_until,
            frame + self.guard_frames,
        )
        self.guard_until = max(
            self.guard_until,
            frame + self.guard_frames,
        )
        self.deadline_misses += 1

    def estimate(self, *, frame: int, default: int = 2) -> DelayEstimate:
        guard_active = frame <= self.guard_until
        if self.end_to_end_lags:
            values = tuple(self.end_to_end_lags)
            low = _nearest_rank(values, 0.10)
            nominal = _nearest_rank(values, 0.75)
            high = _nearest_rank(values, 0.95)
            if len(values) < 12:
                high += 1
            high = max(high, max(values[-8:]))
        elif self.computation_lags:
            computation = tuple(self.computation_lags)
            pickup = tuple(self.pickup_lags) or (self.default_pickup_frames,)
            low = _nearest_rank(computation, 0.10) + _nearest_rank(pickup, 0.10)
            nominal = _nearest_rank(computation, 0.75) + _nearest_rank(pickup, 0.50)
            high = _nearest_rank(computation, 0.95) + _nearest_rank(pickup, 0.95)
            high = max(high, nominal + 1)
        else:
            low = default
            nominal = default + 1
            high = default + 1
        if guard_active:
            high += 1
        if frame <= self.deadline_floor_until:
            high = max(high, self.deadline_support_floor)
        low = max(self.minimum, min(self.maximum, low))
        high = max(low, min(self.maximum, high))
        nominal = max(low, min(high, nominal))
        return DelayEstimate(
            nominal=nominal,
            support=tuple(range(low, high + 1)),
            computation_samples=len(self.computation_lags),
            pickup_samples=len(self.pickup_lags),
            end_to_end_samples=len(self.end_to_end_lags),
            guard_active=guard_active,
            overruns=self.overruns,
            censored=self.censored,
            deadline_misses=self.deadline_misses,
        )
