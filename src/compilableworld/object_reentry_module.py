"""Fixed, compiled Object Re-entry capability over the existing transaction Kernel."""

from __future__ import annotations

from copy import deepcopy
import hashlib

from .models import ActionIR, Entity, EntityDelta, EventIR, ModuleContract, StateDelta, TransitionResult
from .object_reentry import (MAX_DEPTH, MAX_POWER, MODULE_ID, RECIPE_FORMAT, ObjectReentryError, _id, _integer,
                             canonical_hash, derive, validate_compiled_grammar)


class ObjectReentryModule:
    contract = ModuleContract(
        module_id=MODULE_ID, version="0.1.0", layer="runtime",
        actions=["craft", "use_tool"], events=["craft.generated", "craft.used"],
        read=["position.*", "inventory.*", "craft.*"],
        write=["position.*", "inventory.*", "craft.*", "lineage.*"],
        requires_kernel=["entity_transaction/v0.1"],
    )

    def __init__(self, compiled: dict, checksums: dict) -> None:
        self.grammar = validate_compiled_grammar(compiled, checksums)
        self.grammar_hash = canonical_hash(self.grammar)

    def _instance(self, runtime, entity_id: str) -> tuple[Entity, dict]:
        if not isinstance(entity_id, str) or not runtime.registry.contains(entity_id):
            raise ObjectReentryError("unknown generated object")
        entity = runtime.registry.get(entity_id)
        recipe = entity.metadata.get("object_reentry")
        if (entity_id not in runtime.dynamic_entities or entity.entity_type != "item"
                or not isinstance(recipe, dict) or recipe.get("format") != RECIPE_FORMAT
                or recipe.get("grammar_hash") != self.grammar_hash):
            raise ObjectReentryError("object does not belong to this compiled grammar")
        try:
            expected = derive(self.grammar, recipe["recipe_id"], recipe["material_id"],
                              recipe["seed"], recipe["input_tool"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ObjectReentryError("object recipe is invalid") from exc
        if recipe != expected or canonical_hash(recipe) != canonical_hash(expected):
            raise ObjectReentryError("object recipe is not reproducible")
        power = runtime.state.get(entity_id, "craft", "power")
        depth = runtime.state.get(entity_id, "craft", "depth")
        _integer(power, 0, MAX_POWER, "object.power")
        _integer(depth, 1, MAX_DEPTH, "object.depth")
        if power != recipe["output_power"] or depth != recipe["depth"]:
            raise ObjectReentryError("object properties do not match its recipe")
        return entity, recipe

    def _tool(self, runtime, actor: str, tool_id: str) -> dict:
        _, recipe = self._instance(runtime, tool_id)
        if recipe["output_kind"] != "tool":
            raise ObjectReentryError("input must be a generated tool")
        if runtime.state.get(tool_id, "inventory", "carrier") != actor:
            raise ObjectReentryError("actor must carry the input tool")
        condition = runtime.state.get(tool_id, "craft", "condition")
        _integer(condition, 0, 100, "tool.condition")
        last_event = runtime.state.get(tool_id, "craft", "last_event_id")
        if not isinstance(last_event, str) or not last_event:
            raise ObjectReentryError("input tool has no recorded history reference")
        return {
            "entity_id": tool_id, "derivation_id": recipe["derivation_id"],
            "grammar_hash": self.grammar_hash, "kind": recipe["output_kind"],
            "power": recipe["output_power"], "condition": condition, "depth": recipe["depth"],
            "last_event_id": last_event,
            "versions": {key: runtime.state.version(tool_id, "craft", key)
                         for key in ("power", "condition", "last_event_id")},
        }

    def preview(self, runtime, actor: str, recipe_id: str, material_id: str, seed: int,
                tool_id: str | None = None) -> dict:
        tool = self._tool(runtime, actor, tool_id) if tool_id is not None else None
        return derive(self.grammar, recipe_id, material_id, seed, tool)

    def _wear(self, tool: dict, event_id: str) -> list[StateDelta]:
        return [
            StateDelta(tool["entity_id"], "craft", "condition", "set",
                       max(0, tool["condition"] - self.grammar["limits"]["wear_per_use"]),
                       expected_version=tool["versions"]["condition"], source_module=MODULE_ID),
            StateDelta(tool["entity_id"], "craft", "last_event_id", "set", event_id,
                       expected_version=tool["versions"]["last_event_id"], source_module=MODULE_ID),
        ]

    def evaluate(self, action: ActionIR, runtime) -> TransitionResult:
        try:
            if (not runtime.registry.contains(action.actor_id)
                    or runtime.registry.get(action.actor_id).entity_type not in ("character", "creature")):
                raise ObjectReentryError("crafting requires a living actor entity")
            if not isinstance(action.args, dict):
                raise ObjectReentryError("craft arguments must be an object")
            if action.verb == "use_tool":
                if action.args:
                    raise ObjectReentryError("use_tool takes no free effect arguments")
                tool = self._tool(runtime, action.actor_id, action.target_id)
                if tool["condition"] == 0:
                    raise ObjectReentryError("tool is already worn out")
                event = EventIR("craft.used", MODULE_ID, {
                    "tool_id": tool["entity_id"], "previous_event_id": tool["last_event_id"],
                    "condition_before": tool["condition"],
                    "condition_after": max(0, tool["condition"] - self.grammar["limits"]["wear_per_use"]),
                })
                return TransitionResult(True, self._wear(tool, event.event_id), [event], "工具已使用並留下磨耗")
            if action.verb != "craft" or set(action.args) - {"recipe_id", "material_id", "seed", "output_id"}:
                raise ObjectReentryError("unsupported crafting action/arguments")
            seed = action.args.get("seed", int.from_bytes(hashlib.sha256(action.action_id.encode()).digest()[:4], "big"))
            record = self.preview(runtime, action.actor_id, action.args.get("recipe_id"),
                                  action.args.get("material_id"), seed, action.target_id)
            entity_id = action.args.get("output_id", "item.generated_" + hashlib.sha256(action.action_id.encode()).hexdigest()[:24])
            _id(entity_id, "output_id")
            recipe = next(row for row in self.grammar["recipes"] if row["recipe_id"] == record["recipe_id"])
            material = next(row for row in self.grammar["materials"] if row["material_id"] == record["material_id"])
            room = runtime.state.get(action.actor_id, "position", "room")
            if room not in {row["room_id"] for row in runtime.package["rooms"]}:
                raise ObjectReentryError("actor has no valid workshop location")
            event = EventIR("craft.generated", MODULE_ID, {
                "entity_id": entity_id, "derivation_id": record["derivation_id"],
                "input_tool": deepcopy(record["input_tool"]), "power": record["output_power"],
            })
            entity = Entity(entity_id, "item", f"{material['name']}{recipe['name']}",
                            ["position", "inventory", "craft"],
                            {"portable": True, "provenance": MODULE_ID, "object_reentry": record,
                             "creation_event_id": event.event_id})
            deltas = [
                StateDelta(entity_id, "position", "room", "set", room),
                StateDelta(entity_id, "inventory", "carrier", "set", None),
                StateDelta(entity_id, "craft", "power", "set", record["output_power"]),
                StateDelta(entity_id, "craft", "condition", "set", 100),
                StateDelta(entity_id, "craft", "depth", "set", record["depth"]),
                StateDelta(entity_id, "craft", "last_event_id", "set", event.event_id),
                StateDelta(entity_id, "lineage", "creator", "set", action.actor_id),
                StateDelta(entity_id, "lineage", "derivation_id", "set", record["derivation_id"]),
            ]
            if record["input_tool"] is not None:
                deltas.extend(self._wear(record["input_tool"], event.event_id))
            return TransitionResult(True, deltas, [event], "工坊已產生可追溯的新物件",
                                    [EntityDelta("create", entity, source_module=MODULE_ID)])
        except ObjectReentryError as exc:
            return TransitionResult(False, message=str(exc))

    def visual_recipe(self, runtime, entity_id: str) -> dict:
        entity, record = self._instance(runtime, entity_id)
        material = next(row for row in self.grammar["materials"] if row["material_id"] == record["material_id"])
        condition = runtime.state.get(entity_id, "craft", "condition")
        _integer(condition, 0, 100, "object.condition")
        return {"format": "compilableworld.visual-recipe/v0.1", "read_only": True,
                "entity_id": entity_id, "name": entity.name, "kind": record["output_kind"],
                "palette": material["palette"], "overlays": ["worn"] if condition < 100 else [],
                "condition": condition, "power": record["output_power"],
                "derivation_id": record["derivation_id"]}
