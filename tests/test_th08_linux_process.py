from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import unittest

from th08_linux.process import LinuxProcessReader


@unittest.skipUnless(Path("/proc/self/mem").exists(), "requires procfs")
class LinuxProcessReaderTests(unittest.TestCase):
    def test_rejects_nonpositive_process_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            LinuxProcessReader(0)

    def test_reads_explicit_self_memory_without_intermediate_copy(self) -> None:
        source = ctypes.create_string_buffer(b"TH08-lockstep\x00")
        address = ctypes.addressof(source)
        with LinuxProcessReader(os.getpid()) as reader:
            self.assertEqual(reader.read(address, 13), b"TH08-lockstep")
            destination = bytearray(13)
            returned = reader.read_into(address, destination)
            self.assertIs(returned, destination)
            self.assertEqual(destination, b"TH08-lockstep")

    def test_scalar_reads_and_image_identity_use_the_selected_pid(self) -> None:
        value = ctypes.c_uint32(0xA26861B9)
        with LinuxProcessReader(os.getpid()) as reader:
            self.assertEqual(reader.u32(ctypes.addressof(value)), value.value)
            self.assertEqual(reader.image_path().resolve(), Path(sys.executable).resolve())

    def test_rejects_read_only_destination_and_use_after_close(self) -> None:
        reader = LinuxProcessReader(os.getpid())
        with self.assertRaisesRegex(ValueError, "writable"):
            reader.read_into(1, bytes(4))
        reader.close()
        reader.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            reader.read(1, 1)


if __name__ == "__main__":
    unittest.main()
