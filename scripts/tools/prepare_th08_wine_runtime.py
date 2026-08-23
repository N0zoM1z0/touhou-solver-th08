#!/usr/bin/env python3
"""Prepare ignored, attested TH08 game and Win32 Python Wine inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "reference"
PYTHON_ARCHIVE_SHA256 = (
    "daf24de7fb3b173e94e56a201d3f38dfedebbdc7ed1925f7aeb8ed588e2b4189"
)
PYTHON_EXE_SHA256 = (
    "e60592888c3128132df3489a2462716bb268063bfe3564bfe1f2f3dbe9ceafd1"
)
NUMPY_WHEEL_SHA256 = (
    "1af303d6b2210eb850fcf03064d364652b7120803a0b872f5211f5234b399f20"
)
GAME_FILE_SHA256 = {
    "th08.exe": "330fbdbf58a710829d65277b4f312cfbb38d5448b3df523e79350b879213d924",
    "th08.dat": "9d7edf43b8ddd347cbb641836f6b5050745dd936f688daebbf9382ca557043bb",
    "thbgm.dat": "2c2ef05f9ff6f43f752dae5da519a2477372c3f8875b7b44996a8f69fdad4d89",
}
FULL_UNLOCK_SCORE_SHA256 = (
    "9486920663319c9a438c508d3e3a8f8010cdb6f8e5bc1d658811f09071e356f1"
)
RUNTIME_MARKER = ".th08-win32-python-runtime-v1.json"
GAME_MARKER = ".th08-exact-game-runtime-v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configured_python_pth() -> str:
    """Return paths relative to ``reference/tools/<runtime>``."""

    return "\n".join(
        (
            "python311.zip",
            ".",
            r"Lib\site-packages",
            r"..\..\..",
            r"..\..\..\scripts",
            "import site",
            "",
        )
    )


def render_windowed_config() -> bytes:
    """Build the target's 60-byte GameConfiguration with display-only edits."""

    payload = bytearray(60)
    struct.pack_into(
        "<9h",
        payload,
        0,
        0,
        1,
        2,
        4,
        -1,
        -1,
        -1,
        -1,
        3,
    )
    struct.pack_into("<Ihh", payload, 20, 0x00080001, 600, 600)
    payload[28:41] = bytes(
        (
            2,  # lives
            3,  # bombs; the controller never emits the Bomb input bit
            0,  # 32-bit color
            0,  # music off for a headless VPS
            0,  # sound effects off for a headless VPS
            3,  # default Lunatic cursor
            1,  # windowed
            0,  # no frameskip
            2,  # maximum effect quality; preserve gameplay RNG consumers
            0,  # slowdown disabled
            0,  # shot+focus remapping disabled
            0,  # music volume
            0,  # sound volume
        )
    )
    struct.pack_into("<I", payload, 56, 0x00000001)
    return bytes(payload)


def _read_marker(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"runtime marker is not an object: {path}")
    return value


def _atomic_directory(destination: Path, populate) -> None:
    if destination.exists():
        raise FileExistsError(
            f"refusing to replace unrecognized runtime directory: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        populate(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def prepare_python_runtime(
    *,
    archive: Path,
    numpy_wheel: Path,
    destination: Path,
) -> dict[str, object]:
    inputs = {
        "python_archive_sha256": sha256(archive),
        "numpy_wheel_sha256": sha256(numpy_wheel),
    }
    if inputs["python_archive_sha256"] != PYTHON_ARCHIVE_SHA256:
        raise ValueError("Windows Python archive SHA-256 mismatch")
    if inputs["numpy_wheel_sha256"] != NUMPY_WHEEL_SHA256:
        raise ValueError("Win32 NumPy wheel SHA-256 mismatch")
    existing = _read_marker(destination / RUNTIME_MARKER)
    if existing is not None:
        if existing != inputs:
            raise RuntimeError("existing Win32 Python runtime marker drifted")
        if sha256(destination / "python.exe") != PYTHON_EXE_SHA256:
            raise RuntimeError("existing Win32 Python executable drifted")
        pth = destination / "python311._pth"
        if not pth.is_file() or pth.read_text(
            encoding="utf-8"
        ) != configured_python_pth():
            raise RuntimeError("existing Win32 Python search path drifted")
        if not (
            destination / "Lib" / "site-packages" / "numpy" / "__init__.py"
        ).is_file():
            raise RuntimeError("existing Win32 NumPy installation is absent")
        return existing

    def populate(temporary: Path) -> None:
        with zipfile.ZipFile(archive) as source:
            source.extractall(temporary)
        if sha256(temporary / "python.exe") != PYTHON_EXE_SHA256:
            raise RuntimeError("extracted Win32 Python executable drifted")
        site_packages = temporary / "Lib" / "site-packages"
        site_packages.mkdir(parents=True)
        with zipfile.ZipFile(numpy_wheel) as source:
            source.extractall(site_packages)
        (temporary / "python311._pth").write_text(
            configured_python_pth(),
            encoding="utf-8",
            newline="\n",
        )
        (temporary / RUNTIME_MARKER).write_text(
            json.dumps(inputs, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    _atomic_directory(destination, populate)
    return inputs


def prepare_game_runtime(*, source: Path, destination: Path) -> dict[str, object]:
    observed = {
        name: sha256(source / name) for name in GAME_FILE_SHA256
    }
    if observed != GAME_FILE_SHA256:
        raise ValueError(f"exact TH08 game files drifted: {observed}")
    score_source = source / "全开档" / "score.dat"
    score_sha256 = sha256(score_source)
    if score_sha256 != FULL_UNLOCK_SCORE_SHA256:
        raise ValueError("full-unlock TH08 score SHA-256 mismatch")
    marker = {
        "game_file_sha256": observed,
        "score_template_sha256": score_sha256,
        "config_sha256": hashlib.sha256(render_windowed_config()).hexdigest(),
    }
    existing = _read_marker(destination.parent / GAME_MARKER)
    if existing is not None:
        if existing != marker:
            raise RuntimeError("existing TH08 game runtime marker drifted")
        for name, expected in GAME_FILE_SHA256.items():
            if sha256(destination / name) != expected:
                raise RuntimeError(f"existing TH08 runtime file drifted: {name}")
        template_score = destination.parent / "full-unlock-score.dat"
        if (
            not template_score.is_file()
            or sha256(template_score) != FULL_UNLOCK_SCORE_SHA256
        ):
            raise RuntimeError("existing TH08 score template drifted")
        template_config = destination.parent / "windowed-config.dat"
        if (
            not template_config.is_file()
            or template_config.read_bytes() != render_windowed_config()
        ):
            raise RuntimeError("existing TH08 config template drifted")
        return existing

    def populate(temporary_root: Path) -> None:
        game = temporary_root / "th08"
        game.mkdir()
        for name in GAME_FILE_SHA256:
            shutil.copy2(source / name, game / name)
        for name in ("custom.exe", "replayview.exe"):
            candidate = source / name
            if candidate.is_file():
                shutil.copy2(candidate, game / name)
        shutil.copy2(score_source, temporary_root / "full-unlock-score.dat")
        shutil.copy2(score_source, game / "score.dat")
        config = render_windowed_config()
        (temporary_root / "windowed-config.dat").write_bytes(config)
        (game / "th08.cfg").write_bytes(config)
        (temporary_root / GAME_MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    _atomic_directory(destination.parent, populate)
    return marker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-source", type=Path, required=True)
    parser.add_argument(
        "--game-runtime",
        type=Path,
        default=REFERENCE / "th08-game-original" / "th08",
    )
    parser.add_argument(
        "--python-archive",
        type=Path,
        default=REFERENCE / "tools" / "python-3.11.9-embed-win32.zip",
    )
    parser.add_argument(
        "--numpy-wheel",
        type=Path,
        default=(
            REFERENCE / "tools" / "numpy-1.26.4-cp311-cp311-win32.whl"
        ),
    )
    parser.add_argument(
        "--python-runtime",
        type=Path,
        default=REFERENCE / "tools" / "windows-python-3.11.9-embed-win32",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    python_record = prepare_python_runtime(
        archive=args.python_archive.resolve(),
        numpy_wheel=args.numpy_wheel.resolve(),
        destination=args.python_runtime.resolve(),
    )
    game_record = prepare_game_runtime(
        source=args.game_source.resolve(),
        destination=args.game_runtime.resolve(),
    )
    print(
        json.dumps(
            {
                "python_runtime": str(args.python_runtime.resolve()),
                "python": python_record,
                "game_runtime": str(args.game_runtime.resolve()),
                "game": game_record,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
