#!/usr/bin/env python3
"""Inspect TH08 replay metadata, RNG seeds, and stored input streams.

The parser reproduces replay loading at 0x00451D90: rolling-byte decode,
checksum validation, and the same 0x2000-ring LZSS decoder used by PBGZ.
It can emit compact held-input runs; it does not copy replay payloads.

The stage input extent can include words recorded after playable stage teardown
and before the result-screen save. Its length is therefore a storage bound,
not source authority for playable stage duration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from th08_pbgz import (
    PbgzError,
    lzss_compress_literals,
    lzss_decompress,
)


MAGIC = b"T8RP"
VERSION = 6
HEADER_SIZE = 0x68
CHECKSUM_INITIAL = 0x3F000318
STAGE_COUNT = 9


class ReplayError(ValueError):
    """Raised when a replay violates checks made by the game loader."""


@dataclass(frozen=True)
class ReplayStage:
    stage_index: int
    data_offset: int
    auxiliary_offset: int
    rng_seed: int
    lives: int
    bombs: int
    byte_1c: int
    byte_1f: int
    input_record_stride: int
    frame_count: int
    input_sha256: str
    bomb_press_frames: tuple[int, ...]

    @property
    def stored_input_word_count(self) -> int:
        return self.frame_count


@dataclass(frozen=True)
class ReplayInputRun:
    start_frame: int
    end_frame_exclusive: int
    input_mask: int


@dataclass(frozen=True)
class ReplayMetadata:
    name: str
    sha256: str
    file_size: int
    encoded_main_size: int
    compressed_size: int
    uncompressed_size: int
    trailing_size: int
    checksum: int
    rolling_key: int
    route_id: int
    difficulty_index: int
    extended_input_records: bool
    stages: tuple[ReplayStage, ...]


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _stage_end(decoded: bytes, data_offset: int) -> int:
    offsets = {
        _u32(decoded, table + 4 * index)
        for table in (32, 68)
        for index in range(STAGE_COUNT)
    }
    candidates = [offset for offset in offsets if offset > data_offset]
    if not candidates:
        raise ReplayError(f"stage record at {data_offset:#x} has no following extent")
    return min(candidates)


def extract_stage_inputs(
    decoded: bytes, stage: ReplayStage | int, *, extended: bool | None = None
) -> tuple[int, ...]:
    """Return every stored input word in the stage-data extent.

    A playable stage may tear down before consuming the full saved extent.
    """

    data_offset = stage.data_offset if isinstance(stage, ReplayStage) else stage
    if extended is None:
        extended = bool(decoded[6])
    stride = 6 if extended else 2
    start = data_offset + 36
    end = _stage_end(decoded, data_offset)
    if end < start or (end - start) % stride:
        raise ReplayError(
            f"stage input extent [{start:#x}, {end:#x}) is not {stride}-byte aligned"
        )
    return tuple(
        struct.unpack_from("<H", decoded, offset)[0]
        for offset in range(start, end, stride)
    )


def replace_stage_inputs(
    decoded: bytes,
    stage: ReplayStage,
    *,
    start_frame: int,
    input_masks: tuple[int, ...],
) -> bytes:
    """Replace an exact replay input interval without touching future state.

    Only replay command words are changed.  Extended-record payloads, stage
    roots, content, and later input commands remain byte-identical.
    """

    if type(decoded) is not bytes:
        raise ValueError("decoded replay must be exact bytes")
    if type(stage) is not ReplayStage:
        raise ValueError("stage must be decoded replay metadata")
    if type(start_frame) is not int or start_frame < 0:
        raise ValueError("replay replacement start must be nonnegative")
    if type(input_masks) is not tuple or any(
        type(mask) is not int or not 0 <= mask <= 0xFFFF
        for mask in input_masks
    ):
        raise ValueError("replay replacements must be an exact u16 tuple")
    if start_frame + len(input_masks) > stage.frame_count:
        raise ValueError("replay replacement exceeds the stage input extent")

    stride = stage.input_record_stride
    if stride not in (2, 6):
        raise ReplayError(f"unsupported replay input stride {stride}")
    mutated = bytearray(decoded)
    first_offset = stage.data_offset + 36 + start_frame * stride
    for index, mask in enumerate(input_masks):
        struct.pack_into("<H", mutated, first_offset + index * stride, mask)
    return bytes(mutated)


def encode_replay(decoded: bytes) -> bytes:
    """Encode a decoded TH08 replay into a game-loadable byte stream.

    The payload compressor is deliberately literal-only.  The resulting file
    is larger than the original but decodes to the exact supplied bytes and
    retains the original trailing replay metadata.
    """

    if type(decoded) is not bytes or len(decoded) < HEADER_SIZE:
        raise ValueError("decoded replay is smaller than its header")
    if decoded[:4] != MAGIC:
        raise ReplayError("decoded replay has invalid magic")
    if struct.unpack_from("<H", decoded, 4)[0] != VERSION:
        raise ReplayError("decoded replay has unsupported version")

    uncompressed_size = _u32(decoded, 28)
    payload_end = HEADER_SIZE + uncompressed_size
    if payload_end > len(decoded):
        raise ReplayError("decoded replay payload is truncated")
    payload = decoded[HEADER_SIZE:payload_end]
    trailing = decoded[payload_end:]
    compressed = lzss_compress_literals(payload)

    main = bytearray(decoded[:HEADER_SIZE])
    encoded_main_size = HEADER_SIZE + len(compressed)
    struct.pack_into("<I", main, 12, encoded_main_size)
    struct.pack_into("<I", main, 24, len(compressed))
    struct.pack_into("<I", main, 28, uncompressed_size)
    main.extend(compressed)
    checksum = (
        CHECKSUM_INITIAL + sum(main[21:encoded_main_size])
    ) & 0xFFFFFFFF
    struct.pack_into("<I", main, 16, checksum)

    encoded = bytearray(main)
    key = encoded[21]
    for offset in range(24, encoded_main_size):
        encoded[offset] = (encoded[offset] + key) & 0xFF
        key = (key + 7) & 0xFF
    return bytes(encoded) + trailing


def compress_input_runs(inputs: tuple[int, ...]) -> tuple[ReplayInputRun, ...]:
    if not inputs:
        return ()
    runs: list[ReplayInputRun] = []
    start = 0
    current = inputs[0]
    for frame, value in enumerate(inputs[1:], 1):
        if value != current:
            runs.append(ReplayInputRun(start, frame, current))
            start = frame
            current = value
    runs.append(ReplayInputRun(start, len(inputs), current))
    return tuple(runs)


def _bomb_press_frames(inputs: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        frame
        for frame, value in enumerate(inputs)
        if value & 0x02 and (frame == 0 or not inputs[frame - 1] & 0x02)
    )


def decode_replay(path: Path) -> tuple[ReplayMetadata, bytes]:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ReplayError(f"{path}: replay is smaller than its {HEADER_SIZE}-byte header")
    if raw[:4] != MAGIC:
        raise ReplayError(f"{path}: invalid replay magic {raw[:4]!r}")
    if struct.unpack_from("<H", raw, 4)[0] != VERSION:
        raise ReplayError(f"{path}: unsupported replay version")

    encoded_main_size = _u32(raw, 12)
    if not HEADER_SIZE <= encoded_main_size <= len(raw):
        raise ReplayError(f"{path}: invalid encoded main size {encoded_main_size:#x}")

    main = bytearray(raw[:encoded_main_size])
    rolling_key = main[21]
    key = rolling_key
    for offset in range(24, encoded_main_size):
        main[offset] = (main[offset] - key) & 0xFF
        key = (key + 7) & 0xFF

    stored_checksum = _u32(main, 16)
    computed_checksum = (CHECKSUM_INITIAL + sum(main[21:encoded_main_size])) & 0xFFFFFFFF
    if computed_checksum != stored_checksum:
        raise ReplayError(
            f"{path}: checksum mismatch, stored {stored_checksum:#x}, "
            f"computed {computed_checksum:#x}"
        )

    compressed_size = _u32(main, 24)
    uncompressed_size = _u32(main, 28)
    if HEADER_SIZE + compressed_size != encoded_main_size:
        raise ReplayError(
            f"{path}: compressed extent does not match encoded main size"
        )
    try:
        payload = lzss_decompress(
            bytes(main[HEADER_SIZE:encoded_main_size]), uncompressed_size
        )
    except PbgzError as exc:
        raise ReplayError(f"{path}: invalid compressed payload: {exc}") from exc

    decoded = bytes(main[:HEADER_SIZE]) + payload + raw[encoded_main_size:]
    if len(decoded) < 108:
        raise ReplayError(f"{path}: decoded replay lacks route/difficulty bytes")

    extended_input_records = bool(decoded[6])
    stages = []
    for stage_index in range(STAGE_COUNT):
        data_offset = _u32(decoded, 32 + 4 * stage_index)
        auxiliary_offset = _u32(decoded, 68 + 4 * stage_index)
        if not data_offset:
            continue
        if data_offset + 36 > len(decoded):
            raise ReplayError(
                f"{path}: stage {stage_index} record at {data_offset:#x} is truncated"
            )
        stage = ReplayStage(
                stage_index=stage_index,
                data_offset=data_offset,
                auxiliary_offset=auxiliary_offset,
                rng_seed=struct.unpack_from("<H", decoded, data_offset + 26)[0],
                lives=decoded[data_offset + 29],
                bombs=decoded[data_offset + 30],
                byte_1c=decoded[data_offset + 28],
                byte_1f=decoded[data_offset + 31],
                input_record_stride=6 if extended_input_records else 2,
                frame_count=0,
                input_sha256="",
                bomb_press_frames=(),
            )
        inputs = extract_stage_inputs(
            decoded, stage, extended=extended_input_records
        )
        input_bytes = b"".join(struct.pack("<H", value) for value in inputs)
        stages.append(
            ReplayStage(
                **{
                    **asdict(stage),
                    "frame_count": len(inputs),
                    "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
                    "bomb_press_frames": _bomb_press_frames(inputs),
                }
            )
        )

    metadata = ReplayMetadata(
        name=path.name,
        sha256=hashlib.sha256(raw).hexdigest(),
        file_size=len(raw),
        encoded_main_size=encoded_main_size,
        compressed_size=compressed_size,
        uncompressed_size=uncompressed_size,
        trailing_size=len(raw) - encoded_main_size,
        checksum=stored_checksum,
        rolling_key=rolling_key,
        route_id=decoded[106],
        difficulty_index=decoded[107],
        extended_input_records=extended_input_records,
        stages=tuple(stages),
    )
    return metadata, decoded


def _paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*.rpy"))
    return [path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="replay file or directory")
    parser.add_argument("output", nargs="?", type=Path, help="optional JSON report")
    parser.add_argument(
        "--trace-dir",
        type=Path,
        help="write compact per-stage held-input runs as derived JSON",
    )
    args = parser.parse_args(argv)
    try:
        reports = []
        for path in _paths(args.input):
            metadata, decoded = decode_replay(path)
            reports.append(asdict(metadata))
            seeds = ", ".join(
                f"stage{stage.stage_index}=0x{stage.rng_seed:04x}"
                for stage in metadata.stages
            )
            print(
                f"{metadata.name}: route={metadata.route_id} "
                f"difficulty={metadata.difficulty_index} {seeds}"
            )
            if args.trace_dir:
                args.trace_dir.mkdir(parents=True, exist_ok=True)
                for stage in metadata.stages:
                    inputs = extract_stage_inputs(decoded, stage)
                    trace = {
                        "source_replay": metadata.name,
                        "source_sha256": metadata.sha256,
                        "route_id": metadata.route_id,
                        "difficulty_index": metadata.difficulty_index,
                        "stage_index": stage.stage_index,
                        "rng_seed": stage.rng_seed,
                        "frame_count": stage.frame_count,
                        "input_sha256": stage.input_sha256,
                        "bomb_press_frames": list(stage.bomb_press_frames),
                        "runs": [asdict(run) for run in compress_input_runs(inputs)],
                    }
                    output = args.trace_dir / (
                        f"{path.stem}_stage{stage.stage_index}_inputs.json"
                    )
                    output.write_text(
                        json.dumps(trace, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(reports, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return 0
    except (OSError, ReplayError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
