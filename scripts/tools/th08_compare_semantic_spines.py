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

from th08_linux.semantic_trace import (  # noqa: E402
    compare_semantic_traces,
    compare_semantic_traces_by_replay_frame,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--maximum-field-differences", type=int, default=64)
    parser.add_argument(
        "--align-replay-frame",
        action="store_true",
        help=(
            "treat left as a dense reference and compare only replay frames "
            "present in the right-hand sparse sample"
        ),
    )
    return parser


def run(args: argparse.Namespace) -> int:
    comparator = (
        compare_semantic_traces_by_replay_frame
        if args.align_replay_frame
        else compare_semantic_traces
    )
    report = comparator(
        args.left,
        args.right,
        maximum_field_differences=args.maximum_field_differences,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
