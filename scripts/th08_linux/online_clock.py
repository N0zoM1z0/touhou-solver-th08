"""Fail-closed binding between TH08 input epochs and manager-frame policies."""

from __future__ import annotations

from dataclasses import dataclass


GAMEPLAY_ACTIVE_MASK = 0x0004
MANAGER_SKIP_UPDATE_MASK = 0x0400
UNCONTROLLABLE_PLAYER_PHASES = frozenset((1, 2))


@dataclass(frozen=True, slots=True)
class OnlineClockObservation:
    """One post-update root on both clocks used by online control."""

    source_input_epoch: int
    captured_source_input_epoch: int | None
    manager_frame: int
    engine_flags: int
    player_phase: int
    bomb_active: bool
    dialogue_active: bool | None
    scripted_update_freeze: bool | None
    context: tuple[int, int, int | None]


@dataclass(frozen=True, slots=True)
class OnlineClockAssessment:
    """Whether manager-frame policy time is a physical-input-frame surrogate."""

    allowed: bool
    reason: str
    generation: int
    input_manager_offset: int | None
    input_delta: int | None = None
    manager_delta: int | None = None


class OnlineUnitCadenceAuthority:
    """Certify a local 1:1 input-epoch/manager-frame interval.

    The manager counter is useful for ECL and hazard geometry, but it is not a
    universal physical clock.  This tracker gives it online action authority
    only after two coherent safe roots establish an affine 1:1 mapping.  Any
    dialogue, scripted freeze, manager skip, hit/Bomb state, context change, or
    unequal clock delta invalidates all work from the previous generation.
    """

    def __init__(self) -> None:
        self._context: tuple[int, int, int | None] | None = None
        self._previous: OnlineClockObservation | None = None
        self._allowed = False
        self._generation = 0
        self._offset: int | None = None
        self.certified_observations = 0
        self.rejected_observations = 0
        self.delta_mismatches = 0

    @property
    def generation(self) -> int:
        return self._generation

    @staticmethod
    def _root_gate(observation: OnlineClockObservation) -> str | None:
        if observation.source_input_epoch <= 0:
            return "input-epoch-invalid"
        if observation.captured_source_input_epoch != observation.source_input_epoch:
            return "captured-input-epoch-mismatch"
        if not 0 <= observation.manager_frame <= 0xFFFFFFFF:
            return "manager-frame-invalid"
        if not observation.engine_flags & GAMEPLAY_ACTIVE_MASK:
            return "gameplay-inactive"
        if observation.engine_flags & MANAGER_SKIP_UPDATE_MASK:
            return "manager-update-skipped"
        if observation.player_phase in UNCONTROLLABLE_PLAYER_PHASES:
            return "player-uncontrollable"
        if observation.bomb_active:
            return "bomb-active"
        if observation.dialogue_active is None:
            return "dialogue-clock-unknown"
        if observation.dialogue_active:
            return "dialogue-active"
        if observation.scripted_update_freeze is None:
            return "scripted-update-freeze-unknown"
        if observation.scripted_update_freeze:
            return "scripted-update-freeze-active"
        return None

    def _invalidate(self) -> None:
        if self._allowed or self._previous is not None or self._offset is not None:
            self._generation += 1
        self._allowed = False
        self._offset = None
        self._previous = None

    def observe(
        self,
        observation: OnlineClockObservation,
    ) -> OnlineClockAssessment:
        if observation.context != self._context:
            self._invalidate()
            self._context = observation.context

        gate_reason = self._root_gate(observation)
        if gate_reason is not None:
            self._invalidate()
            self.rejected_observations += 1
            return OnlineClockAssessment(
                False,
                gate_reason,
                self._generation,
                None,
            )

        previous = self._previous
        if previous is None:
            self._previous = observation
            self._allowed = False
            self._offset = None
            self.rejected_observations += 1
            return OnlineClockAssessment(
                False,
                "unit-cadence-needs-successor",
                self._generation,
                None,
            )

        input_delta = observation.source_input_epoch - previous.source_input_epoch
        manager_delta = (
            observation.manager_frame - previous.manager_frame
        ) & 0xFFFFFFFF
        if (
            input_delta <= 0
            or manager_delta == 0
            or manager_delta > 0x7FFFFFFF
            or input_delta != manager_delta
        ):
            self.delta_mismatches += 1
            self._invalidate()
            # This safe root is the first candidate root of a new mapping.
            self._previous = observation
            self.rejected_observations += 1
            return OnlineClockAssessment(
                False,
                "input-manager-cadence-mismatch",
                self._generation,
                None,
                input_delta=input_delta,
                manager_delta=manager_delta,
            )

        self._previous = observation
        self._allowed = True
        self._offset = observation.source_input_epoch - observation.manager_frame
        self.certified_observations += 1
        return OnlineClockAssessment(
            True,
            "unit-input-manager-cadence",
            self._generation,
            self._offset,
            input_delta=input_delta,
            manager_delta=manager_delta,
        )


__all__ = (
    "GAMEPLAY_ACTIVE_MASK",
    "MANAGER_SKIP_UPDATE_MASK",
    "OnlineClockAssessment",
    "OnlineClockObservation",
    "OnlineUnitCadenceAuthority",
)
