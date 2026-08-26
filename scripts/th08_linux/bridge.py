"""Blocking client for one native Linux TH08 input bridge."""

from __future__ import annotations

from pathlib import Path
import socket

from th08_linux.protocol import (
    REQUEST_SIZE,
    InputRequest,
    decode_request,
    encode_response,
    read_exact,
)


class SolverBridgeClient:
    def __init__(self, connection: socket.socket) -> None:
        self._connection = connection
        self._pending_epoch: int | None = None
        self._last_epoch = 0

    @classmethod
    def connect(cls, path: Path | str) -> "SolverBridgeClient":
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.connect(str(path))
        except BaseException:
            connection.close()
            raise
        return cls(connection)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._pending_epoch = None

    def receive(self) -> InputRequest:
        if self._connection is None:
            raise RuntimeError("solver bridge client is closed")
        if self._pending_epoch is not None:
            raise RuntimeError(
                f"input epoch {self._pending_epoch} still needs a response"
            )
        request = decode_request(read_exact(self._connection, REQUEST_SIZE))
        expected_epoch = self._last_epoch + 1
        if request.epoch != expected_epoch:
            raise RuntimeError(
                "non-contiguous solver input epoch: "
                f"expected {expected_epoch}, got {request.epoch}"
            )
        self._pending_epoch = request.epoch
        self._last_epoch = request.epoch
        return request

    def respond(self, input_mask: int) -> None:
        if self._connection is None:
            raise RuntimeError("solver bridge client is closed")
        if self._pending_epoch is None:
            raise RuntimeError("no pending solver input request")
        response = encode_response(self._pending_epoch, input_mask)
        self._connection.sendall(response)
        self._pending_epoch = None

    def __enter__(self) -> "SolverBridgeClient":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()
