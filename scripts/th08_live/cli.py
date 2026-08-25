"""Command-line schema for the TH08 live controller."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LiveParserDefaults:
    """Controller-owned defaults consumed by the pure parser builder."""

    planner_horizon: int
    planner_threat_horizon: int
    planner_beam_width: int
    control_delay_frames: int
    corridor_replan_frames: int
    corridor_lookahead_frames: int
    corridor_max_age_frames: int
    stage_transition_timeout_seconds: float
    terminal_inactive_grace_seconds: float


def build_live_parser(
    defaults: LiveParserDefaults,
    *,
    description: str | None,
) -> argparse.ArgumentParser:
    """Build the live-controller CLI without importing controller runtime."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--poll-ms", type=float, default=0.2)
    parser.add_argument("--log-every", type=int, default=30)
    parser.add_argument(
        "--horizon",
        type=int,
        default=defaults.planner_horizon,
    )
    parser.add_argument(
        "--threat-horizon",
        type=int,
        default=defaults.planner_threat_horizon,
        help=(
            "cheap terminal-action hazard rollout; heuristic only, never a "
            "viability certificate"
        ),
    )
    parser.add_argument(
        "--beam-width",
        type=int,
        default=defaults.planner_beam_width,
    )
    parser.add_argument(
        "--control-delay-frames",
        type=int,
        default=defaults.control_delay_frames,
        help="initial rolling-p90 previous-input prefix estimate",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        choices=(0, 1, 2, 3, 4),
        default=3,
        help=(
            "required runtime difficulty index: 0 Easy, 1 Normal, 2 Hard, "
            "3 Lunatic, 4 Extra"
        ),
    )
    parser.add_argument(
        "--corridor-every",
        type=int,
        default=defaults.corridor_replan_frames,
        help="game frames between asynchronous global corridor submissions",
    )
    parser.add_argument(
        "--corridor-lookahead",
        type=int,
        default=defaults.corridor_lookahead_frames,
        help="frames ahead on the corridor used as the local waypoint",
    )
    parser.add_argument(
        "--corridor-max-age",
        type=int,
        default=defaults.corridor_max_age_frames,
        help="discard a corridor result after this many game frames",
    )
    parser.add_argument(
        "--corridor-native-workers",
        type=int,
        choices=(1, 2, 3, 4),
        default=4,
        help=(
            "native viability worker cap on the asynchronous corridor "
            "thread; four preserves authoritative plan throughput, while "
            "smaller values are explicit contention ablations"
        ),
    )
    parser.add_argument(
        "--safety-value-horizon",
        type=int,
        default=0,
        help=(
            "optional max-min signed-clearance horizon in game frames; "
            "ordinary prepublication authority forces the full horizon and "
            "retains per-action values for continuous-position certificates"
        ),
    )
    parser.add_argument(
        "--losing-control-reserve",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "after an empty global kernel, rank fresh-hard-equivalent local "
            "endpoints by delay-scaled reversible boundary reserve; enabled "
            "for the versioned Stage-5 physical gate, with "
            "--no-losing-control-reserve as the exact rollback"
        ),
    )
    parser.add_argument(
        "--ordinary-preexhaustion-authority",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "enable the default-off all-phase exact-spell-id future-source "
            "lane plus the 4px Boolean-lower ordinary-nonspell global "
            "authority and causal active-policy layer predecessor; incomplete "
            "future birth/event coverage remains fail-closed"
        ),
    )
    parser.add_argument(
        "--future-source-retain-dir",
        type=Path,
        help=(
            "write content-addressed coherent future-source roots for "
            "offline replay; capture and I/O are shadow-only and never "
            "grant action authority"
        ),
    )
    parser.add_argument(
        "--future-source-retain-spell",
        action="append",
        type=int,
        default=[],
        metavar="ID",
        help=(
            "active spell ID eligible for shadow root retention; repeat for "
            "multiple cards"
        ),
    )
    parser.add_argument(
        "--future-source-retain-max-per-spell",
        type=int,
        default=1,
        metavar="N",
        help="maximum successfully retained coherent roots per selected spell",
    )
    parser.add_argument(
        "--input-clock-boundary-shadow",
        action="store_true",
        help=(
            "record the native FRScreen enemy-clock gate, active input, and "
            "player motion as read-only telemetry; never changes input, "
            "epochs, estimator state, or policy publication"
        ),
    )
    parser.add_argument(
        "--input-clock-shadow-sample-ms",
        type=float,
        default=1.0,
        help=(
            "minimum repeated-frame telemetry sampling cadence; this controls "
            "trace cost only and is never an episode classifier"
        ),
    )
    parser.add_argument(
        "--local-pipeline-root-shadow-every",
        type=int,
        default=0,
        metavar="DECISIONS",
        help=(
            "after input issue, sample an explicit observed/estimated-root "
            "certificate every N decisions; zero disables it, results never "
            "change the issued action, and the measured work may perturb the "
            "next controller cadence"
        ),
    )
    parser.add_argument(
        "--local-hazard-backend",
        choices=("numpy", "native"),
        default="native",
        help=(
            "local hazard-query implementation; the parity-gated native C "
            "ABI is the default and numpy is the explicit reference rollback"
        ),
    )
    parser.add_argument(
        "--local-beam-reducer",
        choices=("python", "native"),
        default="native",
        help=(
            "quantized beam deduplication and pruning implementation; the "
            "parity-gated native reducer is the default and python is the "
            "explicit reference rollback"
        ),
    )
    parser.add_argument(
        "--bullet-decode-backend",
        choices=("python", "native"),
        default="native",
        help=(
            "planning bullet-pool decoder; the parity-gated native packed "
            "snapshot is the default above its measured sparse crossover, "
            "python objects are the explicit reference rollback, and "
            "transform-runtime tracing always uses the diagnostic Python "
            "decoder"
        ),
    )
    parser.add_argument(
        "--viability-audit-dir",
        type=Path,
        help=(
            "write ignored neutral policy-input capsules for offline "
            "differential audit; diagnostic I/O may perturb timing"
        ),
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="disable the corridor layer for controlled A/B runs",
    )
    parser.add_argument(
        "--authority-only-corridor",
        action="store_true",
        help=(
            "submit expensive corridor solves only when the current exact "
            "time-scale schedule can grant their output action authority"
        ),
    )
    parser.add_argument(
        "--wait-gameplay",
        action="store_true",
        help="warm up at the menu and arm when idle route-2 gameplay begins",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=60.0,
        help="seconds allowed for --wait-gameplay",
    )
    parser.add_argument(
        "--expected-stage",
        type=int,
        choices=range(9),
        help="required stage-route index after menu confirmation",
    )
    parser.add_argument(
        "--terminal-stage",
        type=int,
        choices=range(9),
        help="treat this stage's first stable scene unload as trial completion",
    )
    parser.add_argument(
        "--stop-after-hits",
        type=int,
        default=1,
        help="stop after this many hits; zero keeps running",
    )
    parser.add_argument(
        "--post-hit-frames",
        type=int,
        default=30,
        help="trace frames retained after the hit limit is reached",
    )
    parser.add_argument(
        "--leave-running",
        action="store_false",
        dest="pause_on_exit",
        help="do not press Escape when a gameplay trial exits",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        help="exit safely when this file appears",
    )
    parser.set_defaults(pause_on_exit=True)
    parser.add_argument(
        "--trace-radius",
        type=float,
        default=0.0,
        help=(
            "include native projectile/item geometry within this player "
            "radius"
        ),
    )
    parser.add_argument(
        "--trace-items",
        action="store_true",
        help=(
            "also capture and serialize nearby items for --trace-radius; "
            "disabled by default when items cannot affect control"
        ),
    )
    parser.add_argument(
        "--trace-transform-runtime",
        action="store_true",
        help="include transform-relevant bullets from the full native pool",
    )
    parser.add_argument(
        "--trace-enemy-mode-transitions",
        action="store_true",
        help=(
            "capture active input and player +3/+5/+8 around the existing "
            "first-64 enemy-prefix read; mode fields have no action "
            "authority, while diagnostic reads/retries may perturb cadence"
        ),
    )
    parser.add_argument(
        "--trace-enemy-lifecycle-events",
        action="store_true",
        help=(
            "install the reversible bounded ordinary-enemy allocation, "
            "retirement, and forced-HP-zero event ring; trace only, runtime "
            "instrumentation, no action authority"
        ),
    )
    parser.add_argument(
        "--kill-before-saturation",
        action="store_true",
        help=(
            "prefer the same-direction unfocused complete action for an "
            "observed low-HP ordinary enemy, but only when the fresh issue "
            "transaction certifies it safe and retains any applicable "
            "global action constraint; default off and hard no-Bomb only"
        ),
    )
    parser.add_argument(
        "--diagnostic-continue-root-only-scale",
        action="store_true",
        help=(
            "do not terminate a diagnostic whole-stage run when only the "
            "observed root time scale is known; assume that root constant "
            "for the finite planner horizon with unknown-direction and no "
            "hard scale authority"
        ),
    )
    parser.add_argument(
        "--runtime-ecl-static-image",
        type=Path,
        help=(
            "one decoded static ECL image for a default-off post-issue "
            "one-shot runtime byte-identity observation"
        ),
    )
    parser.add_argument(
        "--runtime-ecl-static-sha256",
        help="required immutable SHA-256 for --runtime-ecl-static-image",
    )
    parser.add_argument(
        "--enable-finalb-scale-source-authority",
        action="store_true",
        help=(
            "enable the exact Final-B difficulty-selected spell-family "
            "complete-source schedule consumer; requires main-difficulty "
            "stage 7, hard no-Bomb, and exact runtime ECL identity"
        ),
    )
    bomb_group = parser.add_mutually_exclusive_group()
    bomb_group.add_argument(
        "--normal-bomb",
        action="store_true",
        help="permit a pre-hit Bomb when every next-frame move overlaps",
    )
    bomb_group.add_argument(
        "--no-bomb",
        action="store_true",
        help="forbid normal Bomb and deathbomb input",
    )
    parser.add_argument(
        "--auto-confirm-every",
        type=int,
        default=0,
        help=(
            "pulse a fresh Z edge this often in sustained empty scenes; "
            "zero disables"
        ),
    )
    parser.add_argument(
        "--auto-confirm-idle-frames",
        type=int,
        default=20,
        help="empty-scene frames required before automatic Z pulsing",
    )
    parser.add_argument(
        "--stage-transition-timeout",
        type=float,
        default=defaults.stage_transition_timeout_seconds,
        help="seconds allowed for a non-final stage resource transition",
    )
    parser.add_argument(
        "--terminal-inactive-grace",
        type=float,
        default=defaults.terminal_inactive_grace_seconds,
        help="stable inactive seconds required after the final stage",
    )
    parser.add_argument("--armed", action="store_true")
    return parser


__all__ = ["LiveParserDefaults", "build_live_parser"]
