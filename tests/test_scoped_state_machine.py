from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world
from compilableworld.kernel import KernelTransactionError, WorldRuntime
from compilableworld.models import ActionIR, EventIR
from compilableworld.modules import install_builtin_modules
from compilableworld.studio import package_overview, runtime_overview


ROOT = Path(__file__).resolve().parents[1]
GRAY_CROWN = ROOT / "examples" / "gray_crown"


def unlock_old_vault(runtime: WorldRuntime) -> None:
    actor = "player.neo"
    runtime.submit(ActionIR(actor, "take", "item.old_key"))
    runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
    runtime.submit(ActionIR(actor, "unlock", "door.old_vault"))


class ScopedStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.package_path = compile_world(GRAY_CROWN, Path(self.temp.name) / "build")
        self.package = json.loads(self.package_path.read_text(encoding="utf-8"))
        self.runtime = WorldRuntime(self.package)
        install_builtin_modules(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compiler_materializes_versioned_scoped_state_ir_without_replacing_legacy_seed(self) -> None:
        self.assertEqual(len(self.package["state_machines"]), 5)
        world_machine = self.package["state_machines"][0]
        self.assertEqual(world_machine["owner_scope"], "world")
        self.assertEqual(world_machine["owner_id"], "gray_crown_demo")
        self.assertEqual(world_machine["authority"], "state_machine.core")
        self.assertEqual(world_machine["transitions"][0]["event_match"], {"door": "door.old_vault"})
        self.assertEqual(
            [condition["condition_id"] for condition in world_machine["transitions"][0]["when"]],
            [
                "world_is_stable", "unlocking_actor_is_alive",
                "unlocking_actor_currency_is_valid",
            ],
        )
        self.assertIn("state_machine.core", self.package["manifest"]["modules"])
        self.assertEqual(
            self.package["manifest"]["source_schemas"]["state_machines"],
            "compilableworld.schema/state-machines/v0.2",
        )

        cells = {
            (item["owner"], item["namespace"], item["key"]): item["value"]
            for item in self.package["initial_state"]
        }
        self.assertEqual(cells[("gray_crown_demo", "fsm", "state")], "stable")
        self.assertEqual(
            cells[("gray_crown_demo", "fsm", "fsm.world.vault_seal")],
            "sealed",
        )
        self.assertEqual(
            cells[("system.security", "fsm", "fsm.system.security")],
            "nominal",
        )

    def test_unlock_event_advances_all_scopes_and_preserves_nested_causation(self) -> None:
        unlock_old_vault(self.runtime)

        expected = {
            ("gray_crown_demo", "fsm.world.vault_seal"): "completed",
            ("region.gray_crown", "fsm.region.gray_crown.alert"): "alerted",
            ("room.vault", "fsm.scene.vault.access"): "open",
            ("npc.guard", "fsm.entity.guard.alert"): "alerted",
            ("system.security", "fsm.system.security"): "breached",
        }
        for (owner_id, machine_id), state in expected.items():
            self.assertEqual(self.runtime.state.get(owner_id, "fsm", machine_id), state)

        door_event = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "door.unlocked"
        )
        world_completion = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.completed"
            and event.payload["state_machine_id"] == "fsm.world.vault_seal"
        )
        region_transition = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload["state_machine_id"] == "fsm.region.gray_crown.alert"
        )
        self.assertEqual(world_completion.causation_id, door_event.event_id)
        self.assertEqual(region_transition.causation_id, world_completion.event_id)
        self.assertEqual(world_completion.visibility, "public")

        entity_transition = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload["state_machine_id"] == "fsm.entity.guard.alert"
        )
        system_transition = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(entity_transition.visibility, "audit")
        self.assertEqual(system_transition.visibility, "audit")

        transition_count = sum(
            event.event_type.startswith("fsm.") for event in self.runtime.event_log.events
        )
        self.runtime.events.publish(EventIR(
            "door.unlocked", "test.repeat", {"door": "door.old_vault"},
            target="door.old_vault",
        ))
        self.assertEqual(
            sum(event.event_type.startswith("fsm.") for event in self.runtime.event_log.events),
            transition_count,
        )

    def test_bounded_owner_condition_blocks_transition_without_blocking_other_scopes(self) -> None:
        package = json.loads(json.dumps(self.package))
        world_seed = next(
            item for item in package["initial_state"]
            if item["owner"] == "gray_crown_demo"
            and item["namespace"] == "fsm"
            and item["key"] == "state"
        )
        world_seed["value"] = "unstable"
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)

        unlock_old_vault(runtime)

        self.assertEqual(
            runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
            "sealed",
        )
        self.assertEqual(
            runtime.state.get("region.gray_crown", "fsm", "fsm.region.gray_crown.alert"),
            "watchful",
        )
        self.assertEqual(
            runtime.state.get("room.vault", "fsm", "fsm.scene.vault.access"),
            "open",
        )
        self.assertFalse(any(
            event.event_type == "fsm.transitioned"
            and event.payload.get("state_machine_id") == "fsm.world.vault_seal"
            for event in runtime.event_log.events
        ))

    def test_actor_condition_requires_verified_causation_and_strict_scalar_types(self) -> None:
        for label, mutate in (
            (
                "missing_actor",
                lambda package: None,
            ),
            (
                "boolean_is_not_one",
                lambda package: package["state_machines"][0]["transitions"][0]["when"][1].update(
                    {"value": 1}
                ),
            ),
        ):
            with self.subTest(label=label):
                package = json.loads(json.dumps(self.package))
                mutate(package)
                runtime = WorldRuntime(package)
                install_builtin_modules(runtime)
                if label == "missing_actor":
                    runtime.events.publish(EventIR(
                        "door.unlocked", "test", {"door": "door.old_vault"},
                        target="door.old_vault",
                    ))
                else:
                    unlock_old_vault(runtime)
                self.assertEqual(
                    runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
                    "sealed",
                )

    def test_highest_priority_transition_is_selected_only_after_conditions_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            machine = source["state_machines"][0]
            machine["states"].append("failed")
            machine["transitions"][0]["when"][0]["value"] = "unstable"
            machine["transitions"].append({
                "transition_id": "fsm.world.vault_seal.fail_closed",
                "from": "sealed",
                "on": "door.unlocked",
                "to": "failed",
                "event_match": {"door": "door.old_vault"},
                "when": [],
                "priority": 0,
            })
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(
                compile_world(world, Path(temp) / "build")
            )
            install_builtin_modules(runtime)

            unlock_old_vault(runtime)

        self.assertEqual(
            runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
            "failed",
        )
        failed = next(
            event for event in runtime.event_log.events
            if event.event_type == "fsm.failed"
            and event.payload["state_machine_id"] == "fsm.world.vault_seal"
        )
        self.assertEqual(
            failed.payload["transition_id"],
            "fsm.world.vault_seal.fail_closed",
        )

    def test_snapshot_and_replay_preserve_every_scoped_state_cell(self) -> None:
        unlock_old_vault(self.runtime)
        snapshot = Path(self.temp.name) / "scoped.snapshot.json"
        self.runtime.save_snapshot(snapshot)

        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        self.assertEqual(restored.state.export(), self.runtime.state.export())

        replayed = WorldRuntime(self.package)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.state.export(), self.runtime.state.export())

    def test_reaction_log_failure_rolls_back_scoped_state(self) -> None:
        before = self.runtime.state.export()
        with patch.object(
            self.runtime.event_log,
            "append_batch",
            side_effect=KernelTransactionError("simulated scoped reaction failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.events.publish(EventIR(
                    "door.unlocked", "test.failure", {"door": "door.old_vault"},
                    target="door.old_vault",
                ))

        self.assertEqual(self.runtime.state.export(), before)
        self.assertEqual(self.runtime.event_log.events, [])

    def test_fsm_terminal_event_can_drive_quest_through_event_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests.append({
                "quest_id": "quest.vault_revealed",
                "title": "庫房封印解除",
                "initial_state": "waiting",
                "transitions": [{
                    "transition_id": "quest.vault_revealed.world_fsm",
                    "from": "waiting",
                    "on": "fsm.completed",
                    "to": "completed",
                    "event_match": {"state_machine_id": "fsm.world.vault_seal"},
                }],
            })
            quests_path.write_text(
                json.dumps(quests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(compile_world(world, Path(temp) / "build"))
            install_builtin_modules(runtime)

            unlock_old_vault(runtime)

            self.assertEqual(
                runtime.state.get("player.neo", "quest", "quest.vault_revealed"),
                "completed",
            )
            fsm_completion = next(
                event for event in runtime.event_log.events
                if event.event_type == "fsm.completed"
                and event.payload["state_machine_id"] == "fsm.world.vault_seal"
            )
            quest_transition = next(
                event for event in runtime.event_log.events
                if event.event_type == "quest.transitioned"
                and event.payload["quest_id"] == "quest.vault_revealed"
            )
            self.assertEqual(quest_transition.causation_id, fsm_completion.event_id)

    def test_compiler_rejects_invalid_owner_graph_effects_and_missing_module(self) -> None:
        def invalid_scene(source: dict, manifest: dict) -> None:
            source["state_machines"][2]["owner_id"] = "room.missing"

        def free_effect(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["transitions"][0]["effects"] = ["set:anything"]

        def unreachable_state(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["states"].append("orphan")

        def duplicate_dispatch(source: dict, manifest: dict) -> None:
            duplicate = dict(source["state_machines"][0]["transitions"][0])
            duplicate["transition_id"] = "fsm.world.vault_seal.duplicate"
            source["state_machines"][0]["transitions"].append(duplicate)

        def terminal_outgoing(source: dict, manifest: dict) -> None:
            machine = source["state_machines"][0]
            machine["states"].append("reopened")
            machine["transitions"].append({
                "transition_id": "fsm.world.vault_seal.reopen",
                "from": "completed",
                "on": "door.opened",
                "to": "reopened",
            })

        def missing_module(source: dict, manifest: dict) -> None:
            manifest["modules"].remove("state_machine.core")

        def invalid_condition_subject(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["transitions"][0]["when"][0]["subject"] = "target"

        def invalid_numeric_condition(source: dict, manifest: dict) -> None:
            condition = source["state_machines"][0]["transitions"][0]["when"][0]
            condition["operator"] = "greater_than"
            condition["value"] = True

        def duplicate_condition_id(source: dict, manifest: dict) -> None:
            conditions = source["state_machines"][0]["transitions"][0]["when"]
            conditions[1]["condition_id"] = conditions[0]["condition_id"]

        def legacy_format_with_conditions(source: dict, manifest: dict) -> None:
            source["format"] = "compilableworld.state-machines/v0.1"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.1"
            )

        def mismatched_source_schema(source: dict, manifest: dict) -> None:
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.1"
            )

        changes = {
            "invalid_scene": invalid_scene,
            "free_effect": free_effect,
            "unreachable_state": unreachable_state,
            "duplicate_dispatch": duplicate_dispatch,
            "terminal_outgoing": terminal_outgoing,
            "missing_module": missing_module,
            "invalid_condition_subject": invalid_condition_subject,
            "invalid_numeric_condition": invalid_numeric_condition,
            "duplicate_condition_id": duplicate_condition_id,
            "legacy_format_with_conditions": legacy_format_with_conditions,
            "mismatched_source_schema": mismatched_source_schema,
        }
        for label, change in changes.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                world = Path(temp) / "world"
                shutil.copytree(GRAY_CROWN, world)
                source_path = world / "state_machines.json"
                manifest_path = world / "manifest.json"
                source = json.loads(source_path.read_text(encoding="utf-8"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                change(source, manifest)
                source_path.write_text(
                    json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                with self.assertRaises(CompileError):
                    compile_world(world, Path(temp) / "build")

    def test_v01_source_remains_supported_and_normalizes_empty_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source["format"] = "compilableworld.state-machines/v0.1"
            for machine in source["state_machines"]:
                for transition in machine["transitions"]:
                    transition.pop("when")
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.1"
            )
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            package = json.loads(
                compile_world(world, Path(temp) / "build").read_text(encoding="utf-8")
            )

        self.assertEqual(
            package["manifest"]["source_schemas"]["state_machines"],
            "compilableworld.schema/state-machines/v0.1",
        )
        self.assertTrue(all(
            transition["when"] == []
            for machine in package["state_machines"]
            for transition in machine["transitions"]
        ))

    def test_studio_overview_projects_static_and_current_scoped_state(self) -> None:
        package_view = package_overview(self.package)
        self.assertEqual(len(package_view["state_machines"]), 5)
        world_record = next(
            item for item in package_view["state_machines"]
            if item["state_machine_id"] == "fsm.world.vault_seal"
        )
        self.assertEqual(world_record["owner_scope"], "world")
        self.assertEqual(world_record["initial_state"], "sealed")
        self.assertEqual(
            [condition["condition_id"] for condition in world_record["transitions"][0]["when"]],
            [
                "world_is_stable", "unlocking_actor_is_alive",
                "unlocking_actor_currency_is_valid",
            ],
        )

        unlock_old_vault(self.runtime)
        live_view = runtime_overview(self.runtime)
        live_world = next(
            item for item in live_view["state_machines"]
            if item["state_machine_id"] == "fsm.world.vault_seal"
        )
        self.assertEqual(live_world["current_state"], "completed")
        self.assertEqual(live_world["state_version"], 1)

    def test_state_machine_module_has_no_direct_action_surface(self) -> None:
        contract = self.runtime.modules["state_machine.core"].contract
        self.assertEqual(contract.actions, [])
        self.assertEqual(contract.write, ["fsm.*"])
        self.assertEqual(contract.requires_kernel, ["state", "event"])

        package = json.loads(json.dumps(self.package))
        transition = package["state_machines"][0]["transitions"][0]
        transition["on"] = "action.failed"
        transition["event_match"] = {"reason": None}
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        runtime.events.publish(EventIR("action.failed", "test", {"verb": "look"}))
        self.assertEqual(
            runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
            "sealed",
        )


if __name__ == "__main__":
    unittest.main()
