#!/usr/bin/env python3
"""Strict audit for one shipped runtime-ECL byte-identity observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from th08_runtime.game_state import EXPECTED_EXE_SHA256


SCHEMA = "th08-runtime-ecl-identity-physical-audit-v1"
TRACE_KIND = "runtime_ecl_identity"
OBSERVATION_SCHEMA = "th08-runtime-ecl-identity-observation-v1"
CAPTURE_SCHEMA = "th08-runtime-ecl-image-capture-v1"
IDENTITY_SCHEMA = "th08-runtime-ecl-image-identity-v1"
STAGE5_STATIC_LABEL = "artifacts/decoded/ecldata5.ecl"
STAGE5_STATIC_LENGTH = 47_224
STAGE5_STATIC_SHA256 = (
    "3148f45faf78bd8211a956edcdc353be73d2781995d3dadd36bdca8132f8fe19"
)


class RuntimeEclIdentityAuditError(ValueError):
    """Raised when retained identity evidence violates the fixed contract."""


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeEclIdentityAuditError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeEclIdentityAuditError(f"{label} must be an integer")
    return value


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeEclIdentityAuditError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise RuntimeEclIdentityAuditError(
            f"{label} must be finite and nonnegative"
        )
    return result


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RuntimeEclIdentityAuditError(
            f"{label} must be a lowercase SHA-256"
        )
    return value


def audit(
    trace: Path,
    *,
    expected_executable_sha256: str = EXPECTED_EXE_SHA256,
    expected_static_label: str = STAGE5_STATIC_LABEL,
    expected_static_length: int = STAGE5_STATIC_LENGTH,
    expected_static_sha256: str = STAGE5_STATIC_SHA256,
    expected_route_id: int = 2,
    expected_difficulty_index: int = 3,
    expected_stage_route_index: int = 5,
) -> dict[str, object]:
    trace_digest = hashlib.sha256()
    trace_bytes = 0
    observations: list[dict[str, Any]] = []
    decision_frames: list[int] = []
    bomb_violation_frames: list[int] = []
    summaries: list[dict[str, Any]] = []
    with trace.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            trace_digest.update(raw_line)
            trace_bytes += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise RuntimeEclIdentityAuditError(
                    f"line {line_number} is not valid JSON: {error}"
                ) from error
            if not isinstance(row, dict):
                raise RuntimeEclIdentityAuditError(
                    f"line {line_number} is not a JSON object"
                )
            kind = row.get("kind")
            if kind == TRACE_KIND:
                observations.append(row)
            elif kind == "decision":
                frame = _integer(
                    row.get("frame"),
                    f"line {line_number} frame",
                )
                decision_frames.append(frame)
                mask = _integer(
                    row.get("mask"),
                    f"line {line_number} mask",
                )
                if mask & 0x02 or row.get("bomb") is not False:
                    bomb_violation_frames.append(frame)
            elif kind == "summary":
                summaries.append(row)

    if len(observations) != 1:
        raise RuntimeEclIdentityAuditError(
            "trace must contain exactly one runtime-ECL identity observation"
        )
    if not summaries or summaries[-1].get("termination_reason") != (
        "route_complete"
    ):
        raise RuntimeEclIdentityAuditError(
            "trace does not end in route_complete"
        )
    if bomb_violation_frames:
        raise RuntimeEclIdentityAuditError(
            "trace contains a Bomb decision"
        )
    row = observations[0]
    if row.get("schema") != OBSERVATION_SCHEMA:
        raise RuntimeEclIdentityAuditError("observation schema is invalid")
    if row.get("status") != "exact_match":
        raise RuntimeEclIdentityAuditError(
            f"runtime ECL identity did not match: {row.get('status')}"
        )
    if row.get("authority") != "trace_only_instruction_byte_identity":
        raise RuntimeEclIdentityAuditError(
            "runtime ECL authority label is invalid"
        )
    if row.get("error") is not None:
        raise RuntimeEclIdentityAuditError(
            "exact runtime ECL identity row contains an error"
        )

    expected_fields = {
        "executable_sha256": expected_executable_sha256,
        "route_id": expected_route_id,
        "difficulty_index": expected_difficulty_index,
        "stage_route_index": expected_stage_route_index,
    }
    for key, expected in expected_fields.items():
        if row.get(key) != expected:
            raise RuntimeEclIdentityAuditError(
                f"observation {key} does not match the fixed workload"
            )
    if _integer(row.get("pid"), "pid") <= 0:
        raise RuntimeEclIdentityAuditError("pid must be positive")
    decision_frame = _integer(row.get("decision_frame"), "decision_frame")
    snapshot_frame = _integer(row.get("snapshot_frame"), "snapshot_frame")
    gameplay_epoch = _integer(row.get("gameplay_epoch"), "gameplay_epoch")
    if min(decision_frame, snapshot_frame, gameplay_epoch) < 0:
        raise RuntimeEclIdentityAuditError(
            "frame and epoch provenance cannot be negative"
        )

    static = _mapping(row.get("static_image"), "static_image")
    if static.get("label") != expected_static_label:
        raise RuntimeEclIdentityAuditError("static image label is invalid")
    if static.get("length") != expected_static_length:
        raise RuntimeEclIdentityAuditError("static image length is invalid")
    if static.get("sha256") != expected_static_sha256:
        raise RuntimeEclIdentityAuditError("static image SHA-256 is invalid")

    capture = _mapping(row.get("capture"), "capture")
    if capture.get("schema") != CAPTURE_SCHEMA:
        raise RuntimeEclIdentityAuditError("capture schema is invalid")
    if capture.get("image_length") != expected_static_length:
        raise RuntimeEclIdentityAuditError(
            "runtime ECL image length is invalid"
        )
    if capture.get("read_count") != 4:
        raise RuntimeEclIdentityAuditError(
            "runtime ECL capture did not use exactly four reads"
        )
    runtime_base = _integer(capture.get("runtime_base"), "runtime_base")
    if not 0x00010000 <= runtime_base <= 0xFFFFFFFF:
        raise RuntimeEclIdentityAuditError("runtime ECL base is invalid")
    if _integer(capture.get("subroutine_count"), "subroutine_count") <= 0:
        raise RuntimeEclIdentityAuditError(
            "runtime ECL subroutine count is invalid"
        )
    timeline_count = _integer(
        capture.get("timeline_count"),
        "timeline_count",
    )
    if not 0 <= timeline_count < 16:
        raise RuntimeEclIdentityAuditError(
            "runtime ECL timeline count is invalid"
        )
    relocated_sha256 = _sha256(
        capture.get("relocated_sha256"),
        "relocated_sha256",
    )
    normalized_sha256 = _sha256(
        capture.get("normalized_sha256"),
        "normalized_sha256",
    )
    if normalized_sha256 != expected_static_sha256:
        raise RuntimeEclIdentityAuditError(
            "normalized runtime digest differs from the static image"
        )
    capture_ms = _finite_nonnegative(
        capture.get("capture_ms"),
        "capture_ms",
    )

    identity = _mapping(row.get("identity"), "identity")
    if identity.get("schema") != IDENTITY_SCHEMA:
        raise RuntimeEclIdentityAuditError("identity schema is invalid")
    if identity.get("exact_match") is not True:
        raise RuntimeEclIdentityAuditError("exact_match is not true")
    if identity.get("static_sha256") != expected_static_sha256:
        raise RuntimeEclIdentityAuditError(
            "identity static digest is invalid"
        )
    if identity.get("normalized_runtime_sha256") != expected_static_sha256:
        raise RuntimeEclIdentityAuditError(
            "identity runtime digest is invalid"
        )
    if identity.get("image_length") != expected_static_length:
        raise RuntimeEclIdentityAuditError("identity length is invalid")
    if identity.get("first_difference_offset") is not None:
        raise RuntimeEclIdentityAuditError(
            "exact identity contains a first difference"
        )
    transaction_ms = _finite_nonnegative(
        row.get("transaction_ms"),
        "transaction_ms",
    )

    matching_indices = [
        index
        for index, frame in enumerate(decision_frames)
        if frame == decision_frame
    ]
    if len(matching_indices) != 1:
        raise RuntimeEclIdentityAuditError(
            "identity frame must match exactly one decision"
        )
    index = matching_indices[0]
    previous_frame = decision_frames[index - 1] if index > 0 else None
    next_frame = (
        decision_frames[index + 1]
        if index + 1 < len(decision_frames)
        else None
    )
    previous_delta = (
        decision_frame - previous_frame
        if previous_frame is not None
        else None
    )
    next_delta = (
        next_frame - decision_frame if next_frame is not None else None
    )
    if previous_delta is not None and previous_delta <= 0:
        raise RuntimeEclIdentityAuditError(
            "previous adjacent decision cadence is invalid"
        )
    if next_delta is not None and next_delta <= 0:
        raise RuntimeEclIdentityAuditError(
            "next adjacent decision cadence is invalid"
        )

    return {
        "schema": SCHEMA,
        "passed": True,
        "source": {
            "trace_name": trace.name,
            "trace_bytes": trace_bytes,
            "trace_sha256": trace_digest.hexdigest(),
        },
        "fixed_workload": {
            "executable_sha256": expected_executable_sha256,
            "route_id": expected_route_id,
            "difficulty_index": expected_difficulty_index,
            "stage_route_index": expected_stage_route_index,
            "static_label": expected_static_label,
            "static_length": expected_static_length,
            "static_sha256": expected_static_sha256,
        },
        "observation": {
            "pid": row["pid"],
            "gameplay_epoch": gameplay_epoch,
            "decision_frame": decision_frame,
            "snapshot_frame": snapshot_frame,
            "runtime_base": runtime_base,
            "subroutine_count": capture["subroutine_count"],
            "timeline_count": timeline_count,
            "read_count": capture["read_count"],
            "relocated_sha256": relocated_sha256,
            "normalized_sha256": normalized_sha256,
            "capture_ms": capture_ms,
            "transaction_ms": transaction_ms,
            "status": row["status"],
            "first_difference_offset": identity[
                "first_difference_offset"
            ],
        },
        "physical_scope": {
            "decision_count": len(decision_frames),
            "termination_reason": summaries[-1]["termination_reason"],
            "bomb_violation_frames": bomb_violation_frames,
            "hard_no_bomb_passed": True,
        },
        "adjacent_decision_cadence": {
            "previous_frame": previous_frame,
            "previous_delta": previous_delta,
            "next_frame": next_frame,
            "next_delta": next_delta,
        },
        "authority": {
            "runtime_instruction_bytes": "exact_for_this_immutable_image",
            "source_completeness": "none",
            "future_geometry": "none",
            "planner": "none",
            "physical_action": "none",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
