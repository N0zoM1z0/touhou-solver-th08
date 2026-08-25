from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from th08_ecl_callback_model import CALLBACK_ADDRESSES  # noqa: E402
from th08_ecl_runtime import ENEMY_MAIN_ECL_VM_OFFSET  # noqa: E402
from th08_live.enemy_ecl_inventory import (  # noqa: E402
    ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
)
from th08_live.enemy_sensor import (  # noqa: E402
    ENEMY_FLAGS_OFFSET,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_STRIDE,
)
from th08_live.runtime_ecl_image import (  # noqa: E402
    ECL_FILE_CONTEXT_ADDRESS,
)
from th08_live.scale_source_trace import (  # noqa: E402
    FINAL_B_ECL_STATIC_SHA256,
    FINAL_B_QUARTER_SCALE_BITS,
    FinalBScaleSourceTraceConfiguration,
    FinalBScaleSourceTraceService,
    decode_scale_vm_source,
    final_b_scale_spell_id,
)
from th08_runtime.game_state import (  # noqa: E402
    ADDR_DIFFICULTY_INDEX,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_ENGINE_FLAGS,
    ADDR_GAMEPLAY_TIME_SCALE,
    ADDR_PLAYER,
    ADDR_ROUTE_ID,
    ADDR_SPELL_CARD_STATE,
    ADDR_STAGE_ROUTE_INDEX,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_PREDEATH_COUNTER_OFFSET,
    SPELL_STATE_CAPTURE_SIZE,
)


STATIC_PATH = ROOT / "artifacts" / "decoded" / "ecldata7.ecl"
RUNTIME_BASE = 0x02100000
OUTSIDE_SPELL_OWNER = 0x03000000


def _relocate_static_ecl(static: bytes, runtime_base: int) -> bytes:
    relocated = bytearray(static)
    _magic, subroutine_count, _timeline_count = struct.unpack_from(
        "<IHH",
        static,
    )
    for index in range(16):
        offset = 0x08 + 4 * index
        value = struct.unpack_from("<I", static, offset)[0]
        struct.pack_into("<I", relocated, offset, runtime_base + value)
    for index in range(subroutine_count):
        offset = 0x48 + 4 * index
        value = struct.unpack_from("<I", static, offset)[0]
        struct.pack_into("<I", relocated, offset, runtime_base + value)
    return bytes(relocated)


def _source_record(
    *,
    installed_callback: int = 0,
    auxiliary: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    record = bytearray(ENEMY_STRIDE)
    struct.pack_into("<I", record, ENEMY_FLAGS_OFFSET, 0x00000005)
    struct.pack_into(
        "<4I",
        record,
        ENEMY_AUXILIARY_ECL_CONTEXT_POINTERS_OFFSET,
        *auxiliary,
    )
    vm = ENEMY_MAIN_ECL_VM_OFFSET
    struct.pack_into("<I", record, vm, RUNTIME_BASE + 0x5C90)
    struct.pack_into(
        "<II",
        record,
        vm + 0x10,
        installed_callback,
        0x02105C44,
    )
    struct.pack_into("<I", record, vm + 0x08, 0)
    struct.pack_into("<i", record, vm + 0x0C, 1)
    struct.pack_into("<8i", record, vm + 0x18, 6, 0, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<8I", record, vm + 0x38, *([0] * 8))
    struct.pack_into("<4i", record, vm + 0x58, 6, 0, 0, 0)
    return bytes(record)


class _Reader:
    def __init__(
        self,
        *,
        installed_callback: int = 0,
        auxiliary: tuple[int, int, int, int] = (0, 0, 0, 0),
        outside_spell_owner: bool = False,
        difficulty_index: int = 3,
        spell_id: int = 190,
    ) -> None:
        static = STATIC_PATH.read_bytes()
        self.relocated = _relocate_static_ecl(static, RUNTIME_BASE)
        pool = bytearray(ENEMY_POOL_SIZE * ENEMY_STRIDE)
        source = _source_record(
            installed_callback=installed_callback,
            auxiliary=auxiliary,
        )
        if not outside_spell_owner:
            pool[: len(source)] = source
        self.pool = bytes(pool)
        self.external_source = source if outside_spell_owner else None
        spell_owner = (
            OUTSIDE_SPELL_OWNER
            if outside_spell_owner
            else ENEMY_POOL_BASE
        )
        spell = bytearray(SPELL_STATE_CAPTURE_SIZE)
        struct.pack_into(
            "<III",
            spell,
            0,
            0x825,
            spell_owner,
            spell_id,
        )
        struct.pack_into("<i", spell, 0x110, 120)
        self.fixed = {
            ADDR_ENEMY_MANAGER_FRAME: struct.pack("<I", 100),
            ADDR_ROUTE_ID: b"\x02",
            ADDR_DIFFICULTY_INDEX: struct.pack("<I", difficulty_index),
            ADDR_STAGE_ROUTE_INDEX: struct.pack("<I", 7),
            ADDR_ENGINE_FLAGS: struct.pack("<I", 4),
            ADDR_SPELL_CARD_STATE: bytes(spell),
            ECL_FILE_CONTEXT_ADDRESS: struct.pack(
                "<II",
                RUNTIME_BASE,
                RUNTIME_BASE + 0x48,
            ),
            ADDR_GAMEPLAY_TIME_SCALE: struct.pack(
                "<I",
                FINAL_B_QUARTER_SCALE_BITS,
            ),
            ADDR_PLAYER: b"\x03",
            ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET: struct.pack("<I", 0),
            ADDR_PLAYER + PLAYER_PREDEATH_COUNTER_OFFSET: struct.pack(
                "<i",
                7,
            ),
        }

    def read(self, address: int, size: int) -> bytes:
        if address == ENEMY_MANAGER_TEMPLATE_BASE:
            return bytes(size)
        if address == ENEMY_POOL_BASE:
            return self.pool[:size]
        if (
            address == OUTSIDE_SPELL_OWNER
            and self.external_source is not None
        ):
            return self.external_source[:size]
        if RUNTIME_BASE <= address < RUNTIME_BASE + len(self.relocated):
            offset = address - RUNTIME_BASE
            return self.relocated[offset : offset + size]
        blob = self.fixed.get(address)
        if blob is None:
            raise OSError(f"unmapped test read {address:#x}+{size:#x}")
        return blob[:size]


class _BufferedReader(_Reader):
    def __init__(self) -> None:
        super().__init__()
        self.allocated_sizes: list[int] = []
        self.read_into_calls = 0

    def allocate_buffer(self, size: int) -> bytearray:
        self.allocated_sizes.append(size)
        return bytearray(size)

    def read_into(self, address: int, buffer: bytearray) -> bytearray:
        self.read_into_calls += 1
        buffer[:] = self.read(address, len(buffer))
        return buffer


class ScaleSourceTraceTests(unittest.TestCase):
    def _service(
        self,
        difficulty_index: int = 3,
    ) -> FinalBScaleSourceTraceService:
        return FinalBScaleSourceTraceService(
            FinalBScaleSourceTraceConfiguration(
                static_path=STATIC_PATH,
                expected_static_sha256=FINAL_B_ECL_STATIC_SHA256,
                expected_difficulty_index=difficulty_index,
            )
        )

    def _observe(
        self,
        reader: _Reader,
        *,
        difficulty_index: int = 3,
    ) -> dict[str, object]:
        record = self._service(difficulty_index).observe_if_due(
            reader,
            decision_frame=101,
            expected_manager_frame=100,
            gameplay_epoch=4,
            route_id=2,
            difficulty_index=difficulty_index,
            stage_route_index=7,
            spell_id=final_b_scale_spell_id(difficulty_index),
            observed_root_scale_bits=FINAL_B_QUARTER_SCALE_BITS,
            observed_player_bomb_active=0,
        )
        assert record is not None
        return record

    def test_exact_full_pool_singleton_produces_complete_trace(self) -> None:
        record = self._observe(_Reader())

        self.assertEqual(
            record["status"],
            "accepted_complete_source_trace",
        )
        self.assertEqual(record["incomplete_reasons"], [])
        self.assertFalse(record["hard_action_authority"])
        self.assertFalse(record["changes_input"])
        identity = record["runtime_ecl_identity"]
        assert isinstance(identity, dict)
        self.assertTrue(identity["exact_match"])
        capture = record["source_capture"]
        assert isinstance(capture, dict)
        self.assertTrue(capture["ordinary_pool_complete"])
        self.assertEqual(capture["ordinary_pool_slots_scanned"], 480)
        self.assertEqual(capture["source_count"], 1)
        phase = capture["phase_before"]
        assert isinstance(phase, dict)
        self.assertEqual(phase["player_predeath_counter"], 7)
        schedule = record["schedule"]
        assert isinstance(schedule, dict)
        self.assertEqual(schedule["complete_horizon"], 300)
        self.assertEqual(schedule["stop_reason"], "horizon")
        self.assertEqual(schedule["bullet_velocity_rescale_frames"], [])
        writes = schedule["writes"]
        assert isinstance(writes, list)
        self.assertEqual(
            [
                (
                    write["frame"],
                    write["callback_index"],
                    write["scale_bits_after"],
                )
                for write in writes
            ],
            [(237, 18, 0x3F800000)],
        )

    def test_all_main_difficulties_share_the_exact_scale_program(self) -> None:
        for difficulty_index in range(4):
            with self.subTest(difficulty_index=difficulty_index):
                spell_id = final_b_scale_spell_id(difficulty_index)
                record = self._observe(
                    _Reader(
                        difficulty_index=difficulty_index,
                        spell_id=spell_id,
                    ),
                    difficulty_index=difficulty_index,
                )
                self.assertEqual(
                    record["status"],
                    "accepted_complete_source_trace",
                )
                self.assertEqual(record["spell_id"], spell_id)

    def test_runtime_pool_buffer_is_allocated_once_and_reused(self) -> None:
        reader = _BufferedReader()
        record = self._observe(reader)

        self.assertEqual(
            record["status"],
            "accepted_complete_source_trace",
        )
        self.assertEqual(
            reader.allocated_sizes,
            [ENEMY_POOL_SIZE * ENEMY_STRIDE],
        )
        self.assertEqual(reader.read_into_calls, 1)

    def test_installed_scale_callback_fails_closed(self) -> None:
        record = self._observe(
            _Reader(installed_callback=CALLBACK_ADDRESSES[18])
        )

        self.assertEqual(record["status"], "unknown")
        self.assertIn(
            "installed_scale_callback_present",
            record["incomplete_reasons"],
        )
        self.assertIsNone(record["schedule"])

    def test_out_of_pool_spell_owner_is_captured_as_complete_source(
        self,
    ) -> None:
        record = self._observe(_Reader(outside_spell_owner=True))

        self.assertEqual(
            record["status"],
            "accepted_complete_source_trace",
        )
        capture = record["source_capture"]
        assert isinstance(capture, dict)
        self.assertFalse(capture["spell_owner_in_ordinary_pool"])
        self.assertEqual(capture["ordinary_active_slots"], 0)
        sources = capture["sources"]
        assert isinstance(sources, list)
        self.assertEqual(
            sources[0]["role"],
            "spell_owner_outside_ordinary_pool",
        )
        self.assertEqual(
            sources[0]["enemy_pointer"],
            OUTSIDE_SPELL_OWNER,
        )

    def test_non_null_auxiliary_context_fails_closed(self) -> None:
        record = self._observe(_Reader(auxiliary=(0x02200000, 0, 0, 0)))

        self.assertEqual(record["status"], "unknown")
        self.assertIn(
            "auxiliary_context_present",
            record["incomplete_reasons"],
        )
        self.assertIsNone(record["schedule"])

    def test_trigger_is_exact_and_one_shot(self) -> None:
        service = self._service()
        reader = _Reader()
        self.assertIsNone(
            service.observe_if_due(
                reader,
                decision_frame=1,
                expected_manager_frame=100,
                gameplay_epoch=0,
                route_id=2,
                difficulty_index=3,
                stage_route_index=7,
                spell_id=189,
                observed_root_scale_bits=FINAL_B_QUARTER_SCALE_BITS,
                observed_player_bomb_active=0,
            )
        )
        self.assertFalse(service.attempted)
        self.assertIsNone(
            service.observe_if_due(
                reader,
                decision_frame=2,
                expected_manager_frame=100,
                gameplay_epoch=0,
                route_id=2,
                difficulty_index=3,
                stage_route_index=7,
                spell_id=190,
                observed_root_scale_bits=0x3F800000,
                observed_player_bomb_active=0,
            )
        )
        self.assertFalse(service.attempted)
        self.assertIsNotNone(
            service.observe_if_due(
                reader,
                decision_frame=3,
                expected_manager_frame=100,
                gameplay_epoch=0,
                route_id=2,
                difficulty_index=3,
                stage_route_index=7,
                spell_id=190,
                observed_root_scale_bits=FINAL_B_QUARTER_SCALE_BITS,
                observed_player_bomb_active=0,
            )
        )
        self.assertTrue(service.attempted)
        self.assertIsNotNone(service.accepted_schedule)
        self.assertIsNone(
            service.observe_if_due(
                reader,
                decision_frame=4,
                expected_manager_frame=100,
                gameplay_epoch=0,
                route_id=2,
                difficulty_index=3,
                stage_route_index=7,
                spell_id=190,
                observed_root_scale_bits=FINAL_B_QUARTER_SCALE_BITS,
                observed_player_bomb_active=0,
            )
        )
        service.reset()
        self.assertFalse(service.attempted)
        self.assertIsNone(service.accepted_schedule)

    def test_decoder_retains_installed_callback_record(self) -> None:
        source = decode_scale_vm_source(
            _source_record(installed_callback=CALLBACK_ADDRESSES[2]),
            role="ordinary_pool",
            slot=0,
            enemy_pointer=ENEMY_POOL_BASE,
            scale_bits=FINAL_B_QUARTER_SCALE_BITS,
        )

        self.assertEqual(source.installed_callback_index, 2)
        self.assertEqual(source.installed_callback_record, 0x02105C44)
        self.assertIsNone(source.invalid_reason)
        self.assertIsNotNone(source.snapshot)

    def test_decoder_does_not_treat_enemy_base_plus_10_as_vm_callback(
        self,
    ) -> None:
        record = bytearray(_source_record())
        struct.pack_into("<II", record, 0x10, CALLBACK_ADDRESSES[18], 0)

        source = decode_scale_vm_source(
            bytes(record),
            role="ordinary_pool",
            slot=0,
            enemy_pointer=ENEMY_POOL_BASE,
            scale_bits=FINAL_B_QUARTER_SCALE_BITS,
        )

        self.assertEqual(source.installed_callback, 0)
        self.assertIsNone(source.installed_callback_index)

    def test_wrong_static_digest_is_rejected_before_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "digest"):
            FinalBScaleSourceTraceService(
                FinalBScaleSourceTraceConfiguration(
                    static_path=STATIC_PATH,
                    expected_static_sha256="0" * 64,
                )
            )


if __name__ == "__main__":
    unittest.main()
