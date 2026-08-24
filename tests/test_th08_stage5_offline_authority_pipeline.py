from __future__ import annotations

import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

from th08_ecl_tool.core import parse_ecl
from th08_live.runtime_ecl_identity import (
    RuntimeEclIdentityDependencies,
    RuntimeEclIdentityService,
    RuntimeEclPhysicalProvenance,
)
from th08_live.runtime_ecl_image import (
    ECL_SUBROUTINE_TABLE_OFFSET,
    RuntimeEclImageCapture,
    RuntimeEclImageIdentity,
)
from th08_live.scale_schedule_authority import (
    NoScaleWriterAuthorityDependencies,
    NoScaleWriterScheduleAuthority,
    audit_no_scale_writer_ecl,
)
from th08_runtime.game_state import EXPECTED_EXE_SHA256
from th08_stage_ecl_catalog import (
    NO_SCALE_WRITER_STAGE_ROUTE_INDICES,
    PRACTICE_STAGE_ECL_IDENTITIES,
    ROUTE_STAGE_ECL_IDENTITIES,
    SCALE_MODEL_NO_WRITER,
)
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS


ROOT = Path(__file__).resolve().parents[1]
DECODED = ROOT / "artifacts" / "decoded"


class _TraceSink:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def emit(
        self,
        record: dict[str, object],
        *,
        flush: bool,
        measure: bool,
    ) -> float:
        self.records.append(record)
        self.assertions = (flush, measure)
        return 0.0


class _Stage5SourceCapture:
    status = "coherent"
    coherent = True

    def __init__(self, *, runtime_base: int) -> None:
        self.phase_before = SimpleNamespace(
            gameplay_active=True,
            route_id=2,
            difficulty_index=3,
            stage_route_index=5,
            ecl_context=struct.pack(
                "<II",
                runtime_base,
                runtime_base + ECL_SUBROUTINE_TABLE_OFFSET,
            ),
            scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            player_bomb_active=0,
        )
        self.sources = (
            SimpleNamespace(snapshot=object(), installed_callback=0),
        )

    def compact_record(self) -> dict[str, object]:
        return {"status": self.status, "source_count": len(self.sources)}


class Stage5OfflineAuthorityPipelineTests(unittest.TestCase):
    def test_catalog_hashes_and_no_writer_claims_match_decoded_images(self) -> None:
        for catalog in (
            ROUTE_STAGE_ECL_IDENTITIES,
            PRACTICE_STAGE_ECL_IDENTITIES,
        ):
            for identity in catalog.values():
                image = DECODED / identity.filename
                self.assertEqual(
                    hashlib.sha256(image.read_bytes()).hexdigest(),
                    identity.sha256,
                )
                self.assertEqual(
                    audit_no_scale_writer_ecl(parse_ecl(image)).eligible,
                    identity.scale_model == SCALE_MODEL_NO_WRITER,
                )

        self.assertEqual(
            ROUTE_STAGE_ECL_IDENTITIES["5"].filename,
            "ecldata5.ecl",
        )
        self.assertEqual(
            PRACTICE_STAGE_ECL_IDENTITIES["5"].filename,
            "ecldata5sp.ecl",
        )
        self.assertNotEqual(
            ROUTE_STAGE_ECL_IDENTITIES["5"].sha256,
            PRACTICE_STAGE_ECL_IDENTITIES["5"].sha256,
        )

        self.assertEqual(
            NO_SCALE_WRITER_STAGE_ROUTE_INDICES,
            frozenset({0, 1, 2, 3, 4, 5}),
        )

    def test_first_stage5_preplan_root_unlocks_exact_unit_schedule(self) -> None:
        identity = PRACTICE_STAGE_ECL_IDENTITIES["5"]
        static_path = DECODED / identity.filename
        static_image = static_path.read_bytes()
        runtime_base = 0x02100000
        capture = RuntimeEclImageCapture(
            runtime_base=runtime_base,
            image_length=len(static_image),
            subroutine_count=1,
            timeline_count=1,
            relocated_sha256="1" * 64,
            normalized_sha256=identity.sha256,
            capture_ms=0.0,
            read_count=1,
            relocated_image=static_image,
            normalized_image=static_image,
        )
        exact = RuntimeEclImageIdentity(
            exact_match=True,
            static_sha256=identity.sha256,
            normalized_runtime_sha256=identity.sha256,
            image_length=len(static_image),
            first_difference_offset=None,
        )
        ticks = iter((1.0, 1.0))
        identity_service = RuntimeEclIdentityService(
            static_image=static_image,
            static_label=identity.filename,
            expected_static_sha256=identity.sha256,
            expected_route_id=2,
            expected_difficulty_index=3,
            expected_stage_route_index=5,
            dependencies=RuntimeEclIdentityDependencies(
                capture=lambda *_args, **_kwargs: capture,
                compare=lambda *_args, **_kwargs: exact,
                clock=lambda: next(ticks),
            ),
        )
        trace_sink = _TraceSink()
        identity_service.observe_if_due(
            SimpleNamespace(),  # type: ignore[arg-type]
            trace_sink,  # type: ignore[arg-type]
            provenance=RuntimeEclPhysicalProvenance(
                pid=1234,
                executable_sha256=EXPECTED_EXE_SHA256,
                route_id=2,
                difficulty_index=3,
                stage_route_index=5,
                gameplay_epoch=9,
                decision_frame=120,
                snapshot_frame=75,
                gameplay_active=True,
            ),
        )
        expected_manager_frames: list[int] = []

        def capture_sources(
            _reader: object,
            *,
            expected_manager_frame: int,
        ) -> _Stage5SourceCapture:
            expected_manager_frames.append(expected_manager_frame)
            return _Stage5SourceCapture(runtime_base=runtime_base)

        ecl = parse_ecl(static_path)
        authority = NoScaleWriterScheduleAuthority(
            ecl,
            expected_static_sha256=identity.sha256,
            expected_route_id=2,
            expected_difficulty_index=3,
            expected_stage_route_index=5,
            horizon_frames=269,
            dependencies=NoScaleWriterAuthorityDependencies(
                capture_sources=capture_sources,
            ),
        )
        resolution = authority.resolve(
            SimpleNamespace(),
            runtime_version=identity_service.accepted_version,
            source_frame=120,
            expected_manager_frame=75,
            gameplay_epoch=9,
            route_id=2,
            difficulty_index=3,
            stage_route_index=5,
            observed_root_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
            observed_player_bomb_active=0,
        )

        self.assertIsNotNone(identity_service.accepted_version)
        self.assertTrue(resolution.planner_scale_authority)
        self.assertEqual(resolution.schedule.source_frame, 120)
        self.assertEqual(resolution.schedule.complete_horizon, 269)
        self.assertEqual(expected_manager_frames, [75])
        self.assertEqual(trace_sink.records[0]["status"], "exact_match")


if __name__ == "__main__":
    unittest.main()
