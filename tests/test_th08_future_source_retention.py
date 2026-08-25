from __future__ import annotations

import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tests.test_th08_ordinary_future_sources import ECL, _payload
from th08_ordinary_future_sources import project_ordinary_future_sources
from th08_runtime.future_source_retention import (
    FutureSourceRetentionExpectation,
    RETAINED_FUTURE_SOURCE_ROOT_SCHEMA,
    read_retained_future_source_root,
    write_retained_future_source_root,
)
from th08_runtime.ordinary_future_source_capture import (
    ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
    OrdinaryFutureSourceSnapshot,
    capture_and_project_ordinary_future_sources,
)


def _root() -> tuple[OrdinaryFutureSourceSnapshot, object]:
    payload = deepcopy(_payload())
    payload["compact_state"].update(
        route_id=2,
        difficulty_index=3,
        stage_route_index=5,
        spell_id=103,
        bomb_active=0,
    )
    closure = project_ordinary_future_sources(
        payload,
        ECL,
        horizon_frames=1,
    )
    snapshot = OrdinaryFutureSourceSnapshot(
        frame_before=2129,
        frame_after=2129,
        update_serial_before=41,
        update_serial_after=41,
        payload=payload,
        read_ms=9.0,
        attempts=1,
    )
    return snapshot, closure


def _expectation() -> FutureSourceRetentionExpectation:
    return FutureSourceRetentionExpectation(
        route_id=2,
        difficulty_index=3,
        stage_route_index=5,
        spell_id=103,
    )


class FutureSourceRetentionTests(unittest.TestCase):
    def test_root_is_canonical_content_addressed_and_deduplicated(self) -> None:
        snapshot, closure = _root()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            first = write_retained_future_source_root(
                snapshot,
                closure,
                destination,
                snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
                requested_horizon_frames=1,
            )
            second = write_retained_future_source_root(
                snapshot,
                closure,
                destination,
                snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
                requested_horizon_frames=1,
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.path, second.path)
            self.assertIn(first.sha256, first.path.name)
            self.assertEqual(first.path.read_bytes()[9], 255)
            retained = read_retained_future_source_root(first.path)
            self.assertEqual(
                retained["schema"],
                RETAINED_FUTURE_SOURCE_ROOT_SCHEMA,
            )
            self.assertEqual(retained["root_identity"]["route_id"], 2)
            self.assertEqual(retained["root_identity"]["spell_id"], 103)
            self.assertEqual(
                retained["root_payload"]["compact_state"]["rng_state"],
                1,
            )

    def test_filename_digest_is_verified_before_replay(self) -> None:
        snapshot, closure = _root()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            artifact = write_retained_future_source_root(
                snapshot,
                closure,
                destination,
                snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
                requested_horizon_frames=1,
            )
            wrong = destination / (
                f"sha256-{'0' * 64}.th08-future-root.json.gz"
            )
            shutil.copyfile(artifact.path, wrong)

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                read_retained_future_source_root(wrong)

    def test_observer_timing_does_not_change_root_identity(self) -> None:
        snapshot, closure = _root()
        slower = OrdinaryFutureSourceSnapshot(
            frame_before=snapshot.frame_before,
            frame_after=snapshot.frame_after,
            update_serial_before=snapshot.update_serial_before,
            update_serial_after=snapshot.update_serial_after,
            payload=snapshot.payload,
            read_ms=999.0,
            attempts=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            first = write_retained_future_source_root(
                snapshot,
                closure,
                destination,
                snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
                requested_horizon_frames=1,
            )
            second = write_retained_future_source_root(
                slower,
                closure,
                destination,
                snapshot_schema=ORDINARY_FUTURE_SOURCE_SNAPSHOT_SCHEMA,
                requested_horizon_frames=1,
            )

            self.assertEqual(first.sha256, second.sha256)

    def test_capture_worker_persists_before_returning_result(self) -> None:
        snapshot, closure = _root()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "capture_ordinary_future_source_snapshot",
                return_value=snapshot,
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "project_ordinary_future_sources",
                return_value=closure,
            ),
        ):
            result = capture_and_project_ordinary_future_sources(
                object(),
                ECL,
                horizon_frames=1,
                retain_dir=Path(directory),
                retention_expectation=_expectation(),
            )
            self.assertIsNotNone(result.retained_root)
            assert result.retained_root is not None
            self.assertTrue(result.retained_root.path.is_file())
            self.assertEqual(result.retained_root.spell_id, 103)
            self.assertIsNone(result.retention_rejection_reason)

    def test_async_phase_transition_does_not_write_or_consume_a_root(self) -> None:
        snapshot, closure = _root()
        payload = deepcopy(snapshot.payload)
        payload["compact_state"]["player_phase"] = 3
        transitioned = OrdinaryFutureSourceSnapshot(
            frame_before=snapshot.frame_before,
            frame_after=snapshot.frame_after,
            update_serial_before=snapshot.update_serial_before,
            update_serial_after=snapshot.update_serial_after,
            payload=payload,
            read_ms=snapshot.read_ms,
            attempts=snapshot.attempts,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "capture_ordinary_future_source_snapshot",
                return_value=transitioned,
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "project_ordinary_future_sources",
                return_value=closure,
            ),
        ):
            destination = Path(directory)
            result = capture_and_project_ordinary_future_sources(
                object(),
                ECL,
                horizon_frames=1,
                retain_dir=destination,
                retention_expectation=_expectation(),
            )

            self.assertIsNone(result.retained_root)
            self.assertEqual(
                result.retention_rejection_reason,
                "captured_player_phase_mismatch:expected=0,actual=3",
            )
            self.assertEqual(list(destination.iterdir()), [])

    def test_async_context_change_is_rejected_before_persistence(self) -> None:
        snapshot, closure = _root()
        payload = deepcopy(snapshot.payload)
        payload["compact_state"]["spell_id"] = 107
        changed = OrdinaryFutureSourceSnapshot(
            frame_before=snapshot.frame_before,
            frame_after=snapshot.frame_after,
            update_serial_before=snapshot.update_serial_before,
            update_serial_after=snapshot.update_serial_after,
            payload=payload,
            read_ms=snapshot.read_ms,
            attempts=snapshot.attempts,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "capture_ordinary_future_source_snapshot",
                return_value=changed,
            ),
            patch(
                "th08_runtime.ordinary_future_source_capture."
                "project_ordinary_future_sources",
                return_value=closure,
            ),
        ):
            result = capture_and_project_ordinary_future_sources(
                object(),
                ECL,
                horizon_frames=1,
                retain_dir=Path(directory),
                retention_expectation=_expectation(),
            )

            self.assertIsNone(result.retained_root)
            self.assertEqual(
                result.retention_rejection_reason,
                "captured_spell_id_mismatch:expected=103,actual=107",
            )


if __name__ == "__main__":
    unittest.main()
