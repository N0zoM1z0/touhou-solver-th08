"""One-shot, pre-plan action-neutral shipped runtime-ECL identity observation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import time
from typing import Callable

from th08_runtime.game_state import EXPECTED_EXE_SHA256

from .runtime_ecl_image import (
    RuntimeEclImageCapture,
    RuntimeEclImageError,
    RuntimeEclImageIdentity,
    RuntimeEclImageReader,
    capture_runtime_ecl_image,
    compare_runtime_ecl_image,
)
from .trace import TraceSink


_CAPTURE_ERRORS = (
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    struct.error,
)


@dataclass(frozen=True, slots=True)
class RuntimeEclPhysicalProvenance:
    """Physical identity available at one stable pre-plan capture."""

    pid: int
    executable_sha256: str
    route_id: int
    difficulty_index: int
    stage_route_index: int
    gameplay_epoch: int
    decision_frame: int
    snapshot_frame: int
    gameplay_active: bool


@dataclass(frozen=True, slots=True)
class RuntimeEclIdentityDependencies:
    capture: Callable[..., RuntimeEclImageCapture] = capture_runtime_ecl_image
    compare: Callable[
        [RuntimeEclImageCapture, bytes],
        RuntimeEclImageIdentity,
    ] = compare_runtime_ecl_image
    clock: Callable[[], float] = time.perf_counter


@dataclass(frozen=True, slots=True)
class RuntimeEclIdentityAttempt:
    """One visible terminal attempt for the configured physical identity."""

    record: dict[str, object]
    emit_ms: float


@dataclass(frozen=True, slots=True)
class RuntimeEclAcceptedVersion:
    """Exact immutable runtime/static image binding for later trace work."""

    runtime_base: int
    image_length: int
    relocated_sha256: str
    normalized_sha256: str
    static_sha256: str
    route_id: int
    difficulty_index: int
    stage_route_index: int
    gameplay_epoch: int
    decision_frame: int
    snapshot_frame: int

    def record(self) -> dict[str, object]:
        return {
            "schema": "th08-runtime-ecl-accepted-version-v1",
            "runtime_base": self.runtime_base,
            "image_length": self.image_length,
            "relocated_sha256": self.relocated_sha256,
            "normalized_sha256": self.normalized_sha256,
            "static_sha256": self.static_sha256,
            "route_id": self.route_id,
            "difficulty_index": self.difficulty_index,
            "stage_route_index": self.stage_route_index,
            "gameplay_epoch": self.gameplay_epoch,
            "decision_frame": self.decision_frame,
            "snapshot_frame": self.snapshot_frame,
        }


class RuntimeEclIdentityService:
    """Attempt exactly once when the configured physical stage is observed."""

    def __init__(
        self,
        *,
        static_image: bytes,
        static_label: str,
        expected_static_sha256: str,
        expected_route_id: int,
        expected_difficulty_index: int,
        expected_stage_route_index: int,
        expected_executable_sha256: str = EXPECTED_EXE_SHA256,
        dependencies: RuntimeEclIdentityDependencies = (
            RuntimeEclIdentityDependencies()
        ),
    ) -> None:
        if not static_label:
            raise ValueError("runtime ECL static label cannot be empty")
        expected_digest = expected_static_sha256.lower()
        if (
            len(expected_digest) != 64
            or any(character not in "0123456789abcdef" for character in expected_digest)
        ):
            raise ValueError("runtime ECL static SHA-256 is invalid")
        actual_digest = hashlib.sha256(static_image).hexdigest()
        if actual_digest != expected_digest:
            raise RuntimeEclImageError(
                "runtime ECL static image SHA-256 does not match the "
                "declared immutable input"
            )
        if expected_route_id < 0:
            raise ValueError("runtime ECL route id cannot be negative")
        if expected_difficulty_index < 0:
            raise ValueError("runtime ECL difficulty cannot be negative")
        if expected_stage_route_index < 0:
            raise ValueError("runtime ECL stage cannot be negative")
        self._static_image = static_image
        self._static_label = static_label
        self._static_sha256 = actual_digest
        self._expected_route_id = expected_route_id
        self._expected_difficulty_index = expected_difficulty_index
        self._expected_stage_route_index = expected_stage_route_index
        self._expected_executable_sha256 = (
            expected_executable_sha256.lower()
        )
        self._dependencies = dependencies
        self._attempted = False
        self._accepted_version: RuntimeEclAcceptedVersion | None = None

    @property
    def attempted(self) -> bool:
        return self._attempted

    @property
    def accepted_version(self) -> RuntimeEclAcceptedVersion | None:
        return self._accepted_version

    def _matches_trigger(
        self,
        provenance: RuntimeEclPhysicalProvenance,
    ) -> bool:
        return (
            provenance.gameplay_active
            and provenance.route_id == self._expected_route_id
            and provenance.difficulty_index
            == self._expected_difficulty_index
            and provenance.stage_route_index
            == self._expected_stage_route_index
        )

    def observe_if_due(
        self,
        reader: RuntimeEclImageReader,
        trace_sink: TraceSink,
        *,
        provenance: RuntimeEclPhysicalProvenance,
    ) -> RuntimeEclIdentityAttempt | None:
        """Publish the first matching attempt, including terminal failures."""

        if self._attempted or not self._matches_trigger(provenance):
            return None
        self._attempted = True
        started = self._dependencies.clock()
        capture: RuntimeEclImageCapture | None = None
        identity: RuntimeEclImageIdentity | None = None
        error_text: str | None = None

        if (
            provenance.pid <= 0
            or provenance.executable_sha256.lower()
            != self._expected_executable_sha256
        ):
            status = "physical_identity_mismatch"
            error_text = "observed executable identity does not match"
        else:
            try:
                capture = self._dependencies.capture(
                    reader,
                    clock=self._dependencies.clock,
                )
                identity = self._dependencies.compare(
                    capture,
                    self._static_image,
                )
                status = (
                    "exact_match" if identity.exact_match else "byte_mismatch"
                )
                if identity.exact_match:
                    self._accepted_version = RuntimeEclAcceptedVersion(
                        runtime_base=capture.runtime_base,
                        image_length=capture.image_length,
                        relocated_sha256=capture.relocated_sha256,
                        normalized_sha256=capture.normalized_sha256,
                        static_sha256=identity.static_sha256,
                        route_id=provenance.route_id,
                        difficulty_index=provenance.difficulty_index,
                        stage_route_index=provenance.stage_route_index,
                        gameplay_epoch=provenance.gameplay_epoch,
                        decision_frame=provenance.decision_frame,
                        snapshot_frame=provenance.snapshot_frame,
                    )
            except _CAPTURE_ERRORS as error:
                status = "capture_error"
                error_text = f"{type(error).__name__}: {error}"

        transaction_ms = (
            self._dependencies.clock() - started
        ) * 1000.0
        record: dict[str, object] = {
            "schema": "th08-runtime-ecl-identity-observation-v1",
            "kind": "runtime_ecl_identity",
            "status": status,
            "authority": "trace_only_instruction_byte_identity",
            "pid": provenance.pid,
            "executable_sha256": provenance.executable_sha256.lower(),
            "route_id": provenance.route_id,
            "difficulty_index": provenance.difficulty_index,
            "stage_route_index": provenance.stage_route_index,
            "gameplay_epoch": provenance.gameplay_epoch,
            "decision_frame": provenance.decision_frame,
            "snapshot_frame": provenance.snapshot_frame,
            "static_image": {
                "label": self._static_label,
                "length": len(self._static_image),
                "sha256": self._static_sha256,
            },
            "capture": capture.record() if capture is not None else None,
            "identity": identity.record() if identity is not None else None,
            "error": error_text,
            "transaction_ms": transaction_ms,
        }
        emit_ms = trace_sink.emit(record, flush=True, measure=True)
        return RuntimeEclIdentityAttempt(record=record, emit_ms=emit_ms)


__all__ = [
    "RuntimeEclAcceptedVersion",
    "RuntimeEclIdentityAttempt",
    "RuntimeEclIdentityDependencies",
    "RuntimeEclIdentityService",
    "RuntimeEclPhysicalProvenance",
]
