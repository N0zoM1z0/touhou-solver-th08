"""Allocation-light read access to one explicitly selected Linux process."""

from __future__ import annotations

import os
from pathlib import Path
import struct
from typing import Any


class LinuxProcessReader:
    def __init__(self, pid: int) -> None:
        if pid <= 0:
            raise ValueError("process ID must be positive")
        self.pid = pid
        self._memory_path = Path(f"/proc/{pid}/mem")
        try:
            self._file: int | None = os.open(
                self._memory_path,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
            )
        except OSError as error:
            raise RuntimeError(
                f"unable to open explicit process {pid} memory: {error}"
            ) from error

    def close(self) -> None:
        if self._file is not None:
            os.close(self._file)
            self._file = None

    def _require_open(self) -> int:
        if self._file is None:
            raise RuntimeError("Linux process reader is closed")
        return self._file

    @staticmethod
    def allocate_buffer(size: int) -> bytearray:
        if size <= 0:
            raise ValueError("process read buffer size must be positive")
        return bytearray(size)

    @staticmethod
    def _writable_bytes(destination: Any) -> memoryview:
        view = memoryview(destination)
        if view.readonly:
            raise ValueError("process read destination must be writable")
        if not view.c_contiguous:
            raise ValueError("process read destination must be contiguous")
        if view.ndim != 1 or view.format != "B":
            view = view.cast("B")
        if len(view) <= 0:
            raise ValueError("process read destination must not be empty")
        return view

    def read_into(self, address: int, destination: Any) -> Any:
        if address < 0:
            raise ValueError("process read address cannot be negative")
        file = self._require_open()
        view = self._writable_bytes(destination)
        completed = 0
        while completed < len(view):
            count = os.preadv(
                file,
                [view[completed:]],
                address + completed,
            )
            if count <= 0:
                raise RuntimeError(
                    "short process memory read at "
                    f"{address:#x}: {completed}/{len(view)} bytes"
                )
            completed += count
        return destination

    def read(self, address: int, size: int) -> bytes:
        destination = self.allocate_buffer(size)
        self.read_into(address, destination)
        return bytes(destination)

    def image_path(self) -> Path:
        self._require_open()
        try:
            return Path(os.readlink(f"/proc/{self.pid}/exe"))
        except OSError as error:
            raise RuntimeError(
                f"unable to resolve explicit process {self.pid} image: {error}"
            ) from error

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u16(self, address: int) -> int:
        return struct.unpack("<H", self.read(address, 2))[0]

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def f32(self, address: int) -> float:
        return struct.unpack("<f", self.read(address, 4))[0]

    def __enter__(self) -> "LinuxProcessReader":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()
