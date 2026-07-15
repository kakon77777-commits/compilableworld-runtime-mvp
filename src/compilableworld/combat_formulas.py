from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .functions import FunctionRegistry

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


def _registry_value(
    registry: FunctionRegistry | None,
    function_id: str,
    values: dict[str, int | float],
    fallback: Any,
) -> int | float:
    if registry is not None and registry.has(function_id):
        return registry.evaluate(function_id, values)
    return fallback()


def hp_from_con(con: int, *, registry: FunctionRegistry | None = None) -> int:
    """HP = CON x 8 (combat_resolution_system.json.hit_and_damage_resolution.hp_formula)."""
    return int(_registry_value(registry, "combat.hp_from_con", {"con": con}, lambda: con * 8))


def melee_ar(attacker: Attributes, *, registry: FunctionRegistry | None = None) -> float:
    """Attack Rating for melee_physical: STR x 0.7 + DEX x 0.3."""
    return float(_registry_value(
        registry,
        "combat.melee_ar",
        {"str": attacker.str_, "dex": attacker.dex},
        lambda: attacker.str_ * 0.7 + attacker.dex * 0.3,
    ))


def melee_dr(defender: Attributes, *, registry: FunctionRegistry | None = None) -> float:
    """Defense Rating for melee_physical: CON x 0.7 + AGI x 0.3."""
    return float(_registry_value(
        registry,
        "combat.melee_dr",
        {"con": defender.con, "agi": defender.agi},
        lambda: defender.con * 0.7 + defender.agi * 0.3,
    ))


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


def hit_chance(ar_effective: float, dr: float, *, registry: FunctionRegistry | None = None) -> float:
    """P(hit) = AR_effective / (AR_effective + DR) — a pure ratio, always in
    (0, 1), never a hard 0% or 100% (deliberate: always leaves a narrative
    sliver for the against-the-odds outcome)."""
    return float(_registry_value(
        registry,
        "combat.hit_chance",
        {"ar_effective": ar_effective, "dr": dr},
        lambda: ar_effective / (ar_effective + dr),
    ))


def damage(ar_effective: float, dr: float, *, registry: FunctionRegistry | None = None) -> int:
    """round((AR_effective - DR*0.5) * 0.1), floored at max(1, round(AR_effective*0.05))
    so a landed hit is never a 0-damage absurdity."""
    if registry is not None and registry.has("combat.damage"):
        return int(registry.evaluate("combat.damage", {"ar_effective": ar_effective, "dr": dr}))
    raw = round((ar_effective - dr * 0.5) * 0.1)
    scratch_floor = max(1, round(ar_effective * 0.05))
    return max(raw, scratch_floor)


def initiative_value(attrs: Attributes, *, registry: FunctionRegistry | None = None) -> float:
    """IV = AGI + 0.5*DEX (turn_and_initiative_structure.initiative_value_formula)."""
    return float(_registry_value(
        registry,
        "combat.initiative_value",
        {"agi": attrs.agi, "dex": attrs.dex},
        lambda: attrs.agi + 0.5 * attrs.dex,
    ))


def action_economy(own_iv: float, opponent_iv: float, *, registry: FunctionRegistry | None = None) -> int:
    """Actions_per_exchange = clamp(round(own_IV / opponent_IV), 1, 4) — the
    faster side gets extra actions within one Exchange; the slower side is
    floored at 1 (always gets to act, never fully locked out). Source file's
    own worked example: IV ratio 3.2 -> 3 actions."""
    return int(_registry_value(
        registry,
        "combat.action_economy",
        {"own_iv": own_iv, "opponent_iv": opponent_iv},
        lambda: max(1, min(4, round(own_iv / opponent_iv))),
    ))


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


# status_effects_framework: duration is counted in "交鋒" (Exchange) units.
# Scoped simplification, documented not hidden: only combat.basic's Exchange
# loop (an `attack` action) ticks decay -- casting a spell doesn't itself
# consume an Exchange for decay purposes, even though the source file's
# cast_time_exchanges implies it should. Tracking that too would need a
# shared exchange-counter between MagicModule and CombatModule; deferred.

def refresh_status(effects: list[dict], status_id: str, exchanges: int, magnitude: float | None = None) -> list[dict]:
    """generic_rules.stacking_rule default: same status re-applied refreshes
    duration rather than stacking (stacking is opt-in per-combo, not built
    generically here)."""
    kept = [e for e in effects if e["id"] != status_id]
    entry = {"id": status_id, "exchanges_remaining": exchanges}
    if magnitude is not None:
        entry["magnitude"] = magnitude
    return kept + [entry]


def decay_status_effects(effects: list[dict]) -> list[dict]:
    """One Exchange has passed for this entity: every active status loses one
    exchange of duration; anything that hits zero is removed."""
    decayed = []
    for effect in effects:
        remaining = effect["exchanges_remaining"] - 1
        if remaining > 0:
            decayed.append({**effect, "exchanges_remaining": remaining})
    return decayed


def has_status(effects: list[dict], status_id: str) -> bool:
    return any(e["id"] == status_id for e in effects)
