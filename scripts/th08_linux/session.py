"""Ownership boundary for one solver-launched native Linux TH08 process."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Mapping, Sequence

from th08_linux.bridge import SolverBridgeClient
from th08_linux.process import LinuxProcessReader


@dataclass(frozen=True, slots=True)
class LinuxRuntimeIdentity:
    path: Path
    size: int
    sha256: str


def identify_linux_runtime(path: Path | str) -> LinuxRuntimeIdentity:
    executable = Path(path).resolve(strict=True)
    if not executable.is_file():
        raise ValueError(f"Linux runtime is not a regular file: {executable}")
    digest = hashlib.sha256()
    with executable.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return LinuxRuntimeIdentity(
        path=executable,
        size=executable.stat().st_size,
        sha256=digest.hexdigest(),
    )


class LinuxGameSession:
    """Launch, connect to, and clean up exactly one native TH08 child.

    ``startup_timeout_seconds`` bounds only executable/socket bootstrap.  No
    gameplay duration or route timeout exists in this ownership layer.
    """

    def __init__(
        self,
        *,
        executable: Path | str,
        data_directory: Path | str,
        expected_sha256: str,
        display: str,
        arguments: Sequence[str] = (),
        environment: Mapping[str, str] | None = None,
        startup_timeout_seconds: float = 30.0,
        shutdown_grace_seconds: float = 5.0,
    ) -> None:
        if not expected_sha256:
            raise ValueError("an expected Linux runtime SHA-256 is required")
        if not display:
            raise ValueError("an explicit X display is required")
        if startup_timeout_seconds <= 0.0:
            raise ValueError("startup timeout must be positive")
        if shutdown_grace_seconds <= 0.0:
            raise ValueError("shutdown grace must be positive")
        self._executable = Path(executable)
        self._data_directory = Path(data_directory)
        self._expected_sha256 = expected_sha256.lower()
        self._display = display
        self._arguments = tuple(arguments)
        self._environment = dict(environment or {})
        self._startup_timeout_seconds = startup_timeout_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._identity: LinuxRuntimeIdentity | None = None
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._socket_path: Path | None = None
        self._log_file = None
        self._log_path: Path | None = None
        self._log_tail = ""
        self._process: subprocess.Popen[bytes] | None = None
        self._bridge: SolverBridgeClient | None = None
        self._reader: LinuxProcessReader | None = None
        self._entered = False
        self._closed = False

    @property
    def identity(self) -> LinuxRuntimeIdentity:
        if self._identity is None:
            raise RuntimeError("Linux game session has not been entered")
        return self._identity

    @property
    def pid(self) -> int:
        if self._process is None:
            raise RuntimeError("Linux game session has not been entered")
        return self._process.pid

    @property
    def bridge(self) -> SolverBridgeClient:
        if self._bridge is None:
            raise RuntimeError("Linux game session has not been entered")
        return self._bridge

    @property
    def reader(self) -> LinuxProcessReader:
        if self._reader is None:
            raise RuntimeError("Linux game session has not been entered")
        return self._reader

    @property
    def runtime_log_tail(self) -> str:
        return self._log_tail

    def __enter__(self) -> "LinuxGameSession":
        if self._entered:
            raise RuntimeError("Linux game session cannot be entered twice")
        if self._closed:
            raise RuntimeError("closed Linux game session cannot be entered")
        self._entered = True
        try:
            identity = identify_linux_runtime(self._executable)
            if identity.sha256 != self._expected_sha256:
                raise RuntimeError(
                    "Linux runtime SHA-256 mismatch: "
                    f"expected {self._expected_sha256}, got {identity.sha256}"
                )
            data_directory = self._data_directory.resolve(strict=True)
            if not data_directory.is_dir():
                raise ValueError(
                    f"Linux runtime data directory is not a directory: "
                    f"{data_directory}"
                )
            self._identity = identity
            self._temporary = tempfile.TemporaryDirectory(
                prefix="th08-linux-lockstep-"
            )
            temporary_path = Path(self._temporary.name)
            self._socket_path = temporary_path / "input.sock"
            self._log_path = temporary_path / "runtime.log"
            self._log_file = self._log_path.open("w+b")
            environment = os.environ.copy()
            environment.update(self._environment)
            environment["DISPLAY"] = self._display
            environment["TH08_SOLVER_SOCKET"] = str(self._socket_path)
            self._process = subprocess.Popen(
                [str(identity.path), *self._arguments],
                cwd=data_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._bridge = self._connect_bridge()
            self._reader = LinuxProcessReader(self._process.pid)
            selected_image = self._reader.image_path().resolve(strict=True)
            if selected_image != identity.path:
                raise RuntimeError(
                    "selected Linux process image mismatch: "
                    f"expected {identity.path}, got {selected_image}"
                )
        except BaseException:
            self.close()
            raise
        return self

    def _connect_bridge(self) -> SolverBridgeClient:
        assert self._process is not None
        assert self._socket_path is not None
        deadline = time.monotonic() + self._startup_timeout_seconds
        last_connect_error: OSError | None = None
        while True:
            return_code = self._process.poll()
            if return_code is not None:
                raise RuntimeError(
                    "Linux runtime exited before accepting its solver socket "
                    f"with status {return_code}"
                )
            if self._socket_path.exists():
                try:
                    return SolverBridgeClient.connect(self._socket_path)
                except (FileNotFoundError, ConnectionRefusedError) as error:
                    # bind(2) publishes the path before listen(2) makes the
                    # server connectable.  Treat that gap as startup, not as a
                    # permanent protocol failure.
                    last_connect_error = error
            if time.monotonic() >= deadline:
                detail = (
                    f"; last connect error: {last_connect_error}"
                    if last_connect_error is not None
                    else ""
                )
                raise TimeoutError(
                    "Linux runtime did not accept its solver socket during "
                    f"the bounded startup phase{detail}"
                )
            time.sleep(0.01)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=self._shutdown_grace_seconds)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=self._shutdown_grace_seconds)
        self._capture_log_tail()
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def _capture_log_tail(self, maximum_bytes: int = 16 * 1024) -> None:
        if self._log_file is None:
            return
        self._log_file.flush()
        size = self._log_file.seek(0, os.SEEK_END)
        self._log_file.seek(max(0, size - maximum_bytes))
        self._log_tail = self._log_file.read().decode(
            "utf-8", errors="replace"
        )

    def __exit__(self, *_exception: object) -> None:
        self.close()


__all__ = [
    "LinuxGameSession",
    "LinuxRuntimeIdentity",
    "identify_linux_runtime",
]
