#!/usr/bin/env python3
"""Report the first exact semantic difference between two TH08 JSONL traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from th08_linux.semantic_trace import compare_semantic_traces  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--maximum-field-differences", type=int, default=64)
    return parser


def run(args: argparse.Namespace) -> int:
    report = compare_semantic_traces(
        args.left,
        args.right,
        maximum_field_differences=args.maximum_field_differences,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
