"""Value-only contract for TH08 current-pool callback composition joins."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from touhou_control.pipeline_identity import VersionIdentity


CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION = (
    "th08-current-pool-callback-composition-v2-source-callback12-14-scale"
)
CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION = (
    "th08-current-pool-callback-join-v2-projection-bullet-policy-scale-clocks"
)


@runtime_checkable
class CurrentPoolProjectionCallbackJoinContract(Protocol):
    """Runtime-safe surface consumed by global policy infrastructure."""

    bullets: object
    complete: bool
    bullet_root_frame: int
    policy_source_frame: int
    policy_horizon_frames: int
    time_scale_bits: int

    @property
    def version(self) -> VersionIdentity: ...

    def matches_projection(self, projection: object) -> bool: ...


__all__ = [
    "CURRENT_POOL_CALLBACK_COMPOSITION_SEMANTICS_VERSION",
    "CURRENT_POOL_CALLBACK_JOIN_SEMANTICS_VERSION",
    "CurrentPoolProjectionCallbackJoinContract",
]
