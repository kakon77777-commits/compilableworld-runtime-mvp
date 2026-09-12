"""Versioned static grammar and pure derivation; no Runtime mutation paths."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any


FORMAT = "compilableworld.object-reentry/v0.1"
COMPILED_FORMAT = "compilableworld.compiled-object-reentry/v0.1"
RECIPE_FORMAT = "compilableworld.object-derivation/v0.1"
SCHEMA_ID = "compilableworld.schema/object-reentry/v0.1"
MODULE_ID = "object_reentry.core"
ALGORITHM = "sha256-prefix64-mod/v1"
MAX_DEPTH = 8
MAX_POWER = MAX_DEPTH * (1000 + 1000 + 20)


class ObjectReentryError(ValueError):
    pass


def _fields(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ObjectReentryError(f"{label}: missing or unsupported fields")


def _text(value: Any, label: str, limit: int = 128) -> None:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ObjectReentryError(f"{label}: invalid text")


def _id(value: Any, label: str) -> None:
    _text(value, label)
    if re.fullmatch(r"[a-z][a-z0-9_.-]*", value) is None:
        raise ObjectReentryError(f"{label}: invalid ID")


def _integer(value: Any, low: int, high: int, label: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ObjectReentryError(f"{label}: expected integer {low}..{high}")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def validate_grammar(raw: Any) -> dict:
    _fields(raw, {"format", "grammar_id", "version", "materials", "recipes", "limits"}, "grammar")
    if raw["format"] != FORMAT:
        raise ObjectReentryError("unsupported Object Re-entry version")
    _id(raw["grammar_id"], "grammar_id")
    _text(raw["version"], "version", 64)
    limits = raw["limits"]
    _fields(limits, {"max_depth", "bonus_max", "wear_per_use", "min_tool_condition"}, "limits")
    for key, low, high in (("max_depth", 1, MAX_DEPTH), ("bonus_max", 0, 20),
                           ("wear_per_use", 1, 100), ("min_tool_condition", 1, 100)):
        _integer(limits[key], low, high, key)
    for key in ("materials", "recipes"):
        if not isinstance(raw[key], list) or not 1 <= len(raw[key]) <= 64:
            raise ObjectReentryError(f"{key}: expected 1..64 records")
    materials: set[str] = set()
    for row in raw["materials"]:
        _fields(row, {"material_id", "name", "power", "palette"}, "material")
        _id(row["material_id"], "material_id")
        _text(row["name"], "material.name")
        _integer(row["power"], 0, 1000, "material.power")
        if not isinstance(row["palette"], str) or re.fullmatch(r"#[0-9a-fA-F]{6}", row["palette"]) is None:
            raise ObjectReentryError("material.palette: expected hex color")
        if row["material_id"] in materials:
            raise ObjectReentryError("duplicate material ID")
        materials.add(row["material_id"])
    recipes: set[str] = set()
    for row in raw["recipes"]:
        _fields(row, {"recipe_id", "name", "output_kind", "input_kind", "material_ids", "power"}, "recipe")
        _id(row["recipe_id"], "recipe_id")
        _text(row["name"], "recipe.name")
        _integer(row["power"], 0, 1000, "recipe.power")
        if row["output_kind"] not in ("tool", "item") or row["input_kind"] not in ("none", "tool"):
            raise ObjectReentryError("recipe: unsupported input/output kind")
        allowed = row["material_ids"]
        if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 64
                or any(not isinstance(item, str) or item not in materials for item in allowed)
                or len(set(allowed)) != len(allowed)):
            raise ObjectReentryError("recipe: invalid material references")
        if row["recipe_id"] in recipes:
            raise ObjectReentryError("duplicate recipe ID")
        recipes.add(row["recipe_id"])
    return deepcopy(raw)


def compile_grammar(raw: Any, source_path: str, source_checksum: str) -> dict:
    grammar = validate_grammar(raw)
    return {"format": COMPILED_FORMAT, "source_path": source_path,
            "source_checksum": source_checksum, "grammar_hash": canonical_hash(grammar), "grammar": grammar}


def validate_compiled_grammar(raw: Any, checksums: dict) -> dict:
    _fields(raw, {"format", "source_path", "source_checksum", "grammar_hash", "grammar"}, "compiled grammar")
    if raw["format"] != COMPILED_FORMAT:
        raise ObjectReentryError("unsupported compiled Object Re-entry version")
    _text(raw["source_path"], "source_path", 4096)
    if (not isinstance(raw["source_checksum"], str)
            or re.fullmatch(r"[a-f0-9]{64}", raw["source_checksum"]) is None
            or checksums.get(raw["source_path"]) != raw["source_checksum"]):
        raise ObjectReentryError("compiled grammar source provenance mismatch")
    grammar = validate_grammar(raw["grammar"])
    if raw["grammar_hash"] != canonical_hash(grammar):
        raise ObjectReentryError("compiled grammar hash mismatch")
    return grammar


def derive(grammar: dict, recipe_id: str, material_id: str, seed: int, tool: dict | None = None) -> dict:
    """Return a reproducible recipe, not an Entity or a StateStore write."""
    _integer(seed, 0, 2**32 - 1, "seed")
    recipe = next((row for row in grammar["recipes"] if row["recipe_id"] == recipe_id), None)
    material = next((row for row in grammar["materials"] if row["material_id"] == material_id), None)
    if recipe is None or material is None or material_id not in recipe["material_ids"]:
        raise ObjectReentryError("recipe/material combination is not allowed")
    digest = canonical_hash(grammar)
    depth, contribution = 1, 0
    if recipe["input_kind"] == "none":
        if tool is not None:
            raise ObjectReentryError("this recipe takes no input tool")
    else:
        _fields(tool, {"entity_id", "derivation_id", "grammar_hash", "kind", "power", "condition",
                       "depth", "last_event_id", "versions"}, "input tool")
        _id(tool["entity_id"], "input tool ID")
        _text(tool["derivation_id"], "input derivation")
        _text(tool["last_event_id"], "input history event")
        if tool["kind"] != "tool" or tool["grammar_hash"] != digest:
            raise ObjectReentryError("input tool belongs to an incompatible grammar/type")
        _integer(tool["power"], 0, MAX_POWER, "tool.power")
        _integer(tool["condition"], 0, 100, "tool.condition")
        _integer(tool["depth"], 1, MAX_DEPTH, "tool.depth")
        _integer(tool["power"], 0, tool["depth"] * 2020, "tool.power at depth")
        _fields(tool["versions"], {"power", "condition", "last_event_id"}, "tool versions")
        for value in tool["versions"].values():
            _integer(value, 0, 2**63 - 1, "tool version")
        if tool["condition"] < grammar["limits"]["min_tool_condition"]:
            raise ObjectReentryError("tool is too worn for this grammar")
        depth = tool["depth"] + 1
        contribution = tool["power"] * tool["condition"] // 100
    if depth > grammar["limits"]["max_depth"]:
        raise ObjectReentryError("Object Re-entry depth limit reached")
    entropy = f"{digest}|{recipe_id}|{material_id}|{seed}".encode("utf-8")
    bonus = int.from_bytes(hashlib.sha256(entropy).digest()[:8], "big") % (grammar["limits"]["bonus_max"] + 1)
    record = {
        "format": RECIPE_FORMAT, "grammar_id": grammar["grammar_id"], "grammar_version": grammar["version"],
        "grammar_hash": digest, "recipe_id": recipe_id, "material_id": material_id,
        "algorithm": ALGORITHM, "seed": seed, "bonus": bonus, "input_tool": deepcopy(tool),
        "depth": depth, "output_kind": recipe["output_kind"],
        "output_power": material["power"] + recipe["power"] + contribution + bonus,
    }
    record["derivation_id"] = "derivation." + canonical_hash(record)
    return record
