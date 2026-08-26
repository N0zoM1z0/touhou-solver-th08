from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from th08_linux.semantic_trace import (
    MANAGER_FRAME_ROOT_EXPECTED,
    MANAGER_FRAME_ROOT_REPEATED_PREVIOUS,
    classify_manager_frame_root,
    compare_semantic_traces,
    read_semantic_trace,
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
    def test_manager_frame_root_classifies_expected_and_restart(self) -> None:
        self.assertEqual(
            classify_manager_frame_root(observed=7650, expected=7650),
            MANAGER_FRAME_ROOT_EXPECTED,
        )
        self.assertEqual(
            classify_manager_frame_root(observed=7649, expected=7650),
            MANAGER_FRAME_ROOT_REPEATED_PREVIOUS,
        )

    def test_manager_frame_root_rejects_regression_or_skip(self) -> None:
        for observed in (7648, 7651):
            with self.subTest(observed=observed):
                with self.assertRaisesRegex(
                    ValueError, "neither the expected manager frame"
                ):
                    classify_manager_frame_root(
                        observed=observed,
                        expected=7650,
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
