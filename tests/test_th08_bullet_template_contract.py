from __future__ import annotations

from pathlib import Path
import unittest

from th08_bullet_template_contract import (
    BULLET_MANAGER_BASE,
    BULLET_TEMPLATE_COUNT,
    BULLET_TEMPLATE_GEOMETRY_SCHEMA,
    BULLET_TEMPLATE_PROFILES,
    BULLET_TEMPLATE_STRIDE,
    ETAMA_DECODED_SHA256,
    BulletTemplateContractError,
    bullet_spawn_lifecycle_for_state,
    bullet_template_profile,
    bullet_type_from_normal_script,
    fallback_geometry_from_observed_prefix,
    pinned_contract_payload,
    verify_decoded_etama,
)
from th08_pbgz import PbgzArchive
from th08_resource import decode_resource


REPO_ROOT = Path(__file__).resolve().parents[1]
GAME_ARCHIVE = (
    REPO_ROOT.parent
    / "game_exe"
    / "extracted"
    / "[th08] 东方永夜抄 (日文版)"
    / "th08.dat"
)


def _observed_prefix() -> dict[str, object]:
    return {
        "schema": BULLET_TEMPLATE_GEOMETRY_SCHEMA,
        "manager_base": BULLET_MANAGER_BASE,
        "template_stride": BULLET_TEMPLATE_STRIDE,
        "rows": [
            {
                "type": profile.bullet_type,
                "width": profile.half_width * 2.0,
                "height": profile.half_height * 2.0,
                "half_width": profile.half_width,
                "half_height": profile.half_height,
                "collision_z": 0.0,
            }
            for profile in BULLET_TEMPLATE_PROFILES[:16]
        ],
    }


class BulletTemplateContractTests(unittest.TestCase):
    def test_source_initialized_table_has_all_21_generic_types(self) -> None:
        self.assertEqual(BULLET_TEMPLATE_COUNT, 21)
        self.assertEqual(
            tuple(profile.bullet_type for profile in BULLET_TEMPLATE_PROFILES),
            tuple(range(21)),
        )
        self.assertEqual(
            (bullet_template_profile(16).half_width,
             bullet_template_profile(20).half_height),
            (2.0, 2.5),
        )
        self.assertEqual(
            (
                bullet_template_profile(2).cull_half_width,
                bullet_template_profile(10).cull_half_height,
                bullet_template_profile(14).cull_half_height,
            ),
            (7.0, 32.0, 15.5),
        )

    def test_lifecycle_ages_are_selected_by_type_not_one_global_age(self) -> None:
        self.assertEqual(bullet_template_profile(0).state2_terminal_age, 10)
        self.assertEqual(bullet_template_profile(7).state2_terminal_age, 30)
        self.assertEqual(bullet_template_profile(10).state2_terminal_age, 24)
        self.assertEqual(bullet_template_profile(1).state3_terminal_age, 15)
        self.assertEqual(bullet_template_profile(0).state4_terminal_age, 30)

    def test_copied_normal_script_recovers_type_and_observed_lifecycle(self) -> None:
        for profile in BULLET_TEMPLATE_PROFILES:
            self.assertEqual(
                bullet_type_from_normal_script(profile.normal_script),
                profile.bullet_type,
            )
            for state, expected_age in (
                (2, profile.state2_terminal_age),
                (3, profile.state3_terminal_age),
                (4, profile.state4_terminal_age),
            ):
                lifecycle = bullet_spawn_lifecycle_for_state(
                    profile.bullet_type,
                    state,
                )
                self.assertEqual(lifecycle.state, state)
                self.assertEqual(lifecycle.terminal_age, expected_age)

        with self.assertRaises(BulletTemplateContractError):
            bullet_type_from_normal_script(-1)

    def test_compact_payload_retains_source_and_asset_provenance(self) -> None:
        payload = pinned_contract_payload()

        self.assertEqual(payload["source_authority"]["template_count"], 21)
        self.assertEqual(
            payload["asset_authority"]["decoded_sha256"],
            ETAMA_DECODED_SHA256,
        )
        self.assertEqual(len(payload["profiles"]), 21)

    def test_old_capture_fallback_requires_exact_complete_overlap(self) -> None:
        observed = _observed_prefix()

        self.assertEqual(
            fallback_geometry_from_observed_prefix(observed, 16),
            (2.0, 2.0),
        )
        self.assertEqual(
            fallback_geometry_from_observed_prefix(observed, 20),
            (2.5, 2.5),
        )
        self.assertIsNone(
            fallback_geometry_from_observed_prefix(observed, 21)
        )

        altered = _observed_prefix()
        altered["rows"][7]["half_width"] = 500.0
        self.assertIsNone(
            fallback_geometry_from_observed_prefix(altered, 16)
        )

        sparse = _observed_prefix()
        sparse["rows"] = sparse["rows"][:-1]
        self.assertIsNone(
            fallback_geometry_from_observed_prefix(sparse, 16)
        )

    def test_exact_shipped_etama_regenerates_pinned_contract(self) -> None:
        if not GAME_ARCHIVE.is_file():
            self.skipTest("exact TH08 archive is outside this checkout")
        archive = PbgzArchive(GAME_ARCHIVE)
        decoded = decode_resource(
            archive.extract(archive.find("etama.anm")),
            require_wrapper=True,
        )

        self.assertEqual(verify_decoded_etama(decoded), BULLET_TEMPLATE_PROFILES)


if __name__ == "__main__":
    unittest.main()
