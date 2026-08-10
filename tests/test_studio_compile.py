from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.studio_compile import StudioCompileError, compile_studio_world_ir
from compilableworld.studio_mapping import suggest_studio_mapping
from compilableworld.studio_world_ir import import_eveglyph_text


ROOT = Path(__file__).resolve().parents[1]
BASE_WORLD = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class StudioCompileTests(unittest.TestCase):
    def test_reviewed_quest_overlay_compiles_on_base_world_without_mutating_source(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.generated_studio
            initial: dormant
            states: [dormant, active, completed]
            variables:
              - id: trust
                type: integer
                default: 0
            events:
              - id: dialogue.responded
                payload: []
            instructions:
              - id: instruction.ask
                intent: dialogue.responded
            responses:
              - id: response.offer
                text: "The clerk offers work."
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
                event_match:
                  dialogue_id: dialogue.generated.offer
                requirements: [reach:room.slum_alley]
                priority: 3
              - from: active
                to: completed
                on: inventory.item_given
                priority: 5
                reward:
                  currency: 12
            """,
            "generated-quest.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        before_quests = (BASE_WORLD / "quests.json").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_studio_world_ir(BASE_WORLD, world_ir, mapping, Path(temp) / "runtime")
            package = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertIn("quest.generated_studio", {quest["quest_id"] for quest in package["quests"]})
        self.assertEqual(package["studio"]["format"], "compilableworld.studio-compile/v0.1")
        self.assertTrue(package["studio"]["semantic_records_are_metadata_only"])
        self.assertEqual(
            package["studio"]["semantic_records"]["quest.generated_studio"]["responses"][0]["id"],
            "response.offer",
        )
        quest = next(quest for quest in package["quests"] if quest["quest_id"] == "quest.generated_studio")
        self.assertEqual(quest["transitions"][0]["event_match"], {"dialogue_id": "dialogue.generated.offer"})
        self.assertEqual(quest["transitions"][0]["requirements"], ["reach:room.slum_alley"])
        self.assertEqual(quest["transitions"][0]["priority"], 3)
        self.assertEqual(quest["transitions"][1]["priority"], 5)
        self.assertEqual(quest["transitions"][1]["reward"], {"currency": 12})
        self.assertEqual((BASE_WORLD / "quests.json").read_text(encoding="utf-8"), before_quests)

    def test_mapped_entity_overlay_requires_explicit_room_and_compiles(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: entity
            id: npc.generated_studio
            type: character
            name: Generated Studio NPC
            location: room.registration_office
            """,
            "generated-npc.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_studio_world_ir(BASE_WORLD, world_ir, mapping, Path(temp) / "runtime")
            package = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertIn("npc.generated_studio", {entity["entity_id"] for entity in package["entities"]})

    def test_free_form_guard_is_rejected_before_package_compile(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.guarded_studio
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
                guards: [trust >= 1]
            """,
            "guarded-quest.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(StudioCompileError):
                compile_studio_world_ir(BASE_WORLD, world_ir, mapping, Path(temp) / "runtime")

    def test_oversized_semantic_metadata_is_rejected_before_package_compile(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.oversized_semantics
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
            """,
            "oversized-semantics.yaml",
        )
        world_ir["state_machines"][0]["responses"] = [{"id": "response.large", "text": "x" * 4_000_001}]
        mapping = suggest_studio_mapping(world_ir)

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(StudioCompileError, "semantic records exceed"):
                compile_studio_world_ir(BASE_WORLD, world_ir, mapping, Path(temp) / "runtime")


if __name__ == "__main__":
    unittest.main()
