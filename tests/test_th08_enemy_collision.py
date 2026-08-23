import unittest

from th08_enemy_collision import (
    enemy_contact_size_to_damage_half_extent,
    enemy_contact_size_to_lethal_half_extent,
    enemy_lethal_to_damage_half_extent,
)


class EnemyCollisionConversionTest(unittest.TestCase):
    def test_lethal_extent_preserves_target_binary32_store_order(self) -> None:
        self.assertEqual(
            enemy_contact_size_to_lethal_half_extent(32.0),
            10.666666984558105,
        )
        self.assertNotEqual(
            enemy_contact_size_to_lethal_half_extent(32.0),
            32.0 / 3.0,
        )

    def test_damage_extent_uses_raw_contact_size(self) -> None:
        self.assertEqual(enemy_contact_size_to_damage_half_extent(32.0), 16.0)

    def test_legacy_damage_fallback_inverts_the_geometric_scale(self) -> None:
        self.assertEqual(enemy_lethal_to_damage_half_extent(8.0), 12.0)


if __name__ == "__main__":
    unittest.main()
