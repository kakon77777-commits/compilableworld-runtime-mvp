from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.studio_world_ir import (
    STUDIO_WORLD_IR_FORMAT,
    import_eveglyph_yaml,
    import_eveglyph_text,
    parse_eveglyph_yaml,
    write_world_ir,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "studio_village_inn"


class StudioWorldIRTests(unittest.TestCase):
    def test_import_normalizes_eveglyph_documents_and_preserves_diagnostics(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE)

        self.assertEqual(world_ir["format"], STUDIO_WORLD_IR_FORMAT)
        self.assertEqual(world_ir["source_format"], "eveglyph-world-yaml/v0.1")
        self.assertFalse(world_ir["compile_ready"])
        self.assertEqual(world_ir["summary"], {"documents": 6, "entities": 8, "state_machines": 3})
        self.assertEqual(world_ir["diagnostics"]["errors"], 2)
        self.assertEqual(
            {issue["code"] for issue in world_ir["diagnostics"]["issues"]},
            {"missing_id", "duplicate_id", "conflicting_transition", "unreachable_state"},
        )
        plan = world_ir["migration_plan"]
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["format"], "compilableworld.studio-migration-plan/v0.1")
        self.assertEqual(
            {decision["code"] for decision in plan["required_decisions"]},
            {"entity_room_binding", "runtime_event_mapping", "guard_semantics"},
        )
        innkeeper = next(
            item for item in world_ir["entities"]
            if item["entity_id"] == "npc.innkeeper" and item["source_document"] == "entity.npc_innkeeper.yaml"
        )
        self.assertEqual(innkeeper["entity_type"], "character")
        self.assertEqual(innkeeper["metadata"]["location"], "room.inn.main")
        quest = next(item for item in world_ir["state_machines"] if item["state_machine_id"] == "quest.missing_caravan")
        self.assertEqual(quest["initial_state"], "locked")
        self.assertEqual(len(quest["transitions"]), 5)
        self.assertEqual(quest["transitions"][0]["guards"], ["player.reputation.village >= 2"])

    def test_parser_supports_nested_lists_and_quoted_scalars(self) -> None:
        document = parse_eveglyph_yaml(
            """
            kind: entity
            id: npc.test
            type: character
            name: 'Test NPC'
            traits:
              - brave
              - "curious"
            """
        )
        self.assertEqual(document["traits"], ["brave", "curious"])

    def test_world_ir_can_be_written_as_deterministic_json_artifact(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE / "quest.missing_caravan.yaml")
        with tempfile.TemporaryDirectory() as temp:
            output = write_world_ir(world_ir, Path(temp) / "studio-world-ir.json")
            loaded = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(loaded["format"], STUDIO_WORLD_IR_FORMAT)
        self.assertEqual(loaded["summary"]["state_machines"], 1)
        self.assertEqual(loaded["diagnostics"]["errors"], 0)
        self.assertEqual(loaded["migration_plan"]["status"], "blocked")

    def test_text_import_preserves_semantic_records_and_bounded_random(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.semantic_draft
            initial: dormant
            states: [dormant, active]
            variables:
              - id: trust
                type: integer
                default: 0
                random:
                  kind: integer
                  min: 1
                  max: 6
            events:
              - id: dialogue.responded
                payload: []
            instructions:
              - id: ask_about_caravan
                intent: dialogue.responded
                examples: ["Where did the caravan go?"]
            responses:
              - id: response.initial
                text: "The clerk watches you carefully."
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
            """,
            "studio-draft.yaml",
        )
        machine = world_ir["state_machines"][0]
        self.assertEqual(world_ir["diagnostics"]["errors"], 0)
        self.assertEqual(machine["variables"][0]["random"]["max"], 6)
        self.assertEqual(machine["events"][0]["id"], "dialogue.responded")
        self.assertEqual(machine["instructions"][0]["examples"], ["Where did the caravan go?"])
        self.assertEqual(machine["responses"][0]["text"], "The clerk watches you carefully.")

    def test_text_import_rejects_unbounded_random(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.bad_random
            initial: dormant
            states: [dormant]
            variables:
              - id: roll
                random:
                  kind: integer
                  min: 0
                  max: 1000001
            """,
            "bad-random.yaml",
        )
        self.assertIn("random_range_limit_exceeded", {item["code"] for item in world_ir["diagnostics"]["issues"]})


if __name__ == "__main__":
    unittest.main()
