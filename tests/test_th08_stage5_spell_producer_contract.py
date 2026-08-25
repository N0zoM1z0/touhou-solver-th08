from __future__ import annotations

from pathlib import Path
import unittest

from analysis.th08_stage5_spell_producer_contract import build_report


ROOT = Path(__file__).resolve().parents[1]
DECODED = ROOT / "artifacts" / "decoded"


class Stage5SpellProducerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_report(DECODED)

    def test_route_and_spell_practice_programs_are_source_equivalent(self) -> None:
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["route"]["spell_ids"],
            [103, 107, 111, 115, 118],
        )
        self.assertEqual(
            report["shared_spell_ids"],
            [103, 107, 111, 115, 118],
        )
        self.assertTrue(
            all(
                row["equivalent"]
                for row in report[
                    "route_spell_practice_equivalence"
                ].values()
            )
        )
        self.assertEqual(
            report["spell_practice"]["filename"],
            "ecldata5sp.ecl",
        )

    def test_observed_spell_roots_and_timeouts_are_exact(self) -> None:
        expected = {
            103: (62, 3000, 53),
            107: (66, 4620, 56),
            111: (63, 3000, 87),
            115: (75, 3000, 53),
        }
        programs = self.report["route"]["programs"]
        for spell_id, values in expected.items():
            root, timeout, successor = values
            with self.subTest(spell_id=spell_id):
                program = programs[str(spell_id)]
                self.assertEqual(program["root_subroutine"], root)
                self.assertEqual(program["timeout_frames"], timeout)
                self.assertEqual(
                    program["timeout_successor_subroutine"],
                    successor,
                )
                self.assertFalse(program["dynamic_subroutine_edges"])

    def test_producer_families_expose_current_solver_boundaries(self) -> None:
        programs = self.report["route"]["programs"]
        expected_counts = {
            103: (6, 0, 1),
            107: (3, 3, 3),
            111: (3, 0, 13),
            115: (6, 3, 2),
        }
        for spell_id, counts in expected_counts.items():
            with self.subTest(spell_id=spell_id):
                site_counts = programs[str(spell_id)]["site_counts"]
                self.assertEqual(
                    (
                        site_counts["direct_fire"],
                        site_counts["transform"],
                        site_counts["child_spawn"],
                    ),
                    counts,
                )

        spell103 = programs["103"]
        self.assertIn("callback_invoke_12", spell103["required_lowering_families"])
        spell115 = programs["115"]
        self.assertIn("callback_invoke_14", spell115["required_lowering_families"])
        self.assertIn("bullet_transform", spell115["required_lowering_families"])

    def test_report_is_deterministic(self) -> None:
        self.assertEqual(self.report, build_report(DECODED))


if __name__ == "__main__":
    unittest.main()
