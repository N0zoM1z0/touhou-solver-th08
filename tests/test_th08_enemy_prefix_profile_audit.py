from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.th08_enemy_prefix_profile_audit import audit_trace
from th08_live.enemy_sensor import ENEMY_SLOT_ZERO_BASE, ENEMY_STRIDE


class EnemyPrefixProfileAuditTests(unittest.TestCase):
    def test_reports_slot_watermark_without_overclaiming_raw_occupancy(self) -> None:
        rows = (
            {"kind": "identity"},
            {
                "kind": "decision",
                "enemy_bodies": [
                    [ENEMY_SLOT_ZERO_BASE, 0, 0, 0, 0, 1, 1, 5],
                    [
                        ENEMY_SLOT_ZERO_BASE + 64 * ENEMY_STRIDE,
                        0,
                        0,
                        0,
                        0,
                        1,
                        1,
                        5,
                    ],
                ],
                "timing_ms": {
                    "read_enemy_pool": 90.0,
                    "read_enemy_prefix_capture": 2.5,
                },
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "trace.jsonl"
            trace.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            report = audit_trace(trace)

        self.assertEqual(report["decision_rows"], 1)
        self.assertEqual(report["maximum_native_slot_observed"], 64)
        self.assertEqual(report["outside_slot_zero_to_63_rows"], 1)
        self.assertEqual(report["rows_with_native_slot_zero"], 1)
        self.assertIn("cannot prove", report["evidence_boundary"])


if __name__ == "__main__":
    unittest.main()
