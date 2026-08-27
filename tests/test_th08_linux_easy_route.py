from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from th08_linux.elf import resolve_defined_symbol
from tools.th08_linux_easy_route import (
    _spell_id,
    _timing_summary,
    build_parser,
)


class LinuxEasyRouteToolTests(unittest.TestCase):
    def test_full_route_has_no_gameplay_cap_by_default(self) -> None:
        arguments = build_parser().parse_args(
            [
                "--executable",
                "th08",
                "--data-directory",
                "data",
                "--expected-sha256",
                "0" * 64,
                "--display",
                ":121",
                "--report",
                "report.json",
            ]
        )
        self.assertIsNone(arguments.diagnostic_gameplay_epochs)
        self.assertFalse(arguments.retail_life_decrement)
        self.assertEqual(arguments.horizon, 8)
        self.assertEqual(arguments.threat_horizon, 12)
        self.assertEqual(arguments.beam_width, 8)

    def test_timing_summary_is_deterministic_and_bounded(self) -> None:
        self.assertEqual(_timing_summary([])["count"], 0)
        summary = _timing_summary([float(value) for value in range(1, 21)])
        self.assertEqual(summary["count"], 20)
        self.assertEqual(summary["mean_ms"], 10.5)
        self.assertEqual(summary["p95_ms"], 19.0)
        self.assertEqual(summary["max_ms"], 20.0)

    def test_spell_id_requires_active_observation(self) -> None:
        self.assertIsNone(_spell_id({"spell": {"active": False, "spell_id": 9}}))
        self.assertEqual(_spell_id({"spell": {"active": True, "spell_id": 9}}), 9)

    def test_elf_symbol_resolution_requires_one_exact_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "runtime"
            executable.touch()
            completed = argparse.Namespace(stdout="wanted T 00123456 10\n")
            with mock.patch(
                "th08_linux.elf.subprocess.run",
                return_value=completed,
            ) as invoked:
                self.assertEqual(
                    resolve_defined_symbol(executable, "wanted"),
                    0x00123456,
                )
            invoked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
