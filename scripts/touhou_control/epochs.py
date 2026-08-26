"""Game-neutral frame-window alignment for asynchronously captured sensors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameWindow:
    """Inclusive frame-counter bounds around one sensor capture."""

    before: int
    after: int

    def __post_init__(self) -> None:
        if self.before < 0 or self.after < self.before:
            raise ValueError("invalid sensor frame window")

    @property
    def span(self) -> int:
        return self.after - self.before


@dataclass(frozen=True)
class HazardEpochAlignment:
    """Align a hazard snapshot and event snapshot to a source state."""

    source_frame: int
    hazard_window: FrameWindow
    current_frame: int
    event_window: FrameWindow | None = None

    def __post_init__(self) -> None:
        if self.source_frame < 0 or self.current_frame < 0:
            raise ValueError("frame counters cannot be negative")

    @property
    def source_to_hazard_lag(self) -> int:
        """Updates between the source state and hazard coordinates."""

        return max(0, self.hazard_window.after - self.source_frame)

    @property
    def hazard_age(self) -> int:
        """Updates between hazard coordinates and the planning epoch."""

        return max(0, self.current_frame - self.hazard_window.after)

    @property
    def hazard_age_support(self) -> tuple[int, ...]:
        """All snapshot ages allowed by a possibly straddled bulk read.

        A bulk pool read bracketed by two frame-counter observations can
        contain records from either endpoint (and every integer frame in
        between).  Relative to the final planning root, each such record is
        therefore between ``current-after`` and ``current-before`` updates
        old.  Keeping the complete discrete support avoids silently choosing
        either endpoint as though the read were atomic.
        """

        youngest = max(0, self.current_frame - self.hazard_window.after)
        oldest = max(0, self.current_frame - self.hazard_window.before)
        return tuple(range(youngest, oldest + 1))

    @property
    def event_frame_offset(self) -> int:
        """Rebase event-relative frames to the hazard coordinate epoch."""

        if self.event_window is None:
            return 0
        return max(0, self.event_window.after - self.hazard_window.after)

    @property
    def event_frame_uncertainty(self) -> int:
        """Conservative timing width contributed by both capture windows."""

        if self.event_window is None:
            return self.hazard_window.span
        return self.hazard_window.span + self.event_window.span

    @property
    def total_frame_extent(self) -> int:
        """Width of all source, capture, event, and planning timestamps."""

        frames = [
            self.source_frame,
            self.hazard_window.before,
            self.hazard_window.after,
            self.current_frame,
        ]
        if self.event_window is not None:
            frames.extend((self.event_window.before, self.event_window.after))
        return max(frames) - min(frames)

    def fits_epoch(self, *, maximum_extent: int) -> bool:
        """Whether one capture is plausibly contained in a single epoch."""

        if maximum_extent < 0:
            raise ValueError("maximum epoch extent cannot be negative")
        return self.total_frame_extent <= maximum_extent


@dataclass(frozen=True)
class ActionIssueAlignment:
    """Validate a planned action at the instant it would be issued.

    Sensor capture can be internally consistent and still become stale while
    the planner is running.  ``delay_support`` is the controller's modeled
    enemy-manager-frame snapshot-to-observed-final-input support, so the
    snapshot-to-issue lag is already a lower bound in that estimator
    coordinate.  It is not a post-issue native priority-17 callback deadline;
    converting it to one requires a separately validated phase adapter.
    """

    source_frame: int
    capture_frame: int
    issue_frame: int
    delay_support: tuple[int, ...]

    def __post_init__(self) -> None:
        if min(self.source_frame, self.capture_frame, self.issue_frame) < 0:
            raise ValueError("frame counters cannot be negative")
        if self.capture_frame < self.source_frame:
            raise ValueError("capture frame cannot precede source frame")
        if self.issue_frame < self.capture_frame:
            raise ValueError("issue frame cannot precede capture frame")
        if (
            not self.delay_support
            or tuple(sorted(set(self.delay_support))) != self.delay_support
            or self.delay_support[0] < 0
        ):
            raise ValueError("delay support must be sorted, unique, and nonnegative")

    @property
    def action_lag(self) -> int:
        """Observed snapshot-to-issue lag."""

        return self.issue_frame - self.source_frame

    @property
    def post_capture_advance(self) -> int:
        """Counter updates that occurred while planning."""

        return self.issue_frame - self.capture_frame

    @property
    def support_high(self) -> int:
        return self.delay_support[-1]

    @property
    def deadline_missed(self) -> bool:
        """Whether even zero additional pickup delay exceeds the model."""

        return self.action_lag > self.support_high

    def crosses_contiguous_epoch(
        self,
        *,
        maximum_post_capture_advance: int,
    ) -> bool:
        """Whether planning observed an implausibly large counter advance.

        This deliberately uses the post-capture interval rather than total
        action lag. A moderately slow plan is a deadline miss, not proof that
        the game's logical frame counter crossed an epoch.
        """

        if maximum_post_capture_advance < 0:
            raise ValueError("maximum contiguous advance cannot be negative")
        return self.post_capture_advance > maximum_post_capture_advance
