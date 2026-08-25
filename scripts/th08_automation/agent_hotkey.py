#!/usr/bin/env python3
"""Prewarmed F8/F9 handoff for manually selected TH08 route-2 trials."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from runtime_agent import InputTransition
from th08_automation.agent_contract import (
    build_long_run_arguments,
    one_shot_trial_finished,
    read_runtime_summary,
)
from th08_corridor_adapter import prewarm_th08_corridor
from th08_live_dodge_agent import build_parser as build_agent_parser
from th08_live_dodge_agent import run as run_agent
from th08_runtime_agent import (
    ADDR_NO_LIFE_DECREMENT_PATCH,
    TARGET_EXE,
    ProcessReader,
    Win32,
    _require_foreground,
    observe_state,
    release_injected_keys,
    send_transitions,
    verify_target,
)
from analysis.th08_trial_report import summarize_rows


HOTKEY_ARM = 1
HOTKEY_STOP = 2
HOTKEY_QUIT = 3
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
LONG_RUN_DURATION_SECONDS = 3600
DIFFICULTY_NAMES = {
    0: "easy",
    1: "normal",
    2: "hard",
    3: "lunatic",
    4: "extra",
}
ERROR_ALREADY_EXISTS = 183
INSTANCE_MUTEX_NAME = r"Local\Codex_TH08_Agent_Hotkey"


class AgentHotkey:
    def __init__(
        self,
        *,
        expected_difficulty: int | None = None,
        expected_stage: int | None = None,
        terminal_stage: int | None = None,
        trace_transform_runtime: bool = False,
        trace_items: bool = False,
        trace_enemy_mode_transitions: bool = False,
        trace_enemy_lifecycle_events: bool = False,
        kill_before_saturation: bool = False,
        ordinary_preexhaustion_authority: bool = False,
        future_source_retain_dir: Path | None = None,
        future_source_retain_spells: tuple[int, ...] = (),
        future_source_retain_max_per_spell: int = 1,
        authority_only_corridor: bool = False,
        diagnostic_continue_root_only_scale: bool = False,
        runtime_ecl_static_image: Path | None = None,
        runtime_ecl_static_sha256: str | None = None,
        enable_finalb_scale_source_authority: bool = False,
        safety_value_horizon: int = 0,
        viability_audit_dir: Path | None = None,
        input_clock_boundary_shadow: bool = False,
        input_clock_shadow_sample_ms: float = 1.0,
        local_pipeline_root_shadow_every: int = 0,
        local_hazard_backend: str = "native",
        local_beam_reducer: str = "native",
        bullet_decode_backend: str = "native",
        duration_seconds: float = LONG_RUN_DURATION_SECONDS,
        detailed_summary: bool = True,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("th08_agent_hotkey.py must run under Windows Python")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self.kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        self.instance_mutex = self.kernel32.CreateMutexW(
            None,
            False,
            INSTANCE_MUTEX_NAME,
        )
        if not self.instance_mutex:
            raise ctypes.WinError(ctypes.get_last_error(), "CreateMutexW")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self.kernel32.CloseHandle(self.instance_mutex)
            self.instance_mutex = None
            raise RuntimeError("another TH08 hotkey daemon is already running")
        self.api = Win32()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.agent_thread: threading.Thread | None = None
        self.agent_error: Exception | None = None
        self.last_summary: dict[str, object] | None = None
        self.stop_file: Path | None = None
        self.output: Path | None = None
        if (
            expected_difficulty is not None
            and expected_difficulty not in DIFFICULTY_NAMES
        ):
            raise ValueError(
                f"unsupported expected difficulty {expected_difficulty}"
            )
        if bullet_decode_backend not in {"python", "native"}:
            raise ValueError("unknown bullet decode backend")
        if (runtime_ecl_static_image is None) != (
            runtime_ecl_static_sha256 is None
        ):
            raise ValueError(
                "runtime ECL identity requires both a static image and "
                "SHA-256"
            )
        if runtime_ecl_static_image is not None and expected_stage is None:
            raise ValueError(
                "runtime ECL identity requires an explicit expected stage"
            )
        if enable_finalb_scale_source_authority and (
            expected_difficulty != 3 or expected_stage not in {0, 7}
        ):
            raise ValueError(
                "Final-B scale-source authority requires Lunatic full route "
                "or stage 7"
            )
        if enable_finalb_scale_source_authority and (
            runtime_ecl_static_image is None
            or runtime_ecl_static_sha256 is None
        ):
            raise ValueError(
                "Final-B scale-source authority requires exact runtime ECL "
                "identity"
            )
        self.expected_difficulty = expected_difficulty
        self.expected_stage = expected_stage
        self.terminal_stage = terminal_stage
        self.trace_transform_runtime = trace_transform_runtime
        self.trace_items = trace_items
        self.trace_enemy_mode_transitions = trace_enemy_mode_transitions
        self.trace_enemy_lifecycle_events = (
            trace_enemy_lifecycle_events
        )
        self.kill_before_saturation = kill_before_saturation
        self.ordinary_preexhaustion_authority = (
            ordinary_preexhaustion_authority
        )
        self.future_source_retain_dir = future_source_retain_dir
        self.future_source_retain_spells = future_source_retain_spells
        self.future_source_retain_max_per_spell = (
            future_source_retain_max_per_spell
        )
        self.authority_only_corridor = authority_only_corridor
        self.diagnostic_continue_root_only_scale = (
            diagnostic_continue_root_only_scale
        )
        self.runtime_ecl_static_image = runtime_ecl_static_image
        self.runtime_ecl_static_sha256 = runtime_ecl_static_sha256
        self.enable_finalb_scale_source_authority = (
            enable_finalb_scale_source_authority
        )
        self.safety_value_horizon = safety_value_horizon
        self.viability_audit_dir = viability_audit_dir
        self.input_clock_boundary_shadow = input_clock_boundary_shadow
        self.input_clock_shadow_sample_ms = input_clock_shadow_sample_ms
        self.local_pipeline_root_shadow_every = (
            local_pipeline_root_shadow_every
        )
        self.local_hazard_backend = local_hazard_backend
        self.local_beam_reducer = local_beam_reducer
        self.bullet_decode_backend = bullet_decode_backend
        self.duration_seconds = duration_seconds
        self.detailed_summary = detailed_summary
        self.artifact_dir = (
            Path(__file__).resolve().parents[2]
            / "artifacts"
            / "runtime_reports"
        )
        prewarm_th08_corridor()

    def _open_target(self) -> tuple[int, ProcessReader, dict[str, object]]:
        pid = self.api.find_pid(TARGET_EXE)
        reader = ProcessReader(self.api, pid)
        try:
            identity = verify_target(reader)
            if reader.u8(ADDR_NO_LIFE_DECREMENT_PATCH) != 0:
                raise RuntimeError("the no-life-decrement runtime patch is absent")
            return pid, reader, identity
        except Exception:
            reader.close()
            raise

    def _wait_ready(self, timeout: float = 10.0) -> None:
        assert self.output is not None
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self.agent_thread is None or not self.agent_thread.is_alive():
                raise RuntimeError("agent exited before wait_ready")
            if self.output.is_file():
                text = self.output.read_text(encoding="utf-8")
                if '"kind": "wait_ready"' in text:
                    return
            time.sleep(0.01)
        raise RuntimeError("timed out waiting for prewarmed agent")

    def _agent_worker(self, arguments: list[str]) -> None:
        assert self.output is not None
        try:
            result = run_agent(build_agent_parser().parse_args(arguments))
            if result:
                raise RuntimeError(f"agent returned {result}")
            if self.detailed_summary:
                rows = [
                    json.loads(line)
                    for line in self.output.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line.strip()
                ]
                report = summarize_rows(rows)
            else:
                report = read_runtime_summary(self.output)
            self.last_summary = report
            summary = self.output.with_suffix(".summary.json")
            summary.write_text(
                json.dumps(
                    report,
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            print(
                "trial complete:",
                f"reason={report['termination_reason']}",
                f"hits={report.get('hit_count', report.get('hit_frames'))}",
                f"frames={report['first_frame']}..{report['last_frame']}",
                f"summary={summary}",
                flush=True,
            )
        except Exception as exc:
            self.agent_error = exc
            print(f"agent error: {exc}", file=sys.stderr, flush=True)

    def arm(self, *, output_path: Path | None = None) -> None:
        if self.agent_thread is not None and self.agent_thread.is_alive():
            print("agent is already active", flush=True)
            return
        self.agent_error = None
        self.last_summary = None
        pid, reader, _identity = self._open_target()
        try:
            _require_foreground(self.api, pid)
            state = observe_state(reader)
            gameplay_active = bool(state["gameplay_active"])
            if gameplay_active:
                difficulty = int(state["difficulty_index"])
                if difficulty not in DIFFICULTY_NAMES:
                    raise RuntimeError(
                        f"active gameplay difficulty is unsupported: {difficulty}"
                    )
                if (
                    self.expected_difficulty is not None
                    and difficulty != self.expected_difficulty
                ):
                    raise RuntimeError(
                        "active gameplay difficulty mismatch: "
                        f"expected {self.expected_difficulty}, got {difficulty}"
                    )
                if int(state["route_id"]) != 2:
                    raise RuntimeError(
                        f"active gameplay route is not Sakuya/Remilia: "
                        f"{state['route_id']}"
                    )
            else:
                difficulty = (
                    3
                    if self.expected_difficulty is None
                    else self.expected_difficulty
                )

            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mode = DIFFICULTY_NAMES[difficulty]
            self.output = output_path or self.artifact_dir / (
                f"{mode}_route2_hotkey_longrun_{stamp}.jsonl"
            )
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.stop_file = self.output.with_suffix(".stop")
            self.output.unlink(missing_ok=True)
            self.stop_file.unlink(missing_ok=True)
            arguments = build_long_run_arguments(
                output=self.output,
                stop_file=self.stop_file,
                pid=pid,
                difficulty=difficulty,
                expected_stage=self.expected_stage,
                terminal_stage=self.terminal_stage,
                trace_transform_runtime=self.trace_transform_runtime,
                trace_items=self.trace_items,
                trace_enemy_mode_transitions=(
                    self.trace_enemy_mode_transitions
                ),
                trace_enemy_lifecycle_events=(
                    self.trace_enemy_lifecycle_events
                ),
                kill_before_saturation=self.kill_before_saturation,
                ordinary_preexhaustion_authority=(
                    self.ordinary_preexhaustion_authority
                ),
                future_source_retain_dir=(
                    self.future_source_retain_dir
                ),
                future_source_retain_spells=(
                    self.future_source_retain_spells
                ),
                future_source_retain_max_per_spell=(
                    self.future_source_retain_max_per_spell
                ),
                authority_only_corridor=self.authority_only_corridor,
                diagnostic_continue_root_only_scale=(
                    self.diagnostic_continue_root_only_scale
                ),
                runtime_ecl_static_image=(
                    self.runtime_ecl_static_image
                ),
                runtime_ecl_static_sha256=(
                    self.runtime_ecl_static_sha256
                ),
                enable_finalb_scale_source_authority=(
                    self.enable_finalb_scale_source_authority
                ),
                safety_value_horizon=self.safety_value_horizon,
                viability_audit_dir=self.viability_audit_dir,
                input_clock_boundary_shadow=(
                    self.input_clock_boundary_shadow
                ),
                input_clock_shadow_sample_ms=(
                    self.input_clock_shadow_sample_ms
                ),
                local_pipeline_root_shadow_every=(
                    self.local_pipeline_root_shadow_every
                ),
                local_hazard_backend=self.local_hazard_backend,
                local_beam_reducer=self.local_beam_reducer,
                bullet_decode_backend=self.bullet_decode_backend,
                duration_seconds=self.duration_seconds,
            )
            if not gameplay_active:
                arguments.extend(("--wait-gameplay", "--wait-timeout", "30"))
            self.agent_thread = threading.Thread(
                target=self._agent_worker,
                args=(arguments,),
                name="th08-live-agent",
                daemon=False,
            )
            self.agent_thread.start()
            if not gameplay_active:
                self._wait_ready()
                _require_foreground(self.api, pid)
                send_transitions(
                    self.api,
                    (InputTransition(0x01, True),),
                )
                try:
                    time.sleep(0.06)
                finally:
                    send_transitions(
                        self.api,
                        (InputTransition(0x01, False),),
                    )
            print(
                f"agent armed: pid={pid} difficulty={difficulty} "
                f"gameplay={gameplay_active} output={self.output}",
                flush=True,
            )
        finally:
            reader.close()

    def wait_for_trial(self, timeout: float | None = None) -> Path:
        if self.agent_thread is None:
            raise RuntimeError("agent has not been armed")
        self.agent_thread.join(timeout=timeout)
        if self.agent_thread.is_alive():
            raise TimeoutError("agent trial did not finish before timeout")
        if self.agent_error is not None:
            raise RuntimeError(f"agent trial failed: {self.agent_error}")
        if self.output is None:
            raise RuntimeError("agent trial completed without an output path")
        return self.output

    def stop(self) -> None:
        if self.agent_thread is None or not self.agent_thread.is_alive():
            print("agent is not active", flush=True)
            return
        assert self.stop_file is not None
        self.stop_file.write_text("stop\n", encoding="ascii")
        print("safe stop requested", flush=True)

    def close(self) -> None:
        try:
            release_injected_keys(self.api)
        except OSError:
            pass
        if self.instance_mutex is not None:
            self.kernel32.CloseHandle(self.instance_mutex)
            self.instance_mutex = None

    def run(self) -> int:
        print(
            "TH08 agent prewarmed (async-key polling). "
            "F8 arm/enter long run, F9 stop+pause, F10 quit.",
            flush=True,
        )
        try:
            keys = {
                VK_F8: self.arm,
                VK_F9: self.stop,
            }
            previous = {virtual_key: False for virtual_key in keys}
            previous[VK_F10] = False
            while True:
                if one_shot_trial_finished(
                    agent_started=self.agent_thread is not None,
                    agent_alive=(
                        self.agent_thread is not None
                        and self.agent_thread.is_alive()
                    ),
                ):
                    print(
                        "trial worker finished; one-shot daemon exiting",
                        flush=True,
                    )
                    break
                quit_pressed = bool(
                    self.user32.GetAsyncKeyState(VK_F10) & 0x8000
                )
                if quit_pressed and not previous[VK_F10]:
                    self.stop()
                    break
                previous[VK_F10] = quit_pressed
                for virtual_key, callback in keys.items():
                    pressed = bool(
                        self.user32.GetAsyncKeyState(virtual_key) & 0x8000
                    )
                    if pressed and not previous[virtual_key]:
                        try:
                            callback()
                        except Exception as exc:
                            print(
                                f"hotkey error: {exc}",
                                file=sys.stderr,
                                flush=True,
                            )
                    previous[virtual_key] = pressed
                time.sleep(0.01)
            if self.agent_thread is not None and self.agent_thread.is_alive():
                self.agent_thread.join(timeout=10.0)
            return 0
        finally:
            self.close()


def main() -> int:
    """Run the Windows hotkey daemon with its historical file logging."""

    try:
        agent = AgentHotkey()
    except Exception as exc:
        with open(
            r"\\wsl.localhost\ubuntu\tmp\th08_agent_hotkey.err",
            "a",
            encoding="utf-8",
        ) as error_output:
            print(f"startup error: {exc}", file=error_output)
        return 1
    sys.stdout = open(
        r"\\wsl.localhost\ubuntu\tmp\th08_agent_hotkey.out",
        "w",
        encoding="utf-8",
        buffering=1,
    )
    sys.stderr = open(
        r"\\wsl.localhost\ubuntu\tmp\th08_agent_hotkey.err",
        "w",
        encoding="utf-8",
        buffering=1,
    )
    try:
        return agent.run()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
