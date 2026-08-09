from __future__ import annotations

import copy
import unittest
from pathlib import Path

from compilableworld.studio_mapping import STUDIO_MAPPING_FORMAT, suggest_studio_mapping, validate_studio_mapping
from compilableworld.studio_world_ir import import_eveglyph_text, import_eveglyph_yaml


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
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.guarded_review
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
                guards: [trust >= 1]
            """,
            "guarded-review.yaml",
        )
        report = validate_studio_mapping(world_ir, _complete_mapping(world_ir))

        self.assertTrue(report["mapping_complete"])
        self.assertFalse(report["runtime_ready"])
        self.assertEqual(report["summary"], {"entity_bindings": 0, "state_machine_bindings": 1})
        self.assertIn(
            "non_runtime_guard_policy",
            {issue["code"] for issue in report["diagnostics"]["issues"]},
        )

    def test_world_ir_diagnostics_block_mapping_even_when_bindings_are_filled(self) -> None:
        world_ir = import_eveglyph_yaml(EXAMPLE)
        report = validate_studio_mapping(world_ir, _complete_mapping(world_ir))

        self.assertFalse(report["mapping_complete"])
        self.assertFalse(report["runtime_ready"])
        self.assertIn(
            "world_ir_diagnostics",
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

    def test_suggestion_carries_requirements_and_validates_them(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.requirements
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: movement.actor_moved
                requirements: [reach:room.slum_alley]
            """,
            "requirements.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        transition_mapping = mapping["state_machines"]["quest.requirements"]["event_mappings"]["quest.requirements.transition.1"]

        self.assertEqual(transition_mapping["requirements"], ["reach:room.slum_alley"])
        report = validate_studio_mapping(world_ir, mapping)
        self.assertTrue(report["mapping_complete"])
        self.assertTrue(report["runtime_ready"])

    def test_mapping_cannot_remove_world_ir_requirements(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.requirements
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: movement.actor_moved
                requirements: [reach:room.slum_alley]
            """,
            "requirements.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        mapping["state_machines"]["quest.requirements"]["event_mappings"]["quest.requirements.transition.1"]["requirements"] = []

        report = validate_studio_mapping(world_ir, mapping)

        self.assertFalse(report["mapping_complete"])
        self.assertIn(
            "requirements_mismatch",
            {issue["code"] for issue in report["diagnostics"]["issues"]},
        )

    def test_suggestion_carries_event_match_and_validates_event_fields(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.event_match
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: dialogue.responded
                event_match:
                  dialogue_id: dialogue.generated.offer
            """,
            "event-match.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        transition_mapping = mapping["state_machines"]["quest.event_match"]["event_mappings"]["quest.event_match.transition.1"]

        self.assertEqual(transition_mapping["event_match"], {"dialogue_id": "dialogue.generated.offer"})
        report = validate_studio_mapping(world_ir, mapping)
        self.assertTrue(report["mapping_complete"])
        self.assertTrue(report["runtime_ready"])

    def test_mapping_rejects_event_match_field_for_target_event(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.event_match
            initial: dormant
            states: [dormant, active]
            transitions:
              - from: dormant
                to: active
                on: movement.actor_moved
                event_match:
                  dialogue_id: dialogue.generated.offer
            """,
            "event-match.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)

        report = validate_studio_mapping(world_ir, mapping)

        self.assertFalse(report["mapping_complete"])
        self.assertIn(
            "invalid_event_match_field",
            {issue["code"] for issue in report["diagnostics"]["issues"]},
        )

    def test_suggestion_carries_priority_and_reward(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.rewarded
            initial: active
            states: [active, completed]
            transitions:
              - from: active
                to: completed
                on: inventory.item_given
                priority: 9
                reward:
                  currency: 12
            """,
            "rewarded-quest.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        transition_mapping = mapping["state_machines"]["quest.rewarded"]["event_mappings"]["quest.rewarded.transition.1"]

        self.assertEqual(transition_mapping["priority"], 9)
        self.assertEqual(transition_mapping["reward"], {"currency": 12})
        report = validate_studio_mapping(world_ir, mapping)
        self.assertTrue(report["mapping_complete"])
        self.assertTrue(report["runtime_ready"])

    def test_extended_builtin_event_is_shared_by_import_mapping_and_runtime_contract(self) -> None:
        world_ir = import_eveglyph_text(
            """
            kind: state_machine
            id: quest.unlock_gate
            initial: locked
            states: [locked, completed]
            transitions:
              - from: locked
                to: completed
                on: door.unlocked
                event_match:
                  door: door.checkpoint_gate
            """,
            "unlock-gate.yaml",
        )
        mapping = suggest_studio_mapping(world_ir)
        transition = mapping["state_machines"]["quest.unlock_gate"]["event_mappings"]["quest.unlock_gate.transition.1"]

        self.assertEqual(transition["event_type"], "door.unlocked")
        self.assertEqual(transition["event_match"], {"door": "door.checkpoint_gate"})
        report = validate_studio_mapping(world_ir, mapping)
        self.assertTrue(report["mapping_complete"])
        self.assertTrue(report["runtime_ready"])


if __name__ == "__main__":
    unittest.main()
