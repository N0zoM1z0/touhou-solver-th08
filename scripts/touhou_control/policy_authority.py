"""Immutable version join for policy artifacts that may affect input."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .pipeline_identity import VersionIdentity


POLICY_AUTHORITY_VERSION_SCHEMA = "policy-authority-version-v1"


@dataclass(frozen=True)
class PolicyAuthorityVersion:
    """Bind one policy to every model family required by its consumer.

    Game adapters decide which identities are complete enough for action
    authority.  Keeping the join game-neutral makes the publication boundary
    explicit without teaching the corridor runtime about ECL or native game
    layouts.
    """

    root: VersionIdentity
    runtime_content: VersionIdentity | None
    time_scale: VersionIdentity
    future_hazard: VersionIdentity | None
    geometry: VersionIdentity
    policy: VersionIdentity
    schema: str = POLICY_AUTHORITY_VERSION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != POLICY_AUTHORITY_VERSION_SCHEMA:
            raise ValueError("unsupported policy authority version schema")

    @property
    def complete(self) -> bool:
        return (
            self.runtime_content is not None
            and self.future_hazard is not None
        )

    def record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "complete": self.complete,
            "root": self.root.record(),
            "runtime_content": (
                self.runtime_content.record()
                if self.runtime_content is not None
                else None
            ),
            "time_scale": self.time_scale.record(),
            "future_hazard": (
                self.future_hazard.record()
                if self.future_hazard is not None
                else None
            ),
            "geometry": self.geometry.record(),
            "policy": self.policy.record(),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.record(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "POLICY_AUTHORITY_VERSION_SCHEMA",
    "PolicyAuthorityVersion",
]
