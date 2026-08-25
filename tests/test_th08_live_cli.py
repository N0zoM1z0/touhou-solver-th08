#!/usr/bin/env python3
"""Focused tests for the active TH08 live-controller CLI."""

from __future__ import annotations

import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from th08_live import controller
from th08_live.cli import LiveParserDefaults, build_live_parser


class Th08LiveCliTests(unittest.TestCase):
    def test_pure_builder_uses_controller_defaults(self) -> None:
        defaults = LiveParserDefaults(
            planner_horizon=11,
            planner_threat_horizon=33,
            planner_beam_width=25,
            control_delay_frames=3,
            corridor_replan_frames=9,
            corridor_lookahead_frames=17,
            corridor_max_age_frames=73,
            stage_transition_timeout_seconds=91.0,
            terminal_inactive_grace_seconds=6.0,
        )
        arguments = build_live_parser(
            defaults,
            description="test parser",
        ).parse_args(["trace.jsonl"])
        self.assertEqual(arguments.output, Path("trace.jsonl"))
        self.assertEqual(arguments.horizon, 11)
        self.assertEqual(arguments.threat_horizon, 33)
        self.assertEqual(arguments.corridor_every, 9)
        self.assertEqual(arguments.stage_transition_timeout, 91.0)
        self.assertFalse(arguments.trace_enemy_lifecycle_events)
        self.assertFalse(arguments.kill_before_saturation)
        self.assertFalse(arguments.ordinary_preexhaustion_authority)
        self.assertIsNone(arguments.future_source_retain_dir)
        self.assertEqual(arguments.future_source_retain_spell, [])
        self.assertEqual(arguments.future_source_retain_max_per_spell, 1)
        self.assertTrue(arguments.losing_control_reserve)

    def test_controller_wrapper_resolves_current_values(self) -> None:
        with (
            patch.object(controller, "PLANNER_HORIZON", 19),
            patch.object(controller, "CORRIDOR_REPLAN_FRAMES", 13),
        ):
            arguments = controller.build_parser().parse_args(["trace.jsonl"])
        self.assertEqual(arguments.horizon, 19)
        self.assertEqual(arguments.corridor_every, 13)

    def test_bomb_options_remain_mutually_exclusive(self) -> None:
        with (
            redirect_stderr(StringIO()),
            self.assertRaises(SystemExit),
        ):
            controller.build_parser().parse_args(
                ["trace.jsonl", "--normal-bomb", "--no-bomb"]
            )

    def test_enemy_lifecycle_probe_is_explicitly_opt_in(self) -> None:
        arguments = controller.build_parser().parse_args(
            ["trace.jsonl", "--trace-enemy-lifecycle-events"]
        )
        self.assertTrue(arguments.trace_enemy_lifecycle_events)

    def test_kill_before_saturation_is_explicitly_opt_in(self) -> None:
        arguments = controller.build_parser().parse_args(
            ["trace.jsonl", "--kill-before-saturation", "--no-bomb"]
        )
        self.assertTrue(arguments.kill_before_saturation)

    def test_ordinary_preexhaustion_authority_is_explicitly_opt_in(
        self,
    ) -> None:
        arguments = controller.build_parser().parse_args(
            [
                "trace.jsonl",
                "--ordinary-preexhaustion-authority",
                "--no-bomb",
            ]
        )
        self.assertTrue(arguments.ordinary_preexhaustion_authority)

    def test_future_source_retention_is_explicit_and_bounded(self) -> None:
        arguments = controller.build_parser().parse_args(
            [
                "trace.jsonl",
                "--future-source-retain-dir",
                "roots",
                "--future-source-retain-spell",
                "103",
                "--future-source-retain-spell",
                "115",
                "--future-source-retain-max-per-spell",
                "2",
            ]
        )

        self.assertEqual(arguments.future_source_retain_dir, Path("roots"))
        self.assertEqual(arguments.future_source_retain_spell, [103, 115])
        self.assertEqual(arguments.future_source_retain_max_per_spell, 2)

    def test_future_source_retention_requires_both_sink_and_spell(self) -> None:
        missing_spell = controller.build_parser().parse_args(
            [
                "trace.jsonl",
                "--armed",
                "--future-source-retain-dir",
                "roots",
            ]
        )
        with self.assertRaisesRegex(ValueError, "both a directory"):
            controller._prepare_live_run(missing_spell)

        missing_sink = controller.build_parser().parse_args(
            [
                "trace.jsonl",
                "--armed",
                "--future-source-retain-spell",
                "103",
            ]
        )
        with self.assertRaisesRegex(ValueError, "both a directory"):
            controller._prepare_live_run(missing_sink)

    def test_unsafe_lifecycle_cleanup_terminates_verified_target(self) -> None:
        records: list[dict[str, object]] = []

        class _Sink:
            def emit(
                self,
                record: dict[str, object],
                *,
                flush: bool = False,
            ) -> None:
                records.append(record)

        api = object()
        image = Path("C:/games/th08.exe")
        with (
            patch(
                "th08_automation.practice_windows.configure_supervisor_api"
            ) as configure,
            patch(
                "th08_automation.practice_windows.terminate_exact_target",
                return_value=True,
            ) as terminate,
        ):
            controller._terminate_unsafe_instrumented_target(
                api=api,
                verified_image_path=image,
                trace_sink=_Sink(),
                phase="cleanup",
            )
        configure.assert_called_once_with(api)
        terminate.assert_called_once_with(api, image)
        self.assertTrue(records[0]["terminated"])

    def test_losing_control_reserve_has_explicit_rollback(self) -> None:
        arguments = controller.build_parser().parse_args(
            ["trace.jsonl", "--no-losing-control-reserve"]
        )
        self.assertFalse(arguments.losing_control_reserve)


if __name__ == "__main__":
    unittest.main()
