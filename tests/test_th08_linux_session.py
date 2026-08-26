from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import textwrap
import unittest

from th08_linux.session import LinuxGameSession, identify_linux_runtime


_FAKE_RUNTIME = textwrap.dedent(
    """
    import os
    import signal
    import socket
    import struct
    import time

    path = os.environ["TH08_SOLVER_SOCKET"]
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    time.sleep(float(os.environ.get("FAKE_LISTEN_DELAY", "0")))
    server.listen(1)
    connection, _ = server.accept()
    connection.sendall(struct.pack(
        "<IHHQHHH2xII",
        0x51523854, 1, 32, 1, 0, 0, 0x9630, 1, 0,
    ))
    response = b""
    while len(response) < 24:
        block = connection.recv(24 - len(response))
        if not block:
            raise SystemExit(2)
        response += block
    signal.pause()
    """
)


class LinuxGameSessionTests(unittest.TestCase):
    def test_identifies_one_exact_runtime(self) -> None:
        identity = identify_linux_runtime(sys.executable)
        self.assertEqual(identity.path, Path(sys.executable).resolve())
        with Path(sys.executable).open("rb") as source:
            self.assertEqual(
                identity.sha256,
                hashlib.sha256(source.read()).hexdigest(),
            )

    def test_launches_connects_and_owns_exact_child(self) -> None:
        identity = identify_linux_runtime(sys.executable)
        with tempfile.TemporaryDirectory() as data_directory:
            session = LinuxGameSession(
                executable=identity.path,
                data_directory=data_directory,
                expected_sha256=identity.sha256,
                display=":test",
                arguments=("-c", _FAKE_RUNTIME),
            )
            with session:
                pid = session.pid
                self.assertEqual(
                    session.reader.image_path().resolve(), identity.path
                )
                request = session.bridge.receive()
                self.assertEqual(request.epoch, 1)
                session.bridge.respond(0)
            self.assertTrue(Path(f"/proc/{pid}").exists() is False)

    def test_retries_the_bind_to_listen_startup_gap(self) -> None:
        identity = identify_linux_runtime(sys.executable)
        with tempfile.TemporaryDirectory() as data_directory:
            session = LinuxGameSession(
                executable=identity.path,
                data_directory=data_directory,
                expected_sha256=identity.sha256,
                display=":test",
                arguments=("-c", _FAKE_RUNTIME),
                environment={"FAKE_LISTEN_DELAY": "0.05"},
            )
            with session:
                request = session.bridge.receive()
                self.assertEqual(request.epoch, 1)
                session.bridge.respond(0)

    def test_rejects_runtime_identity_mismatch_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as data_directory:
            session = LinuxGameSession(
                executable=sys.executable,
                data_directory=data_directory,
                expected_sha256="0" * 64,
                display=":test",
            )
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                session.__enter__()


if __name__ == "__main__":
    unittest.main()
