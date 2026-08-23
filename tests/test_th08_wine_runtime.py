from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from tools import prepare_th08_wine_runtime as prepare
from tools import run_th08_wine as runner


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Th08WinePreparationTests(unittest.TestCase):
    def test_config_matches_target_layout_and_keeps_gameplay_quality(self) -> None:
        config = prepare.render_windowed_config()
        self.assertEqual(len(config), 60)
        self.assertEqual(
            struct.unpack_from("<9h", config, 0),
            (0, 1, 2, 4, -1, -1, -1, -1, 3),
        )
        self.assertEqual(
            struct.unpack_from("<Ihh", config, 20),
            (0x80001, 600, 600),
        )
        self.assertEqual(
            config[28:41],
            bytes((2, 3, 0, 0, 0, 3, 1, 0, 2, 0, 0, 0, 0)),
        )
        self.assertEqual(struct.unpack_from("<I", config, 56)[0], 1)

    def test_embedded_python_path_includes_site_packages_and_solver(self) -> None:
        lines = prepare.configured_python_pth().splitlines()
        self.assertIn(r"Lib\site-packages", lines)
        self.assertIn(r"..\..\..\scripts", lines)
        self.assertEqual(lines[-1], "import site")

    def test_python_runtime_preparation_is_attested_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "python.zip"
            wheel = root / "numpy.whl"
            runtime = root / "runtime"
            python_exe = b"MZ-test-python"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("python.exe", python_exe)
                output.writestr("python311.zip", b"stdlib")
                output.writestr("python311._pth", b"old")
            with zipfile.ZipFile(wheel, "w") as output:
                output.writestr("numpy/__init__.py", b"__version__='test'\n")
            with (
                mock.patch.object(
                    prepare,
                    "PYTHON_ARCHIVE_SHA256",
                    prepare.sha256(archive),
                ),
                mock.patch.object(
                    prepare,
                    "NUMPY_WHEEL_SHA256",
                    prepare.sha256(wheel),
                ),
                mock.patch.object(
                    prepare,
                    "PYTHON_EXE_SHA256",
                    _sha256_bytes(python_exe),
                ),
            ):
                first = prepare.prepare_python_runtime(
                    archive=archive,
                    numpy_wheel=wheel,
                    destination=runtime,
                )
                second = prepare.prepare_python_runtime(
                    archive=archive,
                    numpy_wheel=wheel,
                    destination=runtime,
                )
            self.assertEqual(first, second)
            self.assertTrue(
                (
                    runtime
                    / "Lib"
                    / "site-packages"
                    / "numpy"
                    / "__init__.py"
                ).is_file()
            )

    def test_python_runtime_rejects_search_path_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            archive = root / "python.zip"
            wheel = root / "numpy.whl"
            archive.write_bytes(b"archive")
            wheel.write_bytes(b"wheel")
            inputs = {
                "python_archive_sha256": prepare.sha256(archive),
                "numpy_wheel_sha256": prepare.sha256(wheel),
            }
            (runtime / prepare.RUNTIME_MARKER).write_text(
                json.dumps(inputs),
                encoding="utf-8",
            )
            python_exe = runtime / "python.exe"
            python_exe.write_bytes(b"python")
            (runtime / "python311._pth").write_text(
                "drifted\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    prepare,
                    "PYTHON_ARCHIVE_SHA256",
                    inputs["python_archive_sha256"],
                ),
                mock.patch.object(
                    prepare,
                    "NUMPY_WHEEL_SHA256",
                    inputs["numpy_wheel_sha256"],
                ),
                mock.patch.object(
                    prepare,
                    "PYTHON_EXE_SHA256",
                    prepare.sha256(python_exe),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "search path"):
                    prepare.prepare_python_runtime(
                        archive=archive,
                        numpy_wheel=wheel,
                        destination=runtime,
                    )


class Th08WineRunnerTests(unittest.TestCase):
    def test_wine_full_route_budget_covers_sub_realtime_vps(self) -> None:
        args = runner.build_parser().parse_args(["--mode", "full-route"])
        self.assertEqual(args.agent_duration, 7200.0)
        self.assertEqual(args.trial_timeout, 7350.0)
        self.assertGreater(args.trial_timeout, args.agent_duration)

    def test_pty_bridge_provides_console_handles_and_propagates_status(
        self,
    ) -> None:
        bridge = runner.ROOT / "scripts" / "tools" / "exec_with_pty.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(bridge),
                "--",
                sys.executable,
                "-c",
                (
                    "import os, sys; "
                    "print(os.isatty(0), os.isatty(1)); "
                    "sys.exit(7)"
                ),
            ],
            check=False,
            capture_output=True,
            timeout=10.0,
        )
        self.assertEqual(completed.returncode, 7)
        self.assertIn(b"True True", completed.stdout)

    def test_windows_path_uses_wine_z_drive(self) -> None:
        self.assertEqual(
            runner.windows_path(Path("/tmp/th08 test")),
            r"Z:\tmp\th08 test",
        )

    def test_auto_display_skips_existing_socket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sockets = Path(directory)
            (sockets / "X98").touch()
            self.assertEqual(
                runner.select_display(
                    "auto",
                    socket_root=sockets,
                    lock_root=sockets,
                ),
                ":99",
            )

    def test_auto_display_skips_existing_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            display_root = Path(directory)
            (display_root / ".X98-lock").touch()
            self.assertEqual(
                runner.select_display(
                    "auto",
                    socket_root=display_root,
                    lock_root=display_root,
                ),
                ":99",
            )

    def test_full_route_command_is_lunatic_finalb_and_refuses_existing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = runner.build_windows_controller_command(
                mode="full-route",
                python=root / "python.exe",
                game_dir=root / "game",
                artifact_dir=root / "artifacts",
                agent_duration=4500.0,
                trial_timeout=4650.0,
                kill_before_saturation=False,
                ordinary_preexhaustion_authority=False,
            )
        self.assertIn("--armed", command)
        self.assertIn("--refuse-existing", command)
        self.assertIn("--enable-finalb-scale-source-authority", command)
        self.assertNotIn("--kill-before-saturation", command)
        self.assertNotIn("--ordinary-preexhaustion-authority", command)

    def test_pe_machine_reads_i386_coff_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "planner.dll"
            payload = bytearray(0x86)
            payload[:2] = b"MZ"
            struct.pack_into("<I", payload, 0x3C, 0x80)
            payload[0x80:0x84] = b"PE\0\0"
            struct.pack_into("<H", payload, 0x84, 0x014C)
            image.write_bytes(payload)
            self.assertEqual(runner.pe_machine(image), 0x014C)


if __name__ == "__main__":
    unittest.main()
