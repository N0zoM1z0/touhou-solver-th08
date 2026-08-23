#!/usr/bin/env python3
"""Tests for the fixed G5 corridor-parent priority audit."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from analysis.th08_corridor_priority_audit import (
    CorridorPriorityAuditError,
    audit_trace,
    canonical_report_bytes,
)


def _config(*, requested: bool = True) -> dict[str, object]:
    return {
        "kind": "controller_config",
        "corridor_background_low_priority": requested,
        "corridor_native_viability_workers": 4,
    }


def _split_config() -> dict[str, object]:
    return {
        "kind": "controller_config",
        "ordinary_authority_background_low_priority": True,
        "corridor_native_viability_workers": 4,
    }


def _decision(
    frame: int,
    source_frame: int,
    *,
    priority_lowered: bool = True,
) -> dict[str, object]:
    return {
        "kind": "decision",
        "frame": frame,
        "action_lag": 1,
        "timing_ms": {"local_plan": 5.0},
        "corridor": {
            "source_frame": source_frame,
            "age": frame - source_frame,
            "solve_ms": 100.0,
            "background_priority_lowered": priority_lowered,
            "native_viability_worker_limit": 4,
            "native_viability_worker_limit_applied": True,
            "planning_mode": "robust_viability",
            "policy_status": "queryable",
            "viability": {
                "available": True,
                "support_covers_current": True,
            },
        },
    }


class CorridorPriorityAuditTests(unittest.TestCase):
    def _write_trace(
        self,
        path: Path,
        records: list[dict[str, object]],
    ) -> None:
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_passing_trace_is_deterministic_and_retains_provenance(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            trace = Path(directory) / "trial.jsonl"
            self._write_trace(
                trace,
                [
                    _config(),
                    _decision(81, 80),
                    _decision(82, 80),
                    _decision(90, 88),
                    _decision(99, 96),
                ],
            )

            first = audit_trace(trace)
            second = audit_trace(trace)

        self.assertEqual(
            canonical_report_bytes(first),
            canonical_report_bytes(second),
        )
        self.assertTrue(first["gates"]["application_pass"])
        self.assertTrue(first["gates"]["delivery_pass"])
        self.assertEqual(first["counts"]["unique_solution"], 3)
        self.assertEqual(first["counts"]["priority_lowered_solution"], 3)
        self.assertEqual(
            first["configuration"]["corridor_native_viability_workers"],
            4,
        )

    def test_unapplied_priority_fails_application_gate(self) -> None:
        with TemporaryDirectory() as directory:
            trace = Path(directory) / "trial.jsonl"
            self._write_trace(
                trace,
                [_config(), _decision(81, 80, priority_lowered=False)],
            )
            report = audit_trace(trace)

        self.assertFalse(report["gates"]["application_pass"])
        self.assertFalse(
            report["gates"]["application"][
                "all_solutions_lowered_parent_priority"
            ]
        )

    def test_missing_controller_config_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            trace = Path(directory) / "trial.jsonl"
            self._write_trace(trace, [_decision(81, 80)])
            with self.assertRaisesRegex(
                CorridorPriorityAuditError,
                "no controller_config",
            ):
                audit_trace(trace)

    def test_worker_policy_split_means_main_corridor_was_not_requested(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            trace = Path(directory) / "trial.jsonl"
            self._write_trace(
                trace,
                [_split_config(), _decision(81, 80, priority_lowered=False)],
            )
            report = audit_trace(trace)

        self.assertFalse(
            report["configuration"]["corridor_background_low_priority"]
        )
        self.assertEqual(
            report["configuration"][
                "corridor_background_low_priority_source"
            ],
            "implicit_disabled_after_ordinary_worker_split",
        )


if __name__ == "__main__":
    unittest.main()
