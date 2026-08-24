#!/usr/bin/env python3
"""Build the tracked, dependency-free TH08 source differential oracle."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "native" / "th08_source_oracle"
DEFAULT_OUTPUT = (
    ROOT / "native" / "build" / "source-oracle" / "libth08_source_oracle.so"
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
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
