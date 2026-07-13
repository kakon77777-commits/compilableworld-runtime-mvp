from __future__ import annotations

from dataclasses import dataclass

ATTRIBUTE_FLOOR = 10
"""'凡人地板值' — every unawakened person has this in all five attributes,
per combat_resolution_system.json's attribute_distribution_system.baseline_floor."""


@dataclass(frozen=True, slots=True)
class Attributes:
    str_: int
    con: int
    mag: int
    agi: int
    dex: int


def hp_from_con(con: int) -> int:
    """HP = CON x 8 (combat_resolution_system.json.hit_and_damage_resolution.hp_formula)."""
    return con * 8


def melee_ar(attacker: Attributes) -> float:
    """Attack Rating for melee_physical: STR x 0.7 + DEX x 0.3."""
    return attacker.str_ * 0.7 + attacker.dex * 0.3


def melee_dr(defender: Attributes) -> float:
    """Defense Rating for melee_physical: CON x 0.7 + AGI x 0.3."""
    return defender.con * 0.7 + defender.agi * 0.3


def tier_effective_ar(ar: float, attacker_tier: int, defender_tier: int) -> float:
    """phase_tier_system.tier_gate_combat_rule — a lower-tier attacker vs a
    higher-tier defender is savaged (0.15^gap); a higher-tier attacker vs a
    lower-tier defender is amplified (1 + 0.5*gap). Equal tier: unchanged.
    This is the mechanism that lets a tier-2 character with LOWER raw stats
    still dominate a tier-1 character with higher raw stats (the file's own
    worked example: 露芙緹雅 beats 格洛森 despite his marginally higher
    adjusted cumulative_power)."""
    gap = attacker_tier - defender_tier
    if gap < 0:
        return ar * (0.15 ** abs(gap))
    if gap > 0:
        return ar * (1 + 0.5 * gap)
    return ar


def hit_chance(ar_effective: float, dr: float) -> float:
    """P(hit) = AR_effective / (AR_effective + DR) — a pure ratio, always in
    (0, 1), never a hard 0% or 100% (deliberate: always leaves a narrative
    sliver for the against-the-odds outcome)."""
    return ar_effective / (ar_effective + dr)


def damage(ar_effective: float, dr: float) -> int:
    """round((AR_effective - DR*0.5) * 0.1), floored at max(1, round(AR_effective*0.05))
    so a landed hit is never a 0-damage absurdity."""
    raw = round((ar_effective - dr * 0.5) * 0.1)
    scratch_floor = max(1, round(ar_effective * 0.05))
    return max(raw, scratch_floor)


def initiative_value(attrs: Attributes) -> float:
    """IV = AGI + 0.5*DEX (turn_and_initiative_structure.initiative_value_formula)."""
    return attrs.agi + 0.5 * attrs.dex


def action_economy(own_iv: float, opponent_iv: float) -> int:
    """Actions_per_exchange = clamp(round(own_IV / opponent_IV), 1, 4) — the
    faster side gets extra actions within one Exchange; the slower side is
    floored at 1 (always gets to act, never fully locked out). Source file's
    own worked example: IV ratio 3.2 -> 3 actions."""
    return max(1, min(4, round(own_iv / opponent_iv)))


def apply_damage(current_health: int, current_temp_hp: int, dmg: int) -> tuple[int, int]:
    """Pure: status_effects_framework.shield_buff's temp_HP absorbs before
    real health. Returns (new_health, new_temp_hp). No state/runtime
    coupling deliberately -- a multi-action Exchange needs to thread this
    across several hits before anything is committed, so it can't read
    "current" from the Kernel mid-loop (nothing's committed yet)."""
    if current_temp_hp > 0:
        absorbed = min(current_temp_hp, dmg)
        current_temp_hp -= absorbed
        dmg -= absorbed
    new_health = max(0, current_health - dmg) if dmg > 0 else current_health
    return new_health, current_temp_hp
