"""Player-facing character generation for the Runtime MVP.

The world documents describe a five-attribute projection rather than a fixed
protagonist.  This module keeps that projection deterministic and small:

* the human baseline is 10 in every attribute;
* a template supplies an archetype weight vector;
* ``attribute = 10 + cumulative_power * weight`` is the default projection;
* a player may override individual starter attributes inside a safe starter
  range; and
* random generation uses a local PRNG, so a seed reproduces the exact profile.

The records in ``DEFAULT_TEMPLATES`` are gameplay suggestions, not canon
characters.  They are deliberately generic so they cannot accidentally turn
the former fixed protagonist group into player canon.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from random import Random, SystemRandom
from typing import Any, Mapping

from .combat_formulas import ATTRIBUTE_FLOOR, hp_from_con
from .functions import FunctionRegistry

ATTRIBUTE_NAMES = ("str", "con", "mag", "agi", "dex")
STARTER_LEVEL = 1
STARTER_CUMULATIVE_POWER = 15
STARTER_ATTRIBUTE_MAX = 60
TEMPLATE_SCHEMA_VERSION = "player-template/v0.1"


def _weights(*values: float) -> dict[str, float]:
    if len(values) != len(ATTRIBUTE_NAMES):
        raise ValueError("player template weights must contain five values")
    total = sum(values)
    if total <= 0:
        raise ValueError("player template weights must have a positive sum")
    return {key: value / total for key, value in zip(ATTRIBUTE_NAMES, values)}


# The names and descriptions are AI-proposed starter archetypes.  They are
# intentionally not any of the named protagonist characters from the source
# material.  ``origin`` makes this distinction visible to callers and future
# authoring tools.
DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "balanced",
        "name": "均衡探索者",
        "description": "五維平均，適合第一次進入世界或想自行塑形的玩家。",
        "archetype": "generic_balanced",
        "weights": _weights(0.2, 0.2, 0.2, 0.2, 0.2),
        "talent": {"name": "回聲辨路", "rarity": "普通級", "domain": "感知"},
        "origin": "ai_template",
        "canon_status": "suggestion",
    },
    {
        "template_id": "vanguard",
        "name": "前線守望者",
        "description": "STR／CON 雙主屬性，擅長近身承傷與正面突破。",
        "archetype": "dual_primary",
        "weights": _weights(0.30, 0.30, 0.1333, 0.1333, 0.1334),
        "talent": {"name": "石脈護身", "rarity": "普通級", "domain": "生命"},
        "origin": "ai_template",
        "canon_status": "suggestion",
    },
    {
        "template_id": "spellblade",
        "name": "符刃行者",
        "description": "MAG／DEX 雙重投資，讓規則魔法與精準攻擊互相支援。",
        "archetype": "single_primary",
        "primary": "mag",
        "secondary": "dex",
        "weights": _weights(0.14, 0.14, 0.36, 0.22, 0.14),
        "talent": {"name": "星火刻痕", "rarity": "優秀級", "domain": "符文"},
        "origin": "ai_template",
        "canon_status": "suggestion",
    },
    {
        "template_id": "scout",
        "name": "風痕斥候",
        "description": "AGI／DEX 偏重，適合探索、先攻、遠程與情報型玩法。",
        "archetype": "single_primary",
        "primary": "agi",
        "secondary": "dex",
        "weights": _weights(0.14, 0.14, 0.14, 0.36, 0.22),
        "talent": {"name": "風痕步", "rarity": "普通級", "domain": "運動"},
        "origin": "ai_template",
        "canon_status": "suggestion",
    },
    {
        "template_id": "ritualist",
        "name": "界線觀測者",
        "description": "MAG／CON 偏重，偏向儀式、控制與穩定施法。",
        "archetype": "single_primary",
        "primary": "mag",
        "secondary": "con",
        "weights": _weights(0.14, 0.22, 0.36, 0.14, 0.14),
        "talent": {"name": "靜界留痕", "rarity": "優秀級", "domain": "界域"},
        "origin": "ai_template",
        "canon_status": "suggestion",
    },
)


def _round_attribute(value: float) -> int:
    """Round halves away from zero for transparent authoring math."""
    return int(value + 0.5)


def _registry_value(
    registry: FunctionRegistry | None,
    function_id: str,
    values: dict[str, int | float],
    fallback: Any,
) -> int | float:
    if registry is not None and registry.has(function_id):
        return registry.evaluate(function_id, values)
    return fallback()


def _copy_template(raw: Mapping[str, Any]) -> dict[str, Any]:
    template = dict(raw)
    template_id = str(template.get("template_id", "")).strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_.-]*", template_id):
        raise ValueError(f"invalid player template id: {template_id!r}")
    weights = template.get("weights")
    if not isinstance(weights, Mapping):
        raise ValueError(f"player template {template_id} needs weights")
    normalized_weights = {key: float(weights.get(key, 0)) for key in ATTRIBUTE_NAMES}
    total = sum(normalized_weights.values())
    if total <= 0:
        raise ValueError(f"player template {template_id} weights must be positive")
    normalized_weights = {key: value / total for key, value in normalized_weights.items()}
    for key, value in normalized_weights.items():
        if value < 0:
            raise ValueError(f"player template {template_id} has negative {key} weight")
    template["template_id"] = template_id
    template["weights"] = normalized_weights
    template["name"] = str(template.get("name") or template_id)
    template["description"] = str(template.get("description") or "")
    template["talent"] = dict(template.get("talent") or {})
    template.setdefault("origin", "ai_template")
    template.setdefault("canon_status", "suggestion")
    return template


def template_catalog(package: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
    """Return package templates when present, otherwise the safe defaults."""
    raw_templates = package.get("player_templates") if package else None
    if raw_templates is None:
        raw_templates = DEFAULT_TEMPLATES
    if not isinstance(raw_templates, (list, tuple)) or not raw_templates:
        raise ValueError("player_templates must be a non-empty list")
    templates = tuple(_copy_template(raw) for raw in raw_templates)
    ids = [template["template_id"] for template in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("player template ids must be unique")
    return templates


def template_records(package: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return JSON-safe template records for compiler packages and APIs."""
    return [dict(template, schema_version=TEMPLATE_SCHEMA_VERSION) for template in template_catalog(package)]


def _validate_overrides(overrides: Mapping[str, Any] | None) -> dict[str, int]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise ValueError("attribute overrides must be an object")
    unknown = set(overrides) - set(ATTRIBUTE_NAMES)
    if unknown:
        raise ValueError(f"unknown player attributes: {sorted(unknown)}")
    result: dict[str, int] = {}
    for key, raw in overrides.items():
        if isinstance(raw, bool):
            raise ValueError(f"player attribute {key} must be an integer")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"player attribute {key} must be an integer") from exc
        if not ATTRIBUTE_FLOOR <= value <= STARTER_ATTRIBUTE_MAX:
            raise ValueError(
                f"player attribute {key} must be between {ATTRIBUTE_FLOOR} and {STARTER_ATTRIBUTE_MAX}"
            )
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class GeneratedPlayer:
    name: str
    template_id: str
    mode: str
    seed: int
    level: int
    phase_tier: int
    attributes: dict[str, int]
    talent: dict[str, Any]
    formula: dict[str, Any]
    derived: dict[str, int | float] = field(default_factory=dict)

    @property
    def hp_max(self) -> int:
        return int(self.derived.get("hp_max", hp_from_con(self.attributes["con"])))

    @property
    def mp_max(self) -> int:
        return int(self.derived.get("mp_max", self.attributes["mag"] * 5))

    @property
    def fp_max(self) -> int:
        return int(self.derived.get("fp_max", (self.attributes["mag"] + self.attributes["dex"]) * 2))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_id": self.template_id,
            "mode": self.mode,
            "seed": self.seed,
            "level": self.level,
            "phase_tier": self.phase_tier,
            "attributes": dict(self.attributes),
            "talent": dict(self.talent),
            "formula": dict(self.formula),
            "derived": dict(self.derived),
            "hp_max": self.hp_max,
            "mp_max": self.mp_max,
            "fp_max": self.fp_max,
            "provenance": "player_generated",
            "canon_status": "player_authored_runtime_profile",
        }


def generate_character(
    *,
    template_id: str = "balanced",
    name: str | None = None,
    seed: int | None = None,
    randomize: bool = False,
    attribute_overrides: Mapping[str, Any] | None = None,
    package: Mapping[str, Any] | None = None,
) -> GeneratedPlayer:
    """Generate a starter player profile from a template or a seed.

    ``randomize=True`` chooses a template with the local seeded PRNG.  It does
    not invent a second combat model.  Explicit overrides are applied after
    the formula projection and are recorded as ``mode=custom``.
    """
    actual_seed = seed if seed is not None else SystemRandom().getrandbits(64)
    rng = Random(actual_seed)
    registry = FunctionRegistry.from_package(package) if package is not None else None
    templates = template_catalog(package)
    if randomize:
        template = rng.choice(templates)
    else:
        wanted = str(template_id).strip().lower()
        try:
            template = next(item for item in templates if item["template_id"] == wanted)
        except StopIteration as exc:
            available = ", ".join(item["template_id"] for item in templates)
            raise ValueError(f"unknown player template {wanted!r}; available: {available}") from exc

    weights = {key: float(template["weights"][key]) for key in ATTRIBUTE_NAMES}
    attributes = {}
    for key in ATTRIBUTE_NAMES:
        projected = _registry_value(
            registry,
            "player.attribute_from_weight",
            {"base": ATTRIBUTE_FLOOR, "cumulative_power": STARTER_CUMULATIVE_POWER, "weight": weights[key]},
            lambda key=key: ATTRIBUTE_FLOOR + STARTER_CUMULATIVE_POWER * weights[key],
        )
        attributes[key] = max(ATTRIBUTE_FLOOR, _round_attribute(float(projected)))
    overrides = _validate_overrides(attribute_overrides)
    attributes.update(overrides)
    mode = "random" if randomize else "template"
    if overrides:
        mode = "custom"
    player_name = str(name).strip() if name is not None else ""
    if not player_name:
        player_name = f"{template['name']} #{actual_seed % 10000:04d}"
    derived = {
        "hp_max": int(_registry_value(
            registry,
            "combat.hp_from_con",
            {"con": attributes["con"]},
            lambda: hp_from_con(attributes["con"]),
        )),
        "mp_max": int(_registry_value(
            registry,
            "player.mp_from_mag",
            {"mag": attributes["mag"]},
            lambda: attributes["mag"] * 5,
        )),
        "fp_max": int(_registry_value(
            registry,
            "player.fp_from_mag_dex",
            {"mag": attributes["mag"], "dex": attributes["dex"]},
            lambda: (attributes["mag"] + attributes["dex"]) * 2,
        )),
    }
    formula = {
        "attribute": "10 + cumulative_power_effective * weight_i",
        "attribute_floor": ATTRIBUTE_FLOOR,
        "cumulative_power_effective": STARTER_CUMULATIVE_POWER,
        "weights": weights,
        "hp": "CON * 8",
        "mp": "MAG * 5",
        "fp": "(MAG + DEX) * 2",
        "override_attributes": dict(overrides),
        "functions": {
            "attribute": "player.attribute_from_weight" if registry is not None and registry.has("player.attribute_from_weight") else None,
            "hp": "combat.hp_from_con" if registry is not None and registry.has("combat.hp_from_con") else None,
            "mp": "player.mp_from_mag" if registry is not None and registry.has("player.mp_from_mag") else None,
            "fp": "player.fp_from_mag_dex" if registry is not None and registry.has("player.fp_from_mag_dex") else None,
        },
    }
    return GeneratedPlayer(
        name=player_name,
        template_id=template["template_id"],
        mode=mode,
        seed=actual_seed,
        level=STARTER_LEVEL,
        phase_tier=0,
        attributes=attributes,
        talent=dict(template.get("talent") or {}),
        formula=formula,
        derived=derived,
    )


def actor_id_for_player(profile: GeneratedPlayer, existing_ids: set[str] | None = None) -> str:
    """Create a stable, schema-safe actor id without using canon character ids."""
    normalized = unicodedata.normalize("NFKD", profile.name).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "traveler"
    base = f"player.generated.{slug[:32]}"
    existing = existing_ids or set()
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate
