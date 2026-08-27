"""Latest-only solver client for the continuous native Linux TH08 bridge."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import socket
from typing import Any

from th08_linux.immutable_snapshot import PublishedSnapshotRoot
from th08_linux.online_protocol import (
    REQUEST_SIZE,
    OnlineInputRequest,
    decode_online_request,
    encode_online_response,
    encode_snapshot_release,
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
        self._snapshot_leases: set[tuple[int, int]] = set()
        self._pending_releases: deque[bytes] = deque()
        self.drained_publications = 0
        self.observed_epoch_gaps = 0
        self.local_response_drops = 0
        self.snapshot_releases_sent = 0

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
        self._snapshot_leases.clear()
        self._pending_releases.clear()

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
        if request.snapshot_present:
            lease = (request.snapshot_generation, request.snapshot_slot)
            if lease in self._snapshot_leases:
                raise RuntimeError("duplicate immutable snapshot lease")
            self._snapshot_leases.add(lease)

    def _queue_snapshot_release(self, request: OnlineInputRequest) -> None:
        if not request.snapshot_present:
            return
        lease = (request.snapshot_generation, request.snapshot_slot)
        if lease not in self._snapshot_leases:
            return
        self._snapshot_leases.remove(lease)
        self._pending_releases.append(
            encode_snapshot_release(
                generation=request.snapshot_generation,
                slot=request.snapshot_slot,
            )
        )

    def _flush_snapshot_releases(self) -> None:
        if self._connection is None:
            return
        while self._pending_releases:
            try:
                written = self._connection.send(
                    self._pending_releases[0],
                    socket.MSG_DONTWAIT | getattr(socket, "MSG_NOSIGNAL", 0),
                )
            except BlockingIOError:
                return
            if written != len(self._pending_releases[0]):
                self.close()
                raise RuntimeError(
                    "snapshot release was not sent as one complete packet"
                )
            self._pending_releases.popleft()
            self.snapshot_releases_sent += 1

    def receive(self) -> OnlineInputRequest:
        if self._pending is not None:
            raise RuntimeError(
                f"target epoch {self._pending.target_epoch} still needs an "
                "explicit response or abandon"
            )
        self._flush_snapshot_releases()
        newest = self._receive_packet()
        self._accept_epoch(newest)
        while True:
            try:
                candidate = self._receive_packet(socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
            self._accept_epoch(candidate)
            self._queue_snapshot_release(newest)
            newest = candidate
            self.drained_publications += 1
        self._pending = newest
        return newest

    def capture_snapshot(
        self,
        process_reader: Any,
        request: OnlineInputRequest,
    ) -> PublishedSnapshotRoot:
        """Copy and release the pending runtime slot exactly once.

        The returned root owns local immutable bytes.  Releasing the game-side
        slot does not change them and therefore does not shorten background
        graph work.
        """

        if self._pending is not request:
            raise RuntimeError("immutable snapshot request is not pending")
        lease = (request.snapshot_generation, request.snapshot_slot)
        if lease not in self._snapshot_leases:
            raise RuntimeError("immutable snapshot lease was already released")
        try:
            return PublishedSnapshotRoot.capture(process_reader, request)
        finally:
            self._queue_snapshot_release(request)

    def respond(
        self,
        input_mask: int,
        *,
        continuation_frames: int = 0,
        snapshot_generation: int = 0,
    ) -> bool:
        if self._connection is None:
            raise RuntimeError("online solver bridge client is closed")
        if self._pending is None:
            raise RuntimeError("no pending online input target")
        request = self._pending
        response = encode_online_response(
            source_epoch=request.source_epoch,
            target_epoch=request.target_epoch,
            input_mask=input_mask,
            continuation_frames=continuation_frames,
            snapshot_generation=snapshot_generation,
        )
        self._pending = None
        # Queue ownership transfer before the deadline-sensitive send, but
        # send the input response first so release traffic cannot consume its
        # socket capacity.
        self._queue_snapshot_release(request)
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
        self._flush_snapshot_releases()
        return True

    def abandon(self) -> None:
        """Leave this target unresolved so the runtime applies its fallback."""

        if self._pending is None:
            raise RuntimeError("no pending online input target")
        request = self._pending
        self._pending = None
        self._queue_snapshot_release(request)
        self._flush_snapshot_releases()

    def __enter__(self) -> "OnlineSolverBridgeClient":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()


__all__ = ("OnlineSolverBridgeClient",)
