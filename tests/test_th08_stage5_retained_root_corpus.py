from __future__ import annotations

import json
from pathlib import Path
import unittest

from th08_runtime.future_source_retention import (
    read_retained_future_source_root,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = (
    ROOT
    / "artifacts"
    / "runtime_reports"
    / "lunatic_route2_stage5_unattended_20260825_011207.root"
)
EXPECTED_ECL_SHA256 = (
    "3148f45faf78bd8211a956edcdc353be73d2781995d3dadd36bdca8132f8fe19"
)


class Stage5RetainedRootCorpusTests(unittest.TestCase):
    def test_manifest_and_content_addressed_capsules_agree(self) -> None:
        manifest = json.loads(
            (CORPUS / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["schema"],
            "th08-stage5-retained-future-root-corpus-v1",
        )
        self.assertEqual(manifest["route_id"], 2)
        self.assertEqual(manifest["difficulty_index"], 3)
        self.assertEqual(manifest["stage_route_index"], 5)
        self.assertEqual(
            manifest["runtime_ecl_canonical_sha256"],
            EXPECTED_ECL_SHA256,
        )

        records: dict[int, tuple[dict[str, object], dict[str, object]]] = {}
        for row in manifest["capsules"]:
            digest = row["content_sha256"]
            path = CORPUS / (
                f"sha256-{digest}.th08-future-root.json.gz"
            )
            record = read_retained_future_source_root(path)
            identity = record["root_identity"]
            projection = record["projection_at_capture"]
            self.assertEqual(identity["route_id"], manifest["route_id"])
            self.assertEqual(
                identity["difficulty_index"],
                manifest["difficulty_index"],
            )
            self.assertEqual(
                identity["stage_route_index"],
                manifest["stage_route_index"],
            )
            self.assertEqual(
                identity["runtime_ecl_canonical_sha256"],
                EXPECTED_ECL_SHA256,
            )
            self.assertEqual(identity["spell_id"], row["spell_id"])
            self.assertEqual(identity["manager_frame"], row["manager_frame"])
            self.assertEqual(
                record["root_payload"]["compact_state"]["player_phase"],
                row["player_phase"],
            )
            self.assertEqual(
                projection["direct_fire_event_count"],
                row["initial_direct_fire_events"],
            )
            self.assertEqual(
                projection["source_closure_reason"],
                row["initial_source_closure_reason"],
            )
            self.assertEqual(
                projection["causal_prefix_reason"],
                row["causal_prefix_reason"],
            )
            records[int(row["spell_id"])] = (row, record)

        self.assertEqual(set(records), {103, 107, 111, 115})
        self.assertEqual(
            {
                spell_id
                for spell_id, (row, _record) in records.items()
                if row["planner_root_eligible"]
            },
            {103, 115},
        )
        for spell_id in (107, 111):
            self.assertEqual(records[spell_id][0]["player_phase"], 3)


if __name__ == "__main__":
    unittest.main()
