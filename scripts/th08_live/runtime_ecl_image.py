"""Exact, bounded identity for TH08's relocated runtime ECL image."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import struct
import time
from typing import Callable, Protocol


ECL_FILE_CONTEXT_ADDRESS = 0x004ECCB8
ECL_MAGIC = 0x00000800
ECL_RUNTIME_HEADER_SIZE = 0x48
ECL_SUBROUTINE_TABLE_OFFSET = 0x48
ECL_TIMELINE_SLOT_OFFSET = 0x08
ECL_TIMELINE_SLOT_COUNT = 16
MAXIMUM_RUNTIME_ECL_IMAGE_SIZE = 8 * 1024 * 1024
MAXIMUM_ECL_SUBROUTINES = 4096
MINIMUM_RUNTIME_ADDRESS = 0x00010000
MAXIMUM_RUNTIME_ADDRESS = 0xFFFFFFFF


class RuntimeEclImageError(ValueError):
    """Raised when runtime ECL identity cannot be established safely."""


class RuntimeEclImageReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class RuntimeEclImageCapture:
    runtime_base: int
    image_length: int
    subroutine_count: int
    timeline_count: int
    relocated_sha256: str
    normalized_sha256: str
    capture_ms: float
    read_count: int
    relocated_image: bytes = field(repr=False)
    normalized_image: bytes = field(repr=False)

    def record(self) -> dict[str, object]:
        return {
            "schema": "th08-runtime-ecl-image-capture-v1",
            "runtime_base": self.runtime_base,
            "image_length": self.image_length,
            "subroutine_count": self.subroutine_count,
            "timeline_count": self.timeline_count,
            "relocated_sha256": self.relocated_sha256,
            "normalized_sha256": self.normalized_sha256,
            "capture_ms": self.capture_ms,
            "read_count": self.read_count,
        }


@dataclass(frozen=True, slots=True)
class RuntimeEclImageIdentity:
    exact_match: bool
    static_sha256: str
    normalized_runtime_sha256: str
    image_length: int
    first_difference_offset: int | None

    def record(self) -> dict[str, object]:
        return {
            "schema": "th08-runtime-ecl-image-identity-v1",
            "exact_match": self.exact_match,
            "static_sha256": self.static_sha256,
            "normalized_runtime_sha256": self.normalized_runtime_sha256,
            "image_length": self.image_length,
            "first_difference_offset": self.first_difference_offset,
        }


def _header_counts(image: bytes) -> tuple[int, int]:
    if len(image) < ECL_RUNTIME_HEADER_SIZE:
        raise RuntimeEclImageError("ECL image omits the fixed header")
    magic, subroutine_count, timeline_count = struct.unpack_from(
        "<IHH",
        image,
    )
    if magic != ECL_MAGIC:
        raise RuntimeEclImageError("runtime ECL magic is invalid")
    if not 0 < subroutine_count <= MAXIMUM_ECL_SUBROUTINES:
        raise RuntimeEclImageError("runtime ECL subroutine count is invalid")
    if not 0 <= timeline_count < ECL_TIMELINE_SLOT_COUNT:
        raise RuntimeEclImageError("runtime ECL timeline count is invalid")
    return subroutine_count, timeline_count


def _relocated_image_length(header: bytes, runtime_base: int) -> int:
    subroutine_count, timeline_count = _header_counts(header)
    relocated_end = struct.unpack_from(
        "<I",
        header,
        ECL_TIMELINE_SLOT_OFFSET + 4 * timeline_count,
    )[0]
    image_length = relocated_end - runtime_base
    minimum_length = ECL_SUBROUTINE_TABLE_OFFSET + 4 * subroutine_count
    if not minimum_length <= image_length <= MAXIMUM_RUNTIME_ECL_IMAGE_SIZE:
        raise RuntimeEclImageError("runtime ECL data-end sentinel is invalid")
    return image_length


def normalize_relocated_ecl_image(
    relocated_image: bytes,
    *,
    runtime_base: int,
) -> bytes:
    """Reverse only relocations statically observed in ``ecl_load_file``."""

    subroutine_count, timeline_count = _header_counts(relocated_image)
    image_length = _relocated_image_length(relocated_image, runtime_base)
    if len(relocated_image) != image_length:
        raise RuntimeEclImageError("runtime ECL image length is inconsistent")

    normalized = bytearray(relocated_image)
    for index in range(ECL_TIMELINE_SLOT_COUNT):
        offset = ECL_TIMELINE_SLOT_OFFSET + 4 * index
        pointer = struct.unpack_from("<I", relocated_image, offset)[0]
        relative = pointer - runtime_base
        if not 0 <= relative <= image_length:
            raise RuntimeEclImageError(
                f"runtime ECL timeline slot {index} is out of range"
            )
        struct.pack_into("<I", normalized, offset, relative)

    for index in range(subroutine_count):
        offset = ECL_SUBROUTINE_TABLE_OFFSET + 4 * index
        pointer = struct.unpack_from("<I", relocated_image, offset)[0]
        relative = pointer - runtime_base
        if not ECL_RUNTIME_HEADER_SIZE <= relative < image_length:
            raise RuntimeEclImageError(
                f"runtime ECL subroutine pointer {index} is out of range"
            )
        struct.pack_into("<I", normalized, offset, relative)

    normalized_end = struct.unpack_from(
        "<I",
        normalized,
        ECL_TIMELINE_SLOT_OFFSET + 4 * timeline_count,
    )[0]
    if normalized_end != image_length:
        raise RuntimeEclImageError("normalized ECL data-end sentinel differs")
    return bytes(normalized)


def _validate_static_ecl_image(image: bytes) -> tuple[int, int]:
    subroutine_count, timeline_count = _header_counts(image)
    minimum_length = ECL_SUBROUTINE_TABLE_OFFSET + 4 * subroutine_count
    if not minimum_length <= len(image) <= MAXIMUM_RUNTIME_ECL_IMAGE_SIZE:
        raise RuntimeEclImageError("static ECL image length is invalid")
    static_end = struct.unpack_from(
        "<I",
        image,
        ECL_TIMELINE_SLOT_OFFSET + 4 * timeline_count,
    )[0]
    if static_end != len(image):
        raise RuntimeEclImageError("static ECL data-end sentinel is invalid")
    for index in range(ECL_TIMELINE_SLOT_COUNT):
        relative = struct.unpack_from(
            "<I",
            image,
            ECL_TIMELINE_SLOT_OFFSET + 4 * index,
        )[0]
        if not 0 <= relative <= len(image):
            raise RuntimeEclImageError(
                f"static ECL timeline slot {index} is out of range"
            )
    for index in range(subroutine_count):
        relative = struct.unpack_from(
            "<I",
            image,
            ECL_SUBROUTINE_TABLE_OFFSET + 4 * index,
        )[0]
        if not ECL_RUNTIME_HEADER_SIZE <= relative < len(image):
            raise RuntimeEclImageError(
                f"static ECL subroutine pointer {index} is out of range"
            )
    return subroutine_count, timeline_count


def capture_runtime_ecl_image(
    reader: RuntimeEclImageReader,
    *,
    context_address: int = ECL_FILE_CONTEXT_ADDRESS,
    clock: Callable[[], float] = time.perf_counter,
) -> RuntimeEclImageCapture:
    """Capture one exact stage ECL image under a stable context pointer."""

    started = clock()
    context_before = reader.read(context_address, 8)
    if len(context_before) != 8:
        raise RuntimeEclImageError("ECL context read is truncated")
    runtime_base, subroutine_table = struct.unpack("<II", context_before)
    if not (
        MINIMUM_RUNTIME_ADDRESS
        <= runtime_base
        <= MAXIMUM_RUNTIME_ADDRESS - ECL_RUNTIME_HEADER_SIZE
    ):
        raise RuntimeEclImageError("runtime ECL image base is invalid")
    if (
        runtime_base + MAXIMUM_RUNTIME_ECL_IMAGE_SIZE > 0x100000000
        or subroutine_table != runtime_base + ECL_SUBROUTINE_TABLE_OFFSET
    ):
        raise RuntimeEclImageError("runtime ECL subroutine table is invalid")

    header = reader.read(runtime_base, ECL_RUNTIME_HEADER_SIZE)
    image_length = _relocated_image_length(header, runtime_base)
    relocated_image = reader.read(runtime_base, image_length)
    if len(relocated_image) != image_length:
        raise RuntimeEclImageError("runtime ECL image read is truncated")
    if relocated_image[:ECL_RUNTIME_HEADER_SIZE] != header:
        raise RuntimeEclImageError("runtime ECL header changed during capture")

    context_after = reader.read(context_address, 8)
    if context_after != context_before:
        raise RuntimeEclImageError("runtime ECL context changed during capture")

    normalized_image = normalize_relocated_ecl_image(
        relocated_image,
        runtime_base=runtime_base,
    )
    subroutine_count, timeline_count = _header_counts(relocated_image)
    capture_ms = (clock() - started) * 1000.0
    return RuntimeEclImageCapture(
        runtime_base=runtime_base,
        image_length=image_length,
        subroutine_count=subroutine_count,
        timeline_count=timeline_count,
        relocated_sha256=hashlib.sha256(relocated_image).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized_image).hexdigest(),
        capture_ms=capture_ms,
        read_count=4,
        relocated_image=relocated_image,
        normalized_image=normalized_image,
    )


def compare_runtime_ecl_image(
    capture: RuntimeEclImageCapture,
    static_image: bytes,
) -> RuntimeEclImageIdentity:
    """Compare normalized runtime bytes to one decoded static ECL image."""

    static_subroutines, static_timelines = _validate_static_ecl_image(
        static_image
    )
    if (
        static_subroutines != capture.subroutine_count
        or static_timelines != capture.timeline_count
    ):
        first_difference = 4
    else:
        first_difference = next(
            (
                index
                for index, (runtime_byte, static_byte) in enumerate(
                    zip(capture.normalized_image, static_image, strict=False)
                )
                if runtime_byte != static_byte
            ),
            None,
        )
        if (
            first_difference is None
            and len(capture.normalized_image) != len(static_image)
        ):
            first_difference = min(
                len(capture.normalized_image),
                len(static_image),
            )
    static_sha256 = hashlib.sha256(static_image).hexdigest()
    return RuntimeEclImageIdentity(
        exact_match=(
            first_difference is None
            and len(static_image) == capture.image_length
        ),
        static_sha256=static_sha256,
        normalized_runtime_sha256=capture.normalized_sha256,
        image_length=capture.image_length,
        first_difference_offset=first_difference,
    )


__all__ = [
    "ECL_FILE_CONTEXT_ADDRESS",
    "ECL_MAGIC",
    "ECL_RUNTIME_HEADER_SIZE",
    "ECL_SUBROUTINE_TABLE_OFFSET",
    "ECL_TIMELINE_SLOT_COUNT",
    "ECL_TIMELINE_SLOT_OFFSET",
    "MAXIMUM_RUNTIME_ECL_IMAGE_SIZE",
    "RuntimeEclImageCapture",
    "RuntimeEclImageError",
    "RuntimeEclImageIdentity",
    "capture_runtime_ecl_image",
    "compare_runtime_ecl_image",
    "normalize_relocated_ecl_image",
]
