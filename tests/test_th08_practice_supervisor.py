#!/usr/bin/env python3
"""Tests for unattended original-game Practice Start automation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import th08_practice_supervisor as supervisor
from th08_automation import practice_artifacts
from th08_automation import practice_native_menu
from th08_automation.practice_menu import (
    build_practice_menu_plan,
    forward_menu_steps,
    parse_practice_difficulty,
    parse_practice_stage,
)
from th08_practice_supervisor import (
    ROOT,
    _progress_text,
    build_patch_batch_command,
    build_parser,
    practice_stage_available,
    read_last_json_record,
    resolve_runtime_ecl_static_image,
)


class PracticeSupervisorTests(unittest.TestCase):
    def test_stage_menu_order_matches_original_practice_screen(self) -> None:
        expected = {
            "1": (0, 0),
            "2": (1, 1),
            "3": (2, 2),
            "4a": (3, 3),
            "4b": (4, 4),
            "5": (5, 5),
            "6a": (6, 6),
            "6b": (7, 7),
        }
        for key, (menu_index, route_index) in expected.items():
            with self.subTest(stage=key):
                stage = parse_practice_stage(key)
                self.assertEqual(stage.menu_index, menu_index)
                self.assertEqual(stage.route_index, route_index)

    def test_difficulty_menu_order_matches_original_practice_screen(
        self,
    ) -> None:
        expected = {
            "easy": 0,
            "normal": 1,
            "hard": 2,
            "lunatic": 3,
        }
        for key, menu_index in expected.items():
            with self.subTest(difficulty=key):
                difficulty = parse_practice_difficulty(key)
                self.assertEqual(difficulty.menu_index, menu_index)

    def test_static_menu_intent_names_the_selected_difficulty(self) -> None:
        plan = build_practice_menu_plan(
            parse_practice_stage("1"),
            tap_gap_ms=180,
            screen_settle_ms=700,
            difficulty=parse_practice_difficulty("hard"),
        )
        self.assertEqual(
            plan[4].purpose,
            "accept native-verified Hard",
        )

    def test_plan_stops_before_final_stage_confirm(self) -> None:
        stage = parse_practice_stage("Stage-4B")
        plan = build_practice_menu_plan(
            stage,
            tap_gap_ms=180,
            screen_settle_ms=700,
        )
        self.assertEqual(
            [tap.key for tap in plan],
            [
                "down",
                "down",
                "down",
                "confirm",
                "confirm",
                "right",
                "right",
                "confirm",
            ]
            + ["down"] * 4,
        )
        self.assertEqual(plan[-1].wait_after_ms, 700)
        self.assertNotEqual(plan[-1].key, "confirm")

    def test_stage_one_waits_on_stage_screen_without_extra_direction(self) -> None:
        plan = build_practice_menu_plan(
            parse_practice_stage("1"),
            tap_gap_ms=180,
            screen_settle_ms=700,
        )
        self.assertEqual(
            [tap.key for tap in plan],
            [
                "down",
                "down",
                "down",
                "confirm",
                "confirm",
                "right",
                "right",
                "confirm",
            ],
        )
        self.assertEqual(plan[-1].wait_after_ms, 700)

    def test_ce_0052_fresh_team_menu_moves_to_third_sakuya_remilia(self) -> None:
        plan = build_practice_menu_plan(
            parse_practice_stage("1"),
            tap_gap_ms=180,
            screen_settle_ms=700,
        )
        self.assertEqual(
            [tap.key for tap in plan[5:8]],
            ["right", "right", "confirm"],
        )

    def test_native_cursor_navigation_is_bounded_and_wraps_forward(self) -> None:
        self.assertEqual(forward_menu_steps(3, 3, 4), 0)
        self.assertEqual(forward_menu_steps(0, 3, 4), 3)
        self.assertEqual(forward_menu_steps(3, 2, 4), 3)
        self.assertEqual(forward_menu_steps(0, 2, 4), 2)

    def test_final_a_is_bit_six_of_native_practice_availability(self) -> None:
        final_a = parse_practice_stage("6a")
        self.assertEqual(final_a.menu_index, 6)
        self.assertFalse(practice_stage_available(0xBF, final_a.menu_index))
        self.assertTrue(practice_stage_available(0xFF, final_a.menu_index))

    def test_requested_stage_unlock_sets_only_one_source_clear_bit(self) -> None:
        initial = {
            "manager": 0x1234,
            "mode": practice_native_menu.TITLE_MODE_PRACTICE_STAGE,
            "substate": 1,
            "screen_age": 46,
            "cursor": 0,
            "difficulty_cursor": 3,
            "difficulty_index": 0,
            "route_id": 2,
            "stage_route_index": 0,
            "practice_stage_availability_mask": 0x0001,
        }
        verified = dict(initial)
        verified["practice_stage_availability_mask"] = 0x0021
        api = object()
        with (
            patch.object(
                practice_native_menu,
                "wait_for_title_menu",
                return_value=initial,
            ),
            patch.object(
                practice_native_menu,
                "read_title_menu_state",
                return_value=verified,
            ),
            patch.object(
                practice_native_menu,
                "write_process_u16",
            ) as write,
        ):
            result = practice_native_menu.unlock_requested_practice_stage(
                api,
                284,
                stage_index=5,
                expected_route_id=2,
                expected_difficulty_index=3,
                timeout_seconds=3.0,
            )
        address = practice_native_menu.practice_stage_availability_address(2, 3)
        write.assert_called_once_with(api, 284, address, 0x0021)
        self.assertEqual(result["mask_before"], 0x0001)
        self.assertEqual(result["mask_after"], 0x0021)
        self.assertTrue(result["wrote"])

    def test_parser_accepts_repeatable_stage_selection(self) -> None:
        args = build_parser().parse_args(
            [
                "--stage",
                "6a",
                "--repeat",
                "3",
                "--safety-value-horizon",
                "32",
                "--viability-audit",
                "--agent-duration",
                "86400",
                "--trial-timeout",
                "86700",
                "--armed",
            ]
        )
        self.assertEqual(args.stage.key, "6a")
        self.assertEqual(args.stage.route_index, 6)
        self.assertEqual(args.repeat, 3)
        self.assertTrue(args.armed)
        self.assertTrue(args.kill_existing)
        self.assertEqual(args.safety_value_horizon, 32)
        self.assertTrue(args.viability_audit)
        self.assertEqual(args.agent_duration, 86_400.0)
        self.assertEqual(args.trial_timeout, 86_700.0)
        self.assertFalse(args.input_clock_boundary_shadow)
        self.assertEqual(args.input_clock_shadow_sample_ms, 1.0)
        self.assertEqual(args.difficulty.key, "lunatic")
        self.assertIsNone(args.runtime_ecl_static_image)
        self.assertIsNone(args.runtime_ecl_static_sha256)
        self.assertFalse(args.enable_finalb_scale_source_authority)

    def test_replay_save_slot_is_explicit_and_bounded(self) -> None:
        args = supervisor.build_parser().parse_args(
            ["--stage", "5", "--save-replay-slot", "15"]
        )
        self.assertEqual(args.save_replay_slot, 15)
        self.assertEqual(args.replay_save_timeout, 20.0)
        with self.assertRaises(SystemExit):
            supervisor.build_parser().parse_args(
                ["--save-replay-slot", "16"]
            )

    def test_parser_accepts_explicit_runtime_ecl_identity(self) -> None:
        args = build_parser().parse_args(
            [
                "--stage",
                "5",
                "--runtime-ecl-static-image",
                "artifacts/decoded/ecldata5.ecl",
                "--runtime-ecl-static-sha256",
                "1" * 64,
                "--armed",
            ]
        )
        self.assertEqual(
            args.runtime_ecl_static_image,
            Path("artifacts/decoded/ecldata5.ecl"),
        )
        self.assertEqual(args.runtime_ecl_static_sha256, "1" * 64)

    def test_parser_accepts_explicit_finalb_scale_authority(self) -> None:
        args = build_parser().parse_args(
            [
                "--stage",
                "6b",
                "--runtime-ecl-static-image",
                "artifacts/decoded/ecldata7.ecl",
                "--runtime-ecl-static-sha256",
                supervisor.FINAL_B_ECL_STATIC_SHA256,
                "--enable-finalb-scale-source-authority",
            ]
        )

        self.assertTrue(args.enable_finalb_scale_source_authority)

    def test_runtime_ecl_identity_is_validated_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "data5.ecl"
            payload = b"exact-static-ecl"
            image.write_bytes(payload)
            expected = hashlib.sha256(payload).hexdigest()

            self.assertEqual(
                resolve_runtime_ecl_static_image(image, expected),
                image.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                resolve_runtime_ecl_static_image(image, "0" * 64)
            with self.assertRaisesRegex(ValueError, "not readable"):
                resolve_runtime_ecl_static_image(
                    image.with_name("missing.ecl"),
                    expected,
                )

    def test_runtime_ecl_identity_requires_path_and_hash_together(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires both"):
            resolve_runtime_ecl_static_image(Path("data5.ecl"), None)
        with self.assertRaisesRegex(ValueError, "requires both"):
            resolve_runtime_ecl_static_image(None, "0" * 64)

    def test_enemy_mode_capture_is_whole_stage_diagnostic_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--trace-enemy-mode-transitions"]
        )

        self.assertFalse(default_args.trace_enemy_mode_transitions)
        self.assertTrue(enabled_args.trace_enemy_mode_transitions)

    def test_enemy_lifecycle_capture_is_whole_stage_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--trace-enemy-lifecycle-events"]
        )

        self.assertFalse(default_args.trace_enemy_lifecycle_events)
        self.assertTrue(enabled_args.trace_enemy_lifecycle_events)

    def test_kill_before_saturation_is_physical_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--kill-before-saturation"]
        )

        self.assertFalse(default_args.kill_before_saturation)
        self.assertTrue(enabled_args.kill_before_saturation)

    def test_ordinary_preexhaustion_authority_is_physical_opt_in(
        self,
    ) -> None:
        default_args = build_parser().parse_args([])
        enabled_args = build_parser().parse_args(
            ["--ordinary-preexhaustion-authority"]
        )

        self.assertFalse(
            default_args.ordinary_preexhaustion_authority
        )
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

    def test_scale_continuation_does_not_require_a_trace_observer(
        self,
    ) -> None:
        api = object()
        with (
            patch.object(supervisor.os, "name", "nt"),
            patch.object(supervisor, "Win32", return_value=api),
            patch.object(supervisor, "_configure_supervisor_api"),
            patch.object(
                supervisor,
                "run_trial",
                return_value=SimpleNamespace(run_id="stage5-reserve"),
            ) as run_trial,
        ):
            self.assertEqual(
                supervisor.main(
                    [
                        "--stage",
                        "5",
                        "--diagnostic-continue-root-only-scale",
                        "--armed",
                    ]
                ),
                0,
            )

        self.assertFalse(
            run_trial.call_args.args[0].trace_enemy_mode_transitions
        )
        self.assertTrue(
            run_trial.call_args.args[0].diagnostic_continue_root_only_scale
        )

    def test_parser_accepts_normal_and_hard_practice_difficulties(
        self,
    ) -> None:
        for key, menu_index in (("normal", 1), ("hard", 2)):
            with self.subTest(difficulty=key):
                args = build_parser().parse_args(
                    [
                        "--stage",
                        "1",
                        "--difficulty",
                        key,
                        "--armed",
                    ]
                )
                self.assertEqual(args.difficulty.key, key)
                self.assertEqual(args.difficulty.menu_index, menu_index)

    def test_preconfirm_gate_uses_difficulty_cursor_before_gameplay_index(
        self,
    ) -> None:
        state = {
            "mode": supervisor.TITLE_MODE_PRACTICE_STAGE,
            "substate": 1,
            "cursor": 0,
            "difficulty_cursor": 2,
            "difficulty_index": 0,
            "route_id": 2,
        }
        with patch.object(
            supervisor,
            "_read_title_menu_state",
            return_value=state,
        ):
            selected = supervisor._validate_practice_selection(
                object(),
                1234,
                stage=parse_practice_stage("1"),
                difficulty=parse_practice_difficulty("hard"),
            )
        self.assertIs(selected, state)

    def test_shadow_services_are_explicitly_opt_in(self) -> None:
        cases = (
            (
                "4a",
                (
                    "--input-clock-boundary-shadow",
                    "--input-clock-shadow-sample-ms",
                    "2.5",
                ),
                "input_clock_boundary_shadow",
            ),
        )
        for stage, options, attribute in cases:
            with self.subTest(attribute=attribute):
                args = build_parser().parse_args(
                    ["--stage", stage, *options, "--armed"]
                )
                self.assertTrue(getattr(args, attribute))
                if attribute == "input_clock_boundary_shadow":
                    self.assertEqual(args.input_clock_shadow_sample_ms, 2.5)

    def test_native_backends_default_with_explicit_rollbacks(self) -> None:
        cases = (
            ("local_hazard_backend", "--local-hazard-backend", "numpy"),
            ("local_beam_reducer", "--local-beam-reducer", "python"),
            ("bullet_decode_backend", "--bullet-decode-backend", "python"),
        )
        for attribute, option, rollback in cases:
            with self.subTest(attribute=attribute):
                default_args = build_parser().parse_args(
                    ["--stage", "4a", "--armed"]
                )
                rollback_args = build_parser().parse_args(
                    [
                        "--stage",
                        "4a",
                        option,
                        rollback,
                        "--armed",
                    ]
                )
                self.assertEqual(getattr(default_args, attribute), "native")
                self.assertEqual(
                    getattr(rollback_args, attribute),
                    rollback,
                )

    def test_tail_reader_handles_a_record_larger_than_one_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trial.jsonl"
            records = [
                {"kind": "identity", "padding": "x" * 80_000},
                {
                    "kind": "decision",
                    "frame": 123,
                    "stage_route_index": 2,
                    "hit_count": 4,
                },
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(read_last_json_record(path), records[-1])

    def test_progress_text_is_bounded_and_operator_readable(self) -> None:
        text = _progress_text(
            {
                "kind": "decision",
                "frame": 500,
                "stage_route_index": 3,
                "spell_id": 99,
                "hit_count": 2,
                "active_bullets": 800,
                "active_lasers": 12,
                "unused_large_field": "x" * 1000,
            }
        )
        self.assertEqual(
            text,
            "kind=decision frame=500 stage=3 spell=99 hits=2 "
            "bullets=800 lasers=12",
        )

    def test_progress_text_reads_nested_live_spell_state(self) -> None:
        text = _progress_text(
            {
                "kind": "decision",
                "frame": 500,
                "stage_route_index": 3,
                "spell": {"active": True, "spell_id": 57},
                "hit_count": 2,
                "active_bullets": 800,
                "active_lasers": 0,
            }
        )
        self.assertIn("spell=57", text)

    def test_progress_text_reads_post_issue_decision_frame(self) -> None:
        text = _progress_text(
            {
                "kind": "enemy_combat_progress",
                "decision_frame": 2397,
                "stage_route_index": 5,
            }
        )
        self.assertIn(
            "kind=enemy_combat_progress frame=2397 stage=5",
            text,
        )

    def test_ce_0050_wrapper_does_not_use_dependency_free_ida_python(self) -> None:
        wrapper = (ROOT / "run_th08_practice_agent.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn(r"%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe", wrapper)
        self.assertIn('-c "import numpy"', wrapper)
        self.assertIn(
            r"%~dp0scripts\th08_practice_supervisor.py",
            wrapper,
        )
        self.assertNotIn(
            r"\\wsl.localhost\ubuntu\home\pentester",
            wrapper,
        )
        self.assertNotIn(r"IDA Pro 9.3\python311\python.exe", wrapper)

    def test_ce_0051_patch_batch_path_is_not_nested_in_one_cmd_argument(
        self,
    ) -> None:
        path = Path(r"D:\Game Directory\run patch.bat")
        command = build_patch_batch_command(path)
        self.assertEqual(command[1:5], ("/d", "/c", "call", str(path)))
        self.assertNotIn("/s", tuple(part.lower() for part in command))
        self.assertNotIn('call "', command[-1])

    def test_completed_stage_selects_no_save_with_right_only(self) -> None:
        with (
            patch.object(supervisor, "focus_target_window"),
            patch.object(supervisor, "drive_menu_plan") as drive,
        ):
            result = supervisor.select_no_save_before_termination(
                object(),
                123,
                hold_ms=65,
                tap_gap_ms=180,
            )
        self.assertTrue(result["sent"])
        plan = drive.call_args.args[2]
        self.assertEqual([tap.key for tap in plan], ["right"])

    def test_killed_partial_is_not_accepted_as_completed_practice(self) -> None:
        self.assertTrue(
            supervisor.accepted_practice_termination(
                {"termination_reason": "route_complete"}
            )
        )
        self.assertFalse(
            supervisor.accepted_practice_termination(
                {"termination_reason": "process_unreadable"}
            )
        )
        self.assertFalse(supervisor.accepted_practice_termination(None))

    def test_comparison_skips_newer_discarded_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accepted = root / (
                "lunatic_route2_stage5_unattended_20260724_010000"
                ".dossier.json"
            )
            discarded = root / (
                "lunatic_route2_stage5_unattended_20260724_020000"
                ".dossier.json"
            )
            current = root / (
                "lunatic_route2_stage5_unattended_20260724_030000"
                ".dossier.json"
            )
            for index, dossier in enumerate(
                (accepted, discarded, current), start=1
            ):
                dossier.write_text("{}\n", encoding="utf-8")
                os.utime(dossier, ns=(index, index))
            accepted.with_name(
                accepted.name.replace(".dossier.json", ".session.json")
            ).write_text(
                json.dumps(
                    {"status": "completed", "trial_accepted": True}
                ),
                encoding="utf-8",
            )
            discarded.with_name(
                discarded.name.replace(".dossier.json", ".session.json")
            ).write_text(
                json.dumps(
                    {"status": "discarded", "trial_accepted": False}
                ),
                encoding="utf-8",
            )
            with patch.object(supervisor, "RUNTIME_REPORT_DIR", root):
                baseline = supervisor._previous_dossier(
                    parse_practice_stage("5"),
                    current,
                )
            self.assertEqual(baseline, accepted)

    def test_materializer_writes_one_markdown_run_note(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_reports = root / "runtime_reports"
            run_notes = root / "runs"
            run_id = "lunatic_route2_stage5_unattended_20260729_130000"
            captured_argv: list[str] = []

            def fake_dossier(argv: list[str]) -> None:
                captured_argv.extend(argv)
                markdown = Path(
                    argv[argv.index("--markdown-output") + 1]
                )
                markdown.parent.mkdir(parents=True, exist_ok=True)
                markdown.write_text("# retained run\n", encoding="utf-8")

            with (
                patch.object(
                    practice_artifacts,
                    "build_practice_dossier",
                    side_effect=fake_dossier,
                ),
                patch.object(
                    practice_artifacts,
                    "previous_dossier",
                    return_value=None,
                ) as previous,
            ):
                artifacts = practice_artifacts.materialize_artifacts(
                    run_id=run_id,
                    stage=parse_practice_stage("5"),
                    difficulty=parse_practice_difficulty("lunatic"),
                    trace=runtime_reports / f"{run_id}.jsonl",
                    session_json=runtime_reports / f"{run_id}.session.json",
                    runtime_report_dir=runtime_reports,
                    run_note_dir=run_notes,
                    compare_to_baseline=False,
                )
            previous.assert_not_called()

            run_note = run_notes / f"{run_id}.md"
            self.assertEqual(
                captured_argv[
                    captured_argv.index("--markdown-output") + 1
                ],
                str(run_note),
            )
            self.assertEqual(artifacts.dossier_markdown, run_note)
            self.assertEqual(artifacts.run_note, run_note)
            self.assertEqual(
                run_note.read_text(encoding="utf-8"),
                "# retained run\n",
            )
            self.assertFalse(
                (runtime_reports / f"{run_id}.dossier.md").exists()
            )


if __name__ == "__main__":
    unittest.main()
