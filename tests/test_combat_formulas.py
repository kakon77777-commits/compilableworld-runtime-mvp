from __future__ import annotations

import unittest

from compilableworld.combat_formulas import (
    Attributes, damage, hit_chance, hp_from_con, melee_ar, melee_dr, tier_effective_ar,
)


class CombatFormulaFidelityTests(unittest.TestCase):
    """Regression tests against the exact worked examples in
    worlds/mingyun_zhiyu/data/drafts/combat_resolution_system.json
    (example_b_top12_sparring) — proves this module reproduces Neo's
    approved canon combat math, not an approximation of it."""

    luftiya = Attributes(str_=906, con=906, mag=408, agi=408, dex=408)
    geluosen = Attributes(str_=1106, con=680, mag=436, agi=436, dex=436)

    def test_luftiya_attacks_geluosen(self) -> None:
        ar = melee_ar(self.luftiya)
        self.assertAlmostEqual(ar, 756.6, places=1)
        ar_eff = tier_effective_ar(ar, attacker_tier=2, defender_tier=1)
        self.assertAlmostEqual(ar_eff, 1134.9, places=1)
        dr = melee_dr(self.geluosen)
        self.assertAlmostEqual(dr, 606.8, places=1)
        self.assertAlmostEqual(hit_chance(ar_eff, dr), 0.652, places=3)
        self.assertEqual(damage(ar_eff, dr), 83)

    def test_geluosen_attacks_luftiya(self) -> None:
        ar = melee_ar(self.geluosen)
        self.assertAlmostEqual(ar, 905.0, places=1)
        ar_eff = tier_effective_ar(ar, attacker_tier=1, defender_tier=2)
        self.assertAlmostEqual(ar_eff, 135.75, places=2)
        dr = melee_dr(self.luftiya)
        self.assertAlmostEqual(dr, 756.6, places=1)
        self.assertAlmostEqual(hit_chance(ar_eff, dr), 0.152, places=3)
        self.assertEqual(damage(ar_eff, dr), 7)  # negative raw damage -> scratch floor

    def test_hp_formula(self) -> None:
        self.assertEqual(hp_from_con(906), 7248)
        self.assertEqual(hp_from_con(680), 5440)

    def test_equal_tier_has_no_gate_adjustment(self) -> None:
        self.assertEqual(tier_effective_ar(500.0, attacker_tier=1, defender_tier=1), 500.0)

    def test_two_tier_gap_amplifies_further(self) -> None:
        self.assertAlmostEqual(tier_effective_ar(100.0, attacker_tier=3, defender_tier=1), 200.0)
        self.assertAlmostEqual(tier_effective_ar(100.0, attacker_tier=1, defender_tier=3), 100.0 * 0.15 ** 2, places=4)


if __name__ == "__main__":
    unittest.main()
