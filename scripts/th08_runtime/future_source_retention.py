"""Content-addressed retention for coherent TH08 future-source roots."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from th08_ordinary_future_sources import (
    ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION,
)
from th08_runtime.current_hazard_root import current_hazards_from_root


RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V1 = (
    "th08-retained-ordinary-future-source-root-v1"
)
RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2 = (
    "th08-retained-ordinary-future-source-root-v2-current-hazards"
)
RETAINED_FUTURE_SOURCE_ROOT_SCHEMA = RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2
_SUPPORTED_ROOT_SCHEMAS = frozenset(
    (
        RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V1,
        RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2,
    )
)
_ROOT_NAME = re.compile(
    r"^sha256-([0-9a-f]{64})\.th08-future-root\.json\.gz$"
)


@dataclass(frozen=True)
class RetainedFutureSourceRoot:
    """Immutable locator and integrity metadata for one retained root."""

    path: Path
    sha256: str
    canonical_size_bytes: int
    compressed_size_bytes: int
    root_frame: int
    spell_id: int | None
    created: bool
    schema: str

    def record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "path": str(self.path),
            "sha256": self.sha256,
            "canonical_size_bytes": self.canonical_size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "root_frame": self.root_frame,
            "spell_id": self.spell_id,
            "created": self.created,
            "role": "shadow_capture_only_no_action_authority",
        }


@dataclass(frozen=True)
class FutureSourceRetentionExpectation:
    """Exact gameplay context required before a root may consume quota."""

    route_id: int
    difficulty_index: int
    stage_route_index: int
    spell_id: int

    def __post_init__(self) -> None:
        if self.route_id < 0:
            raise ValueError("retained-root route ID cannot be negative")
        if self.difficulty_index < 0:
            raise ValueError(
                "retained-root difficulty index cannot be negative"
            )
        if self.stage_route_index < 0:
            raise ValueError(
                "retained-root stage route index cannot be negative"
            )
        if not 0 <= self.spell_id <= 255:
            raise ValueError("retained-root spell ID is out of range")

    def record(self) -> dict[str, int]:
        return {
            "route_id": self.route_id,
            "difficulty_index": self.difficulty_index,
            "stage_route_index": self.stage_route_index,
            "spell_id": self.spell_id,
            "player_phase": 0,
            "bomb_active": 0,
        }


def future_source_retention_rejection_reason(
    snapshot: Any,
    expectation: FutureSourceRetentionExpectation,
) -> str | None:
    """Return why an asynchronous snapshot is not a planner-root sample."""

    if not snapshot.stable:
        return "capture_clock_incoherent"
    payload = snapshot.payload
    if not isinstance(payload, dict):
        return "root_payload_not_mapping"
    compact = payload.get("compact_state")
    if not isinstance(compact, dict):
        return "compact_state_absent"
    for field, expected in expectation.record().items():
        actual = compact.get(field)
        if type(actual) is not int or actual != expected:
            return (
                f"captured_{field}_mismatch:"
                f"expected={expected},actual={actual!r}"
            )
    return None


def _canonical_bytes(record: dict[str, object]) -> bytes:
    try:
        text = json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "future-source root is not canonical-JSON serializable"
        ) from error
    return (text + "\n").encode("utf-8")


def _deterministic_gzip(canonical: bytes) -> bytes:
    compressed = bytearray(
        gzip.compress(canonical, compresslevel=6, mtime=0)
    )
    # Python 3.11 may delegate mtime=0 to zlib and inherit its platform OS
    # byte.  RFC 1952 defines 255 as unknown; pinning it makes the wrapper
    # stable across the Linux audit host and Win32 capture process.
    if len(compressed) < 10:
        raise RuntimeError("future-source gzip encoder returned a short header")
    compressed[9] = 255
    return bytes(compressed)


def _required_mapping(
    payload: object,
    key: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is malformed")
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{label}.{key} is malformed")
    return value


def _required_nonnegative_int(
    payload: object,
    key: str,
    *,
    label: str,
) -> int:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is malformed")
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}.{key} is malformed")
    return value


def _validate_v2_root_clock_join(record: dict[str, object]) -> None:
    """Fail closed unless every retained planner input shares one root clock."""

    capture = _required_mapping(
        record,
        "capture_clock",
        label="v2 future-source root",
    )
    identity = _required_mapping(
        record,
        "root_identity",
        label="v2 future-source root",
    )
    projection = _required_mapping(
        record,
        "projection_at_capture",
        label="v2 future-source root",
    )
    root_payload = _required_mapping(
        record,
        "root_payload",
        label="v2 future-source root",
    )
    compact = _required_mapping(
        root_payload,
        "compact_state",
        label="v2 future-source root.root_payload",
    )
    if capture.get("stable") is not True:
        raise ValueError("v2 future-source root capture clock is not stable")

    frames = {
        "capture_clock.manager_frame_before": _required_nonnegative_int(
            capture,
            "manager_frame_before",
            label="v2 future-source root.capture_clock",
        ),
        "capture_clock.manager_frame_after": _required_nonnegative_int(
            capture,
            "manager_frame_after",
            label="v2 future-source root.capture_clock",
        ),
        "root_identity.manager_frame": _required_nonnegative_int(
            identity,
            "manager_frame",
            label="v2 future-source root.root_identity",
        ),
        "projection_at_capture.root_frame": _required_nonnegative_int(
            projection,
            "root_frame",
            label="v2 future-source root.projection_at_capture",
        ),
        "root_payload.compact_state.manager_frame": (
            _required_nonnegative_int(
                compact,
                "manager_frame",
                label=(
                    "v2 future-source root.root_payload.compact_state"
                ),
            )
        ),
    }
    root_frame = next(iter(frames.values()))
    if any(frame != root_frame for frame in frames.values()):
        detail = ",".join(f"{key}={value}" for key, value in frames.items())
        raise ValueError(f"v2 future-source root clocks disagree: {detail}")

    serial_before = _required_nonnegative_int(
        capture,
        "frscreen_update_serial_before",
        label="v2 future-source root.capture_clock",
    )
    serial_after = _required_nonnegative_int(
        capture,
        "frscreen_update_serial_after",
        label="v2 future-source root.capture_clock",
    )
    if serial_before != serial_after:
        raise ValueError("v2 future-source root update serials disagree")
    if "current_hazard_root" not in record:
        raise ValueError("v2 future-source root lacks current hazards")
    current_hazards_from_root(
        record["current_hazard_root"],
        expected_root_frame=root_frame,
    )


def _root_record(
    snapshot: Any,
    closure: Any,
    *,
    snapshot_schema: str,
    requested_horizon_frames: int,
) -> dict[str, object]:
    payload = snapshot.payload
    if not isinstance(payload, dict):
        raise TypeError("future-source snapshot payload is not a mapping")
    compact = payload.get("compact_state")
    if not isinstance(compact, dict):
        raise TypeError("future-source compact root is absent")
    timeline = payload.get("stage_timeline_runtime")
    if not isinstance(timeline, dict):
        raise TypeError("future-source timeline root is absent")
    ecl_file = timeline.get("ecl_file")
    if not isinstance(ecl_file, dict):
        raise TypeError("future-source runtime ECL identity is absent")
    canonical_ecl_sha256 = ecl_file.get("canonical_sha256")
    if not isinstance(canonical_ecl_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", canonical_ecl_sha256
    ):
        raise ValueError("future-source runtime ECL SHA-256 is malformed")

    projection = closure.projection
    coverage = projection.coverage
    current_hazard_root = getattr(snapshot, "current_hazard_root", None)
    schema = (
        RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2
        if current_hazard_root is not None
        else RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V1
    )
    record: dict[str, object] = {
        "schema": schema,
        "role": "coherent_physical_root_shadow_only_no_action_authority",
        "snapshot_semantics": snapshot_schema,
        "future_source_semantics": (
            ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION
        ),
        "capture_clock": {
            "manager_frame_before": int(snapshot.frame_before),
            "manager_frame_after": int(snapshot.frame_after),
            "frscreen_update_serial_before": int(
                snapshot.update_serial_before
            ),
            "frscreen_update_serial_after": int(
                snapshot.update_serial_after
            ),
            "stable": bool(snapshot.stable),
        },
        "root_identity": {
            "manager_frame": int(compact["manager_frame"]),
            "route_id": int(compact["route_id"]),
            "difficulty_index": (
                int(compact["difficulty_index"])
                if "difficulty_index" in compact
                else None
            ),
            "stage_route_index": (
                int(compact["stage_route_index"])
                if "stage_route_index" in compact
                else None
            ),
            "spell_id": (
                int(compact["spell_id"])
                if compact.get("spell_id") is not None
                else None
            ),
            "runtime_ecl_canonical_sha256": canonical_ecl_sha256,
        },
        "projection_at_capture": {
            "requested_horizon_frames": int(requested_horizon_frames),
            "root_frame": int(projection.root_frame),
            "horizon_frame": int(projection.horizon_frame),
            "horizon_frames": int(projection.horizon_frames),
            "source_closure_complete": bool(
                projection.source_closure_complete
            ),
            "source_closure_reason": projection.source_closure_reason,
            "causal_prefix_reason": closure.causal_prefix_reason,
            "coverage_complete": bool(coverage.complete),
            "projection_digest": projection.digest,
            "source_count": int(closure.source_count),
            "auxiliary_count": int(closure.auxiliary_count),
            "silent_child_count": int(closure.silent_child_count),
            "timeline_steps": int(closure.timeline_steps),
            "timeline_spawn_count": int(closure.timeline_spawn_count),
            "direct_fire_event_count": len(closure.direct_fire_events),
        },
        "root_payload": payload,
    }
    if current_hazard_root is not None:
        record["current_hazard_root"] = current_hazard_root
        _validate_v2_root_clock_join(record)
    return record


def write_retained_future_source_root(
    snapshot: Any,
    closure: Any,
    destination: Path,
    *,
    snapshot_schema: str,
    requested_horizon_frames: int,
) -> RetainedFutureSourceRoot:
    """Write one deterministic capsule without changing gameplay state."""

    if not snapshot.stable:
        raise ValueError("refusing to retain an incoherent future-source root")
    record = _root_record(
        snapshot,
        closure,
        snapshot_schema=snapshot_schema,
        requested_horizon_frames=requested_horizon_frames,
    )
    canonical = _canonical_bytes(record)
    digest = hashlib.sha256(canonical).hexdigest()
    compressed = _deterministic_gzip(canonical)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (
        f"sha256-{digest}.th08-future-root.json.gz"
    )
    created = not path.exists()
    if created:
        temporary = destination / f".{path.name}.{os.getpid()}.tmp"
        try:
            temporary.write_bytes(compressed)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        try:
            existing_canonical = gzip.decompress(path.read_bytes())
        except (OSError, EOFError, zlib.error) as error:
            raise RuntimeError(
                "content-addressed future-source root is unreadable"
            ) from error
        if existing_canonical != canonical:
            raise RuntimeError(
                "content-addressed future-source root has conflicting bytes"
            )
    compact = snapshot.payload["compact_state"]
    return RetainedFutureSourceRoot(
        path=path,
        sha256=digest,
        canonical_size_bytes=len(canonical),
        compressed_size_bytes=path.stat().st_size,
        root_frame=int(compact["manager_frame"]),
        spell_id=(
            int(compact["spell_id"])
            if compact.get("spell_id") is not None
            else None
        ),
        created=created,
        schema=str(record["schema"]),
    )


def read_retained_future_source_root(path: Path) -> dict[str, object]:
    """Read and integrity-check a content-addressed root capsule."""

    match = _ROOT_NAME.fullmatch(path.name)
    if match is None:
        raise ValueError("future-source root filename is not content-addressed")
    try:
        canonical = gzip.decompress(path.read_bytes())
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("future-source root gzip stream is invalid") from error
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != match.group(1):
        raise ValueError("future-source root SHA-256 mismatch")
    try:
        record = json.loads(canonical)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("future-source root JSON is invalid") from error
    if not isinstance(record, dict):
        raise ValueError("future-source root JSON is not an object")
    schema = record.get("schema")
    if schema not in _SUPPORTED_ROOT_SCHEMAS:
        raise ValueError("future-source root schema is unsupported")
    if _canonical_bytes(record) != canonical:
        raise ValueError("future-source root JSON is not canonical")
    root_identity = record.get("root_identity")
    if not isinstance(root_identity, dict):
        raise ValueError("future-source root identity is malformed")
    root_frame = root_identity.get("manager_frame")
    if type(root_frame) is not int or root_frame < 0:
        raise ValueError("future-source root manager frame is malformed")
    if schema == RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2:
        _validate_v2_root_clock_join(record)
    elif "current_hazard_root" in record:
        raise ValueError("v1 future-source root cannot carry current hazards")
    return record


__all__ = [
    "FutureSourceRetentionExpectation",
    "RETAINED_FUTURE_SOURCE_ROOT_SCHEMA",
    "RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V1",
    "RETAINED_FUTURE_SOURCE_ROOT_SCHEMA_V2",
    "RetainedFutureSourceRoot",
    "future_source_retention_rejection_reason",
    "read_retained_future_source_root",
    "write_retained_future_source_root",
]
