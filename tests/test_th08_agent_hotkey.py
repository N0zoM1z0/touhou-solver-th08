#!/usr/bin/env python3
"""Focused tests for the active manual-to-agent launch contract."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from th08_agent_hotkey import (
    LONG_RUN_DURATION_SECONDS,
    build_long_run_arguments,
    one_shot_trial_finished,
    read_runtime_summary,
)
from th08_live.controller import _prepare_live_run
from th08_live_dodge_agent import build_parser


def _arguments(**changes: object) -> list[str]:
    values: dict[str, object] = {
        "output": Path("trial.jsonl"),
        "stop_file": Path("trial.stop"),
        "pid": 1234,
        "difficulty": 3,
    }
    values.update(changes)
    return build_long_run_arguments(**values)


class AgentHotkeyTests(unittest.TestCase):
    def test_long_run_contract_is_no_bomb_and_not_first_hit_bounded(self) -> None:
        parsed = build_parser().parse_args(
            _arguments(expected_stage=2, terminal_stage=2)
        )
        self.assertEqual(parsed.duration, LONG_RUN_DURATION_SECONDS)
        self.assertEqual(parsed.stop_after_hits, 0)
        self.assertEqual(parsed.post_hit_frames, 0)
        self.assertTrue(parsed.no_bomb)
        self.assertTrue(parsed.armed)
        self.assertEqual(parsed.expected_stage, 2)
        self.assertEqual(parsed.terminal_stage, 2)
        self.assertFalse(parsed.trace_enemy_lifecycle_events)
        self.assertFalse(parsed.trace_items)
        self.assertFalse(parsed.kill_before_saturation)
        self.assertFalse(parsed.ordinary_preexhaustion_authority)
        self.assertFalse(parsed.authority_only_corridor)
        self.assertFalse(parsed.enable_finalb_scale_source_authority)

    def test_active_diagnostics_are_explicit(self) -> None:
        parsed = build_parser().parse_args(
            _arguments(
                trace_transform_runtime=True,
                trace_enemy_mode_transitions=True,
                trace_enemy_lifecycle_events=True,
                trace_items=True,
                kill_before_saturation=True,
                ordinary_preexhaustion_authority=True,
                authority_only_corridor=True,
                diagnostic_continue_root_only_scale=True,
            )
        )
        self.assertTrue(parsed.trace_transform_runtime)
        self.assertTrue(parsed.trace_enemy_mode_transitions)
        self.assertTrue(parsed.trace_enemy_lifecycle_events)
        self.assertTrue(parsed.trace_items)
        self.assertTrue(parsed.kill_before_saturation)
        self.assertTrue(parsed.ordinary_preexhaustion_authority)
        self.assertTrue(parsed.authority_only_corridor)
        self.assertTrue(parsed.diagnostic_continue_root_only_scale)

    def test_finalb_scale_authority_is_exact_and_stage_bound(self) -> None:
        image = Path("artifacts/decoded/ecldata7.ecl")
        arguments = _arguments(
            expected_stage=7,
            runtime_ecl_static_image=image,
            runtime_ecl_static_sha256="2" * 64,
            enable_finalb_scale_source_authority=True,
        )
        parsed = build_parser().parse_args(arguments)
        self.assertTrue(parsed.enable_finalb_scale_source_authority)
        self.assertEqual(parsed.runtime_ecl_static_image, image)

        with self.assertRaisesRegex(ValueError, "full route or stage 7"):
            _arguments(
                expected_stage=5,
                runtime_ecl_static_image=image,
                runtime_ecl_static_sha256="2" * 64,
                enable_finalb_scale_source_authority=True,
            )

        missing_no_bomb = build_parser().parse_args(
            [
                "--armed",
                "--pid",
                "1234",
                "--difficulty",
                "3",
                "--expected-stage",
                "7",
                "--runtime-ecl-static-image",
                str(image),
                "--runtime-ecl-static-sha256",
                "2" * 64,
                "--enable-finalb-scale-source-authority",
                "trial.jsonl",
            ]
        )
        with self.assertRaisesRegex(ValueError, "hard no-Bomb"):
            _prepare_live_run(missing_no_bomb)

    def test_duration_difficulty_and_native_rollbacks_are_explicit(self) -> None:
        self.assertEqual(
            build_parser().parse_args(
                _arguments(duration_seconds=4500.0)
            ).duration,
            4500.0,
        )
        for difficulty in (1, 2):
            self.assertEqual(
                build_parser().parse_args(
                    _arguments(difficulty=difficulty)
                ).difficulty,
                difficulty,
            )
        for attribute, rollback in (
            ("local_hazard_backend", "numpy"),
            ("local_beam_reducer", "python"),
            ("bullet_decode_backend", "python"),
        ):
            parsed = build_parser().parse_args(
                _arguments(**{attribute: rollback})
            )
            self.assertEqual(getattr(parsed, attribute), rollback)

    def test_terminal_summary_reader_is_bounded(self) -> None:
        with TemporaryDirectory() as temporary:
            trace = Path(temporary) / "trial.jsonl"
            trace.write_text(
                '{"kind":"decision","frame":2}\n'
                '{"kind":"summary","last_frame":225973,'
                '"counter_gaps":4,"hit_count":9,'
                '"termination_reason":"route_complete"}\n',
                encoding="utf-8",
            )
            summary = read_runtime_summary(trace)
        self.assertEqual(summary["last_frame"], 225973)
        self.assertEqual(summary["hit_count"], 9)
        self.assertEqual(summary["termination_reason"], "route_complete")

    def test_completed_trial_cannot_rearm(self) -> None:
        self.assertFalse(
            one_shot_trial_finished(agent_started=False, agent_alive=False)
        )
        self.assertFalse(
            one_shot_trial_finished(agent_started=True, agent_alive=True)
        )
        self.assertTrue(
            one_shot_trial_finished(agent_started=True, agent_alive=False)
        )


if __name__ == "__main__":
    unittest.main()
