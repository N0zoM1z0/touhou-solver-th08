from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from th08_linux.semantic_trace import (
    MANAGER_FRAME_TRANSITION_ADVANCED,
    MANAGER_FRAME_TRANSITION_SAME,
    classify_manager_frame_transition,
    compare_semantic_traces,
    partial_semantic_trace_path,
    read_semantic_trace,
    replay_stage_binding_mismatch,
    replay_stage_terminal_reason,
    write_semantic_trace,
)


def _record(
    epoch: int, bridge_epoch: int, x_bits: int = 0x43400000
) -> dict[str, object]:
    return {
        "schema": "th08-semantic-spine-v3",
        "relative_epoch": epoch,
        "trace_locators": {
            "bridge_epoch": bridge_epoch,
            "rng_calls_absolute": bridge_epoch + 7,
        },
        "rng": {"seed": 9, "calls_since_trace_start": epoch * 2},
        "player": {"x_bits": x_bits},
    }


class LinuxSemanticTraceTests(unittest.TestCase):
    def test_partial_trace_path_preserves_jsonl_compression_suffix(self) -> None:
        self.assertEqual(
            partial_semantic_trace_path(Path("trace.jsonl.gz")),
            Path("trace.partial.jsonl.gz"),
        )
        self.assertEqual(
            partial_semantic_trace_path(Path("trace.jsonl")),
            Path("trace.partial.jsonl"),
        )

    def test_replay_terminal_requires_inactive_and_binding_end(self) -> None:
        fingerprint = {
            "gameplay_active": False,
            "game_manager_flags": 0x08,
            "difficulty_index": 3,
            "shot_type_index": 2,
            "stage_index": 5,
            "replay": {"frame_counter": 7650},
        }
        self.assertIsNone(
            replay_stage_terminal_reason(
                fingerprint,
                difficulty_index=3,
                shot_type_index=2,
                stage_index=5,
            )
        )
        fingerprint["shot_type_index"] = 0
        self.assertEqual(
            replay_stage_terminal_reason(
                fingerprint,
                difficulty_index=3,
                shot_type_index=2,
                stage_index=5,
            ),
            "shot_type_index expected=2 observed=0",
        )
        fingerprint["gameplay_active"] = True
        self.assertIsNone(
            replay_stage_terminal_reason(
                fingerprint,
                difficulty_index=3,
                shot_type_index=2,
                stage_index=5,
            )
        )

    def test_replay_binding_reports_missing_manager(self) -> None:
        self.assertEqual(
            replay_stage_binding_mismatch(
                {
                    "gameplay_active": False,
                    "game_manager_flags": 0,
                    "difficulty_index": 3,
                    "shot_type_index": 2,
                    "stage_index": 5,
                    "replay": None,
                },
                difficulty_index=3,
                shot_type_index=2,
                stage_index=5,
            ),
            "replay manager is absent",
        )

    def test_manager_frame_transition_classifies_advance_and_freeze(self) -> None:
        self.assertEqual(
            classify_manager_frame_transition(previous=7649, observed=7650),
            MANAGER_FRAME_TRANSITION_ADVANCED,
        )
        self.assertEqual(
            classify_manager_frame_transition(previous=4530, observed=6331),
            MANAGER_FRAME_TRANSITION_ADVANCED,
        )
        self.assertEqual(
            classify_manager_frame_transition(previous=7649, observed=7649),
            MANAGER_FRAME_TRANSITION_SAME,
        )

    def test_manager_frame_transition_rejects_regression(self) -> None:
        with self.assertRaisesRegex(ValueError, "regressed"):
            classify_manager_frame_transition(
                previous=7649,
                observed=7648,
            )

    def test_gzip_round_trip_and_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl.gz"
            records = [_record(1, 100), _record(2, 101)]
            write_semantic_trace(path, records)
            self.assertEqual(list(read_semantic_trace(path)), records)
            with self.assertRaises(FileExistsError):
                write_semantic_trace(path, records)

    def test_comparison_ignores_only_source_proven_trace_locators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            left = Path(directory) / "left.jsonl"
            right = Path(directory) / "right.jsonl.gz"
            write_semantic_trace(left, [_record(1, 100), _record(2, 101)])
            write_semantic_trace(right, [_record(1, 900), _record(2, 901)])
            report = compare_semantic_traces(left, right)
            self.assertTrue(report["equal"])
            self.assertEqual(report["compared_records"], 2)

    def test_comparison_reports_first_nested_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            left = Path(directory) / "left.jsonl"
            right = Path(directory) / "right.jsonl"
            write_semantic_trace(
                left, [_record(1, 100), _record(2, 101, 0x43400000)]
            )
            write_semantic_trace(
                right, [_record(1, 900), _record(2, 901, 0x43400001)]
            )
            report = compare_semantic_traces(left, right)
            self.assertFalse(report["equal"])
            self.assertEqual(report["compared_records"], 1)
            first = report["first_difference"]
            assert isinstance(first, dict)
            self.assertEqual(first["record_index"], 2)
            differences = first["field_differences"]
            assert isinstance(differences, list)
            self.assertEqual(differences[0]["path"], "/player/x_bits")

    def test_comparison_reports_shorter_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            left = Path(directory) / "left.jsonl"
            right = Path(directory) / "right.jsonl"
            write_semantic_trace(left, [_record(1, 100)])
            write_semantic_trace(right, [_record(1, 900), _record(2, 901)])
            report = compare_semantic_traces(left, right)
            self.assertFalse(report["equal"])
            self.assertEqual(report["compared_records"], 1)


if __name__ == "__main__":
    unittest.main()
