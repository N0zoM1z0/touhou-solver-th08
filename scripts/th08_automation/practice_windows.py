"""Windows process, foreground, launch, and menu-input ownership."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from runtime_agent import InputTransition
from th08_automation.practice_menu import MenuTap
from th08_runtime_agent import (
    ADDR_NO_LIFE_DECREMENT_PATCH,
    TARGET_EXE,
    TAP_NAMES,
    ProcessReader,
    Win32,
    _require_foreground,
    release_injected_keys,
    send_scan_key,
    send_transitions,
    verify_target,
)

VK_CAPITAL = 0x14
SW_RESTORE = 9
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
CREATE_NO_WINDOW = 0x08000000

WNDENUMPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPARAM,
)


def same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(
        str(right.resolve())
    )


def configure_supervisor_api(api: Win32) -> None:
    api.user32.GetKeyState.argtypes = [ctypes.c_int]
    api.user32.GetKeyState.restype = ctypes.c_short
    api.user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    api.user32.EnumWindows.restype = wintypes.BOOL
    api.user32.IsWindowVisible.argtypes = [wintypes.HWND]
    api.user32.IsWindowVisible.restype = wintypes.BOOL
    api.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    api.user32.ShowWindow.restype = wintypes.BOOL
    api.user32.BringWindowToTop.argtypes = [wintypes.HWND]
    api.user32.BringWindowToTop.restype = wintypes.BOOL
    api.kernel32.TerminateProcess.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    api.kernel32.TerminateProcess.restype = wintypes.BOOL
    api.kernel32.WaitForSingleObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    api.kernel32.WaitForSingleObject.restype = wintypes.DWORD


def caps_lock_enabled(api: Win32) -> bool:
    return bool(api.user32.GetKeyState(VK_CAPITAL) & 1)


def ensure_caps_lock_enabled(api: Win32) -> bool:
    """Enable and verify Caps Lock without depending on the active IME."""

    if caps_lock_enabled(api):
        return False
    send_scan_key(api, scan_code=0x3A, pressed=True)
    send_scan_key(api, scan_code=0x3A, pressed=False)
    time.sleep(0.08)
    if not caps_lock_enabled(api):
        raise RuntimeError("Caps Lock did not become enabled")
    return True


def matching_targets(
    api: Win32,
    expected_exe: Path,
) -> list[tuple[int, dict[str, object]]]:
    matches: list[tuple[int, dict[str, object]]] = []
    for pid in api.find_pids(TARGET_EXE):
        reader = ProcessReader(api, pid)
        try:
            identity = verify_target(reader)
            if same_path(Path(str(identity["image_path"])), expected_exe):
                matches.append((pid, identity))
        finally:
            reader.close()
    return matches


def terminate_exact_target(api: Win32, expected_exe: Path) -> bool:
    matches = matching_targets(api, expected_exe)
    if not matches:
        return False
    if len(matches) != 1:
        raise RuntimeError(
            "refusing to terminate ambiguous exact TH08 targets: "
            + ", ".join(str(pid) for pid, _identity in matches)
        )
    pid, _identity = matches[0]
    release_injected_keys(api)
    handle = api.kernel32.OpenProcess(
        PROCESS_TERMINATE | SYNCHRONIZE,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error(), "OpenProcess terminate")
    try:
        if not api.kernel32.TerminateProcess(handle, 0):
            raise ctypes.WinError(
                ctypes.get_last_error(),
                "TerminateProcess",
            )
        wait_result = api.kernel32.WaitForSingleObject(handle, 10_000)
        if wait_result != WAIT_OBJECT_0:
            raise RuntimeError(f"TH08 process {pid} did not terminate")
    finally:
        api.kernel32.CloseHandle(handle)
    return True


def build_patch_batch_command(launch_bat: Path) -> tuple[str, ...]:
    """Keep CALL and its path as separate argv items for cmd.exe quoting."""

    return (
        os.environ.get("COMSPEC", "cmd.exe"),
        "/d",
        "/c",
        "call",
        str(launch_bat),
    )


def launch_patch_batch(
    *,
    game_dir: Path,
    launch_bat: Path,
    log_path: Path,
) -> tuple[subprocess.Popen[bytes], object]:
    if not launch_bat.is_file():
        raise FileNotFoundError(f"launch batch does not exist: {launch_bat}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("wb")
    try:
        process = subprocess.Popen(
            build_patch_batch_command(launch_bat),
            cwd=game_dir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        log_file.close()
        raise
    return process, log_file


def wait_for_patched_target(
    api: Win32,
    *,
    expected_exe: Path,
    timeout_seconds: float,
) -> tuple[int, dict[str, object]]:
    deadline = time.perf_counter() + timeout_seconds
    reader: ProcessReader | None = None
    identity: dict[str, object] | None = None
    try:
        while time.perf_counter() < deadline and reader is None:
            matches = matching_targets(api, expected_exe)
            if len(matches) > 1:
                raise RuntimeError(
                    "multiple exact TH08 targets appeared after launch"
                )
            if matches:
                pid, identity = matches[0]
                reader = ProcessReader(api, pid)
                break
            time.sleep(0.1)
        if reader is None or identity is None:
            raise TimeoutError(
                "timed out waiting for the exact TH08 executable"
            )
        while time.perf_counter() < deadline:
            if reader.u8(ADDR_NO_LIFE_DECREMENT_PATCH) == 0:
                return reader.pid, verify_target(reader)
            time.sleep(0.05)
        raise TimeoutError(
            "timed out waiting for the no-life-decrement patch"
        )
    finally:
        if reader is not None:
            reader.close()


def wait_for_retail_target(
    api: Win32,
    *,
    expected_exe: Path,
    timeout_seconds: float,
) -> tuple[int, dict[str, object]]:
    """Wait for exact TH08 while requiring the original AddLives(-1) byte."""

    deadline = time.perf_counter() + timeout_seconds
    reader: ProcessReader | None = None
    identity: dict[str, object] | None = None
    try:
        while time.perf_counter() < deadline and reader is None:
            matches = matching_targets(api, expected_exe)
            if len(matches) > 1:
                raise RuntimeError(
                    "multiple exact TH08 targets appeared after launch"
                )
            if matches:
                pid, identity = matches[0]
                reader = ProcessReader(api, pid)
                break
            time.sleep(0.1)
        if reader is None or identity is None:
            raise TimeoutError(
                "timed out waiting for the exact TH08 executable"
            )
        while time.perf_counter() < deadline:
            if reader.u8(ADDR_NO_LIFE_DECREMENT_PATCH) == 0xFF:
                return reader.pid, verify_target(reader)
            time.sleep(0.05)
        raise TimeoutError(
            "timed out waiting for original retail life-decrement byte"
        )
    finally:
        if reader is not None:
            reader.close()


def target_windows(api: Win32, pid: int) -> tuple[int, ...]:
    windows: list[int] = []

    @WNDENUMPROC
    def callback(window: int, _parameter: int) -> bool:
        owner = wintypes.DWORD()
        api.user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and api.user32.IsWindowVisible(window):
            windows.append(int(window))
        return True

    if not api.user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error(), "EnumWindows")
    return tuple(windows)


def focus_target_window(
    api: Win32,
    pid: int,
    *,
    timeout_seconds: float,
) -> int:
    deadline = time.perf_counter() + timeout_seconds
    last_windows: tuple[int, ...] = ()
    while time.perf_counter() < deadline:
        last_windows = target_windows(api, pid)
        for window in last_windows:
            api.user32.ShowWindow(window, SW_RESTORE)
            api.user32.BringWindowToTop(window)
            api.user32.SetForegroundWindow(window)
            if api.foreground_pid() == pid:
                return window
        time.sleep(0.1)
    raise RuntimeError(
        f"could not acquire TH08 foreground ownership; windows={last_windows}"
    )


def drive_menu_plan(
    api: Win32,
    pid: int,
    plan: tuple[MenuTap, ...],
    *,
    hold_ms: int,
) -> None:
    if hold_ms <= 0:
        raise ValueError("menu hold time must be positive")
    _require_foreground(api, pid)
    release_injected_keys(api)
    for tap in plan:
        _require_foreground(api, pid)
        bit = TAP_NAMES[tap.key]
        send_transitions(api, (InputTransition(bit, True),))
        time.sleep(hold_ms / 1000.0)
        send_transitions(api, (InputTransition(bit, False),))
        time.sleep(tap.wait_after_ms / 1000.0)
