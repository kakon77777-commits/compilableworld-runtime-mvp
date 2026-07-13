from __future__ import annotations

import unittest

from compilableworld.combat_formulas import (
    Attributes, action_economy, apply_damage, damage, decay_status_effects,
    has_status, hit_chance, hp_from_con, initiative_value, melee_ar, melee_dr,
    refresh_status, tier_effective_ar,
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

    def test_initiative_value(self) -> None:
        self.assertAlmostEqual(initiative_value(self.luftiya), 408 + 0.5 * 408)

    def test_action_economy_matches_source_files_own_example(self) -> None:
        # "IV比值3.2 -> round(3.2)=3,快的一方每次交鋒可行動3次,對方1次"
        self.assertEqual(action_economy(320.0, 100.0), 3)
        self.assertEqual(action_economy(100.0, 320.0), 1)

    def test_action_economy_clamped_to_one_and_four(self) -> None:
        self.assertEqual(action_economy(1.0, 1000.0), 1)
        self.assertEqual(action_economy(1000.0, 1.0), 4)

    def test_action_economy_below_1_5_ratio_is_simultaneous(self) -> None:
        self.assertEqual(action_economy(149.0, 100.0), 1)
        self.assertEqual(action_economy(100.0, 149.0), 1)

    def test_apply_damage_absorbs_temp_hp_first(self) -> None:
        health, temp_hp = apply_damage(current_health=80, current_temp_hp=15, dmg=5)
        self.assertEqual((health, temp_hp), (80, 10))

    def test_apply_damage_spillover(self) -> None:
        health, temp_hp = apply_damage(current_health=80, current_temp_hp=15, dmg=25)
        self.assertEqual((health, temp_hp), (70, 0))

    def test_refresh_status_replaces_not_stacks(self) -> None:
        effects = refresh_status([], "shield_buff", 3)
        effects = refresh_status(effects, "shield_buff", 3)  # re-cast before it expires
        self.assertEqual(effects, [{"id": "shield_buff", "exchanges_remaining": 3}])

    def test_refresh_status_preserves_other_statuses(self) -> None:
        effects = refresh_status([], "haste_疾風", 3)
        effects = refresh_status(effects, "shield_buff", 3)
        self.assertEqual(len(effects), 2)
        self.assertTrue(has_status(effects, "haste_疾風"))
        self.assertTrue(has_status(effects, "shield_buff"))

    def test_decay_status_effects_counts_down_and_expires(self) -> None:
        effects = [{"id": "haste_疾風", "exchanges_remaining": 1}, {"id": "shield_buff", "exchanges_remaining": 3}]
        effects = decay_status_effects(effects)
        self.assertFalse(has_status(effects, "haste_疾風"))  # hit 0, removed
        self.assertEqual(effects, [{"id": "shield_buff", "exchanges_remaining": 2}])


if __name__ == "__main__":
    unittest.main()
