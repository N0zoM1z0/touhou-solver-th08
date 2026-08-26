from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from th08_live.runtime_ecl_image import (  # noqa: E402
    ECL_FILE_CONTEXT_ADDRESS,
    ECL_MAGIC,
    ECL_RUNTIME_HEADER_SIZE,
    ECL_TIMELINE_SLOT_OFFSET,
    RuntimeEclImageError,
    capture_runtime_ecl_image,
    compare_runtime_ecl_image,
    normalize_relocated_ecl_image,
)


_RUNTIME_BASE = 0x02100000
_IMAGE_LENGTH = 0x100


def _static_ecl_image() -> bytes:
    """Independent raw fixture using the decoded on-disk layout."""

    image = bytearray((index * 17 + 3) & 0xFF for index in range(_IMAGE_LENGTH))
    struct.pack_into("<IHH", image, 0, ECL_MAGIC, 2, 1)
    timeline_slots = (0x80, _IMAGE_LENGTH, *(0 for _ in range(14)))
    struct.pack_into("<16I", image, 8, *timeline_slots)
    struct.pack_into("<2I", image, ECL_RUNTIME_HEADER_SIZE, 0x60, 0x70)
    return bytes(image)


def _relocated_ecl_image(
    static_image: bytes,
    *,
    runtime_base: int = _RUNTIME_BASE,
) -> bytes:
    """Independent oracle for the two relocation loops in ecl_load_file."""

    image = bytearray(static_image)
    for index in range(16):
        offset = 8 + 4 * index
        relative = struct.unpack_from("<I", image, offset)[0]
        struct.pack_into("<I", image, offset, runtime_base + relative)
    for index in range(2):
        offset = ECL_RUNTIME_HEADER_SIZE + 4 * index
        relative = struct.unpack_from("<I", image, offset)[0]
        struct.pack_into("<I", image, offset, runtime_base + relative)
    return bytes(image)


class _Reader:
    def __init__(
        self,
        image: bytes,
        *,
        context_after: bytes | None = None,
        runtime_base: int = _RUNTIME_BASE,
    ) -> None:
        self.image = image
        self.runtime_base = runtime_base
        self.context = struct.pack(
            "<II",
            runtime_base,
            runtime_base + ECL_RUNTIME_HEADER_SIZE,
        )
        self.context_after = context_after or self.context
        self.context_reads = 0
        self.reads: list[tuple[int, int]] = []

    def read(self, address: int, size: int) -> bytes:
        self.reads.append((address, size))
        if address == ECL_FILE_CONTEXT_ADDRESS:
            self.context_reads += 1
            return (
                self.context
                if self.context_reads == 1
                else self.context_after
            )
        if address != self.runtime_base:
            raise AssertionError(f"unexpected address {address:#x}")
        return self.image[:size]


class RuntimeEclImageTests(unittest.TestCase):
    def test_independent_relocation_oracle_normalizes_exactly(self) -> None:
        static_image = _static_ecl_image()
        relocated = _relocated_ecl_image(static_image)
        self.assertEqual(
            normalize_relocated_ecl_image(
                relocated,
                runtime_base=_RUNTIME_BASE,
            ),
            static_image,
        )

    def test_capture_is_bounded_and_exact_identity_matches(self) -> None:
        static_image = _static_ecl_image()
        reader = _Reader(_relocated_ecl_image(static_image))
        times = iter((10.0, 10.0005))
        capture = capture_runtime_ecl_image(
            reader,
            clock=lambda: next(times),
        )
        identity = compare_runtime_ecl_image(capture, static_image)
        self.assertTrue(identity.exact_match)
        self.assertIsNone(identity.first_difference_offset)
        self.assertEqual(capture.image_length, _IMAGE_LENGTH)
        self.assertEqual(capture.subroutine_count, 2)
        self.assertEqual(capture.timeline_count, 1)
        self.assertEqual(capture.read_count, 4)
        self.assertAlmostEqual(capture.capture_ms, 0.5)
        self.assertEqual(
            reader.reads,
            [
                (ECL_FILE_CONTEXT_ADDRESS, 8),
                (_RUNTIME_BASE, ECL_RUNTIME_HEADER_SIZE),
                (_RUNTIME_BASE, _IMAGE_LENGTH),
                (ECL_FILE_CONTEXT_ADDRESS, 8),
            ],
        )

    def test_non_relocation_mutation_cannot_receive_identity(self) -> None:
        static_image = _static_ecl_image()
        relocated = bytearray(_relocated_ecl_image(static_image))
        relocated[0x90] ^= 0x80
        capture = capture_runtime_ecl_image(_Reader(bytes(relocated)))
        identity = compare_runtime_ecl_image(capture, static_image)
        self.assertFalse(identity.exact_match)
        self.assertEqual(identity.first_difference_offset, 0x90)

    def test_capture_accepts_a_valid_high_linux_i386_mapping(self) -> None:
        runtime_base = 0xD75532B0
        static_image = _static_ecl_image()
        relocated = _relocated_ecl_image(
            static_image,
            runtime_base=runtime_base,
        )

        capture = capture_runtime_ecl_image(
            _Reader(relocated, runtime_base=runtime_base)
        )

        self.assertEqual(capture.runtime_base, runtime_base)
        self.assertTrue(
            compare_runtime_ecl_image(capture, static_image).exact_match
        )

    def test_context_churn_fails_closed(self) -> None:
        changed = struct.pack(
            "<II",
            _RUNTIME_BASE + 0x1000,
            _RUNTIME_BASE + 0x1000 + ECL_RUNTIME_HEADER_SIZE,
        )
        with self.assertRaisesRegex(RuntimeEclImageError, "changed"):
            capture_runtime_ecl_image(
                _Reader(
                    _relocated_ecl_image(_static_ecl_image()),
                    context_after=changed,
                )
            )

    def test_malformed_magic_and_end_sentinel_fail_closed(self) -> None:
        invalid_magic = bytearray(_relocated_ecl_image(_static_ecl_image()))
        struct.pack_into("<I", invalid_magic, 0, 0)
        with self.assertRaisesRegex(RuntimeEclImageError, "magic"):
            capture_runtime_ecl_image(_Reader(bytes(invalid_magic)))

        invalid_end = bytearray(_relocated_ecl_image(_static_ecl_image()))
        struct.pack_into("<I", invalid_end, 12, _RUNTIME_BASE + 0x20)
        with self.assertRaisesRegex(RuntimeEclImageError, "sentinel"):
            capture_runtime_ecl_image(_Reader(bytes(invalid_end)))

    def test_malformed_static_relocation_slot_fails_closed(self) -> None:
        static_image = bytearray(_static_ecl_image())
        capture = capture_runtime_ecl_image(
            _Reader(_relocated_ecl_image(bytes(static_image)))
        )
        struct.pack_into(
            "<I",
            static_image,
            ECL_TIMELINE_SLOT_OFFSET + 4 * 5,
            len(static_image) + 1,
        )
        with self.assertRaisesRegex(
            RuntimeEclImageError,
            "timeline slot 5",
        ):
            compare_runtime_ecl_image(capture, bytes(static_image))


if __name__ == "__main__":
    unittest.main()
