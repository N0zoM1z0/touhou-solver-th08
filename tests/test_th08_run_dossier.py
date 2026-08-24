#!/usr/bin/env python3
"""Focused tests for TH08 stitched run dossiers."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from analysis.th08_run_dossier import (
    TraceProvenance,
    _classify_death,
    _case_prefix_for_difficulty,
    _compact_decision,
    _death_clusters,
    _nearest_enemy_body,
    _nearest_bullet,
    _nearest_laser,
    _no_bomb_verification,
    _planner_consistency_summary,
    _robust_control_unsafe,
    _robust_viability_summary,
    _spell_attribution,
    _spell_inventory,
    _viability_action_set_empty,
    render_markdown,
)


def _row(
    frame: int,
    *,
    bullets: int = 1,
    pipeline: float = 5.0,
    slack: float = 2.0,
) -> dict[str, object]:
    return {
        "frame": frame,
        "player": {"x": 192.0, "y": 400.0},
        "nearby_bullets": [
            [17, 192.0, 400.0, 0.0, 0.0, 2.0, 2.0, 0]
        ]
        if bullets
        else [],
        "active_bullets": bullets,
        "active_lasers": 0,
        "pipeline_clearance": pipeline,
        "corridor_slack": slack,
        "action_lag": 1,
        "action": "stay",
    }


class Th08RunDossierTests(unittest.TestCase):
    def test_case_prefix_tracks_physical_difficulty(self) -> None:
        self.assertEqual(_case_prefix_for_difficulty("Hard"), "HARD")
        self.assertEqual(_case_prefix_for_difficulty("Lunatic"), "LUN")

    def test_full_run_markdown_uses_manifest_difficulty(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "runtime_reports"
            / "lunatic_route2_fullrun_unattended_20260730_222529.dossier.json"
        )
        dossier = json.loads(path.read_text(encoding="utf-8"))
        dossier["acceptance_target"]["difficulty"] = "Hard"
        dossier["acceptance_target"]["difficulty_index"] = 2

        rendered = render_markdown(dossier)

        self.assertIn("# TH08 Hard Full-Run Review:", rendered)
        self.assertIn("Sakuya/Remilia, Hard, Final B", rendered)
        self.assertIn("reachable Hard route inventory", rendered)
        self.assertNotIn("Lunatic", rendered)

    def test_spell_inventory_distinguishes_cleanly_observed_from_absent(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (
                root
                / "artifacts"
                / "route_manifests"
                / "sakuya_remilia_lunatic_final_b.json"
            ).read_text(encoding="utf-8")
        )
        decisions = [
            {
                "frame": frame,
                "stage_route_index": 7,
                "spell": {
                    "active": True,
                    "spell_id": 178,
                },
            }
            for frame in (100, 101)
        ]

        inventory = _spell_inventory(
            manifest,
            {},
            [],
            decisions,
            spell_schema_complete=True,
        )
        spells = {
            int(spell["spell_id"]): spell["runtime_attribution"]
            for spell in inventory[7]["spells"]
        }

        self.assertEqual(spells[178]["status"], "observed_live_spell_state")
        self.assertTrue(spells[178]["observed"])
        self.assertEqual(spells[178]["observed_decision_count"], 2)
        self.assertEqual(spells[178]["first_decision_frame"], 100)
        self.assertEqual(spells[178]["last_decision_frame"], 101)
        self.assertEqual(spells[178]["hit_count"], 0)
        self.assertEqual(spells[190]["status"], "not_observed_in_trace")
        self.assertFalse(spells[190]["observed"])
        self.assertEqual(spells[190]["observed_decision_count"], 0)
        self.assertIsNone(spells[190]["first_decision_frame"])
        self.assertIsNone(spells[190]["last_decision_frame"])

    def test_explicit_missing_enemy_snapshot_does_not_abort_dossier(
        self,
    ) -> None:
        row = {
            "frame": 91,
            "stage_route_index": 4,
            "resources": {"lives": 2.0, "bombs": 3.0, "power": 128.0},
            "player": {
                "x": 192.0,
                "y": 400.0,
                "phase": 1,
                "phase_at_action": 1,
                "predeath_at_action": 0,
            },
            "enemy_body_snapshot_frame": None,
            "enemy_bodies": [
                [17, 192.0, 300.0, 1.0, 0.0, 8.0, 8.0, 1]
            ],
        }
        compact = _compact_decision(
            row,
            trace_index=0,
            trace_path=Path("physical.jsonl"),
        )
        nearest = _nearest_enemy_body(row)

        self.assertIsNone(compact["enemy_body_snapshot_frame"])
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest["snapshot_frame"], 91)
        self.assertEqual(nearest["elapsed_frames"], 0)

    def test_no_bomb_verification_uses_input_not_stock_reset(self) -> None:
        provenance = [
            TraceProvenance(
                path="trace.jsonl",
                sha256="0" * 64,
                size_bytes=1,
                parse_errors=0,
                decision_count=1,
                first_frame=1,
                last_frame=1,
                summary=None,
                runtime_errors=(),
                wall_auto_confirm_frames=(),
                controller_configs=({"bomb_policy": "disabled"},),
            )
        ]
        verification = _no_bomb_verification(
            [
                {
                    "frame": 1,
                    "mask": 0x15,
                    "bomb": False,
                    "action": "left_focus",
                }
            ],
            provenance,
        )
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["mask_violation_frames"], [])

    def test_no_bomb_verification_rejects_bomb_input_bit(self) -> None:
        provenance = [
            TraceProvenance(
                path="trace.jsonl",
                sha256="0" * 64,
                size_bytes=1,
                parse_errors=0,
                decision_count=1,
                first_frame=1,
                last_frame=1,
                summary=None,
                runtime_errors=(),
                wall_auto_confirm_frames=(),
                controller_configs=({"bomb_policy": "disabled"},),
            )
        ]
        verification = _no_bomb_verification(
            [
                {
                    "frame": 2,
                    "mask": 0x02,
                    "bomb": False,
                    "action": "stay",
                }
            ],
            provenance,
        )
        self.assertFalse(verification["passed"])
        self.assertEqual(verification["mask_violation_frames"], [2])

    def test_robust_viability_summary_exposes_missing_queries(self) -> None:
        rows = [
            {
                "corridor_planning_mode": "robust_viability",
                "corridor_source_frame": 100,
                "corridor_solve_ms": 800.0,
                "corridor_age": 81,
                "corridor_stale": False,
                "viability": {},
                "robust_control": {"viability_constrained": False},
            },
            {
                "corridor_planning_mode": "robust_viability",
                "corridor_source_frame": 120,
                "corridor_solve_ms": 600.0,
                "corridor_age": 60,
                "corridor_stale": False,
                "viability": {
                    "available": True,
                    "state_viable": True,
                    "safe_action_count": 2,
                    "selected_repair_volume": 5,
                    "age": 60,
                    "support_covers_current": True,
                },
                "robust_control": {"viability_constrained": True},
            },
        ]
        summary = _robust_viability_summary(rows)
        self.assertEqual(summary["unique_solution_count"], 2)
        self.assertEqual(summary["decision_without_query_count"], 1)
        self.assertEqual(summary["available_query_count"], 1)
        self.assertEqual(summary["constrained_decision_count"], 1)
        self.assertEqual(summary["solve_ms"]["median"], 700.0)

    def test_planner_consistency_separates_horizon_from_action_contract(
        self,
    ) -> None:
        rows = [
            {
                "action": "right",
                "viability": {
                    "available": True,
                    "support_covers_current": True,
                    "state_viable": True,
                    "safe_action_count": 1,
                    "safe_actions": ["left"],
                },
                "robust_control": {
                    "worst_collisions": 1,
                    "min_clearance": -2.0,
                },
            },
            {
                "action": "stay",
                "viability": {
                    "available": True,
                    "support_covers_current": True,
                    "state_viable": False,
                    "safe_action_count": 0,
                    "safe_actions": [],
                },
                "robust_control": {
                    "worst_collisions": 0,
                    "min_clearance": 4.0,
                },
            },
            {
                "action": "left",
                "viability": {
                    "available": True,
                    "support_covers_current": True,
                    "state_viable": True,
                    "safe_action_count": 1,
                    "safe_actions": ["left"],
                },
                "robust_control": {
                    "worst_collisions": 1,
                    "min_clearance": -1.0,
                },
            },
            {
                "action": "left",
                "viability": {
                    "available": True,
                    "support_covers_current": True,
                    "state_viable": True,
                    "safe_action_count": 1,
                    "safe_actions": ["left"],
                },
                "robust_control": {
                    "worst_collisions": 1,
                    "min_clearance": -1.0,
                },
                "issue_time_enemy_guard": {
                    "changes": ["contact_mode:0x592230"],
                    "recertified": True,
                },
            },
            {
                "action": "left",
                "viability": {
                    "available": True,
                    "support_covers_current": True,
                    "state_viable": True,
                    "safe_action_count": 1,
                    "safe_actions": ["left"],
                },
                "robust_control": {
                    "worst_collisions": 1,
                    "min_clearance": -1.0,
                },
                "deadline_guard": {"input_suppressed": True},
            },
        ]
        summary = _planner_consistency_summary(rows)
        self.assertEqual(summary["comparable_decision_count"], 3)
        self.assertEqual(
            summary["global_winning_local_prefix_unsafe_count"],
            2,
        )
        self.assertEqual(
            summary["global_losing_local_prefix_safe_count"],
            1,
        )
        self.assertEqual(
            summary[
                "selected_certified_action_local_prefix_unsafe_count"
            ],
            1,
        )
        self.assertEqual(
            summary["selected_action_outside_global_winning_set_count"],
            1,
        )
        self.assertEqual(
            summary["excluded_hazard_version_change_count"],
            1,
        )
        self.assertEqual(summary["excluded_deadline_hold_count"], 1)

    def test_global_viability_exhaustion_requires_available_empty_query(
        self,
    ) -> None:
        self.assertFalse(_viability_action_set_empty({}))
        self.assertFalse(
            _viability_action_set_empty(
                {
                    "viability": {
                        "available": False,
                        "state_viable": False,
                        "safe_action_count": 0,
                    }
                }
            )
        )
        self.assertTrue(
            _viability_action_set_empty(
                {
                    "viability": {
                        "available": True,
                        "state_viable": False,
                        "safe_action_count": 0,
                    }
                }
            )
        )
        self.assertFalse(
            _viability_action_set_empty(
                {
                    "viability": {
                        "available": True,
                        "state_viable": False,
                        "safe_action_count": 0,
                        "support_covers_current": False,
                    }
                }
            )
        )

    def test_robust_action_set_exhaustion_uses_collision_or_margin(self) -> None:
        self.assertFalse(_robust_control_unsafe({}))
        self.assertFalse(
            _robust_control_unsafe(
                {
                    "robust_control": {
                        "worst_collisions": 0,
                        "min_clearance": 0.25,
                    }
                }
            )
        )
        self.assertTrue(
            _robust_control_unsafe(
                {
                    "robust_control": {
                        "worst_collisions": 1,
                        "min_clearance": 3.0,
                    }
                }
            )
        )
        self.assertTrue(
            _robust_control_unsafe(
                {
                    "robust_control": {
                        "worst_collisions": 0,
                        "min_clearance": -0.01,
                    }
                }
            )
        )

    def test_native_overlap_outranks_positive_pipeline_model(self) -> None:
        row = _row(100)
        primary, contributing, nearest, laser, enemy = _classify_death(
            row,
            window=[row],
        )
        self.assertEqual(primary, "observed_bullet_overlap")
        self.assertEqual(nearest["slot"], 17)
        self.assertIsNone(laser)
        self.assertIsNone(enemy)
        self.assertEqual(contributing, [])

    def test_missing_witness_stays_explicitly_unmodeled(self) -> None:
        row = _row(100, bullets=0, pipeline=8.0, slack=-2.0)
        primary, contributing, nearest, laser, enemy = _classify_death(
            row,
            window=[row],
        )
        self.assertEqual(primary, "sensor_gap_or_unmodeled_hazard")
        self.assertIsNone(nearest)
        self.assertIsNone(laser)
        self.assertIsNone(enemy)
        self.assertIn("corridor_deadline_miss", contributing)

    def test_causal_selected_collision_outranks_late_positive_hit_row(
        self,
    ) -> None:
        alive = _row(97, bullets=0, pipeline=3.0)
        alive["player"] = {
            "x": 192.0,
            "y": 400.0,
            "phase": 0,
            "phase_at_action": 0,
        }
        alive["robust_control"] = {
            "worst_collisions": 1,
            "min_clearance": -1.5,
        }
        hit = _row(100, bullets=0, pipeline=2.0)

        primary, contributing, nearest, laser, enemy = _classify_death(
            hit,
            window=[alive, hit],
        )

        self.assertEqual(primary, "modeled_committed_prefix_collision")
        self.assertEqual(contributing, [])
        self.assertIsNone(nearest)
        self.assertIsNone(laser)
        self.assertIsNone(enemy)

    def test_ce_0087_last_alive_deadline_miss_is_attributed(self) -> None:
        alive = _row(26753, bullets=0)
        alive["action_lag"] = 10
        alive["control_delay_frames"] = 5
        alive["control_delay_candidates"] = [3, 4, 5, 6]
        alive["player"]["phase"] = 0
        alive["player"]["phase_at_action"] = 0
        hit = _row(26759, bullets=0, pipeline=-1.0)
        hit["action_lag"] = 5
        hit["control_delay_frames"] = 5
        hit["control_delay_candidates"] = [3, 4, 5, 6]
        _, contributing, _, _, _ = _classify_death(
            hit,
            window=[alive, hit],
        )
        self.assertIn("action_lag_over_model", contributing)

    def test_action_lag_uses_support_high_not_nominal_delay(self) -> None:
        hit = _row(100, bullets=0, pipeline=-1.0)
        hit["action_lag"] = 6
        hit["control_delay_frames"] = 4
        hit["control_delay_candidates"] = [3, 4, 5, 6]
        _, contributing, _, _, _ = _classify_death(
            hit,
            window=[hit],
        )
        self.assertNotIn("action_lag_over_model", contributing)

    def test_overlap_witness_outranks_closer_nonoverlapping_center(self) -> None:
        row = _row(100)
        row["nearby_bullets"] = [
            [1, 195.0, 405.0, 0.0, 0.0, 1.0, 1.0, 0],
            [2, 200.0, 400.0, 0.0, 0.0, 8.0, 2.0, 0],
        ]
        nearest = _nearest_bullet(row)
        self.assertEqual(nearest["slot"], 2)
        self.assertLessEqual(nearest["aabb_clearance"], 0.0)

    def test_native_laser_overlap_uses_exact_segment_geometry(self) -> None:
        row = _row(100, bullets=0)
        row["active_lasers"] = 1
        row["lasers"] = [[100.0, 400.0, 0.0, 0.0, 200.0, 5.0]]
        nearest = _nearest_laser(row)
        self.assertLessEqual(nearest["clearance"], 0.0)
        primary, _, _, _, _ = _classify_death(row, window=[row])
        self.assertEqual(primary, "observed_laser_overlap")

    def test_projected_enemy_body_overlap_is_not_an_exact_witness(self) -> None:
        row = _row(103, bullets=0)
        row["enemy_body_snapshot_frame"] = 100
        row["active_enemy_bodies"] = 1
        row["enemy_bodies"] = [
            [
                0x5826C0,
                186.0,
                400.0,
                2.0,
                0.0,
                12.0,
                10.0,
                5,
            ]
        ]
        primary, _, _, _, enemy = _classify_death(
            row,
            window=[row],
        )
        self.assertEqual(primary, "sensor_gap_or_unmodeled_hazard")
        self.assertEqual(enemy["projected_x_at_action"], 192.0)
        self.assertFalse(enemy["exact_same_epoch"])
        self.assertLessEqual(enemy["aabb_clearance"], 0.0)

    def test_stable_hit_epoch_enemy_body_overlap_is_exact(self) -> None:
        row = _row(104, bullets=0)
        row["active_enemy_bodies"] = 1
        row["hit_contact_observation"] = {
            "frame_before": 104,
            "frame_after": 104,
            "stable": True,
            "player_lethal_aabb": [190.5, 398.5, 193.5, 401.5],
            "enemy_bodies": [
                [
                    0x5826C0,
                    204.0,
                    400.0,
                    -1.0,
                    0.0,
                    12.0,
                    10.0,
                    5,
                    0.0,
                    -1.0,
                    90.0,
                ]
            ],
        }
        primary, contributing, _, _, enemy = _classify_death(
            row,
            window=[row],
        )
        self.assertEqual(primary, "observed_enemy_body_overlap")
        self.assertTrue(enemy["exact_same_epoch"])
        self.assertLessEqual(enemy["aabb_clearance"], 0.0)
        self.assertFalse(enemy["present_in_action_snapshot"])
        self.assertEqual(enemy["internal_motion_x"], -1.0)
        self.assertEqual(enemy["internal_motion_y"], 90.0)
        self.assertIn(
            "enemy_body_absent_from_action_snapshot",
            contributing,
        )

        row["enemy_body_pointers"] = [0x5826C0]
        _, contributing, _, _, enemy = _classify_death(
            row,
            window=[row],
        )
        self.assertTrue(enemy["present_in_action_snapshot"])
        self.assertNotIn(
            "enemy_body_absent_from_action_snapshot",
            contributing,
        )

    def test_ce_0092_hit_row_visibility_is_not_causal_visibility(self) -> None:
        pointer = 0x5826C0 + 18 * 0x53D0
        alive = _row(35415, bullets=0)
        alive["player"].update({"phase": 0, "phase_at_action": 0})
        alive["enemy_body_pointers"] = [0x5826C0]
        hit = _row(35419, bullets=0)
        hit["enemy_body_pointers"] = [
            0x5826C0 + slot * 0x53D0 for slot in range(19)
        ]
        hit["hit_contact_observation"] = {
            "frame_before": 35420,
            "frame_after": 35420,
            "stable": True,
            "player_lethal_aabb": [316.3, 134.9, 319.3, 137.9],
            "enemy_bodies": [
                [
                    pointer,
                    325.859,
                    128.534,
                    -2.274,
                    2.251,
                    18.0,
                    18.0,
                    5,
                ]
            ],
        }
        _, contributing, _, _, enemy = _classify_death(
            hit,
            window=[alive, hit],
        )
        self.assertTrue(enemy["present_in_hit_decision_snapshot"])
        self.assertFalse(enemy["present_in_causal_snapshot"])
        self.assertFalse(enemy["present_in_action_snapshot"])
        self.assertIn(
            "enemy_body_absent_from_action_snapshot",
            contributing,
        )

    def test_live_spell_attribution_is_gated_by_active_flag(self) -> None:
        row = {
            "spell": {
                "active": True,
                "flags": 5,
                "enemy_pointer": 0x1234,
                "spell_id": 145,
                "name": "禁薬「蓬莱の薬」",
            }
        }
        self.assertEqual(_spell_attribution(row)["spell_id"], 145)
        row["spell"]["active"] = False
        attribution = _spell_attribution(row)
        self.assertEqual(attribution["status"], "no_active_spell_at_hit")
        self.assertIsNone(attribution["spell_id"])

    def test_death_clusters_do_not_cross_stages(self) -> None:
        deaths = [
            {
                "frame": 100,
                "stage_route_index": 0,
                "stage_label": "Stage 1",
                "resources_at_hit": {"power": 10.0},
                "active_bullets": 20,
                "primary_cause_class": "sensor_gap_or_unmodeled_hazard",
            },
            {
                "frame": 500,
                "stage_route_index": 0,
                "stage_label": "Stage 1",
                "resources_at_hit": {"power": 8.0},
                "active_bullets": 30,
                "primary_cause_class": "sensor_gap_or_unmodeled_hazard",
            },
            {
                "frame": 550,
                "stage_route_index": 1,
                "stage_label": "Stage 2",
                "resources_at_hit": {"power": 7.0},
                "active_bullets": 40,
                "primary_cause_class": "observed_bullet_overlap",
            },
        ]
        clusters = _death_clusters(deaths)
        self.assertEqual([cluster["death_count"] for cluster in clusters], [2, 1])
        self.assertEqual(clusters[0]["minimum_power"], 8.0)


if __name__ == "__main__":
    unittest.main()
