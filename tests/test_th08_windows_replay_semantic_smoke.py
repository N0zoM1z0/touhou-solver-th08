from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from th08_automation.finalb_replay_observer import NativeReplayStageContract
from tools.th08_windows_replay_semantic_smoke import (
    advance_to_next_manager_frame_root,
    build_parser,
    validate_semantic_sample,
)


def _contract() -> NativeReplayStageContract:
    return NativeReplayStageContract(
        slot=1,
        compact_index=0,
        path=Path("th8_01.rpy"),
        sha256="a" * 64,
        route_id=2,
        difficulty_index=3,
        stage_route_index=5,
        stage_frame_count=33728,
        stage_input_sha256="b" * 64,
        stage_bomb_press_frames=(),
    )


def _fingerprint() -> dict[str, object]:
    return {
        "manager_frame": 600,
        "gameplay_active": True,
        "game_manager_flags": 0x0C,
        "difficulty_index": 3,
        "shot_type_index": 2,
        "stage_index": 5,
        "replay": {"frame_counter": 600},
    }


class _FakeBarrier:
    def __init__(self, manager_frames: list[int]) -> None:
        self.manager_frames = manager_frames
        self.timeouts: list[float] = []

    def natural_advance(self, *, timeout_seconds: float):
        self.timeouts.append(timeout_seconds)
        manager_frame = self.manager_frames.pop(0)
        return type("Root", (), {"root_manager_frame": manager_frame})()


class WindowsReplaySemanticSmokeTests(unittest.TestCase):
    def test_advance_executes_same_manager_restarts_before_next_frame(
        self,
    ) -> None:
        barrier = _FakeBarrier([7649, 7649, 7650])
        root, repeated = advance_to_next_manager_frame_root(
            barrier,  # type: ignore[arg-type]
            current_manager_frame=7649,
            timeout_seconds=5.0,
        )
        self.assertEqual(root.root_manager_frame, 7650)
        self.assertEqual(repeated, 2)
        self.assertEqual(len(barrier.timeouts), 3)

    def test_advance_rejects_manager_frame_regression_or_skip(self) -> None:
        for observed in (7648, 7651):
            with self.subTest(observed=observed):
                barrier = _FakeBarrier([observed])
                with self.assertRaisesRegex(
                    RuntimeError, "invalid manager frame"
                ):
                    advance_to_next_manager_frame_root(
                        barrier,  # type: ignore[arg-type]
                        current_manager_frame=7649,
                        timeout_seconds=5.0,
                    )

    def test_parser_requires_explicit_replay_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = build_parser().parse_args(
                [
                    "--game-dir",
                    str(root),
                    "--launch-bat",
                    str(root / "launch.bat"),
                    "--report",
                    str(root / "report.json"),
                    "--fingerprint-output",
                    str(root / "trace.jsonl.gz"),
                    "--replay-slot",
                    "1",
                    "--expected-replay-sha256",
                    "a" * 64,
                    "--expected-route-id",
                    "2",
                    "--expected-difficulty-index",
                    "3",
                    "--expected-stage-index",
                    "5",
                ]
            )
        self.assertEqual(args.start_manager_frame, 600)
        self.assertEqual(args.gameplay_epochs, 300)

    def test_sample_contract_accepts_exact_aligned_replay(self) -> None:
        validate_semantic_sample(
            _fingerprint(),
            contract=_contract(),
            expected_manager_frame=600,
        )

    def test_sample_contract_rejects_clock_or_identity_drift(self) -> None:
        fingerprint = _fingerprint()
        fingerprint["replay"] = {"frame_counter": 599}
        with self.assertRaisesRegex(RuntimeError, "clocks are not aligned"):
            validate_semantic_sample(
                fingerprint,
                contract=_contract(),
                expected_manager_frame=600,
            )
        with self.assertRaisesRegex(RuntimeError, "difficulty_index changed"):
            validate_semantic_sample(
                _fingerprint(),
                contract=replace(_contract(), difficulty_index=2),
                expected_manager_frame=600,
            )


if __name__ == "__main__":
    unittest.main()
