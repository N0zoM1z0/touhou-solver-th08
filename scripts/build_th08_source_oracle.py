#!/usr/bin/env python3
"""Build the tracked, dependency-free TH08 source differential oracle."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "native" / "th08_source_oracle"
DEFAULT_OUTPUT = (
    ROOT / "native" / "build" / "source-oracle" / "libth08_source_oracle.so"
)
_BUILD_FLAGS = (
    "c11",
    "O2",
    "fPIC",
    "shared",
    "fno-fast-math",
    "ffp-contract=off",
    "fvisibility=hidden",
)


def source_digest() -> str:
    digest = hashlib.sha256()
    for value in _BUILD_FLAGS:
        digest.update(value.encode())
        digest.update(b"\0")
    for path in (
        SOURCE_DIR / "th08_source_oracle.h",
        SOURCE_DIR / "th08_source_oracle.c",
    ):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def stamp_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.sha256")


def requires_rebuild(output: Path) -> bool:
    stamp = stamp_path(output)
    return (
        not output.exists()
        or not stamp.exists()
        or stamp.read_text(encoding="ascii").strip() != source_digest()
    )


def build(output: Path = DEFAULT_OUTPUT) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        raise RuntimeError("a C compiler is required for the TH08 source oracle")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-fPIC",
            "-shared",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-fvisibility=hidden",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(SOURCE_DIR),
            str(SOURCE_DIR / "th08_source_oracle.c"),
            "-lm",
            "-o",
            str(output),
        ],
        check=True,
    )
    stamp_path(output).write_text(source_digest() + "\n", encoding="ascii")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
