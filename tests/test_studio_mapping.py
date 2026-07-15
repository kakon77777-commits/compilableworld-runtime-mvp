from __future__ import annotations

import copy
import unittest
from pathlib import Path

from compilableworld.studio_mapping import STUDIO_MAPPING_FORMAT, suggest_studio_mapping, validate_studio_mapping
from compilableworld.studio_world_ir import import_eveglyph_yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "studio_village_inn"


def _complete_mapping(world_ir: dict) -> dict:
    plan = world_ir["migration_plan"]
    mapping = {
        "format": STUDIO_MAPPING_FORMAT,
        "world_ir_format": world_ir["format"],
        "entities": {},
        "state_machines": {},
    }
    for binding in plan["entity_bindings"]:
        mapping["entities"][binding["binding_key"]] = {
            "room": binding["proposed_room"] or "room.inn.main",
            "target_table": binding["target_table"],
        }
    for machine in plan["state_machine_bindings"]:
        mapping["state_machines"][machine["state_machine_id"]] = {
            "guard_policy": "external_review" if any(item["guards"] for item in machine["transitions"]) else "none",
            "event_mappings": {
                transition["transition_id"]: {"event_type": "dialogue.responded"}
                for transition in machine["transitions"]
            },
        }
    return mapping


class StudioMappingTests(unittest.TestCase):
    def test_suggestion_preserves_explicit_values_and_leaves_unknowns_unresolved(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE)
        suggestion = suggest_studio_mapping(world_ir)

        self.assertEqual(suggestion["format"], STUDIO_MAPPING_FORMAT)
        self.assertEqual(len(suggestion["entities"]), world_ir["summary"]["entities"])
        self.assertEqual(
            suggestion["entities"]["entity.npc_innkeeper.yaml::npc.innkeeper"]["room"],
            "room.inn.main",
        )
        self.assertIsNone(suggestion["entities"]["entities.village_inn.yaml::npc.innkeeper"]["room"])
        self.assertEqual(suggestion["state_machines"]["quest.missing_caravan"]["guard_policy"], "external_review")
        self.assertIsNone(
            suggestion["state_machines"]["quest.missing_caravan"]["event_mappings"]["quest.missing_caravan.transition.1"]["event_type"]
        )

    def test_complete_mapping_is_reviewable_but_guard_policy_blocks_runtime(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE)
        report = validate_studio_mapping(world_ir, _complete_mapping(world_ir))

        self.assertTrue(report["mapping_complete"])
        self.assertFalse(report["runtime_ready"])
        self.assertEqual(report["summary"], {"entity_bindings": 8, "state_machine_bindings": 3})
        self.assertIn(
            "non_runtime_guard_policy",
            {issue["code"] for issue in report["diagnostics"]["issues"]},
        )

    def test_missing_room_keeps_mapping_incomplete(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE)
        mapping = _complete_mapping(world_ir)
        first_key = next(iter(mapping["entities"]))
        mapping["entities"][first_key] = copy.deepcopy(mapping["entities"][first_key])
        mapping["entities"][first_key]["room"] = None

        report = validate_studio_mapping(world_ir, mapping)

        self.assertFalse(report["mapping_complete"])
        self.assertFalse(report["runtime_ready"])
        self.assertIn(
            "missing_entity_room",
            {issue["code"] for issue in report["diagnostics"]["issues"]},
        )


if __name__ == "__main__":
    unittest.main()
