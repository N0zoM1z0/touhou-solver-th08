"""Ownership boundary for one continuously running native Linux TH08 child."""

from __future__ import annotations

import time

from th08_linux.elf import resolve_defined_symbol
from th08_linux.online_bridge import OnlineSolverBridgeClient
from th08_linux.session import LinuxGameSession


INPUT_EPOCH_SYMBOL = "th08_solver_input_epoch"


class LinuxOnlineGameSession(LinuxGameSession):
    """Use protocol v2 and expose its native input-epoch capture bracket."""

    temporary_prefix = "th08-linux-online-"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._input_epoch_address: int | None = None

    @property
    def bridge(self) -> OnlineSolverBridgeClient:
        bridge = self._bridge
        if not isinstance(bridge, OnlineSolverBridgeClient):
            raise RuntimeError("Linux online game session has not been entered")
        return bridge

    @property
    def input_epoch_address(self) -> int:
        if self._input_epoch_address is None:
            raise RuntimeError("Linux online input epoch is unavailable")
        return self._input_epoch_address

    def __enter__(self) -> "LinuxOnlineGameSession":
        try:
            super().__enter__()
            self._input_epoch_address = resolve_defined_symbol(
                self.identity.path,
                INPUT_EPOCH_SYMBOL,
            )
        except BaseException:
            self.close()
            raise
        return self

    def _connect_bridge(self) -> OnlineSolverBridgeClient:
        assert self._process is not None
        assert self._socket_path is not None
        deadline = time.monotonic() + self._startup_timeout_seconds
        last_connect_error: OSError | None = None
        while True:
            return_code = self._process.poll()
            if return_code is not None:
                raise RuntimeError(
                    "Linux runtime exited before accepting its online solver "
                    f"socket with status {return_code}"
                )
            if self._socket_path.exists():
                try:
                    return OnlineSolverBridgeClient.connect(self._socket_path)
                except (FileNotFoundError, ConnectionRefusedError) as error:
                    last_connect_error = error
            if time.monotonic() >= deadline:
                detail = (
                    f"; last connect error: {last_connect_error}"
                    if last_connect_error is not None
                    else ""
                )
                raise TimeoutError(
                    "Linux runtime did not accept its online solver socket "
                    f"during the bounded startup phase{detail}"
                )
            time.sleep(0.01)


__all__ = ("INPUT_EPOCH_SYMBOL", "LinuxOnlineGameSession")
