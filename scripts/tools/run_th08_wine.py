#!/usr/bin/env python3
"""Run exact TH08 under an isolated Win32 Wine prefix and private X display."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from th08_stage_ecl_catalog import (  # noqa: E402
    FINAL_B_ECL_SHA256,
    PRACTICE_STAGE_ECL_IDENTITIES,
    PRACTICE_STAGE_KEYS,
    SCALE_MODEL_FINAL_B,
)
from th08_replay import decode_replay  # noqa: E402


ROOT = SCRIPTS_ROOT.parent
REFERENCE = ROOT / "reference"
GAME_FILE_SHA256 = {
    "th08.exe": "330fbdbf58a710829d65277b4f312cfbb38d5448b3df523e79350b879213d924",
    "th08.dat": "9d7edf43b8ddd347cbb641836f6b5050745dd936f688daebbf9382ca557043bb",
    "thbgm.dat": "2c2ef05f9ff6f43f752dae5da519a2477372c3f8875b7b44996a8f69fdad4d89",
}
FULL_UNLOCK_SCORE_SHA256 = (
    "9486920663319c9a438c508d3e3a8f8010cdb6f8e5bc1d658811f09071e356f1"
)
EXPECTED_CONFIG_SHA256 = (
    "bcd6286bc188e8b58f1c9522975fe721c7cb03c203d96151a7dd897a7cd6290b"
)
PYTHON_EXE_SHA256 = (
    "e60592888c3128132df3489a2462716bb268063bfe3564bfe1f2f3dbe9ceafd1"
)
NATIVE_LIBRARY = (
    ROOT
    / "native"
    / "build"
    / "windows-x86"
    / "touhou_viability.dll"
)
NATIVE_LIBRARY_SHA256 = (
    "aaa39cdc3768ba1c2c2c93e2d6fa715e4e15fd550c7aba75a1aff8c673a4e43f"
)
PREFIX_MARKER = ".th08-wine-win32-ready-v1.json"
WINE_FULL_ROUTE_AGENT_DURATION_SECONDS = 86_400.0
WINE_FULL_ROUTE_TRIAL_TIMEOUT_SECONDS = 86_700.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def windows_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_absolute():
        raise ValueError("Wine path must be absolute")
    return "Z:" + str(resolved).replace("/", "\\")


def pe_machine(path: Path) -> int:
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError(f"not a PE image: {path}")
        source.seek(0x3C)
        header_offset = struct.unpack("<I", source.read(4))[0]
        source.seek(header_offset)
        if source.read(4) != b"PE\0\0":
            raise ValueError(f"invalid PE signature: {path}")
        return struct.unpack("<H", source.read(2))[0]


def repository_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repository_clean() -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return not status.strip()


def prefix_processes(prefix: Path) -> list[dict[str, Any]]:
    """Return only processes whose environment owns the exact prefix."""

    wanted = os.path.realpath(prefix.resolve())
    matches: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            values: dict[str, str] = {}
            for item in (entry / "environ").read_bytes().split(b"\0"):
                if b"=" not in item:
                    continue
                key, value = item.split(b"=", 1)
                if key in (b"WINEPREFIX", b"DISPLAY"):
                    values[key.decode()] = value.decode(errors="replace")
            if os.path.realpath(values.get("WINEPREFIX", "")) != wanted:
                continue
            command = (entry / "cmdline").read_bytes().replace(
                b"\0", b" "
            ).decode(errors="replace").strip()
            matches.append(
                {
                    "pid": int(entry.name),
                    "command": command,
                    "display": values.get("DISPLAY"),
                }
            )
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return sorted(matches, key=lambda item: int(item["pid"]))


def wait_prefix_exit(
    prefix: Path,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and prefix_processes(prefix):
        time.sleep(0.05)
    return prefix_processes(prefix)


def stop_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def select_display(
    requested: str,
    *,
    socket_root: Path = Path("/tmp/.X11-unix"),
    lock_root: Path = Path("/tmp"),
) -> str:
    if requested != "auto":
        if not requested.startswith(":") or not requested[1:].isdigit():
            raise ValueError("display must be 'auto' or :NUMBER")
        candidates = (int(requested[1:]),)
    else:
        candidates = range(98, 128)
    for number in candidates:
        socket = socket_root / f"X{number}"
        lock = lock_root / f".X{number}-lock"
        if not socket.exists() and not lock.exists():
            return f":{number}"
    raise RuntimeError("no free TH08 X display is available")


def validate_cpu_list(value: str) -> None:
    result = subprocess.run(
        ["taskset", "-c", value, "true"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        raise ValueError(f"invalid taskset CPU list: {value}")


def _format_cpu_list(cpus: tuple[int, ...]) -> str:
    if not cpus:
        raise ValueError("CPU affinity cannot be empty")
    ranges: list[str] = []
    start = previous = cpus[0]
    for cpu in cpus[1:]:
        if cpu == previous + 1:
            previous = cpu
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = cpu
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


def select_cpu_list(
    requested: str,
    *,
    available_cpus: set[int] | frozenset[int] | None = None,
) -> str:
    """Resolve ``auto`` inside the host's effective affinity boundary.

    Historical trials reserved the lower half of a 48-vCPU host and ran TH08
    on 24-47.  Preserve that isolation policy after VPS resizing by selecting
    the upper half of the CPUs this process is actually allowed to use.  An
    explicit taskset expression remains untouched and is validated by the
    caller.
    """

    if requested != "auto":
        return requested
    allowed = tuple(
        sorted(
            os.sched_getaffinity(0)
            if available_cpus is None
            else available_cpus
        )
    )
    if not allowed:
        raise RuntimeError("host exposes no CPUs in the effective affinity")
    selected = allowed[len(allowed) // 2 :] if len(allowed) > 1 else allowed
    return _format_cpu_list(selected)


def validate_prefix_target(prefix: Path) -> None:
    resolved = prefix.resolve()
    forbidden = {Path("/"), Path.home().resolve(), ROOT.resolve()}
    if resolved in forbidden or len(resolved.parts) < 5:
        raise ValueError(f"refusing broad Wine prefix target: {resolved}")


def provision_replay_slot(
    source: Path,
    game_dir: Path,
    *,
    slot: int,
    expected_sha256: str,
) -> tuple[Path, bool]:
    """Install one exact replay without replacing an existing slot."""

    if not 1 <= slot <= 15:
        raise ValueError("Wine replay slot must be in 1..15")
    source = source.resolve(strict=True)
    expected_sha256 = expected_sha256.lower()
    if sha256(source) != expected_sha256:
        raise RuntimeError("Wine replay input SHA-256 mismatch")
    destination = game_dir / "replay" / f"th8_{slot:02d}.rpy"
    if destination.exists():
        if not destination.is_file():
            raise RuntimeError(
                f"Wine replay destination is not a file: {destination}"
            )
        if sha256(destination) != expected_sha256:
            raise RuntimeError(
                "refusing to replace an occupied Wine replay slot: "
                f"{destination}"
            )
        return destination, False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as replay_input, destination.open(
            "xb"
        ) as replay_output:
            shutil.copyfileobj(replay_input, replay_output, 1 << 20)
        if sha256(destination) != expected_sha256:
            raise RuntimeError("provisioned Wine replay failed verification")
    except BaseException:
        if destination.is_file():
            destination.unlink()
        raise
    return destination, True


def remove_provisioned_replay(
    destination: Path,
    *,
    expected_sha256: str,
) -> None:
    """Remove only an exact replay file created by this host invocation."""

    if not destination.exists():
        return
    if not destination.is_file() or sha256(destination) != expected_sha256:
        raise RuntimeError(
            "refusing to remove a changed provisioned replay: "
            f"{destination}"
        )
    destination.unlink()


def build_windows_controller_command(
    *,
    mode: str,
    python: Path,
    game_dir: Path,
    artifact_dir: Path,
    agent_duration: float,
    trial_timeout: float,
    kill_before_saturation: bool,
    ordinary_preexhaustion_authority: bool,
    authority_only_corridor: bool,
    trace_items: bool,
    difficulty: str = "lunatic",
    practice_stage: str = "5",
    diagnostic_continue_root_only_scale: bool = False,
    future_source_retain_spells: tuple[int, ...] = (),
    future_source_retain_max_per_spell: int = 1,
    replay_slot: int = 1,
    replay_expected_sha256: str | None = None,
    replay_route_id: int = 2,
    replay_difficulty_index: int = 3,
    replay_stage_index: int = 5,
    replay_start_manager_frame: int = 600,
    replay_gameplay_epochs: int = 300,
    replay_collision_control_projection: bool = False,
) -> list[str]:
    if difficulty not in {"easy", "normal", "hard", "lunatic"}:
        raise ValueError(f"unsupported main difficulty: {difficulty}")
    launcher = ROOT / "scripts" / "tools" / "run_th08_wine_launch.bat"
    if mode == "smoke":
        return [
            windows_path(python),
            windows_path(ROOT / "scripts" / "tools" / "th08_wine_smoke.py"),
            "--game-dir",
            windows_path(game_dir),
            "--launch-bat",
            windows_path(launcher),
            "--report",
            windows_path(artifact_dir / "windows-smoke.json"),
        ]
    if mode == "practice":
        stage_identity = PRACTICE_STAGE_ECL_IDENTITIES[practice_stage]
        command = [
            windows_path(python),
            windows_path(ROOT / "scripts" / "th08_practice_supervisor.py"),
            "--armed",
            "--refuse-existing",
            "--stage",
            practice_stage,
            "--difficulty",
            difficulty,
            "--unlock-requested-stage",
            "--game-dir",
            windows_path(game_dir),
            "--launch-bat",
            windows_path(launcher),
            "--agent-duration",
            str(agent_duration),
            "--trial-timeout",
            str(trial_timeout),
            "--runtime-ecl-static-image",
            windows_path(
                ROOT / "artifacts" / "decoded" / stage_identity.filename
            ),
            "--runtime-ecl-static-sha256",
            stage_identity.sha256,
        ]
        if stage_identity.scale_model == SCALE_MODEL_FINAL_B:
            command.append("--enable-finalb-scale-source-authority")
        if ordinary_preexhaustion_authority:
            command.append("--ordinary-preexhaustion-authority")
        if authority_only_corridor:
            command.append("--authority-only-corridor")
        if diagnostic_continue_root_only_scale:
            command.append("--diagnostic-continue-root-only-scale")
        for spell_id in future_source_retain_spells:
            command.extend(
                ("--future-source-retain-spell", str(spell_id))
            )
        if future_source_retain_spells:
            command.extend(
                (
                    "--future-source-retain-max-per-spell",
                    str(future_source_retain_max_per_spell),
                )
            )
        return command
    if mode == "replay-differential":
        if replay_expected_sha256 is None:
            raise ValueError("replay differential requires an expected SHA-256")
        command = [
            windows_path(python),
            windows_path(
                ROOT
                / "scripts"
                / "tools"
                / "th08_windows_replay_semantic_smoke.py"
            ),
            "--game-dir",
            windows_path(game_dir),
            "--launch-bat",
            windows_path(launcher),
            "--report",
            windows_path(artifact_dir / "windows-replay-semantic.json"),
            "--fingerprint-output",
            windows_path(artifact_dir / "windows-replay-semantic.jsonl.gz"),
            "--replay-slot",
            str(replay_slot),
            "--expected-replay-sha256",
            replay_expected_sha256,
            "--expected-route-id",
            str(replay_route_id),
            "--expected-difficulty-index",
            str(replay_difficulty_index),
            "--expected-stage-index",
            str(replay_stage_index),
            "--start-manager-frame",
            str(replay_start_manager_frame),
            "--gameplay-epochs",
            str(replay_gameplay_epochs),
        ]
        if replay_collision_control_projection:
            command.append("--collision-control-projection")
        return command
    if future_source_retain_spells:
        raise ValueError(
            "future-source root retention is currently a Practice-only gate"
        )
    if mode != "full-route":
        raise ValueError(f"unsupported Wine controller mode: {mode}")
    command = [
        windows_path(python),
        windows_path(ROOT / "scripts" / "th08_full_route_supervisor.py"),
        "--armed",
        "--refuse-existing",
        "--game-dir",
        windows_path(game_dir),
        "--launch-bat",
        windows_path(launcher),
        "--runtime-ecl-static-image",
        windows_path(ROOT / "artifacts" / "decoded" / "ecldata7.ecl"),
        "--runtime-ecl-static-sha256",
        FINAL_B_ECL_SHA256,
        "--enable-finalb-scale-source-authority",
        "--difficulty",
        difficulty,
        "--agent-duration",
        str(agent_duration),
        "--trial-timeout",
        str(trial_timeout),
    ]
    if kill_before_saturation:
        command.append("--kill-before-saturation")
    if ordinary_preexhaustion_authority:
        command.append("--ordinary-preexhaustion-authority")
    if authority_only_corridor:
        command.append("--authority-only-corridor")
    if trace_items:
        command.append("--trace-items")
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("smoke", "practice", "full-route", "replay-differential"),
        default="smoke",
    )
    parser.add_argument(
        "--practice-stage",
        choices=PRACTICE_STAGE_KEYS,
        default="5",
        help="Sakuya/Remilia Practice Start stage",
    )
    parser.add_argument(
        "--difficulty",
        choices=("easy", "normal", "hard", "lunatic"),
        default="lunatic",
        help="Sakuya/Remilia main difficulty; defaults to lunatic",
    )
    parser.add_argument(
        "--game-dir",
        type=Path,
        default=REFERENCE / "th08-game-original" / "th08",
    )
    parser.add_argument(
        "--score-template",
        type=Path,
        default=REFERENCE / "th08-game-original" / "full-unlock-score.dat",
    )
    parser.add_argument(
        "--config-template",
        type=Path,
        default=REFERENCE / "th08-game-original" / "windowed-config.dat",
    )
    parser.add_argument(
        "--windows-python",
        type=Path,
        default=(
            REFERENCE
            / "tools"
            / "windows-python-3.11.9-embed-win32"
            / "python.exe"
        ),
    )
    parser.add_argument(
        "--wine-prefix",
        type=Path,
        default=REFERENCE / "wine-prefixes" / "th08-retail",
    )
    parser.add_argument("--display", default="auto")
    parser.add_argument(
        "--cpu-list",
        default="auto",
        help=(
            "taskset CPU expression, or 'auto' for the upper half of the "
            "host's effective affinity"
        ),
    )
    parser.add_argument(
        "--wine",
        type=Path,
        default=Path(shutil.which("wine") or "wine"),
    )
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--timeout", type=float)
    parser.add_argument(
        "--replay-input",
        type=Path,
        help="exact replay to provision for replay-differential mode",
    )
    parser.add_argument("--expected-replay-sha256")
    parser.add_argument("--replay-slot", type=int, default=1)
    parser.add_argument("--replay-route-id", type=int, default=2)
    parser.add_argument("--replay-difficulty-index", type=int, default=3)
    parser.add_argument("--replay-stage-index", type=int, default=5)
    parser.add_argument("--replay-start-manager-frame", type=int, default=600)
    parser.add_argument("--replay-gameplay-epochs", type=int, default=300)
    parser.add_argument(
        "--replay-collision-control-projection",
        action="store_true",
        help=(
            "capture decoded hostile, effect/ANM, and player-shot damage "
            "state for short replay-differential windows"
        ),
    )
    parser.add_argument(
        "--agent-duration",
        type=float,
        default=WINE_FULL_ROUTE_AGENT_DURATION_SECONDS,
    )
    parser.add_argument(
        "--trial-timeout",
        type=float,
        default=WINE_FULL_ROUTE_TRIAL_TIMEOUT_SECONDS,
    )
    parser.add_argument("--kill-before-saturation", action="store_true")
    parser.add_argument("--ordinary-preexhaustion-authority", action="store_true")
    parser.add_argument(
        "--future-source-retain-spell",
        action="append",
        type=int,
        default=[],
        metavar="ID",
        help=(
            "Practice-only shadow root spell selector; repeat for multiple "
            "cards"
        ),
    )
    parser.add_argument(
        "--future-source-retain-max-per-spell",
        type=int,
        default=1,
        metavar="N",
    )
    parser.add_argument(
        "--authority-only-corridor",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--trace-items", action="store_true")
    parser.add_argument(
        "--diagnostic-continue-root-only-scale",
        action="store_true",
        help=(
            "Practice-only unknown-direction constant-current-root scale "
            "proxy; diagnostic, never exact source authority"
        ),
    )
    return parser


def run(args: argparse.Namespace) -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (
        args.artifact_dir.resolve()
        if args.artifact_dir is not None
        else (ROOT / "artifacts" / "wine-th08" / f"{args.mode}-{timestamp}")
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)
    report_path = artifact_dir / "report.json"
    resolved_cpu_list: str | None = None
    report: dict[str, Any] = {
        "schema": "th08-isolated-wine-run-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "difficulty": args.difficulty,
        "practice_stage": args.practice_stage if args.mode == "practice" else None,
        "replay_input": (
            str(args.replay_input.resolve())
            if args.replay_input is not None
            else None
        ),
        "expected_replay_sha256": args.expected_replay_sha256,
        "replay_slot": args.replay_slot,
        "replay_route_id": args.replay_route_id,
        "replay_difficulty_index": args.replay_difficulty_index,
        "replay_stage_index": args.replay_stage_index,
        "replay_start_manager_frame": args.replay_start_manager_frame,
        "replay_gameplay_epochs": args.replay_gameplay_epochs,
        "replay_collision_control_projection": bool(
            args.replay_collision_control_projection
        ),
        "artifact_dir": str(artifact_dir),
        "display_requested": args.display,
        "cpu_list_requested": args.cpu_list,
        "cpu_list": None,
        "agent_duration_seconds": args.agent_duration,
        "trial_timeout_seconds": args.trial_timeout,
        "authority_only_corridor": args.authority_only_corridor,
        "trace_items": args.trace_items,
        "diagnostic_continue_root_only_scale": (
            args.diagnostic_continue_root_only_scale
        ),
        "future_source_retain_spells": list(
            args.future_source_retain_spell
        ),
        "future_source_retain_max_per_spell": (
            args.future_source_retain_max_per_spell
        ),
        "wine_prefix": str(args.wine_prefix.resolve()),
        "status": "failed",
        "controller_returncode": None,
        "error": None,
    }
    prefix = args.wine_prefix.resolve()
    game_dir = args.game_dir.resolve()
    score_template = args.score_template.resolve()
    config_template = args.config_template.resolve()
    windows_python = args.windows_python.resolve()
    native = NATIVE_LIBRARY.resolve()
    wine = args.wine.resolve()
    controller_process: subprocess.Popen[bytes] | None = None
    xvfb_process: subprocess.Popen[bytes] | None = None
    controller_log = (artifact_dir / "controller.log").open("wb")
    xvfb_log = (artifact_dir / "xvfb.log").open("wb")
    prefix_owned = False
    environment: dict[str, str] | None = None
    wineserver: Path | None = None
    provisioned_replay_path: Path | None = None
    provisioned_replay_owned = False
    result_code = 78
    try:
        validate_prefix_target(prefix)
        resolved_cpu_list = select_cpu_list(args.cpu_list)
        validate_cpu_list(resolved_cpu_list)
        report["cpu_list"] = resolved_cpu_list
        if args.timeout is not None and args.timeout <= 0.0:
            raise ValueError("timeout must be positive")
        if args.mode in {"practice", "full-route"} and args.agent_duration <= 0.0:
            raise ValueError("agent duration must be positive")
        if (
            args.mode in {"practice", "full-route"}
            and args.trial_timeout <= args.agent_duration
        ):
            raise ValueError("trial timeout must exceed agent duration")
        replay_input: Path | None = None
        replay_sha256: str | None = None
        if args.mode == "replay-differential":
            if args.replay_input is None:
                raise ValueError(
                    "replay-differential mode requires --replay-input"
                )
            if args.expected_replay_sha256 is None:
                raise ValueError(
                    "replay-differential mode requires "
                    "--expected-replay-sha256"
                )
            if not 1 <= args.replay_slot <= 15:
                raise ValueError("replay slot must be in 1..15")
            if args.replay_start_manager_frame <= 0:
                raise ValueError("replay start manager frame must be positive")
            if args.replay_gameplay_epochs <= 0:
                raise ValueError("replay gameplay epochs must be positive")
            replay_input = args.replay_input.resolve(strict=True)
            replay_sha256 = args.expected_replay_sha256.lower()
            if len(replay_sha256) != 64:
                raise ValueError(
                    "expected replay SHA-256 must contain 64 hex digits"
                )
            try:
                int(replay_sha256, 16)
            except ValueError as error:
                raise ValueError(
                    "expected replay SHA-256 must contain only hex digits"
                ) from error
            if sha256(replay_input) != replay_sha256:
                raise RuntimeError("replay input SHA-256 mismatch")
            replay_metadata, _decoded = decode_replay(replay_input)
            if replay_metadata.sha256 != replay_sha256:
                raise RuntimeError("replay decoder/file SHA-256 disagreement")
            if replay_metadata.route_id != args.replay_route_id:
                raise RuntimeError("replay input route does not match request")
            if (
                replay_metadata.difficulty_index
                != args.replay_difficulty_index
            ):
                raise RuntimeError(
                    "replay input difficulty does not match request"
                )
            matching_stages = tuple(
                stage
                for stage in replay_metadata.stages
                if stage.stage_index == args.replay_stage_index
            )
            if len(replay_metadata.stages) != 1 or len(matching_stages) != 1:
                raise RuntimeError(
                    "replay input must contain only the requested stage"
                )
            if matching_stages[0].frame_count <= 0:
                raise RuntimeError("replay input stage has no frames")
            if matching_stages[0].bomb_press_frames:
                raise RuntimeError("replay input contains Bomb presses")
            report["replay_input_contract"] = {
                "sha256": replay_sha256,
                "route_id": replay_metadata.route_id,
                "difficulty_index": replay_metadata.difficulty_index,
                "stage_index": matching_stages[0].stage_index,
                "stage_frame_count": matching_stages[0].frame_count,
                "stage_input_sha256": matching_stages[0].input_sha256,
                "stage_bomb_press_frames": list(
                    matching_stages[0].bomb_press_frames
                ),
            }
        if (
            args.diagnostic_continue_root_only_scale
            and args.mode != "practice"
        ):
            raise ValueError(
                "root-only scale continuation is a Practice-only diagnostic"
            )
        if (
            args.future_source_retain_spell
            and args.mode != "practice"
        ):
            raise ValueError(
                "future-source retention is a Practice-only diagnostic"
            )
        if args.future_source_retain_max_per_spell <= 0:
            raise ValueError(
                "future-source retention maximum per spell must be positive"
            )
        if len(set(args.future_source_retain_spell)) != len(
            args.future_source_retain_spell
        ):
            raise ValueError("future-source retained spell IDs must be unique")
        if any(
            not 0 <= spell_id <= 255
            for spell_id in args.future_source_retain_spell
        ):
            raise ValueError("future-source retained spell ID is out of range")
        if not repository_clean():
            raise RuntimeError("Wine evidence run requires a clean worktree")
        required = (
            *(game_dir / name for name in GAME_FILE_SHA256),
            score_template,
            config_template,
            windows_python,
            native,
            ROOT / "scripts" / "tools" / "run_th08_wine_launch.bat",
            ROOT / "scripts" / "tools" / "exec_with_pty.py",
            ROOT / "scripts" / "tools" / "th08_attach_no_life_decrement.py",
        )
        if args.mode == "full-route":
            required += (ROOT / "artifacts" / "decoded" / "ecldata7.ecl",)
        elif args.mode == "practice":
            practice_identity = PRACTICE_STAGE_ECL_IDENTITIES[
                args.practice_stage
            ]
            required += (
                ROOT
                / "artifacts"
                / "decoded"
                / practice_identity.filename,
            )
        elif args.mode == "replay-differential":
            assert replay_input is not None
            required += (
                replay_input,
                ROOT
                / "scripts"
                / "tools"
                / "th08_windows_replay_semantic_smoke.py",
            )
        for path in required:
            if not path.is_file():
                raise FileNotFoundError(f"required TH08 Wine input is absent: {path}")
        observed_game_hashes = {
            name: sha256(game_dir / name) for name in GAME_FILE_SHA256
        }
        if observed_game_hashes != GAME_FILE_SHA256:
            raise RuntimeError(
                f"exact TH08 game file SHA-256 mismatch: {observed_game_hashes}"
            )
        if sha256(score_template) != FULL_UNLOCK_SCORE_SHA256:
            raise RuntimeError("TH08 score template SHA-256 mismatch")
        if sha256(config_template) != EXPECTED_CONFIG_SHA256:
            raise RuntimeError("TH08 config template SHA-256 mismatch")
        if sha256(windows_python) != PYTHON_EXE_SHA256:
            raise RuntimeError("Win32 Python executable SHA-256 mismatch")
        if sha256(native) != NATIVE_LIBRARY_SHA256:
            raise RuntimeError("Win32 native planner SHA-256 mismatch")
        if pe_machine(native) != 0x014C:
            raise RuntimeError("native planner is not an i386 PE DLL")
        if args.mode == "full-route" and sha256(
            ROOT / "artifacts" / "decoded" / "ecldata7.ecl"
        ) != FINAL_B_ECL_SHA256:
            raise RuntimeError("Final-B ECL static image SHA-256 mismatch")
        if args.mode == "practice":
            practice_ecl = (
                ROOT
                / "artifacts"
                / "decoded"
                / practice_identity.filename
            )
            if sha256(practice_ecl) != practice_identity.sha256:
                raise RuntimeError(
                    "Practice ECL static image SHA-256 mismatch: "
                    f"{practice_identity.filename}"
                )
        report.update(
            {
                "repository_commit": repository_commit(),
                "repository_clean": True,
                "game_dir": str(game_dir),
                "game_file_sha256": observed_game_hashes,
                "score_template_sha256": sha256(score_template),
                "config_template_sha256": sha256(config_template),
                "windows_python": str(windows_python),
                "windows_python_sha256": sha256(windows_python),
                "native_library": str(native),
                "native_library_sha256": sha256(native),
                "native_pe_machine": pe_machine(native),
            }
        )
        existing = prefix_processes(prefix)
        if existing:
            raise RuntimeError(
                "Wine prefix already has live processes; refusing shared-prefix "
                f"cleanup: {existing}"
            )
        marker = prefix / PREFIX_MARKER
        prefix_initialized = not marker.is_file()
        if prefix.exists() and prefix_initialized:
            raise RuntimeError(
                "Wine prefix exists without the TH08 ownership marker"
            )
        prefix_owned = True
        display = select_display(args.display)
        report["display"] = display
        environment = os.environ.copy()
        environment.update(
            {
                "WINEPREFIX": str(prefix),
                "WINEARCH": "win32",
                "DISPLAY": display,
                "LANG": "ja_JP.UTF-8",
                "LC_ALL": "ja_JP.UTF-8",
                "WINEDEBUG": "-all",
                "WINEDLLOVERRIDES": "mscoree,mshtml=",
                "LP_NUM_THREADS": "1",
                "MESA_GLTHREAD": "false",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": ";".join(
                    (windows_path(ROOT), windows_path(ROOT / "scripts"))
                ),
                "TH08_GAME_DIR": windows_path(game_dir),
                "TH08_WINDOWS_PYTHON": windows_path(windows_python),
                "TH08_PATCHER": windows_path(
                    ROOT / "scripts" / "tools" / "th08_attach_no_life_decrement.py"
                ),
            }
        )
        version = subprocess.run(
            [str(wine), "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        report["wine_version"] = version
        wineboot = wine.parent / "wineboot"
        wineserver = wine.parent / "wineserver"
        for component in (wineboot, wineserver):
            if not component.is_file():
                raise FileNotFoundError(
                    f"Wine component is absent beside selected wine: {component}"
                )
        xvfb_process = subprocess.Popen(
            [
                "Xvfb",
                display,
                "-screen",
                "0",
                "1024x768x24",
                "-nolisten",
                "tcp",
            ],
            stdin=subprocess.DEVNULL,
            stdout=xvfb_log,
            stderr=subprocess.STDOUT,
        )
        time.sleep(0.5)
        if xvfb_process.poll() is not None:
            raise RuntimeError(
                f"Xvfb exited early with {xvfb_process.returncode}"
            )
        report["prefix_initialized"] = prefix_initialized
        if prefix_initialized:
            prefix.parent.mkdir(parents=True, exist_ok=True)
            with (artifact_dir / "wineboot.log").open("wb") as output:
                initialized = subprocess.run(
                    [str(wineboot), "-u"],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=180,
                )
            if initialized.returncode:
                raise RuntimeError(
                    "dedicated TH08 Wine prefix initialization failed: "
                    f"{initialized.returncode}"
                )
            subprocess.run(
                [str(wineserver), "-k"],
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            leftovers = wait_prefix_exit(prefix)
            if leftovers:
                raise RuntimeError(
                    "dedicated TH08 prefix did not become idle after wineboot: "
                    f"{leftovers}"
                )
            marker.write_text(
                json.dumps(
                    {"wine_version": version, "wine_arch": "win32"},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            marker_value = json.loads(marker.read_text(encoding="utf-8"))
            if marker_value.get("wine_arch") != "win32":
                raise RuntimeError("TH08 Wine prefix marker architecture drifted")
            if marker_value.get("wine_version") != version:
                raise RuntimeError("TH08 Wine prefix marker version drifted")
        shutil.copy2(score_template, game_dir / "score.dat")
        shutil.copy2(config_template, game_dir / "th08.cfg")
        report["score_sha256_at_launch"] = sha256(game_dir / "score.dat")
        report["config_sha256_at_launch"] = sha256(game_dir / "th08.cfg")
        if report["score_sha256_at_launch"] != FULL_UNLOCK_SCORE_SHA256:
            raise RuntimeError("TH08 score restoration failed")
        if report["config_sha256_at_launch"] != EXPECTED_CONFIG_SHA256:
            raise RuntimeError("TH08 config restoration failed")
        if args.mode == "replay-differential":
            assert replay_input is not None
            assert replay_sha256 is not None
            (
                provisioned_replay_path,
                provisioned_replay_owned,
            ) = provision_replay_slot(
                replay_input,
                game_dir,
                slot=args.replay_slot,
                expected_sha256=replay_sha256,
            )
            report["provisioned_replay"] = {
                "path": str(provisioned_replay_path),
                "sha256": replay_sha256,
                "owned": provisioned_replay_owned,
            }
        windows_command = build_windows_controller_command(
            mode=args.mode,
            python=windows_python,
            game_dir=game_dir,
            artifact_dir=artifact_dir,
            agent_duration=args.agent_duration,
            trial_timeout=args.trial_timeout,
            kill_before_saturation=args.kill_before_saturation,
            ordinary_preexhaustion_authority=(
                args.ordinary_preexhaustion_authority
            ),
            authority_only_corridor=args.authority_only_corridor,
            trace_items=args.trace_items,
            difficulty=args.difficulty,
            practice_stage=args.practice_stage,
            diagnostic_continue_root_only_scale=(
                args.diagnostic_continue_root_only_scale
            ),
            future_source_retain_spells=tuple(
                args.future_source_retain_spell
            ),
            future_source_retain_max_per_spell=(
                args.future_source_retain_max_per_spell
            ),
            replay_slot=args.replay_slot,
            replay_expected_sha256=replay_sha256,
            replay_route_id=args.replay_route_id,
            replay_difficulty_index=args.replay_difficulty_index,
            replay_stage_index=args.replay_stage_index,
            replay_start_manager_frame=args.replay_start_manager_frame,
            replay_gameplay_epochs=args.replay_gameplay_epochs,
            replay_collision_control_projection=(
                args.replay_collision_control_projection
            ),
        )
        wine_command = [
            str(wine),
            *windows_command,
        ]
        host_command = [
            "taskset",
            "-c",
            resolved_cpu_list,
            sys.executable,
            str(ROOT / "scripts" / "tools" / "exec_with_pty.py"),
            "--",
            *wine_command,
        ]
        report["windows_controller_command"] = windows_command
        report["wine_controller_command"] = wine_command
        report["host_controller_command"] = host_command
        controller_process = subprocess.Popen(
            host_command,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=controller_log,
            stderr=subprocess.STDOUT,
        )
        default_timeout = {
            "smoke": 180.0,
            "replay-differential": 600.0,
        }.get(args.mode, args.trial_timeout + 180.0)
        timeout = args.timeout or default_timeout
        report["timeout_seconds"] = timeout
        try:
            returncode = controller_process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                f"TH08 Wine {args.mode} exceeded {timeout:.1f} seconds"
            ) from error
        report["controller_returncode"] = returncode
        if returncode:
            raise RuntimeError(
                f"TH08 Windows controller exited with {returncode}"
            )
        if args.mode == "smoke":
            smoke = json.loads(
                (artifact_dir / "windows-smoke.json").read_text(encoding="utf-8")
            )
            report["windows_smoke"] = smoke
            if smoke.get("status") != "passed":
                raise RuntimeError("Windows-side TH08 smoke did not pass")
        elif args.mode == "replay-differential":
            replay_smoke = json.loads(
                (
                    artifact_dir / "windows-replay-semantic.json"
                ).read_text(encoding="utf-8")
            )
            report["windows_replay_semantic"] = replay_smoke
            if replay_smoke.get("status") != "passed":
                raise RuntimeError(
                    "Windows-side TH08 replay semantic capture did not pass"
                )
        report["status"] = "passed"
        result_code = 0
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if isinstance(error, KeyboardInterrupt):
            result_code = 130
    finally:
        stop_process(controller_process)
        cleanup_errors: list[str] = []
        if (
            prefix_owned
            and environment is not None
            and wineserver is not None
        ):
            try:
                stopped = subprocess.run(
                    [str(wineserver), "-k"],
                    env=environment,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30.0,
                )
                # Wine 8 returns 1 when the per-prefix server has already
                # exited. Record that advisory status, but make observed
                # exact-prefix processes the cleanup authority below.
                report["wineserver_k_returncode"] = stopped.returncode
            except BaseException as error:
                cleanup_errors.append(
                    f"{type(error).__name__} stopping wineserver: {error}"
                )
        stop_process(xvfb_process)
        if prefix_owned:
            wait_prefix_exit(prefix)
        if provisioned_replay_owned and provisioned_replay_path is not None:
            try:
                assert replay_sha256 is not None
                remove_provisioned_replay(
                    provisioned_replay_path,
                    expected_sha256=replay_sha256,
                )
                report["provisioned_replay_removed"] = True
            except BaseException as error:
                cleanup_errors.append(
                    f"{type(error).__name__} removing provisioned replay: "
                    f"{error}"
                )
                report["provisioned_replay_removed"] = False
        controller_log.close()
        xvfb_log.close()
        report["leftover_prefix_processes"] = (
            prefix_processes(prefix) if prefix_owned else []
        )
        if report["leftover_prefix_processes"]:
            cleanup_errors.append(
                "dedicated prefix still owns live processes after cleanup"
            )
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["status"] = "failed"
            if report.get("error") is None:
                report["error"] = "; ".join(cleanup_errors)
            if result_code == 0:
                result_code = 78
        report["score_sha256_after"] = (
            sha256(game_dir / "score.dat")
            if (game_dir / "score.dat").is_file()
            else None
        )
        report["config_sha256_after"] = (
            sha256(game_dir / "th08.cfg")
            if (game_dir / "th08.cfg").is_file()
            else None
        )
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return result_code


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
