#!/usr/bin/env python3
"""Regression for the unattended full-route completion boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from th08_automation import full_route_artifacts
from th08_automation.practice_menu import parse_practice_difficulty
from th08_live.scale_source_trace import FINAL_B_ECL_STATIC_SHA256
from th08_full_route_supervisor import (
    _terminal_scene_record,
    build_parser,
    retain_game_after_trial,
    validate_team_selection,
)


class FullRouteSupervisorTests(unittest.TestCase):
    def test_percentile_comparison_preserves_missing_solver_metrics(self) -> None:
        result = full_route_artifacts._percentile_change(
            {"median": 10.0, "p95": 20.0, "max": 30.0},
            None,
        )

        self.assertEqual(
            result,
            {
                "median": {
                    "baseline": 10.0,
                    "candidate": None,
                    "delta": None,
                },
                "p95": {
                    "baseline": 20.0,
                    "candidate": None,
                    "delta": None,
                },
                "max": {
                    "baseline": 30.0,
                    "candidate": None,
                    "delta": None,
                },
            },
        )

    def test_wrapper_resolves_supervisor_relative_to_itself(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "run_th08_full_route_agent.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            r"%~dp0scripts\th08_full_route_supervisor.py",
            wrapper,
        )
        self.assertNotIn(
            r"\\wsl.localhost\ubuntu\home\pentester",
            wrapper,
        )
        self.assertIn("--enable-finalb-scale-source-authority", wrapper)
        self.assertIn(FINAL_B_ECL_STATIC_SHA256, wrapper)
        self.assertIn(r"artifacts\decoded\ecldata7.ecl", wrapper)

    def test_parser_preserves_lunatic_default_and_accepts_hard(self) -> None:
        self.assertEqual(build_parser().parse_args([]).difficulty.key, "lunatic")
        args = build_parser().parse_args(
            ["--difficulty", "hard", "--leave-game-running"]
        )
        self.assertEqual(args.difficulty.menu_index, 2)
        self.assertTrue(args.leave_game_running)

    def test_full_route_scale_source_contract_is_explicit(self) -> None:
        args = build_parser().parse_args(
            [
                "--runtime-ecl-static-image",
                "artifacts/decoded/ecldata7.ecl",
                "--runtime-ecl-static-sha256",
                FINAL_B_ECL_STATIC_SHA256,
                "--enable-finalb-scale-source-authority",
            ]
        )

        self.assertTrue(args.enable_finalb_scale_source_authority)
        self.assertEqual(
            args.runtime_ecl_static_sha256,
            FINAL_B_ECL_STATIC_SHA256,
        )

    def test_enemy_mode_capture_is_complete_route_diagnostic_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--trace-enemy-mode-transitions"]
        )

        self.assertFalse(default_args.trace_enemy_mode_transitions)
        self.assertTrue(enabled_args.trace_enemy_mode_transitions)

    def test_enemy_lifecycle_capture_is_complete_route_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--trace-enemy-lifecycle-events"]
        )

        self.assertFalse(default_args.trace_enemy_lifecycle_events)
        self.assertTrue(enabled_args.trace_enemy_lifecycle_events)

    def test_compute_only_diagnostics_are_explicit(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--trace-items", "--authority-only-corridor"]
        )

        self.assertFalse(default_args.trace_items)
        self.assertFalse(default_args.authority_only_corridor)
        self.assertTrue(enabled_args.trace_items)
        self.assertTrue(enabled_args.authority_only_corridor)

    def test_ordinary_nonspell_control_options_are_explicit(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            [
                "--kill-before-saturation",
                "--ordinary-preexhaustion-authority",
            ]
        )

        self.assertFalse(default_args.kill_before_saturation)
        self.assertFalse(
            default_args.ordinary_preexhaustion_authority
        )
        self.assertTrue(enabled_args.kill_before_saturation)
        self.assertTrue(
            enabled_args.ordinary_preexhaustion_authority
        )

    def test_enemy_mode_scale_continuation_is_explicit(self) -> None:
        enabled_args = build_parser().parse_args(
            [
                "--trace-enemy-mode-transitions",
                "--diagnostic-continue-root-only-scale",
            ]
        )
        self.assertTrue(enabled_args.trace_enemy_mode_transitions)
        self.assertTrue(
            enabled_args.diagnostic_continue_root_only_scale
        )

    def test_team_preconfirm_uses_selected_difficulty_cursor(self) -> None:
        import th08_full_route_supervisor as supervisor
        from unittest.mock import patch

        state = {
            "mode": supervisor.TITLE_MODE_GAME_TEAM,
            "substate": 1,
            "cursor": 2,
            "difficulty_cursor": 2,
        }
        with patch.object(
            supervisor,
            "_read_title_menu_state",
            return_value=state,
        ):
            selected = validate_team_selection(
                object(),
                1234,
                difficulty=parse_practice_difficulty("hard"),
            )
        self.assertIs(selected, state)

    def test_only_accepted_opt_in_route_survives_final_cleanup(self) -> None:
        self.assertTrue(
            retain_game_after_trial(
                accepted=True,
                leave_game_running=True,
            )
        )
        for accepted, requested in (
            (False, False),
            (False, True),
            (True, False),
        ):
            with self.subTest(accepted=accepted, requested=requested):
                self.assertFalse(
                    retain_game_after_trial(
                        accepted=accepted,
                        leave_game_running=requested,
                    )
                )

    def test_terminal_unload_precedes_route_complete_summary(self) -> None:
        with TemporaryDirectory() as temporary:
            trace = Path(temporary) / "trial.jsonl"
            rows = [
                {
                    "kind": "scene_inactive",
                    "frame": 226864,
                    "engine_flags": 109072,
                    "stage_route_index": 7,
                    "transition_from_stage": 7,
                    "expected_stage": None,
                    "status": "terminal_unload",
                },
                {
                    "kind": "summary",
                    "last_frame": 226864,
                    "termination_reason": "route_complete",
                },
            ]
            trace.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            completion = _terminal_scene_record(trace)
        self.assertEqual(completion["frame"], 226864)
        self.assertEqual(completion["engine_flags"], 109072)

    def test_materializer_writes_one_markdown_run_note(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_reports = root / "runtime_reports"
            run_notes = root / "runs"
            run_id = "lunatic_route2_fullrun_unattended_20260729_130000"
            captured_argv: list[str] = []
            dossier = {
                "acceptance_target": {
                    "difficulty_index": 3,
                    "difficulty": "lunatic",
                },
                "stages": [
                    {"stage_route_index": stage}
                    for stage in full_route_artifacts.EXPECTED_ROUTE_STAGES
                ],
                "control_policy": {
                    "no_bomb_verification": {"passed": True}
                },
                "provenance": [
                    {"summary": {"termination_reason": "route_complete"}}
                ],
            }

            def fake_dossier(argv: list[str]) -> None:
                captured_argv.extend(argv)
                json_output = Path(argv[argv.index("--json-output") + 1])
                markdown = Path(
                    argv[argv.index("--markdown-output") + 1]
                )
                json_output.parent.mkdir(parents=True, exist_ok=True)
                json_output.write_text(
                    json.dumps(dossier) + "\n",
                    encoding="utf-8",
                )
                markdown.parent.mkdir(parents=True, exist_ok=True)
                markdown.write_text("# retained route\n", encoding="utf-8")

            with (
                patch.object(
                    full_route_artifacts,
                    "build_run_dossier",
                    side_effect=fake_dossier,
                ),
                patch.object(
                    full_route_artifacts,
                    "write_compact_full_route_summary",
                ),
                patch.object(
                    full_route_artifacts,
                    "load_and_validate",
                    return_value=object(),
                ),
                patch.object(
                    full_route_artifacts,
                    "asdict",
                    return_value={},
                ),
                patch.object(
                    full_route_artifacts,
                    "previous_full_dossier",
                    return_value=None,
                ),
            ):
                artifacts = full_route_artifacts.materialize_artifacts(
                    run_id=run_id,
                    trace=runtime_reports / f"{run_id}.jsonl",
                    completion={"frame": 100, "engine_flags": 1},
                    root=root,
                    runtime_report_dir=runtime_reports,
                    run_note_dir=run_notes,
                )

            run_note = run_notes / f"{run_id}.md"
            self.assertEqual(
                captured_argv[
                    captured_argv.index("--markdown-output") + 1
                ],
                str(run_note),
            )
            self.assertEqual(artifacts["dossier_markdown"], str(run_note))
            self.assertEqual(artifacts["run_note"], str(run_note))
            self.assertEqual(
                run_note.read_text(encoding="utf-8"),
                "# retained route\n",
            )
            self.assertFalse(
                (runtime_reports / f"{run_id}.dossier.md").exists()
            )

    def test_dossier_v4_is_eligible_as_completed_route_baseline(self) -> None:
        with TemporaryDirectory() as temporary:
            runtime_reports = Path(temporary)
            current = runtime_reports / (
                "lunatic_route2_fullrun_unattended_current.dossier.json"
            )
            current.write_text("{}\n", encoding="utf-8")
            candidate = runtime_reports / (
                "lunatic_route2_fullrun_unattended_previous.dossier.json"
            )
            candidate.write_text(
                json.dumps(
                    {
                        "schema": "th08-route-run-dossier-v4",
                        "control_policy": {
                            "no_bomb_verification": {"passed": True}
                        },
                        "provenance": [
                            {
                                "summary": {
                                    "termination_reason": "route_complete"
                                }
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            selected = full_route_artifacts.previous_full_dossier(
                current,
                runtime_report_dir=runtime_reports,
            )

            self.assertEqual(selected, candidate)


if __name__ == "__main__":
    unittest.main()
