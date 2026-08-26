from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import build_native_planner


class NativePlannerBuildTests(unittest.TestCase):
    def test_windows_build_disables_nondeterministic_pe_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "planner.dll"
            with mock.patch.object(
                build_native_planner.subprocess,
                "run",
            ) as run:
                build_native_planner._build(
                    compiler="i686-w64-mingw32-g++",
                    output=output,
                    windows=True,
                    profile="release",
                )

        command = run.call_args.args[0]
        self.assertIn("-Wl,--no-insert-timestamp", command)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_linux_build_does_not_pass_pe_linker_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "planner.so"
            with mock.patch.object(
                build_native_planner.subprocess,
                "run",
            ) as run:
                build_native_planner._build(
                    compiler="g++",
                    output=output,
                    windows=False,
                    profile="release",
                )

        self.assertNotIn("-Wl,--no-insert-timestamp", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
