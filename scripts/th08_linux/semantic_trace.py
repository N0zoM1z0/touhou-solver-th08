"""Exact JSONL traces and first-divergence reports for semantic spines."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import gzip
import json
from pathlib import Path
from typing import Literal


TRACE_COMPARISON_SCHEMA = "th08-semantic-spine-comparison-v1"
MANAGER_FRAME_TRANSITION_ADVANCED = "advanced"
MANAGER_FRAME_TRANSITION_SAME = "same"
_ABSENT = object()


def classify_manager_frame_transition(
    *,
    previous: int,
    observed: int,
) -> Literal["advanced", "same"]:
    """Classify the non-universal manager clock across input epochs.

    Every calculation-chain restart is a real logical input epoch. The enemy
    manager clock may stay frozen at that boundary, but it must not regress or
    jump over an update inside one ordered replay stage.
    """

    if previous < 0 or observed < 0:
        raise ValueError("manager frames must be nonnegative")
    if observed == previous:
        return MANAGER_FRAME_TRANSITION_SAME
    if observed == previous + 1:
        return MANAGER_FRAME_TRANSITION_ADVANCED
    raise ValueError(
        "manager frame neither stayed fixed nor advanced by one input epoch: "
        f"previous={previous} observed={observed}"
    )


def replay_stage_binding_mismatch(
    fingerprint: dict[str, object],
    *,
    difficulty_index: int,
    shot_type_index: int,
    stage_index: int,
) -> str | None:
    """Return the first reason a semantic root is no longer replay-bound."""

    replay = fingerprint.get("replay")
    if not isinstance(replay, dict):
        return "replay manager is absent"
    flags = fingerprint.get("game_manager_flags")
    if not isinstance(flags, int) or isinstance(flags, bool) or not flags & 0x08:
        return "game manager replay flag is clear"
    for field, expected in (
        ("difficulty_index", difficulty_index),
        ("shot_type_index", shot_type_index),
        ("stage_index", stage_index),
    ):
        observed = fingerprint.get(field)
        if observed != expected:
            return f"{field} expected={expected} observed={observed}"
    return None


def replay_stage_terminal_reason(
    fingerprint: dict[str, object],
    *,
    difficulty_index: int,
    shot_type_index: int,
    stage_index: int,
) -> str | None:
    """Recognize only an inactive root whose replay-stage binding has ended."""

    if fingerprint.get("gameplay_active") is not False:
        return None
    return replay_stage_binding_mismatch(
        fingerprint,
        difficulty_index=difficulty_index,
        shot_type_index=shot_type_index,
        stage_index=stage_index,
    )


def _open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8", newline="")
    return path.open(mode, encoding="utf-8", newline="")


def write_semantic_trace(
    path: Path, records: Iterable[dict[str, object]]
) -> None:
    """Write a new plain or gzip JSONL trace without replacing evidence."""

    with _open_text(path, "xt") as output:
        for record in records:
            json.dump(
                record,
                output,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            output.write("\n")


def read_semantic_trace(path: Path) -> Iterator[dict[str, object]]:
    with _open_text(path, "rt") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                raise ValueError(
                    f"blank semantic-trace record at {path}:{line_number}"
                )
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid semantic-trace JSON at {path}:{line_number}: "
                    f"{error.msg}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"semantic-trace record at {path}:{line_number} "
                    "is not an object"
                )
            yield record


def semantic_trace_record(record: dict[str, object]) -> dict[str, object]:
    """Remove only source-proven nonsemantic locators from one record."""

    semantic = dict(record)
    semantic.pop("trace_locators", None)
    return semantic


def _pointer_component(component: object) -> str:
    return str(component).replace("~", "~0").replace("/", "~1")


def _render_value(value: object) -> object:
    if value is _ABSENT:
        return {"absent": True}
    return value


def _field_differences(
    left: object,
    right: object,
    *,
    path: str = "",
    maximum: int = 64,
) -> list[dict[str, object]]:
    differences: list[dict[str, object]] = []

    def visit(lhs: object, rhs: object, pointer: str) -> None:
        if len(differences) >= maximum:
            return
        if lhs is _ABSENT or rhs is _ABSENT:
            differences.append(
                {
                    "path": pointer or "/",
                    "left": _render_value(lhs),
                    "right": _render_value(rhs),
                }
            )
            return
        if type(lhs) is not type(rhs):
            differences.append(
                {
                    "path": pointer or "/",
                    "left": lhs,
                    "right": rhs,
                    "left_type": type(lhs).__name__,
                    "right_type": type(rhs).__name__,
                }
            )
            return
        if isinstance(lhs, dict):
            assert isinstance(rhs, dict)
            for key in sorted(set(lhs) | set(rhs)):
                visit(
                    lhs.get(key, _ABSENT),
                    rhs.get(key, _ABSENT),
                    f"{pointer}/{_pointer_component(key)}",
                )
            return
        if isinstance(lhs, list):
            assert isinstance(rhs, list)
            for index in range(max(len(lhs), len(rhs))):
                visit(
                    lhs[index] if index < len(lhs) else _ABSENT,
                    rhs[index] if index < len(rhs) else _ABSENT,
                    f"{pointer}/{index}",
                )
            return
        if lhs != rhs:
            differences.append(
                {"path": pointer or "/", "left": lhs, "right": rhs}
            )

    visit(left, right, path)
    return differences


def compare_semantic_traces(
    left_path: Path,
    right_path: Path,
    *,
    maximum_field_differences: int = 64,
) -> dict[str, object]:
    """Compare traces exactly and report the first unequal relative epoch."""

    if maximum_field_differences <= 0:
        raise ValueError("maximum field difference count must be positive")
    left_records = read_semantic_trace(left_path)
    right_records = read_semantic_trace(right_path)
    compared = 0
    while True:
        left = next(left_records, _ABSENT)
        right = next(right_records, _ABSENT)
        if left is _ABSENT and right is _ABSENT:
            return {
                "schema": TRACE_COMPARISON_SCHEMA,
                "equal": True,
                "left": str(left_path),
                "right": str(right_path),
                "compared_records": compared,
                "ignored_fields": ["/trace_locators"],
                "first_difference": None,
            }
        record_index = compared + 1
        if left is _ABSENT or right is _ABSENT:
            return {
                "schema": TRACE_COMPARISON_SCHEMA,
                "equal": False,
                "left": str(left_path),
                "right": str(right_path),
                "compared_records": compared,
                "ignored_fields": ["/trace_locators"],
                "first_difference": {
                    "record_index": record_index,
                    "left_relative_epoch": (
                        None
                        if left is _ABSENT
                        else left.get("relative_epoch")
                    ),
                    "right_relative_epoch": (
                        None
                        if right is _ABSENT
                        else right.get("relative_epoch")
                    ),
                    "field_differences": [
                        {
                            "path": "/",
                            "left": _render_value(left),
                            "right": _render_value(right),
                        }
                    ],
                },
            }
        assert isinstance(left, dict)
        assert isinstance(right, dict)
        left_semantic = semantic_trace_record(left)
        right_semantic = semantic_trace_record(right)
        if left_semantic != right_semantic:
            return {
                "schema": TRACE_COMPARISON_SCHEMA,
                "equal": False,
                "left": str(left_path),
                "right": str(right_path),
                "compared_records": compared,
                "ignored_fields": ["/trace_locators"],
                "first_difference": {
                    "record_index": record_index,
                    "left_relative_epoch": left.get("relative_epoch"),
                    "right_relative_epoch": right.get("relative_epoch"),
                    "field_differences": _field_differences(
                        left_semantic,
                        right_semantic,
                        maximum=maximum_field_differences,
                    ),
                },
            }
        compared += 1


__all__ = (
    "MANAGER_FRAME_TRANSITION_ADVANCED",
    "MANAGER_FRAME_TRANSITION_SAME",
    "TRACE_COMPARISON_SCHEMA",
    "classify_manager_frame_transition",
    "compare_semantic_traces",
    "read_semantic_trace",
    "replay_stage_binding_mismatch",
    "replay_stage_terminal_reason",
    "semantic_trace_record",
    "write_semantic_trace",
)
