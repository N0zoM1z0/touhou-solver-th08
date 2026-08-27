from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from th08_automation.finalb_replay_observer import NativeReplayStageContract
from tools.th08_windows_replay_semantic_smoke import (
    build_parser,
    validate_semantic_sample,
    validate_replay_frame_advance,
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
        stage_stored_input_word_count=33728,
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


class WindowsReplaySemanticSmokeTests(unittest.TestCase):
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
        self.assertEqual(args.root_timeout, 300.0)
        self.assertFalse(args.retail_life_decrement)

    def test_parser_can_require_original_life_decrement(self) -> None:
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
                    "0",
                    "--expected-stage-index",
                    "0",
                    "--retail-life-decrement",
                ]
            )
        self.assertTrue(args.retail_life_decrement)

    def test_sample_contract_accepts_exact_aligned_replay(self) -> None:
        validate_semantic_sample(
            _fingerprint(),
            contract=_contract(),
            expected_replay_frame=600,
        )

    def test_sample_contract_accepts_replay_bound_inactive_epoch(self) -> None:
        fingerprint = _fingerprint()
        fingerprint["gameplay_active"] = False
        validate_semantic_sample(
            fingerprint,
            contract=_contract(),
            expected_replay_frame=600,
        )

    def test_sparse_barrier_sample_accepts_only_forward_replay_jumps(self) -> None:
        self.assertEqual(
            validate_replay_frame_advance(previous=10649, observed=10652),
            3,
        )
        for observed in (10649, 10648):
            with self.assertRaisesRegex(RuntimeError, "did not advance"):
                validate_replay_frame_advance(
                    previous=10649,
                    observed=observed,
                )

    def test_sample_contract_rejects_clock_or_identity_drift(self) -> None:
        fingerprint = _fingerprint()
        fingerprint["replay"] = {"frame_counter": 599}
        with self.assertRaisesRegex(RuntimeError, "logical input clock"):
            validate_semantic_sample(
                fingerprint,
                contract=_contract(),
                expected_replay_frame=600,
            )
        with self.assertRaisesRegex(
            RuntimeError, "difficulty_index expected=2 observed=3"
        ):
            validate_semantic_sample(
                _fingerprint(),
                contract=replace(_contract(), difficulty_index=2),
                expected_replay_frame=600,
            )


if __name__ == "__main__":
    unittest.main()
