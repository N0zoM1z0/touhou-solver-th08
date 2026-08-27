"""Latest-only solver client for the continuous native Linux TH08 bridge."""

from __future__ import annotations

from pathlib import Path
import socket

from th08_linux.online_protocol import (
    REQUEST_SIZE,
    OnlineInputRequest,
    decode_online_request,
    encode_online_response,
)


class OnlineSolverBridgeClient:
    """Consume post-update publications without ever pacing the game.

    Publications may legitimately skip because the game-side socket is
    non-blocking.  Before planning, this client drains its queue and exposes
    only the newest source root.
    """

    def __init__(self, connection: socket.socket) -> None:
        if connection.type & socket.SOCK_SEQPACKET != socket.SOCK_SEQPACKET:
            raise ValueError("online bridge requires a SOCK_SEQPACKET socket")
        self._connection: socket.socket | None = connection
        self._pending: OnlineInputRequest | None = None
        self._last_source_epoch: int | None = None
        self.drained_publications = 0
        self.observed_epoch_gaps = 0
        self.local_response_drops = 0

    @classmethod
    def connect(cls, path: Path | str) -> "OnlineSolverBridgeClient":
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
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
        self._pending = None

    def _receive_packet(self, flags: int = 0) -> OnlineInputRequest:
        if self._connection is None:
            raise RuntimeError("online solver bridge client is closed")
        data, _ancillary, message_flags, _address = self._connection.recvmsg(
            REQUEST_SIZE,
            0,
            flags,
        )
        if not data:
            raise EOFError("online solver bridge closed during publication")
        if message_flags & socket.MSG_TRUNC:
            raise ValueError("online solver publication exceeded its wire size")
        return decode_online_request(data)

    def _accept_epoch(self, request: OnlineInputRequest) -> None:
        previous = self._last_source_epoch
        if previous is not None:
            if request.source_epoch <= previous:
                raise RuntimeError(
                    "non-monotonic online source epoch: "
                    f"previous {previous}, got {request.source_epoch}"
                )
            self.observed_epoch_gaps += request.source_epoch - previous - 1
        self._last_source_epoch = request.source_epoch

    def receive(self) -> OnlineInputRequest:
        if self._pending is not None:
            raise RuntimeError(
                f"target epoch {self._pending.target_epoch} still needs an "
                "explicit response or abandon"
            )
        newest = self._receive_packet()
        self._accept_epoch(newest)
        while True:
            try:
                candidate = self._receive_packet(socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
            self._accept_epoch(candidate)
            newest = candidate
            self.drained_publications += 1
        self._pending = newest
        return newest

    def respond(self, input_mask: int) -> bool:
        if self._connection is None:
            raise RuntimeError("online solver bridge client is closed")
        if self._pending is None:
            raise RuntimeError("no pending online input target")
        request = self._pending
        response = encode_online_response(
            source_epoch=request.source_epoch,
            target_epoch=request.target_epoch,
            input_mask=input_mask,
        )
        self._pending = None
        try:
            written = self._connection.send(
                response,
                socket.MSG_DONTWAIT | getattr(socket, "MSG_NOSIGNAL", 0),
            )
        except BlockingIOError:
            self.local_response_drops += 1
            return False
        if written != len(response):
            self.close()
            raise RuntimeError("online response was not sent as one complete packet")
        return True

    def abandon(self) -> None:
        """Explicitly choose the game-owned held-input fallback for this target."""

        if self._pending is None:
            raise RuntimeError("no pending online input target")
        self._pending = None

    def __enter__(self) -> "OnlineSolverBridgeClient":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()


__all__ = ("OnlineSolverBridgeClient",)
