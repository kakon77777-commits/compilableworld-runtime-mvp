from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world
from compilableworld.kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
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


def use_legacy_terminal_chain(source: dict) -> None:
    region_transition = source["state_machines"][1]["transitions"][0]
    region_transition["on"] = "fsm.completed"
    region_transition["event_match"] = {"state_machine_id": "fsm.world.vault_seal"}


def condition_leaves(expression: object) -> list[dict]:
    if not isinstance(expression, dict):
        return []
    if "condition_id" in expression:
        return [expression]
    if "not" in expression:
        return condition_leaves(expression["not"])
    children = expression.get("all", expression.get("any", []))
    return [leaf for child in children for leaf in condition_leaves(child)]


def condition_expression_counts(expression: object) -> tuple[int, int]:
    if isinstance(expression, list):
        child_counts = [condition_expression_counts(child) for child in expression]
        return sum(item[0] for item in child_counts), sum(item[1] for item in child_counts)
    if not isinstance(expression, dict):
        return 0, 0
    if "condition_id" in expression:
        return 1, 1
    if "not" in expression:
        nodes, leaves = condition_expression_counts(expression["not"])
        return nodes + 1, leaves
    children = expression.get("all", expression.get("any", []))
    child_counts = [condition_expression_counts(child) for child in children]
    return 1 + sum(item[0] for item in child_counts), sum(item[1] for item in child_counts)


def use_legacy_condition_lists(source: dict) -> None:
    """Downgrade the v0.6 fixture's representable groups to v0.2-v0.5 AND lists."""
    inverse = {
        "equals": "not_equals",
        "not_equals": "equals",
        "less_than": "greater_or_equal",
        "less_or_equal": "greater_than",
        "greater_than": "less_or_equal",
        "greater_or_equal": "less_than",
    }

    def flatten(expression: dict) -> list[dict]:
        if "condition_id" in expression:
            return [deepcopy(expression)]
        if "all" in expression:
            return [leaf for child in expression["all"] for leaf in flatten(child)]
        if "not" in expression and "condition_id" in expression["not"]:
            leaf = deepcopy(expression["not"])
            leaf["operator"] = inverse[leaf["operator"]]
            return [leaf]
        raise AssertionError("fixture condition expression cannot be downgraded to legacy AND")

    for machine in source["state_machines"]:
        for transition in machine["transitions"]:
            transition["when"] = flatten(transition["when"])


def use_flat_state_hierarchy(source: dict) -> None:
    """Downgrade the v0.6 fixture to the flat v0.1-v0.4 source shape."""
    use_legacy_condition_lists(source)
    for machine in source["state_machines"]:
        machine.pop("hierarchy", None)
        if machine["state_machine_id"] == "fsm.system.security":
            machine["states"].remove("incident")
            machine["transitions"][0]["to"] = "breached"


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
            [
                condition["condition_id"]
                for condition in condition_leaves(world_machine["transitions"][0]["when"])
            ],
            [
                "world_is_stable", "unlocking_actor_is_alive",
                "unlocking_actor_currency_is_negative",
            ],
        )
        self.assertIn("state_machine.core", self.package["manifest"]["modules"])
        self.assertEqual(
            self.package["manifest"]["source_schemas"]["state_machines"],
            "compilableworld.schema/state-machines/v0.6",
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
        self.assertEqual(
            cells[("system.security", "fsm_runtime", "fsm.system.security")],
            0,
        )
        system_machine = next(
            machine for machine in self.package["state_machines"]
            if machine["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(system_machine["initial_leaf"], "nominal")
        self.assertEqual(system_machine["hierarchy"], {
            "parent_by_state": {
                "breached": "incident", "contained": "incident",
            },
            "initial_child_by_state": {"incident": "breached"},
        })
        self.assertEqual(system_machine["transitions"][0]["to"], "incident")
        self.assertEqual(system_machine["transitions"][1]["after_ticks"], 2)

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
        security_transition = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload["transition_id"] == "fsm.system.security.vault_unlocked"
        )
        self.assertEqual(world_completion.causation_id, door_event.event_id)
        self.assertEqual(security_transition.causation_id, door_event.event_id)
        self.assertEqual(security_transition.payload["from"], "nominal")
        self.assertEqual(security_transition.payload["to"], "incident")
        self.assertEqual(security_transition.payload["from_leaf"], "nominal")
        self.assertEqual(security_transition.payload["to_leaf"], "breached")
        self.assertEqual(region_transition.causation_id, security_transition.event_id)
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

    def test_nonterminal_chain_rejects_spoofed_source_and_replay_tampering(self) -> None:
        self.runtime.events.publish(EventIR(
            "fsm.transitioned",
            "test.spoof",
            {
                "state_machine_id": "fsm.system.security",
                "title": "安全系統狀態",
                "owner_scope": "system",
                "owner_id": "system.security",
                "transition_id": "fsm.system.security.vault_unlocked",
                "from": "nominal",
                "to": "breached",
                "trigger": "door.unlocked",
            },
        ))
        self.assertEqual(
            self.runtime.state.get("region.gray_crown", "fsm", "fsm.region.gray_crown.alert"),
            "watchful",
        )

        unlock_old_vault(self.runtime)
        tampered = deepcopy(self.runtime.event_log.events)
        transitioned = next(
            event for event in tampered
            if event.event_type == "fsm.transitioned"
            and event.payload["transition_id"] == "fsm.system.security.vault_unlocked"
        )
        transitioned.source = "test.spoof"
        with self.assertRaisesRegex(RuntimeErrorBase, "authored StateIR lifecycle"):
            WorldRuntime(deepcopy(self.package)).replay(tampered)

        tampered_leaf = deepcopy(self.runtime.event_log.events)
        transitioned_leaf = next(
            event for event in tampered_leaf
            if event.event_type == "fsm.transitioned"
            and event.payload["transition_id"] == "fsm.system.security.vault_unlocked"
        )
        transitioned_leaf.payload["to_leaf"] = "contained"
        with self.assertRaisesRegex(RuntimeErrorBase, "authored StateIR lifecycle"):
            WorldRuntime(deepcopy(self.package)).replay(tampered_leaf)

    def test_same_priority_leaf_transition_overrides_compound_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            system = next(
                machine for machine in source["state_machines"]
                if machine["state_machine_id"] == "fsm.system.security"
            )
            system["transitions"].extend([
                {
                    "transition_id": "fsm.system.security.incident_reset",
                    "from": "incident",
                    "on": "door.opened",
                    "to": "nominal",
                    "event_match": {"door": "door.old_vault"},
                    "when": {"all": []},
                    "priority": 50,
                },
                {
                    "transition_id": "fsm.system.security.breach_contained",
                    "from": "breached",
                    "on": "door.opened",
                    "to": "contained",
                    "event_match": {"door": "door.old_vault"},
                    "when": {"all": []},
                    "priority": 50,
                },
            ])
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(
                compile_world(world, Path(temp) / "build")
            )
            install_builtin_modules(runtime)
            unlock_old_vault(runtime)
            runtime.events.publish(EventIR(
                "door.opened", "test", {"door": "door.old_vault"},
                target="door.old_vault",
            ))

        self.assertEqual(
            runtime.state.get("system.security", "fsm", "fsm.system.security"),
            "contained",
        )
        selected = [
            event for event in runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload.get("transition_id")
            in {
                "fsm.system.security.incident_reset",
                "fsm.system.security.breach_contained",
            }
        ]
        self.assertEqual(
            [event.payload["transition_id"] for event in selected],
            ["fsm.system.security.breach_contained"],
        )

    def test_compound_initial_state_materializes_only_its_initial_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["state_machines"].append({
                "state_machine_id": "fsm.system.compound_probe",
                "title": "compound probe",
                "owner_scope": "system",
                "owner_id": "system.compound_probe",
                "states": ["operating", "idle", "busy"],
                "initial_state": "operating",
                "hierarchy": {
                    "parent_by_state": {"idle": "operating", "busy": "operating"},
                    "initial_child_by_state": {"operating": "idle"},
                },
                "persistence": "runtime",
                "visibility": "system_only",
                "authority": "state_machine.core",
                "transitions": [{
                    "transition_id": "fsm.system.compound_probe.activate",
                    "from": "idle",
                    "on": "door.opened",
                    "to": "busy",
                    "event_match": {"door": "door.old_vault"},
                    "when": {"all": []},
                    "priority": 1,
                }],
            })
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            package = json.loads(
                compile_world(world, Path(temp) / "build").read_text(encoding="utf-8")
            )

        machine = next(
            item for item in package["state_machines"]
            if item["state_machine_id"] == "fsm.system.compound_probe"
        )
        self.assertEqual(machine["initial_state"], "operating")
        self.assertEqual(machine["initial_leaf"], "idle")
        cells = [
            item for item in package["initial_state"]
            if item["owner"] == "system.compound_probe"
            and item["namespace"] == "fsm"
        ]
        self.assertEqual([item["value"] for item in cells], ["idle"])

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
            "alerted",
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
                "payload_actor_without_causation",
                lambda package: None,
            ),
            (
                "boolean_is_not_one",
                lambda package: condition_leaves(
                    package["state_machines"][0]["transitions"][0]["when"]
                )[1].update(
                    {"value": 1}
                ),
            ),
        ):
            with self.subTest(label=label):
                package = json.loads(json.dumps(self.package))
                mutate(package)
                runtime = WorldRuntime(package)
                install_builtin_modules(runtime)
                if label in {"missing_actor", "payload_actor_without_causation"}:
                    payload = {"door": "door.old_vault"}
                    if label == "payload_actor_without_causation":
                        payload["actor"] = "player.neo"
                    runtime.events.publish(EventIR(
                        "door.unlocked", "test", payload,
                        target="door.old_vault",
                    ))
                else:
                    unlock_old_vault(runtime)
                self.assertEqual(
                    runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
                    "sealed",
                )

    def test_any_and_not_groups_preserve_three_valued_fail_closed_semantics(self) -> None:
        base_transition = self.package["state_machines"][0]["transitions"][0]
        stable, alive, negative = [
            deepcopy(condition) for condition in condition_leaves(base_transition["when"])
        ]
        missing = deepcopy(stable)
        missing.update({"condition_id": "missing_owner_state", "key": "missing_state"})

        any_package = deepcopy(self.package)
        any_package["state_machines"][0]["transitions"][0]["when"] = {
            "all": [
                {"any": [missing, stable]},
                alive,
                {"not": negative},
            ]
        }
        any_runtime = WorldRuntime(any_package)
        install_builtin_modules(any_runtime)
        unlock_old_vault(any_runtime)
        self.assertEqual(
            any_runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
            "completed",
        )

        unknown_not_package = deepcopy(self.package)
        unknown_not_package["state_machines"][0]["transitions"][0]["when"] = {
            "not": missing,
        }
        unknown_not_runtime = WorldRuntime(unknown_not_package)
        install_builtin_modules(unknown_not_runtime)
        unlock_old_vault(unknown_not_runtime)
        self.assertEqual(
            unknown_not_runtime.state.get(
                "gray_crown_demo", "fsm", "fsm.world.vault_seal",
            ),
            "sealed",
        )

        false_leaf = deepcopy(stable)
        false_leaf.update({"condition_id": "world_is_not_unstable", "value": "unstable"})
        false_not_package = deepcopy(self.package)
        false_not_package["state_machines"][0]["transitions"][0]["when"] = {
            "not": false_leaf,
        }
        false_not_runtime = WorldRuntime(false_not_package)
        install_builtin_modules(false_not_runtime)
        unlock_old_vault(false_not_runtime)
        self.assertEqual(
            false_not_runtime.state.get(
                "gray_crown_demo", "fsm", "fsm.world.vault_seal",
            ),
            "completed",
        )

    def test_authored_any_not_round_trip_survives_studio_snapshot_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            transition = source["state_machines"][0]["transitions"][0]
            stable, alive, not_negative = deepcopy(transition["when"]["all"])
            stable_fallback = deepcopy(stable)
            stable_fallback["condition_id"] = "world_is_stable_fallback"
            authored_when = {
                "all": [
                    {"any": [stable, stable_fallback]},
                    alive,
                    not_negative,
                ]
            }
            transition["when"] = authored_when
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            package_path = compile_world(world, Path(temp) / "build")
            package = json.loads(package_path.read_text(encoding="utf-8"))
            compiled_when = package["state_machines"][0]["transitions"][0]["when"]
            self.assertEqual(compiled_when, authored_when)
            self.assertEqual(
                package_overview(package)["state_machines"][0]["transitions"][0]["when"],
                authored_when,
            )

            runtime = WorldRuntime.from_package(package_path)
            install_builtin_modules(runtime)
            snapshot = Path(temp) / "before-unlock.snapshot.json"
            runtime.save_snapshot(snapshot)
            restored = WorldRuntime.from_package(package_path)
            install_builtin_modules(restored)
            restored.load_snapshot(snapshot)
            unlock_old_vault(runtime)
            unlock_old_vault(restored)
            self.assertEqual(restored.state.export(), runtime.state.export())
            self.assertEqual(
                runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
                "completed",
            )

            replayed = WorldRuntime.from_package(package_path)
            replayed.replay(runtime.event_log.events)
            self.assertEqual(replayed.state.export(), runtime.state.export())

    def test_compiler_and_loader_accept_exact_condition_node_and_leaf_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            base = deepcopy(
                source["state_machines"][0]["transitions"][0]["when"]["all"][0]
            )
            root_children = []
            leaf_index = 0
            for group_index in range(16):
                children = []
                if group_index < 15:
                    children.append({"all": []})
                for _ in range(2):
                    leaf = deepcopy(base)
                    leaf["condition_id"] = f"budget_leaf_{leaf_index}"
                    children.append(leaf)
                    leaf_index += 1
                root_children.append({"all": children})
            exact_limit = {"all": root_children}
            self.assertEqual(condition_expression_counts(exact_limit), (64, 32))
            source["state_machines"][0]["transitions"][0]["when"] = exact_limit
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            package_path = compile_world(world, Path(temp) / "build")
            runtime = WorldRuntime.from_package(package_path)
            install_builtin_modules(runtime)
            unlock_old_vault(runtime)
            self.assertEqual(
                runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
                "completed",
            )

    def test_runtime_fails_closed_on_malformed_or_overbudget_condition_groups(self) -> None:
        stable = deepcopy(condition_leaves(
            self.package["state_machines"][0]["transitions"][0]["when"]
        )[0])
        too_deep: dict = deepcopy(stable)
        for _ in range(5):
            too_deep = {"not": too_deep}
        too_many_nodes = {
            "all": [
                {"all": [{"all": []} for _ in range(4)]}
                for _ in range(16)
            ]
        }
        leaf_index = 0
        leaf_groups = []
        for _ in range(11):
            children = []
            for _ in range(3):
                leaf = deepcopy(stable)
                leaf["condition_id"] = f"runtime_leaf_{leaf_index}"
                children.append(leaf)
                leaf_index += 1
            leaf_groups.append({"any": children})
        too_many_leaves = {"all": leaf_groups}

        expressions = {
            "empty_any": {"any": []},
            "malformed_hidden_by_true_any": {"any": [stable, {"xor": []}]},
            "duplicate_leaf_id": {"all": [stable, deepcopy(stable)]},
            "too_deep": too_deep,
            "too_many_nodes": too_many_nodes,
            "too_many_leaves": too_many_leaves,
        }
        for label, expression in expressions.items():
            with self.subTest(label=label):
                package = deepcopy(self.package)
                package["state_machines"][0]["transitions"][0]["when"] = expression
                runtime = WorldRuntime(package)
                install_builtin_modules(runtime)
                unlock_old_vault(runtime)
                self.assertEqual(
                    runtime.state.get(
                        "gray_crown_demo", "fsm", "fsm.world.vault_seal",
                    ),
                    "sealed",
                )

    def test_package_loader_rejects_invalid_stateir_and_missing_provenance(self) -> None:
        def missing_when(package: dict) -> None:
            package["state_machines"][0]["transitions"][0].pop("when")

        def invalid_condition_id(package: dict) -> None:
            condition_leaves(
                package["state_machines"][0]["transitions"][0]["when"]
            )[0]["condition_id"] = "Invalid Condition"

        def extra_transition_field(field: str):
            return lambda package: package["state_machines"][0]["transitions"][0].__setitem__(
                field, "metadata only",
            )

        def missing_schema_contract(package: dict) -> None:
            package["schema_contracts"].pop("runtime_package")

        def missing_source_checksums(package: dict) -> None:
            package["source_checksums"] = {}

        def unknown_owner(package: dict) -> None:
            package["state_machines"][2]["owner_id"] = "room.not_real"

        def reaction_cycle(package: dict) -> None:
            transition = package["state_machines"][1]["transitions"][0]
            transition["event_match"] = {
                "state_machine_id": "fsm.region.gray_crown.alert",
                "transition_id": transition["transition_id"],
            }

        mutations = {
            "missing_when": missing_when,
            "invalid_condition_id": invalid_condition_id,
            "guard_is_not_runtime_rule": extra_transition_field("guard"),
            "instructions_are_not_runtime_rule": extra_transition_field("instructions"),
            "responses_are_not_runtime_rule": extra_transition_field("responses"),
            "missing_schema_contract": missing_schema_contract,
            "missing_source_checksums": missing_source_checksums,
            "unknown_owner": unknown_owner,
            "reaction_cycle": reaction_cycle,
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                package = deepcopy(self.package)
                mutate(package)
                path = Path(self.temp.name) / f"{label}.package.json"
                path.write_text(json.dumps(package), encoding="utf-8")
                with self.assertRaises(RuntimeErrorBase):
                    WorldRuntime.from_package(path)

    def test_highest_priority_transition_is_selected_only_after_conditions_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            machine = source["state_machines"][0]
            machine["states"].append("failed")
            condition_leaves(machine["transitions"][0]["when"])[0]["value"] = "unstable"
            machine["transitions"].append({
                "transition_id": "fsm.world.vault_seal.fail_closed",
                "from": "sealed",
                "on": "door.unlocked",
                "to": "failed",
                "event_match": {"door": "door.old_vault"},
                "when": {"all": []},
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

    def test_bounded_timer_uses_entry_tick_snapshot_and_replay(self) -> None:
        unlock_old_vault(self.runtime)
        self.runtime.advance(1)
        self.assertEqual(
            self.runtime.state.get("system.security", "fsm", "fsm.system.security"),
            "breached",
        )

        snapshot = Path(self.temp.name) / "timer.snapshot.json"
        self.runtime.save_snapshot(snapshot)
        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)

        self.runtime.advance(1)
        restored.advance(1)
        self.assertEqual(
            self.runtime.state.get("system.security", "fsm", "fsm.system.security"),
            "contained",
        )
        self.assertEqual(restored.state.export(), self.runtime.state.export())

        timer_event = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.timer_elapsed"
        )
        transition_event = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.transitioned"
            and event.payload["transition_id"] == "fsm.system.security.auto_contained"
        )
        self.assertEqual(timer_event.timestamp_tick, 2)
        self.assertEqual(timer_event.payload["entered_tick"], 0)
        self.assertEqual(timer_event.payload["eligible_at_tick"], 2)
        self.assertEqual(timer_event.payload["fired_at_tick"], 2)
        self.assertEqual(timer_event.correlation_id, timer_event.event_id)
        self.assertEqual(transition_event.causation_id, timer_event.event_id)
        timer_index = self.runtime.event_log.events.index(timer_event)
        timer_commit = self.runtime.event_log.events[timer_index - 1]
        self.assertEqual(timer_commit.event_type, "state.committed")
        self.assertEqual(
            {
                (item["namespace"], item["key"], item["value"])
                for item in timer_commit.payload["applied"]
            },
            {
                ("fsm", "fsm.system.security", "contained"),
                ("fsm_runtime", "fsm.system.security", 2),
            },
        )

        replayed = WorldRuntime(self.package)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.state.export(), self.runtime.state.export())
        self.assertEqual(replayed.scheduler.tick, 2)

    def test_replay_restores_nonzero_tick_before_timer_continuation(self) -> None:
        runtime = WorldRuntime(deepcopy(self.package))
        install_builtin_modules(runtime)
        runtime.advance(5)
        unlock_old_vault(runtime)
        self.assertEqual(
            runtime.state.get(
                "system.security", "fsm_runtime", "fsm.system.security",
            ),
            5,
        )

        replayed = WorldRuntime(deepcopy(self.package))
        install_builtin_modules(replayed)
        replayed.replay(runtime.event_log.events)
        self.assertEqual(replayed.scheduler.tick, 5)
        self.assertEqual(replayed.state.export(), runtime.state.export())

        runtime.advance(2)
        replayed.advance(2)
        self.assertEqual(replayed.scheduler.tick, 7)
        self.assertEqual(replayed.state.export(), runtime.state.export())

    def test_timer_conditions_remain_eligible_and_priority_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            machine = next(
                item for item in source["state_machines"]
                if item["state_machine_id"] == "fsm.system.security"
            )
            machine["states"].append("lockdown")
            high = machine["transitions"][1]
            high["to"] = "lockdown"
            high["when"] = {"all": [{
                "condition_id": "security_is_armed",
                "subject": "owner",
                "namespace": "status",
                "key": "armed",
                "operator": "equals",
                "value": True,
            }]}
            machine["transitions"].append({
                "transition_id": "fsm.system.security.fallback_contained",
                "from": "breached",
                "after_ticks": 3,
                "to": "contained",
                "when": {"all": []},
                "priority": 0,
            })
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(compile_world(world, Path(temp) / "build"))
            install_builtin_modules(runtime)

            unlock_old_vault(runtime)
            runtime.state.seed("system.security", "status", "armed", False)
            runtime.advance(2)
            self.assertEqual(
                runtime.state.get("system.security", "fsm", "fsm.system.security"),
                "breached",
            )
            runtime.state.seed("system.security", "status", "armed", True)
            runtime.advance(1)

        self.assertEqual(
            runtime.state.get("system.security", "fsm", "fsm.system.security"),
            "lockdown",
        )
        timer_event = next(
            event for event in runtime.event_log.events
            if event.event_type == "fsm.timer_elapsed"
        )
        self.assertEqual(timer_event.payload["transition_id"], high["transition_id"])
        self.assertEqual(timer_event.payload["eligible_at_tick"], 2)
        self.assertEqual(timer_event.payload["fired_at_tick"], 3)

    def test_timer_log_failure_rolls_back_transition_and_retries_when_overdue(self) -> None:
        unlock_old_vault(self.runtime)
        before = self.runtime.state.export()
        existing_events = list(self.runtime.event_log.events)
        self.runtime.advance(1)
        append_batch = self.runtime.event_log.append_batch

        def fail_timer_batch(events) -> None:
            batch = list(events)
            if not batch:
                append_batch(batch)
                return
            raise KernelTransactionError("simulated timer append failure")

        with patch.object(
            self.runtime.event_log,
            "append_batch",
            side_effect=fail_timer_batch,
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.advance(1)

        self.assertEqual(self.runtime.state.export(), before)
        self.assertEqual(self.runtime.event_log.events, existing_events)
        self.assertEqual(self.runtime.scheduler.tick, 2)

        self.runtime.advance(1)
        timer_event = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "fsm.timer_elapsed"
        )
        self.assertEqual(timer_event.payload["eligible_at_tick"], 2)
        self.assertEqual(timer_event.payload["fired_at_tick"], 3)

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

            runtime.events.publish(EventIR(
                "fsm.completed",
                "test.spoof",
                {
                    "state_machine_id": "fsm.world.vault_seal",
                    "title": "舊王室庫房封印",
                    "owner_scope": "world",
                    "owner_id": "gray_crown_demo",
                    "transition_id": "fsm.world.vault_seal.unlocked",
                    "from": "sealed",
                    "to": "completed",
                    "trigger": "door.unlocked",
                },
                target="player.neo",
            ))
            self.assertEqual(
                runtime.state.get("player.neo", "quest", "quest.vault_revealed"),
                "waiting",
            )
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
            condition_leaves(
                source["state_machines"][0]["transitions"][0]["when"]
            )[0]["subject"] = "target"

        def invalid_numeric_condition(source: dict, manifest: dict) -> None:
            condition = condition_leaves(
                source["state_machines"][0]["transitions"][0]["when"]
            )[0]
            condition["operator"] = "greater_than"
            condition["value"] = True

        def duplicate_condition_id(source: dict, manifest: dict) -> None:
            conditions = condition_leaves(
                source["state_machines"][0]["transitions"][0]["when"]
            )
            conditions[1]["condition_id"] = conditions[0]["condition_id"]

        def empty_any_group(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["transitions"][0]["when"] = {"any": []}

        def unknown_condition_group(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["transitions"][0]["when"] = {"xor": []}

        def condition_group_too_deep(source: dict, manifest: dict) -> None:
            leaf = condition_leaves(
                source["state_machines"][0]["transitions"][0]["when"]
            )[0]
            expression: dict = deepcopy(leaf)
            for _ in range(5):
                expression = {"not": expression}
            source["state_machines"][0]["transitions"][0]["when"] = expression

        def condition_group_too_many_nodes(source: dict, manifest: dict) -> None:
            source["state_machines"][0]["transitions"][0]["when"] = {
                "all": [
                    {"all": [{"all": []} for _ in range(4)]}
                    for _ in range(16)
                ]
            }

        def condition_group_too_many_leaves(source: dict, manifest: dict) -> None:
            template = condition_leaves(
                source["state_machines"][0]["transitions"][0]["when"]
            )[0]
            index = 0
            groups = []
            for _ in range(11):
                children = []
                for _ in range(3):
                    leaf = deepcopy(template)
                    leaf["condition_id"] = f"bounded_leaf_{index}"
                    children.append(leaf)
                    index += 1
                groups.append({"any": children})
            source["state_machines"][0]["transitions"][0]["when"] = {"all": groups}

        def v06_with_legacy_condition_list(source: dict, manifest: dict) -> None:
            use_legacy_condition_lists(source)

        def legacy_format_with_conditions(source: dict, manifest: dict) -> None:
            source["format"] = "compilableworld.state-machines/v0.1"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.1"
            )

        def mismatched_source_schema(source: dict, manifest: dict) -> None:
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.1"
            )

        def invalid_timer_delay(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["transitions"][1]["after_ticks"] = True

        def timer_with_event_match(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["transitions"][1]["event_match"] = {}

        def timer_with_event_trigger(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["transitions"][1]["on"] = "door.opened"

        def timer_with_actor_condition(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["transitions"][1]["when"] = {"all": [{
                "condition_id": "invalid_timer_actor",
                "subject": "actor",
                "namespace": "status",
                "key": "alive",
                "operator": "equals",
                "value": True,
            }]}

        def duplicate_timer_priority(source: dict, manifest: dict) -> None:
            duplicate = dict(source["state_machines"][4]["transitions"][1])
            duplicate["transition_id"] = "fsm.system.security.ambiguous_timer"
            duplicate["after_ticks"] = 3
            source["state_machines"][4]["transitions"].append(duplicate)

        def v02_with_timer(source: dict, manifest: dict) -> None:
            source["format"] = "compilableworld.state-machines/v0.2"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.2"
            )

        def nonterminal_missing_explicit_source(source: dict, manifest: dict) -> None:
            source["state_machines"][1]["transitions"][0]["event_match"].pop("transition_id")

        def nonterminal_unknown_source_transition(source: dict, manifest: dict) -> None:
            source["state_machines"][1]["transitions"][0]["event_match"]["transition_id"] = (
                "fsm.system.security.missing"
            )

        def nonterminal_mismatched_source_payload(source: dict, manifest: dict) -> None:
            source["state_machines"][1]["transitions"][0]["event_match"]["to"] = "contained"

        def nonterminal_dependency_cycle(source: dict, manifest: dict) -> None:
            transition = source["state_machines"][4]["transitions"][0]
            transition["on"] = "fsm.transitioned"
            transition["event_match"] = {
                "state_machine_id": "fsm.region.gray_crown.alert",
                "transition_id": "fsm.region.gray_crown.vault_revealed",
            }

        def nonterminal_dependency_too_deep(source: dict, manifest: dict) -> None:
            previous_machine = "fsm.system.security"
            previous_transition = "fsm.system.security.vault_unlocked"
            for index in range(65):
                machine_id = f"fsm.system.chain.{index}"
                transition_id = f"fsm.system.chain.{index}.advance"
                source["state_machines"].append({
                    "state_machine_id": machine_id,
                    "title": f"chain {index}",
                    "owner_scope": "system",
                    "owner_id": f"system.chain.{index}",
                    "states": ["idle", "done"],
                    "initial_state": "idle",
                    "persistence": "runtime",
                    "visibility": "system_only",
                    "authority": "state_machine.core",
                    "transitions": [{
                        "transition_id": transition_id,
                        "from": "idle",
                        "on": "fsm.transitioned",
                        "to": "done",
                        "event_match": {
                            "state_machine_id": previous_machine,
                            "transition_id": previous_transition,
                        },
                        "when": {"all": []},
                        "priority": 0,
                    }],
                })
                previous_machine = machine_id
                previous_transition = transition_id

        def v03_with_nonterminal_chain(source: dict, manifest: dict) -> None:
            source["format"] = "compilableworld.state-machines/v0.3"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.3"
            )

        def v04_with_hierarchy_payload(source: dict, manifest: dict) -> None:
            use_flat_state_hierarchy(source)
            source["format"] = "compilableworld.state-machines/v0.4"
            source["state_machines"][1]["transitions"][0]["event_match"][
                "to_leaf"
            ] = "breached"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.4"
            )

        def hierarchy_cycle(source: dict, manifest: dict) -> None:
            hierarchy = source["state_machines"][4]["hierarchy"]
            hierarchy["parent_by_state"]["incident"] = "breached"
            hierarchy["initial_child_by_state"]["breached"] = "incident"

        def hierarchy_missing_initial_child(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["hierarchy"][
                "initial_child_by_state"
            ].pop("incident")

        def hierarchy_non_direct_initial_child(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["hierarchy"][
                "initial_child_by_state"
            ]["incident"] = "nominal"

        def hierarchy_timer_from_compound(source: dict, manifest: dict) -> None:
            timer = source["state_machines"][4]["transitions"][1]
            timer["from"] = "incident"
            timer["to"] = "nominal"

        def hierarchy_target_inside_source(source: dict, manifest: dict) -> None:
            source["state_machines"][4]["transitions"].append({
                "transition_id": "fsm.system.security.invalid_internal_reset",
                "from": "incident",
                "on": "door.opened",
                "to": "contained",
                "event_match": {"door": "door.old_vault"},
                "when": {"all": []},
                "priority": 1,
            })

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
            "empty_any_group": empty_any_group,
            "unknown_condition_group": unknown_condition_group,
            "condition_group_too_deep": condition_group_too_deep,
            "condition_group_too_many_nodes": condition_group_too_many_nodes,
            "condition_group_too_many_leaves": condition_group_too_many_leaves,
            "v06_with_legacy_condition_list": v06_with_legacy_condition_list,
            "legacy_format_with_conditions": legacy_format_with_conditions,
            "mismatched_source_schema": mismatched_source_schema,
            "invalid_timer_delay": invalid_timer_delay,
            "timer_with_event_match": timer_with_event_match,
            "timer_with_event_trigger": timer_with_event_trigger,
            "timer_with_actor_condition": timer_with_actor_condition,
            "duplicate_timer_priority": duplicate_timer_priority,
            "v02_with_timer": v02_with_timer,
            "nonterminal_missing_explicit_source": nonterminal_missing_explicit_source,
            "nonterminal_unknown_source_transition": nonterminal_unknown_source_transition,
            "nonterminal_mismatched_source_payload": nonterminal_mismatched_source_payload,
            "nonterminal_dependency_cycle": nonterminal_dependency_cycle,
            "nonterminal_dependency_too_deep": nonterminal_dependency_too_deep,
            "v03_with_nonterminal_chain": v03_with_nonterminal_chain,
            "v04_with_hierarchy_payload": v04_with_hierarchy_payload,
            "hierarchy_cycle": hierarchy_cycle,
            "hierarchy_missing_initial_child": hierarchy_missing_initial_child,
            "hierarchy_non_direct_initial_child": hierarchy_non_direct_initial_child,
            "hierarchy_timer_from_compound": hierarchy_timer_from_compound,
            "hierarchy_target_inside_source": hierarchy_target_inside_source,
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
            use_legacy_terminal_chain(source)
            use_flat_state_hierarchy(source)
            source["format"] = "compilableworld.state-machines/v0.1"
            for machine in source["state_machines"]:
                machine["transitions"] = [
                    transition for transition in machine["transitions"]
                    if "after_ticks" not in transition
                ]
                if machine["state_machine_id"] == "fsm.system.security":
                    machine["states"].remove("contained")
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

    def test_v02_source_remains_supported_without_timers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            use_legacy_terminal_chain(source)
            use_flat_state_hierarchy(source)
            source["format"] = "compilableworld.state-machines/v0.2"
            for machine in source["state_machines"]:
                machine["transitions"] = [
                    transition for transition in machine["transitions"]
                    if "after_ticks" not in transition
                ]
                if machine["state_machine_id"] == "fsm.system.security":
                    machine["states"].remove("contained")
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.2"
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
            "compilableworld.schema/state-machines/v0.2",
        )
        self.assertFalse(any(
            "after_ticks" in transition
            for machine in package["state_machines"]
            for transition in machine["transitions"]
        ))

    def test_v03_source_remains_supported_with_timers_but_without_nonterminal_chaining(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            use_legacy_terminal_chain(source)
            use_flat_state_hierarchy(source)
            source["format"] = "compilableworld.state-machines/v0.3"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.3"
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
            "compilableworld.schema/state-machines/v0.3",
        )
        self.assertTrue(any(
            "after_ticks" in transition
            for machine in package["state_machines"]
            for transition in machine["transitions"]
        ))

    def test_v04_source_remains_supported_with_flat_nonterminal_chaining(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            use_flat_state_hierarchy(source)
            source["format"] = "compilableworld.state-machines/v0.4"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.4"
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
            "compilableworld.schema/state-machines/v0.4",
        )
        system = next(
            machine for machine in package["state_machines"]
            if machine["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(system["hierarchy"], {
            "parent_by_state": {}, "initial_child_by_state": {},
        })
        self.assertEqual(system["initial_leaf"], "nominal")
        self.assertEqual(system["transitions"][0]["to"], "breached")

        legacy_package = deepcopy(package)
        for machine in legacy_package["state_machines"]:
            machine.pop("initial_leaf")
            machine.pop("hierarchy")
        runtime = WorldRuntime(deepcopy(legacy_package))
        install_builtin_modules(runtime)
        unlock_old_vault(runtime)
        replayed = WorldRuntime(deepcopy(legacy_package))
        replayed.replay(deepcopy(runtime.event_log.events))
        self.assertEqual(
            replayed.state.get("system.security", "fsm", "fsm.system.security"),
            "breached",
        )

    def test_v05_source_remains_supported_with_hierarchy_and_legacy_condition_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "state_machines.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            use_legacy_condition_lists(source)
            source["format"] = "compilableworld.state-machines/v0.5"
            manifest["source_schemas"]["state_machines"] = (
                "compilableworld.schema/state-machines/v0.5"
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
            "compilableworld.schema/state-machines/v0.5",
        )
        self.assertIsInstance(package["state_machines"][0]["transitions"][0]["when"], list)
        system = next(
            machine for machine in package["state_machines"]
            if machine["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(system["initial_leaf"], "nominal")
        self.assertEqual(system["hierarchy"]["initial_child_by_state"], {
            "incident": "breached",
        })
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        unlock_old_vault(runtime)
        self.assertEqual(
            runtime.state.get("gray_crown_demo", "fsm", "fsm.world.vault_seal"),
            "completed",
        )

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
            [
                condition["condition_id"]
                for condition in condition_leaves(world_record["transitions"][0]["when"])
            ],
            [
                "world_is_stable", "unlocking_actor_is_alive",
                "unlocking_actor_currency_is_negative",
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
        live_system = next(
            item for item in live_view["state_machines"]
            if item["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(live_system["entered_tick"], 0)
        self.assertEqual(live_system["current_state"], "breached")
        self.assertEqual(live_system["current_path"], ["incident", "breached"])
        self.assertEqual(live_system["pending_timers"], [{
            "transition_id": "fsm.system.security.auto_contained",
            "after_ticks": 2,
            "eligible_at_tick": 2,
            "remaining_ticks": 2,
            "eligible": False,
        }])
        static_system = next(
            item for item in package_view["state_machines"]
            if item["state_machine_id"] == "fsm.system.security"
        )
        self.assertEqual(static_system["transitions"][1]["trigger_kind"], "timer")
        self.assertEqual(static_system["transitions"][1]["after_ticks"], 2)
        self.assertEqual(static_system["initial_path"], ["nominal"])
        self.assertEqual(
            static_system["transitions"][0]["resolved_to_leaf"], "breached",
        )

    def test_state_machine_module_has_no_direct_action_surface(self) -> None:
        contract = self.runtime.modules["state_machine.core"].contract
        self.assertEqual(contract.actions, [])
        self.assertEqual(contract.write, ["fsm.*", "fsm_runtime.*"])
        self.assertEqual(contract.requires_kernel, ["state", "event", "clock"])

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

    def test_runtime_fails_closed_on_malformed_compound_package(self) -> None:
        package = deepcopy(self.package)
        system = next(
            machine for machine in package["state_machines"]
            if machine["state_machine_id"] == "fsm.system.security"
        )
        system["hierarchy"]["initial_child_by_state"]["incident"] = "nominal"
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)

        unlock_old_vault(runtime)

        self.assertEqual(
            runtime.state.get("system.security", "fsm", "fsm.system.security"),
            "nominal",
        )
        self.assertFalse(any(
            event.event_type == "fsm.transitioned"
            and event.payload.get("state_machine_id") == "fsm.system.security"
            for event in runtime.event_log.events
        ))


if __name__ == "__main__":
    unittest.main()
