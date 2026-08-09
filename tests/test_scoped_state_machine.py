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
        self.assertIn("state_machine.core", self.package["manifest"]["modules"])
        self.assertEqual(
            self.package["manifest"]["source_schemas"]["state_machines"],
            "compilableworld.schema/state-machines/v0.1",
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

        changes = {
            "invalid_scene": invalid_scene,
            "free_effect": free_effect,
            "unreachable_state": unreachable_state,
            "duplicate_dispatch": duplicate_dispatch,
            "terminal_outgoing": terminal_outgoing,
            "missing_module": missing_module,
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

    def test_studio_overview_projects_static_and_current_scoped_state(self) -> None:
        package_view = package_overview(self.package)
        self.assertEqual(len(package_view["state_machines"]), 5)
        world_record = next(
            item for item in package_view["state_machines"]
            if item["state_machine_id"] == "fsm.world.vault_seal"
        )
        self.assertEqual(world_record["owner_scope"], "world")
        self.assertEqual(world_record["initial_state"], "sealed")

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
